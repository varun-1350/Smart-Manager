from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from backend.tools.filesystem.common import sha256_file

from .prepare import Operation
from .report import OperationOutcome


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_event(path, record: dict) -> None:
    """Append one JSON line and force it to disk before returning."""
    line = json.dumps({**record, "ts": _now()}, ensure_ascii=True,
                      separators=(",", ":"), default=str) + "\n"
    needs_newline = False
    try:                                  # a crash can leave a half-written last line
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            if fh.tell() > 0:
                fh.seek(-1, os.SEEK_END)
                needs_newline = fh.read(1) != b"\n"
    except FileNotFoundError:
        pass
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(("\n" if needs_newline else "") + line)
        fh.flush()
        os.fsync(fh.fileno())


class FileJournal:
    """One JSON-lines file per execution. The 'before' line reaches the disk BEFORE the
    change happens, so after a crash we know exactly which step was in flight."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.path: Path | None = None

    def _write(self, record: dict) -> None:
        if self.path is None:
            raise OSError("The journal hasn't been started.")
        append_event(self.path, record)

    def start(self, plan_id, digest, operations: list[Operation]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        safe = re.sub(r"[^A-Za-z0-9_-]", "", str(plan_id))[:40] or "plan"
        for n in range(100):
            candidate = self.directory / f"{stamp}-{safe}{'' if n == 0 else f'-{n}'}.jsonl"
            try:
                with open(candidate, "x", encoding="utf-8"):     # never reuse a file
                    pass
            except FileExistsError:
                continue
            self.path = candidate
            break
        else:
            raise OSError("Couldn't create a journal file.")
        self._write({"event": "start", "plan_id": plan_id, "digest": digest,
                     "operations": [o.to_dict() for o in operations]})

    def before(self, index: int, op: Operation) -> None:
        record = {"event": "before", "index": index, "op": op.to_dict()}
        if op.action == "edit_text_file" and op.source:
            record["before_sha256"] = sha256_file(op.source)   # lets recovery tell if it ran
        self._write(record)

    def after(self, index: int, op: Operation, outcome: OperationOutcome) -> None:
        self._write({"event": "after", "index": index, "status": outcome.status,
                     "message": outcome.message, "undo": outcome.undo,
                     "partial": outcome.partial, "verified": outcome.verified,
                     "output": outcome.output})

    def finish(self, status: str) -> None:
        self._write({"event": "finish", "status": status})


# ------------------------------------------------------------------- reading
@dataclass
class Step:
    index: int
    op: dict
    before_sha256: str | None = None
    outcome: dict | None = None          # None = it started but we never saw it end


@dataclass
class JournalRun:
    path: Path
    plan_id: str
    digest: str
    started_at: str
    operations: list[dict]
    steps: dict[int, Step] = field(default_factory=dict)
    finish_status: str | None = None
    undo_events: list[dict] = field(default_factory=list)
    damaged: bool = False                # a line in the middle couldn't be read

    @property
    def interrupted(self) -> bool:
        return self.finish_status is None

    def unknown_steps(self) -> list[Step]:
        return [s for _, s in sorted(self.steps.items()) if s.outcome is None]


def read_journal(path) -> JournalRun:
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    records, damaged = [], False
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            if not isinstance(rec, dict):
                raise ValueError("not an object")
        except ValueError:
            if i != len(lines) - 1:      # a torn LAST line is a normal crash; others are damage
                damaged = True
            continue
        records.append(rec)
    if not records or records[0].get("event") != "start":
        raise ValueError("it has no start record")
    first = records[0]
    run = JournalRun(path, str(first.get("plan_id", "")), str(first.get("digest", "")),
                     str(first.get("ts", "")), list(first.get("operations", [])), damaged=damaged)
    for rec in records[1:]:
        event, idx = rec.get("event"), rec.get("index")
        if event == "before" and isinstance(idx, int):
            run.steps[idx] = Step(idx, rec.get("op") or {}, rec.get("before_sha256"))
        elif event == "after" and isinstance(idx, int):
            run.steps.setdefault(idx, Step(idx, {})).outcome = rec
        elif event == "finish":
            run.finish_status = rec.get("status")
        elif event == "undo":
            run.undo_events.append(rec)
    return run


def list_runs(directory) -> tuple[list[JournalRun], list[str]]:
    """Every readable journal, plus a message for each one that couldn't be read."""
    d, runs, errors = Path(directory), [], []
    if not d.is_dir():
        return runs, errors
    for p in sorted(d.glob("*.jsonl")):
        try:
            runs.append(read_journal(p))
        except (OSError, ValueError) as exc:
            errors.append(f"{p.name}: {exc}")
    return runs, errors


def find_interrupted(directory, exclude=None) -> tuple[list[JournalRun], list[str]]:
    runs, errors = list_runs(directory)
    skip = Path(exclude) if exclude else None
    return [r for r in runs if r.interrupted and r.path != skip], errors


def acknowledge(path, note: str = "reviewed") -> None:
    """The user has seen an interrupted run. It stops being listed as interrupted."""
    append_event(path, {"event": "finish", "status": "interrupted_reviewed", "note": note})


def record_undo(path, outcomes) -> None:
    append_event(path, {"event": "undo", "results": [
        {"step": o.step, "status": o.status, "message": o.message} for o in outcomes]})