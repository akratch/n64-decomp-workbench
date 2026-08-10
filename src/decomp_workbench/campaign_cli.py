"""Persistent campaign cockpit commands."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

from .campaign import run_campaign
from .campaign_state import (
    build_status,
    export_status,
    find_manifest,
    finish_manifest,
    remaining_sources,
    update_hypothesis,
    validate_resume,
)
from .campaign_survey import CampaignSurveyError, survey_campaign, survey_lines
from .experiments import EXPERIMENT_SCHEMA, RegionConstraint
from .scratch_bundle import bundle_scratch


def _compact_parameter_evidence(family: dict[str, Any]) -> tuple[str, str]:
    """Keep the cockpit readable when a real grid has hundreds of cells."""

    tested = family.get("tested_parameters", [])
    tested_count = int(family.get("tested_parameter_sets", len(tested)))
    if tested_count <= 6:
        tested_text = str(tested)
    else:
        sample = tested[:3]
        tested_text = (
            f"{tested_count} assignment(s); sample={sample} "
            f"(+{tested_count - len(sample)} more; use --json for all "
            "retained evidence)"
        )

    declared = family.get("declared_parameter_space", {})
    declared_text = str(declared)
    choice_count = (
        sum(len(choices) for choices in declared.values() if isinstance(choices, list))
        if isinstance(declared, dict)
        else 0
    )
    if (len(declared_text) > 240 or choice_count > 12) and isinstance(declared, dict):
        parts = []
        for name, choices in declared.items():
            if isinstance(choices, list):
                parts.append(f"{name}={len(choices)} choice(s)")
            else:
                parts.append(f"{name}={choices}")
        declared_text = ", ".join(parts)
    return tested_text, declared_text


def _print_status(report: dict[str, Any]) -> None:
    print(
        f"campaign: {report['status']} — {report['recorded_candidates']}/"
        f"{report['prepared_candidates']} candidate(s), "
        f"{len(report['object_basins'])} object basin(s)"
    )
    best = report.get("best")
    if isinstance(best, dict):
        comparison = best.get("comparison")
        if isinstance(comparison, dict):
            print(
                f"best: {best.get('source')} — {comparison.get('verdict')} "
                f"aligned={comparison.get('aligned_total')} "
                f"words={comparison.get('words', comparison.get('word_mismatches'))}"
            )
    best_temp = report.get("best_temp_prefix")
    if isinstance(best_temp, dict) and best_temp.get("source") != (
        best.get("source") if isinstance(best, dict) else None
    ):
        comparison = best_temp.get("comparison")
        if isinstance(comparison, dict):
            temp = comparison.get("temp_prefix_exact")
            pool = (
                "exact"
                if comparison.get("pool_exact")
                else comparison.get("pool_prefix_exact")
            )
            print(
                f"best temp prefix: {best_temp.get('source')} — "
                f"pool={pool} "
                f"temp={'exact' if temp is None else temp} "
                f"words={comparison.get('words', comparison.get('word_mismatches'))}"
            )
    print(
        f"outcomes: {report['successful_candidates']} successful, "
        f"{report['failed_candidates']} failed, "
        f"{report['remaining_candidates']} remaining"
    )
    if report["trajectory"]:
        values = [
            int(point["best_aligned_total"])
            for point in report["trajectory"]
            if point["best_aligned_total"] is not None
        ]
        if values:
            levels = ".:-=+*#%@"
            high = max(values)
            low = min(values)
            scale = max(1, high - low)
            sparkline = "".join(
                levels[
                    min(
                        len(levels) - 1,
                        round((high - value) * (len(levels) - 1) / scale),
                    )
                ]
                for value in values[-60:]
            )
            print(f"trajectory: {values[0]} {sparkline} {values[-1]} (best aligned)")
    if report["object_basins"]:
        variants = sum(int(item["variant_count"]) for item in report["object_basins"])
        print(
            f"idea collapse: {variants} successful source variant(s) → "
            f"{len(report['object_basins'])} distinct object basin(s)"
        )
    for warning in report["warnings"]:
        print(f"warning: {warning}")
    if report.get("families"):
        print("families:")
        for family in report["families"]:
            state = (
                "COLLAPSED"
                if family["tested_candidates"] > 1 and family["object_basins"] == 1
                else "MOVING"
            )
            best = family["best"].get("comparison") or {}
            print(
                f"  {family['family']}: {family['tested_candidates']} tried, "
                f"{family['object_basins']} basin(s), "
                f"best={best.get('aligned_total')} [{state}]"
            )
            tested, declared = _compact_parameter_evidence(family)
            print(f"    tested: {tested}")
            print(f"    declared: {declared}")
    if report.get("hypothesis"):
        print(f"hypothesis: {report['hypothesis']}")
    for suggestion in report.get("homologous_guidance", []):
        print(
            "homologous next: "
            f"{suggestion['sibling_parameter']}={suggestion['winning_value']!r} — "
            f"{suggestion['reason']}"
        )
        print(f"  parameters: {suggestion['suggested_parameters']}")
    print(f"manifest: {report['manifest']}")


def campaign_status_command(args: argparse.Namespace) -> int:
    try:
        manifest = find_manifest(args.campaign, state_root=args.state_dir)
        report = build_status(manifest)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_status(report)
    return 0


def campaign_resume_command(args: argparse.Namespace) -> int:
    try:
        manifest_path = find_manifest(args.campaign, state_root=args.state_dir)
        manifest = validate_resume(manifest_path)
        previously_exact = manifest.get("status") == "exact"
        already_exact = (
            previously_exact
            and manifest["execution"].get("stop_on_exact", True)
            and not args.continue_after_exact
        )
        sources = [] if already_exact else remaining_sources(manifest)
        if sources:
            inputs = manifest["identity_inputs"]
            compile_info = inputs["compile"]
            execution = manifest["execution"]
            experiment = manifest.get("experiment")
            candidate_metadata = None
            selected_region = None
            if isinstance(experiment, dict):
                parameters_by_source = {
                    str(item["source"]): item.get("parameters", {})
                    for item in experiment.get("candidates", [])
                    if isinstance(item, dict) and "source" in item
                }
                candidate_metadata = {
                    str(source["cache_key"]): {
                        "schema": EXPERIMENT_SCHEMA,
                        "family": experiment["family"],
                        "parameters": parameters_by_source.get(str(source["path"]), {}),
                        "parameter_space": experiment.get("parameters", {}),
                        "baseline": experiment.get("baseline"),
                        "manifest": experiment.get("path"),
                    }
                    for source in manifest["sources"]
                }
                region = experiment.get("selected_region")
                if isinstance(region, dict):
                    selected_region = RegionConstraint(
                        start=int(region["start"]),
                        end=int(region["end"]),
                        name=str(region.get("name", "selected")),
                    )
            results, _ = run_campaign(
                sources,
                target=inputs["target"]["path"],
                template=compile_info["template"],
                cache_dir=manifest["cache_directory"],
                ledger=manifest["ledger"],
                jobs=args.jobs or execution["jobs"],
                objdump=inputs["objdump"]["requested"],
                symbol=inputs.get("symbol"),
                section=inputs["section"],
                environment=compile_info["environment"],
                compile_cwd=compile_info["working_directory"],
                stop_on_exact=execution["stop_on_exact"],
                timeout=(
                    args.timeout
                    if args.timeout is not None
                    else execution["timeout_seconds"]
                ),
                artifact_dir=manifest.get("artifact_directory"),
                candidate_metadata=candidate_metadata,
                selected_region=selected_region,
                rank_by=str(execution.get("rank_by", "auto")),
            )
            finish_manifest(
                manifest_path,
                results=len(results),
                prepared=len(manifest["sources"]),
                exact=(
                    previously_exact
                    or any(
                        item.comparison is not None and item.comparison.exact
                        for item in results
                    )
                ),
            )
        report = build_status(manifest_path)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        if not sources:
            if already_exact:
                print(
                    "resume: exact result already recorded; pass "
                    "--continue-after-exact to run the intentionally skipped grid"
                )
            else:
                print(
                    "resume: nothing to run; every manifest candidate has a "
                    "ledger record"
                )
        _print_status(report)
    return 0


def _render_html(report: dict[str, Any]) -> str:
    campaign = report["campaign"]
    serialized = json.dumps(report, indent=2, sort_keys=True)
    rows = []
    for point in campaign["trajectory"]:
        rows.append(
            "<tr>"
            f"<td>{int(point['record'])}</td>"
            f"<td>{html.escape(str(point['source']))}</td>"
            f"<td>{html.escape(str(point['verdict']))}</td>"
            f"<td>{html.escape(str(point['aligned_total']))}</td>"
            f"<td>{html.escape(str(point['words']))}</td>"
            "</tr>"
        )
    table = "\n".join(rows) or '<tr><td colspan="5">No results yet.</td></tr>'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>decomp-workbench campaign report</title>
<style>
:root {{ color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }}
body {{ max-width: 72rem; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border-bottom: 1px solid #8886; padding: .45rem; text-align: left; }}
code, pre {{ font-family: ui-monospace, monospace; }}
pre {{ overflow: auto; padding: 1rem; background: #8881; }}
.proof {{ border-left: .25rem solid #a86; padding-left: 1rem; }}
</style>
</head>
<body>
<h1>Campaign {html.escape(str(campaign["status"]))}</h1>
<p>{int(campaign["recorded_candidates"])} recorded candidate(s),
{len(campaign["object_basins"])} object basin(s),
{int(campaign["remaining_candidates"])} remaining.</p>
<p class="proof">{html.escape(str(report["proof"]))}</p>
<h2>Trajectory</h2>
<table>
<thead><tr><th>#</th><th>Source</th><th>Verdict</th><th>Aligned</th><th>Words</th></tr></thead>
<tbody>{table}</tbody>
</table>
<details><summary>Machine-readable evidence</summary>
<pre id="report">{html.escape(serialized)}</pre>
</details>
</body>
</html>
"""


def campaign_export_command(args: argparse.Namespace) -> int:
    try:
        manifest = find_manifest(args.campaign, state_root=args.state_dir)
        report = export_status(manifest)
        output = Path(args.output).expanduser().resolve()
        if output.exists():
            raise FileExistsError(f"refusing to overwrite campaign export: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        content = (
            _render_html(report)
            if args.format == "html"
            else json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        with output.open("x", encoding="utf-8") as destination:
            destination.write(content)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    payload = {
        "schema": "decomp-workbench-campaign-export-result-v1",
        "format": args.format,
        "output": str(output),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"campaign {args.format} export: {output}")
    return 0


def campaign_note_command(args: argparse.Namespace) -> int:
    try:
        manifest = find_manifest(args.campaign, state_root=args.state_dir)
        updated = update_hypothesis(manifest, args.note)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    payload = {
        "schema": "decomp-workbench-campaign-note-v1",
        "manifest": str(manifest),
        "hypothesis": updated["hypothesis"],
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"campaign hypothesis: {payload['hypothesis']}")
        print(f"manifest: {manifest}")
    return 0


def campaign_survey_command(args: argparse.Namespace) -> int:
    from .terminal import emit_lines

    try:
        report = survey_campaign(args.directory, budget=args.budget, base=args.base)
    except (CampaignSurveyError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    emit_lines(
        survey_lines(report, limit=args.limit or len(report["stages"]) or 1),
        width=args.width,
        pager=args.pager,
    )
    return 0


def campaign_package_command(args: argparse.Namespace) -> int:
    """Promote a measured campaign winner into a paste-ready scratch bundle."""

    try:
        manifest_path = find_manifest(args.campaign, state_root=args.state_dir)
        manifest = validate_resume(manifest_path)
        report = build_status(manifest_path)
        selected_key = "best_temp_prefix" if args.selection == "temp-prefix" else "best"
        selected = report.get(selected_key)
        if not isinstance(selected, dict):
            raise ValueError("campaign has no successful candidate to package")
        comparison = selected.get("comparison")
        if not isinstance(comparison, dict):
            raise ValueError("selected campaign candidate has no comparison evidence")
        raw_value = comparison.get("raw", comparison.get("raw_word_mismatches"))
        relocation_value = comparison.get("relocation_target_mismatches")
        accepted = (
            bool(comparison.get("exact"))
            and isinstance(raw_value, int)
            and raw_value == 0
            and isinstance(relocation_value, int)
            and relocation_value == 0
        )
        if not accepted and not args.allow_mismatch:
            raise ValueError(
                "selected candidate is not scratch-accepted; pass --allow-mismatch "
                "only when intentionally packaging a near-match"
            )
        cache_key = selected.get("cache_key")
        source_record = next(
            (
                item
                for item in manifest.get("sources", [])
                if isinstance(item, dict) and item.get("cache_key") == cache_key
            ),
            None,
        )
        if not isinstance(source_record, dict):
            raise ValueError("selected source is absent from the campaign manifest")
        source = Path(str(source_record["path"]))
        if not source.is_file():
            raise FileNotFoundError(
                f"selected campaign source no longer exists: {source}"
            )
        result = bundle_scratch(
            args.output,
            target_assembly=args.target_assembly,
            context=args.context,
            source=source,
            platform=args.platform,
            compiler=args.compiler,
            compiler_flags=args.compiler_flags,
            diff_label=args.diff_label,
            project=args.project,
            preset=args.preset,
            compiler_id=args.compiler_id,
            language=args.language,
            provenance={
                "schema": "decomp-workbench-campaign-promotion-v1",
                "campaign_identity": manifest["identity"],
                "campaign_manifest": str(manifest_path),
                "selection": args.selection,
                "source_cache_key": cache_key,
                "source_sha256": source_record["sha256"],
                "scratch_accepted": accepted,
                "comparison": comparison,
            },
        )
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    payload = {
        "schema": "decomp-workbench-campaign-package-result-v1",
        "output": result.output,
        "source": str(source),
        "selection": args.selection,
        "scratch_accepted": accepted,
        "manifest": result.manifest,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"campaign scratch bundle: {result.output}")
        print(f"source: {source}")
        print(f"acceptance: {'ACCEPTED' if accepted else 'MISMATCH ALLOWED'}")
        print(
            "next: verify SHA256SUMS, then follow the generated README.md paste order"
        )
    return 0


_SURVEY_DESCRIPTION = (
    "Read a campaign working directory -- the one holding the stage "
    "directories -- and report what is in it: every stage by recency with its "
    "file, source and object counts; the findings logs with their pending "
    "sidecar notes; the sweep manifests and their coverage; the "
    "instrument-gate stamps, or their absence. It is a reading taken now, not "
    "a registry: nothing is stored, so nothing here can be a stale claim, and "
    "nothing here guesses which artifact is the base. For a manifest "
    "`campaign run` wrote, the command is `campaign status`."
)


def register_campaign_cockpit_commands(
    commands: argparse._SubParsersAction[Any],
) -> None:
    survey = commands.add_parser(
        "campaign-survey",
        help=argparse.SUPPRESS,
        description=_SURVEY_DESCRIPTION,
        epilog="example: decomp-workbench campaign survey .workbench/my-campaign",
    )
    survey.add_argument("directory", help="the campaign working directory")
    survey.add_argument(
        "--base",
        metavar="FILE",
        help="hash this file now and print it as the pinned base",
    )
    survey.add_argument(
        "--budget",
        type=int,
        default=40000,
        metavar="N",
        help="files to walk before stopping and saying so (default: 40000)",
    )
    survey.add_argument(
        "--limit",
        type=int,
        default=20,
        metavar="N",
        help="stage rows to print before eliding (default: 20; 0 prints all)",
    )
    survey.add_argument("--json", action="store_true", help="emit JSON")
    _add_terminal(survey)
    survey.set_defaults(
        handler=campaign_survey_command, report_command="campaign-survey"
    )

    status = commands.add_parser(
        "campaign-status",
        help=argparse.SUPPRESS,
        description="Show best candidate, trajectory, failures, and object basins.",
    )
    status.add_argument("campaign", nargs="?", help="manifest, directory, or ID")
    status.add_argument("--state-dir", default=".decomp-workbench")
    status.add_argument("--json", action="store_true", help="emit JSON")
    status.set_defaults(handler=campaign_status_command)

    resume = commands.add_parser(
        "campaign-resume",
        help=argparse.SUPPRESS,
        description="Resume only candidates not represented in the campaign ledger.",
    )
    resume.add_argument("campaign", nargs="?", help="manifest, directory, or ID")
    resume.add_argument("--state-dir", default=".decomp-workbench")
    resume.add_argument("--jobs", type=int)
    resume.add_argument("--timeout", type=float)
    resume.add_argument(
        "--continue-after-exact",
        action="store_true",
        help="run candidates intentionally skipped after the first exact result",
    )
    resume.add_argument("--json", action="store_true", help="emit JSON")
    resume.set_defaults(handler=campaign_resume_command)

    export = commands.add_parser(
        "campaign-export",
        help=argparse.SUPPRESS,
        description="Write bounded, shareable campaign evidence as JSON or HTML.",
    )
    export.add_argument("campaign", nargs="?", help="manifest, directory, or ID")
    export.add_argument("--state-dir", default=".decomp-workbench")
    export.add_argument("--output", required=True)
    export.add_argument("--format", choices=("json", "html"), default="html")
    export.add_argument("--json", action="store_true", help="emit result JSON")
    export.set_defaults(handler=campaign_export_command)

    package = commands.add_parser(
        "campaign-package",
        help=argparse.SUPPRESS,
        description=(
            "Promote a validated campaign winner into a deterministic, "
            "paste-ready decomp.me scratch bundle."
        ),
    )
    package.add_argument("campaign", nargs="?", help="manifest, directory, or ID")
    package.add_argument("--state-dir", default=".decomp-workbench")
    package.add_argument("--output", required=True)
    package.add_argument(
        "--selection",
        choices=("score", "temp-prefix"),
        default="score",
    )
    package.add_argument("--allow-mismatch", action="store_true")
    package.add_argument("--target-assembly", required=True)
    package.add_argument("--context", required=True)
    package.add_argument("--platform", required=True)
    package.add_argument("--compiler", required=True)
    package.add_argument("--compiler-id")
    package.add_argument("--language")
    package.add_argument("--compiler-flags", default="")
    package.add_argument("--diff-label", required=True)
    package.add_argument("--project")
    package.add_argument("--preset")
    package.add_argument("--json", action="store_true", help="emit JSON")
    package.set_defaults(handler=campaign_package_command)

    note = commands.add_parser(
        "campaign-note",
        help=argparse.SUPPRESS,
        description="Persist the active campaign hypothesis for status and handoff.",
    )
    note.add_argument("note")
    note.add_argument("campaign", nargs="?", help="manifest, directory, or ID")
    note.add_argument("--state-dir", default=".decomp-workbench")
    note.add_argument("--json", action="store_true", help="emit JSON")
    note.set_defaults(handler=campaign_note_command)


def _add_terminal(parser: argparse.ArgumentParser) -> None:
    from .terminal import add_terminal_arguments

    add_terminal_arguments(parser)
