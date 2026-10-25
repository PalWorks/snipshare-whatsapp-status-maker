"""Output file naming.

Names are for a human scanning a folder, so they lead with the date and the song
rather than a video id. Traceability back to the source is preserved by the URL
inside the sidecar caption file and by the run log.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date
from pathlib import Path

log = logging.getLogger("wastatus")

SLUG_MAX = 48


def slugify(text: str, *, max_length: int = SLUG_MAX) -> str:
    """Lowercase ASCII hyphen slug, cut on a word boundary."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text or "").strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)
    if len(slug) <= max_length:
        return slug or "clip"
    cut = slug[:max_length]
    if "-" in cut:
        cut = cut.rsplit("-", 1)[0]
    return cut.strip("-") or slug[:max_length]


def build_stem(
    title: str,
    start: float,
    end: float,
    *,
    video: bool = False,
    on: date | None = None,
) -> str:
    """20260818_sinna-sinna-murugaiyaa_70-85 (plus _video in video mode)."""
    stamp = (on or date.today()).strftime("%Y%m%d")
    parts = [stamp, slugify(title), f"{int(start)}-{int(end)}"]
    if video:
        parts.append("video")
    return "_".join(parts)


def reserve_stem(out_dir: Path, stem: str) -> str:
    """Claim a name, atomically, and return it.

    A check-then-act (look for `<stem>.mp4`, then render) is not enough: the render
    that follows does not create that file until it finishes, half a minute later.
    Two renders of the same song and window started in that window agreed on the
    same name and one overwrote the other. See [TASKS.md](TASKS.md) T-017.

    The claim is the `.part` file the render was going to land in anyway, created
    here with `O_EXCL` so exactly one caller can win it. That works between
    processes and not merely between threads, which matters because the page and the
    command line are different processes. The page's `*.mp4` glob cannot see a
    `.part`, so a claim is invisible until the render renames it into place, and
    `pipeline.produce` already removes it on every exit path.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for candidate in _candidates(stem):
        if (out_dir / f"{candidate}.mp4").exists():
            continue
        claim = out_dir / f"{candidate}.mp4.part"
        try:
            os.close(os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
        except FileExistsError:
            # Either a render is running right now, or one was killed and left its
            # claim behind. Both mean this name is not ours; say so, because a clip
            # that quietly becomes `-2` is the kind of thing nobody notices.
            log.warning("%s is claimed by another render, trying the next name", claim.name)
            continue
        return candidate
    raise RuntimeError(f"cannot find a free name for {stem} in {out_dir}")


def _candidates(stem: str):
    yield stem
    for suffix in range(2, 100):
        yield f"{stem}-{suffix}"
