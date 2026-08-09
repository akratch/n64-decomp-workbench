# Shared notes

`decomp-workbench note` records findings into a shared log that several people
or agents write at once, with one guarantee:

> A note, once written, cannot be lost by a concurrent writer.

## Why this exists

The usual arrangement is a Markdown findings file plus a rule: *append only,
re-read the file first*. That rule is a request, not a mechanism, and it fails
in the ordinary case. Two writers both read the file, both append their own
entry to their own copy, and both write the whole file back. The second write
wins. No error is raised, both writers correctly report success, and one entry
is gone.

One campaign lost about twenty-six consecutive entries this way across eight
stages before anyone noticed, because every stage that lost work had honestly
reported doing it.

`flock` alone does not fix this. It serializes the two read/modify/write
sequences without preventing the second from writing back a copy of the file
that predates the first. The only durable answer is to stop putting the note in
the shared file at the moment it is written.

## How it works

`note add` never opens the log for writing. It writes the note to its own new
file under a sidecar directory beside the log:

```
WORKBENCH-IMPROVEMENTS.md
WORKBENCH-IMPROVEMENTS.md.notes.d/
    20260808T100900-WB-54-7dd45954.json
    20260808T101142-WB-55-1c0ef233.json
    merged/
```

The name carries a random token and the file is created with `O_EXCL`, so two
`note add` calls in the same second with the same identifier both succeed. A
whole-file rewrite of the log cannot destroy a file it does not touch.

The sidecar directory is derived from the log's path, never configured: the
guarantee holds only while every writer of one log agrees on one sidecar, and
agreement by convention is what failed the first time.

## Reading is not claiming

The mechanism above makes a note impossible to lose. It does nothing about the
other collision: two agents filing *different findings under the same number*.
One campaign did that three times in a single night, and every agent involved
had honestly read the log first — because between the read and the write,
somebody else takes the number, and both filings are correct about a file that
no longer says what they read.

So the claim has to be a write, and it has to be exclusive:

```sh
decomp-workbench note reserve --log WORKBENCH-IMPROVEMENTS.md \
    --prefix WB --count 3 --author W4 --purpose "sweep defects"
```

```text
reserved: WB-122, WB-123, WB-124
```

Each identifier gets its own file under `…notes.d/reserved/`, created with
`O_EXCL`. Two agents reserving in the same instant cannot both create
`WB-122.json`: one create succeeds, the other raises, and the loser silently
takes `WB-123`. Scanning for the highest number in use — across the log's own
entries, the pending notes, the merged notes, and the existing reservations —
is only an optimisation. The correctness is entirely in the exclusive create,
because every scheme whose last step is a read has already lost the race by the
time it writes.

If a *second* document in the same campaign also mints numbers in this series
— an audit that renumbered a pile of colliding filings into a backlog, say —
name it, or the scan will hand out a number that has already been published:

```sh
decomp-workbench note reserve --log FINDINGS.md --also-log WB-BACKLOG.md \
    --prefix WB --count 3
```

That is not hypothetical: it is what happened the first time this command was
run for real.

`note add` then refuses an identifier somebody else reserved:

```text
error: WB-122 is reserved by W4 (2026-08-09T09:37:13Z): sweep defects.
Claim your own with `note reserve --prefix WB`, pass --author to file under
your own reservation, or --force if you really mean to write under this one.
```

Pass `--author` matching the reservation to file under your own claim. Nothing
changes for an unreserved identifier, so a log nobody reserves against behaves
exactly as before.

## The filing workflow

1. **`note reserve`** — claim your numbers before you write anything. Do it
   once, at the start, for as many as you expect to file; an unused reservation
   costs nothing and is visible to everyone else.
2. **`note add`** — one call per finding, under a number you hold.
3. **`note list`** — check what is pending, and what is still claimed but
   unfiled.
4. **`note merge`** — fold the pending notes into the log.

Steps 1 and 4 are the ones that get skipped, and they are the two that make the
other two safe.

## The commands

```sh
decomp-workbench note add --log WORKBENCH-IMPROVEMENTS.md \
    --id WB-54 --title "a shared log has no safe append path" \
    --status LOGGED --body-file finding.md
```

`add` prints the file it wrote, so the report is checkable rather than
trusted. `--body -` and `--body-file -` read the body from standard input.

```sh
decomp-workbench note list --log WORKBENCH-IMPROVEMENTS.md
```

`list` renders the merged view: the entries the log document itself carries,
the identifiers claimed but not yet filed under, then the sidecar notes not yet
folded in. Pending notes are visible, so the sidecar is a staging area rather
than a directory that quietly fills up. `--verbose` adds full titles and pending
bodies; `--json` emits `decomp-workbench-note-list-v1`, which carries
`reserved` and `unfiled_reservations` beside `pending`.

```sh
decomp-workbench note merge --log WORKBENCH-IMPROVEMENTS.md
```

`merge` is the only command that writes the log, and it appends under an
exclusive lock rather than rewriting. Merged note files are moved to
`…notes.d/merged/` instead of being deleted, so the note survives even if the
merge output is later clobbered by exactly the kind of writer this mechanism
exists to defend against.

`--dry-run` reports what would be appended without touching the log.

## Reading the log

`note list` parses the log document shallowly on purpose: a heading whose first
token looks like an identifier (`## WB-54 — title`) and the first `**Status:**`
line beneath it. A findings log is prose written by humans, and a parser that
demanded more structure than they actually use would report an empty log and be
believed.

A pending note whose identifier is already in the log is reported as a
duplicate, not resolved. Deciding which text wins is an editorial call.
