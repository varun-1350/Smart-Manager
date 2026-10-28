from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from .errors import PlanningError

ONE = timedelta(days=1)

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_PERIOD = re.compile(r"^(this|last)\s+(week|month|year)$")
_SPAN = re.compile(r"^(?:last|past)\s+(\d+)\s+(day|week|month|year)s?$")
_AGE = re.compile(r"^(older|newer)\s+than\s+(\d+)\s+(day|week|month|year)s?$")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_MONTH_YEAR = re.compile(r"^([a-z]+)\s+(\d{4})$")
_MONTH_DAY = re.compile(r"^([a-z]+)\s+(\d{1,2})(?:\s+(\d{4}))?$")
_DAY_MONTH = re.compile(r"^(\d{1,2})\s+([a-z]+)(?:\s+(\d{4}))?$")


def _unclear(raw: str) -> PlanningError:
    return PlanningError(f"I couldn't understand the date '{raw}'.")


def _day(year: int, month: int, day: int, raw: str) -> date:
    try:
        return date(year, month, day)
    except ValueError:
        raise PlanningError(f"'{raw}' isn't a real date.") from None


def _month(name: str, raw: str) -> int:
    if name not in _MONTHS:
        raise _unclear(raw)
    return _MONTHS[name]


def _count(text: str, raw: str) -> int:
    n = int(text)
    if not 1 <= n <= 1000:
        raise PlanningError(f"'{raw}': the number must be between 1 and 1000.")
    return n


def _shift_months(d: date, n: int) -> date:
    year, month0 = divmod(d.year * 12 + (d.month - 1) + n, 12)
    last_day = calendar.monthrange(year, month0 + 1)[1]
    return date(year, month0 + 1, min(d.day, last_day))


def _back(today: date, n: int, unit: str) -> date:
    if unit == "day":
        return today - timedelta(days=n)
    if unit == "week":
        return today - timedelta(weeks=n)
    if unit == "month":
        return _shift_months(today, -n)
    return _shift_months(today, -12 * n)


def _period(kind: str, today: date, offset: int) -> tuple[date, date]:
    if kind == "week":
        monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
        return monday, monday + timedelta(weeks=1)
    if kind == "month":
        start = _shift_months(today.replace(day=1), offset)
        return start, _shift_months(start, 1)
    return date(today.year + offset, 1, 1), date(today.year + offset + 1, 1, 1)


def _out(raw: str, start: date | None, end: date | None) -> dict:
    return {"text": raw,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None}


def _named_day(name: str, day: str, year: str | None, raw: str, today: date) -> dict:
    month = _month(name, raw)
    if year is not None:
        d = _day(int(year), month, int(day), raw)
        return _out(raw, d, d + ONE)
    d = _day(today.year, month, int(day), raw)
    if d > today:                                   # no year given: most recent PAST occurrence
        d = _day(today.year - 1, month, int(day), raw)
    out = _out(raw, d, d + ONE)
    out["assumed_year"] = True                      # so the approval screen can show it
    return out


def resolve_date(raw: str, today: date) -> dict:
    """'last week' -> {'text', 'start', 'end'} with ISO dates, end exclusive.
    None means open-ended. Anything unclear raises PlanningError."""
    t = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", raw.lower()).replace(",", " ")
    t = " ".join(t.split())
    try:
        if t == "today":
            return _out(raw, today, today + ONE)
        if t == "yesterday":
            return _out(raw, today - ONE, today)
        if m := _PERIOD.match(t):
            start, end = _period(m.group(2), today, 0 if m.group(1) == "this" else -1)
            return _out(raw, start, end)
        if m := _SPAN.match(t):
            return _out(raw, _back(today, _count(m.group(1), raw), m.group(2)), today + ONE)
        if m := _AGE.match(t):
            cutoff = _back(today, _count(m.group(2), raw), m.group(3))
            return _out(raw, None, cutoff) if m.group(1) == "older" else _out(raw, cutoff, None)
        if m := _ISO.match(t):
            d = _day(int(m.group(1)), int(m.group(2)), int(m.group(3)), raw)
            return _out(raw, d, d + ONE)
        if m := _MONTH_YEAR.match(t):
            start = _day(int(m.group(2)), _month(m.group(1), raw), 1, raw)
            return _out(raw, start, _shift_months(start, 1))
        if m := _MONTH_DAY.match(t):
            return _named_day(m.group(1), m.group(2), m.group(3), raw, today)
        if m := _DAY_MONTH.match(t):
            return _named_day(m.group(2), m.group(1), m.group(3), raw, today)
    except (ValueError, OverflowError):
        raise _unclear(raw) from None
    raise _unclear(raw)


def build_date_filter(dates: list[str], field: str | None, today: date) -> dict | None:
    if not dates:
        return None
    if len(dates) > 1:
        raise PlanningError("I can filter by one date or range at a time.")
    out = resolve_date(dates[0], today)
    out["field"] = field or "modified"      # default when the user didn't say
    return out