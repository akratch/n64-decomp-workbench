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
acceptance: NOT ACCEPTED — 2 raw instruction words differ
decomp.me display: score=20/127000 (99.98425%; context only)
evidence: retained-objdump-text
verdict=schedule-mismatch aligned_total=   2 ...
aligned residual classes: aligned_schedule=2
```

This screen deliberately keeps three answers separate:

- **decomp.me display score** is useful provenance from `metadata.json`;
- **linked-function exactness** masks linker-controlled relocation fields;
- **local score-proxy exactness** requires identical pre-link instruction words
  and relocation symbol/addend targets, and comes from comparing `target.o`
  with `current.o`, or
  redistributable `target.objdump` with `current.objdump`.

`check-scratch` now prints the same separation as a truth stack. Site metadata
is context, the scratch object is one measured layer, and an optional project
object is another. Supply `--project-object PROJECT.o` (and optionally
`--project-source UNIT.c`) to compare that project-selected function with the
export's `target.o`. A project-exact/scratch-mismatch pair is classified
`context-only`; neither layer overwrites the other. `--project-source` requires
the project object because source text alone is not object truth.

The saved browser score never overrides freshly measured object evidence. For
a scratch, `--fail-on-mismatch` returns `1` unless every raw instruction word
and known relocation entry agrees. This is deliberately stricter than
`compare`: two symbol/addend spellings can be equivalent after linking while
decomp.me still assigns a
non-zero score to their different unlinked words. JSON exposes both
`decomp_me_score_proxy_exact` and `linked_function_exact`, plus the component
gates `raw_instruction_words_exact` and `relocation_targets_exact`. “Proxy” is
intentional: only the site can report the site's result. The local report also
includes metadata, evidence source, source-composition semantics, and next
actions.

The terminal leads with `ACCEPTED`/`NOT ACCEPTED`; JSON pairs `accepted` with
`acceptance_basis`, `acceptance_summary`, and
`exact_scope=linked-function-after-relocation-field-masking`. When relocation
targets reject an otherwise exact instruction stream,
`relocation_target_differences` and the terminal list each side's offset, type,
symbol, and parsed addend.

When linked exactness passes but the score proxy fails, inspect the
`relocation-controlled` diff site. Match the target's relocation symbol and
addend spelling before claiming 100%; a struct member at `base+offset` and a
direct symbol at that final address are not necessarily score-equivalent.

## Getting the export in the first place

The workbench does not fetch anything: it has no network egress, by design and
by contract (`decomp-workbench commands --json` reports `safety.network:
false` for every command). You obtain the ZIP yourself and point the workbench
at it.

If you script that download, two things are worth knowing, because several
campaign sessions have spent time on each:

* **The API expects a normal browser-shaped request.** A bare `curl` with no
  headers is commonly rejected. Send a **descriptive** `User-Agent` that names
  your tool and a contact — an honest identifier is both the polite thing and
  the thing that makes it possible for the site to tell your traffic from
  abuse — along with the ordinary `Accept`, `Accept-Language`, and `Referer`
  headers a browser would send, and accept compressed responses. Do not
  impersonate a specific browser build to get around a block: if requests are
  being refused, that is a signal to slow down or ask, not to disguise them.
* **Be gentle and cache.** These are volunteer-run community servers. Fetch
  each scratch once, keep the ZIP, and re-run the workbench against the local
  copy — which costs nothing and is reproducible. Serialize requests, leave a
  pause between them, and back off on any error rather than retrying in a
  loop. If you need bulk data, ask the project maintainers first.

Once the ZIP is on disk, everything below is local and offline.

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

On every decomp.me export it additionally runs the pre-paste hardening
checks, each of which encodes a failure that cost real campaign round-trips:
a file-scope symbol defined in both files (the redefinition error never names
the context as the other half), a directive the context makes vacuously true,
and line-splice hazards in `code.c` — an intact
statement-level splice is load-bearing for line-number ties (field-guide
lever 25) and is listed so you re-check it after pasting, while a backslash
followed by trailing whitespace is not a splice at all and is a warning.

A missing final newline in `ctx.c` is safe: decomp.me inserts the
language-aware source boundary before `code.c`, and the workbench's composed
source does the same. Older workbench releases warned about this incorrectly.

## Recompile exactly as the site sees the source

Under `-g3`, compiling `code.c` alone is not equivalent to compiling it on
decomp.me. The site builds one translation unit with this shape:

```c
/* ctx.c */
#line 1 "src.c"   /* C; old-C++ exports use src.cxx */
/* code.c */
```

The line reset can affect IDO/as1 scheduling. `check-scratch` derives
`src.c` versus `src.cxx` from the exported language and canonical compiler ID,
then reports the compiler ID, frontend family, and expected driver separately
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

For one tightly measured C89 shape, the truth stack offers a safe
call-contract probe. It requires an otherwise shape-stable register-only
residual, exactly one coherent `$v0`/`$v1` web late in the function, a nearby
direct call, and an explicit `void` declaration for that callee in the scratch
context. C++, non-C89 frontends, structural residues, unrelated registers, or
an early/far call suppress the hint. The action is deliberately one
scratch-only `int callee();` experiment; it is a hypothesis about unused-return
register occupancy, not proof of the historical prototype and never an
instruction to edit project source blindly.

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

For a recorded candidate, `campaign finish` turns that order into one receipt:
fresh function and required-signal gates always run; scratch, collateral,
handoff, and the caller's project/ROM command run only when supplied and remain
`NOT RUN` otherwise.
