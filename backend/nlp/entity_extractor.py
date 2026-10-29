from __future__ import annotations

import re

from .result import Entities

_EXT = (r"(?:pdf|docx?|xlsx?|pptx?|txt|csv|rtf|odt|png|jpe?g|gif|bmp|webp|svg|"
        r"mp3|wav|mp4|mkv|avi|mov|zip|rar|7z|py|json|md|exe|log)")

# "quoted text" or 'quoted text' (the lookarounds keep don't / it's out)
_QUOTED = re.compile(r'"([^"]+)"|(?<!\w)\'([^\']+)\'(?!\w)')
# C:\folder\file (no spaces unless the path was quoted)
_PATH = re.compile(r'[A-Za-z]:\\[^\s"<>|?*]*')
_PATH_START = re.compile(r"^[A-Za-z]:\\")
# bare filename with a known extension: report.pdf, my.report.v2.docx
_FILENAME = re.compile(
    rf"(?<![\w\\/.])[\w\-()]+(?:\.[\w\-()]+)*\.{_EXT}(?!\w)", re.IGNORECASE
)
_FILENAME_FULL = re.compile(rf'[^\\/:*?"<>|]+\.{_EXT}', re.IGNORECASE)

# "to Archive", "into the Documents folder", 'to "My Backup"', "to D:\Backup"
_DEST = re.compile(
    r"\b(?:to|into)\s+(?:the\s+|my\s+)?(?:folder\s+)?"
    r'(?:"([^"]+)"|\'([^\']+)\'|([A-Za-z]:\\[^\s"<>|?*]*)|([\w\-.]+))',
    re.IGNORECASE,
)
_DEST_STOP = {
    "it", "them", "there", "here", "a", "an", "the", "me", "my", "this", "that",
    "these", "those", "recycle", "trash", "bin","clipboard",
    "delete", "remove", "copy", "move", "open", "find", "search", "list",
    "show", "create", "make", "get", "trash", "erase", "see", "check", "know", "be",
}

# "named X" / "called X" / "folder X"
_NAMED = re.compile(
    r'\b(?:named|called)\s+(?:"([^"]+)"|\'([^\']+)\'|([\w\-.]+))', re.IGNORECASE
)
_FOLDER = re.compile(
    r"\b(?:folder|directory)\s+"
    r"(?!(?:named|called|in|to|into|on|at|for|with|and|from)\b)"
    r'(?:"([^"]+)"|([\w\-.]+))',
    re.IGNORECASE,
)
_RENAME = re.compile(r"\b(?:renam\w*|retitl\w*|change\s+the\s+name)\b", re.IGNORECASE)
_PLACE = re.compile(r"\b(?:put|place|drop|stash|stick)\b", re.IGNORECASE)
_AS = re.compile(r'\bas\s+(?:"([^"]+)"|\'([^\']+)\'|([\w\-.]+))', re.IGNORECASE)
_EDIT_APPEND = re.compile(r"\b(?:add|append|write|insert)\b", re.IGNORECASE)
_EDIT_REPLACE = re.compile(r"\b(?:replace|substitute)\b", re.IGNORECASE)
_EDIT_ANY = re.compile(r"\b(?:add|append|write|insert|replace|substitute|edit)\b", re.IGNORECASE)
_HAS_EXT = re.compile(rf"\.{_EXT}$", re.IGNORECASE)
_MONTHS = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
           r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_UNITS = r"(?:days?|weeks?|months?|years?)"
_REL = (rf"(?:today|yesterday|(?:this|last)\s+(?:week|month|year)|"
        rf"(?:last|past)\s+\d+\s+{_UNITS}|(?:older|newer)\s+than\s+\d+\s+{_UNITS})")
_LOCATION = re.compile(
    r"\b(?:in|inside|within|under|from)\s+(?:the\s+|my\s+)?(?:folder\s+|directory\s+)?"
    r'(?:"([^"]+)"|\'([^\']+)\'|([A-Za-z]:\\[^\s"<>|?*]*)|([\w\-.]+(?:[\\/][\w\-.]+)*))',
    re.IGNORECASE,
)
# "in this folder", "in order to", "in my computer" are not places we can look
_LOC_STOP = frozenset({
    "it", "them", "this", "that", "these", "those", "there", "here", "the", "a", "an",
    "my", "and", "then", "all", "computer", "pc", "laptop", "system", "order", "case",
    "total", "folder", "directory", "current", "same", "everywhere", "anywhere",
    "recycle", "trash", "bin", "clipboard",
})
_DATE = re.compile(
    rf"\b(?:\d{{4}}-\d{{2}}-\d{{2}}"
    rf"|{_MONTHS}\s+\d{{4}}"
    rf"|{_MONTHS}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?"
    rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS}(?:\s+\d{{4}})?"
    rf"|{_REL})\b",
    re.IGNORECASE,
)

_DATE_FIELD = re.compile(r"\b(created|modified|edited|changed|updated)\b", re.IGNORECASE)

_SORT = re.compile(
    r"\b(largest|biggest|smallest|newest|latest|most\s+recent|recent|oldest)\b",
    re.IGNORECASE,
)
_SORT_MAP = {
    "largest": "largest", "biggest": "largest", "smallest": "smallest",
    "newest": "newest", "latest": "newest", "most recent": "newest",
    "recent": "newest", "oldest": "oldest",
}

_REFERENCE = re.compile(
    r"\b(the\s+rest|the\s+remaining|the\s+others|those|them|these|that\s+file|it)\b",
    re.IGNORECASE,
)

# phrases like "in Downloads" / "to the Pictures folder": blanked before file-type
# detection so a folder called Pictures isn't mistaken for "image files"
_LOCATION_PHRASE = re.compile(
    r"\b(?:in|inside|from|to|into|of|under|within)\s+(?:the\s+|my\s+)?[\w\-.]+",
    re.IGNORECASE,
)

_FILE_TYPE_WORDS = {
    "pdf": "pdf", "pdfs": "pdf",
    "image": "image", "images": "image", "photo": "image", "photos": "image",
    "picture": "image", "pictures": "image", "png": "image", "jpg": "image",
    "jpeg": "image",
    "doc": "document", "docs": "document", "docx": "document",
    "excel": "spreadsheet", "spreadsheet": "spreadsheet",
    "spreadsheets": "spreadsheet", "xlsx": "spreadsheet", "csv": "spreadsheet",
    "ppt": "presentation", "pptx": "presentation", "presentation": "presentation",
    "presentations": "presentation",
    "txt": "text",
    "video": "video", "videos": "video", "mp4": "video",
    "music": "audio", "song": "audio", "songs": "audio", "mp3": "audio",
    "audio": "audio",
    "zip": "archive",
}
_FILE_TYPE = re.compile(
    r"\b(" + "|".join(sorted(_FILE_TYPE_WORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _blank(text: str, pattern: re.Pattern) -> str:
    """Replace matches with spaces of equal length (keeps other offsets intact)."""
    return pattern.sub(lambda m: " " * len(m.group(0)), text)


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for item in items:
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _clean(value: str) -> str:
    return value.strip().strip(".,;:!?").strip()


def quoted_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _QUOTED.finditer(text)]


def blank_quoted(text: str) -> str:
    """Hide 'quoted text' so it can't be mistaken for commands or entities."""
    return _blank(text, _QUOTED)


def _inside(m: re.Match, spans: list[tuple[int, int]]) -> bool:
    return any(s <= m.start() < e for s, e in spans)

def _find_locations(text: str) -> list[str]:
    spans = quoted_spans(text)
    masked = _blank(text, _DATE)        # "in October 2026" is a date, not a place
    found: list[str] = []
    for m in _LOCATION.finditer(masked):
        if _inside(m, spans):           # words inside a quoted payload are data
            continue
        value = next(g for g in m.groups() if g is not None)
        if m.group(3) or m.group(4):    # unquoted: trim sentence punctuation
            value = value.rstrip(",;:!?)")
            if value.endswith(".") and value.strip("."):
                value = value.rstrip(".")   # "Downloads." -> "Downloads", but ".." stays
        value = value.strip()
        if not value or value.casefold() in _LOC_STOP or _HAS_EXT.search(value):
            continue                    # empty, vague, or a FILE ("in notes.txt")
        found.append(value)
    return _dedupe(found)

def _find_destination(text: str) -> str | None:
    spans = quoted_spans(text)
    found = None
    for m in _DEST.finditer(text):
        if _inside(m, spans):       # "to Archive" inside a quoted payload is not a destination
            continue
        value = next(g for g in m.groups() if g is not None)
        value = _clean(value) if m.group(4) or m.group(3) else value.strip()
        if value and value.casefold() not in _DEST_STOP:
            found = value  # keep the LAST valid match: "move a to b"
    return found

def mask_entities(text: str) -> str:
    """Replace filenames/paths/quoted text with fixed tokens for the classifier,
    so the model learns *verbs*, not specific filenames."""
    text = _QUOTED.sub(" quotedtoken ", text)
    text = _PATH.sub(" pathtoken ", text)
    return _FILENAME.sub(" filetoken ", text)


def extract_entities(text: str) -> Entities:
    ent = Entities()
    names: list[str] = []

    # 1. destination + names, from the ORIGINAL text so quoted values are visible
    ent.destination = _find_destination(text)
    ent.locations = _find_locations(text)
    spans = quoted_spans(text)
    for m in _NAMED.finditer(text):
        if not _inside(m, spans):
            names.append(_clean(next(g for g in m.groups() if g)))
    for m in _FOLDER.finditer(text):
        if not _inside(m, spans):
            names.append(_clean(next(g for g in m.groups() if g)))

    # 2. quoted values: keep EXACT text (spaces and casing)
    for m in _QUOTED.finditer(text):
        value = (m.group(1) or m.group(2)).strip()
        if _PATH_START.match(value):
            ent.paths.append(value)
        elif _FILENAME_FULL.fullmatch(value):
            ent.filenames.append(value)
        else:
            ent.texts.append(value)   # quoted text: a payload (EDIT) or a quoted name
    work = _blank(text, _QUOTED)

    # 3. unquoted paths, then bare filenames (original casing preserved)
    for m in _PATH.finditer(work):
        ent.paths.append(m.group(0).rstrip(".,;:!?)"))
    work = _blank(work, _PATH)
    for m in _FILENAME.finditer(work):
        ent.filenames.append(m.group(0))
    work = _blank(work, _FILENAME)

    # 4. dates, sort order, references
    ent.dates = [m.group(0) for m in _DATE.finditer(work)]
    field_match = _DATE_FIELD.search(work)
    if ent.dates and field_match:
        ent.date_field = "created" if field_match.group(1).lower() == "created" else "modified"
    sort = _SORT.search(work)
    if sort:
        ent.sort_by = _SORT_MAP[" ".join(sort.group(1).lower().split())]
    ent.references = [" ".join(m.group(1).lower().split())
                      for m in _REFERENCE.finditer(work)]

    # 4b. verbs that change what "to X" means (checked on `work`: quotes are blanked)
    if _RENAME.search(work):
        as_match = _AS.search(text)
        ent.new_name = ent.destination or (
            _clean(next(g for g in as_match.groups() if g)) if as_match else None
        )
        ent.destination = None   # RENAME: "to X" is a new name, not a folder
    if _EDIT_ANY.search(work):
        if _EDIT_REPLACE.search(work):
            ent.edit_op = "replace"
        elif _EDIT_APPEND.search(work):
            ent.edit_op = "append"
        if ent.destination and _HAS_EXT.search(ent.destination):
            ent.destination = None   # "append 'x' to notes.txt": that is the FILE

    # 4c. "put X in Archive": with these verbs, "in <folder>" is where the file goes
    if not ent.destination and len(ent.locations) == 1 and _PLACE.search(work):
        ent.destination, ent.locations = ent.locations[0], []

    # 5. file types, after removing "in X" / "to X" / "folder X" phrases
    typed = _blank(work, _LOCATION_PHRASE)
    typed = _blank(typed, _FOLDER)
    typed = _blank(typed, _NAMED)
    ent.file_types = [_FILE_TYPE_WORDS[m.group(1).lower()]
                      for m in _FILE_TYPE.finditer(typed)]

    # 6. destination / new name are NOT sources: remove them from the source lists
    ent.names = names
    reserved = {v.casefold() for v in (ent.destination, ent.new_name, *ent.locations) if v}
    if reserved:
        ent.paths = [p for p in ent.paths if p.casefold() not in reserved]
        ent.filenames = [f for f in ent.filenames if f.casefold() not in reserved]
        ent.names = [n for n in ent.names if n.casefold() not in reserved]
        ent.texts = [t for t in ent.texts if t.casefold() not in reserved]

    # 7. tidy up. `texts` is NOT de-duplicated: replace 'a' with 'a' needs both
    ent.filenames = _dedupe(ent.filenames)
    ent.paths = _dedupe(ent.paths)
    ent.names = _dedupe(ent.names)
    ent.file_types = _dedupe(ent.file_types)
    ent.dates = _dedupe(ent.dates)
    ent.references = _dedupe(ent.references)
    return ent
    ent = Entities()
    names: list[str] = []

    # 1. destination + names, from the ORIGINAL text so quoted values are visible
    ent.destination = _find_destination(text)
    spans = quoted_spans(text)
    for m in _NAMED.finditer(text):
        if not _inside(m, spans):
            names.append(_clean(next(g for g in m.groups() if g)))
    for m in _FOLDER.finditer(text):
        if not _inside(m, spans):
            names.append(_clean(next(g for g in m.groups() if g)))

    # 2. quoted values: keep EXACT text (spaces and casing)
    for m in _QUOTED.finditer(text):
        value = (m.group(1) or m.group(2)).strip()
        if _PATH_START.match(value):
            ent.paths.append(value)
        elif _FILENAME_FULL.fullmatch(value):
            ent.filenames.append(value)
        else:
            ent.texts.append(value)   # quoted text: a payload (EDIT) or a quoted name
    work = _blank(text, _QUOTED)

    # 3. unquoted paths, then bare filenames (original casing preserved)
    for m in _PATH.finditer(work):
        ent.paths.append(m.group(0).rstrip(".,;:!?)"))
    work = _blank(work, _PATH)
    for m in _FILENAME.finditer(work):
        ent.filenames.append(m.group(0))
    work = _blank(work, _FILENAME)

    # 4. dates, sort order, references
    ent.dates = [m.group(0) for m in _DATE.finditer(work)]
    sort = _SORT.search(work)
    if sort:
        ent.sort_by = _SORT_MAP[" ".join(sort.group(1).lower().split())]
    ent.references = [" ".join(m.group(1).lower().split())
                      for m in _REFERENCE.finditer(work)]
    # 4b. verbs that change what "to X" means. Checked on `work` (quotes blanked),
    #     so words inside a quoted payload can never trigger them.
    if _RENAME.search(work):
        as_match = _AS.search(text)
        ent.new_name = ent.destination or (
            _clean(next(g for g in as_match.groups() if g)) if as_match else None
        )
        ent.destination = None   # RENAME: "to X" is a new name, not a folder
    if _EDIT_ANY.search(work):
        if _EDIT_REPLACE.search(work):
            ent.edit_op = "replace"
        elif _EDIT_APPEND.search(work):
            ent.edit_op = "append"
        if ent.destination and _HAS_EXT.search(ent.destination):
            ent.destination = None   # "append 'x' to notes.txt": that is the FILE, not a folder
    # 5. file types, after removing "in X" / "to X" / "folder X" phrases
    typed = _blank(work, _LOCATION_PHRASE)
    typed = _blank(typed, _FOLDER)
    typed = _blank(typed, _NAMED)
    ent.file_types = [_FILE_TYPE_WORDS[m.group(1).lower()]
                      for m in _FILE_TYPE.finditer(typed)]

    # 6. destination / new name are NOT sources: remove them from the source lists
    ent.names = names
    reserved = {v.casefold() for v in (ent.destination, ent.new_name) if v}
    if reserved:
        ent.paths = [p for p in ent.paths if p.casefold() not in reserved]
        ent.filenames = [f for f in ent.filenames if f.casefold() not in reserved]
        ent.names = [n for n in ent.names if n.casefold() not in reserved]
        ent.texts = [t for t in ent.texts if t.casefold() not in reserved]