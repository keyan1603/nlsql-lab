"""The hard-pair training data: structure, family mapping, and no overlap with any test question or held-out cell."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import make_hard_data as mhd                                   # noqa: E402
from make_terse_data import test_cells                         # noqa: E402
from make_training_data import tests_for_leaks                 # noqa: E402
from nlsql.schema_link import parse_schema                     # noqa: E402
from nlsql.traindata import LeakFilter, filter_cells           # noqa: E402

TRAIN = ROOT / "train" / "data" / "hard_train.jsonl"


def test_jobs_cover_every_family_and_area():
    jobs = mhd.jobs()
    assert {j["technique"] for j in jobs} == set(mhd.HARD) == set(mhd.FAMILY_OF)
    assert len(jobs) == len(mhd.HARD) * 5 and len({j["id"] for j in jobs}) == len(jobs)


@pytest.mark.skipif(not TRAIN.exists(), reason="hard_train.jsonl not built")
def test_new_hard_pairs_are_clear_of_every_test_question_and_cell():
    leak = LeakFilter(tests_for_leaks())
    held = test_cells()
    cols = {t.name: {c.name for c in t.columns} for t in parse_schema(True)}
    rows = [json.loads(line) for line in TRAIN.read_text(encoding="utf-8").splitlines()]
    new = [r for r in rows if r["source"] == "new_hard_teacher_verified"]
    assert len(new) > 500
    for r in new:
        sql = r["messages"][-1]["content"].removeprefix("```sql").removesuffix("```").strip()
        assert leak.why(r["messages"][1]["content"], sql) is None
        assert not filter_cells(sql, cols) & held


@pytest.mark.skipif(not TRAIN.exists(), reason="hard_train.jsonl not built")
def test_replay_keeps_declines_in_the_mix():
    rows = [json.loads(line) for line in TRAIN.read_text(encoding="utf-8").splitlines()]
    declines = [r for r in rows if r["messages"][-1]["content"].startswith("--")]
    assert len(declines) >= 150 and {r["messages"][-1]["content"].split(":")[0] for r in declines} == {"-- UNANSWERABLE", "-- CLARIFY"}
