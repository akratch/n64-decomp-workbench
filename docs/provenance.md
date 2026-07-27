# Provenance

The workbench is a curated extraction of diagnostic tooling built while the
DKR decompilation approached its final matching functions in July 2026.

## Repository sources

| Git reference | Material |
|---|---|
| [`tooling/decomp-workbench`](https://github.com/akratch/Diddy-Kong-Racing/tree/tooling/decomp-workbench) / `decomp-workbench-v0.1.0` | First reusable package |
| [`archive/decomp-research-2026-07-26`](https://github.com/akratch/Diddy-Kong-Racing/tree/archive/decomp-research-2026-07-26) | Menu and racer reports, variants, traces, scripts, and preserved instrumentation patches |
| [`match-trackbg-render-flashy`](https://github.com/akratch/Diddy-Kong-Racing/tree/match-trackbg-render-flashy) | Track renderer and object collision research |
| [`faebc894`](https://github.com/akratch/Diddy-Kong-Racing/commit/faebc894b48cddc60fd2ae32acf7fdf3260cad79) | `trackbg_render_flashy` match |
| [`17f4bddd`](https://github.com/akratch/Diddy-Kong-Racing/commit/17f4bddd9f7f94ba12d1501bf8f85fe8e7e05020) | `func_80017A18` match |
| [`6c626c9b`](https://github.com/akratch/Diddy-Kong-Racing/commit/6c626c9b797c1241b39b1164c3e1955459778330) | `func_80049794` match |
| [`8131d0da`](https://github.com/akratch/Diddy-Kong-Racing/commit/8131d0da107d741084107545554570f9c0392c96) | `func_8008FF1C` match |

The raw archive contains hundreds of function-specific experiments. The public
package extracts recurring mechanisms and leaves the original scripts
available for audit rather than presenting each as a supported command.

## Tool lineage

- Relocation masking came from the strict menu full-word verifiers and was
  expanded into a typed relocation parser that refuses unknown kinds.
- Structural reporting came from the racer oracle, object scorer, and
  within-basin dashboards.
- Campaign caching/ledger design replaces target-specific parallel sweep
  scripts.
- FIFO reconstruction is a cleaned implementation of the racer event
  extraction, logical scheduling, replay, and constraint-solving workflow.
- Globalcolor parsing covers the structured `CSAVE`, `CUP`, and later `[CDX]`
  generations. Earlier `RACER-COLOR` logs remain in the raw archive but were
  not promoted because their schema changed across experiments.
- Retained-pass replay generalizes the menu `as1_probe.py` workflow.
- The uopt patchers are derived from the globalcolor and alias-state diagnostic
  generators and are now hash-pinned, anchor-validated, and composable.

## Collaboration

The research was produced collaboratively by DKR contributors, Adam Kratch,
Claude-assisted coding sessions, and Codex-assisted coding sessions. Individual
matching commits retain their recorded authors and co-authors. This document
describes provenance for reproducibility; it does not replace Git history or
third-party license notices.

## Upstream projects

The workbench interoperates with, but does not redistribute:

- `decompals/ido-static-recomp`;
- GNU binutils;
- asm-differ;
- project-specific IDO toolchains and ROM extraction systems.

Those projects retain their own licenses. Generated compiler profiles must
record the upstream commit and input hash as described in
[compiler instrumentation](compiler-instrumentation.md).

## License boundary

Original workbench code, reduced fixtures, and documentation are dedicated
under CC0. A user applying the tools to third-party code or binaries is
responsible for the terms governing those inputs and outputs.
