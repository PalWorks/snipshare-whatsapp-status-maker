#!/usr/bin/env bash
# Ship SnipShare to its host and restart it.
#
#   scripts/deploy.sh            build the extension, copy, build the image, restart
#   scripts/deploy.sh --check    only say what is running there
#
# Everything this project runs on the host lives in one Compose project, `snipshare`,
# under /opt/snipshare: its own network, volumes and Cloudflare Tunnel, no host
# ports. The one thing outside it is the firewall service that keeps its containers
# off the host's private network (deploy/egress.sh, D-102), matching only its own
# subnet. The host is built on (it may be ARM), and the only images ever pruned are
# this project's own, by label.
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
# An alias, never something ssh could read as one of its own options.
[[ "$HOST" != -* ]] || { echo "WASTATUS_DEPLOY_HOST must be an ssh alias" >&2; exit 1; }
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

ssh "$HOST" "sudo mkdir -p $DEST/extension && sudo chown \$(id -u):\$(id -g) $DEST $DEST/extension && \
             test -f $DEST/.env && test -f $DEST/tunnel.env && \
             test \"\$(stat -c %a $DEST/.env)\" = 600 && test \"\$(stat -c %a $DEST/tunnel.env)\" = 600" || {
  echo "$DEST/.env and $DEST/tunnel.env must exist on the host first, mode 600, see DEPLOYMENT.md" >&2
  exit 1
}
# The extension goes into the image, read-only to the app (D-101), so it is in the
# build context before the build rather than copied into a running container after.
if [[ -n "$SITE" ]]; then
  [[ -f "$ROOT/dist/snipshare-extension.zip" ]] || { echo "the extension did not build" >&2; exit 1; }
  scp -q "$ROOT/dist/snipshare-extension.zip" "$HOST:$DEST/extension/snipshare-extension.zip"
fi
rsync -az --delete \
  --include='/deploy/***' --include='/wastatus/***' --include='/assets/***' \
  --include='/requirements.txt' --include='/.dockerignore' \
  --exclude='__pycache__/' --exclude='*' \
  "$ROOT/" "$HOST:$DEST/"
git -C "$ROOT" rev-parse --short HEAD | ssh "$HOST" "cat > $DEST/REVISION"
# --pull: the base image's security updates arrive with every deploy, rather than
# waiting on a cache nothing ever refreshes.
ssh "$HOST" "$COMPOSE build --pull app && $COMPOSE up -d --remove-orphans && \
             docker image prune -f --filter label=project.name=snipshare >/dev/null"
# After `up`, because the rules are written for the network's subnet as it now is.
ssh "$HOST" "sudo install -m 755 $DEST/deploy/egress.sh /usr/local/sbin/snipshare-egress && \
             sudo install -m 644 $DEST/deploy/snipshare-egress.service /etc/systemd/system/ && \
             sudo systemctl daemon-reload && sudo systemctl enable -q snipshare-egress && \
             sudo systemctl restart snipshare-egress"
for _ in $(seq 1 45); do
  if ssh "$HOST" "docker inspect -f '{{.State.Health.Status}}' snipshare-app" 2>/dev/null | grep -q healthy; then
    echo "snipshare is healthy, revision $(git -C "$ROOT" rev-parse --short HEAD)"
    exit 0
  fi
  sleep 2
done
echo "snipshare-app did not report healthy; check: ssh $HOST docker logs snipshare-app" >&2
exit 1
