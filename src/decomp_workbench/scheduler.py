"""Stable scheduler trace schema, parser, differential view, and guarded patching."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

TRACE_PREFIX = "[DKWB-SCHED-V1]"
TRACE_SCHEMA = "decomp-workbench-scheduler-trace-v1"
PROFILE_SCHEMA = "decomp-workbench-scheduler-profile-v1"
INSTRUMENT_RESULT_SCHEMA = "decomp-workbench-scheduler-instrument-v1"
FIELD_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)")
REQUIRED_FIELDS = (
    "proc",
    "block",
    "cycle",
    "word",
    "opcode",
    "line",
    "ready",
    "chosen",
    "tie",
)


@dataclass(frozen=True)
class SchedulerEvent:
    """One named scheduler selection, independent of emulated node addresses."""

    proc: int
    block: int
    cycle: int
    word: int
    opcode: str
    line: int
    ready: int
    chosen: str
    tie: str

    @property
    def key(self) -> tuple[int, int, int]:
        return self.proc, self.block, self.cycle

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["word"] = f"0x{self.word:08x}"
        return value


def _integer(fields: dict[str, str], name: str, line: int) -> int:
    try:
        return int(fields[name], 0)
    except (KeyError, ValueError):
        raise ValueError(
            f"scheduler trace line {line} has invalid integer field {name!r}"
        ) from None


def parse_scheduler_trace(text: str) -> tuple[list[SchedulerEvent], list[str]]:
    """Parse only the stable named record and preserve unrelated diagnostics."""

    events: list[SchedulerEvent] = []
    ignored: list[str] = []
    seen: set[tuple[int, int, int]] = set()
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.startswith(TRACE_PREFIX):
            if line.strip():
                ignored.append(line)
            continue
        field_pairs = FIELD_RE.findall(line[len(TRACE_PREFIX) :])
        fields = dict(field_pairs)
        if len(fields) != len(field_pairs):
            counts: dict[str, int] = {}
            for name, _value in field_pairs:
                counts[name] = counts.get(name, 0) + 1
            repeated = sorted(name for name, count in counts.items() if count > 1)
            raise ValueError(
                f"scheduler trace line {line_number} repeats field(s): "
                + ", ".join(repeated)
            )
        missing = [name for name in REQUIRED_FIELDS if name not in fields]
        if missing:
            raise ValueError(
                f"scheduler trace line {line_number} is missing field(s): "
                + ", ".join(missing)
            )
        event = SchedulerEvent(
            proc=_integer(fields, "proc", line_number),
            block=_integer(fields, "block", line_number),
            cycle=_integer(fields, "cycle", line_number),
            word=_integer(fields, "word", line_number),
            opcode=fields["opcode"],
            line=_integer(fields, "line", line_number),
            ready=_integer(fields, "ready", line_number),
            chosen=fields["chosen"],
            tie=fields["tie"],
        )
        if event.ready < 1:
            raise ValueError(
                f"scheduler trace line {line_number} has ready={event.ready}; "
                "the selected node itself must be ready"
            )
        if event.key in seen:
            raise ValueError(f"scheduler trace repeats proc/block/cycle {event.key}")
        seen.add(event.key)
        events.append(event)
    return events, ignored


def scheduler_report(
    events: list[SchedulerEvent],
    *,
    proc: int | None = None,
    block: int | None = None,
) -> dict[str, Any]:
    """Return a focused, bounded scheduler report."""

    selected = [
        event
        for event in events
        if (proc is None or event.proc == proc)
        and (block is None or event.block == block)
    ]
    return {
        "schema": TRACE_SCHEMA,
        "proof": (
            "Compiler-decision evidence only. A scheduler trace does not prove "
            "that candidate C is original or object-exact."
        ),
        "events": [event.as_dict() for event in selected],
        "event_count": len(selected),
        "ready_set_ties": sum(event.ready > 1 for event in selected),
        "procedures": sorted({event.proc for event in events}),
        "blocks": sorted({event.block for event in selected}),
    }


def compare_scheduler_traces(
    target: list[SchedulerEvent],
    candidate: list[SchedulerEvent],
) -> dict[str, Any]:
    """Align scheduler decisions by procedure, block, and cycle."""

    target_by_key = {event.key: event for event in target}
    candidate_by_key = {event.key: event for event in candidate}
    differences = []
    for key in sorted(set(target_by_key) | set(candidate_by_key)):
        expected = target_by_key.get(key)
        actual = candidate_by_key.get(key)
        if expected == actual:
            continue
        differences.append(
            {
                "proc": key[0],
                "block": key[1],
                "cycle": key[2],
                "target": expected.as_dict() if expected else None,
                "candidate": actual.as_dict() if actual else None,
                "changed": [
                    field
                    for field in (
                        "word",
                        "opcode",
                        "line",
                        "ready",
                        "chosen",
                        "tie",
                    )
                    if expected is None
                    or actual is None
                    or getattr(expected, field) != getattr(actual, field)
                ],
            }
        )
    return {
        "schema": "decomp-workbench-scheduler-diff-v1",
        "target_events": len(target),
        "candidate_events": len(candidate),
        "difference_count": len(differences),
        "differences": differences,
        "proof": ("Aligned compiler-decision evidence, not source-match evidence."),
    }


def instrument_scheduler_source(
    source: str,
    profile: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Apply a hash-pinned, exact-anchor external scheduler profile."""

    if profile.get("schema") != PROFILE_SCHEMA:
        raise ValueError(f"scheduler profile schema must be {PROFILE_SCHEMA}")
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if profile.get("source_sha256") != digest:
        raise ValueError(
            f"scheduler profile source SHA-256 does not match the input ({digest})"
        )
    injections = profile.get("injections")
    if not isinstance(injections, list) or not injections:
        raise ValueError("scheduler profile requires at least one injection")
    instrumented = source
    applied = 0
    for index, injection in enumerate(injections):
        if not isinstance(injection, dict):
            raise ValueError(f"scheduler injection {index} must be an object")
        anchor = injection.get("anchor")
        text = injection.get("text")
        position = injection.get("position")
        if (
            not isinstance(anchor, str)
            or not anchor
            or not isinstance(text, str)
            or position not in {"before", "after"}
        ):
            raise ValueError(
                f"scheduler injection {index} requires anchor, text, and "
                "position=before|after"
            )
        count = instrumented.count(anchor)
        if count != 1:
            raise ValueError(
                f"scheduler injection {index} anchor matched {count} times; "
                "exactly one is required"
            )
        replacement = text + anchor if position == "before" else anchor + text
        instrumented = instrumented.replace(anchor, replacement, 1)
        applied += 1
    for token in (TRACE_PREFIX, *(f"{name}=" for name in REQUIRED_FIELDS)):
        if token not in instrumented:
            raise ValueError(
                f"scheduler profile does not emit required token {token!r}"
            )
    report = {
        "schema": INSTRUMENT_RESULT_SCHEMA,
        "profile": profile.get("name"),
        "input_sha256": digest,
        "output_sha256": hashlib.sha256(instrumented.encode("utf-8")).hexdigest(),
        "injections": applied,
        "calibration_required": [
            "tracing-off section identity",
            "positive-control event",
            "unedited as0/as1 replay",
            "collateral functions",
            "project output",
        ],
    }
    return instrumented, report


def load_scheduler_profile(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("scheduler profile must be a JSON object")
    return value
