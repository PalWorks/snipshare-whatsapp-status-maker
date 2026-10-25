"""Proof of origin token provider.

YouTube now requires a PO token for the clients that still expose fetchable
media URLs. yt-dlp gets that token from a local bgutil provider over HTTP. This
module finds the provider, starts it on demand, and shuts it down with us.
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PORT = 4416  # where the bgutil plugin looks unless yt-dlp is told otherwise
PORT = int(os.environ.get("WASTATUS_POT_PORT", str(DEFAULT_PORT)))
BASE_URL = f"http://127.0.0.1:{PORT}"
STARTUP_TIMEOUT = 25.0

_started: subprocess.Popen | None = None
# Two renders starting together must not both find the provider down and both
# start one: the second cannot bind, and the first is left running unowned.
_lock = threading.Lock()


def install_dir() -> Path:
    override = os.environ.get("WASTATUS_POT_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":  # pragma: no cover - not a target platform
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif os.uname().sysname == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "wastatus" / "bgutil"


def is_up(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/ping", timeout=timeout):
            return True
    except (urllib.error.URLError, OSError):
        return False


def ensure_running() -> bool:
    """Return True when a provider is reachable, starting one if needed."""
    with _lock:
        return _ensure_running()


def _ensure_running() -> bool:
    global _started

    if is_up():
        return True

    entry = install_dir() / "server" / "build" / "main.js"
    if not entry.exists():
        return False
    node = shutil.which("node")
    if not node:
        return False

    _started = subprocess.Popen(
        [node, str(entry), "--port", str(PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    atexit.register(stop)

    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        if is_up(timeout=1.0):
            return True
        if _started.poll() is not None:
            return False
        time.sleep(0.5)
    stop()
    return False


def stop() -> None:
    global _started
    if _started and _started.poll() is None:
        _started.terminate()
        try:
            _started.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            _started.kill()
    _started = None


def install_hint() -> str:
    return (
        "PO token provider missing. Install it once with:\n"
        "  bash scripts/setup_provider.sh\n"
        "It needs node 20 or newer on PATH."
    )


def ytdlp_args() -> list[str]:
    """What yt-dlp needs told to find this provider: nothing on the plugin's own
    port, its address on any other."""
    if PORT == DEFAULT_PORT:
        return []
    return ["--extractor-args", f"youtubepot-bgutilhttp:base_url={BASE_URL}"]
