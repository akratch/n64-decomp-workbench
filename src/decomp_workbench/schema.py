"""One registry of comparison metric identities.

Human output and JSON output are rendered from the same tuple, so a printed
label can never drift from the JSON key that carries the same number. Two
recorded campaigns lost debugging cycles to ``words=`` in the terminal versus
``word_mismatches`` in ``--json``; naming both from one entry makes that
divergence structurally impossible.

The canonical name of a metric is its printed label *and* its JSON key. Where
a JSON key used to be spelled differently, the old spelling remains available
as a deprecated alias emitted alongside the canonical key for one release.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Any, Literal

RenderKind = Literal["integer", "text"]


@dataclass(frozen=True)
class Metric:
    """One reported value with a single name for humans and machines."""

    key: str
    """Canonical name: the printed label and the JSON key."""

    attribute: str
    """The :class:`~decomp_workbench.model.Comparison` attribute holding it."""

    description: str
    """One line explaining what the value means and what it is good for."""

    summary: bool = False
    """Whether the value appears on the one-line human summary."""

    width: int = 0
    """Field width used on the summary line."""

    kind: RenderKind = "text"

    @property
    def deprecated_keys(self) -> tuple[str, ...]:
        """Return JSON keys retained for compatibility with older consumers."""

        return () if self.attribute == self.key else (self.attribute,)

    def render(self, value: Any) -> str:
        """Render one value exactly as the summary line prints it."""

        if self.kind == "integer" and isinstance(value, int):
            return f"{value:{self.width}d}"
        return f"{value!s:>{self.width}s}" if self.width else str(value)


METRICS: tuple[Metric, ...] = (
    Metric(
        "verdict",
        "verdict",
        "mechanism class that explains the residual",
        summary=True,
    ),
    Metric(
        "aligned_total",
        "aligned_total",
        "LCS-aligned differing rows a source change controls; the ranking "
        "metric, and the sum of the aligned_* class counts below",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "words",
        "word_mismatches",
        "positional word differences after masking known linker-controlled "
        "fields; the function-level matching oracle, and the tiebreaker "
        "between two candidates of the same aligned shape",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "aligned_structural",
        "aligned_structural",
        "aligned rows with an opcode or operand shape difference",
    ),
    Metric(
        "aligned_schedule",
        "aligned_schedule",
        "aligned rows in a pure reordering hunk",
    ),
    Metric(
        "aligned_register",
        "aligned_register",
        "aligned rows differing only in register allocation",
    ),
    Metric(
        "aligned_constant",
        "aligned_constant",
        "aligned rows differing only in an immediate",
    ),
    Metric(
        "aligned_commutative",
        "aligned_commutative",
        "aligned rows with a swapped commutative operand pair",
    ),
    Metric(
        "raw",
        "raw_word_mismatches",
        "positional 32-bit word differences before masking; literal identity "
        "evidence, not a matching score",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "norm",
        "normalized_distance",
        "edit distance after masking addresses, immediates, and stack "
        "offsets; search guidance only",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "regs",
        "register_mismatches",
        "positional register-operand differences",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "fp",
        "fp_register_mismatches",
        "positional differences involving $fN registers",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "insns",
        "candidate_instructions",
        "instructions compared in the candidate function",
        summary=True,
        width=4,
        kind="integer",
    ),
    Metric(
        "frame",
        "candidate_frame_size",
        "first addiu sp,sp,N adjustment in the candidate",
        summary=True,
        width=5,
    ),
    Metric(
        "sha1",
        "candidate_sha1",
        "short hash of the candidate's compared instruction words",
        summary=True,
    ),
    Metric(
        "target_insns",
        "target_instructions",
        "instructions compared in the target function",
    ),
    Metric(
        "insn_delta",
        "instruction_delta",
        "candidate instruction count minus target instruction count",
    ),
    Metric("opcodes", "opcode_mismatches", "positional mnemonic differences"),
    Metric(
        "relocs",
        "relocation_metadata_mismatches",
        "positional relocation-kind differences; prevents an exact verdict",
    ),
    Metric(
        "unknown_relocations",
        "unknown_relocations",
        "relocation kinds without a precise field mask; prevents an exact "
        "verdict rather than guessing",
    ),
    Metric(
        "target_frame",
        "target_frame_size",
        "first addiu sp,sp,N adjustment in the target",
    ),
    Metric(
        "sha256",
        "candidate_sha256",
        "full hash of the candidate's compared instruction words; the "
        "object-basin identity",
    ),
    Metric(
        "exact",
        "exact",
        "masked words and relocation-kind layout agree for this function",
    ),
    Metric(
        "structural_exact",
        "structural_exact",
        "opcode sequence, normalized shape, registers, frame, and count "
        "agree; cross-ROM/lineage evidence only",
    ),
    Metric(
        "diff_sites",
        "diff_sites",
        "every differing site with its class; never filtered by the verdict",
    ),
    Metric(
        "diff_site_classes",
        "diff_site_classes",
        "count of differing sites per class",
    ),
    Metric(
        "aligned_diff_sites",
        "aligned_diff_sites",
        "LCS-aligned residual sites anchored to target instruction indices",
    ),
    Metric(
        "raw_difference_breakdown",
        "raw_difference_breakdown",
        "why literal words differ: instruction bits, relocation layout, or "
        "relocation-controlled fields",
    ),
    Metric(
        "register_mismatch_ranges",
        "register_mismatch_ranges",
        "inclusive index ranges of register-operand differences",
    ),
    Metric(
        "fp_mismatch_ranges",
        "fp_mismatch_ranges",
        "inclusive index ranges of $fN operand differences",
    ),
    Metric(
        "register_diff",
        "register_diff",
        "register-differing sites only; a subset of diff_sites",
    ),
    Metric(
        "candidate_fp_register_uses",
        "candidate_fp_register_uses",
        "histogram of candidate $fN operands",
    ),
    Metric(
        "candidate_stack_offsets",
        "candidate_stack_offsets",
        "histogram of candidate N(sp) operands; spill and local-home evidence",
    ),
    Metric("guidance", "guidance", "the next useful action for this verdict"),
    Metric(
        "warnings",
        "warnings",
        "conditions that make this verdict answer a different question",
    ),
    Metric("symbol", "symbol", "selected function, or null for a whole section"),
    Metric("target", "target", "reference object or dump"),
    Metric("candidate", "candidate", "candidate object, dump, or source path"),
    Metric("error", "error", "why this comparison could not be produced"),
)

# Campaign-level report keys. They describe a run rather than one comparison,
# so they are listed separately, but `--explain-keys` must still explain every
# key a campaign emits.
CAMPAIGN_METRICS: tuple[Metric, ...] = (
    Metric("schema", "schema", "report schema identity"),
    Metric(
        "unique_candidates",
        "unique_candidates",
        "candidates that were compiled and compared in this run",
    ),
    Metric(
        "prepared_candidates",
        "prepared_candidates",
        "candidates resolved and deduplicated before the run started",
    ),
    Metric(
        "source_files",
        "source_files",
        "source paths supplied, before deduplication by cache key",
    ),
    Metric(
        "stopped_on_exact",
        "stopped_on_exact",
        "whether an exact match ended the run before every prepared candidate "
        "was submitted; candidates already running were still recorded",
    ),
    Metric(
        "timeout_seconds",
        "timeout_seconds",
        "per-candidate compiler deadline; timed-out process groups are ended",
    ),
    Metric(
        "object_basins",
        "object_basins",
        "distinct compared-function bytes, with the variants that reached each",
    ),
    Metric(
        "manifest",
        "manifest",
        "durable campaign identity and resume state, or null with --no-ledger",
    ),
    Metric(
        "ledger",
        "ledger",
        "append-only per-candidate evidence, or null with --no-ledger",
    ),
    Metric(
        "experiment",
        "experiment",
        "transformation family, parameter space, and selected-region invariant",
    ),
    Metric("results", "results", "per-candidate records, best rank first"),
)

# Aligned mechanism view keys (``view`` / ``view-dumps``). The view reports
# aligned rows rather than positional words, so it is its own vocabulary: a few
# spellings it shares with the comparison registry (``target_instructions``,
# ``candidate_frame_size``) are canonical here and deprecated there, and that is
# the point -- an aligned count and a positional count are different numbers and
# must not be read through one name. Every key here is already its own printed
# label, so none of them carries a deprecated alias.
VIEW_METRICS: tuple[Metric, ...] = (
    Metric("symbol", "symbol", "function selected from both inputs"),
    Metric("target", "target", "reference input name"),
    Metric("candidate", "candidate", "candidate input name"),
    Metric(
        "register_profile",
        "register_profile",
        "register class table used for the lanes",
    ),
    Metric(
        "target_instructions",
        "target_instructions",
        "instructions parsed from the target",
    ),
    Metric(
        "candidate_instructions",
        "candidate_instructions",
        "instructions parsed from the candidate",
    ),
    Metric("aligned_rows", "aligned_rows", "rows in the LCS alignment"),
    Metric("target_frame_size", "target_frame_size", "target stack frame adjustment"),
    Metric(
        "candidate_frame_size",
        "candidate_frame_size",
        "candidate stack frame adjustment",
    ),
    Metric("match", "match", "aligned rows whose instructions are identical"),
    Metric(
        "displacement",
        "displacement",
        "aligned rows differing only in an alignment-controlled branch offset",
    ),
    Metric(
        "structural",
        "structural",
        "aligned rows with an opcode or operand shape difference",
    ),
    Metric("schedule", "schedule", "aligned rows in a pure reordering hunk"),
    Metric(
        "register", "register", "aligned rows differing only in register allocation"
    ),
    Metric("constant", "constant", "aligned rows differing only in an immediate"),
    Metric(
        "commutative",
        "commutative",
        "aligned rows with a swapped commutative operand pair",
    ),
    Metric(
        "relocation",
        "relocation",
        "aligned rows differing only in linker-controlled fields",
    ),
    Metric("verdict", "verdict", "cheapest mechanism that explains the residual"),
    Metric("playbook", "playbook", "named lever family for the verdict"),
    Metric("signature", "signature", "orthogonal modifiers attached to the verdict"),
    Metric(
        "prefix_exact",
        "prefix_exact",
        "first aligned row whose instruction words differ",
    ),
    Metric("hunks", "hunks", "contiguous runs of non-matching aligned rows"),
    Metric("lanes", "lanes", "per-class register assignment sequences"),
    Metric("webs", "webs", "consistent register substitutions, grouped"),
    Metric("next", "next", "lever guidance for the dominant class"),
    Metric(
        "warnings",
        "warnings",
        "conditions that make this verdict answer a different question",
    ),
    Metric(
        "register_report",
        "register_report",
        "per aligned row register operands, matches included",
    ),
    Metric("hunk", "hunk", "hunk number"),
    Metric("class", "class", "classification label"),
    Metric("classes", "classes", "per-class row counts inside a hunk"),
    Metric("rows", "rows", "aligned row range"),
    Metric("target_bytes", "target_bytes", "target section offsets covered"),
    Metric("candidate_bytes", "candidate_bytes", "candidate section offsets covered"),
    Metric("index", "index", "aligned row index"),
    Metric(
        "slot",
        "slot",
        "first lane position where the two sides differ",
    ),
    Metric(
        "aligned_row",
        "aligned_row",
        "aligned row holding a lane divergence; the same unit as aligned_rows",
    ),
    Metric(
        "rotation",
        "rotation",
        "cyclic offset that maps the target lane tail onto the candidate",
    ),
    Metric("slots", "slots", "lane slots rendered out of the total"),
    Metric("web", "web", "web identifier"),
    Metric("count", "count", "number of sites"),
)

# Keys a command wraps around a report rather than measures. They answer
# "what did this invocation decide", not "what do these two objects look like",
# which is why they are not in the comparison registry -- but a key nobody
# explains is the defect the registry exists to prevent, so they are registered
# and ``--explain-keys`` prints them too.
COMMAND_METRICS: tuple[Metric, ...] = (
    Metric(
        "accepted",
        "accepted",
        "whether this invocation satisfies --fail-on-mismatch",
    ),
    Metric(
        "acceptance_basis",
        "acceptance_basis",
        "function-exact, cross-rom-structural, or mismatch: why the command "
        "accepted or rejected the comparison",
    ),
    Metric(
        "census",
        "census",
        "--census predicate results; exit 3 when any of them fails, which is "
        "distinct from the exit 1 of --fail-on-mismatch",
    ),
    Metric("key", "key", "the metric one census predicate asked about"),
    Metric("expected", "expected", "the value a census predicate was written with"),
    Metric("actual", "actual", "the value the report carried for that key"),
    Metric("pass", "pass", "whether one census predicate held"),
)

METRICS_BY_KEY: dict[str, Metric] = {
    item.key: item for item in (*METRICS, *CAMPAIGN_METRICS)
}
#: The view report is a separate namespace, so it gets a separate lookup: the
#: two registries share spellings that mean different numbers.
VIEW_METRICS_BY_KEY: dict[str, Metric] = {item.key: item for item in VIEW_METRICS}
SUMMARY_METRICS: tuple[Metric, ...] = tuple(item for item in METRICS if item.summary)
DEPRECATED_KEYS: dict[str, str] = {
    alias: item.key for item in METRICS for alias in item.deprecated_keys
}
#: Spellings ``--census`` accepts on a comparison, mapped to the report key
#: each one reads. The deprecated aliases are accepted for as long as the JSON
#: still emits them: a predicate should not stop working one release before the
#: key it names does.
COMPARISON_CENSUS_KEYS: dict[str, str] = {
    **{item.key: item.key for item in METRICS},
    **DEPRECATED_KEYS,
}
#: Spellings ``--census`` accepts on the aligned view. The view has no
#: compatibility spellings, so its keys are exactly its own.
VIEW_CENSUS_KEYS: dict[str, str] = {item.key: item.key for item in VIEW_METRICS}


def summary_line(item: Any) -> str:
    """Render the one-line human summary from the registry."""

    fields = " ".join(
        f"{metric.key}={metric.render(getattr(item, metric.attribute))}"
        for metric in SUMMARY_METRICS
    )
    return f"{fields} {item.candidate}"


def canonical_fields(item: Any) -> dict[str, Any]:
    """Return the canonical JSON keys whose spelling changed."""

    return {
        metric.key: getattr(item, metric.attribute)
        for metric in METRICS
        if metric.deprecated_keys
    }


def selected_fields(item: Any, keys: tuple[str, ...]) -> dict[str, Any]:
    """Return canonical and deprecated JSON keys for selected metrics."""

    payload: dict[str, Any] = {}
    for key in keys:
        metric = METRICS_BY_KEY[key]
        value = getattr(item, metric.attribute)
        payload[metric.key] = value
        for alias in metric.deprecated_keys:
            payload[alias] = value
    return payload


EXPLAIN_WIDTH = 88


def explain_keys_text() -> str:
    """Return the printed registry: label, JSON key, and meaning."""

    header = (
        "Comparison keys. The printed label and the JSON key are the same "
        "string.\n"
        "Deprecated JSON keys are still emitted beside the canonical key for "
        "one release;\n"
        "new consumers should read the canonical key. Every key is followed "
        "by its meaning.\n"
    )
    titles = ("key", "line", "deprecated json key", "")

    def describe(metrics: tuple[Metric, ...]) -> list[tuple[str, str, str, str]]:
        return [
            (
                metric.key,
                "yes" if metric.summary else "-",
                ", ".join(metric.deprecated_keys) or "-",
                metric.description,
            )
            for metric in metrics
        ]

    rows = describe(METRICS)
    campaign_rows = describe(CAMPAIGN_METRICS)
    view_rows = describe(VIEW_METRICS)
    command_rows = describe(COMMAND_METRICS)
    widths = [
        max(
            len(titles[column]),
            *(
                len(row[column])
                for row in rows + campaign_rows + view_rows + command_rows
            ),
        )
        for column in range(3)
    ]

    def format_columns(row: tuple[str, str, str, str]) -> str:
        return "  ".join(
            row[column].ljust(widths[column]) for column in range(3)
        ).rstrip()

    def format_rows(items: list[tuple[str, str, str, str]]) -> list[str]:
        lines: list[str] = []
        for row in items:
            lines.append(format_columns(row))
            lines.extend(
                textwrap.wrap(
                    row[3],
                    EXPLAIN_WIDTH,
                    initial_indent="    ",
                    subsequent_indent="    ",
                )
            )
        return lines

    separator = "  ".join("-" * width for width in widths)
    return "\n".join(
        [
            header,
            format_columns(titles),
            separator,
            *format_rows(rows),
            "",
            "Campaign report keys (campaign --json / --json-summary).",
            "",
            format_columns(titles),
            separator,
            *format_rows(campaign_rows),
            "",
            "Aligned mechanism view keys (view / view-dumps). These count "
            "aligned rows, not",
            "positional words, so a spelling shared with the comparison "
            "registry above is a",
            "different number. Nested keys (hunks, lanes, webs) are listed "
            "with the rest.",
            "",
            format_columns(titles),
            separator,
            *format_rows(view_rows),
            "",
            "Command result keys. These describe what one invocation decided "
            "rather than what",
            "the two inputs look like: acceptance, and the --census predicate "
            "results (exit 3",
            "when any predicate fails, distinct from the exit 1 of "
            "--fail-on-mismatch).",
            "",
            format_columns(titles),
            separator,
            *format_rows(command_rows),
        ]
    )
