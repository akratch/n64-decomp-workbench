"""Argument registration for scratch import, readiness, and skill handoffs."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from .cli_options import (
    add_explain_keys_argument,
    add_process_output_arguments,
    add_symbol_argument,
)
from .view_cli import add_view_render_arguments

Handler = Callable[[argparse.Namespace], int]


def register_scratch_commands(
    commands: argparse._SubParsersAction[Any],
    *,
    check_handler: Handler,
    doctor_handler: Handler,
    skill_handler: Handler,
) -> None:
    check = commands.add_parser(
        "check-scratch",
        help="inspect or site-faithfully compile a decomp.me export",
        description=(
            "Validate an exported ZIP/directory, distinguish the site's display "
            "score from aligned object truth, and optionally compile context plus "
            "source with decomp.me's #line reset."
        ),
    )
    check.add_argument(
        "scratch",
        help="decomp.me export ZIP/directory or workbench scratch bundle",
    )
    add_symbol_argument(
        check,
        help_text=(
            "compare this symbol; defaults to metadata.json's diff_label; "
            "--function is the same option"
        ),
    )
    add_explain_keys_argument(check)
    check.add_argument(
        "--compile-command",
        help="command template containing {source} and {output}",
    )
    check.add_argument(
        "--source",
        help="candidate code to place after ctx.c; defaults to exported code.c",
    )
    check.add_argument(
        "--project-object",
        help=(
            "object produced by the normal project translation unit; compare it "
            "against the same target without replacing scratch truth"
        ),
    )
    check.add_argument(
        "--project-source",
        help=(
            "optional project translation-unit source used only to qualify "
            "context/prototype hypotheses; requires --project-object"
        ),
    )
    check.add_argument("--compile-cwd", help="working directory for the compiler")
    check.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="compiler environment entry; repeatable",
    )
    check.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="compiler timeout in seconds (default: 120)",
    )
    add_process_output_arguments(check)
    check.add_argument(
        "--keep-composed",
        metavar="PATH",
        help="retain the exact context + line reset + source input",
    )
    check.add_argument(
        "--keep-object",
        metavar="PATH",
        help="retain the newly compiled object",
    )
    check.add_argument(
        "--section",
        default=".text",
        help="object section (default: .text)",
    )
    check.add_argument(
        "--objdump",
        help="GNU-compatible MIPS objdump; auto-detected when omitted",
    )
    check.add_argument(
        "--show-diff",
        action="store_true",
        help="print every differing site, grouped by class",
    )
    check.add_argument(
        "--view",
        action="store_true",
        help="include the aligned mechanism view from the same loaded evidence",
    )
    add_view_render_arguments(
        check,
        default_max_hunks=1,
        show_all_help=(
            "with --view, render every hunk and the complete register lanes "
            "(overrides --max-hunks/--lane-window)"
        ),
    )
    check.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="return exit 1 unless an available comparison is exact",
    )
    check.add_argument("--json", action="store_true", help="emit JSON")
    check.set_defaults(handler=check_handler)

    doctor = commands.add_parser(
        "doctor",
        help="check local readiness and validate an optional scratch",
        description=(
            "Report Python, retained-dump, and object-reader readiness; when a "
            "scratch is supplied, validate it and print the exact next command."
        ),
    )
    doctor.add_argument(
        "scratch",
        nargs="?",
        help="optional decomp.me export ZIP/directory or workbench bundle",
    )
    doctor.add_argument(
        "--objdump",
        help="GNU-compatible MIPS objdump; auto-detected when omitted",
    )
    doctor.add_argument(
        "--cache-dir",
        default=".decomp-workbench/cache",
        help="campaign cache to inspect (default: .decomp-workbench/cache)",
    )
    doctor.add_argument(
        "--compile-command",
        help="preflight a wrapper template containing {source} and {output}",
    )
    doctor.add_argument(
        "--toolchain",
        help="verify a real-copy workbench toolchain and use it for preflight",
    )
    doctor.add_argument("--compile-cwd", help="working directory for the preflight")
    doctor.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="compiler environment entry for the preflight; repeatable",
    )
    doctor.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="compiler preflight timeout in seconds (default: 120)",
    )
    add_process_output_arguments(doctor)
    doctor.add_argument("--json", action="store_true", help="emit JSON")
    doctor.set_defaults(handler=doctor_handler)

    skill = commands.add_parser(
        "install-skill",
        help="install the bundled N64 decomp Agent Skill",
        description=(
            "Install n64-decomp-campaign for Codex or Claude Code. "
            "Existing differing installations are never overwritten."
        ),
    )
    skill.add_argument("client", choices=("codex", "claude"))
    skill.add_argument(
        "--destination",
        help=(
            "parent skills directory; defaults to the selected client's "
            "personal skills directory"
        ),
    )
    skill.add_argument("--json", action="store_true", help="emit JSON")
    skill.set_defaults(handler=skill_handler)
