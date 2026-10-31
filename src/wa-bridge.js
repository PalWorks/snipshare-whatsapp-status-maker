// WhatsApp Web's isolated world, injected beside whatsapp.js. Receives the clip
// from the service worker in base64 slices, puts it back together, and hands it to
// the page world in one transfer; then carries the steps and the answer back.
//
// Each slice is acknowledged (`{ack: n}`) and the worker sends the next only then,
// so the worker holds one slice at a time rather than the whole clip in messages
// queued behind each other (docs/scheduling.md, Table SC-R2 E7). The slices are
// written straight into one buffer of the announced size, so this world never holds
// the clip twice, and the buffer is transferred, not copied, to the page.
//
// The worker keeps time: its `tick` is relayed to the page world, where it makes
// every open wait look again even when the page is hidden and its timers are held
// back (whatsapp.js).
(() => {
  "use strict";
  // An extension that was reloaded or updated leaves this world's earlier copy
  // behind with a dead connection to it. That copy is replaced; a live copy of this
  // version is kept, because two would answer the same port.
  const VERSION = 2;
  const MAX_BYTES = 128 * 1024 * 1024; // far above WhatsApp's 10 MiB; refuses a nonsense size
  const prior = window.__wastatusWaBridge;
  const alive = (copy) => { try { return !!copy.alive(); } catch { return false; } };
  if (prior && prior.version === VERSION && alive(prior)) return;
  if (prior && typeof prior.stop === "function") {
    try { prior.stop(); } catch { /* its runtime is gone, and its listener with it */ }
  }
  const runtime = chrome.runtime;

  function serve(port) {
    if (port.name !== "wastatus-wa") return;
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    let whole = null;
    let meta = null;
    let at = 0;
    let gone = false;

    const reply = (message) => { try { port.postMessage(message); } catch { /* the worker went */ } };
    const toPage = (message, transfer) => window.postMessage({ ...message, id }, location.origin, transfer || []);
    const incomplete = () => {
      whole = null;
      reply({ result: { ok: false, code: "failed", error: "The clip arrived incomplete. Try again" } });
    };

    const fromPage = (event) => {
      if (event.source !== window || !event.data || event.data.id !== id) return;
      if (event.data.wastatus === "wa-step") {
        reply({ step: String(event.data.step) });
      } else if (event.data.wastatus === "wa-result") {
        window.removeEventListener("message", fromPage);
        reply({ result: event.data.result });
      }
    };
    window.addEventListener("message", fromPage);

    port.onMessage.addListener((message) => {
      if (gone || !message) return;
      if (message.cmd === "tick") {
        toPage({ wastatus: "wa-tick" });
      } else if (message.cmd === "start") {
        const size = message.size;
        if (!Number.isSafeInteger(size) || size <= 0 || size > MAX_BYTES) { incomplete(); return; }
        meta = { name: String(message.name || "clip.mp4"), caption: String(message.caption || "") };
        whole = new Uint8Array(size);
        at = 0;
      } else if (message.cmd === "chunk") {
        if (!whole) return;
        const text = atob(message.b64);
        if (at + text.length > whole.length) { incomplete(); return; }
        for (let i = 0; i < text.length; i++) whole[at + i] = text.charCodeAt(i);
        at += text.length;
        reply({ ack: message.n });
      } else if (message.cmd === "end") {
        if (!whole || !meta || at !== whole.length) { incomplete(); return; }
        const buffer = whole.buffer;
        whole = null;
        toPage({ wastatus: "wa-run", buffer, name: meta.name, caption: meta.caption }, [buffer]);
      }
    });
    // The worker let go (its limit, Stop, or it was stopped by Chrome): the page
    // stops waiting, so a composer half way through loading is let go too.
    port.onDisconnect.addListener(() => {
      gone = true;
      whole = null;
      window.removeEventListener("message", fromPage);
      toPage({ wastatus: "wa-stop" });
    });
  }

  runtime.onConnect.addListener(serve);
  window.__wastatusWaBridge = {
    version: VERSION,
    // A content script whose extension was reloaded keeps running, but its
    // runtime no longer has an id.
    alive: () => !!runtime.id,
    stop: () => runtime.onConnect.removeListener(serve),
  };
})();
