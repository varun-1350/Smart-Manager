from backend.nlp.negation import find_negated_actions, negated_intents


def test_dont_delete():
    assert find_negated_actions("Don't delete report.pdf") == {"delete"}


def test_do_not_with_filler():
    assert find_negated_actions("Please do not ever remove Budget.xlsx") == {"remove"}


def test_plain_command_not_negated():
    assert find_negated_actions("Delete report.pdf") == set()


def test_mixed_blocks_only_delete():
    assert negated_intents("Don't delete notes.txt, move it to Archive") == {"DELETE"}


def test_copy_covers_both_clipboard_intents():
    assert negated_intents("never copy notes.txt") == {
        "COPY_TO_CLIPBOARD", "COPY_PATH_TO_CLIPBOARD"}

def test_payload_text_is_not_negation():
    assert find_negated_actions("in notes.txt add 'do not delete anything'") == set()


def test_negated_edit():
    assert negated_intents("Don't add 'x' to notes.txt") == {"EDIT_TEXT_FILE"}