"""The browser extension, from the Python side: its own tests, and the facts it
shares with the engine and the renderer.

The extension is plain JavaScript with no build step, so the things that can drift
are constants written down twice: the 90 second limit, WhatsApp's control labels,
the renderer's address and chunk size. Each is read out of the JavaScript here and
compared with the Python it has to agree with. The parser's own behaviour is
tested in Node, in `src/test`, and run from here when Node is installed.
See docs/extension.md.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from wastatus import hosted, pipeline, post

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "src"


def source(name: str) -> str:
    return (EXT / name).read_text(encoding="utf-8")


def imported() -> list[str]:
    match = re.search(r"importScripts\(([^)]*)\)", source("sw.js"))
    assert match, "importScripts not found"
    return re.findall(r'"([^"]+)"', match.group(1))


def js_list(text: str, name: str) -> list[str]:
    match = re.search(rf"const {name} = \[(.*?)\];", text, re.S)
    assert match, f"{name} not found"
    return re.findall(r'"([^"]*)"', match.group(1))


def js_string(text: str, name: str) -> str:
    match = re.search(rf"const {name} = ((?:'[^']*'\s*\+?\s*)+);", text)
    assert match, f"{name} not found"
    return "".join(re.findall(r"'([^']*)'", match.group(1)))


@pytest.mark.skipif(not shutil.which("node"), reason="needs Node")
def test_the_parser_passes_its_own_tests():
    """media.js against fragmented MP4 and WebM fed the awkward ways YouTube
    feeds them. The Node suite skips itself without ffmpeg."""
    run = subprocess.run(["node", "--test", *sorted(str(p) for p in (EXT / "test").glob("*.test.js"))],
                         capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-2000:]


@pytest.mark.skipif(not shutil.which("node"), reason="needs Node")
@pytest.mark.parametrize("name", ["media.js", "recorder.js", "bridge.js", "sw.js",
                                  "whatsapp.js", "wa-bridge.js", "popup.js", "config.js",
                                  "queue.js", "custody.js", "place.js", "schedule.js",
                                  "queue-page.js"])
def test_every_script_parses(name):
    run = subprocess.run(["node", "--check", str(EXT / name)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr


class TestTheManifest:
    manifest = json.loads((EXT / "manifest.json").read_text())

    def test_every_file_it_names_exists(self):
        named = [self.manifest["background"]["service_worker"],
                 *self.manifest["icons"].values(),
                 *self.manifest["action"]["default_icon"].values(),
                 *imported(),
                 # Switched off, not deleted: the toolbar button opens SnipShare now.
                 "popup.html", "popup.js"]
        for script in self.manifest["content_scripts"]:
            named += script["js"]
        for name in named:
            assert (EXT / name).is_file(), name

    def test_the_button_opens_the_page_not_the_popup(self):
        assert "default_popup" not in self.manifest["action"]
        assert "chrome.action.onClicked.addListener" in source("sw.js")
        # Still reachable for a token holder, from the button's own menu.
        assert self.manifest["options_ui"] == {"page": "popup.html", "open_in_tab": True}

    def test_the_parser_loads_before_the_recorder_in_the_same_world(self):
        page = [s for s in self.manifest["content_scripts"] if s.get("world") == "MAIN"]
        assert page and page[0]["js"] == ["media.js", "recorder.js"]
        assert page[0]["run_at"] == "document_start"

    def test_the_scripts_injected_later_are_the_ones_on_disk(self):
        for script in ("sw.js", "place.js"):
            for name in re.findall(r'files: \["([^"]+)"\]', source(script)):
                assert (EXT / name).is_file(), name

    def test_the_worker_loads_the_scheduling_modules_before_its_own_code(self):
        """Scheduled Statuses (docs/scheduling.md): the queue's rules, the clips kept
        for it, the placement in WhatsApp and the schedule, in that order."""
        assert imported() == ["config.js", "queue.js", "custody.js", "place.js", "schedule.js"]

    def test_it_asks_for_nothing_it_does_not_use(self):
        """Scheduling added four: notifications for what needs the person, idle for
        not interrupting someone at the keyboard (FR-12), unlimitedStorage for the
        kept clips (Section 8.2), contextMenus for the queue on the button (E13).
        No `background` permission (E13: only if Phase 0 shows it helps)."""
        assert sorted(self.manifest["permissions"]) == [
            "alarms", "contextMenus", "downloads", "idle", "notifications", "scripting",
            "storage", "unlimitedStorage"]
        assert set(self.manifest["host_permissions"]) == {
            "https://www.youtube.com/*", "https://i.ytimg.com/*",
            "https://web.whatsapp.com/*", "http://127.0.0.1/*", "http://localhost/*"}

    def test_only_a_local_copy_may_talk_to_it_until_it_is_built_for_a_site(self):
        assert self.manifest["externally_connectable"] == {
            "matches": ["http://127.0.0.1/*", "http://localhost/*"]}
        assert re.search(r'site: "(http://127\.0\.0\.1:\d+)"', source("config.js"))

    def test_no_real_address_is_written_into_it(self):
        """The repository is kept fit to publish: the site the extension serves is
        written in when it is built, never here. docs/hosted-page.md, Table HP-3."""
        for file in EXT.rglob("*"):
            if file.suffix in (".js", ".json", ".html", ".css"):
                text = file.read_text(encoding="utf-8")
                found = re.findall(r"https?://([a-z0-9.-]+)", text)
                allowed = ("127.0.0.1", "localhost", "www.youtube.com", "youtube.com",
                           "i.ytimg.com", "web.whatsapp.com", "renderer.example.com",
                           "youtu.be", "m.youtube.com", "music.youtube.com")
                assert set(found) <= set(allowed), (file.name, set(found) - set(allowed))

    def test_the_page_asks_for_no_newer_extension_than_this_one(self):
        from wastatus import portal

        def parts(version):
            return tuple(int(p) for p in version.split("."))
        assert parts(portal.EXTENSION_MIN_VERSION) <= parts(self.manifest["version"])


class TestSharedFacts:
    def test_the_longest_clip_is_the_engines(self):
        assert re.search(r"const MAX_LENGTH = (\d+);", source("popup.js")).group(1) == \
            str(int(pipeline.MAX_DURATION))
        assert f"p.end - p.start <= {int(pipeline.MAX_DURATION)}" in source("sw.js")

    def test_whatsapps_labels_match_the_ones_the_tool_posts_with(self):
        text = source("whatsapp.js")
        assert js_list(text, "ADD_STATUS") == list(post.ADD_STATUS)
        assert js_list(text, "PHOTO_ITEM") == list(post.PHOTO_ITEM)
        assert js_string(text, "SEND") == post.SEND_ICON
        assert js_string(text, "COMPOSER_OPEN") == post.COMPOSER_OPEN

    def test_the_size_warning_is_whatsapps_own_ceiling(self):
        from wastatus import render
        found = re.search(r"const WHATSAPP_MAX_BYTES = (\d+);", source("popup.js")).group(1)
        assert int(found) == render.PLATFORM_MAX_BYTES

    def test_no_chunk_is_larger_than_the_renderer_takes(self):
        text = source("sw.js")
        start = eval(re.search(r"const CHUNK_START = ([\d * ]+);", text).group(1))  # noqa: S307
        assert start <= hosted.CHUNK_MAX

    def test_a_request_gives_up_before_cloudflare_does(self):
        """Cloudflare answers 524 after 100 seconds; a chunk must fail first."""
        timeout = int(re.search(r"const REQUEST_TIMEOUT = (\d+);", source("sw.js")).group(1))
        assert timeout < 100_000


def test_a_build_for_a_site_talks_to_that_site_alone(tmp_path):
    import importlib.util
    import zipfile

    spec = importlib.util.spec_from_file_location("build_extension",
                                                  ROOT / "scripts" / "build_extension.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    key = tmp_path / "key.pem"
    build.new_key(key)
    out = tmp_path / "dist" / "snipshare-extension"
    ident = build.build("https://snipshare.example.com/app", key, out)
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["externally_connectable"] == {"matches": ["https://snipshare.example.com/*"]}
    assert "https://snipshare.example.com/*" in manifest["host_permissions"]
    assert not any("127.0.0.1" in h or "localhost" in h for h in manifest["host_permissions"])
    assert 'site: "https://snipshare.example.com"' in (out / "config.js").read_text()
    # The id Chrome will give it is the one printed, and the key is the public half.
    assert re.fullmatch(r"[a-p]{32}", ident)
    assert ident == build.extension_id(__import__("base64").b64decode(manifest["key"]))
    assert b"PRIVATE" not in (out / "manifest.json").read_bytes()
    names = zipfile.ZipFile(tmp_path / "dist" / "snipshare-extension.zip").namelist()
    assert "snipshare-extension/manifest.json" in names
    assert not any("/test/" in n for n in names)
