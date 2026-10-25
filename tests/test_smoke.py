"""End to end run. Needs the network, YouTube's cooperation and ffmpeg.

Skipped by default because a failure here usually means YouTube changed something
rather than that the code regressed. Enable deliberately:

    WASTATUS_E2E=1 .venv/bin/python -m pytest tests/test_smoke.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("WASTATUS_E2E") != "1",
    reason="set WASTATUS_E2E=1 to run the end to end test",
)

URL = "https://youtu.be/A6DfGQsdz1Y"  # Tamil title, exercises transliteration
START, END = "1:10", "1:20"
ROOT = Path(__file__).resolve().parent.parent


def ffprobe(path: Path, entries: str) -> str:
    return subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", entries,
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


@pytest.fixture(scope="module")
def produced(tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    logs = tmp_path_factory.mktemp("logs")
    proc = subprocess.run(
        [sys.executable, "-m", "wastatus", URL, START, END, "-o", str(out)],
        capture_output=True, text=True, cwd=ROOT,
        env={**os.environ, "WASTATUS_LOG_DIR": str(logs)},
        timeout=600,
    )
    if proc.returncode != 0:
        pytest.fail(f"wastatus exited {proc.returncode}\n{proc.stdout}\n{proc.stderr}")
    return out, logs, proc


def test_exits_cleanly(produced):
    _, _, proc = produced
    assert proc.returncode == 0


def test_writes_the_clip_and_its_caption(produced):
    out, _, _ = produced
    assert len(list(out.glob("*.mp4"))) == 1
    assert len(list(out.glob("*.caption.txt"))) == 1
    # The text only follow up is opt in now that the caption link is tappable,
    # so a default run must not write a second status file.
    assert list(out.glob("*.status2.txt")) == []


def test_filename_leads_with_the_date_and_reads_as_the_song(produced):
    out, _, _ = produced
    stem = next(out.glob("*.mp4")).stem
    date, slug, window = stem.split("_")
    assert date.isdigit() and len(date) == 8
    assert slug.replace("-", "").isalnum()
    assert window == "70-80"


def test_output_is_a_ten_second_vertical_h264_clip(produced):
    out, _, _ = produced
    clip = next(out.glob("*.mp4"))
    assert ffprobe(clip, "stream=width") .splitlines()[0] == "1080"
    assert ffprobe(clip, "stream=height").splitlines()[0] == "1920"
    assert float(ffprobe(clip, "format=duration")) == pytest.approx(10.0, abs=0.3)
    assert "h264" in ffprobe(clip, "stream=codec_name")
    assert "aac" in ffprobe(clip, "stream=codec_name")


def test_caption_is_ascii_and_carries_the_url(produced):
    out, _, _ = produced
    caption = next(out.glob("*.caption.txt")).read_text()
    assert caption.isascii(), "non Latin text leaked past transliteration"
    assert "youtu.be/A6DfGQsdz1Y" in caption


def test_the_run_was_logged_with_the_winning_strategy(produced):
    _, logs, _ = produced
    records = [json.loads(l) for l in (logs / "runs.jsonl").read_text().splitlines()]
    assert records[-1]["status"] == "ok"
    assert records[-1]["client"]
    assert records[-1]["stages"]["download"] > 0


def test_no_work_directory_is_left_behind(produced):
    assert not list(Path("/tmp").glob("wastatus-*"))

