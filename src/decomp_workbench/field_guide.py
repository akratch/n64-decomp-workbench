"""The field guide as a runtime resource, and the on-ramp off every verdict.

A community member ran `diagnose`, got a correct `register-permutation`
verdict with a `playbook=forced-color-oracle` footer, and wrote back: "this
looked cool, but no idea what im meant to do next".  The analysis was right and
the reader was still stranded, because every noun in the footer -- playbook,
forced color probe, instrumented toolchain -- was a concept with no address.
The project's own field guide answers all three, and no terminal output had
ever mentioned it.

This module closes that gap from both ends:

* `next_steps` is *data*, not a parse.  Diagnosis must never depend on a
  Markdown file being readable, so the verdict-to-lever index is transcribed
  here as a table of numbers and one-line actions.  A lever the shipped guide
  does not carry still gets its one-liner.
* `sections` is the parse, used only by `decomp-workbench guide`, which is the
  command the footer now tells the reader to paste.  The guide travels inside
  the package so an installed wheel can print it with no checkout.

The two halves are deliberately independent.  The table is the promise; the
document is the elaboration, and losing the document degrades the promise to a
one-liner rather than to silence.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import resources

__all__ = [
    "GUIDE_DOCUMENT",
    "LEVER_ACTIONS",
    "PLAYBOOK_LEVERS",
    "VERDICT_PLAYBOOKS",
    "GuideSection",
    "Topic",
    "next_steps",
    "read_field_guide",
    "render_topic",
    "resolve_topic",
    "sections",
    "topic_index_lines",
    "topic_names",
]

#: Where the guide lives for a reader who has the repository or the website.
GUIDE_DOCUMENT = "docs/field-guide.md"

#: Where it lives for a reader who only has the installed package. The mirror
#: is byte-identical to `GUIDE_DOCUMENT` and a test enforces that.
PACKAGED_GUIDE = ("docs", "field-guide.md")

#: One line of action per numbered lever.
#:
#: These are transcriptions, not summaries invented here: each says what the
#: lever's own "diff looks like" and code block say, short enough to survive
#: inside a `next:` footer. Levers 20-22 are carried even though this branch's
#: document stops at 19, because the number is the stable identity and the
#: one-liner has to work whether or not the section ships.
LEVER_ACTIONS: dict[int, str] = {
    1: (
        "audit the earliest immediate (lui/li/andi/ori/slti) against the "
        "target assembly, then re-derive every fake fitted to the old value"
    ),
    2: (
        "`a | b` and `b | a` canonicalize identically; `x |= b` is a distinct "
        "AST and flips the emitted operand order"
    ),
    3: (
        "rebuild the same candidate with -g0 and compare again; a collapse "
        "means .loc records constrain the -g3 schedule"
    ),
    4: (
        "re-check flag and ctx.c parity against the project's real preset "
        "before believing a structural residual"
    ),
    5: (
        "do not split loops or duplicate bodies to force a memory re-read; "
        "IDO's own loop-invariant motion wins (+147 words measured)"
    ),
    6: (
        "census the stack offsets on both sides and work the one value that "
        "gained a home, not the N shifted offsets"
    ),
    7: (
        "add `if (gSomeGlobal) {}` for a code-free web that takes the NEXT "
        "FREE pool slot; it cannot reach past a live web"
    ),
    8: (
        "when a plain `if (var) {}` is inert, dead-read an rvalue expression "
        "instead; intermediate values can take v0 where locals cannot"
    ),
    9: (
        "stack a second read of the losing web: uopt orders webs by "
        "accumulated benefit, so read count is a monotone priority dial"
    ),
    10: (
        "split a local's own update chain with `if (!x);` to form a short web "
        "from the intermediate value, at zero instructions and zero frame"
    ),
    11: (
        "promote the value to a named local spanning the loop (pool) or inline "
        "the expression (temp); no color force crosses that line"
    ),
    12: (
        "try `tab * 4` instead of `tab << 2` when a scaled index is near the "
        "divergence: one cheap variant, low confidence"
    ),
    13: (
        "mask into the formal parameter in place (`id &= 0xFFFF`) so the CSE "
        "web never forms; this is the delete-a-web lever"
    ),
    14: (
        "hoist a call-argument expression into a named local in the block "
        "BEFORE the divergence; that reorders the value deaths"
    ),
    15: (
        "materialize a phantom pop with `(state == -1) != 0` inside a real "
        "`if`; a bare discarded expression is dropped instead"
    ),
    16: (
        "add a redundant assembler-folded mask (`((s16)fx & 0x3fff) << 18`) "
        "for a genuinely free FIFO rotation"
    ),
    17: (
        "drop `void` for a K&R implicit-int return type on the declaration "
        "AND the definition; one variant, one coalescing copy"
    ),
    18: (
        "give a twice-referenced expression a named intermediate so the "
        "coalesced copy lands on the other value"
    ),
    19: (
        "the callee-saved tie-break is a uopt priority decision: force only "
        "the high-priority web and let the swap cascade"
    ),
    20: (
        "before concluding 'hand-patched object', fingerprint the other "
        "authentic frontends (accom/ccom, upas) feeding the same backend"
    ),
    21: (
        "under accom lineage source line numbers are semantic: bisect "
        "whitespace around the mis-scheduled instruction, not the expressions"
    ),
    22: (
        "classify the dispatch construct first (source order is never a "
        "switch) before spending variants on the wrong one"
    ),
}

#: The verdict-to-lever index of the field guide, keyed by playbook.
#:
#: Order is priority order, exactly as the document reads it.
PLAYBOOK_LEVERS: dict[str, tuple[int, ...]] = {
    "constant-audit": (1,),
    "ast-shape": (2,),
    "g0-schedule-probe": (3, 4),
    "structure-buckets": (1, 4, 5, 6),
    "temp-fifo-phase": (14, 15, 16),
    "pool-position": (7, 8, 9, 10, 11, 12, 13),
    "forced-color-oracle": (17, 18, 19),
}

#: Verdict spellings that select a playbook.
#:
#: Both vocabularies are here on purpose: `view`/`diagnose` print the aligned
#: taxonomy (`register-permutation`), `compare` prints the exactness taxonomy
#: (`allocation-mismatch`), and a reader who pastes either one into `guide`
#: must land on the same page.
VERDICT_PLAYBOOKS: dict[str, str] = {
    # aligned mechanism view
    "allocation": "pool-position",
    "commutative-order": "ast-shape",
    "constant": "constant-audit",
    "phase-shift": "temp-fifo-phase",
    "register-permutation": "forced-color-oracle",
    "schedule": "g0-schedule-probe",
    "structure": "structure-buckets",
    "words-identical": "relocation-only",
    # exact comparison
    "allocation-mismatch": "pool-position",
    "constant-mismatch": "constant-audit",
    "operand-mismatch": "constant-audit",
    "relocation-layout-mismatch": "relocation-only",
    "schedule-mismatch": "g0-schedule-probe",
    "structure-mismatch": "structure-buckets",
    "unknown-relocation": "relocation-only",
}

#: The instrumentation branch, spelled out for both answers.
#:
#: "prefer a forced color probe on an instrumented toolchain" is true and was
#: unusable: most readers do not have one, and the sentence never said what to
#: do in that case. Every playbook whose expert guidance names a trace, a probe
#: or an oracle therefore owes both branches, and the source-only branch comes
#: with a cost ("one variant each") so it can be chosen honestly.
PLAYBOOK_ONRAMPS: dict[str, tuple[str, ...]] = {
    "constant-audit": (
        "see every differing immediate side by side: "
        "decomp-workbench diagnose TARGET.o CANDIDATE.o --show-diff",
    ),
    "structure-buckets": (
        "bucket the hunks before choosing one: "
        "decomp-workbench view TARGET.o CANDIDATE.o --show-all",
    ),
    "g0-schedule-probe": (
        "have a calibrated toolchain? docs/pass-replay.md, then "
        "decomp-workbench replay-as1 LISTING.s OUT.o --as0-command ... "
        "--as1-command ... tests whether as1 owns the ordering.",
        "don't have one? the -g0 rebuild is levers 3 and 4 and needs only your "
        "normal compiler; run it before anything else.",
    ),
    "temp-fifo-phase": (
        "have a ugen trace? decomp-workbench trace-fifo TRACE.log replays the "
        "pool get/put schedule and shows where the rotation was set.",
        "don't have one? levers 14-16 are pure source and need no "
        "instrumentation; the lane rotation in this view already locates the "
        "preceding block.",
    ),
    "pool-position": (
        "have an instrumented toolchain? docs/compiler-instrumentation.md, "
        "then decomp-workbench instrument-uopt-globalcolor and "
        "decomp-workbench trace-globalcolor TRACE.log --proc N.",
        "don't have one? levers 7-13 are all source-only; spend them first, "
        "and read lever 9 before building any search - it is a dial, not a "
        "permutation.",
    ),
    "forced-color-oracle": (
        "have an instrumented toolchain? docs/compiler-instrumentation.md, "
        "then decomp-workbench diagnose ... --emit-force-spec force.json and "
        "decomp-workbench oracle plan TRACE.log to build the two-phase grid.",
        "don't have one? try levers 17 and 18 first (one variant each): they "
        "resolve a large share of single-bijection register residues cheaply, "
        "and lever 19 says a clean negative here is a legitimate stopping "
        "point - record it, bundle the scratch, take the next function.",
    ),
    "relocation-only": (
        "prove the spellings are linked-address equivalent: "
        "decomp-workbench relocation-aliases TARGET.o CANDIDATE.o",
    ),
}


def next_steps(playbook: str) -> tuple[str, ...]:
    """Return the on-ramp lines appended to one verdict's guidance.

    Pure data by design. `diagnose` must produce the same footer on a machine
    with no documentation installed as on the maintainer's checkout, so nothing
    here reads the guide; the block ends with the command that does.
    """

    levers = PLAYBOOK_LEVERS.get(playbook, ())
    lines: list[str] = []
    if levers:
        lines.append(f"field guide levers for playbook={playbook}:")
        lines.extend(f"  lever {number}: {LEVER_ACTIONS[number]}" for number in levers)
        lines.append(f"read them: decomp-workbench guide {playbook}")
    lines.extend(PLAYBOOK_ONRAMPS.get(playbook, ()))
    return tuple(lines)


# ---------------------------------------------------------------------------
# The document itself
# ---------------------------------------------------------------------------

SECTION_RE = re.compile(r"^###\s+(\d+)\.\s+(.+?)\s*$")
FAMILY_RE = re.compile(r"^##\s+(.+?)\s*$")


@dataclass(frozen=True)
class GuideSection:
    """One numbered lever, with the family heading it sits under."""

    number: int
    title: str
    family: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class Topic:
    """A resolved `guide` argument: what the reader asked for, and which levers."""

    name: str
    kind: str
    levers: tuple[int, ...]
    playbook: str | None


def read_field_guide() -> str:
    """Return the packaged field-guide Markdown.

    Raises `FileNotFoundError` with the two addresses that still work when the
    resource is missing, because a stripped install is exactly the case where
    "read the field guide" is otherwise unactionable advice.
    """

    resource = resources.files(__package__ or "decomp_workbench")
    for part in PACKAGED_GUIDE:
        resource = resource.joinpath(part)
    try:
        return resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as error:
        raise FileNotFoundError(
            "the field guide is not installed with this package "
            f"({'/'.join(PACKAGED_GUIDE)}); read it at {GUIDE_DOCUMENT} in a "
            "checkout, or at "
            "https://github.com/akratch/n64-decomp-workbench/blob/main/"
            f"{GUIDE_DOCUMENT}"
        ) from error


def parse_sections(text: str) -> dict[int, GuideSection]:
    """Split the guide into its `### N. Title` sections.

    The numbering is the guide's own stable addressing scheme -- the
    verdict-to-lever index, the cross-references between levers, and this
    package's tables all cite numbers -- so it is what the parser keys on
    rather than heading text, which is free to be edited.
    """

    found: dict[int, GuideSection] = {}
    family = ""
    number: int | None = None
    title = ""
    body: list[str] = []

    def flush() -> None:
        if number is None:
            return
        kept = list(body)
        while kept and kept[-1].strip() in {"", "---"}:
            kept.pop()
        found[number] = GuideSection(
            number=number,
            title=title,
            family=family,
            lines=tuple(kept),
        )

    for line in text.splitlines():
        section = SECTION_RE.match(line)
        if section is not None:
            flush()
            number, title = int(section.group(1)), section.group(2)
            body = [line]
            continue
        heading = FAMILY_RE.match(line)
        if heading is not None:
            flush()
            number, body = None, []
            family = heading.group(1)
            continue
        if number is not None:
            body.append(line)
    flush()
    return found


def sections() -> dict[int, GuideSection]:
    """Return the parsed shipped guide, keyed by lever number."""

    return parse_sections(read_field_guide())


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------


def topic_names() -> tuple[str, ...]:
    """Return every accepted topic, in the order the index prints them."""

    return (
        *PLAYBOOK_LEVERS,
        *sorted(VERDICT_PLAYBOOKS),
        *(str(number) for number in sorted(LEVER_ACTIONS)),
    )


def resolve_topic(topic: str) -> Topic:
    """Resolve a playbook name, a verdict, or a lever number to its levers."""

    name = topic.strip()
    if name.isdigit():
        number = int(name)
        if number not in LEVER_ACTIONS:
            known = ", ".join(str(item) for item in sorted(LEVER_ACTIONS))
            raise ValueError(f"unknown lever {name}; the guide numbers {known}")
        return Topic(name=name, kind="lever", levers=(number,), playbook=None)
    if name in PLAYBOOK_LEVERS:
        return Topic(
            name=name,
            kind="playbook",
            levers=PLAYBOOK_LEVERS[name],
            playbook=name,
        )
    playbook = VERDICT_PLAYBOOKS.get(name)
    if playbook is not None:
        return Topic(
            name=name,
            kind="verdict",
            levers=PLAYBOOK_LEVERS.get(playbook, ()),
            playbook=playbook,
        )
    raise ValueError(
        f"unknown guide topic {topic!r}; "
        "run `decomp-workbench guide` for the topic index"
    )


def topic_index_lines() -> list[str]:
    """Return the `guide` listing, which never needs the document."""

    lines = [
        f"Field guide topics ({GUIDE_DOCUMENT})",
        "Pass a playbook, a verdict, or a lever number.",
        "",
        "playbooks",
    ]
    width = max(len(name) for name in PLAYBOOK_LEVERS)
    for playbook, levers in PLAYBOOK_LEVERS.items():
        numbers = ", ".join(str(number) for number in levers)
        lines.append(f"  {playbook.ljust(width)}  levers {numbers}")
    lines.extend(("", "verdicts"))
    verdict_width = max(len(name) for name in VERDICT_PLAYBOOKS)
    for verdict, playbook in sorted(VERDICT_PLAYBOOKS.items()):
        lines.append(f"  {verdict.ljust(verdict_width)}  {playbook}")
    lines.extend(("", "levers"))
    for number in sorted(LEVER_ACTIONS):
        lines.append(f"  {number:>2}  {LEVER_ACTIONS[number]}")
    lines.extend(
        (
            "",
            "Example: decomp-workbench guide forced-color-oracle",
        )
    )
    return lines


def _lever_lines(number: int, available: dict[int, GuideSection]) -> Iterable[str]:
    """Render one lever, degrading to its one-liner when the section is absent.

    Levers 20-22 document a frontend-lineage family that is still on its own
    branch. The number is already the stable identity, so a guide that has not
    caught up should say so and still hand over the action, never fail.
    """

    section = available.get(number)
    if section is None:
        yield f"### {number}. (not in the shipped field guide)"
        yield ""
        yield LEVER_ACTIONS[number]
        yield ""
        yield (
            "This lever's section is not in this installation's "
            f"{GUIDE_DOCUMENT}. The one-line action above is complete on its "
            "own; the elaboration ships with a later revision."
        )
        return
    yield f"[{section.family}]"
    yield from section.lines


def render_topic(topic: Topic, available: dict[int, GuideSection]) -> list[str]:
    """Render every section a topic maps to, plus the on-ramp for its playbook."""

    numbers = ", ".join(str(number) for number in topic.levers)
    header = f"FIELD GUIDE  {topic.kind}={topic.name}"
    if topic.playbook is not None and topic.kind == "verdict":
        header += f"  playbook={topic.playbook}"
    if numbers:
        header += f"  levers {numbers}"
    lines = [header, f"source: {GUIDE_DOCUMENT}"]
    for number in topic.levers:
        lines.extend(("", "-" * 72, ""))
        lines.extend(_lever_lines(number, available))
    footer: list[str] = []
    if topic.playbook is not None:
        footer.extend(PLAYBOOK_ONRAMPS.get(topic.playbook, ()))
    else:
        # A lever asked for by number has no playbook of its own, so hand back
        # the families that reach it: that is where its ordering and its
        # instrumentation branch live.
        owners = [
            playbook
            for playbook, levers in PLAYBOOK_LEVERS.items()
            if set(topic.levers) & set(levers)
        ]
        footer.extend(
            f"in playbook {playbook}: decomp-workbench guide {playbook}"
            for playbook in owners
        )
    if footer:
        lines.extend(("", "-" * 72, "", "NEXT"))
        lines.extend(f"  {step}" for step in footer)
    return lines
