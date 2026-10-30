from __future__ import annotations

import argparse
import secrets
import socket
import threading
import time
from pathlib import Path

import uvicorn

from backend.api.app import create_app
from backend.nlp.intent_classifier import ModelNotTrainedError
from backend.security.errors import SecurityError
from backend.serve import StartupError, build_assistant

DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


class JsApi:
    """The only thing the page may ask the desktop shell for: the session token."""

    def __init__(self, token: str):
        self._token = token          # underscore: pywebview doesn't expose it by name

    def get_token(self) -> str:
        return self._token


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Smart Manager desktop app")
    ap.add_argument("--sandbox", help="Allow ONLY this folder (recommended for testing).")
    ap.add_argument("--allow-real-folders", action="store_true")
    args = ap.parse_args()

    if not (DIST / "index.html").is_file():
        print("The interface isn't built yet. Run:\n"
              "  cd frontend\n  npm install\n  npm run build")
        return 1
    try:
        import webview
    except ImportError:
        print("pywebview isn't installed. Run:  pip install pywebview")
        return 1
    try:
        assistant, cfg = build_assistant(args.sandbox, args.allow_real_folders)
    except (ModelNotTrainedError, SecurityError, StartupError) as exc:
        print(exc)
        return 1

    token = secrets.token_urlsafe(32)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(assistant, token), host="127.0.0.1",
                                           port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    else:
        print("The local server didn't start.")
        return 1

    print("Allowed folders:\n  " + "\n  ".join(str(p) for p in cfg.allowed_roots))
    url = f"http://127.0.0.1:{port}/"
    options = dict(js_api=JsApi(token), width=1000, height=760, min_size=(700, 500))
    try:
        webview.create_window("Smart Manager", url, text_select=True, **options)
    except TypeError:        # an older pywebview without this option
        webview.create_window("Smart Manager", url, **options)
    webview.start()
    server.should_exit = True
    thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())