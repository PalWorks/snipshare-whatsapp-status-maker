"""The repository stays fit to publish.

Nothing tracked may name a real person's address, a machine's public address, a
home directory, or anything on the owner's private deny list: those belong in
`.env`, the server's `.env` and the private operations notes, never here. See
docs/hosted-page.md, Table HP-3.

The deny list is `.publish-deny` at the root, one string per line, git-ignored: the
owner's own names, domains and hosts, which cannot be written into this test without
defeating it. Without the file only the general patterns are checked.
"""

from __future__ import annotations

import ipaddress
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DENY = ROOT / ".publish-deny"

# Addresses anybody may write: the documentation domains, and the providers' own
# no-reply style addresses that appear in their docs and headers.
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "example.net", "users.noreply.github.com")
# Placeholders written in instructions, which name nobody.
ALLOWED_EMAILS = {"wastatus-writer@your-project-id.iam.gserviceaccount.com",
                  "writer@x.iam.gserviceaccount.com"}
# The first few addresses of the shared range, used as stand-ins for a tailnet
# address in examples and tests.
PLACEHOLDER_NET = ipaddress.ip_network("100.64.0.0/24")
IPV4 = re.compile(r"(?<![\w./-])(\d{1,3}(?:\.\d{1,3}){3})(?![\w.])")
HOME = re.compile(r"/(?:home|Users)/([A-Za-z0-9._-]+)")
ALLOWED_HOMES = {"someone", "x", "user", "you", "runner", "me", "name"}


def tracked() -> list[Path]:
    names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.splitlines()
    files = []
    for name in names:
        path = ROOT / name
        if not path.is_file() or path.suffix in (".png", ".jpg", ".ttf", ".otf", ".woff2",
                                                  ".ico", ".zip", ".webm", ".mp4"):
            continue
        files.append(path)
    return files


def text_of(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ""


FILES = tracked()


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_personal_or_infrastructure_detail(path):
    text = text_of(path)
    found = []
    for match in EMAIL.finditer(text):
        domain = match.group(0).rsplit("@", 1)[1].lower()
        if not domain.endswith(ALLOWED_EMAIL_DOMAINS) and match.group(0) not in ALLOWED_EMAILS:
            found.append(match.group(0))
    for match in IPV4.finditer(text):
        try:
            address = ipaddress.ip_address(match.group(1))
        except ValueError:
            continue
        # Version numbers look like addresses; a real one is never all four parts
        # under ten except 0.0.0.0 and the like, which are not anybody's.
        if address in PLACEHOLDER_NET or address.is_loopback or address.is_unspecified or address.is_private \
                or address.is_link_local or address.is_multicast or address.is_reserved:
            continue
        if text[max(0, match.start() - 8):match.start()].rstrip().endswith(("version", "v", "/")):
            continue
        found.append(match.group(1))
    for match in HOME.finditer(text):
        if match.group(1) not in ALLOWED_HOMES:
            found.append(match.group(0))
    if DENY.is_file():
        lowered = text.lower()
        for word in DENY.read_text(encoding="utf-8").splitlines():
            word = word.strip().lower()
            if word and not word.startswith("#") and word in lowered:
                found.append(f"deny list entry on line {lowered[:lowered.index(word)].count(chr(10)) + 1}")
    assert not found, f"{path.relative_to(ROOT)}: {sorted(set(found))[:10]}"


def test_the_deny_list_is_never_committed():
    assert ".publish-deny" not in {p.name for p in FILES}


def test_the_hosted_image_installs_a_subset_of_the_tool_s_requirements():
    """deploy/requirements.txt leaves out what the site never runs, and pins nothing
    differently from requirements.txt, so the two cannot drift apart."""
    def lines(path: Path) -> set[str]:
        return {line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")}

    tool = lines(ROOT / "requirements.txt")
    image = lines(ROOT / "deploy" / "requirements.txt")
    assert image <= tool, sorted(image - tool)
    names = {line.split(">")[0].split("=")[0].lower() for line in image}
    assert not names & {"yt-dlp", "bgutil-ytdlp-pot-provider", "websocket-client"}
