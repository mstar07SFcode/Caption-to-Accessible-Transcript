#!/bin/bash
# ============================================================
#  STEP 1 — Clean Captions
#  Double-click to run. Cleans every caption file in
#  Raw_Captions and writes cleaned .vtt + flag logs to
#  Edited_Captions, then archives the originals.
# ============================================================

# Folder this script lives in (the Video Accessibility folder).
DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE="$DIR/usf-caption-pipeline"

# Find Python 3.
PY="$(command -v python3)"
if [ -z "$PY" ]; then
  echo "ERROR: Python 3 is not installed."
  echo "Install it from https://www.python.org/downloads/ and try again."
  echo
  read -n1 -r -p "Press any key to close..."
  exit 1
fi

echo "============================================"
echo "  STEP 1 — Clean Captions"
echo "============================================"
echo
echo "Make sure your .srt / .txt caption files are in:"
echo "  $DIR/Raw_Captions"
echo

# Prompt for course code and speaker (applied to this whole batch).
read -r -p "Course code (e.g. RHET-103), or leave blank: " COURSE
read -r -p "Speaker / instructor name, or leave blank: " SPEAKER
echo

ARGS=(--raw "$DIR/Raw_Captions" --out "$DIR/Edited_Captions" --archive "$DIR/Archived_Captions")
[ -n "$COURSE" ]  && ARGS+=(--course "$COURSE")
[ -n "$SPEAKER" ] && ARGS+=(--speaker "$SPEAKER")

# Offer AI cleanup if it has been set up (Setup launcher created the .venv).
VENV="$PIPELINE/.venv"
echo "Cleanup mode:"
echo "  [1] Basic — remove fillers, fix formatting (fast, free, no AI)"
echo "  [2] AI    — also fix misrecognized words, punctuation, and flag"
echo "             unclear lines for review (needs setup + API key)"
read -r -p "Choose 1 or 2 [1]: " MODE
if [ "$MODE" = "2" ]; then
  if [ ! -x "$VENV/bin/python" ]; then
    echo
    echo "AI cleanup is not set up yet. Run '0_Setup_AI_Cleanup.command' first."
    echo "Falling back to Basic cleanup."
    RUNPY="$PY"
  else
    RUNPY="$VENV/bin/python"
    if [ -z "$ANTHROPIC_API_KEY" ]; then
      echo
      read -rs -p "Paste your Anthropic API key (hidden, used only this run): " ANTHROPIC_API_KEY
      echo
      export ANTHROPIC_API_KEY
    fi
    ARGS+=(--backend api)
    echo
    read -r -p "Use batch mode? Cheaper (~50% less) but can take several minutes [y/N] " BATCH
    case "$BATCH" in
      y|Y|yes|YES) ARGS+=(--batch)
        echo "Batch mode on. Submitting all files together; please leave this window open." ;;
      *) echo "Running AI cleanup, one request per file..." ;;
    esac
  fi
else
  RUNPY="$PY"
fi
echo

cd "$PIPELINE" || { echo "ERROR: cannot find $PIPELINE"; read -n1 -r; exit 1; }
"$RUNPY" -m pipeline.batch clean "${ARGS[@]}"

echo
echo "Done. Cleaned files and flag logs are in: Edited_Captions"
echo "Next: review the FlagLog_*.txt files, then run Step 2."
echo
read -n1 -r -p "Press any key to close..."
