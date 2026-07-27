# Lessons that survived the campaign

These are the practices supported by the four completed DKR investigations.
Each statement is deliberately narrower than a rule about every IDO version or
every decompilation project.

1. **Use several oracles, and name which one is decisive.** Instruction count,
   opcode shape, normalized operands, register ranges, and native asm-differ
   penalties are useful search signals. Relocation-aware instruction words are
   the function-level completion test; the normal project build remains the
   integration test. The
   [`func_80017A18` investigation](../case-studies/objects-structural-score.md)
   got worse under one scalar score at the same moment that all insertion,
   deletion, and reorder penalties disappeared.

2. **Do not normalize away the feature currently under investigation.** A
   scorer that replaced every `N(sp)` operand with one token hid a whole-frame
   shift. Keep literal frame size, stack offsets, register classes, and raw
   words beside normalized structure.

3. **Separate compiler-pass ownership before changing source.** In the menu
   case, ugen already emitted the target register. The remaining difference was
   an as1 scheduling decision constrained by one missing `.noalias` fact. A
   retained ugen listing and as0/as1 replay located the responsible boundary;
   more temp-register experiments would not have answered it. See the
   [pass-replay case](../case-studies/menu-pass-replay.md).

4. **A register mismatch can be a live-range topology problem, not generic
   pressure.** The racer campaign did not make an existing web more profitable.
   Splitting one expression across two assignments created a different web
   spanning `sqrtf`, which recovered the target `f20/f21` allocation and
   248-byte frame. Measure which webs exist before adding dummy locals or
   guessed pressure.

5. **Physical register sequences are not allocation schedules.** Registers can
   be freed and reused before the trace window that first looks relevant.
   Reconstruct the allocator queue, validate every pop and append, and assign
   logical identities to values. That conversion exposed the statement order
   needed for the racer function's final 19 words.

6. **Force controls are causal oracles, not matches.** Forcing the target color,
   temp-register choice, or alias outcome can prove that one compiler decision
   is sufficient to explain a residual. It does not identify the historical
   source or justify shipping a modified compiler. Use the result to narrow the
   next ordinary-source experiment, then turn the control off.

7. **Source that emits no final instruction can still affect compiler state.**
   In `trackbg_render_flashy`, definitions removed before final assembly changed
   expression-table creation order and resolved an allocation tie. This is a
   measured explanation for that function, not permission to add arbitrary
   dead code: first identify the internal ordering or tie that the source must
   influence.

8. **Source provenance can survive into downstream scheduling.** In the menu
   function, direct indexing preserved a named-global base relationship that a
   pointer walk did not. Ugen then emitted the register-pair `.noalias` fact
   required by as1. The useful source distinction was not just address
   arithmetic; it was the alias descriptor passed between compiler stages.

9. **Generated-compiler instrumentation needs the same rigor as production
   code.** Pin the static-recompiler revision and generated-source hash, require
   unique anchors, default tracing off, keep behavior-changing controls
   separate, and test stock versus instrumented output with instrumentation
   disabled. A trace without a negative control is an observation from an
   uncalibrated instrument.

10. **Test the instrument on a microcase before trusting a large trace.** A
    positive control proves that the selected hook and trace field actually
    observe the intended event. Full translation units are poor places to
    discover that a filter, procedure ordinal, or generated-source anchor was
    wrong.

11. **Retain intermediate representations when the final diff is ambiguous.**
    Ucode, ugen listings, binasm, and final objects answer different questions.
    Comparing the earliest stage where candidates diverge is usually more
    informative than assigning every final difference to “the compiler.”

12. **Treat compiler-build and path differences as hypotheses with controls.**
    Mix pass binaries one axis at a time, compare original IRIX and static
    recompiles when possible, and distinguish `.text` changes from path-bearing
    ELF/debug metadata. A different object hash alone does not establish
    different code generation.

13. **Automated source search works best after measurement narrows the
    variable.** Deterministic generators are valuable for declaration order,
    expression topology, statement boundaries, and loop spelling, but broad
    Cartesian sweeps create many correlated variants. Record one transformation
    family at a time and keep all structurally distinct outcomes, not only the
    lowest scalar score.

14. **Preserve negative results and withdrawn conclusions.** Both the racer and
    menu investigations contained plausible “unreachable” arguments later
    falsified by a new source topology. A useful closure note states the tested
    scope, controls, counterexamples, and a concrete condition that would reopen
    the question.

15. **Function equality is not the final integration gate.** Compiler
    interventions can perturb collateral functions in the same translation
    unit. Recheck already-matching functions and the complete project output
    before accepting a result.

The [historical tooling inventory](historical-tooling-inventory.md) maps these
practices to the packaged commands, archived experiments, and external gates.
