# Deferred work

Known issues and improvements that are understood but not yet built. Each
entry records enough to pick the work up cold — what's wrong, what it costs,
and which decisions are still open.

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
