"""Gate 0 asks every spelling, binds on size, and shouts about a match.

Each campaign lesson the command exists for has a test here: a name-only
lookup that misses a data-label-named scratch, an address that finds what the
name did not, and the two rows a reader must never scroll past — a
site-verified zero, and an owner-declared match the site never verified.

The transport is the scripted double from `fake_http`; nothing opens a socket.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from unittest import mock

from fake_http import Answer, FakeOpener, RecordedSleep, json_answer

from decomp_workbench import decompme_cli
from decomp_workbench.cli import main
from decomp_workbench.decompme_search import address_terms, public_match_check
from decomp_workbench.http_client import PoliteClient


def page(*results: dict[str, object]) -> Answer:
    return json_answer(json.dumps({"count": len(results), "results": list(results)}))


def scratch(
    slug: str,
    *,
    name: str = "func_800C1A90",
    owner: str = "someone",
    score: int = 20,
    max_score: int = 12700,
    match_override: bool = False,
) -> dict[str, object]:
    return {
        "slug": slug,
        "name": name,
        "owner": {"username": owner},
        "score": score,
        "max_score": max_score,
        "match_override": match_override,
        "last_updated": "2026-05-01T10:00:00Z",
    }


def client(*answers: Answer) -> tuple[PoliteClient, FakeOpener]:
    opener = FakeOpener(*answers)
    return PoliteClient(opener=opener, sleep=RecordedSleep()), opener


class AddressTermTests(unittest.TestCase):
    def test_an_address_is_searched_in_every_spelling_a_name_might_use(self) -> None:
        self.assertEqual(
            address_terms("0x800C1A90"), ("800C1A90", "800c1a90", "0x800c1a90")
        )
        self.assertEqual(address_terms("800c1a90"), address_terms("0x800C1A90"))

    def test_something_that_is_not_an_address_is_refused_clearly(self) -> None:
        with self.assertRaises(ValueError) as error:
            address_terms("main")
        self.assertIn("not a hexadecimal address", str(error.exception))


class SearchTests(unittest.TestCase):
    def test_a_site_verified_zero_is_the_loudest_thing_in_the_report(self) -> None:
        polite, _opener = client(page(scratch("aBcDe", score=0)))
        report = public_match_check(client=polite, query="func_800C1A90")
        self.assertEqual(report["verdict"], "public-match-exists")
        self.assertEqual(report["public_matches"], ["aBcDe"])
        self.assertTrue(report["results"][0]["public_match"])
        self.assertEqual(report["results"][0]["url"], "https://decomp.me/scratch/aBcDe")

    def test_an_owner_declared_match_is_separated_from_a_verified_one(self) -> None:
        polite, _opener = client(page(scratch("claim", score=400, match_override=True)))
        report = public_match_check(client=polite, query="func_800C1A90")
        self.assertEqual(report["verdict"], "override-claim-only")
        self.assertEqual(report["override_claims"], ["claim"])
        self.assertEqual(report["public_matches"], [])

    def test_the_address_finds_a_scratch_the_name_did_not(self) -> None:
        polite, opener = client(
            page(),
            page(scratch("byaddr", name="D_800C1A90", score=0)),
            page(),
            page(),
        )
        report = public_match_check(
            client=polite, query="func_800C1A90", address="0x800C1A90"
        )
        self.assertEqual(report["public_matches"], ["byaddr"])
        self.assertEqual(report["results"][0]["found_by"], ["800C1A90"])
        # One request per distinct spelling: the name, then the three the
        # address can be written as.
        self.assertEqual(len(opener.requests), 4)
        self.assertIn("search=func_800C1A90", opener.urls[0])
        self.assertIn("search=800C1A90", opener.urls[1])

    def test_one_scratch_found_by_two_terms_is_reported_once(self) -> None:
        polite, _opener = client(
            page(scratch("both", score=0)),
            page(scratch("both", score=0)),
            page(),
            page(),
        )
        report = public_match_check(
            client=polite, query="func_800C1A90", address="800C1A90"
        )
        self.assertEqual(report["result_count"], 1)
        self.assertEqual(
            report["results"][0]["found_by"], ["func_800C1A90", "800C1A90"]
        )

    def test_the_max_score_binding_keeps_a_data_label_named_scratch(self) -> None:
        """The second campaign lesson: bind on size, not on the name."""

        polite, _opener = client(
            page(
                scratch("right", name="jtbl_800C1A90", score=0, max_score=12700),
                scratch("wrong", name="func_800C1A90", score=0, max_score=4400),
            )
        )
        report = public_match_check(client=polite, query="800C1A90", instructions=127)
        self.assertEqual(report["public_matches"], ["right"])
        self.assertEqual(report["max_score_binding"]["max_score"], 12700)
        self.assertEqual(report["max_score_binding"]["excluded_results"], 1)

    def test_an_instruction_count_passed_as_a_max_score_is_flagged(self) -> None:
        polite, _opener = client(page(scratch("aBcDe")))
        report = public_match_check(client=polite, query="x", max_score=127)
        self.assertTrue(report["warnings"])
        self.assertIn("--instructions", report["warnings"][0])

    def test_no_results_reports_a_verdict_and_refuses_to_claim_novelty(self) -> None:
        polite, _opener = client(page())
        report = public_match_check(client=polite, query="func_800C1A90")
        self.assertEqual(report["verdict"], "no-public-match")
        self.assertEqual(report["results"], [])
        self.assertTrue(any("not proof" in limit for limit in report["limits"]))

    def test_a_page_without_results_is_a_clear_failure_not_an_empty_answer(
        self,
    ) -> None:
        polite, _opener = client(json_answer('{"detail": "moved"}'))
        with self.assertRaises(ValueError) as error:
            public_match_check(client=polite, query="func_800C1A90")
        self.assertIn("did not answer with a search page", str(error.exception))

    def test_a_result_missing_a_slug_is_skipped_rather_than_crashing(self) -> None:
        polite, _opener = client(
            json_answer(json.dumps({"results": [{"name": "no slug"}, scratch("ok")]}))
        )
        report = public_match_check(client=polite, query="x")
        self.assertEqual([entry["slug"] for entry in report["results"]], ["ok"])

    def test_nothing_to_search_for_says_why_max_score_cannot_stand_alone(self) -> None:
        polite, opener = client()
        with self.assertRaises(ValueError) as error:
            public_match_check(client=polite, max_score=12700)
        self.assertIn("takes a term", str(error.exception))
        self.assertEqual(opener.requests, [])


class CommandTests(unittest.TestCase):
    def run_cli(self, arguments: list[str], *answers: Answer) -> tuple[int, str, str]:
        polite, _opener = client(*answers)
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(decompme_cli, "build_client", return_value=polite),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_the_terminal_report_shouts_about_a_match(self) -> None:
        status, stdout, stderr = self.run_cli(
            ["public-match-check", "func_800C1A90"],
            page(scratch("aBcDe", score=0), scratch("other")),
        )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("!! MATCH  slug=aBcDe", stdout)
        self.assertIn("   near   slug=other", stdout)
        self.assertIn("gate 0: a site-verified public match already exists", stdout)

    def test_fail_on_match_is_the_gate_a_campaign_can_run_in_ci(self) -> None:
        status, _stdout, _stderr = self.run_cli(
            ["public-match-check", "func_800C1A90", "--fail-on-match"],
            page(scratch("aBcDe", score=0)),
        )
        self.assertEqual(status, 1)
        clear, _stdout, _stderr = self.run_cli(
            ["public-match-check", "func_800C1A90", "--fail-on-match"], page()
        )
        self.assertEqual(clear, 0)

    def test_json_carries_the_schema_and_the_gate(self) -> None:
        status, stdout, _stderr = self.run_cli(
            ["scratch", "public-match-check", "func_800C1A90", "--json"],
            page(scratch("aBcDe", score=0)),
        )
        payload = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertEqual(payload["schema"], "decomp-workbench-public-match-check-v1")
        self.assertEqual(payload["gate"], "gate-0-public-novelty")

    def test_a_refusal_becomes_a_structured_json_error(self) -> None:
        from fake_http import html_answer

        status, stdout, _stderr = self.run_cli(
            ["public-match-check", "func_800C1A90", "--json"], html_answer(403)
        )
        payload = json.loads(stdout)
        self.assertEqual(status, 2)
        self.assertEqual(payload["schema"], "decomp-workbench-error-v1")
        self.assertIn("HTTP 403", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
