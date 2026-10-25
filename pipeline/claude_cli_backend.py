"""Claude-plan judgment backend: AI cleanup with NO API key.

Fills the same JudgmentBackend contract as APIBackend (cleanup / publish), but
instead of calling the Anthropic API with a key, it runs the Claude Code
command-line tool (`claude -p`) that is already installed and signed in on this
Mac. Usage counts against your Claude plan's normal limits, not an API bill.

How each call works:
  * The rules + prompt (the same text APIBackend sends) go in as the system
    prompt, replacing Claude Code's default coding-assistant prompt.
  * The caption cues go in on stdin.
  * All tools are switched off (`--tools ""`, no MCP servers), so Claude can
    only read the text it is given and reply. It cannot open, change or run
    anything on this computer.
  * Claude Code runs in an empty temporary folder, so no project files or
    CLAUDE.md from this repo are pulled in.
  * ANTHROPIC_API_KEY is removed from the child's environment, so Claude Code
    always uses your plan login, never an API key that happens to be set.

Requirements: Claude Code installed and signed in (`claude` then `/login`).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .api_backend import _extract_json, APIBackendError
from .judgment import CleanupJudgment, PublishJudgment, cues_as_prompt_text
from .parse import Cue

# The skill runs its judgment as sub-agents inside a Claude Code session,
# so they inherit that session's model -- Opus. This backend was passing
# sonnet, and the difference showed up as exactly the knowledge-shaped
# misses you would expect: "642 H" left unformatted where the skill wrote
# "642(h)", "fact base case" left where the skill wrote "fact-based".
# Opus fixes both and punctuates better besides. Override per run with
# CAPTION_CLAUDE_MODEL.
DEFAULT_MODEL = "opus"            # Claude Code model alias
DEFAULT_EFFORT = "high"           # the continuation/capitalization sweep
                                  # is methodical work over every adjacent
                                  # pair; at default effort the model finds
                                  # the obvious name fixes and little else
DEFAULT_TIMEOUT = 600             # seconds per file
_PKG = Path(__file__).resolve().parent
_CLEANUP_RULES = _PKG.parent / "rules" / "Caption_Cleanup_Rules.md"
_PUBLISH_RULES = _PKG.parent / "rules" / "Transcript_Publish_Rules.md"
_PROMPTS = _PKG / "prompts"

# Where the Claude Code installers put the binary, for when the app is started
# without the user's normal shell PATH (e.g. from Finder).
_CANDIDATES = [
    "~/.local/bin/claude",
    "~/.claude/local/claude",
    "/opt/homebrew/bin/claude",
    "/usr/local/bin/claude",
    "~/.npm-global/bin/claude",
]


class ClaudeCLIError(APIBackendError):
    pass


# Claude Code validates its reply against these schemas (--json-schema), so the
# cleanup answer always comes back as well-formed JSON with the right keys.
_STR, _INT = {"type": "string"}, {"type": "integer"}
CLEANUP_SCHEMA = {
    "type": "object",
    "properties": {
        "corrections": {"type": "array", "items": {
            "type": "object",
            "properties": {"entry": _INT, "find": _STR, "replace": _STR,
                           "reason": _STR, "confidence": _STR},
            "required": ["entry", "find", "replace", "reason"]}},
        "flags": {"type": "array", "items": {
            "type": "object",
            "properties": {"entry": _INT, "found": _STR, "issue": _STR,
                           "possible": _STR, "timecode": _STR},
            "required": ["entry", "found", "issue", "possible"]}},
    },
    "required": ["corrections", "flags"],
}
_LAST_REPLY = Path.home() / ".config" / "caption-to-transcript" / "last_ai_reply.txt"


def _save_reply(text: str) -> str:
    """Keep the raw reply of a failed call so the problem can be diagnosed."""
    try:
        _LAST_REPLY.parent.mkdir(parents=True, exist_ok=True)
        _LAST_REPLY.write_text(text, encoding="utf-8")
        return str(_LAST_REPLY)
    except OSError:
        return ""


# --- cues prompt file (index<TAB>text; a cue's text may itself wrap) --------

_CUE_LINE_RE = re.compile(r"^(\d+)\t(.*)$")


def _parse_cue_text(text: str) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    idx, buf = None, []
    for line in text.split("\n"):
        m = _CUE_LINE_RE.match(line)
        if m:
            if idx is not None:
                entries.append((idx, "\n".join(buf)))
            idx, buf = int(m.group(1)), [m.group(2)]
        elif idx is not None:
            buf.append(line)
    if idx is not None:
        entries.append((idx, "\n".join(buf)))
    return entries


def _apply_to_cue_text(text: str, corrections: list[dict]) -> str:
    """Fold a pass's corrections into the cues text, so the next pass reads
    what the file will actually say rather than the original."""
    entries = _parse_cue_text(text)
    by = dict(entries)
    for c in corrections:
        e, f, r = c.get("entry"), c.get("find"), c.get("replace")
        if e in by and f and r is not None and f in by[e]:
            by[e] = by[e].replace(f, r, 1)
    return "\n".join(f"{i}\t{by[i]}" for i, _ in entries)


def find_claude() -> str | None:
    """Return the path to the `claude` command, or None if not installed."""
    found = shutil.which("claude")
    if found:
        return found
    for c in _CANDIDATES:
        p = Path(c).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return None


def _child_env() -> dict:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)   # always use the plan login
    return env


def auth_status() -> dict:
    """{'found': bool, 'path': str, 'logged_in': bool, 'method': str, 'message': str}.

    Uses `claude auth status`, which prints JSON and exits 0 only when signed in.
    """
    path = find_claude()
    if not path:
        return {"found": False, "path": "", "logged_in": False, "method": "none",
                "message": "Claude Code is not installed on this Mac."}
    try:
        r = subprocess.run([path, "auth", "status"], capture_output=True,
                           text=True, timeout=20, env=_child_env())
    except Exception as e:  # noqa: BLE001
        return {"found": True, "path": path, "logged_in": False, "method": "unknown",
                "message": f"Could not check sign-in: {e}"}
    method = "unknown"
    try:
        method = json.loads(r.stdout or "{}").get("authMethod", "unknown")
    except json.JSONDecodeError:
        pass
    ok = r.returncode == 0
    if ok and method in ("claude.ai", "oauth_token"):
        msg = "Signed in with your Claude plan."
    elif ok:
        msg = f"Signed in ({method}). This may bill an API account, not your plan."
    else:
        msg = "Claude Code is installed but not signed in. In Terminal run: claude  then type /login"
    return {"found": True, "path": path, "logged_in": ok, "method": method,
            "message": msg}


class ClaudeCLIBackend:
    def __init__(self, model: str | None = None, timeout: int = DEFAULT_TIMEOUT,
                 progress=None, **_ignored):
        self.claude = find_claude()
        if not self.claude:
            raise ClaudeCLIError(
                "Claude Code was not found. Install it from "
                "https://code.claude.com, then run `claude` in Terminal and "
                "type /login.")
        self.model = model or os.environ.get("CAPTION_CLAUDE_MODEL", DEFAULT_MODEL)
        self.effort = os.environ.get("CAPTION_CLAUDE_EFFORT", DEFAULT_EFFORT)
        self.timeout = timeout
        self.progress = progress or (lambda msg: print(msg))
        self._cleanup_rules_text = (
            _CLEANUP_RULES.read_text(encoding="utf-8") if _CLEANUP_RULES.exists() else "")
        self._publish_rules_text = (
            _PUBLISH_RULES.read_text(encoding="utf-8") if _PUBLISH_RULES.exists() else "")

    def _system_for(self, prompt_file: str) -> str:
        tmpl = (_PROMPTS / prompt_file).read_text(encoding="utf-8")
        tmpl = tmpl.replace("{RULES}", self._cleanup_rules_text)
        tmpl = tmpl.replace("{PUBLISH_RULES}", self._publish_rules_text)
        return tmpl + ("\n\nReply with the JSON object only - no prose, "
                       "no code fences.")

    def _ask(self, prompt_file: str, user: str, schema: dict | None = None) -> dict:
        """One call, retried once if the reply is not usable JSON."""
        try:
            return self._ask_once(prompt_file, user, schema)
        except ClaudeCLIError as first:
            if not getattr(first, "retryable", False):
                raise
            self.progress("  ...the AI's reply was not valid JSON - asking again")
            return self._ask_once(prompt_file, user, schema)

    def _ask_once(self, prompt_file: str, user: str, schema: dict | None) -> dict:
        """One judgment, done the way the caption-cleanup skill does it.

        The cues go into a file and Claude is asked to read it and write its
        judgment back as a file, with Read and Write available in an otherwise
        empty temp folder. Inlining the cues and demanding one JSON reply --
        which is what this did before -- cannot carry a full lecture: on a
        271-entry file the reply petered out after a couple of entries, where
        the skill's per-file agent produced 96 corrections on the same input.
        Writing to a file lets the model work through every entry instead of
        fitting them all into one answer.
        """
        with tempfile.TemporaryDirectory(prefix="caption-claude-") as tmp:
            tmpdir = Path(tmp)
            sys_file = tmpdir / "system.md"
            sys_file.write_text(self._system_for(prompt_file), encoding="utf-8")
            cues_file = tmpdir / "cues.txt"
            cues_file.write_text(user, encoding="utf-8")
            out_file = tmpdir / "judgment.json"

            instruction = (
                f"Read {cues_file.name}. It holds every caption entry for one file.\n\n"
                "Apply the rules in your system prompt to EVERY entry in it, first "
                "to last. Working only the opening entries is the most common way "
                "to get this wrong: a long file normally yields dozens of "
                "corrections spread across its whole length.\n\n"
                f"Write your judgment as a single JSON object to {out_file.name}, "
                "in the shape your system prompt specifies. Do not put the JSON in "
                "your reply; the file is the output. When you are done, reply with "
                "nothing but a one-line count, e.g. DONE: 96 corrections, 18 flags."
            )

            cmd = [self.claude, "-p",
                   "--output-format", "json",
                   "--model", self.model,
                   "--system-prompt-file", str(sys_file),
                   # Read and Write only, in a temp folder holding nothing but
                   # this file's cues. --restricted also drops the
                   # command-running tools and ignores user/project settings,
                   # so the run does not vary with local configuration.
                   "--tools", "Read,Write",
                   "--effort", self.effort,
                   "--permission-mode", "acceptEdits",
                   "--restricted",
                   "--strict-mcp-config",
                   "--disable-slash-commands",
                   "--no-session-persistence"]
            try:
                r = subprocess.run(cmd, input=instruction, capture_output=True,
                                   text=True, timeout=self.timeout, cwd=tmp,
                                   env=_child_env())
            except subprocess.TimeoutExpired:
                raise ClaudeCLIError(
                    f"Claude Code did not answer within {self.timeout}s.")

            out = (r.stdout or "").strip()
            try:
                envelope = json.loads(out)
            except json.JSONDecodeError:
                envelope = {}
            result = envelope.get("result", out)
            if envelope.get("is_error") or r.returncode != 0:
                raise ClaudeCLIError(
                    "Claude Code reported an error: "
                    f"{str(result or envelope.get('subtype') or r.stderr)[:600]}")

            # The file is the output. Fall back to the reply only if it never
            # got written, so an older-style answer still works.
            if out_file.exists():
                raw = out_file.read_text(encoding="utf-8")
            else:
                raw = str(result)

        try:
            return _extract_json(raw)
        except (APIBackendError, json.JSONDecodeError) as e:
            saved = _save_reply(raw)
            err = ClaudeCLIError(
                "The AI's reply could not be read as JSON, even after asking twice. "
                "Nothing was changed; your caption file is still in Raw_Captions, "
                "so you can simply run Clean again."
                + (f" (The reply was saved to {saved} for troubleshooting.)" if saved else ""))
            err.retryable = True
            raise err from e

    # -- Per-file judgment, as the caption-cleanup skill runs it -----------

    def _review(self, workdir: Path, read_name: str, write_name: str,
                instruction: str) -> dict:
        """Run one reviewer turn in workdir; return the JSON it wrote."""
        with tempfile.TemporaryDirectory(prefix="caption-claude-") as tmp:
            sys_file = Path(tmp) / "system.md"
            sys_file.write_text(self._system_for("corrections.md"), encoding="utf-8")
            cmd = [self.claude, "-p",
                   "--output-format", "json",
                   "--model", self.model,
                   "--effort", self.effort,
                   "--system-prompt-file", str(sys_file),
                   "--tools", "Read,Write",
                   "--permission-mode", "acceptEdits",
                   "--restricted",
                   "--strict-mcp-config",
                   "--disable-slash-commands",
                   "--no-session-persistence"]
            try:
                r = subprocess.run(cmd, input=instruction, capture_output=True,
                                   text=True, timeout=self.timeout,
                                   cwd=str(workdir), env=_child_env())
            except subprocess.TimeoutExpired:
                raise ClaudeCLIError(f"{read_name}: no answer within {self.timeout}s.")

        out_path = workdir / write_name
        if not out_path.exists():
            detail = (r.stdout or r.stderr or "")[:300]
            raise ClaudeCLIError(f"{read_name}: no judgment file written. {detail}")
        try:
            data = _extract_json(out_path.read_text(encoding="utf-8"))
        except (APIBackendError, json.JSONDecodeError) as e:
            raise ClaudeCLIError(f"{read_name}: judgment was not valid JSON.") from e
        data.setdefault("corrections", [])
        data.setdefault("flags", [])
        return data

    def judge_file(self, cues_path: Path, out_path: Path) -> tuple[int, int]:
        """Review ONE caption file in two passes, writing one judgment JSON.

        Pass 1 applies the rules across the file. Pass 2 then re-reads the cues
        WITH pass 1's corrections folded in and does only the adjacent-pair
        sweep -- the continuation and capitalization work that
        Caption_Cleanup_Rules.md calls the single most common cleanup miss.

        Two passes because that sweep is a different kind of work: it compares
        neighbours rather than inspecting a cue, and it is only decidable once
        the other corrections are in place, since most continuations need their
        comma created before anything can be lowercased. As one item in a long
        instruction it was consistently the thinnest part of the result.
        """
        workdir = cues_path.parent
        original = cues_path.read_text(encoding="utf-8")
        label = cues_path.name[: -len(".cues.txt")]
        # Several reviewers run at once, so every line names its file.
        self.progress(f"     {label}: pass 1 of 2 — reviewing the whole file")

        first = self._review(
            workdir, cues_path.name, out_path.name,
            f"Read {cues_path.name}. It holds every caption entry for one "
            "lecture.\n\n"
            "Your system prompt contains the complete cleanup rules. Apply ALL "
            "of them to EVERY entry, first to last — not a selection of the "
            "rules, and not only the opening entries. A lecture-length file "
            "normally yields dozens of corrections spread over its whole "
            "length.\n\n"
            "Correct at 90% confidence or higher. Anything less certain is a "
            "flag for the reviewer, not a guess. An unfamiliar proper noun is a "
            "flag: do not replace a name you do not recognise with a marker.\n\n"
            f"Write the judgment as one JSON object to {out_path.name}, in the "
            "shape your system prompt specifies. The file is the output — do "
            "not put the JSON in your reply. Finish with only a count line: "
            "DONE: <n> corrections, <n> flags.")

        self.progress(f"     {label}: pass 1 found {len(first['corrections'])} "
                      f"correction(s), {len(first['flags'])} flag(s) — "
                      f"now sweeping sentence breaks")

        # Pass 2 reads the file as pass 1 will leave it.
        pass2_cues = workdir / f"{cues_path.name[:-len('.cues.txt')]}.pass2.txt"
        pass2_out = f"{out_path.name[:-len('.json')]}.pass2.json"
        pass2_cues.write_text(
            _apply_to_cue_text(original, first["corrections"]), encoding="utf-8")

        try:
            second = self._review(
                workdir, pass2_cues.name, pass2_out,
                f"Read {pass2_cues.name}. These captions have already had one "
                "cleanup pass; what you see is their current text.\n\n"
                "Do ONE job: walk every adjacent pair of entries, first to "
                "last, and decide whether the sentence carries across the "
                "break.\n"
                "  * If it does, the earlier entry must not end with a full "
                "stop — make it a comma or nothing — and the next entry's "
                "first word must be lowercase unless it is a proper noun.\n"
                "  * If it does not, the earlier entry should close properly "
                "and the next should start with a capital.\n\n"
                "Watch for a next-entry opening with a conjunction (and, but, "
                "or, so, yet, while, although, because, since, when); these "
                "almost always continue the previous entry.\n\n"
                "Report ONLY changes of this kind; everything else has been "
                "handled. Each correction's `find` must appear verbatim in the "
                "entry you name, as the text now reads.\n\n"
                f"Write them as one JSON object to {pass2_out}, same shape. The "
                "file is the output. Finish with only: DONE: <n> corrections.")
        except ClaudeCLIError as e:
            # The sweep is an improvement, not a precondition — keep pass 1.
            self.progress(f"  (second pass skipped: {e})")
            second = {"corrections": [], "flags": []}

        # Pass 1 first, so pass 2's find strings match once pass 1 has landed.
        merged = {
            "corrections": list(first["corrections"]) + list(second["corrections"]),
            "flags": list(first["flags"]),
        }
        seen = {(f.get("entry"), f.get("found")) for f in merged["flags"]}
        for f in second["flags"]:
            if (f.get("entry"), f.get("found")) not in seen:
                merged["flags"].append(f)

        out_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        pass2_cues.unlink(missing_ok=True)
        (workdir / pass2_out).unlink(missing_ok=True)
        return len(merged["corrections"]), len(merged["flags"])

    # -- JudgmentBackend ----------------------------------------------------

    def cleanup(self, cues: list[Cue], context: dict) -> CleanupJudgment:
        """The JudgmentBackend entry point, used by `batch.py clean
        --backend claude`.

        It runs the same two-pass per-file review as judge_file, which the GUI
        calls directly. Routing both through one implementation keeps the
        command line and the window honest about meaning the same thing by
        `--backend claude`; before this, the CLI got a single thin call.
        """
        if not cues:
            return CleanupJudgment()
        stem = context.get("stem") or "captions"
        with tempfile.TemporaryDirectory(prefix="caption-judge-") as tmp:
            cues_path = Path(tmp) / f"{stem}.cues.txt"
            cues_path.write_text(cues_as_prompt_text(cues), encoding="utf-8")
            out_path = Path(tmp) / f"{stem}.judgment.json"
            self.judge_file(cues_path, out_path)
            data = json.loads(out_path.read_text(encoding="utf-8"))
        return CleanupJudgment.from_json(data)

    def publish(self, cues: list[Cue], context: dict) -> PublishJudgment:
        if not cues:
            return PublishJudgment(title=context.get("title", ""))
        self.progress("  ...asking Claude (your plan) for section headings")
        data = self._ask("headings.md", "CUES:\n" + cues_as_prompt_text(cues))
        data.setdefault("title", context.get("title", ""))
        return PublishJudgment.from_json(data)
