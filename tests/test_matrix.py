"""Tests for `matrix`: run pipeline variants and cluster them into attractors."""

from __future__ import annotations

import contextlib
import io
import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from decomp_workbench.cli import main
from decomp_workbench.matrix import (
    ScoreError,
    cluster_attractors,
    load_matrix_spec,
    run_matrix,
)
from decomp_workbench.model import Instruction

#: Every variant "object" in these tests is a plain 16-byte file: four raw
#: 32-bit words, no ELF wrapper. `_stub_dump_object` below turns those bytes
#: directly into instructions, so scoring is exercised end to end (real
#: subprocess, real files) without a real objdump binary anywhere in CI.
MATCH_WORDS = "0102030411121314212223243132\x00\x00\x00"  # placeholder, unused


def _stub_dump_object(path, *, objdump=None, symbol=None, section=".text"):
    data = Path(path).read_bytes()
    instructions = [
        Instruction(
            address=index * 4,
            word=data[index * 4 : index * 4 + 4].hex(),
            assembly="nop",
        )
        for index in range(len(data) // 4)
    ]
    text = "00000000 <fn>:\n" + "\n".join(
        f"{item.address:x}: {item.word}" for item in instructions
    )
    return text, instructions


def _write_helper(root: Path, name: str, body: str) -> Path:
    path = root / name
    path.write_text(body, encoding="utf-8")
    return path


def _command_for(helper: Path) -> str:
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(helper))} $OUTPUT"


TARGET_BYTES = bytes.fromhex("01020304" "05060708" "090a0b0c" "0d0e0f10")
DIFFERENT_BYTES = bytes.fromhex("ffffffff" "05060708" "090a0b0c" "0d0e0f10")


class MatrixSpecTests(unittest.TestCase):
    def test_load_matrix_spec_requires_variants_and_score(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            spec_path = Path(temp) / "spec.json"
            spec_path.write_text(json.dumps({"variants": []}), encoding="utf-8")
            with self.assertRaises(ScoreError):
                load_matrix_spec(spec_path)

    def test_load_matrix_spec_rejects_duplicate_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            spec_path = Path(temp) / "spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "variants": [
                            {"label": "a", "command": "true $OUTPUT"},
                            {"label": "a", "command": "true $OUTPUT"},
                        ],
                        "score": {
                            "function": "fn",
                            "rom": "r.z64",
                            "rom_offset": "0x0",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ScoreError) as raised:
                load_matrix_spec(spec_path)
        self.assertIn("duplicate", str(raised.exception))

    def test_load_matrix_spec_parses_a_complete_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            spec_path = Path(temp) / "spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "variants": [{"label": "as1", "command": "true $OUTPUT"}],
                        "score": {
                            "function": "fn",
                            "rom": "r.z64",
                            "rom_offset": "0x10",
                        },
                    }
                ),
                encoding="utf-8",
            )
            variants, spec = load_matrix_spec(spec_path)
        self.assertEqual(variants[0].label, "as1")
        self.assertEqual(spec.target.rom_offset, 0x10)

    def test_invalid_json_names_the_fix(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            spec_path = Path(temp) / "spec.json"
            spec_path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ScoreError) as raised:
                load_matrix_spec(spec_path)
        self.assertIn("not valid JSON", str(raised.exception))


class ClusterAttractorsTests(unittest.TestCase):
    def test_orders_attractors_by_best_score(self) -> None:
        from decomp_workbench.matrix import VariantResult
        from decomp_workbench.score import ScoreReport, WordScore

        def make_result(label: str, digest: str, diff_words: int) -> VariantResult:
            score = WordScore(
                label="fn",
                mode="function",
                note=None,
                candidate_size=16,
                target_size=16,
                diff_words=diff_words,
                relocation_floor=0,
                diff_positions=(),
                candidate_sha256=digest,
                matched=diff_words == 0,
            )
            report = ScoreReport(
                candidate=label,
                target_description="test",
                function=score,
                controls=(),
                controls_broken=False,
                matched=diff_words == 0,
            )
            return VariantResult(
                label=label,
                command="",
                returncode=0,
                stdout="",
                stderr="",
                output_path=None,
                output_exists=True,
                duration_seconds=0.0,
                error=None,
                score=report,
                candidate_sha256=digest,
                stderr_warning=None,
                stdout_log="",
                stderr_log="",
            )

        results = [
            make_result("worse", "hash-worse", diff_words=5),
            make_result("best-a", "hash-best", diff_words=0),
            make_result("best-b", "hash-best", diff_words=0),
        ]
        attractors = cluster_attractors(results)
        self.assertEqual(attractors[0].letter, "A")
        self.assertEqual(attractors[0].diff_words, 0)
        self.assertEqual(set(attractors[0].members), {"best-a", "best-b"})
        self.assertEqual(attractors[1].letter, "B")
        self.assertEqual(attractors[1].members, ("worse",))


class RunVariantIntegrationTests(unittest.TestCase):
    """Real subprocesses, real files; only the disassembler is stubbed."""

    def _spec_path(self, root: Path, rom: Path) -> Path:
        spec_path = root / "spec.json"
        spec_path.write_text(
            json.dumps(
                {
                    "variants": self.variants,
                    "score": {
                        "function": "fn",
                        "rom": str(rom),
                        "rom_offset": 0,
                    },
                }
            ),
            encoding="utf-8",
        )
        return spec_path

    def setUp(self) -> None:
        self.variants: list[dict[str, str]] = []

    def test_two_variants_agree_and_one_differs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rom = root / "baserom.z64"
            rom.write_bytes(TARGET_BYTES)
            match_a = _write_helper(
                root,
                "match_a.py",
                "from pathlib import Path\nimport sys\n"
                f"Path(sys.argv[1]).write_bytes(bytes.fromhex({TARGET_BYTES.hex()!r}))\n",
            )
            match_b = _write_helper(
                root,
                "match_b.py",
                "from pathlib import Path\nimport sys\n"
                f"Path(sys.argv[1]).write_bytes(bytes.fromhex({TARGET_BYTES.hex()!r}))\n",
            )
            different = _write_helper(
                root,
                "different.py",
                "from pathlib import Path\nimport sys\n"
                f"Path(sys.argv[1]).write_bytes(bytes.fromhex({DIFFERENT_BYTES.hex()!r}))\n",
            )
            self.variants = [
                {"label": "match-a", "command": _command_for(match_a)},
                {"label": "match-b", "command": _command_for(match_b)},
                {"label": "different", "command": _command_for(different)},
            ]
            spec_path = self._spec_path(root, rom)
            run_dir = root / "run"
            with mock.patch(
                "decomp_workbench.score.dump_object", side_effect=_stub_dump_object
            ):
                report = run_matrix(spec_path, run_dir=run_dir, timeout=30.0)

            self.assertEqual(len(report.attractors), 2)
            best = report.attractors[0]
            self.assertEqual(best.diff_words, 0)
            self.assertEqual(set(best.members), {"match-a", "match-b"})
            self.assertEqual(len(report.collapsed_attractors), 1)
            self.assertFalse(report.all_collapsed)
            self.assertIsNone(report.caution)
            # Logs are never discarded.
            for item in report.variants:
                self.assertTrue(Path(item.stdout_log).is_file())
                self.assertTrue(Path(item.stderr_log).is_file())

    def test_all_variants_collapsing_triggers_the_caution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rom = root / "baserom.z64"
            rom.write_bytes(TARGET_BYTES)
            helpers = []
            for label in ("v1", "v2", "v3"):
                helper = _write_helper(
                    root,
                    f"{label}.py",
                    "from pathlib import Path\nimport sys\n"
                    f"Path(sys.argv[1]).write_bytes(bytes.fromhex({DIFFERENT_BYTES.hex()!r}))\n",
                )
                helpers.append((label, helper))
            self.variants = [
                {"label": label, "command": _command_for(helper)}
                for label, helper in helpers
            ]
            spec_path = self._spec_path(root, rom)
            run_dir = root / "run"
            with mock.patch(
                "decomp_workbench.score.dump_object", side_effect=_stub_dump_object
            ):
                report = run_matrix(spec_path, run_dir=run_dir, timeout=30.0)

        self.assertEqual(len(report.attractors), 1)
        self.assertTrue(report.all_collapsed)
        self.assertIsNotNone(report.caution)
        assert report.caution is not None
        self.assertIn("SSB64 drawbitmap campaign", report.caution)

    def test_stderr_warning_is_surfaced_next_to_its_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rom = root / "baserom.z64"
            rom.write_bytes(TARGET_BYTES)
            warns = _write_helper(
                root,
                "warns.py",
                "from pathlib import Path\nimport sys\n"
                "print('warning: unknown option --fancy-flag, ignored', "
                "file=sys.stderr)\n"
                f"Path(sys.argv[1]).write_bytes(bytes.fromhex({DIFFERENT_BYTES.hex()!r}))\n",
            )
            self.variants = [{"label": "warns", "command": _command_for(warns)}]
            spec_path = self._spec_path(root, rom)
            run_dir = root / "run"
            with mock.patch(
                "decomp_workbench.score.dump_object", side_effect=_stub_dump_object
            ):
                report = run_matrix(spec_path, run_dir=run_dir, timeout=30.0)

        self.assertEqual(len(report.silent_fallback_warnings), 1)
        label, line = report.silent_fallback_warnings[0]
        self.assertEqual(label, "warns")
        self.assertIn("unknown option", line)

    def test_command_without_output_placeholder_is_a_clean_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rom = root / "baserom.z64"
            rom.write_bytes(TARGET_BYTES)
            self.variants = [{"label": "bad", "command": "true"}]
            spec_path = self._spec_path(root, rom)
            run_dir = root / "run"
            report = run_matrix(spec_path, run_dir=run_dir, timeout=30.0)

        self.assertIsNone(report.variants[0].score)
        self.assertIn("$OUTPUT", report.variants[0].error or "")

    def test_command_producing_no_output_is_a_clean_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rom = root / "baserom.z64"
            rom.write_bytes(TARGET_BYTES)
            helper = _write_helper(root, "noop.py", "import sys\n")
            self.variants = [{"label": "noop", "command": _command_for(helper)}]
            spec_path = self._spec_path(root, rom)
            run_dir = root / "run"
            report = run_matrix(spec_path, run_dir=run_dir, timeout=30.0)

        self.assertIsNone(report.variants[0].score)
        self.assertIn("no output object", report.variants[0].error or "")

    def test_failing_command_is_a_clean_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rom = root / "baserom.z64"
            rom.write_bytes(TARGET_BYTES)
            helper = _write_helper(root, "fails.py", "import sys\nsys.exit(3)\n")
            self.variants = [{"label": "fails", "command": _command_for(helper)}]
            spec_path = self._spec_path(root, rom)
            run_dir = root / "run"
            report = run_matrix(spec_path, run_dir=run_dir, timeout=30.0)

        self.assertIsNone(report.variants[0].score)
        self.assertEqual(report.variants[0].returncode, 3)
        self.assertIn("exited 3", report.variants[0].error or "")


class MatrixCliTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_matrix_command_reports_attractors_and_logs_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rom = root / "baserom.z64"
            rom.write_bytes(TARGET_BYTES)
            helper = _write_helper(
                root,
                "match.py",
                "from pathlib import Path\nimport sys\n"
                f"Path(sys.argv[1]).write_bytes(bytes.fromhex({TARGET_BYTES.hex()!r}))\n",
            )
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "variants": [
                            {"label": "match", "command": _command_for(helper)}
                        ],
                        "score": {
                            "function": "fn",
                            "rom": str(rom),
                            "rom_offset": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            run_dir = root / "run"
            with mock.patch(
                "decomp_workbench.score.dump_object", side_effect=_stub_dump_object
            ):
                status, stdout, stderr = self.run_cli(
                    [
                        "matrix",
                        str(spec_path),
                        "--run-dir",
                        str(run_dir),
                    ]
                )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn(str(run_dir), stdout)
        self.assertIn("ATTR", stdout)
        self.assertIn("next:", stdout)

    def test_json_output_has_the_matrix_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rom = root / "baserom.z64"
            rom.write_bytes(TARGET_BYTES)
            helper = _write_helper(
                root,
                "match.py",
                "from pathlib import Path\nimport sys\n"
                f"Path(sys.argv[1]).write_bytes(bytes.fromhex({TARGET_BYTES.hex()!r}))\n",
            )
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "variants": [
                            {"label": "match", "command": _command_for(helper)}
                        ],
                        "score": {
                            "function": "fn",
                            "rom": str(rom),
                            "rom_offset": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            run_dir = root / "run"
            with mock.patch(
                "decomp_workbench.score.dump_object", side_effect=_stub_dump_object
            ):
                status, stdout, _ = self.run_cli(
                    ["matrix", str(spec_path), "--run-dir", str(run_dir), "--json"]
                )
        payload = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertEqual(payload["schema"], "decomp-workbench-matrix-v1")
        self.assertEqual(len(payload["attractors"]), 1)

    def test_missing_spec_file_is_a_clean_error(self) -> None:
        status, stdout, stderr = self.run_cli(["matrix", "/no/such/spec.json"])
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertIn("does not exist", stderr)

    def test_exit_is_one_when_no_variant_is_scorable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rom = root / "baserom.z64"
            rom.write_bytes(TARGET_BYTES)
            spec_path = root / "spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "variants": [{"label": "bad", "command": "true"}],
                        "score": {
                            "function": "fn",
                            "rom": str(rom),
                            "rom_offset": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            run_dir = root / "run"
            status, stdout, _ = self.run_cli(
                ["matrix", str(spec_path), "--run-dir", str(run_dir)]
            )
        self.assertEqual(status, 1)
        self.assertIn("no scorable object", stdout)


if __name__ == "__main__":
    unittest.main()
