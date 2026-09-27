"""Invented compiler metadata and original C, never game/compiler payloads."""

from __future__ import annotations

import hashlib
import struct
import unittest
from unittest.mock import patch

from decomp_workbench.instrument_ugen_owners import (
    MARKER,
    UGEN_SHA256,
    _function,
    _replace,
    instrument_ugen_owners,
)
from decomp_workbench.ugen_owners import (
    external_dense_symbols,
    owner_report,
    parse_owner_trace,
)

# Same draw/register counts, different owners. Used as a real compiler control.
EQUAL_DRAW_C = """extern int first, second;
extern void sink(int *, int *);
void left(void) { sink(&first, &second); }
void right(void) { sink(&second, &first); }
"""


def trace(symbol: int = 1, reg: int = 16) -> str:
    words = [0x6B800000, symbol, reg, 0, 0, 0, 0, 0]
    fields = " ".join(f"w{i}={word}" for i, word in enumerate(words))
    records = [
        f"READ ptr=128 node=0 id=0 {fields}",
        "NEW node=4096 id=1",
        f"INPUT ptr=128 node=4096 id=1 {fields}",
        f"BUILD ptr=4128 node=4096 id=1 {fields}",
        f"DEST node=4096 id=1 hint={reg} reg={reg} node_reg={reg}",
        f"EMIT site=f_eval-1 node=4096 id=1 epoch=1 emit=1 op=36 reg={reg} "
        f"symbol={symbol} addend=0 extra=0 node_op=71 "
        f"node_symbol={symbol} node_addend=0 node_reg={reg}",
        "OUTPUT epoch=1 forward=1 backward=0",
        "OUTPUT epoch=2 forward=0 backward=1",
        "CONCAT",
    ]
    return f"DKWB-OWNER-PROFILE version=1 source_sha256={UGEN_SHA256}\n" + "".join(
        f"DKWB-OWNER-{row.split()[0]} serial={index} {row.partition(' ')[2]}\n"
        for index, row in enumerate(records, 1)
    )


def ucode(symbol: int = 1, reg: int = 16) -> bytes:
    return struct.pack(">4I", 0x6B800000, symbol, reg, 0)


def binasm(symbol: int = 1, reg: int = 16) -> bytes:
    return b"\0" * 16 + struct.pack(">4I", symbol, 0x170048, (reg << 25) | 0x1204000, 0)


def symbols() -> bytes:
    header = [0] * 25
    header[0] = 0x7009
    header[5:7] = [2, 96]
    header[17:19] = [9, 128]
    header[23:25] = [1, 112]
    return (
        struct.pack(">HH23I", *header)
        + struct.pack(">4I", 0, 0, 0x7FFFFFFF, 0)
        + struct.pack(">4I", 0, 0, 0, 0)
        + b"external\0"
    )


class OwnerReaderTests(unittest.TestCase):
    def test_exact_input_node_destination_and_output_join(self) -> None:
        row = owner_report(trace(), ucode=ucode(), binasm=binasm(), symbols=symbols())[
            "emissions"
        ][0]
        self.assertEqual(row["input"]["read_index"], 0)
        self.assertEqual(row["input"]["ucode_word_offset"], 0)
        self.assertEqual(row["input"]["opcode"], "rlda")
        self.assertEqual(row["input"]["retained_operand_verification"], "full")
        self.assertEqual(row["generation"], 2)
        self.assertEqual(row["input_assigned_register"], 16)
        self.assertEqual(row["get_dest"]["hint"], 16)
        self.assertEqual(row["binasm_record"], 1)
        self.assertEqual(row["symbol_name"], "external")

    def test_equal_draws_do_not_equate_owner(self) -> None:
        a = owner_report(trace(1), ucode=ucode(1), binasm=binasm(1))
        b = owner_report(trace(2), ucode=ucode(2), binasm=binasm(2))
        self.assertEqual(a["emission_count"], b["emission_count"])
        self.assertEqual(a["emissions"][0]["reg"], b["emissions"][0]["reg"])
        self.assertNotEqual(a["emissions"][0]["symbol"], b["emissions"][0]["symbol"])

    def test_optional_artifacts_never_create_offsets_or_names(self) -> None:
        row = owner_report(trace())["emissions"][0]
        self.assertIsNone(row["binasm_record"])
        self.assertIsNone(row["symbol_name"])
        self.assertIsNone(row["input"]["ucode_word_offset"])

    def test_mutated_input_is_unresolved_not_equal_pointer_identity(self) -> None:
        value = trace().replace(
            "READ serial=1 ptr=128 node=0 id=0 w0=1803550720 w1=1",
            "READ serial=1 ptr=128 node=0 id=0 w0=1803550720 w1=2",
        )
        row = owner_report(value)["emissions"][0]
        self.assertIn("unresolved", row["input"]["status"])
        self.assertIsNone(row["input"]["read_index"])

    def test_profile_corruption_and_missing_events_refuse(self) -> None:
        for value in [
            trace().replace(UGEN_SHA256, "0" * 64),
            trace().replace("serial=2", "serial=3"),
            trace().replace(" reg=16", " reg=-1"),
            trace().replace("site=f_eval-1", "site=unknown"),
            trace().replace("DKWB-OWNER-EMIT", "junk DKWB-OWNER-EMIT"),
            trace().replace("id=1 epoch=1", "id=2 epoch=1"),
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_owner_trace(value) if "id=2 epoch" not in value else owner_report(
                    value
                )

    def test_conflicting_copy_or_destination_refuse(self) -> None:
        for value in [
            trace().replace("BUILD serial=4 ptr=4128", "BUILD serial=4 ptr=4129"),
            trace().replace("hint=16 reg=16 node_reg=16", "hint=16 reg=16 node_reg=17"),
        ]:
            with self.assertRaises(ValueError):
                owner_report(value)

    def test_stale_retained_inputs_and_output_refuse(self) -> None:
        for kwargs in [
            {"ucode": ucode(2)},
            {"ucode": ucode(1, 17)},
            {"ucode": ucode() * 2},
            {"binasm": binasm(2)},
            {"binasm": binasm() + b"\0" * 16},
        ]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                owner_report(trace(), **kwargs)

    def test_use_before_pending_build_refuses_even_with_later_build(self) -> None:
        for position in (5, 6):
            rows = trace().splitlines()
            build = rows.pop(4)
            rows.insert(position, build)
            import re

            rows = [rows[0]] + [
                re.sub(r"serial=\d+", f"serial={i}", row)
                for i, row in enumerate(rows[1:], 1)
            ]
            with self.assertRaisesRegex(ValueError, "before pending tree copy"):
                owner_report("\n".join(rows) + "\n")

    def test_retained_addend_tampering_refuses(self) -> None:
        with self.assertRaisesRegex(ValueError, "retained rlda operands"):
            owner_report(trace(), ucode=ucode()[:-4] + struct.pack(">I", 4))

    def test_retained_operand_verification_is_explicit(self) -> None:
        row = owner_report(trace())["emissions"][0]
        self.assertEqual(row["input"]["retained_operand_verification"], "not-supplied")
        # An ordinary address record has no authenticated full serialization join here.
        value = trace().replace("w0=1803550720", "w0=1199570944")
        row = owner_report(value, ucode=struct.pack(">6I", 0x47800000, 1, 16, 0, 0, 0))[
            "emissions"
        ][0]
        self.assertEqual(row["input"]["retained_operand_verification"], "prefix-only")

    def test_output_boundary_required_when_binasm_is_supplied(self) -> None:
        value = "\n".join(trace().splitlines()[:-1]) + "\n"
        with self.assertRaises(ValueError):
            owner_report(value, binasm=binasm())

    def test_empty_trace_is_not_match_evidence(self) -> None:
        self.assertEqual(owner_report("other diagnostics")["emission_count"], 0)
        with self.assertRaises(ValueError):
            owner_report("", binasm=binasm())

    def test_dense_symbol_bounds_and_magic_refuse(self) -> None:
        self.assertEqual(external_dense_symbols(symbols()), {1: "external"})
        for value in [
            b"",
            b"xx" + symbols()[2:],
            symbols()[:-1],
            symbols()[:112] + struct.pack(">4I", 0, 99, 0, 0) + symbols()[128:],
        ]:
            with self.assertRaises(ValueError):
                external_dense_symbols(value)


class OwnerInstrumentationTests(unittest.TestCase):
    def test_source_pin_and_duplicate_marker_refuse(self) -> None:
        for value in ["invented", MARKER]:
            with self.assertRaises(ValueError):
                instrument_ugen_owners(value)

    def test_missing_and_duplicate_anchors_refuse(self) -> None:
        for value in ["", "anchor anchor"]:
            with self.assertRaises(ValueError):
                _replace(value, "anchor", "new")
        for value in ["", "static void fake(int a0) {\n}\n" * 2]:
            with self.assertRaises(ValueError):
                _function(value, "fake")

    def test_full_synthetic_profile_does_not_replace_emissions(self) -> None:
        def function(name: str, body: str) -> str:
            return f"static uint32_t {name}(uint32_t a0) {{\n{body}\n}}\n"

        call = "f_emit_ra(mem, sp, a0, a1, a2, a3);\n"
        source = (
            '#include "header.h"\n'
            + function("f_loadstore", call * 3)
            + function("f_eval_mov", call * 2)
            + function("f_eval", call * 2)
        )
        for name in ["f_readuinstr", "f_build_u", "f_new_tree", "f_get_dest"]:
            source += function(name, "return v0;")
        for name in [
            "f_build_tree",
            "f_clear_ibuffer",
            "f_output_inst_bin",
            "f_cat_files",
        ]:
            source += function(name, "return 0;")
        with patch(
            "decomp_workbench.instrument_ugen_owners.UGEN_SHA256",
            hashlib.sha256(source.encode()).hexdigest(),
        ):
            output = instrument_ugen_owners(source)
        self.assertEqual(output.count(call), 7)
        self.assertIn("DKWB-OWNER-DEST", output)
        self.assertIn("DKWB-OWNER-CONCAT", output)
        self.assertIn("DKWB_UGEN_OWNERS", output)
        broken = source.replace(call, "", 1)
        with (
            patch(
                "decomp_workbench.instrument_ugen_owners.UGEN_SHA256",
                hashlib.sha256(broken.encode()).hexdigest(),
            ),
            self.assertRaises(ValueError),
        ):
            instrument_ugen_owners(broken)


if __name__ == "__main__":
    unittest.main()
