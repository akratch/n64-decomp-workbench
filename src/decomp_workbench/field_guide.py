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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from importlib import resources

__all__ = [
    "AMBIGUOUS_ONRAMPS",
    "AMBIGUOUS_PLAYBOOK_FAMILIES",
    "COARSE_ALLOCATION_LEAD_IN",
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
#: inside a `next:` footer.
#:
#: The number, not the heading, is the stable identity: this table was written
#: while levers 20-22 lived on another branch and had to work before their
#: sections existed. They ship now, and the degradation path in `_lever_lines`
#: stays for the next lever that arrives here first.
LEVER_ACTIONS: dict[int, str] = {
    1: (
        "audit the earliest immediate (lui/li/andi/ori/slti) against the "
        "target assembly, then re-derive every fake fitted to the old value"
    ),
    2: (
        "`a | b` and `b | a` canonicalize identically under cfe and `x |= b` "
        "is a distinct AST that flips the emitted order; under accom lineage "
        "`a + b` emits reversed operands, so commuting the source is free"
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
        "only when the residue contains a move/copy: drop `void` for a K&R "
        "implicit-int return type on the declaration AND the definition; "
        "one variant"
    ),
    18: (
        "only when the residue contains a move/copy: give a genuinely "
        "repeated expression a named intermediate so the coalesced copy "
        "lands on the other value; trace-copy-decisions names the first "
        "changing pass, but hash occupancy does not prove source repetition"
    ),
    19: (
        "the callee-saved tie-break is a uopt ordering decision: force the "
        "smallest measured causal web set (often one, sometimes a staggered "
        "blocker ladder), inspect every cascade, and compare paired formation, "
        "save/totalsave, and decision-trace order; no one scalar is priority proof"
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
    23: (
        "preprocess the TU with IDO's acpp (`acpp <defines> f.c > f.i && cc -c "
        "<flags> f.i`): uopt/ugen honor statement line boundaries even at -g0"
    ),
    24: (
        "run `decomp-workbench context lint` over the translation unit: an "
        "#if/#elif whose identifiers are ALL undefined evaluates a constant "
        "no one intended (0 >= 0 is true) -- define the macro, include its "
        "header, or delete the stale guard"
    ),
    25: (
        "cfe numbers statements by LOGICAL line, so ties are free: splice the "
        "block and the statement after it onto one line (trailing `\\`, or one "
        "physical line) to give that statement a line number from inside the "
        "block, and pair it with a legal statement hoist"
    ),
    26: (
        "when registers/opcodes are exact but the frame is not, preserve the "
        "winning live-range topology; first compare observed save-slot bytes "
        "with non-save frame bytes, then ablate, narrow, or reuse phantom "
        "homes only in the component that actually differs -- and move temp "
        "offsets with a split local (a pad slot), not by deleting one"
    ),
    27: (
        "after exactness, inventory suspicious constructs, compose bounded "
        "cross-family substitutions, retain every exact candidate, and gate "
        "the winner on translation-unit collateral plus project verification"
    ),
    28: (
        "when the callee-saved register is taken rather than underpriced, stop "
        "reweighting and alias the memory half of the pair (`if (&local);`): "
        "zero instructions, the local leaves web candidacy, and the slot frees "
        "-- sweep the mark's placement innermost-first (140/131/106 words on "
        "one function) and check candidate_frame_size on every variant"
    ),
}

#: The verdict-to-lever index of the field guide, keyed by playbook.
#:
#: Order is priority order, exactly as the document reads it.
PLAYBOOK_LEVERS: dict[str, tuple[int, ...]] = {
    "constant-audit": (1,),
    "ast-shape": (2,),
    # Lever 23 joins this family rather than replacing it: the -g0 probe is
    # still the first move for a project that builds -g3. It is also the lever
    # that rescues the reader for whom lever 3 is vacuous, which is why a
    # schedule verdict must reach it without a second command. Lever 24 rides
    # along because an undefined-macro guard can also masquerade late.
    "g0-schedule-probe": (3, 4, 23, 24),
    # Lever 25 sits second: once 23 has told you the residue is line numbers,
    # 25 is what you reach for when the number you need is unreachable one
    # statement per physical line.
    "line-assignment-probe": (23, 25, 4),
    "structure-buckets": (1, 4, 24, 5, 6),
    "temp-fifo-phase": (14, 15, 16),
    "pool-position": (7, 8, 9, 10, 11, 12, 13, 28),
    "forced-color-oracle": (17, 18, 19),
    "stack-frame-recovery": (26,),
    "post-match-cleanup": (27,),
    # No `view` verdict reaches this one: two disassemblies cannot tell you
    # that the *frontend* was different. It is here so the levers the field
    # guide's index names in prose are still one command away, and so the
    # topic list admits the family exists.
    "frontend-lineage": (20, 22, 21),
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
    "frame-layout": "stack-frame-recovery",
    "phase-shift": "temp-fifo-phase",
    "register-permutation": "forced-color-oracle",
    "schedule": "g0-schedule-probe",
    "structure": "structure-buckets",
    "words-identical": "relocation-only",
    # exact comparison
    "allocation-mismatch": "pool-position",
    "constant-mismatch": "constant-audit",
    "frame-layout-mismatch": "stack-frame-recovery",
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
        "already building -g0, so the probe has nothing to collapse? that is "
        "lever 23: statement line boundaries constrain uopt/ugen at -g0 too. "
        "decomp-workbench diagnose ... --candidate-listing LISTING.s measures "
        "it before you spend a build, and decomp-workbench probe-lines proves "
        "ownership with one token-identical variant plus a control.",
    ),
    # The two `acpp` branches lead, per this playbook's own convention: the
    # reader without the tool must not be told about the tool first. The probe
    # follows because it measures what those two branches act on, and `--tie`
    # follows the probe because it is the question a positive probe raises.
    "line-assignment-probe": (
        "no acpp in your toolchain? reflow the divergent statements onto their "
        "own source lines - token-identical, newlines only - and rebuild; same "
        "experiment, coarser dial.",
        "have IDO's acpp? acpp <defines> file.c > file.i && cc -c <flags> "
        "file.i, then diagnose again against the new listing.",
        "measure it instead of guessing: decomp-workbench probe-lines UNIT.i "
        "--compile-command '... {input} -o {output}' --target-object TARGET.o "
        "compiles that reflow and a mandatory control, and scores both against "
        "the target.",
        "already know line assignment owns it, and need to know WHICH line a "
        "statement wants? probe-lines ... --tie STATEMENT=LINE (repeatable) "
        "scores that one reassignment toward and away from the target.",
        "swept the line numbers and the one you need is unreachable one "
        "statement per line? that is lever 25: cfe numbers by LOGICAL line, so "
        "splicing a block onto the next statement (trailing `\\`) ties them to "
        "one number - and the plateau you measured is scoped to the statement "
        "order you swept.",
    ),
    # Source levers first, trace last: that is the documented order of work,
    # and a footer that led with instrumentation taught the opposite to every
    # reader who has none. `forced-color-oracle` is the deliberate exception -
    # lever 19 is the point at which source search is genuinely over.
    "temp-fifo-phase": (
        "don't have an instrumented toolchain? levers 14-16 are pure source "
        "and are the first move; the lane rotation above already locates the "
        "preceding block to perturb.",
        "have one, and those levers are spent? decomp-workbench trace-fifo "
        "TRACE.log replays the pool get/put schedule.",
    ),
    "pool-position": (
        "don't have an instrumented toolchain? levers 7-13 are all "
        "source-only and are the first move; read lever 9 before building any "
        "search - it is a dial, not a permutation.",
        "reweighted everything and the value still loses the register? the "
        "register may be TAKEN rather than underpriced - a `decision=split` "
        "with `regsleft` exhausted, or a `force_declined` on a callee-saved "
        "color. That is lever 28: alias the memory half (`if (&local);`) so "
        "the local leaves web candidacy and frees the slot.",
        "have one, and those levers are spent? "
        "docs/compiler-instrumentation.md, then "
        "decomp-workbench instrument-uopt-globalcolor and "
        "decomp-workbench trace-globalcolor TRACE.log --proc N.",
    ),
    "forced-color-oracle": (
        "have an instrumented toolchain? docs/compiler-instrumentation.md, "
        "then decomp-workbench diagnose ... --emit-force-spec force.json and "
        "decomp-workbench oracle plan TRACE.log to build the two-phase grid.",
        "a one-bijection assembly residue is one downstream outcome, not proof "
        "of one source web; use forbidden-color producers to count the blockers.",
        "don't have one? first inspect the residue for an actual move/copy "
        "site. If one exists, levers 17 and 18 are one variant each. If the "
        "residue is only a register bijection with no copy-shaped site, skip "
        "both and go directly to lever 19; a clean forced-color cascade is a "
        "legitimate stopping point - record it, bundle the scratch, take the "
        "next function.",
        "when source variants plateau, use campaign --show-basins; hundreds "
        "of spellings collapsing to a few objects is a negative result, not "
        "a reason to keep permuting declarations.",
    ),
    "stack-frame-recovery": (
        "compare the allocator-exact candidate against one-local ablations; "
        "keep both normalized residue and candidate_frame_size in the ledger.",
        "if narrower and register-qualified types plateau, reuse existing "
        "locals or split one source local into staggered webs at the same CFG "
        "boundaries instead of adding another stack home.",
    ),
    "post-match-cleanup": (
        "start with decomp-workbench experiment inspect-source exact.c; its "
        "findings are syntactic candidates, not declarations of dead code.",
        "encode related deletions/substitutions as one mechanism each, then "
        "use experiment compose with an explicit order and candidate cap.",
        "compile with --no-stop-on-exact and finish with object collateral; "
        "a function-only zero can still add BSS or linker metadata.",
    ),
    "relocation-only": (
        "prove the spellings are linked-address equivalent: "
        "decomp-workbench relocation-aliases TARGET.o CANDIDATE.o",
    ),
    "frontend-lineage": (
        "fingerprint the frontends before porting anything: "
        "docs/alternate-frontends.md, then "
        "decomp-workbench fingerprint-toolchain to compare the microcases.",
        "this family is reached by evidence, not by a verdict - a dispatch "
        "shape the project compiler cannot emit, or a residual hundreds of "
        "spellings never move.",
    ),
}


#: Where a playbook name promises more precision than the verdict has.
#:
#: `pool-position` is the catch-all for a register residual with no consistent
#: permutation and no lane rotation, and the guidance under it names three
#: undifferentiated families. Renaming the tag would contradict the field
#: guide's own cross-references (levers 7 and 11 print "Points here:
#: playbook=pool-position"), so the honest fix is to say so where the reader
#: opens it rather than to invent a tidier label.
PLAYBOOK_CAVEATS: dict[str, str] = {
    "pool-position": (
        "This is one of three unresolved allocation families - temp-FIFO "
        "phase, pool position, or coalescing. `view`'s footer says which one "
        "the lanes support; the levers below cover the pool family, and "
        "levers 14-16 and 17-18 cover the other two."
    ),
}


#: Playbooks whose verdict does not actually choose a lever family.
#:
#: `pool-position` is the tag for "register-only, no rotation, no bijection",
#: which is three families wearing one name. Printing its seven levers there
#: was a guess dressed as a finding: on both shipped register fixtures `view`
#: calls the residual `phase-shift` or `register-permutation`, whose levers are
#: 14-16 and 17-19. Worse, the guess contradicted the sentence directly above
#: it, which tells the reader to run `view` because *it* names the family.
#:
#: So this verdict names all three and picks none. `guide <playbook>` still
#: prints a family's levers in full -- once the reader has chosen one.
AMBIGUOUS_PLAYBOOK_FAMILIES: dict[str, tuple[tuple[str, str], ...]] = {
    "pool-position": (
        ("temp-fifo-phase", "temp-FIFO phase - ugen's block-local queue"),
        ("pool-position", "pool position - uopt's coloring order"),
        ("forced-color-oracle", "coalescing and callee-saved tie-breaks"),
    ),
}

#: The instrumentation branch for a verdict that has not chosen a family.
#:
#: `pool-position`'s own branch names levers 7-13, which is the same
#: over-commitment in a different sentence, so the neutral block gets a neutral
#: pair.
AMBIGUOUS_ONRAMPS: tuple[str, ...] = (
    "don't have an instrumented toolchain? every lever in all three families "
    "is source-only except lever 19 - start with the one `view` names, none "
    "of them need a trace.",
    "have one? it is still the last step: docs/compiler-instrumentation.md, "
    "then decomp-workbench instrument-uopt-globalcolor and "
    "decomp-workbench trace-globalcolor TRACE.log --proc N.",
    # Gated on trace evidence, not on the verdict: this block deliberately
    # does not choose a family, and this line does not either - it names a
    # symptom the reader either sees in a trace or does not.
    "the trace shows your web `decision=split` with `regsleft` exhausted, or "
    "a `force_declined` on a callee-saved color? then the register is taken, "
    "not underpriced, and no reweighting lever can win it: decomp-workbench "
    "guide 28.",
)

#: What `compare` must say before any of the three, because `compare` sees
#: less than `view` does and should not sound like it saw more.
COARSE_ALLOCATION_LEAD_IN = (
    "(compare cannot see which of the three it is - run `view` first to "
    "confirm the family before spending a variant.)"
)


def next_steps(playbook: str, *, lead_in: Sequence[str] = ()) -> tuple[str, ...]:
    """Return the on-ramp lines appended to one verdict's guidance.

    Pure data by design. `diagnose` must produce the same footer on a machine
    with no documentation installed as on the maintainer's checkout, so nothing
    here reads the guide; the block ends with the command that does.

    `lead_in` lets the caller say what *its* evidence could not settle, so a
    coarse verdict never borrows a precise one's confidence.
    """

    lines: list[str] = list(lead_in)
    families = AMBIGUOUS_PLAYBOOK_FAMILIES.get(playbook)
    if families is not None:
        lines.append(
            "field guide: this residual is one of three allocation families "
            "and this verdict cannot choose between them:"
        )
        lines.extend(
            f"  {label}: decomp-workbench guide {name}" for name, label in families
        )
        lines.extend(AMBIGUOUS_ONRAMPS)
        return tuple(lines)
    levers = PLAYBOOK_LEVERS.get(playbook, ())
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
            "Worked end to end: docs/from-verdict-to-edit.md",
        )
    )
    return lines


def _lever_lines(number: int, available: dict[int, GuideSection]) -> Iterable[str]:
    """Render one lever, degrading to its one-liner when the section is absent.

    Every lever this table names ships with a section today. The path is kept
    because it has already been needed once -- levers 20-22 were numbered and
    actionable here while their prose was still on another branch -- and
    because an installation carrying an older mirror than its code is exactly
    the case where "the guide is missing that part" must not become a crash.
    """

    section = available.get(number)
    if section is None:
        yield f"### {number}. (not in the shipped field guide)"
        yield ""
        yield LEVER_ACTIONS[number]
        yield ""
        yield (
            "This lever's section is not in this installation's "
            f"{GUIDE_DOCUMENT}, which is older than this command. The "
            "one-line action above is complete on its own."
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
    caveat = PLAYBOOK_CAVEATS.get(topic.playbook or "")
    if caveat is not None:
        lines.extend(("", caveat))
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
