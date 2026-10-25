"""The local page: the same pipeline behind a form instead of a command line.

`wastatus serve` opens a one page interface on loopback. It runs the identical
`pipeline.produce` the command line runs, and posts through the identical
`post.post_video`, so there is one engine and two ways to reach it.

The standard library is enough for this, and a single user tool that lives for the
length of a session does not need a web framework in `requirements.txt`.

**Why the token.** Any page in any tab can POST to `http://127.0.0.1:8765`. Without
a guard, a website could make this tool post to a WhatsApp Status. Every `/api/`
call therefore needs an `X-Wastatus-Token` header carrying a per process secret
that only the served page knows, and a custom header cannot be set on a
cross-origin request without a preflight this server refuses.

The two media endpoints also accept the token as a `t` query parameter, because an
`<img>` or `<video>` cannot send a header. They are read only, and a page that
cannot read the token cannot build the URL.

They also answer byte ranges. A `<video>` seeks by asking for a range, so a server
that always returns the whole file gives you a slider that does nothing.
"""

from __future__ import annotations

import argparse
import io
import ipaddress
import json
import logging
import math
import mimetypes
import os
import re
import secrets
import socket
import subprocess
import shutil
import tempfile
import threading
import time
import uuid
import webbrowser
from urllib.parse import unquote_plus
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from PIL import Image

from . import (compose, fetch, freetext, gifs, label, pipeline, post, potoken,
               proc, render, retention, runlog, sheet, stickers)
from .pipeline import Job
from .timecode import TimecodeError

log = logging.getLogger("wastatus")

DEFAULT_PORT = 8765
BIND = "127.0.0.1"

# Two settings a person would otherwise retype on every start. They live in `.env`
# rather than in the code because both are facts about one machine: whether there
# is a tailnet to be reached over, and whether posting is wanted at all. Off is
# still the default, so a fresh clone binds loopback only and starts nothing.
# DECISIONS.md D-044.
ALSO_ON_ENV = "WASTATUS_ALSO_ON"
BROWSER_ENV = "WASTATUS_START_BROWSER"
TRUE = ("1", "true", "yes", "on")
WEB_DIR = Path(__file__).resolve().parent / "web"

# The largest request body that will be read into memory. The biggest legitimate one
# is an animated sticker as base64, about 10.7 MB at `stickers.ANIMATED_MAX_BYTES`.
MAX_BODY_BYTES = 12_000_000
TOKEN_HEADER = "X-Wastatus-Token"

# Output stems are `20260818_song-slug_20-50` plus an optional `_video` and a `-2`
# collision suffix. Nothing else may address a file through this server.
SAFE_STEM = re.compile(r"^[A-Za-z0-9_-]{1,120}$")

# `bytes=0-`, `bytes=500-999`, `bytes=-1024`. One range is all a media element asks
# for; multipart ranges are legal HTTP that no player needs.
RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")
MEDIA_CHUNK = 256 * 1024

# A caption is a line or two under a video, not an essay. This is our own ceiling,
# well inside anything WhatsApp itself would refuse.
CAPTION_MAX = 1024
URL_MAX = 2048


# A path on this machine, such as `/data/users/<id>/work/clip.mp4`: never part of a
# URL, which is why a slash after a letter, a colon, a dot or another slash is not one.
_PATH = re.compile(r"(?<![\w:/.~-])/(?:[^\s/'\"]+/)+[^\s'\":,;)]*")


def plain_error(exc: BaseException) -> str:
    """What went wrong, in words fit to show the person: the first line, with any
    path on this machine taken out. The whole of it goes to the log."""
    text = (str(exc).strip() or type(exc).__name__).splitlines()[0]
    return _PATH.sub("a file", text)[:300]


BODY_METHODS = ("POST", "PUT", "DELETE")


def refuse_ambiguous_body(handler: BaseHTTPRequestHandler) -> bool:
    """Answer 400 and end the connection for a request whose body could be read two
    ways, or that carries one where none is read: two Content-Length headers, one
    beside Transfer-Encoding, or a body on any method but POST, PUT and DELETE.
    Each leaves bytes another reader could take for the next request (D-101).
    True when it answered."""
    lengths = handler.headers.get_all("Content-Length") or []
    encoded = handler.headers.get("Transfer-Encoding")
    carries = encoded or any(value.strip() not in ("", "0") for value in lengths)
    if len(lengths) > 1 or (lengths and encoded) or (carries and handler.command not in BODY_METHODS):
        handler.close_connection = True
        handler.send_error(HTTPStatus.BAD_REQUEST, "that request's body cannot be read one way")
        return True
    return False


def _words_of(body: dict[str, Any], key: str) -> str:
    """One line of a card's words from a request, trimmed and held to CAPTION_MAX."""
    return str(body.get(key) or "").strip()[:CAPTION_MAX].strip()

TOKEN_IN_URL = re.compile(r"t=[A-Za-z0-9_-]+")


@dataclass
class Task:
    """One unit of work the page is waiting on: a render or a post."""

    id: str
    kind: str  # "render" or "post"
    status: str = "running"  # running, done, failed
    stage: str = ""
    message: str = ""
    error: str = ""
    started: float = field(default_factory=time.monotonic)
    finished: float | None = None
    result: dict[str, Any] = field(default_factory=dict)
    # The thread doing the work, which is the handle `proc.cancel` needs, and a
    # flag for a stop that arrives before that thread has started.
    thread: int | None = None
    stopping: bool = False

    @property
    def elapsed(self) -> float:
        return (self.finished or time.monotonic()) - self.started

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "stage": self.stage,
            "message": self.message,
            "error": self.error,
            "elapsed": round(self.elapsed, 1),
            "stages": list(pipeline.STAGES),
            "result": self.result,
            # Only a render can be stopped, and only while it is still going.
            "can_stop": self.kind == "render" and self.status == "running",
        }


class App:
    """Everything the handler needs, so the handler itself stays thin."""

    def __init__(
        self, out: Path, cdp_port: int, keep_last: int, also_on: str = ""
    ) -> None:
        self.out = out
        self.cdp_port = cdp_port
        self.keep_last = keep_last
        # A second address the page is reachable at, for the footer to name. The
        # server always listens on loopback as well; see `main`.
        self.also_on = also_on
        # The port the page itself ended up on, filled in by `main` once the socket
        # is bound. Only the label needs it, and only a real port is worth naming:
        # `--port 0` means the number is not known until the bind has happened.
        self.page_port: int | None = None
        self.token = secrets.token_urlsafe(24)
        self.tasks: dict[str, Task] = {}
        self.lock = threading.RLock()  # reentrant: `post_clip` holds it across `start`
        self._whatsapp: tuple[float, dict[str, Any]] | None = None
        # Asked once and remembered: WhatsApp does not rename a control between two
        # clips, and the check opens a menu in a window the owner may be looking at,
        # so it is worth exactly one flicker per run. TASKS.md T-026.
        self._controls: dict[str, Any] | None = None
        # Set while the controls check is reaching into the WhatsApp tab, so a post
        # never starts driving the same tab at the same time.
        self._checking = threading.Event()
        # The last search's results, by id. A pick names one of these; it never
        # sends a url. So this process only ever downloads addresses a provider
        # gave it, and a caller holding the token cannot point it at anything else.
        self._offered: dict[str, Any] = {}

    # A page left open for a week should not accumulate every task it ever ran.
    KEEP_TASKS = 50
    # The page polls its health. Probing several debug ports on every poll would
    # hammer the browser for an answer that changes when you open a tab, not every
    # fifteen seconds.
    WHATSAPP_TTL = 8.0

    # -- tasks ------------------------------------------------------------

    def start(self, kind: str, work: Any) -> Task:
        task = Task(id=uuid.uuid4().hex[:12], kind=kind)
        with self.lock:
            self.tasks[task.id] = task
            for stale in list(self.tasks)[:-self.KEEP_TASKS]:
                del self.tasks[stale]
        thread = threading.Thread(target=self._run, args=(task, work), daemon=True)
        thread.start()
        return task

    def running(self, *kinds: str) -> Task | None:
        """A task of one of these kinds that has not finished, if there is one."""
        with self.lock:
            return self._running(*kinds)

    def _running(self, *kinds: str) -> Task | None:
        for task in self.tasks.values():
            if task.kind in kinds and task.status == "running":
                return task
        return None

    def _run(self, task: Task, work: Any) -> None:
        with proc.cancellable() as ident:
            task.thread = ident
            try:
                # Stopped between `start` registering the task and this thread
                # getting a slot. Rare, and the alternative is a render nobody wants.
                if task.stopping:
                    raise proc.Cancelled("stopped before it started")
                task.result = work(task)
                task.status = "done"
            except proc.Cancelled:
                task.status = "cancelled"
                task.stage, task.message = "", "stopped"
                log.info("%s task stopped on request", task.kind)
            except Exception as exc:  # noqa: BLE001 - the page shows what went wrong
                log.exception("%s task failed", task.kind)
                task.status = "failed"
                task.error = plain_error(exc)
            finally:
                task.finished = time.monotonic()
                task.thread = None

    def cancel(self, task_id: str) -> Task:
        """Stop a render. Posting is deliberately not cancellable: killing a
        driver halfway through an upload leaves WhatsApp in a state this tool
        cannot describe, let alone undo."""
        with self.lock:
            task = self.tasks.get(task_id)
            if task is None:
                raise KeyError(task_id)
            if task.kind != "render":
                raise ValueError(f"a {task.kind} cannot be stopped once it is running")
            if task.status != "running":
                raise ValueError(f"that one has already {task.status}")
            task.stopping = True
            ident = task.thread
        if ident is not None:
            proc.cancel(ident)
        return task

    def render(self, job: Job, follow_up: bool) -> Task:
        def work(task: Task) -> dict[str, Any]:
            run = runlog.Run(
                log, url=job.url, start=job.start, end=job.end,
                duration=job.duration, mode=job.mode, source="web",
                post=False, follow_up=follow_up,
            )

            def progress(stage: str, message: str) -> None:
                task.stage, task.message = stage, message

            try:
                result = pipeline.produce(job, run, progress=progress)
            except proc.Cancelled:
                run.finish("cancelled")
                raise
            except Exception as exc:
                run.finish("failed", error=f"{type(exc).__name__}: {exc}")
                raise
            run.finish("ok")

            if follow_up:
                (job.out / f"{result.stem}.status2.txt").write_text(
                    result.caption + "\n", encoding="utf-8"
                )
            return self.clip_json(result.stem) or {}

        # One render at a time: the page refuses a second press itself, and this is
        # the guard for every other caller, checked and registered under one lock.
        with self.lock:
            if self._running("render"):
                raise RuntimeError("a clip is already being made. Wait for it, or stop it")
            return self.start("render", work)

    def post_clip(self, stem: str, follow_up: bool, send: bool = False) -> Task:
        """Load the clip into WhatsApp, and send it only if asked to.

        Sending is the last step and it is the irreversible one, so the page's
        default is to stop with the composer loaded and let the owner press Send.
        """
        clip = self.out / f"{stem}.mp4"
        caption_file = self.out / f"{stem}.caption.txt"
        if not clip.is_file():
            raise FileNotFoundError(f"no clip called {stem}")
        caption = (
            caption_file.read_text(encoding="utf-8").strip()
            if caption_file.is_file() else ""
        )

        def work(task: Task) -> dict[str, Any]:
            with retention.hold(clip):
                return drive(task)

        def drive(task: Task) -> dict[str, Any]:
            # A posting run gets its own record in `runs.jsonl`, the same as a
            # render does. Without one, "when did that go out, and through which
            # browser" was answerable for a clip made at the command line and not
            # for one posted from the page, which is the route actually used.
            run = runlog.Run(
                log, stem=stem, source="web", kind="post" if send else "load",
                follow_up=follow_up,
            )
            try:
                found = post.discover(self.cdp_port)
                run.set(port=found.port, browser=found.browser)
                if send:
                    task.stage, task.message = "upload", "uploading to your Status"
                else:
                    task.stage, task.message = "load", "loading it into the composer"
                with run.stage("post_video"):
                    if send:
                        # Retries a refusal, and only a refusal: see
                        # `post.send_with_retry`. The page's stage line says so
                        # while it waits, rather than looking like a hang.
                        def announce(attempt, delay, _exc, task=task):
                            task.message = (
                                f"WhatsApp refused it. Trying again in {delay:.0f}s "
                                f"(attempt {attempt + 1})"
                            )

                        took = post.send_with_retry(
                            clip, caption, port=found.port, on_retry=announce,
                        )
                    else:
                        took = post.post_video(clip, caption, port=found.port, send=False)
                done = {
                    "seconds": round(took or 0.0, 1),
                    "follow_up": False,
                    "sent": send,
                    "port": found.port,
                }
            except Exception as exc:
                run.finish("failed", error=f"{type(exc).__name__}: {exc}")
                self._whatsapp = None  # it may have got as far as opening a composer
                raise
            log.info(
                "%s %s through %s%s",
                "posted" if send else "loaded",
                stem,
                found.detail,
                f" in {took:.0f}s" if took else "",
            )
            # The video's row is written the moment WhatsApp acknowledged it, before
            # anything else can fail: from here on it is a Status that went out.
            if send:
                self._record_in_sheet(stem, clip, took, found.browser)
            if send and follow_up:
                # A failure here is the text's alone. The video is live, so the
                # task is not failed, and nothing invites sending the video again.
                task.stage, task.message = "follow_up", "posting the link as text"
                try:
                    with run.stage("post_text"):
                        second = post.send_text_with_retry(
                            caption, port=found.port, on_retry=announce)
                    done["follow_up"] = True
                    # It is a Status this tool published, so it gets its own row.
                    self._record_in_sheet(stem, clip, second, found.browser,
                                          note="follow up text")
                except Exception as exc:  # noqa: BLE001 - reported beside the video
                    log.exception("the follow up text for %s failed", stem)
                    done["follow_up_error"] = plain_error(exc)
            run.finish("ok", seconds=done["seconds"], sent=send)
            self._whatsapp = None  # a composer is open or a Status just went out
            return done

        # The composer takes several files at once and sends all of them, so two
        # overlapping attempts are how one command posts two Statuses. It happened.
        # Checking and registering under one lock, because two requests arriving
        # together would otherwise both find nothing running.
        # A controls check in flight is short: wait for it rather than refuse the
        # press, then decide under the lock, where no new check can begin.
        deadline = time.monotonic() + 30
        while True:
            with self.lock:
                if self._running("post", "prepare"):
                    raise RuntimeError(
                        "WhatsApp is already being driven by another request. "
                        "Finish or cancel that one first"
                    )
                if not self._checking.is_set():
                    return self.start("post" if send else "prepare", work)
            if time.monotonic() > deadline:
                raise RuntimeError("WhatsApp is still being checked. Try again in a moment")
            time.sleep(0.25)

    def words_from(self, url: str) -> dict[str, str]:
        """What a video calls itself, cleaned the way the card would clean it.

        Not a task: there is nothing to report progress about and nothing to stop,
        and a page that has to poll for two strings is more moving parts than the
        two strings are worth. It is one yt-dlp call on this request's own thread,
        which the threading server is already built for, under a timeout short
        enough that a button cannot spin for five minutes. See D-064.
        """
        source = fetch.probe(url, timeout=fetch.PROBE_TIMEOUT)
        title, channel = pipeline.words_from_video(source)
        return {"title": title, "channel": channel}

    def save_caption(self, stem: str, caption: str) -> str:
        """Rewrite a clip's caption. The caption is text, not pixels, so this is
        free: nothing has to be rendered again."""
        if not (self.out / f"{stem}.mp4").is_file():
            raise FileNotFoundError(f"no clip called {stem}")
        text = caption.replace("\r\n", "\n").strip()
        if len(text) > CAPTION_MAX:
            raise ValueError(f"a caption over {CAPTION_MAX} characters is too long")
        (self.out / f"{stem}.caption.txt").write_text(text + "\n", encoding="utf-8")
        return text

    def delete_clip(self, stem: str) -> dict[str, Any]:
        """Delete a clip and everything that belongs with it.

        The group, not the file: `retention` already knows what a clip's sidecars
        are, and deleting the mp4 alone would leave a caption and a still behind
        that nothing would ever clean up.
        """
        if not (self.out / f"{stem}.mp4").is_file():
            raise FileNotFoundError(f"no clip called {stem}")
        with self.lock:
            # A composer may be holding this very file open.
            if self._running("post", "prepare"):
                raise RuntimeError(
                    "WhatsApp is being driven right now. Wait for that to finish"
                )
        files = retention.group_files(self.out, stem)
        freed = sum(path.stat().st_size for path in files)
        for path in files:
            path.unlink()
        log.info("deleted %s: %d files, %.1f MB", stem, len(files), freed / 1_000_000)
        return {
            "deleted": stem,
            "files": len(files),
            "mb": round(freed / 1_000_000, 1),
        }

    # The preview is judged on a screen 300 pixels wide, and on a phone it arrives
    # over a tailnet. A full size PNG of it measured 1254 kB for a card and 694 kB
    # for a video frame, which is twenty times more picture than the box it goes in
    # and is redrawn every time a key stops moving. JPEG at this width is 40 to 90.
    PREVIEW_WIDTH = 720
    PREVIEW_QUALITY = 86
    # A placed line is drawn once at this width and scaled into whatever box it is
    # dragged to, so it only has to be wider than the frame ever is on screen. The
    # renderer draws its own copy at the frame's true scale; see `freetext`.
    TEXT_WIDTH = 720

    def picture_of(self, stem: str) -> "render.Picture | None":
        """Where this clip's picture landed, as a rectangle, or None if unrecorded.

        The video's frames in video mode and the artwork panel in card mode, and in
        both only for clips made since it was written down. Video mode cannot change
        the background under the picture without it, because there is no way to say
        which pixels are the picture; both modes need it to draw a box around
        something whose shape is otherwise unmeasurable from the page.
        """
        raw = self.job_of(stem).get("picture")
        if not isinstance(raw, dict):
            return None
        try:
            box = render.Picture(
                width=int(raw["width"]), height=int(raw["height"]),
                left=int(raw["left"]), top=int(raw["top"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
        return box if box.width > 0 and box.height > 0 else None

    def framing_of(self, stem: str) -> "render.Framing | None":
        """How this clip's picture was placed, or None if it was fitted as usual."""
        try:
            return render.parse_framing(self.job_of(stem).get("framing"))
        except ValueError:
            return None

    def fill_of(self, stem: str) -> str:
        """What this clip was made with. Everything older than the choice is blurred."""
        found = self.job_of(stem).get("fill")
        return found if found in render.FILLS else render.BLUR

    def preview_jpeg(self, stem: str, words: compose.CardText,
                     fill: str | None = None,
                     framing: "render.Framing | None" = None) -> bytes:
        """The clip's own picture with these words on it, as a JPEG.

        **Pillow only. No ffmpeg, no download, nothing re-encoded.** Measured on the
        owner's machine: 0.66s for a card and 0.05s for a video overlay, against 30
        to 66 seconds to make the clip again. That is the whole point of it, T-036.

        The two modes need different things kept, and neither is the finished clip:

        * **card** keeps the artwork, and the card is simply built again. The same
          `build_card` the render calls, so the preview cannot drift from the clip,
          and a placed panel costs nothing extra: it is an argument to that call.
        * **video** keeps one frame of the video with nothing of ours on it, and the
          text layer is composited over it exactly as ffmpeg composites it.

        No stickers are drawn. The page is already drawing them over the top as
        movable things, and drawing them here as well would show each one twice.
        """
        art = self.out / f"{stem}.art.jpg"
        base = self.out / f"{stem}.base.png"
        if not (self.out / f"{stem}.mp4").is_file():
            raise FileNotFoundError(f"no clip called {stem}")

        if art.is_file():
            # The artwork is kept, so card mode has no background it cannot draw:
            # the card is simply built again, with the placement being asked about
            # or, when none is, the one the clip itself was made with. Passing None
            # straight through would preview a fitted card for a placed clip.
            with tempfile.TemporaryDirectory(prefix="wastatus-preview-") as tmp:
                made = compose.build_card(
                    art, words, Path(tmp) / "card.png",
                    framing=framing if framing is not None else self.framing_of(stem),
                )
                return self._shrink(Image.open(made).convert("RGB"))
        if base.is_file():
            # Where the frames landed, recorded when the clip was made. Without it
            # the top text would be drawn against the top of the band rather than
            # against the picture, and the preview would put it somewhere the clip
            # does not. A clip made before this was recorded has no answer, and the
            # fallback is where that clip's own text actually is.
            # `job_of`, not `clip_json`: the latter can return None, and it also
            # re-stats the mp4 and reads the caption to hand back one key of it.
            picture_top = self.job_of(stem).get("picture_top")
            with tempfile.TemporaryDirectory(prefix="wastatus-preview-") as tmp:
                # Where the picture ends as well as where it starts: a placed one
                # can reach down over the row the label lands on, and the label
                # then needs a scrim under it to be readable. D-075.
                placed_rect = self.picture_of(stem)
                layer = compose.build_overlay(
                    words, Path(tmp) / "over.png",
                    picture_top=picture_top if isinstance(picture_top, int) else None,
                    picture_bottom=(placed_rect.top + placed_rect.height
                                    if placed_rect is not None else None),
                )
                picture = Image.open(base).convert("RGBA")
                # The background is under everything, so showing a different one
                # means building the frame again rather than drawing over it. Only
                # possible where the picture's rectangle was recorded.
                rect = self.picture_of(stem)
                if rect is not None and self.rebuilt(stem, fill, framing):
                    picture = render.recompose(
                        picture, rect, fill or self.fill_of(stem),
                        to=self.aimed_at(rect, framing),
                    )
                return self._shrink(Image.alpha_composite(
                    picture, Image.open(layer).convert("RGBA")
                ).convert("RGB"))
        raise FileNotFoundError(
            "this clip was made before the live preview existed, so there is no "
            "picture to draw on. Make it again and the preview will work"
        )

    def dropped_lines(self, stem: str, words: compose.CardText,
                      framing: "render.Framing | None" = None) -> int:
        """How many lines of top text this clip cannot draw. Zero when it all fits.

        Asked because the alternative is what the tool used to do: wrap the block to
        the room above the artwork, find the room is nothing, draw nothing, and say
        nothing. The words stayed in the box and went into the sidecar, so the page
        then compared them against themselves and reported the clip up to date with
        a line it had never drawn. See DECISIONS.md D-075.

        Only a card can run out of room, and now only a **placed** one: video mode
        moves its picture down and a fitted card shrinks. So this is the answer to
        "you have pinned the artwork too high for the line you just typed".
        """
        if not (self.out / f"{stem}.art.jpg").is_file():
            return 0                       # video mode never drops one
        placed = framing if framing is not None else self.framing_of(stem)
        try:
            top = compose.card_rect(self.card_aspect_of(stem), placed, words)[1]
        except (OSError, ValueError):
            return 0                       # no artwork to measure: nothing to promise
        return compose.topline_dropped(words, video=False, top=top)

    def card_aspect_of(self, stem: str) -> float:
        """This clip's artwork shape, or a square when there is no artwork kept."""
        art = self.out / f"{stem}.art.jpg"
        return compose.card_aspect(art) if art.is_file() else 1.0

    def moving_band(
        self, stem: str, words: compose.CardText, fill: str | None = None,
        framing: "render.Framing | None" = None,
    ) -> tuple[float, float] | None:
        """Which rows of the frame move, as fractions of its height.

        The preview is a still, and laying a still over the whole frame froze the
        clip: press play and the picture sat there while the audio ran. But the
        preview only ever redraws **text**, and both layouts keep text off the part
        of the frame that moves, on purpose. So the still can be cut open over
        exactly that part and the clip plays through its own new words, with the old
        ones covered by the same still that carries the new.

        * **card**: the waveform. A card is one still picture; the waveform is the
          only thing ffmpeg animates on it, and it sits below everything drawn.
        * **video**: the band the frames were fitted into. `picture_top` is where
          they landed, recorded when the clip was made, and `video_picture_bottom`
          is the row the words begin at, which is at or below the picture's own
          bottom edge. Cutting to the lower of the two can only expose more blurred
          fill, never a letter.

        Both come from the functions the render itself used, so the hole cannot
        drift into the words. None when there is no picture to preview at all.
        """
        # A still showing a frame the clip was not made with cannot be cut open: the
        # clip would play its old background, or its picture in the old place,
        # through the hole, and the seam would run across the picture.
        if self.rebuilt(stem, fill, framing):
            return None
        if (self.out / f"{stem}.art.jpg").is_file():
            top, bottom = compose.WAVE_TOP, compose.WAVE_TOP + compose.WAVE_H
        elif (self.out / f"{stem}.base.png").is_file():
            # Measured off the **words**, not off the picture. The rule is only that
            # the hole may not open onto a letter, and the top line is the one thing
            # ever drawn above the frames: without one the hole starts at the very
            # top of the frame, with one it starts just below the block. Reading the
            # picture's own top edge here was wrong twice over: it froze the blurred
            # strip under WhatsApp's header for no reason, and a picture somebody
            # placed themselves can start above the frame, where a negative row made
            # this refuse to answer at all and the clip stopped playing under a still
            # that covered it. The anchor is the one `build_overlay` was given, so
            # the block is measured where it is actually drawn.
            lines = compose.topline_lines(words.topline)
            recorded = self.job_of(stem).get("picture_top")
            anchor = (
                recorded if isinstance(recorded, int)
                else compose.video_picture_top(words)
            )
            top = (compose.topline_top(anchor, lines) + compose.topline_height(lines)
                   if lines else 0)
            bottom = compose.video_picture_bottom(words)
        else:
            return None
        top, bottom = max(0, top), min(compose.HEIGHT, bottom)
        if top >= bottom:
            return None
        # Rounded inwards, both ends. Four decimals of a 1920 pixel frame is a fifth
        # of a pixel and nobody can see it, but rounding the wrong way would let the
        # hole reach a row the words are drawn on, and this whole thing rests on it
        # not doing that.
        return (
            math.ceil(top / compose.HEIGHT * 10_000) / 10_000,
            math.floor(bottom / compose.HEIGHT * 10_000) / 10_000,
        )

    def aimed_at(self, rect: "render.Picture",
                 framing: "render.Framing | None") -> "render.Picture | None":
        """The rectangle a placement resolves to, measured off this clip's own.

        The source video is long gone by the time anybody drags anything, and its
        shape is the one thing a placement needs. The rectangle that was recorded
        carries it: that picture is the source, scaled, so its own proportions are
        the source's proportions.
        """
        if framing is None:
            return None
        return render.placed_rect((rect.width, rect.height), framing)

    def rebuilt(self, stem: str, fill: str | None,
                framing: "render.Framing | None") -> bool:
        """Is the frame being asked for a different one from the clip's own?

        One question, asked in two places: what to draw, and whether the still may
        be cut open over the moving band. They cannot be allowed to disagree.
        """
        card = (self.out / f"{stem}.art.jpg").is_file()
        # The background is video mode's alone: a card composes its own and never
        # reads the choice. Answering yes to it for a card clip would freeze the
        # preview over a still identical to the one already playing.
        if not card and fill and fill != self.fill_of(stem):
            return True
        if framing is None:
            return False
        if not card and self.picture_of(stem) is None:
            # Nothing that knows where the picture is. Saying yes here would answer
            # with a still identical to the clip and no hole to play through, which
            # is a frame that has stopped for no reason. Card mode never lands here:
            # it kept the artwork, so it can always draw the card again.
            return False
        return framing != self.framing_of(stem)

    def _shrink(self, picture: Image.Image) -> bytes:
        if picture.width > self.PREVIEW_WIDTH:
            height = round(picture.height * self.PREVIEW_WIDTH / picture.width)
            picture = picture.resize(
                (self.PREVIEW_WIDTH, height), Image.LANCZOS
            )
        buffer = io.BytesIO()
        picture.save(buffer, "JPEG", quality=self.PREVIEW_QUALITY, optimize=True)
        return buffer.getvalue()

    def start_browser(self, page_url: str = "") -> dict[str, Any]:
        """Start a browser we can post through, since Chrome only exposes the
        protocol when it is asked to at launch.

        The preferred port is only a preference. Starting a second browser on a
        port something else already holds is the half open case in `post`: Chrome
        says it is listening, on IPv6 only, and nothing can reach it. So a taken
        port is stepped over rather than argued with, and the port that was
        actually used becomes this session's preference.
        """
        # A browser already open on this profile is the browser to use, whatever
        # port was preferred: a second launch on the same profile is handed to the
        # first one and starts nothing. Preferring it by port is enough for
        # `discover`, which always tries the preferred port first.
        already = post.running_profile_port()
        if already is not None:
            self.cdp_port = already
            self._whatsapp = None
            self._controls = None
            if self.whatsapp_state(fresh=True)["ready"]:
                return {"binary": "", "port": already, "adopted": True,
                        "profile": str(post.profile_dir())}
            raise post.PostError(
                f"a browser is already open on the posting profile, on port "
                f"{already}, but WhatsApp Web is not open in it. Open "
                "https://web.whatsapp.com in that window"
            )
        port = self.cdp_port if not post.in_use(self.cdp_port) else post.free_port()
        exe = post.launch_browser(port, first=self.label(port), page=page_url)
        self.cdp_port = port
        self._whatsapp = None
        self._controls = None
        return {"binary": exe, "port": port, "profile": str(post.profile_dir())}

    def label(self, cdp_port: int) -> Path | None:
        """Write the tab that names this session's ports, or None if it cannot.

        Never fatal, and never allowed to stop a browser starting: a label that
        could not be written is a cache directory problem, and the tool works
        perfectly without one.
        """
        if self.page_port is None:
            return None
        try:
            return label.write(
                port=self.page_port,
                url=url_for(BIND, self.page_port),
                cdp_port=cdp_port,
                profile=str(post.profile_dir()),
                out=str(self.out.resolve()),
                also_on=url_for(self.also_on, self.page_port) if self.also_on else "",
            )
        except OSError as exc:
            log.warning("no session label written: %s", exc)
            return None

    # -- reading the output folder ---------------------------------------

    def _record_in_sheet(self, stem: str, clip: Path, took: float | None,
                         browser: str, note: str = "") -> None:
        """Add the row for a Status that went out. Silent when no sheet is set up.

        Only ever reached after WhatsApp accepted it, which is what makes the row
        honest. A refusal that survived every retry raises before this line.
        """
        sheet.record(clip=clip, stem=stem, seconds=took, browser=browser,
                     note=note)

    def clip_json(self, stem: str) -> dict[str, Any] | None:
        clip = self.out / f"{stem}.mp4"
        if not clip.is_file():
            return None
        caption = self.out / f"{stem}.caption.txt"
        frame = self.out / f"{stem}.png"
        job = self.job_of(stem)
        return {
            "stem": stem,
            "name": _name_from_stem(stem),
            # The sidecar knows, and it is the job that was actually run. The name
            # is only the fallback, for a clip made before sidecars existed.
            "video": bool(job["video"]) if "video" in job else _is_video(stem),
            "window": _window_from_stem(stem),
            "size_mb": round(clip.stat().st_size / 1_000_000, 1),
            "created": clip.stat().st_mtime,
            "caption": (
                caption.read_text(encoding="utf-8").strip()
                if caption.is_file() else ""
            ),
            "has_frame": frame.is_file(),
            # Everything needed to put this clip back in the form and re-make it.
            "job": job,
            "title": job.get("title", ""),
            "channel": job.get("channel", ""),
        }

    def job_of(self, stem: str) -> dict[str, Any]:
        """The sidecar `pipeline.produce` leaves behind. Absent for older clips."""
        file = self.out / f"{stem}.json"
        if not file.is_file():
            return {}
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            log.debug("unreadable job sidecar for %s", stem)
            return {}
        return data if isinstance(data, dict) else {}

    def clips(self, limit: int = 12) -> list[dict[str, Any]]:
        if not self.out.is_dir():
            return []
        # A clip deleted or pruned while this sorts counts as oldest, then drops
        # out at `clip_json`, rather than failing the whole list.
        stems = sorted(
            (p.stem for p in self.out.glob("*.mp4")),
            key=lambda s: retention.mtime(self.out / f"{s}.mp4"),
            reverse=True,
        )
        found = []
        for stem in stems[:limit]:
            try:
                clip = self.clip_json(stem)
            except FileNotFoundError:
                continue
            if clip:
                found.append(clip)
        return found

    # -- environment ------------------------------------------------------

    def state(self, fresh: bool = False) -> dict[str, Any]:
        return {
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "provider": (potoken.install_dir() / "server" / "package.json").is_file(),
            "whatsapp": self.whatsapp_state(fresh=fresh),
            "out": str(self.out),
            # Which machine this is. From a phone, "WhatsApp Web is ready" begs the
            # question "on what", and the answer is the laptop you left in the other
            # room, by the name it calls itself.
            "host": socket.gethostname(),
            "cdp_port": self.cdp_port,
            "max_duration": pipeline.MAX_DURATION,
            # What can go behind the frames. From the renderer, so a page cannot
            # offer a background this server would refuse.
            "fills": list(render.FILLS),
            "stickers": stickers.installed(),
            # The two bands WhatsApp draws over, as fractions of the frame, so the
            # page's guides and the renderer's safe zone cannot drift apart.
            "bands": {
                "top": round(compose.SAFE_TOP / compose.HEIGHT, 4),
                "bottom": round(1 - compose.SAFE_BOTTOM / compose.HEIGHT, 4),
            },
            "keep_last": self.keep_last,
            "busy": bool(self.running("post", "prepare")),
            "also_on": self.also_on,
            # Empty when the feature is off, which is how the page knows not to
            # draw the toggle at all rather than drawing one that cannot answer.
            "gifs": gifs.credit(),
            "clips": self.clips(),
        }

    def remember_gifs(self, found: list) -> None:
        with self.lock:
            # By the name the page uses, which carries the provider: a search of both
            # services can hold two results with the same id.
            self._offered = {one.key: one for one in found}

    def offered_gif(self, ident: str):
        with self.lock:
            return self._offered.get(ident)

    def controls_state(self, fresh: bool = False) -> dict[str, Any]:
        """Whether WhatsApp's Status controls are still where `post` expects them.

        Never runs on the fifteen second poll, only when the page asks, and the page
        asks once: when a clip first becomes postable. See T-026, and D-041 for what
        made it worth asking at all.
        """
        if not fresh and self._controls is not None:
            return self._controls
        busy = {"ok": True, "checked": False, "detail": "WhatsApp is busy"}
        with self.lock:
            if self._running("post", "prepare") or self._checking.is_set():
                # Something is already driving that browser. Do not reach into it,
                # and do not cache a non answer.
                return busy
            self._checking.set()
        try:
            self._controls = post.check_controls(self.cdp_port)
        finally:
            self._checking.clear()
        return self._controls

    def whatsapp_state(self, fresh: bool = False) -> dict[str, Any]:
        """Whether posting will work, so the page can say so before you try."""
        now = time.monotonic()
        cached = self._whatsapp
        if not fresh and cached and now - cached[0] < self.WHATSAPP_TTL:
            return cached[1]
        try:
            found = post.discover(self.cdp_port)
        except post.PostError as exc:
            state = {
                "ready": False,
                "detail": str(exc),
                "port": None,
                "can_launch": post.chrome_binary() is not None,
            }
        else:
            state = {
                "ready": True,
                "detail": found.detail,
                "port": found.port,
                "can_launch": True,
            }
        self._whatsapp = (now, state)
        return state


def _clock(seconds: float) -> str:
    """`80` reads as `1:20`. `timecode.format_timecode` is for ffmpeg, not people."""
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


# `20260818_song_70-85`, or `..._70-85-2` once a name has collided.
# `..._190-280_video-2`: the marker comes first, then the suffix that separates a
# second take of the same window. Both are optional and both must be allowed for,
# because a stem carrying the pair ends in neither one alone. Reading the marker off
# the end with `removesuffix` missed it, and such a clip lost its window in the panel
# and was labelled an artwork card. Found 2026-08-25.
_WINDOW = re.compile(r"_(\d+)-(\d+)(?:_video)?(?:-\d+)?$")


def _is_video(stem: str) -> bool:
    """Video mode, read off the name. Only for clips with no sidecar to ask."""
    return bool(re.search(r"_video(?:-\d+)?$", stem))


def _window_from_stem(stem: str) -> str:
    """`20260818_song_20-50` reads back as `0:20 to 0:50`."""
    found = _WINDOW.search(stem)
    if not found:
        return ""
    start, end = (float(value) for value in found.groups())
    return f"{_clock(start)} to {_clock(end)}"


_ROMAN_WORD = re.compile(r"^(?:i{1,3}|iv|vi{0,3}|ix|xi{0,3}|x)$", re.IGNORECASE)


def _name_from_stem(stem: str) -> str:
    """The song, as a person would read it back. `vol ii` keeps its numeral."""
    parts = stem.removesuffix("_video").split("_")
    slug = parts[1] if len(parts) > 2 else stem
    words = slug.replace("-", " ").strip().split()
    return " ".join(
        word.upper() if _ROMAN_WORD.match(word) else word.title() for word in words
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "wastatus"
    # Keep-alive, so playing a clip does not open a socket per byte range. Every
    # response here sends a Content-Length, which HTTP/1.1 requires.
    protocol_version = "HTTP/1.1"
    # And close a connection nobody is using, rather than holding a thread for it.
    # This is a socket timeout, so it bounds writes as well as reads: a 9 MB clip
    # going to a phone on a slow link blocks inside one `wfile.write`, and at the
    # 30 seconds this used to be, anything under 8 kB/s would have been cut off.
    # 120 costs an idle keep-alive connection two minutes of one thread, which for a
    # single user tool is nothing.
    timeout = 120
    app: App  # set by serve()

    # The page polls its own health and its running task. Logging those buries the
    # lines that matter: a day of polling wrote 150 kB of "GET /api/state 200".
    QUIET = ("/api/state", "/api/task", "/api/frame", "/api/clip")

    # -- plumbing ---------------------------------------------------------

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        line = fmt % args
        if any(f" {path}" in line for path in self.QUIET) and " 200 " in f" {line} ":
            return
        # Media carries the token in the query string. Logging that writes the one
        # secret this server has into a file that outlives the process.
        log.debug("web %s", TOKEN_IN_URL.sub("t=REDACTED", line))

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

    def _send_media(
        self, file: Path, kind: str, extra: dict[str, str] | None = None
    ) -> None:
        """Serve a file, honouring a single byte range.

        Without this a `<video>` has no way to jump: the browser asks for a range,
        gets the whole file with a 200, and the slider does nothing.
        """
        size = file.stat().st_size
        first, last = 0, size - 1
        partial = False

        asked = RANGE.match((self.headers.get("Range") or "").strip())
        if asked:
            begin, end = asked.groups()
            if begin:
                first = int(begin)
                last = min(int(end), size - 1) if end else size - 1
            elif end:  # bytes=-500 means the last 500 bytes
                first = max(0, size - int(end))
            partial = True
            if first >= size or first > last:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

        length = last - first + 1
        self.send_response(
            HTTPStatus.PARTIAL_CONTENT if partial else HTTPStatus.OK
        )
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        if partial:
            self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with file.open("rb") as handle:
            handle.seek(first)
            left = length
            while left > 0:
                chunk = handle.read(min(MEDIA_CHUNK, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    # Seeking, or closing the tab, abandons a response mid flight.
                    return
                left -= len(chunk)

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def _fail(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message}, status)

    def _authorised(self, query_token: str | None = None) -> bool:
        """Guard every api call against other websites on this machine."""
        offered = self.headers.get(TOKEN_HEADER) or query_token
        if not offered or not secrets.compare_digest(offered, self.app.token):
            return False
        origin = self.headers.get("Origin")
        if origin and origin != self._own_origin():
            return False
        return True

    def _own_origin(self) -> str | None:
        """This server, named the way the browser addressed it.

        Chrome sends `Origin` on every same-origin POST, so a hardcoded
        `127.0.0.1` refused every write from a page opened on any other address:
        `127.0.0.2`, `[::1]`, or a tailnet address if the server is ever bound to
        one. Reproduced on 2026-08-19, which is what prompted this.

        The `Host` header is only trusted when it names an address rather than a
        name. That is what keeps DNS rebinding out: an attacker can point
        `evil.com` at 127.0.0.1 and the browser will then send
        `Host: evil.com` with a matching `Origin`, and both are refused here.
        A hostname front door, behind a tunnel, would need this widened on purpose.
        """
        host = self.headers.get("Host", "").strip()
        if not host:
            return None
        name = host.rsplit(":", 1)[0] if ":" in host else host
        name = name.strip("[]")
        if name != "localhost":
            try:
                ipaddress.ip_address(name)
            except ValueError:
                return None
        return f"http://{host}"

    def _local(self) -> bool:
        """Whether this request came from this machine.

        The page uses it to decide which action sits under your thumb: at the
        laptop, loading into WhatsApp Web; from anywhere else, downloading the clip
        to post from the phone. Nothing is hidden either way, so guessing wrong
        costs a glance rather than a workflow.
        """
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except (ValueError, IndexError):
            return False

    def _body(self) -> dict[str, Any] | None:
        """The request body, parsed. `None` means it was too big to read.

        Without a ceiling a caller holding the token could announce any
        `Content-Length` and this process would try to hold all of it in memory. The
        largest legitimate body is one animated sticker, `stickers.ANIMATED_MAX_BYTES`
        as base64, which is about 10.7 MB, so the cap sits a little above that.

        An oversized body is drained rather than ignored, up to the cap, and then the
        connection is closed. Answering without reading what the client is still
        sending gives it a broken pipe instead of the 413 that explains itself.
        """
        raw = (self.headers.get("Content-Length") or "0").strip()
        if not (raw.isascii() and raw.isdigit()):  # `isdigit` alone takes "²"
            # `-1` would read until the socket closes. Nothing is read, and the
            # connection ends after the refusal.
            self.close_connection = True
            return None
        length = int(raw)
        if not length:
            return {}
        if length > MAX_BODY_BYTES:
            remaining = min(length, MAX_BODY_BYTES)
            while remaining > 0:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
            self.close_connection = True
            return None
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, RecursionError):  # not JSON, not UTF-8, or nested too deep
            return {}
        # Every route reads fields off an object; a list or a string is no request.
        return body if isinstance(body, dict) else {}

    # -- routes -----------------------------------------------------------

    def _host_allowed(self) -> bool:
        """Every request, the page itself included, must name this server by an
        address. A rebinding page (`Host: evil.example` resolving to 127.0.0.1)
        could otherwise read the token out of `/` and then use the routes that do
        not send `Origin`. The hosted site, behind its tunnel, overrides this."""
        return self._own_origin() is not None

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_allowed():
            return self._fail(HTTPStatus.FORBIDDEN, "open this page by its address")
        path, _, query = self.path.partition("?")
        params = dict(
            pair.split("=", 1) for pair in query.split("&") if "=" in pair
        )

        if path in ("/", "/index.html"):
            return self._page()
        if path in ("/app.css", "/app.js", "/favicon.svg"):
            return self._static(path.lstrip("/"))
        if path == "/favicon.ico":
            # Browsers ask for this by habit. The real icon is the SVG.
            return self._static("favicon.svg")

        if not path.startswith("/api/"):
            return self._fail(HTTPStatus.NOT_FOUND, "no such page")
        # Media is fetched by the browser itself, which cannot set a header.
        media = path in ("/api/frame", "/api/clip", "/api/sticker", "/api/gif")
        if not self._authorised(params.get("t") if media else None):
            return self._fail(HTTPStatus.FORBIDDEN, "bad or missing token")

        if path == "/api/state":
            state = self.app.state(fresh=params.get("fresh") == "1")
            state["local"] = self._local()
            return self._json(state)
        if path == "/api/task":
            task = self.app.tasks.get(params.get("id", ""))
            if not task:
                return self._fail(HTTPStatus.NOT_FOUND, "no such task")
            return self._json(task.as_json())
        if path in ("/api/frame", "/api/clip"):
            return self._file(
                path, params.get("stem", ""), download=params.get("download") == "1"
            )
        if path == "/api/gifs":
            if not gifs.enabled():
                return self._fail(HTTPStatus.NOT_FOUND, "GIF search is switched off")
            try:
                # `big=1` asks for a thumbnail that suits a wide screen's larger
                # cell. Only the browser knows how big its cells are, and the phone
                # reads this page over a tailnet where three times the bytes is felt.
                found = gifs.search(
                    unquote_plus(params.get("q", "")), large=params.get("big") == "1"
                )
            except gifs.GifError as exc:
                # Their outage is not a bug here, and the message is written to be
                # read by the person searching rather than by whoever wrote this.
                return self._fail(HTTPStatus.BAD_GATEWAY, str(exc))
            self.app.remember_gifs(found)
            return self._json({
                "credit": gifs.credit(),
                "gifs": [one.as_json() for one in found],
            })
        if path == "/api/gif":
            return self._gif_preview(params.get("id", ""))
        if path == "/api/controls":
            return self._json(self.app.controls_state(fresh=params.get("fresh") == "1"))
        if path == "/api/stickers":
            return self._json({
                "installed": stickers.installed(),
                "hint": "" if stickers.installed() else stickers.install_hint(),
                "stickers": stickers.search(unquote_plus(params.get("q", ""))),
            })
        if path == "/api/sticker":
            return self._sticker(
                unquote_plus(params.get("id", "")), params.get("w", "")
            )
        return self._fail(HTTPStatus.NOT_FOUND, "no such endpoint")

    def do_POST(self) -> None:  # noqa: N802
        path, _, _ = self.path.partition("?")
        # The body is read before anything is decided, including whether the caller
        # is allowed to be here at all. This connection is keep-alive, `HTTP/1.1`
        # above, so answering 403 with the body still sitting in the socket leaves
        # it there, and the next request line is then read out of the middle of it:
        # `501 Unsupported method ('{"url":...}POST')`. Seen on 2026-08-20, when a
        # restart left a tab holding a dead token and every POST it made poisoned
        # the connection behind it. Reading is bounded by `MAX_BODY_BYTES`, so an
        # unauthorised caller still cannot make this process hold anything large.
        if not self._host_allowed():
            self.close_connection = True  # the body is left unread
            return self._fail(HTTPStatus.FORBIDDEN, "open this page by its address")
        body = self._body()
        if not self._authorised():
            return self._fail(HTTPStatus.FORBIDDEN, "bad or missing token")
        if body is None:
            return self._fail(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "that is too big to send here"
            )

        if path == "/api/render":
            return self._render(body)
        if path == "/api/post":
            return self._post(body)
        if path == "/api/caption":
            return self._caption(body)
        if path == "/api/gif/pick":
            return self._gif_pick(body)
        if path == "/api/gif/provider":
            return self._gif_provider(body)
        if path == "/api/preview":
            return self._preview(body)
        if path == "/api/text":
            return self._free_text(body)
        if path == "/api/words":
            return self._words(body)
        if path == "/api/browser":
            return self._browser()
        if path == "/api/sticker":
            return self._upload_sticker(body)
        if path == "/api/sticker/delete":
            return self._delete_sticker(body)
        if path == "/api/cancel":
            return self._cancel(body)
        if path == "/api/clip/delete":
            return self._delete_clip(body)
        return self._fail(HTTPStatus.NOT_FOUND, "no such endpoint")

    def do_OPTIONS(self) -> None:  # noqa: N802
        # No CORS headers, deliberately: a preflight that gets no permission stops a
        # cross-origin caller from ever sending the token header. A body is never
        # read here, so the connection ends with the answer (D-101).
        self.close_connection = True
        self._send(HTTPStatus.FORBIDDEN, b"", "text/plain")

    def parse_request(self) -> bool:
        return super().parse_request() and not refuse_ambiguous_body(self)

    # -- handlers ---------------------------------------------------------

    def _page(self) -> None:
        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        # The same page is the hosted one (`portal.fill_app_page`), which fills
        # these with its own name and adds its own script; here they are the
        # local tool's.
        for key, value in (("{{TOKEN}}", self.app.token),
                           ("{{TITLE}}", "WhatsApp Status Maker"),
                           ("{{BRAND}}", "WhatsApp Status Maker"),
                           ("{{TAGLINE}}", "A YouTube snippet, ready to post"),
                           ("{{BODY_DATA}}", ""), ("{{HEAD}}", ""), ("{{SCRIPTS}}", "")):
            html = html.replace(key, value)
        self._send(HTTPStatus.OK, html.encode(), "text/html; charset=utf-8")

    def _static(self, name: str) -> None:
        file = WEB_DIR / name
        if not file.is_file():
            return self._fail(HTTPStatus.NOT_FOUND, "missing asset")
        kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self._send(HTTPStatus.OK, file.read_bytes(), f"{kind}; charset=utf-8")

    def _file(self, path: str, stem: str, download: bool = False) -> None:
        if not SAFE_STEM.match(stem):
            return self._fail(HTTPStatus.BAD_REQUEST, "bad clip name")
        suffix, kind = (
            (".png", "image/png") if path == "/api/frame" else (".mp4", "video/mp4")
        )
        file = self.app.out / f"{stem}{suffix}"
        if not file.is_file():
            return self._fail(HTTPStatus.NOT_FOUND, "not on disk")
        # `SAFE_STEM` has already refused quotes, slashes and anything else that
        # could break out of the filename, so this needs no further escaping.
        extra = (
            {"Content-Disposition": f'attachment; filename="{stem}{suffix}"'}
            if download else None
        )
        self._send_media(file, kind, extra)

    def _job_from(self, body: dict[str, Any]) -> Job:
        """The job a render request describes. Raises `ValueError` in words meant for
        the person, for anything the request gets wrong. Shared with the hosted
        page, which adds the captured media and nothing else, so the two can never
        disagree about what a form means."""
        url = str(body.get("url") or "").strip()
        if not url:
            raise ValueError("a YouTube link is needed")
        if len(url) > URL_MAX:
            raise ValueError("that link is too long to be a YouTube link")
        # A window is a start plus either a length or a stop time, whichever the
        # person had to hand. `resolve_window` prefers the stop time when both come.
        try:
            stop = str(body.get("end") or "").strip() or None
            length = None if stop else float(body.get("duration") or 0) or None
            start, end = pipeline.resolve_window(
                url, str(body.get("start") or "") or None, stop, length
            )
        except TimecodeError as exc:
            raise ValueError(str(exc)) from exc

        decals = stickers.parse_all(body.get("stickers"))

        # Named rather than boolean, because "not blurred" will not always mean
        # black: this is the field a third answer arrives in. Anything else is a
        # page that has drifted from this server, which is worth saying out loud.
        fill = str(body.get("fill") or render.BLUR)
        if fill not in render.FILLS:
            raise ValueError(f"{fill!r} is not a background this tool draws")

        framing = render.parse_framing(body.get("framing"))

        return Job(
            url=url, start=start, end=end,
            video=bool(body.get("video")),
            wave=bool(body.get("wave", True)),
            fill=fill,
            framing=framing,
            # Every line of words is held to a caption's length: nothing on a card
            # needs more, and laying out an unbounded string holds the render slot.
            title=(_words_of(body, "title") or None),
            channel=(_words_of(body, "channel") or None),
            footer=_words_of(body, "footer"),
            eyebrow=_words_of(body, "eyebrow"),
            topline=_words_of(body, "topline"),
            decals=decals,
            frame="mid",  # the page always shows a still, so always make one
            out=self.app.out,
            keep_last=self.app.keep_last,
        )

    def _render(self, body: dict[str, Any]) -> None:
        try:
            job = self._job_from(body)
        except ValueError as exc:
            return self._fail(HTTPStatus.BAD_REQUEST, str(exc))
        try:
            task = self.app.render(job, follow_up=bool(body.get("follow_up")))
        except RuntimeError as exc:
            return self._fail(HTTPStatus.CONFLICT, str(exc))
        self._json({"id": task.id})

    def _post(self, body: dict[str, Any]) -> None:
        stem = str(body.get("stem") or "")
        if not SAFE_STEM.match(stem):
            return self._fail(HTTPStatus.BAD_REQUEST, "bad clip name")
        try:
            task = self.app.post_clip(
                stem,
                follow_up=bool(body.get("follow_up")),
                # Nothing is sent unless the caller says so in as many words.
                send=bool(body.get("send")),
            )
        except FileNotFoundError as exc:
            return self._fail(HTTPStatus.NOT_FOUND, str(exc))
        except RuntimeError as exc:
            return self._fail(HTTPStatus.CONFLICT, str(exc))
        self._json({"id": task.id})

    def _sticker(self, sticker_id: str, width: str = "") -> None:
        """One sticker's image. The id pattern is the whole guard: no dots, no
        slashes, so it cannot address anything outside the two sticker folders.

        `w` asks for a scaled copy, which is what the picker uses.
        """
        file = (
            stickers.thumbnail(sticker_id, int(width))
            if width.isdigit() else stickers.resolve(sticker_id)
        )
        if file is None:
            return self._fail(HTTPStatus.NOT_FOUND, "no such sticker")
        # An animated sticker is a GIF, and saying `image/png` over it would leave
        # the browser guessing. A thumbnail is always a PNG whatever it came from.
        kind = mimetypes.guess_type(file.name)[0] or "image/png"
        self._send_media(file, kind)

    def _gif_preview(self, ident: str) -> None:
        """A search result's thumbnail, fetched by this server rather than by you.

        The page never loads an image from a provider directly. Everything on this
        page comes from one origin, and the reason is the phone: it reads this page
        over a tailnet, and a thumbnail loaded from GIPHY would put the **phone** in
        touch with GIPHY. Proxying keeps the search on this machine. See D-043.
        """
        if not gifs.enabled():
            return self._fail(HTTPStatus.NOT_FOUND, "GIF search is switched off")
        offered = self.app.offered_gif(ident)
        if offered is None:
            # Not an error worth explaining: a stale page asking about a search two
            # searches ago is the ordinary case.
            return self._fail(HTTPStatus.NOT_FOUND, "that result is no longer on offer")
        try:
            data = gifs.fetch(offered.preview, ceiling=stickers.ANIMATED_MAX_BYTES)
        except gifs.GifError as exc:
            return self._fail(HTTPStatus.BAD_GATEWAY, str(exc))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/gif")
        self.send_header("Content-Length", str(len(data)))
        # A provider's own id is stable, so a preview can be cached hard. It is
        # still only ever fetched once per result per run.
        self.send_header("Cache-Control", "private, max-age=86400")
        self.end_headers()
        self.wfile.write(data)

    def _gif_pick(self, body: dict[str, Any]) -> None:
        """Download the chosen result and keep it, returning a sticker to place."""
        if not gifs.enabled():
            return self._fail(HTTPStatus.NOT_FOUND, "GIF search is switched off")
        offered = self.app.offered_gif(str(body.get("id") or ""))
        if offered is None:
            return self._fail(
                HTTPStatus.NOT_FOUND,
                "that result is no longer on offer. Search again and pick it",
            )
        try:
            data = gifs.fetch(offered.full, ceiling=stickers.ANIMATED_MAX_BYTES)
        except gifs.GifError as exc:
            return self._fail(HTTPStatus.BAD_GATEWAY, str(exc))
        try:
            saved = stickers.save_gif(
                offered.provider or gifs.provider(), offered.id, offered.title, data
            )
        except ValueError as exc:
            return self._fail(HTTPStatus.BAD_REQUEST, str(exc))
        self._json(saved)

    def _preview(self, body: dict[str, Any]) -> None:
        """Draw these words on this clip's own picture and answer with a PNG.

        A POST because the words are free text: an address carrying somebody's
        title ends up in every log between here and the browser, and this page is
        reachable from a phone over a tailnet.
        """
        stem = str(body.get("stem") or "")
        if not SAFE_STEM.match(stem):
            return self._fail(HTTPStatus.BAD_REQUEST, "that is not a clip name")
        words = compose.CardText(
            title=str(body.get("title") or "")[:CAPTION_MAX],
            channel=str(body.get("channel") or "")[:CAPTION_MAX],
            footer=str(body.get("footer") or "")[:CAPTION_MAX],
            eyebrow=str(body.get("eyebrow") or "")[:CAPTION_MAX],
            topline=str(body.get("topline") or "")[:CAPTION_MAX],
        )
        fill = str(body.get("fill") or "")
        if fill and fill not in render.FILLS:
            return self._fail(HTTPStatus.BAD_REQUEST,
                              f"{fill!r} is not a background this tool draws")
        try:
            framing = render.parse_framing(body.get("framing"))
        except ValueError as exc:
            return self._fail(HTTPStatus.BAD_REQUEST, str(exc))
        try:
            picture = self.app.preview_jpeg(stem, words, fill=fill or None,
                                            framing=framing)
        except FileNotFoundError as exc:
            return self._fail(HTTPStatus.NOT_FOUND, str(exc))
        except (OSError, ValueError) as exc:
            log.exception("preview failed for %s", stem)
            return self._fail(HTTPStatus.INTERNAL_SERVER_ERROR, plain_error(exc))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(picture)))
        # Every request draws it again, so a cached copy is always the wrong one.
        self.send_header("Cache-Control", "no-store")
        # Where to cut the still open so the clip keeps playing under the new
        # words. A header rather than a second request: it is a fact about this
        # picture, and it must never arrive a keystroke apart from it.
        band = self.app.moving_band(stem, words, fill=fill or None, framing=framing)
        if band:
            self.send_header("X-Moving-Band", f"{band[0]},{band[1]}")
        # What the frame cannot fit, so the page can say so rather than showing a
        # picture with a line missing from it and no explanation.
        lost = self.app.dropped_lines(stem, words, framing)
        if lost:
            self.send_header("X-Dropped-Toplines", str(lost))
        self.end_headers()
        self.wfile.write(picture)

    def _gif_provider(self, body: dict[str, Any]) -> None:
        """Switch which service the search asks, for the life of this process.

        `.env` stays the default and is never written to. The last search's results
        are forgotten with the provider that produced them: a pick names an id, and
        an id from GIPHY means nothing to KLIPY.
        """
        if not gifs.enabled():
            return self._fail(HTTPStatus.NOT_FOUND, "GIF search is switched off")
        try:
            gifs.choose(str(body.get("provider") or ""))
        except gifs.GifError as exc:
            return self._fail(HTTPStatus.BAD_REQUEST, str(exc))
        self.app.remember_gifs([])
        self._json(gifs.credit())

    def _upload_sticker(self, body: dict[str, Any]) -> None:
        try:
            saved = stickers.save_upload(
                str(body.get("name") or ""), str(body.get("data") or "")
            )
        except ValueError as exc:
            return self._fail(HTTPStatus.BAD_REQUEST, str(exc))
        self._json(saved)

    def _delete_sticker(self, body: dict[str, Any]) -> None:
        try:
            gone = stickers.delete_upload(str(body.get("id") or ""))
        except ValueError as exc:
            return self._fail(HTTPStatus.BAD_REQUEST, str(exc))
        if not gone:
            return self._fail(HTTPStatus.NOT_FOUND, "no such sticker")
        self._json({"deleted": True})

    def _caption(self, body: dict[str, Any]) -> None:
        stem = str(body.get("stem") or "")
        if not SAFE_STEM.match(stem):
            return self._fail(HTTPStatus.BAD_REQUEST, "bad clip name")
        try:
            caption = self.app.save_caption(stem, str(body.get("caption") or ""))
        except FileNotFoundError as exc:
            return self._fail(HTTPStatus.NOT_FOUND, str(exc))
        except ValueError as exc:
            return self._fail(HTTPStatus.BAD_REQUEST, str(exc))
        self._json({"caption": caption})

    def _cancel(self, body: dict[str, Any]) -> None:
        try:
            task = self.app.cancel(str(body.get("id") or ""))
        except KeyError:
            return self._fail(HTTPStatus.NOT_FOUND, "no such task")
        except ValueError as exc:
            return self._fail(HTTPStatus.CONFLICT, str(exc))
        self._json({"id": task.id, "stopping": True})

    def _delete_clip(self, body: dict[str, Any]) -> None:
        stem = str(body.get("stem") or "")
        if not SAFE_STEM.match(stem):
            return self._fail(HTTPStatus.BAD_REQUEST, "bad clip name")
        try:
            gone = self.app.delete_clip(stem)
        except FileNotFoundError as exc:
            return self._fail(HTTPStatus.NOT_FOUND, str(exc))
        except RuntimeError as exc:
            return self._fail(HTTPStatus.CONFLICT, str(exc))
        except OSError as exc:
            return self._fail(HTTPStatus.INTERNAL_SERVER_ERROR, plain_error(exc))
        self._json(gone)

    def _words(self, body: dict[str, Any]) -> None:
        """The video's own title and second line, for the boxes to be edited in.

        Answered synchronously, so the page holds one request open while yt-dlp
        talks to YouTube. Everything else on the page carries on: the health poll,
        a render already running and the word preview all have their own threads.
        """
        url = str(body.get("url") or "").strip()
        if not url:
            return self._fail(HTTPStatus.BAD_REQUEST, "a YouTube link is needed")
        try:
            words = self.app.words_from(url)
        except fetch.FetchError as exc:
            # Their end rather than ours: a private video, a playlist, a dead link,
            # or YouTube refusing this machine. The message is already written for
            # whoever pasted the link, so it goes through as it is.
            return self._fail(HTTPStatus.BAD_GATEWAY, str(exc))
        except (ValueError, OSError) as exc:  # unparseable JSON, or no yt-dlp here
            return self._fail(
                HTTPStatus.BAD_GATEWAY, f"could not read that link ({exc})")
        self._json(words)

    def _free_text(self, body: dict[str, Any]) -> None:
        """Draw one placed line, so the page has a picture of it to put on the frame.

        A POST for the same reason `/api/preview` is one: the words are free text,
        and an address carrying them ends up in every log between here and a phone.
        """
        text = freetext.clean(str(body.get("text") or ""))
        if not text:
            return self._fail(HTTPStatus.BAD_REQUEST, "there is nothing to draw")
        try:
            drawn = freetext.to_png(text, self.app.TEXT_WIDTH)
        except (OSError, ValueError) as exc:
            log.exception("free text could not be drawn")
            return self._fail(HTTPStatus.INTERNAL_SERVER_ERROR, plain_error(exc))
        self._send(HTTPStatus.OK, drawn, "image/png")

    def _browser(self) -> None:
        if self.app.whatsapp_state(fresh=True)["ready"]:
            return self._fail(
                HTTPStatus.CONFLICT, "a browser with WhatsApp Web is already open"
            )
        try:
            started = self.app.start_browser()
        except post.PostError as exc:
            return self._fail(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
        self._json(started)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wastatus serve",
        description="Open the local page: the same tool as a form in your browser.",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"port for the page (default {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--cdp-port", type=int, default=post.default_port(), metavar="N",
        help=f"Chrome remote debugging port to prefer for posting "
             f"(default {post.default_port()}; any other debug browser holding a "
             "WhatsApp tab is tried after it, from "
             f"{', '.join(str(p) for p in post.candidate_ports())}, which "
             f"{post.PORTS_ENV} sets)",
    )
    parser.add_argument("-o", "--out", type=Path, default=Path("out"), help="output directory")
    parser.add_argument(
        "--keep-last", type=int, default=retention.DEFAULT_KEEP, metavar="N",
        help=f"clips to retain in the output folder (default {retention.DEFAULT_KEEP})",
    )
    parser.add_argument(
        "--also-on", default=(os.environ.get(ALSO_ON_ENV) or "").strip(),
        metavar="ADDRESS",
        help="additionally listen on this address so another device can reach the "
             "page, for example a phone. `tailscale` resolves your tailnet address. "
             "Loopback is always listening as well. Anyone who can open the page "
             "gets the token that lets it post, so use a tailnet rather than the "
             f"whole local network. {ALSO_ON_ENV} in .env sets it for every run",
    )
    browser = parser.add_mutually_exclusive_group()
    browser.add_argument(
        "--start-browser", dest="start_browser", action="store_true", default=None,
        help="start a Chrome with WhatsApp Web open, if one is not already running, "
             f"so posting works without a second command. {BROWSER_ENV} in .env sets "
             "it for every run",
    )
    browser.add_argument(
        "--no-start-browser", dest="start_browser", action="store_false",
        help=f"do not start a browser, whatever {BROWSER_ENV} says",
    )
    parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    parser.add_argument("-v", "--verbose", action="store_true", help="echo the log to the console")
    return parser


def resolve_host(value: str) -> str:
    """Turn a `--also-on` value into an address to bind.

    `tailscale` asks the tailnet for this machine's address, because looking that
    up by hand before every session is the kind of friction that stops a thing
    being used. Anything else has to be a literal address: a name would be resolved
    once here and then would not match what a browser sends as `Host`, which is what
    `Handler._own_origin` checks.
    """
    if value == "tailscale":
        return tailscale_ip()
    try:
        ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError(
            f"--also-on takes an address or the word tailscale, not {value!r}"
        ) from exc
    return value


def tailscale_ip() -> str:
    exe = shutil.which("tailscale")
    if not exe:
        raise ValueError(
            "tailscale is not installed, so there is nothing to ask for an address"
        )
    try:
        found = subprocess.run(
            [exe, "ip", "-4"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"could not ask tailscale for an address ({exc})") from exc
    first = (found.stdout or "").split()
    if found.returncode != 0 or not first:
        raise ValueError(
            "tailscale returned no address. Is it running and logged in?"
        )
    return first[0]


def url_for(host: str, port: int) -> str:
    return f"http://[{host}]:{port}/" if ":" in host else f"http://{host}:{port}/"


def wanted(flag: bool | None, name: str) -> bool:
    """A switch that the command line may answer and `.env` may answer instead.

    `None` means neither `--start-browser` nor `--no-start-browser` was given, so
    the file gets to speak. An explicit flag always wins, because the point of
    typing one is to overrule the file for this run.
    """
    if flag is not None:
        return flag
    return (os.environ.get(name) or "").strip().lower() in TRUE


def show_page(url: str, port: int | None) -> None:
    """Put the page in the browser this tool posts through, not the default one.

    The label tab says one window holds this session; the page belonging to that
    session opening in a different browser was the loose end. A browser we started
    gets the page on its command line, which is the ordinary route. A browser that
    was already running never saw a command line, so the tab is asked for over the
    debug protocol instead.

    Falling back to the default browser is not a failure worth reporting: the page
    has to open somewhere, and where it opened is visible from the fact that it did.
    """
    if not url:
        return
    if port is not None:
        try:
            post.open_tab(port, url)
            return
        except post.PostError as exc:
            log.debug("could not open the page in the posting browser (%s)", exc)
    webbrowser.open(url)


def ensure_browser(app: App, page_url: str = "") -> None:
    """Open a browser with WhatsApp Web in it, unless one is already there.

    Never fatal. The page is worth having even when posting is not available, and
    a person who wanted the browser will see why it is missing on the health panel
    a moment later. `page_url` is opened wherever this ends up: in the browser
    started here, in the one adopted, or in the default browser if neither happened.
    """
    state = app.whatsapp_state(fresh=True)
    if state["ready"]:
        print(f"WhatsApp Web: {state['detail']}, already open", flush=True)
        show_page(page_url, state["port"])
        return
    try:
        started = app.start_browser(page_url=page_url)
    except post.PostError as exc:
        print(f"WhatsApp Web: not started ({exc})", flush=True)
        show_page(page_url, None)
        return
    if started.get("adopted"):
        # A browser on the posting profile was already running, on a port outside
        # the ones being looked on. It is the right browser; only the preference
        # was wrong, and `start_browser` has moved it.
        print(
            f"WhatsApp Web: already open on debug port {started['port']}, using that",
            flush=True,
        )
        show_page(page_url, started["port"])
        return
    print(
        f"Started {Path(started['binary']).name} on debug port {started['port']} "
        f"with WhatsApp Web.\nFirst time only: scan the QR code. "
        f"That login lives in {started['profile']}.",
        flush=True,
    )


def make_server(
    app: App, port: int = DEFAULT_PORT, host: str = BIND
) -> ThreadingHTTPServer:
    """A server on one address. Port 0 asks the OS for a free one, for tests."""
    handler = type("BoundHandler", (Handler,), {"app": app})
    return ThreadingHTTPServer((host, port), handler)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runlog.stamp(runlog.setup(args.verbose))

    extra = ""
    if args.also_on:
        try:
            extra = resolve_host(args.also_on)
        except ValueError as exc:
            print(f"error: {exc}")
            return 1

    app = App(
        out=args.out, cdp_port=args.cdp_port, keep_last=args.keep_last, also_on=extra,
    )

    # Loopback is always bound, even when another address is asked for. Binding one
    # address only would mean the laptop reaching its own page over the tailnet,
    # where the page cannot tell it apart from the phone and offers the wrong button.
    servers: list[ThreadingHTTPServer] = []
    try:
        servers.append(make_server(app, args.port, BIND))
        port = servers[0].server_address[1]
        if extra:
            servers.append(make_server(app, port, extra))
    except (OSError, OverflowError, ValueError) as exc:
        # A busy port raises OSError; a port outside 0..65535 raises OverflowError,
        # and an unhandled traceback is a poor answer to a typo.
        for server in servers:
            server.server_close()
        print(f"error: cannot listen on port {args.port} ({exc})")
        print("Another wastatus may already be serving. Try --port.")
        return 1

    app.page_port = port
    url = url_for(BIND, port)
    whatsapp = app.whatsapp_state()
    starting = wanted(args.start_browser, BROWSER_ENV)
    # Saying "no Chrome answering on 9230" a second before starting one on 9230 is
    # a false alarm at every single start. When a browser is on its way, say so and
    # let `ensure_browser` report what actually happened.
    if whatsapp["ready"]:
        state = "ready"
    elif starting:
        state = "looking for one, or starting one"
    else:
        state = whatsapp["detail"]
    print(
        f"wastatus is serving {url}\n"
        f"Output goes to {args.out.resolve()}\n"
        f"WhatsApp Web: {state}\n"
        "Stop with Ctrl-C.",
        flush=True,
    )
    if extra:
        print(
            f"Also on {url_for(extra, port)} for another device.\n"
            "Whoever opens that page can post to your Status. Keep it to a tailnet.",
            flush=True,
        )
    open_url = "" if args.no_open else url
    if starting:
        # On a thread: launching Chrome and then probing it takes a few seconds,
        # and the page should be answering by then rather than after. The page is
        # opened in there too, so one window holds the label, the tool and WhatsApp
        # rather than the tool living in whichever browser is the default.
        threading.Thread(
            target=ensure_browser, args=(app,), kwargs={"page_url": open_url},
            daemon=True,
        ).start()
    elif open_url:
        # Nothing is being started, so there is no window of ours to put it in.
        threading.Thread(target=webbrowser.open, args=(open_url,), daemon=True).start()

    for server in servers[1:]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        for server in servers[1:]:
            server.shutdown()  # stop the thread it is serving on
        for server in servers:
            server.server_close()
        potoken.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
