// The schedule queue's rules, as pure functions: what order things go in, how close
// two may be, what a time may be, what the limits allow, what to do with a run that
// woke up late, and what to call every state. Scheduled Statuses, docs/scheduling.md
// Sections 4 and 14.
//
// Nothing here touches Chrome, a clock or storage. The worker (schedule.js) and the
// queue page (queue-page.js) both load this one file, so the page shows the words the
// worker decided and a preview equals what is saved. Every function takes `now`
// explicitly, never mutates what it is given, and returns new objects; an item that
// changes gets its `rev` bumped (FR-17), so a stale edit is refused by whoever stores
// the result. Times are epoch milliseconds; quiet hours and the words for a time are
// the local time of whoever runs this, because that is the person's clock.
(function (root) {
  "use strict";

  const SPACING_MS = 90000;               // two posts closer than this look like a script
  const MIN_AHEAD_MS = 120000;            // a run starts LEAD_MS early, and needs a moment
  const MAX_AHEAD_MS = 30 * 86400000;     // FR-18
  const CATCH_UP_MS = 1800000;            // D4: how late a run may still go out
  const LEAD_MS = 120000;                 // T4: load the composer early so it is ready at the due time
  const PREWARM_MS = 300000;              // FR-10
  const UNDO_MS = 10000;                  // FR-4
  // A run that starts a little after its due time is an ordinary run, not a catch up.
  // Without this an alarm that fires 3 s late inside quiet hours, for a post the person
  // was warned about and chose, would be thrown away as "late at night".
  const QUIET_GRACE_MS = LEAD_MS;
  const COMMENT_MAX = 1024;               // a WhatsApp caption

  // Table SC-8, Release 1 subset. Pending is everything still owed to the person, which
  // is what the limits count; only done and cancelled are finished.
  const PENDING = ["holding", "scheduled", "prewarmed", "waiting", "running", "asked",
    "prepared", "failed", "missed"];
  const TERMINAL = ["done", "cancelled"];
  // A row in these can still be run by the worker, so a pause or a resume matters to it.
  const RUNNABLE = ["scheduled", "prewarmed", "waiting"];
  // Where a row that is being given a new time starts again from.
  const REARM = ["missed", "failed", "asked", "waiting", "prewarmed"];

  const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  // -- ordering -----------------------------------------------------------------

  function byOrder(a, b) {
    if (a.due !== b.due) return a.due - b.due;
    if (a.created !== b.created) return (a.created || 0) - (b.created || 0);
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  }

  // Due time, then who was made first, then id, so the order is the same everywhere
  // and two equal times never swap places between renders.
  function sorted(items) {
    return items.slice().sort(byOrder);
  }

  function pending(items) {
    return items.filter((item) => PENDING.includes(item.state));
  }

  function find(items, id) {
    return items.find((item) => item.id === id) || null;
  }

  function replaceIn(items, changed) {
    const by = new Map(changed.map((item) => [item.id, item]));
    return sorted(items.map((item) => by.get(item.id) || item));
  }

  function bumped(item, fields) {
    return { ...item, ...fields, rev: (item.rev || 0) + 1 };
  }

  // -- the clock ----------------------------------------------------------------

  function minutesOf(hhmm) {
    const match = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || ""));
    if (!match) return null;
    const h = Number(match[1]);
    const m = Number(match[2]);
    return h < 24 && m < 60 ? h * 60 + m : null;
  }

  // Quiet hours as {on, start, end}, local time, spanning midnight when start is later
  // than end. A missing or unreadable pair means there are none, rather than a guess.
  function quietSpan(quiet) {
    if (!quiet || !quiet.on) return null;
    const start = minutesOf(quiet.start);
    const end = minutesOf(quiet.end);
    if (start === null || end === null || start === end) return null;
    return { start, end };
  }

  function inQuiet(ts, quiet) {
    const span = quietSpan(quiet);
    if (!span) return false;
    const d = new Date(ts);
    const m = d.getHours() * 60 + d.getMinutes();
    return span.start < span.end ? m >= span.start && m < span.end : m >= span.start || m < span.end;
  }

  // The next moment quiet hours end, at or after ts. `setDate` rather than adding 24
  // hours, so a daylight saving change cannot land it an hour off.
  function quietEnds(ts, quiet) {
    const span = quietSpan(quiet);
    if (!span) return ts;
    const d = new Date(ts);
    d.setHours(Math.floor(span.end / 60), span.end % 60, 0, 0);
    if (d.getTime() < ts) d.setDate(d.getDate() + 1);
    return d.getTime();
  }

  function quietWords(quiet) {
    return `${quiet.start} to ${quiet.end}`;
  }

  function sameDay(a, b) {
    const x = new Date(a);
    const y = new Date(b);
    return x.getFullYear() === y.getFullYear() && x.getMonth() === y.getMonth() && x.getDate() === y.getDate();
  }

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  // 9:00 AM, or 9:01:30 AM when seconds matter (a time that was moved by 90 s).
  function clock(ts, withSeconds) {
    const d = new Date(ts);
    const h = d.getHours();
    const secs = withSeconds && d.getSeconds() ? `:${pad2(d.getSeconds())}` : "";
    return `${h % 12 || 12}:${pad2(d.getMinutes())}${secs} ${h < 12 ? "AM" : "PM"}`;
  }

  // Wed 5 Nov, 9:00 AM; the year only when it is not this one.
  function dayAndClock(ts, now, withSeconds) {
    const d = new Date(ts);
    const year = now !== undefined && d.getFullYear() !== new Date(now).getFullYear() ? ` ${d.getFullYear()}` : "";
    return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}${year}, ${clock(ts, withSeconds)}`;
  }

  function plural(n, word) {
    return `${n} ${word}${n === 1 ? "" : "s"}`;
  }

  function relative(diff) {
    const future = diff >= 0;
    const minutes = Math.round(Math.abs(diff) / 60000);
    let span;
    if (minutes < 1) return "now";
    if (minutes < 120) span = plural(minutes, "minute");
    else if (minutes < 48 * 60) span = plural(Math.round(minutes / 60), "hour");
    else span = plural(Math.round(minutes / 1440), "day");
    return future ? `in ${span}` : `${span} ago`;
  }

  // "Wed 5 Nov, 9:00 AM, in 4 days": the interpreted time in words, shown before saving
  // and under a time being edited (FR-1, FR-5).
  function describe(due, now) {
    if (!Number.isFinite(due)) return "";
    return `${dayAndClock(due, now, false)}, ${relative(due - now)}`;
  }

  // -- a time the person chose --------------------------------------------------

  function checkDue(due, now, quiet) {
    if (!Number.isFinite(due)) {
      return { ok: false, code: "invalid", error: "Choose a date and time" };
    }
    if (due < now + MIN_AHEAD_MS) {
      return { ok: false, code: "past", error: "Choose a time at least 2 minutes from now" };
    }
    if (due > now + MAX_AHEAD_MS) {
      return { ok: false, code: "far", error: "Choose a time within the next 30 days" };
    }
    // Quiet hours warn and never refuse: the person may want exactly that time.
    if (inQuiet(due, quiet)) {
      return {
        ok: true,
        warning: `That is inside your quiet hours (${quietWords(quiet)}). If the computer is asleep then, it will not be posted late at night, it will be marked missed.`,
      };
    }
    return { ok: true };
  }

  // Where a post wanting `due` may sit: another pending post within 90 s pushes it to
  // 90 s after that one, and so on down the line until a gap is found. One pass over
  // the others in order is enough, because the time only ever moves later.
  function spaced(items, due, selfId) {
    const others = sorted(pending(items).filter((item) => item.id !== selfId));
    let at = due;
    let after = null;
    for (const other of others) {
      if (Math.abs(at - other.due) < SPACING_MS) {
        at = other.due + SPACING_MS;
        after = other.id;
      }
    }
    return { due: at, after };
  }

  // After the last pending post, by the gap setting; the Add to queue button. Never
  // earlier than the minimum lead, so a small gap or a last post that has already
  // passed still gives a time that can be saved.
  function afterLast(items, now, gapMs, quiet) {
    const live = pending(items);
    const last = live.reduce((latest, item) => Math.max(latest, item.due), now);
    let due = Math.max(last + gapMs, now + MIN_AHEAD_MS);
    if (inQuiet(due, quiet)) due = quietEnds(due, quiet);
    return spaced(items, due, null).due;
  }

  function movedNote(due, after, items, now) {
    const other = find(items, after);
    const when = sameDay(due, now) ? clock(due, true) : dayAndClock(due, now, true);
    const them = other ? clock(other.due, true) : "";
    return `Moved to ${when}, 90 s after the clip at ${them}`;
  }

  // -- putting things in and moving them ------------------------------------------

  // A new schedule. Refused when the time is not allowed; otherwise saved at the time
  // asked for, or 90 s after whatever was in the way, and `note` says so.
  function insert(items, item, now, quiet) {
    const check = checkDue(item.due, now, quiet);
    if (!check.ok) return { error: check.error, code: check.code };
    const at = spaced(items, item.due, item.id);
    if (at.due > now + MAX_AHEAD_MS) {
      return { error: "That would put it more than 30 days away. Choose an earlier time", code: "far" };
    }
    const made = { ...item, due: at.due };
    const out = { items: sorted(items.concat([made])), item: made, note: null };
    if (at.after) out.note = movedNote(at.due, at.after, items, now);
    if (check.warning) out.warning = check.warning;
    return out;
  }

  function editable(item) {
    return !!item && item.state !== "running" && item.state !== "prepared" && !TERMINAL.includes(item.state);
  }

  // A missed or failed row given a new time starts again from the top.
  function rearmed(item) {
    if (!REARM.includes(item.state)) return {};
    return {
      state: item.custody === "fetching" ? "holding" : "scheduled",
      rung: null, error: null, outcome: null, attempts: 0, waitUntil: null,
    };
  }

  // The new time is the only thing that moves a post (FR-5), so this is the one way to
  // reorder. The row keeps its id, and so its place in the person's mind, and the list
  // comes back sorted.
  function retime(items, id, due, now, quiet) {
    const item = find(items, id);
    if (!item) return { error: "That post is no longer in the queue", code: "gone" };
    if (!editable(item)) return { error: lockedMessage(item), code: "locked" };
    const check = checkDue(due, now, quiet);
    if (!check.ok) return { error: check.error, code: check.code };
    const at = spaced(items, due, id);
    if (at.due > now + MAX_AHEAD_MS) {
      return { error: "That would put it more than 30 days away. Choose an earlier time", code: "far" };
    }
    const fields = { due: at.due, ...rearmed(item) };
    const changed = at.due !== item.due || fields.state !== undefined;
    const made = changed ? bumped(item, fields) : item;
    const out = {
      items: replaceIn(items, [made]),
      item: made,
      note: at.after ? movedNote(at.due, at.after, items, now) : `Moved to ${dayAndClock(at.due, now, true)}`,
    };
    if (check.warning) out.warning = check.warning;
    return out;
  }

  function lockedMessage(item) {
    if (item.state === "running") return "It is being put in WhatsApp now, so it cannot be changed";
    if (item.state === "prepared") return "It is already in WhatsApp, so it cannot be changed here";
    return "That post is finished, so it cannot be changed";
  }

  // The caption is the only thing edited in place besides the time.
  function edit(items, id, changes) {
    const item = find(items, id);
    if (!item) return { error: "That post is no longer in the queue", code: "gone" };
    if (!editable(item)) return { error: lockedMessage(item), code: "locked" };
    if (!changes || typeof changes.caption !== "string") {
      return { error: "Nothing to change", code: "invalid" };
    }
    const caption = changes.caption.trim();
    if (caption.length > COMMENT_MAX) {
      return { error: `A caption can be at most ${COMMENT_MAX} characters, this one is ${caption.length}. Shorten it`, code: "long" };
    }
    const made = caption === item.caption ? item : bumped(item, { caption });
    return { items: replaceIn(items, [made]), item: made };
  }

  // Cancelling is a state with a deadline, so Undo has ten seconds and nothing is
  // deleted before the deadline passes (FR-4, E11).
  function cancel(items, id, now) {
    const item = find(items, id);
    if (!item) return { error: "That post is no longer in the queue", code: "gone" };
    if (!editable(item)) return { error: lockedMessage(item), code: "locked" };
    const undo = snapshot(items, [id]);
    const made = bumped(item, { state: "cancelled", waitUntil: null, deleteAfter: now + UNDO_MS, endedAt: now });
    return { items: replaceIn(items, [made]), item: made, undo };
  }

  // -- many at once (Release 3 uses these; written and tested now) ----------------

  // Places each move in order of its new time against everything that is not moving and
  // against what has already been placed, so the result is spaced however the moves
  // overlap. A move that cannot be honoured stays where it was and is reported.
  function place(items, moves, now, quiet, validate) {
    const ids = new Set(moves.map((m) => m.id));
    const base = items.filter((item) => !ids.has(item.id));
    const skipped = [];
    const warnings = [];
    const wanted = [];
    for (const move of moves) {
      const item = find(items, move.id);
      if (!item) { skipped.push({ id: move.id, code: "gone", error: "That post is no longer in the queue" }); continue; }
      if (!editable(item)) { skipped.push({ id: move.id, code: "locked", error: lockedMessage(item) }); base.push(item); continue; }
      if (validate) {
        const check = checkDue(move.due, now, quiet);
        if (!check.ok) { skipped.push({ id: move.id, code: check.code, error: check.error }); base.push(item); continue; }
        if (check.warning) warnings.push({ id: move.id, warning: check.warning });
      }
      wanted.push({ item, due: move.due });
    }
    wanted.sort((a, b) => a.due - b.due || byOrder(a.item, b.item));
    const placed = [];
    const moved = [];
    for (const want of wanted) {
      const at = spaced(base.concat(placed), want.due, want.item.id);
      if (validate && at.due > now + MAX_AHEAD_MS) {
        skipped.push({ id: want.item.id, code: "far", error: "That would put it more than 30 days away" });
        placed.push(want.item);
        continue;
      }
      const fields = { due: at.due, ...rearmed(want.item) };
      const changed = at.due !== want.item.due || fields.state !== undefined;
      placed.push(changed ? bumped(want.item, fields) : want.item);
      if (changed) moved.push({ id: want.item.id, from: want.item.due, to: at.due });
    }
    return { items: sorted(base.concat(placed)), moved, skipped, warnings };
  }

  function shift(items, ids, deltaMs, now, quiet) {
    const moves = ids.map((id) => {
      const item = find(items, id);
      return { id, due: item ? item.due + deltaMs : NaN };
    }).filter((move) => find(items, move.id));
    const out = place(items, moves, now, quiet, true);
    for (const id of ids) {
      if (!find(items, id)) out.skipped.push({ id, code: "gone", error: "That post is no longer in the queue" });
    }
    return out;
  }

  // Ticked rows, in the order they are in now, from `start` with a fixed gap (never
  // under the 90 s spacing).
  function spread(items, ids, start, gapMs, now, quiet) {
    const gap = Math.max(gapMs, SPACING_MS);
    const chosen = sorted(items.filter((item) => ids.includes(item.id)));
    const moves = chosen.map((item, i) => ({ id: item.id, due: start + i * gap }));
    const out = place(items, moves, now, quiet, true);
    for (const id of ids) {
      if (!find(items, id)) out.skipped.push({ id, code: "gone", error: "That post is no longer in the queue" });
    }
    return out;
  }

  // -- limits ---------------------------------------------------------------------

  function megabytes(bytes) {
    if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1).replace(/\.0$/, "")} GB`;
    if (bytes >= 1e6) return `${Math.round(bytes / 1e6)} MB`;
    return `${Math.max(1, Math.round(bytes / 1e3))} KB`;
  }

  // Both limits, with the message naming the one that bit and what makes room (FR-18).
  // Bytes are those of pending clips held on this computer, or being brought down.
  function checkLimits(items, size, limits) {
    const live = pending(items);
    if (limits && Number.isFinite(limits.pending) && live.length >= limits.pending) {
      return {
        ok: false, code: "limit",
        error: `You already have ${live.length} posts scheduled, the most allowed here is ${limits.pending}. Post or cancel one to make room`,
      };
    }
    if (limits && Number.isFinite(limits.budgetBytes)) {
      const used = live
        .filter((item) => item.custody === "local" || item.custody === "fetching")
        .reduce((sum, item) => sum + (item.size || 0), 0);
      if (used + (size || 0) > limits.budgetBytes) {
        return {
          ok: false, code: "budget",
          error: `This clip is ${megabytes(size || 0)} and ${megabytes(used)} of the ${megabytes(limits.budgetBytes)} kept on this computer is already used. Post or cancel a scheduled clip to free room`,
        };
      }
    }
    return { ok: true };
  }

  // -- a run that woke up late ------------------------------------------------------

  // Run, or give up on it (FR-9). Quiet hours stop a catch up, not an on time run: the
  // person was warned when they chose that time.
  function catchUp(item, now, quiet) {
    const late = now - item.due;
    const window = Number.isFinite(item.catchUp) ? item.catchUp : CATCH_UP_MS;
    if (late > window) return { decision: "missed", reason: "late" };
    if (late > QUIET_GRACE_MS && inQuiet(now, quiet)) return { decision: "missed", reason: "quiet" };
    return { decision: "run", reason: null };
  }

  // -- pause and resume (FR-8) --------------------------------------------------------

  // The rows that fell due while the queue was paused and have not run.
  function overdue(items, pausedAt, now) {
    return sorted(items.filter((item) => RUNNABLE.includes(item.state) && item.due <= now))
      .map((item) => item.id);
  }

  // Nothing is posted on resume without a choice. `quiet` is not applied: the person
  // is choosing for these rows with the time in front of them.
  function resume(items, choice, pausedAt, now, quiet) {
    const ids = overdue(items, pausedAt, now);
    if (choice === "post") {
      const moves = ids.map((id, i) => ({ id, due: now + i * SPACING_MS }));
      const out = place(items, moves, now, quiet, false);
      return { items: out.items, changed: ids };
    }
    if (choice === "later") {
      const delta = now - pausedAt;
      const moves = ids.map((id) => ({ id, due: Math.max(find(items, id).due + delta, now + MIN_AHEAD_MS) }));
      const out = place(items, moves, now, quiet, false);
      return { items: out.items, changed: ids };
    }
    if (choice === "missed") {
      const made = ids.map((id) => bumped(find(items, id), {
        state: "missed", rung: null, outcome: "missed", waitUntil: null,
        error: { message: "The queue was paused when this was due", code: "paused" },
      }));
      return { items: replaceIn(items, made), changed: ids };
    }
    return { error: "Choose what to do with the posts that fell due", code: "invalid" };
  }

  // -- when the worker next needs to wake ---------------------------------------------

  // The earliest thing that needs doing, for the single `next` alarm (E1). Paused stops
  // the run itself but not the prewarm (FR-8), and a stored wait is a wait for a run, so
  // it stops too: otherwise the worker would wake at once, find nothing allowed, and be
  // told to wake at once again.
  function nextWake(items, now, paused) {
    let at = null;
    const take = (ts) => { if (Number.isFinite(ts) && (at === null || ts < at)) at = ts; };
    for (const item of items) {
      if (item.state === "scheduled") take(item.due - PREWARM_MS);
      if (!paused && (item.state === "scheduled" || item.state === "prewarmed")) take(item.due - LEAD_MS);
      if (!paused && PENDING.includes(item.state)) take(item.waitUntil);
      if (item.deleteAfter) take(item.deleteAfter);
    }
    return at === null ? null : Math.max(at, now);
  }

  // -- Undo -----------------------------------------------------------------------------

  const SNAP_FIELDS = ["due", "caption", "action", "state", "rung", "error", "outcome", "attempts",
    "waitUntil", "deleteAfter", "endedAt"];

  // What an operation is about to change, for the 10 second Undo (FR-4): everything a
  // retime, caption edit, cancel, shift, spread or resume can touch, copied so later
  // changes to the live rows do not leak into it.
  function snapshot(items, ids) {
    const rows = [];
    for (const id of ids) {
      const item = find(items, id);
      if (!item) continue;
      const row = { id };
      for (const key of SNAP_FIELDS) row[key] = item[key] === undefined ? null : JSON.parse(JSON.stringify(item[key]));
      rows.push(row);
    }
    return { items: rows };
  }

  // Puts those fields back. A row that has since started running, or finished, is left
  // alone (a send cannot be undone, and neither can a load in flight), and a row that
  // is gone is not brought back. `rev` goes forward, never back, so a page holding the
  // old one is still told it is stale.
  function restore(items, snap) {
    const changed = [];
    const restored = [];
    const skipped = [];
    for (const row of (snap && snap.items) || []) {
      const item = find(items, row.id);
      if (!item) { skipped.push(row.id); continue; }
      if (item.state === "running" || item.state === "prepared" || item.state === "done") {
        skipped.push(row.id);
        continue;
      }
      const fields = {};
      for (const key of SNAP_FIELDS) fields[key] = row[key];
      // A clip that finished coming down inside the Undo window is kept now: putting
      // the row back to holding would leave nothing to move it on, and it would fail
      // at its due time.
      if (fields.state === "holding" && item.custody === "local") fields.state = "scheduled";
      changed.push(bumped(item, fields));
      restored.push(row.id);
    }
    return { items: replaceIn(items, changed), restored, skipped };
  }

  // -- the words (U1, U2, U8) -------------------------------------------------------------

  // One plain word per state, its tone, its one action, and whether it needs the person.
  // The page and the toolbar badge count `needsYou`; the table shows `word` and `action`.
  // `detail` is a muted second line when the row holds a reason.
  function statusOf(item, paused) {
    const state = item.state;
    const detail = item.error && item.error.message ? item.error.message : null;
    const out = (word, tone, action, needsYou) => ({ word, tone, action, needsYou, detail });
    if (paused && RUNNABLE.includes(state)) return out("Paused", "wait", null, false);
    switch (state) {
      case "planned": return out("Not made yet", "wait", null, false);
      case "making": return out("Making the clip", "wait", null, false);
      case "unmade": return out("Could not make", "bad", "retry", true);
      case "holding": return out("Keeping the clip", "wait", null, false);
      case "scheduled": return out("Scheduled", "ok", "post-now", false);
      case "prewarmed": return out("Ready", "ok", "post-now", false);
      case "waiting": return out("Waiting for you to finish in WhatsApp", "wait", "post-now", false);
      case "running": return out("Putting it in WhatsApp", "wait", null, false);
      case "sending": return out("Sending", "wait", null, false);
      case "asked": return out("Ready, post it now", "warn", "post-now", true);
      // Release 1 only prepares, so a prepared clip waits on the person's Send, and its
      // open composer holds up the next run: it needs them (T2).
      case "prepared": return out("In WhatsApp, press Send", "warn", null, true);
      case "sent": return out("Sent", "ok", null, false);
      case "unconfirmed": return out("Check WhatsApp", "warn", "look", true);
      case "failed": return out("Could not put it in WhatsApp", "bad", "retry", true);
      case "missed": return out("Missed", "warn", "post-now", true);
      case "cancelled": return out("Cancelled", "muted", null, false);
      case "done": return out("Done", "muted", null, false);
      default: return out(String(state || "Unknown"), "muted", null, false);
    }
  }

  const api = {
    SPACING_MS, MIN_AHEAD_MS, MAX_AHEAD_MS, CATCH_UP_MS, LEAD_MS, PREWARM_MS, UNDO_MS,
    QUIET_GRACE_MS, PENDING, TERMINAL,
    sorted, pending, inQuiet, quietEnds, checkDue, spaced, afterLast, insert, retime, edit,
    editable, cancel, shift, spread, checkLimits, catchUp, overdue, resume, nextWake,
    snapshot, restore, statusOf, describe,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SnipQueue = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
