"""Parallel, cached, and resumable candidate compilation campaigns."""

from __future__ import annotations

import concurrent.futures
import hashlib
import itertools
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import DEFAULT_STREAM_LIMIT, capture_streams
from .command_line import split_command
from .compare import TargetObject, compare_candidate, load_target
from .experiment_signals import evaluate_signals, required_signals_pass
from .experiments import RegionConstraint, SignalSpec
from .ledger_redaction import load_or_create_salt, redact_record, warn_if_unredacted
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
        encoding="utf-8",
        errors="replace",
        # The mapping is the complete build environment, not an overlay.
        # Inheriting the host here made compiler output depend on values absent
        # from campaign identity and cache keys.
        env=environment,
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


@dataclass(frozen=True)
class ParameterizedCandidate:
    """One source compiled under a candidate-specific explicit environment."""

    source: str | Path
    environment: dict[str, str]
    metadata: dict[str, Any]


def render_compile_command(template: str, source: Path, output: Path) -> list[str]:
    """Render a compiler command without invoking a shell."""

    parts = split_command(template)
    if not any("{source}" in part for part in parts):
        raise ValueError("--compile-command must contain {source}")
    if not any("{output}" in part for part in parts):
        raise ValueError("--compile-command must contain {output}")
    return [
        part.replace("{source}", str(source)).replace("{output}", str(output))
        for part in parts
    ]


def nice_prefix(level: int | None) -> list[str]:
    """Return the ``nice`` prefix for a background pass, or nothing.

    Every long-running fan-out in this workbench -- a scoring wave, a pass
    replay -- runs beside the interactive session that is reading its output,
    so it runs at a niceness by default. ``None`` or a non-positive level asks
    for none, and a host that has no ``nice`` runs without it rather than
    failing: the niceness is a courtesy, not a correctness property.
    """

    if level is None or level <= 0 or os.name != "posix":
        return []
    executable = shutil.which("nice")
    return [executable, "-n", str(level)] if executable else []


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
    compilation_envelope: Mapping[str, str] | None = None,
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
        compilation_envelope=compilation_envelope,
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
    compilation_envelope: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Return the explicit inputs represented by a campaign cache key."""

    resolved_cwd = (compile_cwd or Path.cwd()).expanduser().resolve()
    provenance: dict[str, object] = {
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
        "environment_mode": "sealed",
    }
    if compilation_envelope:
        provenance["compilation_envelope"] = dict(sorted(compilation_envelope.items()))
    return provenance


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
    compilation_envelope: Mapping[str, str] | None = None,
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
            compilation_envelope=compilation_envelope,
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
    stream_limit: int,
    artifact_dir: Path | None,
    experiment: dict[str, Any] | None,
    selected_region: RegionConstraint | None,
    signal_specs: tuple[SignalSpec, ...],
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
    object_sha256: str | None = None
    kept: str | None = None
    if returncode == 0 and cached_object.is_file():
        object_sha256 = file_sha256(cached_object)
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

    streams = capture_streams(
        stdout,
        stderr,
        limit=stream_limit,
        artifact_dir=artifact_dir,
        stem=candidate.cache_key,
    )
    region = (
        region_score(comparison, selected_region)
        if comparison is not None and selected_region is not None
        else None
    )
    signals = evaluate_signals(signal_specs, comparison)
    return CompileResult(
        source=display_path(candidate.source),
        command=command,
        returncode=returncode,
        stdout=streams.stdout,
        stderr=streams.stderr,
        object_path=kept,
        comparison=comparison,
        cache_key=candidate.cache_key,
        cached=cached,
        duration_seconds=time.monotonic() - started,
        stdout_bytes=streams.stdout_bytes,
        stderr_bytes=streams.stderr_bytes,
        stdout_truncated=streams.stdout_truncated,
        stderr_truncated=streams.stderr_truncated,
        artifacts=streams.artifacts,
        experiment=experiment,
        region=region,
        signals=signals,
        object_sha256=object_sha256,
    )


def append_ledger(
    path: Path,
    result: CompileResult,
    *,
    duplicate_sources: list[str],
    provenance: dict[str, object],
    timeout: float | None,
) -> None:
    """Append one self-contained JSONL record, with the target side redacted.

    This is the only place a *ledger* record is written, which is why the
    redaction lives here and not in ``compare``: the in-memory comparison keeps
    the target's disassembly, so the terminal, the reports and the diagnosis
    paths are unaffected, while the ledger -- written automatically, into the
    project tree, on every campaign run -- has every target-named field
    removed or replaced with a lossy summary, at any depth and in any
    container.

    Be exact about the scope, because an earlier version of this docstring said
    "cannot carry the ROM's instruction text at all" and that was not true.
    :func:`~decomp_workbench.ledger_redaction._sweep` keys on *field names*; it
    does not read string contents. Target code stored under a name that does
    not say ``target``, or as a bare element of a list with no key at all,
    still reaches the file. That residue is deliberate -- deciding whether an
    arbitrary string is disassembly is the consuming project's clean-room gate
    to do -- and it is why the ledger is gitignored rather than merely
    redacted.

    It is not the only file the tool can write with target assembly in it:
    ``--html`` renders target rows into a report, and ``force_spec`` records
    ``target_register``. Both are opt-in and land where the operator asks,
    which is a real mitigation but not a redaction.
    See :mod:`decomp_workbench.ledger_redaction`.
    """

    result_payload = result.as_dict()
    comparison_payload = result_payload.get("comparison")
    if isinstance(comparison_payload, dict):
        # Signals have already reduced row receipts to the declared predicate
        # outcomes. Keeping one receipt per aligned row in every automatic
        # ledger record would make large campaigns scale with function length
        # for evidence status/export never consumes.
        comparison_payload.pop("aligned_row_receipts", None)
    record = {
        "schema": LEDGER_SCHEMA,
        "recorded_at_unix": time.time(),
        "duplicate_sources": duplicate_sources,
        "provenance": provenance,
        "execution": {"timeout_seconds": timeout},
        **result_payload,
    }
    warning = warn_if_unredacted(path)
    if warning is not None:
        print(warning, file=sys.stderr)
    record = redact_record(record, load_or_create_salt(path))
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")


def recorded_ledger_keys(path: Path) -> set[str]:
    """Return completed cache keys without trusting a torn final JSONL line.

    Campaign and oracle ledgers are append-only. Re-running an identical input
    may still be useful (for example, to regenerate a terminal report from the
    cache), but it must not manufacture a second experimental observation.
    """

    if not path.is_file():
        return set()
    lines = path.read_text(encoding="utf-8").splitlines()
    keys: set[str] = set()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                continue
            raise ValueError(
                f"invalid campaign ledger JSON at line {index + 1}: {path}"
            ) from None
        if not isinstance(record, dict):
            raise ValueError(
                f"campaign ledger line {index + 1} is not an object: {path}"
            )
        key = record.get("cache_key")
        if isinstance(key, str) and key:
            keys.add(key)
    return keys


def _execute_candidates(
    candidates: Sequence[Candidate],
    duplicates: Mapping[str, list[str]],
    *,
    target_object: TargetObject,
    template: str,
    cache_path: Path,
    ledger_path: Path | None,
    jobs: int,
    objdump_path: str,
    section: str,
    environment_for: Callable[[Candidate], dict[str, str]],
    compile_cwd_path: Path,
    keep_path: Path | None,
    stop_on_exact: bool,
    timeout: float | None,
    stream_limit: int,
    artifact_path: Path | None,
    candidate_metadata: Mapping[str, dict[str, Any]],
    selected_region: RegionConstraint | None,
    signal_specs: tuple[SignalSpec, ...],
    deduplicate_ledger: bool,
    rank_by: str,
) -> list[CompileResult]:
    """Execute prepared candidates through one lifecycle and target image."""

    results: list[CompileResult] = []
    queue = iter(candidates)
    pending: dict[concurrent.futures.Future[CompileResult], Candidate] = {}
    recorded_keys = (
        recorded_ledger_keys(ledger_path)
        if ledger_path is not None and deduplicate_ledger
        else set()
    )

    def collect(
        future: concurrent.futures.Future[CompileResult], candidate: Candidate
    ) -> CompileResult:
        """Turn one finished future into a result, including a failure."""

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
                experiment=candidate_metadata.get(candidate.cache_key),
                signals=evaluate_signals(signal_specs, None),
            )

    def record(
        future: concurrent.futures.Future[CompileResult], candidate: Candidate
    ) -> CompileResult:
        result = collect(future, candidate)
        results.append(result)
        if ledger_path and (
            not deduplicate_ledger or result.cache_key not in recorded_keys
        ):
            append_ledger(
                ledger_path,
                result,
                duplicate_sources=duplicates[result.cache_key],
                provenance=candidate.provenance,
                timeout=timeout,
            )
            recorded_keys.add(result.cache_key)
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
                        environment=environment_for(candidate),
                        compile_cwd=compile_cwd_path,
                        keep_dir=keep_path,
                        timeout=timeout,
                        stream_limit=stream_limit,
                        artifact_dir=artifact_path,
                        experiment=candidate_metadata.get(candidate.cache_key),
                        selected_region=selected_region,
                        signal_specs=signal_specs,
                    )
                ] = candidate

        try:
            submit_next(jobs)
            stop = False
            while pending and not stop:
                done, _ = concurrent.futures.wait(
                    pending,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                for future in done:
                    result = record(future, pending.pop(future))
                    comparison = result.comparison
                    if stop_on_exact and comparison is not None and comparison.exact:
                        stop = True
                if not stop:
                    submit_next(len(done))
            for future in list(pending):
                if future.cancel():
                    del pending[future]
            concurrent.futures.wait(pending)
            for future in list(pending):
                record(future, pending.pop(future))
        except BaseException:
            for future in pending:
                future.cancel()
            terminate_running_compilers()
            raise
    results.sort(key=sort_campaign_results_key(results, rank_by=rank_by))
    return results


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
    stream_limit: int = DEFAULT_STREAM_LIMIT,
    artifact_dir: str | Path | None = None,
    candidate_metadata: dict[str, dict[str, Any]] | None = None,
    selected_region: RegionConstraint | None = None,
    signal_specs: tuple[SignalSpec, ...] = (),
    compilation_envelope: Mapping[str, str] | None = None,
    rank_by: str = "auto",
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
    if stream_limit < 0:
        raise ValueError("--stream-limit must be non-negative")
    if rank_by not in {"auto", "words", "temp-prefix"}:
        raise ValueError("rank_by must be auto, words, or temp-prefix")
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
    artifact_path = Path(artifact_dir).expanduser().resolve() if artifact_dir else None
    if artifact_path:
        artifact_path.mkdir(parents=True, exist_ok=True)
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
        compilation_envelope=compilation_envelope,
    )
    target_object = load_target(
        target_path, objdump=objdump_path, symbol=symbol, section=section
    )
    results = _execute_candidates(
        candidates,
        duplicates,
        target_object=target_object,
        template=template,
        cache_path=cache_path,
        ledger_path=ledger_path,
        jobs=jobs,
        objdump_path=objdump_path,
        section=section,
        environment_for=lambda _candidate: env,
        compile_cwd_path=compile_cwd_path,
        keep_path=keep_path,
        stop_on_exact=stop_on_exact,
        timeout=timeout,
        stream_limit=stream_limit,
        artifact_path=artifact_path,
        candidate_metadata=candidate_metadata or {},
        selected_region=selected_region,
        signal_specs=signal_specs,
        deduplicate_ledger=False,
        rank_by=rank_by,
    )
    return results, duplicates


def run_parameterized_campaign(
    variants: Sequence[ParameterizedCandidate],
    *,
    target: str | Path,
    template: str,
    cache_dir: str | Path,
    ledger: str | Path | None = None,
    jobs: int = 1,
    objdump: str | None = None,
    symbol: str | None = None,
    section: str = ".text",
    compile_cwd: str | Path | None = None,
    keep_objects: str | Path | None = None,
    stop_on_exact: bool = False,
    timeout: float | None = 120.0,
    stream_limit: int = DEFAULT_STREAM_LIMIT,
    artifact_dir: str | Path | None = None,
    rank_by: str = "auto",
) -> list[CompileResult]:
    """Run one source under many explicit environments in one campaign core."""

    if jobs < 1:
        raise ValueError("--jobs must be at least 1")
    if timeout is not None and timeout <= 0:
        raise ValueError("--timeout must be positive")
    if stream_limit < 0:
        raise ValueError("--stream-limit must be non-negative")
    if rank_by not in {"auto", "words", "temp-prefix"}:
        raise ValueError("rank_by must be auto, words, or temp-prefix")
    target_path = Path(target).expanduser().resolve()
    if not target_path.is_file():
        raise FileNotFoundError(f"target object does not exist: {target_path}")
    cwd = (
        Path(compile_cwd).expanduser().resolve()
        if compile_cwd
        else Path.cwd().resolve()
    )
    if not cwd.is_dir():
        raise NotADirectoryError(f"compiler working directory does not exist: {cwd}")
    objdump_path = discover_objdump(objdump)
    cache_path = Path(cache_dir).expanduser().resolve()
    cache_path.mkdir(parents=True, exist_ok=True)
    keep_path = Path(keep_objects).expanduser().resolve() if keep_objects else None
    if keep_path:
        keep_path.mkdir(parents=True, exist_ok=True)
    artifact_path = Path(artifact_dir).expanduser().resolve() if artifact_dir else None
    if artifact_path:
        artifact_path.mkdir(parents=True, exist_ok=True)
    ledger_path = Path(ledger).expanduser().resolve() if ledger else None
    if ledger_path:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)

    candidates: list[Candidate] = []
    duplicates: dict[str, list[str]] = {}
    environments: dict[str, dict[str, str]] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for variant in variants:
        prepared, _ = prepare_candidates(
            [variant.source],
            template=template,
            target=target_path,
            symbol=symbol,
            environment=variant.environment,
            compile_cwd=cwd,
            section=section,
            objdump=objdump_path,
        )
        candidate = prepared[0]
        if candidate.cache_key in environments:
            raise ValueError(
                "parameterized candidates have duplicate source/environment inputs"
            )
        candidates.append(candidate)
        duplicates[candidate.cache_key] = [display_path(candidate.source)]
        environments[candidate.cache_key] = variant.environment
        metadata[candidate.cache_key] = variant.metadata

    target_object = load_target(
        target_path,
        objdump=objdump_path,
        symbol=symbol,
        section=section,
    )
    return _execute_candidates(
        candidates,
        duplicates,
        target_object=target_object,
        template=template,
        cache_path=cache_path,
        ledger_path=ledger_path,
        jobs=jobs,
        objdump_path=objdump_path,
        section=section,
        environment_for=lambda candidate: environments[candidate.cache_key],
        compile_cwd_path=cwd,
        keep_path=keep_path,
        stop_on_exact=stop_on_exact,
        timeout=timeout,
        stream_limit=stream_limit,
        artifact_path=artifact_path,
        candidate_metadata=metadata,
        selected_region=None,
        signal_specs=(),
        deduplicate_ledger=True,
        rank_by=rank_by,
    )


def region_score(
    comparison: Comparison,
    constraint: RegionConstraint,
) -> dict[str, Any]:
    """Score one protected instruction region separately from its complement."""

    sites = comparison.aligned_diff_sites
    inside = [
        site
        for site in sites
        if constraint.start <= int(site["index"]) < constraint.end
    ]
    outside = [
        site
        for site in sites
        if not constraint.start <= int(site["index"]) < constraint.end
    ]
    covered = (
        comparison.target_instructions >= constraint.end
        and comparison.candidate_instructions >= constraint.end
    )
    return {
        **constraint.as_dict(),
        "covered": covered,
        "exact": covered and not inside,
        "selected_mismatches": len(inside),
        "outside_mismatches": len(outside),
        "outside_residual_sites": outside[:64],
        "outside_residual_sites_truncated": len(outside) > 64,
    }


def campaign_result_sort_key(
    result: CompileResult, *, by_raw: bool = False, rank_by: str = "auto"
) -> tuple[object, ...]:
    """Rank region preservation before the ordinary whole-function metric.

    ``by_raw`` swaps the whole-function metric for positional word counts. It
    is set for a run containing any gapped candidate: see
    :func:`~decomp_workbench.compare.rank_comparisons` for why aligned rows
    stop being a common scale there, even between two gapped candidates.
    """

    signal_key: tuple[object, ...] = (not required_signals_pass(result.signals),)
    region = result.region
    region_key: tuple[object, ...] = ()
    if region is not None:
        region_key = (
            not bool(region["exact"]),
            int(region["selected_mismatches"]),
            int(region["outside_mismatches"]),
        )
    comparison = result.comparison
    metric: tuple[object, ...] = ()
    if comparison is not None:
        if rank_by == "temp-prefix":
            # This is a deliberate late-stage ordering. Pool stability is the
            # gate; then a temp lane that remains exact farther through the
            # function wins even when unrelated later rows make words worse.
            # ``None`` means the lane never diverged, so it sorts ahead of any
            # finite row. Shape-incompatible candidates remain behind the
            # population for which the prefix comparison is meaningful.
            temp_row = comparison.temp_prefix_exact
            metric = (
                comparison.alignment_method != "positional-opcode",
                not comparison.pool_exact,
                temp_row is not None,
                -(
                    temp_row
                    if temp_row is not None
                    else comparison.target_instructions + 1
                ),
                comparison.word_mismatches,
                comparison.aligned_total,
                comparison.candidate,
            )
        elif rank_by == "words":
            metric = comparison.raw_sort_key
        else:
            metric = comparison.raw_sort_key if by_raw else comparison.sort_key
    return (
        comparison is None,
        *signal_key,
        *region_key,
        metric,
        result.source,
    )


def sort_campaign_results_key(
    results: Sequence[CompileResult],
    *,
    rank_by: str = "auto",
) -> Callable[[CompileResult], tuple[object, ...]]:
    """Return the ordering key this result set can honestly be sorted on."""

    by_raw = any(
        not result.comparison.alignment_comparable
        for result in results
        if result.comparison is not None
    )
    return lambda result: campaign_result_sort_key(
        result,
        by_raw=by_raw,
        rank_by=rank_by,
    )


def group_object_basins(
    results: Iterable[CompileResult], *, rank_by: str = "auto"
) -> list[list[CompileResult]]:
    """Group successful variants that compiled to the same function bytes.

    Source-equivalent experiments often look different while collapsing to one
    allocator basin. Reporting that collapse prevents a campaign from
    overstating how many independent ideas it actually tested.
    """

    materialized = list(results)
    result_key = sort_campaign_results_key(materialized, rank_by=rank_by)
    buckets: dict[str, list[CompileResult]] = {}
    for result in materialized:
        comparison = result.comparison
        if comparison is None:
            continue
        buckets.setdefault(comparison.candidate_sha256, []).append(result)
    grouped = list(buckets.values())
    for basin in grouped:
        basin.sort(key=result_key)
    grouped.sort(
        key=lambda basin: (
            result_key(basin[0]),
            basin[0].comparison.candidate_sha256 if basin[0].comparison else "",
        )
    )
    return grouped
