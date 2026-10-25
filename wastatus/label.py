"""A page whose only job is to say which ports this session is on.

`wastatus serve` prints its port to the terminal it was started from, and that
terminal is often not the window you are looking at ten minutes later. With two
or three debug browsers open on this machine there is then nothing on screen that
says which Chrome window belongs to this tool, or which port its page is on.

So the browser this tool starts gets one extra tab, first in the strip, holding
this page. Its `<title>` names the port, which means the window title and the task
bar entry name it too, which is the whole point: the answer is readable without
opening anything.

It is a file on disk rather than a route on the server for one reason: it has to
survive the server. When `wastatus` is stopped the tab still says which ports the
session had, instead of turning into a connection error.
"""

from __future__ import annotations

import html
import os
import sys
import time
from pathlib import Path

NAME = "wastatus"
ACCENT = "#2ea36a"   # the page's own accent, so the tab is recognisably this tool


def cache_dir() -> Path:
    """Where the label is written. Not the output folder: this is not a result."""
    override = os.environ.get("WASTATUS_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":  # pragma: no cover - not the test platform
        return Path.home() / "Library" / "Caches" / NAME
    root = os.environ.get("XDG_CACHE_HOME")
    return (Path(root).expanduser() if root else Path.home() / ".cache") / NAME


def _rows(pairs: list[tuple[str, str]]) -> str:
    return "\n      ".join(
        f"<dt>{html.escape(term)}</dt><dd>{html.escape(value)}</dd>"
        for term, value in pairs if value
    )


def render(
    *, port: int, url: str, cdp_port: int, profile: str, out: str, also_on: str = "",
    when: str | None = None,
) -> str:
    """The page, as text. Separate from `write` so a test can read it without a disk."""
    stamp = when or time.strftime("%a %d %b %Y, %H:%M:%S %Z")
    body = _rows([
        ("This page", url),
        ("Also on", also_on),
        ("Posting browser", f"this one, Chrome debug port {cdp_port}"),
        ("Chrome profile", profile),
        ("Output folder", out),
    ])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>&#9679; {port} &middot; {NAME}</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh;
    display: flex; align-items: center; justify-content: center;
    background: #0b0f14; color: #e6edf3;
    font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    padding: 32px;
  }}
  .card {{
    width: 100%; max-width: 720px;
    background: #111820; border: 1px solid #1f2a37;
    border-top: 6px solid {ACCENT};
    border-radius: 14px; padding: 40px 44px;
    box-shadow: 0 20px 60px rgba(0,0,0,.45);
  }}
  .eyebrow {{
    font-size: 12px; letter-spacing: .18em; text-transform: uppercase;
    color: #7d8b9a; margin: 0 0 18px;
  }}
  .port {{
    font-size: 84px; font-weight: 800; line-height: 1;
    color: {ACCENT}; letter-spacing: -.02em; margin: 0;
    font-variant-numeric: tabular-nums;
  }}
  .name {{ font-size: 30px; font-weight: 600; margin: 10px 0 30px; }}
  dl {{ display: grid; grid-template-columns: minmax(0,auto) minmax(0,1fr);
       gap: 12px 22px; margin: 0; }}
  dt {{ color: #7d8b9a; font-size: 13px; white-space: nowrap; }}
  dd {{ margin: 0; font-size: 13px; font-family: ui-monospace, SFMono-Regular,
       Menlo, monospace; word-break: break-all; }}
  a {{ color: inherit; }}
  .foot {{ margin: 30px 0 0; padding-top: 18px; border-top: 1px solid #1f2a37;
          color: #61707f; font-size: 12px; }}
  .dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%;
         background: {ACCENT}; margin-right: 8px; vertical-align: baseline; }}
</style>
</head>
<body>
  <div class="card">
    <p class="eyebrow">WhatsApp Status &middot; local page</p>
    <p class="port">{port}</p>
    <p class="name"><span class="dot"></span>{NAME}</p>
    <dl>
      {body}
    </dl>
    <p class="foot">Started {html.escape(stamp)} &middot; open
      <a href="{html.escape(url, quote=True)}">{html.escape(url)}</a> to use the tool.
      This tab is only a label: keep it and the window title keeps naming the port.</p>
  </div>
</body>
</html>
"""


def write(**fields) -> Path:
    """Write the label and return its path. One file per page port, overwritten.

    Per port rather than per run, so restarting on the same port does not leave a
    trail of stale labels behind in the cache.
    """
    directory = cache_dir()
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / f"session-{fields['port']}.html"
    dest.write_text(render(**fields), encoding="utf-8")
    return dest
