// Fragmented MP4 and WebM, read as YouTube's player appends them.
//
// The player hands Media Source Extensions a byte stream per SourceBuffer: a
// header, then fragments, in whatever order it fetched them. A seek, a quality
// change or a recreated MediaSource restarts that stream somewhere else, and a seek
// can abandon a fragment halfway through its payload. So nothing here trusts append
// order or a declared length on its own (docs/extension.md, DECISIONS.md D-083):
//
//   - a run is a stretch of bytes the player appended without an abort() or a new
//     header in between; inside a run the bytes are one continuous stream
//   - each run is parsed incrementally, as appends arrive, keeping only whole
//     fragments; whatever is half arrived when the run ends is dropped (fMP4) or kept
//     up to its last whole block (WebM, whose blocks decode on their own)
//   - fragments are filed under the header they decode with, keyed by that header's
//     sample description, and deduplicated on their own timestamp
//   - picking a window takes the header group that best covers it
//
// One implementation, loaded into YouTube's page by the extension and required by
// the Node tests. No DOM, no browser API, no dependency.
(function (root) {
  "use strict";

  const EBML = 0x1a45dfa3;
  const SEGMENT = 0x18538067;
  const CLUSTER = 0x1f43b675;
  const TRACKS = 0x1654ae6b;
  const SEEK_HEAD = 0x114d9b74;
  const CUES = 0x1c53bb6b;
  const TIMECODE_SCALE = 0x2ad7b1;
  const TIMECODE = 0xe7;
  const SIMPLE_BLOCK = 0xa3;
  const BLOCK_GROUP = 0xa0;
  const BLOCK = 0xa1;
  const UNKNOWN_SIZE = Uint8Array.of(0x01, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff);
  const MP4_TOP = new Set(["ftyp", "moov", "moof", "mdat", "sidx", "emsg", "styp", "free", "prft", "skip"]);

  // -- bytes -----------------------------------------------------------------

  function concat(parts, total) {
    if (parts.length === 1) return parts[0];
    const out = new Uint8Array(total === undefined ? parts.reduce((n, p) => n + p.length, 0) : total);
    let at = 0;
    for (const part of parts) { out.set(part, at); at += part.length; }
    return out;
  }

  // A queue of byte chunks that can be peeked and taken from the front without
  // copying everything that arrived, which matters when an mdat is several MB and
  // arrives in 3 KB appends.
  class Pending {
    constructor() { this.parts = []; this.length = 0; }
    push(bytes) { if (bytes.length) { this.parts.push(bytes); this.length += bytes.length; } }
    clear() { this.parts = []; this.length = 0; }
    peek(n) {
      n = Math.min(n, this.length);
      const out = new Uint8Array(n);
      let at = 0;
      for (const part of this.parts) {
        if (at >= n) break;
        const take = Math.min(part.length, n - at);
        out.set(part.subarray(0, take), at);
        at += take;
      }
      return out;
    }
    take(n) {
      const out = this.peek(n);
      let left = out.length;
      while (left > 0) {
        const first = this.parts[0];
        if (first.length <= left) { this.parts.shift(); left -= first.length; }
        else { this.parts[0] = first.subarray(left); left = 0; }
      }
      this.length -= out.length;
      return out;
    }
    all() { return this.peek(this.length); }
  }

  function u32(b, at) { return ((b[at] << 24) >>> 0) + (b[at + 1] << 16) + (b[at + 2] << 8) + b[at + 3]; }
  function u64(b, at) { return u32(b, at) * 4294967296 + u32(b, at + 4); }
  function type4(b, at) { return String.fromCharCode(b[at], b[at + 1], b[at + 2], b[at + 3]); }

  // FNV-1a, enough to tell two sample descriptions apart. Not security.
  function fingerprint(bytes) {
    let h = 0x811c9dc5;
    for (let i = 0; i < bytes.length; i++) { h ^= bytes[i]; h = Math.imul(h, 0x01000193) >>> 0; }
    return h.toString(16).padStart(8, "0");
  }

  // -- fMP4 ------------------------------------------------------------------

  function mp4Children(box, start) {
    const out = [];
    let at = start;
    while (at + 8 <= box.length) {
      let size = u32(box, at);
      const type = type4(box, at + 4);
      if (size === 1 && at + 16 <= box.length) size = u64(box, at + 8);
      if (size < 8 || at + size > box.length) break;
      out.push({ type, at, size, bytes: box.subarray(at, at + size) });
      at += size;
    }
    return out;
  }

  function mp4Find(box, path) {
    let current = box;
    for (const name of path) {
      const hit = mp4Children(current, 8).find((c) => c.type === name);
      if (!hit) return null;
      current = hit.bytes;
    }
    return current;
  }

  function mp4Init(ftyp, moov, mime) {
    const mdhd = mp4Find(moov, ["trak", "mdia", "mdhd"]);
    const timescale = mdhd ? (mdhd[8] === 1 ? u32(mdhd, 28) : u32(mdhd, 20)) : 1000;
    const tkhd = mp4Find(moov, ["trak", "tkhd"]);
    const width = tkhd ? u32(tkhd, tkhd.length - 8) >>> 16 : 0;
    const height = tkhd ? u32(tkhd, tkhd.length - 4) >>> 16 : 0;
    const stsd = mp4Find(moov, ["trak", "mdia", "minf", "stbl", "stsd"]) || moov;
    const trex = mp4Find(moov, ["mvex", "trex"]);
    const head = ftyp ? concat([ftyp, moov]) : moov;
    return {
      key: `${mime}|${width}x${height}|${fingerprint(stsd)}`,
      bytes: head, timescale, width, height,
      defaultDuration: trex && trex.length >= 24 ? u32(trex, 20) : 0,
    };
  }

  function mp4FragmentTimes(moof, init) {
    const tfdt = mp4Find(moof, ["traf", "tfdt"]);
    if (!tfdt) return null;
    const base = tfdt[8] === 1 ? u64(tfdt, 12) : u32(tfdt, 12);
    const tfhd = mp4Find(moof, ["traf", "tfhd"]);
    const trun = mp4Find(moof, ["traf", "trun"]);
    let length = 0;
    if (trun) {
      let duration = init.defaultDuration;
      if (tfhd) {
        const flags = (tfhd[9] << 16) | (tfhd[10] << 8) | tfhd[11];
        let at = 16;
        if (flags & 0x01) at += 8;
        if (flags & 0x02) at += 4;
        if (flags & 0x08) duration = u32(tfhd, at);
      }
      const flags = (trun[9] << 16) | (trun[10] << 8) | trun[11];
      const count = u32(trun, 12);
      let at = 16 + (flags & 0x01 ? 4 : 0) + (flags & 0x04 ? 4 : 0);
      if (flags & 0x100) {
        const step = 4 * [0x100, 0x200, 0x400, 0x800].filter((bit) => flags & bit).length;
        for (let i = 0; i < count && at + 4 <= trun.length; i++, at += step) length += u32(trun, at);
      } else {
        length = duration * count;
      }
    }
    return { t0: base / init.timescale, t1: (base + length) / init.timescale, tick: base };
  }

  // -- WebM ------------------------------------------------------------------

  // An EBML element header at `at`: { id, idLength, size, sizeLength, unknown }.
  // Null when the bytes run out before the header does.
  function ebmlHeader(b, at) {
    if (at >= b.length) return null;
    const first = b[at];
    const idLength = first & 0x80 ? 1 : first & 0x40 ? 2 : first & 0x20 ? 3 : first & 0x10 ? 4 : 0;
    if (!idLength || at + idLength >= b.length) return null;
    let id = 0;
    for (let i = 0; i < idLength; i++) id = id * 256 + b[at + i];
    const lead = b[at + idLength];
    let sizeLength = 1;
    let mask = 0x80;
    while (sizeLength <= 8 && !(lead & mask)) { mask >>= 1; sizeLength++; }
    if (sizeLength > 8 || at + idLength + sizeLength > b.length) return null;
    let size = lead & (mask - 1);
    let allOnes = size === mask - 1;
    for (let i = 1; i < sizeLength; i++) {
      const byte = b[at + idLength + i];
      size = size * 256 + byte;
      if (byte !== 0xff) allOnes = false;
    }
    return { id, idLength, size, sizeLength, unknown: allOnes, head: idLength + sizeLength };
  }

  function readUint(b, at, length) {
    let value = 0;
    for (let i = 0; i < length; i++) value = value * 256 + b[at + i];
    return value;
  }

  // The cluster's timecode, and how far its blocks reach, from what has arrived.
  // `whole` is how many bytes from the cluster's start are complete children.
  function clusterFacts(b, bodyAt, end) {
    let at = bodyAt;
    let timecode = null;
    let last = null;
    let previous = null;
    let whole = bodyAt;
    while (at < end) {
      const h = ebmlHeader(b, at);
      if (!h || h.unknown) break;
      const dataAt = at + h.head;
      if (h.id === BLOCK_GROUP) {
        // Step inside: its Block carries the timing.
        if (dataAt + h.size > end) break;
        let inner = dataAt;
        while (inner < dataAt + h.size) {
          const ih = ebmlHeader(b, inner);
          if (!ih) break;
          if (ih.id === BLOCK) {
            const rel = blockTime(b, inner + ih.head);
            if (rel !== null) { previous = last; last = rel; }
          }
          inner += ih.head + ih.size;
        }
        at = dataAt + h.size;
        whole = at;
        continue;
      }
      if (dataAt + h.size > end) break;
      if (h.id === TIMECODE) timecode = readUint(b, dataAt, h.size);
      else if (h.id === SIMPLE_BLOCK) {
        const rel = blockTime(b, dataAt);
        if (rel !== null) { previous = last; last = rel; }
      }
      at = dataAt + h.size;
      whole = at;
    }
    return { timecode, last, previous, whole };
  }

  // A block's timecode, relative to its cluster: after the track number (a vint),
  // a signed 16 bit integer.
  function blockTime(b, at) {
    const lead = b[at];
    if (lead === undefined) return null;
    let length = 1;
    let mask = 0x80;
    while (length <= 8 && !(lead & mask)) { mask >>= 1; length++; }
    if (at + length + 2 > b.length) return null;
    const raw = (b[at + length] << 8) | b[at + length + 1];
    return raw & 0x8000 ? raw - 0x10000 : raw;
  }

  // -- a SourceBuffer's record -------------------------------------------------

  class Buffer {
    constructor(mime) {
      this.mime = mime;
      this.kind = mime.startsWith("video/") ? "video" : "audio";
      this.container = /webm/.test(mime) ? "webm" : "mp4";
      this.pending = new Pending();
      this.inits = new Map();   // key -> init
      this.groups = new Map();  // init key -> Map(tick -> fragment)
      this.init = null;         // the header the current run decodes with
      this.ftyp = null;
      this.moof = null;
      this.offset = 0;
      this.webmInit = null;     // { parts, total } while a WebM header is arriving
      this.bytes = 0;
    }

    // One append, as the player made it. `offset` is the SourceBuffer's
    // timestampOffset at that moment, which shifts where the media lands.
    append(bytes, offset) {
      if (!(bytes instanceof Uint8Array)) bytes = new Uint8Array(bytes);
      if (typeof offset === "number" && offset !== this.offset) {
        this.offset = offset;
      }
      if (this.isHeader(bytes)) this.endRun();
      this.pending.push(bytes);
      if (this.container === "mp4") this.parseMp4(); else this.parseWebm(false);
    }

    // The player called abort(): whatever is half parsed will never be finished.
    abort() { this.endRun(); }

    // A new mime type on the same buffer; the next header says what it is.
    changeType(mime) {
      this.endRun();
      this.mime = mime;
      this.container = /webm/.test(mime) ? "webm" : "mp4";
    }

    isHeader(bytes) {
      if (bytes.length < 8) return false;
      if (this.container === "mp4") return type4(bytes, 4) === "ftyp" || type4(bytes, 4) === "moov";
      return u32(bytes, 0) === EBML;
    }

    endRun() {
      if (this.container === "webm" && this.pending.length) this.parseWebm(true);
      this.pending.clear();
      this.moof = null;
      this.webmInit = null;
    }

    keep(fragment) {
      if (!this.init) return;
      let group = this.groups.get(this.init.key);
      if (!group) { group = new Map(); this.groups.set(this.init.key, group); }
      // Times here are where the player shows the fragment; `shift` remembers how far
      // that is from the bytes' own times, which the renderer cuts by.
      fragment.shift = this.offset;
      fragment.t0 += this.offset;
      fragment.t1 += this.offset;
      const had = group.get(fragment.tick);
      // The same fragment can arrive twice, once cut short and once whole.
      if (had && had.bytes.length >= fragment.bytes.length) return;
      if (had) this.bytes -= had.bytes.length;
      group.set(fragment.tick, fragment);
      this.bytes += fragment.bytes.length;
    }

    parseMp4() {
      while (this.pending.length >= 8) {
        const head = this.pending.peek(16);
        let size = u32(head, 0);
        const type = type4(head, 4);
        if (size === 1) {
          if (head.length < 16) return;
          size = u64(head, 8);
        }
        if (!MP4_TOP.has(type) || size < 8) {
          // Not a box boundary: the run lost its place. Nothing after this can be
          // trusted until the next header or abort starts a new run.
          this.pending.clear();
          this.moof = null;
          return;
        }
        if (this.pending.length < size) return;
        const box = this.pending.take(size);
        if (type === "ftyp") this.ftyp = box;
        else if (type === "moov") {
          const init = mp4Init(this.ftyp, box, this.mime);
          this.inits.set(init.key, init);
          this.init = init;
        } else if (type === "moof") this.moof = box;
        else if (type === "mdat" && this.moof && this.init) {
          const times = mp4FragmentTimes(this.moof, this.init);
          if (times) this.keep({ ...times, bytes: concat([this.moof, box]) });
          this.moof = null;
        }
      }
    }

    // `final` means the run is over: a cluster that never finished is kept up to
    // its last whole block.
    parseWebm(final) {
      for (;;) {
        if (this.webmInit) {
          if (!this.readWebmInit()) return;
          continue;
        }
        const head = this.pending.peek(12);
        if (head.length < 4) return;
        const id = u32(head, 0);
        if (id === EBML) { this.webmInit = { parts: [], total: 0 }; continue; }
        if (id !== CLUSTER) {
          // Cues, tags, or a run that lost its place: skip one whole element if it
          // is whole, otherwise wait; anything unparseable ends the run.
          const h = ebmlHeader(head, 0);
          if (!h) { if (head.length >= 12) this.pending.clear(); return; }
          if (h.unknown) { this.pending.clear(); return; }
          if (this.pending.length < h.head + h.size) return;
          this.pending.take(h.head + h.size);
          continue;
        }
        const h = ebmlHeader(head, 0);
        if (!h) return;
        const available = this.pending.length;
        if (!h.unknown && available >= h.head + h.size) {
          const cluster = this.pending.take(h.head + h.size);
          this.keepCluster(cluster, h.head, cluster.length, false);
          continue;
        }
        if (h.unknown && !final) {
          // Ends where the next Cluster starts, which has not arrived yet.
          const all = this.pending.all();
          const next = findCluster(all, h.head);
          if (next < 0) return;
          const cluster = this.pending.take(next);
          this.keepCluster(cluster, h.head, cluster.length, true);
          continue;
        }
        if (final) {
          const cluster = this.pending.take(available);
          this.keepCluster(cluster, h.head, cluster.length, true);
        }
        return;
      }
    }

    // EBML header, then the Segment's own header, then every child of the Segment
    // up to the first Cluster: that is the init. Returns false while waiting.
    readWebmInit() {
      const state = this.webmInit;
      for (;;) {
        const head = this.pending.peek(12);
        const h = ebmlHeader(head, 0);
        if (!h) return false;
        if (h.id === CLUSTER) {
          const bytes = concat(state.parts, state.total);
          const tracksAt = findId(bytes, TRACKS);
          const scaleAt = findId(bytes, TIMECODE_SCALE);
          let scale = 1000000;
          if (scaleAt >= 0) {
            const sh = ebmlHeader(bytes, scaleAt);
            if (sh) scale = readUint(bytes, scaleAt + sh.head, sh.size);
          }
          const init = {
            key: `${this.mime}|${fingerprint(tracksAt >= 0 ? bytes.subarray(tracksAt) : bytes)}`,
            bytes, timescale: 1e9 / scale, width: 0, height: 0,
          };
          this.inits.set(init.key, init);
          this.init = init;
          this.webmInit = null;
          return true;
        }
        if (h.id === SEGMENT) {
          // The Segment is the container of everything; keep only its header, and
          // say its size is unknown, because what follows is our own selection.
          this.pending.take(h.head);
          state.parts.push(Uint8Array.of(0x18, 0x53, 0x80, 0x67), UNKNOWN_SIZE);
          state.total += 4 + UNKNOWN_SIZE.length;
          continue;
        }
        if (h.unknown) { this.pending.clear(); this.webmInit = null; return false; }
        if (this.pending.length < h.head + h.size) return false;
        const element = this.pending.take(h.head + h.size);
        // SeekHead and Cues point at byte offsets in YouTube's whole file, which
        // mean nothing in ours. Leaving them out keeps a reader from chasing them.
        if (h.id !== SEEK_HEAD && h.id !== CUES) {
          state.parts.push(element);
          state.total += element.length;
        }
      }
    }

    keepCluster(cluster, bodyAt, end, cut) {
      const facts = clusterFacts(cluster, bodyAt, end);
      if (facts.timecode === null || facts.last === null) return;
      let bytes = cluster;
      if (cut || facts.whole < end) {
        // Re-marked as unknown size so a reader finds the next cluster by its ID
        // rather than trusting a length that is no longer true.
        bytes = concat([Uint8Array.of(0x1f, 0x43, 0xb6, 0x75), UNKNOWN_SIZE,
          cluster.subarray(bodyAt, facts.whole)]);
      }
      const step = facts.previous === null ? 20 : Math.max(0, facts.last - facts.previous);
      const scale = this.init ? this.init.timescale : 1000;
      this.keep({
        tick: facts.timecode,
        t0: facts.timecode / scale,
        t1: (facts.timecode + facts.last + step) / scale,
        bytes,
      });
    }

    // The player evicted [start, end) from its own buffer; so do we. Only what lies
    // wholly inside goes, the way MSE removes coded frames.
    remove(start, end) {
      for (const group of this.groups.values()) {
        for (const [tick, fragment] of group) {
          if (fragment.t0 >= start && fragment.t1 <= end) {
            group.delete(tick);
            this.bytes -= fragment.bytes.length;
          }
        }
      }
    }

    // Drop everything outside [from, to]: the memory ceiling's last resort.
    keepOnly(from, to) {
      for (const group of this.groups.values()) {
        for (const [tick, fragment] of group) {
          if (fragment.t1 < from || fragment.t0 > to) {
            group.delete(tick);
            this.bytes -= fragment.bytes.length;
          }
        }
      }
    }
  }

  function findCluster(bytes, from) {
    for (let i = from; i + 4 <= bytes.length; i++) {
      if (bytes[i] === 0x1f && bytes[i + 1] === 0x43 && bytes[i + 2] === 0xb6 && bytes[i + 3] === 0x75) return i;
    }
    return -1;
  }

  function findId(bytes, id) {
    const want = [];
    for (let v = id; v > 0; v = Math.floor(v / 256)) want.unshift(v & 0xff);
    outer: for (let i = 0; i + want.length <= bytes.length; i++) {
      for (let j = 0; j < want.length; j++) if (bytes[i + j] !== want[j]) continue outer;
      return i;
    }
    return -1;
  }

  // -- picking a window --------------------------------------------------------

  // Every buffer of one kind, merged by the header each fragment decodes with.
  function groupsOf(buffers) {
    const merged = new Map();
    for (const buffer of buffers) {
      for (const [key, group] of buffer.groups) {
        let entry = merged.get(key);
        if (!entry) {
          entry = { init: buffer.inits.get(key), fragments: new Map() };
          merged.set(key, entry);
        }
        for (const [tick, fragment] of group) {
          const had = entry.fragments.get(tick);
          if (!had || had.bytes.length < fragment.bytes.length) entry.fragments.set(tick, fragment);
        }
      }
    }
    return [...merged.values()].filter((entry) => entry.init);
  }

  function spansOf(fragments) {
    const sorted = [...fragments].sort((a, b) => a.t0 - b.t0);
    const out = [];
    for (const f of sorted) {
      const last = out[out.length - 1];
      if (last && f.t0 <= last[1] + 0.05) last[1] = Math.max(last[1], f.t1);
      else out.push([f.t0, f.t1]);
    }
    return out;
  }

  function coveredBy(spans, start, end) {
    let total = 0;
    for (const [a, b] of spans) total += Math.max(0, Math.min(b, end) - Math.max(a, start));
    return total;
  }

  // How far from `from` the best group reaches without a hole; `from` itself if
  // nothing holds it. What the walk watches to know when to move on.
  function reach(buffers, from) {
    let best = from;
    for (const entry of groupsOf(buffers)) {
      for (const [a, b] of spansOf(entry.fragments.values())) {
        if (a <= from + 0.05 && b > best) best = b;
      }
    }
    return best;
  }

  // The header and the fragments that cover [start, end], from the group that
  // covers it best: a higher resolution wins a tie.
  function pick(buffers, start, end, pad) {
    pad = pad === undefined ? 1 : pad;
    let best = null;
    for (const entry of groupsOf(buffers)) {
      const covered = Math.round(coveredBy(spansOf(entry.fragments.values()), start, end) * 10);
      const area = (entry.init.width || 0) * (entry.init.height || 0);
      if (!best || covered > best.covered || (covered === best.covered && area > best.area)) {
        best = { entry, covered, area };
      }
    }
    if (!best) return null;
    const chosen = [...best.entry.fragments.values()]
      .filter((f) => f.t1 > start - pad && f.t0 < end + pad)
      .sort((a, b) => a.t0 - b.t0);
    if (!chosen.length) return null;
    const parts = [best.entry.init.bytes, ...chosen.map((f) => f.bytes)];
    return {
      parts,
      size: parts.reduce((n, p) => n + p.length, 0),
      from: chosen[0].t0,
      to: Math.max(...chosen.map((f) => f.t1)),
      covered: best.covered / 10,
      width: best.entry.init.width,
      height: best.entry.init.height,
      key: best.entry.init.key,
      // Non-zero when the player placed these bytes away from their own times. The
      // renderer cuts by the bytes' times, so a caller must not send such a file.
      shifted: chosen.some((f) => Math.abs(f.shift || 0) > 0.001),
    };
  }

  const api = { Buffer, pick, reach, spansOf, groupsOf, concat, fingerprint };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.WAStatusMedia = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
