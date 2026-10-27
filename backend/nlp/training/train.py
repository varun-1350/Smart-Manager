
import json
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline


HERE = Path(__file__).resolve().parent
DATASET_PATH = HERE / "intents.json"
MODEL_PATH = HERE.parent / "intent_model.joblib"


def main():
    with DATASET_PATH.open("r", encoding="utf-8") as file:
        examples = json.load(file)

    texts = [item["text"] for item in examples]
    labels = [item["intent"] for item in examples]

    # Keep examples from every intent in both splits.
    X_train, X_test, y_train, y_test = train_test_split(
        texts,
        labels,
        test_size=0.25,
        random_state=42,
        stratify=labels,
    )

    model = Pipeline([
        (
            "tfidf",
            TfidfVectorizer(
                lowercase=True,
                ngram_range=(1, 2),
                strip_accents="unicode",
            ),
        ),
        (
            "classifier",
            LogisticRegression(
                max_iter=1000,
                class_weight="balanced",
                random_state=42,
            ),
        ),
    ])

    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    print(f"Training examples: {len(X_train)}")
    print(f"Test examples: {len(X_test)}")
    print("\nHeld-out classification report:")
    print(classification_report(
        y_test,
        predictions,
        zero_division=0,
    ))

    joblib.dump(model, MODEL_PATH)
    print(f"\nModel saved to: {MODEL_PATH}")


if __name__ == "__main__":
    main()
