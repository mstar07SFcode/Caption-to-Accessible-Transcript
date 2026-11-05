"""Tests for the Claude Code CLI backend's timeout handling.

No `claude` binary and no network: find_claude and subprocess.run are both
stubbed, so what these exercise is the backend's own judgement -- whether a
reviewer pass that ran out of time left anything worth keeping, and whether
the caller is told it is worth asking again.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import claude_cli_backend as ccb

JUDGMENT = {"corrections": [{"entry": 1, "find": "texter", "replace": "texture",
                             "reason": "misheard word"}],
            "flags": []}


def _backend(monkeypatch, **kwargs):
    monkeypatch.setattr(ccb, "find_claude", lambda: "/nonexistent/claude")
    return ccb.ClaudeCLIBackend(progress=lambda _m: None, **kwargs)


def _timeout_after(monkeypatch, backend, writes=None, where=None):
    """Make subprocess.run write `writes` (if given), then time out."""
    def fake_run(cmd, **_kw):
        if writes is not None:
            where.write_text(writes, encoding="utf-8")
        raise subprocess.TimeoutExpired(cmd, backend.timeout)
    monkeypatch.setattr(ccb.subprocess, "run", fake_run)


def test_timeout_keeps_a_judgment_already_written(monkeypatch, tmp_path):
    """The judgment is a file, not a reply: a reviewer that finished the
    work and hung on its closing turn has still done the work."""
    backend = _backend(monkeypatch)
    _timeout_after(monkeypatch, backend, json.dumps(JUDGMENT),
                   tmp_path / "out.json")

    data = backend._review(tmp_path, "cues.txt", "out.json", "review this")

    assert len(data["corrections"]) == 1
    assert data["corrections"][0]["replace"] == "texture"
    assert data["flags"] == []


def test_timeout_with_nothing_written_is_retryable(monkeypatch, tmp_path):
    backend = _backend(monkeypatch)
    _timeout_after(monkeypatch, backend)

    with pytest.raises(ccb.ClaudeCLIError) as excinfo:
        backend._review(tmp_path, "cues.txt", "out.json", "review this")

    assert getattr(excinfo.value, "retryable", False) is True
    assert "no answer within" in str(excinfo.value)


def test_timeout_with_half_written_judgment_is_retryable(monkeypatch, tmp_path):
    """Killed mid-write, the file is there but unreadable -- not salvage."""
    backend = _backend(monkeypatch)
    _timeout_after(monkeypatch, backend, '{"corrections": [{"entry"',
                   tmp_path / "out.json")

    with pytest.raises(ccb.ClaudeCLIError) as excinfo:
        backend._review(tmp_path, "cues.txt", "out.json", "review this")

    assert getattr(excinfo.value, "retryable", False) is True


def test_a_non_timeout_failure_is_not_retryable(monkeypatch, tmp_path):
    """An empty workdir with no timeout is a real failure; retrying it
    would only burn another full timeout for the same answer."""
    backend = _backend(monkeypatch)
    monkeypatch.setattr(ccb.subprocess, "run",
                        lambda cmd, **_kw: subprocess.CompletedProcess(
                            cmd, 0, stdout="", stderr=""))

    with pytest.raises(ccb.ClaudeCLIError) as excinfo:
        backend._review(tmp_path, "cues.txt", "out.json", "review this")

    assert getattr(excinfo.value, "retryable", False) is False
    assert "no judgment file written" in str(excinfo.value)


def test_timeout_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("CAPTION_CLAUDE_TIMEOUT", "99")
    assert _backend(monkeypatch).timeout == 99


def test_explicit_timeout_beats_the_environment(monkeypatch):
    monkeypatch.setenv("CAPTION_CLAUDE_TIMEOUT", "99")
    assert _backend(monkeypatch, timeout=5).timeout == 5


def test_a_nonsense_timeout_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("CAPTION_CLAUDE_TIMEOUT", "whenever")
    assert _backend(monkeypatch).timeout == ccb.DEFAULT_TIMEOUT
