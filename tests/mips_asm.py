"""A tiny MIPS assembler that renders GNU objdump text for test fixtures.

Fixtures must keep the instruction word and the printed assembly consistent:
the aligned view derives its byte-identical-prefix signature from the words and
its classification from the operands, so a fixture with invented words would
silently validate nothing.  Encoding the handful of formats these fixtures use
keeps the two honest, and the output is redistributable synthetic text.
"""

from __future__ import annotations

import re

REGISTERS: dict[str, int] = {
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
    "s8": 30,
    "ra": 31,
}

# funct codes for the special-format instructions the fixtures use
SPECIAL: dict[str, int] = {
    "sll": 0x00,
    "srl": 0x02,
    "sra": 0x03,
    "jr": 0x08,
    "mult": 0x18,
    "multu": 0x19,
    "add": 0x20,
    "addu": 0x21,
    "subu": 0x23,
    "and": 0x24,
    "or": 0x25,
    "xor": 0x26,
    "nor": 0x27,
    "slt": 0x2A,
    "sltu": 0x2B,
}

# primary opcodes for the immediate-format instructions the fixtures use
IMMEDIATE: dict[str, int] = {
    "beq": 0x04,
    "bne": 0x05,
    "blez": 0x06,
    "bgtz": 0x07,
    "addi": 0x08,
    "addiu": 0x09,
    "slti": 0x0A,
    "andi": 0x0C,
    "ori": 0x0D,
    "xori": 0x0E,
    "lui": 0x0F,
    "lb": 0x20,
    "lh": 0x21,
    "lw": 0x23,
    "lbu": 0x24,
    "lhu": 0x25,
    "sb": 0x28,
    "sh": 0x29,
    "sw": 0x2B,
}

MEMORY_RE = re.compile(r"^(-?(?:0x[0-9a-fA-F]+|\d+))\((\w+)\)$")
LABEL_RE = re.compile(r"^@(\d+)$")


class AssemblyError(ValueError):
    """Raised when a fixture uses an unsupported instruction form."""


def _register(name: str) -> int:
    try:
        return REGISTERS[name]
    except KeyError:
        raise AssemblyError(f"unknown register {name!r}") from None


def _immediate(text: str) -> int:
    return int(text, 0) & 0xFFFF


def _encode(mnemonic: str, operands: list[str], index: int) -> int:
    if mnemonic == "nop":
        return 0
    if mnemonic in {"jal", "j"}:
        return (0x03 if mnemonic == "jal" else 0x02) << 26
    if mnemonic == "move":
        return (_register(operands[1]) << 21) | (_register(operands[0]) << 11) | 0x21
    if mnemonic == "li":
        return (0x09 << 26) | (_register(operands[0]) << 16) | _immediate(operands[1])
    if mnemonic in SPECIAL:
        funct = SPECIAL[mnemonic]
        if mnemonic in {"sll", "srl", "sra"}:
            return (
                (_register(operands[1]) << 16)
                | (_register(operands[0]) << 11)
                | ((int(operands[2], 0) & 0x1F) << 6)
                | funct
            )
        if mnemonic == "jr":
            return (_register(operands[0]) << 21) | funct
        if mnemonic in {"mult", "multu"}:
            return (
                (_register(operands[0]) << 21) | (_register(operands[1]) << 16) | funct
            )
        return (
            (_register(operands[1]) << 21)
            | (_register(operands[2]) << 16)
            | (_register(operands[0]) << 11)
            | funct
        )
    if mnemonic in IMMEDIATE:
        opcode = IMMEDIATE[mnemonic]
        if mnemonic == "lui":
            return (
                (opcode << 26)
                | (_register(operands[0]) << 16)
                | _immediate(operands[1])
            )
        if mnemonic in {"beq", "bne"}:
            offset = int(operands[2][1:]) - index - 1
            return (
                (opcode << 26)
                | (_register(operands[0]) << 21)
                | (_register(operands[1]) << 16)
                | (offset & 0xFFFF)
            )
        if mnemonic in {"blez", "bgtz"}:
            offset = int(operands[1][1:]) - index - 1
            return (opcode << 26) | (_register(operands[0]) << 21) | (offset & 0xFFFF)
        memory = MEMORY_RE.match(operands[1])
        if memory:
            return (
                (opcode << 26)
                | (_register(memory.group(2)) << 21)
                | (_register(operands[0]) << 16)
                | _immediate(memory.group(1))
            )
        return (
            (opcode << 26)
            | (_register(operands[1]) << 21)
            | (_register(operands[0]) << 16)
            | _immediate(operands[2])
        )
    raise AssemblyError(f"unsupported mnemonic {mnemonic!r}")


def _display(mnemonic: str, operands: list[str], index: int, symbol: str) -> str:
    if mnemonic == "nop":
        return "nop"
    if mnemonic in {"jal", "j"}:
        return f"{mnemonic} 0 <{operands[0]}>"
    rendered = []
    for operand in operands:
        label = LABEL_RE.match(operand)
        if label:
            address = int(label.group(1)) * 4
            rendered.append(f"{address:x} <{symbol}+0x{address:x}>")
            continue
        memory = MEMORY_RE.match(operand)
        if memory:
            rendered.append(f"{memory.group(1)}(${memory.group(2)})")
            continue
        rendered.append(f"${operand}" if operand in REGISTERS else operand)
    return f"{mnemonic} " + ",".join(rendered)


def assemble(
    lines: list[str], *, symbol: str = "demo", relocations: dict[int, str] | None = None
) -> str:
    """Render GNU objdump ``-d -r`` text for a list of assembly lines.

    Branch destinations are written ``@N`` for instruction index ``N``.  Call
    targets are named symbols and take a relocation entry from ``relocations``.
    """

    relocation_map = relocations or {}
    out = [f"00000000 <{symbol}>:"]
    for index, line in enumerate(lines):
        parts = line.split(maxsplit=1)
        mnemonic = parts[0]
        operands = (
            [item.strip() for item in parts[1].split(",")] if len(parts) > 1 else []
        )
        word = _encode(mnemonic, operands, index)
        address = index * 4
        out.append(
            f"{address:>4x}: {word:08x}  {_display(mnemonic, operands, index, symbol)}"
        )
        kind = relocation_map.get(index)
        if kind:
            out.append(f"{' ' * 24}{address:x}: {kind}")
    return "\n".join(out) + "\n"
