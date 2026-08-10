"""Command journey for the sweep family: generate sources, then read them back.

Every command here stops at the source. The project's own compile-one wrapper
turns a sweep directory into objects -- that is the boundary `campaign` already
draws -- and `sweep ingest` is what happens when they come back.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .cli_options import (
    add_explain_keys_argument,
    add_list_file_argument,
    add_symbol_argument,
)
from .compose import ComposeError, parse_zone
from .csource import CSourceError
from .sweep import (
    GENERATOR_CLASSES,
    SweepError,
    SweepManifest,
    read_manifest,
    write_family,
)
from .sweep_generators import (
    carrier_pool,
    commutative_family,
    copy_family,
    fusion_donors,
    fusion_family,
    hoist_family,
    parse_construct,
    removal_family,
)
from .sweep_ingest import ingest_lines, ingest_sweep
from .terminal import add_terminal_arguments, emit_lines

__all__ = ["register_sweep_commands"]

#: RuntimeError is what a failed objdump raises, and `sweep ingest` reads
#: objects. Without it a broken toolchain leaves a traceback and exit 1 --
#: the code reserved for "a requested gate failed", which a sweep driver
#: treats as "no match, keep going".
_SWEEP_ERRORS = (
    SweepError,
    ComposeError,
    CSourceError,
    OSError,
    RuntimeError,
    ValueError,
)


def _frozen(args: argparse.Namespace) -> tuple[tuple[int, int], ...]:
    return tuple(parse_zone(item) for item in args.frozen)


def _emit_manifest(args: argparse.Namespace, manifest: SweepManifest) -> int:
    """Write the family, then say what was written and what comes next."""

    placed = write_family(manifest, directory=args.write, overwrite=args.overwrite)
    if args.json:
        print(json.dumps(placed.as_dict(), indent=2, sort_keys=True))
        return 0
    lines = [
        f"sweep {placed.generator}: {len(placed.variants)} variant source(s) "
        f"in {placed.directory}",
        f"base: {placed.base}  sha256 {placed.base_sha256[:16]}",
        "",
    ]
    classes: dict[str, int] = {}
    for item in placed.variants:
        classes[item.key.generator_class] = classes.get(item.key.generator_class, 0) + 1
    for letter, count in sorted(classes.items()):
        entry = GENERATOR_CLASSES[letter]
        lines.append(f"  {letter}  {count:>4}  {entry.name} -- {entry.description}")
    if placed.dropped:
        lines.extend(("", f"refused ({len(placed.dropped)}), each with its reason:"))
        for refusal in placed.dropped[: args.limit or len(placed.dropped)]:
            lines.append(f"  {refusal.get('site', '?')}  {refusal.get('reason', '')}")
        if args.limit and len(placed.dropped) > args.limit:
            lines.append(f"  ... {len(placed.dropped) - args.limit} more")
    lines.extend(
        (
            "",
            placed.coverage.sentence(),
            "",
            "next: build each source with the project's compile-one wrapper, "
            "writing OBJDIR/<name>.o, then",
            f"      decomp-workbench sweep ingest {placed.directory} "
            "--objects OBJDIR --target target.o",
        )
    )
    emit_lines(lines, width=args.width, pager=args.pager)
    return 0


def _fail(error: Exception) -> int:
    print(f"error: {error}", file=sys.stderr)
    return 2


# --------------------------------------------------------------------------
# carriers / donors -- the two read-only questions
# --------------------------------------------------------------------------


def sweep_carriers_command(args: argparse.Namespace) -> int:
    try:
        pool = carrier_pool(args.source, at=args.at, wanted_type=args.type)
    except _SWEEP_ERRORS as error:
        return _fail(error)
    if args.json:
        print(json.dumps(pool.as_dict(), indent=2, sort_keys=True))
        return 0
    lines = [
        f"carrier pool: {pool.source} at line {pool.at}",
        f"{pool.declared} declared local(s); {len(pool.usable)} dead here and "
        "therefore free",
        "",
        " idx  line  verdict    name                 type",
    ]
    for item in pool.carriers:
        lines.append(
            f" {item.declaration_index:<4} {item.declaration_line:<5} "
            f"{item.verdict:<10} {item.name[:20]:<20} {item.type_text}"
        )
        if not item.usable or args.verbose:
            lines.append(f"        {item.reason}")
    lines.extend(
        (
            "",
            "A carrier is an existing local that is dead here. A fresh "
            "declaration mints a frame slot (8 bytes for an f32 on the one "
            "compiler this was measured on) and the frame gate rejects it, so "
            "the pool never proposes one -- and an unused pad has no web to "
            "merge into, which is why declared symbols come first.",
            "",
            "next: decomp-workbench sweep hoist "
            f"{pool.source} --line {pool.at} --write variants/",
        )
    )
    emit_lines(lines, width=args.width, pager=args.pager)
    return 0


def sweep_donors_command(args: argparse.Namespace) -> int:
    try:
        donors = fusion_donors(args.source, target=args.target)
    except _SWEEP_ERRORS as error:
        return _fail(error)
    payload = {
        "schema": "decomp-workbench-fusion-donors-v1",
        "source": str(args.source),
        "target": args.target,
        "donors": [item.as_dict() for item in donors],
        "disjoint_count": sum(1 for item in donors if item.disjoint),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    lines = [
        f"fusion donors for {args.target}: {args.source}",
        f"{payload['disjoint_count']} of {len(donors)} local(s) have a live "
        "range that avoids the target's",
        "",
        " idx  live      name                 verdict",
    ]
    for item in donors:
        lines.append(
            f" {item.declaration_index:<4} "
            f"{f'{item.first}..{item.last}':<9} {item.name[:20]:<20} "
            f"{'FUSABLE' if item.disjoint else 'no'}"
        )
        lines.append(f"        {item.reason}")
    lines.extend(
        (
            "",
            "This is the half of the donor table that needs no build. The "
            "other half is the donor's price -- how many rows touch its stack "
            "slot -- and that is `decomp-workbench slots OBJECT`.",
            "",
            f"next: decomp-workbench sweep fuse {args.source} "
            f"--target {args.target} --write variants/",
        )
    )
    emit_lines(lines, width=args.width, pager=args.pager)
    return 0


# --------------------------------------------------------------------------
# the generators
# --------------------------------------------------------------------------


def sweep_regress_command(args: argparse.Namespace) -> int:
    try:
        constructs = tuple(parse_construct(item) for item in args.construct)
        manifest = removal_family(
            args.source,
            constructs=constructs,
            order=args.order,
            frozen=_frozen(args),
        )
        return _emit_manifest(args, manifest)
    except _SWEEP_ERRORS as error:
        return _fail(error)


def sweep_hoist_command(args: argparse.Namespace) -> int:
    try:
        classes = tuple(
            item.strip().upper() for item in args.classes.split(",") if item.strip()
        )
        manifest = hoist_family(
            args.source,
            line=args.line,
            classes=classes,
            carriers=tuple(args.carrier),
            frozen=_frozen(args),
        )
        return _emit_manifest(args, manifest)
    except _SWEEP_ERRORS as error:
        return _fail(error)


def sweep_commute_command(args: argparse.Namespace) -> int:
    try:
        manifest = commutative_family(
            args.source,
            lines=tuple(args.line),
            frozen=_frozen(args),
        )
        return _emit_manifest(args, manifest)
    except _SWEEP_ERRORS as error:
        return _fail(error)


def sweep_copies_command(args: argparse.Namespace) -> int:
    try:
        manifest = copy_family(args.source, frozen=_frozen(args))
        return _emit_manifest(args, manifest)
    except _SWEEP_ERRORS as error:
        return _fail(error)


def sweep_fuse_command(args: argparse.Namespace) -> int:
    try:
        manifest = fusion_family(
            args.source,
            target=args.target,
            donors=tuple(args.donor),
            frozen=_frozen(args),
        )
        return _emit_manifest(args, manifest)
    except _SWEEP_ERRORS as error:
        return _fail(error)


# --------------------------------------------------------------------------
# ingest
# --------------------------------------------------------------------------


def sweep_ingest_command(args: argparse.Namespace) -> int:
    try:
        manifest = read_manifest(args.manifest)
        result = ingest_sweep(
            manifest,
            objects=args.objects,
            target=args.target,
            suffix=args.object_suffix,
            dumps=args.dumps,
            target_dumps=args.target_dumps,
            objdump=args.objdump,
            symbol=args.symbol,
            section=args.section,
            slot=args.slot,
            cache_directory=args.disassembly_cache,
        )
    except _SWEEP_ERRORS as error:
        return _fail(error)
    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
        return 0
    limit = args.limit if args.limit else len(result.results) or 1
    emit_lines(ingest_lines(result, limit=limit), width=args.width, pager=args.pager)
    return 0


# --------------------------------------------------------------------------
# registration
# --------------------------------------------------------------------------


def _add_generator_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--write",
        required=True,
        metavar="DIR",
        help="write the variant sources and sweep.json here",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace a non-empty --write directory",
    )
    parser.add_argument(
        "--frozen",
        action="append",
        default=[],
        metavar="LO..HI",
        help=(
            "lines no edit may touch -- another construction's protected "
            "zone; repeatable"
        ),
    )
    add_list_file_argument(parser, option="frozen", dest="frozen", noun="frozen zones")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="refused rows to print before eliding (default: 20; 0 prints all)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    add_terminal_arguments(parser)


def register_sweep_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register the flat `sweep-*` commands behind the `sweep` group spelling."""

    carriers = commands.add_parser(
        "sweep-carriers",
        help=argparse.SUPPRESS,
        description=(
            "List the locals that are dead at one line and can therefore "
            "carry a hoisted value for free. A fresh declaration mints a "
            "frame slot the frame gate rejects, and an unused pad has no web "
            "to merge into -- so the pool is existing declared locals, in "
            "declaration order, and every refusal names its reason."
        ),
        epilog=(
            "example: decomp-workbench sweep carriers "
            "examples/fixtures/value-equality.c --at 13"
        ),
    )
    carriers.add_argument("source", help="the C source to read")
    carriers.add_argument(
        # `--at` and `--line` are one option, as `--symbol`/`--function` are:
        # this command's own `next:` line hands the reader to `sweep hoist`,
        # which spells the same number the other way.
        "--at",
        "--line",
        type=int,
        required=True,
        metavar="LINE",
        help="the site line; --line is the same option",
    )
    carriers.add_argument(
        "--type", metavar="TYPE", help="only carriers declared with this type"
    )
    carriers.add_argument(
        "--verbose", action="store_true", help="print the reason for every carrier"
    )
    carriers.add_argument("--json", action="store_true", help="emit JSON")
    add_terminal_arguments(carriers)
    carriers.set_defaults(
        handler=sweep_carriers_command, report_command="sweep-carriers"
    )

    donors = commands.add_parser(
        "sweep-donors",
        help=argparse.SUPPRESS,
        description=(
            "Rank every local by whether its live range avoids the target's. "
            "That is the half of the fusion question that needs no build; the "
            "other half -- how many rows touch the donor's stack slot, which "
            "is its price -- is `slots`."
        ),
        epilog=(
            "example: decomp-workbench sweep donors "
            "examples/fixtures/value-equality.c --target sp4A0"
        ),
    )
    donors.add_argument("source", help="the C source to read")
    donors.add_argument(
        "--target", required=True, metavar="NAME", help="the local to fuse into"
    )
    donors.add_argument("--json", action="store_true", help="emit JSON")
    add_terminal_arguments(donors)
    donors.set_defaults(handler=sweep_donors_command, report_command="sweep-donors")

    regress = commands.add_parser(
        "sweep-regress",
        help=argparse.SUPPRESS,
        description=(
            "Emit the removal lattice: the base unedited (the control), then "
            "each accumulated construct deleted, singly and jointly. This is "
            "the experiment nobody runs -- every stage inherits its "
            "predecessor's construction and attacks only the residue -- and "
            "the one time one campaign ran it, twelve builds showed a "
            "four-atom supplier set was dead weight costing ten rows on the "
            "live base. Run it first, not last."
        ),
        epilog=(
            "example: decomp-workbench sweep regress work.c "
            "--construct 920..921=hoist --construct 977=deadread "
            "--write regress/"
        ),
    )
    regress.add_argument("source", help="the C source the levers were added to")
    regress.add_argument(
        "--construct",
        action="append",
        default=[],
        metavar="LO..HI[=LABEL]",
        help="one accumulated lever, by the lines that spell it; repeatable",
    )
    add_list_file_argument(
        regress, option="construct", dest="construct", noun="constructs"
    )
    regress.add_argument(
        "--order",
        type=int,
        default=1,
        metavar="N",
        help=(
            "remove up to N constructs jointly (default: 1; the all-removed "
            "point is always included)"
        ),
    )
    _add_generator_arguments(regress)
    regress.set_defaults(handler=sweep_regress_command, report_command="sweep-regress")

    hoist = commands.add_parser(
        "sweep-hoist",
        help=argparse.SUPPRESS,
        description=(
            "Emit one variant per (operand, carrier) pair at one statement. "
            "Class O hoists a leaf out of a nested subexpression -- a "
            "different price from splitting the top-level operator, because a "
            "deep hoist can leave the local ring rotation undisturbed. P and "
            "A cover the compound assignment and the call argument, which no "
            "generator library had. The carrier is part of the key: at one "
            "line, two carriers from different declaration indices produced "
            "two entirely different cost deltas."
        ),
        epilog=(
            "example: decomp-workbench sweep hoist work.c --line 920 "
            "--class O,P --write hoists/"
        ),
    )
    hoist.add_argument("source", help="the C source to read")
    hoist.add_argument(
        "--line",
        "--at",
        type=int,
        required=True,
        metavar="LINE",
        help="the statement to hoist; --at is the same option",
    )
    hoist.add_argument(
        "--class",
        dest="classes",
        default="O",
        metavar="LETTERS",
        help="comma-separated hoist classes: H, O, P, A (default: O)",
    )
    hoist.add_argument(
        "--carrier",
        action="append",
        default=[],
        metavar="NAME",
        help="use these carriers instead of every dead local; repeatable",
    )
    add_list_file_argument(hoist, option="carrier", dest="carrier", noun="carriers")
    _add_generator_arguments(hoist)
    hoist.set_defaults(handler=sweep_hoist_command, report_command="sweep-hoist")

    commute = commands.add_parser(
        "sweep-commute",
        help=argparse.SUPPRESS,
        description=(
            "Emit one variant per commutative operand pair, exchanged. The "
            "classifier that names a commutative row is shipped; this is the "
            "lever it never had. Only textually pure exchanges are emitted: a "
            "swap that would need new parentheses to stay associative-safe is "
            "refused and named, because the parentheses would be a second, "
            "untested edit."
        ),
        epilog=(
            "example: decomp-workbench sweep commute "
            "examples/fixtures/value-equality.c --write commute/"
        ),
    )
    commute.add_argument("source", help="the C source to read")
    commute.add_argument(
        "--line",
        "--at",
        action="append",
        default=[],
        type=int,
        metavar="LINE",
        help=(
            "restrict to these lines; repeatable, and --at is the same "
            "option (default: the whole file)"
        ),
    )
    add_list_file_argument(
        commute, option="line", dest="line", noun="line numbers", value_type=int
    )
    _add_generator_arguments(commute)
    commute.set_defaults(handler=sweep_commute_command, report_command="sweep-commute")

    copies = commands.add_parser(
        "sweep-copies",
        help=argparse.SUPPRESS,
        description=(
            "Find every copy `Y = X;` between two declared locals and emit the "
            "variant that drops it, rehosting Y's later reads onto X. Worth "
            "nine rows in one campaign case and fifteen in another. A copy "
            "whose rehosting the text cannot prove -- X written again, Y "
            "written again, either address taken -- is refused and named."
        ),
        epilog="example: decomp-workbench sweep copies work.c --write copies/",
    )
    copies.add_argument("source", help="the C source to read")
    _add_generator_arguments(copies)
    copies.set_defaults(handler=sweep_copies_command, report_command="sweep-copies")

    fuse = commands.add_parser(
        "sweep-fuse",
        help=argparse.SUPPRESS,
        description=(
            "Emit one variant per donor fused into the target: the donor's "
            "declaration goes and its occurrences read the target instead, so "
            "two webs become one and a stack slot is reclaimed. Only donors "
            "whose live range provably avoids the target's are emitted. Every "
            "edit states the base sha it was written against and refuses a "
            "frozen zone, because a composer that edits another stage's "
            "protected lines is how two constructions merge silently."
        ),
        epilog=(
            "example: decomp-workbench sweep fuse work.c --target sp4B8 "
            "--frozen 900..940 --write fuse/"
        ),
    )
    fuse.add_argument("source", help="the C source to read")
    fuse.add_argument(
        "--target", required=True, metavar="NAME", help="the local to fuse into"
    )
    fuse.add_argument(
        "--donor",
        action="append",
        default=[],
        metavar="NAME",
        help="fuse only these donors; repeatable (default: every fusable one)",
    )
    add_list_file_argument(fuse, option="donor", dest="donor", noun="donors")
    _add_generator_arguments(fuse)
    fuse.set_defaults(handler=sweep_fuse_command, report_command="sweep-fuse")

    ingest = commands.add_parser(
        "sweep-ingest",
        help=argparse.SUPPRESS,
        description=(
            "Read a built sweep back: locate each variant's object, print its "
            "gate line (sha, ni, frame, load/store traffic, ring coset) and "
            "its shift-tolerant distance from the target, and rank the family. "
            "A wrong instruction count is a column, never a rejection -- "
            "position-indexed scoring turned one inserted instruction into a "
            "four-figure mismatch and cost eleven stages their candidates. A "
            "variant with no object is a row naming the path that was looked "
            "for, and the coverage line says what the family's negative "
            "result is entitled to claim."
        ),
        epilog=(
            "example: decomp-workbench sweep ingest regress/ --objects o/ "
            "--target target.o"
        ),
    )
    ingest.add_argument("manifest", help="the sweep directory, or its sweep.json")
    ingest.add_argument(
        "--objects",
        required=True,
        metavar="DIR",
        help="directory the wrapper wrote the built variants into",
    )
    ingest.add_argument(
        "--target",
        required=True,
        metavar="OBJ",
        help=(
            "the reference object the variants are scored against. An object "
            "path, not a variable name: `--target` on the generator side "
            "(`sweep donors`, `sweep fuse`) is the C local being fused into"
        ),
    )
    ingest.add_argument(
        "--object-suffix",
        default=".o",
        metavar="EXT",
        help="built object name is <variant stem><EXT> (default: .o)",
    )
    ingest.add_argument(
        "--dumps",
        action="store_true",
        help="the built variants are retained `objdump -d -r` text",
    )
    ingest.add_argument(
        "--target-dumps",
        action="store_true",
        help="the target is retained `objdump -d -r` text",
    )
    ingest.add_argument(
        "--slot",
        type=int,
        metavar="OFFSET",
        help=(
            "count loads and stores at this sp-relative stack slot only -- "
            "the 1184 in `lwc1 $f10,1184(sp)`, which `slots` lists. It is not "
            "the frame offset `trace-cascade` keys a site by; that is this "
            "number plus the frame size"
        ),
    )
    ingest.add_argument(
        "--section", default=".text", help="object section (default: .text)"
    )
    ingest.add_argument(
        "--objdump", help="GNU-compatible MIPS objdump; auto-detected when omitted"
    )
    ingest.add_argument(
        "--disassembly-cache",
        metavar="DIR",
        help="reuse disassemblies from this directory across runs",
    )
    add_symbol_argument(ingest, help_text="read only this exact symbol")
    ingest.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="ranked rows to print before eliding (default: 20; 0 prints all)",
    )
    ingest.add_argument("--json", action="store_true", help="emit JSON")
    add_explain_keys_argument(ingest)
    add_terminal_arguments(ingest)
    ingest.set_defaults(handler=sweep_ingest_command, report_command="sweep-ingest")
