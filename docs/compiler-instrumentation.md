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
- `DKWB-FREELIST` records at known allocator/free-list helper entries.

Restrict function tracing:

```sh
decomp-workbench instrument-ugen ugen.c ugen.traced.c \
  --functions '^(f_(alloc|free|add_to|remove_from|move_to).*)$'
```

This is a shallow locator, not a complete allocator profile. The parser also
accepts deeper `CODEX-*` queue events, but `instrument-ugen` does not emit all
of them. Its call-frame helper uses the GCC/Clang `cleanup` attribute.

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

### Scheduler-selection traces: evidence and product bar

The `vsprintf` endgame used a temporary as1 selection trace to reduce the last
two-word residual to one ready-set tie. The wrong build selected encoded
`li 45` at cycle 4 with source line `0x30f`, then `li 10` at cycle 5 with line
`0x311`. Combined with controlled line-identity variants, that established the
line-number tie-break and justified a source-line experiment.

That temporary producer is deliberately **not** a workbench profile. It dumped
20 unlabeled words from a generated node and depended on emulated addresses in
one private build. Shipping a parser for that output would turn reverse
engineering the trace into a recurring user task.

A product-quality as1 scheduler profile must instead:

1. pin the static-recompiler revision, generated-source hash, and exact source
   anchors;
2. emit named fields—procedure, block, cycle, encoded instruction, decoded
   source line, ready-set size, and winning tie-break;
3. be entirely opt-in and section-identical to stock with tracing disabled;
4. pass an unedited as0/as1 replay before any edited replay is interpreted;
5. expose enough scope controls to capture one function/region rather than a
   megabyte of unrelated selections;
6. state that a scheduling trace explains a compiler decision, not original C.

Until those conditions are met, use `-g0` to narrow ownership, decoded line
tables to inspect tags, and `replay-as1` to test pass ownership. Capture a
temporary scheduler trace only for the smallest unresolved tie, and record the
field mapping beside the result.

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

Executing the instrumented pass needs the external research toolchain — a
statically recompiled IDO build that is neither redistributable nor
reproducible from this repository — so the gates above remain user-run
integration checks. A green test suite means the patch is well-formed, not
that a particular host build is faithful.

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
