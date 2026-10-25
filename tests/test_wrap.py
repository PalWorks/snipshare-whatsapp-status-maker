"""Title wrapping, measured with the real font at the real card width.

The card allows three lines. Which words land on which line is the difference
between a title that reads as its own name and one that breaks mid-name.
"""

from __future__ import annotations

import re

from PIL import Image, ImageDraw, ImageFont

from wastatus import compose

MAX_WIDTH = compose.WIDTH - 2 * compose.MARGIN


def _wrap(title: str, max_lines: int = 3) -> list[str]:
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = ImageFont.truetype(str(compose.BOLD), 64)
    return compose._wrap(draw, title, font, MAX_WIDTH, max_lines)


def _same_characters(lines: list[str], title: str) -> bool:
    strip = lambda text: re.sub(r"\s+", "", text)  # noqa: E731
    return strip("".join(lines)) == strip(title)


def test_a_hyphen_is_a_break_opportunity():
    """The measured case: this title used to take three lines and split a name."""
    lines = _wrap("Prince Rama Varma-VARA LEELA GANA LOLA")
    assert lines == ["Prince Rama Varma-", "VARA LEELA GANA LOLA"]


def test_no_space_is_introduced_after_a_hyphen():
    lines = _wrap("Prince Rama Varma-VARA LEELA GANA LOLA")
    assert not any(line.startswith("-") for line in lines)
    assert _same_characters(lines, "Prince Rama Varma-VARA LEELA GANA LOLA")


def test_a_dash_between_spaces_keeps_both_spaces():
    """"Artist - Song" is most of YouTube. It used to come out "Artist -Song"."""
    for title in ("Ed Sheeran - Shape of You",
                  "Luis Fonsi - Despacito ft. Daddy Yankee - Live in Concert"):
        lines = _wrap(title)
        assert " ".join(lines) == title
        assert not any("-S" in line or "-D" in line or "-L" in line for line in lines)


def test_short_titles_stay_on_one_line():
    assert _wrap("Thiruppaavai") == ["Thiruppaavai"]


def test_ordinary_titles_still_break_on_spaces():
    lines = _wrap("Sinna Sinna Murugaiyaa Kandha Sashti Kavasam")
    assert len(lines) == 2
    assert all(" " in line for line in lines)
    assert _same_characters(lines, "Sinna Sinna Murugaiyaa Kandha Sashti Kavasam")


def test_an_overlong_title_is_ellipsised_on_the_last_line():
    lines = _wrap(
        "Sinna Sinna Murugaiyaa Kandha Sashti Kavasam Thiruppaavai "
        "Vinayagar Agaval Abirami Andhadhi Kanda Guru Kavasam"
    )
    assert len(lines) == 3
    assert lines[-1].endswith("...")


def test_a_title_that_exactly_fits_is_not_ellipsised():
    lines = _wrap("Sinna Sinna Murugaiyaa Kandha Sashti Kavasam")
    assert not lines[-1].endswith("...")


def test_a_single_unbreakable_word_is_kept():
    lines = _wrap("Thirumurugatrupadaithiruppugazhkandaguruvasagam")
    assert len(lines) == 1
    assert lines[0]


def test_a_trailing_hyphen_does_not_create_an_empty_atom():
    assert compose._atoms("Kavasam-") == ["Kavasam-"]
    assert compose._atoms("a-b-c") == ["a-", "b-", "c"]


def test_every_line_fits_the_card_width():
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = ImageFont.truetype(str(compose.BOLD), 64)
    for title in (
        "Prince Rama Varma-VARA LEELA GANA LOLA",
        "Sinna Sinna Murugaiyaa Kandha Sashti Kavasam",
        "Kandha Sashti Kavasam-Full Version-Devotional",
    ):
        for line in compose._wrap(draw, title, font, MAX_WIDTH, 3):
            assert draw.textlength(line, font=font) <= MAX_WIDTH, f"{line!r} overflows"
