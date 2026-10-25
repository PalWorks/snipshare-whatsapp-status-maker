# Architecture

A command line tool and a local page on the owner's machine, and a hosted renderer
and site for the browser extension. Locally there is no database and no state that
survives a run apart from the output files and the PO token provider it starts; the
hosted site keeps one SQLite database of people, sessions and counts
([DATA_MODEL.md](DATA_MODEL.md)). Every endpoint is in [API.md](API.md). Updated
**2026-10-25T15:11:42+05:30** for the audit before publication (D-100).

Three front ends, one engine. `cli` parses arguments and prints; `serve` answers a
browser; `hosted` answers the extension; all three call `pipeline.produce`, which is
the only thing that knows how a clip gets made. Duplicating any of that into a front
end would be the mistake this split exists to prevent.

**The hosted path asks YouTube nothing.** The extension captures the window in the
viewer's own browser and uploads it; `pipeline.Captured` hands those uploads to
`produce`, which then skips `fetch.probe`, `fetch.download_section` and
`fetch.download_thumbnail` and cuts the window with `capture.section` in the
`download` stage instead. Everything after that is the same code the local tool runs.
See [docs/extension.md](docs/extension.md) and the section below.

About 9,800 lines of Python across twenty three modules, 5,400 lines of page (html,
css and vanilla js, no build step), 2,400 lines of extension (the same, no build
step), and 10,600 lines of tests, orchestrating two external binaries: `yt-dlp` and
`ffmpeg`. Counted on 2026-10-24.

## Pipeline

```
YouTube URL + start + end
        |
        v
[1] fetch.probe                    yt-dlp -J
        |                          id, title, channel, duration
        v
[2] translit.clean_title           Tamil to Latin, noise stripped,
        |                          repeated segments collapsed
        v
[3] potoken.ensure_running         local node server on :4416
        |
        v
[4] fetch.download_section         yt-dlp, client ladder, only the
        |                          requested range, ~1.2 MB / 15s
        |
        +--- card mode ------------+--- video mode ------------+
        |                          |                           |
        v                          v                           v
[5] fetch.download_thumbnail   compose.build_card         compose.build_overlay
    i.ytimg.com, no proxy      1620x2880 PNG              1080x1920 RGBA PNG
        |                          |                           |
        v                          v                           v
[6] render.render_card_clip                        render.render_video_clip
    zoompan + showwaves + fades                    blur fill + overlay + fades
        |                                                      |
        +---------------------+--------------------------------+
                              v
[7] out/YYYYMMDD_song-slug_start-end[_video].mp4
    out/<...>.caption.txt      the caption to post with the clip
    out/<...>.status2.txt      text for the --follow-up status, only with that flag
        |
        v
[8] render.extract_frame       optional --frame still, full resolution
    retention.prune            keeps the newest 20 clips and their sidecars
    runlog.Run.finish          appends one record to logs/runs.jsonl
```

Every stage is wrapped in a `runlog` timer, so a failure records which stage was
reached and how long the earlier ones took. The full subprocess output of a failed
`yt-dlp` or `ffmpeg` goes to the text log; the user sees only the tail.

**Editing the words does not run this pipeline at all.** `App.preview_jpeg` calls
the same `compose.build_card` or `compose.build_overlay` the render calls, over a
picture kept beside the clip, and answers with a JPEG in well under a second. See
[DECISIONS.md](DECISIONS.md) D-048.

**Posting is a run too.** A load or a send from the page opens its own `runlog.Run`
and records the port and browser it went through, so "when did that go out, and
through what" is answerable for the route actually used rather than only for the
command line one.

**Each process writes a stamp before its first run**, `runlog.stamp`: python, yt-dlp,
ffmpeg and Chrome versions, the debug ports in play, the git revision and whether the
working tree is modified, and the **names** of the settings `.env` supplied. Six
months later that is the difference between a log line you can place and one you
cannot. Names, never values, so a key cannot arrive there by accident.

## Component boundaries

| Component | Owns | Does not touch |
|---|---|---|
| `cli` | argument shape, window validation, output naming, user facing text | no ffmpeg or yt-dlp knowledge |
| `fetch` | every conversation with YouTube | no rendering, no text layout |
| `potoken` | provider lifecycle | never called except from `fetch` |
| `pipeline` | the engine: validate a window, then produce the clip | no printing, no argument parsing, no posting |
| `serve` | the local page: routes, tasks, guards | no pipeline logic of its own |
| `compose` | all pixels that carry text, and where WhatsApp's own bands are | no ffmpeg, no network |
| `stickers` | the sticker library, and pasting one onto a canvas | no layout, no ffmpeg. Coordinates arrive as fractions and leave as pixels. `split` decides which of two mechanisms draws each one: a still is pasted here, an animated one is a looping input the renderer builds, see D-036 |
| `freetext` | one line of placed text: cleaning it, measuring it, and drawing it to a transparent picture, emoji included, which are pictures out of the sticker library rather than letters out of the font, see D-065 | knows nothing about the shelf, the page or the renderer. It is called by `stickers.paste` for the clip and by `serve` for the page, so both get the same line, see D-058 |
| `gifs` | GIF search, and the only thing here that talks to anybody but YouTube. Two providers normalised to one shape | off unless `.env` switches it on, and self contained enough to delete. Knows nothing about stickers, the page or the renderer, see D-043 |
| `post` | driving WhatsApp Web's composer over CDP, finding a debug browser, and starting one | only reached by `--post`, `--load` or the page, never on the produce path. **The only module whose correctness depends on somebody else's wording.** WhatsApp's labels live in three lists at the top of it and are matched on words, not on exact strings, see D-041 |
| `render` | filter graphs and encoder settings, and the one Pillow copy of a graph: `recompose`, so a background or a moved picture can be previewed without making the clip again | no text layout, no network. `recompose` lives beside the graph it imitates so the blur's sigma and darkening cannot drift from the ones ffmpeg is given, see D-059 |
| `proc` | starting yt-dlp and ffmpeg so they can be killed | knows nothing about what they are for. `fetch` and `render` are its only callers |
| `translit` | script conversion and title hygiene | pure functions, no io |
| `timecode` | timestamp parsing | pure functions, no io |
| `naming` | output filenames and collision avoidance | knows nothing about video |
| `retention` | pruning the output folder | only ever called after a successful write |
| `sheet` | the Google Sheet record | only ever called after WhatsApp **accepted** a Status, and it can never raise into a run |
| `runlog` | the text log and the per run json record | never raises, a log failure must not lose a clip |
| `env` | reading `.env` into the environment at startup, and naming which keys came from it | sets nothing that is already set, and never records a value: which settings were in play is worth logging, a key is not |
| `label` | the cached html tab whose title names this session's ports, profile and output folder | one file per page port, written before the browser opens and outliving the server, see T-037 |
| `capture` | checking an upload from the extension (one stream, an allowed codec, packets that cover the window without a hole) and cutting the window on its own timestamps | decodes nothing to check it, and is the only place a capture is cut, see D-080 |
| `hosted` | the renderer the extension talks to: tokens, chunked uploads, the job queue, its workers and janitor, serving the clip in ranges | no pipeline logic of its own, and no conversation with YouTube, see D-081 and D-082 |
| `src/` | capturing in the YouTube tab (`recorder.js`, `media.js`), the job from upload to download (`sw.js`), the popup, and loading WhatsApp's composer (`whatsapp.js`) | JavaScript, no build step. The fragment parser lives only here; the server receives clean files and checks them with ffprobe, see D-083 |

## The local page

`serve` is a `ThreadingHTTPServer` on loopback from the standard library. A render or
a post becomes a `Task` on a background thread; the page polls it. That thread is
also the handle a cancellation needs, which is what `proc` is for. Nothing is
persisted: the tasks die with the process, and the output folder is the only state.

The three files in `wastatus/web/` are the whole interface, and they are written
**mobile first**, see [DECISIONS.md](DECISIONS.md) D-029. `app.css` describes a
phone; a 600px query puts things back on shared rows and a 901px one restores the
two columns. Those two columns are **everything you answer, and the answer**: the
form, Stickers, Post it (which holds Make the clip) and Recent on the left, in the
order they are done, and nothing but the frame on the right. The left column is as
long as it likes and the right one is `position: sticky` under the top bar, whose
height the script measures into `--topbar` because that bar is sticky itself. The
frame is sized to the height left on the screen so that a stuck card always fits:
360px where the page has reached its full width at 1180, 300 below that, less on a
short screen. See D-067. The page footer is a phone element only: on a laptop the
health chip at the top of the screen answers the one question it carried, so it is
folded away from 901px, D-069. Every card down the column is spaced by the same
token from 600px up, D-070. On a phone both column
wrappers dissolve to `display: contents` so
every panel is a grid item in its own right and `order` alone decides the sequence,
which is how the sticker shelf stays under the frame it decorates rather than above
it. See D-057, and note that Make the clip carries `form="form"` because it now
lives outside the form it submits. `app.js` is vanilla and holds five pieces of state worth knowing about:

| State | Lives in | Why it is there |
|---|---|---|
| `atLaptop` | `data-where` on `<body>` | the server says whether the caller is on loopback, and CSS picks which post button is filled. Never sniffed from the user agent, because the tailnet address opened on the laptop would answer wrongly |
| the form | `localStorage["wastatus.form"]` | a phone reloads the tab when you switch to WhatsApp and back, and a pasted link should survive that |
| downloaded clips | `localStorage["wastatus.saved"]` | per device, so the Recent strip can say which ones this phone already has |
| which cards are open | `localStorage["wastatus.open"]` | folds you pressed. A fold the page did by itself after a render is deliberately not written here, see D-032 |
| the theme | `localStorage["wastatus.theme"]` | absent means follow the system, see D-031. Applied by a script in `<head>` so the page cannot flash the wrong palette |

**The Recent strip is where a clip is dropped, not just opened.** Each tile is a
`<div>` holding two buttons: one that loads the clip back into the form, and a cross
that deletes it. It is two buttons and not one because a `<button>` nested inside a
`<button>` is invalid and the parser silently unnests them, which would lay the cross
out beside the tile rather than on it. The cross asks twice before it acts and forgets
the question after four seconds, and which tile is asking is held in a variable rather
than in the DOM, because the strip repaints whenever the clip list changes. See D-055.

**One page is not served at all.** When `serve` starts the posting browser, it also
writes `label.py`'s session page into `~/.cache/wastatus` and hands it to Chrome as
the first URL, with the served page as the second. It is a file rather than a route
because it has to outlive the server: stop the tool and a served label becomes a
connection error, while a file still says what the session was. See D-050.

**And the served page goes into that same window.** `serve.show_page` puts it there:
on the command line when a browser is started here, and over `PUT /json/new` when one
was already running and never saw a command line. The default browser is the fallback,
not the route. See D-051.

## Table AR-3: HTTP surface

| Route | Method | Does |
|---|---|---|
| `/`, `/app.css`, `/app.js`, `/favicon.svg` | GET | the page itself. `/` is the only route that needs no token, because it is what delivers the token |
| `/api/state` | GET | health of ffmpeg, the provider and the posting browser, the machine's own name, whether the caller is on loopback, the backgrounds the renderer will draw, plus the recent clips. `?fresh=1` skips the 8 second cache on the browser probe |
| `/api/render` | POST | starts a render, returns a task id. The body carries the window, the words, the look, the background, where the picture goes and everything placed on the frame |
| `/api/task?id=` | GET | one task's stage, message, elapsed and result |
| `/api/frame`, `/api/clip` | GET | the still and the mp4. Byte range aware, and the only routes that accept the token as a `t=` query parameter, because an `<img>` cannot send a header. `&download=1` adds a `Content-Disposition`, which is how a phone takes the clip to post in the real app |
| `/api/caption` | POST | rewrites a clip's `.caption.txt`. No render involved, see D-021 |
| `/api/post` | POST | loads the composer, and sends only if the body says `send: true`, see D-020 |
| `/api/browser` | POST | starts the posting browser when none is running, see D-022 |
| `/api/gifs?q=` | GET | search the configured GIF provider. 404 when the feature is off. The results are remembered on the App, which is what makes a pick safe |
| `/api/gif?id=` | GET | one result's thumbnail, fetched by this server. Takes the token as `t=`, because an `<img>` cannot send a header |
| `/api/gif/pick` | POST | download the chosen result and keep it. The body names an **id from a search this server made**, never a url, see D-043 |
| `/api/gif/provider` | POST | switch which service the search asks, for the life of this process. `.env` stays the default and is never written to, and the last search's results are forgotten with the provider that produced them |
| `/api/preview` | POST | the clip's own picture redrawn with the words currently in the boxes, and with the background and picture placement currently chosen, as a JPEG, by Pillow alone. A POST because a title in an address ends up in every log between here and a phone. Answers with `X-Moving-Band`, the rows of the frame that move, so the page can cut the still open and let the clip play through it, see T-036 |
| `/api/words` | POST | the title and second line the video answers for itself, cleaned exactly as the card would clean them, so the boxes can be corrected before the clip rather than after it. One yt-dlp probe on the request's own thread, 45 seconds' patience rather than a render's five minutes. See D-064 |
| `/api/text` | POST | one line of free text drawn to a transparent PNG, which is what the page places on the frame. A POST for the same reason as the preview, see D-058 |
| `/api/controls` | GET | whether WhatsApp's Status controls are still where `post` expects them. Opens a menu in the posting browser, so it runs once per server run and never on the poll, see T-026 |
| `/api/stickers?q=` | GET | search the library, uploads first |
| `/api/sticker?id=` | GET | one sticker's image. Token in the query, like the other media |
| `/api/sticker` | POST | store an uploaded image as a sticker |
| `/api/sticker/delete` | POST | remove an uploaded one. The library itself is never touched |
| `/api/sticker?id=&w=` | GET | a scaled copy, made once and cached on disk. Only the widths in `stickers.THUMB_WIDTHS` |
| `/api/cancel` | POST | stops a running render. A post is refused with a 409, see D-025 |
| `/api/clip/delete` | POST | deletes a clip and every sidecar that belongs with it. Reached from the Delete button and from the cross on a Recent tile, D-055 |

**Every POST reads its body before it decides whether the caller holds the token**,
up to `MAX_BODY_BYTES`. The server speaks HTTP/1.1 with keep-alive, so answering a
403 with the body still in the socket leaves the next request line to be parsed out
of the middle of it. See D-042, and `TestKeepAlive` in `tests/test_serve.py`. Two
refusals come first and close the connection instead of reading anything: a `Host`
that is not an address (DNS rebinding), and a `Content-Length` that is not digits
(D-100). The hosted site goes further and checks the session before reading at all.

Three things in there are load bearing and easy to break:

- **Ranges.** `_send_media` answers `Range` with a 206 and a `Content-Range`.
  Without it the video element has no way to ask for a later part of the file, and
  the seek slider silently does nothing. `tests/test_seeking` pins it.
- **Single flight.** `App.running("post", "prepare")` refuses a second posting
  request with a 409. The composer sends every file it holds, so two overlapping
  requests are how one command posts two Statuses.
- **Quiet logging.** Successful polls are not logged, and any `t=` in a logged URL
  is redacted, so the token never reaches a file that outlives the process.
- **The origin check.** A write is refused unless `Origin` matches the address the
  request was addressed to, and the `Host` header is trusted only when it names an
  address rather than a name, which is what keeps DNS rebinding out.
- **Where the request came from.** `Handler._local` reports whether the peer address
  is loopback, and the page uses that to decide which action is the primary one. It
  is a property of the connection, not of the user agent, because the page can be
  opened on the laptop at either address. See D-026.

The server binds loopback always, and `--also-on` adds a second address on the same
port. Two sockets rather than one wider bind, so a request's own address still says
which device it came from. **The second socket lasts as long as the process and no
longer**: nothing persists the flag, so every start decides again. `state()` reports
it as `also_on`, which is the only place the running server admits to having one.

Each clip is written with a `{stem}.json` sidecar holding the job that made it: the
link, the window, the mode, the wording and any stickers placed on it. That is what lets the page put a clip
from the Recent strip back into the form and re-make it. It is pruned with its clip
by `retention.SIDECAR_SUFFIXES`.

The seam that matters: **all text is drawn by Pillow, never by ffmpeg.** The
development machine's ffmpeg is built without freetype or libass, so `drawtext`
and `subtitles` do not exist in it. Routing text through Pillow removes the
dependency on how any given ffmpeg was compiled, which is what makes the same
code work on Linux and macOS. See [DECISIONS.md](DECISIONS.md).

## Render specification

## Table AR-1: Output format

| Property | Value |
|---|---|
| Resolution | 1080x1920, square pixels |
| Frame rate | 30 |
| Video codec | H.264 high profile level 4.0, yuv420p |
| Rate control | crf 23, preset faster, and a maxrate derived from the duration so the file stays inside a size WhatsApp will accept, see `render.video_maxrate` |
| Audio codec | AAC 128 kbps, 44.1 kHz stereo |
| Loudness | EBU R128 via `loudnorm`, I=-14 TP=-1.5 LRA=11 |
| Container | mp4 with `+faststart` |
| Typical size | 5 to 6 MB for 15 seconds |
| Length ceiling | 90 seconds, enforced in `pipeline.MAX_DURATION` |
| Size ceiling | about 10 MB by construction, under the 10 MiB line WhatsApp refuses at, silently |

Artwork arrives padded to 16:9 by whoever uploaded it. `compose.detect_bars`
finds those flat bands and they are cropped off before anything else happens, so
neither the card nor the blurred background carries them. The card is then as tall
as the trimmed artwork's aspect ratio asks for, anchored by its bottom edge so the
card and title stay a fixed pair, unless it was placed by hand, in which case
`compose.card_rect` scales that same panel and puts it where it was put. `render.source_picture` does the same job for
`--video`, sampling three frames through the same detector, and returns the size it
found as well, which is what `picture_rect` fits into the band.

**Neither mode lets its picture reach the words, until somebody puts it there.**
That is the fitted layout, which is still the default in both modes and is what
everything below describes. A picture that was **placed** by hand answers to the
placement instead and may reach anywhere at all, including off the frame: see D-061
for video mode's, D-062 for card mode's, and `compose.card_words_anchor` for the two
rows the words stop following a panel at. The shade that keeps text readable over a
picture, `compose._bottom_shade`, is what covers the overlap in both.

The card is anchored `CARD_GAP` above `CARD_TITLE_TOP` and so is safe by
construction. `--video` gets the same guarantee, and it is arithmetic rather than an
expression: `render.picture_rect`
fits the frames inside `ceiling..floor` and centres them no lower than the floor and
no higher than the ceiling, returning an exact rectangle that the filter graph is
handed as numbers. Neither end is a constant. `compose.video_picture_bottom` and
`video_picture_top` read them off the text, because a label sits above the title and
top text sits under WhatsApp's header, and the picture gives up the room for each
only when there is one to draw.

**Python owns that rectangle because Pillow needs it too.** The top text is anchored
to the picture's top edge, and a coordinate ffmpeg kept to itself could not be drawn
against. So the crop probe returns the size it found, one fit answers both the words
and the graph, and `tests/test_safe_zone.py` asserts the rectangle computed here is
the one ffmpeg paints. See D-054. Wide sources are already higher than that line and do
not move. A source too tall for the band is fitted to it and shows blurred fill down
its sides, rather than being cropped into shape. See D-049.

The card is composed at 1620x2880, which is 1.5 times the output. `zoompan`
downscales it to 1080x1920 while travelling from zoom 1.0 to 1.07 across the
clip, so the Ken Burns move never has to upscale and text stays crisp.

## The extension and the hosted renderer

```
YouTube tab (page world)              extension                       the SnipShare server
------------------------              ---------                       --------------------
player appends to MSE  -->  recorder.js copies each append
                            media.js files it as fragments,
                            by header and timestamp
popup "Make my clip"  -->  sw.js start()
                            recorder.js walk: pause, seek,
                            wait for our own record to cover
                            the window, restore the viewer
                            media.js pick(): one header and
                            the fragments over the window
                            bridge.js -> sw.js -> IndexedDB
                            sw.js upload: chunks with        --> hosted: uploads, 1 MiB max,
                            Content-Range, resuming                  idempotent by offset
                            sw.js POST /jobs                 --> queue -> worker thread
                                                                     pipeline.produce(captured)
                                                                     capture.section: trim on the
                                                                     media's own timestamps
                            sw.js poll, then download        <-- clip, with Range
                            with Range into IndexedDB
popup "Load into WhatsApp" --> whatsapp.js in the WhatsApp tab: catch the file input,
                               fill it, type the caption. Never Send.
```

**State lives where it survives.** The job is in `chrome.storage.local`; the
captured files and the clip are in IndexedDB; uploads and jobs on the server have
their own files and a `job.json`. Chrome stopping the extension's worker, the
popup closing, the connection dropping or the renderer restarting each leave a
state the next step can carry on from. D-082.

**Table AR-4: the hosted API**, all under `/api/v1`, all but `health` behind
`Authorization: Bearer <token>`. No CORS headers on any of it.

| Method and path | Does |
|---|---|
| `GET /health` | `{ok, version, queued, rendering, workers}` |
| `GET /me` | the token's name, and the limits the client should respect |
| `POST /uploads` | `{kind: audio, video or artwork, size}` makes an upload |
| `GET /uploads/{id}` | how much of it has arrived |
| `PUT /uploads/{id}` | one chunk, `Content-Range: bytes a-b/size`. A chunk already held is acknowledged; one past what is held is 409 with `received`; one for an upload already in a job is 409 with `received` and `claimed: true` |
| `DELETE /uploads/{id}` | drop it |
| `POST /jobs` | a clip from finished uploads: `video_id, title, channel, duration, start, end, mode, fill, audio, video` or `artwork` (card mode requires `artwork`), optional `title_override, channel_override` |
| `GET /jobs` | the caller's own jobs |
| `GET /jobs/{id}` | `state` (queued, rendering, done, failed, cancelled), `stage`, `position`, `error`, `size`, `caption` |
| `GET /jobs/{id}/clip` | the mp4, with byte ranges |
| `DELETE /jobs/{id}` | stop it, or delete a finished one |
| `HEAD` on the same paths | as `GET`, without the body |

`GET /api/v1/clip?stem=` is the hosted page's own addition: one finished clip of a
signed-in person's, for the extension to load into WhatsApp, behind a grant that
names that clip. A grant for uploads (below) reaches `/uploads` and nothing else.

## SnipShare: the page, hosted per person

```
browser, on the site                     the SnipShare server (portal.SiteHandler)
--------------------                     ------------------------------------------
/, /install, /privacy, /terms,   -->     public pages, `wastatus/pages/`, one layout
/signup, /signin (Google, Turnstile)     accounts: people, sessions (hashed), grants,
                                         usage per day; notify: mail and Chat to the owner
/app: index.html + hosted.js + app.js -> serve.Handler's routes, bound per request to
                                         the person's Workspace (serve.App in
                                         users/<id>/), their stickers and GIF key
  "Make the clip"
    POST /api/grant {window}       -->   checks limits, resolves the window, 15 min grant
    port to the extension: capture
      extension opens the video, reads it, uploads with the grant --> /api/v1/uploads
    POST /api/render {captured}    -->   claims the uploads, waits for a renderer slot,
                                         pipeline.produce(captured), counts the day
  "Load into WhatsApp"
    POST /api/grant {clip}, port: load  -> the extension fetches /api/v1/clip, fills
                                         the composer in the person's own WhatsApp Web
/admin + admin.js                  -->   people, decisions, usage, failure reports
                                         watch.Watch: alerts, the daily digest, backups
```

**One handler, two route tables.** `SiteHandler` inherits the renderer's handler and
the local page's, renderer first so its `_json` and `_send` serve both. A request to
`/api/v1/*` is the renderer's, authorised by a popup token or an upload grant;
any other `/api/*` is the local page's, authorised by the session cookie, the value
derived from it that the page sends in `X-Wastatus-Token`, and, on a change, the
site's `Origin`. What the server cannot do (post, start a browser) answers 404; the
GIF provider switch saves the person's own choice.

**Per person, per request.** The person's sticker folder and GIF key are context
variables, set when the request is authorised and reset when it ends; a render sets
them again on its own thread. The OpenMoji library is shared.

**Table AR-5: the hosted page's own calls**

| Method and path | Who | Does |
|---|---|---|
| `POST /api/signup` | anybody, from the site | a request: name, email or a Google credential, what for, how heard, Turnstile |
| `POST /api/session` | anybody, from the site | a Google credential in, a session out, or where the person stands |
| `POST /api/signout` | anybody, from the site | ends the session |
| `GET /api/me` | anybody | signed in or not, and as whom |
| `POST /api/grant` | a session | `{purpose: upload, window}` or `{purpose: clip, stem}` |
| `POST /api/report` | a session | a failure: source, phase, code, versions |
| `POST /api/gifkey`, `/api/gifkey/delete` | a session | `{provider, key}` to add or replace one service's key, `{provider}` to remove it |
| `POST /api/account/delete` | a session | everything about the person, typed confirmation |
| `GET /account` | a session | the account page, `pages/account.html` and `account.js` |
| `GET /api/account` | a session | profile, today's usage, the GIF keys' last four characters and the search choice |
| `GET /api/account/history` | a session | the last 14 days and every clip of the last 90, with whether each is still kept |
| `POST /api/account/profile` | a session | `{name}` |
| `POST /api/gifkey/source` | a session | `{source: giphy, klipy or both}`; the tool page's shelf switch, `/api/gif/provider`, sets the same choice |
| `POST /api/feedback` | a session | `{kind, subject, message}` required, `name`, `code`, `versions` and up to three `attachments` optional: mailed to the operator with the person as the reply-to |
| `POST /api/account/sessions/end` | a session | sign out one other browser, or every other |
| `GET /api/admin`, `POST /api/admin/decide`, `/add`, `/forget` | an admin's session | the admin page |

## External dependencies

## Table AR-2: Runtime dependencies

| Dependency | Version in use | Why |
|---|---|---|
| Python | 3.14.3 locally, 3.13 in the renderer's image | host language |
| ffmpeg | 8.0.1 locally, 7.1 in the renderer's image | all encoding and filtering |
| node | 22.19.0 | PO token provider, yt-dlp's JS challenge solver, and the extension's parser tests |
| yt-dlp | 2026.7.4 | metadata and media extraction |
| Pillow | 12.3.0 | every pixel that carries text |
| Unidecode | 1.4.0 | fallback romanisation for non Tamil scripts |
| aksharamukha | 2.3 | Tamil phonetic romanisation |
| bgutil-ytdlp-pot-provider | 1.3.1 | the yt-dlp plugin half of the token provider |
| pytest | 8 or newer, dev only | the offline test suite, `requirements-dev.txt` |

The provider's server half is not a pip package. It is cloned and built by
[scripts/setup_provider.sh](scripts/setup_provider.sh) into
`~/.local/share/wastatus/bgutil` on Linux or
`~/Library/Application Support/wastatus/bgutil` on macOS, and occupies about
209 MB once `node_modules` is installed.

## Failure model

Every stage fails loudly with a typed exception: `TimecodeError`, `FetchError`,
`RenderError`. `cli` converts these to a message and a non zero exit. There is
no partial output: the mp4 is only written when ffmpeg succeeds, and the work
directory is removed unless `--keep` is passed.

Two failures are deliberately soft, because neither should cost the user a clip:
the clipboard copy, and any inability to write a log.

Exit codes: `0` success, `1` a stage failed, `2` bad arguments or a window the
platform will not accept.

## Scaling considerations

The local tool: one user, one clip at a time, wall clock about 25 seconds.

The hosted renderer: one worker on three of the production host's four Ampere
cores, a queue of eight, one active clip per token. Measured there on 2026-10-24:
a 20 second card in about 40 seconds end to end, a 90 second 1080p video in about
three minutes, of which two are the engine's own render. More people means
`WASTATUS_HOSTED_WORKERS` and cores, not a different design: the server holds no
state a second worker would fight over beyond its own lock. Egress needs nothing,
because the server never talks to YouTube.
