"""CLI for the line-assignment probe (``decomp-workbench probe-lines``)."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .cli_options import add_process_output_arguments, add_symbol_argument
from .environment import parse_environment
from .line_probe import (
    DEFAULT_SHIFT_LINES,
    DEFAULT_SPLIT_THRESHOLD,
    DEFAULT_WORK_DIR,
    PREPROCESSED_INPUT_HELP,
    VARIANT_DESCRIPTIONS,
    VARIANT_NAMES,
    VERDICT_NONDETERMINISTIC,
    run_line_probe,
)

FUNCTION_HELP = (
    "window the comparison to this function's byte range, read from the "
    "compiled object's ELF symbol table"
)

DESCRIPTION = (
    "Compile a preprocessed C file as three deterministic variants and "
    "report whether statement line assignment participates in late-pass "
    "scheduling: baseline (untouched), split-statements (a token-identical "
    "reflow - a newline after each ';' on an overlong line), and "
    "global-shift (a control: blank lines prepended, never expected to "
    "move the object). --tie adds a fourth variant that reassigns one "
    "statement's line number, which is the follow-up question: not 'does "
    "line assignment own this?' but 'which line does this statement need?'. "
    "The input is " + PREPROCESSED_INPUT_HELP + "."
)

EPILOG = (
    "Variants: "
    + "; ".join(
        f"{name} - {VARIANT_DESCRIPTIONS[name]}" for name in (*VARIANT_NAMES, "tie")
    )
    + ". Verdicts: LINE-SENSITIVE (split moved the object, shift did not - "
    "see field-guide lever 23, preprocessor line assignment); "
    "NOT line-sensitive (neither moved); NONDETERMINISTIC (shift moved - "
    "the compile itself is untrustworthy, not just this probe). "
    "See docs/line-assignment-probe.md for the worked drawbitmap numbers."
)


def _parse_ties(entries: list[str]) -> list[tuple[int, int]]:
    ties: list[tuple[int, int]] = []
    for entry in entries:
        statement, separator, assigned = entry.partition("=")
        if not separator or not statement.isdigit() or not assigned.isdigit():
            raise ValueError(
                f"--tie {entry!r} is not STATEMENT=LINE (two 1-based line "
                "numbers, e.g. --tie 83=88)"
            )
        ties.append((int(statement), int(assigned)))
    return ties


def probe_lines_command(args: argparse.Namespace) -> int:
    try:
        environment = parse_environment(args.env)
        report = run_line_probe(
            args.input,
            compile_template=args.compile_command,
            function=args.symbol,
            split_threshold=args.split_threshold,
            shift_lines=args.shift_lines,
            work_dir=args.work_dir,
            compile_cwd=args.compile_cwd,
            environment=environment,
            timeout=args.timeout,
            stream_limit=args.stream_limit,
            artifact_dir=args.artifact_dir,
            target_bytes=args.target_bytes,
            target_offset=args.target_offset,
            target_object=args.target_object,
            ties=_parse_ties(args.tie),
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_report(report)
    return 1 if report["verdict"] == VERDICT_NONDETERMINISTIC else 0


def _print_report(report: dict[str, Any]) -> None:
    print(f"input: {report['input']}")
    print(f"function: {report['function'] or '(whole .text)'}")
    print(
        f"split-threshold: {report['split_threshold']} char(s)   "
        f"shift-lines: {report['shift_lines']}"
    )
    ties = report.get("ties") or []
    if ties:
        print(
            "ties: "
            + ", ".join(f"{statement}->{assigned}" for statement, assigned in ties)
        )
    for name in report["variants"]:
        variant = report["variants"][name]
        print(
            f"  {name:17s} words={variant['word_count']:<6d} window={variant['window']}"
        )
    print(f"split-statements vs baseline: {report['split_word_diff']} word(s) differ")
    print(f"global-shift vs baseline:     {report['shift_word_diff']} word(s) differ")
    if report.get("tie_word_diff") is not None:
        print(f"tie vs baseline:              {report['tie_word_diff']} word(s) differ")
    print(f"verdict: {report['verdict']}")
    for line in report["message"].splitlines():
        print(line)
    target = report.get("target")
    if target:
        baseline_mismatch = target["baseline"]["mismatched_vs_target"]
        print(f"target: baseline differs from target at {baseline_mismatch} site(s)")
        moved_names = ["split-statements", "global-shift"]
        if "tie" in target:
            moved_names.append("tie")
        for name in moved_names:
            score = target[name]
            print(
                f"target: {name} moved toward target at {score['toward']} "
                f"site(s), away at {score['away']}, unchanged at "
                f"{score['unchanged']} (of {score['total_positions']} "
                f"compared position(s); {score['mismatched_vs_target']} "
                "still differ)"
            )
    # The verdict names the mechanism; these name the next command. They are
    # printed after the target scores because the tie's routing depends on
    # them.
    for step in report.get("next_steps") or ():
        print(f"next: {step}")
    print(f"run directory: {report['run_directory']}")


def register_line_probe_command(commands: argparse._SubParsersAction[Any]) -> None:
    parser = commands.add_parser(
        "probe-lines",
        help="probe whether statement line assignment owns a schedule residue",
        description=DESCRIPTION,
        epilog=EPILOG,
    )
    parser.add_argument(
        "input", help=f"preprocessed .i file - {PREPROCESSED_INPUT_HELP}"
    )
    parser.add_argument(
        "--compile-command",
        required=True,
        help="command template containing {input} and {output}",
    )
    add_symbol_argument(parser, help_text=FUNCTION_HELP)
    parser.add_argument(
        "--split-threshold",
        type=int,
        default=DEFAULT_SPLIT_THRESHOLD,
        metavar="CHARS",
        help=(
            "only reflow physical lines longer than this "
            f"(default: {DEFAULT_SPLIT_THRESHOLD})"
        ),
    )
    parser.add_argument(
        "--shift-lines",
        type=int,
        default=DEFAULT_SHIFT_LINES,
        metavar="N",
        help=(
            "blank lines the global-shift control prepends "
            f"(default: {DEFAULT_SHIFT_LINES})"
        ),
    )
    parser.add_argument(
        "--tie",
        action="append",
        default=[],
        metavar="STATEMENT=LINE",
        help=(
            "reassign the statement on 1-based input line STATEMENT to line "
            "number LINE via a #line pair (a fourth 'tie' variant); "
            "repeatable - the probe that converts a line-owned schedule "
            "residue into a fix"
        ),
    )
    parser.add_argument(
        "--target-bytes",
        help="score every variant against this raw binary file (word diff)",
    )
    parser.add_argument(
        "--target-offset",
        type=int,
        default=0,
        metavar="N",
        help="byte offset into --target-bytes (default: 0)",
    )
    parser.add_argument(
        "--target-object",
        help="score every variant against this object's ELF-windowed .text",
    )
    parser.add_argument(
        "--work-dir",
        default=DEFAULT_WORK_DIR,
        help=f"project-visible run root (default: {DEFAULT_WORK_DIR})",
    )
    parser.add_argument(
        "--compile-cwd",
        help="working directory for the compile command",
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="explicit compiler environment entry; repeatable",
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    add_process_output_arguments(parser)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.set_defaults(handler=probe_lines_command)
