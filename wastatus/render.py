"""ffmpeg composition."""

from __future__ import annotations

import logging
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter

from . import stickers
from .compose import (HEIGHT, SAFE_TOP, VIDEO_PICTURE_BOTTOM, WAVE_H, WAVE_TOP,
                      WIDTH, detect_bars)
from .proc import run_child

log = logging.getLogger("wastatus")

FPS = 30
ZOOM = 0.07  # Ken Burns travel over the whole clip.
# No fade in on the picture: WhatsApp shows a clip's first frame in the composer,
# in the Status list and before anybody presses play, so the first frame is the
# artwork or the video itself, never black. The sound still rises over 0.2 seconds,
# so it does not start with a click. Asked by the owner on 2026-10-25, D-094.
FADE_OUT = 0.4

# Where in the clip to look for letterbox bars. One frame is not enough: a dark
# shot reads as entirely flat, which the detector correctly refuses to trim, and a
# fade would report bars that are not there for the rest of the clip.
BAR_SAMPLES = (0.25, 0.5, 0.75)

# WhatsApp refuses media it will not take by simply never opening its editor, with
# no message at all. Bisected against the real composer on 2026-08-20, every probe
# 90 seconds long and identical but for its size, so only the size was under test:
#
#   10,311,640  accepted      10,650,175  refused
#   10,452,278  accepted      10,519,352  refused
#
# The line between those last two is **10 MiB, 10,485,760 bytes**, and the two
# probes sit 33 kB either side of it. That is the ceiling: not the 16 MB the
# platform documents, and not a length limit, which the earlier 13.7 MB refusal at
# 90 seconds had left open. See TASKS.md T-014.
PLATFORM_MAX_BYTES = 10_485_760

# The budget is not a cap: it sets a maxrate, and the encoder overshoots it by about
# 2 percent, measured twice (a 9.5 MB budget produced 9,684,891 bytes at 90 seconds
# and 9,690,149 at 60). So the budget has to sit far enough below the ceiling that
# the overshoot still clears it. 10,000,000 leaves 4.6 percent, which is twice the
# measured overshoot.
SIZE_BUDGET_BYTES = 10_000_000
MAXRATE_CEILING = 2800   # kbit/s, the quality ceiling for short clips
MAXRATE_FLOOR = 600      # kbit/s, below which the picture is not worth sending
AUDIO_BITRATE = 128      # kbit/s


class RenderError(RuntimeError):
    pass


def ffmpeg_bin() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        raise RenderError("ffmpeg not found on PATH (macOS: brew install ffmpeg)")
    return found


def _moving_inputs(moving: list[stickers.Sticker]) -> list[str]:
    """The ffmpeg arguments that put each animated sticker on the command line.

    `-stream_loop -1` before the input, so a two second loop rides a forty second
    clip. The overlays below end with the picture, which is what stops an endless
    input producing an endless output.
    """
    args: list[str] = []
    for sticker in moving:
        file = stickers.motion(sticker.id)
        if file is None:  # pragma: no cover - split() already checked
            continue
        args += ["-stream_loop", "-1", "-i", str(file)]
    return args


def _moving_chain(
    moving: list[stickers.Sticker], into: str, canvas: tuple[int, int], first: int
) -> tuple[list[str], str]:
    """Filter steps that lay the animated stickers over `into`, in order.

    `canvas` is the size of the stream being drawn on, and the coordinates are
    fractions of it, exactly as `stickers.paste` treats the still ones. The rotated
    box is measured here rather than left to an ffmpeg expression, because `overlay`
    needs the top left corner and a rotation moves it.

    Returns the steps and the name of the stream to carry on with.
    """
    steps: list[str] = []
    label = into
    width, height = canvas
    for at, sticker in enumerate(moving):
        file = stickers.motion(sticker.id)
        if file is None:  # pragma: no cover - split() already checked
            continue
        with Image.open(file) as art:
            ratio = art.height / art.width
        drawn_w = max(2, round(sticker.size * width))
        drawn_h = max(2, round(drawn_w * ratio))

        chain = [f"fps={FPS}", f"scale={drawn_w}:{drawn_h}", "format=rgba"]
        box_w, box_h = drawn_w, drawn_h
        if sticker.rotation:
            # Pillow turns anticlockwise for a positive angle and ffmpeg turns
            # clockwise, so the sign is flipped here. Getting this wrong mirrors
            # every animated sticker against every still one.
            radians = math.radians(-sticker.rotation)
            cos, sin = abs(math.cos(radians)), abs(math.sin(radians))
            box_w = max(2, round(drawn_w * cos + drawn_h * sin))
            box_h = max(2, round(drawn_w * sin + drawn_h * cos))
            chain.append(
                f"rotate={radians:.6f}:c=none:ow={box_w}:oh={box_h}"
            )
        steps.append(f"[{first + at}:v]{','.join(chain)}[mv{at}]")

        left = round(sticker.x * width - box_w / 2)
        top = round(sticker.y * height - box_h / 2)
        nxt = f"mvd{at}"
        steps.append(f"[{label}][mv{at}]overlay={left}:{top}:shortest=1[{nxt}]")
        label = nxt
    return steps, label


def _audio_chain(duration: float, *, normalise: bool = True) -> str:
    out_start = max(0.0, duration - FADE_OUT)
    fades = f"afade=t=in:st=0:d=0.2,afade=t=out:st={out_start:.3f}:d={FADE_OUT}"
    return f"loudnorm=I=-14:TP=-1.5:LRA=11,{fades}" if normalise else fades


# What ffmpeg says when `loudnorm` is handed digital silence: it measures -inf,
# divides by it, and feeds the encoder NaN. The message names neither the filter nor
# the cause, which is why it is matched here rather than shown to anybody.
SILENT_AUDIO = "NaN"


def _run_with_audio(build, duration: float) -> None:
    """Run a render, and run it again without loudnorm if the audio was silent.

    A source with no sound is not an error: a reel with the music stripped out, or a
    slideshow nobody scored, is still a clip somebody wants. Normalising silence is
    the only thing that fails, so the second attempt drops that one filter and keeps
    everything else. The signature is matched rather than the case being predicted,
    because knowing in advance would mean scanning the audio on every render to save
    the one in a hundred that needs it.
    """
    try:
        _run(build(_audio_chain(duration)))
    except RenderError as exc:
        if SILENT_AUDIO not in str(exc):
            raise
        log.warning("this clip's audio is silent, so it is not being levelled")
        _run(build(_audio_chain(duration, normalise=False)))


def _wave_chain(wave: bool) -> str:
    return (
        f"showwaves=s={WIDTH}x{WAVE_H}:mode=cline:rate={FPS}:"
        "colors=0xFFFFFF:scale=sqrt,format=rgba,colorchannelmixer=aa=0.8"
        if wave
        else ""
    )


def render_card_clip(
    card: Path, audio: Path, duration: float, dest: Path, *, wave: bool = True,
    moving: list[stickers.Sticker] | None = None,
) -> Path:
    """Still card, slow zoom, waveform reacting to the audio.

    Animated stickers are laid onto the card **before** the zoom, at the card's own
    resolution, so they travel with it exactly as the pasted ones do. Overlaying
    them after the zoom would have left a still sticker drifting outwards while an
    animated one sat fixed, in the same frame. See DECISIONS.md D-036.
    """
    frames = max(2, round(duration * FPS))
    zoom = f"1+{ZOOM}*on/{frames - 1}"
    fade_out_start = max(0.0, duration - FADE_OUT)
    with Image.open(card) as art:
        card_size = art.size

    # Card first, audio second, so animated stickers start at input two.
    steps, source = _moving_chain(moving or [], "0:v", card_size, first=2)
    graph = [
        *steps,
        f"[{source}]zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d=1:s={WIDTH}x{HEIGHT}:fps={FPS},setsar=1[bg]",
        "[1:a]asplit=2[aw][ao]",
    ]
    if wave:
        graph.append(f"[aw]{_wave_chain(True)}[wv]")
        graph.append(f"[bg][wv]overlay=x=0:y={WAVE_TOP}:eof_action=pass[base]")
    else:
        graph.append("[aw]anullsink")
        graph.append("[bg]null[base]")
    graph.append(
        f"[base]fade=t=out:st={fade_out_start:.3f}:d={FADE_OUT},format=yuv420p[v]"
    )
    def build(audio_chain: str) -> list[str]:
        return [
            ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-framerate", str(FPS), "-t", f"{duration:.3f}",
            "-i", str(card),
            "-i", str(audio),
            *_moving_inputs(moving or []),
            "-filter_complex", ";".join([*graph, f"[ao]{audio_chain}[a]"]),
            "-map", "[v]", "-map", "[a]",
            "-t", f"{duration:.3f}",
            *_encode_args(duration),
            str(dest),
        ]

    _run_with_audio(build, duration)
    return dest


def crop_expression(boxes: list[tuple[int, int, int, int]],
                    size: tuple[int, int]) -> str | None:
    """An ffmpeg `crop` for the picture common to every sampled frame.

    Takes the smallest bar found on each side, so a frame that happened to be dark
    can only ever make the crop more conservative, never invent one. Returns None
    when there is nothing worth cropping.
    """
    if not boxes:
        return None
    width, height = size
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[2] for box in boxes)
    bottom = max(box[3] for box in boxes)

    # yuv420p needs even dimensions and offsets, so round inwards to even numbers.
    left += left % 2
    top += top % 2
    crop_w = (right - left) - ((right - left) % 2)
    crop_h = (bottom - top) - ((bottom - top) % 2)
    if crop_w < 16 or crop_h < 16:
        return None
    if crop_w >= width - 8 and crop_h >= height - 8:
        return None  # nothing meaningful to remove
    return f"crop={crop_w}:{crop_h}:{left}:{top}"


@dataclass(frozen=True)
class Picture:
    """Where the source's own frames land on the 1080x1920 canvas.

    Worked out here rather than left to an ffmpeg expression, because Pillow has to
    know it too: the top text is anchored to this rectangle's top edge, and a
    coordinate ffmpeg keeps to itself cannot be drawn against. Exact numbers also
    beat an expression for reading and for testing, which is the other half of why
    the `min` that used to live in the filter graph now lives here.
    """

    width: int
    height: int
    left: int
    top: int


@dataclass(frozen=True)
class Framing:
    """Where somebody put the picture, in the units everything placed uses.

    `x` and `y` are its centre and `size` is its width, each a fraction of the
    frame, exactly as for a sticker or a line of free text. See D-024: fractions are
    what let the browser drag a rectangle over a 296 pixel preview and the renderer
    put it on a 1080 pixel canvas with no scale factor passed between them.

    The height is not here because it is not a choice: it follows from the source's
    own shape, which is why this is three numbers and `Picture` is four.
    """

    x: float = 0.5
    y: float = 0.5
    size: float = 1.0

    def as_json(self) -> dict:
        return {"x": round(self.x, 5), "y": round(self.y, 5),
                "size": round(self.size, 5)}


# A picture may hang off the frame: that is what full bleed means, and half off is
# a choice somebody can make. Beyond this it is not a placement any more, and the
# ceiling is also the point where scaling the source starts to cost real time: at
# three, a 1080 wide source is scaled to 3240 before it is cropped back.
FRAMING_MIN_SIZE, FRAMING_MAX_SIZE = 0.05, 3.0
FRAMING_REACH = 1.5   # of the frame, from either edge, as for a sticker


def parse_framing(raw: object) -> "Framing | None":
    """A placement from a request or a sidecar. None means "fit it as you always did".

    Clamped rather than refused, the way a sticker's placement is: a picture half off
    the frame is a choice, and a picture at x=900 is a bug in whatever sent it.
    Raises `ValueError` only for something that is not a placement at all.
    """
    if raw in (None, "", {}):
        return None
    if not isinstance(raw, dict):
        raise ValueError("a picture placement has to be an object")

    def number(key: str, default: float, low: float, high: float) -> float:
        try:
            value = float(raw.get(key, default))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"the picture's {key} has to be a number") from exc
        if value != value:  # NaN survives both comparisons below
            raise ValueError(f"the picture's {key} has to be a number")
        return min(max(value, low), high)

    return Framing(
        x=number("x", 0.5, -FRAMING_REACH, FRAMING_REACH),
        y=number("y", 0.5, -FRAMING_REACH, FRAMING_REACH),
        size=number("size", 1.0, FRAMING_MIN_SIZE, FRAMING_MAX_SIZE),
    )


def placed_rect(size: tuple[int, int], framing: Framing) -> Picture:
    """The rectangle a placement resolves to, given what the source's shape is.

    Unlike `picture_rect` nothing is fitted and nothing is clamped into a band: the
    placement is the answer, and it may reach past any edge of the frame. What it
    cannot do is stop being a rectangle, so the height still follows the source.
    """
    source_w, source_h = size
    width = max(2, _even(framing.size * WIDTH))
    height = max(2, _even(width * source_h / max(1, source_w)))
    return Picture(
        width=width, height=height,
        left=_even(framing.x * WIDTH - width / 2),
        top=_even(framing.y * HEIGHT - height / 2),
    )


def framing_of(rect: Picture) -> Framing:
    """The placement a rectangle came from. The inverse of `placed_rect`.

    What a fitted picture is placed at, so that switching from fitted to placed
    starts where the eye already is rather than jumping.
    """
    return Framing(
        x=(rect.left + rect.width / 2) / WIDTH,
        y=(rect.top + rect.height / 2) / HEIGHT,
        size=rect.width / WIDTH,
    )


def _even(value: float) -> int:
    """The nearest even number, which yuv420p's chroma plane needs.

    Nearest rather than rounded down, because a 16:9 source scaled to 1080 wants
    607.5 rows and 608 is the honest answer. Truncating loses a row on half of all
    sources for nothing.
    """
    return int(value / 2 + 0.5) * 2


def source_picture(source: Path, duration: float, work: Path
                   ) -> tuple[str | None, tuple[int, int]]:
    """The crop expression for a letterboxed source, and the size it leaves.

    One pass over three sampled frames for both answers, because every caller
    that wants the crop also wants the size it leaves, and scanning the video
    twice to learn them separately would be silly.
    """
    boxes: list[tuple[int, int, int, int]] = []
    size: tuple[int, int] | None = None
    for index, fraction in enumerate(BAR_SAMPLES):
        probe = work / f"bars{index}.png"
        try:
            extract_frame(source, probe, duration * fraction)
            with Image.open(probe) as frame:
                rgb = frame.convert("RGB")
                size = rgb.size
                boxes.append(detect_bars(rgb))
        except (RenderError, OSError) as exc:
            log.debug("bar probe at %.2f failed (%s)", fraction, exc)
    if size is None:
        raise RenderError(
            f"could not read a single frame out of {source.name} to measure it"
        )
    crop = crop_expression(boxes, size)
    if crop:
        log.info("source is letterboxed, cropping to its picture: %s", crop)
        width, height, *_ = (int(part) for part in crop.removeprefix("crop=").split(":"))
        size = (width, height)
    return crop, size


def picture_rect(size: tuple[int, int], *, ceiling: int = SAFE_TOP,
                 floor: int = VIDEO_PICTURE_BOTTOM) -> Picture:
    """Fit `size` into the band between `ceiling` and `floor`, centred but clamped.

    Two rules, and the second one is the point. The frames are fitted inside the
    band rather than only widened to 1080, so a square or portrait source cannot be
    taller than the space the words have left. And the position is centred in the
    whole canvas only as far as the band allows: `min` against `floor` is what turns
    "centred in the frame" into "centred, but never written on by the title", and
    `max` against `ceiling` does the same for the top text. A wide source is
    untouched by both, because for it the centred position already sits inside.
    """
    band = max(2, floor - ceiling)
    width, height = size
    scale = min(WIDTH / width, band / height)
    drawn_w = max(2, _even(width * scale))
    drawn_h = max(2, _even(height * scale))
    top = min((HEIGHT - drawn_h) / 2, floor - drawn_h)
    return Picture(
        width=drawn_w, height=drawn_h,
        left=max(0, _even((WIDTH - drawn_w) / 2)),
        top=max(0, _even(max(ceiling, top))),
    )



# What goes behind the frames, in the words the page and the sidecar use.
BLUR, BLACK = "blur", "black"
FILLS = (BLUR, BLACK)

# The blurred fill's two numbers, named because `recompose` below has to reproduce
# them in Pillow to preview a frame the clip was not made with. ffmpeg's `eq`
# brightness is additive on a 0..1 scale, which is why the second one is turned into
# a subtraction of 51 rather than a multiplication.
FILL_SIGMA = 28
FILL_DARKEN = 0.20


def picture_steps(source: str, out: str, *, rect: Picture,
                  fill: str = BLUR) -> list[str]:
    """The real frames laid where `rect` says, on whatever fills the rest.

    Exact numbers, not an expression. The fitting and the clamping that used to live
    in an ffmpeg `min` are `picture_rect`'s job now, because Pillow has to know the
    same rectangle: the top text is anchored to its top edge. One answer, computed
    once, used by both.

    **Blurred**, the default: a copy of the same frames, scaled to cover, blurred and
    darkened. It fills a 9:16 frame with something that belongs to the clip.

    **Black**: the same frames with every pixel painted out, which is a full frame of
    black that costs no thought about where it comes from. Not a `color` source, which
    has no natural end and would need a duration, a frame rate and a `shortest` to
    stop it; and no longer a `pad`, which was cheaper and was right only while the
    picture was guaranteed to sit inside the frame. It is not: a placed picture may
    hang off any edge, and `pad` cannot take a negative offset or an input larger than
    its output. One shape for both fills, so a placement cannot work on one and break
    the other. See D-059 and D-061.
    """
    background = (
        f"[fill]scale={WIDTH}:{HEIGHT},drawbox=t=fill:color=black[bg]"
        if fill == BLACK else
        f"[fill]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},gblur=sigma={FILL_SIGMA},"
        f"eq=brightness=-{FILL_DARKEN:.2f}[bg]"
    )
    return [
        f"[{source}]split=2[src][fill]",
        background,
        f"[src]scale={rect.width}:{rect.height}[fg]",
        # Negative offsets are ordinary here: `overlay` clips what hangs off, which
        # is exactly what a picture placed past an edge should do.
        f"[bg][fg]overlay={rect.left}:{rect.top}[{out}]",
    ]


def recompose(frame: Image.Image, rect: Picture, want: str,
              to: "Picture | None" = None) -> Image.Image:
    """One finished frame, rebuilt: a different background, a moved picture, or both.

    **For the preview, never for the clip.** Both of those things are under the
    words, so unlike the words they cannot be drawn over what is already there: to
    show either, the frame has to be built again. The one still kept per clip is
    enough, because the picture inside it is untouched pixels of the video and
    everything outside it is only fill.

    It lives here, beside the graph it is imitating, so the sigma and the darkening
    cannot drift from the ones ffmpeg is given. Black is exact: the same pixels end
    up in the same places. Blurred is close: Pillow's kernel is not ffmpeg's, and
    this is a preview saying what a frame will look like, not a frame of the clip.

    **What it cannot invent is picture the still never had.** A clip whose picture
    already hung off the frame was stored clipped, so moving it back inside shows
    black where those rows were cut. The clip itself has them, because ffmpeg starts
    from the video rather than from a still of it.
    """
    picture = frame.crop(
        (rect.left, rect.top, rect.left + rect.width, rect.top + rect.height)
    )
    target = to or rect
    if (target.width, target.height) != picture.size:
        picture = picture.resize((max(1, target.width), max(1, target.height)),
                                 Image.LANCZOS)
    if want == BLACK:
        canvas = Image.new(frame.mode, frame.size, "black")
    else:
        wide = max(WIDTH / picture.width, HEIGHT / picture.height)
        cover = picture.resize(
            (max(1, round(picture.width * wide)), max(1, round(picture.height * wide))),
            Image.LANCZOS,
        )
        left = (cover.width - WIDTH) // 2
        top = (cover.height - HEIGHT) // 2
        canvas = cover.crop((left, top, left + WIDTH, top + HEIGHT))
        canvas = canvas.filter(ImageFilter.GaussianBlur(FILL_SIGMA))
        drop = round(255 * FILL_DARKEN)
        canvas = Image.eval(canvas.convert("RGB"), lambda v: max(0, v - drop))
        canvas = canvas.convert(frame.mode)
    # Negative coordinates clip, the way `overlay` does in the graph.
    canvas.paste(picture, (target.left, target.top))
    return canvas


def render_video_clip(
    source: Path, overlay: Path, duration: float, dest: Path, *, work: Path,
    moving: list[stickers.Sticker] | None = None, base: Path | None = None,
    crop: str | None = None, rect: Picture | None = None, fill: str = BLUR,
) -> Path:
    """Real video frames, blurred fill to 9:16, text overlay burned on top.

    A letterboxed source is cropped to its picture first, or its own black bars
    would sit inside our blurred fill as hard seams.

    `base` asks for one extra still: the same frame with **no text on it**, which
    is what the live word preview draws over. Written after the clip and never
    allowed to fail it. See TASKS.md T-036.
    """
    fade_out_start = max(0.0, duration - FADE_OUT)
    # `rect` and `crop` are worked out together by whoever needed the rectangle
    # first, which is `pipeline.produce`: Pillow anchors the top text to it, so it
    # exists before this is called. The default is for callers that have no words
    # to place and so never measured, which today means the tests.
    if rect is None:
        crop, size = source_picture(source, duration, work)
        rect = picture_rect(size)
    graph = [
        *([f"[0:v]{crop}[cut]"] if crop else []),
        *picture_steps("cut" if crop else "0:v", "base", rect=rect, fill=fill),
        "[base][1:v]overlay=0:0[merged]",
    ]
    # Source first, text overlay second, so animated stickers start at input two.
    # Here there is no zoom to ride: the text overlay is composited at 0:0 as well,
    # so the animated ones land in the same coordinate space as the pasted ones.
    steps, merged = _moving_chain(moving or [], "merged", (WIDTH, HEIGHT), first=2)
    graph += steps
    graph += [
        f"[{merged}]fps={FPS},setsar=1,"
        f"fade=t=out:st={fade_out_start:.3f}:d={FADE_OUT},format=yuv420p[v]",
    ]

    def build(audio_chain: str) -> list[str]:
        return [
            ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(source),
            "-i", str(overlay),
            *_moving_inputs(moving or []),
            "-filter_complex", ";".join([*graph, f"[0:a]{audio_chain}[a]"]),
            "-map", "[v]", "-map", "[a]",
            "-t", f"{duration:.3f}",
            *_encode_args(duration),
            str(dest),
        ]

    _run_with_audio(build, duration)
    if base is not None:
        # Deliberately a second invocation rather than a second output mapped off
        # the same graph. One graph would be cheaper by a decode, and it would also
        # mean a preview still that could not be written taking the clip down with
        # it. The clip is the thing that matters; this is a convenience.
        try:
            background_still(source, base, crop=crop, rect=rect, fill=fill)
        except (RuntimeError, OSError) as exc:
            # `RenderError` is a `RuntimeError`, and `OSError` covers ffmpeg having
            # gone missing between the two calls. Deliberately not `Exception`:
            # `proc.Cancelled` has to keep travelling, because a render somebody
            # stopped must not quietly finish writing files.
            log.warning("no preview background written: %s", exc)
    return dest


def background_still(source: Path, dest: Path, *, crop: str | None,
                     rect: Picture, at: float = 0.5, fill: str = BLUR) -> Path:
    """One 9:16 frame, its fill and all, with nothing of ours drawn on it.

    The same filters `render_video_clip` uses, minus the overlay, so the words
    drawn over this land exactly where they land in the clip. `crop` and `rect` are
    passed in rather than worked out again: finding them means scanning the video,
    and the caller has already paid for that.
    """
    graph = ";".join([
        *([f"[0:v]{crop}[cut]"] if crop else []),
        *picture_steps("cut" if crop else "0:v", "out", rect=rect, fill=fill),
    ])
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run([
        ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{max(0.0, at):.3f}", "-i", str(source),
        "-filter_complex", graph, "-map", "[out]",
        "-frames:v", "1", "-update", "1", str(dest),
    ])
    return dest


def extract_frame(clip: Path, dest: Path, at: float) -> Path:
    """Pull a single full resolution still out of a finished clip.

    Checking a layout change should not require opening a video player, so this
    exists for eyeballing the result. `-ss` before `-i` seeks on the input, which
    is fast and accurate enough on a clip this short.
    """
    cmd = [
        ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{max(0.0, at):.3f}", "-i", str(clip),
        "-frames:v", "1", str(dest),
    ]
    _run(cmd)
    return dest


def video_maxrate(duration: float) -> int:
    """The kbit/s ceiling that keeps a clip of this length inside the size budget.

    Short clips are limited by quality, long ones by WhatsApp's 16 MB refusal. A
    15 second clip never comes near the budget, so it keeps the full ceiling; a 90
    second one has to fit inside about 1.2 Mbit/s.
    """
    if duration <= 0:
        return MAXRATE_CEILING
    budget = SIZE_BUDGET_BYTES * 8 / duration / 1000  # kbit/s for everything
    return max(MAXRATE_FLOOR, min(MAXRATE_CEILING, round(budget - AUDIO_BITRATE)))


def _encode_args(duration: float) -> list[str]:
    # WhatsApp re-encodes on upload, so the goal here is a file it will accept that
    # still looks clean, not an archival master.
    maxrate = video_maxrate(duration)
    return [
        "-c:v", "libx264", "-preset", "faster", "-crf", "23",
        "-maxrate", f"{maxrate}k", "-bufsize", f"{maxrate * 2}k",
        "-profile:v", "high", "-level", "4.0", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", f"{AUDIO_BITRATE}k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
    ]


# Far above any real encode (a 90 second clip takes under a minute on a small
# server), so only a wedged ffmpeg reaches it and the task ends instead of hanging.
FFMPEG_TIMEOUT = 900.0


def _run(cmd: list[str]) -> None:
    log.debug("ffmpeg %s", " ".join(cmd[1:]))
    try:
        proc = run_child(cmd, timeout=FFMPEG_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        log.error("ffmpeg did not finish within %.0fs", FFMPEG_TIMEOUT)
        raise RenderError(f"ffmpeg did not finish within {FFMPEG_TIMEOUT / 60:.0f} minutes") from exc
    if proc.returncode != 0:
        output = (proc.stderr or proc.stdout).strip()
        log.error("ffmpeg exit %s\n%s", proc.returncode, output)
        tail = output.splitlines()[-8:]
        raise RenderError("ffmpeg failed:\n  " + "\n  ".join(tail))
