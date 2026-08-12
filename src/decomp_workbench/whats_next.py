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
#: Floating-point register rows above which a residual is worth reading as a
#: possible scratch-ring rotation rather than a list of mistakes. Three stages
#: of one campaign scored ring-flipped objects as wins; one row is noise, but a
#: run of them has a shape, and `phase` is the command that names it.
RING_ROTATION_THRESHOLD = 4

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
    """One executable, read-only recommendation and why it comes next.

    ``argv`` is the source of truth.  The shell spelling is rendered only at
    the presentation boundary; callers must never have to parse prose back
    into arguments, and quoting cannot silently discard a selector.
    """

    rank: int
    argv: tuple[str, ...]
    why: str
    action: str
    expected_signal: str

    @property
    def command(self) -> str:
        """Return a paste-ready shell spelling of the typed arguments."""

        return shlex.join(("decomp-workbench", *self.argv))

    def as_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "kind": RANK_LABELS[self.rank],
            "action": self.action,
            "command_argv": ["decomp-workbench", *self.argv],
            "command": self.command,
            "why": self.why,
            "expected_signal": self.expected_signal,
            "safety": "read-only",
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


_DUMP_COMMANDS = {
    "align": "align-dumps",
    "compare": "compare-dumps",
    "diagnose": "diagnose-dumps",
    "phase": "phase-dumps",
    "view": "view-dumps",
}


def _comparison_argv(
    command: str,
    target: str,
    candidate: str,
    *,
    dumps: bool,
    symbol: str | None,
    section: str,
    objdump: str | None,
    extra: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Build an input-kind-correct comparison command with its selectors."""

    actual = _DUMP_COMMANDS[command] if dumps else command
    argv = [actual, target, candidate, *extra]
    if symbol:
        argv.extend(("--function", symbol))
    if not dumps:
        argv.extend(("--section", section))
        if objdump:
            argv.extend(("--objdump", objdump))
    return tuple(argv)


#: One concrete command and one sentence per verdict. Deliberately one route
#: per verdict: the value of this command is that it chooses, and a list of
#: three correct options would hand the choice straight back.
VERDICT_ROUTES: dict[str, tuple[str, tuple[str, ...], str]] = {
    "structure-mismatch": (
        "view",
        ("--show-all",),
        "opcode shape differs, so this is a source-level difference; bucket "
        "the hunks and work at the expression or control-flow level before "
        "any allocator experiment.",
    ),
    "schedule-mismatch": (
        "diagnose",
        (),
        "the instruction multiset is identical and only the order differs, "
        "so this is late-pass scheduling; diagnose says whether statement "
        "line assignment or the assembler owns the ordering.",
    ),
    "allocation-mismatch": (
        "diagnose",
        (),
        "opcode shape matches and only registers differ; diagnose names "
        "which allocation family this is -- temp-FIFO phase, pool position, "
        "or coalescing -- from these two objects, with no instrumented "
        "toolchain.",
    ),
    "constant-mismatch": (
        "diagnose",
        ("--show-diff",),
        "shapes agree and only literal operands differ; this puts every "
        "differing immediate side by side.",
    ),
    "operand-mismatch": (
        "diagnose",
        ("--show-diff",),
        "shapes agree and only literal operands differ; this puts every "
        "differing immediate side by side.",
    ),
    "frame-layout-mismatch": (
        "view",
        (),
        "the stack frames differ, which is its own acceptance gate: a better "
        "register score cannot compensate for a wrong frame.",
    ),
}

#: Verdicts whose residue the allocator owns, and for which the force sweep is
#: a *first* move rather than a post-hoc check. One campaign used `CDX_FORCE`
#: mostly to confirm conclusions it had already reached by editing source; used
#: first, it answered in six builds what a source sweep had not answered in
#: hundreds.
ALLOCATION_VERDICTS = frozenset({"allocation-mismatch", "frame-layout-mismatch"})

#: Where a verdict with no route of its own is sent.
FALLBACK_ROUTE = (
    "diagnose",
    (),
    "one screen of exactness, mechanism, and the field-guide lever for this residual.",
)


def plan_next_steps(
    item: Comparison,
    *,
    target: str,
    candidate: str,
    source: str | None = None,
    dumps: bool = False,
    symbol: str | None = None,
    section: str = ".text",
    objdump: str | None = None,
    symbol_map: str | None = None,
    trace: str | None = None,
    proc: int | None = None,
) -> Plan:
    """Return the ordered plan for one comparison."""

    steps: list[Step] = []
    blocked: list[str] = []

    if item.exact:
        if dumps:
            steps.append(
                Step(
                    RANK_FAMILY,
                    ("guide", "post-match-cleanup"),
                    "the retained disassembly matches, but a text dump cannot "
                    "prove whole-object, translation-unit, or linked-ROM "
                    "fidelity; this names the remaining gates without "
                    "overstating the evidence you supplied.",
                    "open-post-match-gates",
                    "the exactness gates still requiring real build artifacts",
                )
            )
        else:
            steps.append(
                Step(
                    RANK_FAMILY,
                    _comparison_argv(
                        "object-collateral",
                        target,
                        candidate,
                        dumps=False,
                        symbol=symbol,
                        section=section,
                        objdump=objdump,
                    ),
                    "the selected function matches; expose any whole-object "
                    "change that landed outside it before promotion.",
                    "check-object-collateral",
                    "zero unexplained changes outside the selected function",
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
                _comparison_argv(
                    "align",
                    target,
                    candidate,
                    dumps=dumps,
                    symbol=symbol,
                    section=section,
                    objdump=objdump,
                ),
                f"the candidate emits {abs(delta)} {direction} instruction(s) "
                "than the target, so every word after the first count "
                "difference is shifted rather than wrong; this names the "
                "inserted and deleted instructions and says how many "
                "instructions away the candidate really is, instead of what "
                "the shift costs positionally.",
                "locate-structural-shift",
                "the inserted/deleted rows and the first trustworthy aligned residue",
            )
        )
        blocked.append(
            "allocator and scheduler experiments: their residue is not "
            "measurable across an instruction-count difference."
        )

    if item.fp_register_mismatches >= RING_ROTATION_THRESHOLD:
        steps.append(
            Step(
                RANK_FAMILY,
                _comparison_argv(
                    "phase",
                    target,
                    candidate,
                    dumps=dumps,
                    symbol=symbol,
                    section=section,
                    objdump=objdump,
                ),
                f"{item.fp_register_mismatches} row(s) differ in a "
                "floating-point register, which is the shape a rotated "
                "scratch ring makes: read whether the residual is a renaming "
                "before treating it as a mistake, and read the positional "
                "count beside it so a rotation is never recorded as a win.",
                "classify-fp-ring-phase",
                "whether one coherent floating-point register rotation "
                "explains the rows",
            )
        )

    if (
        item.target_frame_size is not None
        and item.candidate_frame_size is not None
        and item.target_frame_size != item.candidate_frame_size
    ):
        steps.append(
            Step(
                RANK_BLOCKER,
                ("guide", "stack-frame-recovery"),
                f"the frames differ (target {item.target_frame_size}, "
                f"candidate {item.candidate_frame_size}); frame recovery is "
                "its own acceptance gate, and a better register score cannot "
                "compensate for a wrong frame.",
                "recover-stack-frame",
                "a source experiment that restores the target frame size",
            )
        )

    if item.word_mismatches == 0 and item.raw_word_mismatches and symbol_map:
        relocation_argv = [
            "relocation-aliases",
            target,
            candidate,
            "--symbol-map",
            symbol_map,
        ]
        if symbol:
            relocation_argv.extend(("--symbol", symbol))
        steps.append(
            Step(
                RANK_FAMILY,
                tuple(relocation_argv),
                "no instruction word differs once linker-controlled fields "
                "are masked, so what is left is relocation spelling; this "
                "proves whether the two spellings link to the same address.",
                "prove-relocation-aliases",
                "resolved-address equality or a concrete non-aliasing relocation",
            )
        )
    elif item.word_mismatches == 0 and item.raw_word_mismatches:
        steps.append(
            Step(
                RANK_FAMILY,
                ("guide", "relocation-only"),
                "only linker-controlled fields remain, but proving aliasing "
                "requires a linked symbol map; the guide explains that proof "
                "and `next --symbol-map MAP` will emit the concrete command.",
                "prepare-relocation-proof",
                "a linked symbol map suitable for resolving both spellings",
            )
        )
    else:
        command, extra, why = VERDICT_ROUTES.get(item.verdict, FALLBACK_ROUTE)
        steps.append(
            Step(
                RANK_FAMILY,
                _comparison_argv(
                    command,
                    target,
                    candidate,
                    dumps=dumps,
                    symbol=symbol,
                    section=section,
                    objdump=objdump,
                    extra=extra,
                ),
                f"verdict={item.verdict}: {why}",
                "inspect-dominant-mechanism",
                "a mechanism-specific residual and evidence-backed lever family",
            )
        )

    if item.verdict in ALLOCATION_VERDICTS and trace:
        # The step campaigns take last and should take first. Forcing one web
        # to a colour turned an apparently 21-row construct into a 2-row one
        # and showed its extra instruction was a symptom rather than a cost --
        # in six builds, against a source sweep that would have taken
        # hundreds. The best forced object is the construct's ceiling: if
        # forcing cannot reach the target, no source spelling of this
        # construct will either.
        steps.append(
            Step(
                RANK_FAMILY,
                (
                    "oracle",
                    "plan",
                    trace,
                    *(("--proc", str(proc)) if proc is not None else ()),
                ),
                "before spending builds on source variants: sweep the forced "
                "colours over the webs this residue names, and record the "
                "best forced object as the construct's ceiling. A ceiling "
                "that does not reach the target rules out every source "
                "spelling of the construct at once.",
                "plan-forced-color-oracle",
                "a bounded force grid and an explicit ceiling for this construct",
            )
        )

    if source:
        steps.append(
            Step(
                RANK_ATTRIBUTION,
                _comparison_argv(
                    "compare",
                    target,
                    candidate,
                    dumps=dumps,
                    symbol=symbol,
                    section=section,
                    objdump=objdump,
                    extra=("--by-region", source),
                ),
                "rank the differing words by the source construct that "
                "emitted them, so the next edit is the biggest attributed "
                "region rather than the first differing row.",
                "attribute-residue-to-source",
                "ranked source regions with explicit attribution coverage",
            )
        )

    playbook = VERDICT_PLAYBOOKS.get(item.verdict)
    if playbook:
        levers = PLAYBOOK_LEVERS.get(playbook, ())
        lever_text = (
            f" (levers {', '.join(str(number) for number in levers)})" if levers else ""
        )
        steps.append(
            Step(
                RANK_REFERENCE,
                ("guide", playbook),
                f"the lever family for this verdict{lever_text}, with the "
                "evidence each one needs.",
                "open-verdict-playbook",
                "candidate source levers and the evidence required to use them",
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
