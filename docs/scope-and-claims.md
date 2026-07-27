# Scope and claims

This repository packages diagnostics used during one decompilation campaign.
It aims to make the experiments reusable without turning case-specific
observations into folklore.

## What an exact result means

`exact=true` means:

- instruction counts are equal;
- all aligned instruction bits not controlled by known relocations are equal;
- relocation kinds occur at the same aligned instruction positions;
- no unknown relocation type was encountered.

It does not by itself prove:

- semantic equivalence for all inputs;
- that the C source is the historical source;
- that relocation symbols/addends are equivalent;
- that another translation unit or whole ROM is unchanged.

Use project-level verification for those broader questions.

## What a forced compiler result means

A force-choice control is an oracle. If forcing web `W` to color `C` makes an
otherwise unchanged object exact, the experiment supports a causal claim about
that allocation choice. It is not evidence that the retail toolchain used a
modified compiler.

## What the DKR examples support

The examples report observations from:

- the canonical DKR IDO 5.3 pipeline used by the project;
- specified static-recompiler builds and generated-source hashes;
- the named translation units and functions;
- whole-ROM verification recorded by the matching commits.

Broader statements such as “IDO always uses this queue” or “this source form
always creates this alias directive” would require a larger compiler corpus.
The documentation therefore uses bounded wording: “in this function,” “under
this profile,” or “the measured trace showed.”

## Historical notes can be wrong

The archived racer and menu reports contain earlier, carefully reasoned
“unreachable” conclusions that were later falsified by new source topology.
The curated case studies lead with the final result and retain only enough
historical material to explain why the tool was useful.

## Redistributable boundary

Included:

- original Python tooling;
- original documentation;
- small synthetic traces;
- reduced GNU objdump text;
- patch generators and hashes.

Excluded:

- ROMs and ROM fragments;
- extracted target objects;
- proprietary SGI/IDO binaries;
- original IRIX system images;
- copied third-party game translation units;
- compiled instrumentation binaries;
- user-specific absolute paths and session caches.

Users supply toolchains and game inputs under their applicable terms.
