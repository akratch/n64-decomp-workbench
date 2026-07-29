# Aligned mechanism view (`view`)

`compare` answers *how different are these two objects?* Mid-campaign the
question is different, and `view` is built for it:

1. Where does the divergence actually begin — not where the first byte differs,
   but where the compiler's state first diverges?
2. Which mechanism owns it — allocation, temp phase, schedule, a constant, an
   expression shape, or real structure?
3. Which lever family moves it?

One command, one screen, four sections: verdict header, register lanes,
classified hunks, and a lever footer.

```sh
decomp-workbench view build/target.o build/candidate.o --function animStep
```

`--function` and `--symbol` are the same option. Objects are optional:
`view-dumps` runs the identical analysis on retained GNU objdump text, so every
screen here works from reduced, redistributable dumps.

```sh
decomp-workbench view-dumps \
  examples/fixtures/phase-shift-target.objdump \
  examples/fixtures/phase-shift-candidate.objdump \
  --function animStep
```

## Reading the screen

```text
view animStep  target_instructions=24 candidate_instructions=24 aligned_rows=24 match=18 target_frame_size=-32 candidate_frame_size=-32
verdict: phase-shift  structural=0 schedule=0 register=6 constant=0 hunks=1 playbook=temp-fifo-phase
signature: prefix-exact@12 state-divergence@temp:5 upstream-byte-invisible
state diverges at the first byte difference and the class is register: the lever is UPSTREAM of hunk 1, not inside it.

REGISTER LANES (per-class assignment sequences, matching instructions included)
  pool  target     t0 t1 a0   slots=0..2/3
        candidate  t0 t1 a0
                   identical 3/3
  temp  target     t6 t7 t8 t9 t6 t7 t8 t9 t6   slots=0..8/9
        candidate  t6 t7 t8 t9 t6 t8 t9 t6 t7
                   ---------------^ divergence=5 index=12 rotation=+1

HUNK 1  class=register rows=12..17 target=12..17 candidate=12..17 target_bytes=0x30..0x44 candidate_bytes=0x30..0x44
     10   sll $t6,$t9,2     | sll $t6,$t9,2
     11   addu $t1,$t0,$t6  | addu $t1,$t0,$t6
     12 > addu $t7,$t1,$s0  | addu $t8,$t1,$s0   t7->t8 [w1]
     13 > lw $t8,20($t7)    | lw $t9,20($t8)     t8->t9 [w2] t7->t8 [w1]
     14 > andi $t9,$t8,0xff | andi $t6,$t9,0xff  t9->t6 [w3] t8->t9 [w2]
     15 > sw $t9,24($s0)    | sw $t6,24($s0)     t9->t6 [w3]
     16 > lw $t6,28($s0)    | lw $t7,28($s0)     t6->t7 [w4]
     17 > addu $a0,$s0,$t6  | addu $a0,$s0,$t7   t6->t7 [w4]
     18   jal 0 <animApply> | jal 0 <animApply>
     19   nop               | nop

WEBS (one consistent substitution may explain many sites)
  w1  t7->t8  count=2 rows=12,13
  w2  t8->t9  count=2 rows=13,14
  w3  t9->t6  count=2 rows=14,15
  w4  t6->t7  count=2 rows=16,17

next: one upstream event, not 6 sites (temp lane, slot 5, aligned row 12, rotation +1).
      perturb the PRECEDING block: hoist a call-argument expression into a named local, which reorders value deaths.
      or materialize a phantom pool get with `(x == C) != 0` inside a real `if`; a bare discarded expression is dropped with no codegen effect.
      do not fix the divergent sites individually; declaration-order permutation is a dead family here.
```

Four register substitutions, four webs, one mechanism: the temp lane runs one
slot ahead from slot 5. The fix is upstream of every printed site.

## Alignment is LCS, never positional

Counts are aligned counts. Positional counting turns one insertion into a
cascade of unrelated-looking differences; on a real campaign function it
reported roughly 76 scattered differences where the aligned truth was roughly
43 hunks, and on another it reported 635 words where the aligned truth was 27
structural plus 8 register.

The shipped insertion fixture reproduces the effect in miniature:

```sh
decomp-workbench compare-dumps \
  examples/fixtures/shifted-insertion-target.objdump \
  examples/fixtures/shifted-insertion-candidate.objdump --symbol blockSum
# verdict=structure-mismatch words=11 regs=10 fp=1

decomp-workbench view-dumps \
  examples/fixtures/shifted-insertion-target.objdump \
  examples/fixtures/shifted-insertion-candidate.objdump --symbol blockSum
# verdict: structure  structural=1 ... hunks=1
```

Eleven positional words, ten of them phantom; one inserted `sll`.

Two passes run over the streams:

1. `difflib.SequenceMatcher(autojunk=False)` aligns the **opcode** streams.
   Unequal blocks become structural or schedule hunks.
2. Inside each aligned pair, the operand difference is classified.

Branch destinations are compared by *aligned row*, not by encoded displacement,
so an insertion does not turn every later branch into a phantom difference. A
relocated operand is never resolved that way: its address field belongs to the
linker.

## Classes and verdicts

Each aligned row carries exactly one class. The header always prints the four
core counts, and adds `commutative` and `relocation` when they are non-zero.

| Class | Rule |
|---|---|
| `match` | identical instruction words and relocation layout |
| `relocation` | differs only in linker-controlled relocation fields |
| `constant` | same opcode and registers, different immediate |
| `commutative` | same opcode and operand multiset, commutative pair swapped |
| `register` | same opcode, different register operands |
| `schedule` | a run whose two sides hold the same instructions in another order |
| `structural` | everything else: opcode shape, symbols, control flow |

The verdict names the cheapest mechanism that explains the whole residual.

| Verdict | When | Playbook |
|---|---|---|
| `exact` | nothing differs | `done` |
| `words-identical` | only relocation-controlled fields differ | `relocation-only` |
| `constant` | only immediates differ | `constant-audit` |
| `commutative-order` | only commutative swaps | `ast-shape` |
| `schedule` | only reorderings | `g0-schedule-probe` |
| `phase-shift` | register-only, and a lane tail is a constant rotation | `temp-fifo-phase` |
| `register-permutation` | register-only, substitutions form one bijection | `forced-color-oracle` |
| `allocation` | register-only, no consistent permutation | `pool-position` |
| `structure` | only opcode-shape differences | `structure-buckets` |
| `mixed(...)` | several classes, listed with counts | the first class by precedence |

Composite verdicts list classes in fix order: constants first because they
cascade, structure second, register classes last.

**The verdict never filters the display.** Every non-matching aligned row is
printed inside its hunk. A verdict that suppressed a difference site once cost
a campaign a mis-framed brief, and suppression is a defect here by definition.

## Signatures

Signatures are modifiers, never verdicts.

* `prefix-exact@N` — aligned rows `0..N-1` are byte-identical; `N` is the first
  divergent aligned row. `prefix-exact@all` means nothing diverged. Relocation
  fields are masked here exactly as they are in `compare`, so a linker-supplied
  address never shortens the prefix.
* `state-divergence@<class>:<slot>` — the first lane slot where a register class
  diverges.
* `unknown-relocation:KIND` — a relocation kind with no known field mask is
  present. Nothing is guessed: an affected difference is reported as a real
  difference rather than excused.
* `upstream-byte-invisible` — the first byte difference *is* a register-class
  state divergence. The visible block is where the divergence surfaces, not
  where it was decided; the lever is upstream. One campaign round burned 13
  variants on the visible block before this was understood.

## Register lanes

A lane is the ordered sequence of registers a class is assigned, in emission
order, **including the instructions that match**. That is the decisive part: on
`modLoadAnimActual` the signal was in the temps that matched, and a display of
mismatched instructions alone hides the queue entirely.

Only definitions add a slot; stores, branches, and jumps read their operands.

Class tables are profile data, not hardcoded policy. The `ido53` profile is
derived from black-box pool probing and confirmed by the ugen deep dive:

| Class | Registers |
|---|---|
| `pool` | `v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5` |
| `temp` | `t6 t7 t8 t9 s8` |

Select another with `--register-profile`. `rotation=+N` on a lane means the
candidate tail equals the target tail rotated by `N` positions through the
registers that function actually uses — one upstream phase event, not N
decisions.

## Webs and coloring

Register substitutions are grouped into webs so one swap reads as one web
instead of many problems. Every site carries its web annotation (`t8->t6 [w1]`)
in monochrome; with a terminal that supports it, `--color auto` gives each web a
stable color across the whole screen. `--color never` and `NO_COLOR` disable it.
Glyphs are ASCII everywhere.

## `--report-regs`

Emits per-aligned-row register operands for both sides, matching rows included —
the readout campaigns previously rebuilt with objdump and a regular expression
once per variant. Under `--json` it appears as `register_report`.

## JSON

`--json` prints one schema whose keys are exactly the human labels. There is no
agent dialect and no human dialect.

| Key | Meaning |
|---|---|
| `symbol`, `target`, `candidate` | inputs |
| `target_instructions`, `candidate_instructions`, `aligned_rows` | sizes |
| `target_frame_size`, `candidate_frame_size` | stack frame adjustments |
| `match`, `structural`, `schedule`, `register`, `constant`, `commutative`, `relocation` | aligned row counts |
| `verdict`, `playbook`, `signature`, `prefix_exact` | diagnosis |
| `hunks` | `hunk`, `class`, `rows`, `target`, `candidate`, `target_bytes`, `candidate_bytes`, `classes` |
| `lanes` | `class`, `target`, `candidate`, `rows`, `divergence`, `index`, `rotation` |
| `webs` | `web`, `target`, `candidate`, `count`, `rows` |
| `next` | lever guidance lines |
| `register_profile` | lane class table in use |
| `register_report` | present with `--report-regs` |

List-valued keys render as a count in the human header (`hunks=1`) and as the
list in JSON. A test asserts every printed `key=` token resolves to a schema
key, so the two renderings cannot drift.

## Options

| Option | Effect |
|---|---|
| `--symbol` / `--function` | select one function (recommended) |
| `--section`, `--objdump` | object inputs only |
| `--context N` | aligned rows of context around each hunk (default 2) |
| `--max-hunks N` | render at most N hunks, 0 for all (default 20) |
| `--lane-window N` | lane slots rendered around a divergence (default 32) |
| `--register-profile` | lane class table (default `ido53`) |
| `--report-regs` | per-row register operands |
| `--color auto\|always\|never` | ANSI web coloring |
| `--json` | machine-readable output |
| `--fail-on-mismatch` | exit 1 unless the verdict is `exact` or `words-identical` |

## Boundaries

* `view` diagnoses; it never claims a match. `exact` here means the aligned
  instructions and relocation layout agree for the selected function — run the
  project's normal link or ROM verification for proof.
* A reordering of two instructions that share an opcode cannot be distinguished
  from an operand change by opcode alignment; it is reported as the operand
  class it looks like.
* Lane classes describe IDO 5.3 behavior. On another toolchain, add a profile
  rather than reading the `ido53` lanes as universal.
* Pool-trace and HTML renderings are not part of this command yet.

## See also

* [Object comparison](object-comparison.md) — the exact verdict and mismatch
  classification `view` sits on top of.
* [Final-function campaign lessons](final-function-campaigns.md) — the reasoning
  the lever footer encodes.
* [Trace analysis](trace-analysis.md) — the next step when a register class
  needs allocator evidence.
