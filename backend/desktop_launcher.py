import os
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


def wait_for_backend(timeout: float = 10.0) -> bool:
    """Waits for the local backend to be healthy before opening the window."""
    start = time.time()
    url = f"http://{settings.smart_manager_host}:{settings.smart_manager_port}/api/health"
    while time.time() - start < timeout:
        try:
            res = httpx.get(url, timeout=1.0)
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

    # 1. Start backend in background thread
    server_thread = threading.Thread(target=run_backend_server, daemon=True)
    server_thread.start()

    # 2. Verify backend availability
    if not wait_for_backend():
        print("ERROR: Backend failed to start within timeout.")
        sys.exit(1)

    print("Backend ready at http://127.0.0.1:8765")

    # 3. Determine frontend URL
    # If production dist exists, we serve it or use dev URL
    dist_index = project_root / "frontend" / "dist" / "index.html"
    window_url = "http://127.0.0.1:5173"  # Default Vite dev server

    # If dist index exists and vite dev is not running, we can open dist or local dev
    try:
        res = httpx.get("http://127.0.0.1:5173", timeout=0.5)
        if res.status_code == 200:
            window_url = "http://127.0.0.1:5173"
        elif dist_index.exists():
            window_url = f"file:///{str(dist_index).replace(os.sep, '/')}"
    except Exception:
        if dist_index.exists():
            window_url = f"file:///{str(dist_index).replace(os.sep, '/')}"

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
