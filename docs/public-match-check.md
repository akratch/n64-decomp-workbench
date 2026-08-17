# Gate 0: is it already matched in public?

The cheapest way to finish a function is to find out that somebody already
did. Run this before a campaign, not after one:

```sh
decomp-workbench public-match-check func_800C1A90 --address 0x800C1A90 --instructions 127
```

```text
public match check: 3 scratches, 1 site-verified match(es), 1 override claim(s)
queries: 'func_800C1A90', '800C1A90', '800c1a90', '0x800c1a90'
bound to max_score=12700 (127 instructions); 4 other result(s) excluded
!! MATCH  slug=aBcDe owner=someone score=0/12700 override=false updated=2026-05-01
           https://decomp.me/scratch/aBcDe
!! CLAIM  slug=Fg7Hi owner=another score=400/12700 override=true updated=2026-04-02
   near   slug=Jk9Lm owner=third score=20/12700 override=false updated=2026-06-11
gate 0: a site-verified public match already exists. Read it before spending a
campaign on this function.
```

`--json` emits `decomp-workbench-public-match-check-v1` for tooling, and
`--fail-on-match` returns exit `1` when anything was found, which is the form
a campaign harness or CI job wants.

This is one of the two commands that open a network connection — see the
[network policy](decompme-exports.md#the-network-policy-this-command-lives-under).
It runs only when you ask for it.

## The two rows you must not scroll past

| Row | What it means |
|---|---|
| `!! MATCH` — `score=0` and `match_override=false` | The site compiled that source against that target and found no difference. This function is done, in public, by somebody else. |
| `!! CLAIM` — `match_override=true` | The owner **declared** a match. The site did not verify it, and the score is not evidence. Read the scratch and verify it locally with `check-scratch` before believing it. |

Everything else prints as `near`, ordered by score, because a 20/12700
neighbour is often the best starting source you will find even when it is not
a match.

## Three lessons this command exists to encode

Each of these cost a measured campaign real time.

**1. Walking a family is not a search.** The obvious move — follow the parents
and children of the scratch you inherited — finds nothing, because public
matches live in *unrelated lineages*: a different person, a different preset,
no shared ancestor. Lineage is a story about how one person worked, not an
index of who solved what. Search the site instead.

**2. A name lookup misses scratches named after a data label.** People name a
scratch after the symbol they were staring at when they made it, which is
frequently a jump table, a string, or the next function along — not the
function it actually targets. The durable binding is the *size*: decomp.me
sets `max_score` to the target's instruction count times one hundred, so a
127-instruction target has `max_score` 12700 whatever the scratch is called.
Pass `--instructions 127`, or `--max-score 12700` if you already have the
number, and the filter keeps the right scratch under the wrong name. (Pass an
instruction count to `--max-score` by mistake and the report says so rather
than silently matching nothing.)

**3. An address finds what a name does not.** In one measured sweep, an
address-anchored lookup surfaced roughly 55 of 127 functions that a
name-anchored lookup did not. `--address` searches the three spellings a hand
written name can use — `800C1A90`, `800c1a90`, `0x800c1a90` — as separate
queries, and merges the results; each row records which term found it under
`found_by`.

## What an empty result does and does not prove

It proves that these terms returned nothing today. It does not prove novelty.
A scratch can be private, named after something you did not think to search,
or created after you looked. The report carries that caveat in its own
`limits`, so a harness that reads the JSON cannot quietly turn "no results"
into "nobody has done this".

If the check is clear, continue with
[the export workflow](decompme-exports.md) or a
[campaign](campaigns.md). If it is not, fetch the winner
(`fetch-scratch <slug>`) and read it first.

## Recon over a large public repository

When the follow-up is "has anyone in this project's community already solved
this family", the efficient shape is two clones with different truncations:

```sh
# Full blobs at HEAD, no history: grep the code.
git clone --depth 1 https://github.com/n64decomp/sm64.git repo-content
# Full history, no blobs: read log subjects and authors.
git clone --filter=blob:none https://github.com/n64decomp/sm64.git repo-history
```

The shallow clone answers content questions; the blobless clone answers
history questions (`git log --oneline`, subjects, authors). Do not run
`git log -S` or `git show` against the blobless clone — every blob it needs
is fetched one round-trip at a time, and a search that would take seconds
locally degrades into thousands of network requests.
