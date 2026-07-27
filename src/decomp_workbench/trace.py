"""Parsers and models for IDO static-recomp diagnostic traces."""

from __future__ import annotations

import collections
import re
from dataclasses import asdict, dataclass, field
from typing import Iterable


FIELD_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)=([^\s]+)")
UGEN_TAG_RE = re.compile(r"^(?:CODEX|DKWB)[-_]([A-Za-z0-9_-]+)")

MIPS_REGISTERS = {
    "zero": 0,
    "at": 1,
    "v0": 2,
    "v1": 3,
    "a0": 4,
    "a1": 5,
    "a2": 6,
    "a3": 7,
    "t0": 8,
    "t1": 9,
    "t2": 10,
    "t3": 11,
    "t4": 12,
    "t5": 13,
    "t6": 14,
    "t7": 15,
    "s0": 16,
    "s1": 17,
    "s2": 18,
    "s3": 19,
    "s4": 20,
    "s5": 21,
    "s6": 22,
    "s7": 23,
    "t8": 24,
    "t9": 25,
    "k0": 26,
    "k1": 27,
    "gp": 28,
    "sp": 29,
    "fp": 30,
    "s8": 30,
    "ra": 31,
}
REGISTER_NAMES = {
    number: name
    for name, number in MIPS_REGISTERS.items()
    if name != "s8"
}


def parse_integer(value: str) -> int | None:
    """Parse decimal, ``0x`` hexadecimal, or bare hexadecimal values."""

    cleaned = value.rstrip(",;")
    try:
        return int(cleaned, 0)
    except ValueError:
        if re.fullmatch(r"[0-9a-fA-F]+", cleaned) and re.search(
            r"[a-fA-F]", cleaned
        ):
            return int(cleaned, 16)
    return None


def parse_register(value: str) -> int:
    """Parse a numeric or conventional MIPS register name."""

    cleaned = value.strip().lower().removeprefix("$")
    if cleaned in MIPS_REGISTERS:
        return MIPS_REGISTERS[cleaned]
    parsed = parse_integer(cleaned)
    if parsed is None or not 0 <= parsed <= 255:
        raise ValueError(f"invalid register: {value!r}")
    return parsed


def register_name(number: int) -> str:
    """Return a conventional name, retaining unknown numeric registers."""

    return REGISTER_NAMES.get(number, str(number))


@dataclass(frozen=True)
class TraceEvent:
    """One normalized diagnostic line."""

    index: int
    tag: str
    action: str
    register: int | None
    source_line: int | None
    serial: int | None
    list_address: int | None
    fields: dict[str, str] = field(default_factory=dict)
    raw: str = ""

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        if self.register is not None:
            result["register_name"] = register_name(self.register)
        return result


def normalize_action(tag: str, fields: dict[str, str]) -> str:
    """Map historical trace spellings to stable actions."""

    upper = tag.upper().replace("_", "-")
    if "ALIAS-QUERY" in upper:
        return "alias-query"
    if upper.endswith("-BASE"):
        return "base"
    if "ALLOC" in upper or (
        upper.endswith("FREELIST") and fields.get("_event") == "ALLOC"
    ):
        return "allocate"
    if "APPEND" in upper or (
        upper.endswith("FREELIST")
        and fields.get("_event") in {"ADD", "FREE", "FORCE_FREE"}
    ):
        return "append"
    if "REMOVE" in upper or "POP" in upper:
        return "remove"
    if "FREE" in upper:
        return "free"
    if "QUEUE" in upper:
        return "queue"
    if "GETDEST" in upper:
        return "get-destination"
    if "HINT" in upper:
        return "hint"
    if "EVAL" in upper:
        return "evaluate"
    return upper.lower()


def parse_trace(text: str) -> list[TraceEvent]:
    """Parse known CODEX/DKWB ugen trace formats.

    Unknown diagnostic tags are retained instead of discarded, which makes
    the summary command useful with newer instrumentation revisions.
    """

    events: list[TraceEvent] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        tag_match = UGEN_TAG_RE.match(stripped)
        if not tag_match:
            continue
        first_token, _, remainder = stripped.partition(" ")
        fields = {key: value for key, value in FIELD_RE.findall(remainder)}
        if first_token == "DKWB-FREELIST":
            event_name, _, rest = remainder.partition(" ")
            fields["_event"] = event_name.upper()
            fields.update({key: value for key, value in FIELD_RE.findall(rest)})
        register_value = fields.get("reg") or fields.get("register")
        source_value = fields.get("line") or fields.get("source_line")
        serial_value = fields.get("serial")
        list_value = fields.get("list") or fields.get("list_address")
        register = (
            parse_register(register_value) if register_value is not None else None
        )
        events.append(
            TraceEvent(
                index=line_number,
                tag=first_token,
                action=normalize_action(first_token, fields),
                register=register,
                source_line=(
                    parse_integer(source_value)
                    if source_value is not None
                    else None
                ),
                serial=(
                    parse_integer(serial_value)
                    if serial_value is not None
                    else None
                ),
                list_address=(
                    parse_integer(list_value)
                    if list_value is not None
                    else None
                ),
                fields=fields,
                raw=raw,
            )
        )
    return events


@dataclass(frozen=True)
class LogicalEvent:
    """An allocation/free event expressed in logical value identities."""

    action: str
    value: int
    register: int
    source_line: int | None
    trace_line: int

    def as_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["register_name"] = register_name(self.register)
        return result


@dataclass
class FifoReplay:
    """Result of replaying one traced FIFO register class."""

    initial_queue: list[int]
    final_queue: list[int]
    allocations: list[int]
    logical_events: list[LogicalEvent]
    violations: list[str]
    max_live: int
    ignored_events: int

    @property
    def valid(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "initial_queue": self.initial_queue,
            "initial_queue_names": [
                register_name(item) for item in self.initial_queue
            ],
            "final_queue": self.final_queue,
            "final_queue_names": [
                register_name(item) for item in self.final_queue
            ],
            "allocations": self.allocations,
            "allocation_names": [
                register_name(item) for item in self.allocations
            ],
            "logical_events": [
                event.as_dict() for event in self.logical_events
            ],
            "violations": self.violations,
            "max_live": self.max_live,
            "ignored_events": self.ignored_events,
        }


def infer_initial_queue(events: Iterable[TraceEvent]) -> list[int]:
    """Use unique leading appends before the first allocation as the seed."""

    queue: list[int] = []
    for event in events:
        if event.action == "allocate":
            break
        if (
            event.action == "append"
            and event.register is not None
            and event.register not in queue
        ):
            queue.append(event.register)
    return queue


def replay_fifo(
    events: Iterable[TraceEvent],
    *,
    initial_queue: Iterable[int] | None = None,
    registers: set[int] | None = None,
    list_address: int | None = None,
) -> FifoReplay:
    """Replay allocation and append events as a strict FIFO.

    If no initial queue is supplied, unique appends before the first allocation
    seed it. Those seed events are not replayed as frees.
    """

    all_events = list(events)
    relevant = [
        event
        for event in all_events
        if event.action in {"allocate", "append"}
        and event.register is not None
        and (registers is None or event.register in registers)
        and (
            list_address is None
            or event.list_address is None
            or event.list_address == list_address
        )
    ]
    inferred = initial_queue is None
    seed = (
        infer_initial_queue(relevant)
        if inferred
        else list(initial_queue or [])
    )
    queue = list(seed)
    live: dict[int, int] = {}
    logical: list[LogicalEvent] = []
    allocations: list[int] = []
    violations: list[str] = []
    next_value = 1
    max_live = 0
    seen_allocation = False

    for event in relevant:
        assert event.register is not None
        register = event.register
        if event.action == "append" and inferred and not seen_allocation:
            continue
        if event.action == "allocate":
            seen_allocation = True
            allocations.append(register)
            if not queue:
                violations.append(
                    f"trace line {event.index}: allocated "
                    f"{register_name(register)} from an empty queue"
                )
            else:
                expected = queue.pop(0)
                if register != expected:
                    violations.append(
                        f"trace line {event.index}: allocated "
                        f"{register_name(register)}, FIFO head was "
                        f"{register_name(expected)}"
                    )
            if register in live:
                violations.append(
                    f"trace line {event.index}: {register_name(register)} "
                    "allocated while already live"
                )
            live[register] = next_value
            logical.append(
                LogicalEvent(
                    action="allocate",
                    value=next_value,
                    register=register,
                    source_line=event.source_line,
                    trace_line=event.index,
                )
            )
            next_value += 1
            max_live = max(max_live, len(live))
        else:
            value = live.pop(register, None)
            if value is None:
                violations.append(
                    f"trace line {event.index}: appended "
                    f"{register_name(register)} without a live allocation"
                )
                value = 0
            if register in queue:
                violations.append(
                    f"trace line {event.index}: appended duplicate "
                    f"{register_name(register)}"
                )
            queue.append(register)
            logical.append(
                LogicalEvent(
                    action="free",
                    value=value,
                    register=register,
                    source_line=event.source_line,
                    trace_line=event.index,
                )
            )

    return FifoReplay(
        initial_queue=seed,
        final_queue=queue,
        allocations=allocations,
        logical_events=logical,
        violations=violations,
        max_live=max_live,
        ignored_events=len(all_events) - len(relevant),
    )


def trace_summary(events: Iterable[TraceEvent]) -> dict[str, object]:
    """Return stable event, register, and source-line histograms."""

    materialized = list(events)
    actions = collections.Counter(event.action for event in materialized)
    registers = collections.Counter(
        register_name(event.register)
        for event in materialized
        if event.register is not None
    )
    source_lines = collections.Counter(
        str(event.source_line)
        for event in materialized
        if event.source_line is not None
    )
    return {
        "events": len(materialized),
        "actions": dict(sorted(actions.items())),
        "registers": dict(sorted(registers.items())),
        "source_lines": dict(
            sorted(source_lines.items(), key=lambda item: int(item[0]))
        ),
    }


def alias_trace_summary(events: Iterable[TraceEvent]) -> dict[str, object]:
    """Summarize the profiled uopt base-provenance and alias decisions."""

    materialized = [
        event
        for event in events
        if event.action in {"base", "alias-query"}
    ]
    bases = [event for event in materialized if event.action == "base"]
    queries = [
        event for event in materialized if event.action == "alias-query"
    ]

    def count_field(
        selected: Iterable[TraceEvent], field_name: str
    ) -> dict[str, int]:
        counts = collections.Counter(
            event.fields[field_name]
            for event in selected
            if field_name in event.fields
        )
        return dict(sorted(counts.items()))

    return {
        "events": len(materialized),
        "base_events": len(bases),
        "alias_queries": len(queries),
        "base_paths": count_field(bases, "path"),
        "base_types": count_field(bases, "type"),
        "query_results": count_field(queries, "result"),
        "left_types": count_field(queries, "left_type"),
        "right_types": count_field(queries, "right_type"),
        "registers": dict(
            sorted(
                collections.Counter(
                    register_name(event.register)
                    for event in materialized
                    if event.register is not None
                ).items()
            )
        ),
        "queries": [event.as_dict() for event in queries],
    }
