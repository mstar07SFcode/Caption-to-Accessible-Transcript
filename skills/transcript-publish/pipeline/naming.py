"""Filename transforms and module-code mapping (deterministic).

Implements the naming rules from Skill-Caption_Cleanup.md, updated to the new
convention: NO `Cleaned_` prefix and NO date stamps. Outputs:

  VTT          -> [Course_][Module_]TransformedName.vtt
  Flag log     -> FlagLog_[Course_][Module_]TransformedName.txt
  Applied log  -> Applied_FlagLog_...txt
  HTML         -> Transcript_<vtt stem>.html
"""

from __future__ import annotations

import re

# ---- Folder name -> module code -------------------------------------------

_WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}


def module_code_from_folder(folder: str) -> str | None:
    """Map a subfolder name to a module code, or None if not applicable."""
    if not folder:
        return None
    name = folder.strip()
    low = name.lower()

    if low in ("getting started",):
        return "M0"

    # Already contains an explicit code like "M4", "Week 3", "W2", "..._M2".
    # Lookbehind excludes letters so "M" in "MSAS" won't false-match, but
    # "_M2" (preceded by underscore) still matches.
    m = re.search(r"(?<![A-Za-z])([MW])\s*-?\s*(\d+)\b", name, re.IGNORECASE)
    if m:
        return f"{m.group(1).upper()}{int(m.group(2))}"

    m = re.match(r"module\s+(\w+)", low)
    if m:
        n = _WORD_NUM.get(m.group(1)) or (int(m.group(1)) if m.group(1).isdigit() else None)
        if n is not None:
            return f"M{n}"
    m = re.match(r"week\s+(\w+)", low)
    if m:
        n = _WORD_NUM.get(m.group(1)) or (int(m.group(1)) if m.group(1).isdigit() else None)
        if n is not None:
            return f"W{n}"

    # Unrecognized -> camelCase the folder name (e.g. "Midterm").
    return _camel(name)


# ---- Filename transformation ----------------------------------------------

_LOCALE_RE = re.compile(r"_Captions_English\s*\([^)]*\)", re.IGNORECASE)
_LOCALE_GENERIC_RE = re.compile(r"_Captions_[A-Za-z]+(\s*\([^)]*\))?", re.IGNORECASE)
_TAG_RE = re.compile(
    r"\b(16x9|4x3|1080p|720p|480p|v\d+|copy)\b|\(copy\)|\(\d+\)",
    re.IGNORECASE,
)


def _camel(s: str) -> str:
    """Remove spaces/hyphens and CamelCase the remaining word parts."""
    parts = re.split(r"[\s\-_]+", s.strip())
    parts = [p for p in parts if p]
    if not parts:
        return ""
    out = []
    for p in parts:
        if p.isupper() or re.match(r"^[A-Z][a-z]", p) or any(c.isupper() for c in p[1:]):
            out.append(p[0].upper() + p[1:])  # preserve internal caps
        else:
            out.append(p[0].upper() + p[1:])
    return "".join(out)


def _abbreviate_modules(s: str) -> str:
    s = re.sub(r"\bModule\s+(\d+)\b", lambda m: f"M{m.group(1)}", s, flags=re.IGNORECASE)
    s = re.sub(r"\bWeek\s+(\d+)\b", lambda m: f"W{m.group(1)}", s, flags=re.IGNORECASE)
    s = re.sub(r"\bChapter\s+(\d+)\b", lambda m: f"Ch{m.group(1)}", s, flags=re.IGNORECASE)
    return s


def transform_stem(source_filename: str,
                   speaker_prefixes: tuple[str, ...] = ()) -> str:
    """Transform a source filename into the cleaned VTT stem (no extension,
    no prefix). `speaker_prefixes` lets the caller strip a known instructor
    first-name prefix (e.g. 'Leigh' in 'Leighmodule-1-overview')."""
    stem = re.sub(r"\.(srt|txt|vtt)$", "", source_filename, flags=re.IGNORECASE)
    stem = _LOCALE_RE.sub("", stem)
    stem = _LOCALE_GENERIC_RE.sub("", stem)
    stem = _TAG_RE.sub("", stem)

    # Strip a known leading speaker-name prefix if present.
    for name in speaker_prefixes:
        if stem.lower().startswith(name.lower()) and len(stem) > len(name):
            stem = stem[len(name):]
            break

    stem = _abbreviate_modules(stem)
    stem = _camel(stem)
    stem = re.sub(r"_{2,}", "_", stem).strip("_")
    return stem


def build_vtt_name(stem: str, course: str | None = None,
                   module: str | None = None) -> str:
    parts = [p for p in (course, module) if p]
    parts.append(stem)
    return "_".join(parts) + ".vtt"


def flaglog_name(vtt_name: str) -> str:
    return "FlagLog_" + re.sub(r"\.vtt$", "", vtt_name) + ".txt"


def applied_flaglog_name(vtt_name: str) -> str:
    return "Applied_" + flaglog_name(vtt_name)


def transcript_html_name(vtt_name: str) -> str:
    return "Transcript_" + re.sub(r"\.vtt$", "", vtt_name) + ".html"


def vtt_stem_for_flaglog(flaglog_filename: str) -> str:
    """Given FlagLog_<stem>.txt (or Applied_FlagLog_<stem>.txt) return <stem>."""
    name = re.sub(r"\.txt$", "", flaglog_filename)
    name = re.sub(r"^Applied_", "", name)
    name = re.sub(r"^FlagLog_", "", name)
    return name
