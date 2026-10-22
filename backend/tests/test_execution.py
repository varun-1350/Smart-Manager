import os
import pytest
from pathlib import Path
from execution.filesystem import FilesystemOperations
from execution.processes import ProcessOperations
from execution.action_dispatcher import ActionDispatcher


def test_filesystem_operations(tmp_path: Path):
    # 1. Create a directory
    test_sub = tmp_path / "test_dir"
    res_mkdir = FilesystemOperations.make_dir(str(test_sub))
    assert res_mkdir["created"] is True
    assert test_sub.exists() and test_sub.is_dir()

    # 2. Write and read file
    test_file = test_sub / "hello.txt"
    test_file.write_text("Smart Manager Test Content", encoding="utf-8")
    res_read = FilesystemOperations.read_text_file(str(test_file))
    assert res_read["content"] == "Smart Manager Test Content"

    # 3. File metadata
    meta = FilesystemOperations.file_metadata(str(test_file))
    assert meta["name"] == "hello.txt"
    assert meta["extension"] == ".txt"
    assert meta["size_bytes"] > 0

    # 4. Search files
    search_res = FilesystemOperations.search_files(str(tmp_path), pattern="hello.txt")
    assert search_res["total_found"] == 1
    assert search_res["results"][0]["name"] == "hello.txt"

    # 5. Copy file
    copy_dst = tmp_path / "hello_copy.txt"
    res_copy = FilesystemOperations.copy_file(str(test_file), str(copy_dst))
    assert res_copy["copied"] is True
    assert copy_dst.exists()

    # 6. Move file
    move_dst = tmp_path / "hello_moved.txt"
    res_move = FilesystemOperations.move_file(str(copy_dst), str(move_dst))
    assert res_move["moved"] is True
    assert move_dst.exists()
    assert not copy_dst.exists()

    # 7. Rename file
    res_rename = FilesystemOperations.rename_file(str(move_dst), "hello_renamed.txt")
    assert res_rename["renamed"] is True
    assert (tmp_path / "hello_renamed.txt").exists()

    # 8. Delete file
    res_del = FilesystemOperations.delete_file(str(tmp_path / "hello_renamed.txt"))
    assert res_del["deleted"] is True
    assert not (tmp_path / "hello_renamed.txt").exists()


def test_storage_info():
    res = ProcessOperations.storage_info()
    assert "drives" in res
    assert len(res["drives"]) > 0
    first_drive = res["drives"][0]
    assert "total_gb" in first_drive
    assert "free_gb" in first_drive


def test_action_dispatcher_read_only(tmp_path: Path):
    sample = tmp_path / "sample.txt"
    sample.write_text("sample content")

    obs = ActionDispatcher.execute(
        tool="fs_file_metadata",
        parameters={"path": str(sample)},
    )
    assert obs.success is True
    assert obs.verified is True
    assert obs.result["name"] == "sample.txt"


def test_action_dispatcher_requires_approval(tmp_path: Path):
    target = tmp_path / "to_delete.txt"
    target.write_text("delete me")

    # Without approval
    obs_denied = ActionDispatcher.execute(
        tool="fs_delete_file",
        parameters={"path": str(target)},
        is_pre_approved=False,
    )
    assert obs_denied.success is False
    assert "WAITING_APPROVAL" in obs_denied.error
    assert target.exists()

    # With pre-approval
    obs_approved = ActionDispatcher.execute(
        tool="fs_delete_file",
        parameters={"path": str(target)},
        is_pre_approved=True,
    )
    assert obs_approved.success is True
    assert obs_approved.verified is True
    assert not target.exists()
