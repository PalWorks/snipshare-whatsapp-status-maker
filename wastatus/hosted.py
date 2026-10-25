"""The hosted renderer: the engine behind an API the browser extension uploads to.

The extension captures a window of a YouTube video in the viewer's own browser and
uploads it here; this runs the identical `pipeline.produce` the command line and the
local page run, with the upload in place of yt-dlp, and hands the clip back. Nothing
in this module, and nothing it calls, talks to YouTube. See docs/extension.md.

Standard library only, like `serve.py`: a handful of people, one or two renders at a
time, behind a Cloudflare Tunnel. A framework would add more to audit than it removes.

**Who may use it.** Holders of a token the owner made with `wastatus hosted token
add NAME`. Only the token's SHA-256 is stored. A renderer anyone can reach is an
ffmpeg anyone can feed, which is why there is no sign-up. DECISIONS.md D-081.

**Built for slow connections.** Uploads go in chunks with `Content-Range`, and the
server always says how much it already has, so a client that lost a chunk, a
connection or its own state resumes instead of starting over. The finished clip is
served with byte ranges for the same reason on the way back. D-082.

**No CORS headers, on purpose.** The extension's service worker has host
permission for this origin and does not need them. A web page would, so a web page
holding someone's token still cannot read a single response.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import queue
import re
import secrets
import shutil
import threading
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from PIL import Image

from . import capture, fetch, pipeline, proc, render, runlog, serve

log = logging.getLogger("wastatus")

API = "/api/v1"
API_VERSION = 1
DEFAULT_PORT = 8790
BIND = "127.0.0.1"

DATA_ENV = "WASTATUS_HOSTED_DATA"
WORKERS_ENV = "WASTATUS_HOSTED_WORKERS"

# A chunk is at most this much. Small enough to go through Cloudflare and Caddy's
# body cap with room to spare, and to be cheap to send again on a bad connection.
CHUNK_MAX = 1_048_576
# What a whole upload may be. A 90 second 1080p AV1 capture measured 25 MB; video
# has twice that. Audio for 90 seconds of Opus is about 1.5 MB.
UPLOAD_MAX = {"audio": 16_000_000, "video": 64_000_000, "artwork": 4_000_000}
ARTWORK_MAX_PIXELS = 4096 * 4096
JSON_MAX = 64_000

UPLOAD_IDLE = 30 * 60   # an upload nobody has touched in this long is abandoned
JOB_TTL = 60 * 60       # a finished job, clip and all, is kept this long
JANITOR_EVERY = 60
QUEUE_MAX = 8           # waiting jobs, across everybody
FREE_DISK_MIN = 1_000_000_000

ID = re.compile(r"^[A-Za-z0-9_-]{16,40}$")
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
CONTENT_RANGE = re.compile(r"^bytes (\d+)-(\d+)/(\d+)$")

QUEUED, RENDERING, DONE, FAILED, CANCELLED = (
    "queued", "rendering", "done", "failed", "cancelled")
ACTIVE = (QUEUED, RENDERING)


def _now() -> float:
    return time.time()


def _iso(stamp: float | None) -> str | None:
    if stamp is None:
        return None
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec="seconds")


def data_dir() -> Path:
    override = os.environ.get(DATA_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "wastatus" / "hosted"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# -- tokens ----------------------------------------------------------------

class Tokens:
    """Names against token hashes, in one small JSON file.

    Read again whenever the file changes, so a token added or revoked from the
    command line takes effect on the next request without a restart.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._stamp: float | None = None
        self._by_hash: dict[str, dict[str, Any]] = {}

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            stamp = self.path.stat().st_mtime
        except FileNotFoundError:
            return {}
        if stamp != self._stamp:
            try:
                self._by_hash = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                # A broken file must lock everybody out, never let everybody in.
                log.error("token file unreadable, refusing every request: %s", exc)
                self._by_hash = {}
            self._stamp = stamp
        return self._by_hash

    def name_of(self, token: str) -> str | None:
        with self._lock:
            entry = self._load().get(hash_token(token))
        return entry.get("name") if entry else None

    def _write(self, entries: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        staged = self.path.with_suffix(".tmp")
        staged.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
        os.chmod(staged, 0o600)
        os.replace(staged, self.path)

    def add(self, name: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9._@-]{1,64}", name):
            raise ValueError("a token's name is letters, digits and . _ @ - only")
        with self._lock:
            entries = dict(self._load())
            if any(entry.get("name") == name for entry in entries.values()):
                raise ValueError(f"there is already a token called {name}")
            token = secrets.token_urlsafe(32)
            entries[hash_token(token)] = {"name": name, "created": _iso(_now())}
            self._write(entries)
            self._stamp = None
        return token

    def revoke(self, name: str) -> bool:
        with self._lock:
            entries = dict(self._load())
            kept = {k: v for k, v in entries.items() if v.get("name") != name}
            if len(kept) == len(entries):
                return False
            self._write(kept)
            self._stamp = None
        return True

    def names(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(self._load().values(), key=lambda e: e.get("name", ""))


# -- uploads and jobs -------------------------------------------------------

@dataclass
class Upload:
    id: str
    owner: str
    kind: str
    size: int
    path: Path
    created: float = field(default_factory=_now)
    touched: float = field(default_factory=_now)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    claimed: bool = False  # handed to a job, so no longer writable or deletable

    @property
    def received(self) -> int:
        try:
            return self.path.stat().st_size
        except FileNotFoundError:
            return 0

    def as_json(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "size": self.size,
                "received": self.received, "chunk": CHUNK_MAX}

    def save(self) -> None:
        self.path.with_suffix(".json").write_text(json.dumps({
            "id": self.id, "owner": self.owner, "kind": self.kind,
            "size": self.size, "created": self.created,
        }), encoding="utf-8")


@dataclass
class HostedJob:
    id: str
    owner: str
    user: str
    request: dict[str, Any]
    folder: Path
    state: str = QUEUED
    stage: str = ""
    message: str = ""
    error: str = ""
    created: float = field(default_factory=_now)
    finished: float | None = None
    clip: Path | None = None
    caption: str = ""
    title: str = ""
    size: int = 0
    thread: int | None = None
    # Asked to stop while the worker was between taking the job and registering
    # its thread. The worker checks this once it has, so the request is not lost.
    cancel_requested: bool = False

    def as_json(self, position: int | None = None) -> dict[str, Any]:
        return {
            "id": self.id, "state": self.state, "stage": self.stage,
            "message": self.message, "error": self.error, "position": position,
            "title": self.title, "caption": self.caption, "size": self.size,
            "video_id": self.request.get("video_id"),
            "start": self.request.get("start"), "end": self.request.get("end"),
            "mode": self.request.get("mode"),
            "created": _iso(self.created), "finished": _iso(self.finished),
        }

    def save(self) -> None:
        record = self.as_json()
        record.update(owner=self.owner, user=self.user, request=self.request,
                      clip=str(self.clip) if self.clip else None,
                      created_at=self.created, finished_at=self.finished)
        staged = self.folder / "job.json.tmp"
        staged.write_text(json.dumps(record, indent=2), encoding="utf-8")
        os.replace(staged, self.folder / "job.json")


class Refused(Exception):
    """A request that is understood and declined. The message is for the person."""

    def __init__(self, status: HTTPStatus, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.extra = extra


class Renderer:
    """Uploads, the job queue, the workers and the janitor.

    One lock guards the two tables. File writes to an upload hold that upload's own
    lock instead, so a slow chunk from one person never stalls anybody else.
    """

    def __init__(self, root: Path, workers: int = 1) -> None:
        self.root = root
        self.uploads_dir = root / "uploads"
        self.jobs_dir = root / "jobs"
        for folder in (self.uploads_dir, self.jobs_dir):
            folder.mkdir(parents=True, exist_ok=True)
        self.tokens = Tokens(root / "tokens.json")
        self.lock = threading.Lock()
        self.uploads: dict[str, Upload] = {}
        self.jobs: dict[str, HostedJob] = {}
        self.queue: queue.Queue[str] = queue.Queue()
        self.waiting: list[str] = []  # queued job ids, in order, for positions
        self.workers = max(1, workers)
        # Every render on this machine takes one of these, whichever door it came
        # in by: a job from the extension's popup or a clip from the hosted page.
        self.slots = threading.BoundedSemaphore(self.workers)
        # Set by the hosted page (`portal`): what a grant token stands for, and the
        # daily allowance an upload counts against. Unset, only tokens work.
        self.grant_owner: Any = None   # (token) -> (owner, name) | None
        self.on_upload: Any = None     # (owner, size) -> None, raising Refused
        self.on_upload_gone: Any = None  # (owner, unsent bytes, created): never claimed
        self._stop = threading.Event()
        self._recover()

    # -- start and stop ----------------------------------------------------

    def _recover(self) -> None:
        """Pick up what a previous process left on disk.

        A finished clip is still worth collecting, so it stays until its time is up.
        A job that was waiting or rendering when the process stopped cannot be
        resumed, so it is reported as failed rather than vanishing into a 404. Part
        uploads come back too: the client asks how much arrived and carries on.
        """
        for folder in self.jobs_dir.iterdir():
            # A folder with no record is a job that never finished being created.
            if folder.is_dir() and not (folder / "job.json").is_file():
                shutil.rmtree(folder, ignore_errors=True)
        for record in self.jobs_dir.glob("*/job.json"):
            try:
                data = json.loads(record.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                shutil.rmtree(record.parent, ignore_errors=True)
                continue
            job = HostedJob(
                id=data["id"], owner=data["owner"], user=data.get("user", ""),
                request=data.get("request", {}), folder=record.parent,
                state=data.get("state", FAILED), stage=data.get("stage", ""),
                message=data.get("message", ""), error=data.get("error", ""),
                created=data.get("created_at", _now()),
                finished=data.get("finished_at"),
                clip=Path(data["clip"]) if data.get("clip") else None,
                caption=data.get("caption", ""), title=data.get("title", ""),
                size=data.get("size", 0),
            )
            if job.state in ACTIVE or (job.state == DONE
                                       and not (job.clip and job.clip.is_file())):
                job.state = FAILED
                job.error = ("the renderer restarted before this clip was finished. "
                             "Make it again")
                job.finished = _now()
                job.save()
            self.jobs[job.id] = job
        for meta in self.uploads_dir.glob("*.json"):
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                upload = Upload(id=data["id"], owner=data["owner"], kind=data["kind"],
                                size=int(data["size"]), path=meta.with_suffix(".bin"),
                                created=float(data.get("created", _now())))
            except (OSError, KeyError, ValueError, json.JSONDecodeError):
                meta.unlink(missing_ok=True)
                continue
            self.uploads[upload.id] = upload

    def start(self) -> None:
        for index in range(self.workers):
            threading.Thread(target=self._work, name=f"render-{index}",
                             daemon=True).start()
        threading.Thread(target=self._janitor, name="janitor", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        for _ in range(self.workers):
            self.queue.put("")

    # -- uploads -----------------------------------------------------------

    def create_upload(self, owner: str, kind: str, size: Any) -> Upload:
        if kind not in UPLOAD_MAX:
            raise Refused(HTTPStatus.BAD_REQUEST, "an upload is audio, video or artwork")
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise Refused(HTTPStatus.BAD_REQUEST, "an upload needs its size in bytes")
        if size > UPLOAD_MAX[kind]:
            raise Refused(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                          f"the {kind} is {size / 1e6:.1f} MB, and the most this "
                          f"renderer takes is {UPLOAD_MAX[kind] / 1e6:.0f} MB")
        if shutil.disk_usage(self.root).free < FREE_DISK_MIN + size:
            raise Refused(HTTPStatus.INSUFFICIENT_STORAGE,
                          "the renderer is out of space. Try again later")
        if self.on_upload is not None:
            self.on_upload(owner, size)
        upload = Upload(id=secrets.token_urlsafe(18), owner=owner, kind=kind,
                        size=size, path=self.uploads_dir / "x")
        upload.path = self.uploads_dir / f"{upload.id}.bin"
        upload.path.touch()
        upload.save()
        with self.lock:
            self.uploads[upload.id] = upload
        log.info("upload %s: %s, %d bytes", upload.id, kind, size)
        return upload

    def upload_of(self, owner: str, upload_id: str) -> Upload:
        with self.lock:
            upload = self.uploads.get(upload_id)
        # Somebody else's upload is answered exactly as a missing one is.
        if upload is None or upload.owner != owner:
            raise Refused(HTTPStatus.NOT_FOUND, "no such upload")
        return upload

    def write_chunk(self, upload: Upload, first: int, last: int, total: int,
                    body: bytes) -> int:
        """Append one chunk. Returns how much of the upload the server now holds.

        Idempotent by offset, which is what makes a retry safe whatever happened to
        the previous attempt: a chunk the server already has is acknowledged again,
        an overlap keeps only the new tail, and a chunk past what the server has is
        refused with the offset it does have, so the client can rewind to it.
        """
        if total != upload.size or last >= upload.size or first > last:
            raise Refused(HTTPStatus.BAD_REQUEST,
                          f"that range does not fit an upload of {upload.size} bytes")
        if len(body) != last - first + 1:
            raise Refused(HTTPStatus.BAD_REQUEST, "the chunk is not the length its "
                          "range says")
        with upload.lock:
            if upload.claimed:
                # Says how much it holds, as every 409 here does: a client reads
                # `received` off a conflict to know where it stands.
                raise Refused(HTTPStatus.CONFLICT, "this upload is already in a job",
                              received=upload.received, claimed=True)
            have = upload.received
            upload.touched = _now()
            if first > have:
                raise Refused(HTTPStatus.CONFLICT, "a chunk is missing before this one",
                              received=have)
            if last < have:
                return have
            with upload.path.open("ab") as handle:
                handle.write(body[have - first:])
            return upload.received

    def delete_upload(self, owner: str, upload_id: str) -> None:
        upload = self.upload_of(owner, upload_id)
        with upload.lock:
            if upload.claimed:
                raise Refused(HTTPStatus.CONFLICT, "this upload is already in a job")
            self._forget_upload(upload)

    def _forget_upload(self, upload: Upload) -> None:
        if self.on_upload_gone is not None and not upload.claimed:
            # Deleted or abandoned before it was used: the part never sent is not
            # counted against anybody's day.
            try:
                self.on_upload_gone(upload.owner, upload.size - upload.received,
                                    upload.created)
            except Exception:  # noqa: BLE001 - accounting must not stop the clean-up
                log.exception("could not give back an abandoned upload's allowance")
        with self.lock:
            self.uploads.pop(upload.id, None)
        upload.path.unlink(missing_ok=True)
        upload.path.with_suffix(".json").unlink(missing_ok=True)

    # -- jobs --------------------------------------------------------------

    def create_job(self, owner: str, user: str, body: dict[str, Any]) -> HostedJob:
        request = self._validate(body)
        # Before the uploads are looked at: a client whose 202 never arrived asks
        # again with uploads the first request already spent, and what it needs to
        # hear is "you already have this job", with its id, not "no such upload".
        self._refuse_if_active(owner)
        needed = {"audio": request["audio"]}
        if request["mode"] == "video":
            needed["video"] = request["video"]
        if request.get("artwork"):
            needed["artwork"] = request["artwork"]

        uploads: dict[str, Upload] = {}
        for kind, upload_id in needed.items():
            upload = self.upload_of(owner, upload_id)
            if upload.kind != kind:
                raise Refused(HTTPStatus.BAD_REQUEST,
                              f"upload {upload_id} is {upload.kind}, not {kind}")
            if upload.received != upload.size:
                raise Refused(HTTPStatus.CONFLICT,
                              f"the {kind} upload is not finished",
                              received=upload.received)
            uploads[kind] = upload
        if "artwork" in uploads:
            _check_artwork(uploads["artwork"].path)

        # Each upload's own lock first, then the tables', which is the order every
        # other path takes them in: a chunk, a delete or the janitor can never be
        # half way through an upload this job is moving.
        with ExitStack() as held:
            for upload in sorted(uploads.values(), key=lambda u: u.id):
                held.enter_context(upload.lock)
            with self.lock:
                self._refuse_if_active(owner, locked=True)
                if len(self.waiting) >= QUEUE_MAX:
                    raise Refused(HTTPStatus.SERVICE_UNAVAILABLE,
                                  "the renderer is busy. Try again in a minute",
                                  retry_after=60)
                for upload in uploads.values():
                    if upload.claimed or self.uploads.get(upload.id) is not upload:
                        raise Refused(HTTPStatus.CONFLICT, "an upload is already in a job")
                job_id = secrets.token_urlsafe(18)
                folder = self.jobs_dir / job_id
                folder.mkdir()
                inputs: dict[str, str] = {}
                try:
                    for kind, upload in uploads.items():
                        target = folder / f"{kind}{_suffix(kind)}"
                        os.replace(upload.path, target)
                        inputs[kind] = str(target)
                    request["inputs"] = inputs
                    job = HostedJob(id=job_id, owner=owner, user=user, request=request,
                                    folder=folder, title=request["title"])
                    job.save()
                except OSError:
                    # Put back what moved, so the client can simply ask again.
                    for kind, target in inputs.items():
                        os.replace(target, uploads[kind].path)
                    shutil.rmtree(folder, ignore_errors=True)
                    raise
                for upload in uploads.values():
                    upload.claimed = True
                    upload.path.with_suffix(".json").unlink(missing_ok=True)
                    self.uploads.pop(upload.id, None)
                self.jobs[job_id] = job
                self.waiting.append(job_id)
        self.queue.put(job_id)
        log.info("job %s queued for %s: %s %.1f-%.1f %s", job_id, user,
                 request["video_id"], request["start"], request["end"], request["mode"])
        return job

    def claim(self, owner: str, needed: dict[str, str], folder: Path) -> dict[str, Path]:
        """Hand finished uploads to a render the hosted page asked for.

        The same checks `create_job` makes: each upload is this owner's, of the
        kind it is named as, and complete. The files move into `folder`, which the
        caller owns and deletes, and the uploads leave the table: spent, exactly as
        a job spends them.
        """
        uploads: dict[str, Upload] = {}
        for kind, upload_id in needed.items():
            if not isinstance(upload_id, str) or not ID.match(upload_id):
                raise Refused(HTTPStatus.BAD_REQUEST, f"{kind} is not an upload id")
            upload = self.upload_of(owner, upload_id)
            if upload.kind != kind:
                raise Refused(HTTPStatus.BAD_REQUEST,
                              f"upload {upload_id} is {upload.kind}, not {kind}")
            if upload.received != upload.size:
                raise Refused(HTTPStatus.CONFLICT, f"the {kind} upload is not finished",
                              received=upload.received)
            uploads[kind] = upload
        if "artwork" in uploads:
            _check_artwork(uploads["artwork"].path)
        folder.mkdir(parents=True, exist_ok=True)
        moved: dict[str, Path] = {}
        with ExitStack() as held:
            for upload in sorted(uploads.values(), key=lambda u: u.id):
                held.enter_context(upload.lock)
            with self.lock:
                for upload in uploads.values():
                    if upload.claimed or self.uploads.get(upload.id) is not upload:
                        raise Refused(HTTPStatus.CONFLICT, "an upload is already in use")
                try:
                    for kind, upload in uploads.items():
                        target = folder / f"{kind}{_suffix(kind)}"
                        os.replace(upload.path, target)
                        moved[kind] = target
                except OSError:
                    for kind, target in moved.items():
                        os.replace(target, uploads[kind].path)
                    raise
                for upload in uploads.values():
                    upload.claimed = True
                    upload.path.with_suffix(".json").unlink(missing_ok=True)
                    self.uploads.pop(upload.id, None)
        return moved

    def _refuse_if_active(self, owner: str, locked: bool = False) -> None:
        def check() -> None:
            mine = [j for j in self.jobs.values() if j.owner == owner and j.state in ACTIVE]
            if mine:
                raise Refused(HTTPStatus.CONFLICT,
                              "a clip of yours is already being made. Wait for it, "
                              "or stop it", job=mine[0].id)
        if locked:
            check()
        else:
            with self.lock:
                check()

    def jobs_of(self, owner: str) -> list[HostedJob]:
        with self.lock:
            return sorted((j for j in self.jobs.values() if j.owner == owner),
                          key=lambda j: j.created)

    def _validate(self, body: dict[str, Any]) -> dict[str, Any]:
        def text(key: str, limit: int, required: bool = True) -> str:
            value = body.get(key)
            if value is None and not required:
                return ""
            if not isinstance(value, str) or (required and not value.strip()):
                raise Refused(HTTPStatus.BAD_REQUEST, f"{key} is missing")
            if len(value) > limit:
                raise Refused(HTTPStatus.BAD_REQUEST, f"{key} is too long")
            return value.strip()

        def number(key: str) -> float:
            value = body.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise Refused(HTTPStatus.BAD_REQUEST, f"{key} has to be a number")
            if value != value or value in (float("inf"), float("-inf")):
                raise Refused(HTTPStatus.BAD_REQUEST, f"{key} has to be a number")
            return float(value)

        video_id = text("video_id", 11)
        if not VIDEO_ID.match(video_id):
            raise Refused(HTTPStatus.BAD_REQUEST, "that is not a YouTube video id")
        start, end, duration = number("start"), number("end"), number("duration")
        if start < 0 or duration <= 0:
            raise Refused(HTTPStatus.BAD_REQUEST, "the window is outside the video")
        if end <= start:
            raise Refused(HTTPStatus.BAD_REQUEST, "the end has to come after the start")
        if end - start > pipeline.MAX_DURATION:
            raise Refused(HTTPStatus.BAD_REQUEST,
                          f"{end - start:.0f}s exceeds the "
                          f"{pipeline.MAX_DURATION:.0f}s WhatsApp Status limit")
        if start >= duration:
            raise Refused(HTTPStatus.BAD_REQUEST, "the start is past the end of the video")
        mode = body.get("mode", "card")
        if mode not in ("card", "video"):
            raise Refused(HTTPStatus.BAD_REQUEST, "mode is card or video")
        fill = body.get("fill", render.BLUR)
        if fill not in render.FILLS:
            raise Refused(HTTPStatus.BAD_REQUEST, "fill is blur or black")
        wave = body.get("wave", True)
        if not isinstance(wave, bool):
            raise Refused(HTTPStatus.BAD_REQUEST, "wave is true or false")
        uploads = {}
        for kind in ("audio", "video", "artwork"):
            value = body.get(kind)
            if value is None:
                continue
            if not isinstance(value, str) or not ID.match(value):
                raise Refused(HTTPStatus.BAD_REQUEST, f"{kind} is not an upload id")
            uploads[kind] = value
        if "audio" not in uploads:
            raise Refused(HTTPStatus.BAD_REQUEST, "the audio upload is missing")
        if mode == "video" and "video" not in uploads:
            raise Refused(HTTPStatus.BAD_REQUEST, "video mode needs the video upload")
        if mode == "card" and "artwork" not in uploads:
            # The engine would fetch the thumbnail itself, and from here that is a
            # request to YouTube from a datacentre address. The browser has it.
            raise Refused(HTTPStatus.BAD_REQUEST, "card mode needs the artwork upload")
        return {
            "video_id": video_id,
            "title": text("title", 300),
            "channel": text("channel", 200),
            "artist": text("artist", 200, required=False),
            "title_override": text("title_override", 300, required=False),
            "channel_override": text("channel_override", 200, required=False),
            "duration": duration, "start": start, "end": min(end, duration),
            "mode": mode, "fill": fill, "wave": wave, **uploads,
        }

    def job_of(self, owner: str, job_id: str) -> HostedJob:
        with self.lock:
            job = self.jobs.get(job_id)
        if job is None or job.owner != owner:
            raise Refused(HTTPStatus.NOT_FOUND, "no such clip. It may have expired")
        return job

    def position(self, job: HostedJob) -> int | None:
        with self.lock:
            if job.state != QUEUED or job.id not in self.waiting:
                return None
            return self.waiting.index(job.id) + 1

    def cancel(self, owner: str, job_id: str) -> HostedJob:
        """Stop a job, or delete a finished one and its clip.

        A rendering job is stopped by killing the ffmpeg it is waiting on; the
        worker then records the state and deletes the folder itself, so nothing is
        removed from under a process still writing into it.
        """
        job = self.job_of(owner, job_id)
        with self.lock:
            rendering = job.state == RENDERING
            if job.state == QUEUED:
                job.state, job.finished = CANCELLED, _now()
                if job.id in self.waiting:
                    self.waiting.remove(job.id)
            if rendering:
                job.cancel_requested = True
            thread = job.thread if rendering else None
        if thread is not None:
            proc.cancel(thread)
        if not rendering:
            self._forget_job(job)
        return job

    def _forget_job(self, job: HostedJob) -> None:
        with self.lock:
            self.jobs.pop(job.id, None)
            if job.id in self.waiting:
                self.waiting.remove(job.id)
        shutil.rmtree(job.folder, ignore_errors=True)

    # -- the work ----------------------------------------------------------

    def _work(self) -> None:
        while not self._stop.is_set():
            job_id = self.queue.get()
            if not job_id:
                return
            with self.lock:
                job = self.jobs.get(job_id)
                if job is None or job.state != QUEUED:
                    continue
                self.waiting.remove(job_id)
                job.state = RENDERING
            try:
                with self.slots:
                    self._render(job)
            except Exception:  # noqa: BLE001 - a worker that dies takes the queue with it
                log.exception("job %s: unexpected failure", job.id)
                with self.lock:
                    job.state, job.error = FAILED, "the render failed unexpectedly"
                    job.finished = _now()
            try:
                job.save()
            except OSError:
                pass  # cancelled and deleted already

    def _render(self, job: HostedJob) -> None:
        request = job.request
        inputs = {kind: Path(path) for kind, path in request["inputs"].items()}
        watch_url = f"https://www.youtube.com/watch?v={request['video_id']}"
        source = fetch.Source(
            video_id=request["video_id"], title=request["title"],
            channel=request["channel"], duration=request["duration"],
            watch_url=watch_url, artist=request.get("artist", ""),
        )
        engine_job = pipeline.Job(
            url=watch_url, start=request["start"], end=request["end"],
            video=request["mode"] == "video", fill=request["fill"],
            wave=request["wave"],
            title=request.get("title_override") or None,
            channel=request.get("channel_override") or None,
            out=job.folder / "out",
            captured=pipeline.Captured(
                source=source, audio=inputs["audio"], video=inputs.get("video"),
                artwork=inputs.get("artwork"),
            ),
        )
        run = runlog.Run(log, url=watch_url, start=engine_job.start,
                         end=engine_job.end, video=engine_job.video,
                         hosted=True, user=job.user, job=job.id)

        def progress(stage: str, message: str) -> None:
            with self.lock:
                job.stage, job.message = stage, message

        with proc.cancellable() as ident:
            with self.lock:
                job.thread = ident
                stop_now = job.cancel_requested
            if stop_now:
                proc.cancel(ident)
            try:
                result = pipeline.produce(engine_job, run, progress)
            except proc.Cancelled:
                run.finish("cancelled")
                with self.lock:
                    job.state, job.finished, job.thread = CANCELLED, _now(), None
                self._forget_job(job)
                return
            except (capture.CaptureError, render.RenderError, fetch.FetchError,
                    ValueError, OSError) as exc:
                run.finish("error", error=str(exc))
                with self.lock:
                    job.state, job.error = FAILED, _plain(exc)
                    job.finished, job.thread = _now(), None
                return
            except Exception as exc:  # noqa: BLE001 - recorded, and the worker lives on
                log.exception("job %s: unexpected failure", job.id)
                run.finish("error", error=repr(exc))
                with self.lock:
                    job.state, job.error = FAILED, "the render failed unexpectedly"
                    job.finished, job.thread = _now(), None
                return
            finally:
                for path in inputs.values():
                    path.unlink(missing_ok=True)
        run.finish("ok")
        with self.lock:
            job.state, job.stage, job.message = DONE, "done", ""
            job.clip, job.caption = result.clip, result.caption
            job.title, job.size = result.title, result.size_bytes
            job.finished, job.thread = _now(), None
        log.info("job %s done: %s, %d bytes", job.id, result.clip.name,
                 result.size_bytes)

    def _janitor(self) -> None:
        while not self._stop.wait(JANITOR_EVERY):
            self.sweep()

    def sweep(self, now: float | None = None) -> None:
        """Delete what nobody will come back for. Run on a timer; public for tests."""
        now = _now() if now is None else now
        with self.lock:
            uploads = [u for u in self.uploads.values()
                       if not u.claimed and now - u.touched > UPLOAD_IDLE]
            jobs = [j for j in self.jobs.values()
                    if j.state not in ACTIVE and j.finished is not None
                    and now - j.finished > JOB_TTL]
        removed = 0
        for upload in uploads:
            with upload.lock:
                # Looked at again under its own lock: a chunk may have landed since
                # the list was made, and that upload is not idle any more.
                if not upload.claimed and now - upload.touched > UPLOAD_IDLE:
                    self._forget_upload(upload)
                    removed += 1
        for job in jobs:
            self._forget_job(job)
        if removed or jobs:
            log.info("janitor: %d upload(s), %d job(s) removed", removed, len(jobs))

    def health(self) -> dict[str, Any]:
        # Every render holds a slot, whichever door it came in by, so the slots in
        # use are the honest count; the popup's own jobs are a subset of them.
        busy = self.workers - self.slots._value  # noqa: SLF001 - read only
        with self.lock:
            return {"ok": True, "version": API_VERSION, "queued": len(self.waiting),
                    "rendering": busy, "workers": self.workers}


def _suffix(kind: str) -> str:
    return ".jpg" if kind == "artwork" else ".media"


def _plain(exc: Exception) -> str:
    return serve.plain_error(exc)


def _check_artwork(path: Path) -> None:
    """An image Pillow can open, of a sane size. Anything else is refused here,
    before the engine opens it, because the engine trusts what it is given."""
    try:
        with Image.open(path) as image:
            if image.width * image.height > ARTWORK_MAX_PIXELS:
                raise Refused(HTTPStatus.BAD_REQUEST, "the artwork is too large")
            image.verify()
    except Refused:
        raise
    except Exception as exc:  # noqa: BLE001 - Pillow raises a wide variety
        raise Refused(HTTPStatus.BAD_REQUEST, "the artwork is not an image") from exc


# -- HTTP ------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "wastatus-hosted"
    protocol_version = "HTTP/1.1"
    # A 1 MiB chunk on a 10 kB/s connection takes over a minute and a half. The
    # socket timeout bounds each read and write, not the request, so this is the
    # longest a stalled connection holds a thread.
    timeout = 120

    def parse_request(self) -> bool:
        # The same refusal as the local page's: a body that could be read two ways,
        # or one on a method that never reads it, ends the connection (D-101).
        return super().parse_request() and not serve.refuse_ambiguous_body(self)
    renderer: Renderer  # set by make_server

    QUIET = ("/health", "/jobs/")

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        line = fmt % args
        if " 200 " in f" {line} " and any(part in line for part in self.QUIET) \
                and "/clip" not in line:
            return
        log.debug("hosted %s %s", self.headers.get("CF-Connecting-IP", "-"), line)

    def _send(self, status: HTTPStatus, body: bytes, content_type: str,
              extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK,
              extra: dict[str, str] | None = None) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json", extra)

    def _refuse(self, refused: Refused) -> None:
        if refused.status != HTTPStatus.UNAUTHORIZED:
            log.info("hosted refused %s %s: %d %s", self.command, self.path.split("?")[0],
                     refused.status, refused)
        extra = {}
        length = self.headers.get("Content-Length") or "0"
        if not getattr(self, "_consumed", False) and (
                length != "0" or self.headers.get("Transfer-Encoding")):
            # Refused before the body was read: a wrong token, somebody else's
            # upload, a chunk too large. The unread body is still in the socket and
            # would be parsed as the next request, so this connection ends here.
            self.close_connection = True
            extra["Connection"] = "close"
        if "retry_after" in refused.extra:
            extra["Retry-After"] = str(refused.extra["retry_after"])
        payload = {"error": str(refused)}
        payload.update({k: v for k, v in refused.extra.items() if k != "retry_after"})
        self._json(payload, refused.status, extra)

    def _owner(self, resource: str = "") -> tuple[str, str]:
        header = self.headers.get("Authorization", "")
        token = header[7:].strip() if header.startswith("Bearer ") else ""
        name = self.renderer.tokens.name_of(token) if token else None
        if not name and token and resource == "uploads" \
                and self.renderer.grant_owner is not None:
            # A grant from the hosted page: short lived, standing for the person
            # signed in there, and good for uploads and nothing else. The clip it
            # becomes is made by the page's own API, which counts it against the
            # person's day; a job from here would not be.
            found = self.renderer.grant_owner(token)
            if found:
                return found
        if not name:
            raise Refused(HTTPStatus.UNAUTHORIZED,
                          "that access token is not one this renderer knows")
        return hash_token(token), name

    def _read(self, limit: int) -> bytes:
        raw = self.headers.get("Content-Length")
        if raw is None or not (raw.isascii() and raw.isdigit()):
            raise Refused(HTTPStatus.LENGTH_REQUIRED, "send a Content-Length")
        length = int(raw)
        self._consumed = length <= limit
        if length > limit:
            # Read nothing: the connection is closed after this answer, rather than
            # draining a body we have already said no to.
            raise Refused(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "that body is too large")
        return self.rfile.read(length)

    def _json_body(self) -> dict[str, Any]:
        try:
            body = json.loads(self._read(JSON_MAX) or b"{}")
        except (ValueError, RecursionError) as exc:
            raise Refused(HTTPStatus.BAD_REQUEST, "the body is not JSON") from exc
        if not isinstance(body, dict):
            raise Refused(HTTPStatus.BAD_REQUEST, "the body has to be an object")
        return body

    def _route(self) -> tuple[str, list[str]]:
        path = self.path.split("?", 1)[0]
        if not path.startswith(API + "/"):
            raise Refused(HTTPStatus.NOT_FOUND, "not found")
        parts = [p for p in path[len(API) + 1:].split("/") if p]
        for part in parts[1:2]:
            if not ID.match(part):
                raise Refused(HTTPStatus.NOT_FOUND, "not found")
        return (parts[0] if parts else ""), parts[1:]

    def _dispatch(self, method: str) -> None:
        self._consumed = False
        try:
            resource, rest = self._route()
            if resource == "health" and method in ("GET", "HEAD") and not rest:
                return self._json(self.renderer.health())
            owner, name = self._owner(resource)
            handler = getattr(self, f"_{method.lower()}_{resource}", None)
            if handler is None:
                raise Refused(HTTPStatus.NOT_FOUND, "not found")
            handler(owner, name, rest)
        except Refused as refused:
            self._refuse(refused)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:  # noqa: BLE001 - one bad request must not take the server
            log.exception("hosted %s %s failed", method, self.path)
            try:
                self._json({"error": "the renderer hit an internal error"},
                           HTTPStatus.INTERNAL_SERVER_ERROR)
            except OSError:
                pass

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_HEAD(self) -> None:  # noqa: N802
        self._dispatch("HEAD")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    # -- resources ---------------------------------------------------------

    def _get_me(self, owner: str, name: str, rest: list[str]) -> None:
        if rest:
            raise Refused(HTTPStatus.NOT_FOUND, "not found")
        self._json({"name": name, "version": API_VERSION, "chunk": CHUNK_MAX,
                    "max_duration": pipeline.MAX_DURATION, "limits": UPLOAD_MAX})

    def _post_uploads(self, owner: str, name: str, rest: list[str]) -> None:
        if rest:
            raise Refused(HTTPStatus.NOT_FOUND, "not found")
        body = self._json_body()
        upload = self.renderer.create_upload(owner, body.get("kind"), body.get("size"))
        self._json(upload.as_json(), HTTPStatus.CREATED)

    def _get_uploads(self, owner: str, name: str, rest: list[str]) -> None:
        if len(rest) != 1:
            raise Refused(HTTPStatus.NOT_FOUND, "not found")
        self._json(self.renderer.upload_of(owner, rest[0]).as_json())

    def _head_uploads(self, owner: str, name: str, rest: list[str]) -> None:
        self._get_uploads(owner, name, rest)

    def _put_uploads(self, owner: str, name: str, rest: list[str]) -> None:
        if len(rest) != 1:
            raise Refused(HTTPStatus.NOT_FOUND, "not found")
        upload = self.renderer.upload_of(owner, rest[0])
        match = CONTENT_RANGE.match(self.headers.get("Content-Range", "").strip())
        if not match:
            raise Refused(HTTPStatus.BAD_REQUEST,
                          "a chunk needs Content-Range: bytes first-last/total")
        first, last, total = (int(x) for x in match.groups())
        body = self._read(CHUNK_MAX)
        received = self.renderer.write_chunk(upload, first, last, total, body)
        self._json({"id": upload.id, "received": received, "size": upload.size})

    def _delete_uploads(self, owner: str, name: str, rest: list[str]) -> None:
        if len(rest) != 1:
            raise Refused(HTTPStatus.NOT_FOUND, "not found")
        self.renderer.delete_upload(owner, rest[0])
        self._json({"deleted": rest[0]})

    def _post_jobs(self, owner: str, name: str, rest: list[str]) -> None:
        if rest:
            raise Refused(HTTPStatus.NOT_FOUND, "not found")
        job = self.renderer.create_job(owner, name, self._json_body())
        self._json(job.as_json(self.renderer.position(job)), HTTPStatus.ACCEPTED)

    def _get_jobs(self, owner: str, name: str, rest: list[str]) -> None:
        if not rest:
            # The caller's own jobs, so a client that lost track of one, because
            # its answer never arrived or the worker was stopped, can find it.
            return self._json({"jobs": [j.as_json(self.renderer.position(j))
                                        for j in self.renderer.jobs_of(owner)]})
        if len(rest) == 1:
            job = self.renderer.job_of(owner, rest[0])
            return self._json(job.as_json(self.renderer.position(job)))
        if len(rest) == 2 and rest[1] == "clip":
            return self._clip(self.renderer.job_of(owner, rest[0]))
        raise Refused(HTTPStatus.NOT_FOUND, "not found")

    def _head_jobs(self, owner: str, name: str, rest: list[str]) -> None:
        self._get_jobs(owner, name, rest)

    def _delete_jobs(self, owner: str, name: str, rest: list[str]) -> None:
        if len(rest) != 1:
            raise Refused(HTTPStatus.NOT_FOUND, "not found")
        job = self.renderer.cancel(owner, rest[0])
        self._json({"id": job.id, "state": job.state})

    def _clip(self, job: HostedJob) -> None:
        if job.state != DONE or not job.clip or not job.clip.is_file():
            raise Refused(HTTPStatus.CONFLICT, "the clip is not ready", state=job.state)
        size = job.clip.stat().st_size
        first, last, partial = 0, size - 1, False
        asked = RANGE.match((self.headers.get("Range") or "").strip())
        if asked:
            begin, end = asked.groups()
            if begin:
                first = int(begin)
                last = min(int(end), size - 1) if end else size - 1
            elif end:
                first = max(0, size - int(end))
            else:
                asked = None
            partial = asked is not None
            if partial and (first >= size or first > last):
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        length = last - first + 1
        self.send_response(HTTPStatus.PARTIAL_CONTENT if partial else HTTPStatus.OK)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition",
                         f'attachment; filename="{job.clip.name}"')
        if partial:
            self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with job.clip.open("rb") as handle:
            handle.seek(first)
            left = length
            while left > 0:
                chunk = handle.read(min(262_144, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)


def make_server(renderer: Renderer, port: int = DEFAULT_PORT,
                host: str = BIND) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"renderer": renderer})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


# -- command line ------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wastatus hosted",
        description="The renderer the browser extension uploads to.",
    )
    parser.add_argument("--data", type=Path, default=None,
                        help=f"where uploads, clips and tokens live (default "
                             f"${DATA_ENV} or {data_dir()})")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="answer the extension")
    serve.add_argument("--host", default=BIND)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument("--workers", type=int, default=None,
                       help=f"renders at once (default ${WORKERS_ENV} or 1)")
    serve.add_argument("-v", "--verbose", action="store_true")
    token = sub.add_parser("token", help="who may use it")
    actions = token.add_subparsers(dest="action", required=True)
    add = actions.add_parser("add", help="make a token and print it, once")
    add.add_argument("name")
    revoke = actions.add_parser("revoke", help="stop a token working")
    revoke.add_argument("name")
    actions.add_parser("list", help="names and when each was made")
    user = sub.add_parser("user", help="who may use the hosted page")
    user.add_argument("action", choices=("list", "approve", "decline", "suspend", "add",
                                         "forget"))
    user.add_argument("email", nargs="?")
    user.add_argument("--name", default="", help="for add: the person's name")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.data or data_dir()
    if args.command == "token":
        tokens = Tokens(root / "tokens.json")
        if args.action == "add":
            try:
                print(tokens.add(args.name))
            except ValueError as exc:
                print(f"error: {exc}")
                return 1
            return 0
        if args.action == "revoke":
            if not tokens.revoke(args.name):
                print(f"error: no token called {args.name}")
                return 1
            return 0
        for entry in tokens.names():
            print(f"{entry.get('name')}\t{entry.get('created')}")
        return 0
    if args.command == "user":
        from . import portal
        return portal.user_command(root, args.action, args.email, args.name)

    runlog.stamp(runlog.setup(args.verbose))
    workers = args.workers or int(os.environ.get(WORKERS_ENV) or 1)
    renderer = Renderer(root, workers=workers)
    # The site (SnipShare's pages and the per-person page API) answers on the same
    # port as the renderer's own API, which it extends rather than replaces: the
    # popup's tokens work exactly as they did.
    from . import portal, watch
    site = portal.Portal(root, renderer)
    try:
        server = portal.make_server(site, args.port, args.host)
    except OSError as exc:
        print(f"error: cannot listen on {args.host}:{args.port} ({exc})")
        return 1
    renderer.start()
    watcher = watch.Watch(site)
    watcher.start()
    print(f"wastatus hosted renderer on http://{args.host}:{server.server_address[1]}"
          f"{API}, {workers} worker(s), data in {root}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        watcher.stop()
        renderer.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
