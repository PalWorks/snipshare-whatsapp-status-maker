#!/usr/bin/env bash
# Installs the bgutil proof-of-origin token provider that yt-dlp needs in order
# to fetch YouTube media. Runs on Linux and macOS. Requires git and node >= 20.
set -euo pipefail

REPO="https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git"
# The server half has to match the yt-dlp plugin half pinned in requirements.txt.
VERSION="${WASTATUS_POT_VERSION:-1.3.1}"

if [[ -n "${WASTATUS_POT_DIR:-}" ]]; then
  TARGET="$WASTATUS_POT_DIR"
elif [[ "$(uname -s)" == "Darwin" ]]; then
  TARGET="$HOME/Library/Application Support/wastatus/bgutil"
else
  TARGET="${XDG_DATA_HOME:-$HOME/.local/share}/wastatus/bgutil"
fi

command -v node >/dev/null || { echo "node >= 20 is required" >&2; exit 1; }
command -v git  >/dev/null || { echo "git is required" >&2; exit 1; }

NODE_MAJOR="$(node --version | sed 's/^v\([0-9]*\).*/\1/')"
[[ "$NODE_MAJOR" -ge 20 ]] || { echo "node >= 20 required, found $(node --version)" >&2; exit 1; }

echo "installing provider into: $TARGET"
mkdir -p "$(dirname "$TARGET")"

if [[ -d "$TARGET/.git" ]]; then
  git -C "$TARGET" fetch --depth 1 --quiet origin tag "$VERSION"
  # --force: an older version of this script ran `npm install`, which can leave the
  # lock file changed, and a plain checkout would refuse over it.
  git -C "$TARGET" checkout --quiet --force "$VERSION"
elif [[ -e "$TARGET" && -n "$(ls -A "$TARGET" 2>/dev/null)" ]]; then
  # Never delete a folder this script did not make.
  echo "$TARGET exists and is not a checkout of the provider. Empty it or point" >&2
  echo "WASTATUS_POT_DIR somewhere else, then run this again." >&2
  exit 1
else
  git clone --depth 1 --branch "$VERSION" --quiet "$REPO" "$TARGET"
fi

cd "$TARGET/server"
npm ci --silent --no-audit --no-fund
npx --yes tsc

echo "done. wastatus will start the provider automatically when it runs."
