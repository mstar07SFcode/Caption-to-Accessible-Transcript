"""Anthropic API judgment backend.

Fills the same JudgmentBackend contract the StubBackend does, but by calling the
Anthropic Messages API. This lets the standalone launchers (which run outside
Claude/Cowork) perform the full AI cleanup. On the server, the same class is the
judgment layer.

Dependencies: the `anthropic` package (imported lazily so the rest of the
pipeline stays dependency-free). An API key is read from the ANTHROPIC_API_KEY
environment variable unless passed explicitly.
"""

from __future__ import annotations

import json
import os
import sys
import re
from pathlib import Path

from .judgment import (CleanupJudgment, PublishJudgment, cues_as_prompt_text,
                       PASS2_SECTIONS, _apply_to_cue_text, _select_sections)
from .parse import Cue

DEFAULT_MODEL = "claude-sonnet-5"
_PKG = Path(__file__).resolve().parent
_CLEANUP_RULES = _PKG.parent / "rules" / "Caption_Cleanup_Rules.md"
_PUBLISH_RULES = _PKG.parent / "rules" / "Transcript_Publish_Rules.md"
_PROMPTS = _PKG / "prompts"


class APIBackendError(RuntimeError):
    pass


def _extract_json(text: str) -> dict:
    """Parse a JSON object from a model response, tolerating fences/prose."""
    text = text.strip()
    # Strip ```json ... ``` fences if present.
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the outermost { ... } span.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise APIBackendError("Model did not return parseable JSON:\n" + text[:500])


class APIBackend:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 max_tokens: int = 8000, poll_interval: int = 15):
        try:
            import anthropic  # lazy
        except ImportError as e:
            raise APIBackendError(
                "The 'anthropic' package is not installed. Run the AI setup "
                "launcher, or: pip install anthropic"
            ) from e
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise APIBackendError(
                "No API key. Set ANTHROPIC_API_KEY or pass api_key."
            )
        self._client = anthropic.Anthropic(api_key=key)
        self.model = model or os.environ.get("CAPTION_PIPELINE_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens
        self.poll_interval = poll_interval
        self._cleanup_rules_text = (
            _CLEANUP_RULES.read_text(encoding="utf-8") if _CLEANUP_RULES.exists() else "")
        self._publish_rules_text = (
            _PUBLISH_RULES.read_text(encoding="utf-8") if _PUBLISH_RULES.exists() else "")

    # -- prompt assembly ----------------------------------------------------

    def _system_for(self, prompt_file: str, rules: str | None = None) -> str:
        tmpl = (_PROMPTS / prompt_file).read_text(encoding="utf-8")
        tmpl = tmpl.replace("{RULES}", self._cleanup_rules_text if rules is None else rules)
        return tmpl.replace("{PUBLISH_RULES}", self._publish_rules_text)

    def _system_blocks(self, prompt_file: str, rules: str | None = None) -> list[dict]:
        """System prompt as a cacheable content block.

        cache_control:ephemeral lets the (identical, ~5k-token) rules+prompt be
        reused across files in a run, billing the cached read at ~10% of input.
        Blocks below the cache minimum (~1k tokens) are simply not cached.
        """
        return [{"type": "text", "text": self._system_for(prompt_file, rules),
                 "cache_control": {"type": "ephemeral"}}]

    def _params(self, system_blocks: list[dict], user: str) -> dict:
        return {"model": self.model, "max_tokens": self.max_tokens,
                "system": system_blocks,
                "messages": [{"role": "user", "content": user}]}

    def _ask(self, system_blocks: list[dict], user: str) -> dict:
        resp = self._client.messages.create(**self._params(system_blocks, user))
        text = "".join(getattr(b, "text", "") for b in resp.content)
        return _extract_json(text)

    # -- JudgmentBackend (synchronous, one call per file) -------------------

    def cleanup(self, cues: list[Cue], context: dict) -> CleanupJudgment:
        """Two passes, matching what the Claude-plan backend does.

        An API key used to get a single call over the whole file, which on a
        lecture-length transcript returns a handful of corrections near the
        start. The second pass re-reads the cues with pass 1's corrections
        folded in and does only the adjacent-pair sweep, which is undecidable
        until the other corrections land -- most continuations need their comma
        created before anything can be lowercased.

        No tools here, so unlike the CLI reviewer this one cannot grep the file
        for how a name is rendered elsewhere. The pass structure is the same.
        """
        if not cues:
            return CleanupJudgment()
        original = cues_as_prompt_text(cues)
        first = self._ask(self._system_blocks("corrections.md"),
                          "CUES:\n" + original)
        first.setdefault("corrections", [])
        first.setdefault("flags", [])

        staged = _apply_to_cue_text(original, first["corrections"])
        sweep_rules = _select_sections(self._cleanup_rules_text, PASS2_SECTIONS)
        try:
            second = self._ask(
                self._system_blocks("corrections.md", rules=sweep_rules),
                "These captions have already had one cleanup pass; this is "
                "their current text.\n\n"
                "Do ONE job: walk every adjacent pair of entries, first to "
                "last, and decide whether the sentence carries across the "
                "break. If it does, the earlier entry must not end with a full "
                "stop and the next entry's first word is lowercase unless it "
                "is a proper noun. If it does not, the earlier entry closes "
                "and the next starts with a capital.\n\n"
                "Report ONLY changes of this kind. Each `find` must appear "
                "verbatim in the entry you name, as the text now reads.\n\n"
                "CUES:\n" + staged)
            second.setdefault("corrections", [])
            second.setdefault("flags", [])
        except Exception as e:
            # The sweep is an improvement, not a precondition: keep pass 1 and
            # say so, rather than silently returning a thinner judgment that
            # looks like the reviewer simply found less.
            print(f"  WARNING: the second pass failed ({type(e).__name__}: {e}); "
                  f"keeping the first pass's corrections.", file=sys.stderr)
            second = {"corrections": [], "flags": []}

        # Pass 1 first, so pass 2's find strings match once pass 1 has applied.
        merged = {"corrections": list(first["corrections"]) + list(second["corrections"]),
                  "flags": list(first["flags"])}
        seen = {(f.get("entry"), f.get("found")) for f in merged["flags"]}
        for f in second["flags"]:
            if (f.get("entry"), f.get("found")) not in seen:
                merged["flags"].append(f)
        return CleanupJudgment.from_json(merged)

    def publish(self, cues: list[Cue], context: dict) -> PublishJudgment:
        if not cues:
            return PublishJudgment(title=context.get("title", ""))
        user = "CUES:\n" + cues_as_prompt_text(cues)
        data = self._ask(self._system_blocks("headings.md"), user)
        data.setdefault("title", context.get("title", ""))
        return PublishJudgment.from_json(data)

    # -- Batch API (50% cheaper; async, polled) -----------------------------

    def _run_batch(self, requests: list[dict], label: str) -> dict[str, dict]:
        """Submit a Message Batch, poll to completion, return {custom_id: json}."""
        import time
        if not requests:
            return {}
        batch = self._client.messages.batches.create(requests=requests)
        start = time.time()
        while True:
            b = self._client.messages.batches.retrieve(batch.id)
            if getattr(b, "processing_status", None) == "ended":
                break
            elapsed = int(time.time() - start)
            print(f"  ...{label} batch processing ({elapsed}s elapsed)")
            time.sleep(self.poll_interval)
        out: dict[str, dict] = {}
        for r in self._client.messages.batches.results(batch.id):
            rtype = r.result.type
            if rtype == "succeeded":
                text = "".join(getattr(b, "text", "") for b in r.result.message.content)
                try:
                    out[r.custom_id] = _extract_json(text)
                except APIBackendError:
                    out[r.custom_id] = {"_error": "unparseable"}
            else:
                out[r.custom_id] = {"_error": rtype}
        return out

    def cleanup_batch(self, items: list[tuple[str, list[Cue]]]
                      ) -> dict[str, CleanupJudgment]:
        """items: (file_id, cues). Returns {file_id: CleanupJudgment}."""
        sys_blocks = self._system_blocks("corrections.md")
        reqs, idmap = [], {}
        for i, (fid, cues) in enumerate(items):
            if not cues:
                continue
            safe = f"r{i}"            # custom_id must be ^[a-zA-Z0-9_-]{1,64}$
            idmap[safe] = fid
            reqs.append({"custom_id": safe,
                         "params": self._params(sys_blocks, "CUES:\n" + cues_as_prompt_text(cues))})
        raw = self._run_batch(reqs, "cleanup")
        out: dict[str, CleanupJudgment] = {}
        for safe, data in raw.items():
            fid = idmap[safe]
            out[fid] = (CleanupJudgment() if "_error" in data
                        else CleanupJudgment.from_json(data))
        for fid, _ in items:
            out.setdefault(fid, CleanupJudgment())
        return out

    def publish_batch(self, items: list[tuple[str, list[Cue], str]]
                      ) -> dict[str, PublishJudgment]:
        """items: (file_id, cues, title). Returns {file_id: PublishJudgment}."""
        sys_blocks = self._system_blocks("headings.md")
        reqs, idmap, titles = [], {}, {}
        for i, (fid, cues, title) in enumerate(items):
            titles[fid] = title
            if not cues:
                continue
            safe = f"r{i}"
            idmap[safe] = fid
            reqs.append({"custom_id": safe,
                         "params": self._params(sys_blocks, "CUES:\n" + cues_as_prompt_text(cues))})
        raw = self._run_batch(reqs, "publish")
        out: dict[str, PublishJudgment] = {}
        for safe, data in raw.items():
            fid = idmap[safe]
            if "_error" in data:
                out[fid] = PublishJudgment(title=titles[fid])
            else:
                data.setdefault("title", titles[fid])
                out[fid] = PublishJudgment.from_json(data)
        for fid, _, title in items:
            out.setdefault(fid, PublishJudgment(title=title))
        return out
