"""FastAPI app behind the desktop window.

Serves one HTML page and a small JSON API. It holds no pipeline logic of its
own -- every route delegates to gui/runner.py, which delegates to pipeline/.

Runs on 127.0.0.1 only. Nothing here is exposed to the network.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import keystore, review, runner

HERE = Path(__file__).resolve().parent
# The shell launchers' remembered working folder: <repo>/launchers/.caption_workflow,
# holding one bare path on its first line. The window reads and writes that same
# file, so the app and the numbered .command launchers never disagree about which
# folder is in play. (The reference GUI kept its own copy under ~/.config; two
# files meant the app and the launchers could drift apart.)
CONFIG_FILE = HERE.parent / "launchers" / ".caption_workflow"

app = FastAPI(title="Caption Transcripts")
jobs = runner.JobManager()


# --- Working folder --------------------------------------------------------

def load_working_folder() -> str:
    """Read the folder the launchers already saved, so both share one setting."""
    if CONFIG_FILE.is_file():
        lines = CONFIG_FILE.read_text(encoding="utf-8").splitlines()
        if lines:
            return lines[0].strip()
    return ""


def save_working_folder(path: str) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(f"{path}\n", encoding="utf-8")


def _wf() -> Path:
    path = load_working_folder()
    if not path or not Path(path).is_dir():
        raise HTTPException(400, "No working folder set.")
    return Path(path)


# --- Models ----------------------------------------------------------------

class FolderIn(BaseModel):
    path: str

class KeyIn(BaseModel):
    api_key: str = ""
    remember: bool = False

class CleanIn(BaseModel):
    course: str = ""
    speaker: str = ""
    use_ai: bool = False
    use_batch: bool = False
    engine: str = "claude"      # "claude" (your plan, no key) or "api"

class PublishIn(BaseModel):
    html: bool = True
    docx: bool = False
    ai_headings: bool = False
    delete_working: bool = False
    use_batch: bool = False
    engine: str = "claude"

class SaveFlagsIn(BaseModel):
    file: str
    entries: list[dict]


# --- Routes ----------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(HERE / "index.html")


@app.get("/api/state")
def get_state():
    path = load_working_folder()
    valid = bool(path) and Path(path).is_dir()
    key, source = keystore.load()
    return {
        "working_folder": path,
        "valid": valid,
        "status": runner.folder_status(Path(path)) if valid else None,
        "has_key": bool(key),
        "key_source": source,
        "key_hint": (key[:10] + "..." + key[-4:]) if len(key) > 18 else "",
        "can_remember": keystore.keyring_available(),
        "busy": jobs.busy(),
        # Re-checked automatically until it reports signed in (no button needed).
        "claude": _claude_status(refresh=not _claude_cache.get("logged_in")),
    }


_claude_cache: dict = {}

def _claude_status(refresh: bool = False) -> dict:
    """Is Claude Code installed and signed in? Cached: the check takes a second."""
    if refresh or not _claude_cache:
        from pipeline.claude_cli_backend import auth_status
        _claude_cache.clear()
        _claude_cache.update(auth_status())
    return dict(_claude_cache)


@app.post("/api/claude/check")
def claude_check():
    return _claude_status(refresh=True)


@app.post("/api/folder")
def set_folder(body: FolderIn):
    p = Path(body.path).expanduser()
    if not p.is_dir():
        raise HTTPException(400, f"Not a folder: {p}")
    save_working_folder(str(p))
    runner.ensure_folders(p)
    return {"ok": True, "working_folder": str(p),
            "status": runner.folder_status(p)}


@app.post("/api/key")
def set_key(body: KeyIn):
    key = body.api_key.strip()
    if key and not keystore.looks_like_key(key):
        raise HTTPException(
            400, "That does not look like an Anthropic key - they start with "
                 "'sk-ant-'. Copy the whole thing from console.anthropic.com.")
    source = keystore.save(key, body.remember)
    return {"ok": True, "has_key": bool(key), "key_source": source}


@app.post("/api/key/test")
def test_key(body: KeyIn):
    """Verify a key against the API. Costs no tokens."""
    key = body.api_key.strip() or keystore.load()[0]
    ok, message = keystore.verify(key)
    return {"ok": ok, "message": message}


@app.post("/api/key/forget")
def forget_key():
    keystore.forget()
    return {"ok": True}


def _require_key_if_ai(use_ai: bool, engine: str = "api") -> None:
    if use_ai and engine == "claude":
        st = _claude_status(refresh=True)
        if not st["logged_in"]:
            raise HTTPException(400, st["message"])
        return
    if use_ai and not keystore.load()[0]:
        raise HTTPException(
            400, "AI mode needs an Anthropic API key - open 'API key' at the "
                 "top of the window and paste yours in.")


@app.post("/api/clean")
def clean(body: CleanIn):
    wf = _wf()
    _require_key_if_ai(body.use_ai, body.engine)
    if jobs.busy():
        raise HTTPException(409, "Another step is still running.")
    job = jobs.start("Cleaning captions", runner.run_clean, wf,
                     body.course, body.speaker, body.use_ai, body.use_batch,
                     body.engine)
    return job.as_dict()


@app.get("/api/flags")
def flags():
    return {"files": runner.read_flaglogs(_wf())}


@app.post("/api/flags")
def save_flags(body: SaveFlagsIn):
    try:
        runner.write_flaglog_entries(_wf(), body.file, body.entries)
    except FileNotFoundError:
        raise HTTPException(404, f"No such flag log: {body.file}")
    return {"ok": True}


@app.post("/api/apply")
def apply_flags():
    wf = _wf()
    if jobs.busy():
        raise HTTPException(409, "Another step is still running.")
    return jobs.start("Applying corrections", runner.run_apply_flaglog, wf).as_dict()


@app.post("/api/publish")
def publish(body: PublishIn):
    wf = _wf()
    if not (body.html or body.docx):
        raise HTTPException(400, "Choose at least one output: web page or Word document.")
    if body.docx:
        from pipeline.docx_publish import docx_available
        if not docx_available():
            raise HTTPException(400, "Word output isn't installed yet. Close the app and "
                                     "open it again with 4_Open_App (it installs it once; "
                                     "needs internet).")
    _require_key_if_ai(body.ai_headings, body.engine)
    if jobs.busy():
        raise HTTPException(409, "Another step is still running.")
    job = jobs.start("Publishing transcripts", runner.run_publish, wf,
                     body.ai_headings, body.delete_working, body.use_batch,
                     body.engine,
                     "both" if body.html and body.docx else "docx" if body.docx else "html")
    return job.as_dict()


# --- Side-by-side review window ---------------------------------------------

class ApplyFlagIn(BaseModel):
    file: str
    entry: int
    found: str
    text: str


# Set by gui/main.py: tells the main window to reload when the review window
# changes something, so it updates straight away.
notify_main = None

def _notify_main():
    if notify_main:
        import threading
        threading.Thread(target=notify_main, daemon=True).start()


class EditIn(BaseModel):
    file: str
    entry: int
    old: str
    new: str


class FindIn(BaseModel):
    file: str
    find: str
    replace: str = ""
    match_case: bool = False
    whole_word: bool = True


class UndoIn(BaseModel):
    file: str
    correction_id: int


@app.get("/review")
def review_page():
    return FileResponse(HERE / "review.html")


@app.get("/api/review")
def review_data(file: str):
    try:
        return review.load_review(_wf(), file)
    except FileNotFoundError:
        raise HTTPException(404, f"No pending flag log called {file}")
    except review.ReviewError as e:
        raise HTTPException(400, str(e))


@app.post("/api/review/undo")
def review_undo(body: UndoIn):
    if jobs.busy():
        raise HTTPException(409, "Another step is still running - try again in a moment.")
    try:
        result = review.undo_correction(_wf(), body.file, body.correction_id)
        _notify_main()
        return result
    except FileNotFoundError:
        raise HTTPException(404, f"No pending flag log called {body.file}")
    except review.ReviewError as e:
        raise HTTPException(400, str(e))


def _review_call(fn, *args, change=True):
    if change and jobs.busy():
        raise HTTPException(409, "Another step is still running - try again in a moment.")
    try:
        result = fn(_wf(), *args)
    except FileNotFoundError as e:
        raise HTTPException(404, f"No pending flag log called {e}")
    except review.ReviewError as e:
        raise HTTPException(400, str(e))
    if change:
        _notify_main()
    return result


@app.post("/api/review/edit")
def review_edit(body: EditIn):
    return _review_call(review.edit_entry, body.file, body.entry, body.old, body.new)


@app.post("/api/review/find")
def review_find(body: FindIn):
    return _review_call(review.find_matches, body.file, body.find,
                        body.match_case, body.whole_word, change=False)


@app.post("/api/review/replace")
def review_replace(body: FindIn):
    return _review_call(review.replace_all, body.file, body.find, body.replace,
                        body.match_case, body.whole_word)


@app.post("/api/review/apply")
def review_apply(body: ApplyFlagIn):
    if jobs.busy():
        raise HTTPException(409, "Another step is still running - try again in a moment.")
    try:
        result = review.apply_flag(_wf(), body.file, body.entry, body.found, body.text)
    except FileNotFoundError:
        raise HTTPException(404, f"No pending flag log called {body.file}")
    except review.ReviewError as e:
        raise HTTPException(400, str(e))
    _notify_main()
    return result


@app.get("/api/job/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "No such job")
    return job.as_dict()


@app.get("/api/transcripts")
def transcripts():
    wf = _wf()
    d, w = wf / "HTML_Transcripts", wf / "Word_Transcripts"
    from pipeline.docx_publish import docx_available
    return {"files": sorted(p.name for p in d.glob("*.html")) if d.is_dir() else [],
            "docx": sorted(p.name for p in w.glob("*.docx")) if w.is_dir() else [],
            "docx_ready": docx_available()}


class OpenIn(BaseModel):
    folder: str
    name: str = ""


@app.post("/api/open")
def open_in_finder(body: OpenIn):
    """Open a Word transcript (in Word/Pages) or show its folder in Finder."""
    import subprocess, sys as _sys
    if body.folder not in ("Word_Transcripts", "HTML_Transcripts"):
        raise HTTPException(400, "Unknown folder")
    base = (_wf() / body.folder).resolve()
    target = (base / body.name).resolve() if body.name else base
    if target != base and target.parent != base or not target.exists():
        raise HTTPException(404, "Not found")
    if _sys.platform == "darwin":
        subprocess.Popen(["open", str(target)])
    elif _sys.platform.startswith("win"):
        os.startfile(str(target))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(target)])
    return {"ok": True}


@app.get("/api/transcript/{name}")
def transcript(name: str):
    wf = _wf()
    p = (wf / "HTML_Transcripts" / name).resolve()
    # Path containment check -- never serve outside the transcripts folder.
    if not str(p).startswith(str((wf / "HTML_Transcripts").resolve())) or not p.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(p)
