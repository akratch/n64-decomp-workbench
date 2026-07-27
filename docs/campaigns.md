# Candidate campaigns

`campaign` is the repeatable replacement for a directory of single-purpose
compile loops.

## Run a campaign

```sh
decomp-workbench campaign target.o candidates/*.c \
  --symbol function_name \
  --compile-command './compile.sh {source} -o {output}' \
  --objdump /path/to/mips64-elf-objdump \
  --jobs 8 \
  --cache-dir .workbench/cache \
  --ledger .workbench/campaign.jsonl \
  --keep-objects .workbench/top-objects
```

`{source}` and `{output}` are required. The template is split with `shlex` and
executed directly; shell expansion, pipes, redirection, and command
substitution are not evaluated.

## What is recorded

Each JSONL record includes:

- source path;
- rendered compiler command;
- explicit compiler environment;
- source, target, directly invoked compiler/wrapper, and objdump identities in
  the cache key;
- compiler stdout, stderr, exit status, and duration;
- cache status;
- comparison metrics and object hashes;
- paths that produced the same prepared key, when applicable.

The directly invoked wrapper is hashed when it is a file. A wrapper may invoke
additional binaries or read configuration that the workbench cannot discover.
For complete reproducibility, put those versions in the wrapper’s own output or
campaign metadata.

Source paths intentionally remain in prepared keys even when file content is
equal. Some wrappers change behavior by path and some object formats embed
source paths. Passing the same prepared source more than once is deduplicated;
different paths are treated as distinct candidates.

## Environment-sensitive compilers

Pass instrumentation and behavioral controls frequently use environment
variables. Declare them explicitly so they become part of the cache key:

```sh
decomp-workbench campaign target.o candidates/*.c \
  --compile-command './compile.sh {source} -o {output}' \
  --env CDX_LOG=1 \
  --env CDX_PROC=3
```

Inherited environment variables are passed to the compiler but not all are
hashed. Avoid relying on undeclared environment state for a scientific
campaign.

## Reading campaign results

Keep several axes visible:

1. instruction count and frame size;
2. exact or relocation-aware word mismatches;
3. insertion/deletion/reorder penalties from the project’s native diff tool;
4. opcode and normalized structure;
5. register and FP-register ranges;
6. trace signature when candidates enter the same structural basin.

A candidate with a numerically worse score can still remove structural
differences and leave only a register permutation. The
[object collision worked example](../case-studies/objects-structural-score.md)
shows that exact transition.

## Writing transformation generators

Keep generators separate from the campaign runner. A generator should:

- start from a pinned source template;
- make one named transformation or a documented Cartesian product;
- emit deterministic filenames;
- include transformation parameters in a sidecar manifest or source comment;
- avoid editing the active project translation unit in place.

The historical DKR archive contains many function-specific generators.
Reusable families include declaration order, expression tree/order, statement
split/merge, control-flow spelling, local reuse, literal type, and live-range
boundary changes. They are examples of experiments, not an API that the
workbench promises to make meaningful for every compiler.

## Cache hygiene

Objects are content-addressed under `--cache-dir`. Removing the cache is safe
but forces recompilation. The ledger is append-only so interrupted runs retain
completed records. Use a new ledger for a materially different experimental
question, even when the cache can be reused.
