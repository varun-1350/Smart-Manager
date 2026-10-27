import pytest

from backend.nlp.entity_extractor import extract_entities
from backend.nlp.result import ClauseResult, NLPResult, NLPStatus
from backend.planner.builder import build_plan
from backend.planner.errors import PlanningError
from backend.schemas.task import RiskLevel


def clause(intent: str, text: str) -> ClauseResult:
    return ClauseResult(text=text, status=NLPStatus.OK, intent=intent, confidence=1.0,
                        margin=1.0, entities=extract_entities(text))


def plan_for(*clauses: ClauseResult):
    nlp = NLPResult(original=" ".join(c.text for c in clauses),
                    status=NLPStatus.OK, clauses=list(clauses))
    return build_plan(nlp)


def test_open_file():
    t = plan_for(clause("OPEN", "open report.pdf")).tasks[0]
    assert t.action == "open_file" and t.risk_level == RiskLevel.MEDIUM
    assert t.parameters == {"target": {"filename": "report.pdf"}}
    assert t.approval_required is False


def test_delete_goes_to_recycle_bin_and_needs_approval():
    t = plan_for(clause("DELETE", "delete report.pdf")).tasks[0]
    assert t.action == "move_to_recycle_bin"
    assert t.risk_level == RiskLevel.DESTRUCTIVE and t.approval_required is True
    assert t.parameters == {"targets": [{"filename": "report.pdf"}]}


def test_delete_keeps_every_named_file():
    t = plan_for(clause("DELETE", "delete a.txt and b.txt")).tasks[0]
    assert t.parameters["targets"] == [{"filename": "a.txt"}, {"filename": "b.txt"}]


def test_move():
    t = plan_for(clause("MOVE", "move report.pdf to Archive")).tasks[0]
    assert t.parameters == {"targets": [{"filename": "report.pdf"}], "destination": "Archive"}
    assert t.risk_level == RiskLevel.HIGH and t.approval_required is True


def test_rename():
    t = plan_for(clause("RENAME", "rename Old.txt to New.txt")).tasks[0]
    assert t.parameters == {"target": {"filename": "Old.txt"}, "new_name": "New.txt"}


def test_rename_cannot_smuggle_a_move():
    with pytest.raises(PlanningError):
        plan_for(clause("RENAME", r"rename a.txt to D:\x\b.txt"))


@pytest.mark.parametrize("intent, text", [
    ("COPY_TO_CLIPBOARD", "copy report.pdf to the clipboard"),
    ("COPY_PATH_TO_CLIPBOARD", "copy the path of report.pdf"),
])
def test_both_clipboard_intents_are_one_action(intent, text):
    t = plan_for(clause(intent, text)).tasks[0]
    assert t.action == "copy_path_to_clipboard"
    assert t.parameters == {"target": {"filename": "report.pdf"}}


def test_create_text_file_adds_txt_only_when_missing():
    assert plan_for(clause("CREATE_TEXT_FILE", "create a text file named notes")
                    ).tasks[0].parameters == {"name": "notes.txt"}
    assert plan_for(clause("CREATE_TEXT_FILE", "create notes.txt")
                    ).tasks[0].parameters == {"name": "notes.txt"}


def test_edit_append_and_replace():
    a = plan_for(clause("EDIT_TEXT_FILE", "in hii.txt add 'yo i am varun'")).tasks[0]
    assert a.parameters == {"target": {"filename": "hii.txt"},
                            "operation": "append", "text": "yo i am varun"}
    r = plan_for(clause("EDIT_TEXT_FILE", "replace 'cat' with 'dog' in pets.txt")).tasks[0]
    assert r.parameters["operation"] == "replace"
    assert (r.parameters["old_text"], r.parameters["new_text"]) == ("cat", "dog")


def test_tasks_are_chained_so_a_failure_stops_the_rest():
    plan = plan_for(clause("CREATE_FOLDER", "create a folder named Archive"),
                    clause("MOVE", "move report.pdf to Archive"))
    assert [t.task_id for t in plan.tasks] == ["t1", "t2"]
    assert plan.tasks[0].dependencies == [] and plan.tasks[1].dependencies == ["t1"]


def test_search_by_type():
    t = plan_for(clause("SEARCH", "find PDFs")).tasks[0]
    assert t.parameters == {"filenames": [], "names": [], "file_types": ["pdf"]}


# ---- must refuse (fail closed) ----
@pytest.mark.parametrize("intent, text", [
    ("OPEN", "open the largest PDF"),                 # reference: piece 2
    ("SEARCH", "find PDFs modified last week"),       # dates: piece 3
    ("DELETE", "delete all PDFs"),                    # type with no folder scope
    ("DELETE", r"delete all PDFs in D:\Work"),        # must NOT delete D:\Work itself
    ("OPEN", "open a.txt and b.txt"),                 # single-target action
    ("MOVE", "move report.pdf"),                      # no destination
    ("UNSUPPORTED", "write me a poem"),
])
def test_refuses_what_it_cannot_plan_safely(intent, text):
    with pytest.raises(PlanningError):
        plan_for(clause(intent, text))


def test_refuses_non_ok_nlp_result():
    nlp = NLPResult(original="x", status=NLPStatus.NEEDS_CLARIFICATION, clauses=[])
    with pytest.raises(PlanningError):
        build_plan(nlp)

def test_find_open_largest_move_rest():
    plan = plan_for(clause("SEARCH", "Find PDFs"),
                    clause("OPEN", "open the largest"),
                    clause("MOVE", "move the rest to Archive"))
    t1, t2, t3 = plan.tasks
    assert t2.parameters == {"target": {"from_task": "t1", "select": "largest"}}
    assert t3.parameters == {
        "targets": [{"from_task": "t1", "select": "remaining", "except_tasks": ["t2"]}],
        "destination": "Archive",
    }
    assert sorted(t2.dependencies) == ["t1"]
    assert sorted(t3.dependencies) == ["t1", "t2"]
    assert t2.approval_required and t3.approval_required
    assert t3.risk_level == RiskLevel.HIGH


def test_largest_pdf_after_a_pdf_search():
    plan = plan_for(clause("SEARCH", "find PDFs"), clause("OPEN", "open the largest PDF"))
    assert plan.tasks[1].parameters == {"target": {"from_task": "t1", "select": "largest"}}


def test_delete_the_rest_stays_destructive():
    plan = plan_for(clause("SEARCH", "find PDFs"),
                    clause("OPEN", "open the largest"),
                    clause("DELETE", "delete the rest"))
    t3 = plan.tasks[2]
    assert t3.action == "move_to_recycle_bin" and t3.risk_level == RiskLevel.DESTRUCTIVE
    assert t3.parameters["targets"][0]["except_tasks"] == ["t2"]


def test_them_means_all_results():
    plan = plan_for(clause("SEARCH", "find PDFs"), clause("MOVE", "move them to Archive"))
    t2 = plan.tasks[1]
    assert t2.parameters["targets"] == [{"from_task": "t1", "select": "all"}]
    assert t2.risk_level == RiskLevel.HIGH and t2.approval_required


def test_it_refers_to_the_file_just_created():
    plan = plan_for(clause("CREATE_TEXT_FILE", "create a text file named todo.txt"),
                    clause("EDIT_TEXT_FILE", "add 'buy milk' to it"))
    assert plan.tasks[1].parameters == {
        "target": {"from_task": "t1", "select": "created"},
        "operation": "append", "text": "buy milk",
    }


def test_it_after_a_search_demands_exactly_one_result():
    plan = plan_for(clause("SEARCH", "find report.pdf"), clause("OPEN", "open it"))
    assert plan.tasks[1].parameters == {"target": {"from_task": "t1", "select": "only"}}


@pytest.mark.parametrize("steps", [
    [("SEARCH", "find PDFs"), ("MOVE", "move the rest to Archive")],        # nothing picked yet
    [("SEARCH", "find PDFs"), ("OPEN", "open them")],                       # many files, one-file action
    [("SEARCH", "find PDFs"), ("OPEN", "open the largest image")],          # type not searched
    [("SEARCH", "find PDFs"), ("OPEN", "open the largest report.pdf")],     # named AND referred
    [("SEARCH", "find PDFs"), ("MOVE", "move a.txt to Archive"),
     ("OPEN", "open it")],                                                  # 'it' after unrelated step
    [("CREATE_FOLDER", "create a folder named Notes"),
     ("EDIT_TEXT_FILE", "add 'x' to it")],                                  # a folder is not a text file
    [("DELETE", "delete the rest")],                                        # nothing earlier at all
    [("SEARCH", "find PDFs"),
     ("MOVE", "move the rest of the largest to Archive")],                  # ambiguous
])
def test_refuses_unsafe_references(steps):
    with pytest.raises(PlanningError):
        plan_for(*[clause(intent, text) for intent, text in steps])