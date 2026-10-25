# Playbook

Step by step procedures. For production style failures see
[RUNBOOK.md](RUNBOOK.md). For first time setup see
[LOCAL_SETUP.md](LOCAL_SETUP.md).

## Change the look of the clip

1. Open [wastatus/compose.py](wastatus/compose.py). All layout lives in design
   coordinates against a 1080x1920 canvas near the top of the file, plus the
   positions inside `_draw_text_layer`.
2. Edit design coordinates only. `SUPER` handles the supersampling.
3. If you move the waveform, change `WAVE_TOP` or `WAVE_H` in `compose.py`.
   `render.py` imports them, so both modes follow automatically.
4. Render with `--frame`, which writes a full resolution still next to the mp4:

```bash
./wastatus.sh "https://youtu.be/A6DfGQsdz1Y" 1:10 1:25 --frame
```

5. Open the `.png`. Compare against a Latin title and a Tamil title, because line
   wrapping differs. Pass `--frame 0:02` to inspect a specific moment, which is
   how you check the zoom start or a fade.
6. Check video mode too. Its text sits lower, and since 2026-08-25 it draws
   everything card mode draws: the label above the words and a line of top text
   under WhatsApp's header, both of which move the frames rather than sitting on
   them. A change that looks right on the card can still collide there.
7. Run `pytest tests/test_safe_zone.py`. It measures the highest and lowest pixel
   the text layer paints, across one, two and three line titles and every artwork
   shape, and fails if anything reaches `SAFE_TOP` or `SAFE_BOTTOM`, the bands
   WhatsApp fills with its own header and caption. If it fails, move the block
   rather than shortening the text.
8. If you touched the card's geometry, remember the card's **bottom** is the fixed
   anchor and its top moves with the artwork's aspect ratio. `tests/test_artwork.py`
   pins that, along with the padding bar detection.

## Post a clip

```bash
./wastatus.sh "https://youtu.be/A6DfGQsdz1Y" 1:10 1:25 --post
```

Needs a Chrome on the debug port with a logged in web.whatsapp.com tab. Any debug
browser holding one will do; `--port N` sets which to try first. Add `--follow-up`
for the text only second Status.

`--load` instead of `--post` stops with the composer open so the Send press is
yours. That is what the page does by default, see [DECISIONS.md](DECISIONS.md) D-020.

To clear the tray first, which is irreversible:

```bash
.venv/bin/python scripts/wa_post.py delete-all --yes
```

To see what will be posted without posting it, load the composer and stop:

```bash
.venv/bin/python scripts/wa_post.py video out/<clip>.mp4 \
    --caption-file out/<clip>.caption.txt
.venv/bin/python scripts/wa_post.py shot /tmp/wa.png     # look at it
.venv/bin/python scripts/wa_post.py send                 # or: cancel
```

## Change the local page

The page is `wastatus/web/index.html`, `app.css` and `app.js`, served by
`wastatus/serve.py`. There is no build step: edit and reload.

1. Run it with `./wastatus.sh serve --no-open -v`.
2. Change a file, reload the browser. The server reads the page off disk per
   request, so only Python changes need a restart.
3. Look at it in both themes and both widths before calling it done.
   `scripts/shot.py` captures the real page in the debug Chrome without a browser
   window getting in the way, which is how this design was reviewed:

```bash
.venv/bin/python scripts/shot.py http://127.0.0.1:8765/ /tmp/wide.png --full
.venv/bin/python scripts/shot.py http://127.0.0.1:8765/ /tmp/dark.png --dark --full
.venv/bin/python scripts/shot.py http://127.0.0.1:8765/ /tmp/narrow.png --width 430 --full
.venv/bin/python scripts/shot.py http://127.0.0.1:8765/ /tmp/guides.png --click "#guides"
```

4. A screenshot shows you the layout, not the behaviour. For anything interactive,
   drive it: open a tab over CDP, click the thing, and read the DOM back. That is how
   the seek slider was proven to move the video and how the caption editor was proven
   to reach the disk. `post.Page.__new__` plus a `Target.createTarget` gives you a
   session on your own tab, the way `scripts/shot.py` does it.
5. `pytest tests/test_serve.py` covers the routes and every guard. Add to it when
   you add an endpoint, especially anything that writes or posts.

**Do not** put pipeline logic in `serve.py`. The page calls `pipeline.produce`; if it
needs something the engine does not give it, change the engine.

**Do not** make sending the default. See [DECISIONS.md](DECISIONS.md) D-020.

**Watch the specificity.** `app.css` defines base rules like `.hint` and `.chips`
further down the file than the sections that customise them, so a single class
override written earlier loses silently and the spacing you wrote never appears. Two
rules were dead this way. Put the declaration next to the base rule, and check what
the browser computed rather than what the file says:

```js
getComputedStyle(document.querySelector(".hint--window")).marginBottom
```

## Drive the real page, because a screenshot only shows the layout

Anything interactive has to be driven. Two bugs on 2026-08-19 were invisible in a
screenshot: a deleted clip staying in the Recent strip, and the "Nothing yet" line
never appearing on a first run.

Open a tab on your own server over CDP, run a snippet in it, read the result back.
`scripts/shot.py` shows the connection: `post.Page.__new__` plus a
`Target.createTarget` gives you a session on a tab you own.

```js
(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  document.querySelector(".tile").click();       // load a clip
  await sleep(1200);
  const el = document.getElementById("download");
  return { classes: el.className, left: Math.round(el.getBoundingClientRect().left) };
})()
```

Serve a scratch output folder, not `out/`, when a check deletes things:

```bash
./wastatus.sh serve --port 8799 --no-open -o /tmp/scratch/out --also-on 192.168.1.10
```

**A non-loopback bind is how you test the phone layout**, because the page decides
which button is primary from the peer address. Keep the window short: the page hands
its token to whoever loads it.

**It is never remembered between runs.** Every start that wants a second address
passes the flag again, D-027, so a check that survives a restart does not exist. If a
phone or an away-layout check suddenly reads as broken, look at `ss -tlnp | grep 8765`
first: one socket means the flag was dropped, not that the code regressed.

**Watch the sentinels.** `recentSignature` uses `null` for "rebuild me", because `""`
is the real signature of an empty clip list and using it meant an empty strip never
repainted. Any "has this changed" cache in this page needs a sentinel that cannot
collide with a real value.

## Stop a render, or delete a clip

From the page: **Stop** beside **Make the clip** while it works, **Delete** in **Post it** on
two presses. From a terminal, if the page is not to hand:

```bash
TOKEN=$(curl -s http://127.0.0.1:8765/ | grep -o 'data-token="[^"]*"' | cut -d'"' -f2)
curl -s -H "X-Wastatus-Token: $TOKEN" -H "Content-Type: application/json" \
    -d '{"id":"<task id>"}' http://127.0.0.1:8765/api/cancel
```

Stopping kills the child's whole process group and `pipeline.produce` removes the
half written mp4. Check nothing survived:

```bash
pgrep -fa "yt_dlp|ffmpeg"      # should find nothing of ours
ls -d /tmp/wastatus-*          # no work directory left
```

A post cannot be stopped, by design: see [DECISIONS.md](DECISIONS.md) D-025. Cancel
it in WhatsApp itself.

## Change something about stickers

The library is not in the repository. `scripts/setup_stickers.sh` puts it in the same
data directory as the token provider, and `WASTATUS_STICKER_DIR` moves it, which is
what the tests use.

1. **The picker or the search** is `stickers.search`. Matching is prefix-on-a-word,
   not substring, so `om` finds `om` rather than every emoji whose tags contain
   `bloom`. The opening shelf is a hand written list of hexcodes, because catalogue
   order opens on sixty grinning faces. `search` de-duplicates that list with
   `dict.fromkeys`, because a hand written list acquires repeats: `1F4FF` was in it
   twice and cost a slot. A test guards the list itself.
2. **Adding your own** is `stickers.save_upload`, one file per request, and the page
   loops over the picked files. One file lands on the frame, several land on the
   shelf, see D-035. Do not batch them into one request: a refusal has to name its
   file and leave the others uploaded. The same function serves the `paste`
   listener, which is how a GIF from a phone keyboard arrives, see D-036.
3. **Animated ones are a second mechanism.** `stickers.motion` answers from the file
   on disk, `stickers.split` divides a placed list, `compose` pastes the still half
   and `render` takes the moving half as looping inputs. In card mode they are
   overlaid **before** `zoompan`, or they would sit still while the pasted ones
   drift outwards. Anything animated is stored as GIF because this ffmpeg refuses an
   animated WebP.
4. **The way one is drawn** is `stickers.paste`, onto whatever canvas it is handed.
   Coordinates are fractions, so it works on the 1620 card and the 1080 overlay with
   no scale factor. Do not add one.
5. **The way one is placed** is `paintDecals` and the three `onFramePointer*`
   handlers in `app.js`. Rebuild the layer only when the set of stickers changes:
   rebuilding during a drag destroys the element holding the pointer capture, and
   the sticker stops moving. `placeDecal` and `repaintMark` touch one element's
   style and dataset, which is why they are safe mid gesture.
6. **Anything the preview draws that the renderer does not paste is a bug**, unless
   it is a handle you are holding. A CSS drop shadow was the first kind and is gone.
   The dashed selection box is the second, and its handles are the third: they are
   drawn on the **selected** sticker and on no other, and nothing is selected until
   you pick one, so the frame still spends its resting life showing only what the
   viewer will see. The 1.4 second fade this rule used to rely on is gone; a handle
   that fades is a handle you cannot click. See D-034 as amended, and D-038. If you
   add another marker, tie it to the selection rather than to a timer.
7. **Thumbnails** are `stickers.thumbnail`, cached under `<sticker dir>/cache/<w>/`.
   Only the widths in `THUMB_WIDTHS` are made. If you add one, the page has to ask
   for it: nothing generates on demand at an arbitrary size, on purpose.
8. `pytest tests/test_stickers.py` covers the ids, the numbers, the search, the
   thumbnails and the coordinate claim. Add to it before changing the arithmetic.

## Change encoder settings

Edit `_encode_args` in [wastatus/render.py](wastatus/render.py). Both modes share
it, so a change applies to both. Verify size and duration afterwards:

```bash
ffprobe -v error -show_entries format=duration,size -of default=nw=1 out/*.mp4
```

Target is 4 to 6 MB for 15 seconds. WhatsApp re-encodes on upload, so pushing
quality higher buys nothing.

## Fix a broken download

This is the failure you will hit most often. Full context in
[docs/extraction.md](docs/extraction.md).

1. Reproduce and read the failure list. `fetch.download_section` reports every
   client it tried and why each failed.
2. Find out what is actually available:

```bash
.venv/bin/python -m yt_dlp --no-playlist --remote-components ejs:github \
  --extractor-args "youtube:player_client=mweb" --list-formats "<URL>"
```

3. Repeat for `web_safari`, `android`, `tv_simply` and with no client override.
   You are looking for a client that lists a muxed format, not storyboards.
4. Try that combination for real, with a section, before touching the code:

```bash
.venv/bin/python -m yt_dlp --no-playlist --remote-components ejs:github \
  --extractor-args "youtube:player_client=<C>" -f <FMT> \
  --download-sections "*0:01:10-0:01:25" -o "/tmp/probe/c.%(ext)s" "<URL>"
```

5. Only when a combination produces a real file, add it to `STRATEGIES_AUDIO` or
   `STRATEGIES_VIDEO` in [wastatus/fetch.py](wastatus/fetch.py). Order matters:
   cheapest and most reliable first.
6. Record the measurement in the table in
   [docs/extraction.md](docs/extraction.md). That table is the reason the next
   debugging session is short.

## Add a title cleanup rule

1. Add the pattern to `_NOISE` in
   [wastatus/translit.py](wastatus/translit.py).
2. Verify against a batch, not one string:

```bash
.venv/bin/python -c "
from wastatus.translit import clean_title
for t in ['<title 1>', '<title 2>']:
    print(repr(clean_title(t)))"
```

3. Check you have not eaten a real song name. The rules are aggressive by design
   and the failure mode is a title that lost its subject.

## Add a CLI flag

1. Add it to `build_parser` in [wastatus/cli.py](wastatus/cli.py) with help text
   that reads as a sentence.
2. Thread it through as a keyword argument. Do not read `args` from inside
   `compose`, `render` or `fetch`.
3. Add a row to the options table in [README.md](README.md), and to the command
   table in [LOCAL_SETUP.md](LOCAL_SETUP.md) if it is one the owner would use.
4. If it changes what a run does, record it on the run with `run.set(...)` so the
   json log stays a faithful account.

## Run it as a service, or stop doing so

**Not installed, on purpose.** Ask before you install it: D-028 records that the
owner starts the page by hand.

```bash
bash scripts/install_service.sh                        # loopback only
bash scripts/install_service.sh --also-on tailscale    # and from a phone
systemctl --user restart wastatus                      # after changing the code
systemctl --user disable --now wastatus                # stop and forget it
```

It is a user unit, so no root and nothing outside `~/.config/systemd/user`. Clips go
to `~/wastatus-out` unless `WASTATUS_OUT` says otherwise, because a service has no
working directory worth reasoning about. A restart rotates the token, so any tab left
open needs a reload.

**Code changes do not take effect on their own.** The page is read from disk per
request, so HTML, CSS and JS are live; Python is not. Restart the service.

## Change the extension or the renderer

1. Read [docs/extension.md](docs/extension.md) and D-080 to D-086.
2. Parser changes go in `src/media.js` only, with a Node test in
   `src/test/media.test.js` built from ffmpeg-made media, never a capture of a
   real video, which is somebody else's to publish.
3. A constant shared with the Python side (the 90 seconds, WhatsApp's labels, chunk
   sizes, the default renderer) is checked by `tests/test_extension.py`; change both.
4. `pytest`, then a local renderer and `scripts/extension_check.py` against it, in
   both modes, then with `--throttle 800 --restart-at uploading` and `--stop-at
   rendering` if the job's flow changed.
5. In the owner's Chrome: reload the extension on `chrome://extensions`, reload the
   YouTube tab, make a clip, **Load into WhatsApp**, and close the composer.
6. `scripts/deploy.sh` for a renderer change (ask first, AGENTS.md), then
   `extension_check.py` against production.
7. People who use the extension update their copy of `src/` and press reload
   on its card; say so if the change needs it.

## Release

A release of the tool is a commit; a release of the hosted site is a commit plus
`scripts/deploy.sh` (DEPLOYMENT.md). Updated **2026-10-25T15:11:42+05:30**: the
repository is public (D-099), so everything committed is published.

1. `git status --short` must show no `.venv/`, `out/`, `logs/`, `dist/`, `.env` or
   `.publish-deny` entries
2. `.venv/bin/python -m pytest` must pass, `tests/test_publishable.py` included, with
   `.publish-deny` present so the private strings are checked too; then run the
   manual set in [TESTING.md](TESTING.md), and `scripts/extension_check.py` against a
   local renderer if `src/` or the renderer changed
3. `gitleaks dir .` over what is about to be committed finds nothing outside the
   git-ignored files
4. Add a dated entry to [CHANGELOG.md](CHANGELOG.md)
5. Commit with a message that says what changed and why, in the style of the
   existing history, signed off (`git commit -s`, CONTRIBUTING.md)
6. Move any resolved item out of [TASKS.md](TASKS.md), and record any new fact
   about a platform in [MEMORY.md](MEMORY.md) or
   [docs/extraction.md](docs/extraction.md)
7. Push only with the owner's say so (AGENTS.md, "Ask first"). The public remote is
   `PalWorks/snipshare-whatsapp-status-maker`; the private `PalWorks/whatsapp-status-maker` keeps the older
   history

## Roll back

```bash
git log --oneline
git revert <sha>
```

For the local tool there are no migrations and no state, so a revert is complete.
The hosted site has a database and a deployed copy: roll it back as
[DEPLOYMENT.md](DEPLOYMENT.md), **Roll back**, says. If the
provider install is suspect, delete it and re-run
[scripts/setup_provider.sh](scripts/setup_provider.sh); it holds no data worth
keeping.

## Set up on the other machine

See [LOCAL_SETUP.md](LOCAL_SETUP.md). The short version is a virtualenv, the
requirements file, `brew install ffmpeg node git` on macOS, and one run of the
provider setup script.
