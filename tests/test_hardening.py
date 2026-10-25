"""What the audit of 2026-10-25, before the repository was published, found in the
local engine, held in place: a link cannot pass options to yt-dlp, a page reached
by another name cannot read the token, sending is never a default, a prune never
fails a render or deletes a clip being posted, the sheet never fails a post, a long
line of words cannot hold the render slot, and an error shown to a person names no
path on the machine. The hosted site's share is in test_portal.py."""

from __future__ import annotations

import http.client
import inspect
import threading
import time
from pathlib import Path

import pytest

from wastatus import compose, fetch, pipeline, post, retention, serve, sheet


class TestALinkIsOnlyALink:
    def test_yt_dlp_is_told_where_its_options_end(self, monkeypatch):
        seen = []
        monkeypatch.setattr(fetch, "_run", lambda cmd, timeout=0: seen.append(cmd) or "{}")
        fetch.probe("--version")
        assert seen and seen[0][-2:] == ["--", "--version"]

    @pytest.mark.parametrize("url", ["--exec=id", "file:///etc/passwd", "ftp://x/y"])
    def test_a_window_needs_a_web_address(self, url):
        with pytest.raises(ValueError):
            pipeline.resolve_window(url, "0:00", None, 15)

    @pytest.mark.parametrize("url", ["youtu.be/abcdefghijk", "www.youtube.com/watch?v=abcdefghijk"])
    def test_a_link_pasted_without_its_scheme_still_works(self, url):
        assert pipeline.resolve_window(url, "0:00", None, 15) == (0.0, 15.0)

    def test_a_length_that_is_not_a_number_is_refused(self):
        with pytest.raises(ValueError):
            pipeline.resolve_window("https://youtu.be/abcdefghijk", "0:00", None, float("nan"))

    def test_the_proxy_password_stays_out_of_the_log(self):
        shown = fetch._shown(["-J", "--proxy", "http://me:secret@proxy:8080", "--", "u"])
        assert "secret" not in shown and "***" in shown


class TestAnotherNameForThisMachine:
    @pytest.fixture
    def base(self, tmp_path):
        app = serve.App(out=tmp_path, cdp_port=9222, keep_last=20)
        server = serve.make_server(app, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield server.server_address[1]
        server.shutdown()
        server.server_close()

    def ask(self, port, method, path, host, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request(method, path, body=body, headers={"Host": host})
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, data

    def test_a_rebinding_name_gets_no_token(self, base):
        status, data = self.ask(base, "GET", "/", "evil.example")
        assert status == 403 and b"X-Wastatus" not in data

    def test_the_address_still_gets_the_page(self, base):
        status, _ = self.ask(base, "GET", "/", f"127.0.0.1:{base}")
        assert status == 200

    def test_a_length_that_is_not_a_number_is_refused_unread(self, base):
        import socket

        with socket.create_connection(("127.0.0.1", base), timeout=10) as sock:
            sock.sendall(f"POST /api/render HTTP/1.1\r\nHost: 127.0.0.1:{base}\r\n"
                         "Content-Length: -1\r\n\r\n".encode())
            answer = sock.recv(4096)
        assert answer.startswith(b"HTTP/1.1 403") or answer.startswith(b"HTTP/1.1 413")


class TestSendingIsNeverTheDefault:
    @pytest.mark.parametrize("function", [post.post_video, post.post_text, serve.App.post_clip])
    def test_send_defaults_to_no(self, function):
        assert inspect.signature(function).parameters["send"].default is False

    def test_an_unreadable_store_is_unconfirmed_not_sent(self, monkeypatch):
        monkeypatch.setattr(post, "store_is_readable", lambda page: False)
        monkeypatch.setattr(post, "wait_until_settled", lambda page, timeout: 1.0)
        with pytest.raises(post.StatusUnconfirmed):
            post.confirm_sent(object(), None, sent_at=0, timeout=1)


class TestPruning:
    def clip(self, folder: Path, stem: str, age: float) -> Path:
        path = folder / f"{stem}.mp4"
        path.write_bytes(b"x")
        (folder / f"{stem}.caption.txt").write_text("c", encoding="utf-8")
        stamp = time.time() - age
        import os
        os.utime(path, (stamp, stamp))
        return path

    def test_a_clip_being_posted_is_never_pruned(self, tmp_path):
        old = self.clip(tmp_path, "old", 100)
        self.clip(tmp_path, "new", 1)
        with retention.hold(old):
            retention.prune(tmp_path, keep=1)
            assert old.exists()
        retention.prune(tmp_path, keep=1)
        assert not old.exists()

    def test_a_clip_gone_already_is_not_a_failure(self, tmp_path, monkeypatch):
        self.clip(tmp_path, "a", 100)
        self.clip(tmp_path, "b", 50)
        self.clip(tmp_path, "c", 1)
        real = retention.group_files

        def vanished(out_dir, stem):
            files = real(out_dir, stem)
            for file in files:
                file.unlink()  # somebody else got there between listing and deleting
            return files
        monkeypatch.setattr(retention, "group_files", vanished)
        retention.prune(tmp_path, keep=1)  # does not raise

    def test_the_clip_list_survives_a_clip_vanishing(self, tmp_path, monkeypatch):
        app = serve.App(out=tmp_path, cdp_port=9222, keep_last=20)
        self.clip(tmp_path, "a", 1)
        monkeypatch.setattr(app, "clip_json", lambda stem: (_ for _ in ()).throw(FileNotFoundError()))
        assert app.clips() == []


def test_the_sheet_never_fails_a_post(tmp_path, monkeypatch):
    monkeypatch.setattr(sheet, "configured", lambda: True)
    clip = tmp_path / "x.mp4"
    clip.write_bytes(b"x")
    (tmp_path / "x.json").write_text('{"start": "a", "end": 3}', encoding="utf-8")
    assert sheet.record(clip=clip, stem="x") is False


def test_a_very_long_line_is_ellipsised_quickly():
    from PIL import Image, ImageDraw, ImageFont

    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    font = ImageFont.truetype(str(Path(compose.__file__).resolve().parent.parent
                                  / "assets" / "fonts" / "DejaVuSans.ttf"), 48)
    text = "word " * 4 + "x" * 20000 + " end"
    started = time.monotonic()
    lines = compose._wrap(draw, text, font, 900, 2)
    assert time.monotonic() - started < 2.0
    assert lines[-1].endswith("...")


def test_a_render_request_holds_its_words_to_a_caption_s_length(tmp_path):
    handler = serve.Handler.__new__(serve.Handler)
    handler.app = serve.App(out=tmp_path, cdp_port=9222, keep_last=20)
    job = handler._job_from({"url": "https://youtu.be/abcdefghijk", "start": "0:00",
                             "duration": 15, "title": "t" * 100000})
    assert len(job.title) <= serve.CAPTION_MAX


def test_one_render_at_a_time(tmp_path, monkeypatch):
    app = serve.App(out=tmp_path, cdp_port=9222, keep_last=20)
    release = threading.Event()
    monkeypatch.setattr(pipeline, "produce", lambda job, run, progress: release.wait(5))
    job = pipeline.Job(url="https://youtu.be/abcdefghijk", start=0, end=15, out=tmp_path)
    app.render(job, follow_up=False)
    with pytest.raises(RuntimeError):
        app.render(job, follow_up=False)
    release.set()


@pytest.mark.parametrize("text, kept", [
    ("ffmpeg could not cut the window: /data/users/ab/work/x.media: bad", "a file: bad"),
    ("https://youtu.be/abc/def is not a video", "https://youtu.be/abc/def"),
])
def test_an_error_shown_to_a_person_names_no_path(text, kept):
    shown = serve.plain_error(Exception(text))
    assert "/data/" not in shown and kept in shown
