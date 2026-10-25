"""Timestamp parsing and formatting."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

_TIME_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)$")
_PLAIN_RE = re.compile(r"^\d+(?:\.\d+)?$")
_YT_T_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s?)?$")


class TimecodeError(ValueError):
    pass


def parse_timecode(value: str) -> float:
    """Accept 93, 1:33, 01:33, 1:02:03, 90.5 and return seconds."""
    value = value.strip()
    if _PLAIN_RE.match(value):
        return float(value)
    m = _TIME_RE.match(value)
    if not m:
        raise TimecodeError(f"cannot parse timestamp {value!r}, try 1:33 or 93")
    hours, minutes, seconds = m.groups()
    total = int(hours or 0) * 3600 + int(minutes) * 60 + float(seconds)
    return total


def format_timecode(seconds: float) -> str:
    """Render seconds as the H:MM:SS.mmm form ffmpeg and yt-dlp both accept."""
    hours, rest = divmod(max(0.0, seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours):d}:{int(minutes):02d}:{secs:06.3f}"


def start_from_url(url: str) -> float | None:
    """Pull a start offset out of a ?t= or #t= parameter if one is present."""
    parsed = urlparse(url)
    for source in (parsed.query, parsed.fragment):
        if not source:
            continue
        raw = parse_qs(source).get("t", [None])[0]
        if not raw:
            continue
        if _PLAIN_RE.match(raw):
            return float(raw)
        m = _YT_T_RE.match(raw)
        if m and any(m.groups()):
            hours, minutes, seconds = m.groups()
            return int(hours or 0) * 3600 + int(minutes or 0) * 60 + int(seconds or 0)
    return None
