"""Command-line interface for decomp-workbench."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

from . import __version__
from .agent_skill import install_agent_skill
from .allocator_cli import register_allocator_commands
from .artifacts import capture_streams
from .cache_cli import register_cache_commands
from .campaign import (
    Candidate,
    CompilerTimeoutError,
    executable_identity,
    file_sha256,
    group_object_basins,
    prepare_candidates,
    run_campaign,
    run_compiler,
)
from .campaign import render_compile_command as render_campaign_command
from .campaign_cli import register_campaign_cockpit_commands
from .campaign_registration import register_campaign_run_commands
from .campaign_state import (
    campaign_identity,
    finish_manifest,
    initialize_manifest,
)
from .cli_options import (
    SYMBOL_OPTION_DEST,
    add_explain_keys_argument,
    add_process_output_arguments,
)
from .compare import compare_instructions, compare_objects
from .comparison_render import comparison_line as comparison_line
from .comparison_render import (
    comparison_payload,
)
from .context_lint_cli import register_context_commands
from .diagnose_cli import register_diagnose_commands
from .diagnosis import diagnose_instructions, diagnose_objects
from .discovery import (
    CommandParser,
    finalize_command_help,
    register_discovery_commands,
    rewrite_group_alias,
)
from .environment import merge_toolchain_environment
from .environment import parse_environment as parse_environment
from .experiment_cli import register_experiment_commands
from .experiments import load_experiment, validate_campaign_sources
from .fidelity_cli import register_fidelity_command
from .fingerprint_cli import register_fingerprint_commands
from .globalcolor import (
    optional_integer,
    parse_globalcolor_trace,
    register_for_color,
)
from .guide_cli import register_guide_command
from .instrument import instrument_ugen
from .instrument_alias import instrument_uopt_alias
from .instrument_profiles import (
    SUPPORTED_PROFILES,
    instrument_uopt_profiles,
)
from .instrument_uopt import instrument_uopt_globalcolor
from .model import Comparison, CompileResult, display_path
from .objdump import discover_objdump, dump_object, parse_disassembly
from .object_cli import (
    compare_command,
    compare_dumps_command,
    print_comparison_explanation,
    print_diff_sites,
    rank_command,
    register_object_commands,
    register_rank_command,
)
from .oracle_cli import register_oracle_commands
from .pass_adapter_cli import register_pass_adapter_command
from .pass_replay import ListingEdit, replay_as1
from .preflight import compile_preflight
from .relocation_cli import register_relocation_command
from .reporting import SCHEMAS, error_report, render_json, run_json_handler
from .scheduler_cli import register_scheduler_commands
from .schema import selected_fields
from .scratch_bundle import bundle_scratch
from .scratch_check import (
    ScratchPackage,
    compose_site_source,
    load_scratch,
    scratch_context_hardening,
    scratch_score,
)
from .scratch_registration import register_scratch_commands
from .source_correlation_cli import register_source_correlation_command
from .toolchain import toolchain_status
from .toolchain_cli import register_toolchain_commands
from .trace import (
    alias_trace_summary,
    parse_integer,
    parse_register,
    parse_trace,
    register_name,
    replay_fifo,
    trace_summary,
)
from .view import MechanismView
from .view_cli import (
    Painter,
    register_view_commands,
    render_view,
    resolve_color,
)

# Ranking metrics kept in `campaign --json-summary`: no compiler streams, no
# instruction-level evidence.
CAMPAIGN_SUMMARY_KEYS = (
    "exact",
    "verdict",
    "structural_exact",
    "aligned_total",
    "aligned_structural",
    "aligned_schedule",
    "aligned_register",
    "aligned_constant",
    "aligned_commutative",
    "words",
    "raw",
    "norm",
    "opcodes",
    "regs",
    "fp",
    "target_insns",
    "insns",
    "insn_delta",
    "target_frame",
    "frame",
    "sha1",
    "sha256",
)


class ScratchCompileFailure(RuntimeError):
    """A site-faithful compile failed after producing reproducibility evidence."""

    def __init__(self, message: str, report: dict[str, object]) -> None:
        super().__init__(message)
        self.report = report


def bundle_scratch_command(args: argparse.Namespace) -> int:
    try:
        result = bundle_scratch(
            args.output,
            target_assembly=args.target_assembly,
            context=args.context,
            source=args.source,
            platform=args.platform,
            compiler=args.compiler,
            compiler_flags=args.compiler_flags,
            diff_label=args.diff_label,
            project=args.project,
            preset=args.preset,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result.manifest, indent=2, sort_keys=True))
    else:
        print(f"scratch bundle: {result.output}")
    return 0


def _scratch_comparison(
    package: ScratchPackage,
    args: argparse.Namespace,
    workspace: Path,
) -> tuple[
    Comparison | None,
    MechanismView | None,
    dict[str, object] | None,
    str,
]:
    """Compile when requested, then select the strongest bundled evidence."""

    symbol = args.symbol
    metadata_symbol = package.metadata.get("diff_label")
    if symbol is None and isinstance(metadata_symbol, str):
        symbol = metadata_symbol

    compile_report: dict[str, object] | None = None
    candidate_object: Path | None = None
    if args.compile_command:
        if package.kind != "decomp.me-export":
            raise ValueError("site-faithful compilation requires a decomp.me export")
        if "target.o" not in package.files:
            raise ValueError("site-faithful compilation needs target.o in the export")
        composed = workspace / "site-source.c"
        composed.write_bytes(compose_site_source(package, args.source).encode("utf-8"))
        output = workspace / "compiled.o"
        command = render_compile_command(args.compile_command, composed, output)
        environment = parse_environment(args.env)
        compile_cwd = (
            Path(args.compile_cwd).expanduser().resolve()
            if args.compile_cwd
            else Path.cwd().resolve()
        )
        if not compile_cwd.is_dir():
            raise ValueError(
                f"compile working directory is not a directory: {compile_cwd}"
            )
        started = time.monotonic()
        try:
            process = run_compiler(
                command,
                compile_cwd=compile_cwd,
                environment=environment,
                timeout=args.timeout,
            )
        except CompilerTimeoutError as error:
            streams = capture_streams(
                error.stdout,
                error.stderr,
                limit=args.stream_limit,
                artifact_dir=args.artifact_dir,
                stem="scratch-compile",
            )
            timeout_report: dict[str, object] = {
                "command": command,
                "returncode": 124,
                "stdout": streams.stdout,
                "stderr": streams.stderr,
                "stdout_bytes": streams.stdout_bytes,
                "stderr_bytes": streams.stderr_bytes,
                "stdout_truncated": streams.stdout_truncated,
                "stderr_truncated": streams.stderr_truncated,
                "artifacts": streams.artifacts,
                "duration_seconds": time.monotonic() - started,
                "working_directory": str(compile_cwd),
                "explicit_environment": environment,
                "compiler": executable_identity(command, cwd=compile_cwd),
                "timeout_seconds": args.timeout,
                "source": "override" if args.source else "exported code.c",
                "composed_source_sha256": file_sha256(composed),
                "site_line_reset": '#line 1 "src.c"',
            }
            raise ScratchCompileFailure(str(error), timeout_report) from error
        compile_report = {
            "command": command,
            "returncode": process.returncode,
            "duration_seconds": time.monotonic() - started,
            "working_directory": str(compile_cwd),
            "explicit_environment": environment,
            "compiler": executable_identity(command, cwd=compile_cwd),
            "timeout_seconds": args.timeout,
            "source": "override" if args.source else "exported code.c",
            "composed_source_sha256": file_sha256(composed),
            "site_line_reset": '#line 1 "src.c"',
        }
        streams = capture_streams(
            process.stdout,
            process.stderr,
            limit=args.stream_limit,
            artifact_dir=args.artifact_dir,
            stem="scratch-compile",
        )
        compile_report.update(
            {
                "stdout": streams.stdout,
                "stderr": streams.stderr,
                "stdout_bytes": streams.stdout_bytes,
                "stderr_bytes": streams.stderr_bytes,
                "stdout_truncated": streams.stdout_truncated,
                "stderr_truncated": streams.stderr_truncated,
                "artifacts": streams.artifacts,
            }
        )
        if process.returncode:
            detail = streams.stderr.strip() or streams.stdout.strip()
            raise ScratchCompileFailure(
                f"compiler failed with exit {process.returncode}: "
                f"{detail or 'no diagnostic'}",
                compile_report,
            )
        if not output.is_file():
            raise RuntimeError(f"compiler succeeded but did not create {output}")
        candidate_object = output
        if args.keep_composed:
            destination = Path(args.keep_composed).expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(composed, destination)
            compile_report["retained_source"] = str(destination)
        if args.keep_object:
            destination = Path(args.keep_object).expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(output, destination)
            compile_report["retained_object"] = str(destination)

    if candidate_object is not None:
        target_object = package.materialize("target.o", workspace)
        view = None
        if args.view:
            diagnosis = diagnose_objects(
                target_object,
                candidate_object,
                objdump=args.objdump,
                symbol=symbol,
                section=args.section,
                register_profile=args.register_profile,
            )
            comparison = diagnosis.comparison
            view = diagnosis.view
        else:
            comparison = compare_objects(
                target_object,
                candidate_object,
                objdump=args.objdump,
                symbol=symbol,
                section=args.section,
            )
        comparison.target = f"{display_path(package.path)}:target.o"
        comparison.candidate = (
            display_path(args.source)
            if args.source
            else f"{display_path(package.path)}:code.c"
        )
        return (
            comparison,
            view,
            compile_report,
            "compiled-site-source-vs-target-object",
        )

    if {"target.o", "current.o"} <= package.files.keys():
        target_object = package.materialize("target.o", workspace)
        current_object = package.materialize("current.o", workspace)
        view = None
        if args.view:
            diagnosis = diagnose_objects(
                target_object,
                current_object,
                objdump=args.objdump,
                symbol=symbol,
                section=args.section,
                register_profile=args.register_profile,
            )
            comparison = diagnosis.comparison
            view = diagnosis.view
        else:
            comparison = compare_objects(
                target_object,
                current_object,
                objdump=args.objdump,
                symbol=symbol,
                section=args.section,
            )
        comparison.target = f"{display_path(package.path)}:target.o"
        comparison.candidate = f"{display_path(package.path)}:current.o"
        return comparison, view, compile_report, "exported-objects"

    dump_pair = next(
        (
            pair
            for pair in (
                ("target.objdump", "current.objdump"),
                ("target.objdump", "candidate.objdump"),
            )
            if set(pair) <= package.files.keys()
        ),
        None,
    )
    if dump_pair is not None:
        target = parse_disassembly(package.text(dump_pair[0]), symbol=symbol)
        candidate = parse_disassembly(package.text(dump_pair[1]), symbol=symbol)
        if not target or not candidate:
            detail = f" for symbol {symbol!r}" if symbol else ""
            raise ValueError(
                "both retained dumps must contain GNU-style objdump "
                f"instruction lines{detail}"
            )
        target_name = f"{display_path(package.path)}:{dump_pair[0]}"
        candidate_name = f"{display_path(package.path)}:{dump_pair[1]}"
        view = None
        if args.view:
            diagnosis = diagnose_instructions(
                target,
                candidate,
                target_name=target_name,
                candidate_name=candidate_name,
                symbol=symbol,
                register_profile=args.register_profile,
            )
            comparison = diagnosis.comparison
            view = diagnosis.view
        else:
            comparison = compare_instructions(
                target,
                candidate,
                target_name=target_name,
                candidate_name=candidate_name,
                symbol=symbol,
            )
        return comparison, view, compile_report, "retained-objdump-text"
    return None, None, compile_report, "no-comparable-object-or-dump-pair"


def _scratch_next_actions(
    package: ScratchPackage,
    comparison: Comparison | None,
    evidence: str,
) -> list[str]:
    if comparison is not None and comparison.exact:
        return [
            "Run the project's normal link/ROM and collateral verification; "
            "function exactness is not whole-project proof."
        ]
    if comparison is not None:
        return list(comparison.guidance)
    if package.kind == "workbench-bundle":
        return [
            "Create the scratch manually from README.md; the checksums are valid.",
            "Download a decomp.me export afterward and run check-scratch on it.",
        ]
    if evidence == "no-comparable-object-or-dump-pair":
        return [
            "Export target.o/current.o from decomp.me, or add "
            "target.objdump/current.objdump for a compiler-free comparison.",
            "Pass --compile-command to verify code.c with decomp.me's line-reset "
            "semantics when target.o is present.",
        ]
    return []


def check_scratch_command(args: argparse.Namespace) -> int:
    """Inspect an export and report decomp.me context beside workbench truth."""

    if args.source and not args.compile_command:
        print("error: --source requires --compile-command", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("error: --timeout must be positive", file=sys.stderr)
        return 2
    if args.stream_limit < 0:
        print("error: --stream-limit must be non-negative", file=sys.stderr)
        return 2
    try:
        package = load_scratch(args.scratch)
        with tempfile.TemporaryDirectory(prefix="decomp-workbench-scratch-") as temp:
            comparison, view, compile_report, evidence = _scratch_comparison(
                package,
                args,
                Path(temp),
            )
    except ScratchCompileFailure as error:
        if args.json:
            report = error_report(
                "check-scratch",
                status=2,
                stage="compile",
                message=str(error),
                details={"returncode": error.report.get("returncode")},
            )
            report["compile"] = error.report
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(f"error: {error}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    score = (
        scratch_score(package.metadata) if package.kind == "decomp.me-export" else None
    )
    actions = _scratch_next_actions(package, comparison, evidence)
    hardening = scratch_context_hardening(package)
    scratch_payload: dict[str, object] = {
        "path": display_path(package.path),
        "kind": package.kind,
        "files": sorted(package.files),
        "metadata": package.public_metadata(),
        "checksums_valid": package.checksums_valid,
    }
    payload: dict[str, object] = {
        "schema": "decomp-workbench-scratch-check-v1",
        "scratch": scratch_payload,
        "external_score": score,
        "evidence": evidence,
        "source_semantics": {
            "site_faithful": bool(args.compile_command),
            "line_reset": '#line 1 "src.c"' if args.compile_command else None,
        },
        "context_hardening": hardening,
        "comparison": (
            comparison_payload(comparison, cross_rom=False)
            if comparison is not None
            else None
        ),
        "view": (
            view.as_dict(report_regs=args.report_regs) if view is not None else None
        ),
        "compile": compile_report,
        "next_actions": actions,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"scratch: {package.kind} ({display_path(package.path)})")
        metadata = package.public_metadata()
        identity = metadata.get("name") or metadata.get("project")
        slug = metadata.get("slug")
        if identity or slug:
            parts = [str(value) for value in (identity, slug) if value]
            print("identity: " + " / ".join(parts))
        print("files: " + ", ".join(sorted(package.files)))
        if package.checksums_valid:
            print("integrity: PASS (all workbench bundle checksums)")
        if hardening["applicable"]:
            if hardening["context_newline_warning"]:
                print(f"warning: {hardening['context_newline_warning']}")
            for duplicate in hardening["duplicate_symbols"]:
                print(
                    f"warning: {duplicate['symbol']} is defined in both ctx.c "
                    f"(line {duplicate['ctx_line']}) and code.c "
                    f"(line {duplicate['code_line']}); keep the file-scope "
                    "definition in exactly one of them"
                )
            lint_findings = hardening["context_lint"]["findings"]
            if lint_findings:
                print(
                    f"context lint: {len(lint_findings)} finding(s) in "
                    "ctx.c/code.c"
                )
                for finding in lint_findings:
                    print(
                        f"  [{finding['severity'].upper()}] {finding['kind']} "
                        f"{finding['source']}:{finding['line']}  "
                        f"#{finding['directive']} {finding['expression']}"
                    )
                    print(f"    do: {finding['action']}")
            else:
                print(
                    "context lint: no undefined-identifier collapse found in "
                    "ctx.c/code.c"
                )
        if score is not None:
            print(
                "decomp.me display: "
                f"score={score['score']:g}/{score['max_score']:g} "
                f"({score['percentage']:.5f}%; context only)"
            )
        print(f"evidence: {evidence}")
        if args.compile_command:
            print(
                'source composition: site-faithful (inserted #line 1 "src.c" '
                "between ctx.c and candidate source)"
            )
        if comparison is None:
            print("comparison: unavailable")
        else:
            print(comparison_line(comparison))
            if view is None:
                print_comparison_explanation(comparison, cross_rom=False)
            if args.show_diff:
                print_diff_sites(comparison)
            if view is not None:
                print("")
                for line in render_view(
                    view,
                    context=args.context,
                    max_hunks=0 if args.show_all else args.max_hunks,
                    lane_window=(
                        max(view.target_instructions, view.candidate_instructions)
                        if args.show_all
                        else args.lane_window
                    ),
                    report_regs=args.report_regs,
                    painter=Painter(resolve_color(args.color)),
                ):
                    print(line)
        # A comparison already rendered its own guidance above. The action
        # list remains in JSON as the machine-readable equivalent, while the
        # terminal gets only genuinely additional handoff steps.
        if comparison is None:
            for action in actions:
                print(f"next: {action}")
    mismatch = comparison is None or not comparison.exact
    return 1 if args.fail_on_mismatch and mismatch else 0


def doctor_command(args: argparse.Namespace) -> int:
    """Explain local readiness and validate an optional scratch handoff."""

    objdump_path: str | None = None
    objdump_error: str | None = None
    objdump_version: str | None = None
    try:
        objdump_path = discover_objdump(args.objdump)
        version = subprocess.run(
            [objdump_path, "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
        lines = (version.stdout or version.stderr).splitlines()
        objdump_version = lines[0].strip() if lines else None
    except FileNotFoundError as error:
        objdump_error = str(error)
    except (OSError, subprocess.TimeoutExpired) as error:
        objdump_error = f"could not query objdump: {error}"
        objdump_path = None

    package: ScratchPackage | None = None
    if args.scratch:
        try:
            package = load_scratch(args.scratch)
        except (OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2

    object_required = bool(package and "target.o" in package.files)
    object_verified = False
    if package and objdump_path and "target.o" in package.files:
        symbol_value = package.metadata.get("diff_label")
        symbol = symbol_value if isinstance(symbol_value, str) else None
        try:
            with tempfile.TemporaryDirectory(
                prefix="decomp-workbench-doctor-"
            ) as temporary:
                target = package.materialize("target.o", Path(temporary))
                dump_object(target, objdump=objdump_path, symbol=symbol)
            object_verified = True
        except (OSError, RuntimeError) as error:
            objdump_error = f"object reader failed the supplied target.o: {error}"

    cache = Path(args.cache_dir).expanduser().resolve()
    cache_files: list[Path] = []
    cache_error: str | None = None
    try:
        if cache.is_dir():
            cache_files = [item for item in cache.rglob("*") if item.is_file()]
        cache_bytes = sum(item.stat().st_size for item in cache_files)
    except OSError as error:
        cache_bytes = 0
        cache_error = str(error)
    cache_large = cache_bytes >= 1024 * 1024 * 1024
    object_status = (
        "verified"
        if object_verified
        else "detected"
        if objdump_path and not object_required
        else "limited"
    )
    preflight: dict[str, object] | None = None
    toolchain: dict[str, object] | None = None
    if args.toolchain:
        try:
            toolchain = toolchain_status(args.toolchain)
        except (OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
    if args.compile_command:
        try:
            environment = parse_environment(args.env)
            if args.toolchain:
                environment = merge_toolchain_environment(
                    environment,
                    args.toolchain,
                )
            compile_cwd = (
                Path(args.compile_cwd).expanduser().resolve()
                if args.compile_cwd
                else Path.cwd().resolve()
            )
            preflight = compile_preflight(
                args.compile_command,
                compile_cwd=compile_cwd,
                environment=environment,
                timeout=args.timeout,
                objdump=objdump_path,
                stream_limit=args.stream_limit,
                artifact_dir=args.artifact_dir,
            )
        except (OSError, RuntimeError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
    payload: dict[str, object] = {
        "schema": "decomp-workbench-doctor-v1",
        "workbench_version": __version__,
        "python": ".".join(str(item) for item in sys.version_info[:3]),
        "python_supported": sys.version_info >= (3, 10),
        "working_directory": str(Path.cwd().resolve()),
        "cache": {
            "path": display_path(cache),
            "exists": cache.is_dir(),
            "files": len(cache_files),
            "bytes": cache_bytes,
            "large": cache_large,
            "error": cache_error,
        },
        "dump_workflow": "ready",
        "object_workflow": {
            "status": object_status,
            "objdump": objdump_path,
            "version": objdump_version,
            "error": objdump_error,
        },
        "scratch": (
            {
                "path": display_path(package.path),
                "kind": package.kind,
                "files": sorted(package.files),
                "checksums_valid": package.checksums_valid,
            }
            if package
            else None
        ),
        "compile_preflight": preflight,
        "toolchain": toolchain,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"decomp-workbench {__version__}")
        python_status = "READY" if payload["python_supported"] else "UNSUPPORTED"
        print(f"Python {payload['python']}: {python_status}")
        print("retained objdump workflow: READY (no compiler or object reader needed)")
        if object_status == "verified":
            print(f"object workflow: VERIFIED ({objdump_path})")
        elif object_status == "detected":
            print(f"object workflow: DETECTED ({objdump_path})")
            print("object format support: checked when the first object is read")
        else:
            print("object workflow: LIMITED")
            print(f"  {objdump_error}")
        cache_label = "UNREADABLE" if cache_error else "LARGE" if cache_large else "OK"
        print(
            f"campaign cache: {cache_label} - {len(cache_files)} file(s), "
            f"{cache_bytes} byte(s) ({display_path(cache)})"
        )
        if cache_error:
            print(f"  error: {cache_error}")
        if cache_large:
            print(
                "  note: inspect this content cache before pruning it; "
                "doctor never deletes campaign evidence"
            )
        if package:
            print(f"scratch: VALID ({package.kind}; {len(package.files)} file(s))")
            command = ["decomp-workbench", "check-scratch", str(package.path)]
            if args.objdump:
                command.extend(["--objdump", args.objdump])
            print(f"next: {shlex.join(command)}")
        if preflight:
            label = "READY" if preflight["ready"] else "FAILED"
            print(
                f"compiler preflight: {label} "
                f"({preflight['status']}, {preflight['duration_seconds']:.2f}s)"
            )
            if not preflight["ready"]:
                diagnostic = str(preflight.get("stderr", "")).strip().splitlines()
                if diagnostic:
                    print(f"  {diagnostic[-1]}")
        if toolchain:
            print(
                f"toolchain: {str(toolchain['claim']).upper()} "
                f"(integrity={'PASS' if toolchain['integrity'] else 'FAIL'})"
            )
            missing = toolchain["next_missing_gates"]
            if isinstance(missing, list) and missing:
                print("  missing gates: " + ", ".join(str(item) for item in missing))
    return (
        1
        if (object_required and not object_verified)
        or cache_error
        or (preflight is not None and not preflight["ready"])
        or (
            toolchain is not None
            and (not bool(toolchain["integrity"]) or toolchain["claim"] != "ready")
        )
        else 0
    )


def install_skill_command(args: argparse.Namespace) -> int:
    """Install the bundled Agent Skill for one supported client."""

    try:
        path, status = install_agent_skill(
            args.client,
            destination=args.destination,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    invocation = (
        "$n64-decomp-campaign" if args.client == "codex" else "/n64-decomp-campaign"
    )
    payload = {
        "client": args.client,
        "invocation": invocation,
        "path": str(path),
        "status": status,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        label = "installed" if status == "installed" else "already current"
        print(f"skill {label}: {path}")
        print(f"invoke with: {invocation}")
    return 0


def render_compile_command(template: str, source: Path, output: Path) -> list[str]:
    """Render a compiler command without invoking a shell."""

    return render_campaign_command(template, source, output)


def compile_rank_command(args: argparse.Namespace) -> int:
    """Compatibility ranking surface backed by the campaign engine."""

    try:
        environment = parse_environment(args.env)
        if args.toolchain:
            environment = merge_toolchain_environment(environment, args.toolchain)
        results, _ = run_campaign(
            args.sources,
            target=args.target,
            template=args.compile_command,
            cache_dir=args.cache_dir,
            objdump=args.objdump,
            symbol=args.symbol,
            section=args.section,
            environment=environment,
            compile_cwd=args.compile_cwd,
            keep_objects=args.keep_objects,
            stop_on_exact=False,
            timeout=args.timeout,
            stream_limit=args.stream_limit,
            artifact_dir=args.artifact_dir,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    successes = [
        (item, item.comparison) for item in results if item.comparison is not None
    ]
    successes.sort(key=lambda item: item[1].sort_key)
    failures = [item for item in results if item.comparison is None]
    ordered = [item for item, _ in successes] + failures
    if args.limit:
        ordered = ordered[: args.limit]
    if args.json:
        print(
            json.dumps(
                [item.as_dict() for item in ordered],
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for rank, (_, comparison) in enumerate(successes[: args.limit or None], 1):
            print(f"{rank:3d} {comparison_line(comparison)}")
        for result in failures:
            detail = result.stderr.strip().splitlines()
            message = detail[-1] if detail else f"exit {result.returncode}"
            print(f"FAIL {result.source}: {message}", file=sys.stderr)
    return 0 if successes else 1


def campaign_command(args: argparse.Namespace) -> int:
    if args.json and args.json_summary:
        print(
            "error: --json and --json-summary are mutually exclusive",
            file=sys.stderr,
        )
        return 2
    manifest_path: Path | None = None
    effective_ledger: str | Path | None = args.ledger
    try:
        if args.no_ledger and args.ledger:
            raise ValueError("--ledger and --no-ledger are mutually exclusive")
        environment = parse_environment(args.env)
        if args.toolchain:
            environment = merge_toolchain_environment(environment, args.toolchain)
        compile_cwd = (
            Path(args.compile_cwd).expanduser().resolve()
            if args.compile_cwd
            else Path.cwd().resolve()
        )
        target = Path(args.target).expanduser().resolve()
        if not target.is_file():
            raise FileNotFoundError(f"target object does not exist: {target}")
        objdump = discover_objdump(args.objdump)
        experiment = (
            load_experiment(args.experiment_manifest)
            if args.experiment_manifest
            else None
        )
        if experiment is not None:
            validate_campaign_sources(experiment, args.sources)
        candidates: list[Candidate] = []
        if not args.no_ledger or experiment is not None:
            candidates, _ = prepare_candidates(
                args.sources,
                template=args.compile_command,
                target=target,
                symbol=args.symbol,
                environment=environment,
                compile_cwd=compile_cwd,
                section=args.section,
                objdump=objdump,
            )
        candidate_metadata = (
            {
                candidate.cache_key: experiment.metadata_for(candidate.source)
                for candidate in candidates
            }
            if experiment is not None
            else None
        )
        if not args.no_ledger:
            identity, identity_inputs = campaign_identity(
                target=target,
                symbol=args.symbol,
                section=args.section,
                template=args.compile_command,
                compile_cwd=compile_cwd,
                environment=environment,
                objdump=objdump,
                toolchain=args.toolchain,
            )
            manifest_path, ledger_path, _ = initialize_manifest(
                candidates,
                identity=identity,
                identity_inputs=identity_inputs,
                state_root=args.state_dir,
                ledger=args.ledger,
                cache_dir=args.cache_dir,
                artifact_dir=args.artifact_dir,
                jobs=args.jobs,
                timeout=args.timeout,
                stop_on_exact=args.stop_on_exact,
                experiment=experiment.as_dict() if experiment else None,
            )
            effective_ledger = ledger_path
        results, duplicates = run_campaign(
            args.sources,
            target=target,
            template=args.compile_command,
            cache_dir=args.cache_dir,
            ledger=effective_ledger,
            jobs=args.jobs,
            objdump=objdump,
            symbol=args.symbol,
            section=args.section,
            environment=environment,
            compile_cwd=compile_cwd,
            keep_objects=args.keep_objects,
            stop_on_exact=args.stop_on_exact,
            timeout=args.timeout,
            stream_limit=args.stream_limit,
            artifact_dir=args.artifact_dir,
            candidate_metadata=candidate_metadata,
            selected_region=experiment.region if experiment else None,
        )
        if manifest_path is not None:
            finish_manifest(
                manifest_path,
                results=len(results),
                prepared=len(duplicates),
                exact=any(
                    result.comparison is not None and result.comparison.exact
                    for result in results
                ),
            )
    except KeyboardInterrupt:
        if manifest_path is not None:
            finish_manifest(
                manifest_path,
                results=0,
                prepared=0,
                exact=False,
                interrupted=True,
            )
        raise
    except (OSError, RuntimeError, ValueError) as error:
        if manifest_path is not None:
            finish_manifest(
                manifest_path,
                results=0,
                prepared=0,
                exact=False,
                interrupted=True,
            )
        print(f"error: {error}", file=sys.stderr)
        return 2
    shown = results[: args.limit] if args.limit else results
    basins = group_object_basins(results)
    unrun = len(duplicates) - len(results)

    def basin_summary(basin: list[CompileResult]) -> dict[str, object]:
        comparison = basin[0].comparison
        if comparison is None:
            raise RuntimeError("object basin contains an unsuccessful candidate")
        return {
            "candidate_sha256": comparison.candidate_sha256,
            "candidate_sha1": comparison.candidate_sha1,
            "variant_count": len(basin),
            "sources": [item.source for item in basin],
            "best_metrics": selected_fields(
                comparison,
                ("verdict", "exact", "words", "norm", "opcodes", "regs"),
            ),
        }

    if args.json or args.json_summary:
        serialized_results = []
        for item in shown:
            if not args.json_summary:
                serialized_results.append(item.as_dict())
                continue
            comparison = item.comparison
            serialized_results.append(
                {
                    "source": item.source,
                    "returncode": item.returncode,
                    "object_path": item.object_path,
                    "cache_key": item.cache_key,
                    "cached": item.cached,
                    "duration_seconds": item.duration_seconds,
                    "experiment": item.experiment,
                    "region": item.region,
                    "comparison": (
                        selected_fields(comparison, CAMPAIGN_SUMMARY_KEYS)
                        if comparison
                        else None
                    ),
                }
            )
        print(
            json.dumps(
                {
                    "schema": "decomp-workbench-campaign-v1",
                    "unique_candidates": len(results),
                    "prepared_candidates": len(duplicates),
                    "stopped_on_exact": bool(unrun) and args.stop_on_exact,
                    "source_files": sum(len(items) for items in duplicates.values()),
                    "timeout_seconds": args.timeout,
                    "manifest": str(manifest_path) if manifest_path else None,
                    "ledger": str(effective_ledger) if effective_ledger else None,
                    "experiment": experiment.as_dict() if experiment else None,
                    "object_basins": [basin_summary(basin) for basin in basins],
                    "results": serialized_results,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for rank, result in enumerate(shown, 1):
            if result.comparison:
                cache = "cache" if result.cached else "built"
                print(
                    f"{rank:3d} {comparison_line(result.comparison)} "
                    f"[{cache} {result.duration_seconds:.2f}s]"
                )
            else:
                detail = result.stderr.strip().splitlines()
                message = detail[-1] if detail else f"exit {result.returncode}"
                print(f"FAIL {result.source}: {message}", file=sys.stderr)
        print(
            f"object basins: {len(basins)} across "
            f"{sum(len(basin) for basin in basins)} successful variants"
        )
        if args.show_basins:
            for number, basin in enumerate(basins, 1):
                comparison = basin[0].comparison
                if comparison is None:
                    continue
                sources = ", ".join(item.source for item in basin)
                print(
                    f"BASIN {number:3d} variants={len(basin):3d} "
                    f"sha1={comparison.candidate_sha1} {comparison.verdict}\n"
                    f"  {sources}"
                )
        if unrun and args.stop_on_exact:
            print(
                f"stopped on the first exact match; {unrun} prepared "
                "candidate(s) were not compiled "
                "(pass --no-stop-on-exact to sweep them)"
            )
        duplicate_count = sum(len(items) - 1 for items in duplicates.values())
        if duplicate_count:
            print(f"deduplicated {duplicate_count} identical source file(s)")
        if effective_ledger:
            print(f"ledger: {Path(effective_ledger).resolve()}")
        if manifest_path:
            print(f"manifest: {manifest_path}")
            print(
                "next: decomp-workbench campaign status "
                f"{shlex.quote(str(manifest_path.parent))}"
            )
    return 0 if any(item.comparison for item in results) else 1


def instrument_command(args: argparse.Namespace) -> int:
    source_path = Path(args.input)
    output_path = Path(args.output)
    if source_path.resolve() == output_path.resolve() and not args.in_place:
        print(
            "error: input and output are identical; pass --in-place to confirm",
            file=sys.stderr,
        )
        return 2
    try:
        result = instrument_ugen(
            source_path.read_text(encoding="utf-8"),
            function_pattern=args.functions,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.source, encoding="utf-8")
    except (OSError, ValueError, re.error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"instrumented {result.functions} functions and "
        f"{result.free_list_hooks} free-list hooks -> {output_path}"
    )
    return 0


def instrument_uopt_command(args: argparse.Namespace) -> int:
    source_path = Path(args.input)
    output_path = Path(args.output)
    if source_path.resolve() == output_path.resolve() and not args.in_place:
        print(
            "error: input and output are identical; pass --in-place to confirm",
            file=sys.stderr,
        )
        return 2
    try:
        result = instrument_uopt_globalcolor(
            source_path.read_text(encoding="utf-8"),
            allow_unverified_source=args.allow_unverified_source,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.source, encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"instrumented {result.trace_points} globalcolor sites "
        f"using {result.profile} -> {output_path}"
    )
    return 0


def instrument_alias_command(args: argparse.Namespace) -> int:
    source_path = Path(args.input)
    output_path = Path(args.output)
    if source_path.resolve() == output_path.resolve() and not args.in_place:
        print(
            "error: input and output are identical; pass --in-place to confirm",
            file=sys.stderr,
        )
        return 2
    try:
        result = instrument_uopt_alias(
            source_path.read_text(encoding="utf-8"),
            allow_unverified_source=args.allow_unverified_source,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.source, encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"instrumented {result.trace_points} alias-decision sites "
        f"using {result.profile} -> {output_path}"
    )
    return 0


def instrument_profiles_command(args: argparse.Namespace) -> int:
    source_path = Path(args.input)
    output_path = Path(args.output)
    if source_path.resolve() == output_path.resolve() and not args.in_place:
        print(
            "error: input and output are identical; pass --in-place to confirm",
            file=sys.stderr,
        )
        return 2
    try:
        result = instrument_uopt_profiles(
            source_path.read_text(encoding="utf-8"),
            args.profile,
            allow_unverified_source=args.allow_unverified_source,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.source, encoding="utf-8")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        f"instrumented {result.trace_points} sites from "
        f"{', '.join(result.profiles)} using {result.profile} -> {output_path}"
    )
    return 0


def trace_summary_command(args: argparse.Namespace) -> int:
    try:
        events = parse_trace(Path(args.trace).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    summary = trace_summary(events)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"events: {summary['events']}")
        for action, count in summary["actions"].items():
            print(f"  {action:18s} {count}")
        if summary["registers"]:
            print(
                "registers: "
                + " ".join(
                    f"{name}={count}" for name, count in summary["registers"].items()
                )
            )
    return 0 if events else 1


def trace_alias_command(args: argparse.Namespace) -> int:
    try:
        events = parse_trace(Path(args.trace).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    report = alias_trace_summary(events)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"base-events={report['base_events']} "
            f"alias-queries={report['alias_queries']}"
        )
        for label, values in (
            ("base paths", report["base_paths"]),
            ("base types", report["base_types"]),
            ("results", report["query_results"]),
            ("left types", report["left_types"]),
            ("right types", report["right_types"]),
        ):
            if values:
                print(
                    f"{label}: "
                    + " ".join(f"{name}={count}" for name, count in values.items())
                )
        if args.show_queries:
            for event in events:
                if event.action != "alias-query":
                    continue
                left = event.fields.get("left_type", "?")
                right = event.fields.get("right_type", "?")
                result = event.fields.get("result", "?")
                register = (
                    register_name(event.register) if event.register is not None else "-"
                )
                print(
                    f"line={event.index:<5d} reg={register:>3s} "
                    f"{left:>8s} ↔ {right:<8s} {result}"
                )
    return 0 if report["events"] else 1


def decoded_color(cost: dict[str, str]) -> str:
    """Return the machine register for a recorded color, in parentheses."""

    register = cost.get("reg") or register_for_color(
        optional_integer(cost.get("color"))
    )
    return f"({register})" if register else ""


def parse_register_list(value: str | None) -> list[int] | None:
    if value is None:
        return None
    return [parse_register(item) for item in value.split(",") if item.strip()]


def trace_fifo_command(args: argparse.Namespace) -> int:
    try:
        events = parse_trace(Path(args.trace).read_text(encoding="utf-8"))
        initial = parse_register_list(args.initial)
        selected = parse_register_list(args.registers)
        list_address = parse_integer(args.list_address) if args.list_address else None
        if args.list_address and list_address is None:
            raise ValueError(f"invalid list address: {args.list_address!r}")
        report = replay_fifo(
            events,
            initial_queue=initial,
            registers=set(selected) if selected is not None else None,
            list_address=list_address,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(
            "initial: " + " ".join(register_name(item) for item in report.initial_queue)
        )
        print(
            "allocations: "
            + " ".join(register_name(item) for item in report.allocations)
        )
        print("final: " + " ".join(register_name(item) for item in report.final_queue))
        print(
            f"logical values: "
            f"{sum(event.action == 'allocate' for event in report.logical_events)} "
            f"max-live={report.max_live}"
        )
        for violation in report.violations:
            print(f"VIOLATION {violation}", file=sys.stderr)
        if args.show_events:
            for event in report.logical_events:
                print(
                    f"{event.action:8s} v{event.value:<4d} "
                    f"{register_name(event.register):>3s} "
                    f"source={event.source_line or '-':>5} "
                    f"trace={event.trace_line}"
                )
    return 1 if args.fail_on_violation and not report.valid else 0


def trace_globalcolor_command(args: argparse.Namespace) -> int:
    if args.web is not None and args.proc is None:
        print(
            "error: --web requires --proc so the allocator lookup is unambiguous",
            file=sys.stderr,
        )
        return 2
    try:
        report = parse_globalcolor_trace(Path(args.trace).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    selected = (
        [] if args.proc is not None else report.ranked(dtype=args.dtype, limit=args.top)
    )
    allocator_webs = report.allocator_webs(
        proc=args.proc, web=args.web, dtype=args.dtype, limit=args.top
    )
    decisions = report.decisions_for(args.proc, web=args.web)
    lookup_error = None
    if args.web is not None and not allocator_webs:
        same_web = report.allocator_webs(proc=args.proc, web=args.web)
        if same_web and args.dtype is not None:
            recorded = sorted(
                {
                    str(item.dtype) if item.dtype is not None else "unknown"
                    for item in same_web
                }
            )
            suffix = (
                f" web exists but does not match dtype={args.dtype}; "
                f"recorded dtype(s): {', '.join(recorded)}"
            )
        else:
            available = report.allocator_webs(proc=args.proc)
            available_webs = sorted({item.web for item in available})
            suffix = (
                " available web(s): " + ", ".join(str(item) for item in available_webs)
                if available_webs
                else " no allocator decisions were recorded for that procedure"
            )
        lookup_error = (
            f"no allocator decision matched proc={args.proc} web={args.web};{suffix}"
        )
    elif args.proc is not None and not allocator_webs and not decisions:
        available_procedures = sorted({item.proc for item in report.allocator_webs()})
        suffix = (
            " available procedure(s): "
            + ", ".join(str(item) for item in available_procedures)
            if available_procedures
            else " no allocator decisions were recorded"
        )
        lookup_error = f"no allocator data matched proc={args.proc};{suffix}"
    if args.json:
        print(
            json.dumps(
                {
                    "error": lookup_error,
                    "filters": {
                        "dtype": args.dtype,
                        "proc": args.proc,
                        "top": args.top,
                        "web": args.web,
                    },
                    "live_ranges": [item.as_dict() for item in selected],
                    "allocator_webs": [item.as_dict() for item in allocator_webs],
                    "decisions": [item.as_dict() for item in decisions],
                    "unparsed_diagnostic_lines": (report.unparsed_diagnostic_lines),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        if lookup_error:
            print(f"error: {lookup_error}", file=sys.stderr)
            return 1
        for item in selected:
            costs = sorted(item.finite_costs, key=lambda entry: entry.cost)
            best = f"r{costs[0].register}:{costs[0].cost:g}" if costs else "-"
            print(
                f"bitpos={item.bitpos:5d} dtype={item.dtype:2d} "
                f"weight={item.weight:5d} "
                f"adjsave={item.adjusted_save:11g} "
                f"total={item.total_save:13g} best={best}"
            )
        for allocator_item in allocator_webs:
            detail = allocator_item.detail
            cost_text = ",".join(
                f"c{cost.get('color', '?')}{decoded_color(cost)}:"
                f"{cost.get('cost', '?')}"
                for cost in allocator_item.color_costs
            )
            print(
                f"proc={allocator_item.proc} web={allocator_item.web} "
                f"phase={allocator_item.phase} "
                f"force_key={allocator_item.force_key} "
                f"dtype={detail.get('dtype', '?')} "
                f"save={allocator_item.fields.get('save', '?')} "
                f"nocs={allocator_item.fields.get('nocs', '?')} "
                f"bestcolor={allocator_item.fields.get('bestcolor', '?')} "
                f"register={allocator_item.assigned_register or '-'} "
                f"decision={allocator_item.fields.get('decision', '?')} "
                f"bb={detail.get('bb', '?')} line={detail.get('line', '?')} "
                f"costs={cost_text or '-'}\n"
                f"  {allocator_item.explanation}"
            )
        print(
            f"live-ranges={len(selected)}/{len(report.live_ranges)} "
            f"allocator-webs={len(allocator_webs)} "
            f"decisions={len(decisions)} "
            f"unparsed={len(report.unparsed_diagnostic_lines)}"
        )
    if lookup_error:
        return 1
    return 0 if selected or allocator_webs or decisions else 1


def parse_listing_edit(value: str, position: str) -> ListingEdit:
    pattern, separator, text = value.partition("=")
    if not separator or not pattern:
        raise ValueError(f"--insert-{position} expects REGEX=TEXT: {value!r}")
    return ListingEdit(position=position, pattern=pattern, text=text)


def replay_as1_command(args: argparse.Namespace) -> int:
    try:
        edits = [
            *(parse_listing_edit(value, "before") for value in args.insert_before),
            *(parse_listing_edit(value, "after") for value in args.insert_after),
        ]
        result = replay_as1(
            args.listing,
            args.output,
            as0_template=args.as0_command,
            as1_template=args.as1_command,
            edits=edits,
            allow_multiple=args.allow_multiple,
            keep_work=args.keep_work,
            calibration_object=args.calibration_object,
            objdump=args.objdump,
            work_root=args.work_root,
            compile_cwd=args.compile_cwd,
            environment=parse_environment(args.env),
            timeout=args.timeout,
            stream_limit=args.stream_limit,
            artifact_dir=args.artifact_dir,
        )
    except (OSError, RuntimeError, ValueError, re.error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result.__dict__, indent=2, sort_keys=True))
    else:
        print(f"as0: {shlex.join(result.as0_command)}")
        print(f"as1: {shlex.join(result.as1_command)}")
        print(f"object: {result.output}")
        if result.retained_directory:
            print(f"retained: {result.retained_directory}")
        if result.calibration:
            print("unedited replay calibration: PASS (section-scoped)")
    return 0


#: What a reader who typed the program name and nothing else needs.
#:
#: argparse's answer was a comma-separated wall of 44 command names and exit
#: 2, which reads as a failure and names no starting point. Four lines that
#: say what this is and where to go next cost nothing and are the first thing
#: anyone sees.
WELCOME = (
    "decomp-workbench: diagnose why an almost-matching MIPS object still "
    "differs, and what to change next.",
    "New here? Run `decomp-workbench commands` for the compact map, or read "
    "docs/START_HERE.md",
    "Full command list: decomp-workbench --help",
    "Name a lever family: decomp-workbench guide <playbook|verdict|lever>",
)


def build_parser() -> argparse.ArgumentParser:
    parser = CommandParser(
        prog="decomp-workbench",
        description=(
            "MIPS object diagnosis, decomp.me handoffs, candidate campaigns, "
            "compiler traces, and pass replay"
        ),
        epilog=(
            "Start with `decomp-workbench commands` for the compact "
            "journey map, or docs/START_HERE.md for the whole workflow."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    add_explain_keys_argument(parser)
    commands = parser.add_subparsers(
        dest="command",
        required=True,
        # The generated ``{a,b,c,...}`` metavar is 44 names wide and is the
        # first thing an error prints. One word plus a pointer is readable.
        metavar="COMMAND",
        help="run `decomp-workbench commands` for the compact journey map",
    )

    # `view` and `view-dumps` read the same two inputs as `compare` and
    # `compare-dumps` and answer the next question about them, so they belong
    # beside them in the listing.
    register_object_commands(
        commands,
        compare_handler=compare_command,
        compare_dumps_handler=compare_dumps_command,
    )
    register_view_commands(commands)
    register_diagnose_commands(commands)
    register_rank_command(commands, handler=rank_command)
    register_guide_command(commands)
    register_discovery_commands(commands)
    register_scheduler_commands(commands)
    register_allocator_commands(commands)
    register_source_correlation_command(commands)
    register_pass_adapter_command(commands)
    register_fingerprint_commands(commands)
    register_relocation_command(commands)
    register_fidelity_command(commands)
    register_toolchain_commands(commands)
    register_oracle_commands(commands)
    register_experiment_commands(commands)

    register_scratch_commands(
        commands,
        check_handler=check_scratch_command,
        doctor_handler=doctor_command,
        skill_handler=install_skill_command,
    )

    register_campaign_run_commands(
        commands,
        compile_rank_handler=compile_rank_command,
        campaign_handler=campaign_command,
    )
    register_campaign_cockpit_commands(commands)
    register_cache_commands(commands)
    register_context_commands(commands)

    instrument_parser = commands.add_parser(
        "instrument-ugen",
        help="instrument statically recompiled ugen C",
        description="Add opt-in function and free-list traces to generated ugen C.",
    )
    instrument_parser.add_argument("input", help="pristine generated ugen.c")
    instrument_parser.add_argument("output", help="instrumented output path")
    instrument_parser.add_argument(
        "--functions",
        default=r"^f_",
        help=r"regular expression selecting generated functions (default: ^f_)",
    )
    instrument_parser.add_argument(
        "--in-place",
        action="store_true",
        help="permit input and output to be the same path",
    )
    instrument_parser.set_defaults(handler=instrument_command)

    instrument_uopt_parser = commands.add_parser(
        "instrument-uopt-globalcolor",
        help="instrument the pinned IDO 5.3 static-recomp uopt profile",
        description="Add globalcolor traces and force probes to pinned uopt C.",
    )
    instrument_uopt_parser.add_argument("input", help="pristine generated uopt.c")
    instrument_uopt_parser.add_argument("output", help="instrumented output path")
    instrument_uopt_parser.add_argument(
        "--allow-unverified-source",
        action="store_true",
        help="bypass the source hash for profile development",
    )
    instrument_uopt_parser.add_argument(
        "--in-place",
        action="store_true",
        help="permit input and output to be the same path",
    )
    instrument_uopt_parser.set_defaults(handler=instrument_uopt_command)

    instrument_alias_parser = commands.add_parser(
        "instrument-uopt-alias",
        help="trace base provenance in the pinned IDO 5.3 uopt profile",
        description="Add base-provenance and alias-query traces to pinned uopt C.",
    )
    instrument_alias_parser.add_argument("input", help="pristine generated uopt.c")
    instrument_alias_parser.add_argument("output", help="instrumented output path")
    instrument_alias_parser.add_argument(
        "--allow-unverified-source",
        action="store_true",
        help="bypass the source hash for profile development",
    )
    instrument_alias_parser.add_argument(
        "--in-place",
        action="store_true",
        help="permit input and output to be the same path",
    )
    instrument_alias_parser.set_defaults(handler=instrument_alias_command)

    instrument_profiles_parser = commands.add_parser(
        "instrument-uopt",
        help="apply compatible profiles to the pinned IDO 5.3 uopt source",
        description="Apply one or more compatible profiles to pinned uopt C.",
    )
    instrument_profiles_parser.add_argument("input", help="pristine generated uopt.c")
    instrument_profiles_parser.add_argument("output", help="instrumented output path")
    instrument_profiles_parser.add_argument(
        "--profile",
        action="append",
        choices=SUPPORTED_PROFILES,
        required=True,
        help="profile to apply; repeat for a combined source",
    )
    instrument_profiles_parser.add_argument(
        "--allow-unverified-source",
        action="store_true",
        help="bypass the source hash for profile development",
    )
    instrument_profiles_parser.add_argument(
        "--in-place",
        action="store_true",
        help="permit input and output to be the same path",
    )
    instrument_profiles_parser.set_defaults(handler=instrument_profiles_command)

    summary_parser = commands.add_parser(
        "trace-summary",
        help="summarize ugen diagnostic events",
        description="Count recognized events, actions, registers, and source lines.",
    )
    summary_parser.add_argument("trace", help="captured compiler log")
    summary_parser.add_argument("--json", action="store_true", help="emit JSON")
    summary_parser.set_defaults(handler=trace_summary_command)

    alias_parser = commands.add_parser(
        "trace-alias",
        help="summarize profiled uopt base-provenance and alias decisions",
        description="Report base paths, descriptor types, and alias outcomes.",
    )
    alias_parser.add_argument("trace", help="captured compiler log")
    alias_parser.add_argument(
        "--show-queries", action="store_true", help="print each alias query"
    )
    alias_parser.add_argument("--json", action="store_true", help="emit JSON")
    alias_parser.set_defaults(handler=trace_alias_command)

    fifo_parser = commands.add_parser(
        "trace-fifo",
        help="replay a traced register free list as a FIFO",
        description="Validate queue order and assign logical value identities.",
    )
    fifo_parser.add_argument("trace", help="captured compiler log")
    fifo_parser.add_argument(
        "--initial",
        help="comma-separated initial queue; inferred from leading appends",
    )
    fifo_parser.add_argument(
        "--registers", help="comma-separated register class to include"
    )
    fifo_parser.add_argument(
        "--list-address", help="only include appends for this list"
    )
    fifo_parser.add_argument(
        "--show-events", action="store_true", help="print the logical event schedule"
    )
    fifo_parser.add_argument("--json", action="store_true", help="emit JSON")
    fifo_parser.add_argument(
        "--fail-on-violation",
        action="store_true",
        help="return exit 1 when FIFO validation fails",
    )
    fifo_parser.set_defaults(handler=trace_fifo_command)

    color_parser = commands.add_parser(
        "trace-globalcolor",
        help="summarize uopt CSAVE/CUP and CDX globalcolor traces",
        description="Rank live ranges and report color/split decisions.",
    )
    color_parser.add_argument("trace", help="captured compiler log")
    color_parser.add_argument(
        "--proc", type=int, help="include only CDX decisions from this procedure"
    )
    color_parser.add_argument(
        "--web",
        type=int,
        help="inspect one allocator web; pair with --proc for an unambiguous lookup",
    )
    color_parser.add_argument("--dtype", type=int, help="include only this data type")
    color_parser.add_argument(
        "--top", type=int, default=20, help="maximum live ranges to show"
    )
    color_parser.add_argument("--json", action="store_true", help="emit JSON")
    color_parser.set_defaults(handler=trace_globalcolor_command)

    replay_parser = commands.add_parser(
        "replay-as1",
        help="edit a retained ugen listing and rerun as0/as1",
        description="Apply unique listing edits and rebuild through as0 and as1.",
    )
    replay_parser.add_argument("listing", help="retained ugen assembly listing")
    replay_parser.add_argument("output", help="output object path")
    replay_parser.add_argument(
        "--as0-command",
        required=True,
        help="template containing {listing} and {binasm}",
    )
    replay_parser.add_argument(
        "--as1-command",
        required=True,
        help="template containing {binasm} and {object}",
    )
    replay_parser.add_argument(
        "--insert-before",
        action="append",
        default=[],
        metavar="REGEX=TEXT",
        help="insert text before a unique regex match; repeatable",
    )
    replay_parser.add_argument(
        "--insert-after",
        action="append",
        default=[],
        metavar="REGEX=TEXT",
        help="insert text after a unique regex match; repeatable",
    )
    replay_parser.add_argument(
        "--allow-multiple",
        action="store_true",
        help="permit an edit regex to match more than once",
    )
    replay_parser.add_argument(
        "--keep-work", help="retain the edited listing and intermediate files here"
    )
    replay_parser.add_argument(
        "--calibration-object",
        help="normal unedited output required before any edited replay",
    )
    replay_parser.add_argument("--objdump", help="object reader for calibration gates")
    replay_parser.add_argument(
        "--work-root",
        help="project-visible temporary root for Docker/QEMU path visibility",
    )
    replay_parser.add_argument("--compile-cwd", help="working directory for as0/as1")
    replay_parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="explicit pass environment entry; repeatable",
    )
    replay_parser.add_argument("--timeout", type=float, default=120.0)
    add_process_output_arguments(replay_parser)
    replay_parser.add_argument("--json", action="store_true", help="emit JSON")
    replay_parser.set_defaults(handler=replay_as1_command)

    bundle_parser = commands.add_parser(
        "bundle-scratch",
        help="package local inputs for manual decomp.me scratch creation",
        description=(
            "Copy target assembly, context, and source into a deterministic "
            "upload-neutral scratch bundle."
        ),
    )
    bundle_parser.add_argument("output", help="new or empty output directory")
    bundle_parser.add_argument(
        "--target-assembly", required=True, help="single-function GAS target"
    )
    bundle_parser.add_argument("--context", required=True, help="context C file")
    bundle_parser.add_argument(
        "--source", required=True, help="candidate source C file"
    )
    bundle_parser.add_argument("--platform", required=True, help="decomp.me platform")
    bundle_parser.add_argument("--compiler", required=True, help="compiler identity")
    bundle_parser.add_argument(
        "--compiler-flags", default="", help="compiler flags copied to the manifest"
    )
    bundle_parser.add_argument(
        "--diff-label", required=True, help="target function label"
    )
    bundle_parser.add_argument("--project", help="optional project identity")
    bundle_parser.add_argument("--preset", help="optional decomp.me preset identity")
    bundle_parser.add_argument("--json", action="store_true", help="emit manifest JSON")
    bundle_parser.set_defaults(handler=bundle_scratch_command)
    finalize_command_help(commands)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        print("\n".join(WELCOME))
        return 0
    arguments = rewrite_group_alias(arguments)
    json_requested = "--json" in arguments or "--json-summary" in arguments
    parser = build_parser()
    if json_requested:
        parse_stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(parse_stderr):
                args = parser.parse_args(arguments)
        except SystemExit as error:
            if error.code == 0:
                raise
            status = error.code if isinstance(error.code, int) else 1
            nested = (
                f"{arguments[0]}-{arguments[1]}" if len(arguments) >= 2 else "unknown"
            )
            command = (
                nested
                if nested in SCHEMAS
                else next(
                    (item for item in arguments if item in SCHEMAS),
                    "unknown",
                )
            )
            diagnostic = parse_stderr.getvalue().strip().splitlines()
            # An argparse diagnostic can run to several lines (usage, the
            # error, and for an unknown command a pointer at `commands`). The
            # reportable part is the one argparse prefixed.
            prefix = f"{parser.prog}: error: "
            reported = [line for line in diagnostic if line.startswith(prefix)]
            message = (
                reported[-1].removeprefix(prefix).strip()
                if reported
                else diagnostic[-1].strip()
                if diagnostic
                else "invalid command arguments"
            )
            print(
                render_json(error_report(command, status=status, message=message)),
                end="",
            )
            return status
    else:
        args = parser.parse_args(arguments)
    # Which spelling of the symbol selector was used is parser bookkeeping,
    # not an argument a command should see.
    vars(args).pop(SYMBOL_OPTION_DEST, None)
    handler = cast(Callable[[argparse.Namespace], int], args.handler)
    if json_requested:
        command = str(getattr(args, "report_command", args.command))
        return run_json_handler(command, args, handler)
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
