import pytest
import tempfile
import shutil
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from app import app
from execution.filesystem import FilesystemOperations
from storage.history import OperationHistoryRepository


@pytest.fixture
def temp_workspace():
    tmp_dir = Path(tempfile.mkdtemp(prefix="sm_explorer_test_"))
    # Create sample files
    (tmp_dir / "doc1.pdf").write_bytes(b"%PDF-1.4 test content 1")
    (tmp_dir / "doc2.pdf").write_bytes(b"%PDF-1.4 test content 1")  # Exact duplicate
    (tmp_dir / "notes.txt").write_text("Hello Smart Manager explorer", encoding="utf-8")
    (tmp_dir / "data.csv").write_text("id,val\n1,100\n2,200", encoding="utf-8")
    (tmp_dir / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")
    (tmp_dir / "empty_dir").mkdir()
    (tmp_dir / "subfolder").mkdir()
    (tmp_dir / "subfolder" / "sub_doc.docx").write_bytes(b"PK fake docx")

    yield tmp_dir

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_browse_directory(temp_workspace):
    res = FilesystemOperations.browse_directory(str(temp_workspace), sort_by="name", sort_order="asc")
    assert res["current_path"] == str(temp_workspace.resolve())
    assert len(res["breadcrumbs"]) >= 1
    assert res["total_count"] >= 6
    names = [e["name"] for e in res["entries"]]
    assert "notes.txt" in names
    assert "doc1.pdf" in names
    assert "empty_dir" in names

    # Folders should be first
    assert res["entries"][0]["is_dir"] is True

    # Date Modified assertions for folders and files
    folder_entry = next(e for e in res["entries"] if e["name"] == "empty_dir")
    assert folder_entry["is_dir"] is True
    assert folder_entry.get("modified") is not None
    assert folder_entry.get("modified_formatted") is not None
    assert isinstance(folder_entry.get("modified_timestamp"), (int, float))

    file_entry = next(e for e in res["entries"] if e["name"] == "notes.txt")
    assert file_entry["is_dir"] is False
    assert file_entry.get("modified") is not None
    assert file_entry.get("modified_formatted") is not None
    assert isinstance(file_entry.get("modified_timestamp"), (int, float))

    # Categories test
    cat_map = {e["name"]: e["category"] for e in res["entries"]}
    assert cat_map["doc1.pdf"] == "documents"
    assert cat_map["notes.txt"] == "text"
    assert cat_map["data.csv"] == "spreadsheets"
    assert cat_map["photo.png"] == "images"


def test_quick_locations():
    locs = FilesystemOperations.get_quick_locations()
    assert isinstance(locs, list)
    labels = [l["label"] for l in locs]
    # Desktop and Downloads should be discovered
    assert any("Desktop" in lbl for lbl in labels)
    assert any("Downloads" in lbl for lbl in labels)


def test_file_preview(temp_workspace):
    preview = FilesystemOperations.file_preview(str(temp_workspace / "notes.txt"))
    assert preview["preview_type"] == "text"
    assert "Hello Smart Manager explorer" in preview["content"]
    assert preview["category"] == "text"


def test_safe_move_and_undo(temp_workspace):
    batch_id = "test-move-batch"
    src_file = temp_workspace / "notes.txt"
    dest_dir = temp_workspace / "subfolder"

    assert src_file.exists()
    move_res = FilesystemOperations.safe_move([str(src_file)], str(dest_dir), batch_id=batch_id)
    assert move_res["success"] is True
    assert not src_file.exists()
    assert (dest_dir / "notes.txt").exists()

    # Revert via undo
    undo_res = FilesystemOperations.undo_last_operation()
    assert undo_res["success"] is True
    assert src_file.exists()
    assert not (dest_dir / "notes.txt").exists()


def test_safe_trash_and_undo(temp_workspace):
    batch_id = "test-trash-batch"
    target_file = temp_workspace / "data.csv"
    assert target_file.exists()

    trash_res = FilesystemOperations.safe_trash([str(target_file)], batch_id=batch_id)
    assert trash_res["success"] is True
    assert not target_file.exists()

    # Restore via undo
    undo_res = FilesystemOperations.undo_last_operation()
    assert undo_res["success"] is True
    assert target_file.exists()


def test_find_duplicates(temp_workspace):
    dup_res = FilesystemOperations.find_duplicates(str(temp_workspace), min_size_bytes=5)
    assert dup_res["duplicate_groups_count"] >= 1
    first_group = dup_res["duplicates"][0]
    names = [f["name"] for f in first_group["files"]]
    assert "doc1.pdf" in names
    assert "doc2.pdf" in names
    assert first_group["wasted_bytes"] > 0


def test_analyze_storage(temp_workspace):
    analysis = FilesystemOperations.analyze_storage(str(temp_workspace))
    assert "empty_folders" in analysis
    empty_names = [d["name"] for d in analysis["empty_folders"]]
    assert "empty_dir" in empty_names


@pytest.mark.asyncio
async def test_explorer_endpoints(temp_workspace):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # 1. Browse
        browse_res = await c.get(f"/api/explorer/browse?path={temp_workspace}")
        assert browse_res.status_code == 200
        data = browse_res.json()
        assert data["total_count"] >= 5

        # 2. Locations
        loc_res = await c.get("/api/explorer/locations")
        assert loc_res.status_code == 200
        assert len(loc_res.json()) >= 2

        # 3. Preview
        preview_res = await c.get(f"/api/explorer/preview?path={temp_workspace / 'notes.txt'}")
        assert preview_res.status_code == 200
        assert preview_res.json()["category"] == "text"

        # 4. Plan organization - valid folder
        plan_res = await c.post("/api/explorer/plan", json={
            "folder_path": str(temp_workspace),
            "instruction": "Organize files by file type",
        })
        assert plan_res.status_code == 200
        plan_data = plan_res.json()
        assert "actions" in plan_data
        assert len(plan_data["actions"]) >= 1

        # 4b. Plan organization - nonexistent directory (404)
        bad_plan_res = await c.post("/api/explorer/plan", json={
            "folder_path": str(temp_workspace / "does_not_exist_404"),
            "instruction": "Organize files",
        })
        assert bad_plan_res.status_code == 404

        # 4c. Plan organization - file instead of directory (400)
        file_plan_res = await c.post("/api/explorer/plan", json={
            "folder_path": str(temp_workspace / "notes.txt"),
            "instruction": "Organize files",
        })
        assert file_plan_res.status_code == 400

        # 5. Duplicates
        dup_res = await c.get(f"/api/explorer/duplicates?folder={temp_workspace}&min_size=5")
        assert dup_res.status_code == 200
        assert dup_res.json()["duplicate_groups_count"] >= 1


@pytest.mark.asyncio
async def test_plan_uses_active_provider(temp_workspace):
    from unittest.mock import AsyncMock, patch, MagicMock
    from agent.model import FilePlanPreview, FileActionItem

    mock_provider = MagicMock()
    mock_provider.model_name = "test-model"
    mock_plan = FilePlanPreview(
        summary="Mocked AI plan for tests",
        target_folder=str(temp_workspace),
        actions=[
            FileActionItem(
                id="act-1",
                tool="fs_move_file",
                source=str(temp_workspace / "notes.txt"),
                destination=str(temp_workspace / "Text" / "notes.txt"),
                reason="Organize notes",
                risk_level="low",
                requires_approval=True,
            )
        ],
        skipped_files=[],
        conflicts=[],
    )
    mock_provider.generate_structured = AsyncMock(return_value=mock_plan)

    with patch("app.provider_manager.get_active_provider", new_callable=AsyncMock) as mock_get_active:
        mock_get_active.return_value = (mock_provider, "Online: test-model")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            res = await c.post("/api/explorer/plan", json={
                "folder_path": str(temp_workspace),
                "instruction": "Custom organization logic for notes",
            })
            assert res.status_code == 200
            data = res.json()
            assert data["summary"] == "Mocked AI plan for tests"
            assert len(data["actions"]) == 1
            assert mock_get_active.call_count >= 1
