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
    "sic": [{"entry": 30, "after": "AI process"}]
  }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from .parse import Cue


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
    sic: list[dict] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict | str) -> "PublishJudgment":
        if isinstance(data, str):
            data = json.loads(data)
        return cls(title=data.get("title", ""),
                   sections=data.get("sections", []),
                   paragraph_breaks=data.get("paragraph_breaks", []),
                   doubled_words=data.get("doubled_words", []),
                   sic=data.get("sic", []))


# ---- Backend protocol ------------------------------------------------------

class JudgmentBackend(Protocol):
    def cleanup(self, cues: list[Cue], context: dict) -> CleanupJudgment: ...
    def publish(self, cues: list[Cue], context: dict) -> PublishJudgment: ...


class StubBackend:
    """No-LLM backend: applies zero corrections and emits trivial publish JSON.

    Lets the deterministic pipeline run and be tested end-to-end. With this
    backend, cleanup output = source minus fillers and auto-gen header only.
    """

    def cleanup(self, cues: list[Cue], context: dict) -> CleanupJudgment:
        return CleanupJudgment()

    def publish(self, cues: list[Cue], context: dict) -> PublishJudgment:
        return PublishJudgment(
            title=context.get("title", ""),
            sections=[{"level": 2, "title": "Transcript", "start_entry": cues[0].index}]
            if cues else [],
            paragraph_breaks=[c.index for c in cues],  # one para per cue
        )


def cues_as_prompt_text(cues: list[Cue]) -> str:
    """Render cues as the compact numbered text given to the LLM (text only —
    no timecodes — to minimize tokens; the pipeline rejoins by entry number)."""
    return "\n".join(f"{c.index}\t{c.text}" for c in cues)
