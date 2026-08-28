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
        """A hedge without a gap named is a hedge that never gets closed.

        The page shipped with two provisional clauses (L9's owning pass,
        L11's survival condition); both were closed by directed probes the
        same day. Any *future* provisional clause must name its missing
        evidence; none existing is the healthy state.
        """

        # The page is hard-wrapped at 79 columns, so a phrase can be split
        # across a newline; match against the unwrapped body.
        bodies = {name: " ".join(body.split()) for name, body in self.sections.items()}
        provisional = [name for name, body in bodies.items() if "Provisional:" in body]
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


class SingleLawLookupTests(unittest.TestCase):
    """`guide laws ERA LAW`: the address a verdict footer prints.

    Footers cited individual laws (`decomp-workbench guide laws ido71 L2`) for
    a release before the command could answer one, so a reader who pasted the
    citation got the whole page and had to find the law by hand.
    """

    def test_a_law_is_addressable_by_its_number(self) -> None:
        law = field_guide.read_law("ido53", "L64")
        self.assertEqual(law.name, "L64")
        self.assertIn("t6 t7 t8 t9 t0", law.title + " ".join(law.lines))
        self.assertIn("ugen", law.section)

    def test_every_spelling_of_a_citation_reaches_the_law(self) -> None:
        for spelling in ("L64", "l64", "64", "law 64", " L64 "):
            with self.subTest(spelling=spelling):
                self.assertEqual(field_guide.read_law("ido53", spelling).name, "L64")

    def test_an_unknown_law_names_the_range_that_exists(self) -> None:
        with self.assertRaises(ValueError) as caught:
            field_guide.read_law("ido53", "L999")
        self.assertIn("L1-L", str(caught.exception))

    def test_the_parse_covers_every_law_on_every_shipped_page(self) -> None:
        for era in LAW_DOCUMENTS:
            with self.subTest(era=era):
                parsed = field_guide.laws(era)
                headings = LAW_HEADING_RE.findall(read_laws(era))
                self.assertEqual(sorted(parsed), sorted(name for name, _ in headings))
                for name, law in parsed.items():
                    self.assertTrue(law.lines[0].startswith(f"### {name}."), name)
                    self.assertTrue(law.section, f"{era} {name} has no pass heading")

    def test_the_command_prints_one_law_and_its_address(self) -> None:
        status, output, error = run_cli(["guide", "laws", "ido53", "L65"])
        self.assertEqual(status, 0)
        self.assertEqual(error, "")
        self.assertIn("COMPILER LAWS  IDO 5.3  L65", output)
        self.assertIn("phantom pop", output)
        self.assertIn("docs/compiler-laws/ido-5.3.md", output)
        # The whole page is one command away, and it is not this one.
        self.assertNotIn("### L64.", output)
        self.assertIn("decomp-workbench guide laws ido53", output)

    def test_an_unknown_law_fails_loudly_instead_of_printing_the_page(
        self,
    ) -> None:
        status, output, error = run_cli(["guide", "laws", "ido53", "L999"])
        self.assertEqual(status, 2)
        self.assertNotIn("### L1.", output)
        self.assertIn("L999", error)

    def test_a_third_argument_without_laws_is_refused(self) -> None:
        status, _, error = run_cli(["guide", "pool-position", "ido53", "L66"])
        self.assertEqual(status, 2)
        self.assertIn("laws", error)


class LawCrossLinkTests(unittest.TestCase):
    """Every campaign-verified law must be reachable from a residual's footer.

    A law nobody is routed to is a law the next campaign re-derives, which is
    exactly how these nine came to be measured twice.
    """

    def cited(self) -> set[tuple[str, str]]:
        return {
            (era, law)
            for entries in field_guide.PASS_LAWS.values()
            for era, law, _summary in entries
        }

    def test_every_cited_law_exists_on_the_page_it_names(self) -> None:
        for era, law in sorted(self.cited()):
            with self.subTest(era=era, law=law):
                self.assertEqual(field_guide.read_law(era, law).name, law)

    def test_the_table_is_keyed_on_the_passes_the_verdict_can_name(self) -> None:
        """A law filed under a pass no verdict emits is a law nobody reads."""

        from decomp_workbench.view import OWNING_PASS_VALUES

        self.assertLessEqual(set(field_guide.PASS_LAWS), set(OWNING_PASS_VALUES))
        for playbook, passes in field_guide.PLAYBOOK_PASSES.items():
            with self.subTest(playbook=playbook):
                self.assertIn(playbook, field_guide.PLAYBOOK_LEVERS)
                self.assertLessEqual(set(passes), set(OWNING_PASS_VALUES))

    def test_the_campaign_laws_are_each_cited_somewhere(self) -> None:
        """L69 is cited by the routing footer; the rest by an owning pass."""

        from decomp_workbench.view import PERMUTER_ROUTING_STEPS

        routed = " ".join(PERMUTER_ROUTING_STEPS)
        cited = {law for _era, law in self.cited()}
        for law in ("L62", "L63", "L64", "L65", "L66", "L67", "L68", "L70"):
            with self.subTest(law=law):
                self.assertIn(law, cited)
        self.assertIn("L69", routed)

    def test_a_footer_prints_the_law_as_a_pasteable_command(self) -> None:
        steps = field_guide.pass_law_steps("ugen-temp-ring")
        citation = next(step for step in steps if step.startswith("law L64:"))
        self.assertIn("decomp-workbench guide laws ido53 L64", citation)
        # Pasteable means it runs.
        status, _, error = run_cli(citation.split("decomp-workbench ")[1].split())
        self.assertEqual(status, 0, error)

    def test_a_lever_family_prints_the_law_its_pass_owns(self) -> None:
        status, output, _ = run_cli(["guide", "stack-frame-recovery"])
        self.assertEqual(status, 0)
        self.assertIn("law L63:", output)
        self.assertIn("decomp-workbench guide laws ido53 L63", output)

    def test_a_family_aimed_at_no_written_down_pass_gains_no_line(self) -> None:
        self.assertEqual(field_guide.playbook_law_steps("post-match-cleanup"), ())

    def test_a_pass_with_no_law_gains_no_line(self) -> None:
        self.assertEqual(field_guide.pass_law_steps("unknown"), ())
