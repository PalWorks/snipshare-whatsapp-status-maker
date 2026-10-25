# Deployment

SnipShare, the hosted page, and the renderer behind it and the browser extension. The
local tool has no deployment: it runs where it is cloned. First written
**2026-10-24T21:00:13+05:30**, when the renderer went live; rewritten
**2026-10-25T01:40:21+05:30** for SnipShare, a self-contained Compose project behind a
Cloudflare Tunnel.

Updated **2026-10-25T15:11:42+05:30** for the audit before publication: the image
installs [deploy/requirements.txt](deploy/requirements.txt), the app and the tunnel
have process limits, and every page links to the source (D-099, D-100).

This is the generic recipe. The real values (the site's address, the host, the
accounts and keys) are in the owner's private operations notes and in the host's
`.env`, never in this repository, which is kept fit to publish
([docs/hosted-page.md](docs/hosted-page.md), Table HP-3).

## Table DP-1: what runs

| What | Value |
|---|---|
| Compose project | `snipshare`, from [deploy/docker-compose.yml](deploy/docker-compose.yml), in `/opt/snipshare` on the host |
| `app` | container `snipshare-app`, image `snipshare:latest` built on the host: the pages, the page API and the renderer's API on port 8790, reachable only inside the project's network |
| `tunnel` | container `snipshare-tunnel`, `cloudflare/cloudflared` pinned to a version: the only way in. No host port is opened |
| Network | `snipshare`, the project's own |
| Volumes | `snipshare_data` at `/data` (people database, uploads, jobs, each person's clips and stickers under `users/`, the sticker library under `stickers/`, the extension download under `src/`, logs); `snipshare_backups` at `/data/backups` (the people database, nightly, seven kept) |
| Settings | `/opt/snipshare/.env` (mode 600) for the app, every name in [.env.example](.env.example) under "SnipShare"; `/opt/snipshare/tunnel.env` (mode 600) holding `TUNNEL_TOKEN` alone |
| Image | `python:3.13-slim-trixie` with Debian's ffmpeg and [deploy/requirements.txt](deploy/requirements.txt): what the site runs, without yt-dlp, the token plugin or the websocket client |
| Limits | app: 3 CPUs, 3 GB, 512 processes, read-only root, no capabilities, user 10001. tunnel: half a CPU, 256 MB, 128 processes, read-only, no capabilities |
| Scheduled work | inside the app (`wastatus/watch.py`): checks every 5 minutes, the daily digest, backup and tidy at 03:00 UTC. Nothing in the host's crontab |
| Monitoring | an external uptime monitor on `/api/v1/health`, looking for `"ok":true` |

## Ship a change

Three settings on the deploying machine, in its `.env` or environment (not in
`.env.example`: the tool never reads them):

| Setting | What |
|---|---|
| `WASTATUS_DEPLOY_HOST` | the host, as an ssh alias |
| `WASTATUS_DEPLOY_SITE` | the site's address, which the extension is built for |
| `WASTATUS_EXTENSION_KEY` | the private key that pins the extension's id, outside the repository, mode 600 |

```bash
.venv/bin/python -m pytest          # first, always
scripts/deploy.sh                   # build the extension, copy, build the image, restart
scripts/deploy.sh --check           # what is running and what it says about itself
```

`deploy.sh` builds the extension for the site (`scripts/build_extension.py`, into the
git-ignored `dist/`), copies only what the image needs (`deploy/`, `wastatus/`,
`assets/`, `requirements.txt`) and the git revision to the host, runs
`docker compose up -d --build`, prunes this project's own superseded images by the
`project.name=snipshare` label and nothing else, waits for the app to report healthy,
and copies the extension's zip into the data volume, where `/install` offers it.

## Who may use it

People ask on the site; the admin approves on `/admin`, or on the host:

```bash
cd /opt/snipshare/deploy
docker compose exec app python -m wastatus hosted user list
docker compose exec app python -m wastatus hosted user approve someone@example.com
docker compose exec app python -m wastatus hosted user suspend someone@example.com
docker compose exec app python -m wastatus hosted user add someone@example.com --name "Some One"
docker compose exec app python -m wastatus hosted user forget someone@example.com
```

The admins are `WASTATUS_ADMIN_EMAILS` and nobody else: whoever is listed is let in
and made admin at start, whoever is taken off stops being one.

The popup's tokens still work, for the owner's own tests:
`docker compose exec app python -m wastatus hosted token add NAME`.

## One time setup

1. **The tunnel.** In Cloudflare, a remotely managed tunnel with one public hostname,
   the site, pointing at `http://app:8790`, and everything else answered 404. Its
   token goes in `/opt/snipshare/tunnel.env` as `TUNNEL_TOKEN=...`, mode 600. The
   hostname's DNS record is the tunnel's own CNAME, which Cloudflare creates.
2. **Google sign-in.** An OAuth client of type *Web application* whose authorised
   JavaScript origin is the site, consent screen with `openid email profile` only and
   links to `/privacy` and `/terms`. Its id is `WASTATUS_GOOGLE_CLIENT_ID`.
3. **Turnstile.** A managed widget for the site's hostname: the site key and secret.
4. **Mail.** A sending-only Resend key limited to a verified sending domain, a from
   address on it, and the owner's address to send to.
5. **Chat.** An incoming webhook for the space the owner watches.
6. **The extension's key**, made once: `scripts/build_extension.py --new-key PATH
   --site URL` prints the id for `WASTATUS_EXTENSION_ID`.
7. Everything else in `.env.example`'s SnipShare section, then `scripts/deploy.sh`.
   `WASTATUS_SOURCE_URL` can stay empty for an unchanged copy; a copy you have changed
   must point it at your own published changes, because the site runs AGPL code
   ([THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).
8. **The sticker library**, once, into the volume: run `scripts/setup_stickers.sh`
   with `WASTATUS_STICKER_DIR` pointing at a local folder, then
   `docker cp FOLDER/. snipshare-app:/data/stickers/`.

## Roll back

```bash
git checkout <good revision> && scripts/deploy.sh
```

The people database's schema mostly only grows (`create table if not exists`), with
one exception: on 2026-10-25 (D-095) `gif_keys` became keyed by person and provider.
A revision before that one cannot add a GIF key to the migrated table; to go back
past it, restore the last backup from `/data/backups` taken before the deploy, and
take one by hand before any deploy that migrates:
`docker compose exec app python -c "from pathlib import Path; from wastatus import accounts; accounts.Accounts(Path('/data/people.db')).backup(Path('/data/backups/people-before-deploy.db'))"`.

## Remove it

```bash
ssh "$WASTATUS_DEPLOY_HOST" 'cd /opt/snipshare/deploy && docker compose down -v'
```

then delete the tunnel in Cloudflare, which removes its DNS record, and the uptime
monitor. `-v` deletes the volumes, people, clips and backups included.
