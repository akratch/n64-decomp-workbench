"""Command journey for the shiftability instrumentation.

``shift`` is a group with room in it. ``shift audit`` is the static half: one
map, one image, one pass, no build. ``shift rehearse`` is the empirical half,
which relinks against a padded script and diffs the two images -- the command
the audit's own text points at. They share a vocabulary
(regions, the movable window, the address model) and a reader's mental model,
so they share a group rather than arriving as two unrelated top-level words.

``rehearse`` is itself a group, for a reason the two halves make obvious.
``analyze`` takes two prebuilt links and explains the difference; it needs no
toolchain, and is the mode a test, a sweep, or a reviewer with two artifacts
can run. ``orchestrate`` produces those links by calling the project's own
relink script, and is therefore the mode that cannot run anywhere the project
cannot build. Folding them into one command would make every analysis carry
the build surface it does not use.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .census import census_status, evaluate_census, parse_census, print_census
from .cli_options import (
    add_census_argument,
    add_explain_keys_argument,
)
from .discovery import subcommand_listing_handler
from .ldmap import read_ld_map
from .mips_refs import RangeModel, WhitelistEntry
from .pins import PinCatalogue, default_pin_model, parse_whitelist_text, read_pin_files
from .schema import SHIFT_CENSUS_KEYS
from .shift_audit import (
    MAP_SNIFF_BYTES,
    build_shift_audit,
    require_parsed_map,
    shift_audit_lines,
)
from .shift_rehearse import (
    WRAPPER_CONTRACT,
    Rehearsal,
    build_rehearsal,
    orchestrate,
    orchestrate_lines,
    parse_mapping,
    parse_offsets,
    rehearse_lines,
)
from .terminal import add_terminal_arguments, emit_lines

__all__ = [
    "register_shift_commands",
    "shift_audit_command",
    "shift_orchestrate_command",
    "shift_rehearse_command",
]

#: How many rows each capped detail list prints, in both renderings. Every
#: list that hits it prints the cap beside the total, so a truncated list is
#: never mistaken for a short one.
DEFAULT_LIMIT = 40


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 2


def shift_audit_command(args: argparse.Namespace) -> int:
    """Report where a linked project's addresses come from."""

    # The predicate is parsed before anything is read: a sweep that runs this
    # over every version of a ROM should not pay a 10 MB scan to learn that a
    # census key is misspelled.
    try:
        predicates = parse_census(args.census, allowed=SHIFT_CENSUS_KEYS)
    except ValueError as error:
        return _fail(str(error))

    try:
        whitelist: tuple[WhitelistEntry, ...] = tuple(
            entry
            for path in args.whitelist
            for entry in parse_whitelist_text(Path(path).read_text(encoding="utf-8"))
        )
        model = default_pin_model(whitelist=whitelist)
        pin_files = [*args.pins, *args.symbol_addrs]
        pins = (
            read_pin_files(pin_files, model=model)
            if pin_files
            else PinCatalogue(entries=(), sources=())
        )
        ldmap = read_ld_map(args.map)
        if not ldmap.sections:
            # Cheap and only paid when there is something to refuse: a
            # small sniff of the file's own first bytes, not the whole
            # (possibly multi-megabyte, swapped-in-for-`--image`) file.
            with open(args.map, "rb") as handle:
                sample = handle.read(MAP_SNIFF_BYTES)
            require_parsed_map(ldmap, path=str(args.map), sample=sample)
        image = Path(args.image).read_bytes()
        audit = build_shift_audit(
            ldmap=ldmap,
            image=image,
            pins=pins,
            model=model,
            blobs=args.blob,
            map_path=str(args.map),
            image_path=str(args.image),
        )
    except (OSError, ValueError) as error:
        return _fail(str(error))

    payload = audit.as_dict(limit=args.limit)
    try:
        census = evaluate_census(predicates, payload)
    except ValueError as error:
        return _fail(str(error))

    if args.json:
        if census:
            payload["census"] = [item.as_dict() for item in census]
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        emit_lines(
            shift_audit_lines(audit, limit=args.limit),
            width=args.width,
            pager=args.pager,
        )
        print_census(census)
    return census_status(census, otherwise=0)


def _range_model(args: argparse.Namespace) -> RangeModel:
    """Build the address model from the caller's whitelist files."""

    whitelist: tuple[WhitelistEntry, ...] = tuple(
        entry
        for path in args.whitelist
        for entry in parse_whitelist_text(Path(path).read_text(encoding="utf-8"))
    )
    return default_pin_model(whitelist=whitelist)


def shift_rehearse_command(args: argparse.Namespace) -> int:
    """Explain every difference between a base link and a shifted relink."""

    # Same order as the audit: a predicate is parsed before a 10 MB image is
    # read, so a sweep learns about a misspelled key for free.
    try:
        predicates = parse_census(args.census, allowed=SHIFT_CENSUS_KEYS)
    except ValueError as error:
        return _fail(str(error))

    try:
        model = _range_model(args)
        pairs = parse_mapping(args.checksum_pair)
        crc_words = parse_offsets(args.crc_words)
        base_ldmap = read_ld_map(args.base_map)
        base_image = Path(args.base_image).read_bytes()
        shifted_ldmap = read_ld_map(args.shifted_map)
        shifted_image = Path(args.shifted_image).read_bytes()
        delta = int(args.delta, 0)
        rehearsal = build_rehearsal(
            base_ldmap=base_ldmap,
            base_image=base_image,
            shifted_ldmap=shifted_ldmap,
            shifted_image=shifted_image,
            delta=delta,
            anchor=None if args.anchor == "auto" else args.anchor,
            blobs=args.blob,
            crc_words=crc_words,
            checksum_pairs=pairs,
            model=model,
            base_map_path=str(args.base_map),
            base_image_path=str(args.base_image),
            shifted_map_path=str(args.shifted_map),
            shifted_image_path=str(args.shifted_image),
        )
    except (OSError, ValueError) as error:
        return _fail(str(error))

    payload = rehearsal.as_dict(limit=args.limit)
    try:
        census = evaluate_census(predicates, payload)
    except ValueError as error:
        return _fail(str(error))

    if args.json:
        if census:
            payload["census"] = [item.as_dict() for item in census]
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        emit_lines(
            rehearse_lines(rehearsal, limit=args.limit),
            width=args.width,
            pager=args.pager,
        )
        print_census(census)
    return census_status(census, otherwise=0)


def shift_orchestrate_command(args: argparse.Namespace) -> int:
    """Relink once per delta through the caller's wrapper, then analyze each."""

    try:
        predicates = parse_census(args.census, allowed=SHIFT_CENSUS_KEYS)
    except ValueError as error:
        return _fail(str(error))

    try:
        model = _range_model(args)
        pairs = parse_mapping(args.checksum_pair)
        crc_words = parse_offsets(args.crc_words)
        deltas = parse_offsets(args.deltas)
        if not deltas:
            raise ValueError("--deltas names no shift amount")

        def analyze(
            *,
            base_map: Path,
            base_image: Path,
            shifted_map: Path,
            shifted_image: Path,
            delta: int,
        ) -> Rehearsal:
            return build_rehearsal(
                base_ldmap=read_ld_map(base_map),
                base_image=base_image.read_bytes(),
                shifted_ldmap=read_ld_map(shifted_map),
                shifted_image=shifted_image.read_bytes(),
                delta=delta,
                anchor=None if args.anchor == "auto" else args.anchor,
                blobs=args.blob,
                crc_words=crc_words,
                checksum_pairs=pairs,
                model=model,
                base_map_path=str(base_map),
                base_image_path=str(base_image),
                shifted_map_path=str(shifted_map),
                shifted_image_path=str(shifted_image),
            )

        orchestration = orchestrate(
            wrapper=args.wrapper,
            ld_script=Path(args.ld_script),
            anchor_object=args.anchor_object,
            deltas=deltas,
            workdir=Path(args.workdir),
            image_name=args.image_name,
            map_name=args.map_name,
            analyze=analyze,
        )
    except (OSError, ValueError) as error:
        return _fail(str(error))

    payload = orchestration.as_dict(limit=args.limit)
    try:
        census = evaluate_census(predicates, payload)
    except ValueError as error:
        return _fail(str(error))

    if args.json:
        if census:
            payload["census"] = [item.as_dict() for item in census]
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        emit_lines(
            orchestrate_lines(orchestration, limit=args.limit),
            width=args.width,
            pager=args.pager,
        )
        print_census(census)
    return census_status(census, otherwise=0)


def _add_rehearsal_arguments(parser: argparse.ArgumentParser) -> None:
    """Options both rehearsal modes share, with one spelling apiece."""

    parser.add_argument(
        "--anchor",
        default="auto",
        metavar="SYMBOL",
        help=(
            "the symbol the pad was inserted at. The default, `auto`, derives "
            "it from the two maps -- the lowest VRAM inside the movable "
            "window at which shared symbols start differing by --delta -- "
            "which removes the footgun: an anchor wrong by one word "
            "reclassifies the whole image"
        ),
    )
    parser.add_argument(
        "--blob",
        action="append",
        default=[],
        metavar="SECTION",
        help=(
            "treat this output section as opaque bytes: paired and counted, "
            "but never split by its input records and never attributed to a "
            "symbol. Repeatable. Same meaning as `shift audit --blob`"
        ),
    )
    parser.add_argument(
        "--crc-words",
        default="",
        metavar="OFFSETS",
        help=(
            "comma-separated ROM offsets a post-link CRC step writes "
            "(N64: 0x10,0x14). Recognised before any decode or value test, "
            "so a checksum word is never explained as an address"
        ),
    )
    parser.add_argument(
        "--checksum-pair",
        action="append",
        default=[],
        metavar="FUNC=VAR",
        help=(
            "a checksum-protected function and the variable its byte-sum is "
            "patched into. Repeatable. Each pair is checked against the "
            "consistency rule: if any word in FUNC's body changed, VAR must "
            "have changed too. Every pair reports a status, passes included"
        ),
    )
    parser.add_argument(
        "--whitelist",
        action="append",
        default=[],
        metavar="FILE",
        help=(
            "addresses to accept as authentic, one `0xADDR reason` or "
            "`0xLO-0xHI reason` per line. Repeatable. Same file `shift audit` "
            "reads"
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        metavar="N",
        help=(
            f"rows per capped detail list (default: {DEFAULT_LIMIT}); every "
            "list prints its cap beside its total"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit a `decomp-workbench-shift-rehearse-v1` report",
    )
    add_census_argument(parser)
    add_explain_keys_argument(parser)
    add_terminal_arguments(parser)


_AUDIT_DESCRIPTION = (
    "Inventory a linked project's addresses without building anything. The "
    "pin half reads the project's own linker-input symbol files and says "
    "which addresses follow the layout (`gMainMemoryPool = main_BSS_END`) "
    "and which are written down (`D_B0000574 = 0xB0000574`). The scan half "
    "reads the image's data and blob regions and reports every word holding "
    "a value inside the movable VRAM window -- with the features that "
    "discriminate a real address reference from a packed field, a repeated "
    "struct constant, a fixed-point table value, or build-machine garbage. "
    "Tiers rank how confidently a word is a reference, never how dangerous "
    "it is: a linked ROM keeps no relocations, so only a shifted relink "
    "(`shift rehearse`) can say which references actually move."
)

_REHEARSE_DESCRIPTION = (
    "The empirical referee. Build the same objects twice against linker "
    "scripts that differ by an inserted pad, and explain every byte of the "
    "difference: which words tracked the shift and how, which build step "
    "wrote the ones neither the compiler nor the linker did, and -- the "
    "finding -- which address-shaped words stayed exactly where they were. "
    "`analyze` explains two links you already have. `orchestrate` produces "
    "them by calling your own relink script. Run "
    "`decomp-workbench shift rehearse analyze --help` for the analysis."
)

_ANALYZE_DESCRIPTION = (
    "Explain the difference between one base link and one shifted relink of "
    "the same objects. Words below the insertion pair positionally and words "
    "at or above it pair with a delta correction, so the report counts the "
    "thousands of words a shift really changes rather than the millions a "
    "naive diff would. Every changed word is classified (jump targets, %hi/"
    "%lo halves, absolute pointers, CRC and checksum storage) and every "
    "changed word that fits no class is `unexplained` -- the gate. Every "
    "address-shaped word that did *not* change is judged against `shift "
    "audit`'s own confidence tiers: ranked high and unmoved is "
    "`stale-confirmed`, the strongest available evidence for a hardcoded "
    "pointer. The headline is that pair, and both numbers are evidence with "
    "coordinates attached, not a verdict about your project."
)

_ORCHESTRATE_DESCRIPTION = (
    "Generate the padded linker scripts, relink through your wrapper once "
    "per delta, analyze each result, and compare the analyses. The pad is "
    "one line -- `. += DELTA;` after the object you name -- because the "
    "objects are this experiment's controlled constant: relink only, never "
    "recompile, or the question changes. Two deltas rather than one, "
    "because a partially symbolized reference can encode correctly at one "
    "shift by coincidence; a class count that differs between deltas is "
    "reported as a finding."
)


def register_shift_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register the ``shift`` group and its ``audit`` and ``rehearse`` halves."""

    parser = commands.add_parser(
        "shift",
        help="inventory and rehearse a project's shiftability",
        description=(
            "Matching proves the bytes at one layout; shiftability is whether "
            "the addresses in them are references. `audit` is the static "
            "inventory -- one map, one image, no build. `rehearse` is the "
            "empirical referee -- the same objects relinked against a padded "
            "script, with every changed word explained. Run "
            "`decomp-workbench shift audit --help` or "
            "`decomp-workbench shift rehearse --help`."
        ),
    )
    operations = parser.add_subparsers(dest="shift_command")
    # Naming no operation is discovery, not a usage error -- see
    # `subcommand_listing_handler`.
    parser.set_defaults(handler=subcommand_listing_handler(parser))

    audit = operations.add_parser(
        "audit",
        help="report where a linked project's addresses come from",
        description=_AUDIT_DESCRIPTION,
        epilog=(
            "example: decomp-workbench shift audit --map build/game.map "
            "--image build/game.z64 --pins ver/symbols/undefined_syms.txt "
            "--blob .assets"
        ),
    )
    audit.add_argument(
        "--map", required=True, metavar="FILE", help="the linked `ld -Map` file"
    )
    audit.add_argument(
        "--image",
        required=True,
        metavar="FILE",
        help="the linked image the map describes",
    )
    audit.add_argument(
        "--pins",
        action="append",
        default=[],
        metavar="FILE",
        help=(
            "an ld-script symbol-assignment file such as "
            "ver/symbols/undefined_syms.txt; repeatable"
        ),
    )
    audit.add_argument(
        "--symbol-addrs",
        action="append",
        default=[],
        metavar="FILE",
        help=(
            "a splat `symbol_addrs` file; repeatable. Read with the same "
            "grammar as --pins, plus the `key:value` attributes splat writes "
            "in the trailing comment"
        ),
    )
    audit.add_argument(
        "--blob",
        action="append",
        default=[],
        metavar="SECTION",
        help=(
            "treat this output section as opaque bytes: scanned, but never "
            "split by its input records and never attributed to a symbol. "
            "Repeatable. Use it for DMA'd segments and boot code, whose VMA "
            "is a load target rather than a place code lives"
        ),
    )
    audit.add_argument(
        "--whitelist",
        action="append",
        default=[],
        metavar="FILE",
        help=(
            "addresses to accept as authentic, one `0xADDR reason` or "
            "`0xLO-0xHI reason` per line (# comments ignored, high bound "
            "inclusive). Repeatable. A reason is required: an address with "
            "no reason is one somebody re-derives later"
        ),
    )
    audit.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        metavar="N",
        help=(
            f"rows per capped detail list (default: {DEFAULT_LIMIT}); every "
            "list prints its cap beside its total"
        ),
    )
    audit.add_argument(
        "--json",
        action="store_true",
        help="emit a `decomp-workbench-shift-audit-v1` report",
    )
    add_census_argument(audit)
    add_explain_keys_argument(audit)
    add_terminal_arguments(audit)
    audit.set_defaults(handler=shift_audit_command, report_command="shift-audit")

    rehearse = operations.add_parser(
        "rehearse",
        help="explain a real shifted relink, word by word",
        description=_REHEARSE_DESCRIPTION,
    )
    rehearsals = rehearse.add_subparsers(dest="rehearse_command")
    rehearse.set_defaults(handler=subcommand_listing_handler(rehearse))

    analyze = rehearsals.add_parser(
        "analyze",
        help="explain the difference between two prebuilt links",
        description=_ANALYZE_DESCRIPTION,
        epilog=(
            "example: decomp-workbench shift rehearse analyze "
            "--base-map build/base.map --base-image build/base.z64 "
            "--shifted-map build/shift/game.map "
            "--shifted-image build/shift/game.z64 --delta 0x10 "
            "--blob .assets --crc-words 0x10,0x14 "
            "--checksum-pair race_check_finish=gRaceCheckFinishChecksum "
            "--census unexplained_changed=0,stale_confirmed=0"
        ),
    )
    analyze.add_argument(
        "--base-map", required=True, metavar="FILE", help="the unshifted `ld -Map` file"
    )
    analyze.add_argument(
        "--base-image",
        required=True,
        metavar="FILE",
        help="the unshifted linked image",
    )
    analyze.add_argument(
        "--shifted-map",
        required=True,
        metavar="FILE",
        help="the relinked build's `ld -Map` file",
    )
    analyze.add_argument(
        "--shifted-image",
        required=True,
        metavar="FILE",
        help="the relinked build's linked image",
    )
    analyze.add_argument(
        "--delta",
        required=True,
        metavar="HEX",
        help=(
            "bytes the pad inserted; the relinked image must be exactly this "
            "much larger than the base, and a mismatch is refused rather than "
            "paired anyway"
        ),
    )
    _add_rehearsal_arguments(analyze)
    analyze.set_defaults(
        handler=shift_rehearse_command, report_command="shift-rehearse"
    )

    driver = rehearsals.add_parser(
        "orchestrate",
        help="relink once per delta through your own script, then analyze each",
        description=_ORCHESTRATE_DESCRIPTION,
        epilog=(
            "example: decomp-workbench shift rehearse orchestrate "
            "--wrapper tools/relink.sh --ld-script mods/game.custom.ld "
            "--anchor-object build/src/hasm/entrypoint.s.o "
            "--deltas 0x10,0x40 --workdir .workbench/rehearsal "
            "--image-name game.z64 --map-name game.map --blob .assets"
        ),
    )
    driver.add_argument(
        "--wrapper",
        required=True,
        metavar="SCRIPT",
        help=f"your project's relink script. Contract: {WRAPPER_CONTRACT}",
    )
    driver.add_argument(
        "--ld-script",
        required=True,
        metavar="FILE",
        help="the project's own linker script, read but never modified in place",
    )
    driver.add_argument(
        "--anchor-object",
        required=True,
        metavar="PATH",
        help=(
            "the object path the pad line goes after. Exactly one line of the "
            "linker script must mention it: zero is a typo and two is "
            "ambiguous, and both refuse before anything is built"
        ),
    )
    driver.add_argument(
        "--deltas",
        required=True,
        metavar="HEX,HEX",
        help=(
            "comma-separated shift amounts. Two, not one: a partially "
            "symbolized reference can encode correctly at one delta by "
            "coincidence and cannot at two"
        ),
    )
    driver.add_argument(
        "--workdir",
        required=True,
        metavar="DIR",
        help="where the padded scripts and each run's output directory go",
    )
    driver.add_argument(
        "--image-name",
        default="image",
        metavar="NAME",
        help="the file name the wrapper leaves the image under (default: image)",
    )
    driver.add_argument(
        "--map-name",
        default="map",
        metavar="NAME",
        help="the file name the wrapper leaves the map under (default: map)",
    )
    _add_rehearsal_arguments(driver)
    driver.set_defaults(
        handler=shift_orchestrate_command, report_command="shift-orchestrate"
    )
