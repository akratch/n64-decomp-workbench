"""An offline transport double for the polite HTTP client.

The client takes its opener as a constructor argument precisely so the tests
never touch a network. This module supplies the one object that satisfies that
seam: a queue of scripted answers, plus the record of what was actually sent,
so a test can assert on the headers and on the pauses a client took as well as
on the report it produced.
"""

from __future__ import annotations

import email.message
import io
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


def message(headers: dict[str, str]) -> email.message.Message:
    """Return the header container `urllib` hands back on a real response."""

    container = email.message.Message()
    for key, value in headers.items():
        container[key] = value
    return container


@dataclass(frozen=True)
class Answer:
    """One scripted server response, success or failure."""

    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)
    #: A transport failure that happens before any status arrives.
    unreachable: str | None = None


def json_answer(payload: str, *, status: int = 200) -> Answer:
    return Answer(
        status=status,
        body=payload.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )


def html_answer(
    status: int, body: str = "<!doctype html><html>blocked</html>"
) -> Answer:
    return Answer(
        status=status,
        body=body.encode("utf-8"),
        headers={"Content-Type": "text/html; charset=utf-8"},
    )


class FakeOpener:
    """Answer each request from a script, recording what was asked."""

    def __init__(self, *answers: Answer) -> None:
        self.answers = list(answers)
        self.requests: list[urllib.request.Request] = []

    @property
    def urls(self) -> list[str]:
        return [request.full_url for request in self.requests]

    def open(self, request: urllib.request.Request, timeout: float) -> Any:
        self.requests.append(request)
        self.timeout = timeout
        if not self.answers:
            raise AssertionError(f"unscripted request: {request.full_url}")
        answer = self.answers.pop(0)
        if answer.unreachable is not None:
            raise urllib.error.URLError(answer.unreachable)
        if answer.status >= 400:
            raise urllib.error.HTTPError(
                request.full_url,
                answer.status,
                "scripted failure",
                message(answer.headers),
                io.BytesIO(answer.body),
            )
        return _Response(request.full_url, answer)


class _Response(io.BytesIO):
    def __init__(self, url: str, answer: Answer) -> None:
        super().__init__(answer.body)
        self.status = answer.status
        self.headers = message(answer.headers)
        self._url = url

    def geturl(self) -> str:
        return self._url


class RecordedSleep:
    """A `sleep` that records instead of waiting."""

    def __init__(self) -> None:
        self.waits: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)
