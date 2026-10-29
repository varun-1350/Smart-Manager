import json

import pytest

from backend.nlp.confidence import Confidence
from backend.nlp.entity_extractor import extract_entities
from backend.nlp.intent_classifier import IntentClassifier, train_model
from backend.nlp.intents import has_trigger
from backend.nlp.negation import negated_intents
from backend.nlp.pipeline import analyze
from backend.nlp.result import NLPStatus
from backend.nlp.training.evaluate import evaluate
from backend.nlp.training.train import EVAL_PATH, load_training_data


@pytest.fixture(scope="module")
def clf():
    texts, labels = load_training_data()
    return IntentClassifier(train_model(texts, labels))


class Stub:
    def __init__(self, intent):
        self.intent = intent

    def predict(self, text):
        return Confidence(self.intent, 0.95, "UNSUPPORTED", 0.9)


def test_no_eval_phrase_is_approved_as_the_wrong_file_change(clf):
    rows = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    report = evaluate(clf, rows)
    assert report["critical"] == [], "\n".join(report["critical"])


# ---- the word check
@pytest.mark.parametrize("intent, text, expected", [
    ("MOVE", "put filetoken in archive", True),
    ("MOVE", "duplicate filetoken into travel", False),
    ("MOVE", "clone filetoken into travel", False),
    ("DELETE", "throw away filetoken", True),
    ("DELETE", "get rid of filetoken", True),
    ("DELETE", "send filetoken to the recycle bin", True),
    ("DELETE", "open the newest binary", False),
    ("RENAME", "retitle filetoken to filetoken", True),
    ("RENAME", "pull up filetoken", False),
    ("EDIT_TEXT_FILE", "read quotedtoken aloud", False),
    ("CREATE_FOLDER", "open the newest", False),
    ("OPEN", "anything at all", True),        # read-only intents need no special word
])
def test_has_trigger(intent, text, expected):
    assert has_trigger(intent, text) is expected


def test_a_move_without_a_move_word_is_not_approved():
    r = analyze("duplicate a.pdf into Travel", Stub("MOVE"))
    assert r.status == NLPStatus.NEEDS_CLARIFICATION
    assert "move" in r.clauses[0].reason


def test_a_real_move_still_passes():
    assert analyze("put a.pdf in Archive", Stub("MOVE")).status == NLPStatus.OK


# ---- new phrasings
def test_put_in_means_destination():
    e = extract_entities("put a.pdf in Archive")
    assert e.destination == "Archive" and e.locations == [] and e.filenames == ["a.pdf"]


def test_recycle_bin_is_not_a_folder():
    e = extract_entities("put photo.png in the recycle bin")
    assert e.locations == [] and e.destination is None


def test_renamed_and_retitle_forms():
    assert extract_entities("i want a.txt renamed to b.txt").new_name == "b.txt"
    assert extract_entities("retitle a.txt to b.txt").new_name == "b.txt"


def test_negated_new_verbs():
    assert "MOVE" in negated_intents("Don't put a.pdf in Archive")
    assert negated_intents("don't throw away a.pdf") == {"DELETE"}
    assert negated_intents("don't get rid of a.pdf") == {"DELETE"}