"""Bounded process streams with explicit, durable full-output artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_STREAM_LIMIT = 64 * 1024


@dataclass(frozen=True)
class StreamCapture:
    """A bounded pair of streams and the metadata needed to find full output."""

    stdout: str
    stderr: str
    stdout_bytes: int
    stderr_bytes: int
    stdout_truncated: bool
    stderr_truncated: bool
    artifacts: dict[str, str]


def _preview(value: str, limit: int) -> tuple[str, int, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value, len(encoded), False
    prefix = encoded[:limit].decode("utf-8", errors="ignore")
    omitted = len(encoded) - len(prefix.encode("utf-8"))
    marker = f"\n… {omitted} byte(s) omitted; retain artifacts for full output\n"
    return prefix + marker, len(encoded), True


def capture_streams(
    stdout: str,
    stderr: str,
    *,
    limit: int = DEFAULT_STREAM_LIMIT,
    artifact_dir: str | Path | None = None,
    stem: str,
) -> StreamCapture:
    """Bound process output and optionally retain its complete contents."""

    if limit < 0:
        raise ValueError("stream limit must be non-negative")
    stdout_preview, stdout_bytes, stdout_truncated = _preview(stdout, limit)
    stderr_preview, stderr_bytes, stderr_truncated = _preview(stderr, limit)
    artifacts: dict[str, str] = {}
    if artifact_dir is not None:
        root = Path(artifact_dir).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        for name, value in (("stdout", stdout), ("stderr", stderr)):
            if not value:
                continue
            suffix = 0
            while True:
                middle = "" if suffix == 0 else f".{suffix}"
                path = root / f"{stem}{middle}.{name}.txt"
                try:
                    # Exclusive creation keeps concurrent candidates with the
                    # same display stem from destroying each other's log.
                    with path.open("x", encoding="utf-8") as artifact:
                        artifact.write(value)
                except FileExistsError:
                    suffix += 1
                    continue
                break
            artifacts[name] = str(path)
    return StreamCapture(
        stdout=stdout_preview,
        stderr=stderr_preview,
        stdout_bytes=stdout_bytes,
        stderr_bytes=stderr_bytes,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
        artifacts=artifacts,
    )
