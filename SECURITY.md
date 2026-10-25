# Security

Small project, but it touches two accounts worth protecting: a YouTube session
and a WhatsApp account.

**If you have just cloned this, three things matter more than the rest.** The local
page hands its token to whoever loads it, so **do not put it on a LAN address or
`0.0.0.0`**; loopback or your own tailnet only, and it is loopback by default.
Chrome's debug port, when posting is in use, is an **unauthenticated control channel
over a logged in WhatsApp session**, so it stays on `127.0.0.1` and the browser gets
closed after. And `--post` presses Send on a real account, which is why it is off by
default and why nothing in here sends without being told to twice.

## Current state

The tool holds no credentials and stores no session. Producing a clip is an
anonymous fetch plus local processing, and there is nothing in the repo to leak.

`--post` reaches a WhatsApp account, but not by holding anything: it drives a
browser the owner has already logged in, over Chrome's debug port on loopback. The
session lives in that Chrome profile, where the owner put it, and can be revoked
from the phone like any linked device. See [DECISIONS.md](DECISIONS.md) D-012.

The hosted renderer and the browser extension, live since 2026-10-24, are the one
part that runs on the internet and serves other people. They are described below,
in **The hosted renderer and the extension**.

## Secrets handling

Nothing sensitive goes in the repo, in code, or in a committed config file. The
repository is public, so `tests/test_publishable.py` fails on any email outside
`example.com`, any public IPv4 address, any home directory, and anything on the
git-ignored `.publish-deny` list of the maintainer's own strings.

Configuration arrives through **environment variables**, and, since 2026-08-20, from
an optional **`.env` file** beside the code. The file is ignored by git; the
environment always wins over it; and the committed `.env.example` names every setting
the tool reads and holds no value for any of them. There is nothing to put in it that
is required: the tool runs every day with none of it set.

## Table SE-1: Configuration surface

| Variable | Sensitivity | Notes |
|---|---|---|
| `WASTATUS_PROXY` | **high**, may embed credentials | a proxy URL with user and password. Never commit, never log |
| `WASTATUS_COOKIES_FROM_BROWSER` | **high** by implication | names a browser profile, and yt-dlp then reads live YouTube session cookies from it |
| `WASTATUS_POT_DIR` | none | filesystem path |
| `WASTATUS_POT_PORT` | none | port number |
| `WASTATUS_CHROME_DIR` | **medium** | the posting browser's profile directory, which holds a logged in WhatsApp session. Anything that can read it can read that session |
| `WASTATUS_STICKER_DIR` | none | where the sticker library and uploads live |
| `WASTATUS_CACHE_DIR` | **low** | where the session label page is written. It names ports, the profile path and the output folder, and deliberately **not** the page token: a file anything on the machine can read must not carry the thing that authorises posting |
| `WASTATUS_LOG_DIR` | **low** | where run logs are written. They name videos and output paths, not credentials, and a `t=` token in a logged URL is redacted |
| `WASTATUS_ENV` | none | read settings from a `.env` file somewhere other than beside the code |

`.gitignore` covers `.env`, `MEMORY.private.md`, `.venv/`, `out/` and `logs/`. If a
credential file is ever added, it goes in `.gitignore` in the same commit.

## The cookie path carries account risk

`WASTATUS_COOKIES_FROM_BROWSER` makes yt-dlp act as a logged in YouTube user. If
that traffic is judged abusive, the consequence lands on a real Google account,
not on an anonymous IP.

Prefer a proxy. Use cookies only when a proxy has been tried and failed, and
prefer a throwaway account over a primary one. Recorded in
[RUNBOOK.md](RUNBOOK.md).

## The WhatsApp account is the asset

That account is the entire distribution channel, so losing it loses the product.

**What the tool does today.** `--post` attaches to an already logged in
web.whatsapp.com tab through the Chrome DevTools Protocol and drives the real Status
composer. This is the owner's own client doing what the owner does by hand, so it
carries no account risk beyond ordinary web use, and it needs no pairing, no
credential, and no recipient list. Recorded as
[DECISIONS.md](DECISIONS.md) D-012.

**What is still refused.** Authenticating as the account through an unofficial
protocol library, whether whatsmeow, Baileys, or anything that pairs as a device.
D-002 stands for that, and [AGENTS.md](AGENTS.md) enforces it.

**Constraints on the posting path:**

- Posting is off by default and requires `--post`
- Nothing presses Send on the owner's audience without his say so, per
  [AGENTS.md](AGENTS.md)
- The debug port is loopback only. A Chrome debug port reachable from the network
  would hand anyone full control of a logged in WhatsApp session, which is a far
  larger exposure than anything else in this repo
- `wa_post.py delete-all` destroys Statuses irreversibly and requires `--yes`

If a session credential is ever stored, it belongs outside the repo, in the
provider style user data directory, with file permissions restricted to the owner.

## The local page

`wastatus serve` runs a standard library HTTP server. It is the second most
sensitive thing here after Chrome's debug port, because it can post to a Status and
read files from the output folder.

| Guard | Why |
|---|---|
| Binds `127.0.0.1`, and only adds another address when told to | not reachable from the network unless `--also-on` says so, which is off by default |
| `--also-on` takes an IP literal, never a name | a name resolved once at bind time would not match the `Host` a browser later sends, which is what the origin check compares against |
| Loopback stays bound alongside it | so the address a request arrived on still says which device it came from. See D-027 |
| Every `/api/` call needs an `X-Wastatus-Token` header | any website you visit can send requests to a loopback server. A custom header cannot be set cross-origin without a preflight |
| Preflights are answered 403 with no CORS headers | so a cross-origin caller can never get permission to send that header |
| An `Origin` that is not the address the request was addressed to is refused | defence in depth, even holding the token. Derived from the request's own `Host` rather than from a constant, so the check survives the page being opened on another address |
| The `Host` header is trusted only when it names an address, never a name | DNS rebinding: an attacker can point `evil.com` at 127.0.0.1, and the browser then sends `Host: evil.com` with a matching `Origin`. Both are refused |
| The token is compared with `secrets.compare_digest` | not because a timing attack on loopback is likely, because there is no reason to write the other comparison |
| The two media endpoints accept the token as a `t` query parameter | an `<img>` or `<video>` cannot send a header. They are read only |
| Clip names must match `^[A-Za-z0-9_-]+$` | the output folder is addressable by name, so nothing else may be |
| The token is per process, from `secrets` | it dies with the server |
| Any `t=` in a logged URL is redacted | media carries the token in the query string, and the text log outlives the process. Without this, one secret ends up in a file on disk |
| `POST /api/post` sends only when the body says `send: true` | an omitted field, an old client or a malformed request means "load it", never "broadcast it" |
| A second posting request while one is running is refused with a 409 | the composer sends every file it holds, so overlapping requests are how one command posts two Statuses |
| A caption over 1024 characters is refused | it is written to a file that is then typed into someone else's client |
| A sticker id must match `^(openmoji\|mine):[A-Za-z0-9_-]{1,64}$` | no dots and no slashes, so an id cannot address anything outside the two sticker folders |
| An uploaded sticker is decoded and re-encoded by Pillow | nothing of the original file survives that round trip. The bytes on disk are ones we produced, not ones we were handed |
| An upload over 2 MB, or one Pillow cannot read as an image, is refused | a sticker is a small drawing. Anything else is something else. An animated one gets a more generous 8 MB, 720 pixels an edge and 240 frames, because a GIF carries many pictures rather than one |
| A request body over 12 MB is drained and refused with a 413 | `Content-Length` is whatever the sender says it is, so it is never read unbounded into memory. Draining first, then answering, is what stops the sender seeing a broken pipe instead of the reason |
| Only `mine:` stickers can be deleted | the library is not ours to remove through an api call |
| `POST /api/browser` takes no parameters | it starts a browser with a fixed command line. Nothing from the request reaches the process it launches |
| `POST /api/cancel` only stops a render | a post cannot be stopped, so a caller cannot leave WhatsApp in an unknown state. See D-025 |
| `POST /api/clip/delete` deletes inside the output folder only, by a name matching the same pattern | it is the one route that destroys data. It is refused while WhatsApp is being driven, and the page makes it two presses |
| `?w=` only makes the widths in `stickers.THUMB_WIDTHS` | otherwise one image could be written to disk at a thousand sizes on request |

The page never sends by itself. Rendering is one button, loading the composer is
another, and sending is a third that says so. `tests/test_serve.py` covers each
guard, including the default: with no `send` field, nothing goes out.

`POST /api/browser` starts a real browser process on the machine. It is behind the
same token as everything else, and it is the one route that has a side effect outside
the output folder, so keep it that way: no arguments, no configurable command.

## Reaching the page from another device

`--also-on` is the one setting here that changes the trust boundary, so it is off by
default and the startup output says what it means.

**Off by default means off at every start.** The flag is not written to a file, an
environment variable or a service unit, so a Ctrl-C or a reboot returns the tool to
loopback alone and the second address has to be asked for again. That is the point:
widening the boundary is a thing you do knowingly, not a state a machine wakes up in.

**Since 2026-08-22 one machine may keep a standing answer**, `WASTATUS_ALSO_ON` in
`.env`. This is narrower than it sounds and worth being precise about: the file is
read when somebody runs the command and at no other time, nothing starts at boot,
D-028's refusal of a service stands, and empty is still the default everywhere it has
not been set. What it changes is that the owner stops retyping a flag he had typed
every day for three days. The startup output still names the second address and still
says in words that whoever opens that page can post, and `--also-on ""` returns a
single run to loopback. See [DECISIONS.md](DECISIONS.md) D-027, amended, and D-044.

**The page hands its token to whoever loads it.** That is fine on loopback, where
"whoever" is you. It is not fine on a shared network. So:

- **Use a tailnet.** Only your own devices can reach a tailnet address, which is as
  strong a boundary as loopback. `--also-on tailscale` resolves it for you.
- **Not `0.0.0.0`, and not the LAN address.** Both are accepted if you type them,
  because refusing to do what you asked is its own problem, but everyone on the
  network can then open the page and post to your Status.
- **A restart rotates the token**, so a page left open on a phone stops working
  rather than holding a stale credential.

Reaching it through a hostname, behind a tunnel, would need the `Host` check widened
on purpose. That is phase 2's business, not something to loosen for convenience.

## Local attack surface

Chrome's remote debugging port, when one is running for posting, is the most
sensitive thing on this machine: it is an unauthenticated control channel over a
logged in WhatsApp session. Keep it on `127.0.0.1`, never pass
`--remote-allow-origins=*`, and close the browser when it is not being used.

The server will use any debug browser on the machine that holds a WhatsApp tab, not
only the one it started. That is a convenience, and it is also the reason the point
above matters: a debug port left open is a door into whatever is logged in behind it,
for us and for anything else running as this user.

Chrome 136 and later refuse the debug switch on the default profile directory for
exactly this reason: a separate directory gets a different encryption key, so the
profile you actually browse with is not exposed by the port. Do not work around it.

The PO token provider is a node HTTP server on `127.0.0.1:4416`. It binds
loopback and is started and stopped per run. Two things to keep true:

- do not bind it to a non loopback interface
- the hosted renderer does not run it at all, because it never talks to YouTube;
  if a server ever does, it stays on loopback and is never exposed

## What this machine talks to

For most of its life the answer was YouTube and nothing else: yt-dlp, YouTube's
thumbnail host, and a token helper on loopback. The hosted renderer talks to nobody:
it only answers.

**The GIF picker adds one more, and only when you switch it on.** With
`WASTATUS_GIF_PROVIDER` set and its key present, a search sends **what you typed**
to GIPHY or KLIPY. That is the cost of the feature and it is worth stating plainly:
your search terms leave this machine. Nothing else does. No clip, no caption, no
address of yours, and nothing about what you post.

- **It is off by default**, and off is also what a provider with no key gets. An
  unconfigured copy has no toggle in the page and answers 404 on both routes.
- **The page never talks to the provider.** Every thumbnail is fetched by this
  server and served from this origin. The reason is the phone: it reads the page
  over the tailnet, and a linked thumbnail would put the phone in touch with GIPHY
  rather than just the laptop.
- **Nothing the browser names is fetched.** A pick sends an id from a search this
  server made, and the address is looked up here. `gifs.fetch` refuses anything that
  is not `https` and stops reading at the sticker ceiling regardless of what the
  provider's own byte count claims.
- **The keys live in `.env`**, which is gitignored and in the never commit list.
  They are sent to their own service and nowhere else.
- **To switch it off entirely**, empty `WASTATUS_GIF_PROVIDER` or delete the line.
  `wastatus/gifs.py` can be deleted outright without touching anything else.

See [DECISIONS.md](DECISIONS.md) D-043.

## Third party code

`scripts/setup_provider.sh` clones and builds
[bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider)
from GitHub and installs its npm dependencies, roughly 265 packages. That is a
real supply chain surface, accepted because the alternative is no working download
path at all.

Related: yt-dlp fetches its JS challenge solver from GitHub at runtime via
`--remote-components ejs:github`. This is yt-dlp's own distribution channel, and
the flag is required for signatures to solve.

Both are pinned only to "latest". Pinning them to a release would reduce risk and
increase breakage when YouTube changes. Current choice is latest, deliberately.

## The hosted renderer and the extension

In production, see [DEPLOYMENT.md](DEPLOYMENT.md) and DECISIONS.md D-081.

**What it holds.** A token file of SHA-256 hashes and names; uploads for at most 30
minutes idle; finished clips for at most an hour, and in practice until the
extension has downloaded them, when it deletes the job. No YouTube credentials, no
WhatsApp anything, no proxy. It never talks to YouTube.

**Who can reach what.**

- Every route but `/api/v1/health` needs a bearer token the owner made. Without
  one, a request gets 401 and nothing else.
- One token cannot see another's uploads or clips; they are answered as missing.
- No CORS headers on any response, so a web page holding a token still cannot read
  an answer. The extension's service worker does not need them.
- IDs are random, 24 characters, and matched against a strict pattern before they
  reach a path, so no request names a file.

**What it parses on someone else's behalf.** An upload is read by ffprobe (packets
only, nothing decoded) and then by ffmpeg, and artwork by Pillow. That is an attack
surface: a file crafted against a decoder bug. The mitigations are the token, so
only people the owner chose can send one, and the container: a non-root user, no
capabilities, `no-new-privileges`, a read-only root filesystem, three CPUs and 3 GB.
Sizes are capped before anything is written: 16 MB of audio, 64 MB of video, 4 MB
of artwork, 1 MiB per chunk.

**Logs.** The renderer logs the token's name, not the token, and the client address
Cloudflare passes on. There is no access log of its own any more: the only way in is
the tunnel (D-092).

**The extension.** It reads YouTube pages (to copy the player's buffers), WhatsApp
Web (only when **Load into WhatsApp** is pressed), YouTube's thumbnail host and the
renderer. The token is kept in `chrome.storage.local`, readable by the extension
and by anyone with the person's Chrome profile. The page world script answers a
capture request from any script on a YouTube page, including YouTube's own; what it
returns is bytes that page already holds. It never presses Send.

**Revoking.** `wastatus hosted token revoke NAME`, effective on the next request.
Losing the whole host loses nothing that matters: tokens are reissued and clips are
made again.

## SnipShare, the hosted page

DECISIONS.md D-087 to D-093, [docs/hosted-page.md](docs/hosted-page.md).

**What it holds, per person.** Their Google name, email and account id; what they
wrote when asking; sessions and grants as SHA-256 hashes only; counts per day; their
newest ten clips and their stickers; their GIF key encrypted with a key derived from
`WASTATUS_SECRET_KEY`; failure reports without any video, title or words, kept 30
days. The people database is mode 600 and backed up nightly, seven kept. The
server's `.env` holds the Resend key (sending only, one domain), the Turnstile
secret, the Chat webhook and the encryption secret, mode 600, outside the image.

**Who can reach what.**

- Every page but the public ones needs a session: a random cookie, `HttpOnly`,
  `Secure`, `SameSite=Lax`, 30 days, ended at once by suspension.
- Every call from the page also carries a value derived from the session that only
  the page has, and every change carries the site's `Origin`. A cookie alone, or
  another site's request with the cookie, is refused.
- The sign-up, sign-in and sign-out calls carry a custom header a cross-site form
  cannot set, and the site's `Origin`. Sign-up is behind Turnstile and five an hour
  per address; sign-in thirty.
- A person's clips, stickers and key are reachable only through their own
  workspace; another person's clip is answered as missing.
- The extension gets grants, never the session: 15 minutes, one purpose, used only
  against the page's own origin. An upload grant reaches `/api/v1/uploads` and
  nothing else; a clip grant names one clip.
- Sign-in only ever returns to a plain path on the site.
- Every page has a Content Security Policy: scripts from the site, Google's sign-in
  and Turnstile only, the tool page's one inline script by its hash; no framing.

**Mail.** Only ever to the owner's own address, never to an address someone typed,
so the sending domain cannot be used against anybody. A requester's words go into
the owner's Chat space with `<` and `>` replaced, so they cannot mention the space.

**The extension, on the site.** It answers only the site it was built for
(`externally_connectable`, and its own check of the sender's origin). A capture it
is asked for opens the video in a tab, muted, and closes it; it never runs two at
once, and paces itself to 20 captures and 10 loads an hour.

**Deleting.** **Delete my account** stops a render in progress and removes the
account, sessions, grants, clips, stickers, key and counts. Reports keep no email.

## Hardening from the audit before publication

Updated **2026-10-25T15:11:42+05:30**, when the repository was prepared to be made
public. The findings and their fixes are in [CHANGELOG.md](CHANGELOG.md) and
[DECISIONS.md](DECISIONS.md) D-100; the tests that hold them are
`tests/test_hardening.py` and `TestWhatAStrangerCannotMakeItDo` in
`tests/test_portal.py`.

**Table SE-2: what a request can no longer do**

| Before | Now |
|---|---|
| A link starting `--` reached yt-dlp as an option, so anyone holding the page token could load a config file of their choosing | `--` ends yt-dlp's options; a window needs an `http(s)` address |
| A page reached through a rebinding name (`Host: evil.example` pointing at 127.0.0.1) could read the local page's token from `/` | every request to the local server must name it by an address |
| A body was read, up to 12 MB, before anyone was signed in | the session is checked first; an unread body closes the connection |
| `Content-Length: -1` read until the socket closed | anything but digits is refused unread |
| A GET or HEAD carrying a body had that body parsed as a second request | refused with the connection closed |
| A title of 300,000 characters held the only render slot for hours | every line of words is held to 1,024 characters, and the ellipsis point is found by halving |
| The sign-up form answered with a typed address's standing | the same answer whatever the address |
| ffprobe and ffmpeg guessed an upload's format, playlists included | local files of the two containers YouTube sends, and nothing else |
| Errors carried paths on the server back to the person | the path is replaced by "a file"; the whole message is in the log |
| A proxy's password could be written to the debug log | masked |
| An upload grant outlived the sign-out of its last session | ends with it |

## Reporting

Single maintainer project, so there is no security team and no response time to
promise. **Report a vulnerability privately through GitHub**: on this repository,
**Security**, then **Report a vulnerability** (GitHub's private vulnerability
reporting). Please do not open a public issue for it. Include what you found, how to
reproduce it, and what it lets someone do; leave out anything that names a real
person's account. If private reporting is unavailable, open an issue that says only
"security report, please contact me" and the maintainer will find a private channel.

Never test against the hosted site with anybody's account but your own, and never in
a way that costs other people their use of it: run a local copy instead
([LOCAL_SETUP.md](LOCAL_SETUP.md)).
