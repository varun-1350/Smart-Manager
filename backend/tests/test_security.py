import pytest
from security.permissions import SecurityPolicy, RiskLevel


def test_path_traversal_prevention():
    res = SecurityPolicy.evaluate_action(
        tool="fs_list_dir",
        parameters={"path": "D:\\safe\\..\\..\\Windows"},
    )
    assert res.allowed is False
    assert res.risk_level == RiskLevel.CRITICAL
    assert "Path traversal" in res.reason


def test_protected_windows_directory_prevention():
    res = SecurityPolicy.evaluate_action(
        tool="fs_make_dir",
        parameters={"path": "C:\\Windows\\System32\\hacked"},
    )
    assert res.allowed is False
    assert res.risk_level == RiskLevel.CRITICAL
    assert "Modifying protected" in res.reason


def test_risk_classification():
    # Read-only
    p_read = SecurityPolicy.evaluate_action("fs_list_dir", {"path": "D:\\Documents"})
    assert p_read.allowed is True
    assert p_read.requires_approval is False
    assert p_read.risk_level == RiskLevel.READ_ONLY

    # High risk deletion
    p_del = SecurityPolicy.evaluate_action("fs_delete_file", {"path": "D:\\Documents\\old.txt"})
    assert p_del.allowed is True
    assert p_del.requires_approval is True
    assert p_del.risk_level == RiskLevel.HIGH

    # Unknown tool
    p_unknown = SecurityPolicy.evaluate_action("format_hard_drive", {})
    assert p_unknown.allowed is False
    assert p_unknown.risk_level == RiskLevel.CRITICAL
