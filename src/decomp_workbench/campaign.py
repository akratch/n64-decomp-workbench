"""Parallel, cached, and resumable candidate compilation campaigns."""

from __future__ import annotations

import concurrent.futures
import hashlib
import itertools
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .compare import TargetObject, compare_candidate, load_target
from .model import Comparison, CompileResult, display_path
from .objdump import discover_objdump

LEDGER_SCHEMA = "decomp-workbench-campaign-v1"

_RUNNING_LOCK = threading.Lock()
_RUNNING_COMPILERS: set[subprocess.Popen[str]] = set()


TERMINATE_GRACE_SECONDS = 2.0


class CompilerTimeoutError(RuntimeError):
    """A compiler exceeded its deadline after its whole process group ended."""

    def __init__(
        self,
        command: list[str],
        timeout: float,
        *,
        stdout: str,
        stderr: str,
    ) -> None:
        super().__init__(f"compiler exceeded --timeout={timeout:g} seconds")
        self.command = command
        self.timeout = timeout
        self.stdout = stdout
        self.stderr = stderr


def process_group_arguments() -> dict[str, Any]:
    """Return the arguments that give a compiler its own process group.

    A compiler wrapper usually starts more processes than the one the
    workbench invoked. Owning the group makes it possible to end all of them
    together: a leaked parallel job outlived its campaign once and degraded
    two later runs.

    On POSIX the child gets its own process group *inside* the workbench's
    session, so it keeps the controlling terminal and is still reaped by a
    terminal hangup if the workbench dies without cleaning up. A new session
    (``start_new_session``) would detach it entirely; that is only used on
    Python 3.10, which has no ``process_group`` parameter.
    """

    if os.name == "posix":
        if sys.version_info >= (3, 11):
            return {"process_group": 0}
        return {"start_new_session": True}
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return {"creationflags": flags} if flags else {}


def signal_process_group(process: subprocess.Popen[str], number: int) -> bool:
    """Signal a compiler's whole process group; report whether that worked."""

    if os.name == "posix":
        try:
            os.killpg(os.getpgid(process.pid), number)
        except OSError:
            return False
        return True
    # Windows has no process-group signals. A console break reaches the group
    # created for this child when a console exists; otherwise only the direct
    # child can be ended, which is why the group guarantee is documented as
    # POSIX-only.
    event = getattr(signal, "CTRL_BREAK_EVENT", None)
    if event is None:
        return False
    try:
        os.kill(process.pid, event)
    except OSError:
        return False
    return True


def terminate_process_group(
    process: subprocess.Popen[str], *, grace: float = TERMINATE_GRACE_SECONDS
) -> None:
    """End one compiler and everything it started.

    Terminate first, then escalate: a wrapper that ignores or traps the polite
    signal must not be able to outlive the campaign that started it.
    """

    if process.poll() is not None:
        return
    if not signal_process_group(process, signal.SIGTERM):
        try:
            process.terminate()
        except OSError:
            return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.05)
    kill_signal = getattr(signal, "SIGKILL", signal.SIGTERM)
    if not signal_process_group(process, kill_signal):
        try:
            process.kill()
        except OSError:
            pass


def terminate_running_compilers() -> None:
    """End every compiler this process started, and their children."""

    with _RUNNING_LOCK:
        processes = list(_RUNNING_COMPILERS)
    for process in processes:
        terminate_process_group(process)


def run_compiler(
    command: list[str],
    *,
    environment: dict[str, str],
    compile_cwd: Path,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one compiler as the owner of its own process group."""

    with subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, **environment},
        cwd=compile_cwd,
        **process_group_arguments(),
    ) as process:
        with _RUNNING_LOCK:
            _RUNNING_COMPILERS.add(process)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            terminate_process_group(process)
            stdout, stderr = process.communicate()
            raise CompilerTimeoutError(
                command,
                timeout if timeout is not None else 0.0,
                stdout=stdout,
                stderr=stderr,
            ) from None
        except BaseException:
            terminate_process_group(process)
            raise
        finally:
            with _RUNNING_LOCK:
                _RUNNING_COMPILERS.discard(process)
    return subprocess.CompletedProcess(
        args=command,
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
    )


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
    target: TargetObject,
    template: str,
    cache_dir: Path,
    objdump: str | None,
    section: str,
    environment: dict[str, str],
    compile_cwd: Path,
    keep_dir: Path | None,
    timeout: float | None,
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
                process = run_compiler(
                    command,
                    environment=environment,
                    compile_cwd=compile_cwd,
                    timeout=timeout,
                )
            except CompilerTimeoutError as error:
                returncode = 124
                stdout = error.stdout
                stderr = f"{error.stderr}\n{error}".strip()
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
            comparison = compare_candidate(
                target,
                cached_object,
                objdump=objdump,
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
    timeout: float | None,
) -> None:
    """Append one self-contained JSONL record."""

    record = {
        "schema": LEDGER_SCHEMA,
        "recorded_at_unix": time.time(),
        "duplicate_sources": duplicate_sources,
        "provenance": provenance,
        "execution": {"timeout_seconds": timeout},
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
    stop_on_exact: bool = True,
    timeout: float | None = 120.0,
) -> tuple[list[CompileResult], dict[str, list[str]]]:
    """Compile a candidate set and return results in deterministic order.

    The target is disassembled once and compared in process, so a variant
    costs one compiler run and one objdump run rather than a comparison
    subprocess per candidate.

    With ``stop_on_exact`` the campaign stops submitting candidates once one
    compares exact. Candidates already running are allowed to finish, and the
    ledger keeps one record for every candidate that actually ran.
    """

    if jobs < 1:
        raise ValueError("--jobs must be at least 1")
    if timeout is not None and timeout <= 0:
        raise ValueError("--timeout must be positive")
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
    target_object = load_target(
        target_path, objdump=objdump_path, symbol=symbol, section=section
    )
    results: list[CompileResult] = []
    queue = iter(candidates)
    pending: dict[concurrent.futures.Future[CompileResult], Candidate] = {}

    def collect(
        future: concurrent.futures.Future[CompileResult], candidate: Candidate
    ) -> CompileResult:
        """Turn one finished future into a result, including a failure.

        A candidate that raises an unmodelled error is a failed candidate,
        not a failed campaign: discarding the other results would throw away
        work the campaign already paid for. ``KeyboardInterrupt`` and
        ``SystemExit`` are not caught here; they end the run.
        """

        try:
            return future.result()
        except Exception as error:
            return CompileResult(
                source=display_path(candidate.source),
                command=candidate.command,
                returncode=1,
                stdout="",
                stderr=f"campaign error: {type(error).__name__}: {error}",
                object_path=None,
                comparison=None,
                cache_key=candidate.cache_key,
            )

    def record(
        future: concurrent.futures.Future[CompileResult], candidate: Candidate
    ) -> CompileResult:
        result = collect(future, candidate)
        results.append(result)
        if ledger_path:
            append_ledger(
                ledger_path,
                result,
                duplicate_sources=duplicates[result.cache_key],
                provenance=candidate.provenance,
                timeout=timeout,
            )
        return result

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:

        def submit_next(count: int) -> None:
            for candidate in itertools.islice(queue, count):
                pending[
                    executor.submit(
                        _compile_candidate,
                        candidate,
                        target=target_object,
                        template=template,
                        cache_dir=cache_path,
                        objdump=objdump_path,
                        section=section,
                        environment=env,
                        compile_cwd=compile_cwd_path,
                        keep_dir=keep_path,
                        timeout=timeout,
                    )
                ] = candidate

        try:
            # Candidates are submitted in flight-sized batches rather than all
            # at once so that stopping early actually stops work instead of
            # cancelling futures the pool has already picked up.
            submit_next(jobs)
            stop = False
            while pending and not stop:
                done, _ = concurrent.futures.wait(
                    pending, return_when=concurrent.futures.FIRST_COMPLETED
                )
                for future in done:
                    result = record(future, pending.pop(future))
                    comparison = result.comparison
                    if stop_on_exact and comparison is not None and comparison.exact:
                        stop = True
                if not stop:
                    submit_next(len(done))
            # Stopping means "submit nothing further". Candidates the pool had
            # already started cannot be cancelled, so they are waited for and
            # recorded: their objects exist, and a ledger that omitted them
            # would misreport what the campaign actually tested.
            for future in list(pending):
                if future.cancel():
                    del pending[future]
            concurrent.futures.wait(pending)
            for future in list(pending):
                record(future, pending.pop(future))
        except BaseException:
            # Interrupts and errors must not leave compilers (or the tools a
            # compiler wrapper spawned) running after the campaign.
            for future in pending:
                future.cancel()
            terminate_running_compilers()
            raise
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
