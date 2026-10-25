"""wastatus command line entry point.

The work itself lives in `pipeline.py`, which the local web page in `serve.py`
also drives. This module is argument parsing, the report a person reads, and
posting.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from . import pipeline, post, render, retention, runlog, sheet
from .pipeline import DEFAULT_DURATION, Job, Result
from .timecode import TimecodeError

SERVE = "serve"  # `wastatus serve` opens the local page instead of making a clip
HOSTED = "hosted"  # `wastatus hosted` is the renderer the browser extension uses


def _framing(value: str | None) -> "render.Framing | None":
    """`--picture 0.5,0.5,1` as a placement. None when it was not given.

    Three fractions rather than pixels, because that is the unit everything placed
    on the frame uses, and because the page and the command line have to be able to
    hand each other the same clip. See D-024 and D-061.
    """
    if not value:
        return None
    parts = [piece.strip() for piece in str(value).split(",")]
    if len(parts) != 3:
        raise ValueError(
            "--picture takes three numbers: the centre and the width, as "
            "fractions of the frame. For example 0.5,0.5,1"
        )
    try:
        x, y, size = (float(piece) for piece in parts)
    except ValueError as exc:
        raise ValueError(f"--picture takes numbers, not {value!r}") from exc
    return render.parse_framing({"x": x, "y": y, "size": size})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wastatus",
        description="Cut a YouTube snippet into a WhatsApp Status clip that carries the link.",
        epilog=f"`wastatus {SERVE}`, or `wastatus` with no arguments at all, opens a "
               "local page instead, with the same options as a form.",
    )
    parser.add_argument("url", help="YouTube URL or video id")
    parser.add_argument("start", nargs="?", help="start timestamp, e.g. 1:23 (default: ?t= or 0)")
    parser.add_argument("end", nargs="?", help="end timestamp, e.g. 1:38")
    parser.add_argument(
        "-d", "--duration", type=float,
        help=f"clip length in seconds when no end is given (default {DEFAULT_DURATION:.0f})",
    )
    parser.add_argument("--title", help="override the on-card title")
    parser.add_argument("--channel", help="override the on-card channel name")
    parser.add_argument("--footer", default="", help="add a small footer line (off by default)")
    parser.add_argument(
        "--top-line", dest="topline", default="", metavar="TEXT",
        help="add a line under WhatsApp's own header, above the picture "
             "(off by default)",
    )
    parser.add_argument(
        "--eyebrow", nargs="?", const="NOW PLAYING", default="",
        help="add a label just above the title, in both modes, "
             "optionally with your own text",
    )
    parser.add_argument(
        "--video", action="store_true",
        help="use the real video frames instead of the artwork card (slower, more data)",
    )
    parser.add_argument("--no-wave", action="store_true", help="drop the waveform strip")
    parser.add_argument(
        "--fill", choices=render.FILLS, default=render.BLUR,
        help="what goes behind the frames with --video: a darkened blurred copy of "
             f"them (default), or plain black (default: {render.BLUR})",
    )
    parser.add_argument(
        "--picture", default=None, metavar="X,Y,SIZE",
        help="place the picture yourself, as three fractions: the centre and the "
             "width. The frames with --video, the artwork panel without it. "
             "0.5,0.5,1 fills the frame's width. Left out, it is fitted into the "
             "room the words leave, as it always was",
    )
    parser.add_argument(
        "--frame", nargs="?", const="mid", default=None, metavar="AT",
        help="also write a still image, at the clip midpoint or at a given offset",
    )
    sending = parser.add_mutually_exclusive_group()
    sending.add_argument(
        "--post", action="store_true",
        help="post it to your Status through a logged in WhatsApp Web tab (off by default)",
    )
    sending.add_argument(
        "--load", action="store_true",
        help="load it into the Status composer with its caption, but stop before Send",
    )
    parser.add_argument(
        "--follow-up", action="store_true",
        help="also post a text only Status carrying the title and link",
    )
    parser.add_argument(
        "--port", type=int, default=None, metavar="N",
        help=f"Chrome remote debugging port to prefer (default {post.default_port()}; "
             "any other debug browser holding a WhatsApp tab is tried after it, from "
             f"{', '.join(str(p) for p in post.candidate_ports())})",
    )
    parser.add_argument("-o", "--out", type=Path, default=Path("out"), help="output directory")
    parser.add_argument(
        "--keep-last", type=int, default=retention.DEFAULT_KEEP, metavar="N",
        help=f"clips to retain in the output folder, 0 disables pruning "
             f"(default {retention.DEFAULT_KEEP})",
    )
    parser.add_argument("--keep", action="store_true", help="keep the intermediate work directory")
    parser.add_argument("-v", "--verbose", action="store_true", help="echo the log to the console")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Bare `./wastatus.sh` opens the page. Making a clip needs a URL and two
    # timestamps, so there is no useful thing an empty command line could mean, and
    # the page is what gets opened most days anyway. TASKS.md T-032.
    if not argv or argv[0] == SERVE:
        from . import serve  # imported here so the CLI path stays dependency free

        return serve.main(argv[1:] if argv else [])
    if argv[0] == HOSTED:
        from . import hosted

        return hosted.main(argv[1:])

    args = build_parser().parse_args(argv)
    log = runlog.setup(args.verbose)
    runlog.stamp(log)

    try:
        start, end = pipeline.resolve_window(
            args.url, args.start, args.end, args.duration
        )
    except (TimecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        framing = _framing(args.picture)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    job = Job(
        url=args.url, start=start, end=end,
        video=args.video, wave=not args.no_wave, fill=args.fill,
        framing=framing,
        title=args.title, channel=args.channel,
        footer=args.footer, eyebrow=args.eyebrow, topline=args.topline,
        frame=args.frame, out=args.out,
        keep_last=args.keep_last, keep=args.keep,
    )
    run = runlog.Run(
        log, url=job.url, start=job.start, end=job.end, duration=job.duration,
        mode=job.mode, post=bool(args.post or args.load),
        follow_up=bool(args.follow_up),
    )

    try:
        result = pipeline.produce(job, run, progress=_printer())
    except Exception as exc:  # noqa: BLE001 - one place turns any failure into a message
        run.finish("failed", error=f"{type(exc).__name__}: {exc}")
        print(f"error: {exc}", file=sys.stderr)
        print(f"\nfull detail in {runlog.log_dir() / runlog.TEXT_LOG}", file=sys.stderr)
        return 1

    return _report(args, run, result)


def _printer() -> pipeline.Progress:
    """Print each stage as `[2/4] fetching audio ...`."""

    def say(stage: str, message: str) -> None:
        step = pipeline.STAGES.index(stage) + 1 if stage in pipeline.STAGES else 0
        print(f"[{step}/{len(pipeline.STAGES)}] {message}")

    return say


def _report(args: argparse.Namespace, run: runlog.Run, result: Result) -> int:
    print()
    print(f"clip     {result.clip}  ({result.size_mb:.1f} MB, {result.duration:.0f}s)")
    if result.size_bytes > render.PLATFORM_MAX_BYTES:
        # WhatsApp refuses an oversize file by never opening its editor, so a person
        # who is not told this discovers it as a composer that does nothing. T-014.
        print(
            f"warning  over WhatsApp's {render.PLATFORM_MAX_BYTES / 1_000_000:.2f} MB "
            "ceiling: the composer will take it and never open"
        )
    if result.frame:
        print(f"frame    {result.frame}")
    print(f"caption  {result.caption}")

    if args.follow_up:
        (args.out / f"{result.stem}.status2.txt").write_text(
            result.caption + "\n", encoding="utf-8"
        )

    posted = _post(args, run, result) if (args.post or args.load) else True
    if posted is None:
        # No answer from WhatsApp either way. Sending again is how a viewer gets the
        # same clip twice, so no command to resend is offered.
        print("\nWhatsApp gave no answer about this Status. Check it on your phone; "
              "post it by hand only if it is not there.")
    elif not posted:
        print("\nThe clip is fine, only the posting failed. Post it by hand, or retry with:")
        print(f"  .venv/bin/python scripts/wa_post.py video {result.clip} \\")
        print(f"      --caption-file {args.out / f'{result.stem}.caption.txt'} --send")
    elif not (args.post or args.load):
        print("\nPost the clip with that caption. WhatsApp makes the URL tappable.")
        if args.follow_up:
            print(
                f"Then post the text in {result.stem}.status2.txt "
                "as a second, text only Status."
            )
        if _copy_to_clipboard(result.caption):
            print("(caption copied to the clipboard)")

    run.finish("ok" if posted else "post_unconfirmed" if posted is None else "post_failed")

    if result.pruned:
        print(
            f"\npruned   {result.pruned.groups} older clip(s), "
            f"{result.pruned.bytes / 1_000_000:.1f} MB freed, "
            f"keeping the newest {args.keep_last}"
        )
    return 0 if posted else 3


def _post(args: argparse.Namespace, run: runlog.Run, result: Result) -> bool | None:
    """Load the clip into WhatsApp, sending it unless --load said not to.

    False if anything failed, None if WhatsApp never said whether the video was
    accepted. A posting failure is not a run failure: the clip exists and can be
    posted by hand, so this reports and carries on. Once the video is accepted, a
    failed follow up text is reported on its own and the video counts as posted.
    """
    try:
        found = post.discover(args.port)
        print(f"\n{'loading ' if args.load else 'posting '} through {found.detail}")
        def announce(attempt, delay, _exc):
            print(f"         WhatsApp refused it. Trying again in {delay:.0f}s "
                  f"(attempt {attempt + 1})")

        with run.stage("post_video"):
            if args.load:
                took = post.post_video(
                    result.clip, result.caption, port=found.port, send=False
                )
            else:
                took = post.send_with_retry(
                    result.clip, result.caption, port=found.port, on_retry=announce
                )
        run.set(post_port=found.port)
        if args.load:
            print("loaded   the composer is open with the caption in place.")
            print("         Press Send in that browser when you are ready.")
            run.set(loaded=True)
            return True
        print(f"posted   WhatsApp accepted it after {took:.0f}s")
        run.set(posted=True, post_seconds=round(took, 1))
        sheet.record(clip=result.clip, stem=result.stem, seconds=took,
                     browser=found.browser)

        if args.follow_up:
            try:
                with run.stage("post_text"):
                    second = post.send_text_with_retry(
                        result.caption, port=found.port, on_retry=announce)
            except post.PostError as exc:
                run.set(post_follow_up_error=str(exc))
                print(f"error    the follow up text did not go out: {exc}", file=sys.stderr)
                print("         The video is live; post the text by hand.", file=sys.stderr)
                return True
            print("posted   the follow up text Status is live")
            run.set(posted_follow_up=True)
            sheet.record(clip=result.clip, stem=result.stem, seconds=second,
                         browser=found.browser, note="follow up text")
        return True
    except post.StatusUnconfirmed as exc:
        run.set(post_error=str(exc))
        print(f"\nunsure   {exc}", file=sys.stderr)
        return None
    except post.PostError as exc:
        run.set(post_error=str(exc))
        print(f"\nerror    posting failed: {exc}", file=sys.stderr)
        return False


def _copy_to_clipboard(text: str) -> bool:
    for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if not shutil.which(cmd[0]):
            continue
        try:
            # xclip and wl-copy stay resident to serve the selection. Detach them
            # and close their streams, or they hold our stdout open forever and
            # anything piping wastatus appears to hang after it has finished.
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            proc.stdin.write(text.encode())
            proc.stdin.close()
            return True
        except Exception:  # noqa: BLE001 - clipboard is a convenience, never fatal
            return False
    return False


if __name__ == "__main__":
    raise SystemExit(main())
