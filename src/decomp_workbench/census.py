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


def _edit_distance(left: str, right: str) -> int:
    """Levenshtein distance, for telling a typo from an unrelated key."""

    if left == right:
        return 0
    previous = list(range(len(right) + 1))
    for row, lchar in enumerate(left, start=1):
        current = [row] + [0] * len(right)
        for column, rchar in enumerate(right, start=1):
            cost = 0 if lchar == rchar else 1
            current[column] = min(
                previous[column] + 1,  # deletion
                current[column - 1] + 1,  # insertion
                previous[column - 1] + cost,  # substitution
            )
        previous = current
    return previous[-1]


def _suggest(key: str, allowed: Mapping[str, str]) -> str | None:
    """The one registered key an unknown ``key`` most plausibly meant.

    Two shapes of typo, both cheap against a key list this short: a unique
    prefix (``pins_sha`` names only ``pins_shadowing``) and a small edit
    distance (``pins_shadowingg`` is one deletion from ``pins_shadowing``).
    Either has to be unambiguous -- when two registered keys tie, guessing
    one would be worse than naming neither, so this suggests nothing.
    """

    prefixed = [name for name in allowed if name != key and name.startswith(key)]
    if len(prefixed) == 1:
        return prefixed[0]

    scored = sorted((_edit_distance(key, name), name) for name in allowed)
    if not scored or scored[0][0] > 2:
        return None
    closest = [name for distance, name in scored if distance == scored[0][0]]
    return closest[0] if len(closest) == 1 else None


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
                suggestion = _suggest(key, allowed)
                hint = f" -- did you mean {suggestion!r}?" if suggestion else ""
                raise ValueError(
                    f"unknown census key {key!r}; this command reports "
                    f"{len(allowed)} keys and --explain-keys prints them "
                    f"with their meanings{hint}"
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
        if predicate.metric not in payload:
            # A registered key the report did not carry this time -- a view key
            # that needs --report-regs, say. Comparing it against nothing would
            # answer a question the run cannot answer.
            raise ValueError(
                f"census key {predicate.key!r} is not in this report; the "
                "option that produces it may not have been passed"
            )
        actual = payload[predicate.metric]
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
