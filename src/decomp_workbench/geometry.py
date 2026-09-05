"""Structural ranking evidence, independent of exact-match verification.

Pareto layers avoid asserting an exchange rate between an extra instruction
and a different opcode. They are a search ordering, not a reachability test.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

GEOMETRY_RANKING = "geometry-pareto"
GeometryVector = tuple[int, int, int]


def geometry_vector(comparison: Mapping[str, Any]) -> GeometryVector | None:
    """Read extent and normalized/opcode edit script distances.

    Complete ledger records work too. Incomplete legacy records return
    None: a missing true extent must not become a fictitious exact extent.
    The true count retains the comparison loader's existing padding rules and
    scope; no whole-section size is substituted for a selected symbol here.
    """

    delta = comparison.get("true_insn_delta", comparison.get("true_instruction_delta"))
    layout = comparison.get("layout")
    edit = (
        layout.get("edit_distance")
        if isinstance(layout, Mapping)
        else comparison.get("norm", comparison.get("normalized_distance"))
    )
    opcodes = comparison.get("opcode_distance")
    if not all(isinstance(value, int) for value in (delta, edit, opcodes)):
        return None
    assert isinstance(delta, int) and isinstance(edit, int) and isinstance(opcodes, int)
    if edit < 0 or opcodes < 0:
        return None
    return abs(delta), edit, opcodes


def pareto_layers(vectors: Sequence[GeometryVector]) -> list[int]:
    """Assign zero to nondominated evidence and increasing layers thereafter.

    A dominates B only if no coordinate is worse and at least one is better.
    Equal vectors share a layer, whatever their positional word scores. Work
    on distinct vectors to keep repeated compiler basins cheap. Lexicographic
    traversal is a topological order of this dominance relation.
    """

    layers: dict[GeometryVector, int] = {}
    for vector in sorted(set(vectors)):
        layers[vector] = 1 + max(
            (
                layer
                for other, layer in layers.items()
                if all(a <= b for a, b in zip(other, vector, strict=True))
            ),
            default=-1,
        )
    return [layers[vector] for vector in vectors]
