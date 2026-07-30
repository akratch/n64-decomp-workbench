"""Original/static pass differentials are explicit, retained, and reproducible."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.pass_adapter import (
    render_pass_command,
    run_pass_differential,
)


class PassAdapterTests(unittest.TestCase):
    def test_command_requires_input_and_output_without_a_shell(self) -> None:
        command = render_pass_command(
            "tool --in {input} --out {output} --work {work}",
            input_path=Path("/tmp/input file"),
            output_path=Path("/tmp/output file"),
            work_path=Path("/tmp/work"),
        )
        self.assertEqual(command[0], "tool")
        self.assertIn("/tmp/input file", command)
        with self.assertRaisesRegex(ValueError, r"\{output\}"):
            render_pass_command(
                "tool {input}",
                input_path=Path("input"),
                output_path=Path("output"),
                work_path=Path("work"),
            )

    def test_adapter_hashes_binaries_inputs_outputs_and_downstream(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "input.ir"
            source.write_text("retained pass input\n", encoding="utf-8")
            copy = root / "copy.py"
            copy.write_text(
                "import pathlib, sys\n"
                "pathlib.Path(sys.argv[2]).write_bytes("
                "pathlib.Path(sys.argv[1]).read_bytes())\n",
                encoding="utf-8",
            )
            template = f"{sys.executable} {copy} {{input}} {{output}}"
            report = run_pass_differential(
                source,
                original_template=template,
                static_template=template,
                downstream_template=template,
                boundary="uopt",
                work_root=root / "state",
                compile_cwd=root,
            )
        self.assertTrue(report["byte_identical"])
        self.assertTrue(report["normalized_identical"])
        self.assertTrue(report["downstream"]["identical"])
        self.assertIsNotNone(report["original"]["executable"]["sha256"])
        self.assertEqual(
            report["original"]["output_sha256"],
            report["static"]["output_sha256"],
        )
        self.assertIn("unedited-replay", report["proof"])


if __name__ == "__main__":
    unittest.main()
