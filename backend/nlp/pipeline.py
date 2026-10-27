from __future__ import annotations

import re

from .confidence import is_confident
from .entity_extractor import blank_quoted, extract_entities, quoted_spans
from .intent_classifier import IntentClassifier
from .intents import MUTATING_INTENTS, UNSUPPORTED
from .negation import find_negated_actions, negated_intents
from .result import ClauseResult, Entities, NLPResult, NLPStatus

_VERBS = (r"(?:find|search|locate|list|show|open|launch|create|make|move|relocate|"
          r"transfer|delete|remove|trash|erase|copy|rename|add|append|write|insert|"
          r"edit|replace)")

# "delete the last line of x.txt" edits INSIDE a file; it must never become a file delete
_PARTIAL_DELETE = re.compile(
    r"\b(?:lines?|words?|paragraphs?|sentences?|contents?)\b", re.IGNORECASE)

# Split on  ; , and / then / after that  ONLY if an action verb follows.
_SPLIT = re.compile(
    r"\s*(?:[;,]|\band\b|\bthen\b|\bafter\s+that\b)"
    r"(?:\s*(?:[;,]|\band\b|\bthen\b))*"
    rf"\s+(?={_VERBS}\b)",
    re.IGNORECASE,
)

_NEEDS_TARGET = {"OPEN", "MOVE", "DELETE", "RENAME",
                 "COPY_TO_CLIPBOARD", "COPY_PATH_TO_CLIPBOARD"}


def normalize_text(text: str) -> str:
    for old, new in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"')):
        text = text.replace(old, new)
    return text.strip()


def split_clauses(text: str) -> list[str]:
    spans = quoted_spans(text)          # never split inside 'quoted text'
    parts, last = [], 0
    for m in _SPLIT.finditer(text):
        if any(s <= m.start() < e for s, e in spans):
            continue
        parts.append(text[last:m.start()])
        last = m.end()
    parts.append(text[last:])
    return [p.strip() for p in parts if p.strip()]

def _missing(intent: str, e: Entities, has_previous: bool) -> list[str]:
    target = e.has_target(has_previous)
    missing = []
    if intent in _NEEDS_TARGET and not target:
        missing.append("which file or folder")
    if intent == "SEARCH" and not (target or e.dates):
        missing.append("what to search for")
    if intent == "MOVE" and not e.destination:
        missing.append("the destination folder")
    if intent == "RENAME" and not e.new_name:
        missing.append("the new name")
    if intent == "CREATE_FOLDER" and not (e.names or e.paths or e.texts):
        missing.append("the folder name")
    if intent == "CREATE_TEXT_FILE" and not (e.filenames or e.names or e.paths or e.texts):
        missing.append("the file name")
    if intent == "EDIT_TEXT_FILE":
        if not (e.filenames or e.paths or e.names or (has_previous and e.references)):
            missing.append("which text file")
        if e.edit_op is None:
            missing.append("what change to make (add or replace text)")
        elif e.edit_op == "append" and len(e.texts) != 1:
            missing.append("exactly one piece of text to add, in quotes")
        elif e.edit_op == "replace" and len(e.texts) != 2:
            missing.append("the old text and the new text, each in quotes")
    return missing   # LIST needs nothing

def _analyze_clause(clause: str, clf: IntentClassifier, has_previous: bool) -> ClauseResult:
    entities = extract_entities(clause)
    negated_verbs = sorted(find_negated_actions(clause))
    blocked = negated_intents(clause)
    conf = clf.predict(clause)

    def make(status: NLPStatus, reason: str = "") -> ClauseResult:
        return ClauseResult(
            text=clause, status=status, intent=conf.top_intent,
            confidence=round(conf.top_prob, 3), margin=round(conf.margin, 3),
            entities=entities, negated_actions=negated_verbs, reason=reason,
        )

    # 1. not sure -> ask
    if not is_confident(conf):
        return make(NLPStatus.NEEDS_CLARIFICATION,
                    f'I\'m not sure what you want me to do with: "{clause}". Could you rephrase?')
    # 2. confidently out of scope
    if conf.top_intent == UNSUPPORTED:
        return make(NLPStatus.UNSUPPORTED, "That request isn't supported yet.")
    # 3. negation: block the negated intent, and ANY file-changing intent
    if blocked and (conf.top_intent in blocked or conf.top_intent in MUTATING_INTENTS):
        return make(NLPStatus.NEEDS_CLARIFICATION,
                    f"You said not to {', '.join(negated_verbs)}. I won't act until you "
                    "tell me exactly what you want.")
    # 3b. partial delete is editing inside a file, never deleting it
    if conf.top_intent == "DELETE" and _PARTIAL_DELETE.search(blank_quoted(clause)):
        return make(NLPStatus.NEEDS_CLARIFICATION,
                    "That sounds like removing text inside a file. I can only add or "
                    "replace text, and I won't delete the file itself unless you ask.")
    # 4. required details missing -> ask
    missing = _missing(conf.top_intent, entities, has_previous)
    if missing:
        return make(NLPStatus.NEEDS_CLARIFICATION, "I need " + " and ".join(missing) + ".")
    return make(NLPStatus.OK)


def analyze(text: str, classifier: IntentClassifier) -> NLPResult:
    text = normalize_text(text)
    clauses = [
        _analyze_clause(c, classifier, has_previous=i > 0)
        for i, c in enumerate(split_clauses(text))
    ]
    if not clauses:
        status = NLPStatus.NEEDS_CLARIFICATION
    elif any(c.status == NLPStatus.UNSUPPORTED for c in clauses):
        status = NLPStatus.UNSUPPORTED
    elif any(c.status == NLPStatus.NEEDS_CLARIFICATION for c in clauses):
        status = NLPStatus.NEEDS_CLARIFICATION
    else:
        status = NLPStatus.OK
    return NLPResult(original=text, status=status, clauses=clauses)