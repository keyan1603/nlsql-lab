"""Which model should answer: the local fine-tuned one or a frontier model.

The router reads the question text only (no gold query, no category label, no test result) and returns where to send it.
The rules are plain regular expressions, grouped into reasoning families that a small model is known to struggle with: a question that
needs several steps before the final query. Cheap, deterministic, explainable, and unit tested.

There is a second, runtime signal that needs no text rules: what the local model did. A database error, an empty result or a decline
sends the question up to the frontier model (see `escalate`). The question rules decide where a question goes first; the runtime
signal catches what the rules missed.

Measured limits (see docs/results/heldout.md and docs/results/learned_router.md). The regular expressions were written after the
test categories were known. On 181 questions they sent 31% to the frontier model and scored only slightly above a random router
sending the same share. On 52 fresh questions phrased differently they matched 1 question and caught none of the 20 the local model
got wrong. Treat the rules as a cheap, explainable first filter that depends on the wording of the questions; the runtime signals
(`escalate`, `nlsql.invented`, and the agreement between two local models in scripts/agreement_router.py) are what carried the result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LOCAL, FRONTIER = "local", "frontier"

# Each family is one kind of multi-step reasoning. A question that matches `threshold` or more families goes to the frontier model.
FAMILIES: dict[str, re.Pattern] = {
    # a number computed over an ordered or partitioned set of rows: ranking, running totals, previous/next row, share of the total
    "window": re.compile(
        r"\b(running|cumulative|moving|rolling|rank(?:ed|ing)?|dense rank|row number|percentile|quartile|decile|previous|prior|preceding|"
        r"following|next order|consecutive|month[- ]over[- ]month|week[- ]over[- ]week|year[- ]over[- ]year|compared with the (?:previous|prior)|"
        r"change from|difference from the|latest|most recent|earliest|first order|top \d+ (?:per|for each|within|in each)|"
        r"within each|in each [a-z ]{1,25} (?:highest|largest|top|most|best)|share of (?:the )?total)\b", re.I),
    # grouping by a calendar period, or a trailing window of time
    "time_bucket": re.compile(
        r"\b(?:per|by|each|every) (?:calendar )?(?:month|quarter|week|year|hour)\b|\bmonthly\b|\bweekly\b|\bquarterly\b|\byearly\b|"
        r"\bday of the week\b|\byear[- ]to[- ]date\b|\btrailing\b|\b(?:last|past|previous) \d+ (?:days|weeks|months)\b|\bbucket", re.I),
    # the question defines a term and then asks about it
    "defined_term": re.compile(
        r"(?:^|[.?!]\s+)(?:a|an|the)\s+[a-z ]{2,40}\s+(?:is|are)\s+(?:a|an|one|when|any|defined|considered|someone|anyone)\b|"
        r"\b(?:is defined as|we define|counts as|is considered|is classified as|that is,|which means|is deemed)\b", re.I),
    # the answer is built in stages: filter a group, then ask something about that group, or a ratio of two groups
    "multi_step": re.compile(
        r"\b(?:of those|of these|of the (?:customers|orders|tickets|users|employees|products) who|among those|among the (?:customers|users) who|"
        r"and then|who also|funnel|conversion|what (?:percent|percentage|proportion|fraction|share)|percentage of|proportion of|fraction of|"
        r"as a (?:percentage|share|fraction)|for the first time|returned? (?:again|later)|retention|churn|cohort)\b", re.I),
    # sets: in A and B, in A but not B, never, neither
    "set_logic": re.compile(
        r"\b(?:both|but not|but never|neither|never (?:ordered|placed|had|opened|bought)|without any|have not|has not|have no|has no|"
        r"do not have|does not have|at least one [a-z ]{1,30} and (?:at least )?one|in common|appear in both|other than those|except those|"
        r"not (?:also )?(?:in|on|among)|either [a-z ]{1,30} or)\b", re.I),
    # compare each row with an aggregate of its own group
    "correlated": re.compile(
        r"\b(?:more than the average|above the average|below the average|higher than the average|lower than the average|"
        r"above[- ]average|below[- ]average|than their own|than (?:its|their) (?:customer|region|category|tier)'?s?|"
        r"compared with the average|exceed(?:s|ed)? the average|largest .* for each|for each .* with the (?:highest|lowest))\b", re.I),
}


@dataclass(frozen=True)
class Route:
    target: str
    families: tuple[str, ...]
    reason: str


def families_of(question: str) -> tuple[str, ...]:
    return tuple(name for name, pat in FAMILIES.items() if pat.search(question))


def route(question: str, threshold: int = 1) -> Route:
    """Send the question to the frontier model when it matches at least `threshold` multi-step families."""
    hit = families_of(question)
    if len(hit) >= threshold:
        return Route(FRONTIER, hit, "multi-step cues: " + ", ".join(hit))
    return Route(LOCAL, hit, "routine question" if not hit else "one weak cue, kept local")


def escalate(kind: str, outcome_status: str, question: str | None = None, sql: str | None = None) -> str | None:
    """Why a local answer should be redone by the frontier model, or None to accept it.
    kind: what the local model produced ('sql', 'refusal', 'clarify'); outcome_status: how the query ran
    ('ok', 'error', 'empty', 'n/a' for a non-query). When question and sql are given, a query that filters on a number or date the
    question never states (an invented filter, see nlsql/invented.py) is escalated too."""
    if kind in ("refusal", "clarify"):
        return "the local model declined"
    if outcome_status == "error":
        return "the database rejected the local query"
    if outcome_status == "empty":
        return "the local query returned no rows"
    if question is not None and sql and kind == "sql":
        from nlsql.invented import invented_values
        inv = invented_values(question, sql)
        if inv:
            return "the local query filters on a value the question does not state: " + ", ".join(inv)
    return None
