"""Everything that talks to YouTube."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from . import potoken
from .proc import run_child
from .timecode import format_timecode

log = logging.getLogger("wastatus")

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Artwork comes off the plain image CDN, which is not behind YouTube's bot check,
# so it never needs the proxy the media streams may need.
THUMB_URLS = (
    "https://i.ytimg.com/vi/{id}/maxresdefault.jpg",
    "https://i.ytimg.com/vi/{id}/sddefault.jpg",
    "https://i.ytimg.com/vi/{id}/hqdefault.jpg",
)

MEDIA_EXTS = {".m4a", ".webm", ".opus", ".mp3", ".ogg", ".aac", ".mp4", ".mkv", ".ts"}

SOCKET_TIMEOUT = 20.0   # per read, inside yt-dlp
RUN_TIMEOUT = 300.0     # for the whole yt-dlp process
# A probe asked for by hand is somebody sitting in front of a spinning icon, not a
# download running in the background: five minutes of spinner is indistinguishable
# from a tool that has died. A render still waits the full `RUN_TIMEOUT`, because
# there the wait has already been paid for. See DECISIONS.md D-064.
PROBE_TIMEOUT = 45.0

# Which player client exposes fetchable media varies by video, so both ladders
# below are tried in order until one produces a file. Format 18 is the muxed
# 360p progressive stream and carries 128 kbps AAC, which is all the card mode
# needs. The web_safari entries are the HLS renditions; 91 and 92 are omitted
# because their HE-AAC audio sounds poor on music.
#
# Both ladders lead with mweb/18 because, as of 2026-08-19, it is the only stream a
# section can be cut from at all:
#   * web_safari now returns storyboards and nothing else, so it fails on every
#     video-mode run. It stays at the end in case YouTube restores it, but leading
#     with it cost 4 to 9 seconds and a misleading "fell through" warning per run.
#   * the DASH renditions (136 at 720p, 137 at 1080p) do exist, but
#     `--download-sections` hands their URLs to ffmpeg, and googlevideo answers
#     ffmpeg with 403. Downloading a whole 70 MB stream to keep 15 seconds is worse
#     than 360p, so video mode is capped at 360p today. See LIMITATIONS.md.
STRATEGIES_AUDIO = (
    ("mweb", "18"),
    ("web_safari", "93/94/95"),
    ("android", "18"),
    ("tv_simply", "18"),
    ("default", "bestaudio/best"),
)
# Video mode leads with the HLS renditions, which carry their own audio and can be
# section downloaded: measured on 2026-08-20, a 5 second cut of format 95 arrived as
# 1280x720 h264 with aac, 1.79 MB, in 7.8 seconds. Not every video has them, and one
# that does not costs a failed attempt before `mweb` picks it up at 360p. DASH is
# still refused: googlevideo answers ffmpeg's range requests with 403, which is why
# no entry here asks for a merge. See DECISIONS.md D-023 and TASKS.md T-018.
STRATEGIES_VIDEO = (
    ("default", "95/96"),
    ("mweb", "18"),
    ("android", "18"),
    ("tv_simply", "18"),
    ("web_safari", "95/94/93"),
)


class FetchError(RuntimeError):
    pass


@dataclass
class Download:
    """A fetched media section, plus how it was obtained."""

    path: Path
    client: str
    fmt: str
    attempts: list[str] = field(default_factory=list)

    @property
    def bytes(self) -> int:
        return self.path.stat().st_size


@dataclass
class Source:
    video_id: str
    title: str
    channel: str
    duration: float
    watch_url: str
    artist: str = ""


def _ytdlp_base(*, client: str | None = None) -> list[str]:
    cmd = [
        sys.executable, "-m", "yt_dlp", "--no-playlist", "--no-warnings",
        # A dead socket otherwise sits there until yt-dlp's own patience runs out,
        # which is long enough that the page looks stuck rather than slow.
        "--socket-timeout", str(int(SOCKET_TIMEOUT)),
    ]
    if client:
        # Media fetches need the JS challenge solver, and most clients need a
        # matching PO token as well. See docs/extraction.md.
        cmd += ["--remote-components", "ejs:github"]
        if client != "default":
            cmd += ["--extractor-args", f"youtube:player_client={client}"]
        cmd += potoken.ytdlp_args()
    proxy = os.environ.get("WASTATUS_PROXY")
    if proxy:
        cmd += ["--proxy", proxy]
    cookies = os.environ.get("WASTATUS_COOKIES_FROM_BROWSER")
    if cookies:
        cmd += ["--cookies-from-browser", cookies]
    return cmd


def _shown(cmd: list[str]) -> str:
    """The command for the log, with the proxy's address masked: it can carry a
    user name and password."""
    shown = list(cmd)
    for index, part in enumerate(shown[:-1]):
        if part == "--proxy":
            shown[index + 1] = "***"
    return " ".join(shown)


def _run(cmd: list[str], timeout: float = RUN_TIMEOUT) -> str:
    log.debug("yt-dlp %s", _shown(cmd[2:]))
    try:
        proc = run_child(cmd, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        # Without this a wedged download is indistinguishable from a slow one: the
        # task never ends, the page polls forever, and nothing says why.
        log.error("yt-dlp did not finish within %.0fs", timeout)
        raise FetchError(
            f"yt-dlp gave up after {timeout:.0f}s. The connection may have dropped, "
            "or YouTube may be throttling this video. Try the same command again"
        ) from exc
    if proc.returncode != 0:
        output = (proc.stderr or proc.stdout).strip()
        # The whole output goes to the log; the user sees only the last lines.
        log.error("yt-dlp exit %s\n%s", proc.returncode, output)
        tail = output.splitlines()[-6:]
        raise FetchError("yt-dlp failed:\n  " + "\n  ".join(tail))
    return proc.stdout


def probe(url: str, *, timeout: float = RUN_TIMEOUT) -> Source:
    """What YouTube says about a video: no media is fetched.

    `timeout` is how long to wait for yt-dlp. The default suits a render, which is
    already a long job; an interactive caller passes `PROBE_TIMEOUT`.
    """
    # `--` ends the options: whatever the address says, yt-dlp reads it as one.
    raw = _run(_ytdlp_base() + ["-J", "--skip-download", "--", url], timeout=timeout)
    info = json.loads(raw)
    _refuse_a_playlist(info)
    video_id = info.get("id") or ""
    return Source(
        video_id=video_id,
        title=info.get("title") or "Untitled",
        channel=info.get("uploader") or info.get("channel") or "",
        duration=float(info.get("duration") or 0.0),
        watch_url=f"https://youtu.be/{video_id}",
        artist=_artist(info),
    )


def _refuse_a_playlist(info: dict) -> None:
    """Stop a playlist link here, where it can still be explained.

    `--no-playlist` already reduces `watch?v=X&list=Y` to the single video X, so the
    only way to arrive here with a playlist is to paste one deliberately. Nothing
    used to catch it, and the result was worse than an error: `id` came back as the
    playlist's id, so `watch_url` became `https://youtu.be/PL...`, which resolves to
    nothing, and that url is the caption. A pasted playlist put a dead link on a real
    Status. Measured 2026-08-21, TASKS.md T-027.

    Taking the first entry was considered and rejected. Which track somebody meant is
    a guess, and this tool does not guess at what it is about to publish.
    """
    if info.get("_type") != "playlist" and "entries" not in info:
        return
    name = (info.get("title") or "").strip()
    named = f", {name!r}" if name else ""
    count = len(info.get("entries") or [])
    holds = f" It holds {count} tracks." if count else ""
    raise FetchError(
        f"that link is a playlist{named}, not one track.{holds} Open the song you "
        f"want and paste its own link: on YouTube Music, use Share on the track "
        f"rather than on the playlist."
    )


def _artist(info: dict) -> str:
    """The performer, when YouTube knows one.

    An auto-generated music upload has a channel like `Release - Topic`, which
    says nothing, while its `artist` field carries the real name. Music apps show
    the artist, so the card does too, and falls back to the channel.
    """
    artists = info.get("artists") or []
    return (
        info.get("artist")
        or (artists[0] if artists else "")
        or info.get("creator")
        or ""
    ).strip()


def download_section(
    url: str, start: float, end: float, workdir: Path, *, video: bool
) -> Download:
    """Fetch only the requested range. Audio only unless video is asked for."""
    workdir.mkdir(parents=True, exist_ok=True)
    if not potoken.ensure_running():
        raise FetchError(potoken.install_hint())

    section = f"*{format_timecode(start)}-{format_timecode(end)}"
    strategies = STRATEGIES_VIDEO if video else STRATEGIES_AUDIO
    failures: list[str] = []

    for client, fmt in strategies:
        attempt = workdir / client
        attempt.mkdir(parents=True, exist_ok=True)
        cmd = _ytdlp_base(client=client) + [
            "-f", fmt,
            "--download-sections", section,
            "--output", str(attempt / "clip.%(ext)s"),
            "--", url,
        ]
        try:
            _run(cmd)
        except FetchError as exc:
            failures.append(f"{client}: {str(exc).splitlines()[-1].strip()}")
            continue
        produced = [p for p in sorted(attempt.iterdir()) if p.suffix.lower() in MEDIA_EXTS]
        if produced:
            winner = max(produced, key=lambda p: p.stat().st_size)
            if failures:
                # A late win means earlier entries have stopped working. Worth
                # noticing before the ladder runs out entirely.
                log.warning(
                    "fell through to %s/%s after %d failed attempt(s)",
                    client, fmt, len(failures),
                )
            log.info("fetched via %s/%s, %d bytes", client, fmt, winner.stat().st_size)
            return Download(winner, client, fmt, failures)
        failures.append(f"{client}: produced no media")

    raise FetchError(
        "no player client could deliver this video:\n  " + "\n  ".join(failures)
    )


def download_thumbnail(video_id: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for template in THUMB_URLS:
        request = urllib.request.Request(
            template.format(id=video_id), headers={"User-Agent": UA}
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
        except Exception as exc:  # noqa: BLE001 - any failure just moves to the next size
            last_error = exc
            continue
        # YouTube answers missing sizes with a tiny grey placeholder.
        if len(data) > 3000:
            dest.write_bytes(data)
            name = template.rsplit("/", 1)[-1]
            log.info("artwork %s, %d bytes", name, len(data))
            if name.startswith("hqdefault"):
                log.warning(
                    "only hqdefault artwork available (480x360), the card will "
                    "look soft; consider --video for this one"
                )
            return dest
    raise FetchError(f"no artwork available for {video_id} ({last_error})")
