"""Verify a campaign/scratch target object's scope before anyone matches it.

The motivating case is `docs/history/postmortem-2026-08-24-cef4c-exact.md`,
finding 7: ten days of campaign work against `func_ovl0_800CEF4C` assumed a
hosted decomp.me `target.o`'s scope was ground truth. It was not. The
splat extraction that produced it symbolized the function's own literal
pool -- four per-use-site copies of the `2048/pi` scale constant
(`0x4422F983`), stored in `.rodata` immediately after the function's two
jump tables -- as four *external* data symbols (`D_ovl0_800D6120` through
`..612C`) and truncated `target.o`'s `.rodata` at the jump table's own end,
20 bytes short of where the function's real read-only data stops. A
ROM-faithful, words=0 candidate scored 5 against that target for exactly
those 20 missing bytes, and nothing about the score said why: the campaign
had to autopsy the ELF and the ROM by hand to find it. See
`docs/target-audit.md` for the full worked narrative.

This module is the one-minute check that finding needed on day one. It is
entirely static plus one optional read-only ROM peek -- no compiler, no
linker, no decomp.me round trip:

1. **ELF sanity** (`_sanity_findings`): sections present, relocation entry
   counts consistent with their declared `sh_entsize`, symbol table indices
   in range. An object that fails this cannot support any of the findings
   below, so these come first and are refused loudly rather than silently
   producing a report with holes in it.
2. **The literal-pool truncation heuristic** (`_literal_pool_findings`):
   the exact shape of the cef4c defect. A relocation in `.text` loads
   through `$at` (`lwc1`/`ldc1`, or a plain `lw` doing the same address
   arithmetic) into an *undefined* symbol -- the object references a datum
   it does not itself carry -- while `.rel.rodata` shows the section's
   jump table (entries whose relocation symbol resolves into `.text`)
   running all the way to `.rodata`'s own declared end, with zero bytes
   left over. That coincidence is exactly what happened to `target.o`: a
   function-owned literal pool that used to sit right after the jump table
   was carved off and externalized, and the truncated section's size hides
   the fact perfectly -- there is no gap to notice by eye.
3. **Data-scope report** (`data_scope` on the result): section sizes, the
   jump table's own extent, and every undefined symbol `.text` reaches
   through a `%hi`/`%lo` pair, with the addends each site uses.
4. **Optional ROM cross-check** (`--rom`/`--rom-offset`/`--va`): read the
   ROM bytes immediately past the object's own extracted `.rodata` extent
   and report what is there. On the cef4c object this is
   `4422F983 4422F983 4422F983 4422F983`, contiguous with the jump table
   and four-for-four with the four undefined symbols `.text` loads through
   `$at` -- the ROM itself proving the pool belongs to the function, in one
   read.

Severities compose into one verdict a caller can gate a campaign
registration on: any `defect` makes the verdict `defects`; otherwise any
`warning` makes it `warnings`; otherwise `ok`. `info` findings never affect
the verdict -- they are evidence, not problems.
"""

from __future__ import annotations

import struct
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .elf import ElfFormatError, ElfObject, read_elf

__all__ = [
    "DEFECT",
    "INFO",
    "ROM_READ_MAX_BYTES",
    "ROM_READ_MIN_BYTES",
    "TARGET_AUDIT_SCHEMA",
    "WARNING",
    "ElfFormatError",
    "Finding",
    "TargetAudit",
    "audit_target",
    "target_audit_lines",
]

TARGET_AUDIT_SCHEMA = "decomp-workbench-target-audit-v1"

DEFECT = "defect"
WARNING = "warning"
INFO = "info"

_SEVERITY_ORDER = {DEFECT: 0, WARNING: 1, INFO: 2}

#: MIPS I-type opcode field (bits 31:26), the six shapes a literal-pool
#: access through `$at` takes. `lw` is included beside the two FP loads on
#: purpose -- an IDO object occasionally loads a pool word into a GPR before
#: an `mtc1`, and that site binds to the same undefined symbol the direct
#: `lwc1`/`ldc1` sites do.
OP_LW = 0x23
OP_LWC1 = 0x31
OP_LDC1 = 0x35
OPCODE_NAMES: dict[int, str] = {OP_LW: "lw", OP_LWC1: "lwc1", OP_LDC1: "ldc1"}

#: The register `$at` (`$1`), the assembler's own scratch register and the
#: one every `lui %hi(sym); OP %lo(sym)($at)` pair loads through. A load
#: through any other base register is addressing something else -- a
#: struct field through a real pointer, not a pool slot -- and is
#: deliberately left out of the heuristic (see the two `lw` sites in the
#: real cef4c object that load through `$a1`/`$v0` and are not literal-pool
#: accesses at all).
REGISTER_AT = 1

#: `--rom` window size around the object's own extracted `.rodata` extent:
#: at least this many bytes, and at least four per undefined FP-pool symbol
#: found (a literal pool this module has ever seen has never needed more).
ROM_READ_MIN_BYTES = 16
ROM_READ_MAX_BYTES = 64


def _word(data: bytes, offset: int) -> int | None:
    if offset < 0 or offset + 4 > len(data):
        return None
    (value,) = struct.unpack_from(">I", data, offset)
    return int(value)


def _opcode(word: int) -> int:
    return (word >> 26) & 0x3F


def _rs(word: int) -> int:
    return (word >> 21) & 0x1F


def _signed_lo(word: int) -> int:
    value = word & 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


@dataclass(frozen=True)
class Finding:
    """One thing this audit noticed, with enough evidence to act on it."""

    severity: str
    code: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class TargetAudit:
    """The full report: verdict, findings, and the evidence behind them."""

    path: str
    verdict: str
    findings: tuple[Finding, ...]
    data_scope: dict[str, Any]
    rom_check: dict[str, Any] | None

    @property
    def defects(self) -> int:
        return sum(1 for item in self.findings if item.severity == DEFECT)

    @property
    def warnings(self) -> int:
        return sum(1 for item in self.findings if item.severity == WARNING)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": TARGET_AUDIT_SCHEMA,
            "path": self.path,
            "verdict": self.verdict,
            "defects": self.defects,
            "warnings": self.warnings,
            "findings": [item.as_dict() for item in self.findings],
            "data_scope": self.data_scope,
            "rom_check": self.rom_check,
        }


#: How many offending symbols/relocations a capped evidence list prints
#: before falling back to "+N more" -- long enough to see the shape of a
#: real problem, short enough that a stripped object's thousand-symbol
#: table does not bury the one sentence that names the finding.
_EVIDENCE_LIMIT = 20


def _capped(items: list[Any]) -> tuple[list[Any], int]:
    shown = items[:_EVIDENCE_LIMIT]
    return shown, max(0, len(items) - len(shown))


def _sanity_findings(elf: ElfObject) -> list[Finding]:
    """ELF sanity: sections present, reloc/symtab structure consistent.

    Everything below this line depends on `.text`'s relocations and
    `.symtab`'s symbols meaning what their headers claim; an object that
    fails here gets those findings anyway (a missing section reads as
    "no sites found", not a crash), but a reader needs to know the negative
    result is not evidence of a clean object.
    """

    findings: list[Finding] = []
    if elf.section(".text") is None:
        findings.append(
            Finding(
                DEFECT,
                "missing-text-section",
                "the object has no `.text` section at all",
                {},
            )
        )
    symtab = elf.section(".symtab")
    if symtab is None:
        findings.append(
            Finding(
                DEFECT,
                "missing-symtab",
                "the object has no `.symtab`; a stripped object cannot be "
                "scoped against its own relocations",
                {},
            )
        )
    elif symtab.size % 16 != 0:
        findings.append(
            Finding(
                DEFECT,
                "symtab-entsize-mismatch",
                f".symtab size {symtab.size} is not a multiple of the "
                "Elf32_Sym entry size (16)",
                {"symtab_size": symtab.size},
            )
        )
    elif (
        not (0 <= symtab.link < len(elf.sections))
        or elf.sections[symtab.link].type != 3
    ):
        findings.append(
            Finding(
                DEFECT,
                "symtab-link-invalid",
                f".symtab's sh_link ({symtab.link}) does not name a string "
                "table section",
                {"sh_link": symtab.link},
            )
        )

    for name in elf.malformed_reloc_sections:
        findings.append(
            Finding(
                DEFECT,
                "reloc-section-malformed",
                f"the relocation section covering `{name}` has an entry "
                "size, target section, or symbol-table link that does not "
                "match a conforming Elf32_Rel table",
                {"applies_to": name},
            )
        )

    max_symbol = len(elf.symbols)
    bad_shndx = [
        symbol.index
        for symbol in elf.symbols
        if symbol.shndx not in (0, 0xFFF1, 0xFFF2)
        and symbol.shndx < 0xFF00
        and symbol.shndx >= len(elf.sections)
    ]
    if bad_shndx:
        shown, extra = _capped(bad_shndx)
        findings.append(
            Finding(
                DEFECT,
                "symbol-shndx-invalid",
                f"{len(bad_shndx)} symbol(s) name a section index past the "
                "object's own section table",
                {"symbol_indices": shown, "more": extra},
            )
        )

    bad_reloc_syms: list[dict[str, Any]] = []
    for section_name, entries in elf.relocations.items():
        for entry in entries:
            if not (0 <= entry.sym_index < max_symbol):
                bad_reloc_syms.append(
                    {
                        "applies_to": section_name,
                        "offset": entry.offset,
                        "sym_index": entry.sym_index,
                    }
                )
    if bad_reloc_syms:
        shown, extra = _capped(bad_reloc_syms)
        findings.append(
            Finding(
                DEFECT,
                "reloc-symbol-index-out-of-range",
                f"{len(bad_reloc_syms)} relocation(s) name a symbol index "
                "outside the object's own symbol table",
                {"relocations": shown, "more": extra},
            )
        )
    return findings


@dataclass(frozen=True)
class _PoolEvidence:
    """What the literal-pool heuristic and the data-scope report share."""

    jump_table_offsets: tuple[int, ...]
    table_start: int | None
    table_end: int | None
    rodata_size: int
    bytes_after_table: int | None
    #: True when the relocated words are one dense ascending run of 4-byte
    #: slots. A jump table is exactly that; a struct holding two function
    #: pointers among other fields is not.
    table_contiguous: bool
    #: Relocations into `.text` whose `.rodata` offset does not fit inside
    #: `.rodata`. A malformed object, reported rather than arithmetically
    #: absorbed -- before the clamp they produced a *negative* count of the
    #: bytes after the table, which read as "the section is over-full".
    out_of_range_offsets: tuple[int, ...]
    fp_pool_sites: tuple[dict[str, Any], ...]
    undef_hilo_symbols: dict[str, list[int | None]]

    @property
    def table_shape_confirmed(self) -> bool:
        """True when the relocated words have the shape the defect requires.

        The cef4c truncation is a *function's own* `.rodata`: its jump table
        starts the section and the pool used to follow it. A const array of
        function pointers relocates into `.text` the same way and, when it
        ends the section, produces the same "zero bytes after the table"
        coincidence on a perfectly healthy object -- but it sits after the
        section's other data rather than at its start. Requiring the run to
        be dense and to begin at offset 0 keeps the defect and drops that
        false positive to a warning.
        """

        return self.table_contiguous and self.table_start == 0

    @property
    def truncated_at_table(self) -> bool:
        return (
            self.bytes_after_table == 0
            and self.table_shape_confirmed
            and bool(self.fp_pool_sites)
        )


def _pool_evidence(elf: ElfObject) -> _PoolEvidence:
    text_section = elf.section(".text")
    rodata_section = elf.section(".rodata")
    text_bytes = elf.section_bytes(".text") or b""
    text_index = text_section.index if text_section is not None else None
    rodata_size = rodata_section.size if rodata_section is not None else 0

    relocated: list[int] = []
    if text_index is not None:
        for entry in elf.relocations_for(".rodata"):
            symbol = elf.symbol(entry.sym_index)
            if symbol is not None and symbol.shndx == text_index:
                relocated.append(entry.offset)
    jump_table_offsets = sorted(
        offset for offset in relocated if 0 <= offset and offset + 4 <= rodata_size
    )
    out_of_range = tuple(
        sorted(offset for offset in relocated if offset < 0 or offset + 4 > rodata_size)
    )
    table_start = jump_table_offsets[0] if jump_table_offsets else None
    table_end = jump_table_offsets[-1] + 4 if jump_table_offsets else None
    table_contiguous = table_end is not None and jump_table_offsets == list(
        range(jump_table_offsets[0], table_end, 4)
    )
    # Clamped by construction: an offset that does not fit inside `.rodata`
    # never reaches `table_end`, so this cannot go negative.
    bytes_after_table = rodata_size - table_end if table_end is not None else None

    fp_pool_sites: list[dict[str, Any]] = []
    undef_hilo: dict[str, list[int | None]] = {}
    for entry in elf.relocations_for(".text"):
        if entry.kind not in ("R_MIPS_HI16", "R_MIPS_LO16"):
            continue
        symbol = elf.symbol(entry.sym_index)
        if symbol is None or symbol.defined:
            continue
        if entry.kind == "R_MIPS_HI16":
            undef_hilo.setdefault(symbol.name, [])
            continue
        word = _word(text_bytes, entry.offset)
        addend = _signed_lo(word) if word is not None else None
        undef_hilo.setdefault(symbol.name, []).append(addend)
        if word is None:
            continue
        opcode = _opcode(word)
        if opcode not in OPCODE_NAMES or _rs(word) != REGISTER_AT:
            continue
        fp_pool_sites.append(
            {
                "text_offset": entry.offset,
                "symbol": symbol.name,
                "opcode": OPCODE_NAMES[opcode],
                "addend": addend,
            }
        )

    return _PoolEvidence(
        jump_table_offsets=tuple(jump_table_offsets),
        table_start=table_start,
        table_end=table_end,
        rodata_size=rodata_size,
        bytes_after_table=bytes_after_table,
        table_contiguous=table_contiguous,
        out_of_range_offsets=out_of_range,
        fp_pool_sites=tuple(fp_pool_sites),
        undef_hilo_symbols=undef_hilo,
    )


def _literal_pool_findings(evidence: _PoolEvidence) -> list[Finding]:
    findings: list[Finding] = []
    if not evidence.fp_pool_sites:
        return findings

    symbols = sorted({site["symbol"] for site in evidence.fp_pool_sites})
    common = {
        "fp_pool_sites": list(evidence.fp_pool_sites),
        "distinct_undef_symbols": symbols,
        "jump_table_words": len(evidence.jump_table_offsets),
        "jump_table_start": evidence.table_start,
        "jump_table_end": evidence.table_end,
        "jump_table_contiguous": evidence.table_contiguous,
        "rodata_size": evidence.rodata_size,
        "bytes_after_jump_table": evidence.bytes_after_table,
        "rodata_relocations_out_of_range": list(evidence.out_of_range_offsets),
    }

    if evidence.table_end is None:
        findings.append(
            Finding(
                WARNING,
                "fp-literal-undef-no-jump-table-context",
                f"{len(symbols)} undefined symbol(s) are reached from "
                "`.text` through `$at` the way a per-use-site FP literal "
                "pool is (`lwc1`/`ldc1 %lo(sym)($at)`), but no jump table "
                "was found in `.rodata` to check the boundary against -- "
                "audit `.rodata`'s scope by hand or supply --rom to check "
                "the bytes directly",
                common,
            )
        )
    elif evidence.bytes_after_table == 0 and not evidence.table_shape_confirmed:
        # Same coincidence, without the shape the defect requires. The most
        # common producer of it is a `const` array of function pointers that
        # ends `.rodata`: it relocates into `.text` exactly like a jump table
        # and is not one. Say what was and was not established, and leave the
        # verdict at `warnings` so a healthy object is not condemned.
        shape = (
            f"the relocated words are not contiguous 4-byte slots "
            f"({len(evidence.jump_table_offsets)} of them between "
            f"{evidence.table_start} and {evidence.table_end})"
            if not evidence.table_contiguous
            else f"the run starts at .rodata+{evidence.table_start}, not at "
            "the section's start"
        )
        findings.append(
            Finding(
                WARNING,
                "rodata-ends-at-text-relocated-words",
                f"`.rodata` ends exactly where its `.text`-relocated words do, "
                f"while {len(symbols)} undefined symbol(s) are loaded through "
                f"`$at` -- but {shape}, so this is not the jump table the "
                "cef4c truncation defect needs. A `const` array of function "
                "pointers at the end of `.rodata` has exactly this shape and "
                "is healthy. Read the words before treating the section as "
                "truncated; see docs/target-audit.md",
                common,
            )
        )
    elif evidence.bytes_after_table == 0:
        findings.append(
            Finding(
                DEFECT,
                "literal-pool-truncated-at-jump-table",
                f"`.rodata` ends exactly at the jump table's own end "
                f"({evidence.table_end} bytes), with zero bytes left over, "
                f"while {len(symbols)} undefined symbol(s) are loaded "
                "through `$at` the way a per-use-site FP literal pool is -- "
                "this is the cef4c defect: a function-owned literal pool "
                "that used to sit right after the jump table was "
                "externalized and the section truncated to hide it. See "
                "docs/target-audit.md",
                common,
            )
        )
    else:
        findings.append(
            Finding(
                INFO,
                "literal-pool-present",
                f"`.rodata` carries {evidence.bytes_after_table} byte(s) "
                f"past the jump table's end ({evidence.table_end}); "
                f"{len(symbols)} undefined symbol(s) are still loaded "
                "through `$at`, but the section is not truncated at the "
                "table boundary",
                common,
            )
        )
    return findings


def _rom_cross_check(
    *,
    rom: str | Path,
    rom_offset: int,
    va: int,
    rodata_size: int,
    undef_fp_symbol_count: int,
    evaluate: bool,
) -> tuple[dict[str, Any], Finding | None]:
    """Read ROM bytes just past the object's own extracted `.rodata` extent.

    ``rom_offset``/``va`` name the same location: the *start* of this
    object's own `.rodata` in the ROM image. That is what lets a caller
    supply one pair (found once, from a splat symbol or a linker map) and
    have every other position -- "just past the extracted extent" -- derived
    from the object's own section size rather than typed in by hand.

    ``evaluate`` gates whether a repeated-word match/mismatch is worth a
    finding at all. It is only true when `_literal_pool_findings` already
    flagged the object as truncated at its jump table boundary -- when it
    has *not*, the extracted `.rodata` already ends past the table (the
    healthy shape), and the bytes "just past" it are ordinary, unrelated
    ROM content (the next symbol's data) that was never expected to repeat.
    Scoring that as a mismatch produced a false `warning` on the corrected
    cef4c object during this module's own validation run: its `.rodata`
    already carries the pool, so 20 bytes further on is simply where the
    next datum starts. The raw words are still read and reported either
    way -- only the interpretive verdict is conditional.

    Strictly read-only: this opens the ROM file, reads one bounded byte
    range, and closes it. It is never parsed as a ROM image, decompressed,
    loaded, or executed.
    """

    path = Path(rom)
    size = path.stat().st_size
    past_offset = rom_offset + rodata_size
    window = min(
        ROM_READ_MAX_BYTES,
        max(ROM_READ_MIN_BYTES, 4 * max(undef_fp_symbol_count, 1)),
    )
    result: dict[str, Any] = {
        "rom": str(path),
        "rodata_extent_rom_offset": rom_offset,
        "rodata_extent_va": va,
        "checked_rom_offset": past_offset,
        "checked_va": va + rodata_size,
        "window_bytes": window,
    }
    if past_offset < 0 or past_offset + window > size:
        result["words"] = []
        return result, Finding(
            DEFECT,
            "rom-read-out-of-range",
            f"the requested ROM window (offset {past_offset:#x}, "
            f"{window} bytes) does not fit inside {path} ({size} bytes)",
            {"rom": str(path), "offset": past_offset, "window": window, "size": size},
        )

    with open(path, "rb") as handle:
        handle.seek(past_offset)
        chunk = handle.read(window)

    words = [
        struct.unpack_from(">I", chunk, index)[0]
        for index in range(0, len(chunk) - 3, 4)
    ]
    result["words"] = [f"0x{value:08x}" for value in words]

    if not words or undef_fp_symbol_count == 0:
        return result, None

    counts = Counter(words)
    top_value, top_count = counts.most_common(1)[0]
    result["most_common_word"] = f"0x{top_value:08x}"
    result["most_common_count"] = top_count
    result["matches_undef_fp_symbol_count"] = top_count == undef_fp_symbol_count

    if not evaluate:
        return result, None

    if top_count == undef_fp_symbol_count and top_count >= 2:
        finding = Finding(
            INFO,
            "rom-confirms-literal-pool",
            f"ROM bytes immediately past the extracted `.rodata` extent "
            f"repeat 0x{top_value:08x} exactly {top_count} time(s) -- "
            f"matching the {undef_fp_symbol_count} undefined symbol(s) "
            "`.text` loads through `$at`. The pool belongs to this "
            "function",
            result,
        )
    else:
        finding = Finding(
            WARNING,
            "rom-does-not-confirm-literal-pool",
            "ROM bytes immediately past the extracted `.rodata` extent do "
            f"not show a value repeated {undef_fp_symbol_count} time(s) "
            "(one per undefined `$at`-loaded symbol) -- inspect `words` "
            "before trusting the truncation finding either way",
            result,
        )
    return result, finding


def audit_target(
    path: str | Path,
    *,
    rom: str | Path | None = None,
    rom_offset: int | None = None,
    va: int | None = None,
) -> TargetAudit:
    """Audit one target/candidate object's ELF scope, statically.

    ``rom``/``rom_offset``/``va`` are optional and go together: supplying
    one without the other two is refused (`ValueError`) rather than
    silently skipping the cross-check. ``rom_offset`` and ``va`` both name
    the *start of this object's own extracted `.rodata`* -- the file offset
    and the run-time address of the same byte -- so the check can derive
    "just past the extent" from the object's own `.rodata` size.
    """

    supplied = (rom is not None, rom_offset is not None, va is not None)
    if any(supplied) and not all(supplied):
        raise ValueError(
            "--rom, --rom-offset, and --va must be supplied together, or not at all"
        )

    elf = read_elf(path)
    findings: list[Finding] = list(_sanity_findings(elf))
    evidence = _pool_evidence(elf)
    if evidence.out_of_range_offsets:
        findings.append(
            Finding(
                DEFECT,
                "rodata-relocation-out-of-range",
                f"{len(evidence.out_of_range_offsets)} relocation(s) into "
                "`.text` name a `.rodata` offset that does not fit inside "
                f"`.rodata`'s own {evidence.rodata_size} bytes",
                {
                    "offsets": list(evidence.out_of_range_offsets),
                    "rodata_size": evidence.rodata_size,
                },
            )
        )
    findings.extend(_literal_pool_findings(evidence))

    text_section = elf.section(".text")
    data_section = elf.section(".data")
    bss_section = elf.section(".bss")
    rodata_section = elf.section(".rodata")

    def _addends(values: list[int | None]) -> list[int | None]:
        return sorted(values, key=lambda item: (item is None, item))

    data_scope: dict[str, Any] = {
        "text_size": text_section.size if text_section is not None else 0,
        "rodata_size": evidence.rodata_size,
        "data_size": data_section.size if data_section is not None else 0,
        "bss_size": bss_section.size if bss_section is not None else 0,
        "rodata_present": rodata_section is not None,
        "jump_table_words": len(evidence.jump_table_offsets),
        "jump_table_start": evidence.table_start,
        "jump_table_end": evidence.table_end,
        "jump_table_contiguous": evidence.table_contiguous,
        "bytes_after_jump_table": evidence.bytes_after_table,
        "rodata_relocations_out_of_range": list(evidence.out_of_range_offsets),
        "undef_data_symbol_count": len(evidence.undef_hilo_symbols),
        "undef_data_symbols": {
            name: _addends(values)
            for name, values in sorted(evidence.undef_hilo_symbols.items())
        },
    }

    rom_check: dict[str, Any] | None = None
    if rom is not None:
        assert rom_offset is not None and va is not None  # `supplied` above
        undef_fp_symbol_count = len({site["symbol"] for site in evidence.fp_pool_sites})
        truncated = evidence.truncated_at_table
        try:
            rom_check, rom_finding = _rom_cross_check(
                rom=rom,
                rom_offset=rom_offset,
                va=va,
                rodata_size=evidence.rodata_size,
                undef_fp_symbol_count=undef_fp_symbol_count,
                evaluate=truncated,
            )
        except OSError as error:
            rom_finding = Finding(
                DEFECT, "rom-read-failed", f"could not read {rom}: {error}", {}
            )
            rom_check = {"rom": str(rom), "error": str(error)}
        if rom_finding is not None:
            findings.append(rom_finding)

    findings.sort(key=lambda item: (_SEVERITY_ORDER[item.severity], item.code))
    if any(item.severity == DEFECT for item in findings):
        verdict = "defects"
    elif any(item.severity == WARNING for item in findings):
        verdict = "warnings"
    else:
        verdict = "ok"

    return TargetAudit(
        path=str(path),
        verdict=verdict,
        findings=tuple(findings),
        data_scope=data_scope,
        rom_check=rom_check,
    )


def target_audit_lines(audit: TargetAudit) -> list[str]:
    """Render a `TargetAudit` as human-readable lines, in verdict order."""

    lines = [
        f"target audit: {audit.path}",
        f"verdict: {audit.verdict.upper()} "
        f"({audit.defects} defect(s), {audit.warnings} warning(s))",
        "",
        "data scope:",
        f"  .text   {audit.data_scope['text_size']:>8} bytes",
        f"  .rodata {audit.data_scope['rodata_size']:>8} bytes"
        + ("" if audit.data_scope["rodata_present"] else "  (section absent)"),
        f"  .data   {audit.data_scope['data_size']:>8} bytes",
        f"  .bss    {audit.data_scope['bss_size']:>8} bytes",
    ]
    if audit.data_scope["jump_table_words"]:
        shape = "" if audit.data_scope["jump_table_contiguous"] else " (not contiguous)"
        lines.append(
            f"  .text-relocated words: {audit.data_scope['jump_table_words']}, "
            f".rodata+{audit.data_scope['jump_table_start']}.."
            f"{audit.data_scope['jump_table_end']}{shape}, "
            f"{audit.data_scope['bytes_after_jump_table']} byte(s) follow them"
        )
    if audit.data_scope["undef_data_symbol_count"]:
        lines.append(
            f"  undefined data symbols reached via %hi/%lo: "
            f"{audit.data_scope['undef_data_symbol_count']}"
        )
        for name, addends in audit.data_scope["undef_data_symbols"].items():
            lines.append(f"    {name}: addends {addends}")

    if audit.rom_check is not None:
        lines.append("")
        lines.append("rom cross-check:")
        for key in (
            "rom",
            "checked_rom_offset",
            "checked_va",
            "words",
            "most_common_word",
            "most_common_count",
            "matches_undef_fp_symbol_count",
            "error",
        ):
            if key in audit.rom_check:
                lines.append(f"  {key}: {audit.rom_check[key]}")

    if audit.findings:
        lines.append("")
        lines.append("findings:")
        for item in audit.findings:
            lines.append(f"  [{item.severity.upper()}] {item.code}: {item.message}")
    else:
        lines.append("")
        lines.append("findings: none")

    return lines
