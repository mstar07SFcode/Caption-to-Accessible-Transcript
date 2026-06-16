#!/bin/bash
# ============================================================
#  STEP 2 — Publish HTML Transcripts
#  Double-click to convert the cleaned .vtt files into
#  accessible HTML transcripts.
#  NOTE: this empties Archived_Captions at the start, archives
#  Panopto-ready .vtt files to VTT_Files, writes HTML to
#  HTML_Transcripts, and clears the Edited_Captions working files.
# ============================================================

DIR="$(cd "$(dirname "$0")" && pwd)"
PIPELINE="$DIR/usf-caption-pipeline"

PY="$(command -v python3)"
if [ -z "$PY" ]; then
  echo "ERROR: Python 3 is not installed."
  echo "Install it from https://www.python.org/downloads/ and try again."
  echo
  read -n1 -r -p "Press any key to close..."
  exit 1
fi

echo "============================================"
echo "  STEP 2 — Publish HTML Transcripts"
echo "============================================"
echo
echo "This will:"
echo "  - empty Archived_Captions (originals no longer needed)"
echo "  - save HTML transcripts to HTML_Transcripts"
echo "  - archive clean .vtt files to VTT_Files"
echo "  - clear the working files in Edited_Captions"
echo
read -r -p "Proceed? [y/N] " OK
case "$OK" in
  y|Y|yes|YES) ;;
  *) echo "Cancelled."; echo; read -n1 -r -p "Press any key to close..."; exit 0 ;;
esac
echo

VENV="$PIPELINE/.venv"
ARGS=(--edited "$DIR/Edited_Captions" --vttout "$DIR/VTT_Files" --html "$DIR/HTML_Transcripts" --archive "$DIR/Archived_Captions")
echo "Transcript structure:"
echo "  [1] Basic — one section, simple paragraphs (fast, free, no AI)"
echo "  [2] AI    — meaningful headings and paragraph breaks (needs setup + API key)"
read -r -p "Choose 1 or 2 [1]: " MODE
if [ "$MODE" = "2" ]; then
  if [ ! -x "$VENV/bin/python" ]; then
    echo "AI is not set up yet. Run '0_Setup_AI_Cleanup.command' first. Using Basic."
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
    read -r -p "Use batch mode? Cheaper (~50% less) but can take several minutes [y/N] " BATCH
    case "$BATCH" in
      y|Y|yes|YES) ARGS+=(--batch); echo "Batch mode on; please leave this window open." ;;
    esac
  fi
else
  RUNPY="$PY"
fi
echo

cd "$PIPELINE" || { echo "ERROR: cannot find $PIPELINE"; read -n1 -r; exit 1; }
"$RUNPY" -m pipeline.batch publish "${ARGS[@]}"

echo
echo "Done. Accessible transcripts are in: HTML_Transcripts"
echo "Panopto-ready caption files are in:  VTT_Files"
echo
read -n1 -r -p "Press any key to close..."
