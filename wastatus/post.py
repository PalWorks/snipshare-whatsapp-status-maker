"""Posts a Status by driving WhatsApp Web over the Chrome DevTools Protocol.

This is the desktop posting route. It uses the real web client in a real logged
in browser, so unlike an unofficial protocol library it carries no account risk
beyond ordinary web use. See DECISIONS.md D-012.

Requires a Chrome started with `--remote-debugging-port` and an already logged in
WhatsApp Web tab. Everything here raises `PostError` rather than exiting, so the
caller decides what a failure means.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

try:  # optional: only --post needs it
    import websocket
except ImportError:  # pragma: no cover - exercised by the CLI's error path
    websocket = None  # type: ignore[assignment]

log = logging.getLogger("wastatus")

TIMEOUT = 25.0
DISCOVER_TIMEOUT = 1.0  # probing a port that is not there must not stall the page
COMPOSER_TIMEOUT = 75.0  # a cold, throttled tab is slow to build the media editor
SEND_TIMEOUT = 240.0

# Other debug browsers people leave running. Chrome only exposes the protocol when
# it was started with --remote-debugging-port, so this is the whole search space:
# there is no way to reach a browser that was started without the switch.
DEFAULT_PORTS = (9222, 9223, 9224, 9225, 9226)
PORTS_ENV = "WASTATUS_CDP_PORTS"
MAX_RANGE = 64  # a wider range is a typo, and probing it would stall the page

# Chrome 136 and later ignore --remote-debugging-port when the default profile
# directory is used, so the posting browser needs a profile of its own. It keeps
# its own WhatsApp login, which is why the QR code is scanned once and not again.
# https://developer.chrome.com/blog/remote-debugging-port
CHROME_BINARIES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)

# The caption box inside the Status composer. It is scoped away from the chat's
# own message box, which is contenteditable too: a bare div[contenteditable="true"]
# matched that one whenever a conversation was open, so the composer looked ready
# before it was and the caption was typed into somebody's chat. Two ways of naming
# the chat box, because either could be reworded on its own.
COMPOSER = (
    'div[contenteditable="true"]'
    ':not([data-testid="conversation-compose-box-input"])'
    ':not([aria-placeholder="Type a message"])'
)
# The composer's Send control, the second half of "the editor is really open": the
# caption box is a selector, the Send button beside it is the editor. It used to be
# matched by its icon alone. By 2026-10-24 WhatsApp had dropped `data-icon` from it,
# so every load waited for a Send button that was already on screen. It is now
# matched by label as well: "Send 1 selected" in the media composer, a bare "Send"
# in the text one. The icon stays first, for a build that still carries it. See
# DECISIONS.md D-079.
SEND_ICON = (
    '[data-icon^="wds-ic-send"],'
    '[aria-label^="Send "][aria-label$=" selected"],'
    '[aria-label="Send"]'
)
# "Is a Status composer already open", asked before touching anything. Narrower
# than SEND_ICON on purpose: a chat with a typed reply has a bare "Send" button
# too, and mistaking that for a composer would back out of the chat. The text
# composer is recognised by its own close control instead.
COMPOSER_OPEN = (
    '[data-icon^="wds-ic-send"],'
    '[aria-label^="Send "][aria-label$=" selected"],'
    '[aria-label="Close status posting view"]'
)

# What WhatsApp Web records against a message it has sent. Its own word for what
# became of it, which is the only honest answer to "did that go out".
ACK_ERROR = -1    # WhatsApp refused it
ACK_PENDING = 0   # written down, no answer yet
ACK_SERVER = 1    # WhatsApp has it; 2 delivered, 3 read, 4 played

STATUS_DB = "model-storage"
STATUS_KEY_PREFIX = "true_status@broadcast_"


class PostError(RuntimeError):
    """Anything that stopped us posting. The message is shown to the user."""


class StatusRefused(PostError):
    """WhatsApp answered, and the answer was no.

    A definite negative, which is what makes it safe to send again: nothing went
    out, so a retry cannot double post.
    """


class StatusUnconfirmed(PostError):
    """No answer either way, which is not the same as a refusal.

    Never retried. The Status may yet go out, and sending a second one to be sure
    is how a viewer gets the same clip twice.
    """


# -- which ports to look on ------------------------------------------------

def candidate_ports() -> tuple[int, ...]:
    """The debug ports to look on, in order. The first one is also the default.

    Read at call time rather than frozen into a constant, because which ports are
    worth looking on is a fact about one machine. Another tool that opens debug
    browsers of its own, an IDE for instance, takes the low ones and never gives
    them back. `WASTATUS_CDP_PORTS` takes a list, `9230,9231`, or a range,
    `9230-9235`, or both.
    """
    raw = (os.environ.get(PORTS_ENV) or "").strip()
    if not raw:
        return DEFAULT_PORTS
    ports = _parse_ports(raw)
    if not ports:
        log.warning(
            "%s is %r, which is not a list or a range of ports. Using %s",
            PORTS_ENV, raw, ", ".join(str(port) for port in DEFAULT_PORTS),
        )
        return DEFAULT_PORTS
    return ports


def _parse_ports(raw: str) -> tuple[int, ...]:
    """`9230-9235,9222` as a tuple. Empty for anything malformed, never partial."""
    found: list[int] = []
    for piece in raw.replace(" ", "").split(","):
        if not piece:
            continue
        low, dash, high = piece.partition("-")
        try:
            first = int(low)
            last = int(high) if dash else first
        except ValueError:
            return ()
        if not (1 <= first <= 65535 and 1 <= last <= 65535):
            return ()
        if last < first or last - first > MAX_RANGE:
            return ()
        found.extend(range(first, last + 1))
    # Order matters and repeats do not: the first entry is the preferred port.
    seen: set[int] = set()
    return tuple(port for port in found if not (port in seen or seen.add(port)))


def default_port() -> int:
    """The port to prefer, and the one a browser we start is started on."""
    return candidate_ports()[0]


def port_owner(port: int) -> str:
    """Which browser asked for this debug port, named by its profile.

    "" when nothing can be said, which is not an error and is the normal answer on
    a machine that is not Linux. It reads /proc rather than asking who holds the
    socket, because the useful question is who *asked* for the port: a browser that
    lost the race and fell back to IPv6 only still answers it, and that browser is
    exactly the one somebody is confused about. See RUNBOOK.md.
    """
    want = f"--remote-debugging-port={port}"
    try:
        entries = os.listdir("/proc")
    except OSError:  # pragma: no cover - not Linux
        return ""
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as handle:
                raw = handle.read()
        except OSError:
            continue  # it exited while we were looking, or it is not ours
        described = _describe(raw, want)
        if described:
            return f"{described} (pid {entry})"
    return ""


_PROFILE = re.compile(r"--user-data-dir=(\S+)")


def _describe(raw: bytes, want: str) -> str:
    """"chrome, profile chrome-wastatus", or "" if this is not the process.

    Two shapes, because Chrome is not like other programs: it rewrites its own
    argv into one space separated string, so the NUL separators /proc normally
    holds are simply not there. A profile path containing a space cannot survive
    that, and nothing here can put it back, which is why only the last part of
    the path is shown.
    """
    line = raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
    args = line.split()
    if not args or want not in args:
        return ""
    who = os.path.basename(args[0]) or "a browser"
    found = _PROFILE.search(line)
    if found:
        who += f", profile {os.path.basename(found.group(1).rstrip('/'))}"
    return who


def in_use(port: int) -> bool:
    """Whether starting a browser on this port would collide with something.

    Both address families, because binding only one of them is the trap this
    guards against: a port that looks free on IPv4 and is held on IPv6 produces a
    browser that starts, prints a listening address, and cannot be reached.
    """
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.3)
                if probe.connect_ex((host, port)) == 0:
                    return True
        except OSError:  # pragma: no cover - a host without IPv6
            continue
    # A browser that asked for the port but has not finished binding it yet.
    return bool(port_owner(port))


def free_port(ports: Iterable[int] | None = None) -> int:
    """The first candidate port nothing has taken.

    Raises rather than guessing at a port outside the list, because a browser
    started somewhere `discover` does not look is a browser nothing will find.
    """
    candidates = tuple(candidate_ports() if ports is None else ports)
    for port in candidates:
        if not in_use(port):
            return port
    raise PostError(
        "every debug port is already taken ("
        + ", ".join(str(port) for port in candidates)
        + f"). Close one of those browsers, or widen {PORTS_ENV} in .env"
    )


# -- reaching one -----------------------------------------------------------

def _cdp_get(port: int, path: str, timeout: float = 5.0, host: str = "127.0.0.1"):
    url = f"http://{host}:{port}{path}"
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.load(response)


def _answers(port: int, host: str = "127.0.0.1") -> bool:
    try:
        _cdp_get(port, "/json/version", DISCOVER_TIMEOUT, host=host)
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return False
    return True


def _silence(port: int, exc: Exception) -> str:
    """The most useful sentence about a debug port that did not answer on IPv4."""
    owner = port_owner(port)
    if _answers(port, host="[::1]"):
        # Chrome prints `bind() failed: Address already in use` and then carries on
        # with IPv6 only, so a port somebody else already held looks like a browser
        # that started fine. Everything here asks 127.0.0.1, which is the other
        # browser. This one cost an afternoon; see RUNBOOK.md.
        return (
            f"port {port} is only half open. Something else already had it on IPv4, "
            f"so {owner or 'the browser you started'} bound [::1] only and this tool "
            "cannot reach it. Start that browser again on a port nothing holds"
        )
    if owner:
        return (
            f"{owner} asked for port {port}, but nothing is answering there. "
            "It may still be starting, or it may have failed to bind"
        )
    return (
        f"no Chrome answering on 127.0.0.1:{port} ({exc}). Start one with "
        f"--remote-debugging-port={port} and open web.whatsapp.com in it"
    )


def find_tab(port: int, timeout: float = 5.0) -> dict:
    """The logged in WhatsApp Web page on this debug port."""
    try:
        tabs = _cdp_get(port, "/json/list", timeout)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise PostError(_silence(port, exc)) from exc
    for tab in tabs:
        if tab.get("type") == "page" and "web.whatsapp.com" in tab.get("url", ""):
            return tab
    # Naming the browser matters more here than anywhere else. Without it this
    # sentence describes somebody else's browser as though it were yours, which
    # reads as "log in again" when the answer is "that is the wrong browser".
    owner = port_owner(port)
    raise PostError(
        f"Chrome is on port {port} but no WhatsApp Web tab is open in it"
        + (f". That one is {owner}" if owner else "")
        + ". Open https://web.whatsapp.com and log in first"
    )


@dataclass
class Endpoint:
    """A debug browser that has a WhatsApp Web tab in it."""

    port: int
    browser: str
    tab: dict

    @property
    def detail(self) -> str:
        return f"{self.browser or 'a debug browser'} on port {self.port}"


def browser_name(port: int, timeout: float = DISCOVER_TIMEOUT) -> str:
    try:
        return str(_cdp_get(port, "/json/version", timeout).get("Browser") or "")
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return ""


def discover(
    preferred: int | None = None, extra: Iterable[int] | None = None
) -> Endpoint:
    """Find a browser to post through, preferring the configured port.

    Any Chrome started with a debug port is a candidate, so opening the page in a
    browser that already has WhatsApp Web works without naming its port. A browser
    started without the switch cannot be reached at all: it exposes no protocol,
    and a page on loopback cannot drive another origin's tab. That is why there is
    a dedicated posting profile rather than "whichever Chrome you happen to use".
    """
    # Read the candidates at call time, not at import time: a default argument
    # would freeze the list and quietly ignore anything that rebinds it, and the
    # list itself comes from the environment.
    candidates = candidate_ports() if extra is None else extra
    preferred = default_port() if preferred is None else preferred
    ports = [preferred] + [port for port in candidates if port != preferred]
    problems: list[str] = []
    for port in ports:
        try:
            tab = find_tab(port, timeout=DISCOVER_TIMEOUT)
        except PostError as exc:
            problems.append(str(exc))
            continue
        return Endpoint(port=port, browser=browser_name(port), tab=tab)
    # The configured port's complaint is the one worth showing: the others are
    # ports nobody asked for.
    raise PostError(problems[0] if problems else "no debug browser found")


# -- starting a browser to post through -----------------------------------

def profile_dir() -> Path:
    """Where the posting browser keeps its own WhatsApp login."""
    override = os.environ.get("WASTATUS_CHROME_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":  # pragma: no cover - not the test platform
        return Path.home() / "Library" / "Application Support" / "wastatus" / "chrome"
    return Path.home() / ".config" / "chrome-wastatus"


def chrome_binary() -> str | None:
    for name in CHROME_BINARIES:
        found = shutil.which(name) or (name if Path(name).is_file() else None)
        if found:
            return found
    return None


CHROME_LOG = "chrome.log"
# Truncated rather than rotated. The interesting part is always the last launch,
# and nobody is going to grep a browser's chatter from last week.
CHROME_LOG_MAX = 2_000_000


def chrome_log_path() -> "Path | None":
    from . import runlog  # here, so `runlog` may keep importing this module

    try:
        directory = runlog.log_dir()
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:  # pragma: no cover - an unwritable log directory
        return None
    return directory / CHROME_LOG


def _chrome_log():
    """A file to point Chrome's own output at, or None if there cannot be one.

    Everything Chrome said used to go to /dev/null. On 2026-08-22 a browser this
    tool started answered once and then exited, and there was nothing whatever to
    read about why. A browser that dies is exactly the case where its own last
    words are the only evidence, so they are kept now.

    Never fatal. A log that cannot be opened means a browser started without one,
    which is what happened every time before this existed.
    """
    path = chrome_log_path()
    if path is None:
        return None
    try:
        if path.is_file() and path.stat().st_size > CHROME_LOG_MAX:
            path.unlink()
        handle = path.open("a", encoding="utf-8", errors="replace")
        handle.write(
            f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} launching =====\n"
        )
        handle.flush()
    except OSError as exc:
        log.debug("chrome output is not being captured: %s", exc)
        return None
    return handle


_PORT_ARG = re.compile(r"--remote-debugging-port=(\d+)")


def running_profile_port(profile: Path | None = None) -> int | None:
    """The debug port of a browser already using the posting profile, if any.

    Chrome hands a second launch on the same profile over to the first one and
    then exits, ignoring the new `--remote-debugging-port` completely. So starting
    a browser on a profile that is already open looks like it worked, opens a
    window, and exposes no protocol at all. Finding the one that is already there
    and using its port is the only honest answer to that.

    None when nothing is using it, and None on a platform without /proc, where the
    old behaviour of trying anyway is no worse than it was.
    """
    want = f"--user-data-dir={profile or profile_dir()}"
    try:
        entries = os.listdir("/proc")
    except OSError:  # pragma: no cover - not Linux
        return None
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as handle:
                raw = handle.read()
        except OSError:
            continue
        line = raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
        if want not in line.split():
            continue
        found = _PORT_ARG.search(line)
        if found:
            return int(found.group(1))
    return None


def launch_browser(
    port: int | None = None, first: Path | None = None, page: str = ""
) -> str:
    """Start the posting browser on `port` with WhatsApp Web open.

    Returns the executable used. The first launch shows a QR code to scan; after
    that the profile stays logged in.

    `first` is an optional local page opened ahead of WhatsApp Web, which is the
    label written by `label.write`. It goes first so the window title names the
    session rather than saying WhatsApp, and that costs nothing: `Page.__init__`
    calls `Page.bringToFront` before it touches anything, so the posting tab is
    foregrounded whether or not it started that way.

    `page` is the tool's own page, opened between the two. One window then holds
    the whole session: what it is, what it does, and what it posts through.
    """
    port = default_port() if port is None else port
    already = running_profile_port()
    if already is not None and already != port:
        raise PostError(
            f"the posting profile is already open in a browser on debug port "
            f"{already}. Chrome would hand this launch to that one and ignore "
            f"port {port}, so nothing would be listening. Close that window, or "
            f"use port {already}"
        )
    exe = chrome_binary()
    if exe is None:
        raise PostError(
            "no Chrome or Chromium found on PATH. Install one, or start it yourself "
            f"with --remote-debugging-port={port}"
        )
    profile = profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    # Chrome's own output, kept rather than discarded. `bind() failed` and the
    # non-default-profile refusal are both printed here and nowhere else, and both
    # are things this tool has spent an afternoon on.
    handle = _chrome_log()
    sink = handle if handle is not None else subprocess.DEVNULL
    try:
        subprocess.Popen(
            [
                exe,
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile}",
                "--no-first-run",
                "--no-default-browser-check",
                *([first.resolve().as_uri()] if first is not None else []),
                *([page] if page else []),
                "https://web.whatsapp.com",
            ],
            stdout=sink,
            stderr=subprocess.STDOUT if handle is not None else subprocess.DEVNULL,
            start_new_session=True,
        )
    finally:
        # The child has its own descriptor now. Ours would otherwise be held for
        # the life of this process, and the file could never be truncated.
        if handle is not None:
            handle.close()
    log.info("started %s on debug port %d with profile %s", exe, port, profile)
    return exe


def open_tab(port: int, url: str, timeout: float = 5.0) -> None:
    """Open `url` as a new tab in the debug browser on `port`.

    For a browser this tool did not start, which therefore never saw our command
    line. `PUT` and not `GET`: Chrome 111 stopped answering `GET /json/new` to close
    a hole where any page in that browser could have opened tabs in it.

    The URL is the query string itself, not a named parameter, which is the shape
    the DevTools HTTP handler documents. Chrome unescapes it, so it is quoted here
    rather than pasted in raw.
    """
    target = (f"http://127.0.0.1:{port}/json/new?"
              f"{urllib.parse.quote(url, safe='')}")
    request = urllib.request.Request(target, method="PUT")
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            pass
    except (urllib.error.URLError, OSError) as exc:
        raise PostError(f"could not open a tab on port {port}: {exc}") from exc
    log.info("opened %s in the browser on port %d", url, port)


class Page:
    """A CDP session against one page."""

    def __init__(self, port: int | None = None, *, foreground: bool = True) -> None:
        port = default_port() if port is None else port
        if websocket is None:
            raise PostError(
                "posting needs the websocket-client package: "
                ".venv/bin/pip install -r requirements.txt"
            )
        tab = find_tab(port)
        try:
            self.ws = websocket.create_connection(
                tab["webSocketDebuggerUrl"], timeout=TIMEOUT, suppress_origin=True
            )
        except Exception as exc:  # noqa: BLE001 - any handshake failure is fatal here
            raise PostError(f"could not attach to the WhatsApp Web tab: {exc}") from exc
        self.n = 0
        self.events: list[dict] = []
        for method in ("Page.enable", "DOM.enable", "Runtime.enable"):
            self.send_cmd(method)
        # Chrome throttles background tabs, and a throttled WhatsApp Web takes
        # long enough to build the media editor that the wait below times out.
        # Foreground the tab first. Failing that is not fatal, only slower.
        #
        # `foreground=False` is for the checks that nobody asked to watch. Taking
        # the screen is right when a composer is being loaded for you to look at,
        # and wrong when the answer is a line of text on the page you are already
        # reading: a clip finishing used to throw you into the WhatsApp window.
        if foreground:
            try:
                self.send_cmd("Page.bringToFront")
                self.unminimise()
            except PostError as exc:
                log.debug("could not foreground the tab (%s)", exc)

    def unminimise(self) -> None:
        """Restore a minimised window, best effort.

        Bringing a tab to front does nothing for a window that is not on screen,
        and a composer the user is meant to inspect has to be visible.
        """
        window = self.send_cmd("Browser.getWindowForTarget")
        if window.get("bounds", {}).get("windowState") == "minimized":
            self.send_cmd(
                "Browser.setWindowBounds",
                windowId=window["windowId"],
                bounds={"windowState": "normal"},
            )

    # -- plumbing ---------------------------------------------------------

    def send_cmd(self, method: str, **params) -> dict:
        self.n += 1
        want = self.n
        self.ws.send(json.dumps({"id": want, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == want:
                if "error" in msg:
                    raise PostError(f"CDP error on {method}: {msg['error']}")
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg)
            # Anything else is a late reply to a call we already gave up on.

    def js(self, expression: str):
        result = self.send_cmd(
            "Runtime.evaluate",
            expression=expression,
            returnByValue=True,
            awaitPromise=True,
            userGesture=True,
        )
        if result.get("exceptionDetails"):
            raise PostError(f"JS error: {result['exceptionDetails'].get('text')}")
        return result.get("result", {}).get("value")

    def js_soft(self, expression: str, default=None):
        """`js`, but a busy or unresponsive browser yields `default`.

        Chrome stops servicing the debug protocol while it uploads a Status, so a
        timeout during polling is normal and must not be treated as a failure.
        """
        try:
            return self.js(expression)
        except Exception as exc:  # noqa: BLE001 - timeouts and transport errors alike
            log.debug("CDP poll did not answer (%s), treating as unknown", exc)
            return default

    def wait_event(self, method: str, timeout: float = TIMEOUT) -> dict:
        for event in self.events:
            if event.get("method") == method:
                self.events.remove(event)
                return event
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.ws.settimeout(max(0.5, deadline - time.monotonic()))
            try:
                msg = json.loads(self.ws.recv())
            except Exception:  # noqa: BLE001 - a quiet socket is just a timeout
                break
            if msg.get("method") == method:
                self.ws.settimeout(TIMEOUT)
                return msg
            if "method" in msg:
                self.events.append(msg)
        self.ws.settimeout(TIMEOUT)
        raise PostError(f"timed out waiting for {method}")

    def wait_for(self, condition: str, what: str, timeout: float = TIMEOUT) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.js_soft(f"!!({condition})", default=False):
                return
            time.sleep(0.4)
        raise PostError(f"timed out waiting for {what}")

    def screenshot(self, dest: Path) -> Path:
        data = self.send_cmd("Page.captureScreenshot", format="png")["data"]
        dest.write_bytes(base64.b64decode(data))
        return dest

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001 - closing a dead socket is not interesting
            pass

    def __enter__(self) -> "Page":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


# -- page interactions ----------------------------------------------------

# WhatsApp's own words for the two Status choices, and for the button that opens
# them. They are not an API and they change: "Photo and video" was "Photo and
# video" from the first commit until some time between the last good post at
# 2026-08-19 22:53 and 2026-08-20 19:42, when it became "Photos & videos" and
# moved behind an "Add Status" button. Exact string equality found neither, so
# every post failed. Matching is on words now, and on a list, so a rewording is
# far more likely to land on something already here. See DECISIONS.md D-041.
ADD_STATUS = ("Add Status", "Add status", "New status")
PHOTO_ITEM = ("Photos & videos", "Photo and video", "Photos and videos",
              "Photo & video", "Photos, videos")
TEXT_ITEM = ("Text", "Text status")


def _canon(label: str) -> str:
    """A label reduced to the words that carry its meaning.

    "Photos & videos" and "Photo and video" both come out as "photo video", so a
    label that is reworded the way WhatsApp rewords them still matches. Case,
    punctuation, the joining word and a trailing plural all go. The trailing "s"
    rule is crude, and turns "Status" into "statu", which is harmless because both
    sides of the comparison get the same treatment.
    """
    words = set()
    for word in re.split(r"[^a-z0-9]+", label.lower()):
        if not word or word == "and":
            continue
        words.add(word[:-1] if len(word) > 3 and word.endswith("s") else word)
    return " ".join(sorted(words))


# A menu item is looked for first and on its own, because the words are short and
# common: "Text" as bare text content appears all over a chat list, and clicking
# the first thing that says it would open somebody's conversation.
_MATCH = """
(() => {
  const want = new Set(%s);
  const doClick = %s;
  const canon = (s) => [...new Set((s || '')
      .toLowerCase().split(/[^a-z0-9]+/)
      .filter((w) => w && w !== 'and')
      .map((w) => (w.length > 3 && w.endsWith('s')) ? w.slice(0, -1) : w))]
      .sort().join(' ');
  const hunt = (selector) => [...document.querySelectorAll(selector)].find((e) =>
    want.has(canon(e.getAttribute('aria-label'))) || want.has(canon(e.textContent)));
  const hit = hunt('[role=menuitem]')
           || hunt('div[role=button],button,li,span,div');
  if (!hit) return 'not found';
  if (!doClick) return 'found';
  (hit.closest('[role=menuitem],div[role=button],button,li') || hit).click();
  return 'clicked';
})()
"""


def _match(page: Page, labels: Sequence[str], *, click: bool) -> str:
    wanted = json.dumps(sorted({_canon(label) for label in labels}))
    return page.js(_MATCH % (wanted, "true" if click else "false"))


def has_control(page: Page, labels: Sequence[str]) -> bool:
    """Is any of these labels on the page right now? Clicks nothing."""
    return _match(page, labels, click=False) != "not found"


def click_any(page: Page, labels: Sequence[str]) -> bool:
    """Click the first control matching any of `labels`. False if none is there."""
    if _match(page, labels, click=True) != "clicked":
        return False
    time.sleep(0.6)
    return True


def click_one_of(page: Page, labels: Sequence[str], what: str) -> None:
    if not click_any(page, labels):
        raise PostError(
            f"could not find {what} in WhatsApp Web. It was labelled "
            f"{labels[0]!r}, and WhatsApp renames these without warning. "
            f"If it has been renamed again, the list to widen is at the top of "
            f"wastatus/post.py"
        )


def require_logged_in(page: Page) -> None:
    """Fail before touching anything if this is the QR screen, not the app."""
    ready = page.js(
        """(() => !!document.querySelector('button[aria-label="Status"]')
                 || !!document.querySelector('#pane-side'))()"""
    )
    if not ready:
        raise PostError(
            "the WhatsApp Web tab is not logged in (no chat list). "
            "Scan the QR code in that browser, then run this again"
        )


def open_status_tab(page: Page) -> None:
    page.js(
        """(() => { const b = document.querySelector('button[aria-label="Status"]');
                    if (b && b.getAttribute('aria-pressed') !== 'true') b.click();
                    return true; })()"""
    )
    time.sleep(0.8)


def open_status_menu(page: Page, item: Sequence[str]) -> None:
    """Make the Status choices visible, whichever build of WhatsApp Web this is.

    Older builds put "Photo and video" and "Text status" straight into the Status
    panel. Newer ones put both behind an "Add Status" button, and the panel on its
    own offers nothing to click. Asking whether the choice is already there, rather
    than always pressing, keeps this working on both: on the old build the press
    would have found nothing, and on the new one pressing a second time would close
    the menu that was already open.
    """
    if has_control(page, item):
        return
    click_any(page, ADD_STATUS)
    time.sleep(0.8)


def open_chats_tab(page: Page) -> None:
    """Put the chat list back, best effort.

    The Status panel is a place the tool goes to do its work, not a place it should
    leave you. Anything that fails here leaves WhatsApp showing Status, which is
    untidy and nothing worse, so it is asked softly and never raises.
    """
    page.js_soft(
        """(() => { const b = document.querySelector('button[aria-label="Chats"]');
                    if (b && b.getAttribute('aria-pressed') !== 'true') b.click();
                    return true; })()""",
        default=False,
    )


def on_status_tab(page: Page) -> bool:
    """Is the Status panel the one already showing?

    True when it cannot be told, because the caller uses this to decide whether to
    put something back, and putting back what was never moved is the worse mistake.
    """
    return bool(page.js_soft(
        """(() => { const b = document.querySelector('button[aria-label="Status"]');
                    return !b || b.getAttribute('aria-pressed') === 'true'; })()""",
        default=True,
    ))


def close_menu(page: Page) -> None:
    """Back out of an open menu without choosing anything from it."""
    for kind in ("keyDown", "keyUp"):
        page.send_cmd("Input.dispatchKeyEvent", type=kind, key="Escape",
                      code="Escape", windowsVirtualKeyCode=27, nativeVirtualKeyCode=27)
    time.sleep(0.4)


def check_controls(port: int | None = None) -> dict[str, object]:
    """Are the Status controls still where this tool expects them?

    Answers before a post is attempted rather than during one, TASKS.md T-026. It
    opens the Add Status menu, looks, and closes it again, which is the only way to
    know: the two choices do not exist in the page until that menu is open.

    **It refuses to look while a composer is open.** A composer holds a clip that
    somebody is about to send, and a menu opened underneath it would be a check that
    broke the thing it was checking.

    **It does not take the screen, and it puts the panel back.** Unlike a post,
    nothing here is for you to look at: it runs unasked when a clip is made, so it
    leaves the browser where it found it.

    Returns `ok`, and when that is False a `detail` naming what is actually on the
    menu, so the message says what to add to the list rather than what is missing
    from it.
    """
    try:
        # Not foregrounded: nobody asked for this check, it runs the moment a clip
        # is made, and the answer is a line of text on a page in another window.
        # Foregrounding it threw you into the WhatsApp window every time a render
        # finished, mid sentence, with the clip you wanted to watch left behind.
        with Page(port, foreground=False) as page:
            require_logged_in(page)
            if page.js_soft(f"!!document.querySelector('{COMPOSER_OPEN}')", default=False):
                return {"ok": True, "checked": False,
                        "detail": "a composer is open, so nothing was touched"}
            # Where you had WhatsApp, so it can be left that way.
            was_on_status = on_status_tab(page)
            open_status_tab(page)
            opened = False
            if not has_control(page, PHOTO_ITEM):
                opened = click_any(page, ADD_STATUS)
            found = {
                "photo": has_control(page, PHOTO_ITEM),
                "text": has_control(page, TEXT_ITEM),
            }
            on_offer = page.js_soft(
                """(() => JSON.stringify([...document.querySelectorAll('[role=menuitem]')]
                     .map(e => (e.getAttribute('aria-label') || '').trim())
                     .filter(Boolean)))()""",
                default="[]",
            )
            if opened:
                close_menu(page)
            if not was_on_status:
                open_chats_tab(page)
    except PostError as exc:
        # No browser, or not logged in. That is the WhatsApp Web check's business and
        # it says so already; this one has nothing to add.
        return {"ok": True, "checked": False, "detail": str(exc)}

    if found["photo"] and found["text"]:
        return {"ok": True, "checked": True, "detail": "both Status choices found"}

    missing = "the photo and video choice" if not found["photo"] else "the text choice"
    try:
        offered = ", ".join(json.loads(on_offer)) or "nothing"
    except (json.JSONDecodeError, TypeError):
        offered = "nothing this tool could read"
    return {
        "ok": False,
        "checked": True,
        "detail": (
            f"WhatsApp has moved or renamed {missing}. Its Status menu offers: "
            f"{offered}. Add the new wording to the list at the top of "
            f"wastatus/post.py"
        ),
    }


def type_into(page: Page, selector: str, text: str) -> None:
    page.js(
        f"""(() => {{ const e = document.querySelector({json.dumps(selector)});
                      if (e) e.focus(); return !!e; }})()"""
    )
    time.sleep(0.3)
    # Insert rather than synthesise keystrokes: newlines in a caption would
    # otherwise submit the composer.
    page.send_cmd("Input.insertText", text=text)
    time.sleep(0.5)


def load_video(page: Page, path: Path, caption: str = "") -> None:
    """Attach a video to the Status composer and type its caption. Does not send.

    The path is resolved here because `DOM.setFileInputFiles` is evaluated by the
    browser, not by us. A relative path means nothing to Chrome: it takes it,
    reports no error, and simply never attaches anything, which surfaces much later
    as a composer that refuses to appear.
    """
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise PostError(f"no such file to post: {path}")

    # A composer left loaded by an earlier run must be backed out of first. The
    # status composer takes several files at once, so attaching into an open one
    # posts both: two Statuses went out at 15:26 on 2026-08-18 that way.
    if page.js_soft(f"!!document.querySelector('{COMPOSER_OPEN}')", default=False):
        log.info("a composer was already open, closing it before attaching")
        cancel(page)
        time.sleep(1.0)

    open_status_tab(page)
    open_status_menu(page, PHOTO_ITEM)
    # Intercept the OS file dialog, so nothing pops up on the desktop.
    page.send_cmd("Page.setInterceptFileChooserDialog", enabled=True)
    try:
        click_one_of(page, PHOTO_ITEM, "the photo and video choice")
        event = page.wait_event("Page.fileChooserOpened")
        backend = event["params"].get("backendNodeId")
        if backend is None:
            raise PostError("the file chooser opened without a node to fill")
        page.send_cmd("DOM.setFileInputFiles", files=[str(path)], backendNodeId=backend)
    finally:
        page.send_cmd("Page.setInterceptFileChooserDialog", enabled=False)

    try:
        # Both halves, not just the caption box: a lone contenteditable is a box
        # that might belong to anything, and the Send button beside it is what
        # says the media editor itself is up.
        page.wait_for(
            f"document.querySelector('{COMPOSER}') "
            f"&& document.querySelector('{SEND_ICON}')",
            "the media composer",
            timeout=COMPOSER_TIMEOUT,
        )
    except PostError as exc:
        raise PostError(
            f"{exc}. WhatsApp Web took the file but never opened the editor. "
            f"Check that {path.name} is a format it accepts"
        ) from exc
    if caption:
        type_into(page, COMPOSER, caption)


def load_text(page: Page, text: str) -> None:
    """Open the text Status composer and type into it. Does not send."""
    open_status_tab(page)
    open_status_menu(page, TEXT_ITEM)
    click_one_of(page, TEXT_ITEM, "the text choice")
    page.wait_for(
        f"document.querySelector('{COMPOSER}') "
        f"&& document.querySelector('{SEND_ICON}')",
        "the text composer",
    )
    type_into(page, COMPOSER, text)


def click_send(page: Page) -> None:
    result = page.js(
        """
        (() => {
          // The label carries a count, e.g. "Send 1 selected", so match the icon
          // rather than an exact label.
          const icon = document.querySelector('[data-icon^="wds-ic-send"]');
          const b = (icon && icon.closest('[role=button],button,div[tabindex]'))
                || [...document.querySelectorAll('[aria-label]')]
                     .find(e => /^send\\b/i.test(e.getAttribute('aria-label')));
          if (!b) return 'not found';
          b.click(); return 'clicked';
        })()
        """
    )
    if result != "clicked":
        raise PostError("could not find the Send button in the open composer")
    time.sleep(2.0)


# Read straight out of WhatsApp Web's own store. `ack` is the field the client
# keeps for what became of a message it sent, and it is the only thing on this
# page that is about WhatsApp rather than about this browser. Keys sort as
# strings, which is not time order, so the newest row is picked by `t`.
_LATEST_STATUS = """
(async () => {
  const answer = (readable, row) => JSON.stringify({readable: readable, row: row});
  let db;
  try {
    db = await new Promise((res, rej) => {
      const r = indexedDB.open(%(db)s);
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
      r.onblocked = () => rej(new Error('blocked'));
    });
  } catch (e) { return answer(false, null); }
  try {
    if (![...db.objectStoreNames].includes('message')) return answer(false, null);
    const store = db.transaction('message', 'readonly').objectStore('message');
    const prefix = %(prefix)s;
    const rows = await new Promise((res) => {
      const out = [];
      const req = store.openCursor(IDBKeyRange.bound(prefix, prefix + '\uffff'));
      req.onsuccess = (e) => {
        const c = e.target.result;
        if (!c) return res(out);
        const v = c.value;
        // Deleting a Status writes a row under this same key prefix: a protocol
        // message, subtype sender_revoke, carrying ack 0. It is a tombstone for
        // the Status that was removed, not a Status. Left in, it is the newest
        // row for a while and confirm_sent reads its ack as "not accepted yet",
        // which turns a delete into a false report of a failed post.
        if (v.type !== 'protocol' && !v.protocolMessageKey) {
          out.push({id: v.id, t: v.t || 0, ack: v.ack, type: v.type});
        }
        c.continue();
      };
      req.onerror = () => res(out);
    });
    if (!rows.length) return answer(true, null);
    rows.sort((a, b) => a.t - b.t);
    return answer(true, rows[rows.length - 1]);
  } catch (e) {
    return answer(false, null);
  } finally {
    db.close();
  }
})()
""" % {"db": json.dumps(STATUS_DB), "prefix": json.dumps(STATUS_KEY_PREFIX)}


def latest_own_status(page: Page) -> dict | None:
    """The newest Status this account sent, as WhatsApp Web has it written down.

    Three different nothings, all of them `None` to the caller, because the caller
    does the same thing with each: wait, and ask again. The browser was too busy to
    answer, the store is not one this build of WhatsApp keeps, or there is no
    Status of ours in it. Only a row that is actually there is a verdict.

    `readable` is kept separate from the row so that a build whose store is shaped
    differently can be told apart from an account that has posted nothing today.
    """
    raw = page.js_soft(_LATEST_STATUS, default=None)
    if not raw:
        return None
    try:
        answer = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not answer.get("readable"):
        return None
    row = answer.get("row")
    return row if isinstance(row, dict) else None


def store_is_readable(page: Page) -> bool | None:
    """Can this browser's WhatsApp be asked what became of a Status at all?

    None when the page gave no answer, which a browser busy sending does: that is
    not a store this tool cannot read, and `confirm_sent` keeps asking."""
    raw = page.js_soft(_LATEST_STATUS, default=None)
    if not raw:
        return None
    try:
        return bool(json.loads(raw).get("readable"))
    except (json.JSONDecodeError, TypeError):
        return False


def composer_closed(page: Page) -> bool | None:
    """Has the composer gone, with nothing still saying "Sending"?

    This was the whole of the old check. It is kept only as the fallback for a
    browser whose message store cannot be read, because on its own it is not an
    answer: it says this page has moved on, not that WhatsApp took anything.
    """
    return page.js_soft(
        f"""
        (() => {{
          if (document.querySelector('{COMPOSER}')) return false;
          const busy = [...document.querySelectorAll('span,div')].some(e => {{
            const t = (e.textContent || '').trim();
            return t === 'Sending...' || t === 'Sending';
          }});
          return !busy;
        }})()
        """,
        default=None,
    )


def wait_until_settled(page: Page, timeout: float) -> float:
    """The old composer-closed wait. Returns the seconds it took.

    Chrome stops answering the debug protocol for part of an upload, so an
    unanswered poll counts as "still going" rather than as an error.
    """
    started = time.monotonic()
    deadline = started + timeout
    settled = 0
    while time.monotonic() < deadline:
        time.sleep(2.0)
        done = composer_closed(page)
        if done is None:  # browser busy, no verdict
            continue
        settled = settled + 1 if done else 0
        if settled >= 2:  # two clean polls in a row, not a gap between states
            return time.monotonic() - started
    raise PostError(
        f"the Status was still uploading after {timeout:.0f}s. "
        "Check the browser: it may yet finish"
    )


def confirm_sent(page: Page, before: dict | None, sent_at: float,
                 timeout: float = SEND_TIMEOUT) -> float:
    """Block until WhatsApp says what became of the Status. Returns the seconds.

    What this replaced asked the page whether the composer had closed, which is a
    question about this browser and not about WhatsApp. It answered "sent" in four
    seconds every time it was ever run, including at 19:21 on 2026-08-31, when the
    Status was refused outright: the clip sat in the tray on the web client, drew
    no views, and never reached the phone. The tool called that a success.

    So the question asked now is the `ack` WhatsApp Web writes against the message:
    below zero it was refused, zero means no answer yet, one or more means WhatsApp
    has it. `before` and `sent_at` are how the new record is told from the one an
    earlier post left behind: a row counts only if it is not the row that was there
    and it is not older than the Send.

    A browser whose store cannot be read at all still waits for the composer to
    settle, then raises `StatusUnconfirmed` rather than answering "sent": the closed
    composer is the same non-answer that called a refused Status a success, and only
    the `ack` counts (AGENTS.md, D-071). Unconfirmed is never retried, so this can
    not post twice, and nothing records it as published.
    """
    if store_is_readable(page) is False:
        log.warning(
            "this WhatsApp Web keeps no message store this tool can read, so "
            "whether the Status was accepted is unconfirmed"
        )
        wait_until_settled(page, timeout)
        raise StatusUnconfirmed(
            "WhatsApp closed its composer, but this browser's WhatsApp Web gives no "
            "way to confirm the Status was accepted. Check your Status on the phone "
            "before sending it again"
        )

    started = time.monotonic()
    deadline = started + timeout
    was = (before or {}).get("id")
    pending = False
    while time.monotonic() < deadline:
        time.sleep(2.0)
        row = latest_own_status(page)
        # Not written yet, or still the one from an earlier post. The clock is the
        # second guard: on a browser that had nothing to compare against, a stale
        # row would otherwise pass for this one.
        if not row or row.get("id") == was or (row.get("t") or 0) < sent_at - 10:
            continue
        ack = row.get("ack")
        if ack is None:
            continue
        if ack <= ACK_ERROR:
            raise StatusRefused(
                "WhatsApp refused the Status. It is in the tray on this browser, "
                "which is why it looks posted, but it was never accepted: it has "
                "no views and will not reach your phone. Delete it there, then "
                "post it again"
            )
        if ack >= ACK_SERVER:
            return time.monotonic() - started
        pending = True  # written down, WhatsApp has not answered yet
    if pending:
        raise StatusUnconfirmed(
            f"WhatsApp had still not accepted the Status after {timeout:.0f}s. "
            "It may yet go out: check its views before posting it again"
        )
    raise StatusUnconfirmed(
        f"no record of the Status appeared after {timeout:.0f}s, so whether it "
        "went out cannot be said. Check the browser"
    )


STATUS_COUNT = """
(() => {
  const label = [...document.querySelectorAll('[aria-label]')]
      .map(e => e.getAttribute('aria-label'))
      .find(a => a && /^Status \\d+ of \\d+$/.test(a));
  return label ? parseInt(label.split(' of ')[1], 10) : 0;
})()
"""


def open_my_status(page: Page) -> int:
    """Open your own Status in the viewer. Returns how many it holds.

    The row does not respond to a synthetic `.click()`, so this dispatches a real
    mouse event at its position in the Status pane.
    """
    open_status_tab(page)
    time.sleep(1.0)
    for kind in ("mousePressed", "mouseReleased"):
        page.send_cmd(
            "Input.dispatchMouseEvent", type=kind, x=180, y=99,
            button="left", clickCount=1,
        )
    time.sleep(3.5)
    return page.js_soft(STATUS_COUNT, default=0) or 0


def delete_all_statuses(page: Page, *, limit: int = 30) -> int:
    """Delete every Status on your own account. Returns how many were removed.

    Destructive and irreversible, which is why the caller has to be explicit about
    wanting it. Each pass reopens the viewer and deletes whichever Status is first,
    rather than tracking indices that shift underneath it.
    """
    removed = 0
    for _ in range(limit):
        if not open_my_status(page):
            break
        page.js(
            """(() => { const b = document.querySelector('[aria-label="Menu"]');
                        if (b) b.click(); return !!b; })()"""
        )
        time.sleep(1.2)
        opened = page.js(
            """
            (() => {
              const item = [...document.querySelectorAll(
                  '[role=menuitem],li,div[role=button],button')]
                .find(e => (e.textContent || '').trim().endsWith('Delete'));
              if (!item) return false;
              item.click(); return true;
            })()
            """
        )
        if not opened:
            raise PostError("the viewer menu has no Delete item any more")
        time.sleep(1.5)
        confirmed = page.js(
            """
            (() => {
              const buttons = [...document.querySelectorAll('button,div[role=button]')]
                .filter(e => (e.textContent || '').trim() === 'Delete');
              if (!buttons.length) return false;
              buttons[buttons.length - 1].click(); return true;
            })()
            """
        )
        if not confirmed:
            raise PostError("no confirmation button appeared for the delete")
        removed += 1
        time.sleep(3.0)
    return removed


def cancel(page: Page) -> None:
    # The text composer's close control is labelled for what it closes, seen on
    # 2026-10-24; the media composer's is still a plain "Close".
    page.js(
        """(() => { const b = document.querySelector(
                      '[aria-label="Close"],[aria-label="Close status posting view"],[aria-label="Back"]');
                    if (b) b.click(); return true; })()"""
    )


# -- what the CLI calls ---------------------------------------------------

def post_video(path: Path, caption: str, *, port: int | None = None,
               send: bool = False) -> float | None:
    """Post one video Status. Returns the upload seconds, or None if unsent."""
    with Page(port) as page:
        require_logged_in(page)
        load_video(page, path, caption)
        if not send:
            return None
        # Read before pressing, so the row this Status writes can be told from
        # whatever the last one left behind.
        before = latest_own_status(page)
        sent_at = time.time()
        click_send(page)
        return confirm_sent(page, before, sent_at)


# How hard to try again when WhatsApp refuses one. Three goes, twenty seconds
# apart and doubling, so a refusal that is a passing server mood is ridden out
# without a person watching, and one that is not gives up in about a minute rather
# than hammering the account. Both are settable per machine.
RETRY_ATTEMPTS = int(os.environ.get("WASTATUS_POST_ATTEMPTS") or 3)
RETRY_BASE_DELAY = float(os.environ.get("WASTATUS_POST_BACKOFF") or 20.0)


def send_with_retry(path: Path, caption: str, *, port: int | None = None,
                    attempts: int = 0, base_delay: float = 0.0,
                    on_retry=None) -> float:
    """Post one video Status, trying again when WhatsApp refuses it.

    Only a refusal is retried. `StatusRefused` means WhatsApp answered no, so
    nothing went out and sending again cannot double post. `StatusUnconfirmed`
    means there was no answer, and a Status that may yet go out must never be sent
    a second time: that one is raised straight through.

    Waits twenty seconds, then forty, then eighty. The delay is a real one because
    the point is to let whatever refused it pass; retrying instantly would put the
    same request to the same server in the same second.

    `on_retry(attempt, delay, error)` is called before each wait, so a caller with a
    screen can say what is happening rather than appearing to hang.
    """
    return _keep_trying(
        lambda: post_video(path, caption, port=port, send=True),
        attempts=attempts, base_delay=base_delay, on_retry=on_retry,
    )


def send_text_with_retry(text: str, *, port: int | None = None,
                         attempts: int = 0, base_delay: float = 0.0,
                         on_retry=None) -> float:
    """The follow up text Status, tried again on the same terms as the video.

    It is a Status this tool posted, so a refusal of it is as retryable as a
    refusal of the clip, and leaving it out meant one of the two Statuses a run can
    send got the treatment and the other did not. Found in the audit of 2026-08-31,
    D-078.
    """
    return _keep_trying(
        lambda: post_text(text, port=port, send=True),
        attempts=attempts, base_delay=base_delay, on_retry=on_retry,
    )


def _keep_trying(send, *, attempts: int, base_delay: float, on_retry) -> float:
    """The retry loop both of the above share. Only `StatusRefused` comes back here.

    `StatusUnconfirmed` is not caught, so it leaves through this untouched: a
    Status that may yet go out must never be sent a second time.
    """
    attempts = attempts or RETRY_ATTEMPTS
    base_delay = base_delay or RETRY_BASE_DELAY
    last: StatusRefused | None = None
    for attempt in range(1, attempts + 1):
        try:
            took = send()
        except StatusRefused as exc:
            last = exc
            if attempt == attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            log.warning(
                "WhatsApp refused the Status (attempt %d of %d). Trying again in %.0fs",
                attempt, attempts, delay,
            )
            if on_retry:
                on_retry(attempt, delay, exc)
            time.sleep(delay)
            continue
        if attempt > 1:
            log.info("WhatsApp took the Status on attempt %d", attempt)
        return took or 0.0
    raise StatusRefused(
        f"WhatsApp refused the Status {attempts} times. {last}"
    ) from last


def post_text(text: str, *, port: int | None = None, send: bool = False) -> float | None:
    """Post one text Status. Returns the send seconds, or None if unsent."""
    with Page(port) as page:
        require_logged_in(page)
        load_text(page, text)
        if not send:
            return None
        before = latest_own_status(page)
        sent_at = time.time()
        click_send(page)
        return confirm_sent(page, before, sent_at, timeout=60.0)
