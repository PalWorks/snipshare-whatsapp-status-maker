"""The tab that says which ports this session is on.

The terminal `wastatus serve` was started from is often not the window you are
looking at later, and with two or three debug browsers open on one machine there
was nothing on screen saying which Chrome belonged to this tool. The label is one
file and one extra tab, and its `<title>` is the part that does the work.
"""

from __future__ import annotations

import pytest

from wastatus import label, post

FIELDS = dict(
    port=8765,
    url="http://127.0.0.1:8765/",
    cdp_port=9230,
    profile="/home/someone/.config/chrome-wastatus",
    out="/home/someone/clips",
)


def test_the_title_names_the_port_because_the_window_title_is_the_point():
    page = label.render(**FIELDS, when="Mon 24 Aug 2026, 12:00:00 IST")
    assert "<title>&#9679; 8765 &middot; wastatus</title>" in page


def test_it_names_both_ports_and_where_the_output_goes():
    page = label.render(**FIELDS, when="now")
    for expected in ("8765", "9230", "chrome-wastatus", "/home/someone/clips"):
        assert expected in page


def test_a_second_address_is_named_only_when_there_is_one():
    assert "Also on" not in label.render(**FIELDS, when="now")
    with_tailnet = label.render(**FIELDS, when="now", also_on="http://100.64.0.1:8765/")
    assert "Also on" in with_tailnet and "100.64.0.1" in with_tailnet


def test_nothing_is_pasted_into_the_page_unescaped(tmp_path):
    """The output folder is a path the person chose, and a page is not a place to
    put text without escaping it, whatever the odds of a `<` in a directory name."""
    page = label.render(**{**FIELDS, "out": "/tmp/<script>alert(1)</script>"}, when="now")
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_it_is_written_per_port_so_a_restart_does_not_leave_a_trail(tmp_path, monkeypatch):
    monkeypatch.setenv("WASTATUS_CACHE_DIR", str(tmp_path / "cache"))
    first = label.write(**FIELDS, when="now")
    again = label.write(**FIELDS, when="later")
    assert first == again
    assert list((tmp_path / "cache").iterdir()) == [first]
    assert "later" in first.read_text(encoding="utf-8")


class TestTheBrowserOpensIt:
    @pytest.fixture(autouse=True)
    def _no_browser_already_open(self, monkeypatch):
        monkeypatch.setattr(post, "running_profile_port", lambda profile=None: None)

    def test_the_label_is_the_first_tab_and_whatsapp_is_still_opened(
        self, monkeypatch, tmp_path
    ):
        """First, so the window title names the port rather than saying WhatsApp.
        `Page.__init__` calls `Page.bringToFront`, so the posting tab does not need
        to have started in front."""
        launched: list[list[str]] = []
        monkeypatch.setattr(post, "chrome_binary", lambda: "/usr/bin/google-chrome")
        monkeypatch.setenv("WASTATUS_CHROME_DIR", str(tmp_path / "profile"))
        monkeypatch.setattr(
            post.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd)
        )
        page = tmp_path / "session-8765.html"
        page.write_text("<html></html>", encoding="utf-8")
        post.launch_browser(9230, first=page)
        assert launched[0][-2:] == [page.as_uri(), "https://web.whatsapp.com"]

    def test_the_page_rides_between_the_label_and_whatsapp(
        self, monkeypatch, tmp_path
    ):
        """One window then holds the whole session: what it is, what it does, and
        what it posts through. The label stays first so the window title keeps
        naming the port."""
        launched: list[list[str]] = []
        monkeypatch.setattr(post, "chrome_binary", lambda: "/usr/bin/google-chrome")
        monkeypatch.setenv("WASTATUS_CHROME_DIR", str(tmp_path / "profile"))
        monkeypatch.setattr(
            post.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd)
        )
        page = tmp_path / "session-8765.html"
        page.write_text("<html></html>", encoding="utf-8")
        post.launch_browser(9230, first=page, page="http://127.0.0.1:8765/")
        assert launched[0][-3:] == [
            page.as_uri(), "http://127.0.0.1:8765/", "https://web.whatsapp.com",
        ]

    def test_without_a_label_the_command_line_is_what_it_always_was(
        self, monkeypatch, tmp_path
    ):
        launched: list[list[str]] = []
        monkeypatch.setattr(post, "chrome_binary", lambda: "/usr/bin/google-chrome")
        monkeypatch.setenv("WASTATUS_CHROME_DIR", str(tmp_path / "profile"))
        monkeypatch.setattr(
            post.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd)
        )
        post.launch_browser(9230)
        assert launched[0][-1] == "https://web.whatsapp.com"
        assert not any(one.startswith("file://") for one in launched[0])


class TestTheServerFillsItIn:
    def test_no_label_before_the_socket_is_bound(self, tmp_path):
        """`--port 0` means the number is not known until the bind has happened, and
        a label naming the wrong port is worse than no label."""
        from wastatus import serve
        app = serve.App(out=tmp_path, cdp_port=9230, keep_last=5)
        assert app.label(9230) is None

    def test_it_names_the_page_the_server_is_actually_on(self, tmp_path, monkeypatch):
        from wastatus import serve
        monkeypatch.setenv("WASTATUS_CACHE_DIR", str(tmp_path / "cache"))
        app = serve.App(out=tmp_path, cdp_port=9230, keep_last=5, also_on="100.64.0.1")
        app.page_port = 9999
        page = app.label(9231)
        assert page is not None
        text = page.read_text(encoding="utf-8")
        assert "http://127.0.0.1:9999/" in text
        assert "http://100.64.0.1:9999/" in text
        assert "9231" in text

    def test_a_cache_that_cannot_be_written_does_not_stop_the_browser(
        self, tmp_path, monkeypatch
    ):
        """The tool works perfectly without a label, so this is a warning at most."""
        from wastatus import serve
        monkeypatch.setattr(
            label, "write", lambda **_: (_ for _ in ()).throw(OSError("read only"))
        )
        app = serve.App(out=tmp_path, cdp_port=9230, keep_last=5)
        app.page_port = 8765
        assert app.label(9230) is None
