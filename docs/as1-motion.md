# Native AS1 cross-block motion

IDO 5.3 has a second useful native diagnostic alongside `-R`:

```sh
cc -Wa,-R,-xbbdbg,8 -c unit.c -o traced.o > native.log 2>&1
decomp-workbench trace-as1-motion native.log
decomp-workbench trace-as1-motion native.log --event 0 --json
```

Use the project's complete configured compilation command. Independently
compile without diagnostic options and run `decomp-workbench fidelity` on the
two objects before interpreting the trace. Capture both output streams. The
reader does not run the compiler or confer a fidelity/matching verdict.

`-R` describes local DAG selection. `-xbbdbg` describes accepted cross-block
moves: paired `MOVETO` and `MOVEFROM` records name the destination and source
block, instruction slot, and each block's old/new scheduling time. Level 2
prints those pairs; level 8 additionally prints the two post-move block dumps.
The reader preserves all accepted events in capture order, including repeated
block IDs. `--line N` selects the moved instruction's native physical line
when a destination dump is present. Labels/pseudo records occupy slots too;
these are not instruction counts or executable-byte offsets.

```sh
decomp-workbench trace-as1-motion first.log --event 2 \
  --against second.log --against-event 4 --json
```

A differential requires explicit event selection. It compares the two native
records, costs and block snapshots; it does not assert that the events belong
to the same value. Block IDs, slots and event ordinals are run-local. A source
change, another procedure, or another optimization round can reuse them.
There is no implicit ordinal, source-line or instruction-word identity join.

## Authenticated producer and cost gate

The option was authenticated in IDO 5.3's generated `as1.c`, SHA-256
`905927751a79aba82d332bdce254b2b30a4312ae14a4108897e11b48487d17a1`.
`f_which_opt` scans 106 entries; zero-based index 73 is `-xbbdbg`. The option
handler consumes its next argument as a decimal diagnostic level. Original
compiler data authenticates the strings used by this reader. The tested host
assembler's SHA-256 is
`46e76dd428651d77e478e4dab229fcd4a3179f3fc5794328a279780a9830673a`.
No compiler source or binary is distributed here.

In `func_42aa0c`, a candidate from `func_42a028` is tentatively inserted by
`func_42a47c`; `f_reschedule` then evaluates both blocks. The accepted path
requires a finite reschedule result and a strict reduction in their summed
scheduling times. A separate path condition can permit destination growth;
otherwise the destination must not get slower. Rejected trials restore the
instruction and reschedule both blocks. The native move messages occur on
the accepted path after this rollback branch. Thus they establish an actual
accepted move, not merely an instruction considered by the ready list.

The report exposes the measured sum reduction and destination increase.
These are compiler scheduling costs, not measured execution time, and they
do not include execution-frequency weighting. The dump's `!` marker is
preserved as `native_marked`; the reader assigns it no semantic meaning.

This is a source-hash-qualified reading of one producer, not a universal law
for every IDO assembler. Unknown or malformed motion records, orphaned pairs,
duplicate dump slots, and dumps ending before the named slot are errors.

## Real controls and limits

The original synthetic C fixture
[`as1-motion-control.c`](../examples/instrumentation/as1-motion-control.c)
produces one accepted move with `-O2 -mips2 -32 -G0 -non_shared`. Its summed
cost falls from 10 to 9; the destination remains at 3. Diagnostic-on/off
text, data, rodata, relocation and symbol fidelity pass.

A full configured Mickey translation unit containing
`func_overlay_052_F000063C_189ACAC` produces 70 accepted records. All five
fidelity gates pass against stock output; the whole files differ in debug
metadata. Its disputed address pair has two accepted move records, each
reducing the summed cost by one with unchanged destination cost. This is
useful causal evidence beyond the older `-R` selection trace. Detailed
object identities, native traces, block dumps and project receipts remain
private under ignored build directories.

The reader does **not** recover:

- rejected trials or the reason a candidate was never admitted;
- procedure or optimization-round identity;
- instruction identity across moves, relocation identity, or ELF offsets;
- the original pre-move instruction from an absent destination dump;
- original C expressions from physical source lines.

Post-move dumps have no explicit completeness marker. `*_dump_present` means
that the header and available records were seen; it is not a claim that every
trailing instruction was captured. Missing events do not prove rejection,
immobility, or trace completeness. A strict move/no-move differential still
needs an independently authenticated value and complete capture, and a C
change still needs semantic review and untouched-compiler matching proofs.

For source-pinned admission predicates, path definition masks, and actual
rollback outcomes, see [AS1 motion predicates](as1-motion-predicates.md).
