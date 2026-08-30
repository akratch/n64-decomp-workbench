"""A promotion receipt keeps static and linked relocation truth separate."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from test_reloc_surface import (
    MODULE_START,
    TU_OFFSET,
    candidate_object,
    module_document,
    shipped_image,
)

from decomp_workbench.elf import read_elf
from decomp_workbench.evidence import EvidenceError, artifact_record
from decomp_workbench.linked_compare import RANGES_SCHEMA, ImageRange, compare_images
from decomp_workbench.reloc_surface import parse_module_map, synthesize
from decomp_workbench.relocation_identity import (
    IDENTITY_PROVIDER_SCHEMA,
    identity_report,
    parse_identity_provider,
)
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
        self.candidate = self.root / "tu.c.o"
        self.target = self.root / "target.z64"
        self.built = self.root / "built.z64"
        self.module_map = self.root / "module.json"
        self.source.write_text("void draw(void) {}\n", encoding="utf-8")
        self.candidate.write_bytes(candidate_object())
        self.target.write_bytes(shipped_image())
        self.built.write_bytes(shipped_image())
        self.module_map.write_text(json.dumps(module_document()), encoding="utf-8")
        self.identity_provider = self.root / "identities.json"
        self.range_map = self.root / "ranges.json"
        self.fallback_path = self.root / "fallback.json"
        self.linked_path = self.root / "linked.json"
        self.receipt_path = self.root / "receipt.json"
        self._write_reports()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_reports(self, *, identities_complete: bool = True) -> None:
        module = parse_module_map(module_document())
        surface = synthesize(
            [(str(self.candidate.resolve()), read_elf(self.candidate))],
            module,
            self.target.read_bytes(),
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
                    "status": "resolved" if identities_complete else "unknown",
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
                        if identities_complete
                        else {}
                    ),
                    "evidence": "synthetic fixture ownership",
                }
                for site in surface.sites
            ],
        }
        self.identity_provider.write_text(json.dumps(provider), encoding="utf-8")
        fallback = surface.as_dict()
        fallback["identities"] = identity_report(
            surface.sites, parse_identity_provider(provider)
        )
        fallback["evidence"] = {
            "schema": EVIDENCE_SCHEMA,
            "module": module.as_dict(),
            "artifacts": [
                artifact_record(self.module_map, role="module-map"),
                artifact_record(self.target, role="target-image"),
                artifact_record(self.candidate, role="candidate-object"),
                artifact_record(self.identity_provider, role="identity-provider"),
            ],
        }
        ranges = [
            ImageRange("draw", MODULE_START + TU_OFFSET, MODULE_START + TU_OFFSET + 16)
        ]
        self.range_map.write_text(
            json.dumps(
                {"schema": RANGES_SCHEMA, "ranges": [item.as_dict() for item in ranges]}
            ),
            encoding="utf-8",
        )
        linked = compare_images(
            self.built.read_bytes(),
            self.target.read_bytes(),
            ranges,
            built_name=str(self.built),
            target_name=str(self.target),
        ).as_dict()
        linked["evidence"] = {
            "schema": EVIDENCE_SCHEMA,
            "artifacts": [
                artifact_record(self.built, role="built-image"),
                artifact_record(self.target, role="target-image"),
                artifact_record(self.range_map, role="range-map"),
            ],
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
        self.assertEqual(receipt["owner"]["module"], "m1")
        self.assertEqual(receipt["owner"]["offset"], TU_OFFSET)
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

    def test_fabricated_identity_claim_is_refused(self) -> None:
        fallback = json.loads(self.fallback_path.read_text(encoding="utf-8"))
        fallback["identities"]["entries"][0]["identity"]["offset"] += 4
        self.fallback_path.write_text(json.dumps(fallback), encoding="utf-8")
        with self.assertRaisesRegex(EvidenceError, "identities disagree"):
            self._build()

    def test_fabricated_linked_verdict_is_refused(self) -> None:
        linked = json.loads(self.linked_path.read_text(encoding="utf-8"))
        linked["ranges"][0]["class"] = "text-exact"
        self.linked_path.write_text(json.dumps(linked), encoding="utf-8")
        with self.assertRaisesRegex(EvidenceError, "bound inputs"):
            self._build()

    def test_cropped_linked_range_is_refused(self) -> None:
        linked = json.loads(self.linked_path.read_text(encoding="utf-8"))
        linked["ranges"][0]["start"] += 4
        self.linked_path.write_text(json.dumps(linked), encoding="utf-8")
        with self.assertRaisesRegex(EvidenceError, "bound range map"):
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
