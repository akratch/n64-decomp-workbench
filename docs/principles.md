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
