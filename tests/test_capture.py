"""A captured window is cut on its own timestamps, and checked before it is cut.

The fixtures imitate what the extension uploads: a VP9 video and an Opus audio
stream in WebM, each on YouTube's own clock, so neither starts at zero and the two
start at different moments. Both carry a mark on every whole second, a red frame and
a 1 kHz beep, which is the same test the spike used against a real video. The cut
is right when, in the result, both marks land on the whole seconds again.
See docs/extension.md and DECISIONS.md D-080.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from wastatus import capture, fetch, pipeline, runlog

VIDEO_STARTS, AUDIO_STARTS, LENGTH = 20, 18, 10  # as conftest.captured_media makes them


@pytest.fixture
def uploads(captured_media):
    return captured_media


def _flash_times(path: Path) -> list[float]:
    """When a red frame starts, in the cut file's own seconds."""
    out = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", str(path), "-map", "0:v:0", "-vf",
         "scale=4:4,showinfo", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    )
    import re
    stamps = [float(x) for x in re.findall(rb"pts_time:([0-9.]+)", out.stderr)]
    pixels = out.stdout
    frame = 4 * 4 * 3
    red = [pixels[i * frame] > 128 and pixels[i * frame + 1] < 64
           for i in range(len(pixels) // frame)]
    return [stamps[i] for i in range(len(red)) if red[i] and (i == 0 or not red[i - 1])]


def _beep_times(path: Path) -> list[float]:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1",
         "-ar", "48000", "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    import array
    samples = array.array("h", raw)
    onsets, quiet = [], True
    for index in range(0, len(samples), 24):  # half a millisecond
        loud = max(abs(v) for v in samples[index:index + 24]) > 8000
        if loud and quiet:
            onsets.append(index / 48000)
        quiet = not loud
    return onsets


class TestProbe:
    def test_a_stream_says_where_it_starts_and_ends_on_its_own_clock(self, uploads):
        video = capture.probe(uploads["video"], "video")
        audio = capture.probe(uploads["audio"], "audio")
        assert video.codec == "vp9" and audio.codec == "opus"
        assert video.start == pytest.approx(VIDEO_STARTS, abs=0.05)
        assert video.end == pytest.approx(VIDEO_STARTS + LENGTH, abs=0.1)
        assert audio.start == pytest.approx(AUDIO_STARTS, abs=0.05)
        assert video.gaps == () and audio.gaps == ()

    def test_a_file_holding_both_kinds_is_not_a_capture(self, uploads):
        with pytest.raises(capture.CaptureError, match="one audio stream"):
            capture.probe(uploads["both"], "audio")

    def test_the_wrong_kind_is_refused(self, uploads):
        with pytest.raises(capture.CaptureError, match="one video stream"):
            capture.probe(uploads["audio"], "video")

    def test_something_that_is_not_media_is_refused(self, uploads):
        junk = uploads["root"] / "junk.webm"
        junk.write_bytes(b"not a media file at all" * 100)
        with pytest.raises(capture.CaptureError):
            capture.probe(junk, "audio")


class TestCoverage:
    def stream(self, start, end, gaps=()):
        return capture.Stream(Path("x"), "audio", "opus", start, end, tuple(gaps))

    def test_a_window_inside_the_stream_is_accepted(self):
        capture.check_covers(self.stream(10, 40), 12, 30)

    def test_a_window_starting_before_the_stream_is_refused_with_the_numbers(self):
        with pytest.raises(capture.CaptureError, match="runs from 20.00s to 40.00s"):
            capture.check_covers(self.stream(20, 40), 12, 30)

    def test_the_end_may_fall_a_little_past_the_last_packet(self):
        """A window to the very end of a video ends where the video does."""
        capture.check_covers(self.stream(10, 263.2), 240, 263.6)

    def test_a_hole_inside_the_window_is_refused(self):
        with pytest.raises(capture.CaptureError, match="missing 15.00s to 17.00s"):
            capture.check_covers(self.stream(10, 40, [(15, 17)]), 12, 30)

    def test_a_hole_outside_the_window_does_not_matter(self):
        capture.check_covers(self.stream(10, 40, [(35, 37)]), 12, 30)


class TestSection:
    def test_both_marks_land_on_the_whole_seconds_after_the_cut(self, uploads, tmp_path):
        """The measurement the module exists for: picture and sound in step."""
        out = capture.section(uploads["audio"], uploads["video"], 22.0, 26.0,
                              tmp_path / "section.mkv")
        flashes = _flash_times(out)
        beeps = _beep_times(out)
        assert len(flashes) == 4 and len(beeps) == 4
        for flash, whole in zip(flashes, range(4)):
            assert flash == pytest.approx(whole, abs=0.034)  # a frame at 30 fps
        for beep, whole in zip(beeps, range(4)):
            assert beep == pytest.approx(whole, abs=0.008)
        length = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout)
        assert length == pytest.approx(4.0, abs=0.05)

    def test_card_mode_cuts_the_sound_alone(self, uploads, tmp_path):
        out = capture.section(uploads["audio"], None, 19.0, 23.0, tmp_path / "a.mkv")
        kinds = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
             "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.split()
        assert kinds == ["audio"]
        assert _beep_times(out)[0] == pytest.approx(0.0, abs=0.008)

    def test_a_window_the_upload_does_not_hold_is_refused_before_ffmpeg_runs(
            self, uploads, tmp_path):
        with pytest.raises(capture.CaptureError, match="the clip needs 5.00s"):
            capture.section(uploads["audio"], None, 5.0, 9.0, tmp_path / "a.mkv")
        assert not (tmp_path / "a.mkv").exists()


class TestTheEngineAsksYouTubeNothing:
    def test_a_captured_card_never_calls_fetch(self, uploads, tmp_path, monkeypatch):
        """The hosted renderer's whole premise: no metadata, media or artwork
        request leaves the server. Every fetch entry point is made to explode."""
        def explode(*_args, **_kwargs):
            raise AssertionError("the engine reached for YouTube")

        for name in ("probe", "download_section", "download_thumbnail"):
            monkeypatch.setattr(fetch, name, explode)

        from PIL import Image
        art = tmp_path / "art.jpg"
        Image.new("RGB", (640, 360), "teal").save(art)
        source = fetch.Source(video_id="abcdefghijk", title="A Song", channel="A Singer",
                              duration=40.0,
                              watch_url="https://www.youtube.com/watch?v=abcdefghijk")
        job = pipeline.Job(
            url=source.watch_url, start=20.0, end=23.0, out=tmp_path / "out",
            captured=pipeline.Captured(source=source, audio=uploads["audio"],
                                       artwork=art),
        )
        run = runlog.Run(runlog.setup(), url=job.url)
        result = pipeline.produce(job, run)
        assert result.clip.is_file()
        assert result.caption == source.watch_url
        assert run.fields["client"] == "browser"

    def test_video_mode_without_the_frames_is_refused(self, uploads, tmp_path):
        source = fetch.Source("abcdefghijk", "A Song", "A Singer", 40.0,
                              "https://www.youtube.com/watch?v=abcdefghijk")
        job = pipeline.Job(url=source.watch_url, start=20.0, end=23.0, video=True,
                           out=tmp_path / "out",
                           captured=pipeline.Captured(source=source,
                                                      audio=uploads["audio"]))
        with pytest.raises(capture.CaptureError, match="needs the captured video"):
            pipeline.produce(job, runlog.Run(runlog.setup(), url=job.url))
