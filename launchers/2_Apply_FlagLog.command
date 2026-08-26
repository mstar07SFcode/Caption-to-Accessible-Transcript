#!/bin/bash
# ============================================================
#  STEP 1b — Apply Flag Log Corrections
#  Double-click AFTER you have reviewed the FlagLog_*.txt files
#  in Edited_Captions (accept, edit, or delete each entry).
#  Applies the remaining corrections to the matching .vtt files.
# ============================================================

source "$(cd "$(dirname "$0")" && pwd)/_common.sh"

find_python
find_pipeline

echo "============================================"
echo "  STEP 1b — Apply Flag Log Corrections"
echo "============================================"
echo

get_workdir
DIR="$WORKDIR"

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

cd "$PIPELINE" || exit 1
"$PY" -m pipeline.batch apply-flaglog --edited "$DIR/Edited_Captions"

echo
echo "Done. Corrections applied; flag logs renamed to Applied_FlagLog_*."
echo "Next: run Step 3 to publish the HTML transcripts."
echo
read -n1 -r -p "Press any key to close..."
