"""The registry is the single source of metric names for humans and machines."""

from __future__ import annotations

import dataclasses
import unittest

from decomp_workbench.cli import CAMPAIGN_SUMMARY_KEYS, comparison_line
from decomp_workbench.compare import compare_instructions
from decomp_workbench.model import Comparison
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.schema import (
    DEPRECATED_KEYS,
    METRICS,
    METRICS_BY_KEY,
    explain_keys_text,
    selected_fields,
)

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
            "verdict=allocation-mismatch words=   2 raw=   2 norm=   1 "
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
        for metric in METRICS:
            with self.subTest(key=metric.key):
                self.assertIn(metric.key, text)
                self.assertIn(metric.description.split(";")[0][:40], text)
        self.assertIn("word_mismatches", text)


if __name__ == "__main__":
    unittest.main()
