# Retained-pass replay

Pass replay asks a causal question without recompiling every earlier stage:

> If this one intermediate directive or instruction were different, would the
> downstream assembler produce the target schedule?

## Retain the ugen listing

With IDO-style drivers, `-K` retains intermediates and `-S` emits assembly.
The exact flags vary by project. The DKR 5.3 pipeline used:

```sh
cc -K -c <project flags> unit.c -o unit.o
```

This retained a human-readable `unit.s`, binasm/symbol-table intermediates, and
the final object.

## Replay as0 and as1

```sh
decomp-workbench replay-as1 unit.s candidate.o \
  --as0-command '/ido/as0 -G 0 -EB -g0 -O2 {listing} -o {binasm} -t {symtab}' \
  --as1-command '/ido/as1 -elf -G 0 -p0 -EB -g0 -O2 {binasm} -o {object} -t {symtab}' \
  --keep-work replay-output
```

Commands are tokenized and invoked without a shell. `as0` must contain
`{listing}` and `{binasm}`; `as1` must contain `{binasm}` and `{object}`.
`{symtab}` is available to both.

## Make one targeted insertion

The menu experiment inserted a register-pair alias directive before one load:

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

## What replay establishes

If one directive produces an exact object, it establishes that the downstream
pass can account for the observed schedule and that the directive is
sufficient at that site. It does not establish why the historical compiler
emitted the directive. That requires tracing or source experiments in the
earlier pass.

See the [menu worked example](../case-studies/menu-pass-replay.md) for the full
uopt → ugen → as1 chain.
