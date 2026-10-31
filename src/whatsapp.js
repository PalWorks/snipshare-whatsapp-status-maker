// WhatsApp Web's page world, injected when someone presses "Load into WhatsApp" or
// when a scheduled Status is prepared. Puts the clip into the Status composer and
// types the caption. Never presses Send: the person looks, then sends. The same
// steps wastatus/post.py takes over the DevTools protocol, with nothing an extension
// does not have: the file input WhatsApp clicks is caught and filled, and the
// caption goes in through the editor's own input handling. See DECISIONS.md D-084.
//
// A scheduled run may find this page hidden, where Chrome runs a chain of timers at
// most once a second and, after five minutes hidden, as rarely as once a minute
// [Inference from Chrome's documented intensive throttling; consistent with D-084,
// not measured here]. So nothing here waits on a timer: every wait is `waitFor`,
// which re-checks when the page changes (a MutationObserver) and on every `tick` the
// service worker sends through wa-bridge.js twice a second. A message is a task, not
// a timer [Inference, to be measured in Phase 0 of docs/scheduling.md]. The worker
// holds the overall limit; the limits here are WhatsApp's own steps, measured by the
// clock whenever a check runs.
(() => {
  "use strict";
  // A copy of this version already listening is enough: a second listener would
  // put the clip in twice. An older copy (a reloaded or updated extension leaves
  // its page world script behind) is told to stop, and this one takes over.
  const VERSION = 2;
  const prior = window.__wastatusWhatsApp;
  if (prior && prior.version === VERSION) return;
  if (prior && typeof prior.stop === "function") {
    try { prior.stop(); } catch { /* an old copy that cannot stop is inert: it listens for other names */ }
  }

  // Kept in step with wastatus/post.py, which has the history of each one.
  const ADD_STATUS = ["Add Status", "Add status", "New status"];
  const PHOTO_ITEM = ["Photos & videos", "Photo and video", "Photos and videos",
    "Photo & video", "Photos, videos"];
  const SEND = '[data-icon^="wds-ic-send"],[aria-label^="Send "][aria-label$=" selected"],[aria-label="Send"]';
  const COMPOSER_OPEN = '[data-icon^="wds-ic-send"],[aria-label^="Send "][aria-label$=" selected"],' +
    '[aria-label="Close status posting view"]';
  const CAPTION = '[data-testid="media-caption-input-container"][contenteditable="true"],' +
    'div[contenteditable="true"][aria-placeholder="Add a caption"]';
  const COMPOSER_TIMEOUT = 75000;
  const STEP_TIMEOUT = 10000;    // a menu or a button WhatsApp shows after a press
  const PICKER_TIMEOUT = 3000;   // WhatsApp clicking its file input after the menu item
  const CAPTION_TIMEOUT = 3000;  // the editor showing the caption it was given
  // Hunting a label walks much of the page, and WhatsApp's page changes many times
  // a second, so a change re-checks at most this often; a tick always checks.
  const CHECK_GAP = 150;
  const WATCHED = ["aria-label", "aria-pressed", "aria-placeholder", "contenteditable",
    "data-icon", "data-testid", "role"];

  const canon = (s) => [...new Set((s || "").toLowerCase().split(/[^a-z0-9]+/)
    .filter((w) => w && w !== "and")
    .map((w) => (w.length > 3 && w.endsWith("s")) ? w.slice(0, -1) : w))].sort().join(" ");
  const hunt = (labels) => {
    const want = new Set(labels.map(canon));
    const find = (sel) => [...document.querySelectorAll(sel)].find((e) =>
      want.has(canon(e.getAttribute("aria-label"))) || want.has(canon(e.textContent)));
    return find("[role=menuitem]") || find("div[role=button],button,li,span,div");
  };
  const press = (el) => (el.closest("[role=menuitem],div[role=button],button,li") || el).click();
  const offered = () => [...document.querySelectorAll("[role=menuitem]")]
    .map((e) => (e.getAttribute("aria-label") || e.textContent || "").trim()).filter(Boolean);
  const signedIn = () => !!document.querySelector('button[aria-label="Status"]') || !!document.querySelector("#pane-side");
  const fail = (code, error) => ({ ok: false, code, error });

  class Stopped extends Error {}

  // One run per port. `poke` re-checks every wait the run has open.
  const runs = new Map();
  function newRun(id) {
    const run = { id, stopped: false, checks: new Set() };
    run.poke = () => { for (const check of [...run.checks]) check(true); };
    runs.set(id, run);
    return run;
  }

  // Resolves with the first truthy value of `test`, or null once `limit` has passed.
  // Checked now, on every change to the page, and on every tick; the one timer is a
  // spare for a page that is in front, where timers do run.
  function waitFor(run, test, limit) {
    return new Promise((resolve, reject) => {
      const start = Date.now();
      let done = false;
      let last = 0;
      let spare = null;
      const observer = new MutationObserver(() => check(false));
      const finish = (error, value) => {
        done = true;
        observer.disconnect();
        run.checks.delete(check);
        clearTimeout(spare);
        if (error) reject(error);
        else resolve(value);
      };
      function check(always) {
        if (done) return;
        if (run.stopped) { finish(new Stopped("Stopped")); return; }
        const now = Date.now();
        if (!always && now - last < CHECK_GAP) return;
        last = now;
        let value = null;
        try { value = test(); } catch { value = null; }
        if (value) finish(null, value);
        else if (now - start >= limit) finish(null, null);
      }
      run.checks.add(check);
      observer.observe(document.documentElement, { subtree: true, childList: true,
                                                    attributes: true, attributeFilter: WATCHED });
      spare = setTimeout(() => check(true), limit + 50);
      check(true);
    });
  }

  function step(run, name) {
    window.postMessage({ wastatus: "wa-step", id: run.id, step: name }, location.origin);
  }

  async function load(run, buffer, name, caption) {
    if (!signedIn()) {
      return fail("signed-out", "WhatsApp Web is not signed in. Scan the QR code in that tab, then try again");
    }
    if (document.querySelector(COMPOSER_OPEN)) {
      return fail("composer-open", "A Status is already open in WhatsApp. Close it or send it, then try again");
    }
    // The File takes its own copy; the buffer is let go here so the clip is not
    // held twice in this page for the length of the run.
    const file = new File([buffer], name, { type: "video/mp4", lastModified: Date.now() });
    buffer = null;

    step(run, "status");
    const status = document.querySelector('button[aria-label="Status"]');
    if (status && status.getAttribute("aria-pressed") !== "true") status.click();
    const first = await waitFor(run, () => hunt(PHOTO_ITEM) ? "photo" : hunt(ADD_STATUS) ? "add" : null,
                                STEP_TIMEOUT);
    let item = first === "photo" ? hunt(PHOTO_ITEM) : null;
    if (!item) {
      const add = hunt(ADD_STATUS);
      if (add) press(add);
      item = await waitFor(run, () => hunt(PHOTO_ITEM), STEP_TIMEOUT);
    }
    if (!item) {
      return fail("moved", `WhatsApp has moved its "Photos & videos" choice. Its menu offers: ${offered().join(", ") || "nothing"}`);
    }

    // WhatsApp opens the file picker from its own click handler. Catch the input it
    // clicks, keep the picker shut, and fill the input ourselves. Two nets: the
    // prototype for a scripted .click(), and a capturing listener for a label's.
    let caught = null;
    const proto = HTMLInputElement.prototype;
    const click = proto.click;
    const showPicker = proto.showPicker;
    proto.click = function () {
      if (this.type === "file") { caught = this; return undefined; }
      return click.call(this);
    };
    if (showPicker) {
      proto.showPicker = function () {
        if (this.type === "file") { caught = this; return undefined; }
        return showPicker.call(this);
      };
    }
    const onClick = (event) => {
      if (event.target instanceof HTMLInputElement && event.target.type === "file") {
        caught = event.target;
        event.preventDefault();
      }
    };
    document.addEventListener("click", onClick, true);
    try {
      step(run, "menu");
      press(item);
      await waitFor(run, () => caught, PICKER_TIMEOUT);
    } finally {
      proto.click = click;
      if (showPicker) proto.showPicker = showPicker;
      document.removeEventListener("click", onClick, true);
    }
    if (!caught) caught = document.querySelector('input[type=file][accept*="video"]');
    if (!caught) return fail("moved", "WhatsApp did not offer a place to put the video");

    const transfer = new DataTransfer();
    transfer.items.add(file);
    caught.files = transfer.files;
    caught.dispatchEvent(new Event("input", { bubbles: true }));
    caught.dispatchEvent(new Event("change", { bubbles: true }));
    // From here a composer may be on its way, so the worker must not try another
    // placement on top of this one.
    step(run, "file");

    const ready = await waitFor(run, () => document.querySelector(CAPTION) && document.querySelector(SEND),
                                COMPOSER_TIMEOUT);
    if (!ready) {
      return fail("timeout", "WhatsApp took the video but never opened its editor. It may be too large");
    }
    step(run, "composer");
    const box = document.querySelector(CAPTION);
    if (caption) {
      box.focus();
      // insertText goes through the editor's own input handling, so a newline in a
      // caption cannot submit the composer the way a synthesised Enter would.
      // [Unverified] that it does so in a page whose window does not have focus;
      // Phase 0 measures it, and the caption read back below shows the result.
      document.execCommand("insertText", false, caption);
      await waitFor(run, () => {
        const now = document.querySelector(CAPTION) || box;
        return now.textContent.trim() ? now : null;
      }, CAPTION_TIMEOUT);
    }
    // What the editor holds, read back, so the caller can see it took.
    return { ok: true, caption: (document.querySelector(CAPTION) || box).textContent };
  }

  async function serve(run, buffer, name, caption) {
    let result;
    try {
      result = await load(run, buffer, name, caption);
    } catch (err) {
      result = err instanceof Stopped ? fail("stopped", "Stopped")
        : fail("failed", String(err && err.message || err));
    } finally {
      runs.delete(run.id);
    }
    window.postMessage({ wastatus: "wa-result", id: run.id, result }, location.origin);
  }

  // Not async itself: the event, and the clip it carries, are let go as soon as the
  // fields are taken out of it.
  const onMessage = (event) => {
    if (event.source !== window || !event.data || typeof event.data !== "object") return;
    const { wastatus, id } = event.data;
    if (wastatus === "wa-tick" || wastatus === "wa-stop") {
      const run = runs.get(id);
      if (!run) return;
      if (wastatus === "wa-stop") run.stopped = true;
      run.poke();
      return;
    }
    // The name differs from the first version's "wa-load", so a copy of that one
    // left in a long-lived tab never answers a run meant for this one.
    if (wastatus !== "wa-run" || runs.has(id)) return;
    serve(newRun(id), event.data.buffer, String(event.data.name), String(event.data.caption || ""));
  };

  window.addEventListener("message", onMessage);
  window.__wastatusWhatsApp = {
    version: VERSION,
    stop() {
      window.removeEventListener("message", onMessage);
      for (const run of runs.values()) { run.stopped = true; run.poke(); }
    },
  };
})();
