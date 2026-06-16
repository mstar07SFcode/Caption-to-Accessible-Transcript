"""Filesystem operations: scanning, archiving, mirroring, cleanup.

Path-based so the same functions serve local folders and per-job server dirs.
No deletion is forced here beyond what the workflow specifies; callers decide.
"""

from __future__ import annotations

import shutil
from pathlib import Path

SOURCE_EXTS = (".srt", ".txt")


def scan_sources(raw_dir: Path) -> list[Path]:
    """All caption source files in raw_dir and its subfolders."""
    out: list[Path] = []
    for p in sorted(raw_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in SOURCE_EXTS:
            out.append(p)
    return out


def subfolder_of(path: Path, root: Path) -> str | None:
    """Immediate subfolder name of `path` under `root`, or None if at top."""
    rel = path.relative_to(root)
    return rel.parts[0] if len(rel.parts) > 1 else None


def archive_source(src: Path, raw_root: Path, archive_root: Path) -> Path:
    """Move a source file to the archive, mirroring its subfolder structure."""
    rel = src.relative_to(raw_root)
    dest = archive_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    return dest


def prune_empty_dirs(root: Path) -> None:
    """Remove now-empty subdirectories under root (root itself is kept)."""
    for p in sorted(root.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        if p.is_dir() and not any(p.iterdir()):
            p.rmdir()


def empty_directory(target: Path) -> list[str]:
    """Delete all contents of `target` but keep the directory itself.

    Used by Transcript Publish to clear Archived_Captions at the start of a run.
    Returns the list of removed top-level names.
    """
    removed: list[str] = []
    if not target.exists():
        return removed
    for child in sorted(target.iterdir()):
        if child.name == ".DS_Store":
            child.unlink(missing_ok=True)
            continue
        removed.append(child.name)
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    return removed
