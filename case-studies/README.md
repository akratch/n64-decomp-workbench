# Worked examples

These examples explain how a diagnostic changed the next experiment. They are
not a catalog of universal source-matching tricks.

| Function | Plateau | Tool that changed the investigation | Final source lever |
|---|---|---|---|
| [`trackbg_render_flashy`](trackbg-globalcolor.md) | FP register tie | uopt globalcolor trace | Expression-table order and a few explicit expression forms |
| [`func_80017A18`](objects-structural-score.md) | Misleading scalar score | Exact asm-differ penalty buckets | Treat stores as compiler spills; reorder interpolation deltas |
| [`func_80049794`](racer-fifo.md) | 19 register-only words in 2,625 instructions | ugen event trace, force oracle, FIFO schedule model | Split a shift into its own statement |
| [`func_8008FF1C`](menu-pass-replay.md) | One store scheduled in the wrong slot | Retained listing and as1 replay | Preserve alias provenance with direct indexing |

Read each example in this order:

1. What was already known from the object.
2. Why another source sweep was unlikely to answer the question.
3. What the instrument or replay experiment observed.
4. How that observation constrained the next source change.
5. Which claims the evidence does and does not support.
