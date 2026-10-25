"""Records a published Status as one row in a Google Sheet.

Append only, and only for a Status WhatsApp actually accepted. A refused one gets
no row on purpose: the sheet is the record of what went out, and `post.send_with_retry`
is what deals with what did not. See DECISIONS.md D-073.

**Nothing in here may break a posting run.** A sheet that cannot be reached is a
lost row, not a lost Status, so every failure is caught, logged, and swallowed.
That is the same rule `runlog` follows, and it is in AGENTS.md.

Set up in `.env`:

    WASTATUS_SHEET_ID=<the long string in your sheet URL, between /d/ and /edit>
    WASTATUS_SHEET_KEY=~/.config/wastatus/sheets-sa.json
    WASTATUS_SHEET_TAB=Sheet1

With no `WASTATUS_SHEET_ID` the whole module is inert and says nothing, because
most people running this will never point it at a sheet.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger("wastatus")

SCOPE = "https://www.googleapis.com/auth/spreadsheets"
API = "https://sheets.googleapis.com/v4/spreadsheets"
TIMEOUT = 20.0

ID_ENV = "WASTATUS_SHEET_ID"
KEY_ENV = "WASTATUS_SHEET_KEY"
TAB_ENV = "WASTATUS_SHEET_TAB"
DEFAULT_TAB = "Sheet1"

# One credential per process. Minting an access token costs a round trip and a
# signature, and a posting run would otherwise pay both on every row.
_lock = threading.Lock()
_credentials = None


def configured() -> bool:
    """Is a sheet set up on this machine? Everything else here checks this first."""
    return bool(os.environ.get(ID_ENV) and os.environ.get(KEY_ENV))


def _key_path() -> Path:
    return Path(os.environ[KEY_ENV]).expanduser()


def _token() -> str:
    """A bearer token for the service account, minted once and refreshed as needed."""
    global _credentials
    with _lock:
        if _credentials is None:
            from google.oauth2 import service_account  # imported late: optional dep

            _credentials = service_account.Credentials.from_service_account_file(
                str(_key_path()), scopes=[SCOPE]
            )
        if not _credentials.valid:
            from google.auth.transport.requests import Request

            _credentials.refresh(Request())
        return _credentials.token


def account() -> str | None:
    """The service account's own address, which is who the sheet must be shared with.

    Read out of the key file rather than typed into a setting, because the two
    would then have to agree and one of them would eventually be wrong.
    """
    try:
        return json.loads(_key_path().read_text(encoding="utf-8"))["client_email"]
    except (OSError, ValueError, KeyError):
        return None


def append(row: list[str]) -> bool:
    """Put one row at the bottom of the sheet. True if it landed.

    `USER_ENTERED` so a timestamp is a date to the sheet rather than a string, and
    `INSERT_ROWS` so an append never overwrites whatever is below the last row.
    """
    if not configured():
        return False
    tab = os.environ.get(TAB_ENV) or DEFAULT_TAB
    where = urllib.parse.quote(f"{tab}!A:D", safe="")
    url = (
        f"{API}/{os.environ[ID_ENV]}/values/{where}:append"
        "?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS"
    )
    body = json.dumps({"values": [row]}).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
        return 200 <= answer.status < 300


def _from_sidecar(clip: Path | None) -> dict:
    """What `pipeline.produce` wrote beside the clip: the URL, the title, the window.

    Read here rather than passed in, so the CLI and the page put the same thing in
    the Source column. They hold different objects and would otherwise each reach
    for the nearest URL to hand, which is how one sheet ends up with two forms of
    the same link.
    """
    if clip is None:
        return {}
    try:
        job = json.loads(clip.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return job if isinstance(job, dict) else {}


def record(*, url: str = "", title: str = "", stem: str = "", seconds: float | None = None,
           browser: str = "", duration: float | None = None,
           size_bytes: int | None = None, clip: Path | None = None,
           note: str = "", when: datetime.datetime | None = None) -> bool:
    """Write the row for one published Status. Never raises.

    The four columns are the sheet's own: Timestamp, Source, Status, Remarks.
    Status is always `Published` here, because this is only ever called for a
    Status WhatsApp accepted: a refusal gets no row, D-074.

    Anything not passed is taken from the clip's sidecar, so a caller only has to
    supply what it knows better than the file does.
    """
    try:
        return _record(url=url, title=title, stem=stem, seconds=seconds, browser=browser,
                       duration=duration, size_bytes=size_bytes, clip=clip, note=note,
                       when=when)
    except Exception as exc:  # noqa: BLE001 - a lost row must never lose a Status
        log.warning("the row could not be put together for the sheet: %s", exc)
        return False


def _record(*, url: str, title: str, stem: str, seconds: float | None, browser: str,
            duration: float | None, size_bytes: int | None, clip: Path | None,
            note: str, when: datetime.datetime | None) -> bool:
    if not configured():
        return False
    job = _from_sidecar(clip)
    url = url or job.get("url", "")
    title = title or job.get("title", "")
    stem = stem or (clip.stem if clip else "")
    if duration is None and job.get("end") is not None and job.get("start") is not None:
        duration = job["end"] - job["start"]
    if size_bytes is None and clip is not None and clip.is_file():
        size_bytes = clip.stat().st_size
    stamp = (when or datetime.datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    remarks = " · ".join(part for part in (
        note,
        title,
        f"{duration:.0f}s" if duration else "",
        f"{size_bytes / 1_000_000:.1f} MB" if size_bytes else "",
        browser,
        f"accepted in {seconds:.0f}s" if seconds else "",
        stem,
    ) if part)
    try:
        landed = append([stamp, url, "Published", remarks])
    except ImportError:
        log.warning("the sheet needs google-auth: .venv/bin/pip install google-auth")
        return False
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001 - a body we cannot read is not the point
            pass
        if exc.code in (401, 403):
            log.warning(
                "the sheet refused this service account (%s). Share the sheet with "
                "%s as an Editor, and check the Sheets API is enabled. %s",
                exc.code, account() or "the address in the key file", detail,
            )
        else:
            log.warning("the sheet would not take the row (%s): %s", exc.code, detail)
        return False
    except Exception as exc:  # noqa: BLE001 - a lost row must never lose a Status
        log.warning("the row could not be written to the sheet: %s", exc)
        return False
    if landed:
        log.info("recorded in the sheet: %s", stamp)
    return landed
