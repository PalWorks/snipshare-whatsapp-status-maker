# API

Last updated **2026-10-25T15:16:18+05:30**

Every HTTP surface this project answers, and the messages the extension takes from
the site. Read from the code: `wastatus/serve.py`, `wastatus/hosted.py`,
`wastatus/portal.py`, `src/sw.js` and `wastatus/pages/hosted.js`. Where a route exists
for a reason, the reason is in [DECISIONS.md](DECISIONS.md); how the pieces fit is in
[ARCHITECTURE.md](ARCHITECTURE.md); the threat model behind every guard below is in
[SECURITY.md](SECURITY.md). What is stored, and where, is in
[DATA_MODEL.md](DATA_MODEL.md).

Three servers, one engine:

**Table API-1: the surfaces**

| Surface | Code | Listens on | Who calls it | Auth |
|---|---|---|---|---|
| The local page | `serve.Handler` | `http://127.0.0.1:8765`, plus `--also-on` | the page `serve` hands out | `X-Wastatus-Token`, a per process secret |
| The renderer API | `hosted.Handler`, under `/api/v1` | port 8790, behind the tunnel | the extension | `Authorization: Bearer`, a popup token or a grant |
| The hosted site | `portal.SiteHandler` | the same port as the renderer | the site's own pages | the session cookie, the value derived from it, and `Origin` |

`SiteHandler` inherits both of the others, so on the hosted site `/api/v1/*` is the
renderer's and every other `/api/*` is the local page's routes run against the
signed-in person's own workspace.

Every error, on every surface, is JSON: `{"error": "words for the person"}`, plus any
extra fields named below. Messages never carry a path on the server
(`serve.plain_error` replaces one with "a file").

## 1. The local page

`wastatus serve`. Standard library `ThreadingHTTPServer`, HTTP/1.1 with keep-alive,
120 second socket timeout. One person, one machine. D-020, D-042, D-044.

### The rules every request meets

1. **Host.** `Host` must name an address (`127.0.0.1`, `[::1]`, a tailnet address) or
   `localhost`, never a hostname. Anything else is `403 open this page by its address`,
   the page itself included, and a POST so refused closes the connection with its
   body unread. This is what keeps DNS rebinding from reading the token out of `/`.
2. **Token.** Every `/api/` call carries `X-Wastatus-Token: <token>`. The token is
   `secrets.token_urlsafe(24)`, made at start and written into the served page. The
   four media routes (`/api/frame`, `/api/clip`, `/api/sticker`, `/api/gif`) also
   take it as `?t=`, because an `<img>` or `<video>` cannot send a header. A wrong
   or missing token is `403 bad or missing token`.
3. **Origin.** When the browser sends `Origin`, it must be `http://<Host>`. Chrome
   sends it on every same origin POST, so every write is held to it.
4. **No CORS.** `OPTIONS` is always `403` with no CORS headers, so a cross origin
   caller can never send the custom header.
5. **Bodies.** A POST body is JSON, at most 12,000,000 bytes (`MAX_BODY_BYTES`, one
   animated sticker as base64). It is read before the token check, so a refusal
   never leaves it in the socket (D-042). Over the cap: drained up to the cap, `413`,
   connection closed. A `Content-Length` that is not digits: `413`, nothing read,
   connection closed. A body that is not JSON is treated as `{}`.
6. **Words.** Every line of card text is cut to 1,024 characters (`CAPTION_MAX`), a
   link to 2,048 (`URL_MAX`). A clip is named by its stem, which must match
   `^[A-Za-z0-9_-]{1,120}$` (`SAFE_STEM`) or the answer is `400 bad clip name`.
7. **Sending.** `POST /api/post` sends a Status **only** when the body says
   `"send": true`. Anything else, an absent field included, loads the composer and
   stops there for the owner to press Send. D-020, D-071.

**Table API-2: local page, pages and reads (GET)**

| Path | Query | Answers | Errors |
|---|---|---|---|
| `/`, `/index.html` | | the page, with the token in it. The only call that needs no token | 403 Host |
| `/app.css`, `/app.js`, `/favicon.svg`, `/favicon.ico` | | static files | 404 |
| `/api/state` | `fresh=1` skips the 8 s WhatsApp cache | `ffmpeg`, `provider`, `whatsapp {ready, detail, port, can_launch}`, `out`, `host`, `cdp_port`, `max_duration`, `fills`, `stickers`, `bands {top, bottom}`, `keep_last`, `busy`, `also_on`, `gifs` (credit), `clips` (newest 12), `local` (the caller is on loopback) | 403 |
| `/api/task` | `id` | a task: `id`, `kind` (`render`, `post`, `prepare`), `status` (`running`, `done`, `failed`, `cancelled`), `stage`, `message`, `error`, `elapsed`, `stages`, `result`, `can_stop` | 404 no such task |
| `/api/frame`, `/api/clip` | `stem`, `t`, `download=1` | the still (`image/png`) or the mp4, honouring one `Range`; `download=1` adds `Content-Disposition: attachment` | 400 stem, 404 not on disk, 416 |
| `/api/gifs` | `q`, `big=1` for larger thumbnails | `{credit, gifs: [...]}`. The results are remembered; a pick must name one of them | 404 switched off, 502 the provider failed |
| `/api/gif` | `id`, `t` | one result's thumbnail, fetched by this server (D-043) | 404, 502 |
| `/api/controls` | `fresh=1` | `{ok, checked, detail}`: whether WhatsApp's Status controls are where `post` expects. Never on the poll (T-026) | |
| `/api/stickers` | `q` | `{installed, hint, stickers: [...]}`, your own first | |
| `/api/sticker` | `id`, `w` (a thumbnail width), `t` | one sticker's image | 404 |

A clip in `clips` and in a render's `result` is `{stem, name, video, window, size_mb,
created, caption, has_frame, job, title, channel}`, where `job` is the clip's `.json`
sidecar ([DATA_MODEL.md](DATA_MODEL.md), Table DM-6).

**Table API-3: local page, actions (POST)**

| Path | Body | Answers | Errors |
|---|---|---|---|
| `/api/render` | `url`; `start`; `end` or `duration`; `video`, `wave` (default true), `fill` (`blur` or `black`), `framing`, `title`, `channel`, `footer`, `eyebrow`, `topline`, `stickers` (placed decals), `follow_up` | `{id}` of a `render` task | 400 a bad window, link or background; 409 a render is already running |
| `/api/post` | `stem`, `follow_up`, `send` | `{id}` of a `post` task when `send` is true, a `prepare` task otherwise. Result: `{seconds, follow_up, sent, port}`, and `follow_up_error` when the second text failed after the video went | 400, 404 no such clip, 409 WhatsApp is being driven, or still being checked after 30 s |
| `/api/caption` | `stem`, `caption` | `{caption}`, rewritten in `.caption.txt` with no render (D-021) | 400 over 1,024, 404 |
| `/api/cancel` | `id` | `{id, stopping: true}`. Renders only; a post cannot be stopped (D-025) | 404, 409 |
| `/api/clip/delete` | `stem` | `{deleted, files, mb}`: the mp4 and every sidecar | 400, 404, 409 while posting, 500 |
| `/api/preview` | `stem`, `title`, `channel`, `footer`, `eyebrow`, `topline`, `fill`, `framing` | `image/jpeg`, the clip's picture with these words, Pillow only (T-036). Headers: `X-Moving-Band: top,bottom` (fractions of the height that move), `X-Dropped-Toplines: n` | 400, 404 made before previews existed, 500 |
| `/api/text` | `text` | `image/png`, one placed line | 400 nothing to draw, 500 |
| `/api/words` | `url` | `{title, channel}`, one yt-dlp probe on the request's own thread (D-064) | 400, 502 |
| `/api/gif/pick` | `id` from the last search | the saved sticker, ready to place | 400, 404 no longer on offer, 502 |
| `/api/gif/provider` | `provider` | the new credit. For the life of the process; `.env` is never written | 400, 404 off |
| `/api/sticker` | `name`, `data` (base64 or a `data:` address) | the saved sticker | 400 |
| `/api/sticker/delete` | `id` (`mine:` or `gif:`) | `{deleted: true}`. The OpenMoji library is never touched | 400, 404 |
| `/api/browser` | | `{binary, port, profile}`, or `{..., adopted: true}` when a browser on the posting profile was already running | 409 already open, 503 cannot start one |

Unknown paths are `404 no such endpoint`.

## 2. The renderer API, `/api/v1`

`hosted.Handler`. What the extension uploads to and collects from. D-081, D-082.

### Auth

- **A popup token**: `Authorization: Bearer <token>`, made with
  `wastatus hosted token add NAME`. Only its SHA-256 is kept, in `tokens.json`, which
  is read again whenever it changes. A broken file refuses everybody. Good for every
  resource below; the owner of what it makes is the token's hash.
- **An upload grant** from the hosted site (`POST /api/grant`): the same header,
  good for `/uploads` and nothing else, 15 minutes, renewed on use so a slow upload
  is never cut off. Its uploads belong to `p:<person id>` and count against that
  person's day (`429` when they would pass it).
- **A clip grant** reaches only `GET /api/v1/clip?stem=` on the hosted site, for the
  one stem it names.
- `GET` and `HEAD /health` need nothing.

Somebody else's upload or job is answered exactly as a missing one: `404`. Ids match
`^[A-Za-z0-9_-]{16,40}$` or the route is `404`. No CORS headers on any of it, so a web
page holding a token still cannot read a response.

### Bodies and refusals

JSON bodies are at most 64,000 bytes, a chunk at most 1,048,576 (`CHUNK_MAX`). A body
needs a `Content-Length` made of digits (`411` otherwise). A body over its limit is
`413` and is not read; whenever a refusal leaves a body unread the answer carries
`Connection: close`. Extra fields on a refusal ride beside `error`: `received`,
`claimed`, `job`, `state`. A full queue answers `503` with `Retry-After: 60`.

**Table API-4: renderer resources**

| Method and path | Request | Answers | Errors |
|---|---|---|---|
| `GET`, `HEAD /health` | | `{ok, version: 1, queued, rendering, workers}` | |
| `GET /me` | token only | `{name, version, chunk, max_duration, limits: {audio, video, artwork}}` | 401 |
| `POST /uploads` | `{kind: audio, video or artwork, size}` | `201 {id, kind, size, received: 0, chunk}` | 400; 413 over 16 MB audio, 64 MB video, 4 MB artwork; 429 a grant's day is used; 507 under 1 GB free |
| `GET`, `HEAD /uploads/{id}` | | `{id, kind, size, received, chunk}` | 404 |
| `PUT /uploads/{id}` | raw bytes; `Content-Range: bytes first-last/total` | `{id, received, size}` | 400 range or length wrong; 409 `{received}` a chunk is missing before this one; 409 `{received, claimed: true}` already in a job; 413 |
| `DELETE /uploads/{id}` | | `{deleted: id}`; a grant's unsent bytes are given back | 404, 409 in a job |
| `POST /jobs` | `video_id`, `title`, `channel`, `duration`, `start`, `end`, `mode` (`card` or `video`), `fill`, `wave`, `audio`, `video` (video mode) or `artwork` (card mode, required), optional `artist`, `title_override`, `channel_override` | `202`, the job | 400; 404 an upload; 409 `{job}` one of yours is active; 409 `{received}` an upload is not finished; 503 |
| `GET /jobs` | | `{jobs: [...]}`, yours, oldest first | |
| `GET`, `HEAD /jobs/{id}` | | `{id, state, stage, message, error, position, title, caption, size, video_id, start, end, mode, created, finished}`; `state` is `queued`, `rendering`, `done`, `failed` or `cancelled`; times are ISO 8601 UTC | 404 |
| `GET`, `HEAD /jobs/{id}/clip` | `Range` optional | the mp4, `200` or `206`, `Content-Disposition: attachment` | 409 `{state}` not ready, 416 |
| `DELETE /jobs/{id}` | | `{id, state}`: a queued job is cancelled, a rendering one stopped, a finished one deleted with its clip | 404 |
| `GET /clip?stem=` | clip grant; `Range` optional | the mp4 from the person's own folder. Hosted site only | 400, 401, 404 |

**Uploads are idempotent by offset.** A chunk the server already holds is
acknowledged with the current `received`; an overlap keeps only the new tail; a chunk
that starts past `received` is `409` carrying `received`, so the client rewinds to it
and carries on. The extension reads `received` off a `200` or a `409` alike, and treats
`claimed: true` as a failure, never as done. One active job per owner, eight waiting
across everybody. An upload idle for 30 minutes and a finished job an hour old are
swept by the janitor.

## 3. The hosted site

`portal.SiteHandler`. Every name, domain and key comes from the environment
(`WASTATUS_PUBLIC_URL`, `WASTATUS_EXTENSION_ID`, and the rest in `.env.example`), so
nothing here names the deployment. D-087 to D-093, D-095, D-100.

### Auth

- **Session.** Cookie `snipshare_session`: `HttpOnly`, `SameSite=Lax`, `Path=/`,
  `Max-Age` 30 days, `Secure` unless the site is plain `http` on a non loopback
  address. A random 32 byte token, stored as its SHA-256. Ended at once by a
  decline or a suspension.
- **The page's value.** `csrf_for(session)`: an HMAC-SHA256 of the session, 40 hex
  characters, written into the page and sent back as `X-Wastatus-Token` (or `t=` on
  the media routes). A page from before a sign out cannot act.
- **Origin.** Must equal the origin of `WASTATUS_PUBLIC_URL`. Required on every
  POST; on a GET it is checked only when the browser sends one.
- **Open calls** (sign up, sign in, sign out) carry `X-SnipShare: 1`, which a cross
  site form cannot set, and the site's `Origin`, or they are `403 that request did not
  come from this site`.
- **Order.** The session is checked before a body is read, so nobody signed out can
  make the process read 12 MB. A refused call with a body closes the connection.
- **Never on this site** (`NOT_HERE`): `POST /api/post` and `POST /api/browser` are
  `404 not offered on this server`. There is no WhatsApp here to drive; the
  extension loads the composer in the person's own browser.
- **Smuggling.** A GET or HEAD carrying a body is `400` with the connection closed. A
  POST, PUT or DELETE with `Transfer-Encoding` is `411` with the connection closed.
- **Headers on every answer:** `X-Content-Type-Options: nosniff`, `X-Frame-Options:
  DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, a Content Security
  Policy on pages, and HSTS when the site is `https`.

**Table API-5: hosted site, pages**

| Path | Answers |
|---|---|
| `/`, `/install`, `/privacy`, `/terms`, `/signup`, `/signin` | public pages; `HEAD` answers 200 |
| `/app` | the tool page with the person's value in it; `303` to `/signin?next=/app` when signed out |
| `/account`, `/admin` | the account and admin pages; signed out `303` to sign in, `/admin` for a non admin `303` to `/app` |
| `/site.css`, `/site.js`, `/theme.js`, `/nav.js`, `/nav.css`, `/hosted.js`, `/hosted.css`, `/account.js`, `/admin.js`, `/mark.svg` | assets |
| `/download/snipshare-extension.zip` | the extension, from `/data/extension`, with ranges |
| anything else | the 404 page |

**Table API-6: hosted site, open calls (POST, `X-SnipShare: 1`)**

| Path | Body | Answers | Errors |
|---|---|---|---|
| `/api/signup` | `turnstile`, `credential` (a Google ID token) or `email`, `name`, `use`, `heard`, `chrome` | Google and already approved: the session cookie and `{status: approved, next: /app}`. Google otherwise: `{status, new}`. A typed address: always `{status: pending, new: true}`, whatever that address's standing. The owner is told of a new request only | 400 not an email, no name, too long; 403 Turnstile; 429 over 5 an hour per address; 503 Google unreachable |
| `/api/session` | `credential` | `{status: unknown, email, name}`, `{status}` when not approved, or the cookie and `{status: approved, next: /app}` | 400, 429 over 30 an hour per address, 503 |
| `/api/signout` | | `{signed_out: true}` and a cleared cookie. When it was the person's last session, their grants end too | |

`GET /api/me` needs nothing: `{signed_in: false}`, or `{signed_in: true, email, name,
admin}`.

**Table API-7: hosted site, account and admin calls**

All need the session and the page's value; the POSTs need `Origin`. A missing session
is `401 sign in again`, a wrong value or origin `403 reload the page and try again`,
an admin call from anyone else `403 that is for the admin`. A refusal the code
expects (`AccessError`) is `400` with its words. Bodies are at most 64,000 bytes, a
feedback body 12,000,000.

| Method and path | Body or query | Answers | Errors besides those above |
|---|---|---|---|
| `POST /api/grant` | `{purpose: upload, window: {url, start, end or duration}}` | `{grant, server, expires_in: 900, video_id, start, end}`, the window resolved exactly as the render will resolve it | 400 the day's clips are made, the hour is full, not a YouTube link; 409 a render of yours is running; 429 over 120 an hour |
| `POST /api/grant` | `{purpose: clip, stem}` | `{grant, server, expires_in: 900}`, good for that one clip | 404 no such clip |
| `POST /api/report` | `source` (`capture`, `load`, `page`, `words`), `phase`, `code`, `detail`, `versions` | `{recorded: true}`, or `{recorded: false}` past 30 an hour | 400 unknown source |
| `POST /api/feedback` | `kind` (`idea`, `problem`, `question`, `other`), `subject` (1 to 120), `message` (3 to 3,000), `name`, `attachments: [{data}]` (at most 3, each at most 4 MB, re-encoded as JPEG), `code`, `versions` | `{sent: true, mailed}`; kept as a report whether or not the mail went | 400, 413, 429 over 5 an hour |
| `GET /api/account` | | `{profile, sessions, usage, gifs, kept: 10, history_days: 90, contact}` | |
| `GET /api/account/history` | | `{days: [14 x {day, clips, failures, upload_bytes}], clips: [{at, video_id, title, channel, mode, start, end, stem, ok, seconds, error, kept}], usage}` | |
| `POST /api/account/profile` | `{name}` | the person | 400 empty or over 120 |
| `POST /api/account/sessions/end` | `{id}` or `{others: true}` | `{ended, sessions}` | 400 the current one (use Sign out) |
| `POST /api/account/delete` | `{confirm: <own email>}` | `{deleted: true}`, cookie cleared; a running render is stopped first | 400 not confirmed, or an admin |
| `POST /api/gifkey` | `{provider: giphy or klipy, key}`, checked with one search before it is kept | the GIF overview: `{keys: {provider: {ends, added}}, source, credit}` | 400, 429 over 10 an hour |
| `POST /api/gifkey/delete` | `{provider}` | the GIF overview | 400 |
| `POST /api/gifkey/source` | `{source: giphy, klipy or both}` | the GIF overview | 400 |
| `GET /api/admin` | `from`, `to`: UTC days, inclusive, today when absent | `{range, totals, people, usage, reports, renderer, disk_free_gb, notifications, clips_per_day, site}` | 400 a range over a year |
| `POST /api/admin/decide` | `{email, status: approved, declined or suspended}` | the person | 400, an admin cannot be refused |
| `POST /api/admin/add` | `{email, name}` | the person, approved | 400 |
| `POST /api/admin/forget` | `{email}` | `{forgotten: true}`, files included | 400 nobody, or an admin |

`usage` is `{clips, failures, upload_bytes, render_seconds, clips_limit,
upload_limit}`. A session in `sessions` is `{id, created, last_seen, agent, current}`,
where `id` is a 16 character name that is not the session's hash.

### The tool page's routes, hosted

Every other `/api/*` is Table API-2 and API-3, answered from the person's own
`Workspace` (`users/<id>/`). The differences:

**Table API-8: where the hosted page differs from the local one**

| Route | On the hosted site |
|---|---|
| `GET /api/state` | adds `hosted: true`, `rendering` (the id of a render the page lost track of), `me {email, name, admin}`, `quota` (the usage object), `extension {id, min_version}`; `whatsapp.ready` is always false |
| `POST /api/render` | also needs `captured: {video_id, duration, title, channel, artist, audio, video or artwork}`, the upload ids the extension sent. The video must match the link. 429 over 30 an hour per person, or the day's clips, the hour's cap or the disk; 409 one of yours is running |
| `POST /api/words` | `{url, title, channel}`: the words the extension read, cleaned as the card cleans them. Nothing asks YouTube |
| `POST /api/gif/provider` | `{provider: giphy, klipy or both}`, kept as the person's choice |
| `POST /api/sticker` | at most 60 of your own; the bytes count against the day's upload allowance (429) |
| `GET /api/controls` | always `{ok: true, checked: false}` |
| `POST /api/post`, `POST /api/browser` | 404 `not offered on this server` (`NOT_HERE`) |

**Table API-9: rate limits**

| What | Limit | Kept by | Over it |
|---|---|---|---|
| Sign up | 5 an hour per address | `signin.Limiter`, in memory | 429, and the owner is alerted |
| Sign in | 30 an hour per address | the same | 429 |
| Grants | 120 an hour per person | the same | 429 |
| Renders asked for | 30 an hour per person | the same | 429 |
| Failure reports | 30 an hour per person | the same | 200 `{recorded: false}` |
| GIF keys | 10 an hour per person | the same | 429 |
| Feedback | 5 an hour per person | the same | 429 |
| Clips made | 10 a day per person (`WASTATUS_CLIPS_PER_DAY`) | `usage` table | 400 at the grant, 429 at the render |
| Upload bytes | 500 MB a day per person (`WASTATUS_UPLOAD_MB_PER_DAY`), stickers included | `usage` table | 429 |
| Renders | 60 an hour across everybody (`WASTATUS_RENDERS_PER_HOUR`) | in memory | 400 at the grant, 429 at the render |
| Renders at once | one per person, `WASTATUS_HOSTED_WORKERS` slots across everybody, shared with popup jobs | `Renderer.slots` | 409, or waits for a slot |
| Waiting popup jobs | 8 | `QUEUE_MAX` | 503, `Retry-After: 60` |
| Captures, loads | 20 and 10 an hour per browser | the extension, `chrome.storage.local` `pace` | the extension refuses, code `paced` |

"Per address" is the peer address, or `CF-Connecting-IP` when `WASTATUS_TRUST_PROXY` is
on. Days are UTC. A restart forgets the in memory limits.

## 4. The extension and the site

The site talks to the extension's service worker over a port:
`chrome.runtime.connect(EXTENSION_ID)` in `hosted.js`, answered by
`chrome.runtime.onConnectExternal` in `src/sw.js`. Chrome offers that only to pages
the manifest's `externally_connectable.matches` lists: loopback in the repository,
the one site in a build (`scripts/build_extension.py`). The worker checks again that
the sender's origin is exactly `CONFIG.site`, and disconnects anyone else.

One port carries one command. The worker answers with any number of
`{progress: {message, progress}}`, then exactly one `{done: {...}}` or
`{error: {message, code, phase}}`. `{cmd: "stop"}` on the same port, or the page
closing the port, stops it. The worker never holds a session: a grant comes with each
capture or load, and is used only against the page's own origin (a `server` naming
another origin is refused).

**Table API-10: commands the extension takes from the site**

| `cmd` | Sent with | `done` | Notes |
|---|---|---|---|
| `hello` | | `{version, whatsapp}`, `whatsapp` being `none`, `open`, `signed-in` or `unknown` | the page waits 4 s, three tries. It is the status check: the page's chip and its version gate (`min_version` 2.0.0) come from it |
| `capture` | `videoId`, `start`, `end`, `mode`, `server`, `grant` (upload) | `{video_id, title, channel, duration, audio, video or artwork}`: upload ids for `POST /api/render`'s `captured` | opens the video muted in a tab beside the page when none shows it, reads the window, uploads to `/api/v1/uploads` with the grant. One at a time in the browser, shared with the popup |
| `load` | `url` (must be `<origin>/api/v1/clip?stem=`), `grant` (clip), `caption` (cut to 1,024), `name` | `{loaded: true}` | fetches the clip with ranges, fills the WhatsApp Web composer, never presses Send. One at a time |
| `words` | `url` or `videoId` | `{title, channel}` from YouTube's oEmbed | the page then posts them to `/api/words`; 20 s timeout |
| `stop` | | | aborts the command on this port |

Error codes the page may see: `invalid`, `busy`, `paced`, `thumbnail`, `open`,
`wrong-video`, `live`, `window`, `read`, `auth`, `upload-refused`, `network`, `gone`,
`size`, `private`, `words`, `stopped`, `unknown`, `failed`, and WhatsApp's own words
under phase `whatsapp`. The page itself adds `no-extension`, `timeout`, `silent` (five
minutes without a message during a capture or load) and `disconnected`. Every failure
but a stop is sent to `POST /api/report`: a phase, a code and versions, never the
video.

## Examples

The local page: read the token out of the page, then start a render and poll it.

```bash
TOKEN=$(curl -s http://127.0.0.1:8765/ | grep -o 'data-token="[^"]*"' | cut -d'"' -f2)
curl -s -X POST http://127.0.0.1:8765/api/render \
  -H "X-Wastatus-Token: $TOKEN" -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=aaaaaaaaaaa","start":"1:10","end":"1:25"}'
# {"id": "3f2a9c0d1e4b"}
curl -s "http://127.0.0.1:8765/api/task?id=3f2a9c0d1e4b" -H "X-Wastatus-Token: $TOKEN"
```

The token is the `data-token` attribute on `<body>` in `wastatus/web/index.html`.

Load a clip into the composer without sending it, then send one on purpose:

```bash
curl -s -X POST http://127.0.0.1:8765/api/post -H "X-Wastatus-Token: $TOKEN" \
  -H 'Content-Type: application/json' -d '{"stem":"20261025_song-name_70-85"}'
curl -s -X POST http://127.0.0.1:8765/api/post -H "X-Wastatus-Token: $TOKEN" \
  -H 'Content-Type: application/json' -d '{"stem":"20261025_song-name_70-85","send":true}'
```

The renderer: make an upload, send it in one chunk, and resume after a refusal.

```bash
API=https://snipshare.example.com/api/v1
curl -s -X POST "$API/uploads" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"kind":"audio","size":1500000}'
# 201 {"id": "Q2xpcF9hdWRpb18wMDAwMDE", "kind": "audio", "size": 1500000, "received": 0, "chunk": 1048576}
curl -s -X PUT "$API/uploads/Q2xpcF9hdWRpb18wMDAwMDE" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Range: bytes 0-1048575/1500000' --data-binary @part1.bin
# {"id": "...", "received": 1048576, "size": 1500000}
# A chunk sent too far ahead is refused with what the server holds:
# 409 {"error": "a chunk is missing before this one", "received": 1048576}
```

Collect a finished clip in pieces:

```bash
curl -s "$API/jobs/$JOB" -H "Authorization: Bearer $TOKEN"
curl -s -o clip.mp4 -H "Authorization: Bearer $TOKEN" -H 'Range: bytes=0-' "$API/jobs/$JOB/clip"
```

The hosted site: ask for an upload grant as the page does. `$SESSION` is the cookie and
`$PAGE_VALUE` the value the tool page was handed for it.

```bash
curl -s -X POST https://snipshare.example.com/api/grant \
  -H "Cookie: snipshare_session=$SESSION" -H "X-Wastatus-Token: $PAGE_VALUE" \
  -H 'Origin: https://snipshare.example.com' -H 'Content-Type: application/json' \
  -d '{"purpose":"upload","window":{"url":"https://youtu.be/aaaaaaaaaaa","start":"0:20","end":"0:50"}}'
# {"grant": "...", "server": "https://snipshare.example.com", "expires_in": 900,
#  "video_id": "aaaaaaaaaaa", "start": 20.0, "end": 50.0}
```
