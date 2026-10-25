/* The admin's page. A range of days at the top that every number below follows;
   requests as cards with Approve and Decline side by side; people as a searchable
   list, each with a menu for the rare things; and a change confirmed by a short
   message with Undo where an undo makes sense. See docs/account-page.md, AP-6. */
(() => {
  const root = document.getElementById("admin");
  const TOKEN = root.dataset.token;
  const SITE = root.dataset.site;
  const $ = (id) => document.getElementById(id);
  const UI = window.SnipShareUI;
  const say = (text, options) => (UI ? UI.toast(text, options) : null);
  const focusEmail = new URLSearchParams(location.search).get("email") || "";
  let clipsPerDay = 10;
  let range = { days: 1 };
  let people = [];
  let filter = "all";

  async function api(path, body) {
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
        ? "The connection is too slow right now. Try again." : "Could not reach SnipShare. Check the connection and try again.");
    }
    let payload = {};
    try { payload = await response.json(); } catch { /* empty */ }
    if (response.status === 401) location.assign("/signin?next=/admin");
    if (!response.ok) throw new Error(payload.error || `failed (${response.status})`);
    return payload;
  }

  const escape = (value) => String(value ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const when = (epoch) => (epoch ? new Date(epoch * 1000).toLocaleString([], {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "never");
  const ago = (epoch) => {
    if (!epoch) return "never";
    const seconds = Math.max(0, Date.now() / 1000 - epoch);
    if (seconds < 90) return "just now";
    if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
    if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
    return `${Math.round(seconds / 86400)} days ago`;
  };
  const mb = (bytes) => `${Math.round((bytes || 0) / 1e6)} MB`;
  const day = (date) => date.toISOString().slice(0, 10);

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

  /* ── the range ─────────────────────────────────────────── */

  function query() {
    if (range.from) return `?from=${range.from}&to=${range.to}`;
    const to = new Date();
    const from = new Date(Date.now() - (range.days - 1) * 86400000);
    return `?from=${day(from)}&to=${day(to)}`;
  }

  document.querySelectorAll("#range [data-range]").forEach((option) => {
    option.addEventListener("click", () => {
      document.querySelectorAll("#range [data-range]").forEach((o) =>
        o.setAttribute("aria-checked", String(o === option)));
      const custom = option.dataset.range === "custom";
      $("custom").hidden = !custom;
      if (custom) {
        $("to").value = $("to").value || day(new Date());
        $("from").value = $("from").value || day(new Date(Date.now() - 6 * 86400000));
        $("from").focus();
        return;
      }
      range = { days: Number(option.dataset.range) };
      load();
    });
  });
  $("custom").addEventListener("submit", (event) => {
    event.preventDefault();
    if (!$("from").value || !$("to").value) return;
    range = { from: $("from").value, to: $("to").value };
    load();
  });

  function rangeLabel(r) {
    const fmt = (d) => new Date(`${d}T00:00:00Z`).toLocaleDateString([], {
      day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
    return r.from === r.to ? `${fmt(r.from)}, UTC` : `${fmt(r.from)} to ${fmt(r.to)}, UTC`;
  }

  /* ── requests ──────────────────────────────────────────── */

  function requestCard(person) {
    const answers = person.answers || {};
    return `
      <article class="card request${person.email === focusEmail ? " person--focus" : ""}" data-email="${escape(person.email)}">
        <div class="request__top">
          <span class="avatar" data-avatar data-picture="${escape(person.picture || "")}" data-initial="${escape(person.name || person.email)}"></span>
          <span class="request__who"><strong>${escape(person.name || "(no name)")}</strong>
            <span class="muted">${escape(person.email)} · asked ${escape(ago(person.created))}</span></span>
        </div>
        ${answers.use || answers.heard ? `<p class="request__answers">
          ${answers.use ? `<span><strong>For:</strong> ${escape(answers.use)}</span>` : ""}
          ${answers.heard ? `<span><strong>Heard from:</strong> ${escape(answers.heard)}</span>` : ""}</p>` : ""}
        <div class="request__buttons">
          <button type="button" class="button button--small" data-decide="declined">Decline</button>
          <button type="button" class="button button--small button--primary" data-decide="approved">Approve</button>
        </div>
      </article>`;
  }

  /* ── people ────────────────────────────────────────────── */

  const STATUS_WORDS = { approved: "Approved", declined: "Declined", suspended: "Suspended",
                         pending: "Waiting" };

  function personRow(person) {
    const admin = person.role === "admin";
    const r = person.range || {};
    return `
      <div class="row personrow${person.email === focusEmail ? " person--focus" : ""}" data-email="${escape(person.email)}">
        <span class="avatar" data-avatar data-picture="${escape(person.picture || "")}" data-initial="${escape(person.name || person.email)}"></span>
        <span class="row__label">${escape(person.name || person.email)}</span>
        <span class="row__value personrow__meta">
          <span>${escape(person.email)}</span>
          <span class="pill pill--${admin ? "admin" : escape(person.status)}">${admin ? "Admin" : STATUS_WORDS[person.status] || escape(person.status)}</span>
          <span>seen ${escape(ago(person.last_seen))}</span>
          <span>${r.clips || 0} clips${r.failures ? `, ${r.failures} failed` : ""}</span>
        </span>
        ${admin ? "" : `<button type="button" class="row__action iconbutton" data-menu aria-haspopup="menu"
            aria-expanded="false" aria-label="More for ${escape(person.name || person.email)}">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm0 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm0 6a2 2 0 1 0 0 4 2 2 0 0 0 0-4z"/></svg>
        </button>`}
      </div>`;
  }

  function paintAvatars(scope) {
    if (!UI) return;
    scope.querySelectorAll("[data-avatar]").forEach((e) => UI.avatar(e, e.dataset.picture, e.dataset.initial));
  }

  function paintPeople() {
    const words = ($("people-search").value || "").trim().toLowerCase();
    const others = people.filter((p) => p.status !== "pending");
    const shown = others.filter((p) => (filter === "all" || p.status === filter)
      && (!words || `${p.name} ${p.email}`.toLowerCase().includes(words)));
    $("n-people").textContent = others.length;
    $("people").innerHTML = shown.map(personRow).join("")
      || `<div class="row"><span class="muted">${others.length ? "Nobody matches." : "Nobody yet."}</span></div>`;
    paintAvatars($("people"));
  }

  $("people-search").addEventListener("input", paintPeople);
  document.querySelectorAll("#people-filter [data-filter]").forEach((chip) => {
    chip.addEventListener("click", () => {
      filter = chip.dataset.filter;
      document.querySelectorAll("#people-filter [data-filter]").forEach((c) =>
        c.setAttribute("aria-pressed", String(c === chip)));
      paintPeople();
    });
  });

  // The ⋯ menu: what can be done to this person, by where they stand.
  function closeMenus() {
    document.querySelectorAll(".menu").forEach((menu) => menu.remove());
    document.querySelectorAll("[data-menu][aria-expanded='true']").forEach((b) => b.setAttribute("aria-expanded", "false"));
  }
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".menu") && !event.target.closest("[data-menu]")) closeMenus();
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeMenus(); });

  $("people").addEventListener("click", (event) => {
    const button = event.target.closest("[data-menu]");
    if (!button) return;
    const row = button.closest(".personrow");
    const open = button.getAttribute("aria-expanded") === "true";
    closeMenus();
    if (open) return;
    const person = people.find((p) => p.email === row.dataset.email);
    const choices = person.status === "approved"
      ? [["suspended", "Suspend"]] : [["approved", person.status === "declined" ? "Approve after all" : "Let back in"]];
    const menu = document.createElement("div");
    menu.className = "menu";
    menu.setAttribute("role", "menu");
    menu.innerHTML = choices.map(([status, label]) =>
      `<button type="button" role="menuitem" data-status="${status}">${label}</button>`).join("")
      + '<button type="button" role="menuitem" class="menu__danger" data-forget="1">Delete account</button>';
    row.append(menu);
    button.setAttribute("aria-expanded", "true");
    menu.querySelector("button").focus();
    menu.addEventListener("click", (choice) => {
      const item = choice.target.closest("button");
      if (!item) return;
      closeMenus();
      if (item.dataset.forget) return confirmForget(row, person);
      return decide(person, item.dataset.status, null);
    });
  });

  function confirmForget(row, person) {
    const box = document.createElement("div");
    box.className = "row__edit";
    box.innerHTML = `<p>Delete ${escape(person.name || person.email)}, their clips, history and keys? This cannot be undone.</p>
      <div class="row__buttons"><button type="button" class="button button--small" data-no>Keep</button>
      <button type="button" class="button button--small button--danger" data-yes>Delete</button></div>`;
    row.classList.add("row--editing");
    row.append(box);
    box.querySelector("[data-no]").focus();
    box.querySelector("[data-no]").addEventListener("click", () => { box.remove(); row.classList.remove("row--editing"); });
    box.querySelector("[data-yes]").addEventListener("click", async (event) => {
      const button = event.currentTarget;
      busy(button, "Deleting");
      try {
        await api("/api/admin/forget", { email: person.email });
        say(`${person.name || person.email} deleted`);
        load(true);
      } catch (error) {
        idle(button);
        say(error.message, { tone: "error" });
      }
    });
  }

  function welcome(person) {
    const site = SITE && SITE !== "this site" ? SITE : location.origin;
    return `Hello ${person.name || ""},\n\nYou are in. Sign in to SnipShare at ${site}/signin `
      + `with your Google account (${person.email}).\n\nMaking a clip needs Google Chrome on a `
      + `computer with the SnipShare extension: ${site}/install\n\nYou can make ${clipsPerDay} clips a day.`;
  }

  async function copyWelcome(person) {
    try {
      await navigator.clipboard.writeText(welcome(person));
      say("Message copied. Paste it to them.");
    } catch {
      say("Could not copy here. Their sign-in address is /signin.", { tone: "error" });
    }
  }

  const DONE = { approved: "let in", declined: "declined", suspended: "suspended" };

  async function decide(person, status, button) {
    const before = person.status;
    if (button) busy(button, status === "approved" ? "Approving" : "Declining");
    try {
      const updated = await api("/api/admin/decide", { email: person.email, status });
      const name = person.name || person.email;
      if (status === "approved") {
        say(`${name} ${DONE[status]}`, { action: { label: "Copy message", run: () => copyWelcome(updated) }, timeout: 9000 });
      } else if (before !== "pending") {
        say(`${name} ${DONE[status]}`, { action: { label: "Undo", run: () => decide({ ...person, status }, before, null) } });
      } else {
        say(`${name} ${DONE[status]}`);
      }
      load(true);
    } catch (error) {
      if (button) idle(button);
      say(error.message, { tone: "error" });
    }
  }

  $("pending").addEventListener("click", (event) => {
    const button = event.target.closest("[data-decide]");
    if (!button) return;
    const person = people.find((p) => p.email === button.closest("[data-email]").dataset.email);
    decide(person, button.dataset.decide, button);
  });

  /* ── adding someone ────────────────────────────────────── */

  function addOpen(on) {
    $("add").hidden = !on;
    $("add-open").hidden = on;
    $("add-error").hidden = true;
    if (on) $("add-email").focus();
    else { $("add").reset(); $("add-open").focus(); }
  }
  $("add-open").addEventListener("click", () => addOpen(true));
  $("add-cancel").addEventListener("click", () => addOpen(false));
  $("add").addEventListener("keydown", (event) => { if (event.key === "Escape") addOpen(false); });
  $("add").addEventListener("submit", async (event) => {
    event.preventDefault();
    const email = $("add-email").value.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      $("add-error").textContent = "That does not look like an email address.";
      $("add-error").hidden = false;
      return $("add-email").focus();
    }
    const button = $("add-save");
    busy(button, "Adding");
    try {
      const person = await api("/api/admin/add", { email, name: $("add-name").value });
      addOpen(false);
      say(`${email} can sign in now`, { action: { label: "Copy message", run: () => copyWelcome(person) }, timeout: 9000 });
      load(true);
    } catch (failure) {
      $("add-error").textContent = failure.message;
      $("add-error").hidden = false;
    } finally {
      idle(button);
    }
  });

  /* ── everything, for the range ─────────────────────────── */

  /* Only the newest load paints: a refresh that set off before the range changed
     must not land after it and show the old range's numbers under the new chip. */
  let loads = 0;
  let loaded = false;

  async function load(quiet = false) {
    const mine = ++loads;
    if (!quiet) $("range-label").textContent = "Loading...";
    let data;
    try {
      data = await api(`/api/admin${query()}`);
    } catch (error) {
      if (mine !== loads) return undefined;
      $("range-label").textContent = "";
      if (!loaded) {
        // Nothing has ever shown: replace the placeholders with a way out.
        $("stats").innerHTML = `<div class="card empty"><p class="error">${escape(error.message)}</p>
          <button type="button" class="button button--quiet" id="load-again">Try again</button></div>`;
        $("load-again").addEventListener("click", () => load());
        return undefined;
      }
      return say(error.message, { tone: "error" });
    }
    if (mine !== loads) return undefined;
    loaded = true;
    clipsPerDay = data.clips_per_day || clipsPerDay;
    people = data.people;
    $("range-label").textContent = rangeLabel(data.range);
    const t = data.totals;
    $("stats").innerHTML = [
      [t.people, "people active"], [t.clips, "clips made"], [t.failures, "failed"],
      [mb(t.upload_bytes), "uploaded"], [t.new_requests, "new requests"],
    ].map(([value, label]) => `<div class="stat"><b>${escape(value)}</b><span>${escape(label)}</span></div>`).join("");
    const n = data.notifications;
    $("system").textContent = `Now: ${data.renderer.queued} waiting, ${data.renderer.rendering} rendering, `
      + `${data.disk_free_gb} GB free. Mail ${n.mail ? "on" : "off"}, Chat ${n.chat ? "on" : "off"}.`;

    const pending = people.filter((p) => p.status === "pending");
    $("n-pending").textContent = pending.length;
    $("pending").innerHTML = pending.map(requestCard).join("")
      || '<div class="card empty"><p class="muted">Nobody is waiting. New requests arrive by email and in Chat, and appear here.</p></div>';
    paintAvatars($("pending"));
    paintPeople();

    $("usage").innerHTML = data.usage.length ? `<thead><tr><th>Who</th><th class="num">Clips</th>
      <th class="num">Failed</th><th class="num">Uploaded</th><th class="num">Render time</th></tr></thead>
      <tbody>${data.usage.map((row) => `<tr><td>${escape(row.email)}</td><td class="num">${row.clips}</td>
        <td class="num">${row.failures}</td><td class="num">${mb(row.upload_bytes)}</td>
        <td class="num">${Math.round((row.render_seconds || 0) / 60)} min</td></tr>`).join("")}</tbody>`
      : '<tbody><tr><td class="muted">Nobody made a clip in these days.</td></tr></tbody>';

    $("n-reports").textContent = data.reports.length;
    $("reports").innerHTML = data.reports.map((row) => `
      <div class="row">
        <div class="feed__top"><span class="pill${row.source === "feedback" ? " pill--approved" : " pill--suspended"}">${escape(row.source)}</span>
          <span>${escape(row.phase)}${row.code ? ` · ${escape(row.code)}` : ""}</span>
          <span>${escape(when(row.at))}</span>${row.email ? `<span>${escape(row.email)}</span>` : ""}</div>
        ${row.detail ? `<p class="feed__detail">${escape(row.detail)}</p>` : ""}
      </div>`).join("") || '<div class="row"><span class="muted">Nothing reported in these days.</span></div>';

    const focused = document.querySelector(".person--focus");
    if (focused && !quiet) focused.scrollIntoView({ block: "center" });
  }

  /* The minute's refresh repaints the lists, so it waits while somebody is in the
     middle of something there: a menu or a confirmation open, a row being edited,
     a button busy. It catches up on the next minute. */
  const midAction = () => !!document.querySelector(
    "#admin .menu:not([hidden]), #admin .row--editing, #admin [aria-busy='true'], #admin .confirm");

  load();
  setInterval(() => { if (!document.hidden && !midAction()) load(true); }, 60000);
})();
