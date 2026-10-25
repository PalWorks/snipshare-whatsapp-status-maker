#!/usr/bin/env python3
"""Build the SnipShare extension for one site.

The extension in the repository talks only to a copy on this machine
(`src/config.js`, and `externally_connectable` in the manifest). This writes a
copy that talks to a real site instead, into `dist/`, which git ignores:

    python scripts/build_extension.py --site https://snipshare.example.com \\
        --key ~/.config/wastatus/extension-key.pem

* `config.js` names the site, so the toolbar button opens it.
* The manifest lets that site, and nothing else, talk to the extension, and gives
  the extension permission to upload to it. The local addresses are taken out.
* The broad `optional_host_permissions` (any https address, which the Settings page
  asks for when pointed at a renderer of one's own) is taken out unless
  `--keep-custom-server` is given: the built copy only ever talks to its site.
* `--key` pins the extension's id, so the site can be told which extension to talk
  to (`WASTATUS_EXTENSION_ID`). The private key stays outside the repository; the
  manifest carries only the public half, which every installed copy shows anyway.
  `--new-key PATH` makes one, once.

It prints the id and leaves `dist/snipshare-extension.zip`, which is what the site
offers at /install. See docs/hosted-page.md, Table HP-3.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
import urllib.parse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src"
LOCAL = ("http://127.0.0.1/*", "http://localhost/*")


def public_key_der(pem: Path) -> bytes:
    from cryptography.hazmat.primitives import serialization

    private = serialization.load_pem_private_key(pem.read_bytes(), password=None)
    return private.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def extension_id(der: bytes) -> str:
    """Chrome's id for a key: the first 128 bits of its SHA-256, as letters a to p."""
    return "".join(chr(ord("a") + int(c, 16)) for c in hashlib.sha256(der).hexdigest()[:32])


def new_key(path: Path) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    if path.exists():
        raise SystemExit(f"error: {path} exists already; a key is made once")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                       serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    os.chmod(path, 0o600)


def build(site: str, key: Path | None, out: Path, keep_custom_server: bool = False) -> str:
    parts = urllib.parse.urlsplit(site)
    if parts.scheme != "https" or not parts.hostname:
        raise SystemExit("error: the site has to be an https address")
    # The page's origin keeps its port; a match pattern cannot carry one.
    origin = f"https://{parts.netloc}"
    pattern = f"https://{parts.hostname}/*"

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SOURCE, out, ignore=shutil.ignore_patterns("test", "*.md"))

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    hosts = [h for h in manifest["host_permissions"] if h not in LOCAL]
    manifest["host_permissions"] = [*hosts, pattern]
    manifest["externally_connectable"] = {"matches": [pattern]}
    if not keep_custom_server:
        manifest.pop("optional_host_permissions", None)
    ident = ""
    if key:
        der = public_key_der(key)
        manifest["key"] = base64.b64encode(der).decode()
        ident = extension_id(der)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out / "config.js").write_text(
        "// Written by scripts/build_extension.py for this site.\n"
        f"const CONFIG = {{ site: {json.dumps(origin)} }};\n", encoding="utf-8")

    archive = out.parent / "snipshare-extension.zip"
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for file in sorted(out.rglob("*")):
            if file.is_file():
                zipped.write(file, Path("snipshare-extension") / file.relative_to(out))
    return ident


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--site", default=os.environ.get("WASTATUS_PUBLIC_URL", ""),
                        help="the site's address (default $WASTATUS_PUBLIC_URL)")
    parser.add_argument("--key", type=Path, help="the private key that pins the id")
    parser.add_argument("--new-key", type=Path, help="make that key first, once")
    parser.add_argument("--out", type=Path, default=ROOT / "dist" / "snipshare-extension")
    parser.add_argument("--keep-custom-server", action="store_true",
                        help="keep the optional permission to reach any https renderer")
    args = parser.parse_args(argv)
    if args.new_key:
        new_key(args.new_key.expanduser())
        args.key = args.new_key
    if not args.site:
        print("error: --site, or WASTATUS_PUBLIC_URL, is needed", file=sys.stderr)
        return 1
    ident = build(args.site, args.key.expanduser() if args.key else None, args.out,
                  args.keep_custom_server)
    print(f"built {args.out} and {args.out.parent / 'snipshare-extension.zip'}")
    if ident:
        print(f"extension id: {ident}  (WASTATUS_EXTENSION_ID)")
    else:
        print("no --key: Chrome will give this copy an id of its own when it is loaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
