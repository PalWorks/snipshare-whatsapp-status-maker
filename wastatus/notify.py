"""Telling the owner: an email through Resend, and a message in a Google Chat space.

Both are optional and both are fire and forget. A notification that cannot be
delivered is logged and dropped: it must never cost anybody a sign-up, a clip or a
page load. Everything that says where they go comes from the environment, so no
address, key or webhook is ever in the code. See D-089 and D-093.

Mail only ever goes to the owner's own address, `WASTATUS_MAIL_TO`. Nothing here
sends to an address somebody typed into a form, which is what keeps the sending
domain's reputation out of a stranger's hands.
"""

from __future__ import annotations

import html
import json
import logging
import os
import threading
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger("wastatus")

RESEND_KEY_ENV = "WASTATUS_RESEND_KEY"
MAIL_FROM_ENV = "WASTATUS_MAIL_FROM"
MAIL_TO_ENV = "WASTATUS_MAIL_TO"
CHAT_ENV = "WASTATUS_CHAT_WEBHOOK"

RESEND_URL = "https://api.resend.com/emails"
TIMEOUT = 15
# Resend sits behind Cloudflare, which refuses Python's default User-Agent with a
# 403 (error 1010) before Resend ever sees the request. Found on the first send
# from the server, 2026-10-25.
USER_AGENT = "SnipShare/1.0 (owner notifications)"


def _post(url: str, payload: dict[str, Any], headers: dict[str, str]) -> int:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json; charset=UTF-8",
                 "User-Agent": USER_AGENT, **headers})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError) as exc:
        log.warning("notification not delivered: %s", exc)
        return 0


def gmail_html(lines: list[str]) -> str:
    """The body as the Gmail composer would write it: one div per line, an empty
    div between paragraphs, no fonts set. An empty string is a paragraph break."""
    parts = []
    for line in lines:
        parts.append("<div><br></div>" if not line else f"<div>{html.escape(line)}</div>")
    return '<div dir="ltr">' + "".join(parts) + "</div>"


def email(subject: str, lines: list[str], wait: bool = False, reply_to: str = "",
          attachments: list[dict[str, str]] | None = None) -> bool:
    """Mail the owner. Returns whether it was handed to Resend, when `wait`.

    `reply_to` is for feedback: the person's own address, so the owner can answer
    from their inbox. The mail itself still only ever goes to the owner."""
    key = os.environ.get(RESEND_KEY_ENV) or ""
    sender = os.environ.get(MAIL_FROM_ENV) or ""
    to = os.environ.get(MAIL_TO_ENV) or ""
    if not (key and sender and to):
        log.info("mail not configured; skipped: %s", subject)
        return False
    payload = {"from": sender, "to": [to], "subject": subject,
               "text": "\n".join(lines), "html": gmail_html(lines)}
    if reply_to:
        payload["reply_to"] = [reply_to]
    if attachments:
        # Resend's own shape: a file name and the bytes in base64.
        payload["attachments"] = [{"filename": a["filename"], "content": a["content"]}
                                  for a in attachments]

    def send() -> bool:
        status = _post(RESEND_URL, payload, {"Authorization": f"Bearer {key}"})
        if status not in (200, 201, 202):
            log.warning("Resend answered %s for %r", status, subject)
            return False
        return True

    return _run(send, wait)


def chat(text: str, wait: bool = False) -> bool:
    """Post to the Google Chat space. Returns whether it was accepted, when `wait`."""
    url = os.environ.get(CHAT_ENV) or ""
    if not url:
        log.info("chat not configured; skipped")
        return False

    def send() -> bool:
        status = _post(url, {"text": text[:4000]}, {})
        if status != 200:
            log.warning("the chat webhook answered %s", status)
            return False
        return True

    return _run(send, wait)


def _run(send, wait: bool) -> bool:
    if wait:
        return send()
    threading.Thread(target=send, daemon=True).start()
    return True


def configured() -> dict[str, bool]:
    return {
        "mail": all(os.environ.get(k) for k in (RESEND_KEY_ENV, MAIL_FROM_ENV, MAIL_TO_ENV)),
        "chat": bool(os.environ.get(CHAT_ENV)),
    }
