"""Side-by-side review helpers for the GUI's review window.

Reads one pending flag log plus its cleaned VTT and returns everything the
review window shows: every caption line, every automatic correction (the
"CORRECTIONS APPLIED" section) and every flagged entry.

It can also UNDO one automatic correction. Undo is the forward edit in reverse:
inside that one entry only, the first occurrence of the replacement text is
turned back into the original text. The flag log line is then marked
"(undone by reviewer)" so the record stays honest and the same fix cannot be
undone twice. No AI is involved.
"""

from __future__ import annotations

import re
from pathlib import Path

from pipeline import naming
from pipeline import parse as P
from pipeline.apply import _mmss
from pipeline.flaglog import editable_possible, entry_text_spans, parse_flaglog

# "  • Entry 33: 'texter' → 'texture' — reason"
# "  ↺ Entry 33 (undone by reviewer): 'texter' → 'texture' — reason"
_CORR = re.compile(
    r"^\s*(?P<mark>[•↺✎])\s*Entry\s+(?P<entry>\d+)(?P<undone>\s*\(undone by reviewer\))?:\s*"
    r"'(?P<find>.*?)'\s*→\s*'(?P<replace>.*?)'\s*—\s*(?P<reason>.*)$")
_REVIEW_HEADING = "ENTRIES REQUIRING HUMAN REVIEW"
_REVIEWER = "Reviewer:"


class ReviewError(RuntimeError):
    pass


_NL = " ⏎ "   # how a line break inside a caption is written in the one-line log record


def _enc(t: str) -> str:
    return t.replace("\n", _NL)


def _dec(t: str) -> str:
    return t.replace(_NL, "\n")


def _insert_records(log_text: str, records: list[str]) -> str:
    """Add reviewer lines (✎) at the end of the CORRECTIONS APPLIED list."""
    head, sep, tail = log_text.partition(_REVIEW_HEADING)
    hl = head.split("\n")
    try:
        k = next(i for i, l in enumerate(hl) if l.startswith("These corrections were applied"))
        j = k + 2
        if j < len(hl) and hl[j].strip() == "(none)":
            del hl[j]
        while j < len(hl) and hl[j].strip():
            j += 1
        hl[j:j] = records
    except StopIteration:
        hl[0:0] = records
    return "\n".join(hl) + sep + tail


def _set_entry_text(vtt_text: str, entry: int, new_text: str) -> str:
    spans = entry_text_spans(vtt_text)
    if entry not in spans:
        raise ReviewError(f"Entry {entry} was not found in the caption file.")
    start, end = spans[entry]
    lines = vtt_text.split("\n")
    lines[start:end] = new_text.split("\n")
    return "\n".join(lines)


def _paths(wf: Path, flaglog_name: str) -> tuple[Path, Path]:
    edited = (wf / "Edited_Captions").resolve()
    log = (edited / flaglog_name).resolve()
    if log.parent != edited or not log.name.startswith("FlagLog_") or not log.is_file():
        raise FileNotFoundError(flaglog_name)
    stem = naming.vtt_stem_for_flaglog(log.name)
    vtt = edited / f"{stem}.vtt"
    if not vtt.is_file():
        raise ReviewError(f"The caption file {stem}.vtt is missing from Edited_Captions.")
    return log, vtt


def _correction_lines(log_text: str) -> list[tuple[int, re.Match]]:
    """(line number, match) for each correction line, in file order."""
    out = []
    head = log_text.split(_REVIEW_HEADING, 1)[0]
    for i, line in enumerate(head.split("\n")):
        m = _CORR.match(line)
        if m:
            out.append((i, m))
    return out


def normalize_flags(entries: list[dict], cue_text: dict[int, str]) -> list[dict]:
    """Make older flag logs consistent with the captions as they are now.

    * A flag whose line was already auto-fixed and whose suggestion is already
      in the caption is dropped (it is done).
    * A flag whose original text is no longer in its line (because an auto-fix
      changed that line) is pointed at the line's current text, so the box and
      Apply work on what is really in the file.
    """
    out = []
    for e in entries:
        now = cue_text.get(e["entry"])
        if now is not None and e["found"] and e["found"] not in now:
            poss = (e.get("possible") or "").strip()
            if poss and poss in now:
                continue
            e = dict(e, found=now)
        out.append(e)
    return out


def cue_texts(vtt: Path) -> dict[int, str]:
    if not vtt.is_file():
        return {}
    return {c.index: c.text for c in P.parse_vtt(vtt.read_text(encoding="utf-8")).cues}


def parse_corrections(log_text: str) -> list[dict]:
    # Lines that change nothing ("no change needed") are hidden. Ids stay the
    # position in the file, so Undo still targets the right line.
    return [{"id": n, "entry": int(m["entry"]), "find": _dec(m["find"]),
             "replace": _dec(m["replace"]), "reason": m["reason"].strip(),
             "undone": bool(m["undone"]) or m["mark"] == "↺",
             "kind": "reviewer" if m["reason"].strip().startswith(_REVIEWER) else "auto"}
            for n, (_, m) in enumerate(_correction_lines(log_text))
            if m["find"] != m["replace"] or m["reason"].strip().startswith(_REVIEWER)]


def load_review(wf: Path, flaglog_name: str) -> dict:
    log, vtt = _paths(wf, flaglog_name)
    log_text = log.read_text(encoding="utf-8")
    doc = P.parse_vtt(vtt.read_text(encoding="utf-8"))
    return {
        "file": log.name,
        "stem": vtt.stem,
        "speaker": doc.meta.get("speaker", ""),
        "course": doc.meta.get("course", ""),
        "cues": [{"entry": c.index, "start": _mmss(c.start), "text": c.text}
                 for c in doc.cues],
        "corrections": parse_corrections(log_text),
        "flags": normalize_flags(
            [{"entry": r.entry, "timecode": r.timecode, "found": r.found,
              "issue": r.issue, "possible": editable_possible(r.found, r.possible), "keep": True}
             for r in parse_flaglog(log_text)],
            {c.index: c.text for c in doc.cues}),
    }


def undo_correction(wf: Path, flaglog_name: str, correction_id: int) -> dict:
    log, vtt = _paths(wf, flaglog_name)
    log_text = log.read_text(encoding="utf-8")
    lines_info = _correction_lines(log_text)
    if not 0 <= correction_id < len(lines_info):
        raise ReviewError("That correction no longer exists - reopen the review window.")
    line_no, m = lines_info[correction_id]
    if m["undone"] or m["mark"] == "↺":
        raise ReviewError("That fix has already been undone.")
    entry, find, replace = int(m["entry"]), _dec(m["find"]), _dec(m["replace"])
    if not replace:
        raise ReviewError("This fix removed text, so it can't be undone "
                          "automatically. Edit the caption file by hand.")

    vtt_text = vtt.read_text(encoding="utf-8")
    spans = entry_text_spans(vtt_text)
    if entry not in spans:
        raise ReviewError(f"Entry {entry} was not found in the caption file.")
    start, end = spans[entry]
    vlines = vtt_text.split("\n")
    block = "\n".join(vlines[start:end])
    if replace not in block:
        raise ReviewError(
            f"Entry {entry} no longer contains '{replace}' (it may have been "
            "edited since), so the fix can't be undone automatically.")
    vlines[start:end] = block.replace(replace, find, 1).split("\n")

    llines = log_text.split("\n")
    llines[line_no] = re.sub(r"^(\s*)[•✎]", r"\1↺", llines[line_no], count=1).replace(
        f"Entry {entry}:", f"Entry {entry} (undone by reviewer):", 1)

    # Write the caption file first; if that fails, the log is left untouched.
    vtt.write_text("\n".join(vlines), encoding="utf-8")
    log.write_text("\n".join(llines), encoding="utf-8")
    return load_review(wf, flaglog_name)


def apply_flag(wf: Path, flaglog_name: str, entry: int, found: str, text: str) -> dict:
    """Apply ONE flagged entry right now, from the review window.

    Inside that entry only, the original caption text (`found`) is replaced with
    the reviewer's `text`. The flag then leaves the review list and is recorded
    in the CORRECTIONS APPLIED section as a reviewer edit (marked with ✎), so it
    shows up alongside the automatic fixes and can be undone the same way.
    Leaving the text identical to the original resolves the flag with no change.
    """
    from .runner import write_flaglog_entries   # same writer the main window uses

    text = (text or "").strip()
    if not text:
        raise ReviewError("Type the corrected wording first (or click the original "
                          "caption to copy it into the box).")
    log, vtt = _paths(wf, flaglog_name)
    log_text = log.read_text(encoding="utf-8")
    pending = normalize_flags(
        [{"entry": r.entry, "timecode": r.timecode, "found": r.found,
          "issue": r.issue, "possible": r.possible, "keep": True}
         for r in parse_flaglog(log_text)], cue_texts(vtt))
    idx = next((i for i, r in enumerate(pending)
                if r["entry"] == entry and r["found"] == found), None)
    if idx is None:
        raise ReviewError(f"Entry {entry} is no longer waiting for review "
                          "(it may have been applied already).")

    changed = text != found
    if changed:
        vtt_text = vtt.read_text(encoding="utf-8")
        spans = entry_text_spans(vtt_text)
        if entry not in spans:
            raise ReviewError(f"Entry {entry} was not found in the caption file.")
        start, end = spans[entry]
        vlines = vtt_text.split("\n")
        block = "\n".join(vlines[start:end])
        if found not in block:
            raise ReviewError(f"Entry {entry} no longer contains the original text, "
                              "so it can't be replaced automatically.")
        vlines[start:end] = block.replace(found, text, 1).split("\n")
        vtt.write_text("\n".join(vlines), encoding="utf-8")

    # Record it among the corrections (head section of the flag log).
    reason = f"{_REVIEWER} edited" if changed else f"{_REVIEWER} kept as is"
    log.write_text(_insert_records(
        log_text, [f"  ✎ Entry {entry}: '{_enc(found)}' → '{_enc(text)}' — {reason}"]),
        encoding="utf-8")

    # Rewrite the review list without this entry (others keep their edits).
    remaining = [r for i, r in enumerate(pending) if i != idx]
    write_flaglog_entries(wf, log.name, remaining)
    return load_review(wf, flaglog_name)


def edit_entry(wf: Path, flaglog_name: str, entry: int, old_text: str, new_text: str) -> dict:
    """Replace one caption line's whole text with the reviewer's version."""
    log, vtt = _paths(wf, flaglog_name)
    new_text = "\n".join(l.strip() for l in (new_text or "").strip().split("\n") if l.strip())
    if not new_text:
        raise ReviewError("A caption line can't be empty. Use [unintelligible] if "
                          "nothing can be made out.")
    current = cue_texts(vtt).get(entry)
    if current is None:
        raise ReviewError(f"Entry {entry} was not found in the caption file.")
    if current != old_text:
        raise ReviewError(f"Entry {entry} changed since you opened it. Reload "
                          "the window and try again.")
    if new_text == current:
        return load_review(wf, flaglog_name)
    vtt.write_text(_set_entry_text(vtt.read_text(encoding="utf-8"), entry, new_text),
                   encoding="utf-8")
    log.write_text(_insert_records(log.read_text(encoding="utf-8"), [
        f"  ✎ Entry {entry}: '{_enc(current)}' → '{_enc(new_text)}' — {_REVIEWER} edited line"]),
        encoding="utf-8")
    return load_review(wf, flaglog_name)


def _pattern(find: str, match_case: bool, whole_word: bool) -> re.Pattern:
    if not find:
        raise ReviewError("Type something to find.")
    pat = re.escape(find)
    if whole_word:
        pat = r"(?<!\w)" + pat + r"(?!\w)"
    return re.compile(pat, 0 if match_case else re.IGNORECASE)


def find_matches(wf: Path, flaglog_name: str, find: str, match_case: bool = False,
                 whole_word: bool = True) -> dict:
    """Every caption line containing `find` (preview only, changes nothing)."""
    _, vtt = _paths(wf, flaglog_name)
    rx = _pattern(find, match_case, whole_word)
    doc = P.parse_vtt(vtt.read_text(encoding="utf-8"))
    out, total = [], 0
    for c in doc.cues:
        spans = [(m.start(), m.end()) for m in rx.finditer(c.text)]
        if spans:
            total += len(spans)
            out.append({"entry": c.index, "start": _mmss(c.start), "text": c.text,
                        "spans": spans})
    return {"matches": out, "total": total}


def replace_all(wf: Path, flaglog_name: str, find: str, replace: str,
                match_case: bool = False, whole_word: bool = True) -> dict:
    """Replace every match in the caption text (never timecodes or header).
    Each changed line is logged as its own reviewer edit, so any one line can
    be undone on its own afterwards."""
    log, vtt = _paths(wf, flaglog_name)
    rx = _pattern(find, match_case, whole_word)
    vtt_text = vtt.read_text(encoding="utf-8")
    doc = P.parse_vtt(vtt_text)
    records, changed, count = [], 0, 0
    for c in doc.cues:
        new, n = rx.subn(lambda m: replace, c.text)
        if n and new != c.text:
            vtt_text = _set_entry_text(vtt_text, c.index, new)
            records.append(f"  ✎ Entry {c.index}: '{_enc(c.text)}' → '{_enc(new)}' — "
                           f"{_REVIEWER} find & replace '{find}' → '{replace}'")
            changed += 1
            count += n
    if not records:
        raise ReviewError(f"No matches for '{find}'.")
    vtt.write_text(vtt_text, encoding="utf-8")
    log.write_text(_insert_records(log.read_text(encoding="utf-8"), records), encoding="utf-8")
    result = load_review(wf, flaglog_name)
    result["replaced"] = {"count": count, "lines": changed}
    return result
