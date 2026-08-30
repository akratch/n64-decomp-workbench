"""Readiness classification keeps stale and identity work out of source lanes."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from test_reloc_surface import candidate_object, module_document, shipped_image

from decomp_workbench.elf import read_elf
from decomp_workbench.evidence import artifact_record
from decomp_workbench.readiness import QUEUE_SCHEMA, readiness_report
from decomp_workbench.reloc_surface import parse_module_map, synthesize
from decomp_workbench.relocation_identity import (
    IDENTITY_PROVIDER_SCHEMA,
    identity_report,
    parse_identity_provider,
)
from decomp_workbench.relocation_proof import EVIDENCE_SCHEMA


class ReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "candidate.c"
        self.target = self.root / "target.o"
        self.candidate = self.root / "tu.c.o"
        self.source.write_text("int candidate;\n", encoding="utf-8")
        self.target.write_bytes(b"target")
        self.candidate.write_bytes(candidate_object())
        self.image = self.root / "target.z64"
        self.image.write_bytes(shipped_image())
        self.module_map = self.root / "module.json"
        self.module_map.write_text(json.dumps(module_document()), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def entry(self, symbol: str, **extra: object) -> dict[str, object]:
        artifacts = [
            artifact_record(self.source, role="source"),
            artifact_record(self.target, role="target-object"),
            artifact_record(self.candidate, role="candidate-object"),
        ]
        return {
            "symbol": symbol,
            "artifacts": artifacts,
            "measurement": {
                "exact": False,
                "words": 6,
                "verdict": "schedule",
                "artifact_sha256": {
                    "target-object": artifacts[1]["sha256"],
                    "candidate-object": artifacts[2]["sha256"],
                },
            },
            **extra,
        }

    def relocation_report(self, *, complete: bool) -> Path:
        path = self.root / f"reloc-{complete}.json"
        provider_path = self.root / f"provider-{complete}.json"
        module = parse_module_map(module_document())
        surface = synthesize(
            [(str(self.candidate.resolve()), read_elf(self.candidate))],
            module,
            self.image.read_bytes(),
        )
        provider = {
            "schema": IDENTITY_PROVIDER_SCHEMA,
            "entries": [
                {
                    "object": site.object,
                    "section": site.section,
                    "object_offset": site.object_offset,
                    "type": site.type,
                    "symbol": site.symbol,
                    "status": "resolved" if complete else "unknown",
                    **(
                        {
                            "identity": {
                                "namespace": "test-module-offset",
                                "module": module.name,
                                "section": site.section,
                                "offset": site.module_offset,
                                "addend": 0,
                            }
                        }
                        if complete
                        else {}
                    ),
                    "evidence": "synthetic fixture ownership",
                }
                for site in surface.sites
            ],
        }
        provider_path.write_text(json.dumps(provider), encoding="utf-8")
        report = surface.as_dict()
        report["evidence"] = {
            "schema": EVIDENCE_SCHEMA,
            "module": module.as_dict(),
            "artifacts": [
                artifact_record(self.module_map, role="module-map"),
                artifact_record(self.image, role="target-image"),
                artifact_record(self.candidate, role="candidate-object"),
                artifact_record(provider_path, role="identity-provider"),
            ],
        }
        report["identities"] = identity_report(
            surface.sites, parse_identity_provider(provider)
        )
        path.write_text(
            json.dumps(report),
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
        measurement = promotion["measurement"]
        assert isinstance(measurement, dict)
        measurement.update({"exact": True, "words": 0})
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

    def test_unbound_measurement_is_never_called_current(self) -> None:
        entry = self.entry("unbound")
        entry["measurement"] = {"exact": True, "words": 0}
        report = readiness_report({"schema": QUEUE_SCHEMA, "entries": [entry]})
        self.assertEqual(report["targets"][0]["class"], "remeasure")
        self.assertIn("artifact_sha256", report["targets"][0]["reasons"][0])

    def test_artifact_roles_are_mandatory(self) -> None:
        entry = self.entry("roleless")
        artifacts = entry["artifacts"]
        assert isinstance(artifacts, list)
        artifact = artifacts[1]
        assert isinstance(artifact, dict)
        del artifact["role"]
        report = readiness_report({"schema": QUEUE_SCHEMA, "entries": [entry]})
        self.assertEqual(report["targets"][0]["class"], "remeasure")
        self.assertIn("role", report["targets"][0]["reasons"][0])

    def test_classification_flags_and_exactness_are_typed(self) -> None:
        entry = self.entry("malformed")
        measurement = entry["measurement"]
        assert isinstance(measurement, dict)
        measurement["exact"] = "false"
        entry["relocation_required"] = "false"
        report = readiness_report({"schema": QUEUE_SCHEMA, "entries": [entry]})
        self.assertEqual(report["targets"][0]["class"], "remeasure")
        self.assertIn("must be a boolean", " ".join(report["targets"][0]["reasons"]))

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
