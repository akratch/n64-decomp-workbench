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
SIZE_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>[kmgt]?i?b?)?", re.I)
SIZE_UNITS = {
    "": 1,
    "b": 1,
    "k": 1024,
    "kb": 1024,
    "kib": 1024,
    "m": 1024**2,
    "mb": 1024**2,
    "mib": 1024**2,
    "g": 1024**3,
    "gb": 1024**3,
    "gib": 1024**3,
    "t": 1024**4,
    "tb": 1024**4,
    "tib": 1024**4,
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


def parse_size(value: str) -> int:
    """Parse a byte limit such as ``500MiB`` or ``2G``."""

    match = SIZE_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"invalid size {value!r}; use values such as 500MiB or 2G")
    unit = (match.group("unit") or "").lower()
    if unit not in SIZE_UNITS:
        raise ValueError(f"invalid size unit in {value!r}")
    size = int(float(match.group("value")) * SIZE_UNITS[unit])
    if size <= 0:
        raise ValueError("size must be positive")
    return size


def format_bytes(size: int) -> str:
    """Return a compact IEC byte count while preserving exact bytes in JSON."""

    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"


def cache_entries(path: str | Path) -> list[CacheEntry]:
    """List regular cache files without following directory symlinks."""

    root = Path(path).expanduser().resolve()
    if not root.exists():
        return []
    if not root.is_dir():
        raise NotADirectoryError(f"cache path is not a directory: {root}")
    entries: list[CacheEntry] = []
    for item in root.rglob("*"):
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
    total = sum(item.bytes for item in entries)
    return {
        "schema": CACHE_STATUS_SCHEMA,
        "path": str(root),
        "exists": root.is_dir(),
        "files": len(entries),
        "bytes": total,
        "human_bytes": format_bytes(total),
        "oldest_modified_at_unix": (entries[0].modified_at_unix if entries else None),
        "newest_modified_at_unix": (entries[-1].modified_at_unix if entries else None),
        "entries": [item.as_dict(now=now) for item in entries],
    }


def prune_cache(
    path: str | Path,
    *,
    older_than: float | None = None,
    max_size: int | None = None,
    keep_recent: int = 0,
    apply: bool,
    trash_root: str | Path,
) -> dict[str, Any]:
    """Plan or recoverably apply a cache prune.

    Applying never unlinks an object. Files are atomically moved into a dated
    trash directory on the same filesystem whenever the configured state
    layout permits it.
    """

    root = Path(path).expanduser().resolve()
    if older_than is None and max_size is None:
        raise ValueError("prune needs --older-than, --max-size, or both")
    if older_than is not None and older_than <= 0:
        raise ValueError("older_than must be positive")
    if max_size is not None and max_size <= 0:
        raise ValueError("max_size must be positive")
    if keep_recent < 0:
        raise ValueError("keep_recent must be non-negative")
    now = time.time()
    entries = cache_entries(root)
    protected = {item.path for item in entries[-keep_recent:]} if keep_recent else set()
    selected_paths = {
        item.path
        for item in entries
        if older_than is not None
        and now - item.modified_at_unix >= older_than
        and item.path not in protected
    }
    if max_size is not None:
        remaining_bytes = sum(
            item.bytes for item in entries if item.path not in selected_paths
        )
        for item in entries:
            if remaining_bytes <= max_size:
                break
            if item.path in selected_paths or item.path in protected:
                continue
            selected_paths.add(item.path)
            remaining_bytes -= item.bytes
    selected = [item for item in entries if item.path in selected_paths]
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
            target = destination / entry.path.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
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
        "max_size_bytes": max_size,
        "keep_recent": keep_recent,
        "cache_bytes_before": sum(item.bytes for item in entries),
        "cache_bytes_after": sum(item.bytes for item in entries)
        - sum(item.bytes for item in selected),
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
        item for item in source.rglob("*") if not item.is_symlink() and item.is_file()
    ]
    conflicts = [
        destination / item.relative_to(source)
        for item in items
        if (destination / item.relative_to(source)).exists()
    ]
    if conflicts:
        rendered = ", ".join(str(item) for item in sorted(conflicts))
        raise FileExistsError(
            f"refusing partial restore; cache entry exists: {rendered}"
        )

    restored = 0
    for item in items:
        target = destination / item.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
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
