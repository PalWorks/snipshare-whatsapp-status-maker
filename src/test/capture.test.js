// Which YouTube tab a capture reads from. A tab that was open before the extension was
// installed or reloaded has no recorder and never answers; bringing it forward to wait
// on it left the page stuck at "Getting the video" (2026-10-31). Run with
// `node --test src/test/*.test.js`.
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

// The worker in a sandbox, with tabs that answer (or not) as each test says.
function worker(tabs, answers) {
  const on = () => ({ addListener: () => {} });
  const local = { get: async () => ({}), set: async () => {}, remove: async () => {} };
  const connected = [];
  const chrome = {
    storage: { local, session: local, onChanged: on() },
    alarms: { onAlarm: on(), get: async () => null, create: async () => {}, clear: async () => true },
    runtime: {
      onInstalled: on(), onStartup: on(), onConnect: on(), onConnectExternal: on(), onMessage: on(),
      id: "ext", getManifest: () => ({ version: "2.1.0" }), getURL: (p) => `chrome-extension://ext/${p}`,
    },
    action: { onClicked: on(), setBadgeText: async () => {}, setBadgeBackgroundColor: async () => {} },
    notifications: { onClicked: on(), onButtonClicked: on() },
    contextMenus: { onClicked: on(), removeAll: (cb) => cb(), create: () => {} },
    tabs: {
      query: async () => tabs,
      connect: (tabId) => {
        connected.push(tabId);
        const message = [];
        const gone = [];
        return {
          onMessage: { addListener: (fn) => message.push(fn) },
          onDisconnect: { addListener: (fn) => gone.push(fn) },
          disconnect: () => {},
          postMessage: () => setTimeout(() => {
            const info = answers[tabId];
            if (info) message.forEach((fn) => fn({ info }));
            else gone.forEach((fn) => fn());   // no content script in that tab
          }, 0),
        };
      },
    },
  };
  const scheduler = { alarm: async () => {}, wake: async () => {}, attach: () => {}, changed: async () => {},
                      clicked: async () => {}, button: async () => {} };
  const sandbox = {
    chrome, console, setTimeout, clearTimeout, AbortController, AbortSignal, URL, Blob,
    importScripts: () => {
      sandbox.CONFIG = { site: "http://127.0.0.1:8790" };
      sandbox.SnipQueue = { nextWake: () => null };
      sandbox.SnipCustody = { PREFIX: "sched:", make: () => ({}) };
      sandbox.SnipPlace = {};
      sandbox.SnipSchedule = { make: () => scheduler, Refusal: class extends Error {} };
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "sw.js"), "utf8"), sandbox, { filename: "sw.js" });
  return { sandbox, connected };
}

const ID = "0HO4KaRF5KI";
const watch = (id, v = ID, extra = {}) => ({ id, url: `https://www.youtube.com/watch?v=${v}`, ...extra });

test("a tab showing the video that does not answer is never chosen, so it is never brought forward", async () => {
  const { sandbox } = worker([watch(7)], {});
  assert.equal(await sandbox.videoTab(ID), null);
});

test("a tab whose player is not ready is not chosen either", async () => {
  const { sandbox } = worker([watch(7)], { 7: { ready: false, videoId: ID } });
  assert.equal(await sandbox.videoTab(ID), null);
});

test("a ready tab is chosen, with what it said, past a silent one for the same video", async () => {
  const { sandbox } = worker([watch(7), watch(9)], { 9: { ready: true, videoId: ID, title: "t" } });
  const found = await sandbox.videoTab(ID);
  assert.equal(found.tab.id, 9);
  assert.equal(found.info.title, "t");
});

test("tabs of other videos and discarded tabs are not asked at all", async () => {
  const { sandbox, connected } = worker(
    [watch(3, "aaaaaaaaaaa"), watch(4, ID, { discarded: true })],
    { 3: { ready: true, videoId: "aaaaaaaaaaa" }, 4: { ready: true, videoId: ID } });
  assert.equal(await sandbox.videoTab(ID), null);
  assert.deepEqual(connected, []);
});
