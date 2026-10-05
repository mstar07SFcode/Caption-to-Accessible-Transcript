"""The judgment interface — the portability key.

The pipeline never makes editorial decisions itself. It hands cue text to a
JudgmentBackend and receives a strict JSON-shaped result, which apply.py then
applies deterministically. Two real backends fill this contract:

  * local  -> a Claude sub-agent writes the JSON to a temp file (wired in the
              skill layer; not imported here so this module stays dependency-free)
  * server -> an Anthropic API call returns the JSON (api_backend.py)

A StubBackend is provided so the deterministic pipeline can be exercised and
tested with no LLM at all.

JSON contract
-------------
Cleanup judgment:
  {
    "corrections": [
      {"entry": 4, "find": "a greater a risk", "replace": "a greater risk",
       "reason": "extra article removed", "confidence": "high"}
    ],
    "flags": [
      {"entry": 40, "timecode": "00:04:11", "found": "...", "issue": "...",
       "possible": "..."}
    ]
  }

Publish judgment:
  {
    "title": "Transcript MSAS-603 M2 Audit Risk",
    "sections": [{"level": 2, "title": "Introduction", "start_entry": 1}],
    "paragraph_breaks": [1, 7, 14],
    "doubled_words": [{"entry": 9, "find": "the the", "replace": "the"}],
    "speaker_turns": [{"entry": 5, "speaker": "Dr. Smith"}],
    "non_speech": [{"entry": 12, "description": "Applause"}]
  }
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol

from .parse import Cue, timecode_to_seconds


# ---- Result containers -----------------------------------------------------

@dataclass
class CleanupJudgment:
    corrections: list[dict] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict | str) -> "CleanupJudgment":
        if isinstance(data, str):
            data = json.loads(data)
        return cls(corrections=data.get("corrections", []),
                   flags=data.get("flags", []))


@dataclass
class PublishJudgment:
    title: str = ""
    sections: list[dict] = field(default_factory=list)
    paragraph_breaks: list[int] = field(default_factory=list)
    doubled_words: list[dict] = field(default_factory=list)
    speaker_turns: list[dict] = field(default_factory=list)
    non_speech: list[dict] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict | str) -> "PublishJudgment":
        if isinstance(data, str):
            data = json.loads(data)
        return cls(title=data.get("title", ""),
                   sections=data.get("sections", []),
                   paragraph_breaks=data.get("paragraph_breaks", []),
                   doubled_words=data.get("doubled_words", []),
                   speaker_turns=data.get("speaker_turns", []),
                   non_speech=data.get("non_speech", []))


# ---- Backend protocol ------------------------------------------------------

class JudgmentBackend(Protocol):
    def cleanup(self, cues: list[Cue], context: dict) -> CleanupJudgment: ...
    def publish(self, cues: list[Cue], context: dict) -> PublishJudgment: ...


# ---- Paragraph breaks from delivery timing ---------------------------------
#
# The silence between two cues is measured data, not an editorial judgment
# about what the words mean, so the no-LLM path is entitled to use it. What it
# cannot recover is topic structure: headings still need a real backend.

_SENTENCE_END_RE = re.compile(r"""[.!?]["')\]]*\s*$""")

# A break needs a genuine pause in delivery. The floor rules out the
# millisecond gaps that merely separate adjacent captions; the percentile
# raises the bar for a speaker who pauses constantly, so a slow talker doesn't
# get a paragraph break at every cue.
_MIN_PAUSE_SECONDS = 0.45
_PAUSE_PERCENTILE = 80

# Keep paragraphs from becoming one-line stubs, and give a speaker who never
# pauses long enough *some* eventual break. The cap is deliberately liberal
# because it is only a backstop — pause length should decide almost every
# break — and it never ends a paragraph mid-sentence; see below.
_MIN_WORDS_PER_PARAGRAPH = 25
_SOFT_WORD_CAP = 400


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile of an already-sorted, non-empty list."""
    k = (len(values) - 1) * pct / 100
    lo = int(k)
    hi = min(lo + 1, len(values) - 1)
    if lo == hi:
        return values[lo]
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def paragraph_breaks_from_timing(cues: list[Cue]) -> list[int]:
    """Cue indices that should begin a new paragraph, read off the timing.

    Breaks where the speaker paused for longer than most of their pauses in
    this recording *and* had finished a sentence. In punctuated captions a
    paragraph therefore never ends mid-sentence — a cue ending in a comma
    means the thought continues, so it is not a candidate. The sentence test
    is dropped when the captions are mostly unpunctuated, since it would
    otherwise suppress every break.
    """
    if not cues:
        return []

    gaps = [max(0.0, timecode_to_seconds(b.start) - timecode_to_seconds(a.end))
            for a, b in zip(cues, cues[1:])]
    pauses = sorted(g for g in gaps if g > 0)
    threshold = max(_MIN_PAUSE_SECONDS,
                    _percentile(pauses, _PAUSE_PERCENTILE) if pauses else 0.0)
    punctuated = (sum(1 for c in cues if _SENTENCE_END_RE.search(c.text))
                  >= len(cues) * 0.2)

    breaks = [cues[0].index]
    words = len(cues[0].text.split())
    for gap, prev, cur in zip(gaps, cues, cues[1:]):
        wants_break = ((gap >= threshold and words >= _MIN_WORDS_PER_PARAGRAPH)
                       or words >= _SOFT_WORD_CAP)
        # The cap only *arms* a break; it takes effect at the next sentence
        # end, so an over-long paragraph still closes cleanly rather than on a
        # comma. Unpunctuated captions have no sentence end to wait for, so
        # there the cap has to act on its own.
        ends_sentence = not punctuated or bool(_SENTENCE_END_RE.search(prev.text))
        if wants_break and ends_sentence:
            breaks.append(cur.index)
            words = 0
        words += len(cur.text.split())
    return breaks


class StubBackend:
    """No-LLM backend: applies zero corrections and emits trivial publish JSON.

    Lets the deterministic pipeline run and be tested end-to-end. With this
    backend, cleanup output = source minus fillers and auto-gen header only,
    and paragraphs come from pause length rather than from any reading of the
    text (see paragraph_breaks_from_timing).
    """

    def cleanup(self, cues: list[Cue], context: dict) -> CleanupJudgment:
        return CleanupJudgment()

    def publish(self, cues: list[Cue], context: dict) -> PublishJudgment:
        return PublishJudgment(
            title=context.get("title", ""),
            sections=[{"level": 2, "title": "Transcript", "start_entry": cues[0].index}]
            if cues else [],
            paragraph_breaks=paragraph_breaks_from_timing(cues),
        )


def cues_as_prompt_text(cues: list[Cue]) -> str:
    """Render cues as the compact numbered text given to the LLM (text only —
    no timecodes — to minimize tokens; the pipeline rejoins by entry number)."""
    return "\n".join(f"{c.index}\t{c.text}" for c in cues)
