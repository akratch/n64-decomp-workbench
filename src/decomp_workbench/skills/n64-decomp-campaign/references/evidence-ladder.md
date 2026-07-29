# Evidence ladder

Use the strongest available evidence and state its scope precisely.

| Evidence | Establishes | Does not establish |
|---|---|---|
| decomp.me percentage or visual diff | A direction worth investigating | Exact code, context, or ROM match |
| Normalized instruction similarity | A structural neighborhood | Literal operands, allocation, or final bytes |
| Same opcode shape | Stable control-flow and instruction schedule | Matching registers or relocation layout |
| Region collapses under `-g0` | Debug metadata constrains the `-g3` schedule; as1 can reach that order | Original or correct source topology |
| Cross-ROM structural match | Shared compiler/source lineage evidence | Exact target object or project match |
| Force-color or pass-replay experiment | A late compiler cause is plausible | A valid C source match |
| Relocation-aware instruction-exact object comparison | The selected function's instructions and known relocation layout agree | Whole-project or final-ROM identity |
| Normal project link and full-output verifier | The project's required final proof | A portable conclusion for another revision without comparison |

## Resolve contradictory-looking evidence

Do not assume a lower external score disproves exact object evidence. First
check whether the two comparisons use different:

- compiler versions or flags;
- selected function boundaries;
- translation-unit declarations and available prototypes;
- constant-pool, BSS, or rodata symbol spelling;
- object versus linked/ROM relocation context.

The Titania campaign demonstrated this boundary: an external scratch score
could retain a tiny residual when the underlying object-level instruction
evidence was already exact, because equivalent linked addresses were printed
through different compiler-generated symbols.

The `vsprintf` campaign demonstrated a second boundary: a large region
collapsing under `-g0` did not prove the C was original. A freer scheduler had
rescued a non-original padding/length topology. The eventual match required a
different source expression shape, followed by site-faithful source-line
identity for the final scheduling tie.

## Keep heuristics in their place

Use a score to rank experiments inside one controlled campaign. Do not compare
scores across changed compiler contexts, ROM revisions, or external tools
without also preserving the comparison metrics and inputs. Prefer a candidate
that removes a structural class of difference over one that merely improves a
single score.

When a score is used, use the aligned one. `aligned_total` counts differing
rows after an LCS alignment; `words` counts positions and shifts on every
inserted or deleted instruction, which misranked candidates in six recorded
campaigns. The workbench sorts on the aligned count for this reason, and the
`aligned_*` class split says which lever family the residual belongs to.
