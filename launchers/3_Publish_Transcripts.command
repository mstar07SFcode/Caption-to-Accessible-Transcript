#!/bin/bash
# ============================================================
#  STEP 2 — Publish HTML Transcripts
#  Double-click to convert the cleaned .vtt files into
#  accessible HTML transcripts.
#  Nothing is deleted unless you ask for it at the prompt.
# ============================================================

source "$(cd "$(dirname "$0")" && pwd)/_common.sh"

find_python
find_pipeline

echo "============================================"
echo "  STEP 2 — Publish HTML Transcripts"
echo "============================================"
echo

get_workdir
DIR="$WORKDIR"

echo "This will:"
echo "  - save HTML transcripts to HTML_Transcripts"
echo "  - archive clean .vtt files to VTT_Files"
echo
read -r -p "Proceed? [y/N] " OK
case "$OK" in
  y|Y|yes|YES) ;;
  *) echo "Cancelled."; echo; read -n1 -r -p "Press any key to close..."; exit 0 ;;
esac
echo

ARGS=(--edited "$DIR/Edited_Captions" --vttout "$DIR/VTT_Files" --html "$DIR/HTML_Transcripts" --archive "$DIR/Archived_Captions")

# Tidy-up is opt-in and runs only after the transcripts are safely written.
echo "Afterward, tidy up the working files?"
echo "  This empties Archived_Captions and deletes the working .vtt files"
echo "  and flag logs in Edited_Captions. Your HTML transcripts and VTT_Files"
echo "  are kept either way."
read -r -p "Tidy up? [y/N] " TIDY
case "$TIDY" in
  y|Y|yes|YES) ARGS+=(--delete-working); echo "Will tidy up after publishing." ;;
  *) echo "Keeping all working files." ;;
esac
echo

VENV="$PIPELINE/.venv"
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

cd "$PIPELINE" || exit 1
"$RUNPY" -m pipeline.batch publish "${ARGS[@]}"

echo
echo "Done. Accessible transcripts are in: $DIR/HTML_Transcripts"
echo "Panopto-ready caption files are in:  $DIR/VTT_Files"
echo
read -n1 -r -p "Press any key to close..."
