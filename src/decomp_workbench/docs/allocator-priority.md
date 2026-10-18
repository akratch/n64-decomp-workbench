# Allocator saving sensitivity (IDO 5.3)

`python -m decomp_workbench.allocator_priority observations.json` reports
arithmetic over explicit observations. It does not run a compiler, infer an
interference graph, predict colors, or prove an allocation.

The native `compute_save` path (`L46f190` through `L46f1ec` in the pinned
IDO 5.3 static-recompiler profile) first adds the number of occurrence-list
entries and the cardinality of the auxiliary block set. It then compresses
that raw count:

```text
units = raw                         if raw < 3
units = 2 + floor((raw - 2) / 4)     otherwise
priority = (gross - charge_a - charge_b) / units
```

Thus raw counts 21 and 22 give divisors 6 and 7; 25 and 26 give 7 and 8.
An empty block can cross a boundary, or change nothing. Counting references,
or counting only blocks with real references, misses auxiliary liveness.
Overlapping occurrence and auxiliary blocks are still counted according to
these two separate native containers; do not union them.

Supply the complete affected set of decisions, with run-local labels of your
choice. Obtain occurrence and auxiliary membership from authenticated native
records; source lines and block intersection alone are insufficient.
This synthetic input changes two numerators together:

```json
{
  "decisions": [
    {"id": "left", "phase": "p1", "order": 1, "gross": 8,
     "charge_a": 0, "charge_b": 0, "occurrences": 1,
     "auxiliary_blocks": [4]},
    {"id": "right", "phase": "p1", "order": 2, "gross": 10,
     "charge_a": 0, "charge_b": 0, "occurrences": 1,
     "auxiliary_blocks": [4]}
  ],
  "changes": {"left": {"net_delta": 6}, "right": {"net_delta": 2}}
}
```

`raw_delta` is also accepted. It describes a hypothetical change to native
units, not a claim that a particular C edit produces that change. Each output
row keeps gross, both penalties, net and divisor separate, and reports the
raw interval that retains the divisor and the distance to each boundary.
An optional `bestcost` reports only whether **total net** is greater, equal or
less. Equal normalized priorities do not imply equal split acceptance.

Phase-one groups are ranked by mathematical priority. Equal values remain a
group: their displayed order retains observation order and does not claim a
native tie rule. Phase two retains observed order even when its saving changes.
The library's `strict_net_window(lower, upper, units)` returns the open interval
that places a numerator strictly between two priorities, excluding both ties.

Every counterfactual holds phase membership, graph, eligibility, split pieces
and register costs fixed. If a source edit changes one of them, these results
cannot be transferred without a new baseline. A complete native replay must
reproduce every observed degree, phase and color before predicting allocation;
a block-set model that works for one register class may fail for another.
Trace decimal values may already be rounded. Exact rational arithmetic here
explains the supplied numbers, not the compiler's floating-point evaluation.

**Evidence and limits.** The formula and phase distinction were checked against
native IDO 5.3 predicates and retained decision records during the Mickey's
Speedway USA campaign (2026-10-18). The final matching ray function supplied a
positive coupled-priority control; target-specific replay and game data are
not shipped. Tests here use synthetic arithmetic, including compression
boundaries, unordered ties, phase-two invariance, total-cost equality and
coupled changes. See also [per-web reports](compiler-instrumentation.md) and
[allocator laws](compiler-laws/ido-5.3.md).
