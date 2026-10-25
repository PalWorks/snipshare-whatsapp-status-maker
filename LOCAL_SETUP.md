# Local setup and first run

Written to be followed literally.

Everything is already installed on the Linux machine at
`~/Documents/WhatsApp-Status`, so to use it today, follow
**Start the page** and nothing else. Setting up a different machine? Do
**Install** first. Prefer the terminal? **Your first run** covers that.

## Use SnipShare instead

Nothing below this section is needed for it: no Python, no ffmpeg, no terminal.
The clip is made on the SnipShare server, and the video is read in your own Chrome.
**Making a clip needs Google Chrome on a computer**; on a phone, SnipShare shows the
clips you made, to watch and save.

1. **Ask for access** on the site's front page: **Request access**, with Google or
   the form. The owner approves it.
2. **Get the extension** from the site's `/install` page. Unzip it into a folder
   that will stay. In Chrome, open `chrome://extensions`, switch on **Developer
   mode** at the top right, press **Load unpacked**, and choose that folder. Pin it
   from the puzzle piece icon so its button is always in the toolbar.
3. **Sign in.** Press the button: it opens SnipShare. **Sign in with Google**, with
   the address you asked with.
4. **Make a clip.** Paste a YouTube link and the window, press **Make the clip**. The
   video opens in a tab for a moment and closes again; the clip lands in the preview.
5. **Post it.** **Load into WhatsApp** opens WhatsApp Web's Status composer with the
   clip and the link as its caption. Check it there, and press Send yourself.

**Updating:** download the zip again from `/install`, replace the folder's contents,
then press the reload arrow on the extension's card in `chrome://extensions`.

**Developing the site** on this machine: `wastatus hosted serve` answers at
`http://127.0.0.1:8790`, and the repository's own `src/` folder, loaded
unpacked, talks to exactly that address (`src/config.js`).
`scripts/site_check.py` runs the whole thing end to end in a throwaway Chrome.

The extension's original popup, which takes a token the owner made
(`wastatus hosted token add NAME`), is its options page: right-click the button,
**Options**.

## Two lines, once `.env` is set up

```bash
cd ~/Documents/WhatsApp-Status
./wastatus.sh
```

That is the whole thing, on a machine whose `.env` says so. The page comes up, the
tailnet address is bound for the phone, and a Chrome with WhatsApp Web is started if
one is not already running. Three settings do it:

```bash
WASTATUS_ALSO_ON=tailscale      # bind the tailnet as well as loopback, every time
WASTATUS_START_BROWSER=1        # start a WhatsApp Web browser if there is not one
WASTATUS_CDP_PORTS=9230-9235    # which debug ports to use, when something else has 9222
```

`.env` is ignored by git and is read at startup. `.env.example` describes all three.
A flag on the command line still wins for that run: `./wastatus.sh serve
--no-start-browser` starts nothing whatever the file says.

**Nothing here starts by itself.** These settings only stop you retyping three flags;
they run when you run the command and stop when you stop it. See
[DECISIONS.md](DECISIONS.md) D-044, and D-028 for why there is no service.

**Set none of them and everything below still applies**, which is what a fresh clone
does: loopback only, no browser started, ports 9222 to 9226.

## Start the page

The page is the easy way in: a card for each part of the job, a preview you can
play, and a button that loads it into WhatsApp for you to send. Five steps, copied
one line at a time into a terminal.

**Step 1. Go to the project.**

```bash
cd ~/Documents/WhatsApp-Status
```

**Step 2. Start Chrome with WhatsApp Web open, so the page can reach WhatsApp.**
Skip this only if you just want the mp4 and will post it yourself.

```bash
google-chrome --remote-debugging-port=9222 \
    --user-data-dir="$HOME/.config/chrome-wastatus" https://web.whatsapp.com &
```

The first time, scan the QR code with your phone. That profile stays logged in, so
every later run just works. Leave the window open, minimised is fine.

Or skip this step and let the page do it: once it is up, open the chip at the top
right and press **start it** on the WhatsApp Web row. It runs exactly this command
for you.

It has to be its own profile, and it has to be started with that switch.

**Your everyday Chrome profile can never be used.** Measured on 2026-08-22: launching
against `~/.config/google-chrome` prints `DevTools remote debugging requires a
non-default data directory` and opens no port at all. Chrome 136 and later refuse it
by design, and no flag gets round it. That is why this tool keeps a profile of its
own, and why the QR code is scanned once and not again.

**You cannot add the switch to a Chrome that is already open.** It has to be there at
launch, so the browser you are reading this in is not a candidate for it.

**Pick a port nothing else holds.** Any browser started this way will do, on any port
in `WASTATUS_CDP_PORTS` (9222 to 9226 by default): the page uses whichever one has a
WhatsApp tab and tells you which. But a port that is already taken fails in a way
that looks like success. Chrome logs `bind() failed: Address already in use (98)`,
carries on with **IPv6 only**, and prints `DevTools listening on ws://[::1]:9222`,
while everything here asks `127.0.0.1`. `ss -ltn | grep 92` lists what is taken, and
the tool now says `port N is only half open` and names the browser that took it.
See [DECISIONS.md](DECISIONS.md) D-022 and D-045.

**Step 3. Start the page.**

```bash
./wastatus.sh serve
```

```
wastatus is serving http://127.0.0.1:8765/
Output goes to ~/Documents/WhatsApp-Status/out
WhatsApp Web: ready
Stop with Ctrl-C.
```

Your browser opens by itself. If it does not, open `http://127.0.0.1:8765` yourself.
The chip at the top right says **All set** when everything the page needs is there;
if it does not, open it and it will say which of the three is missing.

**The Chrome it starts for posting has a label as its first tab.** Its title reads
`● 8765 · wastatus`, so the window title and the task bar say which port this
session's page is on, and the tab itself names the debug port, the profile and the
output folder. That is the answer to "which of these Chrome windows is the tool's".
It is a file, `~/.cache/wastatus/session-8765.html`, so it is still readable after
the tool is stopped, and `WASTATUS_CACHE_DIR` moves it.

**Going to read the page on your phone? Start it this way instead.**

```bash
./wastatus.sh serve --also-on tailscale
```

```
wastatus is serving http://127.0.0.1:8765/
Output goes to ~/Documents/WhatsApp-Status/out
WhatsApp Web: ready
Stop with Ctrl-C.
Also on http://100.x.y.z:8765/ for another device.
Whoever opens that page can post to your Status. Keep it to a tailnet.
```

Open that second address on the phone, with Tailscale connected there. Loopback stays
bound either way, so nothing about using it at the laptop changes.

**The plain command binds loopback only.** That second address hands your Status to
whoever opens it, so it is never the default: a fresh clone, and any machine without
`WASTATUS_ALSO_ON` in its `.env`, binds loopback and nothing else. **The `Also on`
line is how you know you have it**: no such line, no phone.

**Put `WASTATUS_ALSO_ON=tailscale` in `.env` and every start has it**, which is the
fix for the commonest complaint in [RUNBOOK.md](RUNBOOK.md): the phone refusing to
connect after a reboot, because the flag went with it. **Reach the page from your
phone**, below, covers what the phone gets and what it cannot do;
[DECISIONS.md](DECISIONS.md) D-027 and D-044 cover why it works this way.

**Step 4. Make a clip.** In **The clip**, paste the YouTube link, then set the start
and either the length or the end time. Press **Make the clip**. Four steps tick by, a
**Stop** appears beside the button while it works, and then the still appears in the
preview for you to play and scrub through.

**A YouTube Music link works just as well**, and is often the better one to paste. An
auto-generated music upload has a channel like `Release - Topic`, which says nothing,
while the same link carries the real artist, and the card prefers the artist. Paste
the link to **one track**: a playlist or album link is refused, because it names no
single song and the caption would point at nothing. On YouTube Music that means
**Share** on the track rather than on the playlist. A Spotify link cannot work at
all, whatever the tool does: Spotify's audio is DRM protected and yt-dlp refuses it.

Each part of the job is a card that folds, and a folded one still says what is in it
on the right of its header: the window, `Artwork card`, `waveform on`. **Look**,
**Words on the card** and **Extras** are where the title, the second line and the
rest live. On a phone, the moment a clip lands those cards fold themselves away and
the preview comes up the screen. **Clear**, in The clip's header, empties the link,
the window and the words when you want to start something else.

**Optional: put a sticker on it.** Open the **Stickers** card, search for what you
want, click it, and drag it onto the frame. On a phone, **pinch two fingers to size
it and twist them to turn it**: the first finger has to be on the sticker, the second
can be anywhere on the frame, and a twist that lands within a few degrees of square
settles there. Size and Turn do the same job with a mouse, on the one you last
touched, and they follow your fingers while you pinch.

**Searching for a GIF from inside the page** is off until you switch it on. Put a
provider and its key in `.env`:

```
WASTATUS_GIF_PROVIDER=giphy      # or klipy
WASTATUS_GIPHY_KEY=...           # developers.giphy.com, choose API and not SDK
WASTATUS_KLIPY_KEY=...           # docs.klipy.com
WASTATUS_GIF_RATING=pg           # g, pg, pg-13 or r
```

Restart the server and the Stickers card grows a **Drawings / GIFs** toggle. Type,
pick one, and it lands on the frame like any other sticker. The last twenty you pick
are kept and searchable; older ones are dropped, so browsing does not silt up your
shelf. Empty the provider line and the whole thing disappears again, toggle included.

**On GIPHY, take the API key and not the SDK key.** Their form recommends SDK, which
is their own interface components. This tool has its own picker and makes plain REST
calls, so SDK is the wrong key and comes with a licence for something you are not
doing. A GIPHY beta key allows 100 calls an hour, which the page will tell you about
if you ever reach it.

**A GIF gets in two ways on a laptop.** Press **Upload** and pick the `.gif`, or copy
the picture and press Ctrl+V anywhere on the page. One caution that is not this
tool's doing: Chrome's **Copy image** on a web page flattens a GIF to a still, so
save the file first and upload it, or copy the file rather than the image. On a
phone it is the keyboard's GIF tab, in Firefox, see [TASKS.md](TASKS.md) T-024.

**Click a sticker and it stays selected**, wearing a dashed box and its handles,
until you click the frame background to put it down. The cross at the top right
removes it. With a mouse there are two more: a grip at the bottom right to resize
and a handle on a stem above it to turn. A phone gets the cross only, because two
touch targets do not fit on a sticker that size, and pinch and twist already cover
the rest. They are drawn into the video, so press **Make the clip** again to bake
them in. An amber outline means WhatsApp's own header or caption will cover that one.

**Step 5. Send it.** In **Post it**, the caption is the box labelled *Caption, sent
with the video*. Type in it and the edit saves itself; what you see over the frame
above is the same text, drawn where WhatsApp will draw it. The icon inside the box
copies it. Each of the buttons under it says what it does:

- **Load into WhatsApp** opens the Status composer with the clip and the caption in
  place and stops. Switch to that browser and press Send yourself. Nothing has gone
  out until you do.
- **Send it for me** does that last press too.

**When you are done:** press Ctrl-C in that terminal. Nothing else to shut down.

### If something looks wrong

| What you see | What to do |
|---|---|
| The chip at the top right is amber | open it. It names the check that is unhappy, and the WhatsApp Web row carries **start it** and **recheck** |
| The **WhatsApp Web** row is amber | step 2 was skipped, or that Chrome was closed. Press **start it** there, or run step 2 yourself |
| Both post buttons are greyed out | same reason, or another request is already driving WhatsApp. The line under them says which |
| `error: cannot listen on 127.0.0.1:8765` | a page is already serving. Open `http://127.0.0.1:8765`, or start another on `./wastatus.sh serve --port 8790` |
| `./wastatus.sh: No such file or directory` | wrong folder. Do step 1 again |
| The **ffmpeg** row is amber | `sudo apt install ffmpeg`, then press **recheck** |
| The **token provider** row is amber | `bash scripts/setup_provider.sh`, then restart the page |
| The sticker card says the library is not installed | `bash scripts/setup_stickers.sh`, then reload the page |
| The phone cannot open the page, or its address refuses the connection | the page was started without `--also-on tailscale`, so it is listening on loopback only. Look at the startup output: no `Also on` line means no phone. Ctrl-C and start it again with the flag, or put `WASTATUS_ALSO_ON=tailscale` in `.env` so it never happens again |
| Every button says `bad or missing token`, or the chip says `the tool needs you` | the tab was opened before the server was last restarted, and the token belongs to one run of the server. Nothing is stored and nothing is reused, on purpose | **reload the page.** The page now says this in words rather than showing `bad or missing token` |
| Posting says `could not find the photo and video choice in WhatsApp Web` | WhatsApp Web renamed or moved a control. It did on 2026-08-20, when `Photo and video` became `Photos & videos` behind a new **Add Status** button | nothing you can fix from here. [RUNBOOK.md](RUNBOOK.md), **Posting failed** step 3, prints what the controls are called today, and the list to add it to is at the top of `wastatus/post.py` |
| The tailnet address worked yesterday and does not today | the same thing. A restart, a reboot included, drops the flag with the process. It is never remembered |
| The `Also on` line is there and the phone still cannot reach it | Tailscale itself. Run `tailscale status` here and check the phone is listed, and that Tailscale is connected on the phone |

The page takes `--port`, `--cdp-port`, `-o/--out`, `--keep-last` and `--no-open`.
`./wastatus.sh serve --help` lists them.

Prefer the command line, or need a flag the page does not offer? Carry on below.

## Install on a macOS machine

```bash
brew install ffmpeg node git
cd ~/Documents/WhatsApp-Status
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
bash scripts/setup_provider.sh
bash scripts/setup_stickers.sh
```

The provider line clones and builds the proof of origin token provider that YouTube
requires. It takes a few minutes and uses about 209 MB. It runs once per machine.
The tool starts and stops the provider by itself from then on. Since 2026-10-25 it
installs version 1.3.1, the one the yt-dlp plugin in `requirements.txt` is pinned to
(`WASTATUS_POT_VERSION` picks another), with `npm ci`, and it refuses to replace a
folder that is not a checkout of the provider.

### First run on a Mac: the checklist

Every path in the tool already branches on Darwin and the fonts are vendored rather
than taken from the system, but **no run on a Mac is recorded anywhere in this
repository**, so treat the list below as the thing that settles it rather than as a
formality. It takes about twenty minutes, most of it waiting for the provider build.

Swept again on 2026-08-27, by reading rather than by running: every cache, profile,
library and token directory branches on Darwin; the font is vendored and the emoji now come
from the OpenMoji release `setup_stickers.sh` pins rather than from a system emoji
font, so the two machines draw the same clip; the shell scripts hold to
bash 3.2, which is what macOS ships, and use no GNU-only flag; nothing shells out to
a Linux-only tool except through `shutil.which`. Two things are weaker on a Mac
rather than broken, and both already say so where they are used: `port_owner` and the
"a browser is already on this profile" check read `/proc`, and answer "" and None on a
machine without one. One thing is untested rather than weak: `tailscale ip` is found
on `PATH`, which the Homebrew and standalone builds do and the Mac App Store build
does not.

| # | Step | What good looks like | If it fails |
|---|---|---|---|
| 1 | `bash scripts/setup_provider.sh` | ends without an npm error, and `~/Library/Application Support/wastatus/bgutil` exists | the likeliest failure of the lot, and it is a Node build rather than anything of ours. Check `node --version` is 20 or above |
| 2 | `bash scripts/setup_stickers.sh` | 4,495 files under `~/Library/Application Support/wastatus/stickers/openmoji` | needs `curl` and `unzip`, both stock on macOS |
| 3 | `.venv/bin/python -m pytest` | 1,061 passed, 9 skipped: two more skip here than on Linux, one that binds `127.0.0.2` and one that reads `/proc` | a failure here is a genuine portability bug. Record which test |
| 4 | `./wastatus.sh --help` | the usage text | the wrapper uses `.venv/bin/python`, which is correct on macOS |
| 5 | One real clip: `./wastatus.sh <url> --start 0:20 --duration 15` | an mp4 in the working directory, and `ffmpeg` and `yt-dlp` both found | this exercises the provider, the ladder, Pillow and ffmpeg in one go |
| 6 | `./wastatus.sh serve` | the page opens, the health chip reads **All set** | the chip names whichever tool is missing |
| 7 | Place a sticker, then make the clip again | the sticker is in the video | proves the library path resolved on Darwin |
| 8 | Copy the caption | it pastes | `pbcopy` is tried first on macOS, before the Linux helpers |
| 9 | Posting, only if you want it there too | the QR code appears on first launch, then the composer loads | Chrome is looked for at `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome` |

Steps 1 to 7 settle the claim. Post the outcome into the macOS row of
[MEMORY.md](MEMORY.md) Table ME-1, whichever way it goes.

## Install on a fresh Linux machine

```bash
sudo apt install ffmpeg nodejs git python3-venv     # or your package manager
cd ~/Documents/WhatsApp-Status
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
bash scripts/setup_provider.sh
bash scripts/setup_stickers.sh
```

Node must be version 20 or newer. Check with `node --version`.

## Your first run

### Step 1: open a terminal in the project

```bash
cd ~/Documents/WhatsApp-Status
```

### Step 2: get a link and two timestamps

Play the song on YouTube. Note where the good part starts and ends, reading the
numbers off the player, for example `1:10` and `1:25`. Copy the URL.

Ten to twenty seconds works best. Ninety seconds is the hard platform limit.

### Step 3: run it

```bash
./wastatus.sh "https://youtu.be/A6DfGQsdz1Y" 1:10 1:25
```

Keep the quotes around the URL. About 25 seconds later:

```
[1/4] reading https://youtu.be/A6DfGQsdz1Y
[2/4] fetching audio 70s to 85s
[3/4] composing card
[4/4] rendering

clip     out/20260818_sinna-sinna-murugaiyaa_70-85.mp4  (5.6 MB, 15s)
caption  https://youtu.be/A6DfGQsdz1Y

Post the clip with that caption. WhatsApp makes the URL tappable.
(caption copied to the clipboard)
```

### Step 4: watch it before you post

Double click the mp4 in your file manager. Two files were written:

| File | What it is |
|---|---|
| `out/YYYYMMDD_song-slug_start-end.mp4` | the clip |
| `out/YYYYMMDD_song-slug_start-end.caption.txt` | the caption, which is just the link |

The folder keeps the newest 20 clips and quietly deletes older ones, so move
anything you want to hold on to. `--keep-last 50` raises the limit.

Add `--frame` and you also get a full resolution still, which is quicker to look
at than opening a video player.

### Step 5: post it

The tool can post it for you. You need a Chrome running with the debug port open
and WhatsApp Web logged in inside it:

```bash
google-chrome --remote-debugging-port=9222 \
    --user-data-dir="$HOME/.config/chrome-wastatus" https://web.whatsapp.com &
```

Scan the QR code once. That profile stays logged in, so later runs just work. Then:

```bash
./wastatus.sh "https://youtu.be/A6DfGQsdz1Y" 1:10 1:25 --post
```

```
posting  through WhatsApp Web on port 9222
posted   the clip is live, upload took 11s
```

If posting fails the clip is still on disk and the command prints a one line retry.
[RUNBOOK.md](RUNBOOK.md) has the failure index.

### By hand instead

Open web.whatsapp.com, go to Status, choose **Photo and video**, pick the mp4,
paste the caption, send. The caption is on your clipboard already.

To post from the phone instead, get the mp4 across by whichever is easiest:
Telegram Saved Messages sent **as a file** so it is not re-compressed, or a USB
cable into the phone's Movies folder.

`--follow-up` adds a second, text only Status carrying the same link, which
WhatsApp renders with a preview card. It is optional: the caption on the clip is
already tappable.

## Commands you will actually use

| What you want | Command |
|---|---|
| 15 seconds from a start point | `./wastatus.sh "URL" 1:10` |
| A 20 second clip | `./wastatus.sh "URL" 1:10 -d 20` |
| Use the real video, not the artwork card | `./wastatus.sh "URL" 1:10 1:25 --video` |
| Fix an ugly auto title | `./wastatus.sh "URL" 1:10 1:25 --title "Kandha Sashti Kavacham"` |
| Write output somewhere else | `./wastatus.sh "URL" 1:10 1:25 -o ~/Desktop` |
| Check the look without opening the video | `./wastatus.sh "URL" 1:10 --frame` |
| Watch what it is doing | `./wastatus.sh "URL" 1:10 -v` |
| Load it into WhatsApp, and press Send yourself | `./wastatus.sh "URL" 1:10 --load` |
| Post it as well | `./wastatus.sh "URL" 1:10 --post` |
| Use a page instead of the terminal | `./wastatus.sh serve` |
| Reach the page from your phone | `./wastatus.sh serve --also-on tailscale` |
| Leave it running in the background, if you want that | `bash scripts/install_service.sh` |
| Keep more old clips around | `./wastatus.sh "URL" 1:10 --keep-last 50` |
| See every option | `./wastatus.sh --help` |

Timestamps accept `93`, `1:33` and `1:02:03`. With no start given, a `?t=` in the
URL is used.

## Leave it running, instead of starting it each time

**You do not have this, and do not need it.** The page is started by hand. This
section is for the day you want it otherwise; see [DECISIONS.md](DECISIONS.md) D-028
for why it is off.

One command, once:

```bash
cd ~/Documents/WhatsApp-Status
bash scripts/install_service.sh
```

That installs a systemd **user** service. It starts at login, comes back if it
crashes, and survives closing the terminal. It needs no root and writes nothing
outside `~/.config/systemd/user`.

To have it running even when you are logged out, and at boot:

```bash
sudo loginctl enable-linger $USER
```

Afterwards:

| What you want | Command |
|---|---|
| Is it up | `systemctl --user status wastatus` |
| What is it saying | `journalctl --user -u wastatus -f` |
| Pick up code changes | `systemctl --user restart wastatus` |
| Stop it for now | `systemctl --user stop wastatus` |
| Undo the whole thing | `systemctl --user disable --now wastatus && rm ~/.config/systemd/user/wastatus.service` |

**Clips go to `~/wastatus-out`**, not into the project, because a service has no
working directory you can reason about from outside. Set `WASTATUS_OUT` before
running the installer to change that.

**A restart invalidates any tab you had open**, because the token lives for the
length of the process. Reload the page and it gets the new one.

macOS has no `systemctl`. The script says so and stops; the equivalent there is a
launchd plist, which is not written yet.

## Reach the page from your phone

```bash
./wastatus.sh serve --also-on tailscale
```

Loopback stays bound, so nothing about using it at the laptop changes. The page also
appears at your tailnet address, which the phone can open. On this machine that is
`http://100.x.y.z:8765/`, and the startup output prints it for you.

Verified end to end on 2026-08-19, and again on 2026-08-20 after a reboot: both
addresses answer, `app.js` and `app.css` with them, `/api/state` without a token is
still refused with a 403, and the page reports the address it is also on.

**It has to be passed at every start.** The flag lives for the length of the process
and nothing writes it down. On 2026-08-20 a reboot cost an evening for exactly this
reason: **Start the page** was followed literally, the plain command bound loopback
only, and the phone had nothing to open. That walkthrough now names this command
where you read it.

Needs [Tailscale](https://tailscale.com) installed and logged in on both the laptop
and the phone. Without it the command stops with a message rather than binding
something unexpected. You can also pass the address itself, for example
`--also-on 100.64.0.7`.

### Installing Tailscale, once

Needs `sudo`, so it is yours to run and not an agent's.

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up          # prints a link. Open it and log in
tailscale ip -4            # the address --also-on tailscale will bind
```

On this machine, Linux Mint 22.1, the installer reads `UBUNTU_CODENAME` and uses the
Ubuntu `noble` apt repository, with a keyring in `/usr/share/keyrings`. It adds a
`tailscaled` system service, which is Tailscale's own and unrelated to D-028.

On the phone, install Tailscale from the Play Store or the App Store and log in with
**the same account**. Both devices then see each other by their `100.x` addresses,
with nothing opened to the internet.

**On the phone, Download is the filled button** and it carries the size, with the
copy icon inside the caption box beside it: save the mp4, copy the caption, and post
it in the real WhatsApp app. Android's browser saves it to `~/Download`. **Load into
WhatsApp** is still there and still works, filling the composer in the laptop's
browser for you to send when you next sit down; the line under it names the machine
that composer is on. A phone cannot press Send in it, because a Status composer
belongs to the client that opened it.

**One clip already downloaded?** The **Recent** card ticks the ones this device has
saved, so you do not fetch the same 8 MB twice. That tick is per device: the laptop
and the phone each keep their own.

**Downloading to the phone is slow right now**, unexplained, about 700 bytes a
second on the one measured attempt. See [TASKS.md](TASKS.md) T-021 for what is known
and the one test that would settle it.

**Not the whole local network.** Whoever opens the page gets the token that lets it
post to your Status, so a tailnet is the boundary. `--also-on 0.0.0.0` is accepted if
you insist, and is a bad idea.

**Captions:** a link in a Status caption is not tappable when you view your own
Status on the phone you posted it from. It is tappable for everybody else. Check a
caption on a second device, or you will conclude the wrong thing.

## Record every Status in a Google Sheet

Optional, and off unless you set it up. Every Status WhatsApp **accepted** gets a row:
Timestamp, Source, Status, Remarks. One it refused gets none, and one you loaded but
did not send gets none either. The sheet is the record of what went out.

A service account does the writing, so the sheet stays private, is shared with exactly
one robot address, and nothing has to be re-authorised later. In the Google Cloud
console make a project, then, with `gcloud` pointed at the account that owns it:

```bash
P=your-project-id
gcloud services enable sheets.googleapis.com --project=$P
gcloud iam service-accounts create wastatus-writer --project=$P
mkdir -p ~/.config/wastatus && chmod 700 ~/.config/wastatus
gcloud iam service-accounts keys create ~/.config/wastatus/sheets-sa.json \
    --iam-account=wastatus-writer@$P.iam.gserviceaccount.com --project=$P
chmod 600 ~/.config/wastatus/sheets-sa.json
```

If `gcloud` says it does not have permission, it is signed in as the wrong account.
`gcloud auth list` shows them all and `gcloud auth login <address>` adds one.

Then open your sheet, press **Share**, paste
`wastatus-writer@your-project-id.iam.gserviceaccount.com`, and give it **Editor**.
That address is the only thing the sheet is shared with.

Last, three lines in `.env`. The id is the long string in the sheet's own URL,
between `/d/` and `/edit`:

```
WASTATUS_SHEET_ID=<the long string in your sheet URL, between /d/ and /edit>
WASTATUS_SHEET_KEY=~/.config/wastatus/sheets-sa.json
WASTATUS_SHEET_TAB=Sheet1
```

**Nothing here can stop a post.** A sheet that cannot be reached costs the row and
says so in `logs/wastatus.log`. If the log says the sheet refused the credential, it
names the address to share the sheet with, and that is almost always the fix.

The key file is a real credential. It lives outside the repo on purpose, mode 600,
and must never be committed.

## If it fails

Run the same command again. The download depends on YouTube's anti bot behaviour
and a retry often just works.

If it keeps failing, the logs will tell you what happened:

```bash
tail -1 logs/runs.jsonl | .venv/bin/python -m json.tool   # a summary of the last run
tail -40 logs/wastatus.log                               # the full error output
```

[RUNBOOK.md](RUNBOOK.md) maps the symptom to the fix.

## Where things live

| Thing | Path |
|---|---|
| Project | wherever you cloned it; the maintainer's copy is `~/Documents/WhatsApp-Status` |
| Remote | `https://github.com/PalWorks/snipshare-whatsapp-status-maker` (public, since 2026-10-25) |
| Python environment | `.venv/` (not in git) |
| Output | `out/` (not in git) |
| Bundled fonts | `assets/fonts/` |
| Token provider, Linux | `~/.local/share/wastatus/bgutil` |
| Stickers, Linux | `~/.local/share/wastatus/stickers`, with your own in `mine/` |
| Token provider, macOS | `~/Library/Application Support/wastatus/bgutil` |
| Logs | `logs/` (not in git), or `journalctl --user -u wastatus` under the service |
| Sticker thumbnails, cached | `~/.local/share/wastatus/stickers/cache`, safe to delete |
| Service unit | `~/.config/systemd/user/wastatus.service` |
