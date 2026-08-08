"""One honest number for "how far is this candidate from the target".

The workbench reports three counts for one comparison, and they disagree:

``words``
    Positional word differences after masking linker-controlled relocation
    fields. It is the function-level matching oracle -- ``words=0`` is the
    match -- and it is the only one of the three that means the same thing
    for two different candidates.
``raw``
    Every differing word, including the ones whose only differing bits are
    relocation-controlled. On a pair whose literal pools are spelled
    differently it can never reach zero, so it *inflates*.
``aligned_total``
    LCS-aligned rows a source change would have to move. The right question
    about one candidate and the wrong question about two: once the aligner
    inserts gaps, a differently scheduled object realigns against a different
    subsequence and its row count can fall below a strictly better
    candidate's, so it *under-reports*.

None of that is wrong, and all of it was already printed. What was missing was
a default. Every stage of one campaign had to be told which number to trust,
and one of them spent 257 builds building a lever table ordered by the wrong
one. So this module picks: the headline is ``words``, always, and the other
two appear beneath it labelled with what they are for. When they disagree,
the disagreement is stated as a numbered fact with its cause, rather than left
for the reader to notice.

The rule this encodes, in one sentence: *rank on positional words; read
aligned rows to understand one candidate; never rank on raw.*
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .model import Comparison

#: What the headline number is, in the words a newcomer needs. Printed with
#: the score itself rather than kept in documentation, because the failure
#: this module fixes was a reader who had the number and not its meaning.
HEADLINE_GLOSS = (
    "positional word differences after masking linker-controlled relocation fields"
)

#: Role each metric plays, rendered beside its value.
ROLE_SCORE = "the score"
ROLE_ONE_CANDIDATE = "one candidate only"
ROLE_NEVER = "never the score"


@dataclass(frozen=True)
class MetricRow:
    """One metric in the breakdown beneath the headline."""

    key: str
    value: int
    role: str
    gloss: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "role": self.role,
            "gloss": self.gloss,
        }


@dataclass(frozen=True)
class Headline:
    """The headline score for one comparison, with its breakdown and cautions."""

    target: str
    candidate: str
    symbol: str | None
    words: int
    matched: bool
    target_instructions: int
    candidate_instructions: int
    metrics: tuple[MetricRow, ...]
    disagreements: tuple[str, ...]
    verdict: str

    @property
    def instruction_delta(self) -> int:
        return self.candidate_instructions - self.target_instructions

    def as_dict(self) -> dict[str, Any]:
        return {
            "headline_metric": "words",
            "headline_value": self.words,
            "headline_gloss": HEADLINE_GLOSS,
            "matched": self.matched,
            "target": self.target,
            "candidate": self.candidate,
            "symbol": self.symbol,
            "target_instructions": self.target_instructions,
            "candidate_instructions": self.candidate_instructions,
            "instruction_delta": self.instruction_delta,
            "metrics": [row.as_dict() for row in self.metrics],
            "metric_disagreements": list(self.disagreements),
            "verdict": self.verdict,
        }


def metric_rows(item: Comparison) -> tuple[MetricRow, ...]:
    """Return the three counts, ordered by how much they can be trusted."""

    return (
        MetricRow(
            key="words",
            value=item.word_mismatches,
            role=ROLE_SCORE,
            gloss=HEADLINE_GLOSS + "; words=0 is the match",
        ),
        MetricRow(
            key="aligned_total",
            value=item.aligned_total,
            role=ROLE_ONE_CANDIDATE,
            gloss=(
                "LCS-aligned rows a source change controls; it answers how "
                "much of this candidate would have to move, not which of two "
                "candidates is closer"
            ),
        ),
        MetricRow(
            key="raw",
            value=item.raw_word_mismatches,
            role=ROLE_NEVER,
            gloss=(
                "every differing word including relocation-controlled ones, "
                "which no source change moves"
            ),
        ),
    )


def disagreement_notes(item: Comparison) -> tuple[str, ...]:
    """State every way the three counts disagree, each with its cause.

    Silence here is a claim: it means the three numbers agree and any of them
    would have ranked the candidate the same way. That is worth being able to
    rely on, so each note is derived from a measured field rather than from a
    threshold.
    """

    notes: list[str] = []
    controlled = item.raw_difference_breakdown.get("relocation_controlled", 0)
    if item.raw_word_mismatches > item.word_mismatches:
        cause = (
            f"{controlled} relocation-controlled word(s)"
            if controlled
            else "words whose only differing bits are linker-filled"
        )
        notes.append(
            f"raw={item.raw_word_mismatches} exceeds words={item.word_mismatches} "
            f"by {item.raw_word_mismatches - item.word_mismatches}: {cause}. "
            "The linker owns those bits, so raw cannot reach zero on this "
            "pair and words=0 is the honest gate."
        )
    if item.aligned_gaps:
        notes.append(
            f"aligned_total={item.aligned_total} counts rows the aligner "
            f"paired, and it inserted {item.aligned_gaps} gap(s) "
            f"({item.aligned_insertions} insertion(s), "
            f"{item.aligned_deletions} deletion(s)). Those are positions the "
            "two objects do not share, so this aligned_total counts different "
            "things from another candidate's and must not be ranked against it."
        )
    if item.aligned_total < item.word_mismatches:
        notes.append(
            f"aligned_total={item.aligned_total} is "
            f"{item.word_mismatches - item.aligned_total} below "
            f"words={item.word_mismatches}: the aligner absorbed shifted rows "
            "into its gaps, so aligned_total under-reports the work left."
        )
    elif item.aligned_total > item.word_mismatches:
        notes.append(
            f"aligned_total={item.aligned_total} is "
            f"{item.aligned_total - item.word_mismatches} above "
            f"words={item.word_mismatches}: rows differ at positions where "
            "the masked relocation fields agree, so they cost an aligned row "
            "and no word."
        )
    delta = item.candidate_instructions - item.target_instructions
    if delta:
        direction = "more" if delta > 0 else "fewer"
        notes.append(
            f"the candidate emits {abs(delta)} {direction} instruction(s) than "
            "the target. Instruction counts must agree before any of these "
            "numbers is a measure of allocation or scheduling: every word "
            "after the first count difference is shifted, not wrong."
        )
    return tuple(notes)


def build_headline(item: Comparison) -> Headline:
    """Build the headline report for one comparison."""

    return Headline(
        target=item.target,
        candidate=item.candidate,
        symbol=item.symbol,
        words=item.word_mismatches,
        matched=item.exact,
        target_instructions=item.target_instructions,
        candidate_instructions=item.candidate_instructions,
        metrics=metric_rows(item),
        disagreements=disagreement_notes(item),
        verdict=item.verdict,
    )


def headline_line(report: Headline) -> str:
    """Render the single line a reader is meant to quote."""

    if report.matched:
        return "score: 0 words differ — MATCH"
    plural = "" if report.words == 1 else "s"
    return f"score: {report.words} word{plural} differ (0 = match)"


def render_headline(report: Headline, *, verbose: bool = False) -> list[str]:
    """Render the headline, the breakdown, and any disagreement notes.

    Progressive disclosure, in this order: the number, then what the other
    numbers are for, then why they differ. A reader who stops after the first
    line has the right answer; a reader who stops after the breakdown knows
    which number to quote next time.
    """

    lines = [headline_line(report)]
    scope = f" [{report.symbol}]" if report.symbol else ""
    lines.append(f"target:    {report.target}{scope}")
    lines.append(f"candidate: {report.candidate}")
    lines.append("")
    width = max(len(row.key) for row in report.metrics)
    value_width = max(len(str(row.value)) for row in report.metrics)
    for row in report.metrics:
        marker = "<-" if row.role == ROLE_SCORE else "  "
        lines.append(
            f"  {row.key.ljust(width)}  {str(row.value).rjust(value_width)}  "
            f"{marker} {row.role}"
        )
        if verbose:
            lines.append(f"  {' ' * width}  {' ' * value_width}     {row.gloss}")
    if report.disagreements:
        lines.append("")
        lines.append("these numbers disagree, and here is why:")
        for note in report.disagreements:
            lines.extend(_wrap_note(note))
    else:
        lines.append("")
        lines.append(
            "the three counts agree; any of them would rank this candidate the same way"
        )
    lines.append("")
    lines.append(f"verdict: {report.verdict}")
    return lines


def _wrap_note(note: str, *, width: int = 74) -> list[str]:
    """Wrap one disagreement note under a bullet, keeping the hanging indent."""

    words = note.split()
    lines: list[str] = []
    current = "  - "
    for word in words:
        if len(current) + len(word) + 1 > width and current.strip(" -"):
            lines.append(current.rstrip())
            current = "    "
        current += word + " "
    if current.strip():
        lines.append(current.rstrip())
    return lines
