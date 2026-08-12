# Provenance

The workbench was extracted from diagnostics developed while matching MIPS
objects in an N64 decompilation. The standalone Git history preserves the
original package commits; the source project is not a runtime dependency.

The pinned uopt profiles target generated IDO 5.3 source from
[`decompals/ido-static-recomp`](https://github.com/decompals/ido-static-recomp)
commit `9c242adc890beef098020149d9554f48208f699d`.

Original material authored for the workbench—its code, synthetic fixtures, and
documentation—is dedicated under CC0. That dedication does not relicense
third-party inputs merely because they are copied into an example directory.

The package does not redistribute compiler binaries, generated compiler
sources, game objects, ROM files, generated third-party contexts, or extracted
target assembly. The [CV64 notice](../examples/cv64/NOTICE.md) records why its
original scratch payloads were removed. Only aggregate measurements and a
local regeneration recipe remain.
