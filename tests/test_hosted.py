"""The hosted renderer, driven over real HTTP the way the extension drives it.

What these hold in place, in the order a slow connection would test them: a chunk
can be sent twice, sent late, or sent after the server has lost track of the
client, and the upload still ends up whole and in order. A job is made only from
finished uploads that belong to the same token. Nobody else's anything is visible.
A finished clip comes back in ranges. And nothing is kept for longer than it takes
to collect it. See docs/extension.md and DECISIONS.md D-081 and D-082.
"""

from __future__ import annotations

import http.client
import json
import os
import stat
import threading
import time
from pathlib import Path

import pytest

from wastatus import hosted, pipeline, proc


@pytest.fixture
def renderer(tmp_path, monkeypatch):
    # Disk space is the host's business, not the test's.
    monkeypatch.setattr(hosted, "FREE_DISK_MIN", 0)
    made = hosted.Renderer(tmp_path / "data")
    made.start()
    yield made
    made.stop()


@pytest.fixture
def server(renderer):
    srv = hosted.make_server(renderer, 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def token(renderer):
    return renderer.tokens.add("alice")


@pytest.fixture
def other(renderer):
    return renderer.tokens.add("bob")


def call(server, method, path, body=None, token=None, headers=None, raw=False):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=30)
    head = dict(headers or {})
    if token:
        head["Authorization"] = f"Bearer {token}"
    payload = None
    if body is not None:
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        head["Content-Length"] = str(len(payload))
    conn.request(method, hosted.API + path, body=payload, headers=head)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    if raw:
        return response, data
    return response.status, (json.loads(data) if data else None), response


def upload(server, token, kind, data, chunk=100_000):
    status, made, _ = call(server, "POST", "/uploads",
                           {"kind": kind, "size": len(data)}, token)
    assert status == 201, made
    for first in range(0, len(data), chunk):
        last = min(first + chunk, len(data)) - 1
        status, body, _ = call(server, "PUT", f"/uploads/{made['id']}",
                               data[first:last + 1], token,
                               {"Content-Range": f"bytes {first}-{last}/{len(data)}"})
        assert status == 200, body
    return made["id"]


def wait_for(server, token, job_id, states=("done", "failed", "cancelled"), limit=120):
    deadline = time.time() + limit
    while time.time() < deadline:
        status, job, _ = call(server, "GET", f"/jobs/{job_id}", token=token)
        if status != 200 or job["state"] in states:
            return status, job
        time.sleep(0.2)
    raise AssertionError("job never finished")


def artwork_bytes() -> bytes:
    import io

    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (480, 360), "teal").save(buffer, "JPEG")
    return buffer.getvalue()


def card_job(server, token, captured_media, **overrides):
    """Upload what a card needs, the way the extension does, and ask for it."""
    audio = upload(server, token, "audio", captured_media["audio"].read_bytes())
    art = upload(server, token, "artwork", artwork_bytes())
    return call(server, "POST", "/jobs", job_body(audio=audio, artwork=art, **overrides),
                token)


def job_body(**overrides):
    body = {"video_id": "abcdefghijk", "title": "A Song", "channel": "A Singer",
            "duration": 40.0, "start": 20.0, "end": 23.0, "mode": "card"}
    body.update(overrides)
    return body


class TestTokens:
    def test_only_the_hash_is_stored_and_the_file_is_private(self, renderer, token):
        text = (renderer.root / "tokens.json").read_text()
        assert token not in text and hosted.hash_token(token) in text
        mode = stat.S_IMODE(os.stat(renderer.root / "tokens.json").st_mode)
        assert mode == 0o600

    def test_a_revoked_token_stops_working_without_a_restart(self, server, renderer,
                                                              token):
        assert call(server, "GET", "/me", token=token)[0] == 200
        assert renderer.tokens.revoke("alice")
        assert call(server, "GET", "/me", token=token)[0] == 401

    def test_two_tokens_cannot_share_a_name(self, renderer, token):
        with pytest.raises(ValueError, match="already a token called alice"):
            renderer.tokens.add("alice")

    def test_a_broken_token_file_locks_everybody_out(self, server, renderer, token):
        (renderer.root / "tokens.json").write_text("{not json")
        assert call(server, "GET", "/me", token=token)[0] == 401


class TestTheDoor:
    def test_health_needs_no_token(self, server):
        status, body, _ = call(server, "GET", "/health")
        assert status == 200 and body["ok"] is True

    def test_everything_else_does(self, server):
        assert call(server, "GET", "/me")[0] == 401
        assert call(server, "GET", "/me", token="made-up")[0] == 401

    def test_no_response_carries_cors_headers(self, server, token):
        """A web page holding a token still cannot read an answer. D-081."""
        _, _, response = call(server, "GET", "/me", token=token)
        assert response.getheader("Access-Control-Allow-Origin") is None
        response, _ = call(server, "OPTIONS", "/me", raw=True)
        assert response.status == 501

    def test_a_body_refused_unread_ends_the_connection(self, server, token):
        """Otherwise the unread chunk is parsed as the next request on the same
        connection. Found by the suite: a PUT to somebody else's upload."""
        response, _ = call(server, "PUT", "/uploads/" + "x" * 24, b"a" * 5000,
                           "wrong-token", {"Content-Range": "bytes 0-4999/5000"},
                           raw=True)
        assert response.status == 401
        assert response.getheader("Connection") == "close"

    def test_paths_outside_the_api_are_not_found(self, server, token):
        assert call(server, "GET", "/../../etc/passwd", token=token)[0] == 404
        assert call(server, "GET", "/jobs/..%2f..", token=token)[0] == 404


class TestUploadsOnABadConnection:
    def make(self, server, token, size=300):
        status, made, _ = call(server, "POST", "/uploads",
                               {"kind": "audio", "size": size}, token)
        assert status == 201
        return made["id"]

    def put(self, server, token, ident, data, first, total):
        last = first + len(data) - 1
        return call(server, "PUT", f"/uploads/{ident}", data, token,
                    {"Content-Range": f"bytes {first}-{last}/{total}"})

    def test_a_chunk_sent_twice_is_acknowledged_and_not_written_twice(
            self, server, token, renderer):
        ident = self.make(server, token)
        data = bytes(range(256)) + bytes(44)
        assert self.put(server, token, ident, data[:100], 0, 300)[1]["received"] == 100
        assert self.put(server, token, ident, data[:100], 0, 300)[1]["received"] == 100
        assert self.put(server, token, ident, data[100:], 100, 300)[1]["received"] == 300
        assert renderer.uploads[ident].path.read_bytes() == data

    def test_a_chunk_past_what_arrived_says_where_to_resume(self, server, token):
        ident = self.make(server, token)
        self.put(server, token, ident, b"a" * 100, 0, 300)
        status, body, _ = self.put(server, token, ident, b"c" * 100, 200, 300)
        assert status == 409 and body["received"] == 100

    def test_an_overlapping_chunk_keeps_only_the_new_tail(self, server, token, renderer):
        ident = self.make(server, token)
        self.put(server, token, ident, b"a" * 150, 0, 300)
        status, body, _ = self.put(server, token, ident, b"a" * 50 + b"b" * 150, 100, 300)
        assert status == 200 and body["received"] == 300
        assert renderer.uploads[ident].path.read_bytes() == b"a" * 150 + b"b" * 150

    def test_the_client_can_ask_how_much_arrived(self, server, token):
        ident = self.make(server, token)
        self.put(server, token, ident, b"a" * 120, 0, 300)
        status, body, _ = call(server, "GET", f"/uploads/{ident}", token=token)
        assert status == 200 and body["received"] == 120 and body["size"] == 300

    def test_a_chunk_that_lies_about_its_range_is_refused(self, server, token):
        ident = self.make(server, token)
        assert self.put(server, token, ident, b"a" * 100, 0, 999)[0] == 400
        status, _, _ = call(server, "PUT", f"/uploads/{ident}", b"a" * 10, token,
                            {"Content-Range": "bytes 0-99/300"})
        assert status == 400

    def test_an_oversized_chunk_is_refused_unread(self, server, token, monkeypatch):
        monkeypatch.setattr(hosted, "CHUNK_MAX", 50)
        ident = self.make(server, token)
        assert self.put(server, token, ident, b"a" * 100, 0, 300)[0] == 413

    def test_an_upload_larger_than_the_limit_is_refused_at_creation(self, server, token):
        status, body, _ = call(server, "POST", "/uploads",
                               {"kind": "audio", "size": 10**9}, token)
        assert status == 413 and "MB" in body["error"]

    def test_somebody_elses_upload_does_not_exist(self, server, token, other):
        ident = self.make(server, token)
        assert call(server, "GET", f"/uploads/{ident}", token=other)[0] == 404
        assert self.put(server, other, ident, b"a", 0, 300)[0] == 404

    def test_a_part_upload_survives_a_restart(self, server, token, renderer):
        ident = self.make(server, token)
        self.put(server, token, ident, b"a" * 120, 0, 300)
        again = hosted.Renderer(renderer.root)
        assert again.uploads[ident].received == 120


class TestJobs:
    def test_a_card_from_an_upload_comes_back_as_a_clip_in_ranges(
            self, server, token, other, captured_media):
        status, job, _ = card_job(server, token, captured_media)
        assert status == 202, job
        status, job = wait_for(server, token, job["id"])
        assert job["state"] == "done", job
        assert job["caption"] == "https://www.youtube.com/watch?v=abcdefghijk"

        response, whole = call(server, "GET", f"/jobs/{job['id']}/clip", token=token,
                               raw=True)
        assert response.status == 200 and whole[4:8] == b"ftyp"
        assert int(response.getheader("Content-Length")) == len(whole) == job["size"]
        response, part = call(server, "GET", f"/jobs/{job['id']}/clip", token=token,
                              headers={"Range": "bytes=100-"}, raw=True)
        assert response.status == 206 and part == whole[100:]
        assert call(server, "GET", f"/jobs/{job['id']}", token=other)[0] == 404

    def test_the_uploads_are_spent_by_the_job(self, server, token, renderer,
                                              captured_media):
        audio = upload(server, token, "audio", captured_media["audio"].read_bytes())
        art = upload(server, token, "artwork", artwork_bytes())
        status, job, _ = call(server, "POST", "/jobs",
                              job_body(audio=audio, artwork=art), token)
        assert status == 202
        assert audio not in renderer.uploads and art not in renderer.uploads
        status, again, _ = call(server, "POST", "/jobs",
                                job_body(audio=audio, artwork=art), token)
        assert status in (404, 409)

    def test_asking_again_after_a_lost_answer_names_the_job_already_made(
            self, server, token, renderer, captured_media, monkeypatch):
        """The 202 never arrived, so the client asks again with uploads the first
        request spent. It must hear which job it already has, not "no such upload",
        or it sends everything again and renders the clip twice. Found by the audit."""
        release = threading.Event()
        monkeypatch.setattr(pipeline, "produce",
                            lambda *a, **k: release.wait(10) or (_ for _ in ()).throw(
                                ValueError("stopped")))
        audio = upload(server, token, "audio", captured_media["audio"].read_bytes())
        art = upload(server, token, "artwork", artwork_bytes())
        body = job_body(audio=audio, artwork=art)
        first = call(server, "POST", "/jobs", body, token)[1]
        status, again, _ = call(server, "POST", "/jobs", body, token)
        assert status == 409 and again["job"] == first["id"]
        release.set()

    def test_the_list_holds_only_the_callers_jobs(self, server, token, other,
                                                  captured_media):
        made = card_job(server, token, captured_media)[1]
        wait_for(server, token, made["id"])
        status, mine, _ = call(server, "GET", "/jobs", token=token)
        assert status == 200 and [j["id"] for j in mine["jobs"]] == [made["id"]]
        assert call(server, "GET", "/jobs", token=other)[1]["jobs"] == []

    def test_an_unfinished_upload_cannot_be_used(self, server, token):
        status, made, _ = call(server, "POST", "/uploads",
                               {"kind": "audio", "size": 300}, token)
        art = upload(server, token, "artwork", artwork_bytes())
        status, body, _ = call(server, "POST", "/jobs",
                               job_body(audio=made["id"], artwork=art), token)
        assert status == 409 and body["received"] == 0

    @pytest.mark.parametrize("change, words", [
        ({"start": 0.0, "end": 95.0}, "90s WhatsApp Status limit"),
        ({"end": 10.0}, "end has to come after"),
        ({"video_id": "../../x"}, "not a YouTube video id"),
        ({"mode": "gif"}, "mode is card or video"),
        ({"mode": "video"}, "video mode needs the video upload"),
        ({"start": 50.0, "end": 55.0}, "past the end of the video"),
        ({"start": float("nan")}, "has to be a number"),
        ({"artwork": None}, "card mode needs the artwork upload"),
    ])
    def test_a_window_or_a_mode_the_engine_would_refuse_is_refused_here(
            self, server, token, change, words):
        body = job_body(audio="a" * 24, artwork="b" * 24)
        body.update(change)
        body = {k: v for k, v in body.items() if v is not None}
        if body["start"] != body["start"]:
            body["start"] = "NaN"
        status, answer, _ = call(server, "POST", "/jobs", body, token)
        assert status == 400 and words in answer["error"]

    def test_artwork_that_is_not_an_image_is_refused(self, server, token,
                                                      captured_media):
        audio = upload(server, token, "audio", captured_media["audio"].read_bytes())
        art = upload(server, token, "artwork", b"<html>not a picture</html>")
        status, body, _ = call(server, "POST", "/jobs",
                               job_body(audio=audio, artwork=art), token)
        assert status == 400 and "not an image" in body["error"]

    def test_one_clip_at_a_time_per_person(self, server, token, renderer,
                                           captured_media, monkeypatch):
        release = threading.Event()
        monkeypatch.setattr(pipeline, "produce",
                            lambda *a, **k: release.wait(10) or (_ for _ in ()).throw(
                                ValueError("stopped")))
        first = card_job(server, token, captured_media)[1]
        status, body, _ = card_job(server, token, captured_media)
        assert status == 409 and body["job"] == first["id"]
        release.set()

    def test_a_rendering_job_can_be_stopped_and_leaves_nothing(
            self, server, token, renderer, captured_media, monkeypatch):
        def slow(*_args, **_kwargs):
            proc.run_child(["sleep", "30"])
            raise AssertionError("not cancelled")

        monkeypatch.setattr(pipeline, "produce", slow)
        job = card_job(server, token, captured_media)[1]
        for _ in range(100):
            if renderer.jobs[job["id"]].thread:
                break
            time.sleep(0.05)
        started = time.time()
        assert call(server, "DELETE", f"/jobs/{job['id']}", token=token)[0] == 200
        for _ in range(100):
            if job["id"] not in renderer.jobs:
                break
            time.sleep(0.05)
        assert job["id"] not in renderer.jobs
        assert time.time() - started < 5
        assert not (renderer.jobs_dir / job["id"]).exists()

    def test_a_folder_with_no_record_is_removed_on_start(self, renderer):
        stray = renderer.jobs_dir / ("s" * 24)
        stray.mkdir()
        (stray / "audio.media").write_bytes(b"x")
        hosted.Renderer(renderer.root)
        assert not stray.exists()

    def test_a_job_interrupted_by_a_restart_says_so(self, renderer, token):
        folder = renderer.jobs_dir / ("j" * 24)
        folder.mkdir()
        job = hosted.HostedJob(id="j" * 24, owner=hosted.hash_token(token),
                               user="alice", request={}, folder=folder,
                               state=hosted.RENDERING)
        job.save()
        again = hosted.Renderer(renderer.root)
        assert again.jobs["j" * 24].state == "failed"
        assert "restarted" in again.jobs["j" * 24].error


class TestTheJanitor:
    def test_an_abandoned_upload_and_an_old_clip_are_removed(self, renderer, token):
        owner = hosted.hash_token(token)
        upload = renderer.create_upload(owner, "audio", 100)
        folder = renderer.jobs_dir / ("k" * 24)
        folder.mkdir()
        job = hosted.HostedJob(id="k" * 24, owner=owner, user="alice", request={},
                               folder=folder, state=hosted.DONE, finished=time.time())
        renderer.jobs[job.id] = job
        renderer.sweep(now=time.time() + 60)
        assert upload.id in renderer.uploads and job.id in renderer.jobs
        renderer.sweep(now=time.time() + hosted.JOB_TTL + 1)
        assert upload.id not in renderer.uploads and not upload.path.exists()
        assert job.id not in renderer.jobs and not folder.exists()
