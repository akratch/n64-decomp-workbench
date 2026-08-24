"""Hand-built minimal IDO phase streams for tests.

Every fixture here is *synthesized* from the record formats the decoders
document: opcode numbers come from the published Ucode enum and record widths
from the same table the parser uses. No stream, object, or fragment of any
game's compilation is used, stored, or needed.
"""

from __future__ import annotations

import struct

from decomp_workbench.ucode import OPCODE_NAMES

#: Ucode record widths, in 32-bit words, for the records these fixtures use.
_UCODE_WIDTHS = {
    "lab": 4,
    "ldef": 4,
    "nop": 2,
    "ret": 2,
    "ujp": 2,
    "fjp": 2,
    "tjp": 2,
    "neq": 2,
}


def uword(*values: int) -> bytes:
    return b"".join(struct.pack(">I", value & 0xFFFFFFFF) for value in values)


def urecord(
    name: str,
    *operands: int,
    dtype: int = 6,
    mtype: int = 3,
    lexlev: int = 0,
) -> bytes:
    """Build one Ucode record with the width its opcode declares."""

    header = (OPCODE_NAMES.index(name) << 24) | (mtype << 21) | (dtype << 16) | lexlev
    words = [header, *operands]
    width = _UCODE_WIDTHS[name]
    if len(words) > width:
        raise ValueError(f"U{name} holds {width} words, got {len(words)}")
    words.extend([0] * (width - len(words)))
    return uword(*words)


def ucode_stream() -> bytes:
    """A five-record Ucode stream with two labels and one jump."""

    return b"".join(
        (
            urecord("lab", 1, 0, 2),
            urecord("nop"),
            urecord("ujp", 5),
            urecord("lab", 5, 0, 2),
            urecord("ret"),
        )
    )


def binasm_record(*words: int) -> bytes:
    return struct.pack(">IIII", *words)


def binasm_stream() -> bytes:
    """A five-record Binasm stream covering header, code, and a label."""

    return b"".join(
        (
            binasm_record(0, 0x002A0000, 7, 0xA),
            binasm_record(0, 0x00150000, 0, 0),
            binasm_record(0, 0x001C0000, 28, 85),
            binasm_record(0, 0x00170062, 0x040D4000, 0),
            binasm_record(0xFFFFFFDB, 0, 0, 0),
        )
    )
