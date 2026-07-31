"""Options that must behave identically on every command that offers them.

Two spellings of one selector and one printed registry are cross-cutting UX
promises, not properties of a single command. They live here because ``cli``
and ``view_cli`` both register subcommands: a copy in each module is how
``view`` ended up with last-one-wins ``--symbol``/``--function`` handling while
``compare`` rejected the conflict, and how ``view`` ended up with no way to ask
what its keys mean.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

from .artifacts import DEFAULT_STREAM_LIMIT
from .schema import explain_keys_text

#: Where the parser records which spelling of the selector was used, so a
#: conflict can name the option the reader actually typed. ``main`` strips it
#: before any command sees it: it is parser bookkeeping, not an argument.
SYMBOL_OPTION_DEST = "symbol_option"

SYMBOL_HELP = "compare only this exact symbol; --function is the same option"

#: Appended to every spelling of the selector's help.
#:
#: Omitting the selector is a legitimate mode, not a mistake, but it silently
#: changes the question from "does this function match" to "does this section
#: match position for position". Readers were choosing it by default without
#: knowing they had chosen anything; the loud case now also warns at run time.
SYMBOL_OMISSION_HELP = (
    "Omitting it compares the whole section positionally - only safe when "
    "both objects hold the same single function."
)


class SymbolAction(argparse.Action):
    """Accept both vocabularies for one selector.

    Decompilation projects say "function"; GNU tooling says "symbol". Both
    spellings write the same destination. Passing both with different values
    is a mistake worth reporting instead of silently keeping the last one.
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        previous = getattr(namespace, self.dest, None)
        if previous is not None and previous != values:
            previous_option = getattr(namespace, SYMBOL_OPTION_DEST, "--symbol")
            raise argparse.ArgumentError(
                self,
                f"conflicts with {previous_option} {previous!r}; "
                "--symbol and --function are two spellings of one selector",
            )
        setattr(namespace, self.dest, values)
        setattr(namespace, SYMBOL_OPTION_DEST, option_string)


def add_symbol_argument(
    parser: argparse.ArgumentParser, *, help_text: str = SYMBOL_HELP
) -> None:
    """Add the symbol selector under both accepted spellings."""

    parser.add_argument(
        "--symbol",
        "--function",
        action=SymbolAction,
        default=None,
        metavar="NAME",
        help=f"{help_text.rstrip('. ')}. {SYMBOL_OMISSION_HELP}",
    )


class ExplainKeysAction(argparse.Action):
    """Print the metric registry and exit, like ``--version``."""

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str = argparse.SUPPRESS,
        default: str = argparse.SUPPRESS,
        help: str | None = None,
    ) -> None:
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help,
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        print(explain_keys_text())
        parser.exit()


def add_explain_keys_argument(parser: argparse.ArgumentParser) -> None:
    """Offer the metric registry wherever reported keys are printed."""

    parser.add_argument(
        "--explain-keys",
        action=ExplainKeysAction,
        help="print the metric registry (label, JSON key, meaning) and exit",
    )


def add_census_argument(parser: argparse.ArgumentParser) -> None:
    """Offer the report predicate wherever a report is produced.

    One spelling and one exit-code contract on every command that reports
    metrics: a filter whose meaning depended on which command ran it would be
    worse than the ad-hoc regular expressions it replaces.
    """

    parser.add_argument(
        "--census",
        action="append",
        default=[],
        metavar="KEY=VALUE[,KEY=VALUE...]",
        help=(
            "assert reported values; exit 3 if any predicate fails "
            "(2 for an unknown key), and print one PASS/FAIL line each. "
            "Repeatable"
        ),
    )


def add_candidate_listing_argument(parser: argparse.ArgumentParser) -> None:
    """Offer the candidate's ugen assembly listing as statement-line evidence.

    Opt-in, because most readers do not keep the intermediate. The help text
    says where the file comes from rather than naming the file type and
    stopping: a diagnostic input nobody knows how to produce is not an option,
    it is a wall.
    """

    parser.add_argument(
        "--candidate-listing",
        metavar="PATH",
        help=(
            "the assembly listing ugen wrote for the candidate, used to report "
            "whether schedule-divergent sites sit at .loc statement-line "
            "boundaries; the IDO driver keeps it beside the object when you "
            "pass `cc -K`, and `ugen -l` writes it directly"
        ),
    )


def add_process_output_arguments(parser: argparse.ArgumentParser) -> None:
    """Add shared bounded-stream and explicit full-artifact controls."""

    parser.add_argument(
        "--stream-limit",
        type=int,
        default=DEFAULT_STREAM_LIMIT,
        metavar="BYTES",
        help=(
            "maximum retained bytes per compiler stream "
            f"(default: {DEFAULT_STREAM_LIMIT})"
        ),
    )
    parser.add_argument(
        "--artifact-dir",
        help="retain complete compiler stdout/stderr here",
    )
