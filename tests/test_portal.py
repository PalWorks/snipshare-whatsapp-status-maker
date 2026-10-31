"""SnipShare, the hosted page, driven over real HTTP the way a browser drives it.

What these hold in place: nobody gets past the front pages without a session the
owner approved; a session is a cookie plus a value only the page has, so another
site cannot act with it; each person sees only their own clips; the extension's
grants do one thing each; the daily limits hold; and a clip made from what the
extension uploaded is the same engine's clip. Google itself is replaced by a stub:
its checks are `signin.google`'s, tested against the real thing on 2026-10-25 (see
docs/hosted-page.md, Phase 0).
"""

from __future__ import annotations

import hashlib
import http.client
import json
import re
import threading
import time
import urllib.parse

import pytest

from wastatus import accounts, gifs, hosted, notify, portal, signin, stickers

ADMIN = "owner@example.com"


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in ("WASTATUS_PUBLIC_URL", "WASTATUS_RESEND_KEY", "WASTATUS_CHAT_WEBHOOK",
                 "WASTATUS_TURNSTILE_SECRET", "WASTATUS_CLIPS_PER_DAY",
                 "WASTATUS_UPLOAD_MB_PER_DAY", "WASTATUS_TRUST_PROXY",
                 "WASTATUS_GIF_PROVIDER", "WASTATUS_GIPHY_KEY", "WASTATUS_KLIPY_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("WASTATUS_ADMIN_EMAILS", ADMIN)
    monkeypatch.setenv("WASTATUS_SECRET_KEY", "x" * 40)
    monkeypatch.setenv("WASTATUS_GOOGLE_CLIENT_ID", "client.apps.googleusercontent.com")
    monkeypatch.setenv("WASTATUS_EXTENSION_ID", "a" * 32)
    monkeypatch.setenv("WASTATUS_STICKER_DIR", str(tmp_path / "stickers"))
    monkeypatch.setattr(hosted, "FREE_DISK_MIN", 0)

    # Google, as far as these tests are concerned: a credential is "google:EMAIL".
    def google(credential):
        if not credential.startswith("google:"):
            raise accounts.AccessError("that sign-in could not be checked. Try again")
        email = credential.split(":", 1)[1]
        return {"email": email, "name": email.split("@")[0].title(), "sub": "s-" + email}
    monkeypatch.setattr(signin, "google", google)
    told = []
    monkeypatch.setattr(notify, "email", lambda subject, lines, wait=False: told.append(
        ("email", subject, lines)) or True)
    monkeypatch.setattr(notify, "chat", lambda text, wait=False: told.append(
        ("chat", text)) or True)
    return told


@pytest.fixture
def site(env, tmp_path):
    renderer = hosted.Renderer(tmp_path / "data")
    renderer.start()
    made = portal.Portal(tmp_path / "data", renderer)
    server = portal.make_server(made, 0, "127.0.0.1")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    made.port = server.server_address[1]
    yield made
    server.shutdown()
    server.server_close()
    renderer.stop()


class Browser:
    """One person's browser: a cookie jar of one, and the page's own value."""

    def __init__(self, site):
        self.port = site.port
        self.origin = f"http://127.0.0.1:{self.port}"
        self.cookie = ""
        self.token = ""

    def request(self, method, path, body=None, headers=None, origin=True):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        head = dict(headers or {})
        if self.cookie:
            head["Cookie"] = f"{portal.SESSION_COOKIE}={self.cookie}"
        if origin and method != "GET":
            head.setdefault("Origin", self.origin)
        payload = None
        if body is not None:
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            head.setdefault("Content-Type", "application/json")
            head["Content-Length"] = str(len(payload))
        conn.request(method, path, body=payload, headers=head)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        cookie = response.getheader("Set-Cookie") or ""
        found = re.match(rf"{portal.SESSION_COOKIE}=([^;]*)", cookie)
        if found:
            self.cookie = found.group(1)
        return response, data

    def open_call(self, path, body):
        response, data = self.request("POST", path, body, {"X-SnipShare": "1"})
        return response.status, json.loads(data or b"{}")

    def sign_in(self, email):
        status, answer = self.open_call("/api/session", {"credential": f"google:{email}"})
        assert status == 200, answer
        if answer.get("status") == "approved":
            self.load_page()
        return answer

    def load_page(self):
        response, data = self.request("GET", "/app")
        assert response.status == 200, response.status
        self.token = re.search(rb'data-token="([^"]+)"', data).group(1).decode()
        return data.decode()

    def api(self, method, path, body=None):
        response, data = self.request(method, path, body,
                                      {"X-Wastatus-Token": self.token})
        try:
            parsed = json.loads(data or b"{}")
        except json.JSONDecodeError:
            parsed = data
        return response.status, parsed

    def v1(self, method, path, body=None, grant="", headers=None):
        head = {"Authorization": f"Bearer {grant}", **(headers or {})}
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        payload = None
        if body is not None:
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            head["Content-Length"] = str(len(payload))
        conn.request(method, hosted.API + path, body=payload, headers=head)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, data


def approved(site, email):
    site.accounts.add(email, email.split("@")[0].title())
    person = Browser(site)
    person.sign_in(email)
    return person


def upload(person, grant, kind, data):
    status, made = person.v1("POST", "/uploads", {"kind": kind, "size": len(data)}, grant)
    assert status == 201, made
    made = json.loads(made)
    status, body = person.v1("PUT", f"/uploads/{made['id']}", data, grant,
                             {"Content-Range": f"bytes 0-{len(data) - 1}/{len(data)}"})
    assert status == 200, body
    return made["id"]


def artwork_bytes() -> bytes:
    import io

    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (480, 360), "teal").save(buffer, "JPEG")
    return buffer.getvalue()


# -- the pure parts ---------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=abcdefghijk", "abcdefghijk"),
    ("https://youtu.be/abcdefghijk?t=20", "abcdefghijk"),
    ("https://m.youtube.com/watch?v=abcdefghijk&list=PL1", "abcdefghijk"),
    ("https://music.youtube.com/watch?v=abcdefghijk", "abcdefghijk"),
    ("https://www.youtube.com/shorts/abcdefghijk", "abcdefghijk"),
    ("https://www.youtube.com/live/abcdefghijk", "abcdefghijk"),
    ("https://evil.example/watch?v=abcdefghijk", ""),
    ("https://youtube.com.evil.example/watch?v=abcdefghijk", ""),
    ("https://www.youtube.com/watch?v=short", ""),
    ("not a link", ""),
])
def test_a_video_is_named_only_by_youtube(url, expected):
    assert portal.video_id_of(url) == expected


class TestAccounts:
    def test_the_admin_list_is_the_only_authority(self, env, tmp_path, monkeypatch):
        store = accounts.Accounts(tmp_path / "p.db")
        assert store.person(ADMIN).admin and store.person(ADMIN).status == "approved"
        monkeypatch.setenv("WASTATUS_ADMIN_EMAILS", "someone@example.com")
        store.ensure_admins()
        assert not store.person(ADMIN).admin

    def test_a_second_request_notifies_nobody(self, env, tmp_path):
        store = accounts.Accounts(tmp_path / "p.db")
        first, new = store.request_access("A@Example.com ", {"name": "A"})
        assert new and first.email == "a@example.com" and first.status == "pending"
        _, again = store.request_access("a@example.com", {"name": "A"})
        assert not again

    def test_a_session_ends_when_its_person_is_suspended(self, env, tmp_path):
        store = accounts.Accounts(tmp_path / "p.db")
        store.add("a@example.com", "A")
        token = store.start_session("a@example.com")
        assert store.session(token).email == "a@example.com"
        store.decide("a@example.com", "suspended")
        assert store.session(token) is None
        with pytest.raises(accounts.AccessError):
            store.start_session("a@example.com")

    def test_only_hashes_of_sessions_and_grants_are_stored(self, env, tmp_path):
        store = accounts.Accounts(tmp_path / "p.db")
        store.add("a@example.com")
        token = store.start_session("a@example.com")
        grant = store.grant("a@example.com", "upload")
        raw = (tmp_path / "p.db").read_bytes()
        assert token.encode() not in raw and grant.encode() not in raw

    def test_a_grant_does_one_thing(self, env, tmp_path):
        store = accounts.Accounts(tmp_path / "p.db")
        store.add("a@example.com")
        grant = store.grant("a@example.com", "clip", "stem_1")
        assert store.check_grant(grant, "clip", "stem_1")
        assert store.check_grant(grant, "clip", "stem_2") is None
        assert store.check_grant(grant, "upload") is None
        old = store.grant("a@example.com", "upload", seconds=-1)
        assert store.check_grant(old, "upload") is None

    def test_the_upload_allowance_cannot_be_passed_by_racing(self, env, tmp_path,
                                                             monkeypatch):
        monkeypatch.setenv("WASTATUS_UPLOAD_MB_PER_DAY", "1")
        store = accounts.Accounts(tmp_path / "p.db")
        refused = []

        def take():
            try:
                store.reserve_upload("a@example.com", 400_000)
            except accounts.AccessError:
                refused.append(1)
        threads = [threading.Thread(target=take) for _ in range(5)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        assert store.usage("a@example.com")["upload_bytes"] == 800_000
        assert len(refused) == 3

    def test_a_gif_key_is_never_stored_as_itself(self, env, tmp_path):
        store = accounts.Accounts(tmp_path / "p.db")
        store.set_gif_key("a@example.com", "giphy", "the-secret-key-1234")
        assert b"the-secret-key-1234" not in (tmp_path / "p.db").read_bytes()
        assert store.gif_keys("a@example.com") == {"giphy": "the-secret-key-1234"}

    def test_forgetting_leaves_nothing_but_anonymous_reports(self, env, tmp_path):
        store = accounts.Accounts(tmp_path / "p.db")
        store.add("a@example.com")
        store.start_session("a@example.com")
        store.report("capture", "walk", "stuck", email="a@example.com")
        store.forget("a@example.com")
        assert store.person("a@example.com") is None
        assert all(r["email"] == "" for r in store.reports(0))


def test_the_limiter_counts_per_key():
    limit = signin.Limiter()
    assert all(limit.allow("b", "k", 3, 60) for _ in range(3))
    assert not limit.allow("b", "k", 3, 60)
    assert limit.allow("b", "other", 3, 60)


def test_mail_is_written_the_way_gmail_writes_it():
    assert notify.gmail_html(["One <b>", "", "Two"]) == (
        '<div dir="ltr"><div>One &lt;b&gt;</div><div><br></div><div>Two</div></div>')


# -- the public pages -------------------------------------------------------------

class TestPages:
    @pytest.mark.parametrize("path", ["/", "/install", "/privacy", "/terms", "/signup",
                                      "/signin"])
    def test_every_public_page_answers_with_a_policy(self, site, path):
        response, data = Browser(site).request("GET", path)
        assert response.status == 200
        policy = response.getheader("Content-Security-Policy")
        assert "default-src 'self'" in policy and "frame-ancestors 'none'" in policy
        assert response.getheader("X-Frame-Options") == "DENY"
        text = data.decode()
        assert "{{" not in text, "a placeholder reached the page"
        assert "SnipShare" in text

    def test_the_requirement_is_said_before_anyone_signs_up(self, site):
        for path in ("/", "/signup", "/signin", "/install"):
            text = Browser(site).request("GET", path)[1].decode()
            assert "Google Chrome on a computer" in text, path

    def test_a_page_that_does_not_exist_says_so(self, site):
        response, data = Browser(site).request("GET", "/nothing")
        assert response.status == 404 and b"no page at this address" in data

    def test_the_tool_needs_a_session(self, site):
        response, _ = Browser(site).request("GET", "/app")
        assert response.status == 303
        assert response.getheader("Location") == "/signin?next=/app"

    def test_the_admin_page_is_the_admins(self, site):
        person = approved(site, "a@example.com")
        response, _ = person.request("GET", "/admin")
        assert response.status == 303 and response.getheader("Location") == "/app"
        admin = Browser(site)
        admin.sign_in(ADMIN)
        assert admin.request("GET", "/admin")[0].status == 200


# -- getting in -----------------------------------------------------------------

class TestAccess:
    def test_a_request_tells_the_owner_once(self, site, env):
        visitor = Browser(site)
        status, answer = visitor.open_call("/api/signup", {
            "name": "Ravi", "email": "ravi@example.com", "use": "songs", "chrome": True})
        assert status == 200 and answer == {"status": "pending", "new": True}
        assert [kind for kind, *_ in env] == ["email", "chat"]
        subject, lines = env[0][1], env[0][2]
        assert "Ravi" in subject and any("typed, not checked" in line for line in lines)
        status, answer = visitor.open_call("/api/signup", {"name": "Ravi",
                                                           "email": "ravi@example.com"})
        # The owner is told once; the typed address is answered the same either way.
        assert answer == {"status": "pending", "new": True} and len(env) == 2

    def test_a_typed_address_never_says_how_that_account_stands(self, site):
        site.accounts.add("member@example.com", "Member")
        site.accounts.request_access("held@example.com", {"name": "Held"})
        site.accounts.decide("held@example.com", "suspended")
        visitor = Browser(site)
        for email in ("member@example.com", "held@example.com", "nobody@example.com"):
            status, answer = visitor.open_call("/api/signup", {"name": "X", "email": email})
            assert status == 200 and answer == {"status": "pending", "new": True}

    def test_another_site_cannot_send_the_form(self, site):
        visitor = Browser(site)
        response, _ = visitor.request("POST", "/api/signup", {"name": "X", "email": "x@example.com"},
                                      {"X-SnipShare": "1", "Origin": "https://evil.example"})
        assert response.status == 403
        response, _ = visitor.request("POST", "/api/signup", {"name": "X", "email": "x@example.com"})
        assert response.status == 403, "the custom header is required"

    def test_signing_in_says_where_a_person_stands(self, site):
        visitor = Browser(site)
        assert visitor.sign_in("new@example.com")["status"] == "unknown"
        site.accounts.request_access("new@example.com", {"name": "New"})
        assert visitor.sign_in("new@example.com")["status"] == "pending"
        assert not visitor.cookie
        site.accounts.decide("new@example.com", "approved")
        assert visitor.sign_in("new@example.com")["status"] == "approved"
        assert visitor.cookie and visitor.token

    def test_the_session_cookie_is_locked_down(self, site):
        site.accounts.add("a@example.com")
        visitor = Browser(site)
        response, _ = visitor.request("POST", "/api/session",
                                      {"credential": "google:a@example.com"},
                                      {"X-SnipShare": "1"})
        cookie = response.getheader("Set-Cookie")
        for part in ("HttpOnly", "SameSite=Lax", "Path=/", "Secure"):
            assert part in cookie

    def test_signing_up_with_google_when_already_in_signs_in(self, site):
        site.accounts.add("a@example.com")
        visitor = Browser(site)
        status, answer = visitor.open_call("/api/signup", {
            "credential": "google:a@example.com", "name": "A"})
        assert answer["status"] == "approved" and visitor.cookie

    def test_signing_out_ends_the_session_on_the_server(self, site):
        person = approved(site, "a@example.com")
        old = person.cookie
        person.open_call("/api/signout", {})
        person.cookie = old
        assert person.api("GET", "/api/state")[0] == 403


# -- the page's own API -----------------------------------------------------------

class TestPageApi:
    def test_the_page_carries_its_session_value_and_the_hosted_script(self, site):
        person = approved(site, "a@example.com")
        page = person.load_page()
        assert 'data-hosted="1"' in page and "/hosted.js" in page
        assert "<title>SnipShare</title>" in page
        assert person.token == portal.csrf_for(person.cookie)

    def test_the_page_policy_allows_its_one_inline_script_by_hash(self, site):
        person = approved(site, "a@example.com")
        response, _ = person.request("GET", "/app")
        assert "'sha256-" in response.getheader("Content-Security-Policy")
        assert "'unsafe-inline'" not in response.getheader(
            "Content-Security-Policy").split("script-src")[1].split(";")[0]

    def test_a_cookie_alone_is_not_enough(self, site):
        person = approved(site, "a@example.com")
        response, _ = person.request("GET", "/api/state")
        assert response.status == 403
        person.token = "wrong"
        assert person.api("GET", "/api/state")[0] == 403

    def test_another_site_cannot_post_with_the_session(self, site):
        person = approved(site, "a@example.com")
        response, _ = person.request("POST", "/api/caption", {"stem": "x", "caption": "y"},
                                     {"X-Wastatus-Token": person.token,
                                      "Origin": "https://evil.example"})
        assert response.status == 403

    def test_state_is_the_persons_own(self, site):
        person = approved(site, "a@example.com")
        status, state = person.api("GET", "/api/state")
        assert status == 200 and state["hosted"] is True
        assert state["me"]["email"] == "a@example.com"
        assert state["quota"]["clips_limit"] == 10
        assert state["extension"]["id"] == "a" * 32
        assert state["out"] == "" and state["host"] == ""

    @pytest.mark.parametrize("path", ["/api/post", "/api/browser"])
    def test_what_the_server_cannot_do_is_not_offered(self, site, path):
        person = approved(site, "a@example.com")
        status, answer = person.api("POST", path, {"stem": "x"})
        assert status == 404

    def test_a_render_without_a_capture_is_refused(self, site):
        person = approved(site, "a@example.com")
        status, answer = person.api("POST", "/api/render",
                                    {"url": "https://youtu.be/abcdefghijk", "start": "20",
                                     "duration": 3})
        assert status == 400 and "extension" in answer["error"]

    def test_the_words_are_cleaned_by_the_same_rules(self, site):
        person = approved(site, "a@example.com")
        status, words = person.api("POST", "/api/words", {
            "url": "https://youtu.be/abcdefghijk",
            "title": "Some Song (Official Video)", "channel": "Some Singer - Topic"})
        assert status == 200
        assert words["title"] == "Some Song" and words["channel"] == "Some Singer"

    def test_the_gif_search_uses_only_the_persons_own_key(self, site, monkeypatch):
        monkeypatch.setenv("WASTATUS_GIF_PROVIDER", "giphy")
        monkeypatch.setenv("WASTATUS_GIPHY_KEY", "the owner's key")
        person = approved(site, "a@example.com")
        status, state = person.api("GET", "/api/state")
        assert state["gifs"] == {}, "the owner's key must never serve someone else"
        seen = []
        monkeypatch.setattr(gifs, "search", lambda q, limit=40, large=False: seen.append(
            gifs.key_for("klipy")) or [])
        status, answer = person.api("POST", "/api/gifkey", {"provider": "klipy",
                                                            "key": "persons-own"})
        assert status == 200 and seen == ["persons-own"]
        status, state = person.api("GET", "/api/state")
        assert state["gifs"]["provider"] == "klipy"
        assert site.accounts.gif_keys("a@example.com") == {"klipy": "persons-own"}


# -- the extension's part -------------------------------------------------------

class TestGrants:
    def test_a_grant_carries_the_window_the_render_will_use(self, site):
        person = approved(site, "a@example.com")
        status, granted = person.api("POST", "/api/grant", {
            "purpose": "upload",
            "window": {"url": "https://youtu.be/abcdefghijk?t=20", "duration": 15}})
        assert status == 200, granted
        assert (granted["video_id"], granted["start"], granted["end"]) == (
            "abcdefghijk", 20.0, 35.0)
        assert granted["server"] == person.origin

    def test_a_bad_window_is_refused_before_anything_is_read(self, site):
        person = approved(site, "a@example.com")
        status, answer = person.api("POST", "/api/grant", {
            "purpose": "upload", "window": {"url": "https://youtu.be/abcdefghijk",
                                            "start": "0:10", "end": "0:05"}})
        assert status == 400

    def test_an_upload_grant_cannot_ask_for_a_popup_job(self, site):
        person = approved(site, "a@example.com")
        _, granted = person.api("POST", "/api/grant", {
            "purpose": "upload", "window": {"url": "https://youtu.be/abcdefghijk",
                                            "duration": 5}})
        status, _ = person.v1("POST", "/jobs", {"video_id": "abcdefghijk"}, granted["grant"])
        assert status == 401
        status, _ = person.v1("GET", "/me", grant=granted["grant"])
        assert status == 401

    def test_uploads_count_against_the_day(self, site, monkeypatch):
        monkeypatch.setenv("WASTATUS_UPLOAD_MB_PER_DAY", "1")
        person = approved(site, "a@example.com")
        _, granted = person.api("POST", "/api/grant", {
            "purpose": "upload", "window": {"url": "https://youtu.be/abcdefghijk",
                                            "duration": 5}})
        upload(person, granted["grant"], "audio", b"x" * 900_000)
        status, body = person.v1("POST", "/uploads", {"kind": "audio", "size": 200_000},
                                 granted["grant"])
        assert status == 429 and b"limit" in body


class TestRendering:
    def make(self, site, person, captured_media, **form):
        _, granted = person.api("POST", "/api/grant", {
            "purpose": "upload", "window": {"url": "https://youtu.be/abcdefghijk",
                                            "start": "20", "duration": 3}})
        audio = upload(person, granted["grant"], "audio", captured_media["audio"].read_bytes())
        art = upload(person, granted["grant"], "artwork", artwork_bytes())
        body = {"url": "https://youtu.be/abcdefghijk", "start": "20", "duration": 3,
                "captured": {"video_id": "abcdefghijk", "title": "A Song",
                             "channel": "A Singer", "duration": 40, "audio": audio,
                             "artwork": art}, **form}
        return person.api("POST", "/api/render", body)

    def finish(self, person, task_id):
        deadline = time.time() + 120
        while time.time() < deadline:
            status, task = person.api("GET", f"/api/task?id={task_id}")
            if task["status"] != "running":
                return task
            time.sleep(0.3)
        raise AssertionError("never finished")

    def test_a_clip_from_the_capture_is_the_persons_alone(self, site, captured_media):
        alice = approved(site, "alice@example.com")
        bob = approved(site, "bob@example.com")
        status, started = self.make(site, alice, captured_media)
        assert status == 200, started
        task = self.finish(alice, started["id"])
        assert task["status"] == "done", task
        stem = task["result"]["stem"]
        assert task["result"]["title"] == "A Song"
        assert bob.api("GET", "/api/state")[1]["clips"] == []
        assert [c["stem"] for c in alice.api("GET", "/api/state")[1]["clips"]] == [stem]
        response, data = alice.request(
            "GET", f"/api/clip?stem={stem}&t={urllib.parse.quote(alice.token)}")
        assert response.status == 200 and data[4:8] == b"ftyp"
        response, _ = bob.request("GET", f"/api/clip?stem={stem}&t={bob.token}")
        assert response.status == 404
        # Counted, and the uploads spent and gone.
        assert site.accounts.usage("alice@example.com")["clips"] == 1
        assert not site.renderer.uploads
        assert not list((site.users_dir / accounts.person_id("alice@example.com")
                         / "work").iterdir())

        # The extension fetches it with a grant for that clip, and only that clip.
        _, granted = alice.api("POST", "/api/grant", {"purpose": "clip", "stem": stem})
        status, data = alice.v1("GET", f"/clip?stem={stem}", grant=granted["grant"])
        assert status == 200 and data[4:8] == b"ftyp"
        status, _ = bob.v1("GET", f"/clip?stem={stem}x", grant=granted["grant"])
        assert status == 401
        status, _ = bob.api("POST", "/api/grant", {"purpose": "clip", "stem": stem})
        assert status == 404

    def test_the_capture_must_be_of_the_linked_video(self, site, captured_media):
        person = approved(site, "a@example.com")
        status, answer = self.make(site, person, captured_media,
                                   url="https://youtu.be/zyxwvutsrqp")
        assert status == 400 and "different video" in answer["error"]
        # Refused before anything was spent: the uploads are still there to use.
        assert len(site.renderer.uploads) == 2

    def test_the_days_clips_are_a_limit(self, site, captured_media, monkeypatch):
        person = approved(site, "a@example.com")
        site.accounts._count("a@example.com", "clips", 10)
        status, answer = person.api("POST", "/api/grant", {
            "purpose": "upload", "window": {"url": "https://youtu.be/abcdefghijk",
                                            "duration": 5}})
        assert status == 429 and "today's 10 clips" in answer["error"]

    def test_the_hourly_cap_holds_across_everybody(self, site, captured_media,
                                                   monkeypatch):
        monkeypatch.setenv("WASTATUS_RENDERS_PER_HOUR", "1")
        person = approved(site, "a@example.com")
        _, granted = person.api("POST", "/api/grant", {
            "purpose": "upload", "window": {"url": "https://youtu.be/abcdefghijk",
                                            "start": "20", "duration": 3}})
        audio = upload(person, granted["grant"], "audio", captured_media["audio"].read_bytes())
        art = upload(person, granted["grant"], "artwork", artwork_bytes())
        site._renders.append(time.time())    # somebody else took the hour's last place
        status, answer = person.api("POST", "/api/render", {
            "url": "https://youtu.be/abcdefghijk", "start": "20", "duration": 3,
            "captured": {"video_id": "abcdefghijk", "title": "T", "channel": "C",
                         "duration": 40, "audio": audio, "artwork": art}})
        assert status == 429 and "this hour" in answer["error"]
        # And asked before anything is read, the next time.
        status, answer = person.api("POST", "/api/grant", {
            "purpose": "upload", "window": {"url": "https://youtu.be/abcdefghijk",
                                            "duration": 3}})
        assert status == 429 and "this hour" in answer["error"]


class TestAccount:
    def test_deleting_an_account_takes_everything(self, site):
        person = approved(site, "a@example.com")
        folder = site.users_dir / accounts.person_id("a@example.com")
        (folder / "out").mkdir(parents=True)
        (folder / "out" / "x.mp4").write_bytes(b"x")
        status, _ = person.api("POST", "/api/account/delete", {"confirm": "wrong@example.com"})
        assert status == 400
        status, _ = person.api("POST", "/api/account/delete", {"confirm": "a@example.com"})
        assert status == 200
        assert site.accounts.person("a@example.com") is None and not folder.exists()

    def test_only_the_admin_decides(self, site):
        person = approved(site, "a@example.com")
        site.accounts.request_access("b@example.com", {"name": "B"})
        status, _ = person.api("POST", "/api/admin/decide",
                               {"email": "b@example.com", "status": "approved"})
        assert status == 403
        admin = Browser(site)
        admin.sign_in(ADMIN)
        status, answer = admin.api("POST", "/api/admin/decide",
                                   {"email": "b@example.com", "status": "approved"})
        assert status == 200 and answer["status"] == "approved"
        status, overview = admin.api("GET", "/api/admin")
        assert status == 200 and {p["email"] for p in overview["people"]} >= {
            "a@example.com", "b@example.com", ADMIN}

    def test_a_failure_report_carries_no_video(self, site):
        person = approved(site, "a@example.com")
        status, _ = person.api("POST", "/api/report", {
            "source": "capture", "phase": "walk", "code": "stuck",
            "versions": "ext 2.0.0"})
        assert status == 200
        stored = site.accounts.reports(0, "capture")[0]
        assert (stored["phase"], stored["code"]) == ("walk", "stuck")


def test_a_users_stickers_are_their_own(site):
    import base64
    import io

    from PIL import Image
    alice = approved(site, "alice@example.com")
    bob = approved(site, "bob@example.com")
    buffer = io.BytesIO()
    Image.new("RGBA", (64, 64), "red").save(buffer, "PNG")
    status, saved = alice.api("POST", "/api/sticker", {
        "name": "dot", "data": base64.b64encode(buffer.getvalue()).decode()})
    assert status == 200, saved
    assert any(s["id"] == saved["id"] for s in alice.api("GET", "/api/stickers?q=")[1]["stickers"])
    assert not any(s["id"] == saved["id"] for s in bob.api("GET", "/api/stickers?q=")[1]["stickers"])
    assert stickers.personal.get() is None, "a request must not leave its person behind"


# -- found by the audit of 2026-10-25 ---------------------------------------------

def test_sign_in_never_sends_anybody_to_another_site():
    import pathlib
    source = (pathlib.Path(portal.__file__).parent / "pages" / "site.js").read_text()
    pattern = re.search(r"return /(.+?)/\.test\(asked\)", source).group(1).replace("\\/", "/")
    for safe in ("/app", "/admin"):
        assert re.fullmatch(pattern, safe)
    for unsafe in ("//evil.example", "/\\evil.example", "/\\/evil", "https://evil.example",
                   "/app?x=//evil", "javascript:alert(1)"):
        assert not re.fullmatch(pattern, unsafe), unsafe


def test_refused_uploads_cost_nobody_a_place_in_the_hour(site, monkeypatch):
    monkeypatch.setenv("WASTATUS_RENDERS_PER_HOUR", "1")
    person = approved(site, "a@example.com")
    body = {"url": "https://youtu.be/abcdefghijk", "start": "20", "duration": 3,
            "captured": {"video_id": "abcdefghijk", "title": "T", "channel": "C",
                         "duration": 40, "audio": "a" * 24, "artwork": "b" * 24}}
    for _ in range(3):
        status, answer = person.api("POST", "/api/render", body)
        assert status == 404, answer
    assert not site._renders


def test_google_being_unreachable_is_said_as_such(site, monkeypatch):
    def down(credential):
        raise signin.Unavailable("Google sign-in cannot be reached right now")
    monkeypatch.setattr(signin, "google", down)
    status, answer = Browser(site).open_call("/api/session", {"credential": "x"})
    assert status == 503 and "cannot be reached" in answer["error"]


def test_another_cookie_on_the_site_does_not_sign_anybody_out(site):
    person = approved(site, "a@example.com")
    response, _ = person.request("GET", "/api/state", headers={
        "X-Wastatus-Token": person.token,
        "Cookie": f'g_state={{"i_l":0}}; {portal.SESSION_COOKIE}={person.cookie}; x=a b'})
    assert response.status == 200


def test_an_upload_given_up_gives_its_allowance_back(site):
    person = approved(site, "a@example.com")
    _, granted = person.api("POST", "/api/grant", {
        "purpose": "upload", "window": {"url": "https://youtu.be/abcdefghijk", "duration": 5}})
    status, made = person.v1("POST", "/uploads", {"kind": "audio", "size": 1_000_000},
                             granted["grant"])
    upload_id = json.loads(made)["id"]
    person.v1("PUT", f"/uploads/{upload_id}", b"x" * 1000, granted["grant"],
              {"Content-Range": "bytes 0-999/1000000"})
    assert site.accounts.usage("a@example.com")["upload_bytes"] == 1_000_000
    status, _ = person.v1("DELETE", f"/uploads/{upload_id}", grant=granted["grant"])
    assert status == 200
    assert site.accounts.usage("a@example.com")["upload_bytes"] == 1000


def test_an_upload_grant_lasts_as_long_as_the_upload_keeps_going(env, tmp_path):
    store = accounts.Accounts(tmp_path / "p.db")
    store.add("a@example.com")
    grant = store.grant("a@example.com", "upload", seconds=30)
    assert store.check_grant(grant, "upload", renew=True)
    row = store._one("select expires from grants")
    assert row["expires"] > time.time() + accounts.GRANT_SECONDS - 5


def test_deleting_an_account_mid_render_leaves_nothing(site, captured_media):
    person = approved(site, "a@example.com")
    status, started = TestRendering().make(site, person, captured_media)
    assert status == 200, started
    person.api("POST", "/api/account/delete", {"confirm": "a@example.com"})
    time.sleep(1)
    assert not (site.users_dir / accounts.person_id("a@example.com")).exists()
    assert site.accounts.usage_table() == []


def test_notifications_name_themselves(monkeypatch):
    """Cloudflare, in front of Resend, refuses Python's default User-Agent."""
    seen = {}

    class Answer:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opened(request, timeout=0):
        seen.update(request.headers)
        return Answer()
    monkeypatch.setattr("urllib.request.urlopen", opened)
    notify._post("https://api.example.com", {}, {})
    assert "Python" not in seen.get("User-agent", "Python")


# -- found by the master audit of 2026-10-25 -----------------------------------------

def test_a_body_without_a_length_cannot_poison_the_next_request(site):
    import socket
    person = approved(site, "a@example.com")
    with socket.create_connection(("127.0.0.1", site.port), timeout=10) as raw:
        raw.sendall((
            "POST /api/caption HTTP/1.1\r\nHost: 127.0.0.1\r\nTransfer-Encoding: chunked\r\n"
            f"Cookie: {portal.SESSION_COOKIE}={person.cookie}\r\nX-Wastatus-Token: {person.token}\r\n"
            f"Origin: {person.origin}\r\nContent-Type: application/json\r\n\r\n"
            "c\r\n{\"stem\":\"x\"}\r\n0\r\n\r\n"
            "GET /api/v1/health HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n").encode())
        answer = b""
        while True:
            chunk = raw.recv(65536)
            if not chunk:
                break
            answer += chunk
    assert answer.startswith(b"HTTP/1.1 411")
    assert b"400 Bad request" not in answer   # the connection ended; nothing was misread


def test_a_report_cannot_page_the_chat_space(site, env):
    people = [approved(site, f"p{i}@example.com") for i in range(2)]
    for person in people + people[:1]:
        person.api("POST", "/api/report", {"source": "capture", "phase": "walk",
                                           "code": "<users/all> " + "x" * 300})
    texts = [text for kind, text, *rest in [(e[0], e[1]) for e in env] if kind == "chat"]
    assert texts and all("<users/all>" not in text for text in texts)
    assert all(len(r["code"]) <= 80 for r in site.accounts.reports(0))


def test_an_admin_list_that_is_not_set_demotes_nobody(env, tmp_path, monkeypatch):
    store = accounts.Accounts(tmp_path / "p.db")
    monkeypatch.delenv("WASTATUS_ADMIN_EMAILS")
    store.ensure_admins()
    assert store.person(ADMIN).admin


def test_the_state_names_a_render_the_page_lost_track_of(site, captured_media):
    person = approved(site, "a@example.com")
    status, started = TestRendering().make(site, person, captured_media)
    assert status == 200
    assert person.api("GET", "/api/state")[1]["rendering"] in (started["id"], "")
    TestRendering().finish(person, started["id"])
    assert person.api("GET", "/api/state")[1]["rendering"] == ""


def test_a_clip_opens_on_its_picture_not_on_black(site, captured_media):
    """WhatsApp shows the first frame before anybody presses play. D-094."""
    import inspect
    import subprocess

    from PIL import Image

    from wastatus import render
    assert not re.search(r"(?<!a)fade=t=in", inspect.getsource(render))
    person = approved(site, "a@example.com")
    status, started = TestRendering().make(site, person, captured_media)
    task = TestRendering().finish(person, started["id"])
    clip = site.users_dir / accounts.person_id("a@example.com") / "out" / f"{task['result']['stem']}.mp4"
    first = clip.with_suffix(".first.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip), "-frames:v", "1",
                    str(first)], check=True)
    pixels = Image.open(first).convert("L")
    assert sum(pixels.getdata()) / (pixels.width * pixels.height) > 20


# -- the account page, 2026-10-25 ---------------------------------------------------

class TestAccountPage:
    def test_it_is_behind_a_session_and_carries_its_value(self, site):
        response, _ = Browser(site).request("GET", "/account")
        assert response.status == 303
        assert response.getheader("Location") == "/signin?next=/account"
        person = approved(site, "a@example.com")
        response, data = person.request("GET", "/account")
        page = data.decode()
        assert response.status == 200 and "{{" not in page
        assert f'data-token="{person.token}"' in page
        for section in ("profile", "history", "scheduled", "keys", "feedback", "extension",
                        "data"):
            assert f'id="{section}"' in page

    def test_its_policy_frames_the_extensions_queue_and_nothing_else(self, site):
        """Scheduled Statuses shows the extension's queue page in a frame
        (docs/account-page.md, Table AP-8): that one extension is added to frame-src,
        and every other directive is the shared policy's, frame-ancestors included."""
        person = approved(site, "a@example.com")
        response, _ = person.request("GET", "/account")
        policy = response.getheader("Content-Security-Policy")
        directives = dict(d.strip().split(" ", 1) for d in policy.split(";"))
        shared = dict(d.strip().split(" ", 1) for d in portal.PAGE_POLICY.split(";"))
        assert directives["frame-src"] == shared["frame-src"] + " chrome-extension://" + "a" * 32
        assert {k: v for k, v in directives.items() if k != "frame-src"} == \
            {k: v for k, v in shared.items() if k != "frame-src"}
        assert directives["frame-ancestors"] == "'none'"
        assert response.getheader("X-Frame-Options") == "DENY"
        # The other pages do not gain it.
        for path in ("/", "/install", "/admin"):
            other = Browser(site).request("GET", path)[0].getheader("Content-Security-Policy") or ""
            assert "chrome-extension:" not in other, path

    @pytest.mark.parametrize("value", ["", "A" * 32, "a" * 31, "q" * 32,
                                       "a" * 32 + "; script-src *", "a" * 32 + " https://x"])
    def test_an_extension_id_that_is_not_chromes_shape_adds_nothing(self, value):
        assert portal.account_policy(value) == portal.PAGE_POLICY

    def test_the_section_is_offered_only_with_the_pilot_switch(self, site):
        person = approved(site, "a@example.com")
        _, data = person.api("GET", "/api/account")
        assert data["scheduling"] == {"enabled": False}
        admin = Browser(site)
        admin.sign_in(ADMIN)
        _, data = admin.api("GET", "/api/account")
        assert data["scheduling"] == {"enabled": True}
        admin.api("POST", "/api/admin/limits", {"email": "a@example.com",
                                                "changes": {"scheduling": True}})
        _, data = person.api("GET", "/api/account")
        assert data["scheduling"] == {"enabled": True}
        # The page has the section, its link hidden until the switch says otherwise.
        page = person.request("GET", "/account")[1].decode()
        link = re.search(r'<a [^>]*data-section="scheduled"[^>]*>', page).group(0)
        assert re.search(r"\shidden[\s>]", link)
        assert 'id="scheduled"' in page and "Scheduled Statuses" in page

    def test_the_tool_page_links_to_it(self):
        import pathlib
        hosted_js = (pathlib.Path(portal.__file__).parent / "pages" / "hosted.js").read_text()
        assert 'link.href = "/account"' in hosted_js and "accountPanel" not in hosted_js

    def test_the_overview_never_shows_a_key(self, site, monkeypatch):
        monkeypatch.setattr(gifs, "search", lambda q, limit=40, large=False: [])
        person = approved(site, "a@example.com")
        person.api("POST", "/api/gifkey", {"provider": "giphy", "key": "secret-giphy-1234"})
        status, data = person.api("GET", "/api/account")
        assert status == 200
        assert data["gifs"]["keys"]["giphy"]["ends"] == "1234"
        assert "secret-giphy" not in json.dumps(data)
        assert data["profile"]["email"] == "a@example.com"

    def test_a_name_can_be_changed_and_not_emptied(self, site):
        person = approved(site, "a@example.com")
        status, answer = person.api("POST", "/api/account/profile", {"name": "  Asha   K "})
        assert status == 200 and answer["name"] == "Asha K"
        status, _ = person.api("POST", "/api/account/profile", {"name": " "})
        assert status == 400


class TestTwoGifKeys:
    def test_both_keys_are_kept_and_both_is_the_default(self, site, monkeypatch):
        monkeypatch.setattr(gifs, "search", lambda q, limit=40, large=False: [])
        person = approved(site, "a@example.com")
        person.api("POST", "/api/gifkey", {"provider": "giphy", "key": "g-key"})
        status, data = person.api("POST", "/api/gifkey", {"provider": "klipy", "key": "k-key"})
        assert set(data["keys"]) == {"giphy", "klipy"} and data["source"] == "both"
        assert site.accounts.gif_keys("a@example.com") == {"giphy": "g-key", "klipy": "k-key"}
        status, data = person.api("POST", "/api/gifkey/source", {"source": "klipy"})
        assert data["source"] == "klipy" and data["credit"]["placeholder"] == "Search KLIPY"
        status, data = person.api("POST", "/api/gifkey/delete", {"provider": "klipy"})
        # The choice falls back to what is left, rather than leaving search dead.
        assert set(data["keys"]) == {"giphy"} and data["source"] == "giphy"

    def test_the_shelf_switch_is_the_persons_own_choice(self, site, monkeypatch):
        monkeypatch.setattr(gifs, "search", lambda q, limit=40, large=False: [])
        person = approved(site, "a@example.com")
        person.api("POST", "/api/gifkey", {"provider": "giphy", "key": "g"})
        person.api("POST", "/api/gifkey", {"provider": "klipy", "key": "k"})
        status, credit = person.api("POST", "/api/gif/provider", {"provider": "giphy"})
        assert status == 200 and credit["provider"] == "giphy"
        assert site.accounts.gif_source("a@example.com") == "giphy"
        assert [c["name"] for c in credit["choices"]] == ["giphy", "klipy", "both"]

    def test_an_old_one_key_database_is_brought_forward(self, env, tmp_path):
        import sqlite3
        db = sqlite3.connect(tmp_path / "p.db")
        db.executescript("""
            create table people (email text primary key, name text not null default '',
              status text not null, role text not null default 'user',
              answers text not null default '{}', google_sub text, created real not null,
              decided real, last_seen real);
            create table gif_keys (email text primary key, provider text not null,
              secret blob not null, created real not null);
        """)
        db.execute("insert into people (email, status, created) values ('a@example.com', 'approved', 1)")
        db.execute("insert into gif_keys values ('a@example.com', 'giphy', ?, 1)",
                   (accounts._seal("old-key"),))
        db.commit()
        db.close()
        store = accounts.Accounts(tmp_path / "p.db")
        assert store.gif_keys("a@example.com") == {"giphy": "old-key"}
        store.set_gif_key("a@example.com", "klipy", "new-key")
        assert set(store.gif_keys("a@example.com")) == {"giphy", "klipy"}
        assert store.gif_source("a@example.com") == ""


def test_a_search_of_both_asks_both_and_mixes_them(monkeypatch):
    def fake(name):
        def search(query, limit, key, large=False):
            return [gifs.Gif(id=f"{key}{i}", title=name, preview="p", full="f", width=1,
                             height=1, bytes=1) for i in range(3)]
        return search
    monkeypatch.setitem(gifs.PROVIDERS, "giphy", gifs.PROVIDERS["giphy"].__class__(
        **{**gifs.PROVIDERS["giphy"].__dict__, "search": fake("giphy")}))
    monkeypatch.setitem(gifs.PROVIDERS, "klipy", gifs.PROVIDERS["klipy"].__class__(
        **{**gifs.PROVIDERS["klipy"].__dict__, "search": fake("klipy")}))
    token = gifs.personal.set(gifs.Personal(keys={"giphy": "g", "klipy": "k"}, choice="both"))
    try:
        found = gifs.search("cat")
        assert [one.provider for one in found] == ["giphy", "klipy"] * 3
        assert len({one.key for one in found}) == 6
        assert gifs.credit()["placeholder"].startswith("Search KLIPY")
    finally:
        gifs.personal.reset(token)


def test_history_remembers_every_clip_and_its_failures(site, captured_media):
    person = approved(site, "a@example.com")
    status, started = TestRendering().make(site, person, captured_media)
    TestRendering().finish(person, started["id"])
    status, data = person.api("GET", "/api/account/history")
    assert status == 200
    row = data["clips"][0]
    assert row["ok"] and row["video_id"] == "abcdefghijk" and row["title"] == "A Song"
    assert row["kept"] is True and (row["start"], row["end"]) == (20.0, 23.0)
    assert len(data["days"]) == 14 and data["days"][-1]["clips"] == 1
    site.forget("a@example.com")
    assert site.accounts.history("a@example.com") == []


def test_feedback_reaches_the_owner_with_the_person_to_reply_to(site, monkeypatch):
    import base64
    import io

    from PIL import Image
    sent = []
    monkeypatch.setattr(notify, "email", lambda subject, lines, wait=False, reply_to="",
                        attachments=None: sent.append((subject, lines, reply_to, attachments)) or True)
    person = approved(site, "a@example.com")
    status, _ = person.api("POST", "/api/feedback", {"kind": "idea", "subject": "Hi", "message": "x"})
    assert status == 400, "a message of a few words at least"
    status, _ = person.api("POST", "/api/feedback", {"kind": "idea", "message": "a real message"})
    assert status == 400, "a subject is needed"
    shot = io.BytesIO()
    Image.new("RGB", (40, 30), "red").save(shot, "PNG")
    status, answer = person.api("POST", "/api/feedback", {
        "kind": "problem", "subject": "Capture stops", "name": "Asha",
        "message": "The capture stops <users/all>", "code": "capture/read",
        "attachments": [{"name": "s.png", "data": "data:image/png;base64,"
                         + base64.b64encode(shot.getvalue()).decode()}]})
    assert status == 200 and answer["sent"]
    subject, lines, reply_to, attachments = sent[0]
    assert reply_to == "a@example.com" and "problem: Capture stops (Asha)" in subject
    assert any("capture/read" in line for line in lines)
    # Re-encoded: a JPEG, whatever was sent, and nothing but the picture.
    assert attachments[0]["filename"] == "screenshot-1.jpg"
    assert base64.b64decode(attachments[0]["content"])[:3] == b"\xff\xd8\xff"
    status, answer = person.api("POST", "/api/feedback", {
        "kind": "idea", "subject": "x", "message": "a message",
        "attachments": [{"name": "x.png", "data": base64.b64encode(b"not a picture").decode()}]})
    assert status == 400 and "not a picture" in answer["error"]


def test_one_service_down_still_answers_a_search_of_both(monkeypatch):
    def works(query, limit, key, large=False):
        return [gifs.Gif(id=str(i), title="t", preview="p", full="f", width=1, height=1,
                         bytes=1) for i in range(limit)]

    def refuses(query, limit, key, large=False):
        raise gifs.GifError("that GIF key was refused. Check it in "
                            f"{'your account settings' if gifs.personal.get() else '.env'}")
    monkeypatch.setitem(gifs.PROVIDERS, "giphy", gifs.PROVIDERS["giphy"].__class__(
        **{**gifs.PROVIDERS["giphy"].__dict__, "search": works}))
    monkeypatch.setitem(gifs.PROVIDERS, "klipy", gifs.PROVIDERS["klipy"].__class__(
        **{**gifs.PROVIDERS["klipy"].__dict__, "search": refuses}))
    token = gifs.personal.set(gifs.Personal(keys={"giphy": "g", "klipy": "k"}, choice="both"))
    try:
        found = gifs.search("cat", limit=30)
        # Half from each service: a shelf of both costs what a shelf of one does.
        assert len(found) == 15 and {one.provider for one in found} == {"giphy"}
        monkeypatch.setitem(gifs.PROVIDERS, "giphy", gifs.PROVIDERS["klipy"])
        with pytest.raises(gifs.GifError, match="account settings"):
            gifs.search("cat")
    finally:
        gifs.personal.reset(token)


def test_both_with_one_key_on_the_local_tool_uses_that_key(monkeypatch):
    monkeypatch.setenv("WASTATUS_GIF_PROVIDER", "both")
    monkeypatch.setenv("WASTATUS_GIPHY_KEY", "g")
    monkeypatch.delenv("WASTATUS_KLIPY_KEY", raising=False)
    assert gifs.provider() == "giphy"


def test_history_older_than_the_promise_is_never_shown(env, tmp_path):
    store = accounts.Accounts(tmp_path / "p.db")
    store.add("a@example.com")
    store.record("a@example.com", video_id="v", title="t", channel="c", mode="card",
                 start=0, end=1, stem="", ok=True, seconds=1)
    store._do("update history set at = ?", (accounts.days_ago(accounts.HISTORY_DAYS + 1),))
    assert store.history("a@example.com") == []
    store.forget("a@example.com")
    store.record("a@example.com", video_id="v", title="t", channel="c", mode="card",
                 start=0, end=1, stem="", ok=True, seconds=1)
    assert store._all("select * from history") == []


def test_the_gif_switch_reaches_a_phone_on_the_hosted_page():
    import pathlib
    css = (pathlib.Path(portal.__file__).parent / "pages" / "hosted.css").read_text()
    phone = css[css.index("@media (max-width: 900px)"):]
    assert ".gifpick:not([hidden])" in phone and "min-height: 40px" in phone


def test_every_hosted_page_carries_the_pressing_feedback(site):
    """A link that leaves shows a spinner, a slow page a bar, a busy button a spinner."""
    person = approved(site, "a@example.com")
    for path in ("/", "/install", "/signin", "/account", "/app"):
        page = person.request("GET", path)[1].decode()
        assert '<script src="/nav.js"></script>' in page, path
        assert '<link rel="stylesheet" href="/nav.css">' in page, path
    assert person.request("GET", "/nav.js")[0].status == 200
    assert person.request("GET", "/nav.css")[0].status == 200


class TestSecondPass:
    def test_sessions_are_listed_named_and_ended_from_the_account(self, site):
        one = approved(site, "a@example.com")
        two = Browser(site)
        two.request("POST", "/api/session", {"credential": "google:a@example.com"},
                    {"X-SnipShare": "1", "User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/150.0 Safari/537"})
        two.load_page()
        status, data = one.api("GET", "/api/account")
        assert len(data["sessions"]) == 2
        assert sum(s["current"] for s in data["sessions"]) == 1
        other = next(s for s in data["sessions"] if not s["current"])
        assert other["agent"] == "Chrome on Windows"
        assert all(len(s["id"]) == 16 for s in data["sessions"])
        status, answer = one.api("POST", "/api/account/sessions/end", {"id": other["id"]})
        assert answer["ended"] == 1 and len(answer["sessions"]) == 1
        assert two.api("GET", "/api/state")[0] == 403
        current = answer["sessions"][0]["id"]
        status, _ = one.api("POST", "/api/account/sessions/end", {"id": current})
        assert status == 400, "this browser signs out with Sign out"

    def test_the_admin_sees_any_range_of_days(self, site):
        admin = Browser(site)
        admin.sign_in(ADMIN)
        site.accounts._count(ADMIN, "clips", 2)
        status, data = admin.api("GET", "/api/admin?from=2026-01-01&to=2026-01-07")
        assert status == 200 and data["range"] == {"from": "2026-01-01", "to": "2026-01-07"}
        assert data["totals"]["clips"] == 0
        today = accounts.today()
        status, data = admin.api("GET", f"/api/admin?from={today}&to={today}")
        assert data["totals"]["clips"] == 2 and data["totals"]["people"] == 1
        assert next(p for p in data["people"] if p["email"] == ADMIN)["range"]["clips"] == 2
        status, answer = admin.api("GET", "/api/admin?from=2020-01-01&to=2026-01-01")
        assert status == 400

    def test_a_google_photo_is_kept_only_if_it_is_googles(self):
        assert signin.photo("https://lh3.googleusercontent.com/a/abc=s96-c")
        assert not signin.photo("https://evil.example/x.png")
        assert not signin.photo("http://lh3.googleusercontent.com/a/abc")
        assert not signin.photo("https://googleusercontent.com.evil.example/a")

    def test_every_page_offers_the_theme_and_a_signed_in_face(self, site):
        person = approved(site, "a@example.com")
        for path in ("/", "/install", "/privacy"):
            page = person.request("GET", path)[1].decode()
            assert "data-theme-toggle" in page and 'data-initial="A"' in page

    def test_a_browser_is_named_coarsely(self):
        assert portal.browser_of("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604") == "Safari on iPhone"
        assert portal.browser_of("Mozilla/5.0 (X11; Linux x86_64) Chrome/156.0 Safari/537") == "Chrome on Linux"
        assert portal.browser_of("") == "A browser"


# -- the 2026-10-25 audit, held in place ------------------------------------------

class TestWhatAStrangerCannotMakeItDo:
    """Findings from the audit before the repository was published: nobody signed
    in can make the server read a large body, a GET cannot smuggle a second request,
    an admin's files cannot be deleted from under them, and grants end with the last
    session."""

    def raw(self, site, text: bytes) -> bytes:
        import socket

        with socket.create_connection(("127.0.0.1", site.port), timeout=10) as sock:
            sock.sendall(text)
            chunks = []
            while True:
                try:
                    chunk = sock.recv(65536)
                except TimeoutError:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)

    def test_a_large_body_from_nobody_is_refused_unread(self, site):
        # The headers promise 11 MB and only the headers are sent: an answer that
        # arrives anyway was given without reading the body.
        answer = self.raw(site, b"POST /api/feedback HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                                b"Content-Type: application/json\r\n"
                                b"Content-Length: 11000000\r\n\r\n")
        assert answer.startswith(b"HTTP/1.1 401")

    def test_a_tool_call_from_nobody_is_refused_unread(self, site):
        answer = self.raw(site, b"POST /api/render HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                                b"Content-Length: 11000000\r\n\r\n")
        assert answer.startswith(b"HTTP/1.1 403")

    def test_a_get_carrying_a_body_is_one_answer_not_two(self, site):
        smuggled = b"GET /api/me HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
        answer = self.raw(site, b"GET /privacy HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                                b"Content-Length: %d\r\n\r\n" % len(smuggled) + smuggled)
        assert answer.startswith(b"HTTP/1.1 400")
        assert answer.count(b"HTTP/1.1 ") == 1

    def test_an_admin_cannot_be_deleted_and_keeps_their_files(self, site):
        admin = Browser(site)
        admin.sign_in(ADMIN)
        person = site.accounts.person(ADMIN)
        workspace = site.workspace(person)
        with pytest.raises(accounts.AccessError):
            site.forget(ADMIN)
        assert not workspace.gone
        assert site.accounts.person(ADMIN) is not None

    def test_the_last_sign_out_ends_the_extension_s_grants(self, site):
        person = approved(site, "a@example.com")
        grant = site.accounts.grant("a@example.com", "upload")
        assert site.accounts.check_grant(grant, "upload") is not None
        response, _ = person.request("POST", "/api/signout", {}, {"X-SnipShare": "1"})
        assert response.status == 200
        assert site.accounts.check_grant(grant, "upload") is None

    def test_two_requests_at_once_for_one_address_are_one_request(self, site):
        from concurrent.futures import ThreadPoolExecutor

        def ask(_):
            return site.accounts.request_access("same@example.com", {"name": "Same"})[1]

        with ThreadPoolExecutor(max_workers=8) as pool:
            news = list(pool.map(ask, range(8)))
        assert news.count(True) == 1

    def test_a_name_that_looks_like_a_placeholder_stays_a_name(self):
        page = portal.fill_app_page('<body {{BODY_DATA}}>{{HEAD}}', "t", {"name": "{{HEAD}}"})
        assert page.count("hosted.css") == 1
        assert 'data-name="{{HEAD}}"' in page

    def test_every_public_page_links_to_its_source(self, site):
        response, data = Browser(site).request("GET", "/privacy")
        assert response.status == 200
        assert portal.SOURCE_URL.encode() in data

    def test_the_tool_page_offers_its_source_too(self, site):
        person = approved(site, "a@example.com")
        response, data = person.request("GET", "/app")
        assert response.status == 200
        assert f'data-source="{portal.SOURCE_URL}"'.encode() in data

    def test_a_small_refused_body_is_read_so_the_refusal_arrives_cleanly(self, site):
        answer = self.raw(site, b"POST /api/feedback HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                                b"Content-Length: 2\r\nConnection: close\r\n\r\n{}")
        assert answer.startswith(b"HTTP/1.1 401")


def test_daily_counts_older_than_a_year_are_forgotten(env, tmp_path):
    store = accounts.Accounts(tmp_path / "people.db")
    store.add("a@example.com", "A")
    old = accounts.today(accounts.days_ago(accounts.USAGE_DAYS + 5))
    store._do("insert into usage (email, day, clips) values (?,?,1)", ("a@example.com", old))
    assert store.forget_old_usage() == 1
    assert store._one("select 1 from usage where day = ?", (old,)) is None


def test_the_container_s_memory_is_read_from_its_cgroup(tmp_path):
    from wastatus import watch

    (tmp_path / "memory.current").write_text("900\n")
    (tmp_path / "memory.max").write_text("1000\n")
    assert watch.memory_use(tmp_path) == (900, 1000)
    (tmp_path / "memory.max").write_text("max\n")
    assert watch.memory_use(tmp_path) is None
    assert watch.memory_use(tmp_path / "missing") is None


class TestTheSecondSecurityPass:
    """D-101: the protections added in the security audit after publication."""

    def test_an_address_signs_in_only_with_the_google_account_that_first_used_it(self, site):
        site.accounts.add("a@example.com", "A")
        site.accounts.bind_google("a@example.com", "s-original")
        person = Browser(site)
        status, answer = person.open_call("/api/session", {"credential": "google:a@example.com"})
        assert status == 403 and "not the one" in answer["error"]

    def test_the_first_google_account_is_remembered(self, site):
        approved(site, "b@example.com")
        assert site.accounts.google_sub("b@example.com") == "s-b@example.com"

    @pytest.mark.parametrize("url, kept", [
        ("https://lh3.googleusercontent.com/a/photo", True),
        ("javascript:alert(1)", False),
        ("http://lh3.googleusercontent.com/a/photo", False),
        ("https://example.com/photo", False),
    ])
    def test_only_google_s_photo_host_is_kept_as_a_picture(self, site, url, kept):
        site.accounts.add("c@example.com", "C")
        site.accounts.set_picture("c@example.com", url)
        assert (site.accounts.picture("c@example.com") == url) is kept

    def test_a_busy_grant_still_ends(self, site, monkeypatch):
        site.accounts.add("d@example.com", "D")
        grant = site.accounts.grant("d@example.com", "upload")
        start = time.time()
        later = start + accounts.GRANT_LIFETIME + 60
        for moment in range(int(start), int(later), 600):   # used every ten minutes
            monkeypatch.setattr(accounts.time, "time", lambda moment=moment: moment)
            site.accounts.check_grant(grant, "upload", renew=True)
        monkeypatch.setattr(accounts.time, "time", lambda: later)
        assert site.accounts.check_grant(grant, "upload", renew=True) is None

    def test_a_picture_claiming_to_be_huge_is_refused_before_it_is_decoded(self):
        import base64
        import io
        import struct
        import zlib

        from PIL import Image
        # A real 1 by 1 PNG whose header then says 5000 by 5000: under Pillow's own
        # limit, over ours.
        buffer = io.BytesIO()
        Image.new("RGBA", (1, 1)).save(buffer, "PNG")
        data = bytearray(buffer.getvalue())
        data[16:24] = struct.pack(">II", 5000, 5000)
        data[29:33] = struct.pack(">I", zlib.crc32(bytes(data[12:29])) & 0xFFFFFFFF)
        with pytest.raises(ValueError, match="too large"):
            stickers.save_upload("big", base64.b64encode(bytes(data)).decode())

    def test_a_public_site_without_its_turnstile_secret_refuses_forms(self, monkeypatch):
        monkeypatch.delenv("WASTATUS_TURNSTILE_SECRET", raising=False)
        monkeypatch.setenv("WASTATUS_PUBLIC_URL", "https://snipshare.example.com")
        assert signin.human("anything") is False

    def test_an_alert_s_log_line_names_nobody(self, site, caplog):
        site.alert("test", "someone@example.com has used 90% of today's allowance")
        assert "someone@example.com" not in caplog.text and "a person" in caplog.text

    def test_the_extension_offered_is_the_one_in_the_image(self, site, tmp_path, monkeypatch):
        baked = tmp_path / "image" / "snipshare-extension.zip"
        baked.parent.mkdir()
        baked.write_bytes(b"PK baked")
        monkeypatch.setattr(portal, "IMAGE_EXTENSION", baked)
        (site.root / "extension").mkdir(exist_ok=True)
        (site.root / "extension" / "snipshare-extension.zip").write_bytes(b"PK planted")
        response, data = Browser(site).request("GET", "/download/snipshare-extension.zip")
        assert data == b"PK baked"
        response, page = Browser(site).request("GET", "/install")
        assert hashlib.sha256(b"PK baked").hexdigest().encode() in page

    def test_every_answer_carries_the_isolation_headers(self, site):
        response, _ = Browser(site).request("GET", "/")
        assert "camera=()" in response.getheader("Permissions-Policy")
        assert response.getheader("Cross-Origin-Opener-Policy") == "same-origin-allow-popups"
        assert "Python" not in (response.getheader("Server") or "")


class TestARequestIsReadOneWay:
    """D-101, from the defensive tests: every request has exactly one reading, and
    one that does not is answered once and its connection closed."""

    raw = TestWhatAStrangerCannotMakeItDo.raw

    def test_a_body_on_options_is_not_a_second_request(self, site):
        smuggled = b"GET /api/me HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
        answer = self.raw(site, b"OPTIONS /api/state HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                                b"Content-Length: %d\r\n\r\n" % len(smuggled) + smuggled)
        assert answer.count(b"HTTP/1.1 ") == 1

    def test_two_lengths_are_refused(self, site):
        answer = self.raw(site, b"POST /api/session HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                                b"Content-Length: 2\r\nContent-Length: 40\r\n\r\n{}")
        assert answer.startswith(b"HTTP/1.1 400") and answer.count(b"HTTP/1.1 ") == 1

    def test_a_length_beside_chunking_is_refused(self, site):
        answer = self.raw(site, b"POST /api/session HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                                b"Content-Length: 2\r\nTransfer-Encoding: chunked\r\n\r\n{}")
        assert answer.startswith(b"HTTP/1.1 400")

    def test_a_length_in_other_digits_is_answered_not_dropped(self, site):
        answer = self.raw(site, "POST /api/signup HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                                "Content-Length: ²\r\n\r\n".encode("latin-1"))
        assert answer.startswith(b"HTTP/1.1 4")

    @pytest.mark.parametrize("body", [b"[1, 2]", b'"text"', b"[" * 100000 + b"]" * 100000])
    def test_a_body_that_is_not_an_object_is_answered(self, site, body):
        person = approved(site, "a@example.com")
        status, _ = person.api("POST", "/api/caption", body)
        assert 400 <= status < 500

    def test_python_s_own_error_page_has_a_policy(self, site):
        answer = self.raw(site, b"BREW /coffee HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        assert b"Content-Security-Policy: default-src 'none'" in answer

    def test_an_alert_cannot_mention_the_whole_chat_space(self, site, env):
        site.alert("t", "<users/all> <https://evil.example|x>", every=0)
        sent = [text for kind, text in env if kind == "chat"][-1]
        assert "<" not in sent and ">" not in sent
