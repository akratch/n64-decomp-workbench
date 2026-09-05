"""Synthetic structural regressions; no game objects or instruction payloads."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

from mips_asm import assemble

from decomp_workbench.campaign import sort_campaign_results_key
from decomp_workbench.campaign_state import (
    _effective_rank_by,
    _record_key,
    _retention_leaders,
)
from decomp_workbench.cli import main
from decomp_workbench.compare import compare_instructions, rank_comparisons
from decomp_workbench.comparison_render import comparison_line
from decomp_workbench.geometry import geometry_vector, pareto_layers
from decomp_workbench.headline import build_headline, render_headline
from decomp_workbench.model import Comparison, CompileResult
from decomp_workbench.objdump import parse_disassembly


def streams(rows: int = 1208) -> tuple[list[str], list[str], list[str]]:
    body = [f"addiu v0,v0,{index}" for index in range(rows - 2)]
    tail = ["jr ra", "nop"]
    # Seven early insertions shift almost every positional comparison. Nine
    # late insertions damage fewer positions despite a strictly worse extent.
    return body + tail, ["nop"] * 7 + body + tail, body + ["nop"] * 9 + tail


def compare(target: list[str], candidate: list[str], name: str) -> Comparison:
    return compare_instructions(
        parse_disassembly(assemble(target, symbol="demo"), symbol="demo"),
        parse_disassembly(assemble(candidate, symbol="demo"), symbol="demo"),
        target_name="target.o",
        candidate_name=name,
        symbol="demo",
    )


def result(item: Comparison) -> CompileResult:
    return CompileResult(item.candidate + ".c", [], 0, "", "", None, item)


class GeometryRankingTests(unittest.TestCase):
    def test_1208_target_does_not_reward_1215_to_1217_positional_decrease(self) -> None:
        target, near, worse = streams()
        first, second = compare(target, near, "near"), compare(target, worse, "worse")
        self.assertEqual(first.target_true_instructions, 1208)
        self.assertEqual(first.candidate_true_instructions, 1215)
        self.assertEqual(second.candidate_true_instructions, 1217)
        self.assertLess(second.word_mismatches, first.word_mismatches)
        ordered, unsafe = rank_comparisons([second, first])
        self.assertTrue(unsafe)
        self.assertEqual([item.candidate for item in ordered], ["near", "worse"])
        self.assertEqual([item.geometry_front for item in ordered], [0, 1])
        self.assertFalse(any(item.exact for item in ordered))
        self.assertIn("true_insn_delta=+9", comparison_line(second))
        self.assertIn("geometry_front=1", comparison_line(second))
        headline = build_headline(second)
        self.assertEqual(headline.words, second.word_mismatches)
        self.assertEqual(headline.as_dict()["geometry"], second.geometry)
        self.assertIn("extent=+9", "\n".join(render_headline(headline)))

    def test_tradeoffs_share_a_front_instead_of_asserting_size_first(self) -> None:
        self.assertEqual(pareto_layers([(7, 100, 20), (9, 50, 10)]), [0, 0])
        self.assertEqual(pareto_layers([(0, 0, 0), (0, 0, 0), (1, 1, 1)]), [0, 0, 1])
        self.assertEqual(pareto_layers([(3, 3, 3), (1, 1, 1), (2, 2, 2)]), [2, 0, 1])

    def test_true_extent_cannot_be_replaced_by_equal_padded_counts(self) -> None:
        target, near, worse = streams(20)
        first, second = compare(target, near, "near"), compare(target, worse, "worse")
        # Model a loader that compares equal padded sections but has measured
        # distinct true extents. Ranking must use the independent true count.
        first.instruction_delta = second.instruction_delta = 0
        self.assertEqual(first.geometry_vector[0], 7)
        self.assertEqual(second.geometry_vector[0], 9)
        self.assertEqual(rank_comparisons([second, first])[0][0].candidate, "near")

    def test_live_and_persisted_ranking_agree_and_words_override_survives(self) -> None:
        target, near, worse = streams(20)
        results = [
            result(compare(target, source, name))
            for source, name in ((worse, "worse"), (near, "near"))
        ]
        ordered = sorted(results, key=sort_campaign_results_key(results))
        self.assertEqual(ordered[0].source, "near.c")
        records = [item.as_dict() for item in results]
        for record in records:
            record["comparison"]["geometry_front"] = 999  # stale persisted cohort
        ranked_by, unsafe = _effective_rank_by(records, requested="auto")
        self.assertEqual(ranked_by, "geometry-pareto")
        self.assertTrue(unsafe)
        resumed = sorted(
            records, key=lambda item: _record_key(item, ranked_by=ranked_by)
        )
        self.assertEqual(resumed[0]["source"], ordered[0].source)
        self.assertEqual(resumed[0]["comparison"]["geometry_front"], 0)
        explicit = sorted(
            results, key=sort_campaign_results_key(results, rank_by="words")
        )
        self.assertEqual(explicit[0].source, "worse.c")
        self.assertTrue(
            all(
                item.comparison and item.comparison.geometry_front is None
                for item in results
            )
        )

    def test_source_retention_keeps_every_nondominated_tradeoff(self) -> None:
        records: list[dict[str, Any]] = []
        for index, (extent, edit, opcodes, words) in enumerate(
            [(7, 100, 20, 10), (9, 50, 10, 30), (10, 100, 20, 1)]
        ):
            records.append(
                {
                    "source": f"{index}.c",
                    "cache_key": str(index),
                    "comparison": {
                        "alignment_comparable": False,
                        "true_instruction_delta": extent,
                        "normalized_distance": edit,
                        "opcode_distance": opcodes,
                        "words": words,
                    },
                }
            )
        ranked_by, _ = _effective_rank_by(records, requested="auto")
        self.assertEqual(_retention_leaders(records, ranked_by=ranked_by), {"0", "1"})

    def test_incomplete_legacy_evidence_falls_back_without_inventing_geometry(
        self,
    ) -> None:
        incomplete = {"alignment_comparable": False, "words": 10}
        self.assertIsNone(geometry_vector(incomplete))
        self.assertEqual(
            _effective_rank_by([{"comparison": incomplete}], requested="auto"),
            ("words", True),
        )
        self.assertEqual(
            geometry_vector({"true_insn_delta": -3, "norm": 7, "opcode_distance": 5}),
            (3, 7, 5),
        )

    def test_cli_campaign_and_resumed_status_choose_same_structural_leader(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target, near, worse = streams(20)
            for name, source in (
                ("target.o", target),
                ("near.c", near),
                ("worse.c", worse),
            ):
                (root / name).write_text(
                    assemble(source, symbol="demo"), encoding="utf-8"
                )
            compiler = root / "compile.py"
            compiler.write_text(
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[2]).write_bytes(pathlib.Path(sys.argv[1]).read_bytes())\n",
                encoding="utf-8",
            )
            objdump = root / "objdump"
            objdump.write_text(
                "#!/usr/bin/env python3\nimport pathlib, sys\n"
                "print(next(pathlib.Path(arg).read_text() for arg in sys.argv[1:] "
                "if not arg.startswith('-') and pathlib.Path(arg).is_file()))\n",
                encoding="utf-8",
            )
            objdump.chmod(0o755)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    [
                        "campaign",
                        str(root / "target.o"),
                        str(root / "worse.c"),
                        str(root / "near.c"),
                        "--compile-command",
                        f"{sys.executable} {compiler} {{source}} {{output}}",
                        "--objdump",
                        str(objdump),
                        "--symbol",
                        "demo",
                        "--cache-dir",
                        str(root / "cache"),
                        "--state-dir",
                        str(root / "state"),
                        "--json-summary",
                    ]
                )
            self.assertEqual(code, 0, output.getvalue())
            live = json.loads(output.getvalue())
            self.assertEqual(live["ranked_by"], "geometry-pareto")
            self.assertTrue(live["results"][0]["source"].endswith("near.c"))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main(
                    ["campaign", "status", str(Path(live["manifest"]).parent), "--json"]
                )
            self.assertEqual(code, 0)
            resumed = json.loads(output.getvalue())
            self.assertEqual(resumed["ranked_by"], "geometry-pareto")
            self.assertEqual(resumed["best"]["source"], live["results"][0]["source"])


if __name__ == "__main__":
    unittest.main()
