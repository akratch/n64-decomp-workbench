"""CLI for the commands that are allowed to touch the network.

Each is explicit, single-purpose, and opt-in: nothing else in the package
calls out, and none of these runs as a step inside another command. Every
option that shapes the request — the API base, the timeout, the contact in the
`User-Agent` — is visible here rather than hidden in an environment variable.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .decompme_fetch import (
    DEFAULT_API_BASE,
    EXPORT_MEMBERS,
    fetch_scratch,
    scratch_url,
)
from .http_client import NetworkError, PoliteClient


def build_client(args: argparse.Namespace) -> PoliteClient:
    """Return the client one invocation will use.

    This is the seam the offline tests replace: everything below it is domain
    logic that never sees a socket, and everything above it is one function
    that builds a client from parsed options.
    """

    return PoliteClient(timeout=args.timeout, contact=args.contact)


def _add_client_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="seconds to wait for one request (default: 30)",
    )
    parser.add_argument(
        "--contact",
        help=(
            "contact appended to the User-Agent, so a server operator can "
            "reach whoever is making the requests"
        ),
    )
    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help=f"API root to query (default: {DEFAULT_API_BASE})",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")


def fetch_scratch_command(args: argparse.Namespace) -> int:
    try:
        report = fetch_scratch(
            args.slug,
            client=build_client(args),
            outdir=args.outdir,
            api_base=args.api_base,
            force=args.force,
            keep_archive=not args.no_archive,
        )
    except (NetworkError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    state = "reused cached export" if report["reused"] else "downloaded"
    print(f"scratch {report['slug']}: {state} -> {report['output']}")
    print(f"page: {scratch_url(report['slug'], api_base=args.api_base)}")
    print(f"members: {' '.join(sorted(report['files']))}")
    if report["missing_members"]:
        print(
            "not in this export: "
            + " ".join(report["missing_members"])
            + " (optional; check-scratch reports what it can measure)"
        )
    metadata = report["metadata"]
    score, maximum = metadata.get("score"), metadata.get("max_score")
    if score is not None and maximum is not None:
        print(f"decomp.me display: score={score}/{maximum}")
    for action in report["next_actions"]:
        print(f"next: {' '.join(action['command_argv'])}")
    return 0


def register_decompme_commands(commands: argparse._SubParsersAction[Any]) -> None:
    fetch = commands.add_parser(
        "fetch-scratch",
        help="download one decomp.me scratch export into the standard layout",
        description=(
            "Download a scratch export over HTTPS and unpack it to "
            f"OUTDIR/SLUG ({', '.join(EXPORT_MEMBERS)}), keeping the ZIP "
            "alongside it. The request identifies this workbench and its "
            "version honestly; a scratch already on disk is reported rather "
            "than downloaded again. This command opens a network connection, "
            "and it never runs implicitly."
        ),
    )
    fetch.add_argument("slug", help="decomp.me scratch slug or scratch URL")
    fetch.add_argument(
        "--outdir",
        default=".",
        help="directory to create SLUG/ inside (default: the current directory)",
    )
    fetch.add_argument(
        "--force",
        action="store_true",
        help="download again and replace an export already fetched here",
    )
    fetch.add_argument(
        "--no-archive",
        action="store_true",
        help="do not keep the downloaded ZIP next to the unpacked export",
    )
    _add_client_arguments(fetch)
    fetch.set_defaults(handler=fetch_scratch_command, report_command="fetch-scratch")
