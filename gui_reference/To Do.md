# To Do

## 2026-10-04 — Push the `--help` fix to the installed Claude plugin

**What:** `python3 -m pipeline.batch clean --help` crashed (`TypeError: %c requires int or char`).
Cause: the `--batch` help text said `50% cheaper`; argparse read `% c` as a format code.
Fixed locally by changing it to `50%% cheaper` in all 5 copies of `batch.py`:

- [x] `pipeline/batch.py`
- [x] `skills/caption-cleanup/pipeline/batch.py`
- [x] `skills/flaglog-apply/pipeline/batch.py`
- [x] `skills/transcript-publish/pipeline/batch.py`
- [x] `caption-app-update/pipeline/batch.py`

**Update 2026-10-04 — GitHub already has the fix.** Checked GitHub (main branch):
`plugin.json` is version 0.1.1 and all 4 `batch.py` copies already use `50%%`.
The fix was made from the other machine, so steps 1–2 below are done.

- [x] 1. Version bumped to 0.1.1 on GitHub (done from other machine)
- [x] 2. Fixed `batch.py` files are on GitHub (done from other machine)
- [ ] 3. In the Claude app, update the plugin from its marketplace
      (Settings → plugins / marketplace → update or sync). The installed plugin is
      still 0.1.0. Uninstall + reinstall only if the update doesn't show up.
- [ ] 4. Test: start a new task and run `python3 -m pipeline.batch clean --help` in the
      plugin's caption-cleanup folder — it should print the help screen, not crash.
- [ ] 5. Refresh this Mac's copy: download a fresh copy of the repo from GitHub
      to replace this folder (keep this To Do.md).

> ⚠️ **Do NOT upload files from this Mac's folder to GitHub.** This copy is OLDER than
> GitHub (the code has been reorganized since) — uploading would overwrite newer work.

## 2026-10-04 — Added "My Claude plan (no key)" AI option to the local app (for demo)

- New: `pipeline/claude_cli_backend.py` (runs `claude -p`, no tools, no API key)
- Edited: `pipeline/batch.py` (`--backend claude`), `gui/app.py`, `gui/runner.py`,
  `gui/index.html` (AI-engine selector + Claude sign-in pill), `README.md`
- Backups of the edited files are in `_backup_before_demo/`
- Root `pipeline/` only. The skills/ copies were NOT synced (the plugin is unchanged)
- [ ] After the demo: merge this local app (gui/, structure.py, Claude-plan backend,
      INSTALL.md, docs/) with the newer GitHub version, then push
- [x] Ported GitHub's Aug 25 fix: Publish only empties Archived_Captions when
      "Clear the working files" is ticked, and only after outputs are written

## 2026-10-04 — Side-by-side review window (Step 2)

- New: `gui/review.py`, `gui/review.html`; edited `gui/app.py`, `gui/main.py`, `gui/runner.py`, `gui/index.html`
- Step 2 now lists every automatic fix and has an "Open review window" button
- Review window: captions on the left, changes on the right, click to jump, Undo for auto-fixes,
  flag edits save automatically. Undo marks the flag-log line "(undone by reviewer)"
- Backup of the version before this feature: `_backup_demo_v1_working/`
- [ ] Later idea: play the video at a flagged timecode ("listen to verify")
- Follow-up (same night): removed the Re-check button (sign-in is re-checked automatically);
  a flag's "Replace with" box holds only the AI's suggested wording; when there is none it is
  empty with a light "Listen to verify" placeholder (never saved as text); clicking the original
  caption copies it into the box.
  Apply skips flags left unchanged ("left as is"). Files: pipeline/flaglog.py, pipeline/apply.py,
  gui/runner.py, gui/review.py, gui/app.py, gui/index.html, gui/review.html
- Review window v2: flag log on the LEFT, captions on the RIGHT. No Ignore button. Each flag has one
  "Apply this change" button that edits that entry in the VTT immediately, records it in the flag log
  as "✎ ... — Reviewer: edited" (undoable), and pushes a refresh to the main window.
  Backup of the version before this: `_backup_demo_v2_review/`
- Fix (MSA 6 respiratory): AI logged no-change "fixes" and both fixed AND flagged entries 64/67/71.
  App now hides no-change fixes; flags on already-fixed lines are dropped if the suggestion is already
  in the caption, otherwise re-pointed at the current caption text (review.normalize_flags, also run
  before bulk Apply). pipeline/apply.py guards new runs; corrections.md rules 11-12 added.
- Added Rule 2b (discourse fillers kept + set off with commas) and a "don't flag doubled words"
  example to rules/Caption_Cleanup_Rules.md; matching lines in pipeline/prompts/corrections.md (7, 8).
  App copy only - [ ] carry into the GitHub rules/plugin during the merge.
- Fix (api_backend.py line 48 crash = the AI's reply was not valid JSON): the Claude-plan backend now
  passes --json-schema so Claude Code returns validated JSON; retries once if a reply is unreadable;
  saves a bad reply to ~/.config/caption-to-transcript/last_ai_reply.txt; clear error message instead
  of a crash. Verified with a real run on the respiratory file (9 fixes, 2 flags, entry 42 -> "pressure, right,").
- Added Rule 2c (numbers: fix broken numbers like "seven, 57" -> 757 when nearby lines confirm; flag
  when only suggested; flag numbers that break the math, on the right entry). Suggestions that just
  repeat the line are treated as no suggestion (app + AI instructions). [ ] carry into GitHub rules.
- Comma rule: an entry ending with a comma -> next entry starts lowercase (unless proper noun / "I").
  In rules + AI instructions, plus an automatic safety check in pipeline/apply.py (_lowercase_after_comma,
  common-word list only; logged as an undoable correction). [ ] carry into GitHub rules/pipeline.
- Removed the "keep" checkbox from Step 2 (empty box = no change).
- Review window: click any caption line to edit it (Save / Cancel, Cmd/Ctrl+Enter, Esc);
  "Insert [unintelligible]" button at the cursor (caption edit box + flag boxes);
  Find & Replace bar (match case, whole words, live preview, Replace all with confirm click;
  each changed line logged as its own undoable reviewer edit). Backup: `_backup_demo_v3_before_edit/`
  [ ] Merge note: GitHub's clean.py normalises [unintelligible] spacing (Rule 1d/3a) - bring over.
- Word output: Step 3 has "Transcript format" checkboxes (Web page .html / Word .docx, either or both).
  Word files go to Word_Transcripts/ (created automatically); click a .docx in the list to open it.
  New pipeline/docx_publish.py (adapted from GitHub's, same structure/text fixes as the HTML; real
  headings, 12pt minimum, document title property). CLI: publish --format html|docx|both --docx DIR.
  python-docx added to requirements-gui.txt; 4_Open_App installs it on next launch (needs internet once).
  Backup before this: `_backup_demo_v4_before_docx/`
