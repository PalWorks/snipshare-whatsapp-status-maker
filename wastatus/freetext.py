"""Free text placed on the frame: a line you write, drag and resize like a sticker.

The card's own wording is laid out by `compose` and cannot be dragged, because its
position is the layout's answer rather than yours. This is the other thing: one line
that goes where you put it, at the size you drag it to.

**It is drawn here, by Pillow, and never by the browser.** The page places a picture
of the line, the renderer pastes the same line at the frame's own scale, and both
come through `render`. That is what keeps the box you drag and the pixels ffmpeg
burns in the same shape: a browser drawing its own text would break the line
somewhere else, kern it differently, and put the words a few pixels from where the
clip puts them. See DECISIONS.md D-021 and D-024 for why a placed thing is only ever
a rectangle to the page.

**Coordinates are fractions of the frame**, exactly as for a sticker: `x` and `y`
are the centre, and `size` is the **width of the whole picture**, so a longer line
at the same size is set in a smaller face. Dragging the corner is what makes it big.

**Emoji are pictures, not letters.** The face this is set in is DejaVu, which is
bundled so that Linux and macOS draw the same pixels, and DejaVu has no emoji at
all: every one typed into the box used to come out as an empty rectangle. They are
drawn from the OpenMoji library instead, the same 4,495 pictures the sticker picker
already installs, which keeps that promise intact: the clip looks the same on both
machines and on a machine with no emoji font at all. See DECISIONS.md D-065.
"""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

log = logging.getLogger("wastatus")

MAX_CHARS = 120

# Measured at this face and scaled from it. Large enough that the rounding in a
# glyph's advance is noise against the answer, small enough to measure instantly.
REFERENCE = 200
MIN_PX = 8  # below this a face has no shape left to read

# A drop shadow, because unlike the card's wording this can land anywhere: over a
# white sky, over a face, over a caption band. Both numbers are fractions of the
# face, so a line stays as legible small as it is large.
SHADOW_BLUR = 0.05
SHADOW_DROP = 0.03
SHADOW_ALPHA = 170

_SPACES = re.compile(r"\s+")

# -- what counts as a picture ----------------------------------------------

# Deliberately narrow. OpenMoji ships a drawing of a hyphen and of a full stop,
# and a line of words is not improved by having its punctuation replaced with
# pictures of punctuation. So only these four shapes are pictures: the pictograph
# planes, a two letter flag, a keycap, and one of the older symbols wearing the
# variation selector that asks for emoji presentation. A bare (c), a star or a
# quaver is left to DejaVu, which has all three and sets them as text.
_PICTOGRAPH = "[\U0001F000-\U0001FAFF]"
_FLAG = "[\U0001F1E6-\U0001F1FF]{2}"
_KEYCAP = "[0-9#*]\ufe0f?\u20e3"
_ASKED_FOR = "[\u00a9\u00ae\u2000-\u3300]\ufe0f"
# A skin tone or a variation selector belongs to the character before it, and a
# zero width joiner glues two whole emoji into one, as in a family or a flag with
# a pattern on it. Matched together, so one picture is looked up rather than four.
_MODIFIER = "[\U0001F3FB-\U0001F3FF\ufe0f]"
_ONE = f"(?:{_FLAG}|{_PICTOGRAPH}|{_KEYCAP}|{_ASKED_FOR})(?:{_MODIFIER})*"
EMOJI = re.compile(f"{_ONE}(?:\u200d{_ONE})*")

# The square an emoji is drawn in, and where it sits, as fractions of the face.
# A picture has no baseline of its own, so it is hung off the letters': its bottom
# edge a little below theirs, which is where a reader expects to find it. Both
# numbers are fractions, so an emoji scales with the line exactly as a letter does,
# and the square stays inside the ascent and descent the box is already measured
# from. The side bearing is what stops it touching the word beside it.
EMOJI_EM = 1.0
EMOJI_DROP = 0.12
EMOJI_SIDE = 0.05


@lru_cache(maxsize=512)
def _picture(cluster: str) -> Path | None:
    """The OpenMoji file for one cluster, or None if the library has no such thing.

    OpenMoji names each file after the codepoints in it, in upper case hex joined
    with hyphens. It leaves the variation selector out of nearly every name and
    keeps it in the keycaps, so both spellings are tried, in that order.

    Cached, because this is asked once per emoji per keystroke while the preview
    follows your typing. `cache_clear` after installing the library, which is what
    the tests do and what a person does by restarting the tool.
    """
    from . import stickers  # `stickers` imports this module, so not at the top

    codes = [f"{ord(ch):04X}" for ch in cluster]
    names = ["-".join(codes)]
    plain = [code for code in codes if code != "FE0F"]
    if plain and plain != codes:
        names.append("-".join(plain))
    folder = stickers.library_dir()
    for name in names:
        found = folder / f"{name}.png"
        if found.is_file():
            return found
    return None


def _chunks(line: str):
    """The line as (run, is_emoji) pairs, left to right, nothing left out."""
    at = 0
    for found in EMOJI.finditer(line):
        if found.start() > at:
            yield line[at:found.start()], False
        yield found.group(0), True
        at = found.end()
    if at < len(line):
        yield line[at:], False


def _layout(line: str, font: ImageFont.FreeTypeFont, size: int
            ) -> tuple[list[tuple[str, object, float, float]], float]:
    """What to draw, where, and how wide it all comes to.

    One function for both `measure` and `render`, because the width the page draws
    its box from and the width the picture is drawn to are the same number, and a
    second copy of this arithmetic is a second answer to it.

    An emoji with no picture behind it is left out rather than drawn as the empty
    rectangle the font would give, which is not a character anybody typed.
    """
    pieces: list[tuple[str, object, float, float]] = []
    x = 0.0
    for run, is_emoji in _chunks(line):
        if is_emoji:
            file = _picture(run)
            if file is None:
                log.info("no picture for %r, so it is left out of the line", run)
                continue
            wide = size * (EMOJI_EM + 2 * EMOJI_SIDE)
            pieces.append(("emoji", file, x, wide))
        else:
            wide = _ink(run, font)
            pieces.append(("text", run, x, wide))
        x += wide
    return pieces, x


def _art(file: Path, square: int) -> Image.Image:
    with Image.open(file) as opened:
        art = opened.convert("RGBA")
    return art if art.size == (square, square) else art.resize(
        (square, square), Image.LANCZOS)


def clean(text: str) -> str:
    """One line, trimmed to what will be drawn. Empty if there is nothing to draw.

    Newlines fold into spaces rather than wrapping. A placed line is sized by its
    width, so a second line would halve the face on a drag nobody made; two lines
    are two texts, each dragged where it belongs.
    """
    return _SPACES.sub(" ", str(text or "")).strip()[:MAX_CHARS]


def _face(size: int) -> ImageFont.FreeTypeFont:
    # Imported here, not at the top: `compose` imports `stickers`, `stickers`
    # imports this, and this needs the same font file the card is set in. One
    # deferred import is cheaper than a second copy of the path.
    from .compose import BOLD

    return ImageFont.truetype(str(BOLD), max(MIN_PX, size))


def _pad(size: int) -> int:
    """Room around the line for the shadow to fall into."""
    return max(1, round(size * (SHADOW_BLUR * 3 + SHADOW_DROP)))


def _ink(line: str, font: ImageFont.FreeTypeFont) -> float:
    return ImageDraw.Draw(Image.new("L", (1, 1))).textlength(line, font=font)


def measure(text: str) -> tuple[float, float]:
    """The picture's width and height at `REFERENCE`, before any scaling.

    Only the shape of it, so this costs a measurement rather than a render. It is
    what says how tall a placed line is without drawing one, which is the question
    "is this under WhatsApp's caption" needs answered.
    """
    line = clean(text)
    if not line:
        return 0.0, 0.0
    font = _face(REFERENCE)
    ascent, descent = font.getmetrics()
    pad = _pad(REFERENCE)
    _, ink = _layout(line, font, REFERENCE)
    if not ink:
        return 0.0, 0.0
    # The height is still the face's own. An emoji is a square of one em hung
    # a little below the baseline, which lands inside the ascent and descent that
    # were already being measured, so a line with pictures in it is exactly as tall
    # as the same line without them.
    return ink + 2 * pad, ascent + descent + 2 * pad


def aspect(text: str) -> float:
    """Height over width. `1.0` for nothing, which is a sticker's shape."""
    width, height = measure(text)
    return height / width if width else 1.0


def render(text: str, width: int) -> Image.Image:
    """The line, drawn white with its shadow, exactly `width` pixels across.

    The face is worked out from the width rather than given: that is the contract
    the page is holding to when it scales the same picture into the same fraction
    of a smaller frame. Both callers come through here, so neither can drift.
    """
    line = clean(text)
    if not line:
        raise ValueError("there is nothing to draw")
    width = max(1, int(width))

    natural, _ = measure(text)
    if not natural:
        # Everything in the line was an emoji this machine has no picture for.
        raise ValueError(
            "there is no picture for that emoji. The emoji come from the same "
            "library the stickers do: run scripts/setup_stickers.sh to install it")
    size = max(MIN_PX, round(REFERENCE * width / natural))
    font = _face(size)
    ascent, descent = font.getmetrics()
    pad = _pad(size)
    baseline = pad + ascent
    pieces, ink = _layout(line, font, size)

    canvas = Image.new(
        "RGBA", (round(ink) + 2 * pad, ascent + descent + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    pictures = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ink_layer = ImageDraw.Draw(canvas)
    shade = ImageDraw.Draw(shadow)
    drop = round(size * SHADOW_DROP)
    square = max(1, round(size * EMOJI_EM))

    for kind, what, x, _wide in pieces:
        left = pad + x
        if kind == "text":
            shade.text((left, baseline + drop), what, font=font,
                       fill=(0, 0, 0, SHADOW_ALPHA), anchor="ls")
            continue
        art = _art(what, square)
        at = (round(left + size * EMOJI_SIDE),
              round(baseline + size * EMOJI_DROP) - square)
        # The picture's own silhouette, in the same black at the same offset, so a
        # drawing gets the shadow that keeps a letter readable over a bright frame.
        shadow.paste(
            (0, 0, 0, 255), (at[0], at[1] + drop),
            art.getchannel("A").point(lambda level: level * SHADOW_ALPHA // 255),
        )
        # `paste` rather than `alpha_composite`, which refuses a box that reaches
        # past an edge instead of clipping. One layer for all of them, composited
        # once below, so the pictures land over the blur rather than through it.
        pictures.paste(art, at, art)

    canvas.alpha_composite(shadow.filter(
        ImageFilter.GaussianBlur(max(1, round(size * SHADOW_BLUR)))))
    for kind, what, x, _wide in pieces:
        if kind == "text":
            ink_layer.text((pad + x, baseline), what, font=font,
                           fill=(255, 255, 255, 255), anchor="ls")
    canvas.alpha_composite(pictures)

    # The face was chosen for the ink, and the shadow's margin sits outside it, so
    # the picture lands a percent or two wide. Trimmed to the width that was asked
    # for rather than left over, because that width is the fraction of the frame
    # the page has already drawn a box around.
    if canvas.width != width:
        height = max(1, round(canvas.height * width / canvas.width))
        canvas = canvas.resize((width, height), Image.LANCZOS)
    return canvas


def to_png(text: str, width: int) -> bytes:
    """`render`, as the bytes the page places. PNG, for the transparency."""
    buffer = io.BytesIO()
    render(text, width).save(buffer, "PNG", optimize=True)
    return buffer.getvalue()


@dataclass
class FreeText:
    """One placed line. Fractions of the frame, centre anchored, like a sticker."""

    text: str
    x: float = 0.5
    y: float = 0.45
    size: float = 0.6
    rotation: float = 0.0

    kind = "text"
    moving = False  # nothing here animates, so it is always pasted by Pillow

    @property
    def label(self) -> str:
        """What the run record calls it. The words themselves are in the sidecar."""
        return "text"

    @property
    def aspect(self) -> float:
        return aspect(self.text)

    def art(self, width: int) -> Image.Image:
        return render(self.text, width)

    def as_json(self) -> dict:
        return {
            "kind": "text",
            "text": clean(self.text),
            "x": round(self.x, 5),
            "y": round(self.y, 5),
            "size": round(self.size, 5),
            "rotation": round(self.rotation, 2),
        }


# Where a new line arrives: across most of the frame, in the middle of the space
# above the caption band. Wider than a sticker's fifth, because a line of words at a
# fifth of the frame is set too small to read.
DEFAULT_SIZE = 0.6


def parse(raw: dict, number, *, min_size: float, max_size: float) -> FreeText:
    """One text item from a request or a sidecar. `number` clamps and validates.

    The helper and the size bounds are handed in rather than imported: a placed line
    and a placed sticker are then held to the same rules by the same code, and this
    module stays out of `stickers`, which imports it. See `stickers.parse`, the only
    caller.
    """
    text = clean(raw.get("text", ""))
    if not text:
        raise ValueError("a free text needs something to say")
    return FreeText(
        text=text,
        x=number("x", 0.5, -0.5, 1.5),
        y=number("y", 0.45, -0.5, 1.5),
        size=number("size", DEFAULT_SIZE, min_size, max_size),
        rotation=number("rotation", 0.0, -180.0, 180.0),
    )
