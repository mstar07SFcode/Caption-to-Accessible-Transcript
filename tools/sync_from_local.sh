#!/bin/bash
# Sync canonical local sources INTO this plugin repo before committing/pushing.
#
# Canonical lives in your local Video Accessibility folder (the repo's parent):
#   - Caption_Cleanup_Rules.md           (editing rules)
#   - usf-caption-pipeline/pipeline/      (pipeline package incl. prompts)
#   - HTML_Transcript_Template.md         (HTML template)
#   - *.command                           (launchers)
#
# This copies them into the repo so GitHub mirrors your local source of truth.
# Run from anywhere: bash tools/sync_from_local.sh
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$(cd "$REPO/.." && pwd)"   # the Video Accessibility folder

echo "Canonical source: $SRC"
echo "Plugin repo:      $REPO"
echo

copy() { if [ -e "$1" ]; then cp "$1" "$2" && echo "  synced $(basename "$1")"; else echo "  (skip, not found) $1"; fi; }

# Rules
copy "$SRC/Caption_Cleanup_Rules.md" "$REPO/rules/Caption_Cleanup_Rules.md"

# Template
copy "$SRC/HTML_Transcript_Template.md" "$REPO/templates/HTML_Transcript_Template.md"

# Pipeline package (includes pipeline/prompts)
if [ -d "$SRC/usf-caption-pipeline/pipeline" ]; then
  rsync -a --delete --exclude='__pycache__' --exclude='.venv' \
    "$SRC/usf-caption-pipeline/pipeline/" "$REPO/pipeline/"
  echo "  synced pipeline/"
fi

# Launchers
for f in "$SRC"/*.command; do [ -e "$f" ] && cp "$f" "$REPO/launchers/" && echo "  synced launcher $(basename "$f")"; done

echo
echo "Done. Review changes, then:  git -C \"$REPO\" add -A && git commit -m 'sync' && git push"
