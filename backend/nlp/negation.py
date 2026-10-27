import re
from .entity_extractor import blank_quoted
# verb the user might say -> the intents that verb could mean
VERB_TO_INTENTS: dict[str, frozenset[str]] = {
    "find": frozenset({"SEARCH"}), "search": frozenset({"SEARCH"}),
    "locate": frozenset({"SEARCH"}),
    "list": frozenset({"LIST"}), "show": frozenset({"LIST"}),
    "display": frozenset({"LIST"}),
    "open": frozenset({"OPEN"}), "launch": frozenset({"OPEN"}),
    "create": frozenset({"CREATE_FOLDER", "CREATE_TEXT_FILE"}),
    "make": frozenset({"CREATE_FOLDER", "CREATE_TEXT_FILE"}),
    "move": frozenset({"MOVE"}), "relocate": frozenset({"MOVE"}),
    "transfer": frozenset({"MOVE"}),
    "delete": frozenset({"DELETE"}), "remove": frozenset({"DELETE"}),
    "erase": frozenset({"DELETE"}), "trash": frozenset({"DELETE"}),
    "copy": frozenset({"COPY_TO_CLIPBOARD", "COPY_PATH_TO_CLIPBOARD"}),
    "rename": frozenset({"RENAME"}),
    "add": frozenset({"EDIT_TEXT_FILE"}), "append": frozenset({"EDIT_TEXT_FILE"}),
    "write": frozenset({"EDIT_TEXT_FILE"}), "insert": frozenset({"EDIT_TEXT_FILE"}),
    "edit": frozenset({"EDIT_TEXT_FILE"}), "replace": frozenset({"EDIT_TEXT_FILE"}),
}

_VERBS = "|".join(VERB_TO_INTENTS)

# negation word + up to 2 filler words + action verb
_NEGATED = re.compile(
    r"\b(?:don'?t|do\s+not|dont|never|not|without|no\s+need\s+to|"
    r"shouldn'?t|should\s+not|won'?t)\s+(?:\w+\s+){0,2}?"
    rf"({_VERBS})\b",
    re.IGNORECASE,
)


def find_negated_actions(text: str) -> set[str]:
    """Lowercase verbs the user negated, e.g. {'delete'}."""
    # text inside quotes is DATA, never a command: "add 'do not delete it'" is not a negation
    return {m.group(1).lower() for m in _NEGATED.finditer(blank_quoted(text))}
def negated_intents(text: str) -> set[str]:
    """Intents those negated verbs could stand for, e.g. {'DELETE'}."""
    out: set[str] = set()
    for verb in find_negated_actions(text):
        out |= VERB_TO_INTENTS[verb]
    return out