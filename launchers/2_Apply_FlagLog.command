#!/bin/bash
# ============================================================
#  STEP 1b — Apply Flag Log Corrections
#  Double-click AFTER you have reviewed the FlagLog_*.txt files
#  in Edited_Captions (accept, edit, or delete each entry).
#  Applies the remaining corrections to the matching .vtt files.
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
echo "  STEP 1b — Apply Flag Log Corrections"
echo "============================================"
echo
echo "This applies the corrections left in the flag logs in:"
echo "  $DIR/Edited_Captions"
echo
read -r -p "Have you finished reviewing the flag logs? [y/N] " OK
case "$OK" in
  y|Y|yes|YES) ;;
  *) echo "Cancelled. Review the flag logs first, then run this again."
     echo; read -n1 -r -p "Press any key to close..."; exit 0 ;;
esac
echo

cd "$PIPELINE" || { echo "ERROR: cannot find $PIPELINE"; read -n1 -r; exit 1; }
"$PY" -m pipeline.batch apply-flaglog --edited "$DIR/Edited_Captions"

echo
echo "Done. Corrections applied; flag logs renamed to Applied_FlagLog_*."
echo "Next: run Step 3 to publish the HTML transcripts."
echo
read -n1 -r -p "Press any key to close..."
