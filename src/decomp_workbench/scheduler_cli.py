"""CLI for stable scheduler traces and hash-pinned external profiles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .as1_reorganize import parse_as1_reorganize_trace, to_dkwb_records
from .scheduler import (
    compare_scheduler_traces,
    instrument_scheduler_source,
    load_scheduler_profile,
    parse_scheduler_trace,
    scheduler_report,
)
from .terminal import warn_to_stderr
from .trace import read_trace_text

#: What the native `as1 -R` reader can and cannot establish, printed with the
#: report so the two gaps travel with the numbers rather than with this file.
AS1_R_PROOF = (
    "Read from IDO 5.3 `as1 -R` (cc -Wa,-R), which is print-only: the traced "
    "object is byte-identical to the untraced one. `tie=` is computed here "
    "from the losing candidates, which the schema has no field for. The key "
    "chain is evaluated without node->addr, which the record does not carry "
    "per candidate; where addr differs between candidates the named key is "
    "the next one down. Key order: start-time (lower wins), besttime, "
    "aftercycles, latency (higher wins), then lineno (lower wins)."
)


def _read_scheduler_trace(
    path: str, *, from_as1_r: bool, proc: int
) -> tuple[list[Any], list[str]]:
    text = read_trace_text(path, warn=warn_to_stderr)
    if not from_as1_r:
        return parse_scheduler_trace(text)
    _selections, events, ignored = parse_as1_reorganize_trace(text, proc=proc)
    if not events:
        raise ValueError(
            f"{path} carries no `Picking node` selection with a candidate "
            "list. Capture both streams -- `cc -Wa,-R -c source.c "
            ">sched.log 2>&1` -- because which one carries the trace is a "
            "property of the assembler build: IDO 5.3's as1 writes it to "
            "stdout, and a `2>sched.log` redirect then captures a one-line "
            "cfe warning and nothing else."
        )
    return events, ignored


def trace_scheduler_command(args: argparse.Namespace) -> int:
    try:
        for name in ("proc", "block", "limit"):
            value = getattr(args, name)
            if value is not None and value < 0:
                raise ValueError(f"--{name} must be non-negative")
        events, ignored = _read_scheduler_trace(
            args.trace, from_as1_r=args.from_as1_r, proc=args.proc or 0
        )
        selected = [
            event
            for event in events
            if (args.proc is None or event.proc == args.proc)
            and (args.block is None or event.block == args.block)
        ]
        if args.against:
            candidate, _ = _read_scheduler_trace(
                args.against, from_as1_r=args.from_as1_r, proc=args.proc or 0
            )
            selected_candidate = [
                event
                for event in candidate
                if (args.proc is None or event.proc == args.proc)
                and (args.block is None or event.block == args.block)
            ]
            report = compare_scheduler_traces(selected, selected_candidate)
        else:
            report = scheduler_report(events, proc=args.proc, block=args.block)
            report["ignored_diagnostic_lines"] = len(ignored)
        if args.from_as1_r:
            report["proof"] = f"{AS1_R_PROOF} {report['proof']}"
        if args.emit:
            Path(args.emit).write_text(to_dkwb_records(events), encoding="utf-8")
            report["emitted"] = args.emit
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        if args.against:
            print(
                f"scheduler diff: {report['difference_count']} decision(s) differ "
                f"across {report['target_events']} / "
                f"{report['candidate_events']} events"
            )
            for item in report["differences"][: args.limit]:
                changed = ",".join(item["changed"])
                print(
                    f"proc={item['proc']} block={item['block']} "
                    f"cycle={item['cycle']} changed={changed}"
                )
        else:
            print(
                f"scheduler: {report['event_count']} event(s), "
                f"{report['ready_set_ties']} ready-set tie(s), "
                f"provenance={report['provenance_complete']}/{report['event_count']}"
            )
            for event in report["events"][: args.limit]:
                print(
                    f"proc={event['proc']} block={event['block']} "
                    f"cycle={event['cycle']} word={event['word']} "
                    f"opcode={event['opcode']} line={event['line']} "
                    f"ready={event['ready']} chosen={event['chosen']} "
                    f"tie={event['tie']}"
                    + (
                        f" slot={event['emitted_slot']} "
                        f"statement={event['source_statement']} "
                        f"reason={event['reason']}"
                        if event.get("emitted_slot") is not None
                        else ""
                    )
                )
        print(f"proof: {report['proof']}")
    return 0 if selected else 1


def instrument_scheduler_command(args: argparse.Namespace) -> int:
    try:
        input_path = Path(args.input).expanduser().resolve()
        output_path = Path(args.output).expanduser().resolve()
        if input_path == output_path:
            raise ValueError("scheduler input and output must be different paths")
        if output_path.exists():
            raise FileExistsError(f"refusing to overwrite output: {output_path}")
        source = input_path.read_text(encoding="utf-8")
        profile = load_scheduler_profile(args.profile)
        instrumented, report = instrument_scheduler_source(source, profile)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("x", encoding="utf-8") as destination:
            destination.write(instrumented)
        report["output"] = str(output_path)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"scheduler profile: {report['injections']} injection(s) -> {output_path}"
        )
        print("required gates: " + ", ".join(report["calibration_required"]))
    return 0


def register_scheduler_commands(
    commands: argparse._SubParsersAction[Any],
) -> None:
    trace = commands.add_parser(
        "trace-scheduler",
        help="read stable named as1 scheduler selection records",
        description=(
            "Read DKWB-SCHED-V1 records with procedure, block, cycle, word, "
            "opcode, source line, ready-set size, chosen node, and tie-break. "
            "For IDO 5.3, reach for --from-as1-r first: the assembler ships "
            "its own selection trace behind `cc -Wa,-R`, no patched compiler "
            "involved, and the traced object is byte-identical to the "
            "untraced one."
        ),
        epilog=(
            "example: cc -Wa,-R -c source.c >sched.log 2>&1 && "
            "decomp-workbench trace-scheduler sched.log --from-as1-r --block 429"
            "\n\nCapture both streams: IDO 5.3's as1 prints the -R trace on "
            "stdout, other assembler builds may use stderr, and `>` alone "
            "silently produces an empty log on the ones that do."
        ),
    )
    trace.add_argument("trace")
    trace.add_argument("--against", help="second trace for cycle-aligned diff")
    trace.add_argument(
        "--from-as1-r",
        action="store_true",
        help=(
            "the input is a native IDO 5.3 `cc -Wa,-R` trace rather than "
            "DKWB-SCHED-V1; the deciding key is computed from the losing "
            "candidates, which the schema cannot carry"
        ),
    )
    trace.add_argument(
        "--emit",
        metavar="PATH",
        help="also write the selections as DKWB-SCHED-V1 records",
    )
    trace.add_argument("--proc", type=int)
    trace.add_argument("--block", type=int)
    trace.add_argument("--limit", type=int, default=50)
    trace.add_argument("--json", action="store_true", help="emit JSON")
    trace.set_defaults(handler=trace_scheduler_command)

    instrument = commands.add_parser(
        "instrument-scheduler",
        help="apply a hash-pinned external scheduler instrumentation profile",
        description=(
            "Apply exact source anchors from a user-supplied profile. The "
            "output is not supported evidence until every reported fidelity "
            "gate passes. Era note: for IDO 5.3 this is usually unnecessary. "
            "`as1` already carries a richer selection trace behind "
            "`cc -Wa,-R`, with no patch and therefore no profile to pin -- "
            "read it with `trace-scheduler --from-as1-r`. Patch only when the "
            "era's assembler has no built-in trace, or when you need a field "
            "the built-in one does not print."
        ),
    )
    instrument.add_argument("input")
    instrument.add_argument("output")
    instrument.add_argument("--profile", required=True)
    instrument.add_argument("--json", action="store_true", help="emit JSON")
    instrument.set_defaults(handler=instrument_scheduler_command)
