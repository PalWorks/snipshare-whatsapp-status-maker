# Skills

Last updated **2026-10-25T15:15:55+05:30**.

What an agent can do in this repository, and with what: every command and flag,
every script, the HTTP interfaces at a glance, and the common workflows end to end.
Flags were read from `wastatus/cli.py`, `wastatus/serve.py`, `wastatus/hosted.py`
and each script's own parser, and checked against `--help`. Whether an action needs
the owner's say so is in [AGENTS.md](AGENTS.md); this file only says how.

Placeholders: `<VIDEO_ID>` is any YouTube id, `someone@example.com` any person,
`https://snipshare.example.com` the site, `<scratch>` a throwaway folder.

## Entry points

**Table SK-1: the three ways in**

| Command | What it is |
|---|---|
| `./wastatus.sh ARGS` | the wrapper: runs `.venv/bin/python -m wastatus ARGS` from any directory, with the project on `PYTHONPATH`. Output lands in the directory you ran it from |
| `.venv/bin/python -m wastatus ARGS` | the same, directly. `wastatus/__main__.py` reads `.env` first, because some settings are read at import time |
| `.venv/bin/python -m wastatus` with no arguments | opens the local page, the same as `serve` |

The first word chooses the mode: `serve` opens the local page, `hosted` is the
renderer and SnipShare, anything else is a URL and makes a clip.

## Make a clip: `wastatus URL [START] [END]`

**Table SK-2: clip arguments and flags**

| Argument or flag | Default | What it does |
|---|---|---|
| `url` | required | YouTube URL or video id |
| `start` | `?t=` in the URL, or 0 | start timestamp, for example `1:23` |
| `end` | start plus `--duration` | end timestamp, for example `1:38` |
| `-d`, `--duration SECONDS` | 15 | clip length when no end is given (at most 90) |
| `--title TITLE` | from YouTube, cleaned | override the on-card title |
| `--channel CHANNEL` | from YouTube | override the on-card channel name |
| `--footer TEXT` | empty | a small footer line |
| `--top-line TEXT` | empty | a line under WhatsApp's own header, above the picture |
| `--eyebrow [TEXT]` | empty; `NOW PLAYING` if given bare | a label just above the title, both modes |
| `--video` | card mode | the real video frames instead of the artwork card |
| `--no-wave` | waveform on | drop the waveform strip |
| `--fill {blur,black}` | `blur` | behind the frames in `--video`: a darkened blur of them, or black |
| `--picture X,Y,SIZE` | fitted | place the picture as three fractions: centre x, centre y, width. `0.5,0.5,1` fills the width |
| `--frame [AT]` | off; midpoint if bare | also write a still `.png`, at the midpoint or at offset `AT` |
| `--post` | off | post to your Status through a logged in WhatsApp Web tab. Presses Send |
| `--load` | off | load the composer with its caption and stop before Send. Exclusive with `--post` |
| `--follow-up` | off | also post a text only Status with the title and link |
| `--port N` | 9230 | Chrome debug port to try first; then 9230 to 9235, or `WASTATUS_CDP_PORTS` |
| `-o`, `--out DIR` | `out` | output directory |
| `--keep-last N` | 20 | clips kept in the output folder; 0 disables pruning |
| `--keep` | off | keep the intermediate work directory under the temp folder |
| `-v`, `--verbose` | off | echo the log to the console |

Each run writes the `.mp4`, its `.caption.txt` and a `.json` sidecar to the output
folder, with further sidecars in some cases (the list is `retention.py`'s, which
deletes them together; [DOMAIN.md](DOMAIN.md) describes them), plus a record in
`logs/runs.jsonl`.

## The local page: `wastatus serve`

**Table SK-3: `serve` flags**

| Flag | Default | What it does |
|---|---|---|
| `--port PORT` | 8765 | port for the page |
| `--cdp-port N` | 9230 | Chrome debug port to prefer for posting |
| `-o`, `--out DIR` | `out` | output directory |
| `--keep-last N` | 20 | clips kept |
| `--also-on ADDRESS` | none | also listen on this address, for a phone. `tailscale` resolves the tailnet address. Loopback always listens. Anyone who opens the page gets its token; not remembered between runs. `WASTATUS_ALSO_ON` sets it |
| `--start-browser` | off | start a Chrome with WhatsApp Web open if none is running. `WASTATUS_START_BROWSER` sets it |
| `--no-start-browser` | | override `WASTATUS_START_BROWSER` |
| `--no-open` | opens a tab | do not open a browser |
| `-v`, `--verbose` | off | echo the log to the console |

## The renderer and SnipShare: `wastatus hosted`

`--data DIR` comes before the subcommand and says where uploads, clips, tokens and
the people database live. Default `$WASTATUS_HOSTED_DATA`, else
`~/.local/share/wastatus/hosted`; `/data` in the container.

**Table SK-4: `hosted` subcommands**

| Command | Arguments | What it does |
|---|---|---|
| `hosted serve` | `--host HOST` (127.0.0.1), `--port PORT` (8790), `--workers N` (`$WASTATUS_HOSTED_WORKERS` or 1), `-v` | the renderer's API, SnipShare's pages and page API on one port, plus the scheduled watcher |
| `hosted token add NAME` | | make a renderer token and print it once; only its hash is kept |
| `hosted token revoke NAME` | | stop that token working, from the next request |
| `hosted token list` | | names and when each was made |
| `hosted user list` | | everyone and their state |
| `hosted user approve EMAIL` | | let a person who asked in |
| `hosted user decline EMAIL` | | refuse a request |
| `hosted user suspend EMAIL` | | stop a person, ending their sessions |
| `hosted user add EMAIL` | `--name NAME` | add a person directly |
| `hosted user forget EMAIL` | | delete the person and everything of theirs; refuses an admin |

Admins come from `WASTATUS_ADMIN_EMAILS` alone. Approving, suspending, forgetting
and tokens for anyone but the owner are Ask first in [AGENTS.md](AGENTS.md).

## Scripts

Python scripts run with `.venv/bin/python scripts/NAME.py`; shell scripts with
`bash scripts/NAME.sh`.

**Table SK-5: scripts and their arguments**

| Script | Arguments | What it does |
|---|---|---|
| `build_extension.py` | `--site URL` (default `$WASTATUS_PUBLIC_URL`), `--key PEM`, `--new-key PEM`, `--out DIR` (default `dist/snipshare-extension`), `--keep-custom-server` | builds the extension for one site into git-ignored `dist/`: `config.js` and `externally_connectable` name that site, local addresses removed, the any-https permission removed unless kept. `--key` pins the id and the script prints it; `--new-key` makes the key once. Leaves `dist/snipshare-extension.zip` |
| `extension_check.py` | `--renderer URL` and `--token-file PATH` (both required), `--video ID`, `--start S` (120), `--end S` (135), `--mode {card,video}`, `--quality` (hd720), `--throttle KBPS`, `--restart-at {capturing,uploading,rendering,downloading}`, `--stop-at {capturing,uploading,queued,rendering,downloading}`, `--popup PNG`, `--keep-clip MP4`, `--save`, `--headed`, `--port` (9341) | drives the real extension in a throwaway Chrome for Testing against a renderer, follows the job through its phases and checks the clip. The token is read from the file and never printed |
| `site_check.py` | `--load`, `--video ID` | SnipShare end to end on this machine: its own `hosted serve` on a spare port, a test person signed in, the extension built for that port, a throwaway Chrome under Xvfb. Prints one JSON report. Needs `CHROME_FOR_TESTING` or Playwright's Chromium, `xvfb-run`, ffmpeg and a network that reaches YouTube |
| `shot.py` | `URL OUT.png`, `--width` (1280), `--height` (900), `--dark`, `--full`, `--click SELECTOR`, `--wait S` (2.5), `--port N` | screenshots a page in a new tab of the debug Chrome, then closes the tab |
| `wa_post.py` | `video FILE --caption TEXT`, `video FILE --caption-file FILE`, `text "TEXT"`, `send`, `cancel`, `shot OUT.png`, `delete-all --yes`; `--send`, `--port N` | manual door into `wastatus/post.py`. Without `--send` the composer is left loaded and unsent. `delete-all` is irreversible |
| `deploy.sh` | none, or `--check` | builds the extension, copies what the image needs, rebuilds and restarts the Compose project, waits for healthy. `--check` only reports what is running. Reads `WASTATUS_DEPLOY_HOST`, `WASTATUS_DEPLOY_SITE`, `WASTATUS_EXTENSION_KEY` from the environment or `.env`. Ask first |
| `install_service.sh` | any `serve` flags, for example `--also-on tailscale` | writes and starts a systemd user unit running `serve --no-open`, clips to `$WASTATUS_OUT` or `~/wastatus-out`. Ask first |
| `setup_provider.sh` | none; `WASTATUS_POT_DIR`, `WASTATUS_POT_VERSION` (1.3.1) | installs the bgutil token provider yt-dlp needs. Requires git and node 20 or later. Refuses to delete a folder that is not its checkout |
| `setup_stickers.sh` | none; `WASTATUS_STICKER_DIR` | installs the OpenMoji library (CC BY-SA 4.0) and its keyword file. Requires curl and unzip |

## Tests

**Table SK-6: test commands**

| Command | What it runs |
|---|---|
| `.venv/bin/python -m pytest` | the offline suite, about three minutes; includes `node --test` for the extension's parser when Node is present |
| `.venv/bin/python -m pytest tests/test_publishable.py` | nothing personal or infrastructural in tracked files |
| `WASTATUS_E2E=1 .venv/bin/python -m pytest tests/test_smoke.py -v` | a real run against YouTube, about a minute |
| `node --test src/test/*.js` | the extension's parser on its own |

## APIs at a glance

Contracts, bodies and examples are in [API.md](API.md); the boundaries are in
[SECURITY.md](SECURITY.md).

**Table SK-7: the three HTTP surfaces**

| Surface | Served by | Auth | Routes |
|---|---|---|---|
| Local page API | `serve.py`, 127.0.0.1:8765 | `X-Wastatus-Token` header, the token embedded in the page; Host must be an address | GET `/api/state`, `/api/task`, `/api/frame`, `/api/clip`, `/api/gifs`, `/api/gif`, `/api/controls`, `/api/stickers`, `/api/sticker`; POST `/api/render`, `/api/post`, `/api/caption`, `/api/preview`, `/api/text`, `/api/words`, `/api/browser`, `/api/sticker`, `/api/sticker/delete`, `/api/gif/pick`, `/api/gif/provider`, `/api/cancel`, `/api/clip/delete` |
| Renderer API | `hosted.py`, under `/api/v1`, port 8790 | `Authorization: Bearer` token or a page grant; no CORS | `health` (no auth), `me`, `uploads` (POST create, PUT chunks with `Content-Range`, GET and HEAD progress, DELETE), `jobs` (POST, GET, `jobs/ID/clip` with `Range`, DELETE to cancel) |
| SnipShare | `portal.py`, same port | session cookie plus a derived page value, site `Origin` on changes | pages `/`, `/signin`, `/signup`, `/install`, `/app`, `/account`, `/admin`, `/privacy`, `/terms`; API `/api/signup`, `/api/session`, `/api/signout`, `/api/me`, `/api/grant`, `/api/account/*`, `/api/admin/*`, `/api/gifkey*`, `/api/feedback`, `/api/report` |

`POST /api/post` sends only with an explicit `"send": true`; without it the composer
is loaded and left.

## Workflows

### Make a clip locally

```bash
./wastatus.sh "https://youtu.be/<VIDEO_ID>" 1:10 1:25 --frame     # card mode, plus a still
./wastatus.sh "https://youtu.be/<VIDEO_ID>" 1:10 -d 20 --video    # real frames, 20 seconds
./wastatus.sh "https://youtu.be/<VIDEO_ID>?t=95" --eyebrow -o <scratch>
```

Look at the `.png`, then `tail -1 logs/runs.jsonl | .venv/bin/python -m json.tool`
for what ran.

### Post from the page

```bash
./wastatus.sh serve --start-browser          # page on 127.0.0.1:8765, WhatsApp Web in its own Chrome
```

Scan WhatsApp's QR code once in that browser. On the page: paste the link, set the
window, **Make the clip**, then **Load into WhatsApp**, which opens the composer
with the caption and stops. The Send press is the person's. From a terminal, the
equivalent is `--load`, then `scripts/wa_post.py send` or `cancel`.

### Build the extension

```bash
.venv/bin/python scripts/build_extension.py --new-key ~/.config/wastatus/extension-key.pem \
    --site https://snipshare.example.com                  # once: prints the id
.venv/bin/python scripts/build_extension.py --site https://snipshare.example.com \
    --key ~/.config/wastatus/extension-key.pem            # every build
```

For local work, load `src/` unpacked on `chrome://extensions`; it talks to a
renderer on 127.0.0.1. Check it end to end against a local renderer:

```bash
.venv/bin/python -m wastatus hosted --data <scratch> token add me > <scratch>/token
.venv/bin/python -m wastatus hosted --data <scratch> serve &
.venv/bin/python scripts/extension_check.py --renderer http://127.0.0.1:8790 \
    --token-file <scratch>/token --video <VIDEO_ID> --start 120 --end 140 \
    --throttle 800 --restart-at uploading
```

### Deploy

Ask first. Then:

```bash
.venv/bin/python -m pytest
scripts/deploy.sh
scripts/deploy.sh --check
.venv/bin/python scripts/extension_check.py --renderer https://snipshare.example.com \
    --token-file ~/.secrets/<token file> --video <VIDEO_ID> --start 120 --end 140
```

Rollback is `git checkout <good revision> && scripts/deploy.sh`; see
[DEPLOYMENT.md](DEPLOYMENT.md) for the migration caveat.

### Approve a person

Ask first. The admin does it on `/admin`; on the host:

```bash
ssh "$WASTATUS_DEPLOY_HOST" 'cd /opt/snipshare/deploy && docker compose exec app python -m wastatus hosted user list'
ssh "$WASTATUS_DEPLOY_HOST" 'cd /opt/snipshare/deploy && docker compose exec app python -m wastatus hosted user approve someone@example.com'
```

Locally, against a scratch data folder:
`.venv/bin/python -m wastatus hosted --data <scratch> user add someone@example.com --name "Some One"`.
