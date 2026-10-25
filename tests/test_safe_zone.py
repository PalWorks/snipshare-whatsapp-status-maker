"""Nothing may be drawn in the bands WhatsApp reserves for its own interface.

WhatsApp composites the caption across the bottom of a Status video and the
avatar, name, timestamp and playback controls across the top. Both were found by
posting real Statuses on 2026-08-18, the caption after it collided with a link
pill. These tests measure the lowest and highest pixel the layout actually paints,
in the worst case, so a future layout change cannot silently walk back into either
band.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from wastatus import compose, render

TITLES = {
    "one line": "Thiruppaavai",
    "two lines": "Sinna Sinna Murugaiyaa Kandha Sashti Kavasam",
    "three lines": (
        "Sinna Sinna Murugaiyaa Kandha Sashti Kavasam Thiruppaavai "
        "Vinayagar Agaval Abirami Andhadhi Kanda Guru Kavasam"
    ),
}

# Every aspect ratio a YouTube thumbnail can turn into once its padding bars are
# trimmed off: cinemascope, widescreen, the 16:9 it started as, and squarer than
# the card can hold.
ASPECTS = [2.76, 2.33, 16 / 9, 1.5, 4 / 3, 1.0]


def _painted_rows(text: compose.CardText, *, title_top: int, eyebrow_top: int | None,
                  scale: float, bottom: int = compose.SAFE_BOTTOM,
                  eyebrow_anchor: int | None = None,
                  eyebrow: Sequence[str] | None = None,
                  topline: Sequence[str] | None = None,
                  topline_at: int = compose.TOPLINE_TOP,
                  eyebrow_max_lines: int = compose.EYEBROW_MAX_LINES,
                  topline_max_lines: int = compose.TOPLINE_MAX_LINES
                  ) -> tuple[int, int]:
    """(topmost, bottommost) row carrying ink, in design coordinates.

    Paints and measures, and decides nothing. Blocks already wrapped can be handed
    in, which is how the card-mode callers hand it exactly what `build_card` draws
    rather than working the same arithmetic out a second time; D-078. Without them
    it wraps the way video mode does, to the full allowance.

    `eyebrow_anchor` is the thing the label sits above, and it wins over
    `eyebrow_top` when given.
    """
    size = (round(compose.WIDTH * compose.SUPER * scale),
            round(compose.HEIGHT * compose.SUPER * scale))
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    brow = list(eyebrow) if eyebrow is not None else (
        compose.eyebrow_lines(text.eyebrow, max_lines=eyebrow_max_lines)
        if eyebrow_top is not None else [])
    if eyebrow_anchor is not None:
        eyebrow_top = compose.eyebrow_top(eyebrow_anchor, brow)
    head = list(topline) if topline is not None else compose.topline_lines(
        text.topline, max_lines=topline_max_lines)
    compose._draw_text_layer(
        ImageDraw.Draw(canvas), text,
        title_top=title_top, eyebrow_top=eyebrow_top, scale=scale, eyebrow=brow,
        topline=head, topline_at=topline_at,
        bottom=bottom,
    )
    box = canvas.getchannel("A").getbbox()
    assert box is not None, "the text layer painted nothing at all"
    unit = compose.SUPER * scale
    return round(box[1] / unit), round(box[3] / unit)


def _text(title: str, *, footer: bool = False, eyebrow: str = "NOW PLAYING",
          topline: str = "") -> compose.CardText:
    return compose.CardText(
        title=title,
        channel="Prince Rama Varma Official Channel",
        footer="a footer line, which is off by default" if footer else "",
        eyebrow=eyebrow,
        topline=topline,
    )


def _card_rows(title: str, *, footer: bool, aspect: float,
               eyebrow: str = "NOW PLAYING", topline: str = "") -> tuple[int, int]:
    """Measured through the function `build_card` itself lays the words out with.

    It used to work the arithmetic out a second time here, which held only for as
    long as nobody changed the drawing. D-075 changed it and this kept passing,
    still describing the layout that had just been replaced. `compose.card_words`
    is the one answer both now ask for. See D-078.
    """
    text = _text(title, footer=footer, eyebrow=eyebrow, topline=topline)
    top = compose.card_rect(aspect, None, text)[1]
    words = compose.card_words(text, top)
    return _painted_rows(
        text,
        title_top=compose.CARD_TITLE_TOP,
        eyebrow_top=words.eyebrow_top,
        scale=1.0,
        eyebrow=words.eyebrow,
        topline=words.topline,
        topline_at=words.topline_at,
        bottom=compose.WAVE_TOP,
    )


@pytest.mark.parametrize("title", TITLES.values(), ids=list(TITLES))
@pytest.mark.parametrize("footer", [False, True], ids=["plain", "footer"])
@pytest.mark.parametrize("aspect", ASPECTS, ids=[str(round(a, 2)) for a in ASPECTS])
def test_card_mode_stays_inside_the_safe_bands(title, footer, aspect):
    high, low = _card_rows(title, footer=footer, aspect=aspect)
    assert high >= compose.SAFE_TOP, (
        f"card text starts at y={high}, inside WhatsApp's header band above "
        f"y={compose.SAFE_TOP}"
    )
    assert low <= compose.SAFE_BOTTOM, (
        f"card text reaches y={low}, inside WhatsApp's caption band below "
        f"y={compose.SAFE_BOTTOM}"
    )


@pytest.mark.parametrize("title", TITLES.values(), ids=list(TITLES))
@pytest.mark.parametrize("footer", [False, True], ids=["plain", "footer"])
def test_card_mode_text_clears_the_waveform(title, footer):
    _, low = _card_rows(title, footer=footer, aspect=16 / 9)
    assert low <= compose.WAVE_TOP, (
        f"card text reaches y={low}, into the waveform strip at y={compose.WAVE_TOP}"
    )


@pytest.mark.parametrize("title", TITLES.values(), ids=list(TITLES))
@pytest.mark.parametrize("footer", [False, True], ids=["plain", "footer"])
def test_video_mode_stays_inside_the_safe_bands(title, footer):
    high, low = _painted_rows(
        _text(title, footer=footer),
        title_top=compose.VIDEO_TITLE_TOP,
        eyebrow_top=compose.VIDEO_EYEBROW_TOP,
        eyebrow_anchor=compose.VIDEO_TITLE_TOP,
        scale=1 / compose.SUPER,
    )
    assert high >= compose.SAFE_TOP
    assert low <= compose.SAFE_BOTTOM, (
        f"video overlay text reaches y={low}, inside WhatsApp's caption band below "
        f"y={compose.SAFE_BOTTOM}"
    )


@pytest.mark.parametrize("aspect", ASPECTS, ids=[str(round(a, 2)) for a in ASPECTS])
def test_the_card_itself_clears_the_header_band(aspect):
    """The card's own edges. The label is no longer above it, D-075, so what has to
    clear the header is the card, and what has to clear the card is the top text."""
    left, top, right, bottom = compose.card_box(compose.card_height(aspect))
    assert top >= compose.SAFE_TOP, (
        f"a {aspect:.2f} card starts at y={top}, inside WhatsApp's header band"
    )
    assert bottom < compose.CARD_TITLE_TOP
    assert (left, right) == (compose.MARGIN, compose.WIDTH - compose.MARGIN)


@pytest.mark.parametrize("aspect", ASPECTS, ids=[str(round(a, 2)) for a in ASPECTS])
def test_the_card_bottom_is_the_same_whatever_the_artwork_shape(aspect):
    """Series consistency: the card and title stay a fixed pair across songs."""
    _, _, _, bottom = compose.card_box(compose.card_height(aspect))
    assert bottom == compose.CARD_TITLE_TOP - compose.CARD_GAP


def test_the_reserved_bands_are_the_top_and_bottom_of_the_frame():
    """Pins the numbers, so changing one is a visible decision."""
    assert compose.SAFE_BOTTOM == round(compose.HEIGHT * 0.85)
    assert compose.SAFE_TOP == round(compose.HEIGHT * 0.12)


def test_waveform_sits_between_the_text_and_the_caption_band():
    assert compose.WAVE_TOP > compose.CARD_TITLE_TOP
    assert compose.WAVE_TOP + compose.WAVE_H <= compose.SAFE_BOTTOM


# -- the frames in --video mode --------------------------------------------

# A card is anchored above the title and so can never be written on. Frames were
# not: they were centred in the whole 1080x1920 canvas, which knows nothing about
# the words, and anything squarer than 5:3 reached into the title. Measured on
# 2026-08-24: a 4:3 source painted down to y=1365 with the title starting at 1284.
# These render the real filter graph and measure the picture it actually paints,
# because the clamp lives in an ffmpeg expression and an expression cannot be
# proved right by reading it.
VIDEO_ASPECTS = [(1280, 544), (1280, 720), (960, 720), (720, 720), (540, 960)]


def _picture_band(still: Path) -> tuple[int, int]:
    """(topmost, bottommost) row holding the source's own picture.

    The source is pure white, so the picture is white and the blurred fill behind
    it is the same white darkened by `eq=brightness=-0.20`. Nothing about the
    layout is assumed: the two are told apart by their brightness alone.

    The middle column rather than the whole row, because a portrait source is
    fitted to the band and is then narrower than the frame: averaging a row would
    mix its picture with the fill either side of it and find neither.
    """
    frame = Image.open(still).convert("L")
    middle = compose.WIDTH // 2
    lit = [y for y in range(compose.HEIGHT) if frame.getpixel((middle, y)) > 240]
    assert lit, "no picture found in the still at all"
    return lit[0], lit[-1]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
@pytest.mark.parametrize("size", VIDEO_ASPECTS, ids=[f"{w}x{h}" for w, h in VIDEO_ASPECTS])
def test_video_frames_stay_clear_of_the_words_and_the_header(size, tmp_path):
    width, height = size
    source = tmp_path / "src.mp4"
    subprocess.run(
        [shutil.which("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c=white:s={width}x{height}:d=1",
         "-pix_fmt", "yuv420p", str(source)],
        check=True,
    )
    top, bottom = _picture_band(render.background_still(
        source, tmp_path / "still.png", crop=None,
        rect=render.picture_rect((width, height)),
    ))
    assert bottom <= compose.VIDEO_TITLE_TOP, (
        f"a {width}x{height} source paints down to y={bottom}, into the title that "
        f"starts at y={compose.VIDEO_TITLE_TOP}"
    )
    assert top >= compose.SAFE_TOP, (
        f"a {width}x{height} source paints up to y={top}, into WhatsApp's own header"
    )


def test_a_wide_source_is_still_centred_rather_than_pushed_about():
    """The clamp is a floor, not a layout. Nothing that already cleared the title
    is allowed to move, or every existing clip in the series changes shape."""
    for aspect in (2.76, 2.33):
        drawn = compose.WIDTH / aspect
        centred = (compose.HEIGHT - drawn) / 2
        assert centred + drawn <= compose.VIDEO_PICTURE_BOTTOM


# The eyebrow is called "the label above the card", and video mode has no card. It
# was passed `eyebrow_top=None` and therefore silently not drawn at all: a box on
# the page that took a sentence and threw it away. Reported 2026-08-25.
def test_a_label_is_drawn_in_video_mode_at_all():
    without = _painted_rows(
        _text(TITLES["one line"], eyebrow=""), title_top=compose.VIDEO_TITLE_TOP,
        eyebrow_top=compose.VIDEO_EYEBROW_TOP,
        eyebrow_anchor=compose.VIDEO_TITLE_TOP, scale=1 / compose.SUPER,
    )
    with_label = _painted_rows(
        _text(TITLES["one line"], eyebrow="PoV: A BEE ON A FLOWER"),
        title_top=compose.VIDEO_TITLE_TOP,
        eyebrow_top=compose.VIDEO_EYEBROW_TOP,
        eyebrow_anchor=compose.VIDEO_TITLE_TOP, scale=1 / compose.SUPER,
    )
    assert with_label[0] < without[0], "the label painted nothing above the title"
    assert with_label[0] >= compose.SAFE_TOP


# The first sentence anybody typed into this box, 2026-08-25. It was drawn as one
# unwrapped line 1989 pixels wide into a 1080 pixel frame, 454 falling off each side,
# which reads as the field having done nothing at all.
SENTENCE = ("PoV: Describe a bee (you) who just saw a blooming flower (Krishna) "
            "that is ripe with nectar")


def test_a_long_label_is_wrapped_rather_than_run_off_both_edges():
    lines = compose.eyebrow_lines(SENTENCE)
    assert len(lines) > 1, "a 91 character label came back as one line"
    font = ImageFont.truetype(str(compose.BOLD), compose.EYEBROW_SIZE)
    draw = ImageDraw.Draw(Image.new("L", (1, 1)))
    tracking = compose.eyebrow_tracking(SENTENCE)
    for line in lines:
        drawn = (sum(draw.textlength(ch, font=font) for ch in line)
                 + tracking * (len(line) - 1))
        assert drawn <= compose.WIDTH - 2 * compose.MARGIN, (
            f"{line!r} is {round(drawn)} wide, past the margins"
        )


def test_a_sentence_loses_the_letterspacing_a_two_word_label_keeps():
    """Tracking is what makes NOW PLAYING read as a label. On a sentence it is
    noise, and it was also a third of the width that put this off the frame."""
    assert compose.eyebrow_tracking("NOW PLAYING") == compose.EYEBROW_TRACKING
    assert compose.eyebrow_tracking(SENTENCE) == 0


@pytest.mark.parametrize("aspect", ASPECTS, ids=[str(round(a, 2)) for a in ASPECTS])
def test_a_long_label_on_a_card_stays_out_of_whatsapps_header(aspect):
    """It cannot reach the header any more, because it hangs off the title rather
    than off the card, D-075. Kept as the guarantee rather than the mechanism: a
    label wraps upwards, and this is what says how far up it is allowed to get."""
    high, _ = _card_rows(TITLES["one line"], footer=False, aspect=aspect,
                         eyebrow=SENTENCE)
    assert high >= compose.SAFE_TOP


@pytest.mark.parametrize("aspect", ASPECTS, ids=[str(round(a, 2)) for a in ASPECTS])
def test_a_long_label_on_a_card_never_reaches_the_card_above_it(aspect):
    """The collision the move created, in place of the one it removed: the label
    grows upwards from the title, and the card is what is now above it."""
    text = compose.CardText(title=TITLES["one line"], channel="C", eyebrow=SENTENCE)
    left, top, right, bottom = compose.card_rect(aspect, None, text)
    words = compose.card_words(text, top)
    assert words.eyebrow_top >= bottom


def test_a_wrapped_label_in_video_mode_stays_inside_the_bands():
    high, low = _painted_rows(
        _text(TITLES["three lines"], footer=True, eyebrow=SENTENCE),
        title_top=compose.VIDEO_TITLE_TOP,
        eyebrow_top=compose.VIDEO_EYEBROW_TOP,
        eyebrow_anchor=compose.VIDEO_TITLE_TOP,
        scale=1 / compose.SUPER,
    )
    assert high >= compose.SAFE_TOP
    assert low <= compose.SAFE_BOTTOM


def test_a_label_costs_the_frames_room_and_only_when_there_is_one():
    """The picture pays for the label, and pays nothing when there is none: 70
    pixels off every clip for a line that is off by default is the wrong trade."""
    plain = compose.CardText(title="x", channel="y")
    labelled = compose.CardText(title="x", channel="y", eyebrow="PoV")
    assert compose.video_picture_bottom(plain) == compose.VIDEO_PICTURE_BOTTOM
    assert compose.video_picture_bottom(labelled) < compose.VIDEO_EYEBROW_TOP


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_the_frames_clear_the_label_too(tmp_path):
    """Measured, not reasoned: the floor is an ffmpeg expression either way."""
    source = tmp_path / "src.mp4"
    subprocess.run(
        [shutil.which("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=white:s=960x720:d=1",
         "-pix_fmt", "yuv420p", str(source)],
        check=True,
    )
    floor = compose.video_picture_bottom(
        compose.CardText(title="x", channel="y", eyebrow="PoV: A BEE ON A FLOWER")
    )
    _, bottom = _picture_band(render.background_still(
        source, tmp_path / "still.png", crop=None,
        rect=render.picture_rect((960, 720), floor=floor),
    ))
    assert bottom <= compose.VIDEO_EYEBROW_TOP, (
        f"the picture reaches y={bottom}, into the label at y={compose.VIDEO_EYEBROW_TOP}"
    )


# Reported 2026-08-25 as "text wrap is happening here, but not here", of the label
# against the second line and the footer. Both were single unwrapped `draw.text`
# calls: an ordinary channel name measured 1253 pixels and the footer 1209, in a
# 1080 pixel frame with 880 pixels of margins.
LONG_CHANNEL = "Sounds of Isha Official Channel for Devotional and Classical Music"
LONG_FOOTER = ("A long footer line that nobody has yet tried to type into this box "
               "but one day will")


def _drawn_width(text: str, size: int) -> float:
    font = ImageFont.truetype(str(compose.REGULAR), size)
    return ImageDraw.Draw(Image.new("L", (1, 1))).textlength(text, font=font)


@pytest.mark.parametrize("title_top,bottom", [
    (compose.VIDEO_TITLE_TOP, compose.SAFE_BOTTOM),
    (compose.CARD_TITLE_TOP, compose.WAVE_TOP),
], ids=["video", "card"])
def test_the_second_line_and_the_footer_are_wrapped_like_everything_else(
    title_top, bottom
):
    """Every painted pixel inside the margins, in both modes, for text that used to
    run off both edges by 170 pixels a side."""
    text = compose.CardText(title=TITLES["one line"], channel=LONG_CHANNEL,
                            footer=LONG_FOOTER)
    size = (compose.WIDTH, compose.HEIGHT)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    compose._draw_text_layer(
        ImageDraw.Draw(canvas), text, title_top=title_top, eyebrow_top=None,
        bottom=bottom, scale=1 / compose.SUPER,
    )
    box = canvas.getchannel("A").getbbox()
    assert box is not None
    assert box[0] >= compose.MARGIN - 2, f"paint starts at x={box[0]}"
    assert box[2] <= compose.WIDTH - compose.MARGIN + 2, f"paint ends at x={box[2]}"


def test_the_unwrapped_versions_really_did_not_fit():
    """The measurement that made this a bug rather than a preference."""
    assert _drawn_width(LONG_CHANNEL, compose.CHANNEL_SIZE) > compose.WIDTH
    assert _drawn_width(LONG_FOOTER, compose.FOOTER_SIZE) > compose.WIDTH


def test_a_long_second_line_never_pushes_the_footer_past_the_caption_band():
    """The footer keeps a line back for itself, so a wrapped channel cannot eat the
    whole remainder and leave it nowhere to go."""
    _, low = _painted_rows(
        compose.CardText(title=TITLES["three lines"], channel=LONG_CHANNEL,
                         footer=LONG_FOOTER),
        title_top=compose.VIDEO_TITLE_TOP, eyebrow_top=None,
        scale=1 / compose.SUPER, bottom=compose.SAFE_BOTTOM,
    )
    assert low <= compose.SAFE_BOTTOM


# The band under WhatsApp's own header was empty air in video mode. Asked for on
# 2026-08-25 as "how to insert text here?".
TOP_TEXT = "When the Thillana starts and the whole hall forgets to breathe"


def test_top_text_is_drawn_under_whatsapps_header_and_wrapped():
    lines = compose.topline_lines(TOP_TEXT)
    assert len(lines) > 1
    high, _ = _painted_rows(
        _text(TITLES["one line"], topline=TOP_TEXT),
        title_top=compose.VIDEO_TITLE_TOP,
        eyebrow_top=compose.VIDEO_EYEBROW_TOP,
        eyebrow_anchor=compose.VIDEO_TITLE_TOP, scale=1 / compose.SUPER,
    )
    assert high >= compose.SAFE_TOP
    assert high < compose.VIDEO_TITLE_TOP, "nothing was painted up there at all"


def test_the_frames_give_up_room_at_the_top_and_only_when_asked():
    plain = compose.CardText(title="x", channel="y")
    with_top = compose.CardText(title="x", channel="y", topline=TOP_TEXT)
    assert compose.video_picture_top(plain) == compose.SAFE_TOP
    assert compose.video_picture_top(with_top) > compose.SAFE_TOP


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_a_tall_source_stops_below_the_top_text(tmp_path):
    """Measured through the real graph. A square source used to start at SAFE_TOP,
    which is exactly where the top text now is."""
    source = tmp_path / "src.mp4"
    subprocess.run(
        [shutil.which("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=white:s=720x720:d=1",
         "-pix_fmt", "yuv420p", str(source)],
        check=True,
    )
    text = compose.CardText(title="x", channel="y", topline=TOP_TEXT)
    ceiling = compose.video_picture_top(text)
    top, _ = _picture_band(render.background_still(
        source, tmp_path / "still.png", crop=None,
        rect=render.picture_rect(
            (720, 720), ceiling=ceiling, floor=compose.video_picture_bottom(text),
        ),
    ))
    assert top >= ceiling


@pytest.mark.parametrize("aspect", ASPECTS, ids=[str(round(a, 2)) for a in ASPECTS])
def test_top_text_on_a_card_clears_the_card_and_wastapp_s_header(aspect):
    """The two things it can collide with, now that the label has moved out of the
    band and down to the title: WhatsApp's own header above it, and the card below.
    D-075. A fitted card shrinks for it, so at every aspect it is drawn."""
    text = compose.CardText(title="T", channel="C", eyebrow="NOW PLAYING",
                            topline=TOP_TEXT)
    top = compose.card_rect(aspect, None, text)[1]
    words = compose.card_words(text, top)
    assert words.topline, "a fitted card always leaves room for the top text"
    assert words.topline_at >= compose.SAFE_TOP
    assert (words.topline_at + compose.topline_height(words.topline)
            + compose.TOPLINE_GAP) <= top


@pytest.mark.parametrize("aspect", ASPECTS, ids=[str(round(a, 2)) for a in ASPECTS])
def test_the_label_clears_the_card_above_it_and_the_title_below(aspect):
    """It hangs off the title in both modes now, so the card is what gives way."""
    text = compose.CardText(title="T", channel="C", eyebrow="NOW PLAYING",
                            topline=TOP_TEXT)
    left, top, right, bottom = compose.card_rect(aspect, None, text)
    words = compose.card_words(text, top)
    assert words.eyebrow, "a typed label is always drawn"
    assert words.eyebrow_top >= bottom, "below the card"
    assert (words.eyebrow_top + compose.eyebrow_height(words.eyebrow)
            <= compose.CARD_TITLE_TOP), "above the title"


# Python owns the picture's rectangle now, rather than leaving it to an ffmpeg
# expression, because Pillow has to anchor the top text to its top edge. That makes
# these two the load bearing test in this file: if the arithmetic here and the paint
# ffmpeg lays down ever disagree, every word placed against the picture is wrong.
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
@pytest.mark.parametrize("size", VIDEO_ASPECTS, ids=[f"{w}x{h}" for w, h in VIDEO_ASPECTS])
def test_the_rectangle_python_computes_is_the_one_ffmpeg_paints(size, tmp_path):
    width, height = size
    source = tmp_path / "src.mp4"
    subprocess.run(
        [shutil.which("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c=white:s={width}x{height}:d=1",
         "-pix_fmt", "yuv420p", str(source)],
        check=True,
    )
    rect = render.picture_rect(size)
    top, bottom = _picture_band(render.background_still(
        source, tmp_path / "still.png", crop=None, rect=rect,
    ))
    assert top == rect.top
    assert bottom == rect.top + rect.height - 1


def test_the_rectangle_is_even_on_every_side():
    """yuv420p's chroma plane is half resolution, so an odd size or offset is a
    row it cannot represent."""
    for size in VIDEO_ASPECTS:
        rect = render.picture_rect(size)
        assert rect.width % 2 == 0 and rect.height % 2 == 0
        assert rect.left % 2 == 0 and rect.top % 2 == 0


# Reported 2026-08-25: the top text sat against WhatsApp's header with a 278 pixel
# void under it, because it was anchored to the top of the band rather than to the
# picture it belongs to.
def test_top_text_hangs_off_the_picture_rather_than_the_header():
    lines = compose.topline_lines(TOP_TEXT)
    rect = render.picture_rect((1280, 720))
    at = compose.topline_top(rect.top, lines)
    assert at + compose.topline_height(lines) + compose.TOPLINE_GAP == rect.top
    assert at - compose.SAFE_TOP > 200, "it is still hugging the header"


def test_a_shorter_line_sits_further_from_the_header_not_nearer():
    """The whole point of anchoring by the bottom: length grows upwards, so the
    only text that approaches the header is text long enough to need the room."""
    rect = render.picture_rect((1280, 720))
    short = compose.topline_lines("PoV")
    long = compose.topline_lines(TOP_TEXT)
    assert compose.topline_top(rect.top, short) > compose.topline_top(rect.top, long)


def test_a_picture_that_starts_high_does_not_drag_the_text_off_the_frame():
    """A square source begins at the ceiling, so there is no room to hang from and
    the block falls back to the top of the band rather than going above it."""
    text = compose.CardText(title="x", channel="y", topline=TOP_TEXT)
    lines = compose.topline_lines(TOP_TEXT)
    rect = render.picture_rect(
        (720, 720), ceiling=compose.video_picture_top(text),
        floor=compose.video_picture_bottom(text),
    )
    assert compose.topline_top(rect.top, lines) >= compose.SAFE_TOP


def test_a_clip_made_before_the_picture_was_recorded_still_draws_its_top_text():
    """`picture_top=None` is what an old clip's preview passes, and it has to put
    the text where that clip actually has it."""
    assert compose.topline_top(None, compose.topline_lines(TOP_TEXT)) == compose.TOPLINE_TOP


def test_the_band_the_frames_are_fitted_into_is_the_one_above_the_title():
    assert compose.SAFE_TOP + compose.VIDEO_PICTURE_H == compose.VIDEO_PICTURE_BOTTOM
    assert compose.VIDEO_PICTURE_BOTTOM < compose.VIDEO_TITLE_TOP
