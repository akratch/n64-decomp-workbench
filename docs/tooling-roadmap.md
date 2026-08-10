# Historical tooling roadmap from live campaigns

> **Status (2026-07-30).** Every adapter-level item originally listed as
> “Next” below has landed: original/static pass differential, behavioral
> fingerprints and cross-ROM lineage, semantic web/interference joins,
> stack-home reports, marker-aware source/listing correlation, portable pass
> work roots and calibration, experiment manifests/regions, register
> permutations, relocation aliases, and stable scheduler records with
> hash-pinned external profiles. The mutation-recipe library and richer
> emitted-instruction joins remain research because safe equivalence and
> validated producer fields need project evidence. See
> [Product status](product-status.md). The original proposals remain below so
> their acceptance reasoning is not rewritten after the fact.

This backlog records gaps observed while applying the workbench to late-stage
N64 decompilation functions. It is intentionally project-neutral and excludes
ROMs, target objects, and proprietary compiler files.

## Implemented

- Compiler working directories are explicit campaign inputs through
  `--compile-cwd`; they are validated, recorded, and included in cache keys.
- `campaign --json-summary` provides bounded ranking output without compiler
  streams or instruction-level register diffs.
- Globalcolor decisions can be filtered by procedure and can expose allocator
  masks, remaining-register counts, IR metadata, and interference neighbors.
- CDX allocator decisions are joined with target web metadata, so procedure and
  dtype filtering works even without legacy `CSAVE`/`CUP` records.
- Detailed globalcolor traces expose every evaluated color's final cost,
  best-before value, caller/callee class, available-color masks, and secondary
  tie-break state.
- Focused globalcolor lookups require a procedure/web pair, suppress unrelated
  rows, and report available webs when a lookup misses.
- Campaign summaries group source variants by compiled function-byte hash and
  choose the best-ranked representative for each object basin.
- Comparison reports classify relocation-controlled raw differences, emit
  action-oriented verdicts, and keep cross-ROM acceptance separate from exact
  object evidence.
- Comparison and ranking share one LCS-aligned mechanism view. Pure
  instruction reorderings remain scheduling residuals even when unrelated
  relocation addends differ elsewhere.
- `doctor` reports retained-dump/object-reader readiness, validates scratch
  handoffs, and prints a shell-quoted next command.
- `check-scratch` safely reads decomp.me export ZIPs/directories without
  extracting them, separates browser score context from object truth, and can
  recompile `ctx.c` plus source with the site's language-aware `src.c`/`src.cxx`
  line-reset semantics.
- The portable Agent Skill ships in package artifacts and has a safe,
  idempotent installer for Codex and Claude Code.

## Open, observed 2026-08-06

These came out of the `--tie` and lever-28 integration pass. Each is a design
question rather than a missing line of code, which is why it is filed here
instead of shipped.

### A tie is scored but does not reach the verdict

`probe-lines` classifies from the reflow and its control only. A `tie` variant
that moves the object toward the target is reported in the target block and in
the `next:` routing, but the verdict vocabulary
(`line-sensitive`/`not-line-sensitive`/`nondeterministic`) has no way to say
"this reassignment is the one". Adding a fourth verdict changes a published
schema's value set and would have to answer what a *partially* correct tie is
called, which the current evidence does not settle. Until then the toward/away
counts are the result and the verdict is only about ownership.

### Tie sweeps are manual

The natural next tool after `--tie` is a sweep: one statement, several
candidate line numbers, ranked by toward/away. `campaign` already owns
variant sweeps with caching and a durable ledger, but its unit is a compiled
source variant, not a probe run, and `probe-lines` has neither `--census`
predicates nor a ledger. Either `probe-lines` grows a bounded `--tie-sweep`
with its own state, or the probe becomes expressible as a campaign mechanism.
Doing both would give the same experiment two homes.

### Lever 28's placement axis has no tool

Placement of an alias mark is now a measured tuning axis (140/131/106 words on
`func_ovl8_803787C0` at head/`j`-loop/innermost). That is a scoped, ordered
search over source positions with a zero-instruction invariant to check — the
same shape as `experiment compose`'s bounded substitutions, but positional. A
mechanism that emits the placement ladder and asserts the instruction-neutral
invariant would turn a hand sweep into a recorded one.

### `pool-position` cannot route a lever from the footer

`pool-position` is an ambiguous playbook: its footer deliberately names three
families and picks none, so a lever list never prints there. Lever 28 is
reachable only through evidence-gated prose in the neutral block or through
`guide`. The real fix is a verdict that separates the three allocation
families, which needs lane evidence `view` does not currently produce, not
another sentence in the footer.

## Open, observed 2026-08-08

From the `object_interaction` campaign's stage-attribution work. Both items are
real, both have a working campaign-local prototype, and both are filed here
rather than shipped because promoting them as they stand would put an
unmeasured claim behind a workbench command.

### A stage-capture harness for the IDO driver

**The gap.** Answering "which stage decides X" means running `cfe`, `uopt`,
`ugen`, and `as1` by hand on the composed translation unit, which means
scraping `cc -show`, re-quoting `-Amachine(mips)` past the shell, threading the
`-XS<symtab>` temporary between the four stages, and then proving the
hand-driven object is byte-identical to the driver's. That is roughly forty
minutes of setup, it is the *only* way to attribute a decision to a stage, and
two campaigns (`ovl8`, `ge007`) have now built it independently as a local
shell script. The `ge007` prototype is 23 lines and hard-codes every path.

**The shape it would take.** `decomp-workbench stages SRC.c --cc DRIVER
--outdir D`: parse `cc -show`, replay the four stages retaining `.B`, `.O`,
`.s`, and `.o`, then assert the replayed object is byte-identical to the
driver's and fail loudly when it is not. The identity assertion is the whole
value — a replay that silently differs from the driver attributes decisions to
the wrong stage, which is worse than no harness.

**Why it is not shipped yet.** The command is only as good as its model of one
driver's `-show` output, and the workbench has exactly one measured driver: the
IDO 5.3 recompilation this campaign used. `cc -show` is not a stable interface,
the stage set is version-specific (7.1 differs, `accom` differs more), and the
`-XS` temporary threading is a driver detail rather than a documented contract.
Shipping a `stages` command implies it works for a reader's compiler, and this
repository's rule is that a claim carries its provenance. The honest sequence
is: first a *recorded* `-show` transcript format that a reader can supply for
their own driver (redistributable, like the existing objdump fixtures), then a
replay engine over that record, then the identity gate. Note also that
`pass replay-as1` and `toolchain calibrate` already own the "replay a pass and
prove it reproduces the object" contract; a stage harness should extend that
vocabulary rather than open a second one.

**Prototype:** `p3f/work/stages.sh` in the `ge007-object-interaction` campaign
(not redistributable: it names a local toolchain and include tree).

### A ucode record decoder

**The gap.** The `cfe`/`uopt` intermediate streams decode with a small, fixed
record format — 8 bytes per record, an opcode record `[op][ty][flags:2]
[word:4]`, with operand records `[00 00 00][kind][value:4]` following some
opcodes — and every campaign that has needed it has rediscovered that by
inspection. A decoder plus a `--diff A B` mode reporting differing record
ranges is the one query a "which stage owns this decision" investigation
actually runs.

**The known correction, recorded here so it is not rediscovered a third
time.** A decoder written for `accom` 4.1 (`phase3-bdump.py` in the `ssb64`
overlay-8 campaign repository, which is not this repository and is deliberately
not edited by this note) does decode IDO 5.3 streams — the record format is the
same — but it carries one real bug for `cfe.B`: **opcode `0x49` carries two
operand records, not one.** A decoder using the "one operand record may follow
an opcode" heuristic goes out of phase at the first `0x49` and mis-pairs every
record after it. `uopt.O` is unaffected in practice because its expression code
holds no bare `0x49` runs. Opcode identities confirmed by micro-probe on 5.3:
`0x01` add, `0x36` iload, `0x51` line, `0x52` push, `0x5b` mul, `0x7b` store;
type byte low nibble `d` means float.

**Why it is not shipped yet.** The opcode table is empirical and partial. About
two dozen opcodes are named, most of them with a question mark, and the operand
arity that makes the stream parseable at all is known for a handful. A decoder
in this repository would print `op49` beside `add` with no way for a reader to
tell the probed identification from the guessed one — the same failure the
register-profile evidence strings exist to prevent. The shippable version is a
per-opcode **arity** table (which is what parsing needs, and which a probe can
establish one opcode at a time) with the arity's provenance recorded per entry,
plus `--diff`; the mnemonic table stays advisory and clearly labelled until
probed. Until then the format and the `0x49` correction are documented here so
the next campaign starts from the fixed version.

**Prototype:** `p3f/udump.py` in the `ge007-object-interaction` campaign.

### A stage-position map

**The gap.** Nothing joins an object row to the stage state that produced it,
and the two orderings a campaign would naturally assume are both false. The
measurement: editing one floating-point sum changed exactly sixteen records of
`uopt.O` (indices 3279–3310 of 17890, 18% into the stream, corresponding to
object instruction ~863), and the resulting object first differed from the
unedited one at **instruction 94** — 2% in, with 143 differing rows *before*
the edited site. An instrumented `ugen` reported the fp allocate/free decisions
as byte-identical until event 996, while the first trace divergence at event
875 was a free-list **tail order** flip. So "ucode record index implies program
position" is false, and so is "allocator event order implies emission order".
A bisection anchored on either localises the wrong statement. This was checked
for artefacts: the hand-run stage pipeline reproduced the campaign's object
byte-for-byte, and the instrumented `ugen`'s own `ugen.s` was byte-identical to
the stock one.

**The shape it would take.** Per object row, the `uopt.O` record range and the
`ugen` register event that produced it — `ugen` can be instrumented to emit
`(event n, emitted instruction index)` pairs. With that, "which source
statement owns object row R" stops being guesswork whenever a change is
non-local, and "how many extra fp temporaries do we request before row 964"
becomes a subtraction instead of a search.

**Current boundary.** The uopt.O half needs the ucode decoder above,
which is itself deferred and for the same reason: the record arity table is
empirical. Shipping the map without it would mean publishing record *indices*
that the workbench cannot parse into records, which is a coordinate system with
no origin. The `ugen` half now ships: `instrument ugen` stamps free-list events
with the pass's forward-ibuffer ordinal, and `trace fifo --emission-map` joins a
measured ordinal calibration to object row and source file/line. It does not
infer that the ordinal is an object row; missing calibration remains null and
is reported as required. The remaining map work is therefore the validated
uopt-record range, not the ugen emission hook.

**What did ship instead.** The half of this that needs no stage instrumentation
at all is now `force-rows` (see
[Compiler instrumentation](compiler-instrumentation.md)): build the same source
twice under one allocator control and the rows that moved are, by construction,
the rows that control owns. That is a *measured* row-to-decision join rather
than a positional one, and it does not need a position map because it does not
assume an ordering. It cannot replace the map — it answers "which rows does
this control own" one control at a time, not "which decision owns this row" —
but it removes the case that forced the campaign to bisect by hand.

**Prototypes:** `tools-p3d/ugen_ins` and `p3h/tools/webrows.py` in the
`ge007-object-interaction` campaign.

### A save-class force control and the terms of the verdict

**The gap.** The shipped globalcolor force grammar is
`p[12]:w<N>=(c<M>|s)` — force a colour, or force the split path. Neither
expresses the outcome that removes a value from the allocator entirely:
`compute_save`'s class-2 verdict, which strikes the web from both candidate
loops *before* any colour is considered. A campaign holding only `=c`/`=s` can
ask "would this web be happier in another register" but not "is this web
coloured at all", and it can never test the mirror question — "the target
colours one more web than we do" — because a class-2 web never reaches the
decision site where `=c` is read. Two stages of one campaign framed their
residue question as "how does a local avoid uopt colouring?" with no way to
price the answer before searching for a C spelling for it.

**The shape it would take.** Extend the grammar to
`p[12]:w<N>=(c<M>|s|n|y)`, with `n` forcing class 2 and `y` forcing class 1,
applied at `f_compute_save`'s verdict store — the single writer, memoised and
phase independent. Alongside it, a per-web `[CDX] savedetail` record carrying
the *terms* of the verdict (`occ gross chargeA chargeB net divisor dtype save
class`) and a per-occurrence `[CDX] saveocc` (`usesdefs weight term`). Steering
a compiler heuristic from source requires seeing the number, not inferring it:
with the readout it took one build to learn that 293 of one procedure's 404
uncoloured webs sit at exactly `net = 0.0`, one unit of gross from the other
side of a strict `>`.

**Why it is not shipped yet.** The change is not a grammar change, it is a new
anchor in the pinned generated source. Every existing anchor is a
`_replace_once` against a SHA-pinned `build/5.3/uopt.c` that this repository
does not contain and cannot test against; an anchor that fails to match makes
`instrument-uopt-globalcolor` refuse a file it previously accepted, and an
anchor that matches the wrong site silently mis-forces. Accepting `=n`/`=y` in
the parser *without* the anchor would be worse than either: the workbench would
validate a control the shipped pass ignores, so a sweep would record "forced,
no change" for a force that never applied — the exact failure the
phase-qualification gate exists to prevent. The honest sequence is the anchor
and its fidelity gates first, then the parser and the record schema.

**What did ship instead.** The two decision-record fields that read as if the
verdict were already being reported are now documented as what they are:
`class=` is `regclassof` (integer versus floating point), *not* the save class,
and `nocs=` is the compressed divisor `((n - 2) >> 2) + 2`, not the occurrence
count — so `save * nocs` is not "saving times uses", and `trace-webs` no longer
prints those three numbers in the shape of an equation.

**Prototype:** `p3h/LOG.md` §0 and the env-gated, validity-gated
`ido53-globalcolor-recomp/build/5.3/uopt.c` patch in the
`ge007-object-interaction` campaign, whose binary lives in `p3h/tc/`.

## Open, observed 2026-08-08 (UX round)

From the round that shipped `score`, `next`, `compare --by-region`, `note`,
and the compiler-laws document. These two came out of the same review and are
filed here rather than shipped because each needs a decision this evidence does
not make, not a line of code.

### A campaign is not the same object as a campaign manifest

**The gap.** A late-stage campaign runs two tracked artifacts (a pushed-best
and a record-true bundle), an oracle floor with a knob count, an attributed
residue, and a list of what is not yet attributed. Answering "where are we"
means reading four files. The obvious command is
`decomp-workbench campaign status` with a one-screen summary and `--verbose`
for per-region detail.

**Why it is not shipped.** `campaign status` already exists and answers a
different question well: it reports a *manifest* — a set of source variants
compiled, cached, ranked, and recorded through `campaign run`. Its unit is a
compiled candidate, and its state is a ledger it wrote itself.

The campaign that asked for this never used a manifest. Its artifacts are
files a human promoted, its floor came from an oracle sweep in another
directory, and its residue is now a `--by-region` run against a source path
nothing records. Making `campaign status` answer it means introducing a second
notion of "campaign" — a registry of tracked artifacts with provenance —
alongside the manifest, and deciding which one the existing command name
belongs to.

That is a schema decision with a compatibility cost, and there is exactly one
campaign's evidence for the shape it should take. Two would be enough. Until
then the honest position is that the four numbers exist and are each one
command away:

The artifact's score, its residue by region, and the oracle floor:

```sh
decomp-workbench score TARGET.o ARTIFACT.o
decomp-workbench compare TARGET.o ARTIFACT.o --by-region SRC.c
decomp-workbench oracle status
```

**Settled, by refusing the registry.** Shipped as
[`campaign survey`](campaigns.md#survey-a-campaign-directory-that-never-had-a-manifest).
`campaign status` keeps the manifest and the command name; the directory
reading is a second command, not a second meaning for the first.

Both open questions dissolve once nothing is persisted. *Is an artifact's
identity its object hash or its source path?* Neither is fixed: a survey is a
reading of the directory as it is right now — a path, and its content hash
taken at read time — so there is no stored identity to be wrong about. *Is
"unattributed" a property of the residue or of the campaign's own records?* Of
the residue, necessarily, because there are no records. And the schema whose
compatibility cost needed a second campaign's evidence does not exist: the
survey interprets only documents the workbench already defines (findings logs
and their sidecars, sweep manifests, instrument-gate stamps, `campaign run`
manifests) and counts everything else. A second campaign can extend the reader
without breaking anything, which is exactly what a registry could not have
promised.

The one thing it refuses to do is guess which artifact is the base. It names
the newest source and object it found, says they may or may not be the base,
and prints the command that would measure them.

### An instrument build should not be able to return an ungated binary

**The gap.** One campaign built roughly twelve instrumented compilers in
per-stage directories, each re-deriving the same patch/build/gate ritual. The
gate — *with the instrumentation disabled, the built object must be
byte-identical to stock* — is the single most important habit in the whole
practice, and it is enforced nowhere. An ungated instrument attributes
decisions to the wrong pass, which is strictly worse than having no instrument,
and the failure is silent.

The shape is `decomp-workbench instrument build --spec FILE`: apply a
declarative patch spec to a recompiled compiler source tree, build it, run the
identity gate, and **refuse to return an unvalidated binary**. The refusal is
the product; everything else is convenience.

**Why it is not shipped.** The gate is not the hard part — `fidelity` already
expresses it, and the existing `instrument uopt` profiles are already
hash-pinned and gated. The hard part is the middle step. Building the compiler
means invoking the user's build system, and this package will not run
user-supplied compiler commands through a shell, for reasons that have not
changed. Every alternative (a required build-command template, a container, a
declarative build description) either reintroduces the shell or constrains the
recomp trees this can serve to the one it was written against.

There is also a scope question the campaign's own roster raises. Its twelve
instruments patched four different passes with four different record
grammars. A spec format that covers all four is close to "arbitrary source
patch plus arbitrary log format", at which point the tool is a build wrapper
whose only real contribution is the gate.

**Shipped: the gate alone, and its record.**
[`instrument gate`](compiler-instrumentation.md#record-steps-4-and-5-do-not-remember-them)
takes two objects somebody else built and states whether the instrument is
trustworthy — and writes a stamp, because the campaign that asked for this ran
the check by hand every time and left no record that it had. `--verify` re-runs
the comparison rather than re-reading the record, and reports `STALE` when
either object has moved.

Both open questions are answered by that scope, not deferred by it. The
**build-invocation boundary** stays where it was: the package does not build
compilers, so the build half remains campaign-local, naming one compiler tree
and one patch grammar. The **grammar scope** question disappears, because the
gate compares objects rather than logs — one command covers all four
instrumented passes, and each pass keeps its own record reader.

## Campaign migration notes

Campaign-local scripts that the workbench has since absorbed. These are notes
for the campaigns, not work items here; this repository does not edit campaign
files.

- `ge007-object-interaction`: `p3f/win.py`, `p3d/sites.py`, `p3e/fsites.py`,
  and `p3e/fring.py` each scrape `objdump` to print a named row range of two
  builds side by side, each with its own row numbering. `window --json` (and
  `window-dumps` for retained text) does this on the aligner that produces
  `aligned_row`, so migrating them makes the numbers in those scripts the
  numbers a dossier quotes.
- `ge007-object-interaction`: `p3h/tools/webrows.py` is the perturbation join
  now shipped as `force-rows`. The workbench version aligns the two builds
  instead of zipping them by position and joins the target through the same
  alignment `compare` publishes, so it stays correct when a force changes the
  instruction count. The build half stays campaign-local, as it must: it names
  one instrumented compiler and one force grammar extension.

## Original proposals (now implemented unless noted)

### Original-pass differential adapter

Add a reusable adapter that runs a user-supplied original IRIX pass under
QEMU/Docker and compares it with a static recompilation at each retained pass
boundary. Requirements:

- no compiler binaries or generated proprietary sources in this repository;
- explicit mounts and path rebasing for host temporary directories;
- a project-visible temporary directory on macOS, where Docker cannot normally
  access per-user `/var/folders` paths;
- hashes for the original pass, static pass, input, output, and downstream
  assembler;
- disabled-instrumentation and unedited-replay fidelity gates.

### Compiler-variant fingerprinting

Build a redistributable microcase suite that distinguishes compiler/pass
variants by control-flow lowering, stack-home selection, scheduling, and
register-allocation tie behavior. A project should be able to identify a
toolchain variant before running a large source campaign.

Add a cross-ROM fingerprint mode for projects with multiple revisions or
regions. Given equivalent symbol ranges, it should compare instruction
sequences after relocation normalization, identify byte-identical compiler
idioms, and distinguish stable source/compiler lineage from a one-ROM anomaly.
Reports must record ROM and extraction hashes without redistributing ROM data.

### Stable allocator web fingerprints

Numeric web IDs are useful within one compiler input but are not durable across
source changes. Derive a fingerprint from data type, virtual stack home,
def/use basic blocks, expression ancestry, and interference neighborhood.
Reports should map equivalent webs between candidates and explain added or
removed interference edges.

The first comparison mode should align decision streams by semantic provenance
(`dtype`, virtual stack home, table/chain identity, and basic-block context),
not numeric web ID. Folded definitions can renumber every later web while
changing only one real lifetime, making a raw line diff actively misleading.

The report should also identify the already-colored neighbor responsible for
each forbidden color and show its semantic counterpart in the other
candidate. Late-stage campaigns need an answer such as “color 1 became
unavailable because this lifetime now intersects that carrier,” not just two
large neighbor lists.

### Stack-home provenance

Classify each spill home as a named source local, compiler temporary, outgoing
argument home, or allocator-created spill. Expose the virtual offset before
final frame layout and show which source/IR change moved a value between those
classes. This is essential when one source form has the target registers but a
named-local home, while another has the correct anonymous-temporary home.

Provide an offset-centric report that maps every use of a selected final stack
offset back to its web and source/IR owner. Also compare two candidates by
stack-home ownership so a campaign can answer which value displaced a local by
one slot, rather than only reporting that `N(sp)` changed.

### Source and listing correlation

Improve IR-to-source correlation beyond compiler line fields, which can be
coarse or synthetic after preprocessing. Retain preprocessor line markers and
map allocator webs to source expressions and late-pass listing locations.

### Pass-listing portability

Add preflight checks and normalization for host-specific listing paths,
temporary-file visibility, and C-library formatting differences such as
`ecvt`/`fcvt`. An unedited listing replay must remain the mandatory calibration
cell.

### Campaign experiment manifests

Accept a sidecar manifest describing each transformation family and its
parameters. Summaries should report basin transitions and keep the top
candidate per structural signature without embedding unbounded detail.

Ship a project-neutral library of source-equivalent late-stage mutations:
repeated folded conditions, neutral integer operations, nested assignments,
statement grouping, equivalent pointer arithmetic, declaration-order
permutations, and lifetime-carrier placements. These patterns repeatedly
matter in mature IDO decomps. The campaign runner should optionally stop or
deprioritize redundant experiments as compiled function-byte basins arrive,
avoiding unnecessary work after a generator begins producing repeated
outcomes.

Include adjacent repeated indexed empty conditions as a first-class mutation,
with configurable expression, repetition count, and placement anchor. Live IDO
campaigns show that two otherwise code-free indexed conditions can perturb
allocator priorities and colors even when the final instruction stream contains
no trace of the conditions.

Include emission-free comma-expression conditions such as
`if ((carrier, live_value)) {}` at configurable definition/use boundaries.
These are not interchangeable with a plain `if (live_value) {}` in IDO's
optimizer: the comma form can change expression ancestry and allocator web
priority while emitting no instructions. Mutation manifests must retain the
carrier, live value, repetition count, and placement so the causal dimension is
visible after object deduplication.

Add constraint-decomposition scoring for late-stage crossings. Users should be
able to select an instruction region that must remain byte-exact while ranking
the rest of the function separately. Summaries should call out candidates such
as “selected region exact; only one stack-home family regressed” and list the
instruction indices sharing that residual operand. A single global word count
hides this useful structure.

### Register-web swap diagnostics

When two candidates have identical opcode schedules and their remaining
differences form a consistent register permutation, report the permutation and
the affected instruction indices. If compiler allocator instrumentation is
available, map the registers back to stable web fingerprints and optionally
emit a diagnostic force specification for an oracle build.

The force build is evidence only, never a source match. Its report should state
whether the permutation makes the function exact and which source webs must be
re-prioritized. This turns a late-stage register-color residual into a bounded
source mutation problem instead of another broad structural search.

### Linked-address relocation aliases

Classify relocation aliases that resolve to the same linked address. This
occurs when a loop endpoint can be spelled either as `array + count` or as the
next adjacent symbol: a ROM-derived target may choose the successor symbol
while the compiler object retains the base symbol plus an addend. Reports
should identify these as resolved-address-equivalent aliases, list both
spellings, and recommend the project link/ROM check instead of prompting source
changes. External score importers should keep this class separate from genuine
instruction mismatches.

### Deeper late-pass controls

Extend opt-in UGEN/AS1 diagnostics to cover expression evaluation order,
temporary-register carrier selection, and schedule decisions. Controls remain
experimental evidence and must never be presented as source-level matches.

The first scheduler profile should emit a stable, documented record for each
selected node: procedure, block, cycle, opcode, source line, ready-set size,
and the tie-break that won. Calibrate it with an instrumentation-off binary
identity gate and an unedited as0/as1 replay. Do not productize the current
unlabeled pointer dump: a trace whose fields require reverse-engineering every
run is not a user interface.
