#!/usr/bin/env bash
# Convenience wrapper so you can run ./wastatus.sh instead of remembering the
# virtualenv path. Works from any directory.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Output lands in the directory you ran from, not in the project.
exec env PYTHONPATH="$HERE" "$HERE/.venv/bin/python" -m wastatus "$@"
