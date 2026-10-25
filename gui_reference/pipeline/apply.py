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
        if find == replace:
            continue  # a "fix" that changes nothing is noise; never record it
        if find in cue.text:
            cue.text = cue.text.replace(find, replace, 1)
            reason = corr.get("reason", "recognition correction")
            corrections.append(Correction(
                entry=entry, description=f"'{find}' → '{replace}' — {reason}"))
        # If the find text isn't present, silently skip (judgment may be stale).

    lowered = _lowercase_after_comma(cues, corrections)

    reviews: list[ReviewEntry] = []
    for flag in judgment.flags:
        if flag.get("entry") in lowered:
            word, low = lowered[flag.get("entry")]
            for key in ("found", "possible"):
                v = flag.get(key) or ""
                if v.startswith(word + " ") or v == word:
                    flag = dict(flag, **{key: low + v[len(word):]})
        entry = flag.get("entry")
        cue = by_index.get(entry)
        # A flag on a line a correction already changed: drop it when the
        # suggestion is already in place, otherwise point it at the CURRENT text
        # so the reviewer edits (and Apply finds) what is really in the file.
        if cue is not None:
            found_now = flag.get("found", cue.text)
            if found_now and found_now not in cue.text:
                possible = (flag.get("possible") or "").strip()
                if possible and possible in cue.text:
                    continue
                flag = dict(flag, found=cue.text)
        timecode = flag.get("timecode") or (_mmss(cue.start) if cue else "")
        reviews.append(ReviewEntry(
            entry=entry,
            timecode=timecode,
            found=flag.get("found", cue.text if cue else ""),
            issue=flag.get("issue", ""),
            possible=editable_possible(
                flag.get("found", cue.text if cue else ""), flag.get("possible", "")),
        ))

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


def _lowercase_after_comma(cues: list[Cue], corrections: list[Correction]
                           ) -> dict[int, tuple[str, str]]:
    """Safety net (no AI): if a cue ends with a comma, the next cue continues the
    sentence, so a capitalized COMMON first word is lowercased and logged as a
    correction. Returns {entry: (old_word, new_word)} for the cues changed."""
    changed: dict[int, tuple[str, str]] = {}
    for prev, cur in zip(cues, cues[1:]):
        if not prev.text.rstrip().endswith(","):
            continue
        text = cur.text
        first = text.split(maxsplit=1)[0] if text.strip() else ""
        if not first or not first[0].isupper() or first[:1] == "I" and first.rstrip(",.?!;:") in (
                "I", "I'm", "I've", "I'll", "I'd"):
            continue
        bare = first.rstrip(",.?!;:")
        if bare.lower() not in _COMMON_STARTERS:
            continue
        low = bare[0].lower() + bare[1:]
        cur.text = low + text[len(bare):]
        changed[cur.index] = (bare, low)
        corrections.append(Correction(
            entry=cur.index,
            description=f"'{bare}' → '{low}' — Automatic: the previous entry ends "
                        f"with a comma, so the sentence continues"))
    return changed


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
