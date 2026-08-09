"""The identity gate is recorded, and re-verified by re-running it.

One campaign ran this check by hand every time it built an instrument -- twelve
instruments across four passes -- and left no record that it had. A reader
arriving at one of those traces three stages later had a stage's sentence and
nothing to check.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import main
from decomp_workbench.instrument_gate import (
    GATE_SCHEMA,
    InstrumentGateError,
    build_stamp,
    gate_lines,
    verify_stamp,
    write_stamp,
)

OBJDUMP = """#!/usr/bin/env python3
import pathlib, sys
obj = pathlib.Path(sys.argv[-1])
different = b'different' in obj.read_bytes()
if '-s' in sys.argv:
 print('Contents of section:')
 print(' 0000 11223344' if not different else ' 0000 deadbeef')
elif '-r' in sys.argv:
 print('RELOCATION RECORDS FOR [.text]:')
 print('00000000 R_MIPS_26 helper')
elif '-t' in sys.argv:
 print('SYMBOL TABLE:')
 print('00000000 g F .text 00000008 demo')
"""


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class GateCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.objdump = self.root / "objdump"
        self.objdump.write_text(OBJDUMP, encoding="utf-8")
        self.objdump.chmod(0o755)
        self.stock = self.root / "stock.o"
        self.stock.write_bytes(b"stock object")
        self.instrumented = self.root / "cdx.o"
        # Same gated sections, different bytes: the ordinary passing case,
        # because stock IDO under -g3 is not file-level reproducible.
        self.instrumented.write_bytes(b"instrumented object")
        self.failing = self.root / "broken.o"
        self.failing.write_bytes(b"different object")

    def stamp(self, instrumented: Path | None = None) -> dict:
        return build_stamp(
            stock=self.stock,
            instrumented=instrumented or self.instrumented,
            profile="uopt-cdx",
            objdump=str(self.objdump),
        )


class StampTests(GateCase):
    def test_a_passing_gate_records_both_objects_and_its_claim(self) -> None:
        stamp = self.stamp()
        self.assertEqual(stamp["schema"], GATE_SCHEMA)
        self.assertTrue(stamp["pass"])
        self.assertEqual(stamp["profile"], "uopt-cdx")
        self.assertNotEqual(stamp["stock"]["sha256"], stamp["instrumented"]["sha256"])
        self.assertIn("says nothing about", stamp["claim"])

    def test_the_gate_is_section_scoped_and_says_so_when_files_differ(self) -> None:
        lines = "\n".join(gate_lines(self.stamp()))
        self.assertIn("instrument gate: PASS", lines)
        self.assertIn("not file-level reproducible", lines)

    def test_a_failing_gate_says_the_traces_are_not_evidence(self) -> None:
        stamp = self.stamp(self.failing)
        self.assertFalse(stamp["pass"])
        self.assertIn(
            "not evidence about the stock compiler", "\n".join(gate_lines(stamp))
        )

    def test_a_stamp_with_no_profile_cannot_be_looked_up(self) -> None:
        with self.assertRaises(InstrumentGateError) as raised:
            build_stamp(
                stock=self.stock,
                instrumented=self.instrumented,
                profile="  ",
                objdump=str(self.objdump),
            )
        self.assertIn("--profile names which instrumented pass", str(raised.exception))

    def test_a_missing_object_says_the_workbench_does_not_build_compilers(
        self,
    ) -> None:
        with self.assertRaises(InstrumentGateError) as raised:
            build_stamp(
                stock=self.root / "nowhere.o",
                instrumented=self.instrumented,
                profile="uopt-cdx",
                objdump=str(self.objdump),
            )
        self.assertIn("does not build", str(raised.exception))

    def test_a_stamp_is_never_written_into_a_directory_nobody_named(self) -> None:
        with self.assertRaises(InstrumentGateError) as raised:
            write_stamp(self.stamp(), path=self.root / "gates" / "uopt.json")
        self.assertIn("does not exist", str(raised.exception))


class VerifyTests(GateCase):
    def written(self) -> Path:
        return write_stamp(self.stamp(), path=self.root / "uopt-cdx.json")

    def test_a_rerun_that_agrees_passes(self) -> None:
        result = verify_stamp(self.written(), objdump=str(self.objdump))
        self.assertEqual(result["verification"], "AGREES")
        self.assertTrue(result["pass"])

    def test_an_object_that_changed_underneath_the_stamp_is_stale(self) -> None:
        """The record describes what was on disk, not what is."""

        path = self.written()
        self.instrumented.write_bytes(b"different object")
        result = verify_stamp(path, objdump=str(self.objdump))
        self.assertEqual(result["verification"], "STALE")
        self.assertFalse(result["pass"])
        self.assertIn("has changed since the stamp", result["findings"][0])

    def test_an_object_that_is_gone_is_stale_and_named(self) -> None:
        path = self.written()
        self.stock.unlink()
        result = verify_stamp(path, objdump=str(self.objdump))
        self.assertEqual(result["verification"], "STALE")
        self.assertIn("is gone", result["findings"][0])

    def test_a_stamp_of_another_schema_is_refused(self) -> None:
        path = self.root / "other.json"
        path.write_text(json.dumps({"schema": "something-else"}), encoding="utf-8")
        with self.assertRaises(InstrumentGateError) as raised:
            verify_stamp(path)
        self.assertIn(GATE_SCHEMA, str(raised.exception))


class GateCliTests(GateCase):
    def test_the_command_stamps_and_names_the_file(self) -> None:
        target = self.root / "uopt-cdx.json"
        status, stdout, stderr = run_cli(
            [
                "instrument",
                "gate",
                "--stock",
                str(self.stock),
                "--instrumented",
                str(self.instrumented),
                "--profile",
                "uopt-cdx",
                "--stamp",
                str(target),
                "--objdump",
                str(self.objdump),
            ]
        )
        self.assertEqual(status, 0, stderr)
        self.assertIn(f"stamped: {target}", stdout)
        self.assertTrue(target.is_file())

    def test_a_failing_gate_exits_one_so_a_script_can_stop(self) -> None:
        status, stdout, _ = run_cli(
            [
                "instrument",
                "gate",
                "--stock",
                str(self.stock),
                "--instrumented",
                str(self.failing),
                "--profile",
                "uopt-cdx",
                "--objdump",
                str(self.objdump),
            ]
        )
        self.assertEqual(status, 1)
        self.assertIn("instrument gate: FAIL", stdout)

    def test_neither_pair_nor_stamp_explains_both_spellings(self) -> None:
        status, _stdout, stderr = run_cli(["instrument", "gate"])
        self.assertEqual(status, 2)
        self.assertIn("--stock OBJ --instrumented OBJ", stderr)
        self.assertIn("--verify STAMP", stderr)

    def test_verify_reports_json_under_its_schema(self) -> None:
        target = write_stamp(self.stamp(), path=self.root / "uopt-cdx.json")
        status, stdout, _ = run_cli(
            [
                "instrument",
                "gate",
                "--verify",
                str(target),
                "--objdump",
                str(self.objdump),
                "--json",
            ]
        )
        self.assertEqual(status, 0)
        payload = json.loads(stdout)
        self.assertEqual(payload["schema"], GATE_SCHEMA)
        self.assertEqual(payload["verification"], "AGREES")


if __name__ == "__main__":
    unittest.main()
