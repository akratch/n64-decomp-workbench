"""One way to read an object's rows, with the padding rule applied once.

``align`` and ``phase`` both count rows, and a row number is only meaningful if
both commands mean the same thing by it. Two decisions are made here so they
cannot drift apart:

* **Rows are trimmed of `.text` alignment padding.** The linker pads a section
  to a 16-byte boundary, and GNU objdump's ``-z`` mode (which the workbench
  uses, so that a genuine trailing ``nop`` is never lost) prints that padding
  as instructions. Counting it makes two functions of different real length
  report the same row count -- the defect ``true_instruction_count`` already
  fixes for ``compare``. Row *N* here is row *N* of the real function body.
* **Caching is opt-in and explicit.** There is no default cache directory,
  because a scorer with a default reads whatever is in it.
"""

from __future__ import annotations

from pathlib import Path

from .dis_cache import DisassemblyCache
from .model import Instruction
from .objdump import (
    dump_object,
    parse_disassembly,
    symbol_selection_error,
    trim_function_padding,
)

__all__ = ["load_dump_rows", "load_object_rows"]


def load_object_rows(
    path: str | Path,
    *,
    objdump: str | None = None,
    symbol: str | None = None,
    section: str = ".text",
    cache: DisassemblyCache | None = None,
) -> list[Instruction]:
    """Return one object's real instruction rows, padding trimmed."""

    if cache is not None:
        _text, instructions = cache.load(path, symbol=symbol, section=section)
    else:
        _text, instructions = dump_object(
            path, objdump=objdump, symbol=symbol, section=section
        )
    return trim_function_padding(list(instructions))


def load_dump_rows(path: str | Path, *, symbol: str | None = None) -> list[Instruction]:
    """Return rows from retained ``objdump -d -r`` text, padding trimmed."""

    text = Path(path).read_text(encoding="utf-8")
    instructions = parse_disassembly(text, symbol=symbol)
    if not instructions:
        raise ValueError(symbol_selection_error(symbol, inputs=((str(path), text),)))
    return trim_function_padding(list(instructions))
