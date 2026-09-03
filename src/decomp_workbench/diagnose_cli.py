"""Combined exact comparison and aligned mechanism diagnosis commands."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .as1_reorganize import parse_as1_reorganize_trace
from .cascade import CascadeError, CdxLog
from .census import (
    Predicate,
    census_status,
    evaluate_census,
    parse_census,
)
from .cli_options import (
    add_candidate_listing_argument,
    add_census_argument,
    add_explain_keys_argument,
    add_symbol_argument,
)
from .comparison_render import (
    alignment_caution_lines,
    comparison_acceptance,
    comparison_explanation_lines,
    comparison_line,
    diff_site_lines,
    relocation_symbol_caution_lines,
    warning_lines,
)
from .diagnosis import Diagnosis, diagnose_dumps, diagnose_objects
from .emit_provenance import parse_emit_trace
from .force_spec import write_force_specification
from .frame_ladder import frame_ladder
from .globalcolor import parse_globalcolor_trace, pass_evidence
from .html_report import render_diagnosis_html
from .levers import format_lever, lever_for
from .loc_boundaries import (
    MISSING_LISTING_STEPS,
    LocBoundaryReport,
    annotate_schedule_sites,
    render_loc_boundaries,
    report_guidance,
    schedule_class_count,
)
from .model import display_path
from .schema import COMPARISON_CENSUS_KEYS
from .staleness_cli import (
    add_freshness_arguments,
    freshness_display,
    freshness_payload,
    guard_freshness,
)
from .terminal import Painter, emit_lines, resolve_color, warn_to_stderr
from .trace import parse_trace, read_trace_text
from .view import PassEvidence
from .view_cli import (
    add_view_output_arguments,
    add_view_render_arguments,
    render_view,
)

#: What the footer says when a trace was read and settled nothing.
#:
#: Silence here would be the worst of the three outcomes: the reader asked a
#: compiler trace the ownership question, and an `ownership_basis=heuristic`
#: with no explanation looks exactly like a run that was never given one.
TRACE_SETTLED_NOTHING = (
    "trace: {name} holds no declined force and no regsleft=0 contest for this "
    "scope, so ownership stays heuristic. Widen or correct --trace-proc/"
    "--trace-web before reading that as agreement."
)

#: What it says when the trace did settle it, so the basis has a provenance.
TRACE_SETTLED = "trace: ownership measured from {name}{scope}."


def _trace_scope(args: argparse.Namespace) -> str:
    parts = [
        f"{label}={value}"
        for label, value in (
            ("proc", getattr(args, "trace_proc", None)),
            ("web", getattr(args, "trace_web", None)),
        )
        if value is not None
    ]
    return f" ({', '.join(parts)})" if parts else " (whole compilation)"


def trace_evidence(args: argparse.Namespace) -> PassEvidence | None:
    """Read `--trace`, scoped to the procedure and web the reader named.

    Unscoped by accident is the trap: a trace covers a whole compilation and
    a residual is one function's, so *some* declined force in the file is
    nearly certain and reading it as this residual's would manufacture a
    measurement. The scope is the reader's to state, and the footer prints
    which scope was applied either way.
    """

    path = getattr(args, "trace", None)
    if not path:
        return None
    text = read_trace_text(Path(path).expanduser(), warn=warn_to_stderr)
    return pass_evidence(
        parse_globalcolor_trace(text),
        proc=getattr(args, "trace_proc", None),
        web=getattr(args, "trace_web", None),
    )


def _trace_lines(
    args: argparse.Namespace, evidence: PassEvidence | None
) -> tuple[str, ...]:
    """The one line a `--trace` run owes its reader about that trace."""

    if evidence is None:
        return ()
    name = display_path(args.trace)
    if evidence.decisive:
        return (TRACE_SETTLED.format(name=name, scope=_trace_scope(args)),)
    return (TRACE_SETTLED_NOTHING.format(name=name),)


def _with_trace_note(
    diagnosis: Diagnosis,
    args: argparse.Namespace,
    evidence: PassEvidence | None,
) -> Diagnosis:
    """Record in the footer which trace the ownership basis came from."""

    notes = _trace_lines(args, evidence)
    if not notes:
        return diagnosis
    view = dataclasses.replace(diagnosis.view, guidance=diagnosis.view.guidance + notes)
    return dataclasses.replace(diagnosis, view=view)


def _lever(diagnosis: Diagnosis, args: argparse.Namespace) -> Diagnosis:
    """Attach the source-edit class, reading whichever traces were supplied.

    Nothing here is optional-with-a-default: each input is a different
    compiler observation, and a lever named from an input the reader did not
    supply would be the guess the module exists to refuse. An exact comparison
    gets no block at all, because there is no residual to explain.
    """

    if diagnosis.comparison.exact:
        return diagnosis
    ladder = None
    if getattr(args, "ladder", None):
        log = CdxLog(
            read_trace_text(Path(args.ladder).expanduser(), warn=warn_to_stderr),
            name=display_path(args.ladder),
        )
        ladder = frame_ladder(log, proc=getattr(args, "lever_proc", None))
    ring_events = None
    if getattr(args, "ring_trace", None):
        ring_events = parse_trace(
            read_trace_text(Path(args.ring_trace).expanduser(), warn=warn_to_stderr)
        )
    emit_events = None
    if getattr(args, "emit_trace", None):
        emit_events, _ignored = parse_emit_trace(
            read_trace_text(Path(args.emit_trace).expanduser(), warn=warn_to_stderr)
        )
    source = None
    if getattr(args, "source", None):
        source = (
            Path(args.source)
            .expanduser()
            .read_text(encoding="utf-8", errors="replace")
            .splitlines()
        )
    selections = None
    if getattr(args, "as1_trace", None):
        selections, _events, _ignored = parse_as1_reorganize_trace(
            read_trace_text(Path(args.as1_trace).expanduser(), warn=warn_to_stderr)
        )
    lever = lever_for(
        diagnosis.view,
        ladder=ladder,
        ring_events=ring_events,
        emit_events=emit_events,
        as1_selections=selections,
        source=source,
        proc=getattr(args, "lever_proc", None),
    )
    return dataclasses.replace(diagnosis, lever=lever)


def _statement_lines(
    diagnosis: Diagnosis, args: argparse.Namespace
) -> tuple[Diagnosis, LocBoundaryReport | None]:
    """Attach statement-line evidence, or say the option exists.

    Two branches, and the second is the one that matters: a `schedule` verdict
    whose only documented next step is a `-g0` rebuild is a dead end for every
    project that already builds `-g0`, and the reader cannot ask for evidence
    they have never been told the tool can read.
    """

    view = diagnosis.view
    listing = getattr(args, "candidate_listing", None)
    if not listing:
        if schedule_class_count(view):
            view = dataclasses.replace(
                view, guidance=view.guidance + MISSING_LISTING_STEPS
            )
            return dataclasses.replace(diagnosis, view=view), None
        return diagnosis, None
    text = Path(listing).expanduser().read_text(encoding="utf-8")
    report = annotate_schedule_sites(
        view,
        text,
        listing_name=display_path(listing),
        symbol=args.symbol,
    )
    view = dataclasses.replace(view, guidance=view.guidance + report_guidance(report))
    return dataclasses.replace(diagnosis, view=view), report


def _emit(
    diagnosis: Diagnosis,
    args: argparse.Namespace,
    predicates: Sequence[Predicate],
) -> int:
    comparison = diagnosis.comparison
    if args.json and args.html:
        print("error: --json and --html are mutually exclusive", file=sys.stderr)
        return 2
    try:
        diagnosis, listing_report = _statement_lines(diagnosis, args)
        diagnosis = _lever(diagnosis, args)
    except (CascadeError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    try:
        census = evaluate_census(predicates, comparison.as_dict())
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    try:
        force_output = (
            Path(args.emit_force_spec).expanduser().resolve()
            if args.emit_force_spec
            else None
        )
        html_output = Path(args.html).expanduser().resolve() if args.html else None
        for output, label in (
            (force_output, "force specification"),
            (html_output, "HTML report"),
        ):
            if output is not None and output.exists():
                raise FileExistsError(f"refusing to overwrite {label}: {output}")
        if force_output is not None:
            write_force_specification(diagnosis.view, force_output)
        if html_output is not None:
            html_output.parent.mkdir(parents=True, exist_ok=True)
            document = render_diagnosis_html(
                diagnosis.view,
                comparison=comparison,
                report_regs=args.report_regs,
            )
            with html_output.open("x", encoding="utf-8") as destination:
                destination.write(document)
            print(
                f"note: {html_output} contains the target's disassembly. "
                "It is ROM-derived -- keep it out of version control.",
                file=sys.stderr,
            )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    accepted, _ = comparison_acceptance(comparison, cross_rom=args.cross_rom)
    freshness, freshness_warnings = freshness_display(
        args, args.target, args.candidate, labels=("target", "candidate")
    )
    if args.json:
        payload = diagnosis.as_dict(
            report_regs=args.report_regs,
            cross_rom=args.cross_rom,
        )
        if census:
            nested = payload["comparison"]
            if isinstance(nested, dict):
                nested["census"] = [item.as_dict() for item in census]
        payload.update(freshness_payload(freshness))
        if listing_report is not None:
            payload["loc_boundaries"] = listing_report.as_dict()
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        painter = Painter(resolve_color(args.color))
        lines = [
            *freshness_warnings,
            # Provenance ahead of the verdict: a reader who meets it after
            # the numbers has already believed the numbers.
            *(f"compared: {line}" for line in freshness.provenance_lines()),
            *warning_lines(comparison.warnings),
            painter.bold("COMPARISON"),
            *alignment_caution_lines(comparison),
            *relocation_symbol_caution_lines(comparison),
            comparison_line(comparison, painter),
        ]
        lines.extend(
            comparison_explanation_lines(
                comparison,
                cross_rom=args.cross_rom,
                guidance=False,
            )
        )
        if args.show_diff or args.show_all:
            lines.extend(diff_site_lines(comparison))
        lines.extend(("", painter.bold("MECHANISM")))
        lines.extend(
            render_view(
                diagnosis.view,
                context=args.context,
                max_hunks=0 if args.show_all else args.max_hunks,
                lane_window=(
                    max(
                        diagnosis.view.target_instructions,
                        diagnosis.view.candidate_instructions,
                    )
                    if args.show_all
                    else args.lane_window
                ),
                report_regs=args.report_regs,
                painter=painter,
                show_warnings=False,
                width=args.width,
                terse=args.terse,
                extra_sections=(
                    *(
                        render_loc_boundaries(listing_report, painter)
                        if listing_report is not None
                        else ()
                    ),
                    *(
                        ("", *format_lever(diagnosis.lever))
                        if diagnosis.lever is not None
                        else ()
                    ),
                ),
            )
        )
        lines.extend(item.line for item in census)
        if args.html:
            lines.append(f"HTML report: {Path(args.html).expanduser().resolve()}")
        if args.emit_force_spec:
            lines.append(
                "diagnostic force specification: "
                f"{Path(args.emit_force_spec).expanduser().resolve()}"
            )
        emit_lines(
            lines,
            width=args.width,
            pager=args.pager,
        )

    return census_status(
        census,
        otherwise=1 if args.fail_on_mismatch and not accepted else 0,
    )


def diagnose_command(args: argparse.Namespace) -> int:
    """Diagnose two object files after disassembling each exactly once."""

    try:
        guard_freshness(
            args, args.target, args.candidate, labels=("target", "candidate")
        )
        predicates = parse_census(args.census, allowed=COMPARISON_CENSUS_KEYS)
        evidence = trace_evidence(args)
        diagnosis = _with_trace_note(
            diagnose_objects(
                args.target,
                args.candidate,
                objdump=args.objdump,
                symbol=args.symbol,
                section=args.section,
                register_profile=args.register_profile,
                evidence=evidence,
            ),
            args,
            evidence,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return _emit(diagnosis, args, predicates)


def diagnose_dumps_command(args: argparse.Namespace) -> int:
    """Diagnose two retained GNU objdump text files."""

    try:
        guard_freshness(
            args, args.target, args.candidate, labels=("target", "candidate")
        )
        predicates = parse_census(args.census, allowed=COMPARISON_CENSUS_KEYS)
        evidence = trace_evidence(args)
        diagnosis = _with_trace_note(
            diagnose_dumps(
                args.target,
                args.candidate,
                symbol=args.symbol,
                register_profile=args.register_profile,
                evidence=evidence,
            ),
            args,
            evidence,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return _emit(diagnosis, args, predicates)


def _add_shared_arguments(
    parser: argparse.ArgumentParser,
    *,
    object_inputs: bool,
) -> None:
    add_symbol_argument(parser)
    add_explain_keys_argument(parser)
    if object_inputs:
        parser.add_argument(
            "--section",
            default=".text",
            help="object section (default: .text)",
        )
        parser.add_argument(
            "--objdump",
            help="GNU-compatible MIPS objdump; auto-detected when omitted",
        )
    add_candidate_listing_argument(parser)
    parser.add_argument(
        "--trace",
        metavar="PATH",
        help=(
            "an instrumented-uopt globalcolor trace (CSAVE/CUP/CDX). A "
            "declined force or a regsleft=0 contest in it settles ownership "
            "as a measurement, so the verdict reads ownership_basis=trace "
            "instead of heuristic"
        ),
    )
    parser.add_argument(
        "--trace-proc",
        type=int,
        metavar="N",
        help=(
            "scope --trace to one procedure; a trace covers a whole "
            "compilation and a residual is one function's"
        ),
    )
    parser.add_argument(
        "--trace-web",
        type=int,
        metavar="N",
        help="scope --trace to one web within the procedure",
    )
    parser.add_argument(
        "--ladder",
        metavar="PATH",
        help=(
            "a CDX log carrying CDX_SYMTAB=1 itable records; supplies the "
            "declared-local count the stack-home lever is measured against"
        ),
    )
    parser.add_argument(
        "--ring-trace",
        metavar="PATH",
        help=(
            "a DKWB_UGEN_TRACE free-list log; supplies ring pops per source "
            "line, which is what names the construct that bought or sold one"
        ),
    )
    parser.add_argument(
        "--emit-trace",
        metavar="PATH",
        help=(
            "a DKWB-EMIT-V1 ugen emit-provenance log; supplies the line-order "
            "conflicts the loop-header join removes"
        ),
    )
    parser.add_argument(
        "--as1-trace",
        metavar="PATH",
        help=(
            "an as1 `cc -Wa,-R` scheduler trace. The deciding key of a "
            "selection settles the line question outright: decided on lineno "
            "the line lever reaches it, decided above lineno nothing in the "
            "source does"
        ),
    )
    parser.add_argument(
        "--source",
        metavar="PATH",
        help=(
            "the candidate's C. Read only to check what the line a ring "
            "trace charged actually contains: each pop-cost rule was "
            "measured on one construct, and without the line no temp-ring "
            "edit family is named"
        ),
    )
    parser.add_argument(
        "--lever-proc",
        type=int,
        metavar="N",
        help=(
            "scope --ladder, --ring-trace and --emit-trace to one procedure "
            "ordinal, for the same reason --trace-proc exists"
        ),
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    add_view_render_arguments(
        parser,
        default_max_hunks=1,
        show_all_help=(
            "render every hunk, the full lanes, and the literal differing "
            "sites (overrides --max-hunks/--lane-window and implies "
            "--show-diff)"
        ),
    )
    add_view_output_arguments(parser)
    parser.add_argument(
        "--show-diff",
        action="store_true",
        help="print every positional differing site as well as the aligned hunk",
    )
    parser.add_argument(
        "--cross-rom",
        action="store_true",
        help=(
            "accept structural cross-ROM evidence; never call it an "
            "object-exact source match"
        ),
    )
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="return exit 1 unless exact, or structurally exact with --cross-rom",
    )
    add_freshness_arguments(parser)
    add_census_argument(parser)


def register_diagnose_commands(commands: argparse._SubParsersAction[Any]) -> None:
    """Register combined diagnosis commands."""

    parser = commands.add_parser(
        "diagnose",
        help="compare and explain two MIPS objects in one screen",
        description=(
            "Disassemble each object once, then render exact comparison truth "
            "and the decisive aligned mechanism evidence."
        ),
    )
    parser.add_argument("target", help="reference object")
    parser.add_argument("candidate", help="candidate object")
    _add_shared_arguments(parser, object_inputs=True)
    parser.set_defaults(handler=diagnose_command)

    dumps = commands.add_parser(
        "diagnose-dumps",
        help="compare and explain retained GNU objdump text",
        description=(
            "Build the combined exact and aligned diagnosis from redistributable "
            "objdump text."
        ),
    )
    dumps.add_argument("target", help="reference objdump text")
    dumps.add_argument("candidate", help="candidate objdump text")
    _add_shared_arguments(dumps, object_inputs=False)
    dumps.set_defaults(handler=diagnose_dumps_command)
