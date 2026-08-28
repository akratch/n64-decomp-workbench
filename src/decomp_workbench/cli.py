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
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, cast

from . import __version__
from .a71_cli import register_a71_command
from .agent_skill import install_agent_skill
from .align_cli import register_align_commands
from .allocator_cli import register_allocator_commands
from .artifacts import capture_streams
from .binasm_cli import register_binasm_command
from .cache import cache_status as inspect_cache
from .cache import format_bytes
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
    finalize_source_retention,
    finish_manifest,
    initialize_manifest,
    record_control_preflight,
)
from .capture_cli import register_capture_commands
from .cascade_cli import register_cascade_commands
from .cli_options import (
    SYMBOL_OPTION_DEST,
    add_explain_keys_argument,
    add_process_output_arguments,
)
from .collateral_cli import register_collateral_command
from .compare import MIXED_ALIGNMENT_CAUTION, compare_instructions, compare_objects
from .comparison_render import comparison_line as comparison_line
from .comparison_render import (
    relocation_target_difference_lines,
    scratch_acceptance_line,
    scratch_comparison_payload,
    scratch_score_acceptance,
    warning_lines,
)
from .context_lint_cli import register_context_commands
from .context_truth import (
    build_truth_stack,
    call_contract_hypotheses,
    truth_stack_lines,
)
from .decompme_cli import register_decompme_commands
from .diagnose_cli import register_diagnose_commands
from .diagnosis import diagnose_instructions, diagnose_objects
from .discovery import (
    CommandParser,
    finalize_command_help,
    register_discovery_commands,
    rewrite_group_alias,
)
from .environment import merge_toolchain_environment, resolve_compiler_environment
from .environment import parse_environment as parse_environment
from .experiment_cli import register_experiment_commands
from .experiment_controls import run_control_preflight
from .experiments import (
    EXPERIMENT_SCHEMA_V2,
    load_experiment,
    validate_campaign_sources,
)
from .fidelity_cli import (
    register_fidelity_command,
    register_instrument_gate_command,
)
from .fingerprint_cli import register_fingerprint_commands
from .force_rows_cli import register_force_rows_commands
from .globalcolor import (
    COLOR_REGISTERS,
    color_for_register,
    optional_integer,
    parse_globalcolor_trace,
    register_for_color,
)
from .guide_cli import register_guide_command
from .handoff_cli import register_handoff_command
from .instrument import instrument_ugen
from .instrument_alias import instrument_uopt_alias
from .instrument_profiles import (
    SUPPORTED_PROFILES,
    instrument_uopt_profiles,
)
from .instrument_uopt import instrument_uopt_globalcolor
from .line_probe_cli import register_line_probe_command
from .matrix_cli import register_matrix_command
from .model import Comparison, CompileResult, display_path
from .next_cli import register_next_command
from .notes_cli import register_note_commands
from .objdump import discover_objdump, dump_object, parse_disassembly, probe_objdump
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
from .pass_replay_cli import register_replay_ugen_command
from .permute_cli import register_permute_commands
from .phase_cli import register_phase_commands
from .preflight import compile_preflight
from .project_cli import register_project_commands
from .relocation_cli import register_relocation_command
from .reporting import SCHEMAS, error_report, render_json, run_json_handler
from .scheduler_cli import register_scheduler_commands
from .schema import selected_fields
from .score_cli import register_score_command
from .scratch_bundle import bundle_scratch
from .scratch_check import (
    ScratchPackage,
    compose_site_source,
    load_scratch,
    scratch_context_hardening,
    scratch_frontend,
    scratch_score,
    site_source_marker,
)
from .scratch_registration import register_scratch_commands
from .shift_cli import register_shift_commands
from .slots_cli import register_slots_command
from .source_correlation_cli import register_source_correlation_command
from .source_probe_cli import register_source_probe_commands
from .streams_cli import register_stream_commands
from .sweep_cli import register_sweep_commands
from .target_audit_cli import register_target_commands
from .toolchain import toolchain_status
from .toolchain_cli import register_toolchain_commands
from .trace import (
    alias_trace_summary,
    parse_emission_map,
    parse_integer,
    parse_register,
    parse_trace,
    register_name,
    replay_fifo,
    trace_summary,
)
from .ucode_cli import register_ucode_command
from .view import MechanismView
from .view_cli import (
    Painter,
    register_view_commands,
    register_window_commands,
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
    "pool_exact",
    "pool_prefix_exact",
    "temp_prefix_exact",
    "first_temp_divergence",
    "first_divergent_row",
    "alignment_method",
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
            compiler_id=args.compiler_id,
            language=args.language,
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
        frontend = scratch_frontend(package)
        composed = workspace / str(frontend["source_name"])
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
                "site_line_reset": frontend["line_reset"],
                "frontend": frontend,
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
            "site_line_reset": frontend["line_reset"],
            "frontend": frontend,
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
        score_exact, _basis = scratch_score_acceptance(comparison)
        if not score_exact:
            return [
                "The function is relocation-normalized exact, but the local "
                "decomp.me score proxy still fails. Match both raw instruction "
                "words and relocation symbol/addend targets before claiming 100%.",
            ]
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
    if args.project_source and not args.project_object:
        print("error: --project-source requires --project-object", file=sys.stderr)
        return 2
    if args.timeout <= 0:
        print("error: --timeout must be positive", file=sys.stderr)
        return 2
    if args.stream_limit < 0:
        print("error: --stream-limit must be non-negative", file=sys.stderr)
        return 2
    try:
        package = load_scratch(args.scratch)
        project_comparison: Comparison | None = None
        hypotheses: list[dict[str, Any]] = []
        with tempfile.TemporaryDirectory(prefix="decomp-workbench-scratch-") as temp:
            workspace = Path(temp)
            comparison, view, compile_report, evidence = _scratch_comparison(
                package,
                args,
                workspace,
            )
            if args.project_object:
                if "target.o" not in package.files:
                    raise ValueError(
                        "--project-object requires target.o in the scratch export"
                    )
                target_object = package.materialize("target.o", workspace)
                if args.view:
                    project_comparison = diagnose_objects(
                        target_object,
                        args.project_object,
                        objdump=args.objdump,
                        symbol=args.symbol
                        or (
                            package.metadata.get("diff_label")
                            if isinstance(package.metadata.get("diff_label"), str)
                            else None
                        ),
                        section=args.section,
                        register_profile=args.register_profile,
                    ).comparison
                else:
                    project_comparison = compare_objects(
                        target_object,
                        args.project_object,
                        objdump=args.objdump,
                        symbol=args.symbol
                        or (
                            package.metadata.get("diff_label")
                            if isinstance(package.metadata.get("diff_label"), str)
                            else None
                        ),
                        section=args.section,
                    )
                project_comparison.target = f"{display_path(package.path)}:target.o"
                project_comparison.candidate = display_path(args.project_object)
            hypotheses = call_contract_hypotheses(
                package=package,
                scratch=comparison,
                view=view,
                project=project_comparison,
                project_source=args.project_source,
                frontend=scratch_frontend(package),
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
    if hypotheses:
        actions.insert(0, str(hypotheses[0]["action"]))
    hardening = scratch_context_hardening(package)
    frontend = scratch_frontend(package)
    truth_stack = build_truth_stack(
        external_score=score,
        scratch=comparison,
        project=project_comparison,
        hypotheses=hypotheses,
    )
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
            "line_reset": frontend["line_reset"] if args.compile_command else None,
            "source_name": frontend["source_name"],
            "frontend": frontend,
        },
        "context_hardening": hardening,
        "truth_layers": truth_stack["layers"],
        "context_differential": truth_stack["context_differential"],
        "context_hypotheses": truth_stack["context_hypotheses"],
        "truth": truth_stack,
        "comparison": (
            scratch_comparison_payload(comparison) if comparison is not None else None
        ),
        "view": (
            view.as_dict(report_regs=args.report_regs) if view is not None else None
        ),
        "compile": compile_report,
        "project_comparison": (
            scratch_comparison_payload(project_comparison)
            if project_comparison is not None
            else None
        ),
        "next_actions": actions,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if args.project_object or hypotheses:
            for line in truth_stack_lines(truth_stack):
                print(line)
        print(f"scratch: {package.kind} ({display_path(package.path)})")
        if comparison is not None:
            # Same placement rule the comparison commands use: a warning that
            # the selector was answered a different way has to precede the
            # acceptance it qualifies. `--json` has always carried these under
            # `comparison.warnings`; the terminal dropped them.
            for line in warning_lines(comparison.warnings):
                print(line)
            print("acceptance: " + scratch_acceptance_line(comparison))
        metadata = package.public_metadata()
        identity = metadata.get("name") or metadata.get("project")
        slug = metadata.get("slug")
        if identity or slug:
            parts = [str(value) for value in (identity, slug) if value]
            print("identity: " + " / ".join(parts))
        print("files: " + ", ".join(sorted(package.files)))
        frontend_parts = [
            f"compiler_id={frontend['compiler_id']}"
            if frontend["compiler_id"]
            else f"compiler_selection={frontend['compiler']}"
            if frontend["compiler"]
            else None,
            f"language={frontend['language']}" if frontend["language"] else None,
            f"frontend={frontend['frontend']}" if frontend["frontend"] else None,
            f"driver={frontend['expected_driver']}"
            if frontend["expected_driver"]
            else None,
        ]
        if any(frontend_parts):
            print("frontend: " + ", ".join(item for item in frontend_parts if item))
        if package.checksums_valid:
            print("integrity: PASS (all workbench bundle checksums)")
        if hardening["applicable"]:
            for duplicate in hardening["duplicate_symbols"]:
                print(
                    f"warning: {duplicate['symbol']} is defined in both ctx.c "
                    f"(line {duplicate['ctx_line']}) and code.c "
                    f"(line {duplicate['code_line']}); keep the file-scope "
                    "definition in exactly one of them"
                )
            splices = hardening["code_splices"]
            for line_number in splices["broken"]:
                print(
                    f"warning: code.c line {line_number} ends in a backslash "
                    "followed by whitespace -- that is not a line splice, the "
                    "statements compile untied; delete the trailing "
                    "whitespace or put both statements on one physical line"
                )
            if splices["load_bearing"]:
                lines = ", ".join(str(n) for n in splices["load_bearing"])
                print(
                    "note: code.c splices statements onto one logical line at "
                    f"line(s) {lines}; if these ties are load-bearing "
                    "(guide lever 25), re-check them after every paste -- "
                    "whitespace-trimming editors and formatters strip them "
                    "silently, and the one-physical-line form travels better"
                )
            lint_findings = hardening["context_lint"]["findings"]
            if lint_findings:
                print(f"context lint: {len(lint_findings)} finding(s) in ctx.c/code.c")
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
                f"source composition: site-faithful (inserted "
                f"{site_source_marker(package).strip()} "
                "between ctx.c and candidate source)"
            )
        if comparison is None:
            print("comparison: unavailable")
        else:
            print(comparison_line(comparison))
            score_exact, _ = scratch_score_acceptance(comparison)
            if score_exact:
                print(
                    "decomp.me score proxy: PASS "
                    "(raw instruction words and relocation targets agree)"
                )
            elif comparison.exact:
                reasons = []
                if comparison.raw_word_mismatches:
                    reasons.append(
                        f"{comparison.raw_word_mismatches} raw word(s) differ"
                    )
                if comparison.relocation_target_mismatches:
                    reasons.append(
                        f"{comparison.relocation_target_mismatches} relocation "
                        "target(s) differ"
                    )
                print(
                    "decomp.me score proxy: FAIL ("
                    + "; ".join(reasons)
                    + "; linked-function exact is not a 100% site score)"
                )
            if view is None:
                print_comparison_explanation(comparison, cross_rom=False)
            else:
                for line in relocation_target_difference_lines(comparison):
                    print(line)
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
        if project_comparison is not None:
            print("project comparison: " + comparison_line(project_comparison))
        # A comparison already rendered its own guidance above. The action
        # list remains in JSON as the machine-readable equivalent, while the
        # terminal gets only genuinely additional handoff steps.
        if comparison is None or (
            comparison.exact and not scratch_score_acceptance(comparison)[0]
        ):
            for action in actions:
                print(f"next: {action}")
    mismatch = comparison is None or not scratch_score_acceptance(comparison)[0]
    return 1 if args.fail_on_mismatch and mismatch else 0


def doctor_command(args: argparse.Namespace) -> int:
    """Explain local readiness and validate an optional scratch handoff."""

    objdump_path: str | None = None
    objdump_error: str | None = None
    objdump_version: str | None = None
    objdump_checks: dict[str, bool] = {}
    try:
        objdump_path = discover_objdump(args.objdump)
        probe = probe_objdump(objdump_path)
        objdump_version = probe.version
        objdump_checks = dict(probe.checks)
        if not probe.compatible:
            objdump_error = (
                f"objdump is not GNU/MIPS compatible: {objdump_path} ({probe.error})"
            )
            objdump_path = None
    except (FileNotFoundError, RuntimeError) as error:
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
    cache_error: str | None = None
    try:
        cache_report = inspect_cache(cache)
        cache_files = int(cache_report["files"])
        cache_bytes = int(cache_report["bytes"])
    except OSError as error:
        cache_files = 0
        cache_bytes = 0
        cache_error = str(error)
    cache_large = cache_bytes >= 1024 * 1024 * 1024
    object_status = (
        "verified"
        if object_verified
        else "ready"
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
            "files": cache_files,
            "bytes": cache_bytes,
            "large": cache_large,
            "error": cache_error,
        },
        "dump_workflow": "ready",
        "object_workflow": {
            "status": object_status,
            "objdump": objdump_path,
            "version": objdump_version,
            "capabilities": objdump_checks,
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
        elif object_status == "ready":
            print(f"object workflow: READY ({objdump_path})")
            print(
                "object format support: VERIFIED (GNU syntax, MIPS ELF + relocations)"
            )
        else:
            print("object workflow: LIMITED")
            print(f"  {objdump_error}")
        cache_label = "UNREADABLE" if cache_error else "LARGE" if cache_large else "OK"
        print(
            f"campaign cache: {cache_label} - {cache_files} file(s), "
            f"{format_bytes(cache_bytes)} ({cache_bytes} bytes; {display_path(cache)})"
        )
        if cache_error:
            print(f"  error: {cache_error}")
        if cache_large:
            print(
                "  next: decomp-workbench cache prune --max-size 1GiB "
                f"--cache-dir {shlex.quote(str(cache))}"
            )
            print("  note: this is a dry run; add --apply only after inspection")
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
        or (args.objdump is not None and objdump_path is None)
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


def allocation_progress_label(comparison: Comparison) -> str:
    """Render the lane-prefix fields used by late-stage campaign ranking."""

    pool = "exact" if comparison.pool_exact else str(comparison.pool_prefix_exact)
    temp = (
        "exact"
        if comparison.temp_prefix_exact is None
        else str(comparison.temp_prefix_exact)
    )
    first = (
        "exact"
        if comparison.first_divergent_row is None
        else str(comparison.first_divergent_row)
    )
    return f"pool={pool} temp-prefix={temp} first-row={first}"


def campaign_ranking_label(results: list[CompileResult], *, requested: str) -> str:
    """Name the scale that actually ordered one campaign result set."""

    if requested != "auto":
        return requested
    return (
        "words"
        if any(
            item.comparison is not None and not item.comparison.alignment_comparable
            for item in results
        )
        else "aligned_total"
    )


def campaign_alignment_ranking_unsafe(results: list[CompileResult]) -> bool:
    """Say whether aligned totals lack a common scale for this population."""

    return any(
        item.comparison is not None and not item.comparison.alignment_comparable
        for item in results
    )


def compile_rank_command(args: argparse.Namespace) -> int:
    """Compatibility ranking surface backed by the campaign engine."""

    try:
        environment = parse_environment(args.env)
        if args.toolchain:
            environment = merge_toolchain_environment(environment, args.toolchain)
        environment = resolve_compiler_environment(environment, args.inherit_env)
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
            rank_by=args.rank_by,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    successes = [
        (item, item.comparison) for item in results if item.comparison is not None
    ]
    failures = [item for item in results if item.comparison is None]
    ranked_by = campaign_ranking_label(results, requested=args.rank_by)
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
        if ranked_by == "words" and args.rank_by == "auto":
            print(MIXED_ALIGNMENT_CAUTION)
        for rank, (_, comparison) in enumerate(successes[: args.limit or None], 1):
            progress = (
                f" [{allocation_progress_label(comparison)}]"
                if args.rank_by == "temp-prefix"
                else ""
            )
            print(f"{rank:3d} {comparison_line(comparison)}{progress}")
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
    control_report: dict[str, Any] = {
        "status": "NOT DECLARED",
        "passed": True,
        "receipts": [],
    }
    try:
        if args.no_ledger and args.ledger:
            raise ValueError("--ledger and --no-ledger are mutually exclusive")
        environment = parse_environment(args.env)
        if args.toolchain:
            environment = merge_toolchain_environment(environment, args.toolchain)
        environment = resolve_compiler_environment(environment, args.inherit_env)
        compile_cwd = (
            Path(args.compile_cwd).expanduser().resolve()
            if args.compile_cwd
            else Path.cwd().resolve()
        )
        compilation_envelope = {
            key: value
            for key, value in {
                "compiler_id": args.compiler_id,
                "frontend": args.frontend,
                "language": args.language,
                "driver": args.driver,
                "backend": args.backend,
            }.items()
            if value
        }
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
                compilation_envelope=compilation_envelope,
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
                experiment=(
                    experiment.identity_receipt()
                    if experiment is not None
                    and experiment.schema == EXPERIMENT_SCHEMA_V2
                    else None
                ),
                compilation_envelope=compilation_envelope,
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
                rank_by=args.rank_by,
                retain_sources=args.retain_sources,
            )
            effective_ledger = ledger_path
        if experiment is not None and experiment.controls:
            control_report = run_control_preflight(
                experiment,
                target=target,
                template=args.compile_command,
                cache_dir=args.cache_dir,
                objdump=objdump,
                symbol=args.symbol,
                section=args.section,
                environment=environment,
                compile_cwd=compile_cwd,
                timeout=args.timeout,
                stream_limit=args.stream_limit,
                artifact_dir=args.artifact_dir,
                compilation_envelope=compilation_envelope,
            )
            if manifest_path is not None:
                record_control_preflight(manifest_path, control_report)
            if not control_report["passed"]:
                if manifest_path is not None:
                    finish_manifest(
                        manifest_path,
                        results=0,
                        prepared=len(candidates),
                        exact=False,
                        control_invalid=True,
                    )
                failure_payload: dict[str, Any] = {
                    "schema": "decomp-workbench-campaign-v1",
                    "status": "control-invalid",
                    "manifest": str(manifest_path) if manifest_path else None,
                    "controls": control_report,
                    "unique_candidates": 0,
                    "prepared_candidates": len(candidates),
                    "results": [],
                }
                if args.json or args.json_summary:
                    print(json.dumps(failure_payload, indent=2, sort_keys=True))
                else:
                    print(
                        "controls: FAIL — ordinary candidates were not scheduled",
                        file=sys.stderr,
                    )
                    for receipt in control_report["receipts"]:
                        print(
                            f"  {receipt['id']}: {receipt['status']} — "
                            f"{receipt['reason']}",
                            file=sys.stderr,
                        )
                return 2
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
            signal_specs=experiment.signals if experiment else (),
            compilation_envelope=compilation_envelope,
            rank_by=args.rank_by,
        )
        if manifest_path is not None:
            finalize_source_retention(manifest_path)
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
    basins = group_object_basins(results, rank_by=args.rank_by)
    ranked_by = campaign_ranking_label(results, requested=args.rank_by)
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
                    "signals": item.signals,
                    "object_sha256": item.object_sha256,
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
                    "rank_by": args.rank_by,
                    "ranked_by": ranked_by,
                    "alignment_ranking_unsafe": campaign_alignment_ranking_unsafe(
                        results
                    ),
                    "manifest": str(manifest_path) if manifest_path else None,
                    "ledger": str(effective_ledger) if effective_ledger else None,
                    "experiment": experiment.as_dict() if experiment else None,
                    "controls": control_report,
                    "object_basins": [basin_summary(basin) for basin in basins],
                    "results": serialized_results,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        if ranked_by == "words" and args.rank_by == "auto":
            print(MIXED_ALIGNMENT_CAUTION)
        if control_report["status"] != "NOT DECLARED":
            print(
                f"controls: {control_report['passed_required']}/"
                f"{control_report['required']} required PASS"
            )
        for rank, result in enumerate(shown, 1):
            if result.comparison:
                cache = "cache" if result.cached else "built"
                print(
                    f"{rank:3d} {comparison_line(result.comparison)} "
                    f"[{cache} {result.duration_seconds:.2f}s]"
                    + (
                        f" [{allocation_progress_label(result.comparison)}]"
                        if args.rank_by == "temp-prefix"
                        else ""
                    )
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


def allocator_color_label(color: int | None) -> str:
    """Render a selected color without producing user-facing ``cNone``."""

    if color is None:
        return "-"
    return f"c{color}({register_for_color(color) or '-'})"


def parse_register_list(value: str | None) -> list[int] | None:
    if value is None:
        return None
    return [parse_register(item) for item in value.split(",") if item.strip()]


def trace_fifo_command(args: argparse.Namespace) -> int:
    try:
        events = parse_trace(Path(args.trace).read_text(encoding="utf-8"))
        emission_map = (
            parse_emission_map(
                json.loads(Path(args.emission_map).read_text(encoding="utf-8"))
            )
            if args.emission_map
            else None
        )
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
            emission_map=emission_map,
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
        join = report.as_dict()["emission_join"]
        if isinstance(join, dict) and join["with_emitted_index"]:
            print(
                "emission join: "
                f"emitted={join['with_emitted_index']}/"
                f"{join['logical_events']} rows={join['with_object_row']} "
                f"source={join['with_source_line']} "
                f"complete={'yes' if join['complete'] else 'no'}"
            )
            if join["calibration_required"]:
                print(
                    "note: emitted ordinals are not object rows; pass "
                    "--emission-map to supply measured calibration"
                )
        for violation in report.violations:
            print(f"VIOLATION {violation}", file=sys.stderr)
        if args.show_events:
            for event in report.logical_events:
                emitted = (
                    event.emitted_index if event.emitted_index is not None else "-"
                )
                object_row = event.object_row if event.object_row is not None else "-"
                print(
                    f"{event.action:8s} v{event.value:<4d} "
                    f"{register_name(event.register):>3s} "
                    f"emit={emitted:>5} "
                    f"row={object_row:>5} "
                    f"source={event.source_line or '-':>5} "
                    f"trace={event.trace_line}"
                )
                if event.instruction or event.source_file:
                    location = f"{event.source_file or '?'}:{event.source_line or '?'}"
                    print(f"         {location}  {event.instruction or '-'}")
    return 1 if args.fail_on_violation and not report.valid else 0


def _lineage_notes(
    report: Any, lineage: Sequence[Any], *, requested: set[int]
) -> list[str]:
    """Explain an empty `--lineage-table` result instead of returning silence.

    Formation records are opt-in at *capture* time: the instrumentation emits
    `lineage_range`/`lineage_member` only when `CDX_LINEAGE_TABLES` names the
    table. A trace captured with `CDX_DETAIL_WEB` alone therefore contains
    `webdetail` records naming the table and no lineage record for it, and the
    command printed `lineage=0` with no reason -- which reads as "this table
    does not exist" rather than "this trace was not captured for it".
    """

    if not requested or lineage:
        return []
    known = report.webdetail_tables()
    present = sorted(requested & known)
    notes = []
    if present:
        named = ", ".join(str(value) for value in present)
        notes.append(
            f"note: table {named} appears on webdetail records in this trace, "
            "but it carries no formation records for it."
        )
    notes.append(
        "note: lineage_range/lineage_member are opt-in at capture time. "
        "Re-capture with CDX_LINEAGE_TABLES naming the table(s); "
        "CDX_DETAIL_WEB alone does not emit them."
    )
    if not present and known:
        notes.append(
            "note: webdetail tables present in this trace: "
            + ", ".join(str(value) for value in sorted(known)[:12])
        )
    return notes


def trace_globalcolor_command(args: argparse.Namespace) -> int:
    if args.web is not None and args.proc is None:
        print(
            "error: --web requires --proc so the allocator lookup is unambiguous",
            file=sys.stderr,
        )
        return 2
    if args.lineage_table and args.proc is None:
        print(
            "error: --lineage-table requires --proc so formation records are "
            "not mixed across procedures",
            file=sys.stderr,
        )
        return 2
    desired_color = None
    if args.desired_register is not None:
        if args.web is None or args.proc is None:
            print(
                "error: --desired-register requires --proc and --web",
                file=sys.stderr,
            )
            return 2
        desired_color = color_for_register(args.desired_register)
        if desired_color is None:
            known = ", ".join(sorted(set(COLOR_REGISTERS.values())))
            print(
                f"error: unknown allocator register {args.desired_register!r}; "
                f"known registers: {known}",
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
    lineage_only = bool(args.lineage_table) and args.web is None and args.dtype is None
    allocator_webs = (
        []
        if lineage_only
        else report.allocator_webs(
            proc=args.proc, web=args.web, dtype=args.dtype, limit=args.top
        )
    )
    decisions = [] if lineage_only else report.decisions_for(args.proc, web=args.web)
    lineage_tables = set(args.lineage_table)
    if args.web is not None:
        lineage_tables.update(
            table
            for item in allocator_webs
            if (table := optional_integer(item.detail.get("table"))) is not None
        )
    lineage = report.lineage_for(
        args.proc,
        tables=lineage_tables or None,
    )
    lineage_notes = _lineage_notes(report, lineage, requested=set(args.lineage_table))
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
    elif args.proc is not None and not allocator_webs and not decisions and not lineage:
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
                        "desired_register": args.desired_register,
                        "dtype": args.dtype,
                        "proc": args.proc,
                        "top": args.top,
                        "web": args.web,
                    },
                    "legacy_live_range_capture": (
                        "present" if report.live_ranges else "not-captured"
                    ),
                    "live_ranges": [item.as_dict() for item in selected],
                    "allocator_webs": [item.as_dict() for item in allocator_webs],
                    "lineage": [item.as_dict() for item in lineage],
                    "color_barriers": [
                        item.color_barrier(desired_color)
                        for item in allocator_webs
                        if desired_color is not None
                    ],
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
            # A `--lineage-table` miss exits here rather than through the
            # summary, and its explanation is the whole point of asking: this
            # is the path a reader who saw "silently returns nothing" was on.
            for note in lineage_notes:
                print(note)
            if lineage_notes:
                print("lineage=0")
            return 1
        for item in selected:
            costs = sorted(item.eligible_costs, key=lambda entry: entry.cost)
            best = f"r{costs[0].register}:{costs[0].cost:g}" if costs else "-"
            print(
                f"bitpos={item.bitpos:5d} dtype={item.dtype:2d} "
                f"weight={item.weight:5d} "
                f"adjsave={item.adjusted_save:11g} "
                f"total={item.total_save:13g} best={best}"
            )
        for allocator_item in allocator_webs:
            detail = allocator_item.detail
            natural_label = allocator_color_label(allocator_item.natural_color)
            assigned_label = allocator_color_label(allocator_item.assigned_color)
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
                f"natural={natural_label} "
                f"assigned={assigned_label} "
                f"force={allocator_item.fields.get('forced', '-2')} "
                f"decision={allocator_item.fields.get('decision', '?')} "
                f"bb={detail.get('bb', '?')} line={detail.get('line', '?')} "
                f"costs={cost_text or '-'}\n"
                f"  {allocator_item.explanation}"
            )
            if desired_color is not None:
                barrier = allocator_item.color_barrier(desired_color)
                barrier_natural = allocator_color_label(
                    cast(int | None, barrier["natural_color"])
                )
                print(
                    "  barrier: "
                    f"desired=c{barrier['desired_color']}"
                    f"({barrier['desired_register'] or '-'}) "
                    f"cost={barrier['desired_cost']} "
                    f"natural={barrier_natural} "
                    f"cost={barrier['natural_cost']} "
                    f"gap={barrier['cost_gap']} "
                    f"forbidden={'yes' if barrier['desired_forbidden'] else 'no'} "
                    f"ineligible={'yes' if barrier['desired_ineligible'] else 'no'}"
                )
                print(f"    {barrier['advice']}")
                blocking_neighbors = cast(
                    list[dict[str, object]], barrier["blocking_neighbors"]
                )
                for blocker in blocking_neighbors:
                    blocker_detail = cast(dict[str, object], blocker["detail"])
                    print(
                        "    blocker: "
                        f"{blocker['force_key']} "
                        f"assigned=c{blocker['assigned_color']}"
                        f"({blocker['assigned_register'] or '-'}) "
                        f"dtype={blocker_detail.get('dtype', '?')} "
                        f"type={blocker_detail.get('type', '?')} "
                        f"table={blocker_detail.get('table', '?')}"
                    )
                print(f"    {barrier['claim_boundary']}")
        for lineage_item in lineage:
            fields = lineage_item.fields
            if lineage_item.phase == "lineage_range":
                print(
                    "lineage range: "
                    f"proc={fields.get('proc', '?')} "
                    f"event={fields.get('event', '?')} "
                    f"table={fields.get('table', '?')} "
                    f"chain={fields.get('chain', '?')} "
                    f"type={fields.get('type', '?')} "
                    f"dtype={fields.get('dtype', '?')}"
                )
            else:
                print(
                    "lineage member: "
                    f"proc={fields.get('proc', '?')} "
                    f"event={fields.get('event', '?')} "
                    f"table={fields.get('table', '?')} "
                    f"chain={fields.get('chain', '?')} "
                    f"bb={fields.get('bb', '?')} "
                    f"line={fields.get('line', '?')} "
                    f"flags={fields.get('flags', '?')}"
                )
        if report.live_ranges:
            live_range_status = (
                f"legacy-live-ranges={len(selected)}/{len(report.live_ranges)}"
            )
        else:
            live_range_status = "legacy-live-ranges=not-captured(CSAVE/CUP absent)"
        print(
            f"{live_range_status} allocator-webs={len(allocator_webs)} "
            f"decisions={len(decisions)} "
            f"lineage={len(lineage)} "
            f"unparsed={len(report.unparsed_diagnostic_lines)}"
        )
        for note in lineage_notes:
            print(note)
    if lookup_error:
        return 1
    return 0 if selected or allocator_webs or decisions or lineage else 1


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
    register_window_commands(commands)
    # `align` reads the same two objects and answers the question that comes
    # before every metric `compare` reports: are these two streams even the
    # same length, and if not, what did the candidate add?
    register_align_commands(commands)
    # `phase` reads the rows `align` paired, and answers the question that
    # follows: of the rows that differ, how many are a ring rotation?
    register_phase_commands(commands)
    # `shift` asks the same question one scale up: `align` is shift-tolerant
    # about one function's rows, and `shift audit` is about a whole linked
    # image's addresses.
    register_shift_commands(commands)
    # `target audit` asks the question one stage earlier than either: is the
    # object a campaign is about to spend days matching against even the
    # right scope to begin with.
    register_target_commands(commands)
    register_collateral_command(commands)
    register_rank_command(commands, handler=rank_command)
    register_guide_command(commands)
    register_handoff_command(commands)
    register_discovery_commands(commands)
    register_scheduler_commands(commands)
    register_allocator_commands(commands)
    register_a71_command(commands)
    # The cascade family reads the same instrumented build the `trace`
    # commands read, and answers the question they leave open: what
    # happened at one site, in every round, and what colour it really got.
    register_cascade_commands(commands)
    # `force-rows` reads objects but speaks the allocator's vocabulary: its
    # input is a force control, and it answers the question the allocator
    # journey leaves open -- which rows that control actually owns.
    register_force_rows_commands(commands)
    register_source_correlation_command(commands)
    register_pass_adapter_command(commands)
    # Inspect the retained ugen-to-as1 stream before treating a late register
    # rewrite as an allocator or source-shape problem.
    register_binasm_command(commands)
    # Inspect the preceding uopt-to-ugen stream when a switch's XJP range or
    # selector normalization owns the control-flow shape.
    register_ucode_command(commands)
    # Retain those streams in the first place: the arg-preserving wrappers
    # that make a normal build leave every pass boundary on disk.
    register_capture_commands(commands)
    # Read, compare and edit the retained streams by record.
    register_stream_commands(commands)
    # Replay one edited stream through the stock phases with the captured
    # argv, so a boundary hypothesis is proven before any C is hunted for it.
    register_replay_ugen_command(commands)
    # Bounded decomp-permuter searches whose scratch reproduces the real
    # per-object recipe: the search half of the same boundary `campaign`
    # draws, for the residuals no hand lever moves.
    register_permute_commands(commands)
    register_line_probe_command(commands)
    # Two source-level probes: the same-value check one campaign never ran,
    # and the zero-footprint construct no object diff can point at.
    register_source_probe_commands(commands)
    # `slots` reads the same object the other object commands read and
    # answers what a fusion donor costs, without a build.
    register_slots_command(commands)
    # The search half of the same boundary `campaign` draws: emit a variant
    # family and its manifest, let the project's wrapper build them, read the
    # objects back gated, scored, and with the coverage the family declared.
    register_sweep_commands(commands)
    register_fingerprint_commands(commands)
    register_relocation_command(commands)
    register_fidelity_command(commands)
    # The identity gate, recorded: an instrumented pass whose traces are
    # evidence has to have reproduced the stock object first.
    register_instrument_gate_command(commands)
    register_toolchain_commands(commands)
    register_oracle_commands(commands)
    register_experiment_commands(commands)
    register_score_command(commands)
    register_matrix_command(commands)
    register_note_commands(commands)
    register_next_command(commands)

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
    register_decompme_commands(commands)
    register_project_commands(commands, dispatch=main)

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
        "--emission-map",
        help=(
            "JSON mapping instrumented emitted indices to object rows and "
            "optional source locations"
        ),
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
        "--desired-register",
        help=(
            "measure the cost/interference barrier to this register; requires "
            "--proc and --web"
        ),
    )
    color_parser.add_argument(
        "--web",
        type=int,
        help="inspect one allocator web; pair with --proc for an unambiguous lookup",
    )
    color_parser.add_argument(
        "--lineage-table",
        type=int,
        action="append",
        default=[],
        help=(
            "show pre-globalcolor formation for this ICHAIN table; repeat for "
            "more tables and pair with --proc"
        ),
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
        "--compiler-id",
        help="canonical decomp.me compiler id, distinct from the display label",
    )
    bundle_parser.add_argument(
        "--language",
        help="decomp.me language selection (for example C or C++)",
    )
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
