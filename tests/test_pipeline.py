"""Unit + integration tests for the deterministic pipeline core."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import parse as P
from pipeline.clean import remove_fillers, clean_cues
from pipeline import naming
from pipeline import vtt as V
from pipeline.flaglog import (write_flaglog, parse_flaglog, apply_flaglog,
                              Correction, ReviewEntry)
from pipeline.judgment import CleanupJudgment, PublishJudgment
from pipeline.apply import apply_cleanup
from pipeline.publish import build_html, title_from_stem


SRT_SAMPLE = """1
00:00:02,400 --> 00:00:09,090
[Auto-generated transcript. Edits may have been applied for clarity.]
This video shows you an example.

2
00:00:09,840 --> 00:00:13,080
Um, what we have for data are, uh, some income statements.

3
00:00:13,590 --> 00:00:20,580
So we are going to learn it is so much more.
"""


def check(name, cond):
    print(("PASS" if cond else "FAIL") + " " + name)
    if not cond:
        check.failed += 1
check.failed = 0


# ---- parse ----------------------------------------------------------------
def test_parse():
    cues = P.parse_srt(SRT_SAMPLE)
    check("parse: 3 cues", len(cues) == 3)
    check("parse: timecode normalized to period",
          cues[0].start == "00:00:02.400")
    check("parse: index preserved", cues[1].index == 2)
    check("parse: seconds", abs(P.timecode_to_seconds("00:01:30.500") - 90.5) < 1e-6)


# ---- clean ----------------------------------------------------------------
def test_clean():
    check("filler: removes um/uh", remove_fillers("Um, what, uh, now") == "what, now"
          or remove_fillers("Um, what, uh, now") == "what , now" or
          "um" not in remove_fillers("Um, what, uh, now").lower())
    check("filler: keeps 'so'", "so" in remove_fillers("So we begin").lower())
    check("filler: keeps embedded (summary)",
          "summary" in remove_fillers("a summary here"))
    cues = clean_cues(P.parse_srt(SRT_SAMPLE))
    # First cue's auto-gen header stripped but text remains.
    check("clean: autogen header gone",
          "Auto-generated" not in cues[0].text)
    check("clean: cue1 text kept", "This video shows you an example." in cues[0].text)
    check("clean: fillers gone in cue2", "um" not in cues[1].text.lower()
          and "uh" not in cues[1].text.lower())
    check("clean: 'so much more' preserved", "so much more" in cues[2].text)


# ---- naming ---------------------------------------------------------------
def test_naming():
    check("naming: locale + camel",
          naming.transform_stem("Audit Risk_Captions_English (United States).txt")
          == "AuditRisk")
    check("naming: module abbrev",
          naming.transform_stem("Module 5 Intro_Captions_English (United States).txt")
          == "M5Intro")
    check("naming: folder M1", naming.module_code_from_folder("Module one") == "M1")
    check("naming: folder M0", naming.module_code_from_folder("Getting started") == "M0")
    check("naming: folder explicit code",
          naming.module_code_from_folder("MSAS-603_M2") == "M2")
    check("naming: vtt name no prefix",
          naming.build_vtt_name("AuditRisk", course="MSAS-603", module="M2")
          == "MSAS-603_M2_AuditRisk.vtt")
    check("naming: flaglog name no date",
          naming.flaglog_name("MSAS-603_M2_AuditRisk.vtt")
          == "FlagLog_MSAS-603_M2_AuditRisk.txt")
    check("naming: html name",
          naming.transcript_html_name("MSAS-603_M2_AuditRisk.vtt")
          == "Transcript_MSAS-603_M2_AuditRisk.html")
    check("naming: stem from flaglog",
          naming.vtt_stem_for_flaglog("Applied_FlagLog_MSAS-603_M2_AuditRisk.txt")
          == "MSAS-603_M2_AuditRisk")


# ---- vtt write + header strip --------------------------------------------
def test_vtt():
    cues = clean_cues(P.parse_srt(SRT_SAMPLE))
    out = V.write_vtt(cues, speaker="Diane Roberts", course="MSAS-603")
    check("vtt: starts WEBVTT", out.startswith("WEBVTT\n"))
    check("vtt: no Cleaned line", "Cleaned:" not in out)
    check("vtt: no NOTE line", "NOTE" not in out)
    check("vtt: has Speaker", "Speaker: Diane Roberts" in out)
    check("vtt: has Course", "Course: MSAS-603" in out)
    check("vtt: period timecodes", "00:00:02.400 --> 00:00:09.090" in out)
    stripped = V.strip_header(out)
    check("strip: WEBVTT line1", stripped.startswith("WEBVTT\n\n"))
    check("strip: no Speaker", "Speaker:" not in stripped)
    check("strip: no NOTE", "NOTE" not in stripped)
    check("strip: cue text remains", "income statements" in stripped)
    check("duration rounds", V.duration_minutes(cues) == 0)  # 20s -> 0 min


# ---- flag log write/parse/apply -------------------------------------------
def test_flaglog():
    log = write_flaglog(
        "Audit Risk_Captions.txt",
        [Correction(4, "'a greater a risk' → 'a greater risk' — extra article")],
        [ReviewEntry(40, "00:04:11",
                     "year end to require procedure.",
                     "garbled tail",
                     "year end is a required procedure.")],
    )
    check("flaglog: no Cleaned line", "Cleaned:" not in log)
    check("flaglog: has correction", "a greater risk" in log)
    check("flaglog: 1 entry requires review", "1 entry requires review." in log)

    parsed = parse_flaglog(log)
    check("flaglog parse: 1 review", len(parsed) == 1)
    check("flaglog parse: found text", parsed[0].found == "year end to require procedure.")

    vtt_text = ("WEBVTT\n\n40\n00:04:11.000 --> 00:04:15.000\n"
                "Now the inventory observation year end to require procedure.\n")
    res = apply_flaglog(vtt_text, log)
    check("apply: 1 applied", len(res.applied) == 1)
    check("apply: replacement landed",
          "year end is a required procedure." in res.new_vtt_text)

    # Listen-only is skipped.
    log2 = write_flaglog("x.txt", [],
                         [ReviewEntry(5, "00:00:05", "foo", "x",
                                      "Listen to verify the term")])
    res2 = apply_flaglog("WEBVTT\n\n5\n00:00:05.000 --> 00:00:06.000\nfoo\n", log2)
    check("apply: listen-only skipped", len(res2.skipped) == 1 and not res2.applied)


# ---- apply cleanup judgment ----------------------------------------------
def test_apply_judgment():
    cues = clean_cues(P.parse_srt(SRT_SAMPLE))
    j = CleanupJudgment(
        corrections=[{"entry": 1, "find": "an example", "replace": "an example case",
                      "reason": "test"}],
        flags=[{"entry": 3, "issue": "garbled", "possible": "x"}],
    )
    cues, corr, rev = apply_cleanup(cues, j)
    check("judgment: correction applied", "an example case" in cues[0].text)
    check("judgment: 1 correction logged", len(corr) == 1)
    check("judgment: 1 review", len(rev) == 1 and rev[0].entry == 3)
    check("judgment: review timecode derived", rev[0].timecode == "00:13")


# ---- publish html ---------------------------------------------------------
def test_publish():
    cues = clean_cues(P.parse_srt(SRT_SAMPLE))
    j = PublishJudgment(
        title="Transcript MSAS-603 M2 Audit Risk",
        sections=[{"level": 2, "title": "Overview", "start_entry": 1},
                  {"level": 2, "title": "Data", "start_entry": 2}],
        paragraph_breaks=[1, 2, 3],
    )
    html = build_html(cues, j, speaker="Diane Roberts", course="MSAS-603",
                      title="Transcript MSAS-603 M2 Audit Risk")
    check("publish: has h1", "<h1>Transcript MSAS-603 M2 Audit Risk</h1>" in html)
    check("publish: speaker in meta", "Diane Roberts" in html)
    check("publish: first h2 no timecode before it",
          html.index("<h2>Overview</h2>") <
          (html.index('class="timecode"') if 'class="timecode"' in html else 10**9))
    check("publish: second section has timecode", "[00:09]" in html)
    check("publish: WCAG max-width", "75ch" in html)


def test_title_transform():
    check("title: camel split",
          title_from_stem("MSAS-603_M2_AuditRisk") == "Transcript MSAS-603 M2 Audit Risk")
    check("title: chapter abbrev",
          "Ch.20" in title_from_stem("MBA-6008_M3_Kotler_Chapter20_WhyToGoGlobal"))


if __name__ == "__main__":
    for fn in [test_parse, test_clean, test_naming, test_vtt, test_flaglog,
               test_apply_judgment, test_publish, test_title_transform]:
        print(f"\n# {fn.__name__}")
        fn()
    print(f"\n{'ALL PASSED' if check.failed == 0 else str(check.failed) + ' FAILED'}")
    sys.exit(1 if check.failed else 0)
