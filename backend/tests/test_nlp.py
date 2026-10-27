import pytest

from backend.nlp.intent_classifier import IntentClassifier, train_model
from backend.nlp.pipeline import analyze, split_clauses
from backend.nlp.result import NLPStatus
from backend.nlp.training.train import load_training_data


@pytest.fixture(scope="module")
def clf():
    texts, labels = load_training_data()
    return IntentClassifier(train_model(texts, labels))


# ---- deterministic (no model) ----
def test_split_three_actions():
    assert len(split_clauses("Find PDFs, open the largest, and move the rest to Archive")) == 3


def test_list_of_files_is_one_clause():
    assert len(split_clauses("Open a.pdf, b.pdf, and c.pdf")) == 1


# ---- safety: must always hold ----
@pytest.mark.parametrize("text", [
    "Don't delete report.pdf",
    "Do not move budget.xlsx to Archive",
    "never rename notes.txt to old.txt",
    "Don't open report.pdf",
])
def test_negated_request_is_never_ok(clf, text):
    assert analyze(text, clf).status != NLPStatus.OK


@pytest.mark.parametrize("text", [
    "Delete", "Move to Archive", "Rename report.pdf", "Create a folder",
    "Delete the rest",            # nothing earlier for "the rest" to refer to
    "What is the weather in Pune",
])
def test_incomplete_or_unsupported_is_not_ok(clf, text):
    assert analyze(text, clf).status != NLPStatus.OK


# ---- accuracy: if these fail, add training examples or tune thresholds ----
@pytest.mark.parametrize("text, intent", [
    ("Open report.pdf", "OPEN"),
    ("Delete report.pdf", "DELETE"),
    ("Rename report.pdf to final.pdf", "RENAME"),
    ("Create a folder named Projects", "CREATE_FOLDER"),
    ("Copy report.pdf to the clipboard", "COPY_TO_CLIPBOARD"),
])
def test_clear_requests(clf, text, intent):
    r = analyze(text, clf)
    assert r.status == NLPStatus.OK and r.clauses[0].intent == intent


def test_multi_step(clf):
    r = analyze("Find PDFs, open the largest, and move the rest to Archive", clf)
    assert [c.intent for c in r.clauses] == ["SEARCH", "OPEN", "MOVE"]
    assert r.status == NLPStatus.OK

def test_quoted_text_is_never_split():
    assert len(split_clauses("In notes.txt add 'buy milk and delete files'")) == 1


def test_create_then_edit_is_two_clauses():
    assert len(split_clauses("Create a text file named notes.txt and add 'hi' to it")) == 2


def test_edit_request(clf):
    r = analyze("In hii.txt add 'yo i am varun'", clf)
    assert r.status == NLPStatus.OK and r.clauses[0].intent == "EDIT_TEXT_FILE"
    assert r.clauses[0].entities.texts == ["yo i am varun"]


@pytest.mark.parametrize("text", [
    "Add 'hello'",                       # no file
    "Edit notes.txt",                    # no change given
    "Delete the last line of notes.txt", # must never become a file delete
    "Don't add 'x' to notes.txt",
])
def test_unsafe_or_incomplete_edit_is_not_ok(clf, text):
    assert analyze(text, clf).status != NLPStatus.OK