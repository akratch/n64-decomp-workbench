# Source identity without debug-mode code changes

`python -m decomp_workbench.cfe_source` instruments a pinned IDO 5.3 frontend
and joins named source operations to their actual emitted Ucode intervals.
This answers which frontend operation emitted a record. It does not identify
an optimizer spill, final stack home, or register allocation owner.

The profile is for `n64decomp/ido-static-recomp` commit
`9c242adc890beef098020149d9554f48208f699d`, generated `build/5.3/cfe.c` SHA-256
`06f1d133e72f667ceed7de3d07511154467e32d71ee9aa9aaa773328a1b730f5`.
Unknown source hashes are rejected; there is no command-line bypass. Keep
generated compiler sources, objects, binaries and project traces private.

## Producer facts

The compiler's own declaration-name path reads a declaration's identifier,
then its string. Hooks at `load_var`, `store_var` and `load_addr` record that
name as bounded hexadecimal bytes alongside raw declaration fields. Those
fields deliberately have no inferred storage-class or final-home labels.
An opaque declaration token is meaningful only inside that compiler process;
shadowed names and identical offsets must not be merged across procedures.

Each operation receives an invocation ordinal and records start/end stream
positions. Positions combine bytes actually returned by the UWRITE output
routine with the current producer buffer displacement. This is an explicit
emission interval, not a join by source line, event order or register number.
Nested operations retain their parents and may have overlapping intervals.
The parser requires complete event pairs, valid Ucode record boundaries and
the complete cumulative output length. Empty emission intervals are allowed.

## Use and fidelity

```sh
python -m decomp_workbench.cfe_source instrument compiler/cfe.c private/cfe.c
# Build private/cfe.c using the same static-recompiler runtime and headers.
# Substitute only that binary into an isolated capture toolchain.
# Compile the same configured translation unit with tracing off, then on:
DKWB_CFE_SOURCE_TRACE=1 private/toolchain/cc [configured arguments]
python -m decomp_workbench.cfe_source join private/trace.txt private/input.ucode
```

The environment variable is disabled when absent, empty or beginning with zero.
Capture stderr separately from compiler intermediate outputs. Pair the trace
with the actual frontend output captured as optimizer input from the same
invocation. The report hashes both inputs for later freshness checks; matching
length alone does not authenticate that pairing. The join is diagnostic and
always reports `fidelity_proof=false` and `final_home_proof=false`.

Use `decomp-workbench fidelity` to compare both trace-off and trace-on objects
against the untouched stock compiler, including allocated text/data sections,
relocations and symbols. Keep ordinary optimized flags. An optimized-debug
control changed 22 of 28 words despite retaining size, so debug names are not
interchangeable with names from normal compilation.

The initial private producer prototype passed an aggregate/address-escape
control and a two-function control with shadowed locals and repeated calls.
The latter emitted a 26,408-byte stream; all 811 operation intervals ended on
record boundaries across buffer flushes. These are feasibility observations,
not claims that every frontend construct is covered. Synthetic tests exercise
missing/duplicate anchors, malformed and truncated traces, nesting, stream
length, shadow-name separation and boundary rejection.

The product profile also passed a configured full-translation-unit control on
Mickey's `func_overlay_014_F000013C_186FA14`: trace-off and trace-on both preserve
stock text, data, rodata, relocations and symbols. The captured frontend stream
joins 73 operations, including six named uses of the local involved in the
reservation experiment. That authenticates frontend emission ownership. The
later register-home change is supported by a controlled declaration-order
experiment, not by a claim that frontend identities survive every optimizer pass.

The next useful consumer is an authenticated optimizer allocation trace.
Carry explicit producer identities through splits/merges where available;
report missing joins instead of treating frontend displacement as final layout.
