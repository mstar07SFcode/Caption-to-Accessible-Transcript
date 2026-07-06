---
name: flaglog-apply
description: Apply human-reviewed flag-log corrections to the cleaned VTT files. Trigger on "apply flag log", "run flaglog", "I've reviewed the flag log — apply it", "apply the corrections". Run without asking for confirmation.
---

# Apply Flag Log

Step 1b (optional). After the user reviews the `FlagLog_*.txt` files in
`Edited_Captions` — accepting, editing, or deleting each entry — this applies
the remaining corrections to the matching `*.vtt` files. It is a pure-Python
find/replace; no AI judgment is involved. Run immediately when invoked.

How the user prepares each flag-log entry: leave it (accept the `Possible:`
text), edit the `Possible:` text, or delete the whole entry block (skip it).

## Procedure

Let `WF` be the user's working folder.

```bash
cd "${CLAUDE_PLUGIN_ROOT}/skills/flaglog-apply" && python3 -m pipeline.batch apply-flaglog \
    --edited "$WF/Edited_Captions"
```

The pipeline matches each `FlagLog_<stem>.txt` to `<stem>.vtt`, applies every
remaining entry whose `Possible:` field is an actionable replacement (skipping
"Listen to verify" notes and any text not found verbatim), updates the VTT in
place, and renames the log to `Applied_FlagLog_<stem>.txt`.

## Report

Relay the pipeline's per-file output: entries applied, skipped (no actionable
replacement), and unmatched. Then tell the user they can run Transcript Publish.
