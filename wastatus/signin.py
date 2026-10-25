"""Proving who someone is, and that they are a person: Google sign-in, Turnstile,
and a rate limiter for the doors anyone can knock on.

Google's ID token is checked with `google-auth`, which the tool already depends on
for the Sheets record: signature against Google's published keys, issuer, audience
(this site's own client), expiry, and a verified email. Measured working against the
real client on 2026-10-25. The client ID, Turnstile's keys and every other setting
come from the environment.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .accounts import AccessError, normal_email

log = logging.getLogger("wastatus")

CLIENT_ENV = "WASTATUS_GOOGLE_CLIENT_ID"
TURNSTILE_SITE_ENV = "WASTATUS_TURNSTILE_SITEKEY"
TURNSTILE_SECRET_ENV = "WASTATUS_TURNSTILE_SECRET"
TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class Unavailable(AccessError):
    """A check that could not be made, rather than one that failed."""


def client_id() -> str:
    return os.environ.get(CLIENT_ENV) or ""


def google(credential: str) -> dict[str, Any]:
    """The verified email, name and subject in a Google ID token, or AccessError."""
    if not client_id():
        raise AccessError("Google sign-in is not set up on this server")
    if not credential or len(credential) > 8192:
        raise AccessError("that sign-in did not come through. Try again")
    from google.auth.transport import requests as transport
    from google.oauth2 import id_token

    from google.auth import exceptions as google_errors

    try:
        info = id_token.verify_oauth2_token(credential, transport.Request(), client_id())
    except ValueError as exc:
        log.info("a Google sign-in was refused: %s", exc)
        raise AccessError("that sign-in could not be checked. Try again") from exc
    except (google_errors.GoogleAuthError, OSError) as exc:
        # Google's keys could not be fetched: their outage or ours, not the person's.
        log.warning("Google sign-in could not be checked: %s", exc)
        raise Unavailable("Google sign-in cannot be reached right now. Try again in "
                          "a minute") from exc
    if info.get("iss") not in ISSUERS:
        raise AccessError("that sign-in did not come from Google")
    if not info.get("email_verified"):
        raise AccessError("Google has not confirmed that email address yet")
    return {"email": normal_email(info.get("email")), "name": str(info.get("name") or ""),
            "sub": str(info.get("sub") or ""), "picture": photo(info.get("picture"))}


def photo(url: Any) -> str:
    """A Google account photo's address, if it is one: shown on the person's own
    pages, so it must be Google's and nothing a token could be made to carry."""
    url = str(url or "")
    if len(url) <= 500 and url.startswith("https://") and \
            urllib.parse.urlsplit(url).hostname and \
            urllib.parse.urlsplit(url).hostname.endswith(".googleusercontent.com"):
        return url
    return ""


def turnstile_site_key() -> str:
    return os.environ.get(TURNSTILE_SITE_ENV) or ""


def human(token: str, address: str = "") -> bool:
    """Cloudflare Turnstile's answer for a form. With no secret set (a local copy,
    or tests) every request passes, and that is logged, never silent."""
    secret = os.environ.get(TURNSTILE_SECRET_ENV) or ""
    if not secret:
        log.info("Turnstile is not configured; the check is skipped")
        return True
    if not token or len(token) > 4096:
        return False
    body = urllib.parse.urlencode({"secret": secret, "response": token,
                                   "remoteip": address}).encode()
    # A named User-Agent: Cloudflare refuses Python's default one (see notify.py).
    request = urllib.request.Request(TURNSTILE_URL, data=body, method="POST",
                                     headers={"User-Agent": "SnipShare/1.0 (form check)"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            answer = json.loads(response.read() or b"{}")
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        # Cloudflare unreachable. Failing closed stops sign-ups during its outage,
        # failing open lets bots in during one; a sign-up can be tried again.
        log.warning("Turnstile could not be asked: %s", exc)
        return False
    return bool(answer.get("success"))


class Limiter:
    """At most `count` events per `window` seconds for each key. In memory: a
    restart forgets, which errs on the side of letting a person back in."""

    def __init__(self) -> None:
        self._seen: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, bucket: str, key: str, count: int, window: float) -> bool:
        now = time.time()
        with self._lock:
            hits = [t for t in self._seen.get((bucket, key), []) if now - t < window]
            if len(hits) >= count:
                self._seen[(bucket, key)] = hits
                return False
            hits.append(now)
            self._seen[(bucket, key)] = hits
            if len(self._seen) > 50_000:  # never grow without bound
                self._seen = {k: v for k, v in self._seen.items() if v and now - v[-1] < 3600}
            return True
