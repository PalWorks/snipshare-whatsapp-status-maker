// media.js against fragmented MP4 and WebM that ffmpeg makes on the spot, fed in
// the awkward ways YouTube's player feeds a SourceBuffer: small uneven appends, an
// abort halfway through a fragment, a header for a different encoding mid-stream,
// the same fragment twice. Every result is handed back to ffmpeg, which has to read
// it without a single error. Run with `node --test src/test`, or through
// pytest, which runs it when Node is installed. See DECISIONS.md D-083.
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync, spawnSync } = require("node:child_process");

const media = require("../media.js");

const dir = fs.mkdtempSync(path.join(os.tmpdir(), "wastatus-media-"));
test.after(() => fs.rmSync(dir, { recursive: true, force: true }));
const has = (bin) => { try { execFileSync(bin, ["-version"], { stdio: "ignore" }); return true; } catch { return false; } };
const skip = !(has("ffmpeg") && has("ffprobe")) && "needs ffmpeg and ffprobe";

function ffmpeg(args) {
  execFileSync("ffmpeg", ["-y", "-hide_banner", "-loglevel", "error", ...args], { stdio: "pipe" });
}

function make(name, args) {
  const out = path.join(dir, name);
  if (!fs.existsSync(out)) ffmpeg([...args, out]);
  return new Uint8Array(fs.readFileSync(out));
}

// Fragmented MP4 cut on every keyframe, one a second, the way DASH segments are.
const mp4 = (size) => make(`v${size}.mp4`, [
  "-f", "lavfi", "-i", `testsrc2=s=${size}:r=30:d=10`,
  "-c:v", "libx264", "-preset", "ultrafast", "-g", "30", "-keyint_min", "30",
  "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-f", "mp4",
]);
// WebM Opus with a cluster a second, which is how YouTube's audio arrives.
const webm = () => make("a.webm", [
  "-f", "lavfi", "-i", "sine=f=440:sample_rate=48000:d=10",
  "-c:a", "libopus", "-cluster_time_limit", "1000", "-f", "webm",
]);

// A seeded generator, so a failing split can be reproduced.
function chunks(bytes, seed, max = 9000) {
  let state = seed;
  const out = [];
  for (let at = 0; at < bytes.length;) {
    state = (state * 1103515245 + 12345) >>> 0;
    const size = 1 + (state % max);
    out.push(bytes.subarray(at, at + size));
    at += size;
  }
  return out;
}

// Where each top-level piece starts: the header, then each fragment.
function boundaries(bytes, container) {
  const marks = [];
  if (container === "mp4") {
    for (let at = 0; at + 8 <= bytes.length;) {
      const size = ((bytes[at] << 24) >>> 0) + (bytes[at + 1] << 16) + (bytes[at + 2] << 8) + bytes[at + 3];
      const type = String.fromCharCode(...bytes.subarray(at + 4, at + 8));
      marks.push({ at, type, size });
      at += size;
    }
  } else {
    for (let i = 0; i + 4 <= bytes.length; i++) {
      if (bytes[i] === 0x1f && bytes[i + 1] === 0x43 && bytes[i + 2] === 0xb6 && bytes[i + 3] === 0x75) {
        marks.push({ at: i, type: "cluster" });
      }
    }
  }
  return marks;
}

function feed(buffer, bytes, seed, offset) {
  for (const piece of chunks(bytes, seed)) buffer.append(piece.slice(), offset);
}

function write(picked, name) {
  const out = path.join(dir, name);
  fs.writeFileSync(out, media.concat(picked.parts));
  return out;
}

// ffmpeg's own Opus muxer ends its file with a packet that ffmpeg's own decoder
// complains about; the source files made here say it too. Anything else is ours.
const KNOWN = /Error parsing Opus packet header/;

function readsClean(file) {
  const run = spawnSync("ffmpeg", ["-v", "error", "-xerror", "-i", file, "-f", "null", "-"]);
  const complaints = run.stderr.toString().split("\n").filter((l) => l.trim() && !KNOWN.test(l));
  assert.deepEqual(complaints, [], `${path.basename(file)}: ${complaints.join(" / ")}`);
  return run.status === 0;
}

function packets(file) {
  const out = execFileSync("ffprobe", ["-v", "error", "-select_streams", "0", "-show_entries",
    "packet=pts_time", "-of", "csv=p=0", file], { stdio: ["ignore", "pipe", "ignore"] })
    .toString().trim().split("\n").map((line) => parseFloat(line));
  return { first: Math.min(...out), last: Math.max(...out), count: out.length };
}

test("fMP4 in uneven appends: every fragment, timed, and a clean file back", { skip }, () => {
  const bytes = mp4("320x180");
  const buffer = new media.Buffer('video/mp4; codecs="avc1.42c00d"');
  feed(buffer, bytes, 7);
  const [group] = media.groupsOf([buffer]);
  const fragments = [...group.fragments.values()].sort((a, b) => a.t0 - b.t0);
  assert.equal(fragments.length, 10);
  assert.ok(Math.abs(fragments[3].t0 - 3) < 0.001 && Math.abs(fragments[3].t1 - 4) < 0.001);
  const picked = media.pick([buffer], 2.5, 6.2, 0);
  assert.equal(picked.width, 320);
  assert.ok(picked.from <= 2.5 && picked.to >= 6.2);
  const file = write(picked, "mp4-window.mp4");
  assert.ok(readsClean(file));
  const p = packets(file);
  assert.ok(Math.abs(p.first - 2) < 0.05, `starts at ${p.first}`);
  assert.ok(p.last >= 6.9 && p.last < 7.05, `ends at ${p.last}`);
});

test("an abort halfway through a fragment loses that fragment and nothing else", { skip }, () => {
  const bytes = mp4("320x180");
  const marks = boundaries(bytes, "mp4");
  const moofs = marks.filter((m) => m.type === "moof");
  const header = bytes.subarray(0, moofs[0].at);
  const buffer = new media.Buffer('video/mp4; codecs="avc1.42c00d"');
  // Fragments 0 to 3, then half of 4's payload, then the player seeks back to 2.
  const halfway = marks.find((m) => m.type === "mdat" && m.at > moofs[4].at);
  feed(buffer, bytes.subarray(0, halfway.at + Math.floor(halfway.size / 2)), 3);
  buffer.abort();
  feed(buffer, header, 11);
  feed(buffer, bytes.subarray(moofs[2].at), 13);
  const picked = media.pick([buffer], 0, 10, 0);
  assert.equal(media.groupsOf([buffer]).length, 1, "the same header again is the same group");
  const file = write(picked, "mp4-abort.mp4");
  assert.ok(readsClean(file));
  assert.equal(packets(file).count, 300);
});

test("without the abort, a lost place in the stream is noticed, not trusted", { skip }, () => {
  const bytes = mp4("320x180");
  const marks = boundaries(bytes, "mp4");
  const moofs = marks.filter((m) => m.type === "moof");
  const buffer = new media.Buffer('video/mp4; codecs="avc1.42c00d"');
  feed(buffer, bytes.subarray(0, moofs[3].at + 100), 5); // stops inside fragment 3's moof
  feed(buffer, bytes.subarray(moofs[6].at + 7), 9);      // resumes mid box, no header, no abort
  const fragments = [...media.groupsOf([buffer])[0].fragments.values()];
  assert.equal(fragments.length, 3, "fragments 0, 1 and 2 only");
  assert.ok(readsClean(write(media.pick([buffer], 0, 3, 0), "mp4-lost.mp4")));
});

test("a second encoding mid-stream is its own group, and the best cover wins", { skip }, () => {
  const small = mp4("320x180");
  const large = mp4("640x360");
  const smallMoofs = boundaries(small, "mp4").filter((m) => m.type === "moof");
  const largeMoofs = boundaries(large, "mp4").filter((m) => m.type === "moof");
  const buffer = new media.Buffer('video/mp4; codecs="avc1.42c00d"');
  feed(buffer, small.subarray(0, smallMoofs[5].at), 17);           // 320x180, 0 to 5s
  feed(buffer, large.subarray(0, largeMoofs[0].at), 19);           // a new header
  feed(buffer, large.subarray(largeMoofs[3].at), 23);              // 640x360, 3 to 10s
  assert.equal(media.groupsOf([buffer]).length, 2);
  assert.equal(media.pick([buffer], 6, 9, 0).width, 640);
  assert.equal(media.pick([buffer], 0, 2, 0).width, 320);
  assert.equal(media.pick([buffer], 3.2, 4.8, 0).width, 640, "a tie goes to the larger picture");
  assert.ok(readsClean(write(media.pick([buffer], 0, 2, 0), "mp4-small.mp4")));
  assert.ok(readsClean(write(media.pick([buffer], 6, 9, 0), "mp4-large.mp4")));
});

test("the same fragment twice is kept once, and the longer copy wins", { skip }, () => {
  const bytes = mp4("320x180");
  const buffer = new media.Buffer('video/mp4; codecs="avc1.42c00d"');
  feed(buffer, bytes, 29);
  const before = buffer.bytes;
  feed(buffer, bytes, 31);
  assert.equal(buffer.bytes, before);
  assert.equal([...media.groupsOf([buffer])[0].fragments.values()].length, 10);
});

test("remove() follows the player: only what lies wholly inside goes", { skip }, () => {
  const buffer = new media.Buffer('video/mp4; codecs="avc1.42c00d"');
  feed(buffer, mp4("320x180"), 37);
  buffer.remove(0, 4.5);
  const left = [...media.groupsOf([buffer])[0].fragments.values()].map((f) => Math.round(f.t0));
  assert.deepEqual(left.sort((a, b) => a - b), [4, 5, 6, 7, 8, 9]);
  assert.equal(media.reach([buffer], 4), 10);
  assert.equal(media.reach([buffer], 2), 2, "nothing holds 2s any more");
});

test("timestampOffset moves where the media lands", { skip }, () => {
  const buffer = new media.Buffer('video/mp4; codecs="avc1.42c00d"');
  feed(buffer, mp4("320x180"), 41, 100);
  assert.equal(media.reach([buffer], 100), 110);
});

test("WebM Opus in uneven appends, cut short by an abort, still reads clean", { skip }, () => {
  const bytes = webm();
  const clusters = boundaries(bytes, "webm");
  assert.ok(clusters.length >= 9, `${clusters.length} clusters`);
  const header = bytes.subarray(0, clusters[0].at);
  const buffer = new media.Buffer('audio/webm; codecs="opus"');
  // Clusters 0 to 3 and half of 4, an abort, then from 4 again to the end.
  const halfway = clusters[4].at + Math.floor((clusters[5].at - clusters[4].at) / 2);
  feed(buffer, bytes.subarray(0, halfway), 43);
  buffer.abort();
  feed(buffer, header, 47);
  feed(buffer, bytes.subarray(clusters[4].at), 53);
  const picked = media.pick([buffer], 0, 10, 0);
  assert.ok(picked.to > 9.9, `reaches ${picked.to}`);
  const file = write(picked, "webm-abort.webm");
  assert.ok(readsClean(file));
  const p = packets(file);
  assert.ok(p.first < 0.01 && p.last > 9.9, `${p.first} to ${p.last}`);
});

test("a WebM run that ends mid-cluster keeps the blocks that arrived", { skip }, () => {
  const bytes = webm();
  const clusters = boundaries(bytes, "webm");
  const buffer = new media.Buffer('audio/webm; codecs="opus"');
  feed(buffer, bytes.subarray(0, clusters[3].at + Math.floor((clusters[4].at - clusters[3].at) / 2)), 59);
  buffer.abort();
  const picked = media.pick([buffer], 0, 4, 0);
  assert.ok(picked.to > 3.3 && picked.to < 3.7, `kept up to ${picked.to}`);
  assert.ok(readsClean(write(picked, "webm-cut.webm")));
});

test("a run of junk with no header is ignored, not parsed into fragments", { skip }, () => {
  const buffer = new media.Buffer('video/mp4; codecs="avc1.42c00d"');
  buffer.append(new Uint8Array(5000).fill(7));
  assert.equal(media.groupsOf([buffer]).length, 0);
  assert.equal(media.pick([buffer], 0, 1), null);
  const audio = new media.Buffer('audio/webm; codecs="opus"');
  audio.append(new Uint8Array(5000).fill(9));
  assert.equal(media.groupsOf([audio]).length, 0);
});
