// The queue page. It holds no queue of its own: the service worker owns every schedule
// (FR-17), this page subscribes over a port, draws what it is told, and sends commands
// that name the revision they were made against. A stale one is refused with `conflict`
// and the page shows the current queue and keeps the person's edit for another try.
// Statuses, the time words and the checks all come from queue.js (SnipQueue), so this
// page and the worker never disagree about what a state is called or what a time means.
"use strict";

(() => {
  const $ = (id) => document.getElementById(id);

  const UNDO_MS = (SnipQueue && SnipQueue.UNDO_MS) || 10000;
  const FLASH_MS = 2000;
  const SLIDE_MS = 260;
  // Nothing from the worker in this long after connecting means it is not answering.
  const SILENT_MS = 8000;
  const REQUEST_MS = 60000;
  const DEFAULT_QUIET = { on: true, start: "23:00", end: "07:00" };
  const ACTION_LABEL = {
    "post-now": "Prepare now", retry: "Try again", dismiss: "Dismiss", look: "Show me",
  };
  // States a person can still make go now. A running or prepared one is past that.
  const GO_STATES = ["holding", "scheduled", "prewarmed", "waiting", "missed", "asked", "failed"];

  let port = null;
  let state = null;
  let skew = 0;            // worker clock minus this page's clock, from the last push
  let rid = 0;
  const waiting = new Map();
  let retryMs = 1000;
  let retryTimer = null;
  let silentTimer = null;

  let editing = null;      // { id, field, el, rev, orig, ending }
  let openMenu = null;     // { id, wrap }
  let deferred = false;    // a push arrived while a row was busy
  let focusKey = null;
  let flashId = null;
  let flashTimer = null;
  let toast = null;        // { timer, sid }
  let conflict = null;     // { sid, kind, value, label }
  let choosing = false;    // the three-choice panel is open

  const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  const nowMs = () => Date.now() + skew;

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  // -- talking to the worker --------------------------------------------------------

  function connect() {
    clearTimeout(retryTimer);
    try {
      port = chrome.runtime.connect({ name: "snipshare-queue" });
    } catch {
      port = null;
      return lost();
    }
    port.onMessage.addListener(onMessage);
    port.onDisconnect.addListener(() => {
      // Reading lastError marks the disconnect as handled.
      void chrome.runtime.lastError;
      port = null;
      lost();
    });
    clearTimeout(silentTimer);
    silentTimer = setTimeout(() => { if (!state) showFailure("The extension did not answer. Reload this page, or press Try now."); }, SILENT_MS);
  }

  // The worker may have been stopped and started again, which drops the port. Nothing
  // is lost: the next connect is pushed the whole queue.
  function lost() {
    for (const [, ask] of waiting) ask.reject({ message: "Not connected to the extension", code: "offline" });
    waiting.clear();
    $("offline").hidden = false;
    document.body.classList.add("offline");
    clearTimeout(retryTimer);
    retryTimer = setTimeout(connect, retryMs);
    retryMs = Math.min(retryMs * 2, 10000);
  }

  function onMessage(message) {
    if (message && message.event === "queue") {
      clearTimeout(silentTimer);
      retryMs = 1000;
      $("offline").hidden = true;
      $("failure").hidden = true;
      document.body.classList.remove("offline");
      return receive(message.state);
    }
    if (message && message.rid != null && waiting.has(message.rid)) {
      const ask = waiting.get(message.rid);
      waiting.delete(message.rid);
      clearTimeout(ask.timer);
      if (message.ok) ask.resolve(message.result || {});
      else ask.reject(message.error || { message: "That did not work", code: "failed" });
    }
  }

  function request(cmd, args = {}) {
    if (!port) return Promise.reject({ message: "Not connected to the extension", code: "offline" });
    return new Promise((resolve, reject) => {
      const id = ++rid;
      const timer = setTimeout(() => {
        waiting.delete(id);
        reject({ message: "The extension did not answer in time", code: "timeout" });
      }, REQUEST_MS);
      waiting.set(id, { resolve, reject, timer });
      try { port.postMessage({ rid: id, cmd, ...args }); }
      catch { waiting.delete(id); clearTimeout(timer); reject({ message: "Not connected to the extension", code: "offline" }); }
    });
  }

  // -- reading the state -------------------------------------------------------------

  function quiet() {
    const s = (state && state.settings) || {};
    return {
      on: s.quietOn == null ? DEFAULT_QUIET.on : !!s.quietOn,
      start: s.quietStart || DEFAULT_QUIET.start,
      end: s.quietEnd || DEFAULT_QUIET.end,
    };
  }

  const items = () => (state ? SnipQueue.sorted(state.items || []) : []);
  const visible = () => items().filter((i) => !SnipQueue.TERMINAL.includes(i.state));
  const find = (id) => items().find((i) => i.id === id) || null;
  const paused = () => !!(state && state.paused);
  const statusOf = (item) => SnipQueue.statusOf(item, paused());

  function firstLine(text) {
    return String(text || "").split(/\r?\n/)[0].trim();
  }

  function clock(ts) {
    const withSeconds = ts % 60000 !== 0;
    return new Date(ts).toLocaleTimeString([], withSeconds
      ? { hour: "numeric", minute: "2-digit", second: "2-digit" }
      : { hour: "numeric", minute: "2-digit" });
  }

  function dayOf(ts) {
    const d = new Date(ts);
    return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  }

  function dayLabel(ts) {
    const today = dayOf(nowMs());
    const day = dayOf(ts);
    const days = Math.round((day - today) / 86400000);
    if (days === 0) return "Today";
    if (days === 1) return "Tomorrow";
    if (days === -1) return "Yesterday";
    return new Date(ts).toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
  }

  function until(ms) {
    if (ms <= 0) return "due now";
    const s = Math.round(ms / 1000);
    if (s < 60) return `in ${s} s`;
    const m = Math.floor(s / 60);
    if (m < 60) return `in ${m} min ${s % 60} s`;
    const h = Math.floor(m / 60);
    if (h < 24) return `in ${h} h ${m % 60} min`;
    return `in ${Math.floor(h / 24)} days ${h % 24} h`;
  }

  function bytes(n) {
    if (n >= 1e9) { const g = n / 1e9; return `${Number.isInteger(g) ? g : g.toFixed(1)} GB`; }
    return `${Math.round(n / 1e6)} MB`;
  }

  // toLocal and fromLocal: the epoch the worker uses against what a datetime-local
  // field holds, which is wall clock time in the browser's zone.
  function toLocal(ts) {
    const d = new Date(ts);
    const p = (n) => String(n).padStart(2, "0");
    const base = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
    return ts % 60000 ? `${base}:${p(d.getSeconds())}` : base;
  }
  const fromLocal = (value) => (value ? new Date(value).getTime() : NaN);

  // The one line a person needs when something is wrong with an item.
  function why(item) {
    const msg = statusOf(item).detail;
    if (item.state === "missed") {
      return `It was due ${SnipQueue.describe(item.due, nowMs())}.${msg ? ` ${msg}` : ""}`;
    }
    if (item.state === "asked") return "It is ready, but WhatsApp has to come to the front. Prepare it when you can.";
    return msg || "It did not work.";
  }

  // -- announcing ---------------------------------------------------------------------

  // Cleared first so the same sentence twice still gets said.
  function announce(text) {
    const live = $("live");
    live.textContent = "";
    setTimeout(() => { live.textContent = text; }, 40);
  }

  function showToast(text, { snap = null, sid = null, kind = "info" } = {}) {
    clearTimeout(toast && toast.timer);
    const bar = $("toast");
    $("toast-text").textContent = text;
    $("toast-undo").hidden = !snap;
    bar.dataset.kind = kind;
    bar.hidden = false;
    toast = { sid, snap, paused: paused(), timer: setTimeout(hideToast, snap ? UNDO_MS : 7000) };
    announce(text + (snap ? ". Undo is available for 10 seconds." : ""));
  }

  function hideToast() {
    clearTimeout(toast && toast.timer);
    toast = null;
    $("toast").hidden = true;
  }

  function showFailure(text) {
    $("loading").hidden = true;
    $("failure").textContent = text;
    $("failure").hidden = false;
  }

  // -- drawing -------------------------------------------------------------------------

  function receive(next) {
    state = next;
    skew = (next.now || Date.now()) - Date.now();
    $("loading").hidden = true;
    $("content").hidden = false;
    render();
  }

  // A row being edited, or its menu being open, must not move under the person's hands,
  // so the table waits (FR-5); everything else still updates.
  const rowsBusy = () => !!(editing || openMenu);

  function render() {
    const keep = document.activeElement && document.activeElement.closest
      ? document.activeElement.closest("[data-k]") : null;
    if (keep && !focusKey) focusKey = keep.dataset.k;
    renderControls();
    renderNeeds();
    renderNext();
    if (rowsBusy()) deferred = true;
    else { deferred = false; renderRows(); }
    renderHistory();
    renderFooter();
    renderConflict();
    // Undo is never offered once the thing it would undo is running.
    if (toast && toast.snap && toast.sid) {
      const item = find(toast.sid);
      if (item && item.state === "running") hideToast();
    }
    // A note about pausing goes stale the moment another page resumes, or pauses.
    if (toast && !toast.snap && toast.paused !== paused()) hideToast();
    restoreFocus();
  }

  function restoreFocus() {
    if (!focusKey) return;
    const el = document.querySelector(`[data-k="${CSS.escape(focusKey)}"]`);
    focusKey = null;
    if (el && !el.disabled) el.focus({ preventScroll: true });
  }

  function renderControls() {
    const list = visible();
    const next = nextCandidate();
    $("post-next").disabled = !next;
    $("pause").hidden = paused();
    $("pause").disabled = !list.length && !paused();
    $("paused").hidden = !paused();
    if (paused()) {
      $("paused-text").innerHTML = `<strong>Paused</strong> since ${escapeHtml(SnipQueue.describe(state.paused.at, nowMs()))}. Nothing will be prepared until you resume.`;
      const over = SnipQueue.overdue(state.items, state.paused.at, nowMs());
      $("resume-choices").hidden = !choosing || !over.length;
      $("resume-plain").hidden = choosing && over.length > 0;
      if (choosing && !over.length) choosing = false;
      $("resume-ask").textContent = over.length === 1
        ? "1 fell due while the queue was paused. What should happen to it?"
        : `${over.length} fell due while the queue was paused. What should happen to them?`;
    } else {
      choosing = false;
    }
    $("empty").hidden = list.length > 0;
    $("table-block").hidden = list.length === 0;
    $("pause").parentElement.hidden = false;
  }

  function nextCandidate() {
    return visible().find((i) => ["scheduled", "prewarmed", "waiting", "holding"].includes(i.state)) || null;
  }

  function renderNeeds() {
    const need = visible().filter((i) => statusOf(i).needsYou);
    $("needs").hidden = need.length === 0;
    $("needs-count").textContent = need.length ? `(${need.length})` : "";
    $("needs-list").innerHTML = need.map((item) => {
      const st = statusOf(item);
      const action = st.action || "look";
      const cap = firstLine(item.caption) || "No caption";
      return `<li data-tone="${st.tone}">
        <div class="needs__what"><span class="needs__word">${escapeHtml(st.word)}</span> <span class="muted">${escapeHtml(cap)}</span>
          <div class="needs__why">${escapeHtml(why(item))}</div></div>
        <button type="button" class="btn btn--primary" data-act="${action}" data-id="${escapeHtml(item.id)}" data-k="n:${escapeHtml(item.id)}">${ACTION_LABEL[action]}</button>
      </li>`;
    }).join("");
  }

  function renderNext() {
    const item = nextCandidate();
    $("next").hidden = !item;
    if (!item) return;
    const cap = firstLine(item.caption) || "No caption";
    $("next-line").innerHTML = `${paused() ? "Paused. It would be prepared " : ""}<strong id="cd"></strong> `
      + `${escapeHtml(cap)}<span class="muted"> at ${escapeHtml(SnipQueue.describe(item.due, nowMs()))}</span>`;
    tick();
  }

  // Once a second: only the countdown text changes, never the table.
  function tick() {
    const item = state && nextCandidate();
    const cd = $("cd");
    if (item && cd) cd.textContent = until(item.due - nowMs()).replace(/^./, (c) => c.toUpperCase());
  }

  function storageLine(item) {
    if (item.custody === "fetching") {
      const pct = item.size ? Math.min(99, Math.round(((item.fetched || 0) / item.size) * 100)) : 0;
      return `Coming down ${pct} %`;
    }
    return "On this computer";
  }

  function rowHtml(item) {
    const id = escapeHtml(item.id);
    const st = statusOf(item);
    const edit = SnipQueue.editable(item);
    const cap = firstLine(item.caption);
    const full = SnipQueue.describe(item.due, nowMs());
    const when = edit
      ? `<button type="button" class="when" data-act="edit-when" data-id="${id}" data-k="${id}:when" aria-label="Change time, ${escapeHtml(full)}">${escapeHtml(clock(item.due))}</button>`
      : `<span class="when when--locked">${escapeHtml(clock(item.due))}</span>`;
    const caption = edit
      ? `<button type="button" class="cap${cap ? "" : " cap--empty"}" data-act="edit-cap" data-id="${id}" data-k="${id}:cap" aria-label="Edit caption: ${escapeHtml(cap || "empty")}">${escapeHtml(cap || "No caption")}</button>`
      : `<span class="cap cap--locked${cap ? "" : " cap--empty"}">${escapeHtml(cap || "No caption")}</span>`;
    const primary = st.action
      ? `<button type="button" class="btn btn--small" data-act="${st.action}" data-id="${id}" data-k="${id}:act">${ACTION_LABEL[st.action]}</button>`
      : "";
    const menu = [];
    if (GO_STATES.includes(item.state) && st.action !== "post-now") menu.push(["post-now", "Prepare now", ""]);
    if (edit) menu.push(["edit-cap", "Edit caption", ""], ["cancel", "Cancel", "danger"]);
    const more = menu.length
      ? `<span class="more-wrap"><button type="button" class="btn btn--small" data-act="more" data-id="${id}" data-k="${id}:more" aria-haspopup="menu" aria-expanded="false" aria-label="More actions for ${escapeHtml(cap || "this one")}">More</button>`
        + `<ul class="menu" role="menu" aria-label="More actions" hidden>${menu.map(([act, label, cls]) =>
          `<li role="none"><button type="button" role="menuitem" class="${cls}" data-act="${act}" data-id="${id}" tabindex="-1">${label}</button></li>`).join("")}</ul></span>`
      : "";
    const detail = `Due ${full}.${item.error && item.error.message ? ` ${item.error.message}` : ""}`;
    return `<tr class="row" data-id="${id}">
      <td class="c-when">${when}</td>
      <td class="c-cap">${caption}<details class="card-detail"><summary>Details</summary><p>${escapeHtml(detail)}</p></details></td>
      <td class="c-status"><div class="status" data-tone="${st.tone}"><span class="status__word">${escapeHtml(st.word)}</span><span class="status__sub">${escapeHtml(storageLine(item))}</span>${st.detail ? `<span class="status__sub">${escapeHtml(st.detail)}</span>` : ""}</div></td>
      <td class="c-act">${primary}${more}</td>
    </tr>`;
  }

  function renderRows() {
    const body = $("rows");
    const before = new Map();
    for (const tr of body.querySelectorAll("tr.row")) before.set(tr.dataset.id, tr.getBoundingClientRect().top);
    let html = "";
    let lastDay = null;
    for (const item of visible()) {
      const day = dayOf(item.due);
      if (day !== lastDay) {
        html += `<tr class="day"><th scope="rowgroup" colspan="4">${escapeHtml(dayLabel(item.due))}</th></tr>`;
        lastDay = day;
      }
      html += rowHtml(item);
    }
    body.innerHTML = html;
    if (flashId) {
      const row = body.querySelector(`tr.row[data-id="${CSS.escape(flashId)}"]`);
      if (row) {
        row.classList.add("flash");
        row.scrollIntoView({ block: "nearest", behavior: reduced() ? "auto" : "smooth" });
      }
      clearTimeout(flashTimer);
      flashTimer = setTimeout(() => { flashId = null; const r = body.querySelector("tr.flash"); if (r) r.classList.remove("flash"); }, FLASH_MS);
    }
    // A short slide from where each row was to where it is now.
    if (!reduced()) {
      for (const tr of body.querySelectorAll("tr.row")) {
        const was = before.get(tr.dataset.id);
        if (was == null) continue;
        const dy = was - tr.getBoundingClientRect().top;
        if (Math.abs(dy) < 2) continue;
        // Table rows cannot be transformed in every engine; its cells can.
        const cells = [...tr.children];
        for (const c of cells) { c.style.transition = "none"; c.style.transform = `translateY(${dy}px)`; }
        void tr.offsetHeight;
        for (const c of cells) { c.style.transition = `transform ${SLIDE_MS}ms ease`; c.style.transform = ""; }
      }
    }
  }

  function renderHistory() {
    const list = (state.history || []).slice().sort((a, b) => (b.endedAt || b.due) - (a.endedAt || a.due));
    $("history-count").textContent = list.length ? `(${list.length})` : "";
    $("history-empty").hidden = list.length > 0;
    $("history-list").innerHTML = list.map((item) => {
      const st = SnipQueue.statusOf(item, false);
      return `<li><span>${escapeHtml(new Date(item.due).toLocaleString([], { weekday: "short", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }))}</span>`
        + `<span class="status" data-tone="${st.tone}"><span class="status__word">${escapeHtml(st.word)}</span></span>`
        + `<span class="h-cap">${escapeHtml(firstLine(item.caption) || "No caption")}</span></li>`;
    }).join("");
  }

  function renderFooter() {
    const u = state.usage || { bytes: 0, budgetBytes: 0, pending: 0, pendingLimit: 0 };
    $("budget-text").textContent = `${bytes(u.bytes)} of ${bytes(u.budgetBytes)} on this computer`;
    const pct = u.budgetBytes ? Math.min(100, Math.round((u.bytes / u.budgetBytes) * 100)) : 0;
    $("budget-fill").style.width = `${pct}%`;
    $("budget-meter").setAttribute("aria-valuenow", String(pct));
    $("budget-meter").dataset.hot = String(pct >= 85);
    $("storage-detail").textContent = `${u.pending} of ${u.pendingLimit} schedules in use. `
      + "Scheduled clips are kept on this computer. Cancelling or finishing one frees its room.";
    const q = state.quiet || {};
    $("quiet-text").textContent = q.works === true ? "Quiet posting works on this computer."
      : q.works === false ? "Quiet posting does not work on this computer. WhatsApp will ask you instead."
      : "Quiet posting has not been tried on this computer yet.";
  }

  function renderConflict() {
    $("conflict").hidden = !conflict;
    if (!conflict) return;
    $("conflict-text").textContent = `${conflict.label} was changed somewhere else first, so your edit was not saved. The queue above is the current one. Your edit is kept here.`;
    $("conflict-edit").textContent = conflict.value;
  }

  // -- acting ------------------------------------------------------------------------

  function fail(e, label) {
    if (e && e.code === "conflict") return;
    showToast(`${label ? `${label}: ` : ""}${(e && e.message) || "That did not work"}`, { kind: "error" });
  }

  async function act(cmd, args, okText, { sid = null, flash = false } = {}) {
    try {
      const result = await request(cmd, args);
      if (flash && sid) { flashId = sid; focusKey = null; }
      if (okText || result.note) {
        showToast(result.note || okText, { snap: result.undo || null, sid });
      }
      if (result.warning) announce(result.warning);
      if (flash && state) render();
      return result;
    } catch (e) {
      if (e && e.code === "conflict") {
        conflict = { sid, kind: cmd, value: args.__keep || "", label: "This one", args };
        renderConflict();
        announce("This one was changed somewhere else first. Your edit is kept.");
      } else fail(e);
      return null;
    }
  }

  function doAction(name, id) {
    const item = id ? find(id) : null;
    switch (name) {
      case "edit-when": return item && startWhen(item);
      case "edit-cap": return item && startCaption(item);
      case "post-now": return act("post-now", { sid: id }, "Preparing it now.", { sid: id });
      case "retry": return act("retry", { sid: id }, "Trying again.", { sid: id });
      case "dismiss": return act("dismiss", { sid: id }, "Dismissed.", { sid: id });
      case "look": return act("show-whatsapp", {}, "");
      case "cancel": return item && act("cancel", { sid: id, rev: item.rev }, "Cancelled.", { sid: id });
      default: return null;
    }
  }

  // -- editing the time in place (FR-5) -----------------------------------------------

  function startWhen(item) {
    if (editing || !SnipQueue.editable(item)) return;
    closeMenu(false);
    const cell = document.querySelector(`tr.row[data-id="${CSS.escape(item.id)}"] td.c-when`);
    if (!cell) return;
    const eid = `w-${item.id}`;
    cell.innerHTML = `<div class="editor" data-bad="false">
      <input type="datetime-local" value="${escapeHtml(toLocal(item.due))}" ${item.due % 60000 ? 'step="1"' : 'step="60"'} aria-label="New time" aria-describedby="${escapeHtml(eid)}">
      <div class="editor__words" id="${escapeHtml(eid)}"></div>
      <div class="editor__warn"></div><div class="editor__err" role="alert"></div></div>`;
    const el = cell.querySelector(".editor");
    const input = el.querySelector("input");
    editing = { id: item.id, field: "when", el, rev: item.rev, orig: item.due, ending: false };
    input.addEventListener("input", () => checkWhen(el, item));
    input.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") { ev.preventDefault(); saveWhen(item, false); }
      else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); endEdit(item.id, "when"); }
    });
    input.addEventListener("blur", () => saveWhen(item, true));
    input.focus();
    checkWhen(el, item);
  }

  // Live validation: the words line, any refusal beside the field, and the 90 s rule.
  function checkWhen(el, item) {
    const input = el.querySelector("input");
    const due = fromLocal(input.value);
    const words = el.querySelector(".editor__words");
    const err = el.querySelector(".editor__err");
    const warn = el.querySelector(".editor__warn");
    let bad = false;
    let message = "";
    let caution = "";
    if (!Number.isFinite(due)) {
      bad = true; message = "Choose a date and a time.";
      words.textContent = "";
    } else {
      words.textContent = SnipQueue.describe(due, nowMs());
      const check = SnipQueue.checkDue(due, nowMs(), quiet());
      if (!check.ok) { bad = true; message = check.error; }
      else {
        if (check.warning) caution = check.warning;
        const spaced = SnipQueue.spaced(items(), due, item.id);
        if (spaced.due !== due) {
          const other = spaced.after ? find(spaced.after) : null;
          words.textContent = `Will be saved at ${clock(spaced.due)}, 90 s after the clip${other ? ` at ${clock(other.due)}` : " before it"}.`;
        }
      }
    }
    el.dataset.bad = String(bad);
    err.textContent = message;
    warn.textContent = caution;
    return { bad, due, message };
  }

  async function saveWhen(item, fromBlur) {
    if (!editing || editing.id !== item.id || editing.field !== "when" || editing.ending) return;
    const check = checkWhen(editing.el, item);
    if (check.bad) {
      // Enter stays so the person can fix it; leaving puts the old time back and says why.
      if (!fromBlur) return;
      const msg = check.message;
      endEdit(item.id, "when");
      return showToast(`Time not changed: ${msg}`, { kind: "error" });
    }
    if (check.due === editing.orig) return endEdit(item.id, "when");
    editing.ending = true;
    editing.el.querySelector("input").readOnly = true;
    const latest = find(item.id) || item;
    try {
      const result = await request("retime", { sid: item.id, rev: latest.rev, due: check.due });
      editing = null;
      flashId = item.id;
      focusKey = `${item.id}:when`;
      const moved = result.note || `Moved to ${SnipQueue.describe(result.item ? result.item.due : check.due, nowMs())}`;
      render();
      const list = visible();
      const at = list.findIndex((i) => i.id === item.id) + 1;
      showToast(moved, { snap: result.undo || null, sid: item.id });
      if (at) announce(`${moved}. Now number ${at} of ${list.length}.`);
    } catch (e) {
      editing = null;
      if (e && e.code === "conflict") {
        conflict = { sid: item.id, kind: "retime", value: SnipQueue.describe(check.due, nowMs()), label: "This time", due: check.due };
        focusKey = `${item.id}:when`;
        render();
        announce("This one was changed somewhere else first. Your edit is kept.");
      } else {
        focusKey = `${item.id}:when`;
        render();
        fail(e, "Time not changed");
      }
    }
  }

  function endEdit(id, field) {
    if (!editing) return;
    editing.ending = true;
    editing = null;
    focusKey = `${id}:${field === "when" ? "when" : "cap"}`;
    render();
  }

  // -- editing the caption in place ----------------------------------------------------

  function startCaption(item) {
    if (editing || !SnipQueue.editable(item)) return;
    closeMenu(false);
    const cell = document.querySelector(`tr.row[data-id="${CSS.escape(item.id)}"] td.c-cap`);
    if (!cell) return;
    cell.innerHTML = `<div class="editor editor--wide"><textarea maxlength="1024" rows="3" aria-label="Caption" aria-describedby="h-${escapeHtml(item.id)}"></textarea>
      <div class="editor__words" id="h-${escapeHtml(item.id)}">Enter saves. Shift and Enter makes a new line. Escape puts it back.</div>
      <div class="editor__err" role="alert"></div></div>`;
    const el = cell.querySelector(".editor");
    const area = el.querySelector("textarea");
    area.value = item.caption || "";
    editing = { id: item.id, field: "cap", el, rev: item.rev, orig: item.caption || "", ending: false };
    area.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); saveCaption(item, false); }
      else if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); endEdit(item.id, "cap"); }
    });
    area.addEventListener("blur", () => saveCaption(item, true));
    area.focus();
    area.setSelectionRange(area.value.length, area.value.length);
  }

  async function saveCaption(item, fromBlur) {
    if (!editing || editing.id !== item.id || editing.field !== "cap" || editing.ending) return;
    const area = editing.el.querySelector("textarea");
    const text = area.value.trim();
    if (text === editing.orig.trim()) return endEdit(item.id, "cap");
    editing.ending = true;
    area.readOnly = true;
    const latest = find(item.id) || item;
    try {
      const result = await request("caption", { sid: item.id, rev: latest.rev, caption: text });
      editing = null;
      focusKey = `${item.id}:cap`;
      render();
      showToast(result.note || "Caption changed.", { snap: result.undo || null, sid: item.id });
    } catch (e) {
      editing = null;
      focusKey = `${item.id}:cap`;
      if (e && e.code === "conflict") {
        conflict = { sid: item.id, kind: "caption", value: text, label: "This caption", text };
        render();
        announce("This one was changed somewhere else first. Your edit is kept.");
      } else {
        render();
        fail(e, "Caption not changed");
      }
    }
    void fromBlur;
  }

  // A refused edit, applied again against the revision now on screen.
  async function retryConflict() {
    const c = conflict;
    if (!c) return;
    const item = find(c.sid);
    if (!item) { conflict = null; return render(); }
    try {
      const result = c.kind === "retime"
        ? await request("retime", { sid: c.sid, rev: item.rev, due: c.due })
        : await request("caption", { sid: c.sid, rev: item.rev, caption: c.text });
      conflict = null;
      flashId = c.sid;
      render();
      showToast(result.note || "Saved.", { snap: result.undo || null, sid: c.sid });
    } catch (e) {
      if (e && e.code !== "conflict") fail(e);
      else announce("Still out of date. The queue has been refreshed; try once more.");
    }
  }

  // -- the More menu ---------------------------------------------------------------------

  function toggleMenu(btn) {
    const wrap = btn.closest(".more-wrap");
    if (openMenu && openMenu.wrap === wrap) return closeMenu(true);
    closeMenu(false);
    const menu = wrap.querySelector(".menu");
    menu.hidden = false;
    btn.setAttribute("aria-expanded", "true");
    openMenu = { id: btn.dataset.id, wrap, btn };
    menu.querySelector('[role="menuitem"]').focus();
  }

  function closeMenu(refocus) {
    if (!openMenu) return;
    const { wrap, btn } = openMenu;
    openMenu = null;
    wrap.querySelector(".menu").hidden = true;
    btn.setAttribute("aria-expanded", "false");
    if (refocus) btn.focus();
    if (deferred && !editing) { focusKey = refocus ? btn.dataset.k : null; render(); }
  }

  function menuKeys(ev) {
    if (!openMenu) return;
    const items_ = [...openMenu.wrap.querySelectorAll('[role="menuitem"]')];
    const at = items_.indexOf(document.activeElement);
    if (ev.key === "ArrowDown") { ev.preventDefault(); items_[(at + 1) % items_.length].focus(); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); items_[(at - 1 + items_.length) % items_.length].focus(); }
    else if (ev.key === "Escape") { ev.preventDefault(); closeMenu(true); }
    else if (ev.key === "Tab") closeMenu(false);
  }

  // -- the controls -----------------------------------------------------------------------

  async function resume(choice) {
    const result = await act("resume", { choice }, choice === "later" ? "Resumed. Everything that fell due moved later."
      : choice === "missed" ? "Resumed. Those were marked missed." : "Resumed.");
    if (result) { choosing = false; if (state) render(); }
  }

  function wire() {
    $("rows").addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-act]");
      if (!btn) return;
      const name = btn.dataset.act;
      if (name === "more") return toggleMenu(btn);
      if (openMenu) closeMenu(false);
      doAction(name, btn.dataset.id);
    });
    $("rows").addEventListener("keydown", (ev) => {
      if (ev.key === "F2") {
        const target = ev.target.closest("button.when, button.cap");
        if (target) { ev.preventDefault(); target.click(); }
        return;
      }
      menuKeys(ev);
    });
    document.addEventListener("click", (ev) => {
      if (openMenu && !openMenu.wrap.contains(ev.target)) closeMenu(false);
    });
    $("needs-list").addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-act]");
      if (btn) doAction(btn.dataset.act, btn.dataset.id);
    });
    $("post-next").addEventListener("click", () => act("post-next-now", {}, "Preparing the next one now."));
    $("pause").addEventListener("click", () => act("pause", {}, "Paused. Nothing will be prepared until you resume."));
    $("resume").addEventListener("click", async () => {
      const over = SnipQueue.overdue(state.items, state.paused.at, nowMs());
      if (over.length) { choosing = true; renderControls(); const first = $("resume-choices").querySelector("button"); if (first) first.focus(); return; }
      resume("post");
    });
    $("resume-choices").addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-choice]");
      if (btn) resume(btn.dataset.choice);
    });
    $("resume-stay").addEventListener("click", () => { choosing = false; renderControls(); $("resume").focus(); });
    $("toast-close").addEventListener("click", hideToast);
    $("toast-undo").addEventListener("click", async () => {
      const t = toast;
      if (!t || !t.snap) return;
      try {
        await request("restore", { snap: t.snap });
        hideToast();
        flashId = t.sid;
        focusKey = t.sid ? `${t.sid}:when` : null;
        if (state) render();
        showToast("Undone.", { sid: t.sid });
      } catch (e) {
        hideToast();
        fail(e, "Could not undo");
      }
    });
    $("conflict-retry").addEventListener("click", retryConflict);
    $("conflict-drop").addEventListener("click", () => { conflict = null; renderConflict(); });
    $("reconnect").addEventListener("click", () => { retryMs = 1000; connect(); });
    $("test-quiet").addEventListener("click", async () => {
      const out = $("quiet-result");
      const btn = $("test-quiet");
      btn.disabled = true;
      out.hidden = false;
      out.textContent = "Trying quiet mode. Nothing is sent.";
      try {
        const r = await request("test-quiet");
        out.textContent = r && r.ok === false
          ? `It did not work: ${r.error || r.code || "unknown reason"}.`
          : "It works on this computer. Nothing was sent.";
      } catch (e) {
        out.textContent = `Could not try it: ${(e && e.message) || "no answer"}.`;
      }
      btn.disabled = false;
    });
    $("runlog").addEventListener("toggle", async () => {
      if (!$("runlog").open) return;
      try {
        const r = await request("runlog");
        const rows = Array.isArray(r) ? r : (r.entries || r.log || []);
        $("runlog-empty").hidden = rows.length > 0;
        $("runlog-list").innerHTML = rows.slice().reverse().map((e) => {
          const at = e.at || e.ts || e.t || e.ended;
          const parts = [at ? new Date(at).toLocaleString() : "", e.outcome || e.code || e.state || "",
            e.rung || "", e.ms != null ? `${e.ms} ms` : "", e.attempts ? `try ${e.attempts}` : ""];
          return `<li>${escapeHtml(parts.filter(Boolean).join("  "))}</li>`;
        }).join("");
      } catch (e) {
        $("runlog-empty").hidden = false;
        $("runlog-empty").textContent = `Could not read the log: ${(e && e.message) || "no answer"}.`;
      }
    });
    // Leaving the page back to the queue: close anything open on Escape too.
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && openMenu) closeMenu(true); });
    setInterval(tick, 1000);
  }

  wire();
  connect();
})();
