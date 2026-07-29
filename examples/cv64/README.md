# Castlevania 64 worked examples

This walkthrough applies the workbench to five functions from
[`k64ret/cv64`](https://github.com/k64ret/cv64) at commit
`5307217aa772019b7576cad3cb2c545e88e0394a`.

Each directory under [`scratches`](scratches/README.md) is a complete,
copy/paste-ready decomp.me handoff:

```text
README.md       manual creation order
SHA256SUMS      identities for target, context, and source
context.c       complete generated context
scratch.json    compiler, flags, diff label, and provenance
source.c        current candidate
target.s        single-function target assembly
workbench.json  local comparison result and interpretation
```

No upload is performed by the workbench. The bundles contain only the
single-function scratch materials needed for these examples, not a ROM or
extracted non-code game assets.

## Compiler setup

All five cases use IDO 7.1 with:

```text
-Wab,-r4300_mul -non_shared -G0 -Xcpluscomm -mips2 -O2
```

On decomp.me, create a new N64 scratch, select IDO 7.1, use the diff label from
`scratch.json`, and paste `target.s`, `context.c`, then `source.c` in the order
described by the bundle README.

For local campaigns, supply CV64's own IDO 7.1 compile wrapper and declare its
version in the cache identity:

```sh
decomp-workbench campaign target.o candidates/*.c \
  --symbol function_name \
  --objdump /path/to/mips-linux-gnu-objdump \
  --compile-command './compile-cv64-candidate {source} {output}' \
  --env CV64_IDO_VERSION=7.1 \
  --cache-dir .decomp-workbench/cache \
  --ledger .decomp-workbench/campaign.jsonl
```

See [IDO version support](../../docs/ido-support.md) for the distinction
between 7.1-compatible adapters and the deeper 5.3-only uopt profiles.

## Results

| Symbol | State | Candidate/target instructions | Normalized distance | Word mismatches |
|---|---:|---:|---:|---:|
| `menuButton_selectNextOption` | punch-in | 62/63 | 2 | 57 |
| `func_8013B270_BE460` | exact | 19/19 | 0 | 0 |
| `func_800012C0_1EC0` | exact | 6/6 | 0 | 0 |
| `func_800010A0_1CA0` | punch-in | 10/10 | 2 | 2 |
| `func_800010C8_1CC8` | new punch-in | 18/18 | 2 | 2 |

## Scratch model copy: exact after padding classification

`func_8013B270_BE460` copies position, size, and angle fields. Its 19 real
instructions match exactly.

The initial target appeared to contain a twentieth instruction because it was
the final unsized symbol in an extracted section. GNU objdump included one
unreachable zero alignment word after the return delay slot. This case led to
the selected-symbol padding fix in the workbench: zeroes after the final
`jr ra` delay slot are excluded, while the delay-slot instruction and any
nonzero content remain.

## Scratch menu selection: one early instruction

`menuButton_selectNextOption` is 62 candidate instructions against 63 target
instructions. Positional comparison reports 57 word mismatches because the
missing instruction occurs near the beginning; normalized edit distance is
only 2.

The target initializes `v1` to zero before the option-count sign test and later
spills `v1`. IDO removes the candidate's declaration-time `ret` write and
spills architectural zero directly. Removing the later source assignment
restores instruction count but substantially worsens allocation, so it is not
a solution.

IDO 7.1 static-recomp releases v0.6, v1.0, v1.1, and v1.2 produced the same
candidate in the original investigation. IDO 5.3 produced a structurally worse
result. This is a source/pass investigation, not a compiler-generation switch.

## List splice: exact alias expression

`func_800012C0_1EC0` began as `GLOBAL_ASM`. Directly spelling
`left->next` twice gives IDO a reason to reload it because the intervening
store may alias `left`.

Naming the original value expresses the retail behavior:

```c
ListNode* right = left->next;

inserted->next = right;
right->previous = inserted;
left->next = inserted;
inserted->previous = left;
```

The result is exact: six target instructions, six candidate instructions, and
zero mismatches.

## Pool clear loop: correct topology, late schedule

Changing `func_800010A0_1CA0` from a pre-tested `for` loop to the observed
`do/while` removes four extra instructions. The result has the target's 10
instructions, opcodes, and registers.

Only the order of the two independent `%lo` address-forming instructions
remains different. This is a retained-listing/pass-replay problem, not a reason
to keep changing loop semantics.

## New punch-in: pool entry scan

`func_800010C8_1CC8` scans eight-byte pool entries for a null value, fills the
entry, and returns it. The current `do/while` candidate matches all 18 target
instructions, every opcode, and every register.

Like the preceding pool-clear routine, its only two word mismatches are:

```text
target:    addiu v0,v0,%lo(objects_array)
           addiu v1,v1,%lo(D_80341060)

candidate: addiu v1,v1,%lo(D_80341060)
           addiu v0,v0,%lo(objects_array)
```

That makes it a compact unsolved function for manual decomp.me work. Useful
next experiments are source-line grouping and a calibrated IDO 7.1 retained
listing replay. The current bundle intentionally does not claim an exact
match.

## Regenerating a bundle

Given local files, the public command is:

```sh
decomp-workbench bundle-scratch output/function \
  --target-assembly target.s \
  --context ctx.c \
  --source candidate.c \
  --platform n64 \
  --compiler 'IDO 7.1' \
  --compiler-flags='-Wab,-r4300_mul -non_shared -G0 -Xcpluscomm -mips2 -O2' \
  --diff-label function_name \
  --project 'k64ret/cv64@5307217aa772019b7576cad3cb2c545e88e0394a'
```

The output directory must be new or empty. This prevents an update from
silently mixing stale context or target assembly with a new candidate.
