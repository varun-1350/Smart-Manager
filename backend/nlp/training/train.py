from __future__ import annotations

import json
from pathlib import Path

import joblib
from sklearn.metrics import classification_report

from backend.nlp.confidence import MUTATING_INTENTS
from backend.nlp.entity_extractor import mask_entities
from backend.nlp.intent_classifier import MODEL_PATH, train_model

HERE = Path(__file__).parent
TRAIN_PATH = HERE / "intents.json"
EVAL_PATH = HERE / "eval_set.json"


def load_training_data(path: Path = TRAIN_PATH) -> tuple[list[str], list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    texts, labels = [], []
    for intent, examples in data.items():
        for example in examples:
            texts.append(example)
            labels.append(intent)
    return texts, labels


def load_eval_data(path: Path = EVAL_PATH) -> tuple[list[str], list[str]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [r["text"] for r in rows], [r["intent"] for r in rows]


def main() -> None:
    train_x, train_y = load_training_data()
    eval_x, eval_y = load_eval_data()

    leaked = set(t.casefold() for t in train_x) & set(t.casefold() for t in eval_x)
    if leaked:
        print(f"WARNING: {len(leaked)} eval sentences also appear in training: {sorted(leaked)}")

    model = train_model(train_x, train_y)
    predicted = model.predict([mask_entities(t) for t in eval_x])

    print(f"Training examples: {len(train_x)}   Eval examples: {len(eval_x)}\n")
    print(classification_report(eval_y, predicted, zero_division=0))

    print("Dangerous errors (a file-changing intent predicted when it should NOT be):")
    bad = [(t, y, p) for t, y, p in zip(eval_x, eval_y, predicted)
           if p in MUTATING_INTENTS and p != y]
    for text, true, pred in bad:
        print(f"  '{text}'  true={true}  predicted={pred}")
    if not bad:
        print("  none")

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"\nSaved model to {MODEL_PATH}")


if __name__ == "__main__":
    main()