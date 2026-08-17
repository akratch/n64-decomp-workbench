"""Fetch one decomp.me scratch export into the standard local layout.

This is the only command that downloads a scratch, and it exists because the
step before every offline workflow — "get the ZIP" — was the step people kept
getting wrong: an unidentified request that gets refused, a re-download of a
scratch already on disk, or an archive unpacked without any of the validation
`check-scratch` would have applied.

The command downloads once, validates the archive with exactly the loader that
reads a local export, and then writes it out. A scratch already fetched is
never fetched again: the cached copy is reported and no request is made.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .http_client import PoliteClient
from .scratch_check import ScratchPackage, load_scratch

DEFAULT_API_BASE = "https://decomp.me/api"

FETCH_SCHEMA = "decomp-workbench-scratch-fetch-v1"

#: What a complete export holds. `target.s` and `current.o` are present only
#: for some scratches, so a missing member is reported rather than fatal.
EXPORT_MEMBERS = ("metadata.json", "ctx.c", "code.c", "target.o", "target.s")

#: decomp.me slugs are short URL-safe tokens. Validating before building a URL
#: keeps a stray path segment out of the request.
SLUG_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")

ACCEPT_ARCHIVE = "application/zip, application/octet-stream"


def scratch_slug(value: str) -> str:
    """Return the slug named by `value`, which may be a slug or a scratch URL.

    People copy the browser URL, not the slug, and a command that rejects the
    thing on the clipboard for no reason is a command people stop using.
    """

    text = value.strip()
    if not text:
        raise ValueError("scratch slug is empty")
    if "://" in text:
        parsed = urlparse(text)
        parts = [part for part in parsed.path.split("/") if part]
        if "scratch" in parts:
            parts = parts[parts.index("scratch") + 1 :]
        text = parts[0] if parts else ""
    if not SLUG_RE.fullmatch(text):
        raise ValueError(
            f"not a decomp.me scratch slug: {value!r}. Pass the slug "
            f"(for example 'aBcDe') or the scratch URL."
        )
    return text


def export_url(slug: str, *, api_base: str = DEFAULT_API_BASE) -> str:
    """Return the export endpoint for `slug`."""

    return f"{api_base.rstrip('/')}/scratch/{slug}/export"


def scratch_url(slug: str, *, api_base: str = DEFAULT_API_BASE) -> str:
    """Return the human page for `slug`, derived from the API base."""

    parsed = urlparse(api_base)
    origin = (
        f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else "https://decomp.me"
    )
    return f"{origin}/scratch/{slug}"


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _describe(
    package: ScratchPackage, destination: Path, archive: Path
) -> dict[str, Any]:
    files = {
        name: {"bytes": len(content), "sha256": _digest(content)}
        for name, content in sorted(package.files.items())
    }
    return {
        "schema": FETCH_SCHEMA,
        "output": str(destination),
        "archive": str(archive) if archive.exists() else None,
        "files": files,
        "missing_members": [
            name for name in EXPORT_MEMBERS if name not in package.files
        ],
        "metadata": package.public_metadata(),
    }


def _existing_export(destination: Path) -> ScratchPackage | None:
    """Return the export already at `destination`, or None if there is none."""

    if not destination.is_dir() or not any(destination.iterdir()):
        return None
    try:
        package = load_scratch(destination)
    except ValueError:
        return None
    return package if package.kind == "decomp.me-export" else None


def fetch_scratch(
    slug: str,
    *,
    client: PoliteClient,
    outdir: str | Path = ".",
    api_base: str = DEFAULT_API_BASE,
    force: bool = False,
    keep_archive: bool = True,
) -> dict[str, Any]:
    """Download and unpack one export, or report the copy already on disk."""

    slug = scratch_slug(slug)
    root = Path(outdir).expanduser().resolve()
    destination = root / slug
    archive = root / f"{slug}.zip"
    source = export_url(slug, api_base=api_base)

    if not force:
        cached = _existing_export(destination)
        if cached is not None:
            report = _describe(cached, destination, archive)
            report.update({"slug": slug, "source_url": source, "reused": True})
            report["next_actions"] = _next_actions(destination)
            return report
        if destination.exists() and any(Path(destination).iterdir()):
            raise ValueError(
                f"{destination} already exists and is not a decomp.me export. "
                f"Choose another --outdir, or remove it and re-run."
            )

    root.mkdir(parents=True, exist_ok=True)
    body = client.get(source, accept=ACCEPT_ARCHIVE).body
    staging_archive = root / f".{slug}.zip.partial"
    staging_dir = root / f".{slug}.partial"
    try:
        staging_archive.write_bytes(body)
        package = load_scratch(staging_archive)
        if package.kind != "decomp.me-export":
            raise ValueError(
                f"{source} did not return a decomp.me export "
                f"(no metadata.json in the archive)."
            )
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True)
        for name in package.files:
            package.materialize(name, staging_dir)
        if destination.exists():
            # Only ever replace something this command could have written.
            if _existing_export(destination) is None and any(destination.iterdir()):
                raise ValueError(
                    f"refusing to replace {destination}: it is not a decomp.me export."
                )
            shutil.rmtree(destination)
        staging_dir.replace(destination)
        if keep_archive:
            staging_archive.replace(archive)
    finally:
        for leftover in (staging_archive, staging_dir):
            if leftover.is_dir():
                shutil.rmtree(leftover, ignore_errors=True)
            elif leftover.exists():
                leftover.unlink()

    unpacked = load_scratch(destination)
    report = _describe(unpacked, destination, archive)
    report.update({"slug": slug, "source_url": source, "reused": False})
    report["next_actions"] = _next_actions(destination)
    return report


def _next_actions(destination: Path) -> list[dict[str, Any]]:
    return [
        {
            "why": "validate the export and read its truth stack locally",
            "command_argv": ["decomp-workbench", "check-scratch", str(destination)],
        }
    ]
