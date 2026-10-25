#!/bin/bash
# ============================================================
#  OPEN THE APP
#  Double-click to launch the Caption Transcripts window.
#  Does every step — clean, review, publish — in one place.
#  The first run installs what it needs and takes a minute.
# ============================================================

source "$(cd "$(dirname "$0")" && pwd)/_common.sh"

find_python
find_pipeline

VENV="$PIPELINE/.venv"

echo "============================================"
echo "  Caption Transcripts"
echo "============================================"
echo

# The window needs FastAPI and a webview, which the command-line steps do not.
# They live in their own .venv so the pipeline itself keeps working with plain
# system Python, exactly as it does for anyone who never opens the app.
if [ ! -x "$VENV/bin/python" ]; then
  echo "First run — creating the app environment..."
  "$PY" -m venv "$VENV" || {
    echo
    echo "ERROR: could not create the app environment."
    read -n1 -r -p "Press any key to close..."
    exit 1; }
fi

if ! "$VENV/bin/python" -c "import fastapi, uvicorn, keyring, docx" 2>/dev/null; then
  echo "Installing app components (needs internet)..."
  "$VENV/bin/python" -m pip install --upgrade pip >/dev/null 2>&1
  "$VENV/bin/python" -m pip install -r "$PIPELINE/requirements-gui.txt" || {
    echo
    echo "ERROR: install failed. Check your internet connection and try again."
    read -n1 -r -p "Press any key to close..."
    exit 1; }
  echo
fi

echo "Opening the window..."
echo "Leave this Terminal window open while you work — closing it quits the app."
echo

cd "$PIPELINE" || exit 1
"$VENV/bin/python" -m gui.main

echo
read -n1 -r -p "App closed. Press any key..."
