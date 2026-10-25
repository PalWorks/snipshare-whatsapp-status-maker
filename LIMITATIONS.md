# Limitations

Known gaps, debt and edge cases. Read before reporting a bug, and before
"fixing" something that is a deliberate trade off.

## By design, not bugs

- **Posting needs a desktop Chrome.** `--post` drives a logged in WhatsApp Web
  tab over the debug port. Without one the tool stops at producing files, which is
  still the default. See [DECISIONS.md](DECISIONS.md) D-012.
- **One post per song.** The caption link is tappable, so the text only second
  Status is opt in behind `--follow-up`. See D-013, and D-003 for what changed.
- **The bottom 15 percent of the frame is empty.** WhatsApp draws its caption
  there. See D-014.
- **No URL in the frame, no title in the caption.** Each appears once, in the one
  place it belongs. A clip that is downloaded and forwarded therefore arrives with
  no link at all, which is a case the tool does not design for. See D-015.
- **No Tamil script on the card.** Product decision. Everything is romanised, and
  the pipeline holds itself to ASCII throughout.
- **Card mode fetches no video frames.** Use `--video` when the frames matter.
- **Emoji in a placed line are pictures from the sticker library.** Without
  `scripts/setup_stickers.sh` there are no pictures, so an emoji is left out of the
  line rather than drawn as an empty rectangle, and a line that is only an emoji is
  refused with that instruction. An emoji newer than the installed OpenMoji release
  is left out the same way. See D-065.
- **Only an emoji is drawn as a picture.** A star, a quaver, `(c)`, `(R)` and a
  trademark sign are set in the font, because DejaVu has all five and OpenMoji also
  ships a drawing of a hyphen. Type one of those five wearing an emoji selector and
  it becomes a picture, which is what a phone keyboard sends.
- **Fetching the words waits on yt-dlp.** A pasted playlist is refused, but only
  after yt-dlp has enumerated it, which takes as long as it takes: about half a
  minute for nineteen tracks, capped at 45 seconds. The same wait has always applied
  to Make the clip.
- **Make the clip is grey when the clip on screen is what the form asks for.** The
  safe area guides are not counted as a change, because they move the preview and
  never the pixels. See D-066.
- **The frame shrinks on a short screen.** From 901px wide the preview column is
  stuck to the top of the screen, so the card has to fit in what is left below the
  top bar. The frame takes that height, up to a ceiling of 360px on a page at its
  full width and 300px on a narrower laptop, so a tall window gets the whole frame
  and a short one gets a smaller one rather than a player it cannot reach. It stops
  shrinking at 168px wide, below which the card scrolls with the page like any
  other. See D-067.
- **The preview's header can tuck under the top bar at the very bottom of the page.**
  A sticky item can only travel as far as its own grid area, and below that area sits
  the page's bottom padding. Over that last stretch of scroll the card rides up:
  measured at 32 pixels on a 773 pixel tall window and none at all on a 1033 pixel
  one, where it stays pinned throughout. The frame and the player never go under the
  bar, and the header comes back the moment you scroll up. See D-067.
- **Output is not archival quality.** crf 23 with a bitrate cap, because WhatsApp
  re-encodes anyway.
- **No instructional text on the card.** Footer and eyebrow are off by default. See
  [DECISIONS.md](DECISIONS.md) D-010.
- **The output folder deletes old clips.** Newest 20 kept. Move anything you want
  to keep, or raise `--keep-last`. See D-009.
- **The page loads the composer, it does not send.** Sending is a second press, by
  hand, in WhatsApp. `--post` and **Send it for me** still do it in one go. See
  D-020.
- **The posting browser is its own Chrome profile.** Not the one you browse in, and
  not reachable unless it was started with the debug switch. See D-022.
- **Editing the title means rendering again.** Those words are pixels. The caption
  is text and edits instantly. See D-021.
- **Stickers are pixels too.** Moving one means rendering again. An animated one is
  a second mechanism, a looping input in the filter graph rather than a paste, and
  it arrives by pasting a picture at the page. See D-024 and D-036.
- **An animated sticker's phase is not promised.** Where it sits, how big it is and
  which way it is turned are exact between the preview and the clip. Which frame of
  the loop you catch is not: the browser and the encoder run their own clocks. See
  D-036.
- **A source squarer than 5:3 is made smaller in `--video` mode.** The frames are
  kept out of the title, so a 4:3, square or portrait source is fitted to the band
  above it and shows blurred fill down its sides rather than filling the width. A
  crop would fill it, and would take the top off somebody's head. See D-049.
- **A browser that was already running gets no session label.** The label tab is put
  on the command line of a browser this tool starts, so adopting one that was
  already there produces no label. It does still get the page as a new tab, asked
  for over the debug protocol. See D-050 and D-051.
- **A clip made before 2026-08-25 previews its top text at the old position.** The
  clip's sidecar records where its frames landed, and one written before that has no
  answer, so the preview falls back to the fixed placement, which is where that
  clip's own text actually is. Making it again records it. See D-054.
- **A square or portrait source gives the top text nothing to hang from.** It begins
  at the ceiling, so the block falls back to the top of the band rather than sitting
  against the picture. There is no room between them to sit in.
- ~~**Top text may not fit in card mode with a squarish artwork.**~~ **Fixed
  2026-08-31, D-075.** It was true, and worse than it reads: the line was not drawn
  *and nothing said so*, so the page then reported the clip up to date with words it
  had never drawn. The label no longer shares that band, having moved to the title
  where its name always said it was, and a fitted card shrinks by the nineteen
  pixels one line needs. A card **placed** by hand is still never moved, and that
  case is now measured and said out loud rather than dropped. See D-053 for the
  original reasoning and D-075 for what replaced it.
- **The second line and the footer get at most two lines each, and what is left.**
  They take the room the title has not already spent, so a three line title leaves
  them one line apiece and anything longer is ellipsised. The title is never
  shortened to make room for them. See D-052.
- **Typing a label after a clip exists makes the preview disagree for a moment.**
  A label moves the frames up, and the live word preview draws over the still the
  clip was rendered with, so the label sits on the picture until the clip is made
  again. Same staleness the band above the preview already names. See D-052.
- **A sticker may be placed where WhatsApp will cover it.** The page outlines it in
  amber and the log says so, and then places it exactly there. The frame is yours.
- **Dragging the artwork panel up squeezes the top text out.** In card mode the
  label is anchored to the panel and the top text takes what is left above it, so a
  panel placed high can leave it no room at all. That is Option A, chosen
  deliberately on 2026-08-27 over words that stay put: see D-062. The preview is the
  real layout, so it happens in front of you while you drag.
- **A placed panel keeps the crop it had.** `card_height` centre crops an unusually
  square thumbnail into a 620 pixel panel, D-016, and resizing scales that panel
  rather than un-cropping the artwork. A picture that changed shape under the hand
  moving it would not be the thing that was picked up. See D-062.
- **Placing anything needs a clip of that kind on screen.** The box's shape is the
  picture's own shape, and nothing else on the page knows it. A clip made before its
  rectangle was recorded says so and offers to be made again. See D-061 and D-062.
- **Both posting routes are always on the page.** Which one is the big button comes
  from the address the page was opened on, not from the device. See D-026.
- **Deleting a clip takes two presses, not a dialog.** It disarms itself after four
  seconds. See [TASKS.md](TASKS.md) T-016.

## Real limitations

## Table LI-1: Known limitations

| Limitation | Impact | Workaround |
|---|---|---|
| The download path breaks on YouTube's schedule | the tool stops working with no code change | extend the ladder, see [PLAYBOOK.md](PLAYBOOK.md) |
| Tests cover the offline logic only | the download path and the rendered pixels have no automated coverage | the manual set in [TESTING.md](TESTING.md) |
| aksharamukha needs an `ast.Str` shim | one Python release could break Tamil titles | falls back to Unidecode, `--title` overrides |
| The provider install is about 209 MB | disk cost on both machines | none, it is `node_modules` |
| First run fetches the JS solver from GitHub | a cold run can take minutes | one time, cached afterwards |
| Video mode is 720p only when YouTube offers it | the HLS renditions can be section downloaded and are 1280x720, measured 2026-08-20, but whether they exist is a property of the video: a popular music video offered them on three consecutive asks and one of the owner's own uploads offered none. DASH still answers ffmpeg with 403, so format 18 at 360p is the floor | nothing to do: the ladder tries HD first and falls through in about 2 seconds. Prefer card mode, whose pixels are our own 1080p card. See D-023 |
| ~~Two identical renders started in the same second can collide~~ **fixed 2026-08-20** | `naming.reserve_stem` claims the name with `O_EXCL` instead of checking for it, so two renders of the same song and window cannot agree on one. Eight simultaneous asks get eight names | done, T-017. A claim left behind by a killed render blocks that one name and says so in the log |
| A loaded composer stays loaded | if you load a clip and walk away, WhatsApp holds the file until you send or cancel. The next load cancels it first | cancel it in WhatsApp, or just load the next one |
| Editing stickers on a clip that already has some shows both | the video below still has the baked ones while the editor draws the new ones over the top. Only happens on a second pass; the hint says the clip is behind | make the clip again, which is what the hint asks for |
| The sticker library is 45 MB and not in the repository | a fresh machine needs `scripts/setup_stickers.sh` before the picker works | the page says so where the picker is |
| An animated sticker costs encode time | measured on a 4 second card clip: one adds about 1 second and 56 kB, three add about 3.4 seconds and 61 kB. The clip was never still, so the size cost is small | use fewer, or accept it |
| Animated stickers are stored as GIF whatever they arrived as | this ffmpeg cannot read an animated WebP at all, so Pillow converts. GIF has one bit of transparency, so a soft edge in the source becomes a hard one | none today. If ffmpeg ever grows animated WebP support, the conversion can go |
| Nothing prunes your own stickers | `out/` is pruned to the newest 20 clips, `mine/` grows forever. Every paste keeps a copy: a still one is capped at 2 MB in, an animated one at 8 MB in and 720 pixels an edge out | delete them from the picker, or clear `mine/` by hand |
| The file picker offers still images only | deliberate, the owner did not want to curate animated files by hand. It is a suggestion rather than a guard: a GIF chosen anyway is stored and animated correctly. Pasting is the route that is meant | none needed |
| A sticker shelf still costs 191 kB | scaled copies halve it, they do not remove it. Flat artwork already compresses well, so the measured saving is 52 percent and not the order of magnitude expected | it is cached after the first paint. `loading="lazy"` keeps it to what is on screen |
| A post cannot be stopped once it starts | Stop is refused with a 409 during an upload, because a killed driver leaves WhatsApp in a state the tool cannot describe | wait for it, or cancel in WhatsApp itself. See D-025 |
| Reaching the page from another device hands out the token | whoever opens it can post to your Status | `--also-on` is off by default and takes a tailnet address, not the whole local network. See D-027 |
| `--also-on tailscale` needs Tailscale installed | it fails with a clear message rather than binding something unexpected | install Tailscale, or pass the address itself |
| **The live word preview needs a clip to draw on** | it redraws the picture of a clip that already exists. Before one exists there is nothing underneath: card mode would need the artwork downloaded and video mode the video itself | make the clip once, then edit the words and watch |
| **A clip made before 2026-08-22 has no preview** | the picture the words are drawn over is kept at render time, and older clips never had one kept | the page says so and says to make it again. Nothing else about them changes |
| **The preview shows the words, not the finished frame** | a card clip's waveform is drawn by ffmpeg from the audio, and a still cannot have one, so that band is empty in the preview | none. Press **Make the clip** to see the real thing |
| **Chrome refuses remote debugging on your everyday profile, permanently** | Chrome 136 and later print `DevTools remote debugging requires a non-default data directory` and open no port. Measured 2026-08-22. There is no flag that gets round it, and no way to add the switch to a Chrome that is already running | none, and none possible. It is why the tool keeps its own profile, and why the QR code is scanned once |
| **A debug port that is already taken fails in a way that looks like success** | Chrome logs `bind() failed: Address already in use (98)`, carries on, binds IPv6 only, and prints `DevTools listening on ws://[::1]:N`. Everything here asks `127.0.0.1`, which is the other browser | the tool now says `port N is only half open` and names the browser that took it, D-045. `WASTATUS_CDP_PORTS` moves the search off ports something else owns |
| **A second launch on a profile that is already open exposes nothing** | Chrome hands the launch to the running instance and exits, ignoring the new `--remote-debugging-port` entirely, so a window appears and no port opens | the page finds the running browser and adopts its port instead, `post.running_profile_port`. From the command line, reuse that port or close the window |
| Picking a GIF from the phone keyboard needs **Firefox**, not Chrome | Chrome on Android refuses keyboard image insertion outright, with a toast saying "Can't enter this content here". Measured on two phones and two keyboards: a Galaxy M30 with Samsung Keypad and a OnePlus 11 with Gboard, Chrome 151 against Firefox 150. The keyboard makes no difference, the browser makes all of it | use Firefox on the phone, or copy the picture from somewhere and paste it, which works in both. In Firefox it must be the sticker card's picture box that is tapped, since an ordinary text field greys the keyboard's GIF button out. See [DECISIONS.md](DECISIONS.md) D-036 and [TASKS.md](TASKS.md) T-024 |
| The page is not a secure context away from loopback | `navigator.clipboard` is absent on the phone, in both directions, because the address is plain http. Copying the caption falls back to `execCommand`, and any "paste from clipboard" **button** is impossible there. The paste **event** is unaffected | none needed for copying. See [DECISIONS.md](DECISIONS.md) D-037 before using any browser capability marked `[SecureContext]` |
| OpenMoji is CC BY-SA 4.0 | attribution is owed if this is ever published, and share-alike applies to derivatives of the artwork | the README credits it. The assets are downloaded, not committed |
| `--video` and card mode share nothing but the audio | changing layout means checking both | procedure in [PLAYBOOK.md](PLAYBOOK.md) |
| Titles longer than three lines are ellipsised | very long compound titles lose their tail | `--title` |
| Segment dedupe uses a 0.8 similarity threshold | two genuinely different segments that read alike could be collapsed | `--title` |
| No progress output during the encode | a 15 second wait with no feedback | none, it is 15 seconds |
| Clipboard copy is best effort | silently does nothing if no helper is installed | the text is written to `.caption.txt` |
| Posting needs a logged in WhatsApp Web tab in a debug browser | fails with a clear message, the clip is still produced | the page's **start it** chip, or post by hand, or retry with `scripts/wa_post.py` |
| The composer is matched by CSS selectors and visible labels | a WhatsApp Web redesign breaks `--post` with no notice | the selectors are all in `wastatus/post.py`, and `scripts/wa_post.py shot` shows the live page |
| Artwork comes from `i.ytimg.com` at fixed sizes | a video with no `maxresdefault` falls back to `hqdefault`, which is 480x360 and visibly soft on the card | a warning is logged; use `--video`, or accept it |
| Padding bars are only found when they are flat | a bar carrying a watermark or a gradient is not a flat line, so it survives | `--video`, or accept it. The detector errs towards leaving artwork alone |
| A source video whose bars change mid clip keeps them | the crop is the most conservative of three sampled frames | none, and it is the right trade: the alternative crops real picture |
| `wa_post.py delete-all` cannot be undone | a Status removed is gone, viewers and all | the `--yes` flag exists so it cannot happen by accident |
| A long clip is encoded at a low bitrate | a 90 second clip gets about 716 kbit/s, which is soft on a large screen | it is forced by WhatsApp's size refusal, and WhatsApp re-encodes anyway |
| ~~The exact size ceiling is unmapped~~ **mapped 2026-08-20** | the line is 10 MiB: 10,452,278 bytes accepted, 10,519,352 refused, 33 kB either side of it. The budget moved from 9.5 MB to 10 MB, which is a 5 percent bitrate gain on a 90 second clip | done, T-014. A clip that still lands over the line is now called out on screen rather than refused in silence |
| Long camel case words are flattened | `SoundCloud` becomes `Soundcloud`, because that rule exists to fix academic romanisation like `viRalmAranaindhu` | `--title` |
| Accented Latin is flattened | `Café` becomes `Cafe`, because the pipeline holds itself to ASCII | `--title` |

## Table LI-13: Left after the audit before publication, 2026-10-25

Written **2026-10-25T15:11:42+05:30**. Everything else the audit found is fixed
(D-100); these are the deliberate exceptions.

| Limitation | Why | What would change it |
|---|---|---|
| The hosted image's base, `python:3.13-slim-trixie`, is a tag, not a digest | a digest gives a repeatable build and loses the security updates a rebuild picks up; one maintainer rebuilds rarely | pin by digest and refresh it on a schedule, once there is a schedule |
| Most requirements are minimums (`>=`), not locked | the local tool has to keep up with yt-dlp, which YouTube changes on its own timetable; only the token plugin, whose server half is installed separately, is pinned exactly | a lock file for the hosted image alone |
| A YouTube tab that has been hidden for a long time, reused for a capture, can be slowed by Chrome | Chrome throttles timers in long-hidden tabs; bringing the tab forward would take the person's focus | drive the read from the worker's messages rather than the page's timers |
| The search box says "Search KLIPY and GIPHY" when both are on | KLIPY asks for "Search KLIPY"; whether the longer wording is acceptable is unconfirmed | switch to "Search KLIPY" if KLIPY objects |
| A GET or HEAD carrying a body is refused (D-100); unconfirmed that the tunnel never adds `Transfer-Encoding` to a plain GET | cloudflared's behaviour was not observed through the tunnel before the deploy | one `curl -v` of a page through the tunnel after the next deploy |
| How often YouTube places fragments away from their own times (`timestampOffset`) is unknown; such a capture is now refused before upload | the renderer cuts by the bytes' own times, so it would have refused later anyway | upload the offset with the file, if it is ever seen |
| The commercial licence has no published price list | terms are agreed case by case (COMMERCIAL-LICENSE.md) | a standard licence once there is demand |
| Outside contributions need a licence grant as well as a sign-off | the dual licence depends on it (CONTRIBUTING.md) | none; it is the price of offering a commercial licence |

## Table LI-12: SnipShare, 2026-10-25

| Limitation | Why | What would change it |
|---|---|---|
| Making a clip needs Google Chrome on a computer | the extension is what reads the video, and Chrome on a phone has no extensions | none planned; the page says so wherever it matters |
| The extension is loaded unpacked, with Developer mode on | the Chrome Web Store's policy does not allow downloading streaming media | none; Chrome reminds people now and then that a developer extension is on |
| The video shows in a tab for about a second when it is not already open | a tab that has never been in front is not given its media by Chrome (Phase 0) | none needed; the tab is muted and closes itself |
| Protected (DRM) video cannot be clipped, and the extension does not yet say so before trying | encrypted media cannot be read; the check that would name it is deferred (Table HP-1) | build the check once there are a few people |
| One render at a time on the server | four cores, shared | more workers, or a second host |
| A capture is not resumed if Chrome stops the extension's worker mid way | the page's flow keeps nothing across a worker restart, unlike the popup's. Since D-100 no single request can outlast Chrome's 30 seconds, so a slow line no longer causes one | the page offers to try again, which costs a capture |
| Signed-out viewers get YouTube's ads, which the capture waits for | ads are YouTube's, and the capture never skips them | none, by design |

## Table LI-11: The browser extension and the hosted renderer, 2026-10-24

| Limitation | Why | What would change it |
|---|---|---|
| Loaded unpacked, not from the Chrome Web Store | the store's policy forbids enabling downloads of streaming media | nothing in our hands; a private enterprise policy install is the other route |
| Chrome only, desktop only | the capture hooks Chrome's Media Source Extensions in the page; phones run no extensions | Firefox would need its own manifest and testing; the hooks are standard MSE |
| No stickers, GIFs, placed text, placed picture or label in the extension | its first version does the common case; the local page keeps the rest | the job body and the popup would grow; the engine already takes them |
| Live streams refused | a live MediaSource has no fixed timeline to cut | not planned |
| YouTube Music (`music.youtube.com`) not supported by the extension | not tested, and the spike's one attempt timed out | a test on that page, then its match pattern in the manifest |
| A YouTube tab open before the extension was installed or updated must be reloaded once | content scripts start when a page loads | none; the popup says so |
| If YouTube moves MediaSource into a worker, the capture stops working | the page world hooks cannot see a worker | follow the hooks into the worker, D-083; the popup says so plainly if it happens |
| Ads stitched into the content stream were never seen, so are untested | every ad seen in testing played in a MediaSource of its own | the recorder notes player time against media time, which would show it |
| The token lives in `chrome.storage.local` | an extension has nowhere safer | revoke it from the renderer if a profile is lost |
| One clip at a time per person, and a queue of eight across everybody | one render worker on three cores | `WASTATUS_HOSTED_WORKERS` and cores |
| A 90 second video clip takes about three minutes on the production host | the engine's own render at 1080x1920 on Ampere cores is two of them | more cores, or a cheaper blur |

## Table LI-2: Found by posting real statuses, 2026-08-18

| Finding | Consequence | Status |
|---|---|---|
| WhatsApp overlays the caption across the bottom band of the frame | the link pill at y 1640 collided with it and both became unreadable | fixed, the bottom 15 percent is reserved, D-014 |
| The caption URL is a real link, on the web client and on a phone | the pill was redundant; the two post flow was unnecessary | fixed, D-013 |
| Status upload takes 11s for 4.1 MB, about 40s for 9.3 MB | the driver has to wait for WhatsApp to accept it | handled in `post.confirm_sent` |
| WhatsApp can refuse a Status and leave it looking posted | it stays in the tray on the web client with no views and never reaches the phone. Seen 2026-08-31 at 19:21 on a re-post of a clip that had gone out an hour earlier | `post.confirm_sent` reads the `ack` WhatsApp keeps against the message and reports a refusal as a failure, D-071 |
| Top text needs the artwork's top edge at row 344 or lower | one line costs 84 rows under WhatsApp's header. A full height card's top lands on 325 | a **fitted** card shrinks to make room, D-075. A **placed** one is never moved: the page says the line does not fit and to move the artwork down |
| A placed picture can reach the row the label is drawn on | the label hangs off the title, and a placement can be anywhere. The bottom shade is at alpha 1 of 200 there | the shade starts above the label when a picture reaches it, D-075. A fitted picture stops above it and is unchanged |
| The preview still can never show stickers, the waveform or a mode change | the page draws stickers itself so drawing them twice would double them, ffmpeg draws the waveform and it moves | the pane names them rather than going quiet, D-077 |
| Deleting a Status writes a row that reads like one | a protocol message under the same key prefix, subtype `sender_revoke`, `ack 0`. It is the newest row in the range until the next real post | skipped by type and by `protocolMessageKey` in `post._LATEST_STATUS`, D-071 |
| The web client's `ack` is the only client side word on whether a Status went out | -1 refused, 0 unanswered, 1+ accepted. No reason is recorded for a refusal | read from `model-storage` → `message`, keys prefixed `true_status@broadcast_` |
| Chrome's debug endpoint stops responding while the upload runs | a timeout mid upload is normal, not a failure | handled by `post.Page.js_soft` |
| A source with digital silence cannot be loudness normalised | `loudnorm` measures -inf on it and hands the encoder NaN, which ffmpeg reports as an aac error naming neither the filter nor the cause | the render is run again without that one filter, and the run log says so. Every other failure is raised on the first attempt, `render._run_with_audio` |
| Chrome throttles a background tab enough to time out the composer wait | `--post` failed once, then worked on retry with no code change | handled by `Page.bringToFront` |

The bottom 15 percent of the frame is a zone WhatsApp owns.
`tests/test_safe_zone.py` fails if anything is drawn into it.

## Table LI-3: Found by using the page, 2026-08-19

| Finding | Consequence | Status |
|---|---|---|
| The seek slider did nothing | media was served whole, with no `Accept-Ranges` and no 206, so the browser had no way to ask for a later part of the file | fixed, `serve._send_media`, pinned by `tests/test_serve.py` |
| `web_safari` returns storyboards and no media | every video-mode run wasted one failed yt-dlp invocation and logged a warning that read like a problem | fixed by reordering the ladder, D-023 |
| `yt-dlp` had no timeout | a wedged download would hang the task forever, with the page politely polling a job that was never going to end | fixed, `fetch.RUN_TIMEOUT` and `--socket-timeout` |
| The token was written to the log | media carries it in the query string, and every one of those requests was logged verbatim | fixed, redacted in `Handler.log_message` |
| Health polling wrote 150 kB of log in a day | the useful lines were buried under `GET /api/state 200` | fixed, successful polls are not logged |
| Rebuilding the Recent strip re-downloaded every thumbnail | media is `no-store`, and the strip was rebuilt every 15 seconds | fixed, the strip is only rebuilt when its contents change |

## Table LI-4: Found while building the sticker layer, 2026-08-19

| Finding | Consequence | Status |
|---|---|---|
| Every write from a page opened on any address but `127.0.0.1` was refused | `Origin` was compared against a constant, and Chrome sends it on every same-origin POST. The page would load and read, and nothing could be made or posted. It blocks reaching the page from a phone | fixed, and reproduced on `127.0.0.2` before and after |
| Repainting the sticker layer during a drag killed the drag | the element holding the pointer capture was replaced mid gesture, so the sticker never moved | fixed: the layer is rebuilt only when the set changes, and one element is touched while dragging |
| The preview drew a shadow under each sticker that the renderer does not paste | the frame promised something the clip would not deliver | fixed, the shadow is gone |

## Table LI-5: Found while making it a daily driver, 2026-08-19

| Finding | Consequence | Status |
|---|---|---|
| ffmpeg wrote its output straight into the output folder | so a clip still being encoded was listed by the page as a real one: playable, postable, and now deletable mid-write. A render that failed left the truncated file there for good. Present since the first version; found while building Stop | fixed, the encode happens in the work directory and the clip arrives in one atomic rename. Verified live: the folder stays empty for the whole 50 second render |
| An empty Recent strip never repainted | the rebuild sentinel was `""`, which is also the signature of an empty clip list, so the strip skipped its own rebuild. It cost the "Nothing yet" line on a first run, and left a deleted clip on show | fixed, the sentinel is `null`. Found by deleting a clip in the real page |
| The T-020 estimate was an order of magnitude out | a shelf was assumed to cost about a megabyte. Measured, it is 402 kB, and 191 kB scaled | measured and recorded rather than repeated |

## Table LI-6: Found on the phone, 2026-08-19

| Finding | Consequence | Status |
|---|---|---|
| **A clip sometimes downloads to the phone at about 700 bytes a second, and sometimes in a second flat** | 410 kB of an 8.15 MB clip after ten minutes on one attempt; the same kind of clip complete in 1 to 2 seconds on others, with Tailscale on both times. Both reported by the owner. The phone route works, unpredictably | **parked by the owner 2026-08-19, cause not established.** Not the server: the same file leaves this machine at about 900 MB/s. Not a weak radio either, now that the fast runs are known: a weak radio is steady. The favourite is a transfer stuck on the DERP relay in Bengaluru while the direct path is still coming up. See [TASKS.md](TASKS.md) T-021 |
| **`hidden` does nothing on an SVG element** | `hidden` is defined on `HTMLElement`, not on `SVGElement`, so `svg.hidden = true` set a JavaScript property no stylesheet could see. Both icon pairs on the page are SVG: the player showed a play triangle while playing, and the theme button kept one icon in all three states | fixed, `hide`/`unhide` set and remove the attribute. Reported by the owner, who saw the player on his phone; the theme button had the same defect and the check that built it had read the label rather than the icon |
| The left column overflowed under the right one on a laptop | the Recent strip scrolls sideways, and its min-content width pushed its column wider than the space the grid gave it. Only visible at desktop width, and only after the columns were restructured | fixed, `minmax(0, 1fr)` on the column and `min-width: 0` on the cards. Found by measuring the boxes over CDP, not by looking at the screenshot, where it read as a shadow |
| Start and End took a numeric keypad on Android | the keypad has no colon, so `0:20` could not be typed on the phone at all | fixed, both are `inputmode="text"` |
| Three health pills filled the top of a phone screen | the first third of the page was three things that are only interesting when one is wrong | fixed, one chip that opens a panel, D-029 |
| The caption's label was three lines from the caption | the owner asked "what is the actual caption here?" while looking at the page | fixed, the caption has its own labelled box and the frame shows a read only echo, D-030 |
| The form forgot everything but the length and the look on reload | a phone reloads the tab when you switch to WhatsApp and back, so a pasted link was retyped | fixed, the whole form is remembered |
| Safe areas were off until asked for | a sticker placed under WhatsApp's own caption is invisible, and nothing said so | fixed, on by default, and hidden while the frame is empty |

## Table LI-10: Getting a GIF in, 2026-08-21

| What | Where it stands |
|---|---|
| **The Upload dialog used to hide every `.gif`.** `accept` listed png, webp and jpeg only, a list that predates animated stickers, T-019. The server took a GIF happily when one reached it, and the page never filtered by type, so the only barrier was the file dialog | **fixed 2026-08-21.** `image/gif` is in the list, and a test now reads that list out of `index.html` and proves every type in it can actually be stored |
| **Chrome's "Copy image" flattens a GIF to a still PNG.** Not this tool's doing and not fixable here | copy or save the **file** instead, or use Upload. Named in [LOCAL_SETUP.md](LOCAL_SETUP.md) so it is not discovered the hard way |
| **GIF search reaches a third party, and it is off by default because of that.** With it on, what you type goes to GIPHY or KLIPY | built 2026-08-21, T-029 and D-043. Nothing else leaves: no clip, no caption, no address. Emptying `WASTATUS_GIF_PROVIDER` removes the feature entirely |
| **A GIPHY beta key allows 100 calls an hour.** Thirty results cost one call, and each thumbnail is fetched once per run | named in the error rather than hidden. KLIPY has no published cap that has been hit here |
| **Only the last search is pickable.** Two searches later, a result from the first answers `no longer on offer` | deliberate: the server resolves a pick against what it actually handed out, so nothing the browser names is ever fetched. The cost is that a stale page has to search again |
| **Neither provider's library was judged for Tamil devotional or film material.** Both were exercised on English search terms only | the seam takes one word in `.env` to switch, so the comparison is the owner's to make on real searches |

## Table LI-9: Found in groundwork, 2026-08-21

| What | Where it stands |
|---|---|
| **A playlist link used to be accepted and produce a caption with a dead link in it.** `probe` returned the playlist's id as the video id, so `watch_url` became `https://youtu.be/PL...`, which resolves to nothing | **fixed the same day**, T-027. It is refused at `probe` now, naming what was pasted and what to paste instead. Left here because the shape of the bug is worth remembering: the tool was not wrong about anything it could see, it was confidently wrong about what it had |
| **Spotify audio cannot be fetched at all.** yt-dlp refuses on sight, `[DRM] The requested site is known to use DRM protection` | not a defect and not fixable here. A pasted Spotify link shows that error, unprettified. The owner closed T-028 on 2026-08-21 as not worth the work: he does not use Spotify enough. Route C there is the twenty minute version if that changes |
| **Matching a song by title is not reliable for this library.** Searching YouTube for `Project Samskriti Veyuru Tholipangan` returns the wrong track first, **one second from the right duration** | measured 2026-08-21. It is the reason T-028 route B is off the table: Tamil devotional and film music has the same composition recorded by different artists at similar lengths |

## Table LI-8: Found while posting, 2026-08-20 evening

| What | Where it stands |
|---|---|
| **WhatsApp Web can rename a control at any time.** It did on 2026-08-20: `Photo and video` became `Photos & videos` and both Status choices moved behind an **Add Status** button | matching is on words now, so this particular rename would not have broken anything, and since 2026-08-21 a check runs once per server run when a clip becomes postable and reports it on the health row, T-026. **It is still detection, not immunity**: a control that moves while the server is up is found at the next start, and one that moves in a way no wording covers is still found by a failed post |
| **The list of spellings is a guess about words WhatsApp has not used yet.** `PHOTO_ITEM` holds five, one of which is real and four of which are guesses | harmless, and one line to extend. Named here so nobody mistakes the list for something WhatsApp has agreed to |
| **A tab open across a server restart holds a dead token**, because the token is minted per process and stored nowhere | working as intended, D-027's neighbour. The page now says "this page is older than the server. Reload it" rather than `bad or missing token`, which read as a fault in the tool |

## Table LI-7: Found after a reboot, 2026-08-20

| Finding | Consequence | Status |
|---|---|---|
| **The phone route has to be re-armed at every start, and the walkthrough did not say so** | `--also-on tailscale` lives for the length of the process. A reboot, or any Ctrl-C, returns the tool to loopback alone. **Start the page** in [LOCAL_SETUP.md](LOCAL_SETUP.md) gave the plain command, and the flag sat eighty lines below in a reference table, so following the instructions literally after a reboot produced a laptop only page and no message explaining it | **document fixed 2026-08-20; closed properly 2026-08-22.** The walkthrough carries both commands and names the `Also on` line as the thing to check, and [RUNBOOK.md](RUNBOOK.md) carries the symptom. Then `WASTATUS_ALSO_ON` made the standing answer a machine's own, D-044, which reverses the rejection D-027 recorded on 2026-08-20. Empty is still the default, so this is opt in and not drift |
| Nothing on the page says it is loopback only | the phone gets a refused connection, which names no cause. The laptop's page looks perfectly healthy, because it is | **open, and cheap to close.** The state already carries `also_on`, and the health panel already names the host. See [TASKS.md](TASKS.md) T-025 |

## Edge cases not handled

- **Live streams and premieres.** Untested. Duration and section behaviour are
  both likely wrong.
- **Age restricted or region blocked videos.** Will fail at the ladder with no
  useful message. Cookies may help, with the account risk that implies.
- **Playlists.** `--no-playlist` is always passed, so a playlist URL resolves to
  its first video rather than erroring.
- **Videos shorter than the requested window.** Caught for the end timestamp
  against the reported duration, but a video reporting no duration skips that
  check.
- **Non Tamil non Latin scripts.** Devanagari, Telugu and others fall through to
  Unidecode, which is character mapping rather than phonetic. Output will be
  readable but not how a speaker would spell it.
- **Titles that are entirely emoji or punctuation.** After noise stripping the
  title can end up empty, and the card will render a blank line.

## Debt worth paying

Ranked by what would hurt most if left.

1. **No coverage of the rendered pixels.** Every visual regression is caught by a
   human opening a PNG. A perceptual hash comparison against a checked in
   reference frame would catch layout breakage, at the cost of a fixture that
   needs updating whenever the design changes on purpose.
2. **The `_dedupe_segments` similarity threshold is a magic 0.8.** It works on the
   titles tested. It has no test proving where it breaks.
3. **A frame dump flag.** `--frame` writing a still next to the mp4 would remove
   the manual ffprobe step from every visual change. Tracked as
   [TASKS.md](TASKS.md) T-007.
4. **Log growth is bounded but unattended.** Rotation caps the text log at 8 MB
   across four files, and `runs.jsonl` grows without limit. It is a few hundred
   bytes per run, so this is years away from mattering, but it is unbounded.
