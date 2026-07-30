"""No-candidate compiler wrapper and toolchain preflight."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from .artifacts import DEFAULT_STREAM_LIMIT, capture_streams
from .campaign import (
    CompilerTimeoutError,
    executable_identity,
    file_sha256,
    render_compile_command,
    run_compiler,
)
from .objdump import dump_object

PREFLIGHT_SOURCE = (
    "int decomp_workbench_preflight(int value) {\n    return value + 1;\n}\n"
)


def compile_preflight(
    template: str,
    *,
    compile_cwd: str | Path,
    environment: dict[str, str],
    timeout: float,
    objdump: str | None,
    section: str = ".text",
    stream_limit: int = DEFAULT_STREAM_LIMIT,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compile a disposable microcase and verify that its object is readable."""

    if timeout <= 0:
        raise ValueError("--timeout must be positive")
    cwd = Path(compile_cwd).expanduser().resolve()
    if not cwd.is_dir():
        raise NotADirectoryError(f"compiler working directory does not exist: {cwd}")
    with tempfile.TemporaryDirectory(prefix="decomp-workbench-preflight-") as temporary:
        root = Path(temporary)
        source = root / "preflight.c"
        output = root / "preflight.o"
        source.write_text(PREFLIGHT_SOURCE, encoding="utf-8")
        command = render_compile_command(template, source, output)
        started = time.monotonic()
        try:
            process = run_compiler(
                command,
                environment=environment,
                compile_cwd=cwd,
                timeout=timeout,
            )
        except CompilerTimeoutError as error:
            streams = capture_streams(
                error.stdout,
                error.stderr,
                limit=stream_limit,
                artifact_dir=artifact_dir,
                stem="doctor-preflight",
            )
            return {
                "status": "timeout",
                "ready": False,
                "command": command,
                "returncode": 124,
                "duration_seconds": time.monotonic() - started,
                "stdout": streams.stdout,
                "stderr": streams.stderr,
                "stdout_bytes": streams.stdout_bytes,
                "stderr_bytes": streams.stderr_bytes,
                "stdout_truncated": streams.stdout_truncated,
                "stderr_truncated": streams.stderr_truncated,
                "artifacts": streams.artifacts,
                "compiler": executable_identity(command, cwd=cwd),
                "working_directory": str(cwd),
                "explicit_environment": environment,
                "timeout_seconds": timeout,
            }
        streams = capture_streams(
            process.stdout,
            process.stderr,
            limit=stream_limit,
            artifact_dir=artifact_dir,
            stem="doctor-preflight",
        )
        report: dict[str, Any] = {
            "status": "failed" if process.returncode else "compiled",
            "ready": False,
            "command": command,
            "returncode": process.returncode,
            "duration_seconds": time.monotonic() - started,
            "stdout": streams.stdout,
            "stderr": streams.stderr,
            "stdout_bytes": streams.stdout_bytes,
            "stderr_bytes": streams.stderr_bytes,
            "stdout_truncated": streams.stdout_truncated,
            "stderr_truncated": streams.stderr_truncated,
            "artifacts": streams.artifacts,
            "compiler": executable_identity(command, cwd=cwd),
            "working_directory": str(cwd),
            "explicit_environment": environment,
            "timeout_seconds": timeout,
            "object_created": output.is_file(),
            "object_bytes": output.stat().st_size if output.is_file() else 0,
            "object_sha256": file_sha256(output) if output.is_file() else None,
        }
        if process.returncode:
            return report
        if not output.is_file() or output.stat().st_size == 0:
            report["status"] = "missing-object"
            return report
        try:
            _, instructions = dump_object(
                output,
                objdump=objdump,
                symbol="decomp_workbench_preflight",
                section=section,
            )
        except (OSError, RuntimeError, ValueError) as error:
            report["status"] = "unreadable-object"
            report["object_error"] = str(error)
            return report
        report["status"] = "ready"
        report["ready"] = True
        report["instructions"] = len(instructions)
        return report
