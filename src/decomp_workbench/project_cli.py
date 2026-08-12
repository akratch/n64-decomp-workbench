"""Project discovery, explicit configuration, and configured object commands."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .discovery import subcommand_listing_handler
from .project_config import (
    discover_project,
    find_project_config,
    load_project_config,
    render_project_config,
    with_build_overrides,
    with_object_overrides,
    write_project_config,
)


def _config_path(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else find_project_config()


def project_init_command(args: argparse.Namespace) -> int:
    try:
        discovery = with_object_overrides(
            discover_project(args.root),
            target=args.target,
            candidate=args.candidate,
            symbol=args.symbol,
            objdump=args.objdump,
            input_mode="dumps" if args.dumps else "objects",
        )
        command = shlex.split(args.compile_command) if args.compile_command else None
        discovery = with_build_overrides(
            discovery,
            command=command,
            cwd=args.compile_cwd,
            environment=args.env,
            inherit_env=args.inherit_env,
            compiler_id=args.compiler_id,
            frontend=args.frontend,
            language=args.language,
            driver=args.driver,
            backend=args.backend,
        )
        rendered = render_project_config(discovery)
        if args.write:
            output = write_project_config(discovery)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        payload = discovery.as_dict()
        payload["written"] = str(output) if args.write else None
        payload["toml"] = rendered
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("Project discovery")
        for item in discovery.detected:
            print(f"  {item['kind']}: {item['path']}")
        if not discovery.detected:
            print("  no objdiff, Splat, or supported build metadata detected")
        for warning in discovery.warnings:
            print(f"  caution: {warning}")
        print("\nProposed configuration\n")
        print(rendered, end="")
        if args.write:
            print(f"Written: {output}")
        else:
            print("Preview only. Re-run with --write to create the file.")
    return 0


def project_show_command(args: argparse.Namespace) -> int:
    try:
        config = load_project_config(_config_path(args.config))
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    payload = config.as_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Project: {config.name or config.root.name}")
        print(f"Config: {config.path}")
        print(f"Root: {config.root}")
        print(f"Target: {config.target or 'not configured'}")
        print(f"Candidate: {config.candidate or 'not configured'}")
        print(f"Symbol: {config.symbol or 'whole section'}")
        print(f"Section: {config.section}")
        print(f"Objdump: {config.objdump or 'auto-discover'}")
        print(
            "Compiler command: "
            + (
                shlex.join(config.build_command)
                if config.build_command
                else "not configured"
            )
        )
        print(f"Frontend: {config.frontend or 'not configured'}")
        print(f"Backend: {config.backend or 'not configured'}")
    return 0


def configured_object_command(
    args: argparse.Namespace,
    *,
    command: str,
    dispatch: Callable[[list[str]], int],
) -> int:
    try:
        config = load_project_config(_config_path(args.config))
        extra = list(args.arguments)
        if extra[:1] == ["--"]:
            extra.pop(0)
        argv = [*config.object_argv(command), *extra]
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.print_command:
        print(shlex.join(("decomp-workbench", *argv)))
        return 0
    return dispatch(argv)


def configured_campaign_command(
    args: argparse.Namespace,
    *,
    dispatch: Callable[[list[str]], int],
) -> int:
    try:
        config = load_project_config(_config_path(args.config))
        argv = config.campaign_argv(args.sources)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.print_command:
        print(shlex.join(("decomp-workbench", *argv)))
        return 0
    return dispatch(argv)


def register_project_commands(
    commands: argparse._SubParsersAction[Any],
    *,
    dispatch: Callable[[list[str]], int],
) -> None:
    project = commands.add_parser(
        "project",
        help="discover and use durable project defaults",
        description=(
            "Preview conservative metadata discovery, write a portable project "
            "config explicitly, or run common object commands from it."
        ),
    )
    operations = project.add_subparsers(dest="project_command")
    project.set_defaults(handler=subcommand_listing_handler(project))

    init = operations.add_parser("init", help="preview or write project configuration")
    init.add_argument("root", nargs="?", default=".", help="project root")
    init.add_argument("--target", help="target object, relative to the project root")
    init.add_argument(
        "--candidate", help="candidate object, relative to the project root"
    )
    init.add_argument("--symbol", help="function symbol for object commands")
    init.add_argument("--objdump", help="explicit compatible objdump executable")
    init.add_argument(
        "--dumps",
        action="store_true",
        help="target and candidate are retained GNU objdump text, not objects",
    )
    init.add_argument(
        "--compile-command",
        help="compile-one argv template containing {source} and {output}",
    )
    init.add_argument("--compile-cwd", help="compiler working directory")
    init.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="fixed compiler environment value; repeatable",
    )
    init.add_argument(
        "--inherit-env",
        action="append",
        default=[],
        metavar="NAME",
        help="host environment name to record and inherit; repeatable",
    )
    init.add_argument("--compiler-id", help="canonical compiler identity")
    init.add_argument("--frontend", help="frontend lineage, such as IRIX 4.1 accom")
    init.add_argument("--language", help="source language/dialect identity")
    init.add_argument("--driver", help="compiler driver identity")
    init.add_argument("--backend", help="backend/pass lineage identity")
    init.add_argument(
        "--write",
        action="store_true",
        help="create .decomp-workbench.toml; never overwrite",
    )
    init.add_argument(
        "--json", action="store_true", help="emit discovery and proposed TOML as JSON"
    )
    init.set_defaults(handler=project_init_command, report_command="project-init")

    show = operations.add_parser(
        "show", help="show resolved, validated project defaults"
    )
    show.add_argument("--config", help="config path; otherwise search parents")
    show.add_argument("--json", action="store_true", help="emit JSON")
    show.set_defaults(handler=project_show_command, report_command="project-show")

    campaign = operations.add_parser(
        "campaign",
        help="run a campaign with configured target, build, environment, and lineage",
    )
    campaign.add_argument("sources", nargs="+", help="full-TU candidate sources")
    campaign.add_argument("--config", help="config path; otherwise search parents")
    campaign.add_argument(
        "--print-command",
        action="store_true",
        help="print the exact expanded command without running it",
    )
    campaign.set_defaults(
        handler=lambda args: configured_campaign_command(args, dispatch=dispatch),
        report_command="project-campaign",
    )

    for name in ("next", "compare", "diagnose"):
        operation = operations.add_parser(
            name,
            help=f"run {name} with configured target, candidate, symbol, and objdump",
        )
        operation.add_argument("--config", help="config path; otherwise search parents")
        operation.add_argument(
            "--print-command",
            action="store_true",
            help="print the exact expanded command without running it",
        )
        operation.add_argument(
            "arguments",
            nargs=argparse.REMAINDER,
            help=f"additional {name} options (place after --)",
        )
        operation.set_defaults(
            handler=lambda args, selected=name: configured_object_command(
                args, command=selected, dispatch=dispatch
            ),
            report_command=f"project-{name}",
        )


__all__ = ["register_project_commands"]
