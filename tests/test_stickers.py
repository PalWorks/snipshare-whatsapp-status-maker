"""The sticker library and the placement contract.

The load bearing claim is the coordinate one: the browser drags a sticker over a
296 pixel preview, the renderer pastes it onto a 1620 pixel canvas, and the two
have to agree without exchanging a scale factor. Fractions of the frame are what
make that true, so the arithmetic gets tests rather than trust.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from wastatus import compose, stickers


@pytest.fixture
def library(tmp_path, monkeypatch):
    """A small stand in for the 45 MB install, so tests need no download."""
    monkeypatch.setenv("WASTATUS_STICKER_DIR", str(tmp_path))
    stickers._catalogue.cache_clear()
    (tmp_path / "openmoji").mkdir()
    (tmp_path / "mine").mkdir()
    for hexcode, colour in (("1F64F", (255, 0, 0, 255)), ("1FA94", (0, 255, 0, 255))):
        Image.new("RGBA", (618, 618), colour).save(tmp_path / "openmoji" / f"{hexcode}.png")
    (tmp_path / "openmoji.json").write_text(
        '[{"hexcode": "1F64F", "annotation": "folded hands", "tags": "pray, please",'
        ' "openmoji_tags": "", "subgroups": "hand-fingers-partial", "group":'
        ' "people-body", "order": 1, "skintone": ""},'
        ' {"hexcode": "1FA94", "annotation": "diya lamp", "tags": "oil, lamp",'
        ' "openmoji_tags": "", "subgroups": "light-video", "group": "objects",'
        ' "order": 2, "skintone": ""},'
        ' {"hexcode": "1F64F-1F3FD", "annotation": "folded hands: medium skin tone",'
        ' "tags": "", "openmoji_tags": "", "subgroups": "", "group": "people-body",'
        ' "order": 3, "skintone": "medium"}]',
        encoding="utf-8",
    )
    yield tmp_path
    stickers._catalogue.cache_clear()


class TestReadingASticker:
    def test_a_placement_survives_the_round_trip(self):
        placed = stickers.parse(
            {"id": "openmoji:1F64F", "x": 0.25, "y": 0.8, "size": 0.4, "rotation": -30}
        )
        assert placed.as_json() == {
            "id": "openmoji:1F64F", "x": 0.25, "y": 0.8, "size": 0.4, "rotation": -30.0
        }

    def test_defaults_put_it_in_the_middle_of_the_usable_space(self):
        placed = stickers.parse({"id": "mine:cat"})
        assert (placed.x, placed.y) == (0.5, 0.45)
        assert placed.size == 0.2

    @pytest.mark.parametrize("bad", [
        "openmoji:../../etc/passwd",
        "openmoji:1F64F/../../x",
        "elsewhere:1F64F",
        "openmoji:",
        "1F64F",
        "mine:a.png",
    ])
    def test_an_id_that_could_address_a_file_is_refused(self, bad):
        with pytest.raises(ValueError):
            stickers.parse({"id": bad})

    def test_a_size_beyond_the_frame_is_clamped_not_refused(self):
        assert stickers.parse({"id": "mine:x", "size": 40}).size == stickers.MAX_SIZE
        assert stickers.parse({"id": "mine:x", "size": 0}).size == stickers.MIN_SIZE

    def test_a_position_off_the_frame_is_allowed_within_reason(self):
        """Half off the edge is a look. Twelve frames away is a bug upstream."""
        assert stickers.parse({"id": "mine:x", "x": -0.2}).x == -0.2
        assert stickers.parse({"id": "mine:x", "x": 900}).x == 1.5

    @pytest.mark.parametrize("bad", ["nan", "banana", None, [1]])
    def test_a_number_that_is_not_one_is_refused(self, bad):
        with pytest.raises(ValueError):
            stickers.parse({"id": "mine:x", "size": bad})

    def test_a_list_of_placements(self):
        assert stickers.parse_all(None) == []
        assert len(stickers.parse_all([{"id": "mine:a"}, {"id": "mine:b"}])) == 2

    def test_a_frame_full_of_stickers_is_refused(self):
        with pytest.raises(ValueError, match="too many"):
            stickers.parse_all([{"id": "mine:a"}] * 21)

    def test_something_that_is_not_a_list_is_refused(self):
        with pytest.raises(ValueError):
            stickers.parse_all({"id": "mine:a"})


class TestFindingOne:
    def test_an_id_resolves_to_its_file(self, library):
        assert stickers.resolve("openmoji:1F64F") == library / "openmoji" / "1F64F.png"

    def test_a_traversal_resolves_to_nothing(self, library):
        assert stickers.resolve("openmoji:../../../etc/passwd") is None

    def test_a_sticker_that_is_not_installed_resolves_to_nothing(self, library):
        assert stickers.resolve("openmoji:DEAD") is None


class TestSearching:
    def test_a_word_finds_its_sticker(self, library):
        assert [hit["name"] for hit in stickers.search("diya")] == ["diya lamp"]

    def test_a_prefix_is_enough(self, library):
        assert [hit["name"] for hit in stickers.search("pra")] == ["folded hands"]

    def test_a_short_word_does_not_match_the_middle_of_another(self, library):
        """`om` should find `om`, not every emoji whose tags contain `bloom`."""
        assert stickers.search("amp") == []

    def test_skin_tone_variants_are_left_out(self, library):
        names = [hit["name"] for hit in stickers.search("folded")]
        assert names == ["folded hands"]

    def test_your_own_stickers_come_first(self, library):
        Image.new("RGBA", (64, 64)).save(library / "mine" / "diya-of-mine.png")
        assert stickers.search("diya")[0]["id"] == "mine:diya-of-mine"
        assert stickers.search("diya")[0]["mine"] is True

    def test_an_empty_search_opens_on_a_shelf_not_on_grinning_faces(self, library):
        opening = stickers.search("")
        assert opening, "an empty search should still offer something"
        assert all(hit["id"].startswith(("openmoji:", "mine:")) for hit in opening)

    def test_the_opening_shelf_names_no_sticker_twice(self):
        """A repeat costs a slot on a phone screen rather than adding one.

        This is a real bug that shipped: `1F4FF` was listed at positions 12 and 27,
        so the shelf of forty offered thirty nine stickers and the prayer beads
        twice. The list is hand written, so the guard belongs in a test.
        """
        assert len(stickers.OPENING_SHELF) == len(set(stickers.OPENING_SHELF))

    def test_a_repeated_shelf_entry_is_still_served_once(self, library):
        """Even if someone reintroduces one, the page must not show it twice."""
        with_repeat = ("1F64F", "1FA94", "1F64F")
        monkey = pytest.MonkeyPatch()
        monkey.setattr(stickers, "OPENING_SHELF", with_repeat)
        try:
            ids = [hit["id"] for hit in stickers.search("")]
        finally:
            monkey.undo()
        assert ids == ["openmoji:1F64F", "openmoji:1FA94"]

    def test_a_sticker_with_no_file_is_not_offered(self, library):
        (library / "openmoji" / "1FA94.png").unlink()
        stickers._catalogue.cache_clear()
        assert stickers.search("diya") == []


class TestPasting:
    def canvas(self, size=(1080, 1920)):
        return Image.new("RGBA", size, (0, 0, 0, 0))

    def test_a_sticker_lands_centred_on_its_coordinates(self, library):
        canvas = self.canvas()
        stickers.paste(canvas, [stickers.Sticker("openmoji:1F64F", 0.5, 0.5, 0.2)])
        # 0.2 of 1080 is 216 wide, square, centred on (540, 960).
        assert canvas.getbbox() == (432, 852, 648, 1068)

    def test_the_same_fractions_land_the_same_way_on_the_supersampled_card(self, library):
        """The card is 1620 wide and the overlay is 1080. Fractions have to mean the
        same thing on both, or the preview lies about one of them."""
        small = self.canvas((1080, 1920))
        large = self.canvas((1620, 2880))
        placed = [stickers.Sticker("openmoji:1F64F", 0.25, 0.6, 0.3)]
        stickers.paste(small, placed)
        stickers.paste(large, placed)
        assert [round(v / 1080, 3) for v in small.getbbox()[:2]] == \
               [round(v / 1620, 3) for v in large.getbbox()[:2]]

    def test_turning_one_keeps_it_centred(self, library):
        canvas = self.canvas()
        stickers.paste(canvas, [stickers.Sticker("openmoji:1F64F", 0.5, 0.5, 0.2, 45)])
        left, top, right, bottom = canvas.getbbox()
        assert abs((left + right) / 2 - 540) <= 1
        assert abs((top + bottom) / 2 - 960) <= 1

    def test_they_are_pasted_in_order(self, library):
        canvas = Image.new("RGBA", (100, 100), (0, 0, 0, 255))
        stickers.paste(canvas, [
            stickers.Sticker("openmoji:1F64F", 0.5, 0.5, 1.0),   # red
            stickers.Sticker("openmoji:1FA94", 0.5, 0.5, 1.0),   # green
        ])
        assert canvas.getpixel((50, 50))[:3] == (0, 255, 0)

    def test_a_sticker_this_machine_does_not_have_is_skipped(self, library):
        canvas = self.canvas()
        landed = stickers.paste(canvas, [
            stickers.Sticker("openmoji:NOPE", 0.5, 0.5, 0.2),
            stickers.Sticker("openmoji:1F64F", 0.5, 0.5, 0.2),
        ])
        assert landed == 1
        assert canvas.getbbox() is not None

    def test_nothing_to_paste_is_not_an_error(self, library):
        canvas = self.canvas()
        assert stickers.paste(canvas, []) == 0
        assert canvas.getbbox() is None


class TestTheReservedBands:
    def test_a_sticker_in_the_middle_is_clear(self):
        assert not compose.covered_by_whatsapp(stickers.Sticker("mine:x", 0.5, 0.5, 0.2))

    def test_one_under_the_caption_is_reported(self):
        assert compose.covered_by_whatsapp(stickers.Sticker("mine:x", 0.5, 0.95, 0.2))

    def test_one_behind_the_header_is_reported(self):
        assert compose.covered_by_whatsapp(stickers.Sticker("mine:x", 0.5, 0.05, 0.2))

    def test_a_full_width_sticker_centred_vertically_still_clears_both_bands(self):
        """Surprising until you remember the frame is 9:16: a square as wide as the
        whole frame is 1026 pixels tall in a 1920 pixel frame, so it fits between a
        band at 230 and one at 1632 with room to spare."""
        assert not compose.covered_by_whatsapp(stickers.Sticker("mine:x", 0.5, 0.5, 0.95))

    def test_a_full_width_sticker_pushed_down_does_reach_the_caption(self):
        assert compose.covered_by_whatsapp(stickers.Sticker("mine:x", 0.5, 0.65, 0.95))

    def test_the_check_uses_the_same_numbers_the_text_layer_does(self):
        """One definition of the bands, in compose.py, or the page's guides and the
        renderer's safe zone drift apart."""
        just_inside = stickers.Sticker(
            "mine:x", 0.5, (compose.SAFE_TOP + 1) / compose.HEIGHT + 0.0001, 0.0
        )
        assert not compose.covered_by_whatsapp(just_inside)


class TestUploading:
    def png(self, size=(64, 64)) -> str:
        buffer = io.BytesIO()
        Image.new("RGBA", size, (1, 2, 3, 255)).save(buffer, "PNG")
        return base64.b64encode(buffer.getvalue()).decode()

    def test_an_upload_becomes_a_sticker(self, library):
        saved = stickers.save_upload("My Cat", self.png())
        assert saved == {
            "id": "mine:my-cat", "name": "my cat", "mine": True, "moving": False,
        }
        assert (library / "mine" / "my-cat.png").is_file()

    def test_a_data_url_prefix_is_tolerated(self, library):
        saved = stickers.save_upload("cat", "data:image/png;base64," + self.png())
        assert stickers.resolve(saved["id"]) is not None

    def test_it_is_written_back_out_by_pillow(self, library):
        """Whatever arrives, what lands on disk is bytes we produced."""
        saved = stickers.save_upload("cat", self.png())
        assert Image.open(stickers.resolve(saved["id"])).format == "PNG"

    def test_a_second_upload_of_the_same_name_does_not_clobber_the_first(self, library):
        first = stickers.save_upload("cat", self.png())
        second = stickers.save_upload("cat", self.png())
        assert first["id"] != second["id"]
        assert stickers.resolve(first["id"]) is not None

    def test_something_that_is_not_an_image_is_refused(self, library):
        with pytest.raises(ValueError, match="not an image"):
            stickers.save_upload("bad", base64.b64encode(b"#!/bin/sh\nrm -rf /").decode())

    def test_junk_that_is_not_base64_is_refused(self, library):
        with pytest.raises(ValueError, match="base64"):
            stickers.save_upload("bad", "!!!! not base64 !!!!")

    def test_a_name_that_could_be_a_path_is_refused(self, library):
        with pytest.raises(ValueError, match="name"):
            stickers.save_upload("../../etc/passwd", self.png())

    def test_an_upload_that_is_really_a_photo_is_refused(self, library):
        """A real image, over the still ceiling. Noise so PNG cannot compress it.

        The payload has to be a genuine image now: the byte ceiling applied before
        decoding is the generous animated one, and which of the two ceilings a file
        is held to is not known until Pillow has said how many frames it has.
        """
        import os
        buffer = io.BytesIO()
        Image.frombytes("RGB", (1200, 1200), os.urandom(1200 * 1200 * 3)).save(
            buffer, "PNG"
        )
        assert buffer.tell() > stickers.UPLOAD_MAX_BYTES, "the fixture is not big enough"
        with pytest.raises(ValueError, match="under"):
            stickers.save_upload("huge", base64.b64encode(buffer.getvalue()).decode())

    def test_junk_far_past_even_the_animated_ceiling_never_reaches_pillow(self, library):
        big = base64.b64encode(b"x" * (stickers.ANIMATED_MAX_BYTES + 10)).decode()
        with pytest.raises(ValueError, match="under"):
            stickers.save_upload("huge", big)

    def test_a_large_image_is_scaled_down_rather_than_refused(self, library):
        saved = stickers.save_upload("wide", self.png((3000, 1200)))
        assert max(Image.open(stickers.resolve(saved["id"])).size) == \
               stickers.UPLOAD_MAX_EDGE

    def test_only_your_own_stickers_can_be_deleted(self, library):
        with pytest.raises(ValueError, match="your own"):
            stickers.delete_upload("openmoji:1F64F")

    def test_deleting_one_removes_it(self, library):
        saved = stickers.save_upload("cat", self.png())
        assert stickers.delete_upload(saved["id"]) is True
        assert stickers.resolve(saved["id"]) is None

    def test_deleting_one_that_is_gone_says_so(self, library):
        assert stickers.delete_upload("mine:never-existed") is False


class TestThumbnails:
    """The picker drew 618 pixel artwork in 44 pixel cells. See TASKS.md T-020."""

    def test_a_thumbnail_is_the_width_that_was_asked_for(self, library):
        made = stickers.thumbnail("openmoji:1F64F", 96)
        assert made is not None
        with Image.open(made) as image:
            assert image.size == (96, 96)

    def test_it_is_a_great_deal_smaller_than_the_drawing(self, library):
        full = stickers.resolve("openmoji:1F64F")
        small = stickers.thumbnail("openmoji:1F64F", 96)
        assert small.stat().st_size < full.stat().st_size

    def test_the_second_ask_reuses_the_first(self, library):
        first = stickers.thumbnail("openmoji:1F64F", 96)
        stamp = first.stat().st_mtime_ns
        assert stickers.thumbnail("openmoji:1F64F", 96) == first
        assert first.stat().st_mtime_ns == stamp, "it was made a second time"

    def test_a_replaced_upload_is_not_served_from_the_old_copy(self, library):
        """Deleting an upload and adding another under the same name reuses the
        file name, so an older cached copy is stale rather than a hit."""
        import os
        import time

        blue = Image.new("RGBA", (400, 400), (0, 0, 255, 255))
        buffer = io.BytesIO()
        blue.save(buffer, "PNG")
        saved = stickers.save_upload(
            "mine one", base64.b64encode(buffer.getvalue()).decode()
        )
        cached = stickers.thumbnail(saved["id"], 96)
        with Image.open(cached) as image:
            assert image.getpixel((10, 10))[2] > 200      # blue

        source = stickers.resolve(saved["id"])
        Image.new("RGBA", (400, 400), (255, 255, 0, 255)).save(source, "PNG")
        os.utime(source, (time.time() + 5, time.time() + 5))

        with Image.open(stickers.thumbnail(saved["id"], 96)) as image:
            assert image.getpixel((10, 10))[2] < 60       # no longer blue

    def test_deleting_an_upload_takes_its_thumbnails_too(self, library):
        red = io.BytesIO()
        Image.new("RGBA", (300, 300), (255, 0, 0, 255)).save(red, "PNG")
        saved = stickers.save_upload("gone soon", base64.b64encode(red.getvalue()).decode())
        cached = stickers.thumbnail(saved["id"], 96)
        assert cached.is_file()
        assert stickers.delete_upload(saved["id"]) is True
        assert not cached.exists()

    @pytest.mark.parametrize("width", [1, 95, 1000, 618])
    def test_only_the_sizes_the_page_asks_for_are_made(self, library, width):
        """Otherwise one image could be written to disk at a thousand sizes."""
        assert stickers.thumbnail("openmoji:1F64F", width) is None

    def test_a_sticker_that_is_not_there_has_no_thumbnail(self, library):
        assert stickers.thumbnail("openmoji:NOPE", 96) is None

    def test_a_drawing_smaller_than_the_ask_is_not_blown_up(self, library):
        small = io.BytesIO()
        Image.new("RGBA", (40, 40), (0, 0, 0, 255)).save(small, "PNG")
        saved = stickers.save_upload("tiny", base64.b64encode(small.getvalue()).decode())
        with Image.open(stickers.thumbnail(saved["id"], 96)) as image:
            assert image.size == (40, 40)

    def test_an_unwritable_cache_costs_bandwidth_not_the_sticker(self, library, monkeypatch):
        def refuse(*_args, **_kwargs):
            raise OSError("read only file system")

        monkeypatch.setattr(stickers.Image.Image, "save", refuse)
        served = stickers.thumbnail("openmoji:1F64F", 96)
        assert served == stickers.resolve("openmoji:1F64F")

    def test_the_cache_lives_beside_the_library_not_in_it(self, library):
        stickers.thumbnail("openmoji:1F64F", 96)
        assert (library / "cache" / "96").is_dir()
        assert sorted(p.name for p in (library / "openmoji").glob("*")) == [
            "1F64F.png", "1FA94.png",
        ]


class TestAnimatedStickers:
    """A sticker that moves is a second mechanism, not a bigger paste.

    The rule the rest of the code leans on: `motion` answers yes or no from the file
    on disk, `split` divides a placed list by that answer, and nothing else has to
    know. See DECISIONS.md D-036.
    """

    def frames(self, count: int, size) -> list:
        """Frames that differ **after** a GIF reader has composited them.

        Two traps, both of which produced a one frame file that read as a still and
        failed every test built on it for reasons unrelated to the code:

        1. Pillow drops a frame identical to the one before it when writing a GIF.
        2. A GIF frame is composited onto the frame before it unless the source says
           otherwise, so a shape that only ever shrinks leaves the larger one showing
           through and every composited frame comes out identical anyway.

        So each frame here repaints the whole canvas in its own colour, with one
        transparent corner that stays transparent throughout.
        """
        made = []
        for at in range(count):
            picture = Image.new("RGBA", size, (9 + at * 20, 200 - at * 15, 40, 255))
            ImageDraw.Draw(picture).rectangle(
                (0, 0, max(1, size[0] // 4), max(1, size[1] // 4)), fill=(0, 0, 0, 0)
            )
            made.append(picture)
        return made

    def gif(self, frames: int = 4, size=(60, 60)) -> str:
        pictures = self.frames(frames, size)
        buffer = io.BytesIO()
        pictures[0].save(buffer, "GIF", save_all=True, append_images=pictures[1:],
                         duration=80, loop=0, disposal=2)
        return base64.b64encode(buffer.getvalue()).decode()

    def webp(self, frames: int = 4, size=(60, 60)) -> str:
        pictures = self.frames(frames, size)
        buffer = io.BytesIO()
        pictures[0].save(buffer, "WEBP", save_all=True, append_images=pictures[1:],
                         duration=80, loop=0)
        return base64.b64encode(buffer.getvalue()).decode()

    def test_an_animated_upload_is_stored_as_a_gif(self, library):
        saved = stickers.save_upload("a flame", self.gif())
        assert saved["moving"] is True
        assert (library / "mine" / "a-flame.gif").is_file()
        assert stickers.resolve(saved["id"]).suffix == ".gif"

    def test_an_animated_webp_becomes_a_gif_because_ffmpeg_cannot_read_one(self, library):
        """Measured 2026-08-20: this ffmpeg refuses animated WebP outright.

        Pillow reads it, so Pillow is the doorman. If this ever changes, the test is
        the place to find out why the conversion exists.
        """
        saved = stickers.save_upload("a lamp", self.webp())
        file = stickers.resolve(saved["id"])
        assert file.suffix == ".gif"
        with Image.open(file) as opened:
            assert opened.format == "GIF"
            assert opened.n_frames == 4

    def test_a_still_upload_is_still_a_png(self, library):
        buffer = io.BytesIO()
        Image.new("RGBA", (40, 40), (1, 2, 3, 255)).save(buffer, "PNG")
        saved = stickers.save_upload("still", base64.b64encode(buffer.getvalue()).decode())
        assert saved["moving"] is False
        assert stickers.resolve(saved["id"]).suffix == ".png"

    def test_motion_answers_from_the_file_not_from_the_name(self, library):
        moving = stickers.save_upload("moves", self.gif())
        assert stickers.motion(moving["id"]) is not None
        assert stickers.motion("openmoji:1F64F") is None
        assert stickers.motion("mine:not-here") is None

    def test_a_split_puts_each_sticker_with_its_own_mechanism(self, library):
        moving = stickers.save_upload("moves", self.gif())
        still, animated = stickers.split([
            stickers.Sticker(id="openmoji:1F64F"),
            stickers.Sticker(id=moving["id"]),
            stickers.Sticker(id="openmoji:1FA94"),
        ])
        assert [one.id for one in still] == ["openmoji:1F64F", "openmoji:1FA94"]
        assert [one.id for one in animated] == [moving["id"]]

    def test_a_still_and_an_animated_sticker_never_share_a_name(self, library):
        """`resolve` looks for two extensions, so two files under one stem would
        make which one you get a matter of ordering."""
        first = stickers.save_upload("twin", self.gif())
        second = stickers.save_upload("twin", "data:image/png;base64," + TestUploading.png(
            TestUploading(), (30, 30)
        ))
        assert first["id"] != second["id"]
        assert stickers.resolve(first["id"]).suffix == ".gif"
        assert stickers.resolve(second["id"]).suffix == ".png"

    def test_deleting_an_animated_one_removes_it(self, library):
        saved = stickers.save_upload("moves", self.gif())
        assert stickers.delete_upload(saved["id"]) is True
        assert stickers.resolve(saved["id"]) is None

    def test_frames_beyond_the_cap_are_dropped_not_refused(self, library, monkeypatch):
        monkeypatch.setattr(stickers, "ANIMATED_MAX_FRAMES", 3)
        saved = stickers.save_upload("long", self.gif(frames=9))
        with Image.open(stickers.resolve(saved["id"])) as opened:
            assert opened.n_frames == 3

    def test_an_oversized_animation_is_scaled_down(self, library):
        saved = stickers.save_upload("big", self.gif(size=(1400, 1400)))
        with Image.open(stickers.resolve(saved["id"])) as opened:
            assert max(opened.size) == stickers.ANIMATED_MAX_EDGE

    def test_the_thumbnail_of_an_animated_sticker_is_a_still(self, library):
        saved = stickers.save_upload("moves", self.gif())
        with Image.open(stickers.thumbnail(saved["id"], 96)) as thumb:
            assert thumb.format == "PNG"
            assert getattr(thumb, "n_frames", 1) == 1


class TestTheAnimatedFilterGraph:
    """What the renderer builds for an animated sticker.

    ffmpeg is not run here. What is checked is the arithmetic that has to agree with
    `stickers.paste`, because the two draw the same coordinates by different routes
    and a disagreement is invisible until you look at a finished clip.
    """

    def placed(self, library, **kwargs):
        pictures = [
            Image.new("RGBA", (100, 50), (9 + at * 40, 9, 9, 255)) for at in range(3)
        ]
        buffer = io.BytesIO()
        pictures[0].save(buffer, "GIF", save_all=True, append_images=pictures[1:],
                         duration=80, loop=0)
        saved = stickers.save_upload(
            "wide", base64.b64encode(buffer.getvalue()).decode()
        )
        return stickers.Sticker(id=saved["id"], **kwargs)

    def test_each_animated_sticker_is_a_looping_input(self, library):
        from wastatus import render

        one = self.placed(library)
        args = render._moving_inputs([one, one])
        assert args.count("-stream_loop") == 2
        assert args.count("-i") == 2
        assert all(args[at] == "-1" for at, value in enumerate(args)
                   if at and args[at - 1] == "-stream_loop")

    def test_the_box_matches_what_pillow_would_have_pasted(self, library):
        """Same fractions, same pixels. A sticker 20 percent of a 1000 pixel canvas
        is 200 pixels wide and centred on its coordinates, whichever draws it."""
        from wastatus import render

        one = self.placed(library, x=0.5, y=0.25, size=0.2)
        steps, label = render._moving_chain([one], "src", (1000, 2000), first=2)
        assert "scale=200:100" in steps[0]
        # centred: 500 - 100 across, 500 - 50 down
        assert "overlay=400:450:shortest=1" in steps[1]
        assert label == "mvd0"

    def test_a_rotation_turns_the_same_way_pillow_turns(self, library):
        """Pillow turns anticlockwise for a positive angle, ffmpeg turns clockwise.

        If the sign is ever dropped, animated stickers mirror the still ones and
        nothing else in the tool notices.
        """
        from wastatus import render

        one = self.placed(library, rotation=30)
        steps, _ = render._moving_chain([one], "src", (1000, 2000), first=2)
        assert "rotate=-0.523599" in steps[0]

    def test_nothing_animated_means_nothing_added(self, library):
        from wastatus import render

        steps, label = render._moving_chain([], "src", (1000, 2000), first=2)
        assert steps == []
        assert label == "src", "the stream carries on under its own name"


class TestThePickerOffersWhatTheServerStores:
    """The file dialog's filter and `save_upload` have to agree.

    They did not. The server has stored animated stickers since T-019 and reports
    them as `moving`, but `accept` on the file input still listed only png, webp and
    jpeg, so the dialog hid every `.gif` and the only way in was to switch the picker
    to "All files". Nothing else was wrong: the upload handler never filtered by type,
    and the server took a GIF happily when one reached it. Found 2026-08-21.
    """

    PAGE = Path(__file__).resolve().parent.parent / "wastatus" / "web" / "index.html"

    def offered(self) -> list[str]:
        page = self.PAGE.read_text(encoding="utf-8")
        match = re.search(r'id="sticker-file"[^>]*?accept="([^"]+)"', page, re.S)
        assert match, "the sticker file input has no accept list"
        return [one.strip() for one in match.group(1).split(",") if one.strip()]

    def _encode(self, fmt: str, *, animated: bool = False) -> str:
        frames = [Image.new("RGBA", (32, 32), (255, 0, 0, 255))]
        if animated:
            frames.append(Image.new("RGBA", (32, 32), (0, 0, 255, 255)))
        buffer = io.BytesIO()
        first, *rest = frames
        if fmt == "JPEG":
            first = first.convert("RGB")
        if rest:
            first.save(buffer, format=fmt, save_all=True, append_images=rest,
                       duration=120, loop=0)
        else:
            first.save(buffer, format=fmt)
        return base64.b64encode(buffer.getvalue()).decode()

    def test_gif_is_offered_at_all(self):
        assert "image/gif" in self.offered(), (
            "the dialog hides GIFs, which is the whole animated sticker path")

    @pytest.mark.parametrize("mime,fmt", [
        ("image/png", "PNG"), ("image/webp", "WEBP"),
        ("image/jpeg", "JPEG"), ("image/gif", "GIF"),
    ])
    def test_every_offered_type_can_actually_be_stored(
            self, mime, fmt, monkeypatch, tmp_path):
        assert mime in self.offered(), f"{mime} is no longer offered by the picker"
        monkeypatch.setattr(stickers, "uploads_dir", lambda: tmp_path)
        entry = stickers.save_upload(f"probe {fmt.lower()}", self._encode(fmt))
        assert entry["mine"] is True

    def test_an_offered_gif_still_arrives_animated(self, monkeypatch, tmp_path):
        """The point of offering it: a GIF has to reach the disk still moving."""
        monkeypatch.setattr(stickers, "uploads_dir", lambda: tmp_path)
        entry = stickers.save_upload("moving one", self._encode("GIF", animated=True))
        assert entry["moving"] is True
        assert (tmp_path / "moving-one.gif").is_file()

    def test_nothing_is_offered_that_pillow_cannot_read(self):
        """A widened list must not promise a format the round trip cannot make."""
        known = {"image/png", "image/webp", "image/jpeg", "image/gif"}
        assert set(self.offered()) <= known, (
            "the picker offers a type this test does not prove storable")


class TestPickedGifsAreKeptButPruned:
    """Option C: a rolling recent set, not a library and not a bin.

    A picked GIF is something you passed through rather than something you decided
    to have, so it lives in its own folder and that folder is pruned. Uploads are
    never touched by that pruning, which is the whole reason the folders are apart.
    """

    def _gif(self, frames=2) -> bytes:
        pics = [Image.new("RGBA", (48, 48), (255, 0, 0, 255))]
        pics += [Image.new("RGBA", (48, 48), (0, 0, 255, 255))] * (frames - 1)
        buffer = io.BytesIO()
        first, *rest = pics
        if rest:
            first.save(buffer, format="GIF", save_all=True, append_images=rest,
                       duration=100, loop=0)
        else:
            first.save(buffer, format="GIF")
        return buffer.getvalue()

    @pytest.fixture
    def homes(self, tmp_path, monkeypatch):
        gifs, mine, cache = tmp_path / "gifs", tmp_path / "mine", tmp_path / "cache"
        monkeypatch.setattr(stickers, "gifs_dir", lambda: gifs)
        monkeypatch.setattr(stickers, "uploads_dir", lambda: mine)
        monkeypatch.setattr(stickers, "cache_dir", lambda: cache)
        return gifs, mine

    def test_a_picked_gif_is_stored_and_still_moves(self, homes):
        entry = stickers.save_gif("giphy", "abc123", "Thanks GIF", self._gif())
        assert entry["id"] == "gif:giphy-abc123"
        assert entry["moving"] is True
        assert entry["name"] == "Thanks GIF"
        assert stickers.resolve("gif:giphy-abc123") is not None

    def test_a_still_result_is_not_kept_as_a_gif(self, homes):
        """A GIF service will happily return something that does not move."""
        entry = stickers.save_gif("giphy", "still1", "Static", self._gif(frames=1))
        assert entry["moving"] is False
        assert stickers.resolve("gif:giphy-still1").suffix == ".png"

    def test_the_name_carries_the_provider_so_two_services_cannot_collide(self, homes):
        a = stickers.save_gif("giphy", "same", "One", self._gif())
        b = stickers.save_gif("klipy", "same", "Two", self._gif())
        assert a["id"] != b["id"], "the same id on two services overwrote one another"

    def test_the_folder_is_pruned_to_the_newest(self, homes, monkeypatch):
        monkeypatch.setattr(stickers, "GIF_KEEP", 3)
        for n in range(6):
            stickers.save_gif("giphy", f"id{n}", f"G{n}", self._gif())
        left = sorted(p.stem for p in homes[0].glob("*.gif"))
        assert len(left) == 3, f"expected 3 kept, found {left}"
        assert "giphy-id5" in left and "giphy-id0" not in left

    def test_pruning_never_touches_your_uploads(self, homes, monkeypatch):
        monkeypatch.setattr(stickers, "GIF_KEEP", 1)
        homes[1].mkdir(parents=True, exist_ok=True)
        keeper = homes[1] / "my-own-drawing.png"
        Image.new("RGBA", (16, 16)).save(keeper)
        for n in range(4):
            stickers.save_gif("giphy", f"id{n}", "G", self._gif())
        assert keeper.is_file(), "pruning picked GIFs deleted an upload"

    def test_a_picked_gif_can_be_deleted_like_your_own(self, homes):
        entry = stickers.save_gif("giphy", "byebye", "Bye", self._gif())
        assert stickers.delete_upload(entry["id"]) is True
        assert stickers.resolve(entry["id"]) is None

    def test_the_openmoji_library_still_cannot_be_deleted(self, homes):
        with pytest.raises(ValueError, match="only your own"):
            stickers.delete_upload("openmoji:1F64F")

    def test_they_appear_in_the_shelf_between_uploads_and_the_library(self, homes):
        stickers.save_gif("giphy", "flower1", "flower dance", self._gif())
        found = stickers.search("flower")
        ids = [item["id"] for item in found]
        assert "gif:giphy-flower1" in ids, "a picked GIF was not searchable"
        assert found[ids.index("gif:giphy-flower1")]["mine"] is True

    def test_an_oversized_download_is_refused(self, homes):
        with pytest.raises(ValueError, match="under"):
            stickers.save_gif("giphy", "huge", "Huge",
                              b"G" * (stickers.ANIMATED_MAX_BYTES + 1))

    def test_something_that_is_not_an_image_is_refused(self, homes):
        with pytest.raises(ValueError, match="not an image"):
            stickers.save_gif("giphy", "junk", "Junk", b"not a picture at all")
