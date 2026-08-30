"""Readiness classification keeps stale and identity work out of source lanes."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.evidence import artifact_record
from decomp_workbench.readiness import QUEUE_SCHEMA, readiness_report
from decomp_workbench.reloc_surface import SURFACE_SCHEMA
from decomp_workbench.relocation_identity import IDENTITY_REPORT_SCHEMA
from decomp_workbench.relocation_proof import EVIDENCE_SCHEMA


class ReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "candidate.c"
        self.target = self.root / "target.o"
        self.candidate = self.root / "candidate.o"
        self.source.write_text("int candidate;\n", encoding="utf-8")
        self.target.write_bytes(b"target")
        self.candidate.write_bytes(b"candidate")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def entry(self, symbol: str, **extra: object) -> dict[str, object]:
        return {
            "symbol": symbol,
            "artifacts": [
                artifact_record(self.source, role="source"),
                artifact_record(self.target, role="target-object"),
                artifact_record(self.candidate, role="candidate-object"),
            ],
            "measurement": {"exact": False, "words": 6, "verdict": "schedule"},
            **extra,
        }

    def relocation_report(self, *, complete: bool) -> Path:
        path = self.root / f"reloc-{complete}.json"
        path.write_text(
            json.dumps(
                {
                    "schema": SURFACE_SCHEMA,
                    "evidence": {
                        "schema": EVIDENCE_SCHEMA,
                        "artifacts": [
                            artifact_record(self.target, role="target-image"),
                            artifact_record(self.candidate, role="candidate-object"),
                        ],
                    },
                    "identities": {
                        "schema": IDENTITY_REPORT_SCHEMA,
                        "sites": 2,
                        "resolved": 2 if complete else 0,
                        "unknown": 0 if complete else 2,
                        "contradicted": 0,
                        "complete": complete,
                    },
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_queue_is_split_by_actual_readiness(self) -> None:
        incomplete = self.relocation_report(complete=False)
        complete = self.relocation_report(complete=True)
        promotion = self.entry(
            "promotion",
            relocation_required=True,
            relocation_report=artifact_record(complete, role="relocation-report"),
        )
        promotion["measurement"] = {"exact": True, "words": 0}
        report = readiness_report(
            {
                "schema": QUEUE_SCHEMA,
                "entries": [
                    self.entry("source"),
                    self.entry(
                        "identity",
                        relocation_required=True,
                        relocation_report=artifact_record(
                            incomplete, role="relocation-report"
                        ),
                    ),
                    promotion,
                    self.entry("plateau", plateau=True),
                ],
            }
        )
        self.assertEqual(report["source_queue"], ["source", "plateau"])
        self.assertEqual(report["maintenance_queue"], ["identity"])
        self.assertEqual(report["promotion_queue"], ["promotion"])
        plateau = next(row for row in report["targets"] if row["symbol"] == "plateau")
        self.assertIn("new evidence-producing mechanism", plateau["next"])

    def test_changed_artifact_routes_to_remeasurement(self) -> None:
        entry = self.entry("stale")
        self.candidate.write_bytes(b"changed")
        report = readiness_report({"schema": QUEUE_SCHEMA, "entries": [entry]})
        self.assertEqual(report["maintenance_queue"], ["stale"])
        self.assertEqual(report["targets"][0]["class"], "remeasure")
        self.assertIn("stale", report["targets"][0]["reasons"][0])

    def test_missing_measurement_is_never_called_codegen_ready(self) -> None:
        entry = self.entry("unmeasured")
        del entry["measurement"]
        report = readiness_report({"schema": QUEUE_SCHEMA, "entries": [entry]})
        self.assertEqual(report["targets"][0]["class"], "remeasure")

    def test_changed_relocation_report_routes_to_remeasurement(self) -> None:
        relocation = self.relocation_report(complete=True)
        entry = self.entry(
            "stale-relocation",
            relocation_required=True,
            relocation_report=artifact_record(relocation, role="relocation-report"),
        )
        relocation.write_text("{}\n", encoding="utf-8")
        report = readiness_report({"schema": QUEUE_SCHEMA, "entries": [entry]})
        self.assertEqual(report["targets"][0]["class"], "remeasure")
        self.assertIn(
            "relocation report cannot be trusted", report["targets"][0]["reasons"][0]
        )


if __name__ == "__main__":
    unittest.main()
