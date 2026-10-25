"""Shared fixtures, and one guard that applies to every test in the suite.

**The suite used to write into the project's own `logs/`.** Running it appended
thirteen fake run records to `logs/runs.jsonl` and, once Chrome's output began being
captured, four launch headers to `logs/chrome.log`. Nobody noticed because neither
file is in git, but `runs.jsonl` is the thing you read to answer "which extraction
strategy has been working lately", and it was being seeded with runs against
`https://youtu.be/abc` that failed with `ZeroDivisionError`. A log you have to
filter before trusting is a log that will be trusted by accident one day.

Found on 2026-08-22 while auditing, by copying both files, running the suite, and
looking at what changed.
"""

from __future__ import annotations

import pytest

from wastatus import runlog


@pytest.fixture(autouse=True)
def _logs_go_somewhere_disposable(tmp_path, monkeypatch):
    """Point every test's logging at its own temporary directory.

    Autouse and unconditional, because the tests that write to a log are not the
    ones that look like they would: anything that reaches `runlog.Run`, `runlog.setup`
    or `post.launch_browser` writes, and that is most of the suite indirectly.

    `runlog.log_dir` reads this variable at call time, so the override is enough and
    nothing has to be reset afterwards.
    """
    monkeypatch.setenv("WASTATUS_LOG_DIR", str(tmp_path / "logs"))
    # A handler attached by an earlier test would still be pointing at the old
    # file. Tests that want logging call `setup` themselves, and this lets them.
    monkeypatch.setattr(runlog, "_configured", False, raising=False)


# -- what the browser extension uploads ----------------------------------------

CAPTURE_VIDEO_STARTS = 20  # seconds: where the video file's clock begins
CAPTURE_AUDIO_STARTS = 18  # and the audio's, deliberately different
CAPTURE_LENGTH = 10


@pytest.fixture(scope="session")
def captured_media(tmp_path_factory):
    """A VP9 video and an Opus audio stream in WebM, the way the extension uploads
    them: each on YouTube's own clock, so neither starts at zero, and the two start
    at different moments. Both carry a mark on every whole second of that clock, a
    red frame and a 1 kHz beep, so a cut can be measured for sync.

    Skips the test when ffmpeg is missing, because there is nothing to fake here:
    the point is what real ffmpeg does with real streams.
    """
    import shutil
    import subprocess

    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("needs ffmpeg and ffprobe")
    root = tmp_path_factory.mktemp("captured")
    video, audio, both = root / "video.webm", root / "audio.webm", root / "both.webm"

    def make(cmd):
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *cmd],
                       check=True, stdin=subprocess.DEVNULL)

    make([
        "-f", "lavfi", "-i",
        f"color=c=black:s=160x90:r=30:d={CAPTURE_LENGTH},"
        "drawbox=c=red:t=fill:enable='lt(mod(t,1),0.1)'",
        "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8",
        "-g", "30", "-output_ts_offset", str(CAPTURE_VIDEO_STARTS), str(video),
    ])
    make([
        "-f", "lavfi", "-i",
        "aevalsrc='if(lt(mod(t,1),0.1),0.8*sin(2*PI*1000*t),0)'"
        f":s=48000:d={CAPTURE_LENGTH}",
        "-c:a", "libopus", "-output_ts_offset", str(CAPTURE_AUDIO_STARTS), str(audio),
    ])
    make(["-i", str(video), "-i", str(audio), "-c", "copy", str(both)])
    return {"video": video, "audio": audio, "both": both, "root": root}
