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
    "LAW_DOCUMENTS",
    "LAW_ERA_ALIASES",
    "LEVER_ACTIONS",
    "PLAYBOOK_LAWS",
    "PLAYBOOK_LEVERS",
    "VERDICT_PLAYBOOKS",
    "GuideSection",
    "Law",
    "Topic",
    "law_citation",
    "law_eras",
    "law_index_lines",
    "law_steps",
    "laws",
    "next_steps",
    "normalize_era",
    "normalize_law",
    "parse_laws",
    "read_field_guide",
    "read_law",
    "read_laws",
    "render_law",
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

#: Compiler-mechanism documents, keyed by the era token `guide laws` takes.
#:
#: These are a different kind of knowledge from the levers. A lever says what
#: to change; a law says what the compiler will do about it, with the evidence
#: that established it and the earlier claim it corrected. They were filed as
#: "workbench improvements" for a whole campaign because there was nowhere
#: else to put them, which is how twenty-six of them came to be lost.
#:
#: Era-scoped by construction: nothing measured on one IDO release may be
#: printed under another's name, so the era token is part of the address.
LAW_DOCUMENTS: dict[str, tuple[str, str]] = {
    "ido53": ("docs/compiler-laws/ido-5.3.md", "IDO 5.3"),
    "ido71": ("docs/compiler-laws/ido-7.1.md", "IDO 7.1"),
}

#: Era spellings a reader is likely to type, mapped onto the canonical token.
#:
#: The pages are named `ido-5.3.md` and `ido-7.1.md`, campaign notes say
#: "IDO 7.1", and the token is `ido71`; a reader who types any of those is
#: asking one question and must not be told the era does not exist. Punctuation
#: and spacing are normalised away rather than enumerated, so `ido 7.1`,
#: `IDO-7.1` and `7.1` all land on the same page.
LAW_ERA_ALIASES: dict[str, str] = {
    "53": "ido53",
    "71": "ido71",
}

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
        "only with a copy-shaped residue OR check-scratch's measured late "
        "v0/v1 call-return occupancy hypothesis: test one explicit `int`/K&R "
        "return-category variant at the declaration and definition"
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
        "preprocess the TU with IDO's acpp using the project's exact defines "
        "and include paths, then compile the .i with the project's exact "
        "flags: uopt/ugen honor statement line boundaries even at -g0"
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
    29: (
        "when one web wants the neighbouring argument register, stop pricing "
        "it and make the wrong register illegal: give the value a live range "
        "across a call that pins that register, which seeds the web's "
        "forbidden set from the hard-register conflict vector -- zero "
        "instructions, and the forbid follows the whole web, so split the "
        "roles onto two symbols if one carrier holds two"
    ),
    30: (
        "spell a value-position `a && b` the way cfe expands it -- "
        "`v = (a); if (v) { v = (b); }` -- which is byte-identical to the "
        "operator, where `v = 0; if (a && b) v = 1;`, if/else and branch-free "
        "forms cost hundreds of rows"
    ),
    31: (
        "buy a registerizable local out of an array whose base alone is "
        "addressed: shrink the array and declare the new local so the base "
        "keeps its offset, and every other home, the block length and the "
        "frame stay exactly as they were"
    ),
    32: (
        "when the residue is one repeated stack-home addend against a "
        "compiler temp's slot, empty cfe's expression-temp pool: it is one "
        "value-numbered symbol that re-mints, so enumerate its "
        "materialisation classes (call-as-non-final-argument, `&&` as a "
        "value, ternaries) and kill them in one build, and spend what it "
        "releases on a local"
    ),
    33: (
        "fold the two statements onto one physical line so their instructions "
        "tie on `lineno` and ready-list position decides -- as1's scheduler "
        "reads source line numbers, and `cc -Wa,-R` prints the selection "
        "records byte-inert"
    ),
    34: (
        "IDO 7.1: one register wrong on a fallthrough after a copy is as1's "
        "peep_reg -- write `if (x && x && x);` before the dispatch, because "
        "ugen erases one and two conditional branch-to-nexts and four is "
        "catastrophic, but the third survives to kill the copy fact and is "
        "then deleted at zero instruction cost"
    ),
    35: (
        "IDO 7.1: `if (c) goto high; goto low; high:;` makes the goto TARGET "
        "the fallthrough and inverts the branch -- that parity decides which "
        "dispatch block inherits as1's copy facts; polarity spellings "
        "(`>= N`, `> N-1`, `!(x < N)`) are byte-identical, so do not sweep them"
    ),
    36: (
        "IDO 7.1: when a zero-code barrier flips the range branch's sense and "
        "swaps the dispatch clusters, put the SAME statement on the opposing "
        "arm; the ballast restores parity and keeps the register heal, and "
        "one/two/three copies are byte-identical"
    ),
    37: (
        "IDO 7.1: jump-table bodies packed behind their own table are uopt's "
        "`num + 1` depth-first order -- nest the second switch inside the "
        "first one's body and enter it by `goto`; cheaper first tries are an "
        "empty `if (x);` on the FIRST case trampoline or on an explicit "
        "`default: goto low;` (one or two references, never three)"
    ),
    38: (
        "IDO 7.1: an exact allocation with stack homes off by a constant is a "
        "selector-temp residual, not a colouring one -- write "
        "`switch (x ? x : x)`, which moved two temp homes 4 bytes inside an "
        "unchanged frame with identical instructions, opcodes and registers"
    ),
    39: (
        "IDO 7.1: read count is arithmetic, not a search -- priority = "
        "save/units with units quantized from raw = refs + cardbits, +10 save "
        "per ref with no branch-nesting discount, +1 cardbit per spanning "
        "statement, and an empty-body `if` folds AFTER compute_save; three "
        "refs in ONE statement is the step, four collapses codegen"
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
    # Lever 33 sits after 25 for the same reason 25 sits after 23: it is the
    # move for a tie 25's splice cannot express, because the deciding key is
    # read by the assembler's scheduler rather than by cfe.
    "line-assignment-probe": (23, 25, 33, 4),
    "structure-buckets": (1, 4, 24, 5, 6),
    "temp-fifo-phase": (14, 15, 16),
    # Levers 29 and 30 close the family: when the register is not underpriced
    # but forbidden-adjacent, the reachable move is liveness (29), and 30 is
    # the free spelling most carrier edits need to get there.
    # Lever 39 leads on IDO 7.1 and is inert elsewhere, which is why it sits
    # first rather than last: it turns the read-count search the rest of this
    # family describes into arithmetic, and a reader who spends 7-13 without it
    # is sweeping a step function as though it were a slope.
    "pool-position": (39, 7, 8, 9, 10, 11, 12, 13, 28, 29, 30),
    "forced-color-oracle": (17, 18, 19),
    # A full frame is a frame-layout problem even when the frame size is
    # already exact: 31 buys the symbol, 32 buys the slot. Lever 38 comes last
    # because it is era-scoped -- on IDO 7.1 with a switch in the residual it
    # is the cheapest member of the family (it moves temp homes with no codegen
    # collateral at all), and everywhere else it is inert.
    "stack-frame-recovery": (26, 31, 32, 38),
    # The two IDO 7.1 dispatch families. They share every lever and differ in
    # which one leads, because the residual you can see says which mechanism
    # you are missing: a wrong register on a fallthrough is a copy fact, a
    # wrong block order is a traversal. Both end at 38, which is what is left
    # once the first two are right.
    "copy-propagation-barrier": (34, 35, 36, 38),
    "dispatch-layout": (37, 35, 36, 34),
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
        "have IDO's acpp? follow docs/line-assignment-probe.md's array-safe "
        "recipe with the translation unit's exact defines, includes, and "
        "compiler flags, then diagnose again against the new listing.",
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
        "the register at a site is a pure function of the alloc/free event "
        "sequence before it (ugen pops the head of a per-class free list and "
        "frees to its tail - a least-recently-freed ring, re-seeded once per "
        "procedure). So do not chase the phase: chase the CLASS-CROSSING "
        "sites, where one side leaves as a ugen temp what the other colored. "
        "Each one re-phases everything downstream.",
        "score on the site count, not on raw words: partial closure is not "
        "monotone (a recorded run went 1416 -> 1413 -> 1445 -> 1477 -> 572 as "
        "sites closed). Confirm on words only at full closure.",
        "which registers are temps at all is per-compiler-era data. Under IDO "
        "5.3 -O2 -mips2 (probed) t0-t9 and f4/f6/f8/f10 are ALWAYS ugen "
        "temps and never uopt colors; other releases are unverified. "
        "decomp-workbench guide temp-fifo-phase carries the table.",
        "the float ring is FOUR wide. ugen's ffree initializer also lists "
        "f16/f18, but both are withdrawn before the first allocation and "
        "never handed out (1460/1460 measured in f4-f10); they are uopt "
        "colors. A float-site metric that counts them as temps reports "
        "closures that are really coloring changes.",
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
        "site, or run check-scratch --view with a project object to test the "
        "strict late v0/v1 call-return occupancy shape. If either gate fires, "
        "lever 17 is one variant; lever 18 still requires a visible copy and "
        "repeated source expression. Otherwise go directly to lever 19; a "
        "clean forced-color cascade is a legitimate stopping point for HAND "
        "search - and hand search is not the whole search: run "
        "permute-doctor and a sweep before recording a wall, then bundle the "
        "scratch and take the next function.",
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
    # Both 7.1 dispatch families lead with the phase boundary, not with a
    # source lever, because that is the order that worked: the barrier below
    # was proven words=0 by patching a captured stream a full session before
    # any C spelling produced it, and three earlier barrier families were
    # killed the same way for the price of one patched stream each.
    "copy-propagation-barrier": (
        "these levers are IDO 7.1 only - the same Binasm through 5.3's as1 "
        "produces a 321-word object, so do not port them to a 5.3 project.",
        "prove it at the phase boundary first: decomp-workbench pass binasm "
        "on the captured ugen-to-as1 stream shows whether your copy fact "
        "reaches the divergent block at all, and as1's own -peepdbg prints "
        "the rewrite (`Peepreg (INST n) changed rs A => B`, n is BLOCK-local).",
        "the mechanism is update_ctnt: a content fact reaches the next block "
        "only through a single-predecessor fallthrough, and is then filtered "
        "against the taken target's live-in mask. Three ways to win - put the "
        "alias source in that mask, redefine it before the use, or fail the "
        "single-predecessor gate. decomp-workbench guide laws ido71 L2.",
        "score candidates on their pre-as1 Binasm, not on the object: as1 "
        "mutates its content state BEFORE it deletes redundant code, so the "
        "instruction you need may be invisible in the final text.",
    ),
    "dispatch-layout": (
        "these levers are IDO 7.1 only, and they are layout: run "
        "decomp-workbench align first - `words` over-charges a moved block "
        "(1,791 words for a one-block edit script, measured), so rank "
        "permutation candidates on the edit script, never on the scalar.",
        "the predicate is uopt's depth_first_order: it always takes the "
        "successor whose original lexical number is node->num + 1. Placement "
        "follows that literally - 'first' and 'middle' move the layout, "
        "'last' is inert. decomp-workbench guide laws ido71 L8.",
        "prove levers in isolation and compose late: on the function these "
        "came from, the layout alone was 9 words, the layout plus an "
        "unballasted barrier 13, the selector without the ballast 5, the "
        "ballast without the selector 8 - and all four together 0. A lever "
        "that does not improve the score is a component, not a refutation.",
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


#: The compiler law behind a lever family, keyed by playbook.
#:
#: A lever says what to change; the law says what the compiler will do about
#: it, and a reader who has only the lever re-derives the law the hard way --
#: which is exactly what a whole campaign did before contributing L62-L70. So
#: every footer that names a family also names the law that family rests on,
#: as a command that prints it.
#:
#: Each entry is `(era, law, one line)`. The era is part of the address on
#: purpose: nothing measured on one IDO release may be quoted under another's
#: name, and two of these families have laws on both pages.
PLAYBOOK_LAWS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "ast-shape": (
        (
            "ido53",
            "L67",
            "a comparison prints its copy-propagated variable first, so "
            "operand order is a readout of the carrier and not a lever",
        ),
    ),
    "constant-audit": (
        (
            "ido53",
            "L62",
            "a float scalar takes the rodata lwc1 form iff its low halfword "
            "is non-zero, and only that form joins the invariant-load group",
        ),
    ),
    "g0-schedule-probe": (
        (
            "ido53",
            "L62",
            "a schedule difference around one float constant is a load-form "
            "difference: low halfword zero means a statement load, never an "
            "invariant one",
        ),
        (
            "ido53",
            "L70",
            "measure on the project path, never on an isolated cc -c: the "
            "same source compiled 56 instructions one way and 58 the other",
        ),
    ),
    "pool-position": (
        (
            "ido53",
            "L66",
            "a web feeding a call argument inherits that argument register "
            "at cost 0, so a redundant-looking re-cache is what rides it",
        ),
    ),
    "stack-frame-recovery": (
        (
            "ido53",
            "L63",
            "declared locals take descending stack homes in declaration "
            "order, so a declaration reorder places a call-crossing spill",
        ),
    ),
    "structure-buckets": (
        (
            "ido53",
            "L68",
            "a compiler-owned jump table's bytes are the case mapping; "
            "matching .text is not evidence that the mapping is right",
        ),
    ),
    "temp-fifo-phase": (
        (
            "ido53",
            "L64",
            "the integer ring is seeded t6 t7 t8 t9 t0..t5, so a one-pop "
            "phase error rotates by that order and not by register number",
        ),
        (
            "ido53",
            "L65",
            "a folded redundant mask emits no instruction and still pops the "
            "ring once -- the phantom pop, and it works in both directions",
        ),
    ),
}


def law_citation(era: str, law: str, summary: str) -> str:
    """Return one footer line pointing a residual at the law under it."""

    return f"law {law}: {summary} -- decomp-workbench guide laws {era} {law}"


def law_steps(playbook: str) -> tuple[str, ...]:
    """Return the law citations one playbook's footer owes its reader."""

    return tuple(
        law_citation(era, law, summary)
        for era, law, summary in PLAYBOOK_LAWS.get(playbook, ())
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
        lines.extend(law_steps(playbook))
        return tuple(lines)
    levers = PLAYBOOK_LEVERS.get(playbook, ())
    if levers:
        lines.append(f"field guide levers for playbook={playbook}:")
        lines.extend(f"  lever {number}: {LEVER_ACTIONS[number]}" for number in levers)
        lines.append(f"read them: decomp-workbench guide {playbook}")
    lines.extend(PLAYBOOK_ONRAMPS.get(playbook, ()))
    # Last of the family's own lines: the levers are what to try, and this is
    # the mechanism they rest on. A reader who never learns the law exists
    # re-derives it, which is how L62-L70 came to be measured twice.
    lines.extend(law_steps(playbook))
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


def law_eras() -> tuple[str, ...]:
    """Return the era tokens `guide laws` accepts."""

    return tuple(sorted(LAW_DOCUMENTS))


def normalize_era(era: str) -> str:
    """Return the canonical era token for one of its spellings.

    The document, the campaign prose and the token disagree on punctuation
    (`ido-7.1.md`, "IDO 7.1", `ido71`), and all three are things a reader
    types. Stripping the separators and folding case makes them one address;
    an unrecognised spelling is returned as-is so the caller raises the error
    that names the eras that ship.
    """

    token = "".join(
        character for character in era.strip().casefold() if character.isalnum()
    )
    return LAW_ERA_ALIASES.get(token, token)


def read_laws(era: str) -> str:
    """Return one era's compiler-laws document.

    Read from the packaged mirror, like the field guide, so an installed
    wheel can print it with no checkout. An unknown era is an error naming
    the ones that exist rather than a silent empty page: a laws document that
    prints nothing reads as "this compiler has no known laws".
    """

    token = normalize_era(era)
    entry = LAW_DOCUMENTS.get(token)
    if entry is None:
        known = ", ".join(law_eras())
        raise ValueError(
            f"unknown compiler era {era!r}; this package carries laws for: {known}"
        )
    document, _label = entry
    resource = resources.files(__package__ or "decomp_workbench")
    for part in document.split("/"):
        resource = resource.joinpath(part)
    try:
        return resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as error:
        raise FileNotFoundError(
            f"the {token} compiler-laws document is not installed with this "
            f"package ({document}); read it at {document} in a checkout, or "
            "at https://github.com/akratch/n64-decomp-workbench/blob/main/"
            f"{document}"
        ) from error


#: Every `### Ln. Title` law heading, and the `## Pass` heading above it.
LAW_HEADING_RE = re.compile(r"^###\s+(L\d+)\.\s+(.+?)\s*$")


@dataclass(frozen=True)
class Law:
    """One numbered law, with the pass heading it sits under."""

    name: str
    title: str
    section: str
    lines: tuple[str, ...]


def normalize_law(law: str) -> str:
    """Return the canonical `Ln` spelling for one of its spellings.

    A reader types what the footer printed (`L64`), what a note said
    (`law 64`), or just the number. All three name one law, and refusing two
    of them would make the citation in a footer a thing you have to translate
    before you can paste it.
    """

    token = law.strip().casefold().removeprefix("law").strip()
    token = token.removeprefix("l")
    return f"L{token}" if token.isdigit() else law.strip()


def parse_laws(text: str) -> dict[str, Law]:
    """Split a laws document into its `### Ln. Title` sections.

    Keyed on the number, like the field guide's levers, because the number is
    the address every footer and cross-reference cites; heading text is free
    to be edited.
    """

    found: dict[str, Law] = {}
    section = ""
    name: str | None = None
    title = ""
    body: list[str] = []

    def flush() -> None:
        if name is None:
            return
        kept = list(body)
        while kept and kept[-1].strip() in {"", "---"}:
            kept.pop()
        found[name] = Law(name=name, title=title, section=section, lines=tuple(kept))

    for line in text.splitlines():
        heading = LAW_HEADING_RE.match(line)
        if heading is not None:
            flush()
            name, title = heading.group(1), heading.group(2)
            body = [line]
            continue
        family = FAMILY_RE.match(line)
        if family is not None:
            flush()
            name, body = None, []
            section = family.group(1)
            continue
        if name is not None:
            body.append(line)
    flush()
    return found


def laws(era: str) -> dict[str, Law]:
    """Return one era's parsed laws, keyed by `Ln`."""

    return parse_laws(read_laws(era))


def read_law(era: str, law: str) -> Law:
    """Return one law of one era.

    An unknown number names the range that exists rather than printing the
    whole page: a reader who mistyped a citation wants to know the citation
    was wrong, not to scroll a document looking for it.
    """

    available = laws(era)
    name = normalize_law(law)
    found = available.get(name)
    if found is None:
        numbers = sorted(int(item[1:]) for item in available)
        span = f"L{numbers[0]}-L{numbers[-1]}" if numbers else "none"
        raise ValueError(
            f"unknown law {law!r} for era {normalize_era(era)}; "
            f"that page carries {span}"
        )
    return found


def render_law(era: str, law: Law) -> list[str]:
    """Return the printable form of one law, with its address and its page."""

    document, label = LAW_DOCUMENTS[normalize_era(era)]
    lines = [
        f"COMPILER LAWS  {label}  {law.name}",
        f"source: {document}" + (f"  [{law.section}]" if law.section else ""),
        "",
    ]
    lines.extend(law.lines)
    lines.extend(
        (
            "",
            "-" * 72,
            "",
            "NEXT",
            f"  the whole page: decomp-workbench guide laws {normalize_era(era)}",
            "  what to change about it: decomp-workbench guide",
        )
    )
    return lines


def law_index_lines() -> list[str]:
    """Return the listing printed by `guide laws` with no era."""

    lines = [
        "Compiler laws: what the compiler does, as opposed to what to do about it.",
        "",
        "eras",
    ]
    width = max(len(token) for token in LAW_DOCUMENTS)
    for token, (document, label) in sorted(LAW_DOCUMENTS.items()):
        lines.append(f"  {token.ljust(width)}  {label}  ({document})")
    lines.extend(
        (
            "",
            "Example: decomp-workbench guide laws ido53",
            "One law: decomp-workbench guide laws ido53 L64",
            "Levers, as opposed to mechanism: decomp-workbench guide",
        )
    )
    return lines


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
            # Different in kind from everything above: levers say what to
            # change, laws say what the compiler does about it. A reader who
            # never learns the second exists will keep re-deriving it.
            "Compiler mechanism, not levers: decomp-workbench guide laws "
            f"({', '.join(law_eras())})",
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
