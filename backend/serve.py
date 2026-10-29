from __future__ import annotations

import argparse
import secrets
from pathlib import Path

import uvicorn

from backend.api.app import create_app
from backend.nlp.intent_classifier import IntentClassifier, ModelNotTrainedError
from backend.security.config import load_config, sandbox_config
from backend.security.errors import SecurityError
from backend.security.paths import PathPolicy
from backend.services.assistant import Assistant

PROJECT = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Smart Manager local API")
    ap.add_argument("--sandbox", help="Allow ONLY this folder (recommended for testing).")
    ap.add_argument("--allow-real-folders", action="store_true",
                    help="Required to run on your real folders when no sandbox is given.")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    if not args.sandbox and not args.allow_real_folders:
        print("Refusing to start on your real folders. Use --sandbox FOLDER, "
              "or add --allow-real-folders.")
        return 1
    try:
        classifier = IntentClassifier.load()
        cfg = sandbox_config(args.sandbox) if args.sandbox else load_config()
    except (ModelNotTrainedError, SecurityError) as exc:
        print(exc)
        return 1

    assistant = Assistant(classifier, PathPolicy(cfg),
                          journal_dir=PROJECT / "data" / "journal",
                          backup_dir=PROJECT / "data" / "backups")
    token = secrets.token_urlsafe(32)               # new every launch; the UI will receive it
    app = create_app(assistant, token)
    print("Allowed folders:\n  " + "\n  ".join(str(p) for p in cfg.allowed_roots))
    print(f"\nListening on http://127.0.0.1:{args.port}  (this machine only)")
    print(f"Session token (development only): {token}")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")   # host is fixed
    return 0


if __name__ == "__main__":
    raise SystemExit(main())