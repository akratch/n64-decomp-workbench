"""Small, hash-bound evidence primitives shared by durable receipts."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class EvidenceError(ValueError):
    """An evidence document is malformed, stale, or internally inconsistent."""


def file_sha256(path: str | Path) -> str:
    """Hash one file without loading an image-sized artifact into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_record(path: str | Path, *, role: str) -> dict[str, Any]:
    """Describe one stable regular file by resolved path and content identity.

    Hashing a file that is being replaced or rewritten can otherwise produce a
    digest for no state that ever existed on disk.  Read through one descriptor
    and require both that descriptor and the resolved path to name the same,
    unchanged file before publishing the receipt.
    """

    if not role:
        raise EvidenceError("artifact role must be a non-empty string")
    location = Path(path).expanduser().resolve()
    digest = hashlib.sha256()
    try:
        with location.open("rb") as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise EvidenceError(f"{role} is not a regular file: {location}")
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
            after = os.fstat(source.fileno())
        current = location.stat()
    except OSError as error:
        raise EvidenceError(f"cannot capture {role} {location}: {error}") from None

    def identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
        return (
            value.st_dev,
            value.st_ino,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        )

    if identity(before) != identity(after) or identity(after) != identity(current):
        raise EvidenceError(f"{role} changed while it was being captured: {location}")
    return {
        "role": role,
        "path": str(location),
        "sha256": digest.hexdigest(),
        "size": after.st_size,
    }


def verify_artifact_record(value: object, *, where: str) -> dict[str, Any]:
    """Validate and re-hash an artifact record, refusing moved or stale inputs."""

    if not isinstance(value, Mapping):
        raise EvidenceError(f"{where} must be an artifact object")
    path_value = value.get("path")
    role = value.get("role")
    digest = value.get("sha256")
    size = value.get("size")
    if not isinstance(role, str) or not role:
        raise EvidenceError(f"{where}.role must be a non-empty string")
    if not isinstance(path_value, str) or not path_value:
        raise EvidenceError(f"{where}.path must be a non-empty string")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
    ):
        raise EvidenceError(f"{where}.sha256 must be a lowercase SHA-256 digest")
    if type(size) is not int or size < 0:
        raise EvidenceError(f"{where}.size must be a non-negative integer")
    current = artifact_record(path_value, role=role)
    if current["size"] != size or current["sha256"] != digest:
        raise EvidenceError(
            f"{where} is stale: {path_value} no longer has the recorded content"
        )
    return current


def load_json_object(path: str | Path, *, where: str) -> dict[str, Any]:
    """Read exactly one JSON object with a concise domain error."""

    location = Path(path).expanduser()
    try:
        value = json.loads(location.read_text(encoding="utf-8"))
    except OSError as error:
        raise EvidenceError(f"cannot read {where} {location}: {error}") from None
    except json.JSONDecodeError as error:
        raise EvidenceError(f"{where} {location} is not valid JSON: {error}") from None
    if not isinstance(value, dict):
        raise EvidenceError(f"{where} {location} must contain a JSON object")
    return value


def write_json_atomic(path: str | Path, value: Mapping[str, Any]) -> Path:
    """Atomically replace an owned JSON state file after syncing its contents."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(value, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        if os.name != "nt":
            directory = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


@contextmanager
def exclusive_file_lock(path: str | Path) -> Iterator[None]:
    """Serialize one short state transaction on POSIX and Windows."""

    location = Path(path)
    location.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(location, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            import importlib

            msvcrt: Any = importlib.import_module("msvcrt")
            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            yield
        finally:
            os.lseek(descriptor, 0, os.SEEK_SET)
            if os.name == "nt":
                import importlib

                windows_lock: Any = importlib.import_module("msvcrt")
                windows_lock.locking(descriptor, windows_lock.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


__all__ = [
    "EvidenceError",
    "artifact_record",
    "exclusive_file_lock",
    "file_sha256",
    "load_json_object",
    "verify_artifact_record",
    "write_json_atomic",
]
