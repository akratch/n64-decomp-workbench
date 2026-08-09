"""What an inserted instruction costs, as opposed to what it shifts.

``compare`` and ``score`` index by position: candidate row *i* is read against
target row *i*. That is the right model for a candidate the compiler emitted at
the target's length, and it is catastrophically wrong for one that is a single
instruction longer. Every row after the insertion is compared with its
neighbour, so an object that is byte-exact apart from one extra ``nop`` reports
a four-figure mismatch count and reads as garbage.

One campaign paid that cost eleven separate times before anyone wrote the
twenty-five lines that fix it, and two more stages independently rediscovered
the same gap. This module is those lines, generalized: align the two
instruction streams with :class:`difflib.SequenceMatcher`, report the edit
script (``replaced``/``inserted``/``deleted``) instead of a positional count,
and hand back the row pairing so a *scorer* can charge the shifted rows to the
rows they really correspond to.

Three properties this module holds that its campaign ancestors did not:

* **Two relocation spaces, never one.** A row whose word the linker fills
  cannot be compared, on either side. The campaign's scorers unioned the
  target's relocation rows with the candidate's into a single set and then
  tested *both* a target row and its shifted candidate counterpart against
  that mixed set, which over-masks near a shift boundary: two genuine
  mismatches were dropped from a published number that way. Here the target
  rows are masked by the target's relocations and the candidate rows by the
  candidate's, and the two sets are never mixed.
* **Branch destinations are renormalized through the pairing.** A local branch
  encodes an absolute row number, so an insertion above it changes the word
  without changing the code. The candidate's destination is mapped back into
  target row space before the two rows are compared, so a shift does not
  manufacture mismatches out of correct branches.
* **The cut list is derived, not supplied.** The banded scorers this replaces
  required a human to read an alignment and pass the insertion points by hand.
  The pairing here comes straight from the edit script, and
  ``insertion_only`` says whether the shift is of the compensable shape at
  all.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .model import Instruction

__all__ = [
    "ALIGNMENT_GRANULARITIES",
    "DEFAULT_GRANULARITY",
    "EditBlock",
    "RowPairing",
    "ShiftDiff",
    "alignment_key",
    "build_shift_diff",
    "comparable_text",
    "relocation_rows",
    "shift_diff_lines",
]

#: How much of an instruction the aligner is allowed to see.
#:
#: ``opcode``
#:     Mnemonics only. Register allocation, immediates and stack offsets are
#:     invisible, so a renamed-but-identically-shaped candidate aligns
#:     one-to-one and the edit script reports only real insertions and
#:     deletions. This is the granularity a *scorer* wants, because a pairing
#:     built at any finer granularity dissolves under a global register
#:     renaming, which is exactly the situation the pairing exists to survive.
#: ``normalized``
#:     Mnemonics plus operand shape, with addresses, immediates and stack
#:     offsets abstracted. Registers still count, so a renaming shows up as
#:     ``replaced`` rather than being folded into the equal runs.
#: ``exact``
#:     The printed assembly, verbatim. Nothing is abstracted; useful only for
#:     asking "which rows are literally identical".
ALIGNMENT_GRANULARITIES = ("opcode", "normalized", "exact")

#: Aligning on mnemonics is the default because the pairing is the product
#: this module exists to hand downstream, and a pairing must survive a
#: renaming to be worth having.
DEFAULT_GRANULARITY = "opcode"

#: A branch destination as the last operand, in either spelling GNU objdump
#: uses: ``bc0 <object_interaction+0xbc0>`` when the section carries a symbol
#: for the address, and a bare ``0xbc0`` when it does not. Objects built from
#: retail bytes commonly have no function symbol at all, so both spellings
#: turn up in one comparison and must reduce to the same row number.
_DESTINATION_RE = re.compile(
    r"(?<=[,\s])(?:0x)?(?P<address>[0-9a-fA-F]+)(?:\s+<[^>]*>)?\s*$"
)

#: Mnemonics whose last operand is a PC-relative destination. Restricting the
#: rewrite to these is what keeps it from mangling ``ori v0,v0,0x1234``, whose
#: last operand is also a hexadecimal literal.
_NON_DESTINATION_OPCODES = frozenset({"break", "jr", "jalr"})


def _has_destination(opcode: str) -> bool:
    return bool(opcode) and opcode[0] in "bj" and opcode not in _NON_DESTINATION_OPCODES


def alignment_key(instruction: Instruction, *, granularity: str) -> str:
    """Return the token the aligner matches this instruction on."""

    if granularity == "opcode":
        return instruction.opcode
    if granularity == "normalized":
        # Imported here rather than at module scope: `compare` reads this
        # module, so a top-level import would close the cycle.
        from .compare import normalize_instruction

        return normalize_instruction(instruction.assembly)
    if granularity == "exact":
        return instruction.assembly
    raise ValueError(
        f"unknown alignment granularity {granularity!r}; expected one of "
        + ", ".join(ALIGNMENT_GRANULARITIES)
    )


def relocation_rows(instructions: Sequence[Instruction]) -> frozenset[int]:
    """Return the row numbers whose words carry a relocation.

    A relocated word's low bits are the linker's, not the compiler's, so the
    row is evidence about nothing until it is linked. Callers hold one of
    these per side and must never merge them: see this module's docstring.
    """

    return frozenset(
        index for index, item in enumerate(instructions) if item.relocations
    )


def comparable_text(
    instruction: Instruction, *, row_of_address: dict[int, int] | None = None
) -> str:
    """Return one instruction's text with its branch destination in row space.

    A local branch's operand is an absolute address. Insert one instruction
    above it and the address moves, so a correct branch reads as a mismatch
    against the target's. ``row_of_address`` maps this side's destination
    addresses to *target* row numbers; with it, the two sides' branches are
    written in the same coordinates and compare equal when they mean the same
    thing.

    Passing ``None`` renders the destination as its own row number, which is
    the right thing for the target side, whose rows already are the reference
    coordinates.
    """

    if not _has_destination(instruction.opcode):
        return instruction.assembly
    match = _DESTINATION_RE.search(instruction.assembly)
    if match is None:
        return instruction.assembly
    address = int(match.group("address"), 16)
    if row_of_address is None:
        destination: int | None = address // 4
    else:
        destination = row_of_address.get(address)
    rendered = "@?" if destination is None else f"@{destination}"
    return instruction.assembly[: match.start()] + rendered


@dataclass(frozen=True)
class EditBlock:
    """One non-equal block of the edit script that turns target into candidate."""

    tag: str
    target_start: int
    target_stop: int
    candidate_start: int
    candidate_stop: int
    target_text: tuple[str, ...] = ()
    candidate_text: tuple[str, ...] = ()

    @property
    def target_rows(self) -> int:
        return self.target_stop - self.target_start

    @property
    def candidate_rows(self) -> int:
        return self.candidate_stop - self.candidate_start

    def as_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "target_start": self.target_start,
            "target_stop": self.target_stop,
            "candidate_start": self.candidate_start,
            "candidate_stop": self.candidate_stop,
            "target_rows": self.target_rows,
            "candidate_rows": self.candidate_rows,
            "target_text": list(self.target_text),
            "candidate_text": list(self.candidate_text),
        }


@dataclass(frozen=True)
class RowPairing:
    """Which candidate row each target row corresponds to.

    ``None`` at a target row means the aligner found no candidate row for it:
    the candidate deleted that instruction. Rows the candidate *added* have no
    target row at all and appear only in the edit script.
    """

    candidate_of_target: tuple[int | None, ...]

    def candidate_row(self, target_row: int) -> int | None:
        if 0 <= target_row < len(self.candidate_of_target):
            return self.candidate_of_target[target_row]
        return None

    @property
    def target_of_candidate(self) -> dict[int, int]:
        """The inverse map, for reading a candidate row in target coordinates."""

        return {
            candidate: target
            for target, candidate in enumerate(self.candidate_of_target)
            if candidate is not None
        }

    @property
    def shift_at_end(self) -> int:
        """How far the last paired candidate row sits from its target row."""

        for target in range(len(self.candidate_of_target) - 1, -1, -1):
            candidate = self.candidate_of_target[target]
            if candidate is not None:
                return candidate - target
        return 0


@dataclass(frozen=True)
class ShiftDiff:
    """The edit script between two instruction streams, plus its residual."""

    target_name: str
    candidate_name: str
    symbol: str | None
    granularity: str
    target_rows: int
    candidate_rows: int
    replaced: int
    inserted: int
    deleted: int
    blocks: tuple[EditBlock, ...]
    paired_rows: int
    paired_mismatches: int
    paired_mismatch_rows: tuple[int, ...]
    relocation_masked: int
    pairing: RowPairing
    #: What a position-indexed comparison would have charged for the same
    #: object. Reported beside :attr:`edit_distance` so the reader can see the
    #: size of the claim the shift-tolerant number replaces.
    positional_mismatches: int

    @property
    def edit_distance(self) -> int:
        """Instructions the aligner had to add, drop, or substitute."""

        return self.replaced + self.inserted + self.deleted

    @property
    def rows_away(self) -> int:
        """The shift-tolerant distance: the edit script plus the residual.

        The number that replaces a positional mismatch count. A candidate that
        is byte-exact apart from one inserted instruction is ``1`` here and
        four figures positionally, and the difference between those two
        readings is the difference between "nearly done" and "start over".
        """

        return self.edit_distance + self.paired_mismatches

    @property
    def insertion_only(self) -> bool:
        """Whether the whole difference is instructions the candidate added.

        The compensable shape. A pure insertion can be scored against the
        target by mapping rows through the pairing; a deletion or a replaced
        block means the two streams disagree about what the instructions
        *are*, and no amount of row mapping recovers that.
        """

        return all(block.tag == "insert" for block in self.blocks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": SHIFT_DIFF_SCHEMA,
            "target": self.target_name,
            "candidate": self.candidate_name,
            "symbol": self.symbol,
            "granularity": self.granularity,
            "target_rows": self.target_rows,
            "candidate_rows": self.candidate_rows,
            "row_delta": self.candidate_rows - self.target_rows,
            "replaced": self.replaced,
            "inserted": self.inserted,
            "deleted": self.deleted,
            "edit_distance": self.edit_distance,
            "rows_away": self.rows_away,
            "insertion_only": self.insertion_only,
            "positional_mismatches": self.positional_mismatches,
            "paired_rows": self.paired_rows,
            "paired_mismatches": self.paired_mismatches,
            "paired_mismatch_rows": list(self.paired_mismatch_rows),
            "relocation_masked": self.relocation_masked,
            "blocks": [block.as_dict() for block in self.blocks],
            "cuts": list(self.cuts),
        }

    @property
    def cuts(self) -> tuple[int, ...]:
        """The target rows at which the candidate inserted an instruction.

        The "cut list" the banded scorers wanted a human to read off an
        alignment and retype. Derived here, so nobody has to.
        """

        return tuple(
            block.target_start
            for block in self.blocks
            if block.tag == "insert"
            for _ in range(block.candidate_rows)
        )


#: JSON identity for :meth:`ShiftDiff.as_dict`, following the same
#: ``<product>-<report>-v<n>`` shape the other machine-readable reports use.
SHIFT_DIFF_SCHEMA = "decomp-workbench-shift-diff-v1"


def _pair_rows(
    opcodes: Sequence[tuple[str, int, int, int, int]],
    *,
    target_rows: int,
) -> RowPairing:
    """Build the target-row to candidate-row map from an edit script."""

    pairing: list[int | None] = [None] * target_rows
    for tag, target_start, target_stop, candidate_start, candidate_stop in opcodes:
        if tag == "insert":
            continue
        # `equal` pairs one-to-one. `replace` pairs positionally as far as the
        # shorter side reaches: those rows really are opposite each other, and
        # saying so is more useful than declaring the whole block unpaired.
        span = min(target_stop - target_start, candidate_stop - candidate_start)
        for offset in range(span):
            pairing[target_start + offset] = candidate_start + offset
    return RowPairing(candidate_of_target=tuple(pairing))


def build_shift_diff(
    target: Sequence[Instruction],
    candidate: Sequence[Instruction],
    *,
    target_name: str = "target",
    candidate_name: str = "candidate",
    symbol: str | None = None,
    granularity: str = DEFAULT_GRANULARITY,
    context: int = 3,
) -> ShiftDiff:
    """Align two instruction streams and report the edit script and residual.

    ``context`` bounds how many instructions of each non-equal block are
    quoted back in the report; the counts are always exact.
    """

    if granularity not in ALIGNMENT_GRANULARITIES:
        raise ValueError(
            f"unknown alignment granularity {granularity!r}; expected one of "
            + ", ".join(ALIGNMENT_GRANULARITIES)
        )
    target_keys = [alignment_key(item, granularity=granularity) for item in target]
    candidate_keys = [
        alignment_key(item, granularity=granularity) for item in candidate
    ]
    matcher = difflib.SequenceMatcher(a=target_keys, b=candidate_keys, autojunk=False)
    opcodes = matcher.get_opcodes()

    replaced = inserted = deleted = 0
    blocks: list[EditBlock] = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        if tag == "insert":
            inserted += j2 - j1
        elif tag == "delete":
            deleted += i2 - i1
        else:
            replaced += max(i2 - i1, j2 - j1)
        blocks.append(
            EditBlock(
                tag=tag,
                target_start=i1,
                target_stop=i2,
                candidate_start=j1,
                candidate_stop=j2,
                target_text=tuple(
                    item.assembly for item in target[i1 : min(i2, i1 + context)]
                ),
                candidate_text=tuple(
                    item.assembly for item in candidate[j1 : min(j2, j1 + context)]
                ),
            )
        )

    pairing = _pair_rows(opcodes, target_rows=len(target))
    target_relocations = relocation_rows(target)
    candidate_relocations = relocation_rows(candidate)
    # One address-to-row table per side, so a branch destination can be read
    # in target coordinates on both. The candidate's goes through the inverse
    # pairing; the target's is the identity.
    inverse = pairing.target_of_candidate
    candidate_rows_in_target_space = {
        item.address: inverse[index]
        for index, item in enumerate(candidate)
        if index in inverse
    }

    paired = 0
    masked = 0
    mismatched: list[int] = []
    for target_row, candidate_row in enumerate(pairing.candidate_of_target):
        if candidate_row is None:
            continue
        paired += 1
        if target_row in target_relocations or candidate_row in candidate_relocations:
            masked += 1
            continue
        left = comparable_text(target[target_row])
        right = comparable_text(
            candidate[candidate_row], row_of_address=candidate_rows_in_target_space
        )
        if left != right:
            mismatched.append(target_row)

    positional = sum(
        1
        for index in range(max(len(target), len(candidate)))
        if (
            index >= len(target)
            or index >= len(candidate)
            or target[index].assembly != candidate[index].assembly
        )
    )

    return ShiftDiff(
        target_name=target_name,
        candidate_name=candidate_name,
        symbol=symbol,
        granularity=granularity,
        target_rows=len(target),
        candidate_rows=len(candidate),
        replaced=replaced,
        inserted=inserted,
        deleted=deleted,
        blocks=tuple(blocks),
        paired_rows=paired,
        paired_mismatches=len(mismatched),
        paired_mismatch_rows=tuple(mismatched),
        relocation_masked=masked,
        pairing=pairing,
        positional_mismatches=positional,
    )


def _block_line(block: EditBlock) -> str:
    target_span = (
        f"{block.target_start}..{block.target_stop - 1}"
        if block.target_rows
        else f"before {block.target_start}"
    )
    candidate_span = (
        f"{block.candidate_start}..{block.candidate_stop - 1}"
        if block.candidate_rows
        else f"before {block.candidate_start}"
    )
    return (
        f"  {block.tag:8s} target {target_span} ({block.target_rows}) "
        f"<- candidate {candidate_span} ({block.candidate_rows})"
    )


def shift_diff_lines(diff: ShiftDiff, *, blocks: int = 20) -> list[str]:
    """Render one shift-tolerant diff for a terminal."""

    delta = diff.candidate_rows - diff.target_rows
    lines = [
        f"shift-tolerant diff: {diff.candidate_name} against {diff.target_name}"
        + (f" ({diff.symbol})" if diff.symbol else ""),
        f"rows: target {diff.target_rows} candidate {diff.candidate_rows} ({delta:+d})",
        f"edit script (aligned on {diff.granularity}): replaced "
        f"{diff.replaced} inserted {diff.inserted} deleted {diff.deleted}",
        f"paired rows: {diff.paired_rows} compared, {diff.paired_mismatches} "
        f"differing, {diff.relocation_masked} masked as linker-controlled",
        f"=> {diff.rows_away} instruction(s) away "
        f"({diff.edit_distance} edit + {diff.paired_mismatches} residual)",
    ]
    if delta and diff.positional_mismatches > diff.rows_away:
        lines.append(
            f"a position-indexed comparison charges {diff.positional_mismatches} "
            f"rows for the same object: the {abs(delta)}-row shift moves every "
            "later row against its neighbour. Read the edit script."
        )
    if diff.blocks:
        lines.append(
            "shift shape: "
            + (
                "insertion-only, so a banded scorer can compensate for it"
                if diff.insertion_only
                else "not insertion-only, so rows inside the replaced or "
                "deleted blocks are genuinely different instructions"
            )
        )
        if diff.cuts:
            lines.append(
                f"cuts (target rows the candidate inserts at): {list(diff.cuts)}"
            )
        lines.append("")
        lines.append("edit script:")
        for block in diff.blocks[:blocks]:
            lines.append(_block_line(block))
            lines.extend(
                f"      target    {block.target_start + offset:5d}  {text}"
                for offset, text in enumerate(block.target_text)
            )
            target_hidden = (block.target_stop - block.target_start) - len(
                block.target_text
            )
            if target_hidden > 0:
                lines.append(
                    f"      target    ... {target_hidden} more row(s) in this "
                    "block; raise --context-rows to quote them"
                )
            lines.extend(
                f"      candidate {block.candidate_start + offset:5d}  {text}"
                for offset, text in enumerate(block.candidate_text)
            )
            candidate_hidden = (block.candidate_stop - block.candidate_start) - len(
                block.candidate_text
            )
            if candidate_hidden > 0:
                lines.append(
                    f"      candidate ... {candidate_hidden} more row(s) in this "
                    "block; raise --context-rows to quote them"
                )
        if len(diff.blocks) > blocks:
            lines.append(
                f"  ... {len(diff.blocks) - blocks} more block(s); raise "
                "--blocks to see them"
            )
    else:
        lines.append("edit script: empty -- the two streams align exactly")
    return lines
