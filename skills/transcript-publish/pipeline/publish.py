"""Render an accessible HTML transcript from cues + a PublishJudgment.

Deterministic parts (title transform, meta block, duration, timecode placement,
paragraph assembly, doubled-word removal, [sic]/clarification insertion,
speaker-label and non-speech-audio markup) live here. The section structure,
paragraph break points, speaker turns, non-speech cues, and clarifications
all come from the judgment JSON (see rules/Transcript_Publish_Rules.md).
"""

from __future__ import annotations

import html
import re

from .parse import Cue, timecode_to_seconds
from .judgment import PublishJudgment
from .vtt import duration_minutes

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{
      font-family: Arial, Helvetica, sans-serif;
      font-size: 1rem;
      line-height: 1.6;
      max-width: 75ch;
      margin: 0 auto;
      padding: 1rem;
      color: #1a1a1a;
    }}
    h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
    h2 {{ font-size: 1.25rem; margin-top: 2rem; margin-bottom: 0.5rem; }}
    h3 {{ font-size: 1.1rem; margin-top: 1.5rem; margin-bottom: 0.5rem; }}
    p {{ margin-bottom: 1em; }}
    .speaker-label {{ font-weight: bold; }}
    .meta {{ font-size: 0.9rem; color: #555555; margin-bottom: 1.5rem; border-bottom: 1px solid #cccccc; padding-bottom: 1rem; }}
    .non-speech {{ color: #555555; font-style: italic; }}
    .timecode {{ font-size: 0.8rem; color: #777777; margin-top: 2rem; margin-bottom: 0.1rem; }}
  </style>
</head>
<body>

<h1>{title}</h1>

<div class="meta">
  <p><strong>Speaker:</strong> {speaker}</p>
  <p><strong>Course:</strong> {course}</p>
  <p><strong>Duration:</strong> {duration} minutes (approx.)</p>
  <p><em>Auto-generated transcript. Edits have been applied for clarity.</em></p>
</div>

{body}

</body>
</html>
"""


# ---- Title transform (filename stem -> readable title) --------------------

_NOISE_RE = re.compile(
    r"\b(16x9|4x3|1080p|720p|480p|draft|recording)\b", re.IGNORECASE)


def title_from_stem(stem: str) -> str:
    s = stem.replace("Transcript_", "")
    s = s.replace("_", " ")
    s = re.sub(r"\bChapter\s*(\d+)\b", r"Ch.\1", s, flags=re.IGNORECASE)
    s = _split_camel(s)
    s = _NOISE_RE.sub("", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return ("Transcript " + s).replace("  ", " ").strip()


def _split_camel(s: str) -> str:
    # Insert spaces between camelCase boundaries, but keep tokens like MSAS-603,
    # M2, Ch20 intact.
    def space_word(word: str) -> str:
        if re.fullmatch(r"[A-Z0-9.\-]+", word):  # all-caps/code token
            return word
        return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", word)
    return " ".join(space_word(w) for w in s.split(" "))


def _mmss(vtt_timecode: str) -> str:
    secs = timecode_to_seconds(vtt_timecode)
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ---- Doubled-word + [sic] + clarification cleanup at publish -------------

def _apply_publish_text_fixes(cue: Cue, judgment: PublishJudgment) -> str:
    text = cue.text
    for d in judgment.doubled_words:
        if d.get("entry") == cue.index and d.get("find") in text:
            text = text.replace(d["find"], d.get("replace", d["find"]), 1)
    for s in judgment.sic:
        if s.get("entry") == cue.index:
            after = s.get("after", "")
            if after and after in text:
                text = text.replace(after, after + " [sic]", 1)
    for c in judgment.clarifications:
        if c.get("entry") == cue.index:
            after = c.get("after", "")
            insert = c.get("insert", "")
            if after and insert and after in text:
                text = text.replace(after, after + f" [{insert}]", 1)
    for d in judgment.dropped_word_insertions:
        if d.get("entry") == cue.index:
            after = d.get("after", "")
            insert = d.get("insert", "")
            if after and insert and after in text:
                text = text.replace(after, after + f" [{insert}]", 1)
    return text


# ---- Body assembly --------------------------------------------------------

def build_body(cues: list[Cue], judgment: PublishJudgment) -> str:
    section_starts = {s["start_entry"]: s for s in judgment.sections}
    breaks = set(judgment.paragraph_breaks)
    speaker_at = {s["entry"]: s.get("speaker", "")
                  for s in judgment.speaker_turns if s.get("speaker")}
    non_speech_at = {n["entry"]: n.get("description", "")
                     for n in judgment.non_speech if n.get("description")}
    first_section_emitted = False

    parts: list[str] = []
    para: list[str] = []
    para_speaker: str | None = None

    def flush_para():
        nonlocal para_speaker
        if para:
            body_text = html.escape(" ".join(para))
            if para_speaker:
                label = f'<span class="speaker-label">{html.escape(para_speaker)}:</span> '
                parts.append("<p>" + label + body_text + "</p>")
            else:
                parts.append("<p>" + body_text + "</p>")
            para.clear()
        para_speaker = None

    for cue in cues:
        if cue.index in section_starts:
            flush_para()
            sec = section_starts[cue.index]
            level = sec.get("level", 2)
            # Timecode precedes every heading except the very first h2.
            if not (level == 2 and not first_section_emitted):
                parts.append(f'<p class="timecode">[{_mmss(cue.start)}]</p>')
            parts.append(f"<h{level}>{html.escape(sec['title'])}</h{level}>")
            if level == 2:
                first_section_emitted = True

        if cue.index in non_speech_at:
            # Non-speech audio cues contribute no prose — render as their own
            # paragraph and move on.
            flush_para()
            desc = non_speech_at[cue.index]
            parts.append(f'<p><span class="non-speech">[{html.escape(desc)}]</span></p>')
            continue

        if cue.index in speaker_at:
            # A new speaker turn always starts a fresh paragraph.
            flush_para()
            para_speaker = speaker_at[cue.index]
        elif cue.index in breaks and para:
            flush_para()

        text = _apply_publish_text_fixes(cue, judgment)
        para.append(text)

    flush_para()
    return "\n".join(parts)


def build_html(cues: list[Cue], judgment: PublishJudgment,
               *, speaker: str = "", course: str = "",
               title: str | None = None) -> str:
    final_title = html.escape(title or judgment.title or "Transcript")
    return TEMPLATE.format(
        title=final_title,
        speaker=html.escape(speaker),
        course=html.escape(course),
        duration=duration_minutes(cues),
        body=build_body(cues, judgment),
    )
