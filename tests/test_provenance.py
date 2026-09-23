"""A forced result and a stock result score identically; only one is a match.

The case behind these tests is real: a supervising agent read four `0/N`
scores from forced diagnostic runs during a Mickey's Speedway USA campaign and
reported four exact matches. Every one of those lanes went on to file a
plateau. The score was right and the reading was wrong, so the reading is what
this module makes checkable.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from decomp_workbench.cli import main
from decomp_workbench.provenance import (
    FORCING_ENVIRONMENT,
    ProvenanceRefusal,
    classify_build,
    classify_environment,
    read_result,
    resolve_build_provenance,
)


class ClassifyEnvironmentTests(unittest.TestCase):
    def test_any_forcing_variable_marks_the_run_forced(self) -> None:
        for name in FORCING_ENVIRONMENT:
            with self.subTest(name=name):
                self.assertEqual(classify_environment({name: "1"}), "forced")

    def test_clean_environment_is_stock(self) -> None:
        self.assertEqual(classify_environment({"PATH": "/usr/bin"}), "stock")

    def test_empty_environment_is_stock(self) -> None:
        self.assertEqual(classify_environment({}), "stock")

    def test_absent_environment_is_unknown_not_stock(self) -> None:
        # Guessing "stock" here would recreate the false positive.
        self.assertEqual(classify_environment(None), "unknown")


class ReadResultTests(unittest.TestCase):
    def test_forced_exact_is_a_reachability_proof_not_a_match(self) -> None:
        claim = read_result(exact=True, provenance="forced")
        self.assertEqual(claim.claim, "reachability-proof")
        self.assertFalse(claim.is_match)
        self.assertIn("NOT A MATCH", "\n".join(claim.lines))

    def test_unknown_exact_is_not_claimable(self) -> None:
        claim = read_result(exact=True, provenance="unknown")
        self.assertEqual(claim.claim, "unverified")
        self.assertFalse(claim.is_match)

    def test_stock_exact_is_a_match_and_still_names_the_proofs(self) -> None:
        claim = read_result(exact=True, provenance="stock")
        self.assertEqual(claim.claim, "match")
        self.assertTrue(claim.is_match)
        self.assertIn("relocation identities", "\n".join(claim.lines))

    def test_no_provenance_makes_a_nonexact_result_a_match(self) -> None:
        for provenance in ("stock", "forced", "unknown"):
            with self.subTest(provenance=provenance):
                claim = read_result(exact=False, provenance=provenance)
                self.assertEqual(claim.claim, "no-claim")
                self.assertFalse(claim.is_match)

    def test_unrecognised_provenance_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            read_result(exact=True, provenance="probably-fine")

    def test_the_four_readings_that_were_misreported(self) -> None:
        # 0/403, 0/146, 0/131, 0/22 -- all forced, none matches.
        for _words in (403, 146, 131, 22):
            claim = read_result(exact=True, provenance="forced")
            self.assertFalse(claim.is_match)


if __name__ == "__main__":
    unittest.main()


class BuildProvenanceTests(unittest.TestCase):
    """Every scoring command states how its object was built, or refuses."""

    def test_tracing_without_a_force_is_instrumented_not_stock(self) -> None:
        self.assertEqual(classify_build({"CDX_LOG": "1"}), "instrumented")
        self.assertEqual(classify_build({"CDX_LOG": "1", "CDX_FORCE": "x"}), "forced")
        self.assertEqual(classify_build({}), "stock")
        self.assertEqual(classify_build(None), "unknown")
        self.assertEqual(
            read_result(exact=True, provenance="instrumented").claim, "unverified"
        )

    def test_a_forcing_shell_with_nothing_declared_is_refused(self) -> None:
        with self.assertRaisesRegex(ProvenanceRefusal, "CDX_FORCE"):
            resolve_build_provenance(
                declared=None,
                build_environment=None,
                process_environment={"CDX_FORCE": "p1:w1=c2", "PATH": "/bin"},
            )

    def test_a_declaration_or_a_build_environment_answers_it(self) -> None:
        declared = resolve_build_provenance(
            declared="stock",
            build_environment=None,
            process_environment={"CDX_FORCE": "p1:w1=c2"},
        )
        self.assertEqual((declared.provenance, declared.basis), ("stock", "declared"))
        from_file = resolve_build_provenance(
            declared=None,
            build_environment={"CDX_FORCE": "p1:w1=c2", "CDX_PROC": "0"},
            process_environment={},
        )
        self.assertEqual(from_file.provenance, "forced")
        self.assertEqual(from_file.variables, ("CDX_FORCE", "CDX_PROC"))
        with self.assertRaisesRegex(ProvenanceRefusal, "not both"):
            resolve_build_provenance(
                declared="stock", build_environment={}, process_environment={}
            )

    def test_an_undeclared_clean_build_is_unknown_and_never_a_match(self) -> None:
        provenance = resolve_build_provenance(
            declared=None, build_environment=None, process_environment={}
        )
        self.assertEqual(provenance.provenance, "unknown")
        self.assertEqual(provenance.claim(exact=True).claim, "unverified")
        self.assertIn("--build-env stock", provenance.lines(exact=True)[0])


FIXTURE = (
    Path(__file__).resolve().parents[1] / "examples" / "fixtures" / "target.objdump"
)


class ComparisonCommandTests(unittest.TestCase):
    def run_cli(
        self, arguments: list[str], environment: dict[str, str] | None = None
    ) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            mock.patch.dict(os.environ, environment or {}),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def pair(self) -> list[str]:
        return [str(FIXTURE), str(FIXTURE)]

    def test_the_unforced_rescore_trap_is_a_refusal(self) -> None:
        for command in ("compare-dumps", "diagnose-dumps"):
            with self.subTest(command=command):
                status, _, stderr = self.run_cli(
                    [command, *self.pair()], {"CDX_FORCE": "p1:w9=c4"}
                )
                self.assertEqual(status, 2)
                self.assertIn("--build-env", stderr)

    def test_a_forced_exact_comparison_says_it_is_not_a_match(self) -> None:
        status, stdout, _ = self.run_cli(
            ["compare-dumps", *self.pair(), "--build-env", "forced"],
            {"CDX_FORCE": "p1:w9=c4"},
        )
        self.assertEqual(status, 0)
        self.assertIn("build: forced, declared", stdout)
        self.assertIn("NOT A MATCH", stdout)
        status, stdout, _ = self.run_cli(
            ["compare-dumps", *self.pair(), "--build-env", "forced", "--json"]
        )
        payload = json.loads(stdout)
        self.assertEqual(payload["build_provenance"]["claim"], "reachability-proof")
        self.assertEqual(
            payload["build_provenance_schema"], "decomp-workbench-build-provenance-v1"
        )

    def test_only_a_declared_stock_build_is_a_claimable_match(self) -> None:
        _, stdout, _ = self.run_cli(
            ["compare-dumps", *self.pair(), "--build-env", "stock", "--json"]
        )
        self.assertEqual(json.loads(stdout)["build_provenance"]["claim"], "match")
        _, stdout, _ = self.run_cli(["compare-dumps", *self.pair(), "--json"])
        self.assertEqual(json.loads(stdout)["build_provenance"]["claim"], "unverified")
        _, stdout, _ = self.run_cli(["compare-dumps", *self.pair()])
        self.assertIn("build: undeclared", stdout)

    def test_a_build_environment_file_is_read_and_classified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "env.json"
            path.write_text(
                json.dumps({"environment": {"CDX_LOG": "1", "CDX_OUT": "x.log"}}),
                encoding="utf-8",
            )
            _, stdout, _ = self.run_cli(
                [
                    "diagnose-dumps",
                    *self.pair(),
                    "--build-env-file",
                    str(path),
                    "--json",
                ]
            )
        block = json.loads(stdout)["build_provenance"]
        self.assertEqual(block["provenance"], "instrumented")
        self.assertEqual(block["basis"], "environment-file")
