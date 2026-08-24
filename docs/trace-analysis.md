# Trace analysis

Trace analysis answers a narrower question than disassembly: which compiler
events produced an otherwise-correct register or scheduling pattern?

## Read one site's whole decision cascade

```sh
decomp-workbench trace-cascade examples/traces/cascade.log --frame-offset 0xfffffdf8
```

Every round of one web family's `f_split` cascade, the colour it actually
received, and the decision as one inequality. `trace-order` ranks the whole
colouring order with its ties, and `trace-blocks` intersects two webs'
occurrence-block sets. See [the allocator decision cascade](cdx-cascade.md).

## Summarize an unfamiliar trace

```sh
decomp-workbench trace-summary compiler.stderr --json
```

The parser retains known `CODEX-*` and `DKWB-*` tags and counts actions,
registers, and source lines. Unknown diagnostic tags remain visible rather than
being silently discarded.

## Inspect alias-state decisions

```sh
decomp-workbench trace-alias uopt.log --show-queries
```

The pinned uopt profile emits two trace families:

- `DKWB-BASE` records the descriptor associated with a physical register and
  whether the base path was fresh, direct, or retained;
- `DKWB-ALIAS-QUERY` records the two descriptors and the pass's observed
  may-alias/no-alias result.

The report counts base paths, descriptor types, outcomes, and registers.
`--show-queries` prints each decision; `--json` retains the full normalized
event fields for downstream analysis. See
[compiler instrumentation](compiler-instrumentation.md) for profile creation
and the required controls.

## Reconstruct a FIFO free list

```sh
decomp-workbench trace-fifo ugen.log \
  --registers t3,t4,t5,t6,t7,t8,t9 \
  --list-address 10019da4 \
  --show-events \
  --fail-on-violation
```

The replay:

1. Uses unique append events before the first allocation as the initial queue,
   unless `--initial` is supplied.
2. Checks each allocation against the queue head.
3. Assigns a new logical value identity to each allocation.
4. Converts later appends into frees of those logical values.
5. Reports duplicate appends, frees without a live value, allocation of an
   already-live register, and empty-queue allocation.

Use `--initial t6,t7,t8,...` when the trace begins after queue initialization.
Addresses accept decimal, `0x`-prefixed hexadecimal, or bare hexadecimal when
the value contains `a`–`f`; prefix digit-only hexadecimal values with `0x`.
When `--list-address` is set, the replay keeps allocation records, which may
not carry a list address, and accepts append records only from the selected
list. Use `--json` when another solver will consume the logical schedule.

Instrumented `DKWB-FREELIST` rows also carry `emitted=N`, the ugen forward
ibuffer ordinal measured at the event. It is deliberately not called an object
row: labels, directives, and assembler folding make those coordinate systems
different. Supply a measured calibration document to complete the join:

```json
{
  "schema": "decomp-workbench-ugen-emission-map-v1",
  "entries": [
    {"emitted_index": 258, "object_row": 700,
     "instruction": "sll t0,t1,2",
     "source_file": "camera.c", "source_line": 412}
  ]
}
```

```sh
decomp-workbench trace fifo ugen.log \
  --emission-map emission-map.json --show-events --json
```

Each logical allocation/free event then carries `emitted_index`, `object_row`,
`instruction`, `source_file`, and `source_line`; `emission_join` reports
coverage. Without a mapping, `calibration_required=true` and object rows remain
null rather than being inferred.

### Why logical identities matter

A physical sequence such as `t6,t4,t8,...` is not necessarily the allocator’s
entry queue. Allocation and free events interleave, and later registers may
already be recycled values. Logical values make the event schedule explicit
before any inference about source evaluation order.

## Read IDO 7.1 A71 traces

IDO 7.1 campaigns with the compact read-only A71 producer use a separate
static reader:

```sh
decomp-workbench trace a71 baseline.a71 --against variant.a71
decomp-workbench trace a71 baseline.a71 --web 35
```

`trace a71` decodes `savebits` as the allocator's single-precision priority,
names only colors calibrated against IDO 7.1 objects, and decodes both
forbidden-mask words. It accepts either a filtered `.a71` file or a mixed
compiler log. A malformed line beginning with `[A71]` is an error rather than
being silently discarded.

The comparison key is `(phase, web)`, and it is deliberately labelled
**run-local**. A71 has no procedure or semantic provenance: a controlled edit
can insert webs and renumber everything after them. Use the diff to explain a
known-stable web neighborhood, not to claim that every equal numeric web is the
same source value. The first producer's fields named `refs` and `defs` read
the wrong recovered-source offsets; the reader always ignores them and says
so in text and JSON.

## Read globalcolor traces

The richer IDO 5.3 `CSAVE`/`CUP`/`[CDX]` formats remain under
`trace-globalcolor`:

```sh
decomp-workbench trace-globalcolor uopt.log --dtype 13 --top 25
```

Once a comparison has isolated an allocation residual, inspect a single web
instead of scanning an entire procedure:

```sh
decomp-workbench trace-globalcolor uopt.log --proc 46 --web 240
```

Ask for the barrier to one desired physical register when the mismatch is a
register residue:

```sh
decomp-workbench trace-globalcolor uopt.log \
  --proc 46 --web 240 --desired-register s4
```

For an eligible endpoint, the report gives the measured cost gap to the
natural color. For a forbidden endpoint, a trace captured with
`CDX_DETAIL_WEB=240` also names each already-colored interfering web occupying
that register. Without targeted neighbor detail, the report explicitly asks
for that recapture. IDO's finite unavailable-cost sentinel (approximately
`1e20`) is reported as `ineligible`, not as an enormous affinity penalty.
These are three different source-search problems: reshape overlap for
interference, change relative priority or affinity for a real cost gap, and
inspect register-class/availability constraints for an ineligible endpoint.

`--proc` and `--web` hide unrelated legacy live-range rows. `--web` requires
`--proc`, and an explicit lookup exits nonzero when its allocator data is
absent. A missing lookup lists the procedure or web IDs that were actually
recorded.

The report names stable callee-saved profile colors when it can (`c17 (s3)`),
keeps profile-specific colors as `cNN`, and explains whether the web was
colored or split. A force probe is a causal experiment only: use it to learn
which lifetime must be reshaped, never as a source-match result.

Supported formats:

- `CSAVE`: one live range/web and its adjusted-save inputs;
- `CUP`: cost of a candidate color/register;
- `[CDX]`: selection, split/color, and force-choice decisions from the
  profiled instrumentation.

CDX-only captures report `legacy-live-ranges=not-captured(CSAVE/CUP absent)` in
text and `legacy_live_range_capture: "not-captured"` in JSON. This means the
older `CSAVE`/`CUP` producer was not enabled; it does not claim the procedure
had zero live ranges. Allocator-web decisions remain available from CDX.

The report computes `total_save` as `adjusted_save × weight`. Field names are
descriptive handles for the pinned generated source, not stable IDO API names.
Non-finite values become `"inf"`, `"-inf"`, or `"nan"` in JSON.

## Align webs across source variants

Numeric allocator web IDs are stable only inside one compiler input. Compare
semantic provenance instead:

```sh
decomp-workbench trace-webs candidate.cdx --against variant.cdx --proc 7
```

Fingerprints use allocator phase, dtype/type, virtual-home fields,
table/expression formation chain, and block provenance. Numeric IDs are
trace-local handles. The opaque, address-like `raw14` observation remains in
the evidence payload but is excluded from both exact identity and coarse
topology: calibrated captures show it changing when the same web is recreated
in another compiler run. A fingerprint that is not unique on either side is
reported as ambiguous and withheld rather than paired by position.

Read `alignment coverage` before reading the difference count. A broad source
topology change can renumber table, block, and formation provenance so severely
that most fingerprints disappear on one side. In that case presence rows are
fingerprint churn, not proof that each web was inserted or removed. The command
prints `partial` or `no-common-fingerprints` and routes to `trace-origin-probe`
on one controlled edit (or to producer-emitted `source_semantic`) before any
web-by-web causal claim.

When neighbor records are present, the diff joins a newly forbidden color to
the already-colored neighbor that occupies it, naming the neighbor's semantic
fingerprint and decoded register where known.

Forced traces preserve two different facts: `natural` is the allocator's
pre-force best color, while `assigned` is the color actually written by the
later color site. `trace webs --against` reports actual-assignment changes,
natural-choice cascades, forbidden-mask changes, and force overrides
separately. A force must never be presented as the allocator's natural choice.

The same report also prints a **decision outcome**. This compares the observed
ordered `(procedure, phase, decision, color)` sequence without using semantic
fingerprints. It can therefore say that source-distinct hidden webs reached the
same complete register cascade even when semantic alignment is partial. Read
the two claims independently:

- semantic alignment answers whether the same compiler-visible webs changed;
- outcome equivalence answers whether the ordered register endpoints agree.

An identical outcome is carrier-substitution evidence, not source identity.
The SSSV cleanup replaced two static-local webs with two relational-control
webs: only 19 of 29 union fingerprints aligned, but all 20 phase-2 decision
endpoints were identical and the emitted function was raw-object exact.

For one controlled source perturbation, use the three-layer origin probe:

```sh
decomp-workbench trace origin-probe baseline.log variant.log \
  --proc 0 --role texture-value --synthetic
```

It reports exact semantic identity, a detailed run-local formation multiset,
and a deliberately coarse topology multiset. `isolated-removal`,
`isolated-insertion`, and `isolated-replacement` are M0 calibration results,
not source attribution. Formation fields can renumber between compiler runs;
coarse signatures can collide. Both facts remain visible in the report rather
than being resolved by position or register color.

The report also shows an `allocation economics` layer. It groups webs by
phase, save/occurrence totals, interference count, and decision kind. It
deliberately excludes optional web-detail fields so traces from different
instrumentation profiles remain comparable.
This often survives wholesale ICHAIN renumbering and can reveal that a unique
100-save role moved from `w62(t5)` to `w29(a2)`. It is controlled-differential
evidence, not semantic identity: repeated economics signatures are reported as
collisions and never paired by position. The text report separates real color
or interference changes from trace-local web-number renumbering and prints
only the former as transitions.

`trace-stack-homes TRACE --proc N [--offset VALUE]` classifies only homes for
which the producer recorded evidence: named source local, compiler temporary,
outgoing argument home, or allocator spill. Virtual offsets and final offsets
stay separate; a missing final layout is `null`, not inferred. If an ordinary
globalcolor trace contains allocator webs but no stack-home fields, the command
reports `no-stack-home-evidence` and says explicitly that the current profile
cannot answer the query. Opaque `raw10`/`raw14` words are not guessed to be
offsets; a calibrated producer hook is required.

## Correlate logical lines to source and listings

Compiler line fields can be coarse, synthetic, and ambiguous after includes.
Retain the preprocessed/composed input and optional assembly listing:

```sh
decomp-workbench trace-source \
  examples/traces/oracle.log \
  examples/traces/oracle-source.i \
  --listing examples/traces/oracle-listing.s \
  --source-file candidate.c
```

The command replays standard preprocessor markers and `.file/.loc`
directives. It preserves all candidates when a logical line exists in several
files and narrows only on an explicit marker filename. Correlation is evidence
attached to a semantic web, never part of the fingerprint itself.

Neither correlation nor allocator metadata is a source semantic. Without a
direct trace `source_semantic`, `trace-webs` and `oracle plan` classify the web
as run-local/unattributed. Capture that field before turning a force result into
a source-experiment recommendation.

Do not add `#line` solely to manufacture that attribution. IDO uses logical
statement lines as scheduling input even under `-Xg0`; changing them can
reorder instructions while leaving allocator webs unchanged. A marker that
correlates a listing is not a producer-emitted `source_semantic`.

When a final web snapshot is too coarse, the pinned globalcolor profile can
also record `lineage_range` and `lineage_member` before coloring. Filter it by
ICHAIN table identity with `trace-globalcolor --proc N --lineage-table T`.
This answers whether two source forms created the same live-block membership;
it does not turn table `T` into a source variable name. The lineage producer's
procedure number is a separately counted `makelivranges` invocation ordinal;
confirm paired lineage and globalcolor records before relying on that run-local
join.

## Plan a causal allocator probe

```sh
decomp-workbench oracle plan examples/traces/oracle.log
```

The planner reports both p1 and p2, uses only measured cost colors (or explicit
overrides), and omits forbidden endpoints. A ready external toolchain can then
run one force or the full cached grid. See [Calibrated allocator
oracle](oracle.md) for the fidelity gates, state, and proof boundary.

## Trace comparison discipline

- Compare the same procedure ordinal and compiler profile.
- Keep source-line tags stable or record source hashes.
- Establish an instrumentation-off control that is byte-identical per section
  (`.text`, `.rodata`, `.data`, relocations, symbols); `.mdebug` varies between
  runs of stock IDO under `-g3`, so file-level hashes are not a usable gate.
- Compare the same allocator phase: `p1` and `p2` web numbers are disjoint.
- Use a small positive-control source to prove the event hook fires.
- Treat force-choice output as a causal experiment, not as historical
  provenance.
- Reduce a trace to the smallest register class and source window that answers
  the question.
- Reopen saved oracle evidence with `oracle status`; do not rerun merely to
  reconstruct a terminal screen.
