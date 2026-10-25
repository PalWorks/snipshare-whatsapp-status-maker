// The service worker: one clip at a time, from the YouTube tab to the renderer
// and back to WhatsApp.
//
// Everything that has to survive is kept somewhere that survives: the job's state
// in chrome.storage.local, the captured files and the clip in IndexedDB. Chrome
// stops an idle service worker after thirty seconds and starts it again on the next
// event, so every step is written to resume from what is stored rather than from
// what was in memory: an upload asks the server how much arrived, a download asks
// for the rest with a Range, a poll simply polls again. See docs/extension.md and
// DECISIONS.md D-082.
"use strict";

// Where SnipShare is. `config.js` in the repository names a local copy; the built
// extension carries the real address (scripts/build_extension.py).
importScripts("config.js");

const DEFAULTS = { server: CONFIG.site, token: "", quality: "hd720" };
const PHASES_ACTIVE = ["capturing", "uploading", "queued", "rendering", "downloading"];
// Chrome stops an extension's worker when a fetch() waits more than 30 seconds for
// its response, so no single request may take that long, however slow the line:
// chunks start small and are sized to take a few seconds each.
const CHUNK_START = 64 * 1024;
const CHUNK_MIN = 32 * 1024;
const REQUEST_TIMEOUT = 25000;     // under Chrome's 30 seconds for a fetch() in a worker
const CHUNK_FAST = 3000;           // a chunk quicker than this doubles the next one
const CHUNK_SLOW = 8000;           // a chunk slower than this halves it
const KEEP_EVERY = 2 * 1024 * 1024; // a download is saved to storage after this much arrives
const ATTEMPTS = 8;                // consecutive failures before giving up a step
const POLL_SILENCE = 10 * 60000;   // how long the renderer may be unreachable
const STALL_TIMEOUT = 30000;       // a download with nothing arriving for this long has dropped
const THUMBS = ["maxresdefault", "sddefault", "hqdefault"];

// -- storage -------------------------------------------------------------------

async function settings() {
  const stored = (await chrome.storage.local.get("settings")).settings || {};
  return { ...DEFAULTS, ...stored };
}

async function getJob() {
  return (await chrome.storage.local.get("job")).job || null;
}

async function saveJob(job) {
  job.updated = Date.now();
  await chrome.storage.local.set({ job });
  badge(job);
  return job;
}

function badge(job) {
  const phase = job && job.phase;
  const text = !phase ? "" : PHASES_ACTIVE.includes(phase) ? "…" : phase === "ready" ? "✓" : phase === "failed" ? "!" : "";
  chrome.action.setBadgeText({ text }).catch(() => {});
  chrome.action.setBadgeBackgroundColor({ color: phase === "failed" ? "#b3261e" : "#1b7f3b" }).catch(() => {});
}

let dbPromise = null;
function db() {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const open = indexedDB.open("wastatus", 1);
      open.onupgradeneeded = () => open.result.createObjectStore("blobs");
      open.onsuccess = () => resolve(open.result);
      open.onerror = () => { dbPromise = null; reject(open.error); };
    });
  }
  return dbPromise;
}

async function idb(mode, work) {
  const store = (await db()).transaction("blobs", mode).objectStore("blobs");
  return new Promise((resolve, reject) => {
    const request = work(store);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

const idbGet = (key) => idb("readonly", (s) => s.get(key));
const idbPut = (key, value) => idb("readwrite", (s) => s.put(value, key));
const idbDelete = (key) => idb("readwrite", (s) => s.delete(key));

async function forgetBlobs(jobKey) {
  const keys = await idb("readonly", (s) => s.getAllKeys());
  for (const key of keys) if (String(key).startsWith(`${jobKey}:`)) await idbDelete(key);
}

// Anything stored for a job that is no longer the job: left behind when the worker
// was stopped between a Stop forgetting the job and deleting its files.
async function sweepBlobs() {
  const job = await getJob();
  const keys = await idb("readonly", (s) => s.getAllKeys());
  for (const key of keys) {
    if (!job || !String(key).startsWith(`${job.key}:`)) await idbDelete(key);
  }
}

// -- talking to the renderer -----------------------------------------------------

class Failure extends Error {
  // `retry` says whether pressing Try again can carry on, and from which phase.
  constructor(message, retryFrom) { super(message); this.retryFrom = retryFrom; }
}

let aborter = new AbortController();

// `signal` replaces the whole-request timeout, for a download whose body may take
// longer than any fixed limit on a slow line; the caller then times out stalls.
async function api(method, path, { body, headers, raw, signal: own } = {}) {
  const { server, token } = await settings();
  if (!token) throw new Failure("Add your access token in Settings first", null);
  const signal = own || AbortSignal.any([aborter.signal, AbortSignal.timeout(REQUEST_TIMEOUT)]);
  const init = { method, signal, headers: { Authorization: `Bearer ${token}`, ...(headers || {}) } };
  if (body !== undefined) {
    if (body instanceof Blob || body instanceof ArrayBuffer || ArrayBuffer.isView(body)) init.body = body;
    else { init.body = JSON.stringify(body); init.headers["Content-Type"] = "application/json"; }
  }
  const response = await fetch(`${server.replace(/\/+$/, "")}/api/v1${path}`, init);
  if (raw) return response;
  let data = null;
  try { data = await response.json(); } catch { data = null; }
  return { status: response.status, data: data || {}, headers: response.headers };
}

// Ends early when the job is stopped, so a backoff never keeps a stopped job alive.
const sleep = (ms) => new Promise((resolve) => {
  const signal = aborter.signal;
  const timer = setTimeout(resolve, ms);
  signal.addEventListener("abort", () => { clearTimeout(timer); resolve(); }, { once: true });
});
const backoff = (attempt) => Math.min(30000, 1000 * 2 ** attempt);

function stopped() { return aborter.signal.aborted; }

// -- the job -----------------------------------------------------------------------

let running = null;

function run() {
  if (!running) {
    running = drive().finally(() => { running = null; });
  }
  return running;
}

// The once a minute wake-up exists only while a clip is in flight. Chrome may clear
// alarms when the browser restarts, so it is made again whenever there is work.
async function drive() {
  for (;;) {
    const job = await getJob();
    if (!job || !PHASES_ACTIVE.includes(job.phase)) {
      await chrome.alarms.clear("wastatus").catch(() => {});
      return;
    }
    if (!(await chrome.alarms.get("wastatus").catch(() => null))) {
      await chrome.alarms.create("wastatus", { periodInMinutes: 1 });
    }
    const before = job.phase;
    try {
      if (job.phase === "capturing") await capture(job);
      else if (job.phase === "uploading") await upload(job);
      else if (job.phase === "queued" || job.phase === "rendering") await poll(job);
      else if (job.phase === "downloading") await download(job);
    } catch (err) {
      if (stopped()) return;
      const fresh = await getJob();
      // Discarded, replaced by a newer clip, or moved on by another path: look
      // again at whatever is stored now rather than recording a stale failure.
      if (!fresh || fresh.key !== job.key || fresh.phase !== before) continue;
      fresh.retryFrom = err instanceof Failure ? err.retryFrom : before;
      fresh.phase = "failed";
      fresh.error = String(err && err.message || err);
      fresh.detail = "";
      await saveJob(fresh);
      return;
    }
  }
}

async function update(job, changes) {
  const fresh = await getJob();
  if (!fresh || fresh.key !== job.key) throw new Failure("This clip was discarded", null);
  if (stopped()) throw new Failure("Stopped", null);
  Object.assign(fresh, changes);
  Object.assign(job, changes);
  return saveJob(fresh);
}

// Written only while this job is still the job: a Stop or a newer clip in the
// meantime would otherwise leave bytes in IndexedDB under a key nothing reads.
async function keepFile(job, kind, blob) {
  const fresh = await getJob();
  if (!fresh || fresh.key !== job.key || stopped()) throw new Failure("Stopped", null);
  await idbPut(`${job.key}:${kind}`, blob);
}

let capturePort = null;

// The video's thumbnail, largest first, or null.
async function thumbnail(videoId) {
  for (const size of THUMBS) {
    try {
      const response = await fetch(`https://i.ytimg.com/vi/${videoId}/${size}.jpg`);
      const blob = response.ok ? await response.blob() : null;
      // YouTube answers a missing size with a small grey placeholder.
      if (blob && blob.size > 3000) return blob;
    } catch { /* the next size */ }
  }
  return null;
}

// Captures the window in the YouTube tab, and the thumbnail beside it.
async function capture(job) {
  const s = await settings();
  if (job.mode === "card" && !(await idbGet(`${job.key}:artwork`))) {
    await update(job, { detail: "Getting the video's picture", progress: 0 });
    const art = await thumbnail(job.videoId);
    if (!art) throw new Failure("Could not get the video's picture from YouTube. Try again", "capturing");
    await keepFile(job, "artwork", art);
  }

  let tab;
  try { tab = await chrome.tabs.get(job.tabId); } catch { tab = null; }
  if (!tab) throw new Failure("The YouTube tab was closed. Open the video again and start over", null);

  let lastSave = 0;
  const blobs = await readWindow(job.tabId, {
    videoId: job.videoId, start: job.start, end: job.end,
    needVideo: job.mode === "video", quality: s.quality,
  }, (progress) => {
    const now = Date.now();
    if (now - lastSave > 500) {
      lastSave = now;
      update(job, { detail: progress.detail, progress: progress.progress }).catch(() => {});
    }
  }, (port) => { capturePort = port; });

  const sizes = {};
  for (const [kind, blob] of Object.entries(blobs)) {
    await keepFile(job, kind, blob);
    sizes[kind] = blob.size;
  }
  const art = await idbGet(`${job.key}:artwork`);
  if (art) sizes.artwork = art.size;
  await update(job, { phase: "uploading", files: sizes, uploads: {}, progress: 0,
                      detail: "Sending it to the renderer" });
}

// Reads [start, end] from the YouTube page in a tab: recorder.js walks the player,
// bridge.js carries the bytes here. Resolves with a Blob per kind. `hold` is handed
// the port, so a Stop can disconnect it, which stops the walk in the page.
function readWindow(tabId, params, onProgress, hold) {
  return new Promise((resolve, reject) => {
    let port;
    try {
      port = chrome.tabs.connect(tabId, { name: "wastatus-tab" });
    } catch {
      reject(new Failure("Reload the YouTube page once, then try again", null));
      return;
    }
    if (hold) hold(port);
    const got = {};
    let finished = false;
    let heard = false;
    // Silence, not length, is what counts: the page reports twice a second while it
    // reads and while an ad plays, so a minute of nothing means it has gone.
    const silent = () => fail(new Failure("Reading the video took too long. Try again", "capturing"));
    let timer = setTimeout(silent, 60000);
    function fail(err) {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      if (hold) hold(null);
      try { port.disconnect(); } catch { /* gone */ }
      reject(err);
    }
    port.onDisconnect.addListener(() => {
      // Nobody answered at all: the page has no listener, because it was open
      // before the extension was installed or updated.
      void chrome.runtime.lastError;
      fail(heard
        ? new Failure("The YouTube tab was reloaded or closed while reading the video. Try again", "capturing")
        : new Failure("Reload the YouTube page once, then try again", "capturing"));
    });
    port.onMessage.addListener(async (message) => {
      heard = true;
      if (finished) return;
      clearTimeout(timer);
      timer = setTimeout(silent, 60000);
      if (message.error) return fail(new Failure(message.error, "capturing"));
      if (message.progress) {
        onProgress(message.progress);
        return;
      }
      if (message.file) { got[message.file.kind] = { meta: message.file, parts: [] }; return; }
      if (message.chunk) {
        const text = atob(message.chunk.b64);
        const bytes = new Uint8Array(text.length);
        for (let i = 0; i < text.length; i++) bytes[i] = text.charCodeAt(i);
        got[message.chunk.kind].parts.push(bytes);
        return;
      }
      if (message.done) {
        finished = true;
        clearTimeout(timer);
        if (hold) hold(null);
        try { port.disconnect(); } catch { /* gone */ }
        const blobs = {};
        for (const [kind, file] of Object.entries(got)) {
          const blob = new Blob(file.parts);
          if (blob.size !== file.meta.size) {
            reject(new Failure(`The ${kind} arrived incomplete. Try again`, "capturing"));
            return;
          }
          blobs[kind] = blob;
        }
        resolve(blobs);
      }
    });
    port.postMessage({ cmd: "capture", ...params });
  });
}

// Sends each file in chunks, resuming from whatever the server says it holds.
function sameClip(remote, job) {
  return remote && remote.video_id === job.videoId && remote.mode === job.mode &&
    Math.abs(remote.start - job.start) < 0.01 && Math.abs(remote.end - Math.min(job.end, job.duration)) < 0.01;
}

async function upload(job) {
  if (job.posting) {
    // The worker stopped between asking for the clip and hearing the answer. If the
    // renderer has it, carry on with that rather than sending everything again.
    try {
      const listed = await api("GET", "/jobs");
      const found = (listed.data.jobs || []).filter((j) => sameClip(j, job) &&
        ["queued", "rendering", "done"].includes(j.state)).pop();
      if (found) {
        await update(job, { phase: "queued", serverJob: found.id, posting: false, progress: 0 });
        return;
      }
    } catch { /* fall through and send again */ }
  }
  const kinds = job.mode === "video" ? ["audio", "video"] : ["audio", "artwork"];
  const total = kinds.reduce((n, kind) => n + (job.files[kind] || 0), 0);
  let chunk = job.chunk || CHUNK_START;
  const sent = {};
  for (const kind of kinds) {
    const blob = await idbGet(`${job.key}:${kind}`);
    if (!blob) throw new Failure("The captured video is gone. Start over", null);
    let uploads = { ...(job.uploads || {}) };
    let entry = uploads[kind];
    let failures = 0;
    for (;;) {
      if (stopped()) throw new Failure("Stopped", null);
      try {
        if (!entry) {
          const made = await api("POST", "/uploads", { body: { kind, size: blob.size } });
          if (made.status === 401) throw new Failure("The renderer did not accept your access token. Check Settings", null);
          // A 5xx is the renderer restarting or Cloudflare between us: try again.
          if (made.status >= 500) throw new Error(`status ${made.status}`);
          if (made.status !== 201) throw new Failure(made.data.error || `The renderer said ${made.status}`, null);
          entry = { id: made.data.id, received: 0, chunk: made.data.chunk };
          uploads = { ...uploads, [kind]: entry };
          await update(job, { uploads });
        }
        const asked = await api("GET", `/uploads/${entry.id}`);
        if (asked.status === 404) { entry = null; continue; } // expired: start this file again
        if (asked.status !== 200) throw new Error(asked.data.error || `status ${asked.status}`);
        let received = asked.data.received;
        while (received < blob.size) {
          if (stopped()) throw new Failure("Stopped", null);
          const size = Math.min(chunk, entry.chunk || chunk, blob.size - received);
          const started = Date.now();
          const put = await api("PUT", `/uploads/${entry.id}`, {
            body: blob.slice(received, received + size),
            headers: { "Content-Range": `bytes ${received}-${received + size - 1}/${blob.size}` },
          });
          if (put.status === 409 && put.data.claimed) {
            throw new Failure("This upload is already being made into a clip", null);
          }
          if (put.status === 200 || put.status === 409) {
            received = put.data.received;
            if (!Number.isInteger(received)) throw new Error("the renderer did not say how much it holds");
          } else if (put.status === 404) {
            entry = null;
            break;
          } else if (put.status === 401) {
            throw new Failure("The renderer did not accept your access token. Check Settings", null);
          } else if (put.status >= 400 && put.status < 500) {
            throw new Failure(put.data.error || `The renderer refused the upload (${put.status})`, null);
          } else {
            throw new Error(`status ${put.status}`);
          }
          // Grow the chunk on a quick connection, shrink it on a slow one, so one
          // chunk never takes long enough to be cut off.
          const took = Date.now() - started;
          if (took < CHUNK_FAST) chunk = Math.min(chunk * 2, entry.chunk || chunk * 2);
          else if (took > CHUNK_SLOW) chunk = Math.max(CHUNK_MIN, Math.floor(chunk / 2));
          failures = 0;
          sent[kind] = received;
          const done = Object.values(sent).reduce((n, v) => n + v, 0);
          // The chunk size is kept with the job, so a worker that is stopped and
          // woken again carries on at the size this line can take.
          await update(job, { chunk, progress: total ? done / total : 0, detail: "Sending it to the renderer" });
        }
        if (!entry) continue;
        sent[kind] = blob.size;
        break;
      } catch (err) {
        if (err instanceof Failure) throw err;
        if (stopped()) throw new Failure("Stopped", null);
        failures += 1;
        chunk = Math.max(CHUNK_MIN, Math.floor(chunk / 2));
        if (failures >= ATTEMPTS) {
          throw new Failure("The connection kept dropping while sending. Try again to carry on from where it stopped", "uploading");
        }
        await update(job, { detail: "The connection dropped. Trying again" }).catch(() => {});
        await sleep(backoff(failures));
      }
    }
  }

  // Every file is on the server: ask for the clip.
  await update(job, { posting: true });
  const fresh = await getJob();
  const body = {
    video_id: job.videoId, title: job.title, channel: job.author || job.title,
    duration: job.duration, start: job.start, end: job.end, mode: job.mode,
    fill: job.fill || "blur", audio: fresh.uploads.audio.id,
  };
  if (job.mode === "video") body.video = fresh.uploads.video.id;
  else body.artwork = fresh.uploads.artwork.id;
  if (job.titleOverride) body.title_override = job.titleOverride;
  if (job.channelOverride) body.channel_override = job.channelOverride;
  let failures = 0;
  for (;;) {
    try {
      const made = await api("POST", "/jobs", { body });
      if (made.status === 202) {
        await update(job, { phase: "queued", serverJob: made.data.id, progress: 0, posting: false,
                            detail: "Waiting for its turn" });
        return;
      }
      if (made.status === 409 && made.data.job) {
        // A clip of this token's is already being made. If it is this clip, made by
        // an earlier attempt whose answer never arrived, carry on with it.
        const theirs = await api("GET", `/jobs/${made.data.job}`);
        if (theirs.status === 200 && sameClip(theirs.data, job)) {
          await update(job, { phase: "queued", serverJob: made.data.job, progress: 0, posting: false });
          return;
        }
        throw new Failure("Another clip of yours is still being made. Wait for it, then try again", "uploading");
      }
      if (made.status >= 500) throw new Error(`status ${made.status}`); // busy, or restarting
      if (made.status === 404 || made.status === 409) {
        await update(job, { uploads: {} });
        throw new Failure("The upload expired on the renderer. Try again to send it afresh", "uploading");
      }
      throw new Failure(made.data.error || `The renderer said ${made.status}`, null);
    } catch (err) {
      if (err instanceof Failure) throw err;
      failures += 1;
      if (failures >= ATTEMPTS) throw new Failure("Could not reach the renderer. Try again", "uploading");
      await sleep(backoff(failures));
    }
  }
}

const STAGE_WORDS = {
  probe: "Cutting your window", download: "Cutting your window",
  compose: "Laying out the card", render: "Making the clip",
};

async function poll(job) {
  let quietSince = null;
  let wait = 1000;
  for (;;) {
    if (stopped()) throw new Failure("Stopped", null);
    let answer = null;
    try {
      answer = await api("GET", `/jobs/${job.serverJob}`);
      // A 5xx is the renderer restarting or Cloudflare between us, not an answer.
      if (answer.status >= 500) throw new Error(`status ${answer.status}`);
    } catch (err) {
      if (stopped()) throw new Failure("Stopped", null);
      quietSince = quietSince || Date.now();
      if (Date.now() - quietSince > POLL_SILENCE) {
        throw new Failure("Lost touch with the renderer. Try again to pick the clip up", "rendering");
      }
      await update(job, { detail: "Lost touch with the renderer. Still trying" });
      await sleep(5000);
      continue;
    }
    quietSince = null;
    if (answer.status === 404) {
      throw new Failure("The renderer no longer has this clip. Try again to send it afresh", "uploading");
    }
    if (answer.status !== 200) throw new Failure(answer.data.error || `The renderer said ${answer.status}`, "rendering");
    const state = answer.data;
    if (state.state === "done") {
      await update(job, {
        phase: "downloading", progress: 0, detail: "Bringing the clip back",
        clip: { size: state.size, caption: state.caption, title: state.title,
                name: `${(state.title || "status").replace(/[^A-Za-z0-9 _-]+/g, "").trim().slice(0, 60) || "status"}.mp4` },
      });
      return;
    }
    if (state.state === "failed") {
      // A failure while cutting the window means the capture itself was wrong, a
      // hole or a short end: sending the same bytes again would fail the same way,
      // so Try again reads the video afresh. Anything later, sends them again.
      const recapture = state.stage === "probe" || state.stage === "download";
      if (recapture) {
        for (const kind of ["audio", "video"]) await idbDelete(`${job.key}:${kind}`);
      }
      await update(job, { uploads: {}, serverJob: null, posting: false,
                          files: recapture ? {} : job.files });
      throw new Failure(state.error || "The renderer could not make this clip", recapture ? "capturing" : "uploading");
    }
    if (state.state === "cancelled") throw new Failure("The clip was stopped", null);
    const detail = state.state === "queued"
      ? (state.position > 1 ? `Waiting for its turn: ${state.position - 1} ahead` : "Next in line")
      : (STAGE_WORDS[state.stage] || "Making the clip");
    await update(job, { phase: state.state === "queued" ? "queued" : "rendering", detail });
    await sleep(wait);
    wait = Math.min(3000, wait + 500);
  }
}

// Where a partial answer starts, from `Content-Range: bytes START-END/SIZE`.
function rangeStart(response) {
  const match = /^bytes (\d+)-/.exec(response.headers.get("Content-Range") || "");
  return match ? Number(match[1]) : NaN;
}

// Brings the clip back in pieces, keeping what arrived, so a dropped connection
// costs only the piece it dropped.
async function download(job) {
  const partKey = `${job.key}:clip-part`;
  let have = (await idbGet(partKey)) || new Blob([]);
  let failures = 0;
  let fresh = [];
  let freshBytes = 0;
  while (have.size < job.clip.size) {
    if (stopped()) throw new Failure("Stopped", null);
    // No limit on the whole download, which a slow line can take minutes over; a
    // stall of 30 seconds with nothing arriving is what counts as a dropped line.
    const stall = new AbortController();
    let stallTimer = setTimeout(() => stall.abort(), STALL_TIMEOUT);
    const kick = () => { clearTimeout(stallTimer); stallTimer = setTimeout(() => stall.abort(), STALL_TIMEOUT); };
    try {
      const response = await api("GET", `/jobs/${job.serverJob}/clip`, {
        raw: true, headers: have.size ? { Range: `bytes=${have.size}-` } : {},
        signal: AbortSignal.any([aborter.signal, stall.signal]),
      });
      if (response.status === 404) {
        throw new Failure("The renderer no longer has this clip. Try again to send it afresh", "uploading");
      }
      if (response.status !== 200 && response.status !== 206) throw new Error(`status ${response.status}`);
      if (response.status === 200 && have.size) have = new Blob([]); // the whole file again
      if (response.status === 206 && rangeStart(response) !== have.size) {
        // Not the bytes that follow ours: start the file again rather than join it wrong.
        have = new Blob([]);
        fresh = [];
        freshBytes = 0;
        throw new Error("the renderer answered a different range");
      }
      const reader = response.body.getReader();
      fresh = [];
      freshBytes = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        kick();
        failures = 0; // moving forward is not failing, however often the line drops
        fresh.push(value);
        freshBytes += value.length;
        if (freshBytes >= KEEP_EVERY) {
          have = new Blob([have, ...fresh]);
          fresh = [];
          freshBytes = 0;
          await keepFile(job, "clip-part", have);
          await update(job, { progress: have.size / job.clip.size, detail: "Bringing the clip back" });
        }
      }
      have = new Blob([have, ...fresh]);
      await keepFile(job, "clip-part", have);
    } catch (err) {
      if (freshBytes) {
        // Keep what arrived before the line dropped, once: the next attempt must not
        // find these bytes still waiting and add them a second time.
        have = new Blob([have, ...fresh]);
        fresh = [];
        freshBytes = 0;
        await keepFile(job, "clip-part", have).catch(() => {});
      }
      if (err instanceof Failure) throw err;
      if (stopped()) throw new Failure("Stopped", null);
      failures += 1;
      if (failures >= ATTEMPTS) throw new Failure("The connection kept dropping while bringing the clip back. Try again", "downloading");
      await update(job, { detail: "The connection dropped. Trying again" }).catch(() => {});
      await sleep(backoff(failures));
    } finally {
      clearTimeout(stallTimer);
    }
  }
  if (have.size !== job.clip.size) throw new Failure("The clip arrived the wrong size. Try again", "downloading");
  await keepFile(job, "clip", have.slice(0, have.size, "video/mp4"));
  await idbDelete(partKey);
  for (const kind of ["audio", "video", "artwork"]) await idbDelete(`${job.key}:${kind}`);
  await update(job, { phase: "ready", progress: 1, detail: "" });
  // The renderer keeps a clip for an hour in case it is needed again. It is not.
  api("DELETE", `/jobs/${job.serverJob}`).catch(() => {});
}

// -- WhatsApp ----------------------------------------------------------------------

async function whatsappTab() {
  const [found] = await chrome.tabs.query({ url: "https://web.whatsapp.com/*" });
  if (found) return found;
  return chrome.tabs.create({ url: "https://web.whatsapp.com/", active: true });
}

async function signedIn(tabId) {
  try {
    const [result] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => !!document.querySelector('button[aria-label="Status"]') || !!document.querySelector("#pane-side"),
    });
    return !!result.result;
  } catch {
    return false;
  }
}

async function loadIntoWhatsApp() {
  const job = await getJob();
  if (!job || job.phase !== "ready") return { ok: false, error: "There is no finished clip to load" };
  const clip = await idbGet(`${job.key}:clip`);
  if (!clip) return { ok: false, error: "The finished clip is gone. Make it again" };
  return whatsappLoad(clip, job.clip.name, job.clip.caption, aborter.signal);
}

// Opens the Status composer with this clip and caption in place. Never sends.
// One load at a time, whichever path asks: two would fight over the same composer.
let loadingWhatsApp = false;

async function whatsappLoad(clip, name, caption, signal) {
  if (loadingWhatsApp) return { ok: false, error: "WhatsApp is already opening a clip. Wait for it to finish" };
  loadingWhatsApp = true;
  try {
    return await whatsappLoadOnce(clip, name, caption, signal);
  } finally {
    loadingWhatsApp = false;
  }
}

// `signal` is the asking path's Stop: once it fires, nothing more is done in
// WhatsApp, and a composer half way through loading is let go.
async function whatsappLoadOnce(clip, name, caption, signal) {
  const halted = () => !!(signal && signal.aborted);
  const STOPPED = { ok: false, error: "Stopped" };
  if (halted()) return STOPPED;
  const tab = await whatsappTab();
  // Pressed by a person who wants to see WhatsApp, so it comes to the front; and a
  // background tab is throttled hard enough to make the composer time out.
  await chrome.tabs.update(tab.id, { active: true });
  await chrome.windows.update(tab.windowId, { focused: true }).catch(() => {});
  const until = Date.now() + 120000;
  while (!(await signedIn(tab.id))) {
    if (halted()) return STOPPED;
    if (Date.now() > until) return { ok: false, error: "WhatsApp Web is not signed in. Scan the QR code in that tab, then try again" };
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  if (halted()) return STOPPED;
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["wa-bridge.js"] });
  await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["whatsapp.js"], world: "MAIN" });
  const bytes = new Uint8Array(await clip.arrayBuffer());
  return new Promise((resolve) => {
    const port = chrome.tabs.connect(tab.id, { name: "wastatus-wa" });
    const timer = setTimeout(() => { resolve({ ok: false, error: "WhatsApp took too long to open its editor" }); try { port.disconnect(); } catch { /* gone */ } }, 150000);
    port.onMessage.addListener((message) => {
      if (!message.result) return;
      clearTimeout(timer);
      resolve(message.result);
      try { port.disconnect(); } catch { /* gone */ }
    });
    port.onDisconnect.addListener(() => {
      clearTimeout(timer);
      resolve({ ok: false, error: "The WhatsApp tab was closed or reloaded. Try again" });
    });
    if (signal) {
      signal.addEventListener("abort", () => {
        clearTimeout(timer);
        resolve(STOPPED);
        try { port.disconnect(); } catch { /* gone */ }
      }, { once: true });
    }
    port.postMessage({ cmd: "start", name, size: bytes.length, caption });
    const SLICE = 512 * 1024;
    for (let at = 0; at < bytes.length; at += SLICE) {
      let text = "";
      const slice = bytes.subarray(at, at + SLICE);
      for (let i = 0; i < slice.length; i += 0x8000) text += String.fromCharCode.apply(null, slice.subarray(i, i + 0x8000));
      port.postMessage({ cmd: "chunk", b64: btoa(text) });
    }
    port.postMessage({ cmd: "end" });
  });
}

async function save() {
  const job = await getJob();
  if (!job || job.phase !== "ready") return { ok: false, error: "There is no finished clip to save" };
  const clip = await idbGet(`${job.key}:clip`);
  if (!clip) return { ok: false, error: "The finished clip is gone. Make it again" };
  // A service worker cannot make an object URL, so the file goes as a data URL.
  const bytes = new Uint8Array(await clip.arrayBuffer());
  let text = "";
  for (let at = 0; at < bytes.length; at += 0x8000) text += String.fromCharCode.apply(null, bytes.subarray(at, at + 0x8000));
  await chrome.downloads.download({ url: `data:video/mp4;base64,${btoa(text)}`,
                                    filename: job.clip.name, conflictAction: "uniquify" });
  return { ok: true };
}

// -- what the popup asks --------------------------------------------------------------

async function tabInfo(tabId) {
  return new Promise((resolve) => {
    let port;
    try { port = chrome.tabs.connect(tabId, { name: "wastatus-tab" }); } catch { resolve(null); return; }
    const timer = setTimeout(() => { resolve(null); try { port.disconnect(); } catch { /* gone */ } }, 3000);
    port.onMessage.addListener((message) => {
      if (!message.info) return;
      clearTimeout(timer);
      resolve(message.info);
      try { port.disconnect(); } catch { /* gone */ }
    });
    port.onDisconnect.addListener(() => { clearTimeout(timer); resolve(null); });
    port.postMessage({ cmd: "info" });
  });
}

async function start(params) {
  const p = params || {};
  if (!(Number.isFinite(p.start) && Number.isFinite(p.end) && p.end > p.start && p.end - p.start <= 90) ||
      !["card", "video"].includes(p.mode) || !/^[A-Za-z0-9_-]{11}$/.test(p.videoId || "") ||
      !Number.isInteger(p.tabId)) {
    return { ok: false, error: "That clip is not valid" };
  }
  const current = await getJob();
  if (current && PHASES_ACTIVE.includes(current.phase)) return { ok: false, error: "A clip is already being made" };
  if (pageBusy) return { ok: false, error: "A clip is already being read in this browser" };
  aborter = new AbortController();
  if (current) await discard(current);
  const job = {
    key: `j${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`,
    created: Date.now(), phase: "capturing", progress: 0, detail: "Starting",
    tabId: params.tabId, videoId: params.videoId, title: params.title, author: params.author,
    duration: params.duration, start: params.start, end: params.end, mode: params.mode,
    fill: params.fill, titleOverride: params.titleOverride || "", channelOverride: params.channelOverride || "",
    uploads: {}, files: {}, serverJob: null, clip: null, error: "", retryFrom: null,
  };
  await saveJob(job);
  run();
  return { ok: true };
}

async function discard(job) {
  if (job.serverJob && job.phase !== "ready") api("DELETE", `/jobs/${job.serverJob}`).catch(() => {});
  for (const entry of Object.values(job.uploads || {})) {
    if (entry && entry.id) api("DELETE", `/uploads/${entry.id}`).catch(() => {});
  }
  await forgetBlobs(job.key).catch(() => {});
}

async function stop() {
  const job = await getJob();
  if (!job) return { ok: true };
  // Stop what is in flight, then tell the renderer with a fresh controller: the
  // old one is aborted, and a DELETE carrying it would never be sent.
  aborter.abort();
  if (capturePort) {
    // The bridge hears the disconnect and stops the walk in the page.
    try { capturePort.disconnect(); } catch { /* gone */ }
    capturePort = null;
  }
  await chrome.storage.local.remove("job");
  badge(null);
  // Let the step in flight see the abort and return before anything new starts,
  // so it cannot carry on with a request on behalf of a job that no longer exists.
  if (running) await Promise.race([running, new Promise((r) => setTimeout(r, 5000))]);
  aborter = new AbortController();
  await discard(job);
  return { ok: true };
}

async function retry() {
  const job = await getJob();
  if (!job || job.phase !== "failed" || !job.retryFrom) return { ok: false, error: "Nothing to try again" };
  aborter = new AbortController();
  job.phase = job.retryFrom;
  // Captured files that are already stored need not be read from YouTube again.
  if (job.phase === "capturing" && Object.keys(job.files || {}).length) {
    const kinds = job.mode === "video" ? ["audio", "video"] : ["audio", "artwork"];
    const stored = await Promise.all(kinds.map((k) => idbGet(`${job.key}:${k}`)));
    if (stored.every(Boolean)) job.phase = "uploading";
  }
  job.error = "";
  job.retryFrom = null;
  await saveJob(job);
  run();
  return { ok: true };
}

async function checkSettings({ server, token }) {
  try {
    const response = await fetch(`${server.replace(/\/+$/, "")}/api/v1/me`, {
      headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(15000),
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 200) return { ok: true, name: data.name };
    if (response.status === 401) return { ok: false, error: "The renderer does not know that token" };
    return { ok: false, error: data.error || `The renderer said ${response.status}` };
  } catch {
    return { ok: false, error: "Could not reach that address" };
  }
}

// -- the SnipShare page --------------------------------------------------------------
//
// The page at CONFIG.site talks to this worker over a port (externally_connectable
// lists that site and nothing else). It asks four things: hello, capture a window
// of a video, load a finished clip into WhatsApp, and read a video's title. It
// never holds a session: what it hands over is a grant, good for fifteen minutes
// and one purpose, and the server is always the page's own origin.
//
// Nothing here is kept across a worker restart. The open port keeps the worker
// awake while the page waits, and if it is stopped anyway the page hears the port
// close and offers to try again, which costs a capture, not a clip.

const PAGE = {
  CAPTURES_PER_HOUR: 20,  // per browser, Table HP-2: a person's pace, never a crawler's
  LOADS_PER_HOUR: 10,
  OPEN_TIMEOUT: 45000,    // for YouTube to open the video in a new tab
};
let pageBusy = null;      // one capture at a time, whatever asks

class PageFailure extends Error {
  constructor(message, code, phase) { super(message); this.code = code; this.phase = phase || code; }
}

function siteOrigin() {
  try { return new URL(CONFIG.site).origin; } catch { return ""; }
}

// The page's origin, if it is the site this copy was built for (`config.js`), port
// and all. The manifest already keeps every other site out; this keeps out the other
// pages a local build's broader match would let in.
function allowedOrigin(sender) {
  const origin = String(sender && (sender.origin || (sender.url && new URL(sender.url).origin)) || "");
  return origin && origin === siteOrigin() ? origin : "";
}

const pause = (ms, signal) => new Promise((resolve) => {
  const timer = setTimeout(resolve, ms);
  signal.addEventListener("abort", () => { clearTimeout(timer); resolve(); }, { once: true });
});

// At most `limit` of `kind` in an hour, in this browser. One at a time, so two
// requests together cannot both read the count before either writes it.
let pacing = Promise.resolve();
function paced(kind, limit) {
  const turn = pacing.then(() => pacedNow(kind, limit));
  pacing = turn.catch(() => {});
  return turn;
}

async function pacedNow(kind, limit) {
  const now = Date.now();
  const stored = (await chrome.storage.local.get("pace")).pace || {};
  const recent = (stored[kind] || []).filter((at) => now - at < 3600000);
  if (recent.length >= limit) {
    const wait = Math.ceil((3600000 - (now - recent[0])) / 60000);
    throw new PageFailure(`That is ${limit} in an hour from this browser, which is the most `
      + `SnipShare does. Try again in ${wait} minute${wait === 1 ? "" : "s"}.`, "paced");
  }
  recent.push(now);
  await chrome.storage.local.set({ pace: { ...stored, [kind]: recent } });
}

async function whatsappState() {
  const [tab] = await chrome.tabs.query({ url: "https://web.whatsapp.com/*" });
  if (!tab) return "none";
  return (await signedIn(tab.id)) ? "signed-in" : "open";
}

async function videoTab(videoId) {
  const tabs = await chrome.tabs.query({ url: "https://www.youtube.com/watch*" });
  return tabs.find((t) => {
    try { return new URL(t.url).searchParams.get("v") === videoId; } catch { return false; }
  }) || null;
}

async function readyInfo(tabId, until, signal) {
  for (;;) {
    if (signal.aborted) throw new PageFailure("Stopped.", "stopped");
    const info = await tabInfo(tabId);
    if (info && info.ready) return info;
    if (Date.now() > until) {
      throw new PageFailure("YouTube did not open the video in time. Try again.", "open");
    }
    await pause(400, signal);
  }
}

// One request to the renderer, as the page's grant.
async function asPage(op, method, path, { body, headers, signal } = {}) {
  const init = {
    method,
    signal: signal || AbortSignal.any([op.abort.signal, AbortSignal.timeout(REQUEST_TIMEOUT)]),
    headers: { Authorization: `Bearer ${op.grant}`, ...(headers || {}) },
  };
  if (body !== undefined) {
    if (body instanceof Blob) init.body = body;
    else { init.body = JSON.stringify(body); init.headers["Content-Type"] = "application/json"; }
  }
  const response = await fetch(`${op.server}/api/v1${path}`, init);
  let data = null;
  try { data = await response.json(); } catch { data = null; }
  return { status: response.status, data: data || {} };
}

// Sends one file in chunks, carrying on from whatever the server says it holds.
async function sendFile(op, kind, blob, onProgress) {
  let entry = null;
  let chunk = CHUNK_START;
  let failures = 0;
  for (;;) {
    if (op.abort.signal.aborted) throw new PageFailure("Stopped.", "stopped");
    try {
      if (!entry) {
        const made = await asPage(op, "POST", "/uploads", { body: { kind, size: blob.size } });
        if (made.status === 401) {
          throw new PageFailure("This clip's permission to upload ran out. Make the clip again.", "auth", "upload");
        }
        if (made.status >= 500) throw new Error(`status ${made.status}`);
        if (made.status !== 201) {
          throw new PageFailure(made.data.error || `The renderer said ${made.status}.`, "upload-refused", "upload");
        }
        entry = made.data;
      }
      const asked = await asPage(op, "GET", `/uploads/${entry.id}`);
      if (asked.status === 404) { entry = null; continue; }
      if (asked.status !== 200) throw new Error(`status ${asked.status}`);
      let received = asked.data.received;
      while (received < blob.size) {
        if (op.abort.signal.aborted) throw new PageFailure("Stopped.", "stopped");
        const size = Math.min(chunk, entry.chunk || chunk, blob.size - received);
        const started = Date.now();
        const put = await asPage(op, "PUT", `/uploads/${entry.id}`, {
          body: blob.slice(received, received + size),
          headers: { "Content-Range": `bytes ${received}-${received + size - 1}/${blob.size}` },
        });
        if (put.status === 409 && put.data.claimed) {
          throw new PageFailure("This upload is already being made into a clip.", "upload-refused", "upload");
        }
        if (put.status === 200 || put.status === 409) {
          received = put.data.received;
          if (!Number.isInteger(received)) throw new Error("the renderer did not say how much it holds");
        } else if (put.status === 404) { entry = null; break; }
        else if (put.status === 401) {
          throw new PageFailure("This clip's permission to upload ran out. Make the clip again.", "auth", "upload");
        } else if (put.status >= 400 && put.status < 500) {
          throw new PageFailure(put.data.error || `The renderer refused the upload (${put.status}).`, "upload-refused", "upload");
        } else throw new Error(`status ${put.status}`);
        const took = Date.now() - started;
        if (took < CHUNK_FAST) chunk = Math.min(chunk * 2, entry.chunk || chunk * 2);
        else if (took > CHUNK_SLOW) chunk = Math.max(CHUNK_MIN, Math.floor(chunk / 2));
        failures = 0;
        onProgress(received);
      }
      if (!entry) continue;
      return entry.id;
    } catch (err) {
      if (err instanceof PageFailure) throw err;
      if (op.abort.signal.aborted) throw new PageFailure("Stopped.", "stopped");
      failures += 1;
      chunk = Math.max(CHUNK_MIN, Math.floor(chunk / 2));
      if (failures >= ATTEMPTS) {
        throw new PageFailure("The connection kept dropping while sending. Try again.", "network", "upload");
      }
      await pause(backoff(failures), op.abort.signal);
    }
  }
}

async function pageCapture(op, message, sender) {
  const { videoId, start, end, mode } = message;
  if (!/^[A-Za-z0-9_-]{11}$/.test(videoId || "") || !Number.isFinite(start) || !Number.isFinite(end)
      || !(end > start) || end - start > 90.5 || !["card", "video"].includes(mode)) {
    throw new PageFailure("That clip is not valid.", "invalid");
  }
  if (pageBusy) throw new PageFailure("A clip is already being read in this browser.", "busy");
  pageBusy = op;
  const popupJob = await getJob();
  if (popupJob && popupJob.phase === "capturing") {
    pageBusy = null;
    throw new PageFailure("A clip is already being read in this browser.", "busy");
  }
  let opened = null;
  try {
    await paced("captures", PAGE.CAPTURES_PER_HOUR);
    const say = (text, progress) => op.say({ message: text, progress });

    let artwork = null;
    if (mode === "card") {
      say("Getting the video's picture", 0);
      artwork = await thumbnail(videoId);
      if (!artwork) throw new PageFailure("Could not get the video's picture from YouTube. Try again.", "thumbnail");
    }

    // A tab already showing this video is used as it is, and left as it was. If
    // there is none, one opens beside the page, in front only until its player is
    // ready, muted, and closes when the window is read. A tab that has never been
    // in front is not given its media by Chrome, which is why it shows at all.
    let tab = await videoTab(videoId);
    let info = tab ? await tabInfo(tab.id) : null;
    const pageTab = sender.tab;
    if (!tab || !info || !info.ready) {
      say("Opening the video for a moment", 0);
      if (!tab) {
        tab = await chrome.tabs.create({
          url: `https://www.youtube.com/watch?v=${videoId}&t=${Math.floor(start)}s`,
          active: true, ...(pageTab ? { windowId: pageTab.windowId, index: pageTab.index + 1,
                                         openerTabId: pageTab.id } : {}),
        });
        opened = tab.id;
        chrome.tabs.update(tab.id, { muted: true }).catch(() => {});
      } else {
        await chrome.tabs.update(tab.id, { active: true });
      }
      info = await readyInfo(tab.id, Date.now() + PAGE.OPEN_TIMEOUT, op.abort.signal);
      if (pageTab) await chrome.tabs.update(pageTab.id, { active: true }).catch(() => {});
    }
    if (info.videoId !== videoId) throw new PageFailure("That tab is showing a different video. Try again.", "wrong-video");
    if (info.live) throw new PageFailure("Live streams cannot be clipped.", "live");
    if (info.duration && start >= info.duration) {
      throw new PageFailure(`The video is ${Math.floor(info.duration)} seconds long, so that start is past its end.`, "window");
    }

    say(info.ad ? "Waiting for the ad to finish" : "Reading the video", 0);
    const files = await readWindow(tab.id, {
      videoId, start, end, needVideo: mode === "video", quality: "hd720",
    }, (progress) => say(progress.detail || "Reading the video", progress.progress),
    (port) => { op.tabPort = port; });
    if (opened) { chrome.tabs.remove(opened).catch(() => {}); opened = null; }
    if (artwork) files.artwork = artwork;

    const kinds = mode === "video" ? ["audio", "video"] : ["audio", "artwork"];
    const total = kinds.reduce((n, kind) => n + files[kind].size, 0);
    const sent = {};
    const ids = {};
    for (const kind of kinds) {
      ids[kind] = await sendFile(op, kind, files[kind], (received) => {
        sent[kind] = received;
        const done = Object.values(sent).reduce((n, v) => n + v, 0);
        say("Sending it to SnipShare", total ? done / total : 0);
      });
      sent[kind] = files[kind].size;
    }
    return {
      video_id: videoId, title: info.title || "", channel: info.author || "",
      duration: info.duration || end, ...ids,
    };
  } catch (err) {
    if (err instanceof PageFailure) throw err;
    if (op.abort.signal.aborted) throw new PageFailure("Stopped.", "stopped");
    throw new PageFailure(String(err && err.message || err), "read", "capture");
  } finally {
    if (opened) chrome.tabs.remove(opened).catch(() => {});
    if (pageBusy === op) pageBusy = null;
  }
}

// Brings the finished clip back in pieces, so a dropped line costs only a piece.
async function fetchClip(op, url, onProgress) {
  let have = new Blob([]);
  let size = null;
  let failures = 0;
  while (size === null || have.size < size) {
    if (op.abort.signal.aborted) throw new PageFailure("Stopped.", "stopped");
    const stall = new AbortController();
    let timer = setTimeout(() => stall.abort(), STALL_TIMEOUT);
    const kick = () => { clearTimeout(timer); timer = setTimeout(() => stall.abort(), STALL_TIMEOUT); };
    const parts = [];
    try {
      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${op.grant}`, ...(have.size ? { Range: `bytes=${have.size}-` } : {}) },
        signal: AbortSignal.any([op.abort.signal, stall.signal]),
      });
      if (response.status === 401 || response.status === 404) {
        throw new PageFailure("SnipShare no longer has this clip, or the permission ran out. Try again.", "gone", "download");
      }
      if (response.status !== 200 && response.status !== 206) throw new Error(`status ${response.status}`);
      if (response.status === 200) {
        have = new Blob([]);
        size = Number(response.headers.get("Content-Length"));
      } else {
        if (rangeStart(response) !== have.size) {
          have = new Blob([]);
          throw new Error("the renderer answered a different range");
        }
        size = Number((response.headers.get("Content-Range") || "").split("/")[1]);
      }
      if (!Number.isFinite(size) || size <= 0) throw new Error("no size");
      const reader = response.body.getReader();
      let got = have.size;
      let told = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        kick();
        failures = 0;
        parts.push(value);
        got += value.length;
        // A word every second or so: the page counts silence as a hung extension.
        if (onProgress && Date.now() - told > 1000) {
          told = Date.now();
          onProgress(got / size);
        }
      }
      have = new Blob([have, ...parts]);
    } catch (err) {
      if (parts.length) have = new Blob([have, ...parts]);
      if (err instanceof PageFailure) throw err;
      if (op.abort.signal.aborted) throw new PageFailure("Stopped.", "stopped");
      failures += 1;
      if (failures >= ATTEMPTS) {
        throw new PageFailure("The connection kept dropping while fetching the clip. Try again.", "network", "download");
      }
      await pause(backoff(failures), op.abort.signal);
    } finally {
      clearTimeout(timer);
    }
  }
  if (have.size !== size) throw new PageFailure("The clip arrived the wrong size. Try again.", "size", "download");
  return have.slice(0, size, "video/mp4");
}

async function pageLoad(op, message) {
  let url;
  try { url = new URL(message.url); } catch { url = null; }
  if (!url || url.origin !== op.server || url.pathname !== "/api/v1/clip") {
    throw new PageFailure("That clip address is not SnipShare's.", "invalid");
  }
  await paced("loads", PAGE.LOADS_PER_HOUR);
  op.say({ message: "Fetching the clip" });
  const clip = await fetchClip(op, url.href,
    (share) => op.say({ message: "Fetching the clip", progress: Math.min(1, share) }));
  op.say({ message: "Opening WhatsApp" });
  const name = String(message.name || "status.mp4").replace(/[^A-Za-z0-9 ._-]+/g, "").slice(0, 120) || "status.mp4";
  if (op.abort.signal.aborted) throw new PageFailure("Stopped.", "stopped");
  const result = await whatsappLoad(clip, name, String(message.caption || "").slice(0, 1024), op.abort.signal);
  if (op.abort.signal.aborted) throw new PageFailure("Stopped.", "stopped");
  if (!result || !result.ok) {
    throw new PageFailure((result && result.error) || "WhatsApp did not open its editor. Try again.",
      ((result && result.error) || "").slice(0, 60) || "whatsapp", "whatsapp");
  }
  return { loaded: true };
}

async function pageWords(message) {
  const id = String(message.videoId || "") || (() => {
    try {
      const url = new URL(message.url);
      if (url.hostname === "youtu.be") return url.pathname.slice(1, 12);
      return url.searchParams.get("v") || (url.pathname.match(/^\/(shorts|live|embed)\/([^/?]+)/) || [])[2] || "";
    } catch { return ""; }
  })();
  if (!/^[A-Za-z0-9_-]{11}$/.test(id)) throw new PageFailure("That is not a YouTube video link.", "invalid");
  const response = await fetch(`https://www.youtube.com/oembed?format=json&url=${
    encodeURIComponent(`https://www.youtube.com/watch?v=${id}`)}`, { signal: AbortSignal.timeout(15000) });
  if (response.status === 401 || response.status === 403 || response.status === 404) {
    throw new PageFailure("YouTube does not share this video's details. It may be private or removed.", "private");
  }
  if (!response.ok) throw new PageFailure("YouTube did not answer. Try again.", "words");
  const data = await response.json();
  return { title: data.title || "", channel: data.author_name || "" };
}

chrome.runtime.onConnectExternal.addListener((port) => {
  const origin = allowedOrigin(port.sender);
  if (!origin) { port.disconnect(); return; }
  const op = {
    abort: new AbortController(), server: origin, grant: "", tabPort: null,
    say: (progress) => { try { port.postMessage({ progress }); } catch { /* gone */ } },
  };
  let started = false;
  const stopAll = () => {
    op.abort.abort();
    if (op.tabPort) { try { op.tabPort.disconnect(); } catch { /* gone */ } }
  };
  // The page closed, or reloaded: whatever it asked for stops.
  port.onDisconnect.addListener(stopAll);
  port.onMessage.addListener(async (message) => {
    if (!message || typeof message !== "object") return;
    if (message.cmd === "stop") return stopAll();
    if (started) return;
    started = true;
    try {
      let done;
      if (message.cmd === "hello") {
        // Answered quickly whatever WhatsApp's tab is doing: the page waits on this.
        const whatsapp = await Promise.race([whatsappState().catch(() => "unknown"),
          new Promise((resolve) => setTimeout(() => resolve("unknown"), 1500))]);
        done = { version: chrome.runtime.getManifest().version, whatsapp };
      } else if (message.cmd === "capture" || message.cmd === "load") {
        // The grant is used only against the page's own origin, whatever the
        // message says about servers.
        if (message.server && new URL(message.server).origin !== origin) {
          throw new PageFailure("That server is not this page's.", "invalid");
        }
        op.grant = String(message.grant || "");
        if (!op.grant) throw new PageFailure("Sign in again.", "auth");
        done = message.cmd === "capture" ? await pageCapture(op, message, port.sender)
          : await pageLoad(op, message);
      } else if (message.cmd === "words") {
        done = await pageWords(message);
      } else {
        throw new PageFailure("The extension does not know that request. Update it.", "unknown");
      }
      port.postMessage({ done });
    } catch (err) {
      const failure = err instanceof PageFailure ? err
        : new PageFailure(String(err && err.message || err), "failed");
      try {
        port.postMessage({ error: { message: failure.message, code: failure.code, phase: failure.phase } });
      } catch { /* the page has gone */ }
    }
  });
});

// The toolbar button opens SnipShare, or brings an open one forward. The popup that
// used to answer it is kept in the extension, switched off (docs/extension.md).
chrome.action.onClicked.addListener(async () => {
  const site = CONFIG.site.replace(/\/+$/, "");
  const [open] = await chrome.tabs.query({ url: `${site}/app*` }).catch(() => []);
  if (open) {
    await chrome.tabs.update(open.id, { active: true });
    await chrome.windows.update(open.windowId, { focused: true }).catch(() => {});
    return;
  }
  await chrome.tabs.create({ url: `${site}/app` });
});

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  // Only the extension's own pages: the popup, whether in the toolbar or open as a
  // tab. Content scripts run on web pages and have no business here.
  if (sender.id !== chrome.runtime.id || !String(sender.url || "").startsWith(chrome.runtime.getURL(""))) return false;
  const work = {
    "tab-info": () => tabInfo(message.tabId),
    start: () => start(message.params),
    stop, retry,
    "load-whatsapp": loadIntoWhatsApp,
    save,
    "check-settings": () => checkSettings(message),
    resume: async () => { run(); return { ok: true }; },
  }[message.type];
  if (!work) return false;
  work().then(respond, (err) => respond({ ok: false, error: String(err && err.message || err) }));
  return true;
});

// Wake up and carry on: on install, on browser start, and once a minute while a
// clip is in flight, because Chrome may have stopped this worker in between.
chrome.runtime.onInstalled.addListener(() => run());
chrome.runtime.onStartup.addListener(() => run());
chrome.alarms.onAlarm.addListener(() => run());
getJob().then(badge);
sweepBlobs().catch(() => {});
run();
