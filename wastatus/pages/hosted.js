/* SnipShare: what the tool page needs on the hosted site, and only there.

   Loaded before app.js, which asks `window.SnipShare` at the few places the two
   differ: reading the video (the extension, in this browser, instead of yt-dlp on
   the server), loading into WhatsApp (the extension again, instead of a debug
   port), fetching the words, and what the status chip says. Everything else on the
   page is the local tool's own code, talking to the same routes.

   The extension is reached with `chrome.runtime.connect(id)`, which Chrome offers
   to this page only because the extension lists this site as allowed to talk to
   it. A port rather than a single message, because a capture takes seconds and
   reports its progress, and an open port keeps the extension's worker awake. */

window.SnipShare = (() => {
  const data = document.body.dataset;
  const EXT_ID = data.extensionId || "";
  const MIN_VERSION = data.minVersion || "0";
  const TOKEN = data.token;
  const $ = (id) => document.getElementById(id);

  const ua = navigator.userAgentData;
  const mobile = ua ? ua.mobile : /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  const brands = ua ? ua.brands.map((b) => b.brand) : [];
  const chromium = brands.some((b) => /Chrom/.test(b)) || /Chrome\//.test(navigator.userAgent);

  // What the extension said last: {version, whatsapp} or null when it is not here.
  let extension = null;
  let checked = false;
  let quota = null;
  // Scheduled Statuses: the pilot switch and the figures the extension enforces,
  // as the server last said (`/api/state`). Off until it says on.
  let scheduling = { enabled: false, pending: 30, budget_bytes: 400000000 };
  let me = { name: data.name || "", email: data.email || "", admin: data.admin === "1" };
  let current = null;        // the port of the capture or load in flight
  let lastFailure = "";      // the last failure reported, for the feedback form

  /* The site's source, offered here as on every other page: it runs AGPL code
     (THIRD_PARTY_NOTICES.md). Under the Recent strip, beside where the clips are. */
  if (/^https:\/\//.test(data.source || "") && $("foot-out")) {
    const line = document.createElement("p");
    line.className = "hint recent__where";
    const link = document.createElement("a");
    link.href = data.source;
    link.rel = "noopener";
    link.textContent = "Source code";
    line.append(link);
    $("foot-out").after(line);
  }

  /* ── talking to this site ─────────────────────────────── */

  async function call(path, body) {
    let response;
    try {
      response = await fetch(path, {
        method: body ? "POST" : "GET",
        headers: { "X-Wastatus-Token": TOKEN,
                   ...(body ? { "Content-Type": "application/json" } : {}) },
        body: body ? JSON.stringify(body) : undefined,
        signal: AbortSignal.timeout ? AbortSignal.timeout(30000) : undefined,
      });
    } catch (error) {
      throw new Error(error && error.name === "TimeoutError"
        ? "The connection is too slow right now. Try again."
        : "Could not reach SnipShare. Check the connection and try again.");
    }
    let payload = {};
    try { payload = await response.json(); } catch { /* empty */ }
    if (response.status === 401) {
      location.assign("/signin?next=/app");
      throw new Error("Signed out. Sign in again.");
    }
    if (!response.ok) throw new Error(payload.error || `request failed (${response.status})`);
    return payload;
  }

  /* Sanitized before it leaves: a step, a short code, versions. Never the video. */
  function report(source, phase, code) {
    lastFailure = `${source}/${phase}/${code}`;
    // For the account page's feedback form, which offers to include it.
    try {
      localStorage.setItem("snipshare.lastFailure",
        JSON.stringify({ code: lastFailure, email: me.email, at: Date.now() }));
    } catch { /* fine */ }
    call("/api/report", {
      source, phase, code: String(code || "").slice(0, 80),
      versions: `ext ${extension ? extension.version : "none"}; ${
        brands.join(",") || navigator.userAgent.slice(0, 60)}`,
    }).catch(() => {});
  }

  /* ── talking to the extension ─────────────────────────── */

  function connect() {
    if (!EXT_ID || !(window.chrome && chrome.runtime && chrome.runtime.connect)) return null;
    try {
      return chrome.runtime.connect(EXT_ID, { name: "snipshare" });
    } catch {
      return null;
    }
  }

  /* One conversation with the extension: a command, any number of progress
     messages, and one answer. */
  /* `timeout` is for the whole exchange; a capture or a load has none, because a
     slow line takes as long as it takes, and is held instead to `IDLE`: silence for
     longer than any step of the extension's own goes quiet for (waiting for
     WhatsApp to sign in, then for its composer, is up to 270 seconds) means it has
     hung without saying so. */
  const IDLE = 300000;
  let currentFinish = null;

  function converse(message, onProgress, timeout = 0, track = false, watched = false) {
    return new Promise((resolve, reject) => {
      const port = connect();
      if (!port) return reject(Object.assign(new Error(
        "The SnipShare extension is not in this browser."), { code: "no-extension" }));
      let over = false;
      let timer = null;
      let quiet = null;
      const finish = (error, value) => {
        if (over) return;
        over = true;
        clearTimeout(timer);
        clearTimeout(quiet);
        if (track && current === port) { current = null; currentFinish = null; }
        try { port.disconnect(); } catch { /* gone */ }
        error ? reject(error) : resolve(value);
      };
      const hush = () => {
        if (!track && !watched) return;
        clearTimeout(quiet);
        quiet = setTimeout(() => finish(Object.assign(new Error(
          "The extension stopped reporting. Reload this page and try again."),
          { code: "silent" })), IDLE);
      };
      if (timeout) {
        timer = setTimeout(() => finish(Object.assign(
          new Error("The extension did not answer."), { code: "timeout" })), timeout);
      }
      hush();
      port.onMessage.addListener((answer) => {
        hush();
        if (answer.progress && onProgress) onProgress(answer.progress);
        if (answer.done) finish(null, answer.done);
        if (answer.error) {
          finish(Object.assign(new Error(answer.error.message || "The extension failed."),
            { code: answer.error.code || "failed", phase: answer.error.phase || "" }));
        }
      });
      port.onDisconnect.addListener(() => {
        void (chrome.runtime && chrome.runtime.lastError);
        finish(Object.assign(new Error(
          "The extension stopped answering. If it was just updated or reloaded, reload "
          + "this page and try again."), { code: "disconnected" }));
      });
      // Only a capture or a load is what Stop stops; a status check running beside
      // one must not take its place.
      if (track) { current = port; currentFinish = finish; }
      port.postMessage(message);
    });
  }

  function older(version, than) {
    const a = String(version || "0").split(".").map(Number);
    const b = String(than).split(".").map(Number);
    for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
      if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) < (b[i] || 0);
    }
    return false;
  }

  // A worker that Chrome has stopped takes a moment to start again, so a first
  // silence is asked twice more before the page says the extension is missing.
  async function hello(tries = 3) {
    for (let attempt = 1; attempt <= tries; attempt += 1) {
      try {
        extension = await converse({ cmd: "hello" }, null, 4000);
        break;
      } catch (error) {
        extension = null;
        if (error.code === "no-extension") break;   // nothing to wait for
        if (attempt < tries) await new Promise((r) => setTimeout(r, 700 * attempt));
      }
    }
    checked = true;
    paint();
    return extension;
  }

  const ready = () => Boolean(extension) && !older(extension.version, MIN_VERSION) && !mobile;

  /* ── the page's questions ─────────────────────────────── */

  async function capture(body, onProgress) {
    if (!ready()) {
      await hello();
      if (!ready()) throw new Error(why() || "The SnipShare extension is needed to make a clip.");
    }
    onProgress({ step: "read", message: "Checking the window" });
    const granted = await call("/api/grant", {
      purpose: "upload",
      window: { url: body.url, start: body.start, end: body.end, duration: body.duration },
    });
    try {
      return await converse({
        cmd: "capture", videoId: granted.video_id, start: granted.start, end: granted.end,
        mode: body.video ? "video" : "card", server: granted.server, grant: granted.grant,
      }, (progress) => onProgress({ step: "read", ...progress }), 0, true);
    } catch (error) {
      if (error.code !== "stopped") report("capture", error.phase || "capture", error.code);
      throw error;
    }
  }

  /* Asks the extension to stop, and lets go of it a few seconds later whatever it
     says: a Stop that waits on a worker which has hung would never end. */
  function stop() {
    if (!current) return false;
    const asked = current;
    try { current.postMessage({ cmd: "stop" }); } catch { /* gone */ }
    setTimeout(() => {
      if (current === asked && currentFinish) {
        currentFinish(Object.assign(new Error("Stopped."), { code: "stopped" }));
      }
    }, 5000);
    return true;
  }

  async function load(clip, caption) {
    if (!ready()) {
      await hello();
      if (!ready()) throw new Error(why() || "The SnipShare extension is needed for this.");
    }
    const granted = await call("/api/grant", { purpose: "clip", stem: clip.stem });
    try {
      return await converse({
        cmd: "load", url: `${granted.server}/api/v1/clip?stem=${encodeURIComponent(clip.stem)}`,
        grant: granted.grant, caption, name: `${clip.stem}.mp4`,
      }, null, 0, true);
    } catch (error) {
      report("load", error.phase || "load", error.code);
      throw error;
    } finally {
      hello();
    }
  }

  /* ── scheduling (docs/scheduling.md) ──────────────────── */

  /* Whether this page may offer Schedule: the extension says it can ("schedule" in
     its features, from 2.1.0), the server has the pilot on for this person, and
     this is a computer. A phone gets a line saying so instead (U10). */
  function canSchedule() {
    return ready() && scheduling.enabled
      && Array.isArray(extension.features) && extension.features.includes("schedule");
  }

  /* Why not, in one line, or "" when it is fine or when nothing should be said: a
     person the pilot is off for is told nothing, since the feature is not theirs. */
  function whyNotSchedule() {
    if (mobile) return scheduling.enabled
      ? "Scheduling works in Chrome on a computer with the extension" : "";
    if (!scheduling.enabled || !ready()) return "";
    if (!Array.isArray(extension.features) || !extension.features.includes("schedule")) {
      return "Scheduling needs the newest SnipShare extension. Update it, then reload this page.";
    }
    return "";
  }

  /* Keeps the clip on this computer until its time. `when` is {due: epoch ms} or
     {afterLast: true}. The clip is fetched by the extension with a `clip` grant, as
     `load` does, and the answer comes after it is kept, so `onProgress` carries the
     download ({message, progress}). The extension enforces the smaller of the limits
     sent and its own. Action is always "prepare" in this release: nothing here, and
     nothing the extension does for a schedule, presses Send (D-084). */
  async function schedule(clip, caption, when, onProgress) {
    if (!ready()) {
      await hello();
      if (!ready()) throw new Error(why() || "The SnipShare extension is needed for this.");
    }
    if (!canSchedule()) {
      throw new Error(whyNotSchedule() || "Scheduling is not switched on for you yet.");
    }
    const granted = await call("/api/grant", { purpose: "clip", stem: clip.stem });
    const message = {
      cmd: "schedule",
      server: granted.server,
      grant: granted.grant,
      url: `${granted.server}/api/v1/clip?stem=${encodeURIComponent(clip.stem)}`,
      stem: clip.stem,
      name: `${clip.stem}.mp4`,
      caption,
      mode: clip.video ? "video" : "card",
      action: "prepare",
      limits: { pending: scheduling.pending, budgetBytes: scheduling.budget_bytes },
    };
    if (when && when.afterLast) message.afterLast = true;
    else message.due = when.due;
    try {
      return await converse(message, onProgress, 0, false, true);
    } catch (error) {
      // What the person can fix is theirs to read, not a fault to report.
      if (!["past", "far", "limit", "budget", "quota", "gone", "network"].includes(error.code)) {
        report("schedule", error.phase || "schedule", error.code);
      }
      throw error;
    }
  }

  /* The next three, for Up next. Null when the extension cannot say; the page shows
     nothing then rather than an error, because it is a glance, not a task. */
  async function peek() {
    if (!canSchedule()) return null;
    try {
      return await converse({ cmd: "queue-peek" }, null, 6000);
    } catch {
      return null;
    }
  }

  /* The queue is an extension page, which a web page cannot open itself: the
     extension is asked, and opens it in front because the person pressed a link. */
  async function openQueue() {
    if (!ready()) {
      await hello();
      if (!ready()) throw new Error(why() || "The SnipShare extension is needed for this.");
    }
    return converse({ cmd: "open-queue" }, null, 8000);
  }

  async function words(url) {
    if (!ready()) await hello();
    if (!ready()) {
      throw new Error("Fetching the words needs the SnipShare extension. Type them in, "
        + "or leave the boxes empty and they are read when the clip is made.");
    }
    let found;
    try {
      found = await converse({ cmd: "words", url }, null, 20000);
    } catch (error) {
      report("words", "words", error.code);
      throw error;
    }
    return call("/api/words", { url, title: found.title || "", channel: found.channel || "" });
  }

  /* ── what the page shows ──────────────────────────────── */

  function why() {
    if (mobile) return "Making a clip needs Google Chrome on a computer.";
    if (!checked) return "";
    if (!extension && !chromium) return "Open SnipShare in Google Chrome on a computer to make a clip.";
    if (!extension) return "Making a clip needs the SnipShare extension in this browser.";
    if (older(extension.version, MIN_VERSION)) {
      return `Your SnipShare extension is version ${extension.version}. This page needs `
        + `${MIN_VERSION} or newer.`;
    }
    return "";
  }

  function rows(fresh) {
    if (fresh.quota) quota = fresh.quota;
    if (fresh.me) me = fresh.me;
    if (fresh.scheduling) scheduling = fresh.scheduling;
    // The quota line and the buttons follow the state that just arrived.
    queueMicrotask(paint);
    const left = quota ? Math.max(0, quota.clips_limit - quota.clips) : null;
    const wa = extension && extension.whatsapp;
    return [
      {
        ok: ready(), what: "extension",
        detail: ready() ? `version ${extension.version}` : (why() || "checking"),
      },
      {
        ok: wa === "signed-in", tone: wa === "signed-in" ? "ok" : "idle", what: "WhatsApp Web",
        detail: !extension ? "loads through the extension"
          : wa === "signed-in" ? "signed in, in this browser"
            : wa === "open" ? "open, not signed in yet: scan the QR code there"
              : "Load into WhatsApp opens it for you",
      },
      {
        ok: left === null || left > 0, tone: left === null || left > 0 ? "idle" : "",
        what: "today",
        detail: left === null ? "" : `${left} of ${quota.clips_limit} clips left`,
      },
    ];
  }

  function banner() {
    let box = $("host-banner");
    if (!box) {
      box = document.createElement("div");
      box.id = "host-banner";
      box.className = "hostbanner";
      box.setAttribute("role", "status");
      document.querySelector("main").before(box);
    }
    const text = why();
    if (!text) { box.hidden = true; return; }
    const link = mobile ? "" : (!extension && !chromium) ? ""
      : '<a class="button button--primary button--small" href="/install" target="_blank" rel="noopener">Get the extension</a>';
    box.innerHTML = `<span>${escape(text)}${mobile
      ? " Your recent clips are here to watch and save." : ""}</span>${link}`;
    box.hidden = false;
  }

  function paint() {
    banner();
    const reason = why();
    const note = $("host-make-why");
    if (note) {
      note.textContent = reason;
      note.hidden = !reason;
    }
    if (quota && $("host-quota")) {
      const left = Math.max(0, quota.clips_limit - quota.clips);
      $("host-quota").textContent = left
        ? `${left} of ${quota.clips_limit} clips left today`
        : `You have made today's ${quota.clips_limit} clips. More after midnight UTC.`;
    }
    document.body.dataset.where = ready() ? "here" : "away";
    if (window.SnipShareRepaint) window.SnipShareRepaint();
  }

  const escape = (value) => String(value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  /* ── the way to the account page ───────────────────────── */

  // A link, not a panel: the account page holds the profile, history, keys and
  // feedback, and this page keeps its whole height for the work.
  function accountLink() {
    const controls = document.querySelector(".topbar__controls");
    const link = document.createElement("a");
    link.className = "statuschip accountchip";
    link.id = "account-chip";
    link.href = "/account";
    link.title = "Your account: profile, history, GIF keys, feedback";
    link.innerHTML = `<span class="accountchip__initial" aria-hidden="true"></span><span>Account</span>`;
    const face = link.querySelector(".accountchip__initial");
    if (window.SnipShareUI) SnipShareUI.avatar(face, data.picture || "", me.name || me.email);
    else face.textContent = (me.name || me.email || "?").trim().charAt(0).toUpperCase();
    controls.prepend(link);
  }

  function makeNotes() {
    const row = $("makerow");
    const why = document.createElement("p");
    why.className = "hostnote";
    why.id = "host-make-why";
    why.hidden = true;
    row.after(why);
    const left = document.createElement("p");
    left.className = "hint hostquota";
    left.id = "host-quota";
    why.after(left);
  }

  /* Words the local page uses that are not true here. */
  function retell() {
    const set = (id, text) => { const e = $(id); if (e) e.textContent = text; };
    set("foot-reach", "Clips are made on the SnipShare server. You press Send in WhatsApp.");
    const deleteWhat = document.querySelector("#doer-delete .doer__what");
    if (deleteWhat) deleteWhat.textContent = "Removes this clip from SnipShare. Two presses.";
    const send = $("doer-send");
    if (send) send.hidden = true;
    const follow = document.querySelector(".check--follow");
    if (follow) follow.hidden = true;
    const hint = document.querySelector("#sec-words .accordion__body > .hint");
    if (hint) {
      hint.textContent = "Left empty, these are read from the video when the clip is made. "
        + "The arrow in this card's header fetches them now, through the extension, so "
        + "they can be corrected first. Changing them means making the clip again; the "
        + "caption under the preview is text, and edits there are instant.";
    }
  }

  const STEP_LABELS = { read: "read", probe: "check", download: "cut", compose: "lay out",
                        render: "render" };

  // This script sits at the end of the page, so everything it adds to is there.
  accountLink();
  makeNotes();
  retell();
  paint();
  hello();
  // Installed or reloaded the extension in another tab, then came back.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") hello();
  });
  setInterval(() => { if (!document.hidden) hello(); }, 30000);

  return {
    capture, stop, load, words, rows, ready, why, hello,
    schedule, peek, openQueue, canSchedule, whyNotSchedule,
    get scheduling() { return scheduling; },
    label: (stage) => STEP_LABELS[stage] || stage,
    get mobile() { return mobile; },
    get whatsapp() { return extension && extension.whatsapp; },
  };
})();
