"""SnipShare: the full page, hosted, for people the owner has let in.

The renderer (`hosted`) already turns an upload into a clip. This puts the page the
local tool serves (`serve`) in front of it, for several people at once:

* **Who.** A Google sign-in, checked here, and a list the owner approves by hand.
  A session is a random cookie, stored hashed (`accounts`). Request access is a
  form, with Turnstile in front of it, that tells the owner and nobody else
  (`notify`, `signin`).
* **Whose.** Every person gets a workspace of their own: their clips, their
  stickers, their GIF key. It is `serve.App`, pointed at their folder, so every
  route the page uses is the one the local tool already answers and tests.
* **How much.** Ten clips and 500 MB of uploads a day each, one render at a time
  each, a shared cap an hour, and the renderer's own slots shared with the
  extension's popup jobs.
* **What it never does.** Talk to YouTube, or drive WhatsApp. The extension in the
  person's own Chrome reads the video and loads the composer; this only renders.

Nothing here names a domain, a person or a key. Every one of those comes from the
environment, so the code can be published as it is. See docs/hosted-page.md.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import html
import io
import json
import logging
import os
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
import urllib.parse
import uuid
from collections import deque
from datetime import datetime
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from . import (accounts, compose, fetch, gifs, hosted, notify, pipeline, proc,
               render, runlog, serve, signin, stickers)
from .accounts import AccessError, Accounts, Person
from .timecode import TimecodeError

log = logging.getLogger("wastatus")

NAME = "SnipShare"
TAGLINE = "Status Maker for WhatsApp, from YouTube videos"

PUBLIC_URL_ENV = "WASTATUS_PUBLIC_URL"
EXTENSION_ID_ENV = "WASTATUS_EXTENSION_ID"
CONTACT_ENV = "WASTATUS_CONTACT_EMAIL"
OPERATOR_ENV = "WASTATUS_OPERATOR"
STATUS_PAGE_ENV = "WASTATUS_STATUS_URL"
# Where the site's own source is published. Every page links to it: the site runs
# AGPL code, and its source is offered to everyone who uses it. See
# THIRD_PARTY_NOTICES.md.
SOURCE_ENV = "WASTATUS_SOURCE_URL"
SOURCE_URL = "https://github.com/PalWorks/snipshare-whatsapp-status-maker"
TRUST_PROXY_ENV = "WASTATUS_TRUST_PROXY"
RENDERS_PER_HOUR_ENV = "WASTATUS_RENDERS_PER_HOUR"

PAGES = Path(__file__).resolve().parent / "pages"
# `__Host-`: the browser takes it only Secure, for this host alone and for every
# path, so no other subdomain can plant or overwrite it (D-101). Renamed from
# `snipshare_session` on 2026-10-25, which signed everybody out once.
SESSION_COOKIE = "__Host-snipshare_session"
# Every change the page asks for carries this, which a cross-site form cannot set.
OPEN_HEADER = "X-SnipShare"

KEEP_CLIPS = 10                 # per person; the oldest goes when the eleventh lands
STICKER_UPLOADS_MAX = 60        # per person
DEFAULT_RENDERS_PER_HOUR = 60   # across everybody
WARN_SHARE = 0.8                # tell the owner when someone passes this much of a limit
EXTENSION_MIN_VERSION = "2.0.0"

# What the hosted page never offers: there is no WhatsApp on this server to drive.
NOT_HERE = {"/api/post", "/api/browser"}

YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
TOKEN_IN_URL = re.compile(r"(t|credential)=[^&\s]+")


def plain(text: Any, limit: int = 300) -> str:
    """Words from a person, made safe for the owner's Chat space: Chat reads <...>
    as a mention or a link, and a name or a code typed into a request must not be
    able to page the whole space."""
    return " ".join(str(text or "").split())[:limit].replace("<", "\u2039").replace(">", "\u203a")


def _truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in serve.TRUE


def public_url() -> str:
    """The site's own address, scheme and host, no trailing slash. Empty in a copy
    run without one, which then only answers on loopback."""
    return (os.environ.get(PUBLIC_URL_ENV) or "").strip().rstrip("/")


def contact() -> str:
    return (os.environ.get(CONTACT_ENV) or "").strip()


def video_id_of(url: str) -> str:
    """The eleven characters that name a YouTube video, from any of the ways a link
    is written, or "" when the link is not one."""
    try:
        parts = urllib.parse.urlsplit((url or "").strip())
    except ValueError:
        return ""
    host = (parts.hostname or "").lower()
    found = ""
    if host in ("youtu.be", "www.youtu.be"):
        found = parts.path.strip("/").split("/")[0]
    elif host == "youtube.com" or host.endswith(".youtube.com"):
        if parts.path.rstrip("/") == "/watch":
            found = urllib.parse.parse_qs(parts.query).get("v", [""])[0]
        else:
            segments = parts.path.strip("/").split("/")
            if len(segments) > 1 and segments[0] in ("shorts", "live", "embed", "v"):
                found = segments[1]
    return found if YOUTUBE_ID.match(found) else ""


def csrf_for(session: str) -> str:
    """The value the page sends back on every call: tied to the session, so a page
    from before a sign-out cannot act, and readable only by the page itself."""
    return hmac.new(session.encode(), b"snipshare-page", hashlib.sha256).hexdigest()[:40]


# -- a person's own copy of the page's state ---------------------------------

class Workspace(serve.App):
    """One person's clips, stickers and GIF key, behind the local page's routes.

    `serve.App` already knows how to list clips, preview words, keep a caption and
    delete a take. Everything here either says "not on this server" (posting, the
    browser) or adds what only a shared server needs: limits, the shared slots, and
    the media the extension captured standing in for yt-dlp.
    """

    def __init__(self, portal: "Portal", person: Person) -> None:
        self.portal = portal
        self.email = person.email
        self.pid = person.id
        self.root = portal.users_dir / person.id
        super().__init__(out=self.root / "out", cdp_port=0, keep_last=KEEP_CLIPS)
        self.sticker_dir = self.root / "stickers"
        self.work_dir = self.root / "work"
        # Held while a sticker is counted and saved, so uploads arriving together
        # cannot all pass the count before any of them is written.
        self.sticker_lock = threading.Lock()
        # Set when the account is deleted: a render still finishing must not write
        # its clip, or a count, back for a person who is gone.
        self.gone = False

    @contextlib.contextmanager
    def bound(self):
        """Their stickers and their GIF keys, for the length of a request or a render.
        Set and reset here, so nothing of one person's leaks into the next request
        a thread serves."""
        sticker_token = stickers.personal.set(self.sticker_dir)
        gif_token = gifs.personal.set(self.gif_settings())
        try:
            yield
        finally:
            gifs.personal.reset(gif_token)
            stickers.personal.reset(sticker_token)

    def gif_settings(self) -> "gifs.Personal":
        store = self.portal.accounts
        return gifs.Personal(keys=store.gif_keys(self.email),
                             choice=store.gif_source(self.email))

    # -- what this server does not do ---------------------------------------

    def post_clip(self, stem: str, follow_up: bool, send: bool = True):
        raise RuntimeError("loading into WhatsApp is done by the extension, in your browser")

    def start_browser(self, page_url: str = "") -> dict[str, Any]:
        raise RuntimeError("there is no browser to start on this server")

    def controls_state(self, fresh: bool = False) -> dict[str, Any]:
        return {"ok": True, "checked": False, "detail": "checked by the extension"}

    def whatsapp_state(self, fresh: bool = False) -> dict[str, Any]:
        return {"ready": False, "detail": "loaded through the extension", "port": None,
                "can_launch": False}

    def label(self, cdp_port: int) -> Path | None:
        return None

    def _record_in_sheet(self, *args: Any, **kwargs: Any) -> None:
        return None

    def words_from(self, url: str) -> dict[str, str]:
        raise RuntimeError("the words come from the extension on this server")

    # -- what it does instead -------------------------------------------------

    def words_of(self, url: str, title: str, channel: str) -> dict[str, str]:
        """The words the extension read off the video, cleaned exactly as the card
        would clean them. The local tool asks yt-dlp; here the browser already
        knows, and nothing on this server asks YouTube anything."""
        video_id = video_id_of(url)
        if not video_id:
            raise ValueError("that is not a YouTube link")
        source = fetch.Source(video_id=video_id, title=title[:300], channel=channel[:200],
                              duration=0.0, watch_url=f"https://youtu.be/{video_id}")
        title, channel = pipeline.words_from_video(source)
        return {"title": title, "channel": channel}

    def state(self, fresh: bool = False) -> dict[str, Any]:
        person = self.portal.accounts.person(self.email)
        used = self.portal.accounts.usage(self.email)
        return {
            "hosted": True,
            "ffmpeg": True,
            "provider": True,
            "whatsapp": self.whatsapp_state(),
            "out": "",
            "host": "",
            "cdp_port": None,
            "max_duration": pipeline.MAX_DURATION,
            "fills": list(render.FILLS),
            "stickers": stickers.installed(),
            "bands": {
                "top": round(compose.SAFE_TOP / compose.HEIGHT, 4),
                "bottom": round(1 - compose.SAFE_BOTTOM / compose.HEIGHT, 4),
            },
            "keep_last": self.keep_last,
            "busy": False,
            # A render whose answer never reached the page: it can watch and stop it.
            "rendering": (lambda task: task.id if task else "")(self.running("render")),
            "also_on": "",
            "gifs": gifs.credit(),
            "clips": self.clips(),
            "me": {"email": self.email, "name": person.name if person else "",
                   "admin": bool(person and person.admin)},
            "quota": used,
            "extension": {"id": os.environ.get(EXTENSION_ID_ENV) or "",
                          "min_version": EXTENSION_MIN_VERSION},
        }

    def render_captured(self, job: pipeline.Job, captured: dict[str, Any]) -> serve.Task:
        """Make a clip from what the extension uploaded.

        Every check that can say no comes before the uploads are spent: one render
        of yours at a time, today's allowance, the hour's cap across everybody, room
        on the disk. Then the uploads move into a folder of this render's own, and
        the render waits for one of the renderer's slots, which the extension's
        popup jobs take too, so the machine never runs more ffmpegs than it has
        workers for.
        """
        with self.lock:
            if self._running("render"):
                raise RuntimeError("a clip of yours is already being made. Wait for it, "
                                   "or stop it")
            self.portal.accounts.check_clip(self.email)
            if shutil.disk_usage(self.portal.root).free < hosted.FREE_DISK_MIN:
                self.portal.alert("disk", "the renderer refused a clip: the disk is full")
                raise AccessError("the renderer is out of space. Try again later")
            taken = self.portal.take_render()
            folder = self.work_dir / uuid.uuid4().hex[:16]
            needed = {"audio": captured["audio"]}
            if job.video:
                needed["video"] = captured["video"]
            if captured.get("artwork"):
                needed["artwork"] = captured["artwork"]
            try:
                files = self.portal.renderer.claim(f"p:{self.pid}", needed, folder)
            except BaseException:
                # Refused uploads cost nobody a place in the hour.
                self.portal.release_render(taken)
                shutil.rmtree(folder, ignore_errors=True)
                raise
            video_id = captured["video_id"]
            job.captured = pipeline.Captured(
                source=fetch.Source(
                    video_id=video_id, title=captured["title"], channel=captured["channel"],
                    duration=captured["duration"], watch_url=f"https://youtu.be/{video_id}",
                    artist=captured.get("artist", ""),
                ),
                audio=files["audio"], video=files.get("video"), artwork=files.get("artwork"),
            )
            return self.start("render", lambda task: self._make(task, job, folder))

    def _make(self, task: serve.Task, job: pipeline.Job, folder: Path) -> dict[str, Any]:
        slots = self.portal.renderer.slots
        started = time.monotonic()
        ok = False
        made = None
        failure = ""
        try:
            task.stage, task.message = "probe", "waiting for a free renderer"
            # Polled rather than blocked on, so Stop works while it waits.
            while not slots.acquire(timeout=1):
                if task.stopping:
                    raise proc.Cancelled("stopped while waiting")
            try:
                with self.bound():
                    run = runlog.Run(log, url=job.url, start=job.start, end=job.end,
                                     duration=job.duration, mode=job.mode,
                                     source="hosted-page", user=self.pid)

                    def progress(stage: str, message: str) -> None:
                        task.stage, task.message = stage, message

                    try:
                        result = pipeline.produce(job, run, progress=progress)
                    except proc.Cancelled:
                        run.finish("cancelled")
                        raise
                    except Exception as exc:
                        run.finish("failed", error=f"{type(exc).__name__}: {exc}")
                        raise
                    run.finish("ok")
                    ok = True
                    made = result
                    return self.clip_json(result.stem) or {}
            finally:
                slots.release()
        except proc.Cancelled:
            raise
        except Exception as exc:
            failure = hosted._plain(exc)
            if not self.gone:
                self.portal.render_failed(self.email, task.stage, exc)
            raise
        finally:
            shutil.rmtree(folder, ignore_errors=True)
            if self.gone:
                shutil.rmtree(self.root, ignore_errors=True)
            elif ok or not task.stopping:
                took = time.monotonic() - started
                source = job.captured.source if job.captured else None
                try:
                    self.portal.render_finished(self.email, took, ok)
                    self.portal.accounts.record(
                        self.email, video_id=source.video_id if source else "",
                        title=made.title if made else (job.title or (source.title if source else "")),
                        channel=made.channel if made else (job.channel or (source.channel if source else "")),
                        mode=job.mode, start=job.start, end=job.end,
                        stem=made.stem if made else "", ok=ok, seconds=took, error=failure)
                except Exception:  # noqa: BLE001 - bookkeeping must not change the outcome
                    log.exception("a render's count or history could not be written")


# -- the whole site's state ---------------------------------------------------

class Portal:
    """Accounts, workspaces, limits and alerts: everything the handler asks."""

    def __init__(self, root: Path, renderer: hosted.Renderer) -> None:
        self.root = root
        self.renderer = renderer
        self.accounts = Accounts(root / "people.db")
        self.users_dir = root / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self.limiter = signin.Limiter()
        self._workspaces: dict[str, Workspace] = {}
        self._lock = threading.Lock()
        # Renders across everybody in the last hour, and how each one ended, for the
        # hourly cap and the failure rate. In memory: a restart forgets the hour.
        self._renders: deque[float] = deque()
        self._outcomes: deque[tuple[float, bool]] = deque(maxlen=2000)
        renderer.grant_owner = self.grant_owner
        renderer.on_upload = self.on_upload
        renderer.on_upload_gone = self.on_upload_gone
        # Media a render was working on when the process stopped: nobody will come
        # back for it, and it is somebody's captured video.
        for work in self.users_dir.glob("*/work"):
            shutil.rmtree(work, ignore_errors=True)
        for stale in self.users_dir.glob("*/out/*.part"):
            stale.unlink(missing_ok=True)
        # A render killed mid way leaves its scratch folder, with somebody's
        # captured media in it. Only when the scratch space is this project's own.
        scratch = Path(tempfile.gettempdir())
        if scratch.resolve().is_relative_to(root.resolve()):
            for stale in scratch.glob("wastatus-*"):
                shutil.rmtree(stale, ignore_errors=True)

    # -- people's workspaces -------------------------------------------------

    def workspace(self, person: Person) -> Workspace:
        with self._lock:
            found = self._workspaces.get(person.id)
            if found is None:
                found = self._workspaces[person.id] = Workspace(self, person)
            return found

    def forget(self, email: str) -> None:
        """Everything about a person, files included. A render of theirs still
        running is marked first, so it writes nothing back, then stopped and waited
        for."""
        person = self.accounts.person(email)
        # Refused before anything is touched: marking the workspace gone first would
        # let a render of theirs still running delete the admin's own files.
        if person is not None and person.admin:
            raise AccessError("an admin cannot be deleted here")
        workspace = None
        if person is not None:
            with self._lock:
                workspace = self._workspaces.pop(person.id, None)
            if workspace is not None:
                workspace.gone = True
        self.accounts.forget(email)
        if person is None:
            return
        if workspace is not None:
            task = workspace.running("render")
            if task is not None:
                with contextlib.suppress(KeyError, ValueError):
                    workspace.cancel(task.id)
                deadline = time.monotonic() + 60
                while task.status == "running" and time.monotonic() < deadline:
                    time.sleep(0.2)
        shutil.rmtree(self.users_dir / person.id, ignore_errors=True)

    # -- the renderer's two hooks ---------------------------------------------

    def grant_owner(self, token: str) -> tuple[str, str] | None:
        person = self.accounts.check_grant(token, "upload", renew=True)
        if person is None:
            return None
        return f"p:{person.id}", f"p:{person.id[:8]}"

    def on_upload_gone(self, owner: str, unsent: int, created: float) -> None:
        if owner.startswith("p:") and unsent > 0:
            person = self.accounts.by_id(owner[2:])
            if person is not None:
                # Against the day it was counted on, which may not be today.
                self.accounts.refund_upload(person.email, unsent, accounts.today(created))

    def on_upload(self, owner: str, size: int) -> None:
        if not owner.startswith("p:"):
            return  # an owner's token for the popup: no daily allowance
        person = self.accounts.by_id(owner[2:])
        if person is None:
            raise hosted.Refused(HTTPStatus.UNAUTHORIZED, "sign in again")
        try:
            share = self.accounts.reserve_upload(person.email, size)
        except AccessError as exc:
            raise hosted.Refused(HTTPStatus.TOO_MANY_REQUESTS, str(exc)) from exc
        if share >= WARN_SHARE:
            self.alert(f"uploads:{person.id}:{accounts.today()}",
                       f"{person.email} has used {share:.0%} of today's upload allowance",
                       every=86400)

    # -- limits across everybody ---------------------------------------------

    def renders_per_hour(self) -> int:
        try:
            return max(1, int(os.environ.get(RENDERS_PER_HOUR_ENV) or DEFAULT_RENDERS_PER_HOUR))
        except ValueError:
            return DEFAULT_RENDERS_PER_HOUR

    def _hour_full(self, now: float) -> bool:
        while self._renders and now - self._renders[0] > 3600:
            self._renders.popleft()
        return len(self._renders) >= self.renders_per_hour()

    def check_room(self) -> None:
        """Refuse now if the hour is full, before the extension reads anything."""
        with self._lock:
            full = self._hour_full(time.time())
        if full:
            raise AccessError("SnipShare is at its limit for this hour. Try again in a "
                              "few minutes")

    def take_render(self) -> float:
        now = time.time()
        with self._lock:
            full = self._hour_full(now)
            if not full:
                self._renders.append(now)
        if full:
            self.alert("hourly-cap", f"the hourly cap of {self.renders_per_hour()} renders "
                       "was reached; clips are being refused until it eases")
            raise AccessError("SnipShare is at its limit for this hour. Try again in a "
                              "few minutes")
        return now

    def release_render(self, stamp: float) -> None:
        with self._lock, contextlib.suppress(ValueError):
            self._renders.remove(stamp)

    def render_finished(self, email: str, seconds: float, ok: bool) -> None:
        self.accounts.count_clip(email, seconds, ok)
        now = time.time()
        with self._lock:
            self._outcomes.append((now, ok))
            hour = [good for at, good in self._outcomes if now - at < 3600]
        if ok:
            used = self.accounts.usage(email)
            if used["clips"] >= WARN_SHARE * used["clips_limit"]:
                self.alert(f"clips:{accounts.person_id(email)}:{accounts.today()}",
                           f"{email} has made {used['clips']} of today's "
                           f"{used['clips_limit']} clips", every=86400)
        failed = hour.count(False)
        if len(hour) >= 5 and failed / len(hour) > 0.2:
            self.alert("render-rate", f"{failed} of the last {len(hour)} renders this hour "
                       "failed. Check the renderer's log")

    def render_failed(self, email: str, stage: str, exc: Exception) -> None:
        kind = type(exc).__name__
        self.accounts.report("render", stage, kind, detail=hosted._plain(exc),
                             email=email)
        self.alert(f"render-error:{kind}", f"a render failed at {stage or 'the start'}: "
                   f"{kind}: {hosted._plain(exc)}")

    def recent_outcomes(self, seconds: float) -> list[tuple[float, bool]]:
        now = time.time()
        with self._lock:
            return [(at, ok) for at, ok in self._outcomes if now - at < seconds]

    # -- telling the owner ----------------------------------------------------

    def alert(self, key: str, text: str, every: float = 3600) -> None:
        """One Chat message per key per `every` seconds, so a storm is one line.

        The text goes to the owner's Chat and may name a person; the log, which
        lasts longer and is read more widely, gets the key and the text with any
        address taken out."""
        log.warning("alert %s: %s", key, _EMAIL.sub("a person", text))
        try:
            if self.accounts.should_alert(key, every):
                notify.chat(f"{NAME}: {plain(text, 3000)}")
        except Exception:  # noqa: BLE001 - an alert must never break what raised it
            log.exception("an alert could not be recorded")

    def tell_owner_of_request(self, person: Person, google: bool, chrome: bool) -> None:
        site = public_url()
        answers = person.answers
        link = f"{site}/admin?email={urllib.parse.quote(person.email)}" if site else ""
        lines = [
            f"{person.name} asked for access to {NAME}.",
            "",
            f"Email: {person.email} ({'checked by Google' if google else 'typed, not checked'})",
            f"What for: {answers.get('use') or 'not said'}",
            f"Heard of it from: {answers.get('heard') or 'not said'}",
            f"Uses desktop Chrome: {'yes' if chrome else 'not ticked'}",
            "",
        ]
        if link:
            lines += [f"Approve or decline: {link}", ""]
        lines.append(f"Or on the server: wastatus hosted user approve {person.email}")
        notify.email(f"{NAME}: access request from {person.name}", lines)
        notify.chat("\n".join([f"*{NAME}*: access request from {plain(person.name)} "
                               f"({plain(person.email)})",
                               f"What for: {plain(answers.get('use') or 'not said')}"]
                              + ([f"Approve: {link}"] if link else [])))


# -- HTTP -----------------------------------------------------------------------

class SiteHandler(hosted.Handler, serve.Handler):
    """The public pages, the person's page API, and the renderer's API, on one port.

    The renderer's handler comes first in the order, so `_json` and `_send` are its
    versions, which take the extra headers its refusals need; `serve`'s routes then
    run unchanged against the person's own workspace, set per request.
    """

    server_version = "snipshare"
    sys_version = ""   # no Python version in the Server header
    portal: Portal
    QUIET = ("/api/state", "/api/task", "/api/frame", "/api/clip", "/api/v1/health",
             "/api/v1/uploads", "/api/sticker", "/api/gif")

    # -- plumbing -----------------------------------------------------------

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        line = fmt % args
        if " 200 " in f" {line} " or " 206 " in f" {line} ":
            if any(part in line for part in self.QUIET):
                return
        log.debug("site %s %s", self._address(), TOKEN_IN_URL.sub(r"\1=REDACTED", line))

    def _address(self) -> str:
        if _truthy(TRUST_PROXY_ENV):
            forwarded = (self.headers.get("CF-Connecting-IP") or "").strip()
            if forwarded:
                return forwarded[:64]
        return self.client_address[0] if self.client_address else ""

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        # Nothing here uses the camera, microphone, location or payment; saying so
        # means an injected script could not either.
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), "
                         "payment=(), usb=(), interest-cohort=()")
        # Its own browsing context, apart from Google's sign-in popup, which needs
        # to answer the page that opened it.
        self.send_header("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
        policy = getattr(self, "_policy", None)
        if policy:
            self.send_header("Content-Security-Policy", policy)
        if public_url().startswith("https://"):
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        super().end_headers()

    def send_error(self, code: int, message: str | None = None,
                   explain: str | None = None) -> None:
        # Python's own error page, for a request too broken to reach a route: it
        # gets a policy of its own that allows nothing, like every other answer.
        self._policy = "default-src 'none'; frame-ancestors 'none'"
        super().send_error(code, message, explain)

    def _host_allowed(self) -> bool:
        # Named by its domain, behind a tunnel that answers for that name alone;
        # the session cookie and the Origin check guard the calls instead.
        return True

    def _origin(self) -> str:
        """Where this site is, as a browser names it in `Origin`."""
        site = public_url()
        if site:
            parts = urllib.parse.urlsplit(site)
            return f"{parts.scheme}://{parts.netloc}"
        return serve.Handler._own_origin(self) or ""

    def _same_site(self, required: bool) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return not required
        return origin == self._origin()

    def _cookie(self) -> str:
        # Split by hand: `SimpleCookie` gives up on the whole header when another
        # site cookie on this domain holds JSON or a space, as Google's own do.
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == SESSION_COOKIE:
                return value.strip()
        return ""

    def _person(self) -> Person | None:
        return self.portal.accounts.session(self._cookie())

    def _session_cookie(self, token: str, max_age: int) -> str:
        secure = "" if self._origin().startswith("http://") and not self._origin().startswith(
            ("http://localhost", "http://127.0.0.1")) else "; Secure"
        return (f"{SESSION_COOKIE}={token}; Path=/; Max-Age={max_age}; HttpOnly"
                f"; SameSite=Lax{secure}")

    def _redirect(self, where: str) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _params(self) -> dict[str, str]:
        query = self.path.partition("?")[2]
        return {k: v[0] for k, v in urllib.parse.parse_qs(query).items()}

    # -- who is asking, for the page's own API ------------------------------

    def _authorised(self, query_token: str | None = None) -> bool:
        """`serve`'s guard, answered from the session: the cookie, the value the page
        was handed for that session, and, when the browser says, this site's origin.
        Binds the person's workspace for the rest of the request."""
        token = self._cookie()
        person = self.portal.accounts.session(token)
        if person is None:
            return False
        offered = self.headers.get(serve.TOKEN_HEADER) or query_token or ""
        if not secrets.compare_digest(offered, csrf_for(token)):
            return False
        if not self._same_site(required=self.command == "POST"):
            return False
        self._bind(person)
        return True

    def _bind(self, person: Person) -> None:
        workspace = self.portal.workspace(person)
        self.app = workspace
        self._bound = contextlib.ExitStack()
        self._bound.enter_context(workspace.bound())
        self.person = person

    def _unbind(self) -> None:
        bound = getattr(self, "_bound", None)
        if bound is not None:
            bound.close()
            self._bound = None
        self.person = None

    # -- routes -----------------------------------------------------------------

    def _chunked(self) -> bool:
        """A body sent without a length is not read by any route here, so it is
        refused and the connection closed, rather than left in the socket for the
        next request on it, which the tunnel may be carrying for somebody else."""
        if not self.headers.get("Transfer-Encoding"):
            return False
        self.close_connection = True
        self._json({"error": "send a Content-Length"}, HTTPStatus.LENGTH_REQUIRED,
                   {"Connection": "close"})
        return True

    def do_PUT(self) -> None:  # noqa: N802
        if not self._chunked():
            super().do_PUT()

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._chunked():
            super().do_DELETE()

    def _close_unread(self) -> None:
        """Deal with the body of a request being refused, without reading much of it.

        A small one (up to DRAIN_MAX) is read and thrown away, so the connection
        stays usable and the browser is still sending nothing when the refusal
        arrives: a socket closed mid upload is a broken pipe to the browser, which
        then shows a network error instead of the 401 that sends it to sign in. A
        larger one is not read at all, and the connection ends after the answer, as
        the body would otherwise be parsed as the next request on it."""
        raw = (self.headers.get("Content-Length") or "0").strip()
        if self.headers.get("Transfer-Encoding") or not (raw.isascii() and raw.isdigit()):
            self.close_connection = True
            return
        length = int(raw)
        if 0 < length <= DRAIN_MAX:
            self.rfile.read(length)
            self._consumed = True
        elif length:
            self.close_connection = True

    def _body_on_a_read(self) -> bool:
        """A GET or HEAD carrying a body is refused and its connection closed. Left
        alone, the body would be read as a second request on the same connection,
        and its answer handed to whoever sends the next one through a shared proxy."""
        if (self.headers.get("Content-Length") or "0") == "0" and not self.headers.get("Transfer-Encoding"):
            return False
        self.close_connection = True
        self._consumed = True
        self._policy = None
        self._json({"error": "a GET or HEAD carries no body"}, HTTPStatus.BAD_REQUEST,
                   {"Connection": "close"})
        return True

    def do_GET(self) -> None:  # noqa: N802
        self._consumed = False
        self._policy = None
        if self._body_on_a_read():
            return
        path = self.path.partition("?")[0]
        if path == hosted.API or path.startswith(hosted.API + "/"):
            if path == hosted.API + "/clip":
                return self._v1_clip()
            return self._dispatch("GET")
        if path in SITE_PAGES:
            return self._site_page(path)
        if path in ("/app", "/app/", "/index.html"):
            return self._page()
        if path == "/admin":
            return self._admin_page()
        if path == "/account":
            return self._account_page()
        if path in SITE_ASSETS:
            return self._site_asset(SITE_ASSETS[path])
        if path in ("/app.css", "/app.js", "/favicon.svg", "/favicon.ico"):
            return serve.Handler.do_GET(self)
        if path == "/download/snipshare-extension.zip":
            return self._extension_zip()
        if path == "/api/me":
            return self._me()
        if path == "/api/admin":
            return self._account_call(self._admin_overview, admin=True, body=False)
        if path == "/api/account":
            return self._account_call(self._account_overview, body=False)
        if path == "/api/account/history":
            return self._account_call(self._account_history, body=False)
        if path.startswith("/api/"):
            try:
                return serve.Handler.do_GET(self)
            finally:
                self._unbind()
        return self._not_found()

    def do_POST(self) -> None:  # noqa: N802
        self._consumed = False
        self._policy = None
        if self._chunked():
            return
        path = self.path.partition("?")[0]
        if path == hosted.API or path.startswith(hosted.API + "/"):
            return self._dispatch("POST")
        if path in OPEN_CALLS:
            return self._open_call(OPEN_CALLS[path])
        if path in ACCOUNT_CALLS:
            method, admin = ACCOUNT_CALLS[path]
            return self._account_call(getattr(self, method), admin=admin,
                                      limit=FEEDBACK_MAX if path == "/api/feedback"
                                      else hosted.JSON_MAX)
        if path in NOT_HERE:
            self._close_unread()
            return self._fail(HTTPStatus.NOT_FOUND, "not offered on this server")
        if path.startswith("/api/"):
            # `serve` reads the body before its own checks, up to 12 MB. Here the
            # session is looked at first, so only a signed-in person gets that far.
            if self.portal.accounts.session(self._cookie()) is None:
                self._close_unread()
                return self._fail(HTTPStatus.FORBIDDEN, "bad or missing token")
            try:
                return serve.Handler.do_POST(self)
            finally:
                self._unbind()
        self._close_unread()
        return self._fail(HTTPStatus.NOT_FOUND, "no such endpoint")

    def do_HEAD(self) -> None:  # noqa: N802
        if self._body_on_a_read():
            return
        path = self.path.partition("?")[0]
        if path == hosted.API or path.startswith(hosted.API + "/"):
            return super().do_HEAD()
        self._consumed = False
        self._policy = None
        self._send(HTTPStatus.OK if path in SITE_PAGES else HTTPStatus.NOT_FOUND, b"",
                   "text/html; charset=utf-8")

    def _not_found(self) -> None:
        self._policy = PAGE_POLICY
        body = render_page("missing.html", "Not found", "There is nothing at this address.")
        self._send(HTTPStatus.NOT_FOUND, body, "text/html; charset=utf-8")

    # -- pages ------------------------------------------------------------------

    def _site_page(self, path: str) -> None:
        name, title, description = SITE_PAGES[path]
        self._policy = PAGE_POLICY
        person = self._person()
        values = {"SIGNED_IN": "1" if person else "", **self._who(person)}
        if path == "/install":
            values["EXTENSION_DIGEST"] = extension_digest(self.portal.root)
        self._send(HTTPStatus.OK, render_page(name, title, description, values),
                   "text/html; charset=utf-8")

    def _who(self, person: Person | None) -> dict[str, str]:
        """What the header's avatar needs: the photo, or the initial."""
        if person is None:
            return {}
        return {"PICTURE": self.portal.accounts.picture(person.email),
                "INITIAL": (person.name or person.email)[:1].upper()}

    def _site_asset(self, name: str) -> None:
        file = PAGES / name
        if not file.is_file():
            return self._fail(HTTPStatus.NOT_FOUND, "missing asset")
        kind = {"css": "text/css", "js": "text/javascript", "svg": "image/svg+xml"}.get(
            name.rsplit(".", 1)[-1], "application/octet-stream")
        self._send(HTTPStatus.OK, file.read_bytes(), f"{kind}; charset=utf-8")

    def _page(self) -> None:
        """The tool itself, the same page the local tool serves, for a signed-in
        person. Signed out, it goes to the sign-in page and comes back."""
        token = self._cookie()
        person = self.portal.accounts.session(token)
        if person is None:
            return self._redirect("/signin?next=/app")
        page = (serve.WEB_DIR / "index.html").read_text(encoding="utf-8")
        data = {
            "hosted": "1",
            "extension-id": os.environ.get(EXTENSION_ID_ENV) or "",
            "min-version": EXTENSION_MIN_VERSION,
            "name": person.name,
            "email": person.email,
            "admin": "1" if person.admin else "",
            "picture": self.portal.accounts.picture(person.email),
            "source": page_values()["SOURCE_URL"],
        }
        page = fill_app_page(page, csrf_for(token), data)
        self._policy = app_policy(page)
        self._send(HTTPStatus.OK, page.encode(), "text/html; charset=utf-8")

    def _admin_page(self) -> None:
        token = self._cookie()
        person = self.portal.accounts.session(token)
        if person is None:
            return self._redirect("/signin?next=/admin")
        if not person.admin:
            return self._redirect("/app")
        self._policy = PAGE_POLICY
        body = render_page("admin.html", "Admin", "People, requests and usage.",
                           {"TOKEN": csrf_for(token), "SIGNED_IN": "1", **self._who(person)})
        self._send(HTTPStatus.OK, body, "text/html; charset=utf-8")

    def _account_page(self) -> None:
        token = self._cookie()
        person = self.portal.accounts.session(token)
        if person is None:
            return self._redirect("/signin?next=/account")
        self._policy = PAGE_POLICY
        body = render_page("account.html", "Your account", "Profile, history, keys and "
                           "feedback.", {
                               "TOKEN": csrf_for(token), "SIGNED_IN": "1", **self._who(person),
                               "EXTENSION_ID": os.environ.get(EXTENSION_ID_ENV) or "",
                               "MIN_VERSION": EXTENSION_MIN_VERSION})
        self._send(HTTPStatus.OK, body, "text/html; charset=utf-8")

    def _extension_zip(self) -> None:
        file = extension_zip(self.portal.root)
        if file is None:
            return self._not_found()
        self._send_media(file, "application/zip", {
            "Content-Disposition": 'attachment; filename="snipshare-extension.zip"'})

    # -- the renderer's API, one more resource ----------------------------------

    def _v1_clip(self) -> None:
        """A finished clip, for the extension to load into WhatsApp. The grant names
        this one clip and nothing else, and lasts fifteen minutes."""
        header = self.headers.get("Authorization", "")
        token = header[7:].strip() if header.startswith("Bearer ") else ""
        stem = self._params().get("stem", "")
        if not serve.SAFE_STEM.match(stem):
            return self._json({"error": "bad clip name"}, HTTPStatus.BAD_REQUEST)
        person = self.portal.accounts.check_grant(token, "clip", scope=stem, renew=True)
        if person is None:
            return self._json({"error": "that grant is not valid for this clip"},
                              HTTPStatus.UNAUTHORIZED)
        file = self.portal.workspace(person).out / f"{stem}.mp4"
        if not file.is_file():
            return self._json({"error": "that clip is gone"}, HTTPStatus.NOT_FOUND)
        self._send_media(file, "video/mp4", {
            "Content-Disposition": f'attachment; filename="{stem}.mp4"'})

    # -- calls anybody may make: sign up, sign in, sign out -----------------------

    def _open_call(self, method: str) -> None:
        try:
            body = self._json_body()
        except hosted.Refused as refused:
            return self._refuse(refused)
        if not self._same_site(required=True) or self.headers.get(OPEN_HEADER) != "1":
            return self._fail(HTTPStatus.FORBIDDEN, "that request did not come from this site")
        try:
            getattr(self, method)(body)
        except signin.Unavailable as exc:
            self._fail(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
        except AccessError as exc:
            self._fail(HTTPStatus.BAD_REQUEST, str(exc))

    def _signup(self, body: dict[str, Any]) -> None:
        address = self._address()
        if not self.portal.limiter.allow("signup", address, 5, 3600):
            self.portal.alert("signup-flood", "sign-ups are arriving faster than 5 an hour "
                              "from one address; they are being refused", every=3600)
            return self._fail(HTTPStatus.TOO_MANY_REQUESTS,
                              "too many requests from here. Try again in an hour")
        if not signin.human(str(body.get("turnstile") or ""), address):
            return self._fail(HTTPStatus.FORBIDDEN,
                              "the check that you are a person did not pass. Try again")
        credential = str(body.get("credential") or "")
        google = signin.google(credential) if credential else None
        email = google["email"] if google else body.get("email")
        answers = {"name": body.get("name") or (google["name"] if google else ""),
                   "use": body.get("use"), "heard": body.get("heard")}
        person, new = self.portal.accounts.request_access(
            email, answers, google_sub=google["sub"] if google else None)
        if new:
            self.portal.tell_owner_of_request(person, google is not None,
                                              bool(body.get("chrome")))
        if google and person.status == accounts.APPROVED:
            return self._signed_in(person, google)
        if not google:
            # A typed address proves nothing about who typed it, so the answer is
            # the same whatever that address's standing: it must not tell a
            # stranger whether somebody has an account, or has been suspended.
            return self._json({"status": accounts.PENDING, "new": True})
        self._json({"status": person.status, "new": new})

    def _session(self, body: dict[str, Any]) -> None:
        if not self.portal.limiter.allow("signin", self._address(), 30, 3600):
            return self._fail(HTTPStatus.TOO_MANY_REQUESTS,
                              "too many sign-ins from here. Try again in an hour")
        google = signin.google(str(body.get("credential") or ""))
        person = self.portal.accounts.person(google["email"])
        if person is None:
            return self._json({"status": "unknown", "email": google["email"],
                               "name": google["name"]})
        if person.status != accounts.APPROVED:
            return self._json({"status": person.status})
        self._signed_in(person, google)

    def _signed_in(self, person: Person, google: dict[str, Any] | None = None) -> None:
        if google and google.get("sub"):
            # The address is matched to the Google account that first used it: an
            # address Google later gives to somebody else, as a Workspace address can
            # be, does not inherit the account (D-101).
            known = self.portal.accounts.google_sub(person.email)
            if known and known != google["sub"]:
                log.warning("a sign-in for a known address came from another Google account")
                return self._fail(HTTPStatus.FORBIDDEN, "this Google account is not the one "
                                  "this address signed up with. Write to the operator")
            if not known:
                self.portal.accounts.bind_google(person.email, google["sub"])
        if google and google.get("picture"):
            self.portal.accounts.set_picture(person.email, google["picture"])
        token = self.portal.accounts.start_session(person.email, browser_of(
            self.headers.get("User-Agent") or ""))
        self._json({"status": accounts.APPROVED, "next": "/app"}, HTTPStatus.OK,
                   {"Set-Cookie": self._session_cookie(token, accounts.SESSION_DAYS * 86400)})

    def _signout(self, body: dict[str, Any]) -> None:
        self.portal.accounts.end_session(self._cookie())
        self._json({"signed_out": True}, HTTPStatus.OK,
                   {"Set-Cookie": self._session_cookie("", 0)})

    def _me(self) -> None:
        person = self._person()
        if person is None:
            return self._json({"signed_in": False})
        self._json({"signed_in": True, "email": person.email, "name": person.name,
                    "admin": person.admin})

    # -- calls a signed-in person makes -------------------------------------------

    def _account_call(self, method, admin: bool = False, body: bool = True,
                      limit: int = hosted.JSON_MAX) -> None:
        # Who is asking is settled before the body is read, so nobody who is not
        # signed in can make this process read up to `limit` (12 MB for feedback).
        # A refusal leaves the body unread, so the connection ends with it.
        token = self._cookie()
        person = self.portal.accounts.session(token)
        if person is None:
            self._close_unread()
            return self._fail(HTTPStatus.UNAUTHORIZED, "sign in again")
        offered = self.headers.get(serve.TOKEN_HEADER) or ""
        if not secrets.compare_digest(offered, csrf_for(token)) \
                or not self._same_site(required=body):
            self._close_unread()
            return self._fail(HTTPStatus.FORBIDDEN, "reload the page and try again")
        if admin and not person.admin:
            self._close_unread()
            return self._fail(HTTPStatus.FORBIDDEN, "that is for the admin")
        try:
            payload = self._json_body_within(limit) if body else {}
        except hosted.Refused as refused:
            return self._refuse(refused)
        try:
            method(person, payload)
        except AccessError as exc:
            self._fail(HTTPStatus.BAD_REQUEST, str(exc))

    def _json_body_within(self, limit: int) -> dict[str, Any]:
        try:
            body = json.loads(self._read(limit) or b"{}")
        except (ValueError, RecursionError) as exc:
            raise hosted.Refused(HTTPStatus.BAD_REQUEST, "the body is not JSON") from exc
        if not isinstance(body, dict):
            raise hosted.Refused(HTTPStatus.BAD_REQUEST, "the body has to be an object")
        return body

    def _grant(self, person: Person, body: dict[str, Any]) -> None:
        """A token the extension can use for fifteen minutes and one purpose: to
        upload a capture, or to fetch one named clip. It never holds the session."""
        if not self.portal.limiter.allow("grant", person.id, 120, 3600):
            return self._fail(HTTPStatus.TOO_MANY_REQUESTS, "slow down a little")
        purpose = str(body.get("purpose") or "")
        scope = ""
        extra: dict[str, Any] = {}
        if purpose == "clip":
            scope = str(body.get("stem") or "")
            if not serve.SAFE_STEM.match(scope) or not (
                    self.portal.workspace(person).out / f"{scope}.mp4").is_file():
                return self._fail(HTTPStatus.NOT_FOUND, "no such clip")
        elif purpose == "upload":
            # Everything that would refuse the clip, asked before the extension
            # spends a minute reading the video for it.
            # A limit is a 429 here as it is at /api/render, so the page treats a
            # refusal the same wherever it arrives.
            try:
                self.portal.accounts.check_clip(person.email)
                self.portal.check_room()
            except AccessError as exc:
                return self._fail(HTTPStatus.TOO_MANY_REQUESTS, str(exc))
            if self.portal.workspace(person).running("render"):
                return self._fail(HTTPStatus.CONFLICT, "a clip of yours is already being "
                                  "made. Wait for it, or stop it")
            extra = _window(body.get("window"))
        grant = self.portal.accounts.grant(person.email, purpose, scope)
        self._json({"grant": grant, "server": self._origin(),
                    "expires_in": accounts.GRANT_SECONDS, **extra})

    def _report(self, person: Person, body: dict[str, Any]) -> None:
        """A failure the page or the extension saw: a phase, a code and versions,
        never the video. A person's own words go through Feedback."""
        if not self.portal.limiter.allow("report", person.id, 30, 3600):
            return self._json({"recorded": False})
        source = str(body.get("source") or "")
        if source not in ("capture", "load", "page", "words"):
            raise AccessError("unknown source")
        phase = plain(body.get("phase"), 40)
        code = plain(body.get("code"), 80)
        self.portal.accounts.report(source, phase, code,
                                    detail=str(body.get("detail") or ""),
                                    versions=str(body.get("versions") or ""),
                                    email=person.email)
        recent = [r for r in self.portal.accounts.reports(time.time() - 3600, source)]
        people = {r["email"] for r in recent}
        if len(recent) >= 3 and len(people) >= 2:
            self.portal.alert(f"{source}-failures",
                              f"{len(recent)} {source} failures from {len(people)} people "
                              f"in the last hour, the latest {phase}/{code}. "
                              "YouTube or WhatsApp may have changed")
        self._json({"recorded": True})

    def _delete_account(self, person: Person, body: dict[str, Any]) -> None:
        if str(body.get("confirm") or "").strip().lower() != person.email:
            raise AccessError("type your email address to confirm")
        if person.admin:
            raise AccessError("the admin account is removed from the server's settings")
        self.portal.forget(person.email)
        log.info("an account was deleted at its owner's request")
        self._json({"deleted": True}, HTTPStatus.OK,
                   {"Set-Cookie": self._session_cookie("", 0)})

    def _gif_key(self, person: Person, body: dict[str, Any]) -> None:
        provider = str(body.get("provider") or "").strip().lower()
        key = str(body.get("key") or "").strip()
        if provider not in gifs.PROVIDERS or not key or len(key) > 200:
            raise AccessError("choose GIPHY or KLIPY, and paste the key")
        if not self.portal.limiter.allow("gifkey", person.id, 10, 3600):
            return self._fail(HTTPStatus.TOO_MANY_REQUESTS, "try again in an hour")
        # Checked against the service before it is kept, with one search, so a typo
        # is caught here rather than at the first GIF they want.
        token = gifs.personal.set(gifs.Personal(keys={provider: key}, choice=provider))
        try:
            gifs.search("hello", limit=1)
        except gifs.GifError as exc:
            raise AccessError(str(exc)) from exc
        finally:
            gifs.personal.reset(token)
        store = self.portal.accounts
        store.set_gif_key(person.email, provider, key)
        # A second key means both, unless the person has already said otherwise.
        if len(store.gif_keys(person.email)) > 1 and not store.gif_source(person.email):
            store.set_gif_source(person.email, gifs.BOTH)
        self._json(self._gif_overview(person))

    def _gif_key_delete(self, person: Person, body: dict[str, Any]) -> None:
        provider = str(body.get("provider") or "").strip().lower()
        if provider not in gifs.PROVIDERS:
            raise AccessError("say which key to remove")
        self.portal.accounts.remove_gif_key(person.email, provider)
        self._json(self._gif_overview(person))

    def _gif_source(self, person: Person, body: dict[str, Any]) -> None:
        source = str(body.get("source") or body.get("provider") or "").strip().lower()
        self.portal.accounts.set_gif_source(person.email, source)
        self._json(self._gif_overview(person))

    def _gif_overview(self, person: Person) -> dict[str, Any]:
        store = self.portal.accounts
        token = gifs.personal.set(gifs.Personal(keys=store.gif_keys(person.email),
                                                choice=store.gif_source(person.email)))
        try:
            return {"keys": store.gif_key_hints(person.email), "source": gifs.provider(),
                    "credit": gifs.credit()}
        finally:
            gifs.personal.reset(token)

    # -- the account page's calls --------------------------------------------

    def _account_overview(self, person: Person, body: dict[str, Any]) -> None:
        clips, upload = accounts.limits()
        self._json({
            "profile": person.as_json() | {"answers": None,
                                           "picture": self.portal.accounts.picture(person.email)},
            "sessions": self.portal.accounts.sessions_of(person.email, self._cookie()),
            "usage": self.portal.accounts.usage(person.email),
            "gifs": self._gif_overview(person),
            "kept": KEEP_CLIPS, "history_days": accounts.HISTORY_DAYS,
            "contact": contact(),
        })

    def _account_history(self, person: Person, body: dict[str, Any]) -> None:
        workspace = self.portal.workspace(person)
        kept = {clip["stem"] for clip in workspace.clips(limit=KEEP_CLIPS)}
        rows = []
        for row in self.portal.accounts.history(person.email):
            row["kept"] = bool(row["stem"]) and row["stem"] in kept
            rows.append(row)
        self._json({"days": self.portal.accounts.days(person.email), "clips": rows,
                    "usage": self.portal.accounts.usage(person.email)})

    def _sessions_end(self, person: Person, body: dict[str, Any]) -> None:
        """End one other session by its id, or every other one with `others`."""
        if body.get("others"):
            ended = self.portal.accounts.end_other_sessions(person.email, self._cookie())
        else:
            ident = str(body.get("id") or "")
            current = [s for s in self.portal.accounts.sessions_of(person.email, self._cookie())
                       if s["current"]]
            if current and current[0]["id"] == ident:
                raise AccessError("use Sign out to end this one")
            ended = int(self.portal.accounts.end_session_named(person.email, ident))
        self._json({"ended": ended,
                    "sessions": self.portal.accounts.sessions_of(person.email, self._cookie())})

    def _profile(self, person: Person, body: dict[str, Any]) -> None:
        self._json(self.portal.accounts.rename(person.email, body.get("name")).as_json())

    FEEDBACK_KINDS = {"idea": "An idea", "problem": "A problem", "question": "A question",
                      "other": "Something else"}

    def _feedback(self, person: Person, body: dict[str, Any]) -> None:
        """A note to the operator, by mail, with the person's address to reply to.
        Only ever to the operator: the reply-to is the person's own, Google checked,
        address, so nobody can use this to mail anybody else."""
        kind = str(body.get("kind") or "other")
        if kind not in self.FEEDBACK_KINDS:
            raise AccessError("choose what kind of note this is")
        words = str(body.get("message") or "").replace("\r\n", "\n").strip()
        if len(words) < 3:
            raise AccessError("write a few words first")
        if len(words) > 3000:
            raise AccessError("that is over 3000 characters; shorten it a little")
        if not self.portal.limiter.allow("feedback", person.id, 5, 3600):
            return self._fail(HTTPStatus.TOO_MANY_REQUESTS,
                              "that is five notes this hour. Thank you; they are being read")
        subject = " ".join(str(body.get("subject") or "").split())
        if not subject:
            raise AccessError("add a subject, a few words on what this is about")
        if len(subject) > 120:
            raise AccessError("keep the subject under 120 characters")
        name = " ".join(str(body.get("name") or person.name or "").split())[:120] or person.email
        shots = screenshots(body.get("attachments"))
        code = plain(body.get("code"), 120)
        versions = plain(body.get("versions"), 160)
        label = self.FEEDBACK_KINDS[kind]
        lines = [f"{label} from {name} <{person.email}>", f"Subject: {subject}", ""]
        lines += words.split("\n")
        lines += ["", f"Screenshots attached: {len(shots)}" if shots else "No screenshots.",
                  f"The last failure their page saw: {code or 'none'}",
                  f"Versions: {versions or 'not given'}",
                  "", "Reply to this email to answer them directly."]
        # Kept as well as mailed, short, so the admin page has it whatever the mail
        # does; the mail carries it whole.
        self.portal.accounts.report("feedback", kind, code, detail=f"{subject}: {words}"[:400],
                                    versions=versions, email=person.email)
        word = {"idea": "idea", "problem": "problem", "question": "question"}.get(kind, "note")
        sent = notify.email(f"{NAME} {word}: {subject} ({name})", lines, wait=True,
                            reply_to=person.email, attachments=shots)
        if not sent:
            log.warning("feedback (%s) was kept but could not be mailed", kind)
        else:
            log.info("feedback (%s) sent for a person", kind)
        self._json({"sent": True, "mailed": sent})

    # -- the admin's calls ----------------------------------------------------

    def _admin_overview(self, person: Person, body: dict[str, Any]) -> None:
        """Everything on the admin page, for the days asked (`from` and `to`, UTC,
        inclusive; today when not given), plus the state of the machine now."""
        params = self._params()
        first, last = _day_range(params.get("from"), params.get("to"))
        store = self.portal.accounts
        summary = store.range_summary(first, last)
        used = {row["email"]: row for row in summary["by_person"]}
        people = []
        for one in store.people():
            row = one.as_json() | {"picture": store.picture(one.email)}
            got = used.get(one.email) or {}
            row["range"] = {"clips": got.get("clips") or 0, "failures": got.get("failures") or 0,
                            "upload_bytes": got.get("upload_bytes") or 0}
            people.append(row)
        self._json({
            "range": {"from": first, "to": last},
            "totals": summary["totals"] | {"new_requests": summary["new_requests"]},
            "people": people,
            "usage": summary["by_person"],
            "reports": summary["reports"],
            "renderer": self.portal.renderer.health(),
            "disk_free_gb": round(shutil.disk_usage(self.portal.root).free / 1e9, 1),
            "notifications": notify.configured(),
            "clips_per_day": accounts.limits()[0],
            "site": public_url(),
        })

    def _admin_decide(self, person: Person, body: dict[str, Any]) -> None:
        decided = self.portal.accounts.decide(str(body.get("email") or ""),
                                              str(body.get("status") or ""))
        log.info("access for a person set to %s by the admin", decided.status)
        self._json(decided.as_json())

    def _admin_add(self, person: Person, body: dict[str, Any]) -> None:
        added = self.portal.accounts.add(str(body.get("email") or ""),
                                         " ".join(str(body.get("name") or "").split())[:120])
        self._json(added.as_json())

    def _admin_forget(self, person: Person, body: dict[str, Any]) -> None:
        email = accounts.normal_email(body.get("email"))
        if self.portal.accounts.person(email) is None:
            raise AccessError("nobody has that address")
        self.portal.forget(email)
        self._json({"forgotten": True})

    # -- the page API, where the hosted page differs from the local one --------

    def _render(self, body: dict[str, Any]) -> None:
        if not self.portal.limiter.allow("render", self.app.pid, 30, 3600):
            return self._fail(HTTPStatus.TOO_MANY_REQUESTS,
                              "that is a lot of clips asked for in an hour. Try again later")
        try:
            job = self._job_from(body)
            captured = _captured(body.get("captured"), job)
        except ValueError as exc:
            return self._fail(HTTPStatus.BAD_REQUEST, str(exc))
        try:
            task = self.app.render_captured(job, captured)
        except AccessError as exc:
            return self._fail(HTTPStatus.TOO_MANY_REQUESTS, str(exc))
        except RuntimeError as exc:
            return self._fail(HTTPStatus.CONFLICT, str(exc))
        except hosted.Refused as refused:
            return self._fail(refused.status, str(refused))
        self._json({"id": task.id})

    def _words(self, body: dict[str, Any]) -> None:
        try:
            words = self.app.words_of(str(body.get("url") or ""),
                                      str(body.get("title") or ""),
                                      str(body.get("channel") or ""))
        except ValueError as exc:
            return self._fail(HTTPStatus.BAD_REQUEST, str(exc))
        self._json(words)

    def _gif_provider(self, body: dict[str, Any]) -> None:
        """The shelf's choice of service: the person's own, kept for next time."""
        try:
            self.portal.accounts.set_gif_source(self.person.email,
                                                str(body.get("provider") or "").lower())
        except AccessError as exc:
            return self._fail(HTTPStatus.BAD_REQUEST, str(exc))
        gifs.personal.set(self.app.gif_settings())  # reset with the rest at the end
        self.app.remember_gifs([])
        self._json(gifs.credit())

    def _upload_sticker(self, body: dict[str, Any]) -> None:
        """As the local page's, plus a count per person and the day's upload
        allowance: a sticker is bytes sent to this server like any capture."""
        encoded = str(body.get("data") or "")
        size = len(encoded.split(",")[-1]) * 3 // 4
        email = self.person.email
        with self.app.sticker_lock:
            folder = stickers.uploads_dir()
            if folder.is_dir() and sum(1 for _ in folder.iterdir()) >= STICKER_UPLOADS_MAX:
                return self._fail(HTTPStatus.BAD_REQUEST,
                                  f"you have {STICKER_UPLOADS_MAX} stickers of your own. "
                                  "Delete one to add another")
            try:
                self.portal.accounts.reserve_upload(email, size)
            except AccessError as exc:
                return self._fail(HTTPStatus.TOO_MANY_REQUESTS, str(exc))
            try:
                saved = stickers.save_upload(str(body.get("name") or ""), encoded)
            except (ValueError, OSError) as exc:
                self.portal.accounts.refund_upload(email, size)  # nothing was kept
                if isinstance(exc, OSError):
                    log.exception("a sticker could not be saved")
                    return self._fail(HTTPStatus.INTERNAL_SERVER_ERROR,
                                      "the sticker could not be saved. Try again")
                return self._fail(HTTPStatus.BAD_REQUEST, str(exc))
        self._json(saved)


FEEDBACK_MAX = 12_000_000          # a request carrying up to three screenshots
DRAIN_MAX = 1_000_000              # a refused body up to this size is read and dropped
SCREENSHOTS_MAX = 3
SCREENSHOT_BYTES = 4_000_000       # each, as sent
SCREENSHOT_EDGE = 2560


def screenshots(raw: Any) -> list[dict[str, str]]:
    """Images a person attached to feedback, ready to mail. Each is opened and
    written again by Pillow, so what reaches the operator is a plain picture with no
    metadata, whatever was sent. Nothing is kept on the server."""
    if raw in (None, ""):
        return []
    if not isinstance(raw, list) or len(raw) > SCREENSHOTS_MAX:
        raise AccessError(f"attach at most {SCREENSHOTS_MAX} screenshots")
    from PIL import Image, UnidentifiedImageError

    out = []
    for index, item in enumerate(raw, 1):
        data = str((item or {}).get("data") or "") if isinstance(item, dict) else ""
        if "," in data[:100]:
            data = data.split(",", 1)[1]           # a data: address, as browsers give
        try:
            raw_bytes = base64.b64decode(data, validate=True)
        except (ValueError, TypeError) as exc:
            raise AccessError(f"screenshot {index} could not be read") from exc
        if not raw_bytes or len(raw_bytes) > SCREENSHOT_BYTES:
            raise AccessError(f"screenshot {index} is over {SCREENSHOT_BYTES // 1_000_000} MB")
        try:
            with Image.open(io.BytesIO(raw_bytes)) as image:
                if image.width * image.height > 40_000_000:
                    raise AccessError(f"screenshot {index} is too large")
                image.load()
                picture = image.convert("RGB")
        except AccessError:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise AccessError(f"screenshot {index} is not a picture") from exc
        picture.thumbnail((SCREENSHOT_EDGE, SCREENSHOT_EDGE))
        buffer = io.BytesIO()
        picture.save(buffer, "JPEG", quality=85, optimize=True)
        out.append({"filename": f"screenshot-{index}.jpg",
                    "content": base64.b64encode(buffer.getvalue()).decode()})
    return out


def _day_range(first: Any, last: Any) -> tuple[str, str]:
    """Two UTC days, inclusive and in order, no more than a year apart. Today when
    not given or not dates."""
    def day(value: Any) -> str | None:
        try:
            return datetime.strptime(str(value or ""), "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            return None
    today_ = accounts.today()
    a, b = day(first) or today_, day(last) or today_
    if a > b:
        a, b = b, a
    if (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days > 366:
        raise AccessError("choose a range of a year or less")
    return a, b


def browser_of(agent: str) -> str:
    """"Chrome on Linux", from a User-Agent: enough to recognise a session, and no
    more. Unknown parts are left out rather than guessed."""
    browser = next((name for mark, name in (
        ("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("CriOS/", "Chrome"),
        ("Chrome/", "Chrome"), ("Safari/", "Safari")) if mark in agent), "")
    system = next((name for mark, name in (
        ("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("CrOS", "ChromeOS"),
        ("Windows", "Windows"), ("Mac OS X", "macOS"), ("Linux", "Linux")) if mark in agent), "")
    if browser and system:
        return f"{browser} on {system}"
    return browser or system or "A browser"


def _window(raw: Any) -> dict[str, Any]:
    """The window the extension is to read, worked out exactly as the render will
    work it out (`serve.Handler._job_from`), so the two cannot disagree."""
    if not isinstance(raw, dict):
        raise AccessError("say which video and which part of it")
    url = str(raw.get("url") or "").strip()
    video_id = video_id_of(url)
    if not video_id:
        raise AccessError("that is not a YouTube video link")
    try:
        stop = str(raw.get("end") or "").strip() or None
        length = None if stop else float(raw.get("duration") or 0) or None
        start, end = pipeline.resolve_window(url, str(raw.get("start") or "") or None,
                                             stop, length)
    except (TimecodeError, ValueError, TypeError) as exc:
        raise AccessError(str(exc)) from exc
    return {"video_id": video_id, "start": start, "end": end}


def _captured(raw: Any, job: pipeline.Job) -> dict[str, Any]:
    """What the extension said it uploaded, checked against the form it came with."""
    if not isinstance(raw, dict):
        raise ValueError("making a clip here needs the SnipShare extension to read the "
                         "video first")
    video_id = str(raw.get("video_id") or "")
    if not YOUTUBE_ID.match(video_id):
        raise ValueError("the capture did not say which video it is")
    if video_id_of(job.url) != video_id:
        raise ValueError("the capture is of a different video from the link. Make it again")
    duration = raw.get("duration")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) \
            or not 0 < duration < 24 * 3600:
        raise ValueError("the capture did not say how long the video is")
    captured: dict[str, Any] = {
        "video_id": video_id,
        "title": " ".join(str(raw.get("title") or "").split())[:300],
        "channel": " ".join(str(raw.get("channel") or "").split())[:200],
        "artist": " ".join(str(raw.get("artist") or "").split())[:200],
        "duration": float(duration),
    }
    for kind in ("audio", "video", "artwork"):
        value = raw.get(kind)
        if value is not None:
            if not isinstance(value, str) or not hosted.ID.match(value):
                raise ValueError(f"the {kind} upload is not named properly")
            captured[kind] = value
    if "audio" not in captured:
        raise ValueError("the capture has no audio")
    if job.video and "video" not in captured:
        raise ValueError("video frames need the captured video. Make it again")
    if not job.video and "artwork" not in captured:
        raise ValueError("the artwork card needs the video's thumbnail. Make it again")
    return captured


OPEN_CALLS = {"/api/signup": "_signup", "/api/session": "_session",
              "/api/signout": "_signout"}
ACCOUNT_CALLS = {
    "/api/grant": ("_grant", False),
    "/api/report": ("_report", False),
    "/api/account/delete": ("_delete_account", False),
    "/api/gifkey": ("_gif_key", False),
    "/api/gifkey/delete": ("_gif_key_delete", False),
    "/api/gifkey/source": ("_gif_source", False),
    "/api/account/profile": ("_profile", False),
    "/api/account/sessions/end": ("_sessions_end", False),
    "/api/feedback": ("_feedback", False),
    "/api/admin/decide": ("_admin_decide", True),
    "/api/admin/add": ("_admin_add", True),
    "/api/admin/forget": ("_admin_forget", True),
}

# path: (template, title, description)
SITE_PAGES = {
    "/": ("home.html", f"{NAME}: {TAGLINE}",
          "Share the part of a YouTube video you love as a WhatsApp Status, with the "
          "link back to the original in every clip."),
    "/install": ("install.html", f"Get the extension: {NAME}",
                 "Making a clip needs desktop Chrome with the SnipShare extension."),
    "/privacy": ("privacy.html", f"Privacy: {NAME}", "What SnipShare keeps, and why."),
    "/terms": ("terms.html", f"Terms: {NAME}", "The terms of using SnipShare."),
    "/signup": ("signup.html", f"Request access: {NAME}",
                "SnipShare is by invitation. Ask for access here."),
    "/signin": ("signin.html", f"Sign in: {NAME}", "Sign in to SnipShare with Google."),
}
SITE_ASSETS = {"/site.css": "site.css", "/site.js": "site.js", "/theme.js": "theme.js",
               "/account.js": "account.js", "/nav.js": "nav.js", "/nav.css": "nav.css",
               "/hosted.js": "hosted.js",
               "/hosted.css": "hosted.css", "/admin.js": "admin.js",
               "/mark.svg": "mark.svg"}

GOOGLE = "https://accounts.google.com/gsi/"
TURNSTILE = "https://challenges.cloudflare.com"
PAGE_POLICY = (
    "default-src 'self'; "
    f"script-src 'self' {GOOGLE}client {TURNSTILE}; "
    f"style-src 'self' 'unsafe-inline' {GOOGLE}style; "
    f"frame-src {GOOGLE} {TURNSTILE}; "
    f"connect-src 'self' {GOOGLE}; "
    "img-src 'self' data: https://*.googleusercontent.com; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def app_policy(page: str) -> str:
    """The tool page's policy. Its one inline script, the theme set before the
    first paint, is allowed by its hash and nothing else inline is."""
    hashes = " ".join(
        "'sha256-" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + "'"
        for body in re.findall(r"<script>(.*?)</script>", page, flags=re.S))
    return ("default-src 'self'; "
            f"script-src 'self' {hashes}; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: https://*.googleusercontent.com; "
            "media-src 'self' blob:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; "
            "frame-ancestors 'none'")


def fill_app_page(page: str, token: str, data: dict[str, str]) -> str:
    attributes = " ".join(f'data-{key}="{html.escape(value, quote=True)}"'
                          for key, value in data.items())
    values = {
        "TOKEN": token,
        "TITLE": NAME,
        "BRAND": NAME,
        "TAGLINE": html.escape(TAGLINE),
        "BODY_DATA": attributes,
        "HEAD": '<link rel="stylesheet" href="/hosted.css">\n'
                '<link rel="stylesheet" href="/nav.css">',
        "SCRIPTS": '<script src="/nav.js"></script>\n<script src="/hosted.js"></script>',
    }
    # One pass, so nothing put in is looked at again: a person named `{{HEAD}}`
    # must stay a name, not become the stylesheet links inside their own attribute.
    return re.sub(r"\{\{(" + "|".join(values) + r")\}\}",
                  lambda match: values[match.group(1)], page)


# The extension people install, built into the image beside the code, where the
# running app cannot write (`read_only`, and owned by root): a break-in to the app
# must not be able to swap what every new person installs into their browser. A
# copy in the data volume is only looked at outside the image, for a local server.
IMAGE_EXTENSION = Path(__file__).resolve().parent.parent / "extension" / "snipshare-extension.zip"
_digests: dict[tuple[str, float], str] = {}


def extension_zip(root: Path) -> Path | None:
    for file in (IMAGE_EXTENSION, root / "extension" / "snipshare-extension.zip"):
        if file.is_file():
            return file
    return None


def extension_digest(root: Path) -> str:
    """The zip's SHA-256, shown on /install so a download can be checked."""
    file = extension_zip(root)
    if file is None:
        return ""
    key = (str(file), file.stat().st_mtime)
    if key not in _digests:
        _digests[key] = hashlib.sha256(file.read_bytes()).hexdigest()
    return _digests[key]


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def page_values() -> dict[str, str]:
    """What the public pages are filled with. All of it from the environment."""
    site = public_url()
    return {
        "NAME": NAME,
        "TAGLINE": TAGLINE,
        "SITE": site or "this site",
        "CONTACT": contact() or "the address on the operator's website",
        "OPERATOR": (os.environ.get(OPERATOR_ENV) or "").strip() or "the operator",
        "STATUS_URL": (os.environ.get(STATUS_PAGE_ENV) or "").strip(),
        "SOURCE_URL": (os.environ.get(SOURCE_ENV) or "").strip() or SOURCE_URL,
        "GOOGLE_CLIENT_ID": signin.client_id(),
        "TURNSTILE_SITEKEY": signin.turnstile_site_key(),
        "CLIPS_PER_DAY": str(accounts.limits()[0]),
        "UPLOAD_MB_PER_DAY": str(accounts.limits()[1] // 1_000_000),
        "MAX_SECONDS": f"{pipeline.MAX_DURATION:.0f}",
        "KEEP_CLIPS": str(KEEP_CLIPS),
        "YEAR": time.strftime("%Y"),
    }


def render_page(name: str, title: str, description: str,
                extra: dict[str, str] | None = None) -> bytes:
    """A public page: its body inside the shared layout. Every `{{KEY}}` is
    replaced by an escaped value; one that is not known is left empty, so a
    template can never print a placeholder at somebody."""
    values = {**page_values(), "TITLE": title, "DESCRIPTION": description,
              **(extra or {})}
    layout = (PAGES / "layout.html").read_text(encoding="utf-8")
    body = (PAGES / name).read_text(encoding="utf-8")
    page = layout.replace("{{BODY}}", body).replace("{{PAGE}}", name.rsplit(".", 1)[0])

    def value(match: re.Match) -> str:
        return html.escape(values.get(match.group(1), ""), quote=True)

    return re.sub(r"\{\{([A-Z_]+)\}\}", value, page).encode()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Every connection is a thread. Past this many at once a new one is closed at
    # once rather than given a thread, so slow connections cannot use up the
    # container's processes, which ffmpeg needs too (D-101).
    MAX_CONNECTIONS = 200

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._connections = threading.BoundedSemaphore(self.MAX_CONNECTIONS)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._connections.acquire(blocking=False):
            log.warning("connection refused: %d already open", self.MAX_CONNECTIONS)
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._connections.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connections.release()

    def handle_error(self, request: Any, client_address: Any) -> None:
        # A phone that walks out of signal, or a tab closed mid-download, is not a
        # fault, and a traceback for each one buries the ones that are.
        if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError,
                                           TimeoutError)):
            return
        super().handle_error(request, client_address)


def make_server(portal: Portal, port: int, host: str) -> ThreadingHTTPServer:
    handler = type("BoundSiteHandler", (SiteHandler,),
                   {"portal": portal, "renderer": portal.renderer})
    server = Server((host, port), handler)
    server.daemon_threads = True
    return server


# -- the owner's command line ----------------------------------------------------

def user_command(root: Path, action: str, email: str | None, name: str = "") -> int:
    store = Accounts(root / "people.db")
    if action == "list":
        for person in store.people():
            used = store.usage(person.email)
            print(f"{person.status:9} {person.role:5} {person.email}\t{person.name}\t"
                  f"today {used['clips']} clips")
        return 0
    if not email:
        print("error: an email address is needed")
        return 1
    try:
        if action == "add":
            person = store.add(email, name)
        elif action == "forget":
            person = store.person(accounts.normal_email(email))
            store.forget(email)
            if person is not None:
                shutil.rmtree(root / "users" / person.id, ignore_errors=True)
            print(f"forgot {email}")
            return 0
        else:
            person = store.decide(email, {"approve": accounts.APPROVED,
                                          "decline": accounts.DECLINED,
                                          "suspend": accounts.SUSPENDED}[action])
    except AccessError as exc:
        print(f"error: {exc}")
        return 1
    print(f"{person.email} is {person.status}")
    return 0
