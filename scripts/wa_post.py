#!/usr/bin/env python3
"""Standalone access to the Status composer, for debugging.

The posting logic itself lives in `wastatus/post.py`, which `wastatus --post`
uses. This script is the manual door into the same functions: load a composer
without sending, press Send later, back out, or grab a screenshot.

  wa_post.py video <file.mp4> --caption "text" [--send]
  wa_post.py video <file.mp4> --caption-file <file.caption.txt> --send
  wa_post.py text  "text"                      [--send]
  wa_post.py send            click Send on whatever composer is open
  wa_post.py cancel          back out of an open composer
  wa_post.py shot <out.png>  screenshot the page
  wa_post.py delete-all --yes  delete every Status on your account

Without --send the composer is left loaded and unsent, so it can be inspected
first. Requires a Chrome with remote debugging on --port and an already logged in
WhatsApp Web tab.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wastatus import post  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="wa_post.py")
    ap.add_argument(
        "action", choices=["video", "text", "send", "cancel", "shot", "delete-all"]
    )
    ap.add_argument("value", nargs="?")
    ap.add_argument("--caption", default="")
    ap.add_argument(
        "--caption-file", type=Path, default=None,
        help="read the caption from a file, e.g. the .caption.txt beside a clip",
    )
    ap.add_argument("--send", action="store_true", help="press Send, rather than leaving it loaded")
    ap.add_argument(
        "--yes", action="store_true",
        help="required by delete-all, which is irreversible",
    )
    ap.add_argument("--port", type=int, default=post.default_port())
    args = ap.parse_args()

    try:
        with post.Page(args.port) as page:
            post.require_logged_in(page)

            if args.action == "video":
                path = Path(args.value).expanduser().resolve()
                if not path.is_file():
                    return _fail(f"no such file: {path}")
                caption = args.caption
                if args.caption_file:
                    caption = args.caption_file.read_text(encoding="utf-8").strip()
                post.load_video(page, path, caption)
                print(f"loaded {path.name} into the Status composer")
                _maybe_send(page, args.send)

            elif args.action == "text":
                post.load_text(page, args.value or "")
                print("text status composed")
                _maybe_send(page, args.send)

            elif args.action == "send":
                _maybe_send(page, True)

            elif args.action == "cancel":
                post.cancel(page)
                print("closed the composer")

            elif args.action == "delete-all":
                if not args.yes:
                    return _fail(
                        "delete-all removes every Status on your account and cannot "
                        "be undone. Pass --yes if that is what you want"
                    )
                removed = post.delete_all_statuses(page)
                print(f"deleted {removed} status(es)")

            elif args.action == "shot":
                print(f"saved {page.screenshot(Path(args.value))}")
    except post.PostError as exc:
        return _fail(str(exc))
    return 0


def _maybe_send(page: post.Page, send: bool) -> None:
    if not send:
        print("not sent, run: wa_post.py send")
        return
    before = post.latest_own_status(page)
    sent_at = time.time()
    post.click_send(page)
    took = post.confirm_sent(page, before, sent_at)
    print(f"sent, WhatsApp accepted it after {took:.0f}s")


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
