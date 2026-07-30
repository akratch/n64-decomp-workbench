"""Trace-to-source and retained-listing correlation without guessed provenance."""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .allocator_analysis import semantic_webs
from .globalcolor import GlobalColorTrace, optional_integer

SOURCE_CORRELATION_SCHEMA = "decomp-workbench-trace-source-v1"

LINE_MARKER_RE = re.compile(
    r"^\s*#\s*(?:line\s+)?(?P<line>\d+)"
    r'(?:\s+(?P<file>"(?:[^"\\]|\\.)*"))?(?:\s|$)'
)
LISTING_FILE_RE = re.compile(
    r"^\s*\.file\s+(?:(?P<number>\d+)\s+)?"
    r'(?P<file>"(?:[^"\\]|\\.)*")'
)
LISTING_LOC_RE = re.compile(
    r"^\s*\.loc\s+(?P<file>\d+)\s+(?P<line>\d+)"
    r"(?:\s+(?P<column>\d+))?"
)


def _quoted_path(value: str) -> str:
    """Decode a C-style quoted filename, refusing non-string literals."""

    decoded = ast.literal_eval(value)
    if not isinstance(decoded, str):
        raise ValueError(f"line-marker filename is not a string: {value}")
    return decoded


@dataclass(frozen=True)
class SourceLine:
    """One physical input line under its preprocessor logical location."""

    file: str
    line: int
    physical_line: int
    text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "physical_line": self.physical_line,
            "text": self.text,
        }


@dataclass(frozen=True)
class ListingLocation:
    """One retained-listing source-location directive."""

    file: str | None
    file_index: int
    line: int
    column: int | None
    listing_line: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "file_index": self.file_index,
            "line": self.line,
            "column": self.column,
            "listing_line": self.listing_line,
        }


def parse_line_marked_source(text: str, *, origin: str) -> list[SourceLine]:
    """Interpret standard ``# N "file"`` and ``#line N "file"`` markers."""

    current_file = origin
    logical_line = 1
    result: list[SourceLine] = []
    for physical_line, raw in enumerate(text.splitlines(), 1):
        marker = LINE_MARKER_RE.match(raw)
        if marker is not None:
            logical_line = int(marker.group("line"))
            quoted = marker.group("file")
            if quoted is not None:
                current_file = _quoted_path(quoted)
            continue
        result.append(
            SourceLine(
                file=current_file,
                line=logical_line,
                physical_line=physical_line,
                text=raw,
            )
        )
        logical_line += 1
    return result


def parse_listing_locations(text: str) -> list[ListingLocation]:
    """Read GNU-style ``.file``/``.loc`` evidence from a retained listing."""

    files: dict[int, str] = {}
    implicit_file = 1
    result: list[ListingLocation] = []
    for listing_line, raw in enumerate(text.splitlines(), 1):
        file_directive = LISTING_FILE_RE.match(raw)
        if file_directive is not None:
            number_text = file_directive.group("number")
            number = int(number_text) if number_text else implicit_file
            files[number] = _quoted_path(file_directive.group("file"))
            implicit_file = max(implicit_file, number + 1)
            continue
        location = LISTING_LOC_RE.match(raw)
        if location is None:
            continue
        file_index = int(location.group("file"))
        column = location.group("column")
        result.append(
            ListingLocation(
                file=files.get(file_index),
                file_index=file_index,
                line=int(location.group("line")),
                column=int(column) if column is not None else None,
                listing_line=listing_line,
            )
        )
    return result


def _file_matches(candidate: str, requested: str) -> bool:
    if candidate == requested:
        return True
    requested_path = Path(requested)
    return not requested_path.parent.parts and Path(candidate).name == requested


def correlate_trace_source(
    trace: GlobalColorTrace,
    *,
    source_text: str,
    source_origin: str,
    listing_text: str | None = None,
    source_file: str | None = None,
    proc: int | None = None,
) -> dict[str, Any]:
    """Join allocator web lines to source and listing records.

    The trace producer exposes a logical line number but not a reliable source
    filename. A match is therefore reported as unique, selected, ambiguous, or
    unresolved; the implementation never chooses the first include that happens
    to share the number.
    """

    source_lines = parse_line_marked_source(source_text, origin=source_origin)
    source_by_line: dict[int, list[SourceLine]] = defaultdict(list)
    for item in source_lines:
        source_by_line[item.line].append(item)
    listing_locations = (
        parse_listing_locations(listing_text) if listing_text is not None else []
    )
    listing_by_line: dict[int, list[ListingLocation]] = defaultdict(list)
    for listing_item in listing_locations:
        listing_by_line[listing_item.line].append(listing_item)

    rows: list[dict[str, Any]] = []
    counts = {"selected": 0, "unique": 0, "ambiguous": 0, "unresolved": 0}
    for web in semantic_webs(trace, proc=proc):
        trace_line = optional_integer(web.decision.detail.get("line"))
        candidates = list(source_by_line.get(trace_line or -1, []))
        if source_file is not None:
            candidates = [
                item for item in candidates if _file_matches(item.file, source_file)
            ]
        unique_source = {(item.file, item.line, item.text): item for item in candidates}
        candidates = sorted(
            unique_source.values(),
            key=lambda item: (item.file, item.line, item.physical_line),
        )
        if not candidates:
            state = "unresolved"
        elif len(candidates) == 1:
            state = "selected" if source_file is not None else "unique"
        else:
            state = "ambiguous"
        counts[state] += 1

        listing = list(listing_by_line.get(trace_line or -1, []))
        if len(candidates) == 1:
            selected_name = candidates[0].file
            exact_listing = [
                item
                for item in listing
                if item.file is not None and _file_matches(item.file, selected_name)
            ]
            if exact_listing:
                listing = exact_listing
        rows.append(
            {
                "fingerprint": web.fingerprint,
                "confidence": web.confidence,
                "phase": web.decision.phase_tag,
                "force_key": web.decision.force_key,
                "trace_local_web": web.decision.web,
                "trace_line": trace_line,
                "state": state,
                "source_candidates": [item.as_dict() for item in candidates[:8]],
                "source_candidates_truncated": len(candidates) > 8,
                "listing_locations": [item.as_dict() for item in listing[:16]],
                "listing_locations_truncated": len(listing) > 16,
            }
        )
    return {
        "schema": SOURCE_CORRELATION_SCHEMA,
        "evidence": "trace-source-correlation",
        "source_origin": source_origin,
        "source_file_filter": source_file,
        "listing_supplied": listing_text is not None,
        "web_count": len(rows),
        "correlated_webs": counts["selected"] + counts["unique"],
        "states": counts,
        "webs": rows,
        "proof": (
            "Trace logical lines were joined to retained preprocessor markers "
            "and optional .file/.loc directives. Ambiguous line-only matches "
            "are preserved and never promoted to source identity."
        ),
    }
