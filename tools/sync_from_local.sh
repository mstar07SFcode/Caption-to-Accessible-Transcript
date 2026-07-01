#!/bin/bash
# Sync canonical local sources INTO this plugin repo before committing/pushing.
#
# Canonical lives in your local Core_Workflow folder (the repo's parent):
#   - Caption_Cleanup_Rules.md           (editing rules)
#   - usf-caption-pipeline/pipeline/      (pipeline package incl. prompts)
#   - HTML_Transcript_Template.md         (HTML template)
#
# This copies them into the repo so GitHub mirrors your local source of truth.
# Run from anywhere: bash tools/sync_from_local.sh
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$(cd "$REPO/.." && pwd)"   # the Core_Workflow folder

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

# --- Nested copies for Cowork's sandboxed plugin mount ---
# Cowork only mounts each plugin's skills/ subtree, not root-level siblings
# like rules/ or pipeline/. Each skill folder below therefore carries its own
# copy of whatever it needs, kept in sync from the same canonical sources.

# caption-cleanup needs the rules file + the pipeline package
copy "$SRC/Caption_Cleanup_Rules.md" "$REPO/skills/caption-cleanup/rules/Caption_Cleanup_Rules.md"
if [ -d "$SRC/usf-caption-pipeline/pipeline" ]; then
  rsync -a --delete --exclude='__pycache__' --exclude='.venv' \
    "$SRC/usf-caption-pipeline/pipeline/" "$REPO/skills/caption-cleanup/pipeline/"
  echo "  synced skills/caption-cleanup/pipeline/"
fi

# flaglog-apply and transcript-publish only need the pipeline package
for skill in flaglog-apply transcript-publish; do
  if [ -d "$SRC/usf-caption-pipeline/pipeline" ]; then
    rsync -a --delete --exclude='__pycache__' --exclude='.venv' \
      "$SRC/usf-caption-pipeline/pipeline/" "$REPO/skills/$skill/pipeline/"
    echo "  synced skills/$skill/pipeline/"
  fi
done

echo
echo "Done. Review changes, then:  git -C \"$REPO\" add -A && git commit -m 'sync' && git push"
