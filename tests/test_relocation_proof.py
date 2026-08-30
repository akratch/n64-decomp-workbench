"""A promotion receipt keeps static and linked relocation truth separate."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from decomp_workbench.evidence import EvidenceError, artifact_record
from decomp_workbench.linked_compare import LINKED_COMPARE_SCHEMA
from decomp_workbench.reloc_surface import SURFACE_SCHEMA
from decomp_workbench.relocation_identity import IDENTITY_REPORT_SCHEMA
from decomp_workbench.relocation_proof import (
    EVIDENCE_SCHEMA,
    build_relocation_proof,
    verify_relocation_proof,
)


class RelocationProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "candidate.c"
        self.candidate = self.root / "candidate.o"
        self.target = self.root / "target.z64"
        self.built = self.root / "built.z64"
        self.module_map = self.root / "module.json"
        self.source.write_text("void draw(void) {}\n", encoding="utf-8")
        self.candidate.write_bytes(b"candidate-object")
        self.target.write_bytes(bytes(0x200))
        self.built.write_bytes(bytes(0x200))
        self.module_map.write_text("{}\n", encoding="utf-8")
        self.fallback_path = self.root / "fallback.json"
        self.linked_path = self.root / "linked.json"
        self.receipt_path = self.root / "receipt.json"
        self._write_reports()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_reports(self, *, identities_complete: bool = True) -> None:
        fallback = {
            "schema": SURFACE_SCHEMA,
            "module": "overlay7",
            "ok": True,
            "corroborated": True,
            "identities": {
                "schema": IDENTITY_REPORT_SCHEMA,
                "sites": 1,
                "resolved": 1 if identities_complete else 0,
                "unknown": 0 if identities_complete else 1,
                "contradicted": 0,
                "complete": identities_complete,
                "entries": [],
            },
            "evidence": {
                "schema": EVIDENCE_SCHEMA,
                "module": {
                    "name": "overlay7",
                    "image_start": 0x100,
                    "image_end": 0x180,
                    "sections": [{"name": ".text", "offset": 0, "size": 0x80}],
                },
                "artifacts": [
                    artifact_record(self.module_map, role="module-map"),
                    artifact_record(self.target, role="target-image"),
                    artifact_record(self.candidate, role="candidate-object"),
                ],
            },
        }
        linked = {
            "schema": LINKED_COMPARE_SCHEMA,
            "class": "exact",
            "ok": True,
            "ranges": [
                {
                    "name": "draw",
                    "start": 0x110,
                    "end": 0x120,
                    "size": 0x10,
                    "class": "exact",
                }
            ],
            "evidence": {
                "schema": EVIDENCE_SCHEMA,
                "artifacts": [
                    artifact_record(self.built, role="built-image"),
                    artifact_record(self.target, role="target-image"),
                ],
            },
        }
        self.fallback_path.write_text(json.dumps(fallback), encoding="utf-8")
        self.linked_path.write_text(json.dumps(linked), encoding="utf-8")

    def _build(self) -> dict[str, Any]:
        return build_relocation_proof(
            fallback_report=self.fallback_path,
            linked_report=self.linked_path,
            symbol="draw",
            source=self.source,
            candidate_object=self.candidate,
        )

    def test_two_surfaces_remain_named_and_owner_is_derived(self) -> None:
        receipt = self._build()
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["owner"]["module"], "overlay7")
        self.assertEqual(receipt["owner"]["offset"], 0x10)
        self.assertEqual(
            set(receipt["surfaces"]), {"fallback_static", "promoted_linked"}
        )
        self.assertIn("does not claim", receipt["surfaces"]["fallback_static"]["claim"])

    def test_incomplete_identity_never_promotes(self) -> None:
        self._write_reports(identities_complete=False)
        with self.assertRaisesRegex(EvidenceError, "identities are incomplete"):
            self._build()

    def test_different_target_images_are_refused(self) -> None:
        other = self.root / "other.z64"
        other.write_bytes(b"different")
        linked = json.loads(self.linked_path.read_text(encoding="utf-8"))
        linked["evidence"]["artifacts"][1] = artifact_record(other, role="target-image")
        self.linked_path.write_text(json.dumps(linked), encoding="utf-8")
        with self.assertRaisesRegex(EvidenceError, "different target images"):
            self._build()

    def test_receipt_verification_rehashes_every_input(self) -> None:
        receipt = self._build()
        self.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        self.assertTrue(verify_relocation_proof(self.receipt_path)["pass"])
        self.candidate.write_bytes(b"changed")
        with self.assertRaisesRegex(EvidenceError, "stale"):
            verify_relocation_proof(self.receipt_path)

    def test_receipt_identity_is_content_based_not_timestamp_based(self) -> None:
        receipt = self._build()
        self.receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        stat = self.source.stat()
        os.utime(self.source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        self.assertTrue(verify_relocation_proof(self.receipt_path)["pass"])


if __name__ == "__main__":
    unittest.main()
