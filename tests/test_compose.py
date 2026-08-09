"""The composer refuses, or it lands where it was aimed.

Every case here is a shape a real campaign composer got wrong. The weak ones
asserted the content of a few lines and nothing else, so a rebase that shifted
the file silently mis-edited it and produced a plausible, wrong candidate. The
strongest one checked its anchors by searching the whole emitted file, which a
coincidental duplicate string elsewhere satisfies.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from decomp_workbench.compose import (
    Anchor,
    ComposeError,
    Edit,
    EditPlan,
    apply_plan,
    parse_zone,
    source_sha256,
)

SOURCE = """void demo(void) {
    f32 lead;
    f32 span;

    lead = 1.0f;
    span = lead + 2.0f;
    tail(span);
}
"""


class ComposeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "work.c"
        self.path.write_text(SOURCE, encoding="utf-8")
        self.sha = source_sha256(self.path)

    def plan(self, **overrides: object) -> EditPlan:
        fields: dict[str, object] = {
            "base": self.path,
            "base_sha256": self.sha,
            "edits": (
                Edit(
                    line=5,
                    expect="    lead = 1.0f;",
                    replace="    lead = 3.0f;",
                ),
            ),
        }
        fields.update(overrides)
        return EditPlan(**fields)  # type: ignore[arg-type]

    def test_an_edit_lands_where_it_was_aimed(self) -> None:
        composed = apply_plan(self.plan())
        self.assertIn("lead = 3.0f;", composed.text)
        self.assertNotIn("lead = 1.0f;", composed.text)
        self.assertTrue(composed.text.endswith("\n"))

    def test_a_moved_base_is_refused_before_any_line_is_read(self) -> None:
        """The rebase case: every line number in the plan means nothing now."""

        self.path.write_text("/* rebased */\n" + SOURCE, encoding="utf-8")
        with self.assertRaises(ComposeError) as raised:
            apply_plan(self.plan())
        message = str(raised.exception)
        self.assertIn("not the base this plan was written against", message)
        self.assertIn(self.sha, message)

    def test_an_anchor_line_that_says_something_else_is_refused(self) -> None:
        with self.assertRaises(ComposeError) as raised:
            apply_plan(
                self.plan(
                    anchors=(Anchor(line=6, text="span = lead + 9.0f;", owner="B4S"),)
                )
            )
        message = str(raised.exception)
        self.assertIn("is not the anchor line", message)
        self.assertIn("B4S", message)

    def test_an_edit_inside_a_frozen_zone_is_refused_by_name(self) -> None:
        """Another stage's protected lines are not this composer's to edit."""

        with self.assertRaises(ComposeError) as raised:
            apply_plan(self.plan(frozen=((4, 6),), frozen_owner="the B4 supplier set"))
        message = str(raised.exception)
        self.assertIn("frozen zone 4..6", message)
        self.assertIn("the B4 supplier set", message)

    def test_an_anchor_is_re_read_at_its_own_line_not_anywhere(self) -> None:
        """The one weakness in the strongest campaign composer.

        Re-verifying an anchor by searching the whole emitted file is
        satisfied by a coincidental duplicate elsewhere. Here the edit
        replaces the anchor's own line with something else and inserts the
        anchor's text further down; a whole-file search would pass.
        """

        plan = self.plan(
            edits=(
                Edit(
                    line=5,
                    expect="    lead = 1.0f;",
                    replace="    lead = 4.0f;",
                ),
                Edit(
                    line=7,
                    expect="    tail(span);",
                    replace="    lead = 1.0f;",
                ),
            ),
            anchors=(Anchor(line=5, text="lead = 1.0f;"),),
        )
        with self.assertRaises(ComposeError) as raised:
            apply_plan(plan)
        self.assertIn("no longer reads", str(raised.exception))

    def test_two_edits_on_one_line_are_refused(self) -> None:
        plan = self.plan(
            edits=(
                Edit(line=5, expect="    lead = 1.0f;", replace="    lead = 2.0f;"),
                Edit(line=5, expect="    lead = 1.0f;", replace="    lead = 3.0f;"),
            )
        )
        with self.assertRaises(ComposeError) as raised:
            apply_plan(plan)
        self.assertIn("two edits target line 5", str(raised.exception))

    def test_an_insertion_keeps_the_line_it_was_aimed_before(self) -> None:
        composed = apply_plan(
            self.plan(
                edits=(
                    Edit(
                        line=6,
                        expect="    span = lead + 2.0f;",
                        insert=("    span = 0.0f;",),
                    ),
                ),
                anchors=(Anchor(line=6, text="span = lead + 2.0f;"),),
            )
        )
        lines = composed.text.splitlines()
        self.assertEqual(lines[5].strip(), "span = 0.0f;")
        self.assertEqual(lines[6].strip(), "span = lead + 2.0f;")
        self.assertEqual(composed.verified_anchors, (6,))

    def test_a_frozen_zone_outside_the_edit_survives_and_is_checked(self) -> None:
        composed = apply_plan(self.plan(frozen=((7, 7),)))
        self.assertIn("    tail(span);", composed.text)

    def test_an_edit_past_the_end_names_the_file_length(self) -> None:
        with self.assertRaises(ComposeError) as raised:
            apply_plan(
                self.plan(edits=(Edit(line=99, expect="anything"),))
            )
        self.assertIn("line(s); the edit", str(raised.exception))


class ZoneTests(unittest.TestCase):
    def test_a_zone_reads_both_spellings(self) -> None:
        self.assertEqual(parse_zone("10..20"), (10, 20))
        self.assertEqual(parse_zone(" 7 "), (7, 7))

    def test_a_backwards_zone_is_refused(self) -> None:
        with self.assertRaises(ComposeError):
            parse_zone("20..10")

    def test_a_zone_that_is_not_a_range_says_what_to_write(self) -> None:
        with self.assertRaises(ComposeError) as raised:
            parse_zone("the prologue")
        self.assertIn("write LO..HI", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
