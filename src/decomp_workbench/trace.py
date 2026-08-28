"""Parsers and models for IDO static-recomp diagnostic traces.

A diagnostic trace is line-oriented text. The *other* thing a campaign holds
after ``capture make`` is a binary pass-boundary stream -- the Ucode uopt hands
ugen, the Binasm ugen hands as1 -- and handing one of those to a trace command
used to surface as a raw ``UnicodeDecodeError`` with no name for the file and
no next step. :func:`read_trace_source` is the one reader every trace command
goes through: it decodes text, recovers the diagnostic lines out of a stream
that merely *contains* binary, and refuses a pass-boundary stream by name,
pointing at the decoder that reads it and at the Tier-2 instrumentation that
produces a textual trace instead.
"""

from __future__ import annotations

import collections
import re
import struct
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TypedDict

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
    number: name for name, number in MIPS_REGISTERS.items() if name != "s8"
}


class TraceSummary(TypedDict):
    """Aggregate counts for a parsed trace."""

    events: int
    actions: dict[str, int]
    registers: dict[str, int]
    source_lines: dict[str, int]


class AliasTraceSummary(TypedDict):
    """Aggregate counts and query records for the alias profile."""

    events: int
    base_events: int
    alias_queries: int
    base_paths: dict[str, int]
    base_types: dict[str, int]
    query_results: dict[str, int]
    left_types: dict[str, int]
    right_types: dict[str, int]
    registers: dict[str, int]
    queries: list[dict[str, object]]


#: Where a reader is sent when the bytes in hand are not a textual trace.
INSTRUMENTATION_DOC = "docs/compiler-instrumentation.md"
PHASE_CAPTURE_DOC = "docs/phase-capture.md"

#: What each pass-boundary stream is, and which command reads it. The trace
#: commands cannot decode either one: a stream carries records, not decisions,
#: and the decision text only exists when the instrumented toolchain emits it.
STREAM_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "ucode": (
        "variable-width binary Ucode (uopt's output, ugen's positional input)",
        "ucode window",
    ),
    "binasm": (
        "fixed 16-byte binary Binasm (ugen's -o and -temp output)",
        "binasm window",
    ),
}


class BinaryTraceStreamError(ValueError):
    """A trace command was handed bytes that hold no diagnostic text.

    Carries the classification so a caller can branch on it without reparsing
    the message: ``stream_format`` is ``ucode``, ``binasm``, or ``None`` for
    binary this module could not frame as either.
    """

    def __init__(self, message: str, *, stream_format: str | None = None) -> None:
        super().__init__(message)
        self.stream_format = stream_format


@dataclass(frozen=True)
class TraceSource:
    """Decoded trace text, and what had to be done to get it."""

    text: str
    encoding: str
    undecodable_bytes: int
    notes: tuple[str, ...] = ()

    @property
    def recovered(self) -> bool:
        return self.undecodable_bytes > 0


def classify_trace_bytes(data: bytes) -> str | None:
    """Name the pass-boundary stream these bytes frame as, if either.

    Delegates to the stream decoders rather than sniffing here, so the answer a
    trace command gives matches the one ``stream``/``ucode``/``binasm`` give.
    Anything the decoders refuse is ``None`` -- unclassified binary, which is a
    different message with a different next step.
    """

    from .streams import detect_format

    try:
        return detect_format(data)
    except (ValueError, IndexError, struct.error):
        return None


def _stream_record_count(data: bytes, stream_format: str) -> int | None:
    from .streams import decode_stream

    try:
        _, _, records = decode_stream(data, stream_format=stream_format)
    except (ValueError, IndexError, struct.error):
        return None
    return len(records)


def _binary_stream_message(
    data: bytes, stream_format: str, *, name: str, tags: int
) -> str:
    description, reader = STREAM_DESCRIPTIONS[stream_format]
    records = _stream_record_count(data, stream_format)
    measured = f"{records} record(s)" if records is not None else f"{len(data)} bytes"
    recovered = (
        ""
        if tags == 0
        else (
            f" {tags} line(s) in it look like diagnostic tags, which framed "
            "records can spell by accident; they are not read as a trace."
        )
    )
    return (
        f"{name} is a {description} pass-boundary stream, {measured}, not a "
        f"diagnostic trace.{recovered} A stream carries records, not the "
        f"decisions that produced them, so no trace command can decode it: "
        f"read the records with `decomp-workbench {reader} {name}` "
        f"({PHASE_CAPTURE_DOC}), and for a textual per-decision trace build "
        f"the Tier-2 instrumented toolchain ({INSTRUMENTATION_DOC})."
    )


def _unframed_binary_message(data: bytes, *, name: str, undecodable: int) -> str:
    return (
        f"{name} is not UTF-8 text ({undecodable} undecodable byte(s) of "
        f"{len(data)}) and frames as neither Ucode nor Binasm, so there is "
        "nothing to decode either way. No CODEX/DKWB diagnostic line survived "
        f"a lossy decode. If this is a retained pass boundary, read it with "
        f"`decomp-workbench stream window {name}` ({PHASE_CAPTURE_DOC}); if it "
        "should be a trace, the instrumented toolchain did not write one -- "
        f"see {INSTRUMENTATION_DOC}."
    )


def _count_trace_tags(text: str) -> int:
    return sum(bool(UGEN_TAG_RE.match(line.strip())) for line in text.splitlines())


#: Bytes a line-oriented trace uses; everything else below 0x20 is a control
#: byte no diagnostic writer emits.
_TEXT_CONTROL_BYTES = frozenset(b"\t\n\r\f\v\x1b")


def _binary_ratio(data: bytes) -> float:
    """Fraction of bytes that no line-oriented trace would contain."""

    if not data:
        return 0.0
    control = sum(1 for byte in data if byte < 0x20 and byte not in _TEXT_CONTROL_BYTES)
    return control / len(data)


#: A Binasm record's words are small integers, so a whole stream can decode as
#: UTF-8 without raising: refusing only on ``UnicodeDecodeError`` let exactly
#: the streams this reader exists for through as "text" with zero events. One
#: NUL, or a tenth of the file in control bytes, is the evidence instead.
BINARY_CONTROL_RATIO = 0.1


def _looks_binary(data: bytes) -> bool:
    return b"\x00" in data or _binary_ratio(data) > BINARY_CONTROL_RATIO


def read_trace_source(
    source: bytes | str | Path, *, name: str | None = None
) -> TraceSource:
    """Read one trace, naming a binary stream instead of failing on decode.

    Bytes are accepted directly so a caller that already read the file, or a
    test, does not have to touch the filesystem. ``name`` is what the error
    message calls the input; it defaults to the path, or ``<bytes>``.
    """

    if isinstance(source, bytes):
        data = source
        label = name or "<bytes>"
    else:
        path = Path(source)
        data = path.read_bytes()
        label = name or str(path)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is not None and not (_looks_binary(data) and _count_trace_tags(text) == 0):
        # Decodes, and either carries diagnostic tags or holds nothing that
        # only a binary stream contains. Other line formats -- globalcolor,
        # a71, scheduler -- have no CODEX/DKWB tag and must pass through here.
        return TraceSource(text=text, encoding="utf-8", undecodable_bytes=0)
    stream_format = classify_trace_bytes(data)
    lossy = data.decode("utf-8", errors="replace")
    tags = _count_trace_tags(lossy)
    if text is not None and stream_format is None:
        # Decodable, binary-looking, and framed as neither stream. Say so and
        # let the caller read it: refusing here would be a guess.
        return TraceSource(
            text=text,
            encoding="utf-8",
            undecodable_bytes=0,
            notes=(
                f"{label} decodes as text but reads as binary "
                f"({_binary_ratio(data):.0%} control bytes) and holds no "
                "CODEX/DKWB diagnostic line; it frames as neither Ucode nor "
                f"Binasm. Parsed as text anyway ({PHASE_CAPTURE_DOC}).",
            ),
        )
    if stream_format is not None:
        raise BinaryTraceStreamError(
            _binary_stream_message(data, stream_format, name=label, tags=tags),
            stream_format=stream_format,
        )
    undecodable = lossy.count("\ufffd")
    if tags == 0:
        raise BinaryTraceStreamError(
            _unframed_binary_message(data, name=label, undecodable=undecodable)
        )
    return TraceSource(
        text=lossy,
        encoding="utf-8/replace",
        undecodable_bytes=undecodable,
        notes=(
            f"{label} is not valid UTF-8: {undecodable} byte(s) were replaced "
            f"and {tags} diagnostic line(s) were recovered from the rest. A "
            "mixed file is a trace with binary written into the same stream; "
            f"records it may also hold are not decoded here ({PHASE_CAPTURE_DOC}).",
        ),
    )


def read_trace_text(
    source: bytes | str | Path,
    *,
    name: str | None = None,
    warn: Callable[[str], None] | None = None,
) -> str:
    """Return trace text, reporting recovery notes through ``warn``."""

    parsed = read_trace_source(source, name=name)
    if warn is not None:
        for note in parsed.notes:
            warn(note)
    return parsed.text


def parse_integer(value: str) -> int | None:
    """Parse decimal, ``0x`` hexadecimal, or bare hexadecimal values."""

    cleaned = value.rstrip(",;")
    try:
        return int(cleaned, 0)
    except ValueError:
        if re.fullmatch(r"[0-9a-fA-F]+", cleaned) and re.search(r"[a-fA-F]", cleaned):
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


#: ugen numbers a floating-point register as ``32 + n`` in the unified register
#: space its free-list events report, so the fp temp ring ``$f4 $f6 $f8 $f10``
#: reaches the trace as 36, 38, 40, 42. Integer registers stay 0-31, so one
#: decode covers both halves without ambiguity. Values at or above 64 are not
#: registers in this space -- the ``ALLOC_FP`` *entry* hook stamps a request
#: descriptor (e.g. 96, 208), not the allocated register -- and stay numeric so
#: a request is never misread as ``$f64``.
FP_REGISTER_BASE = 32
FP_REGISTER_LIMIT = 64


def register_name(number: int) -> str:
    """Return a conventional name, retaining unknown numeric registers."""

    if number in REGISTER_NAMES:
        return REGISTER_NAMES[number]
    if FP_REGISTER_BASE <= number < FP_REGISTER_LIMIT:
        return f"$f{number - FP_REGISTER_BASE}"
    return str(number)


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
    emitted_index: int | None = None
    object_row: int | None = None
    source_file: str | None = None
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
    if upper.endswith("FREELIST"):
        event = fields.get("_event")
        # ALLOC, ALLOC_FP (the fp request), and ALLOC_FP_RESULT (the register
        # the fp allocator returned) are all allocations; match the family by
        # prefix so a new allocation event does not fall through to the raw
        # tag name.
        if event is not None and event.startswith("ALLOC"):
            return "allocate"
        if event in {"ADD", "FREE", "FORCE_FREE"}:
            return "append"
        if event == "REMOVE":
            return "remove"
        if event == "MOVE_END":
            return "move-end"
    if "ALLOC" in upper:
        return "allocate"
    if "APPEND" in upper:
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
        emitted_value = (
            fields.get("emitted")
            or fields.get("emit_index")
            or fields.get("insn_index")
            or fields.get("ord")
        )
        row_value = fields.get("row") or fields.get("object_row")
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
                    parse_integer(source_value) if source_value is not None else None
                ),
                serial=(
                    parse_integer(serial_value) if serial_value is not None else None
                ),
                list_address=(
                    parse_integer(list_value) if list_value is not None else None
                ),
                emitted_index=(
                    parse_integer(emitted_value) if emitted_value is not None else None
                ),
                object_row=(
                    parse_integer(row_value) if row_value is not None else None
                ),
                source_file=fields.get("file") or fields.get("source_file"),
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
    emitted_index: int | None = None
    object_row: int | None = None
    source_file: str | None = None
    instruction: str | None = None

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
        emitted = sum(event.emitted_index is not None for event in self.logical_events)
        rows = sum(event.object_row is not None for event in self.logical_events)
        sources = sum(event.source_line is not None for event in self.logical_events)
        instructions = sum(
            event.instruction is not None for event in self.logical_events
        )
        return {
            "valid": self.valid,
            "initial_queue": self.initial_queue,
            "initial_queue_names": [register_name(item) for item in self.initial_queue],
            "final_queue": self.final_queue,
            "final_queue_names": [register_name(item) for item in self.final_queue],
            "allocations": self.allocations,
            "allocation_names": [register_name(item) for item in self.allocations],
            "logical_events": [event.as_dict() for event in self.logical_events],
            "violations": self.violations,
            "max_live": self.max_live,
            "ignored_events": self.ignored_events,
            "emission_join": {
                "logical_events": len(self.logical_events),
                "with_emitted_index": emitted,
                "with_object_row": rows,
                "with_source_line": sources,
                "with_instruction": instructions,
                "complete": bool(self.logical_events)
                and rows == len(self.logical_events)
                and sources == len(self.logical_events),
                "calibration_required": emitted > rows,
            },
        }


@dataclass(frozen=True)
class EmissionLocation:
    """One exact instrumented-ordinal to object/source calibration point."""

    emitted_index: int
    object_row: int
    source_line: int | None = None
    source_file: str | None = None
    instruction: str | None = None


EMISSION_MAP_SCHEMA = "decomp-workbench-ugen-emission-map-v1"


def parse_emission_map(value: object) -> dict[int, EmissionLocation]:
    """Validate a durable emitted-index/object-row/source join document."""

    if not isinstance(value, dict) or value.get("schema") != EMISSION_MAP_SCHEMA:
        raise ValueError(f"emission map schema must be {EMISSION_MAP_SCHEMA}")
    entries = value.get("entries")
    if not isinstance(entries, list):
        raise ValueError("emission map entries must be a list")
    result: dict[int, EmissionLocation] = {}
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            raise ValueError(f"emission map entry {index} must be an object")
        try:
            emitted_index = int(raw["emitted_index"])
            object_row = int(raw["object_row"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(
                f"emission map entry {index} requires integer emitted_index "
                "and object_row"
            ) from None
        if emitted_index < 0 or object_row < 0:
            raise ValueError(f"emission map entry {index} indices must be non-negative")
        if emitted_index in result:
            raise ValueError(
                f"emission map emitted_index {emitted_index} is duplicated"
            )
        source_line_value = raw.get("source_line")
        source_line = int(source_line_value) if source_line_value is not None else None
        if source_line is not None and source_line < 1:
            raise ValueError(f"emission map entry {index} source_line must be positive")
        source_file_value = raw.get("source_file")
        if source_file_value is not None and not isinstance(source_file_value, str):
            raise ValueError(f"emission map entry {index} source_file must be a string")
        instruction_value = raw.get("instruction")
        if instruction_value is not None and not isinstance(instruction_value, str):
            raise ValueError(f"emission map entry {index} instruction must be a string")
        result[emitted_index] = EmissionLocation(
            emitted_index=emitted_index,
            object_row=object_row,
            source_line=source_line,
            source_file=source_file_value,
            instruction=instruction_value,
        )
    return result


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
    emission_map: dict[int, EmissionLocation] | None = None,
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
            or event.action == "allocate"
            or event.list_address == list_address
        )
    ]
    inferred = initial_queue is None
    seed = infer_initial_queue(relevant) if inferred else list(initial_queue or [])
    queue = list(seed)
    live: dict[int, int] = {}
    logical: list[LogicalEvent] = []
    allocations: list[int] = []
    violations: list[str] = []
    next_value = 1
    max_live = 0
    seen_allocation = False

    def joined(
        event: TraceEvent,
    ) -> tuple[int | None, int | None, str | None, str | None]:
        location = (
            emission_map.get(event.emitted_index)
            if emission_map is not None and event.emitted_index is not None
            else None
        )
        object_row = (
            event.object_row
            if event.object_row is not None
            else location.object_row
            if location is not None
            else None
        )
        source_line = (
            event.source_line
            if event.source_line is not None
            else location.source_line
            if location is not None
            else None
        )
        source_file = (
            event.source_file
            if event.source_file is not None
            else location.source_file
            if location is not None
            else None
        )
        instruction = location.instruction if location is not None else None
        return object_row, source_line, source_file, instruction

    for event in relevant:
        register = event.register
        if register is None:  # Guard the invariant established by filtering.
            continue
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
            object_row, source_line, source_file, instruction = joined(event)
            logical.append(
                LogicalEvent(
                    action="allocate",
                    value=next_value,
                    register=register,
                    source_line=source_line,
                    trace_line=event.index,
                    emitted_index=event.emitted_index,
                    object_row=object_row,
                    source_file=source_file,
                    instruction=instruction,
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
            object_row, source_line, source_file, instruction = joined(event)
            logical.append(
                LogicalEvent(
                    action="free",
                    value=value,
                    register=register,
                    source_line=source_line,
                    trace_line=event.index,
                    emitted_index=event.emitted_index,
                    object_row=object_row,
                    source_file=source_file,
                    instruction=instruction,
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


def trace_summary(events: Iterable[TraceEvent]) -> TraceSummary:
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


def alias_trace_summary(events: Iterable[TraceEvent]) -> AliasTraceSummary:
    """Summarize the profiled uopt base-provenance and alias decisions."""

    materialized = [
        event for event in events if event.action in {"base", "alias-query"}
    ]
    bases = [event for event in materialized if event.action == "base"]
    queries = [event for event in materialized if event.action == "alias-query"]

    def count_field(selected: Iterable[TraceEvent], field_name: str) -> dict[str, int]:
        counts = collections.Counter(
            event.fields[field_name] for event in selected if field_name in event.fields
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
