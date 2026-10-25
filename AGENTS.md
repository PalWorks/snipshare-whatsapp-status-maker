# Agent contract

Read this before changing anything. Read [CONTEXT_MAP.md](CONTEXT_MAP.md) to find
everything else.

## What this project is

A command line tool and local page that cut a YouTube snippet into a WhatsApp
Status clip carrying the source link; since 2026-10-24 a Chrome extension and a
hosted renderer that do the same from the viewer's own browser; and since
2026-10-25 **SnipShare**, the same page hosted for people the owner approves, which
drives that extension. One maintainer. The site, the renderer's API and the
extension are all in this repository, so they change together.
Optimise for the maintainer being able to fix it six months from now, not for
generality. Public since 2026-10-25 under the AGPL-3.0-only with a commercial licence
(D-099). Last updated **2026-10-25T15:11:42+05:30**.

## Agent roles

**Table AG-1: who does what**

| Role | Does | Never |
|---|---|---|
| Implementer | changes code under the rules below, with tests in the same commit | pushes, deploys, or sends a Status |
| Reviewer | reads a change against CONTRIBUTING.md, Table CO-2, and the review prompt in [PROMPTS.md](PROMPTS.md) | approves its own change |
| Auditor | reads across modules for races, slow networks, orphans and leaks, and proves findings with a scratch test before reporting them | edits while auditing |
| Documenter | keeps the documents in step with the code, each update timestamped | records anything personal or infrastructural |
| The owner | decides, pushes, deploys, approves people, presses Send | |

Reusable prompts for each role are in [PROMPTS.md](PROMPTS.md); the commands and
scripts an agent can run are in [SKILLS.md](SKILLS.md).

## Owner communication rules

These apply to every response, not just to code:

- Direct and concise. No filler, no restating the request back.
- No dashes in prose. No emoji.
- Include the current timestamp in every response.
- Never state something unverified as fact. Label `[Inference]`,
  `[Speculation]` or `[Unverified]`, and say plainly when you cannot verify.
- Never raise a problem alone. Every problem arrives with options, the trade off
  of each, and a recommendation.
- Every response ends on a decision put to the owner or a stated next action.
  This holds even when the work succeeded.
- Tables are markdown and each gets a distinct name for later reference.

## Allowed without asking

- Editing any module under `wastatus/`, `src/`, `deploy/`, the docs, or `scripts/`
- Running `scripts/extension_check.py` against a local renderer or production, and
  `scripts/deploy.sh --check`
- Running the tool against any YouTube URL to verify a change
- Adding to the client and format ladder in `fetch.py`
- Adjusting encoder settings, layout constants, and filter graphs
- Installing Python packages into `.venv` when a change needs them, provided
  `requirements.txt` is updated in the same commit

## Ask first

- Adding a dependency that is not pure Python, or that pulls a native toolchain.
  `google-auth`, which pulls `cryptography`, was asked about and accepted on
  2026-08-31, D-074. It is the only one
- Authenticating as the owner's WhatsApp account through an unofficial protocol
  library: whatsmeow, Baileys, or anything that pairs as a device. This risks the
  account the whole product depends on. See [DECISIONS.md](DECISIONS.md) D-002.
  Driving an already logged in WhatsApp Web tab over CDP is allowed and is what
  `--post` does, see D-012
- Pressing Send on a real Status. Loading a composer to inspect it is fine,
  posting to the owner's audience needs his say so
- Provisioning cloud infrastructure or spending money, including proxies
- Binding the server to a non-loopback address for longer than a check needs, or
  installing the systemd service. Both change what is reachable on the owner's own
  machine and network, so they are his to run. Writing the script is not
- Deleting anything from `out/`. The page can now delete a clip, so a verification
  run works against a scratch folder with `-o`, never against the real one
- Changing what a run posts by default, which is a product decision and not a
  technical one
- `scripts/deploy.sh`, which replaces what is running in production, and
  any change to that host's shared configuration or the site's DNS zone, both shared with
  other services. Run the full suite and `extension_check.py` against a local
  renderer first
- Making, listing or revoking renderer tokens for anyone but the owner
- Approving, declining, suspending or deleting anybody on SnipShare, or changing
  `WASTATUS_ADMIN_EMAILS` or the daily limits on the server
- Anything in Cloudflare (the tunnel, Turnstile, DNS) or Google Cloud (the sign-in
  client, its consent screen)
- `git push`, opening PRs, or anything outward facing. Since 2026-10-25 there are two
  remotes: the public `https://github.com/PalWorks/snipshare`, published as a fresh
  copy (D-099), and the private `PalWorks/whatsapp-status-maker`, which keeps the full
  history. Both exist, which is not the same as having permission to push to either.
  Anything pushed to the public one is public for good
- Changing the licence, the commercial licence's terms, or the contribution terms in
  CONTRIBUTING.md (D-099)
- Merging an outside contribution whose commits are not signed off: the dual licence
  depends on the grant in CONTRIBUTING.md

## Never

- Commit `.venv/`, `.env`, `MEMORY.private.md`, `out/`, `logs/`, `dist/`,
  `.publish-deny`, the service account key or the extension's signing key at
  `~/.config/wastatus/`, the server's `.env` or `tunnel.env`, or anything under the
  provider install directory
- Write the production site's address, the host, the owner's addresses or any key
  into a tracked file. They belong in `.env` files and the private notes;
  `tests/test_publishable.py` fails if one gets in (D-093)
- Let a logging failure break a run. `runlog` swallows its own io errors on purpose,
  and so does `sheet`: an unreachable sheet costs a row and never a Status
- Report a Status as posted on anything but WhatsApp's own `ack`. The composer
  closing is not an answer, see [DECISIONS.md](DECISIONS.md) D-071
- Retry a `StatusUnconfirmed`. Only a refusal is safe to send again, D-073
- Add instructional copy to the card. The footer and eyebrow default to empty
  because a Status is personal, see [DECISIONS.md](DECISIONS.md) D-010
- Reimplement any part of `pipeline.produce` inside `serve.py`. The page exists to
  call the engine, not to be a second copy of it. If the page needs something the
  engine does not expose, change the engine
- Make sending the default anywhere. `POST /api/post` sends only on an explicit
  `send: true`, and the page's primary button loads the composer and stops. An
  omitted field, an old client or a refactor must all mean "load it". See
  [DECISIONS.md](DECISIONS.md) D-020
- Reimplement the card's layout in the browser so the wording can be edited in
  place. Two layout engines drift, and the preview would start lying. Card wording
  is a form field that triggers a render; see D-021 for where that line sits
- Convert sticker coordinates anywhere. They are fractions of the frame from the
  browser to the paste, which is the whole reason dragging one is honest. A scale
  factor passed between the two is the bug this design exists to prevent, see D-024
- Paste an animated sticker with Pillow, or overlay one after `zoompan` in card
  mode. The first flattens it to its first frame; the second leaves it sitting still
  while the pasted stickers drift outwards in the same picture. `stickers.split` and
  the pre-zoom overlay are the two halves of that rule, see D-036
- Store an animated sticker as anything but GIF. This ffmpeg refuses an animated
  WebP outright and gives no useful error. Pillow reads every format and writes the
  one that works, see [MEMORY.md](MEMORY.md) Table ME-5
- Draw anything in the preview that the renderer will not paste. A shadow, a filter,
  a font substitution: if the frame shows it, the clip has to have it. The one
  admitted exception is a handle you are holding, and it is admitted on a condition:
  the dashed selection box is lit only while a finger, the mouse or a slider is on
  the sticker and fades 1.4 seconds after, so the resting frame is still honest. Any
  new marker takes the same rule, see [DECISIONS.md](DECISIONS.md) D-034. The amber
  covered outline stays, because it is a warning rather than a handle
- Fold a card without giving its header a value to show. A collapsed section that
  does not say what is inside it is a hiding place, not a fold, see
  [DECISIONS.md](DECISIONS.md) D-032. `paintSummaries` is where those values live
- Write an automatic fold into `wastatus.open`. The page folds the input cards when
  a clip lands; only a fold the owner pressed is a preference. The flag that
  separates the two rides on the element, because `toggle` fires on a later task
- Assign to `hidden` on an `<svg>`. It is a property of `HTMLElement` and not of
  `SVGElement`, so the assignment silently does nothing. Use `hide`/`unhide`, which
  set the attribute. This cost the play icon and the theme icon on 2026-08-19
- Make the hosted renderer talk to YouTube, for anything, artwork included. Its whole
  reason to exist is that it does not have to; the extension uploads what is needed,
  D-085 and D-080
- Parse fragments on the server, or keep a second copy of `src/media.js`'s
  logic anywhere. One parser, tested in Node; the server checks the files it is
  given with ffprobe, D-083
- Add CORS headers to `hosted.py`, accept a token in a query string, or log one. The
  extension's worker needs no CORS, and a web page must never be able to read an
  answer, D-081
- Let the extension press Send in WhatsApp, D-084, as D-020 says for the page
- Stop recording in `recorder.js` between captures, or break YouTube's playback from
  a hook: every hook calls the original and swallows its own errors, D-083
- Remove the token check or add CORS headers to `serve.py`. Any website you visit
  can reach a loopback server, and this one posts to a WhatsApp account. See
  [SECURITY.md](SECURITY.md)
- Raise `render.SIZE_BUDGET_BYTES` or the maxrate ceiling without attach testing
  the result against the real composer. WhatsApp refuses oversize media silently, so
  a bitrate change made for quality can break posting with no error anywhere. The
  ceiling is `render.PLATFORM_MAX_BYTES`, 10 MiB, bisected on 2026-08-20, and the
  budget must stay below it by more than the encoder's 2 percent overshoot. See
  [DECISIONS.md](DECISIONS.md) D-017
- Draw anything below `compose.SAFE_BOTTOM` or above `compose.SAFE_TOP`. WhatsApp
  puts its caption in the first and its header in the second, and ours collides
  with theirs. `tests/test_safe_zone.py` will fail if you do. See D-014 and D-016
- Hardcode credentials, cookies, proxy URLs or tokens. Configuration arrives
  through the `WASTATUS_*` environment variables listed in
  [README.md](README.md), or from a `.env` file that is never committed. Adding a
  setting means adding it to `.env.example` with **no value**, which a test enforces
- Put a personal address, hostname or home directory into a document. This repository
  is public (D-099), so examples use `example.com`, `100.x.y.z`, `192.168.1.10` and `~`,
  and `tests/test_publishable.py` fails on anything else
- Pass anything a person typed to yt-dlp without `--` before it, or start a child
  process that can read the server's terminal: `proc.run_child` gives every child
  `stdin=DEVNULL` (D-100)
- Read a request body before deciding who is asking, on the hosted site. Refuse
  first and close the connection, `_close_unread` (D-100)
- Give `send` a default of anything but `False`, anywhere (D-100, D-020)
- Let the extension's single `fetch()` wait longer than 25 seconds for its answer.
  Chrome stops a worker whose fetch waits 30, so a big request on a slow line has to
  be several small ones (D-100)
- Use ffmpeg `drawtext`, `subtitles` or `ass` filters. The reference ffmpeg build
  has no freetype or libass. All text goes through Pillow. See
  [ARCHITECTURE.md](ARCHITECTURE.md)
- Bundle or depend on a Tamil font. Card text is Latin only by design
- Add a fourth output file, or rename the existing three, without updating
  [DOMAIN.md](DOMAIN.md) and [README.md](README.md)

## Coding conventions

Match the surrounding code. It is consistent, so read a neighbouring module
before writing a new one.

- `from __future__ import annotations` at the top of every module
- Type hints on every function signature. `Path`, never string paths
- Module docstring saying what the module owns, in one line where possible
- Comments explain **why**, never what. If a line encodes a hard won fact about
  YouTube or ffmpeg, the comment records the fact and points at the doc
- Errors are typed per module: `TimecodeError`, `FetchError`, `RenderError`.
  Never let a raw `CalledProcessError` or `OSError` reach the user
- Subprocesses go through the module's own `_run` helper so failures are
  formatted consistently. New `Popen` calls must set `stdout` and `stderr`
  explicitly, because resident helpers like `xclip` otherwise hold the pipe open
  and the tool appears to hang after finishing
- Pure functions in `translit` and `timecode` stay pure. No io, no logging
- User facing output is the numbered `[n/4]` progress lines plus the final block.
  Do not add chatter between them

## Layout constants

`compose.py` designs against a 1080x1920 canvas and multiplies by `SUPER` at
render time. When moving elements, edit the design coordinates, never the
multiplied values. The waveform strip position is shared: `render.py` imports
`WAVE_TOP` and `WAVE_H` from `compose.py`, so the two never drift.

**`--video` mode's picture floor is derived, not typed.** `VIDEO_PICTURE_BOTTOM` and
`VIDEO_EYEBROW_TOP` both come off `VIDEO_TITLE_TOP`, so moving the title moves the
line the frames may not cross. Both ends of the band are chosen per
clip, by `compose.video_picture_bottom` and `video_picture_top`, because a label
costs the picture room at the bottom and top text costs it room at the top, each only
when there is one; pass them, do not import them.

**Test a destructive control against a throwaway output folder, not the live one.**
The delete cross was exercised against the running server on 2026-08-25, on the
owner's real `out/`, with copies made and deleted to avoid touching his clips. That
protects the clips the script names and nothing else: the control is now live on a
page the owner is also using, and two real clips were deleted minutes later. Start a
second server with `--out` pointing somewhere disposable and drive that instead. The
run log in `logs/runs.jsonl` is what makes a clip re-makeable afterwards, since it
keeps the link, the window and the mode, but it does not keep the wording or the
stickers: those live only in the sidecar that is deleted with the clip.

**Stickers are burnt into the pixels, in both modes.** `pipeline.produce` hands
`decals=still, moving=moving` to the card path exactly as it does to the video path,
so there is no arrangement in which a sticker reaches a clip without that clip being
rendered again. Anything that suggests otherwise to the person using the page is a
bug in the page, not a feature to add to the renderer. See D-056.

**A submit button outside its form needs `form=`.** Make the clip lives in the Post
it panel, which is not inside `<form id="form">`. Without the attribute the button
renders identically, takes the press and does nothing at all, which is the sort of
break no test catches unless it is written for it. `tests/test_page_wiring.py` is.

**A control on a tile is not a button inside a button.** The Recent tile is a `<div>`
with two buttons in it. Nesting one button in another is valid to write, invalid to
parse, and no browser reports it: the parser unnests them into siblings, so a control
meant to sit on the tile lays out beside it and `closest()` from it finds nothing. It
presents as a styling bug. See D-055.

**A `var(--danger)` fill takes its ink from `var(--danger-bg)`.** Both tokens invert
between the palettes, `--danger` being a dark red in one and a pale pink in the other,
so a fixed `#fff` on that fill is readable in exactly one of them. The same holds for
any token pair used as fill and ink rather than as ink alone.

**The picture's rectangle is Python's, not ffmpeg's.** `render.picture_rect` decides
it and the filter graph is given numbers. Do not put the fit or the clamp back into an
expression: Pillow anchors the top text to that rectangle, and a coordinate only
ffmpeg knows cannot be drawn against. The test that asserts the two agree, at five
aspect ratios, is the one to watch when touching either. See D-054.

**Nothing this tool draws is a single `draw.text` any more.** Title, label, top text,
second line and footer are all wrapped, and the last two take what is left of the
block rather than a fixed allowance. Adding a sixth thing means giving it a wrap and
a share of the room, not a coordinate. See D-052 and D-053. Do not replace that `min`
with a fixed y: wide sources are meant to stay centred, and the clamp is a floor for
the ones that are not. `tests/test_safe_zone.py` renders the real graph at five
aspect ratios and will fail if this drifts. See D-049.

## Verifying a change

**For the extension or the renderer**, the suite runs the parser in Node and the
renderer over real HTTP, but YouTube's page, Chrome's extension machinery and
WhatsApp Web are only reached by `scripts/extension_check.py`, against a local
renderer first and production after a deploy, with `--throttle` and `--restart-at`
when anything about the network or the job's state changed. Loading WhatsApp's
composer needs a signed in WhatsApp Web, which only the owner's Chrome has. See
[TESTING.md](TESTING.md), **The extension, end to end**.

`pytest` covers the offline logic. It does not cover the download path or the
pixels. The minimum before claiming a change works:

1. `.venv/bin/python -m pytest` passes
2. Run card mode against a Tamil script title and a Latin title
3. Run `--video` mode
4. Extract a frame and look at it. Do not claim a visual change works without
   looking at the pixels
5. Confirm the process exits and does not hang
6. **For anything on the page, drive it, at phone width.** A screenshot shows the
   layout, not the behaviour, and several bugs on 2026-08-19 were invisible in one.
   Assert on what a viewer would see, `getComputedStyle(el).display` or a bounding
   box, not on the property you just set: the one you set may not be the one the
   browser uses. The procedure is in [PLAYBOOK.md](PLAYBOOK.md) and
   [TESTING.md](TESTING.md)
7. **For anything about a WhatsApp caption, check it on a second device.** WhatsApp
   does not linkify your own Status caption on the device that posted it, and testing
   on one device produces a confident wrong answer. See [MEMORY.md](MEMORY.md)

New offline logic arrives with tests in the same commit. Test names state the
behaviour being protected, not the function being called, and any test encoding a
platform fact points at the doc that records it. See [TESTING.md](TESTING.md).

## Reporting

State what was verified and how. If a stage was skipped or a claim rests on
documentation rather than a run, say so and label it. Faithful failure reporting
is worth more here than a clean sounding summary, because the download path
breaks on YouTube's schedule and false confidence costs the owner a debugging
session.
