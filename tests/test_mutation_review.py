"""A sweep winner that scores well is not therefore the same program.

Derived from the recorded `object_interaction` campaign's local-substitution
sweep. It grouped one local's occurrences by line proximity and renamed a whole
group, which produced two shapes that compile, score, and are not valid C
transformations of the baseline:

* a group holding only *reads* -- the definitions were 130 lines earlier --
  became a read of an uninitialised variable, and outscored its baseline;
* the top-scoring row renamed a local's *first* store and left a later
  conditional store and two reads behind, so a path can now reach a read
  without passing a write.

Nothing downstream catches either one. The comparator answers "are these the
same object", never "are these the same program", so the second question has to
be asked before adoption or not at all.

The command under test is a review surface and the tests hold it to exactly
that claim: it flags the two named shapes, it stays quiet on the campaign's
real adopted edits, and it never reports that a variant is valid.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from decomp_workbench.cli import main
from decomp_workbench.composition import review_mutation

#: A local written once and read twice, a local that is declared and never
#: used, and a loop counter. Between them they carry every case below.
BASELINE = """\
void demo(s32 arg0) {
    f32 sp4A0;
    f32 dead;
    s32 count;

    sp4A0 = compute(arg0);
    count = 0;
    while (count < 4) {
        count += 1;
    }
    use(sp4A0);
    use(sp4A0 + 1.0f);
}
"""


class ReviewTests(unittest.TestCase):
    def review(self, variant: str, baseline: str = BASELINE) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "base.c").write_text(baseline, encoding="utf-8")
            (root / "variant.c").write_text(variant, encoding="utf-8")
            return review_mutation(root / "base.c", root / "variant.c")

    def codes(self, report: dict[str, Any]) -> set[str]:
        return {str(item["code"]) for item in report["findings"]}


class InvalidShapeTests(ReviewTests):
    """The two recorded failures, as findings."""

    def test_a_read_group_rehosted_on_a_dead_local_is_an_error(self) -> None:
        report = self.review(BASELINE.replace("use(sp4A0)", "use(dead)"))

        self.assertIn("read-before-definition", self.codes(report))
        self.assertEqual(report["errors"], 1)
        self.assertFalse(report["reviewed"])
        finding = next(
            item
            for item in report["findings"]
            if item["code"] == "read-before-definition"
        )
        self.assertEqual(finding["identifier"], "dead")
        self.assertIn("never used it", finding["message"])

    def test_deleting_the_only_write_before_a_read_is_an_error(self) -> None:
        report = self.review(BASELINE.replace("    count = 0;\n", ""))

        self.assertIn("definition-removed", self.codes(report))
        self.assertEqual(
            [item["identifier"] for item in report["findings"] if item["line"]],
            ["count"],
        )

    def test_deleting_one_of_several_writes_is_a_warning_not_a_claim(self) -> None:
        """The top-scoring recorded row: a first store renamed away.

        Text cannot say whether a path reaches the surviving reads without
        passing the surviving write -- that is a control-flow question and this
        module builds no control-flow graph. Saying so, and still surfacing the
        deleted write, is the whole contribution.
        """

        baseline = BASELINE.replace(
            "    use(sp4A0);",
            "    if (arg0) {\n        sp4A0 = 2.0f;\n    }\n    use(sp4A0);",
        )
        report = self.review(
            baseline.replace("sp4A0 = compute(arg0);", "dead = compute(arg0);"),
            baseline=baseline,
        )

        self.assertIn("write-removed", self.codes(report))
        finding = next(
            item for item in report["findings"] if item["code"] == "write-removed"
        )
        self.assertEqual(finding["severity"], "warning")
        self.assertEqual(finding["identifier"], "sp4A0")
        self.assertIn("control-flow question", finding["message"])
        self.assertEqual(report["errors"], 0)


class SilenceTests(ReviewTests):
    """What must not be reported, which is most of what a sweep produces."""

    def test_a_pure_rename_of_a_whole_local_is_clean(self) -> None:
        report = self.review(BASELINE.replace("sp4A0", "spare"))

        self.assertEqual(report["findings"], [])
        self.assertTrue(report["reviewed"])
        self.assertEqual(report["identifiers_introduced"], ["spare"])
        self.assertEqual(report["identifiers_withdrawn"], ["sp4A0"])

    def test_an_unchanged_variant_reports_nothing(self) -> None:
        report = self.review(BASELINE)

        self.assertEqual(report["findings"], [])
        self.assertEqual(report["changed_lines_added"], 0)
        self.assertEqual(report["changed_lines_removed"], 0)

    def test_an_external_call_is_not_an_undefined_local(self) -> None:
        """Only identifiers this file declares are candidates.

        A project global and a call to an external function are both names with
        no visible write. Reporting them would bury the finding that matters
        under one row per callee.
        """

        report = self.review(BASELINE.replace("use(sp4A0);", "publish(sp4A0);"))

        self.assertEqual(report["findings"], [])

    def test_a_member_name_is_not_a_local(self) -> None:
        report = self.review(
            BASELINE.replace("use(sp4A0);", "use(arg0->count);"),
        )

        self.assertNotIn("read-before-definition", self.codes(report))

    def test_a_baseline_that_already_reads_early_is_not_this_mutations_doing(
        self,
    ) -> None:
        """The check reports a regression, never a property.

        Plenty of correct code reads a local textually above the branch that
        writes it. Only a shape the mutation introduced is reportable.
        """

        baseline = BASELINE.replace("    use(sp4A0);", "    use(dead);")
        report = self.review(
            baseline.replace("use(dead)", "use(dead + 0.0f)"), baseline
        )

        self.assertEqual(report["errors"], 0)


class ReportShapeTests(ReviewTests):
    def test_the_diff_is_part_of_the_report(self) -> None:
        report = self.review(BASELINE.replace("use(sp4A0)", "use(dead)"))

        self.assertTrue(any(line.startswith("-") for line in report["diff"]))
        self.assertTrue(any(line.startswith("+") for line in report["diff"]))

    def test_a_line_count_change_is_a_warning_to_read_the_diff(self) -> None:
        report = self.review(BASELINE.replace("    use(sp4A0);\n", ""))

        self.assertIn("statement-count-changed", self.codes(report))

    def test_the_report_never_claims_validity(self) -> None:
        report = self.review(BASELINE.replace("sp4A0", "spare"))

        self.assertIn("cannot certify", report["proof"])
        self.assertIn("justify every changed line", report["next_gate"])

    def test_a_negative_context_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "base.c").write_text(BASELINE, encoding="utf-8")
            (root / "variant.c").write_text(BASELINE, encoding="utf-8")
            with self.assertRaises(ValueError):
                review_mutation(root / "base.c", root / "variant.c", context=-1)


class CommandTests(unittest.TestCase):
    def run_cli(self, variant: str, *flags: str) -> tuple[int, dict[str, Any]]:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "base.c").write_text(BASELINE, encoding="utf-8")
            (root / "variant.c").write_text(variant, encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(
                    [
                        "experiment",
                        "review-mutation",
                        str(root / "base.c"),
                        str(root / "variant.c"),
                        *flags,
                    ]
                )
        return status, {"stdout": stdout.getvalue()}

    def test_an_invalid_shape_exits_one(self) -> None:
        status, output = self.run_cli(BASELINE.replace("use(sp4A0)", "use(dead)"))

        self.assertEqual(status, 1)
        self.assertIn("read-before-definition", output["stdout"])
        self.assertIn("--- ", output["stdout"])

    def test_a_clean_variant_exits_zero(self) -> None:
        status, output = self.run_cli(BASELINE.replace("sp4A0", "spare"))

        self.assertEqual(status, 0)
        self.assertIn("NO KNOWN INVALID SHAPE", output["stdout"])

    def test_a_warning_is_fatal_only_on_request(self) -> None:
        variant = BASELINE.replace("    use(sp4A0);\n", "")
        clean, _ = self.run_cli(variant)
        strict, _ = self.run_cli(variant, "--fail-on-warning")

        self.assertEqual(clean, 0)
        self.assertEqual(strict, 1)

    def test_json_carries_the_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "base.c").write_text(BASELINE, encoding="utf-8")
            (root / "variant.c").write_text(BASELINE, encoding="utf-8")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main(
                    [
                        "experiment",
                        "review-mutation",
                        str(root / "base.c"),
                        str(root / "variant.c"),
                        "--json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(payload["schema"], "decomp-workbench-mutation-review-v1")

    def test_a_missing_input_is_an_input_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "base.c").write_text(BASELINE, encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = main(
                    [
                        "experiment",
                        "review-mutation",
                        str(root / "base.c"),
                        str(root / "absent.c"),
                    ]
                )

        self.assertEqual(status, 2)
        self.assertIn("error:", stderr.getvalue())


class GuidanceTests(unittest.TestCase):
    """The rule has to be where an agent reads it, not only in a command."""

    def test_the_skill_states_the_adoption_rule(self) -> None:
        root = Path(__file__).resolve().parents[1]
        skill = (
            root / "src/decomp_workbench/skills/n64-decomp-campaign/SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertIn("never adopted on its score", skill)
        self.assertIn("experiment review-mutation", skill)

    def test_the_field_guide_states_the_adoption_rule(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "docs/field-guide.md",
            "src/decomp_workbench/docs/field-guide.md",
        ):
            with self.subTest(document=relative):
                guide = (root / relative).read_text(encoding="utf-8")
                self.assertIn("A sweep winner is a hypothesis, not an edit", guide)
                self.assertIn("experiment review-mutation", guide)


if __name__ == "__main__":
    unittest.main()
