"""Retained Ucode gives UGEN procedure ordinals names without machine-code inference."""

from __future__ import annotations

import unittest

from decomp_workbench.procedure_identity import procedure_names, select_procedure
from decomp_workbench.ucode import UcodeRecord


def record(index: int, name: str, words: tuple[int, ...]) -> UcodeRecord:
    return UcodeRecord(
        index=index,
        word_offset=index * 4,
        words=words,
        opcode=0,
        name=name,
        dtype=0,
        mtype=0,
        lexlev=0,
        base_word_length=len(words),
    )


def named_procedure(index: int, name: str) -> tuple[UcodeRecord, UcodeRecord]:
    payload = name.encode("ascii") + b"\0"
    payload += b"\0" * ((4 - len(payload) % 4) % 4)
    words = tuple(
        int.from_bytes(payload[offset : offset + 4], "big")
        for offset in range(0, len(payload), 4)
    )
    return (
        record(index, "ent", (0, 0)),
        record(index + 1, "comm", (0, 0, 0, 0, len(name) + 1, 0, *words)),
    )


class ProcedureIdentityTests(unittest.TestCase):
    def test_names_follow_uent_order(self) -> None:
        records = (*named_procedure(0, "first"), *named_procedure(2, "second"))
        self.assertEqual(procedure_names(records), ("first", "second"))

    def test_selection_requires_one_exact_name(self) -> None:
        report = {
            "procedures": [
                {"ordinal": 0, "name": "first"},
                {"ordinal": 1, "name": "second"},
            ]
        }
        self.assertEqual(select_procedure(report, "second"), 1)
        with self.assertRaisesRegex(ValueError, "0 procedures"):
            select_procedure(report, "missing")

    def test_missing_name_record_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "following name Ucomm"):
            procedure_names((record(0, "ent", (0, 0)),))


if __name__ == "__main__":
    unittest.main()
