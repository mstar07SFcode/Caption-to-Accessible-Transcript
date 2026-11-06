"""Desktop launcher: starts the local FastAPI server, opens it in a native window.

    python3 -m gui.main

The server binds 127.0.0.1 on a port the OS picks, so two copies never collide
and nothing is reachable from the network. The window is a real app window --
pywebview wraps the system webview (WebKit on macOS, WebView2 on Windows).

If pywebview is not installed, this falls back to opening your default browser,
which is a fine way to develop.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

WINDOW_TITLE = "Caption Transcripts"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                return True
        except OSError:
            time.sleep(0.15)
    return False


class JsApi:
    """Exposed to the page as window.pywebview.api."""

    def __init__(self):
        self.window = None

    base_url = ""

    def open_review(self, flaglog_name):
        """Open the side-by-side review window for one flag log."""
        import webview
        from urllib.parse import quote
        stem = flaglog_name[len("FlagLog_"):-4] if flaglog_name.startswith("FlagLog_") else flaglog_name
        webview.create_window(f"Review - {stem}",
                              f"{self.base_url}/review?file={quote(flaglog_name)}",
                              width=1320, height=880, min_size=(900, 600))
        return True

    def pick_folder(self):
        import webview
        # pywebview 6 replaced FOLDER_DIALOG with FileDialog.FOLDER. The old
        # constant still works but prints a deprecation warning on every open,
        # and requirements-gui.txt allows 5.x, so prefer the enum and fall back.
        kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
        if kind is None:
            kind = webview.FOLDER_DIALOG
        result = self.window.create_file_dialog(kind)
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result


def _serve_in_browser(url: str, why: str) -> int:
    """Run headless: keep the server alive and let the default browser be the UI.

    The page already covers the two things pywebview provides: Change folder
    falls back to a typed path (index.html checks window.pywebview first), and
    the review window opens as a browser tab instead of its own window. So
    this is the whole app, not a degraded preview of it.
    """
    import webbrowser
    print(why)
    print(f"Opening in your browser instead:\n  {url}")
    print("Leave this window open while you work. Press Ctrl+C to quit.")
    webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0


def main() -> int:
    try:
        import uvicorn
    except ImportError:
        print("ERROR: uvicorn is not installed.")
        print("Run:  pip install -r requirements-gui.txt")
        return 1

    from gui.app import app

    port = _free_port()
    url = f"http://127.0.0.1:{port}"

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    if not _wait_for_server(port):
        print("ERROR: the local server did not start.")
        return 1

    try:
        import webview
    except ImportError:
        return _serve_in_browser(url, "pywebview is not installed.")

    api = JsApi()
    api.base_url = url
    api.window = webview.create_window(WINDOW_TITLE, url, width=1000, height=820,
                                       min_size=(760, 600), js_api=api)
    # Let the review window's Apply/Undo refresh this main window immediately.
    import gui.app as app_module

    def _push_refresh():
        try:
            api.window.evaluate_js(
                "window.onExternalChange && window.onExternalChange()")
        except Exception:
            pass
    app_module.notify_main = _push_refresh

    try:
        webview.start()
    except webview.WebViewException as e:
        # Raised from guilib.initialize() inside start(), once it has tried
        # every GUI toolkit for this platform and found none. The server is
        # already serving, so fall back rather than die.
        return _serve_in_browser(url, f"No app window is available here: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
