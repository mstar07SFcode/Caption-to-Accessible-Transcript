# Deferred work

Known issues and improvements that are understood but not yet built. Each
entry records enough to pick the work up cold — what's wrong, what it costs,
and which decisions are still open.

---

## docx publish: `humanize_title()` is unwired, and nothing is tested

**Raised:** 2026-10-04 · **Status:** feature shipped and wired into Step 3,
two gaps open
**Location:** `pipeline/docx_publish.py`, `cmd_publish` in `pipeline/batch.py`,
`pipeline/naming.py`

**Fixed 2026-10-04:**

- The undeclared `python-docx` dependency. `requirements.txt` now declares it,
  and `cmd_publish` checks for it before the judgment phase instead of
  crashing in Phase 3 with a paid batch already spent.
- Launcher access. `3_Publish_Transcripts.command` now offers
  `[1] Web page (.html) / [2] Word (.docx)` and writes Word output to its own
  `Word_Transcripts` folder. The interpreter question that was open here
  answered itself: the prompt sits *after* the Basic/AI choice, so `$RUNPY` is
  already known, and the launcher offers to `pip install python-docx` into
  that exact interpreter — declining falls back to HTML. Nothing was added to
  `0_Setup_AI_Cleanup.command`, which has no use for the library.
- Doubled filename prefix. `Transcript_Transcript…docx` — `title_from_stem()`
  already begins with "Transcript ". Naming now lives in
  `naming.transcript_docx_name()`, beside its HTML sibling.

`--title-map` and `--speaker-map` remain CLI-only, deliberately: they are
batch-level JSON files with no sensible double-click prompt.

### 1. `humanize_title()` is dead code

**Deliberately deferred 2026-10-04** — the titles `title_from_stem()` produces
were judged good enough in practice. Keep this entry for whoever wants better
ones later; there is no need to act on it otherwise.

`naming.humanize_title()` was written to run on the **original source
filename**, before any CamelCasing, so it can recover real word and clause
boundaries. Nothing calls it.

`cmd_publish` derives the docx title from `title_from_stem(j["stem"])`
instead — the already-CamelCased working stem, which has thrown those
boundaries away. The reader-facing title the helper exists to produce never
reaches a document, and the only way to get a good one today is to hand-write
a `--title-map` JSON.

Wiring it is not a one-liner, because **the original filename is gone by
publish time**: the VTT header carries only `Speaker:`, `Course:` and
`Cleaned:` (`pipeline/vtt.py`), and the original sits in `Archived_Captions`
under a name the working stem no longer maps back to.

| Option | Trade-off |
|---|---|
| Add `Source:` to the VTT header at clean time | Smallest change and survives archiving; needs `strip_header` taught to drop it, and does nothing for VTTs cleaned before the change. |
| Look the original up in `Archived_Captions` by stem | No format change, but publish grows a dependency on the archive still existing — and `--delete-working` empties it. |
| Leave it to `--title-map` | Zero code; every batch then needs a hand-written JSON, which is the work the helper was meant to remove. |

### 2. No test coverage

`tests/` has nothing for `docx_publish.py` or for the `naming.py` helpers the
docx work added (`humanize_title`, `camelize_title`, `safe_filename`,
`transcript_docx_name`) — and `tests/` is not mirrored to the skill copies
either (see *Skill mirrors are not diff-checked* below).

`transcript_docx_name` is the one worth covering first: it already had the
doubled-prefix bug above, and it has a real edge case a careless fix would
reintroduce — a title like "Transcripts of the Board Meeting" must *not* be
stripped to "sOfTheBoardMeeting". `humanize_title` is likewise pure string
logic with documented edge cases (the three underscore patterns,
`_MINOR_WORDS`, `_COMPOUND_FIXES`), cheap to cover whenever §1 is picked up.

There is also no test that the docx path produces real Heading 1/Heading 2
styles rather than bold paragraphs — which is the whole accessibility point of
publishing to Word, and is invisible to a filename check.

---

## `_run_batch` has no timeout, no cancel, and no progress hook

**Raised:** 2026-08-25 · **Status:** deferred, nothing implemented
**Location:** `pipeline/api_backend.py`, `APIBackend._run_batch`

### The problem

The Message Batch poll loop is unbounded:

```python
while True:
    b = self._client.messages.batches.retrieve(batch.id)
    if getattr(b, "processing_status", None) == "ended":
        break
    print(f"  ...{label} batch processing ({elapsed}s elapsed)")
    time.sleep(self.poll_interval)
```

Three gaps, in order of severity:

1. **No maximum wait.** If a batch stalls server-side the loop spins forever.
   On the CLI you can Ctrl-C. A GUI wrapping this hangs with no way out.
2. **No cancellation.** A max wait bounds the hang but does *not* give a GUI a
   working cancel button — that needs the loop to check a predicate on each
   poll and bail early. Worth doing in the same change; it is a few lines once
   the loop is already being touched.
3. **Progress is hardcoded to `print`.** A GUI has nowhere to route status, and
   `print` to a detached stdout is invisible.

### Shape of the fix

Add to `APIBackend.__init__` (all optional, so CLI behavior is unchanged):
`max_wait`, `should_cancel`, `progress`.

### Open decisions

These need answering before implementing — they change behavior, not just
structure.

**1. What happens when max wait is exceeded?**

| Option | Trade-off |
|---|---|
| Raise `APIBackendError` naming the batch id | Batch keeps running; results stay retrievable for ~29 days, so spend isn't wasted. Caller decides. |
| Cancel the batch, then raise | Stops further spend immediately, but discards per-file results that had already succeeded. |
| Return partial results | Never blocks the pipeline, but silently yields an incomplete transcript with no clear signal that files were skipped. |

**2. Early cancellation — include a `should_cancel` predicate, or timeout only?**
Without it, a GUI user waits out the full timeout rather than stopping a batch
they know is wrong.

**3. Progress callback shape.**
`progress(message, info)` — where `info` carries `elapsed`, `batch_id`,
`status` — keeps the default a plain print for the CLI while letting a GUI
drive a real progress bar. The simpler `progress(message)` forces a GUI to
regex values back out of a formatted sentence.

### Notes for whoever picks this up

- `poll_interval` already exists as a constructor arg (default 15s) and
  `tests/test_api_backend.py` constructs with `poll_interval=0`, so the test
  fake is already set up for fast loop testing.
- `_run_batch` is called by both `cleanup_batch` and `publish_batch`; a GUI
  calls those, not `_run_batch` directly, so the constructor is the practical
  injection point.
- Whatever is chosen, a timeout path needs a test that does not actually sleep.

---

## Skill mirrors are not diff-checked

**Raised:** 2026-08-25 · **Status:** deferred, low priority

`tools/sync_to_skills.sh` fans `rules/`, `pipeline/` and `templates/` out to the
per-skill copies, but nothing verifies they match afterward. A mirror edited
directly, or a sync that is forgotten before committing, drifts silently — and
`tests/` is not mirrored at all, so no test would catch it.

A `git diff --no-index` check between root and each mirror, run in CI or as a
pre-commit step, would close this. Note that `skills/*/SKILL.md` is
deliberately *not* synced and must be excluded from any such check.
