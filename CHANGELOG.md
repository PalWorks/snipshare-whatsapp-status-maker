# Changelog

Human readable history. Newest first.

## 2026-10-31, fifty-ninth pass

Written **2026-10-31T12:23:37+05:30**. From the owner's review of production; decision D-107.

### One Schedule button

**Add to queue** is gone. The finished clip has one **Schedule** button, whose picker
opens on **Next in queue**, chosen, with the time it will land ("Next in queue · Sat 6:00
PM"), then In one hour, This evening and Tomorrow morning (passed ones hidden) and the
date and time field. The hint reads "Puts the clip in WhatsApp at the time you choose,
or next in your queue. You press Send." The time comes from three read only fields the
extension now adds to `queue-peek`: `lastDue`, `gapMinutes` and `quiet`. An older
extension gets "Next in queue" and "After your last scheduled post".

### An Account menu on the tool page

The Account chip opens a menu: Profile, History, Scheduled Statuses (when scheduling is
on), Extension, Admin (admins), Sign out. Keyboard and screen reader friendly, 44px
items, kept inside a phone's screen, both themes.

### The footer, and the toast on a phone

The footer's "independent, experimental project" paragraph is removed from every page;
the Terms and the home page's questions still say it. The snackbar now uses the
screen's width on a phone instead of half of it, and its action is 40px tall.

### Extension 2.1.1

For the `queue-peek` fields. `EXTENSION_MIN_VERSION` stays 2.0.0. Tests: 157 Node,
pytest 1613 passed and 7 skipped.

## 2026-10-31, fifty-eighth pass

Written **2026-10-31T11:21:01+05:30**.

### Scheduled Statuses in the account page

The account page's menu gains **Scheduled Statuses**, after History, for people whose
scheduling pilot switch is on. It frames the extension's own queue page
(`queue.html?embed=1`), so there is one queue UI: no header of its own, the site's
theme, its height told to the page. States for loading, extension missing or too old,
a phone, and a frame that does not answer (then the queue opens in its own tab). Up
next's **Scheduled** on the tool page now goes there. The manifest exposes the four
queue files to the site alone (`web_accessible_resources`, rewritten by the build), and
the account page's policy names the extension in `frame-src`. See
[docs/account-page.md](docs/account-page.md), Tables AP-8 and AP-9.

### A capture no longer waits on a YouTube tab that cannot answer

Added **2026-10-31T11:26:20+05:30**. When the video was already open in a tab from before the extension was
installed or reloaded, that tab had no recorder; the extension brought it forward,
waited 45 seconds on it and left the person there, the page showing "Getting the
video". Now an existing tab is used only if its player answers and is ready, and it is
read where it is, never brought forward; otherwise the extension opens its own muted tab
as for a video not open anywhere, and the page's tab is made active again whether the
video opened or not. `src/test/capture.test.js`. Tests: 156 Node, 1593 pytest passed
and 7 skipped.

## 2026-10-31, fifty-seventh pass

Written **2026-10-31T01:51:00+05:30**.

### Scheduled Statuses, Release 1: prepare only, from the editor

D-105; the plan is [docs/scheduling.md](docs/scheduling.md) and what was built is its
Section 15. On SnipShare a finished clip can now be **Scheduled** for a time or **Added
to the queue** after the last one. The extension keeps the clip on the person's own
computer (IndexedDB, in 2 MiB parts, size checked and a SHA-256 kept), and when the
time comes it puts the clip in WhatsApp's composer for the person to send. It never
presses Send: confirmed Send is not built, and AGENTS.md and D-084 still forbid it.

- **The queue** is a page of the extension (`queue.html`, also from the toolbar
  button's menu): a table ordered by time, each row's time and caption edited in place,
  Cancel with Undo, Pause and Resume with three choices, a history of 30 days, the
  budget of held clips, the run log. The one primary button is **Prepare next now**.
- **The quiet runner** walks a ladder of placements (S0 to S5) that avoid taking focus,
  learns per machine which rung works, and asks by notification when none does.
  **Try quiet mode now (nothing is sent)** on the queue page tests it.
- **Notifications and badge.** Every prepared clip says "in WhatsApp, press Send" with a
  **Show WhatsApp** button and counts on the badge as Needs you, because in this
  release every prepared clip needs a press and an open composer blocks the next run.
- **Settings** in the options page: quiet hours (23:00 to 07:00 by default), the gap for
  Add to queue (3 hours), bring WhatsApp forward, take focus when idle, a notice for
  every post. The last three are off.
- **Extension 2.1.0**, with four new permissions: `notifications`, `idle`,
  `unlimitedStorage`, `contextMenus` (SECURITY.md). New port commands `schedule`,
  `queue-peek` and `open-queue`; `hello` now lists `features`.
- **The server** keeps per person limits an admin sets on the admin page: clips a day,
  upload a day, scheduled posts, held clips, and the scheduling pilot switch. Admins
  start with scheduling on, 90 posts and 1 GB; everyone else with it off, 30 posts and
  400 MB. `/api/state` carries `scheduling`; `POST /api/admin/limits` edits it; failure
  reports accept the source `schedule`.
- **Tests.** 152 Node tests pass; the full pytest suite passes (1569 passed, 7 skipped),
  counted 2026-10-31T09:55:06+05:30 after the fixes from an independent review: Undo of a resume restores
  the pause; a Pause or a later time set while WhatsApp is being readied wins; a clip
  handed to WhatsApp is never loaded again after a worker stop; alarm resets are
  serialised; the helper window never closes WhatsApp; calls into a hung tab give up
  after 5 s; a background tab the run opened is closed when the run fails before the
  hand over, unless WhatsApp is signed out.

**Not verified.** Phase 0 has not been run on the owner's Chrome, so every Chrome
behaviour the plan labelled unverified still is, and nothing was tried in a real
WhatsApp Web. A headless Chromium run with the real extension and a local hosted server
covered the queue, but not resume's three choices end to end nor the alarm rebuild on
every wake. Release 2 (from a link) and Release 3 (the bulk bar) are not built.

## 2026-10-26, fifty-sixth pass

Written **2026-10-26T01:29:37+05:30**.

### The app reaches the internet and nothing else

D-102. Firewall rules on the host now stop the app's containers from opening
connections to the host, to the other machines on its private network and to the
cloud's metadata service; everything the app calls on the public internet still
works. The rules match only this project's own network, so nothing else on the
host is affected, and `scripts/deploy.sh` installs them as a service that holds
after a reboot.

## 2026-10-25, fifty-fifth pass

Written **2026-10-25T22:43:40+05:30**.

### The repository's new name

The public repository is `PalWorks/snipshare-whatsapp-status-maker`, "SnipShare:
WhatsApp Status Maker from Social Media Snippets". This folder now follows its
history; the old private history is kept as the local branch `private-history`.

### A second security pass

D-101. The extension you install is now built into the server's image, where nothing
running on the server can replace it, and `/install` shows its SHA-256 so a download
can be checked. Requests that could be read two ways are refused. Sign-in is tied to
the Google account that first used an address, and you will be asked to sign in once
more. The extension's permissions end two hours after they are given, however busy.
GIFs come only from GIPHY's and KLIPY's own servers. Pictures that claim to be huge
are refused before they are opened. More protective headers, and no email addresses
in the server's log. A capture after a long ad is no longer given up on while Chrome
holds the background tab back.

## 2026-10-25, fifty-fourth pass

Written **2026-10-25T15:11:42+05:30**.

### Ready to be public

D-099. The repository is prepared for publication as a fresh copy, `PalWorks/snipshare-whatsapp-status-maker`.
The licence is now **AGPL-3.0-only with a paid commercial licence**
([COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)); the packages it uses and their
terms are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); contributions need a
signed-off commit and a licence grant ([CONTRIBUTING.md](CONTRIBUTING.md)). Every
page of the site links to its source code. The hosted image no longer installs
yt-dlp, the token plugin or the websocket client, which it never ran. New documents:
API, DATA_MODEL, OBSERVABILITY, INCIDENTS, DEPENDENCIES, GLOSSARY, FAQ, PROMPTS,
SKILLS, CODE_STYLE and CONTRIBUTING; the README is rewritten for a newcomer.

### The audit before publication

D-100. Fixed, each with a test:

- **The site:** nothing is read from a stranger before their session is checked; a
  GET or HEAD with a body is refused; titles and words are held to 1,024 characters,
  so a long one cannot hold the render slot; signing up with a typed address no
  longer says how that address stands; an admin's files can no longer be deleted
  through a refused delete; two sign-ups at once are one request; signing out of the
  last browser ends the extension's grants; an upload that just received a chunk is
  never swept; stickers are counted under a lock and against the day's upload
  allowance; uploads are read only as the two containers YouTube sends; errors name
  no path on the server.
- **The extension:** a slow line no longer fails the read at two minutes, or the
  upload when a chunk takes over 30 seconds; the size of the chunks is remembered
  across a restart of the worker; Stop on the site also stops the WhatsApp step; one
  capture and one WhatsApp load at a time, whichever path asks; leftovers in storage
  are cleared; resumed downloads check where they resume.
- **The pages:** watching a post no longer stops the watch on a render; one dropped
  poll no longer calls a render failed; Ctrl+Enter cannot start a second render;
  sticker and GIF results always match the search box; **your own stickers can be
  deleted**; every request has a timeout and a plain message; the admin page's
  refresh waits while you are in the middle of something; Undo stays while you reach
  for it, and Alt+U presses it; controls are 40 px on touch screens.
- **The local tool:** a link can no longer pass options to yt-dlp; the page cannot
  be read through another name for this machine; sending is the default nowhere; a
  Status is "posted" only on WhatsApp's answer, and a failed follow up text never
  hides a video that went out; prune, the controls check and the token provider no
  longer race; ffmpeg cannot read the terminal and gives up after 15 minutes; the
  proxy password stays out of the log; the provider install is pinned and never
  deletes a folder it did not make.

An independent review of the fixes found nine more, all fixed: a download resumed
after a second drop could count the same bytes twice and pass its size check
corrupted; a slow clip fetch for WhatsApp said nothing for five minutes and the page
gave up on it (it now reports progress); a refused small body is read so the browser
sees the refusal rather than a broken pipe; requests on Safari before 16 no longer fail
for want of `AbortSignal.timeout`; a sticker that could not be saved gives its bytes
back properly; the provider install survives a lock file the old script changed; a
link pasted without `https://` works again at the command line; and the tool page
itself links to the source.

Checked end to end against a local renderer: a video clip on an 800 kbit/s line with
the worker stopped mid upload (153 s) and again mid download (117 s), a card clip
(28 s), and Stop while rendering, which left no job behind and put the viewer's player
back.

## 2026-10-25, fifty-third pass

### Account and admin, redesigned as one system

D-098. Settings read first and edit in place; changes confirmed at the foot of the
screen, with Undo where it makes sense. Profile: your Google photo, name, theme. A
new Sign-in and security section lists where you are signed in, with Sign out for
each. API keys as rows: Connected, Replace, Remove. Feedback with a subject and up to
three screenshots. Admin with a date range, request cards, a searchable people list
and a compact Add person. Every page's header now has the theme switch and, signed
in, your photo.

## 2026-10-25, fifty-second pass

### Every press is answered

D-097. Hover and press states on everything pressable, the account chip clearly a
link; a spinner on a link the moment it is pressed and a bar across the top when the
next page is slow; spinners on busy buttons; loading shapes on the account and admin
pages. On a phone, GIPHY, KLIPY and Both sit under the GIF search as a compact row.

### An account page

T-069, D-095. The account icon opens `/account`: two columns on a computer, a row of
tabs on a phone, one section at a time. **Profile** (change your name), **History**
(today against the limits and when they reset in your own time, the last 14 days,
every clip of the last 90 days with a link to the original, and Open or Download
while the clip is still kept), **API keys**, **Feedback**, **Extension**, and
**Privacy and data**, with **Sign out** always there. The panel that unfolded over the
tool page is gone.

**GIPHY and KLIPY at once.** Each person keeps both keys, masked as typed and shown
afterwards only by their last four characters, and searches either one or **both,
mixed together**, asked side by side. With two keys the shelf's service switch
appears beside GIF search, as radios on a computer and as a compact segmented row on a
phone, and the choice is remembered. The local tool can do the
same with both keys in `.env` and `WASTATUS_GIF_PROVIDER=both`.

**Feedback** goes to the operator by mail with your address as the reply-to, so the
answer comes straight back; a problem can carry the last failure the page saw.

### A clip opens on its picture

D-094. Clips faded in from black, so WhatsApp's composer and Status list showed a
black frame until play. The picture no longer fades in; the sound still rises over a
fifth of a second so it does not click.

### `src/`

D-096. The extension's folder is `src/` now.

## 2026-10-25, fifty-first pass

### SnipShare: the page you know, for anybody the owner lets in

T-068, D-087 to D-093. The extension's button now opens **SnipShare**, "Status Maker
for WhatsApp, from YouTube videos": the same page the local tool serves, hosted, each
person with their own clips, stickers and GIF key. People ask for access with a short
form or **Sign up with Google**; the owner hears by mail and in Chat and approves on
`/admin`; approved people sign in with Google. **Make the clip** asks the extension to
read the window in the person's own Chrome (the video shows in a tab for a moment,
then steps back), the server renders it with the same engine, and **Load into
WhatsApp** has the extension place it in their own WhatsApp Web composer. Nothing on
the server asks YouTube anything or drives WhatsApp.

A public front page, `/install`, `/privacy` and `/terms`, plain and factual: not a
downloader, ads play, protected video cannot be clipped, you press Send, experimental
and by invitation, not affiliated with YouTube, Google, WhatsApp or Meta. Making a
clip needs desktop Chrome with the extension, and that is said on every page it
applies to, and in a banner with greyed buttons on the page itself.

Ten clips and 500 MB a day each, one at a time, 60 renders an hour across everybody,
refused before anything is read. Failures are reported without the video; the owner
hears about requests, limits reached, failure rates, a full disk or a long queue,
once per kind per hour, and gets a digest every morning. The popup is kept as the
extension's options page.

### Its own Compose project, behind a Cloudflare Tunnel

The renderer left the host's shared proxy: one Compose project with the app and a
tunnel, its own network and volumes, no host port, its scheduled work inside it.
The shared Caddy block, the DNS `A` record and the old container, image, folder and
volume are gone; the token file and the old logs came across. The uptime monitor
stayed green through the switch, and the other sites on the host were checked after.

### Fit to publish

The site's address, the host, the owner's addresses and every key live in `.env`
files and the private notes; the extension in the repository talks only to a local
copy and is built for the real site by `scripts/build_extension.py`. A new test fails
on any real address, public IP, home directory or string on the owner's private deny
list, and the documents were swept to pass it.

### Audited three times

The master audit, across the whole system after the fixes below, found five more,
all fixed with tests: a body sent without a length on a page call left in the
connection the tunnel shares between people; a failure code able to page the Chat
space; the popup, as an options tab, never finding the YouTube tab; Stop ignored
between the capture and the render's answer; and the check script able to drive a
server it had not started. Also from it: the running render named in the page's
state, so a lost answer can be picked up; clip grants renewed on use; refunds on the
day they were counted; scratch media cleared at start; an unset admin list demoting
nobody; the renderer's health counting the page's renders; and `deploy.sh` refusing a
site that differs from the server's own address.


The first audit found an open redirect after sign-in, the hourly cap kept by refused
uploads, Stop lost to a status check, a Google outage answered with a dropped
connection, an account deleted mid render writing itself back, a cookie set by
Google's own script signing people out, upload bytes counted twice, grants expiring
mid upload on a slow line, a requester's name able to page the whole Chat space, and
the popup left unreachable. All fixed, with tests. Two more were found by testing in
production: Cloudflare in front of Resend refusing Python's default User-Agent, and
the Turnstile box sharing its id with Turnstile's own global, so it never rendered.

## 2026-10-24, fiftieth pass

### A browser extension, and a renderer that never asks YouTube anything

T-066, D-080 to D-085. Anybody with a token the owner made can now make a clip from
the YouTube tab they are watching. The extension copies what YouTube's own player
appended to the page's video buffers, so the video is read on the viewer's own
connection; uploads the window in chunks that resume; and the clip is made at
the hosted renderer by the same `pipeline.produce` the local tool runs, through a
new seam, `pipeline.Captured`, and a new cut, `capture.section`. **Load into
WhatsApp** puts it in WhatsApp Web's Status composer with the link as its caption,
and never presses Send.

Verified end to end in the owner's Chrome, signed out with ads and signed in with
Premium; across in-page navigation; on an 800 kbit/s line through Cloudflare with
the extension's worker stopped mid upload; and with Stop pressed mid capture and mid
render, leaving nothing running anywhere. Sync through the whole production
pipeline: the flash on the frame, the beep 0.6 ms after it.

### Audited twice, the second time by a reader who had not written it

The second audit found twelve things, all fixed before this was called done: the
recorder holding every finished video's bytes in a map nothing trimmed; Stop's
DELETE carrying an already aborted signal, so it was never sent; the recovery for a
lost job answer being unreachable because the server looked at the spent uploads
first; Try again resending a capture the server had rejected as short; a slow
download being cut off at 90 seconds whatever it had received; a video switch during
the walk capturing the other video; a quality switch part way leaving the walk
waiting for a buffer the player would never fetch again; Stop leaving the walk
seeking the viewer's player; an ad that never ends keeping it going for ever; the
viewer's own quality choice being reset to automatic; an upload deleted while a job
claimed it; and any script on a YouTube page being able to answer as the recorder,
now closed by a MessageChannel handed over before YouTube's scripts exist.

### "Artist - Song" kept its space

T-067, D-086. Every card with a dash between spaces in its title read "Artist -Song".
Found on a frame the renderer made.

## 2026-10-24, forty ninth pass

### Send has no icon any more

T-065, to D-079. WhatsApp Web dropped `data-icon` from the composer's Send button,
which was how the tool knew a composer had opened. Loading waited for a button that
was already there. Send is matched by its label as well now, `Send 1 selected` or
`Send`, and the check for an already open composer recognises the text composer by
its `Close status posting view` control, so a chat with a typed reply is never
mistaken for one. `cancel` clicks that control too. Verified on the live page
without sending.

## 2026-09-01, forty eighth pass

### The audit: a green test measuring a frame that no longer existed

T-064, to D-078. `tests/test_safe_zone.py` is what guarantees no text is drawn under
WhatsApp's header or into its caption band. For card mode it worked the layout out a
second time, beside the copy in `build_card`. D-075 changed the drawing; the test
kept passing, still describing the layout that had just been replaced.

Nothing broke because of it. That is the point: the failure mode of a duplicated
layout is a green test, not a red one. `compose.card_words` is the single function
both now ask, `_painted_rows` decides nothing and only measures what it is given,
and every card-mode assertion in that file goes through the same arithmetic the
renderer draws with.

### The follow up Status was the poor relation

T-064, to D-078. One run can publish two Statuses. The clip got the ack check, the
retry and the sheet row; the follow up text got the ack check and neither of the
other two. It has all three now, its row says which of the two it is, and both
senders share one `_keep_trying` loop so the next fix cannot reach one and miss the
other.

### Swept out

To D-078. `eyebrow_room` had no callers left anywhere, in the tool or the tests: it
answered a question card mode stopped asking. Gone, with the test that reasoned
about a label above a card. `--eyebrow`'s help in the CLI and the README still
described the old placement. LIMITATIONS still carried "top text may not fit in card
mode" as a live limitation. A sentence in the preview pane read "cannot show that
... to see that".

### Checked and left alone

Every `D-` and `T-` reference in every document and source file resolves; the five
gaps in the task numbering are the retired ones TASKS.md explains. No broken
relative links. Nothing defined and never used in `wastatus/` or `app.js`. The token
is compared with `secrets.compare_digest`, `SAFE_STEM` and `STICKER_ID` keep a
request off paths of its own choosing, `_static` only ever sees an allowlisted name,
object URLs are revoked, the task lock keeps `post` and `prepare` exclusive, and
`sheet.py` never logs its bearer token.

## 2026-08-31, forty seventh pass

### One field, one place

T-061, to D-075. "Text above title" hung off the title in video mode and off the
card's top edge in card mode, so one field put a line below the picture in one and
above the artwork in the other. It is anchored to the title in both now, and in both
the picture gives way for it: `card_floor` and `video_picture_bottom` are one
function with a different title row.

### A line that is never dropped in silence

T-061, to D-075. Card mode wrapped the label to the room above the card and then
wrapped the top text to whatever the label left, which on a full height card is
nothing. It was drawn as nothing: no gap, no ellipsis, no complaint. The words stayed
in the box and in the sidecar, so the page then compared them against themselves and
reported the clip up to date with a line it had never drawn.

A full height card's top lands on row 325 and one line of top text needs 344.
Nineteen pixels. A fitted card gives them up now. A **placed** one is never moved,
because the placement is the owner's, so that case is measured and said out loud:
`X-Dropped-Toplines` off the preview, and a sentence in the pane before anything
else.

With neither field set the card is exactly the card it always was, which is the whole
no-regression promise: both fields are off by default.

### The label had nothing to be read on

To D-075. Found while reading the frames, not reported. A placed picture can reach
down over the row the label lands on, where the bottom shade has ramped to alpha 1
out of 200: white letters on a bright frame. The shade starts above the label now,
and only when a picture actually reaches it, so a fitted picture is byte for byte the
frame it was.

### The pencil edits the line where the line is

T-062, to D-076. D-063 argued for one box and no second editor. The half that holds
is that there must be one string. The half that does not is that pressing a pencil on
a line you can see sent your hand to a box further down the page. Both are live now
and they are the same string: `applyText` writes the decal and whichever box the
keystroke did not land in, so typing in either follows in the other, and neither is
ever rewritten under its own caret.

### The preview pane says what it cannot show

T-063, to D-077. Reported about a GIF: the Post it panel warned that the clip was out
of date and the pane beside it showed the old frame with nothing to say, while a word
change put both into a warning. `drifted` knew about eight kinds of change and
`aheadOfClip` about three. The three it cannot draw, stickers, the waveform and the
mode, are named in a sentence rather than left silent, and a change it *can* draw
still wins.

## 2026-08-31, forty sixth pass

### A Status counts as posted when WhatsApp says so

To D-071. Reported as "my WA web interface shows as though the video has been
published, but in-reality it has not": nothing on the phone, nothing but zeroes in
the view count. The tool had never checked. `wait_until_sent` asked whether the
composer had closed and whether anything still said "Sending", which are facts about
this browser and not about WhatsApp, and every posting run ever recorded came back
with exactly `4.0` seconds, the arithmetic floor of that function. It had been
measuring its own sleep.

WhatsApp Web keeps an `ack` against every message it sends: below zero refused, zero
unanswered, one or more accepted. `confirm_sent` reads it. The Status posted at 19:21
that day was sitting at `-1` while the tool called it a success. A store this tool
cannot read falls back to the old wait and says in the log that the result is
unconfirmed, because a build it does not understand is not a Status that failed.

### The caption box is named, not merely contenteditable

To D-072. Found while reading the page for the above. `COMPOSER` was
`div[contenteditable="true"]` against the whole document, and the chat's own message
box is one of those. With a conversation open, which is how that browser is always
left, the composer looked ready before the media editor existed and the caption could
be typed into the conversation instead. Scoped now, two ways, and the wait is for the
caption box **and** the Send button beside it.

Verified against the real client with a group chat deliberately open: the scoped
selector matched one element, the caption landed in it, the chat's box was untouched.
The first Status posted through the new code landed and drew views within ten minutes,
where every one before it had not.

### A refusal is tried again, no answer never is

T-058, to D-073. `StatusRefused` means WhatsApp answered no, so nothing went out and a
second go cannot show anyone the same clip twice: three attempts, twenty seconds apart
and doubling. `StatusUnconfirmed` means no answer at all, and that one is never
retried, because a Status that may yet go out must not be sent again to settle a
doubt. Both settable per machine.

### The sheet records what went out, and only that

T-059, to D-074. Every Status WhatsApp accepted gets a row in a private Google Sheet:
Timestamp, Source, Status, Remarks. A refused one gets none. That column is only worth
having because the `ack` check makes it true; before it, every row would have said
Published. A service account keeps the sheet private and needs no re-authorising, and
every failure in `sheet.py` is caught and swallowed: an unreachable sheet costs a row,
never a Status.

### Deleting a Status leaves something that looks like one

To D-071. Caught the same evening, deleting two dead Statuses: a delete writes a
protocol row under the same key prefix, subtype `sender_revoke`, carrying `ack 0`. It
was the newest row in the range for a moment, which would have made the next post
report itself unaccepted. Filtered out by type and by `protocolMessageKey`, either of
which alone would catch it.

## 2026-08-27, forty fifth pass

### One rhythm down the column of cards

T-057, to D-070. Every card on the page is the same card and they read as one run,
and they were not spaced like one: the four inside the form sat 12 pixels apart and
the four around it 20, from 600px up. Two rules, each correct for the container it
was written for, wrong as a pair. Both take the grid's own gap now, so the run is 20
the whole way down; a phone keeps 12, which is where the two already agreed.

### The page says each thing once, and an address carries its port

T-056, to D-069. Three marks on one screenshot of the footer, all the same complaint.
"Clips in out, newest 20 kept" is a line inside the Recent card now, under the strip
it describes rather than at the bottom of a page. The reachable line is folded away on
a laptop, where the health chip has been saying the same thing since T-025 and says it
with the port; on a phone it stays exactly where it was, because the top of the page
is a long way from the bottom and the bottom is where you are when you want to type
that address into the phone in your other hand. And the address carries its port now,
through the same expression the chip's row uses, so the two cannot drift apart again.

It improved the layout from earlier in the day without being asked to. The footer was
most of the page sitting below the grid, and that height is what pulls a sticky column
off its anchor at the end of a scroll: the preview card's ride up was 74 pixels, and
it is 32 at 1440x773 and none at all at 1920x1033.

### The history was scrubbed a second time

T-022, to D-040. The Chrome profile name carrying a personal account handle, which
the working tree lost this morning, lived in commit `4429818` from 2026-08-21. Same
tool and same replacement as the 2026-08-20 rewrite: `git filter-repo --replace-text`,
75 commits rewritten, every hash after the first change new, the working tree byte for
byte what it was. The string is now in no tree of no commit.

Worth knowing rather than assuming: a force push makes the old objects unreachable
from any ref, so they are gone from a clone, from `git log` and from GitHub's search,
but the old commit is **still served by its full hash** through the API until GitHub
garbage collects. Deleting and recreating the repository is the only certain route,
and that belongs to the day it goes public.

### The frame stays on screen while the answers scroll past it

T-055, to D-067. Desktop only. Everything you answer is in the left column now,
including Post it, which moved up out of the frame's column to sit above Recent; the
frame is in the right column and does not move. The reason is a real failure rather
than a preference: the sticker shelf is halfway down the left column and a sticker is
placed by dragging it onto the frame, so reaching the shelf used to scroll the target
off the screen. The same was true of the buttons that send.

Sticky, not a scrolling box: the page keeps its one scrollbar. The offset is the top
bar's own measured height, because that bar is sticky itself and grows a tagline at
600px, and every read of the measurement carries a fallback so the first paint is
right. On a short screen the frame takes the height that is left rather than being
cut off at the player, floored at 168px. At 1440x773 that is 277 wide with 8 pixels
of air under the player. The right column is sized to the frame rather than to half
the page, which gives the fields opposite about 250 pixels they did not have.

The ceiling on that height is 300px up to 1180 wide and **360 from there**, asked for
the same afternoon looking at a 1920 wide screen. 360 is exactly a third of the 1080
the clip is drawn at and about the width of a real phone; it waits for 1180, the
grid's own `max-width`, because below that the extra 60 pixels would come out of the
column holding every field.

The phone is untouched. Panel order there is decided by `order` rather than by the
DOM, so moving Post it between the columns moved it on a laptop and nowhere else.

### A fold control you can aim at, and a class that was quietly taking over

T-055, to D-068. The arrow on every card header was an 18px filled triangle. It is
Material's chevron at 24px in a 32px round target, still turning over when the card
opens, which is why a chevron rather than a plus and a minus: the rotation is the
state. The top bar's own caret is left alone, since it says a panel drops down rather
than that a card is folded.

Doing it turned up a regression from the same morning. The fetch icon added in T-052
was given the class `.iconbutton`, which the top bar's theme and health buttons
already had: same selector, later in the file, so it had been stripping the border
and the surface background off the theme button in the top bar and shrinking its
glyph. It has a name of its own now, `.headeraction`, and a test asserts that
`.iconbutton` is declared exactly once.

### The video's own words, before the clip rather than after it

T-052, to D-064. The title and second line boxes have always meant "leave me empty
and the video answers this", and the answer only ever appeared in the finished
pixels. An arrow in the Words header asks the video now: one probe, the same cleaning
the card would have done, into the two boxes, with the card opened so they can be
corrected before anything is rendered.

What it offers is what an empty pair of boxes means, to the letter. Fetch fills them,
so the next render takes the override path rather than the read-it-from-the-video
path, and those are different code: `to_latin` over an override, `clean_title` over a
fetch. `words_from_video` therefore asks `title_and_channel` for a job that overrides
nothing, and the round trip is a test rather than a claim. A real link answered in
1.5 seconds, a pasted playlist came back with the refusal that names the playlist and
says what to do instead.

### Emoji in a placed line

T-053, to D-065. The free text box always accepted emoji. Pillow drew an empty
rectangle for each one, because the line is set in DejaVu and DejaVu has none.

They come from OpenMoji, the 4,495 pictures the sticker picker already installs: no
new dependency, no new download, the same drawing on Linux and macOS, which is the
promise the vendored font is there for in the first place. A system emoji font would
have broken exactly that.

The rule for what becomes a picture is deliberately narrow, because OpenMoji ships a
drawing of a hyphen. Only the pictograph planes, a two letter flag, a keycap and one
of the older symbols wearing the selector that asks for emoji presentation: a bare
`(c)`, a star and a quaver stay in the font. Forty renders of lines without emoji, at
four widths, are byte identical to what they were.

An emoji this machine has no picture for is left out rather than drawn as an empty
box, which you see happen in the preview as you type. A line that is only such an
emoji is refused with the one sentence that fixes it.

### Make the clip goes grey when there is nothing to make

T-054, to D-066. The button looked the same before and after a render. It is grey now
once the clip on screen is everything the form asks for, and it comes back the moment
anything reaches the pixels: the words, the link, the window, the waveform, the mode,
the background, a placement, a sticker, a GIF, a line of free text.

Not the stale notice's answer, which leaves the link and the window out on purpose so
that setting up the next clip does not fire a warning about the last one. The button
asks the other question and counts them. The safe area guides are still not a change,
because they move the preview and never the pixels. ⌘/Ctrl+Enter had to be stopped
separately: `requestSubmit` does not ask a button whether it is enabled.

### Fit for the two machines, and for being read by strangers

Swept for anything that only works on Linux and anything of the owner's that would
travel with the code. Two tests were Linux only and are now skipped rather than
failed on a Mac: one binds `127.0.0.2`, which macOS does not put on loopback, and one
reads `/proc`, which macOS does not have. The product code behind both already
degrades to a documented "" or None there.

One string of the owner's had reached four documents, a Chrome profile name carrying
their account handle, quoted from live output. It is a placeholder now.

## 2026-08-27, forty fourth pass

### The artwork panel is placed the same way the frames are

T-050, to D-062. D-061 gave video mode's picture a placement the day before and left
card mode's panel laid out for you: a fixed width, a height its own shape asked for,
pinned above the title. It takes the same three fractions now, through the same
control on the page and the same box on the frame.

Where the words go was the real question, and it was put as three options. **Option A
was chosen: the words follow the panel.** That is how card mode was already laid out,
the label anchored to the panel's top edge and the top text above the label; what is
new is that the anchor can be anywhere. So it is clamped at both ends of the travel,
because past the top the label lands under WhatsApp's own header and past the bottom
it lands across the title. Every fitted card already sits between those two clamps,
which is why nothing in the archive moved: 15 fitted cards across five artwork shapes
and three sets of words render byte for byte as they did.

A panel dragged over the title now gets the same bottom shade video mode has always
laid over its frames, because the card's own scrim goes on *before* the panel and
white text on a bright thumbnail is unreadable. Only when the panel reaches past
where a fitted one stops, so no fitted card is darkened.

Card mode has no clip too old to preview, unlike video mode: it kept the artwork, so
the card is drawn again rather than rebuilt from a still.

### A pencil on a line of words

T-051, to D-063. A placed line could be retyped only by knowing that the box below
retypes whichever line is selected, and nothing on the frame said so. A pencil now
appears on a line under the mouse and takes the hand to that box: the section opened,
the box scrolled to, focused, and its contents selected. It opens no editor of its
own, because one box writes free text whether the line is new or being retyped.

Hover, not selection, because until you know a line can be retyped there is nothing
to select it for. Free text only, and mouse only: a phone has no hover, and tapping
a line there already fills the same box.

### Look stopped being a wall of small print

Reported as "too congested". Three stacked label-control-hint blocks, the first of
them with no label at all, which made the second one's read like a heading for the
whole panel. There is a label on the first now, a rule under it, and the two fields
that answer to it sit side by side wherever there is room.

Two things were found while in there. `setMode` unchecked every segmented option on
the page rather than its own, so switching between Artwork card and Video frames left
Background showing neither of its two options until one was clicked. And the rotate
handle's pale icon was drawn on a system-light page, near-white on near-white,
because `:root:not([data-theme="light"])` matches a page whose theme is left on
system regardless of what the machine's setting is.

---

## 2026-08-26, forty third pass

Four tasks, each written up in full in [TASKS.md](TASKS.md): free text you place
yourself (T-046, D-058), black behind the frames (T-047, D-059), the keyboard driving
the frame with one slot of undo (T-048, D-060), and placing the video picture itself
(T-049, D-061). The audit that closed the pass found six defects and fixed all of
them, the sharpest being that the page held the clip's own placement by reference, so
the first nudge edited the record it was about to be compared against and the clip
could never be called stale.

---

## 2026-08-25, forty second pass

### The clip says when it is older than the form above it

T-045, to D-056. Reported as "I have inserted a GIF, but that is not appearing
anywhere on the actual video". Nothing was broken: the clip that had been posted was
made before the GIF was placed. The log has it exactly, a render at 19:43 whose
sidecar records `"stickers": []`, that clip posted at 19:53, and the GIF placed after.
Extracting frames from the clip made afterwards shows both stickers present and the
GIF animating.

The page did say so, in the wrong room. The Stickers panel reads "Make the clip again
to draw these into it"; Post it is a different card with its own four buttons, and
nothing there knew. The notice now sits directly above Load, Send, Download and
Delete, naming what has changed since the clip was made: the words, the stickers, the
waveform, the mode. Not the link or the window, because pasting the next link with a
finished clip still on show is ordinary work.

It is a comparison against the clip's own sidecar rather than another dirty flag, and
it warns rather than blocks: one press explains and the second goes ahead.

### Stickers moved in with the form, and Make the clip moved in with the result

T-045, to D-057. Asked for directly. Everything that goes in is on the left now,
stickers included, and everything that comes out is on the right, the button that
makes it included. Two couplings crossed a boundary in the move and neither would
have raised anything: a submit button outside its form submits nothing without
`form=`, and Stickers had to go beside the form rather than into it, because Enter in
its search box would otherwise have started a render.

The phone keeps the order it had. Both column wrappers dissolve to `display: contents`
below 901px so `order` can place each panel individually, giving form, preview,
stickers, post, recent: the shelf stays under the frame it decorates.

### A second take of a video clip was labelled an artwork card

Found while reading the badge on a clip that was plainly video. `naming` writes the
video marker before the collision suffix, so a second take ends in `_video-2` and
therefore in neither one alone. `endswith("_video")` was False and
`removesuffix("_video")` did nothing, so such a clip was called an artwork card and
lost its window in the panel. Every clip made after the first on 2026-08-25 was
affected.

There were already tests for a collision suffix and for video mode, and none for the
pair, which is exactly the gap it fell through. The mode now comes from the sidecar,
which is the job that was actually run, and the window's pattern allows for both
tails. A first attempt stripped the tail before matching and ate the window's own end
value, losing the window on every clip that had no suffix at all; the four shapes are
tested together now so that fixing one cannot break another.

---

## 2026-08-25, forty first pass

### A cross on each Recent tile, to throw a variant away

T-044, to D-055. Asked over a screenshot with a box drawn on a tile's corner:
"please introduce a close button (cross-mark) here, so that I can delete those
variants that I don't want."

The server needed nothing. `/api/clip/delete` has existed since T-016, deletes the
whole file group rather than the mp4 alone, and refuses while WhatsApp is being
driven. What was missing was a way to reach it: the only route to Delete was to load
a clip into the player first, three presses away from the strip where takes are
actually compared against each other.

It asks twice rather than opening a dialog, the same rule as the Delete button under
the player: a dialog is dismissed by habit and a control that has visibly changed its
mind is not. The cross becomes a filled "Delete?" pill, forgets the question after
four seconds, and only one tile can be asking at a time. Which tile that is lives in
a variable rather than in the DOM, because the strip repaints itself whenever the
clip list changes and the element that was asked is not the element that answers.

The tile stopped being a `<button>` to make room for it. A button nested in a button
is invalid and no browser says so: the parser unnests them into siblings, laying the
cross out beside the tile rather than on it. Three traps of that kind are now tests
in `tests/test_recent_strip.py`, the other two being a `#fff` mark on a `--danger`
fill, which is readable in one palette and not the other, and a touch target that a
mouse reaches and a thumb does not.

Drawn always rather than revealed on hover, because a phone has no hover, with a
hairline ring so the disc does not vanish into the dark top of a thumbnail, and a
transparent hit area grown to 44 pixels around a 24 pixel mark. The "saved on this
device" tick moved to the other corner, which the cross now wants.

### Corrections found auditing the pass before it

`render.detect_source_crop` had no callers left once `source_picture` returned the
crop and the size together, so it is gone. `preview_jpeg` reached the sidecar through
`clip_json(stem)["job"]`, which can be `None`, turning a clean 404 into a 500; it uses
`job_of`, the accessor built for it. A comment claimed the command line takes the
unmeasured path through `render_video_clip`, which it does not: `cli.py` goes through
`pipeline.produce`, and only the tests land there.

---

## 2026-08-25, fortieth pass

### The top text hangs off the picture, not off WhatsApp's header

T-043, to D-054. Looking at the field built an hour earlier, the owner asked the
right question: "should it start alignment from the bottom? This way our probability
of collision with header elements will decrease." Measured on his own clip: two
lines at 260 to 348, the picture starting at 626. Thirty pixels of clearance from the
header band, and 278 pixels of nothing between the words and the picture they belong
to. Every other block above something in this layout is anchored by its bottom for
exactly that reason; this was the one that was not.

The obstacle was that nothing in Python knew where the picture was. It was decided at
render time by an ffmpeg expression from a source shape only ffmpeg had looked at, and
a coordinate the renderer keeps to itself cannot be drawn against. So the arithmetic
moved: `render.picture_rect` fits the source into the band and returns an exact
rectangle, and the filter graph is handed numbers instead of an expression. That is a
better shape anyway, because an expression cannot be unit tested, only rendered and
measured. A test now asserts the rectangle Python computes is the one ffmpeg paints,
at five aspect ratios, which is the seam this creates.

On that clip the block moves from 260..348 to 508..596: 278 pixels of clearance
instead of 30. The crop probe already scanned three frames and now returns the size it
found as well, so the rectangle costs nothing extra. The clip's sidecar records where
the frames landed, because the live word preview draws over a still of them and cannot
measure it; a clip made before that was recorded gets the old fixed position, which is
where its own text actually is.

---

## 2026-08-25, thirty ninth pass

### The page opens in the browser that holds the rest of the session

T-040, to D-051. Yesterday's label tab said "this session is on 8765" in one Chrome
window while the thing on 8765 opened in a different one, because `webbrowser.open`
asks the desktop for its default browser. The page is now Chrome's second URL,
between the label and WhatsApp Web, so one window holds what the session is, what it
does and what it posts through. The label stays first, so the window title still
names the port.

A browser that was already running never saw a command line, so it is asked for the
tab over the debug protocol instead, with `PUT /json/new`. If there is no browser to
start, or the tab is refused, the page opens in the default browser exactly as
before: it has to open somewhere.

### The label above the card is drawn in video mode too

T-041, to D-052. Asked over a screenshot with a sentence typed into the box and
nothing on the preview. The footer already worked in both modes. The label did not:
`build_overlay` passed `eyebrow_top=None` and the drawing code skips it when that is
None, so video mode took the sentence and threw it away, with no error and no note.

It now sits one `EYEBROW_GAP` above the title, the same gap it would have used above
a card. The frames give up the room for it, and only when there is one to draw: with
a label the picture's floor rises from 1244 to 1174, without one it does not move.
Reserving 70 pixels of picture on every clip for a line that is off by default would
be the wrong trade almost every time. The field's wording follows the mode now,
"Label above the card" and "Label above the words", because the old wording was part
of why this read as card-only.

**And it is wrapped, which drawing it alone was not enough to fix.** The first
sentence typed into the box, 91 characters, came out 1989 pixels wide in a 1080 pixel
frame with 454 falling off each side: reported as "still not able to see anything",
and that is what it looked like. The eyebrow was the one line of this layout never
wrapped, because `NOW PLAYING` never needed it. It wraps to three lines at most now,
loses its letterspacing past 28 characters, where tracking is only noise and extra
width, and is anchored by its bottom so a second line grows upwards and a single line
lands exactly where it always did. Card mode ellipsises into the room above the card;
video mode moves the frames instead, 70 pixels for one line and 110 for two.

**The second line and the footer were the same bug**, reported the same afternoon as
"text wrap is happening here, but not here". Both were single unwrapped `draw.text`
calls: an ordinary channel name measured 1253 pixels in a 1080 pixel frame. They wrap
now, taking what is left of the block after the one above them, up to two lines each,
ellipsised beyond that. The footer keeps one line back for itself while the channel is
measured. The title is never shortened to make room for either.

### Text at the top

T-042, to D-053. The band between WhatsApp's own header and the top of the video was
empty air: the frames are centred, so there is room above them, and every word this
tool drew lived at the bottom. There is a **Text at the top** field now, its own box
rather than a placement for the label, so a clip can carry both a hook at the top and
the line that introduces the title at the bottom.

The frames give up room at the top the way they already do at the bottom, and neither
end moves unless the words ask it to. Measured on a square source: it started at 230
and now stops at 388 with two lines of top text above it. In card mode the label above
the card is anchored to the card and goes first, and the top text takes what is left,
which with an unusually square artwork is nothing.

**Known and deliberate:** typing a label after a clip exists moves the frames, and
the live word preview draws over the still that clip was rendered with. So the
preview shows the label over the picture until you make the clip again, which is the
same "the clip still has the old ones" the band above it already says.

---

## 2026-08-24, thirty eighth pass

### The browser now says which port this session is on

To D-050. The port was printed to a terminal that is behind three other windows by
the time you want it, on a machine running several Chromes on several debug ports.
The browser this tool starts now opens one extra tab first, a page whose `<title>`
is `● 8765 · wastatus`, so the window title and the task bar entry carry the answer.
The body names the page URL, the tailnet URL, the Chrome debug port, the posting
profile and the output folder.

A file in `~/.cache/wastatus` rather than a route on the server, because a label
that turns into a connection error when you stop the tool is not a label.
`WASTATUS_CACHE_DIR` moves it. A cache that cannot be written is a warning, never a
browser that failed to start.

### Video frames stop being written on by the title

To D-049, from the owner's own observation. Card mode anchors the card above the
title and is safe by construction. Video mode centred the frames in the whole frame
with an expression that knew nothing about the words, which is safe only down to
5:3: a 4:3 source painted 81 pixels into the title, a square one 216.

The overlay is now centred no lower than 40 pixels above the title, and a source too
tall for the band above that line is fitted to it rather than cropped, because a
margin of blurred fill is a worse picture and a crop is a wrong one. Wide sources do
not move: the clamp is a floor, so the back catalogue keeps its shape. `tests/
test_safe_zone.py` renders the real filter graph at five aspect ratios and measures
the picture it paints, because the clamp lives in an ffmpeg expression and an
expression cannot be proved right by reading it.

### The GIF service is chosen where the GIF shelf was turned on

From a screenshot: "can we have these two as radio buttons here?", with a box drawn
at the right end of the Drawings / GIFs row. They were a second row of pills below
it, wearing the same shape, the same size and the same green, which read as another
choice of equal standing when choosing a service is a detail of having chosen GIFs
at all. They are now a radio group on the right end of that row, and the selected
one is the only one in full strength text.

And "make this less obvious", of the credit. It cannot go away: both providers
require a visible mark, and KLIPY additionally requires the search box to say
"Search KLIPY", which is why the placeholder reads the way it does. What it can stop
doing is taking a line of its own at the foot of four stacked grey lines, so it now
rides on the right end of the hint line at 10px and .55 opacity, and the footnote
asterisk is gone. That is the floor, not a preference.

### Stickers can be placed again after a clip is made

Making the clip put the draggable layer away, on purpose: the stickers are in the
video's pixels by then, exactly as the words are, and handles floating over pixels
that cannot move are a lie. But there was no way back to them either, short of
adding a sticker you did not want. There is now a **Place them again** button, and
the hint says why they went quiet. It does not claim the clip is stale until
something is actually moved.

---

## 2026-08-22, thirty seventh pass

### The words are previewed as you type

T-036, to D-048. Asked as "how to refresh the preview alone without regenerating
fully?", and the answer turned out to be worth building.

**Measured first, and the obvious idea was wrong.** From the owner's own
`runs.jsonl`, a 90 second video clip is probe 1.4s, download 12.3s, render 52.5s.
Caching the download would have saved under a fifth. The render is the wall.

**But no render is needed to see the words.** Both modes draw their text with
Pillow already: `build_card` in 0.86s, `build_overlay` in 0.10s. So the picture
follows your typing and the file waits for the button, and because it is the same
function the render calls, the preview cannot drift from the clip.

Each clip now keeps what its mode needs to draw over. A card keeps its artwork, 74
kB. A video keeps one frame with the blurred fill applied and nothing of ours on it,
640 kB, written by the same filter chain the clip uses minus the overlay. Both are
pruned with the clip. The still is a second ffmpeg call rather than a second output
of the render's own graph, so a preview that cannot be written never takes a clip
with it.

Sent at 720 pixels as JPEG: full size PNG measured 1254 kB for a card, redrawn
every time typing stops, on a page a phone reads over a tailnet. It measures 73 kB.

A band across the top of the preview says "Preview of the words. The clip still has
the old ones", and pressing play shows the actual video. A preview that quietly
replaced the clip would be a lie about the file on disk.

**What it does not show:** a card clip's waveform, which ffmpeg draws from the
audio and a still cannot have. And nothing at all before a clip exists.

---

## 2026-08-22, thirty sixth pass

### The words on the card stop following the last video

T-035, to D-046. Paste a new link, press the button, and the clip came out under the
previous song's title. A guard for this existed and missed three ways: it compared
against the clip on screen, which is null after a reload while the words have
already been restored from storage; it compared raw strings, so one song in two
spellings looked like two songs; and it cleared the title and the channel but not
the footer or the eyebrow. The words now carry the video they were derived for, that
survives a reload, and it is checked again at the press, where being wrong costs a
30 to 66 second render.

### The desktop GIF panel, reviewed

T-034, to D-047. Five things off one screenshot.

The sentence in an empty shelf was running **one word per line**, because `.shelf` is
a grid of 52 pixel columns and the message was an ordinary grid item sitting inside
one of them. Wrong since the shelf became a grid, and now spanning.

Thumbnails were too small to judge, so the cells grew. That made them **worse**:
a 127 pixel image upscaled into a 172 pixel box. Both providers were measured
properly for the first time and the browser now asks for a preview that suits its
own cells. KLIPY `sm` is 220x157 at 376 kB against `xs` at 127x90 and 134 kB; GIPHY's
`fixed_width_downsampled` is 200x190 at 121 kB, twice the resolution of
`fixed_width_small` for a third more bytes, and the bargain of the two. The phone
keeps the cheap one, because it reads this page over a tailnet.

A **GIPHY/KLIPY chooser** now sits under the Drawings/GIFs toggle on wide screens.
It switches for the session and never writes `.env`: that file holds the API keys,
and nothing reachable from a web request should be able to rewrite it.

The phone's paste box is gone from the desktop view. It is `contenteditable` for one
reason, that a phone keyboard offers its GIF tab only against a rich text target,
and with a mouse there is nothing there to reach for. The hint below it stays,
because Ctrl-V anywhere on the page still works.

### Found while auditing: the tests were writing into the real logs

Running the suite appended thirteen fake run records to `logs/runs.jsonl` and, once
Chrome's output started being captured, four launch headers to `logs/chrome.log`.
Nobody noticed because neither file is in git, but `runs.jsonl` is what you read to
answer which extraction strategy has been working lately, and it was being seeded
with runs against `https://youtu.be/abc` that failed with `ZeroDivisionError`.

Found by copying both files, running the suite, and diffing. Now one autouse guard
in `tests/conftest.py` points every test's logging at a temporary directory, and a
test asserts the suite's log directory is not the project's.

**The existing records were left alone.** They are identifiable by that URL, and
deleting from somebody's logs is not a thing to do without asking.

### Chrome's own output is kept

Proposed after a browser this tool started exited on its own and left nothing to
read. It now goes to `logs/chrome.log`, truncated at 2 MB rather than rotated,
because the interesting part is always the last launch.

It earns its place immediately. Reproduced deliberately, a second browser on a busy
port writes exactly this:

```
[ERROR:net/socket/socket_posix.cc:175] bind() failed: Address already in use (98)
DevTools listening on ws://[::1]:9241/devtools/browser/...
```

Which is the whole of D-045's half open case, in two lines, in a file.

---

## 2026-08-22, thirty fifth pass

### One command to get to work

T-032, built to D-044. `./wastatus.sh` with no arguments opens the page. Three
settings in `.env` answer the flags that used to be retyped every day:
`WASTATUS_ALSO_ON=tailscale` binds the tailnet, `WASTATUS_START_BROWSER=1` starts a
Chrome with WhatsApp Web if none is running, and `WASTATUS_CDP_PORTS=9230-9235` moves
the debug port search off ports another program owns.

**This reverses a decision, and says so.** D-027 rejected exactly this on 2026-08-20,
on the grounds that a remembered flag means "a machine that quietly reopens a posting
surface every time it boots". It does not. Nothing in `.env` starts anything; the
file is read when somebody runs the command and never otherwise, and D-028's refusal
of an autostart service is untouched. The real objection was to autostart all along.
What survives is the part that was right: the setting is empty by default, the
startup output still says in words what the second address means, and `--also-on ""`
still returns one run to loopback.

**A browser already open on the posting profile is adopted, not duplicated.** Chrome
hands a second launch on one profile to the running instance and exits, ignoring the
new `--remote-debugging-port` completely, so the naive version opens a window and
opens no port. Measured on the owner's machine: with the search moved to 9230-9235
and a wastatus Chrome already up on 9222, it found that one and used it.

### The tool now says whose browser is on the port

T-031, built to D-045. This is the afternoon lost on 2026-08-20, closed properly.

The message was `Chrome is on port 9225 but no WhatsApp Web tab is open in it`. True,
and useless: 9225 belonged to an IDE's Chrome and the owner's logged in WhatsApp was
somewhere else entirely. It now reads `That one is chrome, profile
antigravity-chrome-profile-someone (pid 151793)`, which is the sentence that
ends the confusion rather than starting it.

Underneath it was a second fault worth naming. **Chrome, given a debug port something
else already holds, prints `bind() failed: Address already in use (98)`, carries on,
binds IPv6 only, and then prints `DevTools listening on ws://[::1]:9225`** — a line
that reads like success. Everything here asks `http://127.0.0.1`, so it reached the
other browser. That case now says `port N is only half open` and names who took it.

**And a bug inside the fix, kept because it will catch the next person.** Chrome
rewrites its own argv into one space separated string, so `/proc/PID/cmdline` does
not hold the NUL separators every other process puts there. The first version split
on NUL, saw one enormous token, and found nothing on a machine where two debug
browsers were plainly running. Both shapes are handled and both are tested.

### Two Chrome facts written down, having cost an afternoon each

**Your everyday Chrome profile can never be used**, measured against
`~/.config/google-chrome` on 2026-08-22: `DevTools remote debugging requires a
non-default data directory`, and no port opens. Chrome 136 and later refuse it by
design, no flag gets round it, and the switch cannot be added to a browser that is
already running. Now in RUNBOOK's new **Chrome will not open its debug port**, in
LOCAL_SETUP where the command is, and in LIMITATIONS.

### Logging says what broke, on which versions

Every process writes a stamp before its first run: python, yt-dlp, ffmpeg and Chrome
versions, the debug ports in play, the git revision and whether the tree is modified,
and the **names** of the settings `.env` supplied. Names, never values, and a test
holds that line.

Posting from the page now writes its own `runs.jsonl` record, with the port and
browser it went through. Until now that file answered "when did this go out" for the
command line route and not for the one actually used.

### Instagram, researched and not started

T-033, written up in [docs/instagram.md](docs/instagram.md). The finding that shapes
it: your own posts and other people's are not the same problem. No official endpoint,
at any tier, returns an arbitrary public account's media, and yt-dlp's anonymous path
is **measured dead** as of today, returning the same empty media response for a
shortcode that cannot exist. Five questions for the owner are in TASKS T-033.

---

## 2026-08-21, thirty fourth pass

### A GIF picker in the page, off unless you switch it on

T-029, built to D-043. The Stickers card grows a **Drawings / GIFs** toggle when
`.env` names a provider and its key. Type, pick, and it lands on the frame like any
other sticker.

**Two providers, not one.** GIPHY and KLIPY are both built, behind one seam, and
`.env` chooses in a word. KLIPY was not in the research and fits better than the
provider that was recommended: its `xs` rendition is 90 pixels, almost exactly what
the thumbnail cache already uses, its `md` is 640 at about 200 kB, and its only
mandatory attribution is the words in the search box rather than a mark on screen.
Tenor is not a route at all any more, and Pixabay's API has no GIF search whatever
its website shows.

**It is off by default and it is a file you can delete.** This is the only part of
the tool that talks to anybody but YouTube, so that is a switch rather than a
comment: no provider or no key means no toggle in the page, 404 on both routes, and
nothing asked of anyone outside this machine. What the feature costs when it is on
is stated plainly in SECURITY: your search terms leave, and nothing else does.

**Nothing the browser names is ever fetched.** A pick sends an id from a search this
server made, and the address is looked up here. `fetch` refuses anything that is not
`https` and stops reading at the sticker ceiling whatever the provider's byte count
claims. Every thumbnail is proxied, because the phone reads this page over the
tailnet and a linked thumbnail would put the phone in touch with GIPHY.

**Picked GIFs are kept, and pruned.** A third namespace, `gif:`, beside `mine`
rather than in it: an upload is something you decided to keep, a picked GIF is
something you passed through. Twenty are kept, the same number as `keep_last` and
for the same reason. Pruning never touches uploads.

The rating default is **pg** rather than **g**, because the clips are songs and
general video rather than only devotional material and `g` strips out ordinary
celebration and reaction GIFs. A value that is not one of the four falls back rather
than being passed through: a typo quietly meaning `off` is the wrong way for a safety
setting to be wrong.

**One bug shipped and was caught by counting rather than reading.** The first pass
rendered thirty shelf cells and every image was a 403, because `/api/gif` was not in
the list of routes that accept the token as a `t=` query parameter and an `<img>`
cannot send a header. It looked exactly like a provider outage. Found with
`naturalWidth` in a real browser, fixed, and pinned by a test.

Also fixed on the way: `prune_gifs` had its keep count as a default argument, which
binds once at import and ignored anybody who changed it afterwards, and the newest
first sort used whole seconds where several files land inside one tick.

617 passed, 7 skipped. 359 links across 21 documents, 0 broken.

---

## 2026-08-21, thirty third pass

### Framing the video: researched, and closed without building

The owner read T-030 and closed it. The blurred fill already does the job on his
material, and the measurement that settled it was that going from 16:9 to 9:16 throws
away about **68 per cent of the width**. That is a large amount of a film song's frame
to lose for a framing choice, and the fill keeps all of it.

The research stays in full rather than being deleted with the task. A closed question
with its reasoning attached is worth more than a closed question, and if the material
ever changes, route A is still two hours and route C still a day and a half, with
nothing left to re-decide.

**One thing worth keeping out of it regardless:** the pipeline deletes its work
directory at the end of every render, so every re-run pays 5 to 13 seconds to download
a section it already had. That is true whether or not anything is ever cropped, and it
is cheap to change if a re-run ever feels slow.

---

## 2026-08-21, thirty second pass

### The Upload dialog stops hiding GIFs

`accept` on the sticker file input listed png, webp and jpeg. That list predates
animated stickers, T-019, and was never widened, so the file dialog hid every `.gif`
and the only way in was to switch the picker to "All files". Nothing else was wrong:
the page never filtered by type, and the server took a GIF and marked it `moving`
when one reached it, which was measured before changing anything.

`image/gif` is in the list now. The test that guards it reads the `accept` attribute
out of `index.html` and, for every type it finds, proves `save_upload` can store one,
so the picker and the server cannot drift apart again. It fails on the old list.

Also written down: Chrome's **Copy image** flattens a GIF to a still PNG, which is
not this tool's doing and cost some confusion. Copy or save the file instead.

### A GIF picker in the page, researched

Both majors refuse without a key, probed with no key and a generic term: Tenor
answers **403 unregistered callers**, GIPHY **401**. Wikimedia Commons needs no key
and is not a substitute, one GIF in five results and encyclopaedic ones at that.

Most of the machinery already exists, the shelf, the cached thumbnail route and
`save_upload` from a data url, so it is about a day. What it really costs is a
credential this tool has never needed and a third party that would see what the owner
searches for, which is the first thing other than YouTube this machine would talk to.
Written up as T-029 with four routes and a recommendation, for the owner to decide.

---

## 2026-08-21, thirty first pass

### A playlist link no longer puts a dead link on a Status

Asked to find out whether YouTube Music and Spotify links could work. YouTube Music
already did, and needs nothing: there is no URL validation anywhere in this tool, the
link goes from the form to yt-dlp untouched, and `music.youtube.com` is the same
extractor. It is in fact the better link to paste, because a `- Topic` upload carries
the real artist where the channel says only `Release - Topic`.

The defect was next door. A **playlist** link was accepted, and `probe` took the
playlist's id as the video id, so `watch_url` came out as `https://youtu.be/PL...`,
which resolves to nothing, `duration` came back 0.0, and that url is the caption. A
pasted playlist would have put a dead link on a real Status.

It is refused at `probe` now, naming what was pasted, how many tracks it holds, and
what to paste instead. Taking the first track was considered and rejected: which song
somebody meant is a guess, and this tool does not guess at what it is about to
publish. Nothing that worked before was narrowed, because `--no-playlist` was already
reducing `watch?v=X&list=Y` to the single video. T-027.

### Spotify, researched and closed

Spotify audio cannot be fetched at all: yt-dlp refuses on sight with `[DRM]`. The only
possible shape was metadata then match on YouTube, and matching was measured against
the owner's own library first. Searching `Project Samskriti Veyuru Tholipangan`
returns the **wrong** track first, **one second** from the right duration, so a length
filter does not rescue it; the title alone, which is all Spotify's credential-free
oEmbed gives, returns nothing right in the top three. Tamil devotional and film music
is full of the same composition recorded by different artists at similar lengths,
which is exactly where title matching is weakest.

Closed by the owner as not worth the work. The research stays in T-028 so the next
person asking gets the measurements rather than the question.

---

## 2026-08-21, thirtieth pass

### Stickers carry their own controls now

T-023, built to the design agreed as D-038 the day before. A selected sticker wears
a cross at the top right that removes it, and where there is a mouse a grip at the
bottom right to resize and a handle on a short stem above it to turn. A touch screen
gets the cross and nothing else, because a default sticker is 76 pixels to hit and
two touch targets need 88 pixels between them; pinch and twist already do the other
two jobs there, so the sliders go on a phone and stay on a laptop.

Resize and rotate are measured from the sticker's centre rather than the corner being
held, so both work at any angle without undoing the rotation first, and rotation goes
through the same `settle` as the two finger twist, so square is square either way.

**The 1.4 second fade is gone**, which is the part that made this half a day rather
than an afternoon. A handle that fades is a handle you cannot click, so D-034's one
state became two: selected, which lasts, and nothing selected, which is the resting
frame D-034 was written to protect. Click a sticker to select it, click the frame
background to put it down.

Everything D-033 measured on 2026-08-19 was re-measured with real pointer and touch
input rather than by calling the functions: pinch 0.200 to 0.344, twist 0 to 40
degrees, drag unchanged, sliders unchanged, resize grip 0.200 to 0.428 with the
centre unmoved, rotate stem landing exactly on 90.

Two things that cost time and are now written into TESTING: headless Chrome reports
**neither** a fine nor a coarse pointer, so a media query written as "not a mouse"
matches a desktop browser and quietly removes its controls; and at 412 pixels wide
the preview sits about 1000 pixels down the page, so input dispatched at its
coordinates hits nothing until the frame is scrolled into view.

### A rename is noticed before a post, not during one

T-026, route B. `check_controls` opens the Add Status menu once per server run, looks
for both Status choices, and closes it again. The page asks when a clip first becomes
postable, which is early enough to matter and cheap enough to be free.

It never runs on the fifteen second poll, which was route A's flaw: that would open
and close a menu under your hands four times a minute. It refuses to look while a
composer is open, because that composer is holding a clip you are about to send. A
bad answer rides on the existing **WhatsApp Web** health row rather than a new one,
and it names what the menu actually offers, so the fix is one line in a list rather
than an investigation. Against the live tab: 2.2 seconds, menu put back.

---

## 2026-08-20, twenty ninth pass

### WhatsApp renamed two controls and every post stopped

`Photo and video` became `Photos & videos`, `Text status` became `Text`, and both
moved behind an **Add Status** button that has to be pressed before either exists.
The tool matched those labels by exact string equality, so it found neither and said
`could not find a control labelled 'Photo and video'`, which was true and told nobody
anything. The strings had been in the file, untouched, since the first commit that
could post. Last good post **2026-08-19 22:53**, first failure **2026-08-20 19:42**;
nothing here changed in between.

It surfaced the way it did because the reboot restarted Chrome, which fetched a newer
build of WhatsApp Web. The tab had been serving the older one from memory.

Labels are now matched on **words** rather than on exact strings: `Photos & videos`
and `Photo and video` both reduce to `photo video`, so this rename would not have
broken anything. Each control has a list of spellings, and `open_status_menu` asks
whether the choice is already visible before pressing **Add Status**, so it works on
either build. When a control really has gone, the error now names the file and the
list to widen. D-041, and RUNBOOK's **Posting failed** step 3 prints what WhatsApp
calls them today.

### A refused POST was corrupting the connection behind it

Separately, and at the same time, the desktop page showed `bad or missing token` on
everything. That part was working as designed: the tab predated the 19:08 restart and
the token is minted per process. What was not working was the log, which filled with

```
501 Unsupported method ('{"url":"https://www.youtube.com/watch?v=..."}POST')
```

`do_POST` answered 403 without reading the request body. The connection is
keep-alive, so the body stayed in the socket and the next request line was parsed out
of the middle of it. The body is now read before anything is decided. D-042, and
`TestKeepAlive` fails without the fix.

The page also says what a 403 means now: **"this page is older than the server.
Reload it"**, rather than repeating the server's `bad or missing token`, which reads
as a broken tool rather than a stale tab.

### T-025 built, route A

A fourth row in the health panel, `another device`. Green with the address to open on
the phone when `--also-on tailscale` was passed, grey and reading **this laptop only**
when it was not. The grey row is not counted as a failing check, so the chip still
says **All set**: loopback only is the default, not a fault. Verified in both states.

### Verified rather than assumed

The composer was opened with a real 10.2 MB clip and its caption, from the phone
layout over the tailnet, and **not sent**. Make and Stop were pressed from the same
layout; Stop wrote nothing and `out/` stayed at 20 clips. 543 passed, 7 skipped.

---

## 2026-08-20, twenty eighth pass

### A reboot took the phone route away, and the documents did not say it would

- **Nothing was broken.** `--also-on tailscale` opens its second socket for the length
  of the process and is remembered nowhere, which is D-027 working as intended. After
  a reboot the owner followed **Start the page** literally, got the plain command,
  and the page bound loopback only. The phone had a refused connection and no cause
- **Diagnosed rather than guessed**: one socket on `127.0.0.1:8765`, the tailnet
  address answering `000`, and `logs/serve.out` showing an `Also on` line on every
  earlier run and none on that one. Tailscale itself was fine throughout, a direct
  `tailscale ping` to the phone at 294 ms with no relay in it
- **Restarted with the flag and verified**: both sockets on one process, both
  addresses 200, `app.js` and `app.css` 200 over the tailnet, a tokenless
  `/api/state` still refused with 403, ffmpeg and provider true, WhatsApp ready

### The fix is the document, not the default

- **LOCAL_SETUP** step 3 now carries both commands, the phone one with its real
  output, and says in as many words that the plain command is loopback only, that the
  flag is not remembered, and that the `Also on` line is how you know you have it.
  Three rows added to the troubleshooting table
- **RUNBOOK** gains three symptom rows: the refused connection, the case where the
  `Also on` line is present and the phone still cannot reach it, and the startup
  refusal when Tailscale is absent
- **D-027 amended** with why remembering the flag was rejected a second time: a
  machine that reopens a posting surface at every boot is the thing D-028 already
  refuses. **README, CONTEXT_MAP, TESTING, PLAYBOOK, ARCHITECTURE, SECURITY** and the
  hosting notes say the same fact where each of them states it. TESTING gains the two
  commands that separate a missing flag from a Tailscale fault, and SECURITY says
  plainly that off by default means off at every start
- **LIMITATIONS Table LI-7** records the finding, **MEMORY Table ME-9** the
  measurements, and **T-025** proposes the one code change worth making: a fourth,
  grey health row naming the address, or saying "this laptop only" when there is none.
  Three routes, costs and a recommendation; it is the owner's call

## 2026-08-20, twenty seventh pass

### Five tasks closed, and two of them changed what the tool knows

- **T-014: WhatsApp's media ceiling is 10 MiB**, 10,485,760 bytes, bisected against
  the live composer with five 90 second probes that differed only in size. 10,452,278
  was accepted and 10,519,352 was refused, 33 kB either side of the line. Not the
  16 MB the platform documents, and not a length limit
- **The encoder budget goes from 9.5 MB to 10 MB**, not to the ceiling, because the
  budget sets a maxrate and the encoder overshoots it by about 2 percent, measured
  twice. A 90 second clip goes from about 716 to 761 kbit/s
- **A clip that lands over the line now says so**, in the log and on screen. WhatsApp
  will not: it takes the file and never opens its editor, which reads as a broken tool
  rather than a refused file
- **T-018: video mode is 720p again, when YouTube offers it.** Not through
  `web_safari`, which still returns four storyboards, and not through DASH, which
  still answers ffmpeg with 403, but through the **default** client's HLS renditions,
  which carry their own audio and can be section downloaded. A real run cut
  **1280x720**, 12.08 seconds, 1.8 MB. Whether a video has them is the video's own
  property, so the ladder tries and falls through to 360p in about 2 seconds
- **T-017: an output name is claimed now, not checked.** `naming.reserve_stem` creates
  the `.part` file with `O_EXCL`, so two renders of the same song and window cannot
  agree on one name. Eight threads asking in the same instant get eight names, and the
  test that proves it loses a file against the old code
- **T-008: a title that is entirely noise no longer strips to a blank line.**
  `(Official Video)` keeps the raw title, and a title that romanises to nothing at all
  falls back to the channel
- **T-009: the dedupe threshold is untunable, which is worth knowing.** A real
  duplicate scores 0.846 and two genuinely different words score 0.900, so no single
  number gets both right. 0.85 stays, keeping the safer failure, and twelve pairs are
  pinned with their measured ratios

### Documentation

D-017 and D-023 amended with both measurements, openings included rather than only
their feet, plus MEMORY's Table ME-8 and the size and resolution claims corrected in
DOMAIN, ARCHITECTURE, RUNBOOK, LIMITATIONS, README, AGENTS, CONTEXT_MAP and the
extraction notes. Two LIMITATIONS rows are struck through as fixed rather than
deleted: the unmapped ceiling and the name race. TESTING gains the composer as an
instrument, with the two rules that make it trustworthy, run a control and cancel
between probes, and names the pair of constants that now have to be checked against
each other before an encoder change.

## 2026-08-20, twenty sixth pass

### This repository is now fit to be public, and the history says so too

The owner answered the four questions in [TASKS.md](TASKS.md) Table T22-2, recorded as
[DECISIONS.md](DECISIONS.md) D-040. **T-022 is done.** Making it public is one switch
on GitHub and it is his to flip.

- **MIT, held by PalWorks**, the name the GitHub account already carries
- **`wastatus/post.py` is published.** It drives a browser the owner is already logged
  into and does nothing an unofficial protocol library would do. A repository that hid
  its most consequential file would teach a reader the wrong thing about it, and
  SECURITY.md now opens by naming what that file can do
- **MEMORY.md is split, not dropped.** The few rows that described the owner rather
  than the tool are in `MEMORY.private.md`, which is ignored by git and named in
  AGENTS.md's never-commit list. Both halves carry the rule that keeps the split
  honest: private if a stranger would learn about **him**, public if about the **tool**
- **The history was rewritten** with `git filter-repo`, replacing the same values in
  every commit, in file contents and in commit messages. Without it the working tree
  scrub was decorative: the values sat in 31 commits, one `git log` away. Every hash
  changed, which costs nothing here

### Deliberately not scrubbed, and the reasons are written down

- **Device models.** A Galaxy M30 and a OnePlus 11 are named throughout, because a
  phone model identifies nobody and a measurement reads better with the real hardware
  in it. Their **addresses** are what went
- **The test fixtures.** The typography and padding bar rules were measured against one
  real title and one real thumbnail, and a fixture renamed to something that was never
  measured proves nothing. The prose no longer names it; the evidence still does

## 2026-08-20, twenty fifth pass

### Groundwork for making this repository public

The owner intends to open it to everybody. Nothing here changes what the tool does;
it changes what a stranger would find. [TASKS.md](TASKS.md) T-022.

- **There was never a secret in here**, and the audit says so plainly: the page's
  token is made per process and dies with the server, and there is no API key
  anywhere. What was in here was the owner's own details
- **27 personal values replaced across eight documents.** His tailnet address, his
  laptop and phone on his home network, his home directory and his machine name are
  now `100.x.y.z`, `192.168.1.10`, `192.168.1.11`, `~` and `this-laptop`. None of the
  reasoning depended on the real ones
- **`.env` is now read at startup**, by `wastatus/env.py`, with the environment always
  winning over the file. `.env` is ignored, `.env.example` is committed and names every
  setting the tool reads with no value for any of them, and **a test keeps those two
  lists equal**, because an example file that drifts is worse than none.
  [DECISIONS.md](DECISIONS.md) D-039
- **Read in `__main__.py`, before `cli` is imported**, because settings like
  `WASTATUS_POT_PORT` are read at import time and a file read inside `main()` would be
  read too late to matter. Proven both ways
- **A LICENSE, which did not exist.** MIT. Without one, a public repository is all
  rights reserved and nobody may legally use it. **The name on it is a guess from the
  git author and needs the owner's word**
- **The font licence that was already owed.** The two committed DejaVu files are byte
  for byte identical to Debian's `fonts-dejavu-core`, so `assets/fonts/LICENSE.md`
  reproduces its Bitstream Vera licence with the MD5s that prove the claim. The README
  now credits all three: MIT, OpenMoji CC BY-SA 4.0, and this

### SECURITY.md, read with a stranger's eyes

- **An opening that names the only three things that can actually hurt someone**: the
  page hands its token to whoever loads it, Chrome's debug port is an unauthenticated
  control channel over a logged in WhatsApp session, and `--post` presses Send on a
  real account
- **Two settings that were never in Table SE-1** are in it, the sticker ceiling is
  corrected for animated uploads, and the 12 MB body cap is written down
- **Reporting rewritten for someone who is not the owner**, since "goes straight to the
  owner" is not a route a stranger has

### Still to decide, all the owner's

The name on the LICENSE, what happens to [MEMORY.md](MEMORY.md), whether to rewrite the
history that still holds those 27 values, and whether to publish the posting path at
all. Table T22-2 has the options and a recommendation for each.

## 2026-08-20, twenty fourth pass

### The keyboard question is closed, and the answer is about browsers

The owner ran the diagnostic on his OnePlus 11, which has Gboard, and got the same
answer the Galaxy M30 gave with Samsung Keypad.

- **Chrome gave nothing**, from the sticker card's ordinary field and from the picture
  box alike. **Firefox worked**, from the box
- So the keyboard is not what decides, on two phones and two keyboards. The **browser**
  is, and nothing in the page can change that: Chrome refuses before the page is told
  anything. [DECISIONS.md](DECISIONS.md) D-036
- **That it only works from the box is the design.** A plain text field tells the
  keyboard it accepts text, so the GIF button greys out. Moving the box would not
  change Chrome's answer
- **T-019 is done.** [TASKS.md](TASKS.md) **T-024** now holds the open question that
  came out of it, which is what to do for Chrome, with three routes costed and one
  decision waiting on the owner

### Decided

- **Route A for Chrome:** do the GIF step in Firefox. It costs nothing and is proven on
  both phones. One measurement is still worth taking when a phone is next on the cable,
  which is whether Chrome's own save-a-picture menu yields a real animated `.gif`; if it
  does, Chrome gets a route with no code at all. [TASKS.md](TASKS.md) T-024
- **The README says so where a reader meets GIFs**, rather than only in LIMITATIONS

### Removed

- **`/paste-test.html`**, the diagnostic. Both phones have been through it, so it has
  no work left. It is in this repository's history if the question reopens

## 2026-08-20, twenty third pass

### Tested on the phone it is for, over USB, for the first time

The owner connected his Galaxy M30 with USB debugging on, so the page could be driven
on the phone the same way it is driven here. Everything below is measured on that
phone rather than reasoned about from the laptop.

- **Picking a GIF from the phone keyboard works in Firefox and is refused by Chrome.**
  Chrome 151 answers with a toast, "Can't enter this content here", and nothing
  reaches the page or the clipboard. Firefox 150 inserts the picture into the box as
  a `data:image/gif` image, with `files=[]` on the paste event
- **That is exactly the route the box was built for.** The whole path then ran on the
  real page: the GIF became a sticker, appeared first on the shelf with its "moves"
  marker, and sat animating on a real clip's frame
- **The keyboard's GIF button is greyed out against the page's ordinary fields and
  lights up against the box**, which is the `contenteditable` earning its place
- The keyboard was **Samsung Keypad**, not Gboard, and its GIF panel is GIPHY. Gboard
  on the owner's other phone is still untested. [DECISIONS.md](DECISIONS.md) D-036
- **The caption Copy button worked on the phone for the first time**, and the text was
  pasted back out with `KEYCODE_PASTE` to prove the clipboard really held it

### Fixed

- **The sticker box was invisible until focused** on that screen: a hairline dashed
  rule around pale placeholder text reads as nothing. Redrawn from the accent colour

### Decided and parked

- **D-038: handles on the sticker itself.** A delete cross top right in both views, a
  resize grip bottom right and a rotate stem above on desktop, sliders kept on desktop
  and dropped on the phone. Agreed and **not built**: it amends D-034 from the same
  day, because a box that fades cannot hold a handle, so the fade has to become a real
  selection. [TASKS.md](TASKS.md) T-023

### Documentation

- **[TASKS.md](TASKS.md) opens with a summary table**, every task on one line with its
  priority, status and what it is waiting on, done work separated from open work
- `parked` is now a status of its own: decided, written up, deliberately waiting

## 2026-08-20, twenty second pass

### Fixed: Copy did nothing at all on the phone, and said nothing about it

- **`navigator.clipboard` does not exist on the address the phone uses.** Measured:
  `http://100.x.y.z:8765` reports `isSecureContext: false` and the whole
  clipboard object is `undefined`. Only https and loopback are trustworthy origins
- The caption's **Copy** button caught that failure and set the button's `title`,
  which a phone has no way to show. So it was a dead control in the middle of the
  away route, the one actually used from the phone
- Now falls back to `document.execCommand("copy")`, which works in any context, and
  says so plainly if even that fails. Verified on the tailnet address: the tick
  appeared and the **system** clipboard really held the caption afterwards, read back
  outside the browser. [DECISIONS.md](DECISIONS.md) D-037

### Added: a box that says it can take a picture

- **A phone keyboard offers its GIF tab based on what the focused element accepts**,
  and a plain search field accepts text. So the sticker card now has a small
  `contenteditable` box to tap first: "Tap here, then pick a GIF on your keyboard"
- It handles both delivery routes, because browsers differ: a `paste` carrying a
  file, and an `<img>` inserted straight into the box, which is pulled back out and
  uploaded. It keeps nothing, ever, and typing words into it is answered rather than
  uploaded
- **`/paste-test.html`**, a diagnostic served to the phone, logging every `paste`,
  `drop`, `beforeinput` and inserted image against three kinds of target. It exists
  to answer what Gboard actually sends, which cannot be answered from this machine,
  and it should be deleted once the answer is written into D-036

### Verified

Both delivery routes drove the real page at phone width and became stickers on the
frame; typed words were answered and discarded; the box emptied itself each time. The
copy fallback was checked on the tailnet address, where there is no clipboard API at
all, and the copied text was read back out of the system clipboard. 471 offline
tests, 7 opt in.

## 2026-08-20, twenty first pass

### Added: paste a GIF in, and it moves in the clip

- **Copy a picture anywhere, paste it at the page, and it is a sticker.** On a phone
  that is the whole Gboard emoji and GIF experience without a picker of ours: open
  the GIF tab in the keyboard, pick one, paste. There is no way for a web page to
  open that picker, and no need. [DECISIONS.md](DECISIONS.md) D-036
- **An animated sticker stays animated.** It loops for the whole clip, and it drags,
  pinches and turns like any other. It is a looping input in the ffmpeg filter graph
  rather than a Pillow paste, because a paste has no time axis
- **In card mode it is laid on before the slow zoom**, so animated and pasted
  stickers travel together. Overlaying after the zoom would have left one sitting
  still while its neighbour drifted outwards in the same frame
- **Anything animated is stored as GIF**, whatever it arrived as, because this
  ffmpeg refuses an animated WebP outright while Pillow reads every format
- Pasting text into the caption box is still pasting text. A paste is only
  intercepted when it actually carries a picture, and a pasted **link** is explained
  rather than silently ignored
- The shelf marks the stickers that move, since their thumbnails are stills

### Fixed

- **An uploaded animated sticker never appeared in the picker again.** The uploads
  listing globbed `*.png` only, so a GIF was stored, placed on the frame, and then
  invisible. Found by driving the real page, not by reading the code
- **The server read whatever `Content-Length` claimed.** The largest legitimate body
  is now four times what it was, so there is a ceiling: an oversized body is drained
  and answered with 413 rather than held in memory

### Amended

- **D-024 gains one honest exception.** An animated sticker's position, size and
  rotation are exact between the preview and the clip. Its **phase** is not: a
  browser and an encoder cannot be held to the same frame of a loop

### Verified

A rotated asymmetric sticker rendered twice, once as an animated overlay and once as
a Pillow paste of the same frame: identical bounding box and identical centroid, to
the pixel, and both grew by the same factor across the clip. The pulse was confirmed
by counting lit pixels frame by frame in both card and video mode, and a sticker
placed at 0.25, 0.6 landed centred on pixel 270, 1152 of a 1080 by 1920 frame. The
paste path was driven in the real page: a GIF on the clipboard became a sticker, was
served back as `image/gif`, appeared first on the shelf, and worked with the caption
box focused, which is where a phone keyboard is when a GIF is picked. Cost, on a
4 second card clip: one animated sticker adds about 1 second of encode and 56 kB.
471 offline tests, 7 opt in.

## 2026-08-19, twentieth pass

### Added: stock your own sticker shelf in one go

- **Upload takes as many files at once as you like.** PNG, WebP or JPEG, from the
  laptop or the phone. One file picked still goes straight onto the frame; several
  go to the shelf and wait, because a dozen files means stocking the cupboard rather
  than dressing this clip. [DECISIONS.md](DECISIONS.md) D-035
- **A file that is not an image is named and skipped, and the rest still upload.**
  Losing eleven good uploads to a bad twelfth was the failure worth designing out
- **Why this matters more than a bigger emoji library**: OpenMoji has 4,495 drawings
  and returns **nothing** for `shiva`, `ganesha`, `krishna` or `tamil`. It is an
  emoji set. A second emoji set would return nothing too. Your own artwork is the
  only answer, so the job is now cheap rather than thirty clicks

### Fixed: the opening shelf offered thirty nine stickers in forty slots

- `1F4FF`, the prayer beads, was listed twice in `OPENING_SHELF`, and the duplicate
  reached the page. `search` now de-duplicates with `dict.fromkeys`, and a test
  guards the list itself
- The freed slot and one other went to **place of worship** and **person in lotus
  position**. The other was `1F573`, which is the emoji for a *hole*, and was
  presumably not what anybody meant on a devotional status

### Documentation

- **A macOS first run checklist** in [LOCAL_SETUP.md](LOCAL_SETUP.md), nine steps,
  and a matching row in [MEMORY.md](MEMORY.md) Table ME-1. Every path in the tool
  branches on Darwin already and the fonts are vendored, but no run on a Mac is
  recorded anywhere in this repository, so the claim is written down as debt
- **T-021 rewritten and parked** at the owner's request. The new evidence changes
  the diagnosis: the same download takes 1 to 2 seconds on some attempts and 10 to
  15 minutes on others, with Tailscale on both times. An intermittent fault is not a
  weak radio, so that candidate is dead, and the test no longer needs Tailscale
  turned off: watch `tailscale status` for `direct` or `relay` during a fast one and
  a slow one

### Verified

Six files picked at once in the real page over CDP, one of them a text file renamed
to `.png`: five uploaded, the sixth was named in the error, none were placed on the
frame, and all five appeared at the head of the shelf. One file picked on its own
still landed on the frame, and a repeated name became `kolam-2` rather than
overwriting. The opening shelf now serves 40 unique stickers where it served 39 in
40 slots. 454 offline tests, 7 opt in.

## 2026-08-19, nineteenth pass

### Changed: the dashed box round a sticker appears only when it is needed

- **The white dashed selection box is now a handle, not a fixture.** It is lit while
  a finger or the mouse is on the sticker, while a Size or Turn slider is being
  dragged, and for a moment after a sticker is placed. It fades out 1.4 seconds
  after everything stops. [DECISIONS.md](DECISIONS.md) D-034
- **Why:** the frame's one job is showing what the viewer will see, and the box is
  something the viewer never sees. It is also the hit area, 8 pixels larger than the
  drawing on every side, so a small sticker wore a box half again its size
- **The orange covered box is unchanged and still permanent.** It warns that a
  sticker sits under WhatsApp's header or caption, and a warning that fades is not
  a warning
- On a mouse, hovering a sticker shows a fainter box, because there is no touch to
  reveal the handle. Phones report `hover: none` and never match

### Verified

The painted outline colour was read out of the browser at eight moments at 412
pixels wide: opaque white when just placed, transparent two seconds later; opaque
with a finger down, while dragging, and at the instant of lifting; transparent two
seconds after lifting; opaque on a slider move and transparent once still; and
orange on a sticker shoved under the caption band while nothing was being held.
Pinch, twist and drag still measure the same as they did in the eighteenth pass.
452 offline tests, 7 opt in.

## 2026-08-19, eighteenth pass

### Added: pinch to size a sticker, twist to turn it

- **Two fingers on the frame size, turn and carry a placed sticker**, the way you
  would move a piece of paper. One finger still drags. The first finger has to land
  on the sticker; the second can land anywhere, because a sticker at its default
  size is about 60 pixels wide and two fingertips do not fit inside that.
  [DECISIONS.md](DECISIONS.md) D-033
- **A sticker is now a bigger target than it is a picture**: eight pixels of
  transparent border, with `box-sizing: content-box` so the drawing is still exactly
  the fraction of the frame the renderer will paste. 60 pixels drawn, 76 to hit
- **A twist within four degrees of square settles there.** Nothing else snaps
- **The frame stops scrolling and zooming while a sticker is held**, and starts
  again the moment the last finger lifts, so an ordinary swipe over the preview
  still scrolls the page
- The Size and Turn sliders stay, follow the fingers live, and are still the only
  route on a laptop

### Verified

Real touch events, dispatched over CDP at 412 pixels wide, not simulated in
JavaScript: a spread of 1.8 took the sticker from 0.2 to 0.361 of the frame and a
30 degree twist landed on 30, with both sliders following; 88 degrees settled on 90;
two fingers moving together carried it without changing its size or angle; lifting
one finger of two continued the drag with no jump; the page's own zoom never fired.
The mouse drag still works. 452 offline tests, 7 opt in.

The harness needed fixing twice before it told the truth, and both traps are now
written down in [TESTING.md](TESTING.md): a touch outside the viewport is dropped,
and `touchEnd` releases every point you leave out of it.

## 2026-08-19, seventeenth pass

Documentation only. A sweep for anything the two redesign passes made untrue.

- [LOCAL_SETUP.md](LOCAL_SETUP.md), the walkthrough that gets followed literally:
  step 4 now describes the folding cards and where the title and the extras live,
  step 5 names the caption box rather than telling you to click the text on the
  frame, which stopped being true with D-030. The health chip replaced three pills,
  so "the third line says ready" and "the orange WhatsApp chip" became the chip at
  the top right and its rows. The phone section gains the filled Download button
  with its size, `~/Download` as where Android puts it, the Recent tick for clips
  this device already has, and the unexplained download speed
- [AGENTS.md](AGENTS.md) gains three invariants a future agent could break without
  noticing: a folded card must show what is in it, an automatic fold is not a
  preference, and `hidden` does nothing on an `<svg>`. Its verification list now
  says to drive the page at phone width and to assert on what a viewer would see
- [README.md](README.md), [PLAYBOOK.md](PLAYBOOK.md), [TASKS.md](TASKS.md),
  [CONTEXT_MAP.md](CONTEXT_MAP.md): Stop is beside Make the clip, not beside the
  progress bar; the caption is edited in its own box; the page is one folding card
  per section
- 452 offline tests and 7 opt in still pass, 0 broken links across 19 documents

## 2026-08-19, sixteenth pass

The page broken into folding cards, one per section, after the owner reviewed a
mock of both layouts. [DECISIONS.md](DECISIONS.md) D-032.

### Changed

- **Eight folding cards** instead of two long ones: the clip, look, words, extras,
  preview, stickers, post it, recent. Every header carries its own value, so a
  folded card still says what is inside it, and a dot marks one holding something
  you set yourself
- **Make the clip never folds.** It sits in a plain card with the progress under it
- **Stickers are a card**, not a button that reveals a panel
- **When a clip lands on a narrow screen** the four input cards fold and the page
  scrolls to the preview. On a laptop nothing moves. An automatic fold is not
  remembered; a fold you pressed is
- **Working and Stop share the row**, half each, while it works
- **Each of the four actions says what it does** in a line under it, and they sit
  two by two from a tablet up, so Delete is level with Send rather than trailing
- **Copy is an icon inside the caption box**, and becomes a tick for a moment
- **Clear**, in the clip card's header, empties the link, the window and the words.
  It leaves the look, the waveform and any placed stickers alone

### Fixed

- **The play icon never became a pause icon**, and the theme button never changed
  either. `hidden` is defined on `HTMLElement` and not on `SVGElement`, so
  `svg.hidden = true` set a property no stylesheet could see. `hide` and `unhide`
  now use the attribute. Reported by the owner from his phone
- **The left column overflowed under the right one** at desktop width once the
  columns were restructured: the sideways scrolling Recent strip pushed its column
  wider than the grid gave it. `minmax(0, 1fr)` and `min-width: 0`

### Verified

452 offline tests and 7 opt in, `node --check` clean. The page was driven in a
phone sized viewport over CDP rather than looked at: Clear emptied the form without
folding the card it sits in, a real 15 second render ran end to end, the row became
two halves while it worked, the input cards folded when the clip landed and the
page scrolled to the preview, the fold stayed out of the remembered layout while a
pressed fold went into it, and the copy icon became a tick. Column widths were
measured, not eyeballed.

## 2026-08-19, fifteenth pass

The page redesigned from the owner's own marked up screenshots, taken on his phone.
Mobile first this time: [DECISIONS.md](DECISIONS.md) D-029 records what that changed
and why each change was made.

### Changed: the page, on a phone and on a laptop

- **One health chip** instead of three pills, opening a panel that names each check
  and, new, **which machine** this is. From the phone, "WhatsApp Web is ready" was
  missing its most useful half: it is ready on `this-laptop`
- **Start, Length and End on one row**, and both timestamps now take a text keypad.
  Android's numeric keypad has no colon, so `0:20` could not be typed on the phone
- **Stop moved beside Make**, where you are already looking, and it takes the place
  of the keyboard hint rather than crowding it
- **The four stages are a numbered sequence** with a rail and a tick behind each one
  that is done, rather than four words in a row
- **Safe areas are on by default**, and hidden while the frame is empty
- **The caption has its own labelled box** under the preview, and what is drawn over
  the frame is a read only echo of it. D-030, which amends D-021
- **A clear button on the link field**
- **The whole form is remembered**, not just the length and the look. A phone
  reloads the tab when you switch to WhatsApp and back
- **One filled action**, chosen by which device opened the page, with the size on the
  Download button. The rest are still there, quieter
- **The sticker picker is a panel** opened by a button, with six tag chips and a
  count badge, rather than a bare disclosure arrow
- **Recent tiles show a tick** for clips this device has already downloaded, which is
  the answer to "did I save this one already"

### Added: light, dark or system

- A button in the top bar cycles the three. The choice is stored, and applied before
  the first paint so the page cannot flash the wrong palette. D-031

### Added: the page knows the machine's name

- `/api/state` returns `host`. One test, and it is what the WhatsApp row and both
  away hints now say

### Found: a clip crawls to the phone

- The owner's download ran at about **700 bytes a second**: 410 kB of 8.15 MB in ten
  minutes. Measured from this end, the server pushes the same file at about 900 MB/s,
  and `tailscale ping` reaches the phone directly on the LAN after two relayed pongs.
  **The cause is not established.** [TASKS.md](TASKS.md) T-021 holds the three
  candidates and the one test that separates them, and
  [LIMITATIONS.md](LIMITATIONS.md) Table LI-6 holds the finding
- Where the file lands **is** now known: the phone's browser saves it to `~/Download`

### Verified

452 offline tests and 7 opt in, `node --check` clean, `compileall` clean. The page
itself was driven over CDP rather than looked at: a real 15 second render end to end
through the redesigned form, the caption edited and saved with the echo following,
the sticker panel opened and a sticker placed, the theme cycled through its three
states with the palette read back each time, and the away layout checked against the
real tailnet address.

## 2026-08-19, fourteenth pass

Documentation only, again. The phone route stopped being theoretical.

- **Tailscale is installed**, by the owner, and `--also-on tailscale` was run against
  the real tailnet for the first time. `tailscale ip -4` resolved to
  `100.x.y.z`, both addresses answered, and one process reported `local: true` to
  loopback and `local: false` to the tailnet address. That is the fact D-026 leans on,
  previously checked only against a LAN peer
- [TESTING.md](TESTING.md) gains a fifth manual item for the phone route, and names the
  one step still unverified: whether the file Android saves from **Download** lands
  where WhatsApp's own picker can see it
- [docs/hosting.md](docs/hosting.md) no longer says Tailscale is missing. Phase 2 is
  now about reaching the page **without** both devices on the tailnet, not about
  reaching it from a phone at all

## 2026-08-19, thirteenth pass

Documentation only. No code changed.

- Pushed to GitHub. `3f2db34` is on `origin/main`; there is no deployed environment
  to push to, because the tool runs on the owner's laptop
- **The background service will not be installed.** The owner does not want anything
  starting with the operating system, so the page is started by hand and stopped with
  Ctrl+C. `scripts/install_service.sh` stays, dormant and documented as such, in
  README, LOCAL_SETUP, PLAYBOOK and CONTEXT_MAP. Reasoning in D-028
- **Installing Tailscale** now has its own steps in LOCAL_SETUP, checked against this
  machine: the official installer reads `UBUNTU_CODENAME` and treats Linux Mint 22.1
  as Ubuntu `noble`. It needs `sudo`, so it is the owner's to run

## 2026-08-19, twelfth pass

Rounding the tool off for daily use. Hosting is deferred: the owner chose to live
with what exists for a while first.

### Added: the page reaches your phone, and offers the route that works from there

- `serve --also-on ADDRESS` opens a second socket on the same port, so a phone can
  open the page. `tailscale` resolves your tailnet address for you. Off by default,
  and **loopback stays bound** so the address a request arrives on still says which
  device it came from
- **Download**, next to Load and Send, with a `Content-Disposition` so a phone saves
  the mp4. Copy the caption above it and post in the real WhatsApp app: WhatsApp's own
  audience, its own privacy settings, no automation at all
- Which button is the primary one follows the address the page was opened on, not the
  user agent. Nothing is ever hidden, so a wrong guess costs a glance. See D-026
- Verified against a genuinely non-loopback peer: the same page reported
  `local: false` and put Download first

### Added: Stop, and Delete

- **Stop** a render. It kills the yt-dlp or ffmpeg the render is waiting on, and the
  task ends as `cancelled` rather than `failed`. Verified on a real render: nothing
  survived, no work directory, and a full render straight afterwards was fine
- The kill goes to the process **group**, because yt-dlp runs an ffmpeg of its own
  and a signal to yt-dlp alone leaves that one encoding
- A post cannot be stopped, deliberately: a killed driver leaves WhatsApp in a state
  this tool cannot describe. Refused with a 409. See D-025
- **Delete** a clip from the page, group and sidecars together, on two presses rather
  than a dialog. Refused while WhatsApp is being driven

### Added: run it in the background

- `scripts/install_service.sh` installs a systemd **user** service: survives a closed
  terminal, restarts on failure, starts at login. No root

### Fixed

- **ffmpeg wrote its output straight into the output folder.** A clip still being
  encoded was therefore listed by the page as a real one: playable, postable, and,
  once Delete existed, deletable while ffmpeg was still writing it. A render that
  failed left the truncated file there for good. Present since the first version,
  found while building Stop. The encode now happens in the work directory and the
  clip arrives in one atomic rename; verified live, with the output folder staying
  empty for the whole of a 50 second render
- **An empty Recent strip never repainted.** The rebuild sentinel was `""`, which is
  also the signature of an empty clip list, so the strip skipped its own rebuild. It
  cost the "Nothing yet" line on a first run and left a deleted clip on show. Found by
  deleting a clip in the real page, not by reading the code
- The sticker picker asks for 96 pixel copies, cached on disk. **Measured: 402 kB to
  191 kB for a shelf of 40**, a 52 percent saving. T-020 had guessed at an order of
  magnitude and was wrong; flat OpenMoji artwork already compresses well

### Learned about WhatsApp, the hard way

- **A link in a Status caption is not tappable when you view your own Status on the
  device you posted it from.** It is tappable for everybody else. Tested from one
  device, concluded Android captions were dead, then found the link live on a second
  device. Any caption check needs a second device

## 2026-08-19, eleventh pass

Stickers, and the investigation that has to come before hosting.

### Added: stickers

- **A library, not a folder to curate.** `scripts/setup_stickers.sh` downloads
  OpenMoji 17.0.0, 4,495 drawings at 618 pixels, into the same data directory the
  token provider uses. Never into the repository, and no new dependency
- Search by word, uploads first. `om`, `diya`, `flower`, `music` all find what you
  would expect, because matching is prefix-on-a-word rather than substring
- Click one and drag it on the frame. Size and Turn adjust the one you last touched
- **Upload your own** from the page, phone included. Whatever arrives is decoded and
  written back out by Pillow, so the bytes on disk are ones we produced
- Placed stickers ride in the job sidecar, so a clip reloaded from Recent comes back
  with them where you left them
- A sticker inside the bands WhatsApp draws over gets an amber outline and a line in
  the log, and is then placed exactly where it was asked to be

### Why dragging a sticker is allowed and editing the title is not

- A sticker has no layout. It is one bitmap at one position, and the browser shows
  the very image the renderer will paste, so what you drag is what you get
- Coordinates are fractions of the frame all the way through: `left`, `top` and
  `width` go straight into CSS percentages and straight into the render request. The
  same numbers land in the same place on the 1080 overlay and the 1620 card, which is
  a test rather than a hope. See [DECISIONS.md](DECISIONS.md) D-024

### Fixed: the page could only be written to from 127.0.0.1

- `Origin` was compared against a hardcoded `127.0.0.1` and `localhost`, and Chrome
  sends that header on every same-origin POST. A page opened on any other address
  would load and read, and refuse every render and every post
- Reproduced by binding to `127.0.0.2`, which is still loopback and exposes nothing:
  `GET /api/state` 200, `POST /api/render` **403**. After the fix, 200 for both
- The expected origin now comes from the request's own `Host`, and that header is
  trusted only when it names an address rather than a name, so DNS rebinding gains
  nothing. This is what would otherwise block ever reaching the page from a phone

### Fixed: two things the sticker work surfaced

- Repainting the layer during a drag replaced the element holding the pointer
  capture, so the sticker never moved. The layer is now rebuilt only when the set
  changes
- The preview drew a shadow under each sticker that the renderer does not paste. The
  frame must not promise what the clip will not deliver

### Investigated: Evolution API and hosting

- Read Evolution API's status endpoint from source, because its documentation pages
  404. Three findings change any design built on it: it wants a URL rather than
  base64, `allContacts` means its own contact table and not WhatsApp's privacy
  setting, and partial failures across its batches of ten are swallowed
- Written up with timestamps in [docs/hosting.md](docs/hosting.md), including the
  laptop-and-phone variant and the two tests that come before any building. Nothing
  is built, and nothing is decided

## 2026-08-19, tenth pass

The page grew the things using it for real showed it needed, and the one step it
should never have taken by itself was taken back.

### Changed: the page loads the composer, you press Send

- **Load into WhatsApp** is the primary button. It opens the Status composer,
  attaches the clip, types the caption, and stops. **Send it for me** is the second
  button, for when you want the old behaviour
- `--load` does the same from the command line. `--post` still sends
- `POST /api/post` sends only when the body says `send: true`, so an omitted field
  can never mean "broadcast it", and two overlapping requests get a 409 rather than
  posting twice. See [DECISIONS.md](DECISIONS.md) D-020

### Added: the caption is in the preview, and editable there

- It sits on the frame exactly where WhatsApp draws it. Click it and type; the edit
  saves itself to the sidecar, and what is on screen is what gets posted
- If an edit cannot be saved, nothing is sent. Posting the previous caption silently
  would be worse than not posting
- The title and the second line stay as form fields, because they are pixels drawn
  by Pillow rather than text sent alongside. The page says so where the fields are.
  See D-021

### Added: a length or an end time, whichever you have

- Both boxes are live linked: set one and the other follows. Whichever you set last
  is the one sent, and `resolve_window` already understood both

### Fixed: the seek slider did nothing

- Media was served whole, with no `Accept-Ranges` and no 206, so the browser had no
  way to ask for a later part of the file. `/api/frame` and `/api/clip` now answer
  byte ranges, including a suffix range and a 416
- Verified by dragging the real slider in the real browser: the video moves

### Added: any debug browser will do, and the page can start one

- The configured port is tried first, then the other debug ports, and the first
  browser holding a WhatsApp Web tab is used. The health chip names the port
- **start it** on that chip launches the posting browser when none is running
- It cannot be your everyday Chrome: since Chrome 136 the debug switch is ignored
  for the default profile, deliberately. See D-022 for the whole answer

### Added: smaller things that came out of using it

- Recent clips carry the date they were made, as "today 0:49" or "18 Aug"
- Clicking one puts its link, window, wording and mode back in the form, read from a
  new `{stem}.json` sidecar written next to every clip and pruned with it
- A favicon, and the page is titled **WhatsApp Status Maker**
- The frame has its own player row under it, because native controls sit exactly
  where the caption goes

### Fixed: both download ladders led with a dead entry

- `web_safari` returns four storyboards and no media at all. It had been failing on
  every video-mode run since, costing 4 to 9 seconds and logging a warning that read
  like a problem. Both ladders now lead with `mweb/18`
- While measuring: 720p and 1080p do exist as DASH renditions, but
  `--download-sections` hands their URLs to ffmpeg and googlevideo answers 403. So
  video mode is capped at 360p, and the reasoning is written down rather than
  rediscovered. See D-023

### Fixed: three things the audit found

- `yt-dlp` ran with no timeout, so a wedged download would hang the task forever
  while the page politely polled it. Now 300 seconds, with a 20 second socket timeout
- The token was written to the text log, because media carries it in the query
  string and every one of those requests was logged verbatim. Now redacted
- Health polling wrote 150 kB of log in a day and re-downloaded every thumbnail
  every fifteen seconds. Successful polls are no longer logged, and the Recent strip
  is only rebuilt when its contents change

### Verified

- **The owner posted two real Statuses from the page**, at 21:53 and 00:14, in 5 and
  4 seconds. That was the last path in the tool nobody had ever exercised
- Loading without sending, inspected over CDP: the composer held the clip, the
  caption rendered as a link, the audience was Status (Contacts), and Send was
  untouched
- 327 offline tests, 7 opt in, 0 broken documentation links

## 2026-08-18, ninth pass

The tool grew a local page, and the engine grew a front door that is not the command
line.

### Added: `wastatus serve`

- One page on `http://127.0.0.1:8765`: paste a link, set a start and a length, watch
  four named stages go by, see the still, play the clip with sound, press one button
  to post. The three chips at the top say whether ffmpeg, the token provider and
  WhatsApp Web are ready before you start
- The preview has a **Safe areas** toggle that draws the two bands WhatsApp
  composites over a Status, so the constraint the card is designed around is visible
  rather than folklore
- Recent clips are listed with their own frames as thumbnails. Click one to load it
  back into the preview and post it again
- Standard library only. No web framework was added to `requirements.txt`

### Changed: one engine, two front ends

- `pipeline.py` is new and holds what used to be `cli._produce`: a `Job` in, a
  `Result` out, progress through a callback. `cli.py` is now argument parsing, the
  report and posting; `serve.py` answers a browser. Both call `pipeline.produce`
- `resolve_window` is shared too, so the page and the command line accept the same
  timestamp forms and refuse the same windows in the same words
- See [DECISIONS.md](DECISIONS.md) D-019, which also records why this is not a Chrome
  extension and not a packaged desktop app

### Added: the code has a remote

- Pushed to `https://github.com/PalWorks/whatsapp-status-maker`, private, all fifteen
  commits, `master` as the default branch. `out/`, `logs/` and `.venv/` stay ignored,
  so no clips and no logs leave the machine
- [LOCAL_SETUP.md](LOCAL_SETUP.md) opens with **Start the page**: the four commands
  to launch the local server, the startup output to expect, and a symptom table for
  when a chip is orange or the port is taken

### Security

- Any website you visit can send requests to a server on loopback, and this one can
  post to a WhatsApp account. Every `/api/` call needs a per process token header,
  preflights are refused so a cross-origin caller can never obtain permission to send
  it, foreign origins are rejected, and clip names are matched against a strict
  pattern before anything touches the disk. `tests/test_serve.py` covers each guard

### Added: `scripts/shot.py`

- Screenshots a page in the debug Chrome at a given width and colour scheme. The
  design of the page was reviewed with it, which caught the thumbnails being 403ed
  because an `<img>` cannot send a token header
- Offline suite now 285 tests

## 2026-08-18, eighth pass

### Settled: 90 second clips are fine, the limit was always size

- A 90 second clip at 9.7 MB attached cleanly to the composer, which settles what
  the 13.7 MB refusal at the same length could not: WhatsApp was rejecting the size
- So the full 90 seconds `cli.MAX_DURATION` allows is usable. The advice to keep
  `--post` clips to 60 seconds is withdrawn
- The effective ceiling is somewhere between 9.7 and 13.7 MB. Mapping it exactly is
  [TASKS.md](TASKS.md) T-014, worth doing only if long clips look too soft

### Posted: the four songs from the library test

- All four went out at the new bitrate, 9.7 MB each for 60 seconds, uploading in
  4 to 5 seconds. Six statuses now live, including the card and video pair from the
  earlier comparison

### Documentation

- `SECURITY.md` claimed the tool authenticates to nothing, which stopped being true
  when `--post` landed. It now describes the CDP route, what is still refused, and
  the debug port as the most sensitive surface on the machine
- `ROADMAP.md` still called phase 3 deferred. It is done on the desktop
- `CONTEXT_MAP.md` was missing `scripts/wa_post.py`

## 2026-08-18, seventh pass

Four songs from the owner's own library, run through the tool and inspected. Three
of the four findings were defects here.

### Fixed: a 60 second clip was too big for WhatsApp to accept

- The encoder had a fixed 2800 kbit/s ceiling, which is right for 15 seconds and
  about 21 MB at 60. WhatsApp refuses oversize media by never opening its editor,
  with no message, so every 60 second clip the tool produced would have failed to
  post and it would have looked like a bug in the driver
- `render.video_maxrate` now derives the ceiling from the duration, landing near
  9.5 MB at any length. A 15 second clip is unaffected
- `cli.MAX_DURATION` raised from 60 to 90 seconds, per the platform's real limit
- Measured against the real composer: 9.4 MB at 30s and 8.8 MB at 60s accepted,
  21.8 MB at 60s and 13.7 MB at 90s refused. The budget is set from the sizes proven
  to work rather than the documented 16 MB. See [DECISIONS.md](DECISIONS.md) D-017

### Fixed: the card said `Release` instead of the artist

- An auto-generated music upload has a channel like `Release - Topic`. Its artist
  field said `Project Samskriti`. The card prefers the artist now

### Fixed: the same name twice, in two romanisations

- `Potri Thiruthandagam - போற்றித் திருத்தாண்டகம்` transliterates into two spellings
  of one name, which the old character comparison could not see. Segments are now
  compared as phonetic skeletons, so both reduce to `potritirutandagam`
- Numbers are compared exactly and separately: `Thevaram Vol I` and `Thevaram Vol II`
  score 0.92 on skeleton similarity and are different volumes
- A dash separator is honoured, but only with space around it, so `Varma-VARA` stays
  one word. Separators survive when nothing is dropped

### Fixed: academic capitalisation on the card

- `Thiruppugazh viRalmAranaindhu (thiruchchendhUr)` now reads
  `Thiruppugazh Viralmaranaindhu (Thiruchchendhur)`
- Judged per run of letters, not per word: judging whole words mangled `Varma-VARA`
  into `Varma-Vara`, caught by a test
- See [DECISIONS.md](DECISIONS.md) D-018. Offline suite now 234 tests

## 2026-08-18, sixth pass

Artwork and layout, after the owner asked why the card had black bands in it.

### Fixed: padding bars are cropped off

- A YouTube thumbnail is always 16:9, so a picture of any other shape arrives
  padded with flat bars. The measured case, a 2.35:1 music thumbnail, is 1280x720 with an 85 pixel black
  bar above and 84 below a 2.35:1 picture, and those bars were showing inside the
  card and as dead bands in the blurred background
- `compose.detect_bars` finds them by sampling points along each line and asking
  whether it is flat and the colour of the outermost line. Two earlier versions of
  the detector were wrong in ways the tests caught: downscaling quantised the bar
  edge to 20 pixels, and averaging along a row made regular texture read as flat
  and ate 144 rows of a striped picture
- The same defect existed in `--video` mode, where the source's own bars sat inside
  the blurred fill as hard black seams. `render.detect_source_crop` samples three
  frames through the same detector and takes the smallest bar found on each side,
  so a dark frame makes the crop more conservative rather than inventing one

### Changed: the card is the shape of its artwork

- Forcing a 2.35:1 still into a 16:9 box cropped a quarter of its width, which cuts
  people out of the sides of a group photograph. The card's height now follows the
  artwork's aspect ratio, clamped so a squarer image cannot crowd WhatsApp's header
- The card's **bottom** is the fixed anchor, so the card and title stay a tight pair
  whatever the artwork's shape, and every post reads as the same series
- A soft drop shadow under the card, because a card floating on a blurred copy of
  itself reads as a hole without one

### Added: `SAFE_TOP`

- WhatsApp draws the avatar, name, timestamp and playback controls over the top 12
  percent of the frame. That band was being respected by accident; it is now
  measured in `tests/test_safe_zone.py` alongside `SAFE_BOTTOM`, across one, two and
  three line titles and every artwork shape
- The text block moved up from y 1075 to 1005, which puts the content in the optical
  centre of what is actually ours

### Fixed: a composer left open sent two Statuses

- The status composer holds several files, so attaching into one that an earlier
  run left loaded posts all of them. Two Statuses went out a second apart on
  2026-08-18 that way, from one command
- `load_video` now backs out of an open composer before attaching

### Added: `wa_post.py delete-all --yes`

- Deletes every Status on the account, reopening the viewer each pass so no index
  goes stale. Irreversible, hence the required flag

### Changed: titles break after a hyphen

- An `Artist Name-LONG SONG TITLE` heading was one unbreakable token, so it took
  three lines and broke the name in the wrong place. Typesetting breaks after a
  hyphen; now so does this, and that title fits two lines at its own boundary
- See [DECISIONS.md](DECISIONS.md) D-016. Offline suite now 189 tests

## 2026-08-18, fifth pass

### Changed: nothing is said twice

- The caption is now the URL alone. The title was already on the card, a centimetre
  above it, and printing it in both places made the Status read like a listing
- The small URL line is gone from the frame. It said nothing the caption did not
  say better, and a viewer cannot tap pixels
- `CardText` no longer has a URL field, and `fetch.Source.short_url` is gone with it
- `CARD_TITLE_TOP_FOOTER` is gone: without the URL line the worst case block fits
  from the normal start, so card mode has one start position again. Video mode's
  text moved back down to y 1284, keeping the same distance from the bottom as
  before
- See [DECISIONS.md](DECISIONS.md) D-015

### Fixed: `--post` silently attached nothing

- The CLI passed the clip's relative path to `DOM.setFileInputFiles`. Chrome takes
  a relative path, reports no error, and attaches nothing, so the failure surfaced
  75 seconds later as "timed out waiting for the media composer" and looked like a
  slow browser. Two posting runs failed this way before the cause was found
- `post.load_video` now resolves the path and checks the file exists before it
  touches the page, and the composer timeout says what it actually means
- `tests/test_post.py` drives the attach path against a fake page and asserts the
  path reaching Chrome is absolute, that a missing file fails before anything is
  clicked, and that the file dialog interception is always turned back off

### Changed: LOCAL_SETUP describes posting, not file transfer

- Steps 5 and 6 told you to copy the mp4 to your phone and post two statuses, and
  wondered in writing whether WhatsApp Web could post a video at all. It can, the
  tool does it, and the run-through now says so with the Chrome command needed

## 2026-08-18, fourth pass

The two post flow was built on a claim nobody had tested. Testing it removed a
feature, a design element and most of phase 3.

### Changed: one post, not two

- A URL in a Status media caption **is** tappable. Confirmed in WhatsApp Web,
  then on the owner's phone, where tapping it opened the YouTube app. The entire
  two post flow existed to work around this and was not needed
- A run now produces and reports one Status. `--follow-up` adds the text only
  second one, for the link preview card
- `.status2.txt` is only written with `--follow-up`
- See [DECISIONS.md](DECISIONS.md) D-013, and D-003 for the superseded reasoning

### Fixed: the caption no longer collides with the frame

- WhatsApp draws its caption across the bottom of the frame. The burned in link
  pill sat at y 1640 of 1920, directly underneath, and both became unreadable on
  a real posted Status
- The bottom 15 percent is now reserved. `compose.SAFE_BOTTOM` marks it and
  nothing is drawn below it in either mode
- The pill is gone, replaced by a small URL line inside the text flow. The caption
  above it carries the tappable link; the in frame copy is for clips that get
  forwarded without their caption
- Every element now flows from the one above it, so a three line title cannot push
  anything into the reserved band. The waveform moved from y 1400 to 1450, into the
  space the pill vacated
- `tests/test_safe_zone.py` measures the painted pixels in both modes, with and
  without a footer, so this cannot silently come back
- Verified against a real posted Status: no collision
- See [DECISIONS.md](DECISIONS.md) D-014

### Added: `--post`

- `wastatus "URL" 1:10 1:25 --post` posts the clip to your Status by driving an
  already logged in WhatsApp Web tab over the Chrome DevTools Protocol. Off by
  default. `--follow-up` posts the text status too, `--port` picks the browser
- Posting logic moved into `wastatus/post.py`. `scripts/wa_post.py` is now a thin
  debugging door into the same functions, and gained `--caption-file`
- A posting failure never loses the clip: the tool exits 3, keeps the files, and
  prints a one line command that posts the existing mp4
- Chrome throttles background tabs hard enough to time out the composer, so the
  driver foregrounds the tab first. It also stops answering the debug protocol
  during an upload, which is treated as "still going" rather than as an error
- This is what phase 3 was going to be, done without an unofficial WhatsApp
  client and therefore without the account risk that deferred it. See
  [DECISIONS.md](DECISIONS.md) D-012
- New dependency: `websocket-client`
- Offline suite now 90 tests

## 2026-08-18, third pass

### Added: `--frame`

- Writes a full resolution still next to the mp4, so the look can be checked
  without opening a video player. `--frame` takes the clip midpoint, `--frame 0:02`
  a specific moment, which is how you inspect the zoom start or a fade
- The still is pruned with its clip and recorded in the run log
- Replaces the two line ffmpeg incantation that [PLAYBOOK.md](PLAYBOOK.md) and
  [TESTING.md](TESTING.md) previously told you to type by hand
- Offline suite now 82 tests

## 2026-08-18, second pass

Four changes from the owner testing the first version.

### Changed: the card is less formal

- The `Full link in the next status` footer and the `NOW PLAYING` eyebrow are both
  gone by default. `--footer TEXT` and `--eyebrow [TEXT]` add them back. A Status
  is personal, and instructional copy made it read as an advertisement. See
  [DECISIONS.md](DECISIONS.md) D-010
- With that space freed, titles wrap to three lines instead of two, so long
  compound names are no longer ellipsised mid-name

### Changed: filenames are human readable

- `20260818_sinna-sinna-murugaiyaa_70-85.mp4` rather than `A6DfGQsdz1Y_70-85.mp4`.
  Leading with the date means alphabetical order is chronological. The source URL
  is still in the sidecar caption and in every run record, so nothing is lost
- Re-clipping the same song and window on the same day gets a `-2` suffix rather
  than overwriting

### Added: logs

- `logs/wastatus.log`, rotating text, carries the **full** yt-dlp and ffmpeg output
  of a failure. The on screen error stays short and points at the file
- `logs/runs.jsonl`, one record per run: window, mode, which extraction strategy
  won, per stage timings, output size, and on failure which stage was reached
- Falling through to a later ladder entry now logs a warning, so extraction
  degrading is visible before it fails outright
- A low resolution artwork fallback logs a warning naming the size
- `--verbose` echoes the log to the console

### Added: tests

- 69 offline tests over timestamps, transliteration, naming, retention and logging,
  plus 7 opt in end to end tests behind `WASTATUS_E2E=1`
- `requirements-dev.txt` and `pytest.ini`
- A guard asserting aksharamukha actually imported, because a silent fallback to
  Unidecode would degrade every Tamil title without failing anything

### Added: the output folder prunes itself

- The newest 20 clips are kept, mp4 and sidecars together, pruned after a
  successful write. `--keep-last N` changes it, `0` disables it

### Fixed

- **Accented Latin leaked through untransliterated.** `to_latin` only converted
  above U+024F, so `Café` passed through unchanged and broke the ASCII invariant
  that filenames and captions rely on. Caught by a test written for the new suite

## 2026-08-18, first pass

### Documentation

Added the repository documentation set described in `agent_docs_guide.md`, scoped
to what this project warrants: [CONTEXT_MAP.md](CONTEXT_MAP.md),
[ARCHITECTURE.md](ARCHITECTURE.md), [DOMAIN.md](DOMAIN.md),
[AGENTS.md](AGENTS.md), [PLAYBOOK.md](PLAYBOOK.md), [RUNBOOK.md](RUNBOOK.md),
[DECISIONS.md](DECISIONS.md), [MEMORY.md](MEMORY.md),
[LIMITATIONS.md](LIMITATIONS.md), [ROADMAP.md](ROADMAP.md),
[TASKS.md](TASKS.md), [TESTING.md](TESTING.md), [SECURITY.md](SECURITY.md),
[LOCAL_SETUP.md](LOCAL_SETUP.md) and this file. Files from the guide that
describe things this project does not have were deliberately skipped, with the
reasoning recorded in [CONTEXT_MAP.md](CONTEXT_MAP.md).

### Added (`caa2600`)

- `wastatus.sh` wrapper, so the tool runs from any directory without remembering
  the virtualenv path. Output lands relative to where it was invoked.

### Added (`9d41a63`) initial working version

- Card render mode: blurred artwork background, artwork as a rounded card, slow
  zoom, waveform reacting to the audio, burned in link pill, footer line
- `--video` mode: real frames, blurred fill to 9:16, text overlay, written to a
  separate `_video.mp4` so the two modes never collide
- Two post output: the clip plus a text only status carrying a tappable link,
  written as `.caption.txt` and `.status2.txt`, with post 2 copied to the
  clipboard
- Tamil romanisation via aksharamukha `RomanReadable` with `TamilTranscribe`,
  Unidecode fallback for other scripts, upload noise stripping, and collapsing of
  titles that repeat themselves once per script
- Timestamp parsing for `93`, `1:33`, `1:02:03` and a `?t=` URL parameter, with
  the 60 second WhatsApp Status ceiling enforced before anything is downloaded
- Automatic proof of origin token provider lifecycle, plus
  `scripts/setup_provider.sh` for the one time install
- Client and format ladder for media extraction, because no single combination
  works across videos
- Bundled DejaVu fonts so Linux and macOS render identically
- `WASTATUS_PROXY` and `WASTATUS_COOKIES_FROM_BROWSER` hooks for hosts with a
  flagged IP

### Fixed during initial development

- Clipboard helpers (`xclip`, `wl-copy`) stay resident and held the inherited
  stdout pipe, so the tool appeared to hang for minutes after it had finished.
  They are now detached with their streams closed
- Card mode and `--video` mode wrote the same filename and overwrote each other
- Encoder settings produced a 10.2 MB clip for 15 seconds. Now 5 to 6 MB

### Known at time of writing

Caption link tappability is unconfirmed on a real device, which is what the two
post flow is built around. See [MEMORY.md](MEMORY.md) Table ME-1 and
[TASKS.md](TASKS.md) T-001.
