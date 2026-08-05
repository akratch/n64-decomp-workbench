# SSSV `func_802963D0_6A7A80`: one visible swap, several hidden causes

This case study records the product lessons from the August 2026 investigation
of decomp.me scratch `CEBtO`. It intentionally excludes ROM bytes, compiler
binaries, target objects, and full proprietary context. Hashes identify the
private evidence without making it redistributable.

## Result and proof boundary

The final candidate compiled with the supplied decomp.me context and untouched
IRIX IDO 5.3 to 93 raw instruction words identical to the retained target,
with the same `-40` frame and relocation targets. No allocator force or match
override was active.

| Evidence | Recorded value |
|---|---:|
| Candidate source SHA-256 | `abeab71a8d1ba2878477bf179fbcf49228e7b6bec0a7762ed4d3575de329e078` |
| Supplied context SHA-256 | `143fc37e33d0d832579a4be5c3a1e6f00f493191df4f4ed28c6866e1bc13fc17` |
| Stock candidate object SHA-256 | `68db181031f7886fef42cad35f36027e9cfd2bfbe4cfb94d9e5d20280ba48017` |
| Corrected six-file archive SHA-256 | `a17b2c43752673abae4c0857f04003ae22d5c727f92ff2111f0d61af61919b4e` |

These values support a local retained-object result. They do not claim
whole-ROM identity, provenance of the original source, or independent public
reproducibility without the rights-holder-controlled inputs.

## Why the visible residue was misleading

The starting 99.19% scratch used deliberate source tricks and ended in what
looked like one register bijection. Treating that as one source web led to
signature, declaration, CSE, alias, and single-force searches that repeatedly
collapsed to the same object basins.

Allocator traces and controlled deletions eventually showed that the visible
pointer was downstream of three optimizer-erased carrier webs placed at two
nested-loop lifetime boundaries. The first successful source shape recreated
their composition. One visible register mapping was therefore one downstream
outcome, not evidence for one causal web or one edit.

The decisive paired trace also separated three notions the initial guidance
had blurred:

- formation rank: when a live range was constructed;
- `save`/`nocs`/`totalsave`: measured allocation economics;
- decision-trace ordinal: when the allocator decision was observed.

The stock-exact cancelled use formed a hidden web at rank 16, before the visible
pointer at rank 17, and gave it `totalsave=101`. A side-effecting bridge formed
the hidden web later and raised it to `2990`, yet reached the same downstream
allocation while emitting unwanted instructions. A separate late
instrumentation-only cost overwrite did not reorder anything because the
relevant list already existed. A priority probe must therefore act before list
construction or compare natural paired builds; rewriting a displayed scalar at
the decision site does not prove causality.

## Why “function exact” still scored 99.89%

The first accepted-looking archive used a struct-member relocation for an
address that the target named through a direct symbol. Relocation masking made
the linked function instructions compare exact, but the unlinked instruction
word and relocation target differed. The retained decomp.me score was
`10/9300`, or 99.89247%.

Changing only the symbol spelling reproduced the target's raw word and
relocation target. This is why `check-scratch` now reports four separate facts:

- `linked_function_exact`;
- `raw_instruction_words_exact`;
- `relocation_targets_exact`;
- `decomp_me_score_proxy_exact`, which requires all applicable local gates and
  remains explicitly a proxy for the site's result.

## Post-match minimization changed the explanation

The first exact source was not the cleanest exact source. It declared three
function-scope statics, used two as empty-control carriers after the inner loop,
and retained a third empty control after both loops. A later candidate retained
only the static whose cancelled `* 0` use shapes texture-coordinate code and
replaced the other two carriers with two adjacent
`if (width == height) {}` controls at the same lifetime boundary. It also
removed the late static control. Untouched IDO 5.3 still emitted all 93 target
words, the `-40` frame, and the target relocation.

This is carrier substitution, not proof that either source is historical. The
two source shapes align only 19 of 29 semantic allocator fingerprints because
the controls create different webs. Their 20 observed phase-2 decisions still
have the same ordered decision kind, natural color, and assigned color. The
allocation outcome is identical even though the semantic carriers are not.

Controlled ablations make the boundary concrete:

| Candidate | Instructions | Frame | Result |
|---|---:|---:|---|
| one static plus two adjacent relational controls | 93 | `-40` | exact |
| remove both relational controls | 90 | `-32` | structural change |
| keep only one relational control | 91 | `-32` | structural change |
| move the controls before the inner-loop boundary | 93 | `-40` | allocation residue |
| make the remaining static automatic | 93 | `-48` | two raw-word mismatches |

Full-object inspection also improved the candidate without declaring victory:
the old three-static translation unit had `.bss` size `0x30`; the one-static
candidate returned it to the baseline `0x20`. Both exact candidates still
changed GP-related linker metadata from the no-static baseline. Function
exactness, cleaner C, translation-unit equivalence, and ROM verification are
therefore four distinct gates.

We missed this candidate because the relational-control family and the later
static-tail deletion were searched on different parent sources. Once the first
exact candidate appeared, the campaign stopped and no bounded cross-family
composition or post-match minimization pass joined the useful mechanisms that
were already on disk. More source variants within either family would not have
fixed that search topology.

## What the workbench should make cheap

The durable workflow is:

1. Group a visible register bijection as one outcome, then inspect the desired
   color's interference producers before assuming one cause.
2. Use one controlled source edit and `trace origin-probe` to correlate source
   roles without pairing run-local web IDs by position.
3. Compare formation chronology, economics, and decision order independently.
4. Test a measured multi-web interaction only after single-force deltas justify
   it; inspect every collateral recolor and emitted instruction change.
5. Keep object basins and explicit stopping rules so hundreds of syntactic
   variants cannot masquerade as progress.
6. After the first exact result, run `experiment inspect-source`, encode
   measured mechanisms with `experiment compose`, and compile the bounded set
   with `--no-stop-on-exact`.
7. Compare exact candidates with `object collateral`; prefer less unexplained
   TU state without mistaking minimal fake-match scaffolding for provenance.
8. Finish with the raw-word and relocation-target scratch proxy, then run the
   project's normal link/ROM verification separately.

The broader lesson is modest: instrumentation is valuable when it narrows the
next falsifiable experiment. It is harmful when a run-local ID, hash bucket,
line marker, cost field, or forced endpoint is presented as source identity.
