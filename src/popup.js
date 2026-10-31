// The toolbar popup. Shows one thing at a time: set up, the form, progress, the
// finished clip, or what went wrong. It holds no state of its own: the job lives in
// chrome.storage.local and is driven by the service worker, so closing the popup
// halfway changes nothing, and opening it again shows where things are.
"use strict";

// From config.js, which the built extension carries with the real address.
const DEFAULT_SERVER = CONFIG.site;
const MAX_LENGTH = 90;
const WHATSAPP_MAX_BYTES = 10485760;
const DEFAULT_LENGTH = 30;
const ORDER = ["capturing", "uploading", "rendering", "downloading"];

const $ = (id) => document.getElementById(id);
let tab = null;
let info = null;
let shownKey = null;
let previewUrl = null;

function show(name) {
  for (const view of document.querySelectorAll(".view")) view.hidden = view.id !== `view-${name}`;
}

const send = (type, extra = {}) => chrome.runtime.sendMessage({ type, ...extra });

// -- times ----------------------------------------------------------------------

// The same forms the command line accepts: 93, 1:33, 01:33, 1:02:03, 90.5.
function parseTime(text) {
  const value = String(text || "").trim().replace(/\s+/g, "");
  if (!/^\d+(\.\d+)?$|^\d+:\d{1,2}(\.\d+)?$|^\d+:\d{1,2}:\d{1,2}(\.\d+)?$/.test(value)) return NaN;
  const parts = value.split(":").map(Number);
  if (parts.slice(1).some((p) => p >= 60)) return NaN;
  return parts.reduce((total, part) => total * 60 + part, 0);
}

function formatTime(seconds) {
  const whole = Math.floor(seconds);
  const tenth = Math.round((seconds - whole) * 10);
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  const s = whole % 60;
  const tail = tenth ? `.${tenth}` : "";
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}${tail}`
           : `${m}:${String(s).padStart(2, "0")}${tail}`;
}

// -- settings -------------------------------------------------------------------

async function settings() {
  return { server: DEFAULT_SERVER, token: "", quality: "hd720",
           ...((await chrome.storage.local.get("settings")).settings || {}) };
}

// Checks the address and the token against the renderer before keeping them, so a
// typo is found here and not half way through a clip.
async function saveSettings(server, token, quality, resultEl) {
  server = (server || DEFAULT_SERVER).trim().replace(/\/+$/, "");
  let origin;
  try {
    const url = new URL(server);
    if (url.protocol !== "https:" && !["127.0.0.1", "localhost"].includes(url.hostname)) throw new Error();
    origin = url.origin;
  } catch {
    return say(resultEl, "That is not an https address", true);
  }
  if (!token.trim()) return say(resultEl, "Paste your access token", true);
  if (origin !== new URL(DEFAULT_SERVER).origin) {
    // Must be asked inside the click that wanted it. Match patterns carry no port.
    const pattern = `${new URL(server).protocol}//${new URL(server).hostname}/*`;
    const granted = await chrome.permissions.request({ origins: [pattern] }).catch(() => false);
    if (!granted) return say(resultEl, "The extension needs permission to reach that address", true);
  }
  say(resultEl, "Checking…", false);
  const answer = await send("check-settings", { server, token: token.trim() });
  if (!answer || !answer.ok) return say(resultEl, (answer && answer.error) || "Could not check", true);
  const stored = await settings();
  await chrome.storage.local.set({ settings: { ...stored, server, token: token.trim(), quality: quality || stored.quality } });
  say(resultEl, `Connected as ${answer.name}`, false);
  return true;
}

function say(el, text, isError) {
  el.hidden = !text;
  el.textContent = text;
  el.className = isError ? "error" : "note";
  return false;
}

// -- scheduling settings ----------------------------------------------------------

// Defaults match the contract: quiet hours on, an evening gap of three hours, and the
// two ways of taking focus off until the person turns them on (docs/scheduling.md T1).
const SCHEDULE_DEFAULTS = {
  quietOn: true, quietStart: "23:00", quietEnd: "07:00", gapMinutes: 180,
  bringForward: false, idleForward: false, perPostNotices: false,
};

function fillSchedule(s) {
  const v = { ...SCHEDULE_DEFAULTS, ...s };
  $("sched-quiet-on").checked = !!v.quietOn;
  $("sched-quiet-start").value = v.quietStart;
  $("sched-quiet-end").value = v.quietEnd;
  // A gap set some other way (an older build, a hand edit) still shows as itself.
  const gap = String(v.gapMinutes);
  if (![...$("sched-gap").options].some((o) => o.value === gap)) {
    $("sched-gap").add(new Option(`${gap} minutes`, gap));
  }
  $("sched-gap").value = gap;
  $("sched-forward").checked = !!v.bringForward;
  $("sched-idle").checked = !!v.idleForward;
  $("sched-notices").checked = !!v.perPostNotices;
  quietTimesState();
  $("sched-result").hidden = true;
}

function quietTimesState() {
  const off = !$("sched-quiet-on").checked;
  $("sched-quiet-start").disabled = off;
  $("sched-quiet-end").disabled = off;
}

async function saveSchedule() {
  quietTimesState();
  const start = $("sched-quiet-start").value;
  const end = $("sched-quiet-end").value;
  // An emptied time field would store nothing the runner can read.
  if (!start || !end) return say($("sched-result"), "Choose a time in both fields", true);
  const changes = {
    quietOn: $("sched-quiet-on").checked, quietStart: start, quietEnd: end,
    gapMinutes: Number($("sched-gap").value) || SCHEDULE_DEFAULTS.gapMinutes,
    bringForward: $("sched-forward").checked, idleForward: $("sched-idle").checked,
    perPostNotices: $("sched-notices").checked,
  };
  await chrome.storage.local.set({ settings: { ...(await settings()), ...changes } });
  say($("sched-result"), "Saved", false);
}

// The person pressed this, so foreground is right: focus the open queue, or open one.
// The SnipShare page's link does the same through open-queue on the external port.
async function openQueue() {
  const url = chrome.runtime.getURL("queue.html");
  const [open] = await chrome.tabs.query({ url });
  if (open) {
    await chrome.tabs.update(open.id, { active: true });
    await chrome.windows.update(open.windowId, { focused: true });
  } else {
    await chrome.tabs.create({ url });
  }
  window.close();
}

// -- the form -------------------------------------------------------------------

async function showForm() {
  shownKey = null;
  show("loading");
  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  // Opened as the options page, in a tab of its own, the active tab is this one:
  // the video is the YouTube tab most recently in front.
  if (tab && String(tab.url || "").startsWith(chrome.runtime.getURL(""))) {
    const watching = await chrome.tabs.query({ url: "https://www.youtube.com/watch*" });
    tab = watching.sort((a, b) => (b.lastAccessed || 0) - (a.lastAccessed || 0))[0] || null;
  }
  const url = (tab && tab.url) || "";
  if (!/^https:\/\/www\.youtube\.com\/watch\?/.test(url)) return show("empty");
  info = await send("tab-info", { tabId: tab.id }).catch(() => null);
  if (!info) return show("reload");
  if (!info.ready || !info.duration) {
    $("view-empty").querySelector("h2").textContent = "Wait for the video to start";
    $("view-empty").querySelector(".lead").textContent = "Then press this button again.";
    $("open-youtube").hidden = true;
    return show("empty");
  }
  if (info.live) {
    $("view-empty").querySelector("h2").textContent = "Live streams cannot be clipped yet";
    $("view-empty").querySelector(".lead").textContent = "Open a video that is not live.";
    $("open-youtube").hidden = true;
    return show("empty");
  }
  $("form-title").textContent = info.title;
  $("form-ad").hidden = !info.ad;
  let start = Math.floor(info.currentTime);
  if (start > info.duration - 5) start = Math.max(0, Math.floor(info.duration - DEFAULT_LENGTH));
  const end = Math.min(start + DEFAULT_LENGTH, info.duration);
  $("start").value = formatTime(start);
  $("end").value = formatTime(Math.floor(end * 10) / 10);
  $("title-override").value = "";
  $("channel-override").value = "";
  show("form");
  validate();
}

function windowOf() {
  const start = parseTime($("start").value);
  const end = parseTime($("end").value);
  let error = "";
  let bad = [];
  if (isNaN(start)) { error = "Use a time like 1:23"; bad = ["start"]; }
  else if (isNaN(end)) { error = "Use a time like 1:53"; bad = ["end"]; }
  else if (end <= start) { error = "The end has to come after the start"; bad = ["end"]; }
  else if (end - start > MAX_LENGTH) {
    error = `That is ${Math.round(end - start)} seconds. A Status can be at most ${MAX_LENGTH}`;
    bad = ["end"];
  } else if (info && start >= info.duration) {
    error = `The video is only ${formatTime(info.duration)} long`; bad = ["start"];
  } else if (info && end > info.duration + 0.5) {
    error = `The video ends at ${formatTime(info.duration)}`; bad = ["end"];
  }
  return { start, end: info ? Math.min(end, info.duration) : end, error, bad };
}

function validate() {
  const w = windowOf();
  for (const id of ["start", "end"]) $(id).setAttribute("aria-invalid", String(w.bad.includes(id)));
  const note = $("window-note");
  note.textContent = w.error || `${Math.round((w.end - w.start) * 10) / 10} seconds`;
  note.className = w.error ? "error" : "hint";
  $("make").disabled = !!w.error;
  return w;
}

function modeChanged() {
  const video = document.querySelector('input[name="mode"]:checked').value === "video";
  $("mode-hint").textContent = video
    ? "The real video, with its title over it. Sends more data."
    : "The video's picture, its title, and a wave that moves with the sound.";
  $("fill-row").hidden = !video;
}

async function useNow(field) {
  const fresh = await send("tab-info", { tabId: tab.id }).catch(() => null);
  if (!fresh) return;
  $(field).value = formatTime(Math.floor(fresh.currentTime * 10) / 10);
  if (field === "start") {
    const end = parseTime($("end").value);
    if (!(end > fresh.currentTime) || end - fresh.currentTime > MAX_LENGTH) {
      $("end").value = formatTime(Math.min(Math.floor(fresh.currentTime) + DEFAULT_LENGTH, info.duration));
    }
  }
  validate();
}

async function make(event) {
  event.preventDefault();
  const w = validate();
  if (w.error) return;
  $("make").disabled = true;
  const mode = document.querySelector('input[name="mode"]:checked').value;
  const titleOverride = $("title-override").value.trim();
  const channelOverride = $("channel-override").value.trim();
  const answer = await send("start", { params: {
    tabId: tab.id, videoId: info.videoId, title: info.title, author: info.author,
    duration: info.duration, start: w.start, end: w.end, mode, fill: $("fill").value,
    titleOverride, channelOverride,
  } });
  if (!answer || !answer.ok) {
    $("window-note").textContent = (answer && answer.error) || "Could not start";
    $("window-note").className = "error";
    $("make").disabled = false;
  }
}

// -- a job in flight, finished, or failed ---------------------------------------------

async function render(job) {
  if (!job) return showForm();
  if (["capturing", "uploading", "queued", "rendering", "downloading"].includes(job.phase)) {
    const now = job.phase === "queued" ? "rendering" : job.phase;
    for (const li of $("steps").children) {
      const at = ORDER.indexOf(li.dataset.phase);
      li.dataset.state = at < ORDER.indexOf(now) ? "done" : at === ORDER.indexOf(now) ? "now" : "";
    }
    const percent = Math.round((job.progress || 0) * 100);
    $("meter-fill").style.width = `${percent}%`;
    $("meter-fill").parentElement.setAttribute("aria-valuenow", String(percent));
    $("progress-detail").textContent = job.detail || "";
    shownKey = null;
    return show("progress");
  }
  if (job.phase === "ready") {
    if (shownKey !== job.key) {
      shownKey = job.key;
      $("caption").textContent = job.clip.caption;
      // WhatsApp refuses a file over this without saying so. The engine aims well
      // under it; this is for the clip that overshot. render.PLATFORM_MAX_BYTES.
      const over = job.clip.size > WHATSAPP_MAX_BYTES;
      $("too-big").hidden = !over;
      $("too-big").textContent = over
        ? `This clip is ${(job.clip.size / 1e6).toFixed(1)} MB, and WhatsApp may refuse anything over ${(WHATSAPP_MAX_BYTES / 1e6).toFixed(1)} MB. A shorter window will fit.`
        : "";
      $("load-result").hidden = true;
      const clip = await readClip(job.key);
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = clip ? URL.createObjectURL(clip) : null;
      $("preview").src = previewUrl || "";
    }
    return show("ready");
  }
  if (job.phase === "failed") {
    shownKey = null;
    $("failed-error").textContent = job.error || "Something went wrong";
    $("retry").hidden = !job.retryFrom;
    return show("failed");
  }
  return showForm();
}

function readClip(key) {
  return new Promise((resolve) => {
    const open = indexedDB.open("wastatus", 1);
    open.onupgradeneeded = () => open.result.createObjectStore("blobs");
    open.onerror = () => resolve(null);
    open.onsuccess = () => {
      const get = open.result.transaction("blobs").objectStore("blobs").get(`${key}:clip`);
      get.onsuccess = () => resolve(get.result || null);
      get.onerror = () => resolve(null);
    };
  });
}

async function busy(button, text, work) {
  const label = button.textContent;
  button.disabled = true;
  button.textContent = text;
  try { return await work(); } finally { button.disabled = false; button.textContent = label; }
}

// -- wiring ------------------------------------------------------------------------

function wire() {
  $("start").addEventListener("input", validate);
  $("end").addEventListener("input", validate);
  for (const id of ["start", "end"]) {
    $(id).addEventListener("blur", () => {
      const value = parseTime($(id).value);
      if (!isNaN(value)) $(id).value = formatTime(value);
      validate();
    });
  }
  $("start-now").addEventListener("click", () => useNow("start"));
  $("end-now").addEventListener("click", () => useNow("end"));
  for (const radio of document.querySelectorAll('input[name="mode"]')) radio.addEventListener("change", modeChanged);
  $("clip-form").addEventListener("submit", make);
  $("open-youtube").addEventListener("click", () => { chrome.tabs.create({ url: "https://www.youtube.com/" }); window.close(); });
  $("reload-tab").addEventListener("click", () => { chrome.tabs.reload(tab.id); window.close(); });
  $("stop").addEventListener("click", () => busy($("stop"), "Stopping…", () => send("stop")));
  $("another").addEventListener("click", () => busy($("another"), "Clearing…", () => send("stop")));
  $("start-over").addEventListener("click", () => busy($("start-over"), "Clearing…", () => send("stop")));
  $("retry").addEventListener("click", () => busy($("retry"), "Trying again…", () => send("retry")));
  $("load").addEventListener("click", () => busy($("load"), "Loading into WhatsApp…", async () => {
    const result = await send("load-whatsapp");
    say($("load-result"), result && result.ok
      ? "It is in WhatsApp's Status composer. Check it there, then press Send."
      : (result && result.error) || "Could not load it into WhatsApp", !(result && result.ok));
  }));
  $("save").addEventListener("click", () => busy($("save"), "Saving…", async () => {
    const result = await send("save");
    if (!result || !result.ok) say($("load-result"), (result && result.error) || "Could not save it", true);
    else say($("load-result"), "Saved to your Downloads folder.", false);
  }));
  $("open-settings").addEventListener("click", async () => {
    const s = await settings();
    $("settings-token").value = s.token;
    $("settings-server").value = s.server;
    $("settings-quality").value = s.quality;
    $("settings-result").hidden = true;
    fillSchedule(s);
    show("settings");
  });
  $("settings-back").addEventListener("click", () => main());
  for (const id of ["sched-quiet-on", "sched-quiet-start", "sched-quiet-end", "sched-gap",
                    "sched-forward", "sched-idle", "sched-notices"]) {
    $(id).addEventListener("change", saveSchedule);
  }
  $("open-queue").addEventListener("click", openQueue);
  $("settings-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await busy($("settings-save"), "Saving…", () =>
      saveSettings($("settings-server").value, $("settings-token").value, $("settings-quality").value, $("settings-result")));
  });
  $("setup-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const ok = await busy($("setup-save"), "Connecting…", () =>
      saveSettings($("setup-server").value, $("setup-token").value, null, $("setup-error")));
    if (ok) setTimeout(main, 600);
  });
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local" || !("job" in changes)) return;
    if (!document.querySelector("#view-settings").hidden) return;
    render(changes.job.newValue || null);
  });
}

async function main() {
  const s = await settings();
  if (!s.token) {
    $("setup-server").value = s.server;
    return show("setup");
  }
  const job = (await chrome.storage.local.get("job")).job || null;
  if (job) send("resume").catch(() => {});
  return render(job);
}

wire();
modeChanged();
main();
