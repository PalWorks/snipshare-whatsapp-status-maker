// schedule.js with a fake clock, a fake chrome.storage, fake alarms and notifications,
// and small fakes of custody.js and place.js; queue.js is the real one. What it
// protects: a worker stopped at any transition carries on from what is stored; alarms
// lost by Chrome are rebuilt; a schedule alarm never wakes the clip job's loop (E1);
// a due time is an instant that a zone or daylight saving change cannot move; a stale
// revision is refused (FR-17); pause and resume with their choices (FR-8); Undo's ten
// seconds are a stored deadline (E11); waiting becomes asking after ten minutes
// (FR-12); prepared becomes done once the composer has gone. docs/scheduling.md.
"use strict";

process.env.TZ = "UTC";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const Q = require("../queue.js");
const SnipSchedule = require("../schedule.js");

const T0 = Date.UTC(2026, 10, 3, 9, 0, 0);   // Tue 3 Nov 2026, 09:00 UTC
const MIN = 60000;

// -- fakes ----------------------------------------------------------------------------

const copy = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));

function fakeArea(initial) {
  const data = copy(initial || {});
  return {
    data,
    async get(keys) {
      const list = keys == null ? Object.keys(data) : Array.isArray(keys) ? keys : [keys];
      const out = {};
      for (const key of list) if (key in data) out[key] = copy(data[key]);
      return out;
    },
    async set(values) { for (const [k, v] of Object.entries(values)) data[k] = copy(v); },
    async remove(keys) { for (const k of Array.isArray(keys) ? keys : [keys]) delete data[k]; },
  };
}

function fakeAlarms() {
  const set = new Map();
  return {
    set,
    async create(name, info) { set.set(name, { name, ...info }); },
    async clear(name) { return set.delete(name); },
    async get(name) { return set.get(name) || undefined; },
    async getAll() { return [...set.values()]; },
  };
}

function fakeNotes() {
  const shown = new Map();
  return {
    shown,
    async create(id, options) { shown.set(id, options); return id; },
    async clear(id) { return shown.delete(id); },
  };
}

function fakeCustody() {
  const kept = new Map();
  const c = {
    kept, dropped: [], fetches: 0, hang: false, damaged: new Set(), size: 9000000,
    async fetch(id, { admit, onProgress, signal }) {
      c.fetches += 1;
      if (c.hang) {
        return new Promise((resolve, reject) => {
          if (signal) signal.addEventListener("abort", () => reject(Object.assign(new Error("Stopped."), { code: "stopped" })));
        });
      }
      if (admit) await admit(c.size);
      if (onProgress) onProgress({ have: c.size, size: c.size, stored: true });
      kept.set(id, c.size);
      return { size: c.size, sha256: "f".repeat(64) };
    },
    async read(id) { return kept.has(id) ? new Blob([new Uint8Array(10)], { type: "video/mp4" }) : null; },
    async verify(id) { return kept.has(id) && !c.damaged.has(id); },
    async drop(id) { kept.delete(id); c.dropped.push(id); },
    async sweep(ids) { for (const id of [...kept.keys()]) if (!ids.includes(id)) kept.delete(id); return 0; },
    async usage() { return { bytes: 0, byId: {} }; },
  };
  return c;
}

function fakePlace() {
  const p = {
    calls: [], results: [], using: false, isBusy: false, prewarms: 0, releases: 0,
    warm: { ok: true, code: "ok", tabId: 7 },
    async load(options) {
      p.calls.push(options);
      const next = p.results.length ? p.results.shift() : { ok: true, rung: "S0", ms: 1500, focusMoved: false };
      if (next === "hang") return new Promise(() => {});
      return next;
    },
    busy: () => p.isBusy,
    async inUse() { return p.using; },
    async prewarm() { p.prewarms += 1; return p.warm; },
    async release() { p.releases += 1; },
    async testQuiet() { return { ok: true, rung: "S1", ms: 900 }; },
    async stats() { return { works: true, best: "S1", tested: T0 }; },
  };
  return p;
}

function world(shared) {
  const w = {
    store: fakeArea({ settings: { quietOn: false, token: "kept" } }),
    session: fakeArea({}),
    alarms: fakeAlarms(),
    notes: fakeNotes(),
    clock: { t: T0 },
    custody: fakeCustody(),
    place: fakePlace(),
    badges: [],
    opened: [],
    paced: 0,
    ...(shared || {}),
  };
  w.s = SnipSchedule.make({
    storage: w.store, session: w.session, alarms: w.alarms, notifications: w.notes,
    queue: Q, place: w.place, custody: w.custody,
    now: () => w.clock.t, random: Math.random, defer: (fn) => setImmediate(fn),
    paced: async () => { w.paced += 1; },
    badge: (n) => w.badges.push(n),
    openQueue: async () => { w.opened.push("queue"); },
    showWhatsApp: async () => { w.opened.push("whatsapp"); },
  });
  // A stopped worker: nothing in memory survives, everything stored does.
  w.restart = (changes) => world({ store: w.store, session: w.session, alarms: w.alarms, notes: w.notes,
    clock: w.clock, custody: w.custody, place: fakePlace(), badges: w.badges, opened: w.opened, ...(changes || {}) });
  return w;
}

async function flush(w) {
  for (let i = 0; i < 8; i++) {
    await w.s.settle();
    await new Promise((resolve) => setImmediate(resolve));
  }
}

async function items(w) { return (w.store.data.sched || { items: [] }).items; }
async function only(w) { return (await items(w))[0]; }

async function schedule(w, dueIn = 10 * MIN, extra = {}) {
  const shares = [];
  const answer = await w.s.create({
    stem: "clip_one", name: "clip.mp4", caption: "Hello", mode: "card", due: w.clock.t + dueIn,
    action: "prepare", limits: { pending: 30, budgetBytes: 400000000 }, ...extra,
  }, { grant: "grant-1", url: "https://renderer.example.com/api/v1/clip?stem=clip_one",
       onProgress: (share) => shares.push(share) });
  await flush(w);
  return { answer, shares };
}

async function at(w, t, alarm = "sched-next") {
  w.clock.t = t;
  await w.s.alarm(alarm);
  await flush(w);
}

// For a worker whose run never ends: it is about to be stopped, so nothing waits on it.
async function startRun(w, t) {
  w.clock.t = t;
  await w.s.alarm("sched-next");
  for (let i = 0; i < 8; i++) await new Promise((resolve) => setImmediate(resolve));
}

function fakePort() {
  const port = {
    sent: [], listener: null, rid: 0,
    postMessage(message) { port.sent.push(message); },
    onMessage: { addListener(fn) { port.listener = fn; } },
    onDisconnect: { addListener() {} },
    async ask(cmd, args) {
      const rid = ++port.rid;
      await port.listener({ rid, cmd, ...(args || {}) });
      return port.sent.find((m) => m.rid === rid);
    },
    pushes() { return port.sent.filter((m) => m.event === "queue"); },
  };
  return port;
}

// -- creating ---------------------------------------------------------------------------

test("a schedule keeps its clip, becomes scheduled, and arms the next wake and the sweep", async () => {
  const w = world();
  const { answer, shares } = await schedule(w);
  const item = await only(w);
  assert.equal(answer.schedule.id, item.id);
  assert.match(item.id, /^s_[a-z0-9]{10}$/);
  assert.equal(item.state, "scheduled");
  assert.equal(item.custody, "local");
  assert.equal(item.size, w.custody.size);
  assert.equal(item.action, "prepare");
  assert.ok(shares.length && shares.at(-1) === 1);
  assert.equal(w.alarms.set.get("sched-next").when, item.due - Q.PREWARM_MS);
  assert.equal(w.alarms.set.get("sched-sweep").periodInMinutes, 15);
  assert.equal(w.store.data.schedLimits.pending, 30);
  assert.equal(w.session.data[`grant:${item.id}`], undefined, "the grant is let go once the clip is kept");
});

test("a time too soon, too far, or over the person's limits is refused with a code", async () => {
  const w = world();
  await assert.rejects(schedule(w, 30000), (err) => err.code === "past");
  await assert.rejects(schedule(w, 31 * 86400000), (err) => err.code === "far");
  await schedule(w);
  await assert.rejects(schedule(w, 60 * MIN, { stem: "clip_two", limits: { pending: 1, budgetBytes: 1e9 } }),
    (err) => err.code === "limit");
  // The budget is checked against the size the server gives.
  await assert.rejects(schedule(w, 60 * MIN, { stem: "clip_two", limits: { pending: 30, budgetBytes: 10000000 } }),
    (err) => err.code === "budget");
  assert.equal((await items(w)).length, 1, "a refused schedule is never saved");
  await assert.rejects(schedule(w, 60 * MIN, { action: "send" }), (err) => err.code === "invalid");
});

// -- the run ------------------------------------------------------------------------------

test("prewarm at due minus five minutes, a quiet run at due minus two, prepared in WhatsApp", async () => {
  const w = world();
  await schedule(w);
  const item = await only(w);
  await at(w, item.due - Q.PREWARM_MS);
  assert.equal((await only(w)).state, "prewarmed");
  assert.equal(w.place.prewarms, 1);
  assert.equal(w.place.calls.length, 0);
  assert.equal(w.alarms.set.get("sched-next").when, item.due - Q.LEAD_MS);
  await at(w, item.due - Q.LEAD_MS);
  assert.equal(w.place.calls.length, 1);
  assert.equal(w.place.calls[0].manual, false);
  assert.equal(w.place.calls[0].caption, "Hello");
  assert.equal(w.place.calls[0].settings.bringForward, false);
  assert.equal(w.paced, 1, "scheduled runs are paced on their own key (E4)");
  const done = await only(w);
  assert.equal(done.state, "prepared");
  assert.equal(done.rung, "S0");
  assert.equal(w.place.releases, 0, "a prepared composer keeps its tab held");
  // It waits on the person's Send, so it is told and counted, perPostNotices or not.
  const notice = w.notes.shown.get(`sched|prepared|${item.id}`);
  assert.match(notice.title, /Status is in WhatsApp\. Press Send there$/);
  assert.deepEqual(notice.buttons, [{ title: "Show WhatsApp" }]);
  assert.equal(w.badges.at(-1), 1);
  await w.s.button(`sched|prepared|${item.id}`, 0);
  assert.deepEqual(w.opened, ["whatsapp"]);
  const log = w.store.data.schedLog;
  assert.equal(log.length, 1);
  assert.deepEqual(Object.keys(log[0]).sort(), ["at", "code", "due", "focusMoved", "id", "late", "manual", "ms", "outcome", "rung"]);
  assert.equal(log[0].code, "ok");
  assert.equal(JSON.stringify(log).includes("Hello"), false, "no caption in the run log (E15)");
});

test("a run whose clip fails its hash fails, says the clip is damaged, and never reaches WhatsApp", async () => {
  const w = world();
  await schedule(w);
  const item = await only(w);
  w.custody.damaged.add(item.id);
  await at(w, item.due - Q.PREWARM_MS);
  const failed = await only(w);
  assert.equal(failed.state, "failed");
  assert.equal(failed.error.code, "damaged");
  assert.ok(w.notes.shown.has(`sched|damaged|${item.id}`));
  assert.equal(w.place.calls.length, 0);
  assert.deepEqual(w.badges.at(-1), 1);
});

test("a failed run is failed with WhatsApp's reason, notified, and the tab let go", async () => {
  const w = world();
  w.place.results.push({ ok: false, code: "moved", rung: "S0", error: "WhatsApp changed its menu", ms: 4000 });
  await schedule(w);
  const item = await only(w);
  await at(w, item.due - Q.LEAD_MS);
  const failed = await only(w);
  assert.equal(failed.state, "failed");
  assert.deepEqual(failed.error, { message: "WhatsApp changed its menu", code: "moved" });
  assert.ok(w.notes.shown.has(`sched|failed|${item.id}`));
  assert.ok(w.place.releases >= 1);
});

test("while the person uses WhatsApp the run waits a minute at a time, then asks after ten minutes", async () => {
  const w = world();
  w.place.using = true;
  await schedule(w);
  const item = await only(w);
  await at(w, item.due - Q.LEAD_MS);
  let row = await only(w);
  assert.equal(row.state, "waiting");
  assert.equal(row.waitUntil, w.clock.t + MIN);
  assert.equal(w.alarms.set.get("sched-next").when, row.waitUntil);
  for (let i = 2; i < SnipSchedule.WAIT_TRIES; i++) {
    await at(w, row.waitUntil);
    row = await only(w);
    assert.equal(row.state, "waiting");
    assert.equal(row.attempts, i);
  }
  await at(w, row.waitUntil);
  row = await only(w);
  assert.equal(row.state, "asked");
  assert.equal(w.place.calls.length, 0, "never loaded while the person was in WhatsApp");
  const notice = w.notes.shown.get(`sched|asked|${item.id}`);
  assert.deepEqual(notice.buttons, [{ title: "Post it now" }]);
  assert.equal(w.badges.at(-1), 1);
  // The person presses the notification: today's model, WhatsApp brought forward.
  w.place.using = false;
  await w.s.clicked(`sched|asked|${item.id}`);
  await flush(w);
  assert.equal(w.place.calls.length, 1);
  assert.equal(w.place.calls[0].manual, true);
  assert.equal((await only(w)).state, "prepared");
});

test("a run that needs the person asks with a notification whose button posts it", async () => {
  const w = world();
  w.place.results.push({ ok: false, code: "ask", rung: "S4", ms: 300 });
  await schedule(w);
  const item = await only(w);
  await at(w, item.due - Q.LEAD_MS);
  assert.equal((await only(w)).state, "asked");
  await w.s.button(`sched|asked|${item.id}`, 0);
  await flush(w);
  assert.equal(w.place.calls.at(-1).manual, true);
  assert.equal((await only(w)).state, "prepared");
});

test("prepared becomes done once the composer has gone, its clip deleted and its row in history", async () => {
  const w = world();
  await schedule(w);
  const item = await only(w);
  await at(w, item.due - Q.LEAD_MS);
  assert.equal((await only(w)).state, "prepared");
  w.place.using = true;   // the composer is still open
  await at(w, item.due + 15 * MIN, "sched-sweep");
  assert.equal((await only(w)).state, "prepared");
  w.place.using = false;
  await at(w, item.due + 30 * MIN, "sched-sweep");
  assert.equal((await items(w)).length, 0);
  assert.deepEqual(w.custody.dropped, [item.id]);
  const history = w.store.data.schedHistory;
  assert.equal(history[0].id, item.id);
  assert.equal(history[0].outcome, "prepared");
  assert.ok(w.place.releases >= 1);
  assert.equal(w.alarms.set.has("sched-sweep"), false, "nothing pending, no sweep");
});

test("a composer nobody closes is done after a day all the same", async () => {
  const w = world();
  await schedule(w);
  const item = await only(w);
  await at(w, item.due - Q.LEAD_MS);
  w.place.using = true;
  await at(w, item.due + SnipSchedule.PREPARED_HOLD_MS, "sched-sweep");
  assert.equal((await items(w)).length, 0);
});

test("a run woken more than the catch up window late is missed, notified, and not run", async () => {
  const w = world();
  await schedule(w);
  const item = await only(w);
  w.clock.t = item.due + 31 * MIN;
  await w.s.wake();
  await flush(w);
  const row = await only(w);
  assert.equal(row.state, "missed");
  assert.equal(w.place.calls.length, 0);
  assert.deepEqual(w.notes.shown.get(`sched|missed|${item.id}`).buttons, [{ title: "Post it now" }]);
  // Woken a little late is still a run.
  const v = world();
  await schedule(v);
  const other = await only(v);
  v.clock.t = other.due + 10 * MIN;
  await v.s.wake();
  await flush(v);
  assert.equal((await only(v)).state, "prepared");
});

// -- a worker stopped at every transition ----------------------------------------------------

test("stopped while the clip came down: a new worker carries on with the stored grant", async () => {
  const w = world();
  w.custody.hang = true;
  const pending = schedule(w).catch(() => {});
  await flush(w);
  assert.equal((await only(w)).state, "holding");
  const v = w.restart();
  w.custody.hang = false;
  await v.s.wake();
  await flush(v);
  const row = await only(v);
  assert.equal(row.state, "scheduled");
  assert.equal(row.custody, "local");
  void pending;
});

test("stopped while holding past the grant's life: failed, never resumed", async () => {
  const w = world();
  w.custody.hang = true;
  schedule(w, 4 * 3600000).catch(() => {});
  await flush(w);
  w.custody.hang = false;
  const v = w.restart();
  v.clock.t = T0 + 2 * 3600000 + 1;
  const before = w.custody.fetches;
  await v.s.wake();
  await flush(v);
  assert.equal((await only(v)).state, "failed");
  assert.equal(w.custody.fetches, before);
});

test("stopped after scheduling: the next worker prewarms and runs on time", async () => {
  const w = world();
  await schedule(w);
  const item = await only(w);
  const v = w.restart();
  v.alarms.set.clear();   // Chrome dropped the alarms over a restart
  v.clock.t = item.due - Q.PREWARM_MS;
  await v.s.wake();
  await flush(v);
  assert.equal((await only(v)).state, "prewarmed");
  assert.ok(v.alarms.set.has("sched-next") && v.alarms.set.has("sched-sweep"), "alarms rebuilt");
  const u = v.restart();
  u.clock.t = item.due - Q.LEAD_MS;
  await u.s.alarm("sched-next");
  await flush(u);
  assert.equal((await only(u)).state, "prepared");
});

test("stopped mid run: the next worker runs it again from the top", async () => {
  const w = world();
  w.place.results.push("hang");
  await schedule(w);
  const item = await only(w);
  await startRun(w, item.due - Q.LEAD_MS);
  assert.equal((await only(w)).state, "running");
  const v = w.restart();
  v.clock.t += 20000;
  await v.s.wake();
  await flush(v);
  assert.equal(v.place.calls.length, 1);
  assert.equal(v.place.calls[0].manual, false);
  assert.equal((await only(v)).state, "prepared");
});

test("stopped mid run when the first load had opened the composer: it waits, it does not load twice", async () => {
  const w = world();
  w.place.results.push("hang");
  await schedule(w);
  const item = await only(w);
  await startRun(w, item.due - Q.LEAD_MS);
  const v = w.restart();
  v.place.results.push({ ok: false, code: "composer-open", rung: null, ms: 10 });
  await v.s.wake();
  await flush(v);
  assert.equal((await only(v)).state, "waiting");
});

test("stopped while waiting: the next worker looks again at the stored time", async () => {
  const w = world();
  w.place.using = true;
  await schedule(w);
  const item = await only(w);
  await at(w, item.due - Q.LEAD_MS);
  const waiting = await only(w);
  const v = w.restart();
  v.clock.t = waiting.waitUntil;
  await v.s.alarm("sched-next");
  await flush(v);
  assert.equal((await only(v)).state, "prepared");
});

test("stopped while prepared: the sweep of a new worker closes it", async () => {
  const w = world();
  await schedule(w);
  const item = await only(w);
  await at(w, item.due - Q.LEAD_MS);
  const v = w.restart();
  v.clock.t = item.due + 20 * MIN;
  await v.s.alarm("sched-sweep");
  await flush(v);
  assert.equal((await items(v)).length, 0);
});

test("stopped inside Undo's ten seconds: the deadline is stored and kept by the next worker (E11)", async () => {
  const w = world();
  await schedule(w);
  const port = fakePort();
  w.s.attach(port);
  await flush(w);
  const item = await only(w);
  const answer = await port.ask("cancel", { sid: item.id, rev: item.rev });
  assert.equal(answer.ok, true);
  assert.ok(answer.result.undo);
  const cancelled = await only(w);
  assert.equal(cancelled.state, "cancelled");
  assert.equal(cancelled.deleteAfter, T0 + Q.UNDO_MS);
  assert.equal(w.alarms.set.get("sched-next").when, T0 + 30000, "no alarm sooner than Chrome allows");
  const v = w.restart();
  v.clock.t = T0 + Q.UNDO_MS;
  await v.s.alarm("sched-next");
  await flush(v);
  assert.equal((await items(v)).length, 0);
  assert.deepEqual(v.custody.dropped, [item.id]);
  assert.equal(v.store.data.schedHistory[0].state, "cancelled");
});

// -- the queue page's commands ------------------------------------------------------------------

test("Undo within ten seconds puts a cancelled post back; after them it is too late", async () => {
  const w = world();
  await schedule(w);
  const port = fakePort();
  w.s.attach(port);
  const item = await only(w);
  const cancelled = await port.ask("cancel", { sid: item.id, rev: item.rev });
  const back = await port.ask("restore", { snap: cancelled.result.undo });
  assert.equal(back.ok, true);
  const row = await only(w);
  assert.equal(row.state, "scheduled");
  assert.equal(row.deleteAfter, null);
  const again = await port.ask("cancel", { sid: row.id, rev: row.rev });
  await at(w, T0 + Q.UNDO_MS + 1);
  const late = await port.ask("restore", { snap: again.result.undo });
  assert.equal(late.ok, false);
  assert.equal(late.error.code, "gone");
});

test("a change made against an old revision is refused and the page is sent the queue as it is", async () => {
  const w = world();
  await schedule(w);
  const port = fakePort();
  w.s.attach(port);
  await flush(w);
  const item = await only(w);
  const first = await port.ask("caption", { sid: item.id, rev: item.rev, caption: "New words" });
  assert.equal(first.ok, true);
  assert.equal(first.result.item.caption, "New words");
  assert.ok(first.result.undo);
  const pushes = port.pushes().length;
  const stale = await port.ask("retime", { sid: item.id, rev: item.rev, due: item.due + 60 * MIN });
  assert.equal(stale.ok, false);
  assert.equal(stale.error.code, "conflict");
  await flush(w);
  assert.ok(port.pushes().length > pushes);
  const fresh = await only(w);
  assert.equal(fresh.due, item.due);
  const moved = await port.ask("retime", { sid: item.id, rev: fresh.rev, due: item.due + 60 * MIN });
  assert.equal(moved.ok, true);
  assert.equal((await only(w)).due, item.due + 60 * MIN);
  assert.ok(moved.result.note);
});

test("every change pushes the whole state to the open pages", async () => {
  const w = world();
  const port = fakePort();
  w.s.attach(port);
  await flush(w);
  const first = port.pushes()[0].state;
  assert.deepEqual(Object.keys(first).sort(),
    ["history", "items", "needsYou", "now", "overdue", "paused", "quiet", "settings", "usage"]);
  assert.deepEqual(first.quiet, { works: true, best: "S1", tested: T0 });
  await schedule(w);
  const last = port.pushes().at(-1).state;
  assert.equal(last.items.length, 1);
  assert.equal(last.usage.bytes, w.custody.size);
  assert.equal(last.usage.pendingLimit, 30);
  assert.equal(last.settings.quietOn, false);
  assert.equal(last.settings.gapMinutes, 180);
});

test("pause stops runs, not prewarm; resume asks what to do with what fell due", async () => {
  const w = world();
  await schedule(w);
  const port = fakePort();
  w.s.attach(port);
  const item = await only(w);
  assert.equal((await port.ask("pause")).ok, true);
  await at(w, item.due - Q.PREWARM_MS);
  assert.equal((await only(w)).state, "prewarmed", "prewarm carries on while paused (FR-8)");
  assert.equal(w.alarms.set.has("sched-next"), false, "no run alarm while paused");
  await at(w, item.due + 5 * MIN);
  assert.equal(w.place.calls.length, 0);
  const asked = await port.ask("resume", {});
  assert.equal(asked.ok, false);
  assert.equal(asked.error.code, "choice");
  const later = await port.ask("resume", { choice: "later" });
  assert.equal(later.ok, true);
  const row = await only(w);
  assert.equal(row.due, item.due + (item.due + 5 * MIN - T0));
  assert.equal(w.store.data.sched.paused, null);
  // Nothing overdue: Resume is a plain unpause, whatever choice the page sends.
  await port.ask("pause");
  assert.equal((await port.ask("resume", { choice: "post" })).ok, true);
  assert.equal(w.store.data.sched.paused, null);
});

test("resume with missed marks what fell due as missed", async () => {
  const w = world();
  await schedule(w);
  const port = fakePort();
  w.s.attach(port);
  const item = await only(w);
  await port.ask("pause");
  await at(w, item.due + MIN);
  await port.ask("resume", { choice: "missed" });
  assert.equal((await only(w)).state, "missed");
});

test("Post now loads it with WhatsApp brought forward; Post next now takes the earliest", async () => {
  const w = world();
  await schedule(w);
  await schedule(w, 60 * MIN, { stem: "clip_two" });
  const port = fakePort();
  w.s.attach(port);
  const next = await port.ask("post-next-now");
  assert.equal(next.ok, true);
  await flush(w);
  const [first, second] = Q.sorted(await items(w));
  assert.equal(first.state, "prepared");
  assert.equal(second.state, "scheduled");
  assert.equal(w.place.calls[0].manual, true);
  const busy = await port.ask("post-now", { sid: first.id });
  assert.equal(busy.ok, false);
  assert.equal(busy.error.code, "locked");
});

test("settings are checked, written to the shared settings object, and test-quiet asks place.js", async () => {
  const w = world();
  const port = fakePort();
  w.s.attach(port);
  const bad = await port.ask("settings", { changes: { quietStart: "25:00" } });
  assert.equal(bad.ok, false);
  const good = await port.ask("settings", { changes: { bringForward: true, gapMinutes: 60 } });
  assert.equal(good.ok, true);
  assert.equal(w.store.data.settings.token, "kept", "the renderer settings are left alone");
  assert.equal(w.store.data.settings.gapMinutes, 60);
  const quiet = await port.ask("test-quiet");
  assert.equal(quiet.result.rung, "S1");
  assert.equal((await port.ask("nope")).error.code, "unknown");
});

test("the page's Up next is the next three, the count and what needs the person", async () => {
  const w = world();
  for (const [i, stem] of ["a1", "a2", "a3", "a4"].entries()) await schedule(w, (10 + i * 10) * MIN, { stem });
  const peek = await w.s.peek();
  assert.equal(peek.count, 4);
  assert.equal(peek.next.length, 3);
  assert.deepEqual(Object.keys(peek.next[0]).sort(), ["caption", "due", "id", "word"]);
  assert.equal(peek.needsYou, 0);
});

// -- time ---------------------------------------------------------------------------------------

test("a due time is an instant: a zone change or a daylight saving change does not move it", async () => {
  try {
    process.env.TZ = "America/New_York";
    const w = world();
    // 05:00 UTC on 1 Nov 2026 is 01:00 in New York, an hour before its clocks go back.
    w.clock.t = Date.UTC(2026, 10, 1, 5, 0, 0);
    await schedule(w, 2 * 3600000);
    const item = await only(w);
    assert.equal(item.due, Date.UTC(2026, 10, 1, 7, 0, 0));
    process.env.TZ = "Asia/Kolkata";
    await at(w, item.due - Q.LEAD_MS - MIN);
    assert.equal(w.place.calls.length, 0);
    await at(w, item.due - Q.LEAD_MS);
    assert.equal(w.place.calls.length, 1);
    assert.equal((await only(w)).due, Date.UTC(2026, 10, 1, 7, 0, 0));
  } finally {
    process.env.TZ = "UTC";
  }
});

test("lost alarms are rebuilt on every wake, and an alarm in the past is never set", async () => {
  const w = world();
  await schedule(w);
  w.alarms.set.clear();
  await w.s.wake();
  assert.ok(w.alarms.set.has("sched-next"));
  assert.ok(w.alarms.set.has("sched-sweep"));
  assert.ok(w.alarms.set.get("sched-next").when >= w.clock.t + 30000);
});

// -- the worker: alarms go to their owner by name (E1) ----------------------------------------------

test("a schedule alarm never drives the clip job, and the job's alarm never wakes the schedule", async () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "sw.js"), "utf8");
  const listeners = {};
  const on = (name) => ({ addListener: (fn) => { listeners[name] = fn; } });
  let jobReads = 0;
  const alarmsSeen = [];
  const local = {
    get: async (key) => { if (key === "job") jobReads += 1; return {}; },
    set: async () => {}, remove: async () => {},
  };
  const chrome = {
    storage: { local, session: local, onChanged: on("changed") },
    alarms: { onAlarm: on("alarm"), get: async () => null, create: async () => {}, clear: async () => true },
    runtime: {
      onInstalled: on("installed"), onStartup: on("startup"), onConnect: on("connect"),
      onConnectExternal: on("external"), onMessage: on("message"), id: "ext",
      getManifest: () => ({ version: "2.1.0" }), getURL: (p) => `chrome-extension://ext/${p}`,
    },
    action: { onClicked: on("action"), setBadgeText: async () => {}, setBadgeBackgroundColor: async () => {} },
    notifications: { onClicked: on("nclick"), onButtonClicked: on("nbutton") },
    contextMenus: { onClicked: on("menu"), removeAll: (cb) => cb(), create: () => {} },
    tabs: { query: async () => [] },
  };
  const scheduler = {
    alarm: async (name) => { alarmsSeen.push(name); },
    wake: async () => {}, attach: () => {}, changed: async () => {}, clicked: async () => {}, button: async () => {},
  };
  const sandbox = {
    chrome, console, setTimeout, clearTimeout, AbortController, AbortSignal, URL, Blob,
    importScripts: () => {
      sandbox.CONFIG = { site: "http://127.0.0.1:8790" };
      sandbox.SnipQueue = Q;
      sandbox.SnipCustody = { PREFIX: "sched:", make: () => ({}) };
      sandbox.SnipPlace = {};
      sandbox.SnipSchedule = { make: () => scheduler, Refusal: SnipSchedule.Refusal };
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename: "sw.js" });
  await new Promise((resolve) => setTimeout(resolve, 20));
  const settledReads = jobReads;
  listeners.alarm({ name: "sched-next" });
  listeners.alarm({ name: "sched-sweep" });
  listeners.alarm({ name: "somebody-else" });
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(jobReads, settledReads, "the job loop was not driven");
  assert.deepEqual(alarmsSeen, ["sched-next", "sched-sweep"]);
  listeners.alarm({ name: "wastatus" });
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.ok(jobReads > settledReads, "the job's own alarm still drives it");
  assert.deepEqual(alarmsSeen, ["sched-next", "sched-sweep"]);
});

// -- found by the independent review, 2026-10-31 ------------------------------------------

test("Undo of a resume puts the pause back, so the rows it restores do not run at once", async () => {
  for (const choice of ["missed", "later"]) {
    const w = world();
    const port = fakePort();
    w.s.attach(port);
    await schedule(w, 10 * MIN);
    await port.ask("pause");
    await at(w, T0 + 20 * MIN);
    const resumed = await port.ask("resume", { choice });
    assert.equal(resumed.ok, true);
    const undone = await port.ask("restore", { snap: resumed.result.undo });
    assert.equal(undone.ok, true);
    assert.ok(w.store.data.sched.paused, choice);
    await at(w, T0 + 21 * MIN);
    assert.equal(w.place.calls.length, 0, choice);
  }
});

// A prewarm held open, so a page can act while the wake that chose the run waits on it.
async function heldPrewarm(w) {
  const gate = {};
  w.place.prewarm = async () => { await new Promise((resolve) => { gate.open = resolve; }); return w.place.warm; };
  w.clock.t = T0 + 9 * MIN;   // inside the lead: prewarm and run chosen by one wake
  gate.ticking = w.s.alarm("sched-next");
  for (let i = 0; i < 20; i++) await new Promise((resolve) => setImmediate(resolve));
  assert.ok(gate.open, "prewarm in flight");
  return gate;
}

test("a Pause pressed while the prewarm is in flight stops the run it was about to start", async () => {
  const w = world();
  const port = fakePort();
  w.s.attach(port);
  await schedule(w, 10 * MIN);
  const gate = await heldPrewarm(w);
  await port.ask("pause");
  gate.open();
  await gate.ticking;
  await flush(w);
  assert.equal(w.place.calls.length, 0);
  assert.equal((await only(w)).state, "prewarmed");
});

test("a new time set while the prewarm is in flight is the time it runs at", async () => {
  const w = world();
  const port = fakePort();
  w.s.attach(port);
  await schedule(w, 10 * MIN);
  const gate = await heldPrewarm(w);
  const row = await only(w);
  assert.equal((await port.ask("retime", { sid: row.id, rev: row.rev, due: T0 + 300 * MIN })).ok, true);
  gate.open();
  await gate.ticking;
  await flush(w);
  assert.equal(w.place.calls.length, 0);
  assert.equal((await only(w)).due, T0 + 300 * MIN);
  await at(w, T0 + 300 * MIN - Q.LEAD_MS);
  assert.equal(w.place.calls.length, 1);
});

test("cancelled while its clip came down, kept inside the Undo window, Undo: it runs at its time", async () => {
  const w = world();
  const port = fakePort();
  w.s.attach(port);
  let finish;
  const real = w.custody.fetch;
  w.custody.fetch = async (id, options) => { await new Promise((resolve) => { finish = resolve; }); return real(id, options); };
  const making = w.s.create({ stem: "clip_one", name: "c.mp4", caption: "x", mode: "card", due: T0 + 60 * MIN,
    action: "prepare" }, { grant: "g", url: "https://renderer.example.com/api/v1/clip?stem=clip_one" });
  for (let i = 0; i < 20; i++) await new Promise((resolve) => setImmediate(resolve));
  const row = await only(w);
  const cancelled = await port.ask("cancel", { sid: row.id, rev: row.rev });
  finish();
  await making.catch(() => {});
  await flush(w);
  assert.equal((await port.ask("restore", { snap: cancelled.result.undo })).ok, true);
  const back = await only(w);
  assert.equal(back.state, "scheduled");
  assert.equal(back.custody, "local");
  await at(w, T0 + 60 * MIN - Q.LEAD_MS);
  assert.equal((await only(w)).state, "prepared");
});

test("stopped after the clip reached WhatsApp: never loaded again, the person is told to look", async () => {
  const w = world();
  w.place.load = async (options) => {
    w.place.calls.push(options);
    options.onStep({ rung: "S0", step: "file" });
    return new Promise(() => {});
  };
  await schedule(w);
  const item = await only(w);
  await startRun(w, item.due - Q.LEAD_MS);
  for (let i = 0; i < 8; i++) await new Promise((resolve) => setImmediate(resolve));
  assert.equal((await only(w)).given, true);
  const v = w.restart();
  v.clock.t += 20000;
  await v.s.wake();
  await flush(v);
  const row = await only(v);
  assert.equal(row.state, "prepared");
  assert.equal(row.error.code, "given");
  assert.equal(v.place.calls.length, 0, "no second load");
  assert.ok(v.notes.shown.has(`sched|prepared|${item.id}`));
});

test("a reconcile that read an older queue never overwrites the newer next alarm", async () => {
  const w = world();
  const port = fakePort();
  w.s.attach(port);
  await schedule(w, 60 * MIN);
  const row = await only(w);
  // Hold the first alarm write, as a slow Chrome call would.
  const create = w.alarms.create.bind(w.alarms);
  let held = null;
  w.alarms.create = async (name, info) => {
    if (name === "sched-next" && !held) { await new Promise((resolve) => { held = resolve; }); }
    return create(name, info);
  };
  const first = port.ask("retime", { sid: row.id, rev: row.rev, due: T0 + 120 * MIN });
  for (let i = 0; i < 20; i++) await new Promise((resolve) => setImmediate(resolve));
  const second = (async () => {
    const fresh = await only(w);
    return port.ask("retime", { sid: row.id, rev: fresh.rev, due: T0 + 240 * MIN });
  })();
  for (let i = 0; i < 20; i++) await new Promise((resolve) => setImmediate(resolve));
  held();
  await first;
  await second;
  await flush(w);
  assert.equal((await only(w)).due, T0 + 240 * MIN);
  assert.equal(w.alarms.set.get("sched-next").when, T0 + 240 * MIN - Q.PREWARM_MS);
});

test("the same clip scheduled for another time while its first copy comes down is refused, not merged", async () => {
  const w = world();
  w.custody.hang = true;
  schedule(w, 60 * MIN).catch(() => {});
  await flush(w);
  await assert.rejects(schedule(w, 120 * MIN), (err) => err.code === "busy" && /another time/.test(err.message));
  assert.equal((await items(w)).length, 1);
  assert.equal((await only(w)).due, T0 + 60 * MIN);
  // Asking again for the same time carries on with the first.
  w.custody.hang = false;
  const again = await schedule(w, 60 * MIN);
  assert.equal((await items(w)).length, 1);
  assert.equal(again.answer.schedule.state, "scheduled");
});
