"""Parallel, cached, and resumable candidate compilation campaigns."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .compare import compare_objects
from .model import Comparison, CompileResult, display_path
from .objdump import discover_objdump

LEDGER_SCHEMA = "decomp-workbench-campaign-v1"


@dataclass(frozen=True)
class Candidate:
    """A resolved source candidate and its reproducibility key."""

    source: Path
    command: list[str]
    cache_key: str
    provenance: dict[str, object]


def render_compile_command(template: str, source: Path, output: Path) -> list[str]:
    """Render a compiler command without invoking a shell."""

    parts = shlex.split(template)
    if not any("{source}" in part for part in parts):
        raise ValueError("--compile-command must contain {source}")
    if not any("{output}" in part for part in parts):
        raise ValueError("--compile-command must contain {output}")
    return [
        part.replace("{source}", str(source)).replace("{output}", str(output))
        for part in parts
    ]


def file_sha256(path: Path) -> str:
    """Hash one file without retaining it in memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def executable_identity(
    command: list[str], *, cwd: Path | None = None
) -> dict[str, str | None]:
    """Record the directly invoked compiler or wrapper when available."""

    executable = command[0]
    discovered = shutil.which(executable)
    resolved: str | None
    if discovered is not None:
        resolved = str(Path(discovered).expanduser().resolve())
    else:
        path = Path(executable).expanduser()
        if not path.is_absolute() and cwd is not None:
            path = cwd / path
        resolved = str(path.resolve()) if path.is_file() else None
    digest = file_sha256(Path(resolved)) if resolved else None
    return {"requested": executable, "resolved": resolved, "sha256": digest}


def candidate_key(
    source: Path,
    *,
    command: list[str],
    target: Path,
    symbol: str | None,
    environment: dict[str, str],
    compile_cwd: Path | None = None,
    section: str = ".text",
    objdump: str | None = None,
) -> str:
    """Build a stable key from the inputs controlled by the workbench."""

    payload = candidate_provenance(
        source,
        command=command,
        target=target,
        symbol=symbol,
        environment=environment,
        compile_cwd=compile_cwd,
        section=section,
        objdump=objdump,
    )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def candidate_provenance(
    source: Path,
    *,
    command: list[str],
    target: Path,
    symbol: str | None,
    environment: dict[str, str],
    compile_cwd: Path | None = None,
    section: str = ".text",
    objdump: str | None = None,
) -> dict[str, object]:
    """Return the explicit inputs represented by a campaign cache key."""

    resolved_cwd = (compile_cwd or Path.cwd()).expanduser().resolve()
    return {
        "schema": LEDGER_SCHEMA,
        "source": str(source.expanduser().resolve()),
        "source_sha256": file_sha256(source),
        "target": str(target.expanduser().resolve()),
        "target_sha256": file_sha256(target),
        "command": command,
        "compiler": executable_identity(command, cwd=resolved_cwd),
        "objdump": executable_identity([objdump], cwd=resolved_cwd)
        if objdump
        else None,
        "compile_cwd": str(resolved_cwd),
        "symbol": symbol,
        "section": section,
        "environment": dict(sorted(environment.items())),
    }


def prepare_candidates(
    sources: Iterable[str | Path],
    *,
    template: str,
    target: Path,
    symbol: str | None,
    environment: dict[str, str],
    compile_cwd: Path | None = None,
    section: str = ".text",
    objdump: str | None = None,
) -> tuple[list[Candidate], dict[str, list[str]]]:
    """Resolve and deduplicate candidates by reproducibility key."""

    prepared: list[Candidate] = []
    duplicate_sources: dict[str, list[str]] = {}
    seen: dict[str, Candidate] = {}
    placeholder_output = Path("{cache_object}")
    for source_name in sources:
        source = Path(source_name).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"candidate source does not exist: {source}")
        command = render_compile_command(template, source, placeholder_output)
        provenance = candidate_provenance(
            source,
            command=command,
            target=target,
            symbol=symbol,
            environment=environment,
            compile_cwd=compile_cwd,
            section=section,
            objdump=objdump,
        )
        encoded = json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        key = hashlib.sha256(encoded).hexdigest()
        duplicate_sources.setdefault(key, []).append(display_path(source))
        if key in seen:
            continue
        candidate = Candidate(
            source=source,
            command=command,
            cache_key=key,
            provenance=provenance,
        )
        seen[key] = candidate
        prepared.append(candidate)
    return prepared, duplicate_sources


def _compile_candidate(
    candidate: Candidate,
    *,
    target: Path,
    template: str,
    cache_dir: Path,
    objdump: str | None,
    symbol: str | None,
    section: str,
    environment: dict[str, str],
    compile_cwd: Path,
    keep_dir: Path | None,
) -> CompileResult:
    started = time.monotonic()
    cached_object = cache_dir / f"{candidate.cache_key}.o"
    cached = cached_object.is_file() and cached_object.stat().st_size > 0
    stdout = ""
    stderr = ""
    returncode = 0
    command: list[str]

    if cached:
        command = render_compile_command(template, candidate.source, cached_object)
    else:
        with tempfile.TemporaryDirectory(prefix="decomp-workbench-campaign-") as temp:
            temporary_object = Path(temp) / "candidate.o"
            command = render_compile_command(
                template, candidate.source, temporary_object
            )
            try:
                process = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    env={**os.environ, **environment},
                    cwd=compile_cwd,
                )
            except OSError as error:
                returncode = 127
                stderr = str(error)
            else:
                stdout = process.stdout
                stderr = process.stderr
                returncode = process.returncode
            if (
                returncode == 0
                and temporary_object.is_file()
                and temporary_object.stat().st_size > 0
            ):
                temporary_cache = cache_dir / (
                    f".{candidate.cache_key}.{os.getpid()}.tmp"
                )
                shutil.copy2(temporary_object, temporary_cache)
                os.replace(temporary_cache, cached_object)

    comparison: Comparison | None = None
    kept: str | None = None
    if returncode == 0 and cached_object.is_file():
        try:
            comparison = compare_objects(
                target,
                cached_object,
                objdump=objdump,
                symbol=symbol,
                section=section,
            )
            comparison.candidate = display_path(candidate.source)
            if keep_dir:
                destination = keep_dir / (
                    f"{candidate.cache_key[:12]}-{candidate.source.stem}.o"
                )
                shutil.copy2(cached_object, destination)
                kept = str(destination)
        except (OSError, RuntimeError) as error:
            returncode = 1
            stderr = f"{stderr}\ncomparison failed: {error}".strip()

    return CompileResult(
        source=display_path(candidate.source),
        command=command,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        object_path=kept,
        comparison=comparison,
        cache_key=candidate.cache_key,
        cached=cached,
        duration_seconds=time.monotonic() - started,
    )


def append_ledger(
    path: Path,
    result: CompileResult,
    *,
    duplicate_sources: list[str],
    provenance: dict[str, object],
) -> None:
    """Append one self-contained JSONL record."""

    record = {
        "schema": LEDGER_SCHEMA,
        "recorded_at_unix": time.time(),
        "duplicate_sources": duplicate_sources,
        "provenance": provenance,
        **result.as_dict(),
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


def run_campaign(
    sources: Iterable[str | Path],
    *,
    target: str | Path,
    template: str,
    cache_dir: str | Path,
    ledger: str | Path | None = None,
    jobs: int = 1,
    objdump: str | None = None,
    symbol: str | None = None,
    section: str = ".text",
    environment: dict[str, str] | None = None,
    compile_cwd: str | Path | None = None,
    keep_objects: str | Path | None = None,
) -> tuple[list[CompileResult], dict[str, list[str]]]:
    """Compile a candidate set and return results in deterministic order."""

    if jobs < 1:
        raise ValueError("--jobs must be at least 1")
    target_path = Path(target).expanduser().resolve()
    if not target_path.is_file():
        raise FileNotFoundError(f"target object does not exist: {target_path}")
    env = environment or {}
    compile_cwd_path = (
        Path(compile_cwd).expanduser().resolve()
        if compile_cwd
        else Path.cwd().resolve()
    )
    if not compile_cwd_path.is_dir():
        raise NotADirectoryError(
            f"compiler working directory does not exist: {compile_cwd_path}"
        )
    objdump_path = discover_objdump(objdump)
    cache_path = Path(cache_dir).expanduser().resolve()
    cache_path.mkdir(parents=True, exist_ok=True)
    keep_path = Path(keep_objects).expanduser().resolve() if keep_objects else None
    if keep_path:
        keep_path.mkdir(parents=True, exist_ok=True)
    ledger_path = Path(ledger).expanduser().resolve() if ledger else None
    if ledger_path:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)

    candidates, duplicates = prepare_candidates(
        sources,
        template=template,
        target=target_path,
        symbol=symbol,
        environment=env,
        compile_cwd=compile_cwd_path,
        section=section,
        objdump=objdump_path,
    )
    results: list[CompileResult] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {
            executor.submit(
                _compile_candidate,
                candidate,
                target=target_path,
                template=template,
                cache_dir=cache_path,
                objdump=objdump_path,
                symbol=symbol,
                section=section,
                environment=env,
                compile_cwd=compile_cwd_path,
                keep_dir=keep_path,
            ): candidate
            for candidate in candidates
        }
        for future in concurrent.futures.as_completed(futures):
            candidate = futures[future]
            result = future.result()
            results.append(result)
            if ledger_path:
                append_ledger(
                    ledger_path,
                    result,
                    duplicate_sources=duplicates[result.cache_key],
                    provenance=candidate.provenance,
                )
    results.sort(
        key=lambda item: (
            item.comparison is None,
            item.comparison.sort_key if item.comparison else (),
            item.source,
        )
    )
    return results, duplicates


def group_object_basins(results: Iterable[CompileResult]) -> list[list[CompileResult]]:
    """Group successful variants that compiled to the same function bytes.

    Source-equivalent experiments often look different while collapsing to one
    allocator basin. Reporting that collapse prevents a campaign from
    overstating how many independent ideas it actually tested.
    """

    buckets: dict[str, list[CompileResult]] = {}
    for result in results:
        comparison = result.comparison
        if comparison is None:
            continue
        buckets.setdefault(comparison.candidate_sha256, []).append(result)
    grouped = list(buckets.values())
    for basin in grouped:
        basin.sort(
            key=lambda item: (
                item.comparison.sort_key if item.comparison else (),
                item.source,
            )
        )
    grouped.sort(
        key=lambda basin: (
            basin[0].comparison.sort_key if basin[0].comparison else (),
            basin[0].comparison.candidate_sha256 if basin[0].comparison else "",
        )
    )
    return grouped
