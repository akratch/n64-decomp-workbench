"""The frame ladder: slot decode, temp classification, and the operation stream.

The fixtures here are synthetic, and deliberately so: the campaign that
produced this reader kept its conclusions and threw away its logs, so the
records below are written from the grammar in
``src/decomp_workbench/patches/README.md`` rather than captured. That makes
them a check on the grammar as much as on the reader -- if the two ever drift,
:class:`PatchGrammarTests` fails before anything else does.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cascade import CascadeError, CdxLog
from decomp_workbench.cli import main
from decomp_workbench.frame_ladder import (
    SYMTAB_RECORD_GRAMMAR,
    frame_ladder,
    op_report,
    parse_slot_names,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "traces" / "frame-ladder.log"
NAMES = ROOT / "examples" / "fixtures" / "frame-names.txt"
PATCH = ROOT / "src" / "decomp_workbench" / "patches" / "uopt-5.3-cdx-symtab.patch"


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


def read_log() -> CdxLog:
    return CdxLog(FIXTURE.read_text(encoding="utf-8"), name="frame-ladder.log")


class LadderTests(unittest.TestCase):
    def test_home_is_the_offset_minus_the_signed_frame(self) -> None:
        # The whole point of the sign convention: -140 in a -216 frame is
        # 76(sp), which is what a disassembly shows.  Adding the signed frame
        # instead would put the slot at -356 and read as a plausible ladder.
        ladder = frame_ladder(read_log(), frame=-216)
        homes = {slot.offset: slot.home for slot in ladder.slots}
        self.assertEqual(homes[-140], 76)
        self.assertEqual(homes[-144], 72)
        self.assertEqual(homes[0], 216)

    def test_without_a_frame_no_home_is_invented(self) -> None:
        ladder = frame_ladder(read_log())
        self.assertTrue(all(slot.home is None for slot in ladder.slots))

    def test_slots_carry_size_class_and_the_first_index(self) -> None:
        ladder = frame_ladder(read_log(), frame=-216)
        slots = {slot.offset: slot for slot in ladder.slots}
        self.assertEqual(slots[-132].size, 2)  # an s16 local
        self.assertEqual(slots[-132].storage_class_name, "M")
        self.assertEqual(slots[0].storage_class_name, "P")
        self.assertEqual(slots[2].storage_class_name, "R")
        self.assertEqual(slots[-140].index, 72)

    def test_webs_join_to_the_slot_by_frame_offset(self) -> None:
        # Two webs share one slot.  Joining by symbol number would have found
        # them too until a rebase renumbered the symbol; the offset does not
        # move.
        ladder = frame_ladder(read_log(), frame=-216)
        slots = {slot.offset: slot for slot in ladder.slots}
        self.assertEqual(slots[-136].webs, (80, 181))
        self.assertEqual(slots[-136].sources, ("symtab", "webdetail"))
        self.assertEqual(slots[-124].webs, ())

    def test_unnamed_slots_below_the_lowest_named_one_are_temps(self) -> None:
        names = parse_slot_names(NAMES.read_text(encoding="utf-8"), frame=-216)
        ladder = frame_ladder(read_log(), frame=-216, names=names)
        self.assertEqual(ladder.lowest_named_offset, -136)
        self.assertEqual([slot.offset for slot in ladder.below_named], [-144, -140])

    def test_no_names_means_no_temp_claim(self) -> None:
        # A ladder with nothing named cannot say which slots are temps, and
        # says nothing rather than guessing a threshold.  One campaign script
        # hard-coded `off < -100` and it was true of exactly one function.
        ladder = frame_ladder(read_log(), frame=-216)
        self.assertEqual(ladder.below_named, ())

    def test_a_name_for_an_absent_slot_is_a_warning_not_a_row(self) -> None:
        ladder = frame_ladder(read_log(), frame=-216, names={-999: "ghost"})
        self.assertEqual(len(ladder.warnings), 1)
        self.assertIn("-999", ladder.warnings[0])
        self.assertNotIn(-999, [slot.offset for slot in ladder.slots])

    def test_webdetail_only_log_says_the_ladder_is_a_subset(self) -> None:
        text = "\n".join(
            line
            for line in FIXTURE.read_text(encoding="utf-8").splitlines()
            if "] symtab" not in line
        )
        ladder = frame_ladder(CdxLog(text, name="webs-only.log"), frame=-216)
        self.assertEqual(ladder.sources, ("webdetail",))
        self.assertEqual([slot.offset for slot in ladder.slots], [-136, -132])
        self.assertTrue(
            any("subset of the frame" in warning for warning in ladder.warnings)
        )

    def test_webdetail_sizes_come_from_the_top_byte_of_raw18(self) -> None:
        text = "\n".join(
            line
            for line in FIXTURE.read_text(encoding="utf-8").splitlines()
            if "] symtab" not in line
        )
        ladder = frame_ladder(CdxLog(text, name="webs-only.log"))
        slots = {slot.offset: slot for slot in ladder.slots}
        self.assertEqual(slots[-136].size, 4)
        self.assertEqual(slots[-132].size, 2)

    def test_a_log_with_no_frame_evidence_names_both_instruments(self) -> None:
        log = CdxLog("[CDX] globalcolor proc=0\n", name="bare.log")
        with self.assertRaises(CascadeError) as caught:
            frame_ladder(log)
        message = str(caught.exception)
        self.assertIn("CDX_SYMTAB=1", message)
        self.assertIn("CDX_LOG=1", message)


class OperationStreamTests(unittest.TestCase):
    def test_operands_resolve_to_supplied_names(self) -> None:
        names = parse_slot_names(NAMES.read_text(encoding="utf-8"), frame=-216)
        ladder = frame_ladder(read_log(), frame=-216, names=names)
        report = op_report(ladder, names=names)
        rows = {row["index"]: row for row in report["operations"]}
        self.assertEqual(rows[71]["left_name"], "viewx(69)")
        self.assertEqual(rows[410]["opcode_name"], "usub")

    def test_an_unnamed_operand_falls_back_to_class_and_offset(self) -> None:
        # The pooled integer temp has no name and must not borrow one.
        ladder = frame_ladder(read_log(), frame=-216)
        rows = {row["index"]: row for row in op_report(ladder)["operations"]}
        self.assertEqual(rows[74]["left_name"], "M-140(72)")

    def test_offsets_filter_the_stream_to_one_slot(self) -> None:
        ladder = frame_ladder(read_log(), frame=-216)
        report = op_report(ladder, offsets=[-140])
        self.assertEqual([row["index"] for row in report["operations"]], [74])

    def test_no_symtab_records_is_an_error_naming_the_instrument(self) -> None:
        text = "\n".join(
            line
            for line in FIXTURE.read_text(encoding="utf-8").splitlines()
            if "] symtab" not in line
        )
        ladder = frame_ladder(CdxLog(text, name="webs-only.log"))
        with self.assertRaises(CascadeError) as caught:
            op_report(ladder)
        self.assertIn("CDX_SYMTAB=1", str(caught.exception))


class NameMapTests(unittest.TestCase):
    def test_both_spellings_of_one_slot_agree(self) -> None:
        frame_offsets = parse_slot_names("-140 temp\n", frame=-216)
        sp_offsets = parse_slot_names("sp:76 temp\n", frame=-216)
        self.assertEqual(frame_offsets, sp_offsets)

    def test_hex_and_two_complement_spellings_are_accepted(self) -> None:
        self.assertEqual(parse_slot_names("0xffffff74 temp\n"), {-140: "temp"})

    def test_an_sp_slot_without_a_frame_is_refused(self) -> None:
        with self.assertRaisesRegex(CascadeError, "needs --frame"):
            parse_slot_names("sp:76 temp\n")

    def test_comments_and_blank_lines_are_ignored(self) -> None:
        self.assertEqual(parse_slot_names("# note\n\n-140 temp\n"), {-140: "temp"})

    def test_a_malformed_line_names_its_line_number(self) -> None:
        with self.assertRaisesRegex(CascadeError, "names line 2"):
            parse_slot_names("-140 temp\nnonsense\n")


class FrameCommandTests(unittest.TestCase):
    def test_the_ladder_prints_lowest_slot_first(self) -> None:
        status, stdout, _ = run_cli(
            ["trace-frame", str(FIXTURE), "--frame", "-216", "--pager", "never"]
        )
        self.assertEqual(status, 0)
        offsets = [
            int(line.split()[0])
            for line in stdout.splitlines()
            if line.startswith("    -") or line.startswith("       ")
        ]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn("76(sp)", stdout)

    def test_summary_is_one_sweep_column(self) -> None:
        status, stdout, _ = run_cli(
            [
                "trace-frame",
                str(FIXTURE),
                "--frame",
                "-216",
                "--names",
                str(NAMES),
                "--summary",
                "--pager",
                "never",
            ]
        )
        self.assertEqual(status, 0)
        self.assertIn("named=8", stdout)
        self.assertIn("temps below it 2", stdout)

    def test_json_carries_the_schema_and_the_slots(self) -> None:
        status, stdout, _ = run_cli(
            ["trace-frame", str(FIXTURE), "--frame", "-216", "--json"]
        )
        self.assertEqual(status, 0)
        document = json.loads(stdout)
        self.assertEqual(document["schema"], "decomp-workbench-frame-ladder-v1")
        self.assertEqual(document["slot_count"], 12)
        self.assertEqual(document["slots"][0]["offset"], -144)

    def test_a_log_without_cdx_records_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "nothing.log"
            empty.write_text("no records here\n", encoding="utf-8")
            status, _, stderr = run_cli(["trace-frame", str(empty)])
        self.assertEqual(status, 2)
        self.assertIn("[CDX]", stderr)

    def test_an_unreadable_names_file_fails_loudly(self) -> None:
        status, _, stderr = run_cli(
            ["trace-frame", str(FIXTURE), "--names", "/nonexistent/names.txt"]
        )
        self.assertEqual(status, 2)
        self.assertIn("cannot read", stderr)

    def test_the_grammar_action_lists_the_symtab_records(self) -> None:
        with self.assertRaises(SystemExit):
            run_cli(["trace-cascade", str(FIXTURE), "--grammar"])


class PatchGrammarTests(unittest.TestCase):
    """The reader and the patch that feeds it must not drift apart."""

    def test_every_field_the_reader_reads_is_in_the_patch(self) -> None:
        patch = PATCH.read_text(encoding="utf-8")
        for field in (
            "idx",
            "kind",
            "dtype",
            "selfidx",
            "ver",
            "off",
            "tag",
            "class",
            "b24",
            "vreg",
            "op",
        ):
            with self.subTest(field=field):
                self.assertIn(f"{field}=%", patch)

    def test_the_patch_records_the_base_it_applies_to(self) -> None:
        readme = (PATCH.parent / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "e465eb4b76ac001d1c94ff8bf74c378217b6ed2e674a6b73c6722edc01baf5ca",
            readme,
        )
        self.assertIn("CDX_SYMTAB", readme)

    def test_the_patch_is_a_unified_diff_against_one_file(self) -> None:
        lines = PATCH.read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines[0].startswith("--- a/build/5.3/uopt.c"))
        self.assertTrue(lines[1].startswith("+++ b/build/5.3/uopt.c"))
        self.assertTrue(any(line.startswith("@@") for line in lines))

    def test_both_records_are_documented_in_the_grammar_table(self) -> None:
        self.assertEqual(set(SYMTAB_RECORD_GRAMMAR), {"symtab", "symtabcount"})
        for description in SYMTAB_RECORD_GRAMMAR.values():
            self.assertIn("CAMPAIGN-LOCAL", description)


if __name__ == "__main__":
    unittest.main()
