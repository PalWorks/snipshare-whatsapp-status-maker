"""The shared engine's window validation.

Both the command line and the local page go through `resolve_window`, so the two
accept the same timestamp forms and refuse the same windows in the same words. That
is the point of the function, and it is what these tests hold in place.
"""

from __future__ import annotations

import json
import threading

import pytest

from pathlib import Path

from wastatus import compose, fetch, pipeline, proc, render, runlog
from wastatus.timecode import TimecodeError

URL = "https://youtu.be/A6DfGQsdz1Y"


class TestResolveWindow:
    def test_a_start_and_a_length(self):
        assert pipeline.resolve_window(URL, "1:10", None, 15) == (70.0, 85.0)

    def test_an_explicit_end_wins_over_a_length(self):
        assert pipeline.resolve_window(URL, "1:10", "1:38", 15) == (70.0, 98.0)

    def test_no_start_means_the_beginning(self):
        assert pipeline.resolve_window(URL, None, None, 30) == (0.0, 30.0)

    def test_a_t_parameter_in_the_link_is_the_start(self):
        assert pipeline.resolve_window(f"{URL}?t=90s", None, None, 15) == (90.0, 105.0)

    def test_the_default_length_applies_when_none_is_given(self):
        _, end = pipeline.resolve_window(URL, "0:10")
        assert end == 10.0 + pipeline.DEFAULT_DURATION

    def test_the_platform_ceiling_is_enforced(self):
        with pytest.raises(ValueError, match="90s WhatsApp Status limit"):
            pipeline.resolve_window(URL, "0:00", None, 91)

    def test_the_longest_allowed_window_is_allowed(self):
        assert pipeline.resolve_window(URL, "0:00", None, 90) == (0.0, 90.0)

    def test_an_end_before_the_start_is_refused(self):
        with pytest.raises(ValueError, match="end has to come after"):
            pipeline.resolve_window(URL, "1:10", "0:30")

    def test_a_zero_length_window_is_refused(self):
        with pytest.raises(ValueError, match="end has to come after"):
            pipeline.resolve_window(URL, "1:10", "1:10")

    @pytest.mark.parametrize("bad", ["half past two", "1:2:3:4", "abc"])
    def test_junk_timestamps_raise_a_timecode_error(self, bad):
        with pytest.raises(TimecodeError):
            pipeline.resolve_window(URL, bad)


class TestJob:
    def test_duration_and_mode_come_from_the_window(self):
        job = pipeline.Job(url=URL, start=70.0, end=85.0)
        assert job.duration == 15.0
        assert job.mode == "card"
        assert pipeline.Job(url=URL, start=0, end=15, video=True).mode == "video"

    def test_the_stage_names_are_the_ones_progress_reports(self):
        """A progress bar divides by these, so an unknown stage would break it."""
        assert pipeline.STAGES == ("probe", "download", "compose", "render")


class TestTheJobSidecar:
    """`produce` leaves a `.json` beside the clip holding what made it.

    The page reads it back so a clip can be corrected and re-made without retyping
    the link, the window, or the wording.
    """

    def test_the_words_survive_a_round_trip(self):
        """The sidecar holds already-transliterated words, and feeding them back in
        as an explicit title must not transliterate them into something else. If it
        did, re-making a clip would quietly rename the song."""
        from wastatus import translit

        for title in (
            "Nadavindu | Sandeep Narayan, Ragini Shankar & Sounds of Isha",
            "Sinna Sinna Murugaiyaa | Murugan Paadal",
            "Potri Thiruthandagam Thevaram Vol II",
            "Prince Rama Varma - Vara Leela Gana Lola",
            "Kandha Sashti Kavacham",
        ):
            assert translit.to_latin(title) == title

    def test_every_word_on_the_frame_is_written_into_it(self, staged, monkeypatch):
        """A word the sidecar forgets is a word that vanishes when you re-open the
        clip to correct it, which is the same silence as a field that never drew."""
        import logging

        monkeypatch.setattr(
            render, "render_card_clip",
            lambda card, media, duration, dest, wave=True, moving=(): dest.write_bytes(b"clip"),
        )
        out = staged / "out"
        job = pipeline.Job(
            url="https://youtu.be/abc", start=70.0, end=85.0, out=out, frame=None,
            title="A Title", channel="A Channel", footer="a footer",
            eyebrow="a label", topline="a line at the top",
        )
        result = pipeline.produce(job, runlog.Run(logging.getLogger("wastatus"), url="x"))
        written = json.loads(
            (out / f"{result.stem}.json").read_text(encoding="utf-8")
        )
        for field in ("title", "channel", "footer", "eyebrow", "topline"):
            assert field in written, f"the sidecar forgot {field}"
        assert written["footer"] == "a footer"
        assert written["eyebrow"] == "a label"
        assert written["topline"] == "a line at the top"

    def test_where_the_frames_landed_is_recorded_for_the_preview(
        self, staged, monkeypatch
    ):
        """The live word preview draws over a still of the frames and cannot
        measure them. Without this recorded, a top line anchored to the picture
        would be drawn against the wrong edge in the preview."""
        import logging

        monkeypatch.setattr(
            render, "source_picture", lambda *a, **k: (None, (1280, 720))
        )
        monkeypatch.setattr(
            render, "render_video_clip",
            lambda src, over, dur, dest, **kw: dest.write_bytes(b"clip"),
        )
        out = staged / "out"
        job = pipeline.Job(
            url="https://youtu.be/abc", start=70.0, end=85.0, out=out, frame=None,
            video=True, title="A Title", topline="a line at the top",
        )
        result = pipeline.produce(job, runlog.Run(logging.getLogger("wastatus"), url="x"))
        written = json.loads(
            (out / f"{result.stem}.json").read_text(encoding="utf-8")
        )
        assert written["picture_top"] == render.picture_rect(
            (1280, 720),
            ceiling=compose.video_picture_top(
                compose.CardText(title="A Title", channel="A Channel",
                                 topline="a line at the top")
            ),
            floor=compose.video_picture_bottom(
                compose.CardText(title="A Title", channel="A Channel",
                                 topline="a line at the top")
            ),
        ).top

    def test_a_video_clip_records_the_whole_rectangle_and_its_background(
        self, staged, monkeypatch
    ):
        """`picture_top` anchors the words. The rest of the rectangle is what lets
        the page rebuild the frame on a different background, and `fill` is what
        says which background that would be a change from."""
        import logging

        monkeypatch.setattr(
            render, "source_picture", lambda *a, **k: (None, (1080, 1920))
        )
        monkeypatch.setattr(
            render, "render_video_clip",
            lambda src, over, dur, dest, **kw: dest.write_bytes(b"clip"),
        )
        out = staged / "out"
        job = pipeline.Job(url="https://youtu.be/abc", start=70.0, end=85.0, out=out,
                           frame=None, video=True, title="A Title",
                           fill=render.BLACK)
        result = pipeline.produce(job, runlog.Run(logging.getLogger("wastatus"), url="x"))
        written = json.loads((out / f"{result.stem}.json").read_text(encoding="utf-8"))
        assert written["fill"] == "black"
        assert set(written["picture"]) == {"left", "top", "width", "height"}
        assert written["picture"]["top"] == written["picture_top"]

    def test_a_card_clip_records_no_picture_top(self, staged, monkeypatch):
        """There are no frames in card mode, so there is nothing to anchor to."""
        import logging

        monkeypatch.setattr(
            render, "render_card_clip",
            lambda card, media, duration, dest, wave=True, moving=(): dest.write_bytes(b"clip"),
        )
        out = staged / "out"
        job = pipeline.Job(url="https://youtu.be/abc", start=70.0, end=85.0,
                           out=out, frame=None)
        result = pipeline.produce(job, runlog.Run(logging.getLogger("wastatus"), url="x"))
        written = json.loads((out / f"{result.stem}.json").read_text(encoding="utf-8"))
        assert written["picture_top"] is None

    def test_a_card_clip_records_the_panel_it_drew(self, staged, monkeypatch):
        """The page cannot draw a box around something whose shape it has no way to
        measure, and the artwork's shape is known only while the clip is being made.
        Video mode has recorded its own rectangle since D-061; this is card mode's,
        and without it the Placed control has nothing to switch to. D-062."""
        import logging

        monkeypatch.setattr(
            render, "render_card_clip",
            lambda card, media, duration, dest, wave=True, moving=(): dest.write_bytes(b"clip"),
        )
        out = staged / "out"
        job = pipeline.Job(url="https://youtu.be/abc", start=70.0, end=85.0,
                           out=out, frame=None,
                           framing=render.Framing(0.4, 0.3, 0.5))
        result = pipeline.produce(job, runlog.Run(logging.getLogger("wastatus"), url="x"))
        written = json.loads((out / f"{result.stem}.json").read_text(encoding="utf-8"))
        assert written["framing"] == {"x": 0.4, "y": 0.3, "size": 0.5}
        panel = written["picture"]
        assert panel["width"] == round(0.5 * compose.WIDTH)
        # Centred where it was asked to be, in whole pixels.
        assert abs(panel["left"] + panel["width"] / 2 - 0.4 * compose.WIDTH) <= 1
        assert abs(panel["top"] + panel["height"] / 2 - 0.3 * compose.HEIGHT) <= 1

    def test_a_fitted_card_records_the_panel_and_no_placement(self, staged,
                                                              monkeypatch):
        """A clip nobody placed still has to be placeable next time round."""
        import logging

        monkeypatch.setattr(
            render, "render_card_clip",
            lambda card, media, duration, dest, wave=True, moving=(): dest.write_bytes(b"clip"),
        )
        out = staged / "out"
        job = pipeline.Job(url="https://youtu.be/abc", start=70.0, end=85.0,
                           out=out, frame=None)
        result = pipeline.produce(job, runlog.Run(logging.getLogger("wastatus"), url="x"))
        written = json.loads((out / f"{result.stem}.json").read_text(encoding="utf-8"))
        assert written["framing"] is None
        left, top, right, bottom = compose.card_rect(16 / 9)
        assert written["picture"] == {
            "left": left, "top": top,
            "width": right - left, "height": bottom - top,
        }

    def test_a_placed_line_of_free_text_is_written_into_it(self, staged, monkeypatch):
        """Free text is dragged, not laid out, so the sidecar is the only record of
        where it went. Without it, re-opening the clip to fix a word loses the line."""
        import logging

        from wastatus import freetext

        monkeypatch.setattr(
            render, "render_card_clip",
            lambda card, media, duration, dest, wave=True, moving=(): dest.write_bytes(b"clip"),
        )
        out = staged / "out"
        line = freetext.FreeText(text="WATCH TILL THE END", x=0.4, y=0.8, size=0.55)
        job = pipeline.Job(
            url="https://youtu.be/abc", start=70.0, end=85.0, out=out, frame=None,
            title="A Title", decals=[line],
        )
        result = pipeline.produce(job, runlog.Run(logging.getLogger("wastatus"), url="x"))
        written = json.loads((out / f"{result.stem}.json").read_text(encoding="utf-8"))
        assert written["stickers"] == [line.as_json()]
        # And it comes back through the same parser the page's request goes through.
        from wastatus import stickers as sticker_module

        assert sticker_module.parse_all(written["stickers"]) == [line]

    def test_it_is_pruned_with_its_clip(self):
        """A sidecar left behind after its clip is deleted is an orphan the page
        would happily read."""
        from wastatus import retention

        assert ".json" in retention.SIDECAR_SUFFIXES


class TestAWindowPastTheEndOfTheVideo:
    """It used to be refused. The video's length is the correction, so it is made.

    The number in the box was a guess at how long the video is, and the tool knows
    the answer the moment it probes. Refusing meant handing that answer back as an
    error and asking for it to be typed in, twice over for a 35 second video with a
    36 second window. See the markup on Screenshot_2026-08-26_10-44-28.
    """

    def _run(self):
        import logging

        return runlog.Run(logging.getLogger("wastatus"), url="x")

    def _short(self, monkeypatch, seconds=35.0):
        monkeypatch.setattr(fetch, "probe", lambda url: fetch.Source(
            video_id="abc", title="Thiruppavai", channel="A Channel",
            duration=seconds, watch_url="https://youtu.be/abc",
        ))

    def test_the_clip_ends_where_the_video_does(self, staged, monkeypatch):
        monkeypatch.setattr(
            render, "render_card_clip",
            lambda card, media, duration, dest, wave=True, moving=(): dest.write_bytes(b"clip"),
        )
        self._short(monkeypatch)
        out = staged / "out"
        job = pipeline.Job(url="https://youtu.be/abc", start=0.0, end=36.0,
                           out=out, frame=None)
        result = pipeline.produce(job, self._run())
        assert job.end == 35.0, "the window was not brought back to the video's end"
        assert result.duration == 35.0

    def test_the_corrected_window_is_what_the_sidecar_holds(self, staged, monkeypatch):
        """The page fills its boxes from the sidecar, so this is what corrects them."""
        monkeypatch.setattr(
            render, "render_card_clip",
            lambda card, media, duration, dest, wave=True, moving=(): dest.write_bytes(b"clip"),
        )
        self._short(monkeypatch)
        out = staged / "out"
        job = pipeline.Job(url="https://youtu.be/abc", start=10.0, end=90.0,
                           out=out, frame=None)
        result = pipeline.produce(job, self._run())
        written = json.loads((out / f"{result.stem}.json").read_text(encoding="utf-8"))
        assert (written["start"], written["end"]) == (10.0, 35.0)

    def test_only_the_length_asked_for_is_given_up(self, staged, monkeypatch):
        """A window that fits is not touched."""
        monkeypatch.setattr(
            render, "render_card_clip",
            lambda card, media, duration, dest, wave=True, moving=(): dest.write_bytes(b"clip"),
        )
        self._short(monkeypatch)
        out = staged / "out"
        job = pipeline.Job(url="https://youtu.be/abc", start=0.0, end=30.0,
                           out=out, frame=None)
        pipeline.produce(job, self._run())
        assert job.end == 30.0

    def test_a_start_past_the_end_is_still_refused(self, staged, monkeypatch):
        """There is nothing to correct it to: the window holds no video at all."""
        self._short(monkeypatch)
        job = pipeline.Job(url="https://youtu.be/abc", start=40.0, end=55.0,
                           out=staged / "out", frame=None)
        with pytest.raises(ValueError, match="would be empty"):
            pipeline.produce(job, self._run())


@pytest.fixture
def staged(tmp_path, monkeypatch):
    """Everything up to the encode faked out, so only the last step decides."""
    monkeypatch.setattr(fetch, "probe", lambda url: fetch.Source(
        video_id="abc", title="Thiruppavai", channel="A Channel",
        duration=600.0, watch_url="https://youtu.be/abc",
    ))

    def section(url, start, end, work, video=False):
        media = work / "audio.m4a"
        media.write_bytes(b"audio")
        return fetch.Download(path=media, client="mweb", fmt="18")

    monkeypatch.setattr(fetch, "download_section", section)

    def artwork(video_id, dest):
        dest.write_bytes(b"art")
        return dest

    monkeypatch.setattr(fetch, "download_thumbnail", artwork)
    monkeypatch.setattr(
        pipeline.compose, "build_card",
        lambda art, text, dest, decals=(), framing=None: (
            dest.write_bytes(b"card") or dest),
    )
    # The panel's shape, which the real one reads off the artwork. `b"art"` is not
    # a picture, so it is answered here rather than opened.
    monkeypatch.setattr(pipeline.compose, "card_aspect", lambda art: 16 / 9)
    return tmp_path


class TestNothingHalfWrittenIsLeftBehind:
    """ffmpeg used to write straight into the output folder, so a clip that was
    still being encoded was listed by the page as a real one: playable, postable,
    and deletable mid-write. A render that failed left it there for good.

    Both the Stop button and the Delete button make that reachable, so the invariant
    is now that nothing incomplete is ever in the folder the page reads."""

    def _job(self, out):
        return pipeline.Job(
            url="https://youtu.be/abc", start=70.0, end=85.0, out=out, frame=None,
        )

    def _run(self):
        import logging

        return runlog.Run(logging.getLogger("wastatus"), url="x")

    def test_the_encoder_is_never_pointed_at_the_output_folder(self, staged, monkeypatch):
        """This is the invariant. Everything else in this class follows from it."""
        seen: dict = {}

        def note(card, media, duration, dest, wave=True, moving=()):
            seen["dest"] = Path(dest)
            dest.write_bytes(b"a clip")

        monkeypatch.setattr(render, "render_card_clip", note)
        out = staged / "out"
        pipeline.produce(self._job(out), self._run())
        assert out not in seen["dest"].parents, (
            f"ffmpeg was told to write inside the output folder: {seen['dest']}"
        )

    def test_a_stopped_render_leaves_no_clip(self, staged, monkeypatch):
        def killed(card, media, duration, dest, wave=True, moving=()):
            dest.write_bytes(b"half an mp4")     # what ffmpeg had got to
            raise proc.Cancelled("stopped")

        monkeypatch.setattr(render, "render_card_clip", killed)
        out = staged / "out"
        with pytest.raises(proc.Cancelled):
            pipeline.produce(self._job(out), self._run())
        assert list(out.glob("*.mp4")) == []

    def test_a_failed_render_leaves_no_clip_either(self, staged, monkeypatch):
        def broke(card, media, duration, dest, wave=True, moving=()):
            dest.write_bytes(b"half an mp4")
            raise render.RenderError("ffmpeg failed")

        monkeypatch.setattr(render, "render_card_clip", broke)
        out = staged / "out"
        with pytest.raises(render.RenderError):
            pipeline.produce(self._job(out), self._run())
        assert list(out.glob("*.mp4")) == []

    def test_no_part_file_is_left_in_the_output_folder(self, staged, monkeypatch):
        """The clip lands under a name the page cannot see, then is renamed. That
        name must not survive a failure either."""
        def broke(card, media, duration, dest, wave=True, moving=()):
            raise render.RenderError("ffmpeg failed")

        monkeypatch.setattr(render, "render_card_clip", broke)
        out = staged / "out"
        with pytest.raises(render.RenderError):
            pipeline.produce(self._job(out), self._run())
        assert list(out.glob("*.part")) == []

    def test_a_render_that_works_keeps_its_clip(self, staged, monkeypatch):
        monkeypatch.setattr(
            render, "render_card_clip",
            lambda card, media, duration, dest, wave=True, moving=(): dest.write_bytes(b"a clip"),
        )
        out = staged / "out"
        result = pipeline.produce(self._job(out), self._run())
        assert result.clip.is_file()
        assert result.clip.parent == out
        assert result.clip.read_bytes() == b"a clip"
        assert list(out.glob("*.part")) == []


class TestTheCardText:
    """T-008. What goes on the card when the title cleans away to nothing."""

    def _source(self, title, channel="Prince Rama Varma", artist=""):
        return fetch.Source(
            video_id="A6DfGQsdz1Y", title=title, channel=channel,
            duration=300.0, watch_url=URL, artist=artist,
        )

    def _job(self, **kw):
        return pipeline.Job(url=URL, start=0.0, end=15.0, **kw)

    def test_an_ordinary_title_is_cleaned_and_kept(self):
        title, channel = pipeline.title_and_channel(
            self._job(), self._source("Song Name (Official Video)")
        )
        assert (title, channel) == ("Song Name", "Prince Rama Varma")

    def test_a_title_that_is_all_noise_keeps_the_raw_title(self):
        title, _ = pipeline.title_and_channel(self._job(), self._source("(Official Video)"))
        assert title == "(Official Video)"

    def test_a_title_that_romanises_to_nothing_falls_back_to_the_channel(self):
        title, channel = pipeline.title_and_channel(
            self._job(), self._source("\N{CLAPPER BOARD}")
        )
        assert title == channel == "Prince Rama Varma"

    def test_the_artist_still_wins_over_the_channel(self):
        _, channel = pipeline.title_and_channel(
            self._job(),
            self._source("Song", channel="Some Label - Topic", artist="Real Artist"),
        )
        assert channel == "Real Artist"

    def test_an_override_still_wins_over_everything(self):
        title, channel = pipeline.title_and_channel(
            self._job(title="Mine", channel="Ours"), self._source("(Official Video)")
        )
        assert (title, channel) == ("Mine", "Ours")


class TestTwoRendersAtOnce:
    """T-017's acceptance: two identical requests started together produce two
    clips, not one clip carrying the other's bytes."""

    def _job(self, out):
        return pipeline.Job(
            url="https://youtu.be/abc", start=70.0, end=85.0, out=out, frame=None,
        )

    def _run(self):
        import logging

        return runlog.Run(logging.getLogger("wastatus"), url="x")

    def test_the_same_song_and_window_twice_over_lands_twice(self, staged, monkeypatch):
        """The encode is held open until both renders have claimed a name, which is
        the window the old check-then-act lost a clip in."""
        from concurrent.futures import ThreadPoolExecutor

        both_claimed = threading.Barrier(2)

        def slow_render(card, media, duration, dest, wave=True, moving=()):
            both_claimed.wait(timeout=10)
            dest.write_bytes(b"a clip from " + str(dest).encode())

        monkeypatch.setattr(render, "render_card_clip", slow_render)
        out = staged / "out"

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(pipeline.produce, self._job(out), self._run())
                for _ in range(2)
            ]
            results = [future.result() for future in futures]

        clips = sorted(path.name for path in out.glob("*.mp4"))
        assert len(clips) == 2, f"one render overwrote the other: {clips}"
        assert len({result.stem for result in results}) == 2
        assert all(clip.stat().st_size > 0 for clip in out.glob("*.mp4"))

    def test_no_claim_is_left_behind_afterwards(self, staged, monkeypatch):
        monkeypatch.setattr(
            render, "render_card_clip",
            lambda card, media, duration, dest, wave=True, moving=(): dest.write_bytes(b"clip"),
        )
        out = staged / "out"
        pipeline.produce(self._job(out), self._run())
        assert list(out.glob("*.part")) == []


class TestAClipTooBigToSend:
    """T-014. WhatsApp refuses an oversize file by taking it and never opening its
    editor, so the tool has to be the one that says something."""

    def _job(self, out):
        return pipeline.Job(
            url="https://youtu.be/abc", start=70.0, end=85.0, out=out, frame=None,
        )

    def _run(self):
        import logging

        return runlog.Run(logging.getLogger("wastatus"), url="x")

    def test_a_clip_over_the_ceiling_is_called_out(self, staged, monkeypatch, caplog):
        monkeypatch.setattr(render, "PLATFORM_MAX_BYTES", 4)  # smaller than the stub
        monkeypatch.setattr(
            render, "render_card_clip",
            lambda card, media, duration, dest, wave=True, moving=(): dest.write_bytes(b"a clip"),
        )
        with caplog.at_level("WARNING"):
            pipeline.produce(self._job(staged / "out"), self._run())
        assert "WhatsApp refuses anything over" in caplog.text

    def test_an_ordinary_clip_says_nothing(self, staged, monkeypatch, caplog):
        monkeypatch.setattr(
            render, "render_card_clip",
            lambda card, media, duration, dest, wave=True, moving=(): dest.write_bytes(b"a clip"),
        )
        with caplog.at_level("WARNING"):
            pipeline.produce(self._job(staged / "out"), self._run())
        assert "WhatsApp refuses" not in caplog.text


class TestThePreviewBaseIsKept:
    """What the live word preview draws over, T-036.

    Two modes need two different things, and neither is the finished clip: the clip
    has the words burned into it, so drawing new ones over it would show both.
    """

    def test_the_two_names_are_pruned_with_their_clip(self, tmp_path):
        """Or the folder fills with backgrounds for clips that no longer exist."""
        from wastatus import retention

        assert ".art.jpg" in retention.SIDECAR_SUFFIXES
        assert ".base.png" in retention.SIDECAR_SUFFIXES

        for name in ("clip.mp4", "clip.art.jpg", "clip.base.png", "clip.caption.txt"):
            (tmp_path / name).write_bytes(b"x")
        found = {path.name for path in retention.group_files(tmp_path, "clip")}
        assert {"clip.art.jpg", "clip.base.png"} <= found

    def test_a_still_frame_sidecar_is_not_confused_with_a_preview_base(self, tmp_path):
        """`<stem>.png` is the --frame still and `<stem>.base.png` is the preview
        background. Both end in .png and they are different files."""
        from wastatus import retention

        for name in ("clip.mp4", "clip.png", "clip.base.png"):
            (tmp_path / name).write_bytes(b"x")
        found = {path.name for path in retention.group_files(tmp_path, "clip")}
        assert "clip.png" in found and "clip.base.png" in found


class TestThePicturesPlacement:
    """D-061. A placement replaces the fitting, and nothing else about the render
    changes: a clip that asks for none is the clip that was always made."""

    def _run(self):
        import logging

        return runlog.Run(logging.getLogger("wastatus"), url="x")

    def _rect_from(self, monkeypatch, out, framing):
        seen: dict = {}
        monkeypatch.setattr(
            render, "source_picture", lambda *a, **k: (None, (1280, 720))
        )

        def note(src, over, dur, dest, **kw):
            seen["rect"] = kw.get("rect")
            dest.write_bytes(b"clip")

        monkeypatch.setattr(render, "render_video_clip", note)
        job = pipeline.Job(url="https://youtu.be/abc", start=70.0, end=85.0, out=out,
                           frame=None, video=True, title="A Title", framing=framing)
        result = pipeline.produce(job, self._run())
        return seen["rect"], json.loads(
            (out / f"{result.stem}.json").read_text(encoding="utf-8"))

    def test_no_placement_fits_the_picture_as_it_always_did(self, staged, monkeypatch):
        rect, written = self._rect_from(monkeypatch, staged / "out", None)
        assert rect == render.picture_rect(
            (1280, 720),
            ceiling=compose.video_picture_top(compose.CardText(title="A Title",
                                                              channel="A Channel")),
            floor=compose.video_picture_bottom(compose.CardText(title="A Title",
                                                               channel="A Channel")),
        )
        assert written["framing"] is None

    def test_a_placement_is_what_the_renderer_is_given(self, staged, monkeypatch):
        framing = render.Framing(x=0.4, y=0.3, size=1.4)
        rect, written = self._rect_from(monkeypatch, staged / "out", framing)
        assert rect == render.placed_rect((1280, 720), framing)
        assert written["framing"] == framing.as_json()
        # and the rectangle it resolved to, which is what the preview measures from
        assert written["picture"] == {"left": rect.left, "top": rect.top,
                                      "width": rect.width, "height": rect.height}

    def test_it_survives_the_round_trip_through_the_sidecar(self, staged, monkeypatch):
        framing = render.Framing(x=0.25, y=0.75, size=0.8)
        _, written = self._rect_from(monkeypatch, staged / "out", framing)
        assert render.parse_framing(written["framing"]) == framing
