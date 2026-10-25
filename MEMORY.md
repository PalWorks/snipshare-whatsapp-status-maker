# Memory

Durable context that is not derivable from the code: what is assumed, what has
been measured, and what is still unverified. Decisions with rationale live in
[DECISIONS.md](DECISIONS.md).

**This file was split on 2026-08-20**, when the repository was prepared to be public.
A few rows described the owner rather than the tool: his own devices and their
addresses, how his home network behaved on a particular evening, the titles he works
with, and the decisions still sitting with him. Those live in `MEMORY.private.md`,
which is not in this repository and never will be. Nothing technical was removed, and
where a row here is thinner than it was, the missing half is a personal detail rather
than a measurement. [TASKS.md](TASKS.md) T-022.

## Unverified claims this project rests on

Treat each as `[Unverified]` until a line here says otherwise. Anything built on
top of one of these can be invalidated by a five minute test.

## Table ME-1: Open verification debt

| Claim | Where it matters | How to settle it |
|---|---|---|
| An Android phone can serve as proxy egress for yt-dlp | the free fallback in the phase 2 egress plan | run a proxy on the phone, set `WASTATUS_PROXY`, run the tool |
| A caption URL is tappable in **other people's** clients | whether `--follow-up` is ever needed. Proven on a second device of the owner's, so this is now about other people's clients rather than about WhatsApp | ask someone who saw a status |
| WhatsApp Business Cloud API does not expose Status posting | only matters for phase 2, where there is no browser to drive | check current Meta docs |
| whatsmeow status posting works with an explicit JID list | now moot for the desktop, see [DECISIONS.md](DECISIONS.md) D-012. Only phase 2 could still need it | test against a 3 contact list |
| Evolution API can post a video Status that plays, with a tappable caption | nothing now: phase 2 was built without it, D-085 | send one to your own JID only, then open it on the phone |
| The extension's capture survives ads stitched into the content stream | the hosted path, if YouTube moves ads into the stream | capture across a mid-roll and compare player time with media time, which the recorder reports |
| The extension works on YouTube Music | the music this tool is for | open `music.youtube.com`, add it to the manifest's matches, capture |
| The slow phone downloads are the ones stuck on the DERP relay, and the fast ones went direct | whether the Download route on a phone is usable at all, which is half of the away layout. **Revised 2026-08-19**: the owner reports the same download taking 1 to 2 seconds on some attempts and 10 to 15 minutes on others, with Tailscale on throughout, so the fault is intermittent and the weak Wi-Fi candidate is dead | watch `tailscale status` on the laptop during a download and read `direct` or `relay` for a fast one and a slow one. No longer needs Tailscale turned off. See [TASKS.md](TASKS.md) T-021, parked |
| The tool runs on macOS | the owner's second machine, and half of what [ARCHITECTURE.md](ARCHITECTURE.md) claims portability about. Every OS specific path already branches on Darwin, and the fonts are vendored, but no run on a Mac is recorded anywhere in this repository. **Swept by reading on 2026-08-27** and nothing new was found: two Linux-only tests now skip rather than fail, `/proc` degrades where it is read, and `tailscale ip` off `PATH` is the one untested assumption | work through the macOS first run checklist in [LOCAL_SETUP.md](LOCAL_SETUP.md) |
| WhatsApp's own picker can see a file in the phone's Download folder | the last step of the away route: Download on the phone, then attach in the WhatsApp app | finish one download on the phone and try to attach it. Blocked by T-021, because no download has finished yet |
| A datacentre IP can still fetch a section from YouTube | whether the pipeline can run on a cloud server at all | run `wastatus` once on the VM. This is the first thing to test, before anything is built |
| The 90 second Status cap is enforced by the client, not the server | whether Baileys can post a longer clip than the web composer will take | post a 2 minute clip through Evolution to one JID and see if it plays |

## Settled

| Claim | Verdict | How |
|---|---|---|
| WhatsApp Web can post a video Status | **CONFIRMED, 2026-08-18** | the Status tab's "Add Status" menu offers "Text status" and "Photo and video". Inspected over CDP against a logged in session |
| A video Status can be posted end to end from the desktop, unattended | **CONFIRMED, 2026-08-18** | `scripts/wa_post.py` attached a 30s clip, typed the caption and pressed Send over CDP. Upload took about 40s |
| A caption URL is linkified by WhatsApp **Web** | **CONFIRMED, 2026-08-18** | the posted status's caption renders as `<a href="https://youtu.be/..." target="_blank" rel="noopener noreferrer">`, inside the video status card |
| A caption typed in the **Android** composer is also tappable | **CONFIRMED, 2026-08-19** | the owner posted one from his phone. It reads as plain text on the phone that posted it, and as a link on another device. See the row below, which is the part that misleads |
| **WhatsApp does not linkify your own Status caption on the device you posted it from** | **CONFIRMED, 2026-08-19** | the owner tested from one device, concluded Android captions were not linkified, then found the link live on a second device. The first conclusion cost a design detour. **Any caption check needs a second device** |
| The phone's browser saves the clip to `~/Download` | **CONFIRMED by the owner, 2026-08-19** | Firefox on Android offered `~/Download` in its own save dialog, with the clip's real filename. Where WhatsApp's picker looks is a separate question, still open |
| A page opened on a non-loopback address is recognised as another device | **CONFIRMED, 2026-08-19** | the server was bound to the machine's LAN address for a few seconds and the real page, driven in Chrome, reported `local: false` and put Download first. Loopback in the same run reported `local: true` |
| `--also-on tailscale` resolves and binds a real tailnet address | **CONFIRMED, 2026-08-19** | with Tailscale installed, `tailscale ip -4` gave `100.x.y.z`, one process answered on both that and loopback, and `/api/state` reported `local: false` there and `local: true` on loopback. Previously only checked against a LAN address |
| Killing a render's process group takes yt-dlp's own ffmpeg with it | **CONFIRMED, 2026-08-19** | a real render was stopped 12s in; no yt-dlp or ffmpeg survived, no work directory remained, and `tests/test_proc.py` proves the grandchild case directly |
| WhatsApp overlays the caption across the bottom of the frame | **CONFIRMED, 2026-08-18** | observed on the posted status, colliding with the link pill that used to sit there. The bottom 15 percent is now reserved, see [DECISIONS.md](DECISIONS.md) D-014 |
| The web composer takes a 90 second clip | **CONFIRMED, 2026-08-18** | 9.7 MB at 90s attached cleanly, which settles that the 13.7 MB refusal at the same length was about size, not duration |
| A caption URL is tappable **on a phone** | **CONFIRMED, 2026-08-18** | the owner opened his own posted status on his phone and tapped the caption URL. It opened the YouTube app. This is what retired the two post flow, see D-013 |
| Posting can be driven from the CLI in one command | **CONFIRMED, 2026-08-18** | `wastatus --post` produced a 12s clip and posted it; the upload took 11s and the viewer showed no collision |
| The page's own post button posts a real Status | **CONFIRMED by the owner, 2026-08-18 21:53 and 2026-08-19 00:14** | two Statuses went out from the page, 5s and 4s. This was the last untested path in the tool |
| The composer can be loaded and left for a human to send | **CONFIRMED, 2026-08-19** | `send=False` attached a 15s clip, typed the caption, and stopped. Inspected over CDP: the composer held the file, the caption rendered as a green link, "Status (Contacts)" was the audience, and Send was untouched. Then cancelled |
| Chrome ignores `--remote-debugging-port` on the default profile from 136 | **CONFIRMED, 2026-08-19** | Chrome's own developer blog announcing the change, and this machine runs 150. It is why the posting profile is separate, see D-022 |
| `web_safari` can still deliver media | **REFUTED, 2026-08-19** | `--list-formats` through that client returns four storyboards and nothing else. The ladder entry had been failing on every video-mode run |
| A 720p or 1080p section can be fetched | **REFUTED for DASH, CONFIRMED for HLS 2026-08-20.** The `default` client lists formats 93 to 96 for some videos, and a section cut from 95 came back 1280x720 with its own aac, 1.8 MB for 12 seconds. Whether a video has them is YouTube's to decide. The DASH half stands: | the DASH renditions exist, but `--download-sections` hands their URLs to ffmpeg and googlevideo answers 403. Tried with the native downloader, a single stream, and an audio only stream. Video mode is 360p until this changes, see D-023 |

The lesson worth keeping from all four: the two post flow, the burned in pill, the
footer copy and half of phase 3 were all built on one claim from a secondary
source that nobody had spent five minutes testing. When a claim is load bearing,
test it before designing around it.

## Table ME-3: Evolution API's status endpoint, read from its source 2026-08-19

Read against `EvolutionAPI/evolution-api` on `main`, pushed 2026-07-14, 9.3k stars.
Not yet run against a real instance: every line here is **read, not executed**.

| Fact | Where | Consequence for us |
|---|---|---|
| `POST /message/sendStatus/{instance}`, body `{type, content, caption, statusJidList, allContacts, backgroundColor, font}` | `SendStatusDto` in `src/api/dto/sendMessage.dto.ts` | a video Status is one HTTP call, no browser anywhere |
| For `type: video` the handler passes `{video: {url: content}}` straight to Baileys, with no base64 branch of its own | `formatStatusMessage` | **give it a URL, not base64.** The multipart `file` path sets `content` to a base64 string and hands that to the same `url` field, which is why base64 is the risky shape |
| `type: text` requires both `backgroundColor` and `font` | same | the follow up text Status needs two fields the browser path never asked for |
| `allContacts: true` builds the list from Evolution's **own contact table**, keeping rows that have a `pushName` | same | not WhatsApp's "My contacts" privacy setting. On a fresh instance it throws `Contacts not found` |
| A second, different `allContacts` implementation exists further down, excluding groups instead of filtering on `pushName`, behind an option the first one never sets | `sendMessageWithTyping`, the `status@broadcast` branch | two list builders for one flag. The `pushName` one is the one that runs |
| The send fans out in **batches of 10** JIDs: the first uploads the media, the rest relay the same `messageId` | same | one upload, then N/10 relays |
| Those later batches run under `Promise.allSettled` | same | **a failed batch is swallowed.** Those contacts never see the Status and nothing says so |
| The route carries the maintainers' own `// TODO: Revisar funcionamento do envio de Status` | `src/api/routes/sendMessage.router.ts` | the endpoint is not considered settled by the people who wrote it. Open issues agree |

## Table ME-25: The audit before publication, 2026-10-25

Written **2026-10-25T15:11:42+05:30**.

| Fact | Status | How it was settled |
|---|---|---|
| Chrome stops an extension's service worker when a `fetch()` waits more than 30 seconds for its response | **CONFIRMED** from Chrome's own documentation (the extension service worker lifecycle page) | read 2026-10-25; the extension's requests now give up at 25 s (D-100) |
| Chrome may clear `chrome.alarms` across a browser restart | [Unverified]; the lifecycle page does not say | the alarm is made again whenever a job is driven, so it does not matter which |
| A video clip survives an 800 kbit/s line with the worker stopped mid upload | **CONFIRMED**, 153 s to ready, against a local renderer | `scripts/extension_check.py --throttle 800 --restart-at uploading` |
| A video clip survives the worker being stopped mid download on an 800 kbit/s line | **CONFIRMED**, 117 s to ready | `--throttle 800 --restart-at downloading` |
| Stop while rendering leaves nothing on the renderer and puts the viewer's player back | **CONFIRMED** | `--stop-at rendering`: no jobs after, the player playing where it was |
| ffmpeg 8 with `-protocol_whitelist file -format_whitelist mov,mp4,m4a,3gp,3g2,mj2,matroska,webm` still reads both containers YouTube sends | **CONFIRMED** locally by the capture tests; Debian's 7.1 in the image has had both options for years [Inference] | `tests/test_capture.py` |
| The AGPL-3.0 is compatible with Unidecode (GPL-2.0-or-later), the token plugin (GPL-3.0) and aksharamukha (AGPL-3.0), and PolyForm Noncommercial is not | [Inference], the common reading of the licences, not legal advice | D-099 |
| A web page's Share button can hand a video to WhatsApp's My status on Android | [Unverified] | one real phone, before ROADMAP.md Table RD-1's first idea is built |

## Table ME-24: SnipShare, 2026-10-25

Measured, not read.

| Fact | Evidence |
|---|---|
| A page can reach an extension that lists its origin in `externally_connectable` with `chrome.runtime.connect(id)`, and 8 MB comes back in 0.09 s | Phase 0, docs/hosted-page.md |
| A YouTube tab opened in front, then stepped behind once its player is ready, keeps loading and can be walked | Phase 0: 0.5 s in front, a 30 s window read behind in 8.1 s |
| `google.oauth2.id_token.verify_oauth2_token` verifies a real sign-in from a page on an authorised origin | Phase 0, against the real client |
| Cloudflare in front of Resend's API refuses Python's default User-Agent with 403, error 1010 | the first mail from the server, 2026-10-25 |
| An element with `id="turnstile"` answers to `window.turnstile` and hides Turnstile's own object | the request form's box stayed empty in production until renamed |
| Google's sign-in button sets cookies, such as `g_state` holding JSON, that make `SimpleCookie` drop every cookie in the header | the audit; the session cookie is now parsed by hand |
| A Chrome for Testing left running from an earlier run keeps its debugging port, and the next run talks to it | three confusing runs before `pgrep` showed them |
| Cloudflare injects its analytics beacon into proxied HTML; a page policy without its host refuses it | the live site's console |

## Table ME-23: The browser extension and the hosted renderer, 2026-10-24

Measured, not read. Spike first ([docs/extension-spike.md](docs/extension-spike.md)), then the built thing.

| Fact | Evidence |
|---|---|
| What reaches a SourceBuffer is plain fragmented MP4 or WebM, SABR or not | 30 captures across seven videos parsed without a single unknown box |
| YouTube's player buffers about 20 seconds ahead while paused, and stops | every walk; hence the seek to the edge |
| A seek can abandon a fragment halfway through its payload, then the player calls `abort()` | append logs; the spike's first stitcher read past it into the next header |
| A SourceBuffer can be re-initialised with a different encoding under the same mime type | `C11EZKAFvro`: a 640x360 header, then a 1920x1080 one, in one buffer |
| A hook armed after page load loses what was buffered first, and the player never fetches it again | `C11EZKAFvro` at 0:00 decoded grey until the recorder recorded always |
| A YouTube document loaded while its tab is hidden loads no media at all; one shown before keeps working | the owner's Chrome with its window behind another one |
| Each pre-roll ad plays in a MediaSource of its own, and the content gets a fresh one | three ads in five signed out videos |
| YouTube's own 360p stream (format 18) is offset from its adaptive streams per video, 24 to 95 ms of audio and about a frame of picture | constant per video at every position; the beep and flash video says format 18 is the late one, by 37 ms |
| WhatsApp Web no longer puts `data-icon` on Send; it is `aria-label="Send 1 selected"` in the media composer and `"Send"` in the text one | read off the live page, D-079 |
| The text Status composer's close control is `aria-label="Close status posting view"` | the same |
| An extension can fill WhatsApp's file input through a DataTransfer and the composer opens | the owner's WhatsApp Web, about two seconds |
| Branded Chrome 156 ignores `--load-extension`; Chrome for Testing 156 honours it | both tried |
| A content script's fetch to a loopback address meets Chrome's local network prompt, which a headed browser leaves open | the spike's first upload hung there; the service worker does not |
| Match patterns carry no port: `http://127.0.0.1/*` covers 8790 | `chrome.permissions` refused `http://127.0.0.1:8790/*` |
| On the production host, a 90 second 1080p video clip takes about 2 minutes to render | the engine's own stages, `runs.jsonl` |

## Table ME-22: The GIF that was not in the video, 2026-08-25

| Claim | Status | Evidence |
|---|---|---|
| The GIF failed to export | **WITHDRAWN** | frames pulled from the 20:47 clip at 1s, 3s and 5s show both stickers, the GIF animating across the three. The export was never in question |
| The clip that was posted had no stickers in it | **CONFIRMED from the sidecar and the log** | the 19:43 clip records `"stickers": []` and was posted at 19:53:35. The GIF was placed after |
| Stickers are burnt in at render, in both modes | **CONFIRMED from the code** | `pipeline.produce` passes `decals=still, moving=moving` to `build_card` and `render_card_clip` in card mode exactly as it does to `build_overlay` and `render_video_clip` in video mode. There is no path where a sticker rides along without a re-render |
| The page already said so | **CONFIRMED, and it was in the wrong room** | the Stickers panel reads "Make the clip again to draw these into it". The four buttons that act are in a different card |
| A second take of a video clip was labelled an artwork card | **CONFIRMED, a real bug, fixed** | `naming` writes the marker before the collision suffix, so `..._video-2` ends in neither alone. `endswith("_video")` was False and the window was lost too. Every clip made after the first that day |
| Stripping the tail before matching the window | **WRONG, caught by testing the other shapes** | the window's own end is `-\d+` too, so `(?:-\d+)?$` ate it and `_0-30` became `_0`. The pattern has to describe what may follow the window instead |

## Table ME-21: The cross on a Recent tile, 2026-08-25

Everything here was driven against the running page over the debug protocol, not
reasoned about.

| Claim | Status | Evidence |
|---|---|---|
| The server needed no work | **CONFIRMED** | `/api/clip/delete` has existed since T-016 with six tests on it. Deleting a copied throwaway through the new cross removed all five files of its group and left the other twenty clips alone |
| A `<button>` inside a `<button>` would not have been reported | **CONFIRMED by construction** | the parser unnests them into siblings, so the cross lays out beside the tile and `closest(".tile")` finds nothing. It reads as a styling bug. This is why the tile is a `<div>` |
| The cross is the hit target, and so is the air around it | **CONFIRMED, measured** | `elementFromPoint` returns the cross at its centre and 5 pixels outside the disc, and the thumbnail elsewhere. 24 pixel disc, 44 pixel target on a coarse pointer |
| The armed fill was not applying | **WITHDRAWN, a measurement artifact** | `backgroundColor` read as unchanged because the tab was backgrounded, where transitions never advance. `document.visibilityState` was `hidden`. Brought to the front it reads `rgb(242, 184, 181)`. The transition on the fill was dropped anyway: a safety signal should not fade in |
| White on a `--danger` fill is unreadable in one palette | **CONFIRMED from the tokens** | `--danger` is `#b3261e` light and `#f2b8b5` dark. `--danger-bg` inverts with it, so the pair is legible either way. Caught before it shipped |
| The tick and the cross do not collide | **CONFIRMED, measured** | 7 pixels from opposite edges, 60 pixels of clear air between them, `overlap: false` |
| Deleting the clip on show leaves nothing pointed at a missing file | **CONFIRMED** | player cleared, `src` removed, "nothing yet" back || Two of the owner's real clips were deleted at 18:42 | **CONFIRMED from the log**, cause not established | `video-6` and `prince-rama-varma...` at 18:42:32 and 18:42:39. The automation's last press on a cross was a single one at 18:41:45, which only arms, and the three scripts that ran between then and the deletes contain no press at all. At 18:42:45 the page loaded a clip into the player, which no script did. Both are re-makeable from `logs/runs.jsonl`, which keeps the link, the window and the mode but not the wording |


## Table ME-20: Where the frames land, 2026-08-25

| Claim | Status | Evidence |
|---|---|---|
| The top text sat against the header with a void beneath it | **CONFIRMED, measured on his own clip** | two lines at 260 to 348, the picture starting at 626. Thirty pixels of clearance from the header band, 278 pixels of nothing below the words |
| Anchoring it to the picture needs Python to know the picture | **CONFIRMED by construction** | the position was `min((H-h)/2, floor-h)` inside the filter graph, from a source shape only ffmpeg had looked at. Nothing in Pillow could ask where it ended up |
| Python's arithmetic matches what ffmpeg paints | **CONFIRMED by rendering and measuring** | five aspect ratios: 2.35:1 at 730, 16:9 at 636, 4:3 at 434, square and portrait at 230, each matching `picture_rect` to the row |
| Rounding to the nearest even, not down | **CORRECTED** | a 16:9 source scaled to 1080 wants 607.5 rows. Truncating gives 606 and loses a row on half of all sources for nothing; 608 is the honest answer and is what ffmpeg's own `force_divisible_by=2` gave |
| The measurement costs nothing extra | **CONFIRMED** | the crop probe already scanned three frames and read their size to detect bars. It returns that size now instead of discarding it |

## Table ME-19: The page's own window, and the label in video mode, 2026-08-25

| Claim | Status | Evidence |
|---|---|---|
| The page was opening in a different browser from the label | **CONFIRMED** | `webbrowser.open` asks the desktop for its default browser, which here is a Chrome on another profile. Reported with a screenshot showing the two side by side |
| Chrome takes a new tab over the debug protocol | **CONFIRMED against the running browser** | `PUT /json/new?<url>` returned a target id and the tab appeared, in both the raw and the percent encoded query form: Chrome unescapes it. `GET` is refused since Chrome 111 |
| The adopted path works end to end | **CONFIRMED 2026-08-25** | a second instance on port 8799 adopted the browser already on 9230 and its page appeared as a tab in that window, beside the 8765 label. Both were then closed |
| The footer draws in video mode | **CONFIRMED** | rendered `build_overlay` with a footer set: it paints, and always has |
| The label does not draw in video mode | **CONFIRMED, and silently** | `build_overlay` passes `eyebrow_top=None`, and `_draw_text_layer` skips the eyebrow on None. No error, no note, an empty preview. The box took the sentence and threw it away |
| The label was drawn but unreadable: 1989 pixels wide in a 1080 pixel frame | **CONFIRMED, measured off his own clip** | 91 characters at size 28 bold with 6px tracking. Centred, so it started at x=-454 and ended at x=1534 and only the middle was on the frame. Reported as "still not able to see anything", which is what that looks like |
| Wrapping has to count the letterspacing | **CONFIRMED** | `textlength` does not see tracking, and at 6px over 91 characters that is 546 pixels, a third of the drawn width. Wrapping without it overflows every line |
| The second line and the footer were never wrapped either | **CONFIRMED, measured** | "Sounds of Isha Official Channel for Devotional and Classical Music" is 1253 pixels at size 38, and a footer of similar length 1209, in a 1080 pixel frame with 880 of margins. Only the title had ever been wrapped |
| There is no fixed allowance left to give them | **CONFIRMED by arithmetic** | video mode has 348 pixels between `VIDEO_TITLE_TOP` and `SAFE_BOTTOM`, and a three line title plus one channel line plus one footer line already spends 338. So they take what is left rather than a constant |
| The band under WhatsApp's header was empty in video mode | **CONFIRMED** | the frames are centred, so a 16:9 source occupies 636 to 1243 and everything above 636 is blurred fill. Nothing was ever drawn there |
| The frames can give up room at the top as well | **CONFIRMED on a real render** | a square source started at `SAFE_TOP`, 230, and stops at 388 with two lines of top text. A 16:9 source does not move at all, because its centred position is already below the ceiling |
| The picture can pay for the label without every clip paying | **CONFIRMED by construction** | `compose.video_picture_bottom` reads the floor off the text: 1244 with no label, 1174 with one. A clip without a label renders exactly as it did |

## Table ME-18: Frames, ports and the sticker panel, 2026-08-24

| Claim | Status | Evidence |
|---|---|---|
| Card mode cannot be written on by its own title, video mode could | **CONFIRMED** | `card_box` anchors the card `CARD_GAP` above `CARD_TITLE_TOP`, so it moves with the words by construction. `--video` overlaid at `(H-h)/2`, an expression naming nothing about the words |
| The trigger is the source's shape, not the title's length | **CONFIRMED** | the title's top is fixed in both modes, 1005 and 1284, and the block grows downwards. Centring is safe only down to 5:3. A one line title over a 4:3 source is already on the picture |
| How far in it reached | **MEASURED 2026-08-24** | picture bottom edge: 2.35:1 at 1190, 16:9 at 1264, 4:3 at 1365, 1:1 at 1500, portrait the whole frame. The title starts at 1284 |
| The owner's own last two posts were never affected | **CONFIRMED** | their source trims to about 2.35:1 and painted 730 to 1188, measured off `.base.png`. This is why it had not been seen |
| The fix moves nothing that was already clear | **CONFIRMED** | `min((H-h)/2, 1244-h)` is the centred value for anything wider than 5:3. Re-measured after the change: 2.35:1 unchanged at 1190, 16:9 down 20 pixels, everything else clamped to 1244 |
| Stickers are in the clip's pixels, not a layer over it | **CONFIRMED** | still ones through `stickers.paste` into the card PNG, animated ones as ffmpeg `overlay` inputs in `_moving_chain`. There is nothing to edit after the render, exactly as with the words |
| Both GIF providers' keys were configured all along | **CONFIRMED** | `/api/state` on the running server returned both `choices`. The chooser was not missing; it is drawn only on the GIFs shelf and only above 901 pixels |
| The provider credit cannot be removed | **CONFIRMED, and it is a terms question not a taste one** | both providers require a visible mark, and KLIPY additionally requires the search box to read "Search KLIPY". Made smaller and moved onto the hint line; not removable |
| A background tab does not cost the posting route anything | **CONFIRMED by construction** | `Page.__init__` calls `Page.bringToFront` before it touches the composer, which is why the label can be Chrome's first URL and WhatsApp Web its second |

## Table ME-17: The live word preview, 2026-08-22

| Claim | Status | Evidence |
|---|---|---|
| Drawing the words costs a fraction of making the clip | **CONFIRMED** | `build_card` 0.86s and `build_overlay` 0.10s, against a 30.7s and 66.5s re-make on the same machine. The whole route, request to JPEG, is 0.86s and 0.10s |
| Caching the download would not have solved it | **CONFIRMED, and it was the obvious idea** | download is 11 to 12s of a 30 to 66s total. The render is 16.6s and 52.5s |
| A full size preview is too heavy to send | **CONFIRMED** | 1254 kB for a card and 694 kB for a video frame as PNG, redrawn on every pause in typing, into a box 300 pixels wide. At 720 pixels and JPEG q86 they are 73 kB and 70 kB |
| The preview matches the clip because it is the same code | **CONFIRMED by construction** | `App.preview_jpeg` calls `compose.build_card` and `compose.build_overlay`, the two functions `pipeline.produce` calls. There is no second implementation to keep in step |
| A video clip's textless background can be made from the render's own filters | **CONFIRMED** | `background_still` reuses the crop, blur sigma 28 and brightness -0.20 of `render_video_clip`, leaving out only the overlay input. A test asserts the graph still matches |
| The preview costs about 74 kB on disk per card clip and 640 kB per video clip | **CONFIRMED** | measured on two real renders. Both are pruned with their clip |
| What the preview cannot show | **KNOWN** | a card clip's waveform, drawn by ffmpeg from the audio. And nothing at all before a clip exists, because card mode would need the artwork downloaded and video mode the video |

## Table ME-16: The GIF panel and the page's own state, 2026-08-22

| Claim | Status | Evidence |
|---|---|---|
| KLIPY offers four renditions and only two are useful here | **CONFIRMED** | `xs` 127x90 at 134 kB, `sm` 220x157 at 376 kB, `md` 498x355 at 2343 kB, `hd` the same size as `md`. `md` and `hd` are indistinguishable in dimensions on the results sampled |
| GIPHY's `fixed_width_downsampled` is the best value either provider offers | **CONFIRMED** | 200x190 at 121 kB, against `fixed_width_small` at 100x96 and 85 kB and `fixed_width` at 200x190 and 337 kB. Twice the resolution of the small one for a third more bytes |
| The desktop shelf draws 172 pixel cells | **CONFIRMED** | measured in the page at 1400 pixels wide. Before the change, 62 pixels |
| `loading="lazy"` does not fire in headless Chrome 151 | **CONFIRMED, and it looks exactly like a broken route** | every thumbnail reported `naturalWidth` 0 and the server logged no image request at all. Forcing one image to `eager` made the request and it loaded. Not a bug in the page |
| A link's video id survives every spelling the tool accepts | **CONFIRMED** | `youtu.be/X`, `watch?v=X`, `watch?v=X&t=30s`, `/shorts/X` and `music.youtube.com/watch?v=X` all reduced to `X` in the running page |
| The reported stale-title bug is the reload path | **CONFIRMED** | words stored for video A, page reloaded, a different link pasted: before, nothing was cleared because the guard asked `current.job.url` and there was no clip on screen |
| Render dominates a clip, not the download | **CONFIRMED** | from his own `runs.jsonl`: a 90 second video clip is probe 1.4s, download 12.3s, **render 52.5s**. A 30 second one is 1.7 / 11.4 / 16.6. Caching the download would save under a fifth |
| Chrome writes `bind() failed` and then a `[::1]` listening line to stderr | **CONFIRMED** | reproduced deliberately on a busy port with `logs/chrome.log` capturing. Both lines present, in that order |

## Table ME-15: Chrome, debug ports and Instagram, 2026-08-22

| Claim | Status | Evidence |
|---|---|---|
| KLIPY works with the owner's key on the content he actually posts | **CONFIRMED** | Tamil cinema searches returned real, relevant results. `thalapathy vijay`, `ilayaraja` and `master vijay` all found matching GIFs |
| KLIPY's documented rendition sizes are wrong by roughly six times | **CONFIRMED** | `md` measured over 132 results across five searches: median 1296 kB, mean 1714 kB, p90 3352 kB, max 10070 kB, against a documented "about 200 kB". Two of the 132 exceeded the 8 MB animated sticker ceiling and would be refused on picking |
| A shelf costs about the same on either provider | **CONFIRMED** | thumbnails measured 107 kB mean on KLIPY, 113 kB on GIPHY, twelve fetched from each on the same query. The shelf cost is the feature's, not one provider's |
| KLIPY's catalogue is thinner than GIPHY's on some queries | **OBSERVED, not quantified** | `ilayaraja` returned 12 on KLIPY against 19 on GIPHY, while several Tamil cinema queries returned the full 30 on KLIPY. One query is not a measurement |
| The login survives killing and restarting the posting browser on a different port | **CONFIRMED** | Chrome closed on 9222, restarted by the server on 9230, and `/api/state` reported `ready` with no QR code. The login lives in the profile, not the session |
| Chrome refuses remote debugging on the default profile, permanently | **CONFIRMED** | launched against `~/.config/google-chrome`: `DevTools remote debugging requires a non-default data directory. Specify this using --user-data-dir.` No port opened. A scratch `--user-data-dir` opened one immediately, `Chrome/151.0.7922.169` |
| The debug switch cannot be added to a Chrome that is already running | **CONFIRMED** | it is read at launch. There is no protocol to ask a live browser to start one |
| A taken debug port makes Chrome bind IPv6 only and print success | **CONFIRMED** | `bind() failed: Address already in use (98)` followed by `DevTools listening on ws://[::1]:9225`. `127.0.0.1:9225` was the other browser's, `[::1]:9225` was the intended one |
| Chrome flattens its own argv, so `/proc/PID/cmdline` is space separated and not NUL separated | **CONFIRMED** | `/proc/151793/cmdline` read back as one string. A NUL-only split found nothing on a machine with two debug browsers plainly running. Both shapes now handled |
| `port_owner` names the right browser on the live machine | **CONFIRMED** | 9225 named `chrome, profile antigravity-chrome-profile-someone (pid 151793)`, 9222 named `chrome, profile chrome-wastatus (pid 157573)` |
| `WASTATUS_ALSO_ON=tailscale` binds the tailnet with no flag typed | **CONFIRMED** | bound `127.0.0.1:8799` and `100.x.y.z:8799`, and printed the `Also on` line |
| A browser already open on the posting profile is adopted rather than duplicated | **CONFIRMED** | ports set to 9230-9235 with a wastatus Chrome on 9222: `already open on debug port 9222, using that`. With a scratch profile nothing was using: `Started google-chrome on debug port 9230` |
| yt-dlp cannot extract any Instagram URL anonymously | **CONFIRMED, and it is not per post** | yt-dlp 2026.07.04 returned `Instagram sent an empty media response` for a real looking shortcode **and** for an invented one that cannot exist, so the whole anonymous path is closed, not one post's permissions |
| Meta's oEmbed endpoint answers with no access token | **CONFIRMED** | `graph.facebook.com/v23.0/instagram_oembed` returned a structured `Media Not Found` rather than an auth failure. It returns embed HTML, never a media file |
| Whether the official API supports personal accounts | **UNVERIFIED, and the sources disagree** | Meta's platform page says Business and Creator for both login variants. Several third party write ups claim personal accounts work with Instagram Login. Resolve by switching an account, not by reading more |
| Whether yt-dlp with the owner's cookie extracts Instagram here | **UNTESTED, deliberately** | it needs a session cookie off his browser, which is not something to take without asking. See [docs/instagram.md](docs/instagram.md) |

## Table ME-14: The GIF picker, built 2026-08-21

| What was measured | The number, and what it settles |
|---|---|
| GIPHY key, live | works. 30 results a search, thumbnails 200 px, kept copies capped at **2 MB by GIPHY itself** so they cannot break the animated ceiling |
| KLIPY key, live | works, at `api/v1/{key}/gifs/search`. `xs` **90x90 12 kB** for the shelf, `md` **640x640 about 200 kB** for keeping, up to 4.6 MB on some results |
| Which fits better | **KLIPY**, unexpectedly. Its `xs` is almost exactly the 96 px the thumbnail cache already uses, and its only mandatory attribution is the search box saying "Search KLIPY" rather than a mark on screen |
| Tenor | `403 unregistered callers`, and the owner reports onboarding closed outside Google's ecosystem. Not a route |
| Pixabay | needs a key, shown on its own docs page once logged in. Irrelevant: **the API has no GIF search**, `image_type` being only all, photo, illustration, vector |
| Thumbnails in a real browser | **30 of 30 loaded**, every one served by this machine. It was **0 of 30** on the first pass: `/api/gif` was missing from the routes that take the token as `t=`, and an `<img>` cannot send a header |
| Switched off | `state.gifs` empty, both routes **404**, no toggle, no credit line, and 48 drawings still on the shelf |
| A GIPHY beta key | **100 calls an hour**, named on their dashboard and now named in the error |

## Table ME-13: Groundwork on a GIF picker and on framing, 2026-08-21

| What was measured | The number, and what it settles |
|---|---|
| A GIF search without an API key | **there is none.** Tenor answers **403**, `Method doesn't allow unregistered callers`; GIPHY answers **401**. Wikimedia Commons needs no key and returned **one GIF in five results**, encyclopaedic ones, so it is not a substitute |
| What the tool talks to today | yt-dlp to YouTube, YouTube's thumbnail host, and a PO token helper on loopback. **Nothing else.** A GIF picker would be the first third party, and it would see what is searched for |
| Whether the Upload dialog offered GIFs | **it did not.** `accept` predated animated stickers and listed png, webp and jpeg. The server took a GIF happily when one reached it: posting a two frame GIF returned `moving: true` |
| What a re-crop costs today | **37 to 111 seconds per attempt**, across 18 video renders: 5 to 13 seconds to download the section, 23 to 95 to render. The work directory is deleted at the end of every run, so nothing is reusable |
| What keeping the source section would cost | across 70 sections: median **1.5 MB**, largest 7.9. Twenty of them is about **30 MB**, against 32 GB free |
| How much picture a 16:9 to 9:16 crop discards | about **68% of the width**. The blurred fill exists because of that, and it is why filling is a per clip judgement rather than a better default |
| Whether filling the frame would break the text | **no.** Video mode already paints a gradient scrim from 63% of the height down, so text survives a bright frame either way |

## Table ME-12: Groundwork on other music links, 2026-08-21

| What was measured | The number, and what it settles |
|---|---|
| Whether this tool validates a URL at all | **it does not.** The link goes from the form to yt-dlp untouched. So anything yt-dlp supports, this supports, and anything it does not, fails as a yt-dlp error |
| YouTube Music | **already works, unchanged.** `music.youtube.com/watch?v=`, with `&si=` and with `&list=`, all probe correctly. It is the better link to paste: a `- Topic` upload gives `artist="Project Samskriti"` where the channel is only `Release - Topic` |
| A playlist link | accepted, and wrong. `video_id` is the playlist id, `duration` is **0.0**, and `watch_url` is `https://youtu.be/PL...`, a dead link that would go out in a caption |
| Spotify | `[DRM] The requested site is known to use DRM protection. It will NOT be supported.` There is no route to the audio |
| Spotify oEmbed, credential free | returns **title and a thumbnail only**. No artist, no duration. Artist and duration need the Web API and therefore a client id and secret |
| Whether a song can be matched from title and artist | **no, not for this library.** `Project Samskriti Veyuru Tholipangan` returns the wrong track first, and it is **1 second** from the right duration, so a length filter does not rescue it. Title alone returns nothing right in the top three |

## Table ME-11: Measurements, 2026-08-21

| What was measured | The number, and what it settles |
|---|---|
| The handle set with a mouse | cross at the box's top right, grip at the bottom right, stem **22 pixels** above the top centre of a 76 pixel box |
| The handle set under touch emulation | **cross only**, 24 pixels drawn and **44 to hit**. D-038's measurement holds: two touch targets need 88 pixels and a default sticker gives 76 |
| Resize by the grip | 0.200 to **0.428** on a 34 pixel drag, centre unmoved. Resize is about the centre, not the corner held |
| Rotate by the stem | 0 to **90 degrees**, landing exactly on square through the same `settle` the two finger twist uses |
| Selection outlives the old timer | still marked at **2 seconds** idle, where `MARK_IDLE` cleared at 1.4 |
| Pinch and twist after the rebuild | 0.200 to **0.344**, 0 to **40 degrees**. D-033's gestures survived the box |
| What headless Chrome reports for pointer | `hover: none`, `pointer: none`, `any-pointer: fine` false. **Neither fine nor coarse**, so a media query written as "not a mouse" matches a desktop browser. Write the positive test |
| Where the preview sits at 412 pixels wide | about **1000 pixels down**, outside the viewport. Input events dispatched at its rect hit nothing until the frame is scrolled into view |
| The control check against the live tab | **2.2 seconds**, correct, menu closed afterwards. Forced to fail, it named `Photos & videos, Text` and the file to widen |

## Table ME-10: Measurements, 2026-08-20 night

| What was measured | The number, and what it settles |
|---|---|
| Last successful post, and the first failure | **2026-08-19 22:53:04** and **2026-08-20 19:42**. WhatsApp Web renamed the Status controls somewhere in between. Nothing in this repository changed in that window: `git log -S "Photo and video"` returns one commit, `293bae7`, from the first week |
| What WhatsApp calls them now | `Photos & videos` and `Text`, both `role="menuitem"`, both behind a button labelled `Add Status`. Read off the live DOM rather than guessed |
| Why it arrived as "suddenly" | the Chrome holding the WhatsApp tab restarted at **18:55** after the reboot and fetched a newer build. The tab had been running the older one in memory since before that. A reboot is what made a silent rename visible |
| The desktop's separate fault | **every request 403 from 19:42 onward**. The tab was loaded before the 19:08 restart and held that process's token. The server had not moved: PID 7696, up since 19:08 |
| The 501s in the log | `Unsupported method ('{"url":...}POST')`, twice. Not a client bug: the 403 path never read the POST body, and keep-alive then parsed the next request line out of the middle of it. Reproduced in a test that fails without the fix |
| The fix, against the live tab | composer opened, caption `https://youtu.be/n_VSKDuxDF0` typed, **nothing sent**, composer backed out clean |
| The mobile layout over the tailnet | `data-where=away`, every endpoint 200, the clip served whole at **10,175,637 bytes**, and **Load into WhatsApp** completed in about 35 seconds. Make and Stop both worked, and Stop left `out/` at 20 clips |

## Table ME-9: Measurements, 2026-08-20 evening

Taken after the owner rebooted and could not reach the page from his phone.

| Fact | Value |
|---|---|
| **The cause was the flag, not Tailscale** | the server was running as `python -m wastatus serve` with no `--also-on`. One socket, `127.0.0.1:8765`. The tailnet address answered `000`, which is a refused connection and not a timeout |
| Tailscale itself was healthy throughout | `tailscale status` listed all three machines, and `tailscale ping` to the phone pongged in **294 ms via the LAN address**, a direct path with no DERP in it |
| The startup output had already said so | every earlier run in `logs/serve.out` carries an `Also on http://100.x.y.z:8765/` line. The run started after the reboot does not. **That line is the check**, and it costs nothing to look at |
| After restarting with the flag | both sockets bound on one process, loopback and the tailnet address both **200**, `app.js` and `app.css` **200** over the tailnet, `/api/state` without a token still **403**, and `also_on` and the host name both reported back by `/api/state` |
| Health at that moment | ffmpeg **true**, provider **true**, WhatsApp **ready** on Chrome 150 port 9222, 12 clips in Recent |
| **What the evening actually cost** | not a defect. `--also-on` is per process by design, D-027, and the walkthrough in [LOCAL_SETUP.md](LOCAL_SETUP.md) named only the plain command while the flag sat eighty lines below. A reboot then produces a laptop only page and no message explaining it. Documents fixed the same evening; the behaviour deliberately left alone |

## Table ME-8: Measurements, 2026-08-20 afternoon

Taken while clearing T-008, T-009, T-014, T-017 and T-018.

| Fact | Value |
|---|---|
| **WhatsApp's real media ceiling** | **10 MiB, 10,485,760 bytes.** Bisected against the live composer with 90 second probes that differed only in size: 10,311,640 and 10,452,278 accepted, 10,519,352 and 10,650,175 and 11,013,670 refused. The two middle ones sit 33 kB either side of the line |
| How a refusal presents | the composer takes the file and never opens its editor, so `wa_post.py video` times out waiting. A file that is accepted opens it in a second or two. That difference is the whole instrument |
| The encoder overshoots its budget by about 2 percent | a 9.5 MB budget produced 9,684,891 bytes at 90 seconds and 9,690,149 at 60. The budget sets a maxrate; it does not cap the file, which is why the new budget is 10,000,000 and not 10,485,760 |
| **HLS renditions can be section downloaded** | format 95 through the `default` client: 1280x720 h264 with its own aac, 12.08 seconds, 1,797,815 bytes, about 5 seconds of download. DASH is still 403 for ffmpeg, tried again the same day |
| Whether a video has them is the video's property, not the caller's | a popular music video offered 93 to 96 on three consecutive asks; one of the owner's own uploads offered none on three. Quiet gaps of 3, 4 and 5 minutes made no difference, so it is not rate limiting |
| ...and it can change under you | that same upload **did** offer 95 earlier the same day, and a real 5 second section was fetched from it, before stopping. So the ladder tries and falls through rather than assuming either way |
| The dedupe threshold cannot be tuned | `Abirami Andhadhi` and `Abhirami Anthathi` are one name and score **0.846**; `Sivapuranam` and `Sivapuram` are two words and score **0.900**. A duplicate scoring below a non duplicate means no single threshold gets both right. 0.85 keeps the safer failure: an untidy title rather than a lost word |
| The output name race is real | eight threads asking `unique_stem` for the same name in the same instant all got it. With `reserve_stem` they get eight different names, and the old behaviour is what the new test catches |

## Table ME-7: The owner's phone, driven directly over USB, 2026-08-20

The first time this project has been tested **on the phone it is for**, rather than
reasoned about from the laptop. A Galaxy M30, Android 10, over adb, with Chrome's
debug socket forwarded so the page could be read and driven the same way the desktop
browser is.

| Fact | Value |
|---|---|
| Its keyboard | **Samsung Keypad**, not Gboard. Gboard is not installed. Its GIF panel is GIPHY. The owner's other phone, a OnePlus 11, has Gboard and is untested |
| `isSecureContext` on the tailnet address, on the phone itself | **false**, `navigator.clipboard` **undefined**. The desktop measurement was right |
| The caption **Copy** button, after the `execCommand` fallback | **works**, and the text was then pasted back into a field with `KEYCODE_PASTE` to prove the clipboard really held it. It had never worked on this phone before |
| Picking a GIF from the keyboard, **Chrome 151** | **refused**: a toast reading "Can't enter this content here". Nothing reaches the page, nothing reaches the clipboard, and a long press offers no copy or share |
| Picking a GIF from the keyboard, **Firefox 150** | **works.** `paste` carries `text/plain` only with `files=[]`, then `beforeinput` `insertFromPaste`, then an `<img>` with a `data:image/gif;base64` src appears in the box. 156,930 characters for a 117 kB GIF |
| The keyboard's GIF and sticker buttons against the page's ordinary `<input>` fields | **greyed out**. Against the `contenteditable` box they light up. The box is doing exactly the job it was added for |
| The whole path on the real page, in Firefox | the GIF became `mine:pasted`, served back as `image/gif` at 116,877 bytes, appeared first on the shelf with its "moves" marker, and sat animating on a real clip's frame |
| The sticker box's border before this | invisible until focused, on this screen. Redrawn from the accent colour at 45 percent |

## Table ME-5: Measurements, 2026-08-20

| Fact | Value |
|---|---|
| ffmpeg on this machine | **8.0.1**, with `overlay`, `rotate`, `scale`, `fps` and `colorkey`, and decoders for `gif`, `apng` and `webp`. Still no freetype or libass, which is why text goes through Pillow |
| Looping an animated GIF over a clip | **works.** `-stream_loop -1` plus `fps,scale,format=rgba,rotate=a:c=none` into `overlay=shortest=1`. A 12 frame 0.96 second GIF rode a 5 second clip, transparency held, and the animation was confirmed by counting lit pixels per frame: 3196 up to 10931 and back down |
| Reading an **animated WebP** with this ffmpeg | **fails**, `image data not found`, width 0, lossy and lossless alike. A **still** WebP reads normally. GIPHY and Tenor both serve animated WebP, so anything from them needs converting first |
| Reading an animated WebP with **Pillow** | works, 12 frames, RGBA. The converter is already a dependency |
| Where stickers are composited today | card mode pastes them onto the 1620 card **before** the `zoompan` slow zoom, so they zoom with it. Video mode pastes them onto the transparent overlay, composited at `0:0` with no zoom. **Settled**: animated ones are overlaid onto the card stream before `zoompan` too, so both travel together. See D-036 |
| An animated overlay against the same sticker pasted by Pillow | **identical**, to the pixel. Same bounding box, same centroid, same growth factor across the clip, for a rotated asymmetric shape. This is what proves the ffmpeg rotation sign and the fraction arithmetic agree with `stickers.paste` |
| What an animated sticker costs, 4 second card clip | one adds about 1 second of encode and 56 kB; three add about 3.4 seconds and 61 kB. Small because the clip already carries a slow zoom and a reacting waveform |
| Pillow drops a GIF frame identical to the one before it | which makes a test fixture built from one repeated picture arrive back as a **still**. A GIF frame is also composited onto the one before it, so a shape that only shrinks leaves every composited frame identical too. Both cost time on 2026-08-20 and both are written into `tests/test_stickers.py` |
| Secrets committed to this repository | **none.** The page token is per process from `secrets`, there is no API key anywhere, and `WASTATUS_PROXY` is an environment variable. What is in here is the owner's own addresses, username and machine name. See [TASKS.md](TASKS.md) T-022 |

## Table ME-6: Measurements, 2026-08-20 morning

| Fact | Value |
|---|---|
| `window.isSecureContext` on `http://100.x.y.z:8765` | **false**, and `typeof navigator.clipboard` is **`undefined`**. Not blocked: absent. Only https and loopback are trustworthy origins, and a tailnet address is neither |
| What that broke | the caption's **Copy** button did nothing at all on the phone, and said nothing, because the failure path set a `title` and a phone has no hover. Fixed with an `execCommand` fallback, see [DECISIONS.md](DECISIONS.md) D-037 |
| The fallback, verified end to end | the tick appeared on the tailnet address and the **system** clipboard really held the caption afterwards, read back outside the browser with `xclip` |
| A default sticker in the phone preview | 60 CSS pixels drawn, 76 to hit, at 412 pixels wide. Two 44 pixel touch targets need 88 pixels between them, so **two touch handles cannot both fit on a default sticker**. This is the number that decides the on-canvas handle design |

## Table ME-4: Measurements, 2026-08-19

| Fact | Value |
|---|---|
| Sticker shelf of 40, full size | 402 kB |
| The same shelf at `w=96` | 191 kB, a 52 percent saving. [TASKS.md](TASKS.md) T-020 had estimated an order of magnitude, which was wrong: flat OpenMoji artwork already compresses well |
| A stopped render, from Stop to the task ending | under half a second, with the kill going to the process group |
| A 15s card clip on this machine today | 35 seconds end to end, 5.65 MB. Slower than the 25s measured on 2026-08-18, same shape |
| `--also-on tailscale` against a real tailnet | works. `tailscale ip -4` resolved, both sockets answered 200, and `/api/state` reported `local: true` on loopback and `local: false` on `100.x.y.z` in the same process. First time this path was run against real Tailscale rather than a stand in |
| An 8.15 MB clip leaving this machine over HTTP | 9 ms, about 900 MB/s, the same on loopback and on the tailnet address. Whatever makes a phone download slow, it is not the server |
| A 15 second card clip through the redesigned page | 5.5 MB, made end to end while driving the real page over CDP |

## Measured facts

These were observed on this machine, not inferred.

## Table ME-2: Measurements, 2026-08-18

| Fact | Value |
|---|---|
| End to end wall clock, 15s card clip | about 25 seconds |
| Stage breakdown | 4s metadata, 5s download, 0.6s card, 15s encode |
| Data pulled per 15 second clip | about 1.2 MB |
| Output size, 15s | 5 to 6 MB |
| Reference ffmpeg | 8.0.1, no freetype, no libass, no drawtext, 481 filters |
| Working client and format on every video tried | `mweb` format 18, muxed 360p, 128 kbps AAC, which is the floor and always works. Since 2026-08-20 the video ladder tries `default 95/96` first, which is 720p when that video has HLS renditions |
| Provider install footprint | about 209 MB with `node_modules` |
| First run penalty | minutes, while the JS solver is fetched from GitHub and cached |
| Wall clock scales with clip length | a 30 second card clip takes about 58 seconds, of which 34 is the encode |
| Offline test suite | 327 tests, about 29 seconds. The page's server tests bind real sockets |
| Card composition, with the shadow blur | about 0.8s, up from 0.6s |
| The measured letterbox case, a 2.35:1 music thumbnail | 1280x720 with an 85px black bar above and 84 below a 2.35:1 picture |
| The same video's frames | letterboxed too, cropped to 1280x544 |
| Padding bar detection | 5ms on a 1280x720 thumbnail |
| A 15s card clip through the local page | 42 seconds end to end, same as the command line |
| Output size, 60s | 9.7 MB at the derived bitrate, down from 21.4 MB |
| WhatsApp composer, measured | accepted 9.4 MB at 30s, 8.8 and 9.7 MB at 60s, 9.7 MB at 90s; refused 13.7 MB at 90s and 21.8 MB at 60s |
| Effective size ceiling | **10 MiB, 10,485,760 bytes**, bisected 2026-08-20. 10,452,278 accepted, 10,519,352 refused, 33 kB either side of it. Every probe was the same 90 seconds and differed only in size, so it is a size limit and not a length one |
| Upload time at 9.7 MB | 4 to 5 seconds |
| An auto-generated music upload | channel is `Release - Topic`, artist is the real name |
| Status upload, 4.1 MB and 12 seconds | 11 to 17 seconds |
| Status upload, 9.4 MB and 30 seconds | 4 seconds on a good connection, about 40 on a bad one |
| This video's fetchable video stream | 640x360 on the run that mattered, so `--video` upscales and looks soft. Card mode uses the 1280x720 thumbnail |
| Status upload, 9.3 MB and 30 seconds | about 40 seconds |
| A background Chrome tab is throttled hard enough to time out the composer wait | the driver calls `Page.bringToFront` first, and restores a minimised window |
| Loading the composer without sending | 8 seconds, and no upload at all. The upload only happens on Send |
| A 15s card clip through the page, measured again | 32 seconds, of which 27 is the encode |
| OpenMoji 17.0.0, released 2026-04-23 | 4,495 drawings at 618 pixels, 45 MB zipped, plus a 2.2 MB keyword file. CC BY-SA 4.0 |
| Of those, searchable after dropping skin tone variants and anything with no file | 2,465 |
| A sticker adds nothing measurable to a render | it is one alpha composite onto a canvas that was being built anyway |
| Chrome sends `Origin` on every same-origin POST | so an origin check against a constant refuses every write from any other address. Reproduced on 127.0.0.2: GET 200, POST 403, and 200 for both after the fix |
| Health polling cost before it was quietened | 150 kB of text log in one day, all of it `GET /api/state 200`, with the media token written out verbatim |

## Constraints that are not negotiable

- **90 seconds** is the WhatsApp Status video ceiling, per the owner. The media size
  limit is **10 MiB**, measured on 2026-08-20 rather than taken from the documented
  16 MB, which the composer does not honour. Oversize media is refused silently, so
  the tool stays inside sizes that are measured to work rather than trusting the
  documented
  limit. Enforced before download and by the encoder.
- **The owner's WhatsApp account** is the asset the product depends on. Nothing
  ships that risks it without an explicit decision.
- **Two machines.** Linux and macOS, switched between frequently. Nothing may
  depend on system fonts, GNU specific flags, or a particular ffmpeg build.
- **This machine is often off.** Any always on component has to live elsewhere,
  which is why phase 2 is a server rather than a daemon here.
- **Datacenter IPs are blocked much harder than residential ones.** Any cloud
  deployment needs proxy egress. The `WASTATUS_PROXY` and cookie hooks exist for
  this and are already wired.

## Assumptions about usage

- One clip at a time, a handful per day. No concurrency, no queue, no rate limits.
- Clips are 10 to 20 seconds. The 15 second default reflects that.
- Titles arrive in Tamil script, mixed, or Latin. All three paths are exercised.
- The owner is not looking for archival quality. WhatsApp re-encodes on upload.

## Things already tried that did not work

Recorded so they are not retried. Detail in
[docs/extraction.md](docs/extraction.md).

- `bestaudio` with the default client: 403 on the media URL
- DASH audio only with `--download-sections`: 403, ffmpeg exits 8
- `web`, `web_safari`, `ios`, `tv` clients without the provider: no formats listed
- PO token provider without the JS solver: formats resolve, still 403
- `indic-transliteration` for Tamil: wrong phonetics, `jhinna` for `sinna`
- `aksharamukha` unshimmed on Python 3.14: `ImportError` on `ast.Str`
- `subprocess.run` for clipboard helpers: `xclip` stays resident holding the
  inherited pipe, so the tool appears to hang after it has finished
- A fixed 2800 kbit/s encoder ceiling: fine at 15 seconds, about 21 MB at 60, which
  WhatsApp refuses without a word. The bitrate now comes from the duration
- Attaching a file while a composer was still open from an earlier run: the
  composer holds several files and Send posts all of them, so two Statuses went out
  a second apart. `load_video` now backs out of an open composer first
- Detecting padding bars by averaging along each row: evenly spaced texture
  averages to a constant, so a striped picture read as flat and lost 144 rows.
  Sampling points along the row instead asks the actual question
- Detecting padding bars on a downscaled copy: quantised the bar edge to 20 pixels,
  which either left a strip of bar or ate a strip of picture
- `DOM.setFileInputFiles` with a **relative** path: Chrome takes the command,
  reports no error, and attaches nothing. The failure surfaces a minute later as a
  composer that never opens, which reads like a slow browser rather than a bad
  argument. `post.load_video` resolves the path and checks it exists first
- Gating transliteration on `ord(ch) > 0x24F`: accented Latin such as `Café` slipped
  through untransliterated and broke the ASCII invariant. The gate is now
  `not text.isascii()`
