# W47: configured-driver fidelity and the missing UOPT join

Status: completed bounded evidence report, not a completed UOPT decision-to-emission proof.

Retained from the 2026-09-28 investigation (original commit
`ae5bf192be49cf79bcf3ce8a65e74a089acba399`). The input-LDA observer added later
does not close this missing decision-to-emission join.

## Fidelity control

The earlier self-context stock comparison bypassed the configured assembler
processor and compiled retained preprocessed input directly. It omitted the
absolute `_ASM_PROCESSOR_PRELUDE_GUARD` symbol. A reproduction through the
configured assembler-processor driver, using the canonical translation unit,
passed section, relocation and symbol fidelity against `stock.o`:

- `.text`: 8,688 bytes, SHA-256 `24a9622c859f6f590c92e035877aeb9a368eeebef4822c6444840569a5ee1601`
- `.rodata`: 48 bytes, SHA-256 `2080a82135fbd959bec78a3eb5f750e8b9a8c0e12aa9145ba2d35fa160e9564a`
- `.data`: absent
- relocations: SHA-256 `cb2337022f0afa2b28ccc2c4607ed07ad60d75a2d140907a4c0147a97f33e6d6`
- symbols: SHA-256 `a8ff38ea02913dc231bbd76b80d0986235383155ad4639c2ba8c8e5234b66dbc`

The retained direct self-context object and the driver run over retained `.i`
both lack `_ASM_PROCESSOR_PRELUDE_GUARD`; their symbol hash is
`0eab8e77dd97c1e9e30bc744fe36da931596a728cc7b07720557563a6fd5bb72`. The
driver run over `.i` therefore still fails the symbol gate. Use the source
translation unit through the configured driver for this control. The existing
OFF and ON full-TU fidelity receipts pass all gates.

## Occurrence evidence

The ON diagnostic used the configured driver and the pinned `final-ugen`
profile. In the retained trace, `DKWB-OWNER-INPUT` and `DKWB-OWNER-BUILD`
identify node `269842176`, ID 32. The conversion scope identifies ID 33 with
that node as its child. Its `eval` event reports ID 32, `mtype=2`; its same-run
`ureg` event reports `(mtype=2, offset=0, result=72)`. The enclosing conversion
then records the ordinary GPR-to-FPR move. This authenticates the exact
parameter-memory input occurrence and UGEN's sentinel result.

The trace has no UOPT descriptor/web identity, eligibility or split decision,
or emitted-memory/register record joined to ID 32 or ID 33. `OWNER-DEST` for
ID 32 is UGEN's evaluation destination (GPR 14), not an authenticated UOPT
storage decision. No `OWNER-EMIT` record names either ID. Therefore the
input-to-UOPT-decision-to-emission chain remains unproved; do not infer it from
record adjacency, colors or pointer values.

## Reproduction pins and limits

- Base: workbench commit `d097d4fc5b0322c402b6991b215eeca40004e7fd`.
- Pinned producer executable: `final-ugen`, SHA-256
  `c42b4795f3256360354b529f03477b968683508704f0bb992efbb36c4acadf02`.
- Pinned conversion source: `final.c`, SHA-256
  `9d3a5e3411f388c71d644673d250f1a06503ac1a8ea55386b8450e92c6b5e31b`.
- Configured diagnostic compiler: SHA-256
  `1f35d3e39e1258476d4beb369a4bf5c9419365c9116c4c5b151fd585e4152443`.
- ON reproduction object: SHA-256
  `e6fabb941577c661315e1eb84c00b73ba2c8d46b6a3c3f67c49f3559152cc6fc`.
- ON reproduction log: SHA-256
  `73f7a282353c305a2b1248793cfb964e6af7f0b30be7cb0abd048f405def311e`.
- Adapter sources inspected: `prototype.py` (`2ce8041585bde62c9cc920227deaceb34d6d14858c692bdc0c73b5270cfad6a8`),
  the private draft `ugen_conversion.py` (`10412a0f438cbb97b7eeebf2c317019254b2a0545e4779f6dc1bec963ca2993c`),
  and `final.c`; their hashes matched the handoff pins where provided.

The reproduction ran with owner and conversion tracing enabled. It changed no
compiler or Mickey source. Generated objects, logs and fidelity JSON remain in
the lane's ignored `build/w47/` directory and are not part of this document.
No C-source experiment was attempted; the missing UOPT join is the stop point.
