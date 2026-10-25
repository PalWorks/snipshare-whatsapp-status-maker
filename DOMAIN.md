# Domain

The rules of the two platforms this tool sits between, and the vocabulary used
across the rest of the docs.

## The problem being solved

Posting a YouTube link to WhatsApp Status produces a static thumbnail with a
link underneath. People do not click it. Posting a ten to twenty second clip of
the music instead gets people to listen, and the ones who like it then follow the
link to the full track. The tool automates producing that clip with the link
attached.

The music is Tamil devotional and film music. Titles arrive in Tamil script,
mixed Tamil and Latin, or Latin only.

## WhatsApp Status rules that shape the design

## Table DO-1: Status constraints

| Rule | Consequence in this repo |
|---|---|
| A single Status video is capped at 90 seconds | `pipeline.MAX_DURATION`, rejected before any download |
| The web composer accepts a 90 second clip, if it is small enough | confirmed 2026-08-18 at 9.7 MB, and the size line bisected on 2026-08-20 |
| Media over **10 MiB** is refused, silently, whatever the platform documents | bisected against the real composer on 2026-08-20: 10,452,278 bytes accepted, 10,519,352 refused. The encoder derives its bitrate from the duration to land under it, see [DECISIONS.md](DECISIONS.md) D-017 |
| Status is vertical, full screen | every output is 1080x1920, 9:16 |
| A URL in a **media caption** IS tappable | confirmed on the web client and on a phone, 2026-08-18. One post is enough, and the caption is the link alone |
| A URL in a **text only** Status is linkified with a preview card | `--follow-up` posts one, for the different look |
| WhatsApp draws the caption across the bottom of the frame | the bottom 15 percent is reserved, `compose.SAFE_BOTTOM`, see D-014 |
| WhatsApp draws the avatar, name, time and controls across the top | the top 12 percent is reserved, `compose.SAFE_TOP`, see D-016 |
| WhatsApp re-encodes on upload | no point shipping a high bitrate master, hence crf 23 |
| There is no official API for posting Status | `--post` drives the real web client instead, see D-012 |

## What a run posts

One Status: the clip, captioned with the link and nothing else. WhatsApp turns
that URL into a tappable link, so a viewer hears the snippet and taps once to
reach the full track.

Each piece of information appears exactly once. The card carries the title and the
channel. The caption carries the link. Putting the title in the caption made the
Status read like a listing rather than something a person sent, and putting the URL
in the frame gave a viewer a string they could not tap next to one they could. See
[DECISIONS.md](DECISIONS.md) D-015.

`--follow-up` adds a second, text only Status carrying the same title and URL,
which WhatsApp renders with a link preview card. It is optional now. It was the
whole design until the caption claim was tested, see
[DECISIONS.md](DECISIONS.md) D-003 and D-013.

The card carries no instruction telling the viewer to look at anything. A Status
is personal, and instructional copy makes it read as an advertisement. See
[DECISIONS.md](DECISIONS.md) D-010.

## YouTube extraction vocabulary

## Table DO-2: Terms

| Term | Meaning |
|---|---|
| PO token | proof of origin token. Without one, media URLs return 403 even when metadata resolves |
| JS challenge | signature and `n` parameter puzzles that need a JavaScript runtime to solve |
| EJS | the solver script distribution yt-dlp fetches from GitHub on demand |
| player client | the client identity yt-dlp impersonates: `mweb`, `web_safari`, `android`, `tv_simply`. Determines which formats are listed and whether they are fetchable |
| itag / format id | numeric stream identifier. `18` is muxed 360p progressive with 128 kbps AAC. `93` to `96` are HLS renditions, which carry their own audio and can be section downloaded when YouTube offers them |
| DASH | separate audio only and video only streams. Currently 403 blocked in this setup |
| HLS | segmented muxed streams. Available on some videos, absent on others |
| progressive | one file with audio and video muxed. Format 18 is the reliable one |
| download section | yt-dlp fetching only a time range rather than the whole file |
| SABR | YouTube's newer delivery path, which is why some clients list no usable formats. By 2026 the whole web player uses it, and it is why the extension reads the page instead of fetching |

Detail and the measurement table live in [docs/extraction.md](docs/extraction.md).

## Capture vocabulary

The browser extension and the hosted renderer, [docs/extension.md](docs/extension.md).

## Table DO-4: Terms

| Term | Meaning |
|---|---|
| MSE | Media Source Extensions: the browser API YouTube's player feeds video into. `appendBuffer` hands it bytes; `remove` evicts a time range; `abort` abandons what is half appended |
| MediaSource, SourceBuffer | one MediaSource per thing the player plays (a video, an ad); one SourceBuffer per track in it, audio and video |
| capture | the extension's copy of the window, read out of what the player appended, never fetched |
| the walk | how a capture fills its window without playing: pause, seek, wait, seek to the edge when the player stops reading ahead |
| header (init segment) | `ftyp` and `moov` in fragmented MP4, the EBML header through `Tracks` in WebM. Every fragment decodes only with the header it was appended under |
| fragment | one `moof` and `mdat` pair in MP4, one Cluster in WebM, each carrying its own start time |
| run | a stretch of appends with no `abort()` and no new header between them; the only place append order means anything |
| group | the fragments that decode with one header, keyed by its sample description |
| renderer | the hosted service, `wastatus/hosted.py`, behind SnipShare (`wastatus/portal.py`) |
| token | a person's key to the renderer, made by the owner, stored there only as its hash |
| upload | one file sent to the renderer in chunks: `audio`, `video` or `artwork` |
| job | one clip being made on the renderer: `queued`, `rendering`, `done`, `failed` or `cancelled` |
| SnipShare | the hosted page: this tool's page, served per person, for people the owner approves |
| person | someone who asked for access: `pending`, `approved`, `declined` or `suspended`; a `user` or an `admin` |
| session | a signed-in person's cookie, 30 days, stored only as its hash |
| workspace | one person's folder and the page's state for it: their clips, stickers and GIF key |
| grant | a short lived token the page hands the extension for one purpose: uploading a capture, or fetching one clip |
| report | a failure the page, the extension or the renderer saw: a source, a phase, a code and versions, never the video |

## Rendering vocabulary

## Table DO-3: Terms

| Term | Meaning |
|---|---|
| card mode | default. Artwork only, no video frames fetched. Blurred artwork background, artwork as a shadowed rounded card shaped to its own aspect ratio, slow zoom, waveform |
| padding bars | the flat bands an uploader pads a picture with to reach 16:9. Cropped off both artwork and source video, see [DECISIONS.md](DECISIONS.md) D-016 |
| video mode | `--video`. Real frames, blurred fill to 9:16, text burned over the bottom |
| the picture rectangle | in video mode, where the real frames actually land, decided by `render.picture_rect` in Python and handed to ffmpeg as numbers. The top text is anchored to its top edge |
| the picture band | in video mode, the space the real frames are allowed: `compose.video_picture_top` to `video_picture_bottom`, both read off the words rather than fixed. They are centred inside the whole frame until that would put them below its floor, and fitted to it when they are taller than it, see D-049 |
| the card | the 1620x2880 PNG that Pillow composes and ffmpeg animates |
| the overlay | the 1080x1920 transparent PNG used in video mode |
| Ken Burns | the slow zoom, `zoompan` from 1.0 to 1.07 across the clip |
| waveform | `showwaves` strip reacting to the audio, sitting at y 1400 to 1580 |
| top line | an optional letterspaced line above the picture, off by default. It hangs off the picture's top edge rather than sitting under WhatsApp's header, so length grows upwards; the frames give up the room for it, and in card mode it takes what the eyebrow leaves. See D-053 and D-054 |
| eyebrow | an optional letterspaced label, off by default. Above the card in card mode, above the words in video mode, where the frames give up the room for it, see D-052 |
| footer | an optional small line under the pill, off by default |
| link pill | the rounded capsule containing a play triangle and `youtu.be/<id>` |
| scrim | the darkening gradient over the blurred background so text stays readable |
| drift | the gap between the clip on show and the form above it. The clip is pixels and cannot be edited, so a word typed or a sticker moved after it was made is not in it. Named next to the buttons that would send it, see D-056 |
| the Recent strip | the row of tiles under the form, one per clip in the output folder, newest first. It is where variants of the same song are compared, and since D-055 where the ones you do not want are dropped: each tile carries a cross that deletes the clip and every sidecar that belongs with it |
| a variant | one of several clips made from the same song while settling the wording or the window. They differ only in the words drawn on them, so they are told apart by their thumbnails and their times, which is why the strip shows both |
| session label | the page opened as the posting browser's first tab, whose title names the port this session's page is on, see D-050 |
| provider credit | the mark naming GIPHY or KLIPY under the sticker shelf. Required by both providers' terms while their results are on show, and KLIPY additionally requires the search box to read "Search KLIPY". Neither is optional |

## Transliteration rules

Nothing on the card is rendered in Tamil script. This is a deliberate product
decision, not a technical limit: no Tamil font is bundled and none is needed.

Tamil is transcribed the way Tamil speakers actually spell it in Latin, which is
phonetic rather than letter by letter. `சின்ன சின்ன முருகையா` becomes
`Sinna Sinna Murugaiyaa`, not `cinnnnnn cinnnnnn murukaiyaa`. This requires
contextual voicing rules, because Tamil க can be `ka`, `ga` or `ha` depending on
position. `aksharamukha` with the `TamilTranscribe` preprocessor and the
`RomanReadable` target does this correctly, and is why that dependency exists.

Titles are also cleaned: bracketed noise like `(Official Video)`, trailing
hashtags, and `- Topic` channel suffixes are removed, and a title that repeats
itself once per script is collapsed to a single copy using a similarity
threshold. `--title` overrides everything.
