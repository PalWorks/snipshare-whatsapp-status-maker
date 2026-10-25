#!/usr/bin/env python3
"""Drive the browser extension end to end, the way a person would, and report.

Starts a throwaway Chrome for Testing with `src/` loaded (branded Chrome no
longer accepts `--load-extension`), points the extension at a renderer, opens a
YouTube video, and asks the extension's own service worker to make a clip: the same
`start` message the popup sends. Then follows the job through its phases and checks
the clip that came back. Nothing here imitates the extension; it only presses its
buttons.

  extension_check.py --renderer https://snipshare.example.com --token-file ~/.config/wastatus/token \\
      --video kJQP7kiw5Fk --start 120 --end 150 --mode video

Optional: `--throttle KBPS` slows the extension's own connection, to see the upload
and download survive a poor network. `--restart-at uploading` stops the service
worker once that phase starts, to see it resume. `--popup out.png` screenshots the
popup as it stands at the end, at its real width.

The token is read from a file and never printed. See TESTING.md and DEPLOYMENT.md.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

import websocket

ROOT = Path(__file__).resolve().parent.parent
EXTENSION = ROOT / "src"
CHROME_CANDIDATES = [
    os.environ.get("CHROME_FOR_TESTING", ""),
    str(Path.home() / ".cache/ms-playwright/chromium-1248/chrome-linux64/chrome"),
    str(Path.home() / ".cache/ms-playwright/chromium-1234/chrome-linux64/chrome"),
]
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/156.0.0.0 Safari/537.36")


class Target:
    """One CDP session."""

    def __init__(self, ws_url: str) -> None:
        self.ws = websocket.create_connection(ws_url, timeout=300, suppress_origin=True)
        self.n = 0

    def call(self, method: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == self.n:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})

    def js(self, expression: str):
        result = self.call("Runtime.evaluate", expression=expression, awaitPromise=True,
                           returnByValue=True)
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"].get("exception", {}).get(
                "description", result["exceptionDetails"]))
        return result.get("result", {}).get("value")

    def close(self) -> None:
        self.ws.close()


def targets(port: int) -> list[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list") as response:
        return json.load(response)


def wait_target(port: int, test, what: str, timeout: float = 30) -> dict:
    until = time.time() + timeout
    while time.time() < until:
        try:
            for target in targets(port):
                if test(target):
                    return target
        except OSError:
            pass
        time.sleep(0.25)
    raise SystemExit(f"no {what} appeared")


def main() -> int:
    ap = argparse.ArgumentParser(prog="extension_check.py")
    ap.add_argument("--renderer", required=True)
    ap.add_argument("--token-file", type=Path, required=True)
    ap.add_argument("--video", default="kJQP7kiw5Fk")
    ap.add_argument("--start", type=float, default=120)
    ap.add_argument("--end", type=float, default=135)
    ap.add_argument("--mode", choices=("card", "video"), default="card")
    ap.add_argument("--quality", default="hd720")
    ap.add_argument("--throttle", type=int, default=0, help="kbit/s up and down")
    ap.add_argument("--restart-at", choices=("capturing", "uploading", "rendering",
                                             "downloading"))
    ap.add_argument("--stop-at", choices=("capturing", "uploading", "queued", "rendering",
                                          "downloading"),
                    help="press Stop once this phase starts, and check nothing is left running")
    ap.add_argument("--popup", type=Path, help="screenshot the popup at the end")
    ap.add_argument("--keep-clip", type=Path, help="write the finished clip here")
    ap.add_argument("--save", action="store_true", help="press Save the video, and check the file")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--port", type=int, default=9341)
    args = ap.parse_args()

    chrome = next((c for c in CHROME_CANDIDATES if c and Path(c).is_file()), None)
    if not chrome:
        print("needs Chrome for Testing: set CHROME_FOR_TESTING")
        return 2
    profile = Path(tempfile.mkdtemp(prefix="wastatus-ext-"))
    # A renderer other than the default is an optional permission, which a person
    # grants from the popup and a headless browser cannot. The extension is loaded
    # from a copy whose manifest already holds it, and is otherwise untouched.
    loaded = profile / "extension"
    shutil.copytree(EXTENSION, loaded, ignore=shutil.ignore_patterns("test"))
    parts = urlsplit(args.renderer)
    manifest = json.loads((loaded / "manifest.json").read_text())
    pattern = f"{parts.scheme}://{parts.hostname}/*"  # match patterns carry no port
    if pattern not in manifest["host_permissions"]:
        manifest["host_permissions"].append(pattern)
        (loaded / "manifest.json").write_text(json.dumps(manifest, indent=2))
    cmd = [chrome, f"--user-data-dir={profile}", f"--remote-debugging-port={args.port}",
           f"--load-extension={loaded}", f"--disable-extensions-except={loaded}",
           "--autoplay-policy=no-user-gesture-required", "--mute-audio",
           "--no-first-run", "--no-default-browser-check", "--window-size=1280,900",
           f"--user-agent={UA}", "about:blank"]
    if not args.headed:
        cmd.insert(1, "--headless=new")
    browser = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    report: dict = {"video": args.video, "window": [args.start, args.end], "mode": args.mode}
    try:
        worker_t = wait_target(args.port, lambda t: t["type"] == "service_worker"
                               and t["url"].endswith("/sw.js"), "extension service worker")
        ext_id = worker_t["url"].split("/")[2]
        worker = Target(worker_t["webSocketDebuggerUrl"])
        token = args.token_file.expanduser().read_text().strip()
        worker.js(f"chrome.storage.local.set({{settings: {{server: {json.dumps(args.renderer)}, "
                  f"token: {json.dumps(token)}, quality: {json.dumps(args.quality)}}}}})")
        del token
        if args.throttle:
            bps = args.throttle * 1000 / 8
            worker.call("Network.enable")
            worker.call("Network.emulateNetworkConditions", offline=False, latency=150,
                        downloadThroughput=bps, uploadThroughput=bps)
        check = worker.js("fetch(" + json.dumps(args.renderer.rstrip("/") + "/api/v1/health")
                          + ").then(r => r.json())")
        report["renderer"] = check

        yt_t = wait_target(args.port, lambda t: t["type"] == "page", "a page")
        yt = Target(yt_t["webSocketDebuggerUrl"])
        yt.call("Page.enable")
        yt.call("Page.navigate", url=f"https://www.youtube.com/watch?v={args.video}")
        info = None
        until = time.time() + 60
        while time.time() < until:
            time.sleep(1)
            tab_id = worker.js("chrome.tabs.query({url: 'https://www.youtube.com/watch*'})"
                               ".then(t => t[0] && t[0].id)")
            if not tab_id:
                continue
            info = worker.js(f"tabInfo({tab_id})")
            if info and info.get("ready") and info.get("duration") and not info.get("ad"):
                break
            if info and info.get("ad"):
                yt.js("document.querySelector('.ytp-skip-ad-button, .ytp-ad-skip-button-modern')"
                      "?.click()")
        if not info or not info.get("ready"):
            raise SystemExit(f"the video never became ready: {info}")
        report["info"] = {k: info[k] for k in ("videoId", "title", "duration", "ad")}
        params = {"tabId": tab_id, "videoId": info["videoId"], "title": info["title"],
                  "author": info["author"], "duration": info["duration"],
                  "start": args.start, "end": min(args.end, info["duration"]),
                  "mode": args.mode, "fill": "blur"}
        started = time.time()
        answer = worker.js(f"start({json.dumps(params)})")
        if not answer.get("ok"):
            raise SystemExit(f"start refused: {answer}")
        phases: dict[str, float] = {}
        restarted = False
        last = None
        while time.time() - started < 900:
            time.sleep(0.5)
            try:
                job = worker.js("chrome.storage.local.get('job').then(s => s.job)")
            except (RuntimeError, websocket.WebSocketException, OSError):
                # The worker was stopped and is starting again: find it once more.
                worker.close()
                worker_t = wait_target(args.port, lambda t: t["type"] == "service_worker"
                                       and t["url"].endswith("/sw.js"), "the worker again")
                worker = Target(worker_t["webSocketDebuggerUrl"])
                continue
            if not job:
                raise SystemExit("the job vanished")
            phase = job["phase"]
            if phase not in phases:
                phases[phase] = round(time.time() - started, 1)
                print(f"{phases[phase]:7.1f}s  {phase}", flush=True)
            note = f"{phase} {job.get('detail')} {round(100 * (job.get('progress') or 0))}%"
            if note != last:
                last = note
            if args.stop_at == phase:
                time.sleep(1)
                report["stop"] = worker.js("stop()")
                time.sleep(3)
                report["job_after_stop"] = worker.js("chrome.storage.local.get('job').then(s => s.job || null)")
                report["renderer_jobs_after_stop"] = worker.js(
                    "api('GET', '/jobs').then(r => r.data.jobs.map(j => j.state))")
                report["viewer_after_stop"] = yt.js(
                    "({paused: document.querySelector('#movie_player video').paused, "
                    "time: document.getElementById('movie_player').getCurrentTime()})")
                break
            if args.restart_at == phase and not restarted:
                restarted = True
                # Stop the worker the way Chrome does when it has been idle: through
                # a page of the extension's own origin, which can see its version.
                # Then let the popup that page is wake it, as opening it would.
                print("         stopping the service worker", flush=True)
                page = Target(json.load(urllib.request.urlopen(urllib.request.Request(
                    f"http://127.0.0.1:{args.port}/json/new?chrome-extension://{ext_id}/popup.html",
                    method="PUT")))["webSocketDebuggerUrl"])
                page.ws.send(json.dumps({"id": 9001, "method": "ServiceWorker.enable"}))
                version = None
                until = time.time() + 10
                while time.time() < until and version is None:
                    message = json.loads(page.ws.recv())
                    for v in message.get("params", {}).get("versions", []):
                        if v.get("runningStatus") == "running" and v.get("scriptURL", "").endswith("/sw.js"):
                            version = v["versionId"]
                if version is None:
                    raise SystemExit("could not find the worker to stop it")
                page.call("ServiceWorker.stopWorker", versionId=version)
                report["stopped_worker_at"] = round(time.time() - started, 1)
                time.sleep(3)
                page.call("Page.reload")  # the popup again: it sends `resume`
                page.close()
                continue
            if phase in ("ready", "failed"):
                report["job"] = {k: job.get(k) for k in ("phase", "error", "retryFrom", "clip",
                                                          "files")}
                break
        report["phases"] = phases
        report["seconds"] = round(time.time() - started, 1)
        if report.get("job", {}).get("phase") == "ready":
            size = worker.js("""(async () => {
                const job = (await chrome.storage.local.get('job')).job;
                const blob = await idbGet(job.key + ':clip');
                return blob ? blob.size : 0; })()""")
            report["clip_bytes"] = size
            if args.keep_clip:
                data = worker.js("""(async () => {
                    const job = (await chrome.storage.local.get('job')).job;
                    const bytes = new Uint8Array(await (await idbGet(job.key + ':clip')).arrayBuffer());
                    let s = ''; for (let i = 0; i < bytes.length; i += 0x8000)
                      s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
                    return btoa(s); })()""")
                args.keep_clip.write_bytes(base64.b64decode(data))
                report["kept"] = str(args.keep_clip)
        if args.save and report.get("job", {}).get("phase") == "ready":
            downloads = profile / "downloads"
            downloads.mkdir()
            top = Target(json.load(urllib.request.urlopen(
                f"http://127.0.0.1:{args.port}/json/version"))["webSocketDebuggerUrl"])
            top.call("Browser.setDownloadBehavior", behavior="allow",
                     downloadPath=str(downloads), eventsEnabled=False)
            report["save"] = worker.js("save()")
            until = time.time() + 30
            while time.time() < until:
                done = worker.js("chrome.downloads.search({}).then(d => d.map(x => "
                                 "({state: x.state, bytes: x.bytesReceived, file: x.filename, error: x.error})))")
                if done and all(d["state"] != "in_progress" for d in done):
                    break
                time.sleep(0.5)
            report["downloads"] = done
            top.close()
        if args.popup:
            popup = Target(json.load(urllib.request.urlopen(urllib.request.Request(
                f"http://127.0.0.1:{args.port}/json/new?chrome-extension://{ext_id}/popup.html",
                method="PUT")))["webSocketDebuggerUrl"])
            popup.call("Emulation.setDeviceMetricsOverride", width=360, height=600,
                       deviceScaleFactor=1, mobile=False)
            time.sleep(2)
            shot = popup.call("Page.captureScreenshot", format="png")
            args.popup.write_bytes(base64.b64decode(shot["data"]))
            report["popup"] = str(args.popup)
    finally:
        browser.terminate()
        try:
            browser.wait(10)
        except subprocess.TimeoutExpired:
            browser.kill()
        shutil.rmtree(profile, ignore_errors=True)
    print(json.dumps(report, indent=1, default=str))
    if args.stop_at:
        clean = (report.get("job_after_stop") is None and
                 not set(report.get("renderer_jobs_after_stop") or []) & {"queued", "rendering"})
        return 0 if clean else 1
    return 0 if report.get("job", {}).get("phase") == "ready" else 1


if __name__ == "__main__":
    sys.exit(main())
