"""The local page's server, against a real socket on an ephemeral port.

The interesting behaviour here is not the happy path, it is the guards: any website
you visit can send a request to `http://127.0.0.1:8765`, and this server can post to
a WhatsApp Status and read files off the disk. So the token, the origin check and
the filename check all get tests.
"""

from __future__ import annotations

import io
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

from wastatus import compose, gifs, post, proc, render, serve, stickers


@pytest.fixture
def out(tmp_path: Path) -> Path:
    folder = tmp_path / "out"
    folder.mkdir()
    (folder / "20260818_thiruppavai_70-85.mp4").write_bytes(b"not really an mp4")
    (folder / "20260818_thiruppavai_70-85.caption.txt").write_text(
        "https://youtu.be/abc\n", encoding="utf-8"
    )
    (folder / "20260818_thiruppavai_70-85.png").write_bytes(b"not really a png")
    return folder


@pytest.fixture
def app(out: Path) -> serve.App:
    return serve.App(out=out, cdp_port=9222, keep_last=20)


@pytest.fixture(autouse=True)
def no_real_browser(monkeypatch):
    """No test may reach whatever browser happens to run on this machine."""
    monkeypatch.setattr(
        post, "discover",
        lambda preferred=9222, extra=(): post.Endpoint(preferred, "Chrome/test", {}),
    )


@pytest.fixture
def base(app: serve.App):
    """A running server. Port 0 means the OS picks a free one."""
    server = serve.make_server(app, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://{serve.BIND}:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _handler(app: serve.App, *, host: str, origin: str | None, token: str):
    """A Handler with just enough on it to ask `_authorised` a question.

    Built by hand rather than over a socket, because the interesting cases are
    addresses this machine will not let a test bind to.
    """
    import email.message

    handler = serve.Handler.__new__(type("Bound", (serve.Handler,), {"app": app}))
    headers = email.message.Message()
    headers["Host"] = host
    if origin:
        headers["Origin"] = origin
    headers[serve.TOKEN_HEADER] = token
    handler.headers = headers
    return handler


def fetch(url: str, *, token: str | None = None, method: str = "GET",
          body: dict | None = None, origin: str | None = None):
    """Returns (status, parsed body or raw bytes)."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if token:
        request.add_header(serve.TOKEN_HEADER, token)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    if origin:
        request.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        raw, status = error.read(), error.code
    try:
        return status, json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return status, raw


def fetch_range(url: str, token: str, byte_range: str):
    """Returns (status, headers, body) for a ranged GET, the way a player asks."""
    request = urllib.request.Request(url)
    request.add_header(serve.TOKEN_HEADER, token)
    request.add_header("Range", byte_range)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


class TestKeepAlive:
    """A refused POST must still leave the connection usable.

    On 2026-08-20 a restart left a tab holding the previous run's token. Every POST
    it made was answered 403 without the body being read, and because this server
    speaks HTTP/1.1 the connection stayed open with the body still in it. The next
    request line was then parsed out of the middle of that JSON, and the log filled
    with `501 Unsupported method ('{"url":...}POST')`.
    """

    def _conn(self, base: str):
        import http.client
        from urllib.parse import urlparse

        parts = urlparse(base)
        return http.client.HTTPConnection(parts.hostname, parts.port, timeout=10)

    def test_a_refused_post_does_not_poison_the_next_request(self, base, app):
        conn = self._conn(base)
        body = json.dumps({"url": "https://youtu.be/abc", "duration": 90}).encode()
        conn.request("POST", "/api/render", body=body, headers={
            "Content-Type": "application/json",
            serve.TOKEN_HEADER: "not-the-token",
        })
        assert conn.getresponse().read() and True
        conn.close()

        # Same shape, one connection, two requests: the second is the one that used
        # to come back 501 because the first body was still unread.
        conn = self._conn(base)
        conn.request("POST", "/api/render", body=body, headers={
            "Content-Type": "application/json",
            serve.TOKEN_HEADER: "not-the-token",
        })
        first = conn.getresponse()
        assert first.status == HTTPStatus.FORBIDDEN
        first.read()

        conn.request("GET", "/api/state", headers={serve.TOKEN_HEADER: app.token})
        second = conn.getresponse()
        payload = second.read()
        conn.close()
        assert second.status == HTTPStatus.OK, (
            f"the leftover body was parsed as a request line: {payload[:120]!r}")


class TestGuards:
    def test_the_page_itself_needs_no_token(self, base):
        status, body = fetch(f"{base}/")
        assert status == 200
        assert b"WhatsApp Status Maker" in body

    def test_the_page_carries_the_token_for_its_own_javascript(self, base, app):
        _, body = fetch(f"{base}/")
        assert app.token.encode() in body
        assert b"{{TOKEN}}" not in body

    def test_api_without_a_token_is_refused(self, base):
        status, body = fetch(f"{base}/api/state")
        assert status == 403
        assert "token" in body["error"]

    def test_api_with_the_wrong_token_is_refused(self, base):
        status, _ = fetch(f"{base}/api/state", token="not-the-token")
        assert status == 403

    def test_api_with_the_token_works(self, base, app):
        status, body = fetch(f"{base}/api/state", token=app.token)
        assert status == 200
        assert body["cdp_port"] == 9222

    def test_a_request_from_another_website_is_refused(self, base, app):
        """Even holding the token, an off-origin caller gets nothing."""
        status, _ = fetch(
            f"{base}/api/state", token=app.token, origin="https://example.com"
        )
        assert status == 403

    def test_our_own_origin_is_accepted(self, base, app):
        port = base.rsplit(":", 1)[1]
        status, _ = fetch(
            f"{base}/api/state", token=app.token, origin=f"http://127.0.0.1:{port}"
        )
        assert status == 200

    def test_a_page_opened_on_another_loopback_address_can_still_write(self, app):
        """Chrome sends Origin on every same-origin POST. A hardcoded 127.0.0.1
        refused every write from a page opened on any other address, which is what
        would block reaching the page from a phone over a private network."""
        handler = _handler(app, host="127.0.0.2:8765",
                           origin="http://127.0.0.2:8765", token=app.token)
        assert handler._authorised() is True

    def test_a_hostname_in_the_host_header_is_not_trusted(self, app):
        """DNS rebinding: an attacker points evil.com at 127.0.0.1, and the browser
        then sends a matching Host and Origin. Only addresses are trusted, so both
        are refused."""
        handler = _handler(app, host="evil.com:8765",
                           origin="http://evil.com:8765", token=app.token)
        assert handler._authorised() is False

    def test_an_ipv6_loopback_page_can_write(self, app):
        handler = _handler(app, host="[::1]:8765", origin="http://[::1]:8765",
                           token=app.token)
        assert handler._authorised() is True

    def test_a_foreign_origin_is_refused_whatever_the_host_says(self, app):
        handler = _handler(app, host="127.0.0.1:8765",
                           origin="https://evil.example", token=app.token)
        assert handler._authorised() is False

    def test_the_right_origin_without_the_token_is_still_refused(self, app):
        handler = _handler(app, host="127.0.0.1:8765",
                           origin="http://127.0.0.1:8765", token="not-the-token")
        assert handler._authorised() is False

    def test_a_preflight_gets_no_permission(self, base):
        """Without CORS permission, a cross-origin caller can never send the header."""
        status, _ = fetch(f"{base}/api/render", method="OPTIONS")
        assert status == 403

    def test_media_may_carry_the_token_in_the_query(self, base, app):
        """An <img> cannot set a header, so these two endpoints accept `t`."""
        url = f"{base}/api/frame?stem=20260818_thiruppavai_70-85&t={app.token}"
        status, body = fetch(url)
        assert status == 200
        assert body == b"not really a png"

    def test_media_without_any_token_is_refused(self, base):
        status, _ = fetch(f"{base}/api/frame?stem=20260818_thiruppavai_70-85")
        assert status == 403


class TestFilenames:
    @pytest.mark.parametrize("stem", [
        "../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        "/etc/passwd",
        "clip.mp4",
        "",
        "a" * 200,
    ])
    def test_nothing_but_a_stem_is_served(self, base, app, stem):
        status, _ = fetch(f"{base}/api/clip?stem={stem}&t={app.token}")
        assert status in (400, 404), f"{stem!r} was not refused"

    def test_a_missing_clip_is_a_clean_404(self, base, app):
        status, body = fetch(f"{base}/api/clip?stem=20260818_nothing_0-15&t={app.token}")
        assert status == 404
        assert "not on disk" in body["error"]


class _Blank:
    """Stands in for a Pillow image where only the plumbing is under test."""

    def convert(self, _mode):
        return self


class TestRendering:
    def test_a_bad_window_is_rejected_with_the_reason(self, base, app):
        status, body = fetch(
            f"{base}/api/render", token=app.token, method="POST",
            body={"url": "https://youtu.be/abc", "duration": 200},
        )
        assert status == 400
        assert "90s WhatsApp Status limit" in body["error"]

    def test_a_missing_link_is_rejected(self, base, app):
        status, body = fetch(
            f"{base}/api/render", token=app.token, method="POST", body={"url": " "},
        )
        assert status == 400
        assert "link" in body["error"]

    def test_an_unparseable_timestamp_is_rejected(self, base, app):
        status, body = fetch(
            f"{base}/api/render", token=app.token, method="POST",
            body={"url": "https://youtu.be/abc", "start": "half past two"},
        )
        assert status == 400
        assert body["error"]

    def test_every_word_on_the_frame_reaches_the_job(self, base, app, monkeypatch):
        """A field the page sends and the server drops is invisible: the box takes
        your sentence and nothing happens, which is exactly how the label spent a
        day not being drawn. So every one of them is checked end to end."""
        seen: list[serve.Job] = []
        monkeypatch.setattr(
            serve.pipeline, "produce",
            lambda job, *a, **kw: seen.append(job) or (_ for _ in ()).throw(
                RuntimeError("far enough")
            ),
        )
        fetch(
            f"{base}/api/render", token=app.token, method="POST",
            body={
                "url": "https://youtu.be/abc", "duration": 15, "video": True,
                "title": "A Title", "channel": "A Channel",
                "footer": "  a footer  ", "eyebrow": "  a label  ",
                "topline": "  a line at the top  ",
            },
        )
        for _ in range(50):
            if seen:
                break
            time.sleep(0.02)
        assert seen, "the render thread never reached produce"
        job = seen[0]
        assert job.title == "A Title"
        assert job.channel == "A Channel"
        assert job.footer == "a footer"
        assert job.eyebrow == "a label"
        assert job.topline == "a line at the top"

    def test_the_preview_draws_every_word_too(self, base, app, monkeypatch):
        """The preview and the clip come from the same `CardText`. A field missing
        from one of them is a preview that lies about what the clip will hold."""
        seen: list[compose.CardText] = []
        monkeypatch.setattr(
            serve.App, "preview_jpeg",
            lambda self, stem, words, fill=None, framing=None: (
                seen.append(words) or b"\xff\xd8jpeg"),
        )
        status, _ = fetch(
            f"{base}/api/preview", token=app.token, method="POST",
            body={
                "stem": "20260818_thiruppavai_70-85", "title": "A Title",
                "channel": "A Channel", "footer": "a footer",
                "eyebrow": "a label", "topline": "a line at the top",
            },
        )
        assert status == 200
        assert seen and seen[0] == compose.CardText(
            title="A Title", channel="A Channel", footer="a footer",
            eyebrow="a label", topline="a line at the top",
        )

    def test_the_preview_anchors_the_top_text_where_the_clip_did(
        self, base, app, out, monkeypatch
    ):
        """The preview draws over a still of the frames and cannot measure them, so
        it reads back where they landed. Getting this wrong puts the top line
        against the wrong edge in the preview and nowhere near it in the clip."""
        (out / "20260818_thiruppavai_70-85.base.png").write_bytes(b"not really a png")
        (out / "20260818_thiruppavai_70-85.json").write_text(
            json.dumps({"url": "https://youtu.be/abc", "start": 70.0, "end": 85.0,
                        "video": True, "picture_top": 636}),
            encoding="utf-8",
        )
        seen: list[int | None] = []
        monkeypatch.setattr(
            serve.compose, "build_overlay",
            lambda words, dest, decals=None, picture_top=None, picture_bottom=None:
                seen.append(picture_top) or dest.write_bytes(b"x") or dest,
        )
        monkeypatch.setattr(serve.Image, "open", lambda *a, **k: _Blank())
        monkeypatch.setattr(serve.Image, "alpha_composite", lambda a, b: _Blank())
        monkeypatch.setattr(serve.App, "_shrink", lambda self, picture: b"jpeg")
        fetch(
            f"{base}/api/preview", token=app.token, method="POST",
            body={"stem": "20260818_thiruppavai_70-85", "title": "A Title"},
        )
        assert seen == [636]

    def test_a_clip_made_before_that_was_recorded_previews_without_it(
        self, base, app, out, monkeypatch
    ):
        (out / "20260818_thiruppavai_70-85.base.png").write_bytes(b"not really a png")
        seen: list[int | None] = []
        monkeypatch.setattr(
            serve.compose, "build_overlay",
            lambda words, dest, decals=None, picture_top=None, picture_bottom=None:
                seen.append(picture_top) or dest.write_bytes(b"x") or dest,
        )
        monkeypatch.setattr(serve.Image, "open", lambda *a, **k: _Blank())
        monkeypatch.setattr(serve.Image, "alpha_composite", lambda a, b: _Blank())
        monkeypatch.setattr(serve.App, "_shrink", lambda self, picture: b"jpeg")
        fetch(
            f"{base}/api/preview", token=app.token, method="POST",
            body={"stem": "20260818_thiruppavai_70-85", "title": "A Title"},
        )
        assert seen == [None]

    def test_a_failing_render_becomes_a_failed_task_not_a_crash(
        self, base, app, monkeypatch
    ):
        def explode(*_args, **_kwargs):
            raise RuntimeError("yt-dlp said no")

        monkeypatch.setattr(serve.pipeline, "produce", explode)
        status, body = fetch(
            f"{base}/api/render", token=app.token, method="POST",
            body={"url": "https://youtu.be/abc", "duration": 15},
        )
        assert status == 200
        task = _settle(base, app, body["id"])
        assert task["status"] == "failed"
        assert task["error"] == "yt-dlp said no"

    def test_a_task_id_that_does_not_exist_is_a_404(self, base, app):
        status, _ = fetch(f"{base}/api/task?id=nope", token=app.token)
        assert status == 404


class TestPosting:
    def test_posting_calls_the_same_function_the_cli_uses(
        self, base, app, monkeypatch
    ):
        sent: dict = {}

        def fake_post_video(path, caption, *, port, send=True):
            sent.update(path=Path(path), caption=caption, port=port)
            return 4.2

        monkeypatch.setattr(post, "post_video", fake_post_video)
        status, body = fetch(
            f"{base}/api/post", token=app.token, method="POST",
            body={"stem": "20260818_thiruppavai_70-85", "send": True},
        )
        assert status == 200
        task = _settle(base, app, body["id"])
        assert task["status"] == "done"
        assert task["result"] == {
            "seconds": 4.2, "follow_up": False, "sent": True, "port": 9222,
        }
        assert sent["caption"] == "https://youtu.be/abc"
        assert sent["port"] == 9222
        assert sent["path"].name == "20260818_thiruppavai_70-85.mp4"

    def test_the_follow_up_posts_the_text_too(self, base, app, monkeypatch):
        monkeypatch.setattr(post, "post_video", lambda *a, **k: 1.0)
        texts = []
        monkeypatch.setattr(
            post, "post_text", lambda text, **k: texts.append(text) or 1.0
        )
        _, body = fetch(
            f"{base}/api/post", token=app.token, method="POST",
            body={
                "stem": "20260818_thiruppavai_70-85",
                "follow_up": True,
                "send": True,
            },
        )
        task = _settle(base, app, body["id"])
        assert task["result"]["follow_up"] is True
        assert texts == ["https://youtu.be/abc"]

    def test_nothing_is_sent_unless_the_page_says_send(self, base, app, monkeypatch):
        """The page's default action stops with the composer loaded.

        Pressing Send is the irreversible step and it belongs to the owner, so an
        omitted flag must never mean "and broadcast it".
        """
        calls: list[bool] = []
        monkeypatch.setattr(
            post, "post_video",
            lambda *a, send=True, **k: calls.append(send) or None,
        )
        _, body = fetch(
            f"{base}/api/post", token=app.token, method="POST",
            body={"stem": "20260818_thiruppavai_70-85"},
        )
        task = _settle(base, app, body["id"])
        assert calls == [False]
        assert task["kind"] == "prepare"
        assert task["result"]["sent"] is False

    def test_a_prepared_composer_ignores_the_follow_up(self, base, app, monkeypatch):
        """A follow up is a second Status. There is nothing to follow up yet."""
        monkeypatch.setattr(post, "post_video", lambda *a, **k: None)
        monkeypatch.setattr(
            post, "post_text",
            lambda *a, **k: pytest.fail("nothing may be sent while only loading"),
        )
        _, body = fetch(
            f"{base}/api/post", token=app.token, method="POST",
            body={"stem": "20260818_thiruppavai_70-85", "follow_up": True},
        )
        assert _settle(base, app, body["id"])["result"]["follow_up"] is False

    def test_two_posts_at_once_are_refused(self, base, app, monkeypatch):
        """The composer holds every file it is given and sends all of them, so one
        overlapping request is how a single command posts two Statuses."""
        import threading

        release = threading.Event()
        monkeypatch.setattr(
            post, "post_video", lambda *a, **k: release.wait(10) or 1.0
        )
        _, first = fetch(
            f"{base}/api/post", token=app.token, method="POST",
            body={"stem": "20260818_thiruppavai_70-85", "send": True},
        )
        try:
            status, body = fetch(
                f"{base}/api/post", token=app.token, method="POST",
                body={"stem": "20260818_thiruppavai_70-85", "send": True},
            )
            assert status == 409
            assert "already being driven" in body["error"]
        finally:
            release.set()
        _settle(base, app, first["id"])

    def test_posting_a_clip_that_is_not_there_is_a_404(self, base, app):
        status, body = fetch(
            f"{base}/api/post", token=app.token, method="POST",
            body={"stem": "20260818_nothing_0-15", "send": True},
        )
        assert status == 404
        assert "no clip" in body["error"]

    def test_a_posting_failure_is_reported_not_raised(self, base, app, monkeypatch):
        def refuse(*_args, **_kwargs):
            raise post.PostError("no logged in tab")

        monkeypatch.setattr(post, "post_video", refuse)
        _, body = fetch(
            f"{base}/api/post", token=app.token, method="POST",
            body={"stem": "20260818_thiruppavai_70-85"},
        )
        task = _settle(base, app, body["id"])
        assert task["status"] == "failed"
        assert task["error"] == "no logged in tab"


class TestReadingTheOutputFolder:
    def test_a_clip_is_described_for_the_page(self, app):
        clip = app.clip_json("20260818_thiruppavai_70-85")
        assert clip["name"] == "Thiruppavai"
        assert clip["window"] == "1:10 to 1:25"
        assert clip["caption"] == "https://youtu.be/abc"
        assert clip["has_frame"] is True
        assert clip["video"] is False

    def test_a_collision_suffix_does_not_break_the_window(self, app, out):
        (out / "20260818_thiruppavai_70-85-2.mp4").write_bytes(b"x")
        assert app.clip_json("20260818_thiruppavai_70-85-2")["window"] == "1:10 to 1:25"

    def test_video_mode_is_labelled(self, app, out):
        (out / "20260818_thiruppavai_70-85_video.mp4").write_bytes(b"x")
        clip = app.clip_json("20260818_thiruppavai_70-85_video")
        assert clip["video"] is True
        assert clip["window"] == "1:10 to 1:25"

    def test_a_video_clip_with_a_collision_suffix_is_still_a_video_clip(
            self, app, out):
        """The gap the two tests above left between them.

        `naming` writes the marker first and the suffix after it, so a second take
        of the same window ends in `_video-2` and therefore in neither one alone.
        `removesuffix("_video")` missed it and `endswith("_video")` was False, so
        the panel called it an artwork card and showed no window at all. Every clip
        the owner made on 2026-08-25 after the first was affected. Found by reading
        the badge on a clip that was plainly video.
        """
        stem = "20260818_thiruppavai_70-85_video-2"
        (out / f"{stem}.mp4").write_bytes(b"x")
        clip = app.clip_json(stem)
        assert clip["video"] is True, "a video clip labelled as an artwork card"
        assert clip["window"] == "1:10 to 1:25"
        assert clip["name"] == "Thiruppavai"

    def test_the_window_survives_every_tail_the_namer_can_write(self, app, out):
        r"""The end of a window is `-\d+` too, so the tail cannot simply be cut off.

        A first fix stripped `(?:-\d+)?$` before matching, which ate the window's
        own end value and lost the window on every clip that had no suffix at all.
        These four shapes are the whole grammar, and they are checked together so
        that fixing one cannot quietly break another.
        """
        for stem, window in [
            ("20260818_thiruppavai_70-85", "1:10 to 1:25"),
            ("20260818_thiruppavai_70-85-2", "1:10 to 1:25"),
            ("20260818_thiruppavai_70-85_video", "1:10 to 1:25"),
            ("20260818_thiruppavai_70-85_video-2", "1:10 to 1:25"),
        ]:
            (out / f"{stem}.mp4").write_bytes(b"x")
            assert app.clip_json(stem)["window"] == window, stem

    def test_the_sidecar_outranks_the_name_for_the_mode(self, app, out):
        """The name is a guess; the sidecar is the job that was actually run."""
        stem = "20260818_thiruppavai_70-85"
        (out / f"{stem}.json").write_text('{"video": true}', encoding="utf-8")
        assert app.clip_json(stem)["video"] is True

    def test_roman_numerals_survive_the_name(self, app, out):
        (out / "20260818_thevaram-vol-ii_0-60.mp4").write_bytes(b"x")
        assert app.clip_json("20260818_thevaram-vol-ii_0-60")["name"] == "Thevaram Vol II"

    def test_an_hour_long_window_reads_as_hours(self, app, out):
        (out / "20260818_long_3700-3760.mp4").write_bytes(b"x")
        assert app.clip_json("20260818_long_3700-3760")["window"] == (
            "1:01:40 to 1:02:40"
        )

    def test_newest_first(self, app, out):
        import os
        import time

        (out / "20260818_older_0-15.mp4").write_bytes(b"x")
        os.utime(out / "20260818_older_0-15.mp4", (time.time() - 600,) * 2)
        assert app.clips()[-1]["stem"] == "20260818_older_0-15"

    def test_an_empty_folder_is_not_an_error(self, tmp_path):
        app = serve.App(out=tmp_path / "nothing", cdp_port=9222, keep_last=20)
        assert app.clips() == []

    def test_a_clip_with_no_sidecars_still_lists(self, app, out):
        (out / "20260818_bare_0-15.mp4").write_bytes(b"x")
        clip = app.clip_json("20260818_bare_0-15")
        assert clip["caption"] == ""
        assert clip["has_frame"] is False


class TestSeeking:
    """A <video> jumps by asking for a byte range.

    Without a 206 the slider does nothing: the browser has no way to say "start
    from here", so it replays what it already holds. This was a real bug, found by
    dragging the slider on a real clip.
    """

    def test_a_range_gets_only_that_range(self, base, app, out):
        (out / "20260818_thiruppavai_70-85.mp4").write_bytes(bytes(range(256)))
        status, headers, body = fetch_range(
            f"{base}/api/clip?stem=20260818_thiruppavai_70-85",
            app.token, "bytes=10-19",
        )
        assert status == 206
        assert body == bytes(range(10, 20))
        assert headers["Content-Range"] == "bytes 10-19/256"
        assert headers["Content-Length"] == "10"

    def test_an_open_ended_range_runs_to_the_end(self, base, app, out):
        (out / "20260818_thiruppavai_70-85.mp4").write_bytes(bytes(range(100)))
        status, headers, body = fetch_range(
            f"{base}/api/clip?stem=20260818_thiruppavai_70-85", app.token, "bytes=90-",
        )
        assert status == 206
        assert body == bytes(range(90, 100))
        assert headers["Content-Range"] == "bytes 90-99/100"

    def test_a_suffix_range_gets_the_tail(self, base, app, out):
        """`bytes=-4` asks for the last four bytes, which is how a player finds an
        mp4's index when the file is not faststart."""
        (out / "20260818_thiruppavai_70-85.mp4").write_bytes(bytes(range(100)))
        _, _, body = fetch_range(
            f"{base}/api/clip?stem=20260818_thiruppavai_70-85", app.token, "bytes=-4",
        )
        assert body == bytes(range(96, 100))

    def test_a_range_past_the_end_is_a_416(self, base, app, out):
        (out / "20260818_thiruppavai_70-85.mp4").write_bytes(b"12345")
        status, headers, _ = fetch_range(
            f"{base}/api/clip?stem=20260818_thiruppavai_70-85", app.token, "bytes=99-",
        )
        assert status == 416
        assert headers["Content-Range"] == "bytes */5"

    def test_a_plain_get_still_returns_everything(self, base, app):
        status, body = fetch(
            f"{base}/api/clip?stem=20260818_thiruppavai_70-85&t={app.token}"
        )
        assert status == 200
        assert body == b"not really an mp4"

    def test_the_player_is_told_ranges_are_available(self, base, app):
        request = urllib.request.Request(
            f"{base}/api/clip?stem=20260818_thiruppavai_70-85&t={app.token}"
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.headers["Accept-Ranges"] == "bytes"


class TestTheCaption:
    """The caption is text sent with the video, not pixels inside it, so editing
    it costs nothing and must never trigger a render."""

    def test_an_edit_is_written_to_the_sidecar(self, base, app, out):
        status, body = fetch(
            f"{base}/api/caption", token=app.token, method="POST",
            body={
                "stem": "20260818_thiruppavai_70-85",
                "caption": "  https://youtu.be/abc\n\nThiruppavai, verse 3  ",
            },
        )
        assert status == 200
        assert body["caption"] == "https://youtu.be/abc\n\nThiruppavai, verse 3"
        written = (out / "20260818_thiruppavai_70-85.caption.txt").read_text()
        assert written == "https://youtu.be/abc\n\nThiruppavai, verse 3\n"

    def test_the_edited_caption_is_what_gets_posted(self, base, app, monkeypatch):
        captions: list[str] = []
        monkeypatch.setattr(
            post, "post_video",
            lambda path, caption, **k: captions.append(caption) or None,
        )
        fetch(
            f"{base}/api/caption", token=app.token, method="POST",
            body={"stem": "20260818_thiruppavai_70-85", "caption": "changed"},
        )
        _, body = fetch(
            f"{base}/api/post", token=app.token, method="POST",
            body={"stem": "20260818_thiruppavai_70-85"},
        )
        _settle(base, app, body["id"])
        assert captions == ["changed"]

    def test_an_essay_is_refused(self, base, app):
        status, body = fetch(
            f"{base}/api/caption", token=app.token, method="POST",
            body={"stem": "20260818_thiruppavai_70-85", "caption": "x" * 2000},
        )
        assert status == 400
        assert "too long" in body["error"]

    def test_a_caption_for_a_clip_that_is_not_there_is_a_404(self, base, app):
        status, _ = fetch(
            f"{base}/api/caption", token=app.token, method="POST",
            body={"stem": "20260818_nothing_0-15", "caption": "hello"},
        )
        assert status == 404

    def test_a_caption_cannot_name_a_path(self, base, app):
        status, _ = fetch(
            f"{base}/api/caption", token=app.token, method="POST",
            body={"stem": "../../etc/passwd", "caption": "hello"},
        )
        assert status == 400


class TestTheWindow:
    def test_a_stop_time_is_accepted_instead_of_a_length(self, base, app, monkeypatch):
        """Some people know where the good part ends, not how long it runs."""
        jobs = []
        monkeypatch.setattr(
            serve.App, "render",
            lambda self, job, follow_up: jobs.append(job) or serve.Task(id="x", kind="render"),
        )
        fetch(
            f"{base}/api/render", token=app.token, method="POST",
            body={"url": "https://youtu.be/abc", "start": "1:00", "end": "1:45"},
        )
        assert (jobs[0].start, jobs[0].end) == (60.0, 105.0)

    def test_a_stop_time_before_the_start_is_refused(self, base, app):
        status, body = fetch(
            f"{base}/api/render", token=app.token, method="POST",
            body={"url": "https://youtu.be/abc", "start": "1:00", "end": "0:30"},
        )
        assert status == 400
        assert "end has to come after" in body["error"]

    def test_a_stop_time_wins_over_a_stale_length(self, base, app, monkeypatch):
        jobs = []
        monkeypatch.setattr(
            serve.App, "render",
            lambda self, job, follow_up: jobs.append(job) or serve.Task(id="x", kind="render"),
        )
        fetch(
            f"{base}/api/render", token=app.token, method="POST",
            body={
                "url": "https://youtu.be/abc", "start": "0:10",
                "end": "0:40", "duration": 90,
            },
        )
        assert jobs[0].duration == 30.0


class TestFetchingTheWords:
    """`/api/words`: what the video calls itself, before anything is rendered.

    Answered on the request's own thread rather than as a task, so the failures
    worth testing are the ones a caller sees immediately. `serve.fetch` is patched
    rather than `fetch`, because the helper at the top of this file is called
    `fetch` too and the module under test is the one that matters.
    """

    def test_it_answers_the_words_the_card_would_have_drawn(self, base, app, monkeypatch):
        monkeypatch.setattr(
            serve.fetch, "probe",
            lambda url, timeout=None: serve.fetch.Source(
                video_id="abc", title="Thiruppavai (Official Video)",
                channel="M S Subbulakshmi - Topic", duration=300.0,
                watch_url="https://youtu.be/abc", artist="M S Subbulakshmi",
            ),
        )
        status, body = fetch(
            f"{base}/api/words", token=app.token, method="POST",
            body={"url": "https://youtu.be/abc"},
        )
        assert status == 200
        assert body == {"title": "Thiruppavai", "channel": "M S Subbulakshmi"}

    def test_it_waits_less_than_a_render_would(self, base, app, monkeypatch):
        """Somebody is sitting in front of a spinning icon."""
        seen = {}

        def probe(url, timeout=None):
            seen["timeout"] = timeout
            return serve.fetch.Source(
                video_id="abc", title="T", channel="C", duration=1.0,
                watch_url="https://youtu.be/abc",
            )

        monkeypatch.setattr(serve.fetch, "probe", probe)
        fetch(f"{base}/api/words", token=app.token, method="POST",
              body={"url": "https://youtu.be/abc"})
        assert seen["timeout"] == serve.fetch.PROBE_TIMEOUT

    def test_no_link_is_asked_about_rather_than_probed(self, base, app, monkeypatch):
        monkeypatch.setattr(
            serve.fetch, "probe",
            lambda *a, **k: pytest.fail("nothing should have been probed"))
        status, body = fetch(
            f"{base}/api/words", token=app.token, method="POST", body={"url": "  "})
        assert status == 400
        assert "link" in body["error"]

    def test_youtubes_own_refusal_is_passed_on_in_its_own_words(
            self, base, app, monkeypatch):
        """A playlist, a private video or a dead link. The message `fetch` raises
        is already written for whoever pasted the link, so it goes through whole:
        rewriting it here would lose the one sentence that says what to do."""
        def refuse(url, timeout=None):
            raise serve.fetch.FetchError(
                "that link is a playlist, not one track. Open the song you want")

        monkeypatch.setattr(serve.fetch, "probe", refuse)
        status, body = fetch(
            f"{base}/api/words", token=app.token, method="POST",
            body={"url": "https://youtube.com/playlist?list=PL1"},
        )
        assert status == 502
        assert "playlist" in body["error"]

    def test_a_broken_answer_is_not_a_traceback(self, base, app, monkeypatch):
        """yt-dlp printing something that is not JSON used to be a 500 and a
        stack trace in the log. It is their end failing, which is a 502."""
        def broken(url, timeout=None):
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

        monkeypatch.setattr(serve.fetch, "probe", broken)
        status, body = fetch(
            f"{base}/api/words", token=app.token, method="POST",
            body={"url": "https://youtu.be/abc"},
        )
        assert status == 502
        assert "could not read that link" in body["error"]

    def test_it_is_behind_the_token_like_everything_else(self, base, app, monkeypatch):
        monkeypatch.setattr(
            serve.fetch, "probe",
            lambda *a, **k: pytest.fail("an unauthorised caller reached yt-dlp"))
        status, _ = fetch(
            f"{base}/api/words", method="POST", body={"url": "https://youtu.be/abc"})
        assert status == 403


class TestRememberingAJob:
    def test_the_sidecar_comes_back_as_the_job(self, app, out):
        (out / "20260818_thiruppavai_70-85.json").write_text(
            json.dumps({
                "url": "https://youtu.be/abc", "start": 70.0, "end": 85.0,
                "video": False, "wave": True,
                "title": "Thiruppavai", "channel": "M S Subbulakshmi",
                "footer": "", "eyebrow": "",
            }),
            encoding="utf-8",
        )
        clip = app.clip_json("20260818_thiruppavai_70-85")
        assert clip["job"]["url"] == "https://youtu.be/abc"
        assert clip["title"] == "Thiruppavai"
        assert clip["channel"] == "M S Subbulakshmi"

    def test_a_sidecar_written_before_the_top_line_existed_still_reads(self, app, out):
        """Old clips have no `topline` key. Re-opening one must not fail, and the
        page must not put the previous clip's top text on it either."""
        (out / "20260818_thiruppavai_70-85.json").write_text(
            json.dumps({
                "url": "https://youtu.be/abc", "start": 70.0, "end": 85.0,
                "video": True, "wave": True, "title": "Thiruppavai",
                "channel": "M S Subbulakshmi", "footer": "", "eyebrow": "",
            }),
            encoding="utf-8",
        )
        job = app.clip_json("20260818_thiruppavai_70-85")["job"]
        assert job.get("topline", "") == ""

    def test_a_clip_from_before_the_sidecar_existed_still_shows(self, app):
        clip = app.clip_json("20260818_thiruppavai_70-85")
        assert clip["job"] == {}
        assert clip["title"] == ""

    def test_a_corrupt_sidecar_is_ignored_not_fatal(self, app, out):
        (out / "20260818_thiruppavai_70-85.json").write_text("{oh no", encoding="utf-8")
        assert app.clip_json("20260818_thiruppavai_70-85")["job"] == {}

    def test_the_date_it_was_made_is_reported(self, app):
        assert app.clip_json("20260818_thiruppavai_70-85")["created"] > 0


class TestStickers:
    @pytest.fixture(autouse=True)
    def library(self, tmp_path, monkeypatch):
        from PIL import Image

        from wastatus import stickers

        monkeypatch.setenv("WASTATUS_STICKER_DIR", str(tmp_path / "stickers"))
        stickers._catalogue.cache_clear()
        (tmp_path / "stickers" / "openmoji").mkdir(parents=True)
        Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(
            tmp_path / "stickers" / "openmoji" / "1FA94.png"
        )
        (tmp_path / "stickers" / "openmoji.json").write_text(
            '[{"hexcode": "1FA94", "annotation": "diya lamp", "tags": "oil",'
            ' "openmoji_tags": "", "subgroups": "light", "group": "objects",'
            ' "order": 1, "skintone": ""}]',
            encoding="utf-8",
        )
        yield
        stickers._catalogue.cache_clear()

    def test_searching_returns_matches(self, base, app):
        status, body = fetch(f"{base}/api/stickers?q=diya", token=app.token)
        assert status == 200
        assert body["installed"] is True
        assert body["stickers"] == [
            {"id": "openmoji:1FA94", "name": "diya lamp", "mine": False,
             "moving": False}
        ]

    def test_a_search_term_with_a_space_survives_the_query_string(self, base, app):
        status, body = fetch(f"{base}/api/stickers?q=diya+lamp", token=app.token)
        assert status == 200
        assert len(body["stickers"]) == 1

    def test_an_image_is_served_with_the_token_in_the_url(self, base, app):
        status, body = fetch(f"{base}/api/sticker?id=openmoji%3A1FA94&t={app.token}")
        assert status == 200
        assert body[:4] == b"\x89PNG"

    def test_an_image_without_a_token_is_refused(self, base):
        status, _ = fetch(f"{base}/api/sticker?id=openmoji%3A1FA94")
        assert status == 403

    def test_an_id_that_walks_out_of_the_folder_finds_nothing(self, base, app):
        status, _ = fetch(
            f"{base}/api/sticker?id=openmoji%3A..%2F..%2F..%2Fetc%2Fpasswd&t={app.token}"
        )
        assert status == 404

    def test_a_render_carries_its_stickers_into_the_job(self, base, app, monkeypatch):
        jobs = []
        monkeypatch.setattr(
            serve.App, "render",
            lambda self, job, follow_up: jobs.append(job) or serve.Task(id="x", kind="render"),
        )
        fetch(
            f"{base}/api/render", token=app.token, method="POST",
            body={
                "url": "https://youtu.be/abc",
                "stickers": [{"id": "openmoji:1FA94", "x": 0.2, "y": 0.8, "size": 0.3}],
            },
        )
        assert [decal.id for decal in jobs[0].decals] == ["openmoji:1FA94"]
        assert jobs[0].decals[0].x == 0.2

    def test_a_render_with_a_bad_sticker_is_refused_before_anything_starts(
        self, base, app, monkeypatch
    ):
        monkeypatch.setattr(
            serve.App, "render",
            lambda *a, **k: pytest.fail("a bad sticker reached the pipeline"),
        )
        status, body = fetch(
            f"{base}/api/render", token=app.token, method="POST",
            body={"url": "https://youtu.be/abc",
                  "stickers": [{"id": "openmoji:../../../etc/passwd"}]},
        )
        assert status == 400
        assert "sticker id" in body["error"]

    def test_uploading_one(self, base, app):
        import base64
        import io

        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGBA", (32, 32), (9, 9, 9, 255)).save(buffer, "PNG")
        status, body = fetch(
            f"{base}/api/sticker", token=app.token, method="POST",
            body={"name": "my cat", "data": base64.b64encode(buffer.getvalue()).decode()},
        )
        assert status == 200
        assert body == {
            "id": "mine:my-cat", "name": "my cat", "mine": True, "moving": False,
        }

    def test_uploading_something_that_is_not_an_image_is_refused(self, base, app):
        import base64

        status, body = fetch(
            f"{base}/api/sticker", token=app.token, method="POST",
            body={"name": "bad", "data": base64.b64encode(b"rm -rf /").decode()},
        )
        assert status == 400
        assert "image" in body["error"]

    def test_uploading_needs_the_token(self, base):
        status, _ = fetch(
            f"{base}/api/sticker", method="POST", body={"name": "x", "data": "y"}
        )
        assert status == 403

    def test_the_library_cannot_be_deleted(self, base, app):
        status, body = fetch(
            f"{base}/api/sticker/delete", token=app.token, method="POST",
            body={"id": "openmoji:1FA94"},
        )
        assert status == 400
        assert "your own" in body["error"]

    def test_the_page_is_told_where_whatsapp_draws(self, base, app):
        """The guides in the page and the safe zone in the renderer are the same two
        numbers, sent from the one file that defines them."""
        from wastatus import compose

        _, body = fetch(f"{base}/api/state", token=app.token)
        assert body["bands"]["top"] == round(compose.SAFE_TOP / compose.HEIGHT, 4)
        assert body["bands"]["bottom"] == round(
            1 - compose.SAFE_BOTTOM / compose.HEIGHT, 4
        )

    def test_the_page_is_told_which_machine_this_is(self, base, app):
        """From a phone, "WhatsApp Web is ready" begs the question "on what". The
        page answers it with the name the laptop calls itself."""
        import socket

        _, body = fetch(f"{base}/api/state", token=app.token)
        assert body["host"] == socket.gethostname()
        assert body["host"], "a machine with no name tells the phone nothing"


class TestTheLog:
    """The token is the one secret this server holds. It travels in the query string
    for media, because an <img> cannot send a header, so it must not travel into a
    file that outlives the process."""

    def test_the_token_is_not_written_to_the_log(self, base, app, caplog):
        import logging

        with caplog.at_level(logging.DEBUG, logger="wastatus"):
            fetch(f"{base}/api/clip?stem=..&t={app.token}")
        assert caplog.text, "the request was not logged at all"
        assert app.token not in caplog.text
        assert "t=REDACTED" in caplog.text

    def test_polling_does_not_fill_the_log(self, base, app, caplog):
        """A day of health polling wrote 150 kB of "GET /api/state 200"."""
        import logging

        with caplog.at_level(logging.DEBUG, logger="wastatus"):
            fetch(f"{base}/api/state", token=app.token)
        assert "/api/state" not in caplog.text

    def test_a_failing_poll_is_still_logged(self, base, caplog):
        import logging

        with caplog.at_level(logging.DEBUG, logger="wastatus"):
            fetch(f"{base}/api/state")
        assert "/api/state" in caplog.text


class TestTheBrowser:
    def test_the_icon_is_served(self, base):
        status, body = fetch(f"{base}/favicon.svg")
        assert status == 200
        assert b"<svg" in body

    def test_the_habitual_ico_request_gets_the_same_icon(self, base):
        status, body = fetch(f"{base}/favicon.ico")
        assert status == 200
        assert b"<svg" in body

    def test_one_can_be_started_when_none_is_running(self, base, app, monkeypatch):
        monkeypatch.setattr(
            post, "discover",
            lambda *a, **k: (_ for _ in ()).throw(post.PostError("nothing there")),
        )
        # Which ports this machine happens to have open is not what is under
        # test, and a developer with a debug browser running would fail this.
        monkeypatch.setattr(post, "in_use", lambda port: False)
        monkeypatch.setattr(post, "running_profile_port", lambda profile=None: None)
        started: list[int] = []
        monkeypatch.setattr(post, "launch_browser", lambda port, first=None, page="": started.append(port) or "chrome")
        status, body = fetch(f"{base}/api/browser", token=app.token, method="POST", body={})
        assert status == 200
        assert started == [9222]
        assert body["binary"] == "chrome"

    def test_a_second_browser_is_not_started_over_a_working_one(self, base, app, monkeypatch):
        monkeypatch.setattr(
            post, "launch_browser",
            lambda port, first=None, page="": pytest.fail("a browser was already there"),
        )
        status, body = fetch(f"{base}/api/browser", token=app.token, method="POST", body={})
        assert status == 409

    def test_starting_a_browser_needs_the_token(self, base):
        status, _ = fetch(f"{base}/api/browser", method="POST", body={})
        assert status == 403


def _settle(base: str, app: serve.App, task_id: str, tries: int = 100) -> dict:
    """Poll a task until it stops running, the way the page does."""
    import time

    for _ in range(tries):
        status, task = fetch(f"{base}/api/task?id={task_id}", token=app.token)
        assert status == 200
        if task["status"] != "running":
            return task
        time.sleep(0.05)
    raise AssertionError("task never finished")


def test_old_tasks_do_not_accumulate_forever(app, monkeypatch):
    """A page left open all week should not hold every task it ever ran."""
    monkeypatch.setattr(serve.App, "KEEP_TASKS", 5)
    for _ in range(12):
        app.start("render", lambda task: {})
    assert len(app.tasks) <= 5


class TestStartingUp:
    def test_a_port_outside_the_range_fails_cleanly(self, capsys, tmp_path):
        """A typo in --port should be a message, not a traceback."""
        code = serve.main(["--port", "99999", "--no-open", "-o", str(tmp_path)])
        assert code == 1
        assert "cannot listen" in capsys.readouterr().out

    def test_a_busy_port_fails_cleanly(self, capsys, tmp_path, app):
        server = serve.make_server(app, port=0)
        try:
            port = server.server_address[1]
            code = serve.main(["--port", str(port), "--no-open", "-o", str(tmp_path)])
            assert code == 1
            assert "already be serving" in capsys.readouterr().out
        finally:
            server.server_close()


class TestStoppingARender:
    """A wrong paste used to cost two minutes of waiting. See TASKS.md T-015."""

    def _slow_render(self, monkeypatch, marker: Path):
        """Stand `pipeline.produce` up as a real child, so the cancel has something
        to kill rather than a flag to flip."""
        def slow(job, run, progress=None):
            proc.run_child([
                sys.executable, "-c",
                f"import pathlib, time;"
                f" pathlib.Path({str(marker)!r}).write_text('x'); time.sleep(30)",
            ])
            raise AssertionError("the child ran to completion, so nothing stopped it")

        monkeypatch.setattr(serve.pipeline, "produce", slow)

    def _start(self, base, app):
        status, body = fetch(
            f"{base}/api/render", token=app.token, method="POST",
            body={"url": "https://youtu.be/abc", "start": "0:10", "duration": 15},
        )
        assert status == 200
        return body["id"]

    def test_a_running_render_can_be_stopped(self, base, app, monkeypatch, tmp_path):
        marker = tmp_path / "started"
        self._slow_render(monkeypatch, marker)
        task_id = self._start(base, app)

        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists(), "the render never got as far as a child"

        status, body = fetch(
            f"{base}/api/cancel", token=app.token, method="POST", body={"id": task_id},
        )
        assert status == 200
        assert body["stopping"] is True

        task = _settle(base, app, task_id)
        assert task["status"] == "cancelled"
        assert task["error"] == ""          # stopping is not failing
        assert task["can_stop"] is False

    def test_a_running_render_says_it_can_be_stopped(
        self, base, app, monkeypatch, tmp_path
    ):
        self._slow_render(monkeypatch, tmp_path / "started")
        task_id = self._start(base, app)
        status, task = fetch(f"{base}/api/task?id={task_id}", token=app.token)
        assert status == 200
        assert task["can_stop"] is True
        fetch(f"{base}/api/cancel", token=app.token, method="POST", body={"id": task_id})
        _settle(base, app, task_id)

    def test_a_finished_render_cannot_be_stopped(self, base, app, monkeypatch):
        monkeypatch.setattr(serve.pipeline, "produce", lambda *a, **k: 1 / 0)
        task_id = self._start(base, app)
        _settle(base, app, task_id)
        status, body = fetch(
            f"{base}/api/cancel", token=app.token, method="POST", body={"id": task_id},
        )
        assert status == 409
        assert "already" in body["error"]

    def test_a_post_cannot_be_stopped(self, base, app, monkeypatch):
        """Killing a driver halfway through an upload leaves WhatsApp in a state
        this tool cannot describe, let alone undo."""
        monkeypatch.setattr(post, "post_video", lambda *a, **k: time.sleep(2) or 1.0)
        _, body = fetch(
            f"{base}/api/post", token=app.token, method="POST",
            body={"stem": "20260818_thiruppavai_70-85", "send": False},
        )
        status, refused = fetch(
            f"{base}/api/cancel", token=app.token, method="POST", body={"id": body["id"]},
        )
        assert status == 409
        assert "cannot be stopped" in refused["error"]
        _settle(base, app, body["id"])

    def test_an_unknown_task_is_a_404(self, base, app):
        status, _ = fetch(
            f"{base}/api/cancel", token=app.token, method="POST", body={"id": "nope"},
        )
        assert status == 404

    def test_stopping_needs_the_token(self, base, app):
        status, _ = fetch(f"{base}/api/cancel", method="POST", body={"id": "x"})
        assert status == 403


class TestDeletingAClip:
    """See TASKS.md T-016. Clearing a bad take should not need a terminal."""

    STEM = "20260818_thiruppavai_70-85"

    def test_the_whole_group_goes_not_just_the_mp4(self, base, app, out):
        (out / f"{self.STEM}.json").write_text("{}", encoding="utf-8")
        status, body = fetch(
            f"{base}/api/clip/delete", token=app.token, method="POST",
            body={"stem": self.STEM},
        )
        assert status == 200
        assert body["deleted"] == self.STEM
        assert body["files"] == 4       # mp4, caption, png, json
        assert list(out.glob(f"{self.STEM}*")) == []

    def test_the_clip_leaves_the_recent_strip(self, base, app):
        fetch(
            f"{base}/api/clip/delete", token=app.token, method="POST",
            body={"stem": self.STEM},
        )
        _, state = fetch(f"{base}/api/state", token=app.token)
        assert state["clips"] == []

    def test_deleting_something_that_is_not_there_is_a_404(self, base, app):
        status, _ = fetch(
            f"{base}/api/clip/delete", token=app.token, method="POST",
            body={"stem": "20260101_nothing_0-1"},
        )
        assert status == 404

    def test_a_name_with_a_path_in_it_is_refused(self, base, app):
        status, body = fetch(
            f"{base}/api/clip/delete", token=app.token, method="POST",
            body={"stem": "../../etc/passwd"},
        )
        assert status == 400
        assert "bad clip name" in body["error"]

    def test_nothing_is_deleted_while_whatsapp_is_being_driven(
        self, base, app, monkeypatch, out
    ):
        """The composer may be holding this very file open."""
        monkeypatch.setattr(post, "post_video", lambda *a, **k: time.sleep(2) or 1.0)
        _, started = fetch(
            f"{base}/api/post", token=app.token, method="POST",
            body={"stem": self.STEM, "send": False},
        )
        status, body = fetch(
            f"{base}/api/clip/delete", token=app.token, method="POST",
            body={"stem": self.STEM},
        )
        assert status == 409
        assert "Wait for that to finish" in body["error"]
        assert (out / f"{self.STEM}.mp4").is_file()
        _settle(base, app, started["id"])

    def test_deleting_needs_the_token(self, base, app, out):
        status, _ = fetch(
            f"{base}/api/clip/delete", method="POST", body={"stem": self.STEM},
        )
        assert status == 403
        assert (out / f"{self.STEM}.mp4").is_file()


class TestDownloading:
    """The route that lets a phone take the clip and post it in the real app."""

    STEM = "20260818_thiruppavai_70-85"

    def _headers(self, base, app, query=""):
        request = urllib.request.Request(
            f"{base}/api/clip?stem={self.STEM}&t={app.token}{query}"
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return dict(response.headers), response.read()

    def test_asking_for_a_download_offers_it_as_a_file(self, base, app):
        headers, body = self._headers(base, app, "&download=1")
        assert headers["Content-Disposition"] == f'attachment; filename="{self.STEM}.mp4"'
        assert body == b"not really an mp4"

    def test_playing_it_in_the_page_is_not_a_download(self, base, app):
        headers, _ = self._headers(base, app)
        assert "Content-Disposition" not in headers

    def test_a_download_still_answers_ranges(self, base, app):
        """The header must not cost the page its seek slider."""
        status, headers, body = fetch_range(
            f"{base}/api/clip?stem={self.STEM}&download=1", app.token, "bytes=4-8"
        )
        assert status == 206
        assert headers["Content-Disposition"].startswith("attachment")
        assert body == b"really"[:5]


class TestWhereThePageWasOpened:
    def test_a_loopback_request_is_local(self, base, app):
        """Which button is the big one comes from the connection, not the browser's
        user agent: the tailnet address can be opened on the laptop too."""
        _, state = fetch(f"{base}/api/state", token=app.token)
        assert state["local"] is True

    def test_a_request_from_elsewhere_is_not(self, app):
        handler = _handler(
            app, host="100.64.0.1:8765", origin=None, token=app.token
        )
        handler.client_address = ("100.64.0.2", 51234)
        assert handler._local() is False

    def test_an_unreadable_peer_is_treated_as_elsewhere(self, app):
        handler = _handler(app, host="x:8765", origin=None, token=app.token)
        handler.client_address = ("", 0)
        assert handler._local() is False

    def test_the_page_says_where_else_it_can_be_reached(self, out):
        app = serve.App(out=out, cdp_port=9222, keep_last=20, also_on="100.64.0.1")
        assert app.state()["also_on"] == "100.64.0.1"

    def test_nothing_is_advertised_by_default(self, app):
        assert app.state()["also_on"] == ""


class TestBindingSomewhereElse:
    def test_an_address_is_taken_as_it_is(self):
        assert serve.resolve_host("127.0.0.2") == "127.0.0.2"

    def test_a_name_is_refused(self):
        """A name resolved once here would not match the `Host` a browser sends,
        which is what the origin check compares against."""
        with pytest.raises(ValueError, match="not 'my-laptop'"):
            serve.resolve_host("my-laptop")

    def test_tailscale_is_asked_for_the_address(self, monkeypatch):
        monkeypatch.setattr(serve.shutil, "which", lambda name: "/usr/bin/tailscale")
        monkeypatch.setattr(
            serve.subprocess, "run",
            lambda *a, **k: serve.subprocess.CompletedProcess(a[0], 0, "100.64.0.7\n", ""),
        )
        assert serve.resolve_host("tailscale") == "100.64.0.7"

    def test_a_missing_tailscale_says_so(self, monkeypatch):
        monkeypatch.setattr(serve.shutil, "which", lambda name: None)
        with pytest.raises(ValueError, match="not installed"):
            serve.resolve_host("tailscale")

    def test_a_tailscale_that_is_not_logged_in_says_so(self, monkeypatch):
        monkeypatch.setattr(serve.shutil, "which", lambda name: "/usr/bin/tailscale")
        monkeypatch.setattr(
            serve.subprocess, "run",
            lambda *a, **k: serve.subprocess.CompletedProcess(a[0], 1, "", "not logged in"),
        )
        with pytest.raises(ValueError, match="running and logged in"):
            serve.resolve_host("tailscale")

    def test_a_bad_address_fails_before_anything_is_bound(self, capsys, tmp_path):
        code = serve.main(
            ["--also-on", "my-laptop", "--no-open", "-o", str(tmp_path), "--port", "0"]
        )
        assert code == 1
        assert "takes an address" in capsys.readouterr().out

    def test_loopback_is_always_bound_as_well(self, app):
        """Binding one address only would leave the laptop reaching its own page
        over the tailnet, where it cannot be told apart from the phone.

        Linux puts the whole of 127.0.0.0/8 on the loopback interface, so any
        address in it can be bound. macOS configures 127.0.0.1 alone, and nothing
        here is worth asking somebody to run `ifconfig lo0 alias` for: the second
        address in real use is a tailnet address on a real interface.
        """
        try:
            second = serve.make_server(app, port=0, host="127.0.0.2")
        except OSError:  # pragma: no cover - not the test platform
            pytest.skip("only 127.0.0.1 is on loopback here, as it is on macOS")
        try:
            assert second.server_address[0] == "127.0.0.2"
        finally:
            second.server_close()

    def test_an_ipv6_url_is_bracketed(self):
        assert serve.url_for("::1", 8765) == "http://[::1]:8765/"
        assert serve.url_for("127.0.0.1", 8765) == "http://127.0.0.1:8765/"


class TestTheBodyCeiling:
    """A caller holding the token can still not make this process hold a gigabyte.

    The token is not a strong boundary here: anyone who can open the page over
    `--also-on` has it. So the size of a request body is capped rather than trusted.
    """

    def test_a_body_larger_than_the_ceiling_is_not_read(self, base, app):
        status, body = fetch(
            f"{base}/api/sticker", token=app.token, method="POST",
            body={"name": "huge", "data": "A" * (serve.MAX_BODY_BYTES + 100)},
        )
        assert status == 413
        assert "too big" in body["error"]

    def test_the_ceiling_clears_the_largest_real_sticker(self):
        from wastatus import stickers

        as_base64 = stickers.ANIMATED_MAX_BYTES * 4 // 3
        assert serve.MAX_BODY_BYTES > as_base64 + 1000, (
            "an animated sticker at the documented limit has to fit through"
        )


class TestControlCheck:
    """T-026: the answer is asked for once and remembered for the run.

    The check reaches into the browser the owner is looking at, so the thing that
    matters here is restraint: not on the poll, not while something else is driving
    that browser, and not twice.
    """

    def test_it_is_asked_once_and_then_remembered(self, base, app, monkeypatch):
        asked = []
        monkeypatch.setattr(
            post, "check_controls",
            lambda port: (asked.append(port), {"ok": True, "checked": True})[1])

        first = fetch(f"{base}/api/controls", token=app.token)
        second = fetch(f"{base}/api/controls", token=app.token)
        assert first == second
        assert len(asked) == 1, f"the browser was reached into {len(asked)} times"

    def test_the_poll_never_triggers_it(self, base, app, monkeypatch):
        monkeypatch.setattr(
            post, "check_controls",
            lambda port: pytest.fail("/api/state must never open a menu"))
        status, _ = fetch(f"{base}/api/state", token=app.token)
        assert status == HTTPStatus.OK

    def test_a_rename_is_reported_rather_than_swallowed(self, base, app, monkeypatch):
        monkeypatch.setattr(post, "check_controls", lambda port: {
            "ok": False, "checked": True, "detail": "WhatsApp has moved something"})
        status, payload = fetch(f"{base}/api/controls", token=app.token)
        assert status == HTTPStatus.OK
        assert payload["ok"] is False
        assert "moved" in payload["detail"]

    def test_it_keeps_out_of_the_way_while_the_browser_is_driven(
            self, base, app, monkeypatch):
        monkeypatch.setattr(
            post, "check_controls",
            lambda port: pytest.fail("reached into a browser that was already busy"))

        class Busy:
            kind, status = "post", "running"

        app.tasks["busy"] = Busy()
        try:
            status, payload = fetch(f"{base}/api/controls", token=app.token)
        finally:
            app.tasks.pop("busy", None)
        assert status == HTTPStatus.OK
        assert payload["ok"] is True and payload["checked"] is False

    def test_it_needs_the_token_like_everything_else(self, base):
        status, _ = fetch(f"{base}/api/controls")
        assert status == HTTPStatus.FORBIDDEN


class TestGifRoutes:
    """The picker's server side. The guard worth testing is what it will fetch.

    A caller holding the token could otherwise name any address and have this
    process download it. It cannot: a pick names an id from a search this server
    itself made, and the address is looked up here rather than sent by the browser.
    """

    @pytest.fixture
    def on(self, monkeypatch):
        monkeypatch.setattr(gifs, "provider", lambda: "giphy")
        monkeypatch.setattr(gifs, "enabled", lambda: True)
        monkeypatch.setattr(gifs, "credit", lambda: {
            "provider": "giphy", "label": "Powered by GIPHY",
            "placeholder": "Search GIPHY", "url": "https://giphy.com"})
        monkeypatch.setattr(gifs, "search", lambda q, limit=30, large=False: [
            gifs.Gif(id="abc", title="Thanks", preview="https://x/s.gif",
                     full="https://x/f.gif", width=480, height=270, bytes=4000)])

    def test_the_state_says_nothing_when_the_feature_is_off(self, base, app,
                                                            monkeypatch):
        monkeypatch.setattr(gifs, "credit", lambda: {})
        _, payload = fetch(f"{base}/api/state", token=app.token)
        assert payload["gifs"] == {}, "the page would draw a toggle that answers 404"

    def test_search_is_refused_while_the_feature_is_off(self, base, app, monkeypatch):
        monkeypatch.setattr(gifs, "enabled", lambda: False)
        status, _ = fetch(f"{base}/api/gifs?q=hi", token=app.token)
        assert status == HTTPStatus.NOT_FOUND

    def test_a_search_returns_results_and_the_credit(self, base, app, on):
        status, payload = fetch(f"{base}/api/gifs?q=thanks", token=app.token)
        assert status == HTTPStatus.OK
        assert payload["credit"]["placeholder"] == "Search GIPHY"
        assert [one["id"] for one in payload["gifs"]] == ["abc"]
        assert "full" not in payload["gifs"][0], (
            "the address must stay on the server, so nothing can be swapped for it")

    def test_a_provider_outage_is_a_sentence_not_a_traceback(self, base, app,
                                                             monkeypatch, on):
        monkeypatch.setattr(gifs, "search", lambda q, limit=30, large=False: (_ for _ in ()).throw(
            gifs.GifError("could not reach the GIF service")))
        status, payload = fetch(f"{base}/api/gifs?q=thanks", token=app.token)
        assert status == HTTPStatus.BAD_GATEWAY
        assert "could not reach" in payload["error"]

    def test_picking_something_never_offered_is_refused(self, base, app, on,
                                                        monkeypatch):
        def refuse(*_a, **_k):
            pytest.fail("this server fetched an address the browser chose")

        monkeypatch.setattr(gifs, "fetch", refuse)
        status, payload = fetch(f"{base}/api/gif/pick", token=app.token,
                                method="POST", body={"id": "https://evil/x.gif"})
        assert status == HTTPStatus.NOT_FOUND
        assert "no longer on offer" in payload["error"]

    def test_a_pick_downloads_the_offered_address_and_keeps_it(self, base, app, on,
                                                               monkeypatch):
        asked = []
        monkeypatch.setattr(gifs, "fetch",
                            lambda url, ceiling: (asked.append(url), b"GIF89a")[1])
        monkeypatch.setattr(stickers, "save_gif",
                            lambda provider, ident, title, data: {
                                "id": f"gif:{provider}-{ident}", "name": title,
                                "mine": True, "moving": True})

        fetch(f"{base}/api/gifs?q=thanks", token=app.token)   # puts it on offer
        status, payload = fetch(f"{base}/api/gif/pick", token=app.token,
                                method="POST", body={"id": "abc"})
        assert status == HTTPStatus.OK
        assert payload["id"] == "gif:giphy-abc"
        assert asked == ["https://x/f.gif"], (
            "it must fetch the full copy, not the shelf thumbnail")

    def test_the_preview_is_proxied_rather_than_linked(self, base, app, on,
                                                       monkeypatch):
        """The phone reads this page over a tailnet and must not meet the provider."""
        monkeypatch.setattr(gifs, "fetch", lambda url, ceiling: b"GIF89a-preview")
        fetch(f"{base}/api/gifs?q=thanks", token=app.token)
        status, raw = fetch(f"{base}/api/gif?id=abc", token=app.token)
        assert status == HTTPStatus.OK
        assert raw == b"GIF89a-preview"

    def test_the_gif_routes_need_the_token(self, base, app, on):
        for url in (f"{base}/api/gifs?q=hi", f"{base}/api/gif?id=abc"):
            status, _ = fetch(url)
            assert status == HTTPStatus.FORBIDDEN, url

    def test_the_preview_takes_its_token_in_the_query(self, base, app, on,
                                                      monkeypatch):
        """An `<img src>` cannot send a header, so it has to be the `t=` parameter.

        Missed on the first pass: the shelf rendered thirty cells and every one of
        them was a 403, which looks like a provider fault and is not one. Found by
        counting `naturalWidth` in a real browser rather than by reading the code.
        """
        monkeypatch.setattr(gifs, "fetch", lambda url, ceiling: b"GIF89a-preview")
        fetch(f"{base}/api/gifs?q=thanks", token=app.token)
        status, raw = fetch(f"{base}/api/gif?id=abc&t={app.token}")
        assert status == HTTPStatus.OK, "the shelf cannot show a thumbnail it cannot load"
        assert raw == b"GIF89a-preview"


class TestSettingsThatComeFromTheEnvironment:
    """One command, because retyping the same two flags every day is friction.

    `.env` answers both, and an explicit flag still overrules it: the point of
    typing one is to mean something different for this run only. D-044, T-032.
    """

    def test_nothing_set_is_loopback_only_and_starts_no_browser(self, monkeypatch):
        monkeypatch.delenv(serve.ALSO_ON_ENV, raising=False)
        monkeypatch.delenv(serve.BROWSER_ENV, raising=False)
        args = serve.build_parser().parse_args([])
        assert args.also_on == ""
        assert serve.wanted(args.start_browser, serve.BROWSER_ENV) is False

    def test_the_file_can_ask_for_the_tailnet_and_a_browser(self, monkeypatch):
        monkeypatch.setenv(serve.ALSO_ON_ENV, "tailscale")
        monkeypatch.setenv(serve.BROWSER_ENV, "1")
        args = serve.build_parser().parse_args([])
        assert args.also_on == "tailscale"
        assert serve.wanted(args.start_browser, serve.BROWSER_ENV) is True

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_the_words_that_mean_yes(self, value, monkeypatch):
        monkeypatch.setenv(serve.BROWSER_ENV, value)
        assert serve.wanted(None, serve.BROWSER_ENV) is True

    @pytest.mark.parametrize("value", ["", "0", "no", "off", "maybe"])
    def test_everything_else_means_no(self, value, monkeypatch):
        """Including a typo. A setting that guesses is a setting that surprises."""
        monkeypatch.setenv(serve.BROWSER_ENV, value)
        assert serve.wanted(None, serve.BROWSER_ENV) is False

    def test_a_flag_on_the_command_line_beats_the_file(self, monkeypatch):
        monkeypatch.setenv(serve.BROWSER_ENV, "1")
        args = serve.build_parser().parse_args(["--no-start-browser"])
        assert serve.wanted(args.start_browser, serve.BROWSER_ENV) is False
        monkeypatch.setenv(serve.BROWSER_ENV, "0")
        args = serve.build_parser().parse_args(["--start-browser"])
        assert serve.wanted(args.start_browser, serve.BROWSER_ENV) is True

    def test_an_address_on_the_command_line_beats_the_file(self, monkeypatch):
        monkeypatch.setenv(serve.ALSO_ON_ENV, "tailscale")
        args = serve.build_parser().parse_args(["--also-on", "100.64.0.1"])
        assert args.also_on == "100.64.0.1"

    def test_an_empty_address_overrules_the_file_back_to_loopback(self, monkeypatch):
        """The escape hatch D-027's amendment promises: one run, loopback only."""
        monkeypatch.setenv(serve.ALSO_ON_ENV, "tailscale")
        args = serve.build_parser().parse_args(["--also-on", ""])
        assert args.also_on == ""


class TestStartingTheBrowserAtStartup:
    """`ensure_browser` is never allowed to stop the page coming up."""

    def test_an_existing_browser_is_left_alone(self, app, monkeypatch):
        monkeypatch.setattr(
            app, "whatsapp_state",
            lambda fresh=False: {"ready": True, "detail": "Chrome on port 9230", "port": 9230},
        )
        started: list[int] = []
        monkeypatch.setattr(post, "launch_browser", lambda port, first=None, page="": started.append(port))
        serve.ensure_browser(app)
        assert started == []

    def test_one_is_started_when_there_is_none(self, app, monkeypatch):
        monkeypatch.setattr(app, "whatsapp_state", lambda fresh=False: {"ready": False})
        monkeypatch.setattr(post, "in_use", lambda port: False)
        monkeypatch.setattr(post, "running_profile_port", lambda profile=None: None)
        started: list[int] = []
        monkeypatch.setattr(
            post, "launch_browser", lambda port, first=None, page="": started.append(port) or "/usr/bin/chrome"
        )
        serve.ensure_browser(app)
        assert started == [app.cdp_port]

    def test_a_browser_that_cannot_be_started_is_reported_not_raised(self, app, monkeypatch):
        """No Chrome on the machine is a reason to lose posting, not the page."""
        monkeypatch.setattr(app, "whatsapp_state", lambda fresh=False: {"ready": False})
        monkeypatch.setattr(post, "in_use", lambda port: False)
        monkeypatch.setattr(post, "running_profile_port", lambda profile=None: None)
        monkeypatch.setattr(
            post, "launch_browser",
            lambda port, first=None, page="": (_ for _ in ()).throw(post.PostError("no Chrome on PATH")),
        )
        serve.ensure_browser(app)  # does not raise

    def test_a_taken_port_is_stepped_over_and_becomes_the_new_preference(self, app, monkeypatch):
        """Starting on a held port is the half open trap: Chrome binds IPv6 only."""
        monkeypatch.setattr(post, "in_use", lambda port: port == app.cdp_port)
        monkeypatch.setattr(post, "running_profile_port", lambda profile=None: None)
        monkeypatch.setattr(post, "free_port", lambda ports=None: 9241)
        started: list[int] = []
        monkeypatch.setattr(
            post, "launch_browser", lambda port, first=None, page="": started.append(port) or "chrome"
        )
        app.start_browser()
        assert started == [9241]
        assert app.cdp_port == 9241

    def test_a_browser_already_on_our_profile_is_adopted_rather_than_duplicated(
        self, app, monkeypatch
    ):
        """Chrome hands a second launch on one profile to the first and exits, so
        launching again would open a window and expose no protocol at all."""
        monkeypatch.setattr(post, "running_profile_port", lambda profile=None: 9222)
        monkeypatch.setattr(
            app, "whatsapp_state",
            lambda fresh=False: {"ready": True, "detail": "x", "port": 9222}
        )
        started: list[int] = []
        monkeypatch.setattr(post, "launch_browser", lambda port, first=None, page="": started.append(port))
        found = app.start_browser()
        assert started == []
        assert found["adopted"] is True
        assert app.cdp_port == 9222

    def test_an_adopted_browser_without_whatsapp_says_to_open_it_there(
        self, app, monkeypatch
    ):
        monkeypatch.setattr(post, "running_profile_port", lambda profile=None: 9222)
        monkeypatch.setattr(app, "whatsapp_state", lambda fresh=False: {"ready": False})
        with pytest.raises(post.PostError) as raised:
            app.start_browser()
        assert "9222" in str(raised.value)
        assert app.cdp_port == 9222


class TestWhereThePageOpens:
    """The page belongs in the window that holds the rest of this session.

    It used to go to whatever the desktop calls the default browser, which on this
    machine is a different Chrome entirely: the tool's own page ended up nowhere
    near the label tab naming its port, or the WhatsApp tab it posts through.
    """

    def test_a_browser_we_start_gets_the_page_on_its_command_line(
        self, app, monkeypatch
    ):
        """No protocol call: Chrome opens it as a tab because it was asked to."""
        monkeypatch.setattr(app, "whatsapp_state", lambda fresh=False: {"ready": False})
        monkeypatch.setattr(post, "in_use", lambda port: False)
        monkeypatch.setattr(post, "running_profile_port", lambda profile=None: None)
        asked: list[str] = []
        monkeypatch.setattr(
            post, "launch_browser",
            lambda port, first=None, page="": asked.append(page) or "/usr/bin/chrome",
        )
        monkeypatch.setattr(
            post, "open_tab", lambda *a, **k: pytest.fail("no tab call is needed")
        )
        monkeypatch.setattr(
            serve.webbrowser, "open", lambda url: pytest.fail("not the default browser")
        )
        serve.ensure_browser(app, page_url="http://127.0.0.1:8765/")
        assert asked == ["http://127.0.0.1:8765/"]

    def test_a_browser_already_running_is_asked_over_the_protocol(
        self, app, monkeypatch
    ):
        """It never saw our command line, so the tab has to be asked for."""
        monkeypatch.setattr(
            app, "whatsapp_state",
            lambda fresh=False: {"ready": True, "detail": "x", "port": 9241},
        )
        tabs: list[tuple[int, str]] = []
        monkeypatch.setattr(post, "open_tab", lambda port, url: tabs.append((port, url)))
        monkeypatch.setattr(
            serve.webbrowser, "open", lambda url: pytest.fail("not the default browser")
        )
        serve.ensure_browser(app, page_url="http://127.0.0.1:8765/")
        assert tabs == [(9241, "http://127.0.0.1:8765/")]

    def test_a_browser_that_could_not_be_started_still_gets_you_the_page(
        self, app, monkeypatch
    ):
        """No Chrome on the machine costs you posting. It must not also cost you
        the page, which is the half of this tool that works without one."""
        monkeypatch.setattr(app, "whatsapp_state", lambda fresh=False: {"ready": False})
        monkeypatch.setattr(post, "in_use", lambda port: False)
        monkeypatch.setattr(post, "running_profile_port", lambda profile=None: None)
        monkeypatch.setattr(
            post, "launch_browser",
            lambda port, first=None, page="": (_ for _ in ()).throw(
                post.PostError("no Chrome on PATH")
            ),
        )
        opened: list[str] = []
        monkeypatch.setattr(serve.webbrowser, "open", opened.append)
        serve.ensure_browser(app, page_url="http://127.0.0.1:8765/")
        assert opened == ["http://127.0.0.1:8765/"]

    def test_a_tab_that_will_not_open_falls_back_rather_than_failing(
        self, app, monkeypatch
    ):
        """A browser can be answering `discover` and still refuse a new tab. The
        page opening somewhere beats an error about where it did not."""
        opened: list[str] = []
        monkeypatch.setattr(
            post, "open_tab",
            lambda port, url: (_ for _ in ()).throw(post.PostError("refused")),
        )
        monkeypatch.setattr(serve.webbrowser, "open", opened.append)
        serve.show_page("http://127.0.0.1:8765/", 9241)
        assert opened == ["http://127.0.0.1:8765/"]

    def test_no_open_means_no_open_anywhere(self, app, monkeypatch):
        monkeypatch.setattr(
            post, "open_tab", lambda *a, **k: pytest.fail("--no-open was given")
        )
        monkeypatch.setattr(
            serve.webbrowser, "open", lambda url: pytest.fail("--no-open was given")
        )
        serve.show_page("", 9241)


class TestChoosingTheGifProvider:
    """`/api/gif/provider`, the chooser the page draws on a wide screen. T-034."""

    @pytest.fixture
    def two(self, monkeypatch):
        """Both keys present, so both are real options."""
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", "giphy")
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "k")
        monkeypatch.setenv("WASTATUS_KLIPY_KEY", "k")

    def test_it_switches_and_answers_with_the_new_credit(self, base, app, two):
        status, payload = fetch(f"{base}/api/gif/provider", token=app.token,
                                method="POST", body={"provider": "klipy"})
        assert status == 200
        assert payload["provider"] == "klipy"
        assert payload["placeholder"] == "Search KLIPY"
        assert gifs.provider() == "klipy"

    def test_the_state_then_reports_the_new_one(self, base, app, two):
        fetch(f"{base}/api/gif/provider", token=app.token, method="POST",
              body={"provider": "klipy"})
        _, state = fetch(f"{base}/api/state", token=app.token)
        assert state["gifs"]["provider"] == "klipy"

    def test_both_are_offered_as_choices(self, base, app, two):
        _, state = fetch(f"{base}/api/state", token=app.token)
        assert [one["name"] for one in state["gifs"]["choices"]] == ["giphy", "klipy", "both"]

    def test_a_provider_with_no_key_is_refused(self, base, app, monkeypatch):
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", "giphy")
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "k")
        monkeypatch.delenv("WASTATUS_KLIPY_KEY", raising=False)
        status, _ = fetch(f"{base}/api/gif/provider", token=app.token,
                          method="POST", body={"provider": "klipy"})
        assert status == HTTPStatus.BAD_REQUEST
        assert gifs.provider() == "giphy"

    @pytest.mark.parametrize("name", ["", "tenor", "../giphy", None])
    def test_junk_is_refused(self, name, base, app, two):
        status, _ = fetch(f"{base}/api/gif/provider", token=app.token,
                          method="POST", body={"provider": name})
        assert status == HTTPStatus.BAD_REQUEST

    def test_it_is_refused_while_the_feature_is_off(self, base, app, monkeypatch):
        monkeypatch.setattr(gifs, "enabled", lambda: False)
        status, _ = fetch(f"{base}/api/gif/provider", token=app.token,
                          method="POST", body={"provider": "klipy"})
        assert status == HTTPStatus.NOT_FOUND

    def test_it_needs_the_token_like_everything_else(self, base, app, two):
        status, _ = fetch(f"{base}/api/gif/provider", method="POST",
                          body={"provider": "klipy"})
        assert status == HTTPStatus.FORBIDDEN

    def test_the_previous_results_are_forgotten(self, base, app, two, monkeypatch):
        """An id from GIPHY means nothing to KLIPY, so a stale pick must not fetch."""
        monkeypatch.setattr(gifs, "search", lambda q, limit=30, large=False: [
            gifs.Gif(id="abc", title="x", preview="https://x/s.gif",
                     full="https://x/f.gif", width=1, height=1, bytes=1)])
        fetch(f"{base}/api/gifs?q=hi", token=app.token)
        assert app.offered_gif("abc") is not None
        fetch(f"{base}/api/gif/provider", token=app.token, method="POST",
              body={"provider": "klipy"})
        assert app.offered_gif("abc") is None
        status, _ = fetch(f"{base}/api/gif/pick", token=app.token, method="POST",
                          body={"id": "abc"})
        assert status == HTTPStatus.NOT_FOUND


class TestChoosingWhatIsBehindTheFrames:
    """The background is under everything, so it cannot be drawn over what is on
    screen: to preview it, the frame is built again from the still that was kept."""

    @pytest.fixture
    def video_clip(self, app):
        """A video clip whose picture rectangle was recorded, as new ones are."""
        from PIL import Image

        stem = "20260826_kailash_0-35_video"
        app.out.mkdir(parents=True, exist_ok=True)
        (app.out / f"{stem}.mp4").write_bytes(b"not really a video")
        rect = {"left": 220, "top": 391, "width": 640, "height": 1138}
        frame = Image.new("RGB", (compose.WIDTH, compose.HEIGHT), (20, 40, 200))
        frame.paste(Image.new("RGB", (rect["width"], rect["height"]), (200, 30, 30)),
                    (rect["left"], rect["top"]))
        frame.save(app.out / f"{stem}.base.png")
        (app.out / f"{stem}.json").write_text(
            json.dumps({"picture": rect, "picture_top": rect["top"], "fill": "blur"}),
            encoding="utf-8")
        return stem

    def _ask(self, base, app, stem, **body):
        request = urllib.request.Request(
            f"{base}/api/preview",
            data=json.dumps({"stem": stem, **body}).encode(),
            headers={"X-Wastatus-Token": app.token,
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def test_the_page_is_told_which_backgrounds_this_server_draws(self, base, app):
        """So a page cannot offer one the renderer would refuse."""
        status, body = fetch(f"{base}/api/state", token=app.token)
        assert status == 200
        assert body["fills"] == list(render.FILLS)

    def test_asking_for_black_gives_back_a_black_backed_frame(self, base, app,
                                                              video_clip):
        from PIL import Image

        _, _, blurred = self._ask(base, app, video_clip, title="x")
        _, _, blacked = self._ask(base, app, video_clip, title="x", fill="black")
        assert blurred != blacked
        drawn = Image.open(io.BytesIO(blacked)).convert("RGB")
        assert sum(drawn.getpixel((6, 6))) < 30, "the corner is not black"

    def test_a_background_the_clip_already_has_is_left_alone(self, base, app,
                                                            video_clip):
        _, _, plain = self._ask(base, app, video_clip, title="x")
        _, _, asked = self._ask(base, app, video_clip, title="x", fill="blur")
        assert plain == asked

    def test_a_still_showing_a_different_background_is_not_cut_open(
        self, base, app, video_clip
    ):
        """The hole lets the clip play through the middle of the preview. With a
        different background around it the clip would play its old one through that
        hole, and the seam would run across the picture."""
        _, same, _ = self._ask(base, app, video_clip, title="x", fill="blur")
        _, other, _ = self._ask(base, app, video_clip, title="x", fill="black")
        assert same["X-Moving-Band"], "the ordinary preview lost its hole"
        assert other.get("X-Moving-Band") is None

    def test_a_clip_with_no_recorded_rectangle_is_previewed_as_it_is(self, base, app):
        """Older clips know where their text went but not where their picture did,
        so there is no way to say which pixels to keep. The words still preview."""
        from PIL import Image

        stem = "20260820_older_0-35_video"
        Image.new("RGB", (compose.WIDTH, compose.HEIGHT), (20, 40, 200)).save(
            app.out / f"{stem}.base.png")
        (app.out / f"{stem}.mp4").write_bytes(b"not really a video")
        status, _, body = self._ask(base, app, stem, title="x", fill="black")
        assert status == 200
        assert Image.open(io.BytesIO(body)).convert("RGB").getpixel((6, 6))[2] > 100

    def test_a_background_nobody_draws_is_refused(self, base, app, video_clip):
        status, _, body = self._ask(base, app, video_clip, title="x", fill="tartan")
        assert status == HTTPStatus.BAD_REQUEST
        assert "background" in json.loads(body)["error"]

    def test_a_render_asking_for_one_is_refused_too(self, base, app):
        """Before yt-dlp is started, not after: it is a page that has drifted from
        this server, and the clip would be made with the wrong thing behind it."""
        status, body = fetch(
            f"{base}/api/render", token=app.token, method="POST",
            body={"url": "https://youtu.be/abc", "duration": 15, "fill": "tartan"},
        )
        assert status == HTTPStatus.BAD_REQUEST
        assert "background" in body["error"]


class TestTheFreeTextPicture:
    """`/api/text`. The page places a picture of a line rather than drawing it.

    Everything else on the frame is Pillow's work, and so is this: a browser laying
    out its own words would break and kern the line differently from the renderer,
    and the box you dragged would not be the pixels ffmpeg burns in.
    """

    def _ask(self, base, app, text):
        request = urllib.request.Request(
            f"{base}/api/text",
            data=json.dumps({"text": text}).encode(),
            headers={"X-Wastatus-Token": app.token,
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def test_a_line_comes_back_as_a_transparent_png(self, base, app):
        from PIL import Image

        status, headers, body = self._ask(base, app, "WATCH TILL THE END")
        assert status == 200
        assert headers["Content-Type"] == "image/png"
        drawn = Image.open(io.BytesIO(body))
        assert drawn.format == "PNG"
        assert drawn.width == app.TEXT_WIDTH
        assert drawn.convert("RGBA").getchannel("A").getextrema()[0] == 0, (
            "the picture has to be transparent around the words")

    def test_different_words_give_a_different_picture(self, base, app):
        _, _, one = self._ask(base, app, "One")
        _, _, two = self._ask(base, app, "Something else entirely")
        assert one != two

    def test_a_line_with_nothing_in_it_is_refused(self, base, app):
        status, _, body = self._ask(base, app, "   \n ")
        assert status == HTTPStatus.BAD_REQUEST
        assert "nothing to draw" in json.loads(body)["error"]

    def test_a_very_long_line_is_drawn_rather_than_refused(self, base, app):
        """It is capped, not rejected: somebody pasting a paragraph in wants to see
        what happened, and the cap is what they see."""
        status, _, body = self._ask(base, app, "long " * 200)
        assert status == 200
        assert len(body) > 0

    def test_it_is_never_cached(self, base, app):
        """The picture is the words, and the words change on every keystroke."""
        _, headers, _ = self._ask(base, app, "Kailash")
        assert "no-store" in (headers.get("Cache-Control") or "")

    def test_it_needs_the_token_like_everything_else(self, base):
        request = urllib.request.Request(
            f"{base}/api/text", data=json.dumps({"text": "x"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=30)
        assert caught.value.code == HTTPStatus.FORBIDDEN


class TestTheLiveWordPreview:
    """`/api/preview`, T-036. Words on the clip's own picture, without ffmpeg.

    The point of it is the cost: making the clip again is 30 to 66 seconds on the
    owner's own measurements, and drawing the words is under one.
    """

    @pytest.fixture
    def clip(self, app):
        """A card-mode clip with the artwork the preview draws from."""
        from PIL import Image

        stem = "20260822_song_0-8"
        app.out.mkdir(parents=True, exist_ok=True)
        (app.out / f"{stem}.mp4").write_bytes(b"not really a video")
        Image.new("RGB", (640, 360), (30, 60, 90)).save(app.out / f"{stem}.art.jpg")
        return stem

    @pytest.fixture
    def video_clip(self, app):
        """A video-mode clip, which keeps a textless frame instead of artwork."""
        from PIL import Image

        stem = "20260822_song_0-8_video"
        app.out.mkdir(parents=True, exist_ok=True)
        (app.out / f"{stem}.mp4").write_bytes(b"not really a video")
        Image.new("RGB", (compose.WIDTH, compose.HEIGHT), (10, 10, 10)).save(
            app.out / f"{stem}.base.png")
        return stem

    def _ask(self, base, app, stem, **words):
        request = urllib.request.Request(
            f"{base}/api/preview",
            data=json.dumps({"stem": stem, **words}).encode(),
            headers={"X-Wastatus-Token": app.token,
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def test_a_card_clip_gives_back_a_jpeg_of_the_words(self, base, app, clip):
        from PIL import Image

        status, headers, body = self._ask(base, app, clip, title="A new title",
                                          channel="A new second line")
        assert status == 200
        assert headers["Content-Type"] == "image/jpeg"
        picture = Image.open(io.BytesIO(body))
        assert picture.format == "JPEG"
        assert picture.width == app.PREVIEW_WIDTH

    def test_a_video_clip_draws_the_words_over_its_own_frame(self, base, app,
                                                             video_clip):
        from PIL import Image

        status, _, body = self._ask(base, app, video_clip, title="Words here")
        assert status == 200
        assert Image.open(io.BytesIO(body)).width == app.PREVIEW_WIDTH

    def test_different_words_give_a_different_picture(self, base, app, clip):
        """The whole feature, in one assertion."""
        _, _, one = self._ask(base, app, clip, title="One")
        _, _, two = self._ask(base, app, clip, title="Something else entirely")
        assert one != two

    def test_it_is_small_enough_to_send_to_a_phone(self, base, app, clip):
        """A full size PNG of this measured 1254 kB, over a tailnet, per keystroke."""
        _, _, body = self._ask(base, app, clip, title="A title of ordinary length")
        assert len(body) < 250_000

    def test_a_card_clip_says_the_waveform_is_the_part_that_moves(
        self, base, app, clip
    ):
        """The still is laid over the clip, so it has to be cut open where the clip
        moves or pressing play shows a frozen picture. On a card that is the
        waveform and nothing else."""
        _, headers, _ = self._ask(base, app, clip, title="x")
        top, bottom = (float(n) for n in headers["X-Moving-Band"].split(","))
        assert top == pytest.approx(compose.WAVE_TOP / compose.HEIGHT, abs=1e-4)
        assert bottom == pytest.approx(
            (compose.WAVE_TOP + compose.WAVE_H) / compose.HEIGHT, abs=1e-4)

    def test_a_video_clip_says_where_its_words_begin(self, base, app, video_clip):
        """Below the frames is where the words are, and the words are the still."""
        (app.out / f"{video_clip}.json").write_text(
            json.dumps({"picture_top": 400}), encoding="utf-8")
        _, headers, _ = self._ask(base, app, video_clip, title="x")
        _, bottom = (float(n) for n in headers["X-Moving-Band"].split(","))
        assert bottom == pytest.approx(
            compose.video_picture_bottom(compose.CardText(title="x", channel=""))
            / compose.HEIGHT, abs=1e-4)

    def test_with_no_top_line_the_whole_top_of_the_frame_moves(
        self, base, app, video_clip
    ):
        """The top line is the only thing drawn above the frames. Without one there
        is nothing up there to cover, and covering it anyway froze the strip under
        WhatsApp's own header for no reason at all."""
        (app.out / f"{video_clip}.json").write_text(
            json.dumps({"picture_top": 400}), encoding="utf-8")
        _, headers, _ = self._ask(base, app, video_clip, title="x")
        top, _ = (float(n) for n in headers["X-Moving-Band"].split(","))
        assert top == 0.0

    def test_a_top_line_is_covered_like_any_other_word(self, base, app, video_clip):
        """With one, the hole starts just under the block, wherever that block was
        drawn. Measured off the words rather than off the picture: the two agree for
        a fitted picture and part company for a placed one."""
        (app.out / f"{video_clip}.json").write_text(
            json.dumps({"picture_top": 400}), encoding="utf-8")
        words = dict(title="x", topline="a line at the top")
        _, headers, _ = self._ask(base, app, video_clip, **words)
        top, _ = (float(n) for n in headers["X-Moving-Band"].split(","))
        lines = compose.topline_lines(words["topline"])
        drawn = compose.topline_top(400, lines) + compose.topline_height(lines)
        assert top * compose.HEIGHT == pytest.approx(drawn, abs=1)
        assert top * compose.HEIGHT <= 400, "the hole reaches past the picture's edge"

    def test_a_picture_that_starts_above_the_frame_still_opens_a_hole(
        self, base, app, video_clip
    ):
        """A placed picture may hang off the top. The row it starts on is then
        negative, and a hole measured from it used to be refused outright: the still
        covered the whole frame and the clip stopped playing underneath it."""
        (app.out / f"{video_clip}.json").write_text(
            json.dumps({"picture_top": -190,
                        "picture": {"left": 0, "top": -190,
                                    "width": 1080, "height": 1766}}),
            encoding="utf-8")
        _, headers, _ = self._ask(base, app, video_clip, title="x")
        assert headers["X-Moving-Band"], "a full bleed picture lost its hole"
        top, bottom = (float(n) for n in headers["X-Moving-Band"].split(","))
        assert 0 <= top < bottom <= 1

    def test_the_hole_never_opens_onto_the_words(self, base, app, video_clip):
        """The whole thing rests on this. If the band reached below the row the
        title starts at, the old title would show through the new one."""
        words = dict(title="A long enough title to wrap onto a second line",
                     channel="A channel", eyebrow="NOW PLAYING",
                     topline="a line at the top")
        (app.out / f"{video_clip}.json").write_text(
            json.dumps({"picture_top": 500}), encoding="utf-8")
        _, headers, _ = self._ask(base, app, video_clip, **words)
        _, bottom = (float(n) for n in headers["X-Moving-Band"].split(","))
        text = compose.CardText(**words)
        assert bottom * compose.HEIGHT <= compose.video_picture_bottom(text)
        assert bottom * compose.HEIGHT < compose.VIDEO_TITLE_TOP

    def test_a_clip_with_no_recorded_picture_is_measured_the_same_way_its_text_was(
        self, base, app, video_clip
    ):
        """No sidecar, so no `picture_top`. The anchor falls back to the function
        that placed the top line, which is the only honest guess there is, and the
        hole still starts under the block rather than on it."""
        words = compose.CardText(title="x", channel="", topline="a line at the top")
        _, headers, _ = self._ask(base, app, video_clip, title="x",
                                  topline="a line at the top")
        top, _ = (float(n) for n in headers["X-Moving-Band"].split(","))
        lines = compose.topline_lines(words.topline)
        drawn = (compose.topline_top(compose.video_picture_top(words), lines)
                 + compose.topline_height(lines))
        assert top * compose.HEIGHT == pytest.approx(drawn, abs=1)

    def test_it_is_never_cached(self, base, app, clip):
        """Every request draws it again, so a cached copy is always the wrong one."""
        _, headers, _ = self._ask(base, app, clip, title="x")
        assert "no-store" in (headers.get("Cache-Control") or "")

    def test_a_clip_with_no_preview_base_says_what_to_do(self, base, app):
        """Everything made before this existed. The message has to be actionable."""
        (app.out).mkdir(parents=True, exist_ok=True)
        (app.out / "20260101_old_0-8.mp4").write_bytes(b"x")
        status, _, body = self._ask(base, app, "20260101_old_0-8", title="x")
        assert status == HTTPStatus.NOT_FOUND
        assert "make it again" in json.loads(body)["error"].lower()

    def test_a_clip_that_does_not_exist_is_refused(self, base, app):
        status, _, _ = self._ask(base, app, "20260101_nothing_0-8", title="x")
        assert status == HTTPStatus.NOT_FOUND

    @pytest.mark.parametrize("stem", ["../../etc/passwd", "a/b", "", "x" * 200])
    def test_a_name_that_is_not_a_clip_name_is_refused(self, stem, base, app):
        status, _, _ = self._ask(base, app, stem, title="x")
        assert status == HTTPStatus.BAD_REQUEST

    def test_it_needs_the_token(self, base, app, clip):
        request = urllib.request.Request(
            f"{base}/api/preview",
            data=json.dumps({"stem": clip, "title": "x"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=20)
        assert raised.value.code == HTTPStatus.FORBIDDEN

    def test_absurdly_long_words_are_cut_rather_than_refused(self, base, app, clip):
        """A caption box can hold 1024 characters and somebody will paste a book."""
        status, _, _ = self._ask(base, app, clip, title="x" * 50_000)
        assert status == 200


class TestPlacingThePictureThroughTheServer:
    """D-061. A placement arrives as three fractions and has to survive the round
    trip to the renderer, to the sidecar, and back into the preview."""

    @pytest.fixture
    def video_clip(self, app):
        from PIL import Image

        stem = "20260826_placed_0-35_video"
        app.out.mkdir(parents=True, exist_ok=True)
        (app.out / f"{stem}.mp4").write_bytes(b"not really a video")
        rect = {"left": 220, "top": 391, "width": 640, "height": 1138}
        frame = Image.new("RGB", (compose.WIDTH, compose.HEIGHT), (20, 40, 200))
        frame.paste(Image.new("RGB", (rect["width"], rect["height"]), (200, 30, 30)),
                    (rect["left"], rect["top"]))
        frame.save(app.out / f"{stem}.base.png")
        (app.out / f"{stem}.json").write_text(json.dumps({
            "picture": rect, "picture_top": rect["top"], "fill": "blur",
            "framing": None,
        }), encoding="utf-8")
        return stem

    def _ask(self, base, app, stem, **body):
        request = urllib.request.Request(
            f"{base}/api/preview",
            data=json.dumps({"stem": stem, **body}).encode(),
            headers={"X-Wastatus-Token": app.token,
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def test_the_preview_moves_the_picture(self, base, app, video_clip):
        from PIL import Image

        _, _, was = self._ask(base, app, video_clip, title="x")
        _, _, now = self._ask(base, app, video_clip, title="x",
                              framing={"x": 0.5, "y": 0.5, "size": 1.0})
        assert was != now
        drawn = Image.open(io.BytesIO(now)).convert("RGB")
        # A full width picture reaches both side edges at its own middle.
        assert drawn.getpixel((4, drawn.height // 2))[0] > 100

    def test_a_moved_picture_closes_the_hole_in_the_still(self, base, app,
                                                          video_clip):
        """The clip underneath still has its picture in the old place: a hole would
        show it there while the still shows it here."""
        _, same, _ = self._ask(base, app, video_clip, title="x")
        _, moved, _ = self._ask(base, app, video_clip, title="x",
                                framing={"x": 0.4, "y": 0.4, "size": 0.7})
        assert same["X-Moving-Band"]
        assert moved.get("X-Moving-Band") is None

    def test_the_clips_own_placement_is_not_a_change(self, base, app, video_clip):
        """Asking for exactly what it was made with must not rebuild anything, or
        every clip made from a placement would preview itself forever."""
        (app.out / f"{video_clip}.json").write_text(json.dumps({
            "picture": {"left": 220, "top": 391, "width": 640, "height": 1138},
            "picture_top": 391, "fill": "blur",
            "framing": {"x": 0.5, "y": 0.5, "size": 0.59259},
        }), encoding="utf-8")
        _, _, plain = self._ask(base, app, video_clip, title="x")
        _, headers, asked = self._ask(base, app, video_clip, title="x",
                                      framing={"x": 0.5, "y": 0.5, "size": 0.59259})
        assert plain == asked
        assert headers["X-Moving-Band"], "the hole closed on a placement that matches"

    def test_a_placement_that_is_not_one_is_refused(self, base, app, video_clip):
        status, _, body = self._ask(base, app, video_clip, title="x",
                                    framing={"size": "wide"})
        assert status == HTTPStatus.BAD_REQUEST
        assert "number" in json.loads(body)["error"]

    def test_a_render_takes_one_and_refuses_junk(self, base, app):
        status, body = fetch(
            f"{base}/api/render", token=app.token, method="POST",
            body={"url": "https://youtu.be/abc", "duration": 15,
                  "framing": {"x": "left"}},
        )
        assert status == HTTPStatus.BAD_REQUEST
        assert "number" in body["error"]


class TestPlacingTheArtworkThroughTheServer:
    """D-062. The same three fractions, for card mode's own panel.

    Card mode has an advantage video mode does not: it kept the artwork, so the card
    is simply drawn again. There is no still to rebuild, and so no clip that is too
    old to show you what you are asking for.
    """

    @pytest.fixture
    def card_clip(self, app):
        from PIL import Image

        stem = "20260827_placed_0-30"
        app.out.mkdir(parents=True, exist_ok=True)
        (app.out / f"{stem}.mp4").write_bytes(b"not really a video")
        Image.new("RGB", (1280, 720), (200, 40, 40)).save(app.out / f"{stem}.art.jpg")
        (app.out / f"{stem}.json").write_text(json.dumps({
            "video": False, "fill": "blur", "framing": None,
            "picture": {"left": 100, "top": 450, "width": 880, "height": 495},
        }), encoding="utf-8")
        return stem

    def _ask(self, base, app, stem, **body):
        request = urllib.request.Request(
            f"{base}/api/preview",
            data=json.dumps({"stem": stem, **body}).encode(),
            headers={"X-Wastatus-Token": app.token,
                     "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def test_the_preview_moves_the_panel(self, base, app, card_clip):
        _, _, was = self._ask(base, app, card_clip, title="x")
        _, _, now = self._ask(base, app, card_clip, title="x",
                              framing={"x": 0.5, "y": 0.5, "size": 1.0})
        assert was != now

    def test_a_moved_panel_closes_the_hole_in_the_still(self, base, app, card_clip):
        """The clip underneath still has its panel in the old place, and the hole is
        the waveform, which a panel dragged down there sits on top of."""
        _, same, _ = self._ask(base, app, card_clip, title="x")
        _, moved, _ = self._ask(base, app, card_clip, title="x",
                                framing={"x": 0.4, "y": 0.4, "size": 0.7})
        assert same["X-Moving-Band"]
        assert moved.get("X-Moving-Band") is None

    def test_a_placed_clip_previews_with_its_own_placement(self, base, app,
                                                           card_clip):
        """Nothing asked for means "as the clip was made", not "fitted". Without
        this, retyping a word on a placed card answered with a fitted one, and the
        still that covers the clip would jump the panel back to the middle."""
        placed = {"x": 0.3, "y": 0.3, "size": 0.5}
        (app.out / f"{card_clip}.json").write_text(json.dumps({
            "video": False, "fill": "blur", "framing": placed,
            "picture": {"left": 90, "top": 420, "width": 540, "height": 304},
        }), encoding="utf-8")
        _, headers, quiet = self._ask(base, app, card_clip, title="x")
        _, _, asked = self._ask(base, app, card_clip, title="x", framing=placed)
        assert quiet == asked
        assert headers["X-Moving-Band"], "its own placement was read as a change"

    def test_a_background_choice_is_not_a_change_to_a_card(self, base, app,
                                                           card_clip):
        """The card composes its own background and never reads that field. It is
        still in the request, because the page sends one form: answering yes to it
        here would freeze the clip under a still identical to itself."""
        _, headers, _ = self._ask(base, app, card_clip, title="x", fill="black")
        assert headers["X-Moving-Band"]

    def test_a_placement_that_is_not_one_is_refused(self, base, app, card_clip):
        status, _, body = self._ask(base, app, card_clip, title="x",
                                    framing={"y": "up"})
        assert status == HTTPStatus.BAD_REQUEST
        assert "number" in json.loads(body)["error"]
