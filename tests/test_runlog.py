import json
import logging

import pytest

from wastatus import runlog


@pytest.fixture
def logs(tmp_path, monkeypatch):
    monkeypatch.setenv("WASTATUS_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(runlog, "_configured", False)
    logger = logging.getLogger("wastatus-test")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    return tmp_path, logger


def read_records(directory):
    path = directory / runlog.JSON_LOG
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_a_successful_run_is_recorded(logs):
    directory, logger = logs
    run = runlog.Run(logger, url="https://youtu.be/x", mode="card")
    run.set(video_id="x", title="Some Song")
    run.finish("ok", output="out/thing.mp4")

    record = read_records(directory)[0]
    assert record["status"] == "ok"
    assert record["url"] == "https://youtu.be/x"
    assert record["title"] == "Some Song"
    assert record["output"] == "out/thing.mp4"
    assert "started_at" in record and "elapsed" in record


def test_stage_timings_are_captured(logs):
    directory, logger = logs
    run = runlog.Run(logger, url="u")
    with run.stage("download"):
        pass
    with run.stage("render"):
        pass
    run.finish("ok")

    stages = read_records(directory)[0]["stages"]
    assert set(stages) == {"download", "render"}
    assert all(isinstance(v, float) for v in stages.values())


def test_a_stage_that_raises_is_still_timed(logs):
    directory, logger = logs
    run = runlog.Run(logger, url="u")
    with pytest.raises(ValueError):
        with run.stage("download"):
            raise ValueError("boom")
    run.finish("failed", error="ValueError: boom")

    record = read_records(directory)[0]
    assert "download" in record["stages"]
    assert record["status"] == "failed"
    assert record["error"] == "ValueError: boom"


def test_which_extraction_strategy_won_is_recoverable(logs):
    directory, logger = logs
    run = runlog.Run(logger, url="u")
    run.set(client="mweb", format="18", failed_attempts=["web_safari: no formats"])
    run.finish("ok")

    record = read_records(directory)[0]
    assert record["client"] == "mweb"
    assert record["failed_attempts"] == ["web_safari: no formats"]


def test_runs_append_rather_than_overwrite(logs):
    directory, logger = logs
    for i in range(3):
        runlog.Run(logger, url=f"u{i}").finish("ok")
    assert len(read_records(directory)) == 3


def test_setup_creates_the_text_log(logs):
    directory, _ = logs
    logger = runlog.setup(verbose=False)
    logger.info("hello")
    for handler in logger.handlers:
        handler.flush()
    assert (directory / runlog.TEXT_LOG).exists()


class TestTheStartupStamp:
    """One block per session about the machine, because "it broke" is not a report.

    The invariant worth a test is the one that would be a leak: `.env` settings are
    named and never quoted, so a key cannot reach a log file by accident.
    """

    def _stamped(self, tmp_path, monkeypatch) -> str:
        monkeypatch.setenv("WASTATUS_LOG_DIR", str(tmp_path))
        monkeypatch.setattr(runlog, "_configured", False)
        logger = logging.getLogger("wastatus-stamp-test")
        logger.handlers.clear()
        logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler(tmp_path / "out.log", encoding="utf-8")
        logger.addHandler(handler)
        runlog.stamp(logger)
        handler.close()
        return (tmp_path / "out.log").read_text(encoding="utf-8")

    def test_it_names_the_versions_that_would_otherwise_be_unrecoverable(
        self, tmp_path, monkeypatch
    ):
        written = self._stamped(tmp_path, monkeypatch)
        for expected in ("wastatus starting", "yt-dlp", "ffmpeg", "chrome", "ports"):
            assert expected in written

    def test_a_secret_in_env_is_named_and_never_quoted(self, tmp_path, monkeypatch):
        from wastatus import env

        monkeypatch.setattr(env, "TAKEN", ["WASTATUS_GIPHY_KEY"])
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "abcdef-do-not-log-me")
        written = self._stamped(tmp_path, monkeypatch)
        assert "WASTATUS_GIPHY_KEY" in written
        assert "do-not-log-me" not in written

    def test_no_env_file_says_so_rather_than_saying_nothing(self, tmp_path, monkeypatch):
        from wastatus import env

        monkeypatch.setattr(env, "TAKEN", [])
        assert "none from .env" in self._stamped(tmp_path, monkeypatch)


def test_the_suite_never_writes_into_the_projects_own_logs():
    """The guard in `conftest.py`, pinned.

    Without it, running the tests appended fake run records to the real
    `logs/runs.jsonl`, the file you read to answer which extraction strategy has
    been working. Found on 2026-08-22 by copying the file, running the suite, and
    diffing.
    """
    from pathlib import Path

    project_logs = Path(__file__).resolve().parent.parent / "logs"
    assert runlog.log_dir().resolve() != project_logs.resolve()


def _fake_section(url, start, end, work, video=False):
    """The download, without one. `produce` only needs a file that exists."""
    from wastatus import fetch

    media = work / "a.m4a"
    media.write_bytes(b"audio")
    return fetch.Download(path=media, client="t", fmt="18")


def _fake_thumbnail(video_id, dest):
    dest.write_bytes(b"art")
    return dest


def test_a_video_run_records_what_the_frame_was_built_from(tmp_path, monkeypatch):
    """The run record answers "why did that one look like that" on its own. The
    words, the window and the mode were already in it; the background and the
    picture's placement are the two that arrived later and are just as visible."""
    import logging

    from wastatus import compose, fetch, pipeline, render

    monkeypatch.setattr(fetch, "probe", lambda url: fetch.Source(
        video_id="abc", title="A song", channel="A Channel", duration=600.0,
        watch_url="https://youtu.be/abc"))
    monkeypatch.setattr(fetch, "download_section", _fake_section)
    monkeypatch.setattr(render, "source_picture", lambda *a, **k: (None, (1080, 1920)))
    monkeypatch.setattr(render, "render_video_clip",
                        lambda src, over, dur, dest, **kw: dest.write_bytes(b"clip"))

    run = runlog.Run(logging.getLogger("wastatus"), url="x")
    job = pipeline.Job(url="https://youtu.be/abc", start=0.0, end=15.0, video=True,
                       out=tmp_path / "out", frame=None, fill=render.BLACK,
                       framing=render.Framing(0.5, 0.4, 1.2))
    pipeline.produce(job, run)
    assert run.fields["fill"] == "black"
    assert run.fields["framing"] == {"x": 0.5, "y": 0.4, "size": 1.2}


def test_a_card_run_records_no_background_and_no_placement_unless_placed(
        tmp_path, monkeypatch):
    """The background means nothing to a card, which composes its own. A placement
    means something in both modes now, D-062, but only when there is one: a field
    that is null on every ordinary clip is noise."""
    import logging

    from wastatus import compose, fetch, pipeline, render

    monkeypatch.setattr(fetch, "probe", lambda url: fetch.Source(
        video_id="abc", title="A song", channel="A Channel", duration=600.0,
        watch_url="https://youtu.be/abc"))
    monkeypatch.setattr(fetch, "download_section", _fake_section)
    monkeypatch.setattr(fetch, "download_thumbnail", _fake_thumbnail)
    monkeypatch.setattr(compose, "build_card",
                        lambda art, text, dest, decals=(), framing=None:
                        dest.write_bytes(b"c") or dest)
    monkeypatch.setattr(compose, "card_aspect", lambda art: 16 / 9)
    monkeypatch.setattr(render, "render_card_clip",
                        lambda card, media, dur, dest, wave=True, moving=():
                        dest.write_bytes(b"clip"))

    run = runlog.Run(logging.getLogger("wastatus"), url="x")
    pipeline.produce(pipeline.Job(url="https://youtu.be/abc", start=0.0, end=15.0,
                                  out=tmp_path / "out", frame=None), run)
    assert "fill" not in run.fields and "framing" not in run.fields

    placed = runlog.Run(logging.getLogger("wastatus"), url="x")
    pipeline.produce(pipeline.Job(url="https://youtu.be/abc", start=0.0, end=15.0,
                                  out=tmp_path / "out2", frame=None,
                                  framing=render.Framing(0.4, 0.3, 0.5)), placed)
    assert placed.fields["framing"] == {"x": 0.4, "y": 0.3, "size": 0.5}
    assert "fill" not in placed.fields


def test_a_fitted_video_run_says_nothing_about_a_placement(tmp_path, monkeypatch):
    """It used to record `framing: null` for every video clip. Absent is the same
    answer and it is the one the rest of this record gives: fields appear when they
    have something to say."""
    import logging

    from wastatus import fetch, pipeline, render

    monkeypatch.setattr(fetch, "probe", lambda url: fetch.Source(
        video_id="abc", title="A song", channel="A Channel", duration=600.0,
        watch_url="https://youtu.be/abc"))
    monkeypatch.setattr(fetch, "download_section", _fake_section)
    monkeypatch.setattr(render, "source_picture", lambda *a, **k: (None, (1080, 1920)))
    monkeypatch.setattr(render, "render_video_clip",
                        lambda src, over, dur, dest, **kw: dest.write_bytes(b"clip"))

    run = runlog.Run(logging.getLogger("wastatus"), url="x")
    pipeline.produce(pipeline.Job(url="https://youtu.be/abc", start=0.0, end=15.0,
                                  video=True, out=tmp_path / "out", frame=None), run)
    assert run.fields["fill"] == "blur"
    assert "framing" not in run.fields
