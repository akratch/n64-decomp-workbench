# Working a backlog of near matches

**You have thirty-odd functions that are almost matched. Here is how to get
through them without picking the wrong one first.**

This is [Start here](START_HERE.md) applied at batch scale. Read that page
first — it explains `compare`, `view`, and the loop. This page is the triage
process, with the shell to run it.

The premise, from real backlogs: about half of a typical near-match pile falls
to levers that cost **one variant each**, and you cannot tell which half by
looking. So you classify everything first, cheaply, and then work the classes in
order of cost. Working the pile in the order you happen to open the files is how
a week disappears into one function that turns out to need an instrumented
compiler.

---

## Step 0 — a warning about sorting by word count

Do not rank the backlog by `words`. Positional word counts are a volume, and
volume does not predict cost:

- One wrong enum constant produced **183** "structural" words. It was a
  one-line fix.
- A single inserted instruction produced **11** words, ten of which were the
  same instructions shifted by one slot.
- A callee-saved tie-break produced **2** words and could not be fixed from
  source at all.

Rank by **verdict class**. The word count is a tiebreaker inside a class, not a
sort key across classes.

`compare` ranks candidates *of one function* on `aligned_total` rather than
`words` for the same reason the second bullet exists — that is a within-function
improvement, and it does not make either number a way to order a backlog.

---

## Step 1 — build the worklist

One function per line: symbol, expected object, your build's object. Keep it in
the repository so it survives a reboot.

```sh
cat > worklist.txt <<'EOF'
func_802963D0_6A7A80  expected/build/code/gfx.o     build/code/gfx.o
func_80296A10_6A7EC0  expected/build/code/gfx.o     build/code/gfx.o
func_8029B1C4_6A9674  expected/build/code/anim.o    build/code/anim.o
EOF
```

Both objects come from **whole translation units** — your normal build output
and the project's expected object. Do not isolate the functions; `compare` is
symbol-scoped and does the isolation for you, and a hand-built harness changes
codegen (see [Minute 1](START_HERE.md#minute-1--do-i-need-to-isolate-the-function-first)).

Build everything once before you start, so the whole sweep reflects one tree
state.

## Step 2 — classify the whole pile in one pass

```sh
#!/bin/sh
# triage.sh - classify every function in worklist.txt
set -eu

OBJDUMP=${OBJDUMP:-/opt/mips/bin/mips64-elf-objdump}
mkdir -p .triage
: > .triage/all.jsonl

while read -r symbol target candidate; do
    [ -n "${symbol:-}" ] || continue
    case "$symbol" in \#*) continue ;; esac
    decomp-workbench compare "$target" "$candidate" \
        --function "$symbol" \
        --objdump "$OBJDUMP" \
        --json > ".triage/$symbol.compare.json" || true
    decomp-workbench view "$target" "$candidate" \
        --function "$symbol" \
        --objdump "$OBJDUMP" \
        --json > ".triage/$symbol.view.json" || true
done < worklist.txt
```

Run it with `sh triage.sh`, not by sourcing it. Two portability notes, since
this is the one script that has to work on everyone's machine:

- `while read -r ... < file` is identical in `sh`, `bash`, and `zsh`. A
  `for f in $(cat list)` loop is **not** — `zsh` does not word-split unquoted
  expansions by default, so that idiom silently produces one giant argument
  under `zsh` and works under `bash`. Use `while read`.
- `|| true` keeps the loop alive when a command exits non-zero. `compare`
  exits non-zero only with `--fail-on-mismatch`, but a missing object or a
  symbol you spelled wrong will exit non-zero too, and you want the other
  twenty-nine results.

Both commands are worth running. `compare` gives you the released verdict
vocabulary and the raw/word split; `view` gives you the mechanism verdict, the
playbook name, the lane divergence, and the aligned counts. **The two disagree
usefully** — `compare`'s `structure-mismatch` on eleven positional words is
`view`'s `structure` on one inserted instruction.

## Step 3 — build the triage table

```sh
#!/bin/sh
# table.sh - one row per function, sorted by class then aligned size
set -eu

for f in .triage/*.view.json; do
    python3 - "$f" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
v = json.loads(p.read_text())
c = json.loads(p.with_name(p.name.replace(".view.", ".compare.")).read_text())
print("\t".join(str(x) for x in (
    v.get("playbook", "?"),
    v.get("verdict", "?"),
    c.get("verdict", "?"),
    v.get("structural", 0),
    v.get("register", 0),
    c.get("words", 0),
    v.get("signature", ""),
    v.get("symbol", p.name.split(".")[0]),
)))
PY
done | sort -k1,1 -k4,4n -k5,5n
```

You get something like this, and this table is the plan:

```text
ast-shape          commutative-order  allocation-mismatch  0  2   2   prefix-exact@41   func_8029B1C4
constant-audit     constant           structure-mismatch   0  0   183 prefix-exact@12   func_80296A10
g0-schedule-probe  schedule           structure-mismatch   0  0   9   prefix-exact@88   func_802A0044
structure-buckets  structure          structure-mismatch   7  0   61  prefix-exact@5    func_802963D0
temp-fifo-phase    phase-shift        allocation-mismatch  0  6   6   prefix-exact@12   func_802A1180
pool-position      allocation         allocation-mismatch  0  4   4   prefix-exact@30   func_802A22C0
forced-color-oracle register-permutation allocation-mismatch 0 1  1   prefix-exact@3    func_802A3400
```

Note what the second and third columns are doing. Three functions that
`compare` calls `allocation-mismatch` are three *different* problems, and one
of them (`ast-shape`) is not an allocation problem at all. That distinction is
the entire value of running `view` over the batch.

---

## Step 4 — work the classes in this order

### Round 1: the one-variant classes

Do all of these before you look at any register problem. Each is a single edit
and a single rebuild.

| Class | What to do | Guide |
|---|---|---|
| `constant-audit` | Read the immediate out of the target assembly, fix the enum, **then re-derive every fake in the function** | [Lever 1](field-guide.md#1-wrong-constant-masquerading-as-structure) |
| `ast-shape` | Rewrite the assignment as `x \|= y` | [Lever 2](field-guide.md#2-commutative-operand-order) |
| `g0-schedule-probe` | Rebuild that one candidate with `-g0` and compare again | [Lever 3](field-guide.md#3-the--g0-diagnostic) |

The `-g0` round is the highest-value hour in the whole backlog, because it does
not fix functions — it **retires** them. Anything whose divergent region
collapses under `-g0` has correct C, and the residual is `-g3` `.loc`-barrier
scheduling. Mark it, stop searching source for it, and take it off the pile.

Re-run `triage.sh` after this round. Fixing a constant re-shapes the whole
function, and several rows will have moved class.

### Round 2: structure

`structure-buckets` rows need real decompilation work, not levers. Take the
largest hunk in each and work it against whatever ground truth you have. Two
things to check before you start typing:

- If the earliest hunk begins at a `lui`/`li`/`andi`, you have a constant
  problem wearing a structure costume — go back to round 1.
- If this function was ported from a scratch or matched in a different tree,
  check flag parity and context parity first
  ([lever 4](field-guide.md#4-flag-parity-and-context-parity)). A single
  missing assembler flag has produced 78 structural words on source that was
  already correct.

Hold every allocator experiment until the instruction count and opcode schedule
are stable across the whole pile.

### Round 3: the register classes

Now the pile is small and every row is register-only. Split it by lane, which
`view` has already told you:

**`temp-fifo-phase`** — the temp lane shows `rotation=+N`. One upstream event.
The lever is in the *preceding* block:
[hoist a call argument](field-guide.md#14-temp-fifo-phase--perturb-the-preceding-block),
[the phantom pop](field-guide.md#15-the-phantom-pop), or
[the redundant mask](field-guide.md#16-the-redundant-mask-lever). Do not edit the
sites the hunk prints — they are downstream of a queue.

**`pool-position`** — a colored web took the wrong slot. Three sub-families,
and they are about *adding*, *removing*, and *re-ranking* webs:
[dead-web positioning](field-guide.md#7-dead-web-positioning),
[expression dead reads](field-guide.md#8-expression-dead-reads),
[the read-count dial](field-guide.md#9-the-read-count-priority-dial),
[chain-split](field-guide.md#10-the-chain-split-dead-read),
[pool-vs-temp routing](field-guide.md#11-pool-vs-temp-routing),
[copy-propagation defeat](field-guide.md#13-copy-propagation-defeat).

**`forced-color-oracle`** — a consistent bijection, usually a callee-saved
tie-break. This is the class to *stop* on if your project has no instrumented
compiler ([lever 19](field-guide.md#19-callee-saved-tie-breaks-and-the-forced-color-oracle)).
Bundle it and move on; you are not going to reach it from C.

**Coalescing** — if the entire residual is one `move` plus a downstream
substitution, try [the return type](field-guide.md#17-kr-implicit-int-return-type)
before anything else. It is one variant and it is frequently the whole answer.

---

## Step 5 — sweep a family with `campaign`

When a function needs a *family* rather than a hypothesis — six placements of a
dead read, `n` stacked reads for the priority dial — generate the variants and
let the campaign run them.

```sh
#!/bin/sh
# sweep.sh - one dimension, one campaign
set -eu

SYMBOL=$1
TARGET=$2

mkdir -p variants
i=0
for site in 12 18 24 31 40 47; do
    i=$((i + 1))
    awk -v line="$site" 'NR==line { print "    if (gTexTab[tab]) {}" } { print }' \
        src/code/gfx.c > "variants/deadread-$i.c"
done

decomp-workbench campaign "$TARGET" variants/*.c \
    --function "$SYMBOL" \
    --objdump "${OBJDUMP:-/opt/mips/bin/mips64-elf-objdump}" \
    --compile-command './tools/compile-one.sh {source} -o {output}' \
    --compile-cwd "$PWD" \
    --cache-dir .workbench/cache \
    --ledger ".workbench/$SYMBOL.jsonl" \
    --jobs 8
```

Rules that keep a sweep honest:

- **One dimension per campaign.** A grid that varies two things tells you which
  cell won and nothing about why.
- **Each `{source}` is a full translation unit.** `compile-one.sh` is your
  project's normal single-file build. The variants are whole-file copies with
  one edit, which is exactly what the `awk` above produces.
- **It stops at the first exact match** by default; candidates already in flight
  are still finished and recorded. Pass `--no-stop-on-exact` when you want the
  whole grid for a basin census.
- **Declare behavior-changing environment with `--env`** so it enters the cache
  key, or you will get a cache hit for a different compiler.
- **Keep the ledger.** One JSONL file per function, appended forever. It is the
  only record of which families are dead, and dead families are half of what you
  learn.

A basin census over the whole grid is worth running once per function on the
stubborn ones: if every cell in a family produces the same word count, that
family is inert here and you never need to try it again.

## Step 6 — track the pile

```sh
#!/bin/sh
# progress.sh - where is the backlog
set -eu
for f in .triage/*.view.json; do
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(d.get("playbook","?"))' "$f"
done | sort | uniq -c | sort -rn
```

```text
   9 structure-buckets
   7 pool-position
   5 temp-fifo-phase
   4 done
   3 constant-audit
   2 forced-color-oracle
   1 g0-schedule-probe
```

Re-run this after every round. The number you are managing is not "words
remaining" — it is **how many functions are in a class you have a lever for**.
When that number stops falling, you have reached the boundary of source search
for this batch, and the remaining rows are candidates for an instrumented
toolchain or for asking someone else.

---

## Step 7 — when to hand one off

Bundle it when the class is `forced-color-oracle`, or when you have exhausted
the lever family for its class and the ledger shows the basin is flat.

```sh
decomp-workbench bundle-scratch scratch/func_802A3400 \
  --target-assembly asm/nonmatchings/gfx/func_802A3400.s \
  --context ctx.c \
  --source variants/best.c \
  --platform n64 \
  --compiler 'IDO 7.1' \
  --compiler-flags='-O2 -mips2' \
  --diff-label func_802A3400
```

Ship the `view` output with it. A question that reads "verdict
`register-permutation`, one bijection `s1->s2`, prefix exact to 3, 830 source
variants flat" gets an answer. "It's 1 word off" does not.

---

## Try the triage on the shipped fixtures

Both halves of step 2 run right now with no ROM and no compiler, using
`compare-dumps` and `view-dumps`:

```sh
decomp-workbench compare-dumps \
  examples/fixtures/phase-shift-target.objdump \
  examples/fixtures/phase-shift-candidate.objdump \
  --function animStep --json
```

```sh
decomp-workbench view-dumps \
  examples/fixtures/phase-shift-target.objdump \
  examples/fixtures/phase-shift-candidate.objdump \
  --function animStep --json
```

```text
"playbook": "temp-fifo-phase",
```

Compare the two `verdict` values and the two `words`/`register` counts. That
gap — `allocation-mismatch` from one, `phase-shift` with a named playbook from
the other — is what the triage table exists to expose across thirty functions
at once.

## See also

- [Start here](START_HERE.md) — the loop, for one function.
- [Field guide](field-guide.md) — the levers referenced throughout.
- [Candidate campaigns](campaigns.md) — every campaign option, the cache key,
  and the ledger schema.
- [Aligned mechanism view](view.md) — the full `view` JSON schema.
- [Scratch bundles](scratch-bundles.md) — the handoff format.
