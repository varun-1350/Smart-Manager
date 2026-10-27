
from backend.input_validation import (
    ValidationStatus,
    validate_input,
)


def test_valid_request():
    result = validate_input("Find PNG files in Downloads")
    assert result.status == ValidationStatus.VALID


def test_empty_request():
    result = validate_input("   ")
    assert result.status == ValidationStatus.EMPTY


def test_request_too_long():
    result = validate_input("a" * 10_001)
    assert result.status == ValidationStatus.TOO_LONG


def test_null_character():
    result = validate_input("Find\x00files")
    assert result.status == ValidationStatus.INVALID_CHARACTERS


def test_non_text_input():
    result = validate_input(None)
    assert result.status == ValidationStatus.INVALID_CHARACTERS


def test_valid_property():
    assert validate_input("Open Notepad").is_valid
    assert not validate_input("").is_valid
