# Calibrated allocator oracle

The oracle answers one narrow causal question:

> If this recorded allocator web took another measured color (or split), how
> close would the resulting object be?

It is the last step in the evidence staircase, after ordinary object diagnosis,
source-level levers, and pass ownership. A forced object is never a source
match and must never be shipped.

## 1. Plan before compiling

Start from one focused globalcolor trace:

```sh
decomp-workbench oracle plan examples/traces/oracle.log
```

Planning always reports both phase namespaces. A trace with no `p2` decisions
says `p2: 0 allocator webs recorded`; it cannot silently turn a phase-one probe
into an “exhaustive allocator sweep.” Colors come from measured cost records or
explicit `--colors-p1/--colors-p2` values. The planner does not invent the rest
of the register universe, and it omits colors forbidden by each web’s
interference mask.

Use `--no-split` only when the split/no-color endpoint is irrelevant. A force
key is always phase-qualified: `p1:w9=c14`, `p2:w55=c2`, or `p1:w9=s`.

## 2. Correlate the web to source evidence

The supported producer records a logical source line but cannot reliably name
the original file after preprocessing. Join it to retained evidence:

```sh
decomp-workbench trace-source \
  examples/traces/oracle.log \
  examples/traces/oracle-source.i \
  --listing examples/traces/oracle-listing.s \
  --source-file candidate.c
```

`trace-source` understands `# N "file"` / `#line` markers and GNU-style
`.file/.loc` directives. Every web is `unique`, `selected`, `ambiguous`, or
`unresolved`. If two includes share line 40, both remain visible until
`--source-file` selects a marker filename. Source lines do not participate in
semantic web fingerprints, so a harmless line-number edit cannot change web
identity.

This correlation is not source attribution. An allocator trace with web, color,
owner, lineage, or line fields but no direct `source_semantic` is classified as
**run-local/unattributed**. It can still support a bounded force experiment,
but it must not recommend a source edit. The next gate is to capture a direct
`source_semantic` handle for the web; only that evidence unlocks a
source-lifetime, priority, or coalescing experiment. Explicit no-metadata
sentinels such as `unavailable`, `unknown`, `none`, and `no-source-metadata`
are not semantic handles.

Instrumented traces may carry this field on paired `[CDX] provenance_web`
records rather than the allocator decision. The workbench joins it only when
exactly one `preselect` and one `postselect` record agree on every shared
field for the same procedure, phase, and web. Missing, duplicated, or
conflicting snapshots remain run-local/unattributed.

For cross-variant decisions, use:

```sh
decomp-workbench oracle diff target.cdx candidate.cdx --proc 7
```

The diff aligns webs by type, virtual home, formation chain, and block
provenance. Numeric web IDs are displayed only as trace-local handles.
Ambiguous fingerprints are withheld rather than paired by position.

## 3. Calibrate the external toolchain

Materialize a real directory; do not point `USR_LIB` at a symlink farm:

```sh
decomp-workbench toolchain init .decomp-workbench/toolchains/ido53-cdx \
  --base /path/to/stock/ido53 \
  --uopt /path/to/instrumented/uopt \
  --fidelity-pair stock-off.o=instrumented-off.o
```

Then record the remaining evidence cells:

```sh
decomp-workbench toolchain calibrate \
  .decomp-workbench/toolchains/ido53-cdx \
  --unedited-replay-pair normal.o=replayed.o \
  --collateral-pair stock-collateral.o=instrumented-collateral.o \
  --project-output-pair expected.z64=actual.z64
```

Object pairs are compared section-by-section; project outputs are exact-file
gates. `toolchain calibrate` exits successfully when supplied cells were
validly recorded even if more cells remain. Read `claim` or
`next_missing_gates`; `oracle force/sweep` refuses anything short of
`claim=ready` with intact recorded hashes.

The manifest contains identities and hashes, never compiler contents. If any
copied file changes later, `toolchain status` reports failed integrity and the
ready claim disappears.

## 4. Force one hypothesis or sweep the measured grid

Both operations require the same source, target, wrapper, trace, and calibrated
toolchain:

```sh
decomp-workbench oracle force candidate.c \
  --trace candidate.cdx \
  --target target.o \
  --toolchain .decomp-workbench/toolchains/ido53-cdx \
  --compile-command './compile-one.sh {source} -o {output}' \
  --symbol function_name \
  --force p2:w55=c2
```

Replace `force` with `sweep` to run every planned cell. The engine:

- compiles one unforced baseline and every validated force;
- owns compiler process groups, deadlines, bounded streams, and explicit
  artifacts;
- disassembles the target once and reuses campaign ranking/cache truth;
- sets `CDX_PROC` from the trace and refuses user-supplied `CDX_FORCE`;
- retains forced objects and an append-only ledger by default;
- does not duplicate ledger observations when an identical sweep is reopened;
- reports `one-force-exact(p2:w55=c2)` only as causal evidence.

State lives under `.decomp-workbench/oracle/<symbol>-<identity>/`. The identity
includes source/target hashes, wrapper and objdump identities, working
directory, explicit environment, toolchain-manifest hash, symbol/section, and
the force plan.

## 5. Reopen and share evidence

```sh
decomp-workbench oracle status
decomp-workbench oracle export --output oracle-report.html
```

With no selector, both commands choose the most recently updated report under
the state directory. A state directory or `report.json` can be passed
explicitly. Exports are self-contained HTML or JSON and refuse to overwrite an
existing path.

## Reading the result

- `baseline words` is the unforced control.
- Each row is one compiler-decision probe, sorted by aligned residual then
  exact words.
- `EXACT UNDER FORCE` appears only when the unforced baseline compiled,
  differed, and the force became exact; it establishes sufficiency of that
  decision under this controlled build.
- An exact forced row with a failed or already-exact baseline is shown but
  withheld from the causal signature.
- No exact force means only that the measured one-force grid did not close the
  residual. It does not exonerate unrecorded colors, multi-web interactions,
  earlier passes, or source topology.

When a direct `source_semantic` is recorded, use it with the winning web’s
interference causes to reshape a lifetime, priority, or coalescing
relationship, then compile with the stock project toolchain and run the normal
object/ROM checks. Otherwise stop at the attribution gate: the result is
run-local causal evidence, not a source-edit recommendation.
