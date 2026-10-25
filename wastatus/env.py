"""Read settings from a `.env` file, so one machine's settings are not code.

The page's token is made per process by `secrets` and dies with the server. The
settings that do carry a secret (a proxy with a password, the GIF keys, the sheet's
service account, and on the hosted site its sign-in, mail and encryption keys) live
here, in `.env`, so a credential always has an obvious place that is not a committed
file. `.env.example` lists every setting the tool reads, with no values; `.env`
itself is ignored by git.

Two rules worth knowing:

* **The environment always wins.** A value already exported in the shell is never
  overwritten by the file, so a one off run overrides the file without editing it.
* **Everything after the first `=` is the value**, so there are no inline comments
  and a value never needs escaping. A whole line starting with `#` is a comment.

Deliberately not a dependency: this is thirty lines and reading a file of `KEY=value`
does not warrant one.
"""

from __future__ import annotations

import os
from pathlib import Path

# Beside the code, which is where somebody who cloned this will look for it.
DEFAULT = Path(__file__).resolve().parent.parent / ".env"
OVERRIDE = "WASTATUS_ENV"  # point at a different file, mostly for tests

# The names the file supplied on this run, for the startup stamp in `runlog`.
# Names only, never values: "which settings were in play" is worth logging and a
# key is not, and keeping the values out of reach here is what makes that certain.
TAKEN: list[str] = []


def load(path: str | Path | None = None) -> list[str]:
    """Set anything named in the file that is not already set.

    Returns the names taken from the file, which is what a caller would log. A
    missing file is the normal case and is not an error: most people will never
    make one.
    """
    chosen = path or os.environ.get(OVERRIDE) or DEFAULT
    try:
        text = Path(chosen).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    taken = []
    for line in text.splitlines():
        name, value = _setting(line)
        if name and name not in os.environ:
            os.environ[name] = value
            taken.append(name)
    TAKEN[:] = taken
    return taken


def _setting(line: str) -> tuple[str | None, str]:
    """Pull one `KEY=value` out of a line, or answer nothing for anything else."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None, ""
    if line.startswith("export "):
        line = line[len("export "):].lstrip()
    name, sep, value = line.partition("=")
    name = name.strip()
    if not sep or not name or not name.replace("_", "").isalnum():
        return None, ""  # not a setting: a stray word, a heading, a broken line
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]  # quotes are how a value keeps its spaces
    return name, value
