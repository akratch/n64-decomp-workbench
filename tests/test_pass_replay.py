"""Tests for retained-listing mutation and pass command rendering."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from decomp_workbench.pass_replay import (
    ListingEdit,
    apply_listing_edits,
    replay_as1,
    render_stage_command,
)


LISTING = """\
\tsw\t$2,0($16)
\t.noalias\t$17,$sp
\tlh\t$10,0($17)
\tbeq\t$10,-1,$1128
"""


class PassReplayTests(unittest.TestCase):
    def test_inserts_directive_before_unique_site(self) -> None:
        result = apply_listing_edits(
            LISTING,
            [
                ListingEdit(
                    position="before",
                    pattern=r"^\tlh\t\$10,0\(\$17\)$",
                    text="\t.noalias\t$17,$16",
                )
            ],
        )
        self.assertIn(
            "\t.noalias\t$17,$16\n\tlh\t$10,0($17)",
            result,
        )

    def test_refuses_ambiguous_pattern(self) -> None:
        with self.assertRaisesRegex(ValueError, "matched 2 times"):
            apply_listing_edits(
                "same\nsame\n",
                [
                    ListingEdit(
                        position="before", pattern="^same$", text="new"
                    )
                ],
            )

    def test_renders_as0_command(self) -> None:
        command = render_stage_command(
            "as0 -G 0 {listing} -o {binasm} -t {symtab}",
            listing=Path("/tmp/replay.s"),
            binasm=Path("/tmp/replay.G"),
            symtab=Path("/tmp/replay.T"),
            output=Path("/tmp/replay.o"),
            stage="as0",
        )
        self.assertEqual(command[0], "as0")
        self.assertIn("/tmp/replay.s", command)
        self.assertIn("/tmp/replay.G", command)

    def test_requires_stage_placeholders(self) -> None:
        with self.assertRaisesRegex(ValueError, r"\{object\}"):
            render_stage_command(
                "as1 {binasm}",
                listing=Path("replay.s"),
                binasm=Path("replay.G"),
                symtab=Path("replay.T"),
                output=Path("replay.o"),
                stage="as1",
            )

    def test_refuses_listing_as_object_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            listing = Path(temp) / "unit.s"
            listing.write_text("nop\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different paths"):
                replay_as1(
                    listing,
                    listing,
                    as0_template="as0 {listing} -o {binasm}",
                    as1_template="as1 {binasm} -o {object}",
                )


if __name__ == "__main__":
    unittest.main()
