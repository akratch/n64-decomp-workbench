"""CLI for `permute-sweep` and `permute-doctor`.

The sweep is the highest-value, zero-reasoning lever in a late-stage
campaign, and the one every host re-implements. Re-implementations keep
re-introducing the same fidelity faults, so the command forces the parts
that are not opinions -- real recovered flags, the replicated post-compile
chain, `--stack-diffs` -- and reports, rather than promotes, what it found.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .permute import (
    QueueItem,
    completed_functions,
    earlier_results,
    load_queue,
    load_ranking,
    order_queue,
    render_queue,
    render_table,
    sweep_payload,
)
from .permute_sweep import (
    PermuterError,
    doctor,
    render_doctor,
    resolve_plan,
    run_sweep,
    write_summary,
)
from .project_config import (
    PermuterOptions,
    find_project_config,
    load_project_config,
)

_SWEEP_DESCRIPTION = (
    "Drive decomp-permuter over a queue of functions with the fidelity a "
    "transferable result needs. Each function's scratch is built from the "
    "project's real recipe -- the codegen flags recovered from the build's "
    "own dry run, plus any post-compile objcopy chain replicated into the "
    "scratch's compile.sh -- and every search runs with --stack-diffs, "
    "because a normalized score reports a match for a spill at the wrong "
    "slot. The queue is ordered closest-first from a ranking, launches are "
    "niced and load-gated, and a run that hit its cap while still "
    "descending can be re-seeded once from its own best candidate. "
    "Promotion is deliberately out of scope: a scratch score of 0 is a "
    "candidate until the project's authoritative build says otherwise."
)

_DOCTOR_DESCRIPTION = (
    "Preflight one function before an hour is spent searching it. Reports "
    "the codegen flags recovered from the build, whether they came from the "
    "build or from a fallback, the post-compile objcopy steps the scratch "
    "replicated and the ones it could not, and whether the scratch base "
    "compiles to a finite, non-zero score. Each of the three has silently "
    "wasted whole campaign days: a scratch on the wrong ISA finds nothing "
    "and reads as a hard function; a scratch missing the objcopy chain "
    "finds a zero that does not transfer; a base that already scores 0 is "
    "not scoring the function under test at all."
)


def _load_options(args: argparse.Namespace) -> tuple[Path, PermuterOptions]:
    """Resolve the project root and its `[permuter]` defaults."""

    if getattr(args, "project", None):
        config_path = Path(args.project).expanduser()
        if config_path.is_dir():
            config_path = config_path / ".decomp-workbench.toml"
    else:
        config_path = find_project_config(".")
    config = load_project_config(config_path)
    return config.root, config.permuter


def _plan(args: argparse.Namespace, extra: list[str]) -> Any:
    root, options = _load_options(args)
    return resolve_plan(
        root,
        options,
        permuter_dir=args.permuter_dir,
        output_dir=args.output_dir,
        minutes=args.minutes,
        extend_minutes=getattr(args, "extend_minutes", 0) or 0,
        threads=args.threads,
        jobs=getattr(args, "jobs", None),
        load_threshold=args.load_threshold,
        make=args.make,
        extra=extra,
        cpu_count=os.cpu_count() or 4,
    )


def _forwarded(args: argparse.Namespace) -> list[str]:
    extra = list(getattr(args, "permuter_args", []) or [])
    return extra[1:] if extra and extra[0] == "--" else extra


def permute_sweep_command(args: argparse.Namespace) -> int:
    try:
        plan = _plan(args, _forwarded(args))
        queue = list(load_queue(args.queue))
    except (OSError, ValueError, json.JSONDecodeError, PermuterError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.function:
        wanted = set(args.function)
        queue = [item for item in queue if item.function in wanted]
    ranking_path = args.ranking or plan.options.ranking
    try:
        ranking = load_ranking(ranking_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if ranking_path is not None and not ranking:
        print(
            f"warning: no differing_words rows read from {ranking_path}; "
            "the queue keeps its own order",
            file=sys.stderr,
        )
    ordered = list(order_queue(queue, ranking))
    unranked = sum(1 for item in ordered if item.function not in ranking)
    summary_path = plan.output_dir / "summary.json"
    carried: list[Any] = []
    if args.resume:
        done = completed_functions(summary_path)
        before = len(ordered)
        ordered = [item for item in ordered if item.function not in done]
        carried = earlier_results(summary_path)
        print(f"--resume: skipping {before - len(ordered)} already-run function(s)")
    if args.limit is not None:
        ordered = ordered[: args.limit]
    if unranked and ranking:
        print(f"note: {unranked} queued function(s) are unranked; they run last")
    if args.list or args.dry_run or not ordered:
        print("\n".join(render_queue(ordered)))
        if args.dry_run:
            print(
                f"dry run: {plan.minutes} min cap, {plan.jobs} concurrent, "
                f"{plan.threads} thread(s) each, load gate {plan.load_threshold}"
            )
        return 0
    print(
        f"running {len(ordered)} function(s), {plan.jobs} concurrent, "
        f"{plan.threads} permuter thread(s) each, {plan.minutes} min cap each"
    )

    def record(results: list[Any]) -> None:
        write_summary(
            plan.output_dir,
            sweep_payload(results, final=False),
            render_table(results),
        )

    def report(message: str) -> None:
        print(message)

    try:
        results = run_sweep(
            plan, ordered, carried=carried, report=report, on_result=record
        )
    except PermuterError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    payload = sweep_payload(results, final=True)
    table = render_table(results)
    summary_json, summary_txt = write_summary(plan.output_dir, payload, table)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("\n".join(table))
        print(f"\nsummary: {summary_json}\n         {summary_txt}")
    return 1 if any(result.error for result in results) else 0


def permute_doctor_command(args: argparse.Namespace) -> int:
    try:
        plan = _plan(args, [])
        if args.queue:
            queue = {item.function: item for item in load_queue(args.queue)}
            item = queue.get(args.function)
            if item is None:
                print(f"error: {args.function} is not in {args.queue}", file=sys.stderr)
                return 2
        else:
            if not args.source:
                print("error: --source is required without --queue", file=sys.stderr)
                return 2
            item = QueueItem(
                function=args.function,
                source=args.source,
                asm=args.asm,
                object=args.object,
                asm_symbol=args.asm_symbol,
            )
        report = doctor(
            plan,
            item,
            seconds=args.seconds,
            check_base=not args.no_base_check,
        )
    except (OSError, ValueError, json.JSONDecodeError, PermuterError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print("\n".join(render_doctor(report)))
    return 0 if report.ok else 1


def _add_shared_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        metavar="PATH",
        help="project config file or directory (default: search upward)",
    )
    parser.add_argument(
        "--permuter-dir",
        metavar="DIR",
        help="decomp-permuter checkout holding import.py and permuter.py",
    )
    parser.add_argument(
        "--output-dir",
        metavar="DIR",
        help="where scratches, logs and the summary are written",
    )
    parser.add_argument("--make", metavar="EXE", help="the project's make binary")
    parser.add_argument(
        "--minutes",
        type=int,
        metavar="N",
        help="per-function wall-clock cap",
    )
    parser.add_argument(
        "--threads",
        type=int,
        metavar="N",
        help="threads per permuter instance (permuter.py -j)",
    )
    parser.add_argument(
        "--load-threshold",
        type=float,
        metavar="X",
        help=(
            "wait until the one-minute load average is below this before each "
            "launch; 0 disables the gate"
        ),
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")


def register_permute_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register `permute-sweep`, `permute-doctor`, and the `permute` group."""

    sweep = commands.add_parser(
        "permute-sweep",
        help="drive decomp-permuter over a queue with a faithful scratch",
        description=_SWEEP_DESCRIPTION,
        epilog=(
            "example: decomp-workbench permute-sweep queue.json "
            "--ranking ranking.json --minutes 20 --resume"
        ),
    )
    _add_sweep_arguments(sweep)

    doctor_parser = commands.add_parser(
        "permute-doctor",
        help="preflight one function's permuter scratch before searching it",
        description=_DOCTOR_DESCRIPTION,
        epilog=(
            "example: decomp-workbench permute-doctor func_80012574 --queue queue.json"
        ),
    )
    _add_doctor_arguments(doctor_parser)

    group = commands.add_parser(
        "permute",
        help="run and preflight bounded decomp-permuter searches",
        description=(
            "Bounded decomp-permuter searches whose scratch reproduces the "
            "project's real per-object recipe. Run "
            "`decomp-workbench permute sweep --help`."
        ),
    )
    operations = group.add_subparsers(dest="permute_command")
    group.set_defaults(handler=_group_listing(group))
    _add_sweep_arguments(
        operations.add_parser(
            "sweep",
            help="drive decomp-permuter over a queue with a faithful scratch",
            description=_SWEEP_DESCRIPTION,
        )
    )
    _add_doctor_arguments(
        operations.add_parser(
            "doctor",
            help="preflight one function's permuter scratch before searching it",
            description=_DOCTOR_DESCRIPTION,
        )
    )


def _group_listing(parser: argparse.ArgumentParser) -> Any:
    from .discovery import subcommand_listing_handler

    return subcommand_listing_handler(parser)


def _add_sweep_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "queue",
        help=(
            "queue file: JSON rows of {function, source, asm, ...}, or one "
            "'function source [asm]' per line"
        ),
    )
    _add_shared_arguments(parser)
    parser.add_argument(
        "--ranking",
        metavar="FILE",
        help=(
            "closeness ranking; queued functions are ordered by ascending "
            "differing_words, and unranked ones run last"
        ),
    )
    parser.add_argument(
        "--function",
        action="append",
        metavar="NAME",
        help="restrict the sweep to this function (repeatable)",
    )
    parser.add_argument(
        "--limit", type=int, metavar="N", help="cap how many functions are searched"
    )
    parser.add_argument(
        "--jobs", type=int, metavar="N", help="how many functions to search at once"
    )
    parser.add_argument(
        "--extend-minutes",
        type=int,
        default=0,
        metavar="N",
        help=(
            "re-seed from the best candidate and search this much longer, but "
            "only when the run hit its cap with its best result in the final "
            "third of the window (default: 0, off)"
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="skip functions already recorded in the output directory's summary",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the ordered queue and the resolved limits, and stop",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the ordered queue and stop",
    )
    parser.add_argument(
        "permuter_args",
        nargs=argparse.REMAINDER,
        help="extra arguments forwarded to permuter.py, after --",
    )
    parser.set_defaults(handler=permute_sweep_command, report_command="permute-sweep")


def _add_doctor_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("function", help="the function to preflight")
    _add_shared_arguments(parser)
    parser.add_argument(
        "--queue", metavar="FILE", help="read this function's row from a queue file"
    )
    parser.add_argument("--source", metavar="FILE", help="the function's C source")
    parser.add_argument("--asm", metavar="FILE", help="the function's target assembly")
    parser.add_argument(
        "--object", metavar="TARGET", help="the Make object target, if not derivable"
    )
    parser.add_argument(
        "--asm-symbol",
        metavar="NAME",
        help="the name the target assembly uses, when it differs from the C name",
    )
    parser.add_argument(
        "--seconds",
        type=int,
        default=120,
        metavar="N",
        help="how long the base-score check may run (default: 120)",
    )
    parser.add_argument(
        "--no-base-check",
        action="store_true",
        help="report flags and objcopy steps without compiling the base",
    )
    parser.set_defaults(
        handler=permute_doctor_command, report_command="permute-doctor", jobs=1
    )


__all__ = [
    "permute_doctor_command",
    "permute_sweep_command",
    "register_permute_commands",
]
