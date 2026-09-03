"""The two-profile drop-in: the recipe, and the check that it survived.

None of these tests needs a compiler, a build, or a ROM. That is the point of
the audit: the failure it catches -- a rebuild that reproduced one pass and
silently dropped the other's profile -- is visible in the built binary's bytes,
and a workbench that could only catch it by compiling would not have caught it
at all.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import main
from decomp_workbench.drop_in import (
    AUDIT_SCHEMA,
    PLAN_SCHEMA,
    PROFILES,
    audit,
    format_audit,
    plan,
    render_script,
)

#: A stand-in for a built compiler carrying every profile's markers. Real
#: binaries are ELF; the audit is a byte scan and does not care.
COMPLETE = b"".join(
    marker.encode("ascii") + b"\x00"
    for profile in PROFILES
    for marker in profile.markers
)

#: The failure this command exists for: ugen rebuilt, uopt's profile gone.
UGEN_ONLY = b"".join(
    marker.encode("ascii") + b"\x00"
    for profile in PROFILES
    if profile.source == "ugen.c"
    for marker in profile.markers
)


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class PlanTests(unittest.TestCase):
    def test_the_plan_covers_both_generated_sources(self) -> None:
        document = plan(generated=Path("/g"), output=Path("/o"))
        self.assertEqual(document["schema"], PLAN_SCHEMA)
        self.assertEqual(
            {item["source"] for item in document["sources"]}, {"uopt.c", "ugen.c"}
        )

    def test_both_passes_are_instrumented_in_one_recipe(self) -> None:
        document = plan(generated=Path("/g"), output=Path("/o"))
        commands = [step["argv"][1] for step in document["steps"]]
        self.assertIn("instrument-uopt", commands)
        self.assertIn("instrument-ugen", commands)

    def test_the_ugen_step_asks_for_emit_provenance(self) -> None:
        document = plan(generated=Path("/g"), output=Path("/o"))
        ugen = next(
            step for step in document["steps"] if step["argv"][1] == "instrument-ugen"
        )
        self.assertIn("--emit-provenance", ugen["argv"])

    def test_a_plan_over_an_absent_tree_is_still_a_plan(self) -> None:
        document = plan(generated=Path("/nowhere"), output=Path("/o"))
        self.assertTrue(document["steps"])
        self.assertFalse(any(item["present"] for item in document["sources"]))
        self.assertTrue(all(item["sha256"] is None for item in document["sources"]))

    def test_a_present_source_is_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "uopt.c").write_text("int main(void){return 0;}\n")
            document = plan(generated=root, output=root / "out")
        uopt = next(item for item in document["sources"] if item["source"] == "uopt.c")
        self.assertTrue(uopt["present"])
        self.assertEqual(len(uopt["sha256"] or ""), 64)

    def test_the_gates_are_part_of_the_recipe(self) -> None:
        document = plan(generated=Path("/g"), output=Path("/o"))
        joined = " ".join(document["gates"])
        self.assertIn("cmp the object against the stock build", joined)
        self.assertIn("positive control", joined)
        self.assertIn("instrument-gate", joined)

    def test_the_stock_scheduler_trace_is_named_so_nobody_patches_as1(self) -> None:
        document = plan(generated=Path("/g"), output=Path("/o"))
        self.assertIn(
            "cc -Wa,-R", [item["command"] for item in document["stock_evidence"]]
        )

    def test_the_script_is_readable_before_it_is_run(self) -> None:
        script = render_script(plan(generated=Path("/g"), output=Path("/o")))
        self.assertTrue(script.startswith("#!/bin/sh"))
        self.assertIn("set -eu", script)
        self.assertIn("test -f /g/uopt.c", script)


class AuditTests(unittest.TestCase):
    def write(self, root: Path, data: bytes) -> Path:
        path = root / "cc"
        path.write_bytes(data)
        return path

    def test_a_complete_drop_in_carries_every_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary = self.write(Path(directory), COMPLETE)
            document = audit([binary])
        self.assertEqual(document["schema"], AUDIT_SCHEMA)
        self.assertTrue(document["complete"])
        self.assertEqual(document["missing"], [])

    def test_the_ugen_only_rebuild_is_reported_as_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary = self.write(Path(directory), UGEN_ONLY)
            document = audit([binary])
        self.assertFalse(document["complete"])
        self.assertEqual(document["missing"], ["uopt-globalcolor", "uopt-alias"])

    def test_profiles_may_live_in_different_binaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            uopt = root / "uopt"
            ugen = root / "ugen"
            uopt.write_bytes(
                b"".join(
                    marker.encode("ascii")
                    for profile in PROFILES
                    if profile.source == "uopt.c"
                    for marker in profile.markers
                )
            )
            ugen.write_bytes(UGEN_ONLY)
            document = audit([uopt, ugen])
        self.assertTrue(document["complete"])

    def test_naming_no_binary_is_an_error_not_an_empty_pass(self) -> None:
        with self.assertRaises(ValueError):
            audit([])

    def test_the_report_says_what_it_cannot_prove(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary = self.write(Path(directory), COMPLETE)
            document = audit([binary])
        self.assertIn("Neither proves it fires", document["proof"])

    def test_the_rendered_report_names_the_empty_log_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary = self.write(Path(directory), UGEN_ONLY)
            text = format_audit(audit([binary]))
        self.assertIn("ABSENT", text)
        self.assertIn("empty rather than wrong", text)


class CommandTests(unittest.TestCase):
    def test_the_plan_command_prints_the_script(self) -> None:
        status, stdout, _ = run_cli(["instrument-drop-in", "/g", "/o"])
        self.assertEqual(status, 0)
        self.assertIn("instrument-uopt", stdout)
        self.assertIn("instrument-ugen", stdout)

    def test_the_journey_spelling_is_the_same_command(self) -> None:
        _flat, flat_out, _ = run_cli(["instrument-drop-in", "/g", "/o", "--json"])
        _group, group_out, _ = run_cli(["instrument", "drop-in", "/g", "/o", "--json"])
        self.assertEqual(json.loads(flat_out), json.loads(group_out))

    def test_the_script_is_written_and_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "build.sh"
            status, _stdout, _ = run_cli(
                ["instrument-drop-in", "/g", "/o", "--script", str(script)]
            )
            self.assertEqual(status, 0)
            self.assertTrue(script.read_text().startswith("#!/bin/sh"))
            status, _stdout, stderr = run_cli(
                ["instrument-drop-in", "/g", "/o", "--script", str(script)]
            )
        self.assertEqual(status, 2)
        self.assertIn("refusing to overwrite", stderr)

    def test_require_sources_fails_on_a_tree_that_is_not_there(self) -> None:
        status, _stdout, stderr = run_cli(
            ["instrument-drop-in", "/nowhere", "/o", "--require-sources"]
        )
        self.assertEqual(status, 1)
        self.assertIn("generated source not found", stderr)

    def test_the_check_command_exits_nonzero_on_a_half_drop_in(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "cc"
            binary.write_bytes(UGEN_ONLY)
            status, stdout, _ = run_cli(["check-drop-in", str(binary)])
        self.assertEqual(status, 1)
        self.assertIn("uopt-globalcolor", stdout)

    def test_the_check_command_passes_a_complete_drop_in(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "cc"
            binary.write_bytes(COMPLETE)
            status, stdout, _ = run_cli(["check-drop-in", str(binary), "--json"])
        self.assertEqual(status, 0)
        self.assertTrue(json.loads(stdout)["complete"])

    def test_an_in_place_plan_passes_in_place_to_every_step(self) -> None:
        """Generated and output tree the same directory is the normal case:
        ido-static-recomp builds from the sources in place. Both instrument
        commands refuse input == output without --in-place, so a plan that
        omits it emits a script that dies on its first step under `set -eu`,
        leaving the previously built drop-in in place and its logs empty."""
        document = plan(generated=Path("/g"), output=Path("/g"))
        self.assertTrue(document["steps"])
        for step in document["steps"]:
            self.assertIn("--in-place", step["argv"], step["profile"])
        script = render_script(document)
        self.assertEqual(script.count("--in-place"), len(document["steps"]))

    def test_a_separate_output_tree_does_not_ask_for_in_place(self) -> None:
        document = plan(generated=Path("/g"), output=Path("/o"))
        self.assertTrue(document["steps"])
        for step in document["steps"]:
            self.assertNotIn("--in-place", step["argv"], step["profile"])

    def test_a_missing_binary_is_an_error_document(self) -> None:
        status, _stdout, stderr = run_cli(["check-drop-in", "/nowhere/cc"])
        self.assertEqual(status, 2)
        self.assertTrue(stderr.startswith("error: "))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
