# Research archive index

This directory is an index, not a dump of every candidate and compiler output.
The raw DKR research remains in Git where its chronology and original context
are preserved.

## Primary archive

Checkout or inspect:

```sh
git show archive/decomp-research-2026-07-26:MENU_FINDINGS.md
git show archive/decomp-research-2026-07-26:racer_research/RACER_FINDINGS_DRAFT.md
git show archive/decomp-research-2026-07-26:menu_research/report_as1_directive.md
```

The branch contains:

- function-specific sweep scripts;
- source variants and checkpoints;
- trace logs and ledgers;
- menu pass-replay tools;
- racer allocator mapping;
- generated-source instrumentation patches;
- historical handoffs and reports.

Object collision reports and tools are on `match-trackbg-render-flashy` under
`objects_research/`.

## Why the raw corpus is separate

Much of the archive contains hardcoded local paths, complete generated
translation units, repeated variants, or scripts designed around one function.
Publishing it as the supported API would make the reusable tools harder to
find and imply portability that has not been demonstrated.

The curated package links each mechanism to a worked example. Researchers who
need the full evidentiary trail can inspect the archival refs.

For a mechanism-by-mechanism disposition, including volatile-session tooling
that was generalized into the package, see the
[historical tooling inventory](../docs/historical-tooling-inventory.md).

## Do not add

Do not add ROMs, target objects, IDO binaries, original IRIX binaries, compiled
instrumented passes, or user-supplied game archives here.
