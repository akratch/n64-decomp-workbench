# Retained-pass replay

Pass replay asks a causal question without recompiling every earlier stage:

> If this one intermediate directive or instruction were different, would the
> downstream assembler produce the target schedule?

## Retain the ugen listing

With IDO-style drivers, `-K` commonly retains intermediates and `-S` emits
assembly. Confirm the flags used by your project:

```sh
cc -K -c -O2 -mips2 unit.c -o unit.o
```

The flags above are an executable example, not a universal preset. Replace
`-O2 -mips2` with the exact flags from the project's normal compile command.

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

## Inspect an existing Binasm boundary without replaying it

When the retained ugen listing is already semantically right but as1 rewrites
one register, inspect the actual 16-byte Binasm records at the suspected
boundary before opening another source sweep:

```sh
decomp-workbench pass binasm retained.G \
  --boundary 0x980 \
  --peep-log as1-peepdbg.stdout \
  --probe-results binasm-barrier-results.json
```

`--boundary` is the byte insertion point *before* a record and must be aligned
to 16 bytes. The report losslessly prints the local record window, names only
calibrated record families (`LOC`, `.set`, instruction, alias/call metadata,
local label), and leaves every unknown record as raw words. It also reads IDO
7.1 `-peepdbg` lines such as `Repl_reg ... changed to NOP` and summarizes a
barrier sweep whose JSON has `results[].name` and `results[].exact`.

The claim boundary matters: an exact inserted Binasm record proves that the
record is sufficient *downstream of ugen*. It does not prove that a C spelling
survives cfe/uopt/ugen and emits that record. The report therefore separates
assembler-mode controls from source-search families such as width
normalization, alias/call metadata, and real control-flow joins.

## Inspect a retained binary Ucode switch

When the suspicious boundary is earlier than ugen, inspect the binary Ucode
that uopt handed to ugen without replaying any pass:

```sh
decomp-workbench pass ucode retained.U
```

Pass UGEN's positional input file here. Do not pass the file named by UGEN's
`-temp` option: despite that generic option name, the retained `-temp` output
is a fixed 16-byte Binasm stream and belongs with `pass binasm`. UGEN's `-o`
output is Binasm as well. The Ucode inspector detects strongly Binasm-shaped
inputs and reports this provenance error instead of treating them as damaged
Ucode.

The report decodes every `Uxjp` from IDO's variable-width, big-endian Ucode
format. It prints the exact postfix selector expression consumed by the jump,
the inclusive lower and upper bounds, the case-table and default labels, and
the dense `Uclab`/`Uujp` value-to-label map that immediately follows it.
`--json` emits the same lossless records and raw words for automation.

For integer `Uldc` selector operands, `constant_value` names the active union
member. A single-word Jdt/Ldt constant has a second storage word because
`Sconstval` is a two-word `union Valu`; the report calls that companion
`inactive_constant_word` so stale bytes there are not mistaken for part of the
integer value.

The case/default distinction is structural: `Uxjp` word 1 names the case-table
label and word 2 names the default label. As with `pass binasm`, this is static
pass-boundary evidence. It proves what the retained stream contains, not which
C spelling produced it.

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
