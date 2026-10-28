import os
import shutil
from pathlib import Path

import pytest

from backend.tools.filesystem import files, system, textedit
from backend.tools.filesystem.common import ToolError, sha256_file


@pytest.fixture
def d(tmp_path):
    return tmp_path.resolve()


def write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def test_relative_paths_are_refused():
    with pytest.raises(ToolError):
        files.create_folder(Path("relative"))


def test_sha256_file(d):
    f = write(d / "a", b"abc")
    assert sha256_file(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


# ------------------------------------------------------------------- create
def test_create_folder(d):
    r = files.create_folder(d / "New")
    assert (d / "New").is_dir() and r.verified and r.undo["op"] == "remove_empty_folder"


def test_create_folder_refuses_existing_or_missing_parent(d):
    (d / "x").mkdir()
    with pytest.raises(ToolError):
        files.create_folder(d / "x")
    with pytest.raises(ToolError):
        files.create_folder(d / "nope" / "y")
    assert not (d / "nope").exists()          # no silent makedirs


def test_create_text_file_never_overwrites(d):
    r = files.create_text_file(d / "t.txt")
    assert (d / "t.txt").read_bytes() == b"" and r.undo["op"] == "remove_empty_file"
    (d / "t.txt").write_bytes(b"keep me")
    with pytest.raises(ToolError):
        files.create_text_file(d / "t.txt")
    assert (d / "t.txt").read_bytes() == b"keep me"


# -------------------------------------------------------------- move/rename
def test_move_file_and_undo_info(d):
    src = write(d / "a.txt", b"hello")
    (d / "sub").mkdir()
    r = files.move_path(src, d / "sub" / "a.txt")
    assert not src.exists() and (d / "sub" / "a.txt").read_bytes() == b"hello"
    assert r.undo == {"op": "move_back", "from": str(d / "sub" / "a.txt"), "to": str(src)}


def test_move_folder(d):
    (d / "src").mkdir()
    write(d / "src" / "f.txt", b"1")
    (d / "dest").mkdir()
    files.move_path(d / "src", d / "dest" / "src")
    assert (d / "dest" / "src" / "f.txt").exists() and not (d / "src").exists()


def test_move_refuses_overwrite_missing_and_into_itself(d):
    a, b = write(d / "a.txt", b"A"), write(d / "b.txt", b"B")
    with pytest.raises(ToolError, match="overwrite"):
        files.move_path(a, b)
    assert a.read_bytes() == b"A" and b.read_bytes() == b"B"
    with pytest.raises(ToolError):
        files.move_path(d / "ghost.txt", d / "x.txt")
    with pytest.raises(ToolError):
        files.move_path(a, d / "nofolder" / "a.txt")
    with pytest.raises(ToolError):
        files.move_path(a, a)
    (d / "dir").mkdir()
    with pytest.raises(ToolError, match="itself"):
        files.move_path(d / "dir", d / "dir" / "inner")


def test_case_only_rename(d):
    src = write(d / "a.txt", b"1")
    files.move_path(src, d / "A.txt", action="rename_file")
    names = os.listdir(d)
    assert "A.txt" in names and "a.txt" not in names


def _fail_on(src):
    real = os.rename

    def fake(a, b):
        if str(a) == str(src):
            raise OSError("cross-device")
        return real(a, b)
    return fake


def test_move_across_volumes_copies_verifies_then_deletes(d, monkeypatch):
    src = write(d / "a.bin", b"hello" * 1000)
    (d / "sub").mkdir()
    dst = d / "sub" / "a.bin"
    monkeypatch.setattr(files, "_different_volume", lambda a, b: True)
    files.move_path(src, dst, rename=_fail_on(src))
    assert dst.read_bytes() == b"hello" * 1000 and not src.exists()
    assert [p.name for p in dst.parent.iterdir()] == ["a.bin"]      # no .part left behind


def test_cross_volume_copy_mismatch_removes_nothing(d, monkeypatch):
    src = write(d / "a.bin", b"data")
    (d / "sub").mkdir()
    answers = iter(["x", "y"])                                       # copy hash != original hash
    monkeypatch.setattr(files, "_different_volume", lambda a, b: True)
    monkeypatch.setattr(files, "sha256_file", lambda p: next(answers))
    with pytest.raises(ToolError, match="didn't match"):
        files.move_path(src, d / "sub" / "a.bin", rename=_fail_on(src))
    assert src.read_bytes() == b"data" and list((d / "sub").iterdir()) == []


def test_cross_volume_folder_is_refused(d, monkeypatch):
    (d / "src").mkdir()
    (d / "dest").mkdir()
    monkeypatch.setattr(files, "_different_volume", lambda a, b: True)
    with pytest.raises(ToolError, match="another drive"):
        files.move_path(d / "src", d / "dest" / "src", rename=_fail_on(d / "src"))
    assert (d / "src").is_dir()


def test_same_volume_failure_is_reported_and_leaves_the_file(d):
    src = write(d / "a.txt", b"1")
    with pytest.raises(ToolError, match="Couldn't move"):
        files.move_path(src, d / "b.txt", rename=_fail_on(src))
    assert src.exists() and not (d / "b.txt").exists()


# ------------------------------------------------------------------- edits
def edit(d, raw: bytes, op: str, **kw):
    f = write(d / "t.txt", raw)
    r = textedit.edit_text(f, op, **kw)
    return f.read_bytes(), r


def test_append_variants(d):
    assert edit(d, b"a\nb\n", "append", text="c")[0] == b"a\nb\nc\n"
    assert edit(d, b"hello", "append", text="yo")[0] == b"hello\nyo\n"      # adds the missing newline
    assert edit(d, b"", "append", text="yo")[0] == b"yo\n"
    assert edit(d, b"a\n", "append", text="x\n")[0] == b"a\nx\n"             # no double newline


def test_append_keeps_crlf_and_bom(d):
    assert edit(d, b"a\r\nb\r\n", "append", text="x\ny")[0] == b"a\r\nb\r\nx\r\ny\r\n"
    assert edit(d, b"\xef\xbb\xbfhi\n", "append", text="x")[0] == b"\xef\xbb\xbfhi\nx\n"


def test_append_unicode(d):
    assert edit(d, b"a\n", "append", text="caf\u00e9")[0] == "a\ncaf\u00e9\n".encode("utf-8")


def test_replace_all_occurrences(d):
    data, r = edit(d, b"cat and cat\n", "replace", old_text="cat", new_text="dog")
    assert data == b"dog and dog\n" and r.output["replacements"] == 2


def test_replace_is_exact(d):
    f = write(d / "t.txt", b"Cat\n")
    with pytest.raises(ToolError, match="couldn't find"):
        textedit.edit_text(f, "replace", old_text="cat", new_text="dog")
    assert f.read_bytes() == b"Cat\n"


@pytest.mark.parametrize("raw, op, kw", [
    (b"a\n", "append", {"text": ""}),
    (b"a\n", "replace", {"old_text": "", "new_text": "x"}),
    (b"a\n", "replace", {"old_text": "a", "new_text": "a"}),     # changes nothing
    (b"a\n", "delete", {"text": "x"}),
    (b"\xff\xfe bad", "append", {"text": "x"}),                   # not UTF-8
    (b"bin\x00ary", "append", {"text": "x"}),
    (b"a\r\nb\n", "append", {"text": "x"}),                       # mixed line endings
    (b"a\rb", "append", {"text": "x"}),                           # old-style line endings
])
def test_edits_it_must_refuse_leave_the_file_untouched(d, raw, op, kw):
    f = write(d / "t.txt", raw)
    with pytest.raises(ToolError):
        textedit.edit_text(f, op, **kw)
    assert f.read_bytes() == raw


def test_edit_size_limits(d, monkeypatch):
    monkeypatch.setattr(textedit, "MAX_EDIT_BYTES", 5)
    big = write(d / "big.txt", b"123456")
    with pytest.raises(ToolError, match="too large"):
        textedit.edit_text(big, "append", text="x")
    small = write(d / "small.txt", b"1234")
    with pytest.raises(ToolError, match="too large"):                # the RESULT would exceed it
        textedit.edit_text(small, "append", text="xyz")
    assert small.read_bytes() == b"1234"


def test_edit_refuses_folders_and_missing_files(d):
    (d / "dir").mkdir()
    for p in (d / "dir", d / "ghost.txt"):
        with pytest.raises(ToolError):
            textedit.edit_text(p, "append", text="x")


def test_edit_leaves_no_temp_files(d):
    edit(d, b"a\n", "append", text="b")
    assert [p.name for p in d.iterdir()] == ["t.txt"]


def test_edit_backup_and_undo_info(d):
    f = write(d / "t.txt", b"one\n")
    r = textedit.edit_text(f, "append", text="two", backup_dir=d / "bak")
    assert Path(r.undo["backup"]).read_bytes() == b"one\n"
    assert r.undo["expected_sha256"] == sha256_file(f) == r.output["after_sha256"]


# ------------------------------------------------------------- recycle bin
def fake_trash(bin_dir: Path):
    bin_dir.mkdir(exist_ok=True)
    return lambda p: shutil.move(p, str(bin_dir / Path(p).name))


def test_recycle_file_and_folder(d):
    trash = fake_trash(d / "bin")
    f = write(d / "a.txt", b"1")
    (d / "dir").mkdir()
    r = files.move_to_recycle_bin(f, trash=trash)
    files.move_to_recycle_bin(d / "dir", trash=trash)
    assert not f.exists() and not (d / "dir").exists()
    assert r.undo["op"] == "restore_from_recycle_bin"


def test_recycle_failures(d):
    f = write(d / "a.txt", b"1")
    with pytest.raises(ToolError, match="still there"):
        files.move_to_recycle_bin(f, trash=lambda p: None)           # call "succeeded" but nothing moved
    def boom(p):
        raise RuntimeError("no bin")
    with pytest.raises(ToolError, match="Couldn't move"):
        files.move_to_recycle_bin(f, trash=boom)
    with pytest.raises(ToolError):
        files.move_to_recycle_bin(d / "ghost.txt", trash=lambda p: None)
    assert f.exists()


# -------------------------------------------------------------- open/clipboard
def test_open_calls_the_opener_once(d):
    f, seen = write(d / "a.pdf", b"x"), []
    r = system.open_path(f, opener=seen.append)
    assert seen == [str(f)] and r.verified is False


def test_open_refuses_programs_and_missing(d):
    seen = []
    exe = write(d / "setup.exe", b"x")
    with pytest.raises(ToolError, match="program or script"):
        system.open_path(exe, opener=seen.append)
    with pytest.raises(ToolError):
        system.open_path(d / "ghost.pdf", opener=seen.append)
    assert seen == []


def test_open_folder_is_allowed(d):
    seen = []
    system.open_path(d, opener=seen.append)
    assert seen == [str(d)]


class FakeClipboard:
    def __init__(self, broken=False):
        self.text, self.broken = None, broken

    def set(self, text):
        self.text = None if self.broken else text

    def get(self):
        return self.text


def test_clipboard_receives_the_path(d):
    f, clip = write(d / "a.txt", b"x"), FakeClipboard()
    system.copy_path_to_clipboard(f, clipboard=clip)
    assert clip.text == str(f)


def test_clipboard_failures(d):
    f = write(d / "a.txt", b"x")
    with pytest.raises(ToolError, match="didn't hold"):
        system.copy_path_to_clipboard(f, clipboard=FakeClipboard(broken=True))
    with pytest.raises(ToolError):
        system.copy_path_to_clipboard(d / "ghost.txt", clipboard=FakeClipboard())