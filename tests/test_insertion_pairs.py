"""The insertion-pair reader: pairs, shadow, owners and the label vocabulary.

Every fixture is synthetic: instruction streams assembled by `mips_asm`, line
headers written in `objdump -l` form, and ugen trace records typed by hand.
No word here comes from a game binary.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from mips_asm import assemble

from decomp_workbench.cli import main
from decomp_workbench.insertion_pairs import (
    LABELS,
    PAIRS_CENSUS_SCHEMA,
    PAIRS_SCHEMA,
    SPECIFIC_LABELS,
    LineTable,
    Step,
    analyse_pairs,
    census_rows,
    classify_word,
    edit_script,
    pairs_from_script,
    parse_line_table,
    parse_owner_trace,
    self_reassignment,
    unprototyped,
)
from decomp_workbench.model import Instruction
from decomp_workbench.objdump import parse_disassembly

SYMBOL = "demo"

FORMS = (
    "addiu t0,t0,{n}",
    "or t1,t2,t3",
    "lw t4,{m}(t5)",
    "sll t5,t6,{s}",
    "and t7,t8,t9",
    "xor s0,s1,s2",
    "sw t3,{m}(t6)",
    "subu s3,s4,s5",
    "slt s6,s7,t0",
    "nor v0,v1,a0",
    "andi t9,t9,{n}",
    "addu s0,s1,s2",
    "sltu t2,t3,t4",
)


def stream(count: int, start: int = 0) -> list[str]:
    """Distinct-looking instructions, so the alignment is unambiguous."""

    return [
        FORMS[index % len(FORMS)].format(
            n=index % 100, m=(index % 20) * 4, s=index % 31
        )
        for index in range(start, start + count)
    ]


def rows(
    lines: list[str], relocations: dict[int, str] | None = None
) -> list[Instruction]:
    return parse_disassembly(
        assemble(lines, symbol=SYMBOL, relocations=relocations), symbol=SYMBOL
    )


def with_lines(dump: str, numbers: list[int], *, source: str = "demo.c") -> str:
    """Interleave `objdump -l` headers: row k is stamped with numbers[k]."""

    out: list[str] = []
    row = 0
    current = None
    for line in dump.splitlines():
        if line.lstrip().startswith(tuple("0123456789abcdef")) and ":" in line:
            head = line.split(":", 1)[0].strip()
            is_row = (
                all(ch in "0123456789abcdef" for ch in head)
                and "R_MIPS" not in line
                and not line.endswith(">:")
            )
            if is_row and row < len(numbers):
                if numbers[row] != current:
                    out.append(f"{source}:{numbers[row]}")
                    current = numbers[row]
                row += 1
        if line.endswith(">:"):
            out.append(line)
            out.append(f"{SYMBOL}():")
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def table(numbers: list[int]) -> LineTable:
    return LineTable(
        source="demo.c", lines={row * 4: n for row, n in enumerate(numbers)}
    )


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


def only_word(report: dict[str, Any], side: str | None = None) -> dict[str, Any]:
    words = [
        word
        for pair in report["pairs"]
        for word in pair["words"]
        if side is None or word["side"] == side
    ]
    assert len(words) == 1, words
    word: dict[str, Any] = words[0]
    return word


class ClassTests(unittest.TestCase):
    def test_classes_come_from_the_encoding(self) -> None:
        cases = {
            "move a0,t0": "move",
            "lw t0,8(sp)": "stack-load",
            "sw t0,8(sp)": "stack-store",
            "lw t0,8(t1)": "load",
            "sw t0,8(t1)": "store",
            "addu t0,t1,t2": "alu",
            "li t0,5": "const",
            "lui t0,0x10": "const",
            "addiu sp,sp,-32": "frame",
            "jr ra": "frame",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                word = rows([text])[0].word_value
                self.assertEqual(classify_word(word), expected)

    def test_a_nop_after_a_branch_is_a_delay_nop(self) -> None:
        branch = rows(["beq t0,t1,@0"])[0].word_value
        self.assertEqual(classify_word(0, branch), "delay-nop")
        self.assertEqual(classify_word(0, None), "nop")


class PairTests(unittest.TestCase):
    def test_one_extra_word_is_one_open_pair_and_the_rest_is_shadow(self) -> None:
        body = stream(20)
        target = rows(body)
        candidate = rows([*body[:8], "move a1,t3", *body[8:]])
        report = analyse_pairs(target, candidate, symbol=SYMBOL)
        self.assertEqual(report["schema"], PAIRS_SCHEMA)
        self.assertEqual(report["size_delta"], 4)
        self.assertEqual(len(report["pairs"]), 1)
        pair = report["pairs"][0]
        self.assertFalse(pair["closed"])
        self.assertEqual(pair["positional_lo"], 8 * 4)
        self.assertIsNone(pair["positional_hi"])
        self.assertEqual(report["aligned_after_shadow"], 1)
        self.assertEqual(report["positional"] - report["shadow"], 1)
        self.assertTrue(report["outside_agrees"])
        word = only_word(report)
        self.assertEqual((word["side"], word["class"]), ("candidate", "move"))
        # No line table: nothing owns it, and the label says so.
        self.assertEqual(word["label"], "unowned")
        self.assertNotIn("assembly", json.dumps(report))

    def test_an_extra_and_a_missing_word_close_a_pair_at_delta_zero(self) -> None:
        body = stream(13)
        target = rows([*body[:6], *body[6:10], "li v1,9", *body[10:]])
        candidate = rows([*body[:6], "move a2,t7", *body[6:10], *body[10:]])
        report = analyse_pairs(target, candidate)
        self.assertEqual(report["size_delta"], 0)
        self.assertEqual(len(report["pairs"]), 1)
        pair = report["pairs"][0]
        self.assertTrue(pair["closed"])
        self.assertEqual(pair["positional_lo"], 6 * 4)
        self.assertEqual(pair["positional_hi"], 11 * 4)
        self.assertGreater(pair["shadow"], 0)
        self.assertEqual(report["aligned_after_shadow"], 2)
        self.assertTrue(report["outside_agrees"])

    def test_a_substituted_word_is_a_replaced_row_not_a_pair(self) -> None:
        body = stream(13)
        target = rows([*body[:4], "li v1,1", *body[4:]])
        candidate = rows([*body[:4], "move a2,t7", *body[4:]])
        script = edit_script(target, candidate)
        self.assertEqual(pairs_from_script(script), [])
        self.assertEqual([step.op for step in script].count("replace"), 1)

    def test_touching_shifts_are_two_pairs(self) -> None:
        script = [
            Step("equal", 0, 0),
            Step("candidate", 1, None),
            Step("target", None, 1),
            Step("candidate", 2, None),
            Step("target", None, 2),
            Step("equal", 3, 3),
        ]
        pairs = pairs_from_script(script)
        self.assertEqual([(pair.lo, pair.hi) for pair in pairs], [(1, 2), (2, 3)])
        self.assertTrue(all(pair.closed for pair in pairs))

    def test_no_one_sided_words_reports_no_pairs(self) -> None:
        body = stream(10)
        report = analyse_pairs(rows(body), rows(body))
        self.assertEqual(report["pairs"], [])
        self.assertEqual(report["label"], "none")


class OwnerTests(unittest.TestCase):
    TRACE = "\n".join(
        [
            "DKWB-CALL 1 > f_gen_procedure",
            "DKWB-CALL 2 > f_move_to_dest",
            "DKWB-CALL 3 > f_emit_rr",
            "DKWB-EMIT-V1 proc=0 block=1 emit=4 op=1 line=12 buffer=fwd fn=f_emit_rr",
            "DKWB-CALL 3 <",
            "DKWB-CALL 2 <",
            "DKWB-EMIT-V1 proc=0 block=1 emit=5 op=1 line=11 buffer=fwd fn=f_emit_rri",
            "DKWB-EMIT-V1 proc=0 block=1 emit=6 op=1 line=11 buffer=back fn=f_emit_rri",
            "DKWB-EMIT-V1 proc=0 block=1 emit=7 op=1 line=11 buffer=fwd fn=f_emit_dir2",
            "unrelated compiler chatter",
        ]
    )

    def test_trace_records_keep_the_handler_below_the_emitter(self) -> None:
        procedures = parse_owner_trace(self.TRACE)
        self.assertEqual(set(procedures), {0})
        emits = procedures[0].emits
        self.assertEqual(emits[12], [{"family": "move", "handler": "move_to_dest"}])
        # Backward-buffer and directive records are not instructions.
        self.assertEqual(len(emits[11]), 1)

    def test_a_word_is_owned_by_its_line_and_construct(self) -> None:
        body = stream(20)
        target = rows(body)
        candidate = rows([*body[:8], "move a1,t3", *body[8:]])
        numbers = [10] * 8 + [12] + [13] * 12
        report = analyse_pairs(
            target,
            candidate,
            lines=table(numbers),
            trace=parse_owner_trace(self.TRACE),
        )
        word = only_word(report)
        self.assertEqual(word["owner"]["line"], 12)
        self.assertEqual(word["owner"]["basis"], "line")
        self.assertEqual(word["owner"]["construct"], "move_to_dest")
        self.assertEqual(word["label"], "split-not-copy")
        self.assertEqual(report["trace"]["proc"], 0)

    def test_the_line_table_reads_objdump_l_headers(self) -> None:
        dump = with_lines(assemble(stream(5), symbol=SYMBOL), [3, 3, 4, 7, 7])
        parsed = parse_line_table(dump, symbol=SYMBOL)
        self.assertEqual(parsed.source, "demo.c")
        self.assertEqual(dict(parsed.lines), {0: 3, 4: 3, 8: 4, 12: 7, 16: 7})
        self.assertEqual(parsed.bounds, (3, 7))

    def test_a_header_line_is_kept_apart_from_the_unit(self) -> None:
        text = "\n".join(
            [
                "00000000 <demo>:",
                "demo.c:4",
                "   0:\t00000000 \tnop",
                "util.h:9",
                "   4:\t00000000 \tnop",
                "demo.c:5",
                "   8:\t00000000 \tnop",
            ]
        )
        parsed = parse_line_table(text, symbol=SYMBOL, source="demo.c")
        self.assertEqual(parsed.lines[4], "util.h:9")
        self.assertEqual(parsed.own_lines, (4, 5))


class SpecificLabelTests(unittest.TestCase):
    """Each label from backlog items 33, 34, 39 and 40, with its check."""

    def test_the_vocabulary_puts_specific_labels_first(self) -> None:
        self.assertEqual(LABELS[: len(SPECIFIC_LABELS)], SPECIFIC_LABELS)

    def test_isa_hazard_names_the_flag_and_no_line(self) -> None:
        head, tail = stream(8), stream(8, 40)
        target = rows([*head, "c.lt.s f0,f2", "nop", "bc1t @20", "nop", *tail])
        candidate = rows([*head, "c.lt.s f0,f2", "bc1t @19", "nop", *tail])
        report = analyse_pairs(target, candidate, lines=table([5] * 30))
        word = only_word(report)
        self.assertEqual(word["label"], "isa-hazard")
        self.assertIsNone(word["owner"]["line"])
        self.assertEqual(word["owner"]["basis"], "isa")
        self.assertIn("-mips2", word["lever"])
        self.assertEqual(report["label"], "isa-hazard")
        self.assertEqual(report["edit"], "compiler-flag")

    def test_a_nop_elsewhere_is_not_an_isa_hazard(self) -> None:
        head, tail = stream(8), stream(8, 40)
        target = rows([*head, "nop", *tail])
        candidate = rows([*head, *tail])
        word = only_word(analyse_pairs(target, candidate))
        self.assertNotEqual(word["label"], "isa-hazard")

    def test_self_reassign_copy_from_the_owning_line(self) -> None:
        body = stream(20)
        target = rows(body)
        candidate = rows([*body[:8], "move t0,t1", *body[8:]])
        source = [""] * 20
        source[11] = "    count = (count + 15) >> 4;"
        report = analyse_pairs(
            target,
            candidate,
            lines=table([10] * 8 + [12] + [14] * 12),
            source=source,
        )
        word = only_word(report)
        self.assertEqual(word["label"], "self-reassign-copy")
        self.assertIn("count", word["lever"])

    def test_self_reassignment_through_a_dead_second_local(self) -> None:
        source = [
            "void f(void) {",
            "    s32 radius, wide;",
            "    wide = radius * 2;",
            "    use(wide);",
            "}",
        ]
        self.assertEqual(self_reassignment(source, 3, 5), ("wide", "radius"))
        source[3] = "    use(wide, radius);"
        self.assertIsNone(self_reassignment(source, 3, 5))
        self.assertEqual(self_reassignment(["    r *= 2;"], 1, 1), ("r",))

    def test_arg_reg_copy_when_the_target_updates_in_place(self) -> None:
        head, tail = stream(8), stream(8, 40)
        target = rows([*head, "or a0,a0,t1", *tail])
        candidate = rows([*head, "or t0,a0,t1", "move a0,t0", *tail])
        report = analyse_pairs(target, candidate, lines=table([7] * 20))
        word = only_word(report)
        self.assertEqual(word["label"], "arg-reg-copy")
        # Preferred over the generic label a move would otherwise take.
        self.assertEqual(report["pairs"][0]["label"], "arg-reg-copy")

    def test_a_copy_into_an_argument_register_alone_is_not_arg_reg_copy(self) -> None:
        head, tail = stream(8), stream(8, 40)
        target = rows([*head, "or t0,a0,t1", *tail])
        candidate = rows([*head, "or t0,a0,t1", "move a0,t0", *tail])
        word = only_word(analyse_pairs(target, candidate, lines=table([7] * 20)))
        self.assertNotEqual(word["label"], "arg-reg-copy")

    def test_narrow_param_store_in_the_prologue(self) -> None:
        body = stream(12)
        target = rows(["addiu sp,sp,-32", "sw a0,32(sp)", *body, "jr ra", "nop"])
        candidate = rows(["addiu sp,sp,-32", *body, "jr ra", "nop"])
        word = only_word(analyse_pairs(target, candidate))
        self.assertEqual(word["label"], "narrow-param-store")
        self.assertIn("incoming-argument home", word["check"])

    def test_a_store_after_the_first_branch_is_not_a_parameter_store(self) -> None:
        body = stream(12)
        target = rows(["beq t0,t1,@3", "nop", *body[:2], "sw a0,24(sp)", *body[2:]])
        candidate = rows(["beq t0,t1,@3", "nop", *body])
        word = only_word(analyse_pairs(target, candidate))
        self.assertNotEqual(word["label"], "narrow-param-store")

    def test_memory_across_call_when_the_pair_brackets_a_jal(self) -> None:
        head, tail = stream(8), stream(8, 40)
        target_lines = [*head, "sw t0,24(sp)", "jal foo", "nop", "lw t0,24(sp)", *tail]
        candidate_lines = [*head, "jal foo", "nop", *tail]
        target = rows(target_lines, {9: "R_MIPS_26\tfoo"})
        candidate = rows(candidate_lines, {8: "R_MIPS_26\tfoo"})
        report = analyse_pairs(target, candidate)
        labels = [w["label"] for p in report["pairs"] for w in p["words"]]
        self.assertEqual(labels, ["memory-across-call", "memory-across-call"])
        self.assertEqual(report["label"], "memory-across-call")

    def test_unprototyped_call_needs_the_declaration(self) -> None:
        head, tail = stream(8), stream(8, 40)
        target = rows([*head, "jal foo", "nop", *tail], {8: "R_MIPS_26\tfoo"})
        candidate = rows(
            [*head, "li a1,0", "jal foo", "nop", *tail], {9: "R_MIPS_26\tfoo"}
        )
        for declaration, expected in (
            ("void foo();", "unprototyped-call"),
            ("void foo(void);", "missing-CSE"),
        ):
            with self.subTest(declaration=declaration):
                report = analyse_pairs(
                    target,
                    candidate,
                    lines=table([3] * 20),
                    source=[declaration, "", "    foo();"],
                    trace=parse_owner_trace(
                        "DKWB-EMIT-V1 proc=0 block=1 emit=1 op=1 line=3 "
                        "buffer=fwd fn=f_emit_ri_"
                    ),
                )
                self.assertEqual(only_word(report)["label"], expected)

    def test_unprototyped_reads_declarations_only(self) -> None:
        self.assertTrue(unprototyped(["extern void foo();"], "foo"))
        self.assertFalse(unprototyped(["void foo(s32 x);"], "foo"))
        self.assertFalse(unprototyped(["    foo();"], "bar"))

    def test_const_arg_copy_across_a_block_boundary(self) -> None:
        head, tail = stream(6), stream(8, 40)
        target = rows(
            [
                *head,
                "li a2,192",
                "beq t1,zero,@10",
                "nop",
                "li t4,1",
                "jal bar",
                "nop",
                *tail,
            ],
            {10: "R_MIPS_26\tbar"},
        )
        candidate = rows(
            [
                *head,
                "li t0,192",
                "beq t1,zero,@10",
                "nop",
                "li t4,1",
                "move a2,t0",
                "jal bar",
                "nop",
                *tail,
            ],
            {11: "R_MIPS_26\tbar"},
        )
        report = analyse_pairs(target, candidate)
        labels = {w["label"] for p in report["pairs"] for w in p["words"]}
        self.assertIn("const-arg-copy", labels)

    def test_a_constant_in_the_same_block_is_not_const_arg_copy(self) -> None:
        head, tail = stream(6), stream(8, 40)
        target = rows(
            [*head, "li a2,192", "jal bar", "nop", *tail], {7: "R_MIPS_26\tbar"}
        )
        candidate = rows(
            [*head, "li t0,192", "move a2,t0", "jal bar", "nop", *tail],
            {8: "R_MIPS_26\tbar"},
        )
        labels = {
            w["label"]
            for p in analyse_pairs(target, candidate)["pairs"]
            for w in p["words"]
        }
        self.assertNotIn("const-arg-copy", labels)


class CensusTests(unittest.TestCase):
    def test_rows_are_filtered_by_size_delta(self) -> None:
        rows_in, rejected = census_rows(
            {
                "functions": [
                    {"name": "a", "size_delta": 4},
                    {"name": "b", "size_delta": 0},
                    {"name": "c", "size_delta": 40},
                    {"symbol": "d"},
                    {"size_delta": 4},
                ]
            },
            max_delta=12,
        )
        self.assertEqual([row["symbol"] for row in rows_in], ["a", "d"])
        self.assertEqual(len(rejected), 1)

    def test_the_census_sorts_by_edit_and_refuses_to_overwrite(self) -> None:
        body = stream(20)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "t.dump").write_text(assemble(body, symbol=SYMBOL))
            (root / "c.dump").write_text(
                assemble([*body[:8], "move a1,t3", *body[8:]], symbol=SYMBOL)
            )
            ranking = root / "ranking.json"
            ranking.write_text(
                json.dumps(
                    [
                        {
                            "name": SYMBOL,
                            "size_delta": 4,
                            "target": "t.dump",
                            "candidate": "c.dump",
                            "dumps": True,
                        },
                        {"name": "missing", "size_delta": 8},
                    ]
                )
            )
            out = root / "census.md"
            status, stdout, _ = run_cli(
                ["object", "pairs-census", str(ranking), "--json", "--out", str(out)]
            )
            self.assertEqual(status, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["schema"], PAIRS_CENSUS_SCHEMA)
            self.assertEqual(payload["measured"], 1)
            self.assertEqual(payload["not_measured"], 1)
            self.assertEqual(payload["results"][0]["aligned_after_shadow"], 1)
            text = out.read_text()
            self.assertIn("## By the edit each needs", text)
            self.assertNotIn("move", text.split("## Functions")[1].split("|")[0])
            status, _, stderr = run_cli(
                ["pairs-census", str(ranking), "--out", str(out)]
            )
            self.assertEqual(status, 2)
            self.assertIn("never overwrites", stderr)


class CommandTests(unittest.TestCase):
    def test_pairs_dumps_reads_the_candidate_dump_line_table(self) -> None:
        body = stream(20)
        numbers = [10] * 8 + [12] + [13] * 12
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "t.dump"
            candidate = root / "c.dump"
            target.write_text(assemble(body, symbol=SYMBOL))
            candidate.write_text(
                with_lines(
                    assemble([*body[:8], "move a1,t3", *body[8:]], symbol=SYMBOL),
                    numbers,
                )
            )
            flat = run_cli(
                [
                    "pairs-dumps",
                    str(target),
                    str(candidate),
                    "--symbol",
                    SYMBOL,
                    "--json",
                ]
            )
            grouped = run_cli(
                [
                    "object",
                    "pairs-dumps",
                    str(target),
                    str(candidate),
                    "--symbol",
                    SYMBOL,
                    "--json",
                ]
            )
            status, stdout, _ = run_cli(
                ["pairs-dumps", str(target), str(candidate), "--symbol", SYMBOL]
            )
        self.assertEqual(flat, grouped)
        payload = json.loads(flat[1])
        self.assertEqual(payload["schema"], PAIRS_SCHEMA)
        self.assertEqual(payload["line_table"]["words"], 21)
        self.assertEqual(only_word(payload)["owner"]["line"], 12)
        self.assertEqual(status, 0)
        self.assertIn("pair 1:", stdout)
        self.assertIn("aligned after shadow 1", stdout)


if __name__ == "__main__":
    unittest.main()
