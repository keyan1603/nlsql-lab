"""The labelled question set: load it and validate that it is well formed."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from nlsql.config import ROOT

EXPECTED = {"answer", "unanswerable", "clarify"}
DIFFICULTY = {"easy", "medium", "hard"}


@dataclass(frozen=True)
class Question:
    id: str
    category: str
    difficulty: str
    expected: str
    question: str
    gold_sql: str | None
    order_matters: bool
    tests: str
    float_tol: float = 0.0


def load_questions(path: Path | None = None) -> list[Question]:
    raw = json.loads((path or ROOT / "data" / "questions.json").read_text(encoding="utf-8"))
    out = []
    for q in raw["questions"]:
        out.append(Question(id=q["id"], category=q["category"], difficulty=q["difficulty"], expected=q["expected"],
                            question=q["question"], gold_sql=q.get("gold_sql"), order_matters=bool(q.get("order_matters", False)),
                            tests=q.get("tests", ""), float_tol=float(q.get("float_tol", 0.0))))
    return out


def problems(questions: list[Question]) -> list[str]:
    """Everything wrong with the set, as readable sentences (empty means well formed)."""
    found: list[str] = []
    seen: set = set()
    for q in questions:
        if q.id in seen:
            found.append(f"{q.id}: duplicate id")
        seen.add(q.id)
        if q.expected not in EXPECTED:
            found.append(f"{q.id}: expected must be one of {sorted(EXPECTED)}")
        if q.difficulty not in DIFFICULTY:
            found.append(f"{q.id}: difficulty must be one of {sorted(DIFFICULTY)}")
        if q.expected == "answer" and not q.gold_sql:
            found.append(f"{q.id}: an answerable question needs gold_sql")
        if q.expected != "answer" and q.gold_sql:
            found.append(f"{q.id}: a {q.expected} question must not have gold_sql")
        if not q.question.strip().endswith(("?", ".")):
            found.append(f"{q.id}: question should be a sentence")
    return found
