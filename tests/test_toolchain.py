"""Real-copy toolchains remain inspectable and refuse unsupported claims."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from decomp_workbench.toolchain import (
    MANIFEST_NAME,
    calibrate_toolchain,
    initialize_toolchain,
    toolchain_status,
)
from decomp_workbench.toolchain_cli import toolchain_calibrate_command


class ToolchainTests(unittest.TestCase):
    def make_objdump(self, root: Path) -> Path:
        objdump = root / "objdump"
        objdump.write_text(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "if '-s' in sys.argv:\n"
            " print(' 0000 11223344')\n"
            "elif '-r' in sys.argv:\n"
            " print('RELOCATION RECORDS FOR [.text]:')\n"
            "elif '-t' in sys.argv:\n"
            " print('SYMBOL TABLE:')\n"
            " print('00000000 g F .text 00000004 demo')\n",
            encoding="utf-8",
        )
        objdump.chmod(0o755)
        return objdump

    def test_init_dereferences_source_links_and_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "stock"
            base.mkdir()
            real = base / "real-uopt"
            real.write_bytes(b"stock")
            (base / "uopt").symlink_to(real.name)
            replacement = root / "instrumented-uopt"
            replacement.write_bytes(b"instrumented")
            output = root / "copy"

            report = initialize_toolchain(
                output,
                base=base,
                replacements={"uopt": replacement},
            )

            self.assertFalse((output / "uopt").is_symlink())
            self.assertEqual((output / "uopt").read_bytes(), b"instrumented")
            self.assertEqual(report["claim"], "uncalibrated")
            self.assertTrue(report["gates"]["real_copy"])
            self.assertTrue((output / MANIFEST_NAME).is_file())
            self.assertTrue(toolchain_status(output)["integrity"])

            (output / "uopt").write_bytes(b"tampered")
            status = toolchain_status(output)
            self.assertFalse(status["integrity"])
            self.assertEqual(status["claim"], "uncalibrated")

    def test_init_refuses_existing_destination_and_nested_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "stock"
            base.mkdir()
            (base / "cc").write_bytes(b"cc")
            with self.assertRaises(ValueError):
                initialize_toolchain(
                    base / "nested",
                    base=base,
                    replacements={},
                )
            existing = root / "existing"
            existing.mkdir()
            with self.assertRaises(FileExistsError):
                initialize_toolchain(
                    existing,
                    base=base,
                    replacements={},
                )

    def test_init_never_cleans_up_a_destination_it_did_not_create(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "stock"
            base.mkdir()
            (base / "cc").write_bytes(b"cc")
            output = root / "raced"
            original_mkdir = Path.mkdir

            def lose_destination_race(
                path: Path,
                mode: int = 0o777,
                parents: bool = False,
                exist_ok: bool = False,
            ) -> None:
                original_mkdir(
                    path,
                    mode=mode,
                    parents=parents,
                    exist_ok=exist_ok,
                )
                (path / "foreign").write_text("do not remove", encoding="utf-8")
                raise FileExistsError(path)

            with mock.patch.object(Path, "mkdir", lose_destination_race):
                with self.assertRaises(FileExistsError):
                    initialize_toolchain(output, base=base, replacements={})

            self.assertEqual(
                (output / "foreign").read_text(encoding="utf-8"),
                "do not remove",
            )

    def test_manifest_contains_no_proprietary_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "stock"
            base.mkdir()
            (base / "cc").write_bytes(b"private-binary")
            output = root / "copy"
            initialize_toolchain(output, base=base, replacements={})
            manifest = json.loads((output / MANIFEST_NAME).read_text(encoding="utf-8"))
            self.assertNotIn("private-binary", json.dumps(manifest))

    def test_calibration_reaches_ready_only_after_every_gate_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = root / "stock"
            base.mkdir()
            (base / "cc").write_bytes(b"cc")
            objdump = self.make_objdump(root)
            stock = root / "stock.o"
            instrumented = root / "instrumented.o"
            stock.write_bytes(b"stock")
            instrumented.write_bytes(b"instrumented")
            scheduler = root / "scheduler.log"
            scheduler.write_text(
                "[DKWB-SCHED-V1] proc=1 block=2 cycle=3 word=0x8c220000 "
                "opcode=lw line=9 ready=2 chosen=n4 tie=source-order\n",
                encoding="utf-8",
            )
            output = root / "copy"
            initialize_toolchain(
                output,
                base=base,
                replacements={},
                fidelity_pairs=[(stock, instrumented)],
                scheduler_positive_log=scheduler,
                objdump=str(objdump),
            )
            self.assertEqual(toolchain_status(output)["claim"], "uncalibrated")

            report = calibrate_toolchain(
                output,
                unedited_replay_pairs=[(stock, instrumented)],
                collateral_pairs=[(stock, instrumented)],
                project_output_pairs=[(stock, stock)],
                objdump=str(objdump),
            )

            self.assertEqual(report["claim"], "ready")
            self.assertEqual(report["next_missing_gates"], [])

    def test_successful_partial_calibration_is_not_a_process_failure(self) -> None:
        report = {
            "claim": "uncalibrated",
            "directory": "/external/toolchain",
            "gates": {"real_copy": True, "collateral": False},
            "next_missing_gates": ["collateral"],
        }
        arguments = argparse.Namespace(
            directory="/external/toolchain",
            unedited_replay_pair=[],
            collateral_pair=[],
            project_output_pair=[],
            scheduler_positive_log=None,
            objdump=None,
            json=False,
        )
        with mock.patch(
            "decomp_workbench.toolchain_cli.calibrate_toolchain",
            return_value=report,
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = toolchain_calibrate_command(arguments)
        self.assertEqual(status, 0)
        self.assertIn("UNCALIBRATED", output.getvalue())


if __name__ == "__main__":
    unittest.main()
