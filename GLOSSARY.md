# Glossary

Last updated **2026-10-25T15:21:02+05:30**

The words this codebase uses, in one alphabetical list, each with where it lives in
the code. [DOMAIN.md](DOMAIN.md) is the primary source for the domain itself: the
WhatsApp rules, the YouTube extraction terms (Table DO-2), the rendering terms
(Table DO-3) and the capture terms (Table DO-4). Where a term is defined there, this
list gives one line and points to it rather than repeating it.

**Table GL-1: terms**

| Term | Meaning | In the code |
|---|---|---|
| ack | the field WhatsApp Web keeps against a message it sent: below zero refused, zero no answer yet, one or more accepted, then delivered, read, played. The only evidence the tool accepts that a Status went out (D-071) | `post.confirm_sent` |
| admin | a person whose account may approve, decline and suspend others, and see `/admin`. Set from the server's settings, not from the page | `accounts`, `portal._admin_*` |
| alert | one Chat message per key per period, so a storm is one line. See [OBSERVABILITY.md](OBSERVABILITY.md), Table OB-4 | `Portal.alert`, `Accounts.should_alert` |
| artwork | the video's thumbnail, the picture card mode is built from. Fetched by the local tool, captured by the extension | `fetch.download_thumbnail`, `Captured.artwork` |
| capture | the extension's copy of the window, read from what YouTube's player appended, never fetched. DOMAIN.md, Table DO-4 | `src/recorder.js`, `src/media.js`, `pipeline.Captured` |
| card | the 1620x2880 PNG Pillow composes and ffmpeg animates; also short for card mode. DOMAIN.md, Table DO-3 | `compose.build_card` |
| card mode | the default: artwork only, no video frames fetched | `Job.video = False` |
| CDP | the Chrome DevTools Protocol, over which the local tool drives WhatsApp Web through a debug port on loopback (D-012) | `post.py` |
| clip | the finished 1080x1920 MP4, at most 90 seconds and under 10 MiB | `pipeline.produce` |
| composer | WhatsApp Web's Status editor, where a clip is attached and its caption typed. **Load into WhatsApp** opens it and stops; Send is pressed by a person (D-020) | `post.load_video`, `src/whatsapp.js` |
| debug port | the port a posting Chrome is started with (`--remote-debugging-port`). An unauthenticated control channel, so it stays on `127.0.0.1` | `post.candidate_ports` |
| decal | one sticker placed on one frame. **Sticker** is the library; **decal** is the placed instance. People only ever read "sticker" | `Job.decals`, `stickers.py` |
| deny list | `.publish-deny` at the repository root: private strings, one per line, git ignored, that must never appear in a published file. `tests/test_publishable.py` fails on any of them (D-093) | `tests/test_publishable.py` |
| digest | the daily Chat message: yesterday's people, clips, failures, busiest hour, top failure reports, free disk | `watch.Watch.digest` |
| drift | the clip on show no longer matching the form above it. DOMAIN.md, Table DO-3 | `wastatus/web/app.js` |
| EJS | yt-dlp's JavaScript challenge solver, fetched from GitHub on demand. DOMAIN.md, Table DO-2 | `fetch.py` |
| extension | the Chrome extension in `src/`, manifest version 3, which reads the video in the viewer's own browser and loads WhatsApp's composer | `src/` |
| fMP4 | fragmented MP4: a header (`ftyp`, `moov`) followed by fragments (`moof` and `mdat` pairs), each with its own start time. What YouTube's player appends, alongside WebM | `src/media.js` |
| follow up | an optional second, text only Status with the title and URL, which WhatsApp shows with a link preview card. `--follow-up`; its text is the `.status2.txt` sidecar (D-013) | `cli.py`, `post.post_text` |
| fragment | one `moof` and `mdat` pair in MP4, one Cluster in WebM. DOMAIN.md, Table DO-4 | `src/media.js` |
| grant | a short lived, single purpose token the page hands the extension: `upload` for a capture, `clip` for fetching one clip. 15 minutes, renewed while in use (D-090) | `Accounts.grant` |
| health chip | on the local page, the chip at the top right that opens the health panel: ffmpeg, token provider, WhatsApp Web, another device | `serve.py`, `wastatus/web/app.js` |
| job | one clip being made: on the renderer `queued`, `rendering`, `done`, `failed` or `cancelled`; in the engine, the `Job` dataclass describing what to make | `hosted.Renderer`, `pipeline.Job` |
| ladder | the ordered list of yt-dlp player clients and formats tried until one works (D-005, D-023). The run record's `client` and `format` say which won | `fetch.STRATEGIES_*` |
| link pill | the rounded capsule with a play triangle and `youtu.be/<id>`. DOMAIN.md, Table DO-3 | `compose.py` |
| MSE | Media Source Extensions, the browser API YouTube's player feeds video through, which the extension hooks. DOMAIN.md, Table DO-4 | `src/recorder.js` |
| person | someone who asked for access to SnipShare: `pending`, `approved`, `declined` or `suspended` | `accounts.Person` |
| player client | the client identity yt-dlp impersonates (`mweb`, `web_safari`, `android`, `tv_simply`, the default). DOMAIN.md, Table DO-2 | `fetch.py` |
| PO token | proof of origin token; without one YouTube's media URLs answer 403. Supplied by the bgutil provider. DOMAIN.md, Table DO-2 | `potoken.py`, `scripts/setup_provider.sh` |
| popup | the extension's original interface, which takes a token the owner made. Now the extension's options page | `src/popup.*` |
| renderer | the hosted service that turns an uploaded capture into a clip with the same engine as the local tool. Behind SnipShare | `wastatus/hosted.py` |
| report | a failure the page, the extension or the renderer saw: source, phase, code, versions, never the video. Kept 30 days | `/api/report`, `Accounts.report` |
| run record | one line of `logs/runs.jsonl` per run. See [OBSERVABILITY.md](OBSERVABILITY.md), Table OB-2 | `runlog.Run` |
| safe zone | the bands WhatsApp draws over: the top 12 percent and the bottom 15 percent of the frame (D-014, D-016) | `compose.SAFE_TOP`, `compose.SAFE_BOTTOM` |
| session | on SnipShare, a signed in person's cookie, 30 days, stored only as its hash | `Accounts.start_session`, `Accounts.session` |
| session label | the posting browser's first tab, whose title names the port of this session's page (D-050) | `serve.py` |
| shelf | the row of stickers to hand under the frame: drawings from the library, your own, or GIF results when the GIF shelf is on. Picking several files adds them here rather than placing them (D-035) | `wastatus/web/index.html`, `app.js` |
| sidecar | a file beside a clip sharing its stem: `.caption.txt`, `.status2.txt`, `.json` (the job, read back to reproduce or edit it), `.png`, `.base.png`, `.art.jpg`. Deleted with the clip | `retention.SIDECAR_SUFFIXES` |
| SnipShare | the hosted site: the local page served per person, for people the owner approves | `wastatus/portal.py` |
| `StatusRefused` | raised when WhatsApp's `ack` is below zero: nothing went out, so it is retried at 20, 40 and 80 seconds (D-073) | `post.py` |
| `StatusUnconfirmed` | raised when WhatsApp gave no answer, or its store could not be read. Never retried, because the Status may still be on its way (D-073) | `post.py` |
| stem | a clip's file name without extension: date, song slug and window, for example `20260818_sinna-sinna-murugaiyaa_70-85`, plus `_video` in video mode. Claimed atomically (T-017) | `naming.build_stem`, `naming.reserve_stem` |
| sticker | a drawing from the library (OpenMoji, plus your own in `mine/`), placed in fractions of the frame (D-024) | `stickers.py` |
| token | a key: on the local page, minted per server process and handed to whoever loads it; on the renderer, a person's key made by the owner, stored only as its hash | `serve.py`, `hosted.py` |
| token provider | the bgutil server, on port 4416 by default, that hands yt-dlp PO tokens | `potoken.py` |
| tunnel | the Cloudflare Tunnel (`cloudflared`) that is the hosted site's only way in. No host port is opened (D-092) | `deploy/docker-compose.yml` |
| Turnstile | Cloudflare's check that a visitor is a person, on the access form. Skipped when its keys are not set | `signin.py` |
| upload | one file sent to the renderer in chunks: `audio`, `video` or `artwork` | `hosted.py`, `src/sw.js` |
| variant | one of several clips of the same song, differing in wording or window. DOMAIN.md, Table DO-3 | |
| video mode | `--video`: real frames, blurred or black fill to 9:16, words over them | `Job.video = True`, `render.py` |
| walk | how a capture fills its window without playing in real time: pause, seek, wait for its own store to cover the range, seek to the edge when the player stops reading ahead. Sometimes called the seek walk. DOMAIN.md, Table DO-4 | `src/recorder.js` |
| window | the stretch of the video to clip: a start and an end, at most 90 seconds, validated by one function for every caller | `pipeline.resolve_window`, `timecode.py` |
| workspace | one person's folder on SnipShare and the page's state for it: clips, stickers, GIF key | `portal.Workspace` |

For the abbreviations of the tables (DO-, OB-, IN- and the rest) and which file
answers which question, see [CONTEXT_MAP.md](CONTEXT_MAP.md).
