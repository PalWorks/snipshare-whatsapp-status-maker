// WhatsApp Web's page world, injected only when someone presses "Load into
// WhatsApp". Puts the clip into the Status composer and types the caption. Never
// presses Send: the person looks, then sends. The same steps wastatus/post.py takes
// over the DevTools protocol, with nothing an extension does not have: the file
// input WhatsApp clicks is caught and filled, and the caption goes in through the
// editor's own input handling. See DECISIONS.md D-084.
(() => {
  "use strict";
  if (window.__wastatusWhatsApp1) return;
  window.__wastatusWhatsApp1 = true;

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

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
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

  async function load(bytes, name, caption) {
    if (!document.querySelector('button[aria-label="Status"]') && !document.querySelector("#pane-side")) {
      return { ok: false, error: "WhatsApp Web is not signed in. Scan the QR code in that tab, then try again" };
    }
    if (document.querySelector(COMPOSER_OPEN)) {
      return { ok: false, error: "A Status is already open in WhatsApp. Close it or send it, then try again" };
    }
    const file = new File([bytes], name, { type: "video/mp4", lastModified: Date.now() });

    const status = document.querySelector('button[aria-label="Status"]');
    if (status && status.getAttribute("aria-pressed") !== "true") status.click();
    await sleep(800);
    let item = hunt(PHOTO_ITEM);
    if (!item) {
      const add = hunt(ADD_STATUS);
      if (add) press(add);
      await sleep(800);
      item = hunt(PHOTO_ITEM);
    }
    if (!item) {
      return { ok: false, error: `WhatsApp has moved its "Photos & videos" choice. Its menu offers: ${offered().join(", ") || "nothing"}` };
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
      press(item);
      for (let i = 0; i < 30 && !caught; i++) await sleep(100);
    } finally {
      proto.click = click;
      if (showPicker) proto.showPicker = showPicker;
      document.removeEventListener("click", onClick, true);
    }
    if (!caught) caught = document.querySelector('input[type=file][accept*="video"]');
    if (!caught) return { ok: false, error: "WhatsApp did not offer a place to put the video" };

    const transfer = new DataTransfer();
    transfer.items.add(file);
    caught.files = transfer.files;
    caught.dispatchEvent(new Event("input", { bubbles: true }));
    caught.dispatchEvent(new Event("change", { bubbles: true }));

    const until = Date.now() + COMPOSER_TIMEOUT;
    while (!(document.querySelector(CAPTION) && document.querySelector(SEND))) {
      if (Date.now() > until) {
        return { ok: false, error: "WhatsApp took the video but never opened its editor. It may be too large" };
      }
      await sleep(300);
    }
    const box = document.querySelector(CAPTION);
    if (caption) {
      box.focus();
      // insertText goes through the editor's own input handling, so a newline in a
      // caption cannot submit the composer the way a synthesised Enter would.
      document.execCommand("insertText", false, caption);
      await sleep(500);
    }
    return { ok: true, caption: box.textContent };
  }

  window.addEventListener("message", async (event) => {
    if (event.source !== window || event.data?.wastatus !== "wa-load") return;
    const { id, buffer, name, caption } = event.data;
    let result;
    try {
      result = await load(new Uint8Array(buffer), String(name), String(caption || ""));
    } catch (err) {
      result = { ok: false, error: String(err && err.message || err) };
    }
    window.postMessage({ wastatus: "wa-result", id, result }, location.origin);
  });
})();
