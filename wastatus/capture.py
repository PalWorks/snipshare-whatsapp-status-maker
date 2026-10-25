"""Media captured in the viewer's browser: check it, and cut out the window.

The browser extension uploads what YouTube's own player fetched, as one audio
stream and, in video mode, one video stream, each still carrying YouTube's own
timestamps: a window starting at 1:30 is at 90 seconds in the file, not at zero.
This module is what stands between those uploads and the engine. It reads them
packet by packet without decoding anything, refuses what is not what it claims to
be or does not cover the window, and cuts the window out on those timestamps.

**How it cuts is the point of the module.** Measured on a beep-and-flash test video
in October 2026: seeking the two inputs separately with `-ss` put the sound 59ms
early, and letting ffmpeg shift each input by its own start time put it 33ms early
again, because the audio and the video files start at different moments. `trim` and
`atrim` on the original timestamps, with `-copyts`, land within half a millisecond.
See DECISIONS.md D-080 and docs/extension.md.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .proc import run_child

log = logging.getLogger("wastatus")

# What YouTube's player appends today, and nothing else. A file that claims to be a
# capture and holds something else did not come from the extension.
VIDEO_CODECS = frozenset({"vp9", "av1", "h264"})
AUDIO_CODECS = frozenset({"opus", "aac"})

# The window may start a hair before the first packet: the walk stops at the first
# fragment that covers the start, and a fragment's first packet is its own start.
START_SLACK = 0.1
# And end a little after the last one: a window that runs to the very end of a
# video ends where the video does, and the last packet's own length is an estimate.
END_SLACK = 0.5
# A hole longer than this inside the window is a missing fragment, not jitter.
MAX_GAP = 0.5

# The widest the engine ever draws a video picture: the frame itself.
SECTION_MAX_WIDTH = 1080

PROBE_TIMEOUT = 60
CUT_TIMEOUT = 300


class CaptureError(RuntimeError):
    """An upload that cannot be made into the section that was asked for."""


@dataclass(frozen=True)
class Stream:
    """One uploaded stream, as its own packets describe it."""

    path: Path
    kind: str     # "audio" or "video"
    codec: str
    start: float  # first packet's timestamp, in seconds
    end: float    # last packet's timestamp plus its length
    gaps: tuple[tuple[float, float], ...]  # holes longer than MAX_GAP


def _tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise CaptureError(f"{name} not found on PATH")
    return found


# Uploads are read as local files of the two containers YouTube's player sends, and
# nothing else: without these ffmpeg guesses the format from the content, and a
# playlist format can make it open other files or addresses.
INPUT_GUARD = ("-protocol_whitelist", "file",
               "-format_whitelist", "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm")


def ffprobe_bin() -> str:
    return _tool("ffprobe")


def _probe_json(cmd: list[str]) -> dict:
    try:
        proc = run_child(cmd, timeout=PROBE_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise CaptureError("reading the upload took too long") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-3:]
        raise CaptureError("the upload is not a media file ffprobe can read: "
                           + " / ".join(tail))
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise CaptureError("ffprobe gave an answer that is not JSON") from exc


def probe(path: Path, kind: str) -> Stream:
    """Describe an uploaded stream, refusing anything that is not one `kind` stream.

    Packets, not frames: nothing is decoded, so this is quick on a 25 MB upload and
    cannot be slowed down by a file built to be expensive to decode.
    """
    if kind not in ("audio", "video"):
        raise ValueError(f"unknown stream kind {kind!r}")
    allowed = AUDIO_CODECS if kind == "audio" else VIDEO_CODECS
    info = _probe_json([
        ffprobe_bin(), "-v", "error", *INPUT_GUARD, "-of", "json",
        "-show_entries", "stream=index,codec_type,codec_name", str(path),
    ])
    streams = info.get("streams") or []
    if len(streams) != 1 or streams[0].get("codec_type") != kind:
        found = ", ".join(s.get("codec_type", "?") for s in streams) or "nothing"
        raise CaptureError(f"the {kind} upload should hold one {kind} stream, "
                           f"and holds {found}")
    codec = streams[0].get("codec_name", "")
    if codec not in allowed:
        raise CaptureError(f"the {kind} upload is {codec or 'an unknown codec'}, "
                           f"which YouTube's player does not send")

    packets = _probe_json([
        ffprobe_bin(), "-v", "error", *INPUT_GUARD, "-of", "json", "-select_streams", "0",
        "-show_entries", "packet=pts_time,duration_time", str(path),
    ]).get("packets") or []
    spans: list[tuple[float, float]] = []
    for packet in packets:
        try:
            at = float(packet["pts_time"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            length = float(packet.get("duration_time") or 0.0)
        except (TypeError, ValueError):
            length = 0.0
        spans.append((at, at + max(0.0, length)))
    if not spans:
        raise CaptureError(f"the {kind} upload has no timed packets in it")
    # Sorted by presentation time, because video packets arrive in decode order.
    spans.sort()
    gaps: list[tuple[float, float]] = []
    reach = spans[0][1]
    for at, until in spans[1:]:
        if at - reach > MAX_GAP:
            gaps.append((reach, at))
        reach = max(reach, until)
    return Stream(path=path, kind=kind, codec=codec, start=spans[0][0], end=reach,
                  gaps=tuple(gaps))


def check_covers(stream: Stream, start: float, end: float) -> None:
    """Refuse a stream that does not hold the whole window, saying what it holds."""
    if stream.start > start + START_SLACK or stream.end < end - END_SLACK:
        raise CaptureError(
            f"the captured {stream.kind} runs from {stream.start:.2f}s to "
            f"{stream.end:.2f}s, and the clip needs {start:.2f}s to {end:.2f}s"
        )
    for hole_start, hole_end in stream.gaps:
        if hole_end > start and hole_start < end:
            raise CaptureError(
                f"the captured {stream.kind} is missing {hole_start:.2f}s to "
                f"{hole_end:.2f}s, inside the clip"
            )


def section(audio: Path, video: Path | None, start: float, end: float,
            dest: Path) -> Path:
    """Cut the window out of the uploads, as the engine's source for this clip.

    The result starts at zero, like a section yt-dlp downloads, so the engine cannot
    tell the two apart. Matroska with FLAC audio: the engine re-encodes everything
    anyway, and FLAC adds no encoder delay, where an AAC intermediate would shift the
    sound by its priming samples before the real encode shifted it again.
    """
    if end <= start:
        raise CaptureError("the end of the window has to come after its start")
    streams = [probe(audio, "audio")]
    if video is not None:
        streams.insert(0, probe(video, "video"))
    for stream in streams:
        check_covers(stream, start, end)

    graph = []
    cmd = [_tool("ffmpeg"), "-y", "-hide_banner", "-loglevel", "error", "-copyts"]
    maps: list[str] = []
    for index, stream in enumerate(streams):
        cmd += [*INPUT_GUARD, "-i", str(stream.path)]
        if stream.kind == "video":
            # No wider than the frame the engine draws it into. A 1920 wide source
            # is drawn 1080 wide at most, so the pixels past that cost two decodes
            # and an encode and never reach the clip: on the production host they
            # made a 90 second cut take 52 seconds. Portrait sources are already
            # narrower and pass through untouched.
            graph.append(f"[{index}:v]trim=start={start:.6f}:end={end:.6f},"
                         f"setpts=PTS-STARTPTS,"
                         f"scale='min(iw,{SECTION_MAX_WIDTH})':-2:flags=lanczos[v]")
            maps += ["-map", "[v]"]
        else:
            graph.append(f"[{index}:a]atrim=start={start:.6f}:end={end:.6f},"
                         f"asetpts=PTS-STARTPTS[a]")
            maps += ["-map", "[a]"]
    cmd += ["-filter_complex", ";".join(graph), *maps]
    if video is not None:
        # Every frame keeps its own time. Without this ffmpeg pads or drops to a
        # constant rate it guessed from the container, which moved a 60 fps source's
        # frames by up to two of them.
        cmd += ["-fps_mode", "passthrough",
                # An intermediate, read once by the engine and deleted: speed over
                # size, and a quality setting the final encode cannot tell apart.
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "14",
                "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "flac", "-f", "matroska", str(dest)]

    dest.parent.mkdir(parents=True, exist_ok=True)
    log.debug("ffmpeg %s", " ".join(cmd[1:]))
    try:
        proc = run_child(cmd, timeout=CUT_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise CaptureError("cutting the window out of the upload took too long") from exc
    if proc.returncode != 0:
        output = (proc.stderr or proc.stdout or "").strip()
        log.error("ffmpeg exit %s\n%s", proc.returncode, output)
        raise CaptureError("ffmpeg could not cut the window: "
                           + " / ".join(output.splitlines()[-3:]))
    log.info("cut %.2fs to %.2fs out of the upload (%s)", start, end,
             " + ".join(f"{s.kind} {s.codec}" for s in streams))
    return dest
