"""Evaluate the WHOLE pipeline, not just the classifier.

    python -m backend.nlp.training.evaluate           # the report
    python -m backend.nlp.training.evaluate --sweep   # how the file-change threshold trades off

'critical' = a file-changing action was approved but it was not what the phrase meant.
That number must be 0.
"""
from __future__ import annotations

import json
import sys

from backend.nlp import confidence
from backend.nlp.intent_classifier import IntentClassifier, train_model
from backend.nlp.intents import MUTATING_INTENTS, SAME_ACTION, UNSUPPORTED
from backend.nlp.pipeline import analyze
from backend.nlp.result import NLPStatus

from .train import EVAL_PATH, load_training_data


def _same(a: str, b: str) -> bool:
    return a == b or frozenset({a, b}) in SAME_ACTION


def evaluate(clf, rows: list[dict]) -> dict:
    out = {"correct": [], "refused_ok": [], "asked": [],
           "wrong_readonly": [], "critical": [], "skipped": []}
    for row in rows:
        text, expected = row["text"], row["intent"]
        result = analyze(text, clf)
        if len(result.clauses) != 1:
            out["skipped"].append(text)
            continue
        c = result.clauses[0]
        if c.status == NLPStatus.OK:
            if _same(c.intent, expected):
                out["correct"].append(text)
            elif c.intent in MUTATING_INTENTS:
                out["critical"].append(f"{text}   expected={expected}  approved={c.intent}")
            else:
                out["wrong_readonly"].append(f"{text}   expected={expected}  got={c.intent}")
        elif expected == UNSUPPORTED:
            out["refused_ok"].append(text)
        else:
            out["asked"].append(f"{text}   ({c.status.value}) {c.reason}")
    return out


def sweep(clf, rows: list[dict]) -> None:
    original = confidence.MIN_CONFIDENCE_MUTATING
    try:
        print("MIN_CONFIDENCE_MUTATING   right   asked   CRITICAL")
        for value in (0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
            confidence.MIN_CONFIDENCE_MUTATING = value
            out = evaluate(clf, rows)
            print(f"{value:>20.2f} {len(out['correct']):>7} {len(out['asked']):>7} "
                  f"{len(out['critical']):>10}")
    finally:
        confidence.MIN_CONFIDENCE_MUTATING = original


def main() -> int:
    texts, labels = load_training_data()
    clf = IntentClassifier(train_model(texts, labels))
    rows = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    if "--sweep" in sys.argv:
        sweep(clf, rows)
        return 0
    out = evaluate(clf, rows)

    total = len(rows) - len(out["skipped"])
    print(f"{total} phrases through the full pipeline\n")
    for key, label in (("correct", "approved with the right action"),
                       ("refused_ok", "unsupported, correctly refused"),
                       ("asked", "supported but I asked or refused (safe, a bit annoying)"),
                       ("wrong_readonly", "wrong read-only action approved (harmless)"),
                       ("critical", "WRONG FILE CHANGE APPROVED  <- must be 0")):
        print(f"  {len(out[key]):>4}  {label}")
    for key in ("critical", "wrong_readonly", "asked"):
        if out[key]:
            print(f"\n{key}:")
            for line in out[key]:
                print("   ", line)
    return 1 if out["critical"] else 0


if __name__ == "__main__":
    sys.exit(main())