"""Evaluate the WHOLE pipeline, not just the classifier.

    python -m backend.nlp.training.evaluate

'critical' = a file-changing action was approved but it was not what the phrase meant.
That number must be 0.
"""
from __future__ import annotations

import json
import sys

from backend.nlp.intent_classifier import train_model
from backend.nlp.intents import MUTATING_INTENTS, UNSUPPORTED
from backend.nlp.pipeline import analyze
from backend.nlp.result import NLPStatus

from .train import EVAL_PATH, load_training_data


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
            if c.intent == expected:
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


def main() -> int:
    texts, labels = load_training_data()
    clf_model = train_model(texts, labels)

    from backend.nlp.intent_classifier import IntentClassifier
    rows = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    out = evaluate(IntentClassifier(clf_model), rows)

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