"""The `as1 -R` reader: the selection trace IDO 5.3 already ships.

The fixture is synthetic, written from the format strings in `as1`'s own
rodata and shaped after two selections a campaign recorded and read out by
hand: a `li`/`sll` pair decided on line number, and a `lui`/`subu` pair whose
second round the same key decides the other way.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.as1_reorganize import (
    mips_mnemonic,
    parse_as1_reorganize_trace,
    to_dkwb_records,
)
from decomp_workbench.cli import main
from decomp_workbench.scheduler import parse_scheduler_trace

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "traces" / "as1-reorganize.log"


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


def parse() -> tuple[list, list, list]:
    return parse_as1_reorganize_trace(FIXTURE.read_text(encoding="utf-8"))


class TieBreakTests(unittest.TestCase):
    def test_the_line_number_key_is_named_where_it_decides(self) -> None:
        # The whole reason this reader earns its place: key five is a source
        # physical line number, so whitespace is a codegen input.
        _selections, events, _ignored = parse()
        decided = {(event.block, event.cycle): event.tie for event in events}
        self.assertEqual(decided[(429, 1)], "lineno")
        self.assertEqual(decided[(131, 0)], "lineno")

    def test_an_earlier_key_wins_before_the_line_number_is_read(self) -> None:
        _selections, events, _ignored = parse()
        decided = {(event.block, event.cycle): event.tie for event in events}
        # node 2 starts a cycle earlier than node 1, so the chain stops at
        # key one and the line numbers are never compared.
        self.assertEqual(decided[(131, 1)], "start-time")

    def test_a_single_candidate_is_not_a_tie(self) -> None:
        _selections, events, _ignored = parse()
        sole = [event for event in events if event.tie == "sole-candidate"]
        self.assertEqual([event.ready for event in sole], [1, 1, 1])

    def test_a_full_tie_falls_through_to_list_order(self) -> None:
        text = (
            "BASIC BLOCK: 7\n"
            "Node   0: inst 00000021, relocation 0, lineno 40\n"
            "Node   1: inst 00000021, relocation 0, lineno 40\n"
            "Initial nodes: 0 1\n"
            "  node 0 (INST 1), time = 0, aftercycles = 0, latency = 0, "
            "besttime = 0\n"
            "  node 1 (INST 2), time = 0, aftercycles = 0, latency = 0, "
            "besttime = 0\n"
            "Picking node 0 (INST 1), at 0, best_addr = 0\n"
        )
        _selections, events, _ignored = parse_as1_reorganize_trace(text)
        self.assertEqual([event.tie for event in events], ["list-order"])

    def test_a_pick_the_chain_does_not_explain_says_so(self) -> None:
        # If the named key does not select the node the assembler picked, the
        # reader says the key disagrees rather than reporting a clean tie --
        # the chain here is evaluated without node->addr, and this is what a
        # trace where addr mattered would look like.
        text = (
            "BASIC BLOCK: 7\n"
            "Node   0: inst 00000021, relocation 0, lineno 40\n"
            "Node   1: inst 00000021, relocation 0, lineno 50\n"
            "Initial nodes: 0 1\n"
            "  node 0 (INST 1), time = 0, aftercycles = 0, latency = 0, "
            "besttime = 0\n"
            "  node 1 (INST 2), time = 0, aftercycles = 0, latency = 0, "
            "besttime = 0\n"
            "Picking node 1 (INST 2), at 0, best_addr = 0\n"
        )
        _selections, events, _ignored = parse_as1_reorganize_trace(text)
        self.assertEqual([event.tie for event in events], ["lineno-disagrees"])


class ParseTests(unittest.TestCase):
    def test_blocks_are_the_assemblers_own_ids(self) -> None:
        _selections, events, _ignored = parse()
        self.assertEqual(sorted({event.block for event in events}), [131, 429])

    def test_without_block_headers_blocks_are_numbered_by_appearance(self) -> None:
        text = "\n".join(
            line
            for line in FIXTURE.read_text(encoding="utf-8").splitlines()
            if not line.startswith("BASIC BLOCK:")
        )
        _selections, events, _ignored = parse_as1_reorganize_trace(text)
        self.assertEqual(sorted({event.block for event in events}), [0, 1])

    def test_a_reentered_block_does_not_reuse_a_cycle_key(self) -> None:
        # `as1` dumps a block again after reorganizing it. Resetting the
        # ordinal on the header would mint two selections with one key, and
        # the schema refuses that -- silently, in a converter that never
        # round-trips.
        text = FIXTURE.read_text(encoding="utf-8")
        _selections, events, _ignored = parse_as1_reorganize_trace(text + text)
        keys = [(event.proc, event.block, event.cycle) for event in events]
        self.assertEqual(len(keys), len(set(keys)))

    def test_the_word_and_line_come_from_the_node_dump(self) -> None:
        _selections, events, _ignored = parse()
        first = events[0]
        self.assertEqual(first.word, 0x8FA20090)
        self.assertEqual(first.opcode, "lw")
        self.assertEqual(first.line, 16404)

    def test_candidates_are_kept_with_the_selection(self) -> None:
        selections, _events, _ignored = parse()
        self.assertEqual(len(selections[0].candidates), 3)
        self.assertEqual(selections[0].winner.node, 0)

    def test_unrelated_assembler_chatter_is_retained_not_dropped(self) -> None:
        _selections, _events, ignored = parse()
        self.assertTrue(any("before reorganization" in line for line in ignored))

    def test_a_pick_without_its_candidate_list_is_not_invented(self) -> None:
        text = "Picking node 4 (INST 9), at 0, best_addr = 0\n"
        selections, events, ignored = parse_as1_reorganize_trace(text)
        self.assertEqual(selections, [])
        self.assertEqual(events, [])
        self.assertEqual(len(ignored), 1)


class MnemonicTests(unittest.TestCase):
    def test_known_words_decode(self) -> None:
        self.assertEqual(mips_mnemonic(0x2418000A), "addiu")
        self.assertEqual(mips_mnemonic(0x0002CC00), "sll")
        self.assertEqual(mips_mnemonic(0x3C020000), "lui")
        self.assertEqual(mips_mnemonic(0x0324C823), "subu")
        self.assertEqual(mips_mnemonic(0x00000000), "nop")

    def test_an_unknown_word_is_labelled_not_guessed(self) -> None:
        self.assertTrue(mips_mnemonic(0x4C000000).startswith("op."))


class RoundTripTests(unittest.TestCase):
    def test_emitted_records_parse_as_the_shipped_schema(self) -> None:
        _selections, events, _ignored = parse()
        reparsed, ignored = parse_scheduler_trace(to_dkwb_records(events))
        self.assertEqual(ignored, [])
        self.assertEqual(
            [item.as_dict() for item in reparsed], [item.as_dict() for item in events]
        )


class CommandTests(unittest.TestCase):
    def test_from_as1_r_reads_the_native_trace(self) -> None:
        status, stdout, _ = run_cli(["trace-scheduler", str(FIXTURE), "--from-as1-r"])
        self.assertEqual(status, 0)
        self.assertIn("block=429", stdout)
        self.assertIn("tie=lineno", stdout)

    def test_the_proof_states_both_gaps(self) -> None:
        status, stdout, _ = run_cli(
            ["trace-scheduler", str(FIXTURE), "--from-as1-r", "--json"]
        )
        self.assertEqual(status, 0)
        proof = json.loads(stdout)["proof"]
        self.assertIn("byte-identical", proof)
        self.assertIn("node->addr", proof)

    def test_emit_writes_records_the_other_commands_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sched.dkwb"
            status, _, _ = run_cli(
                [
                    "trace-scheduler",
                    str(FIXTURE),
                    "--from-as1-r",
                    "--emit",
                    str(output),
                ]
            )
            self.assertEqual(status, 0)
            events, _ = parse_scheduler_trace(output.read_text(encoding="utf-8"))
        self.assertEqual(len(events), 8)

    def test_two_native_traces_diff_against_each_other(self) -> None:
        status, stdout, _ = run_cli(
            [
                "trace-scheduler",
                str(FIXTURE),
                "--against",
                str(FIXTURE),
                "--from-as1-r",
            ]
        )
        self.assertEqual(status, 0)
        self.assertIn("0 decision(s) differ", stdout)

    def test_a_capture_without_selections_names_the_stderr_mistake(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "stdout-only.log"
            empty.write_text("as1: nothing here\n", encoding="utf-8")
            status, _, stderr = run_cli(["trace-scheduler", str(empty), "--from-as1-r"])
        self.assertEqual(status, 2)
        self.assertIn("stderr", stderr)

    def test_the_instrument_command_points_at_the_free_trace_first(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit):
            main(["instrument-scheduler", "--help"])
        self.assertIn("-Wa,-R", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
