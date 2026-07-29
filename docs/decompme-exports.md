# From a decomp.me export to local truth

Use this workflow when the browser says `99.98%`, a local build disagrees, or
you need to hand an exported scratch to somebody without making them reverse
engineer its compilation model.

The workbench never logs in, scrapes, or uploads. You download the ZIP through
decomp.me, then the workbench validates and reads it locally. ZIP members are
size-bounded and read in memory; they are never extracted. Members must share
one flat archive root, so unrelated directories cannot be silently combined
by matching basenames.

## One command first

Run the synthetic export included with this repository:

```sh
decomp-workbench check-scratch examples/fixtures/decompme-export
```

```text
scratch: decomp.me-export (examples/fixtures/decompme-export)
decomp.me display: score=20/127000 (99.98425%; context only)
evidence: retained-objdump-text
verdict=schedule-mismatch aligned_total=   2 ...
aligned residual classes: aligned_schedule=2
```

This screen deliberately keeps two answers separate:

- **decomp.me display score** is useful provenance from `metadata.json`;
- **workbench truth** comes from comparing `target.o` with `current.o`, or
  redistributable `target.objdump` with `current.objdump`.

The score never overrides object evidence. `--fail-on-mismatch` returns `1`
unless an available comparison is exact; `--json` emits the metadata,
evidence source, source-composition semantics, comparison, and next actions as
one report.

## Validate your environment and handoff

```sh
decomp-workbench doctor "/path/to/downloaded scratch.zip"
```

`doctor` validates the export, reports whether an object reader was found, and
prints a shell-quoted `check-scratch` command you can paste. Retained objdump
text always works without a compiler or object reader.

By default it also reports `.decomp-workbench/cache`. If a campaign uses a
different location, pass `doctor --cache-dir /that/path`; the command only
inspects cache evidence and never removes it.

A normal decomp.me export contains:

| Member | Purpose |
|---|---|
| `metadata.json` | compiler, flags, diff label, slug, and browser score |
| `ctx.c` | generated context pasted before the editable source |
| `code.c` | editable source |
| `target.o` | target object used by the site |
| `current.o` | the site's current compiled object |
| `target.s` | target assembly, when included by the export |

`check-scratch` also validates a directory made by `bundle-scratch`, including
every recorded SHA-256, but such a pre-upload bundle has no object comparison
yet.

## Recompile exactly as the site sees the source

Under `-g3`, compiling `code.c` alone is not equivalent to compiling it on
decomp.me. The site builds one translation unit with this shape:

```c
/* ctx.c */
#line 1 "src.c"
/* code.c */
```

The line reset can affect IDO/as1 scheduling. `check-scratch` reproduces it
before invoking your wrapper:

```sh
decomp-workbench check-scratch "/path/to/downloaded scratch.zip" \
  --compile-command './compile-one.sh {source} -o {output}' \
  --compile-cwd /path/to/project \
  --objdump /path/to/mips64-elf-objdump \
  --keep-composed /tmp/site-source.c \
  --fail-on-mismatch
```

The command template is tokenized and run without a shell. It must contain
both `{source}` and `{output}`. `--env NAME=VALUE` is repeatable, and the
compiler is stopped after `--timeout` seconds (120 by default). The workbench
does not silently append the flags in `metadata.json`: wrapper interfaces
differ, so your command must select the recorded compiler, flags, includes,
and assembler options explicitly.

Use `--source candidate.c` to test a local candidate in place of exported
`code.c`. Any `#line` directives inside that candidate are preserved after the
site's line-one reset. `--keep-composed` makes the exact compiler input
inspectable; `--keep-object` retains the resulting object.

## Read a schedule residual without overclaiming it

The fixture reproduces the last shape of a real endgame: two different `li`
instructions are adjacent and reversed. An ordinary positional diff makes
that look like two register changes; opcode LCS can make it look like an
insertion plus a deletion. The shared aligned view now recognizes the equal
instruction multiset as a reorder even when unrelated relocation addends also
differ elsewhere.

Rebuilding with `-g0` is an ownership probe. A collapse means debug metadata
constrains the `-g3` schedule and as1 can reach the target order. It does
**not** prove the C is original—a freer scheduler can rescue the wrong
expression or statement topology. Compare topology and decoded line tags
next; trace the smallest as1 ready-set tie only if those views cannot explain
it.

## The finish line

`exact=true` proves the selected function's instruction words and known
relocation layout match. It does not prove the translation unit, linked image,
or game is healthy. Finish with the project's normal full build, link/ROM
comparison, and collateral checks.
