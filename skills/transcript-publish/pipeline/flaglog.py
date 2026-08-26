"""Flag log writer + applier.

Writer: produces the FlagLog_<stem>.txt format (no `Cleaned:` date line).
Applier (Step 1b): pure string find/replace — no LLM. Parses the reviewed log,
applies each remaining entry's `Possible:` text over its `Found:` text **inside
the cue that entry names**, skips listen-only notes, and reports
applied/skipped/unmatched. Scoping each replacement to its own entry mirrors
apply_cleanup; a whole-file replace would let a phrase flagged at one entry
rewrite an earlier one that happens to contain the same words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .parse import TIMECODE_RE

RULE = "─" * 62

# Phrases in `Possible:` that mean "no actionable replacement" -> skip on apply.
_LISTEN_ONLY = re.compile(
    r"^\s*(listen to verify|unknown\b|unclear\b|could not|n/?a)\b",
    re.IGNORECASE,
)


@dataclass
class Correction:
    entry: int
    description: str  # human-readable line for Corrections Applied


@dataclass
class ReviewEntry:
    entry: int
    timecode: str
    found: str
    issue: str
    possible: str


def write_flaglog(source_filename: str,
                  corrections: list[Correction],
                  reviews: list[ReviewEntry]) -> str:
    out: list[str] = []
    out.append("CAPTION CLEANUP FLAG LOG")
    out.append(f"File: {source_filename}")
    out.append(RULE)
    out.append("")
    out.append("CORRECTIONS APPLIED")
    out.append("These corrections were applied with ≥90% confidence.")
    out.append("")
    if corrections:
        for c in corrections:
            out.append(f"  • Entry {c.entry}: {c.description}")
    else:
        out.append("  (none)")
    out.append("")
    out.append(RULE)
    out.append("")
    n = len(reviews)
    out.append(f"ENTRIES REQUIRING HUMAN REVIEW  ({n} {'entry' if n == 1 else 'entries'})")
    out.append("These entries contain likely auto-caption errors that could not be")
    out.append("corrected with confidence. Please listen to the video and correct")
    out.append("the cleaned file as needed.")
    out.append("")
    if reviews:
        for r in reviews:
            out.append(f"Entry {r.entry} | {r.timecode}")
            out.append(f'  Found:    "{r.found}"')
            out.append(f"  Issue:    {r.issue}")
            out.append(f'  Possible: "{r.possible}"')
            out.append("")
    else:
        out.append("  (none)")
        out.append("")
    out.append(RULE)
    out.append(f"{n} {'entry requires' if n == 1 else 'entries require'} review.")
    return "\n".join(out) + "\n"


# ---- Parsing a (possibly user-edited) flag log ----------------------------

_ENTRY_HEADER_RE = re.compile(r"^Entry\s+(\d+)\s*\|\s*(.+)$")
_FOUND_RE = re.compile(r'^\s*Found:\s*"(.*)"\s*$')
_ISSUE_RE = re.compile(r"^\s*Issue:\s*(.*)$")
_POSSIBLE_RE = re.compile(r'^\s*Possible:\s*"?(.*?)"?\s*$')


def parse_flaglog(text: str) -> list[ReviewEntry]:
    """Extract the review entries that remain in a (reviewed) flag log."""
    text = text.replace("\r\n", "\n")
    # Only look at the "ENTRIES REQUIRING HUMAN REVIEW" portion.
    parts = re.split(r"ENTRIES REQUIRING HUMAN REVIEW", text, maxsplit=1)
    region = parts[1] if len(parts) == 2 else text

    entries: list[ReviewEntry] = []
    cur: dict | None = None
    for line in region.split("\n"):
        m = _ENTRY_HEADER_RE.match(line.strip())
        if m:
            if cur:
                entries.append(_finish(cur))
            cur = {"entry": int(m.group(1)), "timecode": m.group(2).strip(),
                   "found": "", "issue": "", "possible": ""}
            continue
        if cur is None:
            continue
        mf = _FOUND_RE.match(line)
        if mf:
            cur["found"] = mf.group(1)
            continue
        mi = _ISSUE_RE.match(line)
        if mi:
            cur["issue"] = mi.group(1).strip()
            continue
        mp = _POSSIBLE_RE.match(line)
        if mp:
            cur["possible"] = mp.group(1).strip()
            continue
    if cur:
        entries.append(_finish(cur))
    return entries


def _finish(d: dict) -> ReviewEntry:
    return ReviewEntry(entry=d["entry"], timecode=d["timecode"],
                       found=d["found"], issue=d["issue"], possible=d["possible"])


# ---- Applying the reviewed log to the VTT ---------------------------------

@dataclass
class ApplyResult:
    applied: list[tuple[int, str, str]]      # (entry, found, possible)
    skipped: list[tuple[int, str]]           # (entry, reason/possible)
    unmatched: list[tuple[int, str]]         # (entry, found)
    new_vtt_text: str


def _cue_text_line_spans(vtt_text: str) -> dict[int, tuple[int, int]]:
    """Map each cue's entry number -> [start, end) line range of its TEXT lines.

    Walks the file's own lines rather than re-serializing it, so everything
    that is not a cue's text — the WEBVTT line, the metadata header, NOTE
    blocks, blank-line spacing, entry numbers and timecodes — keeps its exact
    original bytes. Cue blocks are recognized the way parse_srt recognizes
    them: a timecode line, optionally preceded by a numeric index line.
    """
    lines = vtt_text.split("\n")
    spans: dict[int, tuple[int, int]] = {}
    fallback_index = 0
    i = 0
    while i < len(lines):
        if not TIMECODE_RE.search(lines[i]):
            i += 1
            continue
        # Numeric line immediately above the timecode is the entry number.
        idx = None
        if i >= 1 and lines[i - 1].strip().isdigit():
            idx = int(lines[i - 1].strip())
        fallback_index += 1
        entry = idx if idx is not None else fallback_index
        # Text runs from the line after the timecode to the next blank line.
        start = i + 1
        end = start
        while end < len(lines) and lines[end].strip() != "":
            end += 1
        # First span wins if a file somehow repeats an entry number.
        spans.setdefault(entry, (start, end))
        i = end
    return spans


def apply_flaglog(vtt_text: str, flaglog_text: str) -> ApplyResult:
    """Apply reviewed corrections to the VTT, each scoped to its flagged entry.

    A replacement is applied only if the `Possible:` text is actionable (not a
    listen-only note) and the `Found:` text appears **within the cue the flag
    log names**. A phrase flagged at entry 40 can therefore never rewrite entry
    3, the metadata header, or a NOTE block; if the text is not in entry 40 it
    is reported as unmatched, not applied elsewhere.

    Only the matched cue's own text lines are rewritten. Entry numbers,
    timecodes, header metadata, NOTE blocks and blank-line spacing keep their
    exact original bytes.
    """
    reviews = parse_flaglog(flaglog_text)
    applied, skipped, unmatched = [], [], []
    lines = vtt_text.split("\n")
    spans = _cue_text_line_spans(vtt_text)

    for r in reviews:
        if not r.possible or _LISTEN_ONLY.match(r.possible):
            skipped.append((r.entry, r.possible or "(no replacement)"))
            continue
        if not r.found:
            skipped.append((r.entry, "(no Found text)"))
            continue
        span = spans.get(r.entry)
        if span is None:
            unmatched.append((r.entry, r.found))
            continue

        start, end = span
        cue_text = "\n".join(lines[start:end])
        if r.found in cue_text:
            new_text = cue_text.replace(r.found, r.possible, 1)
        else:
            # A flag log's Found: is written on one line, so a cue whose text
            # wraps across lines cannot match verbatim. Retry against the cue
            # collapsed to a single line; on success the cue becomes one line.
            collapsed = " ".join(cue_text.split())
            if "\n" in cue_text and r.found in collapsed:
                new_text = collapsed.replace(r.found, r.possible, 1)
            else:
                unmatched.append((r.entry, r.found))
                continue

        lines[start:end] = new_text.split("\n")
        # Later spans shift if the cue's line count changed.
        delta = len(new_text.split("\n")) - (end - start)
        if delta:
            spans = {e: (s + delta, t + delta) if s >= end else (s, t)
                     for e, (s, t) in spans.items()}
        applied.append((r.entry, r.found, r.possible))

    return ApplyResult(applied=applied, skipped=skipped,
                       unmatched=unmatched, new_vtt_text="\n".join(lines))


def format_apply_report(filename: str, result: ApplyResult,
                        archived_log_name: str, vtt_path: str) -> str:
    out = [f"Applied flag log corrections to: {filename}", ""]
    out.append(f"Applied ({len(result.applied)}):")
    for entry, found, possible in result.applied:
        out.append(f'  Entry {entry} — "{found}" → "{possible}"')
    out.append("")
    out.append(f"Skipped — no actionable replacement ({len(result.skipped)}):")
    for entry, reason in result.skipped:
        out.append(f'  Entry {entry} — "{reason}"')
    out.append("")
    out.append(f"Unmatched — text not found in VTT ({len(result.unmatched)}):")
    for entry, found in result.unmatched:
        out.append(f'  Entry {entry} — "{found}"')
    out.append("")
    out.append(f"Flag log archived as: {archived_log_name}")
    out.append(f"Updated file: {vtt_path}")
    return "\n".join(out) + "\n"
