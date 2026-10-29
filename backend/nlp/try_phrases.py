from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.nlp.intent_classifier import IntentClassifier
from backend.nlp.intents import LABELS
from backend.nlp.pipeline import analyze


def main() -> int:
    ap = argparse.ArgumentParser(description="Run phrases through the NLP layer")
    ap.add_argument("file", help="text file: one phrase per line, optionally 'phrase | INTENT'")
    args = ap.parse_args()

    clf = IntentClassifier.load()
    misses: dict[str, list[str]] = {}
    total = wrong = 0
    for raw in Path(args.file).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        text, _, expected = (p.strip() for p in line.partition("|"))
        if expected and expected not in LABELS:
            print(f"!! unknown label '{expected}' in: {line}")
            continue
        result = analyze(text, clf)
        total += 1
        parts = [f"{c.intent} {c.confidence:.2f}/{c.margin:.2f} [{c.status.value}]"
                 for c in result.clauses]
        verdict = ""
        if expected and len(result.clauses) == 1:
            if result.clauses[0].intent != expected:
                verdict, wrong = f"   <-- MISS (expected {expected})", wrong + 1
                misses.setdefault(expected, []).append(text)
            else:
                verdict = "   ok"
        print(f"{text}\n    {' | '.join(parts) or 'no clauses'}{verdict}")
        for c in result.clauses:
            if c.reason:
                print(f"    note: {c.reason}")

    print(f"\n{total} phrases, {wrong} wrong intent(s).")
    if misses:
        print("\nPaste into backend/nlp/training/manual_intents.json (merge by label):")
        print(json.dumps(misses, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())