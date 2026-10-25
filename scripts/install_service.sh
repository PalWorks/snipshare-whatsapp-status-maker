#!/usr/bin/env bash
# Run the page as a background service, so it survives a closed terminal and comes
# back after a reboot without being started by hand.
#
#   bash scripts/install_service.sh                  # loopback only
#   bash scripts/install_service.sh --also-on tailscale
#
# A user service, not a system one: it runs as you, reaches your own home
# directory, and needs no root. Everything it writes is under ~/.config/systemd.
#
# Undo it with:
#   systemctl --user disable --now wastatus
#   rm ~/.config/systemd/user/wastatus.service
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$UNIT_DIR/wastatus.service"
OUT_DIR="${WASTATUS_OUT:-$HOME/wastatus-out}"
EXTRA=("$@")

if ! command -v systemctl >/dev/null 2>&1; then
  echo "This machine has no systemctl. On macOS the same job is a launchd plist;" >&2
  echo "see LOCAL_SETUP.md. Until then, run ./wastatus.sh serve by hand." >&2
  exit 1
fi
if [ ! -x "$HERE/.venv/bin/python" ]; then
  echo "No virtualenv at $HERE/.venv. Follow LOCAL_SETUP.md first." >&2
  exit 1
fi

mkdir -p "$UNIT_DIR" "$OUT_DIR"

# The output folder is an absolute path here on purpose: a service has no
# working directory you can reason about from the outside.
cat > "$UNIT" <<UNIT_FILE
[Unit]
Description=wastatus, the WhatsApp Status maker page
Documentation=file://$HERE/LOCAL_SETUP.md
# Tailscale may still be coming up at boot, and --also-on tailscale needs an
# address from it. Restart= below covers the case where it is not ready yet.
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$HERE
# Quoted for systemd, so a home folder with a space in its name still works.
ExecStart="$HERE/wastatus.sh" serve --no-open -o "$OUT_DIR" ${EXTRA[*]:-}
Restart=on-failure
RestartSec=10
# The page holds a per process token, so a restart invalidates open tabs. That is
# correct: a reload gets the new one.
KillSignal=SIGINT
TimeoutStopSec=20

[Install]
WantedBy=default.target
UNIT_FILE

systemctl --user daemon-reload
systemctl --user enable --now wastatus.service

# Without this the service stops when you log out and does not start at boot.
if ! loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
  echo
  echo "To keep it running when you are logged out, and to start it at boot:"
  echo "  sudo loginctl enable-linger $USER"
fi

echo
echo "Installed $UNIT"
echo "  status:  systemctl --user status wastatus"
echo "  logs:    journalctl --user -u wastatus -f"
echo "  restart: systemctl --user restart wastatus   # after changing the code"
echo "  clips:   $OUT_DIR"
