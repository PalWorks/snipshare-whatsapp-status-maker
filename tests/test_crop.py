"""Choosing a crop for a letterboxed source video.

Video mode blur-fills the frames to 9:16. If the source carries its own black
bars, they land inside that fill as hard seams, which is what the first `--video`
post looked like. The crop is decided from several sampled frames because a single
frame can be misleading.
"""

from __future__ import annotations

from pathlib import Path

from wastatus import render

SIZE = (1280, 720)
LETTERBOXED = (0, 85, 1280, 635)      # 2.35:1 picture inside 16:9
FULL = (0, 0, 1280, 720)              # a dark frame the detector refused to trim


def test_consistent_bars_are_cropped():
    # 85 rounds inward to 86, never outward to 84: a crop must not be able to
    # include a row of the bar it was meant to remove.
    assert render.crop_expression([LETTERBOXED] * 3, SIZE) == "crop=1280:548:0:86"


def test_one_flat_frame_makes_the_crop_more_conservative_not_less():
    """A dark frame reports no bars, so nothing is cropped. Never the reverse."""
    assert render.crop_expression([LETTERBOXED, FULL, LETTERBOXED], SIZE) is None


def test_the_smallest_bar_wins():
    boxes = [(0, 85, 1280, 635), (0, 60, 1280, 660), (0, 90, 1280, 630)]
    assert render.crop_expression(boxes, SIZE) == "crop=1280:600:0:60"


def test_dimensions_and_offsets_are_even():
    """yuv420p cannot encode an odd width, height, or offset."""
    crop = render.crop_expression([(3, 87, 1277, 633)], SIZE)
    assert crop is not None
    numbers = [int(n) for n in crop.removeprefix("crop=").split(":")]
    assert all(n % 2 == 0 for n in numbers), crop


def test_a_full_frame_source_is_not_cropped():
    assert render.crop_expression([FULL], SIZE) is None


def test_a_one_pixel_difference_is_not_worth_a_filter():
    assert render.crop_expression([(0, 1, 1280, 719)], SIZE) is None


def test_pillarboxed_sources_are_cropped_too():
    crop = render.crop_expression([(280, 0, 1000, 720)], SIZE)
    assert crop == "crop=720:720:280:0"


def test_no_samples_means_no_crop():
    assert render.crop_expression([], SIZE) is None


def test_a_degenerate_box_is_ignored():
    assert render.crop_expression([(0, 355, 1280, 365)], SIZE) is None


class TestTheTextlessBackgroundStill:
    """`background_still`, which the live word preview draws over. T-036."""

    def test_it_uses_the_same_filters_as_the_clip_minus_the_overlay(self, monkeypatch):
        """If these drift, the preview puts the words somewhere the clip does not."""
        from wastatus import render

        seen: list[list[str]] = []
        monkeypatch.setattr(render, "_run", lambda cmd, **kw: seen.append(cmd))
        render.background_still(
            Path("in.mp4"), Path("out.png"), crop="crop=10:20:0:0",
            rect=render.picture_rect((1280, 720)),
        )
        graph = seen[0][seen[0].index("-filter_complex") + 1]
        assert "crop=10:20:0:0" in graph
        assert "gblur=sigma=28" in graph          # the same blur the clip uses
        assert "eq=brightness=-0.20" in graph     # and the same darkening
        assert "[1:v]" not in graph, "the overlay is the one thing left out"
        assert "-frames:v" in seen[0]

    def test_no_crop_is_simply_left_out(self, monkeypatch):
        from wastatus import render

        seen: list[list[str]] = []
        monkeypatch.setattr(render, "_run", lambda cmd, **kw: seen.append(cmd))
        render.background_still(
            Path("in.mp4"), Path("out.png"), crop=None,
            rect=render.picture_rect((1280, 720)),
        )
        graph = seen[0][seen[0].index("-filter_complex") + 1]
        assert graph.startswith("[0:v]split=2")

    def test_a_failed_still_never_takes_the_clip_with_it(self, monkeypatch, tmp_path):
        """The clip is the thing that matters. This is a convenience."""
        from wastatus import render

        calls = {"n": 0}

        def run(cmd, **kw):
            calls["n"] += 1
            if calls["n"] > 1:            # the clip first, the still second
                raise RuntimeError("ffmpeg said no")

        monkeypatch.setattr(render, "_run", run)
        monkeypatch.setattr(
            render, "source_picture", lambda *a, **k: (None, (1280, 720))
        )
        dest = tmp_path / "clip.mp4"
        render.render_video_clip(
            tmp_path / "in.mp4", tmp_path / "over.png", 8.0, dest,
            work=tmp_path, base=tmp_path / "base.png",
        )
        assert calls["n"] == 2, "it tried, and did not raise"
