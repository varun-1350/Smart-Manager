import re
ACTIONS = [
    "SEARCH", "LIST", "OPEN", "CREATE_FOLDER", "CREATE_TEXT_FILE", "MOVE",
        "DELETE", "COPY_TO_CLIPBOARD", "COPY_PATH_TO_CLIPBOARD", "RENAME",
    "EDIT_TEXT_FILE",
]
UNSUPPORTED = "UNSUPPORTED"          # catch-all label, not an action
LABELS = ACTIONS + [UNSUPPORTED]

# Intents that change the filesystem: stricter confidence, never run if negated.
MUTATING_INTENTS = frozenset(
    {"CREATE_FOLDER", "CREATE_TEXT_FILE", "MOVE", "DELETE", "RENAME", "EDIT_TEXT_FILE"}
)

# Intents that mean the same thing to the executor: confusing them is not an error.
SAME_ACTION = frozenset({frozenset({"COPY_TO_CLIPBOARD", "COPY_PATH_TO_CLIPBOARD"})})

def _words(*stems: str) -> re.Pattern:
    return re.compile(r"\b(?:" + "|".join(stems) + r")\w*", re.IGNORECASE)


# A file-changing intent is accepted only if the sentence has a word that really means it.
# Checked on text with filenames/paths/quotes already masked out.
TRIGGERS: dict[str, re.Pattern] = {
    "MOVE": _words("mov", "relocat", "transfer", "shift", "put", "plac", "drop",
                   "stash", "stick", "send"),
    "DELETE": _words("delet", "remov", "eras", "trash", "discard", "dispos", "bin\\b",
                     "recycl", r"get\s+rid", r"throw\s+(?:away|out)"),
    "RENAME": _words("renam", "retitl", r"change\s+the\s+name", r"call\s+it", r"name\s+it"),
    "EDIT_TEXT_FILE": _words("add", "append", "writ", "insert", "replac", "substitut",
                             "edit", r"type\b", "put"),
    "CREATE_FOLDER": _words("creat", "mak", r"new\b", "generat", "start", "add", "build",
                            "folder", "director"),
    "CREATE_TEXT_FILE": _words("creat", "mak", r"new\b", "generat", "start", "add", "build"),
}
TRIGGER_HINT = {"MOVE": "move", "DELETE": "delete", "RENAME": "rename",
                "EDIT_TEXT_FILE": "add or replace", "CREATE_FOLDER": "create",
                "CREATE_TEXT_FILE": "create"}


def has_trigger(intent: str, masked_text: str) -> bool:
    pattern = TRIGGERS.get(intent)
    return True if pattern is None else bool(pattern.search(masked_text))