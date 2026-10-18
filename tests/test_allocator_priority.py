"""Synthetic arithmetic only; no proprietary traces or allocator proof."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from decomp_workbench.allocator_priority import (
    PriorityError,
    main,
    normalized_units,
    priority_report,
    raw_unit_band,
    strict_net_window,
)


def row(identifier: str, order: int, net: int, raw: int) -> dict[str, Any]:
    return {
        "id": identifier,
        "order": order,
        "phase": "p1",
        "gross": net + 3,
        "charge_a": 1,
        "charge_b": 2,
        "occurrences": 1 if raw else 0,
        "auxiliary_blocks": list(range(max(0, raw - 1))),
    }


class PriorityTests(unittest.TestCase):
    def test_native_compression_boundaries(self) -> None:
        for raw, units in [
            (0, 0),
            (1, 1),
            (2, 2),
            (3, 2),
            (5, 2),
            (6, 3),
            (21, 6),
            (22, 7),
            (25, 7),
            (26, 8),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(normalized_units(raw), units)
                lo, hi = raw_unit_band(units)
                self.assertLessEqual(lo, raw)
                self.assertGreaterEqual(hi, raw)

    def test_unit_bands_cover_each_raw_once(self) -> None:
        for raw in range(150):
            matches = [
                u
                for u in range(40)
                if raw_unit_band(u)[0] <= raw <= raw_unit_band(u)[1]
            ]
            self.assertEqual(matches, [normalized_units(raw)])

    def test_counterfactual_reports_every_role_and_boundaries(self) -> None:
        result = priority_report(
            [row("a", 1, 100, 22), row("b", 2, 30, 2)],
            {"a": {"raw_delta": 3, "net_delta": 10}},
        )
        a = result["rows"][0]
        self.assertEqual(
            (a["gross"], a["charge_a"], a["charge_b"], a["net"]),
            ("103", "1", "2", "110"),
        )
        self.assertEqual((a["units"], a["raw_additions_to_next_unit"]), (7, 1))
        self.assertEqual(result["p1_priority_groups"], [["a"], ["b"]])
        self.assertFalse(result["allocation_proof"])
        changed = priority_report([row("a", 1, 100, 22)], {"a": {"raw_delta": 4}})
        self.assertEqual(changed["rows"][0]["units"], 8)

    def test_ties_preserve_observation_without_claiming_native_tie_rule(self) -> None:
        result = priority_report(
            [row("later-id", 1, 20, 2), row("earlier-id", 2, 30, 6)]
        )
        self.assertEqual(result["p1_priority_groups"], [["later-id", "earlier-id"]])
        self.assertIn(
            "ties have no inferred native order", " ".join(result["assumptions"])
        )

    def test_phase_two_never_reorders_by_priority(self) -> None:
        rows = [row("a", 1, 1, 2), row("b", 2, 100, 2)]
        for item in rows:
            item["phase"] = "p2"
        result = priority_report(rows, {"a": {"net_delta": 1000}})
        self.assertEqual(result["p2_observed_order"], ["a", "b"])
        self.assertEqual(result["p1_priority_groups"], [])

    def test_same_priority_does_not_mean_same_cost_relation(self) -> None:
        rows = [row("a", 1, 10, 2), row("b", 2, 15, 6)]
        rows[0]["bestcost"] = 10
        rows[1]["bestcost"] = 10
        result = priority_report(rows)
        self.assertEqual(result["p1_priority_groups"], [["a", "b"]])
        self.assertEqual(
            [r["net_vs_bestcost"] for r in result["rows"]], ["equal", "greater"]
        )

    def test_two_changes_restore_a_coupled_order(self) -> None:
        rows = [row("a", 1, 8, 2), row("b", 2, 10, 2), row("c", 3, 6, 2)]

        def groups(changes: dict[str, dict[str, int]]) -> list[list[str]]:
            return priority_report(rows, changes)["p1_priority_groups"]  # type: ignore[no-any-return]

        desired = [["a"], ["c"], ["b"]]
        self.assertNotEqual(groups({"a": {"net_delta": 6}}), desired)
        self.assertNotEqual(groups({"c": {"net_delta": 6}}), desired)
        self.assertEqual(
            groups({"a": {"net_delta": 6}, "c": {"net_delta": 6}}), desired
        )

    def test_strict_window_keeps_equal_endpoints_out(self) -> None:
        self.assertEqual(
            strict_net_window("4.25", "5.5", 4), {"net_gt": "17", "net_lt": "22"}
        )
        for args in [(1, 1, 2), (2, 1, 2), (1, 2, 0)]:
            with self.assertRaises(PriorityError):
                strict_net_window(*args)

    def test_invalid_observations_fail_closed(self) -> None:
        invalid_rows: list[dict[str, Any]] = [
            {"occurrences": True},
            {"auxiliary_blocks": [1, 1]},
            {"gross": "nan"},
            {"charge_a": "inf"},
            {"phase": "p3"},
        ]
        for change in invalid_rows:
            item = row("a", 1, 5, 2) | change
            with self.subTest(change=change), self.assertRaises(PriorityError):
                priority_report([item])
        invalid_changes: list[dict[str, dict[str, Any]]] = [
            {"missing": {}},
            {"a": {"raw_delta": -3}},
            {"a": {"raw_delta": True}},
            {"a": {"phase": "p2"}},
        ]
        for changes in invalid_changes:
            with self.subTest(changes=changes), self.assertRaises(PriorityError):
                priority_report([row("a", 1, 5, 2)], changes)
        with self.assertRaises(PriorityError):
            priority_report([row("a", 1, 5, 2), row("a", 2, 3, 2)])
        with self.assertRaises(PriorityError):
            priority_report([row("a", 1, 5, 2), row("b", 1, 3, 2)])
        with self.assertRaises(PriorityError):
            priority_report([row("a", 1, 5, 0)])

    def test_module_cli_uses_json_and_refuses_bad_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(
                json.dumps({"decisions": [row("a", 1, 5, 2)]}), encoding="utf-8"
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([str(path)]), 0)
            self.assertFalse(json.loads(out.getvalue())["allocation_proof"])
            path.write_text('{"decisions": [null]}', encoding="utf-8")
            with (
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                main([str(path)])
            self.assertEqual(error.exception.code, 2)
