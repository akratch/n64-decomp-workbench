"""Argument registration for source campaign journeys."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from typing import Any

from .cli_options import add_process_output_arguments
from .object_cli import add_common_compare_arguments

Handler = Callable[[argparse.Namespace], int]


def register_campaign_run_commands(
    commands: argparse._SubParsersAction[Any],
    *,
    compile_rank_handler: Handler,
    campaign_handler: Handler,
) -> None:
    """Register legacy-compatible run surfaces apart from their handlers."""

    compile_rank = commands.add_parser(
        "compile-rank",
        help="compile and rank C source candidates",
        description=(
            "Compatibility convenience backed by the same cached, in-process "
            "engine as campaign. Use campaign for persistent state and resume."
        ),
    )
    compile_rank.add_argument("target", help="reference object")
    compile_rank.add_argument("sources", nargs="+", help="candidate C files")
    compile_rank.add_argument(
        "--compile-command",
        required=True,
        help="command template containing {source} and {output}",
    )
    compile_rank.add_argument(
        "--toolchain",
        help="verified real-copy toolchain; supplies its path-sensitive environment",
    )
    compile_rank.add_argument(
        "--keep-objects",
        help="directory in which to retain compiled objects",
    )
    compile_rank.add_argument(
        "--cache-dir",
        default=".decomp-workbench/cache",
        help="content-cache directory",
    )
    compile_rank.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="compiler environment entry; repeatable",
    )
    compile_rank.add_argument(
        "--compile-cwd",
        help="working directory for compiler processes",
    )
    compile_rank.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="per-candidate compiler timeout in seconds (default: 120)",
    )
    compile_rank.add_argument(
        "--limit",
        type=int,
        default=20,
        help="maximum results to show",
    )
    compile_rank.add_argument(
        "--rank-by",
        choices=("auto", "words", "temp-prefix"),
        default="auto",
        help=(
            "candidate ordering: automatic aligned/positional safety, "
            "positional words, or latest exact temp-lane prefix"
        ),
    )
    add_process_output_arguments(compile_rank)
    add_common_compare_arguments(compile_rank)
    compile_rank.set_defaults(handler=compile_rank_handler)

    campaign = commands.add_parser(
        "campaign",
        help="run a parallel, cached candidate campaign",
        description="Compile, cache, rank, and record source candidates.",
    )
    campaign.add_argument("target", help="reference object")
    campaign.add_argument("sources", nargs="+", help="candidate C files")
    campaign.add_argument(
        "--compile-command",
        required=True,
        help="command template containing {source} and {output}",
    )
    campaign.add_argument(
        "--toolchain",
        help="verified real-copy toolchain; supplies its path-sensitive environment",
    )
    campaign.add_argument(
        "--compiler-id",
        help="canonical compiler build identity for this campaign cell",
    )
    campaign.add_argument(
        "--frontend",
        help="frontend family, such as IRIX 4.x accom or later cfe",
    )
    campaign.add_argument("--language", help="source language/dialect for this cell")
    campaign.add_argument("--driver", help="historical or wrapper driver identity")
    campaign.add_argument(
        "--backend",
        help="backend identity when a historical frontend feeds a later backend",
    )
    campaign.add_argument(
        "--cache-dir",
        default=".decomp-workbench/cache",
        help="content-cache directory",
    )
    campaign.add_argument("--ledger", help="append results to this JSONL file")
    campaign.add_argument(
        "--no-ledger",
        action="store_true",
        help="disable the default manifest and append-only ledger",
    )
    campaign.add_argument(
        "--state-dir",
        default=".decomp-workbench",
        help="state namespace for default manifests and ledgers",
    )
    campaign.add_argument(
        "--experiment-manifest",
        help=(
            "experiment-v1/v2 sidecar describing family and candidates; v2 may "
            "also declare signals, controls, and coverage"
        ),
    )
    campaign.add_argument(
        "--jobs",
        type=int,
        default=max(1, min(8, os.cpu_count() or 1)),
        help="parallel compiler processes",
    )
    campaign.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="compiler environment included in the cache key; repeatable",
    )
    campaign.add_argument(
        "--compile-cwd",
        help="working directory for compiler processes; included in the cache key",
    )
    campaign.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="per-candidate compiler timeout in seconds (default: 120)",
    )
    campaign.add_argument(
        "--keep-objects",
        help="directory in which to retain compiled objects",
    )
    campaign.add_argument(
        "--limit",
        type=int,
        default=20,
        help="maximum results to show",
    )
    campaign.add_argument(
        "--rank-by",
        choices=("auto", "words", "temp-prefix"),
        default="auto",
        help=(
            "candidate ordering: automatic aligned/positional safety, "
            "positional words, or latest exact temp-lane prefix"
        ),
    )
    add_process_output_arguments(campaign)
    add_common_compare_arguments(campaign)
    campaign.add_argument(
        "--json-summary",
        action="store_true",
        help="emit compact JSON without compiler streams or instruction-level diffs",
    )
    campaign.add_argument(
        "--stop-on-exact",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "stop submitting candidates once one compares exact "
            "(default: enabled; pass --no-stop-on-exact to sweep every candidate)"
        ),
    )
    campaign.add_argument(
        "--show-basins",
        action="store_true",
        help="show source variants that compiled to each identical object basin",
    )
    campaign.set_defaults(handler=campaign_handler)
