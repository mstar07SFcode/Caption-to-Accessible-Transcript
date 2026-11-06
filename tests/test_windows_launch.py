"""Tests for running the backend on Windows.

The whole point is machines this suite does not run on, so os.name and the
filesystem are stubbed. What is being checked is the one thing that is not
obvious from reading the code: npm installs Claude Code on Windows as
`claude.cmd`, and a batch file cannot be handed to CreateProcess -- it has
to go through cmd.exe, or subprocess dies with WinError 193 however correct
the path is.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import claude_cli_backend as ccb


def _as_windows(monkeypatch):
    monkeypatch.setattr(ccb, "_on_windows", lambda: True)


# ---- launch_argv -------------------------------------------------

def test_a_cmd_shim_is_run_through_cmd_exe(monkeypatch):
    _as_windows(monkeypatch)
    argv = ccb.launch_argv(r"C:\Users\me\AppData\Roaming\npm\claude.cmd")
    assert argv[:3] == ["cmd", "/d", "/c"]
    assert argv[3].endswith("claude.cmd")


def test_a_bat_shim_is_wrapped_too(monkeypatch):
    _as_windows(monkeypatch)
    assert ccb.launch_argv(r"C:\tools\claude.BAT")[:3] == ["cmd", "/d", "/c"]


def test_a_real_exe_is_not_wrapped(monkeypatch):
    """Wrapping an .exe would work but costs a shell and mangles quoting."""
    _as_windows(monkeypatch)
    assert ccb.launch_argv(r"C:\tools\claude.exe") == [r"C:\tools\claude.exe"]


def test_posix_paths_are_never_wrapped():
    assert ccb.launch_argv("/usr/local/bin/claude") == ["/usr/local/bin/claude"]


def test_a_posix_file_named_cmd_is_not_wrapped(monkeypatch):
    """os.name, not the extension, decides -- or a Mac would shell out too."""
    monkeypatch.setattr(ccb, "_on_windows", lambda: False)
    assert ccb.launch_argv("/opt/claude.cmd") == ["/opt/claude.cmd"]


# ---- find_claude -------------------------------------------------

def test_windows_accepts_a_cmd_that_is_not_marked_executable(monkeypatch,
                                                             tmp_path):
    """os.access(X_OK) answers for the ACL on Windows, not for "can be run",
    so requiring it there would reject a perfectly good claude.cmd."""
    shim = tmp_path / "claude.cmd"
    shim.write_text("@echo off\n", encoding="utf-8")
    os.chmod(shim, 0o644)          # readable, not executable

    _as_windows(monkeypatch)
    monkeypatch.setattr(ccb.shutil, "which", lambda _n: None)
    monkeypatch.setattr(ccb, "_WIN_CANDIDATES", [str(shim)])
    assert ccb.find_claude() == str(shim)


def test_posix_still_requires_the_executable_bit(monkeypatch, tmp_path):
    binary = tmp_path / "claude"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(binary, 0o644)

    monkeypatch.setattr(ccb, "_on_windows", lambda: False)
    monkeypatch.setattr(ccb.shutil, "which", lambda _n: None)
    monkeypatch.setattr(ccb, "_CANDIDATES", [str(binary)])
    assert ccb.find_claude() is None


def test_candidate_paths_are_put_through_expandvars(monkeypatch, tmp_path):
    """%APPDATA%\\npm\\claude.cmd is only a path once the variable is expanded.

    os.path.expandvars understands %VAR% in ntpath and ignores it in
    posixpath, so the real expansion cannot run on this host. What is
    checked here is that find_claude routes every candidate through it --
    the part that is this module's responsibility.
    """
    shim = tmp_path / "claude.cmd"
    shim.write_text("@echo off\n", encoding="utf-8")
    candidate = r"%APPDATA%\npm\claude.cmd"
    seen = []

    def fake_expandvars(s):
        seen.append(s)
        return str(shim) if s == candidate else s

    _as_windows(monkeypatch)
    monkeypatch.setattr(ccb.shutil, "which", lambda _n: None)
    monkeypatch.setattr(ccb.os.path, "expandvars", fake_expandvars)
    monkeypatch.setattr(ccb, "_WIN_CANDIDATES", [candidate])

    assert ccb.find_claude() == str(shim)
    assert candidate in seen, "the candidate never reached expandvars"


# ---- the call sites actually use it ------------------------------

def test_auth_status_invokes_the_shim_through_cmd_exe(monkeypatch):
    """A regression guard: find_claude can be right and the run still fail
    if a call site builds [path, ...] by hand."""
    seen = {}

    def fake_run(cmd, **_kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout='{"authMethod":"claude.ai"}',
                                           stderr="")

    _as_windows(monkeypatch)
    monkeypatch.setattr(ccb, "find_claude", lambda: r"C:\npm\claude.cmd")
    monkeypatch.setattr(ccb.subprocess, "run", fake_run)

    status = ccb.auth_status()
    assert seen["cmd"][:3] == ["cmd", "/d", "/c"]
    assert seen["cmd"][-2:] == ["auth", "status"]
    assert status["logged_in"] is True
