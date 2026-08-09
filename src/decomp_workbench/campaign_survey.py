"""Reading a campaign directory that never had a manifest.

`campaign status` answers a good question well, and it is a different question:
its unit is a compiled candidate in a manifest `campaign run` itself wrote. A
late-stage campaign does not look like that. Its artifacts are files a human
promoted by hand, its floor came from a sweep in another directory, and its
residue is a `compare --by-region` run against a source path nothing records.
Asked for a one-screen "where are we", the honest options were to invent a
second notion of "campaign" -- a registry of tracked artifacts with provenance
-- or to leave the question unanswered. Both were wrong, and the second one won
by default for a while.

**The decision this module makes: no registry.** Nothing is persisted, so
nothing can be stale, and the two questions the design note left open stop
being questions:

* *Is an artifact's identity its object hash or its source path?* Neither is
  fixed here. A survey is a reading of the directory as it is right now: a path,
  and its content hash taken at read time. There is no stored identity to be
  wrong about.
* *Is "not yet attributed" a property of the residue or of the campaign's own
  records?* Of the residue, necessarily, because there are no records. The
  survey names the newest source and object it found and prints the command
  that measures them; it does not remember an answer.

The third open question -- "a second campaign is what would settle the schema"
-- is closed by there being no schema to fix. This reads only documents the
workbench already defines: findings logs and their sidecars, sweep manifests,
instrument-gate stamps, and `campaign run`'s own manifests. Everything else is
counted, not interpreted.

And it never guesses which artifact is "the base". Guessing is what a registry
would have institutionalised.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["SURVEY_SCHEMA", "CampaignSurveyError", "survey_lines", "survey_campaign"]

SURVEY_SCHEMA = "decomp-workbench-campaign-survey-v1"

#: Files walked before the survey stops and says so. A campaign directory can
#: hold tens of thousands of objects; a reader wants the shape in a second, and
#: a cap that is not printed is the defect this whole family exists to avoid.
DEFAULT_BUDGET = 40000

_SOURCE_SUFFIXES = frozenset({".c", ".h", ".i", ".s"})
_OBJECT_SUFFIXES = frozenset({".o", ".obj", ".elf"})
_DUMP_SUFFIXES = frozenset({".objdump", ".dis", ".dis2", ".dump", ".txt"})
_NOTE_SUFFIXES = frozenset({".md"})

#: Directories a survey never descends into: version control, caches, and the
#: workbench's own state (which `campaign status` reads properly).
_SKIP = frozenset({".git", "__pycache__", ".mypy_cache", ".ruff_cache", ".venv"})


class CampaignSurveyError(ValueError):
    """The campaign directory could not be read."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stamp(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


@dataclass
class Stage:
    """One stage directory, counted rather than interpreted."""

    name: str
    files: int = 0
    sources: int = 0
    objects: int = 0
    dumps: int = 0
    notes: list[str] = field(default_factory=list)
    modified: float = 0.0
    newest_source: Path | None = None
    newest_object: Path | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "files": self.files,
            "sources": self.sources,
            "objects": self.objects,
            "dumps": self.dumps,
            "notes": sorted(self.notes),
            "modified": _stamp(self.modified) if self.modified else None,
            "newest_source": str(self.newest_source) if self.newest_source else None,
            "newest_object": str(self.newest_object) if self.newest_object else None,
        }


def _walk(root: Path, budget: int) -> tuple[list[Stage], Stage, int, bool]:
    """Count every stage directory's files, within a stated budget."""

    stages: dict[str, Stage] = {}
    top = Stage(name=".")
    seen = 0
    capped = False
    for path in _iterate(root):
        seen += 1
        if seen > budget:
            capped = True
            break
        relative = path.relative_to(root)
        key = relative.parts[0] if len(relative.parts) > 1 else "."
        stage = top if key == "." else stages.setdefault(key, Stage(name=key))
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        stage.files += 1
        stage.modified = max(stage.modified, modified)
        suffix = path.suffix.lower()
        if suffix in _SOURCE_SUFFIXES:
            stage.sources += 1
            if stage.newest_source is None or modified >= _mtime(stage.newest_source):
                stage.newest_source = path
        elif suffix in _OBJECT_SUFFIXES:
            stage.objects += 1
            if stage.newest_object is None or modified >= _mtime(stage.newest_object):
                stage.newest_object = path
        elif suffix in _DUMP_SUFFIXES:
            stage.dumps += 1
        elif suffix in _NOTE_SUFFIXES:
            stage.notes.append(relative.name)
    return sorted(stages.values(), key=lambda item: -item.modified), top, seen, capped


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _iterate(root: Path):
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.name in _SKIP:
                continue
            if entry.is_dir() and not entry.is_symlink():
                stack.append(entry)
                continue
            if entry.is_file():
                yield entry


def _findings_logs(root: Path, budget: int) -> list[dict[str, Any]]:
    """Every shared findings log, read through the note mechanism that owns it."""

    from .notes import NOTES_SUFFIX, NoteError, merged_view

    found: list[dict[str, Any]] = []
    for sidecar in sorted(root.rglob(f"*{NOTES_SUFFIX}"))[:budget]:
        if not sidecar.is_dir():
            continue
        log = sidecar.with_name(sidecar.name[: -len(NOTES_SUFFIX)])
        try:
            view = merged_view(log)
        except NoteError:
            continue
        found.append(
            {
                "log": str(log),
                "entries": len(view.entries),
                "pending": len(view.pending),
                "merged": len(view.merged),
                "duplicate_ids": list(view.duplicate_ids),
            }
        )
    return found


def _documents(root: Path, schema: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    """Every JSON document under `root` carrying `schema`, reduced to `fields`."""

    import json

    found: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        try:
            # A campaign directory holds ledgers and exports too. A schema
            # check is cheap; parsing a hundred-megabyte ledger to find out it
            # is not a sweep manifest is not.
            if path.stat().st_size > 4 << 20:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict) or payload.get("schema") != schema:
            continue
        reduced: dict[str, Any] = {"path": str(path)}
        for name in fields:
            reduced[name] = payload.get(name)
        found.append(reduced)
    return found


def survey_campaign(
    root: str | Path,
    *,
    budget: int = DEFAULT_BUDGET,
    base: str | Path | None = None,
) -> dict[str, Any]:
    """Read one campaign directory and return what is there, not what it means."""

    from .sweep import SWEEP_SCHEMA

    location = Path(root)
    if not location.is_dir():
        raise CampaignSurveyError(
            f"{location} is not a directory. `campaign survey` reads a campaign "
            "working directory -- the one holding the stage directories. For a "
            "manifest `campaign run` wrote, use `campaign status`."
        )
    stages, top, seen, capped = _walk(location, budget)
    sweeps = _documents(
        location, SWEEP_SCHEMA, ("generator", "base", "variant_count", "coverage")
    )
    gates = _documents(
        location,
        "decomp-workbench-instrument-gate-v1",
        ("profile", "pass", "recorded"),
    )
    manifests = [
        str(path)
        for path in sorted(location.rglob("manifest.json"))
        if "campaigns" in path.parts
    ]
    pinned: dict[str, Any] | None = None
    if base is not None:
        pinned_path = Path(base)
        if not pinned_path.is_file():
            raise CampaignSurveyError(f"--base does not exist: {pinned_path}")
        pinned = {
            "path": str(pinned_path),
            "sha256": _sha256(pinned_path),
            "modified": _stamp(_mtime(pinned_path)),
        }
    newest_source = max(
        (item.newest_source for item in [*stages, top] if item.newest_source),
        key=_mtime,
        default=None,
    )
    newest_object = max(
        (item.newest_object for item in [*stages, top] if item.newest_object),
        key=_mtime,
        default=None,
    )
    return {
        "schema": SURVEY_SCHEMA,
        "root": str(location),
        "stages": [item.as_dict() for item in stages],
        "top_level": top.as_dict(),
        "stage_count": len(stages),
        "files_seen": seen,
        "budget": budget,
        "truncated": capped,
        "findings_logs": _findings_logs(location, budget),
        "sweeps": sweeps,
        "instrument_gates": gates,
        "workbench_manifests": manifests,
        "newest_source": str(newest_source) if newest_source else None,
        "newest_object": str(newest_object) if newest_object else None,
        "base": pinned,
        "reading": (
            "A survey is a reading of this directory as it is now: paths, "
            "counts, and hashes taken at read time. Nothing is stored, so "
            "nothing here can be a stale claim -- and nothing here guesses "
            "which artifact is the base."
        ),
    }


def survey_lines(report: dict[str, Any], *, limit: int = 20) -> list[str]:
    """Render the survey: the stages by recency, then what the directory knows."""

    lines = [
        f"campaign survey: {report['root']}",
        f"{report['stage_count']} stage director(ies), "
        f"{report['files_seen']} file(s) read",
    ]
    if report["truncated"]:
        lines.append(
            f"TRUNCATED: the walk stopped at {report['budget']} files. Counts "
            "below are a lower bound; raise --budget to read the rest."
        )
    if report["base"]:
        lines.extend(
            (
                "",
                f"base (pinned by --base): {report['base']['path']}",
                f"  sha256 {report['base']['sha256']}  "
                f"modified {report['base']['modified']}",
            )
        )
    lines.extend(("", " modified              stage           files  src   obj   notes"))
    for stage in report["stages"][:limit]:
        notes = ",".join(stage["notes"][:2]) or "-"
        lines.append(
            f" {(stage['modified'] or '-'):<21} {stage['name'][:15]:<15} "
            f"{stage['files']:<6} {stage['sources']:<5} {stage['objects']:<5} {notes}"
        )
    if report["stage_count"] > limit:
        lines.append(f" ... {report['stage_count'] - limit} older stage(s)")

    for log in report["findings_logs"]:
        lines.extend(
            (
                "",
                f"findings log: {log['log']}",
                f"  {log['entries']} entr(ies) in the log, {log['pending']} "
                f"pending in the sidecar, {log['merged']} merged",
            )
        )
        if log["duplicate_ids"]:
            lines.append(
                f"  warning: {', '.join(log['duplicate_ids'])} are pending and "
                "already in the log"
            )
    if report["sweeps"]:
        lines.extend(("", f"sweeps ({len(report['sweeps'])}):"))
        for item in report["sweeps"][:limit]:
            coverage = item.get("coverage") or {}
            lines.append(
                f"  {item['generator']:<10} {item['variant_count']} variant(s)  "
                f"{coverage.get('vocabulary', '?')}  {item['path']}"
            )
    if report["instrument_gates"]:
        lines.extend(("", f"instrument gates ({len(report['instrument_gates'])}):"))
        for item in report["instrument_gates"][:limit]:
            lines.append(
                f"  {'PASS' if item['pass'] else 'FAIL'}  {item['profile']:<14} "
                f"{item['recorded']}  {item['path']}"
            )
    else:
        lines.extend(
            (
                "",
                "instrument gates: none recorded. If any trace in this "
                "directory came from an instrumented toolchain, its identity "
                "gate is not on file -- `decomp-workbench instrument gate`.",
            )
        )
    if report["workbench_manifests"]:
        lines.extend(("", "campaign manifests (read these with `campaign status`):"))
        lines.extend(f"  {item}" for item in report["workbench_manifests"][:limit])

    lines.extend(("", f"reading: {report['reading']}"))
    newest_source = report["newest_source"]
    newest_object = report["newest_object"]
    if newest_source or newest_object:
        lines.append("")
        lines.append("the newest artifacts found, which may or may not be the base:")
        if newest_source:
            lines.append(f"  source  {newest_source}")
        if newest_object:
            lines.append(f"  object  {newest_object}")
        if newest_object:
            lines.append(
                f"  next: decomp-workbench score {newest_object} "
                "--target-object TARGET --symbol NAME"
            )
    return lines
