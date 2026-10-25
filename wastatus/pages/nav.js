/* What every SnipShare page does when something is pressed. A link that leaves
   for another page on this site shows a spinner at once, and if the next page has
   not arrived after a moment, a bar runs across the top of the screen. Coming back
   with the Back button clears both. */
(() => {
  const bar = document.createElement("div");
  bar.className = "navbar-progress";
  bar.setAttribute("aria-hidden", "true");
  document.body.prepend(bar);
  let timer = null;

  function start(link) {
    if (link) {
      link.classList.add("is-loading");
      link.setAttribute("aria-busy", "true");
    }
    clearTimeout(timer);
    // Only when it is slow: a page that arrives at once needs no bar.
    timer = setTimeout(() => bar.classList.add("is-on"), 150);
  }

  function stop() {
    clearTimeout(timer);
    bar.classList.remove("is-on");
    document.querySelectorAll("a.is-loading").forEach((link) => {
      link.classList.remove("is-loading");
      link.removeAttribute("aria-busy");
    });
  }

  document.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey
        || event.shiftKey || event.altKey) return;
    const link = event.target.closest("a[href]");
    if (!link || link.target || link.hasAttribute("download")) return;
    let url;
    try { url = new URL(link.href, location.href); } catch { return; }
    if (url.origin !== location.origin) return;
    // A section of this same page, or a file to save, is not a page load.
    if (url.pathname === location.pathname && url.search === location.search) return;
    if (/\/api\/|\.zip$/.test(url.pathname)) return;
    start(link);
  });

  window.addEventListener("pageshow", stop);

  /* ── a short message at the foot of the screen ─────────────── */

  const toaster = document.createElement("div");
  toaster.className = "snackbar";
  toaster.setAttribute("role", "status");
  toaster.setAttribute("aria-live", "polite");
  toaster.hidden = true;
  document.body.append(toaster);
  let toastTimer = null;
  let toastLeft = 0;
  let toastSince = 0;

  // Held open while the pointer or the keyboard is on it, so an Undo can always be
  // reached in time (WCAG 2.2.1), and counted on from where it was when let go.
  const hold = () => {
    if (toaster.hidden || !toastTimer) return;
    clearTimeout(toastTimer);
    toastTimer = null;
    toastLeft = Math.max(1500, toastLeft - (Date.now() - toastSince));
  };
  const release = () => {
    if (toaster.hidden || toastTimer || toaster.matches(":hover, :focus-within")) return;
    toastSince = Date.now();
    toastTimer = setTimeout(() => { toaster.hidden = true; toastTimer = null; }, toastLeft);
  };
  toaster.addEventListener("mouseenter", hold);
  toaster.addEventListener("focusin", hold);
  toaster.addEventListener("mouseleave", release);
  toaster.addEventListener("focusout", () => setTimeout(release, 0));

  // `action` is {label, run}: one thing the person may want to do about it. Alt+U
  // presses it from anywhere on the page while it shows.
  document.addEventListener("keydown", (event) => {
    if (!event.altKey || event.key.toLowerCase() !== "u" || toaster.hidden) return;
    const button = toaster.querySelector(".snackbar__action");
    if (button) { event.preventDefault(); button.click(); }
  });

  function toast(text, { action = null, tone = "", timeout = 5000 } = {}) {
    clearTimeout(toastTimer);
    // An action needs time to be read and reached, not only to be seen.
    if (action) timeout = Math.max(timeout, 10000);
    toaster.className = `snackbar${tone ? ` snackbar--${tone}` : ""}`;
    toaster.textContent = "";
    const words = document.createElement("span");
    words.textContent = text;
    toaster.append(words);
    if (action) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "snackbar__action";
      button.textContent = action.label;
      button.setAttribute("aria-keyshortcuts", "Alt+U");
      button.title = `${action.label} (Alt+U)`;
      button.addEventListener("click", () => {
        toaster.hidden = true;
        clearTimeout(toastTimer);
        toastTimer = null;
        action.run();
      });
      toaster.append(button);
    }
    toaster.hidden = false;
    toastLeft = timeout;
    toastSince = Date.now();
    toastTimer = setTimeout(() => { toaster.hidden = true; toastTimer = null; }, timeout);
  }

  /* ── light, dark, or the system's ──────────────────────────── */

  const THEME_KEY = "wastatus.theme";   // the tool page writes the same key
  const THEMES = ["system", "light", "dark"];

  function theme() {
    try {
      const stored = localStorage.getItem(THEME_KEY);
      return THEMES.includes(stored) ? stored : "system";
    } catch { return "system"; }
  }

  function setTheme(next) {
    if (next === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = next;
    try {
      if (next === "system") localStorage.removeItem(THEME_KEY);
      else localStorage.setItem(THEME_KEY, next);
    } catch { /* private mode: it still applies to this page */ }
    paintToggles();
    document.dispatchEvent(new CustomEvent("snipshare:theme", { detail: next }));
  }

  function paintToggles() {
    const now = theme();
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.dataset.now = now;
      const label = `Theme: ${now}. Press for ${THEMES[(THEMES.indexOf(now) + 1) % 3]}`;
      button.setAttribute("aria-label", label);
      button.title = label;
    });
  }


  /* ── a person's photo, or their initial ────────────────────── */

  function avatar(element, picture, name) {
    element.textContent = "";
    const initial = (name || "?").trim().charAt(0).toUpperCase() || "?";
    if (picture) {
      const image = document.createElement("img");
      image.alt = "";
      image.referrerPolicy = "no-referrer";
      image.src = picture;
      // A photo Google no longer serves falls back to the initial.
      image.addEventListener("error", () => { element.textContent = initial; });
      element.append(image);
    } else {
      element.textContent = initial;
    }
  }
  // Loaded at the top of the page, so the page's own scripts can use it; the parts
  // of the page it dresses are wired once they exist.
  function wire() {
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.addEventListener("click", () => setTheme(THEMES[(THEMES.indexOf(theme()) + 1) % 3]));
    });
    paintToggles();
    document.querySelectorAll("[data-avatar]").forEach((element) =>
      avatar(element, element.dataset.picture, element.dataset.initial));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire);
  else wire();

  window.SnipShareUI = { start, stop, toast, theme, setTheme, avatar };
  window.SnipShareLoading = { start, stop };
})();
