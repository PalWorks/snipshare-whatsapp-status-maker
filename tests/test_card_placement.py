"""Putting the artwork panel where you want it, in card mode. D-062.

Card mode's panel was the one thing on either frame still laid out entirely for
you: a fixed width, a height its own shape asked for, pinned a fixed gap above the
title. This is that panel becoming the same kind of object as everything else here,
a rectangle at fractions of the frame.

Two things are pinned hardest. **The fitted card cannot move**, because every card
ever made is one and a pixel of drift would be a pixel of drift in all of them. And
**the words follow the panel**, which is what was asked for on 2026-08-27 over the
two alternatives, so the label and the top text are measured off the panel's own top
edge and stop following it only where following it would draw them somewhere they
cannot be read.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from wastatus import compose, render

TEXT = compose.CardText(
    title="Vara Leela Gana Lola", channel="Prince Rama Varma",
    eyebrow="NOW PLAYING", topline="Watch till the end",
)


def artwork(tmp_path, width=1280, height=720):
    """A thumbnail with structure in it, so a shifted layout is visible."""
    art = Image.new("RGB", (width, height), (30, 60, 120))
    draw = ImageDraw.Draw(art)
    for x in range(0, width, 40):
        draw.line([(x, 0), (x, height)], fill=(220, 180, 40), width=6)
    dest = tmp_path / f"art{width}x{height}.jpg"
    art.save(dest, "JPEG", quality=92)
    return dest


class TestTheRectangle:
    def test_nothing_asked_for_is_the_box_it_has_always_been(self):
        for aspect in (16 / 9, 4 / 3, 1.0, 2.4, 0.8):
            assert compose.card_rect(aspect) == \
                compose.card_box(compose.card_height(aspect))

    def test_the_round_trip_is_exact(self):
        """Switching Fitted to Placed reads the placement back off the rectangle the
        clip recorded. A pixel of drift there calls a clip stale for a placement
        nobody has touched, which is the bug this arithmetic exists to avoid."""
        for aspect in (16 / 9, 4 / 3, 1.0, 2.4, 0.8, 3.2):
            left, top, right, bottom = compose.card_rect(aspect)
            placed = compose.card_rect(aspect, render.Framing(
                x=(left + right) / 2 / compose.WIDTH,
                y=(top + bottom) / 2 / compose.HEIGHT,
                size=(right - left) / compose.WIDTH,
            ))
            assert placed == (left, top, right, bottom)

    def test_the_width_is_the_size_and_the_height_follows_from_it(self):
        left, top, right, bottom = compose.card_rect(
            16 / 9, render.Framing(0.5, 0.5, 1.0))
        assert right - left == compose.WIDTH
        assert left == 0
        # The fitted panel scaled by the same factor, rather than the artwork's own
        # shape: a placed card is the fitted one moved, so the crop it has stays.
        fitted = compose.card_height(16 / 9)
        assert bottom - top == round(fitted * compose.WIDTH / compose.CARD_W)

    def test_it_is_centred_on_the_point_it_was_given(self):
        left, top, right, bottom = compose.card_rect(
            16 / 9, render.Framing(0.25, 0.75, 0.4))
        assert abs((left + right) / 2 - 0.25 * compose.WIDTH) <= 1
        assert abs((top + bottom) / 2 - 0.75 * compose.HEIGHT) <= 1

    def test_it_may_hang_off_any_edge(self):
        left, top, right, bottom = compose.card_rect(
            16 / 9, render.Framing(0.5, 0.5, 2.0))
        assert left < 0 and right > compose.WIDTH
        assert bottom - top > 0

    def test_an_unusually_square_artwork_keeps_the_crop_it_had(self):
        """`card_height` clamps, so a square thumbnail is centre cropped into a
        620 pixel panel. Placing it must not silently un-crop it: dragging a corner
        is a resize, and a picture that changes shape under the hand moving it is
        not the thing that was picked up."""
        fitted = compose.card_rect(1.0)
        wide = compose.card_rect(1.0, render.Framing(0.5, 0.5, 1.0))
        was = (fitted[3] - fitted[1]) / (fitted[2] - fitted[0])
        now = (wide[3] - wide[1]) / (wide[2] - wide[0])
        assert abs(was - now) < 0.001, "the panel changed shape as it was resized"
        # And it is the panel's shape, not the artwork's: a square thumbnail in a
        # panel wider than it is tall is a centre crop, which is what D-016 chose.
        assert was < 0.9


class TestWhereTheLabelHangsFrom:
    """The words follow the panel, and stop at the two ends of its travel."""

    def test_every_fitted_card_sits_inside_the_clamps(self):
        """Which is why nothing made before this moves. If a fitted card could
        reach past either end, this feature would have relaid out the archive."""
        for aspect in (16 / 9, 4 / 3, 1.0, 2.4, 0.5, 3.0, 0.1, 12.0):
            top = compose.card_rect(aspect)[1]
            assert compose.card_words_anchor(top) == top

    def test_a_panel_dragged_high_stops_the_label_at_the_safe_line(self):
        anchor = compose.card_words_anchor(-400)
        assert anchor == compose.CARD_WORDS_TOP
        one_line = compose.eyebrow_lines("NOW PLAYING")
        assert compose.eyebrow_top(anchor, one_line) >= compose.SAFE_TOP

    def test_a_panel_dragged_low_stops_the_label_above_the_title(self):
        anchor = compose.card_words_anchor(1800)
        assert anchor == compose.CARD_WORDS_BOTTOM
        lines = compose.eyebrow_lines("NOW PLAYING")
        bottom = compose.eyebrow_top(anchor, lines) + compose.eyebrow_height(lines)
        assert bottom <= compose.CARD_TITLE_TOP

    def test_in_between_it_simply_follows(self):
        for top in (320, 500, 700, 900):
            assert compose.card_words_anchor(top) == top


class TestTheDrawing:
    def test_a_fitted_card_is_the_card_it_was(self, tmp_path):
        """Byte for byte. The same file compared against itself is not the test:
        this is the placed code path, asked for nothing, against the fitted one."""
        art = artwork(tmp_path)
        first = compose.build_card(art, TEXT, tmp_path / "a.png")
        second = compose.build_card(art, TEXT, tmp_path / "b.png", framing=None)
        assert first.read_bytes() == second.read_bytes()

    def test_the_panel_lands_where_the_rectangle_says(self, tmp_path):
        """Measured in the pixels, not asserted about the arithmetic. The artwork
        is bright yellow and blue and the background is the same thing blurred and
        darkened, so the panel's own corner is far brighter than what is around it."""
        art = artwork(tmp_path)
        framing = render.Framing(0.3, 0.25, 0.4)
        made = compose.build_card(art, TEXT, tmp_path / "c.png", framing=framing)
        left, top, right, bottom = compose.card_rect(
            compose.card_aspect(art), framing)
        card = Image.open(made).convert("RGB")
        scale = card.width / compose.WIDTH

        def at(x, y):
            return card.getpixel((round(x * scale), round(y * scale)))

        inside = at((left + right) / 2, (top + bottom) / 2)
        outside = at((left + right) / 2, bottom + 60)
        assert max(inside) > max(outside) + 40, "the panel is not where it was put"

    def test_a_panel_over_the_title_gets_the_shade_that_keeps_it_readable(
            self, tmp_path):
        """The card's own scrim goes on before the panel, so a panel dragged over
        the words would leave the title white on whatever the artwork happens to be
        there. This is the same layer video mode lays over its own frames.

        The artwork is vertical stripes, so it is the same brightness at every row
        of the panel. Any darkening down it is the shade and nothing else.
        """
        art = artwork(tmp_path)
        framing = render.Framing(0.5, 0.75, 0.9)
        left, top, right, bottom = compose.card_rect(
            compose.card_aspect(art), framing)
        assert top < 1250 and bottom > 1650, "the panel has to cross the shade"
        made = compose.build_card(art, TEXT, tmp_path / "low.png", framing=framing)
        picture = Image.open(made).convert("L")
        scale = picture.width / compose.WIDTH

        def row(y):
            return sum(picture.getpixel((round(x * scale), round(y * scale)))
                       for x in range(left + 20, right - 20, 25))

        assert row(1650) < row(1250) * 0.8, "the shade was not laid over the panel"

    def test_placing_it_where_it_already_is_changes_nothing(self, tmp_path):
        """The whole of the no-regression promise, drawn rather than argued: the
        placed code path, handed the fitted placement, has to produce the fitted
        card. It pins the shade to the case that needs it as well, because a panel
        stopping where a fitted one stops must not darken anything."""
        art = artwork(tmp_path)
        # The same words the card is drawn with. A fitted card shrinks to leave
        # room for the top text and the label, D-075, so the rectangle to place it
        # at is the one those words produce.
        left, top, right, bottom = compose.card_rect(
            compose.card_aspect(art), None, TEXT)
        same = render.Framing(
            x=(left + right) / 2 / compose.WIDTH,
            y=(top + bottom) / 2 / compose.HEIGHT,
            size=(right - left) / compose.WIDTH,
        )
        fitted = compose.build_card(art, TEXT, tmp_path / "f.png")
        placed = compose.build_card(art, TEXT, tmp_path / "p.png", framing=same)
        assert fitted.read_bytes() == placed.read_bytes()

    def test_every_extreme_placement_still_draws(self, tmp_path):
        """Off every edge, at both ends of the size range, and above the frame.
        Pillow clips a paste and a rounded rectangle, but a negative row has
        already been one bug in this tool once."""
        art = artwork(tmp_path)
        for framing in (
            render.Framing(0.5, 0.5, render.FRAMING_MAX_SIZE),
            render.Framing(0.5, 0.5, render.FRAMING_MIN_SIZE),
            render.Framing(-render.FRAMING_REACH, -render.FRAMING_REACH, 0.5),
            render.Framing(render.FRAMING_REACH, render.FRAMING_REACH, 0.5),
            render.Framing(0.5, 0.02, 1.4),
        ):
            made = compose.build_card(art, TEXT, tmp_path / "x.png", framing=framing)
            assert Image.open(made).size == (
                round(compose.WIDTH * compose.SUPER),
                round(compose.HEIGHT * compose.SUPER),
            )

    def test_the_shape_it_reports_is_the_shape_it_draws(self, tmp_path):
        """`card_aspect` is read a second time, for the sidecar. If it disagreed
        with what `build_card` measured, the page would draw its box around a panel
        that is not there."""
        for size in ((1280, 720), (1000, 1000), (1600, 600)):
            art = artwork(tmp_path, *size)
            trimmed = compose.trim_bars(Image.open(art).convert("RGB"))
            assert compose.card_aspect(art) == trimmed.width / trimmed.height


class TestTheWordsAboveAndBelowTheCard:
    """D-075. "Text above title" put a line above the artwork in card mode and
    above the title in video mode, so one field meant two things; and the top text
    was wrapped to whatever room the label left it, which on a tall card was
    nothing, so it was drawn as nothing and never mentioned again."""

    def test_the_label_sits_above_the_title_in_both_modes(self):
        """The card gives way for it exactly as the frames do."""
        plain = compose.CardText(title="T", channel="C")
        labelled = compose.CardText(title="T", channel="C", eyebrow="NOW PLAYING")
        assert compose.card_floor(labelled) < compose.card_floor(plain)
        assert compose.video_picture_bottom(labelled) < compose.video_picture_bottom(plain)
        # Both floors are measured off their own title, one gap above the label.
        assert compose.card_floor(labelled) == (
            compose.eyebrow_top(compose.CARD_TITLE_TOP,
                                compose.eyebrow_lines("NOW PLAYING")) - compose.CARD_GAP)

    def test_a_fitted_card_shrinks_so_the_top_text_has_room(self):
        """Nineteen pixels of artwork were the difference between a line drawn and
        a line dropped in silence: a full height card's top lands on 325, and one
        line of top text needs 344."""
        square = 1.0
        plain = compose.CardText(title="T", channel="C")
        topped = compose.CardText(title="T", channel="C", topline="SHAYAN SERIES")
        assert compose.card_rect(square, None, plain)[1] == 325
        assert compose.card_rect(square, None, topped)[1] == compose.top_text_floor(topped)
        assert compose.topline_room(compose.card_rect(square, None, topped)[1]) >= 1

    def test_a_fitted_card_never_drops_a_line(self):
        for aspect in (0.5, 1.0, 4 / 3, 16 / 9, 2.4):
            for words in ("Watch till the end", "A"):
                text = compose.CardText(title="T", channel="C", topline=words,
                                        eyebrow="NOW PLAYING")
                top = compose.card_rect(aspect, None, text)[1]
                assert compose.topline_dropped(text, video=False, top=top) == 0

    def test_a_card_placed_too_high_says_so_rather_than_going_quiet(self):
        """The one case left, and the whole reason the page has a sentence for it."""
        text = compose.CardText(title="T", channel="C", topline="SHAYAN SERIES")
        assert compose.topline_dropped(text, video=False, top=325) == 1
        assert compose.topline_dropped(text, video=False, top=700) == 0

    def test_video_mode_moves_its_picture_and_so_never_drops_one(self):
        text = compose.CardText(title="T", channel="C", topline="SHAYAN SERIES")
        assert compose.topline_dropped(text, video=True, top=0) == 0

    def test_no_extras_leaves_every_card_ever_made_where_it_was(self):
        """The whole no-regression promise: the fields are off by default, and a
        clip with neither must be the pixel-identical card it always was."""
        plain = compose.CardText(title="T", channel="C")
        for aspect in (0.5, 1.0, 4 / 3, 16 / 9, 2.4):
            assert compose.card_rect(aspect, None, plain) == compose.card_rect(aspect)

    def test_a_placed_picture_over_the_label_gets_a_scrim_under_it(self, tmp_path):
        """The label is anchored to the title, and a placed picture can reach down
        over the row it lands on, where the ramp has barely begun: measured at
        alpha 1 out of 200, which is white letters on a bright frame."""
        size = (compose.WIDTH, compose.HEIGHT)
        brow = compose.eyebrow_lines("NOW PLAYING")
        row = compose.eyebrow_top(compose.VIDEO_TITLE_TOP, brow)
        default = compose._bottom_shade(size).getpixel((10, row + 4))[3]
        raised = compose._bottom_shade(size, row).getpixel((10, row + 4))[3]
        assert default <= 2, "the row the label lands on is bare by default"
        assert raised > 40, "and has something to be read against when raised"

    def test_a_fitted_picture_is_left_exactly_as_it_was(self, tmp_path):
        """It stops above the label, so nothing about it needs darkening and the
        look of every video clip ever made is unchanged."""
        text = compose.CardText(title="T", channel="C", eyebrow="NOW PLAYING")
        fitted = compose.build_overlay(
            text, tmp_path / "a.png",
            picture_top=compose.video_picture_top(text),
            picture_bottom=compose.video_picture_bottom(text))
        none = compose.build_overlay(text, tmp_path / "b.png",
                                     picture_top=compose.video_picture_top(text))
        assert fitted.read_bytes() == none.read_bytes()

    def test_a_picture_reaching_the_label_is_the_one_that_changes(self, tmp_path):
        text = compose.CardText(title="T", channel="C", eyebrow="NOW PLAYING")
        over = compose.build_overlay(text, tmp_path / "c.png", picture_top=200,
                                     picture_bottom=compose.HEIGHT)
        clear = compose.build_overlay(text, tmp_path / "d.png", picture_top=200,
                                      picture_bottom=compose.SAFE_TOP)
        assert over.read_bytes() != clear.read_bytes()
