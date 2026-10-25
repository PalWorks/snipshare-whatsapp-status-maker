#!/usr/bin/env python3
"""SnipShare end to end, on this machine: the real server, the real extension, a
throwaway Chrome for Testing under Xvfb. Nothing touches anybody's own browser.

    scripts/site_check.py                 # words, a card clip and a video clip
    scripts/site_check.py --load          # and Load into WhatsApp, which in a
                                          # throwaway profile ends at "not signed
                                          # in", after two minutes
    scripts/site_check.py --video ID      # another video

It starts `wastatus hosted serve` on a spare port with a data folder of its own,
signs a test person in the way a Google sign-in would end, loads a copy of the
extension built for that port, and drives the page as a person would. It prints one
JSON report. Needs Chrome for Testing (CHROME_FOR_TESTING, or Playwright's copy),
xvfb-run, ffmpeg, and a network that reaches YouTube. See TESTING.md.
"""
import base64, json, os, shutil, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
import websocket

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
import build_extension  # noqa: E402

CHROME = next((Path(c) for c in (
    os.environ.get("CHROME_FOR_TESTING", ""),
    str(Path.home() / ".cache/ms-playwright/chromium-1248/chrome-linux64/chrome"),
    str(Path.home() / ".cache/ms-playwright/chromium-1234/chrome-linux64/chrome"),
) if c and Path(c).is_file()), None)
if CHROME is None:
    raise SystemExit("needs Chrome for Testing: set CHROME_FOR_TESTING")
def free_port() -> int:
    import socket
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


# Ports of their own, so the check can never drive a server or a browser that
# something else already started.
PORT, CDP = free_port(), free_port()
SITE = f"http://127.0.0.1:{PORT}"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
EMAIL = "tester@example.com"
VIDEO = sys.argv[sys.argv.index("--video") + 1] if "--video" in sys.argv else "OPf0YbXqDm0"


class T:
    def __init__(self, url):
        self.ws = websocket.create_connection(url, timeout=300, suppress_origin=True); self.n = 0
    def call(self, m, **p):
        self.n += 1; self.ws.send(json.dumps({"id": self.n, "method": m, "params": p}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == self.n:
                if "error" in r: raise RuntimeError(r["error"])
                return r.get("result", {})
    def js(self, e):
        r = self.call("Runtime.evaluate", expression=e, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r: raise RuntimeError(json.dumps(r["exceptionDetails"])[:800])
        return r.get("result", {}).get("value")


def targets():
    return json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP}/json/list"))


work = Path(tempfile.mkdtemp(prefix="snipshare-check-"))
data = work / "data"
key = work / "key.pem"
build_extension.new_key(key)
ext = work / "ext"
shutil.copytree(REPO / "src", ext, ignore=shutil.ignore_patterns("test"))
manifest = json.loads((ext / "manifest.json").read_text())
der = build_extension.public_key_der(key)
manifest["key"] = base64.b64encode(der).decode()
(ext / "manifest.json").write_text(json.dumps(manifest))
(ext / "config.js").write_text(f'const CONFIG = {{ site: "{SITE}" }};\n')
ext_id = build_extension.extension_id(der)

env = {**os.environ, "WASTATUS_HOSTED_DATA": str(data), "WASTATUS_ADMIN_EMAILS": EMAIL,
       "WASTATUS_SECRET_KEY": "e2e" * 20, "WASTATUS_EXTENSION_ID": ext_id,
       "WASTATUS_LOG_DIR": str(work / "logs"), "WASTATUS_ENV": str(work / "no.env")}
for name in ("WASTATUS_PUBLIC_URL", "WASTATUS_RESEND_KEY", "WASTATUS_CHAT_WEBHOOK",
             "WASTATUS_TURNSTILE_SECRET"):
    env.pop(name, None)
server = subprocess.Popen([str(REPO / ".venv/bin/python"), "-m", "wastatus", "hosted", "serve",
                           "--port", str(PORT), "-v"], cwd=REPO, env=env,
                          stdout=open(work / "server.out", "w"), stderr=subprocess.STDOUT)
for _ in range(50):
    if server.poll() is not None:
        raise SystemExit("the server did not start: " + (work / "server.out").read_text()[-800:])
    try:
        urllib.request.urlopen(f"{SITE}/api/v1/health", timeout=1); break
    except OSError:
        time.sleep(0.2)

# A session, minted the way a Google sign-in would end.
os.environ.update({k: v for k, v in env.items() if k.startswith("WASTATUS_")})
from wastatus import accounts, portal  # noqa: E402
store = accounts.Accounts(data / "people.db")
session = store.start_session(EMAIL)

profile = work / "profile"
browser = subprocess.Popen(["xvfb-run", "-a", "-s", "-screen 0 1400x1000x24", str(CHROME),
                            f"--user-data-dir={profile}", f"--remote-debugging-port={CDP}",
                            f"--load-extension={ext}", f"--disable-extensions-except={ext}",
                            "--mute-audio", "--autoplay-policy=no-user-gesture-required",
                            "--no-first-run", f"--user-agent={UA}", "about:blank"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
report = {"extension_id": ext_id}
try:
    for _ in range(100):
        try:
            if any(t["type"] == "service_worker" and ext_id in t["url"] for t in targets()):
                break
        except OSError:
            pass
        time.sleep(0.2)
    top = T(json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP}/json/version"))["webSocketDebuggerUrl"])
    # `__Host-`: Secure, no domain (host only), path `/`; Chrome counts 127.0.0.1 as
    # a secure origin, so it keeps and sends it over plain http here.
    top.call("Storage.setCookies", cookies=[{"name": portal.SESSION_COOKIE, "value": session,
                                              "url": SITE, "path": "/", "httpOnly": True,
                                              "secure": True}])
    first = next(t for t in targets() if t["type"] == "page")
    page = T(first["webSocketDebuggerUrl"])
    page.call("Page.enable")
    page.call("Runtime.enable")
    page.call("Page.navigate", url=f"{SITE}/app")
    time.sleep(2)
    t_ready = time.time()
    for _ in range(120):
        ready = page.js("window.SnipShare && SnipShare.ready()")
        if ready: break
        time.sleep(0.25)
    report["extension_ready"] = (ready, round(time.time() - t_ready, 1))
    report["state_rows"] = page.js("[...document.querySelectorAll('#status-list li')].map(l => l.innerText.replace(/\\s+/g,' '))")
    report["banner"] = page.js("document.getElementById('host-banner') && !document.getElementById('host-banner').hidden && document.getElementById('host-banner').innerText")
    report["quota_line"] = page.js("document.getElementById('host-quota').textContent")

    # Fetch the words through the extension.
    page.js(f"document.getElementById('url').value = 'https://www.youtube.com/watch?v={VIDEO}'; "
            "document.getElementById('url').dispatchEvent(new Event('input', {bubbles:true}))")
    page.js("document.getElementById('words-fetch').click()")
    for _ in range(60):
        title = page.js("document.getElementById('title').value")
        err = page.js("document.getElementById('words-error').hidden ? '' : document.getElementById('words-error').textContent")
        if title or err: break
        time.sleep(0.25)
    report["words"] = {"title": title, "channel": page.js("document.getElementById('channel').value"), "error": err}

    def make(mode, start, length):
        page.js(f"document.querySelector('[data-mode={mode}]').click()")
        page.js(f"document.getElementById('start').value = '{start}'; "
                f"document.getElementById('duration').value = '{length}'; "
                "document.getElementById('start').dispatchEvent(new Event('input', {bubbles:true}))")
        t0 = time.time()
        page.js("document.getElementById('form').requestSubmit()")
        seen = []
        while time.time() - t0 < 300:
            msg = page.js("document.getElementById('progress-message').textContent")
            steps = page.js("[...document.querySelectorAll('#steps li')].map(l => l.dataset.state[0]).join('')")
            if msg and (not seen or seen[-1][1] != msg):
                seen.append((round(time.time() - t0, 1), msg, steps))
            error = page.js("document.getElementById('error').hidden ? '' : document.getElementById('error').textContent")
            busy = page.js("document.getElementById('form').getAttribute('aria-busy')")
            if busy == "false" and (error or page.js("!document.getElementById('result').hidden")):
                break
            time.sleep(0.3)
        name = page.js("document.getElementById('result-name').textContent")
        tabs = [t["url"][:60] for t in targets() if t["type"] == "page"]
        return {"seconds": round(time.time() - t0, 1), "error": error, "result": name,
                "progress": seen[:25], "tabs_after": tabs}

    report["card"] = make("card", "1:00", 15)
    report["video"] = make("video", "1:20", 10)
    if report["video"]["error"]:
        report["video_again"] = make("video", "2:00", 10)
    st = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{SITE}/api/state", headers={"Cookie": f"{portal.SESSION_COOKIE}={session}",
                                       "X-Wastatus-Token": page.js("document.body.dataset.token")})).read())
    report["clips_on_server"] = [(c["stem"], c["size_mb"], c["video"]) for c in st["clips"]]
    report["quota_after"] = st["quota"]
    report["gif_shelf"] = page.js("document.querySelector('[data-source=gifs]').click(); "
                                  "new Promise(r => setTimeout(() => r(document.getElementById('shelf').textContent.trim().slice(0,160)), 800))")
    if "--load" in sys.argv:
        t0 = time.time()
        page.js("document.getElementById('load').click()")
        time.sleep(0.5)
        if page.js("!document.getElementById('post-stale').hidden"):
            page.js("document.getElementById('load').click()")   # the second press goes ahead
        while time.time() - t0 < 200:
            err = page.js("document.getElementById('post-error').hidden ? '' : document.getElementById('post-error').textContent")
            done = page.js("document.getElementById('post-done').hidden ? '' : document.getElementById('post-done').textContent")
            if err or done: break
            time.sleep(1)
        report["load"] = {"seconds": round(time.time() - t0), "error": err, "done": done,
                          "tabs": [t["url"][:50] for t in targets() if t["type"] == "page"]}
    report["reports"] = [dict(r) for r in store.reports(0)]
finally:
    browser.terminate()
    try: browser.wait(10)
    except subprocess.TimeoutExpired: browser.kill()
    # xvfb-run does not pass the signal on: end every process of this profile.
    for proc in Path("/proc").iterdir():
        if proc.name.isdigit() and int(proc.name) != os.getpid():
            try:
                if str(profile).encode() in (proc / "cmdline").read_bytes():
                    os.kill(int(proc.name), 15)
            except (OSError, ProcessLookupError):
                pass
    time.sleep(1)
    server.terminate()
    server.wait(10)
    report["server_tail"] = (work / "server.out").read_text()[-1500:]
    print(json.dumps(report, indent=1, default=str))
    shutil.rmtree(work, ignore_errors=True)
