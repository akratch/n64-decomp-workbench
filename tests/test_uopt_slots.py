"""Synthetic producer events: no compiler binaries or game output fixtures."""

from __future__ import annotations

import unittest

from decomp_workbench.uopt_slots import (
    CALLER_RETURNS,
    MARKER,
    PATCHES,
    instrument_uopt_slots,
    parse_slot_trace,
)

SOURCE = '#include "header.h"\n' + "".join(old for _, old, _ in PATCHES)
SOURCE += "".join(
    f"f_gettemp(mem, sp, a0, a1);\ngoto {label};\n" for label in CALLER_RETURNS
)
TRACE = (
    "compiler diagnostics may coexist\n"
    "DKWB-SLOT event=procedure proc=0\n"
    "DKWB-SLOT event=request proc=0 request=1 path=spill owner=0x10001000 "
    "size=4 index=7 reserve=32 caller=spilltemps raw_kind=4 raw_dtype=6 "
    "raw_sym=7 raw16=0 raw20=0 raw24=0 raw28=0\n"
    "DKWB-SLOT event=chosen proc=0 request=1 slot=0x10002000 index=0 "
    "offset=-36 size=4 reused=0 before=32 after=36\n"
    "DKWB-SLOT event=home proc=0 opcode=112 mtype=1 block=3 length=4 "
    "offset=-16 before=0 after=16\n"
    "DKWB-SLOT event=udef proc=0 block=3 size=16\n"
)


class UoptSlotInstrumentationTests(unittest.TestCase):
    def test_refuses_unknown_profile(self) -> None:
        with self.assertRaisesRegex(ValueError, "not a pinned"):
            instrument_uopt_slots(SOURCE)

    def test_exact_anchors_and_duplicate_guard(self) -> None:
        result = instrument_uopt_slots(SOURCE, allow_unverified_source=True)
        self.assertIn(MARKER, result.source)
        self.assertIn("DKWB_UOPT_SLOT_TRACE", result.source)
        self.assertIn("dkwb_home_before", result.source)
        self.assertIn("event=rlda", result.source)
        with self.assertRaisesRegex(ValueError, "already instrumented"):
            instrument_uopt_slots(result.source, allow_unverified_source=True)

    def test_every_missing_or_duplicate_anchor_refuses(self) -> None:
        for label, old, _ in PATCHES:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "slot anchor"):
                    instrument_uopt_slots(
                        SOURCE.replace(old, ""), allow_unverified_source=True
                    )
                with self.assertRaisesRegex(ValueError, "slot anchor"):
                    instrument_uopt_slots(SOURCE + old, allow_unverified_source=True)

    def test_missing_caller_refuses(self) -> None:
        with self.assertRaisesRegex(ValueError, "L430350"):
            instrument_uopt_slots(
                SOURCE.replace("goto L430350;", ""), allow_unverified_source=True
            )


class UoptSlotParserTests(unittest.TestCase):
    def test_reserve_is_distinct_from_emitted_demand(self) -> None:
        report = parse_slot_trace(TRACE)
        self.assertEqual(report["allocation_requests"], 1)
        self.assertEqual(report["procedures"], 1)
        events = report["events"]
        assert isinstance(events, list)
        self.assertEqual(events[2]["after"], 36)
        self.assertEqual(events[-1]["size"], 16)
        self.assertIn("Neither slot offsets", str(report["claim_boundary"]))

    def test_multiple_procedures_and_no_allocation(self) -> None:
        result = parse_slot_trace(
            TRACE + "DKWB-SLOT event=procedure proc=1\n"
            "DKWB-SLOT event=udef proc=1 block=4 size=0\n"
        )
        self.assertEqual(result["procedures"], 2)

    def test_reuse_keeps_region(self) -> None:
        trace = TRACE.replace(
            "reused=0 before=32 after=36", "reused=1 before=32 after=32"
        )
        self.assertEqual(parse_slot_trace(trace)["allocation_requests"], 1)
        with self.assertRaisesRegex(ValueError, "reused slot grows"):
            parse_slot_trace(TRACE.replace("reused=0", "reused=1"))

    def test_candidate_decisions_are_not_reuse_claims(self) -> None:
        candidate = (
            "DKWB-SLOT event=candidate proc=0 request=1 reason=size "
            "index=0 available=0 size=8\n"
        )
        trace = TRACE.replace(
            "DKWB-SLOT event=chosen", candidate + "DKWB-SLOT event=chosen"
        )
        self.assertEqual(parse_slot_trace(trace)["allocation_requests"], 1)
        with self.assertRaisesRegex(ValueError, "invalid candidate decision"):
            parse_slot_trace(trace.replace("reason=size", "reason=guessed"))

    def test_request_pairing_and_size_are_required(self) -> None:
        for bad in (
            TRACE.replace(
                "event=chosen proc=0 request=1", "event=chosen proc=0 request=2"
            ),
            TRACE.replace("offset=-36 size=4", "offset=-36 size=8"),
            TRACE.replace("before=32 after=36", "before=28 after=36"),
            "\n".join(
                line for line in TRACE.splitlines() if "event=chosen" not in line
            ),
        ):
            with self.subTest(trace=bad), self.assertRaises(ValueError):
                parse_slot_trace(bad)

    def test_unknown_duplicate_and_truncated_events_refuse(self) -> None:
        for bad in (
            TRACE + "DKWB-SLOT event=surprise proc=0\n",
            TRACE.replace("event=udef proc=0", "event=udef proc=0 proc=0"),
            TRACE.replace(" block=3 size=16", ""),
            "\n".join(line for line in TRACE.splitlines() if "event=udef" not in line),
            TRACE.replace("event=procedure proc=0", "event=procedure proc=2"),
            "",
        ):
            with self.subTest(trace=bad), self.assertRaises(ValueError):
                parse_slot_trace(bad)

    def test_impossible_home_opcode_and_memory_type_refuse(self) -> None:
        for bad in (
            TRACE.replace("opcode=112", "opcode=0"),
            TRACE.replace("mtype=1", "mtype=-1"),
            TRACE.replace("mtype=1", "mtype=8"),
        ):
            with (
                self.subTest(trace=bad),
                self.assertRaisesRegex(ValueError, "register-home"),
            ):
                parse_slot_trace(bad)

    def test_nonpositive_request_ids_refuse(self) -> None:
        for value in ("0", "-1"):
            with (
                self.subTest(value=value),
                self.assertRaisesRegex(ValueError, "positive"),
            ):
                parse_slot_trace(TRACE.replace("request=1", "request=" + value))

    def test_return_to_prior_procedure_refuses(self) -> None:
        with self.assertRaisesRegex(ValueError, "earlier procedure"):
            parse_slot_trace(
                TRACE + "DKWB-SLOT event=procedure proc=1\n"
                "DKWB-SLOT event=udef proc=0 block=3 size=16\n"
                "DKWB-SLOT event=udef proc=1 block=4 size=0\n"
            )

    def test_rlda_layout_is_not_home_length(self) -> None:
        event = (
            "DKWB-SLOT event=rlda proc=0 mtype=2 block=9 color_offset=16 "
            "address_offset=24 descriptor=0x10001000 color=17 "
            "raw_kind=1 raw_dtype=0 raw_sym=6\n"
        )
        result = parse_slot_trace(
            TRACE.replace("DKWB-SLOT event=udef", event + "DKWB-SLOT event=udef")
        )
        events = result["events"]
        assert isinstance(events, list)
        rlda = next(row for row in events if row["event"] == "rlda")
        self.assertEqual(rlda["color_offset"], 16)
        self.assertNotIn("length", rlda)


if __name__ == "__main__":
    unittest.main()
