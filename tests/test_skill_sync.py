"""Guard: every skills/<name>/ copy still matches the canonical repo root.

Cowork mounts only each skill's own subtree, so skills/<name>/pipeline/ and
skills/<name>/rules/ are copies of root-level sources rather than references to
them. Nothing in Python keeps a copy current, so a pipeline edit committed
without running tools/sync_to_skills.sh ships stale code to the plugin while
the repo's own tests go on passing against the root.

This compares the files directly instead of asking git, because it has to be
correct in a WORKING TREE, where an edit to the root and its freshly synced
copies are both legitimately uncommitted. `git diff --exit-code` would call
that drift. The complementary question -- "does running the sync change
anything the commit recorded?" -- belongs in CI, where a clean checkout makes
`git diff --exit-code` exactly right. There is no workflow in this repo yet;
CONTRIBUTING.md says what to add and why it is not here.

The mapping is derived, not restated: whatever a skill carries is compared
against the root original of the same name. A new skill folder is covered the
day it appears, with no edit here.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "skills"

# Root directories a skill may carry its own copy of.
COPIED = ("pipeline", "rules", "templates")
IGNORE_NAMES = {"__pycache__", ".venv", ".DS_Store"}
IGNORE_SUFFIX = (".pyc",)


def _relevant(path: Path) -> bool:
    if path.suffix in IGNORE_SUFFIX:
        return False
    return not any(part in IGNORE_NAMES for part in path.parts)


def _files_under(root: Path) -> set:
    if not root.is_dir():
        return set()
    return {p.relative_to(root) for p in root.rglob("*")
            if p.is_file() and _relevant(p.relative_to(root))}


def _stale_paths() -> list:
    """Every per-skill copy whose bytes differ from its root original.

    `pipeline` is compared as a whole tree: a skill runs the package, so a file
    missing from the copy or left behind in it is drift. `rules` and
    `templates` are compared per file, because a skill carries only the ones it
    needs -- caption-cleanup has no reason to hold the publish rules.
    """
    stale = []
    for skill in sorted(p for p in SKILLS.iterdir() if p.is_dir()):
        for name in COPIED:
            copy, origin = skill / name, REPO / name
            if not copy.is_dir():
                continue
            copied = _files_under(copy)
            if name == "pipeline":
                expected = _files_under(origin)
                for rel in sorted(expected - copied):
                    stale.append(f"{(copy / rel).relative_to(REPO)} — missing")
                for rel in sorted(copied - expected):
                    stale.append(f"{(copy / rel).relative_to(REPO)} — not in the root")
                copied &= expected
            for rel in sorted(copied):
                src = origin / rel
                if not src.is_file():
                    stale.append(f"{(copy / rel).relative_to(REPO)} — no root original")
                elif src.read_bytes() != (copy / rel).read_bytes():
                    stale.append(f"{(copy / rel).relative_to(REPO)} — differs from {name}/{rel}")
    return stale


def check_skill_copies_in_sync(check):
    stale = _stale_paths()
    if stale:
        print("  Per-skill copies are stale:")
        for line in stale:
            print(f"    {line}")
        print("  Fix with:  bash tools/sync_to_skills.sh")
    check("sync: per-skill copies match the repo root", not stale)


def check_hook_installed(check):
    """Not a failure: the hook is a local convenience and CI is the guarantee.

    A missing hook only means this machine syncs by hand, which is exactly the
    thing a new contributor would not know to do.
    """
    hook = REPO / ".git" / "hooks" / "pre-commit"
    if (REPO / ".git").is_dir() and not hook.exists():
        print("  Note: the pre-commit hook is not installed on this machine.")
        print("  It syncs the per-skill copies for you:  bash tools/install_hooks.sh")


# Standalone use: python3 tests/test_skill_sync.py
if __name__ == "__main__":
    failed = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failed.append(name)

    check_skill_copies_in_sync(check)
    check_hook_installed(check)
    print(f"\n{'ALL PASSED' if not failed else str(len(failed)) + ' FAILED'}")
    sys.exit(1 if failed else 0)
