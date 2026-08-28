"""Stamp a closeness ranking with the tree it was measured against.

A ranking is a *measurement*, and it decays: every function that matches,
every source edit that moves a word, changes the ordering it encodes. One
campaign's ranking snapshot was still being read as an ownership ledger
hours after two of the functions in it had already matched, and the sweep
it ordered spent its first window on rows that no longer existed.

The fix is not a smarter ranking, it is a stamp. A ranking that records
the tree hash it was computed against can be *checked* against the tree in
front of it, so a consumer can say "this ordering is a measurement of a
different tree" instead of quietly trusting it. Nothing here recomputes a
ranking: producing one needs the project's build, and this module needs
only the project's git.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile  # nosec B404 - argv-only, never through a shell
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RANKING_STAMP_SCHEMA = "decomp-workbench-ranking-stamp-v1"

#: The key a stamped ranking carries. A ranking file is otherwise the
#: producer's own document, so the stamp is one added key and never a
#: reshaping of the rows.
STAMP_KEY = "stamp"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(moment: datetime) -> str:
    text = moment.astimezone(timezone.utc).isoformat(timespec="seconds")
    return text.replace("+00:00", "Z")


def git_head(root: Path | str, *, runner: Runner = subprocess.run) -> str | None:
    """Return the project's current commit, or None when it cannot be read.

    "Cannot be read" is a real state, not an error: a project may be
    unpacked from an archive, or the ranking may live beside a tree that is
    not a git checkout at all. The callers turn it into "freshness unknown",
    which is a weaker claim than stale but a stronger one than fresh.
    """

    try:
        completed = runner(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    head = (completed.stdout or "").strip()
    return head or None


@dataclass(frozen=True)
class RankingStamp:
    """What tree a ranking was measured against, and when."""

    tree_hash: str
    generated_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": RANKING_STAMP_SCHEMA,
            "tree_hash": self.tree_hash,
            "generated_at": self.generated_at,
        }


@dataclass(frozen=True)
class StampResult:
    """The stamp a ranking now carries, and whether the file changed."""

    path: Path
    stamp: RankingStamp
    changed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": RANKING_STAMP_SCHEMA,
            "path": str(self.path),
            "tree_hash": self.stamp.tree_hash,
            "generated_at": self.stamp.generated_at,
            "changed": self.changed,
        }


def _document(path: Path) -> dict[str, Any]:
    """Read a ranking as a mutable document, whatever spelling it uses.

    A ranking is a list of rows or an object holding them under
    ``functions``; both spellings exist in the wild because both are what a
    producer happened to emit. The list form is wrapped rather than
    rejected, because refusing to stamp the shape a project already has
    would just mean nobody stamps anything.
    """

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"functions": payload}
    if isinstance(payload, dict):
        return dict(payload)
    raise ValueError(f"{path}: a ranking must be a JSON list or object")


def read_stamp(path: Path | str) -> RankingStamp | None:
    """Return the stamp a ranking carries, or None when it carries none."""

    source = Path(path).expanduser()
    if not source.is_file():
        return None
    try:
        document = _document(source)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    raw = document.get(STAMP_KEY)
    if not isinstance(raw, dict):
        return None
    tree_hash = raw.get("tree_hash")
    generated_at = raw.get("generated_at")
    if not isinstance(tree_hash, str) or not tree_hash.strip():
        return None
    return RankingStamp(
        tree_hash=tree_hash,
        generated_at=generated_at if isinstance(generated_at, str) else "",
    )


def _write_atomic(path: Path, text: str) -> None:
    """Replace one file's contents, or leave the old contents in place."""

    directory = path.parent
    handle, temporary = tempfile.mkstemp(dir=str(directory), suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def stamp_ranking(
    path: Path | str,
    tree_hash: str,
    *,
    now: Callable[[], datetime] = _utc_now,
) -> StampResult:
    """Record the tree a ranking was measured against, idempotently.

    Re-stamping an unchanged ranking *keeps* its existing ``generated_at``
    and leaves the file alone: the timestamp records when the measurement
    was taken, and refreshing it on every sweep would turn the one field
    that says how old this ordering is into a field that always says "just
    now".

    The rewrite is atomic. This is derived state written over an input that
    costs a whole build to regenerate, so the file on disk is either the
    ranking it was or the ranking plus its stamp, never a truncated one.
    A ranking in the bare-list spelling is wrapped under ``functions``:
    JSON has nowhere to hang a key on a list, and the wrapping is the
    spelling every reader here already accepts.
    """

    target = Path(path).expanduser()
    if not tree_hash.strip():
        raise ValueError("a ranking stamp needs a non-empty tree hash")
    document = _document(target)
    existing = read_stamp(target)
    if existing is not None and existing.tree_hash == tree_hash:
        return StampResult(path=target, stamp=existing, changed=False)
    stamp = RankingStamp(tree_hash=tree_hash, generated_at=_timestamp(now()))
    document[STAMP_KEY] = stamp.as_dict()
    _write_atomic(target, json.dumps(document, indent=2) + "\n")
    return StampResult(path=target, stamp=stamp, changed=True)


#: Freshness states, worst last. `fresh` is the only one a `--require-fresh`
#: consumer accepts, because every other one means the ordering in front of
#: the operator has not been shown to describe the tree in front of them.
STATUSES = ("fresh", "unstamped", "unknown", "stale", "missing")


@dataclass(frozen=True)
class Freshness:
    """Whether a ranking describes the tree the caller is standing in."""

    path: Path
    status: str
    stamp: RankingStamp | None = None
    current_hash: str | None = None

    @property
    def fresh(self) -> bool:
        return self.status == "fresh"

    @property
    def message(self) -> str:
        stamped = self.stamp.tree_hash[:12] if self.stamp else "(none)"
        head = self.current_hash[:12] if self.current_hash else "(unknown)"
        if self.status == "fresh":
            return f"ranking {self.path} is stamped for the current tree {head}"
        if self.status == "missing":
            return f"ranking {self.path} does not exist"
        if self.status == "unstamped":
            return (
                f"ranking {self.path} carries no tree stamp, so its drift "
                "from this tree cannot be measured. Stamp it where it is "
                "generated: `decomp-workbench ranking stamp <path>`"
            )
        if self.status == "unknown":
            return (
                f"ranking {self.path} is stamped for tree {stamped}, but this "
                "project's HEAD could not be read, so the two cannot be "
                "compared"
            )
        return (
            f"ranking {self.path} was measured against tree {stamped}, but HEAD "
            f"is {head}. A closeness ranking decays within hours -- a function "
            "that matched is still in it, and the ordering it encodes is a "
            "measurement of a different tree. Regenerate it before trusting "
            "the order"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": RANKING_STAMP_SCHEMA,
            "path": str(self.path),
            "status": self.status,
            "fresh": self.fresh,
            "tree_hash": self.stamp.tree_hash if self.stamp else None,
            "generated_at": self.stamp.generated_at if self.stamp else None,
            "current_hash": self.current_hash,
            "message": self.message,
        }


def check_ranking_fresh(path: Path | str, current_hash: str | None) -> Freshness:
    """Compare a ranking's stamp with the tree hash the caller is on."""

    target = Path(path).expanduser()
    if not target.is_file():
        return Freshness(path=target, status="missing", current_hash=current_hash)
    stamp = read_stamp(target)
    if stamp is None:
        return Freshness(path=target, status="unstamped", current_hash=current_hash)
    if current_hash is None:
        return Freshness(path=target, status="unknown", stamp=stamp, current_hash=None)
    status = "fresh" if stamp.tree_hash == current_hash else "stale"
    return Freshness(path=target, status=status, stamp=stamp, current_hash=current_hash)


def render_freshness(freshness: Freshness) -> list[str]:
    """Render one freshness verdict for a human reading a terminal."""

    lines = [
        f"ranking {freshness.path}",
        f"  status          {freshness.status}",
        f"  stamped tree    {freshness.stamp.tree_hash if freshness.stamp else '-'}",
        f"  generated at    {freshness.stamp.generated_at if freshness.stamp else '-'}",
        f"  current HEAD    {freshness.current_hash or '(unknown)'}",
    ]
    if not freshness.fresh:
        lines.append(f"  warning         {freshness.message}")
    return lines


def freshness_warning(freshness: Freshness) -> str | None:
    """The loud line a consumer prints before running on a stale ranking.

    Only a ranking that *contradicts* the tree -- or one whose stamp cannot
    be compared to it -- earns the loud line. A ranking that was never
    stamped is the state every project starts in, and shouting on every run
    about the state everyone is in is how a warning gets filtered out
    before the one that matters arrives; `freshness_note` carries that one
    quietly instead.
    """

    if freshness.status in ("fresh", "missing", "unstamped"):
        return None
    return f"WARNING: {freshness.message}"


def freshness_note(freshness: Freshness) -> str | None:
    """The quiet line for a ranking nobody has stamped yet."""

    if freshness.status != "unstamped":
        return None
    return f"note: {freshness.message}"


__all__ = [
    "RANKING_STAMP_SCHEMA",
    "STAMP_KEY",
    "STATUSES",
    "Freshness",
    "RankingStamp",
    "StampResult",
    "check_ranking_fresh",
    "freshness_note",
    "freshness_warning",
    "git_head",
    "read_stamp",
    "render_freshness",
    "stamp_ranking",
]
