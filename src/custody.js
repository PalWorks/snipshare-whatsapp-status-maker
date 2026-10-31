// Scheduled clips kept on this computer: local custody, docs/scheduling.md Section 8
// as amended by Section 14 (UC1: every scheduled clip comes down when it is scheduled;
// no tickets, no pins).
//
// A clip is kept in IndexedDB as numbered parts, `sched:<id>:part:<n>`, each at most
// 2 MiB, and joined into one Blob only when it is handed to WhatsApp (E5). Each
// request asks for the rest of one part, so a worker stopped half way loses at most
// what had not been written, and a new worker carries on from the parts that are
// there. The server's figure for the size is the only one trusted (E6); the SHA-256 is
// taken once, at the end, and checked once more at prewarm. A write counts as written
// when its transaction completes, not when its request succeeds (E8): a transaction
// can still abort after the request said yes, and a full disk is reported that way.
//
// Everything Chrome gives (IndexedDB, fetch, the storage estimate, the hash) comes in
// through `deps`, so the Node tests drive it with fakes.
(function (root) {
  "use strict";

  const PART_BYTES = 2 * 1024 * 1024;  // E5: one write per part, never the whole growing file
  const REQUEST_TIMEOUT = 25000;       // an answer within this, under Chrome's 30 s for a worker's fetch (D-100)
  const STALL_TIMEOUT = 30000;         // a body with nothing arriving for this long has dropped
  const ATTEMPTS = 8;                  // consecutive failures, with nothing arriving, before giving up
  const ROOM_FACTOR = 2;               // Section 8.2: room for twice the clip before writing it
  const PREFIX = "sched:";
  const PART = /^sched:([^:]+):part:(\d+)$/;

  const QUOTA_MESSAGE = "This computer has no room left to keep the clip. Free some disk "
    + "space, or cancel a scheduled clip, then try again.";

  class CustodyError extends Error {
    // `code` is a word the page and the queue act on: gone, size, quota, network, stopped.
    constructor(message, code) { super(message); this.code = code; }
  }

  function partKey(id, n) { return `${PREFIX}${id}:part:${n}`; }

  function parse(key) {
    const match = PART.exec(String(key));
    return match ? { id: match[1], n: Number(match[2]) } : null;
  }

  function hex(buffer) {
    return Array.from(new Uint8Array(buffer), (b) => b.toString(16).padStart(2, "0")).join("");
  }

  // The same database the worker keeps its job's files in (sw.js `db`).
  function openDb() {
    return new Promise((resolve, reject) => {
      const open = root.indexedDB.open("wastatus", 1);
      open.onupgradeneeded = () => open.result.createObjectStore("blobs");
      open.onsuccess = () => resolve(open.result);
      open.onerror = () => reject(open.error);
    });
  }

  function browserDeps() {
    let database = null;
    return {
      db: () => {
        if (!database) database = openDb().catch((err) => { database = null; throw err; });
        return database;
      },
      fetch: (url, init) => root.fetch(url, init),
      estimate: () => (root.navigator && root.navigator.storage && root.navigator.storage.estimate
        ? root.navigator.storage.estimate() : Promise.resolve(null)),
      digest: (buffer) => root.crypto.subtle.digest("SHA-256", buffer),
      sleep: (ms, signal) => new Promise((resolve) => {
        const timer = setTimeout(resolve, ms);
        if (signal) signal.addEventListener("abort", () => { clearTimeout(timer); resolve(); }, { once: true });
      }),
    };
  }

  const backoff = (attempt) => Math.min(30000, 1000 * 2 ** attempt);

  function make(given) {
    const deps = { ...browserDeps(), ...(given || {}) };

    // A full disk shows up as the transaction aborting with QuotaExceededError,
    // sometimes after the request itself reported success.
    function plain(err) {
      if (err && err.name === "QuotaExceededError") return new CustodyError(QUOTA_MESSAGE, "quota");
      return err || new Error("IndexedDB failed");
    }

    // Resolves when the transaction completes, with the last request's result.
    async function tx(mode, work) {
      const database = await deps.db();
      return new Promise((resolve, reject) => {
        let transaction;
        try {
          transaction = database.transaction("blobs", mode);
        } catch (err) {
          reject(plain(err));
          return;
        }
        let result;
        let request = null;
        transaction.oncomplete = () => resolve(result);
        transaction.onerror = () => reject(plain(transaction.error || (request && request.error)));
        transaction.onabort = () => reject(plain(transaction.error || (request && request.error)));
        try {
          request = work(transaction.objectStore("blobs"));
          if (request) request.onsuccess = () => { result = request.result; };
        } catch (err) {
          try { transaction.abort(); } catch { /* already finished */ }
          reject(plain(err));
        }
      });
    }

    async function allKeys() {
      return (await tx("readonly", (store) => store.getAllKeys())) || [];
    }

    // The parts kept for a clip, in order, stopping at the first gap: a part after a
    // gap cannot be joined to anything, so it is not counted.
    async function parts(id) {
      const numbers = (await allKeys()).map(parse).filter((p) => p && p.id === id)
        .map((p) => p.n).sort((a, b) => a - b);
      const out = [];
      for (const n of numbers) {
        if (n !== out.length) break;
        const blob = await tx("readonly", (store) => store.get(partKey(id, n)));
        if (!blob) break;
        out.push({ n, blob });
        // Only the last part may be short; one that is short in the middle was cut
        // and what follows it is not trusted.
        if (blob.size < PART_BYTES) break;
      }
      return out;
    }

    async function writePart(id, n, blob) {
      await tx("readwrite", (store) => store.put(blob, partKey(id, n)));
    }

    async function deleteKeys(keys) {
      if (!keys.length) return;
      await tx("readwrite", (store) => {
        let last = null;
        for (const key of keys) last = store.delete(key);
        return last;
      });
    }

    async function drop(id) {
      const keys = (await allKeys()).filter((key) => { const p = parse(key); return p && p.id === id; });
      await deleteKeys(keys);
    }

    // Kept bytes in all, by clip id.
    async function usage() {
      const byId = {};
      let bytes = 0;
      for (const key of await allKeys()) {
        const p = parse(key);
        if (!p) continue;
        const blob = await tx("readonly", (store) => store.get(key));
        const size = blob ? blob.size : 0;
        byId[p.id] = (byId[p.id] || 0) + size;
        bytes += size;
      }
      return { bytes, byId };
    }

    // Deletes every `sched:` key no schedule names: left behind by a worker stopped
    // between forgetting a schedule and deleting its clip (E12).
    async function sweep(keepIds) {
      const keep = new Set(keepIds || []);
      const doomed = (await allKeys()).filter((key) => String(key).startsWith(PREFIX)
        && !keep.has((parse(key) || {}).id));
      await deleteKeys(doomed);
      return doomed.length;
    }

    // The whole clip, joined, or null when nothing is kept.
    async function read(id) {
      const kept = await parts(id);
      if (!kept.length) return null;
      return new Blob(kept.map((p) => p.blob), { type: "video/mp4" });
    }

    async function hashOf(blob) {
      return hex(await deps.digest(await blob.arrayBuffer()));
    }

    // The clip is all there and is the clip that was kept. Checked once, at prewarm (E6).
    async function verify(id, size, sha256) {
      const blob = await read(id);
      if (!blob || blob.size !== size) return false;
      if (!sha256) return true;
      return (await hashOf(blob)) === sha256;
    }

    async function room(needed) {
      let estimate = null;
      try { estimate = await deps.estimate(); } catch { estimate = null; }
      if (!estimate || !Number.isFinite(estimate.quota) || !Number.isFinite(estimate.usage)) return;
      if (estimate.quota - estimate.usage < needed) {
        const mb = Math.ceil(needed / 1e6);
        throw new CustodyError(`This computer needs about ${mb} MB free to keep the clip. Free some `
          + "disk space, or cancel a scheduled clip, then try again.", "quota");
      }
    }

    // Brings the clip at `url` down with the page's clip grant into numbered parts,
    // carrying on from whatever parts are already kept. `size` is the server's figure
    // from an earlier start, if any. `admit(size)` is asked once the size is known and
    // before anything new is written, so limits are checked against the real size.
    // `onProgress({have, size, stored})` hears every arrival, `stored` when a part was
    // written. Resolves with `{size, sha256}`.
    async function fetchClip(id, options) {
      const { url, grant, signal, onProgress, admit } = options;
      let size = Number.isFinite(options.size) && options.size > 0 ? options.size : null;
      const kept = await parts(id);
      // Full parts before `index`; `buffer` holds what has arrived of part `index`.
      let index = 0;
      let buffer = [];
      let buffered = 0;
      for (const p of kept) {
        if (p.blob.size === PART_BYTES) { index = p.n + 1; continue; }
        index = p.n;
        buffer = [p.blob];
        buffered = p.blob.size;
      }
      const have = () => index * PART_BYTES + buffered;
      let admitted = false;
      let failures = 0;

      // A server that keeps answering the whole file to a request for the rest, and
      // keeps stopping short, would otherwise be asked for ever.
      let restarts = 0;
      const restart = async () => {
        restarts += 1;
        if (restarts > ATTEMPTS) {
          throw new CustodyError("SnipShare kept sending the clip from the start. Try again.", "network");
        }
        await drop(id);
        index = 0;
        buffer = [];
        buffered = 0;
      };

      const store = async (final) => {
        if (!buffered) return;
        const joined = new Blob(buffer);
        if (joined.size >= PART_BYTES) {
          await writePart(id, index, joined.slice(0, PART_BYTES));
          index += 1;
          const rest = joined.slice(PART_BYTES);
          buffer = rest.size ? [rest] : [];
          buffered = rest.size;
          if (buffered >= PART_BYTES) await store(final);
        } else if (final) {
          await writePart(id, index, joined);
          buffer = [joined];
        }
      };

      const stopped = () => !!(signal && signal.aborted);

      while (size === null || have() < size) {
        if (stopped()) throw new CustodyError("Stopped.", "stopped");
        const from = have();
        const to = from + (PART_BYTES - buffered) - 1;
        const cut = new AbortController();
        let timer = setTimeout(() => cut.abort(), REQUEST_TIMEOUT);
        const kick = () => { clearTimeout(timer); timer = setTimeout(() => cut.abort(), STALL_TIMEOUT); };
        let arrived = false;
        try {
          const response = await deps.fetch(url, {
            headers: { Authorization: `Bearer ${grant}`, Range: `bytes=${from}-${to}` },
            signal: signal ? AbortSignal.any([signal, cut.signal]) : cut.signal,
            cache: "no-store",
          });
          kick();
          if (response.status === 401 || response.status === 403 || response.status === 404) {
            throw new CustodyError("SnipShare no longer has this clip, or the permission ran out. "
              + "Schedule it again from SnipShare.", "gone");
          }
          let total;
          let start;
          if (response.status === 206) {
            const match = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(response.headers.get("Content-Range") || "");
            if (!match) throw new Error("no range in the answer");
            start = Number(match[1]);
            total = Number(match[3]);
          } else if (response.status === 200) {
            start = 0;
            total = Number(response.headers.get("Content-Length"));
          } else if (response.status === 416) {
            const match = /\/(\d+)$/.exec(response.headers.get("Content-Range") || "");
            total = match ? Number(match[1]) : NaN;
            if (Number.isFinite(total) && total < from) {
              await restart();
              throw new CustodyError("The clip on SnipShare is not the size it was. Schedule it again.", "size");
            }
            throw new Error(`status ${response.status}`);
          } else {
            throw new Error(`status ${response.status}`);
          }
          if (!Number.isFinite(total) || total <= 0) throw new Error("no size in the answer");
          if (size !== null && total !== size) {
            await restart();
            throw new CustodyError("The clip on SnipShare is not the size it was. Schedule it again.", "size");
          }
          size = total;
          if (!admitted) {
            // Limits and room are checked against the server's figure, before a byte
            // more is kept (FR-18, Section 8.2).
            if (admit) await admit(size);
            await room(ROOM_FACTOR * (size - from));
            admitted = true;
          }
          if (start !== from) {
            if (start !== 0) throw new Error("the server answered a different range");
            // The whole file again: what was kept is replaced, not joined to.
            await restart();
          }
          const reader = response.body.getReader();
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            kick();
            arrived = true;
            failures = 0;
            buffer.push(value);
            buffered += value.length;
            if (have() > size) {
              try { await reader.cancel(); } catch { /* gone */ }
              await restart();
              throw new CustodyError("The clip arrived the wrong size. Try again.", "size");
            }
            let stored = false;
            if (buffered >= PART_BYTES) { await store(false); stored = true; }
            if (have() === size) { await store(true); stored = true; }
            if (onProgress) onProgress({ have: have(), size, stored });
          }
        } catch (err) {
          clearTimeout(timer);
          // A failure from here on is a word for the person, not a dropped line.
          if (err && typeof err.code === "string") throw err;
          if (stopped()) throw new CustodyError("Stopped.", "stopped");
          // Keep what arrived of the open part, so a stopped worker does not fetch it again.
          if (buffered && arrived) {
            try { await store(true); } catch (keepErr) {
              if (keepErr && keepErr.code === "quota") throw keepErr;
            }
          }
          failures += 1;
          if (failures >= ATTEMPTS) {
            throw new CustodyError("The connection kept dropping while keeping the clip. Try again.", "network");
          }
          await deps.sleep(backoff(failures), signal);
          continue;
        } finally {
          clearTimeout(timer);
        }
      }
      if (have() !== size) throw new CustodyError("The clip arrived the wrong size. Try again.", "size");
      const blob = await read(id);
      if (!blob || blob.size !== size) {
        await drop(id);
        throw new CustodyError("The clip arrived the wrong size. Try again.", "size");
      }
      return { size, sha256: await hashOf(blob) };
    }

    return { fetch: fetchClip, read, verify, drop, usage, sweep, parts };
  }

  const api = { make, CustodyError, partKey, PART_BYTES, REQUEST_TIMEOUT, STALL_TIMEOUT, PREFIX };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SnipCustody = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
