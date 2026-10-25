# Third-party notices

Last updated **2026-10-25T15:11:42+05:30**.

This project's own code is AGPL-3.0-only ([LICENSE](LICENSE)), or commercially
licensed by agreement ([COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)). It uses the
work of others, which keeps its own terms. Nothing below is copied into this
repository except the two fonts; everything else is installed by `pip`, by a setup
script, or by the operator, and is used as published.

## Table TP-1: Python packages

| Package | Licence | Where it is used | Installed for |
|---|---|---|---|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense | reads a YouTube window, run as a separate process (`fetch.py`) | the local tool only |
| [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) | GPL-3.0 | a yt-dlp plugin, loaded by yt-dlp, never imported by this code; its Node server is cloned by `scripts/setup_provider.sh` | the local tool only |
| [websocket-client](https://github.com/websocket-client/websocket-client) | Apache-2.0 | drives an already signed in WhatsApp Web over the Chrome debug protocol (`post.py`) | the local tool only |
| [Pillow](https://python-pillow.org) | MIT-CMU | draws every card, sticker and frame | both |
| [Unidecode](https://github.com/avian2/unidecode) | GPL-2.0-or-later | romanises any non-Latin title (`translit.py`) | both |
| [aksharamukha](https://github.com/virtualvinodh/aksharamukha-python) | AGPL-3.0 | romanises Tamil the way Tamil speakers spell it (`translit.py`); optional, Unidecode is the fallback | both |
| [google-auth](https://github.com/googleapis/google-auth-library-python) | Apache-2.0 | checks a Google sign-in, and writes the optional Google Sheet | both |
| [requests](https://github.com/psf/requests) | Apache-2.0 | the transport `google-auth` uses | both |
| [cryptography](https://github.com/pyca/cryptography) | Apache-2.0 or BSD-3-Clause | encrypts people's GIF keys on the hosted site; signs the extension's id at build | both |
| [pytest](https://pytest.org) | MIT | the tests | development |

The hosted image installs [deploy/requirements.txt](deploy/requirements.txt), which
leaves out the three marked "local tool only".

**Why AGPL fits:** Unidecode (GPL-2.0-or-later), the token plugin (GPL-3.0) and
aksharamukha (AGPL-3.0) are all compatible with AGPL-3.0. Because the hosted site
runs aksharamukha for people over a network, every page of the site links to this
repository's source (`WASTATUS_SOURCE_URL`, in the footer). A copy you have changed
must point that link at your own changed source.

## Table TP-2: bundled and downloaded assets

| What | Licence | How it gets here |
|---|---|---|
| DejaVu Sans and DejaVu Sans Bold, `assets/fonts/` | Bitstream Vera licence with the DejaVu changes, reproduced in [assets/fonts/LICENSE.md](assets/fonts/LICENSE.md) | committed, unmodified |
| [OpenMoji](https://openmoji.org) sticker drawings | CC BY-SA 4.0 | downloaded once by `scripts/setup_stickers.sh`, never committed. A clip that carries one carries an OpenMoji drawing; credit OpenMoji when you share it beyond a Status |
| The extension's icons, `src/icons/` | this project's own | committed |

## Table TP-3: programs and services it talks to

| What | Terms | Used for |
|---|---|---|
| ffmpeg and ffprobe | LGPL-2.1-or-later, or GPL depending on the build | every cut and encode. Not shipped here: the local tool uses the one installed; the hosted image installs Debian's package |
| Google Chrome or Chrome for Testing | Google's terms | the extension's browser, and the local tool's posting browser |
| YouTube | [YouTube Terms of Service](https://www.youtube.com/t/terms) | the videos people choose to clip |
| WhatsApp Web | [WhatsApp Terms of Service](https://www.whatsapp.com/legal) | where a clip is placed for the person to send |
| GIPHY and KLIPY | each provider's API terms; each requires its credit line, which the page shows with their results | optional GIF search, with keys people supply themselves |
| Google Identity Services | Google's API terms | sign-in on the hosted site |
| Cloudflare Turnstile and Tunnel, `cloudflare/cloudflared` (Apache-2.0) | Cloudflare's terms | the hosted site's check that a visitor is a person, and its only way in |
| Resend | Resend's terms | the hosted site's email to the operator |

YouTube, WhatsApp, Google, Meta, GIPHY, KLIPY and Cloudflare are trademarks of their
owners. They are named only to say what this project works with; this project is not
affiliated with, endorsed or sponsored by any of them.
