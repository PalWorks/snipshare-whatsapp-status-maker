# Code style

Last updated **2026-10-25T15:15:55+05:30**.

The conventions this codebase actually follows, read off the code rather than
wished for. The short form is in [AGENTS.md](AGENTS.md), "Coding conventions"; the
rule above all of them is to match the surrounding code, because it is consistent.
Read a neighbouring module before writing a new one.

There is no formatter or linter configuration in the repository. The `noqa` codes
in the source are Ruff and flake8 names, kept so a reader knows which warning was
considered and why it was waived.

## Python

**Table CS-1: Python conventions**

| Convention | What it looks like here |
|---|---|
| Future annotations | `from __future__ import annotations` at the top of every module, `__init__.py` and `__main__.py` aside |
| Type hints | on every signature, with `X \| None` rather than `Optional`; `Path`, never a string path |
| Standard library first | the servers are `http.server.ThreadingHTTPServer` with a `BaseHTTPRequestHandler`, no framework; the CLI path stays dependency free by importing `serve` only when it is needed |
| Dataclasses | records are `@dataclass`, `@dataclass(frozen=True)` when nothing should change them (`capture.Stream`, `accounts`, `gifs`) |
| One logger | `log = logging.getLogger("wastatus")`, shared by every module |
| Errors per module | a class per module whose message is for the person: `TimecodeError(ValueError)`, `FetchError`, `RenderError`, `CaptureError`, `PostError`, `GifError` (all `RuntimeError`), `AccessError`, `hosted.Refused` |
| Subprocesses | through the module's `_run` helper (`fetch._run`, `render._run`, `proc.run_child`); `Popen` sets `stdout`, `stderr` and `stdin` explicitly |
| Section markers | `# -- which ports to look on ---...` between groups of functions in a long module |
| Constants | upper case at module level, each with a comment when the number was measured or chosen for a reason |
| Private helpers | a leading underscore: `_framing`, `_run`, `_route`, `_append` |

### Comments explain why, and cite the decision

A comment records the fact a line rests on and points at the document that holds
it, with a `D-` (DECISIONS.md) or `T-` (TASKS.md) reference. It never restates what
the code does.

```python
# A probe asked for by hand is somebody sitting in front of a spinning icon, not a
# download running in the background: five minutes of spinner is indistinguishable
# from a tool that has died. A render still waits the full `RUN_TIMEOUT`, because
# there the wait has already been paid for. See DECISIONS.md D-064.
PROBE_TIMEOUT = 45.0
```

```python
    # Bare `./wastatus.sh` opens the page. Making a clip needs a URL and two
    # timestamps, so there is no useful thing an empty command line could mean, and
    # the page is what gets opened most days anyway. TASKS.md T-032.
```

Short trailing comments carry units and meaning: `ZOOM = 0.07  # Ken Burns travel
over the whole clip.`

### Docstrings are plain prose

A module docstring says what the module owns. A function or class docstring says
what it is for and what is surprising about it, in sentences, without parameter
tables or reStructuredText fields.

```python
class StatusUnconfirmed(PostError):
    """No answer either way, which is not the same as a refusal.

    Never retried. The Status may yet go out, and sending a second one to be sure
    is how a viewer gets the same clip twice.
    """
```

```python
def plain_error(exc: BaseException) -> str:
    """What went wrong, in words fit to show the person: the first line, with any
    path on this machine taken out. The whole of it goes to the log."""
```

### Logging never raises

A run log, the sheet and the watcher swallow their own failures, because a lost
record must never cost a clip or a Status.

```python
        except OSError as exc:
            self.log.warning("could not write run record: %s", exc)
```

```python
    except Exception as exc:  # noqa: BLE001 - a lost row must never lose a Status
```

### `noqa` always gives its reason

A waived warning carries the code and the reason on the same line.

```python
    except Exception as exc:  # noqa: BLE001 - one place turns any failure into a message
    child = subprocess.Popen(  # noqa: S603 - every argv here is built by us
from .cli import main  # noqa: E402  imported after the file is read, on purpose
```

### Defaults that are safe

A parameter that sends, deletes or opens something defaults to the harmless value:
`send` is `False` in `post.post_video`, `post.post_text` and `App.post_clip`, and a
test asserts it. Bounds are enforced where input arrives (`CAPTION_MAX`, URL length,
`Content-Length`), not trusted from the client.

## JavaScript

**Table CS-2: JavaScript conventions**

| Convention | What it looks like here |
|---|---|
| Vanilla, no build step | edit the file, reload the page. `app.js` opens by saying why: "a build step would be more machinery than the thing it builds" |
| `$()` helper | `const $ = (id) => document.getElementById(id);` in `app.js`, `popup.js` and every page script |
| Escape before `innerHTML` | every interpolated value goes through `escapeHtml`, for example `${escapeHtml(row.detail \|\| "")}` |
| Timeouts on every fetch | `signal: options.signal \|\| AbortSignal.timeout(REQUEST_TIMEOUT_MS)`; 120 s for the tool and account pages, 30 s for admin, site and hosted; a `TimeoutError` becomes a plain message |
| Page modules | each page script is an IIFE, `(() => { ... })();`, holding its own `$`, token and state |
| Extension modules | `"use strict";` at the top of every file; content scripts are IIFEs; `media.js` is a UMD-style wrapper so Node can test it (`module.exports = api`) |
| Constants | upper case with a comment giving the unit or the reason: `const POLL_MS = 600;` |
| Visibility | `hide(el)` and `unhide(el)` set the `hidden` attribute, because `.hidden` does nothing on an `<svg>` |
| Block comments | `/* ... */` for the why of a section, with `/* ── talking to the tool ── */` style dividers in long files |

```js
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}
```

### MV3 service worker rules

`src/sw.js` states them in its header and every step follows them:

- Chrome stops an idle worker after about thirty seconds and starts it on the next
  event. State that must survive lives in `chrome.storage.local`, files and the clip
  in IndexedDB; every step resumes from what is stored, never from memory.
- No single `fetch()` may wait 30 seconds: `REQUEST_TIMEOUT = 25000`, chunks start at
  64 KB and adapt to the line (`CHUNK_FAST`, `CHUNK_SLOW`).
- The `chrome.alarms` keepalive exists only while a job is in flight and is
  re-created on every drive.
- Uploads ask the server what arrived; downloads continue with `Range`; a 206 whose
  start does not match is discarded.
- Hooks in `recorder.js` always call the original and swallow their own errors.

```js
const REQUEST_TIMEOUT = 25000;     // under Chrome's 30 seconds for a fetch() in a worker
```

## CSS

**Table CS-3: CSS conventions**

| Convention | What it looks like here |
|---|---|
| Tokens | the palette and sizes are custom properties on `:root`: `--bg`, `--surface`, `--text`, `--accent`, `--danger`, `--danger-bg`, `--radius`, `--touch` |
| Light and dark | light on `:root`; dark under `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } }` and again under `:root[data-theme="dark"]`, so an explicit choice wins both ways; `color-scheme` set to match |
| Fill and ink pairs | a `var(--danger)` fill takes its ink from `var(--danger-bg)`, never a fixed `#fff`, because both invert between palettes |
| Mobile first | written for a 360 pixel phone, widened by `@media (min-width: 600px)` and up |
| Touch targets | `min-height: 40px` on controls, and more under `@media (pointer: coarse)`; no hover-only actions |
| Reduced motion | `@media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }` |
| Hidden | `[hidden] { display: none !important; }` so the attribute always wins |
| Class names | block, element, modifier: `.button--small`, `.decal__handle--edit`, `.clipline__actions` |
| Specificity | a modifier sits next to its base rule; a single class override written earlier in the file loses silently |

## Tests

**Table CS-4: test conventions**

| Convention | What it looks like here |
|---|---|
| Names are sentences | the behaviour protected, not the function called: `test_a_missing_file_fails_before_touching_the_page`, `test_the_sheet_never_fails_a_post` |
| Classes group a claim | `class TestSendingIsNeverTheDefault:`, `class TestALinkIsOnlyALink:`, `class TestWhatAStrangerCannotMakeItDo:`, with a docstring saying what the group holds |
| Module docstring | says what the file protects and, for audits, when and why the tests were written |
| No network | the offline suite reaches nothing outside the machine; the real run is opt in, `WASTATUS_E2E=1` |
| Monkeypatching | collaborators are replaced with `monkeypatch.setattr`, for example `fetch._run`, `post.store_is_readable`, `sheet.configured` |
| Disposable state | `tmp_path` for files; `conftest.py` points `WASTATUS_LOG_DIR` at a temporary folder for every test, autouse |
| Platform facts cite a doc | a test that encodes a measured fact about WhatsApp or YouTube points at the document recording it |
| Parametrise inputs | `@pytest.mark.parametrize("url", ["--exec=id", "file:///etc/passwd", "ftp://x/y"])` |
| Node tests | the extension's parser in `src/test/*.test.js`, run from `tests/test_extension.py` when Node is present |

```python
class TestSendingIsNeverTheDefault:
    @pytest.mark.parametrize("function", [post.post_video, post.post_text, serve.App.post_clip])
    def test_send_defaults_to_no(self, function):
        assert inspect.signature(function).parameters["send"].default is False
```

## Naming

**Table CS-5: names**

| Thing | Rule | Examples |
|---|---|---|
| Python modules | one short noun for what the module owns | `fetch`, `compose`, `render`, `post`, `portal`, `retention` |
| Settings | `WASTATUS_` plus upper case, listed in `.env.example` with no value | `WASTATUS_LOG_DIR`, `WASTATUS_CDP_PORTS` |
| CLI flags | lower case words joined by hyphens, help text that reads as a sentence | `--top-line`, `--keep-last`, `--also-on` |
| Output files | date led and human readable, not a video id | `out/20260818_<song>_70-85.mp4` |
| Test files | `test_<subject>.py` | `test_safe_zone.py`, `test_publishable.py` |
| JavaScript | `camelCase` functions, upper case constants | `paintSummaries`, `recentSignature`, `POLL_MS` |
| Branches | named for what they do | `fix-upload-resume` |

## Writing the documents

**Table CS-6: writing rules for every document**

| Rule | Detail |
|---|---|
| Language | plain British English: behaviour, colour, licence (noun), organise |
| Tone | direct and concise; say what is so, what was measured, and when |
| No dashes in prose | no em dashes, en dashes or double hyphens used as dashes; use a comma, a colon or a new sentence. Flags such as `--post` are code, not dashes |
| No emoji | anywhere |
| Named tables | every table has a bold caption with a prefix unique to its document, "**Table CS-1: ...**", so it can be cited |
| Timestamps | every update is stamped to the second in ISO 8601 with the offset, taken from `date --iso-8601=seconds`, never estimated: `2026-10-25T15:15:55+05:30` |
| Nothing personal | no real names, emails, domains, hosts, IP addresses or home directories; use `example.com`, `127.0.0.1` and `~`. `tests/test_publishable.py` fails otherwise |
| Unverified content | labelled `[Inference]`, `[Speculation]` or `[Unverified]` |
| Cross references | decisions by `D-` number, tasks by `T-` number, tables by name |
