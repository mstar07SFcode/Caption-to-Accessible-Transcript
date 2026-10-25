# GUI Handoff: rebuilding the Caption Transcripts desktop app

Written 2026-10-24 from the local (older) copy of this repo on the Mac. Source of truth for the
code described here: `gui/`, plus the demo-era additions in `pipeline/`. A snapshot of the state
just before Word output was added is in `_backup_demo_v4_before_docx/`.

## How to use this document (instructions for the Claude doing the rebuild)

1. **Do not overwrite existing files** in the target repo's `pipeline/`, `skills/`, `rules/`,
   `tools/` or `.claude-plugin/`. That repo is newer than this one. Work on a new git branch.
2. Build the GUI in a new `gui/` folder. Copy this machine's `gui/`, `pipeline/claude_cli_backend.py`,
   `pipeline/docx_publish.py`, `launchers/4_Open_App.command` and `requirements-gui.txt` into a
   scratch folder (e.g. `gui_reference/`) and treat them as reference, not as drop-in files.
3. This repo's pipeline was reorganized since the reference copy. Before wiring anything, read the
   target repo's `pipeline/` and map each function listed in "Pipeline hook points" below to its
   current name and signature. The glue code (`gui/runner.py`) is the part that will change most.
4. If the target repo already has `pipeline/core.py` (the architecture doc planned it), have
   `runner.py` call that instead of the argparse-Namespace shim.
5. Ask before changing any existing pipeline file. The only additions the GUI truly needs are
   listed under "Pipeline additions".

## What the app is

A local desktop window (FastAPI server on 127.0.0.1 + a pywebview window, falling back to the default
browser) that wraps the existing three-step caption pipeline. **The GUI contains no pipeline
logic.** Every route delegates to `gui/runner.py`, which calls the same functions the CLI uses, on
a worker thread.

The user picks a **working folder** containing these subfolders (created automatically):
`Raw_Captions`, `Edited_Captions`, `Archived_Captions`, `VTT_Files`, `HTML_Transcripts`,
`Word_Transcripts`.

## Files and what each does

| File | Role |
|---|---|
| `gui/main.py` | Entry (`python -m gui.main`). Picks a free port, starts uvicorn in a thread, waits for it, opens a pywebview window (1000x820). `JsApi` exposes `pick_folder()` (native folder dialog) and `open_review(flaglog_name)` (opens a second window at `/review?file=...`). Pushes a refresh to the main window when the review window changes data. |
| `gui/app.py` | FastAPI routes (below). Stores the working folder in `~/.config/caption-to-transcript/config` as `WORKING_FOLDER=...`, the same file the shell launchers use. |
| `gui/runner.py` | `JobManager` (runs a function on a thread, redirects stdout into a line list the UI polls), `run_clean`, `run_apply_flaglog`, `run_publish`, `folder_status`, flag-log read/write helpers. Builds the `argparse.Namespace` the CLI functions expect. Translates `SystemExit` from a bad backend into a friendly error. |
| `gui/review.py` | Logic for the review window: load a flag log + its VTT, undo an automatic fix, apply a flag, edit a caption line, find/replace, and `normalize_flags`. |
| `gui/keystore.py` | API key storage: OS keychain via `keyring`, else `ANTHROPIC_API_KEY` env, else memory only. Never writes the key to a file. |
| `gui/index.html` | Main window, single page, vanilla JS, no framework. |
| `gui/review.html` | Review window, single page, vanilla JS. |

## Main window (`index.html`)

Header: title, working-folder label, **AI engine** dropdown (My Claude plan (no key) / Anthropic API key),
a **Claude sign-in pill** (re-checked automatically until signed in; there is no Re-check button),
an **API key** pill + toggle button, **Change folder**. A collapsible API-key panel (password field,
"remember on this Mac" checkbox, Save / Test / Forget).

- **Step 1, Clean captions:** file counts, Course and Speaker text fields, "Use AI" checkbox,
  optional batch checkbox (API engine only, 50% cheaper), Run button, live log `<pre>`.
- **Step 2, Review changes:** lists every automatic fix and every flag per file. Each flag shows the
  original caption (click it to copy into the box) and a "Replace with" box that holds only the AI's
  suggested wording. When there is no suggestion the box is empty with a light "Listen to verify"
  placeholder, and that placeholder is never saved as text. There is no "keep" checkbox: an empty/unchanged
  box means no change. Buttons: **Open review window**, Save changes, **Apply corrections** (bulk).
- **Step 3, Publish transcripts:** "Transcript format" checkboxes (Web page `.html`, Word `.docx`, either
  or both), "AI headings" checkbox, "Clear the working files" checkbox, Publish button, log, and a list
  of produced files (click a `.docx` to open it via `/api/open`; HTML opens in a new tab).

Long jobs: POST starts a job and returns `{id, ...}`; the page polls `GET /api/job/{id}` until
`status` is `done` or `error`, appending `lines` to the log. Only one job runs at a time (409 otherwise).

## Review window (`review.html`)

Opened from Step 2 in a second pywebview window. Layout: **flag log on the LEFT, captions on the RIGHT.**
Toolbar: All lines / Changed lines only, filter All / Fixes / Flagged, a save-state live region.

- Left cards: each automatic fix has an **Undo** (two-click confirm; reverses the replacement inside that
  one entry; the log line becomes "(undone by reviewer)"). Each flag has an editable "Replace with" box,
  a button that inserts `[unintelligible]` at the cursor, and one **Apply this change** button that
  edits that entry in the VTT immediately and records it in the flag log as `✎ Entry N ... — Reviewer: edited`
  (itself undoable). No Ignore button. Clicking a card jumps to the caption line.
- Right: every caption line. Click a line to edit it (Save / Cancel, Cmd/Ctrl+Enter, Esc), with an
  Insert `[unintelligible]` button.
- **Find & Replace bar:** match case, whole words (default on), live match count/preview list,
  Replace all with a click-to-confirm; each changed line becomes its own undoable reviewer edit.
- Accessibility is deliberate: `aria-pressed` toggles, `role="search"`, `aria-live` status regions.
- After any change the review window tells the main window to refresh its Step 2 list.

## HTTP API (all JSON unless noted)

| Route | Purpose |
|---|---|
| `GET /` | serves `index.html` |
| `GET /api/state` | working folder, folder counts, key state (`can_remember`), Claude sign-in status |
| `POST /api/claude/check` | force a Claude sign-in re-check |
| `POST /api/folder` `{path}` | set working folder |
| `POST /api/key`, `/api/key/test`, `/api/key/forget` | API key management |
| `POST /api/clean` | start Step 1 (course, speaker, use_ai, use_batch, engine) |
| `GET/POST /api/flags` | read all pending flag logs as editable entries / save edits |
| `POST /api/apply` | bulk apply (normalizes flags first, then runs apply) |
| `POST /api/publish` | start Step 3 (html, docx, ai_headings, delete_working, use_batch, engine); rejects if neither format is ticked or python-docx is missing |
| `GET /api/job/{id}` | poll a job |
| `GET /api/transcripts` | list published html/docx |
| `GET /api/transcript/{name}` | serve an HTML transcript |
| `POST /api/open` | open a file/folder in Finder |
| `GET /review?file=` | serves `review.html` |
| `GET /api/review?file=` | review data (captions, corrections, flags) |
| `POST /api/review/undo`, `/edit`, `/find`, `/replace`, `/apply` | review actions |

## Pipeline hook points (names in the reference copy; verify against the target repo)

- `pipeline.batch.cmd_clean(Namespace)`: fields `raw, out, archive, course, speaker, backend ("stub"|"api"|"claude"), model, batch, batch_timeout, judgment_dir, emit_prompts, no_archive`.
- `pipeline.batch.cmd_apply_flaglog(Namespace(edited=...))`.
- `pipeline.batch.cmd_publish(Namespace)`: `edited, vttout, html, docx, format ("html"|"docx"|"both"), archive, backend, model, batch, batch_timeout, judgment_dir, delete_working`.
- `pipeline.batch.make_backend(args)`: builds the judgment backend; the `claude` choice constructs `ClaudeCLIBackend`.
- `pipeline.flaglog`: `parse_flaglog`, `write_flaglog`, `editable_possible`, `entry_text_spans`, `RULE`.
- `pipeline.naming.vtt_stem_for_flaglog`, `pipeline.parse` (VTT/cue parsing), `pipeline.apply._mmss`.
- Flag log text format the GUI reads and rewrites: a "CORRECTIONS APPLIED" section with lines like
  `  • Entry 33: 'texter' → 'texture' — reason` (markers `•` auto, `↺` undone, `✎` reviewer edit) and an
  "ENTRIES REQUIRING HUMAN REVIEW" section with blocks `Entry N | timecode / Found: / Issue: / Possible:`.
  `gui/review.py` and `runner.write_flaglog_entries` depend on this exact text, so confirm the target
  repo's flag log still uses it.

## Pipeline additions the GUI relies on (demo-era, not synced to the skills/ copies)

1. **`pipeline/claude_cli_backend.py`**: "My Claude plan (no key)" engine. Runs `claude -p` with the
   same rules + prompts the API backend uses as the system prompt, cue text on stdin, **all tools off**
   (`--tools ""`), in an empty temp folder, with `ANTHROPIC_API_KEY` removed from the child env so it
   always uses the plan login. Uses `--json-schema` so replies are validated JSON, retries once on an
   unreadable reply, and saves a bad reply to `~/.config/caption-to-transcript/last_ai_reply.txt`.
   Exposes `find_claude()` (checks PATH plus common install paths), `auth_status()` (feeds the sign-in
   pill) and `ClaudeCLIBackend.cleanup/publish`. Reuses `_extract_json`/`APIBackendError` from `api_backend.py`.
2. **`pipeline/docx_publish.py`**: Word output mirroring `publish.py` structure. Real heading styles,
   12pt minimum, document title property, reuses `publish._apply_publish_text_fixes`. `docx_available()`
   guards the optional `python-docx` import. The reference was adapted from GitHub's version, so the target
   repo probably already has its own; prefer that one.
3. **`pipeline/batch.py` edits**: `--backend claude`, `--format html|docx|both`, `--docx DIR`.
4. **Flag-log/apply behavior the review UI assumes** (`pipeline/flaglog.py`, `pipeline/apply.py`): flags the
   user leaves unchanged are skipped ("left as is"); no-change "fixes" are hidden; flags on already-fixed lines
   are dropped if the suggestion is already in the caption, else re-pointed at the current caption text
   (`review.normalize_flags`, also run before bulk Apply); suggestions that merely repeat the line count as no
   suggestion; after an entry ending in a comma, the next entry is lowercased (common-word list only,
   logged as an undoable correction).
5. **Rule/prompt text** (`rules/Caption_Cleanup_Rules.md`, `pipeline/prompts/corrections.md`): Rule 2b
   (discourse fillers kept and set off with commas; do not flag doubled words), Rule 2c (broken numbers such as
   "seven, 57" to 757 when nearby lines confirm; flag numbers that break the math, on the right entry),
   corrections.md rules 7, 8, 11, 12, and the comma-lowercase rule. These were flagged "carry into GitHub rules"
   and are optional for the GUI to work. Check whether the target repo has them before adding anything.

## Dependencies (`requirements-gui.txt`)

`fastapi>=0.110`, `uvicorn>=0.27`, `pydantic>=2.0`, `pywebview>=5.0`, `keyring>=25.0`, optional
`anthropic>=0.40` (API engine), `python-docx>=1.1` (Word output). The core pipeline needs none of these.
Launcher `launchers/4_Open_App.command` creates `.venv`, installs the requirements on first run, then runs
`python -m gui.main`. It relies on `launchers/_common.sh` (`require_python`, `$PY`, `$VENV`, `$REPO`).

## Suggested rebuild order

1. Skeleton: `gui/main.py` + `gui/app.py` serving a blank page; confirm the window opens and `/api/state` works.
2. `runner.py` + Step 1 (clean) with the stub backend; confirm the job log streams.
3. Flag log read/write + Step 2 list + bulk Apply.
4. Step 3 publish (HTML), then the Word checkbox.
5. Claude-plan engine and the sign-in pill (needs `claude` installed and `/login` done).
6. API key panel and keystore.
7. Review window (`review.py`, `review.html`) last; it is the largest piece and depends on the flag-log format.

## Known gaps and ideas

- "Listen to verify": play the video at a flagged timecode (not built).
- The reference `runner.py` uses a hand-built `argparse.Namespace`; replace with `pipeline/core.py` if available.
- Nothing in this GUI was ever merged to GitHub; this copy's `To Do.md` has the merge checklist.
