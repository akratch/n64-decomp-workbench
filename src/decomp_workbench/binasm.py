"""Read IDO's fixed-width Binasm stream and late-peephole evidence.

The ugen-to-as1 boundary is one of the last places a near match can diverge.
IDO's Binasm stream is not an object file: it is a sequence of 16-byte
records consumed by as1.  This module intentionally decodes only record
families whose identities have been observed and calibrated.  Unknown
records remain visible as four words instead of being guessed into assembly.

Barrier-probe results are likewise evidence about the downstream pass only.
An inserted record producing an exact object proves sufficiency at that
boundary; it does not prove that a C spelling survives cfe/uopt/ugen and
emits that record naturally.
"""

from __future__ import annotations

import hashlib
import re
import struct
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

BINASM_RECORD_SIZE = 16
BINASM_REPORT_SCHEMA = "decomp-workbench-binasm-boundary-v1"

_SET_MODES: dict[int, str] = {
    1: "reorder",
    2: "noreorder",
    3: "macro",
    4: "nomacro",
    5: "at",
    6: "noat",
    7: "move",
    8: "nomove",
    9: "bopt",
    10: "nobopt",
    11: "volatile",
    12: "novolatile",
    13: "transform",
    14: "notransform",
}

# Binasm instruction opcodes established from as0 probes.  This is not an
# instruction decoder: operands have a separate Binasm encoding, and a made-up
# operand rendering is worse evidence than the raw words.
_INSTRUCTION_NAMES: dict[int, str] = {
    0x0004: "addu",
    0x0062: "move",
    0x007C: "nop-pseudo",
    0x0080: "or",
    0x009E: "sll",
    0x00A8: "srl",
    0x00AC: "subu",
    0x00B2: "xor",
    0x01A8: "addiu",
    0x01AE: "andi",
    # The one instruction record that is not self-contained: word 3 is a byte
    # length and the following ceil(length/16) records are raw, space-padded
    # ASCII digits rather than words. Established by three retained streams in
    # which the lengths 3, 12 and 22 framed "0.0", "4294967296.0" and
    # "3.0517578125000000e-05" exactly (22 = 16 + 6).
    0x01F8: "float-literal",
}

#: The instruction record whose successors are an ASCII payload, not records.
_LITERAL_INSTRUCTION = 0x01F8

#: Record families keyed by the high half of word 1.
#:
#: ``calibrated`` families were established by assembling a hand-written probe
#: listing through as0 and reading the record it produced one-for-one, by an
#: as1 diagnostic naming the record's effect, or by a structural pairing that
#: cannot be coincidence. ``inferred`` families were only ever *observed* in a
#: retained stream with a payload that fits a familiar directive; their raw
#: words remain the evidence and the name is a reading aid.
_RECORD_FAMILIES: dict[int, tuple[str, str, str, str]] = {
    # opcode: (kind, name, description, evidence)
    0x0002: ("symbol-scope", "globl", "global symbol declaration", "calibrated"),
    0x0009: (
        "symbol-definition",
        "symbol-def",
        "symbol definition; as1 rejects a duplicate of it",
        "calibrated",
    ),
    0x0015: ("section", "text", "switch to the text section", "calibrated"),
    0x0018: ("procedure", "end", "procedure end", "calibrated"),
    0x001A: (
        "section",
        "section-switch",
        "leave the text section for embedded data",
        "calibrated",
    ),
    0x001B: ("procedure", "ent", "procedure entry", "calibrated"),
    0x0026: ("procedure", "mask", "register save mask and frame offset", "inferred"),
    0x002A: ("stream-header", "header", "Binasm stream header record", "calibrated"),
    0x002B: ("procedure", "frame", "frame description", "inferred"),
    0x0035: (
        "call-metadata",
        "call-live",
        "ugen's own call-site liveness metadata",
        "inferred",
    ),
}

_PEEP_REPLACEMENT_RE = re.compile(
    r"^>>(?P<family>Repl_reg(?:_tgt)?)\s+\(INST\s+(?P<inst>\d+)\)\s+"
    r"(?P<register>\d+)\s+with\s+(?P<with_register>\d+)\s*$"
)
_PEEP_NOP_RE = re.compile(
    r"^>>(?P<family>Repl_reg(?:_tgt)?)\s+\(INST\s+(?P<inst>\d+)\)\s+"
    r"changed\s+to\s+NOP\s*$"
)
_PEEP_RS_RE = re.compile(
    r"^>>(?P<family>Peepreg)\s+\(INST\s+(?P<inst>\d+)\)\s+changed\s+rs\s+"
    r"(?P<register>\d+)\s*=>\s*(?P<with_register>\d+)\s*$"
)
_PEEP_MEMORY_RE = re.compile(
    r"^>>(?P<family>Peepreg)\s+\(INST\s+(?P<inst>\d+)\)\s+mem=>"
    r"(?P<operation>\S+)\s+r\s+(?P<register>\d+)\s*$"
)


#: What either phase decoder accepts: the stream's bytes, or a path to them.
StreamSource = bytes | bytearray | memoryview | str | Path


def read_stream_bytes(source: StreamSource) -> bytes:
    """Return one phase stream's bytes from either a buffer or a path.

    Both decoders take this so a caller holding a patched stream in memory and
    a caller holding a retained capture file use the same entry point. A `str`
    is always a path: a phase stream is binary and never text.
    """

    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source)
    return Path(source).expanduser().read_bytes()


def _signed_u32(value: int) -> int:
    return value - (1 << 32) if value & (1 << 31) else value


@dataclass(frozen=True)
class BinasmRecord:
    """One losslessly retained 16-byte Binasm record."""

    index: int
    offset: int
    words: tuple[int, int, int, int]
    kind: str
    name: str
    detail: str
    source_lever: str | None = None
    #: ``calibrated`` for a family established by a probe listing, an as1
    #: diagnostic, or a structural pairing, **in exactly the form observed**;
    #: ``inferred`` for one only observed, or for a variant of a calibrated
    #: family carrying bits no probe explains; ``none`` for a record left raw.
    evidence: str = "calibrated"

    @property
    def raw_hex(self) -> str:
        return " ".join(f"{word:08x}" for word in self.words)

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "offset": self.offset,
            "offset_hex": f"0x{self.offset:x}",
            "words": [f"0x{word:08x}" for word in self.words],
            "raw_hex": self.raw_hex,
            "kind": self.kind,
            "name": self.name,
            "detail": self.detail,
            "source_lever": self.source_lever,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class PeepEvent:
    """One recognized line from IDO 7.1's ``-peepdbg`` stream."""

    line: int
    family: str
    action: str
    inst: int
    register: int | None = None
    with_register: int | None = None
    operation: str | None = None
    text: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "family": self.family,
            "action": self.action,
            "inst": self.inst,
            "register": self.register,
            "with_register": self.with_register,
            "operation": self.operation,
            "text": self.text,
        }


def _instruction_source_lever(name: str, operands: int, immediate: int) -> str | None:
    """Describe a source search family without claiming upstream survival."""

    if name == "move":
        return (
            "copy assignment or carrier coalescing; a physical self-move may "
            "be removed before Binasm, so verify the retained stream"
        )
    zero_identity_operands = {
        # Calibrated self/value-plus-zero probes. Other register encodings are
        # deliberately not generalized without an operand decoder.
        0x04090000,
        0x060CC000,
        0x060D0000,
    }
    if (
        name in {"addu", "addiu", "or", "subu", "xor"}
        and operands in zero_identity_operands
        and immediate == 0
    ):
        return (
            "zero-arithmetic identity on the live value; source-spellable, but "
            "normally optimized away upstream unless another constraint retains it"
        )
    if name == "andi":
        mask = immediate & 0xFFFF
        return (
            f"narrowing/width normalization with mask 0x{mask:x}; try a proven "
            "narrow type or edge-local conversion and verify that ugen retains it"
        )
    if name == "nop-pseudo":
        return "assembler no-op; useful as a boundary control, not direct C evidence"
    if name in {"sll", "srl"} and immediate == 0:
        return "zero shift identity; source-spellable but normally removed upstream"
    if operands:
        return None
    return None


def _variant_evidence(
    detail: str, low: int, *, observed: str = "calibrated"
) -> tuple[str, str]:
    """Fold a family's unexplained low bits into its detail and its evidence.

    Every record family below is keyed on the *high* half of word 1, and the
    low half is zero in every record the calibration probes produced. A
    nonzero low half is therefore a variant nobody has observed. Dropping
    those bits and still calling the reading ``calibrated`` was the worst of
    both: the evidence tag claimed a probe established this exact record, and
    the only trace of the part that was not established had been deleted from
    the output. So the bits are rendered, and the claim is downgraded.
    """

    if not low:
        return detail, observed
    return f"{detail}; flags=0x{low:04x}", "inferred"


def _classify_record(
    index: int, offset: int, words: tuple[int, int, int, int]
) -> BinasmRecord:
    first, opcode, operands, immediate = words
    signed_first = _signed_u32(first)
    if opcode == 0 and operands == 0 and immediate == 0 and first:
        # A label *definition* is the empty-opcode record. ugen mints local
        # labels as negative numbers and as0 emits named and numeric labels as
        # positive symbol indices; both are the same record family, and the
        # decoder used to see only the negative half of it.
        if signed_first < 0:
            return BinasmRecord(
                index,
                offset,
                words,
                "control-flow",
                "local-label",
                f"local label ${-signed_first}",
                "an explicit label/goto or a control-flow join can create "
                "this boundary",
            )
        return BinasmRecord(
            index,
            offset,
            words,
            "control-flow",
            "symbol-label",
            f"label definition for symbol index {first}",
            "a named label, a function entry, or an assembled local label",
        )
    if opcode >> 16 == 0x0016:
        # The dense case table: one record per case, word 0 naming the target
        # local label, inside a section-switch/text pair. Two retained tables
        # of 6 and 81 entries matched their Ucode `Uclab` length and the range
        # guard of the branch that preceded them.
        target = f"${-signed_first}" if signed_first < 0 else str(first)
        detail, evidence = _variant_evidence(f"case target {target}", opcode & 0xFFFF)
        if (operands, immediate) != (0, 1):
            detail += f" (unusual payload {operands:#x}/{immediate:#x})"
            evidence = "inferred"
        return BinasmRecord(
            index,
            offset,
            words,
            "jump-table",
            "table-entry",
            detail,
            "a switch whose dense range ugen chose to lower as a jump table; "
            "the table's width follows the selector range, not the C spelling",
            evidence,
        )
    if opcode >> 16 == 0x001C:
        detail, evidence = _variant_evidence(
            f"file={operands} line={immediate}", opcode & 0xFFFF
        )
        return BinasmRecord(
            index,
            offset,
            words,
            "source-location",
            "loc",
            detail,
            (
                "statement attribution or #line can change LOC records when the "
                "selected frontend/debug mode emits them"
            ),
            evidence,
        )
    if opcode >> 16 == 0x0020:
        mode = _SET_MODES.get(operands, f"unknown-{operands}")
        detail, evidence = _variant_evidence(f".set {mode}", opcode & 0xFFFF)
        if operands not in _SET_MODES:
            # The prefix says ".set"; the mode number is one no probe named.
            evidence = "inferred"
        return BinasmRecord(
            index,
            offset,
            words,
            "assembler-mode",
            f"set-{mode}",
            detail,
            (
                "assembler directive only; use as a downstream boundary proof, "
                "then seek a source event that creates the same peephole break"
            ),
            evidence,
        )
    if opcode & 0xFFFF0000 == 0x00170000:
        instruction_opcode = opcode & 0xFFFF
        # Here the low half *is* the instruction opcode, so it is explained
        # exactly when it is one of the opcodes the as0 probes established.
        named = instruction_opcode in _INSTRUCTION_NAMES
        name = _INSTRUCTION_NAMES.get(
            instruction_opcode, f"instruction-0x{instruction_opcode:04x}"
        )
        detail = f"Binasm operands=0x{operands:08x} value=0x{immediate:08x}"
        if instruction_opcode == _LITERAL_INSTRUCTION:
            detail += (
                f"; {immediate} ASCII byte(s) follow in "
                f"{_literal_payload_records(immediate)} payload record(s)"
            )
        return BinasmRecord(
            index,
            offset,
            words,
            "instruction",
            name,
            detail,
            _instruction_source_lever(name, operands, immediate),
            "calibrated" if named else "inferred",
        )
    if opcode & 0xFFFF0000 in {0x00300000, 0x00310000}:
        is_alias = opcode & 0xFFFF0000 == 0x00310000
        name = "alias" if is_alias else "noalias"
        detail, evidence = _variant_evidence(
            f"{name} metadata opcode=0x{opcode:08x}", opcode & 0xFFFF
        )
        return BinasmRecord(
            index,
            offset,
            words,
            "alias-metadata",
            name,
            detail,
            (
                "pointer provenance, restrict-like separation, or volatile access "
                "may alter alias metadata; verify the exact frontend emits it"
            ),
            evidence,
        )
    call_metadata = {
        0x00360000: "gjaldef",
        0x00370000: "gjallive",
        0x00380000: "gjrlive",
    }
    if opcode in call_metadata:
        name = call_metadata[opcode]
        return BinasmRecord(
            index,
            offset,
            words,
            "call-metadata",
            name,
            f"{name} mask=0x{operands:08x}",
            "call placement and values live across the call can alter this metadata",
        )
    family = _RECORD_FAMILIES.get(opcode >> 16)
    if family is not None:
        kind, name, description, observed = family
        detail, evidence = _variant_evidence(
            description, opcode & 0xFFFF, observed=observed
        )
        if operands or immediate:
            detail += f"; payload=0x{operands:08x}/0x{immediate:08x}"
        return BinasmRecord(
            index,
            offset,
            words,
            kind,
            name,
            detail,
            None,
            evidence,
        )
    if words == (0, 0, 0, 0):
        return BinasmRecord(index, offset, words, "empty", "zero", "all-zero record")
    return BinasmRecord(
        index,
        offset,
        words,
        "unknown",
        "unknown",
        "unclassified record; raw words retained",
        None,
        "none",
    )


def _literal_payload_records(byte_length: int) -> int:
    """Return how many 16-byte records one ASCII float literal occupies."""

    return (byte_length + BINASM_RECORD_SIZE - 1) // BINASM_RECORD_SIZE


def parse_binasm(source: StreamSource, *, byteorder: str = "big") -> list[BinasmRecord]:
    """Parse a fixed 16-byte IDO Binasm stream without discarding unknowns."""

    data = read_stream_bytes(source)
    if byteorder not in {"big", "little"}:
        raise ValueError("Binasm byte order must be 'big' or 'little'")
    if len(data) % BINASM_RECORD_SIZE:
        raise ValueError(
            f"Binasm stream is {len(data)} bytes; expected a multiple of "
            f"{BINASM_RECORD_SIZE} (trailing {len(data) % BINASM_RECORD_SIZE} byte(s))"
        )
    prefix = ">" if byteorder == "big" else "<"
    records: list[BinasmRecord] = []
    payload_remaining = 0
    for offset in range(0, len(data), BINASM_RECORD_SIZE):
        chunk = data[offset : offset + BINASM_RECORD_SIZE]
        words = struct.unpack(f"{prefix}IIII", chunk)
        index = offset // BINASM_RECORD_SIZE
        if payload_remaining:
            # A float literal's digits, not a record. Word-decoding these is
            # what turned ASCII such as b"96.0            " into invented
            # record families in the first ad hoc classifier.
            payload_remaining -= 1
            text = chunk.decode("ascii", errors="replace").rstrip()
            records.append(
                BinasmRecord(
                    index,
                    offset,
                    words,
                    "literal-payload",
                    "ascii-payload",
                    f"ASCII literal digits {text!r}",
                    None,
                    "calibrated",
                )
            )
            continue
        record = _classify_record(index, offset, words)
        records.append(record)
        if record.name == "float-literal":
            remaining = (len(data) - offset) // BINASM_RECORD_SIZE - 1
            payload_remaining = min(_literal_payload_records(words[3]), remaining)
    return records


def parse_peepdbg(text: str) -> tuple[list[PeepEvent], list[str]]:
    """Parse known IDO 7.1 peephole debug lines and retain unknown debug lines."""

    events: list[PeepEvent] = []
    unparsed: list[str] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped:
            continue
        match = _PEEP_REPLACEMENT_RE.match(stripped)
        if match is not None:
            values = match.groupdict()
            events.append(
                PeepEvent(
                    line=line_number,
                    family=values["family"],
                    action="register-replacement",
                    inst=int(values["inst"]),
                    register=int(values["register"]),
                    with_register=int(values["with_register"]),
                    text=stripped,
                )
            )
            continue
        match = _PEEP_NOP_RE.match(stripped)
        if match is not None:
            values = match.groupdict()
            events.append(
                PeepEvent(
                    line=line_number,
                    family=values["family"],
                    action="changed-to-nop",
                    inst=int(values["inst"]),
                    text=stripped,
                )
            )
            continue
        match = _PEEP_RS_RE.match(stripped)
        if match is not None:
            values = match.groupdict()
            events.append(
                PeepEvent(
                    line=line_number,
                    family=values["family"],
                    action="source-register-rewrite",
                    inst=int(values["inst"]),
                    register=int(values["register"]),
                    with_register=int(values["with_register"]),
                    text=stripped,
                )
            )
            continue
        match = _PEEP_MEMORY_RE.match(stripped)
        if match is not None:
            values = match.groupdict()
            events.append(
                PeepEvent(
                    line=line_number,
                    family=values["family"],
                    action="memory-rewrite",
                    inst=int(values["inst"]),
                    register=int(values["register"]),
                    operation=values["operation"],
                    text=stripped,
                )
            )
            continue
        if stripped.startswith(">>"):
            unparsed.append(raw)
    return events, unparsed


def _peep_report(text: str, *, limit: int) -> dict[str, Any]:
    events, unparsed = parse_peepdbg(text)
    actions = Counter(item.action for item in events)
    families = Counter(item.family for item in events)
    replacement_nop_pairs: list[dict[str, Any]] = []
    for before, after in pairwise(events):
        if (
            before.action == "register-replacement"
            and after.action == "changed-to-nop"
            and before.family == after.family
        ):
            replacement_nop_pairs.append(
                {"replacement": before.as_dict(), "removed_copy": after.as_dict()}
            )
    return {
        "event_count": len(events),
        "action_counts": dict(sorted(actions.items())),
        "family_counts": dict(sorted(families.items())),
        "replacement_nop_pair_count": len(replacement_nop_pairs),
        "replacement_nop_pairs": replacement_nop_pairs[:limit],
        "events": [item.as_dict() for item in events[:limit]],
        "unparsed_debug_line_count": len(unparsed),
        "unparsed_debug_lines": unparsed[:limit],
        "correlation_scope": (
            "INST is pass-local in this trace. Without block/address records it "
            "cannot be mapped honestly to a Binasm byte offset; use it to name "
            "the owning peephole and the observed register pair."
        ),
    }


def _probe_family(name: str) -> str:
    lowered = name.casefold()
    if "identity" in lowered:
        return "identity-instruction"
    if "loc" in lowered:
        return "source-location"
    if "alias" in lowered or "live" in lowered or "metadata" in lowered:
        return "dependency-metadata"
    if "label" in lowered:
        return "control-flow-label"
    if any(
        marker in lowered
        for marker in (
            "nomove",
            "volatile",
            "reorder",
            "macro",
            "transform",
            "bopt",
            "noat",
            "set-",
        )
    ):
        return "assembler-mode"
    return "unclassified"


def _probe_site(name: str) -> str | None:
    lowered = name.casefold().replace("_", "-")
    for marker in (
        "pre-move",
        "post-move",
        "pre-add",
        "post-add",
        "around-add",
        "add-only",
        "move-branch",
        "move-through-add",
        "dispatch-range",
    ):
        if marker in lowered:
            return marker
    return None


def _probe_source_levers(families: Counter[str]) -> list[dict[str, Any]]:
    guidance = {
        "identity-instruction": (
            "Search edge-local width normalization, a copy carrier, or redundant "
            "arithmetic whose Binasm record survives ugen. Confirm the record first; "
            "the C optimizer erases most literal identities."
        ),
        "source-location": (
            "Search statement attribution or a controlled #line change only after "
            "confirming the active frontend/debug mode emits LOC records."
        ),
        "dependency-metadata": (
            "Search alias provenance, volatile access, or call-liveness shapes that "
            "make ugen emit dependency metadata at the boundary."
        ),
        "control-flow-label": (
            "Search a real control-flow join, edge split, or explicit goto/label. "
            "A source label optimized away before Binasm cannot be the lever."
        ),
        "assembler-mode": (
            "Treat this as boundary localization, not a direct C spelling. Seek a "
            "source-emitted record that interrupts the same peephole interval."
        ),
        "unclassified": (
            "Retain and classify the winning inserted record before translating it "
            "into a source hypothesis."
        ),
    }
    return [
        {"family": family, "exact_count": count, "next": guidance[family]}
        for family, count in families.most_common()
    ]


def _barrier_probe_report(value: Any, *, limit: int) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("results"), list):
        raise ValueError("barrier probe JSON must contain a top-level results list")
    results = [item for item in value["results"] if isinstance(item, dict)]
    exact = [item for item in results if item.get("exact") is True]
    families = Counter(
        _probe_family(str(item.get("name", "unnamed"))) for item in exact
    )
    sites = Counter(
        site
        for item in exact
        if (site := _probe_site(str(item.get("name", "")))) is not None
    )
    names = [str(item.get("name", "unnamed")) for item in exact]
    return {
        "probe_count": len(results),
        "failure_count": len(value.get("failures", [])),
        "exact_count": len(exact),
        "exact_names": names[:limit],
        "exact_names_truncated": len(names) > limit,
        "family_counts": dict(sorted(families.items())),
        "site_counts": dict(sorted(sites.items())),
        "source_search": _probe_source_levers(families),
        "strongest_claim": (
            "These exact cells prove that their inserted Binasm record or mode "
            "boundary is sufficient downstream of ugen. They do not prove a C "
            "spelling emits or retains that record."
        ),
    }


def build_binasm_boundary_report(
    path: str | Path,
    *,
    boundary: int,
    radius: int = 4,
    byteorder: str = "big",
    peep_text: str | None = None,
    probe_results: Any | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Build a read-only phase-boundary report around one record insertion site."""

    if radius < 0:
        raise ValueError("window radius must be non-negative")
    if limit <= 0:
        raise ValueError("report limit must be positive")
    source = Path(path).expanduser().resolve()
    data = source.read_bytes()
    records = parse_binasm(data, byteorder=byteorder)
    if boundary < 0 or boundary > len(data):
        raise ValueError(
            f"boundary {boundary:#x} is outside stream range 0x0..{len(data):x}"
        )
    if boundary % BINASM_RECORD_SIZE:
        raise ValueError(
            f"boundary {boundary:#x} is not aligned to a {BINASM_RECORD_SIZE}-byte "
            "record; pass the insertion offset before a record"
        )
    boundary_index = boundary // BINASM_RECORD_SIZE
    first = max(0, boundary_index - radius)
    last = min(len(records), boundary_index + radius)
    window = []
    for record in records[first:last]:
        item = record.as_dict()
        item["boundary_before"] = record.index == boundary_index
        window.append(item)
    kinds = Counter(item.kind for item in records)
    report: dict[str, Any] = {
        "schema": BINASM_REPORT_SCHEMA,
        "format": {
            "record_size": BINASM_RECORD_SIZE,
            "byteorder": byteorder,
            "decoder_scope": (
                "Known Binasm record families only; unknown records remain raw and "
                "lossless. Instruction operands are not guessed. Each record "
                "carries `evidence`: calibrated (this exact record form was "
                "established by a probe listing, an as1 diagnostic, or a "
                "structural pairing), inferred (only observed, or a variant of "
                "a calibrated family carrying unexplained bits, which are "
                "rendered as flags=0x....), or none (left raw)."
            ),
        },
        "stream": {
            "path": str(source),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "record_count": len(records),
            "kind_counts": dict(sorted(kinds.items())),
            "evidence_counts": dict(
                sorted(Counter(item.evidence for item in records).items())
            ),
        },
        "boundary": {
            "offset": boundary,
            "offset_hex": f"0x{boundary:x}",
            "record_index": boundary_index,
            "meaning": "insertion point before record_index",
            "before": (
                records[boundary_index - 1].as_dict() if boundary_index else None
            ),
            "after": (
                records[boundary_index].as_dict()
                if boundary_index < len(records)
                else None
            ),
            "window": window,
        },
        "proof": (
            "This report reads retained files only. It does not run as1, compile "
            "source, mutate the Binasm stream, or execute generated code."
        ),
        "warnings": [
            "Binasm opcode names are calibrated record-family labels, not a full "
            "assembly disassembly.",
            "A downstream exact barrier is a pass-local sufficiency proof, not "
            "source-correctness or upstream-survival evidence.",
        ],
    }
    if peep_text is not None:
        report["peephole"] = _peep_report(peep_text, limit=limit)
    if probe_results is not None:
        report["barrier_probes"] = _barrier_probe_report(probe_results, limit=limit)
    return report
