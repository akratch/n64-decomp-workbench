"""Heal-signature scoring: the watchlist, its columns, and its refusals."""

from __future__ import annotations

import argparse
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from mips_asm import assemble

from decomp_workbench.compare import compare_instructions
from decomp_workbench.model import Comparison
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.object_cli import compare_dumps_command
from decomp_workbench.watch_rows import (
    BROKEN,
    HEALED,
    OUT_OF_RANGE,
    WatchRow,
    WatchRowError,
    evaluate_watch_rows,
    parse_watch_rows,
    watch_row_lines,
    watch_row_payload,
    watch_signature,
)

TARGET = [
    "addiu sp,sp,-16",
    "addu v0,a0,a1",
    "addiu t0,v0,4",
    "or t1,t0,a2",
    "jr ra",
    "addiu sp,sp,16",
]
#: Rows 1 and 3 differ; rows 0, 2, 4 and 5 do not.
CANDIDATE = [
    "addiu sp,sp,-16",
    "addu v1,a0,a1",
    "addiu t0,v0,4",
    "or t1,t0,a3",
    "jr ra",
    "addiu sp,sp,16",
]


def _comparison() -> Comparison:
    return compare_instructions(
        parse_disassembly(assemble(TARGET, symbol="demo")),
        parse_disassembly(assemble(CANDIDATE, symbol="demo")),
        target_name="target.o",
        candidate_name="candidate.o",
        symbol=None,
    )


class ParseTests(unittest.TestCase):
    def test_bare_rows_label_themselves(self) -> None:
        self.assertEqual(
            parse_watch_rows("49,1620,1677"),
            (WatchRow(49, "49"), WatchRow(1620, "1620"), WatchRow(1677, "1677")),
        )

    def test_named_columns(self) -> None:
        self.assertEqual(
            parse_watch_rows("r49=49, cx2=1620"),
            (WatchRow(49, "r49"), WatchRow(1620, "cx2")),
        )

    def test_a_repeated_row_is_an_error_not_a_deduplicated_list(self) -> None:
        with self.assertRaises(WatchRowError) as caught:
            parse_watch_rows("a=7,b=7")
        self.assertIn("watched twice", str(caught.exception))

    def test_a_non_row_token_names_both_spellings(self) -> None:
        with self.assertRaises(WatchRowError) as caught:
            parse_watch_rows("cx2")
        self.assertIn("LABEL=ROW", str(caught.exception))

    def test_no_specification_is_no_rows(self) -> None:
        self.assertEqual(parse_watch_rows(None), ())

    def test_file_form_accepts_a_list_of_objects(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "probes.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "fp-tail",
                        "rows": [
                            {"row": 49, "label": "r49"},
                            {"row": 1620, "label": "cx2"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                parse_watch_rows(f"@{path}"),
                (WatchRow(49, "r49"), WatchRow(1620, "cx2")),
            )

    def test_file_form_accepts_a_bare_label_mapping(self) -> None:
        with TemporaryDirectory() as temp:
            path = Path(temp) / "probes.json"
            path.write_text(json.dumps({"r49": 49}), encoding="utf-8")
            self.assertEqual(parse_watch_rows(f"@{path}"), (WatchRow(49, "r49"),))

    def test_a_missing_file_is_reported_as_such(self) -> None:
        with self.assertRaises(WatchRowError) as caught:
            parse_watch_rows("@/nonexistent/probes.json")
        self.assertIn("cannot read", str(caught.exception))


class EvaluationTests(unittest.TestCase):
    def test_healed_and_broken_columns(self) -> None:
        comparison = _comparison()
        results = evaluate_watch_rows(
            parse_watch_rows("a=0,b=1,c=2,d=3"),
            diff_sites=comparison.diff_sites,
            compared_rows=len(TARGET),
        )
        self.assertEqual(watch_signature(results), f"{HEALED}{BROKEN}{HEALED}{BROKEN}")

    def test_a_broken_row_carries_its_class_and_both_sides(self) -> None:
        comparison = _comparison()
        (result,) = evaluate_watch_rows(
            (WatchRow(1, "b"),),
            diff_sites=comparison.diff_sites,
            compared_rows=len(TARGET),
        )
        self.assertFalse(result.healed)
        self.assertEqual(result.difference, "register")
        self.assertIn("v0", str(result.target))
        self.assertIn("v1", str(result.candidate))

    def test_a_row_past_the_end_is_not_called_healed(self) -> None:
        # The failure this glyph exists for: a candidate that lost the tail of
        # the function would otherwise print a clean signature over rows
        # neither object has.
        comparison = _comparison()
        (result,) = evaluate_watch_rows(
            (WatchRow(9000, "tail"),),
            diff_sites=comparison.diff_sites,
            compared_rows=len(TARGET),
        )
        self.assertIsNone(result.healed)
        self.assertEqual(result.column, OUT_OF_RANGE)

    def test_the_payload_tallies_every_state(self) -> None:
        comparison = _comparison()
        payload = watch_row_payload(
            evaluate_watch_rows(
                parse_watch_rows("a=0,b=1,tail=9000"),
                diff_sites=comparison.diff_sites,
                compared_rows=len(TARGET),
            )
        )
        self.assertEqual(payload["watch_signature"], f"{HEALED}{BROKEN}{OUT_OF_RANGE}")
        self.assertEqual(payload["watch_healed"], 1)
        self.assertEqual(payload["watch_broken"], 1)
        self.assertEqual(payload["watch_out_of_range"], 1)

    def test_the_terminal_block_quotes_only_the_broken_rows(self) -> None:
        comparison = _comparison()
        lines = watch_row_lines(
            evaluate_watch_rows(
                parse_watch_rows("a=0,b=1"),
                diff_sites=comparison.diff_sites,
                compared_rows=len(TARGET),
            )
        )
        rendered = "\n".join(lines)
        self.assertIn("signature=.X", rendered)
        self.assertIn("[    1] b: register", rendered)
        self.assertNotIn("[    0]", rendered)


class CommandSurfaceTests(unittest.TestCase):
    """`compare-dumps --watch-rows`, the toolchain-free half of the surface."""

    def _run(self, **overrides: object) -> tuple[int, str]:
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            target = directory / "target.txt"
            candidate = directory / "candidate.txt"
            target.write_text(assemble(TARGET, symbol="demo"), encoding="utf-8")
            candidate.write_text(assemble(CANDIDATE, symbol="demo"), encoding="utf-8")
            fields: dict[str, object] = {
                "target": str(target),
                "candidate": str(candidate),
                "symbol": None,
                "census": [],
                "json": False,
                "cross_rom": False,
                "show_diff": False,
                "fail_on_mismatch": False,
                "by_region": None,
                "by_region_limit": 12,
                "color": "never",
                "watch_rows": "a=0,b=1,c=3",
            }
            fields.update(overrides)
            args = argparse.Namespace(**fields)
            stream = io.StringIO()
            with redirect_stdout(stream):
                status = compare_dumps_command(args)
            return status, stream.getvalue()

    def test_the_signature_prints_under_the_verdict(self) -> None:
        _status, output = self._run()
        self.assertIn("signature=.XX", output)

    def test_the_json_carries_the_array_and_the_signature(self) -> None:
        _status, output = self._run(json=True)
        payload = json.loads(output)
        self.assertEqual(payload["watch_signature"], ".XX")
        self.assertEqual(
            [entry["label"] for entry in payload["watch_rows"]], ["a", "b", "c"]
        )
        self.assertEqual(payload["watch_rows"][0]["healed"], True)
        self.assertEqual(payload["watch_rows"][1]["class"], "register")

    def test_a_bad_specification_exits_two_without_a_traceback(self) -> None:
        status, _output = self._run(watch_rows="not-a-row")
        self.assertEqual(status, 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
