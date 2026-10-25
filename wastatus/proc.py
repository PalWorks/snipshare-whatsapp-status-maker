"""Running the slow children, so a render can be abandoned.

yt-dlp and ffmpeg do all the waiting in this tool, and `subprocess.run` hands back
no handle to them. That is why a render could not be stopped: a wrong paste cost
two minutes whether you wanted the clip or not.

**The thread is the handle.** Every render already runs on its own thread, so
`run_child` registers its child against the calling thread while it waits, and
`cancel` kills that thread's current child. It also marks the thread cancelled, so
the next `run_child` on it refuses to start: killing one ffmpeg is not enough when
the pipeline would simply walk on to the next stage.

Children are started in their own process group, because yt-dlp runs an ffmpeg of
its own and a signal sent to yt-dlp alone leaves that one running.

`SIGKILL` rather than a polite `SIGTERM` and a grace period: everything these
children write goes into a temporary work directory that is deleted afterwards, so
there is nothing worth letting them finish, and the person is waiting.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
from contextlib import contextmanager
from typing import Iterator

log = logging.getLogger("wastatus")


class Cancelled(Exception):
    """Raised on the working thread once its work has been cancelled."""


_lock = threading.Lock()
_children: dict[int, subprocess.Popen] = {}
_cancelled: set[int] = set()


@contextmanager
def cancellable() -> Iterator[int]:
    """Mark the calling thread as something `cancel` may stop.

    Yields the thread id to hand to `cancel`. Clears any flag left by an earlier
    piece of work, because thread ids are reused.
    """
    ident = threading.get_ident()
    with _lock:
        _cancelled.discard(ident)
        _children.pop(ident, None)
    try:
        yield ident
    finally:
        with _lock:
            _cancelled.discard(ident)
            _children.pop(ident, None)


def cancel(ident: int) -> bool:
    """Stop that thread's work. True if there was a child to kill."""
    with _lock:
        _cancelled.add(ident)
        child = _children.get(ident)
    if child is None:
        return False
    _kill(child)
    return True


def is_cancelled(ident: int | None = None) -> bool:
    with _lock:
        return (ident if ident is not None else threading.get_ident()) in _cancelled


def _kill(child: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(child.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError, AttributeError):
        # Already gone, or a platform without process groups.
        try:
            child.kill()
        except OSError:  # pragma: no cover - it exited between the two calls
            pass


def run_child(
    cmd: list[str], timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    """`subprocess.run`, except that `cancel` can end it.

    Raises `Cancelled` if the work was cancelled before or during the call, and
    `subprocess.TimeoutExpired` on a timeout, so callers keep the handling they
    already have.
    """
    ident = threading.get_ident()
    with _lock:
        if ident in _cancelled:
            raise Cancelled("cancelled before this step started")

    child = subprocess.Popen(  # noqa: S603 - every argv here is built by us
        cmd,
        # Never the server's own stdin: ffmpeg reads keys from a terminal, so a
        # stray `q` would end an encode, and a backgrounded server would be stopped.
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    with _lock:
        _children[ident] = child
        # Cancelled between the check above and the start: kill it now, because
        # `cancel` looked for a child and found none.
        doomed = ident in _cancelled
    if doomed:
        _kill(child)

    try:
        out, err = child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill(child)
        child.communicate()
        raise
    finally:
        with _lock:
            if _children.get(ident) is child:
                del _children[ident]

    if is_cancelled(ident):
        log.info("child %s was cancelled", os.path.basename(cmd[0]) if cmd else "?")
        raise Cancelled("cancelled")
    return subprocess.CompletedProcess(cmd, child.returncode, out, err)
