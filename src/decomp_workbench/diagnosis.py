"""One-pass object loading for combined comparison and mechanism diagnosis."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .compare import compare_instructions, resolve_true_instructions
from .model import Comparison, Instruction, display_path
from .objdump import (
    dump_object,
    parse_selected_disassembly,
    selection_warnings,
    symbol_selection_error,
)
from .view import (
    BASIS_NONE,
    DEFAULT_REGISTER_PROFILE,
    OWNING_PASS_UNKNOWN,
    REACHABILITY_UNKNOWN,
    ROUTING_IMPORT_FIX,
    MechanismView,
    Ownership,
    PassEvidence,
    build_view,
)

#: v2 added `routing` beside the verdict; v3 adds `owning_pass`,
#: `reachability` and `ownership_basis` beside it. Additive at both steps:
#: every v1 key is still present and unchanged, and a consumer that ignores
#: the new fields reads a v3 document exactly as it read a v1 one.
DIAGNOSIS_SCHEMA = "decomp-workbench-diagnosis-v3"


@dataclass(frozen=True)
class Diagnosis:
    """Exact comparison truth and the aligned explanation built from one input."""

    comparison: Comparison
    view: MechanismView

    def as_dict(
        self,
        *,
        report_regs: bool = False,
        cross_rom: bool = False,
    ) -> dict[str, Any]:
        accepted = self.comparison.exact or (
            cross_rom and self.comparison.structural_exact
        )
        basis = (
            "function-exact"
            if self.comparison.exact
            else "cross-rom-structural"
            if cross_rom and self.comparison.structural_exact
            else "mismatch"
        )
        comparison = self.comparison.as_dict()
        comparison.update(accepted=accepted, acceptance_basis=basis)
        return {
            "schema": DIAGNOSIS_SCHEMA,
            "comparison": comparison,
            "routing": self.routing,
            **self.ownership.as_dict(),
            "view": self.view.as_dict(report_regs=report_regs),
        }

    @property
    def routing(self) -> str:
        """Where this residual goes next, over both halves of the evidence.

        The view routes on its own verdict. This adds the one thing the view
        cannot see: a relocation that names a different symbol, or one nothing
        understood, means the candidate is not reading what the target reads.
        That is a question about the inputs -- context, headers, the scratch --
        and neither a source lever nor a search answers it.
        """

        if self._import_fault:
            return ROUTING_IMPORT_FIX
        return self.view.routing

    @property
    def _import_fault(self) -> bool:
        """Whether the two objects were not reading the same things."""

        return bool(
            self.comparison.relocation_symbol_mismatches
            or self.comparison.unknown_relocations
        )

    @property
    def ownership(self) -> Ownership:
        """Which pass owns this residual, over both halves of the evidence.

        The same correction `routing` makes, for the same reason: a candidate
        reading a different symbol has no owning pass to name. Attributing it
        to the colourer would be inventing a decision nobody took.
        """

        if self._import_fault:
            return Ownership(
                OWNING_PASS_UNKNOWN,
                REACHABILITY_UNKNOWN,
                BASIS_NONE,
                "a relocation names a different symbol, or one nothing "
                "understood: the candidate is not reading what the target "
                "reads, so no pass owns this yet",
            )
        return self.view.ownership


def diagnose_instructions(
    target: Sequence[Instruction],
    candidate: Sequence[Instruction],
    *,
    target_name: str,
    candidate_name: str,
    symbol: str | None,
    register_profile: str = DEFAULT_REGISTER_PROFILE,
    warnings: Sequence[str] = (),
    target_true_instructions: int | None = None,
    candidate_true_instructions: int | None = None,
    instruction_count_verified: bool = False,
    evidence: PassEvidence | None = None,
) -> Diagnosis:
    """Build both reports from two already-parsed instruction streams.

    The `target_true_instructions`/`candidate_true_instructions`/
    `instruction_count_verified` triple passes straight through to
    `compare_instructions`; see its docstring.
    """

    target_items = list(target)
    candidate_items = list(candidate)
    comparison = compare_instructions(
        target_items,
        candidate_items,
        target_name=target_name,
        candidate_name=candidate_name,
        symbol=symbol,
        warnings=warnings,
        target_true_instructions=target_true_instructions,
        candidate_true_instructions=candidate_true_instructions,
        instruction_count_verified=instruction_count_verified,
    )
    view = build_view(
        target_items,
        candidate_items,
        target_name=target_name,
        candidate_name=candidate_name,
        symbol=symbol,
        register_profile=register_profile,
        warnings=warnings,
        evidence=evidence,
    )
    return Diagnosis(comparison=comparison, view=view)


def diagnose_objects(
    target: str | Path,
    candidate: str | Path,
    *,
    objdump: str | None = None,
    symbol: str | None = None,
    section: str = ".text",
    register_profile: str = DEFAULT_REGISTER_PROFILE,
) -> Diagnosis:
    """Disassemble each object once, then build both reports in process."""

    target_text, target_items = dump_object(
        target,
        objdump=objdump,
        symbol=symbol,
        section=section,
    )
    candidate_text, candidate_items = dump_object(
        candidate,
        objdump=objdump,
        symbol=symbol,
        section=section,
    )
    warnings = selection_warnings(
        target_text,
        candidate_text,
        symbol=symbol,
        target_name=display_path(target),
        candidate_name=display_path(candidate),
        section=section,
    )
    target_true_instructions = resolve_true_instructions(
        target, symbol=symbol, section=section
    )
    candidate_true_instructions = resolve_true_instructions(
        candidate, symbol=symbol, section=section
    )
    return diagnose_instructions(
        target_items,
        candidate_items,
        target_name=display_path(target),
        candidate_name=display_path(candidate),
        symbol=symbol,
        register_profile=register_profile,
        warnings=warnings,
        target_true_instructions=target_true_instructions,
        candidate_true_instructions=candidate_true_instructions,
        instruction_count_verified=(
            target_true_instructions is not None
            and candidate_true_instructions is not None
        ),
    )


def diagnose_dumps(
    target: str | Path,
    candidate: str | Path,
    *,
    symbol: str | None = None,
    register_profile: str = DEFAULT_REGISTER_PROFILE,
) -> Diagnosis:
    """Load each retained dump once, then build both reports."""

    target_text = Path(target).read_text(encoding="utf-8")
    candidate_text = Path(candidate).read_text(encoding="utf-8")
    target_items = parse_selected_disassembly(target_text, symbol=symbol)
    candidate_items = parse_selected_disassembly(candidate_text, symbol=symbol)
    if not target_items or not candidate_items:
        raise ValueError(
            symbol_selection_error(
                symbol,
                inputs=(
                    (display_path(target), target_text),
                    (display_path(candidate), candidate_text),
                ),
            )
        )
    return diagnose_instructions(
        target_items,
        candidate_items,
        target_name=display_path(target),
        candidate_name=display_path(candidate),
        symbol=symbol,
        register_profile=register_profile,
        warnings=selection_warnings(
            target_text,
            candidate_text,
            symbol=symbol,
            target_name=display_path(target),
            candidate_name=display_path(candidate),
        ),
    )
