"""The registry is the single source of metric names for humans and machines."""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import CAMPAIGN_SUMMARY_KEYS, comparison_line, main
from decomp_workbench.compare import compare_instructions
from decomp_workbench.model import Comparison
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.schema import (
    CAMPAIGN_METRICS,
    COMMAND_METRICS,
    COMPARISON_CENSUS_KEYS,
    DEPRECATED_KEYS,
    METRICS,
    METRICS_BY_KEY,
    VIEW_CENSUS_KEYS,
    VIEW_METRICS,
    VIEW_METRICS_BY_KEY,
    explain_keys_text,
    selected_fields,
)
from decomp_workbench.view import schema_keys

TARGET = """
00000000 <demo>:
   0: 27bdffe0  addiu $sp,$sp,-32
   4: 012a4021  addu $t0,$t1,$t2
   8: 03e00008  jr $ra
   c: 00000000  nop
"""

CANDIDATE = """
00000000 <demo>:
   0: 27bdffd0  addiu $sp,$sp,-48
   4: 012a5821  addu $t3,$t1,$t2
   8: 03e00008  jr $ra
   c: 00000000  nop
"""


def build_comparison() -> Comparison:
    return compare_instructions(
        parse_disassembly(TARGET, symbol="demo"),
        parse_disassembly(CANDIDATE, symbol="demo"),
        target_name="target.o",
        candidate_name="candidate.o",
        symbol="demo",
    )


class SchemaTests(unittest.TestCase):
    def test_every_comparison_field_is_registered(self) -> None:
        registered = {metric.attribute for metric in METRICS}
        fields = {item.name for item in dataclasses.fields(Comparison)}
        self.assertEqual(fields - registered, set())

    def test_keys_and_attributes_are_unique(self) -> None:
        keys = [metric.key for metric in METRICS]
        attributes = [metric.attribute for metric in METRICS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(attributes), len(set(attributes)))
        self.assertEqual(set(keys) & set(DEPRECATED_KEYS), set())

    def test_every_printed_label_resolves_to_a_registry_key(self) -> None:
        comparison = build_comparison()
        line = comparison_line(comparison)
        labels = [
            field.split("=", 1)[0]
            for field in line.split(" ")
            if "=" in field and not field.startswith("-")
        ]
        self.assertEqual(labels, [metric.key for metric in METRICS if metric.summary])
        for label in labels:
            self.assertIn(label, METRICS_BY_KEY)

    def test_summary_line_keeps_its_documented_shape(self) -> None:
        comparison = build_comparison()
        self.assertEqual(
            comparison_line(comparison),
            "verdict=allocation-mismatch aligned_total=   2 words=   2 "
            "raw=   2 norm=   1 "
            "regs=   1 fp=   0 insns=   4 frame=  -48 "
            f"sha1={comparison.candidate_sha1} candidate.o",
        )

    def test_json_carries_the_canonical_key_and_the_deprecated_alias(self) -> None:
        payload = build_comparison().as_dict()
        for alias, key in DEPRECATED_KEYS.items():
            with self.subTest(key=key):
                self.assertIn(key, payload)
                self.assertIn(alias, payload)
                self.assertEqual(payload[key], payload[alias])

    def test_human_and_json_values_cannot_diverge(self) -> None:
        comparison = build_comparison()
        payload = comparison.as_dict()
        for metric in METRICS:
            if not metric.summary:
                continue
            with self.subTest(key=metric.key):
                self.assertEqual(
                    metric.render(payload[metric.key]).strip(),
                    metric.render(getattr(comparison, metric.attribute)).strip(),
                )

    def test_selected_fields_emit_both_spellings(self) -> None:
        payload = selected_fields(build_comparison(), CAMPAIGN_SUMMARY_KEYS)
        self.assertEqual(payload["words"], payload["word_mismatches"])
        self.assertEqual(payload["insns"], payload["candidate_instructions"])
        self.assertIn("verdict", payload)
        self.assertNotIn("diff_sites", payload)

    def test_explain_keys_lists_every_metric(self) -> None:
        text = explain_keys_text()
        for metric in (*METRICS, *CAMPAIGN_METRICS, *VIEW_METRICS, *COMMAND_METRICS):
            with self.subTest(key=metric.key):
                self.assertIn(metric.key, text)
                self.assertIn(metric.description.split(";")[0][:40], text)
        self.assertIn("word_mismatches", text)
        self.assertIn("Campaign report keys", text)
        self.assertIn("Aligned mechanism view keys", text)
        self.assertIn("Command result keys", text)

    def test_census_accepts_exactly_the_keys_a_command_reports(self) -> None:
        """A predicate may name any reported key, and nothing else.

        Both directions matter: a key the report carries but the census refuses
        sends the reader back to a JSON parser, and a key the census accepts but
        the report never carries would answer every question with `None`.
        """

        self.assertEqual(
            set(COMPARISON_CENSUS_KEYS),
            {metric.key for metric in METRICS} | set(DEPRECATED_KEYS),
        )
        self.assertEqual(set(VIEW_CENSUS_KEYS), {metric.key for metric in VIEW_METRICS})
        payload = build_comparison().as_dict()
        for spelling, key in COMPARISON_CENSUS_KEYS.items():
            with self.subTest(key=spelling):
                self.assertIn(key, payload)

    def test_the_view_registry_is_the_view_vocabulary(self) -> None:
        """One registry, and the view reads its keys from it, not a copy."""

        self.assertEqual(schema_keys(), frozenset(VIEW_METRICS_BY_KEY))
        keys = [metric.key for metric in VIEW_METRICS]
        self.assertEqual(len(keys), len(set(keys)))
        for metric in VIEW_METRICS:
            with self.subTest(key=metric.key):
                # The view shipped with label == key from the start, so it has
                # no compatibility spellings to carry.
                self.assertEqual(metric.key, metric.attribute)
                self.assertEqual(metric.deprecated_keys, ())

    def test_the_two_registries_keep_separate_namespaces(self) -> None:
        """A shared spelling is a different number, so the lookups stay apart.

        ``target_instructions`` is a deprecated comparison key and a canonical
        view key. Merging the lookups would silently give one of them the
        other's meaning.
        """

        shared = frozenset(VIEW_METRICS_BY_KEY) & frozenset(METRICS_BY_KEY)
        self.assertIn("verdict", shared)
        self.assertEqual(
            METRICS_BY_KEY["target_insns"].attribute, "target_instructions"
        )
        self.assertEqual(DEPRECATED_KEYS["target_instructions"], "target_insns")
        self.assertNotIn("target_instructions", METRICS_BY_KEY)
        self.assertIn("target_instructions", VIEW_METRICS_BY_KEY)

    def test_campaign_report_keys_are_all_registered(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "target.o").write_bytes(b"target")
            source = root / "candidate.c"
            source.write_text("int candidate;\n", encoding="utf-8")
            compiler = root / "compile.py"
            compiler.write_text(
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[2]).write_bytes(b'object')\n",
                encoding="utf-8",
            )
            objdump = root / "objdump"
            objdump.write_text(
                "#!/usr/bin/env python3\n"
                "print('00000000 <demo>:')\n"
                "print('   0: 03e00008  jr $ra')\n"
                "print('   4: 00000000  nop')\n",
                encoding="utf-8",
            )
            objdump.chmod(0o755)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(
                    [
                        "campaign",
                        str(root / "target.o"),
                        str(source),
                        "--symbol",
                        "demo",
                        "--objdump",
                        str(objdump),
                        "--compile-command",
                        f"{sys.executable} {compiler} {{source}} {{output}}",
                        "--cache-dir",
                        str(root / "cache"),
                        "--no-ledger",
                        "--json-summary",
                    ]
                )
        self.assertEqual(status, 0)
        payload = json.loads(stdout.getvalue())
        registered = {metric.key for metric in CAMPAIGN_METRICS}
        self.assertEqual(set(payload) - registered, set())


if __name__ == "__main__":
    unittest.main()
