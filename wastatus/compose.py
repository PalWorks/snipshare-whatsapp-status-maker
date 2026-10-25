"""Builds the still card that the clip animates.

Everything visual is drawn here with Pillow rather than with ffmpeg's drawtext,
because drawtext needs a freetype-enabled ffmpeg build and that cannot be relied
on across Linux and macOS installs.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import stickers

if TYPE_CHECKING:  # `render` imports this module, so this may only be a name here.
    from . import render

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
REGULAR = FONT_DIR / "DejaVuSans.ttf"
BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"

# Design canvas. The card is rendered at SUPER times this and downscaled by the
# Ken Burns pass, which keeps text crisp after the zoom.
WIDTH, HEIGHT = 1080, 1920
SUPER = 1.5

MARGIN = 100

# WhatsApp composites its own interface over a Status video at both ends of the
# frame: the caption across the bottom, and the avatar, name, timestamp and
# playback controls across the top. Both bands are measured from real posts, and
# nothing of ours is drawn outside SAFE_TOP..SAFE_BOTTOM in either render mode.
# tests/test_safe_zone.py measures the painted pixels rather than trusting these
# numbers to be respected. See DECISIONS.md D-014 and D-016.
SAFE_TOP = 230
SAFE_BOTTOM = 1632

# The waveform is the floor of the composition, sitting just inside SAFE_BOTTOM.
WAVE_TOP = 1450
WAVE_H = 180

# The artwork card is a fixed width, and its height follows the artwork's own
# aspect ratio so a cinemascope still is not cropped into a 16:9 box. The clamp
# keeps an unusually square image from crowding SAFE_TOP; such an image is
# centre cropped instead. See DECISIONS.md D-016.
CARD_W = WIDTH - 2 * MARGIN
CARD_H_MIN = 300
CARD_H_MAX = 620
CARD_RADIUS = 30

# The title block starts at a fixed y and the card sits a fixed gap above it, so
# the card and the title stay a tight pair while the artwork's height varies. The
# slack lands in the air below WhatsApp's header, where nothing notices it.
CARD_TITLE_TOP = 1005
CARD_GAP = 60
EYEBROW_GAP = 70
VIDEO_TITLE_TOP = 1284

# In --video mode the frames are the picture and the words are drawn over them, so
# the picture needs the same protection the card gets: the card is anchored a fixed
# gap above the title and can never be written on, while a frame centred in the
# whole 1080x1920 canvas knows nothing about the words. Centring alone is safe only
# down to 5:3; a 4:3 source reaches y=1365 and a square one y=1500, both of them
# inside the title. So the picture is centred no lower than VIDEO_PICTURE_BOTTOM,
# and anything too tall for the band above that line is fitted to the band instead
# of being cropped: a face lost off the top of a frame is worse than a margin of
# blurred fill down the sides. See DECISIONS.md D-016 for the card's version.
VIDEO_TITLE_GAP = 40
VIDEO_PICTURE_BOTTOM = VIDEO_TITLE_TOP - VIDEO_TITLE_GAP
VIDEO_PICTURE_H = VIDEO_PICTURE_BOTTOM - SAFE_TOP

# The eyebrow. It hangs a fixed gap above the **title**, in both modes, and the
# picture is what gives up the room for it: a card shrinks, frames are fitted into a
# shorter band. It used to hang off the card's top edge in card mode, so one field
# called "text above title" put a line in two different places and took the band the
# top text needed; D-075. It was silently not drawn at all in video mode until
# 2026-08-25: a box on the page that took your sentence and threw it away.
#
# It is also the one line of the layout that was never wrapped. It was designed for
# NOW PLAYING and the first sentence typed into it, 91 characters, was drawn 1989
# pixels wide into a 1080 pixel frame with 454 falling off each side, which reads as
# nothing having been drawn at all. So it wraps now, its block height is a fact the
# layout has to know, and the tracking that makes a two word label look deliberate
# is dropped once it is a sentence, where it is only noise and extra width.
EYEBROW_SIZE = 28
EYEBROW_LINE_H = 40
EYEBROW_MAX_LINES = 3
EYEBROW_TRACKING = 6
EYEBROW_TRACKED_MAX = 28   # characters, beyond which the tracking goes

# The gap is measured to the block's **bottom**, so a second line grows upwards and
# nothing below it moves. `EYEBROW_GAP` measured to the top of a single line, and
# this keeps that exact position for the one line case it was chosen for.
EYEBROW_BASE_GAP = EYEBROW_GAP - EYEBROW_LINE_H

# The one line position in video mode, which is what almost every label is.
VIDEO_EYEBROW_TOP = VIDEO_TITLE_TOP - EYEBROW_GAP

# The band under WhatsApp's own header was empty in video mode: the frames are
# centred, so there is air above them and air below them, and the words all live at
# the bottom. Asked for on 2026-08-25 as "how to insert text here?". It is its own
# field rather than a placement for the label, because a reel wants both: a hook at
# the top and the line that introduces the title at the bottom.
TOPLINE_TOP = SAFE_TOP + 30
TOPLINE_SIZE = 32
TOPLINE_LINE_H = 44
TOPLINE_MAX_LINES = 3
TOPLINE_GAP = 40           # between the block and whatever is under it
TOPLINE_TRACKED_MAX = 28

# The title's own metrics, named because the block below it is now measured rather
# than assumed to fit. Every line of it flows from the one above, and the last of
# them has to clear WhatsApp's caption band.
TITLE_SIZE = 64
TITLE_LINE_H = 78
TITLE_MAX_LINES = 3
CHANNEL_SIZE = 38
CHANNEL_LINE_H = 52
CHANNEL_MAX_LINES = 2
CHANNEL_GAP = 12
FOOTER_SIZE = 30
FOOTER_LINE_H = 42
FOOTER_MAX_LINES = 2
FOOTER_GAP = 10

# Elevation. A card floating on a blurred copy of itself needs a shadow to read
# as a card rather than as a hole.
SHADOW_OFFSET = 16
SHADOW_BLUR = 26
SHADOW_ALPHA = 150


@dataclass
class CardText:
    """Text on the card. Empty strings are simply not drawn.

    The footer and the eyebrow both default to off. A Status is a personal thing
    and instructional captions make it read like an advertisement.

    There is deliberately no URL here. The caption WhatsApp draws under the frame
    carries the link, and it is tappable, so a URL in the pixels was clutter that
    said nothing new. See DECISIONS.md D-015.
    """

    title: str
    channel: str
    footer: str = ""
    eyebrow: str = ""
    topline: str = ""


def _s(value: float) -> int:
    """Design coordinate to render coordinate."""
    return round(value * SUPER)


# The gradient that keeps white text readable over a picture. Video mode has always
# laid it over the frames; a placed card needs the same thing for the same reason,
# because a card put over the title is a picture under the words. Both callers come
# through here so the two cannot drift apart. Fractions of the canvas, because card
# mode draws at SUPER and video mode does not.
SHADE_FROM = 0.63
SHADE_ALPHA = 200
# How far above a line the shade has to start for the line to be readable on
# it. At 300 the ramp has reached about alpha 59 by the time it gets there.
SHADE_LEAD = 300


def _bottom_shade(size: tuple[int, int], from_row: int | None = None) -> Image.Image:
    """A transparent layer, darkening towards the bottom of the frame.

    `from_row` starts it higher than `SHADE_FROM`, in design coordinates. The label
    is the reason: it is anchored to the title, and a picture somebody placed
    themselves can reach down over the row it lands on, where the ramp has barely
    begun and white letters on a bright frame are unreadable. Measured at 1214 on a
    placed picture: alpha 1 out of 200. See DECISIONS.md D-075.
    """
    width, height = size
    shade = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(shade)
    top = round(height * SHADE_FROM)
    if from_row is not None:
        # A lead, not the row itself: the ramp starts at zero, so beginning it *at*
        # the label leaves the label on alpha 1 out of 200, which is what made it
        # unreadable over a bright placed picture in the first place. Starting a
        # `SHADE_LEAD` above puts real darkness under the letters.
        lead = round((from_row - SHADE_LEAD) * height / HEIGHT)
        top = max(0, min(top, lead))
    for y in range(top, height):
        ratio = (y - top) / (height - top)
        draw.line([(0, y), (width, y)], fill=(6, 8, 12, round(SHADE_ALPHA * ratio)))
    return shade


def _cover(image: Image.Image, width: int, height: int) -> Image.Image:
    """Scale and centre-crop so the image fills the box without distortion."""
    scale = max(width / image.width, height / image.height)
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        Image.LANCZOS,
    )
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


# Bar detection samples points along each row and keeps every row, so an edge is
# found to the exact pixel. Two earlier versions were worse: downscaling the other
# axis quantised bar edges to 20 pixels, and averaging along the row instead of
# sampling it destroyed the very evidence being looked for, so regularly textured
# picture read as flat. Point sampling asks the actual question: are these pixels
# along this row all the same colour?
_PROBE = 32            # points sampled along each line
_BAR_TOL = 14          # luminance distance still counted as the same flat colour
_BAR_MAX = 0.35        # never trim more than this fraction off one side


def _flat_run(lines: list[bytes]) -> int:
    """How many lines from the start are flat and the colour of the first one.

    Both conditions are needed. A bar is uniform along its length and identical to
    its neighbours, while a dark first row of real picture is rarely flat and a
    gradient is flat nowhere.
    """
    reference = sum(lines[0]) / len(lines[0])
    count = 0
    for line in lines:
        if max(line) - min(line) > _BAR_TOL:
            break
        if abs(sum(line) / len(line) - reference) > _BAR_TOL:
            break
        count += 1
    return count


def detect_bars(image: Image.Image) -> tuple[int, int, int, int]:
    """The box inside `image` that holds the picture, with flat padding removed.

    YouTube thumbnails are always 16:9, and videos are letterboxed to whatever the
    uploader exported, so a picture of another shape arrives padded with flat bars.
    Those bars otherwise appear inside our card, as dead bands in the blurred
    background, and as hard black seams in `--video` mode.

    A picture padded on all four sides defeats a single pass: a side column
    contains the top bar's pixels, so it is not flat, so the side bars go unseen
    until the top and bottom ones are gone. So a second pass runs, looking **only**
    at the axis the first pass unblocked. Re-examining an axis that was already
    trimmed would let the detector nibble: on a striped picture, removing the
    outermost stripe exposes another flat band, and so on.

    Returns the full box when there is nothing to trim, when the whole image is one
    flat colour, or when trimming would take more than `_BAR_MAX` off a side, which
    means the detection has found something that is not a bar.
    """
    outer = _detect_once(image)
    if outer == (0, 0, image.width, image.height):
        return outer

    rows_trimmed = outer[1] > 0 or outer[3] < image.height
    columns_trimmed = outer[0] > 0 or outer[2] < image.width
    if rows_trimmed and columns_trimmed:
        return outer

    cropped = image.crop(outer)
    inner = _detect_once(
        cropped, rows=not rows_trimmed, columns=not columns_trimmed
    )
    if inner == (0, 0, cropped.width, cropped.height):
        return outer
    return (
        outer[0] + inner[0], outer[1] + inner[1],
        outer[0] + inner[2], outer[1] + inner[3],
    )


def _detect_once(
    image: Image.Image, *, rows: bool = True, columns: bool = True
) -> tuple[int, int, int, int]:
    """One pass of bar detection. See `detect_bars`, which is what callers want."""
    full = (0, 0, image.width, image.height)
    if image.width < 8 or image.height < 8:
        return full

    gray = image.convert("L")
    width, height = image.width, image.height

    def edge(lines: list[bytes], span: int) -> int:
        count = _flat_run(lines)
        if count == 0 or count == span:  # nothing, or the image is entirely flat
            return 0
        return count if count / span <= _BAR_MAX else 0

    top = bottom = left = right = 0
    if rows:
        data = gray.resize((_PROBE, height), Image.NEAREST).tobytes()
        lines = [data[y * _PROBE:(y + 1) * _PROBE] for y in range(height)]
        top, bottom = edge(lines, height), edge(lines[::-1], height)
    if columns:
        data = gray.resize((width, _PROBE), Image.NEAREST).tobytes()
        lines = [
            bytes(data[r * width + x] for r in range(_PROBE)) for x in range(width)
        ]
        left, right = edge(lines, width), edge(lines[::-1], width)

    box = (left, top, width - right, height - bottom)
    if box[2] - box[0] < 8 or box[3] - box[1] < 8:
        return full
    return box


def trim_bars(image: Image.Image) -> Image.Image:
    """`image` with its padding bars cropped off, or unchanged if it has none."""
    box = detect_bars(image)
    if box == (0, 0, image.width, image.height):
        return image
    return image.crop(box)


def eyebrow_tracking(text: str) -> int:
    """Letterspacing, and only while the label is short enough to want it.

    Tracking is what makes NOW PLAYING read as a deliberate label rather than a
    stray word. On a sentence it is noise, and it is also a third of the width that
    put the first sentence anybody typed off both edges of the frame.
    """
    return EYEBROW_TRACKING if len(text) <= EYEBROW_TRACKED_MAX else 0


def _tracked_lines(text: str, size: int, tracking: int, max_lines: int) -> list[str]:
    """A letterspaced block, wrapped to the frame. Empty for no text at all.

    Measured in design coordinates once, rather than at each mode's own scale, so
    the line count the layout reserves room for and the line count that gets drawn
    cannot disagree.
    """
    if not text.strip() or max_lines < 1:
        return []
    font = ImageFont.truetype(str(BOLD), size)
    draw = ImageDraw.Draw(Image.new("L", (1, 1)))

    def measure(line: str) -> float:
        return (sum(draw.textlength(ch, font=font) for ch in line)
                + tracking * max(0, len(line) - 1))

    return _wrap(draw, text, font, WIDTH - 2 * MARGIN, max_lines, measure=measure)


def eyebrow_lines(text: str, max_lines: int = EYEBROW_MAX_LINES) -> list[str]:
    """The label above the title, wrapped to the frame. Both modes, D-075."""
    return _tracked_lines(text, EYEBROW_SIZE, eyebrow_tracking(text), max_lines)


def eyebrow_height(lines: Sequence[str]) -> int:
    return len(lines) * EYEBROW_LINE_H


def topline_tracking(text: str) -> int:
    return EYEBROW_TRACKING if len(text) <= TOPLINE_TRACKED_MAX else 0


def topline_lines(text: str, max_lines: int = TOPLINE_MAX_LINES) -> list[str]:
    """The text under WhatsApp's header, wrapped to the frame."""
    return _tracked_lines(text, TOPLINE_SIZE, topline_tracking(text), max_lines)


def topline_height(lines: Sequence[str]) -> int:
    return len(lines) * TOPLINE_LINE_H


def topline_top(anchor: int | None, lines: Sequence[str]) -> int:
    """The top of the top text block, whose bottom sits a gap above `anchor`.

    Anchored by its bottom for the same reason the label is: a second line grows
    upwards into the empty air, and a short line stays as far from WhatsApp's own
    header as the picture allows. `anchor` is the top edge of the thing below it,
    the picture in video mode and the label or card in card mode.

    `None` means nothing below is known yet, so the block falls back to the top of
    the band. That is only the case where a picture has not been measured.

    Clamped at both ends. `TOPLINE_TOP`, because a picture that starts low would
    otherwise let a long block drift down the frame with a hole above it. And
    `VIDEO_PICTURE_BOTTOM`, because a picture somebody placed themselves may start
    anywhere at all, including below the words, and the top line has to stay the top
    line. Card mode's anchors sit far above that ceiling, so it costs them nothing.
    """
    if anchor is None:
        return TOPLINE_TOP
    settled = min(anchor, VIDEO_PICTURE_BOTTOM)
    return max(TOPLINE_TOP, settled - TOPLINE_GAP - topline_height(lines))


def topline_room(limit: int) -> int:
    """How many lines of top text fit between WhatsApp's header and `limit`.

    Card mode asks, because a card is in the way and the top text cannot push it
    aside once it has been placed. A **fitted** card is not in the way: it shrinks
    for the top text in `fitted_card_height`, so this always answers at least one.
    A **placed** card can be anywhere, including too high for any line at all, and
    `topline_dropped` is what says so rather than letting it vanish. See D-075.
    """
    room = (limit - TOPLINE_GAP - TOPLINE_TOP) // TOPLINE_LINE_H
    return max(0, min(TOPLINE_MAX_LINES, room))


def top_text_floor(text: CardText) -> int:
    """The lowest row the top text block reaches, plus its gap. `SAFE_TOP` if none.

    The one number both modes need, and the reason it is named for the text rather
    than for the picture: whatever sits under the top text, frames or an artwork
    card, may not start above this row. Card mode used to ask a different question
    in a different way and got a different answer, which is how a top line could be
    dropped in silence. See DECISIONS.md D-075.
    """
    lines = topline_lines(text.topline)
    if not lines:
        return SAFE_TOP
    return TOPLINE_TOP + topline_height(lines) + TOPLINE_GAP


def video_picture_top(text: CardText) -> int:
    """The highest row the frames may reach. `SAFE_TOP` unless there is top text."""
    return top_text_floor(text)


def eyebrow_top(anchor: int, lines: Sequence[str]) -> int:
    """The top of the label block, whose bottom sits a fixed gap above `anchor`.

    Anchored by the bottom so a second line grows upwards into the empty air and
    nothing below it moves. `anchor` is the card's top in card mode and the title's
    top in video mode.
    """
    return anchor - EYEBROW_BASE_GAP - eyebrow_height(lines)


def _label_floor(text: CardText, *, title_top: int, empty: int, gap: int) -> int:
    """The lowest row a picture may reach, once the label above the title has its room.

    The label is off by default, so the picture keeps its whole band unless one was
    actually typed. That is why this takes the text rather than being a constant:
    paying 70 pixels of picture for a line nobody asked for would be the wrong trade
    on every clip that has none.
    """
    lines = eyebrow_lines(text.eyebrow)
    if not lines:
        return empty
    return eyebrow_top(title_top, lines) - gap


def video_picture_bottom(text: CardText) -> int:
    """The lowest row the frames may reach, given what is going to be drawn on them."""
    return _label_floor(text, title_top=VIDEO_TITLE_TOP,
                        empty=VIDEO_PICTURE_BOTTOM, gap=VIDEO_TITLE_GAP)


def card_height(aspect: float) -> int:
    """The card is `CARD_W` wide and as tall as the artwork's shape asks for."""
    if aspect <= 0:
        return CARD_H_MAX
    return max(CARD_H_MIN, min(CARD_H_MAX, round(CARD_W / aspect)))


def card_floor(text: "CardText | None" = None) -> int:
    """The lowest row the card may reach, once the label above the title has its room.

    The card gives way for the label exactly as the frames do in video mode, which
    is what makes "text above title" mean the same thing in both. It used to hang
    off the card's top edge here and off the title's in video mode, so one field
    put a line in two different places. See DECISIONS.md D-075.
    """
    if text is None:
        return CARD_WORDS_BOTTOM
    return _label_floor(text, title_top=CARD_TITLE_TOP,
                        empty=CARD_WORDS_BOTTOM, gap=CARD_GAP)


def fitted_card_height(aspect: float, text: "CardText | None" = None) -> int:
    """The card's height, shrunk when the words above and below it need the room.

    A fitted card is anchored above the title, so the only way to clear the top text
    is to be shorter. The shrink is small and it is the whole of what makes top text
    reliable in card mode: at `CARD_H_MAX` the card's top lands on row 325, and one
    line of top text needs 344, so nineteen pixels of artwork were the difference
    between a line drawn and a line dropped in silence.

    Never below `CARD_H_MIN`. Past that the artwork stops being an artwork, and the
    honest answer is to say the top text does not fit rather than to keep shrinking;
    `topline_dropped` is what asks.
    """
    want = card_height(aspect)
    if text is None:
        return want
    room = card_floor(text) - top_text_floor(text)
    return max(CARD_H_MIN, min(want, room))


def card_box(card_h: int, text: "CardText | None" = None) -> tuple[int, int, int, int]:
    """The card's rectangle in design coordinates, anchored above the title."""
    top = card_floor(text) - card_h
    return MARGIN, top, MARGIN + CARD_W, top + card_h


def card_aspect(artwork: Path) -> float:
    """The artwork's shape once its padding bars are off, which is the shape the
    card's height follows.

    Opened a second time rather than guessed: the render needs the panel's rectangle
    for the sidecar, `build_card` needs it for the drawing, and if those two were
    ever different numbers the page would draw its box around a card that is not
    there. Bar detection costs a fraction of a second, once per clip.
    """
    with Image.open(artwork) as opened:
        art = trim_bars(opened.convert("RGB"))
        return art.width / art.height


def card_rect(aspect: float, framing: "render.Framing | None" = None,
              text: "CardText | None" = None) -> tuple[int, int, int, int]:
    """The card's rectangle, fitted above the title or put where somebody put it.

    `framing` is the same three fractions everything placed uses: the centre, and
    the **width**, of the whole card. See D-024 and D-062. The height is not a
    choice here either: a placed card is the fitted card scaled, so the crop an
    unusually square artwork gets is the crop it keeps, rather than changing shape
    under a hand that is only moving it.

    That also makes the round trip exact. A page switching Fitted to Placed reads
    the placement back off this rectangle, and at `size = CARD_W / WIDTH` the
    arithmetic below returns the fitted box itself, to the pixel.
    """
    fitted = fitted_card_height(aspect, text)
    if framing is None:
        return card_box(fitted, text)
    width = max(1, round(framing.size * WIDTH))
    height = max(1, round(fitted * width / CARD_W))
    left = round(framing.x * WIDTH - width / 2)
    top = round(framing.y * HEIGHT - height / 2)
    return left, top, left + width, top + height


# Where the label may hang from once the card can be anywhere. The words follow the
# card, which is what was asked for, so both ends of the card's travel are pinned to
# what the words can survive: high enough that one line of label still clears
# WhatsApp's own header, and low enough that the label cannot be drawn across the
# title. Every fitted card already sits between the two, so nothing made before this
# moves by a pixel. See DECISIONS.md D-062.
CARD_WORDS_TOP = SAFE_TOP + EYEBROW_BASE_GAP + EYEBROW_LINE_H
CARD_WORDS_BOTTOM = CARD_TITLE_TOP - CARD_GAP


class CardWords(NamedTuple):
    """Where card mode's two optional blocks go, for a card whose top edge is `top`.

    One function rather than two copies of the arithmetic. `build_card` used to work
    this out inline and `tests/test_safe_zone.py` worked it out again to check it,
    which held only for as long as nobody changed one of them. D-075 changed the
    drawing and the copy in the test kept passing, still describing the layout that
    had just been replaced: green tests guaranteeing that text stays out of
    WhatsApp's furniture, measured against a frame the renderer no longer draws.
    Found in the audit of 2026-08-31. See DECISIONS.md D-078.
    """

    eyebrow: list[str]
    eyebrow_top: int
    topline: list[str]
    topline_at: int


def card_words(text: CardText, top: int) -> CardWords:
    """The label and the top text as card mode lays them out.

    The label hangs off the **title**, as it does in video mode, and the top text
    hangs off the card. `card_words_anchor` rather than `top` itself, because a
    placed card may be anywhere at all, including off the top of the frame and
    below the title, and the top text has to stay the top line.
    """
    anchor = card_words_anchor(top)
    brow = eyebrow_lines(text.eyebrow)
    head = topline_lines(text.topline, max_lines=topline_room(anchor))
    return CardWords(
        eyebrow=brow,
        eyebrow_top=eyebrow_top(CARD_TITLE_TOP, brow),
        topline=head,
        topline_at=topline_top(anchor, head),
    )


def topline_dropped(text: CardText, *, video: bool, top: int | None) -> int:
    """How many lines of top text will not be drawn. Zero when it all fits.

    The one thing on the frame that can vanish without trace. It is wrapped to
    whatever room is left above the picture, and when that room is nothing the block
    is empty and the render draws it as nothing at all: no gap, no ellipsis, no
    complaint. The words stay in the box and go into the sidecar, so afterwards the
    page compares them against themselves, finds no difference, and reports that the
    clip is up to date with words it never drew.

    Which is a lie the tool told for as long as the field existed. Now the callers
    ask, and say so. See DECISIONS.md D-075.

    `top` is the row the thing below the text begins on: the picture in video mode,
    the card in card mode, and whatever a hand placed it at when it was placed.
    Video mode moves its own picture out of the way and so never drops a line; a
    fitted card shrinks to make room and does not either. What is left is a card or
    a picture somebody pinned somewhere too high, which is exactly the case worth a
    sentence on screen.
    """
    lines = topline_lines(text.topline)
    if not lines or video or top is None:
        return 0
    return max(0, len(lines) - len(card_words(text, top).topline))


def card_words_anchor(top: int) -> int:
    """The row the label sits above, for a card whose own top edge is `top`.

    The label follows the card up and down the frame, and stops following it at the
    two ends, because past either end the alternative is a line drawn where it
    cannot be read: under WhatsApp's header, or across the title.
    """
    return min(max(top, CARD_WORDS_TOP), CARD_WORDS_BOTTOM)


def _atoms(text: str) -> list[str]:
    """Where a line is allowed to break: at whitespace, and after a hyphen.

    Typesetting breaks after a hyphen, and titles from YouTube are full of them:
    `Prince Rama Varma-VARA LEELA GANA LOLA` is one unbreakable token to a naive
    splitter, which forces an over-long line and breaks the name somewhere else
    instead of at its own boundary.
    """
    atoms: list[str] = []
    for word in text.split():
        atoms.extend(part for part in re.split(r"(?<=-)(?=\S)", word) if part)
    return atoms


def _join(left: str, right: str) -> str:
    """Add an atom to a line, without inserting a space after a hyphen.

    Only a hyphen joined to the word before it: `Varma-` + `VARA`. A dash standing
    on its own between spaces, `Ed Sheeran - Shape of You`, keeps the space after
    it. Until 2026-10-24 it did not, and every "Artist - Song" title on a card read
    "Artist -Song". Found reading a frame made through the browser extension. D-086.
    """
    if not left:
        return right
    attached = left.endswith("-") and len(left) > 1 and not left[-2].isspace()
    return left + right if attached else f"{left} {right}"


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int,
          max_lines: int, measure=None) -> list[str]:
    """`measure` is how wide a candidate line is, defaulting to the font's own
    answer. The eyebrow passes its own, because letterspacing is width that
    `textlength` cannot see and wrapping without it overflows by a third."""
    width = measure or (lambda line: draw.textlength(line, font=font))
    atoms = _atoms(text)
    lines: list[str] = []
    current = ""
    used = 0
    for index, atom in enumerate(atoms):
        candidate = _join(current, atom)
        if not current or width(candidate) <= max_width:
            current = candidate
            used = index + 1
            continue
        lines.append(current)
        if len(lines) == max_lines:
            current = ""
            break
        current = atom
        used = index + 1
    if current and len(lines) < max_lines:
        lines.append(current)
    if not lines:
        return [""]
    # Ellipsise the final line if anything was dropped.
    if used < len(atoms):
        # The longest prefix that still fits with its ellipsis, found by halving
        # rather than one character at a time: each measure is of the whole line,
        # so a long line shortened by single characters costs its length squared.
        last = lines[-1]
        low, high = 0, len(last)
        while low < high:
            mid = (low + high + 1) // 2
            if width(last[:mid].rstrip() + "...") <= max_width:
                low = mid
            else:
                high = mid - 1
        lines[-1] = last[:low].rstrip() + "..."
    return lines


def _tracked(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, tracking: int) -> None:
    x, y = xy
    total = sum(draw.textlength(ch, font=font) for ch in text) + tracking * (len(text) - 1)
    x -= total / 2
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking


def covered_by_whatsapp(decal: stickers.Placed) -> bool:
    """Would WhatsApp's own header or caption sit on top of this?

    The bands are `SAFE_TOP` and `SAFE_BOTTOM`, the same two the text layer is kept
    out of. A sticker is allowed in there, because a person putting one in the
    corner has made a choice, but it is worth saying so once.

    The height comes from the thing itself: a drawing answers "square", which is
    what OpenMoji is, and a line of free text answers with its own shape, which is
    a great deal wider than it is tall. Assuming square for a line warned about
    text that was nowhere near the band.
    """
    half = decal.size * WIDTH * decal.aspect / 2
    top = decal.y * HEIGHT - half
    bottom = decal.y * HEIGHT + half
    return top < SAFE_TOP or bottom > SAFE_BOTTOM


def build_card(
    artwork: Path, text: CardText, dest: Path,
    *, decals: list[stickers.Sticker] | None = None,
    framing: "render.Framing | None" = None,
) -> Path:
    """The still card, from the video's own artwork.

    `framing` puts the artwork panel somewhere other than the place the layout
    would have chosen. None is that place, and is what every card made before D-062
    was made with. The words above the panel follow it; the title and everything
    under it does not, because those are anchored to the bottom of the frame and
    have never had anything to do with where the artwork is.
    """
    # Trim first, so the bars an uploader padded their thumbnail with appear
    # neither inside the card nor as dead bands in the blurred background.
    art = trim_bars(Image.open(artwork).convert("RGB"))
    left, top, right, bottom = card_rect(art.width / art.height, framing, text)

    canvas = _cover(art, _s(WIDTH), _s(HEIGHT)).filter(
        ImageFilter.GaussianBlur(_s(42))
    ).convert("RGBA")

    # Darkening scrim, heavier at the bottom where the text sits.
    scrim = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    scrim_draw = ImageDraw.Draw(scrim)
    for y in range(canvas.height):
        ratio = y / canvas.height
        scrim_draw.line(
            [(0, y), (canvas.width, y)], fill=(6, 8, 12, round(120 + 90 * ratio))
        )
    canvas = Image.alpha_composite(canvas, scrim)

    # Elevation: a blurred black rounded rectangle, offset downwards, behind the
    # card. Without it the card reads as a hole cut into its own blur.
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [
            (_s(left), _s(top + SHADOW_OFFSET)),
            (_s(right) - 1, _s(bottom + SHADOW_OFFSET) - 1),
        ],
        radius=_s(CARD_RADIUS),
        fill=(0, 0, 0, SHADOW_ALPHA),
    )
    canvas = Image.alpha_composite(
        canvas, shadow.filter(ImageFilter.GaussianBlur(_s(SHADOW_BLUR)))
    )

    # Artwork card with rounded corners.
    card = _cover(art, _s(right - left), _s(bottom - top)).convert("RGBA")
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), (card.width - 1, card.height - 1)], radius=_s(CARD_RADIUS), fill=255
    )
    canvas.paste(card, (_s(left), _s(top)), mask)

    # A placed card can be underneath the words, and the scrim above it is not: it
    # goes on before the card, so the title would be white on whatever the artwork
    # happens to be there. This is what video mode lays over its own frames, and it
    # is drawn only where it is needed, so a card that stops where a fitted one
    # stops is untouched by it.
    if framing is not None and bottom > CARD_WORDS_BOTTOM:
        canvas = Image.alpha_composite(canvas, _bottom_shade(canvas.size))

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(
        [(_s(left), _s(top)), (_s(right) - 1, _s(bottom) - 1)],
        radius=_s(CARD_RADIUS),
        outline=(255, 255, 255, 46),
        width=max(1, _s(1.5)),
    )
    # The same arrangement as video mode, which is the point: the label hangs off
    # the **title** in both, so "text above title" puts a line in one place rather
    # than two, and the picture is what gives way for it. The top text then has the
    # whole band above the card to itself instead of competing with the label for
    # it. A fitted card has already shrunk to leave room for both, in `card_rect`.
    #
    # `card_words_anchor` rather than `top` for the top text, because a placed card
    # may be anywhere at all, including off the top of the frame and below the
    # title, and the top text has to stay the top text. It is the card's own edge
    # everywhere a fitted card can reach, so the fitted layout is untouched.
    words = card_words(text, top)
    _draw_text_layer(
        draw, text, title_top=CARD_TITLE_TOP,
        eyebrow_top=words.eyebrow_top, eyebrow=words.eyebrow,
        topline=words.topline, topline_at=words.topline_at,
        bottom=WAVE_TOP,
    )

    canvas = Image.alpha_composite(canvas, overlay)
    # Stickers go on last, over everything, because that is what a sticker is.
    stickers.paste(canvas, decals or [])
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(dest, "PNG")
    return dest


def build_overlay(
    text: CardText, dest: Path, *, decals: list[stickers.Sticker] | None = None,
    picture_top: int | None = None, picture_bottom: int | None = None,
) -> Path:
    """Transparent text layer for --video mode, where the frames are the backdrop.

    `picture_top` is the row the real frames begin on, which `render.picture_rect`
    works out. The top text hangs off it: without it the block sits against
    WhatsApp's own header with a void beneath, which on a 16:9 source measured 278
    pixels of nothing between the words and the picture they belong to.
    """
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    # Video mode has no card in the way: the frames give up the room instead, at
    # both ends, so both blocks are wrapped to their full allowance.
    brow = eyebrow_lines(text.eyebrow)
    head = topline_lines(text.topline)
    # A soft base so text stays readable over bright frames, started at the label
    # when there is one: a placed picture can reach down over the row it lands on.
    brow_at = eyebrow_top(VIDEO_TITLE_TOP, brow) if brow else None
    # Only when the picture actually reaches the row the label lands on. A fitted
    # picture stops above it and is untouched by this; a placed one can be anywhere,
    # and white letters on a bright frame with no scrim under them are not readable.
    reaches = (brow_at is not None and picture_bottom is not None
               and picture_bottom > brow_at)
    canvas = Image.alpha_composite(
        canvas, _bottom_shade(canvas.size, brow_at if reaches else None))
    draw = ImageDraw.Draw(canvas)
    _draw_text_layer(
        draw, text, title_top=VIDEO_TITLE_TOP,
        eyebrow_top=eyebrow_top(VIDEO_TITLE_TOP, brow), eyebrow=brow,
        topline=head, topline_at=topline_top(picture_top, head),
        bottom=SAFE_BOTTOM, scale=1 / SUPER,
    )
    stickers.paste(canvas, decals or [])
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, "PNG")
    return dest


def _draw_text_layer(
    draw: ImageDraw.ImageDraw,
    text: CardText,
    *,
    title_top: int,
    eyebrow_top: int | None,
    bottom: int,
    scale: float = 1.0,
    eyebrow: Sequence[str] = (),
    topline: Sequence[str] = (),
    topline_at: int = TOPLINE_TOP,
) -> None:
    """Draw the text block downwards from `title_top`.

    Every element flows from the one above it rather than sitting at a fixed
    coordinate, so a three line title cannot push anything into the reserved
    bottom band. `title_top` is chosen per mode such that the worst case block,
    three title lines plus channel plus footer, still clears `SAFE_BOTTOM`.

    `eyebrow_top` is where the label block starts, and `eyebrow` is that block
    already wrapped. Both are passed in rather than worked out here because the
    caller is the one that knows the room: card mode has a card in the way and
    ellipsises to fit above it, while video mode moves the picture instead. None
    turns it off entirely. `topline` is the same arrangement for the block under
    WhatsApp's header, and `topline_at` is where it starts: its bottom is anchored a
    gap above whatever is below it, so a short line sits low and far from the header
    rather than up against it.

    `bottom` is the last row this block may touch: `WAVE_TOP` in card mode, where
    the waveform is the floor, and `SAFE_BOTTOM` in video mode. The second line and
    the footer are wrapped into whatever room is left after the title has taken what
    it needs, which is why it has to be known here. Both were single unwrapped
    `draw.text` calls until 2026-08-25, and a channel name of ordinary length was
    drawn 1253 pixels wide in a 1080 pixel frame.
    """

    def px(value: float) -> int:
        return round(value * SUPER * scale)

    def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(path), max(1, round(size * SUPER * scale)))

    centre = px(WIDTH / 2)
    white = (255, 255, 255, 255)

    def block(lines, at: float, size: int, colour, step: int, tracking: int = -1):
        """Draw `lines` downwards from design row `at`, and return the next row."""
        face = font(BOLD if tracking >= 0 else REGULAR, size)
        for line in lines:
            if tracking >= 0:
                _tracked(draw, (centre, px(at)), line, face, colour, px(tracking))
            else:
                draw.text((centre, px(at)), line, font=face, fill=colour, anchor="ma")
            at += step
        return at

    if topline:
        block(topline, topline_at, TOPLINE_SIZE, (255, 255, 255, 200),
              TOPLINE_LINE_H, tracking=topline_tracking(text.topline))

    if eyebrow_top is not None and eyebrow:
        block(eyebrow, eyebrow_top, EYEBROW_SIZE, (255, 255, 255, 150),
              EYEBROW_LINE_H, tracking=eyebrow_tracking(text.eyebrow))

    # Three lines fit, which keeps long compound titles from being ellipsised
    # mid-name.
    title_font = font(BOLD, TITLE_SIZE)
    lines = _wrap(draw, text.title, title_font, px(WIDTH - 2 * MARGIN),
                  TITLE_MAX_LINES)
    y = block(lines, title_top, TITLE_SIZE, white, TITLE_LINE_H)

    # What is left, in design rows, once the title has taken what it needed. The
    # footer keeps one line back for itself so a long channel name cannot eat the
    # whole remainder and leave it nowhere to go.
    def room(at: float, step: int, keep: int, cap: int) -> int:
        return max(1, min(cap, int((bottom - at - keep) // step)))

    if text.channel:
        y += CHANNEL_GAP
        keep = FOOTER_GAP + FOOTER_LINE_H if text.footer else 0
        wrapped = _wrap(draw, text.channel, font(REGULAR, CHANNEL_SIZE),
                        px(WIDTH - 2 * MARGIN),
                        room(y, CHANNEL_LINE_H, keep, CHANNEL_MAX_LINES))
        y = block(wrapped, y, CHANNEL_SIZE, (255, 255, 255, 185), CHANNEL_LINE_H)

    if text.footer:
        y += FOOTER_GAP
        wrapped = _wrap(draw, text.footer, font(REGULAR, FOOTER_SIZE),
                        px(WIDTH - 2 * MARGIN),
                        room(y, FOOTER_LINE_H, 0, FOOTER_MAX_LINES))
        block(wrapped, y, FOOTER_SIZE, (255, 255, 255, 140), FOOTER_LINE_H)
