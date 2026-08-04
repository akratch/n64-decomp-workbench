"""CLI for calibrated allocator-oracle planning and differential evidence."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import DEFAULT_STREAM_LIMIT
from .campaign import (
    executable_identity,
    file_sha256,
    render_compile_command,
)
from .cli_options import add_symbol_argument
from .environment import merge_toolchain_environment, parse_environment
from .globalcolor import parse_globalcolor_trace
from .instrument_uopt import parse_force_specification
from .objdump import discover_objdump
from .oracle import oracle_diff, oracle_plan, run_oracle_campaign
from .toolchain import toolchain_status


def _colors(value: str) -> list[int]:
    result = []
    for entry in value.split(","):
        text = entry.strip().lower()
        if text.startswith("c"):
            text = text[1:]
        try:
            color = int(text, 0)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"invalid color {entry!r}; use c1,c2 or 1,2"
            ) from None
        if color < 0 or color > 63:
            raise argparse.ArgumentTypeError("colors must be in c0..c63")
        result.append(color)
    if not result:
        raise argparse.ArgumentTypeError("color list must not be empty")
    return result


def _load(path: str) -> Any:
    return parse_globalcolor_trace(Path(path).read_text(encoding="utf-8"))


def oracle_plan_command(args: argparse.Namespace) -> int:
    try:
        overrides = {
            phase: values
            for phase, values in (
                ("p1", args.colors_p1),
                ("p2", args.colors_p2),
            )
            if values is not None
        }
        report = oracle_plan(
            _load(args.trace),
            proc=args.proc,
            colors=overrides,
            include_split=not args.no_split,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        p1 = report["coverage"]["p1"]
        p2 = report["coverage"]["p2"]
        print(
            f"oracle plan: p1 {p1['webs']} web(s), {p1['forces']} force(s); "
            f"p2 {p2['webs']} web(s), {p2['forces']} force(s)"
        )
        print(f"total: {report['force_count']} diagnostic force build(s)")
        attribution = report["source_attribution"]
        print(
            "source attribution: "
            f"{attribution['classification']} "
            f"({attribution['source_attributed_webs']} source-attributed, "
            f"{attribution['run_local_unattributed_webs']} run-local web(s))"
        )
        if attribution["next_gate"]:
            print(f"next gate: {attribution['next_gate']}")
        for warning in report["warnings"]:
            print(f"warning: {warning}")
        print(f"proof: {report['proof']}")
    return 0 if report["force_count"] else 1


def oracle_diff_command(args: argparse.Namespace) -> int:
    try:
        report = oracle_diff(
            _load(args.target_trace),
            _load(args.candidate_trace),
            proc=args.proc,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        semantic = report["semantic"]
        print(
            f"oracle semantic diff: {report['difference_count']} difference(s), "
            f"{len(semantic['ambiguous_fingerprints'])} ambiguous"
        )
        for row in semantic["differences"][: args.limit]:
            print(f"{row['fingerprint']} changed={','.join(row['changed'])}")
        print(f"proof: {report['proof']}")
    return 0 if report["difference_count"] else 1


@dataclass(frozen=True)
class OracleStatePaths:
    """Resolved durable state and the inputs that give it identity."""

    root: Path
    ledger: Path
    objects: Path
    report: Path
    identity: dict[str, Any]


def _state_paths(
    args: argparse.Namespace,
    plan: dict[str, Any],
    *,
    environment: dict[str, str],
) -> OracleStatePaths:
    source = Path(args.source).expanduser().resolve()
    target = Path(args.target).expanduser().resolve()
    toolchain = toolchain_status(args.toolchain)
    compile_cwd = (
        Path(args.compile_cwd).expanduser().resolve()
        if args.compile_cwd
        else Path.cwd().resolve()
    )
    compiler_command = render_compile_command(
        args.compile_command,
        source,
        Path("__ORACLE_OUTPUT__"),
    )
    objdump = discover_objdump(args.objdump)
    identity = {
        "source": {"path": str(source), "sha256": file_sha256(source)},
        "target": {"path": str(target), "sha256": file_sha256(target)},
        "toolchain": {
            "directory": toolchain["directory"],
            "manifest_sha256": toolchain["manifest_sha256"],
        },
        "compile_command": args.compile_command,
        "compiler": executable_identity(compiler_command, cwd=compile_cwd),
        "compile_cwd": str(compile_cwd),
        "environment": dict(sorted(environment.items())),
        "objdump": executable_identity([objdump], cwd=compile_cwd),
        "symbol": args.symbol,
        "section": args.section,
        "plan": plan,
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    label = args.symbol or target.stem
    safe = "".join(character if character.isalnum() else "-" for character in label)
    safe = safe.strip("-")[:48] or "oracle"
    root = (
        Path(args.state_dir).expanduser().resolve() / "oracle" / f"{safe}-{digest[:12]}"
    )
    ledger = (
        Path(args.ledger).expanduser().resolve()
        if args.ledger
        else root / "ledger.jsonl"
    )
    objects = (
        Path(args.objects_dir).expanduser().resolve()
        if args.objects_dir
        else root / "objects"
    )
    return OracleStatePaths(
        root=root,
        ledger=ledger,
        objects=objects,
        report=root / "report.json",
        identity=identity,
    )


def _write_state_report(path: Path, report: dict[str, Any]) -> None:
    """Atomically refresh derived oracle status inside its owned state tree."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _find_state_report(
    selector: str | None,
    *,
    state_dir: str,
) -> Path:
    if selector is not None:
        selected = Path(selector).expanduser().resolve()
        report = selected / "report.json" if selected.is_dir() else selected
        if not report.is_file():
            raise FileNotFoundError(f"oracle report does not exist: {report}")
        return report
    root = Path(state_dir).expanduser().resolve() / "oracle"
    reports = list(root.glob("*/report.json")) if root.is_dir() else []
    if not reports:
        raise FileNotFoundError(f"no oracle report found under {root}")
    return max(reports, key=lambda path: path.stat().st_mtime)


def _load_state_report(selector: str | None, *, state_dir: str) -> dict[str, Any]:
    path = _find_state_report(selector, state_dir=state_dir)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != (
        "decomp-workbench-oracle-sweep-v1"
    ):
        raise ValueError(f"not a decomp-workbench oracle sweep report: {path}")
    return value


def _plan_for_compile(args: argparse.Namespace) -> dict[str, Any]:
    overrides = {
        phase: values
        for phase, values in (
            ("p1", args.colors_p1),
            ("p2", args.colors_p2),
        )
        if values is not None
    }
    plan = oracle_plan(
        _load(args.trace),
        proc=args.proc,
        colors=overrides,
        include_split=not args.no_split,
    )
    if getattr(args, "force", None):
        entries = parse_force_specification(args.force)
        if len(entries) != 1:
            raise ValueError("oracle force accepts exactly one phase-qualified force")
        selected = [row for row in plan["forces"] if row["force"] == args.force]
        if not selected:
            raise ValueError(
                f"{args.force} is absent from the measured plan; it may be "
                "forbidden or outside the selected color set"
            )
        plan = {
            **plan,
            "forces": selected,
            "force_count": 1,
            "restriction": args.force,
        }
    return plan


def _render_sweep(report: dict[str, Any], *, limit: int) -> None:
    baseline = report["baseline"]
    baseline_comparison = (
        baseline.get("comparison") if isinstance(baseline, dict) else None
    )
    baseline_words = (
        baseline_comparison.get("words")
        if isinstance(baseline_comparison, dict)
        else "failed"
    )
    print(
        f"oracle: {report['completed_forces']}/{report['planned_forces']} "
        f"force(s), baseline words={baseline_words}"
    )
    causal_exact = set(report.get("exact_forces", []))
    for row in report["results"][:limit]:
        comparison = row["comparison"]
        if isinstance(comparison, dict):
            register = f"({row['register']})" if row["register"] else ""
            if row["force"] in causal_exact:
                note = " EXACT UNDER FORCE"
            elif comparison["exact"]:
                note = " EXACT; NOT CAUSAL WITHOUT A NON-EXACT CONTROL"
            else:
                note = ""
            print(
                f"{row['force']}{register} words={comparison['words']} "
                f"aligned={comparison['aligned_total']} "
                f"register={comparison['aligned_register']}{note}"
            )
        else:
            print(f"{row['force']} FAILED returncode={row['returncode']}")
    if len(report["results"]) > limit:
        print(f"... {len(report['results']) - limit} more result(s); use --json")
    if report["signature"]:
        print(f"verdict-signature: {report['signature']}")
    for warning in report.get("warnings", []):
        print(f"warning: {warning}")
    print(f"proof: {report['proof']}")
    # A winning force is evidence about the allocator, not a patch. The
    # translation back into C is exactly what the coloring-pool levers are,
    # so name the command that prints them rather than leaving "source-level
    # lifetime hypothesis" as an exercise.
    print(
        "next: translate the winning force into a source-level lifetime or "
        "priority hypothesis; never ship the forced compiler"
    )
    print("      the source forms that move a coloring decision, in order:")
    print("      decomp-workbench guide pool-position")
    print("      decomp-workbench guide forced-color-oracle")


def oracle_sweep_command(args: argparse.Namespace) -> int:
    try:
        plan = _plan_for_compile(args)
        environment = merge_toolchain_environment(
            parse_environment(args.env),
            args.toolchain,
            require_ready=True,
        )
        state = _state_paths(args, plan, environment=environment)
        report = run_oracle_campaign(
            plan,
            source=args.source,
            target=args.target,
            template=args.compile_command,
            environment=environment,
            cache_dir=args.cache_dir,
            ledger=state.ledger,
            jobs=args.jobs,
            objdump=args.objdump,
            symbol=args.symbol,
            section=args.section,
            compile_cwd=args.compile_cwd,
            keep_objects=None if args.no_keep_objects else state.objects,
            timeout=args.timeout,
            stream_limit=args.stream_limit,
            artifact_dir=args.artifact_dir,
        )
        report = {
            **report,
            "inputs": state.identity,
            "state": {
                "directory": str(state.root),
                "report": str(state.report),
                "ledger": str(state.ledger),
                "objects": (None if args.no_keep_objects else str(state.objects)),
                "updated_at_unix": time.time(),
            },
        }
        _write_state_report(state.report, report)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _render_sweep(report, limit=args.limit)
        print(f"state: {state.root}")
        print(f"ledger: {state.ledger}")
        if not args.no_keep_objects:
            print(f"objects: {state.objects}")
    return (
        0
        if report["control_valid"]
        and any(row["comparison"] for row in report["results"])
        else 1
    )


def oracle_status_command(args: argparse.Namespace) -> int:
    try:
        report = _load_state_report(args.oracle_state, state_dir=args.state_dir)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _render_sweep(report, limit=args.limit)
        state = report.get("state", {})
        if isinstance(state, dict):
            print(f"state: {state.get('directory')}")
            print(f"ledger: {state.get('ledger')}")
    return 0


def _render_oracle_html(report: dict[str, Any]) -> str:
    rows = []
    causal_exact = set(report.get("exact_forces", []))
    for result in report["results"]:
        comparison = result.get("comparison")
        status = "failed"
        words = "—"
        aligned = "—"
        if isinstance(comparison, dict):
            status = (
                "exact under force"
                if result["force"] in causal_exact
                else "exact; control unavailable or already exact"
                if comparison["exact"]
                else "measured"
            )
            words = str(comparison["words"])
            aligned = str(comparison["aligned_total"])
        rows.append(
            "<tr>"
            f"<td><code>{html.escape(str(result['force']))}</code></td>"
            f"<td>{html.escape(str(result.get('register') or '—'))}</td>"
            f"<td>{html.escape(words)}</td>"
            f"<td>{html.escape(aligned)}</td>"
            f"<td>{html.escape(status)}</td>"
            "</tr>"
        )
    serialized = html.escape(json.dumps(report, indent=2, sort_keys=True))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>decomp-workbench oracle report</title>
<style>
:root {{ color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }}
body {{ max-width: 76rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #8886; padding: .45rem; text-align: left; }}
code, pre {{ font-family: ui-monospace, monospace; }}
pre {{ overflow: auto; padding: 1rem; background: #8881; }}
.proof {{ border-left: .25rem solid #a86; padding-left: 1rem; }}
</style>
</head>
<body>
<h1>Allocator oracle evidence</h1>
<p>{int(report["completed_forces"])}/{int(report["planned_forces"])} force(s);
signature: <strong>{html.escape(str(report.get("signature") or "none"))}</strong>.</p>
<p class="proof">{html.escape(str(report["proof"]))}</p>
<table>
<thead><tr><th>Force</th><th>Register</th><th>Words</th><th>Aligned</th><th>Evidence</th></tr></thead>
<tbody>{"".join(rows) or '<tr><td colspan="5">No force results.</td></tr>'}</tbody>
</table>
<details><summary>Machine-readable evidence</summary><pre>{serialized}</pre></details>
</body>
</html>
"""


def oracle_export_command(args: argparse.Namespace) -> int:
    try:
        report = _load_state_report(args.oracle_state, state_dir=args.state_dir)
        output = Path(args.output).expanduser().resolve()
        if output.exists():
            raise FileExistsError(f"refusing to overwrite oracle export: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        content = (
            _render_oracle_html(report)
            if args.format == "html"
            else json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        with output.open("x", encoding="utf-8") as destination:
            destination.write(content)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    result = {
        "schema": "decomp-workbench-oracle-export-v1",
        "format": args.format,
        "output": str(output),
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"oracle {args.format} export: {output}")
    return 0


def _add_compile_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source")
    parser.add_argument("--trace", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--toolchain", required=True)
    parser.add_argument("--compile-command", required=True)
    add_symbol_argument(parser)
    parser.add_argument("--section", default=".text")
    parser.add_argument("--objdump")
    parser.add_argument("--proc", type=int)
    parser.add_argument("--colors-p1", type=_colors)
    parser.add_argument("--colors-p2", type=_colors)
    parser.add_argument("--no-split", action="store_true")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
    )
    parser.add_argument("--compile-cwd")
    parser.add_argument("--jobs", type=int, default=max(1, min(8, os.cpu_count() or 1)))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--cache-dir", default=".decomp-workbench/cache")
    parser.add_argument("--state-dir", default=".decomp-workbench")
    parser.add_argument("--ledger")
    parser.add_argument("--objects-dir")
    parser.add_argument(
        "--no-keep-objects",
        action="store_true",
        help="do not retain forced objects (retained by default)",
    )
    parser.add_argument("--stream-limit", type=int, default=DEFAULT_STREAM_LIMIT)
    parser.add_argument("--artifact-dir")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="emit JSON")


def register_oracle_commands(
    commands: argparse._SubParsersAction[Any],
) -> None:
    parser = commands.add_parser(
        "oracle",
        help="plan and compare calibrated allocator decision probes",
        description=(
            "Oracle evidence bounds a compiler decision; it never proves "
            "source originality or an acceptable final match."
        ),
    )
    operations = parser.add_subparsers(dest="oracle_command", required=True)

    plan = operations.add_parser(
        "plan",
        help="build a phase-complete force grid from one allocator trace",
    )
    plan.add_argument("trace")
    plan.add_argument("--proc", type=int)
    plan.add_argument("--colors-p1", type=_colors)
    plan.add_argument("--colors-p2", type=_colors)
    plan.add_argument(
        "--no-split",
        action="store_true",
        help="omit the diagnostic split/no-color endpoint",
    )
    plan.add_argument("--json", action="store_true", help="emit JSON")
    plan.set_defaults(handler=oracle_plan_command, report_command="oracle-plan")

    diff = operations.add_parser(
        "diff",
        help="compare two traces by stable web provenance",
    )
    diff.add_argument("target_trace")
    diff.add_argument("candidate_trace")
    diff.add_argument("--proc", type=int)
    diff.add_argument("--limit", type=int, default=50)
    diff.add_argument("--json", action="store_true", help="emit JSON")
    diff.set_defaults(handler=oracle_diff_command, report_command="oracle-diff")

    sweep = operations.add_parser(
        "sweep",
        help="compile the complete measured force grid through the campaign engine",
    )
    _add_compile_arguments(sweep)
    sweep.set_defaults(handler=oracle_sweep_command, report_command="oracle-sweep")

    force = operations.add_parser(
        "force",
        help="run one measured causal force plus its unforced baseline",
    )
    _add_compile_arguments(force)
    force.add_argument(
        "--force",
        required=True,
        help="one phase-qualified control such as p2:w55=c2",
    )
    force.set_defaults(handler=oracle_sweep_command, report_command="oracle-sweep")

    status = operations.add_parser(
        "status",
        help="render the latest persisted sweep without recompiling",
    )
    status.add_argument("oracle_state", nargs="?", help="state directory or report")
    status.add_argument("--state-dir", default=".decomp-workbench")
    status.add_argument("--limit", type=int, default=20)
    status.add_argument("--json", action="store_true", help="emit JSON")
    status.set_defaults(handler=oracle_status_command, report_command="oracle-status")

    export = operations.add_parser(
        "export",
        help="write a self-contained persisted oracle report",
    )
    export.add_argument("oracle_state", nargs="?", help="state directory or report")
    export.add_argument("--state-dir", default=".decomp-workbench")
    export.add_argument("--output", required=True)
    export.add_argument("--format", choices=("html", "json"), default="html")
    export.add_argument("--json", action="store_true", help="emit result JSON")
    export.set_defaults(handler=oracle_export_command, report_command="oracle-export")
