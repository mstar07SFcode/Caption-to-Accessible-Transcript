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
import shutil
import subprocess
import tempfile
from pathlib import Path

from .api_backend import _extract_json, APIBackendError
from .judgment import CleanupJudgment, PublishJudgment, cues_as_prompt_text
from .parse import Cue

DEFAULT_MODEL = "sonnet"          # Claude Code model alias
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
        with tempfile.TemporaryDirectory(prefix="caption-claude-") as tmp:
            sys_file = Path(tmp) / "system.md"
            sys_file.write_text(self._system_for(prompt_file), encoding="utf-8")
            cmd = [self.claude, "-p",
                   "--output-format", "json",
                   "--model", self.model,
                   "--system-prompt-file", str(sys_file),
                   "--tools", "",
                   "--strict-mcp-config",
                   "--disable-slash-commands",
                   "--no-session-persistence"]
            if schema:
                cmd += ["--json-schema", json.dumps(schema)]
            try:
                r = subprocess.run(cmd, input=user, capture_output=True,
                                   text=True, timeout=self.timeout, cwd=tmp,
                                   env=_child_env())
            except subprocess.TimeoutExpired:
                raise ClaudeCLIError(
                    f"Claude Code did not answer within {self.timeout}s.")
        out = (r.stdout or "").strip()
        try:
            envelope = json.loads(out)
        except json.JSONDecodeError:
            raise ClaudeCLIError(
                "Claude Code returned an unexpected reply "
                f"(exit {r.returncode}):\n{(out or r.stderr)[:600]}")
        result = envelope.get("result", "")
        if envelope.get("is_error") or r.returncode != 0:
            raise ClaudeCLIError(
                "Claude Code reported an error: "
                f"{str(result or envelope.get('subtype') or r.stderr)[:600]}")
        structured = envelope.get("structured_output")
        if isinstance(structured, dict):
            return structured
        try:
            return _extract_json(result)
        except (APIBackendError, json.JSONDecodeError) as e:
            saved = _save_reply(str(result))
            err = ClaudeCLIError(
                "The AI's reply could not be read as JSON, even after asking twice. "
                "Nothing was changed; your caption file is still in Raw_Captions, "
                "so you can simply run Clean again."
                + (f" (The reply was saved to {saved} for troubleshooting.)" if saved else ""))
            err.retryable = True
            raise err from e

    # -- JudgmentBackend ----------------------------------------------------

    def cleanup(self, cues: list[Cue], context: dict) -> CleanupJudgment:
        if not cues:
            return CleanupJudgment()
        self.progress("  ...asking Claude (your plan) to review this file - "
                      "usually under a minute")
        data = self._ask("corrections.md", "CUES:\n" + cues_as_prompt_text(cues),
                         schema=CLEANUP_SCHEMA)
        return CleanupJudgment.from_json(data)

    def publish(self, cues: list[Cue], context: dict) -> PublishJudgment:
        if not cues:
            return PublishJudgment(title=context.get("title", ""))
        self.progress("  ...asking Claude (your plan) for section headings")
        data = self._ask("headings.md", "CUES:\n" + cues_as_prompt_text(cues))
        data.setdefault("title", context.get("title", ""))
        return PublishJudgment.from_json(data)
