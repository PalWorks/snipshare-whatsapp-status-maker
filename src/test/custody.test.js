// custody.js against a fake IndexedDB and a fake SnipShare clip route: a scheduled
// clip comes down in 2 MiB parts, carries on from the parts already kept after a
// worker stop at any part, refuses a clip whose size is not the server's, notices a
// damaged clip, reports a full disk in plain words, and sweeps parts nobody names.
// docs/scheduling.md Sections 8 and 14 (E5, E6, E8, E12, UC1).
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");

const custodyModule = require("../custody.js");

const { PART_BYTES, partKey } = custodyModule;

// -- a fake IndexedDB: writes land only when the transaction commits -------------------

function fakeDb(options = {}) {
  const data = new Map();
  let commits = 0;
  const database = {
    transaction(name, mode) {
      assert.equal(name, "blobs");
      const staged = [];
      const t = { oncomplete: null, onerror: null, onabort: null, error: null };
      let pending = 0;
      let aborted = false;
      let scheduled = false;
      const commit = () => {
        if (scheduled) return;
        scheduled = true;
        setImmediate(() => {
          if (aborted) return;
          const writes = staged.filter((op) => op.kind === "put").length;
          if (writes) commits += 1;
          // A full disk is reported by the transaction, after the request said yes (E8).
          if (writes && options.quotaAt && commits === options.quotaAt) {
            aborted = true;
            t.error = new DOMException("The quota has been exceeded.", "QuotaExceededError");
            if (t.onerror) t.onerror();
            if (t.onabort) t.onabort();
            return;
          }
          for (const op of staged) {
            if (op.kind === "put") data.set(op.key, op.value);
            else data.delete(op.key);
          }
          if (t.oncomplete) t.oncomplete();
        });
      };
      const request = (work) => {
        const r = { onsuccess: null, onerror: null, result: undefined, error: null };
        pending += 1;
        setImmediate(() => {
          r.result = work();
          if (r.onsuccess) r.onsuccess();
          pending -= 1;
          if (!pending) commit();
        });
        return r;
      };
      t.objectStore = () => ({
        get: (key) => request(() => data.get(key)),
        getAllKeys: () => request(() => [...data.keys()]),
        put: (value, key) => {
          if (mode !== "readwrite") throw new DOMException("read only", "ReadOnlyError");
          return request(() => { staged.push({ kind: "put", key, value }); return key; });
        },
        delete: (key) => request(() => { staged.push({ kind: "delete", key }); }),
      });
      t.abort = () => { aborted = true; };
      return t;
    },
  };
  return { db: async () => database, data };
}

// -- a fake clip route with Range ---------------------------------------------------------

function clipBytes(size, seed = 1) {
  const out = new Uint8Array(size);
  let x = seed;
  for (let i = 0; i < size; i++) { x = (x * 1103515245 + 12345) >>> 0; out[i] = x >>> 24; }
  return out;
}

function sha(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function server(bytes, behaviour = {}) {
  const seen = [];
  let calls = 0;
  const fetch = async (url, init) => {
    calls += 1;
    const range = /^bytes=(\d+)-(\d*)$/.exec(init.headers.Range || "");
    seen.push(init.headers.Range || null);
    assert.equal(init.headers.Authorization, "Bearer grant-1");
    if (behaviour.status) return new Response("{}", { status: behaviour.status });
    const total = behaviour.claimSize || bytes.length;
    const ranged = range && !behaviour.ignoreRange;
    const first = ranged ? Number(range[1]) : 0;
    const last = ranged && range[2] ? Math.min(Number(range[2]), bytes.length - 1) : bytes.length - 1;
    let slice = bytes.subarray(first, last + 1);
    if (behaviour.extra) slice = Buffer.concat([Buffer.from(slice), Buffer.alloc(behaviour.extra)]);
    const dropAt = behaviour.dropOnCall && behaviour.dropOnCall(calls) ? behaviour.dropAfter : null;
    // One piece per pull, so a drop comes after the pieces already read, as on a wire.
    let at = 0;
    const step = 256 * 1024;
    const body = new ReadableStream({
      pull(controller) {
        if (at >= slice.length) { controller.close(); return; }
        if (dropAt !== null && at >= dropAt) { controller.error(new TypeError("network dropped")); return; }
        controller.enqueue(slice.subarray(at, at + step));
        at += step;
      },
    });
    const headers = range && !behaviour.ignoreRange
      ? { "Content-Range": `bytes ${first}-${last}/${total}`, "Content-Length": String(slice.length) }
      : { "Content-Length": String(total) };
    return new Response(body, { status: range && !behaviour.ignoreRange ? 206 : 200, headers });
  };
  return { fetch, seen, calls: () => calls };
}

function custody(store, extra = {}) {
  return custodyModule.make({
    db: store.db,
    estimate: async () => ({ quota: 10e9, usage: 0 }),
    digest: async (buffer) => crypto.createHash("sha256").update(Buffer.from(buffer)).digest().buffer,
    sleep: async () => {},
    ...extra,
  });
}

const URL_ = "https://renderer.example.com/api/v1/clip?stem=a";

test("a clip comes down in numbered parts of at most 2 MiB, one request per part, hashed once", async () => {
  const store = fakeDb();
  const bytes = clipBytes(5 * 1024 * 1024 + 123);
  const route = server(bytes);
  const c = custody(store, { fetch: route.fetch });
  const result = await c.fetch("s_one", { url: URL_, grant: "grant-1" });
  assert.equal(result.size, bytes.length);
  assert.equal(result.sha256, sha(bytes));
  assert.deepEqual([...store.data.keys()].sort(), [0, 1, 2].map((n) => partKey("s_one", n)).sort());
  assert.equal(store.data.get(partKey("s_one", 0)).size, PART_BYTES);
  assert.equal(store.data.get(partKey("s_one", 2)).size, bytes.length - 2 * PART_BYTES);
  // Each request asks for one part at most, so none waits long on a slow line (D-100).
  assert.deepEqual(route.seen, [`bytes=0-${PART_BYTES - 1}`, `bytes=${PART_BYTES}-${2 * PART_BYTES - 1}`,
    `bytes=${2 * PART_BYTES}-${3 * PART_BYTES - 1}`]);
  const joined = new Uint8Array(await (await c.read("s_one")).arrayBuffer());
  assert.deepEqual(Buffer.from(joined), Buffer.from(bytes));
  assert.equal((await c.read("s_one")).type, "video/mp4");
});

for (const stopAfter of [1, 2, 3]) {
  test(`a worker stopped after part ${stopAfter} carries on from the parts kept`, async () => {
    const store = fakeDb();
    const bytes = clipBytes(4 * PART_BYTES + 777, stopAfter);
    const first = server(bytes);
    const stop = new AbortController();
    let stored = 0;
    await assert.rejects(custody(store, { fetch: first.fetch }).fetch("s_res", {
      url: URL_, grant: "grant-1", signal: stop.signal,
      onProgress: (p) => { if (p.stored && ++stored === stopAfter) stop.abort(); },
    }), (err) => err.code === "stopped");
    // A new worker, the same database, nothing in memory.
    const second = server(bytes);
    const result = await custody(store, { fetch: second.fetch }).fetch("s_res", {
      url: URL_, grant: "grant-1", size: bytes.length,
    });
    assert.equal(second.seen[0], `bytes=${stopAfter * PART_BYTES}-${(stopAfter + 1) * PART_BYTES - 1}`);
    assert.equal(result.sha256, sha(bytes));
    assert.equal(result.size, bytes.length);
  });
}

test("a line that drops mid part keeps what arrived and asks only for the rest", async () => {
  const store = fakeDb();
  const bytes = clipBytes(3 * PART_BYTES);
  const route = server(bytes, { dropOnCall: (n) => n === 2, dropAfter: 1024 * 1024 });
  const result = await custody(store, { fetch: route.fetch }).fetch("s_drop", { url: URL_, grant: "grant-1" });
  assert.equal(result.sha256, sha(bytes));
  assert.equal(route.seen[2], `bytes=${PART_BYTES + 1024 * 1024}-${2 * PART_BYTES - 1}`);
});

test("a server that ignores Range gives the whole file, kept in parts all the same", async () => {
  const store = fakeDb();
  const bytes = clipBytes(PART_BYTES + 5000);
  const route = server(bytes, { ignoreRange: true });
  const result = await custody(store, { fetch: route.fetch }).fetch("s_200", { url: URL_, grant: "grant-1" });
  assert.equal(result.sha256, sha(bytes));
  assert.equal(store.data.size, 2);
});

test("a clip whose size is not the server's figure is refused and nothing is kept (E6)", async () => {
  const store = fakeDb();
  const bytes = clipBytes(PART_BYTES + 10);
  // The server now says the clip is a different size from the one started.
  await assert.rejects(custody(store, { fetch: server(bytes).fetch }).fetch("s_size", {
    url: URL_, grant: "grant-1", size: bytes.length + 99,
  }), (err) => err.code === "size");
  assert.equal(store.data.size, 0);
  // More bytes arriving than the server declared.
  await assert.rejects(custody(store, { fetch: server(bytes, { extra: 50 }).fetch }).fetch("s_size", {
    url: URL_, grant: "grant-1",
  }), (err) => err.code === "size");
  assert.equal(store.data.size, 0);
});

test("a damaged clip fails its hash check at prewarm", async () => {
  const store = fakeDb();
  const bytes = clipBytes(PART_BYTES + 40);
  const c = custody(store, { fetch: server(bytes).fetch });
  const { size, sha256 } = await c.fetch("s_hash", { url: URL_, grant: "grant-1" });
  assert.equal(await c.verify("s_hash", size, sha256), true);
  const bad = new Uint8Array(40).fill(7);
  store.data.set(partKey("s_hash", 1), new Blob([bad]));
  assert.equal(await c.verify("s_hash", size, sha256), false);
  store.data.delete(partKey("s_hash", 1));
  assert.equal(await c.verify("s_hash", size, sha256), false);
});

test("a full disk is a plain message, reported when the transaction aborts after the request succeeded", async () => {
  const store = fakeDb({ quotaAt: 2 });
  const bytes = clipBytes(3 * PART_BYTES);
  await assert.rejects(custody(store, { fetch: server(bytes).fetch }).fetch("s_q", { url: URL_, grant: "grant-1" }),
    (err) => err.code === "quota" && /no room left/.test(err.message) && !/Quota/.test(err.message));
  // Only the part whose transaction completed is kept.
  assert.deepEqual([...store.data.keys()], [partKey("s_q", 0)]);
});

test("no byte is written when the computer lacks room for twice the clip", async () => {
  const store = fakeDb();
  const bytes = clipBytes(PART_BYTES);
  const c = custody(store, { fetch: server(bytes).fetch, estimate: async () => ({ quota: 3e6, usage: 0 }) });
  await assert.rejects(c.fetch("s_room", { url: URL_, grant: "grant-1" }), (err) => err.code === "quota" && /MB free/.test(err.message));
  assert.equal(store.data.size, 0);
});

test("the limits are asked with the server's size before anything is kept", async () => {
  const store = fakeDb();
  const bytes = clipBytes(PART_BYTES + 1);
  let asked = null;
  const refusal = Object.assign(new Error("Over the budget"), { code: "budget" });
  await assert.rejects(custody(store, { fetch: server(bytes).fetch }).fetch("s_b", {
    url: URL_, grant: "grant-1", admit: async (size) => { asked = size; throw refusal; },
  }), (err) => err === refusal);
  assert.equal(asked, bytes.length);
  assert.equal(store.data.size, 0);
});

test("a clip SnipShare no longer has, or a grant that ran out, is gone at once", async () => {
  const store = fakeDb();
  const route = server(clipBytes(10), { status: 404 });
  await assert.rejects(custody(store, { fetch: route.fetch }).fetch("s_g", { url: URL_, grant: "grant-1" }),
    (err) => err.code === "gone");
  assert.equal(route.calls(), 1);
});

test("the sweep deletes scheduled parts nobody names and leaves everything else", async () => {
  const store = fakeDb();
  const c = custody(store);
  store.data.set(partKey("s_keep", 0), new Blob([new Uint8Array(10)]));
  store.data.set(partKey("s_gone", 0), new Blob([new Uint8Array(20)]));
  store.data.set(partKey("s_gone", 1), new Blob([new Uint8Array(20)]));
  store.data.set("jabc:clip", new Blob([new Uint8Array(5)]));
  assert.deepEqual(await c.usage(), { bytes: 50, byId: { s_keep: 10, s_gone: 40 } });
  assert.equal(await c.sweep(["s_keep"]), 2);
  assert.deepEqual([...store.data.keys()].sort(), ["jabc:clip", partKey("s_keep", 0)]);
  await c.drop("s_keep");
  assert.deepEqual([...store.data.keys()], ["jabc:clip"]);
});
