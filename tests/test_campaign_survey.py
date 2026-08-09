"""A campaign directory is read, not registered.

The design question this closes: serving the "where are we" ask looked like it
needed a second notion of "campaign" -- a registry of tracked artifacts with
provenance -- alongside the manifest `campaign run` already writes. It does not.
A survey is a reading taken now, so there is no stored identity to be wrong
about and no persisted claim to go stale.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.campaign_survey import (
    SURVEY_SCHEMA,
    CampaignSurveyError,
    survey_campaign,
    survey_lines,
)
from decomp_workbench.cli import main


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class SurveyCase(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "CAMPAIGN-PLAN.md").write_text("plan\n", encoding="utf-8")
        for stage in ("early", "late"):
            directory = self.root / stage
            (directory / "o").mkdir(parents=True)
            (directory / f"{stage}.c").write_text(f"/* {stage} */\n", encoding="utf-8")
            (directory / "o" / f"{stage}.o").write_bytes(b"object")
            (directory / "RESULT.md").write_text("result\n", encoding="utf-8")


class SurveyTests(SurveyCase):
    def test_the_stages_are_counted_and_ordered_by_recency(self) -> None:
        report = survey_campaign(self.root)
        self.assertEqual(report["schema"], SURVEY_SCHEMA)
        self.assertEqual(report["stage_count"], 2)
        names = [item["name"] for item in report["stages"]]
        self.assertEqual(sorted(names), ["early", "late"])
        stage = next(item for item in report["stages"] if item["name"] == "late")
        self.assertEqual(stage["sources"], 1)
        self.assertEqual(stage["objects"], 1)
        self.assertIn("RESULT.md", stage["notes"])

    def test_nothing_guesses_which_artifact_is_the_base(self) -> None:
        report = survey_campaign(self.root)
        self.assertIsNone(report["base"])
        rendered = "\n".join(survey_lines(report))
        self.assertIn("which may or may not be the base", rendered)
        self.assertIn("Nothing is stored", rendered)

    def test_a_pinned_base_is_hashed_now_rather_than_remembered(self) -> None:
        source = self.root / "late" / "late.c"
        first = survey_campaign(self.root, base=source)
        source.write_text("/* changed */\n", encoding="utf-8")
        second = survey_campaign(self.root, base=source)
        assert first["base"] and second["base"]
        self.assertNotEqual(first["base"]["sha256"], second["base"]["sha256"])

    def test_a_truncated_walk_says_so_rather_than_reporting_a_smaller_tree(
        self,
    ) -> None:
        report = survey_campaign(self.root, budget=2)
        self.assertTrue(report["truncated"])
        self.assertIn("TRUNCATED", "\n".join(survey_lines(report)))

    def test_a_findings_log_is_read_through_the_note_mechanism(self) -> None:
        log = self.root / "WORKBENCH-IMPROVEMENTS.md"
        log.write_text("## WB-1 — a finding\n**Status:** LOGGED\n", encoding="utf-8")
        sidecar = self.root / "WORKBENCH-IMPROVEMENTS.md.notes.d"
        sidecar.mkdir()
        (sidecar / "20260809T000000-WB-2-abcd1234.json").write_text(
            json.dumps(
                {
                    "schema": "decomp-workbench-note-v1",
                    "id": "WB-2",
                    "title": "pending",
                    "status": "LOGGED",
                    "body": "",
                    "author": None,
                    "recorded": "2026-08-09T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        report = survey_campaign(self.root)
        self.assertEqual(len(report["findings_logs"]), 1)
        self.assertEqual(report["findings_logs"][0]["entries"], 1)
        self.assertEqual(report["findings_logs"][0]["pending"], 1)

    def test_a_sweep_manifest_is_reported_with_its_coverage(self) -> None:
        from decomp_workbench.sweep import write_family
        from decomp_workbench.sweep_generators import parse_construct, removal_family

        source = self.root / "late" / "late.c"
        source.write_text("int demo(void) {\n    return 1;\n}\n", encoding="utf-8")
        write_family(
            removal_family(source, constructs=(parse_construct("2=return"),)),
            directory=self.root / "late" / "sweep",
        )
        report = survey_campaign(self.root)
        self.assertEqual(len(report["sweeps"]), 1)
        self.assertEqual(report["sweeps"][0]["generator"], "regress")
        self.assertIn("regress", "\n".join(survey_lines(report)))

    def test_no_gate_stamp_is_itself_the_finding(self) -> None:
        rendered = "\n".join(survey_lines(survey_campaign(self.root)))
        self.assertIn("instrument gates: none recorded", rendered)
        self.assertIn("instrument gate", rendered)

    def test_a_gate_stamp_is_reported_with_its_verdict(self) -> None:
        (self.root / "gates").mkdir()
        (self.root / "gates" / "uopt.json").write_text(
            json.dumps(
                {
                    "schema": "decomp-workbench-instrument-gate-v1",
                    "profile": "uopt-cdx",
                    "pass": True,
                    "recorded": "2026-08-09T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        report = survey_campaign(self.root)
        self.assertEqual(report["instrument_gates"][0]["profile"], "uopt-cdx")
        self.assertIn("PASS  uopt-cdx", "\n".join(survey_lines(report)))

    def test_a_file_is_not_a_campaign_directory_and_says_which_command_is(
        self,
    ) -> None:
        with self.assertRaises(CampaignSurveyError) as raised:
            survey_campaign(self.root / "CAMPAIGN-PLAN.md")
        self.assertIn("campaign status", str(raised.exception))


class SurveyCliTests(SurveyCase):
    def test_the_command_runs_and_names_the_root(self) -> None:
        status, stdout, stderr = run_cli(["campaign", "survey", str(self.root)])
        self.assertEqual(status, 0, stderr)
        self.assertIn(f"campaign survey: {self.root}", stdout)

    def test_the_json_form_carries_its_schema(self) -> None:
        status, stdout, _ = run_cli(
            ["campaign", "survey", str(self.root), "--json"]
        )
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stdout)["schema"], SURVEY_SCHEMA)

    def test_a_missing_directory_is_an_actionable_error(self) -> None:
        status, _stdout, stderr = run_cli(
            ["campaign", "survey", str(self.root / "nowhere")]
        )
        self.assertEqual(status, 2)
        self.assertIn("is not a directory", stderr)

    def test_the_campaign_group_lists_both_readings(self) -> None:
        status, stdout, _ = run_cli(["commands", "--group", "campaign"])
        self.assertEqual(status, 0)
        self.assertIn("campaign status", stdout)
        self.assertIn("campaign survey", stdout)


if __name__ == "__main__":
    unittest.main()
