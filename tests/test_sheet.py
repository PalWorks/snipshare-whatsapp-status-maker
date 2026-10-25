"""The Google Sheet record, exercised without a sheet.

The rule these protect is the one in AGENTS.md: a logging failure must never break
a run. A sheet that is unreachable, misconfigured or refusing the credential costs
a row, never a Status.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from wastatus import sheet


@pytest.fixture(autouse=True)
def _no_sheet(monkeypatch):
    for name in (sheet.ID_ENV, sheet.KEY_ENV, sheet.TAB_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sheet, "_credentials", None)


def _configure(monkeypatch, tmp_path):
    key = tmp_path / "sa.json"
    key.write_text(json.dumps({"client_email": "writer@x.iam.gserviceaccount.com"}))
    monkeypatch.setenv(sheet.ID_ENV, "SHEET123")
    monkeypatch.setenv(sheet.KEY_ENV, str(key))
    return key


def test_no_sheet_configured_is_silence_not_an_error():
    assert sheet.configured() is False
    assert sheet.record(url="https://youtu.be/x") is False


def test_a_sheet_that_refuses_the_credential_does_not_break_the_run(
        monkeypatch, tmp_path, caplog):
    _configure(monkeypatch, tmp_path)

    def refused(_row):
        raise urllib.error.HTTPError("u", 403, "Forbidden", {}, None)

    monkeypatch.setattr(sheet, "append", refused)
    assert sheet.record(url="https://youtu.be/x") is False
    assert "writer@x.iam.gserviceaccount.com" in caplog.text


def test_a_network_failure_does_not_break_the_run(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(sheet, "append", lambda _row: (_ for _ in ()).throw(
        OSError("network is unreachable")))
    assert sheet.record(url="https://youtu.be/x") is False


def test_a_missing_google_auth_says_what_to_install(monkeypatch, tmp_path, caplog):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setattr(sheet, "append", lambda _row: (_ for _ in ()).throw(
        ImportError("no google.oauth2")))
    assert sheet.record(url="https://youtu.be/x") is False
    assert "google-auth" in caplog.text


def test_the_row_is_the_sheet_s_four_columns(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    written = []
    monkeypatch.setattr(sheet, "append", lambda row: written.append(row) or True)
    assert sheet.record(
        url="https://youtu.be/luwe3NKvxos", title="Alakh Niranjan",
        stem="20260827_alakh_26-116_video-2", seconds=13.0,
        browser="Chrome/152", duration=90.0, size_bytes=9_079_588,
    ) is True
    row = written[0]
    assert len(row) == 4
    assert row[1] == "https://youtu.be/luwe3NKvxos"
    assert row[2] == "Published"
    assert "Alakh Niranjan" in row[3] and "90s" in row[3] and "9.1 MB" in row[3]


def test_only_a_published_status_is_ever_written(monkeypatch, tmp_path):
    """There is no path here that writes a failure. A refusal gets no row."""
    _configure(monkeypatch, tmp_path)
    written = []
    monkeypatch.setattr(sheet, "append", lambda row: written.append(row) or True)
    sheet.record(url="https://youtu.be/x")
    assert {row[2] for row in written} == {"Published"}


def test_the_service_account_address_comes_from_the_key_file(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    assert sheet.account() == "writer@x.iam.gserviceaccount.com"


def test_an_unreadable_key_file_has_no_address(monkeypatch, tmp_path):
    monkeypatch.setenv(sheet.ID_ENV, "SHEET123")
    monkeypatch.setenv(sheet.KEY_ENV, str(tmp_path / "missing.json"))
    assert sheet.account() is None


def test_the_source_column_comes_from_the_clip_s_sidecar(monkeypatch, tmp_path):
    """Both callers read the same file, so one sheet holds one form of the link."""
    _configure(monkeypatch, tmp_path)
    clip = tmp_path / "20260827_alakh_26-116_video-2.mp4"
    clip.write_bytes(b"x" * 9_079_588)
    clip.with_suffix(".json").write_text(json.dumps({
        "url": "https://www.youtube.com/watch?v=luwe3NKvxos",
        "title": "Alakh Niranjan - Kannada Folk Song",
        "start": 26.0, "end": 116.0,
    }))
    written = []
    monkeypatch.setattr(sheet, "append", lambda row: written.append(row) or True)
    assert sheet.record(clip=clip, seconds=13.0, browser="Chrome/152") is True
    stamp, source, status, remarks = written[0]
    assert source == "https://www.youtube.com/watch?v=luwe3NKvxos"
    assert status == "Published"
    assert "Alakh Niranjan" in remarks and "90s" in remarks and "9.1 MB" in remarks


def test_a_clip_with_no_sidecar_still_writes_a_row(monkeypatch, tmp_path):
    """An older clip predates sidecars. A thin row beats no row."""
    _configure(monkeypatch, tmp_path)
    clip = tmp_path / "old_clip.mp4"
    clip.write_bytes(b"x" * 1000)
    written = []
    monkeypatch.setattr(sheet, "append", lambda row: written.append(row) or True)
    assert sheet.record(clip=clip, seconds=4.0) is True
    assert written[0][2] == "Published"


def test_a_follow_up_gets_its_own_row_and_says_which_it_is(monkeypatch, tmp_path):
    """One run can publish two Statuses. Recording only the clip left the sheet
    quietly incomplete, and recording both without saying which is which would
    read as a duplicate. Audit finding, 2026-08-31."""
    _configure(monkeypatch, tmp_path)
    written = []
    monkeypatch.setattr(sheet, "append", lambda row: written.append(row) or True)
    sheet.record(url="https://youtu.be/x", title="A Song", seconds=4.0)
    sheet.record(url="https://youtu.be/x", title="A Song", seconds=2.0,
                 note="follow up text")
    assert written[0][3].startswith("A Song")
    assert written[1][3].startswith("follow up text")
    assert all(row[2] == "Published" for row in written)
