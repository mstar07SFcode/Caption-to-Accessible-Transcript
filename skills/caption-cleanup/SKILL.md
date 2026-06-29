---
name: caption-cleanup
description: Clean raw SRT/TXT caption files to a verbatim, readable standard and produce upload-ready WebVTT plus a flag log of items needing human review. Trigger on "clean the captions", "run caption cleanup", "clean the SRT", "fix the captions", or when caption files are placed in a Raw_Captions folder.
---

# Caption Cleanup

Step 1 of the caption workflow. Cleans raw `.srt`/`.txt` captions into a cleaned
WebVTT (`.vtt`) plus a `FlagLog_*.txt` of items needing human review, then
archives the originals.

The work is split between a deterministic Python pipeline (bundled with this
plugin) and AI judgment. The pipeline handles filler removal, header stripping,
SRT→VTT conversion, filenaming, and flag-log/VTT writing. The AI handles
recognition corrections, punctuation/continuation, capitalization, and deciding
what to flag — governed entirely by `${CLAUDE_PLUGIN_ROOT}/rules/Caption_Cleanup_Rules.md`.

## Folders (in the user's working folder, NOT the plugin)

| Folder | Purpose |
|---|---|
| `Raw_Captions` | Source `.srt`/`.txt` files (may contain module subfolders) |
| `Edited_Captions` | Output: `*.vtt` + `FlagLog_*.txt` |
| `Archived_Captions` | Originals, moved here after cleanup |

Create any missing folders before running. Let `WF` be the absolute path to the
user's working folder.

## Procedure

1. **Read the rules.** Read `${CLAUDE_PLUGIN_ROOT}/rules/Caption_Cleanup_Rules.md`
   in full and `${CLAUDE_PLUGIN_ROOT}/pipeline/prompts/corrections.md` (the
   judgment instructions + JSON schema). These govern every editing decision.

2. **Ask for course and speaker** if not already known (applied to the batch).
   If `Raw_Captions` has module subfolders, the pipeline derives the module code
   from the folder name automatically.

3. **Deterministic pass + emit judgment prompts:**
   ```bash
   cd "${CLAUDE_PLUGIN_ROOT}" && python3 -m pipeline.batch clean \
       --raw "$WF/Raw_Captions" --out "$WF/Edited_Captions" \
       --archive "$WF/Archived_Captions" \
       --course "<COURSE>" --speaker "<SPEAKER>" \
       --emit-prompts "$WF/.judgment"
   ```
   This writes baseline `*.vtt` + empty `FlagLog_*.txt` to `Edited_Captions`,
   archives the sources, and writes one `<stem>.cues.txt` per file to
   `$WF/.judgment`. Note any duplicate/copy collisions it reports.

4. **Judgment — ALWAYS use parallel sub-agents.** Count the `.cues.txt` files
   in `$WF/.judgment`. **Do NOT read any cues file into the main context.**
   Instead, immediately launch one Agent per file in a single parallel tool call
   (all in the same message). Each agent receives: the cues file path, the rules
   summary, the JSON schema, and instructions to write `<stem>.judgment.json`
   and report one status line. This applies even for small batches — reading
   cues files into the main context is always wrong and makes the session slow.

   Each agent should:
   - Read its assigned `<stem>.cues.txt` via bash
   - Apply the rules (corrections at ≥90% confidence, otherwise flag)
   - Write `$WF/.judgment/<stem>.judgment.json`
   - Report: `DONE: N corrections, N flags` or `ERROR: reason`
   
5. **Apply judgment:**
   ```bash
   cd "${CLAUDE_PLUGIN_ROOT}" && python3 -m pipeline.batch apply-judgment \
       --edited "$WF/Edited_Captions" --judgment-dir "$WF/.judgment"
   ```
   This rewrites each cleaned VTT with the corrections and regenerates its flag
   log. Then delete the `$WF/.judgment` scratch folder.

6. **Report:** number of files cleaned, corrections applied, and entries flagged
   for review. Tell the user to review the `FlagLog_*.txt` files, then run the
   Apply Flag Log skill (step 1b) or go straight to Transcript Publish.

## Alternative: no Claude judgment available

If running outside Claude (or to skip the per-file judgment), the pipeline can
call the Anthropic API directly — add `--backend api` (with `ANTHROPIC_API_KEY`
set) to the `clean` command and skip steps 4–5. See the repo README.

## Output naming

VTT: `[Course_][Module_]Name.vtt` (no prefix, no date). Flag log:
`FlagLog_<stem>.txt`. VTT header is `WEBVTT` + `Speaker:` + `Course:` only.
