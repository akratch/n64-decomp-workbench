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

## The three commands

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
then the sidecar notes not yet folded in. Pending notes are visible, so the
sidecar is a staging area rather than a directory that quietly fills up.
`--verbose` adds full titles and pending bodies; `--json` emits
`decomp-workbench-note-list-v1`.

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
