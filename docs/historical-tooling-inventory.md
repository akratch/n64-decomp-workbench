# Historical tooling inventory

This is the extraction ledger for the DKR final-function research. It records
what was built, what was promoted into the supported workbench, and what
remains a project-specific experiment in the preserved archive.

The inventory is intentionally broader than the command list. “Archive” means
the mechanism or evidence is retained on
[`archive/decomp-research-2026-07-26`](https://github.com/akratch/Diddy-Kong-Racing/tree/archive/decomp-research-2026-07-26),
not that its original hard-coded script is a portable API. “External gate”
means the workbench documents the check but cannot ship the required game or
compiler input.

## Comparison and search

1. **Relocation-aware full-word oracle — packaged.** GNU objdump instruction
   and relocation records are parsed together. Only fields controlled by
   known MIPS relocation types are masked; unknown types prevent an exact
   result. Raw and relocation-aware word counts are both retained.
2. **Redistributable dump oracle — packaged.** `compare-dumps` runs the same
   structural comparison on retained objdump text, allowing fixtures and bug
   reports without sharing target objects.
3. **Normalized topology score — packaged.** Opcode structure is compared
   separately from physical register choices, keeping a correct instruction
   graph visible when register allocation is the remaining problem.
4. **Register-class penalties — packaged.** Integer-register and
   floating-point-register mismatches are independent metrics with localized
   ranges. This preserves promising candidates that a single scalar score can
   bury.
5. **Frame, instruction-count, and stream identity metadata — packaged.**
   Candidate reports retain frame size, instruction count, raw instruction
   hashes, and detailed diffs rather than only “best score.”
6. **Parallel source campaigns — packaged.** `campaign` compiles candidates in
   parallel, deduplicates repeated prepared invocations, caches objects, keeps
   optional outputs, and records an append-only JSONL ledger. Source paths
   remain in keys because wrappers and debug metadata may be path-sensitive.
7. **Campaign provenance — packaged.** Cache keys include target and source
   hashes, compiler command, wrapper identity, selected section, symbol,
   objdump, and explicit environment. This replaces unreproducible numbered
   scratch directories.
8. **Family generators and basin dashboards — archive.** Hundreds of
   target-specific generators explored declaration order, expression
   topology, fake pressure, lifetimes, call spans, loop shapes, constants,
   and statement boundaries. Their reusable execution layer became
   `campaign`; the DKR templates remain audit material.
9. **Within-basin deduplication and promotion — archive.** Research scripts
   grouped objects by structural signature, retained distinct outcomes, and
   promoted the best natural candidates. Content caching and stable ordering
   are packaged; source-specific promotion policies are not.
10. **Whole-translation-unit collateral scoring — external gate.** Menu
    experiments compared every function in the translation unit after a
    compiler intervention. The need for this gate is documented, but its
    inputs are project-owned and not redistributable.
11. **Whole-ROM verification — external gate.** A function-level zero was only
    accepted after the normal project verification and retail image hash.
    Workbench output deliberately does not claim to replace this step.

## Compiler pipeline diagnostics

12. **Retained ugen→as1 listing replay — packaged.** `replay-as1` edits a
    uniquely matched listing site and reruns caller-supplied as0/as1 commands
    without a shell. This isolates pass-boundary causality while retaining the
    exact mutated listing.
13. **Pass-binary Cartesian matrices — archive.** cfe, uopt, ugen, and as1
    revisions were mixed to attribute invariant and variant output. The
    matrix reports, binary identities, blocked cells, and path-related
    `.mdebug` pitfall remain archived; shipping proprietary pass binaries is
    out of scope.
14. **Native-vs-static-recompile differential — archive.** Original IRIX
    passes were run under qemu-irix and compared with static recompilations to
    test whether suspected behavior was a recompiler artifact. The runner is
    environment-specific; the fidelity pattern is retained as a recipe.
15. **Compiler-option enumeration — archive.** Pass option tables and driver
    routing were enumerated from binary evidence before sweeping flags. This
    ruled out guessed toggles more efficiently than ad hoc option changes.
16. **Microcase reduction — documented pattern.** Minimal sources were used
    as positive controls for collapse, alias, coloring, and scheduling paths.
    They established that a hook fired before it was trusted on a large
    translation unit.

## uopt instrumentation

17. **Globalcolor live-range capture — packaged.** `CSAVE` and `CUP` parsers
    retain live-range fields and per-color costs and rank the historical
    `adjusted_save × weight` metric without claiming universal field
    semantics.
18. **Globalcolor decision trace — packaged.** The hash-pinned IDO 5.3 profile
    records procedure ordinal, web, class, save, best cost/color, and
    split/color decision in structured `[CDX]` records.
19. **Forced color/split causal oracle — packaged diagnostic control.**
    `CDX_FORCE` can test whether one allocation decision is sufficient for an
    observed residual. Forced output is labeled diagnostic and is never
    presented as a source match.
20. **Base-provenance trace — packaged.** The pinned alias profile records
    fresh/direct/retained base paths with register and descriptor fields.
21. **Alias-query trace — packaged.** The same profile records both
    descriptors and the observed may-alias/no-alias outcome.
22. **Alias-state report — packaged.** `trace-alias` aggregates paths, types,
    outcomes, and registers while retaining query-level JSON.
23. **Alias-grant causal probes — archive only.** Environment-gated
    interventions tested whether a selected disjointness result was sufficient
    and then measured collateral. They were intentionally not promoted: a
    query fingerprint that reproduces one object is not a general alias rule.
24. **Combined profile composition — packaged.** `instrument-uopt` validates
    one pristine generated-source hash and applies alias and globalcolor
    profiles in a deterministic order.

## ugen and allocator instrumentation

25. **Broad function call tracing — packaged locator.** `instrument-ugen`
    adds opt-in entry/exit frames to selected generated `f_*` functions. It is
    useful for differential localization, but does not pretend generated C is
    stable across compiler versions.
26. **Free-list hook locator — packaged.** Known allocation and free-list
    helper entries receive structured events where compatible anchors exist.
27. **Deep temp-register trace — parser packaged, producer archived.** The DKR
    profile captured queue state, allocation serial, node identity, source
    line, destination hint, and exact append/remove activity. The generic
    parser accepts its `CODEX-*` events; the large IDO-build-specific patch is
    preserved rather than advertised as portable.
28. **FIFO validation — packaged.** `trace-fifo` reconstructs the initial
    queue, verifies every allocation against its head, detects double/free
    errors, and reports final state.
29. **Physical-to-logical event conversion — packaged.** Reused physical
    registers become stable logical values, exposing the actual
    allocate/free schedule that source evaluation order must explain.
30. **Event-window and schedule solvers — partially packaged.** The reusable
    strict replay and JSON event schedule are supported. DKR-specific
    permutation, region, and source-line window solvers remain archived
    because their constraints name one function's statements.
31. **Destination-hint/collapse causal probe — archive only.** A guarded ugen
    intervention showed that withholding a destination hint was sufficient to
    route a load through the temp pool. Its narrow site gates and generated-C
    addresses are evidence, not a portable compiler feature.

## Robustness and forensic diagnostics

32. **Instrumentation-off fidelity controls — documented requirement.** Every
    compiler profile must be compared with stock output while disabled,
    checked on a positive microcase, measured on collateral, and followed by
    the project's full verification.
33. **Guest heap/stack memory poisoning — archive.** Deterministic byte
    patterns and seeded random patterns tested whether code generation
    depended on uninitialized emulated memory. Source-path metadata was
    separated from `.text` before interpreting differences.
34. **Static-recompiler conservative-liveness comparison — archive.**
    Conservative and non-conservative generated passes were compared to
    distinguish host register-liveness accommodations from guest-memory
    behavior.
35. **ROM and corpus idiom scanners — archive.** A small MIPS decoder, raw ROM
    scanner, disassembly scanner, and matched-function filters measured how
    often suspected instruction shapes occurred in DKR and other available
    Rare corpora.
36. **Cross-game/compiler provenance checks — archive.** Compiler binary
    hashes, other Rare projects, available original executables, and matching
    functions were compared before inferring a DKR-specific compiler quirk.
37. **Source-path artifact checks — documented lesson.** ELF/debug metadata
    can differ when temp paths differ while `.text` remains identical.
    Comparison therefore targets the requested section and reports content
    relevant to code generation separately.
38. **Negative-result ledgers and falsifiable closure notes — archive.**
    Reports preserve tested families, controls, counterexamples, withdrawn
    claims, and precise reopen criteria. They are useful audit evidence; the
    reusable conclusions are summarized separately as
    [campaign lessons](lessons-learned.md).

## Extraction policy

A historical tool was promoted when its input contract could be stated
without DKR paths or proprietary artifacts, its output could be tested with a
small redistributable fixture, and its claims could be bounded. Everything
else remains indexed in the raw branch. This keeps the supported surface small
without erasing the investigation that produced it.
