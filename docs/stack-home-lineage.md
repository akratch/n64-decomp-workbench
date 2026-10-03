# Observed pseudo-memory home lineage

`instrument_stack_homes` adds read-only UOPT writer/slot observations and
UGEN tree/frame/memory observations. Its UGEN profile accepts only the
pristine generated source with SHA-256
`4079660f9ebb068a791c6f54abb67cf7c3bb792207c89a6eb9ac2d9e146341ec`
from `decompals/ido-static-recomp` commit
`9c242adc890beef098020149d9554f48208f699d` (IDO 5.3). Existing source-hash
and unique-anchor checks run before instrumentation. Generated sources,
compiler binaries, retained streams and native traces stay private.

The two admitted conversions are the actual `Urstr` to `Ustr` and `Urlod` to
`Ulod` mutations in `f_build_tree`. A `DKWB-HOME-CONVERT` receipt follows the
opcode change, register-halfword clear and union-word clear. It contains
`owner_serial`, `node`, `generation`, `read_index` and the eight resulting
`w0` through `w7` words. Enable both `DKWB_STACK_HOMES=1` and
`DKWB_UGEN_OWNERS=1`; conversion events require the owner lifetime producer.
A version-2 `DKWB-HOME-CAPABILITY` marker declares conversion and rollback
observation. Every home report requires this marker; missing or duplicate
capabilities are refused. Legacy direct-only traces must be regenerated with
the reviewed producer because they cannot establish rollback observation.
The hook reads simulated compiler memory and writes stderr. It does not
change IR, instruction output, allocation or compiler flags.

The reader requires an exact retained READ ordinal, completed INPUT/BUILD
copy and latest fresh NEW generation. Only local/parameter memory classes
1 and 2 are admitted. The post-conversion snapshot must preserve type,
memory class, block, width, offset and all other payload except the three
observed changes. Pointer recycling cannot inherit a prior receipt. Missing
receipts leave pseudo origins unresolved; duplicates, forged generations or
ordinals, changed payloads, unsupported origins and events after frame use
are refused. A concrete home also requires the observed frame input/result
and memory emission to agree with retained binASM at its observed batch/index.
Later compiler changes to that emission remain a refusal, without inferred
normalization. The compiler can also discard trial emissions by restoring its
output-buffer counters before increasing its temporary area. A read-only
`DKWB-HOME-ROLLBACK` receipt follows the actual restores in `f_restore_i_ptrs`
and reports the current owner serial, epoch and restored forward/backward
counters. Any observed rollback refuses the entire home report, even when trial
and final bytes happen to agree. Modeling surviving emission generations remains
out of scope. UOPT allocated-slot joins remain restricted to observed direct
`Ulod`/`Ustr` spill emissions; a conversion receipt alone creates no slot claim.

For fidelity validation, privately copy the pinned generated source and its
support headers/source, record every input hash and compiler recipe, and build
both pristine and instrumented executables. Keep installed compilers unchanged.
Run the same retained input and symbol table through stock, rebuilt pristine,
instrumented OFF and instrumented ON controls. Require identical retained
Ucode, binASM and final configured objects; OFF must emit no trace stderr.
Include direct and pseudo memory cases, parameter/local homes, multiple widths,
recycled nodes and collateral procedures. Keep malformed trace tests synthetic.
The focused tests exercise missing/duplicate anchors, absent/forged receipts,
changed widths/offsets, generation reuse and final-memory disagreement.

This reports retained Ucode to observed UGEN virtual/frame operands and binASM
ownership. It does not establish C variable or source-expression identity, PRE
decisions, rematerialization ownership or AS1 instruction offsets. More coverage
alone does not authorize another matching source experiment.
