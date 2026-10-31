/* wastatus local page.
   Vanilla, because the whole interface is one form, one preview and two buttons,
   and a build step would be more machinery than the thing it builds. */

const TOKEN = document.body.dataset.token;
const $ = (id) => document.getElementById(id);
/* The hosted page (SnipShare) loads `hosted.js` first, which answers the few
   questions that differ there: the extension reads the video and loads WhatsApp,
   in the person's own browser. Null on the local tool, which is every check below. */
const HOSTED = window.SnipShare || null;

const POLL_MS = 600;
const STATE_MS = 15000;
const CAPTION_SAVE_MS = 700;

/* An <img> or <video> cannot send a header, so media carries the token in the URL. */
const media = (kind, stem) =>
  `/api/${kind}?stem=${encodeURIComponent(stem)}&t=${encodeURIComponent(TOKEN)}`;

const STORE_KEY = "wastatus.form";
const SAVED_KEY = "wastatus.saved";   // stems downloaded onto this device
const OPEN_KEY = "wastatus.open";     // which cards you left open

/* Which sections start open on a page you have never opened before. The clip and
   the two that show you the result; the rest are one tap away and their headers
   say what is in them. */
const SECTIONS = ["clip", "look", "words", "extras", "preview", "stickers", "post", "recent"];
const OPEN_BY_DEFAULT = { clip: true, preview: true, post: true, recent: true };

const MODE_HINTS = {
  card: "The album art on a blurred background, with a waveform. Audio only.",
  video: "The real video frames, blur filled to fit. Slower, and more data.",
};

/* What goes behind the frames. Named rather than a checkbox, because "not blurred"
   will not always mean black, and a name is what the renderer is sent. */
const FILL_HINTS = {
  blur: "A darkened, blurred copy of the same frames fills the 9:16 frame.",
  black: "Plain black, which is what WhatsApp draws Status on, so the edges of the "
       + "picture stop being edges.",
};

let mode = "card";
let fill = "blur";
/* Where the picture goes, in the fractions everything placed uses, or null for
   "fitted", which is what it has always been. `placing` is whether its box is on
   the frame; `pickedPicture` is whether that box is the thing the keys drive. */
let framing = null;
let placing = false;
let pickedPicture = false;
let current = null;      // the clip on show: the object /api/state returns
let whatsapp = { ready: false, detail: "", can_launch: false };
let host = "";           // the machine running the tool, for "which laptop is that"
let driving = false;     // a post or a load is in flight, here or in another tab
let windowEdit = "duration";   // which of length or end the person set last
let captionTimer = null;
let decals = [];         // stickers placed on the frame, in fractions of it
let picked = -1;         // index of the selected one, or -1 for none
let decalsDirty = false; // changed since the clip below was rendered
let decalsEditing = false; // handles asked for again after a clip was made
let bands = { top: 0.12, bottom: 0.15 };
let searchTimer = null;
let atLaptop = true;     // the page was opened from this machine, not another device
let renderTask = null;   // the render being watched, so Stop has something to stop
let armed = null;        // Delete is waiting for its second press
let working = false;     // a render is in flight, so the button is not idle
let maxDuration = 90;
let stopWanted = false;  // hosted: Stop pressed after the capture, before the render's id

/* ─────────────────────────  talking to the tool  ───────────────────────── */

// Longer than anything the server does in one request (a YouTube look-up gives up
// at 45 seconds) and than a sticker takes to send on a slow line, so only a dead
// connection reaches it, and a button never spins for the browser's own minutes.
const REQUEST_TIMEOUT_MS = 120000;
// Safari before 16 has no AbortSignal.timeout; there a request simply has no limit
// of its own rather than failing to start.
const timeoutSignal = (ms) => (AbortSignal.timeout ? AbortSignal.timeout(ms) : undefined);

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      signal: options.signal || timeoutSignal(REQUEST_TIMEOUT_MS),
      headers: {
      "X-Wastatus-Token": TOKEN,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(options.headers || {}),
      },
    });
  } catch (error) {
    if (error && error.name === "TimeoutError") {
      throw new Error("the connection is too slow right now. Try again");
    }
    throw error;
  }
  let payload = {};
  try { payload = await response.json(); } catch { /* empty body */ }
  if (response.status === 403) {
    // The token belongs to one run of the server, on purpose: nothing is stored
    // and nothing is reused. So every tab left open across a restart is holding a
    // dead one, and everything it asks for comes back 403, including the health
    // check. That looks like a broken tool and is a stale page, so say which.
    // Hosted, it belongs to a session instead, and a signed-out page reloads into
    // the sign-in page.
    if (HOSTED) staleSession();
    const stale = new Error(
      "this page is older than the server. Reload it to pick up the new token.");
    stale.status = 403;
    throw stale;
  }
  if (!response.ok) {
    const error = new Error(payload.error || `request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

/* Once, not in a loop: a refusal that a reload does not cure says so instead. */
function staleSession() {
  try {
    const last = Number(sessionStorage.getItem("snipshare.reloaded") || 0);
    if (Date.now() - last < 60000) return;
    sessionStorage.setItem("snipshare.reloaded", String(Date.now()));
  } catch { return; }
  location.reload();
}

const post = (path, body) =>
  api(path, { method: "POST", body: JSON.stringify(body) });

/* The same request, answered with a picture instead of JSON. `api` parses a body
   as JSON and would throw on a JPEG, and an <img src> cannot POST, so this is the
   one route that needs its own small helper. */
/* The response, not the picture. The preview answers with a header saying which
   rows of the frame move, and the two have to arrive together. Failures are still
   thrown here, so a caller wanting only pixels goes straight to `.blob()`. */
async function postForImage(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "X-Wastatus-Token": TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (response.status === 403) {
    throw new Error(
      "this page is older than the server. Reload it to pick up the new token.");
  }
  if (!response.ok) {
    let payload = {};
    try { payload = await response.json(); } catch { /* not json */ }
    throw new Error(payload.error || `request failed (${response.status})`);
  }
  return response;
}

/* ─────────────────────  how tall the top bar is  ───────────────────── */

/* On a laptop the preview column is stuck to the top of the screen, and the thing
   it is stuck under is the top bar, which is sticky itself. That bar's height is
   not a number a stylesheet can know: the tagline appears at 600px, the brand line
   is one line or two depending on the window, and the browser's own text size
   moves all of it. So it is measured here and the stylesheet reads it, both for
   where the column stops and for how much height is left for the frame. The CSS
   carries this machine's measurement as a fallback, for the moment before this
   runs and for the case where it never does. See DECISIONS.md D-067. */
const topbar = document.querySelector(".topbar");

function measureTopbar() {
  if (!topbar) return;
  document.documentElement.style.setProperty(
    "--topbar", `${Math.round(topbar.getBoundingClientRect().height)}px`);
}

measureTopbar();
if (topbar && window.ResizeObserver) {
  new ResizeObserver(measureTopbar).observe(topbar);
} else {
  window.addEventListener("resize", measureTopbar);
}


/* ─────────────────────────  the folding cards  ───────────────────────── */

/* A fold nobody asked for is not written down as a preference. Your own presses
   are. The flag rides on the card rather than in a variable, because `toggle`
   fires on a later task: a flag raised and lowered around the assignment is
   already down by the time the listener reads it. */
const section = (name) => $(`sec-${name}`);

function openSection(name, open) {
  const card = section(name);
  if (!card || card.open === open) return;
  card.dataset.auto = "1";
  card.open = open;
}

function rememberOpen() {
  const state = {};
  SECTIONS.forEach((name) => { state[name] = section(name).open; });
  try { localStorage.setItem(OPEN_KEY, JSON.stringify(state)); } catch { /* private mode */ }
}

function restoreOpen() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(OPEN_KEY) || "{}"); } catch { /* ignore */ }
  SECTIONS.forEach((name) => {
    const card = section(name);
    const want = typeof saved[name] === "boolean" ? saved[name] : !!OPEN_BY_DEFAULT[name];
    if (card.open !== want) {
      card.dataset.auto = "1";
      card.open = want;
    }
    card.addEventListener("toggle", () => {
      if (card.dataset.auto) delete card.dataset.auto;
      else rememberOpen();
      if (name === "stickers" && card.open && !$("shelf").children.length) loadShelf();
    });
  });
}

/* The header of a folded card has to answer what is inside it, or folding it is
   just hiding it. */
function paintSummaries() {
  const start = $("start").value.trim() || "0:00";
  const end = $("end").value.trim();
  const length = $("duration").value.trim();
  $("val-clip").textContent = $("url").value.trim()
    ? [end ? `${start} to ${end}` : `from ${start}`, length ? `${length}s` : ""]
        .filter(Boolean).join(" · ")
    : "no link yet";

  $("val-look").textContent = (mode === "video"
    ? ["Video frames", fill === "black" ? "black" : "blurred"]
    : ["Artwork card"]).concat(framing ? "placed" : []).join(" · ");

  const words = [$("title").value.trim(), $("channel").value.trim()].filter(Boolean);
  $("val-words").textContent = words.length ? words.join(" · ") : "from the video";
  $("dot-words").hidden = !words.length;

  const extras = [];
  if ($("footer").value.trim()) extras.push("footer");
  if ($("eyebrow").value.trim()) extras.push("label");
  if ($("topline").value.trim()) extras.push("top text");
  if (decals.some(isText)) extras.push("free text");
  extras.push($("wave").checked ? "waveform on" : "waveform off");
  $("val-extras").textContent = extras.join(" · ");

  $("val-preview").textContent = $("guides").checked ? "Safe areas on" : "Safe areas off";

  $("val-stickers").textContent = decals.length
    ? (decals.length === 1 ? "1 placed" : `${decals.length} placed`)
    : "none";
  $("dot-stickers").hidden = !decals.length;

  $("val-post").textContent = current ? `${current.size_mb} MB` : "nothing yet";

  // The clip on show is pixels and the form may have moved on since it was made.
  paintStale();
}

/* Clearing belongs to the card it is in: the link, the window and the words. What
   it leaves alone is what you set once and keep, the look and the waveform, and
   any stickers you have placed. */
$("clear").addEventListener("click", (event) => {
  // Inside a <summary>, so without this the card folds as well.
  event.preventDefault();
  event.stopPropagation();
  ["url", "start", "end", "title", "channel", "footer", "eyebrow",
   "topline"].forEach((id) => {
    $(id).value = "";
  });
  wordsFor = "";
  clearPreview();
  $("duration").value = "30";
  windowEdit = "duration";
  linkWindow("duration");
  paintClear();
  remember();
  $("url").focus();
});

/* ─────────────────────────  health  ───────────────────────── */

/* Three checks behind one chip. On a phone the three pills they used to be were
   the first third of the screen, and they only ever matter when one is wrong. */

/* Every fifteen seconds, and from a phone that is sometimes over a relayed tailnet
   rather than the local network. Two of these can be in the air at once there, and
   the slower one can land second: without this, a stale answer repaints the health
   row and the Recent strip over a newer one. The same guard the word preview uses. */
let stateSeq = 0;

async function refreshState(fresh = false) {
  const mine = ++stateSeq;
  let state;
  try {
    state = await api(`/api/state${fresh ? "?fresh=1" : ""}`);
  } catch (error) {
    if (mine !== stateSeq) return;
    paintStatus([{ ok: false, what: "the tool", detail: error.message }]);
    return;
  }
  if (mine !== stateSeq) return;   // a newer answer is already on screen

  whatsapp = state.whatsapp;
  host = state.host || "";
  driving = state.busy;
  maxDuration = state.max_duration || maxDuration;
  // Which device you are sitting at decides which button is the big one. The
  // server answers this from the connection, not from the user agent: you can open
  // the tailnet address on the laptop, and a guess about the device would be wrong.
  // Hosted, the question is whether this browser has the extension.
  atLaptop = HOSTED ? HOSTED.ready() : state.local !== false;
  document.body.dataset.where = atLaptop ? "here" : "away";

  if (HOSTED) {
    paintStatus(HOSTED.rows(state));
  } else paintStatus([
    { ok: state.ffmpeg, what: "ffmpeg", detail: state.ffmpeg ? "found" : "not on PATH" },
    {
      ok: state.provider,
      what: "token provider",
      detail: state.provider ? "installed" : "run scripts/setup_provider.sh once",
    },
    {
      // A found browser with controls that have moved is not ready, whatever the
      // browser says. It rides on this row rather than a fifth one, because it is
      // the same question: can this thing post.
      ok: whatsapp.ready && !controlsFault,
      what: "WhatsApp Web",
      detail: controlsFault && whatsapp.ready ? controlsFault : whatsappDetail(),
      action: whatsapp.ready ? "" : (whatsapp.can_launch ? "start it" : "recheck"),
    },
    // The fourth row is the only one that is not a check. `--also-on tailscale`
    // is passed at every start and remembered nowhere, DECISIONS.md D-027, so a
    // restart silently takes the phone away and the laptop's page looks perfectly
    // healthy, because it is. Grey rather than amber: loopback only is the
    // default, it is not a fault, and it is usually what you want. T-025.
    {
      ok: Boolean(state.also_on),
      tone: state.also_on ? "ok" : "idle",
      what: "another device",
      // `also_on` is the bare address. The port is this page's own, which is the
      // same one, and an address without it is not something you can type in.
      detail: state.also_on
        ? `open http://${state.also_on}:${location.port || "80"} there`
        : "this laptop only. Restart with --also-on tailscale to reach it from "
          + "a phone",
    },
  ]);

  if (state.bands) {
    bands = state.bands;
    document.documentElement.style.setProperty("--band-top", `${bands.top * 100}%`);
    document.documentElement.style.setProperty("--band-bottom", `${bands.bottom * 100}%`);
  }
  paintGifSource(state.gifs);
  if (!state.stickers) {
    $("sticker-hint").textContent = HOSTED
      ? "The sticker library is not available on this server right now."
      : "The sticker library is not installed. Run scripts/setup_stickers.sh once.";
  }
  $("foot-out").textContent = HOSTED
    ? `Your newest ${state.keep_last} clips are kept`
    : `Clips in ${state.out}, newest ${state.keep_last} kept`;
  if (HOSTED) {
    // A render of ours whose answer never reached this page, after a reload or a
    // dropped request: watch it, rather than leaving Make refused with no way out.
    if (state.rendering && !working && !renderTask) {
      setBusy(true);
      renderTask = state.rendering;
      watch(state.rendering, onRenderDone);
    }
    renderRecent(state.clips);
    $("val-recent").textContent = state.clips.length
      ? (state.clips.length === 1 ? "1 clip" : `${state.clips.length} clips`)
      : "none yet";
    openAsked(state.clips);
    paintPostButtons();
    paintMake();
    return;
  }
  // With the port. An address without one is not something anybody can type into
  // a phone, and this line existed to be typed. The status panel's own row has
  // said it this way all along; this one had not. D-069.
  $("foot-reach").textContent = state.also_on
    ? `Also reachable at ${state.also_on}:${location.port || "80"}. `
      + "Nothing is sent until you press Send."
    : "Loopback only. Nothing is sent until you press Send.";
  $("status-where").textContent = atLaptop
    ? `You are on ${host || "this machine"}, where the tool runs.`
    : `You are on another device. The tool, and the browser it posts through, are on ${
        host || "the laptop"}.`;
  renderRecent(state.clips);
  $("val-recent").textContent = state.clips.length
    ? (state.clips.length === 1 ? "1 clip" : `${state.clips.length} clips`)
    : "none yet";
  paintPostButtons();
}

/* `/app?clip=NAME`: a clip opened from the account page's History. Once, and the
   address is put back so a reload does not keep reopening it. */
function openAsked(clips) {
  const asked = new URLSearchParams(location.search).get("clip");
  if (!asked) return;
  history.replaceState(null, "", location.pathname + location.hash);
  const found = clips.find((clip) => clip.stem === asked);
  if (found) { show(found); recall(found); }
}

/* "Chrome/150.0.7871.186 on port 9226" is more than a line can hold, and from the
   phone the useful half is which machine that browser is on. */
function whatsappDetail() {
  if (!whatsapp.ready) return whatsapp.detail || "no logged in tab found";
  const where = host ? ` on ${host}` : "";
  return whatsapp.port === null ? `ready${where}` : `ready${where}, port ${whatsapp.port}`;
}

function paintStatus(rows) {
  // A grey row is information rather than a check, so it never turns the chip
  // amber: "this laptop only" is the default and is not something to fix.
  const bad = rows.filter((row) => !row.ok && row.tone !== "idle");
  const chip = $("status-chip");
  chip.dataset.state = bad.length ? "warn" : "ok";
  $("status-text").textContent = bad.length
    ? (bad.length === 1 ? `${bad[0].what} needs you` : `${bad.length} checks`)
    : "All set";

  $("status-list").innerHTML = rows.map((row) => `
    <li>
      <span class="dot ${row.tone === "idle" ? "dot--idle"
                        : row.ok ? "dot--ok" : "dot--warn"}"></span>
      <span class="what">${escapeHtml(row.what)}</span>
      <span class="detail">${escapeHtml(row.detail || "")}</span>
      ${row.action
        ? `<span class="spacer"></span>
           <button type="button" class="button button--quiet button--small"
                   data-do="${row.action === "start it" ? "launch" : "recheck"}">
             ${escapeHtml(row.action)}</button>`
        : ""}
    </li>`).join("");

  $("status-list").querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", async () => {
      if (button.dataset.do !== "launch") return refreshState(true);
      button.disabled = true;
      button.textContent = "starting";
      try {
        await post("/api/browser", {});
        hide($("error"));
      } catch (error) {
        button.disabled = false;
        return fail($("error"), error.message);
      }
      // Chrome takes a few seconds to open, and longer if a QR code is waiting.
      setTimeout(() => refreshState(true), 4000);
    });
  });
}

/* ─────────────────────────  light, dark, system  ───────────────────────── */

/* Three states on one button. "System" is the default and is not stored as a
   value, it is the absence of one, so a machine that changes its own mind at
   sunset keeps being followed. The <head> applies the stored choice before the
   first paint; this only handles the pressing. */

const THEMES = ["system", "light", "dark"];
const THEME_KEY = "wastatus.theme";

function theme() {
  const stored = (() => {
    try { return localStorage.getItem(THEME_KEY); } catch { return null; }
  })();
  return THEMES.includes(stored) ? stored : "system";
}

function setTheme(next) {
  if (next === "system") {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = next;
  }
  try {
    if (next === "system") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, next);
  } catch { /* private mode */ }
  paintTheme(next);
}

function paintTheme(now) {
  // Attributes, not the `hidden` property: these are SVG elements. See `playing`.
  THEMES.forEach((name) => (name === now ? unhide : hide)($(`theme-${name}`)));
  const label = `Theme: ${now}`;
  $("theme").setAttribute("aria-label", label);
  $("theme").title = `${label}. Press for ${THEMES[(THEMES.indexOf(now) + 1) % 3]}`;
}

$("theme").addEventListener("click", () => {
  setTheme(THEMES[(THEMES.indexOf(theme()) + 1) % THEMES.length]);
});

$("status-chip").addEventListener("click", () => {
  const open = $("status-chip").getAttribute("aria-expanded") === "true";
  $("status-chip").setAttribute("aria-expanded", String(!open));
  $("status-panel").hidden = open;
});

/* ─────────────────────────  recents  ───────────────────────── */

/* null, not "": an empty clip list has the signature "", so using that as the
   rebuild sentinel meant an empty strip never repainted. It cost the "Nothing yet"
   line on a first run, and left a deleted clip on show until the next change. */
let recentSignature = null;

function renderRecent(clips) {
  const list = $("recent");
  // Media is served no-store, so rebuilding this strip refetches every thumbnail.
  // Polling every fifteen seconds turned that into a download loop.
  const saved = savedStems();
  const signature = clips.map((clip) =>
    `${clip.stem}:${clip.size_mb}:${saved.has(clip.stem) ? 1 : 0}`).join("|");
  if (signature === recentSignature) return;   // never true for the null sentinel
  recentSignature = signature;
  if (!clips.length) {
    list.innerHTML = `<p class="hint">Nothing yet. The clips you make appear here.</p>`;
    return;
  }
  list.innerHTML = clips.map((clip) => `
    <div class="tile" data-stem="${escapeHtml(clip.stem)}">
      <button class="tile__open" type="button"
              title="${escapeHtml(clip.title || clip.name)}">
        ${clip.has_frame
          ? `<img class="tile__thumb" src="${media("frame", clip.stem)}" alt="" loading="lazy">`
          : `<span class="tile__thumb"></span>`}
        ${saved.has(clip.stem)
          ? `<span class="tile__saved" title="Saved on this device">✓</span>`
          : ""}
        <span class="tile__body">
          <span class="tile__name">${escapeHtml(clip.name)}</span>
          <span class="tile__meta">${escapeHtml(when(clip.created))}</span>
          <span class="tile__meta">${clip.video ? "video · " : ""}${clip.size_mb} MB</span>
        </span>
      </button>
      <button class="tile__kill" type="button"
              title="Delete this one" aria-label="Delete ${escapeHtml(clip.name)}">×</button>
    </div>`).join("");

  list.querySelectorAll(".tile").forEach((tile) => {
    const stem = tile.dataset.stem;
    tile.querySelector(".tile__open").addEventListener("click", async () => {
      const found = (await api("/api/state")).clips.find((clip) => clip.stem === stem);
      if (found) { show(found); recall(found); }
    });
    const kill = tile.querySelector(".tile__kill");
    kill.addEventListener("click", () => killClip(stem, kill));
    // A repaint throws away the DOM, so the armed one is redrawn from the variable
    // that outlived it rather than lost mid-question.
    if (stem === killArmed) armKill(kill);
  });
}

/* ── throwing a variant away from the strip ──────────────────────────────── */

/* Which tile is mid-question, by stem rather than by element: the strip repaints
   on its own whenever the clip list changes, and the element asked first is not
   the element that answers. */
let killArmed = null;
let killTimer = null;

function armKill(button) {
  button.dataset.armed = "true";
  button.textContent = "Delete?";
  button.title = "Press again to delete";
  button.setAttribute("aria-label", "Press again to delete");
}

/* Back to a cross. Takes the button it is given, or finds the armed one, because
   disarming happens both from a press and from a timer that holds no element. */
function disarmKill(button) {
  clearTimeout(killTimer);
  killTimer = null;
  const target = button
    || document.querySelector('.tile__kill[data-armed="true"]');
  killArmed = null;
  if (!target) return;
  const tile = target.closest(".tile");
  const name = tile ? tile.querySelector(".tile__name").textContent : "this clip";
  delete target.dataset.armed;
  target.textContent = "×";
  target.title = "Delete this one";
  target.setAttribute("aria-label", `Delete ${name}`);
}

/* Two presses, the same rule as the Delete button under the clip: a dialog is
   dismissed by habit, a control that has visibly changed its mind is not. Only
   one tile can be asking at a time, so arming a second disarms the first: two
   armed crosses on one strip is two ways to delete the wrong thing. */
async function killClip(stem, button) {
  hide($("recent-error"));
  if (killArmed !== stem) {
    disarmKill();
    killArmed = stem;
    armKill(button);
    killTimer = setTimeout(() => disarmKill(), 4000);
    return;
  }
  disarmKill(button);
  try {
    await post("/api/clip/delete", { stem });
  } catch (error) {
    return fail($("recent-error"), error.message);
  }
  // The one on show may be the one just deleted, and what it points at is gone.
  if (current && current.stem === stem) clearClip();
  recentSignature = null;
  refreshState();
}

/* Which clips this device already has a copy of. It is the answer to "did I
   download this one already", and it is per device, so the laptop and the phone
   each keep their own account of it. */
function savedStems() {
  try { return new Set(JSON.parse(localStorage.getItem(SAVED_KEY) || "[]")); }
  catch { return new Set(); }
}

function markSaved(stem) {
  const saved = savedStems();
  saved.add(stem);
  try { localStorage.setItem(SAVED_KEY, JSON.stringify([...saved].slice(-200))); }
  catch { /* private mode */ }
  recentSignature = null;
  refreshState();
}

/* "today 21:52", "yesterday 09:07", "18 Aug". A bare timestamp on every tile is
   noise; what you want to know is whether this is the one you just made. */
function when(epoch) {
  if (!epoch) return "";
  const made = new Date(epoch * 1000);
  const now = new Date();
  const clockTime = made.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const midnight = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const days = Math.round((midnight(now) - midnight(made)) / 86400000);
  if (days === 0) return `today ${clockTime}`;
  if (days === 1) return `yesterday ${clockTime}`;
  return made.toLocaleDateString([], { day: "numeric", month: "short" });
}

/* ─────────────────────────  making a clip  ───────────────────────── */

$("form").addEventListener("submit", async (event) => {
  event.preventDefault();
  // The button is grey, but `requestSubmit` does not ask a button whether it is
  // enabled, so Ctrl+Enter arrives here anyway, during a render as well: a second
  // press would start a second render with the first one still running.
  if (working || settled()) return;
  hide($("error"));
  // The last moment stale words can be caught. The `input` guard covers typing and
  // pasting; this covers everything else that can put a value in a box without an
  // input event, including a form restored from the last session.
  if (forgetWordsIfSongChanged()) {
    note($("error"), "New link, so the words on the card were cleared. "
      + "They will be read from the video.");
  }

  const body = {
    url: $("url").value.trim(),
    start: $("start").value.trim(),
    video: mode === "video",
    wave: $("wave").checked,
    fill,
    framing,
    title: $("title").value,
    channel: $("channel").value,
    footer: $("footer").value,
    eyebrow: $("eyebrow").value,
    topline: $("topline").value,
    // A line with nothing in it is a box somebody opened and left: it has no
    // picture, and the renderer would refuse the whole clip over it.
    stickers: decals.filter((one) => !isText(one) || one.text.trim()),
  };
  // Whichever of the two the person set last is the one they meant.
  const length = Number($("duration").value.trim());
  if (windowEdit === "end" && $("end").value.trim()) {
    body.end = $("end").value.trim();
  } else if (Number.isFinite(length) && length > 0) {
    if (length > maxDuration) {
      return fail($("error"), `WhatsApp takes ${maxDuration} seconds at most.`);
    }
    body.duration = length;
  } else {
    return fail($("error"), "Length is a number of seconds, or set an end time.");
  }
  if (!body.url) return fail($("error"), "Paste a YouTube link first.");

  remember();
  setBusy(true);
  try {
    if (HOSTED) {
      // Read in this browser first, by the extension; the server then renders what
      // it uploaded. The read is the first step on the same progress line.
      const started = Date.now();
      body.captured = await HOSTED.capture(body, (progress) => paint({
        kind: "render", stage: "read", stages: ["probe", "download", "compose", "render"],
        message: progress.message || "reading the video",
        elapsed: (Date.now() - started) / 1000,
      }));
    }
    const { id } = await post("/api/render", body);
    renderTask = id;
    if (stopWanted) {
      // Pressed while the render was being asked for: stop it now it has a name.
      stopWanted = false;
      post("/api/cancel", { id }).catch(() => {});
    }
    watch(id, onRenderDone);
  } catch (error) {
    setBusy(false);
    fail($("error"), error.message);
  }
});

function onRenderDone(task) {
  setBusy(false);
  if (task.status === "cancelled") {
    return fail($("error"), HOSTED ? "Stopped. Nothing was made."
      : "Stopped. Nothing was written to the output folder.");
  }
  if (task.status === "failed") return fail($("error"), task.error);
  arrived();
  show(task.result);
  recall(task.result);
  // They are in the video now. Drawing them again over the top would be a lie.
  decalsDirty = false;
  decalsEditing = false;
  paintDecals();
  refreshState();
}

/* The clip is made, so the questions that made it can fold away and the answer can
   come up the screen. On a laptop the preview is already beside the form, so
   nothing moves and nothing needs to. None of this is written down as a
   preference: reopen the page tomorrow and it is laid out the way you left it. */
function arrived() {
  if (!window.matchMedia("(max-width: 900px)").matches) return;
  ["clip", "look", "words", "extras"].forEach((name) => openSection(name, false));
  openSection("preview", true);
  openSection("post", true);
  section("preview").scrollIntoView({ behavior: "smooth", block: "start" });
}

/* Stopping kills the yt-dlp or ffmpeg that is running, and the pipeline deletes
   the half written file on its way out. Only a render: a post cannot be taken back
   halfway through an upload. It sits beside Make, which is where you are looking. */
$("stop").addEventListener("click", async () => {
  // Still reading the video in the browser: the extension stops, and the capture
  // comes back as a failure the submit handler already reports.
  if (!renderTask && HOSTED) {
    // Reading the video, or asking for the render that follows it: either way the
    // press is kept, and acted on as soon as there is something to stop.
    if (!HOSTED.stop()) stopWanted = true;
    $("stop").disabled = true;
    $("stop").textContent = "Stopping";
    $("stop").setAttribute("aria-busy", "true");
    return;
  }
  if (!renderTask) return;
  $("stop").disabled = true;
  $("stop").textContent = "Stopping";
  $("stop").setAttribute("aria-busy", "true");
  try {
    await post("/api/cancel", { id: renderTask });
  } catch (error) {
    $("stop").disabled = false;
    $("stop").textContent = "Stop";
    $("stop").removeAttribute("aria-busy");
    fail($("error"), error.message);
  }
});

/* ─────────────────────────  posting  ───────────────────────── */

$("load").addEventListener("click", (event) => {
  if (pastStale($("load"), event)) sendClip(false);
});
$("send").addEventListener("click", (event) => {
  if (pastStale($("send"), event)) sendClip(true);
});

/* The browser does the saving. This only records that this device now has it, so
   the Recent strip can say which ones you already pulled down. The anchor's own
   navigation is what saves the file, so a spent press has to `preventDefault` it,
   which is why the event is handed over rather than only the button. */
$("download").addEventListener("click", (event) => {
  if (!pastStale($("download"), event)) return;
  if (current) markSaved(current.stem);
});

async function sendClip(send) {
  if (!current) return;
  hide($("post-error"));
  hide($("post-done"));
  const button = send ? $("send") : $("load");
  const was = button.textContent;
  [$("load"), $("send")].forEach((b) => { b.disabled = true; });
  button.textContent = send ? "Sending..." : "Loading...";
  button.setAttribute("aria-busy", "true");

  try {
    // Post what is on screen, not what happens to be on disk. If the edit could
    // not be saved, stop: sending the previous caption is worse than not sending.
    if (!await saveCaption()) {
      throw new Error("the caption could not be saved, so nothing was sent");
    }
    if (HOSTED) {
      await HOSTED.load(current, captionText());
      button.textContent = was;
      button.removeAttribute("aria-busy");
      paintPostButtons();
      $("post-done").textContent = "Loaded into WhatsApp Web in this browser, with the "
        + "caption in place. Press Send there when you are ready.";
      unhide($("post-done"));
      return;
    }
    const { id } = await post("/api/post", {
      stem: current.stem,
      send,
      follow_up: send && $("follow-up").checked,
    });
    watch(id, (task) => {
      button.textContent = was;
      button.removeAttribute("aria-busy");
      driving = false;   // ours has finished; a poll would take up to 15s to say so
      paintPostButtons();
      if (task.status === "failed") return fail($("post-error"), task.error);
      const done = task.result || {};
      $("post-done").textContent = done.sent
        ? `Live on your Status. Uploaded in ${done.seconds}s` +
          `${done.follow_up ? ", plus the text status" : ""}.` +
          (done.follow_up_error
            ? ` The text status did not go out (${done.follow_up_error}). Post it by hand; ` +
              "the video is already live, so do not send it again."
            : "")
        : `Loaded into WhatsApp on ${host || "the laptop"} with the caption in place. ` +
          "Press Send in that browser window when you are ready.";
      unhide($("post-done"));
    });
  } catch (error) {
    button.textContent = was;
    button.removeAttribute("aria-busy");
    driving = false;
    paintPostButtons();
    fail($("post-error"), error.message);
  }
}

/* ────────────  the clip on show against the form above it  ──────────── */

/* What the clip below would be missing if you sent it as it stands.

   A comparison, not a flag. `current.job` is the record of what actually went into
   the clip, so the answer can be worked out from it whenever it is wanted. A flag
   would have to be set from every place that can change something, and the place
   that gets forgotten is the place the page then lies about.

   The link and the window are deliberately not in here. They choose *which* clip
   you are making rather than what this one looks like, and pasting the next link
   while the finished clip is still on show is the normal way to use this page: a
   warning there would fire on ordinary work and be learned as noise. */
const DRIFTABLE = [
  ["title", "the title"],
  ["channel", "the second line"],
  ["footer", "the footer"],
  ["eyebrow", "the label"],
  ["topline", "the text at the top"],
];

function drifted() {
  const job = current && current.job;
  if (!job) return [];
  const changes = DRIFTABLE
    .filter(([id]) => ($(id).value || "") !== (job[id] || ""))
    .map(([, name]) => name);
  if (!sameStickers(decals, Array.isArray(job.stickers) ? job.stickers : [])) {
    changes.push("the stickers");
  }
  if ($("wave").checked !== (job.wave !== false)) changes.push("the waveform");
  // Older clips were made before there was a choice, and every one of them is blurred.
  if (mode === "video" && fill !== (job.fill || "blur")) changes.push("the background");
  if (framingDiffers()) {
    changes.push(mode === "video" ? "where the picture goes"
                                  : "where the artwork goes");
  }
  if ((mode === "video") !== !!job.video) changes.push("the look");
  return changes;
}

/* Placed to five decimals in the sidecar and carried back as numbers, so an exact
   comparison is the right one: a sticker that has not been touched is the same
   object it was recalled as. */
function sameStickers(here, there) {
  if (here.length !== there.length) return false;
  return here.every((one, at) => {
    const was = there[at];
    // The words as well as the id. Two placed lines that have never been moved are
    // the same rectangle with different things written in them, and without this
    // the clip would not be called stale after a line was retyped: the one thing
    // free text is for is retyping it.
    return one.id === was.id && (one.text || "") === (was.text || "")
      && one.x === was.x && one.y === was.y
      && one.size === was.size && (one.rotation || 0) === (was.rotation || 0);
  });
}

function listed(names) {
  if (names.length === 1) return names[0];
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/* The standing notice. Present whenever the clip does not match the form, whether
   or not anything has been pressed. */
function paintStale() {
  const box = $("post-stale");
  const changes = current ? drifted() : [];
  paintMake();
  if (!changes.length) {
    disarmStale();
    return hide(box);
  }
  box.textContent =
    `This clip was made before you changed ${listed(changes)}. `
    + `Make the clip again to draw ${changes.length === 1 ? "that" : "those"} in.`
    + (staleArmed
        ? ` Press ${STALE_VERBS[staleArmed]} again to use this one anyway.` : "");
  unhide(box);
}

/* ─────────────  nothing left to do  ─────────────

   Asked for on 2026-08-27: once a clip is made, grey the button out, and bring it
   back the moment anything changes. It is the quietest way a page can say that
   what you are looking at is finished, and it costs nothing to be wrong in one
   direction: an enabled button that would make the same clip again is a wasted
   minute, a greyed one that should not be is a dead end.

   So this asks the question the button asks, which is not the question the stale
   notice asks. `drifted` leaves the link and the window out on purpose, because a
   warning about the take you are about to send must not fire while you are setting
   up the next one. Here they count: pressing Make with a new link in the box is
   the most ordinary thing on this page.

   The safe area guides are deliberately not in here either. They change the
   preview and never the pixels, so making the clip again over them would produce
   the same file, and a button that comes back for them would be saying otherwise. */
function settled() {
  const job = current && current.job;
  if (!job || !current.stem) return false;
  if (drifted().length) return false;
  if (videoKey($("url").value) !== videoKey(job.url || "")) return false;
  // Half a second either way: the boxes hold `1:17` and the sidecar holds 77.0,
  // and a clip whose end was trimmed to the length of the video comes back as the
  // window that was made rather than the one that was asked for.
  const start = seconds($("start").value) ?? 0;
  if (Math.abs(start - (job.start || 0)) > 0.5) return false;
  const end = windowEdit === "end" && $("end").value.trim()
    ? seconds($("end").value)
    : start + Number($("duration").value.trim());
  return Number.isFinite(end) && Math.abs(end - (job.end || 0)) <= 0.5;
}

/* The button, and the line under it that says why it is grey. Called from
   `paintStale`, which is the one place every change on this page already reaches. */
function paintMake() {
  const done = !working && settled();
  $("make").disabled = working || done || Boolean(HOSTED && !HOSTED.ready());
  $("make-note").hidden = !done;
  // The keyboard hint is for a button that can be pressed.
  (working || done) ? hide($("shortcut")) : unhide($("shortcut"));
}

/* One press explains, the second goes ahead. Not a block: sending the older take is
   sometimes exactly what was meant, and a page that refuses is a page you have to
   work around. The same two press rule as Delete, and for the same reason, except
   that nothing here changes the button's own label: Download is an anchor whose
   text lives in a span, and rewriting it would throw the span away. */
let staleArmed = null;
let staleTimer = null;

// What the notice calls each action when it asks for a second press.
const STALE_VERBS = { load: "Load", send: "Send", download: "Download",
                      schedule: "Schedule", "queue-add": "Add to queue" };

function disarmStale() {
  clearTimeout(staleTimer);
  staleTimer = null;
  if (staleArmed && $(staleArmed)) delete $(staleArmed).dataset.stale;
  staleArmed = null;
}

/* True when the action may go ahead. False means this press was spent on the
   warning instead. */
function pastStale(button, event) {
  if (!drifted().length) return true;
  if (staleArmed === button.id) { disarmStale(); paintStale(); return true; }
  if (event) event.preventDefault();
  disarmStale();
  staleArmed = button.id;
  button.dataset.stale = "true";
  staleTimer = setTimeout(() => { disarmStale(); paintStale(); }, 6000);
  paintStale();
  $("post-stale").scrollIntoView({ block: "nearest" });
  return false;
}

/* Which button is filled is decided in CSS from `data-where` on the body. This
   decides what is possible, and says why when something is not. */
function paintPostButtons() {
  if (!current) return;
  if (HOSTED) {
    paintSchedule();
    $("load").disabled = !HOSTED.ready();
    $("load-what").textContent = "Opens the Status composer in WhatsApp Web, in this "
      + "browser, with the clip and the caption in place. You press Send there.";
    $("post-hint").textContent = HOSTED.ready() ? "" : `${HOSTED.why()} Download works anywhere.`;
    $("post-hint").hidden = !$("post-hint").textContent;
    return;
  }
  const blocked = !whatsapp.ready || driving;
  [$("load"), $("send")].forEach((b) => { b.disabled = blocked; });

  $("load-what").textContent =
    `Opens the Status composer on ${host || "the laptop"} with the clip and the ` +
    "caption in place. You press Send there.";

  // Each button now says what it does, so this line is only for what is in the way.
  $("post-hint").textContent = !whatsapp.ready
    ? `Load and Send need a logged in WhatsApp Web tab on ${host || "the laptop"}. ` +
      (whatsapp.detail || "None found.")
    : driving
      ? "WhatsApp is being driven by another request. One at a time."
      : "";
  $("post-hint").hidden = !$("post-hint").textContent;
}

/* ─────────────────────────  scheduling  ───────────────────────── */

/* SnipShare only: `window.SnipShare` exists, so the local tool never builds any of
   this (the elements stay hidden). The extension keeps the clip and, at the time,
   puts it in WhatsApp for the person to send. This release prepares only (D-084). */

const SCHED_MIN_MS = 2 * 60000;          // the extension refuses less (queue.MIN_AHEAD_MS)
const SCHED_MAX_MS = 30 * 86400000;      // and more
// The extension's quiet hours are its own setting, which this page cannot see, so
// the warning uses the default window and says "quiet hours" without claiming more.
const QUIET = { start: 23 * 60, end: 7 * 60 };
let schedMode = "schedule";              // or "queue": the same picker, after the last one
let schedChoice = null;                  // the preset picked: a key, or "custom"
let schedBusy = false;
let upNextSeq = 0;

const inQuiet = (date) => {
  const minute = date.getHours() * 60 + date.getMinutes();
  return minute >= QUIET.start || minute < QUIET.end;
};

/* "Sat 1 Nov, 6:00 PM, in 17 hours". */
function describeDue(date, now = Date.now()) {
  const text = `${date.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })}, `
    + date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const minutes = Math.round((date.getTime() - now) / 60000);
  const hours = Math.round(minutes / 60);
  const days = Math.round(minutes / 1440);
  const away = minutes < 90 ? `in ${minutes} minutes`
    : minutes < 2880 ? `in ${hours} hours`
      : `in ${days} days`;
  return `${text}, ${away}`;
}

/* The presets that are still ahead (U9): a passed one is not offered at all. */
function schedPresets(now = new Date()) {
  const at = (days, hour) => {
    const date = new Date(now);
    date.setDate(date.getDate() + days);
    date.setHours(hour, 0, 0, 0);
    return date;
  };
  const list = [
    { key: "hour", label: "In one hour", date: new Date(now.getTime() + 3600000) },
    { key: "evening", label: "This evening, 6 PM", date: at(0, 18) },
    { key: "morning", label: "Tomorrow, 9 AM", date: at(1, 9) },
  ].filter((p) => p.date.getTime() - now.getTime() >= SCHED_MIN_MS);
  list.push({ key: "last", label: "After the last one", date: null });
  return list;
}

const localValue = (date) => {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
    + `T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

function paintSchedPresets() {
  const box = $("sched-presets");
  box.textContent = "";
  schedPresets().forEach((preset) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip";
    button.dataset.preset = preset.key;
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(schedChoice === preset.key));
    button.textContent = preset.label;
    if (preset.date && inQuiet(preset.date)) {
      const quiet = document.createElement("small");
      quiet.textContent = "quiet hours";
      button.append(" ", quiet);
    }
    box.append(button);
  });
}

/* Reads the picker: what it means, in words, before anything is saved. Returns
   {due} or {afterLast: true} when it can be saved, null when it cannot. */
function readSched() {
  const words = $("sched-words");
  const warn = $("sched-warn");
  warn.hidden = true;
  if (schedChoice === "last") {
    words.textContent = "After the last post in your queue, with the usual gap. "
      + "If the queue is empty, that gap from now.";
    return { afterLast: true };
  }
  const value = $("sched-time").value;
  if (!value) {
    words.textContent = "Choose a time.";
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    words.textContent = "That is not a time. Choose one from the list or the field.";
    return null;
  }
  const ahead = date.getTime() - Date.now();
  if (ahead < SCHED_MIN_MS) {
    words.textContent = "Choose a time at least 2 minutes from now.";
    return null;
  }
  if (ahead > SCHED_MAX_MS) {
    words.textContent = "Choose a time within the next 30 days.";
    return null;
  }
  words.textContent = describeDue(date);
  if (inQuiet(date)) {
    warn.textContent = "That is in quiet hours, 11 PM to 7 AM unless you changed them in the "
      + "queue's settings. Choose it only if you want it then.";
    warn.hidden = false;
  }
  return { due: date.getTime() };
}

function chooseSched(key) {
  schedChoice = key;
  const preset = schedPresets().find((p) => p.key === key);
  if (preset && preset.date) $("sched-time").value = localValue(preset.date);
  if (key === "last") $("sched-time").value = "";
  paintSchedPresets();
  readSched();
  hide($("sched-error"));
}

function openSched(mode) {
  if (!current || !HOSTED || !HOSTED.canSchedule()) return;
  schedMode = mode;
  hide($("sched-error"));
  $("sched-title").textContent = mode === "queue" ? "Add to the queue" : "Schedule this Status";
  $("sched-save").textContent = mode === "queue" ? "Add to queue" : "Schedule it";
  $("sched-caption").value = captionText();
  const now = new Date();
  $("sched-time").min = localValue(new Date(now.getTime() + SCHED_MIN_MS));
  $("sched-time").max = localValue(new Date(now.getTime() + SCHED_MAX_MS));
  $("sched-pick").hidden = false;
  const first = mode === "queue" ? "last" : schedPresets()[0].key;
  unhide($("sched"));
  $("schedule").setAttribute("aria-expanded", String(mode === "schedule"));
  $("queue-add").setAttribute("aria-expanded", String(mode === "queue"));
  chooseSched(first);
  $("sched").scrollIntoView({ block: "nearest" });
  (mode === "queue" ? $("sched-save") : $("sched-presets").querySelector(".chip")).focus();
}

function closeSched(focus = true) {
  if (schedBusy) return;
  hide($("sched"));
  $("schedule").setAttribute("aria-expanded", "false");
  $("queue-add").setAttribute("aria-expanded", "false");
  if (focus) (schedMode === "queue" ? $("queue-add") : $("schedule")).focus();
}

/* Each code the extension's worker can answer with, in words that say what to do. */
function schedProblem(error) {
  const limits = HOSTED.scheduling;
  const mb = Math.round(limits.budget_bytes / 1e6);
  return {
    past: "Choose a time at least 2 minutes from now.",
    far: "Choose a time within the next 30 days.",
    limit: `You already have ${limits.pending} scheduled posts, the most allowed. `
      + "Open the queue and cancel one, or wait for one to be posted, then try again.",
    budget: `The clips kept on this computer would pass ${mb} MB. Open the queue and `
      + "cancel a post to free room, then try again.",
    quota: "This computer has no room left to keep the clip. Free some disk space, or "
      + "cancel a scheduled post, then try again.",
    network: "The clip could not be downloaded. Check the connection and try again.",
    gone: "This clip is no longer on SnipShare. Make it again, then schedule it.",
    size: "The clip arrived the wrong size, so it was not kept. Try again.",
    stopped: "The page was closed or reloaded while the clip was being kept, so the "
      + "schedule was not saved. Try again.",
  }[error.code] || error.message;
}

// Opening the picker is the press that is held back by a clip older than the form,
// as for Load; closing it is never held.
$("schedule").addEventListener("click", (event) => {
  if (!$("sched").hidden && schedMode === "schedule") return closeSched();
  if (pastStale($("schedule"), event)) openSched("schedule");
});
$("queue-add").addEventListener("click", (event) => {
  if (!$("sched").hidden && schedMode === "queue") return closeSched();
  if (pastStale($("queue-add"), event)) openSched("queue");
});
$("sched-cancel").addEventListener("click", () => closeSched());
$("sched").addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeSched();
});
$("sched-presets").addEventListener("click", (event) => {
  const chip = event.target.closest("[data-preset]");
  if (chip) chooseSched(chip.dataset.preset);
});
$("sched-time").addEventListener("input", () => {
  schedChoice = "custom";
  paintSchedPresets();
  readSched();
  hide($("sched-error"));
});

$("sched").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (schedBusy || !current) return;
  const when = readSched();
  if (!when) {
    fail($("sched-error"), $("sched-words").textContent || "Choose a time.");
    return $("sched-time").focus();
  }
  schedBusy = true;
  hide($("sched-error"));
  const save = $("sched-save");
  const label = save.textContent;
  [save, $("sched-cancel"), $("sched-time"), $("sched-caption")].forEach((e) => { e.disabled = true; });
  $("sched-presets").querySelectorAll("button").forEach((b) => { b.disabled = true; });
  save.setAttribute("aria-busy", "true");
  $("sched-bar").removeAttribute("value");
  $("sched-progress-text").textContent = "Keeping the clip on this computer";
  unhide($("sched-progress"));
  try {
    const answer = await HOSTED.schedule(current, $("sched-caption").value.trim(), when, (p) => {
      if (p.message) $("sched-progress-text").textContent = p.message;
      if (typeof p.progress === "number") $("sched-bar").value = p.progress;
    });
    schedBusy = false;
    closeSched(false);
    const note = answer && answer.note ? ` ${answer.note}` : "";
    const due = answer && answer.schedule && answer.schedule.due
      ? describeDue(new Date(answer.schedule.due)) : "";
    const toast = (text, options) => (window.SnipShareUI
      ? window.SnipShareUI.toast(text, options) : null);
    toast(due ? `Scheduled for ${due}.${note}` : `Added to your queue.${note}`, {
      action: { label: "Open the queue", run: () => openQueuePage() }, timeout: 10000,
    });
    $("schedule").focus();
    refreshUpNext();
  } catch (error) {
    schedBusy = false;
    fail($("sched-error"), schedProblem(error));
    $("sched-error").scrollIntoView({ block: "nearest" });
  } finally {
    schedBusy = false;
    save.textContent = label;
    save.removeAttribute("aria-busy");
    [save, $("sched-cancel"), $("sched-time"), $("sched-caption")].forEach((e) => { e.disabled = false; });
    $("sched-presets").querySelectorAll("button").forEach((b) => { b.disabled = false; });
    hide($("sched-progress"));
  }
});

async function openQueuePage() {
  try {
    await HOSTED.openQueue();
  } catch (error) {
    fail($("post-error"), error.message);
  }
}
$("queue-open").addEventListener("click", openQueuePage);

/* Up next: a glance at the next three, from the extension. Quiet when it cannot
   say, since it is not a task. */
async function refreshUpNext() {
  const mine = ++upNextSeq;
  const found = await HOSTED.peek();
  if (mine !== upNextSeq) return;
  const list = $("upnext-list");
  list.textContent = "";
  if (!found) return hide($("upnext"));
  unhide($("upnext"));
  const next = Array.isArray(found.next) ? found.next : [];
  $("upnext-empty").hidden = next.length > 0;
  next.forEach((item) => {
    const li = document.createElement("li");
    const when = document.createElement("span");
    when.className = "upnext__when";
    when.textContent = describeDue(new Date(item.due));
    const words = document.createElement("span");
    words.className = "upnext__what";
    words.textContent = `${(item.caption || "").split("\n")[0] || "No caption"}`;
    const state = document.createElement("span");
    state.className = "upnext__state";
    state.textContent = item.word || "";
    li.append(when, words, state);
    list.append(li);
  });
  $("queue-open").textContent = found.needsYou
    ? `Scheduled (${found.needsYou} need you)` : "Scheduled";
}

/* What shows, from the three things that decide it. Called with every repaint of
   the post buttons, so a late answer from the extension or the server shows it. */
function paintSchedule() {
  if (!HOSTED) return;
  const can = Boolean(current) && HOSTED.canSchedule();
  const wasShown = !$("doer-schedule").hidden;
  $("doer-schedule").hidden = !can;
  const note = current ? HOSTED.whyNotSchedule() : "";
  $("sched-phone").textContent = note;
  $("sched-phone").hidden = !note;
  if (!can && !$("sched").hidden) { schedBusy = false; closeSched(false); }
  if (!can) { $("upnext").hidden = true; upNextSeq += 1; }
  else if (!wasShown) refreshUpNext();
}

/* ─────────────────────────  deleting a clip  ───────────────────────── */

/* Two presses rather than a confirm dialog: a dialog is dismissed by habit, and a
   button that has visibly changed its mind is not. It disarms itself after a few
   seconds so a stray press cannot be completed by a later stray press. */
$("delete").addEventListener("click", async () => {
  if (!current) return;
  if (!armed) {
    $("delete").textContent = "Really delete?";
    $("delete").classList.add("button--armed");
    armed = setTimeout(disarmDelete, 4000);
    return;
  }
  disarmDelete();
  hide($("post-error"));
  const stem = current.stem;
  try {
    await post("/api/clip/delete", { stem });
  } catch (error) {
    return fail($("post-error"), error.message);
  }
  clearClip();
  refreshState();
});

function disarmDelete() {
  clearTimeout(armed);
  armed = null;
  $("delete").textContent = "Delete";
  $("delete").classList.remove("button--armed");
}

/* Nothing is on show any more, because the file it pointed at is gone. */
function clearClip() {
  current = null;
  const showing = $("preview");
  showing.pause();
  showing.removeAttribute("src");
  showing.removeAttribute("poster");
  showing.load();
  hide(showing);
  hide($("player"));
  hide($("caption-band"));
  hide($("result"));
  unhide($("nothing-yet"));
  unhide($("empty"));
  paintSummaries();
  recentSignature = null;   // so the strip rebuilds without it
}

/* ─────────────────────────  watching a task  ───────────────────────── */

/* Asked again only once the last answer is in, rather than every 600ms whatever is
   happening. On a slow link `setInterval` stacks requests up behind each other, and
   two answers landing together can paint out of order or finish the task twice: a
   render that ended would be shown, recalled and have its stickers put away twice
   over. One in the air, one ending, and the next is scheduled from the last. */
/* Follows one task until it ends. Each task has its own timer, so watching a post
   never stops the watch on a render, and watching the same task again replaces the
   first watch rather than running two. A dropped poll is tried again: only an
   answer from the server that the task is gone, or several failures in a row, ends
   the watch as failed, because the task itself may well still be running. */
const watching = new Map();   // task id -> the cancel for its watch
const POLL_TRIES = 4;

function watch(id, done) {
  if (watching.has(id)) watching.get(id)();
  let over = false;
  let timer = null;
  let misses = 0;
  const cancel = () => { over = true; clearTimeout(timer); if (watching.get(id) === cancel) watching.delete(id); };
  watching.set(id, cancel);

  const finish = (task) => {
    if (over) return;
    cancel();
    done(task);
  };

  const tick = async () => {
    let task;
    try {
      task = await api(`/api/task?id=${encodeURIComponent(id)}`);
    } catch (error) {
      if (over) return;
      misses += 1;
      if (error.status === 404 || error.status === 403 || misses >= POLL_TRIES) {
        return finish({ status: "failed", error: error.message, result: {} });
      }
      timer = setTimeout(tick, POLL_MS * 2 ** misses);
      return;
    }
    if (over) return;
    misses = 0;
    paint(task);
    if (task.status !== "running") return finish(task);
    timer = setTimeout(tick, POLL_MS);
  };

  timer = setTimeout(tick, POLL_MS);
}

function paint(task) {
  if (task.kind !== "render") return;
  // Hosted, reading the video in the browser comes first, so it is the first step.
  const stages = HOSTED ? ["read", ...task.stages] : task.stages;
  const index = stages.indexOf(task.stage);
  const share = index < 0 ? 0.04 : (index + 0.65) / stages.length;
  $("progress-bar").style.width = `${Math.round(share * 100)}%`;
  $("progress-message").textContent = task.message || "working";
  $("progress-elapsed").textContent = `${Math.round(task.elapsed)}s`;
  // A sequence with a number on each stop, so four words in a row read as four
  // steps of one journey rather than as four labels.
  $("steps").innerHTML = stages.map((stage, at) => {
    const state = at < index ? "done" : at === index ? "active" : "waiting";
    return `<li data-state="${state}" data-step="${at + 1}">${
      escapeHtml(HOSTED ? HOSTED.label(stage) : stage)}</li>`;
  }).join("");
}

/* ─────────────────────────  showing a clip  ───────────────────────── */

/* WhatsApp renamed two Status controls on 2026-08-20 and the tool found out at the
   moment a post was pressed, which is the worst moment: the clip was made and the
   caption was written. This asks the question earlier, once, the first time a clip
   becomes postable, and the server remembers the answer for the rest of the run.
   It is never on the poll: the check opens a menu in a window you may be looking
   at, and once a run is the most that is worth. T-026, and D-041 for the rename. */
let controlsFault = "";
let controlsAsked = false;

async function checkControlsOnce() {
  if (controlsAsked) return;
  controlsAsked = true;
  try {
    const answer = await api("/api/controls");
    controlsFault = answer.ok ? "" : (answer.detail || "a Status control has moved");
  } catch {
    // A check that cannot run is not a fault to report. Posting will say so itself.
    controlsFault = "";
  }
  refreshState();
}

function show(clip) {
  if (!clip || !clip.stem) return;
  current = clip;
  // This clip's own words are now what is on screen, so anything drawn over it is
  // out of date by definition.
  clearPreview();
  checkControlsOnce();

  const video = $("preview");
  if (clip.has_frame) video.poster = media("frame", clip.stem);
  else video.removeAttribute("poster");
  video.src = media("clip", clip.stem);
  video.load();
  unhide(video);
  unhide($("player"));
  hide($("empty"));
  resetPlayer();

  $("download").href = `${media("clip", clip.stem)}&download=1`;
  $("download").setAttribute("download", `${clip.stem}.mp4`);
  // The size belongs on the button that fetches it, not three lines away: on a
  // phone this is the number that decides whether now is a good moment.
  $("download-text").textContent = `Download ${clip.size_mb} MB`;
  disarmDelete();

  $("caption").textContent = clip.caption || "";
  echoCaption();
  unhide($("caption-band"));
  captionSaved("");

  $("result-name").textContent = clip.title || clip.name;
  $("result-mode").textContent = clip.video ? "video frames" : "artwork card";
  $("result-meta").textContent =
    [clip.window, `${clip.size_mb} MB`, when(clip.created)].filter(Boolean).join(" · ");
  hide($("post-done"));
  hide($("post-error"));
  hide($("nothing-yet"));
  unhide($("result"));
  paintSummaries();
  paintPostButtons();
}

/* Put a clip's own inputs back in the form, so the next press re-makes it with
   whatever you change. The words came from the sidecar, not from the filename. */
function recall(clip) {
  const job = clip && clip.job;
  if (!job || !job.url) return;
  $("url").value = job.url;
  $("start").value = clock(job.start);
  $("end").value = clock(job.end);
  $("duration").value = Math.round(job.end - job.start);
  windowEdit = "duration";
  $("title").value = job.title || "";
  $("channel").value = job.channel || "";
  $("footer").value = job.footer || "";
  $("eyebrow").value = job.eyebrow || "";
  $("topline").value = job.topline || "";
  // These words were derived for this video, not typed for the next one.
  wordsBelongTo(job.url);
  $("wave").checked = job.wave !== false;
  // The clip's own placement, **copied**, which is null for one that was fitted.
  // Held by reference, the first nudge would edit the clip's own record through it:
  // the page would then be comparing the placement against itself and could never
  // call the clip stale. The stickers are copied one by one for the same reason.
  // Placing stays on across a recall, so a run of takes can be nudged one after
  // another without turning it on again each time.
  //
  // Before `setMode`, not after: switching the mode re-asks the placement control,
  // and asking it while this still held the previous clip's placement would have it
  // answer about a rectangle belonging to another clip.
  framing = job.framing ? { ...job.framing } : (placing ? framingNow() : null);
  setMode(job.video ? "video" : "card");
  setFill(job.fill || "blur");
  setPlacing(framing ? "placed" : "fitted");
  markChips();
  paintClear();
  remember();
  decals = Array.isArray(job.stickers) ? job.stickers.map((one) => ({ ...one })) : [];
  picked = -1;
  decalsDirty = false;
  decalsEditing = false;
  paintDecals();
  // The boxes now hold this clip's own words, so there is nothing to preview.
  clearPreview();
  // And the undo slot held something that belonged to the clip before this one:
  // bringing it back here would drop a stranger onto another clip's frame.
  lastRemoved = null;
}

/* ───────────────────  the words, previewed as you type  ─────────────────── */

/* Changing a word on the card means making the clip again: the words are drawn
   into the pixels by ffmpeg, and there is no editing them afterwards. Measured on
   the owner's own runs, that is 30 seconds for a 30 second clip and 66 for a 90
   second one, of which the render alone is 17 and 53. Five goes at a title cost
   five minutes.

   None of that is needed to see the words. `build_card` and `build_overlay` are
   Pillow, they take 0.86 and 0.10 seconds, and the server keeps what each mode
   needs to draw over: the artwork for a card, one textless frame for a video. So
   the picture follows your typing and the file waits for the button. T-036.

   **What it shows is the words, not the finished frame.** A card clip has a
   waveform drawn under the title by ffmpeg from the audio, and a still cannot have
   one. The band it lives in is empty here. */

const PREVIEW_MS = 400;   // after typing stops. A card takes about twice that to draw
let previewTimer = null;
let previewSeq = 0;       // answers can arrive out of order; only the last one counts
let previewUrl = "";      // the object URL on show, revoked when it is replaced

/* The words as they are in the boxes right now. */
const wordsNow = () => ({
  title: $("title").value.trim(),
  channel: $("channel").value.trim(),
  footer: $("footer").value.trim(),
  eyebrow: $("eyebrow").value.trim(),
  topline: $("topline").value.trim(),
});

/* And the words the clip on screen was made with, so the two can be compared.
   The sidecar holds what was drawn, which is what has to be matched: an empty
   title box means "read it from the video", and the video's own answer is what
   ended up in the pixels. */
function wordsInClip() {
  const job = (current && current.job) || {};
  return {
    title: (job.title || "").trim(),
    channel: (job.channel || "").trim(),
    footer: (job.footer || "").trim(),
    eyebrow: (job.eyebrow || "").trim(),
    topline: (job.topline || "").trim(),
  };
}

function wordsDiffer() {
  if (!current || !current.stem) return false;
  const now = wordsNow();
  const was = wordsInClip();
  // An empty box is not a difference. It means the words come from the video, and
  // the video already answered that question when the clip was made.
  return ["title", "channel", "footer", "eyebrow", "topline"].some(
    (key) => now[key] && now[key] !== was[key]);
}

/* The background is drawn into the pixels the same way the words are, so it is
   previewed the same way. It only exists in video mode: a card composes its own.

   Showing one the clip was not made with means building the frame again out of the
   still that was kept, and that needs to know which pixels are the picture. Clips
   made before that was written down cannot be rebuilt, so the honest answer for
   those is a sentence rather than a picture identical to the one underneath.

   Card mode never reaches that sentence. It kept the artwork rather than a still,
   so the card is drawn again from scratch and there is nothing it cannot show; a
   card clip with no rectangle recorded cannot be placed in the first place, so
   there is no placement for this to have to refuse. See D-062. */
const rebuildable = () => !!(current && current.job && current.job.picture);

function fillDiffers() {
  if (!current || !current.stem || !current.video) return false;
  return fill !== ((current.job && current.job.fill) || "blur");
}

const aheadOfClip = () => wordsDiffer() || fillDiffers() || framingDiffers();

/* Called whenever a word or the background changes. Cheap, and it does nothing at
   all when there is no clip to draw on. */
function wordsChanged() {
  paintStale();
  clearTimeout(previewTimer);
  if (!aheadOfClip()) {
    clearPreview();
    return sayUndrawable();
  }
  $("wordshot").classList.add("working");
  previewTimer = setTimeout(drawPreview, PREVIEW_MS);
}

/* Some changes the preview cannot show, and staying silent about those was the
   page telling two stories about one clip: the Post it panel said the clip was out
   of date, and the pane it was next to showed the old frame with nothing to say.
   Reported on 2026-08-31, about a GIF. Stickers are drawn over the frame by the
   page rather than into the still, and the waveform is drawn by ffmpeg and moves,
   so neither can appear in a picture the server draws. Saying so is the whole fix:
   the pane is honest about what it is not showing. See D-077. */
const UNDRAWABLE = {
  "the stickers": "stickers",
  "the waveform": "the waveform",
  // Not "that": the sentence ends "Make the clip again to see that", and the two
  // together read as "cannot show that ... to see that".
  "the look": "the change of mode",
};

function sayUndrawable() {
  const note = $("wordshot-note");
  if (!current) return hide(note);
  const cannot = drifted().filter((what) => what in UNDRAWABLE);
  if (!cannot.length) return hide(note);
  const named = cannot.map((what) => UNDRAWABLE[what]);
  say(note, `The preview cannot show ${listed(named)}. `
      + "Make the clip again to see that.");
}

function clearPreview() {
  clearTimeout(previewTimer);
  previewSeq += 1;                    // anything still in flight is now stale
  const shot = $("wordshot");
  shot.classList.remove("working");
  hide(shot);
  hide($("wordshot-note"));
  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);  // or every keystroke leaks a JPEG
    previewUrl = "";
  }
}

/* The still covers the words and nothing else. Everything it redraws is text, and
   both layouts keep text off the part of the frame that moves, so cutting that part
   out of the still leaves the clip playing inside its own new wording: the old words
   are under the picture, the new ones are on it, and the footage runs between them.
   The server measured the band with the same functions the render used, so the hole
   cannot open onto a letter. A clip too old to have been measured gets no band and
   is covered whole, which is where this started. */
function cutOpen(shot, band) {
  const edges = String(band || "").split(",").map(Number);
  const cut = edges.length === 2 && edges.every(Number.isFinite)
      && edges[0] < edges[1]
    ? `linear-gradient(to bottom, #000 ${pc(edges[0])}, rgba(0,0,0,0) ${pc(edges[0])}`
      + ` ${pc(edges[1])}, #000 ${pc(edges[1])})`
    : "";
  shot.style.maskImage = cut;
  shot.style.webkitMaskImage = cut;  // Safari and every WebKit on iOS
}

const pc = (fraction) => `${(fraction * 100).toFixed(2)}%`;

async function drawPreview() {
  if (!aheadOfClip()) return clearPreview();
  if (!wordsDiffer() && (fillDiffers() || framingDiffers()) && !rebuildable()) {
    // Nothing to draw: the still would come back exactly as it went out, cover the
    // clip, and stop it moving for no reason anybody could see. The Post it panel
    // is already saying the background has changed; this says why it cannot show it.
    clearPreview();
    return say($("wordshot-note"),
               `This clip is older than the ${fillDiffers() ? "background" : "placement"}`
               + " choice. Make it again to see it.");
  }
  const mine = ++previewSeq;
  let answer;
  try {
    answer = await postForImage(
      "/api/preview", { stem: current.stem, fill, framing, ...wordsNow() });
  } catch (error) {
    if (mine !== previewSeq) return;  // a newer one is already on its way
    $("wordshot").classList.remove("working");
    // Not `fail`, and not `note`: the clip is fine and so is the tool, and this
    // band has a style of its own. A clip made before this existed has no picture
    // to draw on, which is worth saying once and quietly.
    say($("wordshot-note"), error.message);
    return;
  }
  if (mine !== previewSeq) return;
  const blob = await answer.blob();
  if (mine !== previewSeq) return;
  const shot = $("wordshot");
  const url = URL.createObjectURL(blob);
  cutOpen(shot, answer.headers.get("X-Moving-Band"));
  shot.src = url;
  shot.classList.remove("working");
  unhide(shot);
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = url;
  // What it is a preview of, so the band is not describing the wrong change.
  const named = mode === "video" ? "picture" : "artwork";
  // What the frame could not fit comes first: a line you typed and cannot see is
  // a more urgent thing to be told than which of your changes this is showing.
  // It used to be drawn as nothing, with the words still in the box and still in
  // the sidecar, so the page then reported the clip up to date with a line it had
  // never drawn. See D-075.
  const lost = Number(answer.headers.get("X-Dropped-Toplines") || 0);
  if (lost > 0) {
    return say($("wordshot-note"),
      `The text at the top does not fit: you have placed the ${named} too high `
      + "for it, so it is not drawn. Move it down to make room.");
  }
  say($("wordshot-note"),
      !wordsDiffer()
        ? (framingDiffers()
            ? `Preview of the ${named}. The clip still has the old one.`
            : "Preview of the background. The clip still has the old one.")
      : (fillDiffers() || framingDiffers()) && !rebuildable()
        ? "Preview of the words. The rest needs the clip made again to show."
        : "Preview of the words. The clip still has the old ones.");
}

function say(element, message) {
  element.textContent = message;
  unhide(element);
}

["title", "channel", "footer", "eyebrow", "topline"].forEach((id) => {
  $(id).addEventListener("input", wordsChanged);
});

/* ─────────────────────  the words the video already has  ─────────────────────

   The two boxes have always meant "leave me empty and the video will answer this
   when the clip is made". That answer only ever appeared in the pixels, so a title
   worth correcting was a title you found out about by making the clip, correcting
   it, and making it again. This asks the same question now: one yt-dlp probe, the
   same cleaning the card would have done, into the boxes, where they can be edited
   before anything is rendered. Asked for on 2026-08-27; see D-064.

   It replaces what is in the boxes, deliberately. The icon is a refresh and a press
   on it is not something a hand does on the way to anywhere else, and the fetched
   words are on the frame a moment later, so a wrong press is visible immediately. */

let fetchingWords = 0;   // a probe over a slow link outlives the link it was for

async function fetchWords() {
  const url = $("url").value.trim();
  const button = $("words-fetch");
  hide($("words-error"));
  if (!url) {
    openSection("words", true);
    fail($("words-error"), "Paste a YouTube link first, in the card above.");
    // The box has to be on screen before it can take the focus: inside a folded
    // card it is `display: none`, and `focus()` on that does nothing at all.
    openSection("clip", true);
    $("url").focus();
    return;
  }
  // Which video was asked about, not which string: `youtu.be/X` and `watch?v=X`
  // are one video, and an answer for it is still the right answer if the box has
  // been retyped into the other spelling while yt-dlp was talking to YouTube.
  const asked = videoKey(url);
  const mine = ++fetchingWords;
  button.dataset.working = "true";
  button.disabled = true;
  let words;
  try {
    words = HOSTED ? await HOSTED.words(url) : await post("/api/words", { url });
  } catch (error) {
    if (mine !== fetchingWords) return;      // a newer press is already in flight
    openSection("words", true);
    fail($("words-error"), error.message);
    return;
  } finally {
    // Only the press that is still the current one owns the button: an older one
    // finishing late must not stop the spinner a newer one started.
    if (mine === fetchingWords) {
      delete button.dataset.working;
      button.disabled = false;
    }
  }
  if (mine !== fetchingWords) return;
  if (videoKey($("url").value) !== asked) return;  // the link moved on; so did we
  $("title").value = words.title || "";
  $("channel").value = words.channel || "";
  // These words are this video's, which is what stops them being carried onto the
  // next one when the link changes.
  wordsBelongTo($("url").value);
  openSection("words", true);
  remember();       // the boxes were filled by hand here, not by a `input` event
  wordsChanged();   // so the frame above shows them, the same as typing would
}

$("words-fetch").addEventListener("click", (event) => {
  // Inside a <summary>, so without this the card folds as the press lands.
  event.preventDefault();
  event.stopPropagation();
  fetchWords();
});

/* ─────────────────────────  the caption  ───────────────────────── */

/* One caption, edited in one labelled box, shown in two places: the box, and an
   echo drawn over the frame where WhatsApp will draw it. Before this the only
   editable copy was the one over the frame, under a bar labelled "Caption" that
   sat above the song title, and it was not obvious which text was which. */

/* A contenteditable inserts non-breaking spaces as you type at an edge, and
   they look identical to real ones. Fold them, and any run of blank lines. */
const captionText = () =>
  $("caption").innerText.replace(/\u00a0/g, " ").replace(/\n{3,}/g, "\n\n").trim();

function echoCaption() {
  $("caption-echo").textContent = captionText();
}

$("caption").addEventListener("input", () => {
  echoCaption();
  captionSaved("editing", true);
  clearTimeout(captionTimer);
  captionTimer = setTimeout(saveCaption, CAPTION_SAVE_MS);
});

$("caption").addEventListener("blur", () => {
  clearTimeout(captionTimer);
  saveCaption();
});

/* Firefox before 136 has no plaintext-only, and a pasted link would arrive as
   markup. Paste as text everywhere and the editor stays a caption. */
$("caption").addEventListener("paste", (event) => {
  event.preventDefault();
  const text = (event.clipboardData || window.clipboardData).getData("text");
  document.execCommand("insertText", false, text.replace(/\s*\n\s*/g, "\n"));
});

async function saveCaption() {
  if (!current) return true;
  const text = captionText();
  if (text === (current.caption || "")) return true;
  try {
    const saved = await post("/api/caption", { stem: current.stem, caption: text });
    current.caption = saved.caption;
    captionSaved("saved");
    return true;
  } catch (error) {
    captionSaved(error.message, true);
    return false;
  }
}

function captionSaved(message, warn = false) {
  const state = $("caption-state");
  state.textContent = message;
  state.classList.toggle("caption__state--warn", warn);
}

/* `navigator.clipboard` exists only in a secure context, and the address the phone
   opens this page on is plain http, so on the phone it is not there at all. The old
   code caught that and set a `title`, which a phone has no way to show: the button
   did nothing, silently, on the one device where copying the caption matters most.
   `execCommand` is deprecated and works everywhere, including here. */
async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch { /* fall through to the old way */ }
  }
  const holder = document.createElement("textarea");
  holder.value = text;
  holder.setAttribute("readonly", "");
  holder.style.cssText = "position:fixed;top:0;left:0;opacity:0;pointer-events:none";
  document.body.appendChild(holder);
  holder.select();
  holder.setSelectionRange(0, text.length);   // iOS needs the range as well
  let done = false;
  try { done = document.execCommand("copy"); } catch { done = false; }
  holder.remove();
  return done;
}

$("copy").addEventListener("click", async () => {
  const text = captionText();
  if (!text) return;
  if (!await copyText(text)) {
    fail($("post-error"), "Copying is blocked here. Select the caption and copy it.");
    return;
  }
  // An icon cannot say "Copied", so it becomes a tick for a moment.
  hide($("copy-icon"));
  unhide($("copy-done"));
  setTimeout(() => { unhide($("copy-icon")); hide($("copy-done")); }, 1400);
});

/* ─────────────────────────  the player  ───────────────────────── */

/* Native controls would sit exactly where WhatsApp draws its caption, and the
   point of this frame is to look like what the viewer gets. So: our own. */

const video = $("preview");

$("play").addEventListener("click", () => {
  if (video.paused) video.play(); else video.pause();
});

video.addEventListener("play", () => playing(true));
video.addEventListener("pause", () => playing(false));
video.addEventListener("ended", () => { playing(false); video.currentTime = 0; });
video.addEventListener("loadedmetadata", () => {
  $("seek").max = Number.isFinite(video.duration) ? video.duration : 100;
  paintTime();
});
video.addEventListener("timeupdate", () => {
  if (!seeking) $("seek").value = video.currentTime;
  paintTime();
});

let seeking = false;
$("seek").addEventListener("pointerdown", () => { seeking = true; });
$("seek").addEventListener("input", () => {
  video.currentTime = Number($("seek").value);
  paintTime();
});
$("seek").addEventListener("change", () => { seeking = false; });

function playing(on) {
  // `hidden` is a property of HTMLElement, and these two are SVG elements, so
  // `svg.hidden = true` sets a JavaScript property that no stylesheet can see.
  // The attribute is the only thing that works on both. It cost the play icon: it
  // never became a pause icon, on any device.
  (on ? hide : unhide)($("icon-play"));
  (on ? unhide : hide)($("icon-pause"));
  $("play").setAttribute("aria-label", on ? "Pause" : "Play");
  // Nothing to do for the words. The still is cut open over the part of the frame
  // that moves, so the clip plays inside it and the wording no longer changes
  // between stopped and playing. It used to be hidden here, which is what made
  // pressing play swap the title back. See `cutOpen` and TASKS.md T-036.
}

function paintTime() {
  const total = Number.isFinite(video.duration) ? video.duration : 0;
  $("time").textContent = `${clock(video.currentTime)} / ${clock(total)}`;
}

function resetPlayer() {
  playing(false);
  $("seek").value = 0;
  $("time").textContent = "0:00 / 0:00";
}

/* ─────────────────────────  stickers  ───────────────────────── */

/* Everything here works in fractions of the frame, and the frame is a 9:16 box, so
   a sticker's left, top and width go straight into CSS percentages and straight
   into the render request with no conversion in between. That is the whole reason
   a sticker can be dragged in the browser while the card's wording cannot: there
   is no layout to reimplement, only a rectangle to place. See D-021 and D-024. */

/* `width` asks the server for a scaled copy. The shelf uses it: 40 drawings cost
   402 kB at full size and 191 kB at 96, measured 2026-08-19. Placed stickers ask for
   the full drawing, because there are a handful of them and they are drawn large. */
const stickerImage = (id, width = 0) =>
  `/api/sticker?id=${encodeURIComponent(id)}&t=${encodeURIComponent(TOKEN)}` +
  (width ? `&w=${width}` : "");

/* ── free text ──────────────────────────────────────────────────────────────
   A placed line is a picture of that line, drawn by the server in the same Pillow
   the renderer uses. The page never sets the words itself: it would break the line
   somewhere else and kern it differently, and the box you dragged would then not be
   the pixels ffmpeg burns in. Type, ask for a picture, place the picture. That is
   the same bargain stickers make, and it is why either can be dragged at all: to
   this layer both are a rectangle. See wastatus/freetext.py, D-021 and D-024. */

const textShots = new Map();   // the words -> an object URL of their picture
const TEXT_SHOTS_MAX = 40;     // a line being typed makes one picture per keystroke

async function textImage(words) {
  const held = textShots.get(words);
  if (held) return held;
  const answer = await postForImage("/api/text", { text: words });
  const url = URL.createObjectURL(await answer.blob());
  if (textShots.size >= TEXT_SHOTS_MAX) {
    // The oldest words that are not on the frame. Revoking a picture that a box is
    // still showing would empty it, and the drafts on the way to a line are exactly
    // what fills this: every keystroke leaves one behind.
    const placed = new Set(decals.filter(isText).map((one) => one.text));
    const spare = [...textShots.keys()].find((words) => !placed.has(words));
    if (spare !== undefined) {
      URL.revokeObjectURL(textShots.get(spare));
      textShots.delete(spare);
    }
  }
  textShots.set(words, url);
  return url;
}

/* The picture arrives after the box does, so how tall the line is, and whether
   WhatsApp is about to draw over it, are settled when it lands rather than guessed
   before it. A line nobody can draw leaves an empty box and no banner: the words
   that made it are still in the box that made them, which is where a correction
   goes. */
function dressText(art, decal, at) {
  art.alt = decal.text;
  art.addEventListener("load", () => {
    decal.aspect = art.naturalHeight / art.naturalWidth || 1;
    placeDecal(at);
  });
  textImage(decal.text).then((url) => { art.src = url; }).catch(() => {});
}

const isText = (decal) => !!decal && decal.kind === "text";

/* Rebuild the layer. Only when the set of stickers changes: rebuilding it while a
   sticker is being dragged destroys the element holding the pointer capture, and
   rebuilding it on every slider step refetches every image. */
function paintDecals() {
  const layer = $("decals");
  layer.hidden = !(decalsDirty || decalsEditing || !current) || !decals.length;
  paintSummaries();
  paintStickerEdit();

  layer.replaceChildren(...decals.map((decal, at) => {
    // A box rather than the drawing itself, because the drawing cannot hold the
    // handles. The box takes its height from the picture inside it, so a sticker
    // that is not square is still boxed exactly, and it carries the rotation, so
    // the handles turn with the sticker the way every design tool turns them.
    const box = document.createElement("div");
    // The kind is on the class rather than in a `data-` attribute because the
    // stylesheet is the only thing that asks: it offers the pencil on a line of
    // words and on nothing else.
    box.className = isText(decal) ? "decal decal--text" : "decal";
    box.dataset.at = String(at);
    // A tab stop, so a hand that never touches the mouse can still reach one, and
    // a name, so what it reaches is not called "group". Focus and selection are the
    // same thing here: tabbing to a box is how a keyboard picks it up.
    box.tabIndex = 0;
    // No role: a box you drag is not a button, and promising a button's Enter and
    // Space would be promising something this does not do.
    box.setAttribute("aria-label",
      isText(decal) ? `Free text: ${decal.text}` : "Sticker");
    box.addEventListener("focus", () => { if (picked !== at) select(at); });

    const art = new Image();
    art.className = "decal__art";
    art.draggable = false;
    art.alt = "";
    if (isText(decal)) dressText(art, decal, at);
    else art.src = stickerImage(decal.id);
    box.append(art, ...handles(decal));
    return box;
  }));
  decals.forEach((_, at) => placeDecal(at));
  paintPicked();
}

/* The three controls that ride on the box. Every sticker carries all three; CSS
   shows them only on the selected one, and shows resize and rotate only where
   there is a mouse. See D-038 for why the phone gets the cross and nothing else:
   a default sticker is 76 pixels to hit and two touch targets need 88 between
   them, so two handles do not fit on it and one has to be chosen. */
function handles(decal) {
  // The pencil is free text's alone: there is nothing to retype about a drawing,
  // and a fourth circle on a sticker would be a fourth thing in the way of it.
  const jobs = ["delete", "resize", "rotate"];
  if (isText(decal)) jobs.push("edit");
  return jobs.map((job) => {
    const handle = document.createElement("button");
    handle.type = "button";
    handle.className = `decal__handle decal__handle--${job}`;
    handle.dataset.handle = job;
    handle.tabIndex = -1;   // reached by pointer; the sliders are the keyboard route
    handle.setAttribute("aria-label",
      job === "delete" ? "Remove this sticker"
      : job === "resize" ? "Resize this sticker"
      : job === "edit" ? "Edit these words" : "Turn this sticker");
    return handle;
  });
}

/* One sticker's position, size, angle and outline, written straight onto the
   element. Percentages of the frame, which is what the renderer is sent. */
function placeDecal(at) {
  const image = $("decals").children[at];
  const decal = decals[at];
  if (!image || !decal) return;
  image.style.left = `${decal.x * 100}%`;
  image.style.top = `${decal.y * 100}%`;
  image.style.width = `${decal.size * 100}%`;
  image.style.transform = `translate(-50%, -50%) rotate(${decal.rotation}deg)`;
  image.dataset.picked = String(at === picked);
  image.dataset.covered = String(covered(decal));
}

/* The dashed box says which sticker the handles and the sliders belong to, and it
   stays until you choose otherwise. It used to fade 1.4 seconds after your hand
   left it, D-034, and that was right while the box was only a hint. It carries
   controls now, and a handle that fades is a handle you cannot click, so one state
   became two: **selected**, which persists, and **nothing selected**, which is the
   resting frame D-034 was written to protect. Tapping the background is what gets
   you back to it. See D-038, and the amendment at the foot of D-034.

   The orange covered box is not this: it is a warning, and it is on every sticker
   that earns it, selected or not. */

function select(at) {
  picked = decals[at] ? at : -1;
  if (picked !== -1 && pickedPicture) {
    // The frame holds one selection, not two: the keys have to have one answer.
    pickedPicture = false;
    paintPictureBox();
  }
  repaintPicked();
}

function deselect() {
  if (pickedPicture) {
    pickedPicture = false;
    paintPictureBox();
    paintStickerHint();
  }
  if (picked === -1) return;
  picked = -1;
  repaintPicked();
}

/* Only the outline changes, so no element is replaced: rebuilding the layer during
   a gesture would destroy the element holding the pointer capture. */
function repaintPicked() {
  const children = $("decals").children;
  decals.forEach((_, at) => {
    if (children[at]) children[at].dataset.picked = String(at === picked);
  });
  paintPicked();
}

function paintPicked() {
  const one = decals[picked];
  $("picked").hidden = !one;
  const forget = $("sticker-forget");
  const own = !!one && /^(mine|gif):/.test(String(one.id || ""));
  forget.hidden = !own;
  if (forget.dataset.for !== String(one && one.id)) {
    // Another sticker picked: the second press has to be asked for again.
    delete forget.dataset.armed;
    forget.textContent = "Delete from my stickers";
    forget.dataset.for = String(one && one.id);
  }
  if (one) {
    $("sticker-size").value = Math.round(one.size * 100);
    $("sticker-turn").value = Math.round(one.rotation);
  }
  // Selecting a line puts its words back in the box that writes them. Only when
  // they differ, or every repaint during typing would rewrite the box under the
  // cursor and send it to the end.
  if (isText(one) && $("text-line").value !== one.text) $("text-line").value = one.text;
  paintStickerHint();
  // A repaint that arrives while a line is being retyped on the frame closes the
  // editor with it: the element it lived in has been replaced.
  if (inlineAt >= 0 && !inlineBox()) inlineAt = -1;
}

/* What the pencil does: open a real input over the line, on the frame, where the
   line is. D-063 argued for one box and no second editor, and the box is still
   the one that inserts a line and still writes every keystroke; what it got wrong
   is that retyping a line you can see on the frame sends your eye and your hand
   somewhere else on the page to do it. Both are live now, and they are the same
   string: typing in either writes the decal and repaints the other. See D-076.

   The drawing is a PNG, so it cannot be typed into. The input is laid over it
   inside the same box, which is what makes it carry the box's rotation and move
   with it, and the drawing is hidden while it is open so the words are not on the
   frame twice. It comes back, redrawn, the moment editing stops. */
let inlineAt = -1;   // which decal is being typed on the frame, or -1

function inlineBox() {
  return $("decals").querySelector(".decal__edit");
}

/* Both boxes and the decal hold one string. `from` is whichever box the keystroke
   landed in, and is the one thing not written back: rewriting the box under the
   cursor sends the caret to the end of it. */
function applyText(value, from) {
  const one = decals[picked];
  if (!isText(one)) return;
  one.text = value;
  if (from !== "field" && $("text-line").value !== value) {
    $("text-line").value = value;
  }
  const inline = inlineBox();
  if (from !== "inline" && inline && inline.value !== value) inline.value = value;
  const box = inline && inline.closest(".decal");
  if (box) box.setAttribute("aria-label", `Free text: ${value}`);
  clearTimeout(textTimer);
  textTimer = setTimeout(() => {
    if (decals[picked] === one && one.text.trim()) changed();
  }, TEXT_MS);
}

function editText(at) {
  const one = decals[at];
  if (!isText(one)) return;
  if (picked !== at) select(at);
  // Closed first, and quietly: closing normally redraws the line, which rebuilds
  // the whole layer and would leave the box found below detached from the page.
  closeInline(true);
  const box = $("decals").querySelector(`.decal[data-at="${at}"]`);
  if (!box) return openTextField(one);   // the layer is folded away: fall back
  const input = document.createElement("input");
  input.type = "text";
  input.className = "decal__edit";
  input.maxLength = 120;
  input.autocomplete = "off";
  input.setAttribute("aria-label", "Edit these words on the frame");
  input.value = one.text;
  // Sized off the box the drawing occupies, so the typed line is about the size of
  // the drawn one. The two fonts are not the same and this is not trying to be a
  // preview: the drawing itself is what comes back when you stop.
  const art = box.querySelector(".decal__art");
  const tall = (art && art.getBoundingClientRect().height) || box.clientHeight;
  if (tall) input.style.fontSize = `${Math.max(9, tall * 0.72)}px`;
  input.addEventListener("input", () => applyText(input.value, "inline"));
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeInline();
    }
  });
  // Dragging the box would otherwise start the moment the caret is placed.
  ["pointerdown", "pointermove", "pointerup"].forEach((kind) => {
    input.addEventListener(kind, (event) => event.stopPropagation());
  });
  input.addEventListener("blur", closeInline);
  box.classList.add("decal--editing");
  box.append(input);
  inlineAt = at;
  requestAnimationFrame(() => {
    input.focus({ preventScroll: true });
    input.select();
  });
}

/* Put the drawing back and redraw it. Safe to call when nothing is open.

   `quiet` skips the redraw, for the one caller that is about to open another
   editor and needs the layer to stay exactly as it is while it does. */
function closeInline(quiet) {
  const input = inlineBox();
  inlineAt = -1;
  if (!input) return;
  const box = input.closest(".decal");
  input.remove();
  if (box) box.classList.remove("decal--editing");
  if (quiet) return;
  const one = decals[picked];
  if (isText(one) && !one.text.trim()) return;   // an emptied line is left alone
  changed();
}

/* The old route, kept for the case the frame cannot offer: the decal layer is
   hidden once a clip has been made, and there is then nothing on screen to type
   into. Opens the section and selects what is in the box. */
function openTextField(one) {
  const section = $("sec-extras");
  if (section && !section.open) {
    section.open = true;
    rememberOpen();
  }
  const box = $("text-line");
  box.value = one.text;
  requestAnimationFrame(() => {
    box.focus({ preventScroll: true });
    box.select();
    box.scrollIntoView({ block: "center", behavior: "smooth" });
  });
}

const TEXT_MS = 300;   // after typing stops, before the picture is asked for
let textTimer = null;

/* One box, two jobs. With a line selected it retypes that line; with anything else
   selected, or nothing, Insert puts a new one in the middle of the frame. That is
   the same box people reach for either way, and it is why there is no separate
   "edit" mode to be in or out of. */
function insertText() {
  const words = $("text-line").value.trim();
  if (!words) return $("text-line").focus();
  decals.push({ kind: "text", text: words, x: 0.5, y: 0.45, size: 0.6, rotation: 0 });
  picked = decals.length - 1;
  changed();
  $("text-line").focus();
}

$("text-add").addEventListener("click", insertText);

$("text-line").addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  // This box is inside the form, so Enter would otherwise make the clip.
  event.preventDefault();
  insertText();
});

$("text-line").addEventListener("input", () => {
  // The untrimmed value, so both boxes and the line hold the same string and the
  // repaint never writes over what is being typed. `applyText` is what keeps the
  // one on the frame in step, when one is open.
  applyText($("text-line").value, "field");
});

/* A sticker is square, so its height in frame fractions is its width times 9/16. */
/* `aspect` is height over width, and it is 1 until a picture says otherwise, which
   is what a drawing is. A line of words is a great deal wider than it is tall, and
   calling it square warned about text that was nowhere near the band. */
function covered(decal) {
  const half = (decal.size * 9 / 16) * (decal.aspect || 1) / 2;
  return decal.y - half < bands.top || decal.y + half > 1 - bands.bottom;
}

/* The way back to the handles after a clip has been made, and the only place that
   decides whether it is offered: there are stickers, they are already in the clip
   on show, and nothing has been touched since. */
function paintStickerEdit() {
  $("sticker-edit").hidden =
    !(current && decals.length && !decalsDirty && !decalsEditing);
}

function paintStickerHint() {
  const hidden = decals.filter(covered).length;
  const parts = [];
  paintStickerEdit();
  if (decalsDirty && decals.length) {
    parts.push("Make the clip again to draw these into it.");
  } else if (decalsEditing && decals.length) {
    // The handles are back but nothing has moved yet, so the clip below is not
    // behind anything and saying it is would be the page inventing a change.
    parts.push("Move them, then make the clip again.");
  } else if (!decals.length) {
    parts.push("Pick one, then drag it on the frame.");
  } else if (current) {
    // They are pixels now, exactly like the words. Saying so is the answer to
    // "why can I not drag these any more", which is otherwise a silent no.
    parts.push("These are drawn into the clip below now, the way the words are.");
  }
  if (hidden) {
    parts.push(hidden === 1
      ? "One sits where WhatsApp draws its own header or caption."
      : `${hidden} sit where WhatsApp draws its own header or caption.`);
  }
  // Only where there is a keyboard to press. A phone reads this too, and telling a
  // phone about arrow keys is telling it about somebody else's machine.
  if (decals[picked] && HAS_KEYS) {
    parts.push("Arrows nudge it, + and − size it, [ and ] turn it, "
             + "Delete removes it. Hold Shift to go further, ⌘Z to bring it back.");
  } else if (pickedPicture && HAS_KEYS) {
    parts.push("Arrows nudge the picture, + and − size it. Hold Shift to go "
             + "further, Escape to put it down.");
  }
  $("sticker-hint").textContent = parts.join(" ");
}

/* The set changed: rebuild, and say the clip below is now behind. */
function changed() {
  decalsDirty = true;
  paintDecals();
  // A sticker is a change to the clip like any other, and the preview pane has to
  // account for it even though it cannot draw it. Without this the Post it panel
  // warned and the pane beside it said nothing. See D-077.
  wordsChanged();
}

/* One sticker moved or was resized: touch that element only. */
function adjusted(at) {
  decalsDirty = true;
  placeDecal(at);
  paintPicked();
  $("decals").hidden = false;
}

/* -- moving, sizing and turning one with your fingers -- */

/* One finger drags. Two fingers pinch to size and twist to turn, and the pair also
   carries the sticker along with its own midpoint, which is what makes a gesture
   feel like holding a piece of paper rather than driving three separate controls.

   The listeners are on the frame, not on the sticker, and only the **first** finger
   has to land on the sticker. A sticker at its default size is a fifth of a 300
   pixel frame, about 60 pixels, and two fingertips do not fit inside that. So the
   second finger may land anywhere on the frame and still belong to the gesture.

   The sliders below the shelf do the same two jobs for a mouse, and they stay: a
   laptop has no second finger, and they are also how you set an exact number. */

const MIN_SIZE = 0.03;
const MAX_SIZE = 0.9;      // the sliders stop here, and so does this
const SNAP_DEGREES = 4;    // close enough to square that you meant square

let gesture = null;

const frameBox = () => $("decals").getBoundingClientRect();

/* Where a pointer is, as a fraction of the frame: the same units the renderer is
   sent, so nothing is converted between here and the paste. */
function fraction(box, point) {
  return {
    x: (point.clientX - box.left) / box.width,
    y: (point.clientY - box.top) / box.height,
  };
}

const clamp = (value, low, high) => Math.min(Math.max(value, low), high);

/* Turning is measured in pixels, not fractions: the frame is 9:16, so an angle
   computed in fractions of it would be sheared and a straight twist would wobble. */
const spread = (a, b) => Math.hypot(b.clientX - a.clientX, b.clientY - a.clientY);
const twist = (a, b) =>
  Math.atan2(b.clientY - a.clientY, b.clientX - a.clientX) * 180 / Math.PI;

/* Square is a place people aim for and miss by a degree or two. Nothing else is
   snapped, so a deliberate 37 degrees stays 37 degrees. */
function settle(degrees) {
  let turned = ((degrees + 180) % 360 + 360) % 360 - 180;
  for (const mark of [-180, -90, 0, 90, 180]) {
    if (Math.abs(turned - mark) <= SNAP_DEGREES) turned = mark;
  }
  return Math.round(turned);
}

function onFramePointerDown(event) {
  const reach = event.target.closest ? event.target : null;
  // A handle is inside the box it belongs to, so it would otherwise read as a grab
  // on the sticker. It runs its own drag, below, and this one keeps out of the way.
  if (reach && reach.closest(".decal__handle")) return;
  const image = reach && reach.closest(".decal");

  if (!gesture) {
    // The first finger has to be on a sticker, or this is not a gesture at all and
    // the frame keeps its ordinary behaviour, including scrolling the page.
    // Landing on the background is also how you put a selection down.
    if (!image) return deselect();
    const at = Number(image.dataset.at);
    if (!decals[at]) return;
    gesture = { at, points: new Map(), anchor: null };
    select(at);
    // The press below is prevented, and a prevented press does not move focus. The
    // keys and the hand have to end up on the same sticker, so this says it.
    image.focus({ preventScroll: true });
    decals.forEach((_, index) => placeDecal(index));
    // While two fingers are on the frame, the browser must not treat them as a
    // page zoom. The sticker itself already says `touch-action: none`; this says it
    // for the space around it, and only for as long as the gesture lasts.
    $("screen").classList.add("gesturing");
  } else if (gesture.points.size >= 2) {
    return;   // two is a gesture, three is a lap
  }

  gesture.points.set(event.pointerId, event);
  $("screen").setPointerCapture(event.pointerId);
  anchorGesture();
  event.preventDefault();
}

/* Everything a move is measured against, recorded whenever the number of fingers
   changes. Without re-anchoring, lifting one finger of two makes the sticker jump. */
function anchorGesture() {
  const decal = decals[gesture.at];
  if (!decal) return;
  const box = frameBox();
  const points = [...gesture.points.values()];

  if (points.length === 1) {
    const held = fraction(box, points[0]);
    gesture.anchor = {
      kind: "one",
      grabX: decal.x - held.x,
      grabY: decal.y - held.y,
    };
    return;
  }
  const [a, b] = points;
  const middle = fraction(box, {
    clientX: (a.clientX + b.clientX) / 2,
    clientY: (a.clientY + b.clientY) / 2,
  });
  gesture.anchor = {
    kind: "two",
    spread: spread(a, b) || 1,
    twist: twist(a, b),
    middle,
    size: decal.size,
    rotation: decal.rotation,
    x: decal.x,
    y: decal.y,
  };
}

function onFramePointerMove(event) {
  if (!gesture || !gesture.points.has(event.pointerId)) return;
  gesture.points.set(event.pointerId, event);
  const decal = decals[gesture.at];
  const anchor = gesture.anchor;
  if (!decal || !anchor) return;
  const box = frameBox();
  const points = [...gesture.points.values()];

  if (anchor.kind === "one") {
    const held = fraction(box, points[0]);
    decal.x = clamp(held.x + anchor.grabX, -0.25, 1.25);
    decal.y = clamp(held.y + anchor.grabY, -0.25, 1.25);
  } else {
    const [a, b] = points;
    const middle = fraction(box, {
      clientX: (a.clientX + b.clientX) / 2,
      clientY: (a.clientY + b.clientY) / 2,
    });
    decal.size = clamp(anchor.size * (spread(a, b) / anchor.spread), MIN_SIZE, MAX_SIZE);
    decal.rotation = settle(anchor.rotation + (twist(a, b) - anchor.twist));
    decal.x = clamp(anchor.x + (middle.x - anchor.middle.x), -0.25, 1.25);
    decal.y = clamp(anchor.y + (middle.y - anchor.middle.y), -0.25, 1.25);
  }
  placeDecal(gesture.at);
  // The sliders are the same two numbers, so they follow the fingers.
  paintPicked();
  event.preventDefault();
}

function onFramePointerUp(event) {
  if (!gesture || !gesture.points.has(event.pointerId)) return;
  gesture.points.delete(event.pointerId);
  try { $("screen").releasePointerCapture(event.pointerId); } catch { /* already gone */ }

  if (gesture.points.size) {
    anchorGesture();   // one finger left: carry on dragging from where it is now
    return;
  }
  const at = gesture.at;
  gesture = null;
  $("screen").classList.remove("gesturing");
  adjusted(at);
  // Nothing to start: the selection this gesture made stays until you put it down.
}

/* -- the handles on the box -- */

/* Resize and rotate are measured from the sticker's centre, not from the corner the
   grip sits in. The centre of a rotated box is the one point its bounding rectangle
   still reports truthfully, so both work at any angle with no trigonometry to undo
   the rotation first. Size is the ratio of two distances and rotation is the
   difference of two angles, which means neither one jumps when you grab it. */

let handling = null;

const centreOf = (box) => {
  const rect = box.getBoundingClientRect();
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
};
const reach = (from, event) => Math.hypot(event.clientX - from.x, event.clientY - from.y);
const bearing = (from, event) =>
  Math.atan2(event.clientY - from.y, event.clientX - from.x) * 180 / Math.PI;

function onHandleDown(event) {
  const handle = event.target.closest && event.target.closest(".decal__handle");
  if (!handle) return;
  const box = handle.closest(".decal");
  const at = Number(box.dataset.at);
  const decal = decals[at];
  if (!decal) return;

  // Whatever it is, it is not a drag of the sticker and not a press on the frame.
  event.preventDefault();
  event.stopPropagation();
  select(at);
  box.focus({ preventScroll: true });

  if (handle.dataset.handle === "edit") {
    editText(at);
    return;
  }

  if (handle.dataset.handle === "delete") {
    // No confirmation, on purpose: a sticker is one tap to put back from the shelf,
    // unlike a clip, which is why that one asks twice. See D-038. It goes through
    // the same one slot undo the Delete key uses, so ⌘Z brings back either.
    removeDecal(at);
    return;
  }

  const centre = centreOf(box);
  handling = {
    at,
    job: handle.dataset.handle,
    centre,
    reach: reach(centre, event) || 1,
    bearing: bearing(centre, event),
    size: decal.size,
    rotation: decal.rotation,
  };
  // Which cursor the frame wears until the hand comes off. The pointer leaves the
  // handle within a few pixels of the press, and without this it would go back to
  // the box's grab hand halfway through a resize.
  $("screen").dataset.gesture = handling.job;
  // A pointer can be gone by the time this runs, and capturing a dead one throws.
  try { handle.setPointerCapture(event.pointerId); } catch { /* nothing to hold */ }
  handle.addEventListener("pointermove", onHandleMove);
  handle.addEventListener("pointerup", onHandleUp);
  handle.addEventListener("pointercancel", onHandleUp);
}

function onHandleMove(event) {
  if (!handling) return;
  const decal = decals[handling.at];
  if (!decal) return;
  if (handling.job === "resize") {
    decal.size = clamp(
      handling.size * (reach(handling.centre, event) / handling.reach),
      MIN_SIZE, MAX_SIZE);
  } else {
    // The same `settle` the two finger twist uses, so square is square by either
    // route and a deliberate 37 degrees stays 37 by either route too.
    decal.rotation = settle(
      handling.rotation + (bearing(handling.centre, event) - handling.bearing));
  }
  adjusted(handling.at);
  event.preventDefault();
}

function onHandleUp(event) {
  const handle = event.currentTarget;
  handle.removeEventListener("pointermove", onHandleMove);
  handle.removeEventListener("pointerup", onHandleUp);
  handle.removeEventListener("pointercancel", onHandleUp);
  try { handle.releasePointerCapture(event.pointerId); } catch { /* already gone */ }
  delete $("screen").dataset.gesture;
  handling = null;
}

/* ─────────────────────  placing the picture itself  ─────────────────────

   The picture is the one thing on the frame that was always placed for you: the
   frames are fitted into whatever band the words leave. Placing it by hand makes it
   the same kind of object as everything else here, a rectangle at a fraction of the
   frame, which is why it needs no new units and no new arithmetic. See D-061.

   Two things it is not. It is not a `.decal`: the sticker gestures find their
   target with `closest(".decal")`, and the picture must never answer to those. And
   it is not previewed while it moves: the picture lives under the words, so seeing
   it move means the server rebuilding the frame, which happens when you let go. The
   box is the truth in the meantime, and it is exact. */

const FRAME_ASPECT = 9 / 16;          // the frame's own shape, as the stylesheet has it
const PICTURE_MIN = 0.05, PICTURE_MAX = 3;

/* The shape of the source, read off the rectangle the clip recorded: that picture
   is the source scaled, so its proportions are the source's. 1 until a clip says
   otherwise, which only shows while there is nothing to place. */
function pictureAspect() {
  const rect = current && current.job && current.job.picture;
  return rect && rect.width ? rect.height / rect.width : 1;
}

/* What the clip on screen is placed at, whether or not anybody placed it. Switching
   to Placed starts here, so the box appears exactly where the picture already is. */
function framingNow() {
  const job = current && current.job;
  // What was asked for, when anything was: reading it back off the rectangle
  // instead costs a pixel of rounding, and a pixel is enough to call a clip stale
  // for a placement nobody has touched.
  if (job && job.framing) return { ...job.framing };
  const rect = job && job.picture;
  if (!rect) return null;
  return {
    x: (rect.left + rect.width / 2) / 1080,
    y: (rect.top + rect.height / 2) / 1920,
    size: rect.width / 1080,
  };
}

/* Is the clip on screen the kind this mode makes? A placement belongs to one shape
   of picture, and the video's frames and the artwork panel are not the same shape:
   reading one clip's rectangle while the other mode is chosen would draw the box
   around something that is not there. */
const sameKind = () => !!(current && current.stem
                          && (mode === "video") === !!current.video);

const placeable = () => !!(sameKind() && current.job && current.job.picture);

function framingDiffers() {
  if (!sameKind()) return false;
  const was = current.job && current.job.framing;
  if (!framing) return !!was;
  if (!was) {
    // Fitted, and now placed: a placement that resolves to where it already is is
    // not a change, and switching the control on and off must not make the clip
    // stale. Five decimals is what the sidecar keeps.
    const at = framingNow();
    return !at || ["x", "y", "size"].some(
      (key) => Math.abs(framing[key] - at[key]) > 1e-4);
  }
  return ["x", "y", "size"].some((key) => Math.abs(framing[key] - was[key]) > 1e-5);
}

/* The box, written straight onto the element as percentages of the frame, the same
   way a sticker's box is. The height is not a choice: it follows the source. */
function paintPictureBox() {
  const box = $("picture-box");
  box.hidden = !(placing && framing);
  if (box.hidden) return;
  const height = framing.size * pictureAspect() * FRAME_ASPECT;
  box.style.left = `${(framing.x - framing.size / 2) * 100}%`;
  box.style.top = `${(framing.y - height / 2) * 100}%`;
  box.style.width = `${framing.size * 100}%`;
  box.style.height = `${height * 100}%`;
  box.dataset.picked = String(pickedPicture);
}

function selectPicture() {
  if (!placing || pickedPicture) return;
  deselect();                       // one selection on the frame, not two
  pickedPicture = true;
  paintPictureBox();
  paintStickerHint();
}

function setPlacing(next) {
  const want = next === "placed" && placeable();
  placing = want;
  if (want && !framing) framing = framingNow();
  // The control is in Look and the box it turns on is down in the preview. With
  // that section folded, pressing Placed looked like it did nothing at all: the box
  // was there, inside a closed `details`, which is `display: none` and cannot even
  // be focused. The pencil opens the section its box lives in for the same reason.
  if (want) {
    const shown = $("sec-preview");
    if (shown && !shown.open) {
      shown.open = true;
      rememberOpen();
    }
  }
  if (!want) {
    framing = null;
    pickedPicture = false;
  }
  document.querySelectorAll(".segmented__option[data-picture]").forEach((option) =>
    option.setAttribute("aria-checked", String((option.dataset.picture === "placed")
                                               === want)));
  $("picture-placed").disabled = !placeable();
  const named = mode === "video" ? "picture" : "artwork";
  $("picture-hint").textContent = !placeable()
    // Three ways to have nothing to place, and they want different advice.
    ? (sameKind()
        ? `This clip is older than the choice. Make it again, and its ${named} can `
          + "be placed."
        : `Make the clip first: the box has to know the shape of the ${named}.`)
    : want
      ? `Drag it, pull the corner, or use the arrow keys. The ${named} itself `
        + "redraws when you let go."
      : mode === "video"
        ? "The frames are sized into the band the words leave."
        : "The artwork sits above the title, as tall as its own shape asks for.";
  paintPictureBox();
  paintSummaries();
}

/* -- dragging it -- */

let placingGesture = null;

$("picture-box").addEventListener("pointerdown", (event) => {
  if (!placing || !framing) return;
  // Never let this reach the frame's own handler: that one reads a press outside a
  // sticker as "put the selection down".
  event.stopPropagation();
  event.preventDefault();
  selectPicture();
  $("picture-box").focus({ preventScroll: true });

  const screen = $("screen").getBoundingClientRect();
  const grip = event.target.closest && event.target.closest(".framebox__grip");
  const centre = {
    x: screen.left + framing.x * screen.width,
    y: screen.top + framing.y * screen.height,
  };
  placingGesture = {
    grip: !!grip,
    size: framing.size,
    reach: reach(centre, event) || 1,
    centre,
    from: { x: framing.x, y: framing.y },
    at: { x: event.clientX, y: event.clientY },
    screen,
  };
  $("screen").dataset.gesture = grip ? "picture-size" : "picture";
  try { event.currentTarget.setPointerCapture(event.pointerId); } catch { /* gone */ }
});

$("picture-box").addEventListener("pointermove", (event) => {
  if (!placingGesture) return;
  const held = placingGesture;
  if (held.grip) {
    framing.size = clamp(held.size * (reach(held.centre, event) / held.reach),
                         PICTURE_MIN, PICTURE_MAX);
  } else {
    framing.x = clamp(held.from.x + (event.clientX - held.at.x) / held.screen.width,
                      -1.5, 1.5);
    framing.y = clamp(held.from.y + (event.clientY - held.at.y) / held.screen.height,
                      -1.5, 1.5);
  }
  paintPictureBox();
  event.preventDefault();
});

function endPlacing(event) {
  if (!placingGesture) return;
  placingGesture = null;
  delete $("screen").dataset.gesture;
  try { $("picture-box").releasePointerCapture(event.pointerId); } catch { /* gone */ }
  // Now it is worth asking the server for the frame again: while the hand was
  // moving, the box was the answer.
  wordsChanged();
}

$("picture-box").addEventListener("pointerup", endPlacing);
$("picture-box").addEventListener("pointercancel", endPlacing);

document.querySelectorAll(".segmented__option[data-picture]").forEach((option) => {
  option.addEventListener("click", () => {
    setPlacing(option.dataset.picture);
    remember();
    wordsChanged();
  });
});

$("picture-box").addEventListener("focus", selectPicture);

/* ─────────────────────  the keyboard on the frame  ─────────────────────

   Everything placed on the frame could be driven with a hand and only with a hand.
   A placed thing is a box with a position, a size and an angle: three numbers, and
   numbers are what a keyboard is better at than a hand. Half a percent of a 300
   pixel frame is one and a half pixels, which is not a drag anybody can make.

   Two ways in, and they meet in the same place. Click a sticker, because that is
   how a hand gets to one; or tab to it, which is the only route for somebody not
   using a pointer at all. Either way it is `picked`, and the keys act on `picked`
   rather than on whatever happens to hold focus.

   **Nothing here fires while you are typing.** `inAField` is the same guard the
   paste handler uses: Delete inside the free text box has to stay Delete, and an
   arrow key in the caption has to move the cursor. */

/* A machine that is not a touch screen has a keyboard beside it; a phone does not.
   Asked the way the stylesheet asks it, D-038's way round: the positive test is
   "this is a touch screen", so a browser that reports neither keeps the hint rather
   than quietly losing it. It decides only whether the hint mentions keys, never
   whether they work: an external keyboard on a tablet drives the frame the same. */
const HAS_KEYS = !window.matchMedia("(hover: none) and (pointer: coarse)").matches;

const NUDGE = 0.005, NUDGE_FAR = 0.02;    // fractions of the frame, per press
const SIZE_KEY = 0.01, SIZE_KEY_FAR = 0.05;
const TURN_KEY = 1, TURN_KEY_FAR = 15;

/* One slot of undo, because the keyboard is what makes an accidental delete
   likely. The cross has always removed without asking, on the grounds that a
   sticker is one tap to put back; a line of free text is not, it is retyped, and
   Delete is a key people press by mistake. */
let lastRemoved = null;

function removeDecal(at) {
  if (!decals[at]) return;
  lastRemoved = { decal: decals[at], at };
  decals.splice(at, 1);
  picked = -1;
  changed();
}

function restoreRemoved() {
  if (!lastRemoved) return false;
  const { decal, at } = lastRemoved;
  lastRemoved = null;
  picked = Math.min(at, decals.length);
  decals.splice(picked, 0, decal);
  changed();
  const box = $("decals").children[picked];
  if (box) box.focus({ preventScroll: true });
  return true;
}

const KEY_MOVES = {
  ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1],
};

/* The picture under the same keys as everything else placed. Returns whether the
   press was used, so the handler below can carry on to the stickers if not. */
function drivePicture(event) {
  const far = event.shiftKey;
  const moved = KEY_MOVES[event.key];
  if (moved) {
    const step = far ? NUDGE_FAR : NUDGE;
    framing.x = clamp(framing.x + moved[0] * step, -1.5, 1.5);
    framing.y = clamp(framing.y + moved[1] * step, -1.5, 1.5);
  } else if (["+", "=", "-", "_"].includes(event.key)) {
    const way = (event.key === "+" || event.key === "=") ? 1 : -1;
    framing.size = clamp(framing.size + way * (far ? SIZE_KEY_FAR : SIZE_KEY),
                         PICTURE_MIN, PICTURE_MAX);
  } else if (event.key === "Escape") {
    pickedPicture = false;
    paintPictureBox();
    if (document.activeElement === $("picture-box")) $("picture-box").blur();
    paintStickerHint();
    event.preventDefault();
    return true;
  } else {
    return false;
  }
  paintPictureBox();
  paintStale();
  // Held down, this fires many times a second: the redraw is debounced inside
  // `wordsChanged`, so the server sees one request after the last press.
  wordsChanged();
  event.preventDefault();
  return true;
}

document.addEventListener("keydown", (event) => {
  if (inAField(event.target)) return;
  const undo = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z";
  if (undo && !event.shiftKey) {
    if (restoreRemoved()) event.preventDefault();
    return;
  }
  if (event.metaKey || event.ctrlKey || event.altKey) return;

  // The picture answers to the same keys, minus the ones that make no sense on it:
  // it cannot be turned, and it cannot be thrown away, only fitted again.
  if (pickedPicture && framing) {
    if (drivePicture(event)) return;
  }
  const one = decals[picked];
  if (event.key === "Escape") {
    // Out of the selection, and out of the box holding focus, so the next Tab
    // carries on through the page rather than back into the frame.
    if (!one) return;
    deselect();
    if (document.activeElement && document.activeElement.closest(".decal")) {
      document.activeElement.blur();
    }
    return event.preventDefault();
  }
  if (!one) return;

  const far = event.shiftKey;
  const moved = KEY_MOVES[event.key];
  if (moved) {
    const step = far ? NUDGE_FAR : NUDGE;
    // The same bounds the server clamps to: half off the frame is a choice, and
    // anywhere past that is not a placement any more.
    one.x = clamp(one.x + moved[0] * step, -0.5, 1.5);
    one.y = clamp(one.y + moved[1] * step, -0.5, 1.5);
    adjusted(picked);
    return event.preventDefault();
  }
  if (event.key === "Delete" || event.key === "Backspace") {
    removeDecal(picked);
    return event.preventDefault();
  }
  if (["+", "=", "-", "_"].includes(event.key)) {
    const way = (event.key === "+" || event.key === "=") ? 1 : -1;
    one.size = clamp(one.size + way * (far ? SIZE_KEY_FAR : SIZE_KEY),
                     MIN_SIZE, MAX_SIZE);
    adjusted(picked);
    return event.preventDefault();
  }
  if (event.key === "[" || event.key === "]") {
    const way = event.key === "]" ? 1 : -1;
    one.rotation = settle(one.rotation + way * (far ? TURN_KEY_FAR : TURN_KEY));
    adjusted(picked);
    return event.preventDefault();
  }
  if (event.key === "Enter" && isText(one)) {
    // The words are edited in the box that wrote them, which is where the caret
    // has to go: Enter on a line of text is "let me retype this".
    $("text-line").focus();
    $("text-line").select();
    return event.preventDefault();
  }
});

$("decals").addEventListener("pointerdown", onHandleDown);

$("screen").addEventListener("pointerdown", onFramePointerDown);
$("screen").addEventListener("pointermove", onFramePointerMove);
$("screen").addEventListener("pointerup", onFramePointerUp);
$("screen").addEventListener("pointercancel", onFramePointerUp);

/* -- the shelf -- */

/* Which shelf you are looking at. "drawings" is the 4,495 OpenMoji library plus
   your own; "gifs" is whatever provider `.env` names, and does not exist at all
   unless one is configured. Kept apart rather than merged, because forty GIF
   results would bury the drawings and the two are reached for at different
   moments. See D-043. */
let gifSource = false;

/* Only the newest search paints the shelf: typing "cat" asks for "c", "ca" and
   "cat", and a slow answer for "ca" must not land on top of the one for "cat". */
let shelfAsked = 0;

async function loadShelf(query = "") {
  if (gifSource) return loadGifShelf(query);
  const mine = ++shelfAsked;
  let found;
  try {
    found = await api(`/api/stickers?q=${encodeURIComponent(query)}`);
  } catch (error) {
    if (mine !== shelfAsked) return undefined;
    return fail($("sticker-error"), error.message);
  }
  if (mine !== shelfAsked) return undefined;
  hide($("sticker-error"));
  const shelf = $("shelf");
  if (!found.stickers.length) {
    shelf.innerHTML = `<p class="shelf__empty">${
      escapeHtml(found.hint || "Nothing matches that.")}</p>`;
    return;
  }
  // The shelf shows a still thumbnail of an animated sticker, because a grid of
  // forty looping GIFs is a fairground. The corner mark is what says it moves.
  shelf.innerHTML = found.stickers.map((sticker) => `
    <button type="button" class="shelf__item" data-id="${escapeHtml(sticker.id)}"
            ${sticker.moving ? 'data-moving="true"' : ""}
            title="${escapeHtml(sticker.name)}${sticker.mine ? " (yours)" : ""}${
              sticker.moving ? ", moves" : ""}">
      <img src="${stickerImage(sticker.id, 96)}" alt="${escapeHtml(sticker.name)}"
           loading="lazy">
    </button>`).join("");
  shelf.querySelectorAll(".shelf__item").forEach((item) => {
    item.addEventListener("click", () => add(item.dataset.id));
  });
}

/* A GIF shelf. Every thumbnail comes from this server, never from the provider:
   the phone reads this page over the tailnet, and an image loaded straight from
   GIPHY would put the phone in touch with GIPHY rather than just the laptop. */
async function loadGifShelf(query = "") {
  const mine = ++shelfAsked;   // an empty box also outdates a search still out
  const shelf = $("shelf");
  if (HOSTED && !gifCredit.provider) {
    shelf.innerHTML = `<p class="shelf__empty">GIF search uses your own free GIPHY or
      KLIPY keys, one or both. <a href="/account#keys">Add them in your account</a>.</p>`;
    return;
  }
  if (!query.trim()) {
    shelf.innerHTML = `<p class="shelf__empty">Type what you are looking for.</p>`;
    return;
  }
  shelf.innerHTML = `<p class="shelf__empty">Searching...</p>`;
  let found;
  try {
    // The wide shelf draws 172 pixel cells and the phone draws 92 pixel ones, so
    // it asks for a thumbnail that suits it rather than upscaling a small one.
    // Measured 2026-08-22: KLIPY's small preview is 127 pixels wide, which was
    // visibly soft in the desktop cell the moment the cell grew.
    const big = matchMedia("(min-width: 901px)").matches ? "&big=1" : "";
    found = await api(`/api/gifs?q=${encodeURIComponent(query)}${big}`);
  } catch (error) {
    if (mine !== shelfAsked) return undefined;
    shelf.innerHTML = "";
    return fail($("sticker-error"), error.message);
  }
  if (mine !== shelfAsked) return undefined;
  hide($("sticker-error"));
  if (!found.gifs.length) {
    shelf.innerHTML = `<p class="shelf__empty">Nothing matches that.</p>`;
    return;
  }
  // These do move in the shelf, unlike the drawings. A GIF chosen from a still is
  // a guess, and the whole point of the picture is the motion.
  shelf.innerHTML = found.gifs.map((gif) => `
    <button type="button" class="shelf__item shelf__item--gif"
            data-gif="${escapeHtml(gif.id)}" data-moving="true"
            title="${escapeHtml(gif.title)}">
      <img src="/api/gif?id=${encodeURIComponent(gif.id)}&t=${
        encodeURIComponent(TOKEN)}" alt="${escapeHtml(gif.title)}" loading="lazy">
    </button>`).join("");
  shelf.querySelectorAll(".shelf__item").forEach((item) => {
    item.addEventListener("click", () => pickGif(item));
  });
}

/* Chosen: the server downloads it, keeps it in the rolling recent set, and hands
   back an ordinary sticker id. From that point it is a sticker like any other. */
async function pickGif(item) {
  if (item.dataset.busy) return;
  item.dataset.busy = "1";
  item.classList.add("shelf__item--working");
  try {
    const saved = await post("/api/gif/pick", { id: item.dataset.gif });
    hide($("sticker-error"));
    add(saved.id);
  } catch (error) {
    fail($("sticker-error"), error.message);
  } finally {
    delete item.dataset.busy;
    item.classList.remove("shelf__item--working");
  }
}

/* The toggle only exists when a provider is configured, so an unconfigured tool
   shows no trace of the feature rather than a button that answers 404. */
function paintGifSource(credit) {
  const bar = $("sticker-source");
  // Hosted, the GIF shelf is always there: without a key of the person's own, it
  // says how to add one rather than not existing.
  const on = Boolean(HOSTED) || Boolean(credit && credit.provider);
  bar.hidden = !on;
  if (!on && gifSource) {
    gifSource = false;
    markSource();
    loadShelf($("sticker-search").value);
  }
  gifCredit = credit || {};
  paintCredit();
}

function paintCredit() {
  const mark = $("gif-credit");
  const show = gifSource && gifCredit.label;
  mark.hidden = !show;
  if (show) mark.textContent = gifCredit.label;
  $("sticker-search").placeholder = gifSource
    ? (gifCredit.placeholder || "Search GIFs")
    : "Search: om, flower, music";
  // The cells are sized per source: a drawing reads at 52 pixels and a GIF does
  // not. See `.shelf[data-source="gifs"]`.
  $("shelf").dataset.source = gifSource ? "gifs" : "drawings";
  paintProviders();
}

/* Which service answers the search, as radios on the end of the source toggle.

   They were pills below that toggle and read as a second toggle of the same
   standing: same shape, same colour, sitting where the eye had just been told a
   choice lives. Choosing a service is a detail of having chosen GIFs at all, and a
   radio group says exactly that without a word of explanation.

   Drawn only while the GIF shelf is showing and only when there is more than one
   key configured: one provider is not a choice, and a chooser with a single option
   is furniture. The CSS keeps it off narrow screens as well.

   **This switches for the session and never writes `.env`.** The file stays the
   default, so a restart goes back to whatever is written there. A web request that
   can rewrite the file holding the API keys is not a trade worth making for a
   choice this cheap to repeat. */
function paintProviders() {
  const bar = $("gif-provider");
  const choices = gifCredit.choices || [];
  const show = gifSource && choices.length > 1;
  bar.hidden = !show;
  if (!show) return;
  bar.innerHTML = choices.map((one) => `
    <label class="gifpick__choice">
      <input type="radio" name="gif-provider" value="${escapeHtml(one.name)}"
             ${one.name === gifCredit.provider ? "checked" : ""}><span>${
      escapeHtml(one.name === "both" ? "Both" : one.name.toUpperCase())}</span></label>`).join("");
  // `change` rather than `click`: a radio group is also driven by the arrow keys,
  // and a click listener would ignore every one of them.
  bar.querySelectorAll("input").forEach((radio) => {
    radio.addEventListener("change", () => switchProvider(radio.value));
  });
}

async function switchProvider(name) {
  if (!name || name === gifCredit.provider) return;
  try {
    gifCredit = await post("/api/gif/provider", { provider: name });
  } catch (error) {
    return fail($("sticker-error"), error.message);
  }
  hide($("sticker-error"));
  paintCredit();
  // The old results named ids the new provider has never heard of, so the shelf
  // is asked again rather than left showing pictures that can no longer be picked.
  loadShelf($("sticker-search").value);
}

function markSource() {
  $("sticker-source").querySelectorAll(".chip").forEach((chip) =>
    chip.setAttribute("aria-pressed",
      String((chip.dataset.source === "gifs") === gifSource)));
  paintCredit();
}

let gifCredit = {};

$("sticker-source").querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    const want = chip.dataset.source === "gifs";
    if (want === gifSource) return;
    gifSource = want;
    markSource();
    hide($("sticker-error"));
    loadShelf($("sticker-search").value);
  });
});

/* Bring the handles back over a clip that already contains these stickers.

   `decalsEditing` rather than `decalsDirty`: nothing has actually changed yet, and
   saying "make the clip again" before a single sticker has been moved would be the
   page telling the person something untrue. The first drag sets `decalsDirty`
   itself, through `adjusted`. */
$("sticker-edit").addEventListener("click", () => {
  decalsEditing = true;
  if (picked === -1) picked = decals.length - 1;   // arrives wearing its handles
  paintDecals();
  repaintPicked();
});

function add(id) {
  if (decals.length >= 20) return fail($("sticker-error"), "Twenty is plenty.");
  decals.push({ id, x: 0.5, y: 0.45, size: 0.2, rotation: 0 });
  picked = decals.length - 1;   // it arrives selected, wearing its handles
  changed();
}

$("sticker-search").addEventListener("input", (event) => {
  clearTimeout(searchTimer);
  markTags("");
  searchTimer = setTimeout(() => loadShelf(event.target.value), 200);
});

/* A shelf you can reach without typing. Six words cover most of what goes on a
   devotional Status, and the search box is still there for everything else. */
$("sticker-tags").querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    $("sticker-search").value = chip.dataset.tag;
    markTags(chip.dataset.tag);
    loadShelf(chip.dataset.tag);
  });
});

function markTags(tag) {
  $("sticker-tags").querySelectorAll(".chip").forEach((chip) =>
    chip.setAttribute("aria-pressed", String(chip.dataset.tag === tag)));
}

$("sticker-size").addEventListener("input", (event) => {
  if (!decals[picked]) return;
  decals[picked].size = Number(event.target.value) / 100;
  adjusted(picked);
});

$("sticker-turn").addEventListener("input", (event) => {
  if (!decals[picked]) return;
  decals[picked].rotation = Number(event.target.value);
  adjusted(picked);
});

$("sticker-remove").addEventListener("click", () => removeDecal(picked));

/* Deleting one of your own stickers. Asked once, then asked again, the same rule as
   deleting a clip: the second press is the one that cannot be taken back. Every
   copy of it comes off this frame, because its picture is gone with it. */
$("sticker-forget").addEventListener("click", async () => {
  const button = $("sticker-forget");
  const one = decals[picked];
  if (!one || button.getAttribute("aria-busy") === "true") return;
  if (!button.dataset.armed) {
    button.dataset.armed = "true";
    button.textContent = "Delete it for good";
    return;
  }
  const id = one.id;
  button.setAttribute("aria-busy", "true");
  try {
    await post("/api/sticker/delete", { id });
  } catch (error) {
    button.removeAttribute("aria-busy");
    return fail($("sticker-error"), error.message);
  }
  button.removeAttribute("aria-busy");
  for (let at = decals.length - 1; at >= 0; at--) if (decals[at].id === id) removeDecal(at);
  lastRemoved = null;   // an undo would bring back a picture that no longer exists
  loadShelf($("sticker-search").value);
});

/* -- uploading one of your own -- */

$("sticker-upload").addEventListener("click", () => $("sticker-file").click());

const readFile = (file) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result));
  reader.onerror = () => reject(new Error("that file could not be read"));
  reader.readAsDataURL(file);
});

/* One file is "I want that one, now", and it goes straight onto the frame. Several
   is stocking the cupboard, and putting a dozen stickers on the frame is not what
   anybody meant by picking a dozen files. One refusal does not stop the rest: the
   others are already uploaded by then, and the way to lose thirty minutes of
   collecting artwork is to throw the batch away over one bad file. See D-035. */
async function ingest(files, verb) {
  hide($("sticker-error"));
  const saved = [];
  const refused = [];
  for (const [at, file] of files.entries()) {
    $("sticker-hint").textContent = files.length > 1
      ? `${verb} ${at + 1} of ${files.length}.`
      : `${verb} it.`;
    try {
      const name = (file.name || "pasted").replace(/\.[^.]+$/, "");
      saved.push(await post("/api/sticker", { name, data: await readFile(file) }));
    } catch (error) {
      refused.push(`${file.name || "that picture"}: ${error.message}`);
    }
  }

  $("sticker-search").value = "";
  markTags("");
  await loadShelf();

  if (files.length === 1 && saved.length) {
    add(saved[0].id);
  } else {
    paintStickerHint();
    if (saved.length) {
      $("sticker-hint").textContent =
        `${saved.length} added to your shelf. Pick the ones you want.`;
    }
  }
  if (refused.length) {
    fail($("sticker-error"), refused.length === 1
      ? refused[0]
      : `${refused.length} were refused, the rest are in. ${refused[0]}`);
  }
  return saved;
}

$("sticker-file").addEventListener("change", async (event) => {
  const files = [...event.target.files];
  event.target.value = "";           // so the same files can be picked again
  if (files.length) await ingest(files, "Uploading");
});

/* ── paste a picture in, which is how a GIF arrives ──
   There is no way for a page to open the phone keyboard's own GIF picker, and no
   need: pick one in Gboard, in any app, and it lands on the clipboard, and this
   takes it from there. The same listener means a copied picture on the laptop works
   too, which is the ordinary way people move an image around a desktop.

   The paste is only intercepted when it actually carries a picture. A pasted link
   or a pasted line of text goes where it was aimed, which matters because the
   caption box is the thing people paste into most. */
document.addEventListener("paste", async (event) => {
  const carried = event.clipboardData;
  if (!carried) return;
  const pictures = [...(carried.files || [])].filter(
    (file) => file.type && file.type.startsWith("image/")
  );

  if (!pictures.length) {
    // Some keyboards hand over a link to the picture instead of the picture. That
    // is not something this page can use, and saying so is better than doing
    // nothing at all while the person waits for a sticker to appear.
    const text = (carried.getData("text/plain") || "").trim();
    const looksLikeOne = /^https?:\/\/\S+\.(gif|png|jpe?g|webp)(\?|$)/i.test(text);
    if (looksLikeOne && !inAField(event.target)) {
      openSection("stickers", true);
      fail($("sticker-error"),
        "That paste was a link, not a picture. Save the image first, then paste it.");
    }
    return;
  }

  event.preventDefault();
  openSection("stickers", true);
  await ingest(pictures, "Adding");
});

/* ── the box that can receive a picture ──
   A phone keyboard decides whether to offer its GIF tab from what the focused
   element says it accepts, and a plain `<input>` says text only. This one is
   `contenteditable`, which is the target type that can take a picture.

   Two routes land here and both are handled. Some browsers deliver a paste event
   carrying a File, which the listener above already takes before anything is
   inserted. Others insert an `<img>` straight into the box and never mention a
   file, so anything that appears in here is pulled back out and uploaded. */
const gifBox = $("gif-drop");

gifBox.addEventListener("input", async () => {
  const images = [...gifBox.querySelectorAll("img")];
  const typed = gifBox.textContent.trim();
  gifBox.innerHTML = "";           // a slot, never a field: it never keeps anything

  if (!images.length) {
    if (typed) {
      $("gif-hint").textContent =
        "This box takes pictures, not words. Search above for a drawing.";
    }
    return;
  }
  $("gif-hint").textContent = "Or copy any picture and paste it anywhere on this page.";
  openSection("stickers", true);

  const files = [];
  for (const image of images) {
    try {
      const answer = await fetch(image.src);
      const blob = await answer.blob();
      files.push(new File([blob], "pasted", { type: blob.type || "image/png" }));
    } catch {
      fail($("sticker-error"),
        "That picture came in as a link this page cannot open. Save it first.");
    }
  }
  if (files.length) await ingest(files, "Adding");
});

// Return kept in a box that holds nothing would only make an empty line.
gifBox.addEventListener("keydown", (event) => {
  if (event.key === "Enter") event.preventDefault();
});

/* Typing targets keep their own paste. A link pasted into the caption box is a
   caption, not a failed sticker. */
function inAField(node) {
  if (!node || !node.closest) return false;
  // The picture box is contenteditable but is not somewhere anybody types, so a
  // link pasted into it gets the same explanation as a link pasted at the page.
  if (node.closest("#gif-drop")) return false;
  return Boolean(node.closest("input, textarea, [contenteditable]"));
}

/* ─────────────────────────  the window: length or end  ───────────────────────── */

/* A second timestamp parser, deliberately: this one only keeps the two boxes
   agreeing as you type. The server validates with `timecode.py`, which is the one
   that decides what a window means. */
function seconds(text) {
  const value = (text || "").trim();
  if (!value) return null;
  if (/^\d+(\.\d+)?$/.test(value)) return parseFloat(value);
  const parts = value.match(/^(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)$/);
  if (!parts) return null;
  return (parseInt(parts[1] || "0", 10) * 3600)
       + (parseInt(parts[2], 10) * 60)
       + parseFloat(parts[3]);
}

function clock(total) {
  const whole = Math.max(0, Math.round(total || 0));
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const secs = whole % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return hours ? `${hours}:${pad(minutes)}:${pad(secs)}` : `${minutes}:${pad(secs)}`;
}

function linkWindow(edited) {
  if (edited) windowEdit = edited;
  const start = seconds($("start").value) ?? 0;
  if (windowEdit === "end") {
    const end = seconds($("end").value);
    if (end !== null && end > start) $("duration").value = Math.round(end - start);
  } else {
    const length = Number($("duration").value.trim());
    if (Number.isFinite(length) && length > 0) $("end").value = clock(start + length);
  }
  markChips();
}

$("duration").addEventListener("input", () => { linkWindow("duration"); remember(); });
$("end").addEventListener("input", () => { linkWindow("end"); remember(); });
$("start").addEventListener("input", () => { linkWindow(); remember(); });

document.querySelectorAll(".chip[data-duration]").forEach((chip) => {
  chip.addEventListener("click", () => {
    $("duration").value = chip.dataset.duration;
    linkWindow("duration");
    remember();
  });
});

function markChips() {
  const value = $("duration").value.trim();
  document.querySelectorAll(".chip[data-duration]").forEach((chip) =>
    chip.setAttribute("aria-pressed", String(chip.dataset.duration === value)));
}

/* ─────────────────────────  small interactions  ───────────────────────── */

/* What the label sits above depends on the mode: card mode has a card and video
   mode does not, and it goes above the words there instead. It is drawn in both. */
function setMode(next) {
  mode = next;
  // `[data-mode]`, not every segmented option on the page. Without it this reached
  // into Background and Picture and unchecked both of their options, and Background
  // has nothing that puts its own back: switching the mode left it showing neither
  // Blurred video nor Black until one was clicked.
  document.querySelectorAll(".segmented__option[data-mode]").forEach((option) =>
    option.setAttribute("aria-checked", String(option.dataset.mode === next)));
  $("mode-hint").textContent = MODE_HINTS[next];
  // The card composes its own background, scrim and shadow together, so there is
  // nothing to choose there.
  $("fill-field").hidden = next !== "video";
  // Both modes place a picture: the video's frames in one, the artwork panel in the
  // other. Only the background is video's alone. A clip of the other kind is on
  // screen while the mode is being switched, so the control has to be re-asked.
  $("picture-label").textContent = next === "video" ? "Picture" : "Artwork";
  setPlacing(placing ? "placed" : "fitted");
  // The eyebrow's label used to be swapped here, because it sits above the card in
  // one mode and above the words in the other. Both are above the title, so it is
  // called that in both and there is nothing to swap.
}

document.querySelectorAll(".segmented__option[data-mode]").forEach((option) => {
  option.addEventListener("click", () => {
    setMode(option.dataset.mode);
    remember();
  });
});

function setFill(next) {
  fill = next === "black" ? "black" : "blur";
  document.querySelectorAll(".segmented__option[data-fill]").forEach((option) =>
    option.setAttribute("aria-checked", String(option.dataset.fill === fill)));
  $("fill-hint").textContent = FILL_HINTS[fill];
  paintSummaries();
}

document.querySelectorAll(".segmented__option[data-fill]").forEach((option) => {
  option.addEventListener("click", () => {
    setFill(option.dataset.fill);
    remember();
    // It is under everything, so the still that previews the words has to be
    // asked for again: it carries the background as well as the words.
    wordsChanged();
  });
});

/* The words on the card belong to a song. Keeping them when the link changes is
   how you post one song under another song's title.

   This existed before and missed three ways, all of them reported as "the title is
   left over from the previous video" on 2026-08-22:

   1. It asked `current.job.url`, the clip on screen. After a reload there is no
      clip on screen, but `restore` has already put the previous words back from
      localStorage, so nothing was compared and nothing was cleared.
   2. It compared raw strings, so pasting the same song as `youtu.be/X` after
      `watch?v=X` threw away words that belonged to that very song.
   3. It cleared the title and the channel and left the footer and the eyebrow,
      which belong to a song just as much.

   So the words now carry the video they were derived for, `wordsFor`, which is
   remembered with them and survives a reload. */
const WORD_FIELDS = ["title", "channel", "footer", "eyebrow", "topline"];
let wordsFor = "";

/* The video a link names, so two spellings of one song are one song. `youtu.be/X`,
   `watch?v=X`, `/shorts/X` and `/embed/X` all reduce to X; anything unrecognised
   falls back to the address itself, which is no worse than the old behaviour. */
function videoKey(url) {
  const text = (url || "").trim();
  if (!text) return "";
  const found = text.match(
    /(?:youtu\.be\/|[?&]v=|\/shorts\/|\/embed\/|\/live\/)([A-Za-z0-9_-]{11})/);
  return found ? found[1] : text.toLowerCase().replace(/\/+$/, "");
}

/* Called wherever the boxes are filled from a job rather than by hand. */
function wordsBelongTo(url) {
  wordsFor = videoKey(url);
}

function forgetWordsIfSongChanged() {
  const key = videoKey($("url").value);
  if (!key || !wordsFor || key === wordsFor) return false;
  const had = WORD_FIELDS.some((id) => $(id).value);
  WORD_FIELDS.forEach((id) => { $(id).value = ""; });
  wordsFor = "";
  clearPreview();
  return had;
}

$("url").addEventListener("input", () => {
  forgetWordsIfSongChanged();
  paintClear();
  remember();
});

$("url-clear").addEventListener("click", () => {
  $("url").value = "";
  paintClear();
  remember();
  $("url").focus();
});

function paintClear() {
  $("url-clear").hidden = !$("url").value;
}

$("guides").addEventListener("change", (event) => {
  $("phone").dataset.guides = event.target.checked ? "on" : "off";
  remember();
});

$("title").addEventListener("input", remember);
$("channel").addEventListener("input", remember);
$("footer").addEventListener("input", remember);
$("eyebrow").addEventListener("input", remember);
$("topline").addEventListener("input", remember);
// The waveform is drawn by ffmpeg and it moves, so no still can show it. The
// pane says that rather than saying nothing, which is what it used to do.
$("wave").addEventListener("change", () => { remember(); wordsChanged(); });

document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    if ($("caption").contains(document.activeElement)) return;
    event.preventDefault();
    $("form").requestSubmit();
  }
});

/* ─────────────────────────  helpers  ───────────────────────── */

function setBusy(busy) {
  working = busy;
  if (!busy) stopWanted = false;
  $("make").textContent = busy ? "Working..." : "Make the clip";
  // The spinner beside "Working...": the button is grey while it works, and grey
  // alone reads as broken rather than busy.
  $("make").toggleAttribute("aria-busy", busy);
  $("form").setAttribute("aria-busy", String(busy));
  busy ? unhide($("progress")) : hide($("progress"));
  // While it works the row is two halves: what you started, and the way out of it.
  $("makerow").classList.toggle("makerow--working", busy);
  busy ? unhide($("stop")) : hide($("stop"));
  $("stop").disabled = false;
  $("stop").textContent = "Stop";
  $("stop").removeAttribute("aria-busy");
  if (!busy) renderTask = null;
  // Whether it is grey afterwards is not this function's business: a render that
  // has just finished leaves a clip that is exactly what the form asks for.
  paintMake();
}

function fail(element, message) {
  element.textContent = message;
  element.classList.add("alert");
  element.classList.remove("notice");
  unhide(element);
}

/* The same slot, saying something that is not a failure. `.notice` already
   existed for this; nothing had reached for it from here before. */
function note(element, message) {
  element.textContent = message;
  element.classList.remove("alert");
  element.classList.add("notice");
  unhide(element);
}

/* The attribute, not the property. `hidden` is defined on HTMLElement and not on
   SVGElement, so assigning to `svg.hidden` silently does nothing at all. */
const hide = (element) => element.setAttribute("hidden", "");
const unhide = (element) => element.removeAttribute("hidden");

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

/* Remember the whole form, not the shape of it.

   It used to keep the length, the look and the extras, and drop the link, the
   window and the words. That is fine on a laptop where the tab stays open, and
   wrong on a phone, where switching to WhatsApp and back can reload the page and
   you are retyping a link you pasted a minute ago. */

function remember() {
  const state = {
    url: $("url").value,
    start: $("start").value,
    end: $("end").value,
    duration: $("duration").value,
    title: $("title").value,
    channel: $("channel").value,
    mode,
    fill,
    framing,
    placing,
    wave: $("wave").checked,
    footer: $("footer").value,
    eyebrow: $("eyebrow").value,
    topline: $("topline").value,
    guides: $("guides").checked,
    edit: windowEdit,
    // Which video the words belong to, kept with them. Without this a reload puts
    // the words back and forgets whose they were, which is how they ended up on
    // the next song.
    wordsFor,
  };
  try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch { /* private mode */ }
  paintSummaries();
}

function restore() {
  let state = {};
  try { state = JSON.parse(localStorage.getItem(STORE_KEY) || "{}"); } catch { /* ignore */ }
  if (state.url) $("url").value = state.url;
  if (state.start) $("start").value = state.start;
  if (state.end) $("end").value = state.end;
  if (state.duration) $("duration").value = state.duration;
  if (state.title) $("title").value = state.title;
  if (state.channel) $("channel").value = state.channel;
  if (state.wave === false) $("wave").checked = false;
  if (state.footer) $("footer").value = state.footer;
  if (state.eyebrow) $("eyebrow").value = state.eyebrow;
  if (state.topline) $("topline").value = state.topline;
  // An older stored form has no `wordsFor`. Fall back to the url it was stored
  // with, which is the video those words were for.
  wordsFor = state.wordsFor || videoKey(state.url || "");
  // The safe areas are on unless you turned them off: a sticker under WhatsApp's
  // own caption is invisible, and you cannot see that coming without the bands.
  if (state.guides === false) $("guides").checked = false;
  $("phone").dataset.guides = $("guides").checked ? "on" : "off";
  setMode(state.mode === "video" ? "video" : "card");
  setFill(state.fill);
  framing = state.framing || null;
  setPlacing(state.placing && framing ? "placed" : "fitted");
  windowEdit = state.edit === "end" ? "end" : "duration";
  linkWindow(windowEdit);
  paintClear();
  markTags("");
  paintSummaries();
}

if (HOSTED) {
  // Up next follows the queue, which changes without this page being told.
  setInterval(() => {
    if (!document.hidden && current && HOSTED.canSchedule()) refreshUpNext();
  }, 30000);
  // The extension answered, or stopped answering: the buttons follow.
  window.SnipShareRepaint = () => {
    atLaptop = HOSTED.ready();
    paintPostButtons();
    paintMake();
  };
}

paintTheme(theme());
restoreOpen();
restore();
refreshState();
setInterval(refreshState, STATE_MS);
