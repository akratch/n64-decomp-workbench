# AS1 admission and rollback predicates

The native [motion reader](as1-motion.md) identifies accepted motion and its
post-move blocks. This optional, trace-only producer adds the decisions native
`-xbbdbg` does not emit: admission predicates, path definition masks, and actual
trial/accept/rollback outcomes. It does not change matching verdicts or provide a
source rewrite automatically.

## Authenticated producer

The profile supports only generated `build/5.3/as1.c` from
[`ido-static-recomp`](https://github.com/decompals/ido-static-recomp), revision
`9c242adc890beef098020149d9554f48208f699d`, with SHA-256
`905927751a79aba82d332bdce254b2b30a4312ae14a4108897e11b48487d17a1`.
Unknown hashes, repeated instrumentation, missing anchors, and changed branch
counts are rejected. There is no force or unverified-source option.

The profile instruments 29 pure register predicates in `func_42a028` and 30 in
its path helper `func_429928`. Site IDs are their source-order branch ordinals:
`admit-00` through `admit-28`, and `path-00` through `path-29`. The generated
manifest contains each exact condition and raw register operands. A true branch
is **not necessarily a rejection**. Repeated visits remain separate records.

The following field meanings were checked against generated producer code:

- Basic-block identity is the index at block offset 64. IDs are local to an
  invocation of `f_do_xbb_opt`; the invocation counter is not a procedure or
  optimization-round identity.
- `f_defuse` writes definitions through its first output pointer and uses through
  its second. Its LUI case and calls to `f_addset` establish that direction.
  `f_addset` uses MSB-first register masks: ID `r` occupies bit
  `0x80000000 >> (r % 32)` in word `r / 32`; IDs span 0–71. These are compiler
  register IDs, not source variables. Register zero is not added.
- In `func_429928`, `s3` points at candidate definitions. The three words at
  helper stack offsets 96/100/104 accumulate path definitions. The contribution
  hook at `L429c14` records the individual definitions before accumulation;
  `L429cac` records the aggregate. The block index was saved at stack offset 140;
  the instruction slot is the current 40-byte record offset divided by 40.
  `path-28` rejects an intersection between candidate and path definitions.
  Other path checks, including uses and liveness, remain raw predicates.
- `func_42aa0c` at `L42ae90` has the old and freshly rescheduled source and
  destination costs. `L42aedc` enters restoration; `L42afe8` accepts the trial.
  These three sites produce `trial`, `rollback`, and `accepted`, respectively.
  The context field is the raw word at stack offset 108. Do not rename it to a
  source semantic property: its nonzero value permits destination-cost growth
  after strict combined-cost improvement. Both new costs must also avoid the
  scheduler failure sentinel. The reader reports actual outcomes, not a guessed
  rejection from a missing native move.

All inserted hooks read existing state and write diagnostic output only. They
neither change simulated registers/memory nor replace branch conditions. The
host-side counters and candidate-slot context are diagnostic state. Trace-off
still increments those counters but emits nothing.

## Private build and validation

Generate a private copy; never edit or distribute the original compiler source:

```sh
PYTHONPATH=src python3 -m decomp_workbench.instrument_as1_motion \
  "$IDO_RECOMP/build/5.3/as1.c" \
  --output build/as1-predicates.c --manifest build/as1-predicates-sites.json
cc -O2 -w -fno-strict-aliasing -I "$IDO_RECOMP" \
  -o build/as1-predicates build/as1-predicates.c \
  "$IDO_RECOMP/build/5.3/libc_impl.o" \
  "$IDO_RECOMP/build/5.3/version_info.o" -lm
```

Use a private compiler-driver directory with the normal driver and other stages,
replacing only its assembler with this binary. A symlink to the original driver
may resolve its original stage directory; copy the driver into the private
folder when needed. Keep flags and all other stages identical to the stock
build. Set `DKWB_AS1_MOTION_TRACE=1` to emit records. Optional decimal
`DKWB_AS1_MOTION_SRC` and `DKWB_AS1_MOTION_DST` select block IDs. These are trace
filters only; no records cannot prove no motion. Leave the variables unset for
an unfiltered run.

Capture stderr separately from stdout. Native AS1 diagnostics may use buffered
stdout; merging streams can interleave fragments and corrupt a record.

```sh
DKWB_AS1_MOTION_TRACE=1 private-ido/cc [normal flags and inputs] \
  > build/compiler.stdout 2> build/predicates.log
PYTHONPATH=src python3 -m decomp_workbench.as1_predicates \
  build/predicates.log > build/predicates.json
```

The reader requires the pinned profile header for every invocation, preserves
query order and repeated predicates, and rejects conflicting endpoints,
incomplete queries, unpaired cost outcomes, invalid masks, unknown fields, and
interleaved records. `compare_queries` accepts explicit candidate slots; it does
not equate identities across runs. Profile headers alone authenticate a declared
format, not the compiler binary: retain compiler/source hashes and fidelity
receipts independently.

First compare stock against recompiled trace-off, then trace-on against stock:

```sh
decomp-workbench fidelity stock.o trace-off.o --objdump "$OBJDUMP" --json
decomp-workbench fidelity stock.o trace-on.o --objdump "$OBJDUMP" --json
```

Require text, data, rodata, relocation, and symbol gates. Whole-file differences
can come from object metadata and do not replace those gates. Repeat after
changing instrumentation or the host build. Traces, generated sources, compiler
binaries, objects, and manifests containing generated predicate expressions stay
private. The tests use invented metadata and miniature synthetic source only.

## Measured usefulness and boundary

The synthetic `examples/instrumentation/as1-motion-control.c` passed all five
fidelity gates with tracing off and on and exposed its one accepted move.
The full Mickey `overlay52TailB.c` control passed all five gates with tracing
off, filtered on, and unfiltered on. The unfiltered run recorded 236 queries:
143 with no admitted candidate, 70 accepted moves, and 23 actual rollbacks.
The first rollback retained both old schedule costs, distinguishing a failed
profitability trial from an admission failure. This is validation of this
profile on these controls, not a general equivalence proof for every input.

In the named address-motion question, the state-address candidate was rejected
at `path-28`: its GPR16 definition intersected four definitions in two path
blocks. The descriptor-address candidate defined GPR17 and had no intersection
against the same aggregate path masks; it was admitted and subsequently passed
the measured cost gate. The native adapter independently identified the accepted
address pair and its destination. No candidate source was changed or credited.

This eliminates a generic ready-order explanation for that distinction. It does
**not** justify manufacturing a GPR17 write, volatile access, padding, or a dummy
value. No newly supported C spelling was established in this packet. The next
smallest missing join is UGEN ownership of the address definition and of the
four interfering path definitions: emitted instruction ordinal, allocator
value/temp identity, source Ucode operation identity, assigned register, and
live-range endpoints. These must be captured at actual emission/allocation
sites and joined to the normal-g0 source identity producer with fidelity checks.
Call-bracket labels or equal instruction words alone cannot authenticate those
owners. A source experiment becomes admissible only when that join identifies
an existing value whose lifetime or evaluation point can change without
inventing behavior. Before/after native block evidence remains a separate
artifact; raw predicate truth is not a substitute for it.
