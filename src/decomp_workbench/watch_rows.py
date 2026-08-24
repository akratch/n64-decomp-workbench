"""A fixed watchlist of rows, rendered as healed/broken columns.

Scalar metrics answer "how far", and on a layout-shaped candidate they answer
it badly. One campaign's endgame had six rows that discriminated between the
mechanisms actually in play -- an integer ``addiu`` at row 49, four
floating-point temp assignments, one selector -- and the number that predicted
progress was not ``words``, ``opcodes`` or ``regs`` but *which of those six
were healed*. ``opcodes`` conflated schedule with allocation; ``words``
over-charged a block permutation by three orders of magnitude. The six-column
signature did neither, because it is not a distance at all: it is a per-site
truth table over sites the reader chose because they discriminate.

That watchlist was carried in an ad hoc scorer, retyped into three successive
shapes, and never available from the product. This module is it::

    r49 cx2 sx3 tm2 tm1 f1
     .   X   .   X   X   .

``.`` healed (the row does not differ), ``X`` broken (it does), ``?`` out of
range (neither stream has that row -- reported rather than silently counted as
healed, because a shortened candidate would otherwise print a perfect
signature).

Rows are *positional* indices into the comparison, the same coordinates
``diff_sites[].index`` and ``compare --show-diff`` use, so a row number read
off one report can be pasted into the next command without translation.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "BROKEN",
    "HEALED",
    "OUT_OF_RANGE",
    "WATCH_ROWS_SCHEMA",
    "WatchRow",
    "WatchRowError",
    "WatchRowResult",
    "evaluate_watch_rows",
    "parse_watch_rows",
    "watch_row_lines",
    "watch_row_payload",
    "watch_signature",
]

#: The identity of the watch-row *sub-document*. It is reported under
#: ``watch_schema``, never ``schema``: these keys are merged into a host
#: report that has a schema of its own.
WATCH_ROWS_SCHEMA = "decomp-workbench-watch-rows-v1"

HEALED = "."
BROKEN = "X"
#: Neither object has this row. Deliberately its own glyph: folding it into
#: ``.`` would let a candidate that lost the tail of the function print a
#: clean signature, which is the exact failure the signature exists to catch.
OUT_OF_RANGE = "?"


class WatchRowError(ValueError):
    """A watch-row specification could not be read."""


@dataclass(frozen=True)
class WatchRow:
    """One watched position, and the short name it prints under."""

    row: int
    label: str

    def as_dict(self) -> dict[str, Any]:
        return {"row": self.row, "label": self.label}


@dataclass(frozen=True)
class WatchRowResult:
    """What one watched row is doing in one comparison."""

    row: int
    label: str
    #: ``True`` when the row does not differ. ``None`` when the row is past
    #: the end of the comparison and there is nothing to say.
    healed: bool | None
    #: The ``diff_sites`` class when broken, otherwise ``None``.
    difference: str | None = None
    target: str | None = None
    candidate: str | None = None

    @property
    def column(self) -> str:
        if self.healed is None:
            return OUT_OF_RANGE
        return HEALED if self.healed else BROKEN

    def as_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "label": self.label,
            "healed": self.healed,
            "column": self.column,
            "class": self.difference,
            "target": self.target,
            "candidate": self.candidate,
        }


_LABEL_RE = re.compile(r"^(?P<label>[A-Za-z_][A-Za-z0-9_.-]*)=(?P<row>\d+)$")


def _row_entry(item: Any, *, origin: str) -> WatchRow:
    """Build one watch row from a JSON entry of any accepted shape."""

    if isinstance(item, bool):  # bool is an int; a True column is nonsense
        raise WatchRowError(f"{origin}: {item!r} is not a row number")
    if isinstance(item, int):
        return WatchRow(row=item, label=str(item))
    if isinstance(item, dict):
        if "row" not in item:
            raise WatchRowError(
                f'{origin}: an object entry needs a "row" key; got {sorted(item)!r}'
            )
        row = item["row"]
        if isinstance(row, bool) or not isinstance(row, int):
            raise WatchRowError(f'{origin}: "row" must be an integer, got {row!r}')
        label = item.get("label") or item.get("name") or str(row)
        return WatchRow(row=row, label=str(label))
    raise WatchRowError(
        f'{origin}: {item!r} is neither a row number nor an object with a "row" key'
    )


def _from_json(payload: Any, *, origin: str) -> list[WatchRow]:
    if isinstance(payload, dict):
        # Two object shapes: the named-set document `{"rows": [...]}` and the
        # bare `{"label": row}` mapping. Both turned up in the campaign's own
        # probe files, and refusing either would send the reader to rewrite a
        # file they already have.
        if "rows" in payload:
            rows = payload["rows"]
            if not isinstance(rows, list):
                raise WatchRowError(f'{origin}: "rows" must be a list')
            return [_row_entry(item, origin=origin) for item in rows]
        entries: list[WatchRow] = []
        for label, row in payload.items():
            if isinstance(row, bool) or not isinstance(row, int):
                raise WatchRowError(
                    f"{origin}: {label!r} maps to {row!r}, not a row number"
                )
            entries.append(WatchRow(row=row, label=str(label)))
        return entries
    if isinstance(payload, list):
        return [_row_entry(item, origin=origin) for item in payload]
    raise WatchRowError(
        f"{origin}: expected a list of rows, a {{label: row}} object, or an "
        'object with a "rows" list'
    )


def parse_watch_rows(spec: str | None) -> tuple[WatchRow, ...]:
    """Read ``49,1620`` / ``r49=49,cx2=1620`` / ``@probes.json``.

    The ``@file`` form exists for the same reason `ListFileAction` does: a
    watchlist is a durable artifact of a campaign, not a thing to retype, and
    a shell variable holding one does not word-split under zsh.

    Duplicate rows are an error rather than a deduplicated list: two columns
    under two names for one row is a probe file that has drifted, and a
    signature whose width does not match its header is unreadable.
    """

    if spec is None:
        return ()
    text = spec.strip()
    if not text:
        raise WatchRowError("--watch-rows was given an empty specification")
    if text.startswith("@"):
        location = Path(text[1:]).expanduser()
        try:
            payload = json.loads(location.read_text(encoding="utf-8"))
        except OSError as error:
            raise WatchRowError(f"cannot read the watch-row file: {error}") from None
        except ValueError as error:
            raise WatchRowError(f"{location} is not valid JSON: {error}") from None
        rows = _from_json(payload, origin=str(location))
    else:
        rows = []
        for token in (item.strip() for item in text.split(",")):
            if not token:
                continue
            labelled = _LABEL_RE.match(token)
            if labelled is not None:
                rows.append(
                    WatchRow(
                        row=int(labelled.group("row")),
                        label=labelled.group("label"),
                    )
                )
                continue
            if not token.isdigit():
                raise WatchRowError(
                    f"{token!r} is not a row number or a LABEL=ROW pair. "
                    "--watch-rows takes 49,1620,1677 or r49=49,cx2=1620, or "
                    "@probes.json for a named set"
                )
            rows.append(WatchRow(row=int(token), label=token))
    if not rows:
        raise WatchRowError("--watch-rows selected no rows")
    seen: dict[int, str] = {}
    for entry in rows:
        if entry.row < 0:
            raise WatchRowError(f"row {entry.row} is negative; rows are 0-based")
        previous = seen.get(entry.row)
        if previous is not None:
            raise WatchRowError(
                f"row {entry.row} is watched twice ({previous!r} and "
                f"{entry.label!r}); one row is one column"
            )
        seen[entry.row] = entry.label
    return tuple(rows)


def evaluate_watch_rows(
    rows: Sequence[WatchRow],
    *,
    diff_sites: Iterable[dict[str, Any]],
    compared_rows: int,
) -> tuple[WatchRowResult, ...]:
    """Score each watched row against one comparison's differing sites.

    ``compared_rows`` is how many positions the comparison covers -- the
    longer of the two instruction streams. A watched row past it is
    :data:`OUT_OF_RANGE`, never healed.
    """

    sites = {int(site["index"]): site for site in diff_sites}
    results: list[WatchRowResult] = []
    for entry in rows:
        if entry.row >= compared_rows:
            results.append(
                WatchRowResult(row=entry.row, label=entry.label, healed=None)
            )
            continue
        site = sites.get(entry.row)
        if site is None:
            results.append(
                WatchRowResult(row=entry.row, label=entry.label, healed=True)
            )
            continue
        results.append(
            WatchRowResult(
                row=entry.row,
                label=entry.label,
                healed=False,
                difference=str(site.get("class")) if site.get("class") else None,
                target=(
                    None if site.get("target") is None else str(site.get("target"))
                ),
                candidate=(
                    None
                    if site.get("candidate") is None
                    else str(site.get("candidate"))
                ),
            )
        )
    return tuple(results)


def watch_signature(results: Sequence[WatchRowResult]) -> str:
    """Render the compact column string, e.g. ``.X.XX.``."""

    return "".join(item.column for item in results)


def watch_row_payload(results: Sequence[WatchRowResult]) -> dict[str, Any]:
    """The machine-readable half: the array, the signature, and the tally.

    Every key is prefixed, ``watch_schema`` included. This payload is always
    *merged into* a host document -- a comparison, a ranked row, a wave row --
    and a bare ``schema`` key here overwrote the host's own identity, so a
    ``compare --json --watch-rows`` document announced itself as a watch-row
    set and every ranked row claimed to be one. The sub-document's identity is
    worth keeping; owning the top-level name is not.
    """

    return {
        "watch_schema": WATCH_ROWS_SCHEMA,
        "watch_rows": [item.as_dict() for item in results],
        "watch_signature": watch_signature(results),
        "watch_healed": sum(1 for item in results if item.healed is True),
        "watch_broken": sum(1 for item in results if item.healed is False),
        "watch_out_of_range": sum(1 for item in results if item.healed is None),
    }


def watch_header(results: Sequence[WatchRowResult]) -> str:
    """The label row a signature is read under, one column per watched row."""

    return " ".join(item.label for item in results)


def watch_row_lines(results: Sequence[WatchRowResult]) -> list[str]:
    """Render the signature and then the per-site detail for broken rows."""

    if not results:
        return []
    widths = [max(len(item.label), 1) for item in results]
    header = " ".join(
        item.label.ljust(width) for item, width in zip(results, widths, strict=True)
    )
    columns = " ".join(
        item.column.ljust(width) for item, width in zip(results, widths, strict=True)
    )
    healed = sum(1 for item in results if item.healed is True)
    broken = sum(1 for item in results if item.healed is False)
    missing = sum(1 for item in results if item.healed is None)
    tally = f"{healed} healed, {broken} broken"
    if missing:
        tally += f", {missing} out of range"
    lines = [
        f"watch rows ({HEALED}=healed {BROKEN}=broken"
        + (f" {OUT_OF_RANGE}=out of range" if missing else "")
        + f"): {tally}",
        f"  {header}",
        f"  {columns}",
        f"  signature={watch_signature(results)}",
    ]
    for item in results:
        if item.healed is None:
            lines.append(
                f"  [{item.row:>5}] {item.label}: past the end of the "
                "comparison; neither object has this row"
            )
            continue
        if item.healed:
            continue
        lines.append(f"  [{item.row:>5}] {item.label}: {item.difference or 'differs'}")
        if item.target is not None:
            lines.append(f"          target    {item.target}")
        if item.candidate is not None:
            lines.append(f"          candidate {item.candidate}")
    return lines
