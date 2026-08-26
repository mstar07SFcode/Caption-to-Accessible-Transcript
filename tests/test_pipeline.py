"""Unit + integration tests for the deterministic pipeline core."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import parse as P
from pipeline.clean import (remove_fillers, clean_cues,
                            normalize_captioner_markers, MARKER)
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


def test_captioner_markers():
    """Rule 1d: normalize the captioner's own 'could not transcribe' markers.

    The first four cases are exactly the rows of the Rule 1d table in
    rules/Caption_Cleanup_Rules.md — if that table changes, these change.
    """
    n = normalize_captioner_markers

    # --- the four documented cases, verbatim from the rules table ---
    check("marker: straight swap",
          n("Alpha pays [unrecognized] for a 10% interest")
          == "Alpha pays [unintelligible] for a 10% interest")
    check("marker: missing spaces repaired",
          n("Alpha pays[unrecognized]for a 10% interest")
          == "Alpha pays [unintelligible] for a 10% interest")
    check("marker: bare possessive repaired",
          n("[unrecognized]s 2027 net income")
          == "[unintelligible]'s 2027 net income")
    check("marker: spacing repaired, terminal punctuation kept",
          n("included in current net income[unrecognized].")
          == "included in current net income [unintelligible].")

    # --- every engine variant maps to the one project marker ---
    for variant in ["[unrecognized]", "[unrecognised]", "[inaudible]",
                    "[indiscernible]", "[unclear]", "[unintelligible]",
                    "[?]", "[???]", "[ unrecognized ]", "[UNRECOGNIZED]"]:
        check(f"marker: variant {variant} -> {MARKER}",
              n(f"the {variant} figure") == f"the {MARKER} figure")

    # --- multiple markers in one cue are all normalized ---
    check("marker: two in one cue",
          n("[inaudible] and [?] too")
          == f"{MARKER} and {MARKER} too")

    # --- idempotent: re-running must not double-space or double-possessive ---
    once = n("Alpha pays[unrecognized]for [unrecognized]s share.")
    check("marker: idempotent", n(once) == once)
    check("marker: idempotent result correct",
          once == f"Alpha pays {MARKER} for {MARKER}'s share.")

    # --- no marker present: text must pass through untouched ---
    for clean_text in ["nothing here at all",
                       "a 10% interest in the [bracketed] aside",
                       "she said it was unrecognized by the board"]:
        check(f"marker: untouched {clean_text[:24]!r}", n(clean_text) == clean_text)

    # --- runs through the deterministic clean step, not just in isolation ---
    cues = P.parse_srt("""1
00:00:01,000 --> 00:00:03,000
Um, Alpha pays[unrecognized]for it.
""")
    cleaned = clean_cues(cues)
    check("marker: applied by clean_cues",
          cleaned[0].text == f"Alpha pays {MARKER} for it.")


def test_flaglog_scoping():
    """A correction must land in the entry the flag log names, and nowhere else.

    Regression: apply_flaglog used to run str.replace over the whole VTT text,
    so the FIRST occurrence anywhere won — a phrase flagged at entry 40 would
    silently rewrite entry 3, the metadata header, or a NOTE block.
    """
    vtt = ("WEBVTT\n"
           "Speaker: the balance sheet date matters\n"
           "Course: MSAS-603\n"
           "\n"
           "NOTE the balance sheet date matters\n"
           "\n"
           "3\n"
           "00:00:10.000 --> 00:00:12.000\n"
           "the balance sheet date matters\n"
           "\n"
           "40\n"
           "00:04:11.000 --> 00:04:15.000\n"
           "the balance sheet date matters\n")
    log = write_flaglog("x.txt", [], [ReviewEntry(
        40, "04:11", "the balance sheet date matters",
        "garbled", "the balance sheet date is what matters")])
    res = apply_flaglog(vtt, log)
    out = res.new_vtt_text

    check("flaglog scope: applied once", len(res.applied) == 1)
    # The decisive assertion: entry 3 is untouched, entry 40 is corrected.
    e3 = out.split("3\n00:00:10.000 --> 00:00:12.000\n")[1].split("\n")[0]
    e40 = out.split("40\n00:04:11.000 --> 00:04:15.000\n")[1].split("\n")[0]
    check("flaglog scope: entry 3 NOT rewritten",
          e3 == "the balance sheet date matters")
    check("flaglog scope: entry 40 rewritten",
          e40 == "the balance sheet date is what matters")
    check("flaglog scope: only one occurrence changed",
          out.count("is what matters") == 1)

    # Everything that is not cue text keeps its exact bytes.
    check("flaglog scope: header metadata untouched",
          "Speaker: the balance sheet date matters" in out)
    check("flaglog scope: NOTE block untouched",
          "NOTE the balance sheet date matters" in out)
    check("flaglog scope: timecodes untouched",
          "00:00:10.000 --> 00:00:12.000" in out
          and "00:04:11.000 --> 00:04:15.000" in out)

    # Text that exists in the file but NOT in the named entry is unmatched,
    # never applied somewhere else.
    log2 = write_flaglog("x.txt", [], [ReviewEntry(
        40, "04:11", "a phrase only in entry 3", "x", "a replacement")])
    vtt2 = vtt.replace("3\n00:00:10.000 --> 00:00:12.000\n"
                       "the balance sheet date matters",
                       "3\n00:00:10.000 --> 00:00:12.000\n"
                       "a phrase only in entry 3")
    res2 = apply_flaglog(vtt2, log2)
    check("flaglog scope: wrong-entry text is unmatched",
          not res2.applied and len(res2.unmatched) == 1)
    check("flaglog scope: unmatched leaves file byte-identical",
          res2.new_vtt_text == vtt2)

    # An entry number the VTT does not contain is unmatched, not misapplied.
    log3 = write_flaglog("x.txt", [], [ReviewEntry(
        99, "09:99", "the balance sheet date matters", "x", "nope")])
    res3 = apply_flaglog(vtt, log3)
    check("flaglog scope: missing entry unmatched",
          not res3.applied and len(res3.unmatched) == 1)
    check("flaglog scope: missing entry leaves file unchanged",
          res3.new_vtt_text == vtt)

    # A cue whose text wraps across lines still matches the one-line Found:.
    vtt4 = ("WEBVTT\n\n7\n00:00:01.000 --> 00:00:04.000\n"
            "the year end to\nrequire procedure\n")
    log4 = write_flaglog("x.txt", [], [ReviewEntry(
        7, "00:01", "the year end to require procedure", "garbled",
        "the year end is a required procedure")])
    res4 = apply_flaglog(vtt4, log4)
    check("flaglog scope: wrapped cue matched via collapse",
          len(res4.applied) == 1
          and "the year end is a required procedure" in res4.new_vtt_text)

    # Two corrections where the first changes the cue's line count: the second
    # must still land in its own entry (span bookkeeping).
    vtt5 = ("WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.000\n"
            "alpha one\nalpha two\n\n"
            "2\n00:00:02.000 --> 00:00:03.000\nbravo here\n")
    log5 = write_flaglog("x.txt", [], [
        ReviewEntry(1, "00:01", "alpha one alpha two", "x", "alpha merged"),
        ReviewEntry(2, "00:02", "bravo here", "x", "bravo fixed")])
    res5 = apply_flaglog(vtt5, log5)
    check("flaglog scope: both applied after line-count shift",
          len(res5.applied) == 2)
    check("flaglog scope: second correction landed in entry 2",
          res5.new_vtt_text.rstrip().endswith("bravo fixed"))


def test_publish_never_adds_text():
    """Publish Rule 3: the publish step has no way to add text to a transcript.

    [sic], bracketed clarifications and dropped-word insertions were removed.
    A model that emits those keys anyway — they were in the schema for months,
    so a plausible hallucination — must have them ignored, not rendered.
    """
    cues = [P.Cue(1, "00:00:00.000", "00:00:04.000",
                  "we need make sure the the section 117 rule applies")]
    j = PublishJudgment.from_json({
        "title": "T", "sections": [{"level": 2, "title": "S", "start_entry": 1}],
        "paragraph_breaks": [1],
        "doubled_words": [{"entry": 1, "find": "the the", "replace": "the"}],
        # --- all three removed fields, supplied anyway ---
        "sic": [{"entry": 1, "after": "we need make sure"}],
        "clarifications": [{"entry": 1, "after": "section 117",
                            "insert": "referring to §117(a)"}],
        "dropped_word_insertions": [{"entry": 1, "after": "we need",
                                     "insert": "to"}],
    })
    check("publish: removed fields dropped from judgment",
          not any(hasattr(j, f) for f in
                  ("sic", "clarifications", "dropped_word_insertions")))

    html = build_html(cues, j, title="T")
    check("publish: no [sic] rendered", "[sic]" not in html)
    check("publish: no clarification rendered", "§117(a)" not in html)
    check("publish: no dropped word rendered", "[to]" not in html)
    check("publish: sentence left exactly as spoken",
          "we need make sure" in html)
    check("publish: doubled word still removed", "the the" not in html)

    # The two legitimate bracket forms must still survive the publish step.
    marker_cues = [P.Cue(1, "00:00:00.000", "00:00:04.000",
                         f"Alpha pays {MARKER} for it.")]
    mj = PublishJudgment.from_json({
        "title": "T", "sections": [{"level": 2, "title": "S", "start_entry": 1}],
        "paragraph_breaks": [1],
        "non_speech": [],
    })
    check("publish: [unintelligible] passes through untouched",
          MARKER in build_html(marker_cues, mj, title="T"))


def test_publish_deletion_is_opt_in():
    """publish must destroy nothing unless --delete-working is passed.

    Previously working files were deleted by default and Archived_Captions was
    emptied unconditionally, as the FIRST action of the run — so a publish that
    failed part-way left the user with neither transcripts nor originals.
    """
    import tempfile, shutil
    from pipeline.batch import main as batch_main

    def make_workdir(root: Path) -> dict[str, Path]:
        dirs = {name: root / name for name in
                ("Edited_Captions", "Archived_Captions",
                 "VTT_Files", "HTML_Transcripts")}
        for d in dirs.values():
            d.mkdir(parents=True)
        (dirs["Edited_Captions"] / "A.vtt").write_text(
            "WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\nHello there.\n")
        (dirs["Edited_Captions"] / "FlagLog_A.txt").write_text("log\n")
        (dirs["Archived_Captions"] / "original.srt").write_text("orig\n")
        return dirs

    def run(dirs, *extra):
        return batch_main(["publish",
                           "--edited", str(dirs["Edited_Captions"]),
                           "--vttout", str(dirs["VTT_Files"]),
                           "--html", str(dirs["HTML_Transcripts"]),
                           "--archive", str(dirs["Archived_Captions"]),
                           *extra])

    # --- default: nothing is deleted ---
    tmp = Path(tempfile.mkdtemp())
    try:
        dirs = make_workdir(tmp)
        rc = run(dirs)
        check("publish cli: default run succeeds", rc == 0)
        check("publish cli: transcript written",
              (dirs["HTML_Transcripts"] / "Transcript_A.html").exists())
        check("publish cli: vtt archived", (dirs["VTT_Files"] / "A.vtt").exists())
        # The decisive assertions.
        check("publish cli: working vtt KEPT by default",
              (dirs["Edited_Captions"] / "A.vtt").exists())
        check("publish cli: flag log KEPT by default",
              (dirs["Edited_Captions"] / "FlagLog_A.txt").exists())
        check("publish cli: Archived_Captions NOT emptied by default",
              (dirs["Archived_Captions"] / "original.srt").exists())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- --keep-working still accepted (back-compat no-op) ---
    tmp = Path(tempfile.mkdtemp())
    try:
        dirs = make_workdir(tmp)
        check("publish cli: --keep-working still parses",
              run(dirs, "--keep-working") == 0)
        check("publish cli: --keep-working keeps files",
              (dirs["Edited_Captions"] / "A.vtt").exists())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- --delete-working: cleanup happens, transcripts survive ---
    tmp = Path(tempfile.mkdtemp())
    try:
        dirs = make_workdir(tmp)
        check("publish cli: --delete-working succeeds",
              run(dirs, "--delete-working") == 0)
        check("publish cli: working vtt deleted on request",
              not (dirs["Edited_Captions"] / "A.vtt").exists())
        check("publish cli: flag log deleted on request",
              not (dirs["Edited_Captions"] / "FlagLog_A.txt").exists())
        check("publish cli: Archived_Captions emptied on request",
              not (dirs["Archived_Captions"] / "original.srt").exists())
        # Outputs must survive the cleanup.
        check("publish cli: transcript survives cleanup",
              (dirs["HTML_Transcripts"] / "Transcript_A.html").exists())
        check("publish cli: archived vtt survives cleanup",
              (dirs["VTT_Files"] / "A.vtt").exists())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_title_transform():
    check("title: camel split",
          title_from_stem("MSAS-603_M2_AuditRisk") == "Transcript MSAS-603 M2 Audit Risk")
    check("title: chapter abbrev",
          "Ch.20" in title_from_stem("MBA-6008_M3_Kotler_Chapter20_WhyToGoGlobal"))


if __name__ == "__main__":
    for fn in [test_parse, test_clean, test_captioner_markers, test_naming,
               test_vtt, test_flaglog, test_flaglog_scoping,
               test_apply_judgment, test_publish,
               test_publish_never_adds_text, test_publish_deletion_is_opt_in,
               test_title_transform]:
        print(f"\n# {fn.__name__}")
        fn()
    print(f"\n{'ALL PASSED' if check.failed == 0 else str(check.failed) + ' FAILED'}")
    sys.exit(1 if check.failed else 0)
