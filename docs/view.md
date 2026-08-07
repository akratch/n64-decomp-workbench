# Aligned mechanism view (`view`)

`compare` answers *how different are these two objects?* Mid-campaign the
question is different, and `view` is built for it:

1. Where does the divergence actually begin, and is the first thing that
   diverges a *shape* difference or a *register* difference?
2. Which mechanism owns it — allocation, temp phase, schedule, a constant, an
   expression shape, or real structure?
3. Which lever family moves it?

One command, one screen, four sections: verdict header, register lanes,
classified hunks, and a lever footer.

```sh
decomp-workbench view build/target.o build/candidate.o --function animStep
```

`--function` and `--symbol` are the same option, as on every command that
selects one function; passing both with different values is refused instead of
silently resolved. Objects are optional:
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
view animStep  target_instructions=24 candidate_instructions=24 aligned_rows=24 match=18 target_frame_size=-32 candidate_frame_size=-32 register_profile=ido53
verdict: phase-shift  structural=0 schedule=0 register=6 constant=0 hunks=1 playbook=temp-fifo-phase
signature: prefix-exact@12 state-divergence@temp:5 register-first-divergence
webs: w1 t7->t8 x2, w2 t8->t9 x2, w3 t9->t6 x2, w4 t6->t7 x2
the FIRST divergence is a register-class divergence, not a structural one: the decision was made upstream of hunk 1 even though it surfaces there.

REGISTER LANES (per-class assignment sequences, matching instructions included)
  pool  target     t0 t1 a0   slots=0..2/3
        candidate  t0 t1 a0
                   identical 3/3
  temp  target     t6 t7 t8 t9 t6 t7 t8 t9 t6   slots=0..8/9
        candidate  t6 t7 t8 t9 t6 t8 t9 t6 t7
                   ---------------^ slot=5 aligned_row=12 rotation=+1

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

The `webs:` header line is that conclusion in one line, printed before the
hunks rather than after them, because a reader who stops at the first
divergence would otherwise never reach the table that explains it. The full
`WEBS` table below still carries the per-web row lists.

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
# verdict=structure-mismatch aligned_total=1 words=11 regs=10 fp=1

decomp-workbench view-dumps \
  examples/fixtures/shifted-insertion-target.objdump \
  examples/fixtures/shifted-insertion-candidate.objdump --symbol blockSum
# verdict: structure  structural=1 ... displacement=1 hunks=1
```

Eleven positional words; one inserted `sll`, plus one branch whose encoded
offset moved because of it. Everything else was the same instruction in a
different place.

`compare` reports the aligned counts too — `aligned_total` and its class split
come from this same analysis, and they are what ranks candidates. `view` is
what tells you **where**: the hunk, the lane, the web, and the lever.

The `playbook=` token in the verdict line is a `guide` topic. Whatever it says,
`decomp-workbench guide <playbook>` prints that family's field-guide levers;
so does the verdict itself, and so does any lever number.
[From verdict to edit](from-verdict-to-edit.md) walks one of them to a source
change.

Two anchorings are built with `difflib.SequenceMatcher(autojunk=False)`, and
the one that explains more of the function as identical wins:

1. anchor on normalized instruction **text**, then pair by **opcode** inside
   each unmatched region;
2. anchor on **opcode**, then pair by text inside each unmatched region.

Neither is safe alone, and both failures are real. Opcode anchoring cannot
resolve a run of repeated opcodes: eight `addu` instructions with one inserted
among them align position by position, and four correct instructions are then
reported as register differences beside a phantom insertion. Text anchoring
inherits `difflib`'s greedy longest-block anchor: on a function whose text
repeats, the longest single common run can sit past the change, and everything
before it is discarded — on one 1500-instruction fixture that produced 61
matches and 2079 structural rows. Scoring both against "how many instructions
are explained as unchanged" settles it; ties go to the text anchoring, which
cannot mispair by construction.

Instructions paired inside an unmatched region are the population that
operand-level classification exists for: same opcode, different registers or
immediates.

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
| `displacement` | same aligned branch destination, different encoded offset |
| `relocation` | differs only in linker-controlled relocation fields |
| `pool` | reads the same literal-pool slot through a differently named anchor |
| `pool_layout` | literal-pool accesses that resolve to different slots or widths |
| `constant` | same opcode and registers, different immediate |
| `commutative` | same opcode and operand multiset, commutative pair swapped |
| `register` | same opcode, different register operands |
| `schedule` | a run whose two sides hold the same instructions in another order |
| `structural` | everything else: opcode shape, symbols, control flow |

`displacement` is what an insertion does to every branch that spans it. The
bytes differ, so the row is not `match`, but nothing a source change controls
differs either, so the row does not open a hunk: it is counted in the header,
annotated where it happens, and left out of the prefix signature. Letting it
open hunks would scatter one insertion across the whole function, which is the
phantom cascade this command exists to remove.

`pool` is the same idea one level out. Whether a literal is reached through one
named external symbol per datum (`lui at,%hi(D_80052AA8)`) or through one dense
anonymous section symbol plus an addend (`lui at,%hi(.rodata)` /
`lwc1 $f0,8(at)`) is a property of the two *symbol tables*, decided before
either object was written. Both spellings resolve to a slot and the rows are
compared on the slot, so a matching pool disappears instead of filling the
`relocation` class — 88 rows on one recorded pair. A site whose slot, access
width, or anchor correspondence genuinely differs becomes `pool_layout`, which
is reported and gets its own verdict.

The resolution is reported as `pool_resolution`, because the two tiers answer
different questions. `absolute` means both sides anchor on a section symbol, so
the byte offset inside the section was compared directly. `anchor-correspondence`
means at least one side names each literal with an external symbol whose address
the object does not carry; what was checked there is that the two objects' slots
are in one-to-one correspondence at a constant displacement per anchor pair.
Neither tier claims the two pools hold the same *bytes* — a target with no
`.rodata` section of its own cannot support that claim, and it stays with the
project's link or ROM check.

The verdict names the cheapest mechanism that explains the whole residual.

| Verdict | When | Playbook |
|---|---|---|
| `exact` | nothing differs | `done` |
| `words-identical` | only relocation-controlled or pool-anchoring fields differ | `relocation-only` |
| `pool-layout` | literal-pool accesses resolve to different slots | `constant-audit` |
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

* `prefix-exact@N` — aligned rows `0..N-1` are identical outside
  relocation-controlled and alignment-controlled fields; `N` is the first
  divergent aligned row. `prefix-exact@all` means nothing diverged. Relocation
  fields are masked exactly as they are in `compare`, and a branch whose
  encoded offset moved because of an insertion does not shorten the prefix
  either — both are counted and printed, neither is a source difference.
* `state-divergence@<class>:<slot>` — the first lane slot where a register class
  diverges.
* `unknown-relocation:KIND` — a relocation kind with no known field mask is
  present. Nothing is guessed: an affected difference is reported as a real
  difference rather than excused.
* `register-first-divergence` — the first divergence is a register-class
  divergence rather than a structural one. The block where it surfaces is not
  the block where it was decided, so the lever is upstream; one campaign round
  burned 13 variants on the visible block before that was understood.

  This command reads two disassemblies, so a state divergence that leaves the
  bytes alone is not observable from here: anything that changes a lane also
  changes an instruction. Proving *where* upstream needs a pool trace, which
  this command does not read. The signature says what is actually in evidence
  and no more.

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

The caret line carries two different units, and they are named separately:
`slot=` is a position in *this lane*, and `aligned_row=` is a row of the
alignment — the same unit as the header's `aligned_rows` and every hunk range,
so it is the number to look up in the hunk listing. Both spellings are also the
JSON keys.

## Webs and coloring

Register substitutions are grouped into webs so one swap reads as one web
instead of many problems. Every site carries its web annotation (`t8->t6 [w1]`)
in monochrome; with a terminal that supports it, `--color auto` gives each web a
stable color across the whole screen — on the `webs:` header line, on the
substituted register token inside the disassembly, on the trailing annotation,
and in the `WEBS` table. `--color never` and `NO_COLOR` disable it. Glyphs are
ASCII everywhere, and the verdict itself is bolded and colored by family so a
scrolled batch is separable before it is read.

Every non-matching row is annotated, whether or not it falls inside the hunk
being printed. The `>` marker is what distinguishes this hunk's rows from the
evidence around them; a context row whose swap belongs to a known web says so.

`--width` never costs an annotation, and never costs a `next:` line. When a row
or a guidance sentence will not fit, it wraps to a continuation line rather than
being cut — the assembly columns are what the requested width truncates. The
footer carries the dead-family warnings, and a truncated warning is worse than
no warning.

## Orientation notes and `--terse`

Three one-line notes are printed by default: what the signature's parts mean in
order, what the `pool` and `temp` lane classes are, and where the label registry
lives (`decomp-workbench --explain-keys`). They are true of every run and useful
on the first few, so the reader who needs them does not have to know to ask.
`--terse` removes exactly those three lines and nothing else — every label,
count, lane, hunk, web, and footer line is unchanged.

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
| `match`, `displacement`, `structural`, `schedule`, `register`, `constant`, `commutative`, `relocation`, `pool`, `pool_layout` | aligned row counts |
| `pool_resolution`, `pool_slots` | how literal-pool accesses were resolved, and the slot count each object references |
| `verdict`, `playbook`, `signature`, `prefix_exact` | diagnosis |
| `hunks` | `hunk`, `class`, `rows`, `target`, `candidate`, `target_bytes`, `candidate_bytes`, `classes` |
| `lanes` | `class`, `target`, `candidate`, `rows`, `slot`, `aligned_row`, `rotation` |
| `webs` | `web`, `target`, `candidate`, `count`, `rows` |
| `next` | lever guidance lines |
| `register_profile` | lane class table in use |
| `register_report` | present with `--report-regs` |

List-valued keys render as a count in the human header (`hunks=1`) and as the
list in JSON.

These names live in the same metric registry as the comparison and campaign
keys, so `view --explain-keys` (or the root `--explain-keys`) prints them
with their meanings. A test asserts the registry and the output are *one set* in
both directions: a key can neither be printed without an explanation nor
explained without being printed.

The view counts aligned rows; `compare` counts positional words. Where a
spelling appears in both registries — `target_instructions`,
`candidate_frame_size` — it is a different number, which is why the two
vocabularies are listed separately.

## Options

| Option | Effect |
|---|---|
| `--symbol` / `--function` | select one function (recommended); two spellings of one option, and conflicting values are rejected rather than silently resolved |
| `--explain-keys` | print the key registry and exit |
| `--section`, `--objdump` | object inputs only |
| `--context N` | aligned rows of context around each hunk (default 2) |
| `--max-hunks N` | render at most N hunks, 0 for all (default 20) |
| `--lane-window N` | lane slots rendered around a divergence (default 32) |
| `--register-profile` | lane class table (default `ido53`) |
| `--report-regs` | per-row register operands |
| `--terse` | drop the one-line orientation notes; every label and count stays |
| `--color auto\|always\|never` | ANSI web and verdict coloring |
| `--width`, `--pager` | bound and page terminal output; annotations wrap rather than truncate |
| `--html PATH` | self-contained report: lanes, per-hunk sections, webs, and the JSON payload |
| `--json` | machine-readable output |
| `--fail-on-mismatch` | exit 1 unless the verdict is `exact` or `words-identical` |
| `--census KEY=VALUE[,...]` | assert reported values; exit 3 if any predicate fails, 2 for an unknown key |

`--census` takes this command's keys — `structural=0`, `verdict=phase-shift`,
`prefix_exact=12`, `candidate_frame_size=-128` — and turns a shell loop into a
filter without a JSON parser in it:

```sh
decomp-workbench view-dumps \
  examples/fixtures/phase-shift-target.objdump \
  examples/fixtures/phase-shift-candidate.objdump \
  --function animStep --census verdict=phase-shift,register=6
```

```text
census: PASS verdict=phase-shift
census: PASS register=6
```

The exit-code contract is shared with `compare` and documented once, in
[object comparison](object-comparison.md#ask-a-question-and-read-the-exit-code---census).
The view's keys are its own: `register` here counts aligned rows, and
`aligned_register` on `compare` is the same number under the comparison
registry's spelling.

## Boundaries

* `view` diagnoses; it never claims a match. `exact` here means the aligned
  instructions and relocation layout agree for the selected function — run the
  project's normal link or ROM verification for proof.
* A run whose two sides hold the same instructions in a different order is
  reported as `schedule`, whether the alignment paired those instructions or
  left them unpaired. A reordering that is *also* a register change in the same
  rows cannot be separated from allocation by this evidence.
* Alignment is quadratic in the worst case. Measured end to end, including
  rendering: 500 instructions 0.008 s, 1500 0.035 s, 3000 0.11 s, 6000 0.37 s.
  A pathological stream (every instruction sharing one opcode) costs about
  0.22 s at 1500. Interactive well past vsprintf scale, but not linear.
* An empty selection is refused rather than reported as `exact`.
* Lane classes describe IDO 5.3 behavior. On another toolchain, add a profile
  rather than reading the `ido53` lanes as universal.
* Pool-trace rendering is not part of this command yet.

## The HTML report

`--html PATH` writes one self-contained file — inline CSS, no script, no
network — carrying the same evidence as the screen from the same view model:
a sticky verdict bar, the register lanes with the divergent slot outlined, one
linkable `<section id="hunk-N">` per hunk with context and divergence row
classes, a per-row substitution cell whose swatch links to its web, and a
`Webs` table that links each bijection back to every hunk it explains. The
machine-readable payload stays in the collapsed `<details>` block at the end.

The identity chip reports the share of aligned rows that are byte-identical.
That is deliberately *not* labelled a decomp.me score: that number comes from
the site's own scratch model, and two tools printing different numbers under
one name is how they come to disagree about whether a function is close.

## See also

* [Object comparison](object-comparison.md) — the exact verdict and mismatch
  classification `view` sits on top of.
* [Final-function campaign lessons](final-function-campaigns.md) — the reasoning
  the lever footer encodes.
* [Trace analysis](trace-analysis.md) — the next step when a register class
  needs allocator evidence.
