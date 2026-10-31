// Placing a clip in WhatsApp Web's Status composer: the one way in, for a person
// pressing Load into WhatsApp and for a scheduled Status alike. Never presses Send.
//
// A press by a person brings WhatsApp to the front, as it always has (D-084). A
// scheduled run must not: it walks a ladder of placements, quietest first, and
// stops at the first that works (docs/scheduling.md, Section 6, Table SC-4):
//
//   S0  WhatsApp's own tab, left where it is, never activated
//   S1  a new background tab in the window the person last used (no tab exists)
//   S2  a small unfocused helper window; an existing tab is moved into it and back,
//       never duplicated, because a second WhatsApp tab raises its "Use here"
//   S3  the front while the person is idle, focus put back (opt in, Section 14 T1)
//   S4  ask: the caller notifies, and a press runs the manual load
//   S5  the front without asking (the setting Bring WhatsApp forward when needed)
//
// Which of S0 to S2 work on a given computer is not known. Phase 0 of the plan, the
// measurements on the owner's Chrome, has not been run. So the order is data: every
// quiet run records how its rung did in `placeStats` and the next run starts at the
// best one (FR-16). The facts the rungs rest on are labelled where they are used.
//
// The focus guard (6.1) watches the focused window and its active tab for the whole
// run; a change that follows one of the run's own calls within 1.5 s is the run's,
// is undone at once and counts against the rung.
//
// Pure parts (`order`, `ladder`, `skipped`, `record`, `judge`, `handover`) need no
// Chrome and are tested in Node; `create(deps)` takes Chrome's APIs as `deps.chrome`
// so the tests can pass fakes. Loaded by sw.js with importScripts, as `SnipPlace`.
(function (root) {
  "use strict";

  const WA_URL = "https://web.whatsapp.com/";
  const WA_MATCH = "https://web.whatsapp.com/*";
  const PORT_NAME = "wastatus-wa";
  const QUIET = ["S0", "S1", "S2"];
  const RUNGS = ["S0", "S1", "S2", "S3", "S4", "S5"];
  const SIGN_IN_MS = 120000;     // WhatsApp Web signing in, or a tab loading, before giving up
  const LOAD_LIMIT_MS = 150000;  // the whole composer load, measured here and not in the page
  const TICK_MS = 500;           // the worker keeps time for a page whose timers are held back
  const SLICE = 512 * 1024;      // one slice of the clip in flight at a time (E7)
  const GUARD_MS = 1500;         // a focus change this soon after our own call is ours (6.1)
  const SETTLE_MS = 300;         // focus events arrive a moment after the call that caused them
  const IDLE_SECONDS = 60;       // chrome.idle's threshold for S3 and for "in use" (FR-12, FR-13)
  const SKIP_AFTER = 3;          // failures in a row before a rung is skipped (FR-16)
  const SKIP_MS = 7 * 86400000;  // and for how long
  const POLL_MS = 1000;          // between looks at a tab that is loading or signing in
  const CALL_MS = 5000;          // a Chrome call into a tab that has not answered by now has hung
  const MAX_UNDOS = 6;           // the guard gives up undoing rather than fight the window manager
  const STATS_KEY = "placeStats";
  // The helper window. [Unverified] that WhatsApp Web lays out usably at this size,
  // and that Linux window managers honour `focused: false` (Phase 0 item 2).
  const HELPER = { width: 760, height: 640, left: 0, top: 0 };
  const NONE = -1;               // chrome.windows.WINDOW_ID_NONE: no Chrome window has focus

  // Placements that fail for a reason of their own are worth trying the next rung
  // for. Everything else ends the walk: signed out, a composer already open, the
  // person using WhatsApp, a selector WhatsApp moved, Stop.
  const NEXT_RUNG = new Set(["timeout", "closed", "failed"]);
  // The failures after which S1 closes the tab it opened (signed out is kept).
  const CLOSE_S1 = new Set(["timeout", "closed", "failed"]);

  const MESSAGES = {
    busy: "WhatsApp is already opening a clip. Wait for it to finish",
    "signed-out": "WhatsApp Web is not signed in. Scan the QR code in that tab, then try again",
    timeout: "WhatsApp took too long to open its editor",
    closed: "The WhatsApp tab was closed or reloaded. Try again",
    stopped: "Stopped",
    "in-use": "You are using WhatsApp, so the Status waits",
    ask: "WhatsApp needs to come to the front to load this Status",
  };
  const failure = (code, error) => ({ ok: false, code, error: error || MESSAGES[code] || "Something went wrong" });

  // -- the record of what works here (pure) ------------------------------------------

  function blank() {
    return { wins: 0, fails: 0, streak: 0, moved: 0, placed: 0, lastWin: null, lastFail: null, ms: null };
  }

  // FR-16: a rung that failed three times running is left alone for a week, then
  // tried again; one more failure then puts it away for another week.
  function skipped(rec, now) {
    return !!rec && rec.streak >= SKIP_AFTER && rec.lastFail != null && now - rec.lastFail < SKIP_MS;
  }

  // The quiet rungs in the order to try them: those that worked last time first,
  // then the untried, then those failing but not yet skipped; the quieter first
  // within each.
  function order(stats, now) {
    const rungs = (stats && stats.rungs) || {};
    const rank = (r) => {
      const rec = rungs[r];
      if (!rec || (!rec.wins && !rec.fails)) return 1;
      return rec.streak === 0 && rec.wins > 0 ? 0 : 2;
    };
    return QUIET.filter((r) => !skipped(rungs[r], now))
      .sort((a, b) => rank(a) - rank(b) || QUIET.indexOf(a) - QUIET.indexOf(b));
  }

  // The whole walk. S3 only when the person opted in (T1); the last step either
  // brings WhatsApp forward (S5, when they said so) or asks (S4), never both.
  function ladder(stats, settings, now) {
    const s = settings || {};
    const steps = order(stats, now);
    if (s.idleForward) steps.push("S3");
    steps.push(s.bringForward ? "S5" : "S4");
    return steps;
  }

  // A new record with one outcome added; `stats` itself is left alone. `quiet` is
  // true when the composer loaded and nothing the person sees moved.
  function record(stats, rung, outcome, now) {
    const next = { ...(stats || {}), rungs: { ...((stats && stats.rungs) || {}) } };
    const rec = { ...blank(), ...(next.rungs[rung] || {}) };
    if (outcome.placedOnly) {
      // A test without a clip shows only whether placing the tab moved anything.
      if (outcome.moved) { rec.fails += 1; rec.streak += 1; rec.moved += 1; rec.lastFail = now; }
      else rec.placed += 1;
    } else if (outcome.ok && outcome.quiet) {
      rec.wins += 1;
      rec.streak = 0;
      rec.lastWin = now;
      const ms = Math.max(0, Math.round(outcome.ms || 0));
      rec.ms = rec.ms == null ? ms : Math.round((rec.ms * 3 + ms) / 4);
    } else {
      rec.fails += 1;
      rec.streak += 1;
      rec.lastFail = now;
      if (outcome.moved) rec.moved += 1;
    }
    next.rungs[rung] = rec;
    next.last = now;
    if (outcome.test) next.tested = now;
    return next;
  }

  // What the queue shows: does quiet posting work here, from which rung, and when
  // it was last tried. `works` is null until a quiet rung has been tried at all.
  function summary(stats, now) {
    const rungs = (stats && stats.rungs) || {};
    const tried = QUIET.filter((r) => rungs[r] && (rungs[r].wins || rungs[r].fails));
    const working = order(stats, now).filter((r) => rungs[r] && rungs[r].wins > 0 && rungs[r].streak === 0);
    return {
      works: working.length ? true : tried.length ? false : null,
      best: working[0] || null,
      tested: (stats && (stats.tested || stats.last)) || null,
    };
  }

  // -- the focus guard's judgement (pure) ----------------------------------------

  // `before` is {windowId, tabId}: the focused window when the run began (NONE if
  // the person was in another application) and its active tab. `events` are
  // {type: "window"|"tab", windowId, tabId?, at}; `calls` are the run's own calls,
  // {start, end} with `end` null while one is still running.
  //
  // An event within GUARD_MS of one of our calls is ours. Only the latest event of
  // each kind matters: if the person moved after us, theirs stands. Returns whether
  // anything we did moved what the person sees, whether the person moved anything,
  // and what to put back.
  function judge(before, events, calls, guardMs) {
    const gap = guardMs == null ? GUARD_MS : guardMs;
    const ours = (e) => calls.some((c) => e.at >= c.start && e.at <= (c.end == null ? Infinity : c.end + gap));
    const changes = (e) => e.type === "window" ? e.windowId !== before.windowId
      : e.windowId === before.windowId && e.tabId !== before.tabId;
    const lastWindow = [...events].reverse().find((e) => e.type === "window");
    const lastTab = [...events].reverse().find((e) => e.type === "tab" && e.windowId === before.windowId);
    const undoWindow = !!lastWindow && ours(lastWindow) && changes(lastWindow);
    const undoTab = !!lastTab && ours(lastTab) && changes(lastTab) && before.tabId != null;
    return {
      moved: events.some((e) => ours(e) && changes(e)),
      person: events.some((e) => !ours(e)),
      undo: undoWindow || undoTab ? {
        windowId: undoWindow ? before.windowId : null,
        // Focus went to this window; with nothing of Chrome's focused before, it is
        // unfocused again rather than another window being raised.
        blur: undoWindow && before.windowId === NONE ? lastWindow.windowId : null,
        tabId: undoTab ? before.tabId : null,
      } : null,
    };
  }

  // -- handing the clip over (pure but for the port) -------------------------------

  function base64(bytes) {
    let text = "";
    for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(text);
  }

  // One slice read from the Blob, sent, and acknowledged before the next is read,
  // so the clip is held once (the Blob, which IndexedDB keeps on disk) plus one
  // slice, never whole in memory and again in queued messages (E7). `waitAck(n)`
  // resolves when the bridge says `{ack: n}` and rejects if the port goes.
  async function handover(port, clip, meta, waitAck, halted) {
    port.postMessage({ cmd: "start", name: meta.name, size: clip.size, caption: meta.caption });
    for (let n = 0, at = 0; at < clip.size; n += 1, at += SLICE) {
      if (halted && halted()) return false;
      const bytes = new Uint8Array(await clip.slice(at, Math.min(at + SLICE, clip.size)).arrayBuffer());
      const acked = waitAck(n);
      port.postMessage({ cmd: "chunk", n, b64: base64(bytes) });
      await acked;
    }
    port.postMessage({ cmd: "end" });
    return true;
  }

  // -- one at a time ------------------------------------------------------------------

  // Two loads would fight over the same composer, whoever asked for them.
  function makeLock() {
    let held = false;
    return {
      take() { if (held) return false; held = true; return true; },
      free() { held = false; },
      held() { return held; },
    };
  }

  // -- the runner, over Chrome's APIs -----------------------------------------------

  function create(deps) {
    const chrome = deps.chrome;
    const now = deps.now || (() => Date.now());
    const sleep = deps.sleep || ((ms) => new Promise((resolve) => setTimeout(resolve, ms)));
    const every = deps.setInterval || setInterval;
    const stopEvery = deps.clearInterval || clearInterval;
    const after = deps.setTimeout || setTimeout;
    const cancel = deps.clearTimeout || clearTimeout;
    const storage = () => chrome.storage.local;
    const lock = makeLock();
    const callMs = deps.callMs || CALL_MS;

    // A call into a tab can hang (a page stuck in a long task, a tab mid crash), and
    // a hung call would hold the lock until Chrome stopped the worker, refusing
    // every Load meanwhile. Each such call is raced against `callMs`.
    function timed(promise) {
      let timer;
      const late = new Promise((_, reject) => { timer = after(() => reject(new Error("Chrome did not answer")), callMs); });
      return Promise.race([promise, late]).finally(() => cancel(timer));
    }

    async function readStats() {
      try { return (await storage().get(STATS_KEY))[STATS_KEY] || { rungs: {} }; } catch { return { rungs: {} }; }
    }
    async function writeStats(stats) {
      // A lost record costs the next run a slower start, never this run its result.
      try { await storage().set({ [STATS_KEY]: stats }); } catch { /* see above */ }
    }

    // Read afresh each time: `hold` writes to the same record during a run.
    async function note(rung, outcome) {
      await writeStats(record(await readStats(), rung, outcome, now()));
    }

    async function findTab() {
      try {
        const [found] = await timed(chrome.tabs.query({ url: WA_MATCH }));
        return found || null;
      } catch { return null; }
    }

    async function probe(tabId) {
      try {
        const [answer] = await timed(chrome.scripting.executeScript({
          target: { tabId },
          // Kept in step with whatsapp.js (its own sign in check and COMPOSER_OPEN).
          func: () => ({
            signedIn: !!document.querySelector('button[aria-label="Status"]') || !!document.querySelector("#pane-side"),
            composer: !!document.querySelector('[data-icon^="wds-ic-send"],[aria-label^="Send "][aria-label$=" selected"],' +
              '[aria-label="Close status posting view"]'),
          }),
        }));
        return answer && answer.result || { signedIn: false, composer: false };
      } catch {
        return { signedIn: false, composer: false };
      }
    }

    // Waits for a tab to finish loading and WhatsApp to be signed in; reloads it in
    // the background first if Chrome discarded it (6.3). `null` when it is ready.
    async function ready(tabId, halted, limit) {
      const until = now() + (limit == null ? SIGN_IN_MS : limit);
      let reloaded = false;
      for (;;) {
        if (halted()) return "stopped";
        let tab = null;
        try {
          tab = await timed(chrome.tabs.get(tabId));
        } catch (err) {
          // A missing tab is closed; a call that hung is asked again until the limit.
          if (!/did not answer/.test(String(err && err.message))) return "closed";
        }
        if (!tab) {
          // asked again below
        } else if (tab.discarded && !reloaded) {
          reloaded = true;
          // A reload does not activate the tab.
          await chrome.tabs.reload(tabId).catch(() => {});
        } else if (tab.status === "complete" && !tab.discarded && (await probe(tabId)).signedIn) {
          return null;
        }
        if (now() > until) return "signed-out";
        await sleep(POLL_MS);
      }
    }

    async function inject(tabId) {
      await timed(chrome.scripting.executeScript({ target: { tabId }, files: ["wa-bridge.js"] }));
      await timed(chrome.scripting.executeScript({ target: { tabId }, files: ["whatsapp.js"], world: "MAIN" }));
    }

    // Opens the port, keeps time, hands the clip over and waits for the answer,
    // all within LOAD_LIMIT_MS measured here. `given` says whether the file reached
    // WhatsApp, after which another placement must not be tried on top of it.
    function talk(tabId, clip, meta, signal, onStep) {
      return new Promise((resolve) => {
        let given = false;
        let finished = false;
        const acks = new Map();
        let port;
        try { port = chrome.tabs.connect(tabId, { name: PORT_NAME }); } catch {
          resolve({ ...failure("closed"), given }); return;
        }
        const finish = (result) => {
          if (finished) return;
          finished = true;
          stopEvery(ticker);
          cancel(timer);
          if (signal) signal.removeEventListener("abort", onAbort);
          for (const waiter of acks.values()) waiter.reject(new Error("closed"));
          acks.clear();
          try { port.disconnect(); } catch { /* gone */ }
          resolve({ ...result, given });
        };
        const onAbort = () => finish(failure("stopped"));
        const timer = after(() => finish(failure("timeout")), LOAD_LIMIT_MS);
        const ticker = every(() => { try { port.postMessage({ cmd: "tick" }); } catch { /* gone */ } }, TICK_MS);
        if (signal) signal.addEventListener("abort", onAbort, { once: true });
        port.onMessage.addListener((message) => {
          if (!message) return;
          if (typeof message.ack === "number") {
            const waiter = acks.get(message.ack);
            if (waiter) { acks.delete(message.ack); waiter.resolve(); }
          } else if (message.step) {
            if (message.step === "file") given = true;
            if (onStep) { try { onStep(message.step); } catch { /* a caller's display never stops a load */ } }
          } else if (message.result) {
            finish(message.result);
          }
        });
        port.onDisconnect.addListener(() => finish(failure("closed")));
        const waitAck = (n) => new Promise((ok, no) => {
          if (finished) { no(new Error("closed")); return; }
          acks.set(n, { resolve: ok, reject: no });
        });
        handover(port, clip, meta, waitAck, () => finished)
          .catch((err) => finish(failure(finished ? "closed" : "failed", err && err.message)));
      });
    }

    // Everything after the tab is placed: ready, no composer open, scripts in, clip in.
    async function runOn(tabId, clip, meta, signal, onStep, waitLimit) {
      const halted = () => !!(signal && signal.aborted);
      const waited = await ready(tabId, halted, waitLimit);
      if (waited) return { ...failure(waited), given: false };
      if ((await probe(tabId)).composer) {
        return { ...failure("composer-open", "A Status is already open in WhatsApp. Close it or send it, then try again"), given: false };
      }
      if (halted()) return { ...failure("stopped"), given: false };
      try { await inject(tabId); } catch { return { ...failure("closed"), given: false }; }
      return talk(tabId, clip, meta, signal, onStep);
    }

    // The focus guard (6.1). `call` wraps each of the run's own placement calls so
    // their effects can be told from the person's.
    async function guard(intended) {
      const g = { before: { windowId: NONE, tabId: null }, lastWindowId: null, events: [], calls: [],
                  moved: false, undos: 0, intended, chain: Promise.resolve() };
      try {
        const win = await timed(chrome.windows.getLastFocused({ windowTypes: ["normal"] }));
        g.lastWindowId = win ? win.id : null;
        if (win && win.focused) {
          g.before.windowId = win.id;
          const [active] = await timed(chrome.tabs.query({ active: true, windowId: win.id }));
          g.before.tabId = active ? active.id : null;
        }
      } catch { /* no window at all: nothing for the person to lose */ }
      const onFocus = (windowId) => { g.events.push({ type: "window", windowId, at: now() }); g.check(); };
      const onActive = (info) => { g.events.push({ type: "tab", windowId: info.windowId, tabId: info.tabId, at: now() }); g.check(); };
      chrome.windows.onFocusChanged.addListener(onFocus);
      chrome.tabs.onActivated.addListener(onActive);

      g.call = async (work) => {
        const c = { start: now(), end: null };
        g.calls.push(c);
        try { return await work(); } finally { c.end = now(); }
      };
      g.check = () => {
        g.chain = g.chain.then(async () => {
          const verdict = judge(g.before, g.events, g.calls);
          if (verdict.moved) g.moved = true;
          if (g.intended || !verdict.undo || g.undos >= MAX_UNDOS) return;
          g.undos += 1;
          await g.call(() => putBack(verdict.undo));
        }).catch(() => {});
        return g.chain;
      };
      // Waits for the events of the calls just made, then judges them.
      g.settle = async () => { await sleep(SETTLE_MS); await g.check(); };
      // S3 and S5 moved focus on purpose; at the end it goes back unless the person
      // moved it meanwhile.
      g.restore = async () => {
        if (judge(g.before, g.events, g.calls).person) return;
        await g.call(() => putBack({ windowId: g.before.windowId === NONE ? null : g.before.windowId,
                                     tabId: g.before.tabId, blur: null }));
      };
      g.stop = () => {
        chrome.windows.onFocusChanged.removeListener(onFocus);
        chrome.tabs.onActivated.removeListener(onActive);
      };
      return g;
    }

    async function putBack(undo) {
      if (undo.tabId != null) await chrome.tabs.update(undo.tabId, { active: true }).catch(() => {});
      if (undo.windowId != null && undo.windowId !== NONE) {
        await chrome.windows.update(undo.windowId, { focused: true }).catch(() => {});
      } else if (undo.blur != null) {
        // [Unverified] that unfocusing hands focus back to the application the
        // person was in, rather than to another Chrome window.
        await chrome.windows.update(undo.blur, { focused: false }).catch(() => {});
      }
    }

    async function hold(tabId) {
      await chrome.tabs.update(tabId, { autoDiscardable: false }).catch(() => {});
      const stats = await readStats();
      if (stats.held !== tabId) await writeStats({ ...stats, held: tabId });
    }

    // -- the rungs --------------------------------------------------------------------

    // Each returns the run's result plus `skip: true` when the rung does not apply
    // here (S0 with no tab, S1 with one), which is not held against it.
    async function rungS0(ctx) {
      if (!ctx.existing) return { skip: true };
      const tab = await findTab();
      if (!tab || tab.id !== ctx.existing) return { skip: true };
      await hold(tab.id);
      // [Inference] a tab hidden for over five minutes is throttled hard; the ticks
      // are what is meant to carry it (6.2). Never activated.
      return runOn(tab.id, ctx.clip, ctx.meta, ctx.signal, ctx.onStep);
    }

    async function rungS1(ctx) {
      if (await findTab()) return { skip: true };
      const windowId = ctx.guard.lastWindowId;
      const tab = await ctx.guard.call(() => chrome.tabs.create({ url: WA_URL, active: false,
                                                                  ...(windowId != null ? { windowId } : {}) }));
      await ctx.guard.settle();
      await hold(tab.id);
      // [Inference] Chrome gives no media to a tab never in front (sw.js,
      // pageCapture); whether the composer's preview needs it is a Phase 0 question.
      const result = await runOn(tab.id, ctx.clip, ctx.meta, ctx.signal, ctx.onStep);
      // A tab this run opened, that failed before WhatsApp had the file and that the
      // person has not turned to, is closed again rather than left in their strip.
      // Signed out is the exception: the notice sends them to that tab to scan.
      if (!result.ok && !result.given && CLOSE_S1.has(result.code) && !(await looked(ctx.guard, tab.id))) {
        await ctx.guard.call(() => chrome.tabs.remove(tab.id)).catch(() => {});
        await unhold(tab.id);
      }
      return result;
    }

    async function looked(g, tabId) {
      if (g.events.some((e) => e.type === "tab" && e.tabId === tabId)) return true;
      try { return !!(await timed(chrome.tabs.get(tabId))).active; } catch { return false; }
    }

    // The tab, or a new one, goes into a helper window that does not take focus,
    // `work` runs on it there, and it goes back where it was; the helper is closed.
    // A tab is never opened beside an existing one: WhatsApp would ask which one to
    // "Use here".
    async function viaHelper(g, work) {
      const tab = await findTab();
      // The tab the person is looking at is visible already; moving it would move
      // what they see.
      if (tab && tab.id === g.before.tabId) return { skip: true };
      // A tab alone in its window cannot go out and back: Chrome closes a window
      // whose last tab leaves [Inference], and there would be nowhere to return to.
      if (tab) {
        const neighbours = await timed(chrome.tabs.query({ windowId: tab.windowId })).catch(() => null);
        if (!neighbours || neighbours.length <= 1) return { skip: true };
      }
      const home = tab ? { windowId: tab.windowId, index: tab.index, active: tab.active } : null;
      let helper;
      try {
        helper = await g.call(() => chrome.windows.create({
          focused: false, type: "normal", ...HELPER, ...(tab ? { tabId: tab.id } : { url: WA_URL }),
        }));
      } catch {
        return failure("failed", "Could not open a window for WhatsApp");
      }
      await g.settle();
      let tabId = tab ? tab.id : null;
      if (tabId == null) {
        const [made] = await chrome.tabs.query({ windowId: helper.id }).catch(() => []);
        tabId = made ? made.id : null;
      }
      try {
        if (tabId == null) return failure("failed", "Could not open WhatsApp in its window");
        // [Unverified] that moving a tab between windows neither reloads WhatsApp
        // nor raises its "Use here" (Phase 0 item 2). A reload shows as `closed`.
        return await work(tabId);
      } finally {
        await g.call(() => goHome(tabId, home, helper.id, g.lastWindowId));
        await g.settle();
      }
    }

    // WhatsApp goes back to its own window, or the window the person last used; the
    // helper is closed only once WhatsApp is out of it. If it cannot be moved, the
    // helper stays open: closing it would close WhatsApp and a prepared composer.
    async function goHome(tabId, home, helperId, lastWindowId) {
      const exists = async (id) => {
        if (id == null || id === helperId) return false;
        try { await timed(chrome.windows.get(id)); return true; } catch { return false; }
      };
      if (tabId != null) {
        const homeOk = home && await exists(home.windowId);
        const windowId = homeOk ? home.windowId : (await exists(lastWindowId)) ? lastWindowId : null;
        if (windowId == null) return;
        try {
          await timed(chrome.tabs.move(tabId, { windowId, index: homeOk ? home.index : -1 }));
        } catch { /* checked below */ }
        let now;
        try { now = await timed(chrome.tabs.get(tabId)); } catch { now = null; }
        // Still in the helper, or not known: the helper stays open.
        if (!now || now.windowId === helperId) return;
        if (now && homeOk && home.active) await chrome.tabs.update(tabId, { active: true }).catch(() => {});
      }
      // Moving the last tab out may close the window by itself; this is for when
      // Chrome kept it.
      await chrome.windows.remove(helperId).catch(() => {});
    }

    async function rungS2(ctx) {
      return viaHelper(ctx.guard, async (tabId) => {
        await hold(tabId);
        return runOn(tabId, ctx.clip, ctx.meta, ctx.signal, ctx.onStep);
      });
    }

    async function forward(ctx) {
      let tab = await findTab();
      if (!tab) tab = await ctx.guard.call(() => chrome.tabs.create({ url: WA_URL, active: true }));
      await hold(tab.id);
      await ctx.guard.call(async () => {
        await timed(chrome.tabs.update(tab.id, { active: true }));
        await timed(chrome.windows.update(tab.windowId, { focused: true })).catch(() => {});
      });
      try {
        // Once started it finishes, even if the person comes back: a half loaded
        // composer is worse than a finished one (Table SC-4, S3).
        return await runOn(tab.id, ctx.clip, ctx.meta, ctx.signal, ctx.onStep);
      } finally {
        await ctx.guard.settle();
        await ctx.guard.restore();
      }
    }

    async function idleNow() {
      // Without the idle permission nobody can be known to be away.
      if (!chrome.idle || !chrome.idle.queryState) return "active";
      try { return await chrome.idle.queryState(IDLE_SECONDS); } catch { return "active"; }
    }

    async function rungS3(ctx) {
      if ((await idleNow()) === "active") return { skip: true };
      return forward(ctx);
    }

    const RUN = { S0: rungS0, S1: rungS1, S2: rungS2, S3: rungS3, S5: forward };

    // -- the walk -----------------------------------------------------------------------

    async function walk(options, quietOnly) {
      const start = now();
      const signal = options.signal;
      const halted = () => !!(signal && signal.aborted);
      const onStep = (step) => { if (options.onStep) options.onStep(step); };
      const meta = { name: String(options.name || "clip.mp4"), caption: String(options.caption || "") };
      const stats = await readStats();
      const existing = await findTab();
      const steps = quietOnly ? order(stats, now()) : ladder(stats, options.settings, now());
      let last = null;
      let ended = null;
      for (const rung of steps) {
        if (halted()) return { ...failure("stopped"), rung: last, ms: now() - start };
        if (rung === "S4") {
          return { ...failure("ask"), rung: "S4", ms: now() - start };
        }
        const intended = rung === "S3" || rung === "S5";
        const g = await guard(intended);
        const ctx = { clip: options.clip, meta, signal, guard: g, existing: existing ? existing.id : null,
                      onStep: (step) => onStep({ rung, step }) };
        const began = now();
        let result;
        try {
          onStep({ rung, step: "placing" });
          result = await RUN[rung](ctx);
          await g.settle();
        } catch (err) {
          result = failure("failed", err && err.message);
        } finally {
          g.stop();
        }
        if (result.skip) continue;
        last = rung;
        // Only what the placement itself decided is held against it: not a signed out
        // WhatsApp, an open composer, a moved selector or Stop. S3 and S5 move focus
        // by design; for them only whether the composer loaded is recorded.
        if (result.ok || NEXT_RUNG.has(result.code) || (!intended && g.moved)) {
          await note(rung, { ok: result.ok, quiet: intended || !g.moved, moved: !intended && g.moved,
                             ms: now() - began, test: !!options.test });
        }
        const answer = { ok: !!result.ok, rung, ms: now() - start, focusMoved: g.moved };
        if (result.ok) return { ...answer, caption: result.caption };
        ended = { ...answer, code: result.code || "failed", error: result.error };
        // A file already handed to WhatsApp may yet become a composer; another
        // placement on top of it could load the clip twice.
        if (result.given || !NEXT_RUNG.has(ended.code)) return ended;
      }
      // Only a quiet test, or S3 or S5 failing, gets here.
      if (quietOnly) return { ...failure("ask"), rung: last, ms: now() - start, focusMoved: false };
      if (ended) return { ...ended, ms: now() - start };
      return { ...failure("failed"), rung: last, ms: now() - start, focusMoved: false };
    }

    // Today's Load into WhatsApp, pressed by a person who wants to see WhatsApp, so
    // it comes to the front; a background tab is throttled hard enough to make the
    // composer time out (D-084).
    async function manual(options) {
      const start = now();
      const signal = options.signal;
      const halted = () => !!(signal && signal.aborted);
      const done = (result) => ({ rung: null, focusMoved: false, ...result, ms: now() - start });
      if (halted()) return done(failure("stopped"));
      let tab = await findTab();
      if (!tab) tab = await timed(chrome.tabs.create({ url: WA_URL, active: true }));
      await timed(chrome.tabs.update(tab.id, { active: true }));
      await timed(chrome.windows.update(tab.windowId, { focused: true })).catch(() => {});
      const meta = { name: String(options.name || "clip.mp4"), caption: String(options.caption || "") };
      const onStep = (step) => { if (options.onStep) options.onStep({ rung: null, step }); };
      const result = await runOn(tab.id, options.clip, meta, signal, onStep, SIGN_IN_MS);
      const { given, ...rest } = result;
      return done(rest);
    }

    async function load(options) {
      if (!lock.take()) return { ...failure("busy"), rung: null, ms: 0 };
      try {
        if (options.manual) return await manual(options);
        if (await inUse()) return { ...failure("in-use"), rung: null, ms: 0 };
        return await walk(options, false);
      } catch (err) {
        return { ...failure("failed", err && err.message), rung: null, ms: 0 };
      } finally {
        lock.free();
      }
    }

    // FR-12: WhatsApp's tab in front in the focused window while the person is not
    // idle, or a Status composer open in it.
    async function inUse() {
      const tab = await findTab();
      if (!tab) return false;
      try {
        const win = await timed(chrome.windows.getLastFocused({}));
        if (tab.active && win && win.focused && win.id === tab.windowId && (await idleNow()) === "active") return true;
      } catch { /* no windows */ }
      if (tab.discarded) return false;
      return (await probe(tab.id)).composer;
    }

    // FR-10: five minutes before a run. Not discardable from now until `release`; a
    // discarded tab is reloaded in the background and waited on. No tab means
    // nothing to warm: the run's S1 or S2 opens one.
    async function prewarm() {
      const tab = await findTab();
      if (!tab) return { ok: false, code: "none", tabId: null };
      await hold(tab.id);
      const wasDiscarded = !!tab.discarded;
      const waited = await ready(tab.id, () => false);
      if (!waited) return { ok: true, code: "ok", tabId: tab.id, reloaded: wasDiscarded };
      let still = null;
      try { still = await chrome.tabs.get(tab.id); } catch { /* closed */ }
      if (!still) return { ok: false, code: "none", tabId: null };
      return { ok: false, code: still.discarded || still.status !== "complete" ? "discarded" : "signed-out", tabId: tab.id };
    }

    async function unhold(tabId) {
      const stats = await readStats();
      if (stats.held !== tabId) return;
      const { held, ...rest } = stats;
      await writeStats(rest);
    }

    async function release() {
      const stats = await readStats();
      if (stats.held == null) return;
      await chrome.tabs.update(stats.held, { autoDiscardable: true }).catch(() => {});
      const { held, ...rest } = stats;
      await writeStats(rest);
    }

    // U7: Try quiet mode now. With a clip, a quiet walk (S0 to S2 only) that loads
    // the composer and, like every run, stops before Send. Without one, each quiet
    // placement is made and checked for sign in and for focus, and nothing is loaded.
    async function testQuiet(clip) {
      if (!lock.take()) return { ...failure("busy"), rung: null, ms: 0 };
      try {
        if (clip) {
          return await walk({ clip, name: "quiet-test.mp4", caption: "", test: true }, true);
        }
        return await placeOnly();
      } catch (err) {
        return { ...failure("failed", err && err.message), rung: null, ms: 0 };
      } finally {
        lock.free();
      }
    }

    async function placeOnly() {
      const start = now();
      const never = () => false;
      const signedIn = async (tabId) => { const w = await ready(tabId, never); return w ? failure(w) : { ok: true }; };
      const existing = await findTab();
      for (const rung of order(await readStats(), now())) {
        const g = await guard(false);
        let result;
        try {
          if (rung === "S0") {
            result = existing ? await signedIn(existing.id) : { skip: true };
          } else if (rung === "S1") {
            if (await findTab()) result = { skip: true };
            else {
              const tab = await g.call(() => chrome.tabs.create({ url: WA_URL, active: false,
                ...(g.lastWindowId != null ? { windowId: g.lastWindowId } : {}) }));
              await g.settle();
              result = await signedIn(tab.id);
            }
          } else {
            result = await viaHelper(g, signedIn);
          }
          await g.settle();
        } finally {
          g.stop();
        }
        if (result.skip) continue;
        await note(rung, { placedOnly: true, moved: g.moved, test: true });
        const answer = { rung, ms: now() - start, focusMoved: g.moved };
        if (result.ok && !g.moved) return { ok: true, ...answer };
        if (result.code === "signed-out") return { ...failure("signed-out"), ...answer };
      }
      return { ...failure("ask"), rung: null, ms: now() - start, focusMoved: false };
    }

    async function stats() {
      return summary(await readStats(), now());
    }

    return { load, busy: () => lock.held(), inUse, prewarm, release, testQuiet, stats };
  }

  const pure = { order, ladder, skipped, record, summary, judge, handover, makeLock, create,
                 RUNGS, QUIET, SLICE, GUARD_MS, SKIP_AFTER, SKIP_MS, TICK_MS, LOAD_LIMIT_MS, NONE };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = pure;
  } else {
    root.SnipPlace = { ...pure, ...create({ chrome: root.chrome }) };
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
