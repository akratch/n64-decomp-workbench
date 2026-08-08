"""`decomp-workbench next`: what to run now, and one sentence of why.

The workbench has around forty commands and the field guide has around thirty
numbered levers. Both are correct and neither answers the question a reader
actually has in front of a mismatching pair, which is *which one first*.
Through one whole campaign that question was answered by a coordinator, out of
band, once per stage. A new reader gets no coordinator, so the answer has to
be a command.

This module is a router, not a second field guide. Each step it prints is one
concrete command with the real paths already substituted -- the footers
elsewhere print ``TARGET.o CANDIDATE.o`` and leave the reader to edit them --
plus a single sentence saying what that command settles. The detail behind
each family stays in `guide`, which every plan ends by naming, so there is
exactly one place the lever prose lives.

The ordering is the product. It encodes one rule the campaign paid for
repeatedly: *some differences make the others unreadable*. An instruction
count difference shifts every later word, so a register residue measured
across one is not a register residue at all. Steps that clear a blocker are
therefore ranked above steps that interpret what the blocker distorts, and
the blocker says so in its own sentence rather than relying on the reader to
infer it from position.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any

from .field_guide import PLAYBOOK_LEVERS, VERDICT_PLAYBOOKS
from .model import Comparison

#: Ranks, low first. Named rather than numbered at the call sites so the
#: ordering rule stays legible when a new route is added.
RANK_BLOCKER = 0
RANK_FAMILY = 1
RANK_ATTRIBUTION = 2
RANK_REFERENCE = 3

RANK_LABELS = {
    RANK_BLOCKER: "blocker",
    RANK_FAMILY: "family",
    RANK_ATTRIBUTION: "attribution",
    RANK_REFERENCE: "reference",
}


@dataclass(frozen=True)
class Step:
    """One recommended command with the reason it comes where it does."""

    rank: int
    command: str
    why: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "kind": RANK_LABELS[self.rank],
            "command": self.command,
            "why": self.why,
        }


@dataclass(frozen=True)
class Plan:
    """The ordered plan for one comparison."""

    target: str
    candidate: str
    words: int
    verdict: str
    matched: bool
    steps: tuple[Step, ...]
    blocked: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "decomp-workbench-next-v1",
            "target": self.target,
            "candidate": self.candidate,
            "words": self.words,
            "verdict": self.verdict,
            "matched": self.matched,
            "steps": [step.as_dict() for step in self.steps],
            "blocked": list(self.blocked),
        }


def _command(*parts: str) -> str:
    return " ".join(["decomp-workbench", *parts])


#: One concrete command and one sentence per verdict. Deliberately one route
#: per verdict: the value of this command is that it chooses, and a list of
#: three correct options would hand the choice straight back.
VERDICT_ROUTES: dict[str, tuple[str, str]] = {
    "structure-mismatch": (
        "view {target} {candidate} --show-all",
        "opcode shape differs, so this is a source-level difference; bucket "
        "the hunks and work at the expression or control-flow level before "
        "any allocator experiment.",
    ),
    "schedule-mismatch": (
        "diagnose {target} {candidate}",
        "the instruction multiset is identical and only the order differs, "
        "so this is late-pass scheduling; diagnose says whether statement "
        "line assignment or the assembler owns the ordering.",
    ),
    "allocation-mismatch": (
        "diagnose {target} {candidate}",
        "opcode shape matches and only registers differ; diagnose names "
        "which allocation family this is -- temp-FIFO phase, pool position, "
        "or coalescing -- from these two objects, with no instrumented "
        "toolchain.",
    ),
    "constant-mismatch": (
        "diagnose {target} {candidate} --show-diff",
        "shapes agree and only literal operands differ; this puts every "
        "differing immediate side by side.",
    ),
    "operand-mismatch": (
        "diagnose {target} {candidate} --show-diff",
        "shapes agree and only literal operands differ; this puts every "
        "differing immediate side by side.",
    ),
    "frame-layout-mismatch": (
        "view {target} {candidate}",
        "the stack frames differ, which is its own acceptance gate: a better "
        "register score cannot compensate for a wrong frame.",
    ),
    "relocation-layout-mismatch": (
        "relocation-aliases {target} {candidate}",
        "the differences are linker-controlled, so prove whether the two "
        "spellings resolve to the same linked address before treating any of "
        "them as work.",
    ),
    "unknown-relocation": (
        "relocation-aliases {target} {candidate}",
        "an unrecognized relocation kind is in play, so the masked word "
        "counts cannot be trusted until it is classified.",
    ),
}

#: Where a verdict with no route of its own is sent.
FALLBACK_ROUTE = (
    "diagnose {target} {candidate}",
    "one screen of exactness, mechanism, and the field-guide lever for this residual.",
)


def plan_next_steps(
    item: Comparison,
    *,
    target: str,
    candidate: str,
    source: str | None = None,
) -> Plan:
    """Return the ordered plan for one comparison."""

    quoted_target = shlex.quote(target)
    quoted_candidate = shlex.quote(candidate)
    steps: list[Step] = []
    blocked: list[str] = []

    if item.exact:
        steps.append(
            Step(
                RANK_FAMILY,
                _command("fidelity", quoted_target, quoted_candidate),
                "the selected function matches; whether the rest of the "
                "object does is a separate gate and this is the one that "
                "answers it.",
            )
        )
        steps.append(
            Step(
                RANK_ATTRIBUTION,
                _command("object-collateral", quoted_target, quoted_candidate),
                "expose any whole-object change that landed outside the "
                "function you were working on.",
            )
        )
        return Plan(
            target=target,
            candidate=candidate,
            words=item.word_mismatches,
            verdict=item.verdict,
            matched=True,
            steps=tuple(steps),
            blocked=(),
        )

    delta = item.candidate_instructions - item.target_instructions
    if delta:
        direction = "more" if delta > 0 else "fewer"
        steps.append(
            Step(
                RANK_BLOCKER,
                _command("view", quoted_target, quoted_candidate),
                f"the candidate emits {abs(delta)} {direction} instruction(s) "
                "than the target, so every word after the first count "
                "difference is shifted rather than wrong; find where the "
                "counts diverge before reading anything downstream of it.",
            )
        )
        blocked.append(
            "allocator and scheduler experiments: their residue is not "
            "measurable across an instruction-count difference."
        )

    if (
        item.target_frame_size is not None
        and item.candidate_frame_size is not None
        and item.target_frame_size != item.candidate_frame_size
    ):
        steps.append(
            Step(
                RANK_BLOCKER,
                _command("guide", "stack-frame-recovery"),
                f"the frames differ (target {item.target_frame_size}, "
                f"candidate {item.candidate_frame_size}); frame recovery is "
                "its own acceptance gate, and a better register score cannot "
                "compensate for a wrong frame.",
            )
        )

    if item.word_mismatches == 0 and item.raw_word_mismatches:
        steps.append(
            Step(
                RANK_FAMILY,
                _command("relocation-aliases", quoted_target, quoted_candidate),
                "no instruction word differs once linker-controlled fields "
                "are masked, so what is left is relocation spelling; this "
                "proves whether the two spellings link to the same address.",
            )
        )
    else:
        template, why = VERDICT_ROUTES.get(item.verdict, FALLBACK_ROUTE)
        steps.append(
            Step(
                RANK_FAMILY,
                _command(
                    template.format(target=quoted_target, candidate=quoted_candidate)
                ),
                f"verdict={item.verdict}: {why}",
            )
        )

    region_command = _command(
        "compare",
        quoted_target,
        quoted_candidate,
        "--by-region",
        shlex.quote(source) if source else "SRC.c",
    )
    if source:
        region_why = (
            "rank the differing words by the source construct that emitted "
            "them, so the next edit is the biggest region rather than the "
            "first differing row."
        )
    else:
        region_why = (
            "rank the differing words by the source construct that emitted "
            "them; pass --src to have this filled in with your candidate's "
            "source path."
        )
    steps.append(Step(RANK_ATTRIBUTION, region_command, region_why))

    playbook = VERDICT_PLAYBOOKS.get(item.verdict)
    if playbook:
        levers = PLAYBOOK_LEVERS.get(playbook, ())
        lever_text = (
            f" (levers {', '.join(str(number) for number in levers)})" if levers else ""
        )
        steps.append(
            Step(
                RANK_REFERENCE,
                _command("guide", playbook),
                f"the lever family for this verdict{lever_text}, with the "
                "evidence each one needs.",
            )
        )

    steps.sort(key=lambda step: step.rank)
    return Plan(
        target=target,
        candidate=candidate,
        words=item.word_mismatches,
        verdict=item.verdict,
        matched=False,
        steps=tuple(steps),
        blocked=tuple(blocked),
    )


def render_plan(plan: Plan, *, limit: int | None = None) -> list[str]:
    """Render the plan: the state in one line, then numbered steps."""

    if plan.matched:
        head = f"next: this function matches ({plan.target} vs {plan.candidate})"
    else:
        plural = "" if plan.words == 1 else "s"
        head = (
            f"next: {plan.words} word{plural} differ, verdict={plan.verdict} "
            f"({plan.target} vs {plan.candidate})"
        )
    lines = [head, ""]
    shown = plan.steps if limit is None else plan.steps[:limit]
    for position, step in enumerate(shown, start=1):
        marker = "  [blocker] " if step.rank == RANK_BLOCKER else "  "
        lines.append(f"{position}.{marker}{step.command}")
        lines.extend(_wrap(step.why, prefix="     why: ", continuation="          "))
        lines.append("")
    if limit is not None and len(plan.steps) > limit:
        remaining = len(plan.steps) - limit
        lines.append(f"({remaining} further step(s); pass --all to see them)")
        lines.append("")
    if plan.blocked:
        lines.append("not yet:")
        for entry in plan.blocked:
            lines.extend(_wrap(entry, prefix="  - ", continuation="    "))
    return [line.rstrip() for line in lines]


def _wrap(text: str, *, prefix: str, continuation: str, width: int = 78) -> list[str]:
    lines: list[str] = []
    current = prefix
    for word in text.split():
        if len(current) + len(word) + 1 > width and current.strip() not in {
            prefix.strip(),
            "",
        }:
            lines.append(current.rstrip())
            current = continuation
        current += word + " "
    if current.strip():
        lines.append(current.rstrip())
    return lines
