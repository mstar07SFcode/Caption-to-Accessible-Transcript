"""Parsing: SRT / plain caption TXT / WebVTT -> internal cue model.

The cue model is the single intermediate representation used by every other
module. Timecodes are normalized to WebVTT form (period millisecond separator)
at parse time so downstream code never has to care about the source format.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# Header line some auto-captioners inject into the first cue.
AUTOGEN_HEADER_RE = re.compile(
    r"\[\s*Auto-generated transcript\.?.*?\]", re.IGNORECASE
)

# HH:MM:SS,mmm --> HH:MM:SS,mmm   (comma = SRT, period = VTT; accept either)
TIMECODE_RE = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3})"
)


@dataclass
class Cue:
    index: int
    start: str  # normalized to VTT form "HH:MM:SS.mmm"
    end: str
    text: str = ""

    @property
    def lines(self) -> list[str]:
        return self.text.split("\n") if self.text else []


@dataclass
class Document:
    cues: list[Cue] = field(default_factory=list)
    meta: dict = field(default_factory=dict)  # speaker, course, etc.


def normalize_timecode(tc: str) -> str:
    """Convert an SRT comma timecode to VTT period form; pad millis to 3."""
    tc = tc.strip().replace(",", ".")
    h, m, rest = tc.split(":")
    if "." in rest:
        s, ms = rest.split(".")
    else:
        s, ms = rest, "0"
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}.{int(ms):03d}"


def timecode_to_seconds(tc: str) -> float:
    tc = tc.replace(",", ".")
    h, m, rest = tc.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def _split_blocks(text: str) -> list[list[str]]:
    """Split on blank lines into blocks of non-empty lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks, cur = [], []
    for line in text.split("\n"):
        if line.strip() == "":
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        blocks.append(cur)
    return blocks


def parse_srt(text: str) -> list[Cue]:
    """Parse SRT or plain numbered caption TXT (same structure)."""
    cues: list[Cue] = []
    for block in _split_blocks(text):
        idx, tc_line_i = None, None
        # Find the timecode line; the line just before it (if numeric) is index.
        for i, line in enumerate(block):
            if TIMECODE_RE.search(line):
                tc_line_i = i
                break
        if tc_line_i is None:
            continue  # not a cue block
        if tc_line_i >= 1 and block[tc_line_i - 1].strip().isdigit():
            idx = int(block[tc_line_i - 1].strip())
        m = TIMECODE_RE.search(block[tc_line_i])
        start, end = normalize_timecode(m.group(1)), normalize_timecode(m.group(2))
        text_lines = block[tc_line_i + 1 :]
        cue_text = "\n".join(text_lines).strip()
        cues.append(Cue(index=idx if idx is not None else len(cues) + 1,
                        start=start, end=end, text=cue_text))
    return cues


def parse_vtt(text: str) -> Document:
    """Parse a WebVTT file (with or without our custom metadata header)."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    meta: dict = {}
    lines = text.split("\n")

    # Header: read metadata lines that appear before the first blank line.
    i = 0
    if lines and lines[0].lstrip().upper().startswith("WEBVTT"):
        i = 1
        while i < len(lines) and lines[i].strip() != "":
            line = lines[i]
            for key in ("Speaker", "Course", "Cleaned"):
                if line.startswith(key + ":"):
                    meta[key.lower()] = line.split(":", 1)[1].strip()
            i += 1

    body = "\n".join(lines[i:])
    # Drop NOTE blocks before cue parsing (they are separated by blank lines).
    kept_blocks = []
    for block in _split_blocks(body):
        if block and block[0].lstrip().upper().startswith("NOTE"):
            continue
        kept_blocks.append(block)
    rebuilt = "\n\n".join("\n".join(b) for b in kept_blocks)
    cues = parse_srt(rebuilt)
    return Document(cues=cues, meta=meta)


def parse_source(text: str, filename: str = "") -> Document:
    """Dispatch by extension/content. Returns a Document (meta may be empty)."""
    if filename.lower().endswith(".vtt") or text.lstrip().upper().startswith("WEBVTT"):
        return parse_vtt(text)
    return Document(cues=parse_srt(text), meta={})


def strip_autogen_header(cue: Cue) -> Optional[Cue]:
    """Remove the auto-generated header text from a cue.

    Returns the modified cue, or None if the cue becomes empty (caller should
    drop it). Entry numbers/timecodes are never altered here.
    """
    new_text = AUTOGEN_HEADER_RE.sub("", cue.text).strip()
    # Clean up a leading orphaned newline left by removal.
    new_text = re.sub(r"^\n+", "", new_text).strip()
    if not new_text:
        return None
    cue.text = new_text
    return cue
