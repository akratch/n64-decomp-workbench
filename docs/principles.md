# Principles

1. **Keep the exact oracle separate from search scores.** Normalized structure
   helps rank candidates; relocation-aware words decide function equality.
2. **Do not normalize away the feature under investigation.** Keep frame size,
   stack offsets, registers, instruction count, and raw words visible.
3. **Measure the owning pass.** Retain intermediates or trace the narrowest
   compiler stage before changing unrelated source.
4. **Treat force controls as causal probes.** A forced match identifies a
   decision worth explaining; it is not a source match.
5. **Calibrate instrumentation.** Tracing-off output must equal stock output,
   and a positive microcase must prove the hook fires.
6. **Make campaigns reproducible.** Record source, target, wrapper, objdump,
   explicit environment, outputs, and timing.
7. **Validate the complete project.** A function-level exact result does not
   replace collateral and final ROM or binary checks.
8. **Reproduce the real compilation envelope.** Translation-unit context,
   compiler working directory, explicit environment, and source-line markers
   are inputs. A reduced harness is a probe, not ground truth.
9. **Scope negative evidence to the probe.** A `-g0` collapse, forced color,
   or unchanged mutation rules one mechanism in or out under stated
   conditions; it does not prove source correctness or a universal wall.
10. **Own every process and every timeout.** A compiler wrapper's children are
    part of the command lifecycle. An interrupt, failure, or deadline must not
    leak work into the next campaign.
11. **Make examples and metadata trustworthy.** Pasted commands must run from
    the directory the page names, synthetic fixtures must state what is and is
    not causally related, and development builds must not reuse a release
    version.
12. **Preserve ambiguity rather than guessing.** A trace-local web number,
    source line shared by two includes, unknown relocation, or duplicate
    semantic fingerprint is evidence to expose, not a prompt to choose the
    first plausible row.
13. **State is part of the product.** The best candidate, failed attempts,
    family parameter space, active hypothesis, exact-stop point, and
    calibration cells must survive interruption and be reopenable without
    recompilation.
14. **Make cleanup recoverable and output exclusive.** A command must not
    overwrite an explicit report or silently delete cached evidence. Derived
    state updates atomically; pruning moves to restorable trash.
15. **Give humans and automation one truth.** Terminal labels, JSON keys,
    census predicates, ledger fields, and docs share vocabulary. `--json`
    errors are documents, not mixed streams.
16. **A flat spelling lattice is not evidence that a residual is unreachable.**
    The compiler never reads a spelling. It reads a *decision variable* --
    operand weight, uopt web number, a `$sp` disambiguation fact, a temp count,
    a live range. Source forms map onto those variables **many-to-one and not
    onto**, so an exhausted lattice bounds the sampling and says nothing about
    reachability. Write closures as "N forms left variable X untouched", never
    as "not source-reachable", and name the variable you believe is stuck.
    A closure that cannot name one has not finished its diagnosis.

    The base rate is not marginal. Of five closures re-tested on Mickey's
    Speedway USA on 2026-09-10, **none survived**: two functions matched on the
    first attempt afterwards, one had its stated mechanism falsified with three
    independent routes to zero, one carried a measurement that did not
    reproduce at all, and one law's cost claim was falsified by a probe. Every
    one of those closures had exhausted a spelling space; every recovery came
    from naming the variable instead. "Both operand orders emit the same word"
    was read as a wall when it is the signature of the weight law, and the fix
    was a cast that is a no-op on the value's own type.
