#!/usr/bin/env bash
# Installs the OpenMoji sticker library: 4,495 drawings at 618 pixels, plus the
# keyword file the page searches. Runs on Linux and macOS. Requires curl and unzip.
#
# OpenMoji is CC BY-SA 4.0. https://openmoji.org
set -euo pipefail

VERSION="17.0.0"
BASE="https://github.com/hfg-gmuend/openmoji"
ZIP="$BASE/releases/download/$VERSION/openmoji-618x618-color.zip"
META="https://raw.githubusercontent.com/hfg-gmuend/openmoji/$VERSION/data/openmoji.json"

if [[ -n "${WASTATUS_STICKER_DIR:-}" ]]; then
  TARGET="$WASTATUS_STICKER_DIR"
elif [[ "$(uname -s)" == "Darwin" ]]; then
  TARGET="$HOME/Library/Application Support/wastatus/stickers"
else
  TARGET="${XDG_DATA_HOME:-$HOME/.local/share}/wastatus/stickers"
fi

command -v curl  >/dev/null || { echo "curl is required" >&2; exit 1; }
command -v unzip >/dev/null || { echo "unzip is required" >&2; exit 1; }

echo "installing stickers into: $TARGET"
mkdir -p "$TARGET/openmoji" "$TARGET/mine"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "fetching OpenMoji $VERSION, about 45 MB"
curl -fsSL -o "$WORK/openmoji.zip" "$ZIP"
curl -fsSL -o "$WORK/openmoji.json" "$META"

# -o overwrites, so re-running upgrades in place rather than failing on prompts.
unzip -q -o "$WORK/openmoji.zip" -d "$TARGET/openmoji"
mv "$WORK/openmoji.json" "$TARGET/openmoji.json"

COUNT="$(find "$TARGET/openmoji" -name '*.png' | wc -l | tr -d ' ')"
echo "done. $COUNT stickers ready, and your own go in $TARGET/mine"
