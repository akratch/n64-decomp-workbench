"""Statement-line evidence: the screen a `-g0` project's schedule verdict owed.

`verdict=schedule-mismatch` used to route to one probe -- rebuild at `-g0` --
which is vacuous for a project that already builds `-g0`. These tests hold the
promises the new evidence makes:

* the ugen listing parses into instructions carrying the `.loc` that governs
  them, through labels, directives, comments and a truncated file;
* a site is mapped by anchors, never by position, and an unmappable one says so
  instead of disappearing;
* the counts on the shipped fixture are the ones the page claims, and a
  boundary majority promotes `playbook=line-assignment-probe`;
* a reader who did not pass the option is told it exists and where the file
  comes from.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import ClassVar

from mips_asm import assemble

from decomp_workbench import field_guide, loc_boundaries
from decomp_workbench.cli import main
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.view import build_view

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples" / "fixtures"
TARGET = FIXTURES / "loc-boundary-target.objdump"
CANDIDATE = FIXTURES / "loc-boundary-candidate.objdump"
LISTING = FIXTURES / "loc-boundary-candidate.s"
SYMBOL = "blitRow"

#: A listing exercising every line shape the parser must survive.
SAMPLE = """\
\t.file\t2 "sample.c"
\t.option\tpic2
\t.text
\t.globl\tsample
\t.loc\t2\t10
 #    10\tvoid sample(s32 *p) {
\t.ent\tsample 2
sample:
\t.frame\t$sp, 0, $31
\t.mask\t0x00000000, 0
\t.loc\t2\t12
 #    12\t    p[0] = 1;
\tli\t$t0, 1
\tsw\t$t0, 0($a0)
$32:
\t.livereg\t0x0000FF0E,0x00000000
\t.loc\t2\t14
 #    14\t    p[1] = p[0];
\tlw\t$t1, 0($a0)\t# a trailing comment
\tsw\t$t1, 4($a0)
\t.loc\t2\t15
\tjr\t$ra
\t.end\tsample
"""


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    """Run one command in process and capture both streams."""

    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


def fixture_view() -> object:
    target = parse_disassembly(TARGET.read_text(encoding="utf-8"), symbol=SYMBOL)
    candidate = parse_disassembly(CANDIDATE.read_text(encoding="utf-8"), symbol=SYMBOL)
    return build_view(
        target,
        candidate,
        target_name="target",
        candidate_name="candidate",
        symbol=SYMBOL,
    )


class ListingParserTests(unittest.TestCase):
    def test_every_instruction_carries_the_loc_that_governs_it(self) -> None:
        functions = loc_boundaries.parse_listing(SAMPLE)
        self.assertEqual([item.name for item in functions], ["sample"])
        found = [(item.mnemonic, item.line) for item in functions[0].instructions]
        self.assertEqual(
            found,
            [
                ("li", 12),
                ("sw", 12),
                ("lw", 14),
                ("sw", 14),
                ("jr", 15),
            ],
        )

    def test_labels_directives_and_comments_are_not_instructions(self) -> None:
        """Each of these once parsed as a mnemonic and shifted every line."""

        instructions = loc_boundaries.parse_listing(SAMPLE)[0].instructions
        mnemonics = {item.mnemonic for item in instructions}
        for absent in (".livereg", ".frame", ".mask", ".option", "$32", "#"):
            with self.subTest(shape=absent):
                self.assertNotIn(absent, mnemonics)
        self.assertEqual(len(instructions), 5)

    def test_a_trailing_comment_does_not_reach_the_instruction_text(self) -> None:
        instructions = loc_boundaries.parse_listing(SAMPLE)[0].instructions
        self.assertEqual(instructions[2].text, "lw $t1, 0($a0)")

    def test_the_file_table_names_the_loc_file_index(self) -> None:
        instruction = loc_boundaries.parse_listing(SAMPLE)[0].instructions[0]
        self.assertEqual(instruction.file_index, 2)
        self.assertEqual(instruction.file, "sample.c")

    def test_several_functions_are_kept_apart(self) -> None:
        text = SAMPLE + SAMPLE.replace("sample", "other")
        functions = loc_boundaries.parse_listing(text)
        self.assertEqual([item.name for item in functions], ["sample", "other"])

    def test_a_truncated_listing_keeps_what_it_has(self) -> None:
        """A cut-off capture is partial evidence, not a parse error."""

        truncated = SAMPLE.split("\t.loc\t2\t14")[0]
        functions = loc_boundaries.parse_listing(truncated)
        self.assertEqual(len(functions), 1)
        self.assertEqual(len(functions[0].instructions), 2)

    def test_a_trimmed_listing_without_ent_still_parses(self) -> None:
        body = "\n".join(
            line
            for line in SAMPLE.splitlines()
            if ".ent" not in line and ".end" not in line
        )
        functions = loc_boundaries.parse_listing(body)
        self.assertEqual([item.name for item in functions], [""])
        self.assertEqual(len(functions[0].instructions), 5)

    def test_selecting_a_missing_function_names_what_the_file_holds(self) -> None:
        functions = loc_boundaries.parse_listing(SAMPLE)
        with self.assertRaises(ValueError) as raised:
            loc_boundaries.select_function(functions, "absent")
        self.assertIn("sample", str(raised.exception))

    def test_several_functions_without_a_symbol_is_refused(self) -> None:
        functions = loc_boundaries.parse_listing(SAMPLE + SAMPLE.replace("sample", "b"))
        with self.assertRaises(ValueError) as raised:
            loc_boundaries.select_function(functions, None)
        self.assertIn("--symbol", str(raised.exception))


class SiteMappingTests(unittest.TestCase):
    def test_anchors_map_and_a_macro_stays_unmapped(self) -> None:
        """`li` is still a macro in the listing; nothing is paired by position."""

        function = loc_boundaries.parse_listing(LISTING.read_text(encoding="utf-8"))[0]
        candidate = parse_disassembly(
            CANDIDATE.read_text(encoding="utf-8"), symbol=SYMBOL
        )
        mapping = loc_boundaries.map_to_listing(
            [item.assembly for item in candidate], function
        )
        self.assertEqual(mapping[:14], tuple(range(14)))
        # index 14 is `addiu $v0,$zero,1`, written `li $v0, 1` in the listing;
        # index 19 is the delay-slot `nop` as1 added.
        self.assertIsNone(mapping[14])
        self.assertIsNone(mapping[19])
        self.assertEqual(mapping[15:19], (15, 16, 17, 18))

    def test_a_mnemonic_survives_an_operand_respelling(self) -> None:
        """The second pass exists for `sw $31` versus `sw $ra`."""

        listing = SAMPLE.replace("\tjr\t$ra", "\tjr\t$31")
        function = loc_boundaries.parse_listing(listing)[0]
        mapping = loc_boundaries.map_to_listing(
            ["li $t0,1", "sw $t0,0($a0)", "lw $t1,0($a0)", "sw $t1,4($a0)", "jr $ra"],
            function,
        )
        self.assertEqual(mapping[4], 4)


class SiteAnnotationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = loc_boundaries.annotate_schedule_sites(
            fixture_view(),  # type: ignore[arg-type]
            LISTING.read_text(encoding="utf-8"),
            listing_name="listing.s",
            symbol=SYMBOL,
        )

    def test_the_fixture_counts_are_the_ones_the_page_claims(self) -> None:
        self.assertEqual(len(self.report.sites), 3)
        self.assertEqual(self.report.boundary_sites, 2)
        self.assertEqual(self.report.decidable_sites, 3)
        self.assertEqual(len(self.report.target_only_hunks), 3)
        self.assertTrue(self.report.majority)
        self.assertIn(
            "2 of 3 schedule-divergent sites sit at statement-line boundaries",
            self.report.summary_line,
        )

    def test_one_site_straddles_a_boundary_and_one_does_not(self) -> None:
        statuses = [site.status for site in self.report.sites]
        self.assertEqual(statuses, ["boundary", "same-line", "boundary"])
        boundary, same_line, _ = self.report.sites
        self.assertEqual(boundary.distinct_lines, (201, 206, 211))
        self.assertEqual(same_line.distinct_lines, (220,))

    def test_a_one_sided_hunk_is_widened_and_says_so(self) -> None:
        widened = [site.widened for site in self.report.sites]
        self.assertEqual(widened, [True, False, True])
        rendered = "\n".join(loc_boundaries.render_loc_boundaries(self.report))
        self.assertIn("widened=yes", rendered)
        self.assertIn("one instruction on each side", rendered)

    def test_target_only_hunks_are_named_never_dropped(self) -> None:
        rendered = "\n".join(loc_boundaries.render_loc_boundaries(self.report))
        self.assertIn("3 hunks hold no candidate instruction (2, 4, 6)", rendered)

    def test_an_instruction_missing_from_the_listing_prints_as_unknown(self) -> None:
        rendered = "\n".join(loc_boundaries.render_loc_boundaries(self.report))
        self.assertIn("lines=?,224,228", rendered)
        self.assertIn("never guessed at by position", rendered)

    def test_a_boundary_majority_promotes_the_new_playbook(self) -> None:
        guidance = "\n".join(loc_boundaries.report_guidance(self.report))
        self.assertIn("field guide levers for playbook=line-assignment-probe", guidance)
        self.assertIn("lever 23:", guidance)
        self.assertIn("even at -g0", guidance)

    def test_the_payload_carries_every_rendered_number(self) -> None:
        payload = self.report.as_dict()
        self.assertEqual(payload["schema"], loc_boundaries.LOC_BOUNDARIES_SCHEMA)
        self.assertEqual(payload["playbook"], "line-assignment-probe")
        self.assertEqual(payload["boundary_sites"], 2)
        self.assertEqual(payload["target_only_hunks"], [2, 4, 6])
        self.assertEqual(payload["sites"][0]["lines"], [201, 206, 211])


class UnmappableSiteTests(unittest.TestCase):
    def test_a_listing_for_another_function_reports_no_result_not_a_negative(
        self,
    ) -> None:
        """A negative is a decision. "I could not tell" must not look like one."""

        unrelated = (
            "\t.loc\t1\t3\n\t.ent\tblitRow\nblitRow:\n"
            "\tmult\t$t0, $t1\n\tmflo\t$t2\n\tbreak\t0\n\t.end\tblitRow\n"
        )
        report = loc_boundaries.annotate_schedule_sites(
            fixture_view(),  # type: ignore[arg-type]
            unrelated,
            listing_name="wrong.s",
            symbol=SYMBOL,
        )
        self.assertEqual(report.boundary_sites, 0)
        self.assertEqual(report.decidable_sites, 0)
        self.assertEqual(report.unmapped_sites, 3)
        self.assertFalse(report.majority)
        guidance = "\n".join(loc_boundaries.report_guidance(report))
        self.assertIn("no site could be attributed", guidance)
        self.assertNotIn("playbook=line-assignment-probe", guidance)
        rendered = "\n".join(loc_boundaries.render_loc_boundaries(report))
        self.assertEqual(rendered.count("status=unmapped"), 3)

    def test_a_comparison_with_no_schedule_rows_says_so(self) -> None:
        identical = assemble(["lw t0,0(a0)", "jr ra"], symbol="tiny")
        view = build_view(
            parse_disassembly(identical, symbol="tiny"),
            parse_disassembly(
                assemble(["lw t1,0(a0)", "jr ra"], symbol="tiny"), symbol="tiny"
            ),
            target_name="target",
            candidate_name="candidate",
            symbol="tiny",
        )
        report = loc_boundaries.annotate_schedule_sites(
            view,
            "\t.ent\ttiny\ntiny:\n\t.loc\t1\t5\n\tlw\t$t1, 0($a0)\n\t.end\ttiny\n",
            listing_name="tiny.s",
            symbol="tiny",
        )
        self.assertEqual(report.sites, ())
        self.assertIn("no aligned row is schedule-class", report.summary_line)


class DiagnoseCommandTests(unittest.TestCase):
    ARGUMENTS: ClassVar[list[str]] = [
        "diagnose-dumps",
        str(TARGET),
        str(CANDIDATE),
        "--function",
        SYMBOL,
        "--pager",
        "never",
    ]

    def test_the_listing_section_and_the_promoted_playbook_reach_the_screen(
        self,
    ) -> None:
        status, stdout, _ = run_cli(
            [*self.ARGUMENTS, "--candidate-listing", str(LISTING)]
        )
        self.assertEqual(status, 0)
        self.assertIn("STATEMENT LINES", stdout)
        self.assertIn(
            "2 of 3 schedule-divergent sites sit at statement-line boundaries",
            stdout,
        )
        self.assertIn("playbook=line-assignment-probe", stdout)
        # the footer stays one block, with the continuation indent
        footer = stdout.split("next: ", 1)[1].splitlines()
        self.assertTrue(
            all(not line or line.startswith("      ") for line in footer[1:])
        )

    def test_the_section_sits_above_the_footer(self) -> None:
        """The footer is the instruction, and must be the last thing read."""

        _, stdout, _ = run_cli([*self.ARGUMENTS, "--candidate-listing", str(LISTING)])
        self.assertLess(stdout.index("STATEMENT LINES"), stdout.index("next: "))

    def test_a_schedule_verdict_without_the_option_is_told_it_exists(self) -> None:
        status, stdout, _ = run_cli(self.ARGUMENTS)
        self.assertEqual(status, 0)
        self.assertIn("--candidate-listing", stdout)
        self.assertIn("cc -K", stdout)
        self.assertIn("ugen -l", stdout)
        self.assertNotIn("STATEMENT LINES", stdout)

    def test_the_json_payload_carries_the_report(self) -> None:
        status, stdout, _ = run_cli(
            [*self.ARGUMENTS, "--candidate-listing", str(LISTING), "--json"]
        )
        self.assertEqual(status, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["loc_boundaries"]["boundary_sites"], 2)
        self.assertIn(
            "field guide levers for playbook=line-assignment-probe",
            "\n".join(payload["view"]["next"]),
        )

    def test_an_unreadable_listing_is_an_error_not_a_traceback(self) -> None:
        status, _, stderr = run_cli(
            [*self.ARGUMENTS, "--candidate-listing", str(FIXTURES / "absent.s")]
        )
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)

    def test_a_listing_without_the_selected_function_says_what_it_holds(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            other = Path(temp) / "other.s"
            other.write_text(SAMPLE, encoding="utf-8")
            status, _, stderr = run_cli(
                [*self.ARGUMENTS, "--candidate-listing", str(other)]
            )
        self.assertEqual(status, 2)
        self.assertIn("sample", stderr)

    def test_the_option_help_says_where_the_file_comes_from(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit):
            main(["diagnose", "--help"])
        text = " ".join(stdout.getvalue().split())
        self.assertIn("--candidate-listing", text)
        self.assertIn("cc -K", text)
        self.assertIn("ugen -l", text)


class FieldGuideRegistryTests(unittest.TestCase):
    def test_lever_23_has_an_action_and_a_section(self) -> None:
        self.assertIn(23, field_guide.LEVER_ACTIONS)
        self.assertIn("acpp", field_guide.LEVER_ACTIONS[23])
        self.assertIn("-g0", field_guide.LEVER_ACTIONS[23])
        self.assertIn(23, field_guide.sections())

    def test_the_new_playbook_and_the_old_one_both_reach_lever_23(self) -> None:
        # The roster grows as line-number mechanisms are found (33 is the
        # assembler's scheduler reading source lines), so the property held
        # here is the reachability and the opening order, not the exact set.
        levers = field_guide.PLAYBOOK_LEVERS["line-assignment-probe"]
        self.assertEqual(levers[:2], (23, 25))
        self.assertIn(4, levers)
        self.assertIn(23, field_guide.PLAYBOOK_LEVERS["g0-schedule-probe"])

    def test_lever_25_follows_lever_23_on_the_line_assignment_playbook(self) -> None:
        # 23 says the residue is line numbers; 25 is what you reach for when the
        # number you need is unreachable one statement per physical line. The
        # order is the point, so assert adjacency rather than membership.
        levers = field_guide.PLAYBOOK_LEVERS["line-assignment-probe"]
        self.assertEqual(levers[levers.index(23) + 1], 25)
        self.assertIn(25, field_guide.LEVER_ACTIONS)
        self.assertIn("LOGICAL", field_guide.LEVER_ACTIONS[25])
        self.assertIn(25, field_guide.sections())

    def test_the_playbook_offers_both_branches(self) -> None:
        steps = field_guide.PLAYBOOK_ONRAMPS["line-assignment-probe"]
        self.assertTrue(steps[0].startswith("no acpp"))
        self.assertTrue(any(step.startswith("have IDO") for step in steps))

    def test_the_guide_command_prints_the_new_section(self) -> None:
        status, stdout, _ = run_cli(
            ["guide", "line-assignment-probe", "--pager", "never"]
        )
        self.assertEqual(status, 0)
        self.assertIn("### 23.", stdout)
        self.assertIn("drawbitmap", stdout)
        self.assertIn("59", stdout)

    def test_lever_3_points_forward_to_lever_23(self) -> None:
        """The dead end this whole change exists to remove."""

        body = "\n".join(field_guide.sections()[3].lines)
        self.assertIn("already `-g0`", body)
        self.assertIn("lever 23", body)


if __name__ == "__main__":
    unittest.main()
