# Caption-to-Accessible-Transcript

A Claude plugin that cleans auto-generated video captions to a verbatim,
readable standard and publishes **WCAG 2.1 AA** accessible HTML transcripts.

It bundles three skills and a pure-Python pipeline. The pipeline does the
mechanical work (filler removal, SRT→VTT, naming, flag-log/VTT/HTML writing).
The AI judgment — recognition corrections, punctuation, capitalization,
flagging, section headings — comes from **your own Claude** (no API key) or, if
you run it standalone, from the **Anthropic API**.

## What you get

- **Caption Cleanup** — raw `.srt`/`.txt` → cleaned `.vtt` + a flag log of items
  needing human review.
- **Apply Flag Log** — apply the corrections you accepted in the flag log.
- **Transcript Publish** — cleaned `.vtt` → accessible HTML transcript +
  Panopto-ready VTT archive.

## Requirements

- **Python 3.9+** (for the pipeline). No third-party libraries for the core.
- **Claude** (Cowork or Claude Code) for the AI judgment via your own account —
  *or* an **Anthropic API key** to run the AI judgment standalone (`pip install
  anthropic`). Basic, deterministic cleanup needs neither.

## Install (public repo)

In **Claude Code**:

```
/plugin marketplace add <your-org>/Caption-to-Accessible-Transcript
/plugin install caption-to-accessible-transcript
```

In **Cowork**: Settings → Capabilities → add the GitHub repo as a marketplace,
then install the plugin.

## Use (inside Claude)

1. Put caption files in a `Raw_Captions` folder in your working folder (module
   subfolders are fine).
2. Say "clean the captions." The Caption Cleanup skill runs the pipeline, your
   Claude supplies the judgment, and you get `Edited_Captions/*.vtt` + flag logs.
3. Review the `FlagLog_*.txt` files, then "apply the flag log."
4. Say "publish the transcripts" for accessible HTML in `HTML_Transcripts` and
   Panopto-ready VTTs in `VTT_Files`.

## Use (standalone, no Claude)

Double-click launchers (macOS) are in `launchers/`. Run
`0_Setup_AI_Cleanup.command` once to enable AI mode (creates a venv, installs
`anthropic`), then `1_Clean_Captions`, `2_Apply_FlagLog`, `3_Publish_Transcripts`.
Basic mode needs only Python; AI mode prompts for an Anthropic API key.

CLI directly:

```bash
cd <plugin folder>
python3 -m pipeline.batch clean   --raw Raw_Captions --out Edited_Captions \
        --archive Archived_Captions --course RHET-103 --speaker "Jane Doe" [--backend api] [--batch]
python3 -m pipeline.batch apply-flaglog --edited Edited_Captions
python3 -m pipeline.batch publish --edited Edited_Captions --vttout VTT_Files \
        --html HTML_Transcripts --archive Archived_Captions [--backend api] [--batch]
```

`--backend api` uses the Anthropic API (needs `ANTHROPIC_API_KEY`); `--batch`
submits all files as one Message Batch (50% cheaper). Prompt caching is always
on. See `tests/` for the validated behavior.

## Editing the rules

All editing behavior lives in `rules/Caption_Cleanup_Rules.md` and the prompts
in `pipeline/prompts/`. These are the single source of truth for both the
in-Claude path and the API path. If you maintain a canonical copy elsewhere,
keep this repo in sync from it before pushing (see `tools/sync_from_local.sh`).

## Privacy

Caption content and generated documents stay in your working folders and are
git-ignored — they are never committed. Basic mode sends nothing off-machine;
AI mode transmits caption text to Anthropic for processing (not stored or
trained on under the API/commercial terms). No API keys are stored in the repo.

## License

MIT — see `LICENSE`.
