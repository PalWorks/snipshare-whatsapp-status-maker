// Scheduled Statuses in the worker: the stored queue, its alarms, and what happens at
// each one. docs/scheduling.md, Release 1 (Section 14 overrides the earlier sections):
// From the editor only, every clip kept on this computer (custody.js), and a run only
// ever prepares: the clip is put in WhatsApp's composer and the person presses Send.
// Nothing here presses Send, or asks anything else to (AGENTS.md, D-084).
//
// Chrome stops this worker whenever it likes, so every transition is written to
// `chrome.storage.local` before anything acts on it and every wake starts from what is
// stored (Section 5, Resilience). Every change to the queue runs through one promise
// chain (E8) and names the revision it was made against (FR-17). One `sched-next`
// alarm stands for the nearest thing to do and one `sched-sweep` every 15 minutes
// mops up; both are rebuilt on every wake, because Chrome can drop alarms (E1, FR-9).
//
// The rules (order, spacing, limits, catch up, words) are queue.js's; placing a clip in
// WhatsApp is place.js's. Everything Chrome gives comes in through `deps`, so the Node
// tests drive a fake clock, a fake store and fakes of both.
(function (root) {
  "use strict";

  const SWEEP_MINUTES = 15;              // FR-9
  const WAIT_STEP_MS = 60000;            // FR-12: look again a minute later
  const WAIT_TRIES = 10;                 // FR-12: then ask, after ten minutes
  const PREPARED_HOLD_MS = 24 * 3600000; // a composer nobody closed is let go after a day
  const TAB_HOLD_MS = 6 * 3600000;       // WhatsApp's tab is kept from discarding this long at most
  const ASKED_HOLD_MS = 24 * 3600000;    // Table SC-8: asked becomes missed after 24 hours
  const HISTORY_MS = 30 * 86400000;      // FR-15
  const LOG_KEEP = 200;                  // E15
  const MIN_ALARM_MS = 30000;            // Chrome fires an alarm no sooner than 30 s ahead
  const GRANT_LIFE_MS = 2 * 3600000;     // a clip grant never outlives 2 hours (D-101)
  const CAPTION_MAX = 1024;
  const SAFE_STEM = /^[A-Za-z0-9_-]{1,120}$/;  // serve.SAFE_STEM
  const SCHEDULING = ["bringForward", "idleForward", "quietOn", "quietStart", "quietEnd",
    "gapMinutes", "perPostNotices"];
  const DEFAULTS = {
    bringForward: false, idleForward: false, quietOn: true, quietStart: "23:00",
    quietEnd: "07:00", gapMinutes: 180, perPostNotices: false,
  };
  // What the server allows when the page has never said (Contract, Server).
  const LIMIT_DEFAULTS = { pending: 30, budgetBytes: 400000000 };
  // Codes from place.js that mean "not now", not "cannot" (FR-12).
  const WAIT_CODES = ["busy", "in-use", "composer-open"];
  // A row a run may start from.
  const RUN_FROM = ["scheduled", "prewarmed", "waiting", "asked", "missed", "failed"];

  class Refusal extends Error {
    constructor(message, code) { super(message); this.code = code; }
  }

  function chromeDeps() {
    const c = root.chrome;
    return {
      storage: c && c.storage && c.storage.local,
      session: c && c.storage && c.storage.session,
      alarms: c && c.alarms,
      notifications: c && c.notifications,
      queue: root.SnipQueue,
      place: root.SnipPlace,
      now: () => Date.now(),
      random: () => Math.random(),
      defer: (fn) => setTimeout(fn, 0),
      paced: async () => {},
      badge: () => {},
      openQueue: async () => {},
      showWhatsApp: async () => {},
      iconUrl: "icons/icon128.png",
    };
  }

  function clock(ts) {
    return new Date(ts).toLocaleTimeString("en", { hour: "numeric", minute: "2-digit" });
  }

  function clone(value) { return JSON.parse(JSON.stringify(value)); }

  function make(given) {
    const deps = { ...chromeDeps(), ...(given || {}) };
    const Q = deps.queue;
    const place = deps.place;
    const custody = deps.custody;

    let chain = Promise.resolve();
    const ports = new Set();
    const fetching = new Map();   // id -> AbortController, for fetches in this worker
    let runningId = null;         // the run this worker is carrying out, if any
    let current = null;           // its promise, for the tests and for a second ask
    let ticking = null;
    let tickAgain = false;

    // -- the store --------------------------------------------------------------------

    function normal(sched) {
      const s = sched && typeof sched === "object" ? sched : {};
      return { items: Array.isArray(s.items) ? s.items : [], paused: s.paused || null, seq: s.seq || 0 };
    }

    async function load() {
      return normal((await deps.storage.get("sched")).sched);
    }

    async function settings() {
      const stored = (await deps.storage.get("settings")).settings || {};
      return stored;
    }

    async function schedSettings() {
      const stored = await settings();
      const out = { ...DEFAULTS };
      for (const key of SCHEDULING) if (stored[key] !== undefined) out[key] = stored[key];
      return out;
    }

    function quietOf(s) {
      return { on: !!s.quietOn, start: s.quietStart, end: s.quietEnd };
    }

    async function limits() {
      const stored = (await deps.storage.get("schedLimits")).schedLimits || {};
      return {
        pending: Number.isFinite(stored.pending) ? stored.pending : LIMIT_DEFAULTS.pending,
        budgetBytes: Number.isFinite(stored.budgetBytes) ? stored.budgetBytes : LIMIT_DEFAULTS.budgetBytes,
      };
    }

    // queue.js bumps `rev` on what it changes; a change made here bumps it the same
    // way, once, so a page holding the old revision is refused (FR-17).
    function bumpChanged(before, after) {
      const old = new Map(before.map((item) => [item.id, item]));
      for (const item of after) {
        const was = old.get(item.id);
        if (!was) { if (!item.rev) item.rev = 1; continue; }
        if (item.rev !== was.rev) continue;
        const a = { ...item, rev: 0 };
        const b = { ...was, rev: 0 };
        if (JSON.stringify(a) !== JSON.stringify(b)) item.rev = (was.rev || 0) + 1;
      }
    }

    // One change at a time, read and written whole, so two pages and the alarms can
    // never write over each other (E8). `work` changes `sched` in place, or replaces
    // `sched.items`, and returns what the caller needs.
    function mutate(work) {
      const turn = chain.then(async () => {
        const sched = await load();
        const before = clone(sched);
        const out = await work(sched);
        if (JSON.stringify(sched) !== JSON.stringify(before)) {
          bumpChanged(before.items, sched.items);
          await deps.storage.set({ sched });
          return { out, changed: true };
        }
        return { out, changed: false };
      });
      chain = turn.catch(() => {});
      return turn.then(async ({ out, changed }) => {
        if (changed) await settled();
        return out;
      });
    }

    function find(sched, id) {
      return sched.items.find((item) => item.id === id) || null;
    }

    function current_(sched, sid, rev) {
      const item = find(sched, sid);
      if (!item) throw new Refusal("That post is no longer in the queue.", "gone");
      if (rev !== undefined && rev !== null && rev !== item.rev) {
        throw new Refusal("This post was changed somewhere else first. Here is the queue as it is now.", "conflict");
      }
      return item;
    }

    function patch(sched, id, fields) {
      sched.items = sched.items.map((item) => (item.id === id ? { ...item, ...fields } : item));
      return find(sched, id);
    }

    // -- history and the run log ---------------------------------------------------------

    async function addHistory(rows) {
      if (!rows.length) return;
      const now = deps.now();
      const stored = (await deps.storage.get("schedHistory")).schedHistory || [];
      const kept = stored.concat(rows).filter((row) => now - (row.endedAt || now) <= HISTORY_MS);
      await deps.storage.set({ schedHistory: kept });
    }

    async function history() {
      const now = deps.now();
      const stored = (await deps.storage.get("schedHistory")).schedHistory || [];
      return stored.filter((row) => now - (row.endedAt || now) <= HISTORY_MS)
        .sort((a, b) => (b.endedAt || 0) - (a.endedAt || 0));
    }

    // Codes and timings only, never the caption or the video (E15).
    async function logRun(entry) {
      try {
        const stored = (await deps.storage.get("schedLog")).schedLog || [];
        stored.push(entry);
        await deps.storage.set({ schedLog: stored.slice(-LOG_KEEP) });
      } catch { /* a lost record must never cost a run */ }
    }

    // Takes finished rows out of the queue into history and lets their clips go.
    // Called inside the chain.
    async function retire(sched, ids) {
      const now = deps.now();
      const going = sched.items.filter((item) => ids.includes(item.id));
      if (!going.length) return;
      sched.items = sched.items.filter((item) => !ids.includes(item.id));
      await addHistory(going.map((item) => ({
        id: item.id, stem: item.stem, name: item.name, caption: item.caption, mode: item.mode,
        due: item.due, created: item.created, state: item.state, outcome: item.outcome || item.state,
        rung: item.rung || null, error: item.error || null, endedAt: item.endedAt || now,
      })));
      for (const item of going) {
        const controller = fetching.get(item.id);
        if (controller) controller.abort();
        try { await custody.drop(item.id); } catch { /* the sweep takes it later */ }
        try { if (deps.session) await deps.session.remove(`grant:${item.id}`); } catch { /* gone */ }
      }
    }

    // -- alarms, badge, and telling the open pages ------------------------------------------

    // One `sched-next` at the nearest thing to do and a sweep while anything is
    // pending, rebuilt from the store every time (E1).
    async function reconcile(sched) {
      const s = sched || await load();
      const now = deps.now();
      const wake = Q.nextWake(s.items, now, !!s.paused);
      try {
        if (wake === null) await deps.alarms.clear("sched-next");
        else await deps.alarms.create("sched-next", { when: Math.max(wake, now + MIN_ALARM_MS) });
        const live = Q.pending(s.items).length > 0;
        const sweep = await deps.alarms.get("sched-sweep");
        if (live && !sweep) await deps.alarms.create("sched-sweep", { periodInMinutes: SWEEP_MINUTES });
        if (!live && sweep) await deps.alarms.clear("sched-sweep");
      } catch { /* the next wake rebuilds them */ }
      return wake;
    }

    function needsYou(sched) {
      return sched.items.filter((item) => Q.statusOf(item, !!sched.paused).needsYou).length;
    }

    async function state() {
      const sched = await load();
      const now = deps.now();
      const lim = await limits();
      let quiet = { works: null, best: null, tested: null };
      try {
        const stats = await place.stats();
        if (stats) quiet = { works: stats.works ?? null, best: stats.best ?? null, tested: stats.tested ?? null };
      } catch { /* not known yet */ }
      const live = Q.pending(sched.items);
      const bytes = live.reduce((sum, item) => sum + (item.custody === "local" ? (item.size || 0)
        : item.custody === "fetching" ? (item.fetched || 0) : 0), 0);
      return {
        items: Q.sorted(sched.items),
        paused: sched.paused,
        overdue: sched.paused ? Q.overdue(sched.items, sched.paused.at, now) : [],
        history: await history(),
        usage: { bytes, budgetBytes: lim.budgetBytes, pending: live.length, pendingLimit: lim.pending },
        settings: await schedSettings(),
        quiet,
        needsYou: needsYou(sched),
        now,
      };
    }

    async function push() {
      if (!ports.size) return;
      let snapshot;
      try { snapshot = await state(); } catch { return; }
      for (const port of ports) {
        try { port.postMessage({ event: "queue", state: snapshot }); } catch { ports.delete(port); }
      }
    }

    // Work that reads the queue and acts on it outside a change, run in the same chain
    // as the changes so it always sees the newest queue: a reconcile that read an older
    // one must never clear a newer `sched-next`.
    function serial(work) {
      const turn = chain.then(work);
      chain = turn.catch(() => {});
      return turn;
    }

    // After every change: the alarms, the badge and the open pages.
    async function settled() {
      const sched = await serial(async () => {
        const fresh = await load();
        await reconcile(fresh);
        return fresh;
      });
      try { deps.badge(needsYou(sched)); } catch { /* cosmetic */ }
      await push();
    }

    // -- notifications (T2: only what needs the person) ------------------------------------

    async function notify(kind, item, title, message, buttons) {
      try {
        await deps.notifications.create(`sched|${kind}|${item ? item.id : "all"}`, {
          type: "basic", iconUrl: deps.iconUrl, title, message, priority: 1,
          ...(buttons ? { buttons: buttons.map((b) => ({ title: b })) } : {}),
        });
      } catch { /* a lost notice must never cost a run */ }
    }

    function tell(kind, item) {
      const at = clock(item.due);
      if (kind === "asked") {
        return notify("asked", item, `Your ${at} Status is ready`,
          "Post it now: WhatsApp opens with it in place for you to send.", ["Post it now"]);
      }
      if (kind === "missed") {
        return notify("missed", item, `Your ${at} Status was missed`,
          (item.error && item.error.message) || "Chrome was closed or the computer was asleep at that time.",
          ["Post it now"]);
      }
      if (kind === "failed") {
        return notify("failed", item, `Your ${at} Status could not be put in WhatsApp`,
          (item.error && item.error.message) || "Open the queue to try again.");
      }
      if (kind === "signed-out") {
        return notify("signed-out", item, "WhatsApp Web is signed out",
          `Scan the code in WhatsApp Web before ${at}, or your Status cannot go in.`, ["Show WhatsApp"]);
      }
      if (kind === "damaged") {
        return notify("damaged", item, `Your ${at} Status cannot go out`,
          "The scheduled clip is damaged. Schedule it again from SnipShare.");
      }
      if (kind === "prepared") {
        return notify("prepared", item, `Your ${at} Status is in WhatsApp. Press Send there`,
          "It is waiting in the Status composer for you.", ["Show WhatsApp"]);
      }
      return null;
    }

    // One summary a day of what was put in WhatsApp (T2), rather than one per post.
    async function countPrepared() {
      const today = new Date(deps.now()).toDateString();
      const stored = (await deps.storage.get("schedSummary")).schedSummary || { day: today, count: 0 };
      if (stored.day !== today) await summarise(stored, today);
      const fresh = (await deps.storage.get("schedSummary")).schedSummary || { day: today, count: 0 };
      await deps.storage.set({ schedSummary: { day: today, count: (fresh.day === today ? fresh.count : 0) + 1 } });
    }

    async function summarise(stored, today) {
      if (stored && stored.count > 0) {
        await notify("summary", null, "Scheduled Statuses",
          `${stored.count} Status${stored.count === 1 ? " was" : "es were"} put in WhatsApp for you on ${stored.day}.`);
      }
      await deps.storage.set({ schedSummary: { day: today, count: 0 } });
    }

    async function summaryDue() {
      const today = new Date(deps.now()).toDateString();
      const stored = (await deps.storage.get("schedSummary")).schedSummary;
      if (stored && stored.day !== today) await summarise(stored, today);
    }

    // -- creating: the `schedule` command from the SnipShare page --------------------------

    function newId() {
      const letters = "abcdefghijklmnopqrstuvwxyz0123456789";
      let out = "s_";
      for (let i = 0; i < 10; i++) out += letters[Math.floor(deps.random() * letters.length)];
      return out;
    }

    function cleanLimits(given) {
      if (!given || typeof given !== "object") return null;
      const pending = Number(given.pending);
      const budgetBytes = Number(given.budgetBytes);
      const out = {};
      if (Number.isInteger(pending) && pending >= 0) out.pending = pending;
      if (Number.isFinite(budgetBytes) && budgetBytes >= 0) out.budgetBytes = budgetBytes;
      return Object.keys(out).length ? out : null;
    }

    // Saves the schedule, brings the clip down, and answers once it is kept and its hash
    // recorded. A page that asks again for the same clip while the first is still
    // coming down (its port closed when a worker stopped) carries on with that one.
    async function create(message, { grant, url, signal, onProgress }) {
      const stem = String(message.stem || "");
      if (!SAFE_STEM.test(stem)) throw new Refusal("That clip is not valid.", "invalid");
      if (!["card", "video"].includes(message.mode)) throw new Refusal("That clip is not valid.", "invalid");
      if (message.action !== undefined && message.action !== "prepare") {
        // Release 1 prepares only; sending is not built (AGENTS.md, D-084).
        throw new Refusal("This version can only put a clip in WhatsApp for you to send.", "invalid");
      }
      const caption = String(message.caption || "").trim();
      if (caption.length > CAPTION_MAX) throw new Refusal("That caption is too long for WhatsApp.", "invalid");
      const name = String(message.name || `${stem}.mp4`).replace(/[^A-Za-z0-9 ._-]+/g, "").slice(0, 120) || "status.mp4";
      const told = cleanLimits(message.limits);
      if (told) await deps.storage.set({ schedLimits: { ...(await limits()), ...told } });
      const lim = await limits();
      const s = await schedSettings();
      const quiet = quietOf(s);
      const now = deps.now();

      const made = await mutate(async (sched) => {
        // The page asking again for the same clip at the same time carries on with the
        // first; the same clip for another time waits until the first is kept.
        const asked = message.afterLast ? "afterLast" : Number(message.due);
        const existing = sched.items.find((item) => item.stem === stem && item.state === "holding");
        if (existing && existing.asked === asked) {
          return { item: patch(sched, existing.id, { error: null }), note: null, resumed: true };
        }
        if (existing) {
          throw new Refusal("This clip is still being kept for another time. Wait for it to finish, "
            + "then schedule it again.", "busy");
        }
        const check = Q.checkLimits(sched.items, 0, lim);
        if (!check.ok) throw new Refusal(check.error, check.code);
        const due = message.afterLast ? Q.afterLast(sched.items, now, (Number(s.gapMinutes) || 180) * 60000, quiet)
          : Number(message.due);
        const item = {
          id: newId(), rev: 1, created: now, due, zone: timeZone(),
          stem, name, caption, mode: message.mode,
          size: 0, sha256: null, custody: "fetching", fetched: 0,
          action: "prepare", catchUp: Q.CATCH_UP_MS,
          state: "holding", rung: null, attempts: 0, error: null, outcome: null,
          origin: "editor", looked: true, repeat: null,
          waitUntil: null, deleteAfter: null, ranAt: null, endedAt: null, checked: null,
          asked, given: false,
        };
        const placed = Q.insert(sched.items, item, now, quiet);
        if (placed.error) throw new Refusal(placed.error, placed.code);
        sched.items = placed.items;
        sched.seq = (sched.seq || 0) + 1;
        return { item: placed.item, note: placed.note || null, warning: placed.warning || null };
      });

      const id = made.item.id;
      try {
        if (deps.session) await deps.session.set({ [`grant:${id}`]: { grant, url, at: now } });
      } catch { /* resuming after a stop needs it, a first run does not */ }
      const kept = await keep(id, { grant, url, signal, onProgress, fromPage: true });
      return { schedule: kept, note: made.note, warning: made.warning || null };
    }

    function timeZone() {
      try { return Intl.DateTimeFormat().resolvedOptions().timeZone || null; } catch { return null; }
    }

    // Brings one clip down into custody and moves its row from holding to scheduled.
    async function keep(id, { grant, url, signal, onProgress, fromPage }) {
      const earlier = fetching.get(id);
      if (earlier) earlier.abort();
      const controller = new AbortController();
      fetching.set(id, controller);
      const both = signal ? AbortSignal.any([signal, controller.signal]) : controller.signal;
      const lim = await limits();
      const sched = await load();
      const item = find(sched, id);
      let lastStored = 0;
      try {
        const result = await custody.fetch(id, {
          url, grant, size: item && item.size ? item.size : null, signal: both,
          admit: (size) => mutate(async (s) => {
            const row = find(s, id);
            if (!row) throw new Refusal("That post is no longer in the queue.", "gone");
            const check = Q.checkLimits(s.items.filter((other) => other.id !== id), size, lim);
            if (!check.ok) throw new Refusal(check.error, check.code);
            patch(s, id, { size });
          }),
          onProgress: ({ have, size, stored }) => {
            if (onProgress) onProgress(size ? have / size : 0);
            if (stored && have !== lastStored) {
              lastStored = have;
              mutate(async (s) => { if (find(s, id)) patch(s, id, { fetched: have }); }).catch(() => {});
            }
          },
        });
        const done = await mutate(async (s) => {
          const row = find(s, id);
          if (!row) throw new Refusal("That post was cancelled while its clip came down.", "gone");
          return patch(s, id, {
            custody: "local", fetched: result.size, size: result.size, sha256: result.sha256,
            state: row.state === "holding" ? "scheduled" : row.state, error: null,
          });
        });
        try { if (deps.session) await deps.session.remove(`grant:${id}`); } catch { /* gone */ }
        return done;
      } catch (err) {
        const code = err && typeof err.code === "string" ? err.code : "network";
        const message = String(err && err.message || err);
        if (controller.signal.aborted && !(signal && signal.aborted)) {
          // Replaced by a newer fetch of the same clip, or the row was retired: the
          // other path owns the row now.
          throw new Refusal(message, "stopped");
        }
        if (code === "network" || (code === "stopped" && !fromPage)) {
          // Kept for a second try: the page asking again carries on from the parts.
          await mutate(async (s) => {
            if (find(s, id)) patch(s, id, { error: { message, code } });
          }).catch(() => {});
        } else {
          // Refused, or the page went away while it came down: never saved (Table SC-8,
          // holding is "removed with the error on the page").
          await mutate(async (s) => {
            s.items = s.items.filter((row) => row.id !== id);
          }).catch(() => {});
          try { await custody.drop(id); } catch { /* the sweep takes it */ }
          try { if (deps.session) await deps.session.remove(`grant:${id}`); } catch { /* gone */ }
        }
        throw new Refusal(message, code === "stopped" ? "stopped" : code);
      } finally {
        if (fetching.get(id) === controller) fetching.delete(id);
      }
    }

    // A holding row whose fetch was cut by a worker stop carries on in the background,
    // while its grant can still be used.
    async function resumeHolding(item) {
      let saved = null;
      try { saved = deps.session ? (await deps.session.get(`grant:${item.id}`))[`grant:${item.id}`] : null; } catch { saved = null; }
      if (!saved || deps.now() - saved.at > GRANT_LIFE_MS) return false;
      keep(item.id, { grant: saved.grant, url: saved.url, fromPage: false }).catch(() => {});
      return true;
    }

    // -- the run ----------------------------------------------------------------------------

    function lateBy(item, now) { return now - item.due; }

    async function allSettings() {
      return { ...DEFAULTS, ...(await settings()) };
    }

    // Moves a row to running and carries the run out. `manual` is a person pressing
    // Post now or a notification: WhatsApp comes forward, as Load does today (FR-7).
    // Resolves once the row is running (or with the refusal); the run itself goes on.
    async function start(id, manual) {
      if (runningId) throw new Refusal("Another post is being put in WhatsApp. Try again in a moment.", "busy");
      runningId = id;
      let claimed;
      try {
        const quiet = quietOf(await schedSettings());
        claimed = await mutate(async (sched) => {
          const item = find(sched, id);
          if (!item) throw new Refusal("That post is no longer in the queue.", "gone");
          if (!RUN_FROM.includes(item.state)) {
            throw new Refusal("That post cannot be put in WhatsApp from where it is.", "locked");
          }
          if (item.custody !== "local") {
            throw new Refusal("Its clip is still coming down. Try again in a moment.", "holding");
          }
          const now = deps.now();
          if (!manual) {
            // The wake chose this run before a prewarm that can take two minutes; a
            // Pause, a new time or a missed window since then wins over that choice.
            if (sched.paused) throw new Refusal("The queue is paused.", "paused");
            if (item.state === "waiting" ? (item.waitUntil && item.waitUntil > now)
              : now < item.due - Q.LEAD_MS) {
              throw new Refusal("It is not due yet.", "early");
            }
            if (Q.catchUp(item, now, quiet).decision !== "run") {
              throw new Refusal("It is past its catch up window.", "late");
            }
          }
          const before = item.state;
          const row = patch(sched, id, { state: "running", rung: null, ranAt: now, waitUntil: null,
                                         error: null, outcome: null, given: false });
          return { row, before };
        });
      } catch (err) {
        runningId = null;
        throw err;
      }
      current = perform(claimed.row, claimed.before, manual).finally(() => {
        runningId = null;
        current = null;
        kick();
      });
      return claimed.row;
    }

    async function perform(item, before, manual) {
      const startedAt = deps.now();
      let result;
      try {
        if (!manual) {
          // Never while the person is using WhatsApp, nor while another load is in
          // flight (FR-12); and never paced by the page's loads (E4).
          if (place.busy() || await place.inUse()) result = { ok: false, code: "in-use", rung: null };
          else {
            try { await deps.paced(); } catch { result = { ok: false, code: "busy", rung: null }; }
          }
        }
        if (!result && !item.checked) {
          if (!(await custody.verify(item.id, item.size, item.sha256))) {
            result = { ok: false, code: "damaged", error: "The scheduled clip is damaged. Schedule it again from SnipShare." };
          } else {
            await mutate(async (s) => { if (find(s, item.id)) patch(s, item.id, { checked: deps.now() }); });
          }
        }
        if (!result) {
          const clip = await custody.read(item.id);
          if (!clip) {
            result = { ok: false, code: "gone", error: "The scheduled clip is no longer on this computer. Schedule it again from SnipShare." };
          } else {
            result = await place.load({
              clip, name: item.name, caption: item.caption, manual: !!manual,
              settings: await allSettings(), signal: undefined,
              onStep: (step) => {
                const rung = step && step.rung;
                // Once the file is in WhatsApp's hands, a stopped worker must never
                // load it again: the person could send both (D-073's rule, no replay
                // after an uncertain side effect).
                const given = !!step && step.step === "file";
                if (rung || given) {
                  mutate(async (s) => {
                    const r = find(s, item.id);
                    if (r && r.state === "running") patch(s, item.id, { ...(rung ? { rung } : {}), ...(given ? { given: true } : {}) });
                  }).catch(() => {});
                }
              },
            });
          }
        }
      } catch (err) {
        result = { ok: false, code: "failed", error: String(err && err.message || err) };
      }
      result = result || { ok: false, code: "failed" };
      await finish(item, before, manual, result, startedAt);
    }

    async function finish(item, before, manual, result, startedAt) {
      const now = deps.now();
      const code = result.ok ? "ok" : String(result.code || "failed");
      let told = null;
      const row = await mutate(async (sched) => {
        const live = find(sched, item.id);
        if (!live) return null;
        if (result.ok) {
          told = "prepared";
          return patch(sched, item.id, { state: "prepared", rung: result.rung || null, outcome: "prepared",
                                         attempts: 0, error: null, endedAt: now });
        }
        if (code === "ask") {
          told = "asked";
          return patch(sched, item.id, { state: "asked", rung: result.rung || "S4", outcome: "asked",
                                         error: null, endedAt: now });
        }
        if (WAIT_CODES.includes(code)) {
          if (manual) {
            // The person pressed it and it cannot go in now: back where it was, saying why.
            return patch(sched, item.id, { state: before, error: { message: result.error || waitWords(code), code } });
          }
          const attempts = (live.attempts || 0) + 1;
          if (attempts >= WAIT_TRIES) {
            told = "asked";
            return patch(sched, item.id, { state: "asked", attempts, waitUntil: null, outcome: "asked",
                                           error: { message: waitWords(code), code }, endedAt: now });
          }
          return patch(sched, item.id, { state: "waiting", attempts, waitUntil: now + WAIT_STEP_MS,
                                         error: { message: waitWords(code), code } });
        }
        told = code === "signed-out" ? "signed-out" : code === "damaged" ? "damaged" : "failed";
        return patch(sched, item.id, {
          state: "failed", rung: result.rung || null, outcome: code, endedAt: now,
          error: { message: result.error || "WhatsApp did not open its editor.", code },
        });
      });
      await logRun({
        id: item.id, at: startedAt, due: item.due, late: startedAt - item.due,
        ms: Number.isFinite(result.ms) ? result.ms : now - startedAt, rung: result.rung || null,
        code, outcome: row ? row.state : code, manual: !!manual, focusMoved: !!result.focusMoved,
      });
      if (!row) return;
      const s = await schedSettings();
      if (told === "prepared") {
        await countPrepared().catch(() => {});
        // Always: in Release 1 a prepared clip waits on the person's Send, whatever
        // perPostNotices says (T2, decided 2026-10-31).
        await tell("prepared", row);
      } else if (told === "signed-out") {
        await tell("signed-out", row);
      } else if (told && !(manual && told === "failed")) {
        await tell(told, row);
      }
      // A prepared composer keeps its tab from being discarded until it closes; a run
      // that failed or asked has nothing in the tab worth keeping.
      if (told && told !== "prepared") await letGo();
      else await release();
    }

    function waitWords(code) {
      if (code === "busy") return "WhatsApp was opening another clip, so this one waits its turn.";
      if (code === "composer-open") return "A Status is open in WhatsApp, so this one waits until it is closed.";
      return "You were using WhatsApp, so this one waits until you are done.";
    }

    async function letGo() {
      try { await place.release(); } catch { /* nothing to let go */ }
    }

    // The tab is let go once nothing is about to need it (Section 6.3): no run warming
    // or under way, and no prepared composer younger than TAB_HOLD_MS.
    async function release() {
      const sched = await load();
      const now = deps.now();
      const holding = sched.items.some((item) => ["prewarmed", "running", "waiting"].includes(item.state)
        || (item.state === "prepared" && now - (item.endedAt || now) < TAB_HOLD_MS));
      if (!holding) await letGo();
    }

    // At due minus five minutes: the clip checks, and WhatsApp's tab is found, kept
    // from being discarded, and checked signed in (FR-10, E6).
    async function prewarm(item) {
      let ok = true;
      if (!item.checked) {
        try { ok = await custody.verify(item.id, item.size, item.sha256); } catch { ok = false; }
      }
      if (!ok) {
        const row = await mutate(async (sched) => {
          const live = find(sched, item.id);
          if (!live || live.state !== "scheduled") return null;
          return patch(sched, item.id, {
            state: "failed", outcome: "damaged", endedAt: deps.now(),
            error: { message: "The scheduled clip is damaged. Schedule it again from SnipShare.", code: "damaged" },
          });
        });
        if (row) await tell("damaged", row);
        await letGo();
        return;
      }
      let warm;
      try { warm = await place.prewarm(); } catch { warm = { ok: false, code: "failed" }; }
      const row = await mutate(async (sched) => {
        const live = find(sched, item.id);
        if (!live || live.state !== "scheduled") return null;
        return patch(sched, item.id, { state: "prewarmed", checked: live.checked || deps.now() });
      });
      if (row && warm && warm.code === "signed-out") await tell("signed-out", row);
      // A tab that could not be warmed is not worth holding; the run finds its own.
      if (!warm || !warm.ok) await letGo();
    }

    // -- the wake: whatever is due now ---------------------------------------------------------

    function kick() {
      try { deps.defer(() => { tick().catch(() => {}); }); } catch { /* the alarm will */ }
    }

    function tick() {
      if (ticking) { tickAgain = true; return ticking; }
      ticking = (async () => {
        do {
          tickAgain = false;
          await tickOnce();
        } while (tickAgain);
      })().finally(() => { ticking = null; });
      return ticking;
    }

    async function tickOnce(sweeping) {
      const s = await schedSettings();
      const quiet = quietOf(s);
      const missed = [];
      const given = [];
      const plan = await mutate(async (sched) => {
        const now = deps.now();
        const todo = { prewarm: [], run: null, resume: [], done: [] };
        const finished = [];
        for (const item of sched.items) {
          if (item.state === "cancelled" && item.deleteAfter && item.deleteAfter <= now) finished.push(item.id);
          else if (item.state === "done") finished.push(item.id);
          else if (item.state === "running" && runningId !== item.id && item.given) {
            // The worker stopped after the clip reached WhatsApp: it may be in the
            // composer now. Never loaded again; the person is told to look.
            given.push(patch(sched, item.id, {
              state: "prepared", outcome: "prepared", endedAt: now,
              error: { message: "Chrome stopped while this went in. Check WhatsApp before you send.", code: "given" },
            }));
          } else if (item.state === "running" && runningId !== item.id) {
            // The worker stopped during a run before the clip reached WhatsApp. Run it
            // again from the top: an open composer makes place.js refuse (Table SC-8).
            patch(sched, item.id, { state: "scheduled", rung: null, waitUntil: null });
          } else if (item.state === "holding" && !fetching.has(item.id)) {
            if (now - item.created > GRANT_LIFE_MS || now >= item.due) {
              patch(sched, item.id, {
                state: "failed", custody: "fetching", outcome: "network", endedAt: now,
                error: { message: "Could not bring the clip down from SnipShare. Schedule it again.", code: "network" },
              });
            } else if (!item.error) {
              todo.resume.push(item);
            }
          } else if (item.state === "prepared" && now - (item.endedAt || now) >= PREPARED_HOLD_MS) {
            patch(sched, item.id, { state: "done", outcome: "prepared" });
            finished.push(item.id);
          } else if (item.state === "asked" && now - (item.endedAt || now) >= ASKED_HOLD_MS) {
            const row = patch(sched, item.id, { state: "missed", outcome: "missed", endedAt: now,
              error: { message: "Nobody pressed Post it now within a day.", code: "late" } });
            missed.push(row);
          }
        }
        if (sweeping) todo.done = sched.items.filter((item) => item.state === "prepared").map((item) => item.id);
        await retire(sched, finished);

        for (const item of Q.sorted(sched.items)) {
          if (item.state === "scheduled" && now >= item.due - Q.PREWARM_MS) todo.prewarm.push(item);
        }
        if (sched.paused) return todo;
        for (const item of Q.sorted(sched.items)) {
          const due = (item.state === "scheduled" || item.state === "prewarmed") && now >= item.due - Q.LEAD_MS;
          const retry = item.state === "waiting" && item.waitUntil && item.waitUntil <= now;
          if (!due && !retry) continue;
          // FR-9: a run that woke late goes only inside the catch up window, never
          // late into quiet hours; several missed never run back to back unasked.
          const decision = Q.catchUp(item, now, quiet);
          if (decision.decision === "missed") {
            const row = patch(sched, item.id, {
              state: "missed", outcome: "missed", endedAt: now, waitUntil: null,
              error: { message: decision.reason === "quiet"
                ? "It fell due during your quiet hours while Chrome was closed or asleep."
                : `Chrome was closed or the computer was asleep at ${clock(item.due)}.`, code: decision.reason || "late" },
            });
            missed.push(row);
            continue;
          }
          if (!todo.run && !runningId) todo.run = item.id;
        }
        return todo;
      });
      for (const row of missed) await tell("missed", row);
      for (const row of given) await tell("prepared", row);
      for (const item of plan.prewarm) await prewarm(item);
      for (const item of plan.resume) await resumeHolding(item);
      if (plan.done.length) await closeFinished(plan.done);
      if (plan.run && !runningId) {
        try { await start(plan.run, false); } catch { /* changed meanwhile; the next wake looks again */ }
      }
    }

    // A prepared row is done once its composer has gone: the person sent it or closed
    // it. place.js cannot tell those apart, and it does not need to (Section 8.2).
    async function closeFinished(ids) {
      let busy = true;
      try { busy = place.busy() || await place.inUse(); } catch { busy = true; }
      if (busy) return;
      await mutate(async (sched) => {
        const now = deps.now();
        const going = [];
        for (const id of ids) {
          const item = find(sched, id);
          if (item && item.state === "prepared") {
            patch(sched, id, { state: "done", outcome: "prepared", endedAt: item.endedAt || now });
            going.push(id);
          }
        }
        await retire(sched, going);
      });
      await release();
    }

    async function sweep() {
      await tickOnce(true);
      if (!runningId) await release();
      await summaryDue().catch(() => {});
      try {
        const sched = await load();
        await custody.sweep(sched.items.map((item) => item.id));
      } catch { /* next sweep */ }
      await addHistory([]).catch(() => {});
    }

    // On install, browser start and every worker start: alarms rebuilt, and whatever
    // fell due while the worker was not running is looked at now.
    async function wake() {
      await tick();
      await settled();
    }

    async function alarm(name) {
      if (name === "sched-sweep") await sweep();
      else if (name === "sched-next") await tick();
      await settled();
    }

    // -- the queue page's commands -----------------------------------------------------------

    async function retime({ sid, rev, due }) {
      const s = await schedSettings();
      return mutate(async (sched) => {
        current_(sched, sid, rev);
        const out = Q.retime(sched.items, sid, Number(due), deps.now(), quietOf(s));
        if (out.error) throw new Refusal(out.error, out.code);
        const undo = Q.snapshot(sched.items, [sid]);
        sched.items = out.items;
        return { item: out.item, note: out.note || null, warning: out.warning || null, undo };
      });
    }

    async function caption({ sid, rev, caption: text }) {
      return mutate(async (sched) => {
        current_(sched, sid, rev);
        const out = Q.edit(sched.items, sid, { caption: String(text === undefined ? "" : text) });
        if (out.error) throw new Refusal(out.error, out.code);
        const undo = Q.snapshot(sched.items, [sid]);
        sched.items = out.items;
        return { item: out.item, undo };
      });
    }

    async function cancel({ sid, rev }) {
      return mutate(async (sched) => {
        current_(sched, sid, rev);
        const out = Q.cancel(sched.items, sid, deps.now());
        if (out.error) throw new Refusal(out.error, out.code);
        sched.items = out.items;
        return { item: out.item, undo: out.undo, note: "Cancelled" };
      });
    }

    async function restore({ snap }) {
      return mutate(async (sched) => {
        const ids = ((snap && snap.items) || []).map((row) => row.id);
        if (ids.some((id) => { const item = find(sched, id); return item && item.state === "running"; })) {
          throw new Refusal("It is being put in WhatsApp now, so it cannot be undone.", "locked");
        }
        const out = Q.restore(sched.items, snap);
        if (!out.restored.length) throw new Refusal("It is too late to undo that.", "gone");
        sched.items = out.items;
        if (snap.paused && Number.isFinite(snap.paused.at) && !sched.paused) sched.paused = { at: snap.paused.at };
        return { item: find(sched, out.restored[0]), restored: out.restored, skipped: out.skipped };
      });
    }

    async function postNow({ sid }) {
      const item = await start(sid, true);
      return { item, note: "Opening WhatsApp" };
    }

    async function postNextNow() {
      const sched = await load();
      const next = Q.sorted(sched.items).find((item) => ["scheduled", "prewarmed", "waiting"].includes(item.state)
        && item.custody === "local");
      if (!next) throw new Refusal("Nothing is waiting to go out.", "empty");
      return postNow({ sid: next.id });
    }

    async function pause() {
      return mutate(async (sched) => {
        if (!sched.paused) sched.paused = { at: deps.now() };
        return { note: "Queue paused. Nothing will be put in WhatsApp until you resume it." };
      });
    }

    async function resume({ choice }) {
      return mutate(async (sched) => {
        if (!sched.paused) return { note: "The queue is running." };
        const now = deps.now();
        const overdue = Q.overdue(sched.items, sched.paused.at, now);
        if (overdue.length) {
          const s = await schedSettings();
          // Undo puts the pause back too: rows restored to times already past would
          // otherwise run the moment they are restored.
          const undo = { ...Q.snapshot(sched.items, overdue), paused: { ...sched.paused } };
          const out = Q.resume(sched.items, choice, sched.paused.at, now, quietOf(s));
          if (out.error) throw new Refusal(out.error, out.code === "invalid" ? "choice" : out.code);
          sched.items = out.items;
          sched.paused = null;
          return { changed: out.changed, undo, note: "Queue resumed" };
        }
        sched.paused = null;
        return { changed: [], note: "Queue resumed" };
      });
    }

    async function dismiss({ sid }) {
      return mutate(async (sched) => {
        const item = current_(sched, sid);
        if (!["failed", "missed", "asked", "prepared"].includes(item.state)) {
          throw new Refusal("That post still has somewhere to go.", "locked");
        }
        const row = patch(sched, sid, { state: "done", outcome: item.outcome || item.state, endedAt: deps.now() });
        await retire(sched, [sid]);
        return { item: row, note: "Moved to history" };
      });
    }

    async function retry({ sid }) {
      const sched = await load();
      const item = current_(sched, sid);
      if (item.custody !== "local") {
        throw new Refusal("The clip is not on this computer. Schedule it again from SnipShare.", "gone");
      }
      return postNow({ sid });
    }

    function cleanSettings(changes) {
      const out = {};
      const clockText = /^([01]\d|2[0-3]):[0-5]\d$/;
      for (const [key, value] of Object.entries(changes || {})) {
        if (["bringForward", "idleForward", "quietOn", "perPostNotices"].includes(key)) {
          if (typeof value !== "boolean") throw new Refusal(`${key} must be on or off.`, "invalid");
          out[key] = value;
        } else if (key === "quietStart" || key === "quietEnd") {
          if (!clockText.test(String(value))) throw new Refusal("Choose a time like 23:00.", "invalid");
          out[key] = String(value);
        } else if (key === "gapMinutes") {
          const n = Number(value);
          if (!Number.isInteger(n) || n < 2 || n > 1440) throw new Refusal("Choose a gap between 2 minutes and a day.", "invalid");
          out[key] = n;
        } else {
          throw new Refusal("That is not a scheduling setting.", "invalid");
        }
      }
      return out;
    }

    async function saveSettings({ changes }) {
      const clean = cleanSettings(changes);
      await (chain = chain.then(async () => {
        const stored = await settings();
        await deps.storage.set({ settings: { ...stored, ...clean } });
      }).catch(() => {}));
      await settled();
      return { settings: await schedSettings(), note: "Saved" };
    }

    async function testQuiet() {
      const result = await place.testQuiet();
      await push();
      return result;
    }

    async function runlog() {
      return (await deps.storage.get("schedLog")).schedLog || [];
    }

    const COMMANDS = {
      queue: () => state(),
      retime, caption, cancel, restore,
      "post-now": postNow,
      "post-next-now": postNextNow,
      pause, resume, dismiss, retry,
      settings: saveSettings,
      "test-quiet": testQuiet,
      "show-whatsapp": async () => { await deps.showWhatsApp(); return { shown: true }; },
      runlog,
    };

    async function command(message) {
      const work = COMMANDS[message && message.cmd];
      if (!work) throw new Refusal("The extension does not know that request.", "unknown");
      return work(message);
    }

    // The queue page and the options page, over `snipshare-queue`.
    function attach(port) {
      ports.add(port);
      port.onDisconnect.addListener(() => ports.delete(port));
      port.onMessage.addListener(async (message) => {
        if (!message || typeof message !== "object") return;
        const rid = message.rid;
        try {
          const result = await command(message);
          try { port.postMessage({ rid, ok: true, result }); } catch { ports.delete(port); }
        } catch (err) {
          const code = err && typeof err.code === "string" ? err.code : "failed";
          try {
            port.postMessage({ rid, ok: false, error: { message: String(err && err.message || err), code } });
          } catch { ports.delete(port); }
          if (code === "conflict") await push();
        }
      });
      state().then((snapshot) => {
        try { port.postMessage({ event: "queue", state: snapshot }); } catch { ports.delete(port); }
      }).catch(() => {});
    }

    // The SnipShare page's Up next: the next three, the count, and what needs the person.
    async function peek() {
      const sched = await load();
      const live = Q.sorted(Q.pending(sched.items));
      return {
        next: live.slice(0, 3).map((item) => ({
          id: item.id, due: item.due, caption: item.caption, word: Q.statusOf(item, !!sched.paused).word,
        })),
        count: live.length,
        needsYou: needsYou(sched),
      };
    }

    // -- notifications pressed -------------------------------------------------------------------

    function parseNotice(id) {
      const [head, kind, sid] = String(id || "").split("|");
      return head === "sched" ? { kind, sid } : null;
    }

    async function clicked(id) {
      const notice = parseNotice(id);
      if (!notice) return false;
      try { await deps.notifications.clear(id); } catch { /* gone */ }
      if (notice.kind === "asked") {
        // The person pressed it: today's model, WhatsApp brought forward (FR-13).
        try { await start(notice.sid, true); return true; } catch { /* show the queue instead */ }
      }
      if (notice.kind === "signed-out" || notice.kind === "prepared") { await deps.showWhatsApp(); return true; }
      await deps.openQueue();
      return true;
    }

    async function button(id, index) {
      const notice = parseNotice(id);
      if (!notice) return false;
      try { await deps.notifications.clear(id); } catch { /* gone */ }
      if (index === 0 && (notice.kind === "asked" || notice.kind === "missed")) {
        try { await start(notice.sid, true); return true; } catch { await deps.openQueue(); return true; }
      }
      if (index === 0 && (notice.kind === "signed-out" || notice.kind === "prepared")) {
        await deps.showWhatsApp();
        return true;
      }
      await deps.openQueue();
      return true;
    }

    return {
      create, peek, attach, command, alarm, wake, tick, sweep, state, clicked, button,
      needsYou: async () => needsYou(await load()),
      // Settings written straight to storage by the options page: tell the open pages.
      changed: () => settled(),
      // For the tests: the run in flight, if any.
      settle: async () => { while (current || ticking) { await (current || ticking); } await chain; },
    };
  }

  const api = { make, Refusal, DEFAULTS, LIMIT_DEFAULTS, WAIT_TRIES, WAIT_STEP_MS, SWEEP_MINUTES,
    PREPARED_HOLD_MS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SnipSchedule = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
