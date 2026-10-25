# Getting media out of YouTube

Notes from making this work in August 2026. The download path is the fragile
part of this project, so this records what was measured rather than assumed.

## The problem

YouTube gates media URLs behind two mechanisms:

1. **Proof of origin (PO) tokens.** Without one, the clients that still list
   fetchable formats return `403 Forbidden` on the media URL itself, even though
   metadata extraction succeeds.
2. **JS challenges.** Signature and `n` parameter solving needs a JavaScript
   runtime plus a solver script that yt-dlp fetches on demand.

Neither is about which downloader you use. Every extractor faces the same wall,
so switching away from yt-dlp gains nothing.

## What was tried

Against a control video and a Tamil devotional upload, with current yt-dlp:

| Attempt | Result |
|---|---|
| `bestaudio`, default client, no provider | 403 on the media URL |
| `--download-sections` with DASH audio | 403, ffmpeg exits 8 |
| `player_client=web` / `web_safari` / `ios` / `tv`, no provider | no formats listed at all |
| PO token provider running, no JS solver | formats resolve, still 403 |
| Provider plus `--remote-components ejs:github` | signatures solve, DASH still 403 |
| Provider plus solver, `web_safari` HLS renditions | **works** on the control video, no HLS on the Tamil one |
| Provider plus solver, `mweb` format 18 | **works on both** |

Re-measured on 2026-08-19, on `MbaNXlu4bXY`:

| Attempt | Result |
|---|---|
| `--list-formats` through `web_safari` | four storyboards, no media at all. The HLS route is closed |
| `--list-formats` through `mweb` | the full DASH set, including 136 at 720p and 137 at 1080p, plus 18 |
| `--download-sections` with `136+140` | 403, ffmpeg exits 8 |
| `--download-sections` with `136` alone | 403 |
| `--download-sections` with `140` alone, audio only | 403 |
| `--download-sections` with `136` and `--downloader native` | 403, sections still route through ffmpeg |
| `--download-sections` with `18` | **works**, as it has all along |

So the picture is unchanged in the only way that matters: **format 18 is the only
stream a section can be cut from**. The HD renditions are visible and unreachable,
because a section download hands the URL to ffmpeg and googlevideo refuses ffmpeg.
The only way to 720p would be fetching a whole stream, 70 MB for a seven minute
video to keep fifteen seconds. See [DECISIONS.md](../DECISIONS.md) D-023.

## What we ship

`fetch.py` requires a running provider, enables the solver, then walks a ladder
of (client, format) pairs until one produces a file:

```
audio: mweb/18, web_safari/93-95, android/18, tv_simply/18, default/bestaudio
video: default/95-96, mweb/18, android/18, tv_simply/18, web_safari/95-93
```

The audio ladder leads with `mweb/18` because it is the only entry that works.

**The video ladder leads with `default 95/96`, since 2026-08-20.** Those are HLS
renditions: they carry their own audio, and unlike the DASH ones a section really can
be cut from them, measured at 1280x720 and 1.8 MB for 12 seconds. Whether a video has
them is YouTube's to decide and varies by video, so `mweb/18` stays underneath as the
360p floor and a video without them costs about 2 seconds before the ladder falls
through. The dead `web_safari` entry stays at the end as a probe; it still returns
four storyboards and nothing else. `tests/test_fetch.py` pins the order and the
reason.

Format 18 is the muxed 360p progressive stream. It carries 128 kbps AAC, which
is all the card mode needs, and `--download-sections` fetches only the requested
range from it: about 1.2 MB for 15 seconds.

The ladder exists because format availability varies per video. Expect to revisit
it: YouTube ships anti bot changes weekly and the working combination moves.

## Watching the ladder

Every run records which `(client, format)` pair won, in `logs/runs.jsonl`. A run
that falls through to a later entry still succeeds, so the degradation is silent
unless you look. It also logs a `fell through` warning to `logs/wastatus.log`.

```bash
grep -o '"client": "[^"]*"' logs/runs.jsonl | sort | uniq -c   # what is winning
grep "fell through" logs/wastatus.log                          # early warning
```

When the leading entry stops winning, that is the signal to re-run the discovery
procedure in [PLAYBOOK.md](../PLAYBOOK.md) and update both the ladder and the table
above, before the ladder runs out entirely.

## The provider

`scripts/setup_provider.sh` clones and builds
[bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider),
whose yt-dlp plugin half is a normal pip dependency. `potoken.py` starts the
node server on port 4416 when a download needs it and stops it on exit.

## Running on a server

Datacenter IPs are flagged much harder than residential ones, so a cloud host
will need `WASTATUS_PROXY` pointing at residential egress, or cookies via
`WASTATUS_COOKIES_FROM_BROWSER`. Both hooks are already in `fetch.py`.

## Timings

On the development machine, a 15 second card clip end to end takes about 25
seconds: 4s metadata, 5s download, 0.6s card composition, 15s encode. The first
ever run is slower because the solver script is fetched from GitHub and cached.
