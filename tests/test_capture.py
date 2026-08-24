"""Phase capture, run listing, and ugen replay against a synthetic toolchain.

The "compiler" here is two POSIX shell scripts that consume and produce the
same *shapes* IDO's phases do: ugen reads a stream and a symbol table, writes a
second stream, mutates the symbol table and touches a temporary; as1 reads that
stream plus the mutated symbol table and writes an object. That is enough to
exercise every part of the harness that can be wrong -- argv preservation, the
before/after retention, the symbol-table hand-off ugen mutates in place, and
the byte-for-byte reproduction gate -- with no compiler and no game data.
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from phase_streams import ucode_stream

from decomp_workbench.capture import (
    list_capture_runs,
    make_capture_toolchain,
    parse_phase_argv,
    read_capture_run,
    stock_phase_binary,
)
from decomp_workbench.cli import main
from decomp_workbench.pass_replay import replay_ugen
from decomp_workbench.streams import patch_stream

#: Parse the option shapes IDO's phases use, then do something deterministic.
_ARGUMENT_PARSER = """
out=""; sym=""; tmp=""; input=""
while [ $# -gt 0 ]
do
    case "$1" in
        -o) out="$2"; shift 2 ;;
        -t) sym="$2"; shift 2 ;;
        -temp) tmp="$2"; shift 2 ;;
        -G) shift 2 ;;
        -*) shift ;;
        *) input="$1"; shift ;;
    esac
done
"""

FAKE_UGEN = f"""#!/bin/sh
set -e
{_ARGUMENT_PARSER}
cat "$input" > "$out"
printf 'ugen-ran\\n' >> "$sym"
: > "$tmp"
"""

FAKE_AS1 = f"""#!/bin/sh
set -e
{_ARGUMENT_PARSER}
cat "$input" "$sym" > "$out"
"""

FAKE_AS0 = """#!/bin/sh
exit 0
"""


def build_fake_ido_root(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in (
        ("ugen", FAKE_UGEN),
        ("as1", FAKE_AS1),
        ("as0", FAKE_AS0),
    ):
        path = root / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
    (root / "err.english.cc").write_text("messages\n", encoding="utf-8")
    return root


def run_fake_build(toolchain: Path, work: Path, stream: bytes) -> dict[str, Path]:
    """Drive the wrapped phases the way a compiler driver would."""

    ucode = work / "tmp-ucode"
    binasm = work / "tmp-binasm"
    symtab = work / "tmp-symtab"
    temp = work / "tmp-temp"
    obj = work / "tmp-object"
    ucode.write_bytes(stream)
    symtab.write_text("symbols\n", encoding="utf-8")
    subprocess.run(
        [
            str(toolchain / "ugen"),
            "-G",
            "0",
            "-mips2",
            "-EB",
            "-g0",
            "-O2",
            str(ucode),
            "-o",
            str(binasm),
            "-t",
            str(symtab),
            "-temp",
            str(temp),
        ],
        check=True,
    )
    subprocess.run(
        [
            str(toolchain / "as1"),
            "-elf",
            "-G",
            "0",
            "-p0",
            "-mips2",
            "-EB",
            "-g0",
            "-O2",
            str(binasm),
            "-o",
            str(obj),
            "-t",
            str(symtab),
        ],
        check=True,
    )
    return {"ucode": ucode, "binasm": binasm, "object": obj, "symtab": symtab}


class ArgvTests(unittest.TestCase):
    def test_roles_and_inputs_are_split_without_losing_flags(self) -> None:
        argv = parse_phase_argv(
            ["-G", "0", "-mips2", "/tmp/in", "-o", "/tmp/out", "-t", "/tmp/sym"]
        )
        self.assertEqual(argv.inputs, ((4, "/tmp/in"),))
        self.assertEqual(argv.value_of("output"), "/tmp/out")
        self.assertEqual(argv.index_of("symtab"), 8)
        self.assertIn("-mips2", argv.flags)
        self.assertIn("-G 0", argv.flags)
        self.assertIn("output=out", argv.summary())


@unittest.skipIf(sys.platform == "win32", "the capture wrapper is a POSIX shell")
class CaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.ido = build_fake_ido_root(self.root / "ido" / "7.1")
        self.destination = self.root / "capture"
        self.manifest = make_capture_toolchain(self.ido, self.destination)
        self.toolchain = Path(self.manifest["toolchain"])
        self.work = self.root / "work"
        self.work.mkdir()

    def test_the_generated_toolchain_wraps_only_the_named_phases(self) -> None:
        self.assertEqual(self.manifest["wrapped_phases"], ["ugen", "as0", "as1"])
        for phase in ("ugen", "as0", "as1"):
            wrapper = self.toolchain / phase
            self.assertTrue(wrapper.is_symlink())
            self.assertEqual(os.readlink(wrapper), "phase-wrapper")
            self.assertTrue((self.toolchain / f"{phase}.real").is_file())
        self.assertTrue((self.toolchain / "err.english.cc").is_file())
        # The version-directory alias keeps `$(TOOLROOT)/7.1/ugen` working.
        self.assertIn("7.1", self.manifest["self_aliases"])
        self.assertTrue((self.toolchain / "7.1" / "ugen").exists())

    def test_an_existing_toolchain_is_not_silently_replaced(self) -> None:
        with self.assertRaisesRegex(FileExistsError, "refusing to overwrite"):
            make_capture_toolchain(self.ido, self.destination)
        replaced = make_capture_toolchain(self.ido, self.destination, force=True)
        self.assertEqual(replaced["carry_mode"], "copy")

    def test_a_destination_inside_the_ido_root_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be inside"):
            make_capture_toolchain(self.ido, self.ido / "captures")

    def test_a_missing_phase_is_named_with_what_the_root_holds(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "has no upas"):
            make_capture_toolchain(self.ido, self.root / "other", phases=["upas"])

    def test_a_build_leaves_one_run_per_phase_with_argv_and_streams(self) -> None:
        run_fake_build(self.toolchain, self.work, ucode_stream())
        report = list_capture_runs(self.destination)
        self.assertEqual(report["run_count"], 2)
        self.assertEqual(report["phase_counts"], {"as1": 1, "ugen": 1})
        ugen = next(item for item in report["runs"] if item["phase"] == "ugen")
        self.assertEqual(ugen["status"], 0)
        self.assertIn("-mips2", ugen["argv"]["flags"])
        self.assertEqual(
            Path(ugen["argv"]["roles"]["output"]["value"]).name, "tmp-binasm"
        )
        # The input was retained on entry and the outputs on exit.
        roles = {(item["role"], item["name"]) for item in ugen["files"]}
        self.assertIn(("before", "tmp-ucode"), roles)
        self.assertIn(("after", "tmp-binasm"), roles)
        self.assertGreater(ugen["stream_bytes"], 0)

    def test_the_symbol_table_is_retained_before_ugen_mutates_it(self) -> None:
        run_fake_build(self.toolchain, self.work, ucode_stream())
        report = list_capture_runs(self.destination, phase="ugen")
        run = read_capture_run(report["runs"][0]["directory"])
        index = run.argv.index_of("symtab")
        before = run.file_for("before", index)
        after = run.file_for("after", index)
        if before is None or after is None:
            self.fail("the wrapper retained no symbol table copies")
        self.assertEqual(before.path.read_text(encoding="utf-8"), "symbols\n")
        self.assertIn("ugen-ran", after.path.read_text(encoding="utf-8"))

    def test_capture_off_passes_straight_through(self) -> None:
        environment = dict(os.environ, WORKBENCH_CAPTURE_OFF="1")
        ucode = self.work / "off.U"
        ucode.write_bytes(ucode_stream())
        subprocess.run(
            [
                str(self.toolchain / "ugen"),
                str(ucode),
                "-o",
                str(self.work / "off.G"),
                "-t",
                str(self.work / "off.T"),
                "-temp",
                str(self.work / "off.tmp"),
            ],
            check=True,
            env=environment,
        )
        self.assertEqual(list_capture_runs(self.destination)["run_count"], 0)

    def test_replay_reproduces_the_captured_object_byte_for_byte(self) -> None:
        products = run_fake_build(self.toolchain, self.work, ucode_stream())
        runs = list_capture_runs(self.destination, phase="ugen")["runs"]
        replayed = self.work / "replayed.o"
        report = replay_ugen(
            products["ucode"],
            toolchain=self.destination,
            argv_from=runs[0]["directory"],
            output=replayed,
        )
        self.assertEqual(report["ugen"]["returncode"], 0)
        self.assertEqual(report["as1"]["returncode"], 0)
        self.assertTrue(report["verification"]["byte_identical"])
        self.assertEqual(replayed.read_bytes(), products["object"].read_bytes())
        # The replay ran the untouched binaries, so it left no run of its own.
        self.assertEqual(list_capture_runs(self.destination)["run_count"], 2)

    def test_a_patched_stream_changes_the_object_and_the_gate_says_so(
        self,
    ) -> None:
        products = run_fake_build(self.toolchain, self.work, ucode_stream())
        runs = list_capture_runs(self.destination, phase="ugen")["runs"]
        patched_bytes, _patch_report = patch_stream(
            products["ucode"],
            insert_at="#2",
            records_spec="0x42600000,{fresh},0,2",
            fresh_label_count=1,
        )
        patched = self.work / "patched.U"
        patched.write_bytes(patched_bytes)
        report = replay_ugen(
            patched,
            toolchain=self.destination,
            argv_from=runs[0]["directory"],
        )
        self.assertFalse(report["verification"]["byte_identical"])
        self.assertIn("differs", report["verification"]["verdict"])

    def test_replay_can_stop_at_the_binasm_boundary(self) -> None:
        products = run_fake_build(self.toolchain, self.work, ucode_stream())
        runs = list_capture_runs(self.destination, phase="ugen")["runs"]
        binasm = self.work / "replay.G"
        report = replay_ugen(
            products["ucode"],
            toolchain=self.destination,
            argv_from=runs[0]["directory"],
            output=binasm,
            run_as1=False,
        )
        self.assertNotIn("object", report)
        self.assertEqual(binasm.read_bytes(), products["binasm"].read_bytes())

    def test_replay_refuses_an_as1_run_as_the_argv_source(self) -> None:
        run_fake_build(self.toolchain, self.work, ucode_stream())
        as1_run = list_capture_runs(self.destination, phase="as1")["runs"][0]
        with self.assertRaisesRegex(ValueError, "is a as1 run"):
            replay_ugen(
                self.work / "tmp-ucode",
                toolchain=self.destination,
                argv_from=as1_run["directory"],
            )

    def test_replay_prefers_the_untouched_phase_binary(self) -> None:
        self.assertEqual(
            stock_phase_binary(self.destination, "ugen"),
            self.toolchain / "ugen.real",
        )

    def test_the_runs_listing_renders_a_row_per_run(self) -> None:
        run_fake_build(self.toolchain, self.work, ucode_stream())
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            status = main(["capture", "runs", str(self.destination)])
        text = stdout.getvalue()
        self.assertEqual(status, 0)
        self.assertIn("ugen", text)
        self.assertIn("as1", text)
        self.assertIn("output=tmp-binasm", text)


if __name__ == "__main__":
    unittest.main()
