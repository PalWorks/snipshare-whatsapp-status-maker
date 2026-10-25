#!/usr/bin/env python3
"""Screenshot a page in the debug Chrome, at a chosen size and colour scheme.

Design review needs to see the real page, not an imagined one, and at the widths and
themes it is actually used at. This drives the same Chrome `--post` uses, so no
browser window has to be arranged by hand.

  shot.py http://127.0.0.1:8765/ out.png
  shot.py http://127.0.0.1:8765/ narrow.png --width 430 --dark --full
  shot.py http://127.0.0.1:8765/ guides.png --click "#guides"

Requires a Chrome with --remote-debugging-port (see LOCAL_SETUP.md). The tab is
opened and closed again, so nothing is left behind.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wastatus import post  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="shot.py")
    ap.add_argument("url")
    ap.add_argument("out", type=Path)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--dark", action="store_true", help="emulate a dark colour scheme")
    ap.add_argument("--full", action="store_true", help="capture past the viewport")
    ap.add_argument("--click", help="CSS selector to click before capturing")
    ap.add_argument("--wait", type=float, default=2.5, help="seconds to settle")
    ap.add_argument("--port", type=int, default=post.default_port())
    args = ap.parse_args()

    with urllib.request.urlopen(
        f"http://127.0.0.1:{args.port}/json/version", timeout=5
    ) as response:
        browser = json.load(response)["webSocketDebuggerUrl"]

    import websocket

    control = websocket.create_connection(browser, timeout=25, suppress_origin=True)
    target = _cmd(control, 1, "Target.createTarget", url="about:blank")["targetId"]
    try:
        page = post.Page.__new__(post.Page)  # a session on our new tab, not a lookup
        with urllib.request.urlopen(
            f"http://127.0.0.1:{args.port}/json/list", timeout=5
        ) as response:
            tab = next(t for t in json.load(response) if t.get("id") == target)
        page.ws = websocket.create_connection(
            tab["webSocketDebuggerUrl"], timeout=60, suppress_origin=True
        )
        page.n, page.events = 0, []
        for method in ("Page.enable", "Runtime.enable"):
            page.send_cmd(method)
        page.send_cmd(
            "Emulation.setEmulatedMedia",
            media="screen",
            features=[{
                "name": "prefers-color-scheme",
                "value": "dark" if args.dark else "light",
            }],
        )
        page.send_cmd(
            "Emulation.setDeviceMetricsOverride",
            width=args.width, height=args.height, deviceScaleFactor=1, mobile=False,
        )
        page.send_cmd("Page.navigate", url=args.url)
        time.sleep(args.wait)
        if args.click:
            page.js(
                f"""(() => {{ const e = document.querySelector({json.dumps(args.click)});
                              if (e) e.click(); return !!e; }})()"""
            )
            time.sleep(1.0)
        data = page.send_cmd(
            "Page.captureScreenshot", format="png",
            captureBeyondViewport=bool(args.full),
        )["data"]
        args.out.write_bytes(base64.b64decode(data))
        print(f"saved {args.out} ({args.width}x{args.height}, "
              f"{'dark' if args.dark else 'light'})")
        page.close()
    finally:
        _cmd(control, 99, "Target.closeTarget", targetId=target)
        control.close()
    return 0


def _cmd(ws, ident: int, method: str, **params):
    ws.send(json.dumps({"id": ident, "method": method, "params": params}))
    while True:
        message = json.loads(ws.recv())
        if message.get("id") == ident:
            if "error" in message:
                sys.exit(f"{method}: {message['error']}")
            return message.get("result", {})


if __name__ == "__main__":
    raise SystemExit(main())
