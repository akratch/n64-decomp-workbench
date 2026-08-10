"""CLI for semantic allocator and stack-home reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .allocator_analysis import (
    compare_semantic_webs,
    origin_probe_report,
    stack_home_report,
    web_report,
)
from .copytrace import copy_decision_report
from .globalcolor import parse_globalcolor_trace


def copy_decisions_command(args: argparse.Namespace) -> int:
    try:
        baseline = Path(args.trace).read_text(encoding="utf-8")
        against = (
            Path(args.against).read_text(encoding="utf-8") if args.against else None
        )
        report = copy_decision_report(
            baseline,
            against=against,
            tag=args.stage,
            proc=args.proc,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.against:
        before = report["summary"]
        after = report["candidate_summary"]
        print(
            "copy decisions: "
            f"{before['decision_count']} -> {after['decision_count']}; "
            f"coalesced={before['coalesced']}->{after['coalesced']}; "
            f"temporary copies={before['temporary_copies']}->"
            f"{after['temporary_copies']}"
        )
        print(f"decision delta: {report['difference_count']} aligned difference(s)")
        for item in report["differences"][: args.limit]:
            before_item = item["baseline"]
            after_item = item["candidate"]
            transition = (
                "presence changed"
                if before_item is None or after_item is None
                else f"{before_item['decision']}->{after_item['decision']}"
            )
            print(
                f"{item['alignment_key']} {transition} "
                f"changed={','.join(item['changed'])}"
            )
        print(f"warning: {report['warnings'][0]}")
        print(f"proof: {report['proof']}")
        if not before["decision_count"] and not after["decision_count"]:
            baseline_stages = report["timeline"]["observed_stages"]
            candidate_stages = report["candidate_timeline"]["observed_stages"]
            print(
                "next: no decisions matched the selected stage; observed "
                f"baseline stages={baseline_stages or 'none'}, "
                f"candidate stages={candidate_stages or 'none'}"
            )
    else:
        summary = report["summary"]
        print(
            f"copy decisions: {summary['decision_count']} at {args.stage}; "
            f"coalesced={summary['coalesced']}; "
            f"temporary copies={summary['temporary_copies']}"
        )
        for item in report["decisions"][: args.limit]:
            print(
                f"{item['alignment_key']} {item['decision']} "
                f"rhs_formed={item['rhs_formed']} "
                f"colors={item['lhs_color']}/{item['rhs_color']}"
            )
        timeline = report["timeline"]
        for item in timeline["transitions"][: args.limit]:
            owner = item["owner_pass"] or "unresolved"
            print(
                f"transition: {item['alignment_key']} "
                f"{item['before_decision']}->{item['after_decision']} "
                f"across {item['before_stage']}->{item['after_stage']}; "
                f"owner={owner}"
            )
        print(f"warning: {report['warnings'][0]}")
        if not summary["decision_count"]:
            print(
                "next: no decisions matched the selected stage; observed "
                f"stages={timeline['observed_stages'] or 'none'}"
            )
    count = report["summary"]["decision_count"]
    if args.against:
        count += report["candidate_summary"]["decision_count"]
    return 0 if count else 1


def allocator_webs_command(args: argparse.Namespace) -> int:
    try:
        target = parse_globalcolor_trace(Path(args.trace).read_text(encoding="utf-8"))
        report = (
            compare_semantic_webs(
                target,
                parse_globalcolor_trace(Path(args.against).read_text(encoding="utf-8")),
                proc=args.proc,
            )
            if args.against
            else web_report(target, proc=args.proc)
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.against:
        summary = report["decision_summary"]
        outcome = report["outcome_schedule"]
        print(
            f"allocator semantic diff: {report['difference_count']} difference(s), "
            f"{len(report['ambiguous_fingerprints'])} ambiguous fingerprint(s)"
        )
        coverage = report["alignment_coverage"]
        rendered_coverage = "n/a" if coverage is None else f"{coverage:.1%}"
        print(
            "alignment coverage: "
            f"common={report['common_fingerprints']}/"
            f"{report['alignment_denominator']} ({rendered_coverage}) "
            f"status={report['alignment_status']}"
        )
        # A bare `common=0` sent one campaign looking for a bug in its builds.
        # Whichever way alignment failed, name the fields and say whether the
        # fix is an instrument setting or is not available at all.
        if not report["common_fingerprints"]:
            diagnosis = report["alignment_diagnosis"]
            for label, key in (
                ("present but sharing no value", "no_shared_value"),
                ("absent from one side", "absent_from_one_side"),
            ):
                if diagnosis[key]:
                    print(f"  identity {label}: {', '.join(diagnosis[key])}")
            for record in diagnosis["missing_records"]:
                print(f"  no record on either side supplies: {record}")
            print(f"  diagnosis: {diagnosis['guidance']}")
        print(
            "decision delta: "
            f"actual assignments={summary['actual_assignment_changes']}, "
            f"natural choices={summary['natural_choice_changes']}, "
            f"forbidden masks={summary['forbidden_mask_changes']}, "
            f"force overrides={len(summary['candidate_force_overrides'])}"
        )
        print(
            "decision outcome: "
            f"status={outcome['status']} "
            f"count={outcome['target_count']}->{outcome['candidate_count']} "
            f"common-prefix={outcome['common_prefix']}"
        )
        phases = sorted(
            set(outcome["target_phase_counts"]) | set(outcome["candidate_phase_counts"])
        )
        if phases:
            phase_summary = ",".join(
                f"{phase}:{outcome['target_phase_counts'].get(phase, 0)}"
                f"->{outcome['candidate_phase_counts'].get(phase, 0)}"
                for phase in phases
            )
            print(f"decision phases: {phase_summary}")
        if outcome["identical"] and report["alignment_status"] != "aligned":
            print(
                "note: source-distinct web topology reached the same ordered "
                "register endpoints; this is carrier substitution evidence, "
                "not semantic-web identity"
            )
        for item in report["differences"][: args.limit]:
            before = item["target"]
            after = item["candidate"]
            if before is None or after is None:
                transition = "presence changed"
            else:
                transition = (
                    f"w{before['numeric_web']} -> w{after['numeric_web']} "
                    f"natural={before['natural_register']}->"
                    f"{after['natural_register']} "
                    f"assigned={before['assigned_register']}->"
                    f"{after['assigned_register']}"
                )
            print(
                f"{item['fingerprint']} {transition} "
                f"changed={','.join(item['changed'])}"
            )
            for side in ("target", "candidate"):
                for cause in item[f"{side}_only_forbidden_causes"]:
                    owner = before if side == "target" else after
                    print(
                        f"  {side}-only barrier: {cause['register']} by "
                        f"proc{owner['proc']}:{owner['phase']}:"
                        f"w{cause['trace_local_neighbor']} "
                        f"({cause['neighbor_fingerprint']})"
                    )
        for override in summary["candidate_force_overrides"]:
            print(
                "force override: "
                f"{override['force_key']} "
                f"{override['natural_register']}->{override['assigned_register']}"
            )
        if report["next_gate"]:
            print(f"next gate: {report['next_gate']}")
        print(f"outcome proof: {outcome['proof']}")
        print(f"proof: {report['proof']}")
    else:
        print(
            f"allocator webs: {report['web_count']} semantic fingerprint(s), "
            f"{report['low_confidence']} low-confidence"
        )
        print(
            "source attribution: "
            f"{report['source_attributed_webs']} source-attributed, "
            f"{report['run_local_unattributed_webs']} run-local/unattributed"
        )
        print(
            "formation lineage: "
            f"{report['formation_captured_webs']}/{report['web_count']} web(s) joined"
        )
        if report["next_gate"]:
            print(f"next gate: {report['next_gate']}")
        for item in report["webs"][: args.limit]:
            formation = item["formation"]
            economics = item["economics"]
            formation_text = (
                f"event={formation['range_event']} "
                f"rank={formation['formation_rank']} "
                f"first-bb={formation['first_member_bb']}"
                if formation["status"] == "captured"
                else "not-captured"
            )
            print(
                f"{item['fingerprint']} confidence={item['confidence']} "
                f"phase={item['phase']} local=w{item['numeric_web']} "
                f"color={item['assigned_color']} register={item['assigned_register']} "
                f"decision-trace={item['decision_trace_ordinal']} "
                # Printed as three named fields, not as `save*nocs=total`.
                # `nocs` is the pass's compressed occurrence divisor, not an
                # occurrence count, so the equation shape asserted arithmetic
                # the records do not establish and invited ranking by a
                # product that is not "saving times uses".
                f"economics=save:{economics.get('save', '-')} "
                f"nocs:{economics.get('nocs', '-')} "
                f"totalsave:{economics.get('totalsave', '-')} "
                f"formation={formation_text}"
            )
        print(f"formation guidance: {report['formation_order_guidance']}")
        print(f"proof: {report['proof']}")
    count = report.get("web_count", 0)
    if args.against:
        count = report["target_webs"] + report["candidate_webs"]
    return 0 if count else 1


def stack_homes_command(args: argparse.Namespace) -> int:
    try:
        trace = parse_globalcolor_trace(Path(args.trace).read_text(encoding="utf-8"))
        report = stack_home_report(trace, proc=args.proc, offset=args.offset)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"stack homes: {report['selected_count']} shown / "
            f"{report['home_count']} classified"
        )
        for home in report["homes"][: args.limit]:
            print(
                f"{home['fingerprint']} kind={home['kind']} "
                f"virtual={home['virtual_offset']} final={home['final_offset']} "
                f"source={home['source']}"
            )
        if report["next_gate"]:
            print(f"next gate: {report['next_gate']}")
        print(f"proof: {report['proof']}")
    return 0 if report["selected_count"] else 1


def origin_probe_command(args: argparse.Namespace) -> int:
    try:
        baseline = parse_globalcolor_trace(
            Path(args.baseline).read_text(encoding="utf-8")
        )
        variant = parse_globalcolor_trace(
            Path(args.variant).read_text(encoding="utf-8")
        )
        report = origin_probe_report(
            baseline,
            variant,
            role=args.role,
            proc=args.proc,
            source_semantic=args.source_semantic,
            synthetic=args.synthetic,
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        counts = report["counts"]
        print(
            f"origin probe: role={report['role']} "
            f"classification={report['classification']} "
            f"scope={report['claim_scope']}"
        )
        print(
            "web delta: "
            f"{counts['baseline_webs']} -> {counts['variant_webs']}; "
            f"formation -{counts['formation_removed']} "
            f"+{counts['formation_added']}; "
            f"color cascades={counts['common_web_color_changes']}; "
            f"formation collisions={counts['formation_collisions']}"
        )
        print(
            "coarse topology: "
            f"-{counts['topology_removed']} +{counts['topology_added']}; "
            f"collisions={counts['topology_collisions']}"
        )
        print(
            "allocation economics: "
            f"-{counts['economics_removed']} +{counts['economics_added']}; "
            f"allocation changes={counts['allocation_economics_transitions']}; "
            f"trace-local renumbers={counts['economics_renumber_only']}; "
            f"collisions={counts['economics_collisions']}"
        )
        for item in report["allocation_economics_transitions"]:
            before = item["baseline"]
            after = item["variant"]
            print(
                "economics transition: "
                f"w{before['trace_local_web']}({before['natural_register']}) -> "
                f"w{after['trace_local_web']}({after['natural_register']}) "
                f"changed={','.join(item['changed'])}"
            )
        if report["cascade_warning"]:
            print(f"warning: {report['cascade_warning']}")
        print(f"proof: {report['proof']}")
        print(f"next gate: {report['next_gate']}")
    return 0 if report["evidence_status"] == "ready" else 1


def register_allocator_commands(
    commands: argparse._SubParsersAction[Any],
) -> None:
    copies = commands.add_parser(
        "trace-copy-decisions",
        help="show IDO coalesce-versus-temporary-copy decisions",
        description=(
            "Parse COPYDEC snapshots without treating trace-local bit numbers "
            "or hash buckets as source identity. With --against, align final "
            "decisions by stack home and assignment ordinal."
        ),
    )
    copies.add_argument("trace")
    copies.add_argument("--against", help="second COPYDEC trace to compare")
    copies.add_argument("--stage", default="pre-reemit")
    copies.add_argument("--proc", type=int)
    copies.add_argument("--limit", type=int, default=50)
    copies.add_argument("--json", action="store_true", help="emit JSON")
    copies.set_defaults(handler=copy_decisions_command)

    webs = commands.add_parser(
        "trace-webs",
        help="fingerprint allocator webs by semantic provenance",
        description=(
            "Align allocator decisions by dtype, virtual home, formation chain, "
            "and block context; numeric web IDs remain trace-local."
        ),
    )
    webs.add_argument("trace")
    webs.add_argument("--against", help="second trace for semantic web diff")
    webs.add_argument("--proc", type=int)
    webs.add_argument("--limit", type=int, default=50)
    webs.add_argument("--json", action="store_true", help="emit JSON")
    webs.set_defaults(handler=allocator_webs_command)

    origin = commands.add_parser(
        "trace-origin-probe",
        help="classify one controlled source edit's allocator-web delta",
        description=(
            "Compare exact semantic identity and coarse topology for one "
            "controlled perturbation. This calibrates a role; it does not "
            "claim source attribution."
        ),
    )
    origin.add_argument("baseline")
    origin.add_argument("variant")
    origin.add_argument("--role", required=True, help="human experiment role label")
    origin.add_argument("--proc", type=int)
    origin.add_argument(
        "--source-semantic",
        help="expected source role label (not producer attribution)",
    )
    origin.add_argument(
        "--synthetic",
        action="store_true",
        help="mark the result calibration-only",
    )
    origin.add_argument("--json", action="store_true", help="emit JSON")
    origin.set_defaults(handler=origin_probe_command)

    homes = commands.add_parser(
        "trace-stack-homes",
        help="classify and query trace-derived stack-home ownership",
    )
    homes.add_argument("trace")
    homes.add_argument("--proc", type=int)
    homes.add_argument(
        "--offset",
        type=lambda value: int(value, 0),
        help="show owners of one virtual or explicitly recorded final offset",
    )
    homes.add_argument("--limit", type=int, default=50)
    homes.add_argument("--json", action="store_true", help="emit JSON")
    homes.set_defaults(handler=stack_homes_command)
