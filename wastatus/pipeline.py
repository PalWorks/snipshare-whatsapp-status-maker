"""The engine: a YouTube window in, a postable clip out.

Separated from the command line so the local web page in `serve.py` runs exactly
this pipeline rather than a copy of it. Nothing here prints, parses arguments, or
posts: it produces files and reports progress through a callback. Callers decide
what any of that means to a person.
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import (capture, compose, fetch, naming, render, retention, runlog,
               stickers, translit)
from .timecode import parse_timecode, start_from_url

log = logging.getLogger("wastatus")

DEFAULT_DURATION = 15.0
MAX_DURATION = 90.0  # WhatsApp Status will not take a longer single video.

# In order, for anything drawing a progress indicator.
STAGES = ("probe", "download", "compose", "render")

Progress = Callable[[str, str], None]


@dataclass
class Captured:
    """A window the viewer's own browser already fetched, so nothing is downloaded.

    The browser extension uploads what YouTube's player appended, and these are the
    facts it read off the same page. With one of these on the job, `produce` asks
    YouTube nothing at all: not the metadata, not the media and not the artwork,
    which is the whole reason the hosted renderer can live on a datacentre address
    YouTube refuses. See docs/extension.md and DECISIONS.md D-080.
    """

    source: fetch.Source
    audio: Path                  # one audio stream, on YouTube's own timestamps
    video: Path | None = None    # one video stream, the same; video mode only
    artwork: Path | None = None  # the thumbnail the browser fetched; card mode


@dataclass
class Job:
    """What to make. Timestamps are seconds; `resolve_window` produces them."""

    url: str
    start: float
    end: float
    video: bool = False
    wave: bool = True
    # What fills the frame behind the picture in video mode: `render.BLUR`, a
    # darkened blurred copy of the same frames, or `render.BLACK`, which is the
    # colour WhatsApp draws Status on. Card mode composes its own background and
    # does not read this. See D-059.
    fill: str = render.BLUR
    title: str | None = None
    channel: str | None = None
    footer: str = ""
    eyebrow: str = ""
    topline: str = ""
    # Placed by whoever asked for the clip, in fractions of the frame. Pasted last,
    # over everything, in both modes. See DECISIONS.md D-024.
    decals: list[stickers.Placed] = field(default_factory=list)
    # Where the picture goes, in the same fractions: the video's frames in video
    # mode, the artwork panel in card mode. None is the answer both have always
    # given, which is to fit it into the room the words leave. See D-061 and D-062.
    framing: "render.Framing | None" = None
    frame: str | None = None  # None, "mid", or a timecode inside the clip
    # Set by the hosted renderer only. None is every local run: yt-dlp fetches.
    captured: Captured | None = None
    out: Path = field(default_factory=lambda: Path("out"))
    keep_last: int = retention.DEFAULT_KEEP
    keep: bool = False

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def mode(self) -> str:
        return "video" if self.video else "card"


@dataclass
class Result:
    """What was made."""

    clip: Path
    caption: str
    stem: str
    title: str
    channel: str
    duration: float
    size_bytes: int
    video: bool
    frame: Path | None = None
    pruned: retention.Pruned | None = None

    @property
    def size_mb(self) -> float:
        return self.size_bytes / 1_000_000


def resolve_window(
    url: str,
    start: str | None = None,
    end: str | None = None,
    duration: float | None = None,
) -> tuple[float, float]:
    """Turn optional timestamp strings into a validated window in seconds.

    Both callers go through this, so the command line and the web page accept the
    same timestamp forms and refuse the same windows with the same words.

    Raises `TimecodeError` for an unparseable timestamp and `ValueError` for a
    window that WhatsApp would not take.
    """
    # A web address, with or without its scheme (`youtu.be/ID` is what people paste
    # and yt-dlp takes it), and never something yt-dlp could read as an option or
    # another kind of address, such as `--exec` or `file:///`.
    lowered = url.strip().lower()
    if lowered.startswith("-") or ("://" in lowered
                                   and not lowered.startswith(("https://", "http://"))):
        raise ValueError("that is not a web address. Paste the YouTube link")
    begin = parse_timecode(start) if start else (start_from_url(url) or 0.0)
    finish = parse_timecode(end) if end else begin + (duration or DEFAULT_DURATION)

    if not (math.isfinite(begin) and math.isfinite(finish)):
        raise ValueError("the start and the end have to be times")
    length = finish - begin
    if length <= 0:
        raise ValueError("the end has to come after the start")
    if length > MAX_DURATION:
        raise ValueError(
            f"{length:.0f}s exceeds the {MAX_DURATION:.0f}s WhatsApp Status limit"
        )
    return begin, finish


def frame_offset(value: str, duration: float) -> float:
    """Resolve a frame request into an offset inside the clip."""
    at = duration / 2 if value == "mid" else parse_timecode(value)
    # A still from past the end is an empty file rather than an error, so clamp.
    return min(max(0.0, at), max(0.0, duration - 0.05))


def title_and_channel(job: "Job", source: fetch.Source) -> tuple[str, str]:
    """The title and the channel that go on the card, and into the filename.

    An override always wins. Otherwise the title is cleaned, and if cleaning leaves
    nothing at all the channel stands in: `translit.clean_title` already falls back
    to the raw title, so reaching here means the title romanised to nothing, which an
    emoji only title does. A card carrying the channel still says whose clip it is,
    where a blank line says nothing. See [TASKS.md](TASKS.md) T-008.
    """
    channel = (
        translit.to_latin(job.channel) if job.channel
        else translit.clean_channel(source.artist or source.channel)
    )
    title = (
        translit.to_latin(job.title) if job.title else translit.clean_title(source.title)
    )
    return (title.strip() or channel), channel


def words_from_video(source: fetch.Source) -> tuple[str, str]:
    """The words a video answers for itself: what an empty pair of boxes means.

    The page's Fetch fills those boxes in advance, so what it offers has to be what
    the card would have drawn from this video and not a second cleaning of the same
    fields that could drift from it. Asking `title_and_channel` for a job that
    overrides nothing is the only way to be sure of that, so that is what this does.
    The words it hands back then arrive here again as overrides and resolve to
    themselves, which is why pressing Fetch changes what is on screen and never what
    would land in the pixels. See DECISIONS.md D-064.
    """
    return title_and_channel(Job(url=source.watch_url, start=0.0, end=0.0), source)


def produce(job: Job, run: runlog.Run, progress: Progress | None = None) -> Result:
    """Make the clip. Raises on any failure, having cleaned up after itself."""

    def say(stage: str, message: str) -> None:
        if progress:
            progress(stage, message)

    say("probe", f"reading {job.url}")
    with run.stage("probe"):
        source = job.captured.source if job.captured else fetch.probe(job.url)
    run.set(video_id=source.video_id, raw_title=source.title)

    if source.duration and job.end > source.duration:
        # A window running past the end used to be refused. That meant reading the
        # video's length off an error message and typing it back into the box, when
        # the length is the whole answer: take it. ffmpeg stops at the end of the
        # file either way, so the clip made here is the clip that window could ever
        # have produced. Only a start that is past the end has nothing to make.
        if job.start >= source.duration:
            raise ValueError(
                f"the video is {source.duration:.0f}s long, so a clip starting at "
                f"{job.start:.0f}s would be empty"
            )
        log.warning(
            "asked for a clip ending at %.0fs; the video is %.0fs long, "
            "so it ends there instead",
            job.end, source.duration,
        )
        job.end = float(source.duration)
        say("probe", f"the video is {source.duration:.0f}s long, so the clip ends there")
        # The window in the run record has to be the window that was made, not the
        # one that was asked for. The sidecar below is written from `job` and is
        # already right, which is what puts the corrected numbers in the page's boxes.
        run.set(end=job.end, duration=job.duration, trimmed_to_video=True)

    title, channel = title_and_channel(job, source)
    run.set(
        title=title, channel=channel,
        raw_channel=source.channel, raw_artist=source.artist,
    )
    if job.decals:
        run.set(stickers=[decal.label for decal in job.decals])
    # What the frame was built from, so a run record answers "why did that one look
    # like that" without the sidecar beside it. The background is video mode's alone,
    # because card mode composes its own; the placement means something in both.
    if job.video:
        run.set(fill=job.fill)
    if job.framing:
        run.set(framing=job.framing.as_json())

    job.out.mkdir(parents=True, exist_ok=True)
    # Claimed, not merely checked: two renders of the same song and window started
    # in the same second used to agree on a name and one overwrote the other. The
    # claim is the `.part` file below, and the `finally` clears it. See T-017.
    stem = naming.reserve_stem(
        job.out, naming.build_stem(title, job.start, job.end, video=job.video)
    )
    dest = job.out / f"{stem}.mp4"
    run.set(stem=stem)

    work = Path(tempfile.mkdtemp(prefix="wastatus-"))
    # ffmpeg writes into the work directory, never into the output folder. A
    # partially written mp4 in `out/` is listed by the page as a real clip, can be
    # played, posted and deleted while ffmpeg is still writing it, and used to be
    # left behind for good when a render failed. It arrives in the output folder in
    # one atomic step instead, under a name the page's `*.mp4` glob cannot see until
    # the rename.
    staged = work / f"{stem}.mp4"
    landing = job.out / f"{stem}.mp4.part"  # already created, as the name's claim
    made = False
    try:
        say(
            "download",
            f"fetching {'video' if job.video else 'audio'} "
            f"{job.start:.0f}s to {job.end:.0f}s",
        )
        with run.stage("download"):
            if job.captured:
                # Already fetched, by the viewer's browser. Cutting the window out
                # of it is this stage's work instead, and it lands in the same work
                # directory a download would have. Card mode never needs the frames.
                if job.video and job.captured.video is None:
                    raise capture.CaptureError("video mode needs the captured video")
                section = capture.section(
                    job.captured.audio,
                    job.captured.video if job.video else None,
                    job.start, job.end, work / "section.mkv",
                )
                media = fetch.Download(section, "browser", "capture")
            else:
                media = fetch.download_section(
                    job.url, job.start, job.end, work, video=job.video
                )
        run.set(
            client=media.client, format=media.fmt,
            source_bytes=media.bytes, failed_attempts=media.attempts,
        )

        say("compose", "composing the card")
        card_text = compose.CardText(
            title=title, channel=channel, footer=job.footer, eyebrow=job.eyebrow,
            topline=job.topline,
        )

        for decal in job.decals:
            if compose.covered_by_whatsapp(decal):
                log.warning(
                    "%s sits where WhatsApp draws its own header or caption",
                    decal.label,
                )

        # Two mechanisms, one list. A sticker that is a still image is pasted into
        # the picture by Pillow before ffmpeg starts; one that moves cannot be, so it
        # becomes a looping input in the filter graph. The split is made here, once,
        # rather than inside either of them. See DECISIONS.md D-036.
        still, moving = stickers.split(job.decals)
        if moving:
            log.info("%d animated sticker(s) go in as looping inputs", len(moving))

        say("render", "rendering")
        with run.stage("render"):
            # What the live word preview will draw over, kept out of the work
            # directory so it survives it. Video mode needs a frame with no text on
            # it; card mode needs only the artwork, because the card itself is a
            # Pillow render that takes under a second to repeat. T-036.
            preview_base = None
            picture_top = None
            picture_rect = None
            if job.video:
                # Where the frames land is worked out here, before anything is
                # drawn, because Pillow needs it: the top text hangs off the
                # picture's top edge. One measurement, used by the words and by the
                # filter graph, so the two cannot disagree. The frames give up room
                # at either end only when there is something to draw there. See
                # compose.video_picture_top and video_picture_bottom.
                crop, size = render.source_picture(media.path, job.duration, work)
                rect = (
                    # Placed by hand: the placement is the answer, and it may reach
                    # past any edge. Fitted: the band the words leave is the answer,
                    # which is what every clip made before this did. See D-061.
                    render.placed_rect(size, job.framing) if job.framing
                    else render.picture_rect(
                        size,
                        ceiling=compose.video_picture_top(card_text),
                        floor=compose.video_picture_bottom(card_text),
                    )
                )
                picture_top = rect.top
                # The whole rectangle, not only the edge the words are anchored to.
                # It is what lets the page preview a background the clip was not
                # made with: the picture inside the still is untouched video, and
                # everything outside it is only fill. See `render.recompose`.
                picture_rect = {
                    "left": rect.left, "top": rect.top,
                    "width": rect.width, "height": rect.height,
                }
                overlay = compose.build_overlay(
                    card_text, work / "overlay.png", decals=still,
                    picture_top=rect.top,
                    picture_bottom=rect.top + rect.height,
                )
                render.render_video_clip(
                    media.path, overlay, job.duration, staged, work=work,
                    moving=moving, base=work / "base.png", crop=crop, rect=rect,
                    fill=job.fill,
                )
                preview_base = (work / "base.png", f"{stem}.base.png")
            else:
                if job.captured and job.captured.artwork:
                    artwork = work / "art.jpg"
                    shutil.copyfile(job.captured.artwork, artwork)
                else:
                    artwork = fetch.download_thumbnail(source.video_id, work / "art.jpg")
                card = compose.build_card(
                    artwork, card_text, work / "card.png", decals=still,
                    framing=job.framing,
                )
                # The panel's rectangle, for the same reason video mode records its
                # own: the page cannot draw a box around something whose shape it
                # has no way to measure, and the artwork's shape is only known here.
                # The words, so the rectangle recorded here is the one the card
                # was actually drawn in: a fitted card shrinks to leave room for
                # the top text and the label, and the sidecar has to agree with
                # the pixels or the page draws its box around a card that moved.
                left, top, right, panel_bottom = compose.card_rect(
                    compose.card_aspect(artwork), job.framing, card_text)
                picture_rect = {
                    "left": left, "top": top,
                    "width": right - left, "height": panel_bottom - top,
                }
                render.render_card_clip(
                    card, media.path, job.duration, staged, wave=job.wave,
                    moving=moving,
                )
                preview_base = (artwork, f"{stem}.art.jpg")

        # The work directory may be on another filesystem, so this is a copy and
        # then a rename rather than one move: `shutil.move` across filesystems
        # writes the destination progressively, which is the thing being avoided.
        shutil.copyfile(staged, landing)
        os.replace(landing, dest)
        made = True

        # After the clip, and never able to stop it: a missing preview base costs
        # the live preview for this one clip, which is not worth losing a render to.
        if preview_base:
            source_file, name = preview_base
            try:
                if source_file.is_file():
                    shutil.copyfile(source_file, job.out / name)
            except OSError as exc:
                log.warning("no preview base kept for %s: %s", stem, exc)
    finally:
        if job.keep:
            log.info("work dir kept at %s", work)
        else:
            shutil.rmtree(work, ignore_errors=True)
        landing.unlink(missing_ok=True)
        if not made:
            # Belt and braces: nothing should have reached this name, and a clip
            # that is not finished must never be in the folder the page reads.
            dest.unlink(missing_ok=True)

    # Just the link. The title is already on the card, a foot above the caption,
    # and printing it twice made the Status read like a listing. See D-015.
    caption = source.watch_url
    (job.out / f"{stem}.caption.txt").write_text(caption + "\n", encoding="utf-8")

    # What it would take to make this clip again. The page reads this back to fill
    # its form from a clip in the Recent strip, so wording can be corrected and the
    # card re-made without retyping the link or the window.
    (job.out / f"{stem}.json").write_text(
        json.dumps(
            {
                "url": job.url,
                "start": job.start,
                "end": job.end,
                "video": job.video,
                "wave": job.wave,
                "fill": job.fill,
                "title": title,
                "channel": channel,
                "footer": job.footer,
                "eyebrow": job.eyebrow,
                "topline": job.topline,
                # Not a setting: where the frames actually landed. The live word
                # preview draws over a still of them and has no way to measure it,
                # and a top line placed against the wrong edge is a preview that
                # lies about the clip.
                "picture_top": picture_top,
                "picture": picture_rect,
                # What was asked for, against the rectangle above, which is what it
                # resolved to. The page fills its own control from this: a clip that
                # kept only the pixels could not say whether they were placed or fitted.
                "framing": job.framing.as_json() if job.framing else None,
                "stickers": [decal.as_json() for decal in job.decals],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    frame = None
    if job.frame is not None:
        at = frame_offset(job.frame, job.duration)
        frame = render.extract_frame(dest, job.out / f"{stem}.png", at)
        run.set(frame=str(frame), frame_at=at)

    run.set(output=str(dest), output_bytes=dest.stat().st_size)
    if dest.stat().st_size > render.PLATFORM_MAX_BYTES:
        # The budget should have prevented this, but the budget sets a maxrate and
        # the encoder overshoots it. Say so here, because WhatsApp will not: it takes
        # the file and never opens its editor. See T-014.
        log.warning(
            "this clip is %.2f MB and WhatsApp refuses anything over %.2f MB, "
            "without saying so. Make it shorter, or drop the bitrate",
            dest.stat().st_size / 1_000_000,
            render.PLATFORM_MAX_BYTES / 1_000_000,
        )

    pruned = retention.prune(job.out, job.keep_last)
    if pruned:
        run.set(pruned_groups=pruned.groups, pruned_bytes=pruned.bytes)

    return Result(
        clip=dest,
        caption=caption,
        stem=stem,
        title=title,
        channel=channel,
        duration=job.duration,
        size_bytes=dest.stat().st_size,
        video=job.video,
        frame=frame,
        pruned=pruned,
    )
