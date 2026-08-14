"""The polite client identifies itself, retries once, and refuses evasion.

Every test here runs against an injected transport double. No test in this
package opens a socket.
"""

from __future__ import annotations

import gzip
import unittest

from fake_http import Answer, FakeOpener, RecordedSleep, html_answer, json_answer

from decomp_workbench.http_client import (
    MAX_RETRY_AFTER_SECONDS,
    NetworkError,
    PoliteClient,
    RateLimited,
    RequestRefused,
    ResourceNotFound,
)

URL = "https://decomp.me/api/scratch/abcde"


def client(*answers: Answer, **overrides: object) -> tuple[PoliteClient, FakeOpener]:
    opener = FakeOpener(*answers)
    sleep = overrides.pop("sleep", RecordedSleep())
    return (
        PoliteClient(opener=opener, sleep=sleep, backoff_seconds=2.0, **overrides),  # type: ignore[arg-type]
        opener,
    )


class RequestShapeTests(unittest.TestCase):
    def test_every_request_names_the_workbench_and_its_version(self) -> None:
        polite, opener = client(json_answer('{"slug": "abcde"}'))
        polite.get_json(URL)
        sent = opener.requests[0]
        agent = str(sent.get_header("User-agent"))
        self.assertIn("n64-decomp-workbench/", agent)
        self.assertIn("github.com/akratch/n64-decomp-workbench", agent)
        # The ordinary headers an API served to a browser expects, and no
        # claim to be any particular browser build.
        self.assertEqual(sent.get_header("Accept"), "application/json")
        self.assertIsNotNone(sent.get_header("Accept-language"))
        self.assertIsNotNone(sent.get_header("Referer"))
        self.assertNotIn("Mozilla", agent)

    def test_a_contact_is_appended_to_the_identity_when_offered(self) -> None:
        polite, opener = client(json_answer("{}"), contact="me@example.invalid")
        polite.get_json(URL)
        self.assertIn(
            "contact:me@example.invalid",
            str(opener.requests[0].get_header("User-agent")),
        )

    def test_a_compressed_body_is_decoded_rather_than_returned_raw(self) -> None:
        polite, _opener = client(
            Answer(
                body=gzip.compress(b'{"ok": true}'),
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
            )
        )
        self.assertEqual(polite.get_json(URL), {"ok": True})


class FailureMessageTests(unittest.TestCase):
    def test_a_403_interstitial_is_explained_and_never_worked_around(self) -> None:
        polite, opener = client(html_answer(403))
        with self.assertRaises(RequestRefused) as refused:
            polite.get_json(URL)
        message = str(refused.exception)
        # The message has to carry three things: what happened, that the
        # workbench will not disguise itself, and what to do instead.
        self.assertIn("HTTP 403", message)
        self.assertIn("web page rather than the API document", message)
        self.assertIn("will not imitate a specific browser build", message)
        self.assertIn("browser", message)
        self.assertIn("maintainers", message)
        # A refusal is not retried: the server said no, clearly.
        self.assertEqual(len(opener.requests), 1)

    def test_a_missing_scratch_says_so_instead_of_failing_generically(self) -> None:
        polite, _opener = client(json_answer('{"detail": "Not found."}', status=404))
        with self.assertRaises(ResourceNotFound) as missing:
            polite.get_json(URL)
        self.assertIn("does not exist", str(missing.exception))

    def test_malformed_json_names_what_arrived_instead(self) -> None:
        polite, _opener = client(Answer(body=b"<html>not json</html>"))
        with self.assertRaises(NetworkError) as broken:
            polite.get_json(URL)
        message = str(broken.exception)
        self.assertIn("did not answer with JSON", message)
        self.assertIn("not json", message)

    def test_an_unreachable_host_points_at_the_offline_route(self) -> None:
        sleep = RecordedSleep()
        polite, opener = client(
            Answer(unreachable="name resolution failed"),
            Answer(unreachable="name resolution failed"),
            sleep=sleep,
        )
        with self.assertRaises(NetworkError) as unreachable:
            polite.get_json(URL)
        self.assertIn("could not reach", str(unreachable.exception))
        self.assertIn("works offline", str(unreachable.exception))
        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(sleep.waits, [2.0])


class BackoffTests(unittest.TestCase):
    def test_a_429_is_retried_once_after_the_requested_pause(self) -> None:
        sleep = RecordedSleep()
        polite, opener = client(
            Answer(status=429, headers={"Retry-After": "5"}),
            json_answer('{"slug": "abcde"}'),
            sleep=sleep,
        )
        self.assertEqual(polite.get_json(URL), {"slug": "abcde"})
        self.assertEqual(sleep.waits, [5.0])
        self.assertEqual(len(opener.requests), 2)

    def test_a_second_429_stops_rather_than_hammering_the_server(self) -> None:
        sleep = RecordedSleep()
        polite, opener = client(
            Answer(status=429),
            Answer(status=429),
            sleep=sleep,
        )
        with self.assertRaises(RateLimited) as limited:
            polite.get_json(URL)
        self.assertIn("already retried once", str(limited.exception))
        self.assertEqual(sleep.waits, [2.0])
        self.assertEqual(len(opener.requests), 2)

    def test_a_long_retry_after_is_reported_rather_than_slept_through(self) -> None:
        sleep = RecordedSleep()
        polite, opener = client(
            Answer(
                status=429,
                headers={"Retry-After": str(int(MAX_RETRY_AFTER_SECONDS) + 60)},
            ),
            sleep=sleep,
        )
        with self.assertRaises(RateLimited) as limited:
            polite.get_json(URL)
        self.assertIn("Nothing was fetched", str(limited.exception))
        self.assertEqual(sleep.waits, [])
        self.assertEqual(len(opener.requests), 1)

    def test_a_server_error_is_retried_once_then_reported(self) -> None:
        polite, opener = client(Answer(status=503), Answer(status=503))
        with self.assertRaises(NetworkError) as failed:
            polite.get_json(URL)
        self.assertIn("server side", str(failed.exception))
        self.assertEqual(len(opener.requests), 2)


if __name__ == "__main__":
    unittest.main()
