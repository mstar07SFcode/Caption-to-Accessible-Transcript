# Contributing

Setup is one command. It is safe to re-run.

```bash
bash tools/setup.sh          # add --gui if you will work on the desktop app
```

That creates `.venv`, installs the git hooks, and runs the tests so you know
the checkout is sound before you change anything.

## The one rule

**Edit `rules/`, `pipeline/` and `templates/` at the repo root. Never edit the
copies under `skills/`.**

Cowork mounts only each skill's own `skills/<name>/` subtree at runtime, so it
never sees root-level siblings. Each skill folder therefore carries its own
copy of what it needs, and all three skills run `python3 -m pipeline.batch`, so
each one needs the whole package. The copies are identical duplicates of the
root, not subsets.

You do not maintain them by hand. The pre-commit hook installed by `setup.sh`
runs `tools/sync_to_skills.sh` and stages the copies whenever a commit touches
a canonical source. If you ever want to run it yourself:

```bash
bash tools/sync_to_skills.sh
```

`skills/*/SKILL.md` is the exception — it is deliberately not copied anywhere.
Edit those in place.

## Tests

```bash
.venv/bin/python tests/test_pipeline.py
```

The pipeline and its tests are standard library only, so plain `python3` works
too. The suite includes a check that the per-skill copies match the root; when
it fails it names the stale files and the command that fixes them.

## What guards the copies

Two layers today, and neither is a hard gate:

- the drift check in the test suite, which compares the copies against the
  root byte for byte. It travels with the repo, so anyone who runs the tests
  sees a stale copy named.
- `tools/pre-commit`, which syncs and stages the copies for you. It is
  per-machine, `git commit --no-verify` skips it, and a fresh clone has none
  until you run setup.

So someone who skips setup and never runs the tests can still commit a stale
copy. CI is the fix for that, and it is deliberately not in this repo yet:
pushing any file under `.github/workflows/` needs a token carrying the
`workflow` scope (classic) or Workflows write permission (fine-grained), which
the project does not currently have. Once it does, add a workflow with two
jobs -- the test suite on Python 3.9 (the floor this project supports) and
3.13, and a generated-files job that runs `bash tools/sync_to_skills.sh
--quiet` and then `git diff --exit-code`. That second job is exact only in a
clean checkout, which is why it belongs in CI rather than in the local test.

## Releasing

Bump `version` in `.claude-plugin/plugin.json` when a change alters what an
installed copy does. Plugins are pulled at install time, so users get a change
when they re-install or update, not immediately.
