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

- **Python 3.9+**, for the pipeline and the desktop app alike. The core needs
  no third-party libraries; the app installs its own into a private `.venv` on
  first run.
- **macOS or Windows** for the desktop app. Linux runs it too, in the browser
  fallback, unless you add a toolkit (`pip install 'pywebview[qt]'`).
- **Claude** (Cowork or Claude Code) for the AI judgment via your own account —
  *or* an **Anthropic API key** to run the AI judgment standalone (`pip install
  anthropic`). Basic, deterministic cleanup needs neither.

## Install (public repo)

In **Claude Code**:

```
/plugin marketplace add mstar07SFcode/Caption-to-Accessible-Transcript
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

`4_Open_App.command` opens all three steps in one window instead. Its first run
builds its own `.venv` from `requirements-gui.txt`, so it needs an internet
connection once. It takes its AI judgment from Claude Code signed in to your
plan, so it never asks for an API key — the window says so on screen, and tells
you what to do if Claude Code is missing or signed out.

**On Windows**, double-click `launchers\4_Open_App.bat` for that same app and
the same first-run install. The numbered `.command` steps are macOS-only; on
Windows drive the pipeline from PowerShell instead, as under *CLI directly*
below. If no app window can be opened — a Windows 10 machine with no Edge
WebView2 runtime, say — the app serves itself in your default browser and tells
you it did, rather than failing. Everything works there: Change folder asks for
a typed path, and the review window opens as a browser tab.

On first run a launcher asks where your caption folders are and creates the
five subfolders if they are missing. The answer is remembered in
`launchers/.caption_workflow` — delete that file to be asked again. Keep the
launchers inside the project folder, next to `pipeline/`.

CLI directly:

```bash
cd <plugin folder>
python3 -m pipeline.batch clean   --raw Raw_Captions --out Edited_Captions \
        --archive Archived_Captions --course RHET-103 --speaker "Jane Doe" [--backend api] [--batch]
python3 -m pipeline.batch apply-flaglog --edited Edited_Captions
python3 -m pipeline.batch publish --edited Edited_Captions --vttout VTT_Files \
        --html HTML_Transcripts --archive Archived_Captions [--backend api] [--batch] \
        [--delete-working]
```

`--backend api` uses the Anthropic API (needs `ANTHROPIC_API_KEY`); `--batch`
submits all files as one Message Batch (50% cheaper). Prompt caching is always
on. See `tests/` for the validated behavior.

`publish` deletes nothing by default. `--delete-working` empties
`Archived_Captions` and removes the working `.vtt` files and flag logs from
`Edited_Captions`, after the transcripts are safely written. (`--keep-working`
is still accepted and does nothing — keeping is now the default.)

## Editing the rules

All editing behavior lives in `rules/Caption_Cleanup_Rules.md`,
`rules/Transcript_Publish_Rules.md`, and the prompts in `pipeline/prompts/`.
These are the single source of truth for both the in-Claude path and the API
path — edit them here, at the repo root.

Cowork mounts only each skill's own `skills/<name>/` subtree at runtime, so
every skill folder carries its own copy of `rules/`, `pipeline/` and
`templates/`. After editing any of those three at the root, fan the changes out
before committing:

```bash
bash tools/sync_to_skills.sh
```

In practice you rarely run that by hand. `bash tools/setup.sh` installs a
pre-commit hook that syncs and stages the copies for you, the test suite fails
when a copy is stale and names the files, and CI re-runs the sync on every push
and fails if anything changed — so a missed sync surfaces instead of quietly
shipping.

`skills/*/SKILL.md` is deliberately not synced — edit those in place.

**Working on this repo?** See `CONTRIBUTING.md` for setup in one command, and
`UPDATING_THE_PLUGIN.md` for the release process.

## Privacy

Caption content and generated documents stay in your working folders and are
git-ignored — they are never committed. Basic mode sends nothing off-machine;
AI mode transmits caption text to Anthropic for processing (not stored or
trained on under the API/commercial terms). No API keys are stored in the repo.

## License

MIT — see `LICENSE`.
