"""Safe inspection and recoverable pruning for the content-addressed cache."""

from __future__ import annotations

import errno
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CACHE_STATUS_SCHEMA = "decomp-workbench-cache-status-v1"
CACHE_PRUNE_SCHEMA = "decomp-workbench-cache-prune-v1"
DURATION_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>[smhdw])")
DURATION_UNITS = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
    "w": 7 * 24 * 60 * 60,
}


@dataclass(frozen=True)
class CacheEntry:
    path: Path
    bytes: int
    modified_at_unix: float

    def as_dict(self, *, now: float) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "bytes": self.bytes,
            "modified_at_unix": self.modified_at_unix,
            "age_seconds": max(0.0, now - self.modified_at_unix),
        }


def parse_duration(value: str) -> float:
    """Parse a compact duration such as ``30d``, ``12h``, or ``1w2d``."""

    text = value.strip().lower()
    if not text:
        raise ValueError("duration must not be empty")
    position = 0
    seconds = 0.0
    for match in DURATION_RE.finditer(text):
        if match.start() != position:
            raise ValueError(
                f"invalid duration {value!r}; use combinations such as 30d or 1w2d"
            )
        seconds += float(match.group("value")) * DURATION_UNITS[match.group("unit")]
        position = match.end()
    if position != len(text) or seconds <= 0:
        raise ValueError(
            f"invalid duration {value!r}; use combinations such as 30d or 1w2d"
        )
    return seconds


def cache_entries(path: str | Path) -> list[CacheEntry]:
    """List regular cache files without following directory symlinks."""

    root = Path(path).expanduser().resolve()
    if not root.exists():
        return []
    if not root.is_dir():
        raise NotADirectoryError(f"cache path is not a directory: {root}")
    entries: list[CacheEntry] = []
    for item in root.iterdir():
        if item.is_symlink() or not item.is_file():
            continue
        stat = item.stat()
        entries.append(
            CacheEntry(
                path=item,
                bytes=stat.st_size,
                modified_at_unix=stat.st_mtime,
            )
        )
    entries.sort(key=lambda item: (item.modified_at_unix, item.path.name))
    return entries


def cache_status(path: str | Path) -> dict[str, Any]:
    """Return a bounded cache inventory."""

    root = Path(path).expanduser().resolve()
    now = time.time()
    entries = cache_entries(root)
    return {
        "schema": CACHE_STATUS_SCHEMA,
        "path": str(root),
        "exists": root.is_dir(),
        "files": len(entries),
        "bytes": sum(item.bytes for item in entries),
        "oldest_modified_at_unix": (entries[0].modified_at_unix if entries else None),
        "newest_modified_at_unix": (entries[-1].modified_at_unix if entries else None),
        "entries": [item.as_dict(now=now) for item in entries],
    }


def prune_cache(
    path: str | Path,
    *,
    older_than: float,
    apply: bool,
    trash_root: str | Path,
) -> dict[str, Any]:
    """Plan or recoverably apply a cache prune.

    Applying never unlinks an object. Files are atomically moved into a dated
    trash directory on the same filesystem whenever the configured state
    layout permits it.
    """

    root = Path(path).expanduser().resolve()
    now = time.time()
    selected = [
        item
        for item in cache_entries(root)
        if now - item.modified_at_unix >= older_than
    ]
    destination: Path | None = None
    moved: list[dict[str, str]] = []
    if apply and selected:
        trash = Path(trash_root).expanduser().resolve()
        destination = trash / time.strftime("cache-%Y%m%d-%H%M%S", time.gmtime(now))
        suffix = 1
        while destination.exists():
            destination = trash / (
                time.strftime("cache-%Y%m%d-%H%M%S", time.gmtime(now)) + f"-{suffix}"
            )
            suffix += 1
        destination.mkdir(parents=True)
        for entry in selected:
            target = destination / entry.path.name
            try:
                os.replace(entry.path, target)
            except OSError as error:
                if error.errno != errno.EXDEV:
                    raise
                # A caller may intentionally place trash on another volume.
                # ``move`` preserves recoverability there, even though the
                # cross-filesystem operation cannot be atomic.
                shutil.move(str(entry.path), target)
            moved.append({"from": str(entry.path), "to": str(target)})
    return {
        "schema": CACHE_PRUNE_SCHEMA,
        "path": str(root),
        "mode": "applied" if apply else "dry-run",
        "older_than_seconds": older_than,
        "selected_files": len(selected),
        "selected_bytes": sum(item.bytes for item in selected),
        "trash_directory": str(destination) if destination else None,
        "recoverable": bool(apply and selected),
        "entries": [item.as_dict(now=now) for item in selected],
        "moves": moved,
    }


def restore_pruned_cache(trash_directory: str | Path, cache_dir: str | Path) -> int:
    """Restore non-conflicting objects from one prune trash directory."""

    source = Path(trash_directory).expanduser().resolve()
    destination = Path(cache_dir).expanduser().resolve()
    if not source.is_dir():
        raise NotADirectoryError(f"trash directory does not exist: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    items = [
        item for item in source.iterdir() if not item.is_symlink() and item.is_file()
    ]
    conflicts = [
        destination / item.name for item in items if (destination / item.name).exists()
    ]
    if conflicts:
        rendered = ", ".join(str(item) for item in sorted(conflicts))
        raise FileExistsError(
            f"refusing partial restore; cache entry exists: {rendered}"
        )

    restored = 0
    for item in items:
        target = destination / item.name
        try:
            # A hard link creates the destination exclusively and makes the
            # same-filesystem move recoverable until the source name is
            # removed. Unsupported/cross-filesystem links use an exclusive
            # copy with the same no-overwrite contract.
            os.link(item, target)
        except FileExistsError:
            raise FileExistsError(
                f"refusing to overwrite cache entry: {target}"
            ) from None
        except OSError:
            try:
                with (
                    item.open("rb") as input_stream,
                    target.open("xb") as output_stream,
                ):
                    shutil.copyfileobj(input_stream, output_stream)
                    output_stream.flush()
                    os.fsync(output_stream.fileno())
                shutil.copystat(item, target)
            except BaseException:
                target.unlink(missing_ok=True)
                raise
        item.unlink()
        restored += 1
    return restored
