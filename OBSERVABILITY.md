# Observability

Last updated **2026-10-25T15:21:02+05:30**

What the tool and the hosted site record about themselves, what raises an alert, and
where to look when something is wrong. Symptom to fix is in [RUNBOOK.md](RUNBOOK.md);
this file is about the instruments.

There are three kinds of signal: **logs** (two files, written by both the local tool
and the hosted site), **alerts and the daily digest** (hosted site only, to the
owner's Chat space), and **the admin page** (hosted site only). There is **no
tracing**: no spans, no request ids carried across the page, the extension and the
renderer, and no tracing library is installed. A failure is followed by its time,
its run record and its report row, not by a trace id.

## Logs

Both outputs come from [wastatus/runlog.py](wastatus/runlog.py), and both answer a
different question (D-011).

**Table OB-1: the log files**

| File | What it is | Written by | Read it when |
|---|---|---|---|
| `wastatus.log` | rotating text, 2 MB a file, three backups (`wastatus.log.1` to `.3`). Carries the full yt-dlp and ffmpeg failure output, which is otherwise lost | `runlog.setup`, once per process | something broke and you need the subprocess's own words |
| `runs.jsonl` | one JSON object per run, appended when the run finishes | `runlog.Run.finish` | you want trends: which extraction strategy is winning, how often runs fail, when a clip was made |
| `chrome.log` | the posting Chrome's own output, capped at 2 MB | `post.chrome_log_path` | the posting browser would not start or open its debug port |

**Where the directory is.** `WASTATUS_LOG_DIR` if it is set, otherwise `logs/` at the
repository root. The hosted image sets `WASTATUS_LOG_DIR=/data/logs`, inside the data
volume ([deploy/Dockerfile](deploy/Dockerfile)). The tests point it at a temporary
directory through an autouse guard in `tests/conftest.py`, after the suite was found
seeding the real `runs.jsonl` with fake runs (see [INCIDENTS.md](INCIDENTS.md),
IN-07).

**An unwritable log directory never stops a clip.** `setup` swallows the `OSError`
and carries on without a file handler; a run record that cannot be written is a
warning, not a failure.

**The session stamp.** `runlog.stamp` writes one block at the top of each session:
Python and platform, the yt-dlp, ffmpeg and Chrome versions, the debug ports tried,
the git revision (with `(modified)` for a dirty tree), and the **names** of the
settings `.env` supplied. Values are never written, so a key cannot reach the log by
accident.

### What a run record holds

`Run` starts with `started_at` and whatever the caller passes, collects fields with
`set`, times each stage with `stage(name)`, and on `finish` adds `status`, `stages`
(seconds per stage) and `elapsed`.

**Table OB-2: run record fields worth knowing**

| Field | Meaning |
|---|---|
| `status` | `ok`, `failed`, `cancelled`, `error` (the renderer's API), `post_failed`, `post_unconfirmed` |
| `source` | `hosted-page` for a render from SnipShare; absent for the local tool |
| `user` | on the hosted site, the person's id, never the email |
| `url`, `video_id`, `start`, `end`, `duration`, `mode` | what was asked for |
| `client`, `format`, `failed_attempts` | which rung of the extraction ladder won, and what fell through first (local tool) |
| `stem`, `output`, `output_bytes` | the clip that was made |
| `stages`, `elapsed` | where the time went |
| `error` | on a failure, the exception's type and message |
| `posted`, `post_seconds`, `post_error`, `loaded` | the posting step, local tool only |

### Request logging on the hosted site

`SiteHandler.log_message` in [wastatus/portal.py](wastatus/portal.py) logs requests at
debug level with the caller's address (from `CF-Connecting-IP` when
`WASTATUS_TRUST_PROXY` is on) and any token in the URL replaced by `REDACTED`.
Successful polls (`/api/state`, `/api/task`, `/api/v1/health` and the rest of
`QUIET`) are not logged, so the file is not buried in them. A refused renderer
request is logged as `hosted refused METHOD PATH: status message`; a 401 is not,
because scanners send those all day.

Docker keeps the containers' standard output as well: `json-file`, 10 MB times three
for the app and 5 MB times two for the tunnel
([deploy/docker-compose.yml](deploy/docker-compose.yml)).

## Metrics

There is no metrics system. The figures that exist are counters in SQLite and a few
in memory, read by the watcher and the admin page.

**Table OB-3: what is counted**

| Figure | Where it lives | Kept for |
|---|---|---|
| Clips, failures, upload bytes, render seconds, per person per UTC day | the `usage` table in the people database ([wastatus/accounts.py](wastatus/accounts.py)) | as long as the person's account |
| Each render's outcome and time, across everybody | `Portal._outcomes`, in memory, the last 2000 | until a restart |
| Renders started in the last hour, for the hourly cap | `Portal._renders`, in memory | until a restart: a restart forgets the hour |
| One row per clip made: video, title, mode, window, seconds, error | the `history` table | as long as the account |
| Failure reports: source, phase, code, short detail, versions | the `reports` table | 30 days; deleting an account blanks the email on its rows |
| When each alert key last fired, and how often it was suppressed | the `alerts` table | indefinitely |

## The health endpoint

`GET /api/v1/health` (and `HEAD`) answers without authentication, from
`Renderer.health` in [wastatus/hosted.py](wastatus/hosted.py):

```json
{"ok": true, "version": 1, "queued": 0, "rendering": 0, "workers": 1}
```

`rendering` is the slots in use, which counts the page's renders and the popup's
alike. Two things read it:

- **Docker's `HEALTHCHECK`**, every 30 seconds from inside the container, which
  fails on anything but a 200. `scripts/deploy.sh` waits for it to report healthy.
- **An external uptime monitor** on the public address, looking for `"ok":true`
  ([DEPLOYMENT.md](DEPLOYMENT.md), Table DP-1). It is the one piece of monitoring
  outside the project; its configuration is in the owner's private operations notes.

The local page has its own health panel (`/api/state`): the chip at the top right,
with rows for ffmpeg, the token provider, WhatsApp Web and another device. See
[LOCAL_SETUP.md](LOCAL_SETUP.md), **If something looks wrong**.

## Alerts

Every alert goes through `Portal.alert(key, text, every)`. It logs a warning, then
asks `Accounts.should_alert`, which lets a key through at most once per `every`
seconds (an hour by default) and counts the ones it holds back, so a storm is one
line. What gets through is posted to the owner's Google Chat space by
[wastatus/notify.py](wastatus/notify.py).

**Table OB-4: alert keys**

| Key | Raised when | Raised by | At most |
|---|---|---|---|
| `disk-low` | less than 5 GB free on the data volume | `watch.check`, every 5 minutes | hourly |
| `disk` | the renderer refused a clip because the disk is full | `Portal` | hourly |
| `queue-wait` | a popup job has waited more than 5 minutes for the renderer | `watch.check` | hourly |
| `hourly-cap` | the cap of `WASTATUS_RENDERS_PER_HOUR` renders (60 by default) across everybody is reached | `Portal` | hourly |
| `render-rate` | at least 5 renders this hour and more than 20 percent of them failed | `Portal.render_finished` | hourly |
| `render-error:<kind>` | a render raised; one key per exception type | `Portal.render_failed` | hourly per type |
| `clips:<person>:<day>` | a person has made 80 percent of today's clips | `Portal.render_finished` | daily |
| `uploads:<person>:<day>` | a person has used 80 percent of today's upload allowance | `Portal.on_upload` | daily |
| `<source>-failures` | 3 or more reports from one source in an hour, from at least 2 people. Usually YouTube or WhatsApp has changed | `_report` | hourly |
| `signup-flood` | sign-ups from one address arriving faster than 5 an hour; they are refused | `_signup` | hourly |

An access request is not an alert: it is mailed to the owner and posted to Chat at
once by `tell_owner_of_request`.

### Delivery

**Table OB-5: the two channels**

| Channel | Settings | Used for |
|---|---|---|
| Email through Resend | `WASTATUS_RESEND_KEY`, `WASTATUS_MAIL_FROM`, `WASTATUS_MAIL_TO` | access requests, feedback. Only ever to the owner's own address |
| Google Chat webhook | `WASTATUS_CHAT_WEBHOOK` | alerts, the digest, access requests |

Both are optional and fire and forget. A message that cannot be delivered is logged
(`notification not delivered`, `Resend answered N`, `the chat webhook answered N`)
and dropped, so a notification can never cost anybody a sign-up, a clip or a page
load. With a channel unset the log says `mail not configured; skipped` or `chat not
configured; skipped`. The admin page shows which channels are on.

## The watcher and the daily digest

[wastatus/watch.py](wastatus/watch.py) runs as a thread inside the app container. No
host crontab is involved, so removing the project removes all of it.

**Table OB-6: scheduled work**

| When | What |
|---|---|
| Every 5 minutes | free disk against the 5 GB floor; the oldest waiting job against 5 minutes |
| Once a day, from 03:00 UTC | the digest, then the backup, then the tidy. Each step runs even if the one before it failed |

**The digest** goes to Chat: yesterday's people, clips and failures, MB uploaded; new
and waiting requests; the busiest hour; the five most common failure reports as
`source/phase/code xN`; free disk. **The backup** copies the people database to
`/data/backups/people-YYYY-MM-DD.db`, mode 600, seven kept. **The tidy** removes the
clips of anyone not seen in 90 days and logs how many.

A check that raises is logged (`the watch could not run its checks`, `daily step X
failed`) and the loop carries on.

## Failure reports from the page and the extension

The extension does not talk to the server about failures itself. The hosted page
drives it (D-090), and when a capture, a load into WhatsApp or a words lookup fails,
`report()` in [wastatus/pages/hosted.js](wastatus/pages/hosted.js) posts to
`/api/report`:

- `source`: `capture`, `load`, `page` or `words`
- `phase` and `code`: the step and a short reason, at most 80 characters
- `versions`: the extension's version and the browser's brands

Never the video, the title, the email typed or the words. The server rate limits a
person to 30 reports an hour, stores the row against their account, and raises
`<source>-failures` as in Table OB-4. Render failures are written to the same table
by the server itself, with source `render`; feedback from the account page is kept
there too, with source `feedback`. The last failure's code is also kept in the
browser's `localStorage` so the feedback form can offer to include it.

## The admin page

`/admin`, for admin accounts only, reads `GET /api/admin` for a chosen range of
UTC days ([wastatus/pages/admin.js](wastatus/pages/admin.js)).

**Table OB-7: what the admin page shows**

| Part | Figures |
|---|---|
| Totals for the range | people active, clips made, failed, uploaded, new requests |
| Now | jobs waiting, jobs rendering, GB free, whether mail and Chat are on |
| Requests | everyone pending, to approve or decline |
| Usage | per person: clips, failed, uploaded, render time |
| People | everyone, with their range figures |
| Failures | the report rows in the range, up to 500: source, phase, code, versions |

## Where to look for what

**Table OB-8: question to place**

| Question | Look at |
|---|---|
| Is the site up? | `curl -s "$WASTATUS_DEPLOY_SITE/api/v1/health"`, the uptime monitor, `scripts/deploy.sh --check` |
| Why did this local run fail? | `tail -1 logs/runs.jsonl`, then `tail -40 logs/wastatus.log` |
| Is the extraction ladder degrading? | `grep -o '"client": "[^"]*"' logs/runs.jsonl \| sort \| uniq -c`, and `grep "fell through" logs/wastatus.log` |
| Why will the posting browser not start? | `logs/chrome.log` |
| Why did a hosted render fail? | `docker exec snipshare-app tail -50 /data/logs/wastatus.log` and `tail -5 /data/logs/runs.jsonl` on the host |
| Are captures or loads failing for several people? | the Chat alert, the admin page's **Failures**, the morning digest |
| Is the tunnel the problem? | a 502 or 1033 from Cloudflare; `docker compose ps`, then `docker compose logs --tail 30 tunnel` |
| Who used it, and how much? | the admin page's **Usage**, or `wastatus hosted user list` in the container |
| Did a Status really go out? | the run record's `status`: `ok` means WhatsApp acknowledged it, `post_unconfirmed` means it did not answer (D-071) |

The full commands are in [RUNBOOK.md](RUNBOOK.md), **The server** and **The renderer**.

## What is not observed

**Table OB-9: gaps**

| Gap | Consequence | Option |
|---|---|---|
| No tracing | a failure spanning the page, the extension and the renderer is joined by time and person, by hand | add a request id the page mints and the server logs; cheap, and enough at this scale |
| In-memory render counters | a restart forgets the hour's renders and failure rate | persist them in SQLite if restarts ever hide a failure storm |
| No container memory alert | the planned "memory near its limit" check ([docs/hosted-page.md](docs/hosted-page.md), Table HP-4) is not in `watch.py` | read the cgroup's memory figures in `watch.check` |
| Product analytics | PostHog is named as optional in docs/hosted-page.md; nothing in the code sends events | none needed until the funnel matters |
