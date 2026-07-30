"""How the evidence is presented, and what presentation may never cost.

The alignment decides *what* is true; this file is about the layer that decides
what a reader actually sees of it. Five comprehension defects are pinned here,
each of which let a correct analysis read as a different one:

* the exported HTML dropped lanes, hunks, webs, and every substitution
  annotation into a collapsed JSON blob, so "the same evidence" was not;
* the verdict rendered plain while a downstream sentence rendered bold red;
* `--width` silently cut a row's second web tag, which is a verdict
  suppressing its own evidence;
* a context row's substitution printed as a bare `register` even when a named
  web already explained it;
* one caret line spelled two different units as though they were a pair.

The last class holds the properties that must survive every future change to
this layer.
"""

from __future__ import annotations

import contextlib
import io
import re
import tempfile
import unittest
from pathlib import Path

from mips_asm import assemble

from decomp_workbench.cli import main
from decomp_workbench.html_report import render_diagnosis_html
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.terminal import Painter, visible_length
from decomp_workbench.view import MechanismView, build_view
from decomp_workbench.view_cli import render_view

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "examples" / "fixtures"
PHASE_TARGET = str(FIXTURES / "phase-shift-target.objdump")
PHASE_CANDIDATE = str(FIXTURES / "phase-shift-candidate.objdump")
SHIFT_TARGET = str(FIXTURES / "shifted-insertion-target.objdump")
SHIFT_CANDIDATE = str(FIXTURES / "shifted-insertion-candidate.objdump")

SYMBOL = "demo"
PROLOGUE = ["addiu sp,sp,-32", "sw ra,28(sp)"]
EPILOGUE = ["lw ra,28(sp)", "jr ra", "addiu sp,sp,32"]


def body(*instructions: str) -> list[str]:
    return [*PROLOGUE, *instructions, *EPILOGUE]


def view_of(target: list[str], candidate: list[str]) -> MechanismView:
    return build_view(
        parse_disassembly(assemble(target, symbol=SYMBOL), symbol=SYMBOL),
        parse_disassembly(assemble(candidate, symbol=SYMBOL), symbol=SYMBOL),
        target_name="target",
        candidate_name="candidate",
        symbol=SYMBOL,
    )


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


def phase_view() -> MechanismView:
    """The documented four-web phase shift, built straight from the fixture."""

    return build_view(
        parse_disassembly(
            Path(PHASE_TARGET).read_text(encoding="utf-8"), symbol="animStep"
        ),
        parse_disassembly(
            Path(PHASE_CANDIDATE).read_text(encoding="utf-8"), symbol="animStep"
        ),
        target_name="target.objdump",
        candidate_name="candidate.objdump",
        symbol="animStep",
    )


class HtmlParityTests(unittest.TestCase):
    """The export claims to preserve the screen's evidence. Hold it to that."""

    document: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls.document = render_diagnosis_html(phase_view())

    def test_every_hunk_is_its_own_linkable_section(self) -> None:
        self.assertIn('<section class="hunk" id="hunk-1">', self.document)
        self.assertIn('<h3><a href="#hunk-1">Hunk 1</a></h3>', self.document)

    def test_rows_carry_context_and_divergence_classes(self) -> None:
        self.assertIn('<tr class="diverge">', self.document)
        self.assertIn('<tr class="context">', self.document)

    def test_substitution_annotations_are_a_real_cell(self) -> None:
        """`t7->t8 [w1]` existed only inside the collapsed JSON blob."""

        self.assertIn("t7-&gt;t8 [w1]", self.document)
        self.assertIn('href="#web-1"', self.document)
        self.assertIn('class="swatch"', self.document)

    def test_webs_are_a_section_that_links_to_its_hunks(self) -> None:
        self.assertIn('<tr id="web-1">', self.document)
        self.assertIn("<h2>Webs</h2>", self.document)
        self.assertIn('<a href="#hunk-1">hunk 1</a>', self.document)

    def test_lanes_are_rendered_with_the_divergence_marked(self) -> None:
        self.assertIn("<h2>Register lanes</h2>", self.document)
        self.assertIn('class="slot-diverge"', self.document)
        self.assertIn("slot=5 aligned_row=12 rotation=+1", self.document)

    def test_the_verdict_area_is_sticky(self) -> None:
        self.assertIn('class="verdict-bar"', self.document)
        self.assertIn("position: sticky", self.document)

    def test_the_machine_readable_blob_is_still_there(self) -> None:
        self.assertIn("Machine-readable evidence", self.document)
        self.assertIn('<pre id="report">', self.document)

    def test_the_page_is_self_contained_and_needs_no_script(self) -> None:
        self.assertNotIn("<script", self.document)
        self.assertEqual(re.findall(r'(?:src|href)="https?:', self.document), [])

    def test_cheap_semantics_are_present(self) -> None:
        self.assertIn('scope="col"', self.document)
        self.assertIn('scope="row"', self.document)
        self.assertIn('<html lang="en">', self.document)

    def test_the_identity_chip_never_claims_to_be_the_site_score(self) -> None:
        self.assertIn("aligned identical 18/24", self.document)
        self.assertIn("not decomp.me", self.document)

    def test_an_input_warning_survives_the_export(self) -> None:
        view = build_view(
            parse_disassembly(assemble(body("lw t8,0(s0)"), symbol=SYMBOL)),
            parse_disassembly(assemble(body("lw t6,0(s0)"), symbol=SYMBOL)),
            target_name="a",
            candidate_name="b",
            warnings=("target defines 'x' but candidate defines 'y'",),
        )
        document = render_diagnosis_html(view)
        self.assertIn('class="warning"', document)
        self.assertIn("candidate defines &#x27;y&#x27;", document)

    def test_the_command_still_writes_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "report.html"
            status, _, _ = run_cli(
                [
                    "diagnose-dumps",
                    PHASE_TARGET,
                    PHASE_CANDIDATE,
                    "--function",
                    "animStep",
                    "--html",
                    str(output),
                    "--pager",
                    "never",
                ]
            )
            self.assertEqual(status, 0)
            self.assertIn('id="hunk-1"', output.read_text(encoding="utf-8"))


class VerdictColorTests(unittest.TestCase):
    def test_the_verdict_is_the_emphasized_token(self) -> None:
        status, stdout, _ = run_cli(
            [
                "compare-dumps",
                PHASE_TARGET,
                PHASE_CANDIDATE,
                "--function",
                "animStep",
                "--color",
                "always",
            ]
        )
        self.assertEqual(status, 0)
        # bold key, then the family colour on the value
        self.assertIn("\033[1mverdict=\033[0m", stdout)
        self.assertIn("\033[1;31mallocation-mismatch\033[0m", stdout)

    def test_each_family_gets_its_own_hue(self) -> None:
        painter = Painter(True)
        seen = {
            painter.verdict(name)
            for name in ("exact", "constant", "schedule", "structure", "allocation")
        }
        self.assertEqual(len(seen), 5)

    def test_an_unknown_verdict_still_renders(self) -> None:
        painter = Painter(True)
        mixed = "mixed(register:2, constant:1)"
        self.assertIn(mixed, painter.verdict(mixed))

    def test_compare_commands_can_be_colorized_at_all(self) -> None:
        """Batch triage was the one journey that could never colourize."""

        import argparse

        from decomp_workbench.cli import build_parser

        parser = build_parser()
        subparsers = next(
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        for command in ("compare", "compare-dumps", "rank", "diagnose", "view"):
            with self.subTest(command=command):
                options = {
                    option
                    for action in subparsers.choices[command]._actions
                    for option in action.option_strings
                }
                self.assertIn("--color", options)

    def test_no_color_is_respected(self) -> None:
        _, plain, _ = run_cli(
            [
                "compare-dumps",
                PHASE_TARGET,
                PHASE_CANDIDATE,
                "--function",
                "animStep",
                "--color",
                "never",
            ]
        )
        self.assertNotIn("\033[", plain)


class WidthNeverSuppressesEvidenceTests(unittest.TestCase):
    def test_a_narrow_width_wraps_the_annotation_instead_of_cutting_it(self) -> None:
        """Row 13 carries two webs; at 60 columns one used to disappear."""

        status, stdout, _ = run_cli(
            [
                "view-dumps",
                PHASE_TARGET,
                PHASE_CANDIDATE,
                "--function",
                "animStep",
                "--pager",
                "never",
                "--width",
                "60",
            ]
        )
        self.assertEqual(status, 0)
        hunk = stdout.split("HUNK 1")[1].split("WEBS")[0]
        # The hunk's own metadata line may be cut; a row of evidence may not.
        rows = [line for line in hunk.splitlines() if "|" in line or "[w" in line]
        self.assertNotIn("…", "\n".join(rows))
        for label in ("t7->t8 [w1]", "t8->t9 [w2]", "t9->t6 [w3]", "t6->t7 [w4]"):
            self.assertIn(label, stdout)

    def test_every_wrapped_line_still_fits_the_budget(self) -> None:
        view = phase_view()
        for line in render_view(view, width=60):
            with self.subTest(line=line):
                if "[w" in line:
                    self.assertLessEqual(visible_length(line), 60)

    def test_an_unlimited_width_keeps_the_annotation_inline(self) -> None:
        screen = "\n".join(render_view(phase_view(), width=0))
        self.assertIn("lw $t8,20($t7)    | lw $t9,20($t8)     t8->t9 [w2]", screen)


class ContextRowAnnotationTests(unittest.TestCase):
    def test_a_context_row_in_a_known_web_names_the_web(self) -> None:
        """A bare `register` beside explained rows reads as an unexplained site."""

        target = body(
            "lw t8,0(s0)",
            "addu t1,t1,t1",
            "lw t8,4(s0)",
            "addu t2,t2,t2",
            "lw t8,8(s0)",
        )
        candidate = body(
            "lw t6,0(s0)",
            "addu t1,t1,t1",
            "lw t6,4(s0)",
            "addu t2,t2,t2",
            "lw t6,8(s0)",
        )
        screen = "\n".join(render_view(view_of(target, candidate), max_hunks=1))
        annotated = [line for line in screen.splitlines() if "t8->t6" in line]
        self.assertGreaterEqual(len(annotated), 2)
        self.assertNotIn("  register\n", screen)
        # the `>` marker, not the annotation, separates this hunk from context
        self.assertTrue(any(" > " in line for line in annotated))
        self.assertTrue(any(" > " not in line for line in annotated))


class LaneUnitTests(unittest.TestCase):
    def test_the_caret_names_both_units(self) -> None:
        _, stdout, _ = run_cli(
            [
                "view-dumps",
                PHASE_TARGET,
                PHASE_CANDIDATE,
                "--function",
                "animStep",
                "--pager",
                "never",
            ]
        )
        self.assertIn("slot=5 aligned_row=12 rotation=+1", stdout)
        self.assertNotIn("divergence=5", stdout)
        self.assertNotIn("index=12", stdout)


class MustNotBreakTests(unittest.TestCase):
    """Properties the presentation layer is not allowed to cost us."""

    def test_a_shifted_insertion_stays_one_structural_row(self) -> None:
        """Positional diffing multiplied this into phantom register hunks."""

        status, stdout, _ = run_cli(
            [
                "view-dumps",
                SHIFT_TARGET,
                SHIFT_CANDIDATE,
                "--pager",
                "never",
            ]
        )
        self.assertEqual(status, 0)
        self.assertIn("structural=1", stdout)
        self.assertIn("register=0", stdout)
        self.assertIn("hunks=1", stdout)

    def test_webs_print_in_full_under_hunk_truncation(self) -> None:
        """The bijection is the conclusion; a display limit may not shorten it."""

        target = body(*[f"lw t8,{index * 4}(s0)" for index in range(6)])
        candidate = body(*[f"lw t6,{index * 4}(s0)" for index in range(6)])
        for index in (1, 3, 5):
            candidate[len(PROLOGUE) + index] = target[len(PROLOGUE) + index]
        view = view_of(target, candidate)
        screen = "\n".join(render_view(view, max_hunks=1))
        self.assertIn("further hunk(s) not shown", screen)
        self.assertNotIn("HUNK 2", screen)
        web = view.webs[0]
        self.assertIn(f"count={web.count}", screen)
        for row in web.rows:
            self.assertIn(str(row), screen.split("WEBS")[1])

    def test_the_caret_lands_under_the_first_divergent_slot(self) -> None:
        screen = render_view(phase_view())
        candidate_line = next(
            line for line in screen if line.lstrip().startswith("candidate  t6 t7")
        )
        caret_line = next(line for line in screen if "^ slot=5" in line)
        # The sixth cell of the candidate lane is slot 5, the first divergence.
        cells = candidate_line.split("candidate  ", 1)[1]
        offset = candidate_line.index("candidate  ") + len("candidate  ")
        slot_five = offset + sum(len(cell) + 1 for cell in cells.split()[:5])
        self.assertEqual(caret_line.index("^"), slot_five)

    def test_monochrome_keeps_every_label(self) -> None:
        view = phase_view()
        monochrome = "\n".join(render_view(view, painter=Painter(False)))
        colored = "\n".join(render_view(view, painter=Painter(True)))
        self.assertNotIn("\033[", monochrome)
        for label in ("[w1]", "[w2]", "[w3]", "[w4]"):
            self.assertIn(label, monochrome)
            self.assertIn(label, colored)

    def test_one_web_keeps_one_color_everywhere_it_appears(self) -> None:
        colored = "\n".join(render_view(phase_view(), painter=Painter(True)))
        first = re.search(r"\033\[(\d+)m[^\033]*t7->t8 \[w1\]", colored)
        assert first is not None
        summary = re.search(r"\033\[(\d+)mw1 t7->t8", colored)
        assert summary is not None
        self.assertEqual(first.group(1), summary.group(1))

    def test_painted_registers_do_not_break_column_alignment(self) -> None:
        """Colour is added inside the cells; the `|` must stay in one column."""

        colored = render_view(phase_view(), painter=Painter(True))
        columns = {
            visible_length(line.split("|", 1)[0])
            for line in colored
            if re.match(r"^\s+\d+ [ >] ", line) and "|" in line
        }
        self.assertEqual(len(columns), 1)


if __name__ == "__main__":
    unittest.main()
