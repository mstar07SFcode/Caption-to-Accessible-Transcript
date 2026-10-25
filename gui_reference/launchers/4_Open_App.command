#!/bin/bash
# ============================================================
#  OPEN THE APP
#  Double-click to launch the Caption Transcripts window.
#  First run installs what it needs (takes a minute).
# ============================================================

source "$(cd "$(dirname "$0")" && pwd)/_common.sh"
require_python

echo "Starting Caption Transcripts..."
echo

if [ ! -x "$VENV/bin/python" ]; then
  echo "First run - creating the app environment..."
  "$PY" -m venv "$VENV" || { echo "ERROR: could not create environment."; read -n1 -r; exit 1; }
fi

if ! "$VENV/bin/python" -c "import fastapi, uvicorn, keyring, docx" 2>/dev/null; then
  echo "Installing app components (needs internet)..."
  "$VENV/bin/python" -m pip install --upgrade pip >/dev/null 2>&1
  "$VENV/bin/python" -m pip install -r "$REPO/requirements-gui.txt" || {
    echo "ERROR: install failed. Check your internet connection."
    read -n1 -r -p "Press any key to close..."; exit 1; }
fi

cd "$REPO" || exit 1
"$VENV/bin/python" -m gui.main

echo
read -n1 -r -p "App closed. Press any key..."
