"""``--census``: ask a question about a report and get it back as an exit code.

Campaign agents rebuilt this filter at least seven times in one day, always as
an objdump-plus-regular-expression layer outside the workbench, because the only
way to ask "is this variant's frame -128 with no register residual left?" from a
shell loop was to run the comparison, emit JSON, and parse it. A predicate over
the keys the command already reports removes that layer: a 2500-variant sweep
becomes a ``for`` loop and a test, at roughly the cost of the comparison itself.

The exit status is the contract:

* ``0`` -- the report was produced and every predicate held;
* ``3`` -- the report was produced and at least one predicate failed;
* ``2`` -- the census could not be evaluated at all: malformed syntax, a key
  that is not in the command's registry, or a key whose value is a list or an
  object rather than a scalar.

``3`` is deliberately not ``1``. ``--fail-on-mismatch`` already answers with
``1`` and means "this candidate is not a match"; a filter that answered with the
same status could not be told apart from it inside a loop, and the two questions
are independent -- a variant can be the shape you are looking for and still not
be the match.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: Status returned when the report was produced and a predicate did not hold.
CENSUS_FAILURE_EXIT = 3

#: Entries are comma-separated. A comma only separates when what follows it
#: looks like the start of another entry, so a value that contains one --
#: ``verdict=mixed(constant:1, register:2)`` -- survives intact.
ENTRY_SEPARATOR_RE = re.compile(r",(?=[A-Za-z_][A-Za-z0-9_]*=)")

TRUE_WORDS = frozenset({"true", "yes", "1"})
FALSE_WORDS = frozenset({"false", "no", "0"})
EMPTY_WORDS = frozenset({"none", "null", ""})


@dataclass(frozen=True)
class Predicate:
    """One parsed ``KEY=VALUE`` question, with the key it will read."""

    key: str
    """The spelling the caller typed, which is what any message quotes back."""

    metric: str
    """The canonical report key that spelling resolves to."""

    expected: str


@dataclass(frozen=True)
class CensusResult:
    """One evaluated predicate."""

    key: str
    expected: str
    actual: Any
    passed: bool

    @property
    def line(self) -> str:
        """Render the one line this predicate prints.

        The actual value is printed only when it differs from the question,
        because a passing line whose value repeats itself is noise in a loop
        that prints thousands of them.
        """

        verdict = "PASS" if self.passed else "FAIL"
        detail = "" if self.passed else f" (actual {self.actual})"
        return f"census: {verdict} {self.key}={self.expected}{detail}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "expected": self.expected,
            "actual": self.actual,
            "pass": self.passed,
        }


def parse_census(
    expressions: Sequence[str], *, allowed: Mapping[str, str]
) -> tuple[Predicate, ...]:
    """Parse ``--census`` values against the keys one command reports.

    Parsing is separated from evaluation so that a typo fails before the
    command disassembles anything: a sweep that spends a compile per candidate
    should not spend one to learn that a key is misspelled.
    """

    predicates: list[Predicate] = []
    for expression in expressions:
        entries = ENTRY_SEPARATOR_RE.split(expression)
        for entry in entries:
            key, separator, expected = entry.partition("=")
            if not separator or not key:
                raise ValueError(
                    f"census entry {entry!r} is not KEY=VALUE; "
                    "write --census aligned_register=0,frame=-128"
                )
            metric = allowed.get(key)
            if metric is None:
                raise ValueError(
                    f"unknown census key {key!r}; this command reports "
                    f"{len(allowed)} keys and --explain-keys prints them "
                    "with their meanings"
                )
            predicates.append(Predicate(key=key, metric=metric, expected=expected))
    return tuple(predicates)


def matches(actual: Any, expected: str) -> bool:
    """Compare one reported value with one written value.

    Comparison is by the reported value's own type rather than by rendered
    text, so ``exact=true`` reads a boolean, ``frame=-0x80`` reads an integer in
    any base the report could have printed it in, and a verdict compares as the
    string it is.
    """

    if isinstance(actual, bool):
        word = expected.strip().lower()
        if word in TRUE_WORDS:
            return actual
        if word in FALSE_WORDS:
            return not actual
        raise ValueError(
            f"census value {expected!r} is not true or false; this key reports "
            "a boolean"
        )
    if isinstance(actual, int):
        try:
            return int(expected, 0) == actual
        except ValueError:
            raise ValueError(
                f"census value {expected!r} is not an integer; this key "
                "reports a number"
            ) from None
    if actual is None:
        return expected.strip().lower() in EMPTY_WORDS
    return expected == str(actual)


def evaluate_census(
    predicates: Sequence[Predicate], payload: Mapping[str, Any]
) -> list[CensusResult]:
    """Answer every predicate against one report payload."""

    results: list[CensusResult] = []
    for predicate in predicates:
        actual = payload.get(predicate.metric)
        if isinstance(actual, list | dict):
            raise ValueError(
                f"census key {predicate.key!r} reports a "
                f"{type(actual).__name__}, not a single value; census "
                "predicates compare scalars"
            )
        try:
            passed = matches(actual, predicate.expected)
        except ValueError as error:
            raise ValueError(f"{error} ({predicate.key})") from None
        results.append(
            CensusResult(
                key=predicate.key,
                expected=predicate.expected,
                actual=actual,
                passed=passed,
            )
        )
    return results


def census_status(results: Sequence[CensusResult], *, otherwise: int) -> int:
    """Return the census exit status, or the command's own status."""

    if any(not item.passed for item in results):
        return CENSUS_FAILURE_EXIT
    return otherwise


def print_census(results: Sequence[CensusResult]) -> None:
    """Print one PASS/FAIL line per predicate, in the order they were asked."""

    for item in results:
        print(item.line)
