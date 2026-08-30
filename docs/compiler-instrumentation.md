# Compiler instrumentation

The workbench targets C emitted by
[`ido-static-recomp`](https://github.com/decompals/ido-static-recomp). It does
not include compiler binaries or generated compiler source.

## Two levels of intervention

### Trace-only hooks

Trace-only instrumentation observes host-side execution of a statically
recompiled compiler pass. With its environment variables unset it is intended
to leave emulated compiler state unchanged.

That intention still requires an output-fidelity test.

### Behavioral controls

Controls such as a forced globalcolor choice intentionally alter compiler
behavior. They are useful for questions like:

> If this web were assigned the target register, would the remaining object
> become exact?

An affirmative result isolates cause. It does not show that the original
compiler contained that control or that a forced object is an acceptable
decompilation result.

## Basic ugen call/free-list hooks

```sh
decomp-workbench instrument-ugen \
  /path/to/generated/ugen.c \
  /tmp/ugen.traced.c
```

Compile the result as the upstream project normally would, then enable:

```sh
DKWB_UGEN_TRACE=1 /path/to/traced-cc ...
```

The generated source emits:

- `DKWB-CALL` entry/exit records for selected `f_*` functions;
- `DKWB-FREELIST` records at known allocator/free-list helper entries, stamped
  with the target-procedure ordinal (`proc=`), current forward-ibuffer emitted
  ordinal, and ugen's current source line (`line=`, the value `f_warning`
  prints as `line %d`). The source line
  ties a temp-ring pop to the construct that consumed it: two pops on one line
  is a phantom pop (e.g. a redundant `x & 0xFFFF` on a byte field allocates a
  temp that is folded away, advancing the ring one phase), and the line that
  gains or loses a pop is the exact source statement to edit.

Restrict function tracing:

```sh
decomp-workbench instrument-ugen ugen.c ugen.traced.c \
  --functions '^(f_(alloc|get_free|free|add_to|remove_from|move_to).*)$'
```

#### Which free-list hook actually fires

`ADD` records come from `f_add_to_free_list`, which a recorded campaign
measured as running only inside `f_init_regs` — ten calls for a
4644-instruction procedure. It shows the initial pool being built and says
nothing about the allocations that follow, so a study of "which register does
the n-th temporary get" that hooks there will see nothing and conclude wrongly.
The hooks that fire per allocation are `f_get_free_reg` (`ALLOC_GP` /
`ALLOC_GP_RESULT`, integer), `f_get_free_fp_reg` (`ALLOC_FP` /
`ALLOC_FP_RESULT`, floating point), and `f_free_reg` (`FREE`). Note that
`f_alloc_reg` (`ALLOC`) does *not* fire in the sampled procedures, and
`f_remove_from_free_list` (`REMOVE`) is dominated by the `v0`/`v1` setup
removals — neither is the integer temp-ring pop.

#### `ALLOC_*` is the request; `ALLOC_*_RESULT` is the allocated register

`f_get_free_reg` and `f_get_free_fp_reg` are each handed a class/hint
descriptor in `a0` and *return* the register they chose in `v0`. The entry hook
can only see `a0`, so the `ALLOC_GP` / `ALLOC_FP` record stamps the request,
not the result — a recorded trace showed `a0` values such as 96, 176, and 208
that no object uses as that register. A second hook injected before the
function's return emits `ALLOC_GP_RESULT` / `ALLOC_FP_RESULT` carrying `v0`,
the register actually allocated. Read the two together: the same ordinal with a
request that resolves to an already-live register is a **phantom pop**, and the
`*_RESULT` stream alone is the temp ring in dequeue order.

The integer allocator returns a register directly (`0`–`31`), so an
`ALLOC_GP_RESULT` reads back as its conventional name (`reg=14` → `t6`). ugen
numbers an *fp* register as `32 + n` in the same unified space, so the fp temp
ring `$f4 $f6 $f8 $f10` arrives as `36 38 40 42` and `trace` names it back
(`reg=36` → `$f4`). A `reg` at or above 64 is the request descriptor, not a
register, and stays numeric. On the Mickey `func_80012574` fp-web case the fp
result stream is exactly `36 38 40 42` rotating — the `FP_LOCAL_RING` seen from
the pop side, independent of the globalcolor `bestcolor` decode.

This is a shallow allocator locator, not a complete allocator profile. The parser also
accepts deeper `CODEX-*` queue events, but `instrument-ugen` does not emit all
of them. The emitted ordinal is a real pass coordinate, not an inferred object
row; join it through `trace fifo --emission-map` as documented in
[Trace analysis](trace-analysis.md). Its call-frame helper uses the GCC/Clang
`cleanup` attribute.

### Procedure identity is producer-scoped

The default procedure boundary is `f_init_regs`, measured to run once per
target procedure in the supported generated ugen. `instrument-ugen` injects a
single ordinal increment there and stamps every free-list event with that
ordinal. Select another reviewed generated function with
`--procedure-function`; an empty value disables the hook for profile
development.

An ordinal alone is run-local. Bind it to the candidate's own retained Ucode,
where every `Uent` is followed by its procedure-name `Ucomm`:

```sh
decomp-workbench trace fifo ugen.log \
  --ucode build/retained.U --symbol demo \
  --candidate-object build/demo.o --json
```

The resulting `decomp-workbench-ugen-procedures-v1` block hashes the retained
Ucode and optional candidate object, maps the unique symbol to its ordinal, and
uses that ordinal to scope FIFO replay. A mixed-procedure trace is refused
unless `--proc` or the Ucode/symbol pair selects one procedure. Mixed scoped
and legacy unscoped events are also refused rather than silently joined.

This is candidate evidence only. Machine code does not retain the allocator's
producer events, so the map never claims to reconstruct a target trace.

## PRE and speculative-hoist decisions

`trace pre` reads stable `[DKWB-PRE-V1]` records. Every event names procedure,
block, expression identity, decision, reason, and source line; candidate,
availability, and cost are optional. Decisions are exactly `insert`, `hoist`,
`retain`, `reject`, or `kill`.

```sh
decomp-workbench trace pre pre.log --proc 3
decomp-workbench trace pre target-pre.log --against candidate-pre.log --json
```

Diffs align by procedure/block/expression and name the fields that changed.
They are compiler-decision evidence, never source originality or object-match
evidence.

Generated uopt layouts differ, so the workbench supplies a guarded adapter,
not a pretend-universal patch:

```sh
decomp-workbench instrument pre generated-uopt.c traced-uopt.c \
  --profile pre-profile.json
```

The `decomp-workbench-pre-profile-v1` document pins the exact input SHA-256 and
lists uniqueness-checked `anchor`, `text`, and `position` injections. The
injected source must visibly emit every required named field. It becomes
supported evidence only after tracing-off section identity, accept and reject
positive controls, and collateral-procedure gates pass. No reviewed generated
uopt source is bundled with the package.

## Pinned uopt profiles

Apply both compatible profiles in one guarded operation:

```sh
decomp-workbench instrument-uopt \
  /path/to/generated/5.3/uopt.c \
  /tmp/uopt.traced.c \
  --profile alias \
  --profile globalcolor
```

The command validates the pristine input once, applies profiles in a stable
order, and validates every source anchor. Use the narrower commands below when
only one trace family is needed.

### Globalcolor profile

```sh
decomp-workbench instrument-uopt-globalcolor \
  /path/to/generated/5.3/uopt.c \
  /tmp/uopt.globalcolor.c
```

#### Globalcolor environment variables

| Variable | Effect |
|---|---|
| `CDX_LOG=1` | Emit `[CDX]` decision records |
| `CDX_PROC=N` | Restrict logs and controls to globalcolor invocation `N` |
| `CDX_PROC=name` | Refused with an explanation; emits the `procindex` table so the ordinal can be chosen |
| `CDX_DETAIL_WEB=N` | Emit IR metadata, interference neighbors, and every evaluated color cost for web `N` |
| `CDX_DETAIL_WEB=all` | Emit IR metadata and every evaluated color cost for all allocator decisions, without neighbor expansion |
| `CDX_LINEAGE_TABLES=688,1004` | Emit live-range creation and member records for these pre-globalcolor ICHAIN table IDs (`all` is accepted for small inputs) |
| `CDX_OUT=FILE` | Write diagnostics to a file instead of stderr |
| `CDX_FORCE=p1:w9=c30` | Force phase-one web 9 to color 30 for the selected procedure |
| `CDX_FORCE=p2:w55=c2` | Force phase-two web 55 to color 2 for the selected procedure |
| `CDX_FORCE=p1:w9=s` | Force the split/no-color path for phase-one web 9 |

#### Phases are separate web spaces

Phase one colors callee-saved candidates and phase two colors caller-saved
candidates, and the two emit **disjoint** web numbering: `w55` in phase one and
`w55` in phase two are different webs. Every record carries `phase=p1` or
`phase=p2`, and every force key must name its phase.

An unqualified `CDX_FORCE=w55=c2` is refused — by `campaign --env` before a
compile is spent, and by the instrumented pass itself, which exits with a
message naming both namespaces. This is a correctness gate: an "exhaustive"
26-web sweep that was silently phase-one only produced a wrong exoneration in
the field, and the residual turned out to be phase-two web 55.

`trace-globalcolor` prints the ready-to-use key for every reported web as
`force_key=p2:w55`.

#### Colors are decoded to registers

Records print the machine register beside the color (`bestcolor=2 bestreg=v1`,
`color=2 reg=v1`), and `trace-globalcolor` decodes recorded colors the same
way, including in the per-color cost list (`c2(v1):22.25`). The mapping is one
table in the workbench, rendered into the generated C so the pass and the
reader can never disagree:

| Colors | Registers | How it was established |
|---|---|---|
| c1–c5 | `v0 v1 a0 a1 a2` | Empirically confirmed: each color was forced with `CDX_FORCE` and the resulting object diffed to see which machine register moved |
| c6–c12 | `a3`, `t0`–`t5` | Continuation of the caller-saved pool order decoded from the compiler's `coloroffset` table, consistent with black-box pool probing |
| c14–c22 | `s0`–`s8` | The stable callee-saved block, in use since before this table existed |
| c23 | `ra` | `coloroffset` table |

**Provenance and limits.** Only c1–c5 have been proved by force-and-diff on a
real build. The rest come from the `coloroffset` table decode plus pool-order
probing; they are consistent with every trace seen so far but have not each
been individually forced. The table is pinned to the IDO 5.3 profile and is not
claimed to hold for other IDO releases.

Colors outside the table — including c13 and everything above c23 — stay
numeric in both the records and the reports. Naming them would be a guess, and
a wrong register name is worse than a number. If you confirm one, add it to
`COLOR_REGISTERS` in `globalcolor.py`: the generated C table is rendered from
that mapping, so the pass and the reader cannot disagree.

#### Selecting a procedure by name

`CDX_PROC` takes the globalcolor invocation ordinal. A symbol name cannot be
resolved at this layer — the instrumented sites see procedure ordinals and
symbol *numbers*, never linker names — so a non-numeric value is refused with
an explanation instead of being `atoi()`d to procedure 0, which twice produced
a wrong conclusion by tracing an unrelated function.

When a name is given, the pass logs every procedure and emits an index table:

```text
[CDX] procindex proc=0 decisions=12
[CDX] procindex proc=1 decisions=147
[CDX] procindex proc=2 decisions=3
```

`decisions` counts allocator decisions in that invocation. It is a size proxy,
not an instruction count, and it is enough to align ordinals with functions in
compilation order. Pick the ordinal and re-run with `CDX_PROC=<ordinal>`; force
controls stay disabled until one is selected.

`trace-globalcolor` joins `p1dec`/`p2dec` records to matching target
`webdetail` records and reports them as allocator webs. `--proc` and `--dtype`
filter this joined view, so CDX-only traces remain useful even when they do not
contain the older `CSAVE`/`CUP` live-range format.
Current `webdetail` and interference records carry the same explicit `p1`/`p2`
namespace as decisions. Older phase-less detail is joined only when that
procedure/web number has a single recorded phase; an ambiguous number is
withheld rather than cross-contaminating the two allocator passes.

The joined record also contains `color_costs`. Each entry identifies the
caller- or callee-saved color, its final cost (including any first-use
surcharge), and the best cost immediately before that color was considered.
This makes exact ties and scan-order tie breaking visible.

Decision records include the available-color masks, the `allcallersave`
setting, and whether colors 1 and 2 are already present in the procedure's
register-use table. Those fields explain the allocator's secondary preference
when several colors have equal cost.

Multiple force entries are comma-separated (`p1:w9=c30,p2:w55=c2`).
`CDX_FORCE` is ignored unless `CDX_PROC` selects one globalcolor invocation;
this prevents an experimental choice from being applied to the same web number
in unrelated procedures. Here `wN` is the allocator bit position printed as
`web=N`; `sym` is reported separately and is not the force key.

#### Trace live-range formation before coloring

`webdetail` is a final allocator snapshot. To see how the represented live
range was formed, enable `CDX_LINEAGE_TABLES` together with `CDX_LOG=1` and a
numeric `CDX_PROC`. The profile emits `lineage_range` when `formlivbb` creates
the range and `lineage_member` for each live-block member, including the ICHAIN
table/chain identity, block number, line, and six retained membership flags.
Its `proc` is a run-local `makelivranges` invocation ordinal, counted
independently from the later globalcolor hook. The pinned profile expects those
calls to be one-to-one; confirm that the selected capture contains both lineage
and allocator decisions before treating their ordinal join as evidence.

Inspect one or more table identities without mixing procedure invocations:

```sh
decomp-workbench trace-globalcolor TRACE.log \
  --proc 0 --lineage-table 688 --lineage-table 1004
```

When `--web` has a joined `webdetail.table`, the command automatically includes
matching lineage records. Table/chain identities are earlier and usually more
stable than run-local web numbers, but they are still compiler IR identities.
They do not recover a C identifier or satisfy `source_semantic`; use controlled
one-operation source probes for that attribution boundary.

#### A forbidden color is declined, not fatal

A web's interference mask forbids some colors outright. Forcing one of those
used to abort the compiler with `SIGABRT`: six probes across three campaigns
could not be run at all, including an endpoint confirmation that would have
closed a residual, and a sweep that hit one lost every result after it.

The pass now **declines** such a force. It records the decline and lets the
natural decision stand:

```text
[CDX] force_declined phase=p2 site=dec proc=11 web=300 color=2 reg=v1 \
  forbidden=0x7f80000000000000
```

- `site=dec` is the allocate-or-split decision; `site=color` is the assignment
  that follows it. A force that is declined at both prints twice, because the
  pass made two decisions and honored neither.
- `forbidden` is the web's two mask words concatenated, high word first. Color
  `c` occupies bit `31 - c` of the high word (`0x7f800000` is exactly c1–c8),
  and bit `63 - c` of the low word above c31. `trace-globalcolor` decodes the
  same mask into `forbidden_colors`, so a sweep can be planned from a single
  logging run instead of discovered one abort at a time.
- The record prints **whether or not `CDX_LOG` is set**. This is the point of
  the change: a declined force that behaved like a silent no-op would be
  indistinguishable from a force the pass never saw, and "the object did not
  change" would then have two very different meanings.
- `p1:w9=s` forces the split path rather than a color, so no mask can forbid it
  and it is never declined.

A declined force is evidence, not a failure: it says the endpoint you were
probing for does not exist under this interference, which is often the answer
the probe was asking for. The sweep still finishes, and every other entry in it
still applies.

#### Three ways a force does nothing and says nothing

The decline record above covers the forbidden-colour case. Three other ways to
get a no-op are **toolchain-side** — they are properties of the instrumented
`uopt` a campaign is holding, not of any workbench command — and all three read
as "the object did not change", which is exactly what a *successful* byte-inert
force also reads as. Check them before concluding anything from a null result.

- **A split child declines silently.** Forcing a web that `f_split` has already
  divided leaves `forced=-2` in the records and emits **no** decline record and
  no reason. `forced=-2` is the same value a web that was never named by
  `CDX_FORCE` carries, so the log cannot distinguish "declined because it is a
  child" from "never asked". Read the family with `trace-cascade` first: if the
  site has more than one round, the web number you are forcing may be a child
  of an earlier decision. A decline record naming the cause is the fix, and it
  belongs in the instrument.
- **`=n` does not exist.** The 5.3 instrumented `uopt` accepts `=c<N>` and
  `=s` and nothing else. A control spelled `p1:w9=n` — intended to force the
  *colourability verdict* rather than the colour — is not a grammar this pass
  has, and `parse_force_specification` refuses it before a compile is spent.
  Whether a web is coloured at all is decided earlier, by `compute_save`'s
  `save > 0` gate, which no shipped control reaches. See the grammar limit
  under [force rows](#which-object-rows-does-a-force-actually-own) below.
- **Forces need `CDX_PROC`.** Until a procedure ordinal is selected, force
  controls stay disabled — deliberately, so a sweep cannot apply one
  phase-one control to every procedure in the translation unit. The shipped
  profile writes `DKWB: CDX_FORCE ignored without CDX_PROC` to stderr and
  clears the control, so this one is visible **if the capture keeps stderr**.
  A driver that redirects only stdout gets a normal object, no decline
  record, and no notice.

#### Which object rows does a force actually own?

A web number is not a location. It indexes a run-local allocator table that
does not survive into the object, and a recorded campaign measured that the
intermediate stream's ordering does not imply the object's: a change confined
to sixteen `uopt.O` records 18% into the stream first moved the object at
instruction 94, with 143 differing rows *before* the edited site. So the
web-to-row map cannot be read. It has to be measured, by building the same
source twice and seeing which rows move:

```sh
decomp-workbench force-rows      baseline.o forced.o --force p1:w9=c30
decomp-workbench force-rows-dumps baseline.d forced.d --force p1:w9=c30 \
  --target target.d
```

```text
force=p1:w9=c30 aligned_rows=1204 moved=42 runs=6
  run   1  rows 860-868  moved=9  classes=register  compare_row=863
        baseline: lwc1 $f4,0(at)
        target:   lwc1 $f4,12(at)
```

The two builds are **inputs**. This command runs no compiler, so the join works
for any control a reader can set, on any toolchain, with no assumption about
how the forced object was produced. What it does own is the alignment:

- runs come from the same LCS aligner `compare` and `window` use, so a force
  that changes the instruction *count* is one run and not "everything after the
  insertion". A positional diff of the two disassemblies gets this wrong, and
  gets it wrong silently;
- `--target` adds `compare_row`, the aligned row number `compare --json`
  publishes as `aligned_row` and `window --rows` accepts. Without it the run is
  still reported, in the baseline-versus-forced numbering only;
- `--gap N` is how many matched rows may sit inside one run before it splits
  (default 3; `--gap 0` reports strictly contiguous runs);
- a control that moves nothing prints `BYTE-INERT`. That is a result: the force
  reached the pass and changed no emitted instruction, so the web owns no row
  here. It is not an empty screen.

`--force` is validated by the same parser the instrumented pass uses, so a
control this command will label a run with is a control the pass would accept —
including the phase qualification. It is a label, not an instruction: the
command cannot verify that `forced.o` was in fact built with it.

**Grammar limit.** The shipped profile's controls are `c<N>` (force a color)
and `s` (force the split path). Both express *which* register a coloured web
gets; neither expresses whether the web is coloured at all, which is decided
earlier by `compute_save`'s class verdict. A campaign extension adding `n`/`y`
for that verdict is recorded in
[the roadmap](roadmap.md) and is not part of this grammar.

#### Reading `p1dec`/`p2dec` economics

Three fields in the decision records are easy to read as something they are
not, and a recorded campaign ranked or picked webs by the wrong quantity
before checking each one:

- **`class=`** is the IR register class (integer versus floating point), from
  `regclassof`. It is **not** the save class — the class-1/class-2 verdict that
  decides whether the web is a colouring candidate at all is not in this
  record, and no shipped field reports it.
- **`nocs=`** is the compressed divisor the pass computes, `((n - 2) >> 2) + 2`
  for `n` occurrences, not the occurrence count `n`. Ranking by `save * nocs`
  is therefore not ranking by "saving times uses"; `save` is already the
  per-web figure the pass compares.
- **`available0=`/`available1=`** is **not** "colours still free" — it is the
  **minimum-cost tie set**. `uopt` keeps this pair of words at `sp+212`/
  `sp+216` across the whole cost sweep for the web: it **resets** to just the
  current color on a strictly *lower* cost and **ORs** the current color in on
  an exact *tie*. What survives to the decision site is every color that
  shares the cheapest measured cost, not every color the allocator could
  legally still assign. Several stages read it as the free/available set and
  treated any listed color as an equally legal substitute for another.
  That reading is coincidentally right in exactly one case: when the winning
  `bestcost` is the caller-save 0.0 tier, every caller-save register ties at
  zero, so "tied for cheapest" and "still free" name the same set there. At
  any other cost tier they diverge. The workbench reads this field as
  `AllocatorWebDecision.mincost_tie_colors` (`mincost_tie_colors`/
  `mincost_tie_registers` in `web_report`'s JSON) — same 64-color bitmask
  convention as `forbidden0=`/`forbidden1=` (`1 << (31 - color)`), decoded by
  the same code, under a name that says what the bits mean instead of what a
  reader might assume. The raw `available0=`/`available1=` strings are
  unchanged in the record and in `AllocatorWebDecision.fields`, for anything
  already reading them by that name. Confirmed against a recorded trace:
  `available0=0x1c` decodes to `{c27, c28, c29}`, independently identified
  from the same trace by hand.

`save`, `totalsave`, and `bestcost` are the pass's own floats at the decision
and are reported as measured.

### Campaign-local patches that are kept, not remembered

The shipped profiles are what `instrument-uopt` writes. Some records the
workbench *reads* come from patches it does not ship — `savedetail`, `saveocc`,
and the `symtab` itable dump. `trace-cascade --grammar` marks every record
SHIPPED or CAMPAIGN-LOCAL, so a log can be checked against a reader without
running anything.

Those patches now have a home:
[`src/decomp_workbench/patches/`](../src/decomp_workbench/patches/README.md).
The precedent is unhappy — an earlier CDX patch was recorded as **lost**, the
instrumented binary outliving the source that made it, and two campaigns paid
for the recovery. Each entry there carries the diff, the base file's sha256,
the sha256 the patch produces, the rebuild recipe, and the fidelity gates the
rebuild owes.

`uopt-5.3-cdx-symtab.patch` adds one environment variable:

| Variable | Effect |
|---|---|
| `CDX_SYMTAB=1` | Dump `uopt`'s whole per-procedure itable once per procedure; honours `CDX_PROC` and `CDX_OUT`, independent of `CDX_LOG` |

The itable is what `sym=` indexes everywhere else in the grammar, and it is a
hash table of expressions in **first-occurrence order**. `trace-frame` reads
the dump; [the frame ladder](cdx-cascade.md#the-frame-ladder) is the page about
reading it.

Two facts about it are worth having before you reach for the patch. The input
ucode carries **no names** — every local, parameter, and temp is a bare
(class, offset) pair, so `name=` in the record is the itable kind and no patch
can make it a symbol name. And stock `uopt -Wo,-zdbug:2` already writes the
same table to `./uoptlist` with no patched compiler at all; the patch is for
when you want it in one log beside the CDX web records.

### Alias and base-provenance profile

```sh
decomp-workbench instrument-uopt-alias \
  /path/to/generated/5.3/uopt.c \
  /tmp/uopt.alias.c
```

Set `DKWB_UOPT_ALIAS_TRACE=1` while compiling to emit:

- `DKWB-BASE` when the pass observes a base in a register, including the
  register, descriptor type, symbol, address, prior-state flag, and `fresh`,
  `direct`, or `retain` path;
- `DKWB-ALIAS-QUERY` at the profiled base-noalias return, including both
  descriptors and the `may-alias` or `no-alias` outcome.

Summarize a captured log with:

```sh
decomp-workbench trace-alias uopt.log --show-queries
```

The profile observes the pinned sites; it does not grant alias relationships
or change the return value. Its current-register association follows the
profiled pass's observed call path, so validate it with a positive-control
microcase before interpreting a new workload.

### Input identity

Both profiles support this generated source:

- upstream: `decompals/ido-static-recomp`;
- upstream commit used to generate the profile:
  `9c242adc890beef098020149d9554f48208f699d`;
- generated `build/5.3/uopt.c` SHA-256:
  `b0058f1559441c1a194d649271eb43b8637ec255682cfdd629031340b915b13f`.

Every profile command validates the SHA and every source anchor. It refuses a
different file by default. `--allow-unverified-source` exists for profile
development, not routine use; review the resulting diff and run all fidelity
gates.

### Copy/coalescing decision traces

Research producers may emit `CDXW ... COPYDEC` snapshots around live-range
formation and coloring. Analyze a final snapshot with:

```sh
decomp-workbench trace-copy-decisions baseline.trace
decomp-workbench trace-copy-decisions baseline.trace \
  --against variant.trace --proc 0
```

The report treats `rhsformed=1 -> TEMPCOPY` and
`rhsformed!=1 -> COALESCE` as direct producer observations. It aligns two
final snapshots by the LHS virtual stack home and assignment ordinal, then
shows formation, color, and outcome changes. That alignment is a controlled
differential hypothesis, not source attribution; always compare the emitted
objects too.

`rhstable` and `rhschain` are exposed as `rhs_hash_bucket` and
`rhs_hash_chain`. They are collision-prone hash-table observations. Earlier
research notes incorrectly described a shared bucket as expression identity
and its population as CSE multiplicity; distinct expressions have been
observed in the same bucket. Numeric statement and bit IDs are run-local for
the same reason. The analyzer warns about both limitations instead of turning
them into source advice.

The parser is supported, but the current copy-trace producer remains a
hash-pinned research profile until its generator and full fidelity matrix are
promoted alongside the existing uopt profiles.

### Scheduler-selection traces

#### For IDO 5.3, the assembler already ships one

Before patching anything, try this:

```sh
cc -Wa,-R -c source.c >sched.log 2>&1
```

```sh
decomp-workbench trace-scheduler examples/traces/as1-reorganize.log --from-as1-r --block 429
```

```text
scheduler: 4 event(s), 2 ready-set tie(s)
proc=0 block=429 cycle=1 word=0x2418000a opcode=addiu line=16408 ready=2 chosen=n1 tie=lineno
```

`as1` carries its own list-scheduler trace behind the `-R` (reorganize)
option — option-table index 13 of the 106-entry table `f_which_opt` reads —
and `cc` forwards `-Wa,-R` to it. There is **no patched compiler**, and
therefore no profile to hash-pin and no fidelity gate to record beyond the one
the campaign that found it already recorded: an object built with `-Wa,-R` was
`cmp`-identical to the same object built without it, whole file, not merely
section-scoped. The trace goes to stderr, so a capture that redirects only
stdout keeps the object and loses the trace.

The native records are *richer* than `DKWB-SCHED-V1` — the whole per-block DAG,
with `before`, `aftercycles`, `maxhazard`, and successor latencies — which is
why the reader parses them natively and converts, rather than asking you to
convert first. `--emit PATH` writes the `DKWB-SCHED-V1` form for the commands
that read it.

The deciding key is **computed** by the reader, not read: the schema has no
field for the losing candidates, and without the losers there is nothing to
compute a tie from. The chain is the lexicographic minimum of

```txt
( start_time, -besttime, -aftercycles, -latency, node->addr, node->lineno, ready-list position )
```

each step a strict accept / not-equal reject. A leading `-` marks a key that
is **maximised** (higher wins); the rest are minimised (lower wins). The
direction matters most for `node->lineno`, which is the one key with a source
lever attached.

`besttime` outranks `aftercycles`, which is a correction to an earlier
published chain. A recorded block picks `aftercycles=0` over `aftercycles=1`
because the winner's `besttime` is higher; the reader used to label that
`aftercycles-disagrees` and name no key at all. It is not the outright primary
key either — the shipped `examples/traces/as1-reorganize.log` has a selection
that `besttime` alone decides the wrong way.

Two more things follow, and both are printed with the report rather than kept
here:

- **`node->lineno` is a source physical line number.** Key five means source
  whitespace is a codegen input: folding two statements onto one physical line
  makes their line numbers equal, and lets key six — ready-list position —
  decide instead. One campaign closed eight mismatched rows with a
  whitespace-only edit this way.
- **`node->addr` is not in the record per candidate**, only on the chosen node.
  The reader evaluates the other keys and, when the named key does not select
  the node the assembler picked, reports the key as `*-disagrees` rather than a
  clean tie.

`cycle=` is the selection ordinal within the block. `as1` prints no cycle
counter, and the ordinal is what two traces align on.

`instrument-scheduler` below remains the answer for an era whose assembler has
no built-in trace, or when a field the built-in trace does not print is needed.
For IDO 5.3 it is unnecessary.

#### The stable named schema

The `vsprintf` endgame used an early private pointer dump to reduce the last
two-word residual to one ready-set tie. That unlabeled format remains
unsupported. The workbench also supports the replacement interface:

```txt
[DKWB-SCHED-V1] proc=1 block=2 cycle=3 word=0x8c220000 \
opcode=lw line=9 ready=2 chosen=n4 tie=source-order \
slot=7 file=demo.c statement=14 reason=latency ready_ids=n4,n9
```

Read and compare stable records:

```sh
decomp-workbench trace-scheduler examples/traces/scheduler.log
decomp-workbench trace-scheduler target.log --against candidate.log
```

Every field is named and strictly parsed. Reports can filter one procedure or
block, align two traces by procedure/block/cycle, and distinguish opcode,
source-line, ready-set, chosen-node, and tie-break changes.

The fields after `tie` are optional for existing profiles. A profile that sets
`provenance_required=true` must emit `slot`, `statement`, `reason`, and
`ready_ids`; instrumentation refuses the profile when any token is absent.
The parser also requires exactly `ready` unique IDs and requires `chosen` to be
one of them. An event counts toward `provenance_complete` only when slot, source
file and statement, reason, and that validated ready set are all present.
`file` is optional. Reports preserve those fields, include them in aligned
diffs, and print `provenance=N/M` so partial captures cannot look complete.
This exposes which ready instruction occupied an emitted slot and why. It does
not imply that a C-level lever can change that choice.

Generated compiler C is still revision-specific, so the repository does not
bundle a pretend-universal as1 patch. Apply a project-owned, hash-pinned
profile:

```sh
decomp-workbench instrument-scheduler generated-as1.c traced-as1.c \
  --profile scheduler-profile.json
```

The adapter checks the exact input SHA-256 and every source anchor, refuses an
existing output, and reports required calibration gates. A scheduler positive
control must record at least one real ready-set tie (`ready >= 2`); uncontested
selections do not establish that tie-break instrumentation works.

The profile is supported evidence only after trace-off section fidelity,
positive control, unedited replay, collateral, and project-output gates are
recorded by a real-copy [toolchain](toolchain-calibration.md). A scheduling
trace explains a compiler decision, never the original C.

## Required fidelity gates

For each profile and host:

1. Hash the unmodified generated source.
2. Build stock and instrumented passes with identical host flags.
3. Compile a positive-control microcase with tracing off through both.
4. Compare pass outputs **section by section**: `.text`, `.rodata`, `.data`,
   relocations, and the symbol table must be byte-identical.
5. Compile the target translation unit through both, with the same
   section-scoped comparison.
6. Compare the target and already-matching collateral functions.
7. Rebuild and verify the complete ROM or binary.
8. Turn tracing on and prove the expected diagnostic appears.
9. If using a behavioral control, prove the disabled control returns to the
   stock output.

### Record steps 4 and 5, do not remember them

Steps 4 and 5 are the identity gate, and they are the ones campaigns skip —
not by deciding to, but by running them once, by hand, and leaving no record. One
campaign built roughly twelve instruments across four compiler passes and the
only evidence that any of them had been gated was a stage's own sentence saying
so. A reader arriving at one of those traces three stages later has nothing to
check.

```sh
decomp-workbench instrument gate \
  --stock stock.o --instrumented cdx.o \
  --profile uopt-cdx --stamp gates/uopt-cdx.json
```

The comparison is the section-scoped one below, unchanged. What the command
adds is the stamp: the profile, both objects with their hashes, the sections
gated, the objdump that read them, and the sentence naming what the gate does
and does not claim. It exits `1` when the gate fails, so a build script can
stop.

```sh
decomp-workbench instrument gate --verify gates/uopt-cdx.json
```

`--verify` **re-runs** the comparison rather than re-reading the record, and
reports `STALE` when either object has moved or changed underneath the stamp. A
record that could only be checked against itself would be a record of an
intention.

Two things this deliberately does not do. It does not build a compiler:
building means invoking your build system, and the package does not run
user-supplied build commands — every alternative either reintroduces the shell
or constrains the recompilation trees it can serve to the one it was written
against. And it says nothing about a trace's *record grammar*: the gate is
about objects, and each instrumented pass keeps its own reader.

### Byte identity is section-scoped, not file-scoped

Gate on sections, not on whole-file hashes. Stock IDO `cc` under `-g3` is not
file-level reproducible: `.mdebug` varies between runs of the *unmodified*
compiler, so a whole-file comparison reports a difference that has nothing to
do with the instrumentation and hides the sections that matter. Compare
`.text`, `.rodata`, `.data`, relocations, and symbols; treat `.mdebug`
differences under `-g3` as expected noise, and if debug-section fidelity itself
matters, gate it separately with `-g0` or `-g1`.

### What the workbench's own tests cover

The unit tests cover *generation*: the pinned source hash, every anchor, the
emitted record schema (phase tags, decoded registers, the `procindex` table),
the phase-qualified force-key parser, and a host-compiler build of the injected
header so a syntax or type error cannot ship. They deliberately stop there.

Executing the instrumented pass needs the external research toolchain, so the
evidence cells remain user-run integration checks. The workbench can
materialize and hash that external tree, compare object pairs section by
section, require a scheduler tie positive control, record unedited replay and
collateral cells, and exact-hash the final project output through
`toolchain init/calibrate/status`; see
[External toolchains and calibration](toolchain-calibration.md). A green
package suite means the adapters and gates are well-formed, not that a
particular external build has passed them.

## Profile development

Generated C is coupled to an input binary and static-recompiler revision.
Prefer a small patch generator with exact anchors over committing an enormous
diff of generated source. Record:

- input executable/version;
- static-recompiler commit;
- generated-source hash;
- all emulated addresses and what established them;
- trace schema;
- control semantics;
- positive and negative controls.
