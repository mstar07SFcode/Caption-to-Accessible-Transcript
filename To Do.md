# To Do

Running list for this repo. The earlier machine's own list, and the frozen
copy of its GUI that this rebuild was worked from, were removed once the
rebuild was done and running; they are still in history at b26da44.

## Standing preference — numeric sense over hyphenation

When two configurations trade off against each other, prefer the one that
reasons better about **numbers** over the one that gets **hyphenation** right.
A wrong figure in a tax lecture misleads; a missing hyphen in "fact-based"
reads slightly wrong and nothing more. Recorded 2026-10-26.

This already decides one open question — see "append vs replace" below.

## 2026-11-09 — Opened as PR #1, with one thing unverified

The desktop app, the plan-login reviewer and Windows support went up as PR #1
(`gui` into `main`: 22 commits, 32 files, +4,141/-62). Three concerns were
raised while checking whether the app would run on someone else's machine. Two
did not survive being looked at. They are written up here as settled so they do
not get raised a third time.

### Open — `4_Open_App.bat` has never run under `cmd.exe`

Written and reviewed on a Mac. The Windows-specific code it leans on is covered
by `tests/test_windows_launch.py`, and the file's own structure was checked,
but batch files fail in ways only `cmd.exe` shows. PR #1 asks a Windows tester
for one run and says what to report back.

- [ ] Get one full Windows run of `launchers\4_Open_App.bat`, start to finish

### Settled — `safe_filename` already handles backslashes

Raised as "it replaces `/` but not `\`, which is equally illegal on Windows".
It handles both. `_ILLEGAL_FILENAME_RE` is `[<>:"/\\|?*]` and strips the
backslash on the line after the `/` replacement:

    'Trusts \ Estates'  ->  'Trusts Estates.vtt'

The two are treated differently — `/` becomes " and ", `\` is dropped — but
both produce a legal Windows filename. Reading line 249 without line 250 is
what produced the false alarm. No change needed.

### Settled — `cmd_clean` does not redo finished work

Raised as "no skip-if-exists, so a re-run reprocesses every file in
`Raw_Captions`". There is indeed no such check, but archiving stands in for
one: `cmd_clean` calls `F.archive_source` per file as that file succeeds, so a
finished source leaves `Raw_Captions` and the next run never sees it. What
stays behind is what failed — which is exactly what should be re-run.

The one unprotected case is `--no-archive`, where nothing moves and a second
run does redo everything. That flag exists for trial runs, so this is arguably
correct. Worth knowing rather than fixing.

## 2026-10-26 — `.gitignore` has an uncommitted line

`_comparisons/` was added to `.gitignore` so the local comparison reports
(current-vs-new caption output) stay out of the branch. The line is still
uncommitted.

- [ ] Commit the `.gitignore` line, or delete `_comparisons/` and revert it

The folder holds `OPUS5_yours_vs_opus.txt`, `BATCH_current_vs_new.txt` and
`COMPARISON_yours_vs_run6.txt` — reading material only, nothing depends on them.

## 2026-10-26 — Measure `--append-system-prompt-file` against `--system-prompt-file`

**What.** `CAPTION_CLAUDE_SYSTEM_MODE` switches the reviewer between replacing
Claude Code's own system prompt with the cleanup rules (`replace`, the default)
and keeping the default prompt and adding the rules to it (`append`). The
caption-cleanup skill's sub-agents keep the default, so `append` is the closer
match to the process that produced the existing transcripts.

**Why it is still open.** One run each on Lecture 8A:

| mode | corrections | flags | entry 34 `fact-based` | entry 38 numeric flag |
|---|---|---|---|---|
| replace | 116 | 29 | missed | flagged **with the arithmetic** and proposed 27.5 million |
| append | 100 | 28 | correct | flagged, but only "Listen to verify" |

The 16-correction gap is inside the measured noise: three identical runs of one
config on this material spanned 61–95 corrections. So the totals decide nothing.

**Decision for now.** Keep `replace`, on the standing preference above —
it produced the better numeric flag; `append` won only on hyphenation.
Revisit when it can be measured properly.

**How to measure it properly.**

1. Build a regression set from the seven `Applied_FlagLog_*.txt` files in
   `Edited_Captions`. Those are corrections that were reviewed and applied, so
   they are human-approved ground truth — roughly 400 `entry / find / replace`
   triples across Lectures 1A–3C.
2. Score a build by the fraction of those triples it reproduces, not by how
   many corrections it makes. Totals have never distinguished a good run from
   a bad one; specific expected outcomes do.
3. Run at least three times per mode. A fix that lands once in three is a coin
   flip, not a fix — `fact-based` landed in one Opus run and not another, and
   `26/27` reproduced zero times after being presented as evidence.
4. Report numeric and citation checks separately from the rest, since those are
   the categories that matter most and the ones the rules were just written for.

- [ ] Build the regression set from the applied flag logs
- [ ] Score `replace` and `append`, three runs each
- [ ] Decide, and record the result here

## 2026-10-26 — Unverified by measurement

Landed in `72087f5` with sound reasoning but no isolated evidence, because four
changes went in together against a benchmark noisier than their effects:

- [ ] Rule 2d (citations) — entry 12 `642(h)` was already correct before the
      rule existed. Test it against `642(c)` on Lecture 6, which is where it
      actually failed.
- [ ] Pass-2 rule trimming (28,133 → 5,925 chars) — reasoning matches the
      earlier finding that naming specific rules narrowed attention, but this
      run cannot separate it from the other three changes.
