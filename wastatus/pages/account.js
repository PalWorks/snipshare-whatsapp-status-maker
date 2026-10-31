/* The account page: one section at a time, named in the address, so Back works and
   a link can open a section. Settings read first and are edited in place: a row
   shows its value and a pencil, and the pencil turns the row into its field with
   Save and Cancel (Enter saves, Escape cancels). A change is confirmed by a short
   message at the foot of the screen. See docs/account-page.md, Table AP-5. */
(() => {
  const root = document.getElementById("account");
  const TOKEN = root.dataset.token;
  const EXT_ID = root.dataset.extensionId || "";
  const MIN_VERSION = root.dataset.minVersion || "0";
  const $ = (id) => document.getElementById(id);
  const UI = window.SnipShareUI;
  const SECTIONS = ["profile", "security", "history", "scheduled", "keys", "feedback",
    "extension", "data"];
  const NAMES = { giphy: "GIPHY", klipy: "KLIPY", both: "both" };
  const loaded = { history: false, extension: false, scheduled: false };
  // The person's pilot switch for Scheduled Statuses, from /api/account: null until
  // it answers, and the section is offered only when it is on.
  let scheduling = null;
  let me = null;
  let historyDays = 90;
  let keptClips = 10;

  // Long enough for feedback with three screenshots on a slow line; only a dead
  // connection reaches it.
  const REQUEST_TIMEOUT_MS = 120000;

  async function api(path, body) {
    let response;
    try {
      response = await fetch(path, {
        method: body ? "POST" : "GET",
        headers: { "X-Wastatus-Token": TOKEN,
                   ...(body ? { "Content-Type": "application/json" } : {}) },
        body: body ? JSON.stringify(body) : undefined,
        signal: AbortSignal.timeout ? AbortSignal.timeout(REQUEST_TIMEOUT_MS) : undefined,
      });
    } catch (error) {
      throw new Error(error && error.name === "TimeoutError"
        ? "The connection is too slow right now. Try again."
        : "Could not reach SnipShare. Check the connection and try again.");
    }
    let payload = {};
    try { payload = await response.json(); } catch { /* empty */ }
    if (response.status === 401) {
      location.assign("/signin?next=/account");
      throw new Error("Signed out. Sign in again.");
    }
    if (!response.ok) throw new Error(payload.error || `something went wrong (${response.status})`);
    return payload;
  }

  const escape = (value) => String(value ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const when = (epoch, withTime = true) => (epoch ? new Date(epoch * 1000).toLocaleString([], {
    day: "numeric", month: "short", year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}) }) : "never");
  const ago = (epoch) => {
    const seconds = Math.max(0, Date.now() / 1000 - epoch);
    if (seconds < 90) return "just now";
    if (seconds < 3600) return `${Math.round(seconds / 60)} minutes ago`;
    if (seconds < 86400) return `${Math.round(seconds / 3600)} hours ago`;
    return when(epoch, false);
  };
  const clock = (seconds) => {
    const whole = Math.round(seconds || 0);
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
  };
  const show = (element, on = true) => { element.hidden = !on; };
  const say = (text, options) => (UI ? UI.toast(text, options) : null);

  function busy(button, label) {
    button.style.minWidth = `${button.offsetWidth}px`;
    button.dataset.label = button.innerHTML;
    button.textContent = label;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  }
  function idle(button) {
    if (button.dataset.label) button.innerHTML = button.dataset.label;
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }

  /* ── a group of radio buttons, driven by the arrow keys ── */

  function radioKeys(group, selector) {
    if (!group) return;
    group.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
      const options = [...group.querySelectorAll(selector)].filter((o) => !o.disabled);
      const at = options.indexOf(document.activeElement);
      if (at < 0) return;
      event.preventDefault();
      const step = event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 1;
      const next = options[(at + step + options.length) % options.length];
      next.focus();
      next.click();
    });
  }

  /* ── one section at a time ─────────────────────────────── */

  function open(name) {
    if (!SECTIONS.includes(name) || (name === "scheduled" && scheduling === false)) name = "profile";
    SECTIONS.forEach((section) => show($(section), section === name));
    document.querySelectorAll(".account__nav [data-section]").forEach((link) => {
      if (link.dataset.section === name) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    const current = document.querySelector(`.account__nav [data-section="${name}"]`);
    if (current) current.scrollIntoView({ block: "nearest", inline: "nearest" });
    if (name === "history" && !loaded.history) loadHistory();
    if (name === "extension" && !loaded.extension) checkExtension();
    if (name === "feedback") paintLastFailure();
    if (name === "scheduled") { openScheduled(); tellShown(); }
  }
  window.addEventListener("hashchange", () => open(location.hash.slice(1)));

  /* ── profile ───────────────────────────────────────────── */

  function paintProfile(profile) {
    me = profile;
    $("who-name").textContent = profile.name || profile.email;
    $("who-email").textContent = profile.email;
    $("who-role").textContent = profile.role === "admin" ? "Admin" : "Member";
    $("who-role").className = `pill${profile.role === "admin" ? " pill--admin" : " pill--approved"}`;
    show($("who-role"));
    if (UI) UI.avatar($("avatar"), profile.picture, profile.name || profile.email);
    $("name-value").textContent = profile.name || "Not set";
    $("email").textContent = profile.email;
    $("access").textContent = profile.role === "admin" ? "Admin: approves people" : "Member";
    $("since").textContent = when(profile.created, false);
    $("fb-name").value = $("fb-name").value || profile.name || "";
    $("fb-email").value = profile.email;
    show($("admin-link"), profile.role === "admin");
  }

  // Editing in place: the row's value gives way to its field, and comes back.
  function editName(on) {
    show($("name-form"), on);
    show($("name-value"), !on);
    show($("name-edit"), !on);
    $("row-name").classList.toggle("row--editing", on);
    show($("name-error"), false);
    if (on) {
      $("name").value = (me && me.name) || "";
      $("name").focus();
      $("name").select();
    } else {
      $("name-edit").focus();
    }
  }
  $("name-edit").addEventListener("click", () => editName(true));
  $("name-cancel").addEventListener("click", () => editName(false));
  $("name").addEventListener("keydown", (event) => {
    if (event.key === "Escape") { event.preventDefault(); editName(false); }
  });
  $("name-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = $("name").value.trim();
    if (!name) {
      $("name-error").textContent = "A name cannot be empty.";
      show($("name-error"));
      return $("name").focus();
    }
    if (me && name === me.name) return editName(false);
    const button = $("name-save");
    busy(button, "Saving");
    try {
      const updated = await api("/api/account/profile", { name });
      paintProfile({ ...me, ...updated, picture: me.picture });
      editName(false);
      say("Name updated");
    } catch (error) {
      $("name-error").textContent = error.message;
      show($("name-error"));
    } finally {
      idle(button);
    }
  });

  function paintTheme(now) {
    document.querySelectorAll("[data-theme-value]").forEach((option) =>
      option.setAttribute("aria-checked", String(option.dataset.themeValue === now)));
  }
  document.querySelectorAll("[data-theme-value]").forEach((option) => {
    option.addEventListener("click", () => {
      if (!UI || option.getAttribute("aria-checked") === "true") return;
      UI.setTheme(option.dataset.themeValue);
      say(`Theme: ${option.dataset.themeValue}`);
    });
  });
  document.addEventListener("snipshare:theme", (event) => paintTheme(event.detail));
  if (UI) paintTheme(UI.theme());
  radioKeys($("theme-choice"), "[data-theme-value]");

  /* ── sign-in and security ──────────────────────────────── */

  function paintSessions(sessions) {
    $("sessions").innerHTML = sessions.map((one) => `
      <div class="row">
        <span class="row__label">${escape(one.agent)}</span>
        <span class="row__value">${one.current ? '<span class="pill pill--approved">This browser</span> ' : ""}
          <span class="row__note">Last used ${escape(ago(one.last_seen))}, signed in ${escape(when(one.created, false))}</span></span>
        ${one.current ? "" : `<button type="button" class="row__action linkish linkish--danger"
            data-end="${escape(one.id)}">Sign out</button>`}
      </div>`).join("") || '<div class="row"><span class="muted">No sessions.</span></div>';
    show($("others-out"), sessions.some((one) => !one.current));
  }

  $("sessions").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-end]");
    if (!button) return;
    busy(button, "Signing out");
    try {
      paintSessions((await api("/api/account/sessions/end", { id: button.dataset.end })).sessions);
      say("That browser is signed out");
    } catch (error) {
      idle(button);
      say(error.message, { tone: "error" });
    }
  });
  $("others-out").addEventListener("click", async () => {
    const button = $("others-out");
    busy(button, "Signing out");
    try {
      const answer = await api("/api/account/sessions/end", { others: true });
      paintSessions(answer.sessions);
      say(`Signed out of ${answer.ended} other ${answer.ended === 1 ? "browser" : "browsers"}`);
    } catch (error) {
      say(error.message, { tone: "error" });
    } finally {
      idle(button);
    }
  });

  /* ── history ───────────────────────────────────────────── */

  async function loadHistory() {
    if (!loaded.history) {
      $("today").innerHTML = '<div class="stat"><span class="skeleton" style="height:44px"></span></div>'.repeat(3);
      $("clips").innerHTML = '<span class="skeleton" style="height:84px"></span>'.repeat(3);
    }
    let data;
    try {
      data = await api("/api/account/history");
    } catch (error) {
      $("clips").innerHTML = `<p class="error">${escape(error.message)}</p>`;
      return;
    }
    loaded.history = true;
    const used = data.usage;
    $("today").innerHTML = [
      [`${used.clips} of ${used.clips_limit}`, "clips today"],
      [`${Math.round(used.upload_bytes / 1e6)} of ${Math.round(used.upload_limit / 1e6)} MB`, "uploaded today"],
      [`${used.failures}`, "failed today"],
    ].map(([value, label]) => `<div class="stat"><b>${escape(value)}</b><span>${escape(label)}</span></div>`).join("");
    const reset = new Date();
    reset.setUTCHours(24, 0, 0, 0);
    $("resets").textContent = `The day's limits reset at ${reset.toLocaleTimeString([], {
      hour: "2-digit", minute: "2-digit" })} your time.`;

    const most = Math.max(1, ...data.days.map((d) => d.clips + d.failures));
    $("days").innerHTML = data.days.map((d) => {
      const date = new Date(`${d.day}T00:00:00Z`);
      const label = date.toLocaleDateString([], { day: "numeric", month: "short", timeZone: "UTC" });
      return `<div class="day" title="${escape(label)}: ${d.clips} made, ${d.failures} failed">
        <span class="day__bar"><span class="day__ok" style="height:${(d.clips / most) * 100}%"></span><span
          class="day__bad" style="height:${(d.failures / most) * 100}%"></span></span>
        <span class="day__label">${date.getUTCDate()}</span></div>`;
    }).join("");

    $("history-note").textContent = `Every clip from the last ${historyDays} days. The newest `
      + `${keptClips} can still be opened or saved; older ones keep a link to the original.`;
    if (!data.clips.length) {
      $("clips").innerHTML = '<div class="empty"><p>No clips yet.</p><a class="button button--primary" href="/app">Make your first clip</a></div>';
      return;
    }
    $("clips").innerHTML = data.clips.map((clip) => {
      const source = clip.video_id
        ? `https://youtu.be/${encodeURIComponent(clip.video_id)}?t=${Math.floor(clip.start)}` : "";
      const media = (kind) => `/api/${kind}?stem=${encodeURIComponent(clip.stem)}&t=${encodeURIComponent(TOKEN)}`;
      return `<article class="clipline${clip.ok ? "" : " clipline--failed"}">
        ${clip.kept
          ? `<img class="clipline__thumb" src="${media("frame")}" alt="" loading="lazy">`
          : `<span class="clipline__thumb clipline__thumb--gone" aria-hidden="true"></span>`}
        <div class="clipline__body">
          <strong class="clipline__title">${escape(clip.title || "Untitled")}</strong>
          <span class="muted">${escape(clip.channel || "")}</span>
          <span class="clipline__meta">${escape(clock(clip.start))} to ${escape(clock(clip.end))}
            · ${clip.mode === "video" ? "video frames" : "artwork card"} · ${escape(when(clip.at))}
            ${clip.ok ? "" : ` · <span class="clipline__error">did not finish${clip.error ? `: ${escape(clip.error)}` : ""}</span>`}</span>
          <span class="clipline__actions">
            ${clip.kept ? `<a href="/app?clip=${encodeURIComponent(clip.stem)}">Open in SnipShare</a>
              <a href="${media("clip")}&download=1">Download</a>` : ""}
            ${source ? `<a href="${escape(source)}" target="_blank" rel="noopener">The original on YouTube</a>` : ""}
          </span>
        </div>
      </article>`;
    }).join("");
  }

  /* ── API keys ──────────────────────────────────────────── */

  function paintKeys(gifs) {
    document.querySelectorAll(".keyrow").forEach((row) => {
      const provider = row.dataset.provider;
      const have = gifs.keys[provider];
      const pill = row.querySelector("[data-state]");
      pill.textContent = have ? "Connected" : "Not added";
      pill.className = `pill${have ? " pill--approved" : ""}`;
      row.querySelector("[data-hint]").textContent = have
        ? `Key ending ${have.ends} · added ${when(have.added, false)}` : "";
      const openButton = row.querySelector("[data-open]");
      openButton.textContent = have ? "Replace" : "Add key";
      openButton.setAttribute("aria-label", `${have ? "Replace" : "Add"} your ${NAMES[provider]} key`);
      show(row.querySelector("[data-remove]"), Boolean(have));
      row.querySelector(".keyrow__how").hidden = Boolean(have);
      row.querySelector("input").placeholder = have
        ? `Paste a new ${NAMES[provider]} key` : `Paste your ${NAMES[provider]} key`;
    });
    const count = Object.keys(gifs.keys).length;
    document.querySelectorAll("#source [data-source]").forEach((option) => {
      const possible = option.dataset.source === "both" ? count > 1 : Boolean(gifs.keys[option.dataset.source]);
      option.disabled = !possible;
      option.setAttribute("aria-checked", String(option.dataset.source === gifs.source));
    });
    $("source-hint").textContent = !count
      ? "Add a key above, and GIF search appears beside the drawings in SnipShare."
      : count === 1
        ? "Add the other service's key too, to choose between them or search both."
        : gifs.source === "both"
          ? "Each search asks both services at once and mixes their answers."
          : `Searching ${NAMES[gifs.source]}. The same choice sits beside GIF search in SnipShare.`;
    $("gif-summary").textContent = !count ? "No keys yet"
      : `${Object.keys(gifs.keys).map((k) => NAMES[k]).join(" and ")} · searching ${
        gifs.source === "both" ? "both" : NAMES[gifs.source]}`;
  }

  // A key row is one of: "view", "edit" or "confirm". Only one row edits at a time.
  function keyMode(row, mode) {
    if (mode !== "view") {
      document.querySelectorAll(".keyrow").forEach((other) => { if (other !== row) keyMode(other, "view"); });
    }
    row.classList.toggle("row--editing", mode !== "view");
    show(row.querySelector("form"), mode === "edit");
    show(row.querySelector("[data-confirm]"), mode === "confirm");
    show(row.querySelector(".keyrow__actions"), mode === "view");
    show(row.querySelector("[data-error]"), false);
    if (mode === "edit") {
      row.querySelector("input").value = "";
      row.querySelector("input").focus();
    }
    if (mode === "confirm") row.querySelector("[data-keep]").focus();
  }

  document.querySelectorAll(".keyrow").forEach((row) => {
    const provider = row.dataset.provider;
    const input = row.querySelector("input");
    const error = row.querySelector("[data-error]");
    row.querySelector("[data-open]").addEventListener("click", () => keyMode(row, "edit"));
    row.querySelector("[data-cancel]").addEventListener("click", () => keyMode(row, "view"));
    row.querySelector("[data-remove]").addEventListener("click", () => keyMode(row, "confirm"));
    row.querySelector("[data-keep]").addEventListener("click", () => keyMode(row, "view"));
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { event.preventDefault(); keyMode(row, "view"); }
    });
    row.querySelector("form").addEventListener("submit", async (event) => {
      event.preventDefault();
      show(error, false);
      const key = input.value.trim();
      if (!key) {
        error.textContent = "Paste the key first.";
        show(error);
        return input.focus();
      }
      const button = row.querySelector("[data-save]");
      busy(button, "Checking");
      try {
        paintKeys(await api("/api/gifkey", { provider, key }));
        keyMode(row, "view");
        say(`${NAMES[provider]} key saved and working`);
      } catch (failure) {
        error.textContent = failure.message;
        show(error);
      } finally {
        idle(button);
      }
    });
    row.querySelector("[data-really]").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      busy(button, "Removing");
      try {
        paintKeys(await api("/api/gifkey/delete", { provider }));
        keyMode(row, "view");
        say(`${NAMES[provider]} key removed`);
      } catch (failure) {
        say(failure.message, { tone: "error" });
      } finally {
        idle(button);
      }
    });
  });

  document.querySelectorAll("#source [data-source]").forEach((option) => {
    option.addEventListener("click", async () => {
      if (option.disabled || option.getAttribute("aria-checked") === "true") return;
      try {
        paintKeys(await api("/api/gifkey/source", { source: option.dataset.source }));
        say(`GIF search: ${option.dataset.source === "both" ? "both services" : NAMES[option.dataset.source]}`);
      } catch (failure) {
        say(failure.message, { tone: "error" });
      }
    });
  });
  radioKeys($("source"), "[data-source]");

  /* ── feedback ──────────────────────────────────────────── */

  let kind = "idea";
  let files = [];        // {name, data (a data: address), size}
  const MAX_FILES = 3;
  const MAX_BYTES = 4_000_000;

  // Only this person's, and only from the last day: the browser may be shared, and
  // a week-old code is not what a problem written today is about.
  function lastFailure() {
    try {
      const kept = JSON.parse(localStorage.getItem("snipshare.lastFailure") || "null");
      if (!kept || !me || kept.email !== me.email || Date.now() - kept.at > 86400000) return "";
      return kept.code || "";
    } catch { return ""; }
  }

  function paintLastFailure() {
    const code = lastFailure();
    $("last-code").textContent = code;
    show($("include-wrap"), Boolean(code) && kind === "problem");
  }

  document.querySelectorAll("#kind [data-kind]").forEach((chip) => {
    chip.addEventListener("click", () => {
      kind = chip.dataset.kind;
      document.querySelectorAll("#kind [data-kind]").forEach((other) =>
        other.setAttribute("aria-checked", String(other === chip)));
      paintLastFailure();
    });
  });
  radioKeys($("kind"), "[data-kind]");

  $("message").addEventListener("input", () => {
    $("count").textContent = $("message").value.length;
    show($("message-error"), false);
  });
  $("subject").addEventListener("input", () => show($("subject-error"), false));

  function paintFiles() {
    $("thumbs").innerHTML = files.map((file, at) => `
      <figure class="thumb">
        ${file.data ? `<img src="${file.data}" alt="${escape(file.name)}">` : '<span class="skeleton"></span>'}
        <button type="button" class="thumb__remove" data-at="${at}" aria-label="Remove ${escape(file.name)}">×</button>
      </figure>`).join("");
    show($("drop-add"), files.length < MAX_FILES);
  }
  $("thumbs").addEventListener("click", (event) => {
    const button = event.target.closest("[data-at]");
    if (!button) return;
    files.splice(Number(button.dataset.at), 1);
    paintFiles();
  });

  function addFiles(list) {
    show($("files-error"), false);
    const problems = [];
    for (const file of list) {
      if (files.length >= MAX_FILES) { problems.push(`at most ${MAX_FILES} screenshots`); break; }
      if (!/^image\/(png|jpeg|webp|gif)$/.test(file.type)) { problems.push(`${file.name} is not a picture`); continue; }
      if (file.size > MAX_BYTES) { problems.push(`${file.name} is over 4 MB`); continue; }
      const reader = new FileReader();
      const slot = { name: file.name || "screenshot", data: "", size: file.size };
      files.push(slot);
      reader.addEventListener("load", () => { slot.data = reader.result; paintFiles(); });
      reader.readAsDataURL(file);
    }
    if (problems.length) {
      $("files-error").textContent = `Not added: ${problems.join("; ")}.`;
      show($("files-error"));
    }
    paintFiles();
  }
  $("files").addEventListener("change", () => { addFiles([...$("files").files]); $("files").value = ""; });
  const zone = $("dropzone");
  ["dragenter", "dragover"].forEach((type) => zone.addEventListener(type, (event) => {
    event.preventDefault();
    zone.classList.add("dropzone--over");
  }));
  ["dragleave", "drop"].forEach((type) => zone.addEventListener(type, () => zone.classList.remove("dropzone--over")));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    addFiles([...event.dataTransfer.files]);
  });
  $("feedback").addEventListener("paste", (event) => {
    const pictures = [...(event.clipboardData ? event.clipboardData.files : [])];
    if (pictures.length) { event.preventDefault(); addFiles(pictures); }
  });

  $("feedback-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    show($("send-error"), false);
    const subject = $("subject").value.trim();
    const message = $("message").value.trim();
    let first = null;
    if (!subject) {
      $("subject-error").textContent = "Add a subject, a few words on what this is about.";
      show($("subject-error"));
      first = $("subject");
    }
    if (message.length < 3) {
      $("message-error").textContent = "Write a few words first.";
      show($("message-error"));
      first = first || $("message");
    }
    if (first) return first.focus();
    if (files.some((file) => !file.data)) {
      $("send-error").textContent = "A screenshot is still being read. Send again in a moment.";
      return show($("send-error"));
    }
    const include = !$("include-wrap").hidden && $("include").checked;
    const brands = navigator.userAgentData
      ? navigator.userAgentData.brands.map((b) => `${b.brand} ${b.version}`).join(", ") : "";
    const button = $("send");
    busy(button, files.length ? "Sending with screenshots" : "Sending");
    try {
      await api("/api/feedback", {
        kind, subject, message, name: $("fb-name").value.trim(),
        code: include ? lastFailure() : "",
        versions: `${brands || navigator.userAgent.slice(0, 80)}`,
        attachments: files.map((file) => ({ name: file.name, data: file.data })),
      });
      $("sent-text").textContent = `The reply, if one is needed, comes to ${me ? me.email : "your address"}.`;
      show($("feedback-form"), false);
      show($("sent"));
      $("sent").focus();
    } catch (failure) {
      $("send-error").textContent = failure.message;
      show($("send-error"));
    } finally {
      idle(button);
    }
  });
  $("another").addEventListener("click", () => {
    $("subject").value = "";
    $("message").value = "";
    $("count").textContent = "0";
    files = [];
    paintFiles();
    show($("sent"), false);
    show($("feedback-form"));
    $("subject").focus();
  });

  /* ── extension ─────────────────────────────────────────── */

  function older(version, than) {
    const a = String(version || "0").split(".").map(Number);
    const b = String(than).split(".").map(Number);
    for (let i = 0; i < Math.max(a.length, b.length); i += 1) {
      if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) < (b[i] || 0);
    }
    return false;
  }

  function checkExtension() {
    loaded.extension = true;
    const tell = (ext, wa) => { $("ext-state").textContent = ext; $("wa-state").textContent = wa; };
    const mobile = navigator.userAgentData ? navigator.userAgentData.mobile
      : /Android|iPhone|iPad|Mobile/i.test(navigator.userAgent);
    if (mobile) return tell("Not on a phone: the extension needs Chrome on a computer", "Loaded by the extension");
    if (!EXT_ID || !(window.chrome && chrome.runtime && chrome.runtime.connect)) {
      return tell("Not found", "Loaded by the extension, once it is here");
    }
    let port;
    try { port = chrome.runtime.connect(EXT_ID, { name: "snipshare" }); } catch {
      return tell("Not found", "Loaded by the extension, once it is here");
    }
    const timer = setTimeout(() => { tell("Not answering: reload this page", "Unknown"); port.disconnect(); }, 5000);
    port.onMessage.addListener((answer) => {
      if (!answer.done) return;
      clearTimeout(timer);
      const version = answer.done.version;
      const wa = { "signed-in": "Signed in, in this browser", open: "Open, waiting for the QR code",
                   none: "Not open: Load into WhatsApp opens it" }[answer.done.whatsapp] || "Unknown";
      tell(older(version, MIN_VERSION) ? `Version ${version}: please update` : `Installed, version ${version}`, wa);
      port.disconnect();
    });
    port.onDisconnect.addListener(() => {
      void chrome.runtime.lastError;
      clearTimeout(timer);
      if ($("ext-state").textContent === "checking") tell("Not found", "Loaded by the extension, once it is here");
    });
    port.postMessage({ cmd: "hello" });
  }

  /* ── Scheduled Statuses ────────────────────────────────── */

  /* The queue lives in the extension (docs/scheduling.md, SC-D2) and its page is the
     one queue there is: it is framed here, not drawn a second time. The frame says
     only its height; this page says only the theme and which part of the frame is on
     screen. Both sides check the other's origin. docs/account-page.md, Table AP-8. */
  const EXT_ORIGIN = EXT_ID ? `chrome-extension://${EXT_ID}` : "";
  // Long enough for a cold service worker to start and answer the frame; past it the
  // frame is taken down and the queue offered in a tab of its own.
  const FRAME_WAIT_MS = 6000;
  let frame = null;
  let frameReady = false;
  let frameTimer = 0;

  function failure(code, message) {
    const error = new Error(message || code);
    error.code = code;
    return error;
  }

  // One request over a port of its own, answered once.
  function askExtension(message, wait) {
    return new Promise((resolve, reject) => {
      if (!EXT_ID || !(window.chrome && chrome.runtime && chrome.runtime.connect)) {
        return reject(failure("missing"));
      }
      let port;
      try { port = chrome.runtime.connect(EXT_ID, { name: "snipshare" }); } catch {
        return reject(failure("missing"));
      }
      let settled = false;
      const finish = (then, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        try { port.disconnect(); } catch { /* gone */ }
        then(value);
      };
      const timer = setTimeout(() => finish(reject, failure("silent")), wait);
      port.onMessage.addListener((answer) => {
        if (answer && answer.done) finish(resolve, answer.done);
        else if (answer && answer.error) finish(reject, failure(answer.error.code || "failed", answer.error.message));
      });
      port.onDisconnect.addListener(() => {
        void chrome.runtime.lastError;
        finish(reject, failure("missing"));
      });
      port.postMessage(message);
    });
  }

  // A state that is not the queue: one sentence and, where there is one, the one
  // thing to do about it.
  function schedNote(text, { link = "", openTab = false } = {}) {
    show($("sched-loading"), false);
    $("sched-note-text").textContent = text;
    $("sched-note-link").textContent = link;
    show($("sched-note-link"), Boolean(link));
    show($("sched-note-open"), openTab);
    show($("sched-note-actions"), Boolean(link) || openTab);
    show($("sched-note-error"), false);
    show($("sched-note"));
  }

  async function openScheduled() {
    if (loaded.scheduled || scheduling !== true) return;
    loaded.scheduled = true;
    const mobile = navigator.userAgentData ? navigator.userAgentData.mobile
      : /Android|iPhone|iPad|Mobile/i.test(navigator.userAgent);
    if (mobile) return schedNote("Scheduling works in Chrome on a computer with the extension.");
    let hello;
    try {
      hello = await askExtension({ cmd: "hello" }, 5000);
    } catch (error) {
      if (error.code === "silent") {
        return schedNote("The extension did not answer. Reload this page, and if it still "
          + "does not answer, update the extension.", { link: "Update the extension" });
      }
      return schedNote("Your queue is kept by the SnipShare extension. Add it to Chrome on "
        + "this computer to see and change it here.", { link: "Get the extension" });
    }
    if (older(hello.version, MIN_VERSION) || !(hello.features || []).includes("schedule")) {
      return schedNote(`This extension, version ${hello.version || "unknown"}, cannot schedule. `
        + "Update it to see and change your queue here.", { link: "Update the extension" });
    }
    mountFrame();
  }

  function mountFrame() {
    const wrap = $("sched-frame-wrap");
    frame = document.createElement("iframe");
    frame.title = "Your Scheduled Statuses";
    // Laid out at full width from the start, so the first height it sends is the
    // right one; it stays out of sight until then.
    frame.style.height = "0";
    frame.style.visibility = "hidden";
    frame.src = `${EXT_ORIGIN}/queue.html?embed=1&theme=${encodeURIComponent(UI ? UI.theme() : "system")}`;
    wrap.append(frame);
    show(wrap);
    frameTimer = setTimeout(() => { if (!frameReady) frameFailed(); }, FRAME_WAIT_MS);
  }

  function frameFailed() {
    if (frame) frame.remove();
    frame = null;
    show($("sched-frame-wrap"), false);
    schedNote("Your queue could not be shown on this page. It opens in a tab of its own.",
      { openTab: true });
  }

  window.addEventListener("message", (event) => {
    if (!frame || event.origin !== EXT_ORIGIN || event.source !== frame.contentWindow) return;
    const height = event.data && event.data.snipshareQueueHeight;
    if (!Number.isFinite(height)) return;
    frame.style.height = `${Math.min(Math.max(Math.round(height), 120), 20000)}px`;
    if (!frameReady) {
      frameReady = true;
      clearTimeout(frameTimer);
      show($("sched-loading"), false);
      frame.style.visibility = "";
      show($("sched-own-tab"));
    }
    tellShown();
  });

  // The frame is as tall as its content, so its toast is placed by what is on screen.
  let shownFrame = 0;
  function tellShown() {
    if (!frameReady || !frame || shownFrame) return;
    shownFrame = requestAnimationFrame(() => {
      shownFrame = 0;
      if (!frame || $("scheduled").hidden) return;
      const box = frame.getBoundingClientRect();
      frame.contentWindow.postMessage({ snipshareShown: {
        top: Math.max(0, -box.top), bottom: window.innerHeight - box.top } }, EXT_ORIGIN);
    });
  }
  window.addEventListener("scroll", tellShown, { passive: true });
  window.addEventListener("resize", tellShown);
  document.addEventListener("snipshare:theme", (event) => {
    if (frame && frameReady) frame.contentWindow.postMessage({ snipshareTheme: event.detail }, EXT_ORIGIN);
  });

  async function openQueueTab(button) {
    busy(button, "Opening");
    show($("sched-note-error"), false);
    try {
      await askExtension({ cmd: "open-queue" }, 8000);
    } catch (error) {
      const words = error.code === "missing" || error.code === "silent"
        ? "The extension did not answer. Reload this page and try again." : error.message;
      if ($("sched-note").hidden) say(words, { tone: "error" });
      else { $("sched-note-error").textContent = words; show($("sched-note-error")); }
    } finally {
      idle(button);
    }
  }
  $("sched-own-tab").addEventListener("click", (event) => openQueueTab(event.currentTarget));
  $("sched-note-open").addEventListener("click", (event) => openQueueTab(event.currentTarget));

  /* ── privacy and data ──────────────────────────────────── */

  $("delete-confirm").addEventListener("input", () => {
    $("delete").disabled = !me || $("delete-confirm").value.trim().toLowerCase() !== me.email;
  });
  $("delete").addEventListener("click", async () => {
    busy($("delete"), "Deleting");
    try {
      await api("/api/account/delete", { confirm: $("delete-confirm").value.trim().toLowerCase() });
      location.assign("/");
    } catch (failure) {
      idle($("delete"));
      $("delete-error").textContent = failure.message;
      show($("delete-error"));
    }
  });

  /* ── signing out ───────────────────────────────────────── */

  $("signout").addEventListener("click", async () => {
    busy($("signout"), "Signing out");
    // Only a sign-out the server confirmed leaves the page: going to the front page
    // with the session still alive would look signed out and not be.
    const done = await fetch("/api/signout", { method: "POST",
      headers: { "Content-Type": "application/json", "X-SnipShare": "1" }, body: "{}",
      signal: AbortSignal.timeout ? AbortSignal.timeout(30000) : undefined })
      .then((response) => response.ok).catch(() => false);
    if (done) return location.assign("/");
    idle($("signout"));
    say("Could not sign out: SnipShare did not answer. Check the connection and try again.",
      { tone: "error" });
  });

  /* ── start ─────────────────────────────────────────────── */

  open(location.hash.slice(1));
  api("/api/account").then((data) => {
    historyDays = data.history_days;
    keptClips = data.kept;
    paintProfile(data.profile);
    paintSessions(data.sessions);
    paintKeys(data.gifs);
    scheduling = Boolean(data.scheduling && data.scheduling.enabled);
    show($("scheduled-link"), scheduling);
    if (location.hash.slice(1) === "scheduled") open("scheduled");
    document.querySelectorAll("[data-kept]").forEach((e) => { e.textContent = data.kept; });
    document.querySelectorAll("[data-days]").forEach((e) => { e.textContent = data.history_days; });
    paintLastFailure();
  }).catch((error) => {
    $("load-error").textContent = `${error.message}. Reload the page to try again.`;
    show($("load-error"));
  });
})();
