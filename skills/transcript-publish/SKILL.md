---
name: transcript-publish
description: Convert cleaned VTT caption files into accessible WCAG 2.1 AA HTML transcripts and archive Panopto-ready VTTs. Trigger on "publish the transcripts", "convert to HTML", "generate the HTML transcript", "run transcript publish".
---

# Transcript Publish

Step 2 (final). Converts each cleaned `*.vtt` in `Edited_Captions` into an
accessible HTML transcript, archives a standards-compliant VTT, empties
`Archived_Captions`, and clears the working files.

Deterministic parts (timecodes, duration, HTML scaffolding, header strip) are
handled by the pipeline. Section headings and paragraph structure are AI
judgment, governed by `${CLAUDE_PLUGIN_ROOT}/pipeline/prompts/headings.md`.

## Folders (in the user's working folder)

| Folder | Purpose |
|---|---|
| `Edited_Captions` | Input: cleaned `*.vtt` (+ flag logs) |
| `VTT_Files` | Archive: standards-compliant `*.vtt` for Panopto |
| `HTML_Transcripts` | Output: accessible `.html` |
| `Archived_Captions` | **Emptied at the start of this step** |

Let `WF` be the user's working folder.

## Procedure

1. **Judgment (recommended).** Read `${CLAUDE_PLUGIN_ROOT}/pipeline/prompts/headings.md`
   for the schema. For each `*.vtt` in `$WF/Edited_Captions`, read its cues
   directly and write a `<stem>.judgment.json` to `$WF/.judgment` matching that
   schema (sections, paragraph_breaks, doubled_words, sic). Use a sub-agent per
   file when there are more than 3 files. (The `<stem>` is the VTT filename
   without `.vtt`.)

2. **Publish with judgment:**
   ```bash
   cd "${CLAUDE_PLUGIN_ROOT}" && python3 -m pipeline.batch publish \
       --edited "$WF/Edited_Captions" --vttout "$WF/VTT_Files" \
       --html "$WF/HTML_Transcripts" --archive "$WF/Archived_Captions" \
       --judgment-dir "$WF/.judgment"
   ```

3. **Basic alternative (no AI):** run the same command without `--judgment-dir`;
   the pipeline emits one section and simple paragraphs.

The pipeline empties `Archived_Captions` first, writes HTML to
`HTML_Transcripts`, archives header-stripped VTTs to `VTT_Files`, and clears the
working files in `Edited_Captions`. Afterward, delete the `$WF/.judgment`
scratch folder.

## Output Filename Naming Rules

Apply these rules to every HTML transcript filename (and its `<title>` / `<h1>`) before saving:

**1. Remove duplicate module prefix.**
Source filenames from Zoom/Canvas recordings sometimes repeat the module
number: `MSAS-603_M4_M4Lapping`. Strip the second occurrence so the segment
after the module token starts directly with the topic:
- ✅ `Transcript_MSAS-603_M4_Lapping.html`
- ❌ `Transcript_MSAS-603_M4_M4Lapping.html`

**2. Remove orphaned attempt numbers.**
A trailing number or version suffix (e.g. `2`, `1`, `V3`) that has no
counterpart in the same folder is an artifact of the recording attempt, not
meaningful to students. Remove it.
- If `filename2` exists but `filename1` does not → rename to `filename`.
- If `filename1` exists but `filename2` does not → rename to `filename`.
- If `filenameV3` exists but `filenameV1` / `filenameV2` do not → rename to `filename`.
- If a genuine sequence exists (both `filename1` and `filename2` are present) → keep the numbers.

Apply both rules to the HTML `<title>` and `<h1>` tag as well as the filename.

## Report

Number of transcripts published; confirm files are in `HTML_Transcripts` and
Panopto-ready VTTs in `VTT_Files`. Note any filenames corrected under the
naming rules above.

## Alternative: Anthropic API

Add `--backend api` (with `ANTHROPIC_API_KEY` set) to do the structuring without
Claude. See the repo README.
