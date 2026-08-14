"""Gate 0: is this function already matched in public?

Three lessons from measured campaigns are built into this command, because
each of them cost a campaign real time:

1. **Walking a family is not a search.** Public matches live in lineages
   unrelated to the scratch you inherited — a different person, a different
   preset, no shared parent. Following parents and children finds none of
   them.
2. **A name lookup misses scratches named after a data label.** People name a
   scratch after the symbol they were staring at, which is often a jump table
   or a string, not the function. The reliable binding is the *size*:
   `max_score` is the target's instruction count times 100, so a candidate
   with the same instruction count is worth reading whatever it is called.
3. **An address finds what a name does not.** In one measured sweep, an
   address-anchored lookup surfaced roughly 55 of 127 functions that a
   name-anchored lookup did not.

So a query here is a *set* of terms, each asked separately and merged, and
`--max-score` is a binding filter over the union rather than a search term.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import quote, urlparse

from .http_client import PoliteClient

DEFAULT_API_BASE = "https://decomp.me/api"

SEARCH_SCHEMA = "decomp-workbench-public-match-check-v1"

#: decomp.me binds one point of score to one hundredth of an instruction: a
#: 127-instruction target has `max_score` 12700. This is the size binding the
#: docstring's second lesson is about.
SCORE_UNITS_PER_INSTRUCTION = 100

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

ADDRESS_RE = re.compile(r"(?:0x)?(?P<digits>[0-9a-fA-F]{4,16})\Z")


@dataclass(frozen=True)
class SearchHit:
    """One public scratch, with only the fields a gate-0 decision needs."""

    slug: str
    name: str | None
    owner: str | None
    score: int | None
    max_score: int | None
    match_override: bool | None
    last_updated: str | None
    found_by: tuple[str, ...]

    @property
    def is_public_match(self) -> bool:
        """A site-verified zero: the site compiled it and found no difference."""

        return self.score == 0 and self.match_override is False

    @property
    def is_override_claim(self) -> bool:
        """An owner-declared match the site did not verify."""

        return self.match_override is True

    def as_dict(self, *, api_base: str) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "owner": self.owner,
            "score": self.score,
            "max_score": self.max_score,
            "match_override": self.match_override,
            "last_updated": self.last_updated,
            "found_by": list(self.found_by),
            "url": _scratch_url(self.slug, api_base=api_base),
            "public_match": self.is_public_match,
            "override_claim": self.is_override_claim,
        }


def _scratch_url(slug: str, *, api_base: str) -> str:
    parsed = urlparse(api_base)
    origin = (
        f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else "https://decomp.me"
    )
    return f"{origin}/scratch/{slug}"


def address_terms(address: str) -> tuple[str, ...]:
    """Return the spellings of `address` a scratch name might use.

    A name written by hand can hold any of `func_800C1A90`, `800c1a90`, or
    `0x800C1A90`. Searching one spelling and concluding "nothing public" is
    the mistake this exists to prevent.
    """

    match = ADDRESS_RE.fullmatch(address.strip())
    if match is None:
        raise ValueError(
            f"not a hexadecimal address: {address!r}. Pass something like "
            f"0x800C1A90 or 800c1a90."
        )
    digits = match.group("digits")
    ordered = (digits.upper(), digits.lower(), f"0x{digits.lower()}")
    seen: list[str] = []
    for term in ordered:
        if term not in seen:
            seen.append(term)
    return tuple(seen)


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _owner(value: Any) -> str | None:
    """Return a display name for the owner without copying an account record."""

    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("username", "name", "display_name"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
    return None


def _hit(payload: Any, term: str) -> SearchHit | None:
    if not isinstance(payload, dict):
        return None
    slug = payload.get("slug")
    if not isinstance(slug, str) or not slug:
        return None
    override = payload.get("match_override")
    return SearchHit(
        slug=slug,
        name=payload.get("name") if isinstance(payload.get("name"), str) else None,
        owner=_owner(payload.get("owner")),
        score=_integer(payload.get("score")),
        max_score=_integer(payload.get("max_score")),
        match_override=override if isinstance(override, bool) else None,
        last_updated=(
            payload.get("last_updated")
            if isinstance(payload.get("last_updated"), str)
            else None
        ),
        found_by=(term,),
    )


def search_url(term: str, *, api_base: str, page_size: int) -> str:
    return f"{api_base.rstrip('/')}/scratch?search={quote(term)}&page_size={page_size}"


def public_match_check(
    *,
    client: PoliteClient,
    query: str | None = None,
    address: str | None = None,
    max_score: int | None = None,
    instructions: int | None = None,
    api_base: str = DEFAULT_API_BASE,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Query the public search for every term, and report what came back."""

    terms: list[str] = []
    if query and query.strip():
        terms.append(query.strip())
    if address:
        terms.extend(address_terms(address))
    if not terms:
        raise ValueError(
            "nothing to search for. Give a function name, an --address, or "
            "both. --max-score binds the result size; the public search "
            "itself takes a term, so it cannot be the only input."
        )
    if instructions is not None and max_score is not None:
        raise ValueError("give --max-score or --instructions, not both")
    if instructions is not None:
        max_score = instructions * SCORE_UNITS_PER_INSTRUCTION
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))

    ordered: dict[str, SearchHit] = {}
    queries: list[dict[str, Any]] = []
    seen_terms: list[str] = []
    for term in terms:
        if term in seen_terms:
            continue
        seen_terms.append(term)
        url = search_url(term, api_base=api_base, page_size=page_size)
        payload = client.get_json(url)
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise ValueError(
                f"{url} did not answer with a search page: expected a 'results' list."
            )
        queries.append({"term": term, "url": url, "returned": len(results)})
        for item in results:
            hit = _hit(item, term)
            if hit is None:
                continue
            previous = ordered.get(hit.slug)
            ordered[hit.slug] = (
                hit
                if previous is None
                else replace(previous, found_by=(*previous.found_by, term))
            )

    hits = list(ordered.values())
    excluded = 0
    if max_score is not None:
        bound = [hit for hit in hits if hit.max_score == max_score]
        excluded = len(hits) - len(bound)
        hits = bound
    hits.sort(
        key=lambda hit: (hit.score if hit.score is not None else 1 << 30, hit.slug)
    )

    warnings: list[str] = []
    if max_score is not None and max_score % SCORE_UNITS_PER_INSTRUCTION:
        warnings.append(
            f"max_score={max_score} is not a multiple of "
            f"{SCORE_UNITS_PER_INSTRUCTION}; decomp.me binds it to the "
            f"target's instruction count times {SCORE_UNITS_PER_INSTRUCTION}. "
            f"If you meant an instruction count, pass --instructions."
        )

    matches = [hit for hit in hits if hit.is_public_match]
    claims = [hit for hit in hits if hit.is_override_claim]
    return {
        "schema": SEARCH_SCHEMA,
        "gate": "gate-0-public-novelty",
        "queries": queries,
        "max_score_binding": (
            None
            if max_score is None
            else {
                "max_score": max_score,
                "instructions": max_score / SCORE_UNITS_PER_INSTRUCTION,
                "excluded_results": excluded,
            }
        ),
        "warnings": warnings,
        "result_count": len(hits),
        "results": [hit.as_dict(api_base=api_base) for hit in hits],
        "public_matches": [hit.slug for hit in matches],
        "override_claims": [hit.slug for hit in claims],
        "verdict": (
            "public-match-exists"
            if matches
            else "override-claim-only"
            if claims
            else "no-public-match"
        ),
        "limits": [
            "The public search takes a term; family walks and name-only "
            "lookups both miss matches in unrelated lineages.",
            "An empty result is not proof that no public match exists — a "
            "scratch may be named after a data label rather than the "
            "function. Bind on --max-score as well.",
        ],
    }


def render_public_match_check(report: dict[str, Any]) -> list[str]:
    """Render the report for a person, loudest fact first."""

    matches = report["public_matches"]
    claims = report["override_claims"]
    headline = (
        f"public match check: {report['result_count']} scratches, "
        f"{len(matches)} site-verified match(es), {len(claims)} override claim(s)"
    )
    lines = [headline]
    terms = ", ".join(f"{item['term']!r}" for item in report["queries"])
    lines.append(f"queries: {terms}")
    binding = report["max_score_binding"]
    if binding is not None:
        lines.append(
            f"bound to max_score={binding['max_score']} "
            f"({binding['instructions']:g} instructions); "
            f"{binding['excluded_results']} other result(s) excluded"
        )
    for entry in report["results"]:
        score = "?" if entry["score"] is None else entry["score"]
        maximum = "?" if entry["max_score"] is None else entry["max_score"]
        common = (
            f"slug={entry['slug']} owner={entry['owner'] or '?'} "
            f"score={score}/{maximum} "
            f"override={_flag(entry['match_override'])} "
            f"updated={entry['last_updated'] or '?'}"
        )
        if entry["public_match"]:
            lines.append(f"!! MATCH  {common}")
            lines.append(f"           {entry['url']}")
        elif entry["override_claim"]:
            lines.append(f"!! CLAIM  {common}")
            lines.append(
                "           match_override=true: the owner declared this a "
                "match and the site did not verify it. Read it, do not trust "
                "the score."
            )
            lines.append(f"           {entry['url']}")
        else:
            lines.append(f"   near   {common}")
    lines.extend(f"warning: {item}" for item in report["warnings"])
    lines.append(_verdict_line(report))
    lines.extend(f"limit: {item}" for item in report["limits"])
    return lines


def _flag(value: bool | None) -> str:
    return "?" if value is None else ("true" if value else "false")


def _verdict_line(report: dict[str, Any]) -> str:
    if report["verdict"] == "public-match-exists":
        return (
            "gate 0: a site-verified public match already exists. Read it "
            "before spending a campaign on this function."
        )
    if report["verdict"] == "override-claim-only":
        return (
            "gate 0: only owner-declared matches were found. Verify one "
            "locally with check-scratch before treating it as done."
        )
    return (
        "gate 0: no public match found for these terms. That is not proof of "
        "novelty; try the address and the max_score binding too."
    )
