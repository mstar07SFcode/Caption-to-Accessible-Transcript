#!/bin/bash
# ============================================================
#  ONE-TIME SETUP — AI Cleanup
#  Double-click once to enable the AI cleanup option in the
#  Step 1 and Step 3 launchers. Creates a small private Python
#  environment inside usf-caption-pipeline and installs the
#  Anthropic library there. Safe to run again any time.
# ============================================================

DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE="$DIR/usf-caption-pipeline"
VENV="$PIPELINE/.venv"

PY="$(command -v python3)"
if [ -z "$PY" ]; then
  echo "ERROR: Python 3 is not installed."
  echo "Install it from https://www.python.org/downloads/ and run this again."
  echo
  read -n1 -r -p "Press any key to close..."
  exit 1
fi

echo "============================================"
echo "  Setting up AI cleanup (one time)"
echo "============================================"
echo
if [ ! -d "$VENV" ]; then
  echo "Creating Python environment..."
  "$PY" -m venv "$VENV" || { echo "ERROR: could not create environment."; read -n1 -r; exit 1; }
fi
echo "Installing/updating the Anthropic library..."
"$VENV/bin/python" -m pip install --upgrade pip >/dev/null 2>&1
if "$VENV/bin/python" -m pip install --upgrade anthropic; then
  echo
  echo "AI cleanup is ready."
  echo "You can now choose 'AI cleanup' when you run Step 1 or Step 3."
  echo
  echo "You will need an Anthropic API key (starts with sk-ant-...)."
  echo "The launcher will ask you to paste it, or you can set it once in"
  echo "Terminal with:  export ANTHROPIC_API_KEY=sk-ant-..."
else
  echo
  echo "ERROR: install failed. Check your internet connection and try again."
fi
echo
read -n1 -r -p "Press any key to close..."
