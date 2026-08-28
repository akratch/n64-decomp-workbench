"""A comparison against a stale build reads as a match, so it is refused.

Nothing here needs a compiler, a ROM, or a build: every artifact is a file in
a temporary directory whose modification time is set explicitly, which is the
only input the guard reads.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import main
from decomp_workbench.staleness import (
    STALENESS_SCHEMA,
    StaleBuildError,
    chain_report,
    enforce_freshness,
    file_sha256,
    staleness_report,
)

DUMP = """
00000000 <animStep>:
   0: 03e00008  jr $ra
   4: 00000000  nop
"""

#: A fixed instant, so a test never races the clock it is asserting about.
BASE = 1_700_000_000.0


def write(path: Path, text: str, *, age: float) -> Path:
    """Write one file and stamp it `age` seconds after the base instant."""

    path.write_text(text, encoding="utf-8")
    os.utime(path, (BASE + age, BASE + age))
    return path


class StalenessReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_a_build_newer_than_its_source_is_fresh(self) -> None:
        source = write(self.root / "track.c", "int a;\n", age=0)
        rom = write(self.root / "game.z64", "rom", age=60)
        report = staleness_report(source, rom)
        self.assertEqual(report.status, "fresh")
        self.assertTrue(report.fresh)
        self.assertFalse(report.stale)
        self.assertEqual(report.violations, ())

    def test_a_rom_older_than_the_edited_source_is_stale(self) -> None:
        """The false positive this whole module exists for."""

        rom = write(self.root / "game.z64", "rom", age=0)
        source = write(self.root / "track.c", "int a;\n", age=600)
        report = staleness_report(source, rom)
        self.assertEqual(report.status, "stale")
        self.assertTrue(report.stale)
        self.assertFalse(report.fresh)
        self.assertEqual(len(report.violations), 1)
        violation = report.violations[0]
        self.assertEqual(violation.input.label, "input")
        self.assertEqual(violation.derived.label, "built")
        self.assertIn("BEFORE", violation.message)
        self.assertIn("10m", violation.message)

    def test_every_earlier_path_is_an_input_to_every_later_one(self) -> None:
        """A ROM relinked after the object but before the source is stale.

        Checking only adjacent pairs would call this chain fresh: the ROM is
        newer than the ELF and the ELF newer than the object, and the one
        thing that moved -- the source -- is two links back.
        """

        source = write(self.root / "track.c", "int a;\n", age=900)
        obj = write(self.root / "track.o", "obj", age=0)
        elf = write(self.root / "game.elf", "elf", age=10)
        rom = write(self.root / "game.z64", "rom", age=20)
        report = staleness_report(source, obj, elf, rom)
        self.assertEqual(report.status, "stale")
        self.assertEqual(
            {item.derived.label for item in report.violations},
            {"input2", "input3", "built"},
        )

    def test_one_timestamp_tick_is_not_staleness(self) -> None:
        """A guard that fires on the normal case is a guard that gets disabled."""

        source = write(self.root / "track.c", "int a;\n", age=1)
        obj = write(self.root / "track.o", "obj", age=0)
        self.assertFalse(staleness_report(source, obj).stale)
        self.assertTrue(staleness_report(source, obj, tolerance_seconds=0.0).stale)

    def test_a_missing_artifact_is_unproven_not_fresh(self) -> None:
        source = write(self.root / "track.c", "int a;\n", age=0)
        report = staleness_report(source, self.root / "never-built.z64")
        self.assertEqual(report.status, "missing")
        self.assertFalse(report.fresh)
        self.assertFalse(report.stale)
        self.assertEqual(report.artifacts[1].built_at, "(missing)")
        self.assertIn("does not exist", report.message)

    def test_one_artifact_alone_proves_nothing(self) -> None:
        source = write(self.root / "track.c", "int a;\n", age=0)
        report = staleness_report(source)
        self.assertEqual(report.status, "unknown")
        self.assertFalse(report.fresh)

    def test_hashes_are_recorded_only_when_asked(self) -> None:
        source = write(self.root / "track.c", "int a;\n", age=0)
        rom = write(self.root / "game.z64", "rom", age=10)
        self.assertIsNone(staleness_report(source, rom).artifacts[0].sha256)
        hashed = staleness_report(source, rom, hashes=True)
        self.assertEqual(hashed.artifacts[0].sha256, file_sha256(Path(source)))
        self.assertRegex(str(hashed.artifacts[0].sha256), r"^[0-9a-f]{64}$")
        self.assertNotEqual(hashed.artifacts[0].sha256, hashed.artifacts[1].sha256)

    def test_labels_must_correspond_to_paths(self) -> None:
        source = write(self.root / "track.c", "int a;\n", age=0)
        with self.assertRaises(ValueError):
            staleness_report(source, labels=("source", "rom"))

    def test_provenance_states_every_artifact_and_when_it_was_built(self) -> None:
        source = write(self.root / "track.c", "int a;\n", age=0)
        rom = write(self.root / "game.z64", "rom", age=10)
        lines = staleness_report(source, rom).provenance_lines()
        self.assertEqual(len(lines), 2)
        self.assertIn("track.c", lines[0])
        self.assertIn("built 20", lines[0])

    def test_two_derived_siblings_are_never_stale_against_each_other(self) -> None:
        """A target older than the candidate says nothing; it is not derived from it."""

        source = write(self.root / "track.c", "int a;\n", age=0)
        target = write(self.root / "target.o", "t", age=10)
        candidate = write(self.root / "candidate.o", "c", age=900)
        report = chain_report(
            (target, candidate), (source,), labels=("source", "target", "candidate")
        )
        self.assertFalse(report.stale)
        self.assertEqual(report.artifacts[0].label, "source")

    def test_enforce_refuses_by_default_and_warns_under_allow_stale(self) -> None:
        rom = write(self.root / "game.z64", "rom", age=0)
        source = write(self.root / "track.c", "int a;\n", age=600)
        report = staleness_report(source, rom)
        with self.assertRaises(StaleBuildError):
            enforce_freshness(report, allow_stale=False)
        warnings = enforce_freshness(report, allow_stale=True)
        self.assertTrue(all(item.startswith("warning:") for item in warnings))
        self.assertTrue(any("--allow-stale" in item for item in warnings))


class CheckStalenessCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def chain(self, *, rom_age: float) -> tuple[str, str]:
        source = write(self.root / "track.c", "int a;\n", age=0)
        rom = write(self.root / "game.z64", "rom", age=rom_age)
        return str(source), str(rom)

    def test_a_fresh_chain_exits_zero_and_says_when_it_was_built(self) -> None:
        source, rom = self.chain(rom_age=60)
        status, stdout, _ = self.run_cli(["check-staleness", source, rom])
        self.assertEqual(status, 0)
        self.assertIn("build freshness: fresh", stdout)
        self.assertIn("built 20", stdout)

    def test_a_stale_chain_exits_one_and_names_the_input(self) -> None:
        source, rom = self.chain(rom_age=-600)
        status, stdout, _ = self.run_cli(["check-staleness", source, rom])
        self.assertEqual(status, 1)
        self.assertIn("STALE:", stdout)
        self.assertIn("track.c", stdout)

    def test_allow_stale_reports_and_still_exits_zero(self) -> None:
        source, rom = self.chain(rom_age=-600)
        status, stdout, _ = self.run_cli(
            ["check-staleness", source, rom, "--allow-stale"]
        )
        self.assertEqual(status, 0)
        self.assertIn("STALE:", stdout)

    def test_json_is_one_schema_named_document(self) -> None:
        source, rom = self.chain(rom_age=-600)
        status, stdout, stderr = self.run_cli(
            ["check-staleness", source, rom, "--json", "--sha256"]
        )
        payload = json.loads(stdout)
        self.assertEqual(status, 1)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["schema"], STALENESS_SCHEMA)
        self.assertTrue(payload["stale"])
        self.assertEqual(payload["status"], "stale")
        self.assertRegex(payload["artifacts"][0]["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(payload["violations"]), 1)

    def test_one_path_is_a_usage_error_not_a_pass(self) -> None:
        source, _ = self.chain(rom_age=60)
        status, _, stderr = self.run_cli(["check-staleness", source])
        self.assertEqual(status, 2)
        self.assertIn("at least two paths", stderr)

    def test_labels_must_correspond(self) -> None:
        source, rom = self.chain(rom_age=60)
        status, _, stderr = self.run_cli(
            ["check-staleness", source, rom, "--label", "source"]
        )
        self.assertEqual(status, 2)
        self.assertIn("must correspond", stderr)

    def test_the_grouped_spelling_is_the_same_command(self) -> None:
        source, rom = self.chain(rom_age=60)
        flat = self.run_cli(["check-staleness", source, rom])
        grouped = self.run_cli(["object", "staleness", source, rom])
        self.assertEqual(grouped, flat)


class ComparisonFreshnessTests(unittest.TestCase):
    """The guard where it matters: on the commands that report a match."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = write(self.root / "target.objdump", DUMP, age=0)
        self.candidate = write(self.root / "candidate.objdump", DUMP, age=0)

    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def edited_source(self, *, age: float) -> str:
        return str(write(self.root / "track.c", "int a;\n", age=age))

    def base_arguments(self) -> list[str]:
        return ["compare-dumps", str(self.target), str(self.candidate)]

    def test_a_zero_word_result_states_what_it_compared_and_when(self) -> None:
        status, stdout, _ = self.run_cli(self.base_arguments())
        self.assertEqual(status, 0)
        self.assertIn("compared: target", stdout)
        self.assertIn("compared: candidate", stdout)
        self.assertIn("built 20", stdout)

    def test_a_comparison_older_than_the_source_is_refused(self) -> None:
        source = self.edited_source(age=600)
        status, stdout, stderr = self.run_cli(
            [*self.base_arguments(), "--built-from", source]
        )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertIn("error: ", stderr)
        self.assertIn("BEFORE", stderr)
        self.assertIn("--allow-stale", stderr)

    def test_allow_stale_runs_it_anyway_and_says_so_first(self) -> None:
        source = self.edited_source(age=600)
        status, stdout, _ = self.run_cli(
            [*self.base_arguments(), "--built-from", source, "--allow-stale"]
        )
        self.assertEqual(status, 0)
        first = stdout.splitlines()[0]
        self.assertTrue(first.startswith("warning:"), first)
        self.assertIn("verdict=", stdout)

    def test_a_build_newer_than_the_source_passes_the_guard(self) -> None:
        source = self.edited_source(age=-600)
        status, stdout, _ = self.run_cli(
            [*self.base_arguments(), "--built-from", source]
        )
        self.assertEqual(status, 0)
        self.assertIn("compared: source", stdout)

    def test_json_carries_the_freshness_block_without_renaming_its_host(
        self,
    ) -> None:
        source = self.edited_source(age=-600)
        status, stdout, _ = self.run_cli(
            [*self.base_arguments(), "--built-from", source, "--json"]
        )
        payload = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertEqual(payload["schema"], "decomp-workbench-comparison-v1")
        self.assertEqual(payload["staleness_schema"], STALENESS_SCHEMA)
        self.assertEqual(payload["staleness"]["status"], "fresh")
        self.assertNotIn("schema", payload["staleness"])
        labels = [item["label"] for item in payload["staleness"]["artifacts"]]
        self.assertEqual(labels, ["source", "target", "candidate"])

    def test_a_stale_refusal_is_a_json_error_document(self) -> None:
        source = self.edited_source(age=600)
        status, stdout, stderr = self.run_cli(
            [*self.base_arguments(), "--built-from", source, "--json"]
        )
        payload = json.loads(stdout)
        self.assertEqual(status, 2)
        self.assertEqual(stderr, "")
        self.assertEqual(payload["schema"], "decomp-workbench-error-v1")
        self.assertIn("BEFORE", payload["error"]["message"])

    def test_diagnose_refuses_the_same_way(self) -> None:
        source = self.edited_source(age=600)
        status, _, stderr = self.run_cli(
            [
                "diagnose-dumps",
                str(self.target),
                str(self.candidate),
                "--built-from",
                source,
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("BEFORE", stderr)

    def test_diagnose_states_its_provenance_by_default(self) -> None:
        status, stdout, _ = self.run_cli(
            ["diagnose-dumps", str(self.target), str(self.candidate), "--terse"]
        )
        self.assertEqual(status, 0)
        self.assertIn("compared: target", stdout.splitlines()[0])


if __name__ == "__main__":
    unittest.main()
