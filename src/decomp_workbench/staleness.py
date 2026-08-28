"""Whether the artifact in front of you was built from the inputs beside it.

A comparison answers "are these two objects the same". It does not answer
"is this object the thing my last edit produced", and the two questions look
identical on screen: a ROM-level check against a `build/` image that was never
rebuilt reports **0 differing words** and reads as a match. That happened on a
real project. The false match survived until a fresh assembly of the target
disagreed, and the intervening verify cycles were spent proving something that
was never true.

Nothing here recompiles or rebuilds. It reads modification times -- and, when
asked, content hashes -- of artifacts named in build order, and reports the one
fact that is cheap to check and expensive to miss: a derived artifact that is
older than something it is derived from. The chain is the caller's to declare,
because only the project knows it: source -> object -> ELF -> ROM on one
project, a single object built from three fragments on another.

Two deliberate limits:

* mtime is evidence, not proof. A build that preserves timestamps, a restored
  archive, or a clock that moved can all produce a fresh artifact that looks
  stale, and a `touch` produces a stale one that looks fresh. That is why the
  escape hatch exists and why the hashes are recorded: a host that keeps a
  report can compare the *content* of an input across two runs and know
  whether the rebuild it is about to trust had anything to rebuild from.
* Equal timestamps are not stale. Filesystem timestamp granularity is coarse
  enough that a fast build genuinely produces an object in the same second as
  the source, and refusing on that would make the guard the thing operators
  routinely pass `--allow-stale` to get past.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STALENESS_SCHEMA = "decomp-workbench-staleness-v1"

#: Read size for content hashing. Large enough that hashing a ROM is one
#: bounded pass, small enough that it is never the memory an agent notices.
_CHUNK = 1 << 20

#: How much older a derived artifact may be before it is called stale.
#:
#: One second, not zero: `make` can genuinely write an object in the same
#: filesystem timestamp tick as the source it read, and a guard that fires on
#: the normal case is a guard that gets disabled.
DEFAULT_TOLERANCE_SECONDS = 1.0

#: Report states, best first. Only `fresh` is a positive claim.
STATUSES = ("fresh", "unknown", "missing", "stale")


def _timestamp(seconds: float) -> str:
    moment = datetime.fromtimestamp(seconds, tz=timezone.utc)
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def file_sha256(path: Path) -> str | None:
    """Return the content hash of one file, or None when it cannot be read."""

    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(_CHUNK), b""):
                digest.update(block)
    except OSError:
        return None
    return digest.hexdigest()


@dataclass(frozen=True)
class Artifact:
    """One named file in a build chain, and when it was last written."""

    path: Path
    label: str
    exists: bool
    mtime: float | None = None
    size: int | None = None
    sha256: str | None = None

    @property
    def built_at(self) -> str:
        """When this artifact was last written, in words a human can read."""

        return "(missing)" if self.mtime is None else _timestamp(self.mtime)

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "path": str(self.path),
            "exists": self.exists,
            "mtime": self.mtime,
            "built_at": self.built_at,
            "size": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class Violation:
    """One derived artifact that predates an input it is derived from."""

    input: Artifact
    derived: Artifact
    seconds: float

    @property
    def message(self) -> str:
        return (
            f"{self.derived.label} {self.derived.path} was built "
            f"{_age(self.seconds)} BEFORE {self.input.label} "
            f"{self.input.path} was last written "
            f"({self.derived.built_at} < {self.input.built_at})"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "input": self.input.label,
            "input_path": str(self.input.path),
            "derived": self.derived.label,
            "derived_path": str(self.derived.path),
            "seconds": round(self.seconds, 3),
            "message": self.message,
        }


def _age(seconds: float) -> str:
    """Render a duration the way an operator reads one: coarse and honest."""

    if seconds < 90:
        return f"{seconds:.0f}s"
    if seconds < 5400:
        return f"{seconds / 60:.0f}m"
    if seconds < 172800:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


@dataclass(frozen=True)
class StalenessReport:
    """What was compared, when each part of it was built, and whether that holds."""

    artifacts: tuple[Artifact, ...]
    violations: tuple[Violation, ...]
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS

    @property
    def missing(self) -> tuple[Artifact, ...]:
        return tuple(item for item in self.artifacts if not item.exists)

    @property
    def status(self) -> str:
        if self.violations:
            return "stale"
        if self.missing:
            return "missing"
        if len(self.artifacts) < 2:
            # One artifact has nothing to be older than. Saying `fresh` here
            # would turn "nobody declared a chain" into a positive claim that
            # the build is current, which is exactly the claim that was wrong.
            return "unknown"
        return "fresh"

    @property
    def stale(self) -> bool:
        return bool(self.violations)

    @property
    def fresh(self) -> bool:
        return self.status == "fresh"

    @property
    def message(self) -> str:
        if self.violations:
            return (
                f"{self.violations[0].message}. A comparison against a build "
                "older than its inputs measures the previous edit: rebuild, "
                "or pass --allow-stale to say you meant this one"
            )
        if self.missing:
            names = ", ".join(str(item.path) for item in self.missing)
            return (
                f"freshness unproven: {names} does not exist, so the build "
                "chain could not be checked"
            )
        if len(self.artifacts) < 2:
            return (
                "freshness unproven: name the inputs this artifact was built "
                "from (--built-from) to have it checked"
            )
        return "every artifact is at least as new as the inputs before it"

    def provenance_lines(self) -> list[str]:
        """State plainly what was read and when each part of it was built."""

        if not self.artifacts:
            return []
        width = max(len(item.label) for item in self.artifacts)
        return [
            f"{item.label.ljust(width)}  {item.path}  built {item.built_at}"
            for item in self.artifacts
        ]

    def lines(self) -> list[str]:
        """The whole report, for a terminal."""

        rendered = ["build freshness: " + self.status, *self.provenance_lines()]
        rendered.extend(f"STALE: {item.message}" for item in self.violations)
        if not self.violations and self.status != "fresh":
            rendered.append(f"note: {self.message}")
        return rendered

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": STALENESS_SCHEMA,
            "status": self.status,
            "stale": self.stale,
            "fresh": self.fresh,
            "tolerance_seconds": self.tolerance_seconds,
            "artifacts": [item.as_dict() for item in self.artifacts],
            "violations": [item.as_dict() for item in self.violations],
            "message": self.message,
        }


def _label_for(index: int, total: int, given: str | None) -> str:
    if given:
        return given
    if index == total - 1:
        return "built"
    return f"input{index + 1}" if total > 2 else "input"


def artifact_for(path: str | Path, *, label: str, hashes: bool = False) -> Artifact:
    """Stat one artifact, hashing it only when the caller asked."""

    resolved = Path(path).expanduser()
    try:
        stat = resolved.stat()
    except OSError:
        return Artifact(path=resolved, label=label, exists=False)
    return Artifact(
        path=resolved,
        label=label,
        exists=True,
        mtime=stat.st_mtime,
        size=stat.st_size,
        sha256=file_sha256(resolved) if hashes else None,
    )


def staleness_report(
    *paths: str | Path,
    labels: Sequence[str] | None = None,
    hashes: bool = False,
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS,
) -> StalenessReport:
    """Check a build chain named in build order, earliest input first.

    ``staleness_report("track.c", "track.o", "game.elf", "game.z64")`` says
    what each artifact is, when it was built, and whether any of them predates
    something it was built from. Every earlier path is treated as an input to
    every later one, not only to the next one: a ROM relinked after an object
    was rebuilt but before the *source* was recompiled is stale against the
    source even though it is newer than the object it holds.

    `labels` renames the rows for the report; by default the last path is
    ``built`` and the rest are inputs. `hashes` records a SHA-256 per artifact
    so a host can persist the report and later tell a rebuild that changed
    something from a rebuild that changed nothing.
    """

    if labels is not None and len(labels) != len(paths):
        raise ValueError(
            f"staleness_report got {len(paths)} path(s) and "
            f"{len(labels)} label(s); they must correspond"
        )
    total = len(paths)
    artifacts = tuple(
        artifact_for(
            path,
            label=_label_for(index, total, labels[index] if labels else None),
            hashes=hashes,
        )
        for index, path in enumerate(paths)
    )
    violations: list[Violation] = []
    for index, derived in enumerate(artifacts):
        if derived.mtime is None:
            continue
        for earlier in artifacts[:index]:
            if earlier.mtime is None:
                continue
            gap = earlier.mtime - derived.mtime
            if gap > tolerance_seconds:
                violations.append(
                    Violation(input=earlier, derived=derived, seconds=gap)
                )
    return StalenessReport(
        artifacts=artifacts,
        violations=tuple(violations),
        tolerance_seconds=tolerance_seconds,
    )


class StaleBuildError(ValueError):
    """A comparison was asked to trust an artifact older than its inputs."""


def enforce_freshness(
    report: StalenessReport,
    *,
    allow_stale: bool,
) -> list[str]:
    """Refuse a stale comparison, or return the warning that replaces the refusal.

    The default is a refusal because the failure this guards is a *false
    positive*: a stale comparison does not look wrong, it looks like a match,
    and the operator's next move is to spend verify cycles on it. `--allow-stale`
    exists for the cases where the operator genuinely knows better -- a
    deliberately retained reference build, a timestamp-preserving checkout --
    and it never suppresses the report, only the refusal.
    """

    if not report.stale:
        return []
    if not allow_stale:
        raise StaleBuildError(report.message)
    return [f"warning: {item.message}" for item in report.violations] + [
        "warning: --allow-stale was given, so this result is about a build "
        "that predates its inputs"
    ]


def chain_report(
    derived: Iterable[str | Path],
    inputs: Sequence[str | Path],
    *,
    labels: Sequence[str] | None = None,
    hashes: bool = False,
) -> StalenessReport:
    """Check several derived artifacts against one shared set of inputs.

    The comparison commands need exactly this shape: two objects that must
    both be newer than the sources named with `--built-from`, with no claim
    that either object is derived from the other.
    """

    derived_paths = list(derived)
    ordered = [*inputs, *derived_paths]
    if labels is not None and len(labels) != len(ordered):
        raise ValueError("chain_report labels must match inputs plus derived")
    report = staleness_report(*ordered, labels=labels, hashes=hashes)
    # Drop any violation *between* two derived artifacts: they are siblings,
    # and a candidate older than the target says nothing at all.
    sibling_labels = {artifact.label for artifact in report.artifacts[len(inputs) :]}
    kept = tuple(
        item for item in report.violations if item.input.label not in sibling_labels
    )
    return StalenessReport(
        artifacts=report.artifacts,
        violations=kept,
        tolerance_seconds=report.tolerance_seconds,
    )


__all__ = [
    "DEFAULT_TOLERANCE_SECONDS",
    "STALENESS_SCHEMA",
    "STATUSES",
    "Artifact",
    "StaleBuildError",
    "StalenessReport",
    "Violation",
    "artifact_for",
    "chain_report",
    "enforce_freshness",
    "file_sha256",
    "staleness_report",
]
