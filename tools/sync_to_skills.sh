#!/bin/bash
# Fan out this repo's own root-level sources into each skill's nested copy.
#
# This repo IS the canonical source (edit files at the repo root: rules/,
# pipeline/, templates/). But Cowork only mounts each plugin skill's own
# skills/<name>/ subtree at runtime -- it never sees root-level siblings like
# rules/ or pipeline/. So each skill folder keeps its own copy of whatever it
# needs, and this script keeps those copies in sync with the root originals.
#
# Run this after editing anything under rules/, pipeline/, or templates/ at
# the repo root, before committing.
#
# Run from anywhere: bash tools/sync_to_skills.sh
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"

echo "Plugin repo (canonical): $REPO"
echo

copy() { if [ -e "$1" ]; then cp "$1" "$2" && echo "  synced $(basename "$1") -> $2"; else echo "  (skip, not found) $1"; fi; }

# caption-cleanup needs the cleanup rules file + the pipeline package
copy "$REPO/rules/Caption_Cleanup_Rules.md" "$REPO/skills/caption-cleanup/rules/Caption_Cleanup_Rules.md"
rsync -a --delete --exclude='__pycache__' --exclude='.venv' --exclude='.DS_Store' \
  "$REPO/pipeline/" "$REPO/skills/caption-cleanup/pipeline/"
echo "  synced skills/caption-cleanup/pipeline/"

# transcript-publish needs the publish rules file + the pipeline package
mkdir -p "$REPO/skills/transcript-publish/rules"
copy "$REPO/rules/Transcript_Publish_Rules.md" "$REPO/skills/transcript-publish/rules/Transcript_Publish_Rules.md"
rsync -a --delete --exclude='__pycache__' --exclude='.venv' --exclude='.DS_Store' \
  "$REPO/pipeline/" "$REPO/skills/transcript-publish/pipeline/"
echo "  synced skills/transcript-publish/pipeline/"

# flaglog-apply only needs the pipeline package (no API rules lookups)
rsync -a --delete --exclude='__pycache__' --exclude='.venv' --exclude='.DS_Store' \
  "$REPO/pipeline/" "$REPO/skills/flaglog-apply/pipeline/"
echo "  synced skills/flaglog-apply/pipeline/"

echo
echo "Done. Review changes, then:  git -C \"$REPO\" add -A && git commit -m 'sync' && git push"
