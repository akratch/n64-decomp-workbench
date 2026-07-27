# Version 0.2.0 validation record

This record separates checks performed on the redistributable package from
checks that require an external compiler or game project. It was recorded on
2026-07-27 before tagging version 0.2.0.

## Package checks

The 48-test suite passed on CPython 3.10.19, 3.11.14, 3.12.12, 3.13.11,
and 3.14.3. The same source passed:

- Ruff lint and format checks;
- mypy in strict mode with a Python 3.10 target;
- codespell over code and public prose;
- `actionlint` on the package workflow;
- Bandit with no medium- or high-severity finding;
- `git diff --check`.

Fresh wheel and source distributions passed `twine check`. The wheel passed
`check-wheel-contents`. Each distribution was installed into a separate empty
environment; `decomp-workbench --version`, relocation-aware dump comparison,
and FIFO trace replay all completed successfully.

## Real MIPS object check

The comparator was run against `init_track` in the DKR build's real
`build/src/tracks.c.o` with the repository's GNU-compatible
`mips64-elf-objdump`:

| Check | Result |
|---|---:|
| Parsed instructions | 217 |
| Parsed MIPS relocations | 76 |
| Raw word mismatches | 0 |
| Relocation metadata mismatches | 0 |
| Unknown relocation kinds | 0 |
| Frame adjustment | -40 |
| Verdict | `exact=true` |

The object is a local project input and is not included in the distribution.
The redistributable tests use reduced objdump text.

## Pinned instrumentation check

The exact upstream profile was regenerated from
`decompals/ido-static-recomp` commit
`9c242adc890beef098020149d9554f48208f699d`. The generated
`build/5.3/uopt.c` SHA-256 was:

```text
b0058f1559441c1a194d649271eb43b8637ec255682cfdd629031340b915b13f
```

This matches the packaged profile. The alias-only, globalcolor-only, combined
uopt, and generic ugen outputs all compiled as host C. The combined uopt and
generic ugen were then built into the real static-recompiled IDO 5.3 toolchain
and used to compile
[`examples/instrumentation/fidelity-micro.c`](../examples/instrumentation/fidelity-micro.c).

With all instrumentation variables unset, the stock and instrumented compilers
produced the same MIPS object:

```text
8aa46868a7e58f7154e9b9961792e0696c7ae53002cb9e51e133f7b23371a2f4
```

Enabling all trace-only controls still produced that object exactly and
yielded these positive controls:

| Trace family | Records |
|---|---:|
| `[CDX]` globalcolor decisions | 34 |
| `DKWB-BASE` and `DKWB-ALIAS-QUERY` | 12 |
| Generic `DKWB-CALL` and `DKWB-FREELIST` | 15,584 |

The workbench parsers consumed the resulting combined log. Phase-two CDX web
identifiers followed the actual bit positions (`0`, `3`, `6`, `9`, …), rather
than a stale stack value.

Two behavior-changing controls were also checked on procedure 0, web 9:

- `CDX_FORCE=w9=c5` logged the forced color and changed the object;
- `CDX_FORCE=w9=s` logged the forced split and changed the object.

Setting `CDX_FORCE` without `CDX_PROC` emitted the documented warning, ignored
the control, and reproduced the stock object.

## Campaign and pass-replay checks

The fidelity microcase was compiled through the real IDO wrapper with
`campaign`. The first run produced an exact comparison and populated the
cache; an identical second run reported `cached=true` and remained exact. The
two JSONL records contained source and target hashes, compiler and objdump
paths and hashes, symbol, section, environment, command, output, timing, and
comparison data.

The same compiler retained its ugen listing. An unedited `replay-as1` run
through the real as0 and as1 binaries reproduced all 154 instructions with
matching relocation metadata, no unknown relocations, and `exact=true`.

## Claim boundary

The microcase establishes that the packaged patchers fit the pinned generated
source, compile, remain output-identical while trace-only controls are used,
emit parseable positive controls, and apply scoped force choices. It does not
replace a new user's host-specific collateral and whole-project checks.

The four case-study commits record the original DKR function and whole-ROM
verification results. Compiler instrumentation on a different host, upstream
revision, or project must still complete the
[required fidelity gates](compiler-instrumentation.md#required-fidelity-gates).
