"""Emoji in a placed line of free text. D-065.

The line is set in DejaVu, bundled so that Linux and macOS draw the same pixels.
DejaVu has no emoji, so every one typed into the box came out as an empty
rectangle: the tool accepted them, kept them in the sidecar, and drew tofu.

They are drawn from OpenMoji instead, which is already installed for the sticker
picker, already licensed, and already the same on both platforms. Two things are
pinned here. **A line with no emoji in it must not change at all**, because every
placed line ever made is one. And **the picture is only ever a picture of an
emoji**: OpenMoji ships a drawing of a hyphen, and a line of words whose
punctuation turns into pictures of punctuation would be a worse tool.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from wastatus import freetext, stickers


@pytest.fixture(autouse=True)
def _fresh_lookups():
    """The file lookup is cached for the life of the process, and these tests move
    the library out from under it."""
    freetext._picture.cache_clear()
    yield
    freetext._picture.cache_clear()


def colours(image: Image.Image) -> int:
    """How many pixels have a hue. The line itself is white with a black shadow,
    so anything coloured came out of the picture library.

    `getcolors` rather than `getdata`, which Pillow 14 removes.
    """
    counted = image.convert("RGB").getcolors(maxcolors=1 << 20) or []
    return sum(count for count, pixel in counted if max(pixel) - min(pixel) > 40)


def drawn_pixels(image: Image.Image) -> int:
    """How much of the picture has any ink in it at all."""
    counted = image.convert("RGBA").getcolors(maxcolors=1 << 20) or []
    return sum(count for count, pixel in counted if pixel[3] > 0)


def installed() -> bool:
    return (stickers.library_dir() / "1F3B5.png").is_file()


needs_library = pytest.mark.skipif(
    not installed(),
    reason="the OpenMoji library is not installed: scripts/setup_stickers.sh",
)


class TestWhatCountsAsAPicture:
    @pytest.mark.parametrize("line, wanted", [
        ("Hello 🎵", ["🎵"]),
        ("👍🏽", ["👍🏽"]),                    # a skin tone belongs to the hand
        ("👨‍👩‍👦", ["👨‍👩‍👦"]),  # one family, not three people
        ("🇮🇳", ["🇮🇳"]),                    # a flag is two letters, one picture
        ("☺️", ["☺️"]),          # asked for as an emoji, so it is one
        ("1️⃣", ["1️⃣"]),          # a keycap
        ("★ ♪ © ® ™", []),                 # DejaVu has all five, as letters
        ("a-b.c!", []),                    # OpenMoji ships a hyphen. Not here it does not
        ("9 to 5", []),                    # a bare digit is not a keycap
    ])
    def test_the_line_splits_where_it_should(self, line, wanted):
        assert [run for run, is_emoji in freetext._chunks(line) if is_emoji] == wanted

    def test_nothing_is_lost_in_the_splitting(self):
        line = "Watch 🎵 till 👍🏽 the end"
        assert "".join(run for run, _ in freetext._chunks(line)) == line


class TestTheLookup:
    @needs_library
    def test_a_plain_emoji_is_found_by_its_codepoint(self):
        assert freetext._picture("🎵").name == "1F3B5.png"

    @needs_library
    def test_the_variation_selector_is_dropped_when_the_file_has_none(self):
        """OpenMoji leaves `FE0F` out of nearly every name and keeps it in the
        keycaps, so both spellings have to be tried."""
        assert freetext._picture("☺️").name == "263A.png"
        assert freetext._picture("1️⃣").name == "0031-FE0F-20E3.png"

    def test_an_emoji_nobody_has_a_picture_of_is_not_a_file(self, tmp_path,
                                                            monkeypatch):
        monkeypatch.setattr(stickers, "library_dir", lambda: tmp_path)
        freetext._picture.cache_clear()
        assert freetext._picture("🎵") is None


class TestALineWithNoEmojiIsUntouched:
    """Every placed line ever made is one of these."""

    @pytest.mark.parametrize("line", [
        "Watch till the end", "Vara Leela Gana Lola", "★ ♪ © ® ™", "a-b.c!", "9 to 5",
    ])
    def test_it_is_set_in_the_font_and_nothing_else(self, line):
        drawn = freetext.render(line, 600)
        assert colours(drawn) == 0, "something in that line became a picture"

    def test_and_it_is_still_exactly_the_width_that_was_asked_for(self):
        for width in (60, 300, 1080):
            assert freetext.render("Watch till the end", width).width == width


@needs_library
class TestALineWithThem:
    def test_the_emoji_is_drawn_in_colour(self):
        """🙏 rather than 🎵: OpenMoji draws a quaver in black, which is exactly
        what a font would have drawn and so proves nothing."""
        assert colours(freetext.render("Hello 🙏", 600)) > 0

    def test_the_line_is_still_the_width_that_was_asked_for(self):
        for width in (60, 300, 1080):
            assert freetext.render("Hello 🎵 world", width).width == width

    def test_an_emoji_takes_room_the_way_a_letter_does(self):
        """It is wider with one in it, and the box the page draws is measured from
        the same arithmetic that draws the picture."""
        plain, _ = freetext.measure("Hello world")
        with_one, _ = freetext.measure("Hello 🎵 world")
        assert with_one > plain

    def test_a_line_of_pictures_is_no_taller_than_a_line_of_letters(self):
        """The square is hung inside the ascent and descent, so the height the page
        was already measuring is still right. If this fails, a placed line's box no
        longer matches its picture and every drag is off."""
        assert freetext.measure("Hello 🎵")[1] == freetext.measure("Hello")[1]

    def test_what_it_measures_is_what_it_draws(self):
        for line in ("🎵", "🎵🎵🎵", "a 🎵", "🇮🇳 India 🙏"):
            drawn = freetext.render(line, 500)
            assert abs(drawn.height / drawn.width - freetext.aspect(line)) < 0.02

    def test_every_size_draws_without_falling_off_the_picture(self):
        """A square hung off a baseline is arithmetic that can land at -1, and
        Pillow's `alpha_composite` refuses a negative box rather than clipping."""
        for width in (12, 24, 60, 200, 1080, 2160):
            assert freetext.render("a 🎵 b", width).width == width

    def test_the_picture_carries_the_same_shadow_the_letters_do(self, monkeypatch):
        """Over a bright frame a drawing needs the outline as much as a letter.

        Measured as area: the same emoji drawn with the shadow turned off covers
        less of the picture than the one drawn with it on, and the difference is
        the shadow around its edge.
        """
        with_shadow = drawn_pixels(freetext.render("🙏", 300))
        monkeypatch.setattr(freetext, "SHADOW_ALPHA", 0)
        without = drawn_pixels(freetext.render("🙏", 300))
        assert with_shadow > without


class TestWhenTheLibraryIsNotThere:
    """The pictures are the sticker library, which is an optional install."""

    @pytest.fixture(autouse=True)
    def _empty_library(self, tmp_path, monkeypatch):
        monkeypatch.setattr(stickers, "library_dir", lambda: tmp_path)
        freetext._picture.cache_clear()

    def test_an_emoji_is_left_out_rather_than_drawn_as_an_empty_box(self):
        """Tofu is not a character anybody typed. Leaving it out is visible in the
        preview as you type, which is where a person can do something about it."""
        drawn = freetext.render("Hello 🎵 world", 600)
        assert colours(drawn) == 0

    def test_the_words_around_it_still_arrive(self):
        assert freetext.render("Hello 🎵 world", 600).width == 600

    def test_a_line_that_is_only_an_emoji_says_what_to_install(self):
        with pytest.raises(ValueError) as raised:
            freetext.render("🎵", 600)
        assert "setup_stickers.sh" in str(raised.value)

    def test_and_measures_as_nothing_rather_than_dividing_by_it(self):
        assert freetext.measure("🎵") == (0.0, 0.0)
        assert freetext.aspect("🎵") == 1.0
