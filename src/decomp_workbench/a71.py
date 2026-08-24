"""Parse and compare the compact IDO 7.1 ``[A71]`` allocator trace.

The A71 producer records the allocator's final coloring order.  It is much
smaller than the IDO 5.3 CDX profile: there is no procedure or semantic-web
provenance, so ``(phase, web)`` is deliberately treated as a run-local key.
"""

from __future__ import annotations

import math
import re
import struct
from collections import Counter
from dataclasses import dataclass
from typing import cast

from .globalcolor import decode_forbidden_colors

A71_PREFIX = "[A71]"
A71_FIELD_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)")
A71_REQUIRED_FIELDS = frozenset(
    {
        "phase",
        "web",
        "sym",
        "class",
        "color",
        "savebits",
        "forbidden0",
        "forbidden1",
    }
)

# These mappings have direct IDO 7.1 object receipts.  Keeping the table local
# avoids silently extending the separately calibrated IDO 5.3 CDX color map to
# colors that the A71 campaign did not verify.
A71_COLOR_REGISTERS: dict[int, str] = {
    1: "v0",
    2: "v1",
    3: "a0",
    4: "a1",
    5: "a2",
    24: "$f0",
    25: "$f2",
    26: "$f12",
    27: "$f14",
    28: "$f16",
    29: "$f18",
}

# ``refs`` and ``defs`` existed in the first producer, but the recovered C
# read the wrong live-range offsets.  They must never become alignment inputs.
A71_UNVERIFIED_FIELDS = frozenset({"refs", "defs"})


def _decimal(value: str, *, field: str, line_number: int) -> int:
    try:
        return int(value, 10)
    except ValueError as error:
        raise ValueError(
            f"line {line_number}: A71 field {field} is not decimal: {value!r}"
        ) from error


def _hex_word(value: str, *, field: str, line_number: int) -> int:
    cleaned = value.removeprefix("0x").removeprefix("0X")
    if not re.fullmatch(r"[0-9a-fA-F]{1,8}", cleaned):
        raise ValueError(
            f"line {line_number}: A71 field {field} is not a 32-bit hex word: {value!r}"
        )
    return int(cleaned, 16)


def _priority_from_bits(bits: int) -> float:
    return cast(float, struct.unpack(">f", bits.to_bytes(4, byteorder="big"))[0])


def _json_float(value: float) -> float | str:
    if math.isfinite(value):
        return value
    if math.isnan(value):
        return "nan"
    return "inf" if value > 0 else "-inf"


@dataclass(frozen=True)
class A71Record:
    """One final-color record from the read-only IDO 7.1 trace point."""

    phase: int
    web: int
    symbol: int
    register_class: int
    color: int
    priority_bits: int
    forbidden0: int
    forbidden1: int
    trace_line: int

    @property
    def key(self) -> tuple[int, int]:
        return (self.phase, self.web)

    @property
    def priority(self) -> float:
        return _priority_from_bits(self.priority_bits)

    @property
    def register(self) -> str | None:
        return A71_COLOR_REGISTERS.get(self.color)

    @property
    def forbidden_colors(self) -> list[int]:
        return decode_forbidden_colors(self.forbidden0, self.forbidden1)

    def as_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "web": self.web,
            "symbol": self.symbol,
            "register_class": self.register_class,
            "color": self.color,
            "register": self.register,
            "priority": _json_float(self.priority),
            "priority_bits": f"0x{self.priority_bits:08x}",
            "forbidden0": f"0x{self.forbidden0:08x}",
            "forbidden1": f"0x{self.forbidden1:08x}",
            "forbidden_colors": self.forbidden_colors,
            "trace_line": self.trace_line,
        }


@dataclass(frozen=True)
class A71Trace:
    """A validated single-input A71 allocation stream."""

    records: tuple[A71Record, ...]
    ignored_diagnostic_lines: int = 0
    unverified_fields_seen: tuple[str, ...] = ()

    def selected(
        self,
        *,
        phase: int | None = None,
        web: int | None = None,
        register_class: int | None = None,
    ) -> list[A71Record]:
        return [
            record
            for record in self.records
            if (phase is None or record.phase == phase)
            and (web is None or record.web == web)
            and (register_class is None or record.register_class == register_class)
        ]

    def summary(self, records: list[A71Record] | None = None) -> dict[str, object]:
        selected = list(self.records) if records is None else records
        return {
            "record_count": len(selected),
            "phase_counts": dict(
                sorted(Counter(item.phase for item in selected).items())
            ),
            "class_counts": dict(
                sorted(Counter(item.register_class for item in selected).items())
            ),
            "ignored_diagnostic_lines": self.ignored_diagnostic_lines,
            "unverified_fields_seen": list(self.unverified_fields_seen),
        }


def parse_a71_trace(text: str) -> A71Trace:
    """Parse A71 records from a filtered trace or a mixed compiler log.

    Non-A71 diagnostics are counted and ignored.  A line that claims the A71
    prefix is validated strictly so a producer drift cannot masquerade as an
    allocator change.
    """

    records: list[A71Record] = []
    seen: set[tuple[int, int]] = set()
    unverified_seen: set[str] = set()
    ignored = 0
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line.startswith(A71_PREFIX):
            if line:
                ignored += 1
            continue
        fields = dict(A71_FIELD_RE.findall(line.removeprefix(A71_PREFIX)))
        missing = sorted(A71_REQUIRED_FIELDS - fields.keys())
        if missing:
            raise ValueError(
                f"line {line_number}: malformed A71 record; missing "
                + ", ".join(missing)
            )
        unverified_seen.update(A71_UNVERIFIED_FIELDS & fields.keys())
        record = A71Record(
            phase=_decimal(fields["phase"], field="phase", line_number=line_number),
            web=_decimal(fields["web"], field="web", line_number=line_number),
            symbol=_decimal(fields["sym"], field="sym", line_number=line_number),
            register_class=_decimal(
                fields["class"], field="class", line_number=line_number
            ),
            color=_decimal(fields["color"], field="color", line_number=line_number),
            priority_bits=_hex_word(
                fields["savebits"], field="savebits", line_number=line_number
            ),
            forbidden0=_hex_word(
                fields["forbidden0"], field="forbidden0", line_number=line_number
            ),
            forbidden1=_hex_word(
                fields["forbidden1"], field="forbidden1", line_number=line_number
            ),
            trace_line=line_number,
        )
        if record.key in seen:
            raise ValueError(
                f"line {line_number}: duplicate A71 phase/web key {record.key}"
            )
        seen.add(record.key)
        records.append(record)
    if not records:
        raise ValueError("trace contains no [A71] records")
    return A71Trace(
        records=tuple(records),
        ignored_diagnostic_lines=ignored,
        unverified_fields_seen=tuple(sorted(unverified_seen)),
    )


def _comparison_fields(record: A71Record) -> dict[str, int]:
    return {
        "symbol": record.symbol,
        "register_class": record.register_class,
        "color": record.color,
        "priority_bits": record.priority_bits,
        "forbidden0": record.forbidden0,
        "forbidden1": record.forbidden1,
    }


def compare_a71_traces(
    baseline: A71Trace,
    candidate: A71Trace,
    *,
    phase: int | None = None,
    web: int | None = None,
    register_class: int | None = None,
) -> dict[str, object]:
    """Diff two A71 streams on their explicitly run-local phase/web keys."""

    before_records = baseline.selected(
        phase=phase, web=web, register_class=register_class
    )
    after_records = candidate.selected(
        phase=phase, web=web, register_class=register_class
    )
    before = {record.key: record for record in before_records}
    after = {record.key: record for record in after_records}
    changes: list[dict[str, object]] = []
    for key in sorted(before.keys() | after.keys()):
        left = before.get(key)
        right = after.get(key)
        if left is None:
            assert right is not None
            changes.append(
                {
                    "status": "added",
                    "phase": key[0],
                    "web": key[1],
                    "changed_fields": [],
                    "baseline": None,
                    "candidate": right.as_dict(),
                }
            )
            continue
        if right is None:
            changes.append(
                {
                    "status": "removed",
                    "phase": key[0],
                    "web": key[1],
                    "changed_fields": [],
                    "baseline": left.as_dict(),
                    "candidate": None,
                }
            )
            continue
        left_fields = _comparison_fields(left)
        right_fields = _comparison_fields(right)
        changed_fields = [
            name for name in left_fields if left_fields[name] != right_fields[name]
        ]
        if changed_fields:
            changes.append(
                {
                    "status": "changed",
                    "phase": key[0],
                    "web": key[1],
                    "changed_fields": changed_fields,
                    "baseline": left.as_dict(),
                    "candidate": right.as_dict(),
                }
            )
    return {
        "format": "ido-7.1-a71-final-color",
        "filters": {
            "phase": phase,
            "web": web,
            "register_class": register_class,
        },
        "baseline_summary": baseline.summary(before_records),
        "candidate_summary": candidate.summary(after_records),
        "difference_count": len(changes),
        "changes": changes,
        "alignment_scope": "run-local-phase-web",
        "alignment_warning": (
            "A71 has no semantic-web provenance. Phase/web keys may be compared "
            "only for controlled inputs where numbering remains aligned; added "
            "or removed webs can shift later keys."
        ),
        "field_warning": (
            "Historical refs/defs fields read invalid recovered-source offsets "
            "and are ignored by parsing and comparison."
        ),
    }
