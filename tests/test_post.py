"""The posting driver, exercised against a fake page rather than a browser.

These are here because of a real bug: the CLI passed a relative clip path, Chrome
accepted it without complaint, attached nothing, and the failure surfaced 75
seconds later as "timed out waiting for the media composer". Nothing in the
protocol reports it, so the invariant has to be tested on our side.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from wastatus import post


class FakePage:
    """Enough of `Page` for `load_video` to run. Records every command."""

    def __init__(self, *, composer_open: bool = False) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.typed: list[str] = []
        self.composer_open = composer_open
        self.cancelled = False

    def send_cmd(self, method: str, **params) -> dict:
        self.calls.append((method, params))
        return {}

    def js(self, expression: str):
        if "wds-ic-send" in expression:
            return self.composer_open
        if "aria-label=\"Close\"" in expression:
            self.cancelled = True
            return True
        if "aria-label" in expression and "want" in expression:
            return "clicked"
        return True

    def js_soft(self, expression: str, default=None):
        return self.js(expression)

    def wait_event(self, method: str, timeout: float = 0) -> dict:
        return {"method": method, "params": {"backendNodeId": 42}}

    def wait_for(self, condition: str, what: str, timeout: float = 0) -> None:
        return None

    def files_set(self) -> list[str]:
        for method, params in self.calls:
            if method == "DOM.setFileInputFiles":
                return params["files"]
        return []


def _click_returns_clicked(monkeypatch):
    monkeypatch.setattr(post, "click_one_of", lambda page, labels, what: None)
    monkeypatch.setattr(post, "open_status_menu", lambda page, item: None)
    monkeypatch.setattr(post.time, "sleep", lambda _s: None)


def test_a_relative_path_is_resolved_before_it_reaches_chrome(tmp_path, monkeypatch):
    _click_returns_clicked(monkeypatch)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"not really an mp4")
    monkeypatch.chdir(tmp_path)

    page = FakePage()
    post.load_video(page, Path("clip.mp4"))

    sent = page.files_set()
    assert sent, "no file was ever handed to the browser"
    assert Path(sent[0]).is_absolute(), f"Chrome cannot resolve {sent[0]!r}"
    assert Path(sent[0]).resolve() == clip.resolve()


def test_a_missing_file_fails_before_touching_the_page(tmp_path, monkeypatch):
    _click_returns_clicked(monkeypatch)
    page = FakePage()
    with pytest.raises(post.PostError, match="no such file to post"):
        post.load_video(page, tmp_path / "absent.mp4")
    assert page.calls == [], "the page was driven despite there being nothing to send"


def test_the_file_dialog_interception_is_always_turned_back_off(tmp_path, monkeypatch):
    """A left on interception would swallow the user's own file dialogs."""
    monkeypatch.setattr(post.time, "sleep", lambda _s: None)
    monkeypatch.setattr(post, "open_status_menu", lambda page, item: None)
    monkeypatch.setattr(
        post, "click_one_of",
        lambda page, labels, what: (_ for _ in ()).throw(post.PostError("boom")),
    )
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")

    page = FakePage()
    with pytest.raises(post.PostError, match="boom"):
        post.load_video(page, clip)

    intercept = [p["enabled"] for m, p in page.calls if m == "Page.setInterceptFileChooserDialog"]
    assert intercept == [True, False]


def test_the_caption_is_typed_only_when_there_is_one(tmp_path, monkeypatch):
    _click_returns_clicked(monkeypatch)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")

    page = FakePage()
    post.load_video(page, clip)
    assert not [m for m, _ in page.calls if m == "Input.insertText"]

    page = FakePage()
    post.load_video(page, clip, "https://youtu.be/abc")
    typed = [p["text"] for m, p in page.calls if m == "Input.insertText"]
    assert typed == ["https://youtu.be/abc"]


def test_a_composer_left_open_is_closed_before_attaching(tmp_path, monkeypatch):
    """Attaching into an open composer sends both files as separate Statuses.

    That happened for real on 2026-08-18: a diagnostic left a clip loaded, the next
    run attached another, and two Statuses went out a second apart.
    """
    _click_returns_clicked(monkeypatch)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")

    page = FakePage(composer_open=True)
    post.load_video(page, clip)
    assert page.cancelled, "an already open composer was not backed out of"


def test_nothing_is_cancelled_when_no_composer_is_open(tmp_path, monkeypatch):
    _click_returns_clicked(monkeypatch)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")

    page = FakePage(composer_open=False)
    post.load_video(page, clip)
    assert not page.cancelled


def test_deleting_nothing_is_not_an_error(monkeypatch):
    """An empty tray has no viewer to open, so the routine simply does nothing."""
    monkeypatch.setattr(post.time, "sleep", lambda _s: None)
    monkeypatch.setattr(post, "open_my_status", lambda page: 0)
    assert post.delete_all_statuses(FakePage()) == 0


def test_deleting_stops_at_the_limit(monkeypatch):
    """A tray that never empties must not loop forever."""
    monkeypatch.setattr(post.time, "sleep", lambda _s: None)
    monkeypatch.setattr(post, "open_my_status", lambda page: 5)
    assert post.delete_all_statuses(FakePage(), limit=3) == 3


def test_a_missing_delete_item_is_reported(monkeypatch):
    """A WhatsApp Web redesign must fail loudly, not silently delete nothing."""
    monkeypatch.setattr(post.time, "sleep", lambda _s: None)
    monkeypatch.setattr(post, "open_my_status", lambda page: 1)

    class NoDeleteItem(FakePage):
        def js(self, expression: str):
            if "endsWith('Delete')" in expression:
                return False
            return super().js(expression)

    with pytest.raises(post.PostError, match="no Delete item"):
        post.delete_all_statuses(NoDeleteItem())


class TestFindingABrowser:
    """Chrome only speaks the protocol when it was started with the switch, so the
    search space is "debug browsers", not "browsers". Anything else is unreachable:
    a page on loopback cannot drive another origin's tab, whatever it is asked to
    do. Hence a dedicated profile, and hence this discovery."""

    def test_the_configured_port_is_preferred(self, monkeypatch):
        seen: list[int] = []

        def fake_find(port, timeout=5.0):
            seen.append(port)
            return {"url": "https://web.whatsapp.com/"}

        monkeypatch.setattr(post, "find_tab", fake_find)
        monkeypatch.setattr(post, "browser_name", lambda port, timeout=1.0: "Chrome/1")
        found = post.discover(9223)
        assert found.port == 9223
        assert seen == [9223]

    def test_another_debug_browser_is_used_when_the_first_has_no_whatsapp(
        self, monkeypatch
    ):
        def fake_find(port, timeout=5.0):
            if port != 9226:
                raise post.PostError(f"nothing on {port}")
            return {"url": "https://web.whatsapp.com/"}

        monkeypatch.setattr(post, "find_tab", fake_find)
        monkeypatch.setattr(post, "browser_name", lambda port, timeout=1.0: "Chrome/1")
        assert post.discover(9222).port == 9226

    def test_with_nothing_running_the_configured_port_is_what_gets_reported(
        self, monkeypatch
    ):
        """Complaining about port 9225 to someone who configured 9222 is noise."""
        monkeypatch.setattr(
            post, "find_tab",
            lambda port, timeout=5.0: (_ for _ in ()).throw(
                post.PostError(f"no Chrome answering on 127.0.0.1:{port}")
            ),
        )
        with pytest.raises(post.PostError, match="9222"):
            post.discover(9222)

    def test_the_detail_names_the_browser_and_the_port(self):
        found = post.Endpoint(port=9226, browser="Chrome/150.0", tab={})
        assert found.detail == "Chrome/150.0 on port 9226"

    def test_a_browser_we_cannot_name_is_still_a_browser(self):
        assert post.Endpoint(port=9222, browser="", tab={}).detail == (
            "a debug browser on port 9222"
        )


class TestStartingABrowser:
    @pytest.fixture(autouse=True)
    def _no_browser_already_open(self, monkeypatch):
        """Whether the developer has a posting browser running is not under test.

        `launch_browser` refuses when the profile is already open, which is correct
        and is checked in its own test below. Without this, running the suite while
        using the tool fails these two, which is how it was found.
        """
        monkeypatch.setattr(post, "running_profile_port", lambda profile=None: None)

    def test_without_chrome_installed_it_says_so(self, monkeypatch):
        monkeypatch.setattr(post, "chrome_binary", lambda: None)
        with pytest.raises(post.PostError, match="no Chrome or Chromium"):
            post.launch_browser()

    def test_it_refuses_when_the_profile_is_already_open_elsewhere(self, monkeypatch):
        """Chrome would hand this launch to the running instance and exit, ignoring
        the new debug port, so the naive version opens a window and opens no port."""
        monkeypatch.setattr(post, "running_profile_port", lambda profile=None: 9222)
        monkeypatch.setattr(post, "chrome_binary", lambda: "/usr/bin/chrome")
        with pytest.raises(post.PostError) as raised:
            post.launch_browser(9230)
        assert "9222" in str(raised.value)
        assert "9230" in str(raised.value)

    def test_the_same_port_is_not_a_conflict(self, monkeypatch):
        """Asking for the port it is already on is not a second launch worth refusing."""
        monkeypatch.setattr(post, "running_profile_port", lambda profile=None: 9230)
        launched: list[list[str]] = []
        monkeypatch.setattr(post, "chrome_binary", lambda: "/usr/bin/chrome")
        monkeypatch.setattr(
            post.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd)
        )
        post.launch_browser(9230)
        assert launched

    def test_it_starts_chrome_on_the_debug_port_with_its_own_profile(
        self, monkeypatch, tmp_path
    ):
        """The profile has to be its own: Chrome 136 and later ignore the debug
        switch when the default profile directory is used."""
        launched: list[list[str]] = []
        monkeypatch.setattr(post, "chrome_binary", lambda: "/usr/bin/google-chrome")
        monkeypatch.setenv("WASTATUS_CHROME_DIR", str(tmp_path / "profile"))
        monkeypatch.setattr(
            post.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd)
        )
        post.launch_browser(9299)
        assert launched[0][0] == "/usr/bin/google-chrome"
        assert "--remote-debugging-port=9299" in launched[0]
        assert f"--user-data-dir={tmp_path / 'profile'}" in launched[0]
        assert launched[0][-1] == "https://web.whatsapp.com"
        assert (tmp_path / "profile").is_dir()


class TestLabelsWhatsAppKeepsChanging:
    """WhatsApp renamed the Status choices, and every post failed on 2026-08-20.

    "Photo and video" became "Photos & videos" and moved behind an "Add Status"
    button, some time between the last good post at 2026-08-19 22:53 and the first
    failure at 19:42 the next evening. Nothing in this repository changed. The
    matcher is on words now so that the next rewording of the same item still lands.
    """

    @pytest.mark.parametrize("label", [
        "Photos & videos", "Photo and video", "Photos and videos", "photos & videos",
    ])
    def test_every_spelling_of_the_media_choice_reduces_to_one_thing(self, label):
        assert post._canon(label) == post._canon("Photo and video")

    def test_two_different_controls_do_not_collide(self):
        assert post._canon("Text") != post._canon("Photos & videos")
        assert post._canon("Add Status") != post._canon("Text")


class TestTheStatusMenu:
    """The menu is opened only when the choice is not already on screen.

    Pressing "Add Status" on a build that already shows the choices would close
    them again, and not pressing it on a build that hides them leaves nothing to
    click. Which build this is, is answered by looking rather than by assuming.
    """

    class Page:
        def __init__(self, *, item_showing: bool) -> None:
            self.item_showing = item_showing
            self.clicked: list[str] = []

        def js(self, expression: str):
            if "doClick = false" in expression:
                return "found" if self.item_showing else "not found"
            if "doClick = true" in expression:
                self.clicked.append(expression)
                self.item_showing = True
                return "clicked"
            return True

    def test_the_menu_is_opened_when_the_choice_is_hidden(self, monkeypatch):
        monkeypatch.setattr(post.time, "sleep", lambda _s: None)
        page = self.Page(item_showing=False)
        post.open_status_menu(page, post.PHOTO_ITEM)
        assert len(page.clicked) == 1, "Add Status was never pressed"

    def test_the_menu_is_left_alone_when_the_choice_is_already_there(self, monkeypatch):
        monkeypatch.setattr(post.time, "sleep", lambda _s: None)
        page = self.Page(item_showing=True)
        post.open_status_menu(page, post.PHOTO_ITEM)
        assert page.clicked == [], "pressing Add Status would have closed the menu"

    def test_a_choice_that_is_gone_says_where_to_widen_the_list(self, monkeypatch):
        monkeypatch.setattr(post.time, "sleep", lambda _s: None)

        class Missing:
            def js(self, _expression):
                return "not found"

        with pytest.raises(post.PostError, match="wastatus/post.py"):
            post.click_one_of(Missing(), post.PHOTO_ITEM, "the photo and video choice")


def test_the_status_menu_is_opened_before_the_choice_is_clicked(tmp_path, monkeypatch):
    """Order matters: the choice does not exist until the menu is open."""
    monkeypatch.setattr(post.time, "sleep", lambda _s: None)
    order: list[str] = []
    monkeypatch.setattr(post, "open_status_menu",
                        lambda page, item: order.append("menu"))
    monkeypatch.setattr(post, "click_one_of",
                        lambda page, labels, what: order.append("choice"))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"x")

    post.load_video(FakePage(), clip)
    assert order == ["menu", "choice"]


class TestTheControlCheck:
    """T-026: ask whether the Status controls have moved, before a post does.

    The check has to open a menu to see anything, because the two choices do not
    exist in the page until it is open. That makes two things load bearing: it must
    put the menu back, and it must refuse to look while a composer is holding a clip
    somebody is about to send.
    """

    class Page:
        def __init__(self, *, offers, composer_open=False, panel="chats") -> None:
            self.offers = offers
            self.composer_open = composer_open
            self.keys: list[str] = []
            self.clicks = 0
            # Like the real thing: the choices are not in the page until the menu
            # is open, which is the whole reason this check has to open one.
            self.menu_open = False
            # Which side panel WhatsApp is showing, so "put it back" can be tested.
            self.panel = panel

        def js(self, expression: str):
            if "wds-ic-send" in expression:
                return self.composer_open
            if "!b ||" in expression:          # which panel is showing?
                return self.panel == "status"
            if 'aria-label="Status"' in expression:
                self.panel = "status"
                return True
            if 'aria-label="Chats"' in expression:
                self.panel = "chats"
                return True
            if "role=menuitem" in expression and "JSON.stringify" in expression:
                return json.dumps(self.offers if self.menu_open else [])
            if "doClick = true" in expression:
                self.clicks += 1
                self.menu_open = True
                return "clicked"
            if "doClick = false" in expression:
                if not self.menu_open:
                    return "not found"
                wanted = expression.split("new Set(")[1].split(")")[0]
                return "found" if any(
                    post._canon(label) in wanted for label in self.offers
                ) else "not found"
            return True

        def js_soft(self, expression: str, default=None):
            return self.js(expression)

        def send_cmd(self, method: str, **params):
            if method == "Input.dispatchKeyEvent" and params.get("type") == "keyDown":
                self.keys.append(params.get("key"))
            return {}

        def __enter__(self): return self
        def __exit__(self, *_exc): return None

    def _run(self, monkeypatch, page):
        monkeypatch.setattr(post.time, "sleep", lambda _s: None)
        monkeypatch.setattr(post, "Page", lambda _port, **_kw: page)
        monkeypatch.setattr(post, "require_logged_in", lambda _page: None)
        return post.check_controls(9222)

    def test_todays_labels_pass(self, monkeypatch):
        page = self.Page(offers=["Photos & videos", "Text"])
        answer = self._run(monkeypatch, page)
        assert answer["ok"] and answer["checked"]

    def test_yesterdays_labels_pass_too(self, monkeypatch):
        """The build that was live until 2026-08-20 must not be called broken."""
        page = self.Page(offers=["Photo and video", "Text status"])
        assert self._run(monkeypatch, page)["ok"]

    def test_a_rename_is_reported_with_what_is_actually_there(self, monkeypatch):
        page = self.Page(offers=["Snaps and clips", "Words"])
        answer = self._run(monkeypatch, page)
        assert not answer["ok"]
        assert "Snaps and clips" in answer["detail"], "the message must say what it saw"
        assert "wastatus/post.py" in answer["detail"], "and where to put it"

    def test_the_menu_is_put_back(self, monkeypatch):
        page = self.Page(offers=["Photos & videos", "Text"])
        self._run(monkeypatch, page)
        assert "Escape" in page.keys, "the menu was left open over the chat list"

    def test_an_open_composer_is_never_reached_into(self, monkeypatch):
        """A composer holds a clip about to be sent. Checking must not touch it."""
        page = self.Page(offers=["Photos & videos", "Text"], composer_open=True)
        answer = self._run(monkeypatch, page)
        assert answer["ok"] and not answer["checked"]
        assert page.clicks == 0, "the check opened a menu under an open composer"

    def test_it_never_takes_the_screen(self, monkeypatch):
        """Nobody asked for this check. It runs the moment a clip is made, and a
        foregrounded tab threw the window you were reading away every time."""
        page = self.Page(offers=["Photos & videos", "Text"])
        seen: dict = {}
        monkeypatch.setattr(post.time, "sleep", lambda _s: None)
        monkeypatch.setattr(post, "require_logged_in", lambda _page: None)

        def attach(_port, **kw):
            seen.update(kw)
            return page

        monkeypatch.setattr(post, "Page", attach)
        post.check_controls(9222)
        assert seen.get("foreground") is False, "the check grabbed the browser window"

    def test_the_panel_is_left_where_it_was_found(self, monkeypatch):
        """Looking at the Status menu is this tool's business, not a place to
        leave somebody. The chat list was showing, so it is showing afterwards."""
        page = self.Page(offers=["Photos & videos", "Text"], panel="chats")
        self._run(monkeypatch, page)
        assert page.panel == "chats", "WhatsApp was left on the Status panel"

    def test_a_status_panel_that_was_already_open_stays_open(self, monkeypatch):
        """Putting back what was never moved is its own small rudeness."""
        page = self.Page(offers=["Photos & videos", "Text"], panel="status")
        self._run(monkeypatch, page)
        assert page.panel == "status"

    def test_no_browser_is_not_reported_as_a_rename(self, monkeypatch):
        monkeypatch.setattr(post.time, "sleep", lambda _s: None)

        def no_browser(_port, **_kw):
            raise post.PostError("no Chrome answering on 127.0.0.1:9222")

        monkeypatch.setattr(post, "Page", no_browser)
        answer = post.check_controls(9222)
        assert answer["ok"] and not answer["checked"]


class TestWhichPortsToLookOn:
    """`WASTATUS_CDP_PORTS`, because an IDE can own the low ports for good.

    Read at call time on purpose. A default argument or a module constant would
    freeze the list at import, which is before `.env` has been read.
    """

    def test_the_built_in_list_is_used_when_nothing_says_otherwise(self, monkeypatch):
        monkeypatch.delenv(post.PORTS_ENV, raising=False)
        assert post.candidate_ports() == post.DEFAULT_PORTS
        assert post.default_port() == 9222

    def test_a_range_is_expanded(self, monkeypatch):
        monkeypatch.setenv(post.PORTS_ENV, "9230-9235")
        assert post.candidate_ports() == (9230, 9231, 9232, 9233, 9234, 9235)
        assert post.default_port() == 9230

    def test_a_list_and_a_range_can_be_mixed(self, monkeypatch):
        monkeypatch.setenv(post.PORTS_ENV, "9230-9232, 9222")
        assert post.candidate_ports() == (9230, 9231, 9232, 9222)

    def test_the_first_entry_wins_a_repeat(self, monkeypatch):
        monkeypatch.setenv(post.PORTS_ENV, "9230,9231,9230")
        assert post.candidate_ports() == (9230, 9231)

    @pytest.mark.parametrize(
        "value",
        [
            "nine thousand",          # not numbers at all
            "9235-9230",              # backwards
            "0-10",                   # port 0 is not a port to look on
            "70000",                  # past the end of the range
            "9000-9500",              # so wide that probing it would stall the page
            "9230-",                  # a range with one end missing
        ],
    )
    def test_anything_malformed_falls_back_rather_than_guessing(self, value, monkeypatch):
        """Half a list is worse than none: it would look on ports nobody chose."""
        monkeypatch.setenv(post.PORTS_ENV, value)
        assert post.candidate_ports() == post.DEFAULT_PORTS

    def test_a_free_port_is_the_first_nobody_has_taken(self, monkeypatch):
        monkeypatch.setenv(post.PORTS_ENV, "9230-9232")
        monkeypatch.setattr(post, "in_use", lambda port: port in (9230, 9231))
        assert post.free_port() == 9232

    def test_all_taken_says_so_and_names_the_setting(self, monkeypatch):
        monkeypatch.setenv(post.PORTS_ENV, "9230-9231")
        monkeypatch.setattr(post, "in_use", lambda port: True)
        with pytest.raises(post.PostError) as raised:
            post.free_port()
        assert "9230, 9231" in str(raised.value)
        assert post.PORTS_ENV in str(raised.value)


class TestNamingTheBrowserOnAPort:
    """Who holds a debug port, because the honest answer is often "not you".

    This came from an afternoon lost to port 9225: an IDE already had it, so the
    message said "no WhatsApp Web tab is open in it" about somebody else's browser,
    which reads as "log in again" when the answer is "wrong browser". T-031.
    """

    # Not a port anything really uses. An earlier version of this test took 9241,
    # which a browser opened for an unrelated reason during a session, and the test
    # then found that browser instead of its own child.
    PRETEND_PORT = 59241

    @pytest.mark.skipif(
        not Path("/proc").is_dir(),
        reason="port_owner reads /proc, which macOS does not have. It answers \"\" "
               "there, which the test below already covers",
    )
    def test_the_process_that_asked_for_the_port_is_named_with_its_profile(self, tmp_path):
        import subprocess
        import sys
        import time

        if post.port_owner(self.PRETEND_PORT):
            pytest.skip(f"something on this machine already claims {self.PRETEND_PORT}")
        profile = tmp_path / "chrome-pretend"
        # A real process with a real /proc entry. Its argv is what is being read,
        # so it does not have to be a browser, only to be spelled like one.
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)",
             f"--remote-debugging-port={self.PRETEND_PORT}",
             f"--user-data-dir={profile}"],
        )
        try:
            for _ in range(50):  # /proc is written before exec finishes, not after
                found = post.port_owner(self.PRETEND_PORT)
                if found:
                    break
                time.sleep(0.05)
            assert "chrome-pretend" in found
            assert f"pid {child.pid}" in found
        finally:
            child.kill()
            child.wait()

    def test_a_port_nobody_asked_for_says_nothing_rather_than_guessing(self):
        assert post.port_owner(65123) == ""

    def test_chrome_flattens_its_own_argv_and_is_still_read(self):
        """The bug this test exists for. Chrome rewrites argv into one string, so
        the NUL separators /proc normally holds are not there, and a reader that
        only splits on NUL sees one enormous token and matches nothing."""
        flat = (b"/opt/google/chrome/chrome --remote-debugging-port=9225 "
                b"--user-data-dir=/home/x/.config/some-other-profile --force-dark-mode")
        said = post._describe(flat, "--remote-debugging-port=9225")
        assert said == "chrome, profile some-other-profile"

    def test_the_ordinary_nul_separated_shape_still_works(self):
        proper = b"\0".join([
            b"/usr/bin/google-chrome",
            b"--remote-debugging-port=9230",
            b"--user-data-dir=/home/x/.config/chrome-wastatus",
        ]) + b"\0"
        said = post._describe(proper, "--remote-debugging-port=9230")
        assert said == "google-chrome, profile chrome-wastatus"

    def test_a_different_port_on_the_same_browser_is_not_a_match(self):
        flat = b"/opt/google/chrome/chrome --remote-debugging-port=92250"
        assert post._describe(flat, "--remote-debugging-port=9225") == ""


class TestAPortThatDidNotAnswer:
    """The three different things silence on a debug port can mean."""

    def test_ipv6_only_is_called_out_as_half_open(self, monkeypatch):
        """Chrome loses the bind, falls back to [::1], and prints success anyway."""
        monkeypatch.setattr(post, "_answers", lambda port, host="127.0.0.1": host == "[::1]")
        monkeypatch.setattr(post, "port_owner", lambda port: "chrome (pid 42), profile mine")
        said = post._silence(9225, OSError("refused"))
        assert "half open" in said
        assert "profile mine" in said

    def test_a_browser_that_asked_but_is_not_answering_is_named(self, monkeypatch):
        monkeypatch.setattr(post, "_answers", lambda port, host="127.0.0.1": False)
        monkeypatch.setattr(post, "port_owner", lambda port: "chrome (pid 42), profile mine")
        said = post._silence(9225, OSError("refused"))
        assert "chrome (pid 42)" in said
        assert "half open" not in said

    def test_nothing_there_at_all_still_says_how_to_start_one(self, monkeypatch):
        monkeypatch.setattr(post, "_answers", lambda port, host="127.0.0.1": False)
        monkeypatch.setattr(post, "port_owner", lambda port: "")
        said = post._silence(9225, OSError("refused"))
        assert "--remote-debugging-port=9225" in said

    def test_a_browser_with_no_whatsapp_tab_names_whose_browser_it_is(self, monkeypatch):
        monkeypatch.setattr(post, "_cdp_get", lambda *a, **k: [
            {"type": "page", "url": "https://antigravity.google/"},
        ])
        monkeypatch.setattr(post, "port_owner", lambda port: "chrome (pid 42), profile theirs")
        with pytest.raises(post.PostError) as raised:
            post.find_tab(9225)
        assert "profile theirs" in str(raised.value)


# -- what became of the Status -------------------------------------------
#
# The old check asked whether the composer had closed, which is a fact about the
# browser and not about WhatsApp. It said "sent" in four seconds every time it
# ever ran, including at 19:21 on 2026-08-31 for a Status WhatsApp refused: it
# sat in the tray on the web client with no views and never reached the phone.
# These pin the replacement, which reads WhatsApp's own `ack`.


class StorePage:
    """A page whose WhatsApp store answers with a script of prepared replies.

    One reply is consumed per question, and the last one repeats, so a test says
    only as much as it cares about. `None` stands for a browser too busy to answer.
    """

    def __init__(self, answers, *, composer_gone: bool = True) -> None:
        self.answers = list(answers)
        self.asked = 0
        self.composer_gone = composer_gone

    def js_soft(self, expression: str, default=None):
        if "indexedDB.open" in expression:
            self.asked += 1
            answer = self.answers[min(self.asked - 1, len(self.answers) - 1)]
            return None if answer is None else json.dumps(answer)
        if "contenteditable" in expression:
            return self.composer_gone
        return default


def _readable(row):
    return {"readable": True, "row": row}


def _row(msg_id="true_status@broadcast_NEW", *, ack, t=2000):
    return {"id": msg_id, "t": t, "ack": ack}


@pytest.fixture()
def _no_waiting(monkeypatch):
    """Take the two second poll out, so a test is not paced by a real clock."""
    monkeypatch.setattr(post.time, "sleep", lambda _seconds: None)


def test_a_status_whatsapp_accepted_reports_the_seconds(_no_waiting):
    page = StorePage([_readable(_row(ack=post.ACK_SERVER))])
    took = post.confirm_sent(page, None, sent_at=1000, timeout=5.0)
    assert took >= 0


def test_a_status_whatsapp_refused_is_a_failure_not_a_success(_no_waiting):
    page = StorePage([_readable(_row(ack=post.ACK_ERROR))])
    with pytest.raises(post.PostError) as caught:
        post.confirm_sent(page, None, sent_at=1000, timeout=5.0)
    assert "refused" in str(caught.value)
    assert "no views" in str(caught.value)


def test_a_status_still_unanswered_at_the_deadline_is_not_called_sent(_no_waiting):
    page = StorePage([_readable(_row(ack=post.ACK_PENDING))])
    with pytest.raises(post.PostError) as caught:
        post.confirm_sent(page, None, sent_at=1000, timeout=0.05)
    assert "not accepted" in str(caught.value)


def test_the_row_an_earlier_post_left_behind_is_not_this_one(_no_waiting):
    """A previous Status sits in the store, read and accepted. It proves nothing."""
    stale = _row("true_status@broadcast_OLD", ack=3, t=900)
    page = StorePage([_readable(stale)])
    with pytest.raises(post.PostError) as caught:
        post.confirm_sent(page, stale, sent_at=1000, timeout=0.05)
    assert "no record" in str(caught.value)


def test_a_row_older_than_the_send_is_not_this_one(_no_waiting):
    """Nothing to compare against, so the clock has to do the telling apart."""
    page = StorePage([_readable(_row("true_status@broadcast_OLD", ack=3, t=100))])
    with pytest.raises(post.PostError) as caught:
        post.confirm_sent(page, None, sent_at=1000, timeout=0.05)
    assert "no record" in str(caught.value)


def test_a_store_this_tool_cannot_read_is_unconfirmed_never_sent(_no_waiting):
    """A build whose store is shaped differently is not a Status that failed, and
    not one that went out either: the closed composer is no answer (D-071). It is
    unconfirmed, which is never retried, so it cannot post twice."""
    page = StorePage([{"readable": False, "row": None}], composer_gone=True)
    with pytest.raises(post.StatusUnconfirmed):
        post.confirm_sent(page, None, sent_at=1000, timeout=5.0)


def test_a_busy_browser_is_asked_again_rather_than_believed(_no_waiting):
    page = StorePage([None, None, _readable(_row(ack=post.ACK_SERVER))])
    assert post.confirm_sent(page, None, sent_at=1000, timeout=5.0) >= 0


def test_latest_own_status_tells_three_nothings_apart():
    assert post.latest_own_status(StorePage([None])) is None
    assert post.latest_own_status(StorePage([{"readable": False, "row": None}])) is None
    assert post.latest_own_status(StorePage([_readable(None)])) is None
    assert post.latest_own_status(StorePage([_readable(_row(ack=1))]))["ack"] == 1


def test_the_composer_selector_leaves_the_chat_message_box_alone():
    """The caption went into an open conversation while this was a bare selector."""
    assert 'div[contenteditable="true"]' in post.COMPOSER
    assert ':not([data-testid="conversation-compose-box-input"])' in post.COMPOSER
    assert ':not([aria-placeholder="Type a message"])' in post.COMPOSER


# -- trying again, and knowing when not to -------------------------------


def test_a_refusal_is_tried_again(monkeypatch):
    """WhatsApp said no, so nothing went out and a second go cannot double post."""
    tries = []

    def flaky(path, caption, *, port=None, send=True):
        tries.append(port)
        if len(tries) < 3:
            raise post.StatusRefused("WhatsApp refused the Status.")
        return 12.0

    monkeypatch.setattr(post, "post_video", flaky)
    monkeypatch.setattr(post.time, "sleep", lambda _s: None)
    assert post.send_with_retry(Path("clip.mp4"), "cap", port=9230) == 12.0
    assert len(tries) == 3


def test_the_wait_between_tries_doubles(monkeypatch):
    waited = []

    def always_refused(path, caption, *, port=None, send=True):
        raise post.StatusRefused("no")

    monkeypatch.setattr(post, "post_video", always_refused)
    monkeypatch.setattr(post.time, "sleep", lambda s: waited.append(s))
    with pytest.raises(post.StatusRefused):
        post.send_with_retry(Path("clip.mp4"), "cap", attempts=4, base_delay=10.0)
    assert waited == [10.0, 20.0, 40.0]


def test_a_status_that_may_yet_go_out_is_never_sent_twice(monkeypatch):
    """The one failure that must not be retried: a viewer would get it twice."""
    tries = []

    def unconfirmed(path, caption, *, port=None, send=True):
        tries.append(1)
        raise post.StatusUnconfirmed("no answer either way")

    monkeypatch.setattr(post, "post_video", unconfirmed)
    monkeypatch.setattr(post.time, "sleep", lambda _s: None)
    with pytest.raises(post.StatusUnconfirmed):
        post.send_with_retry(Path("clip.mp4"), "cap")
    assert len(tries) == 1


def test_giving_up_says_how_many_times_it_tried(monkeypatch):
    monkeypatch.setattr(post, "post_video", lambda *a, **k: (_ for _ in ()).throw(
        post.StatusRefused("WhatsApp refused the Status.")))
    monkeypatch.setattr(post.time, "sleep", lambda _s: None)
    with pytest.raises(post.StatusRefused) as caught:
        post.send_with_retry(Path("clip.mp4"), "cap", attempts=3, base_delay=1.0)
    assert "3 times" in str(caught.value)


def test_a_refusal_is_told_apart_from_no_answer(_no_waiting):
    """The retry hangs off this distinction, so it is pinned here too."""
    refused = StorePage([_readable(_row(ack=post.ACK_ERROR))])
    with pytest.raises(post.StatusRefused):
        post.confirm_sent(refused, None, sent_at=1000, timeout=5.0)

    pending = StorePage([_readable(_row(ack=post.ACK_PENDING))])
    with pytest.raises(post.StatusUnconfirmed):
        post.confirm_sent(pending, None, sent_at=1000, timeout=0.05)

    assert issubclass(post.StatusRefused, post.PostError)
    assert issubclass(post.StatusUnconfirmed, post.PostError)


def test_a_deleted_status_leaves_a_tombstone_that_is_not_a_status():
    """Deleting one writes a protocol row under the same key prefix, with ack 0.

    Seen for real on 2026-08-31: a delete put `sender_revoke` at the top of the
    range, `latest_own_status` returned it, and its ack 0 would have made the next
    post report itself unaccepted. Both ways of spotting it are in the query.
    """
    assert "v.type !== 'protocol'" in post._LATEST_STATUS
    assert "!v.protocolMessageKey" in post._LATEST_STATUS


def test_the_follow_up_text_gets_the_same_retry(monkeypatch):
    """One run can send two Statuses. Only one of them was being retried, which is
    the audit finding of 2026-08-31: a refused follow up is as safe to send again
    as a refused clip, because a refusal means nothing went out either way."""
    tries = []

    def flaky(text, *, port=None, send=True):
        tries.append(text)
        if len(tries) < 2:
            raise post.StatusRefused("no")
        return 3.0

    monkeypatch.setattr(post, "post_text", flaky)
    monkeypatch.setattr(post.time, "sleep", lambda _s: None)
    assert post.send_text_with_retry("https://youtu.be/x", port=9230) == 3.0
    assert len(tries) == 2


def test_the_follow_up_still_never_retries_an_unconfirmed_one(monkeypatch):
    tries = []

    def unconfirmed(text, *, port=None, send=True):
        tries.append(text)
        raise post.StatusUnconfirmed("no answer either way")

    monkeypatch.setattr(post, "post_text", unconfirmed)
    monkeypatch.setattr(post.time, "sleep", lambda _s: None)
    with pytest.raises(post.StatusUnconfirmed):
        post.send_text_with_retry("https://youtu.be/x")
    assert len(tries) == 1


def test_both_kinds_of_send_share_one_retry_loop():
    """Two copies of it is how one of them ends up with a fix the other misses."""
    import inspect
    for fn in (post.send_with_retry, post.send_text_with_retry):
        assert "_keep_trying(" in inspect.getsource(fn)


def test_send_is_found_by_its_label_now_that_the_icon_is_gone():
    """By 2026-10-24 WhatsApp had dropped `data-icon` from Send, and a load waited
    for a button already on screen. Both composers' labels are matched now:
    "Send 1 selected" for media, a bare "Send" for text. DECISIONS.md D-079."""
    assert '[aria-label^="Send "][aria-label$=" selected"]' in post.SEND_ICON
    assert '[aria-label="Send"]' in post.SEND_ICON
    assert "wds-ic-send" in post.SEND_ICON  # a build that still has the icon


def test_a_typed_chat_reply_is_not_taken_for_an_open_composer():
    """A chat with text typed in it has a bare "Send" too. Taking that for a Status
    composer would back out of the chat before attaching, so the open check
    recognises the text composer by its own close control instead."""
    assert '[aria-label="Send"]' not in post.COMPOSER_OPEN
    assert '[aria-label="Close status posting view"]' in post.COMPOSER_OPEN


def test_the_selectors_survive_being_put_inside_a_quoted_js_string():
    # Every use is `document.querySelector('<selector>')`.
    for selector in (post.SEND_ICON, post.COMPOSER_OPEN, post.COMPOSER):
        assert "'" not in selector
