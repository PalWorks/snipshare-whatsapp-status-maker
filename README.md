# SnipShare

**Status Maker for WhatsApp, from YouTube videos.** Pick a few seconds of a YouTube or
YouTube Music video and get a vertical WhatsApp Status clip that carries the link back
to the original, so people hear the snippet first and can then go to the full track.

[![Licence: AGPL-3.0](https://img.shields.io/badge/licence-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB.svg)](requirements.txt)
[![Chrome MV3](https://img.shields.io/badge/Chrome-MV3-4285F4.svg)](src/manifest.json)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-0A9EDC.svg)](TESTING.md)

Last updated **2026-10-31T13:12:52+05:30**, with Scheduled Statuses (Release 1), the account page's menu and extension 2.1.1 (before that 2026-10-25T15:13:17+05:30)

```bash
./wastatus.sh "https://youtu.be/A6DfGQsdz1Y" 1:10 1:25
```

**Experimental.** A personal project, offered as is. It is not affiliated with,
endorsed by or sponsored by YouTube, Google, WhatsApp or Meta; their names are used
only to say what it works with, and belong to them. **Sending is always your own
press:** the tool loads WhatsApp's Status composer and stops, unless you ask it to
send from your own machine.

Source: [github.com/PalWorks/snipshare-whatsapp-status-maker](https://github.com/PalWorks/snipshare-whatsapp-status-maker). The
Python package and the command are still called `wastatus`, the project's working
name.

## Table of contents

- [Overview](#overview)
- [Responsible use](#responsible-use)
- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API reference](#api-reference)
- [Project structure](#project-structure)
- [Testing](#testing)
- [Deployment](#deployment)
- [Roadmap](#roadmap)
- [Agent usage notes](#agent-usage-notes)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [Licence](#licence)
- [Acknowledgements](#acknowledgements)

## Overview

There are two ways to use it. Both run the same engine, `pipeline.produce`, so the
clip looks the same whichever you choose.

**Table RM-1: the two ways to use SnipShare**

| | The local tool | The extension and the hosted site |
|---|---|---|
| What it is | a command line tool and a page, `./wastatus.sh serve`, on your own Linux or macOS machine | a Chrome extension plus a hosted renderer and site, invite only |
| Who reads YouTube | your machine, through `yt-dlp` | your own browser: the extension keeps what YouTube's player already loaded in your tab. The server never asks YouTube for anything |
| Where the clip is made | your machine, with `ffmpeg` | the hosted renderer |
| What you install | Python, ffmpeg, node, git, this repository | Google Chrome on a computer and the extension, loaded unpacked |
| How it reaches WhatsApp | prints the clip and caption; `--load` fills WhatsApp Web's Status composer in a Chrome you are signed into; `--post` also sends | **Load into WhatsApp** fills the composer in your own WhatsApp Web, and you press Send. **Schedule** does the same at a time you choose, for people the owner has switched scheduling on for |
| Start here | [Installation](#installation), or [LOCAL_SETUP.md](LOCAL_SETUP.md) line by line | [Use the hosted site](#use-the-hosted-site) |

**What you get:** one Status, the clip, captioned with the link. WhatsApp makes that
URL tappable (confirmed on the web client and on a phone), so one post is enough. The
title is on the card and not in the caption; the URL is in the caption and not in the
frame, because each would repeat the other ([DECISIONS.md](DECISIONS.md) D-015). The
bottom 15 percent and the top 12 percent of every frame are left empty, because
WhatsApp draws its caption and header there ([DOMAIN.md](DOMAIN.md)).

No account credentials, no unofficial WhatsApp client: posting drives a WhatsApp Web
tab you are already signed into, over the Chrome DevTools Protocol.

## Responsible use

- **Clip only what you have the right to share.** The video is not yours and not
  ours. Every clip carries the link back to the upload, which is the point of it, but
  what you may do with the result is between you and the uploader.
- **Keep YouTube's and WhatsApp's terms.** This is a tool for a person sharing a
  moment they like, at a person's pace. It is not for bulk or unattended posting, and
  the hosted site has daily limits that keep it that way. **Scheduled Statuses** (a
  pilot, switched on per person) only have the clip waiting in WhatsApp's composer at
  the time you chose; you still press Send, so nothing is posted unattended.
- **It never posts by itself.** The default everywhere is to load the composer and
  stop. The local tool sends only on `--post` or the page's explicit Send button; the
  extension never presses Send at all, including for a scheduled clip
  ([DECISIONS.md](DECISIONS.md) D-020, D-084, D-105). Sending on a schedule, with a
  confirmation, is designed but not built ([docs/scheduling.md](docs/scheduling.md)).
- **Protected (DRM) video cannot be clipped.** Encrypted media cannot be read. The
  extension does not yet say so before it tries ([LIMITATIONS.md](LIMITATIONS.md)).
- It is not a downloader: it reads only the window you choose, at most 90 seconds,
  and renders it into a new frame with the source named. It does not skip or block
  ads.

## Features

**The engine**

- A YouTube or YouTube Music link and two timestamps in; a 1080x1920 mp4 and its
  caption out. Timestamps accept `93`, `1:33` and `1:02:03`; with no start, a `?t=` in
  the URL is used.
- **Card mode** (default): blurred artwork background, the artwork as a rounded card
  with a soft shadow, the title and channel, a slow zoom, and a waveform that moves
  with the audio. Padding bars baked into the thumbnail are cropped off first, so a
  cinemascope still is not squeezed into a 16:9 box. Only the audio is fetched.
- **Video mode** (`--video`): real frames, a blurred or black fill to 9:16, text over
  the bottom. A letterboxed source is cropped to its picture first. Output goes to a
  separate `_video.mp4`.
- **Titles in Latin script.** Tamil titles are transcribed the way Tamil speakers
  spell them (`சின்ன சின்ன முருகையா` becomes `Sinna Sinna Murugaiyaa`), upload noise
  like `(Official Video)` and hashtags is stripped, and a title repeated in two
  scripts is collapsed.
- **Within WhatsApp's limits.** A single Status video is capped at 90 seconds, and
  the bitrate falls as the clip gets longer so the file stays under the 10 MiB line
  WhatsApp silently refuses at: about 5.5 MB for 15 seconds, about 10 MB for 90
  ([DECISIONS.md](DECISIONS.md) D-017).
- Files are named `YYYYMMDD_song-slug_start-end`, so the folder sorts by date and
  reads as a list of songs. The folder prunes itself to the newest 20 clips.

**The local page** (`./wastatus.sh serve`): everything the command line does, plus
the following.

**Table RM-2: what the page adds to the command line**

| On the page | Why |
|---|---|
| Set a **length or an end time**, whichever you have | you either know the clip runs 30 seconds or you know it ends at 1:45 |
| **The caption has its own box**, and the frame shows it where WhatsApp will draw it | it is text sent with the video, so an edit needs no render. D-021, D-030 |
| **The words on the card follow your typing**, redrawn by Pillow in well under a second, with a note that the file still has the old ones until you make the clip again | the words are pixels, so changing them means a 30 to 66 second render; seeing them takes 0.1 to 0.9 seconds. D-048 |
| **Load into WhatsApp** is the primary button, Send the second | sending is the only irreversible step. D-020 |
| **Play and scrub** the clip before it goes anywhere | the frame is what a viewer gets |
| **Recent clips** with their date; click one to load it back into the form | a correction is one edit and one press |
| **Stickers**: search 4,495 OpenMoji drawings, drag one onto the frame, size and turn it; pinch and twist on a phone; paste a picture or GIF in; upload your own | they are drawn into the video. D-024, D-033, D-036, D-038 |
| **GIF search**, GIPHY or KLIPY, off unless `.env` names a provider and its key. Thumbnails are fetched by the server, never by your browser | the only part of the local tool that talks to anybody but YouTube. D-043 |
| **Stop** a render you started by mistake | a 90 second clip takes about two minutes. D-025 |
| **Delete** a bad take, on two presses rather than a dialog | a dialog is dismissed by habit |
| **Download** the clip and copy its caption | for posting from the WhatsApp app on a phone. D-026 |
| **Every section folds**, and a folded one still says what is in it | on a phone the whole job fits in one screen. D-032 |
| **Light, dark or system** theme, remembered | the laptop and the phone do not agree. D-031 |
| Everything you typed **survives a reload** | a phone reloads the tab when you switch to WhatsApp and back |

On a laptop the page is two columns: everything you answer on the left, and the frame
on the right, which stays where it is. On a phone it is one column, in the order the
job is done.

**The extension and the hosted site**

- The same page, served per person: their own clips, stickers and GIF keys.
- Google sign-in after the operator approves a request; an account page with your
  profile, every clip you made, feedback with screenshots, and GIF search with your
  own free GIPHY and KLIPY keys.
- Ten clips and 500 MB of uploads a day each by default, one at a time.
- Slow connections are expected: uploads go in chunks that shrink when the line is
  slow and resume from what the renderer already holds; downloads resume too. If
  Chrome stops the extension's worker part way, the page offers to try again, which
  costs a read of the video, never a clip.
- An admin page for requests, people, usage and failure reports, and, per person, the
  scheduling pilot switch and limits.
- **Scheduled Statuses (a pilot, Release 1, live since 2026-10-31).** On a finished
  clip, **Schedule** opens a picker that starts on **Next in queue** (with the time it
  will land, such as "Next in queue · Sat 6:00 PM"), then In one hour, This evening,
  Tomorrow morning and a date and time. The extension keeps the clip on your own
  computer and, at the time, puts it and its caption in WhatsApp's Status composer
  without taking focus where Chrome allows, and notifies you; **you press Send**. The
  queue, one table sorted by time, is the extension's own page and also sits in the
  account page under **Scheduled Statuses**: change a time or caption in its row,
  cancel with Undo, pause, and see what needs you. It runs only while Chrome is open
  and the computer awake. It is off for everyone but the admins until an admin
  switches a person on. Not built yet: confirmed Send, **From a link** (Release 2)
  and the bulk bar (Release 3). [Unverified] whether a quiet placement works on a
  given machine: the owner's own Chrome and WhatsApp test (Phase 0) is in progress,
  and until it is done the extension asks by notification when no quiet way works.
  Design and as built: [docs/scheduling.md](docs/scheduling.md).
- The tool page's **Account** chip opens a menu: Profile, History, Scheduled
  Statuses (when scheduling is on), Extension, Admin (admins) and Sign out
  ([docs/account-page.md](docs/account-page.md)).

## Architecture

Three front ends, one engine. `cli` parses arguments and prints; `serve` answers the
local page; `hosted` and `portal` answer the extension and the hosted site. All of
them call `pipeline.produce`, the only thing that knows how a clip gets made.

```
local tool                                        hosted path
----------                                        -----------
YouTube URL + window                              YouTube tab in your Chrome
   |                                                 | extension copies what the
   v                                                 | player appended (recorder.js,
fetch: yt-dlp, client ladder,                        | media.js), uploads it in chunks
only the requested range                             v
   |                                              hosted: uploads, job queue
   +-----------------------+-------------------------+ capture.section cuts the window
                           v
             pipeline.produce: translit, compose (Pillow), render (ffmpeg)
                           |
                           v
             mp4 + caption + sidecars, retention, runlog
                           |
        +------------------+------------------+
        v                                     v
post.py over CDP: load the composer,      extension (whatsapp.js) fills the
send only when asked                      composer in your WhatsApp Web; never Send
```

The hosted path asks YouTube nothing. YouTube refuses datacentre addresses and has
moved its web player to a protocol `yt-dlp` cannot fetch from a server reliably, so
the extension never fetches anything either: it keeps a copy of what YouTube's own
player appended to the page's video buffers, on the viewer's own connection, and the
server checks the files it is given with ffprobe ([docs/extension.md](docs/extension.md)).

All text is drawn by Pillow, never by ffmpeg, because the reference ffmpeg build has
no freetype or libass; that is also what makes Linux and macOS render identically.
The local tool has no database: the output folder and its sidecars are the only state.
The hosted site keeps a small SQLite people database ([DATA_MODEL.md](DATA_MODEL.md)).

About 13,000 lines of Python in `wastatus/`, a page in vanilla HTML, CSS and
JavaScript with no build step, and an extension in the same style. Full design,
component boundaries and the failure model: [ARCHITECTURE.md](ARCHITECTURE.md).

## Tech stack

**Table RM-3: tech stack**

| Layer | What | Notes |
|---|---|---|
| Language | Python 3 | 3.13 in the hosted image; developed on 3.14 |
| Media | ffmpeg, ffprobe | all encoding and filtering; text never goes through ffmpeg |
| Extraction | yt-dlp, bgutil PO token provider (node) | local tool only; the provider is installed by `scripts/setup_provider.sh` |
| Pixels | Pillow | every glyph, card, sticker and preview |
| Romanisation | aksharamukha, Unidecode | Tamil phonetic romanisation, with Unidecode as the fallback |
| Posting | websocket-client over the Chrome DevTools Protocol | local tool only |
| Local server | Python standard library `http.server` | no framework |
| Front end | vanilla HTML, CSS, JavaScript | no build step, mobile first |
| Extension | Chrome Manifest V3, vanilla JavaScript | fragment parser tested in Node |
| Hosted site | the same server code, SQLite, google-auth, cryptography | Google sign-in, Cloudflare Turnstile, Resend mail, a Chat webhook |
| Deployment | Docker Compose, Cloudflare Tunnel | no host port opened |
| Tests | pytest, `node --test` | offline by default |

Versions in use are in [ARCHITECTURE.md](ARCHITECTURE.md) Table AR-2 and
[DEPENDENCIES.md](DEPENDENCIES.md).

## Installation

### The local tool, on Linux or macOS

Prerequisites: Python 3, `ffmpeg` on PATH, git, and node 20 or newer. On macOS:
`brew install ffmpeg node git`.

```bash
git clone https://github.com/PalWorks/snipshare-whatsapp-status-maker.git
cd snipshare
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
bash scripts/setup_provider.sh      # once, needs git and node >= 20
bash scripts/setup_stickers.sh      # once, 45 MB of stickers, optional
```

`setup_provider.sh` installs the proof of origin token provider that YouTube now
requires, pinned to 1.3.1; the tool starts and stops it automatically
([docs/extraction.md](docs/extraction.md)). It lives outside the repository, in
`~/.local/share/wastatus/bgutil` on Linux or
`~/Library/Application Support/wastatus/bgutil` on macOS, about 209 MB.

`setup_stickers.sh` downloads [OpenMoji](https://openmoji.org) once: 4,495 drawings
at 618 pixels, into the same data directory, never into this repository.

Never run it before? [LOCAL_SETUP.md](LOCAL_SETUP.md) walks a first run step by step,
for a Mac and a fresh Linux machine.

### The extension, for the hosted site

1. **Ask for access** on the site, with Google or the form. The operator approves.
2. **Get the extension** from the site's `/install` page, unzip it into a folder that
   will stay, and load it unpacked: `chrome://extensions`, **Developer mode**, **Load
   unpacked**. It cannot be on the Chrome Web Store, whose policy does not allow
   downloading streaming media.
3. **Sign in with Google**, or press the extension's button, which opens the site.

The site currently offers extension **2.1.1** (`src/manifest.json`); the site
accepts 2.0.0 and newer for making clips, and **Scheduled Statuses needs 2.1.0 or
newer** (2.1.1 adds the time on **Next in queue**; an older one still schedules and
shows the words "After your last scheduled post"). `chrome://extensions` shows the
version on the extension's card, and the account page's **Extension** item opens the
download. 2.1.0 added four permissions for Scheduled Statuses (`notifications`,
`idle`, `unlimitedStorage`, `contextMenus`); the reasons are in
[SECURITY.md](SECURITY.md).

To update, download the zip again, replace the folder's contents and press the reload
arrow on the extension's card.

## Configuration

**None of the settings is required.** Set one in your shell, or copy `.env.example`
to `.env` and put it there. `.env` is ignored by git, and anything already exported
in your shell wins over the file. Every setting is listed, with no values, in
[.env.example](.env.example).

**Table RM-4: settings**

| Variable | Purpose |
|---|---|
| `WASTATUS_PROXY` | proxy for YouTube traffic, for hosts with a flagged address |
| `WASTATUS_COOKIES_FROM_BROWSER` | passed to `yt-dlp --cookies-from-browser` |
| `WASTATUS_ALSO_ON` | bind a second address as well as loopback at every start; `tailscale` resolves your tailnet address. Empty, the default, is loopback only |
| `WASTATUS_START_BROWSER` | start a Chrome with WhatsApp Web when the page starts, if none is running |
| `WASTATUS_CDP_PORTS` | which debug ports to look for that browser on, as a list or a range (default `9222-9226`) |
| `WASTATUS_CHROME_DIR` | the posting browser's own profile, which holds its WhatsApp login |
| `WASTATUS_CACHE_DIR` | where the session label tab is written (default `~/.cache/wastatus`) |
| `WASTATUS_STICKER_DIR` | where the sticker library and your uploads live |
| `WASTATUS_LOG_DIR` | where logs are written (default `logs/`) |
| `WASTATUS_POT_DIR`, `WASTATUS_POT_PORT` | where the token provider is installed, and its port (default 4416) |
| `WASTATUS_GIF_PROVIDER`, `WASTATUS_GIPHY_KEY`, `WASTATUS_KLIPY_KEY`, `WASTATUS_GIF_RATING` | the GIF picker, off unless a provider and its key are both set |
| `WASTATUS_SHEET_ID`, `WASTATUS_SHEET_KEY`, `WASTATUS_SHEET_TAB` | the optional Google Sheet record. Unset means no sheet |
| `WASTATUS_POST_ATTEMPTS`, `WASTATUS_POST_BACKOFF` | how many times to re-send a Status WhatsApp refused (default 3), and the first wait in seconds, doubling (default 20) |
| `WASTATUS_ENV` | read settings from a `.env` file somewhere other than beside the code |
| `WASTATUS_E2E` | `1` enables the end to end test |
| `WASTATUS_HOSTED_DATA`, `WASTATUS_HOSTED_WORKERS` | the hosted renderer only: where uploads, clips and tokens live, and renders at once (default 1) |
| `WASTATUS_PUBLIC_URL`, `WASTATUS_ADMIN_EMAILS`, `WASTATUS_SECRET_KEY`, `WASTATUS_SOURCE_URL` and the rest of `.env.example`'s SnipShare section | the hosted site only: its address, its admins, sign-in, Turnstile, mail and Chat, daily limits, and where its source code is published. Never needed on a machine that runs only the local tool |

`WASTATUS_PROXY` and `WASTATUS_COOKIES_FROM_BROWSER` both carry account risk. See
[SECURITY.md](SECURITY.md).

## Usage

### Make a clip at the command line

```bash
./wastatus.sh "https://youtu.be/A6DfGQsdz1Y" 1:10 1:25
```

```
clip     out/20260818_sinna-sinna-murugaiyaa_70-85.mp4  (5.6 MB, 15s)
caption  https://youtu.be/A6DfGQsdz1Y

Post the clip with that caption. WhatsApp makes the URL tappable.
(caption copied to the clipboard)
```

The caption is also written next to the mp4 as `.caption.txt`. The source URL lives
there and in the run log, so nothing is lost by keeping the id out of the filename.

`--load` opens the Status composer with the clip and the caption in place and stops,
leaving Send to you:

```
loading  through Chrome/150.0.7871.186 on port 9222
loaded   the composer is open with the caption in place.
         Press Send in that browser when you are ready.
```

`--post` sends as well, and reports it as posted only on WhatsApp's own
acknowledgement ([DECISIONS.md](DECISIONS.md) D-071):

```
posting  through WhatsApp Web on port 9222
posted   the clip is live, upload took 11s
```

Both need a Chrome started with `--remote-debugging-port` and web.whatsapp.com open
and signed in inside it. The configured port is tried first, then the others, and the
first browser holding a WhatsApp tab is used. Since Chrome 136 that switch is ignored
for your default profile, which is why the posting browser has a profile of its own
(D-012, D-022). If posting fails, the clip is still on disk.

**Table RM-5: command line options**

| Flag | Effect |
|---|---|
| `-d, --duration N` | clip length when no end timestamp is given (default 15s) |
| `--video` | use the real video frames instead of the artwork card |
| `--fill blur\|black` | what goes behind the frames with `--video` (default a darkened blurred copy) |
| `--picture X,Y,SIZE` | place the picture yourself, as fractions: centre and width |
| `--no-wave` | drop the waveform strip |
| `--frame [AT]` | also write a still png, at the midpoint or a given offset |
| `--load` | load the composer with clip and caption, and stop before Send |
| `--post` | post it to your Status through a signed in WhatsApp Web tab |
| `--follow-up` | also post a text only Status carrying the title and link (D-003, D-013) |
| `--port N` | Chrome debugging port to prefer (default 9222) |
| `--title`, `--channel` | override the on-card text |
| `--footer TEXT` | add a small footer line, off by default |
| `--eyebrow [TEXT]` | add a label just above the title, off by default (D-075) |
| `--top-line TEXT` | add a line under WhatsApp's own header, off by default |
| `-o, --out DIR` | output directory (default `out/`) |
| `--keep-last N` | clips to retain in the output folder, `0` disables pruning (default 20) |
| `--keep` | keep the intermediate work directory |
| `-v, --verbose` | echo the log to the console |

Exit codes: `0` success, `1` a stage failed, `2` bad arguments or a window the
platform will not accept.

### The local page

```bash
./wastatus.sh serve       # or just ./wastatus.sh, which means the same thing
```

```
wastatus is serving http://127.0.0.1:8765/
Output goes to ~/snipshare/out
WhatsApp Web: ready
Stop with Ctrl-C.
```

The browser opens by itself. The three health checks live behind one chip at the top
right, green when they all pass; if WhatsApp Web is not `ready`, the post button stays
disabled, and the chip offers **start it** and **recheck**. When the tool starts a
posting browser, that browser's first tab is a label whose title reads
`● 8765 · wastatus`, so you can tell which Chrome window is this session's (D-050).

It binds loopback, and every request from the page carries a per process token,
because any website you visit can otherwise reach a server on localhost
([SECURITY.md](SECURITY.md)).

**Table RM-6: page options**

| Flag | Effect |
|---|---|
| `--port N` | port for the page (default 8765) |
| `--cdp-port N` | Chrome debugging port to prefer for posting (default 9222, or the first of `WASTATUS_CDP_PORTS`) |
| `--start-browser`, `--no-start-browser` | start a Chrome with WhatsApp Web if none is running, or refuse to |
| `-o, --out DIR` | output directory |
| `--keep-last N` | clips to retain in the output folder (default 20) |
| `--also-on ADDRESS` | additionally listen on this address, so a phone can reach the page; `tailscale` resolves your tailnet address |
| `--no-open` | do not open a browser |
| `-v, --verbose` | echo the log to the console |

### From a phone

```bash
./wastatus.sh serve --also-on tailscale
```

Loopback stays bound, and the page also appears at your tailnet address, printed as
an `Also on` line. Pass the flag every time, or set `WASTATUS_ALSO_ON=tailscale` in
`.env`: it lasts as long as the process. On the phone the panel leads with
**Download** and the caption's **Copy**, so you can post in the real WhatsApp app
with no automation at all. **Load into WhatsApp** still works from the phone: it fills
the composer in the laptop's browser and stops.

A tailnet rather than the whole local network, because the page hands its token to
whoever loads it (D-027). Needs [Tailscale](https://tailscale.com) on both machines;
four commands in [LOCAL_SETUP.md](LOCAL_SETUP.md).

**Captions on your own device.** A link in a Status caption is not tappable when you
view your own Status on the device that posted it. It is tappable for everyone else.
Test a caption on a second device.

### Stickers and GIFs

Search for `om`, `diya`, `flower` or `music`, then drag a sticker onto the frame.
OpenMoji is an emoji set and has no deity art, so `shiva` or `ganesha` return nothing;
**Upload** takes your own PNG, WebP or JPEG files, up to 2 MB and 2048 pixels an edge,
and your own always come first.

**Paste a picture in** and it becomes a sticker, an animated GIF included, which
loops for the whole clip. On a phone, tap the dashed box that says "Tap here, then
pick a GIF on your keyboard" and use the keyboard's GIF tab. Do this step in Firefox
on Android: Chrome on Android refuses a picture from the keyboard ("Can't enter this
content here"), measured on two phones and two keyboards.

Stickers are drawn into the video, so a change means making the clip again, and the
page says so. One that strays into the bands WhatsApp draws over is outlined in amber
rather than moved (D-024).

### Use the hosted site

1. Paste a YouTube link and the window, press **Make the clip**.
2. The extension opens the video in a tab for a moment, reads the window without
   playing it, uploads it with a 15 minute grant, and the clip lands in the preview.
3. **Load into WhatsApp** puts it into WhatsApp Web's Status composer with the link
   as its caption. Look, and press Send.

To post later instead, press **Schedule** and pick a time (it starts on **Next in
queue**); the clip waits on your computer and is put in WhatsApp's composer at the
time, ready for you to send. **Scheduled Statuses** in the Account menu shows the
queue. Scheduling appears only for people an admin has switched it on for, and only
when the extension is 2.1.0 or newer.

Making a clip needs Google Chrome on a computer; on a phone the site shows the clips
you made, to watch and save. Design, limits and what is watched:
[docs/hosted-page.md](docs/hosted-page.md); the extension's side:
[docs/extension.md](docs/extension.md).

### Develop the site and extension locally

```bash
./wastatus.sh hosted serve                 # site and renderer at http://127.0.0.1:8790
./wastatus.sh hosted token add NAME        # a token for the extension's options page
.venv/bin/python scripts/site_check.py     # the whole site end to end, throwaway Chrome
```

Load the repository's own `src/` folder unpacked: `src/config.js` points it at
`http://127.0.0.1:8790`.

### Record every Status in a Google Sheet

Optional. Every Status WhatsApp **accepted** gets a row: Timestamp, Source, Status,
Remarks. A refused one gets none, and neither does one loaded but not sent.

```bash
gcloud services enable sheets.googleapis.com --project=your-project-id
gcloud iam service-accounts create wastatus-writer --project=your-project-id
gcloud iam service-accounts keys create ~/.config/wastatus/sheets-sa.json \
    --iam-account=wastatus-writer@your-project-id.iam.gserviceaccount.com
chmod 600 ~/.config/wastatus/sheets-sa.json
```

Share the sheet with that service account address as **Editor**, and put the three
`WASTATUS_SHEET_*` settings in `.env`. Nothing here can break a post: an unreachable
sheet costs a row and says so in the log (D-074).

### Run it in the background

Optional, and not how it is normally run (D-028):

```bash
bash scripts/install_service.sh                       # loopback only
bash scripts/install_service.sh --also-on tailscale   # and from a phone
systemctl --user status wastatus
journalctl --user -u wastatus -f
```

A systemd **user** service: no root, nothing outside `~/.config/systemd`. Clips go to
`~/wastatus-out` unless `WASTATUS_OUT` says otherwise. macOS has no `systemctl`; the
script says so and stops.

### Logs

**Table RM-7: log files**

| File | Use |
|---|---|
| `logs/wastatus.log` | rotating text, 2 MB and three backups: full yt-dlp and ffmpeg output, every request the page served with the token redacted, and a stamp at each start naming versions, ports, the git revision and the **names** (never values) of the settings `.env` supplied |
| `logs/chrome.log` | what the posting browser said; truncated at 2 MB |
| `logs/runs.jsonl` | one JSON object per run, from the command line or the page: window, mode, which extraction strategy won, stage timings, output size, and for a post the port and browser |

```bash
tail -5 logs/runs.jsonl | .venv/bin/python -m json.tool --json-lines
grep -o '"client": "[^"]*"' logs/runs.jsonl | sort | uniq -c
```

More in [OBSERVABILITY.md](OBSERVABILITY.md); symptoms and fixes in
[RUNBOOK.md](RUNBOOK.md).

## API reference

Three HTTP surfaces, all served by this repository. The full contracts, with request
and response shapes, are in [API.md](API.md) and [ARCHITECTURE.md](ARCHITECTURE.md)
Tables AR-3, AR-4 and AR-5.

**Table RM-8: HTTP surfaces**

| Surface | Served by | Authorised by | Examples |
|---|---|---|---|
| The local page's API, `/api/*` | `serve.py`, loopback | a per process token sent in a header; a write also needs a matching `Origin` | `GET /api/state`, `POST /api/render`, `GET /api/task?id=`, `POST /api/post` (sends only on `send: true`), `POST /api/cancel` |
| The renderer's API, `/api/v1/*` | `hosted.py` | `Authorization: Bearer <token>`, or an upload grant; no CORS headers | `GET /health`, `POST /uploads`, `PUT /uploads/{id}` with `Content-Range`, `POST /jobs`, `GET /jobs/{id}/clip` |
| The hosted site's calls | `portal.py` | a session cookie, the value derived from it, and the site's `Origin` | `POST /api/signup`, `POST /api/session`, `POST /api/grant`, `GET /api/account`, `GET /api/admin` |

```bash
curl -s http://127.0.0.1:8790/api/v1/health
```

```json
{"ok": true, "version": 1, "queued": 0, "rendering": 0, "workers": 1}
```

Admin commands on a running site:

```bash
python -m wastatus hosted user list
python -m wastatus hosted user approve someone@example.com
python -m wastatus hosted user suspend someone@example.com
python -m wastatus hosted user add someone@example.com --name "Some One"
python -m wastatus hosted user forget someone@example.com
```

## Project structure

```
wastatus/
  cli.py         argument handling, the report, posting
  pipeline.py    the engine: a window in, a postable clip out
  serve.py       the local page's server, standard library only
  web/           the page itself: one html, one css, one js
  post.py        drives WhatsApp Web's Status composer over CDP
  fetch.py       yt-dlp: metadata, the section download ladder, artwork
  potoken.py     finds, starts and stops the PO token provider
  compose.py     Pillow: the card and the transparent text overlay
  render.py      ffmpeg: zoom, waveform, fades, encode
  stickers.py    the sticker library, and pasting stickers onto a frame
  gifs.py        GIF search, GIPHY and KLIPY behind one seam
  translit.py    title cleanup and Tamil romanisation
  naming.py      date led, human readable output filenames
  retention.py   keeps the output folder trimmed
  runlog.py      text log and one JSON record per run
  sheet.py       the optional Google Sheet record
  capture.py     checks an upload from the extension and cuts the window
  hosted.py      the hosted renderer the extension uploads to
  portal.py      the hosted site: public pages, sign-in, each person's page
  accounts.py    the hosted site's people database
  signin.py      Google sign-in and Turnstile
  notify.py      mail and Chat to the operator
  watch.py       the hosted site's checks, daily digest, backup and tidy
  pages/         the hosted site's public pages, account and admin pages
src/             the Chrome extension: capture, upload, load WhatsApp; the scheduled
                 queue (queue.js, custody.js, place.js, schedule.js, queue.html); Node tests
deploy/          Dockerfile, Compose project (app and tunnel), the image's requirements
scripts/         setup, deploy.sh, build_extension.py, extension_check.py, site_check.py
tests/           pytest, offline plus an opt in end to end run
assets/fonts/    DejaVu Sans, bundled so Linux and macOS render identically
docs/            deep dives: extraction, hosting, the extension, the hosted page
.env.example     every setting the tool reads, with no values
```

`logs/`, `out/` and `dist/` are created at run time and ignored by git. A full source
index is in [CONTEXT_MAP.md](CONTEXT_MAP.md) Table CM-2.

## Testing

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest                                      # offline suite
WASTATUS_E2E=1 .venv/bin/python -m pytest tests/test_smoke.py   # real run, opt in
```

The offline suite, 1,613 pytest tests (7 skipped) and 157 Node tests when last counted
on 2026-10-31 (the commit that added the one Schedule button), covers timestamp parsing,
transliteration, naming, retention, logging, the bands WhatsApp's own interface
occupies, the size budget, the posting driver, the local page's server and its
guards, the hosted renderer and site, the capture cut, and the extension's parser,
which runs under `node --test` from `tests/test_extension.py`.
`tests/test_publishable.py` keeps personal and infrastructure detail out of every
tracked file.

The end to end test is opt in, because a failure there usually means YouTube changed
something rather than that the code regressed. Pixels, the download path and the
extension in a real Chrome are checked by hand and by `scripts/extension_check.py`;
the manual set is in [TESTING.md](TESTING.md).

## Deployment

The local tool has no deployment: it runs where it is cloned. The hosted site is a
Docker Compose project of two containers: `app` (pages, page API and renderer on port
8790, reachable only inside the project's network) and `tunnel` (`cloudflared`, the
only way in; no host port is opened). The app runs with a read only root, no
capabilities and a non root user, and installs only
[deploy/requirements.txt](deploy/requirements.txt): no yt-dlp, no token provider, no
websocket-client, because the site never talks to YouTube and never drives WhatsApp.

```bash
.venv/bin/python -m pytest          # first, always
scripts/deploy.sh                   # build the extension, copy, build the image, restart
scripts/deploy.sh --check           # what is running and what it says about itself
```

`deploy.sh` reads `WASTATUS_DEPLOY_HOST`, `WASTATUS_DEPLOY_SITE` and
`WASTATUS_EXTENSION_KEY` from the deploying machine. The one time setup (tunnel,
Google sign-in client, Turnstile, mail, Chat webhook, extension key), roll back and
removal are in [DEPLOYMENT.md](DEPLOYMENT.md). Because the site is AGPL, every public
page links "Source code" to `WASTATUS_SOURCE_URL`; a changed copy must point at its
own published changes.

## Roadmap

**Table RM-9: roadmap**

| Phase | Goal | Status |
|---|---|---|
| 1 | Local tool: link plus timestamps in, clip and caption out | done |
| 2 | Usable without the owner's laptop | done, as the extension and hosted renderer |
| 2b | The full page, hosted for invited people | done, as the hosted site |
| 3 | Post to WhatsApp Status directly | done on the desktop, by driving WhatsApp Web |
| 4 | Capture the current video from the browser | done, as part of phase 2 |
| 5 | Scheduled Statuses: put a clip in WhatsApp at a chosen time | **Release 1 live** (prepare only, from the editor, pilot). Next: the owner's Phase 0 test, a week of use, then confirmed Send, Release 2 (from a link), Release 3 (the bulk bar) |

Next, each the maintainer's call: the extension naming protected video before it
tries, product analytics once there are enough people, the Chrome Web Store if its
policy ever allows it, and Instagram as a second source ([TASKS.md](TASKS.md) T-033).
Non goals: archival quality output, a general purpose video editor, and working
around YouTube protections. Detail in [ROADMAP.md](ROADMAP.md); known gaps in
[LIMITATIONS.md](LIMITATIONS.md).

## Agent usage notes

- [AGENTS.md](AGENTS.md) is the behaviour contract: allowed actions, what needs
  asking first, what is never done, conventions and how to report. Read it before
  changing code. [CONTEXT_MAP.md](CONTEXT_MAP.md) says which file answers what.
- Reusable prompts are in [PROMPTS.md](PROMPTS.md); the commands, scripts and
  workflows an agent can call are in [SKILLS.md](SKILLS.md).
- The download path breaks on YouTube's schedule. That is expected, not a regression.
  [RUNBOOK.md](RUNBOOK.md) maps symptoms to fixes and
  [docs/extraction.md](docs/extraction.md) holds the measurement history.
- `pytest` covers the offline logic, not the download path or the pixels. Look at a
  rendered frame before claiming a visual change works ([TESTING.md](TESTING.md)).
- Never use ffmpeg `drawtext`, never bundle a Tamil font, never authenticate as a
  WhatsApp account through an unofficial client, never make sending the default, and
  never make the hosted renderer talk to YouTube. The reasons are in
  [DECISIONS.md](DECISIONS.md).
- Never write a real address, host, key or home directory into a tracked file; use
  `example.com` placeholders. `tests/test_publishable.py` fails on them.

## Documentation

**Table RM-10: documentation index**

| Read | For |
|---|---|
| [LOCAL_SETUP.md](LOCAL_SETUP.md) | first run, step by step, on Linux or macOS |
| [ARCHITECTURE.md](ARCHITECTURE.md) | pipeline, component boundaries, HTTP surface, scaling |
| [API.md](API.md) | every endpoint, its contract and examples |
| [DATA_MODEL.md](DATA_MODEL.md) | the output files, sidecars and the hosted people database |
| [DOMAIN.md](DOMAIN.md), [GLOSSARY.md](GLOSSARY.md) | WhatsApp's platform rules, and the terms used here |
| [DECISIONS.md](DECISIONS.md) | why things are built the way they are (the D numbers above) |
| [DEPLOYMENT.md](DEPLOYMENT.md) | running a copy of the hosted site |
| [OBSERVABILITY.md](OBSERVABILITY.md), [RUNBOOK.md](RUNBOOK.md), [INCIDENTS.md](INCIDENTS.md) | logs and monitoring, fixing failures, past incidents |
| [SECURITY.md](SECURITY.md) | secrets, the page's token, account risk, reporting a vulnerability |
| [TESTING.md](TESTING.md) | the automated and manual checks |
| [DEPENDENCIES.md](DEPENDENCIES.md) | external tools, services and versions |
| [FAQ.md](FAQ.md) | common questions |
| [AGENTS.md](AGENTS.md), [PROMPTS.md](PROMPTS.md), [SKILLS.md](SKILLS.md), [PLAYBOOK.md](PLAYBOOK.md) | working on the code, by hand or with an agent |
| [MEMORY.md](MEMORY.md), [LIMITATIONS.md](LIMITATIONS.md) | assumptions, known gaps and edge cases |
| [ROADMAP.md](ROADMAP.md), [TASKS.md](TASKS.md), [CHANGELOG.md](CHANGELOG.md) | where it is going, what is next, what changed |
| [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_STYLE.md](CODE_STYLE.md) | how to contribute, and the conventions |
| [docs/](docs/) | deep dives: [extraction](docs/extraction.md), [the extension](docs/extension.md), [the hosted page](docs/hosted-page.md), [the account page](docs/account-page.md), [scheduling](docs/scheduling.md), [hosting](docs/hosting.md), [Instagram](docs/instagram.md) |

## Contributing

Contributions are welcome under [CONTRIBUTING.md](CONTRIBUTING.md). Because the
project is dual licensed, a contribution needs a licence grant that lets PalWorks
offer it under both licences; CONTRIBUTING.md says how. Before opening a pull request:
read [AGENTS.md](AGENTS.md) and [CODE_STYLE.md](CODE_STYLE.md), add tests for new
offline logic in the same change, and run `.venv/bin/python -m pytest`. Report a
security problem as [SECURITY.md](SECURITY.md) describes, not in a public issue.

## Licence

SnipShare is dual licensed:

- **AGPL-3.0-only**, in [LICENSE](LICENSE). If you change the code and let people use
  it over a network, offer them the source of your changed version.
- **A paid commercial licence** from PalWorks, for building on the code or running a
  changed copy as a service without publishing your changes. See
  [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md).

Third-party code keeps its own terms, listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). In short:

**Table RM-11: third-party terms in brief**

| What | Terms |
|---|---|
| Python packages (yt-dlp, Pillow, aksharamukha, Unidecode and the rest) | their own licences, installed by `pip`, never copied here. aksharamukha is AGPL-3.0 whatever licence you take from us |
| **OpenMoji**, the sticker drawings | CC BY-SA 4.0, downloaded on first use, not committed |
| **DejaVu Sans**, the two fonts under `assets/fonts/` | the Bitstream Vera licence, in [assets/fonts/LICENSE.md](assets/fonts/LICENSE.md), committed unmodified |
| **The video you point this at** | not yours and not ours. See [Responsible use](#responsible-use) |

YouTube, YouTube Music, Google, Chrome, WhatsApp and Meta are trademarks of their
owners.

## Acknowledgements

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [FFmpeg](https://ffmpeg.org), which
  do the hard work underneath.
- [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider),
  for the proof of origin tokens.
- [Pillow](https://python-pillow.org), which draws every pixel that carries text.
- [aksharamukha](https://github.com/virtualvinodh/aksharamukha-python) and
  [Unidecode](https://github.com/avian2/unidecode), for romanisation.
- [OpenMoji](https://openmoji.org) for the stickers and DejaVu for the fonts.
- [GIPHY](https://developers.giphy.com) and [KLIPY](https://docs.klipy.com) for GIF
  search, and [Tailscale](https://tailscale.com) for reaching the page from a phone.
