# Runbook

Symptom to fix. The download path is the fragile part; everything else is
deterministic.

## SnipShare, the hosted page

### Table RB-4: what the page says, and what to do

| It says | Why | Do |
|---|---|---|
| Making a clip needs the SnipShare extension in this browser | the page asked the extension and nobody answered: not installed, disabled, or built for another site | `/install`; on the owner's machine, the copy in `dist/` is the one built for the site, not `src/` |
| Your SnipShare extension is version X | an older copy | load the new zip from `/install` and press reload on `chrome://extensions` |
| The extension stopped answering | Chrome stopped its worker, or it was reloaded, while it worked | reload the page and make the clip again; nothing was counted |
| That is 20 in an hour from this browser | the extension's own pace | wait the minutes it says |
| You have made today's 10 clips | the day's limit | midnight UTC; the admin can raise `WASTATUS_CLIPS_PER_DAY` |
| SnipShare is at its limit for this hour | 60 renders across everybody | wait; an alert told the owner |
| Google sign-in cannot be reached | the server could not fetch Google's keys | try again in a minute; if it lasts, the container's outbound network |
| Your request is with the operator | not approved yet | the admin approves on `/admin` |
| Sign in again | the session ended or the account was suspended | sign in |

The capture and WhatsApp messages from Table RB-3 below apply on the page as well,
under **Make the clip** and **Load into WhatsApp**.

### The server

```bash
scripts/deploy.sh --check
ssh "$WASTATUS_DEPLOY_HOST" 'cd /opt/snipshare/deploy && docker compose logs --tail 100 app'
ssh "$WASTATUS_DEPLOY_HOST" 'cd /opt/snipshare/deploy && docker compose logs --tail 30 tunnel'
ssh "$WASTATUS_DEPLOY_HOST" docker exec snipshare-app tail -50 /data/logs/wastatus.log
ssh "$WASTATUS_DEPLOY_HOST" 'cd /opt/snipshare/deploy && docker compose exec app python -m wastatus hosted user list'
```

Alerts arrive in the owner's Chat space, at most once per kind per hour; the admin
page's **Failures** table and the morning digest say what has been failing and on
which versions. Many capture failures from several people in an hour usually means
YouTube changed its player (D-083); load failures carry the step WhatsApp refused
at. A 502 or 1033 from Cloudflare means the tunnel cannot reach the app or is down:
`docker compose ps`, then the tunnel's log.

## The extension's popup and the hosted renderer

**Start with what the popup says.** Every failure there is written to be acted on,
and the ones that can be tried again have **Try again**, which carries on from the
step that failed: a capture that is stored is not read from YouTube twice, an
upload resumes from what the renderer holds.

### Table RB-3: what the extension says, and what to do

| It says | Why | Do |
|---|---|---|
| Reload this page once | the YouTube page was open before the extension was installed or updated, so nothing is recording in it | reload; the extension listens from the moment a page loads |
| Wait for the video to start | the player has not loaded the video yet | press play, then the button again |
| Waiting for the ad to finish | it waits for ads, up to five minutes in all, and that time does not count against reading the video | skip it if you can |
| YouTube stopped sending the video | the player read nothing new for 60 seconds before the window was covered (since D-100; a slow but steady line is let finish, up to 10 minutes) | reload the YouTube page, then Make my clip again |
| This page plays its video in a way the extension cannot read yet | YouTube has moved MediaSource into a worker, which the page hooks cannot see | needs code: the hooks have to follow it into the worker, D-083 |
| The renderer did not accept your access token | revoked, or mistyped | a new token from the owner, in Settings |
| The connection kept dropping | eight failures in a row on one step | Try again; nothing already sent is sent twice |
| The renderer no longer has this clip | it expired (an hour), or the renderer was rebuilt | Try again sends the stored files afresh |
| The renderer restarted before this clip was finished | a deploy or a crash while it rendered | Try again |
| WhatsApp Web is not signed in | the QR code is waiting in that tab | scan it, then Load into WhatsApp again |
| A Status is already open in WhatsApp | a composer from before is still open | close it or send it, then try again |
| WhatsApp has moved its "Photos & videos" choice | WhatsApp renamed a control | the lists at the top of `wastatus/post.py` and in `src/whatsapp.js`; a test keeps them equal |

### The renderer

```bash
scripts/deploy.sh --check                                   # running? healthy? which revision
ssh "$WASTATUS_DEPLOY_HOST" docker logs --tail 100 snipshare-app
ssh "$WASTATUS_DEPLOY_HOST" docker exec snipshare-app tail -50 /data/logs/wastatus.log
ssh "$WASTATUS_DEPLOY_HOST" docker exec snipshare-app tail -5 /data/logs/runs.jsonl
curl -s "$WASTATUS_DEPLOY_SITE/api/v1/health"
```

`runs.jsonl` has one record per clip with `user`, `job`, the window, the stage
timings and, on a failure, the error. A refused request is logged as `hosted
refused METHOD PATH: status message`; a 401 is not, because scanners send those all
day. 502 or 524 from Cloudflare means the container is down or a request took over
100 seconds: check the container first. A full disk refuses new uploads with 507;
the janitor clears expired work every minute.

### Checking it end to end

`scripts/extension_check.py` drives the real extension in a throwaway Chrome for
Testing and reports each phase with its time, see [TESTING.md](TESTING.md).
`--throttle 800` and `--restart-at uploading` reproduce a poor connection and Chrome
stopping the worker.

## The GIF picker will not work

| Symptom | Cause | Fix |
|---|---|---|
| No **Drawings / GIFs** toggle in the Stickers card | the feature is off, which is the default. Either `WASTATUS_GIF_PROVIDER` is empty or the key for the provider it names is | fill both in `.env` and **restart the server**: settings are read at startup |
| No **GIPHY / KLIPY** chooser under that toggle | it is drawn only with more than one key configured, only while the GIF shelf is showing, and only above 901 pixels wide. On a phone it is deliberately absent | fill both keys in `.env`. On a phone, `WASTATUS_GIF_PROVIDER` is the only way to choose |
| The chooser went back to the other provider after a restart | **not a bug.** It switches for the session and never writes `.env`, which holds your API keys | change the word in `.env` to move the default |
| GIF thumbnails look soft | a preview sized for a phone drawn in a desktop cell | the page asks for the bigger rendition above 901 pixels, `/api/gifs?big=1`. If they are soft on a wide screen, check that parameter is being sent |
| `that GIF key was refused` | wrong key, or a GIPHY **SDK** key where an API key is needed | make a new one at developers.giphy.com choosing **API**. The SDK is their own interface components, which this tool does not use |
| `the GIF service is rate limiting this key` | a GIPHY beta key allows **100 calls an hour** | wait, or switch `WASTATUS_GIF_PROVIDER` to `klipy` for the rest of the hour |
| Thumbnails are blank cells | the preview route is answering 403. It takes the token as `t=` because an `<img>` cannot send a header | check `/api/gif?id=<id>&t=<token>` returns 200. This exact bug shipped and was fixed on 2026-08-21, T-029 |
| `that result is no longer on offer` | the page is showing an older search than the server remembers. Only the last search is on offer | search again and pick from the new results |
| A picked GIF vanished from the shelf | **not a bug.** Twenty are kept and the oldest drop off, D-043. Uploads are never pruned | upload it if you want it kept for good |

## When a link is refused before anything is downloaded

| It says | What it is | What to do |
|---|---|---|
| `that link is a playlist ... not one track` | a playlist or album link, which names no single track. It used to be accepted and put `https://youtu.be/PL...` in the caption, a link that resolves to nothing, T-027 | open the song itself and paste its own link. On YouTube Music that is **Share** on the track, not on the playlist |
| `[DRM] The requested site is known to use DRM protection` | a Spotify link, or anything else with protected audio. yt-dlp refuses on sight and there is no route round it | find the song on YouTube or YouTube Music and paste that. T-028 has the research, closed as not worth automating |

**A YouTube Music link is not a special case.** `music.youtube.com` is the same
extractor and needs nothing, and it is the better link to paste: a `- Topic` upload
carries the real artist where the channel says only `Release - Topic`.

## First response to any download failure

Run the same command again. YouTube's anti bot behaviour is probabilistic and a
plain retry often succeeds. If two retries fail, start with the logs.

```bash
tail -1 logs/runs.jsonl | .venv/bin/python -m json.tool   # which stage, which strategy, what error
tail -40 logs/wastatus.log                               # the full yt-dlp or ffmpeg output
```

The run record tells you where it stopped and which extraction strategy was in
play. The text log has the complete subprocess output, which is the part the
on screen error deliberately truncates. Then work through the entry below that
matches.

Two things worth grepping when the download path feels flaky rather than broken:

```bash
grep -c '"status": "failed"' logs/runs.jsonl              # how often lately
grep -o '"client": "[^"]*"' logs/runs.jsonl | sort | uniq -c   # is mweb still winning
grep "fell through" logs/wastatus.log                     # the ladder degrading
```

A `fell through` warning means an earlier ladder entry has stopped working. The
tool still succeeded, but it is the signal that arrives before an outright failure.

## Table RB-1: Failure index

| Symptom | Cause | Fix |
|---|---|---|
| `no player client could deliver this video` | every client in the ladder failed | see **Ladder exhausted** |
| `PO token provider missing` | provider not installed, or node absent | run `bash scripts/setup_provider.sh` |
| `HTTP Error 403: Forbidden` in the failure list | that client's media URL is gated | expected for some clients, the ladder continues. Only a problem if all fail |
| `Requested format is not available` | that client listed no usable formats | expected, the ladder continues |
| `ffmpeg exited with code 8` | ffmpeg got a 403 on a media URL | same as 403 above |
| `ffmpeg not found on PATH` | ffmpeg missing | Linux: install from your package manager. macOS: `brew install ffmpeg` |
| `the video is Ms long, so a clip starting at Ns would be empty` | the start itself is past the end | move the start back. A window that merely *ends* past the end is not an error: it is brought back to the video's last second and the corrected numbers come back in the boxes |
| `Ns exceeds the 90s WhatsApp Status limit` | window too long | shorten it, the platform will not take it |
| The composer never opens for a file that exists | WhatsApp is refusing the media, silently. It is the size, not the length: the line is **10 MiB**, bisected on 2026-08-20, and every probe was the same 90 seconds | the tool keeps output near 10 MB and says so on screen when a clip goes over, so suspect a file made by hand or by an older version |
| `WhatsApp refused the Status` | WhatsApp took the file but never accepted the post. It shows in the tray on the web client, has no views, and is not on your phone | delete it in the browser, then post again. If the same file is refused twice, render it afresh: a re-send reuses the first upload's media key, which is the most likely reason, D-071 |
| `WhatsApp had still not accepted the Status after Ns` | it is written down but unanswered | it may yet go out. Look at its view count before posting it again, so you do not end up with two |
| `no record of the Status appeared` | Send was pressed but nothing was written | look at the browser. The composer may not have been the one the tool thought it was |
| The log says whether a Status was accepted is `unconfirmed` | this WhatsApp Web keeps no message store the tool can read | the post may well have gone out. Check its views. If this is permanent, WhatsApp has reshaped its storage and `post.STATUS_DB` needs the new name |
| Command finishes but the shell never returns | a resident clipboard helper holding the pipe | fixed in `caa2600`. If it recurs, check any new `Popen` call sets `stdout` and `stderr` |
| Tamil title comes out as `cinnnnnn` | aksharamukha failed to import, fell back to Unidecode | see **Transliteration degraded** |
| Card text clipped or overlapping | layout change without checking both modes | see [PLAYBOOK.md](PLAYBOOK.md), render and look at a frame |
| First ever run takes minutes | the JS solver is being fetched from GitHub and cached | one time, let it finish |
| An older clip has disappeared from `out/` | retention pruned it, newest 20 are kept | raise `--keep-last`, or move clips you want to keep |
| Card looks soft | artwork fell back to `hqdefault`, 480x360, logged as a warning | `--video` for that song |
| `logs/` is missing | the directory could not be written | logging never blocks a clip; check permissions or set `WASTATUS_LOG_DIR` |
| `no Chrome answering on 127.0.0.1:9222` | no browser on that debug port | start one with `--remote-debugging-port=9222`, or pass `--port`. See **Chrome will not open its debug port** |
| `port N is only half open` | something else already had that port on IPv4, so Chrome bound `[::1]` only and printed a listening address anyway | see **Chrome will not open its debug port** |
| `no WhatsApp Web tab is open in it. That one is chrome, profile X` | right port, **wrong browser**. `profile X` is whose it actually is | if that profile is not yours, the browser you meant is somewhere else. See **Chrome will not open its debug port** |
| `the posting profile is already open in a browser on debug port N` | Chrome hands a second launch on one profile to the first and exits, so this launch would expose nothing | use port N, or close that window first. The page adopts it for you |
| `the WhatsApp Web tab is not logged in` | the QR screen | scan it in that browser, then rerun |
| `timed out waiting for the media composer` | WhatsApp Web took the file but never opened the editor. Historically a relative path, which Chrome accepts and ignores; now impossible, the driver resolves it | rerun once, then see **Posting failed** |
| `no such file to post` | the clip path does not exist from here | check the path; the driver resolves relative ones against the current directory |
| `could not find a control labelled 'Photo and video'` | WhatsApp Web changed its interface | see **Posting failed** |
| `the Status was still uploading after 240s` | a big clip, a slow link, or a stuck upload | check the browser, it may yet finish. The clip is on disk either way |
| Exit code 3 | the clip was produced but posting failed | the printed retry line reposts it without re-rendering |
| Two Statuses went out from one run | a composer was left loaded by an earlier run, and the composer sends every file it holds | fixed: `load_video` backs out of an open composer first. If it recurs, `wa_post.py cancel` |
| `--video` output looks soft | that video had no HLS rendition, so the ladder fell through to format 18 at 360p, upscaled to 1080 wide. The run log's `client` and `format` say which one won | nothing to fix: it is YouTube's to offer. Use card mode for that song, whose pixels are our own 1080p card. See [DECISIONS.md](DECISIONS.md) D-023 |
| `yt-dlp gave up after 300s` | the download wedged rather than failed. Usually a dropped connection | run it again. The ceiling exists so a stalled fetch fails instead of hanging the page forever |
| `fell through to X after N failed attempt(s)` | an earlier ladder entry did not produce a file | **expected in video mode**: the ladder tries the HLS renditions first and most videos do not have them, which costs about 2 seconds. Also expected while `web_safari` is dead. Worth acting on only if the entry that fails is `mweb/18`, which is the one everything depends on |

## The preview does not follow what I type

| Symptom | Cause | Fix |
|---|---|---|
| Nothing happens when a word changes | there is no clip on screen. The preview redraws a clip's own picture, so it needs one | make the clip once. After that the words follow your typing |
| `this clip was made before the live preview existed` | the picture the words are drawn over is kept at render time, and clips made before 2026-08-22 have none | make that clip again. Nothing else about it changes |
| The preview updates but the waveform is missing | **not a bug.** A card clip's waveform is drawn by ffmpeg from the audio and a still cannot have one, so that band is empty. This is a preview of the words | press **Make the clip** to see the finished frame |
| The band says the clip still has the old words, and it is right | that is what it is for. The file on disk is not touched until you press the button | press **Make the clip** when the words are what you want |
| The preview will not go away | the words in the boxes still differ from the ones in the clip. Press play and it hides while the video runs | clear the box, or make the clip |
| It is slow on every keystroke | it waits 400 ms after typing stops, and a card takes about 0.9s to draw. A video takes 0.1s | nothing. If it is much slower than that, check `logs/wastatus.log` for a preview traceback |

## Deleting statuses

`wa_post.py delete-all --yes` removes every Status on the account. It is
irreversible and there is no undo, which is why the flag is required and why the
command prints how many it removed. Each pass reopens the viewer and deletes
whichever Status is first, so no index can go stale underneath it.

## The local page will not work

| Symptom | Cause | Fix |
|---|---|---|
| `cannot listen on 127.0.0.1:8765` | another `wastatus serve` is running | use it, or `--port` |
| The page loads but every action says `bad or missing token` | the tab was left open across a server restart, so it holds a dead token | reload the page |
| Thumbnails are blank | the frame file is missing, or the media URL lost its `t` parameter | make the clip again with the current version |
| A render never finishes | it is the pipeline, not the page. The stage name tells you where | [RUNBOOK.md](RUNBOOK.md) above, and `logs/wastatus.log` |
| Both post buttons are disabled | no logged in WhatsApp Web tab in any debug browser | press **start it** on the orange chip, or start Chrome as in [LOCAL_SETUP.md](LOCAL_SETUP.md) and press **recheck** |
| Both post buttons are disabled and the line says "being driven by another request" | a load or a send is in flight, here or in another tab | wait for it, or cancel the composer in WhatsApp. One at a time is deliberate: the composer sends every file it holds |
| `WhatsApp is already being driven by another request` (409) | same | same |
| The seek slider does nothing | the media route stopped answering byte ranges, so the browser cannot ask for a later part of the file | check `Accept-Ranges` and a 206 on `/api/clip`. `tests/test_serve.py::TestSeeking` covers it |
| The caption says something other than `saved` under the frame | the edit did not reach the disk. Posting is blocked in that state on purpose, rather than sending the previous caption | read the message, it is the server's own words. Over 1024 characters is refused |
| `start it` does nothing | no Chrome or Chromium on PATH, or it started and the QR screen is waiting | check for a new browser window, and scan the code. Then press **recheck** |
| The **WhatsApp Web** health row is amber and says a Status choice has moved | the once per run control check found the Add Status menu offering something it does not recognise, T-026 | the row names what the menu actually offers. Add that wording to `PHOTO_ITEM` or `TEXT_ITEM` at the top of `wastatus/post.py`, then restart the server: the answer is cached for the life of the process |
| A sticker's handles will not respond, or only the cross is there | the browser is reporting itself as a touch screen, `(hover: none) and (pointer: coarse)`, which drops resize, rotate and both sliders by design, D-038 | check `matchMedia("(pointer: coarse)").matches` in the console. On a real laptop it is false. Pinch and twist do the same two jobs where it is true |
| `could not find the photo and video choice in WhatsApp Web` | WhatsApp renamed or moved the Status controls. It did exactly this on 2026-08-20, `Photo and video` becoming `Photos & videos` behind a new **Add Status** button | **Posting failed**, step 3 below, prints what they are called today. Add it to the list at the top of `wastatus/post.py` |
| A second Chrome opened instead of a WhatsApp tab appearing | the profile was already running, so Chrome forwarded the URL to it | that is the intended fallback. Look for the WhatsApp tab in the existing window |
| The phone cannot reach the page, and its address refuses the connection | started without `--also-on tailscale`, so only loopback is bound | check the startup output for an `Also on` line, and `ss -tlnp \| grep 8765` for a second socket. If there is one socket, Ctrl-C and start again. `WASTATUS_ALSO_ON=tailscale` in `.env` makes it every start's default, which is what stops this recurring after a reboot |
| The `Also on` line is printed and the phone still cannot reach it | Tailscale, not this tool | `tailscale status` should list the phone, and `tailscale ping <phone>` should pong. Check Tailscale is connected on the phone itself |
| `tailscale is not installed` or `tailscale returned no address` at startup | the flag resolved nothing, so the server stopped rather than binding something unexpected | install it, or `sudo tailscale up`, both in [LOCAL_SETUP.md](LOCAL_SETUP.md). Or pass the address yourself, `--also-on 100.64.0.7` |

There is no cancel button. A render runs to completion or fails; the longest it can
take is a 90 second clip, which is around two minutes.

## Chrome will not open its debug port

Chrome only speaks the DevTools protocol when it was **started** with
`--remote-debugging-port`. There is no way to add it to a browser that is already
running, and no flag that reaches one. Everything below follows from that.

### Table RB-2: the four ways a debug browser fails to appear

| What you see | What actually happened | What to do |
|---|---|---|
| `DevTools remote debugging requires a non-default data directory` and the port never opens | Chrome 136 and later **refuse** remote debugging on the default profile, permanently and by design. Measured on 2026-08-22 against `~/.config/google-chrome` | nothing to fix. This is why the tool keeps its own profile, `~/.config/chrome-wastatus`, which is also why the QR code is scanned once and not again |
| Chrome prints `DevTools listening on ws://[::1]:NNNN` and the tool still cannot reach it | **the port was already taken.** Chrome logs `bind() failed: Address already in use (98)`, carries on with IPv6 only, and then prints a line that reads like success. Everything here asks `http://127.0.0.1:NNNN`, which is the *other* browser | start it on a port nothing holds. `ss -ltn \| grep 92` lists what is taken. The tool now says `port N is only half open` and names the browser that took it |
| `no WhatsApp Web tab is open in it`, in a browser you are sure is logged in | you are looking at somebody else's debug browser. An IDE that opens Chrome of its own takes 9222 upward and does not give it back | read the profile name in the message. `WASTATUS_CDP_PORTS=9230-9235` in `.env` moves this tool's search somewhere that is yours |
| A second Chrome window opens and the port stays shut | Chrome hands a launch on an already open profile to the running instance and exits, ignoring the new `--remote-debugging-port` entirely | the page detects this and adopts the running browser's port. From the command line, close the window or reuse its port |

### What the browser itself said

```bash
tail -40 logs/chrome.log      # the last launch, and why it did or did not work
```

Chrome's own output has been kept since 2026-08-22. It is the only place two things
are ever printed: `bind() failed: Address already in use (98)`, and the refusal to
run remote debugging on a default profile. A browser that started and then vanished
leaves its reason here and nowhere else.

### Which browser is on which port

**Look at the window title first.** A browser this tool started has a label tab as
its first tab, and its title is `● 8765 · wastatus`, so the window title and the task
bar entry name the session's page port. The tab itself names the debug port, the
profile and the output folder. It is a file, `~/.cache/wastatus/session-<port>.html`,
so it is still readable after the tool has been stopped, and it can be reopened at
any time. A browser that was already running when the tool started never gets one:
nothing was launched, so there was no command line to put it on.

For a browser nobody labelled:

```bash
ss -ltnp | grep -E '92[0-9][0-9]'          # what is listening, and its pid
grep -az remote-debugging-port /proc/PID/cmdline | tr '\0' '\n'   # and whose profile it is
```

The profile is the identifying part, not the port. Chrome flattens its own argv
into one space separated string, so `--user-data-dir=` is in there but the usual
NUL separators are not, which is worth knowing before writing anything that parses
it. `post.port_owner(port)` does this and is what the error messages use.

### Starting one by hand

```bash
google-chrome --remote-debugging-port=9230 \
  --user-data-dir="$HOME/.config/chrome-wastatus" https://web.whatsapp.com
```

Any profile except the default one works. The port only has to be in
`WASTATUS_CDP_PORTS`, or named with `--cdp-port`, and `discover` tries every
candidate anyway.

## Posting failed

The clip is never lost to a posting failure. It is on disk, the caption is beside
it, and the tool prints a retry line that posts the existing file.

1. Look at the page. `scripts/wa_post.py shot /tmp/wa.png` writes a screenshot of
   whatever WhatsApp Web is showing, which answers most questions immediately.
2. Load the composer without sending, and inspect it:
   `scripts/wa_post.py video out/<clip>.mp4 --caption-file out/<clip>.caption.txt`
   then `scripts/wa_post.py send` when it looks right, or `cancel` to back out.
3. If a control cannot be found, WhatsApp Web has been redesigned. Every selector
   and label is at the top of `wastatus/post.py`: `ADD_STATUS`, `PHOTO_ITEM` and
   `TEXT_ITEM` are lists of the spellings seen so far, `div[contenteditable="true"]`
   is both composers, and `SEND_ICON` is Send. WhatsApp dropped Send's
   `data-icon` by 2026-10-24, so it is matched by label too: `Send 1 selected` in
   the media composer, `Send` in the text one, [DECISIONS.md](DECISIONS.md) D-079. **Labels are matched on words**, so `Photos & videos` and
   `Photo and video` are the same thing to it, [DECISIONS.md](DECISIONS.md) D-041.
   To find out what WhatsApp calls it today, open the Status tab in that browser and
   read the labels off the page:

   ```bash
   .venv/bin/python - <<'PY'
   from wastatus import post
   with post.Page(9222) as page:
       post.open_status_tab(page)
       post.click_any(page, post.ADD_STATUS)
       print(page.js("""(() => JSON.stringify([...document.querySelectorAll(
           '[role=menuitem]')].map(e => e.getAttribute('aria-label'))))()"""))
   PY
   ```

   Add whatever it prints to the matching list. Nothing else needs to change.
4. Chrome stops answering the debug protocol while it uploads. That is expected and
   `post.Page.js_soft` treats it as "still going". Do not add a retry that
   interprets it as failure.

## Ladder exhausted

Every client in `STRATEGIES_AUDIO` or `STRATEGIES_VIDEO` failed. This is the
expected consequence of a YouTube change and needs the ladder updated, not a
config tweak.

1. Confirm the provider is alive:

```bash
curl -s http://127.0.0.1:4416/ping
```

Expect a JSON body with `server_uptime`. If nothing answers, start it by hand and
read its output:

```bash
node ~/.local/share/wastatus/bgutil/server/build/main.js --port 4416
```

2. Check yt-dlp is current. A stale yt-dlp is the single most common cause:

```bash
.venv/bin/pip install --upgrade yt-dlp
```

3. Work through the format discovery procedure in
   [PLAYBOOK.md](PLAYBOOK.md) under **Fix a broken download**, then extend the
   ladder in [wastatus/fetch.py](wastatus/fetch.py) and record the result in
   [docs/extraction.md](docs/extraction.md).

4. If no client works from this network at all, the IP is the problem rather than
   the tool. Set egress explicitly:

```bash
export WASTATUS_PROXY="http://user:pass@host:port"
# or
export WASTATUS_COOKIES_FROM_BROWSER=firefox
```

Cookies carry account ban risk. Prefer a proxy. See
[SECURITY.md](SECURITY.md).

## Transliteration degraded

Titles that should read `Sinna Sinna Murugaiyaa` coming out as `cinnnnnn`
means `aksharamukha` did not import and the Unidecode fallback took over.

```bash
.venv/bin/python -c "
import wastatus.translit as t
print('aksharamukha loaded:', t._ak is not None)"
```

The known cause is Python version drift: aksharamukha imports `ast.Str`, removed
in Python 3.12. `translit.py` shims it, so a `False` here means either the
package is missing or the shim no longer covers what it needs.

Reinstall first:

```bash
.venv/bin/pip install --force-reinstall aksharamukha
```

If it still fails, the fallback is `--title "Correct Title"` on each run while a
fix is worked out. Do not remove the shim; see
[DECISIONS.md](DECISIONS.md) D-006.

## Provider will not start

`potoken.ensure_running` returns False when the built entry point is missing or
node is absent.

```bash
node --version                                                   # need >= 20
ls ~/.local/share/wastatus/bgutil/server/build/main.js
```

If the build directory is empty, the TypeScript build did not run:

```bash
cd ~/.local/share/wastatus/bgutil/server && npm install && npx tsc
```

If the port is already taken by something else, move it:

```bash
export WASTATUS_POT_PORT=4417
```

## Output looks wrong but nothing errored

Extract frames and inspect. Never diagnose a visual problem from the logs.

```bash
ffmpeg -y -ss 2  -i out/<file>.mp4 -frames:v 1 /tmp/f1.png
ffmpeg -y -ss 12 -i out/<file>.mp4 -frames:v 1 /tmp/f2.png
```

Two frames apart in time also confirms the zoom and the waveform are moving.

## Health check

A single command that exercises metadata, download, provider, compose and encode:

```bash
./wastatus.sh "https://youtu.be/A6DfGQsdz1Y" 1:10 1:20 -o /tmp/health
```

Healthy result: about 25 seconds, an mp4 of 3 to 6 MB, two text files, a clean
exit, and a Latin title on the card.
