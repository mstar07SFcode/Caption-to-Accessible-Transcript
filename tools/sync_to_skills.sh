#!/bin/bash
# Fan out this repo's own root-level sources into each skill's nested copy.
#
# This repo IS the canonical source (edit files at the repo root: rules/,
# pipeline/, templates/). But Cowork only mounts each plugin skill's own
# skills/<name>/ subtree at runtime -- it never sees root-level siblings like
# rules/ or pipeline/. So each skill folder keeps its own copy of whatever it
# needs, and this script keeps those copies in sync with the root originals.
#
# Usage:
#   bash tools/sync_to_skills.sh            copy root -> the per-skill copies
#   bash tools/sync_to_skills.sh --quiet    same, without the banner/footer
#
# Run it after editing anything under rules/, pipeline/, or templates/ at the
# repo root, before committing. You should rarely need to: the pre-commit hook
# from tools/install_hooks.sh runs it for you.
#
# This script only COPIES. Checking is deliberately elsewhere:
#   * tests/test_skill_sync.py -- "do the copies match the root right now?",
#     correct in a working tree with uncommitted edits.
#   * In CI, once there is a workflow: run this script and then
#     `git diff --exit-code`, the standard way to verify generated files, which
#     is exact there because the checkout is clean. See CONTRIBUTING.md.
#
# Run from anywhere: bash tools/sync_to_skills.sh
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

say() { [ "$QUIET" -eq 0 ] && echo "$@"; return 0; }

EXCLUDES=(--exclude='__pycache__' --exclude='.venv' --exclude='.DS_Store'
          --exclude='*.pyc')

copy() {  # copy <src-file> <dst-file>
  if [ ! -e "$1" ]; then say "  (skip, not found) $1"; return 0; fi
  cp "$1" "$2"
  say "  synced $(basename "$1") -> ${2#$REPO/}"
}

tree() {  # tree <src-dir/> <dst-dir/>
  mkdir -p "$2"
  rsync -a --delete "${EXCLUDES[@]}" "$1" "$2"
  say "  synced ${2#$REPO/}"
}

say "Plugin repo (canonical): $REPO"
say

# caption-cleanup needs the cleanup rules file + the pipeline package
copy "$REPO/rules/Caption_Cleanup_Rules.md" \
     "$REPO/skills/caption-cleanup/rules/Caption_Cleanup_Rules.md"
tree "$REPO/pipeline/" "$REPO/skills/caption-cleanup/pipeline/"

# transcript-publish needs the publish rules file + the pipeline package
mkdir -p "$REPO/skills/transcript-publish/rules"
copy "$REPO/rules/Transcript_Publish_Rules.md" \
     "$REPO/skills/transcript-publish/rules/Transcript_Publish_Rules.md"
tree "$REPO/pipeline/" "$REPO/skills/transcript-publish/pipeline/"

# flaglog-apply only needs the pipeline package (no API rules lookups)
tree "$REPO/pipeline/" "$REPO/skills/flaglog-apply/pipeline/"

say
say "Done. Review changes, then:  git -C \"$REPO\" add -A && git commit -m 'sync' && git push"
