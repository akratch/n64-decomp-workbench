"""Address-equivalent relocation spellings are linker evidence, not fake C."""

from __future__ import annotations

import unittest

from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.relocation_alias import relocation_alias_report

TARGET = """
0: 3c010000  lui $at,0
                  0: R_MIPS_HI16 next_symbol
"""

CANDIDATE = """
0: 3c010000  lui $at,0
                  0: R_MIPS_HI16 array+0x20
"""


class RelocationAliasTests(unittest.TestCase):
    def test_same_linked_address_is_reported_without_claiming_exactness(self) -> None:
        report = relocation_alias_report(
            parse_disassembly(TARGET),
            parse_disassembly(CANDIDATE),
            symbols={"next_symbol": 0x80400020, "array": 0x80400000},
        )
        self.assertEqual(report["alias_count"], 1)
        alias = report["resolved_address_aliases"][0]
        self.assertEqual(alias["resolved_address"], 0x80400020)
        self.assertIn("link or ROM check", report["proof"])

    def test_unknown_symbol_stays_unresolved(self) -> None:
        report = relocation_alias_report(
            parse_disassembly(TARGET),
            parse_disassembly(CANDIDATE),
            symbols={"array": 0x80400000},
        )
        self.assertEqual(report["alias_count"], 0)
        self.assertEqual(len(report["unresolved_spelling_differences"]), 1)

    def test_kind_and_cardinality_differences_are_never_hidden(self) -> None:
        different_kind = CANDIDATE.replace("R_MIPS_HI16", "R_MIPS_LO16")
        report = relocation_alias_report(
            parse_disassembly(TARGET),
            parse_disassembly(different_kind),
            symbols={"next_symbol": 0x80400020, "array": 0x80400000},
        )
        self.assertEqual(report["alias_count"], 0)
        self.assertEqual(len(report["unresolved_spelling_differences"]), 1)

        missing = relocation_alias_report(
            parse_disassembly(TARGET),
            parse_disassembly("0: 3c010000  lui $at,0\n"),
            symbols={"next_symbol": 0x80400020},
        )
        self.assertEqual(len(missing["unresolved_spelling_differences"]), 1)
        self.assertIsNone(missing["unresolved_spelling_differences"][0]["candidate"])


if __name__ == "__main__":
    unittest.main()
