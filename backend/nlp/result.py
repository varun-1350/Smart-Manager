from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class NLPStatus(str, Enum):
    OK = "ok"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


@dataclass
class Entities:
    filenames: list[str] = field(default_factory=list)   # report.pdf
    paths: list[str] = field(default_factory=list)       # D:\Work\plan.docx
    names: list[str] = field(default_factory=list)       # folder/item names: Projects
    file_types: list[str] = field(default_factory=list)  # pdf, image, spreadsheet...
    dates: list[str] = field(default_factory=list)       # "October 2026", "last week"
    sort_by: str | None = None                           # largest/smallest/newest/oldest
    destination: str | None = None                       # "to Archive"  (MOVE)
    new_name: str | None = None                          # "rename a to NEW" (RENAME)
    references: list[str] = field(default_factory=list)  # "the rest", "them", "it"
    texts: list[str] = field(default_factory=list)       # 'quoted text' (EDIT payload)
    edit_op: str | None = None    
    date_field: str | None = None                        # "created" | "modified"  
    locations: list[str] = field(default_factory=list)   # "in Downloads", "in D:\Work"                     # "append" | "replace"

    def has_target(self, has_previous: bool = False) -> bool:
        """True if the user pointed at something to act on.

        'the rest', 'it', 'the largest' only count when an EARLIER clause in the
        same request can supply what they refer to."""
        explicit = (self.filenames or self.paths or self.names
                    or self.file_types or self.texts)
        implicit = has_previous and (self.references or self.sort_by)
        return bool(explicit or implicit)

@dataclass
class ClauseResult:
    text: str
    status: NLPStatus
    intent: str | None          # a guess when status != OK. Never act on it.
    confidence: float
    margin: float
    entities: Entities
    negated_actions: list[str] = field(default_factory=list)
    reason: str = ""            # message to show the user when status != OK


@dataclass
class NLPResult:
    original: str
    status: NLPStatus
    clauses: list[ClauseResult]

    def to_dict(self) -> dict:
        return asdict(self)