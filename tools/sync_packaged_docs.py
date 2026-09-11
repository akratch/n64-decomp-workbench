#!/usr/bin/env python3
"""Mirror every documentation page that ships as package data.

    python3 tools/sync_packaged_docs.py            # copy canonical -> packaged
    python3 tools/sync_packaged_docs.py --check    # fail if they differ

`src/decomp_workbench/docs/` holds byte-identical copies of pages under `docs/`
so an installed wheel can print them without a checkout. Keeping them identical
was a manual `cp` after every edit, and the guarantee was tested for exactly one
of the four files.

The other three drifted the way unwatched invariants do: `improvement-backlog.md`
fell **636 lines** behind its canonical copy — everything from item 17 onward —
while the two compiler-law pages stayed in sync only because whoever edited them
happened to remember. A reader of the installed wheel would have been served a
backlog missing half its entries with nothing anywhere reporting it.

So the set is derived rather than listed: every file under the packaged tree
must have a canonical counterpart, and every canonical counterpart is copied.
Adding a fifth page cannot forget to register it, because there is nothing to
register.
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "docs"
PACKAGED = ROOT / "src" / "decomp_workbench" / "docs"


def pairs() -> list[tuple[pathlib.Path, pathlib.Path]]:
    """Every packaged page and the canonical page it mirrors."""
    out = []
    for packaged in sorted(PACKAGED.rglob("*.md")):
        canonical = CANONICAL / packaged.relative_to(PACKAGED)
        out.append((canonical, packaged))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Mirror packaged documentation.")
    ap.add_argument("--check", action="store_true",
                    help="report drift and exit nonzero instead of copying")
    args = ap.parse_args(argv)

    missing, drifted, copied = [], [], []
    for canonical, packaged in pairs():
        if not canonical.is_file():
            missing.append(packaged.relative_to(ROOT).as_posix())
            continue
        if canonical.read_bytes() == packaged.read_bytes():
            continue
        name = packaged.relative_to(ROOT).as_posix()
        if args.check:
            a = canonical.read_text(encoding="utf-8").splitlines()
            b = packaged.read_text(encoding="utf-8").splitlines()
            drifted.append(f"{name}: canonical {len(a)} lines, packaged {len(b)}")
        else:
            shutil.copyfile(canonical, packaged)
            copied.append(name)

    for name in missing:
        print(f"error: {name} has no canonical counterpart under docs/",
              file=sys.stderr)
    if args.check:
        for line in drifted:
            print(f"drifted: {line}", file=sys.stderr)
        if drifted or missing:
            print("\nRun tools/sync_packaged_docs.py to mirror them.",
                  file=sys.stderr)
            return 1
        print(f"packaged docs in sync ({len(pairs())} page(s))")
        return 0

    for name in copied:
        print(f"synced {name}")
    if not copied:
        print(f"packaged docs already in sync ({len(pairs())} page(s))")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
