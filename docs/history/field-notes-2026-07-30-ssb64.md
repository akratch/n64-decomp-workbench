# Field notes — SSB64 ovl8 frontend-lineage campaign (2026-07-29/30)

> **Historical field record.** Measurements and failures are preserved as
> observed on the dates above. Use [Product status](../product-status.md) and the
> current command guides for supported syntax and capabilities.

Live-fire observations from the SSB64 debug-overlay campaign
(`func_ovl8_803781A4` and three siblings; IDO 7.1 backend, -O2 -mips2).
Project-neutral; no ROMs, objects, or proprietary artifacts. The full
public narrative lives outside the workbench (ssb64 STORY.md); this page
records only what changes workbench practice.

## Headline

A dispatch proven impossible for the project frontend (algorithm-level
analysis of cfe's switch grouping, sealed with duplicate-case probes) was
resolved by swapping the **frontend generation, not the source**: IDO
4.1 `accom` ucode into the stock 7.1 backend reproduced the function
word-for-word. New docs: [alternate-frontends](../alternate-frontends.md);
new levers: field-guide 20–22 plus two dead families.

## Gaps / friction

- **Comparator: vestigial aligned residual on exact matches.** A
  `verdict=instruction-words-identical words=0 raw=0` comparison still
  rendered `aligned residual classes: aligned_schedule=2` (and
  `aligned_total=2`) — observed repeatedly on 391-instruction exact
  matches during this campaign. On an exact verdict the aligned-residual
  line reads as contradiction; suppress it (or label it) when
  `words==0 && raw==0`. Not yet reduced to a redistributable repro; the
  trailing-nop / function-padding trim is the suspected source.
- **Case-insensitive symbol fallback** (`compare --function`): `upas`
  folds identifiers to lower case, so Pascal-built objects need an
  `objcopy --redefine-sym` round-trip before comparison. Patched in this
  branch: exact match first, unique casefold match as fallback
  (`objdump.parse_disassembly`).
- **Foreign-frontend objects and the harness.** The 4.1 pipeline's
  ECOFF-era quirks (glibc ≥2.38 emulator, `/usr/tmp` requirement,
  little-endian-only `ecoff_tool`) cost a night of debugging; recorded in
  the alternate-frontends doc so they are paid once.

## Validated (keep doing this)

- The lever discipline held: every terminal residue was classified
  (allocator tie-break vs frontend convention vs construct
  misidentification) before spending variants.
- The instrumented-frontend trace loop (compiler-instrumentation.md's
  approach applied to cfe's switch grouping) turned "we tried everything"
  into a finite reachability proof — the strongest possible justification
  for then changing the compiler variable.
- Probe matrices through an identical backend (the "fingerprint atlas")
  discriminate frontends in minutes and correctly predicted per-function
  attribution before any full-function port.

## Numbers

| function | patched-cfe best | accom-hybrid best | note |
|---|---|---|---|
| A (391 insns) | words=0 (patched) | **words=0 (authentic)** | also words=0 via Pascal `upas` — excluded by sibling forensics |
| B (226) | 29 words, heavy artifice | 33 → 225/226 natural | remaining: one allocator tie-break |
| C (456) | 148 words | 52 words natural | reassociation casts unnecessary under accom |
| D (524) | 122 words | 70 words natural, count exact | line-placement lever (21) closed the scheduling residue |
