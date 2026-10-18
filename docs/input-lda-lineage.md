# Front-end occurrences and input LDA identity

This opt-in observation connects a front-end invocation to the actual input
expression constructed by UOPT. It does not establish PRE decisions,
rematerialization, optimized output ownership, source-expression semantics or
final register/stack homes.

The producer uses `ido-static-recomp` commit
`9c242adc890beef098020149d9554f48208f699d`, generated IDO 5.3 sources:

- CFE: `06f1d133e72f667ceed7de3d07511154467e32d71ee9aa9aaa773328a1b730f5`.
- Pristine UOPT:
  `b0058f1559441c1a194d649271eb43b8637ec255682cfdd629031340b915b13f`.

Unknown sources, duplicate/missing anchors and instrumented input are refused.
Apply patches to private copies; preserve installed compilers and user-modified
support. No original compiler sources, binaries, Ucode or traces belong in a
public contribution.

```sh
python -m decomp_workbench.cfe_source instrument cfe.c cfe-observed.c --occurrences
python -m decomp_workbench.lda_lineage instrument uopt.pristine.c uopt-observed.c
```

Enable `DKWB_CFE_SOURCE_TRACE=1` and `DKWB_LDA_INPUT_TRACE=1` only for observation.
The ordinary CFE source producer remains available without `--occurrences`.

## What is observed

CFE `f_make` records the returned node after the compiler stores its own node
ID and make tag. `f_expr_cg` records actual invocation intervals using the
existing output cursor. Nodes may be recycled; creation generations and
compiler IDs must agree at use. A null expression argument is permitted by
the original function and receives an explicitly unidentified occurrence.
Raw make tags are not decoded as complete C expression semantics. Names come
from the existing named declaration operation observer, and equal spellings
never merge declaration tokens or occurrences. Lexical scope ownership is
not inferred.

The actual successful `UWRITE` buffer is observed after `fwrite`, using the
saved buffer pointer and returned byte count. The occurrence reader requires
complete, contiguous byte receipts equal to the supplied captured Ucode.
This provides payload pairing, rather than pairing traces by equal lengths.

UOPT can consume its input more than once. `ugetinit` records each input pass;
`ugetint` records returned consumed words. `ugeteof` reads a lookahead and
restores the input buffer index when input remains. Calls inside that actual
invocation are excluded from consumption, and the actual return records the
lookahead/EOF result. Every pass must reproduce the complete supplied stream.
`readuinstr` records its actual consumed word interval and current record;
`getop` records its selected input generation. String records replace raw
payload with compiler pointers, so they are paired through consumed words,
without guessing pointer identities.

Fresh expression generations are recorded after `appendchain` initializes a
successful allocation. Invalidation is observed only after the guarded
`delentry` mutation; entering a deletion helper alone does not prove death.
The reviewed LDA path records its result after the actual stack push, with
its saved entry read generation and recursion depth. Only a nonrecursive,
unchanged LDA with a live observed generation is admitted. Repeated admitted
inputs can then report reuse of that generation. Procedure ordinals come
from the same retained input stream boundaries.

```sh
python -m decomp_workbench.lda_lineage join uopt.trace captured-input.ucode cfe.trace
```

## Refusals and limits

The reader refuses missing producer capability, stale/forged generations or
ordinals, incomplete passes, changed consumed words, wrong record boundaries,
malformed or duplicate events, unsupported LDA normalization and missing
live generations. Pointer recycling starts a new generation. Missing
construction receipts and recursive/unsupported opcode paths are explicitly
unresolved. ILDA, folding, deferred addends, optimizer replacement and
re-emission have no admitted lineage in this profile. A source operation
without an identified occurrence is not source ownership evidence.

`optimized_ownership_proof`, `pre_proof`, `final_home_proof` and
`fidelity_proof` remain false. Fidelity requires a separate control receipt;
an input expression identity alone cannot reopen a matching source packet.

## Required fidelity controls

For a synthetic two-address fixture first, and then an unchanged configured
translation unit, compare stock, pristine rebuilt, patched OFF and patched ON
compilers. Require identical captured CFE Ucode, optimized Ucode, binASM and
full object bytes. OFF stderr must be empty. Verify whole-TU procedure
mapping and hash source/support before and after. Never execute generated game
binaries. Keep all native streams and receipts private.

Synthetic tests cover missing/duplicate anchors, malformed events, stream
mismatch, node and expression pointer recycling, same-spelling declarations,
null occurrences, invalidation, missing construction and unsupported recursive
origins. More optimizer coverage requires separately authenticated mutation
hooks; this profile must not extend ownership by address equality.

## Native validation receipt (2026-10-18)

The profile was freshly generated from both pinned sources using upstream
commit `9c242adc890beef098020149d9554f48208f699d`. The pristine UOPT source
was regenerated privately from that commit rather than using an unknown
modified local source. Stock, freshly rebuilt pristine, patched OFF and
patched ON compilers were compared on an original synthetic address fixture
and an unchanged configured diagnostic project translation unit. The retained
configured argument vector included `-DNON_MATCHING`; this was observer
fidelity for that context, not a canonical promotion object or ROM proof.

- Synthetic controls produced identical CFE Ucode, optimized Ucode, binASM
  and complete objects in all four variants. OFF stderr was empty. The
  reader admitted four unchanged input-LDA chains, including one observed
  generation reuse.
- The configured diagnostic translation unit produced identical allocated sections,
  symbol tables and relocation tables in all four variants. Its independently
  generated temporary input paths changed unallocated `.mdebug` and debug
  records in the intermediate streams. Those varying-path bytes were not
  normalized or used as the intermediate fidelity gate.
- The actual captured configured input and phase argument vectors were then
  replayed sequentially at identical input, output and symbol-file paths,
  with a common stage invocation name. All four variants produced identical
  complete CFE Ucode, optimized Ucode, binASM and raw objects. Source, support,
  header and compiler hashes were unchanged across the repeat control. OFF
  added no diagnostics beyond the pristine compiler's existing warnings.
- The configured input reader consumed two complete passes over 66 procedures:
  498 chains were admitted and **616 remained unresolved**. These are input
  construction observations, not complete origin coverage. The join's
  `optimized_ownership_proof`, `pre_proof`, `final_home_proof` and
  `fidelity_proof` fields intentionally remain false; the independent compiler
  control is the fidelity receipt, not a promotion of those claims.

Generated sources, compilers, project streams, objects and detailed receipts
remain private. No game binary was executed and no configured compiler was
modified. Native controls are a measurement precedent, not a fixture that
permits another compiler or source revision without repeating the gates.
See the [W47 record](history/w47-uopt-classification-handoff.md) for the distinct
failure caused by bypassing a configured assembler-processor driver.

The original [native address fixture](../examples/fixtures/input-lda-native.c)
is redistributable C; its compiled outputs are not shipped.
