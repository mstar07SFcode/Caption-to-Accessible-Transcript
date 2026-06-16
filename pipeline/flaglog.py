"""Flag log writer + applier.

Writer: produces the FlagLog_<stem>.txt format (no `Cleaned:` date line).
Applier (Step 1b): pure string find/replace — no LLM. Parses the reviewed log,
applies each remaining entry's `Possible:` text over its `Found:` text in the
VTT, skips listen-only notes, and reports applied/skipped/unmatched.
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
    out.append("ENTRIES REQUIRING HUMAN REVIEW")
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
    n = len(reviews)
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


def apply_flaglog(vtt_text: str, flaglog_text: str) -> ApplyResult:
    """Apply reviewed corrections to the VTT text by exact string replacement.

    A replacement is applied only if the `Found:` text appears verbatim in the
    VTT and the `Possible:` text is an actionable replacement (not a listen-only
    note). Entry numbers and timecodes are untouched.
    """
    reviews = parse_flaglog(flaglog_text)
    applied, skipped, unmatched = [], [], []
    text = vtt_text

    for r in reviews:
        if not r.possible or _LISTEN_ONLY.match(r.possible):
            skipped.append((r.entry, r.possible or "(no replacement)"))
            continue
        if not r.found:
            skipped.append((r.entry, "(no Found text)"))
            continue
        if r.found in text:
            text = text.replace(r.found, r.possible, 1)
            applied.append((r.entry, r.found, r.possible))
        else:
            unmatched.append((r.entry, r.found))

    return ApplyResult(applied=applied, skipped=skipped,
                       unmatched=unmatched, new_vtt_text=text)


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
