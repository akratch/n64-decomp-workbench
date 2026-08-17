"""A small, polite, explicitly invoked HTTP client for public decomp.me APIs.

The workbench is offline-first. The only reason this module exists is that two
commands — fetching an export and checking whether a match is already public —
answer questions that cannot be answered from local files, and every campaign
that answered them by hand rebuilt the same fragile `curl` invocation.

The design constraints are deliberate:

* **Standard library only.** The package depends on nothing at runtime, and a
  polite GET does not justify changing that.
* **The transport is injected.** :class:`PoliteClient` never reaches for a
  global opener, so the tests exercise every branch — success, refusal, rate
  limit, malformed body — without a network, and a caller can substitute a
  proxy-aware opener.
* **Honest identification.** The `User-Agent` names this package and its
  version. The remaining headers are the ordinary ones a browser sends,
  because the API is served to a browser and rejects a bare request; they are
  *not* an imitation of a particular browser build, and this module will not
  grow one. A refusal is reported as a refusal, with the offline route out.
* **One retry.** A transient failure deserves a second attempt; a server that
  refuses twice deserves to be left alone.
"""

from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from . import __version__

#: Where the package documents itself. Part of the honest identification: a
#: server operator who sees this traffic can find out what produced it.
PROJECT_URL = "https://github.com/akratch/n64-decomp-workbench"

USER_AGENT = f"n64-decomp-workbench/{__version__} (+{PROJECT_URL})"

#: Requests are refused without these. A browser sends them; the API is served
#: to that browser. `Referer` is the site's own origin because the endpoint is
#: the site's own API. Nothing here claims to be a specific browser build.
BROWSER_SHAPED_HEADERS: dict[str, str] = {
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://decomp.me/",
}

#: Compressed responses are accepted and decoded here; urllib does not decode
#: them for us, and a community server should not have to send an export twice
#: the size because a client could not be bothered.
ACCEPT_ENCODING = "gzip, deflate"

#: A response larger than this is refused unread. The largest thing either
#: command asks for is one scratch export.
MAX_RESPONSE_BYTES = 64 * 1024 * 1024

#: A `Retry-After` longer than this is reported rather than slept through: a
#: command that silently blocks for ten minutes is worse than one that says
#: when to come back.
MAX_RETRY_AFTER_SECONDS = 30.0

RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


class NetworkError(RuntimeError):
    """A request could not be completed. The message is user-facing."""


class RequestRefused(NetworkError):
    """The server answered, and the answer was "no"."""


class RateLimited(NetworkError):
    """The server asked for a wait longer than a command should impose."""


class ResourceNotFound(NetworkError):
    """The server has no such resource."""


class _TransientFailure(Exception):
    """The transport failed before any status arrived. Internal to this module."""

    def __init__(self, reason: str, cause: BaseException) -> None:
        super().__init__(reason)
        self.reason = reason
        self.cause = cause


class Opener(Protocol):
    """The one method :class:`PoliteClient` needs from a transport.

    `urllib.request.OpenerDirector` satisfies this, and so does a test double
    of a dozen lines. Keeping the surface this small is what makes the offline
    tests honest rather than a mock of our own logic.
    """

    def open(
        self, request: urllib.request.Request, timeout: float
    ) -> Any:  # pragma: no cover - structural
        ...


@dataclass(frozen=True)
class HttpResponse:
    """One completed exchange, whatever its status."""

    url: str
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    @property
    def content_type(self) -> str:
        return str(self.headers.get("Content-Type", "")).split(";")[0].strip().lower()

    def text(self, limit: int | None = None) -> str:
        decoded = self.body.decode("utf-8", errors="replace")
        return decoded if limit is None else decoded[:limit]

    def looks_like_a_web_page(self) -> bool:
        """Whether the body is HTML rather than the API document requested."""

        if self.content_type == "text/html":
            return True
        return self.body.lstrip()[:15].lower().startswith((b"<!doctype", b"<html"))


def _decode_body(raw: bytes, encoding: str) -> bytes:
    normalized = encoding.strip().lower()
    if normalized in ("", "identity"):
        return raw
    try:
        if normalized == "gzip":
            return gzip.decompress(raw)
        if normalized in ("deflate", "zlib"):
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return zlib.decompress(raw, -zlib.MAX_WBITS)
    except (OSError, zlib.error) as error:
        raise NetworkError(
            f"the server sent a {normalized} response the client could not "
            f"decode: {error}"
        ) from error
    raise NetworkError(f"unsupported response content-encoding: {encoding}")


def _read_bounded(stream: Any, url: str) -> bytes:
    body = stream.read(MAX_RESPONSE_BYTES + 1)
    if not isinstance(body, bytes):  # pragma: no cover - defensive
        body = bytes(body)
    if len(body) > MAX_RESPONSE_BYTES:
        raise NetworkError(
            f"response from {url} exceeds the "
            f"{MAX_RESPONSE_BYTES // (1024 * 1024)} MiB limit"
        )
    return body


def _headers_of(response: Any) -> dict[str, str]:
    headers = getattr(response, "headers", None)
    if headers is None:
        return {}
    items = getattr(headers, "items", None)
    return {str(key): str(value) for key, value in items()} if items else dict(headers)


def _retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    """Return the server's requested wait, ignoring the HTTP-date spelling.

    A date-shaped `Retry-After` is legal and rare; treating an unparsable one
    as "no advice" falls back to the client's own backoff, which is bounded.
    """

    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return None
    try:
        seconds = float(str(raw).strip())
    except ValueError:
        return None
    return max(0.0, seconds)


class PoliteClient:
    """Serialized, identified, timed-out, retry-once GETs."""

    def __init__(
        self,
        *,
        opener: Opener | None = None,
        timeout: float = 30.0,
        retries: int = 1,
        backoff_seconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        user_agent: str = USER_AGENT,
        contact: str | None = None,
    ) -> None:
        self._opener = opener if opener is not None else urllib.request.build_opener()
        self._timeout = timeout
        self._retries = max(0, retries)
        self._backoff = max(0.0, backoff_seconds)
        self._sleep = sleep
        self._user_agent = f"{user_agent} contact:{contact}" if contact else user_agent

    @property
    def user_agent(self) -> str:
        return self._user_agent

    def headers_for(self, accept: str) -> dict[str, str]:
        """Return the exact header set a request will carry."""

        return {
            "User-Agent": self._user_agent,
            "Accept": accept,
            "Accept-Encoding": ACCEPT_ENCODING,
            **BROWSER_SHAPED_HEADERS,
        }

    def get(self, url: str, *, accept: str = "application/json") -> HttpResponse:
        """Fetch `url`, raising a user-facing error for anything but success."""

        attempt = 0
        while True:
            try:
                response = self._attempt(url, accept=accept)
            except _TransientFailure as failure:
                if attempt >= self._retries:
                    raise NetworkError(
                        f"could not reach {url}: {failure.reason}. The "
                        f"workbench works offline; download the file in a "
                        f"browser and pass the local path instead."
                    ) from failure.cause
                self._sleep(self._backoff * (attempt + 1))
                attempt += 1
                continue
            if response.status == 200:
                return response
            if response.status in RETRYABLE_STATUSES and attempt < self._retries:
                self._wait(response, attempt=attempt, url=url)
                attempt += 1
                continue
            raise self._failure(response)

    def get_json(self, url: str) -> Any:
        """Fetch and parse one JSON document, naming what arrived instead."""

        response = self.get(url, accept="application/json")
        try:
            return json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            preview = response.text(limit=200).replace("\n", " ").strip()
            raise NetworkError(
                f"{url} did not answer with JSON ({error}). The first bytes "
                f"were: {preview!r}. If that looks like a web page, the API "
                f"path may have moved; check it in a browser."
            ) from error

    def _attempt(self, url: str, *, accept: str) -> HttpResponse:
        # A GET built here is never rendered through a shell and never
        # carries a body; the caller's URL is the whole request.
        request = urllib.request.Request(
            url, headers=self.headers_for(accept), method="GET"
        )
        try:
            raw = self._opener.open(request, timeout=self._timeout)
        except urllib.error.HTTPError as error:
            # An HTTPError *is* the response, and its body is the part that
            # explains a refusal, so it is normalized rather than raised on.
            with error:
                headers = _headers_of(error)
                body = _decode_body(
                    _read_bounded(error, url), headers.get("Content-Encoding", "")
                )
            return HttpResponse(
                url=url,
                status=int(getattr(error, "code", 0) or 0),
                body=body,
                headers=headers,
            )
        except urllib.error.URLError as error:
            raise _TransientFailure(str(error.reason), error) from error
        except OSError as error:
            raise _TransientFailure(str(error), error) from error
        with raw:
            headers = _headers_of(raw)
            body = _decode_body(
                _read_bounded(raw, url), headers.get("Content-Encoding", "")
            )
            reported = getattr(raw, "status", None) or getattr(raw, "code", None)
            status = int(reported) if reported is not None else 200
        return HttpResponse(url=url, status=status, body=body, headers=headers)

    def _wait(self, response: HttpResponse, *, attempt: int, url: str) -> None:
        requested = _retry_after_seconds(response.headers)
        if requested is not None and requested > MAX_RETRY_AFTER_SECONDS:
            raise RateLimited(
                f"{url} is rate limiting this client and asked for "
                f"{requested:g} seconds. Nothing was fetched. Re-run the "
                f"command after that wait; it is a volunteer-run server and "
                f"the request is not worth working around."
            )
        self._sleep(
            requested if requested is not None else self._backoff * (attempt + 1)
        )

    def _failure(self, response: HttpResponse) -> NetworkError:
        url, status = response.url, response.status
        if status == 404:
            return ResourceNotFound(
                f"{url} does not exist (HTTP 404). Check the slug or search "
                f"term; a scratch can also be deleted by its owner."
            )
        if status in (401, 403):
            interstitial = (
                " and answered with a web page rather than the API document"
                if response.looks_like_a_web_page()
                else ""
            )
            return RequestRefused(
                f"{url} refused this request (HTTP {status}){interstitial}.\n"
                f"The workbench sends an honest User-Agent naming itself and "
                f"its version ({self._user_agent}) plus the ordinary browser "
                f"headers, and it will not imitate a specific browser build "
                f"to get past a block — that is an arms race, and the site is "
                f"run by volunteers.\n"
                f"Do this instead: open the page in a browser, download what "
                f"you need, and point the workbench at the local file; or "
                f"wait and retry later; or ask the decomp.me maintainers for "
                f"API access if you need this regularly."
            )
        if status == 429:
            return RateLimited(
                f"{url} is rate limiting this client (HTTP 429) and it was "
                f"already retried once. Wait before trying again, and "
                f"serialize requests rather than running them in parallel."
            )
        if status >= 500:
            return NetworkError(
                f"{url} failed on the server side (HTTP {status}) and the "
                f"retry failed too. This is not something the command can "
                f"fix; try again later."
            )
        return NetworkError(f"{url} returned an unexpected HTTP {status}.")
