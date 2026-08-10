"""What a donor costs, and which slot is really one variable.

One campaign spent a full sweep answering "how many rows touch this donor's
stack slot" by construction. It is a census over the object's own rows, and it
closed a competing brief's route in thirty seconds once somebody wrote the ten
lines. The two facts a screen line could not carry are here: the split between
loads and stores at each offset, and whether more than one access width
reaches it — which is a pun, and the allocator keys webs on storage.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from unittest import mock

from mips_asm import assemble

from decomp_workbench.cli import main
from decomp_workbench.csource import CSourceError
from decomp_workbench.model import Instruction
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.slots import slot_report, volatile_probe_sources

SYMBOL = "demo"
BODY = [
    "addiu sp,sp,-1704",
    "sw ra,28(sp)",
    "swc1 f0,1184(sp)",
    "lwc1 f4,1184(sp)",
    "lwc1 f6,1184(sp)",
    "sw t0,64(sp)",
    "lw t1,64(sp)",
    "lh t2,64(sp)",
    "addiu a0,sp,96",
    "lw ra,28(sp)",
    "jr ra",
    "addiu sp,sp,1704",
]

SOURCE = """\
void demo(void) {
    f32 sp4A0;
    struct beam *beam_local;
    s32 i;

    sp4A0 = 0.0f;
    for (i = 0; i < 4; i++) {
        step(sp4A0);
    }
}
"""


def rows(lines: list[str]) -> list[Instruction]:
    return parse_disassembly(assemble(lines, symbol=SYMBOL), symbol=SYMBOL)


def fake_dump(text: str) -> Callable[..., tuple[str, list[Instruction]]]:
    def _dump(
        path: str | Path,
        *,
        objdump: str | None = None,
        symbol: str | None = None,
        section: str = ".text",
    ) -> tuple[str, list[Instruction]]:
        return text, parse_disassembly(text, symbol=symbol)

    return _dump


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class SlotReportTests(unittest.TestCase):
    def report(self) -> dict[str, Any]:
        return slot_report(rows(BODY), label="demo.o")

    def test_loads_and_stores_are_counted_apart(self) -> None:
        entries = {item["offset"]: item for item in self.report()["slots"]}

        self.assertEqual((entries[1184]["loads"], entries[1184]["stores"]), (2, 1))
        self.assertEqual(entries[1184]["total"], 3)

    def test_two_widths_at_one_offset_is_named_a_pun(self) -> None:
        entries = {item["offset"]: item for item in self.report()["slots"]}

        self.assertTrue(entries[64]["punned"])
        self.assertEqual(entries[64]["widths"], [2, 4])
        self.assertFalse(entries[1184]["punned"])

    def test_an_address_take_is_a_slot_but_not_a_touch(self) -> None:
        entries = {item["offset"]: item for item in self.report()["slots"]}

        self.assertEqual(entries[96]["address_taken"], 1)
        self.assertEqual(entries[96]["total"], 0)

    def test_the_frame_itself_is_not_a_slot(self) -> None:
        """`addiu sp,sp,-1704` is the frame; counting it put it first."""

        offsets = [item["offset"] for item in self.report()["slots"]]

        self.assertNotIn(-1704, offsets)
        self.assertNotIn(1704, offsets)

    def test_the_cheapest_list_ranks_only_slots_that_are_touched(self) -> None:
        cheapest = self.report()["cheapest"]

        self.assertTrue(all(item["total"] > 0 for item in cheapest))
        self.assertEqual(cheapest[0]["total"], min(item["total"] for item in cheapest))

    def test_each_slot_carries_the_frame_offset_the_trace_keys_it_by(self) -> None:
        """`slots` says 1184; the cascade wants 0xfffffdf8. Same storage.

        The two commands are the two halves of one question -- what does this
        site cost, and why did the allocator do that to it -- and the campaign
        that needed both had to convert by hand, with the frame size coming
        from a third command.
        """

        report = self.report()
        slots = cast(list[dict[str, Any]], report["slots"])
        cheapest = cast(list[dict[str, Any]], report["cheapest"])
        self.assertEqual(report["frame"], -1704)
        entries = {item["offset"]: item for item in slots}
        self.assertEqual(entries[1184]["frame_offset"], -520)
        self.assertEqual(entries[1184]["frame_offset"] & 0xFFFFFFFF, 0xFFFFFDF8)
        for item in cheapest:
            self.assertIn("frame_offset", item)

    def test_a_row_range_narrows_the_census(self) -> None:
        narrowed = slot_report(rows(BODY), label="demo.o", rows=(1, 3))

        offsets = [item["offset"] for item in narrowed["slots"]]
        self.assertIn(28, offsets)
        self.assertNotIn(64, offsets)


class VolatileProbeTests(unittest.TestCase):
    def test_one_variant_per_local_with_the_declaration_volatile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "work.c"
            source.write_text(SOURCE, encoding="utf-8")
            report = volatile_probe_sources(source, directory=Path(directory) / "v")
            names = {item["variable"] for item in report["variants"]}
            first = Path(report["variants"][0]["path"]).read_text(encoding="utf-8")

        self.assertEqual(names, {"sp4A0", "beam_local", "i"})
        self.assertIn("volatile f32 sp4A0;", first)
        # Only the one declaration changes.
        self.assertEqual(len(first.splitlines()), len(SOURCE.splitlines()))

    def test_a_pointer_declaration_keeps_its_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "work.c"
            source.write_text(SOURCE, encoding="utf-8")
            report = volatile_probe_sources(
                source, directory=Path(directory) / "v", variables=("beam_local",)
            )
            text = Path(report["variants"][0]["path"]).read_text(encoding="utf-8")

        self.assertEqual(report["count"], 1)
        self.assertIn("volatile struct beam *beam_local;", text)

    def test_an_unknown_variable_is_an_error_that_names_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "work.c"
            source.write_text(SOURCE, encoding="utf-8")
            with self.assertRaises(CSourceError) as caught:
                volatile_probe_sources(
                    source, directory=Path(directory) / "v", variables=("nosuch",)
                )

        self.assertIn("nosuch", str(caught.exception))


class SlotsCommandTests(unittest.TestCase):
    def test_the_command_prints_the_table_and_the_pun_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "demo.o"
            target.write_bytes(b"\x7fELF placeholder")
            with mock.patch(
                "decomp_workbench.row_source.dump_object",
                fake_dump(assemble(BODY, symbol=SYMBOL)),
            ):
                status, out, _ = run_cli(["slots", str(target)])

        self.assertEqual(status, 0)
        self.assertIn("stack slots:", out)
        self.assertIn("PUN", out)
        self.assertIn("cheapest slots to disturb:", out)
        self.assertIn("does not say which C local lives at a slot", out)
        # The site the reader will paste into `trace-cascade`, spelled the
        # way that command's own option accepts it.
        self.assertIn("frame=-1704", out)
        self.assertIn("0xfffffdf8", out)
        self.assertIn("--frame-offset", out)

    def test_the_volatile_probe_needs_a_source_and_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "demo.o"
            target.write_bytes(b"\x7fELF placeholder")
            with mock.patch(
                "decomp_workbench.row_source.dump_object",
                fake_dump(assemble(BODY, symbol=SYMBOL)),
            ):
                status, _, err = run_cli(
                    ["slots", str(target), "--volatile-probe", str(target.parent / "v")]
                )

        self.assertEqual(status, 2)
        self.assertIn("--volatile-probe needs --source", err)

    def test_json_carries_the_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "demo.o"
            target.write_bytes(b"\x7fELF placeholder")
            with mock.patch(
                "decomp_workbench.row_source.dump_object",
                fake_dump(assemble(BODY, symbol=SYMBOL)),
            ):
                status, out, _ = run_cli(["slots", str(target), "--json"])

        self.assertEqual(status, 0)
        payload = json.loads(out)
        self.assertEqual(payload["schema"], "decomp-workbench-stack-slots-v1")
        self.assertTrue(payload["slots"])

    def test_an_unreadable_object_is_refused_rather_than_traced_back(self) -> None:
        """A failed objdump must reach the user as a refusal, not a traceback.

        Every sibling census (`align`, `phase`, `score`, `view`) answers an
        unreadable object with `error:` and exit 2. This one caught only
        OSError and ValueError, so the RuntimeError objdump raises escaped the
        handler and printed a stack trace with the real message at the bottom.
        """

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "demo.o"
            target.write_bytes(b"not an object at all")

            def refuse(*_args: object, **_kwargs: object) -> None:
                raise RuntimeError(
                    f"objdump failed for {target}: this does not look like a "
                    "compiled MIPS ELF object"
                )

            with mock.patch("decomp_workbench.row_source.dump_object", refuse):
                status, _, err = run_cli(["slots", str(target)])

        self.assertEqual(status, 2)
        self.assertTrue(err.startswith("error: objdump failed for"), err)
        self.assertNotIn("Traceback", err)

    def test_the_grouped_spelling_reaches_the_same_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "demo.o"
            target.write_bytes(b"\x7fELF placeholder")
            with mock.patch(
                "decomp_workbench.row_source.dump_object",
                fake_dump(assemble(BODY, symbol=SYMBOL)),
            ):
                status, out, _ = run_cli(["object", "slots", str(target)])

        self.assertEqual(status, 0)
        self.assertIn("stack slots:", out)


if __name__ == "__main__":
    unittest.main()
