// queue.js: the schedule queue's rules, with no Chrome and no clock. Times are built
// with local Date constructors, because quiet hours and the words for a time are the
// runtime's local time; run with a fixed zone too, `TZ=Asia/Kolkata node --test
// src/test`, to be sure. Run with `node --test src/test`, or through pytest. See
// docs/scheduling.md Sections 4, 11 and 14.
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const Q = require("../queue.js");

const at = (y, mo, d, h = 0, mi = 0, s = 0) => new Date(y, mo - 1, d, h, mi, s).getTime();
const SEC = 1000;
const MIN = 60000;
const HOUR = 3600000;
// Saturday 1 November 2025, 9:00 AM local.
const NOW = at(2025, 11, 1, 9, 0);
const QUIET = { on: true, start: "23:00", end: "07:00" };
const NO_QUIET = { on: false, start: "23:00", end: "07:00" };

let counter = 0;
function make(due, extra = {}) {
  counter += 1;
  return {
    id: `s_${String(counter).padStart(10, "0")}`, rev: 1, created: NOW - counter * SEC, due,
    zone: "Asia/Kolkata", stem: "clip", name: "clip.mp4", caption: "hello", mode: "video",
    size: 10e6, sha256: null, custody: "local", fetched: 10e6, action: "prepare", catchUp: Q.CATCH_UP_MS,
    state: "scheduled", rung: null, attempts: 0, error: null, outcome: null, origin: "editor",
    looked: true, repeat: null, waitUntil: null, deleteAfter: null, ranAt: null, endedAt: null,
    ...extra,
  };
}

const dues = (items) => items.map((item) => item.due);
// Every pair of pending rows at least 90 s apart.
function assertSpaced(items) {
  const d = dues(Q.sorted(Q.pending(items)));
  for (let i = 1; i < d.length; i++) assert.ok(d[i] - d[i - 1] >= Q.SPACING_MS, `gap ${d[i] - d[i - 1]} at ${i}`);
}
const frozen = (value) => JSON.stringify(value);

test("sorted orders by due, then created, then id, and does not touch its input", () => {
  const a = make(NOW + HOUR, { id: "s_b", created: 5 });
  const b = make(NOW + HOUR, { id: "s_a", created: 5 });
  const c = make(NOW + HOUR, { id: "s_c", created: 1 });
  const d = make(NOW + 10 * MIN);
  const input = [a, b, c, d];
  const before = frozen(input);
  assert.deepEqual(Q.sorted(input).map((i) => i.id), [d.id, "s_c", "s_a", "s_b"]);
  assert.equal(frozen(input), before);
});

test("pending is every state except done and cancelled", () => {
  const states = ["holding", "scheduled", "prewarmed", "waiting", "running", "asked", "prepared", "failed",
    "missed", "done", "cancelled"];
  const items = states.map((state) => make(NOW + HOUR, { state }));
  assert.deepEqual(Q.pending(items).map((i) => i.state), states.slice(0, 9));
});

// -- quiet hours --------------------------------------------------------------------

test("quiet hours span midnight and end exclusive", () => {
  assert.equal(Q.inQuiet(at(2025, 11, 1, 23, 0), QUIET), true);
  assert.equal(Q.inQuiet(at(2025, 11, 1, 23, 59), QUIET), true);
  assert.equal(Q.inQuiet(at(2025, 11, 2, 0, 30), QUIET), true);
  assert.equal(Q.inQuiet(at(2025, 11, 2, 6, 59), QUIET), true);
  assert.equal(Q.inQuiet(at(2025, 11, 2, 7, 0), QUIET), false);
  assert.equal(Q.inQuiet(at(2025, 11, 1, 22, 59), QUIET), false);
  assert.equal(Q.inQuiet(at(2025, 11, 1, 12, 0), QUIET), false);
});

test("quiet hours inside one day, switched off, or unreadable are handled", () => {
  const day = { on: true, start: "13:00", end: "15:00" };
  assert.equal(Q.inQuiet(at(2025, 11, 1, 14, 0), day), true);
  assert.equal(Q.inQuiet(at(2025, 11, 1, 15, 0), day), false);
  assert.equal(Q.inQuiet(at(2025, 11, 1, 23, 30), NO_QUIET), false);
  assert.equal(Q.inQuiet(at(2025, 11, 1, 23, 30), { on: true, start: "x", end: "07:00" }), false);
  assert.equal(Q.inQuiet(at(2025, 11, 1, 23, 30), { on: true, start: "07:00", end: "07:00" }), false);
  assert.equal(Q.inQuiet(at(2025, 11, 1, 23, 30), undefined), false);
});

test("quietEnds is the next end at or after the time, across midnight", () => {
  assert.equal(Q.quietEnds(at(2025, 11, 1, 23, 30), QUIET), at(2025, 11, 2, 7, 0));
  assert.equal(Q.quietEnds(at(2025, 11, 2, 2, 0), QUIET), at(2025, 11, 2, 7, 0));
  assert.equal(Q.quietEnds(at(2025, 11, 2, 7, 0), QUIET), at(2025, 11, 2, 7, 0));
  assert.equal(Q.quietEnds(at(2025, 11, 2, 12, 0), QUIET), at(2025, 11, 3, 7, 0));
  assert.equal(Q.quietEnds(at(2025, 11, 1, 12, 0), NO_QUIET), at(2025, 11, 1, 12, 0));
});

// -- checkDue -------------------------------------------------------------------------

test("a time under 2 minutes ahead is refused with the fix, and exactly 2 minutes is allowed", () => {
  const soon = Q.checkDue(NOW + 119 * SEC, NOW, QUIET);
  assert.equal(soon.ok, false);
  assert.equal(soon.code, "past");
  assert.equal(soon.error, "Choose a time at least 2 minutes from now");
  assert.equal(Q.checkDue(NOW - HOUR, NOW, QUIET).code, "past");
  assert.equal(Q.checkDue(NOW + 2 * MIN, NOW, QUIET).ok, true);
});

test("a time over 30 days ahead is refused, 30 days exactly is allowed", () => {
  const far = Q.checkDue(NOW + 30 * 86400000 + SEC, NOW, QUIET);
  assert.equal(far.ok, false);
  assert.equal(far.code, "far");
  assert.match(far.error, /30 days/);
  assert.equal(Q.checkDue(NOW + 30 * 86400000, NOW, NO_QUIET).ok, true);
});

test("a time that is not a number is refused", () => {
  assert.equal(Q.checkDue(NaN, NOW, QUIET).code, "invalid");
  assert.equal(Q.checkDue(undefined, NOW, QUIET).ok, false);
});

test("quiet hours warn and never refuse, including a time past midnight", () => {
  for (const due of [at(2025, 11, 1, 23, 30), at(2025, 11, 2, 1, 0)]) {
    const result = Q.checkDue(due, NOW, QUIET);
    assert.equal(result.ok, true);
    assert.match(result.warning, /quiet hours/);
    assert.match(result.warning, /23:00 to 07:00/);
  }
  assert.equal(Q.checkDue(at(2025, 11, 1, 18, 0), NOW, QUIET).warning, undefined);
  assert.equal(Q.checkDue(at(2025, 11, 1, 23, 30), NOW, NO_QUIET).warning, undefined);
});

// -- spacing --------------------------------------------------------------------------

test("a time within 90 s of another moves to 90 s after it, and a clear one stays", () => {
  const first = make(NOW + HOUR);
  assert.deepEqual(Q.spaced([first], NOW + HOUR + 30 * SEC, null), { due: NOW + HOUR + 90 * SEC, after: first.id });
  assert.deepEqual(Q.spaced([first], NOW + HOUR - 30 * SEC, null), { due: NOW + HOUR + 90 * SEC, after: first.id });
  assert.deepEqual(Q.spaced([first], NOW + HOUR + 90 * SEC, null), { due: NOW + HOUR + 90 * SEC, after: null });
});

test("spacing cascades down a run of close posts", () => {
  const a = make(NOW + HOUR);
  const b = make(NOW + HOUR + 90 * SEC);
  const c = make(NOW + HOUR + 180 * SEC);
  const result = Q.spaced([a, b, c], NOW + HOUR + SEC, null);
  assert.equal(result.due, NOW + HOUR + 270 * SEC);
  assert.equal(result.after, c.id);
});

test("spacing ignores itself and rows that are finished", () => {
  const me = make(NOW + HOUR);
  const gone = make(NOW + HOUR + 10 * SEC, { state: "cancelled" });
  assert.deepEqual(Q.spaced([me, gone], NOW + HOUR, me.id), { due: NOW + HOUR, after: null });
});

test("insert keeps the time when clear, and spaces and says so when it is not", () => {
  const first = make(at(2025, 11, 1, 18, 0));
  const clear = Q.insert([first], make(at(2025, 11, 1, 19, 0)), NOW, QUIET);
  assert.equal(clear.note, null);
  assert.equal(clear.items.length, 2);
  const close = make(at(2025, 11, 1, 18, 0, 20));
  const spaced = Q.insert([first], close, NOW, QUIET);
  assert.equal(spaced.item.due, at(2025, 11, 1, 18, 1, 30));
  assert.equal(spaced.note, "Moved to 6:01:30 PM, 90 s after the clip at 6:00 PM");
  assert.equal(spaced.item.id, close.id);
});

test("insert refuses a bad time with its code, and carries a quiet hours warning", () => {
  assert.deepEqual(Q.insert([], make(NOW + MIN), NOW, QUIET), {
    error: "Choose a time at least 2 minutes from now", code: "past",
  });
  assert.equal(Q.insert([], make(NOW + 31 * 86400000), NOW, QUIET).code, "far");
  const quiet = Q.insert([], make(at(2025, 11, 1, 23, 30)), NOW, QUIET);
  assert.match(quiet.warning, /quiet hours/);
});

test("insert near the 30 day edge cannot be spaced past it", () => {
  const edge = NOW + 30 * 86400000;
  const result = Q.insert([make(edge)], make(edge - SEC), NOW, NO_QUIET);
  assert.equal(result.code, "far");
});

test("insert does not mutate its inputs and returns a sorted list", () => {
  const items = [make(NOW + 3 * HOUR), make(NOW + HOUR)];
  const before = frozen(items);
  const result = Q.insert(items, make(NOW + 2 * HOUR), NOW, QUIET);
  assert.equal(frozen(items), before);
  assert.deepEqual(dues(result.items), [NOW + HOUR, NOW + 2 * HOUR, NOW + 3 * HOUR]);
});

// -- afterLast ------------------------------------------------------------------------

test("afterLast is the last pending time plus the gap, or now plus the gap when none", () => {
  const gap = 3 * HOUR;
  assert.equal(Q.afterLast([], NOW, gap, NO_QUIET), NOW + gap);
  const items = [make(NOW + HOUR), make(NOW + 5 * HOUR), make(NOW + 9 * HOUR, { state: "cancelled" })];
  assert.equal(Q.afterLast(items, NOW, gap, NO_QUIET), NOW + 8 * HOUR);
});

test("afterLast starts from now when the last post has already passed, and keeps the minimum lead", () => {
  const old = [make(NOW - 5 * HOUR, { state: "missed" })];
  assert.equal(Q.afterLast(old, NOW, HOUR, NO_QUIET), NOW + HOUR);
  assert.equal(Q.afterLast([], NOW, 0, NO_QUIET), NOW + Q.MIN_AHEAD_MS);
});

test("afterLast moves a time inside quiet hours to where they end", () => {
  const last = make(at(2025, 11, 1, 21, 0));
  assert.equal(Q.afterLast([last], NOW, 3 * HOUR, QUIET), at(2025, 11, 2, 7, 0));
  // 22:00 plus 90 minutes lands at 23:30, still quiet, so 07:00 the next morning.
  const early = make(at(2025, 11, 1, 22, 0));
  assert.equal(Q.afterLast([early], NOW, 90 * MIN, QUIET), at(2025, 11, 2, 7, 0));
});

test("afterLast spaces a time that lands on the quiet end against a post already there", () => {
  const last = make(at(2025, 11, 1, 21, 0));
  const morning = make(at(2025, 11, 2, 7, 0, 30), { created: 0 });
  // morning is the last pending post: 7:00:30 + 3 h, no quiet, nothing in the way.
  assert.equal(Q.afterLast([last, morning], NOW, 3 * HOUR, QUIET), at(2025, 11, 2, 10, 0, 30));
  const blocker = make(at(2025, 11, 2, 7, 0));
  // Pushed to 07:00 by quiet hours, where `blocker` already is: 90 s after it.
  assert.equal(Q.afterLast([last, make(at(2025, 11, 1, 23, 40), { state: "cancelled" })], NOW, 3 * HOUR, QUIET),
    at(2025, 11, 2, 7, 0));
  assert.equal(blocker.due, at(2025, 11, 2, 7, 0));
});

// -- retime ---------------------------------------------------------------------------

test("retime re-sorts the list and keeps the row's identity", () => {
  const a = make(NOW + HOUR);
  const b = make(NOW + 2 * HOUR);
  const c = make(NOW + 3 * HOUR);
  const result = Q.retime([a, b, c], a.id, NOW + 4 * HOUR, NOW, NO_QUIET);
  assert.deepEqual(result.items.map((i) => i.id), [b.id, c.id, a.id]);
  assert.equal(result.item.id, a.id);
  assert.equal(result.item.caption, a.caption);
  assert.equal(result.item.created, a.created);
  assert.equal(result.item.rev, a.rev + 1);
  assert.equal(result.note, "Moved to Sat 1 Nov, 1:00 PM");
});

test("retime to within 90 s of another saves 90 s after it, with the words for it", () => {
  const a = make(at(2025, 11, 1, 9 + 9, 0));
  const b = make(at(2025, 11, 1, 20, 0));
  const result = Q.retime([a, b], b.id, at(2025, 11, 1, 18, 0, 30), NOW, NO_QUIET);
  assert.equal(result.item.due, at(2025, 11, 1, 18, 1, 30));
  assert.equal(result.note, "Moved to 6:01:30 PM, 90 s after the clip at 6:00 PM");
  assertSpaced(result.items);
});

test("retime cascades past a run of posts and a day away says the day", () => {
  const a = make(at(2025, 11, 5, 9, 0));
  const b = make(at(2025, 11, 5, 9, 1, 30));
  const c = make(at(2025, 11, 7, 12, 0));
  const result = Q.retime([a, b, c], c.id, at(2025, 11, 5, 9, 0, 10), NOW, NO_QUIET);
  assert.equal(result.item.due, at(2025, 11, 5, 9, 3, 0));
  assert.equal(result.note, "Moved to Wed 5 Nov, 9:03 AM, 90 s after the clip at 9:01:30 AM");
  assertSpaced(result.items);
});

test("retime refuses a past or far time with its code and changes nothing", () => {
  const a = make(NOW + HOUR);
  assert.equal(Q.retime([a], a.id, NOW + MIN, NOW, QUIET).code, "past");
  assert.equal(Q.retime([a], a.id, NOW + 40 * 86400000, NOW, QUIET).code, "far");
  assert.equal(Q.retime([a], "s_nope", NOW + 3 * HOUR, NOW, QUIET).code, "gone");
});

test("retime warns inside quiet hours but still moves it", () => {
  const a = make(NOW + HOUR);
  const result = Q.retime([a], a.id, at(2025, 11, 1, 23, 30), NOW, QUIET);
  assert.equal(result.item.due, at(2025, 11, 1, 23, 30));
  assert.match(result.warning, /quiet hours/);
});

test("a running, prepared or finished row cannot be retimed or edited", () => {
  for (const state of ["running", "prepared", "done", "cancelled"]) {
    const a = make(NOW + HOUR, { state });
    assert.equal(Q.editable(a), false, state);
    assert.equal(Q.retime([a], a.id, NOW + 3 * HOUR, NOW, QUIET).code, "locked", state);
    assert.equal(Q.edit([a], a.id, { caption: "x" }).code, "locked", state);
  }
  for (const state of ["holding", "scheduled", "prewarmed", "waiting", "asked", "failed", "missed"]) {
    assert.equal(Q.editable(make(NOW + HOUR, { state })), true, state);
  }
});

test("giving a missed or failed row a new time puts it back to scheduled and clears the failure", () => {
  const missed = make(NOW - HOUR, {
    state: "missed", outcome: "missed", attempts: 2, rung: "S1", error: { message: "late", code: "late" },
  });
  const result = Q.retime([missed], missed.id, NOW + 3 * HOUR, NOW, QUIET);
  assert.equal(result.item.state, "scheduled");
  assert.equal(result.item.error, null);
  assert.equal(result.item.outcome, null);
  assert.equal(result.item.attempts, 0);
  const fetching = make(NOW - HOUR, { state: "failed", custody: "fetching" });
  assert.equal(Q.retime([fetching], fetching.id, NOW + 3 * HOUR, NOW, QUIET).item.state, "holding");
});

test("retime does not mutate its input", () => {
  const items = [make(NOW + HOUR), make(NOW + 2 * HOUR)];
  const before = frozen(items);
  Q.retime(items, items[0].id, NOW + 5 * HOUR, NOW, QUIET);
  assert.equal(frozen(items), before);
});

// -- edit and cancel --------------------------------------------------------------------

test("edit trims the caption, refuses one over 1024 characters, and bumps the revision", () => {
  const a = make(NOW + HOUR);
  const result = Q.edit([a], a.id, { caption: "  new words \n" });
  assert.equal(result.item.caption, "new words");
  assert.equal(result.item.rev, a.rev + 1);
  assert.equal(Q.edit([a], a.id, { caption: "x".repeat(1024) }).item.caption.length, 1024);
  const long = Q.edit([a], a.id, { caption: "x".repeat(1025) });
  assert.equal(long.code, "long");
  assert.match(long.error, /1024/);
  assert.equal(Q.edit([a], a.id, {}).code, "invalid");
  assert.equal(a.caption, "hello");
});

test("cancel sets a deadline of ten seconds and its Undo brings the row back", () => {
  const a = make(NOW + HOUR);
  const b = make(NOW + 2 * HOUR);
  const result = Q.cancel([a, b], a.id, NOW);
  assert.equal(result.item.state, "cancelled");
  assert.equal(result.item.deleteAfter, NOW + Q.UNDO_MS);
  const back = Q.restore(result.items, result.undo);
  assert.deepEqual(back.restored, [a.id]);
  const row = back.items.find((i) => i.id === a.id);
  assert.equal(row.state, "scheduled");
  assert.equal(row.deleteAfter, null);
  assert.equal(row.endedAt, null);
});

// -- shift and spread -------------------------------------------------------------------

test("shift moves the chosen rows by the same amount, spaced, and reports what moved", () => {
  const a = make(NOW + HOUR);
  const b = make(NOW + HOUR + 90 * SEC);
  const c = make(NOW + 5 * HOUR);
  const result = Q.shift([a, b, c], [a.id, b.id], 2 * HOUR, NOW, NO_QUIET);
  assert.deepEqual(result.items.map((i) => i.id), [a.id, b.id, c.id]);
  assert.equal(result.items[0].due, NOW + 3 * HOUR);
  assert.equal(result.items[1].due, NOW + 3 * HOUR + 90 * SEC);
  assert.deepEqual(result.moved.map((m) => m.id), [a.id, b.id]);
  assert.equal(result.moved[0].from, NOW + HOUR);
  assertSpaced(result.items);
});

test("shift lands spaced against rows that stay put and skips what cannot move", () => {
  const a = make(NOW + HOUR);
  const stay = make(NOW + 2 * HOUR);
  const locked = make(NOW + 3 * HOUR, { state: "running" });
  const result = Q.shift([a, stay, locked], [a.id, locked.id, "s_none"], HOUR, NOW, NO_QUIET);
  assert.equal(result.items.find((i) => i.id === a.id).due, NOW + 2 * HOUR + 90 * SEC);
  assert.deepEqual(result.skipped.map((s) => s.code).sort(), ["gone", "locked"]);
  assertSpaced(result.items);
  const past = Q.shift([a], [a.id], -2 * HOUR, NOW, NO_QUIET);
  assert.equal(past.skipped[0].code, "past");
  assert.equal(past.items[0].due, a.due);
});

test("shift warns about a row moved into quiet hours", () => {
  const a = make(at(2025, 11, 1, 21, 0));
  const result = Q.shift([a], [a.id], 2 * HOUR + 30 * MIN, NOW, QUIET);
  assert.equal(result.warnings.length, 1);
  assert.equal(result.warnings[0].id, a.id);
});

test("spread puts the rows in their current order from the start, a fixed gap apart", () => {
  const a = make(NOW + 5 * HOUR);
  const b = make(NOW + HOUR);
  const c = make(NOW + 3 * HOUR);
  const start = NOW + 10 * HOUR;
  const result = Q.spread([a, b, c], [a.id, b.id, c.id], start, 30 * MIN, NOW, NO_QUIET);
  const ordered = result.items;
  assert.deepEqual(ordered.map((i) => i.id), [b.id, c.id, a.id]);
  assert.deepEqual(dues(ordered), [start, start + 30 * MIN, start + 60 * MIN]);
  // A gap under 90 s is raised to 90 s.
  const tight = Q.spread([a, b], [a.id, b.id], start, 10 * SEC, NOW, NO_QUIET);
  assert.deepEqual(dues(tight.items), [start, start + 90 * SEC]);
});

test("a preview of shift or spread equals what is saved, and inputs are untouched", () => {
  const items = [make(NOW + HOUR), make(NOW + 2 * HOUR), make(NOW + 3 * HOUR)];
  const before = frozen(items);
  const ids = [items[0].id, items[2].id];
  assert.equal(frozen(Q.shift(items, ids, HOUR, NOW, QUIET).items), frozen(Q.shift(items, ids, HOUR, NOW, QUIET).items));
  assert.equal(frozen(items), before);
  const spreadOut = Q.spread(items, ids, NOW + 6 * HOUR, HOUR, NOW, QUIET);
  assert.deepEqual(spreadOut.moved.map((m) => m.to), [NOW + 6 * HOUR, NOW + 7 * HOUR]);
});

// -- limits ---------------------------------------------------------------------------

test("the pending limit refuses at the count and the message names it and what frees room", () => {
  const items = [make(NOW + HOUR), make(NOW + 2 * HOUR), make(NOW + 3 * HOUR, { state: "done" })];
  const result = Q.checkLimits(items, 10e6, { pending: 2, budgetBytes: 1e9 });
  assert.equal(result.ok, false);
  assert.equal(result.code, "limit");
  assert.match(result.error, /2 posts scheduled/);
  assert.match(result.error, /most allowed here is 2/);
  assert.match(result.error, /Post or cancel/);
  assert.equal(Q.checkLimits(items, 10e6, { pending: 3, budgetBytes: 1e9 }).ok, true);
});

test("the budget counts pending local and fetching clips, and the message names the budget", () => {
  const items = [
    make(NOW + HOUR, { size: 300e6 }),
    make(NOW + 2 * HOUR, { size: 50e6, custody: "fetching" }),
    make(NOW + 3 * HOUR, { size: 900e6, state: "cancelled" }),
  ];
  const limits = { pending: 90, budgetBytes: 400e6 };
  assert.equal(Q.checkLimits(items, 50e6, limits).ok, true);
  const result = Q.checkLimits(items, 50e6 + 1, limits);
  assert.equal(result.ok, false);
  assert.equal(result.code, "budget");
  assert.match(result.error, /350 MB of the 400 MB/);
  assert.match(result.error, /free room/);
  assert.match(Q.checkLimits([make(NOW + HOUR, { size: 1e9 })], 1e8, { pending: 5, budgetBytes: 1.05e9 }).error, /1 GB of the 1\.1 GB|1 GB of the 1\.05 GB/);
});

test("the pending limit is checked before the budget, and missing limits allow", () => {
  const items = [make(NOW + HOUR, { size: 400e6 })];
  assert.equal(Q.checkLimits(items, 1, { pending: 1, budgetBytes: 400e6 }).code, "limit");
  assert.equal(Q.checkLimits(items, 1, {}).ok, true);
  assert.equal(Q.checkLimits(items, 1, undefined).ok, true);
});

// -- catch up -------------------------------------------------------------------------

test("a run within the catch up window and outside quiet hours goes", () => {
  const item = make(at(2025, 11, 1, 10, 0));
  assert.deepEqual(Q.catchUp(item, at(2025, 11, 1, 10, 0), QUIET), { decision: "run", reason: null });
  assert.deepEqual(Q.catchUp(item, at(2025, 11, 1, 10, 30), QUIET), { decision: "run", reason: null });
  assert.deepEqual(Q.catchUp(item, at(2025, 11, 1, 9, 58), QUIET), { decision: "run", reason: null });
});

test("a run later than the window is missed for being late, and the window is per item", () => {
  const item = make(at(2025, 11, 1, 10, 0));
  assert.deepEqual(Q.catchUp(item, at(2025, 11, 1, 10, 30, 1), QUIET), { decision: "missed", reason: "late" });
  const patient = make(at(2025, 11, 1, 10, 0), { catchUp: 2 * HOUR });
  assert.equal(Q.catchUp(patient, at(2025, 11, 1, 11, 59), QUIET).decision, "run");
  const strict = make(at(2025, 11, 1, 10, 0), { catchUp: 0 });
  assert.equal(Q.catchUp(strict, at(2025, 11, 1, 10, 0), QUIET).decision, "run");
  assert.equal(Q.catchUp(strict, at(2025, 11, 1, 10, 0, 1), QUIET).decision, "missed");
  assert.equal(Q.catchUp(strict, at(2025, 11, 1, 10, 5), QUIET).decision, "missed");
});

test("a catch up in quiet hours is missed, but an on time run in quiet hours still goes", () => {
  const item = make(at(2025, 11, 1, 22, 50));
  const late = Q.catchUp(item, at(2025, 11, 1, 23, 10), QUIET);
  assert.deepEqual(late, { decision: "missed", reason: "quiet" });
  const chosen = make(at(2025, 11, 1, 23, 30));
  assert.equal(Q.catchUp(chosen, at(2025, 11, 1, 23, 30, 3), QUIET).decision, "run");
  assert.equal(Q.catchUp(item, at(2025, 11, 1, 23, 10), NO_QUIET).decision, "run");
});

// -- pause ----------------------------------------------------------------------------

function paused() {
  const pausedAt = at(2025, 11, 1, 10, 0);
  const now = at(2025, 11, 1, 11, 0);
  const o1 = make(at(2025, 11, 1, 10, 20), { created: 2 });
  const o2 = make(at(2025, 11, 1, 10, 40), { created: 1, state: "waiting" });
  const later = make(at(2025, 11, 1, 13, 0));
  const failed = make(at(2025, 11, 1, 10, 30), { state: "failed" });
  const done = make(at(2025, 11, 1, 10, 10), { state: "done" });
  return { pausedAt, now, o1, o2, later, failed, items: [later, failed, o2, done, o1] };
}

test("overdue is the runnable rows whose time passed while paused, in order", () => {
  const p = paused();
  assert.deepEqual(Q.overdue(p.items, p.pausedAt, p.now), [p.o1.id, p.o2.id]);
  assert.deepEqual(Q.overdue(p.items, p.pausedAt, p.pausedAt), []);
});

test("resume post: the overdue rows run now, then 90 s apart, in order", () => {
  const p = paused();
  const result = Q.resume(p.items, "post", p.pausedAt, p.now, QUIET);
  assert.deepEqual(result.changed, [p.o1.id, p.o2.id]);
  const o1 = result.items.find((i) => i.id === p.o1.id);
  const o2 = result.items.find((i) => i.id === p.o2.id);
  assert.equal(o1.due, p.now);
  assert.equal(o2.due, p.now + 90 * SEC);
  assert.equal(o2.state, "scheduled");
  assert.equal(o1.rev, p.o1.rev + 1);
  assertSpaced(result.items);
  assert.equal(result.items.find((i) => i.id === p.later.id).due, p.later.due);
});

test("resume post keeps spacing against a row already due soon", () => {
  const p = paused();
  const close = make(p.now + 30 * SEC);
  const result = Q.resume(p.items.concat([close]), "post", p.pausedAt, p.now, QUIET);
  assertSpaced(result.items);
});

test("resume later moves the overdue rows by the time paused, no earlier than a lead from now", () => {
  const p = paused();
  const result = Q.resume(p.items, "later", p.pausedAt, p.now, QUIET);
  const o1 = result.items.find((i) => i.id === p.o1.id);
  const o2 = result.items.find((i) => i.id === p.o2.id);
  assert.equal(o1.due, at(2025, 11, 1, 11, 20));
  assert.equal(o2.due, at(2025, 11, 1, 11, 40));
  assert.equal(o2.state, "scheduled");
  const ran = make(p.pausedAt - 5 * MIN);
  const clamped = Q.resume([ran], "later", p.pausedAt, p.now, QUIET);
  assert.equal(clamped.items[0].due, p.now + Q.MIN_AHEAD_MS);
});

test("resume missed marks the overdue rows missed with a reason and leaves the rest", () => {
  const p = paused();
  const result = Q.resume(p.items, "missed", p.pausedAt, p.now, QUIET);
  const o1 = result.items.find((i) => i.id === p.o1.id);
  assert.equal(o1.state, "missed");
  assert.equal(o1.error.code, "paused");
  assert.equal(result.items.find((i) => i.id === p.later.id).state, "scheduled");
  assert.equal(result.items.find((i) => i.id === p.failed.id).state, "failed");
});

test("resume refuses an unknown choice and does not mutate its input", () => {
  const p = paused();
  const before = frozen(p.items);
  assert.equal(Q.resume(p.items, "later-ish", p.pausedAt, p.now, QUIET).code, "invalid");
  Q.resume(p.items, "post", p.pausedAt, p.now, QUIET);
  Q.resume(p.items, "later", p.pausedAt, p.now, QUIET);
  Q.resume(p.items, "missed", p.pausedAt, p.now, QUIET);
  assert.equal(frozen(p.items), before);
});

// -- nextWake -------------------------------------------------------------------------

test("nextWake is the earliest of prewarm and lead for scheduled rows", () => {
  const due = NOW + HOUR;
  assert.equal(Q.nextWake([make(due)], NOW, false), due - Q.PREWARM_MS);
  assert.equal(Q.nextWake([make(due, { state: "prewarmed" })], NOW, false), due - Q.LEAD_MS);
  assert.equal(Q.nextWake([make(due), make(due - 30 * MIN)], NOW, false), due - 30 * MIN - Q.PREWARM_MS);
});

test("nextWake is never earlier than now, and null when there is nothing to wake for", () => {
  assert.equal(Q.nextWake([make(NOW + MIN)], NOW, false), NOW);
  assert.equal(Q.nextWake([], NOW, false), null);
  assert.equal(Q.nextWake([make(NOW + HOUR, { state: "done" })], NOW, false), null);
  assert.equal(Q.nextWake([make(NOW + HOUR, { state: "asked" })], NOW, false), null);
});

test("nextWake takes waitUntil and deleteAfter", () => {
  const waiting = make(NOW - MIN, { state: "waiting", waitUntil: NOW + 7 * MIN });
  assert.equal(Q.nextWake([waiting], NOW, false), NOW + 7 * MIN);
  const cancelled = make(NOW + HOUR, { state: "cancelled", deleteAfter: NOW + 10 * SEC });
  assert.equal(Q.nextWake([make(NOW + 3 * HOUR), cancelled], NOW, false), NOW + 10 * SEC);
});

test("nextWake while paused keeps the prewarm and the deletions but skips the lead and the waits", () => {
  const due = NOW + HOUR;
  assert.equal(Q.nextWake([make(due)], NOW, true), due - Q.PREWARM_MS);
  assert.equal(Q.nextWake([make(due, { state: "prewarmed" })], NOW, true), null);
  const waiting = make(NOW - MIN, { state: "waiting", waitUntil: NOW + 7 * MIN });
  assert.equal(Q.nextWake([waiting], NOW, true), null);
  const cancelled = make(due, { state: "cancelled", deleteAfter: NOW + 10 * SEC });
  assert.equal(Q.nextWake([cancelled], NOW, true), NOW + 10 * SEC);
});

// -- Undo -----------------------------------------------------------------------------

// Whatever an operation changed, Undo puts back exactly, apart from the revision,
// which only ever goes forward.
function withoutRev(items) {
  return frozen(Q.sorted(items).map((item) => ({ ...item, rev: 0 })));
}

test("Undo of a retime restores the time, the place and the state", () => {
  const missed = make(NOW - HOUR, { state: "missed", error: { message: "late", code: "late" }, attempts: 1 });
  const other = make(NOW + 2 * HOUR);
  const items = [missed, other];
  const snap = Q.snapshot(items, [missed.id]);
  const moved = Q.retime(items, missed.id, NOW + 5 * HOUR, NOW, QUIET);
  const back = Q.restore(moved.items, snap);
  assert.equal(withoutRev(back.items), withoutRev(items));
  assert.ok(back.items.find((i) => i.id === missed.id).rev > moved.item.rev);
});

test("Undo of a caption edit restores the caption", () => {
  const a = make(NOW + HOUR);
  const snap = Q.snapshot([a], [a.id]);
  const edited = Q.edit([a], a.id, { caption: "different" });
  assert.equal(withoutRev(Q.restore(edited.items, snap).items), withoutRev([a]));
});

test("Undo of shift, spread and each resume choice restores every row", () => {
  const p = paused();
  const ids = p.items.map((i) => i.id);
  const snap = Q.snapshot(p.items, ids);
  const operations = [
    Q.shift(p.items, [p.later.id, p.o1.id], 3 * HOUR, p.now, NO_QUIET).items,
    Q.spread(p.items, [p.later.id, p.o1.id, p.o2.id], p.now + 5 * HOUR, HOUR, p.now, NO_QUIET).items,
    Q.resume(p.items, "post", p.pausedAt, p.now, QUIET).items,
    Q.resume(p.items, "later", p.pausedAt, p.now, QUIET).items,
    Q.resume(p.items, "missed", p.pausedAt, p.now, QUIET).items,
  ];
  for (const after of operations) {
    assert.notEqual(withoutRev(after), withoutRev(p.items));
    assert.equal(withoutRev(Q.restore(after, snap).items), withoutRev(p.items));
  }
});

test("a snapshot is a copy and a restore leaves a running row alone and does not bring back a missing one", () => {
  const a = make(NOW + HOUR, { error: { message: "m", code: "c" } });
  const b = make(NOW + 2 * HOUR);
  const snap = Q.snapshot([a, b], [a.id, b.id, "s_nope"]);
  assert.equal(snap.items.length, 2);
  a.error.message = "changed after";
  assert.equal(snap.items[0].error.message, "m");
  const running = { ...a, state: "running", due: NOW + 9 * HOUR };
  const result = Q.restore([running], snap);
  assert.deepEqual(result.restored, []);
  assert.deepEqual(result.skipped.sort(), [a.id, b.id].sort());
  assert.equal(result.items.length, 1);
  assert.equal(result.items[0].state, "running");
  assert.equal(result.items[0].due, NOW + 9 * HOUR);
});

test("restore does not mutate its input", () => {
  const a = make(NOW + HOUR);
  const snap = Q.snapshot([a], [a.id]);
  const moved = Q.retime([a], a.id, NOW + 3 * HOUR, NOW, QUIET).items;
  const before = frozen(moved);
  Q.restore(moved, snap);
  assert.equal(frozen(moved), before);
});

// -- statusOf -------------------------------------------------------------------------

test("every state has a word, a tone and an action, and only missed, failed, asked and prepared need the person", () => {
  // Prepared needs a press of Send in Release 1, which prepares only (T2).
  const needs = new Set(["missed", "failed", "asked", "prepared"]);
  const states = ["holding", "scheduled", "prewarmed", "waiting", "running", "asked", "prepared", "failed",
    "missed", "cancelled", "done"];
  const tones = new Set(["ok", "wait", "warn", "bad", "muted"]);
  const actions = new Set([null, "post-now", "retry", "dismiss", "look"]);
  const words = new Set();
  for (const state of states) {
    const status = Q.statusOf(make(NOW + HOUR, { state }), false);
    assert.ok(status.word && typeof status.word === "string", state);
    assert.ok(tones.has(status.tone), state);
    assert.ok(actions.has(status.action), state);
    assert.equal(status.needsYou, needs.has(state), state);
    words.add(status.word);
  }
  assert.equal(words.size, states.length);
});

test("each state offers the one action that fits it", () => {
  const action = (state) => Q.statusOf(make(NOW + HOUR, { state }), false).action;
  assert.equal(action("missed"), "post-now");
  assert.equal(action("asked"), "post-now");
  assert.equal(action("failed"), "retry");
  assert.equal(action("prepared"), null);
  assert.equal(action("running"), null);
  assert.equal(action("done"), null);
  assert.equal(action("cancelled"), null);
});

test("tones: missed warns, failed is bad, asked warns, finished is muted", () => {
  const tone = (state) => Q.statusOf(make(NOW + HOUR, { state }), false).tone;
  assert.equal(tone("missed"), "warn");
  assert.equal(tone("failed"), "bad");
  assert.equal(tone("asked"), "warn");
  assert.equal(tone("prepared"), "warn");
  assert.equal(tone("scheduled"), "ok");
  assert.equal(tone("done"), "muted");
});

test("while paused a row that would run says Paused, and one that already needs you does not", () => {
  for (const state of ["scheduled", "prewarmed", "waiting"]) {
    const status = Q.statusOf(make(NOW + HOUR, { state }), true);
    assert.equal(status.word, "Paused");
    assert.equal(status.tone, "wait");
    assert.equal(status.needsYou, false);
  }
  assert.equal(Q.statusOf(make(NOW, { state: "missed" }), true).needsYou, true);
  assert.equal(Q.statusOf(make(NOW, { state: "done" }), true).word, "Done");
});

test("a status carries the stored reason as its detail line", () => {
  const status = Q.statusOf(make(NOW, { state: "failed", error: { message: "WhatsApp Web is signed out", code: "signed-out" } }), false);
  assert.equal(status.detail, "WhatsApp Web is signed out");
  assert.equal(Q.statusOf(make(NOW), false).detail, null);
});

// -- describe -------------------------------------------------------------------------

test("describe gives day, time and how far, the way the picker shows it", () => {
  assert.equal(Q.describe(at(2025, 11, 5, 9, 0), NOW), "Wed 5 Nov, 9:00 AM, in 4 days");
  // A mid month day, clear of any zone's daylight saving change.
  assert.equal(Q.describe(at(2025, 11, 15, 2, 0), at(2025, 11, 14, 9, 0)), "Sat 15 Nov, 2:00 AM, in 17 hours");
  assert.equal(Q.describe(at(2025, 11, 1, 18, 0), NOW), "Sat 1 Nov, 6:00 PM, in 9 hours");
});

test("describe handles minutes, noon and midnight, the past, and another year", () => {
  assert.equal(Q.describe(at(2025, 11, 1, 9, 17), NOW), "Sat 1 Nov, 9:17 AM, in 17 minutes");
  assert.equal(Q.describe(at(2025, 11, 1, 9, 1), NOW), "Sat 1 Nov, 9:01 AM, in 1 minute");
  assert.equal(Q.describe(at(2025, 11, 1, 12, 0), at(2025, 11, 1, 9, 0)), "Sat 1 Nov, 12:00 PM, in 3 hours");
  assert.equal(Q.describe(at(2025, 11, 2, 0, 5), at(2025, 11, 1, 9, 0)), "Sun 2 Nov, 12:05 AM, in 15 hours");
  assert.equal(Q.describe(at(2025, 11, 1, 8, 0), NOW), "Sat 1 Nov, 8:00 AM, 60 minutes ago");
  assert.equal(Q.describe(NOW, NOW), "Sat 1 Nov, 9:00 AM, now");
  assert.equal(Q.describe(at(2026, 1, 5, 9, 0), NOW), "Mon 5 Jan 2026, 9:00 AM, in 65 days");
  assert.equal(Q.describe(NaN, NOW), "");
});

// -- the whole -------------------------------------------------------------------------

test("a sequence of operations never leaves two pending rows closer than 90 s", () => {
  let items = [];
  const quiet = QUIET;
  for (let i = 0; i < 12; i++) {
    const result = Q.insert(items, make(NOW + HOUR + (i % 4) * 20 * SEC), NOW, quiet);
    items = result.items;
    assertSpaced(items);
  }
  const ids = items.map((i) => i.id);
  items = Q.retime(items, ids[0], dues(items)[5] + SEC, NOW, quiet).items;
  assertSpaced(items);
  items = Q.shift(items, ids.slice(0, 5), 20 * SEC, NOW, quiet).items;
  assertSpaced(items);
  items = Q.spread(items, ids.slice(3, 9), NOW + 2 * HOUR, 10 * SEC, NOW, quiet).items;
  assertSpaced(items);
  items = Q.resume(items, "post", NOW, NOW + 3 * HOUR, quiet).items;
  assertSpaced(items);
});

test("the module exports its constants as the contract states them", () => {
  assert.equal(Q.SPACING_MS, 90000);
  assert.equal(Q.MIN_AHEAD_MS, 120000);
  assert.equal(Q.MAX_AHEAD_MS, 30 * 86400000);
  assert.equal(Q.CATCH_UP_MS, 1800000);
  assert.equal(Q.LEAD_MS, 120000);
  assert.equal(Q.PREWARM_MS, 300000);
  assert.equal(Q.UNDO_MS, 10000);
  assert.ok(!Q.PENDING.includes("done") && !Q.PENDING.includes("cancelled"));
  assert.deepEqual(Q.TERMINAL, ["done", "cancelled"]);
});

test("Undo of a cancel whose clip finished coming down meanwhile puts the row back as scheduled", () => {
  // Cancelled while holding; the download finished inside the Undo window. Holding
  // would have nothing to move it on and would fail at its due time (review, 2026-10-31).
  const a = make(NOW + HOUR, { state: "holding", custody: "fetching", fetched: 0 });
  const cancelled = Q.cancel([a], a.id, NOW);
  const kept = cancelled.items.map((row) => ({ ...row, custody: "local", fetched: row.size }));
  const back = Q.restore(kept, cancelled.undo);
  assert.equal(back.items[0].state, "scheduled");
  const stillComing = Q.restore(cancelled.items, cancelled.undo);
  assert.equal(stillComing.items[0].state, "holding");
});
