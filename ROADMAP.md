# Roadmap

Direction and intent, so changes do not pull against where this is going.
Concrete next actions are in [TASKS.md](TASKS.md).

## Shape of the plan

Four phases, agreed with the owner. Each is usable on its own. All four are done, phase 2 in a different shape from the one first agreed.

| Phase | Goal | Status |
|---|---|---|
| 1 | Local tool: link plus timestamps in, clip and caption out | **done**, in daily use |
| 2 | Usable without the owner's laptop | **done, in a different shape**: a browser extension and a hosted renderer, 2026-10-24. See below |
| 3 | Post to WhatsApp Status directly | **done on the desktop**, ahead of phase 2, by driving WhatsApp Web over CDP |
| 4 | Convenience: capture the current YouTube video and timestamp from the browser | **done**, as part of phase 2: the extension reads the window from the tab you are watching |

## After publication: ideas, not commitments

Added **2026-10-25T15:11:42+05:30**, when the repository went public (D-099).

**Table RD-1: what might come next**

| Idea | What it would take | What it would cost |
|---|---|---|
| A way to make a clip with no extension, from the website alone | Chrome's "share this tab" prompt records the YouTube tab the person picks; the clip then comes back as a download, or on an Android phone through the browser's Share button, where WhatsApp offers My status. A site cannot read another site's player or script WhatsApp Web, so the extension's two jobs have no direct equivalent | recording runs in real time and is a re-encoded screen capture rather than YouTube's own stream; the prompt appears every time; protected video records as black. [Unverified] that Share from a web page reaches My status: to be tested on a real phone before anything is built |
| Warn before trying a protected (DRM) video | the check deferred in Table HP-1 | a little extension code, once there are a few people |
| Scheduled Statuses from the extension, run without taking focus, today's tab model as fallback (added 2026-10-31T00:03:18+05:30) | [docs/scheduling.md](docs/scheduling.md): Phase 0 spike, then schedules, custody of the clip, a quiet placement ladder, fallback, page UI, and confirmed send only if the owner allows it | three releases: about 15, 5 and 2 days [Inference]; reviewed and approved 2026-10-31T00:45:04+05:30 (D-104, docs/scheduling.md Section 14). **Release 1 built 2026-10-31T01:53:14+05:30** (prepare only, from the editor, D-105, Section 15): awaiting Phase 0 on the owner's Chrome and a week of the owner's use. Next: Phase 0 by the owner, then confirmed Send (Phase 8), Release 2 (from a link), Release 3 (the bulk bar) |
| A standard commercial licence | a price list and a short agreement, once enquiries arrive | the owner's time |

## Phase 1: the local tool (done)

Deliberately shipped before any cloud work, on the owner's instruction to settle
the core value first. Zero account risk, no infrastructure, and the pipeline is
reusable no matter what sits in front of it. Now also posts, which was phase 3, by
a route that turned out to carry no account risk.

## Phase 2: always on with a UI

**Built on 2026-10-24, not in the shape below.** The shape agreed in August put the
local page on a cloud server and fetched YouTube from there. By October a datacentre
fetch was the weakest link in the whole tool, and the owner asked for something
anybody could run from their own machine. What was built instead: a Chrome
extension that captures the window in the viewer's own browser, and a renderer at
a hosted renderer that runs the same engine and never talks to YouTube. See
[DECISIONS.md](DECISIONS.md) D-085, [docs/extension.md](docs/extension.md) and
[DEPLOYMENT.md](DEPLOYMENT.md). The August plan is kept below as the record of what
was decided then.

**Driver:** the development machine is often off, and the owner moves between a
Linux and a macOS machine. The tool needs to be reachable from a phone, from
anywhere.

**Already built for it:** the local page from D-019 is the interface phase 2 needs.
Hosting it means putting the same `serve.py` behind the tunnel with real
authentication in front, not designing a UI from scratch.

**Agreed shape:**

- **Host:** a free tier ARM cloud server
- **Front door:** a protected UI on a subdomain the owner controls, via Cloudflare
  Tunnel plus Cloudflare Access, email one time code, no open inbound ports
- **Egress:** Cloudflare WARP first, because it is free and reportedly not
  blocked, with a spare Android phone serving as proxy fallback and a paid
  residential proxy as the last resort. Both hooks already exist as
  `WASTATUS_PROXY` and `WASTATUS_COOKIES_FROM_BROWSER`
- **Underneath:** the same CLI, unchanged

**Known risks going in:** free tier capacity is often unavailable in busy regions,
and providers reclaim idle free instances. Fallbacks were another provider's small
instance or a cheap ARM box. The PO token provider has to become a long lived service
rather than a per run child, and concurrent requests need a queue because ffmpeg
will saturate a small VM.

**Considered and rejected:** Cloudflare Workers, which cannot run ffmpeg or
yt-dlp and cannot hold a long lived session. Running the always on piece on this
machine, which is the constraint that created the phase. Fly.io, Render and
Railway free tiers, which sleep and sit on datacenter IPs.

**Open question:** a web UI or a Telegram bot. A bot needs no inbound network, no
auth to build and delivers the finished mp4 straight to the phone. The owner has
asked for a UI on a subdomain, so the plan is the UI, with the bot as a
possible addition rather than a replacement.

## Phase 3: post directly to Status

**Done on the desktop, 2026-08-18, ahead of phase 2.** `wastatus --post` drives the
real WhatsApp Web composer over the Chrome DevTools Protocol: attach the mp4, type
the caption, press Send, wait for the upload. The account risk that deferred this
never applied to driving the client the owner already uses by hand, so the whole
whatsmeow design was unnecessary. See [DECISIONS.md](DECISIONS.md) D-012, and D-002
for what it replaced.

**What it needs:** a Chrome with `--remote-debugging-port` and a logged in
web.whatsapp.com tab. Nothing else. No pairing, no recipient JID list, because the
composer's own audience selector handles that.

**What is left:** posting from phase 2's always on host, where there is no browser
to drive and no owner sitting in front of it. Three routes, none tested:

| Route | Trade-off |
|---|---|
| Headless Chrome on the host with a persisted session | same code path as today. A long lived headless WhatsApp Web session is untested and may be logged out by WhatsApp |
| The host produces the clip, the desktop or phone posts it | keeps posting where the session already is. Needs a second step, so not truly always on |
| whatsmeow after all | no browser needed, but it is back to pairing as a device against the owner's account, which is what D-002 refused |

**Recommendation when phase 2 arrives:** the second route. The hard part the owner
wanted solved is the clip, not the tap.

**Settled by phase 2 as built, 2026-10-24:** the second route. The renderer makes
the clip and the extension loads it into the composer of the viewer's own WhatsApp
Web, where the session already is; the person presses Send. D-084.

## Phase 2b: the full page, hosted, for invited people

**Done 2026-10-25, as SnipShare.** The local page served per person by the renderer,
Google sign-in after the owner approves a request, the extension reading the video
and loading WhatsApp for the page. DECISIONS.md D-087 to D-093,
[docs/hosted-page.md](docs/hosted-page.md). Next on it, each the owner's call: the
extension naming protected video before trying (Table HP-1), PostHog once there are
ten people. The Chrome Web Store is ruled out for now (D-103, 2026-10-26T01:53:58+05:30): the
extension is distributed from the site only.

## Phase 4: browser capture

**Done with phase 2, 2026-10-24.** The extension is this, and more than this: it
does not hand a link and a timestamp to the tool, it hands over the media itself.

A small extension or bookmarklet that takes the video currently playing and its
timestamp and hands them to the tool. Pure convenience, no new capability. Not
worth starting before phase 2 exists to receive the request.

## Non goals

- Accounts, sign-up or billing. The hosted renderer serves the people the owner
  gives a token to, one clip at a time each, and that is the whole of its multi user
  story. (Until 2026-10-24 this line read "serving anyone other than the owner"; the
  owner reversed it, D-085.)
- Archival quality output. WhatsApp re-encodes on upload.
- Supporting sources other than YouTube.
- A general purpose video editor. The tool does one framing, well.
- Working around YouTube protections beyond what yt-dlp does in the open, with
  the owner's own network or a proxy the owner pays for.
