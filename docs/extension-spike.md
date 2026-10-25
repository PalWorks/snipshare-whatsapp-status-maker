# The spike behind the extension: capture in the browser, render on a server

Written 2026-10-24T14:11:13+05:30, on a throwaway branch that has since been removed;
moved here unchanged apart from this paragraph and the last section, because it is the
evidence [extension.md](extension.md) and DECISIONS.md D-080 to D-085 rest on. The
spike's code was replaced by the built extension: its fragment stitcher by
`src/media.js`, its cut by `wastatus/capture.py`, its posting test by
`src/whatsapp.js`.

## The question

Can a Chrome extension get the chosen section of a YouTube video out of the viewer's
own browser, on the viewer's own IP, well enough that the existing engine can render
from it on a server?

## How it works

1. `src/hook.js` runs in the page's world before YouTube's player exists and
   copies every buffer the player hands to Media Source Extensions. SABR changes how
   the player fetches; it does not change what reaches a SourceBuffer, which is plain
   fMP4 or WebM.
2. To fill the window the driver seeks the paused player to the start, waits for it
   to stop reading ahead (about 20s), seeks to the edge of what it has, and repeats
   until it has the window plus 6s. No playback.
3. `src/bridge.js` hands the bytes to the service worker, which uploads them.
4. `stitch.py` cuts each buffer into runs at aborts and header appends, walks each
   run strictly, groups fragments by the header they decode with, deduplicates on
   their own timestamps and writes one clean file per kind.
5. `render_from_capture.py` runs `pipeline.produce` unchanged, with only
   `fetch.probe` and `fetch.download_section` replaced.

## Table SP-1: final matrix (matrix4, 14 runs, every one passed)

Reference: YouTube's own 360p progressive stream (format 18) via the tool's yt-dlp
path, whole file, cut frame accurately.

| Video | Window | Browser | Capture time | Output | Duration right | Best SSIM |
|---|---|---|---|---|---|---|
| V3DpYi6e3Uo (vertical) | 30+15 | headless | 3.5s | 720x1280 | yes | 0.975 |
| MbaNXlu4bXY | 60+30 | headless | 6.0s | 1080p | yes | 0.990 |
| kJQP7kiw5Fk | 120+60 | headless | 18.3s | 1080p | yes | 0.927 |
| JGwWNGJdvx8 | 150+90 | headless | 11.9s | 1080p | yes | 0.975 |
| C11EZKAFvro | 0+30 | headless | 2.1s | 1080p | yes | 0.996 |
| V3DpYi6e3Uo | 440+29, near the end | headless | 5.0s | 720x1280 | yes | 0.973 |
| M3aLeoGOiFU (sync test) | 10+20 | headless | 2.4s | 1080p | yes | 1.000 |
| C11EZKAFvro | 26+90 | headless | 9.1s | 720p | yes | 0.997 |
| kJQP7kiw5Fk | 30+45 | headless | 7.1s | 720p | yes | 0.953 |
| MbaNXlu4bXY | 200+60 | headless | 8.0s | 720p | yes | 0.988 |
| kJQP7kiw5Fk | 120+60 | headed (Xvfb) | 11.9s | 1080p | yes | 0.927 |
| JGwWNGJdvx8 | 150+90 | headed | 16.1s | 1080p | yes | 0.975 |
| C11EZKAFvro | 0+30 | headed | 2.0s | 1080p | yes | 0.996 |
| M3aLeoGOiFU | 10+20 | headed | 3.4s | 1080p | yes | 0.995 |

SSIM is the best within three frames either way: format 18 is a separate encode and
its picture sits about one frame off the adaptive streams.

## Sync

Measured on the beep and flash test video, on the files' own timestamps: the flash
lands on the whole second to the frame and the beep within 7ms in the raw capture,
and within 0.5ms after the cut. Format 18, which the current tool uses, has its beep
36.7ms late. The capture is the more accurate of the two.

Two cutting traps found and fixed, both in ffmpeg rather than in the capture: seeking
two inputs separately with `-ss` cost 59ms, and without `-copyts` each input is
shifted by its own start time, which cost 33ms. Cut with `trim`/`atrim` on the
original timestamps, `-copyts`, `-fps_mode passthrough`.

## Engine

`render_from_capture.py` made a 90s clip in both modes from a captured section with
no change to the engine: card mode in 75s, video mode in 41s, on this laptop. Frames
looked at.

## Found and fixed during the spike

- Arming the capture after page load loses whatever the player buffered first, and
  the player does not fetch it again. Record from the first byte.
- A seek can abandon a fragment halfway through its payload; a box walker that
  trusts the length then reads into the next header. Hence runs, cut at aborts.
- A SourceBuffer can be re-initialised mid-stream with a different encoding under
  the same mime type. Fragments are grouped by the header's sample description.
- A content script's fetch to a loopback address meets Chrome's local network
  prompt, which a headed browser leaves open. The service worker uploads.

## In the owner's own Chrome, 2026-10-24 evening

Branded Chrome 156 on port 9226, extension loaded unpacked, signed out of YouTube.

- Capture works there as it does in Chrome for Testing: Despacito 120+30 in 4.2s at
  1080p, SSIM 0.927, the same per-video audio offset against format 18 as before.
- **Ads.** Five popular videos, ads before three of them. Each ad played in a
  MediaSource of its own, flagged as an ad by the hook from its first append; the
  video then got a fresh MediaSource. `getCurrentTime()` and `video.currentTime`
  agreed to the hundredth, so no ad was stitched into the content timeline. All
  three verified clean: 20.0s, SSIM 0.978 to 0.985, audio correlation 0.97 to 0.98.
- A YouTube tab that is not on screen loads no media at all. Not a problem for the
  product, where the viewer is watching the video when they press the button.
- **Posting.** The service worker fetched a finished clip and injected
  `whatsapp.js` into the WhatsApp Web tab. It opened Status, chose Photo and video,
  caught the file input WhatsApp clicked, filled it through a DataTransfer, and
  typed the caption with `execCommand("insertText")`. Composer ready in 2.1s with
  the caption linkified. Send not pressed. No CDP-only command used.
- WhatsApp no longer puts `data-icon="wds-ic-send..."` on Send; it is found by its
  label, "Send 1 selected". `wastatus/post.py` still waits for the icon.

## Signed in with YouTube Premium, 2026-10-24T17:57:38+05:30

The window was behind another one, so every tab reported hidden. A document loaded
while hidden gets no media; one that was shown before keeps working. So each video
was opened through the page's own player (`loadVideoById`), the way YouTube moves
between videos itself, with no tab activated.

Six videos, including the three that had ads signed out: no ads, captures in 1.3 to
8.4s at 1080p, every duration exact, SSIM 0.925 to 1.000, and the sync test at
0.0ms flash and +0.5ms beep.

Two things the product has to do, both learnt here:

- **Never disarm.** The driver disarmed the hook at the end of each run, so the
  next in-page video lost its first 20 seconds. The extension records always.
- **Tag every buffer with its video.** In-page navigation keeps old buffers in the
  same page, and their timestamps overlap the new video's. The spike filtered by
  MediaSource number; the product should record the video id at addSourceBuffer.

## Not tested

- Ads stitched into the content stream. Not seen; the check above is how to see it.
- YouTube Music. The one attempt timed out before the player was ready; not debugged.
- Signed-in profiles, Premium, DRM videos, a player that moves MSE into a worker.
- Posting from the extension. It needs a WhatsApp Web session in a browser with the
  extension loaded, which only the owner can provide.
- Branded Chrome. Chrome for Testing 156 was used because branded Chrome no longer
  accepts `--load-extension`; the engine is the same.

## Files

The spike's scripts (a CDP driver, an upload stand-in, a Python stitcher, the
yt-dlp comparison and the beep and flash measurement) were throwaway and are not
kept. What replaced each is named at the top. The measuring method survives in
[TESTING.md](../TESTING.md), **The extension, end to end**.
