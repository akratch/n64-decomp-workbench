"""`python -m decomp_workbench` must be a working way in, not an import error.

The console script is the documented entry point, but `python -m` is what a
reader reaches for when the script is not on PATH. Before `__main__.py` existed
that spelling failed with "No module named decomp_workbench.__main__", which
reads as a broken install. These tests pin the behaviour rather than the file:
the module runs, it delegates to the same `main`, and it returns `main`'s exit
status instead of swallowing it.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from decomp_workbench import __main__ as module_entry
from decomp_workbench.cli import main

SRC = Path(__file__).resolve().parents[1] / "src"


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(SRC), *filter(None, [env.get("PYTHONPATH")])]
    )
    return subprocess.run(
        [sys.executable, "-m", "decomp_workbench", *argv],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


class ModuleEntryPointTests(unittest.TestCase):
    def test_module_delegates_to_the_cli_main(self) -> None:
        self.assertIs(module_entry.main, main)

    def test_python_dash_m_prints_usage_and_exits_zero(self) -> None:
        result = _run("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("decomp-workbench", result.stdout)

    def test_python_dash_m_propagates_a_failing_exit_status(self) -> None:
        result = _run("no-such-subcommand")
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
