"""Apply a CleanupJudgment to cues deterministically.

The LLM proposes corrections (string find/replace scoped to an entry) and flags
(left untouched in the text, written to the flag log). This module applies the
corrections and turns flags into ReviewEntry objects. It performs NO judgment of
its own — only mechanical application of the JSON.
"""

from __future__ import annotations

from .parse import Cue
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

    return cues, corrections, reviews


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
