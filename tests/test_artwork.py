"""Trimming the padding bars that uploaders bake into YouTube thumbnails.

A thumbnail is always 16:9, so a picture of any other shape arrives padded with
flat bars. Left alone they appear inside the card and, once blurred, as dead bands
across the background. The measured case that prompted this: Prince Rama Varma's
VARA LEELA GANA LOLA, a 1280x720 thumbnail carrying an 85px black bar above and an
84px bar below a 2.33:1 picture.
"""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from wastatus import compose


def _picture(width: int, height: int) -> Image.Image:
    """Something with structure, so a bar is distinguishable from the picture."""
    image = Image.new("RGB", (width, height), (40, 90, 160))
    draw = ImageDraw.Draw(image)
    for i in range(0, width, 12):
        draw.line([(i, 0), (i + 40, height)], fill=(220, 180, 60), width=5)
    draw.ellipse([(width * 0.3, height * 0.2), (width * 0.7, height * 0.8)],
                 fill=(230, 240, 250))
    return image


def _letterboxed(bar: int, colour=(0, 0, 0), *, size=(1280, 720)) -> Image.Image:
    width, height = size
    canvas = Image.new("RGB", size, colour)
    canvas.paste(_picture(width, height - 2 * bar), (0, bar))
    return canvas


def test_black_letterbox_bars_are_removed():
    trimmed = compose.trim_bars(_letterboxed(85))
    assert trimmed.width == 1280
    assert trimmed.height == pytest.approx(720 - 170, abs=8)


def test_the_real_world_case_becomes_cinemascope():
    """The measured VARA LEELA GANA LOLA thumbnail: 85 above, 84 below."""
    canvas = Image.new("RGB", (1280, 720), (0, 0, 0))
    canvas.paste(_picture(1280, 551), (0, 85))
    trimmed = compose.trim_bars(canvas)
    assert trimmed.width / trimmed.height == pytest.approx(2.32, abs=0.1)


def test_pillarbox_bars_are_removed():
    canvas = Image.new("RGB", (1280, 720), (0, 0, 0))
    canvas.paste(_picture(720, 720), (280, 0))
    trimmed = compose.trim_bars(canvas)
    assert trimmed.height == 720
    assert trimmed.width == pytest.approx(720, abs=20)


def test_white_bars_are_removed_too():
    trimmed = compose.trim_bars(_letterboxed(85, (255, 255, 255)))
    assert trimmed.height == pytest.approx(550, abs=8)


def test_near_black_bars_are_removed():
    """JPEG noise stops a black bar from being exactly black."""
    canvas = _letterboxed(85, (6, 4, 7))
    trimmed = compose.trim_bars(canvas)
    assert trimmed.height == pytest.approx(550, abs=8)


def test_a_windowboxed_picture_loses_all_four_bars():
    """Padding on all four sides. One detection pass cannot see the side bars,
    because a side column contains the top bar's pixels and so is not flat."""
    canvas = Image.new("RGB", (1280, 720), (0, 0, 0))
    canvas.paste(_picture(900, 500), (190, 110))
    trimmed = compose.trim_bars(canvas)
    assert trimmed.width == pytest.approx(900, abs=20)
    assert trimmed.height == pytest.approx(500, abs=20)


def test_detect_bars_reports_the_box_in_original_coordinates():
    """`--video` mode turns this box into an ffmpeg crop, so the offsets matter."""
    canvas = Image.new("RGB", (1280, 720), (0, 0, 0))
    canvas.paste(_picture(900, 500), (190, 110))
    left, top, right, bottom = compose.detect_bars(canvas)
    assert (left, top) == pytest.approx((190, 110), abs=20)
    assert (right, bottom) == pytest.approx((1090, 610), abs=20)


def test_a_full_frame_picture_is_left_alone():
    original = _picture(1280, 720)
    trimmed = compose.trim_bars(original)
    assert trimmed.size == original.size


def test_regular_texture_is_not_mistaken_for_a_bar():
    """A regression: averaging along a row made evenly spaced stripes read as flat.

    The fixture above is stripes plus an ellipse, and the stripes reach the top
    edge. An averaging detector trimmed the top 144 rows of it.
    """
    stripes = Image.new("RGB", (1280, 720), (30, 30, 30))
    draw = ImageDraw.Draw(stripes)
    for x in range(0, 1280, 12):
        draw.rectangle([(x, 0), (x + 5, 720)], fill=(210, 210, 210))
    trimmed = compose.trim_bars(stripes)
    assert trimmed.height == 720, "regular texture was trimmed as a letterbox bar"
    # The outermost stripe is a genuinely uniform band a few pixels wide, so losing
    # it is correct. Losing any real fraction of the picture is not.
    assert trimmed.width >= 1270


def test_a_dark_picture_is_not_mistaken_for_a_bar():
    """Dark is not flat. A gradient must survive intact."""
    image = Image.new("RGB", (640, 360))
    draw = ImageDraw.Draw(image)
    for y in range(360):
        draw.line([(0, y), (640, y)], fill=(y // 12, y // 10, y // 8))
    assert compose.trim_bars(image).size == image.size


def test_an_entirely_flat_image_is_left_alone():
    """Trimming every row would leave nothing to show."""
    flat = Image.new("RGB", (640, 360), (12, 12, 12))
    assert compose.trim_bars(flat).size == flat.size


def test_bars_larger_than_the_cap_are_not_trimmed():
    """A picture that is mostly padding is more likely a detection failure."""
    canvas = Image.new("RGB", (1280, 720), (0, 0, 0))
    canvas.paste(_picture(1280, 100), (0, 310))  # 43 percent bar each side
    assert compose.trim_bars(canvas).size == (1280, 720)


def test_a_tiny_image_is_left_alone():
    tiny = Image.new("RGB", (4, 4), (0, 0, 0))
    assert compose.trim_bars(tiny).size == (4, 4)


def test_trimming_never_returns_an_empty_image():
    for bar in range(0, 200, 17):
        trimmed = compose.trim_bars(_letterboxed(bar))
        assert trimmed.width >= 8 and trimmed.height >= 8


@pytest.mark.parametrize(
    "aspect,expected",
    [(2.93, compose.CARD_H_MIN), (16 / 9, 495), (1.0, compose.CARD_H_MAX)],
)
def test_card_height_follows_the_artwork_and_stays_in_range(aspect, expected):
    assert compose.card_height(aspect) == expected


def test_card_height_survives_a_nonsense_aspect():
    assert compose.card_height(0) == compose.CARD_H_MAX
    assert compose.card_height(-3) == compose.CARD_H_MAX
