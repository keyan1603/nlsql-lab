"""Model output that cannot even be tokenized (an unterminated quote, a stray backtick from a half-closed code fence) must be
reported as an ordinary syntax failure, never crash the run."""

import pytest

from nlsql.safety import check_select

BROKEN = [
    "SELECT a FROM t WHERE b = 'x' GROUP BY a\n``",
    "SELECT `a FROM t",
    "SELECT 'unterminated",
    "SELECT a FROM t WHERE c = \"open",
]


@pytest.mark.parametrize("sql", BROKEN)
def test_text_that_cannot_be_tokenized_is_a_syntax_failure_not_a_crash(sql):
    v = check_select(sql)
    assert not v.ok and v.kind == "syntax"
