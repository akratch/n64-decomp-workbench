# UGEN address operand ownership

This narrow producer and reader connect seven `f_emit_ra` call sites to the
actual owning tree node, its input Ucode record, `f_get_dest` result where used,
and exact retained binASM record. They distinguish a register assigned before
UGEN from a temporary UGEN selected. They do not infer a C rewrite, allocator
reason, target identity, or final stack home.

## Supported source and authenticated fields

The profile accepts only pristine generated IDO 5.3 `ugen.c` SHA-256
`4079660f9ebb068a791c6f54abb67cf7c3bb792207c89a6eb9ac2d9e146341ec`, inspected in
[`ido-static-recomp`](https://github.com/decompals/ido-static-recomp) revision
`9c242adc890beef098020149d9554f48208f699d`. Unknown hashes, an existing marker,
missing/duplicate anchors, changed call counts and changed return counts fail
closed. There is no unverified-input option. Keep generated sources and compiler
binaries private.

The join follows these producer sites rather than a call-bracket heuristic:

- `f_readuinstr` returns a decoded record through its original first argument.
  The hook captures that record after the read. The reader verifies the complete
  read count and every opcode/second-word pair against the retained input stream;
  an associated `rlda` also requires all four encoded words to agree.
- `f_new_tree` allocates a tree and writes its compiler ID into bits 8–31 of
  word 16. Every allocation receives a separate trace generation. A recycled
  address or ID does not inherit an old node's provenance.
- `f_build_u` copies eight words from its input pointer into tree offsets 32–60.
  The input snapshot must equal the latest read at that pointer, and the built
  copy must equal the input snapshot. Modified or unread inputs stay unresolved.
  Other tree-building/copy routes are not silently attributed to `f_build_u`.
- The three `f_loadstore` address-emission sites own node `s0`; the two
  `f_eval_mov` sites own `v1`; the two `f_eval` sites own `s6`. At each actual
  call, `f_emit_ra` takes opcode in `a0`, destination register in `a1`, symbol
  index in `a2`, addend in `a3`, and the extra relocation field at caller stack
  offset 16. The writer's bit packing authenticates those meanings.
- `f_get_dest` records the original node and register hint, the returned
  register, and the register stored in node byte 25 bits 1–7. The two `f_eval`
  address sites require that destination result to agree with emission.
- `f_clear_ibuffer` marks a new buffer epoch. `f_output_inst_bin` supplies its
  forward/backward record counts. It writes backward records first, then forward
  records; the normal main path emits bodies, emits declarations, and calls
  `f_cat_files` to put declarations before bodies. Those actual boundaries resolve
  an emission ordinal to a file record without searching for equal words. The
  reader checks total file extent and all four words of every owned address
  record. A missing concatenation boundary or conflicting record is an error.

The optional `.T` reader supports external dense-symbol names only, from the
big-endian IDO symbolic header, DNR and EXTR/string extents. It follows the
on-disk representation of `st_pdn_idn`, `st_psym_ifd_isym` and `st_str_extiss`;
it is not ELF symbol-table order. Bounds, overlap, external indices and string
termination are checked. Local names stay unresolved. UGEN may not have its
symbol table loaded while emitting, so the producer does not call runtime symbol
helpers or invent names from source text.

Raw snapshots contain decoded compiler records, including unused or stale union
members. They are not serialized stream bytes or permission to reinterpret every
field. Only the specific joins above are authenticated. The source pin identifies
the intended profile; retain source/binary hashes and fidelity receipts to prove
which compiler actually ran.

## Use privately

```sh
PYTHONPATH=src python3 -m decomp_workbench.instrument_ugen_owners \
  "$IDO_RECOMP/build/5.3/ugen.pristine.c" --output build/ugen-owners.c
cc -O2 -w -fno-strict-aliasing -I "$IDO_RECOMP" \
  -o build/ugen-owners build/ugen-owners.c \
  "$IDO_RECOMP/build/5.3/libc_impl.o" \
  "$IDO_RECOMP/build/5.3/version_info.o" -lm
```

Put that binary in an isolated compiler-driver directory, replacing only UGEN.
Keep other stages and flags identical. Capture the actual input Ucode, output
binASM and post-UGEN `-t` symbol table. A wrapper can copy those paths before and
after executing UGEN; do not reconstruct them from a listing. Set
`DKWB_UGEN_OWNERS=1` and capture stderr separately from stdout.

```sh
DKWB_UGEN_OWNERS=1 private-ido/cc [normal flags and inputs] \
  > build/compiler.stdout 2> build/owners.log
PYTHONPATH=src python3 -m decomp_workbench.ugen_owners build/owners.log \
  --ucode build/input.U --binasm build/output.B --symbols build/symbols.T \
  > build/owners.json
```

Without retained artifacts, their names/offsets remain absent. Equal draw counts,
matching words elsewhere, and equal raw pointers across runs cannot fill those
gaps. The reader never changes an object or a matching verdict. Trace serials are
contiguous; missing, reordered, malformed or conflicting records are refused.
No trace or no owned emission is not proof of no compiler activity.

Run stock versus recompiled trace-off and then trace-on fidelity before relying
on a capture. Require text, data, rodata, relocation and symbol gates. Repeat when
producer code or the host build changes. Generated sources, compiler binaries,
objects, traces and record snapshots remain ignored/private.

## Controls and measured result

The original equal-draw C fixture is in `tests/test_ugen_owners.py`. Its two
procedures each pass two global addresses in the same two argument registers,
but reverse the owners. The real trace distinguishes both owner orders despite
equal counts. Both trace-off and trace-on objects passed stock fidelity.

The committed before/after `overlay44UpdateFrameCache` closure was also compiled
as a control. Each source independently passed stock fidelity with tracing off
and on. Both expose the same single global-address owner/register through this
reader. Its known expression-order/access-scope closure is outside these seven
address-emission sites; this negative control prevents claiming that a generic
emission count explains that closure.

For the retained Mickey o052 full TU, all 103 owned address emissions joined to
exact binASM records and external symbol names. Of those, 69 also joined to
an unchanged decoded input record; 19 had a modified/unread input and 15 had
no `f_build_u` origin. Those 34 remain explicitly unresolved upstream. The two addresses relevant to the authenticated AS1
`path-28` comparison originate in consecutive input `rlda` records. The state
address arrives assigned GPR16; the descriptor address arrives assigned GPR17.
`f_build_tree`'s `rlda` case at `L41229c` creates an `lda` child and a register
store wrapper from the input assignment; `f_get_dest` receives and preserves the
same hints. Independent dense-symbol bindings and output-batch boundaries verify
the named addresses and emitted record positions. These are candidate compiler
facts, not a match claim.

A separately supplied, fidelity-checked UOPT reservation producer exposed the
immediate upstream endpoint: `f_genrlodrstr(a0=opcode, a1=color, a2=descriptor)`.
Its `rlda` path takes symbol/block from descriptor halfword 28, address offset
from word 16, and register offset from `f_coloroffset(color)`, then writes the
record through `f_uwrite`. Existing allocator decision and interference records
connect those same descriptors to color choice. This reader does not duplicate
or silently infer that upstream join.

For the measured pair, the state web takes the first zero-cost saved color;
the descriptor overlaps it and takes the next saved color at lower cost than a
caller register. This excludes a UGEN temporary-ring cause for these two
addresses. Previously exhausted color and loop-spelling controls remain closed;
no semantically supported source lever was established and no game C was edited.
The remaining source question would require independent evidence that changes
the already-authenticated UOPT lifetime/interference, not another emission
counter or arbitrary color force.

The input binding reports `retained_operand_verification` separately from the
READ-to-INPUT snapshot comparison: `full` for authenticated serialized `rlda`
records, `prefix-only` for other retained records, `not-supplied` without a
retained stream, or `unresolved` when no unchanged input can be bound. Snapshot
union padding is not treated as serialized Ucode. A destination or emission
using a pending input before its tree-copy event is rejected.
