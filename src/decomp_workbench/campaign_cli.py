"""Persistent campaign cockpit commands."""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

from .campaign import file_sha256, run_campaign
from .campaign_finish import finish_campaign
from .campaign_state import (
    build_status,
    durable_source_path,
    export_status,
    finalize_source_retention,
    find_manifest,
    finish_manifest,
    record_control_preflight,
    remaining_sources,
    update_hypothesis,
    validate_resume,
)
from .campaign_survey import CampaignSurveyError, survey_campaign, survey_lines
from .compare import MIXED_ALIGNMENT_CAUTION
from .experiment_controls import run_control_preflight
from .experiments import (
    EXPERIMENT_SCHEMA,
    RegionConstraint,
    SignalSpec,
    load_experiment,
)
from .html_report import document_shell
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
    ranked_by = str(report.get("ranked_by", report.get("rank_by", "auto")))
    requested_rank = str(report.get("rank_by", "auto"))
    requested_note = (
        f" (requested {requested_rank})" if requested_rank != ranked_by else ""
    )
    print(f"ranking: {ranked_by}{requested_note}")
    if bool(report.get("alignment_ranking_unsafe")) and requested_rank == "auto":
        print(MIXED_ALIGNMENT_CAUTION)
    retention = report.get("source_retention")
    if isinstance(retention, dict):
        print(
            "sources: "
            f"policy={retention.get('policy')} "
            f"retained={retention.get('retained')} "
            f"pending={retention.get('pending')} "
            f"not-retained={retention.get('not_retained')}"
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
    controls = report.get("controls", {})
    if isinstance(controls, dict) and controls.get("status") != "NOT DECLARED":
        print(
            f"controls: {controls.get('passed_required', 0)}/"
            f"{controls.get('required', 0)} required PASS "
            f"({controls.get('status')})"
        )
    coverage = report.get("coverage")
    if isinstance(coverage, dict):
        declared = coverage.get("declared_assignments")
        if declared is None:
            print(
                f"coverage: unknown denominator; "
                f"{coverage.get('visited_assignments', 0)} visited "
                f"[{coverage.get('conclusion')}]"
            )
        else:
            print(
                f"coverage: {coverage.get('visited_assignments', 0)}/{declared} "
                f"visited, {coverage.get('excluded_assignments', 0)} excluded "
                f"[{coverage.get('conclusion')}]"
            )
    if report["trajectory"] and ranked_by != "temp-prefix":
        trajectory_field = (
            "best_words" if ranked_by == "words" else "best_aligned_total"
        )
        trajectory_label = "best words" if ranked_by == "words" else "best aligned"
        values = [
            int(point[trajectory_field])
            for point in report["trajectory"]
            if point.get(trajectory_field) is not None
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
            print(
                f"trajectory: {values[0]} {sparkline} {values[-1]} ({trajectory_label})"
            )
    if report.get("mechanism_trajectory"):
        transitions = report["mechanism_trajectory"]
        print(f"mechanism transitions: {len(transitions)}")
        for transition in transitions[-8:]:
            print(
                f"  #{transition['record']} {transition['signal']}: "
                f"{transition['from'] or 'UNMEASURED'} -> {transition['to']} "
                f"({transition['source']})"
            )
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
        manifest_path = find_manifest(
            args.campaign,
            state_root=args.state_dir,
            require_explicit_when_ambiguous=True,
        )
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
            signal_specs: tuple[SignalSpec, ...] = ()
            if isinstance(experiment, dict):
                experiment_path = experiment.get("path")
                loaded_experiment = (
                    load_experiment(str(experiment_path))
                    if isinstance(experiment_path, str)
                    else None
                )
                if loaded_experiment is not None:
                    signal_specs = loaded_experiment.signals
                    if loaded_experiment.controls and not bool(
                        manifest.get("control_preflight", {}).get("passed")
                    ):
                        control_report = run_control_preflight(
                            loaded_experiment,
                            target=inputs["target"]["path"],
                            template=compile_info["template"],
                            cache_dir=manifest["cache_directory"],
                            objdump=inputs["objdump"]["requested"],
                            symbol=inputs.get("symbol"),
                            section=inputs["section"],
                            environment=compile_info["environment"],
                            compile_cwd=compile_info["working_directory"],
                            timeout=(
                                args.timeout
                                if args.timeout is not None
                                else execution["timeout_seconds"]
                            ),
                            stream_limit=65536,
                            artifact_dir=manifest.get("artifact_directory"),
                            compilation_envelope=compile_info.get("envelope", {}),
                        )
                        record_control_preflight(manifest_path, control_report)
                        if not control_report["passed"]:
                            finish_manifest(
                                manifest_path,
                                results=0,
                                prepared=len(manifest["sources"]),
                                exact=False,
                                control_invalid=True,
                            )
                            raise ValueError(
                                "required experiment control failed; ordinary "
                                "candidates were not scheduled"
                            )
                if loaded_experiment is not None:
                    candidate_metadata = {
                        str(source["cache_key"]): loaded_experiment.metadata_for(
                            str(source["path"])
                        )
                        for source in manifest["sources"]
                    }
                else:
                    parameters_by_source = {
                        str(item["source"]): item.get("parameters", {})
                        for item in experiment.get("candidates", [])
                        if isinstance(item, dict) and "source" in item
                    }
                    candidate_metadata = {
                        str(source["cache_key"]): {
                            "schema": experiment.get("schema", EXPERIMENT_SCHEMA),
                            "family": experiment["family"],
                            "parameters": parameters_by_source.get(
                                str(source["path"]), {}
                            ),
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
                signal_specs=signal_specs,
                compilation_envelope=compile_info.get("envelope", {}),
                rank_by=str(execution.get("rank_by", "auto")),
            )
            finalize_source_retention(manifest_path)
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
    coverage = campaign.get("coverage", {})
    controls = campaign.get("controls", {})
    mechanism_rows = (
        "\n".join(
            "<li>"
            f"#{int(item['record'])} {html.escape(str(item['signal']))}: "
            f"{html.escape(str(item.get('from') or 'UNMEASURED'))} → "
            f"{html.escape(str(item['to']))} "
            f"({html.escape(str(item.get('source')))})"
            "</li>"
            for item in campaign.get("mechanism_trajectory", [])
        )
        or "<li>No declared signal transitions.</li>"
    )
    ranking_note = (
        " (alignment gaps made aligned totals incomparable)"
        if campaign.get("alignment_ranking_unsafe")
        else ""
    )
    body = f"""
<h1>Campaign {html.escape(str(campaign["status"]))}</h1>
<p>{int(campaign["recorded_candidates"])} recorded candidate(s),
{len(campaign["object_basins"])} object basin(s),
{int(campaign["remaining_candidates"])} remaining.</p>
<p><strong>Ranking:</strong>
{html.escape(str(campaign.get("ranked_by", campaign.get("rank_by", "auto"))))}
{html.escape(ranking_note)}.</p>
<p><strong>Controls:</strong>
{html.escape(str(controls.get("status", "NOT DECLARED")))}.
<strong>Coverage:</strong> {html.escape(str(coverage.get("visited_assignments", 0)))} /
{html.escape(str(coverage.get("declared_assignments") or "unknown"))} visited;
conclusion={html.escape(str(coverage.get("conclusion", "coverage-unknown")))}.</p>
<p class="proof">{html.escape(str(report["proof"]))}</p>
<h2>Trajectory</h2>
<div class="table-scroll"><table><caption>Candidate trajectory</caption>
<thead><tr><th>#</th><th>Source</th><th>Verdict</th><th>Aligned</th><th>Words</th></tr></thead>
<tbody>{table}</tbody>
</table></div>
<h2>Mechanism trajectory</h2>
<ul>{mechanism_rows}</ul>
"""
    return document_shell("decomp-workbench campaign report", body, report)


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
        manifest = find_manifest(
            args.campaign,
            state_root=args.state_dir,
            require_explicit_when_ambiguous=True,
        )
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
        manifest_path = find_manifest(
            args.campaign,
            state_root=args.state_dir,
            require_explicit_when_ambiguous=True,
        )
        manifest = validate_resume(manifest_path, allow_retained_sources=True)
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
        source = durable_source_path(source_record)
        if not source.is_file():
            raise FileNotFoundError(
                f"selected campaign source no longer exists: {source}"
            )
        recorded_source_hash = selected.get("source_sha256")
        if (
            recorded_source_hash is not None
            and recorded_source_hash != source_record.get("sha256")
        ):
            raise ValueError(
                "selected ledger record and campaign manifest disagree on the "
                "source hash; refusing mutable promotion"
            )
        cache_object = Path(str(manifest["cache_directory"])) / f"{cache_key}.o"
        if not cache_object.is_file():
            raise FileNotFoundError(
                "selected immutable campaign object is absent from cache: "
                f"{cache_object}"
            )
        actual_object_hash = file_sha256(cache_object)
        recorded_object_hash = selected.get("object_sha256")
        if (
            recorded_object_hash is not None
            and actual_object_hash != recorded_object_hash
        ):
            raise ValueError(
                "selected cached object hash changed; refusing source/object promotion"
            )
        finish_receipt: dict[str, Any] | None = None
        finish_receipt_hash: str | None = None
        if args.finish_receipt:
            finish_path = Path(args.finish_receipt).expanduser().resolve()
            finish_receipt_hash = file_sha256(finish_path)
            finish_receipt = json.loads(finish_path.read_text(encoding="utf-8"))
            winner = finish_receipt.get("winner", {})
            if (
                finish_receipt.get("schema") != "decomp-workbench-campaign-finish-v1"
                or finish_receipt.get("status") != "PASS"
                or finish_receipt.get("campaign_identity") != manifest["identity"]
                or not isinstance(winner, dict)
                or winner.get("cache_key") != cache_key
                or winner.get("source_sha256") != source_record["sha256"]
                or winner.get("recorded_object_sha256") != actual_object_hash
            ):
                raise ValueError(
                    "finish receipt is not a passing receipt for this immutable winner"
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
                "object_sha256": actual_object_hash,
                "recorded_at_unix": selected.get("recorded_at_unix"),
                "ledger_record_cache_key": cache_key,
                "target_sha256": manifest["identity_inputs"]["target"]["sha256"],
                "scratch_accepted": accepted,
                "comparison": comparison,
                "finish_receipt": (
                    str(Path(args.finish_receipt).expanduser().resolve())
                    if finish_receipt is not None
                    else None
                ),
                "finish_receipt_sha256": finish_receipt_hash,
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


def campaign_finish_command(args: argparse.Namespace) -> int:
    """Freshly rebuild a winner and record every integration gate separately."""

    try:
        manifest = find_manifest(
            args.campaign,
            state_root=args.state_dir,
            require_explicit_when_ambiguous=True,
        )
        report, output = finish_campaign(
            manifest,
            selection=args.selection,
            output=args.output,
            format=args.format,
            scratch_context=args.scratch_context,
            scratch_compile_command=args.scratch_compile_command,
            collateral_reference=args.collateral_reference,
            handoff=args.handoff,
            project_command=args.project_command,
            project_timeout=args.project_timeout,
            stream_limit=args.stream_limit,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(
            json.dumps(
                {
                    "schema": "decomp-workbench-campaign-finish-result-v1",
                    "output": str(output),
                    "status": report["status"],
                    "ready": report["ready"],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"campaign finish: {report['status']}")
        for name, gate in report["gates"].items():
            print(f"  {name.replace('_', ' ')}: {gate['status']} — {gate['reason']}")
        print(f"receipt: {output}")
    return 0 if report["ready"] else 1


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
    package.add_argument(
        "--finish-receipt",
        help="require a passing JSON campaign-finish receipt for the selected winner",
    )
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

    finish = commands.add_parser(
        "campaign-finish",
        help=argparse.SUPPRESS,
        description=(
            "Freshly rebuild one immutable winner and record function, signal, "
            "scratch, collateral, handoff, and project gates independently."
        ),
    )
    finish.add_argument("campaign", nargs="?", help="manifest, directory, or ID")
    finish.add_argument("--state-dir", default=".decomp-workbench")
    finish.add_argument(
        "--selection", choices=("score", "temp-prefix"), default="score"
    )
    finish.add_argument("--output")
    finish.add_argument("--format", choices=("json", "html"), default="json")
    finish.add_argument("--scratch-context")
    finish.add_argument("--scratch-compile-command")
    finish.add_argument("--collateral-reference")
    finish.add_argument("--handoff")
    finish.add_argument("--project-command")
    finish.add_argument("--project-timeout", type=float, default=120.0)
    finish.add_argument("--stream-limit", type=int, default=65536)
    finish.add_argument("--json", action="store_true", help="emit result JSON")
    finish.set_defaults(handler=campaign_finish_command)

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
