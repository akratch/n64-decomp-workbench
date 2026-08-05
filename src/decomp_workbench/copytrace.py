"""Parse and compare IDO copy/coalescing decision traces.

The producer's ``rhstable`` field is a hash-table bucket, not an expression
identity: unrelated expressions can collide there.  This module deliberately
keeps that value as an observation while aligning final decisions by the LHS
stack home and assignment ordinal.  Statement, bit, and bucket numbers remain
run-local evidence.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from itertools import pairwise
from typing import Any

COPYTRACE_SCHEMA = "decomp-workbench-copy-decisions-v1"
COPYDEC_STAGE_ORDER = (
    "pre-makelivranges",
    "post-makelivranges",
    "pre-localcolor",
    "post-localcolor",
    "post-globalcolor",
    "pre-reemit",
)
COPYDEC_RE = re.compile(
    r"^CDXW\s+\d+\s+p(?P<proc>-?\d+)\s+d\d+\s+COPYDEC\s+"
    r"tag=(?P<tag>\S+)\s+stmt=(?P<stmt>-?\d+)\s+"
    r"lhs=(?P<lhs>-?\d+)\s+rhs=(?P<rhs>-?\d+)\s+"
    r"rhsop=(?P<rhsop>[0-9a-fA-F]+)\s+"
    r"rhstable=(?P<bucket>\d+)\s+rhschain=(?P<chain>\d+)\s+"
    r"occ=(?P<formed_occurrences>\d+)/(?P<bucket_occupancy>\d+)\s+"
    r"rhsformed=(?P<rhsformed>-?\d+)\s+bbwit=(?P<bbwit>-?\d+)\s+"
    r"lhscolor=(?P<lhscolor>-?\d+)\s+rhscolor=(?P<rhscolor>-?\d+)\s+"
    r"lhsframe=(?P<lhsframe>[0-9a-fA-F]+)\s+->\s+"
    r"(?P<decision>COALESCE|TEMPCOPY)$"
)


def _signed_u32(value: str) -> int:
    parsed = int(value, 16)
    return parsed - (1 << 32) if parsed & (1 << 31) else parsed


@dataclass(frozen=True)
class CopyDecision:
    """One trace-local assignment decision at an optimizer census point."""

    proc: int
    tag: str
    stmt: int
    lhs: int
    rhs: int
    rhs_opcode: int
    rhs_hash_bucket: int
    rhs_hash_chain: int
    bucket_formed_entries: int
    bucket_occupancy: int
    rhs_formed: int
    basic_block_witnesses: int
    lhs_color: int
    rhs_color: int
    lhs_frame: int
    decision: str
    home_ordinal: int = 0

    @property
    def stable_key(self) -> tuple[int, int, int]:
        return (self.proc, self.lhs_frame, self.home_ordinal)

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["rhs_opcode"] = f"0x{self.rhs_opcode:02x}"
        result["lhs_frame_hex"] = f"0x{self.lhs_frame & 0xFFFFFFFF:08x}"
        result["alignment_key"] = (
            f"proc{self.proc}:home{self.lhs_frame:+#x}:#{self.home_ordinal}"
        )
        return result


def parse_copy_decisions(
    text: str,
    *,
    tag: str = "pre-reemit",
    proc: int | None = None,
) -> tuple[list[CopyDecision], list[str]]:
    """Parse one final-stage COPYDEC snapshot and retain malformed records."""

    selected: list[CopyDecision] = []
    malformed: list[str] = []
    ordinals: dict[tuple[int, int], int] = defaultdict(int)
    for raw in text.splitlines():
        if "COPYDEC" not in raw:
            continue
        match = COPYDEC_RE.match(raw.strip())
        if match is None:
            malformed.append(raw)
            continue
        values = match.groupdict()
        item_proc = int(values["proc"])
        if values["tag"] != tag or (proc is not None and item_proc != proc):
            continue
        lhs_frame = _signed_u32(values["lhsframe"])
        ordinal_key = (item_proc, lhs_frame)
        ordinal = ordinals[ordinal_key]
        ordinals[ordinal_key] += 1
        selected.append(
            CopyDecision(
                proc=item_proc,
                tag=values["tag"],
                stmt=int(values["stmt"]),
                lhs=int(values["lhs"]),
                rhs=int(values["rhs"]),
                rhs_opcode=int(values["rhsop"], 16),
                rhs_hash_bucket=int(values["bucket"]),
                rhs_hash_chain=int(values["chain"]),
                bucket_formed_entries=int(values["formed_occurrences"]),
                bucket_occupancy=int(values["bucket_occupancy"]),
                rhs_formed=int(values["rhsformed"]),
                basic_block_witnesses=int(values["bbwit"]),
                lhs_color=int(values["lhscolor"]),
                rhs_color=int(values["rhscolor"]),
                lhs_frame=lhs_frame,
                decision=values["decision"],
                home_ordinal=ordinal,
            )
        )
    return selected, malformed


def _summary(items: list[CopyDecision]) -> dict[str, Any]:
    outcomes = Counter(item.decision for item in items)
    return {
        "decision_count": len(items),
        "coalesced": outcomes["COALESCE"],
        "temporary_copies": outcomes["TEMPCOPY"],
        "stack_homes": len({(item.proc, item.lhs_frame) for item in items}),
    }


def _owner_pass(before: str, after: str) -> str | None:
    """Name a pass only when snapshots directly bracket that same pass."""

    if before.startswith("pre-") and after == f"post-{before[4:]}":
        return before[4:]
    return None


def _transition_timeline(text: str, *, proc: int | None) -> dict[str, Any]:
    """Find the first observed COPYDEC outcome transition for each stack home."""

    snapshots: dict[tuple[int, int, int], list[CopyDecision]] = defaultdict(list)
    observed_stages: list[str] = []
    for stage in COPYDEC_STAGE_ORDER:
        items, _ = parse_copy_decisions(text, tag=stage, proc=proc)
        if items:
            observed_stages.append(stage)
        for item in items:
            snapshots[item.stable_key].append(item)

    transitions: list[dict[str, Any]] = []
    for items in snapshots.values():
        for before, after in pairwise(items):
            if before.decision == after.decision:
                continue
            owner = _owner_pass(before.tag, after.tag)
            transitions.append(
                {
                    "alignment_key": before.as_dict()["alignment_key"],
                    "before_stage": before.tag,
                    "after_stage": after.tag,
                    "before_decision": before.decision,
                    "after_decision": after.decision,
                    "before_rhs_formed": before.rhs_formed,
                    "after_rhs_formed": after.rhs_formed,
                    "before_basic_block_witnesses": before.basic_block_witnesses,
                    "after_basic_block_witnesses": after.basic_block_witnesses,
                    "owner_pass": owner,
                    "owner_claim": (
                        "directly bracketed pass"
                        if owner is not None
                        else "unresolved interval between snapshots"
                    ),
                }
            )
            break
    return {
        "observed_stages": observed_stages,
        "decision_transition_count": len(transitions),
        "transitions": transitions,
    }


def copy_decision_report(
    text: str,
    *,
    against: str | None = None,
    tag: str = "pre-reemit",
    proc: int | None = None,
) -> dict[str, Any]:
    """Report one trace or compare two final copy-decision snapshots."""

    baseline, malformed = parse_copy_decisions(text, tag=tag, proc=proc)
    report: dict[str, Any] = {
        "schema": COPYTRACE_SCHEMA,
        "stage": tag,
        "proc": proc,
        "claim_scope": "allocator-copy-decision",
        "summary": _summary(baseline),
        "decisions": [item.as_dict() for item in baseline],
        "timeline": _transition_timeline(text, proc=proc),
        "malformed_copydec_lines": malformed,
        "warnings": [
            "rhs_hash_bucket/rhs_hash_chain are collision-prone hash-table "
            "observations, not expression identity or CSE multiplicity.",
            "stmt, lhs, and rhs numbers are trace-local; comparison aligns "
            "by LHS stack home and assignment ordinal.",
            "A changed decision identifies compiler behavior, not the source "
            "expression that caused it; recompare the emitted object.",
            "A basic-block witness is correlated formation evidence, not by "
            "itself proof that the observed set is the pass's causal input.",
        ],
    }
    if against is None:
        return report

    candidate, candidate_malformed = parse_copy_decisions(against, tag=tag, proc=proc)
    baseline_by_key = {item.stable_key: item for item in baseline}
    candidate_by_key = {item.stable_key: item for item in candidate}
    differences: list[dict[str, Any]] = []
    trusted_fields = (
        "decision",
        "rhs_formed",
        "basic_block_witnesses",
        "lhs_color",
        "rhs_color",
        "rhs_opcode",
    )
    for key in sorted(set(baseline_by_key) | set(candidate_by_key)):
        before = baseline_by_key.get(key)
        after = candidate_by_key.get(key)
        if before is None or after is None:
            changed = ["presence"]
        else:
            changed = [
                field
                for field in trusted_fields
                if getattr(before, field) != getattr(after, field)
            ]
        if not changed:
            continue
        aligned = before if before is not None else after
        assert aligned is not None
        differences.append(
            {
                "alignment_key": aligned.as_dict()["alignment_key"],
                "changed": changed,
                "baseline": None if before is None else before.as_dict(),
                "candidate": None if after is None else after.as_dict(),
            }
        )
    report.update(
        candidate_summary=_summary(candidate),
        candidate_timeline=_transition_timeline(against, proc=proc),
        candidate_malformed_copydec_lines=candidate_malformed,
        difference_count=len(differences),
        differences=differences,
        proof=(
            "COPYDEC outcomes and formation witnesses are direct producer "
            "observations; alignment and source causality remain hypotheses."
        ),
    )
    return report
