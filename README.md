# Decomp Workbench

`decomp-workbench` packages the reusable parts of the compiler-oracle and
instrumentation workflow used to finish Diddy Kong Racing's Adventure One.
It is intentionally project-agnostic:

- compare two MIPS objects at exact, opcode, normalized, and register levels;
- rank a directory of candidate objects against one target;
- compile and rank source candidates with any compiler command;
- add opt-in call and register-free-list tracing to a statically recompiled
  IDO `ugen.c`.

The package contains no ROM data, target objects, compiler binaries, or
function-specific candidates. The original DKR experiments and compiler
patches are preserved separately on the fork's
`archive/decomp-research-2026-07-26` branch.

## Install

Python 3.10 or newer is required. From this directory:

```sh
python3 -m pip install .
```

For development:

```sh
python3 -m pip install -e .
python3 -m unittest discover -s tests
```

## Compare objects

```sh
decomp-workbench compare target.o candidate.o \
  --symbol func_80049794 \
  --objdump ../../tools/binutils/mips64-elf-objdump
```

Add `--json` for machine-readable output, `--show-diff` to print localized
register differences, or `--fail-on-mismatch` for CI.

The reported `normalized_distance` ignores branch target addresses, immediate
values, and stack offsets. It is a useful structural signal, not a proof of
equivalence. `word_mismatches == 0` is the exact-match check.

## Rank retained objects

```sh
decomp-workbench rank target.o /tmp/candidate-*.o \
  --symbol func_80049794 --limit 20
```

Candidates are ordered by exact word mismatch count, normalized distance,
register mismatch count, and instruction-count delta.

## Compile and rank sources

Use `{source}` and `{output}` placeholders in a compiler command. The command
is split without invoking a shell.

```sh
decomp-workbench compile-rank target.o candidates/*.c \
  --symbol func_80049794 \
  --compile-command './compile.sh {source} -o {output}'
```

Failed compilations are retained in the report instead of aborting the whole
sweep. Use `--keep-objects DIR` to retain successful objects.

## Instrument a recompiled ugen

```sh
decomp-workbench instrument-ugen ugen.c ugen.traced.c
cc -O2 -o cc-traced ugen.traced.c
DKWB_UGEN_TRACE=1 ./cc-traced ...
```

The generated source is behavior-neutral while tracing is disabled. With
`DKWB_UGEN_TRACE=1`, it prints:

- `DKWB-CALL` entries and exits for the selected recompiled functions;
- `DKWB-FREELIST` events for known GP-register allocation/free-list helpers.

Restrict call tracing with a regular expression:

```sh
decomp-workbench instrument-ugen ugen.c ugen.traced.c \
  --functions '^(f_(alloc|free|add_to|remove_from|move_to).*)$'
```

The instrumenter targets the C output produced by static recompilation, where
functions use names such as `f_alloc_reg`. It refuses to instrument the same
file twice and reports how many functions and free-list hooks it added.

## Research lessons retained in the tool

The original campaigns showed that a single raw instruction-difference score
is too coarse late in a match. Useful oracles form a ladder:

1. instruction count and exact word mismatches;
2. opcode and normalized structural distance;
3. integer and floating-point register mismatch ranges;
4. stack frame, spill offsets, and register-use counts;
5. compiler allocator/free-list traces when source-level searches plateau.

The `func_8008FF1C` match also demonstrated that alias provenance and literal
loop bounds can change uopt scheduling: direct array indexing let uopt prove a
store could not alias another global, and the literal inner bound preserved
strength reduction. Those observations belong in research notes and tools,
not as permanent function-specific source comments.
