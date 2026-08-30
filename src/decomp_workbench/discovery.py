"""Compact journey map, non-breaking command groups, and shell completions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Mapping
from typing import Any, NoReturn

from .reporting import schema_for

#: One readable word in place of argparse's generated choice list.
COMMAND_METAVAR = "COMMAND"

#: Matches argparse's own invalid-choice sentence, whichever metavar it used.
INVALID_CHOICE_RE = re.compile(
    r"argument (?P<argument>\S+): invalid choice: (?P<value>'[^']*')"
)


class CommandParser(argparse.ArgumentParser):
    """An `ArgumentParser` that will not answer a typo with a catalogue.

    argparse generates its own ``(choose from a, b, c, ...)`` list, which for
    this program is a forty-odd name paragraph attached to a one-word mistake.
    Suppressing the metavar fixes the usage line but not this sentence, and
    there is no public hook for it, so the message is rewritten on the way out.
    Everything else about `error` is left exactly as argparse defines it,
    including the exit status.
    """

    def error(self, message: str) -> NoReturn:
        match = INVALID_CHOICE_RE.match(message)
        if match is not None:
            self.print_usage(sys.stderr)
            self.exit(
                2,
                f"{self.prog}: error: {match.group('value')} is not a "
                f"{self.prog} command.\n"
                f"Run `{self.prog.split()[0]} commands` for the compact "
                f"journey map, or `{self.prog} --help` for every command.\n",
            )
        super().error(message)


COMMAND_MAP: dict[str, tuple[tuple[str, str], ...]] = {
    "object": (
        ("next", "name the next diagnostic step, with the command and why"),
        ("score", "one honest headline number for how far this candidate is"),
        ("diagnose", "one-screen exactness, mechanism, and next lever"),
        ("compare", "exact object truth and ranked metrics"),
        ("align", "the edit script between two objects, tolerant of shifts"),
        ("phase", "the scratch-ring phase vector over named row slots"),
        ("view", "full aligned mechanism evidence"),
        ("window", "print named aligned rows side by side"),
        ("force-rows", "join an allocator force control to the rows it moved"),
        ("slots", "count the loads, stores and address-takes per frame offset"),
        ("rank", "triage prebuilt candidate objects"),
        ("relocation-aliases", "prove linked-address-equivalent spellings"),
        ("collateral", "expose whole-object changes outside an exact function"),
        ("staleness", "refuse a comparison against a build older than its inputs"),
        ("linked-compare", "classify a built image against the target, per range"),
        ("reloc-surface", "synthesize a module's placeholder values from the image"),
        ("reloc-proof", "bind static relocation identities to exact linked bytes"),
    ),
    "scratch": (
        ("fetch", "download one decomp.me export into the standard layout"),
        ("public-match-check", "gate 0: is this function already matched in public?"),
        ("check", "validate or site-faithfully compile a decomp.me export"),
        ("bundle", "build a deterministic manual-upload handoff"),
        ("doctor", "verify retained-dump, object, and compiler readiness"),
    ),
    "handoff": (
        ("audit", "catch missing, local-only, and untracked publication dependencies"),
    ),
    "campaign": (
        ("run", "compile, cache, rank, and record source candidates"),
        ("status", "show trajectory, failures, families, and basins"),
        ("survey", "read a campaign working directory that has no manifest"),
        ("resume", "run only manifest work absent from the ledger"),
        ("note", "persist the active hypothesis for status and handoff"),
        ("export", "write bounded shareable JSON or HTML evidence"),
        ("package", "promote a winner into a paste-ready scratch bundle"),
        ("finish", "freshly rebuild a winner and audit every integration gate"),
        ("checkpoint", "archive distinct current and deterministically ranked best"),
        ("restore-best", "materialize best with drift checks and a backup"),
        ("accept", "point the manifest at one immutable accepted artifact"),
        ("dossier-add", "append a tested hypothesis and do-not-repeat result"),
        ("dossier-list", "query tested hypotheses by function or result"),
        ("readiness", "split source work from identity and remeasurement queues"),
    ),
    "experiment": (
        ("validate", "check paths, parameter assignments, and region bounds"),
        ("inspect-source", "inventory suspicious constructs before cleanup"),
        ("review-mutation", "diff a sweep winner before adopting it"),
        ("compose", "generate bounded combinations of proven mechanisms"),
    ),
    "cache": (
        ("status", "inspect cache size and age"),
        ("prune", "dry-run or recoverably move old entries to trash"),
        ("restore", "restore a prune without overwriting entries"),
    ),
    "note": (
        ("reserve", "claim the next unused identifiers before filing under them"),
        ("add", "record a finding that a concurrent writer cannot lose"),
        ("list", "render the log's entries plus the pending sidecar notes"),
        ("merge", "append pending notes to the log under an exclusive lock"),
    ),
    "context": (
        ("lint", "audit #if/#elif guards for the undefined-identifier trap"),
        ("duplicates", "find file-scope definitions repeated across fragments"),
    ),
    "project": (
        ("init", "preview discovery and explicitly write durable defaults"),
        ("show", "show resolved target, candidate, symbol, and tool defaults"),
        ("next", "run next from the configured object pair"),
        ("compare", "run compare from the configured object pair"),
        ("diagnose", "run diagnose from the configured object pair"),
        ("campaign", "run a campaign from configured build and lineage inputs"),
    ),
    "trace": (
        ("a71", "inspect or diff IDO 7.1 final-color records"),
        ("cascade", "every round of one allocator site's decision cascade"),
        ("order", "the p1 colouring order, with the same-save ties named"),
        ("blocks", "which webs occur in which blocks, and where the sets meet"),
        ("frame", "the frame ladder: every stack slot one procedure owns"),
        ("summary", "summarize function and allocator trace events"),
        ("fifo", "replay ugen pool get/put state"),
        ("globalcolor", "inspect a focused allocator decision"),
        ("origin-probe", "classify one controlled edit's allocator-web delta"),
        ("copy-decisions", "show coalesced-versus-temporary copy decisions"),
        ("alias", "inspect base-provenance and alias-query traces"),
        ("scheduler", "inspect named ready-set decisions and tie-breaks"),
        ("pre", "inspect PRE and speculative-hoist decisions"),
        ("webs", "align allocator webs by semantic provenance"),
        ("source", "join web lines to preprocessor and listing evidence"),
        ("stack-homes", "query virtual and final stack-home ownership"),
    ),
    "instrument": (
        ("ugen", "add opt-in ugen function/free-list traces"),
        ("uopt", "apply pinned, fidelity-gated uopt profiles"),
        ("globalcolor", "add focused allocator color probes"),
        ("alias", "add base-provenance alias probes"),
        ("scheduler", "apply a hash-pinned external scheduler profile"),
        ("pre", "apply a hash-pinned PRE/hoist profile"),
        ("fidelity", "gate meaningful sections, relocations, and symbols"),
        ("gate", "prove an instrumented build reproduces stock, and stamp it"),
    ),
    "pass": (
        ("replay-as1", "calibrate and probe late assembler scheduling"),
        ("replay-ugen", "replay a Ucode stream through stock ugen and as1"),
        ("diff", "compare user-supplied original and static pass boundaries"),
        ("binasm", "inspect a retained ugen-to-as1 peephole boundary"),
        ("ucode", "inspect retained XJP ranges, selectors, and case tables"),
    ),
    "capture": (
        ("make", "wrap an IDO root so a build retains every pass boundary"),
        ("runs", "list collected runs with phase, argv, and stream sizes"),
    ),
    "ucode": (
        ("inspect", "inspect retained XJP ranges, selectors, and case tables"),
        ("window", "print the decoded records around one stream position"),
        ("patch", "insert, replace, or delete whole records safely"),
    ),
    "binasm": (
        ("inspect", "inspect a retained ugen-to-as1 peephole boundary"),
        ("window", "print the decoded records around one stream position"),
    ),
    "stream": (("diff", "compare two phase streams record by record"),),
    "probe": (
        ("lines", "probe whether statement line assignment owns a schedule"),
        ("equiv", "the ranges over which every read of a local is one value"),
        ("deadread", "positions where a zero-footprint discarded read can be tried"),
    ),
    "sweep": (
        ("build", "compile a wave of candidates and score them into one table"),
        ("regress", "price every accumulated construct by removing it"),
        ("carriers", "the locals that are dead at a site, and therefore free"),
        ("donors", "the locals whose live range avoids a fusion target's"),
        ("hoist", "hoist an operand into every available carrier"),
        ("commute", "exchange every commutative operand pair"),
        ("copies", "drop a copy and rehost its reads on the original"),
        ("fuse", "fuse a donor's live range into the target's"),
        ("ingest", "gate, score and rank a built variant family"),
    ),
    "toolchain": (
        ("init", "materialize a real-copy toolchain with calibration gates"),
        ("calibrate", "run replay, collateral, and project-output gates"),
        ("status", "verify hashes and show the strongest supported claim"),
        ("fingerprint", "compile redistributable behavioral microcases"),
        ("lineage", "compare symbol lineage across object revisions"),
    ),
    "shift": (
        ("audit", "inventory where a linked project's addresses come from"),
        ("rehearse", "relink against a padded script and explain every changed word"),
        ("config", "prove a linker-config edit reproduces the shipped link exactly"),
        ("plan", "merge the reports into one ranked, gated remediation queue"),
    ),
    "target": (
        ("audit", "verify a target object's ELF scope and literal-pool extent"),
    ),
    "permute": (
        ("sweep", "drive decomp-permuter over a queue with a faithful scratch"),
        ("doctor", "preflight one function's scratch before searching it"),
        ("classify", "assign each swept function a measured wall class"),
    ),
    "ranking": (
        ("stamp", "record the tree hash a closeness ranking was measured on"),
        ("check", "report whether a ranking still describes the current tree"),
    ),
    "oracle": (
        ("plan", "build an honest two-phase allocator force grid"),
        ("diff", "compare compiler decisions by semantic web provenance"),
        ("force", "run a calibrated causal force set plus its baseline"),
        ("sweep", "run the full measured force grid as a cached campaign"),
        ("status", "render the latest durable sweep without recompiling"),
        ("export", "write self-contained JSON or HTML oracle evidence"),
    ),
}

GROUP_ALIASES: dict[tuple[str, str], str] = {
    ("object", "next"): "next",
    ("object", "next-dumps"): "next-dumps",
    ("object", "score"): "score",
    ("object", "compare"): "compare",
    ("object", "compare-dumps"): "compare-dumps",
    ("object", "align"): "align",
    ("object", "align-dumps"): "align-dumps",
    ("object", "phase"): "phase",
    ("object", "phase-dumps"): "phase-dumps",
    ("object", "diagnose"): "diagnose",
    ("object", "diagnose-dumps"): "diagnose-dumps",
    ("object", "view"): "view",
    ("object", "view-dumps"): "view-dumps",
    ("object", "window"): "window",
    ("object", "window-dumps"): "window-dumps",
    ("object", "force-rows"): "force-rows",
    ("object", "force-rows-dumps"): "force-rows-dumps",
    ("object", "slots"): "slots",
    ("object", "rank"): "rank",
    ("object", "relocation-aliases"): "relocation-aliases",
    ("object", "collateral"): "object-collateral",
    ("object", "staleness"): "check-staleness",
    ("object", "linked-compare"): "linked-compare",
    ("object", "reloc-surface"): "reloc-surface",
    ("object", "reloc-proof"): "reloc-proof",
    ("scratch", "fetch"): "fetch-scratch",
    ("scratch", "public-match-check"): "public-match-check",
    ("scratch", "check"): "check-scratch",
    ("scratch", "bundle"): "bundle-scratch",
    ("scratch", "doctor"): "doctor",
    ("handoff", "audit"): "audit-handoff",
    ("campaign", "run"): "campaign",
    ("campaign", "status"): "campaign-status",
    ("campaign", "survey"): "campaign-survey",
    ("campaign", "resume"): "campaign-resume",
    ("campaign", "note"): "campaign-note",
    ("campaign", "export"): "campaign-export",
    ("campaign", "package"): "campaign-package",
    ("campaign", "finish"): "campaign-finish",
    ("campaign", "checkpoint"): "campaign-checkpoint",
    ("campaign", "restore-best"): "campaign-restore-best",
    ("campaign", "accept"): "campaign-accept",
    ("campaign", "dossier-add"): "campaign-dossier-add",
    ("campaign", "dossier-list"): "campaign-dossier-list",
    ("campaign", "readiness"): "target-readiness",
    ("note", "add"): "note-add",
    ("note", "reserve"): "note-reserve",
    ("note", "list"): "note-list",
    ("note", "merge"): "note-merge",
    ("trace", "blocks"): "trace-blocks",
    ("trace", "a71"): "trace-a71",
    ("trace", "cascade"): "trace-cascade",
    ("trace", "frame"): "trace-frame",
    ("trace", "order"): "trace-order",
    ("trace", "summary"): "trace-summary",
    ("trace", "fifo"): "trace-fifo",
    ("trace", "globalcolor"): "trace-globalcolor",
    ("trace", "origin-probe"): "trace-origin-probe",
    ("trace", "copy-decisions"): "trace-copy-decisions",
    ("trace", "alias"): "trace-alias",
    ("trace", "scheduler"): "trace-scheduler",
    ("trace", "pre"): "trace-pre",
    ("trace", "webs"): "trace-webs",
    ("trace", "source"): "trace-source",
    ("trace", "stack-homes"): "trace-stack-homes",
    ("instrument", "ugen"): "instrument-ugen",
    ("instrument", "uopt"): "instrument-uopt",
    ("instrument", "globalcolor"): "instrument-uopt-globalcolor",
    ("instrument", "alias"): "instrument-uopt-alias",
    ("instrument", "scheduler"): "instrument-scheduler",
    ("instrument", "pre"): "instrument-pre",
    ("instrument", "fidelity"): "fidelity",
    ("instrument", "gate"): "instrument-gate",
    ("pass", "replay-as1"): "replay-as1",
    ("pass", "replay-ugen"): "replay-ugen",
    ("pass", "diff"): "pass-diff",
    ("pass", "binasm"): "inspect-binasm",
    ("pass", "ucode"): "inspect-ucode",
    ("capture", "make"): "capture-make",
    ("capture", "runs"): "capture-runs",
    ("ucode", "inspect"): "inspect-ucode",
    ("ucode", "window"): "ucode-window",
    ("ucode", "patch"): "ucode-patch",
    ("binasm", "inspect"): "inspect-binasm",
    ("binasm", "window"): "binasm-window",
    ("stream", "diff"): "stream-diff",
    ("probe", "deadread"): "probe-deadread",
    ("probe", "equiv"): "probe-equiv",
    ("probe", "lines"): "probe-lines",
    ("sweep", "build"): "sweep-build",
    ("sweep", "carriers"): "sweep-carriers",
    ("sweep", "commute"): "sweep-commute",
    ("sweep", "copies"): "sweep-copies",
    ("sweep", "donors"): "sweep-donors",
    ("sweep", "fuse"): "sweep-fuse",
    ("sweep", "hoist"): "sweep-hoist",
    ("sweep", "ingest"): "sweep-ingest",
    ("sweep", "regress"): "sweep-regress",
    ("toolchain", "fingerprint"): "fingerprint-toolchain",
    ("toolchain", "lineage"): "lineage",
    ("toolchain", "init"): "toolchain-init",
    ("toolchain", "calibrate"): "toolchain-calibrate",
    ("toolchain", "status"): "toolchain-status",
}

#: Every command that may open a network connection, as journey coordinates.
#:
#: The workbench is offline-first: analysis reads local files and never calls
#: out, so this set is the whole network surface and is small enough to read.
#: A command is listed here only if a user must name it explicitly; nothing
#: else in the package may reach it, and no command fetches anything on a
#: caller's behalf as a side effect of doing something local.
NETWORK_COMMANDS: frozenset[tuple[str, str]] = frozenset(
    {
        ("scratch", "fetch"),
        ("scratch", "public-match-check"),
    }
)

#: The hosts the listed commands contact, and why. Stated once so a reader,
#: an auditor, or an egress policy can see the whole list without reading code.
NETWORK_HOSTS: tuple[dict[str, str], ...] = (
    {
        "host": "decomp.me",
        "why": (
            "public scratch export download and public scratch search, over "
            "HTTPS, read-only, one request per term"
        ),
    },
)

#: The policy the inventory above implements, in one sentence per rule.
NETWORK_POLICY: tuple[str, ...] = (
    "Offline-first: every analysis command reads local files only.",
    "A network command never runs implicitly; a user names it explicitly.",
    "A network command is never a step inside another command.",
    "Requests identify the workbench and its version honestly, and are "
    "serialized, timed out, retried at most once, and cached on disk.",
)

HIDDEN_FLAT_COMMANDS = frozenset(
    {
        "campaign-accept",
        "campaign-checkpoint",
        "campaign-dossier-add",
        "campaign-dossier-list",
        "campaign-export",
        "campaign-finish",
        "campaign-note",
        "campaign-package",
        "campaign-resume",
        "campaign-restore-best",
        "campaign-status",
        "campaign-survey",
        "next-dumps",
        "binasm-window",
        "capture-make",
        "capture-runs",
        "inspect-binasm",
        "inspect-ucode",
        "stream-diff",
        "ucode-patch",
        "ucode-window",
        "note-add",
        "note-list",
        "note-merge",
        "note-reserve",
        "sweep-build",
        "sweep-carriers",
        "sweep-commute",
        "sweep-copies",
        "sweep-donors",
        "sweep-fuse",
        "sweep-hoist",
        "sweep-ingest",
        "sweep-regress",
        "toolchain-calibrate",
        "toolchain-init",
        "toolchain-status",
    }
)


def rewrite_group_alias(arguments: list[str]) -> list[str]:
    """Translate a journey spelling to its stable flat implementation."""

    if len(arguments) == 1 and arguments[0] in COMMAND_MAP:
        return ["commands", "--group", arguments[0]]
    if len(arguments) < 2:
        return arguments
    command = GROUP_ALIASES.get((arguments[0], arguments[1]))
    return [command, *arguments[2:]] if command else arguments


def command_map_payload() -> dict[str, Any]:
    def safety(group: str, command: str) -> dict[str, object]:
        stateful = {
            ("cache", "restore"),
            ("campaign", "finish"),
            ("campaign", "checkpoint"),
            ("campaign", "restore-best"),
            ("campaign", "accept"),
            ("campaign", "dossier-add"),
            ("campaign", "note"),
            ("campaign", "package"),
            ("campaign", "resume"),
            ("campaign", "run"),
            ("note", "add"),
            ("note", "merge"),
            ("note", "reserve"),
            ("oracle", "force"),
            ("oracle", "sweep"),
            ("project", "campaign"),
            ("toolchain", "calibrate"),
            ("toolchain", "init"),
        }
        explicit_output = {
            ("campaign", "export"),
            ("permute", "doctor"),
            ("permute", "sweep"),
            ("capture", "make"),
            ("experiment", "compose"),
            ("instrument", "alias"),
            ("instrument", "fidelity"),
            ("instrument", "gate"),
            ("instrument", "globalcolor"),
            ("instrument", "scheduler"),
            ("instrument", "pre"),
            ("instrument", "ugen"),
            ("instrument", "uopt"),
            ("oracle", "export"),
            ("pass", "replay-as1"),
            ("project", "init"),
            ("scratch", "bundle"),
            ("shift", "plan"),
            ("sweep", "commute"),
            ("sweep", "copies"),
            ("sweep", "fuse"),
            ("sweep", "hoist"),
            ("sweep", "regress"),
        }
        dry_run_default = (group, command) in {
            ("cache", "prune"),
            ("project", "init"),
        }
        external_process = group == "object" or (group, command) in {
            ("campaign", "finish"),
            ("permute", "doctor"),
            ("permute", "sweep"),
            ("campaign", "resume"),
            ("campaign", "run"),
            ("instrument", "fidelity"),
            ("instrument", "gate"),
            ("oracle", "force"),
            ("oracle", "sweep"),
            ("pass", "replay-as1"),
            ("project", "compare"),
            ("project", "diagnose"),
            ("project", "next"),
            ("project", "campaign"),
            ("scratch", "check"),
            ("scratch", "doctor"),
            ("shift", "rehearse"),
            ("sweep", "ingest"),
            ("toolchain", "calibrate"),
            ("toolchain", "fingerprint"),
        }
        return {
            "default": (
                "dry-run"
                if dry_run_default
                else "stateful"
                if (group, command) in stateful
                else "writes-explicit-output"
                if (group, command) in explicit_output
                else "read-only"
            ),
            "external_process": external_process,
            "network": (group, command) in NETWORK_COMMANDS,
            "destructive": False,
        }

    report_overrides = {
        ("project", "campaign"): "campaign",
        ("project", "compare"): "compare",
        ("project", "diagnose"): "diagnose",
        ("project", "next"): "next",
    }
    return {
        "schema": "decomp-workbench-command-map-v1",
        "groups": {
            group: [
                {
                    "command": command,
                    "invocation": ["decomp-workbench", group, command],
                    "description": description,
                    "report_schema": schema_for(
                        report_overrides.get(
                            (group, command),
                            GROUP_ALIASES.get((group, command), f"{group}-{command}"),
                        )
                    ),
                    "safety": safety(group, command),
                }
                for command, description in entries
            ]
            for group, entries in COMMAND_MAP.items()
        },
        "automation": {
            "success": "one versioned JSON document when --json is supported",
            "failure_schema": "decomp-workbench-error-v1",
            "exit_codes": {
                "0": "success",
                "1": "gate/no-result",
                "2": "usage/capability/process",
                "3": "census-failed",
            },
            "next_actions": "next reports command_argv, safety, and expected_signal",
        },
        # The network surface as an inventory rather than a per-command flag a
        # consumer would have to scan for. An empty `commands` list is the
        # positive claim that nothing in this build can open a connection.
        "network": {
            "policy": list(NETWORK_POLICY),
            "commands": [
                {
                    "invocation": ["decomp-workbench", group, command],
                    "command": f"{group} {command}",
                }
                for group, command in sorted(NETWORK_COMMANDS)
            ],
            "hosts": [dict(host) for host in NETWORK_HOSTS],
        },
        "compatibility": (
            "Existing flat command names remain supported; grouped spellings "
            "are aliases."
        ),
    }


def render_command_map(*, group: str | None = None) -> list[str]:
    groups: Mapping[str, tuple[tuple[str, str], ...]] = COMMAND_MAP
    if group:
        if group not in groups:
            raise ValueError(f"unknown command group: {group}")
        groups = {group: groups[group]}
    lines = [
        "Journey command map",
        "Grouped spellings and existing flat commands are both supported.",
    ]
    for name, entries in groups.items():
        lines.extend(("", name))
        width = max(len(command) for command, _ in entries)
        lines.extend(
            f"  {name} {command.ljust(width)}  {description}"
            for command, description in entries
        )
    lines.extend(
        (
            "",
            "Start here: decomp-workbench doctor",
            # The flat spelling, because it is the only one README and
            # START_HERE teach. Grouped spellings are explained in
            # docs/workflows.md; a first command should match the page the
            # reader just came from.
            "Common diagnosis: decomp-workbench diagnose target.o candidate.o",
            "Next lever: decomp-workbench guide <playbook|verdict|lever>",
            # A backlog of functions is a loop rather than a command, and the
            # groups above list its steps a screen apart. One line names the
            # order and its two guards, which is what a reader scanning this
            # map for "what do I run after the sweep" is looking for.
            "Late-stage loop: ranking check -> permute doctor -> permute sweep",
            "                 -> permute classify -> diagnose --trace"
            " -> compare --built-from",
            "                 (docs/permute-sweep.md)",
        )
    )
    return lines


def commands_command(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(command_map_payload(), indent=2, sort_keys=True))
    else:
        print("\n".join(render_command_map(group=args.group)))
    return 0


def group_help_command(args: argparse.Namespace) -> int:
    print("\n".join(render_command_map(group=args.command)))
    return 0


def subcommand_listing_handler(
    parser: argparse.ArgumentParser,
) -> Callable[[argparse.Namespace], int]:
    """Return a handler that prints ``parser``'s own listing and succeeds.

    Printing the operations a command group offers is the success path of
    discovery, not a usage error: `argparse`'s ``required=True`` answers it on
    stderr with exit 2, which breaks `set -e` scripts and reads as a failure to
    anyone who just wanted to know what was available. Naming a subcommand that
    does not exist is still an error, and still exits non-zero.
    """

    def handler(_args: argparse.Namespace) -> int:
        parser.print_help()
        return 0

    return handler


def _top_level_words(parser: argparse.ArgumentParser) -> list[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return sorted(
                name for name in action.choices if name not in HIDDEN_FLAT_COMMANDS
            )
    return []


def finalize_command_help(
    commands: argparse._SubParsersAction[Any],
) -> None:
    """Keep compatible flat aliases parseable without leaking them into help.

    ``argparse`` renders ``help=SUPPRESS`` as the literal ``==SUPPRESS==`` for
    subparsers and still includes those choices in its generated metavar. It
    exposes no public hook for hiding a parseable subcommand, so keep the
    choices intact and adjust only the two presentation attributes.

    The metavar is a single word rather than the visible-command list. Forty-odd
    names inline made the usage line — the first thing every argument error
    prints — unreadable, and the list they replaced is one command away.
    """

    commands._choices_actions[:] = [
        choice
        for choice in commands._choices_actions
        if choice.dest not in HIDDEN_FLAT_COMMANDS
    ]
    commands.metavar = COMMAND_METAVAR


def _command_options(parser: argparse.ArgumentParser) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, child in action.choices.items():
            result[name] = sorted(
                option
                for child_action in child._actions
                for option in child_action.option_strings
            )
    return result


def _operation_options(
    parser: argparse.ArgumentParser,
) -> dict[tuple[str, str], list[str]]:
    """Return live options for grouped aliases and real nested commands."""

    top_options = _command_options(parser)
    top_children: dict[str, argparse.ArgumentParser] = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            top_children.update(action.choices)
    result: dict[tuple[str, str], list[str]] = {}
    for group, operations in COMMAND_MAP.items():
        nested = top_children.get(group)
        nested_children: dict[str, argparse.ArgumentParser] = {}
        if nested is not None:
            for action in nested._actions:
                if isinstance(action, argparse._SubParsersAction):
                    nested_children.update(action.choices)
        for operation, _description in operations:
            alias = GROUP_ALIASES.get((group, operation))
            if alias is not None:
                result[(group, operation)] = top_options.get(alias, [])
                continue
            child = nested_children.get(operation)
            result[(group, operation)] = (
                sorted(
                    option
                    for action in child._actions
                    for option in action.option_strings
                )
                if child is not None
                else []
            )
    return result


def command_registry_errors(parser: argparse.ArgumentParser) -> tuple[str, ...]:
    """Return journey-map entries absent from the live parser.

    Command implementations remain in focused modules; this validates the
    seam that generates grouped help, aliases, and completion from one map.
    """

    top_children: dict[str, argparse.ArgumentParser] = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            top_children.update(action.choices)
    errors: list[str] = []
    for group, entries in COMMAND_MAP.items():
        group_parser = top_children.get(group)
        if group_parser is None:
            errors.append(f"missing command group: {group}")
        nested: set[str] = set()
        if group_parser is not None:
            for action in group_parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    nested.update(action.choices)
        for operation, _description in entries:
            alias = GROUP_ALIASES.get((group, operation))
            if alias is not None:
                if alias not in top_children:
                    errors.append(
                        f"{group} {operation} aliases missing command {alias}"
                    )
            elif operation not in nested:
                errors.append(f"missing grouped command: {group} {operation}")
    return tuple(errors)


def render_completion(parser: argparse.ArgumentParser, shell: str) -> str:
    """Generate a dependency-free completion script from the live parser."""

    commands = _top_level_words(parser)
    options = _command_options(parser)
    operation_options = _operation_options(parser)
    words = " ".join(commands)
    operations = {
        group: " ".join(command for command, _description in entries)
        for group, entries in COMMAND_MAP.items()
    }
    if shell == "bash":
        option_cases = "\n".join(
            f"    {name}) opts={json.dumps(' '.join(values))} ;;"
            for name, values in options.items()
        )
        operation_cases = "\n".join(
            f"    {group}) ops={json.dumps(values)} ;;"
            for group, values in operations.items()
        )
        nested_option_cases = "\n".join(
            f"    {group}:{operation}) opts={json.dumps(' '.join(values))} ;;"
            for (group, operation), values in operation_options.items()
        )
        return f"""_decomp_workbench() {{
  local cur cmd op ops opts
  cur="${{COMP_WORDS[COMP_CWORD]}}"
  if [[ $COMP_CWORD -eq 1 ]]; then
    COMPREPLY=( $(compgen -W {json.dumps(words)} -- "$cur") )
    return
  fi
  cmd="${{COMP_WORDS[1]}}"
  case "$cmd" in
{operation_cases}
  esac
  if [[ -n $ops ]]; then
    if [[ $COMP_CWORD -eq 2 ]]; then
      COMPREPLY=( $(compgen -W "$ops" -- "$cur") )
      return
    fi
    op="${{COMP_WORDS[2]}}"
    case "$cmd:$op" in
{nested_option_cases}
    esac
  else
  case "$cmd" in
{option_cases}
  esac
  fi
  COMPREPLY=( $(compgen -W "$opts" -- "$cur") )
}}
complete -F _decomp_workbench decomp-workbench
"""
    if shell == "zsh":
        operation_cases = "\n".join(
            f"    {group}) ops=("
            + " ".join(json.dumps(item) for item in values.split())
            + ") ;;"
            for group, values in operations.items()
        )
        option_cases = "\n".join(
            f"    {name}) opts=({' '.join(json.dumps(item) for item in values)}) ;;"
            for name, values in options.items()
        )
        nested_option_cases = "\n".join(
            f"    {group}:{operation}) opts=("
            + " ".join(json.dumps(item) for item in values)
            + ") ;;"
            for (group, operation), values in operation_options.items()
        )
        return f"""#compdef decomp-workbench
_decomp_workbench() {{
  local -a commands ops opts
  local cmd op
  commands=({" ".join(json.dumps(item) for item in commands)})
  if (( CURRENT == 2 )); then
    compadd -- $commands
    return
  fi
  cmd=$words[2]
  case "$cmd" in
{operation_cases}
  esac
  if (( ${{#ops}} )); then
    if (( CURRENT == 3 )); then
      compadd -- $ops
      return
    fi
    op=$words[3]
    case "$cmd:$op" in
{nested_option_cases}
    esac
  else
    case "$cmd" in
{option_cases}
    esac
  fi
  compadd -- $opts
}}
compdef _decomp_workbench decomp-workbench
"""
    if shell == "fish":
        lines = [
            "complete -c decomp-workbench -f",
            *(
                f"complete -c decomp-workbench -n '__fish_use_subcommand' "
                f"-a {json.dumps(command)}"
                for command in commands
            ),
        ]
        for group, group_operations in operations.items():
            condition = (
                f"__fish_seen_subcommand_from {group}; and not "
                f"__fish_seen_subcommand_from {group_operations}"
            )
            lines.append(
                f"complete -c decomp-workbench -n {json.dumps(condition)} "
                f"-a {json.dumps(group_operations)}"
            )
        for (group, operation), values in operation_options.items():
            if not values:
                continue
            condition = (
                f"__fish_seen_subcommand_from {group}; and "
                f"__fish_seen_subcommand_from {operation}"
            )
            lines.append(
                f"complete -c decomp-workbench -n {json.dumps(condition)} "
                f"-a {json.dumps(' '.join(values))}"
            )
        return "\n".join(lines) + "\n"
    if shell == "powershell":
        choices = ", ".join(f"'{item}'" for item in commands)
        group_cases = "\n".join(
            f"    '{group}' {{ $choices = @("
            + ", ".join(f"'{item}'" for item in values.split())
            + ") }"
            for group, values in operations.items()
        )
        nested_cases = "\n".join(
            f"    '{group}:{operation}' {{ $choices = @("
            + ", ".join(f"'{item}'" for item in values)
            + ") }"
            for (group, operation), values in operation_options.items()
            if values
        )
        return f"""Register-ArgumentCompleter -Native `
  -CommandName decomp-workbench -ScriptBlock {{
  param($wordToComplete, $commandAst, $cursorPosition)
  $tokens = @($commandAst.CommandElements | ForEach-Object {{ $_.Extent.Text }})
  $choices = @({choices})
  if ($tokens.Count -ge 2) {{
    switch ($tokens[1]) {{
{group_cases}
    }}
  }}
  if ($tokens.Count -ge 3) {{
    $operation = "$($tokens[1]):$($tokens[2])"
    switch ($operation) {{
{nested_cases}
    }}
  }}
  $choices | Where-Object {{ $_ -like "$wordToComplete*" }} |
    ForEach-Object {{ [System.Management.Automation.CompletionResult]::new($_) }}
}}
"""
    raise ValueError(f"unsupported shell: {shell}")


def completion_command(args: argparse.Namespace) -> int:
    from .cli import build_parser

    try:
        script = render_completion(build_parser(), args.shell)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(script, end="")
    return 0


def register_discovery_commands(
    commands: argparse._SubParsersAction[Any],
) -> None:
    command_map = commands.add_parser(
        "commands",
        help="show the compact journey-oriented command map",
    )
    command_map.add_argument("--group", choices=sorted(COMMAND_MAP))
    command_map.add_argument("--json", action="store_true", help="emit JSON")
    command_map.set_defaults(handler=commands_command)

    completion = commands.add_parser(
        "completion",
        help="generate shell completion from the live command parser",
    )
    completion.add_argument(
        "shell",
        choices=("bash", "zsh", "fish", "powershell"),
    )
    completion.set_defaults(handler=completion_command)

    # Every group whose own name is not already a command. `probe` was
    # shipped without one and answered `decomp-workbench probe` with "not a
    # command", which is the opposite of what a reader asking what is on offer
    # deserves.
    for group in (
        "object",
        "scratch",
        "handoff",
        "note",
        "probe",
        "sweep",
        "trace",
        "instrument",
        "pass",
        "capture",
        "ucode",
        "binasm",
        "stream",
        "toolchain",
    ):
        entries = COMMAND_MAP[group]
        width = max(len(operation) for operation, _description in entries)
        operation_help = "\n".join(
            f"  {group} {operation.ljust(width)}  {description}"
            for operation, description in entries
        )
        parser = commands.add_parser(
            group,
            help=f"{group} journey commands; run without arguments for a map",
            description=(
                "Grouped spellings and existing flat commands are both supported."
            ),
            epilog=operation_help,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.set_defaults(handler=group_help_command)
