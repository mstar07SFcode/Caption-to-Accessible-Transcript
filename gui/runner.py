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
import shutil
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from pipeline import batch, naming
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

    # Stage 1 — deterministic, no AI.
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
        no_archive=False,
    ))

    cues_files = sorted(jdir.glob("*.cues.txt"))
    if not cues_files:
        shutil.rmtree(jdir, ignore_errors=True)
        return

    # Stage 2 — one reviewer per file.
    n = len(cues_files)
    print(f"\nReviewing {n} file(s) with Claude — one reviewer each, "
          f"up to {MAX_PARALLEL_REVIEWS} at a time. This is the slow part.")
    backend = ClaudeCLIBackend()
    judged = 0
    failures: list[str] = []

    def review(cues_path: Path):
        stem = cues_path.name[: -len(".cues.txt")]
        return cues_path, backend.judge_file(cues_path, jdir / f"{stem}.judgment.json")

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_REVIEWS) as pool:
        futures = [pool.submit(review, c) for c in cues_files]
        for fut in as_completed(futures):
            try:
                cues_path, (ncorr, nflag) = fut.result()
                judged += 1
                stem = cues_path.name[: -len(".cues.txt")]
                print(f"  [{judged}/{n}] {stem} — {ncorr} correction(s), "
                      f"{nflag} flag(s)")
            except ClaudeCLIError as e:
                failures.append(str(e))
                print(f"  ERROR: {e}")

    if failures and not judged:
        shutil.rmtree(jdir, ignore_errors=True)
        raise ClaudeCLIError(
            "No file could be reviewed. Your captions are cleaned but "
            "unreviewed in Edited_Captions; run Clean again to retry.")

    # Stage 3 — fold the judgments in. Files without one keep the baseline.
    print()
    batch.cmd_apply_judgment(SimpleNamespace(
        edited=str(wf / "Edited_Captions"),
        judgment_dir=str(jdir),
    ))
    shutil.rmtree(jdir, ignore_errors=True)
    if failures:
        print(f"\nWARNING: {len(failures)} file(s) could not be reviewed and "
              f"were left as the plain deterministic clean.")


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
