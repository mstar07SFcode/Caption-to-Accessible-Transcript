"""Render an accessible Word (.docx) transcript from cues + a PublishJudgment.

Mirrors publish.py's build_body/build_html in structure and rules - the same
sections, paragraphs, speaker labels, non-speech cues and the same publish
text fixes (it reuses publish._apply_publish_text_fixes) - but emits a
python-docx Document instead of HTML. Adapted from the GitHub plugin's
docx_publish.py so the two stay easy to merge.

Accessibility: real Word heading styles (navigable headings pane), every run
at 12pt or larger, document title set in the file's properties.

Needs the python-docx package; imported only when Word output is chosen, so an
HTML-only setup never needs it.
"""

from __future__ import annotations

from docx import Document
from docx.shared import Pt, RGBColor

from .judgment import PublishJudgment
from .parse import Cue
from .publish import _apply_publish_text_fixes, _mmss
from .vtt import duration_minutes

_GRAY = RGBColor(0x55, 0x55, 0x55)
_MIN_PT = Pt(12)


def _timecode_paragraph(doc, vtt_start: str) -> None:
    p = doc.add_paragraph()
    run = p.add_run(f"[{_mmss(vtt_start)}]")
    run.font.size = _MIN_PT
    run.font.color.rgb = _GRAY
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(2)


def _non_speech_paragraph(doc, description: str) -> None:
    run = doc.add_paragraph().add_run(f"[{description}]")
    run.italic = True
    run.font.color.rgb = _GRAY


def build_body(doc, cues: list[Cue], judgment: PublishJudgment) -> None:
    section_starts = {s["start_entry"]: s for s in judgment.sections}
    breaks = set(judgment.paragraph_breaks)
    speaker_at = {s["entry"]: s.get("speaker", "")
                  for s in judgment.speaker_turns if s.get("speaker")}
    non_speech_at = {n["entry"]: n.get("description", "")
                     for n in judgment.non_speech if n.get("description")}
    first_section_emitted = False
    para: list[str] = []
    para_speaker: str | None = None

    def flush_para():
        nonlocal para_speaker
        if para:
            p = doc.add_paragraph()
            if para_speaker:
                p.add_run(f"{para_speaker}: ").bold = True
            p.add_run(" ".join(para))
            para.clear()
        para_speaker = None

    for cue in cues:
        if cue.index in section_starts:
            flush_para()
            sec = section_starts[cue.index]
            level = sec.get("level", 2)
            if not (level == 2 and not first_section_emitted):
                _timecode_paragraph(doc, cue.start)
            doc.add_heading(sec["title"], level=level)
            if level == 2:
                first_section_emitted = True
        if cue.index in non_speech_at:
            flush_para()
            _non_speech_paragraph(doc, non_speech_at[cue.index])
            continue
        if cue.index in speaker_at:
            flush_para()
            para_speaker = speaker_at[cue.index]
        elif cue.index in breaks and para:
            flush_para()
        para.append(_apply_publish_text_fixes(cue, judgment))
    flush_para()


def _set_font_sizes(doc) -> None:
    """Word's default template has Normal at 11pt; the floor here is 12pt."""
    doc.styles["Normal"].font.size = _MIN_PT
    doc.styles["Title"].font.size = Pt(24)
    doc.styles["Heading 1"].font.size = Pt(18)
    doc.styles["Heading 2"].font.size = Pt(15)
    doc.styles["Heading 3"].font.size = Pt(13)


def build_docx(cues: list[Cue], judgment: PublishJudgment, *, speaker: str = "",
               course: str = "", title: str | None = None):
    doc = Document()
    _set_font_sizes(doc)
    final_title = title or judgment.title or "Transcript"
    doc.core_properties.title = final_title       # read by screen readers / Word
    doc.core_properties.language = "en-US"
    doc.add_heading(final_title, level=1)

    def meta(label: str, value: str):
        p = doc.add_paragraph()
        p.add_run(f"{label}: ").bold = True
        p.add_run(value)

    if speaker:
        meta("Speaker", speaker)
    if course:
        meta("Course", course)
    meta("Duration", f"{duration_minutes(cues)} minutes (approx.)")
    doc.add_paragraph().add_run(
        "Auto-generated transcript. Edits have been applied for clarity.").italic = True
    build_body(doc, cues, judgment)
    return doc


def docx_available() -> bool:
    try:
        import docx  # noqa: F401
        return True
    except ImportError:
        return False
