# Context map

Which file to read for what. Start here. Last updated
**2026-10-31T13:12:52+05:30**, after the sweep that brought the documents level with Release 1 live and extension 2.1.1 (before that 2026-10-31T11:35:20+05:30, Scheduled Statuses in the account page and the capture fix; before that 2026-10-31T01:53:14+05:30, Scheduled Statuses Release 1; earlier: 2026-10-25T15:11:42+05:30, when the
documentation set was completed to the agent documentation guide
([agent_docs_guide.md](agent_docs_guide.md)) for publication).

## Table CM-1: Documentation index

| Question | File |
|---|---|
| What is this and how do I run it | [README.md](README.md) |
| I would rather click than type | `./wastatus.sh serve`, described in [README.md](README.md) |
| Just tell me how to start the page | [LOCAL_SETUP.md](LOCAL_SETUP.md), first section |
| I want to read the page on my phone | `./wastatus.sh serve --also-on tailscale`, or `WASTATUS_ALSO_ON=tailscale` in `.env` so every start has it. [LOCAL_SETUP.md](LOCAL_SETUP.md), **Two lines**, **Start the page** and **Reach the page from your phone** |
| What address do I type into the phone | the health chip at the top of the page, **another device**, which names the address and the port together. The server prints the same line when it starts. On a phone it is at the bottom of the page as well, [DECISIONS.md](DECISIONS.md) D-069 |
| Starting it is three commands and I keep forgetting one | `.env` answers all three. [LOCAL_SETUP.md](LOCAL_SETUP.md), **Two lines, once `.env` is set up**, and [DECISIONS.md](DECISIONS.md) D-044 |
| Which of these Chrome windows is this tool's, and what port is the page on | the browser this tool starts opens a label tab first, whose title is `● 8765 · wastatus`. [DECISIONS.md](DECISIONS.md) D-050 |
| The tool says a browser is on the port but it is not mine | [RUNBOOK.md](RUNBOOK.md), **Chrome will not open its debug port**. The message names the profile |
| Could this take an Instagram link? | [docs/instagram.md](docs/instagram.md), and [TASKS.md](TASKS.md) T-033 for the decision it needs |
| I have never run it, walk me through | [LOCAL_SETUP.md](LOCAL_SETUP.md) |
| How is it put together | [ARCHITECTURE.md](ARCHITECTURE.md) |
| What do the terms mean, what are the platform rules | [DOMAIN.md](DOMAIN.md) |
| I am an agent about to change code | [AGENTS.md](AGENTS.md) |
| How do I add a feature, debug, release | [PLAYBOOK.md](PLAYBOOK.md) |
| It broke, what now | [RUNBOOK.md](RUNBOOK.md) |
| What can I put on the frame, and where | [DOMAIN.md](DOMAIN.md), Table DO-3, and [DECISIONS.md](DECISIONS.md) D-052 and D-053 for the label and the top text |
| Why is the download path so convoluted | [docs/extraction.md](docs/extraction.md) |
| What would hosting this look like, and what does Evolution API actually do | [docs/hosting.md](docs/hosting.md), the investigation; [docs/extension.md](docs/extension.md) is what was built instead |
| How does the browser extension work, and why can it fetch when a server cannot | [docs/extension.md](docs/extension.md), and [ARCHITECTURE.md](ARCHITECTURE.md), **The extension and the hosted renderer** |
| SnipShare, the full page hosted for invited people: what it is, why, and how it was built | [docs/hosted-page.md](docs/hosted-page.md), DECISIONS.md D-087 to D-093, [ARCHITECTURE.md](ARCHITECTURE.md) **SnipShare** |
| The account page, both GIF keys, feedback, and its **Scheduled Statuses** section (the extension's queue framed) | [docs/account-page.md](docs/account-page.md) (Tables AP-8, AP-9), DECISIONS.md D-095, D-106 and D-107 (the tool page's Account menu) |
| What was measured before the extension was built | [docs/extension-spike.md](docs/extension-spike.md) |
| Scheduling a Status for later without taking focus: the requirement and plan, and **Section 15, what Release 1 built** (live; prepare only; Phase 0 with the owner) | [docs/scheduling.md](docs/scheduling.md), DECISIONS.md D-104, D-105 and D-107 (one Schedule button); the extension's side in [docs/extension.md](docs/extension.md), the data in [DATA_MODEL.md](DATA_MODEL.md), the permissions in [SECURITY.md](SECURITY.md), how it fits in [ARCHITECTURE.md](ARCHITECTURE.md) **Scheduled Statuses**, the terms in [DOMAIN.md](DOMAIN.md) Table DO-5 |
| A person says their schedule did not run, or where do I switch scheduling on and set limits | [RUNBOOK.md](RUNBOOK.md), **Scheduled Statuses, the pilot** (Table RB-5), and [DEPLOYMENT.md](DEPLOYMENT.md), **Scheduled Statuses: what a deploy must keep true**; the run log is in [OBSERVABILITY.md](OBSERVABILITY.md) |
| How do I change the queue's code | [PLAYBOOK.md](PLAYBOOK.md), **Change scheduling or the queue** |
| How do I install the extension, or let somebody in | [README.md](README.md), **SnipShare**; approving people and tokens in [DEPLOYMENT.md](DEPLOYMENT.md) |
| Where does the hosted renderer run, and how do I ship to it | [DEPLOYMENT.md](DEPLOYMENT.md) |
| SnipShare, the extension or the renderer broke | [RUNBOOK.md](RUNBOOK.md), **SnipShare, the hosted page** |
| Why was something built this way | [DECISIONS.md](DECISIONS.md) |
| What is assumed, what is unverified | [MEMORY.md](MEMORY.md) |
| What is known broken or missing | [LIMITATIONS.md](LIMITATIONS.md) |
| What is planned | [ROADMAP.md](ROADMAP.md) |
| What should I work on next | [TASKS.md](TASKS.md) |
| How is this verified | [TESTING.md](TESTING.md) |
| Where do credentials live | [SECURITY.md](SECURITY.md), and `.env.example` for the settings themselves |
| What may I do with this code | [LICENSE](LICENSE) (AGPL-3.0-only), [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), and [assets/fonts/LICENSE.md](assets/fonts/LICENSE.md) for the fonts |
| How do I contribute, and on what terms | [CONTRIBUTING.md](CONTRIBUTING.md) |
| What changed | [CHANGELOG.md](CHANGELOG.md) |
| Every endpoint, its fields and its errors | [API.md](API.md) |
| What is stored, where, and for how long | [DATA_MODEL.md](DATA_MODEL.md) |
| Where the logs, counts and alerts are | [OBSERVABILITY.md](OBSERVABILITY.md) |
| What went wrong before, and what was learnt | [INCIDENTS.md](INCIDENTS.md) |
| Which versions of what it depends on | [DEPENDENCIES.md](DEPENDENCIES.md) |
| A word I do not know | [GLOSSARY.md](GLOSSARY.md), then [DOMAIN.md](DOMAIN.md) |
| A question somebody has surely asked | [FAQ.md](FAQ.md) |
| How the code is written | [CODE_STYLE.md](CODE_STYLE.md) |
| Prompts for an agent: implement, review, debug, sweep the docs | [PROMPTS.md](PROMPTS.md) |
| Every command, script and workflow an agent can run | [SKILLS.md](SKILLS.md) |

## Table CM-2: Source index

| Module | Responsibility |
|---|---|
| [wastatus/cli.py](wastatus/cli.py) | argument parsing, the report, `--post` and `--load` |
| [wastatus/pipeline.py](wastatus/pipeline.py) | the engine both front ends call: window validation, then produce the clip |
| [wastatus/serve.py](wastatus/serve.py) | the local page's server, standard library only |
| [wastatus/web/](wastatus/web/) | the page: `index.html`, `app.css`, `app.js`. Mobile first, one folding card per section, see [DECISIONS.md](DECISIONS.md) D-029 and D-032. From 901px it is two columns, everything you answer on the left and the frame stuck on the right, D-067. |
| [wastatus/post.py](wastatus/post.py) | drives WhatsApp Web's Status composer over the DevTools protocol, finds a debug browser and can start one |
| [wastatus/fetch.py](wastatus/fetch.py) | yt-dlp: metadata, the client and format ladder, artwork |
| [wastatus/potoken.py](wastatus/potoken.py) | finds, starts and stops the PO token provider |
| [wastatus/compose.py](wastatus/compose.py) | Pillow: the card and the transparent text overlay |
| [wastatus/gifs.py](wastatus/gifs.py) | GIF search, GIPHY and KLIPY behind one seam. Off unless `.env` says otherwise |
| [wastatus/stickers.py](wastatus/stickers.py) | the sticker library, and pasting stickers onto a frame |
| [wastatus/render.py](wastatus/render.py) | ffmpeg filter graphs and encode settings |
| [wastatus/proc.py](wastatus/proc.py) | starts yt-dlp and ffmpeg so a render can be stopped, and kills the process group |
| [wastatus/translit.py](wastatus/translit.py) | title cleanup and Tamil romanisation |
| [wastatus/naming.py](wastatus/naming.py) | date led, human readable output filenames, and claiming one so two renders cannot pick the same |
| [wastatus/retention.py](wastatus/retention.py) | pruning the output folder |
| [wastatus/sheet.py](wastatus/sheet.py) | one row in a Google Sheet per Status WhatsApp accepted. Inert with no `WASTATUS_SHEET_ID` |
| [wastatus/runlog.py](wastatus/runlog.py) | the text log and the per run json record |
| [wastatus/timecode.py](wastatus/timecode.py) | timestamp parsing and formatting |
| [wastatus/env.py](wastatus/env.py) | reads an optional `.env` file at startup. The environment always wins over it |
| [wastatus/capture.py](wastatus/capture.py) | checks an upload from the extension and cuts the window out of it on its own timestamps |
| [wastatus/hosted.py](wastatus/hosted.py) | the hosted renderer: tokens, chunked uploads, the job queue, serving the clip, the render slots shared with the page |
| [wastatus/portal.py](wastatus/portal.py) | SnipShare: public pages, sign-in and sessions, each person's `Workspace`, grants for the extension, limits, the admin's calls, `wastatus hosted user` |
| [wastatus/accounts.py](wastatus/accounts.py) | the people database: requests, sessions and grants as hashes, usage per day, encrypted GIF keys, failure reports, alert throttling |
| [wastatus/signin.py](wastatus/signin.py), [wastatus/notify.py](wastatus/notify.py), [wastatus/watch.py](wastatus/watch.py) | Google's ID token and Turnstile; mail and Chat to the owner; the checks, digest, backup and tidy that run inside the container |
| [wastatus/pages/](wastatus/pages/) | the public pages and their layout, `site.js` (sign-in, the request form), `hosted.js` (the tool page's bridge to the extension, the Schedule picker and the Account menu, D-107), `account.js` (the account page), `admin.js` |
| [src/](src/) | the Chrome extension: `media.js` the fragment parser, `recorder.js` the capture in the YouTube page, `bridge.js`, `sw.js` the job, `popup.*`, `whatsapp.js` and `wa-bridge.js` for the composer; Node tests in `src/test` |
| [src/queue.js](src/queue.js), [src/custody.js](src/custody.js), [src/place.js](src/place.js), [src/schedule.js](src/schedule.js) | Scheduled Statuses, Release 1, in the worker: the queue's pure rules (order, spacing, limits, catch up, resume, words); the clip held in IndexedDB parts; the placement ladder and its per machine record; the stored queue, its alarms, notifications and ports. Plan and as built: [docs/scheduling.md](docs/scheduling.md) |
| [src/queue.html](src/queue.html), [src/queue.css](src/queue.css), [src/queue-page.js](src/queue-page.js) | the queue page: the table of scheduled Statuses, edited in place, Undo, Pause, history, the budget and the quiet test. Also framed by the account page as `queue.html?embed=1` (D-106) |
| [deploy/](deploy/) | the hosted site's Dockerfile, its own `requirements.txt` (what the site runs, a subset of the tool's) and the Compose project (app and tunnel) |
| [scripts/deploy.sh](scripts/deploy.sh) | ships the renderer to the production host |
| [scripts/extension_check.py](scripts/extension_check.py) | drives the real extension's popup flow in a throwaway Chrome for Testing, end to end, optionally on a throttled connection |
| [scripts/site_check.py](scripts/site_check.py) | SnipShare end to end on this machine: a server of its own, the extension, a throwaway Chrome |
| [scripts/build_extension.py](scripts/build_extension.py) | the extension built for one site, its id pinned, zipped for `/install` |
| [wastatus/label.py](wastatus/label.py) | the session label: one cached page, opened as the posting browser's first tab, whose title names the port |
| [tests/](tests/) | pytest, offline plus an opt in end to end run. `test_scheduling_limits.py` holds the server's per person limits, and `src/test/` the Node tests: `queue.test.js`, `custody.test.js`, `place.test.js` and `schedule.test.js` for the scheduling modules and `capture.test.js` for the capture's choice of YouTube tab (D-106, IN-14) |
| [scripts/setup_provider.sh](scripts/setup_provider.sh) | one time PO token provider install |
| [scripts/setup_stickers.sh](scripts/setup_stickers.sh) | one time OpenMoji sticker library install |
| [scripts/install_service.sh](scripts/install_service.sh) | installs the systemd user service that keeps the page running. Deliberately not installed, D-028 |
| [scripts/wa_post.py](scripts/wa_post.py) | manual door into the composer: load, send, cancel, screenshot, delete-all |
| [scripts/shot.py](scripts/shot.py) | screenshot a page in the debug Chrome, for reviewing the local page's design |
| [wastatus.sh](wastatus.sh) | wrapper so the tool runs from any directory |

## Deliberately absent

Nothing from the guide's list, since 2026-10-25. `INCIDENTS.md` is short because the
project is; it is mined from the decisions and the changelog rather than kept live,
so a new incident goes in CHANGELOG.md and DECISIONS.md first and is summarised
there after.
