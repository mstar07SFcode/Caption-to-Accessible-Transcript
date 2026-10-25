"""Flag log writer + applier.

Writer: produces the FlagLog_<stem>.txt format (no `Cleaned:` date line).
Applier (Step 1b): pure string find/replace — no LLM. Parses the reviewed log,
applies each remaining entry's `Possible:` text over its `Found:` text in the
VTT, skips listen-only notes, and reports applied/skipped/unmatched.

Replacements are SCOPED TO THE FLAGGED ENTRY, matching apply.apply_cleanup.
A document-wide replace would silently rewrite an earlier, unrelated cue that
happens to contain the same phrase. The applier edits only the text lines
belonging to the flagged entry number and leaves every other byte of the file —
header, NOTE blocks, entry numbers, timecodes — untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RULE = "─" * 62

# Phrases in `Possible:` that mean "no actionable replacement" -> skip on apply.
_LISTEN_ONLY = re.compile(
    r"^\s*(listen to verify|unknown\b|unclear\b|could not|n/?a)\b",
    re.IGNORECASE,
)


def is_listen_only(text: str) -> bool:
    """True when a suggestion is a note ("Listen to verify") rather than wording."""
    return not (text or "").strip() or bool(_LISTEN_ONLY.match(text))


def editable_possible(found: str, possible: str) -> str:
    """The text to put in a flag's 'Replace with' box: the AI's suggested
    wording, or an empty string when it only left a note such as "Listen to
    verify". The box then shows a light placeholder instead, so that note text
    can never end up in the captions. (`found` is kept for call compatibility.)"""
    if is_listen_only(possible) or possible.strip() == (found or "").strip():
        return ""   # a "suggestion" that repeats the line is no suggestion
    return possible


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


# A cue block is: an entry-number line, a timecode line, then its text lines.
_ENTRY_NUM_LINE_RE = re.compile(r"^\s*(\d+)\s*$")


def entry_text_spans(vtt_text: str) -> dict[int, tuple[int, int]]:
    """Map each entry number to the [start, end) line span holding its text.

    Only lines inside a returned span are eligible for replacement, which is
    what keeps a correction flagged at entry 40 from rewriting entry 3.
    """
    lines = vtt_text.split("\n")
    spans: dict[int, tuple[int, int]] = {}
    i, n = 0, len(lines)
    while i < n:
        m = _ENTRY_NUM_LINE_RE.match(lines[i])
        if m and i + 1 < n and "-->" in lines[i + 1]:
            start = i + 2
            j = start
            while j < n and lines[j].strip() != "":
                j += 1
            spans.setdefault(int(m.group(1)), (start, j))
            i = j
        else:
            i += 1
    return spans


def apply_flaglog(vtt_text: str, flaglog_text: str) -> ApplyResult:
    """Apply reviewed corrections to the VTT text by exact string replacement.

    A replacement is applied only if the `Found:` text appears verbatim in the
    text of the flagged entry and the `Possible:` text is an actionable
    replacement (not a listen-only note). Entry numbers, timecodes, and every
    other entry are untouched.
    """
    reviews = parse_flaglog(flaglog_text)
    applied, skipped, unmatched = [], [], []

    lines = vtt_text.split("\n")
    spans = entry_text_spans(vtt_text)
    # Accumulate edits per entry, then splice once so spans stay valid.
    edited: dict[int, list[str]] = {}

    for r in reviews:
        if r.possible.strip() == r.found.strip() and r.found:
            skipped.append((r.entry, "(left as is)"))
            continue
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
        block = "\n".join(edited.get(r.entry, lines[start:end]))
        if r.found in block:
            edited[r.entry] = block.replace(r.found, r.possible, 1).split("\n")
            applied.append((r.entry, r.found, r.possible))
        else:
            unmatched.append((r.entry, r.found))

    # Splice back in reverse start order so earlier spans keep their indices.
    for entry in sorted(edited, key=lambda e: spans[e][0], reverse=True):
        start, end = spans[entry]
        lines[start:end] = edited[entry]

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
