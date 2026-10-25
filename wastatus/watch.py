"""Keeping an eye on the hosted page, from inside its own container.

Every few minutes: is the disk filling, is the container near its memory limit, is
anything waiting too long for a render.
Once a day: a digest of yesterday to the owner's Chat space, a backup of the
people database, and the clips of anyone who has not been back in 90 days removed.
Nothing here goes on the host's crontab, so removing the project removes all of it.
See docs/hosted-page.md, Phase 3.
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import accounts, notify

log = logging.getLogger("wastatus")

EVERY = 300                        # seconds between checks
DISK_FLOOR = 5_000_000_000         # alert below this much free space
QUEUE_WAIT = 300                   # alert when a popup job has waited this long
DIGEST_AT = (3, 0)                 # 03:00 UTC is 08:30 in India
BACKUPS_KEPT = 7
INACTIVE_DAYS = 90
MEMORY_SHARE = 0.85                # alert when the container uses this much of its limit
CGROUP = Path("/sys/fs/cgroup")    # cgroup v2, as Docker mounts it inside a container


def memory_use(root: Path = CGROUP) -> tuple[int, int] | None:
    """Bytes in use and the limit, from the container's own cgroup, or None outside
    a container or without a limit (`max`)."""
    try:
        used = int((root / "memory.current").read_text().strip())
        limit = (root / "memory.max").read_text().strip()
    except (OSError, ValueError):
        return None
    if not limit.isdigit():
        return None
    return used, int(limit)


class Watch:
    def __init__(self, portal) -> None:
        self.portal = portal
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._loop, name="watch", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(EVERY):
            try:
                self.check()
            except Exception:  # noqa: BLE001 - the watcher must outlive what it watches
                log.exception("the watch could not run its checks")

    def check(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        portal = self.portal
        free = shutil.disk_usage(portal.root).free
        if free < DISK_FLOOR:
            portal.alert("disk-low", f"the renderer has {free / 1e9:.1f} GB free")
        memory = memory_use()
        if memory and memory[0] > MEMORY_SHARE * memory[1]:
            portal.alert("memory-high", f"the renderer is using {memory[0] / 1e9:.1f} GB of "
                         f"its {memory[1] / 1e9:.1f} GB")
        oldest = self._oldest_wait(now)
        if oldest > QUEUE_WAIT:
            portal.alert("queue-wait", f"a clip has waited {oldest / 60:.0f} minutes for "
                         "the renderer")
        when = datetime.fromtimestamp(now, timezone.utc)
        if (when.hour, when.minute) >= DIGEST_AT:
            day = when.strftime("%Y-%m-%d")
            if portal.accounts.should_alert(f"daily:{day}", 2 * 86400):
                self.daily(when)

    def _oldest_wait(self, now: float) -> float:
        renderer = self.portal.renderer
        with renderer.lock:
            waits = [now - renderer.jobs[i].created for i in renderer.waiting
                     if i in renderer.jobs]
        return max(waits, default=0.0)

    # -- once a day -----------------------------------------------------------

    def daily(self, when: datetime) -> None:
        for step in (self.digest, self.backup, self.tidy):
            try:
                step(when)
            except Exception:  # noqa: BLE001 - one step failing must not skip the rest
                log.exception("daily step %s failed", step.__name__)

    def digest(self, when: datetime) -> str:
        store = self.portal.accounts
        yesterday = (when - timedelta(days=1)).strftime("%Y-%m-%d")
        rows = store.usage_table(yesterday)
        since = (when - timedelta(days=1)).timestamp()
        reports = store.reports(since)
        people = store.people()
        pending = [p for p in people if p.status == accounts.PENDING]
        new = [p for p in people if p.created >= since]
        clips = sum(r["clips"] for r in rows)
        failures = sum(r["failures"] for r in rows)
        upload_mb = sum(r["upload_bytes"] for r in rows) / 1e6
        hours = Counter(datetime.fromtimestamp(at, timezone.utc).hour
                        for at, _ in self.portal.recent_outcomes(86400))
        lines = [
            f"SnipShare, {yesterday}: {len(rows)} people made {clips} clips "
            f"({failures} failed), {upload_mb:.0f} MB uploaded.",
            f"Requests: {len(new)} new, {len(pending)} waiting for you.",
        ]
        if hours:
            hour, count = hours.most_common(1)[0]
            lines.append(f"Busiest hour: {hour:02d}:00 UTC, {count} renders.")
        if reports:
            kinds = Counter(f"{r['source']}/{r['phase']}/{r['code']}" for r in reports)
            lines.append("Failures reported: " + ", ".join(
                f"{kind} x{count}" for kind, count in kinds.most_common(5)))
        free = shutil.disk_usage(self.portal.root).free / 1e9
        lines.append(f"Disk free: {free:.0f} GB.")
        text = "\n".join(lines)
        notify.chat(text)
        return text

    def backup(self, when: datetime) -> Path:
        folder = self.portal.root / "backups"
        dest = self.portal.accounts.backup(folder / f"people-{when:%Y-%m-%d}.db")
        for old in sorted(folder.glob("people-*.db"))[:-BACKUPS_KEPT]:
            old.unlink(missing_ok=True)
        return dest

    def tidy(self, when: datetime) -> int:
        """Clips of people who have not been back in 90 days. Their account stays,
        so they can sign in again; the files are what costs the disk."""
        cutoff = (when - timedelta(days=INACTIVE_DAYS)).timestamp()
        removed = 0
        for person in self.portal.accounts.people():
            seen = person.last_seen or person.created
            out = self.portal.users_dir / person.id / "out"
            if seen < cutoff and out.is_dir():
                shutil.rmtree(out, ignore_errors=True)
                removed += 1
        if removed:
            log.info("tidy: clips of %d inactive people removed", removed)
        days = self.portal.accounts.forget_old_usage()
        if days:
            log.info("tidy: %d daily count(s) past their year removed", days)
        return removed
