"""CLI for the linked-image oracle: `reloc-surface` and `linked-compare`.

Two commands, one loop. `reloc-surface` turns the per-function integration
ritual an unrelocated module demands -- a hand-derived linker value for every
placeholder the candidate references -- into generated data. `linked-compare`
then reads the image that link produced and says, per function, whether its
bytes are the target's.

Neither builds anything. The host drives its own make; see
`docs/linked-oracle.md` for the loop and a worked example of it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .elf import ElfFormatError, read_elf
from .evidence import (
    EvidenceError,
    artifact_record,
    load_json_object,
    write_json_atomic,
)
from .linked_compare import (
    ImageRange,
    RangeError,
    compare_images,
    parse_range_argument,
    parse_ranges,
    render,
)
from .reloc_surface import (
    ModuleMapError,
    RelocSurface,
    audit,
    parse_module_map,
    render_linker_block,
    synthesize,
    tracked_values,
)
from .relocation_identity import identity_report, parse_identity_provider
from .relocation_proof import (
    EVIDENCE_SCHEMA,
    build_relocation_proof,
    verify_relocation_proof,
)
from .terminal import warn_to_stderr

_SURFACE_DESCRIPTION = (
    "Synthesize the linker values a module's placeholder symbols must carry, "
    "by reading the stored addend at each relocation site from the target "
    "image. A module that ships unrelocated stores addends, not addresses, so "
    "for a candidate whose schedule already agrees at the site every value is "
    "readable rather than derived by hand. Sites that disagree are refused by "
    "name, with both values and every conflicting site: that is a schedule "
    "divergence at the site, and no consistent addend exists there."
)

_SURFACE_EPILOG = (
    "example: decomp-workbench reloc-surface build/tu.c.o "
    "--module-map module.json --image target.z64"
)

_COMPARE_DESCRIPTION = (
    "Compare a built image against the target image and classify each "
    "function's byte range: exact, text-exact (the range agrees, something "
    "outside it does not), text-differs N words, or size-differs. This is the "
    "only sound oracle for code in a module that ships unrelocated, whose "
    "calls no object-level score can reproduce. Exit status is 0 when every "
    "range's own bytes agree and 1 otherwise."
)

_COMPARE_EPILOG = (
    "example: decomp-workbench linked-compare build/game.z64 target.z64 "
    "--range drawActive:0x1878b84:0x1878c40"
)


def _load_module_map(path: str) -> Any:
    document = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    return parse_module_map(document, origin=path)


def _objects(paths: list[str]) -> list[tuple[str, Any]]:
    return [(path, read_elf(path)) for path in paths]


def reloc_surface_command(args: argparse.Namespace) -> int:
    try:
        module = _load_module_map(args.module_map)
        image = Path(args.image).expanduser().read_bytes()
        surface = synthesize(_objects(args.object), module, image)
        identities = (
            identity_report(
                surface.sites,
                parse_identity_provider(
                    load_json_object(args.identity_provider, where="identity provider")
                ),
            )
            if args.identity_provider
            else None
        )
        report = (
            audit(
                surface,
                tracked_values(
                    Path(args.audit).expanduser().read_text(encoding="utf-8")
                ),
            )
            if args.audit
            else None
        )
    except (
        OSError,
        ValueError,
        ElfFormatError,
        ModuleMapError,
        RangeError,
        json.JSONDecodeError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.json:
        payload: dict[str, Any] = surface.as_dict()
        payload["evidence"] = {
            "schema": EVIDENCE_SCHEMA,
            "module": module.as_dict(),
            "artifacts": [
                artifact_record(args.module_map, role="module-map"),
                artifact_record(args.image, role="target-image"),
                *(
                    artifact_record(path, role="candidate-object")
                    for path in args.object
                ),
                *(
                    [artifact_record(args.identity_provider, role="identity-provider")]
                    if args.identity_provider
                    else []
                ),
            ],
        }
        if identities is not None:
            payload["identities"] = identities
        if not args.sites:
            payload.pop("sites", None)
        if report is not None:
            payload["audit"] = report.as_dict()
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif report is not None:
        print("\n".join(_audit_lines(surface, report)))
    else:
        print("\n".join(render_linker_block(surface)))
        if args.sites:
            for site in surface.sites:
                print(
                    f"/* site {site.object} +0x{site.object_offset:04x} "
                    f"-> module 0x{site.module_offset or 0:x} {site.kind} "
                    f"{site.symbol}{' ' + site.note if site.note else ''} */"
                )
    for warning in surface.warnings:
        warn_to_stderr(warning)
    if args.out:
        Path(args.out).expanduser().write_text(
            "\n".join(render_linker_block(surface)) + "\n", encoding="utf-8"
        )
    if report is not None:
        return 0 if report.ok else 1
    return 0 if surface.ok else 1


def _audit_lines(surface: RelocSurface, report: Any) -> list[str]:
    lines = [
        f"reloc-surface audit {surface.module}",
        f"  objects         {len(surface.objects)}",
        f"  agree           {report.agree}/{report.compared}",
        f"  disagree        {report.disagree}",
        f"  untracked       {report.count('untracked')} "
        "(the link defines these by other means)",
        f"  unreproduced    {report.count('unreproduced')} "
        "(the synthesis did not reach these)",
        f"  conflicts       {len(report.conflicts)}",
    ]
    for row in report.rows:
        if row.status == "disagree":
            lines.append(
                f"  MISMATCH        {row.name} tracked=0x{row.tracked:08x} "
                f"synthesized=0x{row.synthesized:08x}"
            )
    for conflict in report.conflicts:
        lines.append(f"  UNRESOLVED      {conflict.symbol}: {conflict.detail}")
    lines.append("  verdict         " + ("agrees" if report.ok else "DISAGREES"))
    return lines


def linked_compare_command(args: argparse.Namespace) -> int:
    try:
        ranges: list[ImageRange] = []
        if args.ranges:
            document = json.loads(
                Path(args.ranges).expanduser().read_text(encoding="utf-8")
            )
            ranges.extend(parse_ranges(document, origin=args.ranges))
        for text in args.range or ():
            ranges.append(parse_range_argument(text))
        built = Path(args.built).expanduser().read_bytes()
        target = Path(args.target).expanduser().read_bytes()
    except (OSError, RangeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    comparison = compare_images(
        built,
        target,
        ranges,
        built_name=str(args.built),
        target_name=str(args.target),
    )
    if args.json:
        payload = comparison.as_dict()
        payload["evidence"] = {
            "schema": EVIDENCE_SCHEMA,
            "artifacts": [
                artifact_record(args.built, role="built-image"),
                artifact_record(args.target, role="target-image"),
                *(
                    [artifact_record(args.ranges, role="range-map")]
                    if args.ranges
                    else []
                ),
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("\n".join(render(comparison)))
    return 0 if comparison.ok else 1


def relocation_proof_command(args: argparse.Namespace) -> int:
    """Build or verify one hash-bound dual-surface proof receipt."""

    try:
        if args.verify:
            report = verify_relocation_proof(args.verify)
        else:
            missing = [
                name
                for name, value in (
                    ("--linked", args.linked),
                    ("--symbol", args.symbol),
                    ("--source", args.source),
                    ("--candidate-object", args.candidate_object),
                )
                if not value
            ]
            if missing:
                raise EvidenceError(
                    "building a relocation proof requires " + ", ".join(missing)
                )
            report = build_relocation_proof(
                fallback_report=args.fallback,
                linked_report=args.linked,
                symbol=args.symbol,
                source=args.source,
                candidate_object=args.candidate_object,
            )
            if args.out:
                output = Path(args.out).expanduser()
                if output.exists():
                    raise FileExistsError(f"refusing to overwrite receipt: {output}")
                write_json_atomic(output, report)
    except (EvidenceError, FileExistsError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json or not args.out:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"relocation proof: PASS -> {Path(args.out).expanduser()}")
    return 0 if report.get("pass", report.get("status") == "PASS") else 1


def register_linked_oracle_commands(
    commands: argparse._SubParsersAction[Any],
) -> None:
    """Register `reloc-surface` and `linked-compare`."""

    surface = commands.add_parser(
        "reloc-surface",
        help="synthesize a module's placeholder symbol values from the image",
        description=_SURFACE_DESCRIPTION,
        epilog=_SURFACE_EPILOG,
    )
    surface.add_argument(
        "object",
        nargs="+",
        help=(
            "the module's compiled objects. Pass every object of the module "
            "the link consumes: a symbol another of them defines needs no "
            "value at all"
        ),
    )
    surface.add_argument(
        "--module-map",
        required=True,
        metavar="FILE",
        help="the module's section map and per-object text placement (JSON)",
    )
    surface.add_argument(
        "--image",
        required=True,
        metavar="FILE",
        help="the target image the module ships inside",
    )
    surface.add_argument(
        "--audit",
        metavar="FILE",
        help="replay an existing hand-written linker block against the result",
    )
    surface.add_argument(
        "--out",
        metavar="FILE",
        help="also write the generated block to this file",
    )
    surface.add_argument(
        "--sites", action="store_true", help="report every mapped relocation site"
    )
    surface.add_argument(
        "--identity-provider",
        metavar="FILE",
        help=(
            "project-generated relocation identity document; joins exact "
            "overlay/section/offset identities without teaching the workbench "
            "a game's atlas format"
        ),
    )
    surface.add_argument("--json", action="store_true", help="emit JSON")
    surface.set_defaults(handler=reloc_surface_command, report_command="reloc-surface")

    compare = commands.add_parser(
        "linked-compare",
        help="classify a built image against the target, per function range",
        description=_COMPARE_DESCRIPTION,
        epilog=_COMPARE_EPILOG,
    )
    compare.add_argument("built", help="the image the host just built")
    compare.add_argument("target", help="the target image")
    compare.add_argument(
        "--range",
        action="append",
        metavar="NAME:START:END",
        help="one function's image range; repeatable. NAME:START+SIZE also works",
    )
    compare.add_argument(
        "--ranges",
        metavar="FILE",
        help="a JSON file of ranges, for a whole trial's worth of functions",
    )
    compare.add_argument("--json", action="store_true", help="emit JSON")
    compare.set_defaults(
        handler=linked_compare_command, report_command="linked-compare"
    )

    proof = commands.add_parser(
        "reloc-proof",
        help="bind fallback relocation evidence to exact final linked bytes",
        description=(
            "Compose two deliberately separate surfaces: a corroborated static "
            "relocation report with complete project-supplied identities, and an "
            "exact range in a promoted linked image. Every report and artifact "
            "is re-hashed; stale, ambiguous, or incomplete evidence is refused."
        ),
    )
    proof_mode = proof.add_mutually_exclusive_group(required=True)
    proof_mode.add_argument(
        "--fallback", metavar="REPORT", help="JSON reloc-surface report"
    )
    proof_mode.add_argument(
        "--verify", metavar="RECEIPT", help="rebuild and verify an existing receipt"
    )
    proof.add_argument("--linked", metavar="REPORT", help="JSON linked-compare report")
    proof.add_argument("--symbol", help="the exact linked range name")
    proof.add_argument("--source", help="candidate source file to bind")
    proof.add_argument("--candidate-object", help="candidate object to bind")
    proof.add_argument("--out", metavar="FILE", help="write a new receipt atomically")
    proof.add_argument("--json", action="store_true", help="emit JSON")
    proof.set_defaults(handler=relocation_proof_command, report_command="reloc-proof")


__all__ = [
    "linked_compare_command",
    "register_linked_oracle_commands",
    "reloc_surface_command",
]
