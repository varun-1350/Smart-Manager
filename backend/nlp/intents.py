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