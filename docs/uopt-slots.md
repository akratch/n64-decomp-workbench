# UOPT allocation and emitted local-area tracing

This narrow IDO 5.3 producer trace distinguishes **allocated temporary reserve**
from **emitted register-home demand**. They are different counters. A temporary
may receive a slot without that slot setting the emitted local-area size. A
register-home annotation can retain a source displacement and enlarge that area
without corresponding additional machine stack traffic.

Use a private copy of generated UOPT and a private compiler installation:

```sh
python -m decomp_workbench.uopt_slots instrument uopt.c private/uopt.c
# Build private/uopt.c with the matching static-recomp support files.
# Substitute only that uopt binary into a copied, otherwise stock toolchain.
DKWB_UOPT_SLOT_TRACE=1 project-build-command 2> private/slots.log
python -m decomp_workbench.uopt_slots report private/slots.log
```

The module refuses unknown source hashes, missing or duplicate anchors, repeated
instrumentation, and writing over its input. An explicitly reviewed unpinned
source can use `--allow-unverified-source`; exact anchors still must occur once.
That option is not a fidelity waiver. Never modify a shared compiler in place.
No game-derived trace, generated compiler source or binary belongs in the tree.

Prove the actual configured full translation unit against stock with tracing
disabled **and** enabled: text, data, rodata, relocations and symbols. Match each
procedure ordinal to its actual input Uent using the retained input stream.
Ordinals enumerate `oneproc` calls; they are not source names, global stable IDs,
or automatically interchangeable with another tracer's ordinals.

## Events and authenticated meanings

- `request`: the size requested by `spilltemps` or `gettemp`, the current
  allocation reserve, and the producer's owner identity. For spill requests,
  owner is the descriptor pointer and index is its table index. Descriptor
  kind/dtype/symbol fields remain explicitly raw. For `gettemp`, owner is the
  destination pointer receiving a slot pointer, not a source variable.
- `candidate`: interference-bit rejection/size check in `spilltemps`, or
  free-flag/size inspection in `gettemp`. An available flag alone does not prove
  size compatibility; compare the request and candidate sizes.
- `chosen`: slot index, signed displacement, size, reuse, and reserve before
  and after selection. The slot layout is authenticated by its construction and
  consumers. This displacement is not a final machine stack offset.
- `home`: the actual `Urlod`/`Urstr` record at the `genrlodrstr` emission point,
  and emitted-local highwater before and after that producer. Block, width and
  displacement are record fields; mtype distinguishes register, local and
  other spaces. These pseudo operations do not by themselves prove a machine
  load/store. Other highwater producers exist; coverage is not universal.
- `rlda`: the descriptor pointer and raw identity fields, requested allocation
  color, and emitted register-address record's block, address displacement and
  color offset. Its word-two field is a color offset, **not** a memory width.
  A final physical register or runtime symbol requires an independent join.
- `udef`: the actual emitted local-area definition size. It is deliberately
  reported separately from the allocation reserve.

The parser rejects malformed recognized records, duplicate fields/procedures,
missing request/choice pairs, inconsistent sizes/reserve, impossible reuse
with region growth, and incomplete procedure/local-definition traces. It can
ignore unrelated compiler diagnostics. Successful parsing is not a match proof
or a general completeness claim about every allocator path.

## Validated causal control and limits

On an authenticated configured translation unit, the allocator reserved an
additional word in both controls. Moving only one declared local earlier changed
its emitted register-home displacement and local Udef size, while that allocated
slot remained unchanged. The resulting frame changed as predicted, with no new
machine stack traffic and full stock/OFF/ON fidelity. This validates the
specific source-home mechanism; it does not establish generic cross-pass stable
IDs or a declaration-order search strategy.

For a source lever, join a named CFE operation and emitted Ucode interval to the
retained register-home operand, then use a single predicted, semantics-preserving
control. For actual spill-home attribution, retain the allocation producer,
its use during Ucode emission, and UGEN's eventual address conversion. A chosen
slot alone cannot fill in the missing stages. The trace never edits allocation
choices or output instructions, and grants no matching credit.
