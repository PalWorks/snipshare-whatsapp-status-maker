"""Run logging.

Two outputs, because they answer different questions:

- `logs/wastatus.log`, rotating text, is what you read when something broke. It
  carries the full yt-dlp and ffmpeg failure output, which is otherwise lost.
- `logs/runs.jsonl`, one object per run, is what you grep when you want to know
  which extraction strategy has been working lately, or when a clip was made.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

LOG_NAME = "wastatus"
TEXT_LOG = "wastatus.log"
JSON_LOG = "runs.jsonl"
MAX_BYTES = 2_000_000
BACKUPS = 3

_configured = False


def log_dir() -> Path:
    override = os.environ.get("WASTATUS_LOG_DIR")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parent.parent / "logs"


def setup(verbose: bool = False) -> logging.Logger:
    """Attach handlers once per process."""
    global _configured
    logger = logging.getLogger(LOG_NAME)
    if _configured:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    directory = log_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            directory / TEXT_LOG, maxBytes=MAX_BYTES, backupCount=BACKUPS,
            encoding="utf-8",
        )
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S"
            )
        )
        logger.addHandler(handler)
    except OSError:
        # An unwritable log directory must never stop a clip being made.
        pass

    if verbose:
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)
        console.setFormatter(logging.Formatter("      %(message)s"))
        logger.addHandler(console)

    _configured = True
    return logger


class Run:
    """Collects one run's facts and appends them to the jsonl log on close."""

    def __init__(self, logger: logging.Logger, **fields: Any) -> None:
        self.log = logger
        self.fields: dict[str, Any] = {
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **fields,
        }
        self.stages: dict[str, float] = {}
        self._t0 = time.monotonic()
        self.log.info("run start %s", json.dumps(fields, default=str))

    def set(self, **fields: Any) -> None:
        self.fields.update(fields)

    @contextmanager
    def stage(self, name: str):
        start = time.monotonic()
        self.log.debug("stage %s start", name)
        try:
            yield
        finally:
            elapsed = round(time.monotonic() - start, 3)
            self.stages[name] = elapsed
            self.log.debug("stage %s done in %.3fs", name, elapsed)

    def finish(self, status: str, **fields: Any) -> None:
        self.fields.update(fields)
        self.fields["status"] = status
        self.fields["stages"] = self.stages
        self.fields["elapsed"] = round(time.monotonic() - self._t0, 3)
        self.log.info("run %s in %.1fs", status, self.fields["elapsed"])
        self._append()

    def _append(self) -> None:
        try:
            directory = log_dir()
            directory.mkdir(parents=True, exist_ok=True)
            with (directory / JSON_LOG).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(self.fields, default=str) + "\n")
        except OSError as exc:
            self.log.warning("could not write run record: %s", exc)


def _version(cmd: list[str], keep: int = 1) -> str:
    """The first line of something's `--version`, or "" if it is not installed."""
    try:
        found = subprocess.run(cmd, capture_output=True, text=True, timeout=6)
    except (OSError, subprocess.SubprocessError):
        return ""
    line = (found.stdout or found.stderr or "").strip().splitlines()
    return " ".join(line[0].split()[:keep + 2]) if line else ""


def stamp(logger: logging.Logger) -> None:
    """Write one block about this machine at the top of every session.

    "It broke" is not a report. Six months from now the useful question about a
    line in this log is which yt-dlp wrote it, on which ffmpeg, against which
    Chrome, and none of that is recoverable afterwards. It costs two subprocess
    calls once per start.

    **Settings are named, never quoted.** `env.TAKEN` holds the names `.env`
    supplied and nothing else, so a key cannot reach this file by accident.
    """
    from . import env, post  # here, to keep this module importable on its own

    logger.info("=" * 60)
    logger.info(
        "wastatus starting: python %s on %s",
        sys.version.split()[0], platform.platform(),
    )
    logger.info("  yt-dlp   %s", _version([sys.executable, "-m", "yt_dlp", "--version"]) or "missing")
    logger.info("  ffmpeg   %s", _version(["ffmpeg", "-version"]) or "missing")
    chrome = post.chrome_binary()
    logger.info("  chrome   %s", _version([chrome, "--version"]) if chrome else "missing")
    logger.info("  ports    %s", ", ".join(str(p) for p in post.candidate_ports()))
    logger.info("  revision %s", _revision() or "not a git checkout")
    logger.info(
        "  settings %s", ", ".join(env.TAKEN) if env.TAKEN else "none from .env"
    )


def _revision() -> str:
    """The commit this is running from, so a log line can be placed in history."""
    root = Path(__file__).resolve().parent.parent
    try:
        found = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=6,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    revision = (found.stdout or "").strip()
    if not revision:
        return ""
    dirty = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True, text=True, timeout=6,
    )
    return revision + (" (modified)" if (dirty.stdout or "").strip() else "")
