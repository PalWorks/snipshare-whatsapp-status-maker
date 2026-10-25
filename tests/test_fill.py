"""What goes behind the frames in video mode: a blurred copy of them, or black.

Two things are pinned here. The **graph**, because the black one is a single `pad`
rather than a black source overlaid, and a `color` filter with no duration is how a
render hangs. And **`recompose`**, which reproduces the same two backgrounds in Pillow
so the page can show one the clip was not made with. That second one exists only
because a background is under everything: unlike the words, it cannot be drawn over
what is already on screen.
"""

from __future__ import annotations

import pytest
from PIL import Image

from wastatus import compose, render

RECT = render.Picture(width=640, height=1138, left=220, top=391)


class TestTheFilterGraph:
    def test_the_default_is_the_blurred_copy_it_always_was(self):
        steps = ";".join(render.picture_steps("0:v", "out", rect=RECT))
        assert "split=2" in steps
        assert f"gblur=sigma={render.FILL_SIGMA}" in steps
        assert "eq=brightness=-0.20" in steps

    def test_black_is_the_frames_painted_out_rather_than_a_colour_source(self):
        """A `color` source has no natural end: overlaying one needs a duration, a
        frame rate and a `shortest` to stop it, and a source with none of those is
        how a render hangs. Painting the frames black needs none of that."""
        steps = ";".join(render.picture_steps("0:v", "out", rect=RECT,
                                              fill=render.BLACK))
        assert "color=black" in steps and "color=c=" not in steps
        assert "gblur" not in steps, "the black fill is not blurring anything"
        assert f"scale={RECT.width}:{RECT.height}" in steps

    def test_neither_fill_uses_pad_any_more(self):
        """`pad` cannot take a negative offset or an input larger than its output,
        and a placed picture is allowed to be both. See D-061."""
        for fill in render.FILLS:
            steps = ";".join(render.picture_steps("0:v", "out", rect=RECT, fill=fill))
            assert "pad=" not in steps
            assert f"overlay={RECT.left}:{RECT.top}" in steps

    def test_a_picture_hanging_off_the_frame_is_overlaid_where_it_says(self):
        out = render.Picture(width=3240, height=5760, left=-1080, top=-1920)
        for fill in render.FILLS:
            steps = ";".join(render.picture_steps("0:v", "out", rect=out, fill=fill))
            assert "overlay=-1080:-1920" in steps

    def test_the_picture_lands_in_the_same_place_either_way(self):
        """The words are anchored to that rectangle, so the two backgrounds cannot
        put the frames anywhere different from each other."""
        for fill in render.FILLS:
            steps = ";".join(render.picture_steps("0:v", "out", rect=RECT, fill=fill))
            assert f"{RECT.left}:{RECT.top}" in steps

    def test_an_unknown_fill_falls_back_to_the_blur(self):
        """Nothing should reach here unvalidated, and if it does it gets the
        default rather than a graph with a hole in it."""
        steps = render.picture_steps("0:v", "out", rect=RECT, fill="tartan")
        assert "gblur" in ";".join(steps)


class TestBuildingTheFrameAgainForThePreview:
    """`recompose` is for the preview and never for the clip."""

    def frame(self):
        """A finished frame: a red picture on a blue fill, where RECT says."""
        canvas = Image.new("RGB", (compose.WIDTH, compose.HEIGHT), (20, 40, 200))
        canvas.paste(Image.new("RGB", (RECT.width, RECT.height), (200, 30, 30)),
                     (RECT.left, RECT.top))
        return canvas

    def test_black_keeps_the_picture_and_blacks_out_the_rest(self):
        """Exact, not approximate: a pad and a paste put the same pixels in the
        same places, which is what the clip itself would do."""
        done = render.recompose(self.frame(), RECT, render.BLACK)
        assert done.getpixel((RECT.left + 5, RECT.top + 5)) == (200, 30, 30)
        assert done.getpixel((10, 10)) == (0, 0, 0)
        assert done.getpixel((compose.WIDTH - 10, compose.HEIGHT - 10)) == (0, 0, 0)

    def test_the_picture_is_not_touched_by_either_of_them(self):
        original = self.frame()
        box = (RECT.left, RECT.top, RECT.left + RECT.width, RECT.top + RECT.height)
        for fill in render.FILLS:
            assert render.recompose(original, RECT, fill).crop(box).tobytes() == \
                original.crop(box).tobytes()

    def test_the_blur_comes_from_the_picture_and_is_darker_than_it(self):
        """It is the same operation ffmpeg is given: the frames scaled to cover,
        blurred, then darkened. Close rather than identical, because Pillow's kernel
        is not ffmpeg's, and this says what a background will look like."""
        black = Image.new("RGB", (compose.WIDTH, compose.HEIGHT), (0, 0, 0))
        black.paste(Image.new("RGB", (RECT.width, RECT.height), (200, 30, 30)),
                    (RECT.left, RECT.top))
        done = render.recompose(black, RECT, render.BLUR)
        corner = done.getpixel((10, 10))
        assert corner != (0, 0, 0), "the blurred fill was not built"
        assert corner[0] < 200, "the fill has to be darker than the picture it came from"
        assert corner[0] > corner[1], "and it has to come from the picture's own colour"

    def test_it_never_changes_the_size_of_the_frame(self):
        for fill in render.FILLS:
            assert render.recompose(self.frame(), RECT, fill).size == \
                (compose.WIDTH, compose.HEIGHT)


class TestTheJobCarriesTheChoice:
    def test_a_job_is_blurred_unless_it_says_otherwise(self):
        from wastatus import pipeline

        assert pipeline.Job(url="x", start=0, end=15).fill == render.BLUR

    def test_the_command_line_offers_the_same_two(self):
        """The page and the command line take the same clip, so they take the same
        backgrounds. A flag the page has and the terminal does not is a fork."""
        from wastatus import cli

        parser = cli.build_parser()
        assert parser.parse_args(["u"]).fill == render.BLUR
        assert parser.parse_args(["u", "--fill", "black"]).fill == render.BLACK
        with pytest.raises(SystemExit):
            parser.parse_args(["u", "--fill", "tartan"])


class TestPlacingThePictureItself:
    """D-061. The picture becomes a placed thing, in the units everything placed
    uses: a centre and a width, as fractions of the frame. What it does not get is
    a height, because that is not a choice: it follows the source's own shape."""

    SOURCE = (1280, 720)     # a 16:9 source, cropped or not

    def test_nothing_asked_for_means_fitted_as_it_always_was(self):
        assert render.parse_framing(None) is None
        assert render.parse_framing({}) is None
        assert render.parse_framing("") is None

    def test_a_placement_is_clamped_rather_than_refused(self):
        """Half off the frame is a choice. x=900 is a bug in whatever sent it."""
        placed = render.parse_framing({"x": 900, "y": -900, "size": 99})
        assert placed.x == render.FRAMING_REACH
        assert placed.y == -render.FRAMING_REACH
        assert placed.size == render.FRAMING_MAX_SIZE

    def test_junk_is_refused_before_it_reaches_pillow(self):
        for bad in ({"size": "wide"}, {"x": float("nan")}, [1, 2, 3], "0.5"):
            with pytest.raises(ValueError):
                render.parse_framing(bad)

    def test_the_width_is_the_size_and_the_height_follows_the_source(self):
        rect = render.placed_rect(self.SOURCE, render.Framing(0.5, 0.5, 1.0))
        assert rect.width == compose.WIDTH
        assert abs(rect.height - compose.WIDTH * 720 / 1280) <= 2
        assert rect.left == 0
        assert abs(rect.top - (compose.HEIGHT - rect.height) / 2) <= 2

    def test_it_is_centred_on_the_point_it_was_given(self):
        rect = render.placed_rect(self.SOURCE, render.Framing(0.25, 0.75, 0.5))
        assert abs((rect.left + rect.width / 2) - 0.25 * compose.WIDTH) <= 2
        assert abs((rect.top + rect.height / 2) - 0.75 * compose.HEIGHT) <= 2

    def test_a_picture_may_hang_off_any_edge(self):
        """Which is what full bleed means, and `overlay` clips what hangs off."""
        rect = render.placed_rect(self.SOURCE, render.Framing(0.0, 0.0, 2.0))
        assert rect.left < 0 and rect.top < 0
        assert rect.width > compose.WIDTH

    def test_both_dimensions_stay_even(self):
        """yuv420p's chroma plane cannot take an odd width or height."""
        for size in (0.31, 0.777, 1.13, 2.9):
            rect = render.placed_rect((1080, 1441), render.Framing(0.5, 0.5, size))
            assert rect.width % 2 == 0 and rect.height % 2 == 0

    def test_a_fitted_rectangle_can_say_what_placement_it_is(self):
        """Switching from fitted to placed has to start where the eye already is,
        which means reading the placement back off the rectangle."""
        fitted = render.picture_rect(self.SOURCE)
        placed = render.placed_rect(self.SOURCE, render.framing_of(fitted))
        for was, now in ((fitted.width, placed.width), (fitted.height, placed.height),
                         (fitted.left, placed.left), (fitted.top, placed.top)):
            assert abs(was - now) <= 2, f"{fitted} came back as {placed}"


class TestMovingThePictureInThePreview:
    """`recompose` moves it as well as changing what is behind it, because both
    live under the words and neither can be drawn over what is already there."""

    RECT = render.Picture(width=640, height=1138, left=220, top=391)

    def frame(self):
        canvas = Image.new("RGB", (compose.WIDTH, compose.HEIGHT), (20, 40, 200))
        canvas.paste(Image.new("RGB", (self.RECT.width, self.RECT.height),
                               (200, 30, 30)), (self.RECT.left, self.RECT.top))
        return canvas

    def test_the_picture_lands_where_it_is_sent(self):
        to = render.Picture(width=320, height=569, left=40, top=60)
        done = render.recompose(self.frame(), self.RECT, render.BLACK, to=to)
        assert done.getpixel((to.left + 5, to.top + 5)) == (200, 30, 30)
        # and where it used to be is background now
        assert done.getpixel((self.RECT.left + 300, self.RECT.top + 900)) == (0, 0, 0)

    def test_it_can_be_sent_off_the_edge(self):
        to = render.Picture(width=2160, height=3840, left=-540, top=-960)
        done = render.recompose(self.frame(), self.RECT, render.BLACK, to=to)
        assert done.size == (compose.WIDTH, compose.HEIGHT)
        assert done.getpixel((5, 5)) == (200, 30, 30), "a full bleed picture is not full"

    def test_sending_it_nowhere_leaves_it_alone(self):
        done = render.recompose(self.frame(), self.RECT, render.BLUR)
        box = (self.RECT.left, self.RECT.top,
               self.RECT.left + self.RECT.width, self.RECT.top + self.RECT.height)
        assert done.crop(box).tobytes() == self.frame().crop(box).tobytes()


class TestTheCommandLineTakesAPlacement:
    """The page and the terminal have to be able to hand each other the same clip."""

    def test_three_fractions(self):
        from wastatus import cli

        assert cli._framing("0.4,0.3,1.4") == render.Framing(0.4, 0.3, 1.4)

    def test_nothing_given_means_fitted(self):
        from wastatus import cli

        assert cli._framing(None) is None
        assert cli._framing("") is None

    def test_it_says_what_it_wanted(self):
        from wastatus import cli

        for bad in ("0.5,0.5", "0.5,0.5,1,1", "middle,0.5,1"):
            with pytest.raises(ValueError, match="--picture"):
                cli._framing(bad)

    def test_it_is_clamped_like_everything_else_placed(self):
        from wastatus import cli

        assert cli._framing("9,9,9").size == render.FRAMING_MAX_SIZE
