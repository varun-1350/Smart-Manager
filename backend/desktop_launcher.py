import os
import secrets
import sys
import threading
import time
from pathlib import Path
import uvicorn
import webview
import httpx

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent
project_root = backend_dir.parent
sys.path.insert(0, str(backend_dir))

from config import settings
from app import app


def run_backend_server():
    """Starts the FastAPI backend on loopback interface."""
    uvicorn.run(
        app,
        host=settings.smart_manager_host,
        port=settings.smart_manager_port,
        log_level="warning",
    )


def wait_for_backend(timeout: float = 10.0, session_secret: str | None = None) -> bool:
    """Waits for the local backend to be healthy before opening the window."""
    start = time.time()
    url = f"http://{settings.smart_manager_host}:{settings.smart_manager_port}/api/health"
    headers = {"X-Smart-Manager-Session": session_secret} if session_secret else None
    while time.time() - start < timeout:
        try:
            # Packaged mode authenticates every loopback API request, including
            # this launcher readiness probe.
            res = httpx.get(url, timeout=1.0, headers=headers)
            if res.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def main():
    print("=========================================================")
    print("      Starting Smart Manager Windows Desktop Agent       ")
    print("=========================================================")

    # The embedded UI receives this one-time token in its private launch URL;
    # the backend rejects unauthenticated loopback API calls.
    session_secret = secrets.token_urlsafe(32)
    os.environ["API_SESSION_SECRET"] = session_secret
    settings.api_session_secret = session_secret

    # 1. Start backend in background thread
    server_thread = threading.Thread(target=run_backend_server, daemon=True)
    server_thread.start()

    # 2. Verify backend availability
    if not wait_for_backend(session_secret=session_secret):
        print("ERROR: Backend failed to start within timeout.")
        sys.exit(1)

    print("Backend ready at http://127.0.0.1:8765")

    # 3. Determine frontend URL
    # By default, use the local backend which serves the built frontend directly
    window_url = f"http://{settings.smart_manager_host}:{settings.smart_manager_port}/?sm_session={session_secret}"

    # If developer explicitly started Vite dev server on 5173, use it for HMR
    try:
        res = httpx.get("http://127.0.0.1:5173", timeout=0.3)
        if res.status_code == 200:
            window_url = f"http://127.0.0.1:5173/?sm_session={session_secret}"
    except Exception:
        pass

    print(f"Launching desktop window pointing to: {window_url}")

    # 4. Create native Windows desktop window using Edge WebView2
    window = webview.create_window(
        title="Smart Manager — Autonomous Local AI Agent",
        url=window_url,
        width=1280,
        height=840,
        min_size=(900, 600),
        background_color="#0a0d14",
    )

    # 5. Start WebView2 event loop
    webview.start(gui="edgechromium")


if __name__ == "__main__":
    main()
