"""Project identity providers stay declarative, exact-site keyed, and fail closed."""

from __future__ import annotations

import unittest
from typing import Any

from decomp_workbench.reloc_surface import R_MIPS_26, Site
from decomp_workbench.relocation_identity import (
    IDENTITY_PROVIDER_SCHEMA,
    identity_report,
    parse_identity_provider,
)


def site() -> Site:
    return Site(
        symbol="callee",
        object="build/tu.o",
        section=".text",
        object_offset=4,
        type=R_MIPS_26,
    )


def provider(*, status: str = "resolved") -> dict[str, Any]:
    entry: dict[str, object] = {
        "object": "build/tu.o",
        "section": ".text",
        "object_offset": 4,
        "type": R_MIPS_26,
        "symbol": "callee",
        "status": status,
        "evidence": "canonical overlay ownership",
    }
    if status == "resolved":
        entry["identity"] = {
            "namespace": "overlay-section-offset",
            "module": "overlay7",
            "section": ".text",
            "offset": "0x120",
            "addend": 0,
        }
    return {"schema": IDENTITY_PROVIDER_SCHEMA, "entries": [entry]}


class RelocationIdentityTests(unittest.TestCase):
    def test_resolved_identity_is_joined_by_the_exact_site(self) -> None:
        report = identity_report([site()], parse_identity_provider(provider()))
        self.assertTrue(report["complete"])
        self.assertEqual(report["resolved"], 1)
        identity = report["entries"][0]["identity"]
        self.assertEqual(identity["module"], "overlay7")
        self.assertEqual(identity["offset"], 0x120)

    def test_missing_knowledge_is_unknown_not_a_contradiction(self) -> None:
        report = identity_report(
            [site()],
            parse_identity_provider(
                {
                    "schema": IDENTITY_PROVIDER_SCHEMA,
                    "entries": [],
                }
            ),
        )
        self.assertFalse(report["complete"])
        self.assertEqual((report["unknown"], report["contradicted"]), (1, 0))

    def test_a_contradiction_is_distinct_and_blocks_completeness(self) -> None:
        report = identity_report(
            [site()], parse_identity_provider(provider(status="contradicted"))
        )
        self.assertFalse(report["complete"])
        self.assertEqual(report["contradicted"], 1)

    def test_duplicate_exact_sites_are_refused(self) -> None:
        document = provider()
        document["entries"] = [document["entries"][0], document["entries"][0]]
        with self.assertRaisesRegex(ValueError, "duplicates"):
            parse_identity_provider(document)

    def test_unknown_entries_cannot_smuggle_an_identity(self) -> None:
        document = provider(status="unknown")
        document["entries"][0]["identity"] = {
            "namespace": "overlay",
            "module": "wrong",
            "section": ".text",
            "offset": 0,
        }
        with self.assertRaisesRegex(ValueError, "only when status=resolved"):
            parse_identity_provider(document)


if __name__ == "__main__":
    unittest.main()
