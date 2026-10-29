from __future__ import annotations

import argparse
from pathlib import Path

from backend.nlp.intent_classifier import IntentClassifier, ModelNotTrainedError
from backend.security.config import load_config, sandbox_config
from backend.security.errors import SecurityError
from backend.security.paths import PathPolicy
from backend.services.assistant import Assistant

PROJECT = Path(__file__).resolve().parents[1]


def _show_recovery(assistant: Assistant) -> None:
    reports, errors = assistant.interrupted()
    for msg in errors:
        print(f"[journal] couldn't read {msg}")
    for rep in reports:
        print(f"\n[!] An earlier run didn't finish ({Path(rep.run_path).name}).")
        for s in rep.unknown:
            print(f"    step {s.index}: {s.description}\n      -> {s.state}: {s.note}")
        if rep.undo_steps:
            print(f"    {len(rep.undo_steps)} step(s) from that run can be undone.")
        assistant.dismiss_interrupted(rep.run_path)
        print("    (I won't show this again.)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Smart Manager (command line)")
    ap.add_argument("--sandbox", help="Allow ONLY this folder. Recommended for testing.")
    args = ap.parse_args()

    try:
        classifier = IntentClassifier.load()
    except ModelNotTrainedError as exc:
        print(exc)
        return 1
    try:
        cfg = sandbox_config(args.sandbox) if args.sandbox else load_config()
    except SecurityError as exc:
        print(exc)
        return 1
    policy = PathPolicy(cfg)
    print("Allowed folders:\n  " + "\n  ".join(str(p) for p in cfg.allowed_roots))
    if not args.sandbox and input("These are your real folders. Continue? [y/N] ").lower() != "y":
        return 0

    assistant = Assistant(classifier, policy, journal_dir=PROJECT / "data" / "journal",
                          backup_dir=PROJECT / "data" / "backups")
    _show_recovery(assistant)
    print("\nType a request, 'undo', or 'quit'.")

    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line.lower() in ("quit", "exit"):
            return 0
        if line.lower() == "undo":
            steps = assistant.undo_preview()
            if not steps:
                print("Nothing to undo.")
                continue
            print("This would:\n  " + "\n  ".join(steps))
            if input("Undo? [y/N] ").lower() == "y":
                for o in assistant.undo_last(confirmed=True):
                    print(f"  [{o.status}] {o.message}")
            continue
        turn = assistant.handle(line)
        print("\n" + turn.message)
        if turn.kind == "needs_approval":
            if input("\nApprove exactly this? [y/N] ").lower() == "y":
                print("\n" + assistant.approve(turn.turn_id, turn.digest).message)
            else:
                assistant.reject(turn.turn_id)
                print("Cancelled. Nothing was changed.")


if __name__ == "__main__":
    raise SystemExit(main())