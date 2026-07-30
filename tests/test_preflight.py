"""Doctor verifies a compiler wrapper without needing a real candidate."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import main


class PreflightTests(unittest.TestCase):
    def test_doctor_compile_preflight_reports_the_reproducibility_envelope(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compiler = root / "compile.py"
            compiler.write_text(
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[2]).write_bytes(b'object')\n",
                encoding="utf-8",
            )
            objdump = root / "objdump"
            objdump.write_text(
                "#!/usr/bin/env python3\n"
                "print('00000000 <decomp_workbench_preflight>:')\n"
                "print('   0: 03e00008  jr $ra')\n"
                "print('   4: 00000000  nop')\n",
                encoding="utf-8",
            )
            objdump.chmod(0o755)
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                status = main(
                    [
                        "doctor",
                        "--compile-command",
                        f"{sys.executable} {compiler} {{source}} {{output}}",
                        "--objdump",
                        str(objdump),
                        "--compile-cwd",
                        str(root),
                        "--json",
                    ]
                )
        payload = json.loads(stdout.getvalue())
        preflight = payload["compile_preflight"]
        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertTrue(preflight["ready"])
        self.assertEqual(preflight["status"], "ready")
        self.assertEqual(preflight["instructions"], 2)
        self.assertEqual(preflight["working_directory"], str(root.resolve()))
        self.assertIsNotNone(preflight["compiler"]["sha256"])


if __name__ == "__main__":
    unittest.main()
