"""WebVTT writer and header utilities.

Writes the working VTT (with the custom Speaker/Course/NOTE header used by the
local workflow) and can strip that header to produce the standards-compliant
file archived to VTT_Files. No `Cleaned:` date line is ever written.
"""

from __future__ import annotations

from .parse import Cue, timecode_to_seconds


def write_vtt(cues: list[Cue], *, speaker: str = "", course: str = "") -> str:
    """Serialize cues to a WebVTT string.

    Header is just WEBVTT plus optional Speaker/Course. No NOTE line and no
    Cleaned: date — the .vtt extension and Edited_Captions location already
    signal the file has been processed.
    """
    lines: list[str] = ["WEBVTT"]
    if speaker:
        lines.append(f"Speaker: {speaker}")
    if course:
        lines.append(f"Course: {course}")
    lines.append("")  # blank line ends the header block
    for cue in cues:
        lines.append(str(cue.index))
        lines.append(f"{cue.start} --> {cue.end}")
        lines.append(cue.text)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def strip_header(vtt_text: str) -> str:
    """Return standards-compliant WebVTT: WEBVTT on line 1, blank line, cues.

    Removes Speaker:/Course:/Cleaned: metadata lines and NOTE blocks. Mirrors
    the awk used in Skill-Transcript_Publish.md.
    """
    text = vtt_text.replace("\r\n", "\n").replace("\r", "\n")
    src = text.split("\n")
    out: list[str] = []
    found_webvtt = False
    in_note = False
    for line in src:
        if not found_webvtt:
            if line.lstrip().upper().startswith("WEBVTT"):
                found_webvtt = True
                out.append("WEBVTT")
            continue
        if in_note:
            if line.strip() == "":
                in_note = False
            continue
        if line.startswith("NOTE"):
            in_note = True
            continue
        if line.startswith(("Speaker:", "Course:", "Cleaned:")):
            continue
        out.append(line)
    # Ensure exactly one blank line after WEBVTT.
    body = "\n".join(out[1:]).lstrip("\n")
    return "WEBVTT\n\n" + body.rstrip("\n") + "\n"


def duration_minutes(cues: list[Cue]) -> int:
    """Last cue end time rounded to nearest minute (>=30s rounds up)."""
    if not cues:
        return 0
    secs = timecode_to_seconds(cues[-1].end)
    return int((secs + 30) // 60)
