from datetime import date

import pytest

from backend.nlp.entity_extractor import extract_entities
from backend.nlp.result import ClauseResult, NLPResult, NLPStatus
from backend.planner.builder import build_plan
from backend.planner.dates import resolve_date
from backend.planner.errors import PlanningError

TODAY = date(2026, 10, 28)   # a Wednesday


@pytest.mark.parametrize("raw, start, end", [
    ("today", "2026-10-28", "2026-10-29"),
    ("yesterday", "2026-10-27", "2026-10-28"),
    ("this week", "2026-10-26", "2026-11-02"),
    ("last week", "2026-10-19", "2026-10-26"),
    ("this month", "2026-10-01", "2026-11-01"),
    ("last month", "2026-09-01", "2026-10-01"),
    ("this year", "2026-01-01", "2027-01-01"),
    ("last year", "2025-01-01", "2026-01-01"),
    ("last 7 days", "2026-10-21", "2026-10-29"),
    ("past 2 weeks", "2026-10-14", "2026-10-29"),
    ("last 3 months", "2026-07-28", "2026-10-29"),
    ("older than 30 days", None, "2026-09-28"),
    ("newer than 2 weeks", "2026-10-14", None),
    ("October 2026", "2026-10-01", "2026-11-01"),
    ("December 2025", "2025-12-01", "2026-01-01"),
    ("2026-10-05", "2026-10-05", "2026-10-06"),
    ("5th March 2026", "2026-03-05", "2026-03-06"),
    ("March 5, 2026", "2026-03-05", "2026-03-06"),
])
def test_resolve_date(raw, start, end):
    r = resolve_date(raw, TODAY)
    assert (r["start"], r["end"]) == (start, end)
    assert "assumed_year" not in r


def test_missing_year_uses_most_recent_past_date_and_says_so():
    r = resolve_date("March 5", TODAY)
    assert r["start"] == "2026-03-05" and r["assumed_year"] is True
    r = resolve_date("December 5", TODAY)            # December 2026 is still in the future
    assert r["start"] == "2025-12-05" and r["assumed_year"] is True


@pytest.mark.parametrize("raw", ["February 30 2026", "last 0 days", "last 5000 days",
                                 "sometime soon", "2026-13-01"])
def test_bad_dates_are_refused(raw):
    with pytest.raises(PlanningError):
        resolve_date(raw, TODAY)


def clause(intent, text):
    return ClauseResult(text=text, status=NLPStatus.OK, intent=intent, confidence=1.0,
                        margin=1.0, entities=extract_entities(text))


def plan_for(*clauses):
    nlp = NLPResult(original=" ".join(c.text for c in clauses),
                    status=NLPStatus.OK, clauses=list(clauses))
    return build_plan(nlp, today=TODAY)


def test_search_with_date_filter():
    t = plan_for(clause("SEARCH", "find PDFs modified last week")).tasks[0]
    assert t.parameters["file_types"] == ["pdf"]
    assert t.parameters["date_filter"] == {
        "text": "last week", "start": "2026-10-19", "end": "2026-10-26", "field": "modified"}


def test_created_field_and_date_only_search():
    t = plan_for(clause("SEARCH", "find files created in October 2026")).tasks[0]
    assert t.parameters["date_filter"]["field"] == "created"
    assert t.parameters["date_filter"]["start"] == "2026-10-01"


def test_handoff_example_end_to_end():
    plan = plan_for(clause("SEARCH", "Find PDFs modified in October 2026"),
                    clause("OPEN", "open the largest"),
                    clause("MOVE", "move the rest to Archive"))
    assert plan.tasks[0].parameters["date_filter"]["end"] == "2026-11-01"
    assert plan.tasks[2].parameters["targets"][0]["except_tasks"] == ["t2"]


@pytest.mark.parametrize("intent, text", [
    ("DELETE", "delete all PDFs older than 30 days"),                 # search first
    ("OPEN", "open report.pdf from last week"),
    ("SEARCH", "find PDFs between October 2026 and November 2026"),   # two dates
])
def test_dates_refused_where_unsafe_or_unclear(intent, text):
    with pytest.raises(PlanningError):
        plan_for(clause(intent, text))