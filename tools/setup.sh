#!/bin/bash
# One-command setup for working ON this repo. Safe to re-run.
#
#   bash tools/setup.sh           core pipeline only (no dependencies needed)
#   bash tools/setup.sh --gui     also install the desktop GUI's dependencies
#
# What it does: creates .venv if missing, installs the git hooks, and runs the
# test suite so you know the checkout is good before you change anything.
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

WITH_GUI=0
[ "${1:-}" = "--gui" ] && WITH_GUI=1

PY=python3
command -v python3 >/dev/null || { echo "python3 not found on PATH." >&2; exit 1; }
echo "Using $($PY --version)"
echo

# 1. Virtual environment. The core pipeline is standard library only, so this
#    matters mainly for the optional extras and for a stable interpreter.
if [ -d .venv ]; then
  echo "[1/3] .venv already exists — leaving it alone."
else
  echo "[1/3] Creating .venv"
  $PY -m venv .venv
fi
VENV_PY="$REPO/.venv/bin/python"
[ -x "$VENV_PY" ] || VENV_PY="$REPO/.venv/Scripts/python.exe"   # Windows layout

if [ "$WITH_GUI" -eq 1 ]; then
  echo "      Installing GUI dependencies (requirements-gui.txt)"
  "$VENV_PY" -m pip install -q --upgrade pip
  "$VENV_PY" -m pip install -q -r requirements-gui.txt
else
  echo "      Skipping optional dependencies — the pipeline needs none."
  echo "      Re-run with --gui if you will work on the desktop app."
fi
echo

# 2. Git hooks: syncs the per-skill copies so you never commit a stale one.
echo "[2/3] Installing git hooks"
bash tools/install_hooks.sh | sed 's/^/      /'
echo

# 3. Prove the checkout is sound.
echo "[3/3] Running the test suite"
LOG="$(mktemp)"
trap 'rm -f "$LOG"' EXIT
if "$VENV_PY" tests/test_pipeline.py > "$LOG" 2>&1; then
  tail -1 "$LOG" | sed 's/^/      /'
else
  echo "      Tests FAILED:"
  sed 's/^/      /' "$LOG"
  exit 1
fi

echo
echo "Ready. Read CONTRIBUTING.md for the one rule that matters:"
echo "  edit rules/, pipeline/ and templates/ at the REPO ROOT, never the"
echo "  copies under skills/ -- the hook and CI keep those in step for you."
