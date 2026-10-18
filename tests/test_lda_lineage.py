"""Synthetic source/input receipts; no proprietary compiler payloads."""

import unittest
from typing import Any

from phase_streams import uword
from test_cfe_source import source_fixture

from decomp_workbench.cfe_source import (
    SOURCE_SHA256 as CFE_SHA,
)
from decomp_workbench.cfe_source import _instrument_occurrences, join_occurrences
from decomp_workbench.lda_lineage import (
    SOURCE_SHA256,
    _instrument,
    instrument,
    join_trace,
)
from decomp_workbench.ucode import OPCODE_NAMES

WORDS = ((OPCODE_NAMES.index("lda") << 24) | (3 << 21) | (6 << 16), 7, 4, 0, 0, 0)
STREAM = uword(*WORDS, *WORDS)


def frontend() -> str:
    t = f"DKWB-CFE profile=1 source_sha256={CFE_SHA}\nDKWB-CFE-OCC capability=1\n"
    for i in range(1, 3):
        t += f"DKWB-CFE-OCC node={i} ptr={100 * i} node_id={i} tag=65\n"
        t += f"DKWB-CFE-OCC begin={i} ptr={100 * i} node_id={i} offset={24 * (i - 1)}\n"
        t += (
            f"DKWB-CFE begin={i} op=load_addr offset={24 * (i - 1)} "
            f"decl={1000 * i} raw36=0 raw44=1 raw60=7 "
            "namehex=74656d706c617465 truncated=0\n"
        )
        t += f"DKWB-CFE end={i} offset={24 * i}\nDKWB-CFE-OCC end={i} offset={24 * i}\n"
    return (
        t + "DKWB-CFE written=48\nDKWB-CFE-OCC output=0 datahex=" + STREAM.hex() + "\n"
    )


def words(kind: str, read: int) -> str:
    return (
        f"DKWB-LDA kind={kind} read={read} "
        + " ".join(f"w{i}={v}" for i, v in enumerate((*WORDS, 0, 0)))
        + "\n"
    )


def construct(read: int, ptr: int = 500) -> str:
    return (
        f"DKWB-LDA construct={read} current={read} depth=1 ptr={ptr} kind=5 "
        + " ".join(f"w{i}={v}" for i, v in enumerate((*WORDS, 0, 0)))
        + "\n"
    )


def backend() -> str:
    t = (
        f"DKWB-LDA capability=1 source_sha256={SOURCE_SHA256}\n"
        "DKWB-LDA pass=1\nDKWB-LDA alloc=1 ptr=500\n"
    )
    for n in range(1, 3):
        t += f"DKWB-LDA peek_result=0 pass=1 offset={6 * (n - 1)}\n"
        for i, v in enumerate(WORDS, start=6 * (n - 1) + 1):
            t += f"DKWB-LDA word={i} pass=1 value={v}\n"
        t += f"DKWB-LDA record={n} pass=1 start={6 * (n - 1)} end={6 * n}\n"
        t += words("READ", n) + words("GETOP", n) + construct(n)
    return t


def report(trace: str = "", cfe: str = "") -> dict[str, Any]:
    return join_trace(trace or backend(), STREAM, cfe_trace=cfe or frontend())


def uopt_fixture() -> str:
    anchors = {
        "f_ugetinit": "return;",
        "f_ugetint": "return v0;",
        "f_ugeteof": "return v0;",
        "f_readuinstr": "return;",
        "f_getop": "return;",
        "f_readnxtinst": "func_43e3a8(mem, sp, a0);\ngoto L441664;\nreturn;",
        "f_appendchain": "MEM_U16(v1 + 8) = (uint16_t)t0;\nL4855f8:\nreturn v0;",
        "f_delentry": "MEM_U8(a0 + 0) = (uint8_t)t8;\nreturn;",
    }
    return '#include "header.h"\n' + "".join(
        f"static uint32_t {n}(uint8_t *mem) {{\n/* synthetic */\n{a}\n}}\n"
        for n, a in anchors.items()
    )


class ProducerTests(unittest.TestCase):
    def test_pinned_and_unique_anchors(self) -> None:
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            instrument(uopt_fixture())
        result = _instrument(uopt_fixture())
        self.assertEqual(result.count("dkwb_lda_construct(mem);"), 1)
        self.assertEqual(result.count("dkwb_lda_dead(a0);"), 1)
        for bad in (
            uopt_fixture().replace("goto L441664;", "goto other;"),
            uopt_fixture().replace("return v0;", "", 1),
            uopt_fixture() + "static void f_getop(void) {\nreturn;\n}\n",
            result,
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                _instrument(bad)

    def test_cfe_creation_and_occurrence_anchors(self) -> None:
        fixture = source_fixture() + (
            "static uint32_t f_make(uint8_t *mem) {\nreturn v0;\n}\n"
            "static void f_expr_cg(uint8_t *mem) {\n/* synthetic */\nreturn;\n}\n"
        )
        result = _instrument_occurrences(fixture)
        self.assertIn("dkwb_cfe_node(mem,v0);", result)
        self.assertIn("dkwb_cfe_occ_end(mem,dkwb_occ);", result)
        for bad in (
            fixture.replace("f_make", "f_other"),
            fixture.replace("return v0;", "return v0;\nreturn v0;"),
        ):
            with self.assertRaises(ValueError):
                _instrument_occurrences(bad)


class OccurrenceTests(unittest.TestCase):
    def test_shadow_names_remain_distinct(self) -> None:
        r = join_occurrences(frontend(), STREAM)
        self.assertEqual([e["declaration_token"] for e in r["events"]], [1000, 2000])
        self.assertEqual([e["occurrence"] for e in r["events"]], [1, 2])
        self.assertFalse(r["source_expression_semantics"])

    def test_actual_cfe_output_pairing_is_mandatory(self) -> None:
        for t in (
            frontend().replace(STREAM.hex(), "00" * len(STREAM)),
            frontend().replace("output=0", "output=1"),
            frontend().replace(
                "DKWB-CFE-OCC output=0 datahex=" + STREAM.hex() + "\n", ""
            ),
        ):
            with self.assertRaises(ValueError):
                join_occurrences(t, STREAM)

    def test_recycled_node_pointer_uses_new_creation(self) -> None:
        t = frontend().replace("ptr=200", "ptr=100")
        r = join_occurrences(t, STREAM)
        self.assertEqual([e["generation"] for e in r["occurrences"]], [1, 2])
        with self.assertRaisesRegex(ValueError, "stale"):
            join_occurrences(
                t.replace("node_id=2 offset=24", "node_id=1 offset=24"), STREAM
            )

    def test_null_occurrence_has_no_node_identity(self) -> None:
        t = frontend().replace("ptr=100 node_id=1 offset=0", "ptr=0 node_id=0 offset=0")
        r = join_occurrences(t, STREAM)
        self.assertEqual(r["occurrences"][0]["generation"], 0)

    def test_forged_stale_missing_and_unbalanced_occurrences(self) -> None:
        cases = [
            frontend().replace("node_id=1 offset=0", "node_id=9 offset=0"),
            frontend().replace("DKWB-CFE-OCC capability=1\n", ""),
            frontend().replace("end=1 offset=24", "end=9 offset=24"),
            frontend().replace("node=2 ptr=200 node_id=2", "node=2 ptr=200 node_id=1"),
            frontend().replace("offset=24", "offset=23"),
        ]
        for t in cases:
            with self.subTest(t=t), self.assertRaises(ValueError):
                join_occurrences(t, STREAM)


class JoinTests(unittest.TestCase):
    def test_two_inputs_share_authentic_generation(self) -> None:
        r = report()
        self.assertEqual([c["generation"] for c in r["chains"]], [1, 1])
        self.assertEqual(
            [c["reused_observed_generation"] for c in r["chains"]], [False, True]
        )
        self.assertFalse(r["pre_proof"])
        self.assertFalse(r["optimized_ownership_proof"])

    def test_pointer_recycling_creates_new_generation(self) -> None:
        t = backend().replace(
            construct(2), "DKWB-LDA dead=500\nDKWB-LDA alloc=2 ptr=500\n" + construct(2)
        )
        r = report(t)
        self.assertEqual([c["generation"] for c in r["chains"]], [1, 2])
        self.assertFalse(r["chains"][1]["reused_observed_generation"])

    def test_dead_and_unobserved_pointer_refused(self) -> None:
        for t in (
            backend().replace(construct(2), "DKWB-LDA dead=500\n" + construct(2)),
            backend().replace("DKWB-LDA alloc=1 ptr=500\n", ""),
        ):
            with self.assertRaisesRegex(ValueError, "generation"):
                report(t)

    def test_unsupported_recursive_origin_is_explicit(self) -> None:
        t = backend().replace(
            "construct=2 current=2 depth=1", "construct=2 current=2 depth=2"
        )
        r = report(t)
        self.assertEqual(len(r["chains"]), 1)
        self.assertEqual(len(r["unresolved"]), 1)

    def test_missing_receipt_is_unresolved(self) -> None:
        r = report(backend().replace(construct(2), ""))
        self.assertEqual(r["unresolved"][0]["record_index"], 1)

    def test_missing_identified_source_occurrence_is_not_ownership(self) -> None:
        cfe = frontend().replace(
            "ptr=100 node_id=1 offset=0", "ptr=0 node_id=0 offset=0"
        )
        r = report(cfe=cfe)
        self.assertFalse(r["chains"][0]["source_occurrence_proof"])
        self.assertTrue(r["chains"][1]["source_occurrence_proof"])

    def test_ilda_is_not_admitted(self) -> None:
        other = (WORDS[0] & 0xFFFFFF) | (OPCODE_NAMES.index("ilda") << 24)
        stream = uword(*WORDS, other, *WORDS[1:])
        cfe = frontend().replace(STREAM.hex(), stream.hex())
        t = backend().replace(
            f"word=7 pass=1 value={WORDS[0]}", f"word=7 pass=1 value={other}"
        )
        t = t.replace(
            words("READ", 2), words("READ", 2).replace(f"w0={WORDS[0]}", f"w0={other}")
        )
        t = t.replace(
            words("GETOP", 2),
            words("GETOP", 2).replace(f"w0={WORDS[0]}", f"w0={other}"),
        )
        t = t.replace(construct(2), "")
        r = join_trace(t, stream, cfe_trace=cfe)
        self.assertEqual(len(r["chains"]), 1)
        self.assertEqual(r["unresolved"][0]["reason"], "unsupported ILDA input")

    def test_payload_normalization_refused(self) -> None:
        t = backend().replace(construct(2), construct(2).replace("w1=7", "w1=8"))
        with self.assertRaisesRegex(ValueError, "normalization"):
            report(t)

    def test_missing_peek_or_record_refused(self) -> None:
        for t in (
            backend().replace("DKWB-LDA peek_result=0 pass=1 offset=0\n", ""),
            backend().replace("DKWB-LDA record=2 pass=1 start=6 end=12\n", ""),
        ):
            with self.assertRaises(ValueError):
                report(t)

    def test_duplicate_selection_and_retimed_event_refused(self) -> None:
        t = backend().replace(words("GETOP", 2), words("GETOP", 2) + words("GETOP", 2))
        with self.assertRaises(ValueError):
            report(t)
        t = backend().replace(construct(1), "").replace(construct(2), construct(1))
        with self.assertRaisesRegex(ValueError, "retimed"):
            report(t)

    def test_stream_forgery_and_malformed_events_refused(self) -> None:
        bad = [
            backend().replace("word=1 pass=1 value=", "word=2 pass=1 value="),
            backend().replace("word=2 pass=1 value=7", "word=2 pass=1 value=8"),
            backend().replace("record=1 pass=1 start=0", "record=1 pass=1 start=1"),
            backend().replace("kind=READ read=2", "kind=READ read=3"),
            backend().replace("alloc=1 ptr=500", "alloc=2 ptr=500"),
            backend().replace(construct(2), construct(2) + construct(2)),
            backend() + "DKWB-LDA bad=1\n",
            backend() + "DKWB-LDA dead=500 dead=500\n",
            backend().replace(
                "peek_result=0 pass=1 offset=0", "peek_result=1 pass=1 offset=0"
            ),
        ]
        for t in bad:
            with self.subTest(t=t), self.assertRaises(ValueError):
                report(t)


if __name__ == "__main__":
    unittest.main()
