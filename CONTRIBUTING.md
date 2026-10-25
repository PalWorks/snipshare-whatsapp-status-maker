# Contributing

Last updated **2026-10-25T15:11:42+05:30**.

SnipShare is a small, experimental project with one maintainer. Issues and pull
requests are welcome; read this first, because two things here are stricter than
usual: what a change may never do (the product posts to people's WhatsApp
audiences), and the licence your contribution is accepted under (the project is
dual licensed).

## Table CO-1: where to start

| You want to | Read |
|---|---|
| run it | [LOCAL_SETUP.md](LOCAL_SETUP.md) |
| understand it | [ARCHITECTURE.md](ARCHITECTURE.md), [DOMAIN.md](DOMAIN.md), [GLOSSARY.md](GLOSSARY.md) |
| change it | [PLAYBOOK.md](PLAYBOOK.md), [CODE_STYLE.md](CODE_STYLE.md), [AGENTS.md](AGENTS.md) |
| test it | [TESTING.md](TESTING.md) |
| know why it is the way it is | [DECISIONS.md](DECISIONS.md), [LIMITATIONS.md](LIMITATIONS.md) |
| report a vulnerability | [SECURITY.md](SECURITY.md#reporting), never a public issue |

## Branches and pull requests

- `main` is always releasable. Work on a branch named for what it does,
  `fix-upload-resume` or `page-gif-switch`, and open a pull request against `main`.
- One change per pull request. A refactor and a behaviour change go separately.
- Commit messages say what changed for a person using it, in the present tense:
  "A failed follow up text no longer hides a video that went out".
- The maintainer merges. A pull request that touches posting, the hosted site's
  access control or the extension's messaging gets a second read before it does.

## Table CO-2: the review checklist

Every pull request is read against this list; tick it in the description.

| # | Check |
|---|---|
| 1 | `.venv/bin/python -m pytest -q` passes, and `node --test src/test/*.js` if `src/` changed |
| 2 | Behaviour changes come with a test that fails without them |
| 3 | Sending a Status is still never the default anywhere: an omitted field means "load it" ([DECISIONS.md](DECISIONS.md) D-020) |
| 4 | Nothing reports a Status as posted except WhatsApp's own `ack` (D-071), and nothing retries a `StatusUnconfirmed` (D-073) |
| 5 | No address, host name, key, personal name or home directory in a tracked file; `tests/test_publishable.py` passes ([docs/hosted-page.md](docs/hosted-page.md), Table HP-3) |
| 6 | Anything user-facing works at 360 px wide, in light and dark, with 40 px touch targets and full keyboard use |
| 7 | Slow and dropped connections were considered: timeouts, retries, and what is left behind when a request dies half way |
| 8 | New settings are in `.env.example` with no value (`tests/test_env.py`) |
| 9 | The documents that describe the change are updated in the same pull request, each update timestamped |

## Licence of contributions

The project is offered under the **AGPL-3.0-only** ([LICENSE](LICENSE)) and under a
**commercial licence** ([COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)). For that to
stay possible, every contribution has to be usable under both.

By opening a pull request you confirm that:

1. **You have the right to submit it.** It is your own work, or you have permission
   to contribute it, in the terms of the
   [Developer Certificate of Origin 1.1](https://developercertificate.org/). Sign
   each commit off with `git commit -s`.
2. **It is licensed under the AGPL-3.0-only**, the same as the rest of the project.
3. **You grant PalWorks a perpetual, worldwide, non-exclusive, royalty-free,
   irrevocable licence** to use, modify, distribute and sublicense your contribution,
   including under the commercial licence and under any later version of these
   licences. You keep your copyright, and you may use your contribution in any way
   you like.

A pull request without signed-off commits cannot be merged. If you cannot agree to
point 3, say so in the pull request: the change can still be discussed, and the
maintainer may write it independently.

This is a description of the terms, not legal advice.

## What not to send

- A dependency that is not pure Python, or that pulls a native toolchain, without
  asking first in an issue ([AGENTS.md](AGENTS.md), "Ask first").
- Anything that signs in to WhatsApp as a device through an unofficial protocol
  library (whatsmeow, Baileys and the like). It risks the account a person posts
  from (D-002).
- Anything that bypasses DRM, YouTube's ads, or a platform's limits. The project
  reads only what the viewer's own browser plays, and says so in public.
- Bulk, scheduled or unattended posting.
