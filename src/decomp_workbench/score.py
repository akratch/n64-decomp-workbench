"""Score one candidate function's bytes against ROM or object ground truth.

During a late-stage campaign the operator does not need a structural verdict;
they need one number -- did these exact bytes stop differing -- computed the
same way every time. The hand-rolled version of this (objcopy the candidate's
``.text``, window out one function, compare word-for-word against retail ROM
bytes at a known offset, mask relocation words from ``objdump -r``, count
differences) was rewritten by hand roughly ten times during the SSB64
drawbitmap campaign, and it broke twice:

* a hardcoded function offset went stale when the translation unit changed
  and silently scored garbage against the wrong bytes;
* IDO strips local (``static``) function symbols from the object's symbol
  table, so a symbol lookup for one of those functions returned nothing and a
  downstream tool reported the whole file 100% different.

:func:`score_report` is the one code path both the ``score`` command and the
``matrix`` command call, so the bug fixed here stays fixed everywhere it
matters. Windowing goes through the symbol table (:func:`window_by_symbol`)
or, when IDO has stripped the symbol, through the visible neighbours on
either side of it (:func:`window_between`) -- never a hardcoded offset.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .model import Instruction, display_path
from .objdump import dump_object

#: Printed and returned whenever `--between` is the active windowing mode, so
#: a reader who has never hit the stripped-symbol problem still learns why the
#: option exists instead of just that it does.
BETWEEN_RATIONALE = (
    "IDO strips local (static) function symbols from the object's symbol "
    "table, so --function cannot find them; --between locates the bytes "
    "between two surrounding symbols IDO did keep."
)

#: One relocation-kind hex address label, as GNU objdump prints it in a
#: whole-section disassembly: ``00000038 <name>:``.
_LABEL_ADDRESS_RE = re.compile(r"^(?P<addr>[0-9a-fA-F]+)\s+<(?P<name>[^>]+)>:\s*$")


class ScoreError(ValueError):
    """A scoring input could not be resolved.

    Every message names the fix: which flag to add, which symbol to check, or
    which file to inspect. Raised in place of a bare ``RuntimeError`` so a
    caller can catch scoring-specific problems without also swallowing
    genuine programming errors.
    """


def label_addresses(text: str) -> dict[str, int]:
    """Return every ``<name>:`` label in a whole-section dump, with its address."""

    result: dict[str, int] = {}
    for line in text.splitlines():
        match = _LABEL_ADDRESS_RE.match(line)
        if match:
            result[match.group("name")] = int(match.group("addr"), 16)
    return result


@dataclass(frozen=True)
class Window:
    """One windowed region of instructions selected for scoring."""

    label: str
    instructions: tuple[Instruction, ...]
    mode: str
    #: Populated only for `--between`; explains why the mode exists.
    note: str | None = None

    @property
    def words(self) -> list[str]:
        return [item.word for item in self.instructions]

    @property
    def size(self) -> int:
        """Byte length of the window (four bytes per instruction word)."""

        return len(self.instructions) * 4


def window_by_symbol(
    path: str | Path,
    *,
    objdump: str | None,
    symbol: str,
    section: str = ".text",
    label: str | None = None,
) -> Window:
    """Window one function's instructions by its symbol-table entry."""

    try:
        _, instructions = dump_object(
            path, objdump=objdump, symbol=symbol, section=section
        )
    except RuntimeError as error:
        raise ScoreError(
            f"{error}\n"
            f"  If {symbol!r} is a local/static function, IDO may have stripped "
            "its symbol from the table -- try --between with the two symbols "
            "that surround it."
        ) from error
    return Window(
        label=label or symbol, instructions=tuple(instructions), mode="function"
    )


def window_between(
    path: str | Path,
    *,
    objdump: str | None,
    start_symbol: str,
    end_symbol: str,
    section: str = ".text",
    label: str | None = None,
) -> Window:
    """Window the bytes between the end of one symbol and the start of another.

    See :data:`BETWEEN_RATIONALE`: this exists for functions IDO stripped from
    the symbol table, bracketed by two symbols it kept.
    """

    text, instructions = dump_object(
        path, objdump=objdump, symbol=None, section=section
    )
    addresses = label_addresses(text)
    if end_symbol not in addresses:
        defined = ", ".join(sorted(addresses)) or "no symbols"
        raise ScoreError(
            f"--between end symbol {end_symbol!r} was not found in "
            f"{display_path(path)}; it defines: {defined}"
        )
    try:
        _, start_instructions = dump_object(
            path, objdump=objdump, symbol=start_symbol, section=section
        )
    except RuntimeError as error:
        raise ScoreError(
            f"--between start symbol {start_symbol!r} could not be disassembled "
            f"in {display_path(path)}: {error}"
        ) from error
    if not start_instructions:
        raise ScoreError(
            f"--between start symbol {start_symbol!r} produced no instructions "
            f"in {display_path(path)}"
        )
    start_address = start_instructions[-1].address + 4
    end_address = addresses[end_symbol]
    if end_address <= start_address:
        raise ScoreError(
            f"--between {start_symbol},{end_symbol} is empty or reversed in "
            f"{display_path(path)} (end 0x{end_address:x} <= start "
            f"0x{start_address:x}); check the symbol order and that both "
            "symbols belong to the same section"
        )
    windowed = tuple(
        item for item in instructions if start_address <= item.address < end_address
    )
    if not windowed:
        raise ScoreError(
            f"--between {start_symbol},{end_symbol} covered no instructions in "
            f"{display_path(path)}"
        )
    return Window(
        label=label or f"{start_symbol}..{end_symbol}",
        instructions=windowed,
        mode="between",
        note=BETWEEN_RATIONALE,
    )


def read_rom_window(path: str | Path, *, offset: int, size: int) -> bytes:
    """Read `size` raw bytes at `offset` from a local ROM/binary file."""

    file_path = Path(path)
    if not file_path.is_file():
        raise ScoreError(
            f"ROM file does not exist: {display_path(file_path)} "
            "(check --rom)"
        )
    if offset < 0:
        raise ScoreError(f"--rom-offset must not be negative: {offset:#x}")
    if size <= 0:
        raise ScoreError(f"--size must be positive: {size}")
    data = file_path.read_bytes()
    if offset >= len(data):
        raise ScoreError(
            f"--rom-offset {offset:#x} is past the end of "
            f"{display_path(file_path)} ({len(data)} byte(s)); check the "
            "offset and that this is the right ROM revision"
        )
    end = offset + size
    if end > len(data):
        raise ScoreError(
            f"--rom-offset {offset:#x} + size {size} reaches past the end of "
            f"{display_path(file_path)} ({len(data)} byte(s)); the ROM may be "
            "the wrong revision, or the offset/size is wrong"
        )
    window = data[offset:end]
    if len(window) % 4:
        raise ScoreError(
            f"ROM window at {offset:#x} is {len(window)} byte(s), which is not "
            "a multiple of 4; check --size"
        )
    return window


def words_from_bytes(data: bytes) -> list[str]:
    """Split raw big-endian bytes into 32-bit hex words."""

    return [data[index : index + 4].hex() for index in range(0, len(data), 4)]


@dataclass(frozen=True)
class WordScore:
    """Word-for-word score for one window against one target byte range."""

    label: str
    mode: str
    note: str | None
    candidate_size: int
    target_size: int
    diff_words: int
    relocation_floor: int
    diff_positions: tuple[int, ...]
    candidate_sha256: str
    matched: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "mode": self.mode,
            "note": self.note,
            "candidate_size": self.candidate_size,
            "target_size": self.target_size,
            "diff_words": self.diff_words,
            "relocation_floor": self.relocation_floor,
            "diff_positions": list(self.diff_positions),
            "candidate_sha256": self.candidate_sha256,
            "matched": self.matched,
        }

    @property
    def summary(self) -> str:
        """``size A/B, diff words N (+R relocation-floor word(s))``."""

        plural = "" if self.relocation_floor == 1 else "s"
        return (
            f"size {self.candidate_size}/{self.target_size}, diff words "
            f"{self.diff_words} (+{self.relocation_floor} relocation-floor "
            f"word{plural})"
        )


def score_window(window: Window, target_words: list[str]) -> WordScore:
    """Score one candidate window against target words, masking reloc words.

    A word at a relocation offset is counted only in the relocation floor,
    never as a real diff: the linker, not the compiler, owns that field.
    """

    candidate_words = window.words
    reloc_offsets = {
        index for index, item in enumerate(window.instructions) if item.relocations
    }
    total = max(len(candidate_words), len(target_words))
    diff = 0
    floor = 0
    positions: list[int] = []
    for index in range(total):
        candidate_word = (
            candidate_words[index] if index < len(candidate_words) else None
        )
        target_word = target_words[index] if index < len(target_words) else None
        if (
            index in reloc_offsets
            and candidate_word is not None
            and target_word is not None
        ):
            floor += 1
            continue
        if candidate_word != target_word:
            diff += 1
            positions.append(index)
    candidate_sha256 = hashlib.sha256(
        "".join(candidate_words).encode("ascii")
    ).hexdigest()
    return WordScore(
        label=window.label,
        mode=window.mode,
        note=window.note,
        candidate_size=len(candidate_words) * 4,
        target_size=len(target_words) * 4,
        diff_words=diff,
        relocation_floor=floor,
        diff_positions=tuple(positions),
        candidate_sha256=candidate_sha256,
        matched=diff == 0,
    )


#: One control specification: a known-good function checked the same way as
#: the function under test, so a lever that quietly breaks it is caught.
@dataclass(frozen=True)
class ControlSpec:
    name: str
    offset: int | None = None
    size: int | None = None


_CONTROL_RE = re.compile(
    r"^(?P<name>[^@]+?)(?:@(?P<offset>0[xX][0-9a-fA-F]+|\d+)(?::(?P<size>\d+))?)?$"
)


def parse_control_spec(text: str) -> ControlSpec:
    """Parse ``NAME``, ``NAME@0xOFFSET``, or ``NAME@0xOFFSET:SIZE``."""

    match = _CONTROL_RE.match(text.strip())
    if not match or not match.group("name"):
        raise ScoreError(
            f"invalid --control {text!r}; expected NAME, NAME@0xOFFSET, or "
            "NAME@0xOFFSET:SIZE"
        )
    offset = int(match.group("offset"), 0) if match.group("offset") else None
    size = int(match.group("size")) if match.group("size") else None
    return ControlSpec(name=match.group("name"), offset=offset, size=size)


@dataclass(frozen=True)
class TargetSpec:
    """Where target bytes come from: a raw ROM window, or a target object."""

    kind: str  # "rom" or "object"
    rom: str | None = None
    rom_offset: int | None = None
    size: int | None = None
    target_object: str | None = None


@dataclass(frozen=True)
class ScoreSpec:
    """Everything needed to score one candidate object, minus its own path."""

    target: TargetSpec
    function: str | None
    between: tuple[str, str] | None
    controls: tuple[ControlSpec, ...] = ()
    objdump: str | None = None
    section: str = ".text"


def score_spec_from_dict(data: dict[str, Any]) -> ScoreSpec:
    """Build a `ScoreSpec` from a `matrix` JSON spec's ``"score"`` object."""

    function = data.get("function")
    between_raw = data.get("between")
    between: tuple[str, str] | None = None
    if between_raw is not None:
        if not (isinstance(between_raw, list) and len(between_raw) == 2):
            raise ScoreError(
                "'between' in the matrix spec must be a two-item array "
                "[start_symbol, end_symbol]"
            )
        between = (str(between_raw[0]), str(between_raw[1]))
    if bool(function) == bool(between):
        raise ScoreError(
            "the matrix spec's 'score' object needs exactly one of 'function' "
            "or 'between'"
        )
    target_object = data.get("target_object")
    rom = data.get("rom")
    if bool(target_object) == bool(rom):
        raise ScoreError(
            "the matrix spec's 'score' object needs exactly one of "
            "'target_object' or 'rom'"
        )
    if rom:
        rom_offset_raw = data.get("rom_offset")
        if rom_offset_raw is None:
            raise ScoreError("'rom' in the matrix spec requires 'rom_offset'")
        rom_offset = (
            rom_offset_raw
            if isinstance(rom_offset_raw, int)
            else int(str(rom_offset_raw), 0)
        )
        size = data.get("size")
        target = TargetSpec(kind="rom", rom=str(rom), rom_offset=rom_offset, size=size)
    else:
        target = TargetSpec(kind="object", target_object=str(target_object))
    controls = tuple(
        parse_control_spec(str(item)) for item in data.get("controls", [])
    )
    return ScoreSpec(
        target=target,
        function=str(function) if function else None,
        between=between,
        controls=controls,
        objdump=data.get("objdump"),
        section=data.get("section", ".text"),
    )


@dataclass(frozen=True)
class ScoreReport:
    """Full scoring result: the function under test plus every control."""

    candidate: str
    target_description: str
    function: WordScore
    controls: tuple[WordScore, ...]
    controls_broken: bool
    matched: bool
    guidance: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate,
            "target": self.target_description,
            "function": self.function.as_dict(),
            "controls": [item.as_dict() for item in self.controls],
            "controls_broken": self.controls_broken,
            "matched": self.matched,
            "guidance": self.guidance,
        }


def resolve_candidate_window(candidate_path: str | Path, spec: ScoreSpec) -> Window:
    """Window the function under test out of the candidate object."""

    if spec.function:
        return window_by_symbol(
            candidate_path,
            objdump=spec.objdump,
            symbol=spec.function,
            section=spec.section,
        )
    if spec.between is None:
        raise ScoreError("score spec needs exactly one of --function or --between")
    start, end = spec.between
    return window_between(
        candidate_path,
        objdump=spec.objdump,
        start_symbol=start,
        end_symbol=end,
        section=spec.section,
    )


def _resolve_target_words(
    spec: ScoreSpec, window: Window
) -> tuple[list[str], str]:
    """Return target words plus a human description of where they came from."""

    if spec.target.kind == "rom":
        if not spec.target.rom or spec.target.rom_offset is None:
            raise ScoreError("--rom requires --rom-offset")
        size = spec.target.size or window.size
        data = read_rom_window(
            spec.target.rom, offset=spec.target.rom_offset, size=size
        )
        description = (
            f"--rom {display_path(spec.target.rom)} offset "
            f"{spec.target.rom_offset:#x} size {size}"
        )
        return words_from_bytes(data), description
    target_object = spec.target.target_object
    if not target_object:
        raise ScoreError("--target-object is required when --rom is not given")
    if spec.function:
        target_window = window_by_symbol(
            target_object,
            objdump=spec.objdump,
            symbol=spec.function,
            section=spec.section,
        )
    else:
        assert spec.between is not None
        start, end = spec.between
        target_window = window_between(
            target_object,
            objdump=spec.objdump,
            start_symbol=start,
            end_symbol=end,
            section=spec.section,
        )
    description = (
        f"--target-object {display_path(target_object)} ({target_window.label})"
    )
    return target_window.words, description


def _resolve_control_target_words(
    spec: ScoreSpec, control: ControlSpec, control_window: Window
) -> list[str]:
    if spec.target.kind == "rom":
        if control.offset is None:
            raise ScoreError(
                f"--control {control.name} needs @OFFSET when scoring against "
                f"--rom (for example --control {control.name}@0x1000)"
            )
        if not spec.target.rom:
            raise ScoreError("--rom requires a path")
        size = control.size or control_window.size
        data = read_rom_window(spec.target.rom, offset=control.offset, size=size)
        return words_from_bytes(data)
    if control.offset is not None:
        raise ScoreError(
            f"--control {control.name}@{control.offset:#x} must not include an "
            "offset when scoring against --target-object; pass the bare symbol "
            f"name instead (--control {control.name})"
        )
    target_object = spec.target.target_object
    if not target_object:
        raise ScoreError("--target-object is required when --rom is not given")
    target_window = window_by_symbol(
        target_object, objdump=spec.objdump, symbol=control.name, section=spec.section
    )
    return target_window.words


def build_guidance(
    *,
    matched: bool,
    function_score: WordScore,
    controls_broken: bool,
    target: TargetSpec,
    function_label: str,
) -> list[str]:
    """Return the ``next:`` guidance lines for one score report."""

    lines: list[str] = []
    if controls_broken:
        lines.append(
            "CONTROLS BROKEN: a control function that used to match no longer "
            "does. Your lever changed something it must not touch -- revert it "
            "and narrow the change before trusting the function score below."
        )
    if matched:
        lines.append(
            "Diff words are zero outside the relocation floor and every "
            "control is clean. Run the project's normal link/ROM verification "
            "for the final proof."
        )
        return lines
    if not function_score.diff_words:
        # The function under test already matches; only a control broke, and
        # the CONTROLS BROKEN line above already says what to do about that.
        # Nothing here should imply the function itself still has diffs.
        return lines
    if target.kind == "object" and target.target_object:
        lines.append(
            "Run `decomp-workbench diagnose "
            f"{display_path(target.target_object)} <candidate.o> --function "
            f"{function_label}` for full mechanism classification of the "
            "remaining diff words."
        )
    else:
        lines.append(
            "The target came from raw ROM bytes, so `diagnose` needs a "
            "comparable target object to run against; export one, or run "
            "`decomp-workbench guide <verdict>` for lever guidance on the "
            "remaining diff words."
        )
    return lines


def score_report(candidate_path: str | Path, spec: ScoreSpec) -> ScoreReport:
    """Score one candidate object's function, plus every declared control."""

    candidate_display = display_path(candidate_path)
    if not Path(candidate_path).is_file():
        raise ScoreError(f"candidate object does not exist: {candidate_display}")
    window = resolve_candidate_window(candidate_path, spec)
    target_words, target_description = _resolve_target_words(spec, window)
    function_score = score_window(window, target_words)
    control_scores: list[WordScore] = []
    for control in spec.controls:
        control_window = window_by_symbol(
            candidate_path,
            objdump=spec.objdump,
            symbol=control.name,
            section=spec.section,
        )
        control_target_words = _resolve_control_target_words(
            spec, control, control_window
        )
        control_scores.append(score_window(control_window, control_target_words))
    controls_broken = any(not item.matched for item in control_scores)
    matched = function_score.matched and not controls_broken
    guidance = build_guidance(
        matched=matched,
        function_score=function_score,
        controls_broken=controls_broken,
        target=spec.target,
        function_label=window.label,
    )
    return ScoreReport(
        candidate=candidate_display,
        target_description=target_description,
        function=function_score,
        controls=tuple(control_scores),
        controls_broken=controls_broken,
        matched=matched,
        guidance=guidance,
    )
