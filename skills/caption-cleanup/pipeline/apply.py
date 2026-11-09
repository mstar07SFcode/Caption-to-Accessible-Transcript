"""Apply a CleanupJudgment to cues deterministically.

The LLM proposes corrections (string find/replace scoped to an entry) and flags.
This module applies the corrections, and applies any flag that carries an actual
replacement in its `possible` field, logging it under Corrections Applied. Flags
whose `possible` is a "Listen to verify" note become ReviewEntry objects, so the
review section holds only what a human has to check against the audio. It
performs NO judgment of its own — only mechanical application of the JSON.

Note: consecutive-punctuation collapse (Rule 1c) runs in clean.py BEFORE the
AI sees the cues, so the AI never flags doubled punctuation and corrections
cannot reintroduce it in practice.
"""

from __future__ import annotations

from .parse import Cue
from .clean import normalize_captioner_markers
from .judgment import CleanupJudgment
from .flaglog import Correction, ReviewEntry, editable_possible


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
        found = flag.get("found", cue.text if cue else "")
        issue = flag.get("issue", "")
        possible = flag.get("possible", "")

        # A flag that carries a real replacement is applied here, like a
        # correction, and reported under Corrections Applied -- it is no longer
        # held back for the reviewer to apply by hand. editable_possible()
        # returns "" for the cases that are not a replacement at all: a
        # "Listen to verify" note, an empty suggestion, or one that merely
        # repeats the found text. Those still go to the review section, so what
        # remains there is only what a human has to listen to.
        replacement = editable_possible(found, possible)
        if cue is not None and found and replacement:
            if _replace_in_cue(cue, found, replacement):
                corrections.append(Correction(
                    entry=entry,
                    description=f"'{found}' \u2192 '{replacement}' \u2014 Suggested"
                                + (f": {issue}" if issue else "")))
                continue
            # The found text is not in the cue -- a stale judgment, or an
            # earlier correction already rewrote that span. Leave it for review
            # rather than guessing where the replacement was meant to go.

        reviews.append(ReviewEntry(
            entry=entry,
            timecode=timecode,
            found=found,
            issue=issue,
            possible=possible,
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


def _replace_in_cue(cue: Cue, found: str, replacement: str) -> bool:
    """Replace `found` with `replacement` inside one cue's text.

    A flag's `found` is written on a single line, so a cue whose text wraps
    across lines cannot match it verbatim. Retry against the cue collapsed to
    one line -- the same fallback apply_flaglog uses for a reviewed log. Returns
    False when the text is not in the cue at all, leaving the cue untouched.
    """
    if found in cue.text:
        cue.text = cue.text.replace(found, replacement, 1)
        return True
    collapsed = " ".join(cue.text.split())
    if "\n" in cue.text and found in collapsed:
        cue.text = collapsed.replace(found, replacement, 1)
        return True
    return False


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
