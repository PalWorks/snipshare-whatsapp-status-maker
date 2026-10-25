// WhatsApp Web's isolated world, injected beside whatsapp.js. Receives the clip
// from the service worker in base64 slices, puts it back together, and hands it to
// the page world in one transfer; then carries the answer back.
(() => {
  "use strict";
  if (window.__wastatusWaBridge1) return;
  window.__wastatusWaBridge1 = true;

  chrome.runtime.onConnect.addListener((port) => {
    if (port.name !== "wastatus-wa") return;
    let parts = [];
    let meta = null;
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;

    const onResult = (event) => {
      if (event.source !== window || event.data?.wastatus !== "wa-result" || event.data.id !== id) return;
      window.removeEventListener("message", onResult);
      try { port.postMessage({ result: event.data.result }); } catch { /* popup gone */ }
    };

    port.onMessage.addListener((message) => {
      if (message.cmd === "start") {
        meta = message;
        parts = [];
      } else if (message.cmd === "chunk") {
        const text = atob(message.b64);
        const bytes = new Uint8Array(text.length);
        for (let i = 0; i < text.length; i++) bytes[i] = text.charCodeAt(i);
        parts.push(bytes);
      } else if (message.cmd === "end" && meta) {
        const total = parts.reduce((n, p) => n + p.length, 0);
        if (total !== meta.size) {
          port.postMessage({ result: { ok: false, error: "The clip arrived incomplete. Try again" } });
          return;
        }
        const whole = new Uint8Array(total);
        let at = 0;
        for (const part of parts) { whole.set(part, at); at += part.length; }
        parts = [];
        window.addEventListener("message", onResult);
        window.postMessage({ wastatus: "wa-load", id, buffer: whole.buffer, name: meta.name,
                             caption: meta.caption }, location.origin, [whole.buffer]);
      }
    });
    port.onDisconnect.addListener(() => window.removeEventListener("message", onResult));
  });
})();
