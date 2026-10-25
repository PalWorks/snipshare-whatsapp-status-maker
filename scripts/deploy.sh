#!/usr/bin/env bash
# Ship SnipShare to its host and restart it.
#
#   scripts/deploy.sh            build the extension, copy, build the image, restart
#   scripts/deploy.sh --check    only say what is running there
#
# Everything this project runs on the host lives in one Compose project, `snipshare`,
# under /opt/snipshare: its own network, volumes and Cloudflare Tunnel, no host
# ports, nothing in shared configuration. The host is built on (it may be ARM), and
# the only images ever pruned are this project's own, by label.
#
# Three settings, from the environment or from the local .env, never from here: they
# name somebody's machine and site, and this repository is meant to be fit to publish.
#   WASTATUS_DEPLOY_HOST     the host, as an ssh alias
#   WASTATUS_DEPLOY_SITE     the site's address, for the extension built for it
#   WASTATUS_EXTENSION_KEY   the private key that pins the extension's id
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
setting() {
  local name="$1"
  if [[ -z "${!name:-}" && -f "$ROOT/.env" ]]; then
    sed -n "s/^${name}=//p" "$ROOT/.env" | tail -1
  else
    printf '%s' "${!name:-}"
  fi
}
HOST="$(setting WASTATUS_DEPLOY_HOST)"
SITE="$(setting WASTATUS_DEPLOY_SITE)"
KEY="$(setting WASTATUS_EXTENSION_KEY)"
: "${HOST:?set WASTATUS_DEPLOY_HOST to the ssh alias of the host, see DEPLOYMENT.md}"
DEST=/opt/snipshare
COMPOSE="cd $DEST/deploy && docker compose"

if [[ "${1:-}" == "--check" ]]; then
  ssh "$HOST" "$COMPOSE ps --format '{{.Name}} {{.Status}}'; cat $DEST/REVISION; \
               docker exec snipshare-app python -c \"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8790/api/v1/health').read().decode())\""
  exit 0
fi

if [[ -n "$SITE" ]]; then
  # The extension answers only the site it is built for, and the server only pages
  # on its own address: the two must be the same, or every capture is refused.
  served="$(ssh "$HOST" "sed -n 's/^WASTATUS_PUBLIC_URL=//p' $DEST/.env 2>/dev/null | tail -1")"
  if [[ -n "$served" && "${served%/}" != "${SITE%/}" ]]; then
    echo "WASTATUS_DEPLOY_SITE ($SITE) is not the server's WASTATUS_PUBLIC_URL ($served)" >&2
    exit 1
  fi
  "$ROOT/.venv/bin/python" "$ROOT/scripts/build_extension.py" --site "$SITE" \
    ${KEY:+--key "$KEY"} >/dev/null
fi

ssh "$HOST" "sudo mkdir -p $DEST && sudo chown \$(id -u):\$(id -g) $DEST && \
             test -f $DEST/.env && test -f $DEST/tunnel.env" || {
  echo "$DEST/.env and $DEST/tunnel.env must exist on the host first, see DEPLOYMENT.md" >&2
  exit 1
}
rsync -az --delete \
  --include='/deploy/***' --include='/wastatus/***' --include='/assets/***' \
  --include='/requirements.txt' --include='/.dockerignore' \
  --exclude='__pycache__/' --exclude='*' \
  "$ROOT/" "$HOST:$DEST/"
git -C "$ROOT" rev-parse --short HEAD | ssh "$HOST" "cat > $DEST/REVISION"
ssh "$HOST" "$COMPOSE up -d --build --remove-orphans && \
             docker image prune -f --filter label=project.name=snipshare >/dev/null"
for _ in $(seq 1 45); do
  if ssh "$HOST" "docker inspect -f '{{.State.Health.Status}}' snipshare-app" 2>/dev/null | grep -q healthy; then
    if [[ -f "$ROOT/dist/snipshare-extension.zip" && -n "$SITE" ]]; then
      scp -q "$ROOT/dist/snipshare-extension.zip" "$HOST:$DEST/snipshare-extension.zip"
      ssh "$HOST" "docker cp $DEST/snipshare-extension.zip snipshare-app:/data/extension/snipshare-extension.zip"
    fi
    echo "snipshare is healthy, revision $(git -C "$ROOT" rev-parse --short HEAD)"
    exit 0
  fi
  sleep 2
done
echo "snipshare-app did not report healthy; check: ssh $HOST docker logs snipshare-app" >&2
exit 1
