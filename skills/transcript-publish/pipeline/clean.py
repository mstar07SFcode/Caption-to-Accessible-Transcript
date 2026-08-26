"""Deterministic cleanup — the rule-based transformations that need no LLM.

Per Caption_Cleanup_Rules.md, the only fully deterministic text edits are:
  1. Strip the auto-generated transcript header line.
  2. Global filler removal: um, uh, ah, er (and elongated variants).
  3. Consecutive punctuation collapse (Rule 1c): runs of .,?! reduced to one mark.
  4. Captioner marker normalization (Rule 1d): [unrecognized] and friends ->
     [unintelligible], with spacing and possessives repaired.

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


# Markers the auto-captioner itself emits where it could not transcribe a word.
# Panopto uses [unrecognized]; other engines use [inaudible]/[unclear]/[?].
# All are normalized to the project's single marker (Rule 1d).
_CAPTIONER_MARKER_RE = re.compile(
    r"\[\s*(?:unrecognized|unrecognised|inaudible|indiscernible|unclear|unintelligible|\?+)\s*\]",
    re.IGNORECASE)

MARKER = "[unintelligible]"


def normalize_captioner_markers(text: str) -> str:
    """Normalize auto-captioner 'could not transcribe' markers to MARKER.

    Rule 1d. The source engine's own marker (e.g. Panopto's [unrecognized]) is
    a statement that the recognizer failed, which is the same thing the project
    marker says — so it is normalized rather than passed through, keeping one
    marker in front of students.

    Also repairs the two defects these markers arrive with, both of which make
    screen readers run words together:
      * missing whitespace either side  ("pays[unrecognized]for" )
      * a bare possessive 's'           ("[unrecognized]s 2027"  )

    This is deterministic and runs before the AI sees the cues, so judgment
    never needs to flag or correct these.
    """
    text = _CAPTIONER_MARKER_RE.sub(MARKER, text)
    if MARKER not in text:
        return text
    esc = re.escape(MARKER)
    # Possessive: "[unintelligible]s word" -> "[unintelligible]'s word"
    text = re.sub(esc + r"s\b", MARKER + "'s", text)
    # Separate the marker from adjacent word characters on either side.
    text = re.sub(r"(?<=[\w,.])" + esc, " " + MARKER, text)
    text = re.sub(esc + r"(?=[\w])", MARKER + " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"\s+([,.;:!?])", r"\1", text)


def collapse_punctuation(text: str) -> str:
    """Collapse any run of consecutive punctuation marks (.,?!) to a single mark.

    Rule 1c: same mark repeated → one; mixed adjacent marks → terminal (. ? !)
    beats comma; among terminals keep the first. Intentional ellipses (...) are
    preserved. Running this before AI judgment means the AI never sees doubled
    punctuation and won't waste flags on it.
    """
    text = text.replace('...', '\x00')
    def _pick(m: re.Match) -> str:
        for ch in m.group(0):
            if ch in '.?!':
                return ch
        return ','
    text = re.sub(r'[.,?!]{2,}', _pick, text)
    return text.replace('\x00', '...')


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
    stripped.text = collapse_punctuation(stripped.text)
    stripped.text = normalize_captioner_markers(stripped.text)
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
