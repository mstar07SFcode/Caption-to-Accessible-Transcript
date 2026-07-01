"""Deterministic cleanup — the rule-based transformations that need no LLM.

Per Caption_Cleanup_Rules.md, the only fully deterministic text edits are:
  1. Strip the auto-generated transcript header line.
  2. Global filler removal: um, uh, ah, er (and elongated variants).

Everything else (recognition corrections, punctuation across entries,
capitalization, possessives, flagging) is judgment and lives in judgment.py.
Doubled words are deliberately PRESERVED here — they are cleaned at publish.
"""

from __future__ import annotations

import re

from .parse import Cue, strip_autogen_header

# Standalone hesitation tokens, including elongated forms (umm, uhh, ahh, err).
# \b boundaries keep us from touching real words ("ah" in "aha" is safe; a bare
# "ah" token is removed). Case-insensitive.
_FILLER_RE = re.compile(r"\b(?:u[mh]+|ah+|er+)\b", re.IGNORECASE)


def remove_fillers(text: str) -> str:
    """Remove standalone filler tokens and tidy the resulting whitespace.

    Preserves so / you know / I mean / right / well (Rule 2) because those are
    not in the filler set. Does not remove fillers embedded in words.
    """
    # Remove "<filler>," or "<filler>" plus surrounding spaces.
    out = _FILLER_RE.sub("", text)
    # Collapse spaces created by removal.
    out = re.sub(r"[ \t]{2,}", " ", out)
    # Fix " ," / " ." spacing artifacts and stray leading punctuation.
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    out = re.sub(r"^[ \t]*[,;:]\s*", "", out)  # orphaned leading comma
    # Trim each line.
    out = "\n".join(line.strip() for line in out.split("\n"))
    return out.strip()


def clean_cue(cue: Cue) -> Cue | None:
    """Apply deterministic cleanup to one cue. Returns None if it empties out
    (e.g. a cue that contained only the auto-generated header)."""
    stripped = strip_autogen_header(cue)
    if stripped is None:
        return None
    stripped.text = remove_fillers(stripped.text)
    if not stripped.text.strip():
        return None
    return stripped


def clean_cues(cues: list[Cue]) -> list[Cue]:
    """Deterministic pass over all cues. Entry numbers and timecodes are never
    changed; a cue that becomes empty is dropped but later cues keep their
    original numbers (verbatim standard preserves source numbering)."""
    out: list[Cue] = []
    for cue in cues:
        cleaned = clean_cue(cue)
        if cleaned is not None:
            out.append(cleaned)
    return out
