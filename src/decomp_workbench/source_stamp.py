"""Stamp a compile-keyed artefact with the source it measured, and check it.

A colour landscape, a force grid, a sweep's price table: each is a
measurement of *one* function body. Edit the body and the measurement
describes a function that no longer exists, while still reading exactly like
one that does. On Mickey's Speedway USA (2026-09-14..16) five consecutive
lanes measured colours against a body that had moved 227 -> 207 -> 187 words
underneath them, and every one of them was told not to re-run a landscape
measured two revisions earlier. The host fixed it with a stamp and a refusal;
this module is that stamp, generalised.

The rules:

* **A writer stamps.** Every artefact keyed to a compile records the SHA-256
  of each source it compiled, under :data:`STAMP_KEY`.
* **A reader checks, and a mismatch is a refusal by default.** A reader that
  merely warned would be read once and filtered forever after, which is the
  failure the stamp exists to end. ``allow_stale=True`` (``--allow-stale-source``
  on every reader) downgrades the refusal to a warning that is still printed
  and still carried in JSON.
* **Only a contradiction refuses.** ``unstamped`` (an artefact from before the
  stamp existed, or a host's own) and ``unknown`` (the stamped source cannot be
  read from here) are warnings: neither shows the source moved, and refusing
  them would refuse every old report and every report read from another
  checkout. ``--stamped-source PATH`` names where the source lives now.

Nothing here decides *which* sources a measurement depended on -- the writer
knows that and says so, the same boundary the staleness chain keeps (backlog
item 1). A stamp records content, not modification times: a checkout, a
rebase or a ``touch`` changes an mtime without changing what was measured.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOURCE_STAMP_SCHEMA = "decomp-workbench-source-stamp-v1"

#: The key a stamped artefact carries. One added key, never a reshaping.
STAMP_KEY = "source_stamp"

#: The key a reader's JSON output carries its verdict under.
FRESHNESS_KEY = "source_freshness"

STATUS_FRESH = "fresh"
STATUS_UNSTAMPED = "unstamped"
STATUS_UNKNOWN = "unknown"
STATUS_STALE = "stale"

#: Worst last. Only ``stale`` refuses; see the module docstring for why.
STATUSES = (STATUS_FRESH, STATUS_UNSTAMPED, STATUS_UNKNOWN, STATUS_STALE)


class StaleSourceError(ValueError):
    """A reader was handed an artefact measured against a different source."""


def file_digest(path: str | Path) -> str:
    return hashlib.sha256(Path(path).expanduser().read_bytes()).hexdigest()


def _timestamp() -> str:
    text = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return text.replace("+00:00", "Z")


@dataclass(frozen=True)
class StampedSource:
    """One source as it was when the artefact was measured."""

    path: str
    sha256: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True)
class SourceStamp:
    """Every source one compile-keyed artefact was measured against."""

    sources: tuple[StampedSource, ...]
    stamped_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "stamp_schema": SOURCE_STAMP_SCHEMA,
            "sources": [item.as_dict() for item in self.sources],
            "stamped_at": self.stamped_at,
        }


def stamp_sources(
    paths: Iterable[str | Path],
    *,
    digests: Mapping[str, str] | None = None,
) -> SourceStamp:
    """Hash each source now and return the stamp to embed in an artefact.

    ``digests`` supplies a hash the writer already computed for a path (its
    resolved spelling), so an artefact whose identity block hashed the source
    before compiling carries that same digest rather than a second read taken
    after the compile -- the one that was measured.
    """

    known = {
        str(Path(path).expanduser().resolve()): digest
        for path, digest in (digests or {}).items()
    }
    entries = []
    for raw in paths:
        resolved = str(Path(raw).expanduser().resolve())
        digest = known.get(resolved) or file_digest(resolved)
        entries.append(StampedSource(path=resolved, sha256=digest))
    if not entries:
        raise ValueError("a source stamp needs at least one source")
    return SourceStamp(sources=tuple(entries), stamped_at=_timestamp())


def _parse(raw: object) -> SourceStamp | None:
    if not isinstance(raw, Mapping):
        return None
    items = raw.get("sources")
    if not isinstance(items, list) or not items:
        return None
    entries = []
    for item in items:
        if not isinstance(item, Mapping):
            return None
        path, digest = item.get("path"), item.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str) or not digest:
            return None
        entries.append(StampedSource(path=path, sha256=digest))
    stamped_at = raw.get("stamped_at")
    return SourceStamp(
        sources=tuple(entries),
        stamped_at=stamped_at if isinstance(stamped_at, str) else "",
    )


def read_source_stamp(
    document: Mapping[str, Any],
    *,
    legacy: Sequence[tuple[str, str]] = (),
) -> SourceStamp | None:
    """Return the stamp a document carries, or None.

    ``legacy`` lets a reader name a digest its artefact recorded before the
    stamp existed -- an oracle report's ``inputs.source``, a sweep manifest's
    ``base``/``base_sha256``. Those were always digests of the measured
    source, so honouring them checks every report already on disk instead of
    waving them through as unstamped.
    """

    stamp = _parse(document.get(STAMP_KEY))
    if stamp is not None:
        return stamp
    entries = tuple(
        StampedSource(path=path, sha256=digest)
        for path, digest in legacy
        if path and digest
    )
    return SourceStamp(sources=entries) if entries else None


@dataclass(frozen=True)
class SourceCheck:
    """One stamped source against the file in front of the reader now."""

    stamped: StampedSource
    checked_path: str
    current_sha256: str | None
    reason: str = ""

    @property
    def status(self) -> str:
        if self.current_sha256 is None:
            return STATUS_UNKNOWN
        if self.current_sha256 == self.stamped.sha256:
            return STATUS_FRESH
        return STATUS_STALE

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.stamped.path,
            "checked_path": self.checked_path,
            "stamped_sha256": self.stamped.sha256,
            "current_sha256": self.current_sha256,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SourceFreshness:
    """Whether a compile-keyed artefact still describes the source."""

    artefact: str
    status: str
    checks: tuple[SourceCheck, ...] = ()
    stamp: SourceStamp | None = None
    allowed: bool = False

    @property
    def fresh(self) -> bool:
        return self.status == STATUS_FRESH

    @property
    def refused(self) -> bool:
        return self.status == STATUS_STALE and not self.allowed

    @property
    def message(self) -> str:
        if self.status == STATUS_FRESH:
            return f"{self.artefact} was measured against the current source"
        if self.status == STATUS_UNSTAMPED:
            return (
                f"{self.artefact} carries no source stamp, so whether it still "
                "describes the source cannot be checked; re-run it if the "
                "source may have changed"
            )
        if self.status == STATUS_UNKNOWN:
            unread = [item for item in self.checks if item.status == STATUS_UNKNOWN]
            where = ", ".join(item.checked_path for item in unread)
            return (
                f"{self.artefact} is stamped, but its source cannot be read "
                f"here ({where}); pass --stamped-source PATH to check it against "
                "the source as it is now"
            )
        moved = [item for item in self.checks if item.status == STATUS_STALE]
        detail = "; ".join(
            f"{item.checked_path}: measured {item.stamped.sha256[:12]}, now "
            f"{(item.current_sha256 or '')[:12]}"
            for item in moved
        )
        return (
            f"STALE: {self.artefact} was measured against a different source "
            f"({detail}). A source change voids a measurement keyed to a "
            "compile; re-run it before acting on it"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "stamp_schema": SOURCE_STAMP_SCHEMA,
            "artefact": self.artefact,
            "status": self.status,
            "fresh": self.fresh,
            "allowed_stale": self.allowed,
            "refused": self.refused,
            "stamp": self.stamp.as_dict() if self.stamp else None,
            "checks": [item.as_dict() for item in self.checks],
            "message": self.message,
        }


def check_source_stamp(
    stamp: SourceStamp | None,
    *,
    artefact: str,
    source: str | Path | None = None,
    allow_stale: bool = False,
) -> SourceFreshness:
    """Compare a stamp with the sources as they are now.

    ``source`` overrides where a single-source stamp's file is read from --
    the report was measured in another checkout, or the path was relative to
    a directory the reader is not in. A multi-source stamp cannot be
    overridden by one path without guessing which entry it means, so that is
    refused rather than guessed.
    """

    if stamp is None:
        return SourceFreshness(
            artefact=artefact, status=STATUS_UNSTAMPED, allowed=allow_stale
        )
    if source is not None and len(stamp.sources) != 1:
        raise ValueError(
            f"{artefact} is stamped with {len(stamp.sources)} sources; "
            "--stamped-source names one file and cannot say which of them it "
            "replaces"
        )
    checks = []
    for item in stamp.sources:
        location = Path(source if source is not None else item.path).expanduser()
        try:
            current: str | None = file_digest(location)
            reason = ""
        except OSError as error:
            current = None
            reason = error.strerror or type(error).__name__
        checks.append(
            SourceCheck(
                stamped=item,
                checked_path=str(location),
                current_sha256=current,
                reason=reason,
            )
        )
    statuses = {item.status for item in checks}
    status = (
        STATUS_STALE
        if STATUS_STALE in statuses
        else STATUS_UNKNOWN
        if STATUS_UNKNOWN in statuses
        else STATUS_FRESH
    )
    return SourceFreshness(
        artefact=artefact,
        status=status,
        checks=tuple(checks),
        stamp=stamp,
        allowed=allow_stale,
    )


def enforce(freshness: SourceFreshness) -> list[str]:
    """Refuse a stale artefact, or return the warning lines a reader prints.

    The returned lines are for stderr (or the terminal report) and are
    returned even when the refusal was waived: ``--allow-stale-source`` is
    permission to proceed, never permission to stop saying so.
    """

    if freshness.refused:
        raise StaleSourceError(
            freshness.message
            + ". Pass --allow-stale-source to read it anyway, stated as stale."
        )
    if freshness.status == STATUS_FRESH:
        return []
    prefix = "warning" if freshness.status != STATUS_STALE else "WARNING"
    return [f"{prefix}: {freshness.message}"]


def add_source_stamp_arguments(parser: Any, *, source: bool = True) -> None:
    """The two reader options, spelled the same on every reader."""

    parser.add_argument(
        "--allow-stale-source",
        action="store_true",
        help=(
            "read an artefact whose source stamp no longer matches the source; "
            "the mismatch is still printed and carried in JSON"
        ),
    )
    if source:
        parser.add_argument(
            "--stamped-source",
            metavar="PATH",
            help=(
                "check the artefact's source stamp against this file instead "
                "of the path it recorded (another checkout, a moved tree)"
            ),
        )


__all__ = [
    "FRESHNESS_KEY",
    "SOURCE_STAMP_SCHEMA",
    "STAMP_KEY",
    "STATUSES",
    "STATUS_FRESH",
    "STATUS_STALE",
    "STATUS_UNKNOWN",
    "STATUS_UNSTAMPED",
    "SourceCheck",
    "SourceFreshness",
    "SourceStamp",
    "StaleSourceError",
    "StampedSource",
    "add_source_stamp_arguments",
    "check_source_stamp",
    "enforce",
    "file_digest",
    "read_source_stamp",
    "stamp_sources",
]
