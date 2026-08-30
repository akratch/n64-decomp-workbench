"""Stable PRE/speculative-hoist decision records and guarded instrumentation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

TRACE_PREFIX = "[DKWB-PRE-V1]"
TRACE_SCHEMA = "decomp-workbench-pre-trace-v1"
PROFILE_SCHEMA = "decomp-workbench-pre-profile-v1"
INSTRUMENT_SCHEMA = "decomp-workbench-pre-instrument-v1"
FIELD_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)")
DECISIONS = frozenset({"insert", "hoist", "retain", "reject", "kill"})
REQUIRED_FIELDS = ("proc", "block", "expression", "decision", "reason", "line")


@dataclass(frozen=True)
class PreDecision:
    """One PRE or speculative-hoist decision named without pointer identities."""

    proc: int
    block: int
    expression: str
    decision: str
    reason: str
    line: int
    candidate: str | None = None
    availability: str | None = None
    cost: int | None = None

    @property
    def key(self) -> tuple[int, int, str]:
        return self.proc, self.block, self.expression

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _integer(fields: Mapping[str, str], name: str, line: int) -> int:
    try:
        return int(fields[name], 0)
    except (KeyError, ValueError):
        raise ValueError(
            f"PRE trace line {line} has invalid integer field {name!r}"
        ) from None


def parse_pre_trace(text: str) -> tuple[list[PreDecision], list[str]]:
    """Parse versioned records and retain unrelated compiler diagnostics."""

    decisions: list[PreDecision] = []
    ignored: list[str] = []
    seen: set[tuple[int, int, str]] = set()
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.startswith(TRACE_PREFIX):
            if line.strip():
                ignored.append(line)
            continue
        pairs = FIELD_RE.findall(line[len(TRACE_PREFIX) :])
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError(f"PRE trace line {line_number} repeats a field")
        missing = [name for name in REQUIRED_FIELDS if name not in fields]
        if missing:
            raise ValueError(
                f"PRE trace line {line_number} is missing field(s): "
                + ", ".join(missing)
            )
        decision = fields["decision"]
        if decision not in DECISIONS:
            raise ValueError(
                f"PRE trace line {line_number} has unsupported decision {decision!r}"
            )
        cost = _integer(fields, "cost", line_number) if "cost" in fields else None
        item = PreDecision(
            proc=_integer(fields, "proc", line_number),
            block=_integer(fields, "block", line_number),
            expression=fields["expression"],
            decision=decision,
            reason=fields["reason"],
            line=_integer(fields, "line", line_number),
            candidate=fields.get("candidate"),
            availability=fields.get("availability"),
            cost=cost,
        )
        if item.key in seen:
            raise ValueError(
                "PRE trace repeats proc/block/expression " + repr(item.key)
            )
        seen.add(item.key)
        decisions.append(item)
    return decisions, ignored


def pre_report(
    decisions: Sequence[PreDecision], *, proc: int | None = None
) -> dict[str, Any]:
    selected = [item for item in decisions if proc is None or item.proc == proc]
    counts = {decision: 0 for decision in sorted(DECISIONS)}
    for item in selected:
        counts[item.decision] += 1
    return {
        "schema": TRACE_SCHEMA,
        "events": [item.as_dict() for item in selected],
        "event_count": len(selected),
        "decisions": {key: value for key, value in counts.items() if value},
        "procedures": sorted({item.proc for item in decisions}),
        "proof": (
            "Compiler-decision evidence: this records where PRE/hoisting accepted "
            "or rejected an expression. It does not prove source originality or "
            "object equality."
        ),
    }


def compare_pre_traces(
    target: Sequence[PreDecision], candidate: Sequence[PreDecision]
) -> dict[str, Any]:
    expected = {item.key: item for item in target}
    actual = {item.key: item for item in candidate}
    differences = []
    for key in sorted(set(expected) | set(actual)):
        left = expected.get(key)
        right = actual.get(key)
        if left == right:
            continue
        differences.append(
            {
                "proc": key[0],
                "block": key[1],
                "expression": key[2],
                "target": left.as_dict() if left else None,
                "candidate": right.as_dict() if right else None,
                "changed": [
                    field
                    for field in (
                        "decision",
                        "reason",
                        "line",
                        "candidate",
                        "availability",
                        "cost",
                    )
                    if left is None
                    or right is None
                    or getattr(left, field) != getattr(right, field)
                ],
            }
        )
    return {
        "schema": "decomp-workbench-pre-diff-v1",
        "target_events": len(target),
        "candidate_events": len(candidate),
        "difference_count": len(differences),
        "differences": differences,
        "proof": "Aligned PRE decision evidence, not source-match evidence.",
    }


def instrument_pre_source(
    source: str, profile: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Apply a source-hash-pinned list of uniqueness-checked injections."""

    if profile.get("schema") != PROFILE_SCHEMA:
        raise ValueError(f"PRE profile schema must be {PROFILE_SCHEMA}")
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if profile.get("source_sha256") != digest:
        raise ValueError(f"PRE profile source SHA-256 does not match input ({digest})")
    injections = profile.get("injections")
    if not isinstance(injections, Sequence) or isinstance(injections, str | bytes):
        raise ValueError("PRE profile injections must be a non-empty list")
    if not injections:
        raise ValueError("PRE profile injections must be a non-empty list")
    instrumented = source
    for index, raw in enumerate(injections):
        if not isinstance(raw, Mapping):
            raise ValueError(f"PRE injection {index} must be an object")
        anchor = raw.get("anchor")
        text = raw.get("text")
        position = raw.get("position")
        if (
            not isinstance(anchor, str)
            or not anchor
            or not isinstance(text, str)
            or position not in {"before", "after"}
        ):
            raise ValueError(
                f"PRE injection {index} requires anchor, text, and "
                "position=before|after"
            )
        count = instrumented.count(anchor)
        if count != 1:
            raise ValueError(
                f"PRE injection {index} anchor matched {count} times; "
                "exactly one required"
            )
        replacement = text + anchor if position == "before" else anchor + text
        instrumented = instrumented.replace(anchor, replacement, 1)
    for token in (TRACE_PREFIX, *(f"{field}=" for field in REQUIRED_FIELDS)):
        if token not in instrumented:
            raise ValueError(f"PRE profile does not emit required token {token!r}")
    return instrumented, {
        "schema": INSTRUMENT_SCHEMA,
        "profile": profile.get("name"),
        "input_sha256": digest,
        "output_sha256": hashlib.sha256(instrumented.encode("utf-8")).hexdigest(),
        "injections": len(injections),
        "calibration_required": [
            "tracing-off section identity",
            "positive-control accept decision",
            "positive-control reject decision",
            "collateral procedures",
        ],
    }


def load_pre_profile(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("PRE profile must be a JSON object")
    return value


__all__ = [
    "INSTRUMENT_SCHEMA",
    "PROFILE_SCHEMA",
    "TRACE_SCHEMA",
    "PreDecision",
    "compare_pre_traces",
    "instrument_pre_source",
    "load_pre_profile",
    "parse_pre_trace",
    "pre_report",
]
