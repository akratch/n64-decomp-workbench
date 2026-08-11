# Trustworthy endgame live acceptance — 2026-08-11

This receipt records hashes and comparison facts only. It contains no ROM
bytes, target disassembly, proprietary compiler binary, or target object.

Tooling baseline: workbench parent `90f67cae247268b9fd2ce777d11a96ebd7b50c46`
plus the trustworthy-endgame implementation under review; GNU MIPS objdump
2.46.1, SHA-256
`639607836871b1218379e01f5a169c7625779845ca78b036a283843e9714d7b7`.

## Downloaded decomp.me export and project truth

- export SHA-256:
  `e7026beb83f520b25fa5a8e8ed4a2d7f0548d3e85e4a409be490f6692d0316de`;
- target-object SHA-256:
  `6e971d33afb86108a5e31cad355dc40fd2ee58a11520219a5b5c499725cd1a58`;
- project winner object SHA-256:
  `834350d407593395c1466172219456d98c600446243db7c26edfbba9f5b1db1f`;
- project winner source SHA-256:
  `f0a7144ee154082281983cf22d8aa5cac116cb561e20a1fa4f504a04ec7892dd`.

`check-scratch --view --project-object --project-source` classified the result
`context-only`. The downloaded scratch measured 133 instructions, frame −56,
three raw/aligned register differences, zero structural differences, and
`allocation-mismatch`. The independently archived full-translation-unit
winner measured 133 instructions, frame −56, zero raw words, zero aligned
differences, and `instruction-words-identical`. The export's saved site
metadata was 15/13300; it remained context and did not override either object
measurement. The aligned view did find one late `$v1`→`$v0` web, but no
qualifying direct call precedes it within 24 aligned rows, so the call-contract
hint correctly stayed silent.

## Authentic alternate frontend cell

An existing authentic IRIX 4.1 `accom` standalone object, SHA-256
`14494cb09bd70502f5761d6463a281bb4ec61854d008a181d7ebed6b2ed3f7d6`,
was compared against the same selected 133-instruction function. Count and
frame were exact; the measured result was 16 words/aligned rows,
`allocation-mismatch`. The stock 7.1 full-TU winner above was exact. This is a
measured frontend distinction, not an assumption from a shared backend.

Synthetic integration additionally proved that otherwise identical wrapper
commands with IRIX 4 `accom` and later `cfe` compiler envelopes receive
different cache/campaign identities, while an omitted/empty envelope preserves
the legacy cache key.

## Acceptance summary

- downloaded export: truth layers and context-only differential PASS;
- project full-TU/non-scratch object: selected function exact PASS;
- authentic alternate frontend: measured and kept distinct PASS;
- asset-free v2 control/coverage/fresh-finish/package walkthrough: PASS.

The project function is exact. The downloaded scratch remains a three-word
context mismatch, so decomp.me's override can accurately acknowledge a
project-verified match without pretending the exported scratch object is byte
exact.
