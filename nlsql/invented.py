"""Find values in a generated query that the question never states (an 'invented' filter).

Only two kinds are checked, because they have an unambiguous test: a number compared with `=`, `IN` or a range on a column
and a quoted date. A value counts as stated when its digits occur in the question or its English number word does.
Coded text values (`'PL'` for platinum) are not checked: the question legitimately names them in words.
"""
from __future__ import annotations

import re

_WORDS = {"0": "zero none", "1": "one first single once", "2": "two second twice", "3": "three third", "4": "four fourth", "5": "five fifth",
          "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten"}
_NUM = re.compile(r"(?<![\w.'])(?:\w+\.)?([a-z_]\w*)\s*(?:=|<>|!=|>=|<=|>|<)\s*(-?\d+(?:\.\d+)?)\b(?!\s*[-:])", re.I)
_IN = re.compile(r"\b([a-z_]\w*)\s+IN\s*\(\s*(\d+(?:\s*,\s*\d+)*)\s*\)", re.I)
# 0/1 flag columns: the question says "active" or "discontinued", not "1"
_FLAGS = {"is_actv", "disc_flag"}
_DATE = re.compile(r"'(\d{4}-\d{2}(?:-\d{2})?)(?:[ T][\d:]+)?'")


def _stated(num: str, q: str) -> bool:
    ql = q.lower()
    if "." in num and float(num) == int(float(num)):
        num = str(int(float(num)))
    if re.search(rf"(?<![\d.]){re.escape(num)}(?![\d])", ql):
        return True
    return any(re.search(rf"\b{w}\b", ql) for w in _WORDS.get(num, "").split())


def invented_values(question: str, sql: str) -> list[str]:
    # drop string literals before looking for numbers, so '2024-01-01' or 'C-1002' do not count as numeric filters
    bare = re.sub(r"'[^']*'", "''", sql)
    out = []
    cand = [n for c, n in _NUM.findall(bare) if c.lower() not in _FLAGS]
    cand += [x for c, g in _IN.findall(bare) if c.lower() not in _FLAGS for x in re.split(r"\s*,\s*", g)]
    for n in cand:
        if not _stated(n, question) and n not in out:
            out.append(n)
    for d in _DATE.findall(sql):
        parts = d.split("-")
        if d not in question and not (len(parts) >= 2 and d[:7] in question) and parts[0] not in question:
            out.append(d) if d not in out else None
    return out
