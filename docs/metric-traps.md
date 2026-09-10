# Metric traps

**Read this if:** a score improved, a lever's price looked stable, or a
catalogue told you a site was already priced — and you are about to act on
that number without re-deriving it. Every trap below was a **correct reading
of the wrong quantity**, not a bug. The scorer, the catalogue, and the census
all did exactly what they were built to do; the mistake was trusting what
they did not measure. The first six each cost a real stage of real work in
the GE007 `object_interaction` campaign (54 → 0 differing words); the seventh
comes from one level up, where the number being misread is the matching gate
itself; the eighth comes from the SSB64 `cef4c` endgame, where the number
being misread is the one this project tells you to rank on.

Each trap about the compiler links to its entry in
[Compiler laws: IDO 5.3](compiler-laws/ido-5.3.md), which carries the formal
statement, the receipt, and the falsification history. This page is the
narrative version — what the mistake felt like from the inside, so you
recognize it before you repeat it. Trap 7 is not about the compiler at all —
it is about the linker — and links to its own page instead. Trap 8 is about
the comparator, and unlike the rest it now carries its own correction: the
command prints the counter-evidence beside the misleading number.

## Trap 1: a ring-quotiented score can hide a 100x-worse object

**The trap:** a band-relative score ("`free`", a count reported after
factoring out a global ring-coset rotation) reads like ordinary progress. It
is not the same axis as the positional word score that actually decides
whether a candidate is better.

**The incident.** One stage reported a construct as "worth 10" — a
re-deal that appeared to close ten rows of a known residual. The object
behind that number, re-scored on the positional metric, was **1045 words**
off. The whole family the "worth 10" figure was drawn from carried a hidden
global ring-coset shift that the band scorer canceled out before printing
its headline number, and nothing about the printed number said so.

**Why it happened.** The ring-phase state is a group, and a scorer that
reports distance modulo that group's rotation is answering a real, useful
question ("how far is this from *some* rotation of the target") — just not
the question "is this candidate better." The two coincide only when the
candidate's ring phase already agrees with the target's on every axis, and
nothing forces that to be checked before the headline number is trusted.

**The rule:** never read a `free`/band count as a positional score. Confirm
every ring-phase coordinate is independently at identity first; if even one
is not, the band number is measuring the wrong thing.

See [L46](compiler-laws/ido-5.3.md#l46-ring-quotiented-scores-are-not-positional-scores).

## Trap 2: a four-coordinate score is a lossy projection of a seven-dimensional state

**The trap:** a scorer built to track "the ring phase" as a small, fixed
number of coordinates can report identity — full agreement — while two
different regions of the function individually disagree with the target in
ways that happen to cancel in the coarse read.

**The incident.** The actual ring-phase state of one function's temp
rotation needed **seven independent counters**, not four, because one region
that a four-coordinate model treated as a single phase actually decomposed
into three finer sub-phases. A construct that a prior stage had proven
"byte-exact if and only if" one whole-function coordinate took a specific
value — stated as a fixed, function-wide law — broke on the very next base,
because the real state had degrees of freedom that coordinate could not
see. A candidate scoring the *ideal* value on every one of the four coarse
coordinates still missed by over a thousand positional words, purely on the
phase axes the coarse model could not resolve.

**Why it happened.** Building a four-slot model was not wrong when it was
built — it explained everything measured at the time. It became wrong
silently, the moment a new region entered the picture with its own
independent phase, because nothing about a four-coordinate scorer signals
that a fifth degree of freedom exists.

**The rule:** treat any fixed-width phase or coordinate model as a
hypothesis about dimensionality, not a fact about the compiler. When a
"should be identity" candidate still scores badly, suspect an unmodeled
coordinate before suspecting the construct.

See [L41](compiler-laws/ido-5.3.md#l41-the-temp-ring-phase-is-a-seven-slot-vector-not-four-coordinates).

## Trap 3: a catalogue keyed by site alone hides which carrier was measured

**The trap:** "this source site is worth N rows" reads like a fact about the
line of code. It is often a fact about the line of code **and** the specific
local variable used to test it — and reusing the number against a different
variable at the same site silently fails to reproduce.

**The incident.** At one site, one construct shape produced a cheap delta
class **only** when the carrier was one of the two earliest-declared
candidate locals available; every other same-typed local at the same site,
in the same construct, produced a more expensive class. A prior catalogue
had recorded the site's price from measuring just one carrier and carried
that number forward through at least two later stages' work — including a
census that had *thinned its own candidate list* on the strength of a price
that only ever held for one specific carrier.

**Why it happened.** "The delta belongs to the site" is true often enough to
feel like a law, and cheaper to believe than to re-derive per carrier. It
happened to be checked against a small number of naturally-similar carriers
early on, which hid the dependency until a structurally different carrier
was finally tried.

**The rule:** a site's price is not fully specified until the carrier is
named. When reusing a catalogued number against a new carrier — even one
that looks interchangeable — re-measure rather than assume.

See [L44](compiler-laws/ido-5.3.md#l44-a-constructs-delta-class-depends-on-the-carrier-not-only-the-site).

## Trap 4: a lever's price is a property of the base, not of the edit

**The trap:** "this construct costs N rows" reads like a property of the
construct. It is a property of the construct **applied to the object it
was measured against**, and that price can move — including to zero, or to
negative — the moment something upstream of it changes.

**The incident.** One three-line edit was measured at **+1015** positional
rows against one base. After an unrelated fix changed that base's ring
phase, the identical edit, unmodified, was measured at **free, and −4**
against the next base. Nothing about the edit changed between the two
measurements.

**The rule:** re-measure every named lever on the current base before
spending a build planning around its old price. A price that was correct
when it was recorded is not evidence about what it costs now.

See [L47](compiler-laws/ido-5.3.md#l47-a-levers-price-is-a-property-of-the-base--re-measure-the-whole-set).

## Trap 5: an inherited set of levers is never re-tested against zero

**The trap:** once several edits have each individually been justified and
adopted, the accumulated set feels validated — each piece earned its place.
Nobody re-asks whether the **set**, as a whole, is still buying anything on
the base it now sits on.

**The incident.** A later stage tried removing four previously-adopted
edits together, purely as a control — a null-hypothesis experiment nobody
had run because each edit had already been individually priced and
approved. All four turned out to be pure cost: an unrelated fix, adopted
later, had already supplied the effect all four were originally justified
by. A 128-point lattice sweeping every small combination of the four
(128 builds, well under two minutes) found the all-plain point — every one
of the four *removed* — strictly better than every combination that kept
any of them, by ten rows.

**Why it happened.** Each of the four edits was correctly priced *at the
time it was adopted*. Nothing about "correctly priced once" implies
"still buying anything" once the object around it has moved — see Trap 4.
The specific failure here is narrower than Trap 4: it is not re-measuring a
*single* lever, it is never subjecting an *entire inherited set* to a
removal experiment, because no single piece of it looks suspect on its own.

**The rule:** periodically re-price the whole accumulated lever set from
zero — build the base with each inherited edit removed, alone and in small
combinations — rather than only re-pricing edits you already suspect. A
lever's price can be its entire remaining benefit, and only a removal
experiment shows that.

See [L47](compiler-laws/ido-5.3.md#l47-a-levers-price-is-a-property-of-the-base--re-measure-the-whole-set).

## Trap 6: a statement can cost zero instructions and still be load-bearing

**The trap:** a disassembly-driven reconstruction implicitly assumes every
source statement in the original left a trace in the object. Most do. The
ones that do not are invisible to exactly the method used to find them.

**The incident.** A campaign's last residual — after every allocation
mechanism was understood and every disassembly-visible construct had been
tried — closed with a single statement that reads a local and discards its
value (`if (v != 0.0f);`), compiling to **zero instructions**, whose only
effect was reshaping the register allocator's carve of one web (see
[chargeB](p1-decision-arithmetic.md#chargeb--a-store-placement-charge-not-a-loop-charge)).
Eleven prior stages of disassembly-and-mechanism-driven work did not find
it, because there was nothing in the disassembly to find — the statement
left no bytes. It was found by an external oracle instead: a sibling game's
**independently matched** decompilation of the evolved version of the same
routine carries the identical discarded-read idiom, in the identical place,
three times in fifteen lines — proof the idiom is a real authoring pattern,
not a decompiler artifact invented to close a gap.

**The rule, stated as an operational test:** when a function is byte-exact
under a *forced* allocator decision (an oracle proves the target machine
code is reachable at all) but not under an unforced, stock compile, the gap
is not necessarily a wrong construct — it may be a **missing** one that
costs nothing to add. Look for a zero-footprint statement before looking for
a mis-spelled one. When a sibling, already-matched codebase exists for a
related routine, check it for exactly this shape before assuming the
decompiled source is otherwise complete.

See [L48](compiler-laws/ido-5.3.md#l48-zero-footprint-statements-can-be-load-bearing) and
[error eleven in the campaign postmortem](history/postmortem-2026-08-09-ge007.md#11-zero-footprint-discarded-read).

## Trap 7: byte-identity does not prove address provenance

**The trap:** a build that reproduces the ROM byte-for-byte reads like proof
that the source is right. It is proof that the *bytes* are right, at one
layout. "100% matched," a green CI gate, and a project's own retail verifier
all measure the same thing, and none of them measures where an address in the
image came from.

**The incident.** A one-line edit was injected into a finished, 100%-matched
N64 decompilation — a global pointer initialized from a raw address literal
instead of `&symbol`, with the address read out of the project's own build
map so that it was the correct value at that layout:

```c
SoundPlayer *gSoundPlayerPtr = &gSoundPlayer;               /* before */
SoundPlayer *gSoundPlayerPtr = (SoundPlayer *) 0x80110470;  /* after  */
```

Every existing gate passed. The bugged matching build was **byte-identical to
the retail cartridge** — CRCs good, the project's own `Verify: OK`, and an
independent `cmp` against the baserom. The bugged mod-mode build was
byte-identical to the clean one. Nothing in the ecosystem had a way to say
that this ROM now contained one address that would not survive an insertion,
because the community runs no shiftability check in CI at all: papermario,
zeldaret/oot and mk64 workflow files were fetched and grepped, zero hits.

Relink the same objects against a script with `0x10` inserted, and the truth
is one byte wide: the bugged shifted image differs from the clean shifted
image in exactly **seven bytes** — six of CRC recalculation, and one byte of
the stale pointer, `0x70` where it should read `0x80`. `shift rehearse`
reports `stale_confirmed=1` at ROM `0x0d29dc`, value `0x80110470`, and names
the symbol the word should have been: `gSoundPlayer`. Nothing else fires.
Revert the line, rebuild the pair, and the same command says
`stale_confirmed=0, findings=0`.

The same project's own 2021 shift-hardening carries the harder version. Four
of its fixes did nothing but turn a raw hex offset into `%lo(symbol)` — code
that assembled to **byte-identical output before the shift**, because the
literal happened to equal that symbol's low half in that one layout. There
is no address-shaped word to scan for: the effective address is only ever
formed at run time by combining a correctly relocated `lui` with a frozen
16-bit offset, and in a linked image that offset is indistinguishable from a
legitimate struct-member displacement. No single-build check, static or
dynamic, reaches that class. A differential relink does.

And one class reaches past both. The same game checksums four of its own
functions at run time, with a post-link build step recomputing each byte-sum
from the map. In 2021 one audio function was left off that step's allowlist;
under a shift its bytes changed, its frozen checksum did not, the game's own
self-check failed, and the bug was filed as "cursed audio." That word holds a
byte-sum, not an address — neither a static address scan nor a generic
stale-word detector has anything to key off. It needs its own stated rule:
*if a protected function's body changed, its checksum word must have changed
too*.

**Why it happened.** A linked N64 ROM keeps no relocations. A literal
`0x80123456` and a linker-resolved symbol that lives at `0x80123456` produce
the same four bytes, so the finished image contains no evidence of which one
was written. Byte identity is a point measurement, and provenance is only
visible in a neighborhood: you have to move the layout and see which values
move with it. Nothing about a byte-for-byte pass announces that it was never
asked the question.

**The rule:** never read byte identity — a match score, a green gate, a
retail verifier — as a claim about where an address came from. It is a claim
about one layout. When what you need is "every address in this image is
explained by a reference," that is a different measurement, and it costs a
relink: build the same objects twice against scripts that differ by an
inserted pad, at two different deltas, and require every changed word to be
explained and every unmoved address-shaped word to be judged.

See [Shiftability](shiftability.md) for the four commands that make that
measurement, the tier rules behind their findings, and the boundaries they
refuse to cross, and
[The shiftability campaign](shiftability-campaign.md) for the order to run
them in on a project that has never been shifted.

## Trap 8: `words` over-charges a moved block by three orders of magnitude

**The trap:** `words` is the metric this project tells you to rank on, and it
is the right one — *for a candidate the compiler emitted at the target's
shape*. It is a **positional** count: candidate row *i* against target row
*i*. Move a block of code and every row between its old home and its new one
is compared against a stranger, so a candidate whose real edit script is one
relocated block reports a four-figure residual and reads as garbage.

**The incident.** In the SSB64 `cef4c` endgame, the p2 layout family produced
a candidate reporting **1,791 differing words**. It was ranked below several
strictly worse candidates and nearly abandoned. Its actual difference was a
**single 29-row block relocated** — one edit, in a family whose whole purpose
was to find that block's correct position. The same postmortem records the
mirror-image failure on the o3and family, where `opcodes` conflated a
schedule change with an allocation change and sent two waves at the wrong
layer.

**Why it happened.** A positional metric has no model of correspondence. It
cannot distinguish "these two objects disagree about 1,791 instructions" from
"these two objects agree about all of them and disagree about where one run of
29 sits." Both readings produce the same number, and the number is the one on
the summary line.

**The rule:** on `structure-mismatch` and `schedule-mismatch` — the two
verdicts a permutation lands on — read the `layout` block before `words`.
`compare` now computes it for you: it runs the shift-tolerant aligner
automatically on those verdicts and prints the edit script, the moved-block
count and rows, and `rows_away` beside the positional count, in text and under
`layout` in `--json`. When `moved_block_count` is non-zero, the guidance line
leads with it, because the next experiment is a block-order question and not a
1,791-word one. Run [`align`](from-verdict-to-edit.md) for the full script.

Nothing here retires `words`. It stays the comparable number across a
candidate set (Trap 1, and
[L18](compiler-laws/ido-5.3.md#l18-positional-words-are-the-honest-metric));
the fix is that the reading now arrives with its own correction attached
rather than three screens away in a command nobody thought to run.

**Corollary — a scalar is the wrong fitness function for a layout search.**
The number that actually converged that endgame was not a scalar at all: it
was a six-column *heal signature* over rows chosen because they discriminate
between the mechanisms in play (`compare --watch-rows r49=49,cx2=1620,…`,
and the same column in `rank` and `sweep build`). `.` healed, `X` broken, one
column per watched row. It is not a distance and does not pretend to be one,
which is exactly why it does not average away the thing you are looking for.

See
[the cef4c postmortem](history/postmortem-2026-08-24-cef4c-exact.md), "What
failed or was missing" item 5, for both halves of this trap in their original
form. The objects are not redistributable and are not in this repository.

## Trap 9: splat's listing carries the *linked* word; the assembled object does not

**The trap:** a fast scorer reads the target's words out of the disassembly
listing instead of assembling it. The listing annotates each line with the
word as it sits **in the ROM** -- fully linked, every address resolved. The
object you get by assembling that same listing is **unlinked**: the address
fields are zero and the information lives in relocations instead. Comparing an
unlinked candidate against linked target words reports differences at every
site where the linker supplied a value, and none of them are real.

**The incident.** A lane building a direct-`cc` iteration loop scored its
target this way and carried two phantom rows the whole time: a link-time
resolved internal call, and an import whose addend is stored in the image.
Both differ by construction, neither survives linking. Switching to the
assembled target object made its numbers agree exactly with the project
comparator, base and edit alike.

**Why it survives review.** The count is *close*. Two phantom rows against a
few hundred real ones looks like ordinary noise, not a methodology error, and
every intermediate the lane measures is wrong by the same small constant --
so the edit-to-edit *deltas* that drive the search stay correct and the loop
feels trustworthy. It only shows up when the absolute number is compared with
a tool that assembles.

**Distinct from the relocation-masking question**, which is about a word
carrying a relocation on one side only and is handled by masking the union of
both sides' relocation fields. This trap is upstream of that: it is about
having read the wrong bytes for the target in the first place, and no masking
policy repairs it.

**The rule:** assemble the listing and read the object. If a scorer's absolute
count disagrees with the project's comparator while its deltas agree, suspect
this before suspecting the comparator.

## Trap 10: a stale candidate object reads as a plausible residual

**The trap:** a scorer compares against a candidate object left over from an
earlier state of the source. Nothing in the resulting diff says so. It is not
noise and it does not look broken — it looks like a large, coherent, workable
residual, and a lane will happily plan against it.

**The incident.** A handoff recorded that a specific arithmetic regrouping made
rows 19-59 exact and moved a function's first mismatch from `+0x4C` to `+0xF0`.
Re-measured against a freshly compiled object: **107 masked words, first
mismatch still `+0x4C`**, and three other groupings of the same shift all
within one word of each other. The filed claim does not reproduce, and the
function's recorded "next lever" rested entirely on it. The stale reading had
been 430 words at size delta `+48` against a true 36 at delta `0`.

**The tell is the size delta.** A stale object is usually stale because the
source changed shape, so its instruction count disagrees with the target's in a
way the current source does not. A residual whose delta is large while the
current source is known to be extent-exact is stale until proven otherwise.
Check the delta before reading the word count, always.

**The structural fix** is to recompile rather than to find the object: a scorer
that owns its own compile cannot serve a stale one. `score_symbol.py` in the
Mickey host does exactly that, and it is why its numbers agree with the ranking
by construction rather than by review.

## Trap 12: the positional score can prefer the structurally worse spelling

**The trap:** two spellings are compared on the positional differing-word count
and the better number is adopted. On a function still far from matching, that
number is dominated by *displacement* — one instruction emitted in a different
place makes every word after it differ, although the two streams are the same
instructions. A spelling that is structurally closer can therefore score worse.

**The incident.** On a 14,456-byte body, one exit-test spelling measures 894
positional words and the natural alternative measures 988. Under
shape-tolerant alignment, with register names erased, the ranking inverts: the
*natural* form gives 2,905 byte-exact rows against 2,872, and 633 register-only
rows against 692. It loses only positionally, and only because of a single
register eviction that displaces the tail.

**Why it matters more the further you are from a match.** Near zero the two
metrics agree, because there is no displacement left to amplify. At several
hundred words they routinely disagree, and the positional number is the one
that misleads: it rewards keeping instructions in place over getting them
right, which is exactly backwards while the residual is still structural.

**The rule:** on a residual above roughly a hundred words, read the
shape-tolerant counts beside the positional one before adopting a spelling.
Adopt on the positional score only once displacement is closed. Record both
when you file a plateau, because the next lane inherits whichever you wrote
down.

**A second receipt, independent and much smaller.** On a 1,080-byte overlay
function, marking four aggregate members `volatile` and dropping a carrier
scores **37 against the standing 39 — and is further from the target**: it
emits five loads where the target emits three, and it fills both r4300
multiply-hazard `nop` slots that the target leaves open. So the trap is not
only a large-residual phenomenon. Any edit that moves the *schedule* can buy
positional words while losing instructions, because a filled hazard slot is a
word that now agrees by accident. Count instructions, not just words, whenever
a candidate changes scheduling.

## See also

- [Compiler laws: IDO 5.3](compiler-laws/ido-5.3.md) — the formal law entries
  behind every trap above.
- [The p1 decision arithmetic](p1-decision-arithmetic.md) — the formula
  several of these traps were made while reasoning about.
- [Postmortem: GE007 `object_interaction`](history/postmortem-2026-08-09-ge007.md) —
  the full campaign the first six traps are drawn from.
- [Hotwash: the cef4c exact-match endgame](history/postmortem-2026-08-24-cef4c-exact.md) —
  where Trap 8 was paid for, and where the heal-signature fitness function
  that answers its corollary was invented.
- [From verdict to edit](from-verdict-to-edit.md) — `align`, the full
  shift-tolerant edit script Trap 8's summary is drawn from.
- [Shiftability](shiftability.md) — the commands Trap 7 routes to, and the
  worked example of a matched ROM carrying an address bug.
- [L18, positional words are the honest metric](compiler-laws/ido-5.3.md#l18-positional-words-are-the-honest-metric) and
  [L19, partial closure is not monotone](compiler-laws/ido-5.3.md#l19-partial-closure-is-not-monotone) —
  the two measurement laws this page's traps extend.

## Trap 11: a forced-colour receipt is numbered against the variant it ran on

**The trap:** a `CDX_FORCE` result is cited as "forcing web N reaches score S",
and the web number is carried forward into a later brief. Web numbers are
assigned per compilation. A receipt taken against a candidate that carried one
extra carrier numbers its webs differently from the candidate you are holding,
so the number names a different web, and the score it promises is a score the
current source cannot reach.

**The incident.** A receipt recorded "forcing web 105 takes 113 to 99" and was
put into the next lane's brief as its starting point. Re-derived on the current
source: the web is **104**, not 105 — the original ran against a variant
carrying an extra carrier — and the colouring decision is worth **14** words,
not the 113 the brief implied. A full sweep, 57 webs across c1–c8 with 258
forces applied, established both. The function then went 113 to 22 on entirely
different levers.

**Why it survives review.** The receipt is *true of the run that produced it*
and reproduces exactly if you rebuild that variant, so it does not read as
stale. Nothing about a bare web number says which source it was numbered
against.

**The rule:** cite a forced-colour receipt with the source it was taken on, and
re-derive the web number before spending a lane on it. A force is a causal
probe -- it identifies a decision worth explaining -- and its *number* is an
artifact of one compilation, not a property of the function.

