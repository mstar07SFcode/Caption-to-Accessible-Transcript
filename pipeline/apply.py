"""Apply a CleanupJudgment to cues deterministically.

The LLM proposes corrections (string find/replace scoped to an entry) and flags
(left untouched in the text, written to the flag log). This module applies the
corrections and turns flags into ReviewEntry objects. It performs NO judgment of
its own — only mechanical application of the JSON.

Note: consecutive-punctuation collapse (Rule 1c) runs in clean.py BEFORE the
AI sees the cues, so the AI never flags doubled punctuation and corrections
cannot reintroduce it in practice.
"""

from __future__ import annotations

from .parse import Cue
from .clean import normalize_captioner_markers
from .judgment import CleanupJudgment
from .flaglog import Correction, ReviewEntry


def apply_cleanup(cues: list[Cue], judgment: CleanupJudgment
                  ) -> tuple[list[Cue], list[Correction], list[ReviewEntry]]:
    by_index = {c.index: c for c in cues}
    corrections: list[Correction] = []

    for corr in judgment.corrections:
        entry = corr.get("entry")
        find = corr.get("find")
        replace = corr.get("replace")
        cue = by_index.get(entry)
        if cue is None or find is None or replace is None:
            continue
        if find in cue.text:
            cue.text = cue.text.replace(find, replace, 1)
            reason = corr.get("reason", "recognition correction")
            corrections.append(Correction(
                entry=entry, description=f"'{find}' → '{replace}' — {reason}"))
        # If the find text isn't present, silently skip (judgment may be stale).

    reviews: list[ReviewEntry] = []
    for flag in judgment.flags:
        entry = flag.get("entry")
        cue = by_index.get(entry)
        timecode = flag.get("timecode") or (_mmss(cue.start) if cue else "")
        reviews.append(ReviewEntry(
            entry=entry,
            timecode=timecode,
            found=flag.get("found", cue.text if cue else ""),
            issue=flag.get("issue", ""),
            possible=flag.get("possible", ""),
        ))

    # The rules are stated to the AI, but a rule only the AI enforces is a rule
    # that holds most of the time. These two run afterwards, deterministically.
    _lowercase_after_comma(cues, corrections)
    for cue in cues:
        # Rule 1d. normalize_captioner_markers runs in the deterministic pass
        # BEFORE the AI sees the cues, so a marker the AI introduces in a
        # replacement used to survive. The rules text names Panopto's
        # [unrecognized] eight times while asking for [unintelligible], so it
        # is the form the model reaches for. Normalize again here.
        cue.text = normalize_captioner_markers(cue.text)

    return cues, corrections, reviews


# Common words that, after a comma, are always mid-sentence and so lowercase.
# Anything not listed (names, "I", product names) is left exactly as it is.
_COMMON_STARTERS = frozenset("""
a about after all also an and any are as at be because been before both but by
can could did do does each even every for from had has have he her here his how
if in into is it it's its just let let's like maybe more most my no nor not now
of on once one only or our out over she should since so some such than that
that's the their them then there there's these they they're this those though
to too under until up us very was we we'd we'll we're we've were what what's
when where whether which while who why will with would yet you you'll you're
your
""".split())


def _lowercase_after_comma(cues: list[Cue], corrections: list[Correction]) -> None:
    """If a cue ends with a comma the sentence continues, so a capitalized
    COMMON first word in the next cue is lowercased and logged as a correction.

    No AI: this is the mechanical half of the continuation rule that
    Caption_Cleanup_Rules.md calls the single most common cleanup miss. Only
    words in _COMMON_STARTERS are touched, so a name, "I", or a case name at
    the start of a continuing cue is left exactly as it is.
    """
    for prev, cur in zip(cues, cues[1:]):
        if not prev.text.rstrip().endswith(","):
            continue
        text = cur.text
        first = text.split(maxsplit=1)[0] if text.strip() else ""
        if not first or not first[0].isupper():
            continue
        bare = first.rstrip(",.?!;:")
        if bare.lower() not in _COMMON_STARTERS:
            continue
        low = bare[0].lower() + bare[1:]
        cur.text = low + text[len(bare):]
        corrections.append(Correction(
            entry=cur.index,
            description=f"'{bare}' → '{low}' — Automatic: the previous entry ends "
                        f"with a comma, so the sentence continues"))


def _mmss(vtt_timecode: str) -> str:
    """HH:MM:SS.mmm -> MM:SS (or HH:MM:SS if >= 1h) for flag-log display."""
    try:
        h, m, rest = vtt_timecode.split(":")
        s = rest.split(".")[0]
        if int(h) > 0:
            return f"{int(h)}:{int(m):02d}:{int(s):02d}"
        return f"{int(m):02d}:{int(s):02d}"
    except Exception:
        return vtt_timecode
