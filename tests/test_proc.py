"""Stopping the children the pipeline waits on.

Real processes, not mocks: the whole point of this module is what a signal does to
a process group, and a mock cannot be wrong about that in the same way.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from wastatus import proc


def sleeper(marker: Path, seconds: int = 30) -> list[str]:
    """A child that says when it has started, then waits to be killed."""
    return [
        sys.executable, "-c",
        f"import pathlib, time; pathlib.Path({str(marker)!r}).write_text('x');"
        f" time.sleep({seconds})",
    ]


def wait_for(path: Path, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise AssertionError(f"{path} never appeared")


class TestRunningOne:
    def test_a_child_that_finishes_comes_back_like_subprocess_run(self):
        with proc.cancellable():
            done = proc.run_child([sys.executable, "-c", "print('hello')"])
        assert done.returncode == 0
        assert done.stdout.strip() == "hello"

    def test_a_failing_child_brings_its_output_with_it(self):
        with proc.cancellable():
            done = proc.run_child([
                sys.executable, "-c",
                "import sys; sys.stderr.write('nope'); sys.exit(3)",
            ])
        assert done.returncode == 3
        assert "nope" in done.stderr

    def test_a_timeout_still_raises_what_callers_already_catch(self, tmp_path):
        """`fetch._run` turns this into its own message, so it has to stay this."""
        with proc.cancellable():
            with pytest.raises(subprocess.TimeoutExpired):
                proc.run_child(sleeper(tmp_path / "started"), timeout=0.3)


class TestCancelling:
    def test_cancelling_kills_the_child_and_raises_on_its_thread(self, tmp_path):
        marker = tmp_path / "started"
        outcome: dict = {}
        ident: dict = {}
        ready = threading.Event()

        def work() -> None:
            with proc.cancellable() as mine:
                ident["id"] = mine
                ready.set()
                try:
                    proc.run_child(sleeper(marker))
                except proc.Cancelled:
                    outcome["cancelled"] = True

        thread = threading.Thread(target=work)
        thread.start()
        ready.wait(5)
        wait_for(marker)

        assert proc.cancel(ident["id"]) is True
        thread.join(10)
        assert not thread.is_alive(), "the child outlived the cancel"
        assert outcome == {"cancelled": True}

    def test_the_kill_reaches_a_grandchild(self, tmp_path):
        """yt-dlp runs an ffmpeg of its own. Killing only yt-dlp leaves that one
        encoding, which is the reason children get their own process group."""
        alive = tmp_path / "alive"
        grandchild = tmp_path / "grandchild.py"
        grandchild.write_text(
            "import pathlib, time\n"
            f"p = pathlib.Path({str(alive)!r})\n"
            "while True:\n"
            "    with p.open('a') as handle:\n"
            "        handle.write('x')\n"
            "    time.sleep(0.05)\n"
        )
        parent = [
            sys.executable, "-c",
            f"import subprocess, sys, time;"
            f" subprocess.Popen([sys.executable, {str(grandchild)!r}]);"
            f" time.sleep(30)",
        ]
        ident: dict = {}
        ready = threading.Event()

        def work() -> None:
            with proc.cancellable() as mine:
                ident["id"] = mine
                ready.set()
                with pytest.raises(proc.Cancelled):
                    proc.run_child(parent)

        thread = threading.Thread(target=work)
        thread.start()
        ready.wait(5)
        wait_for(alive)

        proc.cancel(ident["id"])
        thread.join(10)
        time.sleep(0.3)
        settled = alive.stat().st_size
        time.sleep(0.5)
        assert alive.stat().st_size == settled, "the grandchild is still running"

    def test_a_cancelled_thread_will_not_start_another_child(self, tmp_path):
        """Killing one ffmpeg is not enough when the pipeline would simply walk on
        to the next stage."""
        with proc.cancellable() as mine:
            proc.cancel(mine)
            with pytest.raises(proc.Cancelled):
                proc.run_child([sys.executable, "-c", "print('should not run')"])

    def test_cancelling_nothing_says_so(self):
        with proc.cancellable() as mine:
            assert proc.cancel(mine) is False   # no child was running
            assert proc.is_cancelled(mine)

    def test_the_flag_does_not_survive_into_the_next_piece_of_work(self):
        """Thread ids are reused, so a stale flag would refuse an innocent run."""
        with proc.cancellable() as mine:
            proc.cancel(mine)
        assert not proc.is_cancelled(mine)
        with proc.cancellable():
            done = proc.run_child([sys.executable, "-c", "print('again')"])
        assert done.stdout.strip() == "again"

    def test_nothing_is_left_registered_afterwards(self):
        with proc.cancellable() as mine:
            proc.run_child([sys.executable, "-c", "pass"])
        assert mine not in proc._children
        assert mine not in proc._cancelled
