"""API key storage.

Three places a key can come from, in priority order:

  1. The OS keychain (macOS Keychain / Windows Credential Manager) via `keyring`
  2. The ANTHROPIC_API_KEY environment variable
  3. Typed into the window this session, held in memory only

The key is NEVER written to a plain file in the repo or the working folder. If
`keyring` is not installed the app still works -- it just forgets the key when
you close the window, and says so.
"""

from __future__ import annotations

import os

SERVICE = "caption-transcripts"
ACCOUNT = "anthropic-api-key"

_memory: dict[str, str] = {"key": ""}


def keyring_available() -> bool:
    try:
        import keyring
        # An unusable backend (headless Linux, locked keychain) still imports,
        # so confirm a real one is wired up.
        backend = keyring.get_keyring()
        name = type(backend).__name__
        return "fail" not in name.lower()
    except Exception:
        return False


def load() -> tuple[str, str]:
    """Return (key, source). source is one of: keychain, env, session, none."""
    if _memory["key"]:
        return _memory["key"], _memory.get("source", "session")

    if keyring_available():
        try:
            import keyring
            stored = keyring.get_password(SERVICE, ACCOUNT)
            if stored:
                _memory["key"] = stored
                _memory["source"] = "keychain"
                return stored, "keychain"
        except Exception:
            pass

    env = os.environ.get("ANTHROPIC_API_KEY", "")
    if env:
        _memory["key"] = env
        _memory["source"] = "env"
        return env, "env"

    return "", "none"


def save(key: str, remember: bool) -> str:
    """Store the key. Returns the source it ended up in."""
    key = (key or "").strip()
    _memory["key"] = key
    # The pipeline reads the key from the environment, so mirror it there.
    if key:
        os.environ["ANTHROPIC_API_KEY"] = key
    else:
        os.environ.pop("ANTHROPIC_API_KEY", None)

    if remember and key and keyring_available():
        try:
            import keyring
            keyring.set_password(SERVICE, ACCOUNT, key)
            _memory["source"] = "keychain"
            return "keychain"
        except Exception:
            pass

    if not remember:
        forget(clear_memory=False)

    _memory["source"] = "session"
    return "session"


def forget(clear_memory: bool = True) -> None:
    """Remove the key from the keychain (and optionally from memory)."""
    if keyring_available():
        try:
            import keyring
            keyring.delete_password(SERVICE, ACCOUNT)
        except Exception:
            pass  # not stored; nothing to remove
    if clear_memory:
        _memory["key"] = ""
        _memory["source"] = "none"
        os.environ.pop("ANTHROPIC_API_KEY", None)


def looks_like_key(key: str) -> bool:
    return bool(key) and key.strip().startswith("sk-ant-") and len(key.strip()) > 20


def verify(key: str) -> tuple[bool, str]:
    """Check a key against the API without spending tokens.

    models.list() is a metadata call, so this costs nothing but proves the key
    is real, active, and reachable from this machine.
    """
    key = (key or "").strip()
    if not key:
        return False, "No key entered."
    try:
        import anthropic
    except ImportError:
        return False, ("The 'anthropic' package is not installed in this "
                       "environment. Reinstall with requirements-gui.txt.")
    try:
        client = anthropic.Anthropic(api_key=key)
        models = client.models.list(limit=1)
        n = len(getattr(models, "data", []) or [])
        return True, ("Key works." if n else "Key accepted.")
    except Exception as e:
        name = type(e).__name__
        msg = str(e)
        if "authentication" in msg.lower() or "401" in msg or "invalid" in msg.lower():
            return False, "That key was rejected. Check you copied all of it."
        if "connect" in msg.lower() or "network" in msg.lower():
            return False, "Could not reach the API. Check your internet connection."
        return False, f"{name}: {msg[:180]}"
