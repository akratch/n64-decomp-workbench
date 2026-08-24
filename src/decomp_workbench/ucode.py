"""Decode retained IDO binary Ucode switch dispatches.

IDO's binary Ucode is a variable-width stream of big-endian 32-bit words.
This decoder follows the public IDO source definitions in ``ucode.h`` and
``libu/uini.c`` rather than searching for byte signatures. Its deliberately
narrow report answers the late-stage control-flow question that motivated it:
what selector expression feeds each ``Uxjp``, which label owns the case table,
which label is the default, and where does every dense table entry jump?

The format tables below are transcribed from n64decomp/ido commit
``d068e439``. Unknown semantic operands remain as raw words; record framing,
XJP operands, labels, and stack effects are decoded only where the source
format establishes them.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .binasm import (
    BINASM_RECORD_SIZE,
    StreamSource,
    parse_binasm,
    read_stream_bytes,
)

UCODE_REPORT_SCHEMA = "decomp-workbench-ucode-xjp-v1"

# Append-only Uopcode enum order from src/ucode.h.
OPCODE_NAMES: tuple[str, ...] = (
    "abs",
    "add",
    "adj",
    "aent",
    "and",
    "aos",
    "asym",
    "bgn",
    "bgnb",
    "bsub",
    "cg1",
    "cg2",
    "chkh",
    "chkl",
    "chkn",
    "chkt",
    "cia",
    "clab",
    "clbd",
    "comm",
    "csym",
    "ctrl",
    "cubd",
    "cup",
    "cvt",
    "cvtl",
    "dec",
    "def",
    "dif",
    "div",
    "dup",
    "end",
    "endb",
    "ent",
    "eof",
    "equ",
    "esym",
    "fill",
    "fjp",
    "fsym",
    "geq",
    "grt",
    "gsym",
    "hsym",
    "icuf",
    "idx",
    "iequ",
    "igeq",
    "igrt",
    "ijp",
    "ilda",
    "ildv",
    "ileq",
    "iles",
    "ilod",
    "inc",
    "ineq",
    "init",
    "inn",
    "int",
    "ior",
    "isld",
    "isst",
    "istr",
    "istv",
    "ixa",
    "lab",
    "lbd",
    "lbdy",
    "lbgn",
    "lca",
    "lda",
    "ldap",
    "ldc",
    "ldef",
    "ldsp",
    "lend",
    "leq",
    "les",
    "lex",
    "lnot",
    "loc",
    "lod",
    "lsym",
    "ltrm",
    "max",
    "min",
    "mod",
    "mov",
    "movv",
    "mpmv",
    "mpy",
    "mst",
    "mus",
    "neg",
    "neq",
    "nop",
    "not",
    "odd",
    "optn",
    "par",
    "pdef",
    "pmov",
    "pop",
    "regs",
    "rem",
    "ret",
    "rlda",
    "rldc",
    "rlod",
    "rnd",
    "rpar",
    "rstr",
    "sdef",
    "sgs",
    "shl",
    "shr",
    "sign",
    "sqr",
    "sqrt",
    "ssym",
    "step",
    "stp",
    "str",
    "stsp",
    "sub",
    "swp",
    "tjp",
    "tpeq",
    "tpge",
    "tpgt",
    "tple",
    "tplt",
    "tpne",
    "typ",
    "ubd",
    "ujp",
    "unal",
    "uni",
    "vreg",
    "xjp",
    "xor",
    "xpar",
    "mtag",
    "alia",
    "ildi",
    "isti",
    "irld",
    "irst",
    "ldrc",
    "msym",
    "rcuf",
    "ksym",
    "osym",
    "irlv",
    "irsv",
)

DTYPE_NAMES: tuple[str, ...] = (
    "Adt",
    "Cdt",
    "Fdt",
    "Gdt",
    "Hdt",
    "Idt",
    "Jdt",
    "Kdt",
    "Ldt",
    "Mdt",
    "Ndt",
    "Pdt",
    "Qdt",
    "Rdt",
    "Sdt",
    "Wdt",
    "Xdt",
    "Zdt",
)
MTYPE_NAMES: tuple[str, ...] = (
    "Zmt",
    "Mmt",
    "Pmt",
    "Rmt",
    "Smt",
    "Amt",
    "Tmt",
    "Kmt",
)

# uini.c defaults every instruction to two words and then overrides these.
_FOUR_WORD_OPS = frozenset(
    {
        "adj",
        "aent",
        "asym",
        "bgn",
        "cia",
        "clab",
        "comm",
        "csym",
        "ctrl",
        "cup",
        "cvt",
        "def",
        "dif",
        "ent",
        "esym",
        "fill",
        "fsym",
        "gsym",
        "hsym",
        "icuf",
        "iequ",
        "igeq",
        "igrt",
        "ildv",
        "ileq",
        "iles",
        "ilod",
        "ineq",
        "inn",
        "int",
        "isld",
        "isst",
        "istr",
        "istv",
        "ksym",
        "lab",
        "lca",
        "ldc",
        "ldef",
        "ldrc",
        "lod",
        "lsym",
        "mov",
        "mpmv",
        "msym",
        "mus",
        "optn",
        "osym",
        "par",
        "pdef",
        "pmov",
        "rcuf",
        "regs",
        "rlda",
        "rldc",
        "rlod",
        "rnd",
        "rpar",
        "rstr",
        "sdef",
        "sgs",
        "ssym",
        "str",
        "swp",
        "typ",
        "uni",
        "vreg",
        "ildi",
        "isti",
        "irld",
        "irst",
    }
)
_SIX_WORD_OPS = frozenset({"ilda", "lda", "init"})
_HAS_CONSTANT = frozenset({"cia", "comm", "init", "lca", "ldc", "rldc", "ssym"})
_VARIABLE_CONSTANT_DTYPES = frozenset({9, 12, 13, 14, 16})

# Stack effects copied from uini.c. They let the report find the exact postfix
# expression consumed by XJP instead of printing an arbitrary record window.
_PUSH_ONE = frozenset(
    {
        "abs",
        "add",
        "adj",
        "and",
        "bsub",
        "chkh",
        "chkl",
        "chkn",
        "cvt",
        "cvtl",
        "dec",
        "dif",
        "div",
        "dup",
        "equ",
        "geq",
        "grt",
        "idx",
        "iequ",
        "igeq",
        "igrt",
        "ilda",
        "ildi",
        "ileq",
        "iles",
        "ilod",
        "irld",
        "inc",
        "ineq",
        "inn",
        "int",
        "ior",
        "isld",
        "ixa",
        "lbd",
        "lca",
        "lda",
        "ldap",
        "ldc",
        "ldrc",
        "ldsp",
        "leq",
        "les",
        "lnot",
        "lod",
        "max",
        "min",
        "mod",
        "mpy",
        "mus",
        "neg",
        "neq",
        "not",
        "odd",
        "rem",
        "rnd",
        "sgs",
        "shl",
        "shr",
        "sign",
        "sqr",
        "sqrt",
        "sub",
        "swp",
        "typ",
        "ubd",
        "uni",
        "xor",
    }
)
_POP_ONE = frozenset(
    {
        "abs",
        "adj",
        "aos",
        "chkh",
        "chkl",
        "chkn",
        "chkt",
        "cvt",
        "cvtl",
        "dec",
        "fjp",
        "icuf",
        "ijp",
        "ilda",
        "ilod",
        "inc",
        "irld",
        "isld",
        "lbd",
        "lnot",
        "mpmv",
        "neg",
        "not",
        "odd",
        "par",
        "pmov",
        "pop",
        "rnd",
        "sgs",
        "sqr",
        "sqrt",
        "str",
        "stsp",
        "swp",
        "tjp",
        "typ",
        "ubd",
        "xjp",
        "xpar",
    }
)
_POP_TWO = frozenset(
    {
        "add",
        "and",
        "bsub",
        "dif",
        "div",
        "equ",
        "fill",
        "geq",
        "grt",
        "iequ",
        "igeq",
        "igrt",
        "ildi",
        "ileq",
        "iles",
        "ineq",
        "inn",
        "int",
        "ior",
        "irst",
        "isst",
        "istr",
        "ixa",
        "leq",
        "les",
        "max",
        "min",
        "mod",
        "mov",
        "mpy",
        "mus",
        "neq",
        "rem",
        "shl",
        "shr",
        "sign",
        "sub",
        "tpeq",
        "tpge",
        "tpgt",
        "tple",
        "tplt",
        "tpne",
        "uni",
        "xor",
    }
)
_POP_THREE = frozenset({"idx", "isti"})

_CONTROL_BOUNDARIES = frozenset(
    {
        "bgn",
        "bgnb",
        "clab",
        "end",
        "endb",
        "fjp",
        "ijp",
        "lab",
        "ldef",
        "ret",
        "tjp",
        "ujp",
        "xjp",
    }
)


def _signed(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return value - (1 << bits) if value & sign else value


def _dtype_name(dtype: int) -> str:
    return DTYPE_NAMES[dtype] if dtype < len(DTYPE_NAMES) else f"dtype-{dtype}"


def _base_word_length(name: str) -> int:
    if name == "xjp":
        return 8
    if name in _SIX_WORD_OPS:
        return 6
    if name in _FOUR_WORD_OPS:
        return 4
    return 2


def _stack_pop(name: str) -> int:
    if name in _POP_THREE:
        return 3
    if name in _POP_TWO:
        return 2
    if name in _POP_ONE:
        return 1
    return 0


def _wrong_pass_format_hint(data: bytes) -> str:
    """Name fixed-record Binasm when it was passed as variable Ucode."""

    if not data or len(data) % BINASM_RECORD_SIZE:
        return ""
    records = parse_binasm(data)
    recognized = sum(record.kind != "unknown" for record in records)
    # Binasm deliberately retains unknown record families, so demand a strong
    # majority rather than requiring every record to have a calibrated name.
    if recognized * 4 < len(records) * 3:
        return ""
    return (
        f"; input appears to be fixed {BINASM_RECORD_SIZE}-byte Binasm "
        f"({recognized}/{len(records)} records recognized). UGEN's -temp "
        "output is Binasm-shaped, not its input Ucode; inspect that file with "
        "`pass binasm` and give `pass ucode` UGEN's positional input"
    )


@dataclass(frozen=True)
class UcodeRecord:
    """One losslessly framed IDO binary Ucode instruction."""

    index: int
    word_offset: int
    words: tuple[int, ...]
    opcode: int
    name: str
    dtype: int
    mtype: int
    lexlev: int
    base_word_length: int

    @property
    def byte_offset(self) -> int:
        return self.word_offset * 4

    @property
    def raw_hex(self) -> str:
        return " ".join(f"{word:08x}" for word in self.words)

    @property
    def integer_constant(self) -> int | None:
        """Return the active integer member of an Uldc ``union Valu``.

        ``Sconstval`` always occupies two words, but a single-word Jdt/Ldt
        constant uses only ``swpart.Ival`` (the first on-disk payload word).
        The companion word is the inactive ``swpart.Chars`` member and can
        retain unrelated data.  Idt/Kdt are emitted low-word first by
        ``libu/bwri.c`` and therefore need reconstructing in the opposite
        order from XJP's big-endian bounds.
        """

        if self.name != "ldc" or len(self.words) < self.base_word_length + 2:
            return None
        first = self.words[self.base_word_length]
        second = self.words[self.base_word_length + 1]
        if self.dtype == 5:  # Idt: signed double-word integer
            return _signed((second << 32) | first, 64)
        if self.dtype == 6:  # Jdt: signed single-word integer
            return _signed(first, 32)
        if self.dtype == 7:  # Kdt: unsigned double-word integer
            return (second << 32) | first
        if self.dtype == 8:  # Ldt: non-negative single-word integer
            return first
        return None

    @property
    def detail(self) -> str:
        if self.name == "xjp":
            return (
                f"cases=L{self.words[1]} default=L{self.words[2]} "
                f"range={self.lower_bound}..{self.upper_bound}"
            )
        if self.name == "clab":
            return f"label=L{self.words[1]} entries={self.words[2]}"
        if self.name in {"lab", "ldef"}:
            return f"label=L{self.words[1]}"
        if self.name in {"fjp", "tjp", "ujp"}:
            return f"target=L{self.words[1]}"
        if self.name == "loc":
            return f"file={self.lexlev} line={self.words[1]}"
        if self.name == "ldc" and len(self.words) >= self.base_word_length + 2:
            constant = self.integer_constant
            if constant is not None:
                detail = f"constant={constant} length={self.words[2]}"
                if self.dtype in {6, 8}:
                    inactive = self.words[self.base_word_length + 1]
                    detail += f" inactive-word=0x{inactive:08x}"
                return detail
            payload = self.words[self.base_word_length : self.base_word_length + 2]
            return (
                f"constant-payload=0x{payload[0]:08x}/0x{payload[1]:08x} "
                f"length={self.words[2]}"
            )
        if self.name in {"lod", "str"}:
            return (
                f"{MTYPE_NAMES[self.mtype]} block={self.words[1]} "
                f"offset={_signed(self.words[2], 32)} length={self.words[3]}"
            )
        return f"dtype={_dtype_name(self.dtype)}"

    @property
    def lower_bound(self) -> int:
        if self.name != "xjp":
            raise ValueError("lower_bound is defined only for Uxjp")
        return _signed((self.words[4] << 32) | self.words[5], 64)

    @property
    def upper_bound(self) -> int:
        if self.name != "xjp":
            raise ValueError("upper_bound is defined only for Uxjp")
        return _signed((self.words[6] << 32) | self.words[7], 64)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "index": self.index,
            "byte_offset": self.byte_offset,
            "offset_hex": f"0x{self.byte_offset:x}",
            "word_count": len(self.words),
            "words": [f"0x{word:08x}" for word in self.words],
            "raw_hex": self.raw_hex,
            "opcode": self.opcode,
            "name": f"U{self.name}",
            "dtype": self.dtype,
            "dtype_name": _dtype_name(self.dtype),
            "mtype": self.mtype,
            "mtype_name": MTYPE_NAMES[self.mtype],
            "lexlev": self.lexlev,
            "detail": self.detail,
        }
        if self.name == "ldc" and len(self.words) >= self.base_word_length + 2:
            result["constant_storage_words"] = [
                f"0x{word:08x}"
                for word in self.words[
                    self.base_word_length : self.base_word_length + 2
                ]
            ]
            result["constant_value"] = self.integer_constant
            if self.dtype in {6, 8}:
                result["inactive_constant_word"] = (
                    f"0x{self.words[self.base_word_length + 1]:08x}"
                )
        return result


def parse_ucode(source: StreamSource) -> tuple[UcodeRecord, ...]:
    """Parse one complete big-endian IDO binary Ucode stream."""

    data = read_stream_bytes(source)
    if len(data) % 4:
        raise ValueError(
            f"Ucode stream is {len(data)} bytes; expected complete 32-bit words"
        )
    raw_words = struct.unpack(f">{len(data) // 4}I", data)
    records: list[UcodeRecord] = []
    cursor = 0
    while cursor < len(raw_words):
        header = raw_words[cursor]
        opcode = header >> 24
        if opcode >= len(OPCODE_NAMES):
            raise ValueError(
                f"unknown Ucode opcode 0x{opcode:02x} at byte offset 0x{cursor * 4:x}"
                f"{_wrong_pass_format_hint(data)}"
            )
        name = OPCODE_NAMES[opcode]
        dtype = (header >> 16) & 0x1F
        base_length = _base_word_length(name)
        total_length = base_length
        if name in _HAS_CONSTANT:
            total_length += 2
            if dtype in _VARIABLE_CONSTANT_DTYPES or name == "comm":
                if cursor + base_length >= len(raw_words):
                    raise ValueError(
                        f"truncated U{name} constant at byte offset 0x{cursor * 4:x}"
                    )
                byte_length = raw_words[cursor + base_length]
                payload_words = (byte_length + 3) // 4
                if payload_words & 1:
                    payload_words += 1
                total_length += payload_words
        end = cursor + total_length
        if end > len(raw_words):
            raise ValueError(
                f"truncated U{name} at byte offset 0x{cursor * 4:x}: "
                f"needs {total_length} words, only {len(raw_words) - cursor} remain"
            )
        records.append(
            UcodeRecord(
                index=len(records),
                word_offset=cursor,
                words=tuple(raw_words[cursor:end]),
                opcode=opcode,
                name=name,
                dtype=dtype,
                mtype=(header >> 21) & 0x7,
                lexlev=header & 0xFFFF,
                base_word_length=base_length,
            )
        )
        cursor = end
    return tuple(records)


def _selector_expression(
    records: tuple[UcodeRecord, ...], xjp_index: int, *, limit: int
) -> tuple[tuple[UcodeRecord, ...], bool]:
    """Recover the postfix expression whose single result XJP consumes."""

    needed = 1
    selected: list[UcodeRecord] = []
    start = max(0, xjp_index - limit)
    for record in reversed(records[start:xjp_index]):
        if record.name in _CONTROL_BOUNDARIES:
            break
        pushes = 1 if record.name in _PUSH_ONE else 0
        if pushes == 0:
            # LOC and other metadata can sit between expression records; they
            # do not participate in the postfix stack slice.
            continue
        selected.append(record)
        needed = needed - 1 + _stack_pop(record.name)
        if needed == 0:
            break
    selected.reverse()
    return tuple(selected), needed == 0


def _case_table(
    records: tuple[UcodeRecord, ...], xjp_index: int
) -> tuple[UcodeRecord | None, tuple[UcodeRecord, ...]]:
    """Resolve the Uclab and dense Uujp records immediately after XJP."""

    xjp = records[xjp_index]
    next_index = xjp_index + 1
    if next_index >= len(records):
        return None, ()
    clab = records[next_index]
    if clab.name != "clab" or clab.words[1] != xjp.words[1]:
        return None, ()
    expected = clab.words[2]
    jumps: list[UcodeRecord] = []
    for record in records[next_index + 1 : next_index + 1 + expected]:
        if record.name != "ujp":
            break
        jumps.append(record)
    return clab, tuple(jumps)


def _label_blocks(
    records: tuple[UcodeRecord, ...],
) -> dict[int, tuple[UcodeRecord, ...]]:
    """Index ordinary ``Ulab`` blocks by label number.

    This deliberately stops only at the next ordinary label.  A switch case
    trampoline emitted by the C frontend is normally ``Ulab`` plus metadata
    and one ``Uujp``; retaining the complete slice makes the classification
    auditable when a less trivial record appears after the jump.
    """

    positions = [index for index, record in enumerate(records) if record.name == "lab"]
    blocks: dict[int, tuple[UcodeRecord, ...]] = {}
    for offset, start in enumerate(positions):
        end = positions[offset + 1] if offset + 1 < len(positions) else len(records)
        label = records[start].words[1]
        blocks[label] = records[start:end]
    return blocks


def _trivial_jump_target(block: tuple[UcodeRecord, ...]) -> int | None:
    """Return the destination of a metadata-only label/jump trampoline."""

    semantic = [
        record for record in block if record.name not in {"lab", "loc", "nop", "comm"}
    ]
    if len(semantic) == 1 and semantic[0].name == "ujp":
        return semantic[0].words[1]
    return None


def _case_target_chain(
    blocks: dict[int, tuple[UcodeRecord, ...]],
    target: int,
    *,
    limit: int = 32,
) -> dict[str, Any]:
    """Trace a case target through zero-work ``Uujp`` trampolines."""

    labels = [target]
    visited = {target}
    status = "direct"
    for _ in range(limit):
        block = blocks.get(labels[-1])
        if block is None:
            status = "missing-label"
            break
        next_target = _trivial_jump_target(block)
        if next_target is None:
            status = "trampoline" if len(labels) > 1 else "direct"
            break
        status = "trampoline"
        if next_target in visited:
            labels.append(next_target)
            status = "cycle"
            break
        labels.append(next_target)
        visited.add(next_target)
    else:
        status = "limit"

    terminal_block = blocks.get(labels[-1])
    return {
        "labels": labels,
        "hop_count": len(labels) - 1,
        "effective_target_label": labels[-1],
        "status": status,
        "terminal_block_record_count": (
            len(terminal_block) if terminal_block is not None else None
        ),
        "terminal_block_preview": (
            [record.as_dict() for record in terminal_block[:8]]
            if terminal_block is not None
            else None
        ),
    }


def build_ucode_xjp_report(
    stream: str | Path, *, expression_limit: int = 64
) -> dict[str, Any]:
    """Build a machine-readable report for every XJP in one retained stream."""

    if expression_limit < 1:
        raise ValueError("expression limit must be at least 1")
    path = Path(stream)
    data = path.read_bytes()
    records = parse_ucode(data)
    blocks = _label_blocks(records)
    dispatches: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if record.name != "xjp":
            continue
        expression, complete = _selector_expression(
            records, index, limit=expression_limit
        )
        clab, jumps = _case_table(records, index)
        lower = record.lower_bound
        upper = record.upper_bound
        span = upper - lower + 1 if upper >= lower else 0
        targets = [jump.words[1] for jump in jumps]
        target_chains = [_case_target_chain(blocks, target) for target in targets]
        dispatches.append(
            {
                "xjp": record.as_dict(),
                "case_table_label": record.words[1],
                "default_label": record.words[2],
                "lower_bound": lower,
                "upper_bound": upper,
                "range_size": span,
                "selector_expression": [item.as_dict() for item in expression],
                "selector_expression_complete": complete,
                "case_table": clab.as_dict() if clab is not None else None,
                "case_targets": targets,
                "cases": [
                    {
                        "value": lower + offset,
                        "target_label": target,
                        "target_chain": target_chains[offset],
                    }
                    for offset, target in enumerate(targets)
                ],
                "trampoline_case_count": sum(
                    chain["hop_count"] > 0 for chain in target_chains
                ),
                "case_table_complete": clab is not None and len(jumps) == span,
            }
        )
    return {
        "schema": UCODE_REPORT_SCHEMA,
        "stream": {
            "path": str(path),
            "bytes": len(data),
            "words": len(data) // 4,
            "record_count": len(records),
            "sha256": hashlib.sha256(data).hexdigest(),
            "byteorder": "big",
        },
        "dispatch_count": len(dispatches),
        "dispatches": dispatches,
        "format_source": {
            "repository": "https://github.com/n64decomp/ido",
            "revision": "d068e439f52615763a3facd6944873899ebad2fd",
            "files": ["src/ucode.h", "src/libu/uini.c"],
        },
        "proof": (
            "This is static pass-boundary evidence: it establishes the binary "
            "Ucode selector, XJP labels/range, encoded dense table, and any "
            "metadata-only Uujp trampoline chains. It does not by itself prove "
            "which C spelling emitted that Ucode."
        ),
    }
