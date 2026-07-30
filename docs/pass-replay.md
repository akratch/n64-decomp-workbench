# Retained-pass replay

Pass replay asks a causal question without recompiling every earlier stage:

> If this one intermediate directive or instruction were different, would the
> downstream assembler produce the target schedule?

## Retain the ugen listing

With IDO-style drivers, `-K` commonly retains intermediates and `-S` emits
assembly. Confirm the flags used by your project:

```sh
cc -K -c <project flags> unit.c -o unit.o
```

You need a human-readable `unit.s`; as0/as1 will recreate the binasm,
symbol-table, and object outputs.

## Replay as0 and as1

```sh
decomp-workbench replay-as1 unit.s candidate.o \
  --as0-command '/ido/as0 -G 0 -EB -g0 -O2 {listing} -o {binasm} -t {symtab}' \
  --as1-command '/ido/as1 -elf -G 0 -p0 -EB -g0 -O2 {binasm} -o {object} -t {symtab}' \
  --calibration-object normal.o \
  --objdump /path/to/mips64-elf-objdump \
  --work-root .decomp-workbench/pass-replay \
  --keep-work replay-output
```

Commands are tokenized and invoked without a shell. `as0` must contain
`{listing}` and `{binasm}`; `as1` must contain `{binasm}` and `{object}`.
`{symtab}` is available to both.

Use `--compile-cwd` for wrappers with relative paths and repeat
`--env NAME=VALUE` for pass inputs that must be explicit. The 120-second
default timeout applies to each external stage. Report streams are bounded by
`--stream-limit`; `--artifact-dir` retains collision-safe complete streams.

`--work-root` is for QEMU, Docker, or another wrapper that cannot see the host
temporary directory (notably per-user macOS `/var/folders` paths). Each replay
gets a unique directory under the supplied project-visible root.

## Make one targeted insertion

For example, insert a register-pair alias directive before one load:

```sh
decomp-workbench replay-as1 unit.s candidate.o \
  --insert-before '^\tlh\t\$10,0\(\$17\)$=\t.noalias\t$17,$16' \
  --as0-command '...' \
  --as1-command '...'
```

The syntax is `REGEX=TEXT`. Quote the argument so the shell does not interpret
`$` or backslashes. Patterns must match exactly once unless
`--allow-multiple` is explicitly supplied.

After replay:

```sh
decomp-workbench compare target.o candidate.o \
  --symbol function_name \
  --fail-on-mismatch
```

## Controls

Run at least three cells:

1. Original retained listing through replay, with no edit.
2. Edited listing through the same replay.
3. A deliberately irrelevant nearby edit, when useful.

Cell 1 must reproduce the normal downstream object. Otherwise the replay
pipeline itself differs and the causal result is ambiguous.

The CLI enforces that control. Any `--insert-before` or `--insert-after`
requires `--calibration-object`; it automatically runs the unedited listing
first and compares meaningful sections, relocations, and symbols through the
selected objdump. An edited replay is refused if calibration fails.

For an earlier boundary, use the generic original/static adapter:

```sh
decomp-workbench pass diff retained.input \
  --boundary uopt-to-ugen \
  --original-command '/qemu-irix original-pass {input} {output}' \
  --static-command '/host/static-pass {input} {output}' \
  --work-dir .decomp-workbench/pass-diff \
  --require-identical
```

The adapter accepts only user-supplied executables, records executable and
input/output hashes, runs in a project-visible directory, and can send both
results through one `--downstream-command`. Byte identity and host-normalized
identity are separate, so path or C-library formatting noise is not mistaken
for pass behavior.

## What replay establishes

If one directive produces an exact object, it establishes that the downstream
pass can account for the observed schedule and that the directive is
sufficient at that site. It does not establish why the earlier pass omitted
the directive; that requires tracing or source experiments upstream.
