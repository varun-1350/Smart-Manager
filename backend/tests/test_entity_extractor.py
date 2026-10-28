from backend.nlp.entity_extractor import extract_entities, mask_entities


def test_filename_casing_preserved():
    e = extract_entities("Open Report_FINAL.pdf")
    assert e.filenames == ["Report_FINAL.pdf"]


def test_trailing_period_not_part_of_filename():
    assert extract_entities("open report.pdf.").filenames == ["report.pdf"]


def test_windows_paths_and_destination():
    e = extract_entities(r"move D:\Work\Plan.docx to D:\Archive")
    assert e.paths == [r"D:\Work\Plan.docx"]
    assert e.filenames == []
    assert e.destination == r"D:\Archive"


def test_quoted_filename_with_spaces():
    e = extract_entities('Copy "My Report.pdf" to Backup')
    assert e.filenames == ["My Report.pdf"]
    assert e.destination == "Backup"


def test_quoted_destination_is_not_a_source():
    e = extract_entities('copy to "My Backup"')
    assert e.destination == "My Backup"
    assert not e.has_target()


def test_date_sort_and_type():
    e = extract_entities("Find PDFs modified in October 2026")
    assert e.dates == ["October 2026"]
    assert e.file_types == ["pdf"]


def test_sort_type_reference_destination():
    e = extract_entities("open the largest PDF")
    assert e.sort_by == "largest" and e.file_types == ["pdf"]
    e = extract_entities("move the rest to Archive")
    assert "the rest" in e.references and e.destination == "Archive"


def test_folder_named_pictures_is_not_image_type():
    e = extract_entities("list files in Pictures")
    assert e.file_types == []


def test_folder_name():
    assert extract_entities("create a folder named Projects").names == ["Projects"]
    assert extract_entities("create folder Backup").names == ["Backup"]


def test_mask_removes_specific_names():
    masked = mask_entities(r"delete report.pdf and D:\x\y.txt")
    assert "report" not in masked and "filetoken" in masked

def test_clipboard_is_not_a_destination():
    e = extract_entities("copy report.pdf to the clipboard")
    assert e.destination is None and e.filenames == ["report.pdf"]


def test_rename_to():
    e = extract_entities("rename Old.txt to New.txt")
    assert e.new_name == "New.txt" and e.filenames == ["Old.txt"] and e.destination is None


def test_rename_as_quoted():
    e = extract_entities('rename "my file.txt" as "your file.txt"')
    assert e.filenames == ["my file.txt"] and e.new_name == "your file.txt"


def test_move_still_has_destination():
    assert extract_entities("move a.txt to Archive").destination == "Archive"

def test_edit_append_payload_stays_a_payload():
    e = extract_entities("in hii.txt add 'yo i am varun'")
    assert e.filenames == ["hii.txt"] and e.texts == ["yo i am varun"]
    assert e.edit_op == "append" and e.destination is None


def test_payload_words_are_not_entities():
    e = extract_entities("in notes.txt add 'move it to Archive'")
    assert e.destination is None and e.references == [] and e.file_types == []
    assert e.texts == ["move it to Archive"]


def test_append_to_file_is_target_not_destination():
    e = extract_entities('append "hello" to Notes.txt')
    assert e.filenames == ["Notes.txt"] and e.destination is None and e.texts == ["hello"]


def test_replace_has_two_texts():
    e = extract_entities("replace 'cat' with 'dog' in pets.txt")
    assert e.edit_op == "replace" and e.texts == ["cat", "dog"] and e.filenames == ["pets.txt"]


def test_move_is_not_an_edit():
    e = extract_entities("move report.pdf to Archive")
    assert e.edit_op is None and e.destination == "Archive"

def test_date_field():
    assert extract_entities("find PDFs created last week").date_field == "created"
    assert extract_entities("find PDFs modified last week").date_field == "modified"
    assert extract_entities("find PDFs from last week").date_field is None