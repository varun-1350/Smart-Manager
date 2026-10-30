"""Generate synthetic intent data (train + eval) from templates.

    python -m backend.nlp.training.generate_data
    python -m backend.nlp.training.generate_data --train-per-intent 80 --eval-per-intent 15 --seed 7

Writes intents.json and eval_set.json next to this file. Hand-written examples go in
manual_intents.json ({"DELETE": ["..."]}) and manual_eval.json ([{"text":..,"intent":..}]).
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

from backend.nlp.entity_extractor import mask_entities
from backend.nlp.intents import LABELS

HERE = Path(__file__).parent

# Train and eval use DIFFERENT words for every slot, to test generalization.
POOLS = {
    "train": {
        "file": ["report.pdf", "budget.xlsx", "notes.txt", "invoice.docx", "photo.jpg",
                 "resume.docx", "plan.pptx", "data.csv", "Taxes_2025.pdf", '"My Report.pdf"'],
        "txtfile": ["notes.txt", "todo.txt", "ideas.txt", "diary.txt", "shopping.txt"],
        "path": [r"D:\Work\plan.docx", r"C:\Users\Admin\Documents\report.pdf",
                 r"E:\Photos\trip.jpg"],
        "dirpath": [r"D:\Projects", r"C:\Users\Admin\Downloads", r"E:\Backup"],
        "folder": ["Archive", "Backup", "Documents", "Downloads", "Desktop",
                   "Pictures", "Projects", "Finance"],
        "name": ["Projects", "Archive2026", "Backup", "Invoices", "Photos", "Temp",
                 "Scans", "Logs"],
        "new": ["final.pdf", "summary.docx", "budget_2026.xlsx", "cover_letter.docx",
                "old_notes.txt"],
        "type": ["pdf", "image", "spreadsheet", "presentation", "video", "document"],
        "types": ["PDFs", "images", "spreadsheets", "text files", "photos",
                  "presentations", "videos", "docx files"],
        "sort": ["largest", "newest", "oldest", "smallest"],
        "when": ["last week", "yesterday", "last month", "today", "in October 2026"],
        "n": ["7", "30", "90"],
        "person": ["John", "my boss", "Priya"],
        "topic": ["cheap flights", "python tutorials", "pizza places"],
        "text": ["'yo i am varun'", '"buy milk tomorrow"', "'meeting at 5 pm'",
                 '"remember to call John"', "'hello world'", '"move it to Archive"'],
        "old": ["'cat'", '"draft"', "'Monday'"],
        "newtext": ["'dog'", '"final"', "'Tuesday'"],
    },
    "eval": {
        "file": ["contract.pdf", "Sales_Q3.xlsx", "readme.md", "holiday.png",
                 "thesis.docx", "slides.pptx", "scan_01.jpg", '"Final Draft.docx"'],
        "txtfile": ["journal.txt", "draft.txt", "memo.txt"],
        "path": [r"D:\School\essay.docx", r"C:\Temp\log.txt"],
        "dirpath": [r"D:\Clients", r"F:\Media"],
        "folder": ["Work", "Clients", "Receipts", "Music", "Scans", "Taxes", "Travel"],
        "name": ["Clients", "Receipts", "Drafts", "Travel", "School"],
        "new": ["v2.pdf", "backup_copy.xlsx", "report_final.docx"],
        "type": ["photo", "song", "document", "pdf"],
        "types": ["PDF files", "pictures", "Excel files", "music files", "documents"],
        "sort": ["biggest", "latest", "oldest", "smallest"],
        "when": ["this week", "last year", "in March 2026", "on 2026-10-01"],
        "n": ["14", "60", "365"],
        "person": ["Sam", "the team", "my professor"],
        "topic": ["news", "cricket scores", "hotel deals"],
        "text": ["'see you soon'", '"pay the rent"', "'todo: gym'",
                 '"call mom tonight"', "'good night'"],
        "old": ["'red'", '"v1"'],
        "newtext": ["'blue'", '"v2"'],
    },
}

# {t} = a generic target: a filename, a path, "the largest pdf", "all PDFs", or "it"/"the rest"
TRAIN_TEMPLATES = {
    "SEARCH": [
        "find {types}", "search for {file}", "find all {types} modified {when}",
        "look for files named {name}", "search my computer for {types}", "locate {file}",
        "where is {file}", "find the {sort} {type}", "search for {types} created {when}",
        "find {types} older than {n} days", "find {file}", "look for {types}",
    ],
    "LIST": [
        "list files in {folder}", "show me what is in the {folder} folder",
        "list all files in this folder", "what files are in {folder}",
        "show the contents of {dirpath}", "list the {types} in {folder}",
        "list everything in {folder}", "display the files in the {folder} folder",
        "show folder contents", "list the current directory", "list {dirpath}",
        "list files",
    ],
    "OPEN": [
        "open {t}", "please open {t}", "launch {t}", "open the {sort} {type}",
        "can you open {t}", "open the folder {folder}", "start {file}", "open {path}",
        "open the file {file}", "open it", "open {dirpath}",
        "bring up {t}", "load {file}", "view {file}",
    ],
    "CREATE_FOLDER": [
        "create a folder named {name}", "make a new folder called {name}",
        "create folder {name}", "new folder {name}", "make a directory called {name}",
        "create a directory named {name}", "create a new folder {name}",
        "make folder {name}", "create folder {dirpath}",
        "i need a new folder named {name}", "create a folder", "make a new folder",
    ],
    "CREATE_TEXT_FILE": [
        "create a text file named {name}", "make a new text file called {name}",
        "create a text file called {txtfile}", "create {txtfile}", "new text file {name}",
        "make a txt file named {name}", "create a new file called {txtfile}",
        "create a text document named {name}", "create a text file",
        "make a new text file", "create a new text file {txtfile}",
    ],
    "MOVE": [
        "move {t} to {folder}", "move {t} into {folder}", "move all {types} to {folder}",
        "move the rest to {folder}", "please move {file} to {dirpath}",
        "transfer {t} to {folder}", "relocate {file} to {folder}",
        "shift {t} into the {folder} folder", "move the {sort} {type} to {folder}",
        "move them to {folder}", "move to {folder}", "move {file}", "move",
        "move {t} to {dirpath}","put {file} in {folder}", "put {file} into {folder}", "place {file} in {folder}",
        "drop {file} into {folder}", "stash {t} in {folder}", "send {file} to {folder}",
        "put {t} in the {folder} folder", "put all {types} in {folder}",
    ],
    "DELETE": [
        "delete {t}", "remove {file}", "send {t} to the recycle bin",
        "move {file} to the recycle bin", "trash {t}", "delete all {types}",
        "delete the {sort} {type}", "get rid of {file}", "erase {t}",
        "please delete {file}", "delete the rest", "delete",
        "delete {types} older than {n} days", "delete old files",
        "delete all {types} in {folder}","discard {t}", "throw out {t}", "put {t} in the trash", "bin {t}",
        "toss {file} in the trash", "dispose {file}",
    ],
    "COPY_TO_CLIPBOARD": [
        "copy {t} to the clipboard", "copy {file} to clipboard",
        "put {t} on the clipboard", "copy {file}",
        "copy the {sort} {type} to the clipboard", "clipboard copy {file}",
        "copy {t} to my clipboard", "copy all {types} to the clipboard",
        "copy the file {file}", "copy {t}",
    ],
    "COPY_PATH_TO_CLIPBOARD": [
        "copy the path of {t}", "copy path of {file}", "copy the file path of {file}",
        "copy {file} path to the clipboard",
        "copy the full path of {t} to the clipboard", "copy the location of {file}",
        "copy path", "copy the path to the clipboard",
        "put the path of {file} on the clipboard", "copy the folder path of {file}",
        "copy {file}'s path",
    ],
    "RENAME": [
        "rename {file} to {new}", "rename {file} as {new}",
        "change the name of {file} to {new}", "rename {t} to {new}",
        "rename the {sort} {type} to {new}", "rename {file}", "rename it to {new}",
        "rename", "please rename {file} to {new}", "rename {path} to {new}",
        "retitle {file} to {new}", "rename {t} as {new}",
        "i want {file} renamed to {new}", "rename {file} to {new} please",
    ],
    "EDIT_TEXT_FILE": [
        "in {txtfile} add {text}", "add {text} to {txtfile}", "append {text} to {txtfile}",
        "write {text} in {txtfile}", "insert {text} into {txtfile}",
        "in {txtfile} write {text}", "in {txtfile} append {text}",
        "add a line {text} to {txtfile}", "add the text {text} to {txtfile}",
        "write {text} into {txtfile}", "append the line {text} to {txtfile}",
        "add {text} at the end of {txtfile}",
        "replace {old} with {newtext} in {txtfile}",
        "in {txtfile} replace {old} with {newtext}",
        "substitute {old} with {newtext} in {txtfile}",
        "edit {txtfile}", "add {text} to it", "append {text} to the file",
        "write {text} in it", "add {text}",
        "write {text} to {txtfile}", "put {text} in {txtfile}", "type {text} into {txtfile}",
        "in {txtfile} put {text}", "add the line {text} to {txtfile}",
        "in {txtfile} insert the line {text}", "append {text} to {txtfile} please",
        "add {text} to the end of the file {txtfile}", "write the line {text} in {txtfile}",
        "in the file {txtfile} add {text}", "insert {text} at the end of {txtfile}",
        "replace {old} with {newtext}",
    ],
    "UNSUPPORTED": [
        "copy {file} to {folder}", "copy all {types} to {folder}",
        "what is the weather today", "write me a poem", "send an email to {person}",
        "play some music", "what is the capital of France", "tell me a joke",
        "install python", "shut down the computer", "run this script",
        "set a reminder for 5 pm", "translate this text to Spanish",
        "format the D drive", "download {file} from the internet", "hello",
        "who are you", "calculate tomorrow's stock price", "quit the application",
        "restart my pc", "compress {types} into a zip", "print {file}",
        "email {file} to {person}", "upload {file} to the cloud", "what time is it",
        "search the web for {topic}", "google {topic}", "undo the last change",
        "what is in {file}", "delete the last line of {txtfile}",
        "remove the first line from {txtfile}", "delete line {n} of {txtfile}",
        "clear the contents of {txtfile}",
        "make a copy of {file}", "back up {file} to {folder}", "read {file}",
        "summarize {file}", "convert {file} to pdf", "share {file} with {person}",
        "encrypt {file}", "what does {file} say", "email {types} to {person}",
    ],
}

# Different phrasings from the training templates, so eval measures generalization.
EVAL_TEMPLATES = {
    "SEARCH": [
        "look for every {type} file", "find {file} on my computer", "can you find {file}",
        "i need to find my {types}", "search for files called {name}",
        "hunt down {types} edited {when}", "find {types} created {when}",
    ],
    "LIST": [
        "what's inside the {folder} folder", "give me a list of files in {folder}",
        "list {dirpath}", "show every file in {folder}",
        "enumerate the {types} in {folder}",
    ],
    "OPEN": [
        "could you open {t} for me", "i want to open {file}", "pull up {file}",
        "open {file} please", "open up {t}",
    ],
    "CREATE_FOLDER": [
        "please create a folder called {name}", "add a new folder named {name}",
        "make a new directory {name}", "i want a folder named {name}",
        "create a new directory called {name}",
    ],
    "CREATE_TEXT_FILE": [
        "please make a text file named {name}", "generate a new text file {txtfile}",
        "i want a new txt file called {name}", "create an empty text file {txtfile}",
        "start a new text file named {name}",
    ],
    "MOVE": [
        "can you move {t} to {folder}", "i want to move {t} into {folder}",
        "relocate all {types} into {folder}", "move {t} over to the {folder} folder",
        "transfer {file} to {dirpath}","stick {file} in {folder}",
    ],
    "DELETE": [
        "could you delete {t}", "throw away {file}", "i want to delete {t}",
        "put {file} in the recycle bin", "remove all {types} older than {n} days",
        "dispose of {file}","toss {file} in the bin",
    ],
    "COPY_TO_CLIPBOARD": [
        "please copy {file} to the clipboard", "can you copy {t} to clipboard",
        "place {file} on my clipboard", "copy {types} to the clipboard",
    ],
    "COPY_PATH_TO_CLIPBOARD": [
        "copy the path for {file}", "i need the path of {t} on my clipboard",
        "copy {file} location to clipboard", "copy full path of {file}",
    ],
    "RENAME": [
        "can you rename {file} to {new}", "i want to rename {file} as {new}",
        "rename {file} into {new}", "i'd like to rename {t} to {new}",
        "rename the file {file} to {new}",
    ],
    "EDIT_TEXT_FILE": [
        "please add {text} to {txtfile}", "in {txtfile} please write {text}",
        "append the note {text} to {txtfile}", "in {txtfile} insert {text}",
        "write down {text} in {txtfile}", "can you add {text} to {txtfile}",
        "replace {old} by {newtext} in {txtfile}", "i want to edit {txtfile}",
    ],
    "UNSUPPORTED": [
        "duplicate {file} into {folder}", "what's the weather in Mumbai",
        "email this to my boss", "play a song", "zip {types} into an archive",
        "read {file} aloud", "who won the cricket match", "turn off wifi",
        "search the web for {topic}", "google {topic}", "undo the last change",
        "what is in {file}", "delete the last line of {txtfile}",
        "remove the first line from {txtfile}", "delete line {n} of {txtfile}",
        "clear the contents of {txtfile}","clone {file} into {folder}",
        
    ],
}

_SLOT = re.compile(r"\{(\w+)\}")


PREFIXES = ["can you ", "could you ", "please ", "i want to ", "i'd like to ", "would you "]
_NO_PREFIX_START = {"in", "the", "what", "what's", "where", "who", "how", "i", "hello",
                    "new", "please", "can", "could", "clipboard"}


def _can_prefix(template: str) -> bool:
    first = template.split(" ", 1)[0].lower()
    return not first.startswith("{") and first not in _NO_PREFIX_START


def _target(rng: random.Random, pool: dict, standalone: bool = False) -> str:
    # standalone = a request with no earlier step, so "it"/"the rest"/"the largest" can't be used
    kinds = (["file", "file", "path", "all"] if standalone
             else ["file", "file", "path", "typed", "all", "ref"])
    kind = rng.choice(kinds)
    if kind == "file":
        return rng.choice(pool["file"])
    if kind == "path":
        return rng.choice(pool["path"])
    if kind == "typed":
        return f"the {rng.choice(pool['sort'])} {rng.choice(pool['type'])}"
    if kind == "all":
        return f"all {rng.choice(pool['types'])}"
    return rng.choice(["it", "them", "the rest", "that file"])


def fill(template: str, rng: random.Random, pool: dict, *, augment: bool = False,
         standalone: bool = False) -> str:
    def pick(m: re.Match) -> str:
        key = m.group(1)
        return _target(rng, pool, standalone) if key == "t" else rng.choice(pool[key])
    text = _SLOT.sub(pick, template)
    if augment and _can_prefix(template) and rng.random() < 0.3:
        text = rng.choice(PREFIXES) + text          # real people say "can you ..."
    return text

def _key(text: str) -> str:
    """What the classifier actually sees (masked, lowercased)."""
    return " ".join(mask_entities(text).casefold().split())


def build_split(templates, pool, per_intent, rng, blocked=frozenset(), *,
                augment=False, standalone=False):
    """Return ({intent: [texts]}, conflicts). Duplicates (after masking) are dropped.
    A sentence that lands under two different intents is removed from BOTH."""
    data: dict[str, list[str]] = {label: [] for label in LABELS}
    owner: dict[str, tuple[str, str]] = {}
    banned: set[str] = set()
    conflicts: list[str] = []

    for intent in LABELS:
        tpls = templates[intent]
        tries = 0
        while len(data[intent]) < per_intent and tries < per_intent * 40:
            text = fill(tpls[tries % len(tpls)], rng, pool,
                        augment=augment, standalone=standalone)   # round-robin templates
            tries += 1
            key = _key(text)
            if key in blocked or key in banned:
                continue
            if key in owner:
                prev_intent, prev_text = owner[key]
                if prev_intent != intent:                      # ambiguous -> drop both
                    data[prev_intent].remove(prev_text)
                    del owner[key]
                    banned.add(key)
                    conflicts.append(f"'{text}' appears under {prev_intent} and {intent}")
                continue
            owner[key] = (intent, text)
            data[intent].append(text)
    return data, conflicts


def _load_json(name: str):
    path = HERE / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _check_label(label: str) -> None:
    if label not in LABELS:
        raise ValueError(f"Unknown intent '{label}'. Allowed: {LABELS}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate intent training/eval data")
    ap.add_argument("--train-per-intent", type=int, default=60)
    ap.add_argument("--eval-per-intent", type=int, default=12)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    train, c1 = build_split(TRAIN_TEMPLATES, POOLS["train"], args.train_per_intent, rng,
                            augment=True)

    manual_train = _load_json("manual_intents.json") or {}
    for label, texts in manual_train.items():
        _check_label(label)
        have = {_key(t) for t in train[label]}
        train[label] += [t for t in texts if _key(t) not in have]

    train_keys = {_key(t) for texts in train.values() for t in texts}
    evals, c2 = build_split(EVAL_TEMPLATES, POOLS["eval"], args.eval_per_intent, rng,
                            blocked=train_keys, standalone=True)

    eval_rows = [{"text": t, "intent": label} for label, texts in evals.items() for t in texts]
    for row in _load_json("manual_eval.json") or []:
        _check_label(row["intent"])
        if _key(row["text"]) not in train_keys:
            eval_rows.append(row)

    (HERE / "intents.json").write_text(
        json.dumps(train, indent=2, ensure_ascii=False), encoding="utf-8")
    (HERE / "eval_set.json").write_text(
        json.dumps(eval_rows, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{'intent':<26}{'train':>6}{'eval':>6}")
    for label in LABELS:
        n_eval = sum(1 for r in eval_rows if r["intent"] == label)
        print(f"{label:<26}{len(train[label]):>6}{n_eval:>6}")
    for msg in c1 + c2:
        print("CONFLICT (dropped):", msg)
    print(f"\nWrote {HERE / 'intents.json'}\nWrote {HERE / 'eval_set.json'}")


if __name__ == "__main__":
    main()