"""Background job running + flag-log editing helpers for the GUI.

The GUI never reimplements pipeline logic. It calls the same `batch.cmd_*`
functions the CLI does, on a worker thread, capturing their printed output so
the window can show progress instead of freezing.

The argparse Namespace is built by hand here because those functions were
written for a CLI. When `pipeline/core.py` lands (see the architecture doc),
this module should call that instead and lose the Namespace shim.
"""

from __future__ import annotations

import contextlib
import io
import itertools
import re
import shutil
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from pipeline import batch, files as F, naming
from pipeline.flaglog import editable_possible, parse_flaglog, write_flaglog, RULE

SUBFOLDERS = ("Raw_Captions", "Edited_Captions", "Archived_Captions",
              "VTT_Files", "HTML_Transcripts", "Word_Transcripts")

# Scratch folder for the judgment stage, created and removed per run.
JUDGMENT_DIR = ".judgment"
# How many files are reviewed at once. The skill launches every agent in
# parallel; a cap keeps a 40-lecture batch from opening 40 at once.
MAX_PARALLEL_REVIEWS = 4


# --- Jobs ------------------------------------------------------------------

@dataclass
class Job:
    id: str
    label: str
    status: str = "running"          # running | done | error
    lines: list[str] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "status": self.status,
                "lines": self.lines, "error": self.error}


class _LineWriter(io.TextIOBase):
    """Collects printed output line by line so the UI can poll it."""

    def __init__(self, job: Job):
        self._job = job
        self._buf = ""

    def write(self, s: str) -> int:
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self._job.lines.append(line.rstrip())
        return len(s)

    def flush(self) -> None:
        if self._buf.strip():
            self._job.lines.append(self._buf.rstrip())
            self._buf = ""


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def busy(self) -> bool:
        return any(j.status == "running" for j in self._jobs.values())

    def start(self, label: str, fn, *args, **kwargs) -> Job:
        """Run fn on a worker thread, capturing its stdout into the job."""
        with self._lock:
            job = Job(id=str(next(self._ids)), label=label)
            self._jobs[job.id] = job

        def target():
            writer = _LineWriter(job)
            try:
                with contextlib.redirect_stdout(writer):
                    fn(*args, **kwargs)
                writer.flush()
                job.status = "done"
            except SystemExit as e:
                # batch.make_backend calls sys.exit(2) on a bad API key.
                writer.flush()
                job.status = "error"
                job.error = (
                    "The AI option could not start. " +
                    ("Claude Code was not found or is not signed in - in "
                     "Terminal run `claude`, then type /login."
                     if e.code == 3 else
                     "Check that your API key is set and the anthropic "
                     "package is installed.") +
                    f" (exit code {e.code})")
            except Exception as e:
                writer.flush()
                job.status = "error"
                job.error = f"{type(e).__name__}: {e}"
                job.lines.append(traceback.format_exc().strip())

        threading.Thread(target=target, daemon=True).start()
        return job


# --- Pipeline invocations --------------------------------------------------

def ensure_folders(wf: Path) -> None:
    for name in SUBFOLDERS:
        (wf / name).mkdir(parents=True, exist_ok=True)


def _backend_for(use_ai: bool, engine: str) -> str:
    """Map the window's choices to a pipeline backend name.

    engine: "claude" = Claude Code signed in with your Claude plan (no key),
            "api"    = Anthropic API key.
    """
    if not use_ai:
        return "stub"
    return "api" if engine == "api" else "claude"


def run_clean(wf: Path, course: str, speaker: str, use_ai: bool,
              use_batch: bool = False, engine: str = "claude") -> None:
    ensure_folders(wf)
    if use_ai and engine == "claude":
        _clean_with_agents(wf, course, speaker)
        return
    batch.cmd_clean(SimpleNamespace(
        raw=str(wf / "Raw_Captions"),
        out=str(wf / "Edited_Captions"),
        archive=str(wf / "Archived_Captions"),
        course=course or None,
        speaker=speaker or None,
        backend=_backend_for(use_ai, engine),
        model=None,
        batch=bool(use_batch) and engine == "api",
        judgment_dir=None,
        emit_prompts=None,
        no_archive=False,
    ))


def _mark_awaiting_review(wf: Path, cues_files: list[Path]) -> None:
    """Stamp the stage-1 flag logs as not final.

    Stage 1 writes a flag log per file with no corrections and no flags,
    because the AI has not run yet; stage 3 overwrites it with the real one.
    In between, a folder inspected by hand shows "(none)" and "0 entries
    require review", which reads as a finished file with nothing wrong rather
    than a file whose review is still running.
    """
    edited = wf / "Edited_Captions"
    for cues in cues_files:
        stem = cues.name[: -len(".cues.txt")]
        log = edited / f"FlagLog_{stem}.txt"
        if not log.is_file():
            continue
        try:
            log.write_text(
                "CAPTION CLEANUP FLAG LOG\n"
                f"File: {stem}\n"
                + "─" * 62 + "\n\n"
                "AI REVIEW IN PROGRESS — THIS FILE IS NOT FINISHED\n\n"
                "The captions have had the automatic pass only. Claude is\n"
                "still reviewing them; corrections and flags will replace\n"
                "this note when it finishes.\n\n"
                "If this note is still here, the review did not complete —\n"
                "run Clean captions again.\n",
                encoding="utf-8")
        except OSError:
            pass   # cosmetic only; never fail a run over it


def _clean_with_agents(wf: Path, course: str, speaker: str) -> None:
    """Clean the way the caption-cleanup skill does, in three stages.

    1. A deterministic pass writes the baseline VTTs and one <stem>.cues.txt
       per file. No AI yet.
    2. One reviewer per file, in parallel, each reading only its own cues and
       writing its own <stem>.judgment.json.
    3. apply-judgment folds those judgments into the VTTs and flag logs.

    Handing the whole batch to a single call instead -- which is what the
    judgment backend used to do -- produced a few corrections at the start of
    a lecture and nothing after, however the call was shaped. One reviewer per
    file is the part that matters, so the GUI runs the skill's sequence rather
    than its own.
    """
    from pipeline.claude_cli_backend import ClaudeCLIBackend, ClaudeCLIError

    jdir = wf / JUDGMENT_DIR
    shutil.rmtree(jdir, ignore_errors=True)

    # Stage 1 — deterministic, no AI. cmd_clean prints its own "Cleaned N
    # file(s) — 0 correction(s), 0 flag(s)" summary, which is true for the CLI
    # where that IS the whole job, but here it announces completion at the
    # one-third mark and reads as a finished result with nothing found.
    # Swallow it and report the stage instead.
    # The sources are archived only once the whole three-stage run has
    # succeeded. Stage 1 used to move them itself, which emptied
    # Raw_Captions seconds after the click while the review — the part that
    # does the real work — had not started, and left nothing to re-run from
    # if a later stage failed.
    raw_root = wf / "Raw_Captions"
    sources = F.scan_sources(raw_root)

    print("Step 1 of 3 — preparing captions")
    staged = io.StringIO()
    with contextlib.redirect_stdout(staged):
        batch.cmd_clean(SimpleNamespace(
            raw=str(wf / "Raw_Captions"),
            out=str(wf / "Edited_Captions"),
            archive=str(wf / "Archived_Captions"),
            course=course or None,
            speaker=speaker or None,
            backend="stub",
            model=None,
            batch=False,
            judgment_dir=None,
            emit_prompts=str(jdir),
            no_archive=True,
        ))
    # Warnings (duplicate names, unreadable files) still matter to the user.
    for line in staged.getvalue().splitlines():
        if "WARNING" in line or "ERROR" in line:
            print(f"  {line.strip()}")

    cues_files = sorted(jdir.glob("*.cues.txt"))
    if not cues_files:
        shutil.rmtree(jdir, ignore_errors=True)
        print("  No caption files found in Raw_Captions.")
        return
    n = len(cues_files)
    _mark_awaiting_review(wf, cues_files)
    print(f"  {n} file(s) ready.\n")

    # Stage 2 — one reviewer per file.
    print(f"Step 2 of 3 — reviewing with Claude")
    print(f"  Two passes per file, up to {MAX_PARALLEL_REVIEWS} files at a "
          f"time. Allow a few minutes per file.")
    backend = ClaudeCLIBackend(progress=lambda _msg: None)   # stage lines only
    done = 0
    failures: list[str] = []

    def review(cues_path: Path):
        stem = cues_path.name[: -len(".cues.txt")]
        print(f"  {stem} — in process")
        return stem, backend.judge_file(cues_path, jdir / f"{stem}.judgment.json")

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_REVIEWS) as pool:
        futures = [pool.submit(review, c) for c in cues_files]
        for fut in as_completed(futures):
            try:
                stem, (ncorr, nflag) = fut.result()
                done += 1
                print(f"  {stem} — completed ({done} of {n})")
            except ClaudeCLIError as e:
                failures.append(str(e))
                print(f"  could not be reviewed: {e}")

    if failures and not done:
        shutil.rmtree(jdir, ignore_errors=True)
        raise ClaudeCLIError(
            "No file could be reviewed. Your captions are cleaned but "
            "unreviewed in Edited_Captions; run Clean again to retry.")

    # Stage 3 — fold the judgments in. Files without one keep the baseline.
    print(f"\nStep 3 of 3 — applying corrections")
    applied = io.StringIO()
    with contextlib.redirect_stdout(applied):
        batch.cmd_apply_judgment(SimpleNamespace(
            edited=str(wf / "Edited_Captions"),
            judgment_dir=str(jdir),
        ))
    shutil.rmtree(jdir, ignore_errors=True)

    # One honest total, from the flag logs that were actually written.
    corr = flags = 0
    for line in applied.getvalue().splitlines():
        m = re.search(r"(\d+) correction\(s\), (\d+) flag\(s\)", line)
        if m:
            corr += int(m.group(1))
            flags += int(m.group(2))
    print(f"\nCompleted — {n} file(s), {corr} correction(s) applied, "
          f"{flags} flag(s) to review.")
    if failures:
        print(f"WARNING: {len(failures)} file(s) could not be reviewed and "
              f"were left as the plain deterministic clean.")
        print("  Your originals stay in Raw_Captions so you can run Clean "
              "again; the unreviewed results are in Edited_Captions.")
        return

    for src in sources:
        if src.exists():
            F.archive_source(src, raw_root, wf / "Archived_Captions")
    F.prune_empty_dirs(raw_root)


def run_apply_flaglog(wf: Path) -> None:
    # Bring each pending flag log in line with the captions first (see
    # review.normalize_flags), so flags on auto-fixed lines apply cleanly.
    for f in read_flaglogs(wf):
        write_flaglog_entries(wf, f["file"], f["entries"])
    _run_apply_flaglog(wf)


def _run_apply_flaglog(wf: Path) -> None:
    batch.cmd_apply_flaglog(SimpleNamespace(edited=str(wf / "Edited_Captions")))


def run_publish(wf: Path, ai_headings: bool, delete_working: bool,
                use_batch: bool = False, engine: str = "claude",
                fmt: str = "html") -> None:
    """Publish the edited captions as a web page, a Word document, or both.

    One cmd_publish call whatever the format: with fmt="both" it renders each
    transcript twice from a single judgment, so ticking both boxes with AI
    headings on costs one AI pass, not two.
    """
    ensure_folders(wf)
    batch.cmd_publish(SimpleNamespace(
        edited=str(wf / "Edited_Captions"),
        vttout=str(wf / "VTT_Files"),
        html=str(wf / "HTML_Transcripts"),
        docx=str(wf / "Word_Transcripts"),
        format=fmt,
        archive=str(wf / "Archived_Captions"),
        backend=_backend_for(ai_headings, engine),
        model=None,
        batch=bool(use_batch) and engine == "api",
        judgment_dir=None,
        title_map=None,
        speaker_map=None,
        delete_working=bool(delete_working),
    ))


# --- Folder status ---------------------------------------------------------

def folder_status(wf: Path) -> dict:
    def count(sub: str, pattern: str) -> int:
        d = wf / sub
        return len([p for p in d.rglob(pattern) if p.is_file()]) if d.is_dir() else 0

    return {
        "raw": count("Raw_Captions", "*.srt") + count("Raw_Captions", "*.txt"),
        "edited": count("Edited_Captions", "*.vtt"),
        "flaglogs": count("Edited_Captions", "FlagLog_*.txt"),
        "vtt": count("VTT_Files", "*.vtt"),
        "html": count("HTML_Transcripts", "*.html"),
        "docx": count("Word_Transcripts", "*.docx"),
    }


# --- Flag log read / write -------------------------------------------------

def _normalized(vtt: Path, entries: list[dict]) -> list[dict]:
    from .review import normalize_flags, cue_texts
    return normalize_flags(entries, cue_texts(vtt))


def _corrections(text: str) -> list[dict]:
    from .review import parse_corrections
    return parse_corrections(text)


def read_flaglogs(wf: Path) -> list[dict]:
    """Every pending flag log, parsed into editable entries."""
    edited = wf / "Edited_Captions"
    if not edited.is_dir():
        return []
    out = []
    for log in sorted(edited.glob("FlagLog_*.txt")):
        text = log.read_text(encoding="utf-8")
        stem = naming.vtt_stem_for_flaglog(log.name)
        out.append({
            "file": log.name,
            "stem": stem,
            "has_vtt": (edited / f"{stem}.vtt").exists(),
            "corrections": _corrections(text),
            "entries": _normalized(edited / f"{stem}.vtt", [
                {"entry": r.entry, "timecode": r.timecode, "found": r.found,
                 "issue": r.issue, "possible": editable_possible(r.found, r.possible), "keep": True}
                for r in parse_flaglog(text)
            ]),
        })
    return out


def write_flaglog_entries(wf: Path, filename: str, entries: list[dict]) -> None:
    """Rewrite only the review section of a flag log, preserving the rest.

    Entries the user discarded are simply omitted, which is exactly what
    deleting the block by hand in a text editor would do.
    """
    log = (wf / "Edited_Captions" / filename)
    if not log.is_file():
        raise FileNotFoundError(filename)

    original = log.read_text(encoding="utf-8")
    head = original.split("ENTRIES REQUIRING HUMAN REVIEW", 1)[0].rstrip("\n")

    kept = [e for e in entries if e.get("keep", True)]
    body: list[str] = [""]
    n = len(kept)
    body.append(f"ENTRIES REQUIRING HUMAN REVIEW  ({n} {'entry' if n == 1 else 'entries'})")
    body.append("These entries contain likely auto-caption errors that could not be")
    body.append("corrected with confidence. Please listen to the video and correct")
    body.append("the cleaned file as needed.")
    body.append("")
    if kept:
        for e in kept:
            body.append(f"Entry {e['entry']} | {e.get('timecode', '')}")
            body.append(f'  Found:    "{e.get("found", "")}"')
            body.append(f'  Issue:    {e.get("issue", "")}')
            body.append(f'  Possible: "{e.get("possible", "")}"')
            body.append("")
    else:
        body.append("  (none)")
        body.append("")
    body.append(RULE)
    body.append(f"{n} {'entry requires' if n == 1 else 'entries require'} review.")

    log.write_text(head + "\n" + "\n".join(body) + "\n", encoding="utf-8")
