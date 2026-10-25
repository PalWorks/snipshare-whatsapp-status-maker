# Dependencies

Last updated **2026-10-25T15:21:02+05:30**

Everything this project needs that it does not contain: Python packages, programs,
images, assets and outside services, with the version asked for and, where it can be
read, the version in use. Licences are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md); this file is about versions and
what each one is for.

"Installed" below is what `.venv/bin/pip show` and `--version` report on the
development machine on the date above. It is a record, not a requirement.

## Python packages

Two lists. [requirements.txt](requirements.txt) is the local tool's.
[deploy/requirements.txt](deploy/requirements.txt) is what the hosted image installs:
the same lines without the three only the local tool uses, and
`tests/test_publishable.py` checks it stays a subset.

**Table DE-1: Python packages**

| Package | Asked for | Installed | Hosted image | Used for |
|---|---|---|---|---|
| yt-dlp | `>=2026.7.4` | 2026.7.4 | no | reading a YouTube window, run as a subprocess (`fetch.py`) |
| bgutil-ytdlp-pot-provider | `==1.3.1` | 1.3.1 | no | the yt-dlp plugin that asks the token provider for a PO token |
| websocket-client | `>=1.8` | 1.9.0 | no | driving WhatsApp Web over Chrome's debug protocol (`post.py`) |
| Pillow | `>=10.0` | 12.3.0 | yes | every card, overlay, sticker and the word preview |
| Unidecode | `>=1.3` | 1.4.0 | yes | romanising any non-Latin title, and the fallback for Tamil |
| aksharamukha | `>=2.1` | 2.3 | yes | phonetic Tamil romanisation, behind a shim (D-006) |
| google-auth | `>=2.30` | 2.57.0 | yes | verifying a Google sign-in; the optional Google Sheet |
| requests | `>=2.31` | 2.34.2 | yes | the transport google-auth uses |
| cryptography | `>=42` | 50.0.1 | yes | encrypting people's GIF keys; pinning the extension's id at build |
| pytest | `>=8.0` ([requirements-dev.txt](requirements-dev.txt)) | 9.1.1 | no | the tests |

## Programs and runtimes

**Table DE-2: programs**

| What | Version asked for | In use | Where it is asked for | Used for |
|---|---|---|---|---|
| Python | 3 with `venv`; no floor is declared | 3.14.7 locally; 3.13 in the image | [LOCAL_SETUP.md](LOCAL_SETUP.md); [deploy/Dockerfile](deploy/Dockerfile) | everything server side |
| ffmpeg and ffprobe | none declared | 8.0.1 locally; the image takes Debian trixie's package, 7.1 by the Dockerfile's comment | the operator's package manager; the Dockerfile | every cut and encode |
| Node.js | `>= 20` | 22.23.2 locally | [scripts/setup_provider.sh](scripts/setup_provider.sh), which refuses an older one | the token provider's server; the extension's `media.js` tests |
| bgutil PO token provider (server) | tag `1.3.1`, overridable with `WASTATUS_POT_VERSION` | 1.3.1 | `setup_provider.sh`, `git clone --branch` then `npm ci` | serving PO tokens on port 4416 (`WASTATUS_POT_PORT`) |
| git | any | | `setup_provider.sh`; `runlog` reads the revision | cloning the provider; the revision in the log |
| Google Chrome | **116 or later** (`minimum_chrome_version` in [src/manifest.json](src/manifest.json), manifest version 3) | 156 on the development machine | the extension's manifest | the extension's browser, and the local tool's posting browser |
| Chrome for Testing | any; set `CHROME_FOR_TESTING`, or Playwright's copy | | [scripts/extension_check.py](scripts/extension_check.py), [scripts/site_check.py](scripts/site_check.py) | throwaway browsers for end to end checks. Branded Chrome no longer accepts `--load-extension` |
| Xvfb | any | | `site_check.py` | a display for that browser |
| Tailscale | any | | optional, `--also-on tailscale` | reaching the local page from a phone |

yt-dlp also fetches its JavaScript challenge solver from GitHub on demand
(`--remote-components ejs:github` in `fetch.py`), so that piece is whatever yt-dlp
asks for at run time.

## Images

**Table DE-3: container images**

| Image | Tag | Where | Pinned |
|---|---|---|---|
| `python` | `3.13-slim-trixie` | [deploy/Dockerfile](deploy/Dockerfile) | by tag, not by digest |
| `cloudflare/cloudflared` | `2026.10.0` | [deploy/docker-compose.yml](deploy/docker-compose.yml) | by tag, run with `--no-autoupdate` |
| `snipshare:latest` | built on the host | the same | the project's own build |

## Assets

**Table DE-4: assets**

| What | Version | How it arrives |
|---|---|---|
| OpenMoji stickers, 618 pixel colour set | `17.0.0` (`VERSION` in [scripts/setup_stickers.sh](scripts/setup_stickers.sh)) | downloaded once from the project's GitHub release, about 45 MB; never committed |
| DejaVu Sans and Sans Bold | as committed | in `assets/fonts/`, unmodified |

## Outside services

**Table DE-5: services**

| Service | Used by | For | Needs | Without it |
|---|---|---|---|---|
| [YouTube](https://www.youtube.com) | local tool (yt-dlp); extension (the player in the viewer's browser, and oEmbed for the title) | the videos people clip | nothing for the local tool beyond the PO token; the viewer's own browser for the extension | nothing can be made |
| [WhatsApp Web](https://web.whatsapp.com) | local tool over CDP; extension | placing the clip in the Status composer | a signed in session in that browser | clips are made but not loaded |
| [GIPHY](https://developers.giphy.com) | the GIF shelf | optional GIF search | `WASTATUS_GIPHY_KEY` locally; each person's own key on the hosted site | the shelf says how to add a key |
| [KLIPY](https://partner.klipy.com) | the GIF shelf | optional GIF search | `WASTATUS_KLIPY_KEY` locally; each person's own key on the hosted site | the same |
| Google Identity Services | hosted site | sign-in | `WASTATUS_GOOGLE_CLIENT_ID` and an authorised origin | nobody can sign in with Google |
| Cloudflare Turnstile | hosted site | the human check on the access form | `WASTATUS_TURNSTILE_SITEKEY` and `WASTATUS_TURNSTILE_SECRET` | the check is skipped |
| Cloudflare Tunnel | hosted site | the only way in; certificates | `TUNNEL_TOKEN` in `tunnel.env` | the site is unreachable |
| [Resend](https://resend.com) | hosted site, `notify.py` | mail to the owner | `WASTATUS_RESEND_KEY`, `WASTATUS_MAIL_FROM`, `WASTATUS_MAIL_TO` | logged and skipped |
| Google Chat webhook | hosted site, `notify.py` | alerts and the digest | `WASTATUS_CHAT_WEBHOOK` | logged and skipped |
| Google Sheets API v4 | local tool, `sheet.py` | one row per accepted Status | `WASTATUS_SHEET_ID` and a service account key | the module is inert |
| An external uptime monitor | hosted site | checking `/api/v1/health` for `"ok":true` | configured outside the project | no outside view of downtime |

Every setting above is described in [.env.example](.env.example). None of their values
are in the repository (D-093).

## Pinning policy

What is pinned, and why:

- **The token provider, plugin and server, at 1.3.1.** The plugin and the server it
  talks to must match, and a new provider release can change behaviour against
  YouTube on the same day. `requirements.txt` says `==1.3.1` and
  `setup_provider.sh` clones that tag and installs with `npm ci`.
- **cloudflared, by tag**, and its self-update is off, so the front door changes only
  when a deploy changes it.
- **OpenMoji, by release.** An emoji newer than the installed release is left out of
  a line rather than drawn wrong (D-065).
- **The extension's Chrome floor**, 116, in the manifest.

What is not pinned, and the trade-off:

**Table DE-6: unpinned**

| What | Today | Risk | Option |
|---|---|---|---|
| Python packages other than the provider plugin | `>=` floors | a fresh install or image build can pick up a breaking release | a lock file (for example `pip-compile` output) for the image, keeping `>=` for the local tool |
| yt-dlp | `>=2026.7.4` | none extra: it is deliberately left free, because YouTube changes faster than a pin would be updated | keep as is; upgrade when extraction degrades |
| The Python base image | tag only | a rebuild takes whatever `3.13-slim-trixie` points to that day | pin by digest and refresh it on a schedule, once there is one (LIMITATIONS, Table LI-13) |
| ffmpeg | the distribution's or the machine's | the engine's ffmpeg arguments meet a version they were not tested on | record the version in the log, which `runlog.stamp` already does |
| Node.js | `>= 20` | a future major could break the provider's server | none needed while `npm ci` installs from the provider's own lock file |
| yt-dlp's EJS solver | fetched on demand | a solver change arrives without a deploy | none: that is its purpose |

The unpinned base image and `>=` requirements are also recorded in Table LI-13 of
[LIMITATIONS.md](LIMITATIONS.md).
