"""CLI for compiler behavioral fingerprints and cross-revision lineage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .fingerprint import (
    compare_fingerprint_reports,
    cross_rom_lineage,
    run_toolchain_fingerprint,
)


def _pairs(values: list[str], *, label: str) -> dict[str, str]:
    result = {}
    for value in values:
        name, separator, content = value.partition("=")
        if not separator or not name or not content:
            raise ValueError(f"{label} expects NAME=VALUE: {value!r}")
        if name in result:
            raise ValueError(f"{label} repeats name {name!r}")
        result[name] = content
    return result


def fingerprint_toolchain_command(args: argparse.Namespace) -> int:
    try:
        if args.compare:
            target = json.loads(Path(args.compare[0]).read_text(encoding="utf-8"))
            candidate = json.loads(Path(args.compare[1]).read_text(encoding="utf-8"))
            report = compare_fingerprint_reports(target, candidate)
        else:
            environment = _pairs(args.env, label="--env")
            if args.compile_command is None:
                raise ValueError("--compile-command is required")
            report = run_toolchain_fingerprint(
                args.compile_command,
                compile_cwd=args.compile_cwd,
                environment=environment,
                objdump=args.objdump,
                timeout=args.timeout,
                stream_limit=args.stream_limit,
                artifact_dir=args.artifact_dir,
            )
        if args.output:
            output = Path(args.output).expanduser().resolve()
            if output.exists():
                raise FileExistsError(f"refusing to overwrite report: {output}")
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("x", encoding="utf-8") as destination:
                destination.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        if args.compare:
            state = (
                "INCOMPATIBLE SUITES"
                if not report["compatible"]
                else "IDENTICAL"
                if report["identical"]
                else "DIFFERENT"
            )
            print(f"toolchain fingerprints: {state}")
            if not report["compatible"]:
                print("rebuild both reports with the same workbench microcase suite")
            for item in report["differences"]:
                print(f"{item['case']}: " + ", ".join(item["changed_features"]))
        else:
            print(f"toolchain fingerprint: {report['fingerprint']}")
            print(f"microcase suite: {report['suite']}")
            print(f"cases: {len(report['cases'])}")
            dispatch = {
                item["name"]: item["features"]["computed_jump"]
                for item in report["cases"]
                if item["name"].startswith("dense-switch-")
            }
            if dispatch:
                rendered = ", ".join(
                    f"{name.removeprefix('dense-switch-')}="
                    f"{'table' if computed else 'chain'}"
                    for name, computed in dispatch.items()
                )
                print(f"dense switch dispatch: {rendered}")
            print(f"proof: {report['proof']}")
        if args.output:
            print(f"report: {Path(args.output).expanduser().resolve()}")
    return 0


def lineage_command(args: argparse.Namespace) -> int:
    try:
        revisions = {
            label: Path(path).expanduser().resolve()
            for label, path in _pairs(args.revisions, label="revision").items()
        }
        rom_hashes = _pairs(args.rom_hash, label="--rom-hash")
        report = cross_rom_lineage(
            revisions,
            objdump=args.objdump,
            symbol=args.symbol,
            section=args.section,
            rom_hashes=rom_hashes,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"lineage: {len(report['revisions'])} revision(s), "
            f"{len(report['normalized_lineage_groups'])} normalized group(s)"
        )
        for group in report["normalized_lineage_groups"]:
            print(
                f"{group['normalized_sha256'][:12]}: " + ", ".join(group["revisions"])
            )
        if report["anomalies"]:
            print("one-revision anomalies: " + ", ".join(report["anomalies"]))
        print(f"proof: {report['proof']}")
    return 0


def register_fingerprint_commands(
    commands: argparse._SubParsersAction[Any],
) -> None:
    fingerprint = commands.add_parser(
        "fingerprint-toolchain",
        help="identify compiler/frontend behavior with redistributable microcases",
    )
    mode = fingerprint.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--compile-command",
        help="wrapper template containing {source} and {output}",
    )
    mode.add_argument(
        "--compare",
        nargs=2,
        metavar=("TARGET_JSON", "CANDIDATE_JSON"),
    )
    fingerprint.add_argument("--compile-cwd", default=".")
    fingerprint.add_argument("--env", action="append", default=[])
    fingerprint.add_argument("--objdump")
    fingerprint.add_argument("--timeout", type=float, default=120.0)
    fingerprint.add_argument("--stream-limit", type=int, default=64 * 1024)
    fingerprint.add_argument("--artifact-dir")
    fingerprint.add_argument("--output")
    fingerprint.add_argument("--json", action="store_true", help="emit JSON")
    fingerprint.set_defaults(handler=fingerprint_toolchain_command)

    lineage = commands.add_parser(
        "lineage",
        help="compare one symbol across object revisions without reading ROMs",
    )
    lineage.add_argument("revisions", nargs="+", metavar="LABEL=OBJECT")
    lineage.add_argument("--symbol", required=True)
    lineage.add_argument("--section", default=".text")
    lineage.add_argument("--objdump")
    lineage.add_argument(
        "--rom-hash",
        action="append",
        default=[],
        metavar="LABEL=SHA256",
        help="record a caller-supplied ROM identity without reading ROM data",
    )
    lineage.add_argument("--json", action="store_true", help="emit JSON")
    lineage.set_defaults(handler=lineage_command)
