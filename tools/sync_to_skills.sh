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
#   bash tools/sync_to_skills.sh           copy root -> the per-skill copies
#   bash tools/sync_to_skills.sh --check   report drift and change nothing;
#                                          exits 0 in sync, 1 when stale
#
# Run this after editing anything under rules/, pipeline/, or templates/ at
# the repo root, before committing. The pre-commit hook installed by
# tools/install_hooks.sh does it for you; tests/test_skill_sync.py runs
# --check so a stale copy fails the suite.
#
# Run from anywhere: bash tools/sync_to_skills.sh
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"

MODE=sync
QUIET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE=check ;;
    --quiet) QUIET=1 ;;
    *)       echo "usage: $(basename "$0") [--check] [--quiet]" >&2; exit 2 ;;
  esac
  shift
done

STALE=0
EXCLUDES=(--exclude='__pycache__' --exclude='.venv' --exclude='.DS_Store'
          --exclude='*.pyc')

# copy <src-file> <dst-file>
copy() {
  local src="$1" dst="$2"
  if [ ! -e "$src" ]; then echo "  (skip, not found) $src"; return 0; fi
  if [ "$MODE" = check ]; then
    if ! cmp -s "$src" "$dst"; then
      echo "  STALE  ${dst#$REPO/}"
      STALE=1
    fi
  else
    cp "$src" "$dst"
    echo "  synced $(basename "$src") -> ${dst#$REPO/}"
  fi
}

# tree <src-dir-with-trailing-slash> <dst-dir-with-trailing-slash>
tree() {
  local src="$1" dst="$2" out
  if [ "$MODE" = check ]; then
    # --dry-run prints one itemized line per file that WOULD change, so empty
    # output is the definition of "in sync". A missing destination counts.
    out="$(rsync -a --delete --dry-run --itemize-changes "${EXCLUDES[@]}" \
           "$src" "$dst" 2>/dev/null || echo '?? destination unreadable')"
    if [ -n "$out" ]; then
      echo "  STALE  ${dst#$REPO/}"
      echo "$out" | sed 's/^/           /'
      STALE=1
    fi
  else
    mkdir -p "$dst"
    rsync -a --delete "${EXCLUDES[@]}" "$src" "$dst"
    echo "  synced ${dst#$REPO/}"
  fi
}

if [ "$QUIET" -eq 0 ]; then
  if [ "$MODE" = check ]; then
    echo "Checking per-skill copies against the repo root: $REPO"
  else
    echo "Plugin repo (canonical): $REPO"
  fi
  echo
fi

# caption-cleanup needs the cleanup rules file + the pipeline package
copy "$REPO/rules/Caption_Cleanup_Rules.md" \
     "$REPO/skills/caption-cleanup/rules/Caption_Cleanup_Rules.md"
tree "$REPO/pipeline/" "$REPO/skills/caption-cleanup/pipeline/"

# transcript-publish needs the publish rules file + the pipeline package
[ "$MODE" = check ] || mkdir -p "$REPO/skills/transcript-publish/rules"
copy "$REPO/rules/Transcript_Publish_Rules.md" \
     "$REPO/skills/transcript-publish/rules/Transcript_Publish_Rules.md"
tree "$REPO/pipeline/" "$REPO/skills/transcript-publish/pipeline/"

# flaglog-apply only needs the pipeline package (no API rules lookups)
tree "$REPO/pipeline/" "$REPO/skills/flaglog-apply/pipeline/"

if [ "$MODE" = check ]; then
  if [ "$STALE" -ne 0 ]; then
    [ "$QUIET" -eq 0 ] && echo && \
      echo "Per-skill copies are STALE. Fix with:  bash tools/sync_to_skills.sh"
    exit 1
  fi
  [ "$QUIET" -eq 0 ] && echo && echo "In sync."
  exit 0
fi

# The footer is for a human running this by hand. The pre-commit hook passes
# --quiet, because inside a commit "now commit and push" is nonsense.
if [ "$QUIET" -eq 0 ]; then
  echo
  echo "Done. Review changes, then:  git -C \"$REPO\" add -A && git commit -m 'sync' && git push"
fi
