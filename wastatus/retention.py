"""Keeps the output folder from growing without bound.

A run produces one mp4 plus its sidecar text files. Those are treated as a group
so pruning never leaves an orphaned caption behind.
"""

from __future__ import annotations

import contextlib
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

DEFAULT_KEEP = 20
# `.base.png` and `.art.jpg` are what the live word preview draws over, T-036.
# They belong to the clip and go when it goes, or the folder fills with backgrounds
# for clips that no longer exist.
SIDECAR_SUFFIXES = (
    ".caption.txt", ".status2.txt", ".json", ".png", ".base.png", ".art.jpg",
)


@dataclass
class Pruned:
    groups: int
    files: int
    bytes: int

    def __bool__(self) -> bool:
        return self.groups > 0


# Clips something is using right now, such as a post uploading one: a prune skips
# them, however old they are, so a clip never vanishes from under its upload.
_held: Counter[Path] = Counter()
_held_lock = threading.Lock()


@contextlib.contextmanager
def hold(clip: Path):
    """Keep `clip` and its sidecars out of every prune for the length of the block."""
    key = clip.resolve()
    with _held_lock:
        _held[key] += 1
    try:
        yield
    finally:
        with _held_lock:
            _held[key] -= 1
            if _held[key] <= 0:
                del _held[key]


def mtime(path: Path) -> float:
    """When a file last changed, or 0 for one deleted since it was listed: two
    prunes, or a prune and a delete, may run at once."""
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def group_files(out_dir: Path, stem: str) -> list[Path]:
    """The mp4 and every sidecar that belongs with it."""
    found = [out_dir / f"{stem}.mp4"]
    found += [out_dir / f"{stem}{suffix}" for suffix in SIDECAR_SUFFIXES]
    return [path for path in found if path.exists()]


def prune(out_dir: Path, keep: int = DEFAULT_KEEP) -> Pruned:
    """Delete all but the newest `keep` clips. keep=0 disables pruning."""
    if keep <= 0 or not out_dir.is_dir():
        return Pruned(0, 0, 0)

    clips = sorted(out_dir.glob("*.mp4"), key=mtime, reverse=True)
    doomed = clips[keep:]

    groups = files = freed = 0
    for clip in doomed:
        with _held_lock:
            if clip.resolve() in _held:
                continue
        paths = group_files(out_dir, clip.stem)
        if not paths:
            continue
        groups += 1
        for path in paths:
            try:
                size = path.stat().st_size
                path.unlink()
            except FileNotFoundError:
                continue  # somebody else got there first
            freed += size
            files += 1
    return Pruned(groups, files, freed)
