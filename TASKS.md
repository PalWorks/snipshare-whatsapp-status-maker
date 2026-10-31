# Tasks

Work queue. Each task has a goal, constraints and acceptance criteria so it can
be picked up without rereading the conversation that produced it.

**Numbering starts at T-004.** T-001 to T-003 were the first three questions this
project had, all settled and pruned from this file before it took its present shape:
whether a Status caption link is tappable, where a phase 3 recipient list would come
from, and confirming the card design. Older entries in [DECISIONS.md](DECISIONS.md)
and [CHANGELOG.md](CHANGELOG.md) still cite them, and `git show f0aa836:TASKS.md` is
where they last appear in full.

**Priority:** P0 blocks other work, P1 next, P2 when convenient.
**Status:** `open` not started, `parked` decided and deliberately waiting, `done`
finished and verified. A parked task is not a stalled one: it says what was decided
and why it is waiting, so picking it up is implementation rather than another round
of deciding.

## Table TK-1: Everything at a glance

Newest thinking first within each block. The one line each is the whole point: if a
row needs more, the task below has it.

### Open and parked

| Task | Priority | Status | In one line | Waiting on |
|---|---|---|---|---|
| [T-073](#t-073-open-scheduled-statuses-release-1-awaiting-phase-0) Scheduled Statuses, Release 1 | P1 | **built, awaiting Phase 0** | prepare only, from the editor: a queue page, clips held on the computer, a quiet placement ladder, per person limits. Nothing tried in a real WhatsApp Web yet | the owner: Phase 0 on his Chrome (**Try quiet mode now (nothing is sent)**), then a week of use. Release 1 plus the account section are being merged, pushed and deployed on the owner's instruction of 2026-10-31 (updated 2026-10-31T11:35:20+05:30) |
| [T-033](#t-033-open-instagram-as-a-second-source) Instagram as a second source | P2 | open | researched on 2026-08-22 and the ground is not level: your own posts have an official route, other people's have none. yt-dlp is the only mechanism that takes a pasted link, and anonymous extraction is dead today | the owner, on Table T33-2 |
| [T-024](#t-024-p2-a-way-to-reach-a-gif-from-chrome) A way to reach a GIF from Chrome | P2 | **parked** | Chrome on Android refuses keyboard GIFs on any phone, so the GIF step is done in Firefox, which is route A and costs nothing | a phone on the cable, to settle whether route B works. Nothing to decide |
| [T-021](#t-021-p1-find-out-why-a-clip-sometimes-crawls-to-the-phone) Why a clip sometimes crawls to the phone | P1 | **parked** | 1 to 2 seconds on some attempts, 10 to 15 minutes on others, Tailscale on throughout | the owner, when it next bites. The test is now to watch `tailscale status` for `direct` or `relay` |
| [T-012](#t-012-p2-confirm-the-caption-link-outside-the-owners-own-devices) Caption link on other people's clients | P2 | open | proven on two of the owner's devices, unproven on anybody else's | someone who saw a Status |

### Done

| Task | Finished | What it delivered |
|---|---|---|
| [T-072](#t-072-done-keep-the-apps-containers-off-the-hosts-private-network) Keep the app's containers off the host's private network | 2026-10-26 | host firewall rules for the project's subnet alone: no host, private network or metadata service, public internet open; installed by `deploy.sh` as a service (D-102) |
| [T-071](#t-071-done-a-second-security-pass-and-the-first-deploy-from-the-public-repository) A second security pass, and the first deploy from the public repository | 2026-10-25 | static and supply chain audit plus 133 defensive tests; every weakness found fixed and tested (D-101); the repository renamed `snipshare-whatsapp-status-maker`; deployed |
| [T-070](#t-070-done-audit-and-publish-the-repository) Audit and publish the repository | 2026-10-25 | a four-part audit of the whole codebase with every finding fixed and tested (D-100); AGPL-3.0-only with a commercial licence, third-party notices and contribution terms (D-099); the documentation set completed to the agent documentation guide; a fresh single-commit public repository |
| [T-069](#t-069-done-an-account-page-both-gif-keys-and-no-black-first-frame) An account page, both GIF keys, no black first frame | 2026-10-25 | `/account` in two columns with Profile, History, API keys, Feedback, Extension and Privacy and data; GIPHY and KLIPY kept at once and searched either or both; feedback mailed with a reply-to; clips open on their picture rather than black; `extension/` renamed `src/` |
| [T-068](#t-068-done-snipshare-the-full-page-hosted-for-invited-people) SnipShare: the full page, hosted, for invited people | 2026-10-25 | the extension's button opens the site: Google sign-in after the owner approves a request, each person's own clips, stickers and GIF key, the extension reading the video and loading WhatsApp for the page, daily limits, alerts and a digest, a self-contained Compose project behind a Cloudflare Tunnel, and a repository that names no site, host or person. Verified end to end locally and in production |
| [T-067](#t-067-done-a-dash-between-spaces-keeps-its-space) A dash keeps its space | 2026-10-24 | every "Artist - Song" card read "Artist -Song", found on a frame the renderer made. The join drops a space only after a hyphen attached to its word |
| [T-066](#t-066-done-the-browser-extension-and-the-hosted-renderer) The browser extension and the hosted renderer | 2026-10-24 | anybody with a token makes a clip from the YouTube tab they are watching: captured in their own browser, rendered on the hosted renderer, loaded into their WhatsApp composer. Verified end to end in the owner's Chrome, through ads, Premium, in-page navigation, a throttled connection and a stopped worker |
| [T-065](#t-065-done-send-has-no-icon-any-more) Send has no icon any more | 2026-10-24 | WhatsApp dropped the icon the tool used to know a composer had opened, so every load waited for a Send button already on screen. Matched by label now, and an open composer is told from a chat with a typed reply |
| [T-057](#t-057-done-one-rhythm-down-the-column-of-cards) One rhythm down the column | 2026-08-27 | the four cards inside the form sat 12 pixels apart and the four around it 20, on one unbroken run of identical boxes. Two rules, each right for its own container, wrong as a pair. Both take the grid's gap from 600px now |
| [T-056](#t-056-done-the-page-says-each-thing-once) The page says each thing once | 2026-08-27 | three marks on one screenshot of the footer, all the same complaint: text in a place that is not the place it belongs. Where the clips are moved under the clips, the reachable line goes on a laptop and stays on a phone, and the address it gives finally carries the port you have to type |
| [T-055](#t-055-done-the-frame-stays-on-screen-and-the-fold-control-grows) The frame stays on screen | 2026-08-27 | the sticker shelf and the send buttons are halfway down the page, and reaching either one scrolled the frame they are about off the screen. Post it moved into the scrolling column above Recent, the frame's column is stuck under the top bar and sized to the height that is left, and the fold control is a 24px chevron in a 32px target |
| [T-054](#t-054-done-make-the-clip-goes-grey-when-there-is-nothing-to-make) Make the clip goes grey | 2026-08-27 | the button looked the same before and after a render, so the only way to know a clip was finished was to remember pressing it. It greys out once the clip on screen is what the form asks for, and comes back the moment anything that reaches the pixels changes, including the link and the window that the stale notice deliberately ignores |
| [T-053](#t-053-done-emoji-in-a-placed-line) Emoji in a placed line | 2026-08-27 | the free text box took emoji and Pillow drew an empty rectangle for each one, because DejaVu has none. They are drawn from the OpenMoji library the stickers already install, so both platforms draw the same clip. A line with no emoji in it renders byte for byte as it did |
| [T-052](#t-052-done-fetch-the-videos-own-words) Fetch the video's own words | 2026-08-27 | the title and second line were only knowable by making the clip and looking at it. An icon in the Words header asks the video now, fills both boxes with exactly what the card would have drawn, and opens the card so they can be corrected before anything is rendered |
| [T-051](#t-051-done-a-pencil-on-a-line-of-words) A pencil on a line of words | 2026-08-27 | a placed line could be retyped only by finding it in the box below, and nothing on the frame said so. A pencil appears on a line under the mouse and takes the hand to that box, opened, scrolled to, focused and selected. Look was rearranged in the same pass, reported as "too congested" |
| [T-050](#t-050-done-place-the-artwork-panel-too) Place the artwork panel too | 2026-08-27 | D-061 placed the picture in video mode and left card mode's panel laid out for you. It is placed the same way now, with the label and the top text following it, and stopping where following it would put them under WhatsApp's header or across the title. Every fitted card renders byte for byte as it did |
| [T-049](#t-049-done-place-the-picture-yourself) Place the picture yourself | 2026-08-26 | the frames were fitted into the band the words left and that was the only answer. The picture is a placed thing now, with the same centre and width every other placed thing has: dragged, sized by its corner or by the arrow keys, allowed to hang off any edge for a full bleed. Fitted stays the default and renders byte for byte as it did |
| [T-048](#t-048-done-the-keyboard-drives-the-frame) The keyboard drives the frame | 2026-08-26 | placed things could be moved, sized and thrown away by hand and only by hand. Arrows nudge by half a percent of the frame, Shift by two, `+` and `−` size, `[` and `]` turn, Delete removes, Escape puts it down, and ⌘Z brings back the last thing removed however it was removed. Every box is a tab stop, so a hand that never touches the mouse can reach one |
| [T-047](#t-047-done-black-behind-the-frames) Black behind the frames | 2026-08-26 | video mode filled the frame with a blurred copy of itself and there was no other answer. Black is one `pad` in the graph, a choice in Look, and 27 per cent smaller on the clip measured. Previewing it meant rebuilding the frame from the still already kept, which is also the piece a resizable picture will need |
| [T-046](#t-046-done-free-text-you-put-where-you-want-it) Free text you place yourself | 2026-08-26 | three boxes that each put a line where the layout says, and no way to put one anywhere else. A line you write is now a placed thing like a sticker: dragged, resized, turned, as many as you like. Drawn by the server so the box you drag is the pixels that get burned in. The Extras boxes were renamed and re-ordered down the frame in the same pass |
| [T-045](#t-045-done-the-clip-says-when-it-is-older-than-the-form) The clip says when it is stale | 2026-08-25 | a GIF was placed and the clip posted without being made again, so the GIF was not in it. The Post it panel now names what has changed since the clip was made, next to the buttons that would send it. Stickers and Make the clip changed columns in the same pass |
| [T-044](#t-044-done-a-cross-on-the-tile-to-throw-a-variant-away) A cross on the tile | 2026-08-25 | dropping a bad take meant loading it into the player first, three presses away from the strip where takes are actually compared. Each tile carries its own cross now, it asks twice before it acts, and it is reachable by a finger without becoming the picture |
| [T-043](#t-043-done-anchor-the-top-text-to-the-picture) Top text anchored to the picture | 2026-08-25 | it sat 30 pixels under WhatsApp's header with 278 pixels of void beneath it. It hangs off the picture's top edge now, which meant moving the picture's arithmetic out of an ffmpeg expression and into Python |
| [T-042](#t-042-done-text-at-the-top-of-the-frame) Text at the top of the frame | 2026-08-25 | the empty band under WhatsApp's header takes text now, its own field rather than a placement for the label, and the frames give up room at the top the way they already do at the bottom |
| [T-041](#t-041-done-the-label-above-the-card-works-in-video-mode) The label works in video mode | 2026-08-25 | a sentence typed into "Label above the card" was silently dropped in video mode, then drawn 1989 pixels wide in a 1080 pixel frame. It is drawn above the words, wrapped, and the frames give up the room for it only when there is one |
| [T-040](#t-040-done-the-page-opens-where-the-rest-of-the-session-is) The page opens in the session's own browser | 2026-08-25 | the page is Chrome's second URL after the label, so one window holds the label, the tool and WhatsApp. A browser already running is asked over the debug protocol instead |
| [T-039](#t-039-done-the-sticker-panel-second-review) The sticker panel, second review | 2026-08-24 | a way back to the sticker handles after a clip has been made, the GIF service chosen as radios on the end of the row that turned GIFs on rather than as a second row of identical pills, and the provider credit down to a mark on the hint line |
| [T-038](#t-038-done-video-frames-stop-being-written-on-by-the-title) Video frames clear of the words | 2026-08-24 | frames centred no lower than 40 pixels above the title, and fitted to the band above it when they are too tall for it. A 4:3 source used to paint 81 pixels into the title and a square one 216. Wide sources do not move |
| [T-037](#t-037-done-say-which-port-this-session-is-on-where-it-can-be-read) Say which port this session is on | 2026-08-24 | the posting browser's first tab is a label whose title reads `● 8765 · wastatus`, naming the page port, the debug port, the profile and the output folder. A cached file, so it outlives the server |
| [T-036](#t-036-done-the-words-previewed-as-you-type) The words, previewed as you type | 2026-08-22 | the clip's own picture redrawn with whatever is in the boxes, by Pillow, in 0.86s for a card and 0.10s for a video, against 30 to 66 seconds to make the clip again |
| [T-035](#t-035-done-the-words-on-the-card-stop-following-the-last-video) Words stop following the last video | 2026-08-22 | the words carry the video they were derived for, survive a reload, treat two spellings of one link as one song, and are checked again at the press |
| [T-034](#t-034-done-the-desktop-gif-panel-reviewed) The desktop GIF panel reviewed | 2026-08-22 | thumbnails three times the size and sharp rather than upscaled, a GIPHY/KLIPY chooser on wide screens, the phone-only paste box gone from the desktop view, the empty shelf message no longer one word per line, and room between the toggle and the search box |
| [T-032](#t-032-done-one-command-to-get-to-work) One command to get to work | 2026-08-22 | `./wastatus.sh` with no arguments opens the page, and `WASTATUS_ALSO_ON`, `WASTATUS_START_BROWSER` and `WASTATUS_CDP_PORTS` in `.env` answer the three flags that used to be retyped. A browser already open on the posting profile is adopted rather than duplicated |
| [T-031](#t-031-done-name-the-browser-that-is-holding-a-debug-port) Name the browser holding a debug port | 2026-08-22 | the error says whose browser it is, by profile, and calls out the half open IPv6 case that made a taken port look like a working one |
| [T-029](#t-029-done-a-gif-picker-in-the-page) A GIF picker in the page | 2026-08-21 | a **Drawings / GIFs** toggle in the Stickers card, GIPHY and KLIPY behind one seam, everything proxied through the server, picked GIFs kept in a pruned set of twenty, and the whole thing off unless `.env` switches it on |
| [T-030](#t-030-closed-frame-the-video-yourself-instead-of-taking-the-blurred-fill) Frame the video yourself | 2026-08-21 | **closed without building.** The research is the deliverable: the blurred fill already does the job, and 68 per cent of the picture is too much to throw away for it |
| [T-027](#t-027-done-a-youtube-music-link-works-a-playlist-link-lies) A playlist link no longer lies | 2026-08-21 | route A. A playlist is refused at `probe`, naming what was pasted, how many tracks it holds, and what to paste instead. YouTube Music needed no work: it already worked |
| [T-023](#t-023-done-handles-on-the-sticker-itself) Handles on the sticker itself | 2026-08-21 | a delete cross everywhere, a resize grip and a rotate stem where there is a mouse, and a selection that lasts instead of D-034's 1.4 second fade |
| [T-026](#t-026-done-notice-when-whatsapp-renames-a-control-before-a-post-does) Notice a WhatsApp rename before a post does | 2026-08-21 | route B: one probe per server run, asked when a clip first becomes postable, reported on the WhatsApp Web health row with what the menu actually offers |
| [T-025](#t-025-done-let-the-page-say-it-is-loopback-only) Let the page say it is loopback only | 2026-08-20 | a fourth row in the health panel, route A. Green with the address to open on the phone, grey and reading "this laptop only" without the flag. Grey does not turn the chip amber: it is the default, not a fault |
| [T-018](#t-018-done-promote-the-hd-ladder-if-youtube-reopens-it) HD ladder promoted | 2026-08-20 | video mode is 720p when YouTube offers HLS for that video, 360p when it does not. DASH is still 403 |
| [T-014](#t-014-done-narrow-whatsapps-effective-media-size-ceiling) Size ceiling mapped | 2026-08-20 | the line is 10 MiB, bisected against the live composer. Budget 9.5 MB to 10 MB, and a clip that goes over is called out rather than refused in silence |
| [T-017](#t-017-done-queue-a-render-instead-of-racing-for-a-name) The name race | 2026-08-20 | a name is claimed with `O_EXCL`, not checked. Eight simultaneous asks get eight names |
| [T-009](#t-009-done-prove-where-the-segment-dedupe-threshold-breaks) Dedupe threshold pinned | 2026-08-20 | measured: no threshold separates a real duplicate at 0.846 from two real words at 0.900, so 0.85 stays and the tests say why |
| [T-008](#t-008-done-handle-an-empty-title-after-noise-stripping) Empty title after stripping | 2026-08-20 | the raw title stands in, and the channel behind that |
| [T-022](#t-022-p2-make-this-repository-fit-to-be-public) Make this repository fit to be public | 2026-08-20 | the owner's addresses out of the working tree and the history, a LICENSE, the font licence, `.env` support, and MEMORY.md split. Flipping the switch on GitHub is his |
| [T-019](#t-019-done-animated-stickers-and-how-one-arrives) Animated stickers | 2026-08-20 | a pasted GIF loops for the whole clip. It arrives from the phone keyboard's GIF tab, in Firefox |
| [T-020](#t-020-done-serve-sticker-thumbnails-at-thumbnail-size) Sticker thumbnails at thumbnail size | 2026-08-19 | `?w=96`, cached on disk. A shelf of 40 went from 402 kB to 191 kB |
| [T-016](#t-016-done-let-the-page-delete-a-clip) Delete a clip from the page | 2026-08-19 | two presses, disarming after four seconds |
| [T-015](#t-015-done-let-the-page-cancel-a-render) Stop a render | 2026-08-19 | Stop beside Make, killing the process group |
| [T-013](#t-013-done-exercise-the-card-across-the-owners-real-library) Card across the real library | 2026-08-18 | the card design approved against real songs |
| [T-007](#t-007-done-add-a---frame-flag) `--frame` | earlier | pull a still out of a finished clip |
| [T-006](#t-006-done-warn-when-artwork-falls-back-to-a-low-resolution-thumbnail) Low resolution artwork warning | earlier | says so rather than shipping a soft card silently |
| [T-005](#t-005-done-record-which-ladder-entry-succeeded) Record the winning ladder entry | earlier | the run log names the client and format that worked |
| [T-004](#t-004-done-add-a-smoke-test) Smoke test | earlier | regressions caught without a human looking at frames |

Retired numbers: T-001, T-002, T-003, T-010, T-011 were folded into decisions or
overtaken; they are not missing, they are gone.

---

## T-073 (open) Scheduled Statuses, Release 1: awaiting Phase 0

**Built:** 2026-10-31T01:53:14+05:30. Branch `feat/scheduling-r1`, uncommitted when this was written.

**Goal.** A clip made on SnipShare can be scheduled, held on the person's computer, and
put in WhatsApp's composer at its time for the person to send, without taking focus
where Chrome allows. Plan: [docs/scheduling.md](docs/scheduling.md), Section 15 is what
was built; decisions D-104 and D-105.

**Acceptance.**

- [x] From the editor only, prepare only: the extension never presses Send
- [x] Local custody in 2 MiB parts, size checked, SHA-256 kept; no tickets, no pins
- [x] The queue page: in row time and caption edits, Cancel with Undo, Pause and Resume,
  history, budget, quiet test, run log
- [x] The quiet runner, prewarm, fallback, notifications and badge, settings
- [x] Per person server limits and the pilot switch, edited on the admin page
- [x] 152 Node tests and the pytest suite (1569 passed, 7 skipped, 2026-10-31T09:55:06+05:30, after the
  review fixes); a headless Chromium run with the real extension and a local server
- [x] Added 2026-10-31T11:35:20+05:30: Scheduled Statuses in the account page (the queue framed, D-106) and the
  capture fix (IN-14); 156 Node tests, pytest 1593 passed and 7 skipped (counted 2026-10-31 after
  d917694); extension version stays 2.1.0, `EXTENSION_MIN_VERSION` 2.0.0
- [x] Added 2026-10-31T12:23:37+05:30: the owner's review (D-107): one Schedule button with Next in queue
  and its time, the Account menu, the footer's fine print removed, the snackbar's width
  on a phone; extension 2.1.1, `EXTENSION_MIN_VERSION` 2.0.0; 157 Node tests, pytest 1613
  passed and 7 skipped
- [ ] The account section's "extension too old" state, driven in a browser
- [ ] Phase 0 on the owner's Chrome: a composer in a hidden tab, a tab never shown, an
  unfocused helper window on Linux, a tab moved without "Use here", a caption typed
  unfocused. [Unverified] until then
- [ ] A scheduled clip prepared in a real WhatsApp Web, by the owner
- [ ] Resume's three choices and the alarm rebuild on every wake, end to end
- [ ] A week of the owner's use of Prepare

**Next, in order:** Phase 0 by the owner; then confirmed Send (Phase 8, which needs the
owner's word and amends nothing until then, AGENTS.md Never, D-084); then Release 2
(from a link); then Release 3 (the bulk bar).

---

## T-072 (done) Keep the app's containers off the host's private network

**Finished:** 2026-10-26T01:29:37+05:30

**Goal.** Code that ever ran inside the app cannot reach the shared host, its
private network or the cloud's metadata service; everything the app calls still
works.

**Acceptance.**

- [x] Checked from inside the container first: the metadata service and the host's
  ports answered; the cloud CLI showed no dynamic group or policy giving the
  machine's identity any power
- [x] [deploy/egress.sh](deploy/egress.sh) and its systemd unit, matching only the
  project's subnet, idempotent; installed and re-applied by `scripts/deploy.sh`
- [x] After applying: all of those refused from inside the app; DNS, Google,
  Turnstile, Resend, GIPHY and Chat answer; the site passes its checks

---

## T-071 (done) A second security pass, and the first deploy from the public repository

**Finished:** 2026-10-25T22:43:40+05:30

**Goal.** No way in through a link, text, a script or a request trick, verified, and
the site running the public repository's code.

**Acceptance.**

- [x] Static audit (semgrep), dependency audit (pip-audit), container and deploy
  review; 133 defensive tests against a local copy
- [x] Every weakness found fixed with a test (D-101); LIMITATIONS.md, Table LI-13,
  for what needs the owner
- [x] Full suite, Node tests, `scripts/site_check.py` and `scripts/extension_check.py`
  pass locally
- [x] Pushed to `PalWorks/snipshare-whatsapp-status-maker` and deployed with
  `scripts/deploy.sh`, then checked on the live site

## T-070 (done) Audit and publish the repository

**Finished:** 2026-10-25T15:11:42+05:30

**Goal.** Make the repository public without legal exposure and without leaking
anything personal or infrastructural, after a strict audit of the whole codebase.

**Constraints.** The private repository's history must not become public (D-099).
Nothing that names the site, the host, a person or a key in a tracked file
(`tests/test_publishable.py`). Every finding proven against the code before it is
fixed; every fix with a test.

**Acceptance.**

- [x] Audit of the hosted site, the extension, the pages and the local engine; all
  findings fixed or recorded in LIMITATIONS.md, Table LI-13 (D-100)
- [x] Full suite and Node tests pass; the extension checked end to end against a
  local renderer, throttled, with the worker stopped mid upload and with Stop
- [x] Licence chosen by the owner and in place: LICENSE (AGPL-3.0),
  COMMERCIAL-LICENSE.md, THIRD_PARTY_NOTICES.md, CONTRIBUTING.md (D-099)
- [x] The hosted image installs only what the site runs; every page links to its
  source
- [x] Documents completed to the agent documentation guide and swept
- [x] A secrets scan (gitleaks) of the exact tree published, and the deny list test
- [x] Published as one commit to `PalWorks/snipshare-whatsapp-status-maker`
- [ ] Redeploy the hosted site with these changes, which needs the owner's go ahead
  (AGENTS.md, "Ask first")

## T-069 (done) An account page, both GIF keys, and no black first frame

**Asked 2026-10-25** by the owner, with screenshots: a separate account page opened
from the account icon, two columns, Profile, History, API keys, Feedback with a mail
behind it, sign-out; GIPHY and KLIPY keys kept together and switched between or
searched both; the clip's first frame black in WhatsApp's composer; and the
extension's folder renamed `src/`. Plan in [docs/account-page.md](docs/account-page.md);
DECISIONS.md D-094 to D-096.

**Acceptance, all met:** the page at 360 and 1280 pixels, light and dark, every
section; both keys stored, masked, never sent back whole, the choice falling back
when a key is removed, an old one-key database migrated in place; a search of both
asking the two at once and mixing them; history recorded for made and failed clips
and removed with the account; feedback mailed with the person's reply-to and refused
when empty or too frequent; a made clip's first frame measured and not black; the
suite and `scripts/site_check.py` green; deployed.

---

## T-068 (done) SnipShare: the full page, hosted, for invited people

**Asked 2026-10-24** by the owner, testing the extension: show the full page they
already use, from the extension's button, for anyone who loads the extension, with
the popup flow kept but switched off. Then: a sign-up form with Google, the owner
told by mail and in Chat, approval, abuse protection and failure reporting, people's
own GIF keys, the extension requirement said everywhere it applies, a contained
deployment, and a repository fit to publish. Plan and decisions in
[docs/hosted-page.md](docs/hosted-page.md); DECISIONS.md D-087 to D-093.

**Acceptance, all met:**

- Public pages (`/`, `/install`, `/privacy`, `/terms`, `/signup`, `/signin`), mobile
  first, light and dark, checked at 360 and 1280 pixels; the extension requirement
  on each; Google's sign-in button and Turnstile render on the live site.
- A request notifies the owner once, by mail and in Chat; an unapproved address
  cannot sign in; the admin approves, declines, suspends, adds and deletes on
  `/admin` or with `wastatus hosted user`.
- One person cannot see, fetch or delete another's clips or stickers; a cookie alone
  cannot act; another site cannot post with the session; grants do one thing each.
- Limits: 10 clips and 500 MB a day, one render at a time, 60 an hour across
  everybody, all refused before the extension reads anything.
- End to end, in a throwaway Chrome with the built extension: words fetched, a card
  clip and a video clip made from a real YouTube video through ads, in 18 to 35
  seconds, locally and against production; Load into WhatsApp reaches WhatsApp Web
  and reports it not signed in, as a throwaway profile is.
- Two independent audits; every confirmed finding fixed with a test.
- Production: the old container, Caddy block, A record, image, folder and volume
  gone; the tunnel serving the site; the uptime monitor green throughout; the other
  sites on the host answering as before.

**Still the owner's:** the first real request from a second Google account, approval,
and a clip loaded into the owner's own signed-in WhatsApp Web with the production
extension; publishing the Google consent screen now that `/privacy` and `/terms` are
live.

---

## T-067 (done) A dash between spaces keeps its space

**Found 2026-10-24** reading a frame the hosted renderer made: "Ed Sheeran -Shape of
You". `compose._join` dropped the space after any line ending in a hyphen. See
[DECISIONS.md](DECISIONS.md) D-086.

---

## T-066 (done) The browser extension and the hosted renderer

**Asked 2026-10-24:** "Can we build a chrome extension for this repo, so that whoever
runs it, they run the app from their own system and thus data-center IPs don't get
flagged for using yt-dlp." Then, after the spike: "plan well in a detailed manner
... and then execute step by step without making any mistakes."

**Plan and record:** [docs/extension.md](docs/extension.md). **Decisions:** D-080 to
D-085. **Deployment:** [DEPLOYMENT.md](DEPLOYMENT.md).

### What was built

| Part | Where |
|---|---|
| The engine takes a captured window | `pipeline.Captured`, `wastatus/capture.py` |
| The hosted renderer | `wastatus/hosted.py`, `wastatus hosted serve` and `token` |
| The extension | `src/`, loaded unpacked |
| Production | one host, a self-contained Compose project behind a Cloudflare Tunnel, `deploy/`, `scripts/deploy.sh` |
| Checks | `tests/test_capture.py`, `tests/test_hosted.py`, `tests/test_extension.py`, `src/test/media.test.js`, `scripts/extension_check.py` |

### Acceptance, each verified on 2026-10-24

- A card and a video clip from a real YouTube video, end to end against production,
  through the extension's own worker and through the popup's own buttons.
- In the owner's own Chrome, signed out with ads and signed in with Premium:
  capture, upload, render, download, and the clip loaded into WhatsApp Web's Status
  composer with its caption, then closed without sending.
- Sync: the beep and flash test video through the whole production pipeline, flash
  on the frame, beep 0.6 ms after.
- In-page navigation: the clip is the new video's, correlation 0.94, and not the old
  one's, 0.04.
- Bad network: 800 kbit/s through Cloudflare with the extension's worker stopped mid
  upload; it resumed from the server's offset and finished.

---

## T-065 (done) Send has no icon any more

**Found 2026-10-24** while testing the extension spike against the owner's own
WhatsApp Web, not reported as a failure. `SEND_ICON` matched no element on a page
showing a loaded composer.

Send is matched by its label as well as its icon, `COMPOSER_OPEN` is the narrower
"is one already open" check, and `cancel` knows the text composer's close control.
Three tests pin the selectors.

**Verified 2026-10-24** through `load_video`, `load_text` and `cancel` on the live
page, without sending. See [DECISIONS.md](DECISIONS.md) D-079.

---

## T-064 (done) Audit the codebase after D-075 to D-077

**Asked 2026-08-31:** "do a detailed audit of our entire codebase now, update all
documentation, and push everything to GitHub please."

### What it found

The one that matters: **`tests/test_safe_zone.py` was passing against a layout the
renderer had stopped drawing.** It duplicated the card-mode arithmetic instead of
calling it, D-075 changed the drawing, and the copy kept agreeing with itself. The
file that guarantees text never lands under WhatsApp's furniture was guaranteeing it
about a frame that no longer existed.

`compose.card_words` is now the single answer both the drawing and the measuring
ask. `_painted_rows` paints what it is handed and decides nothing.

Then: the follow up text Status had neither retry nor sheet row, `eyebrow_room` was
dead, and four documents plus one CLI help string still described the old placement.
All fixed.

### What it confirmed

Every `D-` and `T-` reference resolves, no relative link is broken, nothing is
defined and never used, and the security surface (token comparison, path
validation, the static allowlist, log hygiene) is as the documents describe it.

See [DECISIONS.md](DECISIONS.md) D-078.

---

## T-063 (done) The preview pane accounts for what it cannot draw

**Asked 2026-08-31:** "If I place a GIF, the tooltip above post it section correctly
shows that the clip has changed and I have to regenerate. But similar message is not
showing in the preview pane."

`drifted` names eight kinds of change; `aheadOfClip`, which the pane runs on, knew
three. Stickers, the waveform and the mode cannot go into a still on purpose, so the
pane names them instead of going quiet. A change it can draw still wins.

See [DECISIONS.md](DECISIONS.md) D-077.

---

## T-062 (done) The pencil edits the line in place

**Asked 2026-08-31:** "if I insert a free text into the preview pane, and then click
edit (pencil) icon, I thought it will edit in-situ... Can we create functionality such
that it will edit in-situ and parallely update within the freetext input box too?"

A real input laid over the drawing, inside the same decal box so it carries the
rotation. `applyText` is the only writer and keeps all three holders of the string in
step, never rewriting the box the keystroke landed in. The box in Extras is still the
one that inserts, and is still the fallback for when the layer is folded away.

**Verified 2026-08-31** by driving the page: pencil opens the editor over the line at
its size, typing on the frame reaches the box, typing in the box reaches the frame,
and Enter puts the drawing back with the text kept.

See [DECISIONS.md](DECISIONS.md) D-076.

---

## T-061 (done) One field, one place, and no line dropped in silence

**Asked 2026-08-31:** two reports. "If I type something in the text at the top input
box, I'm not able to preview it." And "if I type anything into text above title, that
should come under the artwork-card / video-frame, but above the video title. Instead
it is appearing above the artwork-card / video-frame itself."

One cause. The label was anchored to the card in card mode and to the title in video
mode, and it took the band the top text needed. A full height card's top lands on 325
and one line of top text needs 344, so the block wrapped to zero lines and was drawn
as nothing, with the words still in the box and still in the sidecar.

The label hangs off the title in both modes now and the picture gives way for it in
both. A fitted card shrinks for the top text; a placed one is never moved and the
page says so instead.

See [DECISIONS.md](DECISIONS.md) D-075.

---

## T-060 (done) The sheet records what went out

**Asked 2026-08-31:** "whatever status I'm publishing via this project, can you make
a record in this google spreadsheet... It is a private sheet and I want it to remain
so", followed by "Failed posts do not get a row."

### What was built

`wastatus/sheet.py`, and one call at each of the two places a Status is sent. Four
columns, the sheet's own: Timestamp, Source, Status, Remarks. Source comes from the
clip's sidecar rather than from whatever URL each caller happened to hold, so the
page and the CLI write the same form of the link into one column.

A service account, so the sheet stays private and shared with exactly one robot
address, and so nothing expires. Every failure in the module is caught and
swallowed: an unreachable sheet costs a row, never a Status. With no
`WASTATUS_SHEET_ID` it is inert.

**Verified 2026-08-31** against the real sheet: credential reads *WhatsApp Status
Publish DB*, and the row for the 21:13 Status landed at row 4, below the two legend
rows and without touching them.

See [DECISIONS.md](DECISIONS.md) D-074.

---

## T-059 (done) A refusal is tried again, no answer never is

**Asked 2026-08-31:** "We need to build a retry and backoff mechanism for failures."

### What was built

`post.send_with_retry`. It hangs on a distinction that only exists because of T-058:
`StatusRefused` is WhatsApp answering no, so nothing went out and a retry cannot
double post; `StatusUnconfirmed` is no answer at all, and is raised straight through
because a Status that may yet go out must never be sent twice to settle a doubt.

Three attempts, twenty seconds apart and doubling. The wait is real: an immediate
retry is the same attempt written twice. `WASTATUS_POST_ATTEMPTS` and
`WASTATUS_POST_BACKOFF` move both. `on_retry` reports the wait, so neither the page
nor the CLI looks like it has hung.

See [DECISIONS.md](DECISIONS.md) D-073.

---

## T-058 (done) Know whether a Status actually went out

**Asked 2026-08-31:** "My WA web interface shows as though the video has been
published, but in-reality it has not got published. I'm unable to see my own status
on my mobile phone + its views are only zero."

### What was built

`post.confirm_sent`, reading the `ack` WhatsApp Web keeps against the message, and a
scoped `COMPOSER` that no longer matches the chat's own box.

**The old check had never been a check.** It asked whether the composer had closed.
Every posting run in `logs/runs.jsonl`, all of them, returned exactly `4.0` seconds,
which is two seconds of sleep in `click_send` plus two polls two seconds apart.

**What was actually there**, in `model-storage` → `message`:

| Sent | ack | |
| --- | --- | --- |
| 18:14 | 3 | did not land, 0 views |
| 19:21 | -1 | refused outright |
| 21:13 | 3 | first post through the new code. Landed, 18 views in nine minutes |

The owner confirmed the third from his phone. Every Status before it, through the old
code, had failed to land.

See [DECISIONS.md](DECISIONS.md) D-071 and D-072.

---

## T-057 (done) One rhythm down the column of cards

**Asked 2026-08-27:** "Can you equi-space all these sections?", arrow at the seam
between Extras and Stickers.

### What was built

One line. `.stack` takes the same gap the page grid takes, from 600px up.

**Measured before**, at 1920 wide: 12, 12, 12, 20, 20, 20 down the seven cards. The
seam is where the form ends, and nothing on the screen says a form ends there.
**After**: 20 six times. On a phone it is 12 eight times, before and after, because
that is the width where the two rules already agreed.

### Found in passing

Nothing was broken in either rule. Each was written for its own container, months
apart, and the fault is only visible as the two of them down one column. The test
that guards it asserts the two selectors carry the **same value** rather than any
particular value, which is the only shape that catches this.

---

## T-056 (done) The page says each thing once

**Asked 2026-08-27**, marked up on a screenshot of the footer: "Move this text into
the 'recents' section", "This info is already available under \"All set\"isn't it? We
can remove it from desktop view. But keep it at bottom of page in mobile view", and
"Also the URL needs to have the port too: 8765".

### What was built

| Piece | Where |
|---|---|
| The output folder and retention, under the strip it describes | `#foot-out`, now in the Recent card |
| A rule above it, because it describes rather than continues | `.recent__where` |
| The footer folded away on a laptop | `.foot { display: none }`, at 901px |
| The address given its port | `foot-reach`, the same expression the chip's row uses |

**The id did not change when the line moved**, so the one place in the script that
fills it is untouched. A test asserts it is in the Recent card and no longer in the
footer, because the failure mode of a move like this is having it in both.

**Measured in a browser.** At 1920 wide the footer computes to `display: none` and
the line reads under the Recent strip; at 500 wide the footer is the last thing on
the page and reads `Also reachable at 100.64.0.7:8799. Nothing is sent until you
press Send.` The port is the page's own, so it is right whatever the tool was started
on.

### Found in passing

**It made T-055 better.** The footer was most of the page sitting below the grid, and
that height is what pulls a sticky column off its anchor at the end of a scroll. The
ride up was 74 pixels; it is 32 at 1440x773 and none at all at 1920x1033. D-067 and
LIMITATIONS.md now carry the measured numbers instead of the old ones.

**What was dropped rather than moved.** "Nothing is sent until you press Send" was
the other half of the reachable sentence and goes with it on a laptop. Named in D-069
so the loss is a decision rather than an oversight.

---

## T-055 (done) The frame stays on screen, and the fold control grows

**Asked 2026-08-27:** "in desktop view alone, can we make a dual column setup, such
that the right side column contains 'preview section' and is always fixed in view...
the left side column will contain all our other sections (Let's move the 'post it'
section to the left side, just above the recents section) and we'll make it such that
this column can be scrolled up / down, while keeping the right side preview section
fixed." And: "for all our sections, we have a arrow symbol that indicates minimize /
maximize right? Can we make it a bigger chevron or a plus/minus button?"

### What was built

| Piece | Where |
|---|---|
| Post it moved into the scrolling column, above Recent | `index.html`, one block moved |
| The frame's column stuck under the top bar | `#clipside`, inside the 901px query |
| The bar's height, measured rather than typed | `measureTopbar()` in `app.js` |
| The frame sized to the height that is left | `clamp()` on `.phone__screen, .player` |
| Its ceiling raised to 360 once the page is full width | `--frame-max`, at 1180px |
| The frame's column sized to the frame | `.grid` columns, `1fr` and 334px |
| A 24px chevron in a 32px target | `.accordion__caret`, all eight cards |
| The header action given a name of its own | `.headeraction`, was `.iconbutton` |

**The DOM move is the whole layout change.** Panel order on a phone is decided by
`order`, not by the DOM, so moving Post it from one column to the other moved it on a
laptop and nowhere else. Verified at 500px: form, preview, stickers, post, recent, in
that order, exactly as before.

**Measured in a browser** at 1440x773. The frame comes out 277 by 493 with 8 pixels
of air below the player. Scrolled to the sticker shelf and to the send buttons, the
card stays at 93 pixels from the top with the top bar's own 85 above it. The clamp
was exercised at both ends by moving `--topbar`: a tall screen caps out, a short one
floors at 168. Dark and light both checked, and the phone view screenshotted.

**Then the frame was asked to be bigger**, looking at a 1920 wide screen where it was
300 in a 334 pixel column. The ceiling is 360 from 1180px up: measured at 1920x1033
the frame is 360 by 640, which is exactly a third of the clip, and at 1000 wide it is
300 in a 334 pixel column with a 598 pixel column of fields, unchanged to the pixel.

### Found in passing

**A silent regression from the same morning.** The fetch icon in T-052 was given the
class `.iconbutton`, which the top bar's theme and health buttons already had. Same
selector, later in the file, so it stripped the border and the surface background off
the theme button in the top bar and shrank its glyph by a pixel. Renamed to
`.headeraction`, and a test now asserts `.iconbutton` is declared exactly once.
D-068. This is the second defect this week that came of a change nobody looked at in
the place it landed, after the focus into a folded card in T-052.

**What was accepted rather than fixed.** At the very bottom of the scroll a sticky
item reaches the end of its grid area and rides up, so the preview card's header
tucks under the top bar by up to 66 pixels. The frame and the player never do. The
arithmetic and the two alternatives are in D-067; both cost more than the symptom.

---

## T-054 (done) Make the clip goes grey when there is nothing to make

**Asked 2026-08-27:** "Once a clip is made, can we grey out this make the clip
button? We can re-enable it only when some kind of change has happened anywhere on
the setup (Either in the text input boxes / emojis / GIF / preview section / and
anywhere else). This will act as subtle user feedback that whatever is shown on the
preview section is final and there is nothing more to be executed."

### What was built

| Piece | Where |
|---|---|
| `settled()`: the clip on screen is everything the form asks for | `app.js`, D-066 |
| The button, and the line that says why it is grey | `paintMake()`, `#make-note` |
| One repaint hook every control already reaches | inside `paintStale()` |
| ⌘/Ctrl+Enter stopped as well | the `submit` handler |

**"Anywhere else" is the requirement, so it is not a list.** `paintStale` is reached
by `paintSummaries`, which is reached by `remember`, which every control on the page
calls. Hanging the repaint there means a control added next year is covered without
anybody remembering to add it here.

**Measured in a browser** rather than reasoned about: opening a clip greys the
button, and each of the title, the second line, the top text, the link, the start,
the length, the end, the waveform, the mode, the background, a placement and an
inserted line of free text brings it back, with every one of them returning it to
grey when put back. ⌘/Ctrl+Enter with the button grey started no render.

### Found in passing

Nothing new. The one thing worth knowing is written into D-066: `drifted` leaves the
link and the window out on purpose, so wiring the button to it alone would have left
it grey after a new link was pasted, which is the most ordinary thing anybody does
on this page.

---

## T-053 (done) Emoji in a placed line

**Asked 2026-08-27:** "our free-form text, can it not accept emojis? Can we enable
that functionality in that text input box please?"

The box always accepted them. Pillow drew an empty rectangle for each one, because
the line is set in DejaVu and DejaVu has no emoji.

### What was built

| Piece | Where |
|---|---|
| What counts as a picture rather than a letter | `freetext.EMOJI`, deliberately narrow |
| The lookup, cached, exact name then without `FE0F` | `freetext._picture` |
| One layout used by both the measurement and the drawing | `freetext._layout` |
| The square, hung off the letters' baseline, with its own shadow | `freetext.render` |

**Where the pictures come from:** the OpenMoji library the sticker picker already
installs, so nothing new is downloaded, nothing new is depended on, and a clip made
on macOS matches one made on Linux. See D-065 for the two routes that were rejected.

**Proved rather than asserted:** 40 renders of lines with no emoji in them, at four
widths, are byte identical to the same lines before this existed, `★ ♪ © ® ™` among
them. A line with emoji was drawn through the running server and through
`compose.build_card` at full frame scale.

### What it does not do

An emoji this machine has no picture for is left out of the line rather than drawn
as an empty box, and a line that is only such an emoji is refused with the one
sentence that fixes it. See LIMITATIONS.md.

---

## T-052 (done) Fetch the video's own words

**Asked 2026-08-27:** "Incase I want to fetch the title, sub-title etc before
creating the clip, can we have a fetch / refresh icon here? So that I can click it,
fetch these text data from metadata of the video clip, and edit them before hand
itself, so as to save one iteration."

### What was built

| Piece | Where |
|---|---|
| The words a video answers for itself | `pipeline.words_from_video` |
| `POST /api/words`, synchronous, 45 second patience | `serve.App.words_from`, `_words` |
| The icon, in the Words header where the answer lands | `#words-fetch`, `.iconbutton` |
| Two guards for a slow link: a counter and the video key | `fetchWords()` in `app.js` |

**The one property that matters** is that what Fetch offers is what an empty pair of
boxes means, exactly, because it comes back as an override down a different code
path. `words_from_video` asks `title_and_channel` for a job that overrides nothing,
so the two cannot drift, and the round trip is a test over five real title shapes
including a Tamil one.

**Measured end to end:** a real probe of a real link answered in 1.5 seconds, the
icon spun while it waited, the boxes filled, the Words header filled with them, and
the card opened. A pasted playlist came back with the refusal `fetch` already writes
for that case, and the empty box came back as a 400 without yt-dlp being started.

### Found in passing

Pressing the icon with no link in the box focused a box inside a folded card, which
cannot take focus. The link card is opened first now. This is the second time that
exact defect has appeared, after the picture box in T-050.

---

## T-051 (done) A pencil on a line of words

**Asked 2026-08-27:** "In our preview section, in desktop view, can we show an edit
pencil icon for text elements on hover? Clicking that pencil icon should allow
editing functionality same as the text input boxes." And, in the same message:
"kindly improve the UI UX of this section. Currently it looks too congested."

### What was built

| Piece | Where |
|---|---|
| A fourth handle, on free text alone | `handles(decal)`, `.decal__handle--edit` |
| Shown on hover, and only where there is a mouse | `@media (hover: hover) and (pointer: fine)` |
| The action: open the section, scroll, focus, select | `editText`, D-063 |
| Look regrouped: a label on the first field, a rule, two columns | `.fieldgroup`, `index.html` |

**Look was three stacked label-control-hint blocks** and read as one wall of small
print. The first field had no label at all, which is what made the second one's look
like a heading for the whole panel. It has one now, "Made from", and the two fields
that answer to it sit under a rule and side by side wherever there is room. Card mode
hides Background entirely, so the grid is `auto-fit`: the field left behind takes the
width rather than half of it.

### Found in passing

`setMode` unchecked **every** segmented option on the page rather than its own three,
and Background has nothing that puts its own back: switching between Artwork card and
Video frames left it showing neither Blurred video nor Black until one was clicked.
And the rotate handle's pale icon was drawn on a system-light page, near-white on
near-white. Both fixed here; see D-063.

---

## T-050 (done) Place the artwork panel too

**Asked 2026-08-27:** "Go ahead with option-A for card mode", choosing from three
ways the words could respond to a panel that moves.

### What was built

| Piece | Where |
|---|---|
| The panel's rectangle, fitted or placed | `compose.card_rect`, D-062 |
| The row the words hang from, clamped to what they can survive | `compose.card_words_anchor` |
| The artwork's shape, for the sidecar | `compose.card_aspect` |
| The shade that keeps the title readable over a panel | `compose._bottom_shade`, shared with video mode |
| The preview, drawn from the artwork rather than rebuilt from a still | `App.preview_jpeg`, `App.rebuilt` |
| The same box, grip and arrow keys as video mode | `#picture-box`, `sameKind()` |

**Option A was chosen over the two alternatives.** The words follow the panel, which
is how card mode was already laid out; the label is anchored to the panel's top edge
and the top text sits above the label. What is new is that the anchor can now be
anywhere, so it is clamped at both ends. Every fitted card sits inside those clamps,
which is why the archive did not move: 15 fitted cards across five artwork shapes and
three sets of words render byte for byte as they did.

### Known and deliberate

Dragging the panel high squeezes the top text and can leave no room for it at all,
which is the trade Option A was chosen with. It is visible while you drag, because
the preview is the real layout. The panel keeps whatever crop `card_height` gave it
rather than un-cropping as it is resized: see D-062, and LIMITATIONS.md.

---

## T-049 (done) Place the picture yourself

**Asked 2026-08-26:** "Similar to resizing text & GIF, can we create an option to
resize video / artwork?" and, when offered it in stages, "I ideally prefer full
drag-anywhere plus resize".

### What was built

| Piece | Where |
|---|---|
| A placement: a centre and a width, in fractions of the frame | `render.Framing`, `parse_framing`, D-061 |
| The rectangle it resolves to, given the source's shape | `render.placed_rect`, and `framing_of` for the way back |
| Both fills able to take a picture that hangs off an edge | `render.picture_steps`, which no longer uses `pad` |
| The job, the sidecar, the page and the command line all carrying it | `Job.framing`, `--picture X,Y,SIZE`, `POST /api/render` |
| Its own box on the frame, with one corner grip | `#picture-box`, deliberately not a `.decal` |
| The same arrow keys, `+` and `−`, and Escape | `drivePicture`, sharing the steps with T-048 |
| Rebuilding the frame to preview it | `render.recompose`, which now moves the picture as well as changing what is behind it |

**The top line no longer chases it.** The top text is anchored to the picture's top
edge, T-043, and a picture somebody placed themselves can start anywhere at all,
including below the words. `compose.topline_top` clamps the anchor at
`VIDEO_PICTURE_BOTTOM` as well as at `TOPLINE_TOP`. Card mode's anchors sit far above
that ceiling, so it costs them nothing.

### Known and deliberate

Video mode only, until T-050 did the same for card mode's panel a day later.
Rotation is not offered, because turning the frames would leave corners with nothing
in them. And the preview cannot
show picture the still never kept, which is the one case where the clip has more than
the preview does: see D-061.

---

## T-048 (done) The keyboard drives the frame

**Asked 2026-08-26:** "while I'm resizing, dragging, deleting elements on our
preview (like GIFs, texts etc) in desktop mode, I would like to use keyboard buttons
such as delete, Esc".

### What was built

| Key | Does |
|---|---|
| Arrows | nudge by half a percent of the frame; with Shift, two per cent |
| `+` `−` | size by one per cent; with Shift, five |
| `[` `]` | turn by a degree; with Shift, fifteen, through the same `settle` a twist uses |
| Delete, Backspace | remove it |
| Escape | put it down, and let go of focus so the next Tab carries on through the page |
| Enter | on a line of free text, put the caret in the box that wrote it |
| ⌘Z, Ctrl+Z | bring back the last thing removed, wherever it was removed from |
| Tab | reach the next placed thing without a pointer at all |

Everything is clamped to the bounds the server clamps to, in the fractions the
renderer is sent. See D-060 for why focus and selection are the same thing here, why
nothing fires while you are typing, and why one slot of undo arrived with the keys
rather than before them.

---

## T-047 (done) Black behind the frames

**Asked 2026-08-26,** over a screenshot of the preview: "currently the same video is
run in BG, in a blurred fashion, isn't it? Can we have an option to keep this
blurred functionality or keep a simple plain BG?"

### What was built

| Piece | Where |
|---|---|
| One `pad` instead of a blurred copy, and why it is not a `color` source | `render.picture_steps`, D-059 |
| The choice, on the job, in the sidecar, on the command line | `Job.fill`, `--fill`, `POST /api/render` |
| The control, in Look rather than beside Safe areas | `#fill-field`, D-059 |
| Building the frame again to preview it | `render.recompose`, from the still already kept |
| The whole picture rectangle in the sidecar, not only its top edge | `pipeline.produce`, which is what `recompose` needs to know which pixels to keep |
| The word preview's hole closing while the two backgrounds disagree | `App.moving_band` |

**Measured on the first clip through it:** 439 kB against 598 kB for the same three
seconds, 27 per cent smaller, because nothing outside the picture moves for the
encoder to spend bitrate on. Against WhatsApp's 10 MiB ceiling that is bitrate handed
back to the picture.

**Known and deliberate.** Video mode only: a card composes its own background, scrim
and shadow together, and swapping that for black is a redesign rather than a setting.
Clips made before the rectangle was recorded cannot be previewed on a different
background, and say so rather than showing a picture identical to the one underneath.

---

## T-046 (done) Free text you put where you want it

**Asked 2026-08-26**, over a screenshot of the Extras panel: "Can we have a new
button called Free Text here, which can be moved around and resized, like our GIF
image? (and can also be inserted multiple times like our GIF images?)"

Everything this tool draws was laid out by `compose`: the title where the title
goes, the label above it, the top line under WhatsApp's header. Three boxes that each
put a line **where the layout says**. There was no way to put a word anywhere else on
the frame, which is what a hook, a date or a caption over somebody's face wants.

### What was built

| Piece | Where |
|---|---|
| One line, cleaned, measured and drawn to a transparent picture | `wastatus/freetext.py` |
| `POST /api/text` | the page places a picture of the line rather than setting the words itself, D-058 |
| Placed, dragged, resized, turned and deleted like a sticker | the same `.decal` box and the same handles, so nothing new had to learn about gestures |
| Pasted into the clip by the same call the page previewed with | `stickers.paste`, through `Placed.art` |
| Kept in the sidecar with the clip | so a clip re-opened from Recent still has its lines |
| Insert, and retype the selected one, from one box | `#text-line` and `#text-add` in Extras |

**The size is the width of the line.** Dragging the corner sets a fraction of the
frame and the face follows from it, so a longer line at the same width is set
smaller. That is what let a placed line go through `paste` with no second code path,
and it is the same bargain a text box makes in any design tool.

**Two things came out with it**, both from the same markup:

- The Extras boxes are named for where their line lands and listed in that order:
  **Text at the top**, **Text above title**, **Text below sub-title**, then Free
  text. They used to be listed in the order they were built, so finding the one you
  wanted meant reading all three. The label above the title stopped following the
  mode with the rename: it sits above the card in one mode and above the words in
  the other, and both of those are above the title.
- **The resize handle now says it resizes.** `cursor: nwse-resize` was declared on
  it and lost, every time, to the three-selector rule above it that gives every
  handle a pointer. The corner of a sticker said "click me" like a link. The cursor
  also stays with the gesture now: the pointer leaves the handle within a few pixels
  of the press, and the frame wears the gesture's cursor until the hand comes off.

### Known and deliberate

The line is one line: newlines fold into spaces. Sized by its width, a second line
would halve the face on a drag nobody made, and two lines are two texts, each
dragged where it belongs. There is no colour or font choice: white, bold, with a
drop shadow so it stays legible over a bright frame.

---

## T-025 (done) Let the page say it is loopback only

**Priority:** P2
**Status:** **done, 2026-08-20.** Route A was chosen and built the same evening

**The problem.** `--also-on tailscale` is passed at every start and remembered
nowhere, by design, see [DECISIONS.md](DECISIONS.md) D-027. When it is missing the
phone gets a refused connection, which names no cause, and the laptop's page gives no
hint either, because from the laptop nothing is wrong. The document now says all of
this, [LOCAL_SETUP.md](LOCAL_SETUP.md) and [RUNBOOK.md](RUNBOOK.md) both, but a
document is read before the mistake and the page is looked at after it.

**What already exists.** `App.state()` carries `also_on` and `host`, both added on
2026-08-19 and 2026-08-20, and the health panel already draws three rows and names
the machine. Nothing new has to be plumbed.

### Table T25-1: the three ways to close it

| Route | What it costs | What it buys | What it risks |
|---|---|---|---|
| **A: a fourth row in the health panel** | about an hour. One row, green with the tailnet address when `also_on` is set, grey and reading "this laptop only" when it is not | the answer sits with the other three checks, which is where you already look when something is off. The address is then copyable rather than remembered | a fourth row in a panel that was cut to one chip for a reason, D-029. It is grey and not amber, so the chip stays green |
| **B: a line under the Download button on the away layout** | half an hour | it lands where the phone user is looking | the phone can never see it, because the phone cannot load the page at all in the failing case. **This route does not solve the reported problem** |
| **C: print the address into the health panel only when asked** | least of the three | no new persistent chrome | one more thing to know to press |

**Recommendation: A.** It is the only one that shows up in the case that actually
bites, which is the owner at the laptop wondering why the phone will not open it. The
row is informational and grey rather than amber, so a laptop only run is not dressed
up as a fault: it is the default and it is usually right.

### What was built

A fourth row, `another device`, under the three checks in the health panel.

| The server was started | The row says | The dot |
|---|---|---|
| `serve --also-on tailscale` | `open http://100.x.y.z:8765 there` | green |
| `serve` | `this laptop only. Restart with --also-on tailscale to reach it from a phone` | grey |

The address is built from `also_on`, which is the bare address, and the page's own
port, because an address without a port is not something anyone can type in.

**The grey row is not counted as a failing check.** `paintStatus` filters it out of
`bad`, so the chip still reads **All set** on a loopback only run. Verified in both
states on 2026-08-20 against a server on a scratch port: with the flag, four green
rows and the tailnet address; without it, the grey row, the chip still green.

**Not to be built: remembering the flag.** Rejected in D-027 and rejected again here.
A machine that reopens a posting surface at every boot is the thing the owner does not
want, and it is the same reason there is no autostart service, D-028.

---

## T-030 (closed) Frame the video yourself, instead of taking the blurred fill

**Priority:** P2
**Status:** **closed 2026-08-21 by the owner, without building.** "It doesn't add
much value to what we already have." Kept in full, because the measurements are the
reason and a reason is worth more than a decision on its own

**What video mode does today.** A 16:9 source is scaled to the full width and centred,
so it sits as a strip across the middle, and the space above and below is the same
frame blown up, blurred at `sigma=28` and darkened. Baked in letterbox bars are
detected and cut off first, `detect_source_crop` (T-043 folded it into
`source_picture`, which returns the crop and the size together), or they would show as hard seams
inside that blur. The picture is never cropped for framing, only for bars.

**What is being asked for** is the sticker treatment applied to the video: drag it to
choose what shows, pinch it to choose how much.

### What the research settled

**The renderer is most of the way there already.** The chain is
`scale=WIDTH:-2:force_original_aspect_ratio=decrease` then a centred overlay. A zoom
and an offset replace two numbers in that. The whole fractions of the frame model,
the gesture code, the safe band overlay and the handles all exist from the sticker
work and transfer directly.

**Text legibility is not an obstacle, which it looked like it would be.** Video mode
already paints a gradient scrim from 63% of the height down to the bottom, precisely
so text survives a bright frame. A filled frame does not change that.

**The real obstacle is the feedback loop, and it is measured.** Direct manipulation
only feels direct if the answer is instant. A sticker is instant because the browser
draws it. A crop is not, because the browser has never seen the source: the work
directory is deleted at the end of every render, `shutil.rmtree` in `pipeline`. So
adjusting a crop today means a fresh download and a fresh render.

| Measured from the run log, 18 video renders | |
|---|---|
| Download a section | **5 to 13 seconds** |
| Render | **23 to 95 seconds** |
| End to end | **37 to 111 seconds per attempt** |

Nobody frames a shot at a minute an attempt. So the interesting version of this
feature is not a renderer change, it is **keeping the source section and serving it
to the page**, after which the browser can preview the crop as fast as it previews a
sticker and the render happens once, at the end.

**What keeping it costs.** Measured across 70 sections in the run log: median
**1.5 MB**, largest 7.9 MB. Twenty of them, matching `keep_last`, is about **30 MB**.
Retention already exists and already prunes by group, so this is a suffix to add, not
a mechanism to build. There is 32 GB free on this machine.

**The bonus that falls out of it.** A kept source also means changing the window, or
the look, or the words, without downloading anything again. That is the same 5 to 13
seconds saved on every re-run, which is most re-runs.

**The thing to say out loud: filling the frame throws away most of the picture.**
Going from 16:9 to 9:16 discards about **68% of the width**. For a film song with two
people in shot, or with lyrics burned into the video, a centre crop ruins it, and the
blurred fill exists precisely because it does not. So filling is a per clip judgement
rather than a better default, which is an argument for the version that lets the eye
decide rather than for a switch that decides in advance.

### Table T30-1: the three ways

| Route | What it costs | What it buys | What it risks |
|---|---|---|---|
| **A: a Fill or Fit choice, no dragging** | about **two hours**. One parameter into the existing chain, a pair of buttons beside **Artwork card** and **Video frames**, and tests | most of the value. A talking head or a single performer fills the frame instead of sitting in a letterbox | it crops from the centre, which is a guess. On the clips where the centre is wrong there is nothing to do about it but switch back |
| **B: Fill, plus a horizontal nudge** | about **half a day**. A single slider, in fractions, the same units the renderer already takes | covers the common case where the subject is off centre, without serving anything new | still a slider and still a render per attempt, so it is aim, wait a minute, look, aim again |
| **C: drag and pinch the source in the frame** | about **a day and a half**. Keep the section, serve it, put the existing gesture code on the video element, then one render at the end | the thing that was actually asked for, and it makes every other re-run 5 to 13 seconds faster as a side effect | the pipeline stops throwing its work away, which is a real change: a new file per clip, a new route, and retention has to learn the suffix |

**Recommendation: C, and A first if it wants proving.** C is the only one where the
feedback is instant, and instant is the whole reason the sticker controls work. It is
also the only one where the 68% you are throwing away is something you can see while
you decide. A is two hours and would tell you within a day whether filling the frame
is something you actually want on these clips; if it is not, C is not worth a day and
a half and the question is closed cheaply. B is the one to skip: it costs half of C
and keeps the slow loop that makes framing unpleasant.

### The owner's answer: none of them

Read and closed the same day. The blurred fill already does the job on his material,
and nothing in the research argued hard enough against it: the two hour version crops
from a guess, and the day and a half version buys precision over a decision he does
not often need to make. **The 68 per cent figure is what settled it.** Throwing away
that much of a film song's frame is a large cost for a framing choice, and the fill
keeps the whole picture.

**What would reopen it**: material where the subject is reliably off centre, or a run
of clips where the letterboxed strip looks wrong. Neither is today's problem. If it
does reopen, route A is still two hours and route C is still a day and a half, and
nothing here needs re-deciding.

**What was worth keeping anyway**: that the pipeline deletes its work directory at
the end of every render, so every re-run pays 5 to 13 seconds to download a section
it already had. That is true whether or not this feature is ever built, and it is
cheap to change if a re-run ever feels slow.

**Not to be built: cropping the finished clip.** Re-cropping the mp4 that already has
text and stickers burned into it would scale the text with the picture and crop the
words off the edges. The crop belongs where the source is still separate, which is
inside the render, before the overlay is composited.

---

## T-029 (done) A GIF picker in the page

**Priority:** P2
**Status:** **done, 2026-08-21.** Researched, decided and built the same day. The
design is [DECISIONS.md](DECISIONS.md) D-043

**What is being asked for.** Today a GIF arrives by paste, or by Upload now that the
file dialog stops hiding them. Both mean leaving the page: find a GIF somewhere,
save it, come back. The ask is to search and place one without that round trip.

### What the research settled

**Every usable source needs an API key.** Probed on 2026-08-21, with no key and a
generic search term:

| Source | Answer without a key |
|---|---|
| Tenor, `tenor.googleapis.com/v2/search` | **403.** `Method doesn't allow unregistered callers`. Needs a Google Cloud project and an API key |
| GIPHY, `api.giphy.com/v1/gifs/search` | **401 Unauthorized.** Needs a key from their developer site, which is a free signup and not a cloud project |
| Wikimedia Commons | **works, no key**, and is not a substitute. A search for an animated flower returned **one GIF in five results**, the rest stills, and they are encyclopaedic images rather than anything anybody would put on a Status |

**This would be the first thing the tool talks to that is not YouTube.** Today the
whole outbound surface is yt-dlp, YouTube's thumbnail host, and a PO token helper on
loopback. A GIF picker adds a third party that would see **what the owner searches
for**, which is a change in posture worth deciding rather than absorbing, and would
need a line in [SECURITY.md](SECURITY.md) if built.

**Most of the machinery already exists**, which is why this is a day and not a week.
The shelf, the thumbnail route with its on-disk cache, the placement rules and
`stickers.save_upload` from a data url are all built and all reusable. The genuinely
new parts are a search call, a second shelf fed by it, and a server side "fetch the
one I chose and store it".

**Two details that would bite if missed.** A raw GIF from either service routinely
exceeds `ANIMATED_MAX_BYTES`, 8 MB, and `ANIMATED_MAX_EDGE`, 720; both services
publish downsized variants, GIPHY's `fixed_width` and `downsized`, Tenor's `tinygif`,
and the picker has to ask for those rather than the original. And both carry content
nobody wants near a devotional Status, so the rating filter, GIPHY's `rating=g` and
Tenor's `contentfilter=high`, is not optional. [Unverified] those two parameter names
are from the published API documentation and were not exercised here, because that
needs a key.

### Table T29-1: the four ways

| Route | What it costs | What it buys | What it risks |
|---|---|---|---|
| **A: GIPHY, proxied through the server** | about a day, plus a two minute signup for a free key in `.env` | search and place without leaving the page, on the laptop and on the phone alike | a credential this tool has never needed, a third party that sees the search terms, and an attribution mark GIPHY's terms require on screen |
| B: Tenor, same shape | the same day, plus a **Google Cloud project** to get the key | possibly better coverage than GIPHY | the heavier signup, for a difference nobody here can measure without doing it |
| C: Wikimedia Commons, no key at all | half a day | no credential, no third party worth worrying about | **measured useless for this**: one GIF in five results, and encyclopaedic ones. It would answer the letter of the ask and not the point of it |
| D: leave it. Paste, and now Upload | nothing | nothing changes | the round trip out of the page stays |

**One thing that is not a route: fetching from the page instead of through the
server.** The phone reaches this page over the tailnet, so a picker that loaded
thumbnails straight from GIPHY would have **the phone** talking to GIPHY, not just
the laptop. Everything else on this page comes from one origin, `/api/sticker` and
`/api/clip` included, and the picker should too. That also makes the existing
thumbnail cache work for it for free.

**Recommendation: A, and build the provider so B is a setting rather than a rewrite.**
GIPHY's key is the lighter signup of the two and its downsized variants map cleanly
onto the ceilings already in `stickers.py`. Coverage for Tamil devotional and film
material is the one thing that cannot be judged from here, on either service, so the
honest design is one provider interface with GIPHY first and Tenor as a config
change, the same shape as the client ladder in `fetch.py`.

**The decision that is actually being made** is not GIPHY versus Tenor. It is whether
this tool starts telling a third party what the owner is searching for. That is a
reasonable trade for a picker that saves a round trip every time, and it is his to
make, not one to slide in under a feature.

### What was built, and what the research got wrong

The owner took it, and signed up for three services rather than one. Two of the
research's conclusions survived contact and one did not.

| The research said | What actually happened |
|---|---|
| Both majors need a key | held. GIPHY 401, Tenor 403 |
| Tenor is route B, a heavier signup | **wrong, and worse than wrong.** Tenor has closed onboarding outside Google's ecosystem. It is not a route at all |
| GIPHY first, Tenor as a config change | half held. The seam was built; the second provider is **KLIPY**, which the research had never heard of |
| Pixabay was not considered | it should have been, and it fails: a key exists, shown on its docs page once you log in, but the API has **no GIF search**. `image_type` is only `all`, `photo`, `illustration`, `vector` |

**KLIPY turned out to fit better than GIPHY**, which nothing in the research predicted:
its `xs` rendition is 90 pixels, almost exactly what the thumbnail cache already
uses, its `md` is 640 pixels at about 200 kB, and its only mandatory attribution is
the words in the search box rather than a mark on screen. Both are built; `.env`
chooses in one word.

### Table T29-2: measured, 2026-08-21

| Check | Result |
|---|---|
| GIPHY, live | 30 results, thumbnails 200 px, kept copies capped at 2 MB by GIPHY itself |
| KLIPY, live | 30 results, `md` 374x374 to 640x640, 52 kB to 4.6 MB |
| Preview thumbnails | **30 of 30 loaded** in a real browser, every one served by this machine |
| Picking one | downloaded, stored animated, placed on the frame, in the shelf |
| An id never offered | refused. The address is never taken from the browser |
| Switched off | `state.gifs` empty, both routes **404**, no toggle, no credit line, 48 drawings still on the shelf |

**One bug, found by counting rather than by reading.** The first pass rendered thirty
shelf cells and every image was a 403: `/api/gif` was not in the list of routes that
accept the token as a `t=` query parameter, and an `<img src>` cannot send a header.
It looked exactly like a provider fault. Caught by checking `naturalWidth` in a real
browser, and pinned by a test.

---

---

## T-045 (done) The clip says when it is older than the form

**Reported 2026-08-25**: "I have inserted a GIF, but that is not appearing anywhere
on the actual video. I have checked by both posting the video to my status and also
downloading it." Followed by the right guess: "or is it such that, after placing
emojis / GIFs, I have to recreate the video?"

### Not a bug, and the log says so exactly

| Time | Event |
|---|---|
| 19:43 | `..._video.mp4` rendered. Its sidecar records `"stickers": []` |
| **19:53:35** | **that clip posted** |
| 20:46 | Make the clip pressed again |
| 20:47 | `..._video-2.mp4` rendered, sidecar records the KLIPY GIF and the openmoji |

Frames pulled out of the 20:47 clip at 1s, 3s and 5s have both stickers in them, the
GIF animating across the three. The export was never in question. The clip that was
posted simply predated the GIF.

And the guess was right: stickers are burnt in at render, in **both** modes. Card mode
gets `decals=still, moving=moving` exactly as video mode does, so artwork is no
different and there is no path where a sticker rides along without a re-render.

### The gap that let it happen

The Stickers panel already says "Make the clip again to draw these into it." Post it
is a different card, holding the four buttons that act, and nothing there knew the
clip was older than the form. The notice moved to where the mistake is made.

| Piece | Where |
|---|---|
| What has changed since the clip was made | `drifted()` in `app.js`, against `current.job` |
| The standing notice | `#post-stale`, directly above the four buttons |
| One press explains, the second acts | `pastStale()`, on Load, Send and Download |

### Table T45-1: what counts as drift

| Counted | Not counted |
|---|---|
| the five words, the stickers, the waveform, the mode | the link, the window |
| everything drawn into the pixels | what chooses *which* clip you are making |

The second column is the important one. Pasting the next link while the finished clip
is still on show is the ordinary way to use this page. A warning that fires on
ordinary work is learned as noise and then not read on the day it matters.

### The panels moved in the same pass

Asked directly: Stickers to where Make the clip was, Make the clip into Post it. See
D-057. Two couplings crossed a boundary, neither of which raises anything when cut: a
submit button outside its form needs `form=` or it does nothing at all, and Stickers
had to go beside the form rather than inside it, because Enter in its search box would
otherwise start a render. Both are tested in `tests/test_page_wiring.py`.

### Found on the way

The Post it badge read "artwork card" on a clip that was plainly video. `naming`
writes the video marker before the collision suffix, so a second take ends in
`_video-2`, and both `endswith("_video")` and `removesuffix("_video")` miss it. Every
clip made after the first that day was mislabelled and showed no window. There were
already tests for a collision suffix and for video mode, and none for the two
together.

---

## T-044 (done) A cross on the tile, to throw a variant away

**Asked 2026-08-25**, over a screenshot with a box drawn on the corner of a Recent
tile: "please introduce a close button (cross-mark) here, so that I can delete those
variants that I don't want. Please design it nicely for both mobile and desktop
views."

**The server needed nothing.** `/api/clip/delete` has existed since T-016: it takes a
stem, deletes the whole file group rather than the mp4 alone, refuses with a 409 while
WhatsApp is being driven, and is covered by six tests. What was missing was a way to
reach it. The only route to Delete was to load a clip into the player first, which is
three presses and a repaint to throw away a take you can already see is wrong, and the
strip is exactly where takes are compared against each other.

So this task is entirely in `app.js`, `app.css` and one line of `index.html`.

### What was built

| Piece | Where |
|---|---|
| The cross, and the tile split into two buttons | `renderRecent` in `app.js` |
| Ask, then act, and forget the question after four seconds | `killClip`, `armKill`, `disarmKill` |
| Which tile is asking, held across a repaint | `killArmed`, a stem rather than an element |
| The disc, the ring, and the grown hit area | `.tile__kill` and `.tile__kill::before` in `app.css` |
| A place to say a delete was refused | `#recent-error`, under the strip |

### Table T44-1: the three traps, and what each one would have looked like

None of these announce themselves. Each is now a test in `tests/test_recent_strip.py`.

| Trap | What it would have looked like | Guard |
|---|---|---|
| A `<button>` inside a `<button>` | valid to write, silently unnested by the parser: the cross lays out beside the tile, and `closest(".tile")` from it finds nothing. Reads as a styling bug | `TestATileIsNotAButtonInsideAButton` |
| `color: #fff` on a `var(--danger)` fill | fine in the light palette, invisible in the dark one, because `--danger` is a dark red in one and a pale pink in the other | `TestTheArmedStateStaysReadableInBothPalettes` |
| A 22 pixel touch target | reachable with a mouse, missed with a thumb. Growing the disc instead of the hit area trades it for a cross that eats the thumbnail | `TestTheCrossCanBeHitByAFinger` |

### Measured, not assumed

Driven through the debug protocol against the running page rather than reasoned
about. The armed fill read as unchanged at first and the cause was the tab being
backgrounded, where transitions never advance: a measurement artifact, but it made
the point that a safety signal should not fade in at all, so the transition on the
fill was dropped.

| Checked | Result |
|---|---|
| The cross is the hit target at its centre, and 5 pixels outside the disc | yes, and the tile body still opens elsewhere |
| First press arms exactly one tile | yes, and it disarms itself after four seconds |
| Second press deletes | all five files of the group gone, tile removed, strip refilled from 12 to 12 |
| Deleting the clip on show | player cleared, "nothing yet" back |
| A refused delete | the message lands in `#recent-error`, not in the collapsed Post panel |
| The tick and the cross | 7 pixels from opposite edges, 60 pixels of clear air between them |
| Touch target on a coarse pointer | 24 pixel disc, 44 pixel target |

---

## T-043 (done) Anchor the top text to the picture

**Asked 2026-08-25**, an hour after T-042 shipped, over a screenshot of it working:
"should it start alignment from the bottom? Can we change it such that text above the
video frame always starts from the top of the frame? This way our probability of
collision with header elements will decrease."

**Measured on his own clip before answering.**

| | |
|---|---|
| Top text drawn at | 260 to 348 |
| Picture starts at | 626 |
| Void between them | **278 pixels** |
| Clearance from the header band at 230 | **30 pixels** |

Every other block above something in this layout is anchored by its bottom, so length
grows upwards into empty air rather than downwards into whatever it was meant to sit
above. The top text was the one that was not, and it was the one with a header full of
WhatsApp's own controls just above it.

### The obstacle, and why it was worth clearing

Nothing in Python knew where the picture was. It was decided at render time by
`min((H-h)/2, floor-h)` inside the filter graph, from a source shape only ffmpeg had
looked at. A coordinate the renderer keeps to itself cannot be drawn against.

So the arithmetic moved into `render.picture_rect`, which fits the source into the
band and returns an exact rectangle, and the graph is handed numbers. Better anyway:
an expression cannot be unit tested, only rendered and measured, and one fit now
answers two questions instead of one.

| Piece | Where |
|---|---|
| The rectangle, exact | `render.Picture` and `render.picture_rect` |
| The crop probe returning the size it found | `render.source_picture`, one scan for both answers |
| The block hung off it, clamped so it cannot leave the frame | `compose.topline_top` |
| Recorded for the preview, which cannot measure a still | `picture_top` in the clip's sidecar |

### Table T43-1: the rectangle Python computes, checked against the paint

Five aspect ratios rendered through the real graph and measured. This is the seam the
change creates, so it is the test that matters most in that file.

| Source | Rectangle | Painted |
|---|---|---|
| 2.35:1 | 1080x460 at (0, 730) | 730 to 1189 |
| 16:9 | 1080x608 at (0, 636) | 636 to 1243 |
| 4:3 | 1080x810 at (0, 434) | 434 to 1243 |
| 1:1 | 1014x1014 at (34, 230) | 230 to 1243 |
| 9:16 | 570x1014 at (256, 230) | 230 to 1243 |

On the owner's clip the block moves from 260..348 to **508..596**: 278 pixels of
clearance from the header instead of 30, and the words against the picture instead of
adrift above it.

**Known and deliberate.** A clip made before the picture position was recorded
previews with the old fixed placement, which is where that clip's own text actually
is. A square or portrait source begins at the ceiling, so there is nothing to hang
from and the block falls back to the top of the band.

---

## T-042 (done) Text at the top of the frame

**Asked 2026-08-25**, over a screenshot with a box drawn around the empty band
between WhatsApp's header and the top of the video: "how to insert text here?"

Nothing drew there. In video mode the frames are centred, so there is air above them
and air below them, and every word this tool draws lives at the bottom.

**Two answers were possible and the choice mattered.** A placement toggle on the
existing label is less interface: one box, one choice, no new field, but a clip can
then have a line at the top **or** above the words, never both. A separate field is
one more box and lets it have both, which is the shape of the reel this was asked
for: a hook at the top, the line that introduces the title at the bottom. The owner
chose the field.

### What was built

| Piece | Where |
|---|---|
| The field, wrapped to three lines at 32 pixels | `compose.topline_lines`, sharing `_tracked_lines` with the label |
| Drawn 30 pixels below `SAFE_TOP` | `compose.TOPLINE_TOP` |
| The frames' ceiling, as the label is their floor | `compose.video_picture_top`, into `render.picture_steps(ceiling=...)`. T-043 moved this into `render.picture_rect(ceiling=...)` |
| What is left above the label, in card mode | `compose.topline_room` |
| Through the page, the sidecar and the command line | `topline` on `Job` and `CardText`, `--top-line` |

### Table T42-1: measured on a real render, square source, 2026-08-25

| Top text | Picture starts | Ceiling |
|---|---|---|
| none | 230 | 230 |
| two lines | 388 | 388 |

**Known and deliberate.** Card mode's band up there is shared with the label above
the card, which is anchored to the card and cannot move, so the label is placed first
and the top text takes what is left. With an unusually square artwork the card is at
its tallest, its top is at 325, and what is left is nothing. Recorded in
[LIMITATIONS.md](LIMITATIONS.md) rather than solved: that is the case where there is
genuinely no room.

---

## T-041 (done) The label above the card works in video mode

**Asked 2026-08-25**, over a screenshot in video mode with a sentence typed into the
box and nothing on the preview: "won't these sections work for videos?", pointing at
Footer and at Label above the card.

**Measured before answering.** Rendered both modes with both fields set. The footer
draws in video mode and always has. The label draws in neither the preview nor the
clip: `build_overlay` passes `eyebrow_top=None` and `_draw_text_layer` skips the
eyebrow when that is None. So half the report was right, and the half that was right
was a field that took a sentence and threw it away with no error and no note.

**Why it was written that way.** The eyebrow's whole definition was "above the card",
its y came from the card's top, and video mode has no card. What was missed is that
video mode does have a words block, and above that block is the same idea.

### What changed

| Piece | Where |
|---|---|
| Drawn one `EYEBROW_GAP` above the title | `compose.VIDEO_EYEBROW_TOP`, and `build_overlay` passing it |
| The frames give up the room, and only when there is a label | `compose.video_picture_bottom`, which takes the text rather than being a constant |
| Carried into both ffmpeg graphs | `render.picture_steps(floor=...)`, from `render_video_clip` and `background_still`. T-043 moved this into `render.picture_rect(floor=...)`, and both graphs are handed the rectangle |
| The field says what it does in each mode | `EYEBROW_LABELS` in `app.js`, "above the card" and "above the words" |

Without a label the picture's floor stays at 1244 and nothing about an existing clip
changes. With one it rises to 1174. Paying 70 pixels of picture on every clip for a
line that is off by default would be the wrong trade almost every time.

### Reported again the same day: "still not able to see anything"

Drawing it was half the job. The first sentence typed into the box, 91 characters,
was drawn as **one unwrapped line 1989 pixels wide in a 1080 pixel frame**, centred,
so 454 pixels fell off each side and what remained was a fragment with no beginning
and no end. Measured off the clip he made, not reasoned about.

The eyebrow was the one line of this layout that had never been wrapped, because
`NOW PLAYING` never needed it.

| Piece | Where |
|---|---|
| Wrapped to three lines at most, at the frame's own margins | `compose.eyebrow_lines`, through the same `_wrap` the title uses |
| Wrapping that counts the letterspacing | `_wrap(measure=...)`, because `textlength` cannot see tracking and wrapping without it overflows by a third |
| Tracking dropped past 28 characters | `compose.eyebrow_tracking`. It makes a two word label deliberate and a sentence unreadable |
| Anchored by its bottom, so a second line grows upwards | `compose.eyebrow_top`. One line lands exactly where it always did, so nothing existing moves |
| Card mode ellipsises, video mode moves the frames | `compose.eyebrow_room` against `SAFE_TOP`, and `video_picture_bottom` against the block's height |

### Table T41-1: measured on a real render, 2026-08-25

| Label | Picture band | Label top | Floor |
|---|---|---|---|
| none | 636 to 1243 | none | 1244 |
| one line | 566 to 1173 | 1214 | 1174 |
| two lines | 526 to 1133 | 1174 | 1134 |

### And the second line and the footer were the same bug

Reported the same afternoon, over the preview: "text wrap is happening here, but not
here". Both were single unwrapped `draw.text` calls, and only the title had ever been
wrapped. Measured: an ordinary channel name, "Sounds of Isha Official Channel for
Devotional and Classical Music", is **1253 pixels** in a 1080 pixel frame; a footer of
similar length, 1209.

They wrap now, but not to a fixed allowance, because there is not one to give: a three
line title has already spent almost the whole block. Each takes what is left after the
one above it, up to two lines, ellipsised beyond that, and the footer keeps one line
back for itself while the channel is measured. The title is never shortened to make
room for either; trading a line of the song's name for a line of the channel's is the
wrong way round.

**Known and deliberate.** Typing a label after a clip exists moves the frames, and
the live word preview draws over the still that clip was rendered with, so the
preview shows the label over the picture until the clip is made again. That is the
same staleness the band above the preview already names.

---

## T-040 (done) The page opens where the rest of the session is

**Reported 2026-08-25:** "when I launch our project using the launch script, this
URL opens in a completely separate browser. Along with the initial informational tab
that we are opening, can we open this URL too on the same browser?"

**Correct, and it was the loose end in T-037.** That task gave the posting browser a
tab naming the session's port. The page that port serves still went through
`webbrowser.open`, which asks the desktop for its default browser: one window said
"this session is on 8765" while the thing on 8765 was in another window entirely.

The page is now Chrome's **second** URL, after the label and before WhatsApp Web.
The label stays first because the window title follows the active tab and naming the
port there is what T-037 was for; the page is one tab across.

### Table T40-1: where the page ends up

| Situation | Where it opens | How |
|---|---|---|
| A browser is started here | in it, second tab | on the command line |
| A browser is already running | in it, a new tab | `PUT /json/new` over the debug protocol |
| No browser could be started | the default browser | `webbrowser.open`, as before |
| The tab is refused | the default browser | same fallback |
| `--no-open` | nowhere | checked before any of the above |

`PUT` and not `GET`: Chrome 111 stopped answering `GET /json/new` to close a hole
where any page in that browser could have opened tabs in it. Verified against the
running browser on 2026-08-25, both the encoded and the plain query form.

---

## T-039 (done) The sticker panel, second review

**Two things, both from one screenshot, 2026-08-24.**

**"What happened to the icons / GIFs? They are a separate layer, right?"** They are
not, and that is the honest answer: still stickers are pasted into the card by
Pillow and animated ones are ffmpeg `overlay` inputs, so by the time a clip exists
they are its pixels, exactly like the words. What was wrong was not the render but
the way back. Making the clip hid the draggable layer, correctly, since handles
floating over pixels that cannot move are a lie; but nothing offered to bring it
back, and a person who had deselected everything could only get there by adding a
sticker they did not want.

There is now a **Place them again** button, shown only when there are stickers, they
are already in the clip on show, and nothing has been touched since. It sets its own
flag rather than the "this clip is behind" one, because nothing has changed yet and
saying otherwise would be the page inventing a change. The hint no longer goes
silent either: it says the stickers are drawn into the clip below now, the way the
words are.

**"Can we have these two as radio buttons here?"**, over a box drawn at the right
end of the Drawings / GIFs row. The GIPHY and KLIPY chips sat in a second row below
it wearing the same pill shape, the same size and the same green, which reads as
another choice of equal standing when choosing a service is a detail of having
chosen GIFs at all. They are radios on the right end of that row now, the selected
one in full strength text and the other muted.

**"Make this less obvious"**, of the credit. It cannot go away and that is worth
recording: both providers require a visible mark, and KLIPY additionally requires
the search box to read "Search KLIPY", which is where that placeholder comes from.
What it could stop doing was taking a fourth stacked line of grey text at the foot
of the panel. It now rides on the right end of the hint's own line at 10px and .55
opacity, without the footnote asterisk. That is the floor, not a preference.

---

## T-038 (done) Video frames stop being written on by the title

**Reported 2026-08-24:** "if a title is very long, in artwork mode, the artwork is
moved slightly up accordingly, so as to not allow it to come upon the artwork, which
is nice. But in video-frames mode the video is vertically centred, and if the title
is too long a part of it overlays the video."

**Right about the outcome, and the cause was not the stated one.** The title's top
never moves in either mode: it is `CARD_TITLE_TOP` at 1005 and `VIDEO_TITLE_TOP` at
1284. Card mode is safe because `card_box` anchors the card above that line whatever
the artwork's shape. Video mode centred the frames in the whole 1080x1920 canvas
with `overlay=(W-w)/2:(H-h)/2`, an expression that knows nothing about the words.

So the trigger is the **source's shape**, not the title's length. A long title just
puts more lines on top of a picture that was already being written on.

### Table T38-1: where a source's own picture ended, measured 2026-08-24

| Source, after letterbox trimming | Bottom edge before | After | Title starts 1284 |
|---|---|---|---|
| 2.35:1, the owner's last two posts | 1190 | 1190, unmoved | clear |
| 16:9 | 1264 | 1244 | clear |
| 4:3 | 1365 | 1244 | was 81 into the title |
| 1:1 | 1500 | 1244 | was 216 into the title |
| 9:16 | 1920 | 1244 | was the whole block |

**A floor, not a layout.** `min((H-h)/2, VIDEO_PICTURE_BOTTOM-h)` keeps the centred
position for everything that already cleared the words, so the back catalogue keeps
its shape. Giving video mode the card's structure instead, always sitting in the
band above the title, would have moved every existing 16:9 clip up by 300 pixels for
a problem it does not have.

**Too tall to fit is fitted, not cropped.** A square or portrait source is scaled
into the 1080x1014 band and shows blurred fill down its sides. Cropping it to the
band's shape, which is what the card does with an unusually square thumbnail, would
take the top off somebody's head: a margin is a worse picture, a crop is a wrong one.

`background_still` shares the same steps, so the still the live word preview draws
over cannot disagree with the clip it is previewing. Five source shapes are rendered
through the real graph in `tests/test_safe_zone.py` and the picture they paint is
measured. See D-049.

---

## T-037 (done) Say which port this session is on, where it can be read

**Asked 2026-08-24**, over two screenshots of another tool's label pages: "in
addition to opening a Chrome browser on a port, can we show a similar page which
will tell on what port we have opened up this project?"

**The information already existed and was in the wrong place.** `serve` prints its
port to the terminal it was started from, and ten minutes later that terminal is
behind three other windows on a machine running several Chromes on several debug
ports. Nothing on screen said which window belonged to this tool.

### What was built

| Piece | Where |
|---|---|
| The page itself, as text | `label.render`, separate from the writing so a test can read it without a disk |
| Written per page port, overwritten on restart | `label.write`, into `~/.cache/wastatus`, moved by `WASTATUS_CACHE_DIR` |
| Handed to Chrome as its **first** URL | `post.launch_browser(port, first=...)`, ahead of `https://web.whatsapp.com` |
| Filled in once the socket is bound | `App.page_port`, set in `serve.main`, because `--port 0` means the number is not known until then |

The `<title>` is the part that does the work: `● 8765 · wastatus` in the window title
and in the task bar, readable without opening anything. The body names the page URL,
the tailnet URL when there is one, the Chrome debug port, the posting profile and
the output folder.

**A file, not a route,** so it outlives the server. **First tab, not last,** because
the window title follows the active tab, and that costs nothing: `Page.__init__`
calls `Page.bringToFront` before it touches anything. **Never fatal:** a cache that
cannot be written logs a warning and the browser starts anyway.

**Known and deliberate.** A browser that was already running when the tool started
does not get one. Nothing was launched, so there was no command line to put it on,
and reaching into somebody's running browser to open a tab in it is a larger thing
than this is worth. See D-050.

---

## T-036 (done) The words, previewed as you type

**Asked 2026-08-22:** "if I make changes in this title / second line, etc, how to
refresh the preview alone without regenerating fully?"

**Measured before designing anything.** From the owner's own `runs.jsonl`, a 90
second video clip is probe 1.4s, download 12.3s, **render 52.5s**. So the obvious
idea, caching the download so a re-make skips it, would have saved under a fifth of
the wait. The render is the wall.

**And the render is not needed to see the words.** Both modes draw their text with
Pillow already. Card mode is `build_card`, 0.86s. Video mode is `build_overlay`,
0.10s, composited over a frame. Calling the same functions the render calls means
the preview cannot drift from the clip.

### What was built

| Piece | Where |
|---|---|
| One extra still per video clip, blurred fill and all, with no text on it | `render.background_still`, called from `render_video_clip` in a second ffmpeg run so it can never fail the clip |
| The artwork kept for card clips | `pipeline.produce`, copied out of the work directory before it is deleted |
| Both pruned with their clip | `retention.SIDECAR_SUFFIXES` |
| Draw these words on that picture | `App.preview_jpeg`, 720 pixels wide and JPEG: full size PNG measured 1254 kB and this measures 73 |
| `POST /api/preview` | a POST, because a title in an address ends up in every log between here and a phone |
| The picture over the video, under the stickers, with a band saying so | `#wordshot`, `#wordshot-note`, 400ms after typing stops |

### Table T36-1: measured in a real browser, 2026-08-22

| Case | Result |
|---|---|
| Card clip, new title typed | preview appears, 720x1280, band reads "Preview of the words. The clip still has the old ones." |
| Video clip, new title typed | the same, drawn over the clip's own frame |
| Words reverted to the clip's own | preview and band both disappear |
| Press play | still hides, video plays. Pause brings it back |
| A clip made before this existed | no preview, and the message says "Make it again and the preview will work" |
| Console errors across all of it | zero |
| Preview weight | 73 kB card, 70 kB video, against 1254 kB and 694 kB full size |

**Known and deliberate.** There is no preview before a clip exists: card mode would
need the artwork downloaded and video mode would need the video. And a card clip's
waveform is drawn by ffmpeg from the audio, so the band it lives in is empty in the
preview. This shows the words, not the finished frame.

**Changed 2026-08-26.** The "press play" row above no longer holds. Reported off
Screenshot_2026-08-26_10-47-29: playing showed the old title, stopping showed the
new one, and nothing on screen said why the words changed under you.

The still now **stays up and is cut open** over the part of the frame that moves,
so the clip plays inside its own new wording. The old words are under the still,
the new ones are on it, and the footage runs between them. The hole is safe because
the layout already keeps text off that band and the server measures it with the
same functions the render used: `App.moving_band`, sent as the `X-Moving-Band`
header on the preview it belongs to, applied as a CSS mask by `cutOpen`.

| Mode | The band that moves | Measured by |
|---|---|---|
| Card | the waveform, the only thing ffmpeg animates on a still card | `compose.WAVE_TOP`, `WAVE_H` |
| Video | where the frames were fitted | `picture_top` from the sidecar, `compose.video_picture_bottom` |

The video band is cut to the row the **words** begin at rather than the picture's
own bottom edge, which can only expose more blurred fill and never a letter. Its top
edge is the top of the frame unless a top line was typed, since the top line is the
only thing drawn above the frames and freezing that strip bought nothing. A clip old
enough to have no `picture_top` is measured with `compose.video_picture_top`
instead, which is the same function that placed its text.

**Checked before it was believed,** 2026-08-26, by compositing what the mask will
produce: `preview_jpeg` for new words, cut at the band, laid over a real frame
pulled out of `20260826_soak-in-the-powerful-presence-of-kailash_0-35_video-3.mp4`
four seconds in. The footage is there, the new title is on it, and no part of the
old title shows anywhere.

---

## T-035 (done) The words on the card stop following the last video

**Reported 2026-08-22:** "I input another new URL and click Make the clip. The new
video is getting created, but the title etc are left-overs from the previous video."

**Confirmed, and the cause was not the obvious one.** A guard existed. It compared
against `current.job.url`, the clip on screen, which is null after a page reload,
while `restore` had already put the previous words back from localStorage. So the
path that fails is exactly the ordinary one: use the tool, close the laptop, come
back, paste a new link.

Two further holes came out with it: it compared raw strings, so `youtu.be/X` after
`watch?v=X` cleared words that belonged to that very song, and it cleared the title
and the channel but not the footer or the eyebrow.

### What was built

`wordsFor` holds the video the words were derived for, is set wherever the boxes are
filled from a job, and is stored with the form so it survives a reload. Checked on
input and again at the press, and the press says what it did rather than emptying
four boxes in silence.

### Table T35-1: measured in the page on 2026-08-22

| Case | Result |
|---|---|
| Five spellings of one link, including `?t=`, `/shorts/` and `music.youtube.com` | all reduce to the same video id |
| Words for A, then a different link | title, channel, footer and eyebrow all cleared |
| Words for A, then the same song spelled differently | all four kept |
| Words for A, then the same song with a timestamp | all four kept |
| Words stored, page reloaded, different link pasted | `wordsFor` restored, then cleared. **The reported case** |
| A value set with no input event, caught at the press | cleared |

**The window is left alone on purpose.** See [DECISIONS.md](DECISIONS.md) D-046: the
owner posts the same window from many videos, so clearing it would cost more than it
saves. Say so if that is wrong and it is one line.

---

## T-034 (done) The desktop GIF panel, reviewed

**Goal:** the four things marked on the owner's screenshot of 2026-08-22, and a
provider chooser.

### Table T34-1: what was marked, and what was done

| Marked | Cause | Done |
|---|---|---|
| "Why is this text formatted like this?" over a sentence running one word per line | `.shelf` is a grid of 52 pixel columns and `.shelf__empty` was an ordinary grid item, so it was laid out inside one column. Wrong since the shelf became a grid | `grid-column: 1 / -1`. Measured after: 542 pixels wide instead of 52 |
| "The GIF previews in desktop views are too small. I'm unable to judge them" | one cell size for 4,495 drawings and for somebody's video | cells sized per source, 92 pixels on a phone and 132 on a wide screen, and a taller shelf. Measured 172x172 actual |
| "This entire section is not useful in desktop view, right?" | the paste box is a touch affordance: only a rich text target makes a phone keyboard offer its GIF tab, D-036 | hidden above 901 pixels, and the hint below it kept, because Ctrl-V anywhere on the page still works |
| "Too close by" | `#sticker-source` had a margin above and none below, so it sat on the search box | a margin below it |
| "We need to have the GIF provider chooser to be shown" | there was none: `.env` chose, and only at startup | GIPHY/KLIPY chips under the toggle, wide screens only |

### The thing that only showed up once it was built

Growing the cell made the pictures **worse**, because a 127 pixel thumbnail was
being upscaled into a 172 pixel box. Both providers were then measured for the first
time, [DECISIONS.md](DECISIONS.md) Table D47-1, and the browser now asks for a
preview that suits its own cells, `/api/gifs?big=1`. Measured after: 220 pixels wide
in a 172 pixel cell, so downscaled and sharp.

**Found by looking, not by reading.** In the headless browser every thumbnail
reported `naturalWidth` 0, which looked like the 403 bug of T-029 all over again. It
was not: `loading="lazy"` does not fire in that headless build, and forcing one image
to `eager` made the request and loaded it. Worth knowing before somebody spends an
hour on it again.

---

## T-032 (done) One command to get to work

**Goal:** `cd` to the folder, run one thing, and have the page, the tailnet address
and a WhatsApp browser all up.

**Why it was worth doing.** Three commands, of which two were the same every day and
one was forgotten most often. `--also-on tailscale` is not remembered across a
reboot, so the commonest support question in [RUNBOOK.md](RUNBOOK.md) was the phone
refusing to connect, and the answer was always the missing flag.

### What was built, 2026-08-22

| Change | Where |
|---|---|
| `./wastatus.sh` with no arguments opens the page | `cli.main`. There is no useful clip a bare command line could describe: making one needs a URL and two timestamps |
| `WASTATUS_ALSO_ON` supplies `--also-on` | `serve.build_parser`. A flag on the command line still wins |
| `WASTATUS_START_BROWSER` starts a Chrome with WhatsApp Web, unless one is running | `serve.ensure_browser`, on a thread, so the page answers while Chrome comes up |
| `WASTATUS_CDP_PORTS` sets which debug ports are looked on, as a list or a range | `post.candidate_ports`, read at call time, never frozen into a default argument |
| A browser already open on the posting profile is adopted | `post.running_profile_port`. Chrome hands a second launch on one profile to the first and exits, so launching anyway opens a window and exposes nothing |
| A startup stamp in the text log: python, yt-dlp, ffmpeg, Chrome, ports, git revision, and the **names** of the settings `.env` supplied | `runlog.stamp`. Names, never values |

### Table T32-1: measured on 2026-08-22, on the owner's machine

| Case | What happened |
|---|---|
| `WASTATUS_ALSO_ON=tailscale` and nothing else | bound `127.0.0.1:8799` and `100.x.y.z:8799`, and printed the `Also on` line |
| `WASTATUS_START_BROWSER=1`, ports `9230-9235`, a wastatus Chrome already running on 9222 | adopted it: `already open on debug port 9222, using that`. No second browser, no duplicate profile |
| The same, with a scratch profile nothing was using | `Started google-chrome on debug port 9230 with WhatsApp Web` |
| Bare `./wastatus.sh` with the real server already up | reached `serve` and failed on the busy port, which is the right failure |

**Off is still the default.** A fresh clone binds loopback only and starts nothing.
See [DECISIONS.md](DECISIONS.md) D-044, and D-028, which refused a thing that starts
with the operating system and still refuses it. Nothing here starts unless somebody
types the command.

---

## T-031 (done) Name the browser that is holding a debug port

**Goal:** when a debug port answers and is the wrong browser, say whose it is.

**What it cost to not do.** On 2026-08-20 the tool said `Chrome is on port 9225 but
no WhatsApp Web tab is open in it`, which was true and useless: 9225 belonged to an
IDE's own Chrome, and the owner's logged in WhatsApp was in a different browser
entirely. The message reads as "log in again". The answer was "wrong browser".

Underneath it was a second fault. Chrome had been started on 9225 while something
already held it, so Chrome printed `bind() failed: Address already in use (98)`,
carried on, bound **IPv6 only**, and printed `DevTools listening on ws://[::1]:9225`.
That line reads as success. `_cdp_get` asks `http://127.0.0.1:{port}` and reached the
other browser instead.

### Table T31-1: what the three silences say now

| Situation | Message |
|---|---|
| Nothing on the port | unchanged: `no Chrome answering on 127.0.0.1:N`, with how to start one |
| A browser bound `[::1]` only | `port N is only half open`, naming the browser that took IPv4 |
| A browser with somebody else's tabs | `no WhatsApp Web tab is open in it. That one is chrome, profile antigravity-chrome-profile-someone (pid 151793)` |

### What was built

`post.port_owner(port)` reads `/proc` for a process whose command line asked for that
debug port and names it by profile. `post.in_use(port)` probes both address families
before a browser is started on one. `post._silence(port, exc)` chooses between the
three sentences above.

**The bug inside the fix, worth keeping.** Chrome rewrites its own argv into a single
space separated string, so `/proc/PID/cmdline` does not hold the NUL separators every
other process puts there. The first version split on NUL, saw one enormous token, and
found nothing on a machine where two debug browsers were plainly running. Both shapes
are handled and both are tested,
`tests/test_post.py::TestNamingTheBrowserOnAPort`.

Verified on the owner's machine on 2026-08-22 against the live 9225, which named the
IDE's profile correctly. See [DECISIONS.md](DECISIONS.md) D-045.

---

## T-033 (open) Instagram as a second source

**Goal:** decide whether pasting an Instagram link should produce a Status, and if
so, for whose posts.

**Status:** researched 2026-08-22, not started. The research is in
[docs/instagram.md](docs/instagram.md); this is the decision it leads to.

**The one fact that shapes everything:** your own posts and other people's are not
the same problem and never will be. Meta's API is scoped to accounts that have
authorised your app, and there is no endpoint, at any price, that returns an
arbitrary public account's media. The only mechanism that takes a pasted link is
yt-dlp, and it needs a logged in session to work at all.

### Table T33-1: what each route can actually do

| Route | Your own posts | Other people's | What it costs |
|---|---|---|---|
| yt-dlp with a session cookie | yes | yes, whatever that account can see | the session cookie sits on this machine, and Instagram may act against the account |
| yt-dlp anonymous | **no** | **no** | measured dead on 2026-08-22: every URL returns `Instagram sent an empty media response`, including one that does not exist |
| Instagram API with Instagram Login | yes, after switching to a Creator account | **no** | a Meta app, an OAuth flow, and an account type change. Free and reversible |
| oEmbed, tokenless since June 2026 | metadata only | metadata only | nothing. Returns embed HTML, never a media file |
| Driving a logged in browser, as posting does | yes | yes | the most machinery, and the least unofficial |

### Table T33-2: what the owner has to answer before this can be planned

| Question | Why it changes the work |
|---|---|
| Your own posts, other people's, or both? | own only has an official route and needs no cookie. Other people's has exactly one mechanism |
| Willing to switch the account to **Creator**? | the only way to the official route. Free, instant, reversible, and changes nothing about ordinary use |
| Willing to keep an Instagram session cookie on this machine, and on which account? | the yt-dlp route needs one. A second account keeps the risk off the main one |
| Re-encode to 9:16 like a YouTube clip, or pass the original file through? | a reel is already 9:16 and already short, so the card, the waveform and the crop have nothing to do |
| Two or three real links of the kind you would post | nothing here can be measured without them, and measurement is what settled every other source |

**Not a small feature dressed as one.** The YouTube path is "a link and two
timestamps become a card". An Instagram path is "fetch a finished video and re-post
it", which shares the posting half of this tool and none of the making half.

---

## T-027 (done) A YouTube Music link works, a playlist link lies

**Priority:** P2
**Status:** **done, 2026-08-21, route A.** Raised and closed the same day, from
groundwork the owner asked for

**YouTube Music needs no work at all.** There is no URL validation anywhere in this
tool: the link goes straight to yt-dlp, and `music.youtube.com` is the same extractor
as `youtube.com`. Measured on 2026-08-21, all three forms probe correctly, including
the `&si=` share tail and a `&list=` radio tail.

It is in fact the **better** link to paste. A `- Topic` upload gives
`channel="Release - Topic"`, which says nothing, and `artist="Project Samskriti"`,
which is the name the card wants. `fetch._artist` already prefers the artist, so a
YouTube Music link and a YouTube link for the same track produce the same card.

**The defect is next door.** A playlist link is accepted and produces nonsense:

| Pasted | What `probe` returns |
|---|---|
| `youtube.com/playlist?list=PLbpi...` | `video_id` is the **playlist** id, `title` is the playlist's name, `duration` is **0.0**, and `watch_url` is `https://youtu.be/PLbpi...`, **which is a dead link** |

That `watch_url` is the caption, and the caption is what goes out on the Status. So a
pasted playlist produces a Status whose link goes nowhere. Measured, not inferred.

### Table T27-1: what to do about the playlist case

| Route | What it costs | What it buys | What it risks |
|---|---|---|---|
| **A: refuse it, and say which link to paste instead** | about fifteen minutes. `probe` already has the answer: yt-dlp reports `_type: "playlist"`, and a `duration` of zero is a second signal | the failure lands at the moment of pasting, in one sentence, instead of as a dead link on somebody's Status | nothing. It cannot refuse anything that works today, because nothing that works today looks like this | 
| B: take the playlist's first track | about an hour | a paste that would have failed does something | guessing which track somebody meant is exactly the kind of guess this repository does not make elsewhere |
| C: leave it | nothing | nothing | the failure is silent and lands in public |

**Recommendation: A.** It is the smallest change in the file and it is the only one
that closes a defect rather than decorating it. B is a guess wearing a feature's
clothes.

### What was built

`fetch._refuse_a_playlist`, called from `probe` before a `Source` is built. It reads
`_type == "playlist"`, and `entries` on its own as well, because some extractors
return the entries without labelling the type.

**Measured against the live playlist that found the bug, 2026-08-21:**

```
that link is a playlist, 'Top Trending Videos of the Week', not one track.
It holds 19 tracks. Open the song you want and paste its own link: on YouTube
Music, use Share on the track rather than on the playlist.
```

Driven through `/api/render` on a scratch port, that is the message the page shows,
word for word: `task.error` is `str(exc)`, so nothing prefixes it with a class name.
No clip was written.

**Nothing that worked before was narrowed.** `--no-playlist` was already reducing
`watch?v=X&list=Y` to the single video, so a track with a radio or album tail is
untouched, verified live, and so is a plain YouTube Music link.

---

## T-028 (closed) Spotify links: researched, and not wanted

**Priority:** P3
**Status:** **closed 2026-08-21 by the owner**, on the research below: "No need for
spotify. I don't use it that much as such." Kept rather than deleted, because the
measurements are the answer to the next person who asks

**Spotify audio cannot be fetched, and that is not a limitation of this tool.**
yt-dlp refuses on sight:

```
ERROR: [DRM] The requested site is known to use DRM protection. It will NOT be supported.
```

There is no version of this that downloads from Spotify. So the only shape the
feature can have is: **read what the link is about, then find that recording on
YouTube.** That makes it a matching problem, and matching is where it was measured.

### What a Spotify link will tell you, without credentials

`https://open.spotify.com/oembed?url=...` answers with no authentication, and carries
**the title and a thumbnail. No artist. No duration.** Measured 2026-08-21.

Artist and duration need the Spotify Web API, which needs a client id and secret. They
are free and need no user login, but they are credentials, so they would arrive
through `WASTATUS_*` and `.env` with no value in `.env.example`, per D-039.

### The measurement that decides this

Searching YouTube for a track from the owner's own library, and asking whether the
first hit is the right recording:

| Query | First hit | Right? |
|---|---|---|
| `Project Samskriti Veyuru Tholipangan` (artist and title, the best case) | `Kolaru Pathigam`, same artist, **1 second from the right duration** | **No.** The correct track was second |
| `Veyuru Tholipangan` (title only, which is all oEmbed gives) | a different recording by a different artist | **No.** None of the top three was right |

**A duration filter does not save it.** The wrong first hit was one second from the
right length. Tamil devotional and film music is full of the same composition
recorded by different artists at similar lengths, which is exactly the case where
title matching is weakest and exactly the library this tool is for.

### Table T28-1: the three shapes this could take

| Route | What it costs | What it buys | What it risks |
|---|---|---|---|
| **A: paste a Spotify link, get a shortlist to choose from** | a day. Spotify API credentials, a search, and a chooser in the page showing title, channel, duration and thumbnail for three to five candidates | the link becomes usable without the tool ever guessing. The owner picks, which is the only party who can tell two recordings apart | a new card in the page, a new credential in `.env`, and a step that a YouTube link does not need |
| B: resolve it silently to the first hit | half a day | a Spotify link behaves like a YouTube one | **it posts the wrong recording**, measured, on the first track tried. Not acceptable for this library |
| C: refuse it with a useful sentence, "Spotify audio is DRM protected. Search this song on YouTube Music and paste that link" | twenty minutes | the paste fails immediately and says what to do, instead of showing a yt-dlp DRM stack trace | it is not the feature; it is an honest no |

**The owner's answer: none of them.** He does not use Spotify enough to be worth
twenty minutes, let alone a day. So a pasted Spotify link keeps showing yt-dlp's DRM
error, which is ugly but accurate and rare. **If that changes, route C is the twenty
minute version and nothing here needs re-deciding.**

**Recommendation at the time was C now, A only if pasting Spotify links is something
you actually do often.** Route C is twenty minutes and turns a confusing failure into an instruction.
Route A is a real day's work and adds a credential and a chooser to a page that has
neither, to save the step of searching YouTube Music yourself, which is the same step
route A's chooser would make you do anyway, only inside the tool. B is off the table:
it was measured wrong on the first attempt.

---

## T-026 (done) Notice when WhatsApp renames a control, before a post does

**Priority:** P3
**Status:** **done, 2026-08-21, route B.** Raised the evening before, out of the
evening WhatsApp renamed two of them

**The problem.** On 2026-08-20 WhatsApp Web renamed `Photo and video` to
`Photos & videos` and put both Status choices behind an **Add Status** button. The
tool found out when a post was pressed, which is the worst moment: the clip was
rendered, the caption was written, and the answer was an error naming a label that no
longer exists. [DECISIONS.md](DECISIONS.md) D-041 made the matching survive that
particular rename. It cannot survive every one.

**What already exists.** `has_control` answers "is this on the page" without clicking
anything, and the health panel already polls `/api/state` every fifteen seconds.

### Table T26-1: the three ways to close it

| Route | What it costs | What it buys | What it risks |
|---|---|---|---|
| **A: fold it into the WhatsApp Web check** | about two hours. The existing check already opens a page; it would also open the Status menu and confirm both choices are there | the chip goes amber before a clip is made, not after | it drives the real WhatsApp Web tab on a timer, opening and closing a menu under the owner's hands every fifteen seconds. That is worse than the problem |
| **B: check once, when a clip is selected** | about an hour | one probe, at a moment the owner is already waiting, and well before Send | still opens a menu in a window the owner may be looking at |
| **C: leave it, and keep the error good** | nothing | the failure already names the file and the list to widen, and RUNBOOK prints what the labels are today | the owner finds out at the moment of posting, as he did |

**Recommendation was C for now, B if it happens twice.** The owner asked for it to be
taken up on 2026-08-21, so **B was built**, which was the recommendation's own next
step rather than a departure from it.

### What was built

`post.check_controls` opens the Add Status menu, looks for both choices, and closes
it with Escape. `/api/controls` runs it and the answer is cached for the life of the
server process. The page asks once, when a clip first lands in **Post it**.

| Guard | Why |
|---|---|
| **Never on the poll** | route A's flaw. Fifteen seconds would mean opening and closing a menu under the owner's hands four times a minute |
| **Never while a composer is open** | that composer is holding a clip somebody is about to send. A check that breaks the thing it checks is worse than no check |
| **Never while a post or prepare is running** | one hand on that browser at a time, the same rule D-025 already enforces. That answer is not cached either, so it is asked again later |
| **A failed probe is not a fault** | no browser, or not logged in, is the WhatsApp Web check's business and it says so already |

**Measured, 2026-08-21.** Against the live tab: **2.2 seconds**, correct answer, menu
closed afterwards. With `PHOTO_ITEM` pointed at a label that does not exist, it
reported `Its Status menu offers: Photos & videos, Text` and named the file to widen,
and still closed the menu. On the page: asked once, green row when healthy; when
faulty the row goes amber, carries the message, and the chip reads
**WhatsApp Web needs you**.

**Not built: a fifth health row.** It rides on the WhatsApp Web row because it is the
same question, can this thing post, and a row that is silent 364 days a year is a row
nobody reads on the day it speaks.

---

## T-023 (done) Handles on the sticker itself

**Priority:** P2
**Status:** **done, 2026-08-21.** Parked by the owner on 2026-08-20 and picked up the
next day. The design was agreed in advance as [DECISIONS.md](DECISIONS.md) D-038, so
this was an implementation job with nothing left to decide, which is what parking it
that way was for

**What was agreed:** a delete cross at the top right in both views; a resize grip at
the bottom right and a rotate handle above the box on a stem, on desktop only; the
Size and Turn sliders kept on desktop and dropped on the phone.

**What makes it half a day rather than an afternoon:** it amends D-034 from the same
day. The dashed box currently fades 1.4 seconds after your hand leaves it, and a
handle that fades is a handle you cannot click. So the timer has to be replaced by a
real selection: tap a sticker and it stays selected with its handles, tap the frame
background and everything goes. That touches the gesture code, the selection model
and D-034 together, and every gesture measured on 2026-08-19 has to be re-verified
afterwards.

**The measurement that decided the phone half**, and the reason the phone gets one
handle rather than three: a default sticker is 60 pixels drawn and 76 to hit at 412
pixels wide. Two 44 pixel touch targets need 88 pixels between them, so two touch
handles cannot both fit on it.

**Acceptance:** handles as in D-038; selection persists and idle clears it; the fade
timer is gone; pinch, twist, drag and the sliders all still measure what they
measured on 2026-08-19.

### Table T23-1: measured against acceptance, 2026-08-21

Driven with real pointer and touch input over CDP, not by calling the functions.

| Acceptance | Measured |
|---|---|
| Handles as in D-038 | with a mouse: cross at the box's top right, grip at the bottom right, stem 22 pixels above the top centre. With touch emulated: **cross only**, 24 pixels drawn and **44 to hit**, resize and rotate `display: none` |
| Resize grip | 0.200 to 0.428 on a 34 pixel diagonal drag, and the sticker's centre did not move |
| Rotate stem | 0 to 90 degrees on a quarter swing, landing exactly on square through the same `settle` the twist uses |
| Selection persists | still marked after **2 seconds** idle, where the old timer cleared at 1.4 |
| Idle clears it | tapping the frame background: `picked` back to -1, box unmarked, slider bar hidden. Clicking the sticker selects it again |
| The fade timer is gone | `MARK_IDLE`, `markPicked`, `unmarkPicked`, `repaintMark` and `marking` all removed |
| Drag still measures | body drag moved x and y and left size and rotation untouched |
| Pinch and twist still measure | 0.200 to 0.344 and 0 to 40 degrees under two emulated fingers |
| The sliders still measure | 35 and -25 straight through to the decal |
| Nothing else regressed | the amber covered warning still lights and still says so in the hint |

**One thing the design did not settle, decided here:** desktop is a pointer test,
`(hover: none) and (pointer: coarse)`, and the test is positive so that a browser
reporting neither keeps the full set. Recorded in D-038.

---

## T-004 (done) Add a smoke test

**Goal:** catch regressions without a human looking at frames.

**Constraints:** must not require network access to pass in a form that is useful
offline, so split it: a pure unit layer over `timecode` and `translit`, and one
opt in end to end run behind an environment flag.

**Acceptance:**
- `timecode` cases: `93`, `1:33`, `1:02:03`, `90.5`, a `?t=90s` URL, and three
  malformed inputs raising `TimecodeError`
- `translit` cases: the three Tamil titles in
  [DECISIONS.md](DECISIONS.md) D-006 producing their recorded output, plus a
  Latin title passing through unchanged
- one end to end run asserting exit code 0, the three output files exist, the mp4
  duration is within 0.2s of requested, and the caption is pure ASCII
- documented in [TESTING.md](TESTING.md)

---

## T-005 (done) Record which ladder entry succeeded

**Goal:** see the download path degrading before it fails completely.

**Shape:** print the winning `(client, format)` on the `[2/4]` line, and append a
line to a local log. No telemetry leaves the machine.

**Acceptance:** the successful strategy is visible in normal output, and
[docs/extraction.md](docs/extraction.md) says where the log lives.

---

## T-006 (done) Warn when artwork falls back to a low resolution thumbnail

**Goal:** stop soft cards shipping unnoticed.

**Detail:** `fetch.download_thumbnail` walks `maxresdefault`, `sddefault`,
`hqdefault`. The last is 480x360 and visibly soft scaled to a 880 wide card.

**Acceptance:** a one line warning naming the size that was used, and a suggestion
to try `--video`.

---

## T-007 (done) Add a `--frame` flag

**Goal:** remove the manual ffprobe step from every visual change.

**Shape:** write a still from the midpoint of the clip next to the mp4.

**Acceptance:** the flag exists, [PLAYBOOK.md](PLAYBOOK.md) uses it in place of the
current two line ffmpeg incantation.

---

## T-008 (done) Handle an empty title after noise stripping

**Goal:** avoid a blank line on the card.
**Status:** **done 2026-08-20**

**Detail:** an aggressive `_NOISE` match on a short title leaves nothing.
`(Official Video)`, `#shorts` and `[HD]` are each noise by every rule in
`translit._NOISE` and the title by the only rule that matters.

**Acceptance: met**, in the two places the two fallbacks belong.
`translit.clean_title` keeps the **raw title** when stripping empties it, because a
silly line on the card beats a blank one. `pipeline.title_and_channel` falls back to
the **channel** when even that romanises to nothing, which an emoji only title
does.

---

## T-009 (done) Prove where the segment dedupe threshold breaks

**Goal:** replace confidence with a test.
**Status:** **done 2026-08-20**, and the answer is more interesting than a number

**Detail:** `_dedupe_segments` treats two title segments as duplicates above a
`SequenceMatcher` ratio on their skeletons. The task said 0.8; the constant is
**0.85**, `translit._SAME_NAME`. It was chosen because it worked on the titles to
hand.

**What twelve real Tamil devotional title pairs showed.** The threshold is not
merely untested, it is **untunable**:

| Pair | Ratio | What it is |
|---|---|---|
| `Abirami Andhadhi` / `Abhirami Anthathi` | **0.846** | one name, two spellings. **Not** collapsed |
| `Sivapuranam` / `Sivapuram` | **0.900** | two different words. **Collapsed** |

A real duplicate scoring **below** a real non duplicate means no single threshold
gets both right. Lowering it to catch the first keeps collapsing the second; raising
it to protect the second loses more real duplicates. So 0.85 stays, and it keeps the
safer of the two failures: a title that carries both spellings is untidy, a title
that loses a word is wrong.

**Acceptance: met.** `TestTheDuplicateThreshold` pins twelve pairs with their
measured ratios, the threshold itself, and the overlap, so any future change is a
visible decision. The ratio assertions also catch a change to `_skeleton`, which is
the other way this quietly drifts.

---

## T-013 (done) Exercise the card across the owner's real library

**Goal:** find what the new card geometry does to artwork shapes and titles that
have not been through it yet.

**Why it needs the owner:** the layout is now driven by each thumbnail's own aspect
ratio, and every shape has only been tested synthetically or against one song. A
square devotional thumbnail, a portrait one, a title that is entirely Tamil, and a
channel name longer than the title are all real cases with no real evidence.

**Steps:** the owner names three or four songs he would actually post. Each is
rendered with `--frame`, without posting, and every frame is checked by eye.

**Done, 2026-08-18.** Four songs the owner named were rendered and inspected. Four
findings, three of them defects in this tool:

| Finding | Outcome |
|---|---|
| A 60 second clip was 21 MB, which WhatsApp refuses silently | the encoder now derives its bitrate from the duration, [DECISIONS.md](DECISIONS.md) D-017 |
| An auto-generated upload's channel read `Release` | the artist field is preferred, D-018 |
| A title carried the same name in two romanisations | phonetic skeleton dedupe, D-018 |
| A title carried academic capitals, `viRalmAranaindhu` | normalised per letter run, D-018 |

The card geometry itself needed no change: a square album cover, a 16:9 still and a
cinemascope frame all composed correctly.

---

## T-022 (P2) Make this repository fit to be public

**Priority:** P2
**Status:** **done 2026-08-20.** The repository is fit to be public. Making it public
is one switch on GitHub and it is the owner's to flip

**The good news, from an audit on 2026-08-20: there is nothing secret in here.** The
page's token is generated per process by `secrets` and dies with the server, there is
no API key anywhere, and `WASTATUS_PROXY` is already an environment variable that
[SECURITY.md](SECURITY.md) marks as never to be committed. So there is no secret to
move out of the code. What there is instead is **the owner's own details**, and a
handful of things a public repository needs and this one did not have.

### Table T22-1: What was in here that should not be published

| What | Where it was | Now |
|---|---|---|
| the owner's tailnet address | CHANGELOG, DECISIONS, LOCAL_SETUP, MEMORY, TESTING | `100.x.y.z` |
| his laptop and his phone on his home network | MEMORY, PLAYBOOK, TASKS | `192.168.1.10` and `192.168.1.11` |
| his home directory in worked examples | CHANGELOG, LOCAL_SETUP, README | `~` |
| his machine's name | CHANGELOG | `this-laptop` |
| [MEMORY.md](MEMORY.md) as a whole | which songs he posts, when his phone is on, how his network behaves, what he tried and abandoned | **undecided**, see below |

None of those was a credential. All of them are him. **27 replacements across eight
documents**, and none of the reasoning depended on the actual numbers.

### Done on 2026-08-20

| Step | What landed |
|---|---|
| **`.env` support** | `wastatus/env.py`, read in `__main__.py` before anything else, environment always winning. `.env` ignored, `.env.example` committed and naming every setting the tool reads, with a test that keeps the two equal. [DECISIONS.md](DECISIONS.md) D-039 |
| **Placeholders for the personal values** | Table T22-1 above |
| **A LICENSE** | MIT, at [LICENSE](LICENSE). **The copyright name is a guess and needs the owner's word**, see the decisions below |
| **The font licence that was already owed** | `assets/fonts/LICENSE.md`. The two committed DejaVu files are byte for byte identical to Debian's `fonts-dejavu-core`, so its Bitstream Vera licence is reproduced with the MD5s that prove it. The README now credits all three: MIT, OpenMoji CC BY-SA 4.0, and this |
| **SECURITY.md read with a stranger's eyes** | a three sentence opening naming the only three things that can actually hurt someone, the `.env` rule written down, two settings that were never in Table SE-1 added, the sticker ceiling corrected for animated uploads, the 12 MB body cap documented, and Reporting rewritten for someone who is not the owner |

### Table T22-2: The four decisions, answered by the owner on 2026-08-20

| # | Decision | Answer |
|---|---|---|
| 1 | The name on the LICENSE | **PalWorks**, the name the GitHub account already carries |
| 2 | What happens to [MEMORY.md](MEMORY.md) | **split, and the public half published.** The personal rows are in `MEMORY.private.md`, ignored by git and in AGENTS.md's never-commit list |
| 3 | The history | **rewritten** with `git filter-repo`, the same replacements as the working tree, in commit contents and messages alike |
| 4 | Whether to publish `wastatus/post.py` | **published** |

All four are recorded as [DECISIONS.md](DECISIONS.md) D-040.

### Re-checked 2026-08-27, and one thing had drifted back in

Asked for as "ensure that our repo is fit to become open-source (i.e, none of our PII
is present in code, and is maintained separately). I think we laid the ground-work
for this sometime back, just ensure that we are still on-track for the same."

Swept the working tree for the owner's email and its local part, their machine name,
their real tailnet address, their home directory and any phone number. **One hit**: a
Chrome profile name carrying the local part of their Google account, quoted from live
output into CHANGELOG, DECISIONS, MEMORY and TASKS on 2026-08-21, after the audit
above. It is `antigravity-chrome-profile-someone` in all four now.

Everything else held: no key or token anywhere in the tree, `.env` and
`MEMORY.private.md` still ignored and never committed, `/home/someone` and
`100.64.0.x` still the only addresses and paths in the tests, and the LICENSE and font
licences still in place.

**The history still carries that one string**, in commit `4429818`. Nothing else does:
`git log -S` finds zero commits for the tailnet address, the machine name, the home
directory and the email. So publishing from this history publishes that one profile
name. Either accept it, or run `git filter-repo` once more with the same replacement
that was made on 2026-08-20, before the switch is flipped. The owner's call.

### What was deliberately left alone

**Device models.** A Galaxy M30 and a OnePlus 11 are named in the documents, because a
phone model identifies nobody and a measurement reads better with the real hardware in
it. Their **addresses** are what was replaced.

**The test fixtures.** `Prince Rama Varma-VARA LEELA GANA LOLA` still appears in five
test files and one comment, because the hyphen breaking rule and the padding bar
arithmetic were measured against that exact string and that exact thumbnail. A fixture
renamed to something that was never measured proves nothing. The prose no longer names
it; the evidence still does. Ten minutes to change if that ever stops being acceptable.

**Acceptance: met.** No personal address, hostname or home directory in the working
tree or in the history; a LICENSE; the font licence; `.env` supported and ignored; and
a recorded decision on the history, on MEMORY.md and on `post.py`.

---

## T-024 (P2) A way to reach a GIF from Chrome

**Priority:** P2
**Status:** **parked 2026-08-20. The owner chose route A**, which is to use Firefox
for the GIF step and costs nothing to run. Route B is worth one measurement the next
time a phone is on the cable, and route C is not to be built unless that measurement
fails and Chrome still matters

**The problem, measured rather than suspected.** Chrome on Android refuses keyboard
image insertion outright, on a Galaxy M30 with Samsung Keypad and on a OnePlus 11 with
Gboard, in both cases with the toast "Can't enter this content here". Firefox accepts
it on both. So today the GIF step needs Firefox, and nothing about the page can change
that: the refusal happens in the browser before the page is told anything.

### Table T24-1: the routes out, and what each costs

| Route | What it costs | What it buys |
|---|---|---|
| **A: use Firefox for the GIF step** | nothing at all | it works today, measured on two phones. The rest of the tool stays wherever the owner likes it |
| **B: save the GIF, then use the sticker file picker** | nothing to build, more taps, and the keyboard's own picker is no longer what you browse | Chrome's own long press menu on a picture offers to save it, and the sticker file picker already accepts a GIF and already animates it. [Unverified] on a phone: whether Chrome saves a GIF as a real `.gif` rather than a still frame has not been checked |
| **C: paste a link and let the server fetch it** | an outbound fetch, an allowlist of hosts, a size cap, a timeout, and tests. It is also the first time this tool would fetch a thing the owner did not name | one paste, in any browser. The page already recognises a pasted link and says it is not a picture, so the place to hook it exists |

**Chosen on 2026-08-20: A.** It costs nothing and is proven on both phones, so the
GIF step is a Firefox step and the rest of the tool stays wherever it is opened.

**The one thing still worth doing** is a single measurement of B: does Chrome's own
save-a-picture menu produce a real animated `.gif`, or a flattened still frame? If it
produces a real one, Chrome has a working route with no code written at all, and this
task closes for good. That needs a phone on the cable and about five minutes. **C is
not to be built** unless B fails and the owner still wants the whole flow in Chrome.

**Not a route:** making the sticker search field accept pictures as well. It would
change where you tap, not whether Chrome accepts, and Chrome is the whole problem.

---

## T-019 (done) Animated stickers, and how one arrives

**Priority:** P2
**Status:** **done 2026-08-20 for the route the owner chose.** An animated sticker
loops for the whole clip, and it arrives by pasting a picture at the page, which is
how a GIF from the phone keyboard's own GIF tab gets in. See
[DECISIONS.md](DECISIONS.md) D-036

**What the owner decided on 2026-08-20**, which cut two of the three phases:

| Phase as planned | Decision |
|---|---|
| 1: upload your own animated files | **not wanted.** The render half of it was built anyway, because without it a pasted GIF would arrive as a still, and the file picker was left accepting still images only |
| 2: a Gboard style picker | **this one**, by the clipboard route rather than by an API key. No Tenor account, no attribution terms, no network call while composing |
| 3: an animated library | **not wanted** |

**Settled on 2026-08-20**, by driving the owner's Galaxy M30 over USB:

| Browser on Android | Picking a GIF from the keyboard |
|---|---|
| Chrome 151 | **refused**, with a toast: "Can't enter this content here." Nothing reaches the page or the clipboard |
| Firefox 150 | **works.** The picture arrives as a `data:image/gif` `<img>` inserted into the box. The paste event carries `text/plain` only, `files=[]` |

The whole path was then run on the real page in Firefox: the GIF became a sticker,
appeared first on the shelf with its "moves" marker, and sat animating on a real
clip's frame. The keyboard was Samsung Keypad, whose GIF panel is GIPHY.

**Closed on 2026-08-20 by the owner's OnePlus 11**, which has Gboard. Chrome gave
nothing, from the sticker card's ordinary field and from the box alike. Firefox worked,
from the box. Two phones, two keyboards, the same answer: the keyboard is not what
decides, the browser is. `/paste-test.html` had done its job and was deleted.

What is left is not part of this task but a consequence of it: Chrome is the browser
most people reach for, so **T-024** holds what could be done about that.

Today a sticker is one static PNG pasted by Pillow onto a canvas. An animated one is
a second **video** input with its own loop and timing in the ffmpeg filter graph,
which is a different mechanism rather than a bigger version of the same one.

### What was measured on 2026-08-20, before planning

| Question | Answer |
|---|---|
| Can this machine's ffmpeg loop an animated GIF over a clip, with transparency, scaled and rotated? | **Yes.** ffmpeg 8.0.1, `-stream_loop -1` plus `fps,scale,format=rgba,rotate=a:c=none` into `overlay=shortest=1`. A 12 frame 0.96s GIF rode a 5s clip and kept looping, the background stayed untouched where the GIF was transparent, and the animation was confirmed by counting lit pixels across frames: 3196 rising to 10931 and back |
| Can it read an **animated WebP**? | **No.** `image data not found`, width 0, for both lossy and lossless. A **still** WebP reads fine. This matters because GIPHY and Tenor serve stickers as animated WebP as often as GIF |
| Can Pillow read an animated WebP? | **Yes**, 12 frames, RGBA. So the normaliser we would need already ships in this project's dependencies |
| Does the clip have motion today? | Yes: card mode is `-loop 1` plus a `zoompan` slow zoom plus a reacting waveform. An animated sticker is not introducing motion into a still, so the file size cost should be modest. Measure it rather than assume |

### The one design question the measurement exposed

**In card mode, stickers currently ride the slow zoom**, because they are pasted onto
the card canvas by Pillow before `zoompan` touches it. An animated sticker becomes an
ffmpeg overlay instead, and an overlay does not zoom. Static and animated stickers
would therefore behave differently in the same frame. In video mode there is no
problem: stickers go on the transparent overlay, which is composited at `0:0` with no
zoom, so an animated one matches exactly.

| Option | Trade |
|---|---|
| Give the animated overlay the same zoom ramp, as an expression on `x`, `y` and `scale` | exact, and the expression is already written once in `render_card_clip`. Fiddly to get right, and it has to stay in step if the zoom ever changes |
| Accept that animated stickers do not zoom | free, and probably invisible on a 4 percent zoom over 15 seconds. Dishonest in the strict sense: the preview cannot show the difference either way |
| Composite every frame in Pillow | perfectly consistent, and hopeless: 375 PNGs at 1620 pixels for a 15 second clip |

Recommended: the first, with the second as the fallback if it fights back.

### What was built, 2026-08-20

- `stickers.motion` and `stickers.split`: one rule, in one place, for which
  mechanism draws a sticker
- The renderer takes the moving half as `-stream_loop -1` inputs, scaled, rotated
  and overlaid at the same fractional coordinates the paste uses. In card mode the
  overlay goes on **before** `zoompan`, so animated and pasted stickers travel
  together. Verified to the pixel against a Pillow paste of the same rotated shape
- Anything animated is stored as GIF, because this ffmpeg refuses an animated WebP.
  Pillow does the converting
- A `paste` listener on the page, which only intercepts a paste that carries a
  picture. Text pasted into the caption box is still text
- The shelf marks the ones that move, because their thumbnails are stills
- A body ceiling on the server, since the largest legitimate request is now four
  times what it was

### The picker, if the clipboard turns out to be too narrow a door

The owner's reference is Gboard's emoji and GIF tab. [Unverified] Gboard's GIF tab is
Tenor, which Google owns. Three routes, and they are not exclusive:

| Route | What it takes | What it gives |
|---|---|---|
| **Receive from Gboard through the clipboard** | a `paste` listener on the page reading `event.clipboardData.files`. Perhaps twenty lines | the owner picks a GIF in his own Gboard, in any app, and pastes it into our page. No key, no terms, no catalogue of ours to curate. Whether Gboard hands a browser a file rather than a text link is the thing to test first |
| **Tenor API v2 in our own picker** | a Google Cloud API key, attribution, a network call while composing, and a key to keep out of the repository per [SECURITY.md](SECURITY.md) | the Gboard experience inside our page, on the laptop as well as the phone |
| **GIPHY API** | same shape, different terms | same |

**Do not build the picker before testing the catalogue.** This is the exact mistake
already made once with OpenMoji: 4,495 drawings and nothing for `shiva`, `ganesha`,
`krishna` or `tamil`. The two minute test is to search those words in Gboard's own
GIF tab on the phone and look at what comes back. If Tenor is as thin as OpenMoji for
this material, the picker is not worth an API key.

**Acceptance, and what is left of it:** a looping sticker rides the whole clip, with
the same drag, pinch and twist and the same fractional coordinates **(done)**; static
stickers are untouched **(done)**; the file size cost is measured and recorded
**(done)**; D-024 carries the phase amendment **(done)**; and a GIF picked in Gboard
on the owner's phone actually reaches the page **(not tested)**.

---

## T-020 (done) Serve sticker thumbnails at thumbnail size

**Done, 2026-08-19.** `/api/sticker?id=...&w=96` returns a scaled copy, written once
into `<sticker dir>/cache/96/` and served from there afterwards. Only the widths in
`stickers.THUMB_WIDTHS` are made, so nothing can fill the disk with one image at a
thousand sizes, and deleting an upload takes its thumbnails with it.

**The estimate in this task was wrong, and the measurement is worth keeping.** The
opening shelf of 40 costs **402 kB** at full size and **191 kB** at `w=96`, measured
in the real page: a 52 percent saving, not the order of magnitude guessed at here.
Flat OpenMoji artwork already compresses well. Still worth having over a phone
connection, and free after the first paint, but it is a halving and not a cure.

---

## T-015 (done) Let the page cancel a render

**Done, 2026-08-19.** A **Stop** button, since the redesign beside **Make the clip**
itself. It kills the yt-dlp
or ffmpeg the render is waiting on, the task ends as `cancelled` rather than
`failed`, and the run log says so. See [DECISIONS.md](DECISIONS.md) D-025 for why the
thread is the handle and why a post cannot be stopped the same way.

Verified against a real render on 2026-08-19: stopped 12 seconds in during the
download, no yt-dlp or ffmpeg left running, nothing in the output folder, no work
directory in `/tmp`, and a full render straight afterwards produced a correct clip.

**It found an older bug on the way.** ffmpeg writes straight into the output folder,
so a *failed* render had been leaving a truncated mp4 there for the page to list and
offer to post. `pipeline.produce` now removes a half written file on any exit.

---

## T-016 (done) Let the page delete a clip

**Done, 2026-08-19.** A **Delete** button in the result panel, set apart from the
buttons that get pressed on purpose. Two presses rather than a confirmation dialog,
because a dialog is dismissed by habit and a button that has visibly changed its mind
is not; it disarms itself after four seconds. It deletes the group the way
`retention` does, sidecars included, and is refused with a 409 while WhatsApp is
being driven, because the composer may be holding that very file.

---

## T-021 (P1) Find out why a clip *sometimes* crawls to the phone

**Priority:** P1, was P0
**Status:** **parked by the owner, 2026-08-19.** Revisit when it next bites

**What is known, measured 2026-08-19:**

| Measurement | Value |
|---|---|
| One download, from the owner's notification | 410 kB of 8.15 MB after ten minutes, about 700 bytes a second |
| **Other downloads of the same kind** | **1 to 2 seconds, complete. Reported by the owner, and with Tailscale on in both cases** |
| The same file leaving this machine | 8.15 MB in 9 ms, about 900 MB/s, on both loopback and the tailnet address |
| `tailscale ping` to the phone | two pongs `via DERP(blr)` at 374 ms, then `via 192.168.1.11:41335` at 35 ms |
| Both devices | on the same LAN, `192.168.1.10` and `192.168.1.11` |

**The intermittency is the finding, and it rewrites the task.** A fault that is
sometimes 1 second and sometimes 15 minutes, with the same tunnel up both times, is
not a bandwidth ceiling and not a weak radio: those are steady. It is something that
differs between one attempt and the next. That kills the third candidate outright
and demotes the first two into one question.

| Candidate | Still standing | Why |
|---|---|---|
| The slow transfers never left the DERP relay in Bengaluru, the fast ones went direct | **yes, and it is now the favourite** | `tailscale ping` was seen doing exactly this upgrade, relay first and direct three pings later. A transfer that starts before the upgrade and sticks to the relay is slow; one that starts after is fast. A relay in another city is also shared and rate limited |
| Android suspended the download in the background | **yes** | screen off or the browser backgrounded is the other thing that differs between two attempts of the same download |
| The phone's Wi-Fi is weak, or on a band the laptop is not | **no** | a weak radio does not deliver 8 MB in a second one time and 410 kB in ten minutes the next |

**The test to run when this is picked up again**, and it no longer needs Tailscale
turned off: start a download on the phone and, while it runs, watch
`tailscale status` on the laptop. It prints `direct` or `relay` per peer. Do it for
a fast one and a slow one. If slow always reads `relay`, the cause is settled and
the fix is to give the direct path time to come up, or to offer the LAN address
alongside the tailnet one when both devices are on the same network.

**Acceptance:** a stated cause, and either a fix or a recorded limit with a working
route around it. [LIMITATIONS.md](LIMITATIONS.md) Table LI-6 holds the finding.

---

## T-017 (done) Queue a render instead of racing for a name

**Priority:** P2
**Status:** **done 2026-08-20**, by the cheap fix done properly rather than by a queue

Two identical renders started in the same second can pick the same output stem, and
one clip overwrites the other. `naming.unique_stem` checks the folder and then the
render writes to it, which is a check-then-act with a real window in between.

It needs the same song and the same window submitted twice at once, so it has never
happened.

**What was built instead of a lock or a queue.** A lock in `serve.App` would only
cover the page, and the window is not the allocation: it is the **whole render**,
because the name is not on disk until the encode finishes half a minute later. So the
name is **claimed** rather than checked. `naming.reserve_stem` creates the `.part`
file the render was going to land in anyway, with `O_CREAT|O_EXCL`, so exactly one
caller can win it, between processes and not merely between threads. The page's
`*.mp4` glob cannot see a `.part`, so a claim is invisible until the render renames
it into place, and `produce` already cleared it on every exit path.

A claim left behind by a killed render blocks that one name. It is logged as a
warning rather than silently stepping to `-2`, because a clip that quietly becomes
`-2` is the kind of thing nobody notices.

**Acceptance: met.** Eight threads asking in the same instant get eight different
names, and two `produce` calls held open until both had claimed produce two clips.
Both tests fail against the old code: the second one loses a file entirely.

---

## T-018 (done) Promote the HD ladder if YouTube reopens it

**Priority:** P2
**Status:** **done 2026-08-20.** It reopened, through a door neither of the two
conditions below named

Video mode was 360p because format 18 was the only stream `--download-sections`
could cut, see [DECISIONS.md](DECISIONS.md) D-023. Two things would have unblocked
720p:

- `web_safari` returning HLS renditions again: **still no.** Four storyboards and
  nothing else, checked again on 2026-08-20
- googlevideo accepting ffmpeg's range requests for DASH: **still no.** 403 again,
  tried again the same day

**What actually opened it:** the **default** client lists formats 93 to 96, the HLS
renditions, and a section really can be cut from them because they carry their own
audio and need no merge. `STRATEGIES_VIDEO` now leads with `default 95/96`.

**Acceptance: met.** A real video-mode run reported `client=default format=95/96`
with no failed attempts, and the source it cut was **1280x720** h264 with aac,
12.08 seconds, **1,797,815 bytes**: bounded, which the DASH path never was.

**The catch, measured rather than assumed.** Whether a video has HLS renditions is
the video's property: a popular music video offered them on three consecutive asks,
and one of the owner's own uploads offered none on three, having offered them earlier
the same day. Quiet gaps of 3, 4 and 5 minutes changed nothing, so it is not rate
limiting. **Video mode is 720p when YouTube offers it and 360p when it does not**,
and a video that does not costs one failed attempt, about 2 seconds. The run log
names the winning client and format, so which happened is never a guess.

---

## T-014 (done) Narrow WhatsApp's effective media size ceiling

**Goal:** stop giving away bitrate on long clips.
**Status:** **done 2026-08-20.** The line is 10 MiB, and it was bisected rather than
estimated

**How.** Five probes attached to the live composer without sending, each one 90
seconds and identical to the others but for its size, so only size was under test.
A refusal presents as the composer taking the file and never opening its editor,
which is the whole instrument: an accepted file opens it in a second or two.

| Probe, bytes | Verdict |
|---|---|
| 10,311,640 | accepted |
| **10,452,278** | **accepted**, 33 kB under 10 MiB |
| **10,519,352** | **refused**, 34 kB over 10 MiB |
| 10,650,175 | refused |
| 11,013,670 | refused |

**The ceiling is 10 MiB, 10,485,760 bytes**, now `render.PLATFORM_MAX_BYTES`. Not
the 16 MB the platform documents. A control run confirmed the method: the 9,684,891
byte clip that had been accepted before was accepted again in the same session.

**The budget moved from 9,500,000 to 10,000,000**, not to the ceiling, because the
budget sets a maxrate and the encoder overshoots it by about 2 percent, measured
twice. 10,000,000 leaves 4.6 percent, twice the overshoot, and a test holds that
ratio. A 90 second clip goes from about 716 to 761 kbit/s.

**And the silent failure is no longer silent.** A clip that still lands over the
line is named in the log and on the command line report, because WhatsApp will not
say anything at all.

---

## T-012 (P2) Confirm the caption link outside the owner's own devices

**Goal:** know whether `--follow-up` is ever worth using.

**Detail:** the caption URL is tappable in WhatsApp Web and on the owner's own
phone. Every viewer so far is the owner. It is a safe assumption that other
clients render captions the same way, but it is still an assumption.

**Acceptance:** one person who saw a Status says the link worked, recorded in
[MEMORY.md](MEMORY.md) Table ME-1.

---

## Done

- Local pipeline, both render modes, transliteration, the two post output
  (`9d41a63`)
- Wrapper script so the tool runs from any directory (`caa2600`)
- Documentation set per `agent_docs_guide.md` (`1224f58`)
- **T-004** offline pytest suite plus an opt in end to end run, 82 and 7 tests
- **T-005** the winning extraction strategy is recorded per run, and a fall through
  to a later ladder entry logs a warning
- **T-006** a low resolution artwork fallback logs a warning naming the size
- Human readable date led filenames, output folder self pruning, and the
  instructional card text removed
- **T-007** `--frame` writes a full resolution still beside the clip, pruned with
  it and recorded in the run log
- Posting a real Status end to end from the desktop over CDP (`ece0d90`)
- **T-001** the caption link is tappable. Confirmed in WhatsApp Web, then by the
  owner tapping it on his phone, where it opened the YouTube app. This retired the
  two post flow, see [DECISIONS.md](DECISIONS.md) D-013
- **T-010** the bottom 15 percent of the frame is reserved for WhatsApp's caption.
  The link pill is gone, replaced by a small URL line inside the text flow, and
  `tests/test_safe_zone.py` measures that nothing intrudes. Verified against a real
  posted Status with no collision, see D-014
- **T-011** `--post` posts the clip from the main CLI, `--follow-up` adds the text
  only Status. Posting logic lives in `wastatus/post.py`, and
  `scripts/wa_post.py` is now a debugging door into the same functions
- **T-002** dropped. The composer's own audience selector handles the recipients,
  so the JID list question that blocked the whatsmeow design no longer exists
- Artwork rework: padding bars cropped from thumbnails and from letterboxed source
  video, the card shaped to its artwork, elevation, `SAFE_TOP`, and hyphen aware
  title wrapping (D-016)
- The page's post button, verified live by the owner: two Statuses out at 21:53 on
  2026-08-18 and 00:14 on 2026-08-19, 5s and 4s. That was the last path in the tool
  that had never been exercised for real
- **Load, not send** is the page's primary action, and `--load` does the same from
  the command line (D-020). The composer is left holding the clip and its caption
- The caption is edited in its own labelled box and echoed where WhatsApp draws it, saved without a
  render, and the card wording is filled back into the form from a per clip job
  sidecar so a correction is one edit and one press (D-021)
- Byte range serving, which is what makes the preview's seek slider work at all
- Any debug browser holding a WhatsApp tab can be posted through, and the page can
  start one (D-022)
- Both download ladders lead with the only format a section can be cut from, after
  measuring that `web_safari` returns no media at all (D-023)
- Stickers: an installed OpenMoji library of 4,495, search, drag, size and turn on
  the preview, upload your own, baked into both modes by `compose`, remembered in the
  job sidecar (D-024)
- The origin check derives its answer from the request rather than from a constant,
  which unblocks ever reaching the page from another device, and refuses a name in
  the `Host` header so DNS rebinding gains nothing
- Evolution API's status endpoint read from source and written up in
  [docs/hosting.md](docs/hosting.md), before anything was built on top of it
- **T-015** a render can be stopped, and a stopped or failed one leaves no truncated
  clip in the output folder (D-025)
- **T-016** a clip can be deleted from the page, group and all, on two presses
- **T-020** the sticker picker asks for 96 pixel copies, halving what a shelf costs
- The page is reachable from another device with `--also-on`, loopback still bound,
  and it offers Download plus the caption for posting in the WhatsApp app instead
  (D-026, D-027)
- The page redesigned mobile first from the owner's own marked up screenshots:
  one health chip, a one row window, a text keypad on the timestamps, Stop beside
  Make, a numbered stage sequence, safe areas on by default, a labelled caption box,
  a sticker panel with tags, one device chosen primary action, the whole form
  remembered, and light, dark or system (D-029, D-030, D-031)
- **T-003** the card design is approved. The owner compared the card and `--video`
  versions posted at 16:07 and 16:08 on 2026-08-18 and approved both, including the
  air between the channel line and the waveform
