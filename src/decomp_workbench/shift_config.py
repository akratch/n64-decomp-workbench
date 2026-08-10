"""The faithful-cascade gate: does a config change leave the link alone?

Making a project shiftable means editing its linker configuration, and the
one thing that edit must not do is change the build. S6 made pilotwings64
shift-capable with a single yaml line (``follows_vram: kernel`` on the ``app``
segment, ``s6/PW64-SHIFT-CONFIG.md`` §1.5) and then had to prove the claim
before any rehearsal of it meant anything. That proof is Gate 2, and the
doc's own playbook line is the reason this module exists:

    "the identity gate is three checks, not one. A byte-identical *image* can
    coexist with a symbol that moved into a hole; ``nm -n`` diff is what
    closes that. Run all three."

`shift config verify` is those three checks as one command.

**Check 1 -- every shared symbol at an identical address.** The movement
audit :func:`~decomp_workbench.ldmap.audit_symbol_movement` already
generalizes S0's, and a faithful pair is exactly the case where the only
allowed delta is ``0``. This is the check that catches a symbol that moved
into a hole the image's own bytes cannot show.

**Check 2 -- identical placed extents.** Every output section must land at
the same VMA, with the same size and the same ``AT()`` load address. A pair
that agrees on symbols but disagrees on a section's placement is not the same
layout; it is two layouts that happen to share their symbol table.

**Check 3 -- byte-identical images, when both are given.** The cheapest check
and the weakest, in that order. It is optional because a caller comparing two
*maps* out of a config experiment often has no images yet, and asking for
them would push the gate later than it needs to run.

What this command refuses is as important as what it passes. Handing it a
genuinely shifted pair -- S0's DKR ``nm-base`` map against its ``shift-0x10``
relink -- must be loud, not quiet: that pair is a correct, healthy shift, and
"faithful" is simply not the question it answers. The report names the first
divergence of each kind in address order rather than dumping thousands of
rows, because the first one is the one a reader debugs.

Exit status follows the census contract (:mod:`decomp_workbench.census`):
``0`` when the pair is faithful, ``3`` when it is not, ``2`` when the
question could not be asked at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .ldmap import LdMap, OutputSection, audit_symbol_movement

__all__ = [
    "CONFIG_VERIFY_SCHEMA",
    "FAITHFUL_CHECKS",
    "ConfigVerification",
    "FaithfulCheck",
    "SectionDivergence",
    "verify_faithful",
    "verify_lines",
]

#: JSON identity for the report.
CONFIG_VERIFY_SCHEMA = "decomp-workbench-shift-config-v1"

#: The one delta a faithful pair is allowed. Named rather than inlined so the
#: report can print the rule it was judged against: a reader comparing this
#: command with `shift rehearse` (whose allowed set is ``{0, delta}``) can see
#: that the difference between the two commands is one number.
FAITHFUL_DELTAS: frozenset[int] = frozenset({0})


@dataclass(frozen=True)
class FaithfulCheck:
    """One published check, with what it catches that the others do not."""

    name: str
    evidence: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "evidence": self.evidence}


#: S6's Gate 2, as data. Three checks in strength order, and every one of
#: them reports whether it ran -- a check that was skipped because its input
#: was not supplied is not a check that passed.
FAITHFUL_CHECKS: tuple[FaithfulCheck, ...] = (
    FaithfulCheck(
        "symbols",
        "every symbol both maps define is at the same address. The strongest "
        "of the three: a byte-identical image can still coexist with a symbol "
        "that moved into a hole, and only this check sees that",
    ),
    FaithfulCheck(
        "sections",
        "every output section both maps place lands at the same VMA, with the "
        "same size and the same AT() load address. Two layouts can share a "
        "symbol table and still place their sections differently",
    ),
    FaithfulCheck(
        "image",
        "the two linked images are byte-identical. The cheapest check and the "
        "weakest; optional, because a config experiment compares maps before "
        "it has images",
    ),
)


@dataclass(frozen=True)
class SectionDivergence:
    """One output section the two maps did not place identically."""

    name: str
    field: str
    """``"vma"``, ``"size"`` or ``"load_address"`` -- the first of the three
    that differed, in that order."""

    pinned: int | None
    candidate: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "section": self.name,
            "field": self.field,
            "pinned": self.pinned,
            "candidate": self.candidate,
        }


def _section_divergences(
    pinned: Sequence[OutputSection], candidate: Sequence[OutputSection]
) -> tuple[
    tuple[SectionDivergence, ...], tuple[str, ...], tuple[str, ...], int
]:
    """Compare two maps' section placements, in the pinned map's VMA order."""

    by_name = {item.name: item for item in candidate}
    pinned_names = {item.name for item in pinned}
    found: list[SectionDivergence] = []
    shared = 0
    for section in sorted(pinned, key=lambda item: (item.vma, item.name)):
        other = by_name.get(section.name)
        if other is None:
            continue
        shared += 1
        for field in ("vma", "size", "load_address"):
            mine, theirs = getattr(section, field), getattr(other, field)
            if mine != theirs:
                found.append(
                    SectionDivergence(
                        name=section.name,
                        field=field,
                        pinned=mine,
                        candidate=theirs,
                    )
                )
                break
    return (
        tuple(found),
        tuple(sorted(pinned_names - set(by_name))),
        tuple(sorted(set(by_name) - pinned_names)),
        shared,
    )


def _first_difference(pinned: bytes, candidate: bytes) -> int | None:
    """The first byte offset at which two images differ, or ``None``."""

    if pinned == candidate:
        return None
    for offset in range(min(len(pinned), len(candidate))):
        if pinned[offset] != candidate[offset]:
            return offset
    return min(len(pinned), len(candidate))


@dataclass(frozen=True)
class ConfigVerification:
    """One pinned/candidate pair, judged against all three identity checks."""

    pinned_map_path: str | None
    candidate_map_path: str | None
    pinned_image_path: str | None
    candidate_image_path: str | None
    shared_symbols: int
    moved_symbols: tuple[tuple[str, int, int], ...]
    """``(name, pinned address, candidate address)`` for every shared symbol
    the two maps place differently, in the pinned map's address order."""

    symbols_only_in_pinned: tuple[str, ...]
    symbols_only_in_candidate: tuple[str, ...]
    shared_sections: int
    section_divergences: tuple[SectionDivergence, ...]
    sections_only_in_pinned: tuple[str, ...]
    sections_only_in_candidate: tuple[str, ...]
    image_checked: bool
    image_bytes: int | None
    candidate_image_bytes: int | None
    image_first_difference: int | None

    @property
    def symbols_moved(self) -> int:
        return len(self.moved_symbols)

    @property
    def sections_diverged(self) -> int:
        return len(self.section_divergences)

    @property
    def image_identical(self) -> bool | None:
        """``None`` when no image pair was given -- see `FAITHFUL_CHECKS`."""

        if not self.image_checked:
            return None
        return (
            self.image_first_difference is None
            and self.image_bytes == self.candidate_image_bytes
        )

    @property
    def first_moved_symbol(self) -> tuple[str, int, int] | None:
        return self.moved_symbols[0] if self.moved_symbols else None

    @property
    def first_section_divergence(self) -> SectionDivergence | None:
        return self.section_divergences[0] if self.section_divergences else None

    @property
    def differences(self) -> int:
        """Every reason this pair is not faithful, counted once each."""

        return (
            self.symbols_moved
            + len(self.symbols_only_in_pinned)
            + len(self.symbols_only_in_candidate)
            + self.sections_diverged
            + len(self.sections_only_in_pinned)
            + len(self.sections_only_in_candidate)
            + (0 if self.image_identical in (None, True) else 1)
        )

    @property
    def faithful(self) -> bool:
        return self.differences == 0

    def as_dict(self, *, limit: int) -> dict[str, Any]:
        cap = max(0, limit)
        return {
            "schema": CONFIG_VERIFY_SCHEMA,
            "pinned_map": self.pinned_map_path,
            "candidate_map": self.candidate_map_path,
            "pinned_image": self.pinned_image_path,
            "candidate_image": self.candidate_image_path,
            "allowed_deltas": sorted(FAITHFUL_DELTAS),
            "shared_symbols": self.shared_symbols,
            "symbols_moved": self.symbols_moved,
            "symbols_only_in_pinned": len(self.symbols_only_in_pinned),
            "symbols_only_in_candidate": len(self.symbols_only_in_candidate),
            "moved_symbols_shown": len(self.moved_symbols[:cap]),
            "moved_symbols": [
                {"name": name, "pinned": pinned, "candidate": candidate}
                for name, pinned, candidate in self.moved_symbols[:cap]
            ],
            "shared_sections": self.shared_sections,
            "sections_diverged": self.sections_diverged,
            "sections_only_in_pinned": list(self.sections_only_in_pinned[:cap]),
            "sections_only_in_candidate": list(
                self.sections_only_in_candidate[:cap]
            ),
            "section_divergences": [
                item.as_dict() for item in self.section_divergences[:cap]
            ],
            "image_checked": self.image_checked,
            "image_identical": self.image_identical,
            "image_bytes": self.image_bytes,
            "candidate_image_bytes": self.candidate_image_bytes,
            "image_first_difference": self.image_first_difference,
            "differences": self.differences,
            "faithful": self.faithful,
            "faithful_checks": [item.as_dict() for item in FAITHFUL_CHECKS],
            "limit": cap,
        }


def verify_faithful(
    *,
    pinned: LdMap,
    candidate: LdMap,
    pinned_image: bytes | None = None,
    candidate_image: bytes | None = None,
    pinned_image_path: str | None = None,
    candidate_image_path: str | None = None,
) -> ConfigVerification:
    """Run S6's Gate 2 -- all three checks -- over one pair.

    ``pinned`` is the link the project ships today and ``candidate`` is the
    link the config edit produces. The names are not symmetric on purpose:
    the question is whether the candidate reproduces the pinned build, and a
    report that called them "a" and "b" would leave a reader to remember
    which direction a divergence points.

    Naming one image and not the other is refused rather than half-checked --
    the same rule the rehearsal applies to its ELF pair, and for the same
    reason: an identity check that silently did not run is worse than one
    that says it did not.
    """

    if (pinned_image is None) != (candidate_image is None):
        raise ValueError(
            "--pinned-image and --candidate-image go together: byte-identity "
            "is a question about two images, and one of them cannot answer it"
        )

    movement = audit_symbol_movement(
        pinned, candidate, allowed_deltas=FAITHFUL_DELTAS
    )
    moved = tuple(
        (item.name, item.base_address, item.shifted_address)
        for item in movement.anomalies
    )
    divergences, only_pinned, only_candidate, shared_sections = _section_divergences(
        pinned.sections, candidate.sections
    )
    first_difference = (
        _first_difference(pinned_image, candidate_image)
        if pinned_image is not None and candidate_image is not None
        else None
    )
    return ConfigVerification(
        pinned_map_path=pinned.path,
        candidate_map_path=candidate.path,
        pinned_image_path=pinned_image_path,
        candidate_image_path=candidate_image_path,
        shared_symbols=len(movement.movements),
        moved_symbols=moved,
        symbols_only_in_pinned=movement.only_in_base,
        symbols_only_in_candidate=movement.only_in_shifted,
        shared_sections=shared_sections,
        section_divergences=divergences,
        sections_only_in_pinned=only_pinned,
        sections_only_in_candidate=only_candidate,
        image_checked=pinned_image is not None,
        image_bytes=len(pinned_image) if pinned_image is not None else None,
        candidate_image_bytes=(
            len(candidate_image) if candidate_image is not None else None
        ),
        image_first_difference=first_difference,
    )


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    """Render one column-aligned table, the shape the shift family prints."""

    if not rows:
        return [" ".join(header)]
    widths = [
        max(len(header[column]), *(len(row[column]) for row in rows))
        for column in range(len(header))
    ]
    lines = [
        "  ".join(
            header[column].ljust(widths[column]) for column in range(len(header))
        ).rstrip()
    ]
    for row in rows:
        lines.append(
            "  ".join(
                row[column].ljust(widths[column]) for column in range(len(row))
            ).rstrip()
        )
    return lines


def verify_lines(found: ConfigVerification, *, limit: int) -> list[str]:
    """Render the human report: the same numbers `as_dict` carries."""

    image_state = (
        "not-checked"
        if found.image_identical is None
        else "identical"
        if found.image_identical
        else "differs"
    )
    lines = [
        f"shift config verify  pinned={found.pinned_map_path or '-'}  "
        f"candidate={found.candidate_map_path or '-'}",
        "",
        f"faithful={'yes' if found.faithful else 'NO'}  "
        f"differences={found.differences:,}  "
        f"allowed_deltas={sorted(FAITHFUL_DELTAS)}",
        "",
        f"shared_symbols={found.shared_symbols:,}  "
        f"symbols_moved={found.symbols_moved:,}  "
        f"symbols_only_in_pinned={len(found.symbols_only_in_pinned):,}  "
        f"symbols_only_in_candidate={len(found.symbols_only_in_candidate):,}",
        f"shared_sections={found.shared_sections:,}  "
        f"sections_diverged={found.sections_diverged:,}  "
        f"sections_only_in_pinned={len(found.sections_only_in_pinned):,}  "
        f"sections_only_in_candidate={len(found.sections_only_in_candidate):,}",
        f"image={image_state}  "
        f"pinned_image_bytes="
        + ("-" if found.image_bytes is None else f"{found.image_bytes:,}")
        + "  candidate_image_bytes="
        + (
            "-"
            if found.candidate_image_bytes is None
            else f"{found.candidate_image_bytes:,}"
        )
        + "  image_first_difference="
        + (
            "-"
            if found.image_first_difference is None
            else f"0x{found.image_first_difference:06x}"
        ),
    ]

    first_symbol = found.first_moved_symbol
    if first_symbol is not None:
        name, pinned_address, candidate_address = first_symbol
        lines.extend(
            (
                "",
                f"first divergent symbol: {name} "
                f"0x{pinned_address:08x} -> 0x{candidate_address:08x} "
                f"({candidate_address - pinned_address:+#x})",
            )
        )
    first_section = found.first_section_divergence
    if first_section is not None:
        lines.append(
            f"first divergent section: {first_section.name}.{first_section.field} "
            + (
                "-"
                if first_section.pinned is None
                else f"0x{first_section.pinned:x}"
            )
            + " -> "
            + (
                "-"
                if first_section.candidate is None
                else f"0x{first_section.candidate:x}"
            )
        )

    lines.extend(
        (
            "",
            f"moved symbols ({min(found.symbols_moved, max(0, limit))} of "
            f"{found.symbols_moved:,}, --limit)",
        )
    )
    lines.extend(
        _table(
            ("name", "pinned", "candidate", "delta"),
            [
                (
                    name,
                    f"0x{pinned_address:08x}",
                    f"0x{candidate_address:08x}",
                    f"{candidate_address - pinned_address:+#x}",
                )
                for name, pinned_address, candidate_address in found.moved_symbols[
                    : max(0, limit)
                ]
            ],
        )
    )

    lines.extend(
        (
            "",
            f"section divergences ({min(found.sections_diverged, max(0, limit))} "
            f"of {found.sections_diverged:,}, --limit)",
        )
    )
    lines.extend(
        _table(
            ("section", "field", "pinned", "candidate"),
            [
                (
                    item.name,
                    item.field,
                    "-" if item.pinned is None else f"0x{item.pinned:x}",
                    "-" if item.candidate is None else f"0x{item.candidate:x}",
                )
                for item in found.section_divergences[: max(0, limit)]
            ],
        )
    )

    lines.extend(("", "checks"))
    for check in FAITHFUL_CHECKS:
        lines.append(f"  {check.name}: {check.evidence}")
    lines.extend(
        (
            "",
            "a faithful pair is one where a configuration edit changed the "
            "linker script and nothing else -- the gate to pass before "
            "rehearsing any shift; on pilotwings64 it passed byte-exactly on "
            "the first try. A pair that is genuinely shifted fails every one "
            "of these checks by construction: that is `shift rehearse`'s "
            "question, not this one's.",
        )
    )
    return lines
