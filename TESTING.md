# Testing

## Current state, stated plainly

**1593 offline tests pass and 7 are skipped, and 156 Node tests pass**, counted
2026-10-31 after commit d917694 (account section and capture fix), recorded 2026-10-31T11:35:09+05:30 (earlier, 1569 and 152 at
2026-10-31T09:55:06+05:30 on the Scheduled Statuses build, after the fixes from its independent review; the 1509 offline
tests counted 2026-10-25T22:43:40+05:30, after the second security pass (D-101), whose tests are
`TestTheSecondSecurityPass` and `TestARequestIsReadOneWay` in `tests/test_portal.py`).
They cover timestamp parsing, transliteration, output naming, retention, logging,
frame offsets, the local page, the posting driver, and since 2026-10-24 the hosted
renderer, the capture cut and the browser extension's parser, which runs in Node
from inside pytest.

**They do not cover the download path or the pixels.** Those still need the manual
procedure below. Do not read a green test run as a claim that a visual or
extraction change works.

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest                                       # offline, about three minutes
WASTATUS_E2E=1 .venv/bin/python -m pytest tests/test_smoke.py -v  # real run, about a minute
```

## Before changing encoder settings

`tests/test_bitrate.py` proves the arithmetic, not the platform. It holds the two
numbers that matter against each other: `PLATFORM_MAX_BYTES`, the 10 MiB the composer
was measured to refuse above on 2026-08-20, and `SIZE_BUDGET_BYTES`, which must stay
below it by more than the encoder's measured 2 percent overshoot.

WhatsApp refuses oversize media by never opening its editor, with no message, so any
change to `SIZE_BUDGET_BYTES`, the maxrate ceiling, or `MAX_DURATION` needs one real
attach test at the longest allowed duration:

```bash
./wastatus.sh "URL" 0 -d 90
.venv/bin/python scripts/wa_post.py video out/<clip>.mp4 --caption-file out/<clip>.caption.txt
.venv/bin/python scripts/wa_post.py cancel
```

If the composer opens, the size is acceptable. If it times out, it is not.

## Table TE-1: What the suite covers

| File | Covers |
|---|---|
| `tests/test_timecode.py` | every documented timestamp form, junk rejection, `?t=` parsing, round tripping through the yt-dlp format |
| `tests/test_translit.py` | the Tamil baselines from [DECISIONS.md](DECISIONS.md) D-006, the ASCII invariant, noise stripping, segment dedupe, and a guard that aksharamukha actually imported |
| `tests/test_naming.py` | slug rules and cap, date led stems, video mode separation, collision suffixes |
| `tests/test_retention.py` | oldest first pruning, sidecars pruned with their clip, reported counts, `keep=0` disabling |
| `tests/test_frame_offset.py` | `--frame` midpoint and explicit offsets, clamping past the end, junk rejection |
| `tests/test_artwork.py` | padding bar detection: black, white and near black bars, pillarbox, the measured 2.35:1 letterbox case, and everything that must be left alone, including a gradient, a flat image, regular texture and a bar bigger than the cap |
| `tests/test_wrap.py` | title wrapping at the real width with the real font: hyphens as break opportunities, no character gained or lost, ellipsis on overflow, and every line fitting the card |
| `tests/test_serve.py` | that the preview anchors the top text where the clip put it, reading back the position from the sidecar, and falls back cleanly for a clip made before that was recorded. Plus that **every word on the frame reaches the job and the preview**, title, second line, footer, label and top text alike, because a field the page sends and the server drops is invisible in exactly the way the label was for a day; and that a sidecar written before the top line existed still reads without putting the previous clip's words on it. Plus where the page opens: on the command line of a browser started here, over the debug protocol into one that was already running, and in the default browser when neither happened or when the tab is refused, with `--no-open` reaching none of them. Plus the live word preview: a card clip and a video clip each answering with a JPEG at the preview width, different words giving a different picture, the answer small enough to send to a phone, never cached, a clip with no preview base saying what to do about it, a name that is not a clip name refused, the token required, and 50,000 characters of title cut rather than refused. Plus choosing a GIF provider over `/api/gif/provider`: that it switches and the state agrees, that a provider with no key is refused, that junk and an empty name are refused, that it needs the token, and that the previous search's results are forgotten so a stale id cannot be picked. Plus starting up from `.env`, `WASTATUS_ALSO_ON` and `WASTATUS_START_BROWSER`: which words mean yes, that a typo means no rather than yes, that a flag beats the file and `--also-on ""` returns one run to loopback, that a browser already open on the posting profile is adopted instead of duplicated, and that a browser which cannot be started is reported and never stops the page coming up. Plus the local page's server against a real socket: the token, the origin check, preflights, the media query token, filename traversal, window validation, a failing render becoming a failed task, posting through a fake poster, byte ranges and a 416, caption editing and its ceiling, a stop time instead of a length, the job sidecar read back, that nothing is sent unless asked, that two posting requests collide with a 409, and that the token never reaches the log. Plus stopping a render and being refused a stopped post, deleting a clip with its whole group and being refused during a post, the download disposition and that it does not cost the seek slider its ranges, whether a request is local, and what `--also-on` accepts |
| `tests/test_proc.py` | stopping a child for real, not through a mock: a normal run coming back like `subprocess.run`, a timeout still raising what `fetch` catches, a cancel killing the child and raising on its own thread, the kill reaching a **grandchild** because yt-dlp runs its own ffmpeg, a cancelled thread refusing to start the next stage, and the flag not surviving into the next piece of work on a reused thread |
| `tests/test_stickers.py` | the sticker library and the placement contract: ids that could address a file, clamped and refused numbers, prefix search, skin tone variants left out, uploads re-encoded through Pillow, and the coordinate claim itself, that the same fractions land in the same place on the 1080 overlay and the 1620 card. Plus thumbnails: the width asked for, a cached copy reused, a replaced upload not served from a stale one, only the allowed widths made, and the cache living beside the library rather than in it |
| `tests/test_fetch.py` | the download ladders' order, and why: both lead with the only format a section can be cut from, no entry asks for a merge, and the dead `web_safari` entry stays last |
| `tests/test_pipeline.py` | that the sidecar beside a clip holds **every** word that was drawn on it, since a word it forgets is a word that vanishes when you re-open the clip to correct it, and that it records where the frames landed, which the preview cannot measure for itself; and that a card clip records no such position, because it has no frames. Plus the window validation both front ends share: every timestamp form, the platform ceiling, an end before a start, the stage names a progress bar divides by, and that a title fed back from the job sidecar transliterates to itself, so re-making a clip cannot quietly rename the song. Plus that a stopped or failed render leaves no truncated mp4 in the output folder, and a successful one keeps its clip |
| `tests/test_bitrate.py` | that every allowed clip length lands inside a size WhatsApp is measured to accept, that short clips keep the quality ceiling, and that the duration cap matches the platform |
| `tests/test_crop.py` | the textless background still the live word preview draws over: that its filter graph still matches the clip's, crop, blur sigma and brightness alike, minus the overlay, so the two cannot drift; and that a still which fails to write never takes the clip with it. Plus choosing a crop for a letterboxed source: consistent bars cropped, a dark frame making it more conservative rather than less, even offsets and dimensions, and rounding inwards |
| `tests/test_post.py` | finding a browser and starting one, plus the posting driver against a fake page: the clip path reaching Chrome is absolute, a missing file fails before the page is touched, the file dialog interception is always restored, a caption is typed only when there is one, a composer left open is backed out of first, and deleting stops when the tray is empty or the limit is reached. Plus what became of a Status: WhatsApp's `ack` accepted, refused and unanswered each read correctly, a row an earlier post left behind is not mistaken for this one, a row older than the Send is not either, a delete's `sender_revoke` tombstone is skipped, a store that cannot be read falls back instead of failing, and the composer selector leaves the chat's message box alone. Plus trying again: a refusal is retried with a doubling wait, no answer is **never** retried, and giving up says how many times it tried. Plus which ports to look on: a range and a list expanded, every malformed value falling back whole rather than partly, and the first free one chosen. Plus naming the browser that holds a port, against a real process with a real `/proc` entry, in **both** command line shapes, because Chrome flattens its own argv and a NUL-only reader finds nothing |
| `tests/test_safe_zone.py` | measures the lowest pixel the text layer paints, in both modes, with and without a footer, and fails if anything reaches the band WhatsApp reserves for its caption. Plus the frames in `--video` mode: five source shapes from 2.35:1 to portrait are rendered through the **real filter graph** and the picture they paint is measured, because until D-054 the clamp that keeps them off the title lived in an ffmpeg expression, and an expression can only be rendered and measured, never read. Skipped where there is no ffmpeg. Plus the label in video mode: that it paints anything at all above the title, which it silently did not until 2026-08-25; that the picture's floor rises for it and **only** when there is one; and that the frames measured off a real render clear it. Plus the wrapping that followed the same day: that the 91 character sentence which was drawn 1989 pixels wide in a 1080 pixel frame comes back as more than one line with **every line inside the margins, letterspacing counted**; that a sentence loses the tracking a two word label keeps; that a long label on a card stays out of WhatsApp's header and, since D-075 moved it to the title, never reaches the card now above it either, at every artwork shape; and that a wrapped label over a three line title with a footer still clears both bands. Plus the two fields below the title, which were the same bug: that the second line and the footer paint **inside the margins** in both modes, for text that used to run off by 170 pixels a side; that the unwrapped versions really did not fit, which is what made it a bug rather than a preference; and that a long second line never pushes the footer past the caption band. Plus the top text: that it is drawn under WhatsApp's header and wrapped, that the frames give up room at the top **and only when asked**, that a square source measured through the real graph stops below it, and that in card mode it clears both WhatsApp's header and the card below it at every artwork shape, which a fitted card shrinks to guarantee, D-075. **Every card-mode measurement here goes through `compose.card_words`, the same function `build_card` lays the words out with**: this file used to work the arithmetic out a second time, and when D-075 changed the drawing it kept passing against the layout that had just been replaced, D-078. Plus the seam D-054 creates, which is the load bearing test in this file now that Python decides where the frames land: **the rectangle Python computes is the one ffmpeg paints**, rendered and measured at five aspect ratios, and even on every side because yuv420p's chroma plane cannot represent an odd row. Plus the anchoring itself: that the block hangs a gap above the picture rather than under the header, that a shorter line sits **further** from the header rather than nearer, that a picture starting at the ceiling cannot drag it off the frame, and that a clip with no recorded picture position still draws its top text where that clip has it |
| `tests/test_fetching_the_words.py` | that asking the video what it is called is the **same question** the two empty boxes have always asked. Fetch fills them, so the next render takes the override path rather than the read-it-from-the-video one, and those are different code: `to_latin` over an override, `clean_title` over a fetch. Five real title shapes, a noisy upload, a romanised Tamil one, a `- Topic` artist upload, a title that romanises to nothing and a volume series, each fetched and then fed back, are asserted to land where an empty pair of boxes would have. Plus that a probe asked for by hand gives up in 45 seconds rather than the render's five minutes, and that a render still gets the long one |
| `tests/test_freetext_emoji.py` | emoji in a placed line, drawn from the sticker library because the line is set in a bundled font that has none. Two things are pinned. **A line with no emoji must not change at all**, since every placed line ever made is one, so five such lines are asserted to contain no colour and `★ ♪ © ® ™` are asserted to stay letters. And **only an emoji becomes a picture**: OpenMoji ships a drawing of a hyphen, and a line whose punctuation turned into pictures of punctuation would be a worse tool. Plus the splitting itself over nine lines, a skin tone belonging to its hand and a family staying one picture; the `FE0F` lookup ladder, which OpenMoji leaves out of nearly every name and keeps in the keycaps; that the box the page draws matches the picture, at every width, including the sizes where a square hung off a baseline lands at -1; that the drawing carries the same shadow the letters do, measured as area with the shadow turned off; and that without the library the line loses the emoji rather than drawing an empty box, while a line that is only an emoji says which script to run |
| `tests/test_page_wiring.py` | where the panels live and the wiring a move can quietly cut, after D-057 put Stickers in the form's column and Make the clip in Post it: that the make button, now outside the form, still names the form it submits, since without `form=` it renders identically, takes the press and does nothing; that the form it names exists; that the keyboard shortcut goes through `requestSubmit()` on the form rather than clicking the button, which the move would also have broken; that Stickers is beside the form and not in it, because Enter in a lone text input inside a form submits it and would start a render; and that the phone keeps its own running order, both wrappers dissolving to `display: contents` so `order` can reach each panel, every panel holding a distinct place, the shelf between the frame and the making of it, and the columns coming back at 901px where the row coupling would otherwise return. Plus D-056's warning: that it sits in the Post panel before the buttons it is about, that all three acting buttons are guarded, that Download is handed the event because an anchor is followed unless it is cancelled, and that the link and the window are **not** counted as drift, since a warning that fires while setting up the next clip is one that will not be read on the day it matters. Plus what was added on 2026-08-27: the fetch icon in the Words header, that it is in the summary rather than the body and hugs the value, that the working state survives a page which refuses animation, and that it does **not** share a class with the top bar's buttons, which it did until that class quietly stripped the border off the theme button; the grey Make button, that the question it asks is not the stale notice's; and the desktop's two columns, that Post it moved into the scrolling one above Recent, that the stuck one holds the frame and nothing else since anything else is height, that it is stuck under the top bar by a **measured** offset rather than a typed one and that every read of that measurement carries a fallback, that the frame shrinks to what is left of the screen, that its ceiling is raised only once the page is at its full width, and that the fold control is a chevron in a target big enough to aim at. Plus D-069's tidy of the footer: that where the clips are is inside the Recent card and **no longer** in the footer as well, which is the failure mode of a move like that; that the script's lookup still finds it, since it changed tag as well as parent; that the address a phone is given carries the port, without which it is not something anybody can type in; and that the footer is folded away only where the health chip is always on screen, which a phone is not. Plus D-070's spacing: that the page grid and the card stack carry the **same** gap at every width, asserted as equal to each other rather than to any particular number, because each rule was right for its own container and the fault existed only as the two of them down one column |
| `tests/test_recent_strip.py` | the delete cross on a Recent tile, and the three traps it steps around, none of which announce themselves: that the tile is not a `<button>` inside a `<button>`, which is invalid and which the parser silently unnests into siblings, laying the cross out beside the tile rather than on it; that an armed fill using `--danger` takes its ink from `--danger-bg` rather than a fixed white, since `--danger` is a dark red in one palette and a pale pink in the other; and that the touch target reaches 44 pixels through the grown `::before` while the visible disc stays small enough not to become the thumbnail. Plus that the route the page posts to is a route the server actually has, checked against `serve.py` rather than asserted on its own, since renaming it breaks nothing that compiles; that the cross and the "saved" tick are pinned to opposite corners; that only one tile can be asking at a time and the question expires; that it survives a repaint, which the fifteen second poll causes; and that a refused delete has somewhere to be seen. The delete itself is tested in `test_serve.py`, and nothing here repeats it |
| `tests/test_label.py` | the session label: that its title carries the port, because the window title is the whole point; that it names both ports and the output folder; that a second address appears only when there is one; that a path is escaped rather than pasted into the page; that it is written per port so a restart overwrites instead of accumulating; that it is Chrome's **first** URL, that the page rides between it and WhatsApp Web so one window holds the whole session, and that WhatsApp Web is still opened last; that no label leaves the command line as it always was; and that a page port which is not known yet, or a cache that cannot be written, produces no label and no failure |
| `tests/conftest.py` | one autouse guard for the whole suite: every test's logging goes to its own temporary directory. Until 2026-08-22 running the tests appended thirteen fake run records to the project's real `logs/runs.jsonl`, the file you read to answer which extraction strategy has been working, seeded with runs against `https://youtu.be/abc` that failed with `ZeroDivisionError`. Found by copying the file, running the suite and diffing |
| `tests/test_card_placement.py` (D-075 block) | the label sits above the title in **both** modes and both pictures give way for it; a fitted card shrinks so the top text has room and never drops a line, at every aspect; a placed card too high says so instead; video mode never reaches that case; **a clip with neither field set is the pixel-identical card it always was**; and the shade is raised only where a picture actually reaches the label |
| `tests/test_sheet.py` | the sheet row, without a sheet: not configured is silence, a refused credential names the service account address to share with, a network failure and a missing `google-auth` both cost a row and never a Status, the row is the sheet's four columns, Source comes from the clip's sidecar so the page and the CLI write the same form of the link, and **nothing here can write a row that is not `Published`** |
| `tests/test_runlog.py` | run records written, stage timings captured including on exception, winning strategy recoverable, appending rather than overwriting. Plus the startup stamp: it names the versions that are otherwise unrecoverable afterwards, and it names `.env` settings **without ever quoting one**, which is the invariant that would be a leak |
| `tests/test_capture.py` | the hosted path's cut, against streams ffmpeg makes in `conftest.captured_media`: a VP9 video and an Opus audio stream on clocks that start at 20 and 18 seconds, each with a mark on every whole second. **Both marks land on the whole seconds after the cut**, the flash to a frame and the beep to 8 ms, which is the sync measurement D-080 rests on. Plus refusing a file holding both kinds, the wrong kind, and junk; a window the upload does not hold, before ffmpeg runs; a hole inside the window, and not one outside it. Plus that a captured card **never reaches `fetch`**, with every fetch entry point made to raise |
| `tests/test_hosted.py` | the hosted renderer over real HTTP. Tokens: only the hash stored, the file private, a revoked token refused without a restart, a broken file refusing everybody. The door: health without a token, everything else with one, **no CORS header on any answer**, and a body refused unread ending its connection, which the suite found. Uploads on a bad connection: a chunk sent twice written once, a chunk past what arrived answered with where to resume, an overlap keeping only the new tail, a chunk that lies about its range, oversize chunks and uploads, somebody else's upload not existing, and a part upload surviving a restart. Jobs: a card from uploads coming back as a clip in byte ranges, the uploads spent by the job, **asking again after a lost answer naming the job already made**, the list holding only the caller's jobs, every window and mode the engine would refuse refused here, artwork that is not an image, one clip at a time per person, a rendering job stopped within seconds and leaving nothing, a restart reporting the job it interrupted, and a folder with no record cleared. The janitor: abandoned uploads and old clips removed, recent ones kept |
| `tests/test_portal.py` | SnipShare over real HTTP, Google replaced by a stub. Accounts: the admin list the only authority, a second request notifying nobody, suspension ending sessions, only hashes stored, a grant doing one thing, the upload allowance unraceable, a GIF key never stored as itself, deletion leaving only anonymous reports. Pages: every public page with a policy and no placeholder, the Chrome requirement on each, `/app` and `/admin` behind a session. Access: the owner told once, another site unable to send the form, where a person stands at sign-in, the cookie's flags. The page API: the session value required as well as the cookie, another origin refused, state per person, what the server cannot do answering 404, the words cleaned by the card's rules, **the owner's GIF key never serving anybody else**. Grants: the window resolved as the render will, a bad one refused before anything is read, an upload grant unable to make a popup job, uploads counted against the day. Rendering: a clip made from uploaded media that **only its maker can see or fetch**, the capture having to be of the linked video, the day's and the hour's limits. And everything the audit found, and since D-100 `TestWhatAStrangerCannotMakeItDo`: a large body from nobody refused unread, a GET carrying a body answered once and closed, an admin's files kept through a refused delete, the last sign-out ending the extension's grants, eight simultaneous sign-ups for one address making one request, a name like `{{HEAD}}` staying a name, every public page linking to its source, a typed address never told how it stands, daily counts past a year forgotten, and the container's memory read from its cgroup |
| `tests/test_publishable.py` | every tracked file free of real email addresses, public IPv4 addresses, home directories and the owner's private deny list (`.publish-deny`, git-ignored); the hosted image's `deploy/requirements.txt` a subset of `requirements.txt`, without yt-dlp, the token plugin or the websocket client |
| `tests/test_hardening.py` | the local engine's share of the audit before publication, D-100: a link cannot pass options to yt-dlp and needs `http(s)`, the proxy password masked in the log, a rebinding `Host` refused the token, a `Content-Length` that is not digits refused unread, `send` defaulting to no in all three signatures, an unreadable WhatsApp store unconfirmed rather than sent, a clip being posted never pruned, a prune or the clip list surviving a clip vanishing, the sheet never failing a post, a 20,000 character line ellipsised in well under two seconds, render words held to a caption's length, one local render at a time, and errors shown without a server path |
| `tests/test_extension.py` | runs the Node suite in `src/test` (the fragment parser against fragmented MP4 and WebM fed in uneven appends, through an abort mid fragment, a lost place, a second encoding mid stream, duplicates, `remove()`, `timestampOffset`, a WebM run cut mid cluster, and junk, every result read back by ffmpeg with no complaint) and `node --check` on every script. Plus the manifest: every file it names exists, the parser loads before the recorder in the page world, it asks for nothing it does not use. Plus the facts written down twice: the 90 second limit, **WhatsApp's labels and selectors equal to `post.py`'s**, the default renderer reachable, no chunk larger than the renderer takes, a request giving up before Cloudflare does, and the size warning equal to `render.PLATFORM_MAX_BYTES` |
| `src/test/queue.test.js`, and the three below (all run by `tests/test_extension.py`) | the queue's pure rules with an explicit clock: order and spacing, the 2 minute and 30 day bounds, quiet hours as a warning, limits, catch up, resume's three choices, the next wake, Undo snapshots, the plain words per state, `shift` and `spread` |
| `src/test/custody.test.js` | the clip kept in 2 MiB parts and hashed once, carried on after a stop, a line that drops mid part, a server that ignores Range, a wrong size refused with nothing kept, a damaged clip failing its hash, a full disk, no byte written without room for twice the clip, a clip the server no longer has, and the sweep deleting only unnamed scheduled parts |
| `src/test/place.test.js` | the ladder with fake tabs and windows: quietest first with no record, then the order learned from `placeStats`, a rung skipped for a week after three failures, a load that moved focus counting against its rung, S3 and S5 only when allowed, the focus guard (our own focus change put back, the person's own left alone), the bridge's acknowledgement of every slice, one load at a time, and the person using WhatsApp holding a run back |
| `src/test/schedule.test.js` | the stored queue against a fake clock, store, alarms and notifications: a schedule keeping its clip and arming the alarms, a bad time or a limit refused with a code, prewarm then a quiet run then prepared, a damaged clip never reaching WhatsApp, waiting a minute at a time then asking, catch up and missed, a worker stopped at each stage and the next one carrying on, Undo inside ten seconds, stale revisions refused, pause and resume's choices, lost alarms rebuilt on every wake, and a schedule alarm never driving the clip job |
| `tests/test_extension.py` (additions) | the worker loads `queue.js`, `custody.js`, `place.js`, `schedule.js` in that order before its own code, every script passes `node --check`, and the manifest asks for exactly the permissions in SECURITY.md Table SE-4 and no `background` |
| `src/test/capture.test.js` | the capture's tab choice with fake tabs, added 2026-10-31T11:35:09+05:30: a tab showing the video that does not answer is never chosen and so never brought forward, a tab whose player is not ready is not chosen, a ready tab is chosen with what it said even past a silent one for the same video, and tabs of other videos and discarded tabs are not asked at all |
| `tests/test_extension.py`, `tests/test_page_wiring.py`, `tests/test_portal.py` (additions, 2026-10-31T11:35:09+05:30) | the manifest exposes only the four queue files, to the local addresses in the repository copy and to the site alone in a build; the framed queue tells its height to the site's origin only and takes messages only from the site's own parent; Up next's Scheduled goes to the account's section; the account page's policy frames the extension and nothing else, an id not of Chrome's shape adds nothing, and `/api/account` carries the pilot switch |
| `tests/test_scheduling_limits.py` | the server's per person limits: defaults for a person and for an admin, an older database gaining the columns, each figure set and put back, an admin switched off, the daily clip and upload limits following the person, nonsense refused with nothing changed, deleting a person taking their figures, a person told their own, only an admin changing anyone's, the refusal coming before the body is read, a failure report with the source `schedule` |
| `tests/test_page_wiring.py` (additions) | the Schedule controls start hidden and only the hosted script shows them, **Load into WhatsApp** stays the primary, the save button is inside the picker's form, the picker says what it does, and the phone line is the planned one |
| `tests/test_smoke.py` | one real run: exit code, the output files and the absence of the opt in one, filename shape, 1080x1920 h264 and aac, duration, ASCII caption, the run record, and no leftover work directory |

The aksharamukha import guard in `test_translit.py` is deliberate. That dependency
sits behind a compatibility shim, and a silent fallback to Unidecode would degrade
every Tamil title without failing anything.

## SnipShare, end to end

```bash
scripts/site_check.py            # the real server and extension, a throwaway Chrome
scripts/site_check.py --load     # and Load into WhatsApp, to "not signed in"
```

It starts a server of its own on a spare port, signs a test person in as a Google
sign-in would end, loads a copy of the extension built for that port, and drives the
page: the words fetched through the extension, a card clip and a video clip made
from a real YouTube video (through whatever ads a signed-out browser gets), the
quota after, and the failure reports. Measured 2026-10-25: 18 to 35 seconds a clip,
up to a minute with an ad. Against production the same was run with the built
extension and a session minted on the server, then removed.

The public pages are checked by eye at 360 and 1280 pixels, light and dark; Google's
button and Turnstile need the real site, because both are tied to its hostname.

## The extension, end to end

`pytest` covers the parser, the renderer and the cut. What it cannot cover is
YouTube's page, Chrome's extension machinery and WhatsApp Web. Those are covered by
driving the real extension:

```bash
# a throwaway Chrome for Testing, the extension loaded, a real YouTube video
scripts/extension_check.py --renderer "$WASTATUS_DEPLOY_SITE" \
    --token-file ~/.secrets/<token file> --video kJQP7kiw5Fk --start 120 --end 140

--mode video --quality hd1080     # the frames, at 1080p
--throttle 800                    # an 800 kbit/s line, both ways
--restart-at uploading            # Chrome stopping the worker mid upload
--stop-at rendering               # press Stop, and check nothing is left running
--save                            # press Save the video, and check the file
--keep-clip out.mp4 --popup p.png # keep what came back, and screenshot the popup
```

A local renderer works the same way: `wastatus hosted --data /tmp/h token add me`,
`wastatus hosted --data /tmp/h serve`, then `--renderer http://127.0.0.1:8790`. The
script loads a copy of the extension whose manifest already permits that address.

**Loading WhatsApp's composer needs a signed in WhatsApp Web**, so it is checked in
the owner's own Chrome rather than a throwaway one; it was on 2026-10-24, through
the extension's own `loadIntoWhatsApp`, and the composer was closed without sending.

**Sync** is checked with the beep and flash video `M3aLeoGOiFU`: keep the clip, and
measure the red frames against the 1 kHz onsets on the clip's own timestamps. The
flash has to land on the whole second and the beep within a few milliseconds.

## Scheduled Statuses, end to end

Written **2026-10-31T01:52:38+05:30**. A headless Chromium with the real unpacked extension and a local
hosted server (a throwaway data folder, a scratch browser profile, a test person) was
driven in outline like this:

1. Start a local hosted server with a throwaway data folder and sign a test person in,
   with scheduling switched on for them.
2. Load the unpacked extension built for that server's address into a scratch profile.
3. Make a real clip on the page, then **Schedule** it and **Add to queue**, and open
   the queue page.
4. Retime a row, edit a caption, cancel a row and Undo it, Pause and Resume, with two
   queue pages open to watch the other follow.
5. Let a schedule fall due with WhatsApp blocked, and check that it fails cleanly to
   "signed out", notifies, and moves no focus.

Verified this way on 2026-10-31. **Not verified:** anything in a real WhatsApp Web,
resume's three choices end to end, the alarm rebuild on every wake end to end. A real
WhatsApp Web needs the owner's own signed in Chrome and is Phase 0 of the plan, which
has not been run; **Try quiet mode now (nothing is sent)** on the queue page is the
owner's test. Never run any of this against the owner's real WhatsApp or profile.

## Philosophy

Three things can break, and they need different treatment:

1. **Pure logic** (`timecode`, `translit`, `naming`, `retention`, `runlog`).
   Deterministic, offline, cheap to test. This is where the automated suite lives
   and where it pays for itself.
2. **The download path** (`fetch`, `potoken`). Depends on a third party actively
   trying to break it. Cannot be unit tested meaningfully; a test that mocks
   YouTube would only assert that the mock matches yesterday's YouTube. Verified
   by running it, and by the measurement table in
   [docs/extraction.md](docs/extraction.md).
3. **Pixels** (`compose`, `render`). No assertion substitutes for looking. Frame
   dumps, by eye.

## Manual verification set

`pytest` first, then these six. Together they exercise both render modes, both
title paths, the phone route, and the parts no assertion can cover.

### 1. Card mode, Tamil script title

```bash
./wastatus.sh "https://youtu.be/A6DfGQsdz1Y" 1:10 1:25
```

Expect: about 25 seconds, an mp4 of 5 to 6 MB, a romanised Latin title on the
card, and a clean exit with the shell prompt returning.

### 2. Card mode, Latin title

```bash
./wastatus.sh "https://youtu.be/dQw4w9WgXcQ" 0:43 0:58
```

Expect: the title passes through with its original casing, not title cased.

### 3. Video mode

```bash
./wastatus.sh "https://youtu.be/A6DfGQsdz1Y" 1:10 1:25 --video
```

Expect: a separate `_video.mp4`, real frames with a blurred fill, and text sitting
below the video and not colliding with it. Add `--eyebrow "a label"` and
`--top-line "a line"` and expect both to be drawn, wrapped, and the frames to have
moved up and down to make room: since 2026-08-25 video mode draws everything card
mode draws.

### 4. Look at the frames

```bash
./wastatus.sh "<URL>" 1:10 1:25 --frame 0:02 -o /tmp/f1
./wastatus.sh "<URL>" 1:10 1:25 --frame 0:12 -o /tmp/f2
```

Open both `.png` files. Two frames apart in time confirms the zoom moved and the
waveform is reacting. Check nothing is clipped, overlapping, or off canvas.

### 5. The page from a phone

```bash
./wastatus.sh serve --also-on tailscale
```

Expect two addresses printed, and the tailnet one to open on the phone over
Tailscale. On the phone the result panel leads with **Download**; on the laptop it
leads with **Load into WhatsApp**. Verified on 2026-08-19 down to the state the page
reads: `local: true` on loopback, `local: false` on the tailnet address, same process.

**No test reaches a GIF provider.** `tests/test_gifs.py` feeds recorded payloads
through `_get`, so the suite runs with no key, no network and no rate limit. What it
pins is the switch, that two providers come out as one shape, that only a provider
with a key can be chosen, that choosing one **never writes `.env`**, and that `fetch`
refuses anything that is not `https` and stops at the ceiling whatever a header
claims. To exercise the real thing, put a key in `.env` and drive the page.

**`loading="lazy"` does not fire in headless Chrome 151, and it looks exactly like a
broken route.** On 2026-08-22 every shelf thumbnail reported `naturalWidth` 0 and the
server logged no image request at all, which is the signature of the 403 bug below.
It was not that. Forcing one image to `loading="eager"` made the request and it
loaded. Before investigating a shelf that will not paint in a headless browser, do
that first:

```js
[...document.querySelectorAll(".shelf__item img")]
  .forEach(i => { i.loading = "eager"; const u = i.src; i.src = ""; i.src = u; });
```

**A thumbnail that does not appear is not a provider fault.** Thirty shelf cells
rendered and every image was a 403 on the first pass, because `/api/gif` was not in
the list of routes that take the token as a `t=` query parameter and an `<img>`
cannot send a header. Reading the code did not find it; counting did:

```js
[...document.querySelectorAll("#shelf img")].filter(i => i.naturalWidth > 0).length
```

Anything that draws images from a route should be checked that way rather than by
looking at the page, because a broken `<img>` in a small cell looks like an empty
cell looks like a slow network.

**The page has no test runner, so anything on it is driven rather than asserted.**
The sticker handles were verified by dispatching real input over CDP into a headless
Chrome pointed at a server on a scratch port: `Input.dispatchMouseEvent` for the
mouse half, and `Emulation.setTouchEmulationEnabled` plus
`Input.dispatchTouchEvent` for the touch half, which is the only way to make
`(pointer: coarse)` match and therefore the only way to see what a phone sees. Two
things that cost time and are worth knowing:

- **Headless Chrome reports no pointer at all**, neither fine nor coarse. Any media
  query written as "not a mouse" will match it. Write the positive test.
- **Scroll the frame into view first.** Input events are dispatched at viewport
  coordinates, and at 412 pixels wide the preview sits about 1000 pixels down. Every
  gesture silently did nothing until `scrollIntoView` went in front of it.

**When a post says it cannot find a control, WhatsApp moved it, not you.** Ask the
live page what the controls are called before changing any code:

```bash
.venv/bin/python - <<'PY'
from wastatus import post
with post.Page(9222) as page:
    post.open_status_tab(page)
    post.click_any(page, post.ADD_STATUS)
    print(page.js("""(() => JSON.stringify([...document.querySelectorAll(
        '[role=menuitem]')].map(e => e.getAttribute('aria-label'))))()"""))
PY
```

Whatever it prints goes into `PHOTO_ITEM` or `TEXT_ITEM` at the top of
`wastatus/post.py`. Matching is on words, so a plural or an `&` is already covered;
only a genuinely new word needs adding. `TestLabelsWhatsAppKeepsChanging` pins that,
and `TestTheStatusMenu` pins that the menu is opened by looking rather than by
assuming. Neither of them touches a browser.

**A refused POST must leave the connection usable.** `TestKeepAlive` opens one
connection, sends a POST with a bad token, then a good GET on the same socket, and
fails if the second comes back anything but 200. It failed with a 400 before the fix,
because the unread body was being parsed as the next request line.

**Check the flag took before blaming anything else.** The commonest failure of this
whole section is that the flag was not passed, which after a reboot is the default
rather than an accident. Two checks, both cheap:

```bash
ss -tlnp | grep 8765          # expect two sockets, not one
curl -s -o /dev/null -w "%{http_code}\n" http://100.x.y.z:8765/
```

Two sockets and a `200` mean the server is right and anything still broken is
Tailscale or the phone. **One socket and a `000` is a refused connection**, so the
flag is missing: Ctrl-C and start it again. Re-verified this way on 2026-08-20 after a
reboot, along with `app.js`, `app.css` and a tokenless `/api/state` that still answers
403 over the tailnet.

**Where the file lands is known:** the phone's browser saves it to `~/Download`,
confirmed 2026-08-19.

**Still unverified, and the last gap in the route:** whether WhatsApp's own picker
can see it there. That check is **blocked by [TASKS.md](TASKS.md) T-021**, because no
download has finished yet: 410 kB of 8.15 MB arrived in ten minutes. When one does
finish, post the clip from the WhatsApp app and check the caption **on a second
device**, because your own Status does not linkify on the phone that posted it.

### 6. The page's two postures, without a phone

The layout that a phone gets is reachable from the laptop, which is how it was built
and how it should be re-checked after any change to `wastatus/web/`:

```bash
./wastatus.sh serve --also-on tailscale --no-open
.venv/bin/python scripts/shot.py http://127.0.0.1:8765/ /tmp/here.png --width 412 --height 900 --full --click .tile
.venv/bin/python scripts/shot.py http://100.x.y.z:8765/ /tmp/away.png --width 412 --height 900 --full --click .tile
```

Expect `/tmp/here.png` to lead with **Load into WhatsApp** and `/tmp/away.png` with
**Download**, both at phone width. Opening the tailnet address from the laptop is a
genuine away test: the server decides from the connection, not the user agent.

**Driving touch.** Gestures need `Emulation.setDeviceMetricsOverride` with
`mobile: true`, `Emulation.setTouchEmulationEnabled`, then `Input.dispatchTouchEvent`.
Two things about that harness cost an hour on 2026-08-19 and will cost it again:

- **A touch outside the viewport is dropped.** Scroll the frame into view and read
  the bounding box *after* scrolling, or the gesture silently does nothing and reads
  as a broken feature.
- **`touchEnd` releases every point you leave out of it.** To lift one finger of
  two, send `touchEnd` carrying only the point that left, with stable ids of your
  own. Leaving the remaining finger in the list ends the whole gesture, which looks
  exactly like a re-anchoring bug.
- Pointer moves are delivered on the frame clock, and a background tab throttles it.
  Read the value after the gesture ends, not between two moves.
- **`Page.captureScreenshot` on a backgrounded tab never returns.** It waits for a
  frame the compositor is not producing. Send `Page.bringToFront` first, and give
  the socket a timeout so a stall fails loudly instead of hanging.
- **`captureScreenshot` clips in page coordinates, `getBoundingClientRect` reports
  viewport coordinates.** Add the scroll offset, or the picture is of the topbar.

### Driving the owner's phone directly

The phone can be driven from here, which is how the keyboard question was finally
answered. It needs **USB debugging** on, which is a separate toggle from Developer
options: until it is on, Android exposes no ADB interface at all and `adb devices`
prints an empty list even though `lsusb` shows the phone.

```bash
ADB=~/Android/Sdk/platform-tools/adb
$ADB devices -l                                   # authorise on the phone if asked
$ADB shell am start -a android.intent.action.VIEW -d "http://100.x.y.z:8765/" com.android.chrome
$ADB forward tcp:9444 localabstract:chrome_devtools_remote
curl -s http://127.0.0.1:9444/json/list           # the phone's tabs, drivable over CDP
$ADB exec-out screencap -p > shot.png             # what it looks like
$ADB shell input tap X Y                          # a real tap, which opens the real keyboard
```

Four things worth knowing, each of which cost time on 2026-08-20:

- **Chrome on the phone is drivable over CDP, Firefox is not.** Firefox has to be
  read from screenshots. Since the diagnostic page prints its own log on screen, that
  is enough.
- **Pick a forward port nothing else holds.** 9223 was already taken by another
  browser on this laptop, and the failure looked like a working connection to the
  wrong browser.
- **The screen sleeps in 30 seconds and re-locks.** `adb shell svc power stayon usb`
  keeps it awake while charging; put it back with `svc power stayon false`. A locked
  phone needs its owner: do not touch the PIN screen.
- **`KEYCODE_BACK` navigates the browser**, so use the navigation bar's own hide-keyboard
  key to dismiss the keyboard instead.

**What a phone keyboard actually sends** cannot be answered from this machine, and
was answered by a page built for the purpose, `wastatus/web/paste-test.html`: three
targets, a rich text box, a plain input and a file picker, and a log of every `paste`,
`drop`, `beforeinput` and inserted `<img>` each one received. It was deleted once both
phones had been through it, on 2026-08-20, and it is in this repository's history if
the question reopens. The answer it gave is in [DECISIONS.md](DECISIONS.md) D-036:
**the browser decides, not the keyboard.** Chrome on Android refuses, Firefox accepts,
and that held on a Galaxy M30 with Samsung Keypad and on a OnePlus 11 with Gboard.

**Asking WhatsApp where a limit is.** The composer answers by behaviour, not by
words: an acceptable file opens its editor within a second or two, and an
unacceptable one is taken and nothing happens, so `wa_post.py video` times out. That
difference is a usable instrument. Build probes that differ in **one** property, keep
everything else identical, attach each without `--send`, and `wa_post.py cancel`
between them so nothing is left staged. That is how the 10 MiB size ceiling was
bisected on 2026-08-20, with five 90 second clips re-encoded from one source at
different bitrates. Two rules: run a **control** through it, a file already known to
be accepted, or an environmental failure reads as a refusal; and cancel after every
probe, because the composer holds every file it is given and one Send would post all
of them.

**Driving a paste.** A clipboard cannot be filled from CDP, but the event can be
built: `new ClipboardEvent('paste', {clipboardData: dt})` with a `DataTransfer`
carrying a `File`. That is a faithful test of the page's handler and it is what
proved the GIF path, including with the caption box focused, which is the state a
phone is in when its keyboard is open. Two things to know: a synthetic paste never
inserts text into a field whatever happens, so `defaultPrevented` is not evidence of
anything, and the caption box has had its own paste listener since long before this,
which cancels every paste and inserts the text itself.

**Something that appears and then goes away** cannot be checked by looking once.
Read the painted value at each moment it is supposed to change, waiting past the
timer in between: `getComputedStyle(el).outlineColor` is opaque with a finger down
and `rgba(0, 0, 0, 0)` two seconds after lifting. The attribute alone is not the
check, because the attribute is not what the eye receives.

**Two traps this page has already fallen into.** A screenshot proves layout and
never behaviour, so drive the real page for anything that moves; and reading back
the thing you just set proves nothing, because the property you set may not be the
one the browser uses. `svg.hidden = true` assigns a property that does not exist on
`SVGElement` and no stylesheet can see it, and the check that missed it read the
button's label instead of the icon's computed `display`. Assert on what the viewer
would see: `getComputedStyle(el).display`, a bounding box, the text on screen. `~/Plugins/cdp eval 8790 '<javascript>'` against a page already open in
the debug browser is the cheapest way, and it is what verified the theme button, the
caption echo, the sticker panel and the stage sequence on 2026-08-19.

## Checks worth running

### Output conforms

```bash
ffprobe -v error -show_entries format=duration,size \
  -show_entries stream=codec_name,width,height,bit_rate \
  -of default=nw=1 out/<file>.mp4
```

Expect 1080x1920, h264 and aac, and a duration within about 0.2 seconds of what
was requested.

### Transliteration, without a network round trip

```bash
.venv/bin/python -c "
from wastatus.translit import clean_title
for t in ['சின்ன சின்ன முருகையா | முருகன் பாடல் | SADHASIVAM #murugansongs',
          'Kandha Sashti Kavacham | Murugan | கந்த சஷ்டி கவசம் | Original Full Video',
          'Rick Astley - Never Gonna Give You Up (Official Music Video)']:
    print(repr(clean_title(t)))"
```

Expected output, and the regression baseline:

```
'Sinna Sinna Murugaiyaa | Murugan Paadal'
'Kandha Sashti Kavacham | Murugan'
'Rick Astley - Never Gonna Give You Up'
```

### Timestamp parsing

```bash
.venv/bin/python -c "
from wastatus.timecode import parse_timecode, start_from_url
print([parse_timecode(v) for v in ['93','1:33','01:33','1:02:03','90.5']])
print(start_from_url('https://youtu.be/x?t=1m30s'), start_from_url('https://youtu.be/x?t=90'))"
```

Expect `[93.0, 93.0, 93.0, 3723.0, 90.5]` then `90 90.0`.

The mixed `90` and `90.0` is real: the `1m30s` branch returns an int and the bare
seconds branch returns a float. Harmless downstream, both are consumed as numbers.

### Health check

The one command version, for confirming the environment rather than a change:

```bash
./wastatus.sh "https://youtu.be/A6DfGQsdz1Y" 1:10 1:20 -o /tmp/health
```

## The page's own behaviour, which the suite cannot reach

There is no JavaScript test harness here, and adding one for 800 lines of vanilla
would be more machinery than the thing it tests. So anything interactive is verified
by driving the real page over CDP, and the procedure is in
[PLAYBOOK.md](PLAYBOOK.md). Two bugs were found that way on 2026-08-19 and neither
would have shown in a screenshot: a deleted clip staying in the Recent strip, and the
"Nothing yet" line never appearing on a first run.

Worth re-driving after touching the page:

| Check | What proves it |
|---|---|
| Stop ends a render | the form re-enables, the message says nothing was written, and `pgrep yt_dlp` finds nothing |
| Delete needs two presses | the first says "Really delete?", the second empties the panel **and** the Recent strip |
| The primary button follows the address | open the page at a non-loopback address and Download comes first, with Load still present |
| The shelf asks for thumbnails | every `.shelf__item img` src carries `&w=96`, and `naturalWidth` is 96 |
| A sticker lands where it was dragged | crop the rendered still at the box the fractions predict and look at it |

## What to watch for beyond the obvious

- **Does the process exit?** A resident subprocess holding stdout makes the tool
  look like it hangs long after it has finished. This has happened once, with
  `xclip`. Any new `Popen` call is a suspect.
- **Did the work directory get cleaned?** `ls /tmp/wastatus-*` should be empty
  unless `--keep` was passed.
- **Is the caption pure ASCII?** Non Latin characters leaking into the output text
  means the transliteration path was bypassed.
- **Did the ladder fall through to a late entry?** A working but degraded download
  produces a softer clip. Check with `grep "fell through" logs/wastatus.log`.

## When a test fails

Failures in the download path are usually YouTube, not the code. Retry twice
before debugging, then read `logs/wastatus.log` for the full subprocess output and
follow [RUNBOOK.md](RUNBOOK.md).

A useful first question after any failure:

```bash
tail -1 logs/runs.jsonl | .venv/bin/python -m json.tool
```

That shows which stage was reached, which extraction strategy was in play, and the
error, without reading the text log at all.
