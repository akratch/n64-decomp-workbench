# Scratch bundles

`bundle-scratch` creates a deterministic local handoff for one decomp.me
scratch. It does not contact decomp.me or any other service.

## Create a bundle

Provide a single-function GAS target, the complete generated context, and the
current candidate source:

```sh
decomp-workbench bundle-scratch scratch/demo \
  --target-assembly target.s \
  --context ctx.c \
  --source candidate.c \
  --platform n64 \
  --compiler 'IDO 7.1' \
  --compiler-flags='-O2 -mips2' \
  --diff-label demo \
  --project example
```

The output directory must be new or empty. The command refuses to merge with
or overwrite an existing bundle.

## Output

```text
scratch/demo/
├── README.md
├── SHA256SUMS
├── context.c
├── scratch.json
├── source.c
└── target.s
```

- `target.s`, `context.c`, and `source.c` are byte-for-byte copies.
- `scratch.json` records the decomp.me selections and SHA-256 identities.
- `SHA256SUMS` lets a recipient verify the copied inputs.
- `README.md` gives the manual paste order.

Use `--json` to print the manifest after a successful bundle operation.

## Presets

When a known decomp.me preset should be selected, record it with `--preset`.
The compiler and flags remain in the manifest as explicit provenance:

```sh
decomp-workbench bundle-scratch scratch/demo \
  --target-assembly target.s \
  --context ctx.c \
  --source candidate.c \
  --platform n64 \
  --compiler 'IDO 7.1' \
  --compiler-flags='-O2 -mips2' \
  --preset 'Project preset name' \
  --diff-label demo
```

## Redistribution boundary

The command packages user-supplied local files; it does not make them
redistributable. A generated context can contain substantial third-party
project source, and target assembly can be derived from a copyrighted binary.

Keep such bundles out of this repository unless every input's terms permit
redistribution under the repository license. Project integrations should
normally commit a generation recipe and ignore the generated payload.

The command deliberately performs no upload. Review the bundle, verify its
checksums, and create the scratch manually at <https://www.decomp.me/new>.
