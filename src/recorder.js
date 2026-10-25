// YouTube's page world, from document_start, before the player exists.
//
// Records what the player appends to Media Source Extensions: bytes it already
// fetched on the viewer's own connection, so recording costs no extra request. It
// records always, from the first byte, because whatever the player buffered before
// recording began is gone for good and it will not fetch it again (the spike lost
// the first 20 seconds of a video that way). Memory follows the player: when it
// evicts a range from its buffer, so do we. See docs/extension.md, DECISIONS.md D-083.
//
// Never allowed to break playback. Every hook calls the original first or last and
// swallows its own errors: a bug here costs a capture, never the video.
//
// Talks to bridge.js (the isolated world) over a MessageChannel the bridge hands
// over once, at document_start, before any of YouTube's own scripts exist to see
// it. Everything after that goes over that private port, so nothing else on the
// page can ask for a capture or answer as if it were this script.
(() => {
  "use strict";
  if (window.__wastatusRecorder) return;
  window.__wastatusRecorder = true;

  const M = window.WAStatusMedia;
  try { delete window.WAStatusMedia; } catch { /* non-configurable in some worlds */ }
  if (!M) return;

  // Bytes held across every buffer in this tab before trimming. Recording runs in
  // every YouTube tab, so this is per tab: a few open tabs must not tie up gigabytes.
  const MEMORY_CEILING = 200e6;
  const KEEP_BEHIND = 120;      // seconds behind the playhead kept when trimming
  const KEEP_AHEAD = 300;

  const sources = [];            // one per MediaSource still worth keeping
  const byMediaSource = new WeakMap();
  const byBuffer = new WeakMap();
  const byUrl = new Map();       // blob URL -> source, to find the player's own
  let nextId = 1;
  const cancelled = new Set();   // capture ids the extension has stopped

  const player = () => document.getElementById("movie_player");
  const video = () => document.querySelector("#movie_player video");
  const isAd = () => !!player()?.classList.contains("ad-showing");
  const playerVideoId = () => {
    try { return player()?.getVideoData?.()?.video_id || null; } catch { return null; }
  };
  const urlVideoId = () => {
    try { return new URLSearchParams(location.search).get("v"); } catch { return null; }
  };

  function sourceOf(mediaSource) {
    let source = byMediaSource.get(mediaSource);
    if (!source) {
      source = { id: nextId++, ms: mediaSource, buffers: [], videoId: null, ad: isAd(),
                 created: Date.now(), urls: [], dropped: false };
      byMediaSource.set(mediaSource, source);
      sources.push(source);
    }
    return source;
  }

  function total() {
    let bytes = 0;
    for (const source of sources) for (const b of source.buffers) bytes += b.bytes;
    return bytes;
  }

  // Forgotten for good: its bytes go, its URL goes, and anything the player still
  // appends to it is not recorded, so nothing is held that nothing counts.
  function drop(source) {
    source.dropped = true;
    source.buffers = [];
    for (const url of source.urls) byUrl.delete(url);
    const at = sources.indexOf(source);
    if (at >= 0) sources.splice(at, 1);
  }

  function current() {
    const v = video();
    const source = v && byUrl.get(v.src);
    return source && !source.dropped ? source : null;
  }

  // A new video's first MediaSource makes every other video's recordings useless.
  // Ads go too: they are never part of a clip.
  function forgetOthers(keep) {
    for (const s of [...sources]) {
      if (s !== keep && (s.ad || (s.videoId && s.videoId !== keep.videoId))) drop(s);
    }
  }

  function trimToCeiling() {
    if (total() <= MEMORY_CEILING) return;
    const at = video()?.currentTime || 0;
    for (const source of sources) {
      for (const b of source.buffers) b.keepOnly(at - KEEP_BEHIND, at + KEEP_AHEAD);
    }
    // Still over: the oldest recordings go first, never the one playing.
    const playing = current();
    for (const s of [...sources]) {
      if (total() <= MEMORY_CEILING) break;
      if (s !== playing) drop(s);
    }
  }

  // -- the hooks -------------------------------------------------------------

  const createObjectURL = URL.createObjectURL;
  URL.createObjectURL = function (object) {
    const url = createObjectURL.apply(this, arguments);
    try {
      if (typeof MediaSource !== "undefined" && object instanceof MediaSource) {
        const source = sourceOf(object);
        if (!source.dropped) { byUrl.set(url, source); source.urls.push(url); }
      }
    } catch { /* never break the page */ }
    return url;
  };

  const proto = window.MediaSource && MediaSource.prototype;
  if (proto) {
    const addSourceBuffer = proto.addSourceBuffer;
    proto.addSourceBuffer = function (mime) {
      const sb = addSourceBuffer.apply(this, arguments);
      try {
        const source = sourceOf(this);
        const buffer = new M.Buffer(String(mime));
        source.buffers.push(buffer);
        byBuffer.set(sb, { buffer, source });
      } catch { /* never break the page */ }
      return sb;
    };
  }

  const sbProto = window.SourceBuffer && SourceBuffer.prototype;
  if (sbProto) {
    const appendBuffer = sbProto.appendBuffer;
    sbProto.appendBuffer = function (data) {
      try {
        const entry = byBuffer.get(this);
        if (entry && !entry.source.dropped) {
          const bytes = data instanceof ArrayBuffer
            ? new Uint8Array(data.slice(0))
            : new Uint8Array(data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength));
          const source = entry.source;
          if (!source.videoId) {
            source.ad = source.ad || isAd();
            source.videoId = source.ad ? null : (playerVideoId() || urlVideoId());
            if (source.videoId) forgetOthers(source);
          }
          entry.buffer.append(bytes, this.timestampOffset);
          trimToCeiling();
        }
      } catch { /* never break the page */ }
      return appendBuffer.apply(this, arguments);
    };

    const abort = sbProto.abort;
    sbProto.abort = function () {
      try { byBuffer.get(this)?.buffer.abort(); } catch { /* never break the page */ }
      return abort.apply(this, arguments);
    };

    const remove = sbProto.remove;
    sbProto.remove = function (start, end) {
      const result = remove.apply(this, arguments);
      try { byBuffer.get(this)?.buffer.remove(start, end); } catch { /* never break the page */ }
      return result;
    };

    if (sbProto.changeType) {
      const changeType = sbProto.changeType;
      sbProto.changeType = function (mime) {
        try { byBuffer.get(this)?.buffer.changeType(String(mime)); } catch { /* never break the page */ }
        return changeType.apply(this, arguments);
      };
    }
  }

  // -- what the extension asks ------------------------------------------------

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function info() {
    const p = player();
    const v = video();
    let data = {};
    try { data = p?.getVideoData?.() || {}; } catch { /* not ready */ }
    const onWatch = location.pathname === "/watch";
    return {
      ready: !!(p && v && data.video_id && onWatch),
      videoId: data.video_id || urlVideoId(),
      title: data.title || document.title.replace(/ - YouTube$/, ""),
      author: data.author || "",
      duration: (() => { try { return p?.getDuration?.() || 0; } catch { return 0; } })(),
      currentTime: (() => { try { return p?.getCurrentTime?.() || 0; } catch { return 0; } })(),
      ad: isAd(),
      live: (() => { try { return !!p?.getVideoData?.()?.isLive; } catch { return false; } })(),
      qualities: (() => { try { return p?.getAvailableQualityLevels?.() || []; } catch { return []; } })(),
      recording: sources.length > 0,
    };
  }

  function quality(p) {
    try { return p.getPreferredQuality?.() || "auto"; } catch { return "auto"; }
  }

  // The recordings that belong to this video: the MediaSources made for it that did
  // not begin as an ad, and the one the player is playing now, whatever it says.
  function eligible(videoId, kind) {
    const playing = current();
    const duration = (() => { try { return player()?.getDuration?.() || 0; } catch { return 0; } })();
    const picked = sources.filter((s) => {
      if (s.ad) return false;
      // The one playing now may not have had its id read yet; never another video's.
      if (s === playing && !s.videoId) return true;
      if (s.videoId !== videoId) return false;
      // A MediaSource whose duration is not this video's is not this video's.
      const d = Number(s.ms?.duration);
      return !(d && isFinite(d) && duration && Math.abs(d - duration) > 2);
    });
    return picked.flatMap((s) => s.buffers.filter((b) => b.kind === kind));
  }

  // Fill [start, end] without playing: pause, seek, wait for our own record (not
  // the element's buffered ranges) to cover it, and when the player stops reading
  // ahead, seek to the edge of what it has. Then put the viewer back where they were.
  const ORDER = ["hd2160", "hd1440", "hd1080", "hd720", "large", "medium", "small", "tiny"];

  async function walk(job, report) {
    const p = player();
    const v = video();
    if (!p || !v) throw new Error("The YouTube player is not on this page");
    if (v.srcObject && !v.src) {
      // MediaSource in a worker, handed over as a handle: the hooks above never see
      // it. YouTube does not do this today; if it starts, this says so plainly.
      throw new Error("This page plays its video in a way the extension cannot read yet");
    }
    const need = job.needVideo ? ["audio", "video"] : ["audio"];
    const duration = p.getDuration();
    // The last fragment's own length is an estimate, so the very end of a video is
    // asked for half a second short of where the player says it is.
    const target = Math.min(job.end + job.margin, duration - 0.5);
    const was = { time: p.getCurrentTime(), paused: v.paused, quality: quality(p) };
    let pinned = null;
    const pin = (level) => { p.setPlaybackQualityRange(level, level); pinned = level; };
    const stillThisVideo = () => {
      if (p.getVideoData?.().video_id !== job.videoId) {
        throw new Error("The video on this tab changed. Open the video again and retry");
      }
    };
    // Time spent on ads is not time the video took: an ad plays for as long as it
    // plays, and only the reading itself is held to the limit. Ads have their own.
    // Silence, not length, is what fails a read: a slow line reading steadily is
    // let finish, and only a read that has stopped growing for `stallMs` gives up.
    // `timeoutMs` is a ceiling far above any real read.
    let adTime = 0;
    let grewAt = Date.now();
    const check = () => {
      if (cancelled.has(job.id)) throw new Error("Stopped");
      if (adTime > job.adLimitMs) {
        throw new Error("The ads did not finish in five minutes. Try again");
      }
      if (Date.now() - grewAt > job.stallMs || Date.now() - startedAt - adTime > job.timeoutMs) {
        throw new Error("YouTube stopped sending the video. Reload the YouTube page, then try again");
      }
    };
    const waitForAd = async () => {
      while (isAd()) {
        report({ phase: "capturing", detail: "Waiting for the ad to finish", progress: 0 });
        const before = Date.now();
        await sleep(500);
        adTime += Date.now() - before;   // measured: a background tab's timers run late
        grewAt = Date.now();
        check();
      }
    };

    const startedAt = Date.now();
    await waitForAd();
    stillThisVideo();
    try {
      if (job.needVideo && job.quality && job.quality !== "auto") {
        const levels = p.getAvailableQualityLevels?.() || [];
        const cap = ORDER.indexOf(job.quality);
        const best = levels.filter((q) => ORDER.indexOf(q) >= cap).sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b))[0];
        if (best) pin(best);
      }
      p.pauseVideo();
      p.seekTo(job.start, true);
      let lastReach = -1;
      let stillSince = Date.now();
      let kicks = 0;
      let repins = 0;
      for (;;) {
        await sleep(250);
        check();
        if (isAd()) { await waitForAd(); stillSince = Date.now(); continue; }
        stillThisVideo();
        const reaches = need.map((kind) => M.reach(eligible(job.videoId, kind), job.start));
        const reached = Math.min(...reaches);
        const fraction = Math.max(0, Math.min(1, (reached - job.start) / Math.max(0.1, target - job.start)));
        report({ phase: "capturing", detail: "Reading the video from YouTube", progress: fraction });
        if (reached >= target) break;
        if (reached !== lastReach) { lastReach = reached; stillSince = grewAt = Date.now(); kicks = 0; }
        if (Date.now() - stillSince > 1500) {
          kicks += 1;
          if (kicks >= 4 && repins < 2) {
            // Nothing new after several nudges. The usual cause is the player
            // switching quality part way, which leaves the window in two encodings
            // that cannot be joined, and a buffer it will not fetch again. Pinning a
            // quality makes it start afresh in one encoding, from the start.
            const levels = (p.getAvailableQualityLevels?.() || []).filter((q) => ORDER.includes(q));
            const now = p.getPlaybackQuality?.();
            const next = levels.find((q) => q !== pinned && q === now) ||
                         levels.find((q) => q !== pinned && ORDER.indexOf(q) > ORDER.indexOf(now)) ||
                         levels.find((q) => q !== pinned);
            if (next) pin(next);
            repins += 1;
            kicks = 0;
            p.seekTo(job.start, true);
          } else {
            // The player has stopped reading ahead, or has not started here. Put the
            // playhead just inside the edge of what we hold, so it reads on from there.
            p.seekTo(Math.max(job.start, Math.min(reached - 1, duration - 1)), true);
          }
          p.pauseVideo();
          stillSince = Date.now();
        }
      }
    } finally {
      try {
        // Back to what the viewer had: their own quality choice, place and state.
        if (pinned) {
          if (was.quality && was.quality !== "auto") p.setPlaybackQualityRange(was.quality, was.quality);
          else p.setPlaybackQualityRange("auto", "auto");
        }
        p.seekTo(was.time, true);
        if (!was.paused) p.playVideo(); else p.pauseVideo();
      } catch { /* the page may have navigated away */ }
    }
    const files = {};
    for (const kind of need) {
      const picked = M.pick(eligible(job.videoId, kind), job.start, Math.min(job.end, duration), 1);
      if (!picked) throw new Error(`Could not put the ${kind} together. Try again`);
      if (picked.shifted) throw new Error("This video's timing cannot be read for a clip. Try another video");
      files[kind] = picked;
    }
    return files;
  }

  // -- messages ---------------------------------------------------------------

  // The bridge sends one MessagePort, once, at document_start. The first one wins;
  // nothing that arrives later can replace it.
  // The port's own methods are kept from now, before YouTube's scripts run: one
  // loaded later could replace MessagePort.prototype.postMessage and read or answer
  // on the port. Calling these copies keeps the channel private after that too.
  let port = null;
  const portPost = MessagePort.prototype.postMessage;
  const setOnMessage = Object.getOwnPropertyDescriptor(MessagePort.prototype, "onmessage").set;
  const removeListener = window.removeEventListener;
  function onPort(event) {
    if (event.source !== window || event.data?.wastatus !== "bridge-port" || !event.ports[0]) return;
    removeListener.call(window, "message", onPort);
    port = event.ports[0];
    setOnMessage.call(port, (message) => handle(message.data));
  }
  window.addEventListener("message", onPort);

  const reply = (id, body, transfer) => { try { portPost.call(port, { id, ...body }, transfer || []); } catch { /* gone */ } };

  async function handle(message) {
    const { id, cmd } = message || {};
    if (cmd === "info") return reply(id, { info: info() });
    if (cmd === "cancel") { cancelled.add(message.target); return undefined; }
    if (cmd !== "capture") return undefined;
    const job = {
      id, videoId: String(message.videoId || ""),
      start: Number(message.start), end: Number(message.end),
      needVideo: !!message.needVideo, quality: String(message.quality || "auto"),
      // A stall is judged by the clock, not by ticks, and ticks can be a minute
      // apart in a slowed background tab, so the stall allowance is wider than one.
      margin: 4, stallMs: 120000, timeoutMs: 600000, adLimitMs: 300000,
    };
    if (!(job.end > job.start) || !job.videoId) return reply(id, { error: "That window is not valid" });
    try {
      const files = await walk(job, (progress) => reply(id, { progress }));
      // One file at a time, in slices the bridge can carry. The slices are copies,
      // so the record stays intact for a retry.
      for (const [kind, picked] of Object.entries(files)) {
        reply(id, { file: { kind, size: picked.size, from: picked.from, to: picked.to,
                            width: picked.width, height: picked.height } });
        const whole = M.concat(picked.parts, picked.size);
        const SLICE = 512 * 1024;
        for (let at = 0; at < whole.length; at += SLICE) {
          if (cancelled.has(id)) throw new Error("Stopped");
          const slice = whole.slice(at, at + SLICE);
          reply(id, { chunk: { kind, at, bytes: slice.buffer } }, [slice.buffer]);
        }
      }
      reply(id, { done: true });
    } catch (err) {
      reply(id, { error: String(err && err.message || err) });
    } finally {
      cancelled.delete(id);
    }
    return undefined;
  }
})();
