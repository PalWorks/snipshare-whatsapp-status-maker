// YouTube's isolated world. Carries requests from the service worker to
// recorder.js in the page, and the answers back: progress, then the captured files
// in slices, base64 encoded because an extension port carries text. Holds nothing.
//
// The two talk over a MessageChannel handed to the page world here, at
// document_start, before any of YouTube's own scripts exist: a window message
// would be visible to every script on the page, and any of them could answer it.
(() => {
  "use strict";
  if (window.__wastatusBridge) return;
  window.__wastatusBridge = true;

  const channel = new MessageChannel();
  const page = channel.port1;
  window.postMessage({ wastatus: "bridge-port" }, location.origin, [channel.port2]);

  const waiting = new Map(); // request id -> the service worker's port

  function base64(bytes) {
    let text = "";
    for (let at = 0; at < bytes.length; at += 0x8000) {
      text += String.fromCharCode.apply(null, bytes.subarray(at, at + 0x8000));
    }
    return btoa(text);
  }

  chrome.runtime.onConnect.addListener((port) => {
    if (port.name !== "wastatus-tab") return;
    const mine = new Set();
    port.onMessage.addListener((message) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      waiting.set(id, port);
      mine.add(id);
      page.postMessage({ ...message, id });
    });
    // The worker went away, or stopped this clip: the page stops the walk too, and
    // puts the viewer back, rather than seeking their player for two more minutes.
    port.onDisconnect.addListener(() => {
      for (const id of mine) {
        if (waiting.delete(id)) page.postMessage({ cmd: "cancel", target: id });
      }
    });
  });

  page.onmessage = (event) => {
    const { id, ...body } = event.data || {};
    const port = waiting.get(id);
    if (!port) return;
    if (body.chunk) {
      body.chunk = { kind: body.chunk.kind, at: body.chunk.at,
                     b64: base64(new Uint8Array(body.chunk.bytes)) };
    }
    try {
      port.postMessage(body);
    } catch {
      waiting.delete(id);
      page.postMessage({ cmd: "cancel", target: id });
      return;
    }
    if (body.done || body.error || body.info) waiting.delete(id);
  };
})();
