from __future__ import annotations

from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from .confidence import Confidence, summarize
from .entity_extractor import mask_entities

MODEL_PATH = Path(__file__).parent / "models" / "intent_model.joblib"


class ModelNotTrainedError(RuntimeError):
    pass


def build_model() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(lowercase=True, ngram_range=(1, 2), sublinear_tf=True)),
        ("clf", LogisticRegression(C=10, max_iter=1000, class_weight="balanced")),
    ])


def train_model(texts: list[str], labels: list[str]) -> Pipeline:
    """Always train on MASKED text, the same transform used at prediction time."""
    model = build_model()
    model.fit([mask_entities(t) for t in texts], labels)
    return model


class IntentClassifier:
    def __init__(self, model: Pipeline):
        self._model = model

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "IntentClassifier":
        if not path.exists():
            raise ModelNotTrainedError(
                f"No model at {path}. Run: python -m backend.nlp.training.train"
            )
        return cls(joblib.load(path))

    def predict(self, text: str) -> Confidence:
        probs = self._model.predict_proba([mask_entities(text)])[0]
        return summarize(self._model.classes_, probs)