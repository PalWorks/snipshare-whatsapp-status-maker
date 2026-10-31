// place.js without Chrome: the order the ladder is walked in, the week a failing
// rung is left alone, the focus guard's judgement of whose change a focus event
// was, the clip handed over one acknowledged slice at a time, and the one load at a
// time rule. Two runs go through `create` with a fake Chrome, to show a quiet S0
// that never touches focus and an S2 whose stolen focus is put back and counted.
// None of this measures Chrome itself: which rungs work is Phase 0's question
// (docs/scheduling.md, Section 12). Run with `node --test src/test`.
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const place = require("../place.js");

const DAY = 86400000;
const NOW = 1_800_000_000_000;

test("with no record the quiet rungs are tried quietest first", () => {
  assert.deepEqual(place.order({ rungs: {} }, NOW), ["S0", "S1", "S2"]);
  assert.deepEqual(place.order(null, NOW), ["S0", "S1", "S2"]);
});

test("the ladder starts at the rung that worked, then the untried, then the failing", () => {
  const stats = { rungs: {
    S0: { wins: 0, fails: 1, streak: 1, lastFail: NOW - 1000 },
    S2: { wins: 4, fails: 0, streak: 0, lastWin: NOW - 1000 },
  } };
  assert.deepEqual(place.order(stats, NOW), ["S2", "S1", "S0"]);
});

test("a rung that failed three times running is skipped for a week, then tried again", () => {
  const rec = { wins: 2, fails: 3, streak: 3, lastFail: NOW - 6 * DAY };
  assert.equal(place.skipped(rec, NOW), true);
  assert.deepEqual(place.order({ rungs: { S0: rec } }, NOW), ["S1", "S2"]);
  assert.equal(place.skipped(rec, NOW + 2 * DAY), false);
  assert.deepEqual(place.order({ rungs: { S0: rec } }, NOW + 2 * DAY), ["S1", "S2", "S0"]);
  assert.equal(place.skipped({ ...rec, streak: 2 }, NOW), false);
});

test("recording three failures puts a rung away, and a quiet success brings it back", () => {
  let stats = { rungs: {} };
  const frozen = JSON.stringify(stats);
  for (let i = 0; i < 3; i++) stats = place.record(stats, "S0", { ok: false }, NOW + i);
  assert.equal(JSON.stringify({ rungs: {} }), frozen, "the input is never changed");
  assert.equal(stats.rungs.S0.streak, 3);
  assert.equal(place.skipped(stats.rungs.S0, NOW + 10), true);
  stats = place.record(stats, "S0", { ok: true, quiet: true, ms: 8000 }, NOW + 8 * DAY);
  assert.equal(stats.rungs.S0.streak, 0);
  assert.equal(stats.rungs.S0.ms, 8000);
  stats = place.record(stats, "S0", { ok: true, quiet: true, ms: 4000 }, NOW + 9 * DAY);
  assert.equal(stats.rungs.S0.ms, 7000, "time is a running average, weighted to the past");
});

test("a load that moved focus is a success for the run but a failure for the rung", () => {
  const stats = place.record({ rungs: {} }, "S2", { ok: true, quiet: false, moved: true, ms: 9000 }, NOW);
  assert.equal(stats.rungs.S2.wins, 0);
  assert.equal(stats.rungs.S2.fails, 1);
  assert.equal(stats.rungs.S2.moved, 1);
});

test("a placement test without a clip counts only a focus move against the rung", () => {
  let stats = place.record({ rungs: {} }, "S1", { placedOnly: true, moved: false, test: true }, NOW);
  assert.equal(stats.rungs.S1.placed, 1);
  assert.equal(stats.rungs.S1.fails, 0);
  assert.equal(stats.tested, NOW);
  stats = place.record(stats, "S1", { placedOnly: true, moved: true, test: true }, NOW + 1);
  assert.equal(stats.rungs.S1.fails, 1);
});

test("the idle rung only when opted in, and bringing forward replaces asking", () => {
  assert.deepEqual(place.ladder({}, {}, NOW), ["S0", "S1", "S2", "S4"]);
  assert.deepEqual(place.ladder({}, { idleForward: true }, NOW), ["S0", "S1", "S2", "S3", "S4"]);
  assert.deepEqual(place.ladder({}, { bringForward: true }, NOW), ["S0", "S1", "S2", "S5"]);
  const allFailing = { rungs: Object.fromEntries(["S0", "S1", "S2"].map((r) =>
    [r, { fails: 3, streak: 3, lastFail: NOW - DAY }])) };
  assert.deepEqual(place.ladder(allFailing, {}, NOW), ["S4"]);
});

test("the queue is told whether quiet posting works here", () => {
  assert.deepEqual(place.summary({ rungs: {} }, NOW), { works: null, best: null, tested: null });
  const failing = place.record({ rungs: {} }, "S0", { ok: false }, NOW);
  assert.equal(place.summary(failing, NOW).works, false);
  const working = place.record(failing, "S2", { ok: true, quiet: true, ms: 5 }, NOW);
  assert.deepEqual(place.summary(working, NOW), { works: true, best: "S2", tested: NOW });
});

// -- the focus guard -----------------------------------------------------------------

const BEFORE = { windowId: 1, tabId: 11 };

test("a focus change just after our own call is ours and is put back", () => {
  const verdict = place.judge(BEFORE, [{ type: "window", windowId: 9, at: 1200 }],
                              [{ start: 1000, end: 1100 }]);
  assert.equal(verdict.moved, true);
  assert.equal(verdict.person, false);
  assert.deepEqual(verdict.undo, { windowId: 1, blur: null, tabId: null });
});

test("a change more than 1.5 s after our call is the person's and stays", () => {
  const verdict = place.judge(BEFORE, [{ type: "window", windowId: 9, at: 2700 }],
                              [{ start: 1000, end: 1100 }]);
  assert.equal(verdict.moved, false);
  assert.equal(verdict.person, true);
  assert.equal(verdict.undo, null);
});

test("while our call is still running every change is ours", () => {
  const verdict = place.judge(BEFORE, [{ type: "tab", windowId: 1, tabId: 50, at: 60000 }],
                              [{ start: 1000, end: null }]);
  assert.deepEqual(verdict.undo, { windowId: null, blur: null, tabId: 11 });
});

test("when the person moves after us, their choice stands", () => {
  const verdict = place.judge(BEFORE, [
    { type: "window", windowId: 9, at: 1200 },
    { type: "window", windowId: 3, at: 5000 },
  ], [{ start: 1000, end: 1100 }]);
  assert.equal(verdict.moved, true, "the run's move is still recorded against the rung");
  assert.equal(verdict.person, true);
  assert.equal(verdict.undo, null);
});

test("a tab activated in another window, such as the helper, moves nothing the person sees", () => {
  const verdict = place.judge(BEFORE, [{ type: "tab", windowId: 9, tabId: 70, at: 1050 }],
                              [{ start: 1000, end: 1100 }]);
  assert.equal(verdict.moved, false);
  assert.equal(verdict.undo, null);
});

test("our undo, being our own call too, settles the matter", () => {
  const verdict = place.judge(BEFORE, [
    { type: "window", windowId: 9, at: 1200 },
    { type: "window", windowId: 1, at: 1300 },
  ], [{ start: 1000, end: 1100 }, { start: 1250, end: 1260 }]);
  assert.equal(verdict.moved, true);
  assert.equal(verdict.undo, null);
});

test("with no Chrome window in focus before, a window we raise is unfocused again", () => {
  const verdict = place.judge({ windowId: place.NONE, tabId: null },
                              [{ type: "window", windowId: 9, at: 1200 }], [{ start: 1000, end: 1100 }]);
  assert.deepEqual(verdict.undo, { windowId: place.NONE, blur: 9, tabId: null });
});

// -- the clip handover -----------------------------------------------------------------

function bytesOf(n) {
  const out = new Uint8Array(n);
  for (let i = 0; i < n; i++) out[i] = (i * 31 + 7) & 0xff;
  return out;
}

test("each slice waits for the bridge's acknowledgement of the one before", async () => {
  const size = place.SLICE * 2 + 1000;
  const source = bytesOf(size);
  const blob = new Blob([source]);
  let reads = 0;
  const clip = { size: blob.size, slice: (a, b) => { reads += 1; assert.ok(b - a <= place.SLICE); return blob.slice(a, b); } };
  const sent = [];
  const port = { postMessage: (message) => sent.push(message) };
  const pending = new Map();
  const waitAck = (n) => new Promise((resolve) => pending.set(n, resolve));
  const turn = () => new Promise((resolve) => setImmediate(resolve));

  const done = place.handover(port, clip, { name: "a.mp4", caption: "hi" }, waitAck);
  await turn();
  assert.deepEqual(sent.map((m) => m.cmd), ["start", "chunk"]);
  assert.equal(sent[0].size, size);
  await turn();
  assert.equal(sent.length, 2, "nothing more is sent until slice 0 is acknowledged");
  assert.equal(reads, 1, "nor read");
  pending.get(0)();
  await turn(); await turn();
  assert.deepEqual(sent.map((m) => m.cmd), ["start", "chunk", "chunk"]);
  pending.get(1)();
  await turn(); await turn();
  pending.get(2)();
  assert.equal(await done, true);
  assert.deepEqual(sent.map((m) => m.cmd), ["start", "chunk", "chunk", "chunk", "end"]);
  assert.deepEqual(sent.filter((m) => m.cmd === "chunk").map((m) => m.n), [0, 1, 2]);
  const back = Buffer.concat(sent.filter((m) => m.cmd === "chunk").map((m) => Buffer.from(m.b64, "base64")));
  assert.deepEqual(new Uint8Array(back), source);
});

test("a port that goes mid handover stops it", async () => {
  const blob = new Blob([bytesOf(place.SLICE + 10)]);
  const sent = [];
  const port = { postMessage: (message) => sent.push(message) };
  const done = place.handover(port, blob, { name: "a.mp4", caption: "" }, () => Promise.reject(new Error("closed")));
  await assert.rejects(done, /closed/);
  assert.equal(sent.filter((m) => m.cmd === "chunk").length, 1);
  assert.equal(sent.some((m) => m.cmd === "end"), false);
});

// -- one at a time, and two runs over a fake Chrome ---------------------------------------

test("the lock admits one holder", () => {
  const lock = place.makeLock();
  assert.equal(lock.take(), true);
  assert.equal(lock.take(), false);
  assert.equal(lock.held(), true);
  lock.free();
  assert.equal(lock.take(), true);
});

function events() {
  const fns = new Set();
  return { addListener: (f) => fns.add(f), removeListener: (f) => fns.delete(f), fire: (...a) => [...fns].forEach((f) => f(...a)) };
}

// A Chrome with one focused window (1, active tab 11) and whatever tabs are given.
// The WhatsApp tab's port behaves as wa-bridge.js does: it acknowledges each chunk,
// says when the file is in, and answers with the caption it was given.
function fakeChrome(tabs, options = {}) {
  const log = [];
  const store = {};
  const got = [];
  let nextWindow = 9;
  const chrome = {
    log, store, got,
    storage: { local: {
      get: async (key) => ({ [key]: store[key] }),
      set: async (obj) => { Object.assign(store, JSON.parse(JSON.stringify(obj))); },
    } },
    tabs: {
      onActivated: events(),
      query: async (q) => {
        if (q.url) return tabs.filter((t) => t.url.startsWith("https://web.whatsapp.com/"));
        if (q.active) return tabs.filter((t) => t.active && t.windowId === q.windowId);
        if (q.windowId != null) return tabs.filter((t) => t.windowId === q.windowId);
        return tabs;
      },
      get: async (id) => { const t = tabs.find((x) => x.id === id); if (!t) throw new Error("no tab"); return t; },
      update: async (id, props) => { log.push(["tabs.update", id, props]); return tabs.find((t) => t.id === id); },
      create: async (props) => {
        log.push(["tabs.create", props]);
        if (!options.canCreate) throw new Error("not in this test");
        const t = { id: 90 + tabs.length, windowId: props.windowId ?? 1, index: 9, active: !!props.active,
                    url: props.url, status: "complete" };
        tabs.push(t);
        return t;
      },
      remove: async (id) => { log.push(["tabs.remove", id]); tabs.splice(tabs.findIndex((t) => t.id === id), 1); },
      reload: async (id) => { log.push(["tabs.reload", id]); },
      move: async (id, props) => {
        log.push(["tabs.move", id, props]);
        if (options.moveFails) throw new Error("cannot move");
        const t = tabs.find((x) => x.id === id); t.windowId = props.windowId; t.index = props.index;
      },
      connect: (tabId) => {
        const fromBridge = events();
        const disconnect = events();
        let size = 0;
        const reply = (m) => setImmediate(() => fromBridge.fire(m));
        return {
          onMessage: fromBridge, onDisconnect: disconnect,
          disconnect: () => log.push(["port.disconnect", tabId]),
          postMessage: (m) => {
            if (m.cmd === "start") { size = m.size; chrome.caption = m.caption; }
            else if (m.cmd === "chunk") { got.push(Buffer.from(m.b64, "base64")); reply({ ack: m.n }); }
            else if (m.cmd === "end") {
              if (options.answer) { reply({ result: options.answer }); return; }
              reply({ step: "file" });
              const total = got.reduce((n, b) => n + b.length, 0);
              reply({ result: total === size ? { ok: true, caption: chrome.caption } : { ok: false, code: "failed" } });
            }
          },
        };
      },
    },
    windows: {
      onFocusChanged: events(),
      getLastFocused: async () => ({ id: 1, focused: true }),
      get: async (id) => ({ id }),
      update: async (id, props) => { log.push(["windows.update", id, props]); },
      remove: async (id) => { log.push(["windows.remove", id]); },
      create: async (props) => {
        const id = nextWindow++;
        log.push(["windows.create", props]);
        const t = tabs.find((x) => x.id === props.tabId);
        if (t) { t.windowId = id; t.index = 0; }
        // A window manager that ignores `focused: false`.
        if (options.stealFocus) chrome.windows.onFocusChanged.fire(id);
        return { id };
      },
    },
    scripting: {
      executeScript: async ({ func, files }) => {
        log.push(["executeScript", files || "probe"]);
        if (options.hang) return new Promise(() => {});
        return [{ result: func ? { signedIn: !options.signedOut, composer: false } : undefined }];
      },
    },
  };
  return chrome;
}

function runner(chrome, step = 10, callMs) {
  let clock = NOW;
  return place.create({ chrome, now: () => (clock += step), sleep: async () => {}, callMs });
}

test("a quiet S0 run leaves focus alone, keeps the tab from being discarded, and is recorded", async () => {
  const tabs = [
    { id: 11, windowId: 1, index: 0, active: true, url: "https://www.youtube.com/", status: "complete" },
    { id: 20, windowId: 1, index: 1, active: false, url: "https://web.whatsapp.com/", status: "complete" },
  ];
  const chrome = fakeChrome(tabs);
  const snip = runner(chrome);
  const clip = new Blob([bytesOf(place.SLICE + 5)]);
  const steps = [];
  const result = await snip.load({ clip, name: "a.mp4", caption: "Hello", manual: false, settings: {},
                                   onStep: (s) => steps.push(s) });
  assert.equal(result.ok, true, JSON.stringify(result));
  assert.equal(result.rung, "S0");
  assert.equal(result.caption, "Hello");
  assert.equal(result.focusMoved, false);
  assert.deepEqual(new Uint8Array(Buffer.concat(chrome.got)), bytesOf(place.SLICE + 5));
  assert.ok(steps.some((s) => s.rung === "S0" && s.step === "file"));
  const updates = chrome.log.filter((e) => e[0] === "tabs.update" || e[0] === "windows.update");
  assert.deepEqual(updates, [["tabs.update", 20, { autoDiscardable: false }]], "nothing brought forward");
  assert.equal(chrome.store.placeStats.rungs.S0.wins, 1);
  assert.equal(chrome.store.placeStats.held, 20);
  assert.equal(snip.busy(), false);
  assert.deepEqual(await snip.stats(), { works: true, best: "S0", tested: chrome.store.placeStats.last });

  await snip.release();
  assert.deepEqual(chrome.log.at(-1), ["tabs.update", 20, { autoDiscardable: true }]);
  assert.equal(chrome.store.placeStats.held, undefined);
});

test("S2 moves the one WhatsApp tab and back, and puts back the focus the helper took", async () => {
  const tabs = [
    { id: 11, windowId: 1, index: 0, active: true, url: "https://www.youtube.com/", status: "complete" },
    { id: 20, windowId: 2, index: 3, active: false, url: "https://web.whatsapp.com/", status: "complete" },
    { id: 21, windowId: 2, index: 0, active: true, url: "https://www.youtube.com/", status: "complete" },
  ];
  const chrome = fakeChrome(tabs, { stealFocus: true });
  chrome.store.placeStats = { rungs: { S0: { wins: 0, fails: 3, streak: 3, lastFail: NOW } } };
  const snip = runner(chrome);
  const result = await snip.load({ clip: new Blob([bytesOf(1000)]), name: "a.mp4", caption: "", manual: false,
                                   settings: {} });
  assert.equal(result.rung, "S2");
  assert.equal(result.ok, true, "the composer is ready, so the run is not lost");
  assert.equal(result.focusMoved, true);
  assert.equal(chrome.log.some((e) => e[0] === "tabs.create"), false, "never a second WhatsApp tab");
  const created = chrome.log.find((e) => e[0] === "windows.create")[1];
  assert.equal(created.tabId, 20);
  assert.equal(created.focused, false);
  assert.ok(chrome.log.some((e) => e[0] === "windows.update" && e[1] === 1 && e[2].focused === true),
            "focus is given back to the person's window");
  assert.deepEqual(chrome.log.find((e) => e[0] === "tabs.move"), ["tabs.move", 20, { windowId: 2, index: 3 }]);
  assert.deepEqual(tabs[1].windowId, 2);
  const rec = chrome.store.placeStats.rungs.S2;
  assert.equal(rec.wins, 0);
  assert.equal(rec.moved, 1);
});

test("a second load while one is in flight is refused as busy, manual or not", async () => {
  let open;
  const gate = new Promise((resolve) => { open = resolve; });
  const chrome = fakeChrome([]);
  chrome.tabs.query = async () => { await gate; return []; };
  const snip = runner(chrome);
  const first = snip.load({ clip: new Blob([bytesOf(10)]), name: "a.mp4", manual: true });
  assert.equal(snip.busy(), true);
  const second = await snip.load({ clip: new Blob([bytesOf(10)]), name: "b.mp4", manual: false, settings: {} });
  assert.equal(second.ok, false);
  assert.equal(second.code, "busy");
  assert.equal((await snip.testQuiet()).code, "busy");
  open();
  const ended = await first;
  assert.equal(ended.ok, false);
  assert.equal(snip.busy(), false);
});

test("the person using WhatsApp holds a scheduled run back", async () => {
  const tabs = [{ id: 20, windowId: 1, index: 0, active: true, url: "https://web.whatsapp.com/", status: "complete" }];
  const chrome = fakeChrome(tabs);
  chrome.idle = { queryState: async () => "active" };
  const snip = runner(chrome);
  const result = await snip.load({ clip: new Blob([bytesOf(10)]), name: "a.mp4", manual: false, settings: {} });
  assert.equal(result.code, "in-use");
  assert.equal(chrome.log.some((e) => e[0] === "executeScript" && e[1] !== "probe"), false);
});

// -- fixes after the 2026-10-31 review and headless smoke test ------------------------

const S0_AWAY = () => ({ rungs: { S0: { wins: 0, fails: 3, streak: 3, lastFail: NOW } } });

test("S2 is skipped when WhatsApp is alone in its window, which would close on the way out", async () => {
  const tabs = [
    { id: 11, windowId: 1, index: 0, active: true, url: "https://www.youtube.com/", status: "complete" },
    { id: 20, windowId: 2, index: 0, active: true, url: "https://web.whatsapp.com/", status: "complete" },
  ];
  const chrome = fakeChrome(tabs);
  chrome.store.placeStats = S0_AWAY();
  const result = await runner(chrome).load({ clip: new Blob([bytesOf(10)]), name: "a.mp4", manual: false, settings: {} });
  assert.equal(result.code, "ask");
  assert.equal(chrome.log.some((e) => e[0] === "windows.create"), false);
});

test("the helper window is never closed while it still holds WhatsApp", async () => {
  const tabs = [
    { id: 11, windowId: 1, index: 0, active: true, url: "https://www.youtube.com/", status: "complete" },
    { id: 20, windowId: 2, index: 3, active: false, url: "https://web.whatsapp.com/", status: "complete" },
    { id: 21, windowId: 2, index: 0, active: true, url: "https://www.youtube.com/", status: "complete" },
  ];
  const chrome = fakeChrome(tabs, { moveFails: true });
  chrome.store.placeStats = S0_AWAY();
  const result = await runner(chrome).load({ clip: new Blob([bytesOf(10)]), name: "a.mp4", manual: false, settings: {} });
  assert.equal(result.rung, "S2");
  assert.equal(result.ok, true);
  assert.equal(chrome.log.some((e) => e[0] === "windows.remove"), false, "WhatsApp and its composer stay");
});

test("a hung call into the tab ends the load and frees the lock for the next Load", async () => {
  const tabs = [{ id: 20, windowId: 1, index: 0, active: false, url: "https://web.whatsapp.com/", status: "complete" }];
  const chrome = fakeChrome(tabs, { hang: true });
  const snip = runner(chrome, 5000, 20);
  const result = await snip.load({ clip: new Blob([bytesOf(10)]), name: "a.mp4", manual: true });
  assert.equal(result.ok, false);
  assert.equal(result.code, "signed-out");
  assert.equal(snip.busy(), false);
  const again = await snip.load({ clip: new Blob([bytesOf(10)]), name: "a.mp4", manual: true });
  assert.notEqual(again.code, "busy");
});

test("S1 closes the tab it opened when it failed before WhatsApp had the file", async () => {
  const tabs = [{ id: 11, windowId: 1, index: 0, active: true, url: "https://www.youtube.com/", status: "complete" }];
  const chrome = fakeChrome(tabs, { canCreate: true, answer: { ok: false, code: "failed", error: "x" } });
  // S2 is away too, so the walk ends after S1.
  chrome.store.placeStats = { rungs: { S2: { wins: 0, fails: 3, streak: 3, lastFail: NOW } } };
  const result = await runner(chrome).load({ clip: new Blob([bytesOf(10)]), name: "a.mp4", manual: false, settings: {} });
  assert.equal(result.code, "ask");
  const made = chrome.log.find((e) => e[0] === "tabs.create");
  assert.equal(made[1].active, false);
  assert.ok(chrome.log.some((e) => e[0] === "tabs.remove"), "the tab it opened is closed");
  assert.equal(tabs.some((t) => t.url.startsWith("https://web.whatsapp.com/")), false);
  assert.equal(chrome.store.placeStats.held, undefined);
});

test("S1 keeps the tab it opened when WhatsApp is signed out, so the person can scan there", async () => {
  const tabs = [{ id: 11, windowId: 1, index: 0, active: true, url: "https://www.youtube.com/", status: "complete" }];
  const chrome = fakeChrome(tabs, { canCreate: true, signedOut: true });
  const snip = runner(chrome, 5000);
  const result = await snip.load({ clip: new Blob([bytesOf(10)]), name: "a.mp4", manual: false, settings: {} });
  assert.equal(result.code, "signed-out");
  assert.equal(result.rung, "S1");
  assert.equal(chrome.log.some((e) => e[0] === "tabs.remove"), false);
  assert.equal(tabs.some((t) => t.url.startsWith("https://web.whatsapp.com/")), true);
});
