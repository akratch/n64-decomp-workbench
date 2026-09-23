"""Source-level invariants the package maintains by convention across files.

Each invariant here is one a reviewer would otherwise have to re-check by
hand on every new call site, and each is currently held in seven or more
places with nothing enforcing it.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "decomp_workbench"


def _sequence_matcher_calls() -> list[tuple[Path, ast.Call]]:
    """Every ``SequenceMatcher(...)`` construction in the package."""
    found: list[tuple[Path, ast.Call]] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else func.id
                if isinstance(func, ast.Name)
                else None
            )
            if name == "SequenceMatcher":
                found.append((path, node))
    return found


class SequenceMatcherInvariants(unittest.TestCase):
    """``autojunk`` must never be left at its default in a comparison.

    difflib's "popular element" heuristic engages once ``b`` reaches 200 rows
    and then refuses to anchor a match on any row occurring in more than 1% of
    ``b``. Instruction and symbol streams are exactly where that misfires:
    masking operands collapses distinct rows onto a few shared keys, which is
    precisely how a row becomes "popular", so a stream can score *worse* after
    being made more similar. Measured on a heavily-diverged 400-row pair, the
    heuristic costs 1 row of 352 unmasked and 21 of 356 (6%) masked.

    The cost is zero on near-identical streams -- ``find_longest_match``
    extends blocks across junk -- which is why this survives casual testing
    and bites only where scores are actually ranked on.
    """

    def test_every_call_site_disables_the_popular_element_heuristic(self) -> None:
        calls = _sequence_matcher_calls()
        self.assertGreaterEqual(
            len(calls), 7, "expected the known call sites to be found"
        )
        offenders = []
        for path, call in calls:
            keyword = next((k for k in call.keywords if k.arg == "autojunk"), None)
            if keyword is None:
                offenders.append(f"{path.name}:{call.lineno} omits autojunk")
            elif not (
                isinstance(keyword.value, ast.Constant) and keyword.value.value is False
            ):
                offenders.append(
                    f"{path.name}:{call.lineno} does not pass autojunk=False"
                )
        self.assertEqual(offenders, [], "; ".join(offenders))


if __name__ == "__main__":
    unittest.main()
