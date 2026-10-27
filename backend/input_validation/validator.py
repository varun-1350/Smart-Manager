
from dataclasses import dataclass
from enum import Enum


MAX_REQUEST_LENGTH = 10_000


class ValidationStatus(str, Enum):
    VALID = "valid"
    EMPTY = "empty"
    TOO_LONG = "too_long"
    INVALID_CHARACTERS = "invalid_characters"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


@dataclass
class ValidationResult:
    status: ValidationStatus
    message: str

    @property
    def is_valid(self) -> bool:
        return self.status == ValidationStatus.VALID


def validate_input(text: str) -> ValidationResult:
    if not isinstance(text, str):
        return ValidationResult(
            ValidationStatus.INVALID_CHARACTERS,
            "Request must be text.",
        )

    if not text.strip():
        return ValidationResult(
            ValidationStatus.EMPTY,
            "Please enter a request.",
        )

    if len(text) > MAX_REQUEST_LENGTH:
        return ValidationResult(
            ValidationStatus.TOO_LONG,
            "Request exceeds the maximum length.",
        )

    if "\x00" in text:
        return ValidationResult(
            ValidationStatus.INVALID_CHARACTERS,
            "Request contains an invalid null character.",
        )

    return ValidationResult(
        ValidationStatus.VALID,
        "Input passed basic validation.",
    )
