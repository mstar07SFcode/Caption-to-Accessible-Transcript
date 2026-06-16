"""CLI entry points for the three workflow steps.

    python -m pipeline.batch clean        --raw RAW --out EDITED --archive ARCHIVE [--course X]
    python -m pipeline.batch apply-flaglog --edited EDITED
    python -m pipeline.batch publish      --edited EDITED --vttout VTT --html HTML --archive ARCHIVE

Judgment (the LLM step) is pluggable:
  * default            -> StubBackend (deterministic only; fillers + header strip)
  * --judgment-dir DIR -> load <stem>.judgment.json produced by a sub-agent/API
  * --emit-prompts DIR -> also write <stem>.cues.txt for a judge to read

This keeps the same code usable for local (sub-agent) and server (API) modes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import parse as P
from . import naming, vtt as V, files as F
from .clean import clean_cues
from .judgment import (CleanupJudgment, PublishJudgment, StubBackend,
                       cues_as_prompt_text)
from .apply import apply_cleanup
from .flaglog import (write_flaglog, apply_flaglog, format_apply_report)


def make_backend(args):
    """Return the judgment backend selected by --backend (default stub)."""
    if getattr(args, "backend", "stub") == "api":
        from .api_backend import APIBackend, APIBackendError
        try:
            return APIBackend(model=getattr(args, "model", None))
        except APIBackendError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(2)
    return StubBackend()


# --------------------------------------------------------------------------
# clean
# --------------------------------------------------------------------------

def cmd_clean(args) -> int:
    raw = Path(args.raw)
    out = Path(args.out)
    archive = Path(args.archive)
    out.mkdir(parents=True, exist_ok=True)
    backend = make_backend(args)
    jdir = Path(args.judgment_dir) if args.judgment_dir else None
    pdir = Path(args.emit_prompts) if args.emit_prompts else None
    if pdir:
        pdir.mkdir(parents=True, exist_ok=True)

    sources = F.scan_sources(raw)
    if not sources:
        print(f"No source files found in {raw}")
        return 0

    # Phase 1 — collect jobs (parse + deterministic clean + naming).
    jobs = []  # dicts: src, cues, doc, vtt_name, log_name, out_stem
    seen_names: dict[str, str] = {}
    for src in sources:
        text = src.read_text(encoding="utf-8", errors="replace")
        doc = P.parse_source(text, src.name)
        cues = clean_cues(doc.cues)

        folder = F.subfolder_of(src, raw)
        module = naming.module_code_from_folder(folder) if folder else None
        stem = naming.transform_stem(src.name)
        vtt_name = naming.build_vtt_name(stem, course=args.course, module=module)
        out_stem = vtt_name[:-4]

        if vtt_name in seen_names:
            print(f"  WARNING: '{src.name}' maps to '{vtt_name}', already produced "
                  f"from '{seen_names[vtt_name]}'. Likely a duplicate/copy — "
                  f"skipping. Resolve and re-run if both are needed.")
            continue
        seen_names[vtt_name] = src.name

        if pdir:
            (pdir / f"{out_stem}.cues.txt").write_text(
                cues_as_prompt_text(cues), encoding="utf-8")

        jobs.append({"src": src, "cues": cues, "doc": doc,
                     "vtt_name": vtt_name, "log_name": naming.flaglog_name(vtt_name),
                     "out_stem": out_stem})

    # Phase 2 — obtain judgments (batch, per-file API, precomputed, or stub).
    judgments: dict[str, CleanupJudgment] = {}
    use_api = getattr(args, "backend", "stub") == "api"
    if use_api and getattr(args, "batch", False):
        print(f"Submitting {len(jobs)} file(s) as one Message Batch (50% cost)...")
        judgments = backend.cleanup_batch([(j["out_stem"], j["cues"]) for j in jobs])
    else:
        for j in jobs:
            jf = jdir / f"{j['out_stem']}.judgment.json" if jdir else None
            if jf and jf.exists():
                judgments[j["out_stem"]] = CleanupJudgment.from_json(
                    json.loads(jf.read_text()))
            else:
                judgments[j["out_stem"]] = backend.cleanup(j["cues"], {})

    # Phase 3 — apply, write outputs, archive sources.
    summary = []
    for j in jobs:
        judgment = judgments.get(j["out_stem"], CleanupJudgment())
        cues, corrections, reviews = apply_cleanup(j["cues"], judgment)
        vtt_text = V.write_vtt(
            cues,
            speaker=args.speaker or j["doc"].meta.get("speaker", ""),
            course=args.course or j["doc"].meta.get("course", ""))
        (out / j["vtt_name"]).write_text(vtt_text, encoding="utf-8")
        (out / j["log_name"]).write_text(
            write_flaglog(j["src"].name, corrections, reviews), encoding="utf-8")
        if not args.no_archive:
            F.archive_source(j["src"], raw, archive)
        summary.append((j["vtt_name"], len(corrections), len(reviews)))

    if not args.no_archive:
        F.prune_empty_dirs(raw)

    print(f"Cleaned {len(summary)} file(s):")
    for name, ncorr, nrev in summary:
        print(f"  {name} — {ncorr} correction(s), {nrev} flag(s) for review")
    return 0


# --------------------------------------------------------------------------
# apply-flaglog
# --------------------------------------------------------------------------

def cmd_apply_flaglog(args) -> int:
    edited = Path(args.edited)
    logs = sorted(p for p in edited.glob("FlagLog_*.txt"))
    if not logs:
        print("No FlagLog_*.txt files to apply.")
        return 0

    for log in logs:
        stem = naming.vtt_stem_for_flaglog(log.name)
        vtt_path = edited / f"{stem}.vtt"
        if not vtt_path.exists():
            print(f"  skip {log.name}: no matching {stem}.vtt")
            continue
        result = apply_flaglog(vtt_path.read_text(encoding="utf-8"),
                               log.read_text(encoding="utf-8"))
        vtt_path.write_text(result.new_vtt_text, encoding="utf-8")
        archived = naming.applied_flaglog_name(f"{stem}.vtt")
        log.rename(edited / archived)
        print(format_apply_report(stem, result, archived, str(vtt_path)))
    return 0


# --------------------------------------------------------------------------
# apply-judgment  (Cowork flow: a Claude sub-agent supplies judgment JSON)
# --------------------------------------------------------------------------

def cmd_apply_judgment(args) -> int:
    """Apply <stem>.judgment.json files to the matching VTTs in Edited_Captions,
    rewriting each VTT and its flag log. This is how a plugin user's own Claude
    performs the judgment step without an API key: run `clean --emit-prompts`,
    have Claude write judgment JSON per file, then run this."""
    edited = Path(args.edited)
    jdir = Path(args.judgment_dir)
    vtts = sorted(edited.glob("*.vtt"))
    if not vtts:
        print("No *.vtt files in Edited_Captions.")
        return 0

    applied = 0
    for v in vtts:
        stem = v.name[:-4]
        jf = jdir / f"{stem}.judgment.json"
        if not jf.exists():
            continue
        doc = P.parse_vtt(v.read_text(encoding="utf-8"))
        judgment = CleanupJudgment.from_json(json.loads(jf.read_text()))
        cues, corrections, reviews = apply_cleanup(doc.cues, judgment)
        v.write_text(V.write_vtt(cues, speaker=doc.meta.get("speaker", ""),
                                 course=doc.meta.get("course", "")), encoding="utf-8")
        (edited / naming.flaglog_name(v.name)).write_text(
            write_flaglog(stem, corrections, reviews), encoding="utf-8")
        print(f"  {v.name} — {len(corrections)} correction(s), {len(reviews)} flag(s)")
        applied += 1

    print(f"Applied judgment to {applied} file(s).")
    return 0


# --------------------------------------------------------------------------
# publish
# --------------------------------------------------------------------------

def cmd_publish(args) -> int:
    edited = Path(args.edited)
    vttout = Path(args.vttout)
    htmlout = Path(args.html)
    archive = Path(args.archive)
    vttout.mkdir(parents=True, exist_ok=True)
    htmlout.mkdir(parents=True, exist_ok=True)
    backend = make_backend(args)
    jdir = Path(args.judgment_dir) if args.judgment_dir else None

    # Step 1: empty Archived_Captions.
    removed = F.empty_directory(archive)
    if removed:
        print(f"Emptied Archived_Captions ({len(removed)} item(s)).")

    vtts = sorted(p for p in edited.glob("*.vtt"))
    if not vtts:
        print("No *.vtt files to publish.")
        return 0

    from .publish import build_html, title_from_stem

    # Phase 1 — parse each VTT.
    jobs = []  # dicts: path, doc, stem, title
    for v in vtts:
        doc = P.parse_vtt(v.read_text(encoding="utf-8"))
        stem = v.name[:-4]
        jobs.append({"path": v, "doc": doc, "stem": stem,
                     "title": naming.transcript_html_name(v.name)[:-5]})

    # Phase 2 — obtain publish judgments (batch / per-file / precomputed / stub).
    judgments: dict[str, PublishJudgment] = {}
    use_api = getattr(args, "backend", "stub") == "api"
    if use_api and getattr(args, "batch", False):
        print(f"Submitting {len(jobs)} file(s) as one Message Batch (50% cost)...")
        judgments = backend.publish_batch(
            [(j["stem"], j["doc"].cues, j["title"]) for j in jobs])
    else:
        for j in jobs:
            jf = jdir / f"{j['stem']}.judgment.json" if jdir else None
            if jf and jf.exists():
                judgments[j["stem"]] = PublishJudgment.from_json(json.loads(jf.read_text()))
            else:
                judgments[j["stem"]] = backend.publish(j["doc"].cues, {"title": j["title"]})

    # Phase 3 — render HTML and archive stripped VTTs.
    for j in jobs:
        v, doc = j["path"], j["doc"]
        judgment = judgments.get(j["stem"], PublishJudgment(title=j["title"]))
        html_text = build_html(doc.cues, judgment,
                               speaker=doc.meta.get("speaker", ""),
                               course=doc.meta.get("course", ""),
                               title=title_from_stem(j["stem"]))
        (htmlout / naming.transcript_html_name(v.name)).write_text(
            html_text, encoding="utf-8")
        (vttout / v.name).write_text(
            V.strip_header(v.read_text(encoding="utf-8")), encoding="utf-8")

    # Delete flag logs and working VTTs from edited.
    if not args.keep_working:
        for p in edited.glob("FlagLog_*.txt"):
            p.unlink()
        for p in edited.glob("Applied_FlagLog_*.txt"):
            p.unlink()
        for v in vtts:
            v.unlink()

    print(f"Published {len(vtts)} transcript(s) to {htmlout}")
    return 0


# --------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pipeline.batch")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("clean")
    c.add_argument("--raw", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--archive", required=True)
    c.add_argument("--course", default=None)
    c.add_argument("--speaker", default=None)
    c.add_argument("--backend", choices=["stub", "api"], default="stub")
    c.add_argument("--model", default=None)
    c.add_argument("--batch", action="store_true",
                   help="submit all files as one Message Batch (50% cheaper, async)")
    c.add_argument("--judgment-dir", default=None)
    c.add_argument("--emit-prompts", default=None)
    c.add_argument("--no-archive", action="store_true")
    c.set_defaults(func=cmd_clean)

    a = sub.add_parser("apply-flaglog")
    a.add_argument("--edited", required=True)
    a.set_defaults(func=cmd_apply_flaglog)

    aj = sub.add_parser("apply-judgment")
    aj.add_argument("--edited", required=True)
    aj.add_argument("--judgment-dir", required=True)
    aj.set_defaults(func=cmd_apply_judgment)

    p = sub.add_parser("publish")
    p.add_argument("--edited", required=True)
    p.add_argument("--vttout", required=True)
    p.add_argument("--html", required=True)
    p.add_argument("--archive", required=True)
    p.add_argument("--backend", choices=["stub", "api"], default="stub")
    p.add_argument("--model", default=None)
    p.add_argument("--batch", action="store_true",
                   help="submit all files as one Message Batch (50% cheaper, async)")
    p.add_argument("--judgment-dir", default=None)
    p.add_argument("--keep-working", action="store_true")
    p.set_defaults(func=cmd_publish)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
