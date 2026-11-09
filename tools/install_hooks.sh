#!/bin/bash
# Install this repo's git hooks. Run once per clone, on each machine you
# develop on -- git never versions .git/hooks, so a fresh clone has none.
#
#   bash tools/install_hooks.sh
#
# What it installs: a pre-commit hook that runs tools/sync_to_skills.sh and
# stages the per-skill copies whenever a commit touches rules/, pipeline/ or
# templates/. The installed file is only a shim that execs tools/pre-commit,
# which IS versioned -- so changing the hook's behavior later needs no
# reinstall.
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
HOOK_DIR="$(cd "$REPO" && git rev-parse --git-path hooks)"
HOOK_DIR="$(cd "$REPO" && cd "$HOOK_DIR" && pwd)"
TARGET="$HOOK_DIR/pre-commit"

if [ -e "$TARGET" ] && ! grep -q "tools/pre-commit" "$TARGET" 2>/dev/null; then
  cp "$TARGET" "$TARGET.backup"
  echo "Existing pre-commit hook backed up to: $TARGET.backup"
fi

cat > "$TARGET" <<'SHIM'
#!/bin/bash
# Installed by tools/install_hooks.sh. The logic lives in the versioned
# tools/pre-commit, so this shim never needs reinstalling.
exec bash "$(git rev-parse --show-toplevel)/tools/pre-commit" "$@"
SHIM
chmod +x "$TARGET"
chmod +x "$REPO/tools/pre-commit" 2>/dev/null || true

echo "Installed pre-commit hook -> $TARGET"
echo "It runs tools/pre-commit (versioned). Skip it once with: git commit --no-verify"
