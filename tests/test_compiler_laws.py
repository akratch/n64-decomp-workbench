"""Tests for `guide laws`: compiler mechanism, era-scoped and evidence-tiered.

A laws document is only worth shipping if it cannot quietly become a page of
unsourced assertions. The tests here hold the two properties that keep it
honest: every law carries a receipt naming its evidence tier, and the page
records what each law corrected. The falsification history is the part a
reader cannot reconstruct and the part that makes the conclusions trustworthy,
so its absence is a test failure, not a style note.
"""

from __future__ import annotations

import contextlib
import io
import re
import unittest
from pathlib import Path

from decomp_workbench import field_guide
from decomp_workbench.cli import main
from decomp_workbench.field_guide import LAW_DOCUMENTS, law_eras, read_laws

ROOT = Path(__file__).resolve().parents[1]

#: Every `### Ln. Title` law heading.
LAW_HEADING_RE = re.compile(r"^### (L\d+)\. (.+)$", re.MULTILINE)


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class PackagedLawsTests(unittest.TestCase):
    def test_every_era_document_exists_in_the_checkout(self) -> None:
        for era, (document, _label) in LAW_DOCUMENTS.items():
            with self.subTest(era=era):
                self.assertTrue((ROOT / document).is_file(), document)

    def test_the_packaged_mirror_matches_the_documentation(self) -> None:
        """The wheel must ship the page a reader browses, not a fork of it."""

        for era, (document, _label) in LAW_DOCUMENTS.items():
            canonical = ROOT / document
            packaged = ROOT / "src" / "decomp_workbench" / document
            with self.subTest(era=era):
                self.assertEqual(
                    packaged.read_text(encoding="utf-8"),
                    canonical.read_text(encoding="utf-8"),
                    f"the packaged {era} laws drifted; run:\n"
                    f"  cp {document} src/decomp_workbench/{document}",
                )

    def test_read_laws_serves_the_document(self) -> None:
        for era, (_document, label) in LAW_DOCUMENTS.items():
            with self.subTest(era=era):
                self.assertIn(f"# Compiler laws: {label}", read_laws(era))

    def test_the_era_token_is_case_insensitive(self) -> None:
        self.assertEqual(read_laws("IDO53"), read_laws("ido53"))

    def test_the_document_and_prose_spellings_reach_the_same_page(self) -> None:
        """`ido-7.1.md`, "IDO 7.1" and `ido71` are one address, not three."""

        for spelling in ("ido-7.1", "IDO 7.1", "ido 7.1", "7.1"):
            with self.subTest(spelling=spelling):
                self.assertEqual(read_laws(spelling), read_laws("ido71"))

    def test_an_unknown_era_names_the_ones_that_ship(self) -> None:
        with self.assertRaises(ValueError) as caught:
            read_laws("ido62")
        for era in law_eras():
            self.assertIn(era, str(caught.exception))


class LawContentTests(unittest.TestCase):
    """Content invariants, held over **every** era the package ships.

    Parameterised by `LAW_DOCUMENTS` rather than written against one page: the
    properties below are what makes a laws document worth shipping, and a new
    era that quietly skipped them would be exactly the page this suite exists
    to prevent.
    """

    era = "ido53"

    def setUp(self) -> None:
        self.text = read_laws(self.era)
        self.sections = self._split(self.text)

    @staticmethod
    def _split(text: str) -> dict[str, str]:
        matches = list(LAW_HEADING_RE.finditer(text))
        sections: dict[str, str] = {}
        for position, match in enumerate(matches):
            end = (
                matches[position + 1].start()
                if position + 1 < len(matches)
                else len(text)
            )
            sections[match.group(1)] = text[match.start() : end]
        return sections

    def test_the_page_carries_laws(self) -> None:
        self.assertGreaterEqual(len(self.sections), 10)

    def test_law_numbers_are_contiguous_from_one(self) -> None:
        numbers = sorted(int(name[1:]) for name in self.sections)
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))

    def test_every_law_carries_a_receipt(self) -> None:
        missing = [
            name for name, body in self.sections.items() if "Receipt" not in body
        ]
        self.assertEqual(missing, [])

    def test_every_receipt_names_an_evidence_tier(self) -> None:
        untiered = [
            name
            for name, body in self.sections.items()
            if not re.search(r"\bT[123]\b", body)
        ]
        self.assertEqual(untiered, [])

    def test_the_page_states_its_era_scope(self) -> None:
        _document, label = LAW_DOCUMENTS[self.era]
        self.assertIn(label, self.text)
        # Hard-wrapped prose: match the sentence, not one page's line breaks.
        self.assertIn(
            "No law on this page has been tested", " ".join(self.text.split())
        )

    def test_the_page_defines_its_evidence_tiers(self) -> None:
        for tier in ("**T1**", "**T2**", "**T3**"):
            self.assertIn(tier, self.text)

    def test_the_identity_gate_is_stated(self) -> None:
        self.assertIn("identity gate", self.text.casefold())
        self.assertIn("byte-identical", self.text)

    def test_falsification_history_is_present_and_substantial(self) -> None:
        # The corrections are the most useful part of the page: several of
        # these laws overturned earlier, confidently-held claims.
        falsifies = sum(1 for body in self.sections.values() if "Falsifies" in body)
        self.assertGreaterEqual(falsifies, len(self.sections) // 2)

    def test_superseded_claims_are_listed_for_a_reader_of_older_notes(self) -> None:
        self.assertIn("should not believe", self.text)

    def test_no_impossibility_claim_discipline_is_recorded(self) -> None:
        self.assertIn("No impossibility claims", self.text)


class Ido71LawContentTests(LawContentTests):
    """The same invariants, on the 7.1 page.

    Subclassing rather than looping keeps each failure named after the era it
    belongs to; a shared loop reports "one era failed" and makes you find out
    which.
    """

    era = "ido71"

    def test_provisional_laws_say_what_evidence_is_missing(self) -> None:
        """A hedge without a gap named is a hedge that never gets closed."""

        # The page is hard-wrapped at 79 columns, so a phrase can be split
        # across a newline; match against the unwrapped body.
        bodies = {name: " ".join(body.split()) for name, body in self.sections.items()}
        provisional = [name for name, body in bodies.items() if "rovisional" in body]
        self.assertNotEqual(provisional, [])
        for name in provisional:
            with self.subTest(law=name):
                self.assertIn("Missing evidence", bodies[name])

    def test_the_five_zero_word_receipts_are_quoted(self) -> None:
        """The composition ladder is the page's load-bearing measurement."""

        for basin in ("fd6f35253f3f", "60ac03f5e694", "339c48483cf5", "3ba07814aab3"):
            self.assertIn(basin, self.text)


class LawEraCoverageTests(unittest.TestCase):
    def test_every_shipped_era_has_a_content_test_class(self) -> None:
        """A new era must not be able to ship without the invariants above."""

        covered = {
            cls.era for cls in (LawContentTests, *LawContentTests.__subclasses__())
        }
        self.assertEqual(covered, set(LAW_DOCUMENTS))


class GuideLawsCommandTests(unittest.TestCase):
    def test_the_era_listing_prints_without_an_era(self) -> None:
        status, output, _ = run_cli(["guide", "laws"])
        self.assertEqual(status, 0)
        for era, (_document, label) in LAW_DOCUMENTS.items():
            self.assertIn(era, output)
            self.assertIn(label, output)

    def test_an_era_prints_its_document(self) -> None:
        for era, (_document, label) in LAW_DOCUMENTS.items():
            with self.subTest(era=era):
                status, output, _ = run_cli(["guide", "laws", era])
                self.assertEqual(status, 0)
                self.assertIn(f"Compiler laws: {label}", output)
                self.assertIn("Evidence tiers", output)

    def test_an_unknown_era_fails_loudly(self) -> None:
        status, _, error = run_cli(["guide", "laws", "ido62"])
        self.assertEqual(status, 2)
        self.assertIn("ido53", error)
        self.assertIn("ido71", error)

    def test_the_topic_index_advertises_that_laws_exist(self) -> None:
        status, output, _ = run_cli(["guide"])
        self.assertEqual(status, 0)
        self.assertIn("guide laws", output)

    def test_a_second_argument_is_rejected_for_ordinary_topics(self) -> None:
        status, _, error = run_cli(["guide", "structure-buckets", "ido53"])
        self.assertEqual(status, 2)
        self.assertIn("guide laws", error)

    def test_ordinary_topics_still_work(self) -> None:
        status, output, _ = run_cli(["guide", "structure-buckets"])
        self.assertEqual(status, 0)
        self.assertIn("FIELD GUIDE", output)

    def test_law_eras_is_the_single_source_of_the_era_list(self) -> None:
        self.assertEqual(law_eras(), tuple(sorted(LAW_DOCUMENTS)))
        self.assertIn("law_eras", field_guide.__all__)


if __name__ == "__main__":
    unittest.main()
