"""Compact journey map, non-breaking command groups, and shell completions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable, Mapping
from typing import Any, NoReturn

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
                f"Run `{self.prog} commands` for the compact journey map, or "
                f"`{self.prog} --help` for every command.\n",
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
    ),
    "scratch": (
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
    "context": (("lint", "audit #if/#elif guards for the undefined-identifier trap"),),
    "trace": (
        ("cascade", "every round of one allocator site's decision cascade"),
        ("order", "the p1 colouring order, with the same-save ties named"),
        ("blocks", "which webs occur in which blocks, and where the sets meet"),
        ("summary", "summarize function and allocator trace events"),
        ("fifo", "replay ugen pool get/put state"),
        ("globalcolor", "inspect a focused allocator decision"),
        ("origin-probe", "classify one controlled edit's allocator-web delta"),
        ("copy-decisions", "show coalesced-versus-temporary copy decisions"),
        ("alias", "inspect base-provenance and alias-query traces"),
        ("scheduler", "inspect named ready-set decisions and tie-breaks"),
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
        ("fidelity", "gate meaningful sections, relocations, and symbols"),
        ("gate", "prove an instrumented build reproduces stock, and stamp it"),
    ),
    "pass": (
        ("replay-as1", "calibrate and probe late assembler scheduling"),
        ("diff", "compare user-supplied original and static pass boundaries"),
    ),
    "probe": (
        ("lines", "probe whether statement line assignment owns a schedule"),
        ("equiv", "the ranges over which every read of a local is one value"),
        ("deadread", "positions where a zero-footprint discarded read can be tried"),
    ),
    "sweep": (
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
    ("note", "add"): "note-add",
    ("note", "reserve"): "note-reserve",
    ("note", "list"): "note-list",
    ("note", "merge"): "note-merge",
    ("trace", "blocks"): "trace-blocks",
    ("trace", "cascade"): "trace-cascade",
    ("trace", "order"): "trace-order",
    ("trace", "summary"): "trace-summary",
    ("trace", "fifo"): "trace-fifo",
    ("trace", "globalcolor"): "trace-globalcolor",
    ("trace", "origin-probe"): "trace-origin-probe",
    ("trace", "copy-decisions"): "trace-copy-decisions",
    ("trace", "alias"): "trace-alias",
    ("trace", "scheduler"): "trace-scheduler",
    ("trace", "webs"): "trace-webs",
    ("trace", "source"): "trace-source",
    ("trace", "stack-homes"): "trace-stack-homes",
    ("instrument", "ugen"): "instrument-ugen",
    ("instrument", "uopt"): "instrument-uopt",
    ("instrument", "globalcolor"): "instrument-uopt-globalcolor",
    ("instrument", "alias"): "instrument-uopt-alias",
    ("instrument", "scheduler"): "instrument-scheduler",
    ("instrument", "fidelity"): "fidelity",
    ("instrument", "gate"): "instrument-gate",
    ("pass", "replay-as1"): "replay-as1",
    ("pass", "diff"): "pass-diff",
    ("probe", "deadread"): "probe-deadread",
    ("probe", "equiv"): "probe-equiv",
    ("probe", "lines"): "probe-lines",
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

HIDDEN_FLAT_COMMANDS = frozenset(
    {
        "campaign-export",
        "campaign-note",
        "campaign-resume",
        "campaign-status",
        "campaign-survey",
        "next-dumps",
        "note-add",
        "note-list",
        "note-merge",
        "note-reserve",
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

    if len(arguments) < 2:
        return arguments
    command = GROUP_ALIASES.get((arguments[0], arguments[1]))
    return [command, *arguments[2:]] if command else arguments


def command_map_payload() -> dict[str, Any]:
    return {
        "schema": "decomp-workbench-command-map-v1",
        "groups": {
            group: [
                {"command": command, "description": description}
                for command, description in entries
            ]
            for group, entries in COMMAND_MAP.items()
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
        "note",
        "probe",
        "sweep",
        "trace",
        "instrument",
        "pass",
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
