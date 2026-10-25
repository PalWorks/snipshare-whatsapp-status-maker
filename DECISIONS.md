# Decisions

Why things exist. Newest first. Do not undo one of these without reading the
rationale and the alternatives that were rejected.

---

## D-103: The extension is distributed from the site only, not the Chrome Web Store

**Date:** 2026-10-26T01:53:58+05:30
**Status:** decided by the owner

**Context.** The owner asked whether the extension could go on the Chrome Web Store.
The Store's program policies, read on this date, say: "Do not encourage, facilitate,
or enable the unauthorized access, download, or streaming of copyrighted content or
media", and "Repeated infringement of intellectual property rights, including
copyright, will also result in account termination." Cutting a clip from somebody
else's YouTube video is that use, and a rejection would count against the PalWorks
developer account, not only this extension. Loading a clip into WhatsApp without
pressing Send keeps it inside the rule against sending messages for the user (D-020).

**Decision:** keep installing it unpacked from the site's `/install` page, with the
zip's SHA-256 shown there (D-101). No Store submission, listed or unlisted.

**Alternatives rejected for now:** submitting it as it is, unlisted (reviewed under
the same policies; likely rejection and a strike on the account); a smaller Store
extension that only loads people's own uploads into WhatsApp (safe, but without the
reason people use SnipShare); an enterprise policy install (only for browsers an
organisation manages).

**Revisit when** SnipShare gains a source that is not somebody else's copyrighted
video, such as a person's own recordings, or the Store's policy changes.

---

## D-102: The app's containers reach the public internet and nothing else

**Date:** 2026-10-26T01:29:37+05:30
**Status:** built, tested on the host, deployed with this change

D-101 left one gap for the owner: code that ever ran inside the app container could
open connections to the host, to the other machines on its private network, and to
the cloud's metadata service. Checked from inside the running container before this
change: the metadata service answered, and the host's ssh, http and https ports were
open on its bridge address. The host is shared with other projects.

The cloud's own firewall (security lists and network security groups, set through
its CLI) cannot close this: it filters traffic at the machine's network card, and
none of these connections leaves the machine. The metadata service in particular
cannot be blocked there. The cloud CLI did confirm the exposure was not yet
dangerous: the tenancy has no dynamic groups and no policy that gives the machine's
identity any power, so the certificate the metadata service hands out opens nothing.
That holds only until someone adds one.

**Decision:** firewall rules on the host, matching only this project's subnet, read
from Docker at the time they are applied
([deploy/egress.sh](deploy/egress.sh)). In `DOCKER-USER`, a connection from the
project to a private, link-local, loopback, shared or multicast range is refused,
apart from DNS to the host's own resolvers; the public internet stays open. In
`INPUT`, any new connection from the project to the host itself is refused. A
systemd unit ([deploy/snipshare-egress.service](deploy/snipshare-egress.service))
re-applies them whenever Docker starts, and `scripts/deploy.sh` installs it and
re-applies the rules after every `up`, so a recreated network gets rules for its
new subnet. Nothing removes them when Docker stops, because with live restore the
containers keep running.

**Alternatives rejected:** an `internal` Docker network with an egress proxy (a
third container and a proxy allowlist to keep in step with every service the app
calls, for the same result); pinning the subnet in Compose (recreating the network
for a value the script can read); rules in the host's saved `rules.v4` (they load
before Docker and would mix this project into the host's own file).

**Verified:** applied twice, leaving one jump in each chain. From inside the app:
the metadata service, the host's ports at both its addresses, the network's gateway
and another project's bridge are all refused; DNS resolves; Google's keys,
Turnstile, Resend, GIPHY and Chat all answer.

---

## D-101: A second security pass, before the first deploy from the public repository

**Date:** 2026-10-25T22:43:40+05:30
**Status:** built, tested, deployed with this change

The owner asked, once the repository was public, for confidence that nobody could
take over the server through a link, text or a script. Two independent reviews: a
static and supply chain audit (semgrep across the code, pip-audit on both
requirement files, the container and deploy setup, headers, cryptography, the
extension), and 133 defensive tests run against a local copy covering escaping,
file access, access control between people, limits, the data layer and outside
fetches. Neither found a way to read another person's data, run script in a page,
reach a file, or run a command. pip-audit found no known vulnerability. What was
found, and changed:

- **The extension people install is built into the image**, where the app cannot
  write, instead of copied into the data volume after start. Code running inside the
  app could otherwise have swapped what every new person installs into the browser
  that holds their WhatsApp. `/install` shows the zip's SHA-256.
- **A request has one reading.** Two `Content-Length` headers, one beside
  `Transfer-Encoding`, or a body on a method that never reads one (`OPTIONS`
  included) is answered 400 and the connection closed; a length in other digits
  (`²`), a body that is a list or nested a hundred thousand deep, a screenshot that
  claims a huge picture are all answered rather than dropping the connection.
- **Sign-in.** The session cookie is `__Host-snipshare_session`, so no other
  subdomain can set it; everybody signed in once more. An address signs in only
  with the Google account that first used it. A grant slides while in use but ends
  two hours after it was made. A public site with no Turnstile secret refuses the
  form instead of skipping the check, and a Turnstile answer for another host is
  refused. Only Google's own photo host is kept as a picture.
- **Outside fetches.** A GIF is fetched only from GIPHY's and KLIPY's media hosts,
  and a redirect is followed only to them.
- **Limits.** At most 200 connections at once; an uploaded sticker may claim at most
  4000 by 4000 pixels, 300 frames and 200 million pixels in all, checked before
  decoding.
- **Headers and logs.** `Permissions-Policy`, `Cross-Origin-Opener-Policy`
  (allowing Google's sign-in popup), HSTS with `includeSubDomains`, no Python
  version in `Server`, a policy on Python's own error pages. Alerts reach Chat with
  `<` and `>` replaced, and reach the log without email addresses.
- **The container.** `PYTHONNOUSERSITE=1`, so nothing planted in the data volume
  runs at start; the base image refreshed at every deploy; the tunnel's metrics on
  its own loopback; `tunnel.env` kept out of the build context; the host's two
  settings files required at mode 600.
- **Found while checking it end to end:** after a long ad in a tab that is not in
  front, Chrome slowed the YouTube page's timers enough that the worker's 60 second
  silence limit failed a capture that was only being held back. The limits are now
  150 seconds of silence and 120 seconds without progress.

**Left for the owner** (LIMITATIONS.md, Table LI-13): keeping the app container from
reaching the host's other services needs firewall rules on the host, which is shared
and needs root; and the base image is refreshed rather than pinned by digest.

## D-100: The audit before publication, and what it changed

**Date:** 2026-10-25T15:11:42+05:30
**Status:** built, tested; not yet deployed to the hosted site

Before the repository went public, the whole codebase was audited in four parts
(the hosted site, the extension, the pages, the local engine), each finding checked
against the code and the worst proven with a scratch test. Nothing was found that
let one person reach another's clips, uploads or keys, and no script injection. What
was found, and is fixed with a test for each (`tests/test_hardening.py`,
`tests/test_portal.py`):

- **Requests a stranger could make.** A body read before the session was checked,
  `Content-Length: -1`, a GET with a body parsed as a second request, a title long
  enough to hold the render slot for hours, a sign-up answer that said how an address
  stood. SECURITY.md, Table SE-2.
- **The local page.** A link beginning `--` passed options to yt-dlp; a rebinding
  name could read the token. Both closed.
- **Posting.** Three places where the rules of D-020, D-071 and D-073 were kept by
  accident rather than by design: `send` defaulted to true in three signatures (now
  false); a browser whose store could not be read was reported "sent" when its
  composer closed (now `StatusUnconfirmed`, and a browser merely too busy to answer
  is told apart from it and asked again); a failed follow up text marked a video
  that had gone out as failed, skipped its sheet row and offered a command to send it
  again (now the video stands, and the text's failure is reported beside it).
- **Slow and interrupted lines.** The extension's read failed at a fixed two minutes
  however steadily it moved (now 60 seconds without progress); upload chunks could
  outlast Chrome's 30 seconds for a `fetch()` in a worker, which stops the worker (now
  64 KB to start, sized to a few seconds, 25 second timeout, the size kept with the
  job); a download was rewritten to storage every 256 KB (now every 2 MB) and joined
  without checking where a partial answer started (now checked). The pages' polls
  shared one timer, so watching a post stopped the watch on a render; one dropped
  poll called a running render failed.
- **Races.** Prune against a post, two prunes, the controls check against a post,
  two token providers starting, the janitor against a chunk landing, two sign-ups for
  one address, two stickers past the count.

**Rejected:** leaving the lesser findings for later. The repository was about to be
read by strangers, and every one was a few lines with a test.

**Left, on purpose,** in LIMITATIONS.md: the base image is not pinned by digest, the
requirements are minimums, and a long-hidden YouTube tab can be slowed by Chrome,
because bringing it forward would take the person's focus.

## D-099: Published as a new repository, under the AGPL with a commercial licence

**Date:** 2026-10-25T15:11:42+05:30
**Status:** decided by the owner

**A fresh repository, one commit.** The private repository keeps the whole history
and stays private. Its early commits carry the site's address, the host's name and
personal details that later passes removed (D-093); rewriting them out of history is
possible but easy to get subtly wrong, and one missed blob is public for good. A
single commit made from the audited tree has nothing in it that was not read. The
public copy is `PalWorks/snipshare-whatsapp-status-maker`; the private operations notes stay where they were.

**AGPL-3.0-only, plus a paid commercial licence (dual licensing).** It replaces MIT.
The owner chose it from Table L-3 over PolyForm Noncommercial, AGPL alone, and
keeping MIT.

- The packages in use are GPL-2.0-or-later (Unidecode), GPL-3.0 (the token plugin)
  and AGPL-3.0 (aksharamukha). The AGPL is compatible with all three; PolyForm
  Noncommercial is not, and would have meant dropping the Tamil romanisation.
- The hosted site runs aksharamukha for people over a network, so every page links
  to the source (`WASTATUS_SOURCE_URL`, defaulting to the public repository).
- A commercial licence can only be offered for code PalWorks may license both ways,
  so CONTRIBUTING.md asks every contributor for a licence grant alongside the DCO
  sign-off, and COMMERCIAL-LICENSE.md says plainly that third-party code keeps its
  own terms.

**The hosted image installs less** (Table L-2, option B): `deploy/requirements.txt`
leaves out yt-dlp, the token plugin and the WhatsApp driver's websocket client, none
of which the site runs. A test keeps it a subset of `requirements.txt`.

**Rejected:** PolyForm Noncommercial (above); MIT (anyone could run a changed copy as
a service and keep the changes closed); a history rewrite (above).

---

## D-098: The account and admin pages, designed as one system

**Date:** 2026-10-25T13:12:05+05:30
**Status:** built

The owner marked up the Profile, API keys, Feedback and Admin screens. They are now
built from one small set of parts (docs/account-page.md, Tables AP-5 to AP-7):
settings as rows that read first and edit in place (pencil, field, Save and Cancel,
Enter and Escape); a short message at the foot of the screen to confirm a change,
with Undo or Copy where it helps; destructive actions confirmed in the row they
affect, never in a dialog; segmented buttons, chips and pills used the same way
everywhere. Profile gains the Google photo, a role pill and **Preferences** with the
theme (System, Light, Dark), which every page's header also carries; a new **Sign-in
and security** section lists the browsers signed in, by kind ("Chrome on Linux"), with
Sign out for each and everywhere else. API keys are rows with Connected or Not added,
Replace and Remove. Feedback asks for name (filled), the Google address (locked),
type, **subject**, message and up to three **screenshots**, which are re-encoded and
mailed, not kept. Admin gets a **date range** that every figure follows, requests as
cards with Approve and Decline side by side, people as a searchable, filterable list
with a menu for the rare actions, and Add person as one compact row.

**New data kept**, said on the privacy page: the Google photo's address, and each
session's coarse browser and system.

---

## D-097: Every press is answered: hover, press, spinner, bar

**Date:** 2026-10-25T10:49:50+05:30
**Status:** built

Asked by the owner: the account icon gave no sign it was clickable, and pressing it
showed nothing until the next page arrived. Across the site and the tool page now:
everything pressable changes on hover (the account chip takes the accent and its
initial grows a ring) and gives a little when pressed; a link to another page shows
a spinner at once and, if the page takes more than 150 ms, a thin bar runs across
the top (`pages/nav.js`, `nav.css`); a button waiting on the server shows a spinner
beside its words without changing size, the tool page's **Make the clip**, **Stop**
and **Load into WhatsApp** included; the account and admin pages show the shape of
what is loading; and a section arrives with a short rise. All of it stops for
anybody who has asked their system for reduced motion.

---

## D-096: The extension's folder is `src/`

**Date:** 2026-10-25T09:21:14+05:30
**Status:** built

Asked by the owner. `extension/` is now `src/`; every script, test and document that
named it follows. The built copy people install is unchanged: it is still built into
`dist/snipshare-extension/` and zipped under that name, because that is the folder
name a person sees on their own disk.

---

## D-095: An account page, and keys for both GIF services at once

**Date:** 2026-10-25T09:21:14+05:30
**Status:** built

The Account panel unfolded across the top of the tool page and pushed the work down;
it held one GIF key, so adding KLIPY threw GIPHY away; it showed a pasted key in
plain text. Asked by the owner on 2026-10-25: a page of its own, `/account`, two
columns from 900 pixels and a row of tabs on a phone, one section at a time and named
in the address: Profile (the name can be changed), History (today against the
limits, the last 14 days, every clip of the last 90 days with its video, window and
outcome, opened or downloaded while it is kept), API keys, Feedback, Extension, and
Privacy and data, with Sign out always there. The tool page's chip is a link to it.

**GIF keys:** one per service per person, so GIPHY and KLIPY are both kept, masked as
they are typed and shown afterwards only as their last four characters. **Search
with** GIPHY, KLIPY or both: both asks the two services at once, in parallel, and
interleaves their answers, keeping one service's results if the other fails. Each
result carries its provider, and the page names it `provider-id`, so two services'
ids cannot collide. A second key makes both the default. The local tool gains the
same: two keys in `.env` and `WASTATUS_GIF_PROVIDER=both`. Each service's credit is
kept, KLIPY's required words opening the search box.

**Feedback** is mailed to the operator with the person's own, Google checked,
address as the reply-to, so it can be answered from the inbox; it still only ever
goes to the operator. It is sent through Resend's HTTP API, which is what Resend's
CLI calls: the container has no Node to run the CLI, and the key and domain are the
same. A problem can carry the last failure the tool page saw.

**History** is a new table, 90 days, gone with the account, and said on the privacy
page. Plan and the decisions taken without asking: [docs/account-page.md](docs/account-page.md).

**Rejected:** a wider panel (still in the way of the work); keeping one key with a
switch (the second service's key would have to be pasted again every time).

---

## D-094: A clip opens on its picture, never on black

**Date:** 2026-10-25T09:21:14+05:30
**Status:** built

Reported by the owner with two screenshots: WhatsApp's composer showed a loaded clip
as a black rectangle until it was played, and its thumbnail was black too. The clip
faded in from black over its first 0.3 seconds, so its first frame, which WhatsApp
shows before anybody presses play, in the composer and in the Status list, was black.
The picture no longer fades in, in either mode: the first frame is the artwork card or
the video itself. The sound still rises over its first 0.2 seconds, so it does not
start with a click, and the end still fades out. A test makes a clip and measures its
first frame.

---

## D-093: The repository names no site, host, person or key

**Date:** 2026-10-25T02:06:06+05:30
**Status:** built

The owner asked for the repository to stay fit to publish, with a clear line between
what is code and what is theirs. Everything that names the production site, the
host, the owner's addresses or a key lives in the local `.env`, the server's `.env`
and `tunnel.env` (mode 600), and the private operations notes. The extension in the
repository talks only to a local copy (`src/config.js`); the copy people
install is built for the site by `scripts/build_extension.py`, which writes the
address into `config.js` and the manifest and pins the id with a key kept outside
the repository. `tests/test_publishable.py` fails on a real email address, a public
IPv4 address, a home directory, or any string on the owner's git-ignored deny list,
and the documents were swept to pass it.

**Rejected:** a clean-up just before going public (it is always one file short);
committing the built extension (it carries the site's address). **Not done here:**
the git history still holds the old addresses; a history scan and rewrite, or a
fresh squashed public repository, is the owner's call when the switch is flipped.

---

## D-092: SnipShare runs as its own Compose project behind a Cloudflare Tunnel

**Date:** 2026-10-25T02:06:06+05:30
**Status:** built, live

The renderer used to sit on the host's shared reverse proxy network, reached through
a block in the shared Caddyfile and a DNS `A` record. Decided 2026-10-24 that this
project must be editable, restartable and removable without touching anything else
on the host. It is now one Compose project, `snipshare`: the app and a `cloudflared`
container on a network of their own, two named volumes, no host port, and the
scheduled work (`wastatus/watch.py`) inside the app. The Caddy block was removed
(backup beside the Caddyfile), the DNS record became the tunnel's CNAME in place, the
old container, image, folder and volume were removed after its token file and logs
were copied into the new volume. Uptime monitoring saw no failed check across the
switch. See [DEPLOYMENT.md](DEPLOYMENT.md).

**Rejected:** keeping the shared proxy (every change meant editing a file other
sites depend on); host ports behind a firewall (one more thing open).

---

## D-091: Limits per person, a cap per hour, and the owner hears about trouble

**Date:** 2026-10-25T02:06:06+05:30
**Status:** built

Ten clips and 500 MB of uploads a day each (the owner's numbers, Table HP-1), one
render at a time each, 60 renders an hour across everybody, and the renderer's
worker slots shared by the page's renders and the popup's jobs, so the machine never
runs more ffmpegs than it has workers. Every check that can refuse a clip runs
before the extension reads anything (`/api/grant`) and again before the uploads are
spent; uploads that never arrive give back what they did not send; a refused render
gives its place in the hour back. The extension paces itself too: 20 captures and 10
loads an hour per browser, never two captures at once.

What goes wrong is reported without the video: the page reports a failed capture,
load or fetch as a phase, a code and versions; the server records render failures.
Alerts go to the owner's Chat space at most once per kind per hour (a new request,
80 percent of a limit, the hourly cap, failure rates, a full disk, a long queue); a
digest of yesterday arrives daily at 08:30 IST, beside a backup of the people
database (seven kept) and the removal of clips of anybody away 90 days.

**Rejected for now:** PostHog product analytics (Table HP-1: server usage only until
there are ten people).

---

## D-090: The page drives the extension, and the extension never holds a session

**Date:** 2026-10-25T02:06:06+05:30
**Status:** built

The toolbar button opens the site. The page talks to the extension over a port
(`externally_connectable`, the built site alone): hello, capture this window, load
this clip, read this video's title. For a capture the page asks the server for a
grant first, which also resolves the window exactly as the render will; the
extension opens the video in a tab beside the page for the moment its player needs
to start (measured 0.5 s in Phase 0), steps back, reads the window, closes the tab,
and uploads with the grant. The grant is good for 15 minutes and one purpose, slides
forward while an upload keeps sending, and is only ever used against the page's own
origin, whatever a message says. A clip's fetch has a grant naming that one clip.
The words come from YouTube's oEmbed in the browser and are cleaned on the server by
the same `title_and_channel` the card uses.

The popup, which took a token the owner made, is kept as the extension's options
page, off the toolbar.

**Rejected:** a content script relaying between page and extension (no id to know,
but every page of the site would carry it); giving the extension the session cookie.

---

## D-089: Who gets in: Google sign-in, and the owner says yes

**Date:** 2026-10-25T02:06:06+05:30
**Status:** built

A request is a short form (name, email, what for, how heard, a Chrome tick box), with
**Sign up with Google** to fill it and prove the address, behind Cloudflare
Turnstile and a limit of five an hour per address. The owner hears by mail (Resend,
a sending-only key for one domain) and in the Chat space, with a link to approve;
nothing is ever mailed to the person, so a typed address cannot hurt the sending
domain. Access is only ever granted to a Google sign-in with an approved address.
A session is a random cookie (HttpOnly, Secure, SameSite=Lax, 30 days) stored as a
hash; every call also carries a value derived from the session that only the page
has, and every change an `Origin` of the site. Suspending someone ends their sessions
and grants at once. The admins are the addresses in `WASTATUS_ADMIN_EMAILS` and
nobody else.

**Rejected:** anybody with a Google account straight in (Table HP-1: the approval is
the abuse protection that costs nothing).

---

## D-088: Each person's GIF key is their own, encrypted; the owner's is never shared

**Date:** 2026-10-25T02:06:06+05:30
**Status:** built

GIF search on SnipShare uses a free GIPHY or KLIPY key the person adds under
Account. It is checked with one search before it is kept, stored encrypted (Fernet,
from a key derived from `WASTATUS_SECRET_KEY`), used only for that person's
searches, and removed on request. Without a key, the GIF shelf says how to add one.
The owner's own keys stay in the local `.env` and are never used for anybody else:
on the hosted page the provider and key come from the person, through a context
variable set per request, or there is none.

---

## D-087: SnipShare is the local page, served per person by the renderer

**Date:** 2026-10-25T02:06:06+05:30
**Status:** built, live

The owner asked for the full page they use every day to open from the extension's
button, for anyone who loads the extension. It is served by the renderer rather than
packed into the extension, so media needs no token in its address and a page fix
ships with a deploy. `serve.App` already answers every call the page makes, so it is
reused, not copied: `portal.Workspace` is `serve.App` pointed at one person's folder,
with posting and the debug browser switched off and the extension's capture standing
in for yt-dlp; `portal.SiteHandler` is the renderer's handler and the local page's
handler in one, binding the signed-in person's workspace, stickers and GIF key for
the length of each request. The page is the same `index.html` and `app.js`, with
`hosted.js` answering the few questions that differ. The name is **SnipShare**,
"Status Maker for WhatsApp, from YouTube videos": the marks appear only in the
description, never as the name. The public pages say plainly what it is and is not
(not a downloader, ads play, protected video cannot be clipped, you press Send,
experimental and invite only, not affiliated).

**Rejected:** a separate web app (two copies of every route); packing the page into
the extension (tokens in every media address, a release for every page fix).

---

## D-086: A dash between spaces keeps the space after it

**Date:** 2026-10-24T21:00:13+05:30
**Status:** built

Found reading a frame the hosted renderer made, not reported. `compose._join` glued
the next word to any line ending in a hyphen, so that `Varma-VARA` could break after
the hyphen without growing a space. A dash standing on its own between spaces ends a
line in a hyphen too, and every "Artist - Song" title came out "Artist -Song", on
every card the tool has made. The join now drops the space only when the hyphen is
attached to the word before it. `tests/test_wrap.py` holds both cases.

---

## D-085: Phase 2 is a browser extension and a hosted renderer

**Date:** 2026-10-24T21:00:13+05:30
**Status:** built, live in production

The agreed phase 2 was the local page on an always-on host behind Cloudflare Access,
with YouTube fetched from there through WARP or a residential proxy. Its one load
bearing risk was the datacentre address, and by October 2026 that risk had grown:
YouTube's web player had moved to SABR, the remaining yt-dlp routes were being
closed client by client, and a server was the worst place to chase them from.

**The owner asked instead for something anybody could run from their own machine,
so the fetch happens on their own address.** A spike measured the alternative before
anything was built ([docs/extension-spike.md](docs/extension-spike.md)): the
YouTube page already holds the media, in the buffers its own player fills, and an
extension can copy it. So the split is the viewer's browser for YouTube and the
server for the engine, with the server asking YouTube nothing at all.

**Rejected:** an extension plus a local Python install for everyone (the engine
needs Python, ffmpeg and node, which is the install this replaces); porting the
engine to the browser with ffmpeg.wasm (a rewrite of the engine, and minutes per
render); Chrome Web Store distribution (its policy forbids enabling downloads of
streaming media, so the extension is loaded unpacked). The host is the existing
PalWorks server rather than a new one, because it already runs Caddy on a shared
network and had the cores to spare. See [docs/extension.md](docs/extension.md) and
[DEPLOYMENT.md](DEPLOYMENT.md).

---

## D-084: The extension loads WhatsApp's composer without the debugging protocol

**Date:** 2026-10-24T21:00:13+05:30
**Status:** built

`post.py` attaches the file with `DOM.setFileInputFiles` and types with
`Input.insertText`, neither of which an extension has. The extension catches the file
input WhatsApp clicks (through the prototype for a scripted click, and a capturing
listener for a label's), keeps the picker shut, fills the input through a
`DataTransfer` and dispatches `change`; the caption goes in through
`execCommand("insertText")`, the editor's own input path, so a newline cannot submit.
Verified on the owner's WhatsApp Web: composer ready in about two seconds, caption
linkified, closed again without sending.

**Never Send**, exactly as D-020 says for the page. **The WhatsApp tab is brought to
the front**, because the person pressed **Load into WhatsApp** to look at it, and a
background tab is throttled hard enough to make the composer time out. Its labels and
selectors are the ones in `post.py`; `tests/test_extension.py` fails if the two lists
drift apart.

---

## D-083: Capture from the player's own appends, recording always, parsed only in the extension

**Date:** 2026-10-24T21:00:13+05:30
**Status:** built

`recorder.js` hooks `MediaSource` and `SourceBuffer` at `document_start` and keeps a
copy of every append. Below SABR, what reaches a SourceBuffer is plain fragmented MP4
or WebM, so the hook does not care how YouTube fetched it.

- **Recording always.** The spike's hook was armed per capture and lost whatever the
  player had buffered first, which the player never fetches again. Memory follows the
  player instead: its `remove()` drops our copy of the same range, with a ceiling as
  the last resort.
- **The walk, not playback.** Pause, seek to the start, wait for our own record (not
  `video.buffered`, which includes what we might not hold) to cover the window, and
  seek to the edge whenever the player stops reading ahead. Two to eighteen seconds
  for up to 90 seconds of video. The viewer's place and play state are put back.
- **Runs, not append order.** A run is cut at every `abort()` and every header; a
  fragment whose length runs past its run was abandoned by a seek and is dropped,
  which is what corrupted the spike's first stitcher. Fragments are filed under the
  header they decode with, because the player re-initialises a buffer with a
  different encoding under the same mime type.
- **Which buffers belong to the clip.** Every MediaSource is tagged with its video id
  and whether it began during an ad; a new video's first MediaSource drops every other
  video's, ads included. Verified across in-page navigation: the clip correlated 0.94
  with the new video and 0.04 with the one before.
- **One parser.** `media.js` runs in the page and in the Node tests. The server never
  parses fragments: it receives two clean files and checks them with ffprobe (D-080).

---

## D-082: Built for a slow connection, and for Chrome stopping the extension

**Date:** 2026-10-24T21:00:13+05:30
**Status:** built

Every step resumes from stored state rather than from memory, because Chrome stops an
idle extension worker after thirty seconds and the person may close the popup.

- **Uploads** are chunks with `Content-Range`, idempotent by offset on the server: a
  chunk already held is acknowledged, an overlap keeps only the new tail, and one past
  what is held is 409 with the offset that is. The client asks how much arrived before
  it sends, so a worker that died mid chunk carries on where the server says. Chunks
  start at 256 KiB, double while each takes under two seconds, halve when one takes
  over ten, never exceed the renderer's 1 MiB, and give up after 90 seconds, before
  Cloudflare does at 100.
- **5xx is not an answer.** The renderer restarting or Cloudflare between the two is
  retried with backoff, in the upload, in the job request and in polling.
- **The download** keeps what arrived in IndexedDB every megabyte and asks for the
  rest with `Range`.
- **The job** lives in `chrome.storage.local`, the files and the clip in IndexedDB,
  and an alarm wakes the worker once a minute while anything is in flight.
- **The renderer** keeps part uploads across a restart, and reports a job interrupted
  by one as failed with that reason, so Try again sends the stored files afresh.

Measured: an 800 kbit/s connection through Cloudflare, with the worker stopped mid
upload, finished; so did 1 Mbit/s and 2 Mbit/s against a local renderer.

---

## D-081: Who may render: a token per person, and no CORS

**Date:** 2026-10-24T21:00:13+05:30
**Status:** built

A renderer anyone can reach is an ffmpeg anyone can feed with a file they made. So
the owner makes a token per person (`wastatus hosted token add NAME`), the server
stores only its SHA-256, and a revoked token stops working on the next request. No
accounts, no passwords, no email.

**No CORS headers anywhere.** The extension's worker has host permission for the
renderer and does not need them; a web page does, so a page that somehow held a token
still cannot read an answer. Everything one token made is invisible to another, and
answered exactly as a missing thing is.

**A body refused before it is read ends the connection.** Found by the suite: a PUT
to somebody else's upload was refused before its chunk was read, and the chunk was
then parsed as the next request on the same connection.

---

## D-080: A captured window is cut on its own timestamps

**Date:** 2026-10-24T21:00:13+05:30
**Status:** built

The uploads keep YouTube's own timestamps: a window starting at 1:30 is at 90 seconds
in the file, and the audio and the video files start at different moments. Measured
on a beep and flash test video: seeking the two inputs separately with `-ss` put the
sound 59 ms early; without `-copyts` each input is shifted by its own start and the
sound was 33 ms early again. `capture.section` uses `trim` and `atrim` on the original
timestamps, `-copyts` and `-fps_mode passthrough`, and the result is within half a
millisecond. Through the whole production pipeline, the finished clip's flash lands
on the frame and its beep 0.6 ms after it. YouTube's own 360p stream, which yt-dlp
gives the local tool, is 37 ms late on the same test.

Before cutting, `capture.probe` reads packets without decoding: exactly one stream of
the expected kind, a codec YouTube's player sends, and no hole longer than half a
second inside the window. The cut is no wider than the frame, 1080, because nothing
wider ever reaches a clip, and is written fast and large (`ultrafast`, FLAC audio,
which adds no encoder delay): on the production host that took a 90 second 1080p cut
from 52 seconds to 18.

`pipeline.Captured` is how the engine is given it. With one on the job, `produce` asks
YouTube nothing, not even for the artwork, which the extension uploads; the hosted
renderer refuses a card without it.

---

## D-079: Send is found by its label, because the icon has gone

**Date:** 2026-10-24T17:57:16+05:30
**Status:** built

Found while testing a Chrome extension on a spike branch, not reported as a failure.
WhatsApp Web no longer puts `data-icon="wds-ic-send..."` on the composer's Send
button: on 2026-10-24 the only `data-icon` left on the whole page was the wordmark.
`SEND_ICON` was that icon and nothing else, and it is half of the condition every
load waits for. So `--load` and `--post` waited 75 seconds for a Send button that
was already on screen, then said the editor never opened.

**Matched by label now, the icon kept first.** The media composer's Send reads
`Send 1 selected`, the text composer's reads `Send`. Both are in `SEND_ICON`.

**The "is a composer already open" check is narrower than that, deliberately.** A
chat with a reply typed into it has a bare `Send` too. Taken for a Status composer,
it would make `load_video` back out of the chat before attaching. `COMPOSER_OPEN`
recognises the text composer by its own close control,
`Close status posting view`, instead, and `cancel` clicks that control as well as
the media composer's plain `Close`.

**Verified** against the live page through the tool's own `load_video`,
`load_text` and `cancel`, without sending: media composer loaded in 3.5s with the
caption in place, text composer in 2.3s, each backed out of cleanly.

---

## D-078: The test and the drawing ask one function

**Date:** 2026-09-01
**Status:** built

From the audit asked for after D-075 to D-077 went in.

**The worst thing found was a green test.** `tests/test_safe_zone.py` is the file
that guarantees no text is ever drawn under WhatsApp's own header or into its
caption band. It did that for card mode by working the layout out a second time,
beside the copy in `build_card`, and the two agreed for as long as nobody changed
either. D-075 changed the drawing. The test kept passing, still measuring the layout
that had just been replaced: the label above the card, the top text wrapped to
whatever the label left. A guarantee about pixels, checked against a frame the
renderer no longer draws.

Nothing was broken by it, this time. That is the point. The failure mode of a
duplicated layout is not a red test, it is a green one, and green is what it had
been showing for however long it would have taken to notice.

**So there is one function.** `compose.card_words` returns both blocks and where
they go. `build_card` draws what it returns and `_card_rows` measures what it
returns, and there is no longer a second place for the arithmetic to live. Every
card-mode assertion in that file now goes through it.

**`_painted_rows` decides nothing.** It used to wrap the blocks itself, which is
what made it possible for the caller to hand it a different layout from the one
being tested. It paints what it is given and measures the ink.

**What else the audit turned up.**

| Found | Done |
| --- | --- |
| `eyebrow_room` had no callers left in the tool or the tests: it answered a question card mode stopped asking | removed, and the test that reasoned about a label above a card rewritten to ask about the card |
| The follow up text Status had no retry and no sheet row. One run can publish two Statuses and only one got either | `send_text_with_retry`, and its own row saying which it is |
| Two copies of the retry loop would have been the same mistake again | `_keep_trying`, shared, with a test that both callers use it |
| `--eyebrow`'s help in the CLI and the README still described the old placement | corrected |
| LIMITATIONS carried "top text may not fit in card mode" as a live limitation | struck through, with what replaced it |

**And what it confirmed rather than changed.** Every `D-` and `T-` reference in
every document and every source file resolves, and the five gaps in the task
numbering are the retired ones TASKS.md already explains. No relative link in any
document is broken. Nothing in `wastatus/` or `app.js` is defined and never used.
The page token is compared with `secrets.compare_digest`; `SAFE_STEM` and
`STICKER_ID` keep a request from reaching a path of its own choosing, and `_static`
is only ever handed a name from a literal allowlist. Object URLs are revoked. The
task lock makes `post` and `prepare` mutually exclusive, which is what stops two
composers being loaded at once. `sheet.py` logs a status code and the service
account address and never the bearer token, and the startup stamp still names
`.env` settings without quoting one.

---

## D-077: The preview pane says what it cannot show, instead of nothing

**Date:** 2026-08-31
**Status:** built

Reported as "if I place a GIF, the tooltip above post it correctly shows that the
clip has changed and I have to regenerate. But similar message is not showing in
the preview pane. However, if I make a change in the text input section, the
preview pane also shows a green BG warning message."

**One clip, two stories.** `drifted` knows about eight kinds of change and the Post
it panel names every one of them. `aheadOfClip`, which is what the preview pane
runs on, knew about three: the words, the background, the placement. So a sticker
put the Post it panel into a warning and left the pane beside it showing the old
frame with nothing at all to say, while a word put both into a warning. Nothing was
wrong with either panel on its own. They were answering different questions and only
one of them said so.

**Not drawn, said.** The three it is silent about cannot go into a still and that is
deliberate: the page draws stickers over the frame itself as movable things, so
drawing them into the preview as well would show each one twice, D-036; ffmpeg draws
the waveform and it moves; and switching mode changes both. So the fix is not to
draw them. It is for the pane to name what it is not showing, which is a sentence,
and which is what a person needed in order to trust the picture in front of them.

**A change it can draw wins.** Type a word after placing a sticker and the pane goes
back to previewing the words, because now it has something to show. The undrawable
note is for the case where the alternative was silence.

---

## D-076: The pencil edits the line where the line is

**Date:** 2026-08-31
**Status:** built

Reported as "if I insert a free text into the preview pane, and then click edit
(pencil) icon, I thought it will edit in-situ, but it is actually editing within the
freetext input box only. Can we create functionality such that it will edit in-situ
and parallely update within the freetext input box too?"

**D-063 was half right.** It argued for one box and no second editor, and the half
that holds is that there must be one string: two editors that could disagree about
what a line says would be worse than the walk down the page. The half that does not
is the walk. The line is on the frame, under the hand that just pressed a pencil on
it, and the answer to "retype this" was to open a section further down, scroll it
into view and put the caret somewhere else entirely.

**Both, and they are the same string.** `applyText` is the only thing that writes a
line, and it writes all three places that hold it: the decal, the box on the frame,
and the box in Extras. `from` names the one the keystroke landed in, and that is the
one not written back, because rewriting a box under its own caret sends the caret to
the end of it. Type in either and the other follows, live.

**The drawing is a PNG, so it is hidden while the input is over it.** The line on the
frame is drawn by the server in the same Pillow the renderer uses, which is what
makes the box you drag the pixels that get burned in, D-063. That picture cannot be
typed into. A real input is laid over it inside the same box, so it inherits the
box's rotation and moves with it, and the drawing is hidden for as long as the input
is open or the words would be on the frame twice. Enter, Escape or a click elsewhere
puts the drawing back, redrawn.

**The box in Extras is still the fallback and still inserts.** The decal layer is
folded away once a clip has been made, and there is then nothing on the frame to
type into; `openTextField` is the old route, kept for exactly that.

---

## D-075: One field, one place, and a line that is never dropped in silence

**Date:** 2026-08-31
**Status:** built

Two reports, one cause. "If I type something in the text at the top input box, I'm
not able to preview it." And "if I type anything into text above title, that should
come under the artwork-card / video-frame, but above the video title. Instead it is
appearing above the artwork-card / video-frame itself."

**The label meant two different things.** It hung off the **title** in video mode and
off the **card's top edge** in card mode. So one field called "Text above title" put
a line below the picture in one mode and above the artwork in the other, and the
card-mode answer is the one that contradicts the field's own name. It is anchored to
the title in both now, and in both the picture is what gives way for it: `card_floor`
is `video_picture_bottom` with a different title row, and they are one function.

**And it was eating the top text.** Card mode wrapped the label to whatever room was
left above the card, then wrapped the top text to whatever the label left. On a full
height card there is nothing left. `topline_room` returned 0, `topline_lines`
returned an empty list, and the renderer drew an empty list as nothing at all: no
gap, no ellipsis, no complaint. The words stayed in the box and went into the
sidecar, so afterwards the page compared them against themselves, found no
difference, and reported the clip up to date with a line it had never drawn.

Measured on the owner's own clip: a full height card's top edge lands on row **325**,
and one line of top text needs the row below it to be **344**. Nineteen pixels were
the difference between a line drawn and a line that did not exist.

**A fitted card shrinks.** `fitted_card_height` gives up whatever the two blocks need,
which for the case above is nineteen pixels of artwork nobody can see the loss of.
With neither field set it returns exactly what it always did, so every card ever made
is untouched: the fields are off by default and that is the whole no-regression
promise.

**A placed card is not moved, and is told about.** The owner's placement is his, so
the one case left is an artwork pinned too high for the line just typed.
`topline_dropped` answers how many lines will not be drawn, `/api/preview` returns it
as `X-Dropped-Toplines`, and the pane says so before it says anything else, because a
line you typed and cannot see is more urgent than which of your changes is on screen.
Video mode moves its own picture and a fitted card shrinks, so neither can ever reach
that sentence.

**The label needed something to be read on.** Found while reading the frames for the
above, not reported. The label is anchored to the title, and a picture somebody
placed themselves can reach down over the row it lands on. The bottom shade starts at
63 percent of the frame and ramps from zero, so at the label's row it was **alpha 1
out of 200**: white letters on a bright frame. The shade now starts `SHADE_LEAD`
above the label, but only when a picture actually reaches it, so a fitted picture,
which stops above the label, is byte for byte the frame it always was.

---

## D-074: The sheet records what went out, and only that

**Date:** 2026-08-31
**Status:** built

Asked for as a record of every Status published by this project, in a private Google
Sheet the owner already keeps, with the explicit instruction that failed posts do
not get a row.

**Which is only now an honest thing to write.** Before D-071 every row would have
said Published, including the one WhatsApp refused, because the tool had no way to
tell the two apart. The Status column is worth having because the `ack` check makes
it true.

**A service account, not the owner's own Google login.** The sheet stays private and
is shared with exactly one robot address. The credential is a file on the owner's
machine rather than a token held by a third party, and there is no consent screen to
renew: an OAuth user credential on an unpublished app expires every seven days,
which is a maintenance task attached to something that should never need attention.

**Never in the way of a post.** Every failure in `sheet.py` is caught, logged and
swallowed, the same rule `runlog` follows and the one AGENTS.md sets: a sheet that
cannot be reached costs a row, never a Status. A 401 or 403 says the service account
address out of the key file, because the fix is always to share the sheet with that
address and the address is the thing a person has to go and paste.

**Not configured is silence.** With no `WASTATUS_SHEET_ID` the module does nothing
and says nothing. Most people who clone this will never point it at a sheet, and a
warning on every post about a feature they did not ask for is noise.

**The one dependency, and why it was asked about.** `google-auth` is the only thing
added, and it pulls `cryptography`, which is not pure Python. AGENTS.md says to ask
before adding one of those, so it was asked and the owner accepted it on
2026-08-31. Current `google-auth` hard requires it for ES256 and has no pure Python
fallback any more, so the alternatives were this or hand rolling an RS256 JWT and a
PKCS#8 unwrap, which is not code worth owning for one appended row. It installs from
a wheel and needs no toolchain. The rejected alternative was an Apps Script web app
on the sheet itself: no dependency at all, but the deployment URL becomes a write
capability guarded only by a shared secret.

---

## D-073: A refusal is tried again, no answer never is

**Date:** 2026-08-31
**Status:** built

Asked for as "we need to build a retry and backoff mechanism for failures", once
D-071 made a failure something the tool could actually see.

**The two failures are not the same failure, and the difference decides everything.**
`confirm_sent` now raises one of two things:

| | What WhatsApp said | Retried |
| --- | --- | --- |
| `StatusRefused` | no, `ack -1` | yes |
| `StatusUnconfirmed` | nothing, `ack 0` or no row at all | never |

A refusal is a definite negative: nothing went out, so sending again cannot put the
same clip in front of a viewer twice. No answer is not a negative. That Status may
still be on its way, and a tool that retries it is a tool that shows people the same
clip twice to spare itself an uncertainty. So `send_with_retry` raises that one
straight through and leaves the judgement to a person.

**Twenty seconds, then forty, then eighty.** The wait is real because the point of
it is to let whatever refused the Status pass. An immediate retry puts the same
request to the same server in the same second, which is not a retry, it is the same
attempt written twice. Three goes gives up in about two minutes rather than
hammering an account the whole product depends on. `WASTATUS_POST_ATTEMPTS` and
`WASTATUS_POST_BACKOFF` move both.

**The caller is told, not left watching a hang.** `on_retry` reports the attempt and
the wait, so the page's stage line and the CLI both say what is happening during a
delay long enough to look like a crash.

---

## D-072: The caption box is named, not merely contenteditable

**Date:** 2026-08-31
**Status:** built

Found while reading the page for D-071, not reported: it had not yet cost anything.

`COMPOSER` was `div[contenteditable="true"]`, matched against the whole document.
The chat's own message box is a `div[contenteditable="true"]`. So with a
conversation open, which is how WhatsApp Web is normally left, `load_video` could
see a composer the moment it looked, before the media editor existed, and
`type_into` would then focus the first match in the document and insert the caption
into that conversation. `click_send` matches a send icon, and a chat with text in it
has one.

The failure is a YouTube link typed into somebody's group chat and sent. It did not
happen. The arrangement that produces it was live: a group conversation was open in
the posting browser while this was being read.

**Scoped by what the box is, twice.** The selector now excludes the chat box by its
`data-testid` and by its `aria-placeholder`, either of which WhatsApp could rename
on its own. And the wait is no longer for the box alone but for the box **and** the
Send button beside it: a lone contenteditable is a box that might belong to
anything, the Send button next to it is the media editor.

**Verified against the real client** on 2026-08-31 with the group chat deliberately
left open: the scoped selector matched one element, the caption landed in it, and
the chat's box was untouched. Loaded, inspected, cancelled, never sent.

---

## D-071: A Status counts as posted when WhatsApp says so, not when the composer closes

**Date:** 2026-08-31
**Status:** built

Reported as "my WA web interface shows as though the video has been published, but
in-reality it has not. I'm unable to see my own status on my mobile phone and its
views are only zero."

**The tool had never once checked.** `wait_until_sent` asked the page two things:
is the composer gone, and does nothing say "Sending". Both are facts about this
browser. Neither is a fact about WhatsApp. Every posting run ever recorded in
`logs/runs.jsonl` returned exactly `4.0`, which is the arithmetic floor of that
function: two seconds of sleep in `click_send` plus two polls two seconds apart. It
had been measuring its own sleep and calling it an upload.

**What actually happened.** The same clip was posted twice. WhatsApp Web's own
store, `model-storage` → `message`, holds both:

| Sent | `ack` | What that is |
| --- | --- | --- |
| 18:14:26 | `3` | read: it went out, and people watched it |
| 19:21:38 | `-1` | refused: WhatsApp never took it |

The tool called both of them a success in four seconds.

**`ack` is the answer.** It is the field the web client keeps for what became of a
message it sent: below zero refused, zero no answer yet, one or more accepted, then
delivered, read, played. `confirm_sent` polls it and reports the refusal as a
failure, which is what the run log and the page now show.

**Telling this Status from the last one.** Two guards, because either alone has a
hole. The row is read before Send, so the new row is the one whose id differs; and
a row older than the moment of Send is rejected, so a browser that had nothing to
compare against cannot mistake yesterday's accepted Status for today's.

**A store it cannot read is not a Status that failed.** WhatsApp reshapes its
storage without warning, and a build whose `message` store is not there would
otherwise turn every post into an error on a machine where posting works. That case
falls back to the old composer-closed wait and says in the log that the result is
unconfirmed.

**A delete looks like a Status, briefly.** Removing one writes a row under the same
`true_status@broadcast_` key prefix: a protocol message, subtype `sender_revoke`,
carrying `ack 0`. Caught the same evening, clearing the two dead Statuses. It was the
newest row in the range, so `latest_own_status` returned it and the next post would
have read its `ack 0` and reported itself unaccepted. Skipped now by type and by the
presence of `protocolMessageKey`, either of which alone would catch it, because
WhatsApp could rename one.

**Why the refusal is not diagnosed here.** Both records carry the same
`directPath`, `mediaKey`, `filehash` and the same `mediaKeyTimestamp`: the second
send reused the first send's upload rather than making a new one. That looked like
the reason, and it was wrong. A third send that evening reused the identical
`mediaKeyTimestamp` again and was accepted. WhatsApp records no reason client side,
so the cause is unknown. The tool reports the refusal, which is knowable, and says
nothing about why, which is not.

---

## D-070: One rhythm down the column of cards

**Date:** 2026-08-27
**Status:** built

Reported as "Can you equi-space all these sections?", with an arrow at the seam
between Extras and Stickers.

**There were two spacings on one unbroken run of identical boxes.** The four cards
inside the form are children of a `.stack`; the four around it, Stickers, Post it,
Recent and the frame, are items of the page grid. Both are grids of cards and both
have a gap, and the two used different tokens. On a phone they agree at 12 pixels. At
600px the grid went to 20 and the stack did not, so from a tablet up the top four
cards sat 12 apart and the bottom four 20, which is a seam exactly where the form
ends and nothing on the screen says a form ends there.

**Unified upwards, at 20.** The column already read at 20, the frame's column
declares 20, and the request was to even the spacing rather than to tighten the page.
One line: `.stack` takes the grid's own gap from 600px. The phone is untouched,
because that is where the two already agreed.

**Why it survived this long.** Nothing was wrong in either rule. Each was written for
its own container, months apart, and the mistake is only visible as the two of them
side by side down one column. A test now asserts they carry the same value at every
width, which is the only form this can be caught in.

---

## D-069: The page says each thing once, and an address carries its port

**Date:** 2026-08-27
**Status:** built

Three marks on one screenshot of the footer, and they are the same complaint three
times: a line of text in a place that is not the place it belongs.

**Where the clips are moved under the clips.** "Clips in out, newest 20 kept"
described the Recent strip from the bottom of the page, which on a laptop is below
the fold of a column that scrolls. It is a hint line inside the Recent card now, with
a rule above it, so what it says and what it is about are in the same box. The id is
unchanged, so the one line in the script that fills it did not move with it.

**The reachable line goes on a laptop and stays on a phone.** Asked as "This info is
already available under All set isn't it? We can remove it from desktop view. But keep
it at bottom of page in mobile view." It is: the health chip's "another device" row
has named that address since T-025, and names the port with it. On a laptop the chip
is on screen whatever you have scrolled to, so the footer was saying it twice. On a
phone the top of the page is a long way from the bottom, and the bottom is where you
are when you want to type that address into the phone in your other hand. So the
footer is `display: none` from 901px and untouched below it.

**The address grows a port.** The footer said `100.64.0.7` where the chip's row
said `100.64.0.7:8765`. An address without a port is not something anybody can
type into a phone, which is the only reason that line exists. Same expression as the
chip's, `location.port || "80"`, so the two cannot drift again.

**What went with it, and is not coming back for now.** "Nothing is sent until you
press Send" was the other half of that sentence, and it disappears from a laptop with
it. It was a reassurance rather than an instruction, the panel it guards is called
Post it, and the two actions in it are labelled with what they do. Worth knowing it
was dropped rather than kept somewhere new.

**It made D-067 better by accident.** The footer was most of the page that sat below
the grid, and that height is exactly what pulls a sticky column off its anchor at the
end of a scroll. See the amendment there: 74 pixels of ride up became 32, and none at
all on a tall screen.

---

## D-068: One name, one button, and a fold control you can aim at

**Date:** 2026-08-27
**Status:** built

Asked for as "for all our sections, we have a arrow symbol that indicates minimize /
maximize right? Can we make it a bigger chevron or a plus/minus button?" A chevron
was chosen over plus and minus.

**A chevron rather than plus and minus, because the rotation is the state.** Plus and
minus name the action and say nothing about which way the card is now; the chevron
turns over when the card opens, so a screen full of folded cards reads at a glance.
It was an 18px filled triangle, `arrow_drop_down`; it is now Material's `expand_more`
at 24px inside a 32px round target. The target is not a new hit area, since the whole
header has always taken the press. It is there so the header looks pressable.

**The top bar's own caret is deliberately left as it was.** It says a panel drops
down, not that a card is folded, and it is not the thing anybody complained about.

**Found while doing it, and the reason this decision has a second half.** The fetch
icon added the same morning in D-064 was given the class `.iconbutton`, which the top
bar's theme and health buttons already had. Same selector, later in the file: it took
the border and the surface background off the theme button in the top bar and shrank
its glyph from 17px to 16. Nothing raised, nothing failed, and the screenshots taken
that morning were of the cards rather than the bar.

The fix is a name of its own, `.headeraction`, not a more specific selector: two
buttons that look nothing alike cannot share one class and be kept apart by the order
they happen to appear in. A test now asserts that `.iconbutton` is declared exactly
once, because this class of mistake is silent by construction.

---

## D-067: The frame stays on screen while the answers scroll past it

**Date:** 2026-08-27
**Status:** built

Asked for as "in desktop view alone, can we make a dual column setup, such that the
right side column contains 'preview section' and is always fixed in view... the left
side column will contain all our other sections (Let's move the 'post it' section to
the left side, just above the recents section) and we'll make it such that this
column can be scrolled up / down, while keeping the right side preview section fixed."

**This fixes a real failure, not a preference.** The page already had two columns.
The sticker shelf was halfway down the left one and a sticker is placed by dragging
it onto the frame, so scrolling far enough to reach the shelf scrolled the target off
the screen. The same was true of the buttons that send: the panel below the frame is
where you decide, and the frame was the thing you could no longer see.

**Moving Post it is what makes the fixed column possible, not a separate idea.** A
frame and a Post it panel together are about 1,100 pixels; no laptop can hold that
still. With only the frame in the right column the card is about 670, which fits.

**Page scroll and a sticky column, not a scrolling box.** The obvious reading of
"this column can be scrolled" is an inner scroll container on the left, and that
brings two scrollbars, a keyboard whose Page Down depends on what has focus, and a
drag near the edge that scrolls the wrong thing. `position: sticky` gives the same
result with the page's own single scrollbar.

**The offset is measured, not typed.** The top bar is sticky itself and grows a
tagline at 600px, so the height to sit below is not a number a stylesheet can know. A
`ResizeObserver` writes it into `--topbar`. Every read of it carries this machine's
measurement as a fallback, so the first paint is right and a script that never runs
costs nothing.

**The frame shrinks to the screen rather than being cut off.** A stuck card taller
than the viewport is a card whose bottom, which is the player, cannot be reached. So
on a short screen the frame takes the height that is left and `aspect-ratio` turns
that back into a width, floored at 168px. At 1440x773 that is 277 wide with 8 pixels
of air under the player.

**The ceiling on it is 300px, and 360 once the page is at its full width.** Asked for
the same afternoon, looking at a 1920 wide screen where the frame read small for the
thing the whole tool is about. 360 rather than a little more for two reasons that
agree: it is exactly a third of the 1080 the clip is drawn at, so the preview is an
even scale of the real thing, and it is about the width of a real phone in CSS
pixels, which is what "read the caption where the viewer will" asks for. The word
preview is drawn 720 wide, so it is still sampled down. It waits for 1180px, which is
the grid's own `max-width`, because below that the extra 60 pixels would come out of
the column that holds every field, and around 900 that is the difference between two
fields on a row and one.

**The right column is sized to the frame, not to half the page.** An even split with
only the preview in it is 250 pixels of empty column taken from the fields opposite.

**What is accepted.** Over the last stretch of the scroll, where the page below the
grid is the body's bottom padding, a sticky item reaches the end of its own grid area
and rides up, and the card's header tucks under the top bar. The frame itself and the
player never do, which is what had to stay visible. The alternative is a smaller frame
at every scroll position, which is not worth it for a header that is legible again
the moment you scroll back.

**Amended 2026-08-27, later the same day.** D-069 folds the page footer away on a
laptop, and the footer was most of the page that sat below the grid. The ride up
measured 74 pixels when this was written; it is 32 at 1440x773 and **none at all** at
1920x1033, where the card is pinned for the whole scroll.

**The phone is untouched, which the request asked for.** Every rule here is inside
the 901px media query, and the panel order on a phone is decided by `order` rather
than by the DOM, so moving Post it between the columns did not move it on a phone.

---

## D-066: Make the clip goes grey when there is nothing left to make

**Date:** 2026-08-27
**Status:** built

Asked for as "Once a clip is made, can we grey out this make the clip button? We can
re-enable it only when some kind of change has happened anywhere on the setup... This
will act as subtle user feedback that whatever is shown on the preview section is
final and there is nothing more to be executed."

**It costs nothing to be wrong in one direction and a great deal in the other.** A
button left enabled when it would remake the same clip wastes a minute. A button
greyed out when it should not be is a dead end with no way past it, so everything
here leans towards enabled: an unparseable window, a start box left empty while the
link carries its own `?t=`, a clip whose end was trimmed to the length of the video,
all of them leave the button live.

**It is not the question the stale notice asks, and reusing that answer would have
been the bug.** `drifted` deliberately leaves the link and the window out, D-057:
that notice is about the take you are about to *send*, and firing it while somebody
sets up the next clip teaches them to ignore it. The button asks something else,
"would pressing this produce what is already on screen", and the link and the window
are most of that. So `settled` is `drifted` plus the video and the window, and the
one place they must never be merged is written down in both.

**The safe area guides are deliberately not a change.** They move the preview and
never the pixels. A button that came back for them would be saying that making the
clip again would produce a different file, which is false.

**One hook, not a list.** `paintStale` is called by `paintSummaries`, which is called
by `remember`, which every control on this page already calls. Hanging the repaint
there is what makes "anywhere else" true rather than a list of controls to keep up to
date as the page grows.

**The keyboard had to be stopped as well.** `form.requestSubmit()` does not ask the
submit button whether it is enabled, so ⌘/Ctrl+Enter went straight past the grey
button until the submit handler was given the same guard.

**A grey control with no explanation is a bug report waiting to happen**, so the
keyboard hint under the button is replaced by the reason while it is grey.

---

## D-065: Emoji are pictures from OpenMoji, not letters from a font

**Date:** 2026-08-27
**Status:** built

Asked for as "our free-form text, can it not accept emojis? Can we enable that
functionality in that text input box please?" It accepted them and always had: the
box took them, the sidecar kept them, and Pillow drew an empty rectangle for each
one, because the line is set in DejaVu and DejaVu has no emoji at all.

**Three ways to fix that, and only one of them keeps the promise the font is there
for.** DejaVu is vendored precisely so that Linux and macOS draw the same pixels.

| Route | Why not |
|---|---|
| A colour emoji font from the system | Noto Color Emoji on Linux, Apple Color Emoji on macOS: two different sets of drawings, so the same clip made on the two machines would not match. Pillow will only render Noto's bitmap strikes at exactly 109 pixels, and neither font is guaranteed to be installed |
| Bundle a colour emoji font | 10 MB and more in the repository, and Pillow's support for `CBDT` and `sbix` colour tables is version dependent |
| **OpenMoji pictures, chosen** | 4,495 of them are already installed for the sticker picker, already licensed CC BY-SA 4.0, already credited, and identical on both platforms. Nothing new is downloaded and nothing new is depended on |

**The rule for what becomes a picture is narrow on purpose.** OpenMoji ships a
drawing of a hyphen and of a full stop. Only four shapes are looked up: the
pictograph planes above `U+1F000`, a two letter flag, a keycap, and one of the older
symbols wearing the `FE0F` that asks for emoji presentation. A bare `(c)`, a star and
a quaver stay in DejaVu, which has all three and sets them as text. Every line
without an emoji in it renders byte for byte as it did, which was measured across 40
renders rather than argued.

**An emoji with no picture behind it is left out rather than drawn as tofu.** An
empty rectangle is not a character anybody typed. It is left out in the live preview
as you type, which is where a person can do something about it, and a line that is
*only* an unavailable emoji fails with the one sentence that fixes it: run
`scripts/setup_stickers.sh`.

**The square is hung off the letters' baseline**, one em wide and set a little below
it, so a picture sits inside the ascent and descent the line was already measured
from. That is what keeps the box the page draws around a placed line the same shape
as the picture the server draws, which is the whole contract in D-021.

---

## D-064: The video's own words, before the clip rather than after it

**Date:** 2026-08-27
**Status:** built

Asked for as "Incase I want to fetch the title, sub-title etc before creating the
clip, can we have a fetch / refresh icon here? So that I can click it, fetch these
text data from metadata of the video clip, and edit them before hand itself, so as to
save one iteration."

**The boxes have always meant "leave me empty and the video answers this".** The
answer only ever appeared in the finished pixels, so a title worth correcting, and
YouTube titles usually are, cost one render to discover and another to fix.

**It is the same question asked early, and that has to be true to the letter.** What
Fetch puts in the boxes comes back to the renderer as an *override*, down a different
path: `to_latin` over an override, `clean_title` over a fetch. If those two disagreed
by so much as a stripped dash, pressing Fetch would quietly change the card. So
`words_from_video` does not clean anything itself, it asks `title_and_channel` for a
job that overrides nothing, and the round trip is a test.

**In the Words header, where the answer lands**, not beside the link it reads. The
link's box already carries a clear cross, the value in the Words header is the
fetched words themselves, so a press on a folded card is answered without opening it,
and the card opens anyway so the words can be edited straight away.

**Synchronous, not a task.** There is no progress to report and nothing to stop, and
a page polling for two strings is more moving parts than two strings are worth. The
threading server already runs it off the page's other work. It waits
`fetch.PROBE_TIMEOUT`, 45 seconds, rather than the render's five minutes, because
somebody is watching an icon spin.

**It replaces what is in the boxes, deliberately.** The icon is a refresh, a press on
it is not something a hand does on the way to anywhere else, and the fetched words
are on the frame a moment later, so a wrong press is visible immediately.

**Two guards on a slow link.** A counter, so an older press finishing second cannot
overwrite a newer one, and the video key, so an answer for a link that has since been
retyped is thrown away rather than landing on another song.

---

## D-063: A pencil on a line of words, on hover, on a mouse

**Date:** 2026-08-27
**Status:** built

Asked for as "in our preview section, in desktop view, can we show an edit pencil
icon for text elements on hover? Clicking that pencil icon should allow editing
functionality same as the text input boxes."

**It is an offer, not a control, which is why it breaks the rule the other handles
keep.** Delete, resize and rotate appear only on the selected box: D-034 said the
resting frame shows what the viewer will see, and three circles on every line would
be furniture. The pencil appears on hover, because until you know a line can be
retyped there is nothing to select it *for*. Once it is hovered the offer is made
and the rule goes back to being right.

**It opens no editor of its own.** One box writes free text, whether the line is new
or being retyped, and selecting a line already puts its words back into that box:
that wiring is what made "one box, two jobs" work when free text was built, D-058.
The pencil takes the hand to it, and takes it the whole way: the section is opened,
the box is scrolled into view, focused, and its contents selected, so the first key
pressed replaces the line rather than appending to it. A second editor floating over
the frame would be a second thing to keep in step with the picture the server draws.

**Free text only.** There is nothing to retype about a drawing, and a fourth circle
on a sticker would be a fourth thing in the way of it.

**Mouse only.** A touch screen has no hover to reveal it with, and D-038 already
settled that a default sticker is 76 pixels to hit and two fingertip targets need 88
between them, so there is room for exactly one handle there. Nothing is lost: tapping
a line on a phone already selects it and fills the box that writes it, which is what
the pencil does in two more steps.

**Found in passing.** The rotate handle's pale icon was drawn by a bare
`:root:not([data-theme="light"])`, which matches a page whose theme is left on system
— the default — regardless of what the machine's own setting is. On a system-light
page it drew a near-white arc on a near-white circle. Both icons now declare the pale
version twice, once for the explicit dark theme and once inside
`@media (prefers-color-scheme: dark)`, which is the only thing that knows.

---

## D-062: The artwork panel is placed the same way, and the words follow it

**Date:** 2026-08-27
**Status:** built

D-061 gave video mode's picture a placement and said, in as many words, "video mode
only: a card lays out its own artwork". This is that sentence being retired. Asked
for on 2026-08-27, choosing between three ways the words could respond, as "go ahead
with option-A for card mode".

**The same three fractions, and the same control.** A centre and a width, `x`, `y`,
`size`, resolved by `compose.card_rect`. Fitted is still the default and still means
what it meant: `CARD_W` wide, as tall as the artwork's own shape asks for, a fixed
gap above the title.

**A placed panel is the fitted one scaled, not the artwork uncropped.** The height
follows `card_height`, which clamps an unusually square thumbnail into a 620 pixel
panel and centre crops it, D-016. Deriving the height from the artwork's raw shape
instead would have un-cropped a square thumbnail the moment it was dragged, and a
picture that changes shape under the hand that is only moving it is not the thing
that was picked up. Keeping the crop also makes the round trip exact: at
`size = CARD_W / WIDTH` the placed arithmetic returns the fitted box to the pixel,
so switching Fitted to Placed cannot call a clip stale.

**Option A: the words follow the panel.** The label is anchored to the panel's top
edge and the top text sits above the label, which is how card mode has always been
laid out; placing the panel simply means that anchor can now be anywhere. The two
alternatives were rejected: freezing the words where a fitted card would have put
them makes the label a stray line with nothing above it, and giving the panel its own
independent words is a second layout to keep in step.

**Following stops at both ends of the travel.** `card_words_anchor` clamps the row
the label hangs from between `CARD_WORDS_TOP` and `CARD_WORDS_BOTTOM`: past the top
the label would be drawn under WhatsApp's own header, and past the bottom it would be
drawn across the title. **Every fitted card already sits between those two**, which
is what makes this safe: `test_every_fitted_card_sits_inside_the_clamps` holds it,
and 15 fitted cards across five artwork shapes and three sets of words render byte
for byte as they did before.

**A panel over the words gets the shade video mode has always had.** The card's own
scrim goes on *before* the panel, so a panel dragged down over the title would leave
white text on whatever the artwork happens to be there. The same bottom gradient
`build_overlay` lays over the frames is laid over the card, and only when the panel
reaches past where a fitted one stops, so no fitted card is darkened by a pixel.
One function draws it for both callers.

**Card mode has no clip too old to preview.** Video mode rebuilds its frame from a
still it kept, and a clip made before that still existed cannot be shown a
background or a placement it was not made with. Card mode keeps the artwork, so the
card is simply drawn again: `preview_jpeg` passes the placement into the same
`build_card` the render calls. What it does need is the panel's rectangle in the
sidecar, because the page cannot draw a box around something whose shape it has no
way to measure, so a card made before D-062 offers to be made again first.

**The background choice stays video mode's alone.** A card composes its own
background, scrim and shadow together. The page sends one form, so the field is in
the request either way, and `App.rebuilt` now ignores it for a card: answering yes
would have frozen the clip under a still identical to itself.

---

## D-061: The picture is placed the way everything else on the frame is

**Date:** 2026-08-26
**Status:** built

Asked for as "similar to resizing text & GIF, can we create an option to resize
video / artwork?", and then: "I ideally prefer full drag-anywhere plus resize". The
picture was the one thing on the frame that was always placed *for* you:
`picture_rect` fits the frames into whatever band the words leave, centred and
clamped, and that was the only answer available.

**It becomes a rectangle at a fraction of the frame, like everything else.** A
centre and a width, `x`, `y`, `size`, which is a sticker's vocabulary and a line of
free text's. No new units, no new arithmetic, and D-024's bargain holds: the browser
drags a box over a 296 pixel preview and the renderer puts the picture on a 1080
pixel canvas with no scale factor passed between them. What it does not get is a
height, because that is not a choice: it follows the source's own shape.

**Fitted stays the default and stays untouched.** `Job.framing` is `None` for every
clip that does not ask, and that path is the code that was already there. The audit
for this pass compared the fitted rectangle against the previous commit's for seven
source shapes and three sets of words, and the blurred filter graph string as well:
both identical.

**`pad` had to go.** The black background was one `pad`, which was cheaper than an
overlay and was correct only while the picture was guaranteed to sit inside the
frame. A placed picture may hang off any edge or be larger than the frame, and `pad`
takes neither a negative offset nor an input bigger than its output. Both fills are
now a background layer with the picture overlaid on it, which is one shape for both
and clips what hangs off. Verified against ffmpeg on four placements, in bounds and
out, on both fills.

**The box on the page is deliberately not a `.decal`.** The sticker gestures find
their target with `closest(".decal")`; a picture box carrying that class would be
dragged, turned, deleted and posted as a sticker. It is its own element with its own
class, its own solid accent outline against the sticker's white dashes, and one
corner grip. The frame holds one selection, so picking it puts a sticker down and
picking a sticker puts it down: two selections would be two answers to an arrow key.

**It is not previewed while it moves.** The picture lives under the words, so seeing
it move means the server rebuilding the frame from the still it kept. The box is the
truth while the hand is moving and it is exact; when the hand comes off, the frame is
drawn again through the same debounce the words already use. What that rebuild cannot
invent is picture the still never had: a clip whose picture already hung off the frame
was stored clipped, so moving it back inside shows black where those rows were cut.
The clip itself has them, because ffmpeg starts from the video rather than from a
still of it.

**Placing needs a clip on screen**, because the box's shape is the source's shape and
nothing else on the page knows it. A clip made before the rectangle was recorded says
so and offers to be made again.

## D-060: The keyboard drives the frame, and one slot of undo comes with it

**Date:** 2026-08-26
**Status:** built

Asked for as "while I'm resizing, dragging, deleting elements on our preview, I
would like to use keyboard buttons such as delete, Esc". A placed thing is a box
with a position, a size and an angle: three numbers, and a keyboard is better at
numbers than a hand is. Half a percent of a 300 pixel frame is one and a half
pixels, which is not a drag anybody can make.

**Two ways in, meeting at `picked`.** Click a box, because that is how a hand gets
to one, or tab to it, which is the only route for somebody not using a pointer.
Focus and selection are the same thing: focusing a box selects it, and clicking one
focuses it, which the prevented press would otherwise have skipped. The keys are
handled on the document and act on `picked` rather than on whatever holds focus, so
they keep working after a click that lands on the frame's background.

**Arrows nudge, Shift goes further, `+` and `−` size, `[` and `]` turn, Delete
removes, Escape puts it down.** The steps are fractions of the frame, the same units
the renderer is sent, and they are clamped to the same bounds the server clamps to.

**Nothing fires while you are typing.** `inAField` is the guard the paste handler
already uses. Delete inside the free text box has to stay Delete, and an arrow key
in the caption has to move the caret.

**One slot of undo, and every removal goes through it.** The cross has always
removed without asking, on the grounds that a sticker is one tap to put back from
the shelf, D-038. A line of free text is not: it is retyped. And a key is pressed by
mistake in a way a cross is not. So `removeDecal` records what it took and ⌘Z puts
it back where it was, whether it went by the key, the cross or the Remove button.
One slot rather than a stack, because this is a frame with a handful of things on
it, not a document.

## D-059: Black is an option behind the frames, and it lives in Look

**Date:** 2026-08-26
**Status:** built

Asked over a screenshot: "currently the same video is run in BG, in a blurred
fashion, isn't it? Can we have an option to keep this blurred functionality or keep
a simple plain BG?" Yes: `picture_steps` splits the source, blurs one copy to cover
a 9:16 frame, darkens it, and lays the real frames on top.

**Black is one `pad`, not a black source overlaid.** A `color` filter has no natural
end, so overlaying one needs a duration, a frame rate and a `shortest` to stop it,
and a source with none of those is how a render hangs. Padding the scaled picture
out to the frame puts the same pixels in the same places with none of that. It also
came out **27 per cent smaller** on the first clip measured, 439 kB against 598 kB,
because there is nothing moving outside the picture for the encoder to spend on:
against WhatsApp's 10 MiB ceiling, that is bitrate handed back to the picture.

**It is in Look, not beside Safe areas**, which is where it was asked for. Safe
areas is a view toggle: it changes the preview and nothing else, instantly. This
changes the clip and does nothing until the clip is made again. Two switches that
look alike and act differently teach the wrong thing about both, so this one sits
with the other control that changes the clip.

**Video mode only.** A card composes its own background: a blurred cover of the
artwork, a scrim heavier at the bottom, and a shadow that keeps the card from
reading as a hole cut into its own blur. Swapping that for black is a redesign of
the card rather than a setting on it, and it can have its own decision if it is ever
wanted.

**Previewing it meant building the frame again.** The words are drawn over what is
already on screen, which is why they preview in 0.1s. A background is under
everything, so the only way to show one is to rebuild the frame: `render.recompose`
does it in Pillow from the still already kept per clip, keeping the picture's own
pixels and replacing what is around them. Black is exact. Blurred is close, because
Pillow's kernel is not ffmpeg's, and that is the right trade for a preview. It needs
the picture's rectangle, which is why the sidecar now records the whole rectangle
rather than only the top edge the words are anchored to. A clip made before that was
recorded says so rather than showing a picture identical to the one underneath.

**The hole in the word preview closes while the background differs.** T-036's still
is cut open so the clip plays through the middle of it. With a different background
around the hole, the clip would play its old one through it and the seam would run
across the picture, so `moving_band` answers with nothing while the two disagree.

## D-058: Free text is drawn by the server; the browser only places the picture

**Date:** 2026-08-26
**Status:** built

Asked for as "a new button called Free Text, which can be moved around and resized,
like our GIF image, and can also be inserted multiple times". The dragging was never
the question: `stickers` already places a rectangle at a fraction of the frame, and
D-024 is why that works at all. The question was who sets the words.

**The browser could.** A `<div>` with the font on it, dragged around, and the server
laying the same line out again at render time. It is less code and it types with no
round trip. It is also the one thing this codebase has refused since D-001: two text
engines, asked the same question, giving answers that differ. The browser breaks a
line where its own metrics say to, kerns with its own rasteriser, and rounds to CSS
pixels. The box you dragged would not be the pixels ffmpeg burns in, and you would
only find out after the render you were trying to avoid.

**So the server draws it and the page places the drawing.** `freetext.render` makes
a transparent PNG of one line; `POST /api/text` hands it to the page, which puts it
in the same `.decal` box a sticker goes in; `stickers.paste` calls the same
`render` again at the frame's own scale when the clip is made. One layout engine,
two callers, and to the page it is a rectangle like any other.

**The size is the width of the line, not the size of the face.** Dragging the corner
sets a fraction of the frame, exactly as it does for a sticker, and the face follows
from it: a longer line at the same width is set smaller. That is the same bargain a
text box makes in any design tool, and it is what lets `paste` stay one code path.

The cost is a round trip per edit, debounced at 300ms, which is the same shape as the
word preview in T-036 and is not noticeable on loopback. The picture is cached by its
words, so dragging one never fetches anything.

## D-057: The form owns one column, the clip owns the other

**Date:** 2026-08-25
**Status:** built

Asked plainly: "move the stickers section to where Make the clip is now, and move
Make the clip into the Post it section."

It is a better split than the one it replaces. Everything that **goes in** is now on
the left, stickers included, because a sticker is an input like a title is. Everything
that **comes out** is on the right: the frame, the button that makes it, and the clip
that lands under it. Make the clip sitting at the top of Post it means the press and
its result are in the same panel, a few pixels apart, instead of in opposite columns.

**Two couplings crossed a boundary and neither would have raised anything.**

A submit button only submits the form it belongs to, and inside `<form>` that is
implicit. Moved into Post it it is outside, so the association is written down as
`form="form"`. Without it the button renders identically, takes the press, and does
nothing. The keyboard shortcut was already safe: it calls `requestSubmit()` on the
form rather than clicking the button.

Stickers went **beside** the form rather than into it. The panel holds a text input,
and a lone text input inside a form makes Enter submit it, so searching for a sticker
and pressing Enter would have started a render.

**The phone keeps the order it had, which is not the DOM's.** Read straight through,
the DOM now gives form, stickers, recent, preview, post: the shelf above the frame it
decorates, and Recent in the middle of the run. Both column wrappers dissolve to
`display: contents` below 901px, so every panel is a grid item in its own right and
`order` puts them back as form, preview, stickers, post, recent. The wrappers return
as real columns at 901px, where they are still needed: without them the panels pair
up into shared rows and each column is padded to the height of the one beside it,
which is what the wrappers were introduced to avoid.

---

## D-056: A clip that no longer matches the form says so where you would act on it

**Date:** 2026-08-25
**Status:** built

The owner placed a GIF, posted, and found no GIF in what he had posted. Nothing was
broken: he had posted the clip made *before* the GIF was placed. The log has it
exactly, a render at 19:43 whose sidecar records `"stickers": []`, that clip posted at
19:53, and the GIF placed after.

**The page did say so, in the wrong room.** The Stickers panel reads "Make the clip
again to draw these into it" whenever there are unrendered stickers. Post it is a
different card, with its own four buttons, and nothing there knew the clip was older
than the form above it.

So the notice moved to where the mistake is made: directly above Load, Send, Download
and Delete, naming what has changed since the clip was made.

**A comparison, not a flag.** `current.job` is the record of what actually went into
the clip, so the answer can be worked out whenever it is wanted. A flag has to be set
from every place that can change something, and the place that gets forgotten is the
place the page then lies about. This is the same reasoning as D-055's armed stem.

**What counts as drift, and what deliberately does not.** The five words, the
stickers, the waveform and the mode: everything drawn into the pixels. Not the link
and not the window. Pasting the next link while the finished clip is still on show is
the ordinary way to use this page, and a warning that fires on ordinary work is
learned as noise and then not read on the day it matters.

**It warns, it does not block.** One press explains and the second goes ahead, the
same two press rule as Delete and the tile cross. Sending the older take is sometimes
exactly what was meant, and a page that refuses is a page you have to work around.
Download needed the click event as well as the button: the other two are buttons whose
handlers return early, while Download is an anchor the browser follows unless the
event is cancelled.

---

## D-055: A clip is thrown away from the tile, and it asks twice

**Date:** 2026-08-25
**Status:** built

Asked over a screenshot with a box drawn on the corner of a Recent tile: "please
introduce a close button (cross-mark) here, so that I can delete those variants that
I don't want. Please design it nicely for both mobile and desktop views."

**Nothing was missing from the server.** `/api/clip/delete` has existed since T-016,
it deletes the whole file group rather than the mp4, and it refuses while WhatsApp is
being driven. What was missing was a way to reach it: the only route to Delete was to
load a clip into the player first, which is three presses and a repaint to throw away
a take you can already see is wrong. The strip is where variants are compared, so it
is where they should be dropped.

**It asks twice, and deliberately not with a dialog.** The same rule as the Delete
button under the player: a dialog is dismissed by habit and a control that has
visibly changed its mind is not. The cross becomes a filled "Delete?" pill and
disarms itself after four seconds, so a stray press cannot be completed by a later
stray press. Only one tile can be asking at a time, because two armed crosses on one
strip is two ways to delete the one you did not mean to.

**Which tile is asking is held in a variable, not in the DOM.** The strip repaints
itself whenever the clip list changes, which throws the buttons away, and the
element that was asked is not the element that answers. Holding the stem instead
means the question survives a repaint.

**The tile stopped being a `<button>`.** A button nested in a button is invalid and
no browser reports it: the parser silently unnests them into siblings, which lays
the cross out beside the tile rather than on it. The tile is a `<div>` holding two
buttons now, one for opening and one for deleting.

### What "nicely for both" came to

| Decision | Why |
|---|---|
| Always drawn, never revealed on hover | a phone has no hover, and a control only a mouse can find is one half the devices cannot |
| A hairline ring around the disc | the top of a thumbnail is where the title is drawn and so is usually dark, and a dark disc alone disappears into it |
| 22px disc, 24px on a coarse pointer, hit area grown to 44 by a transparent `::before` | the tile is 116px wide and a quarter of it taken by a cross is a cross that has become the picture. The same trick the sticker handles use, D-038 |
| The "saved on this device" tick moved to the left corner | both are 20-something pixel badges, and they were both claiming the right one |
| The armed fill takes its ink from `--danger-bg` | `--danger` is a dark red in the light palette and a pale pink in the dark one. White on it reads in one and not the other |
| Its own error line under the strip | delete is refused with a 409 whenever WhatsApp is being driven, and the Post panel is collapsible and at the other end of the page on a phone |

---

## D-054: Python owns the picture's rectangle, so text can be anchored to it

**Date:** 2026-08-25
**Status:** built

D-053 put the top text at a fixed `TOPLINE_TOP`, 30 pixels under `SAFE_TOP`, and the
owner looked at the result and asked the right question: "should it start alignment
from the bottom? This way our probability of collision with header elements will
decrease."

**Measured on his own clip.** Two lines of top text at 260 to 348, the picture
starting at 626. Thirty pixels of clearance from WhatsApp's header band and **278
pixels of nothing** between the words and the picture they belong to. Every other
block above something in this layout is anchored by its bottom, for exactly this
reason: length grows upwards, into empty air, rather than downwards into whatever it
was meant to sit above. The top text was the one that was not.

**The obstacle was that nothing in Python knew where the picture was.** It was
decided at render time by an ffmpeg expression,
`min((H-h)/2, floor-h)`, from a source shape only ffmpeg had looked at. A coordinate
the renderer keeps to itself cannot be drawn against.

So the arithmetic moved: `render.picture_rect` fits the source into the band and
returns an exact `Picture`, and the filter graph is handed numbers instead of an
expression. That is a better shape anyway. An expression cannot be unit tested, only
rendered and measured, and the same fit now answers two questions instead of one.
`tests/test_safe_zone.py` asserts the rectangle Python computes is the one ffmpeg
paints, at five aspect ratios, which is the seam this decision creates.

The block now hangs `TOPLINE_GAP` above the picture's top edge, clamped at
`TOPLINE_TOP` so a picture that starts high cannot drag it off the frame. On that
same clip it moves from 260..348 to 508..596: 278 pixels of clearance from the
header instead of 30, and the text against the picture instead of adrift above it.

**One measurement, used twice.** The crop probe already scanned three frames; it now
returns the size it found as well, so the rectangle costs nothing extra.
`compose.build_overlay` takes `picture_top`, and the clip's sidecar records it,
because the live word preview draws over a still of the frames and has no way to
measure them. A clip made before that was recorded passes `None` and gets the old
fixed position, which is where that clip's own text actually is.

---

## D-053: Text at the top is its own field, not a placement for the label

**Date:** 2026-08-25
**Status:** built

Asked over a screenshot with a box drawn around the empty band between WhatsApp's
header and the top of the video: "how to insert text here?". Nothing drew there. In
video mode the frames are centred, so there is air above them and air below them,
and every word this tool draws lives at the bottom.

**Two ways to answer it**, and the choice matters more than it looks. A placement
toggle on the existing label is less user interface: one box, one choice, no new
field. A separate field is more, but it lets a clip carry **both**, a hook at the top
and the line that introduces the title at the bottom, which is exactly the shape of
the reel this was asked for. The owner chose the field.

It is drawn at `TOPLINE_TOP`, 30 pixels below `SAFE_TOP`, wrapped to three lines, at
32 pixels against the label's 28, because it stands alone up there rather than
leaning on the title. It carries the same letterspacing rule: tracked while it is
short enough to read as a label, plain once it is a sentence.

**The frames give up room at the top the way they already do at the bottom.**
`compose.video_picture_top` is the ceiling, `video_picture_bottom` is the floor, and
`render.picture_steps` takes both. (D-054 later moved that pair into
`render.picture_rect`, which takes the same two rows and returns an exact rectangle;
`picture_steps` is handed the result.) Neither moves unless the words ask it to: a clip
with no top text renders exactly as it did. Measured on a square source: it started
at `SAFE_TOP`, 230, and now stops at 388 with two lines of top text above it.

**Card mode shares the band rather than owning it.** The label above the card is
anchored to the card and cannot move, so it is placed first and the top text takes
what is left above it. With an unusually square artwork, where the card is at its
tallest and its top is at 325, what is left is nothing and the top text is not drawn.
That is recorded in [LIMITATIONS.md](LIMITATIONS.md) rather than solved: card mode
already has a picture up there, and the case it fails in is the one where there is
genuinely no room.

---

## D-052: The label above the card is drawn in video mode too

**Date:** 2026-08-25
**Status:** built

Asked over a screenshot with a sentence typed into the box and nothing on the
preview: "won't these sections work for videos?", pointing at Footer and at Label
above the card.

**Half of it already worked.** The footer draws in both modes and always has.
`build_overlay` passed `eyebrow_top=None`, and `_draw_text_layer` skips the eyebrow
when that is None, so video mode took the sentence and threw it away: no error, no
note, an empty preview. A field on the page that quietly does nothing is worse than
no field, because you assume you typed it wrong.

It was written that way for a reason that was true at the time. The eyebrow's whole
definition was "above the card", the position was derived from the card's top, and
video mode has no card. What was missed is that it does have a words block, and
above that block is the same idea.

So it is drawn at `VIDEO_EYEBROW_TOP`, one `EYEBROW_GAP` above the title, exactly
the gap it would have used above a card.

**The frames pay for it, and only when there is one.** `compose.video_picture_bottom`
takes the text rather than being a constant: with a label the picture's floor rises
from 1244 to 1174, and without one it does not move at all. Reserving 70 pixels of
picture on every clip for a line that is off by default would be the wrong trade on
almost every clip. This is why `render.picture_steps` and `render_video_clip` take a
`floor` instead of importing one. (D-054 moved that argument to `picture_rect`, which
is where the fitting now happens.) See D-049 for the floor itself.

**The field's wording follows the mode**, "Label above the card" and "Label above the
words", because the old wording was itself part of why this read as card-only.

### Amendment, the same day: it also has to be wrapped

Drawing it was not enough, and the first sentence typed into it proved that. "PoV:
Describe a bee (you) who just saw a blooming flower (Krishna) that is ripe with
nectar", 91 characters, came out **1989 pixels wide in a 1080 pixel frame**, centred,
with 454 falling off each side. Reported as "still not able to see anything", which
is exactly right: the beginning and the end were both off the frame and the middle
was a fragment.

The eyebrow was the one line of this layout that had never been wrapped, because
`NOW PLAYING` never needed it. It wraps now, to three lines at most, and:

- **The tracking goes past 28 characters.** Letterspacing is what makes a two word
  label read as deliberate. On a sentence it is noise, and it was also a third of
  the width that put this off the frame.
- **The block is anchored by its bottom**, so a second line grows upwards into empty
  air and nothing below it moves. A single line lands on exactly the y it always did,
  so no existing clip changes.
- **Card mode ellipsises, video mode moves the picture.** The card is already as tall
  as its artwork asked for, so a label above it has only the room left before
  `SAFE_TOP` and is cut to fit. Video mode has no card, so the frames give way
  instead: one line costs them 70 pixels, two costs 110.

Measured on a real render afterwards: no label, picture 636 to 1243; one line, 566 to
1173 with the label at 1214; two lines, 526 to 1133 with the label at 1174.

### Second amendment: the second line and the footer were the same bug

Reported the same afternoon as "text wrap is happening here, but not here", of the
label against the two fields below it. Both were single unwrapped `draw.text` calls.
An ordinary channel name, "Sounds of Isha Official Channel for Devotional and
Classical Music", measured **1253 pixels** in a 1080 pixel frame, and a footer of
similar length 1209. Only the title had ever been wrapped.

They wrap now, but not to a fixed allowance, because there is not one to give. The
words block runs from `title_top` down to a floor, `WAVE_TOP` in card mode and
`SAFE_BOTTOM` in video mode, and a three line title has already spent almost all of
it. So each block takes **what is left after the one above it**, up to two lines,
and is ellipsised beyond that. The footer keeps one line back for itself while the
channel is measured, or a long channel name would eat the whole remainder and leave
the footer nowhere to go.

The title is never shortened to make room for either. Trading a line of the song's
own name for a line of the channel's is the wrong way round.

---

## D-051: The page opens in the browser that holds the rest of the session

**Date:** 2026-08-25
**Status:** built

D-050 gave the posting browser a tab naming this session's port. It left the
obvious loose end: the page that port serves opened in whatever the desktop calls
the default browser, which on this machine is a different Chrome entirely. One
window said "this session is on 8765" and the thing on 8765 was in another window.

The page is now Chrome's second URL, between the label and WhatsApp Web. The label
stays first, so the window title keeps naming the port, which is what D-050 was for;
the page is one tab across.

**A browser that was already running never saw a command line**, so it is asked over
the debug protocol instead, with `PUT /json/new`. `PUT` and not `GET`: Chrome 111
stopped answering `GET` there to close a hole where any page in that browser could
have opened tabs in it.

**Falling back is not an error.** If there is no browser to start, or the tab is
refused, the page opens in the default browser as before. The page has to open
somewhere, and where it opened is visible from the fact that it did.

---

## D-050: A session label tab, because a port is only useful where you can read it

**Date:** 2026-08-24
**Status:** built

`wastatus serve` prints its port to the terminal it was started from. Ten minutes
later that terminal is behind three other windows, and the machine has several
Chromes on debug ports belonging to several tools. Nothing on screen said which
window was this one, or which port its page was on.

So the browser this tool starts gets one extra tab, first in the strip, holding a
page whose whole content is the answer. The `<title>` is the part that does the
work: it puts `● 8765 · wastatus` in the window title and in the task bar, where it
is readable without opening anything. The body names the page URL, the tailnet URL
when there is one, the Chrome debug port, the posting profile and the output folder.

**A file, not a route.** It would have been less code to serve it at `/ports`, and
it would have been wrong: the label has to outlive the server. Stop `wastatus` and a
served label turns into a connection error, while a file still says what the session
was. It lives in `~/.cache/wastatus`, one file per page port so a restart overwrites
rather than accumulates, and `WASTATUS_CACHE_DIR` moves it.

**First tab, not last.** The window title follows the active tab, and the label is
only worth having if it is the one being read. That costs nothing, because
`Page.__init__` calls `Page.bringToFront` before it touches anything: the posting tab
is foregrounded when it is used, whether or not it started that way.

**Never fatal.** A cache directory that cannot be written logs a warning and the
browser starts anyway. The tool works perfectly without a label.

---

## D-049: Video frames are centred, but never under the words

**Date:** 2026-08-24
**Status:** built

The owner noticed the asymmetry: "in artwork mode the artwork is moved up
accordingly, so the title does not come upon it. In video-frames mode the video is
vertically centred, and a part of the title overlays the video."

**Both halves were true, and the diagnosis was not quite the stated one.** Card mode
is safe by construction: `card_box` anchors the card `CARD_GAP` above `CARD_TITLE_TOP`,
so whatever the artwork's shape, the words start below it. Video mode centred the
frames in the whole 1080x1920 canvas with `overlay=(W-w)/2:(H-h)/2`, an expression
that knows nothing about the words at all.

So the trigger is the source's shape, not the title's length. Centring is safe only
down to 5:3, and a longer title just puts more lines on top of what was already
being written on:

### Table D49-1: where a source's own picture ended, measured 2026-08-24

| Source, after letterbox trimming | Drawn height | Bottom edge | Title starts 1284 |
|---|---|---|---|
| 2.35:1, the owner's last two posts | 460 | 1190 | clear by 94 |
| 16:9 | 608 | 1264 | clear by 20 |
| 4:3 | 810 | 1365 | **81 into the title** |
| 1:1 | 1080 | 1500 | **216 into the title** |
| 9:16 | 1920 | 1920 | **the whole block** |

**The fix is a floor, not a layout.** `min((H-h)/2, VIDEO_PICTURE_BOTTOM-h)` keeps
the centred position for anything that already cleared the words, which is the whole
back catalogue, and lifts only what would have been written on. Giving video mode
the card's structure instead, always sitting in the band above the title, would have
moved every existing 16:9 clip up by 300 pixels for a problem it does not have.

**Too tall to fit is fitted, not cropped.** A square or portrait source is scaled
into the 1080x1014 band and shows blurred fill down its sides. Cropping it to the
band's shape, which is what the card does with an unusually square thumbnail, would
take the top off somebody's head. A margin is a worse picture; a crop is a wrong one.

`background_still` shares the same steps, so the still the live word preview draws
over cannot disagree with the clip it is previewing.

---

## D-048: The words are previewed by Pillow; only the clip needs ffmpeg

**Date:** 2026-08-22
**Status:** built. [TASKS.md](TASKS.md) T-036

The owner asked, over a screenshot of a title he had just edited: "how to refresh
the preview alone without regenerating fully?"

**The honest answer was that the words are pixels.** ffmpeg draws them into the
video and there is no editing them afterwards. What made that answer unsatisfying
was the price, measured from his own `runs.jsonl`:

### Table D48-1: where a re-make actually goes

| Clip | probe | download | render | total |
|---|---|---|---|---|
| 30 seconds, video mode | 1.7s | 11.4s | 16.6s | 30.7s |
| 90 seconds, video mode | 1.4s | 12.3s | **52.5s** | 66.5s |

**So caching the download was the wrong idea**, which is worth recording because it
was the obvious one. It is under a fifth of the wait. The render is the wall, and
nothing makes ffmpeg draw a 90 second video quickly.

**But seeing the words needs no video at all.** Both modes already build their text
with Pillow, in a shape that can simply be run again:

| Mode | What draws the words | Measured |
|---|---|---|
| card | `build_card`, the whole composition | 0.86s |
| video | `build_overlay`, a transparent text layer composited at 0:0 | 0.10s |

**The same functions the render calls, so the preview cannot drift from the clip.**
A second implementation that drew "roughly the same thing" would be a second thing
to keep in step, and the first time it fell behind nobody would know which was
right.

**What has to be kept is the picture underneath, and it is different per mode.**
Not the finished clip: that has the old words burned into it, and drawing new ones
over it would show both.

| Mode | Kept beside the clip | Why that and not something else |
|---|---|---|
| card | `<stem>.art.jpg`, about 74 kB | the card is a Pillow render of the artwork. Keeping the artwork means the card is built again exactly, blur, shadow and all |
| video | `<stem>.base.png`, about 640 kB | one frame with the blurred fill applied and nothing of ours on it. Written by the same filter chain the clip uses, minus the overlay |

Both are sidecars in `retention.SIDECAR_SUFFIXES`, so they go when the clip goes.

**The still is written by a second ffmpeg call, not a second output of the render's
own graph.** One graph would be cheaper by a decode. It would also mean a preview
still that failed to write taking the clip down with it, and the clip is the thing
that matters. It is wrapped and logged, and a failure costs the preview for one
clip.

**720 pixels and JPEG, not full size and PNG.** A full size PNG measured 1254 kB for
a card and 694 kB for a video frame, redrawn every time typing stops, on a page a
phone reads over a tailnet. The box it goes in is 300 pixels wide. JPEG at 720
measured 73 kB and 70 kB.

**No stickers are drawn into it.** The page draws them itself, live and draggable.
Drawing them here as well would show every one of them twice.

**It says what it is, on the picture.** A preview that quietly replaced the clip
would be a lie about the file on disk, so a band across the top reads "Preview of
the words. The clip still has the old ones", and pressing play hides the still and
shows the actual video.

**What it does not show.** A card clip has a waveform drawn under the title by
ffmpeg, from the audio. A still cannot have one, so that band is empty in the
preview. This is a preview of the words, not of the frame.

---

## D-047: The GIF shelf is sized for the screen that asked, and the provider is a session choice

**Date:** 2026-08-22
**Status:** built. [TASKS.md](TASKS.md) T-034

Two things the owner reported on the same screenshot: the previews were too small to
judge, and there was no way to change provider without editing a file.

**A drawing reads at any size and a GIF does not.** The shelf was one grid of 52
pixel cells for both, which is right for 4,495 OpenMoji glyphs and useless for
somebody's video. His words: "I'm unable to judge them". Cells are now sized per
source, 92 pixels for GIFs on a phone and 132 on a wide screen, with a taller shelf
so more than one row shows.

**Bigger cells made the thumbnails worse before they made them better.** The first
version simply grew the cell, which upscaled a 127 pixel image into a 172 pixel box.
Both providers were then measured properly for the first time:

### Table D47-1: what each provider actually offers, measured 2026-08-22

| Provider | small preview | large preview | full |
|---|---|---|---|
| KLIPY | `xs` 127x90, 134 kB | `sm` 220x157, 376 kB | `md` 498x355, ~2343 kB |
| GIPHY | `fixed_width_small` 100x96, 85 kB | `fixed_width_downsampled` 200x190, **121 kB** | `downsized`, capped at 2 MB |

GIPHY's downsampled rendition is the bargain of the two: twice the resolution for a
third more bytes. KLIPY's `sm` costs nearly three times its `xs`, which is why the
size is not simply raised for everyone.

**So the browser says which it wants.** `/api/gifs?big=1`, set from
`matchMedia("(min-width: 901px)")`. Only the browser knows how big its cells are,
and the phone reads this page over a tailnet where three times the bytes is felt.
Deciding it on the server would mean either a soft desktop shelf or an expensive
phone one.

**The provider chooser switches for the session and never writes `.env`.** The file
stays the default and a restart returns to it. A web request that can rewrite the
file holding the API keys is not a trade worth making for a choice this cheap to
repeat, and the failure mode of a half written `.env` is losing both keys.

**Only providers with a key are offered.** Choosing one without a key would switch
the feature off and leave the page with nothing to say about why, so `available()`
filters on the key rather than on the name.

**Desktop only, by instruction and by judgement.** On a phone this is a row of chips
between you and the thing you came for, and `.env` has already chosen. The owner
asked for it in the desktop view and said Gboard is enough on the phone.

**The paste box is gone from the wide view, and the hint stays.** That box is
`contenteditable` for one reason: a phone keyboard decides whether to offer its GIF
tab from what the focused element accepts, and only a rich text target gets it,
D-036. With a mouse there is no keyboard GIF tab to reach for and Ctrl-V already
works anywhere on the page. The owner's question, "this entire section is not useful
in desktop view, right?", was correct.

---

## D-046: The words on the card belong to a video, and the page remembers which

**Date:** 2026-08-22
**Status:** built. [TASKS.md](TASKS.md) T-035

Reported as: make a clip, paste a different link, press the button, and the new video
comes out under the old video's title.

A guard for this already existed and missed three ways, which is worth recording
because each was a different kind of mistake:

### Table D46-1: three holes in one four line guard

| Hole | What it was | Why it mattered |
|---|---|---|
| It asked the wrong thing | the condition was `current.job.url`, the clip on screen | after a reload there is no clip on screen, but `restore` has already put the previous words back from localStorage. Nothing was compared, so nothing was cleared. **This is the one he hit** |
| It compared raw strings | `youtu.be/X` and `watch?v=X` are one video and two strings | pasting the same song in the other spelling threw away words that belonged to it |
| It cleared half the words | title and channel, not footer and eyebrow | those belong to a song just as much |

**So the words carry the video they were derived for.** `wordsFor` holds the video
id, is set wherever the boxes are filled from a job rather than by hand, and is
stored with the form, so it survives a reload. Two spellings of one song are one
song: `youtu.be/X`, `watch?v=X`, `/shorts/X`, `/embed/X` and `/live/X` all reduce to
`X`, and anything unrecognised falls back to the address, which is no worse than
what it replaced.

**Checked twice, on input and again at the press.** The input event covers typing
and pasting. The press covers everything that can put a value in a box without one:
autofill, a restored session, a browser handling a paste its own way. The press is
the last moment it can be caught, and it is the moment where getting it wrong is
expensive, because the answer is a 30 to 66 second render.

**It says so rather than doing it silently.** Clearing four boxes under somebody's
hands with no explanation is its own bug. The press prints a notice naming what
happened and why.

**The window is deliberately left alone.** Start, length and end survive a link
change, because the owner posts the same window from many videos and re-typing 0:00
to 0:30 every time would be a worse tax than the one being removed. Words are
derived from a video; a window is a decision about a clip.

---

## D-045: A debug port is described by whoever holds it, not by whether it answered

**Date:** 2026-08-22
**Status:** built. [TASKS.md](TASKS.md) T-031

An afternoon was lost on 2026-08-20 to this message:

> Chrome is on port 9225 but no WhatsApp Web tab is open in it. Open
> https://web.whatsapp.com and log in first

Every word of it was true and the advice was useless, because the browser it was
describing belonged to an IDE. The owner had a logged in WhatsApp Web open the whole
time, in a different browser. The message read as "log in again" when the answer was
"that is not your browser".

**So the messages name the process.** `port_owner(port)` reads `/proc` for a process
whose command line asked for that debug port, and reports it by its **profile**:
`chrome, profile antigravity-chrome-profile-someone (pid 151793)`. The profile
is the identifying part. A port is a number anybody can take; a profile is whose
browser it is.

**Reading /proc rather than asking who holds the socket**, because the useful
question is who *asked* for the port. A browser that lost the race and fell back to
IPv6 only still answers that question, and that browser is exactly the one somebody
is confused about.

### Table D45-1: the three silences, and what each one now says

| Situation | What the old message said | What it says now |
|---|---|---|
| Nothing is there | `no Chrome answering on 127.0.0.1:N` | unchanged. It was right |
| A browser asked for the port and only bound `[::1]` | `no Chrome answering on 127.0.0.1:N` | `port N is only half open`, and names the browser that took IPv4 |
| A browser is there, holding somebody else's tabs | `no WhatsApp Web tab is open in it` | the same, plus `That one is chrome, profile X` |

**The half open case is the one worth the code.** Chrome, given a port something
else already holds, prints `bind() failed: Address already in use (98)`, carries on,
binds IPv6 only, and then prints `DevTools listening on ws://[::1]:9225`. That last
line reads as success. Nothing in this tool could see it, because `_cdp_get` asks
`http://127.0.0.1:{port}` and always will: a name that resolved to both families
would make which browser gets driven a matter of resolver order.

**Rejected: parsing `ss -ltnp`.** It answers a different question, needs an external
binary, and says nothing about a browser that failed to bind. `/proc` is already
there and holds the profile, which is the part a person recognises.

**Chrome flattens its own argv.** It rewrites the command line into a single space
separated string, so the NUL separators `/proc/PID/cmdline` normally holds are not
there. A reader that only splits on NUL sees one enormous token and matches nothing;
this was written that way first and found nothing on a machine where two debug
browsers were plainly running. Both shapes are handled, and both are tested.

---

## D-044: Starting is one command, and the facts that make it one live in `.env`

**Date:** 2026-08-22
**Status:** built. [TASKS.md](TASKS.md) T-032

Getting to work meant three things: start the server, remember `--also-on tailscale`
or the phone cannot reach it, and start a Chrome with WhatsApp Web in it. Two of
those are the same every day on the same machine, and the one that was forgotten
most was the tailnet flag, because a reboot is how you lose it.

**So `./wastatus.sh` with no arguments opens the page**, and two settings in `.env`
answer the rest:

| Setting | What it does | Default |
|---|---|---|
| `WASTATUS_ALSO_ON` | binds a second address as well as loopback. `tailscale` resolves the tailnet address | empty, loopback only |
| `WASTATUS_START_BROWSER` | starts a Chrome with WhatsApp Web if one is not already running | empty, starts nothing |
| `WASTATUS_CDP_PORTS` | which debug ports to look on, and to start one on. A list or a range | 9222-9226 |

**Off stays the default.** A fresh clone binds loopback only and starts no browser,
which is what [D-027](#d-027-loopback-is-always-bound-and-a-second-address-is-added-rather-than-widened)
and [D-028](#d-028-the-page-is-started-by-hand-the-service-stays-available-and-uninstalled)
already settled. What changed is not the default but where one machine's answer is
allowed to live. Binding the tailnet is a decision about a network, so it belongs in
a file that machine owns and git never sees, not in code that is published.

**This is not the service.** D-028 refused a thing that starts with the operating
system and that stands. Nothing here runs unless somebody types the command; it only
stops them typing the same three flags after it.

**A flag still wins.** `--no-start-browser` overrules the file, because the point of
typing one is to mean something different for this run.

**Which ports to look on is a fact about one machine, not a constant.** An IDE that
opens debug browsers of its own takes 9222 upward and never gives them back, and no
amount of code fixes that. The list is read at call time and not frozen into a
default argument, which would bind it at import, before `.env` has been read.

**A browser already open on the posting profile is adopted, not duplicated.** Chrome
hands a second launch on one profile to the running instance and exits, ignoring the
new `--remote-debugging-port` completely, so the naive version opens a window and
exposes nothing. `running_profile_port()` finds the one that is there and prefers its
port instead. `discover` tries the preferred port before the candidate list, so a
browser outside the configured range is still reachable once it has been found.

---

## D-043: The GIF picker is a module with a switch, and everything it fetches comes through us

**Date:** 2026-08-21
**Status:** built. [TASKS.md](TASKS.md) T-029

**This is the only part of the tool that talks to anybody but YouTube.** Until now
the whole outbound surface was yt-dlp, YouTube's thumbnail host, and a token helper
on loopback. A GIF search adds a third party that sees what the owner types into it.
That is a change in what the machine does, not just a feature, so it is switched off
by default and it is a file you can delete.

**Off is the default, and a half finished setup is also off.** `provider()` returns
`""` unless `WASTATUS_GIF_PROVIDER` names a provider **and** that provider's key has
a value. A named provider with no key would otherwise draw a search box in the page
that answers nothing but errors. The page asks `state` whether the feature exists at
all and draws no toggle when it does not, so an unconfigured copy shows no trace of
it: no button, no credit line, and the routes answer 404.

**Two providers behind one shape.** GIPHY and KLIPY return entirely different JSON.
Both are normalised to one small record before anything else sees them, so the page,
the server and the tests know one shape and a third provider is a function.

### Table D43-1: what each provider is asked for, and why

| | KLIPY | GIPHY |
|---|---|---|
| Shelf thumbnail | `xs`, measured mean **107 kB** | `fixed_width_small`, measured mean **113 kB** |
| What gets kept | `md`, measured median **1296 kB**, p90 3352 kB | `downsized`, which GIPHY itself caps at 2 MB |
| Content filter | `content_filter`: off, low, medium, high | `rating`: g, pg, pg-13, r |
| Required attribution | the search box must say **"Search KLIPY"** | a visible **"Powered by GIPHY"** mark |

**Corrected 2026-08-22, and the original figures were wrong by roughly six times.**
This table first said KLIPY's `xs` was "about 12 kB" and its `md` "about 200 kB",
taken from their documentation rather than from a request. Measured over 132 real
results across five searches: `md` has a median of 1296 kB, a p90 of 3352 kB and a
maximum of 10070 kB, and **two of the 132 were over the 8 MB animated sticker
ceiling and would be refused on picking**. Thumbnails measured 107 kB mean on KLIPY
against 113 kB on GIPHY, so a shelf costs roughly the same either way and this is the
feature's price rather than one provider's. Nothing in the design changes; the
numbers it was justified with do.

Two sizes rather than one, because the shelf draws thirty at once and a placed
sticker is drawn at up to 90 per cent of a 1080 pixel frame. One size for both means
either a blurry sticker or a shelf that costs megabytes.

**The rating default is `pg`, not `g`.** The owner posts songs and general video, not
only devotional material, and `g` is narrow enough to strip out ordinary celebration
and reaction GIFs. A value that is not one of the four is refused and falls back
rather than being passed through: a typo quietly meaning `off` is the wrong way for a
safety setting to be wrong.

**Everything is proxied, and nothing the browser says is fetched.** Two separate
reasons, and each would be enough on its own.

The first is the phone. It reads this page over the tailnet, so a thumbnail loaded
straight from GIPHY would put **the phone** in touch with GIPHY rather than just the
laptop. Every other image on this page comes from one origin and this one does too.

The second is that a pick names an **id from a search this server made**, never a
url. The address is looked up in what this process last handed out. A caller holding
the token cannot point this machine at an address of their choosing, and `fetch`
refuses anything that is not `https` and stops reading at the sticker ceiling
whatever the provider's own byte count claims.

**Picked GIFs are kept, and pruned: `gif:` is a third namespace.** They live beside
`mine` rather than in it, because an upload is something you decided to keep and a
picked GIF is something you passed through. Twenty are kept, the same number and the
same reasoning as `keep_last` for clips. Pruning never touches uploads, which is the
whole reason the folders are apart. The file is named for its provider and its id
rather than its title, because two services will eventually both have a `thank-you`.

**Rejected: one search box for both.** The library is 4,495 OpenMoji drawings, and
thirty GIF results merged into that would bury them. They are reached for at
different moments, so they are a toggle: **Drawings** and **GIFs**.

**Rejected: Tenor, and Pixabay.** Tenor answers `403 unregistered callers` and now
requires a Google Cloud project; the owner reported onboarding closed outside
Google's ecosystem on 2026-08-21. Pixabay needs a key, shown on its docs page once
you log in, and it does not matter: its API has no GIF search at all, `image_type`
being only `all`, `photo`, `illustration`, `vector`. Neither has a setting in
`.env.example`, because a setting no code reads is a promise this repository's own
test refuses to let it make.

---

## D-042: A refused request still has to be read to the end

**Date:** 2026-08-20
**Status:** accepted, and covered by a test that fails without it

`do_POST` used to answer `403 bad or missing token` before touching the request
body. The connection is keep-alive, `protocol_version = "HTTP/1.1"`, so the body
stayed in the socket and the next request line was parsed out of the middle of it.
The log filled with

```
501 Unsupported method ('{"url":"https://www.youtube.com/watch?v=...","start":""...}POST')
```

which names nothing that is actually wrong and sent an evening looking at the wrong
thing. **The body is now read before anything is decided**, including whether the
caller is allowed to be here. Reading is bounded by `MAX_BODY_BYTES` exactly as it
was, so an unauthorised caller still cannot make this process hold anything large;
the only change is that the socket is left in a state the next request can use.

**Rejected: closing the connection instead.** Setting `close_connection = True` on
the 403 path would also have stopped the desync, and would have been one line. It
was rejected because it turns every refused request into a new TCP connection for
the page to make, and because the page retries `/api/state` every fifteen seconds:
a tab left open across a restart would have sat there opening and dropping a
connection four times a minute. Reading a bounded body is cheaper than that.

**Why a page would ever hold a bad token.** The token is minted per process,
D-027's neighbour: nothing is stored and nothing is reused. So every tab open
across a restart is holding a dead one. That is working as intended, and the page
now says so in words rather than showing `bad or missing token`, which reads as a
fault in the tool rather than an age difference between the tab and the server.

---

## D-041: WhatsApp's labels are matched on words, not on exact strings

**Date:** 2026-08-20
**Status:** accepted, after every post failed for an evening

**What happened.** `load_video` clicked a control whose `aria-label` was exactly
`Photo and video`, and `load_text` one labelled exactly `Text status`. Those strings
were written in the first commit that could post, `293bae7`, and were never touched
again. Some time between the last good post at **2026-08-19 22:53** and the first
failure at **2026-08-20 19:42**, WhatsApp Web renamed the first to `Photos & videos`
and the second to `Text`, and moved both behind an **Add Status** button that has to
be pressed before either exists in the DOM. Exact equality found neither, and the
tool reported `could not find a control labelled 'Photo and video'`, which was true
and useless.

**Labels are not an API.** WhatsApp owes this tool nothing and will rename them
again. Three ways to be less brittle were weighed.

### Table D41-1: what to match on

| Match on | Why it was or was not taken |
|---|---|
| **The words in the label, punctuation and case and plurals removed** | **Taken.** `Photos & videos` and `Photo and video` both reduce to `photo video`, so this specific rename would not have broken anything. A list of known spellings is checked as well, so an outright new word is one line to add |
| The `data-icon` value, `ic-filter` and `ic-edit` | Rejected. It is not on the button, only near it, and an icon name is no more promised than a label is. It would also have needed the same list, one layer further from what a person can read and check |
| A stable `data-testid` or `role` path | Rejected because there is not one. The items carry `role="menuitem"`, which narrows the search and is now the first place looked, but the two items are indistinguishable by role alone |

**The menu is opened by asking, not by assuming.** `open_status_menu` checks whether
the choice is already on screen before pressing **Add Status**. On an older build
where the choices sit in the panel, pressing would have found nothing; on the current
one, pressing twice would close the menu that had just opened. Looking first works on
both, and will keep working if WhatsApp moves it back.

**How a rename is noticed now, 2026-08-21.** `check_controls` opens the Add Status
menu once per server run, looks for both choices, and closes it again. The page asks
for it when a clip first becomes postable, which is early enough to matter and late
enough to be free; it is never on the fifteen second poll, because that would open
and close a menu under the owner's hands four times a minute. It refuses to look
while a composer is open, since that composer is holding a clip somebody is about to
send. A bad answer rides on the existing **WhatsApp Web** health row rather than a new
one, because it is the same question, can this thing post, and it names what the menu
actually offers so the fix is one line. Route B of [TASKS.md](TASKS.md) T-026; route A,
checking on the poll, was rejected for the reason above.

**What is deliberately not done: pinning a WhatsApp Web version.** There is no
version to pin. It is a web app, it updates itself, and the tab that had been running
since before the reboot was serving an older build than the one Chrome fetched when it
restarted at 18:55 on 2026-08-20. That is why this arrived as "suddenly": nothing in
this repository changed, and nothing in this repository could have prevented it. The
only defence is to fail in a way that says where to look, which is why the error now
names the file and the list to widen.

---

## D-040: This repository is published, with the posting path in it

**Date:** 2026-08-20
**Status:** accepted by the owner. The four questions in [TASKS.md](TASKS.md)
Table T22-2 were answered on the same day

**The licence is MIT**, held by **PalWorks**, which is the name the GitHub account
this lives on already carries. Without a licence a public repository is all rights
reserved and nobody may legally use it, which was not the intent.

**`wastatus/post.py` is published.** It drives a browser the owner is already logged
into, over Chrome's own debug port on loopback, and does nothing an unofficial
protocol library would do; D-002 still forbids that and [AGENTS.md](AGENTS.md) still
enforces it. The alternative was to publish everything except the posting path and let
the tool stop at producing files, which is already its default. That was rejected
because a repository that hides its most consequential file teaches a reader the wrong
thing about it. [SECURITY.md](SECURITY.md) opens by naming what that file can do.

**[MEMORY.md](MEMORY.md) is split rather than dropped.** It is the best answer in here
to "why is this built this way", and only a few of its rows were about the owner
rather than about the tool. Those moved to `MEMORY.private.md`, which is ignored by
git and named in AGENTS.md's never-commit list. The rule for keeping the split honest
is written at the top of both halves: a row is private if a stranger would learn
something about **him**, public if they would learn something about the **tool**.

**The history was rewritten**, with `git filter-repo`, replacing the same values in
every commit that the working tree scrub replaced. Leaving it would have made the
scrub decorative: the values sat in 31 commits, one `git log` away. Every hash changed,
which costs nothing in a single author repository with no forks and no open pull
requests. A tag was left behind on the old history locally, so the rewrite is
reversible until it is deleted.

**Rewritten a second time on 2026-08-27.** A Chrome profile name carrying the owner's
account handle was quoted from live output into four documents on 2026-08-21, after
this scrub, and lived in commit `4429818` until the working tree was cleaned. Same
tool, same replacement, one string. Note what GitHub does with the old objects: a
force push makes them unreachable from any ref, so they are gone from a clone, from
`git log` and from search, but the old commit is **still served by its full hash**
through the API until GitHub garbage collects, which is theirs to run and not ours.
Deleting and recreating the repository is the only route that is certain, and that is
a decision for the day it goes public rather than a step in this one.

**What was deliberately not scrubbed.** Device models, because a phone model
identifies nobody and a measurement reads better with the real hardware in it. And the
test fixtures, which still carry the real title the typography rules were measured
against, because a fixture renamed to something that was never measured proves nothing.

---

## D-039: Settings come from the environment, and `.env` is the file that feeds it

**Date:** 2026-08-20
**Status:** accepted. Groundwork for [TASKS.md](TASKS.md) T-022, making this
repository fit to be public

There is **no secret in this repository** and there never was one: the page's token
is made per process by `secrets` and dies with the server, and there is no API key
anywhere. So this is not a decision about moving a secret out. It is about where a
stranger who clones this would put one, because two settings would carry a credential
if anything did: `WASTATUS_PROXY` can embed a password, and
`WASTATUS_COOKIES_FROM_BROWSER` names a browser profile to read live YouTube session
cookies from.

**The shape.** `wastatus/env.py` reads `KEY=value` lines from a `.env` beside the
code. `.env` is ignored by git; `.env.example` is committed, names every setting the
tool reads, and holds no value for any of them. A test asserts that list stays equal
to what the code actually reads, because an example file that drifts is worse than
none.

**Three rules, each with a reason:**

* **The environment always wins over the file.** A file that overrode an exported
  variable would make a one off run impossible to do without editing it.
* **Everything after the first `=` is the value.** No inline comments, so a proxy URL
  with a `#` in its password needs no escaping and no quoting rules to learn.
* **The file is read in `__main__.py`, before `cli` is imported.** Some settings, like
  `WASTATUS_POT_PORT`, are read at import time rather than at use time, so a file read
  inside `main()` would be read too late to matter. It is deliberately not read on
  import of the package: importing `wastatus` must not change a process that only
  wanted to call a function.

**No dependency.** `python-dotenv` does this well, and it is thirty lines. A tool
whose whole install story is "python, ffmpeg, yt-dlp" does not add a package to read
`KEY=value`.

---

## D-038: Handles on the sticker itself, and selection replacing the fade

**Date:** 2026-08-20
**Status:** **built, 2026-08-21.** Agreed and parked on 2026-08-20, picked up the
next day. See [TASKS.md](TASKS.md) T-023 for what was measured after

A sticker will carry its own controls, drawn on the box around it, rather than being
driven only from sliders below the frame.

**What decided the mobile half: one measurement.** A default sticker in the phone
preview is **60 pixels drawn, 76 to hit**, at 412 pixels wide. A touch target needs
44 pixels, and two of them need 88 pixels between them. **Two touch handles cannot
both fit on a default sticker.** So a phone gets exactly one, and it has to be the
delete cross, because pinch and twist already do size and rotation. A laptop has a
mouse, which is precise, so it gets the full set.

| Control | Where | Why |
|---|---|---|
| Delete | a cross at the **top right**, both views | universal and unambiguous. One press, no confirmation: a sticker is re-added from the shelf in one tap, unlike a clip |
| Resize | **bottom right**, desktop only | the owner's sketch put it top left. Every operating system window and every design tool puts resize at the bottom right, and a grip at the top left reads as the object's origin, so it would be missed |
| Rotate | **above the box on a short stem**, desktop only | the owner's idea, and it is the PowerPoint and Keynote convention. The alternative, a spare corner, saves the stem and teaches nobody |
| Size and Turn sliders | **kept on desktop, removed on phone** | pinch covers it on a phone and the numbers mean nothing there. A laptop has no second finger, so the sliders stay as the precise route |

**The consequence that makes this a decision rather than a task.** It amends
[D-034](#d-034-the-dashed-box-round-a-sticker-is-a-handle-and-appears-only-when-there-is-a-hand-near-it),
agreed hours earlier the same day. That decision fades the dashed box 1.4 seconds
after a hand leaves it, and **handles that fade are handles you cannot click.** So
one state has to become two:

| State | Behaviour |
|---|---|
| **Selected** | you tapped the sticker. Box and handles stay, indefinitely |
| **Idle** | you tapped the frame background, or another sticker. Both vanish |

That keeps the clean resting frame D-034 was written for, because nothing is selected
most of the time, and it makes handles usable, because a selection persists. The idle
timer is then unnecessary and goes away. This is a better rule than the timer, and it
is the reason the work is not a small addition: it touches the gesture code, the
selection model and D-034 at once.

**Why it is parked rather than dropped.** Nothing about it is wrong; it is a matter
of when. The design is written down here so that picking it up later is an
implementation job and not another round of deciding.

### Built, and the one thing the design did not say

**Which devices count as "desktop" is decided by the pointer, not by the width.**
The reasoning above is "a laptop has a mouse, which is precise", so the query is
`(hover: none) and (pointer: coarse)`, the same pair the hover rule in D-034 already
relies on, and the test is **positive**: this is a touch screen, therefore drop two
handles and both sliders. Written the other way round, "this is not a mouse", a
browser that reports neither would silently lose them. A headless Chrome reports
neither, which is how that was found rather than guessed.

**The sticker became a box.** A drawing cannot hold handles, so each one is now a
`div` carrying the transform with the `img` inside it. The box takes its height from
the picture, so a sticker that is not square is boxed exactly, and because the box
carries the rotation the handles turn with it, which is what every design tool does.

**Resize and rotate are measured from the centre, not from the corner being held.**
The centre of a rotated box is the one point its bounding rectangle still reports
truthfully, so both work at any angle without undoing the rotation first. Size is a
ratio of two distances and rotation a difference of two angles, so neither jumps when
grabbed, and rotation uses the same `settle` as the two finger twist, which means
square is square by either route.

**Remove stays on the phone**, though the sliders beside it go. A sticker shrunk to
the 3% minimum is smaller than the cross that would delete it, and that is the one
case where the cross is not enough.

---

## D-037: The page is not a secure context on a phone, so the clipboard API is not there at all

**Date:** 2026-08-20
**Status:** accepted

Measured, not assumed: opened on `http://100.x.y.z:8765`, which is the address
the phone uses, the page reports `isSecureContext: false` and
`typeof navigator.clipboard` is **`undefined`**. Not blocked, not permission denied:
absent. Only `https` and loopback count as trustworthy origins, and a tailnet
address is neither.

**What this broke, silently, on the one device it mattered on.** The caption's
**Copy** button called `navigator.clipboard.writeText` inside a `try`, and on
failure set the button's `title`. A phone has no hover, so there was nothing to
show: on the phone, Copy did nothing at all, and gave no sign of it. Copying the
caption is half of the away route, the one the owner actually uses, so this was a
dead control in the middle of the main path.

**The fix is a deprecated API, deliberately.** `document.execCommand("copy")` over a
hidden textarea works in any context, and it is what the fallback uses. The modern
API is still tried first where it exists. Verified on the tailnet address: the tick
appeared, and the system clipboard really held the caption afterwards, read back
outside the browser.

**The wider consequence, which is why this is a decision and not a bug fix.**
Anything that needs a secure context is unavailable on the phone: `navigator.clipboard`
in both directions, and therefore any "paste from clipboard" **button** we might have
built for GIFs. The `paste` **event** and its `clipboardData` are not gated that way,
which is why the picture route is built on the event rather than on a button. Before
reaching for a browser capability, check whether it is `[SecureContext]` in its spec:
on this project it will be missing exactly where it is most wanted.

**The alternative was to serve the page over https**, with a certificate the phone
trusts. That means a local certificate authority installed on every device, or a
real name and a real certificate for a machine that is often off. It buys one API.
Not worth it, and the fallback costs six lines.

---

## D-036: A sticker that moves is a second mechanism, and the clipboard is how it arrives

**Date:** 2026-08-20
**Status:** accepted, and it amends [D-024](#d-024-stickers-are-dragged-in-the-browser-in-fractions-of-the-frame)

A still sticker is pasted into the picture by Pillow before ffmpeg starts. An
animated one cannot be: a paste has no time axis. It becomes a **looping video
input in the filter graph** instead, and the two kinds are separated once, in
`pipeline.produce`, by `stickers.split`.

**How one arrives, and why there is no picker of ours.** The owner asked for
Gboard's emoji and GIF experience. A web page cannot open the phone keyboard's own
picker and cannot read its catalogue, so the page does not try. It listens for a
**paste** instead: pick a GIF in Gboard, in any app, and it lands on the clipboard,
and the page takes it from there. The same listener means a copied picture on the
laptop works too.

That choice buys a great deal by not being a picker: no API key, no attribution
terms, no network call while composing, no catalogue of ours to curate, and no
question about whether Tenor has any Tamil devotional material. The picker route is
still written down in [TASKS.md](TASKS.md) T-019 if the clipboard turns out to be
too narrow a door.

**A paste is only intercepted when it carries a picture.** A pasted link or a line
of text goes where it was aimed, which matters because the caption box is the thing
people paste into most. Both paths were driven and measured: pasting a GIF with the
caption focused adds the sticker and leaves the caption text untouched.

**A box that says it can take a picture, added 2026-08-20.** A phone keyboard decides
whether to offer its GIF tab from what the focused element declares it accepts, and a
plain `<input>` declares text. So the sticker card carries a small `contenteditable`
box, which is the target type that can take a picture: tap it, and the keyboard's GIF
tab has something to aim at. It keeps nothing, ever. Two delivery routes are handled
because browsers differ: a `paste` event carrying a `File`, and an `<img>` inserted
straight into the box, which is pulled back out and uploaded. Typing words into it is
answered with a line saying it takes pictures, not words.

**What a phone keyboard actually delivers, settled on 2026-08-20** by driving the
owner's own Galaxy M30 over USB rather than reasoning about it:

| Browser on Android | What happens when a GIF is picked from the keyboard |
|---|---|
| **Chrome 151** | **refused.** A toast: *"Can't enter this content here."* Nothing reaches the page, nothing reaches the clipboard. Long pressing the GIF offers no copy or share either |
| **Firefox 150** | **works.** A `paste` event arrives carrying **`text/plain` only, `files=[]`**, then a `beforeinput` of `insertFromPaste`, and then the picture appears in the box as an `<img>` with a **`data:image/gif;base64`** src, 156,930 characters for a 117 kB GIF |

**This is why the box watches for an inserted `<img>` and not only for a file.** The
paste event carries no file at all, so a listener that reads `clipboardData.files`,
which is what the whole-page listener does, sees nothing. The `<img>` route is the
only one that fires, and it fires on the box.

It also settles which element the box has to be. Focused on the page's ordinary
`<input>` fields, the keyboard's GIF and sticker buttons are **greyed out**. Focused
on this box, they light up. The `contenteditable` is doing exactly the work it was
added for.

**The keyboard was Samsung Keypad, not Gboard**, and its GIF panel is GIPHY.

**Confirmed on Gboard the same day.** The owner ran the same thing on his OnePlus 11,
which has Gboard: **Chrome gave nothing**, from the sticker card's ordinary field and
from the box alike, and **Firefox worked from the box**. So the keyboard is not what
decides. The **browser** is, now measured on two phones and two keyboards, and the
page itself needs no keyboard specific code: it handles a file, an inserted image and
a pasted link, and Android's rich-content mechanism is the same one underneath all of
them.

**That it only works from the box is the design, not a fault.** A plain `<input>`
declares that it accepts text, and the keyboard believes it, which is why the GIF
button is greyed out there. Making the sticker search field a `contenteditable` as
well would move the box without solving anything, because Chrome would still refuse.
What could be done for Chrome is held in [TASKS.md](TASKS.md) T-024.

`wastatus/web/paste-test.html` was the instrument that answered this. Both phones have
been through it, so it was deleted on 2026-08-20. It is in this repository's history
if the question ever reopens.

**Animated stickers are stored as GIF, and that is a measurement rather than a
preference.** ffmpeg 8.0.1 on this machine reads an animated GIF and refuses an
animated WebP outright, `image data not found`. Pillow reads both. So Pillow is the
doorman: every frame is read and written back out as GIF, which also keeps the
existing rule that the bytes on disk are ones we produced.

**Where an animated sticker is laid down, and why it matters.** In card mode the
still ones are pasted onto the 1620 pixel card *before* the slow zoom, so they
travel with it. An animated overlay applied after the zoom would sit still while its
neighbour drifted outwards, in the same frame. So the animated ones are overlaid
onto the card stream **before** `zoompan`, at the card's own resolution, and the zoom
carries both. Measured: a rotated asymmetric sticker drawn both ways lands on the
same bounding box and the same centroid, to the pixel, and both grow by the same
factor across the clip. In video mode there is no zoom and the overlay is composited
at `0:0` alongside the text layer, so the question does not arise.

**The amendment to D-024.** That decision promises the preview shows what the clip
will contain. For an animated sticker, **position, size and rotation stay exact and
the phase does not**: the preview runs on its own clock and the render starts the
loop at frame zero. Nobody can hold a browser and an encoder to the same frame of a
loop, and pretending otherwise would be the dishonest choice. Everything D-024 was
built to protect, the fractional coordinates with no scale factor between browser
and renderer, is untouched.

**Consequence, and the cost.** Measured on a 4 second card clip: one animated
sticker adds about 1 second of encode and 56 kB, three add about 3.4 seconds and
61 kB. The clip was never still to begin with, since card mode already carries a
slow zoom and a reacting waveform, which is why the size cost is small.

---

## D-035: One file picked goes on the frame, several go to the shelf

**Date:** 2026-08-19
**Status:** accepted

The sticker upload takes several files at once. What happens next depends on how
many you picked: **one** is placed on the frame immediately, **several** are added
to your shelf and nothing is placed.

**Why the split rather than one rule.** Picking one file is an act of using it: you
found the drawing you want on this clip, and the old behaviour, which placed it,
was right. Picking twelve is an act of stocking: nobody wants twelve stickers
dropped onto one frame, and the placement cap would refuse the batch at twenty
anyway. The same button serves two intentions, and the count is what tells them
apart. It needs no extra control and no explanation on screen.

**Why the batch survives a bad file.** Each upload is its own request, and a refusal
is collected rather than thrown. The way to lose half an hour of gathering artwork
is to have the twelfth file sink the eleven that already uploaded. The message names
the file that was refused and says the rest are in.

**Why not a folder picker or a drag and drop zone.** `webkitdirectory` is a
different permission conversation on every browser, and a drop zone is a second
target to maintain on a page whose primary device is a phone, where there is nothing
to drop. Multiple selection is one attribute and works identically in the phone's
file picker and the laptop's.

**What this does not solve.** OpenMoji has no deity art, and that is the actual
reason the picker feels thin for a Tamil devotional channel: `shiva`, `ganesha`,
`krishna` and `tamil` return nothing out of 4,495 drawings. This decision makes
stocking your own set cheap. It does not stock it for you.

---

## D-034: The dashed box round a sticker is a handle, and appears only when there is a hand near it

**Date:** 2026-08-19
**Status:** accepted, and it amends [D-024](#d-024-stickers-are-dragged-in-the-browser-in-fractions-of-the-frame)

The white dashed box marking the picked sticker used to be drawn from the moment a
sticker was placed until the page was reloaded. It is now lit only while there is a
reason for it, and fades out 1.4 seconds after the last one stops.

**Why it had to go quiet.** The frame has one job, written on it: *what the viewer
sees*. A permanent dashed box is a thing the viewer will never see, drawn on top of
the one place in the page that is supposed to be truthful. On a 300 pixel phone
frame it is also loud: the box is the sticker's hit area, 8 pixels larger on every
side than the drawing, so a small sticker wears a box half again its size and at
whatever angle it has been twisted to. The owner asked for it after looking at a
finished Status preview and seeing the box before the flame.

**When it is lit.** A finger or the mouse is on the sticker; a Size or Turn slider
is being dragged; a sticker has just been placed from the shelf. Each of those is a
moment when the question *which one am I about to move* is live. Then it fades.

**Why a timer and not just the gesture.** The sliders are the other way to move the
picked sticker, and on a phone your thumb is at the bottom of the screen while the
sticker is in the middle. Lighting the box only during a touch on the sticker itself
would leave the sliders working on something unmarked. The idle timer covers both
routes with one rule: recently touched, by any means, means marked.

**The orange covered box is not this and does not fade.** It is a warning that the
sticker sits under WhatsApp's own header or caption and will not be seen. A warning
that disappears on its own is not a warning, so it stays until the sticker is moved.

**How it is drawn.** The outline is always declared and transparent, and only its
colour changes, so nothing shifts when it appears and the fade is a plain colour
transition. Outlines are painted outside the box and never affect layout. The
reduced motion rule already in the stylesheet turns the fade into a cut.

**Consequence.** On a mouse there is no touch to reveal the handle, so hovering a
sticker shows a fainter version of the box. Phones report `hover: none` and never
match that rule.

**Amendment, 2026-08-21: the timer is gone, and selection replaces it.** D-038 put
controls on the box, and a handle that fades after 1.4 seconds is a handle you cannot
click. So the one state this decision described became two: **selected**, which lasts
until you put it down, and **nothing selected**, which is the resting frame this
decision was written to protect. Tapping the frame background is what returns you to
it, and nothing is selected most of the time, so the intent here survives intact. The
hover rule above is untouched. What is gone is `MARK_IDLE`, `markPicked` and the
timer that drove them.

---

## D-033: Two fingers size and turn a sticker, and the first one has to be on it

**Date:** 2026-08-19
**Status:** accepted, and it extends [D-024](#d-024-stickers-are-dragged-in-the-browser-in-fractions-of-the-frame)

One finger drags a sticker. Two fingers pinch it larger or smaller, twist it round,
and carry it along with their own midpoint, the way you would move a piece of paper
on a table. The gesture starts when a finger lands **on a sticker**; the second
finger may land anywhere on the frame.

**Why the second finger is allowed to miss.** A sticker at its default size is a
fifth of a 300 pixel frame, about 60 pixels across. Two fingertips do not fit inside
that, so requiring both to land on the drawing would have made the gesture
impossible on exactly the stickers people place. Requiring the *first* one keeps the
rule simple to state and leaves an ordinary swipe over the frame doing what it
always did.

**Why the sticker also grew a transparent border.** Eight pixels of `border` with
`box-sizing: content-box`, so the drawing is still exactly `size × frame width` and
the eight pixels are hit area, not picture. A 60 pixel sticker is a 76 pixel target,
against a fingertip nearer 40. The contract D-024 protects is untouched: the number
sent to the renderer is still the fraction the browser drew.

**What the gesture must not do, and what stops it.** Two fingers on a page are also
how you zoom a page. While a sticker is held, the frame gets `touch-action: none`,
so the second finger joins the gesture instead of zooming; the class comes off when
the last finger lifts, and swiping the frame scrolls the page again.

**Turning snaps to square.** Within four degrees of 0, 90 or 180 the angle settles
exactly, because straight is a thing people aim for and miss by a degree. Nothing
else snaps, so a deliberate 37 degrees stays 37. The sliders do not snap at all:
typing a number is already exact.

**Consequence.** A laptop has no second finger, so the Size and Turn sliders stay
and are the only route there. They also follow the fingers live, which is what makes
the two controls obviously the same two numbers.

---

## D-032: Every section is a folding card, and a fold is not a hiding place

**Date:** 2026-08-19
**Status:** accepted, and it extends [D-029](#d-029-the-page-is-written-mobile-first)

The page is eight `<details>` cards: the clip, look, words, extras, preview,
stickers, post it, recent. Make the clip is not one of them.

**Why fold at all.** On a phone the page is four screens tall, and on any given
pass you are changing one thing. Folded, the whole job fits in one screen and you
open the part you are touching. The owner asked for it after using the flat
version for an evening.

**The rule that keeps it honest: every header carries its own value.** `0:20 to
0:50 · 30s`, `Artwork card`, `waveform on`, `2 placed`, `5.4 MB`. A fold that hides
what is inside it is worse than the scroll it saved, so a collapsed card still
answers what it holds, and a card holding something unusual also carries a dot.

**What never folds.** The button you came to press. Make the clip sits in a plain
card with the progress under it, because a primary action behind a disclosure is
an interface playing hide and seek.

**Folding by itself, and what that must not do.** When a render lands on a narrow
screen, the four input cards fold and the page scrolls to the preview: the
questions are answered, so the answer takes the screen. On a laptop nothing moves,
because the preview is already beside the form. **An automatic fold is never
written down as a preference.** Your own presses are, so tomorrow the page opens
the way you left it, not the way one render left it.

That distinction needed care in the code: `toggle` fires on a later task, so a
flag raised and lowered around `card.open = false` is already down by the time the
listener reads it. The flag rides on the element instead, and the listener clears
it. Without that, one render would have rewritten the layout you chose.

**Consequence.** Native `<details>` means keyboard and screen reader behaviour come
for free, and the state survives with no JavaScript. It also means the animation
is a jump rather than a slide, which is the trade this page takes.

---

## D-031: Light, dark or system is the page's own setting

**Date:** 2026-08-19
**Status:** accepted

One button in the top bar cycles system, light, dark. The choice is stored in
`localStorage` and applied by a five line script in `<head>`, before the first
paint. "System" is stored as the absence of a value, not as the word.

**Why a choice at all.** The page follows `prefers-color-scheme`, and that is the
right default, but the two devices this runs on do not agree: a laptop on a dark
desktop theme and a phone that switches at sunset. The owner asked for the control.

**Why the absence of a value means system.** If "system" were stored as a word, a
machine that changes its own mind at sunset would still be followed, but only
because the code remembered to keep asking. Storing nothing makes following the
system the thing that happens when nobody has said otherwise, which is what it
means.

**Why the inline script.** The stylesheet cannot know the stored choice, so without
it a page set to light loads dark for one frame on a dark machine. Five lines in
the head, before any paint, is the whole fix.

**Consequence.** Every dark token is written twice, once under
`@media (prefers-color-scheme: dark) :root:not([data-theme="light"])` and once under
`:root[data-theme="dark"]`, because a media query and an attribute cannot be
combined into one selector. Changing a dark colour means changing two lines. The
alternative, a class toggled by JavaScript on load, trades that duplication for a
flash of the wrong palette, which is worse.

---

## D-030: One caption, edited in a labelled box, echoed on the frame

**Date:** 2026-08-19
**Status:** accepted, and it amends [D-021](#d-021-the-caption-is-edited-in-place-the-card-wording-is-edited-in-the-form)

The caption is edited in a box under the preview, labelled "Caption, sent with the
video". What is drawn over the bottom of the frame is a read only echo of that box,
in the place WhatsApp will draw it.

**Why the change.** D-021 put the only editable copy on the frame itself, under a
bar that said "Caption", above a heading that said the song's name. The owner, on
his phone, asked the question that settles it: "Not clear. What is the actual
caption here?" A label that is three lines away from the text it names is not a
label.

**What D-021 got right, and keeps.** The caption is still text sent alongside the
video rather than pixels inside it, it is still saved without a render, and the card
wording is still edited in the form because those words are drawn into the frames.
The split between the two is unchanged. Only the place you type has moved.

**Consequence.** The frame is now read only, so a caption cannot be edited while
looking at exactly where it lands. The box sits directly under the frame, so both
are on screen together on a phone, which is where the confusion was reported.

---

## D-029: The page is written mobile first

**Date:** 2026-08-19
**Status:** accepted

`app.css` describes a phone. Two media queries widen it: 600px puts labels and
buttons back on shared rows, 901px restores the two column layout. Nothing in the
base stylesheet assumes a pointer or a wide viewport.

**Why.** The page is opened from two postures and the phone is the harder one: a
360 pixel column, a thumb instead of a pointer, and a browser that reloads the tab
when you switch to WhatsApp and back. Written the other way round, the phone gets
whatever survives the shrinking, and what did not survive was measured on the
owner's own screenshots: three health pills taking the first third of the page, a
numeric keypad on a field that needs a colon, a stop button below the fold, and a
form that lost a pasted link on every reload.

**What this decided, concretely.**

| Was | Is | Because |
|---|---|---|
| Three health pills across the header | One chip, opening a panel | They matter when one is wrong, which is rarely |
| `inputmode="numeric"` on Start and End | `inputmode="text"` | Android's numeric keypad has no colon, so `0:20` could not be typed |
| Start, Length and End down the page | One row | They are one decision |
| Stop beside the progress bar | Beside Make, replacing the shortcut hint | That is where you are looking while it works |
| Four stage names in a row | A numbered sequence with a rail and ticks | Four words in a row do not read as four steps |
| Safe areas off by default | On, and hidden only when the frame is empty | A sticker under WhatsApp's caption is invisible, and you cannot see that coming |
| Four post buttons in one row | One filled action chosen by device, then the rest | Only one of them is the one you came for |
| Length, look and extras remembered | The whole form remembered | The phone reloads the tab, and a pasted link should survive it |

**Consequence.** Touch targets are 44px and inputs are 16px on a phone, because
anything smaller makes the browser zoom on focus. The desktop layout is a widening
of the phone one rather than its own design, which keeps one stylesheet honest at
the cost of a laptop page that is slightly more generous with space than it needs
to be.

---

## D-028: The page is started by hand. The service stays available and uninstalled

**Date:** 2026-08-19
**Status:** accepted

`scripts/install_service.sh` is kept, tested and documented, and is **not installed
on the owner's machine**. The page is started with `./wastatus.sh serve` when it is
wanted and stopped with Ctrl+C when it is not.

**Why.** The owner was offered it and declined: he does not want something starting
with the operating system, and posting to a Status is a deliberate act he is already
sitting down for. A service that is always up is only a saving if the page is wanted
without warning, which is not how this tool is used.

**Why the script survives anyway.** It costs nothing dormant, it is the answer to
"the terminal closed and took the page with it", and writing it later under pressure
is worse than having it now. It is a user unit, so undoing it is one command.

**Consequence.** Clips stay in the project's `out/` for a run started by hand, rather
than the `~/wastatus-out` a service would use. Nothing in the code depends on either.
Do not install it without asking, which [AGENTS.md](AGENTS.md) already requires.

---

## D-027: Loopback is always bound, and a second address is added rather than widened

**Date:** 2026-08-19
**Status:** accepted

`--also-on ADDRESS` opens a second socket on the same port. It does not replace the
loopback bind, and there is no `0.0.0.0` shortcut.

**Why two sockets and not one wider bind.** The address a request arrived on is the
only honest answer to "which device is this person sitting at", and D-026 depends on
it. Binding a single non-loopback address would leave the laptop reaching its own
page over the tailnet, where it looks exactly like the phone.

**Why an address and never a name.** The value is validated as an IP literal.
A name resolved once at bind time would not match the `Host` a browser later sends,
which is what the origin check compares against.

**Why a tailnet and not the local network.** The page hands its token to whoever
loads it, so "anyone on the WiFi" is not a trust boundary worth accepting for
something that can post to a Status. `tailscale` is accepted as a value and resolved
with `tailscale ip -4`, so the address never has to be looked up by hand.

**Still off by default.** Loopback alone, unless asked otherwise, and the startup
output says plainly what the second address means.

**Confirmed against real Tailscale on 2026-08-19**, once the owner installed it:
`tailscale ip -4` resolved, both sockets answered, and one process reported
`local: true` to loopback and `local: false` to the tailnet address.

**Amendment, 2026-08-20: off by default means off at every start, and that has a
cost worth naming.** The flag lives for the length of the process. Nothing writes it
to a file, an environment variable or a service unit, so a Ctrl-C or a reboot returns
the tool to loopback alone. This is the decision working as intended, not a defect:
the second address hands the posting token to whoever loads it, so re-arming it is
meant to be a thing the owner does knowingly rather than a state the machine drifts
into. What it cost on 2026-08-20 was an evening, because **Start the page** in
[LOCAL_SETUP.md](LOCAL_SETUP.md) said only `./wastatus.sh serve` and the phone route
was named eighty lines further down, in a reference table nobody reads after a
reboot. **The fix is the document, not the default.** The walkthrough now carries
both commands, the startup output's `Also on` line is named as the thing to look for,
and [RUNBOOK.md](RUNBOOK.md) carries the symptom. Re-verified the same day: both
sockets, `app.js` and `app.css` over the tailnet, and `/api/state` without a token
still refused with a 403.

**Rejected again while fixing this: remembering the flag.** A `.env` entry or a
`--remember` switch would have prevented the evening, and would also mean a machine
that quietly reopens a posting surface every time it boots. The owner keeps no
autostart service for the same reason, see D-028. A document that tells the truth at
the point of use is the cheaper half of the trade.

**Reversed, 2026-08-22, by D-044. `WASTATUS_ALSO_ON` now exists.** The paragraph
above is left standing because it was the position for two days and the reasoning is
worth reading, but its central worry does not hold. It said a remembered flag means
"a machine that quietly reopens a posting surface every time it boots". It does not:
nothing in `.env` starts anything, the file is read when somebody runs the command
and never otherwise, and D-028's refusal of a service is untouched. The real objection
was to autostart, and autostart was a different question all along.

What survives of it is the part that was right. The setting is **empty by default**,
so a fresh clone and any machine that has not opted in still binds loopback alone.
The startup output still prints the `Also on` line and still says in words that
whoever opens that page can post. And a run can still overrule the file: `--also-on
""` binds loopback only for that run, whatever `.env` says. What changed is only
where one machine's standing answer is allowed to live, and the honest reading is
that the owner re-armed that flag by hand for three days and the friction bought
nothing that the printed warning does not already buy.

---

## D-026: Both posting routes are always present. Only which one is primary changes

**Date:** 2026-08-19
**Status:** accepted

The result panel always carries **Load into WhatsApp**, **Send it for me** and
**Download**. Which one is drawn as the primary button, and which comes first in the
row, is decided by whether the request came from loopback.

**Why not hide the wrong one.** A Status composer is local to the client that opened
it, so a page open on a phone cannot press Send in the laptop's WhatsApp Web. But it
can usefully *load* the composer for later, and the laptop can usefully download a
clip. Neither route is ever wrong, only less likely, so hiding one would remove a
working path to save a glance.

**Why the connection and not the user agent.** The tailnet address can be opened on
the laptop, and a phone can be handed a loopback address through a tunnel. The peer
address is a fact; a device sniff is a guess. Verified on 2026-08-19 against a real
non-loopback peer: the same page reported `local: false` and put Download first.

**Consequence.** A wrong guess costs a glance. `body[data-where]` carries it, so the
swap is CSS ordering plus two class toggles, with no second layout.

---

## D-025: A render can be stopped. A post cannot

**Date:** 2026-08-19
**Status:** accepted

`/api/cancel` kills the yt-dlp or ffmpeg a render is waiting on. The same call
against a post is refused with a 409.

**Why the thread is the handle.** Every task already runs on its own thread, so
`proc` registers each child against the calling thread and `proc.cancel(ident)`
kills that thread's current child. No signature in `pipeline`, `fetch` or `render`
changes. The flag outlives the kill, so the next `run_child` on that thread refuses
to start: killing one ffmpeg is not enough when the pipeline would walk on to the
next stage.

**Why the process group.** yt-dlp runs an ffmpeg of its own, and a signal to yt-dlp
alone leaves that one encoding. Children get `start_new_session=True` and the kill
goes to the group. `tests/test_proc.py` proves it with a real grandchild.

**Why SIGKILL and no grace period.** Everything these children write goes into a
temporary work directory that is deleted afterwards, so there is nothing worth
letting them finish, and somebody is waiting.

**Why a post is different.** Killing a driver halfway through an upload leaves
WhatsApp in a state this tool cannot describe, let alone undo. The Status may be
live, may be half uploaded, may be nothing. Refusing is the honest answer.

**A stopped render leaves nothing behind.** ffmpeg used to write straight into the
output folder, which meant a clip still being encoded was listed by the page as a
real one, and a failed render left the truncated file there for good. The encode now
happens in the work directory and the finished clip arrives in the output folder in
one atomic rename, under a name the page's `*.mp4` glob cannot see until then. Copy
then rename rather than a move, because `shutil.move` across filesystems writes the
destination progressively, which is the thing being avoided.

---

## D-024: Stickers are dragged in the browser, in fractions of the frame

**Date:** 2026-08-19
**Status:** accepted

A sticker is placed on the preview by dragging it, and stored as `{id, x, y, size,
rotation}` where `x`, `y` and `size` are fractions of the frame between 0 and 1.
`compose` pastes them last, over everything, in both modes.

**Why fractions.** The browser drags a sticker over a 296 pixel preview; the
renderer pastes it onto a 1620 pixel card or a 1080 pixel overlay. With fractions,
`left`, `top` and `width` go straight into CSS percentages and straight into the
render request, and nothing converts anything. `tests/test_stickers.py` pins that
the same numbers land in the same place on both canvas sizes.

**Why this is allowed to be WYSIWYG when the card's wording is not.** D-021 refused
in-place editing of the title because the browser would have to reimplement font
metrics, hyphen aware wrapping and a card whose height follows its artwork, and two
layout engines drift. A sticker has no layout. It is one bitmap at one position, and
the browser shows the very image the renderer will paste. Same reasoning, opposite
answer.

**Consequence.** Stickers are pixels, so changing one means rendering again, exactly
like the title. Unlike the title, you can see the result before paying the thirty
seconds, so you only render once you are happy. The page says which of the two
states it is in.

**Amended 2026-08-20 by [D-036](#d-036-a-sticker-that-moves-is-a-second-mechanism-and-the-clipboard-is-how-it-arrives).**
An animated sticker keeps every promise above except one: its **phase**. Position,
size and rotation are exact, and which frame of the loop you happen to see in the
preview is not the frame the render will be on. A browser and an encoder cannot be
held to the same instant of a loop.

**The library is OpenMoji**, 4,495 drawings at 618 pixels, downloaded by
`scripts/setup_stickers.sh` into the same data directory the PO token provider uses,
never into the repository. It is CC BY-SA 4.0, so attribution belongs in the README
if this is ever published. It was chosen over Twemoji because Twemoji ships 72 pixel
PNGs, which would be a four times upscale on a 1080 wide frame, and over a colour
emoji font because Pillow's colour bitmap path is fussier than pasting a PNG and
would have been the same artwork twice.

**Placement is warned about, not prevented.** A sticker inside the bands WhatsApp
draws over gets an amber outline in the page and a line in the log, and is then
placed exactly where it was asked to be. Somebody putting a sticker in the corner
has made a choice; the text layer is generated and so is still kept out by
`tests/test_safe_zone.py`.

**Not animated.** An animated sticker is a second video input with its own loop and
timing in the filter graph, not a paste. Tracked as [TASKS.md](TASKS.md) T-019.

---

## D-023: Both ladders lead with the format a section can be cut from

**Date:** 2026-08-19
**Status:** accepted

`STRATEGIES_VIDEO` used to start with `web_safari 95/94/93`, the HLS renditions.
That entry now fails on every single video-mode run, so `web_safari` sits at the end
as a probe and the audio ladder leads with `mweb/18`. **The video ladder leads with
`default 95/96` since 2026-08-20**, which is the amendment at the foot of this
decision: same renditions, different client.

**Why.** Two measurements on 2026-08-19:

- `--list-formats` through `web_safari` returns four storyboards and no media at
  all. The entry was not "sometimes better", it was dead, and leading with it cost
  4 to 9 seconds and a "fell through" warning on every video clip made all day.
- The DASH renditions do exist: 136 is 720p and 137 is 1080p. But
  `--download-sections` hands their URLs to ffmpeg, and googlevideo answers ffmpeg
  with `403 Forbidden`. Tried with the native downloader, with a single stream, and
  with an audio only stream: 403 every time.

**Consequence, stated plainly.** Video mode was capped at 360p, upscaled to 1080
wide. The only way past it is to download an entire stream, 70 MB for a seven minute
video, to keep fifteen seconds. That is a worse trade than softness, so it is not
done. Card mode is unaffected: its pixels are our own 1080p card, and format 18
carries the 128 kbit/s AAC the audio needs.

**Amended 2026-08-20: the HLS renditions came back, from a different door.** Not
`web_safari`, which still returns four storyboards and nothing else, but the
**default** client, which lists 93 to 96 and lets a section be cut from them.
Measured:

| Question | Answer |
|---|---|
| Can a section be cut from format 95? | **Yes.** 1280x720 h264 with its own aac, 12.08 seconds, 1.8 MB, in about 5 seconds. Bounded, which DASH never was |
| Does DASH work now? | **No.** 136 and 137 still answer ffmpeg with 403, tried again on 2026-08-20 |
| Is it offered for every video? | **No, and this is the catch.** It is a property of the video: a popular music video offered 93 to 96 on three consecutive asks, and one of the owner's own uploads offered none on three. That same upload did offer 95 earlier the same day, and a real 5 second section was fetched from it, so the answer can also change under you |

So `STRATEGIES_VIDEO` now leads with `default 95/96` and keeps `mweb/18`
underneath. **Video mode is 720p when YouTube offers HLS for that video and 360p
when it does not**, and a video that does not costs one failed attempt, about 2
seconds, before the ladder falls through. The run log names the client and format
that won, so which one happened is never a guess. [TASKS.md](TASKS.md) T-018.

---

## D-022: A dedicated posting profile, and any debug browser will do

**Date:** 2026-08-19
**Status:** accepted

The posting browser is a Chrome started with `--remote-debugging-port` and its own
`--user-data-dir`. The server prefers the configured port and then tries the other
debug ports on the machine, using the first browser that holds a WhatsApp Web tab.

**Why not "whatever Chrome I am already using".** It was asked for, and it cannot
be done:

- Chrome exposes no protocol unless it was started with the switch. There is no way
  to turn it on afterwards, and no way to reach a browser that was started without
  it.
- Chrome 136 and later ignore `--remote-debugging-port` when the default profile
  directory is used. It is a deliberate hardening: a non default directory gets a
  different encryption key, so profile data is protected from anything that abuses
  the protocol. This machine runs Chrome 150, so the restriction applies.
  https://developer.chrome.com/blog/remote-debugging-port
- A page on loopback cannot drive a tab on another origin. Only an extension could,
  and an extension is rejected for other reasons in D-019.

**So the cost is one QR scan, once.** In exchange, the discovery makes the common
case work without configuration: if the browser the page is open in happens to have
a debug port and a WhatsApp tab, that is the one used, and the health chip names the
port so there is no guessing. `POST /api/browser` starts the profile if nothing is
running, so the launch command does not have to be remembered either.

---

## D-021: The caption is edited in place, the card wording is edited in the form

**Date:** 2026-08-19
**Status:** accepted

The caption is a `contenteditable` sitting in the preview exactly where WhatsApp
draws it. The title and the second line are ordinary inputs in the compose form.

**Why the split is not arbitrary.** It follows what the thing is made of.

- The caption is **text sent alongside the video**. Editing it costs nothing: one
  request rewrites `.caption.txt`, and what is on screen is what gets posted. So it
  is edited where it will be read, which also answers "show me the caption in the
  preview" with the same gesture.
- The title and the second line are **pixels inside the video**, laid out by Pillow
  with font metrics, hyphen aware wrapping, and a card whose height follows its
  artwork. To edit those in place, the browser would have to reimplement
  `compose.py` well enough to be believed, and then two layout engines would drift.
  A Shopify style click-to-edit card would be a lie the moment it disagreed with
  the render.

**Consequence.** Changing the wording means making the clip again, about 30 seconds,
and the page says so where the fields are. Changing the caption is instant. The
sidecar in D-020 is what makes the re-make cheap to ask for.

---

## D-020: The page loads the composer and stops. Sending is a second press

**Date:** 2026-08-19
**Status:** accepted

The primary button is **Load into WhatsApp**: it opens the Status composer, attaches
the clip, types the caption, and stops. **Send it for me** is the secondary button.
`--load` does the same from the command line; `--post` still sends.

**Why.** The owner posts one Status at a time and wants to see it in WhatsApp before
it goes out. Sending is the one irreversible step in the whole tool, and it is the
one step that needs no automation: it is a single click in a window that is already
open. Everything before it is the tedious part, and that is what the tool is for.

**Why it is safer, too.** `POST /api/post` sends only when the body says
`send: true`. An omitted flag, an old client, or a malformed request now means "load
it", never "broadcast it". Two overlapping requests are refused with a 409, because
the composer holds every file it is given and sends all of them at once: that is how
one command posted two Statuses on 2026-08-18.

**Consequence.** A loaded composer stays open until it is sent or cancelled, and the
next load cancels it first. The follow up text Status applies only to sending, since
there is nothing to follow up until something has gone out.

---

## D-019: A local page, not an extension and not a packaged app

**Date:** 2026-08-18
**Status:** accepted

`wastatus serve` opens a one page interface on loopback. The engine stays a command
line tool and a library; the page is a front end over it.

**Why a page.** The owner wanted something friendlier than typing a command. A local
page costs one module and one html file, works identically on both his machines,
needs no packaging, and is the same interface phase 2 will host on a server later.

**Why not a Chrome extension.** It cannot contain this work. There is no ffmpeg in an
extension, only ffmpeg.wasm, and this is not a light encode: 1080x1920, a Ken Burns
zoom, a waveform overlay, a blur fill in video mode. An MV3 service worker is also
killed while idle, so a minute long render needs an offscreen document and still sits
inside memory limits. And extraction is the hardest part of the whole tool, PO
tokens and the JS challenge and a five entry client ladder, which would have to be
rewritten in extension JavaScript and maintained against YouTube forever.

**Why not a packaged desktop app.** It buys an icon and no capability. The cost is
permanent: bundling ffmpeg and Node, signing and notarising for macOS, and an update
mechanism, paid on every release to save one line of typing.

**What the split preserves.** Interface and engine are separate, so the hosted UI in
phase 2 is this page with a different host, and if a browser extension is ever worth
building it can be a thin capture front end that hands a URL and a timestamp to this
engine rather than trying to be the engine.

**Standard library only.** `http.server` with a thread per request is enough for one
user, and a web framework in `requirements.txt` would be more supply chain than the
feature deserves. The trade is that progress is polled every 600ms rather than
streamed, which at this scale nobody can tell apart.

---

## D-018: The card names the artist, and reads a title the way a person would

**Date:** 2026-08-18
**Status:** accepted

Three fixes, all found by running the owner's own library through the tool:

**The artist beats the channel.** An auto-generated music upload has a channel like
`Release - Topic`, which cleans up to the meaningless `Release`. Its `artist` field
said `Project Samskriti`. Music apps show the artist, so the card does too, falling
back to the channel when YouTube knows no artist.

**Two spellings of one name are one name.** Tamil uploads carry the title twice,
once per script, and after transliteration the two rarely match character for
character: the uploader's `Potri Thiruthandagam` next to our
`Potrith Thiruththaandagam`. Comparing phonetic skeletons catches it. Fold the
consonant digraphs romanisation disagrees about, drop any remaining `h`, collapse
doubled letters, and both become `potritirutandagam`.

Numbers are compared separately and exactly, because `Thevaram Vol I` and
`Thevaram Vol II` score 0.92 on skeleton similarity and are different volumes.
Separators survive too: rewriting `A - B` as `A | B` when nothing was dropped would
be a gratuitous change to a title that was already fine.

**Academic capitalisation is normalised.** `Thiruppugazh viRalmAranaindhu
(thiruchchendhUr)` reads as broken. Each run of letters is judged on its own, not
each word: `Varma-VARA` is two runs, one deliberately all caps, and judging the pair
together mangled it to `Varma-Vara`. Only runs of eight letters or more are touched,
so `YouTube` survives; `SoundCloud` does not, which is the accepted cost.

---

## D-017: The bitrate comes from the duration, not from a constant

**Date:** 2026-08-18
**Status:** accepted

`render.video_maxrate` derives the encoder's ceiling from the clip length so the
file lands near 10 MB whatever its duration, under the 10 MiB the composer refuses
at. `pipeline.MAX_DURATION` is 90 seconds. The budget was 9.5 MB until the ceiling
was bisected on 2026-08-20, which is the amendment below.

**Why:** WhatsApp refuses media it will not take by never opening its editor, with
no message at all. Measured against the real composer:

| Clip | Verdict |
|---|---|
| 9.4 MB, 30s | accepted, and posted |
| 8.8 MB, 60s | accepted |
| 9.7 MB, 60s | accepted, and posted |
| 9.7 MB, **90s** | **accepted** |
| 13.7 MB, 90s | refused |
| 21.8 MB, 60s | refused |

The owner gives the platform limits as 90 seconds and 16 MB. A fixed 2800 kbit/s
ceiling produced about 21 MB at 60 seconds, well past that, so every 60 second clip
the tool made would have failed to post, and it would have looked like a bug in the
posting driver rather than in the encoder.

**Length is not the constraint.** 90 seconds at 9.7 MB was accepted, which settles
what the 13.7 MB refusal at the same length could not: the composer was rejecting
the size. So the full 90 seconds is usable, as long as the file is small.

**The ceiling was 9.5 MB and is now 10 MB, because the line was found.** Amended
2026-08-20 by bisecting it against the real composer, with 90 second probes that
differed only in size:

| Probe | Verdict |
|---|---|
| 10,311,640 | accepted |
| 10,452,278 | **accepted** |
| 10,519,352 | **refused** |
| 10,650,175 | refused |
| 11,013,670 | refused |

Those middle two sit 33 kB either side of **10 MiB, 10,485,760 bytes**, which is the
ceiling. Not the 16 MB the platform documents, and not a length limit: every probe
was the same 90 seconds. `render.PLATFORM_MAX_BYTES` holds it.

**The budget is 10,000,000 and not 10,485,760** because the budget is not a cap. It
sets a maxrate, and the encoder overshoots it by about 2 percent: a 9.5 MB budget
produced 9,684,891 bytes at 90 seconds and 9,690,149 at 60. 10,000,000 leaves 4.6
percent of headroom, twice the measured overshoot, and a test holds that ratio.

**And if a clip still comes out over the line**, `pipeline.produce` says so in the
log and the command line report says so on screen. WhatsApp will not: it takes the
file and never opens its editor, which reads as a broken tool rather than a refused
file. [TASKS.md](TASKS.md) T-014.

**Consequence:** a 15 second clip keeps the full quality ceiling, since it is
nowhere near the budget. A 90 second one gets about 716 kbit/s, which is soft on a
large screen and fine on a phone.

---

## D-016: The artwork's own shape decides the card, and padding is cropped

**Date:** 2026-08-18
**Status:** accepted

Three related pieces of the same problem:

**Padding bars are cropped before the artwork is used.** A YouTube thumbnail is
always 16:9, so an uploader whose picture is a different shape pads it with flat
bars. The measured case, a 2.35:1 music thumbnail, is 1280x720 carrying an 85 pixel black bar
above and 84 below a 2.35:1 picture. Left alone those bars appear inside the card
and, blurred, as dead bands across the background. `compose.detect_bars` finds
them by sampling points along each row and column and asking whether the line is
flat and the colour of the outermost one, which is what a bar is. Both conditions
are needed: a dark row of real picture is rarely flat, and a gradient is flat
nowhere.

**The card takes the artwork's aspect ratio.** Forcing a 2.35:1 still into a 16:9
box crops a quarter of its width, which on a group photograph cuts people out of
the sides. `card_height` derives the height from the shape, clamped so an unusually
square image cannot crowd WhatsApp's header band. The card's **bottom** is fixed
and only its top moves, so the card and the title stay a tight pair however the
artwork is shaped, and every post in the tray reads as the same series.

**Letterboxed source video is cropped too.** The same defect appears in `--video`
mode, where the source's own bars sit inside our blurred fill as hard black seams.
`render.detect_source_crop` samples three frames, runs the same detector, and takes
the smallest bar found on each side, so a dark frame can only make the crop more
conservative, never invent one. Offsets and dimensions round inwards to even
numbers, because yuv420p cannot encode odd ones and a crop must never be able to
include a row of the bar it was meant to remove.

(D-054 folded that function into `render.source_picture`, which returns the crop
and the size it left in one pass. The detector and the sampling are unchanged.)

**Considered and rejected:** ffmpeg's `cropdetect`, which would mean a second
detection mechanism and parsing numbers out of ffmpeg's stderr. Anchoring video
mode's frames above the title the way card mode does, which breaks down for a
vertical source, where centring degrades gracefully and anchoring does not.

**Also here:** a soft drop shadow under the card, because a card floating on a
blurred copy of itself reads as a hole without one. And `SAFE_TOP`, the top 12
percent, where WhatsApp draws the avatar, name, timestamp and playback controls.
That band was being respected by accident before this; now it is measured, in
`tests/test_safe_zone.py`, alongside `SAFE_BOTTOM`.

---

## D-015: Nothing is said twice

**Date:** 2026-08-18
**Status:** accepted, amends D-014

The caption is the URL alone. The frame carries the title and the channel and no
URL.

**Why:** the owner, on seeing the first clean post: the title is already on the
card so it does not belong in the caption too, and a URL drawn in the frame "is of
no use". He is right on both counts. The card and the caption sit a centimetre
apart on the screen, so repeating either one reads as a listing rather than as
something a person sent, and a URL in the pixels is a string a viewer can read but
cannot tap, next to one they can.

**What this withdraws:** the small in frame URL line that D-014 introduced when the
link pill was removed. Its justification was that a downloaded and forwarded clip
loses its caption and keeps its pixels. That is true, and it is worth less than a
clean frame: a forward is not the case being designed for, and a viewer who wants
the track can ask.

**Consequence:** `CardText` has no URL field, so a caller cannot put one back
without a deliberate change. `compose.CARD_TITLE_TOP_FOOTER` is gone too, because
without the URL line the worst case block fits from the normal start.

---

## D-014: The bottom 15 percent of the frame belongs to WhatsApp

**Date:** 2026-08-18
**Status:** accepted

`compose.SAFE_BOTTOM` is y 1632 of 1920. Nothing is drawn below it in either
render mode, and `tests/test_safe_zone.py` measures the painted pixels to prove
it for the worst case text block.

**Why:** WhatsApp draws the Status caption across the bottom of the frame. The
first real post, on 2026-08-18, put our link pill at y 1640 to 1736 directly
underneath that caption and both became unreadable. No amount of local frame
inspection finds this, because the overlap only exists once WhatsApp composites
its own interface over the video.

**What replaced the pill:** a small, quiet URL line inside the text flow, on the
reasoning that a forwarded clip keeps its pixels but loses its caption. That line
was itself removed the same day by D-015. The pill's removal stands; only its
replacement was withdrawn.

**Consequence for layout:** every element in `_draw_text_layer` flows from the one
above it rather than sitting at a fixed y, so a three line title cannot push
anything into the reserved band. Each mode's `title_top` is chosen for the worst
case block, and the waveform was moved from 1400 to 1450 to sit in the space the
pill vacated.

---

## D-013: One post by default, the follow up is a flag

**Date:** 2026-08-18
**Status:** accepted, supersedes D-003

A run produces and posts one Status. `--follow-up` adds the text only second one.

**Why:** the premise of the two post flow was that a caption URL is not tappable.
That premise was wrong. Confirmed on 2026-08-18 in WhatsApp Web, where the caption
renders as a real anchor, and then on the owner's phone, where tapping the caption
URL opened the YouTube app. One post is what a person would actually send.

**Why keep the flag:** a text only Status also gets a link preview card, which is
a different look, and it costs nothing to keep the path that already worked.

---

## D-012: Posting drives WhatsApp Web over CDP, not an unofficial client

**Date:** 2026-08-18
**Status:** accepted, narrows D-002

`wastatus --post` attaches to an already logged in WhatsApp Web tab through the
Chrome DevTools Protocol and drives the real Status composer: attach the file,
type the caption, press Send, wait for the upload.

**Why:** D-002 deferred posting because every route considered authenticated as
the owner's account through an unofficial protocol library. Driving the real web
client is not that. It is the same client the owner uses by hand, doing the same
things, so it carries no account risk beyond ordinary web use. It also needs no
recipient JID list, because the composer's own audience selector handles that,
which retires the blocking question in T-002 entirely.

**Cost:** it needs a Chrome running with `--remote-debugging-port` and a logged in
tab, so it works on a desktop and not on a phone or a headless server. Phase 2's
always on host will need a different answer, which is why this is a flag rather
than the only path.

**Measured:** a 4.1 MB, 12 second clip uploaded in 11 seconds; a 9.3 MB, 30 second
one took about 40. Chrome stops answering the debug protocol while it uploads, and
throttles the tab entirely when it is in the background, so the driver foregrounds
the tab first and treats an unanswered poll as "still going".

---

## D-011: Two logs, text for debugging and jsonl for trends

**Date:** 2026-08-18
**Status:** accepted

`logs/wastatus.log` is rotating text carrying the complete yt-dlp and ffmpeg
output. `logs/runs.jsonl` is one object per run with the window, the mode, the
winning extraction strategy, per stage timings and output size.

**Why two:** they answer different questions. When a run fails you need the full
subprocess output, which is verbose and only interesting once. When you want to
know whether the extraction ladder is degrading, you need one structured line per
run that you can grep and count. Forcing both into one file makes each worse.

**Why the winning strategy is recorded:** the ladder degrades silently. A run that
falls through from `mweb` to a later entry still succeeds, just with a worse
source. Recording it means the degradation is visible before the ladder runs out.

**Failure output stays short on screen.** The user sees the last few lines plus a
pointer to the log. Everything else goes to the file.

---

## D-010: No instructional text on the card

**Date:** 2026-08-18
**Status:** accepted

The footer and the `NOW PLAYING` eyebrow both default to empty. `--footer TEXT`
and `--eyebrow [TEXT]` add them back.

**Why:** the owner's words, on seeing the output: a Status is an expression of
himself, and `Full link in the next status` made it read as formal. Instructional
copy tells the viewer what to do, which is what an advertisement does. The link
pill already carries the information.

**Consequence:** the freed space let the title cap rise from two lines to three,
which stopped long compound titles being ellipsised mid-name.

---

## D-009: The output folder prunes itself

**Date:** 2026-08-18
**Status:** accepted

After each successful run, all but the newest 20 clips are deleted, mp4 and
sidecars together. `--keep-last N` changes the limit and `0` disables it.

**Why:** at 5 to 10 MB a clip, an unbounded folder becomes a housekeeping chore
the owner has to remember. Pruning on write means it never grows.

**Why newest count and not age:** a count is predictable regardless of how often
the tool is used. An age rule deletes everything after a quiet fortnight, which is
the wrong behaviour for someone who posts in bursts.

**Safety:** clips are pruned as groups, so a caption is never orphaned from its
video, and pruning runs only after the new clip has been written.

---

## D-008: Filenames lead with the date and the song, not the video id

**Date:** 2026-08-18
**Status:** accepted

`20260818_sinna-sinna-murugaiyaa_70-85.mp4` rather than
`A6DfGQsdz1Y_70-85.mp4`.

**Why:** the owner's point, and correct: a video id is not human readable, so the
folder was unscannable. Leading with `YYYYMMDD` means a plain alphabetical sort is
also chronological.

**Traceability:** dropping the id from the name loses nothing, because the full URL
is in the sidecar caption file and the id is in every run record in
`logs/runs.jsonl`.

**Collisions:** the same song and window clipped twice on the same day gets a `-2`
suffix rather than silently overwriting.

---

## D-007: The tool runs from a wrapper script, output lands where you are

**Date:** 2026-08-18
**Status:** accepted

`./wastatus.sh` sets `PYTHONPATH` to the project and executes the virtualenv
interpreter, so the tool runs from any directory and writes `out/` relative to
where it was invoked.

**Why:** the owner asked to be spoon fed the run steps.
`.venv/bin/python -m wastatus` is a poor thing to have to remember.

---

## D-006: aksharamukha is kept behind a compatibility shim

**Date:** 2026-08-18
**Status:** accepted, with a known fragility

Tamil is romanised with `aksharamukha`, target `RomanReadable`, preprocessor
`TamilTranscribe`. The package imports `ast.Str`, removed in Python 3.12, so
`translit.py` defines it before importing.

**Why:** the alternatives were measured on real titles and were all worse.

| Approach | `சின்ன சின்ன முருகையா` | `கந்த சஷ்டி கவசம்` |
|---|---|---|
| Unidecode | `cinnnnnn cinnnnnn murukaiyaa` | `knt csstti kvcm` |
| indic-transliteration ISO | `jhinna jhinna murughaiya` | `ghandha jhasdhi ghavajham` |
| aksharamukha RomanReadable + TamilTranscribe | `sinna sinna murugaiyaa` | `kandha sashti kavasam` |

Tamil script is phonemically ambiguous, so correct romanisation needs contextual
voicing rules rather than a character map. Only aksharamukha has them.

**Rejected:** pinning the project to Python 3.11 to avoid the shim, which would
add setup friction on both machines for one import line. Hand rolling a Tamil
romaniser, which is a project in itself.

**Fragility:** the shim breaks if aksharamukha starts needing `ast.Str` for real.
The import is wrapped and falls back to Unidecode, so the tool degrades rather
than dies. `--title` is always available. See
[RUNBOOK.md](RUNBOOK.md).

---

## D-005: Media is fetched through a client and format ladder

**Date:** 2026-08-18
**Status:** accepted

`fetch.download_section` tries ordered `(player_client, format)` pairs until one
produces a file, rather than requesting a single best format.

**Why:** measured behaviour. No single combination works on all videos. Against a
control video and a Tamil devotional upload, `web_safari` HLS worked on the first
and listed only storyboards on the second, while `mweb` format 18 worked on both.
Full table in [docs/extraction.md](docs/extraction.md).

**Also required:** a running PO token provider and
`--remote-components ejs:github`. Without the token, media URLs return 403 even
though metadata resolves. Without the solver, signatures do not solve.

**Rejected:** switching away from yt-dlp. pytubefix, NewPipeExtractor and Cobalt
all face the same wall, because the block is on IP reputation and token presence,
not on the tool. yt-dlp has the fastest patch cadence, so leaving it would cost
maintenance velocity and gain nothing.

**Expect to revisit.** YouTube ships anti bot changes weekly.

---

## D-004: Card mode is the default, real video frames are opt in

**Date:** 2026-08-18
**Status:** accepted

Default output is artwork plus a slow zoom and an audio waveform. `--video` uses
the real frames.

**Why:** most Tamil devotional uploads are already a static image over audio, so
the card loses almost nothing on the common case while being faster, smaller and
visually consistent across every song. The zoom and waveform are what keep it
reading as a video rather than a photo, which matters for whether a viewer stops
and listens.

**Cost note:** the original rationale included a large bandwidth saving. That
turned out to be wrong. Audio only DASH streams are 403 blocked, so the working
path pulls a muxed 360p progressive stream at roughly 1.2 MB per 15 seconds
either way. Video mode can now pull an HLS rendition instead where one is offered,
which is about 1.8 MB for 12 seconds, still a section rather than a whole file. The real justification is robustness, speed and consistency, not data.

---

## D-003: Every status is two posts

**Date:** 2026-08-18
**Status:** SUPERSEDED by D-013 on 2026-08-18. The claim below is false: a caption
URL is tappable, on the web client and on a phone. Kept for the record.

Each run emits the clip plus a separate text only status carrying the link.

**Why:** a URL in a media caption appears to be plain text, while a text only
status is linkified with a preview. The two post flow guarantees a tappable link
either way.

**Rejected:** a QR code in the frame, which the owner judged too much friction for
a viewer.

**How it fell:** the claim rested on secondary sources rather than a device test.
Posting a real Status showed the caption is a real anchor in WhatsApp Web, and the
owner then tapped it on his phone and it opened the YouTube app. The lesson is in
[MEMORY.md](MEMORY.md): a load bearing claim from a secondary source is worth a
five minute test before anything is designed around it.

---

## D-002: No WhatsApp automation in the MVP

**Date:** 2026-08-18
**Status:** accepted

The tool produces the clip and the two texts. The owner posts them.

**Why:** whatsmeow can post to `status@broadcast`, but its own README calls status
sending experimental and warns it may not work for large contact lists, and status
broadcast needs an explicit recipient JID list. No packaged CLI exposes status
with media as a supported command: wacli does not document it, and gowa lists
"Post Whatsapp Status" as a feature while exposing no such path among its 60 plus
documented endpoints. All of these are unofficial clients authenticating as the
owner's primary account, which is the single asset the product depends on.

**Deferred, not rejected.** Phase 3 in [ROADMAP.md](ROADMAP.md) revisits it behind
an explicit flag, tested against a small contact list first.

---

## D-001: All text is drawn by Pillow, never by ffmpeg

**Date:** 2026-08-18
**Status:** accepted

`compose.py` renders every glyph into a PNG which ffmpeg then composites.

**Why:** the reference ffmpeg build has no freetype and no libass, so `drawtext`,
`subtitles` and `ass` do not exist in it. Confirmed against
`ffmpeg -buildconf` and `ffmpeg -filters`. Depending on how a given ffmpeg was
compiled is exactly the sort of thing that breaks when moving between Linux and
macOS.

**Secondary benefit:** Pillow gives real text layout, so wrapping, ellipsising,
letterspacing and the rounded pill are straightforward rather than an expression
language exercise.

**Consequence:** the fonts are bundled in `assets/fonts` rather than resolved from
the system, because macOS ships a different font set.
