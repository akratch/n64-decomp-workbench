"""One-pass object loading for combined comparison and mechanism diagnosis."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .compare import compare_instructions
from .model import Comparison, Instruction, display_path
from .objdump import (
    cross_function_warning,
    dump_object,
    parse_disassembly,
    symbol_selection_error,
)
from .view import DEFAULT_REGISTER_PROFILE, MechanismView, build_view

DIAGNOSIS_SCHEMA = "decomp-workbench-diagnosis-v1"


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
            "view": self.view.as_dict(report_regs=report_regs),
        }


def diagnose_instructions(
    target: Sequence[Instruction],
    candidate: Sequence[Instruction],
    *,
    target_name: str,
    candidate_name: str,
    symbol: str | None,
    register_profile: str = DEFAULT_REGISTER_PROFILE,
    warnings: Sequence[str] = (),
) -> Diagnosis:
    """Build both reports from two already-parsed instruction streams."""

    target_items = list(target)
    candidate_items = list(candidate)
    comparison = compare_instructions(
        target_items,
        candidate_items,
        target_name=target_name,
        candidate_name=candidate_name,
        symbol=symbol,
        warnings=warnings,
    )
    view = build_view(
        target_items,
        candidate_items,
        target_name=target_name,
        candidate_name=candidate_name,
        symbol=symbol,
        register_profile=register_profile,
        warnings=warnings,
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
    warning = cross_function_warning(
        target_text,
        candidate_text,
        symbol=symbol,
        section=section,
    )
    return diagnose_instructions(
        target_items,
        candidate_items,
        target_name=display_path(target),
        candidate_name=display_path(candidate),
        symbol=symbol,
        register_profile=register_profile,
        warnings=(warning,) if warning else (),
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
    target_items = parse_disassembly(target_text, symbol=symbol)
    candidate_items = parse_disassembly(candidate_text, symbol=symbol)
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
    warning = cross_function_warning(target_text, candidate_text, symbol=symbol)
    return diagnose_instructions(
        target_items,
        candidate_items,
        target_name=display_path(target),
        candidate_name=display_path(candidate),
        symbol=symbol,
        register_profile=register_profile,
        warnings=(warning,) if warning else (),
    )
