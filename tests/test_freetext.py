"""Free text: a line you write, drag and resize on the frame.

The whole feature rests on one bargain, and these hold it: **the page never draws
the words**. It places a picture of them that the server drew, and the renderer
draws the same picture again at the frame's own scale. If those two ever disagreed
about the shape of a line, the box you dragged would not be the pixels ffmpeg burns
in, and free text would be free only until you pressed Make.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from wastatus import compose, freetext, stickers


class TestTheWordsThemselves:
    def test_a_line_is_one_line(self):
        """Sized by its width, so a second line would halve the face on a drag
        nobody made. Two lines are two texts, each dragged where it belongs."""
        assert freetext.clean("one\ntwo   three\t four ") == "one two three four"

    def test_nothing_is_nothing(self):
        assert freetext.clean("   \n  ") == ""
        assert freetext.clean(None) == ""

    def test_it_is_capped(self):
        assert len(freetext.clean("x" * 500)) == freetext.MAX_CHARS

    def test_a_line_with_nothing_in_it_cannot_be_drawn(self):
        with pytest.raises(ValueError, match="nothing to draw"):
            freetext.render("   ", 400)


class TestTheShapeOfALine:
    """A placed line is a rectangle to everything above it. This is that rectangle."""

    LINE = "Soak in the powerful presence of Kailash"

    def test_it_is_exactly_the_width_it_was_asked_for(self):
        """That width is the fraction of the frame the page has drawn a box round."""
        for width in (120, 480, 648, 1080):
            assert freetext.render(self.LINE, width).width == width

    def test_the_same_words_keep_their_shape_at_any_size(self):
        """The page scales one picture into a 300 pixel frame and the renderer draws
        another at 1080. Disagree here and the words land somewhere else in the clip
        than in the box, which is the one thing this design exists to prevent."""
        page = freetext.render(self.LINE, 720)
        clip = freetext.render(self.LINE, 1080)
        page_shape = page.height / page.width
        clip_shape = clip.height / clip.width
        assert abs(page_shape - clip_shape) / clip_shape < 0.05

    def test_a_longer_line_at_the_same_width_is_set_smaller(self):
        """Which is what dragging the corner means: the box is the size, not the
        face. A sentence at a fifth of the frame would be unreadable otherwise."""
        short = freetext.render("Kailash", 600)
        long = freetext.render("Kailash, and the whole of the sojourn", 600)
        assert long.height < short.height

    def test_the_measurement_matches_what_gets_drawn(self):
        """`aspect` answers without rasterising anything, and the covered-by-WhatsApp
        warning trusts it. It has to be the same shape the drawing comes out."""
        drawn = freetext.render(self.LINE, 900)
        assert abs(freetext.aspect(self.LINE) - drawn.height / drawn.width) < 0.005

    def test_a_line_is_wider_than_it_is_tall(self):
        """The old warning assumed square, which is a drawing's shape, not a line's."""
        assert freetext.aspect(self.LINE) < 0.2

    def test_it_has_something_in_it(self):
        """A transparent picture of nothing would place and drag exactly like a
        picture of words, and only the finished clip would say otherwise."""
        drawn = freetext.render("Kailash", 400)
        assert drawn.mode == "RGBA"
        assert drawn.getchannel("A").getextrema()[1] > 0, "nothing was drawn"

    def test_the_page_gets_a_png(self):
        raw = freetext.to_png("Kailash", 300)
        assert Image.open(io.BytesIO(raw)).format == "PNG"


class TestPlacingOne:
    """It goes through the same parser, the same splitter and the same paste as a
    sticker. That is the point of it: one code path, two kinds of thing."""

    def test_the_page_sends_a_kind_and_gets_a_line_back(self):
        one = stickers.parse({"kind": "text", "text": "WATCH TILL THE END",
                              "x": 0.5, "y": 0.2, "size": 0.55})
        assert isinstance(one, freetext.FreeText)
        assert one.text == "WATCH TILL THE END"
        assert (one.x, one.y, one.size) == (0.5, 0.2, 0.55)

    def test_an_older_sidecar_has_no_kind_and_is_still_a_sticker(self):
        one = stickers.parse({"id": "openmoji:1F64F", "x": 0.5, "y": 0.5})
        assert isinstance(one, stickers.Sticker)

    def test_a_line_with_no_words_is_refused(self):
        with pytest.raises(ValueError, match="something to say"):
            stickers.parse({"kind": "text", "text": "  "})

    def test_placement_is_clamped_the_same_way_a_sticker_is(self):
        """Half off the frame is a choice. x=900 is a bug in whatever sent it."""
        one = stickers.parse({"kind": "text", "text": "x", "x": 900, "size": 40})
        assert one.x == 1.5
        assert one.size == stickers.MAX_SIZE

    def test_it_survives_the_round_trip_through_the_sidecar(self):
        """The sidecar is what fills the form back in from a clip in Recent. A line
        that cannot be read back is a line that vanishes when you re-open the clip."""
        first = stickers.parse({"kind": "text", "text": "Kailash, August 2026",
                                "x": 0.4, "y": 0.7, "size": 0.45, "rotation": -4})
        again = stickers.parse(first.as_json())
        assert again == first

    def test_nothing_written_ever_animates(self):
        """`split` decides which mechanism draws a thing. Text is always Pillow's."""
        placed = stickers.parse_all([{"kind": "text", "text": "hello"}])
        still, moving = stickers.split(placed)
        assert (len(still), len(moving)) == (1, 0)

    def test_it_lands_on_the_canvas_where_it_was_put(self):
        canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 255))
        placed = stickers.parse_all([
            {"kind": "text", "text": "WATCH TILL THE END", "x": 0.5, "y": 0.25,
             "size": 0.6},
        ])
        assert stickers.paste(canvas, placed) == 1
        # The line is centred on y=0.25 of the frame and is nowhere near the top.
        band = canvas.crop((0, 400, 1080, 560)).convert("L").getextrema()
        assert band[1] > 200, "no white line where it was placed"
        assert canvas.crop((0, 0, 1080, 200)).convert("L").getextrema()[1] == 0

    def test_a_line_nobody_can_draw_does_not_take_the_clip_down(self, monkeypatch):
        """Everything else on the frame is already made by the time this runs."""
        monkeypatch.setattr(
            freetext, "render",
            lambda text, width: (_ for _ in ()).throw(OSError("no font today")),
        )
        canvas = Image.new("RGBA", (1080, 1920), (0, 0, 0, 255))
        assert stickers.paste(canvas, [freetext.FreeText(text="hello")]) == 0


class TestTheWarningAboutWhatsAppsOwnFurniture:
    """A wide, short line is not a square drawing, and saying it was warned about
    text that sat nowhere near the band."""

    def test_a_line_near_the_top_is_not_warned_about_for_being_wide(self):
        one = freetext.FreeText(text="Kailash, August 2026", x=0.5, y=0.2, size=0.8)
        assert not compose.covered_by_whatsapp(one)

    def test_a_line_actually_under_the_header_is_warned_about(self):
        one = freetext.FreeText(text="Kailash, August 2026", x=0.5, y=0.05, size=0.8)
        assert compose.covered_by_whatsapp(one)

    def test_a_drawing_is_still_treated_as_square(self):
        """OpenMoji is square, and the arithmetic that assumed it stays right."""
        assert stickers.Sticker(id="openmoji:1F64F").aspect == 1.0
