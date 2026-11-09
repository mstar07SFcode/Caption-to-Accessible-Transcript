"""Guard: every skills/<name>/ copy still matches the canonical repo root.

Cowork mounts only each skill's own subtree, so skills/<name>/pipeline/ and
skills/<name>/rules/ are copies of root-level sources rather than references to
them. Nothing in Python keeps a copy current, so a pipeline edit committed
without running tools/sync_to_skills.sh ships stale code to the plugin while
the repo's own tests go on passing against the root.

This test closes that gap: it runs the sync script in --check mode, which
compares and changes nothing. The script is the single implementation of what
"in sync" means -- the pre-commit hook from tools/install_hooks.sh runs the
same script in its copying mode.
"""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools" / "sync_to_skills.sh"


def check_skill_copies_in_sync(check):
    if not SCRIPT.is_file():
        check("sync: script present", False)
        return

    proc = subprocess.run(["bash", str(SCRIPT), "--check"],
                          capture_output=True, text=True, cwd=str(REPO))

    if proc.returncode != 0:
        # Print the script's own itemized report: it names each stale path and
        # the one command that fixes them.
        sys.stdout.write(proc.stdout)
        if proc.stderr.strip():
            sys.stdout.write(proc.stderr)
    check("sync: per-skill copies match the repo root", proc.returncode == 0)


# Standalone use: python3 tests/test_skill_sync.py
if __name__ == "__main__":
    failed = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failed.append(name)

    check_skill_copies_in_sync(check)
    print(f"\n{'ALL PASSED' if not failed else str(len(failed)) + ' FAILED'}")
    sys.exit(1 if failed else 0)
