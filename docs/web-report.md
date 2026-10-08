# Why each web got its colour: `trace web-report`

`trace cascade` follows one allocator site through every round, and `trace
growth` reads one split. `trace web-report` answers the question that comes
before either, for every decision of one procedure at once: *which references
bought this web its priority, which registers was it already denied before
any neighbour was coloured, and if it split, which block refused to join the
piece?*

It reads a log. It never compiles.

```sh
decomp-workbench trace web-report examples/traces/web-report.log --lines 7-20 \
  --source examples/fixtures/web-report-mini.c \
  --local -28=col --local -32=index --param 0=grid --web 3
```

```text
web 3 p1  (col & 7)  [expression temporary]   decision 1 of 5
  priority save 300  nocs 2  totalsave 600  bestcost 0  numintf 4  regsleft 12
  color -> s0 (c14)   forced: dec=-2 color=-2  (-2 never forced, -1 accepted)
  references: gross 600 - chargeA 0 - chargeB 0 = net 600  (/ nocs 2 = save 300)
    bb3    x5      uses 1 defs 0 -> 500   lines 15,16   naming col: 16
    bb4    x1      uses 1 defs 0 -> 100   lines 18   naming col: 18
  forbidden seed 0x54000000  at decision 0x54010000  (neighbours add s1)
    v0 from bb4 <- web 9 $v0
    a0 from bb4 <- col held over its range
    a2 from bb1 <- no web (a constant or address bound to the register)
```

The log and the C beside it are synthetic and hand-written; the numbers are
illustrative.

## The four readings

**Identity.** The web's value rendered over the procedure's own names. Names
are optional: `--local OFFSET=NAME` and `--param OFFSET=NAME` take the frame
offsets the records print (cfe assigns them before optimisation, so they are
the offsets a `-g` compile's symbol table gives). Without them a local prints
as `auto[-28]`. The line also gives `save`, `nocs`, `totalsave`, `bestcost`,
the decision, the colour it resolved to (from the *colour* record, not the
decision's pre-force `bestcolor`), and the `forced` state of both records.

**References.** One row per occurrence block: loop weight, uses, defs, term,
the source lines the block spans, and -- with `--source` -- which of those
lines name the web's variables. The decision record prints only a total, and
this breakdown says which reference to add or remove to move it. The reader
checks that the terms sum to `gross`, that `net = gross - chargeA - chargeB`,
and that `net` equals the decision's `totalsave`; a failed check prints
`CHECK:` and the records win.

**The forbidden seed.** Per block, the mask the block folded into the web's
forbidden set before any neighbour was coloured, with the web's *own* colour
bit removed. Each bit names its source: a web pinned in that block, a value
held in a register over a range that includes it, or -- when no web owns it --
a register bound outside any web, such as a constant or address argument.
Bits in the decision's `forbidden0` beyond the seed are neighbours' colours
(`neighbours add`).

**Splits.** For a web the pass split, every growth test of every piece,
re-checked against the split growth rule (IDO 5.3
[L161](compiler-laws/ido-5.3.md): accept iff `new < left_before` and
`2*left_after >= numintf + new`). The first refused block is named, and a
verdict the rule does not explain is flagged `(rule disagrees: read the
record)` instead of being believed.

## Options

| Option | Effect |
|---|---|
| `--proc N` | the procedure ordinal |
| `--lines LO-HI` | choose the procedure whose first source line falls in this span (the function's definition) |
| `--web N` | only this web (repeatable) |
| `--block BB` | only rows for this block, plus the block's weight, lines and pinned registers |
| `--source FILE` | name the lines that mention each web |
| `--local OFFSET=NAME`, `--param OFFSET=NAME` | name frame offsets |
| `--json` | `decomp-workbench-web-report-v1` |

Without `--proc` or `--lines`, a log with one procedure is read; a log with
several exits 2 and lists them.

## Dependency, stated plainly

The decision, colour, `webblocks` and growth rows come from the shipped
`instrument-uopt` globalcolor profile. Seven records do **not**: `bbline`,
`bbpin`, `rangepin`, `saveocc`, `savedetail`, `webexpr` and `forbidseed` come
from a campaign-local `uopt.c` patch switched on by `CDX_WEBREPORT=1`. The
grammar this command reads is `decomp_workbench.web_report.RECORD_GRAMMAR`, one
line per record, so a differently-patched instrument can check compatibility
without running anything. A log that carries none of the seven is refused by
name (exit 2) rather than printed as an empty report.

The patch is a tracing patch: with `CDX_WEBREPORT` unset its object, stderr
and every other record must be byte-identical to the profile without it, and
with it set the instrumented `.text` must equal a stock compile's. Check both
before reading a report -- [`instrument gate`](compiler-instrumentation.md)
does the second -- because a record from a compiler that is not producing the
stock object is evidence about a different program.

`lr` values are invocation-local pointers, used only as a join key inside one
log. Web numbers are not stable across source edits; to follow one value
through an edit, use its expression and its lines, as
[`sweep levers`](lever-sweep.md) does.
