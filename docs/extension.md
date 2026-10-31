# The Chrome extension and the hosted renderer

Written **2026-10-24T19:49:08+05:30**, from the spike recorded in
[extension-spike.md](extension-spike.md), which has every measurement this plan leans
on. This is the plan and, as each phase lands, the record of what was built.

## Why this exists

A server cannot fetch from YouTube: datacentre addresses are refused, and the SABR
rollout has made even yt-dlp's best routes fragile. The viewer's own browser has
none of that problem, because YouTube's own player is already fetching the video on
the viewer's own connection. So the split is:

```
viewer's Chrome                                     the SnipShare server
---------------                                     --------------------
YouTube tab: the player buffers the video
  recorder.js copies what it appends (MSE)
  the walk fills the chosen window, ~2-15s
  media.js cuts out only the window's fragments
        |  audio (+ video in video mode) + artwork
        v
service worker: resumable chunked upload  ------->  hosted.py: uploads, a job queue
        |                                             capture.section: cut on the
        |  poll the job                                 media's own timestamps
        |                                             pipeline.produce: unchanged
        |  download the clip (Range, resumable) <--  the finished mp4
        v
IndexedDB, then:
  WhatsApp Web tab: load into the Status composer, never press Send
  or: save the mp4
```

Nothing on the server talks to YouTube. The engine renders exactly as it does for
the local tool, from a section that arrived by upload instead of by yt-dlp.

## Table EX-1: what was proven before building

| Claim | Evidence |
|---|---|
| The page hands over the exact section | 14 runs plus 9 in the owner's Chrome: durations exact, SSIM 0.925 to 1.000 against yt-dlp's copy |
| Sync is right | beep and flash test: within 0.5ms after the cut, where format 18 is 37ms late |
| It is fast | 1.3 to 18.3s for 15 to 90 second windows, with no playback |
| Ads do not get in | each ad plays in a MediaSource of its own; player and media clocks agreed |
| Premium is fine | six videos signed in, no ads, same results |
| The engine needs no change to render it | 90s clips in both modes from a captured section |
| An extension can load WhatsApp's composer | file input caught and filled, caption by `insertText`, 2.1s |

## Phase plan

Each phase ends with a strict audit of that phase before the next starts.

### Phase 1: the engine takes a captured section

- `wastatus/capture.py`: probe an uploaded stream (one stream of the expected kind,
  an allowed codec, where it starts and ends on its own timestamps), and cut the
  window out of it. Cut with `trim`/`atrim` on the original timestamps, `-copyts`,
  `-fps_mode passthrough`: the spike lost 59ms to separate `-ss` seeks and 33ms to
  per-input start-time shifting before landing on that. The section is written as
  Matroska with FLAC audio, so no AAC priming delay is added before the engine's
  own encode.
- `pipeline.Captured` and `Job.captured`: when present, `produce` skips the probe
  and the download, takes the source facts it was given, cuts the section in its
  own work directory during the `download` stage, and uses the uploaded artwork.
  Nothing else in `produce` changes.
- Tests: synthetic streams with a flash and a beep on every whole second, with
  timestamps that do not start at zero, cut and measured.

### Phase 2: the hosted renderer

`wastatus/hosted.py`, standard library only, like `serve.py`.

- **Auth:** a bearer token per person. Stored as a SHA-256 hash with a name; the
  plain token is shown once, when it is made. `python -m wastatus hosted token
  add|list|revoke`. No accounts, no passwords, no email.
- **Uploads, built for slow networks:** create, then `PUT` chunks with
  `Content-Range`. A chunk the server already has is acknowledged again, a chunk
  past the end of what it has is answered 409 with the offset it does have, so a
  client that lost its place resumes rather than restarts. Chunks are at most
  1 MiB, under Cloudflare's limits and small enough to retry cheaply.
- **Jobs:** created from finished uploads that belong to the same token. A bounded
  queue, a fixed number of render workers, one active job per token. States:
  `queued`, `rendering`, `done`, `failed`, `cancelled`. The stage names are the engine's own.
- **The clip:** `GET` with `Range` support, so a download over a poor connection
  resumes too.
- **Janitor:** unfinished uploads go after 30 minutes idle, jobs and their files
  after an hour. Nothing is kept for longer than it takes to collect it.
- **Limits:** window at most `pipeline.MAX_DURATION`, upload sizes capped, codecs
  checked by `capture` before ffmpeg is asked to decode anything.
- **No CORS headers.** The extension's service worker has host permission and does
  not need them; a web page does, and is therefore refused.

### Phase 3: the extension

`src/`, Manifest V3, no build step, no dependencies.

- `media.js`: the fMP4 and WebM fragment parser, the spike's `stitch.py` ported and
  made incremental. One implementation, used in the page and by the Node tests.
  Fragments carry their own timestamps; runs are cut at aborts and header appends;
  fragments are grouped by the header they decode with; a `remove()` by the player
  drops ours for the same range, so memory follows the player's own buffer.
- `recorder.js`, page world, from `document_start`: hooks MediaSource and
  SourceBuffer, **records always** (the spike lost 20 seconds to a disarmed hook),
  tags each MediaSource with its video id and whether it began as an ad, and runs the
  walk: pause, seek, wait for our own store (not `video.buffered`) to cover the
  window, seek to the edge when the player stops reading ahead, restore where the
  viewer was.
- `bridge.js`, isolated world: carries messages and bytes between the page and the
  service worker.
- `sw.js`: one job at a time, its state in `chrome.storage.local` so a closed
  popup or a restarted worker loses nothing that can be kept. Uploads chunk by
  chunk with retries and backoff, polls the job with backoff, downloads with Range
  resume into IndexedDB, loads WhatsApp's composer through `whatsapp.js`, saves the
  file through `chrome.downloads`.
- `popup.*`: set up (server and token, checked against `/api/v1/me`), the form
  (start and end prefilled from where the video is, Card or Video, the words behind
  a disclosure), progress by phase, and the finished clip with **Load into
  WhatsApp** as the one primary action and **Save the video** beside it.
- Node tests for `media.js`, against fragmented MP4 and WebM that ffmpeg makes on
  the spot, appended in awkward pieces with aborts and re-inits.

### Phase 4: production

- Host: one shared host: a reverse proxy on a shared network, other services
  already running as containers, 4 Ampere cores and 20 GB free. One render worker,
  the container capped at 3 cores so the neighbours keep one.
- The production site, proxied through Cloudflare, SSL strict, the shared proxy
  holding its certificate and capping request bodies at 2 MB, which only a chunk can
  need. (Replaced on 2026-10-25 by a Compose project of its own behind a Cloudflare
  Tunnel; see [hosted-page.md](hosted-page.md) and [DEPLOYMENT.md](../DEPLOYMENT.md).)
- `deploy/`: Dockerfile (Debian, ffmpeg from the distribution, the repo's own
  requirements), compose file, the Caddy block, and `scripts/deploy.sh`.
  [DEPLOYMENT.md](../DEPLOYMENT.md) becomes mandatory the moment this ships, per
  [CONTEXT_MAP.md](../CONTEXT_MAP.md).

### Phase 5: end to end, and the bad network

In the owner's Chrome, against production: capture, upload, render, download, load
into the composer, cancel. Then the same with the network throttled, with the
server restarted mid-upload, and with the popup closed half way.

### Phase 6: master audit and the documentation sweep

## Decisions taken in this plan

Recorded in [DECISIONS.md](../DECISIONS.md) as D-080 to D-085.

| Question | Answer | Why |
|---|---|---|
| Where is the fragment parser | in the extension only | one implementation; the server receives clean files and checks them with ffprobe |
| What does card mode upload | audio and artwork, no video | it is all the card uses, and a tenth of the bytes |
| Default quality | 720p, 1080p in settings | the frame is 1080 wide, a landscape source is drawn 1080x608, and a slow upload is the commonest failure |
| Who may render | holders of a token the owner issued | a renderer anyone can reach is an ffmpeg anyone can feed |
| Stickers, GIFs, placed text | not in the extension's first version | the local page keeps them; the extension does the common case well |
| Does the server ever touch YouTube | no, not even for artwork | the extension uploads the thumbnail it fetched itself |

## As built, 2026-10-24T21:00:13+05:30

Every phase above was built, audited and verified. Where the build differs from the
plan, the build is right and this says why.

| Planned | Built | Why |
|---|---|---|
| Artwork uploaded in card mode | **required** in card mode; the renderer refuses a card without it | the engine's fallback is to fetch the thumbnail itself, which is a request to YouTube from the server |
| The cut at the source's resolution | no wider than 1080, written `ultrafast` | nothing wider reaches a clip; a 90 second 1080p cut went from 52 to 18 seconds on the host |
| Quality in settings | applies to Video clips only, and is put back to automatic after the capture | Card clips send only the sound; the viewer's player should not stay pinned |
| Load into WhatsApp | brings the WhatsApp tab to the front | the person asked to see it, and a background tab is throttled into a timeout |
| | 5xx retried everywhere | the renderer restarting, or Cloudflare between, is not an answer |
| | a body refused unread closes the connection | the unread chunk was being parsed as the next request |
| | `compose._join` fixed, D-086 | found reading a frame from the renderer; it affected every card |

## Table EX-2: measured end to end, 2026-10-24

| Case | Result |
|---|---|
| Card, 20 s, owner's Chrome, Premium, production | capture 2 s, upload 4 s, render 37 s, ready at 46 s; loaded into WhatsApp in 7.5 s |
| Video, 90 s at 1080p, production | capture 16 s, upload 27 s, render 127 s, ready at 173 s |
| Video, 30 s, 800 kbit/s through Cloudflare, worker stopped mid upload | resumed from the server's offset, ready at 169 s |
| Beep and flash video through production | flash on the frame, beep +0.6 ms |
| In-page navigation to a second video | clip correlates 0.94 with it, 0.04 with the first |
| The popup's own buttons, set up to finished clip | 42 s, no horizontal overflow at 360 px |

## Slow lines and a stopped worker, 2026-10-25T15:11:42+05:30

From the audit before publication (D-100). The numbers the extension now lives by:

**Table EX-4: how long anything may take**

| What | Limit | Why |
|---|---|---|
| Reading the window in the page | fails after 120 s with nothing new read, or 10 minutes in all, time on ads excluded; the worker gives up on a page silent for 150 s | a slow line reading steadily is let finish; only silence fails it. It used to fail at a fixed two minutes. The silences are wide because Chrome can slow a background tab's timers to about one a minute after a long ad (D-101) |
| One request to the renderer | 25 s | Chrome stops an extension's worker when a `fetch()` waits more than 30 s for its answer |
| An upload chunk | starts at 64 KB, never under 32 KB; doubles when one takes under 3 s, halves over 8 s; the size is kept with the job | so no chunk outlasts the request limit on any line the extension can use, and a woken worker carries on at the size the line took |
| A download | no overall limit; 30 s with nothing arriving is a dropped line; what arrived is kept every 2 MB; a resumed answer must start where the kept part ends | a slow download is not a failure, and storage writes no longer grow with the square of the clip |
| The page waiting on the extension | 5 minutes without a word | longer than any step of the extension's own goes quiet for |
| Stop, from the page | the extension is told; the page lets go after 5 s whatever it says | a Stop must end even if the worker has hung |

One capture and one WhatsApp load at a time, whichever path asks, the site or the
Options page. The once a minute wake-up exists only while a job is in flight. Memory
held per YouTube tab is capped at 200 MB. A capture whose fragments the player shifted
in time (`timestampOffset`) is refused, because the renderer cuts by the bytes' own
times.

## Driven by SnipShare, 2026-10-25T02:06:06+05:30

Since T-068 the toolbar button opens the site, and the page drives the extension
(DECISIONS.md D-090; the page's side is in [hosted-page.md](hosted-page.md)). The
popup is still in the extension, as its options page (right-click the button,
**Options**), for anybody holding a token.

### Table EX-3: what the page may ask, over `chrome.runtime.connect(id)`

| Asks | With | Answers | Notes |
|---|---|---|---|
| `hello` | | `{version, whatsapp: none, open or signed-in}` | within 1.5 s whatever WhatsApp's tab is doing |
| `capture` | `videoId, start, end, mode, server, grant` | progress messages, then `{video_id, title, channel, duration, audio, video or artwork}` upload ids | one at a time; 20 an hour per browser; opens the video beside the page if it is not open, muted, in front until its player is ready, then closes it |
| `load` | `url` of `/api/v1/clip?stem=`, `grant`, `caption`, `name` | progress, then `{loaded: true}` | 10 an hour; fetches with Range and a stall timeout, then the same composer steps as the popup |
| `words` | `url` | `{title, channel}` | YouTube's oEmbed, from the browser; the server cleans them |
| `stop` | | | aborts the capture or load in flight, and the walk in the YouTube page |

Every failure comes back as `{error: {message, code, phase}}`; the page shows the
message and reports the code and versions, never the video. The extension answers
only the origin it was built for (`config.js`), and uses a grant only against that
origin. `scripts/build_extension.py` writes that origin into the manifest
(`externally_connectable`, `host_permissions`) and `config.js`, and pins the id.

Ads: the walk's two minute limit now counts only the time spent reading, not time
spent waiting for ads, which have five minutes of their own; the worker gives up on
a capture after a minute with no word from the page, rather than after three
minutes in all.

## Scheduled Statuses, Release 1, 2026-10-31T01:51:47+05:30

Version 2.1.0. The plan is [scheduling.md](scheduling.md) and what was built is its
Section 15; the decisions are D-104 and D-105. The extension now keeps a queue of
clips and, when one is due, puts it in WhatsApp's composer for the person to send. It
never presses Send.

**Table EX-5: what Release 1 adds to the extension**

| Piece | What it is |
|---|---|
| `queue.html`, `queue.css`, `queue-page.js` | a page of the extension: the queue table, Needs you, history, the held clip budget, the quiet test and the run log. Opened by the page's **Scheduled** link (`open-queue`), by **Open the queue** in the options page, or from the toolbar button's menu (**Scheduled Statuses**). Talks to the worker over the internal port `snipshare-queue` |
| `queue.js`, `custody.js`, `place.js`, `schedule.js` | the worker's modules, loaded by `importScripts` before its own code: the rules, the held clips, the placement ladder, the stored queue (`SnipQueue`, `SnipCustody`, `SnipPlace`, `SnipSchedule`) |
| options page | the scheduling settings: quiet hours, the gap for Add to queue, bring WhatsApp forward, take focus when idle, a notice for every post |
| new permissions | `notifications`, `idle`, `unlimitedStorage`, `contextMenus`; the reasons are in [SECURITY.md](../SECURITY.md) |

**Table EX-6: what the page may now ask, over the external port**

| Asks | With | Answers | Notes |
|---|---|---|---|
| `hello` | | `{version, whatsapp, features}` | `features` is `["schedule"]`; the page offers scheduling only when it is there and the server's `scheduling.enabled` is on |
| `schedule` | `url` of `/api/v1/clip?stem=`, `grant` (clip), `stem`, `name`, `caption`, `mode`, `due` or `afterLast: true`, `action: "prepare"`, `limits` | progress ("Keeping the clip on this computer"), then `{schedule, note}` | validates the time and the limits, then fetches the clip into IndexedDB; any `action` but `prepare` is refused |
| `queue-peek` | | `{next, count, needsYou}`, the next three | for the page's **Up next** |
| `open-queue` | | `{opened: true}` | opens `queue.html` in a new active tab, or focuses the open one: the person pressed a link, so the front is right |

**The alarms.** One `sched-next` alarm stands for the nearest thing to do (a prewarm
five minutes ahead, a run two minutes before the due time so the composer is ready at
it, a wait, a deadline) and one `sched-sweep` runs every 15 minutes. Both are rebuilt
on every wake, because Chrome can drop alarms. The existing `wastatus` alarm belongs
to the popup's job. `chrome.alarms.onAlarm` sends each alarm by name: `wastatus` to
the job loop, `sched-*` to the schedule, and a name nobody owns is ignored, so a
schedule alarm never drives the job loop.

**A run** is: prewarm (mark WhatsApp's tab undiscardable, check it is signed in), then
at the lead time check the person is not using WhatsApp and no composer is open, walk
the ladder from the rung that worked last on this machine, and put the clip in the
composer. Success notifies "in WhatsApp, press Send"; failure notifies what the person
can do. Scheduled runs are paced at 40 an hour on their own key. The tab stays
undiscardable until the composer is closed, for 6 hours at most.

[Unverified] on the owner's Chrome: nothing here has run against a real WhatsApp Web,
and Phase 0 has not been run.

### The account page's frame and the capture tab rule, 2026-10-31T11:35:09+05:30

**Table EX-7: what the queue page gains**

| Piece | What it is |
|---|---|
| `web_accessible_resources` | `queue.html`, `queue.css`, `queue.js`, `queue-page.js`, to the site alone (local addresses in the repository copy; `scripts/build_extension.py` writes the site). Needed so the account page can frame the queue |
| Embed mode | `queue.html?embed=1&theme=<system, light or dark>`: no header of its own, the site's theme, its height told to the page after every change of layout, its toast kept in the part of the frame on screen. It loads `config.js` for the site's origin, and refuses to draw or connect if an ancestor is not the site |
| `open-queue` | also what the account section's fallback asks when the frame is silent for 6 seconds |

What crosses between the page and the frame is Table AP-9 in
[account-page.md](account-page.md); the security reasoning is in SECURITY.md.

**The capture's tab rule.** `videoTab(videoId)` in `src/sw.js` returns a tab only if it
shows this video, is not discarded and its player answers `ready` for this video. The
tab is read where it is and never brought forward. Otherwise the extension opens its
own muted tab beside the page, in front only until its player is ready, and makes the
page's tab active again whether or not the video opened. A tab open from before the
extension was installed or reloaded has no content scripts and so never answers; that
is what used to leave a capture at "Getting the video" (IN-14). Tests:
`src/test/capture.test.js`.

Version stays 2.1.0 and `EXTENSION_MIN_VERSION` 2.0.0. [Unverified] on the owner's
open tabs: the rule is tested with fake tabs only.
