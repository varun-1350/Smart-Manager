from backend.schemas.task import RiskLevel

# NLP intent -> (planner action, base risk)
ACTIONS: dict[str, tuple[str, RiskLevel]] = {
    "SEARCH": ("search_files", RiskLevel.LOW),
    "LIST": ("list_files", RiskLevel.LOW),
    "OPEN": ("open_file", RiskLevel.MEDIUM),
    "CREATE_FOLDER": ("create_folder", RiskLevel.MEDIUM),
    "CREATE_TEXT_FILE": ("create_text_file", RiskLevel.MEDIUM),
    "COPY_TO_CLIPBOARD": ("copy_path_to_clipboard", RiskLevel.LOW),
    "COPY_PATH_TO_CLIPBOARD": ("copy_path_to_clipboard", RiskLevel.LOW),
    "MOVE": ("move_file", RiskLevel.HIGH),
    "RENAME": ("rename_file", RiskLevel.HIGH),
    "EDIT_TEXT_FILE": ("edit_text_file", RiskLevel.HIGH),
    "DELETE": ("move_to_recycle_bin", RiskLevel.DESTRUCTIVE),  # Recycle Bin, never permanent
}

SUPPORTED_ACTIONS = frozenset(action for action, _ in ACTIONS.values())
APPROVAL_RISKS = frozenset({RiskLevel.HIGH, RiskLevel.DESTRUCTIVE})