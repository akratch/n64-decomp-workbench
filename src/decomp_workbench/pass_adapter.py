"""User-supplied original/static pass differential adapter."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from .artifacts import DEFAULT_STREAM_LIMIT, capture_streams
from .campaign import (
    CompilerTimeoutError,
    executable_identity,
    file_sha256,
    run_compiler,
)
from .command_line import split_command

PASS_DIFF_SCHEMA = "decomp-workbench-original-pass-diff-v1"


def render_pass_command(
    template: str,
    *,
    input_path: Path,
    output_path: Path,
    work_path: Path,
) -> list[str]:
    """Render an external pass without a shell or implicit mounts."""

    parts = split_command(template)
    for placeholder in ("{input}", "{output}"):
        if not any(placeholder in part for part in parts):
            raise ValueError(f"pass command must contain {placeholder}")
    replacements = {
        "{input}": str(input_path),
        "{output}": str(output_path),
        "{work}": str(work_path),
    }
    result = []
    for part in parts:
        for old, new in replacements.items():
            part = part.replace(old, new)
        result.append(part)
    return result


def _normalized_hash(path: Path, *, work: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    for spelling in {str(work), os.path.realpath(work)}:
        data = data.replace(spelling.encode("utf-8"), b"{WORK}")
    return hashlib.sha256(data).hexdigest()


def _run_stage(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    timeout: float,
    stream_limit: int,
    artifact_dir: Path,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        process = run_compiler(
            command,
            environment={},
            compile_cwd=cwd,
            timeout=timeout,
        )
        returncode = process.returncode
        stdout = process.stdout
        stderr = process.stderr
    except CompilerTimeoutError as error:
        returncode = 124
        stdout = error.stdout
        stderr = f"{error.stderr}\n{error}".strip()
    streams = capture_streams(
        stdout,
        stderr,
        limit=stream_limit,
        artifact_dir=artifact_dir,
        stem=name,
    )
    return {
        "command": command,
        "executable": executable_identity(command, cwd=cwd),
        "returncode": returncode,
        "duration_seconds": time.monotonic() - started,
        "stdout": streams.stdout,
        "stderr": streams.stderr,
        "stdout_bytes": streams.stdout_bytes,
        "stderr_bytes": streams.stderr_bytes,
        "stdout_truncated": streams.stdout_truncated,
        "stderr_truncated": streams.stderr_truncated,
        "artifacts": streams.artifacts,
    }


def run_pass_differential(
    input_path: str | Path,
    *,
    original_template: str,
    static_template: str,
    boundary: str,
    work_root: str | Path,
    compile_cwd: str | Path,
    timeout: float = 120.0,
    stream_limit: int = DEFAULT_STREAM_LIMIT,
    downstream_template: str | None = None,
) -> dict[str, Any]:
    """Run one retained boundary through original and static passes."""

    if timeout <= 0:
        raise ValueError("--timeout must be positive")
    source = Path(input_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"pass input does not exist: {source}")
    cwd = Path(compile_cwd).expanduser().resolve()
    if not cwd.is_dir():
        raise NotADirectoryError(f"pass working directory does not exist: {cwd}")
    root = Path(work_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix=f"{boundary}-", dir=root))
    original_output = run_dir / "original.out"
    static_output = run_dir / "static.out"
    original_command = render_pass_command(
        original_template,
        input_path=source,
        output_path=original_output,
        work_path=run_dir,
    )
    static_command = render_pass_command(
        static_template,
        input_path=source,
        output_path=static_output,
        work_path=run_dir,
    )
    original = _run_stage(
        "original",
        original_command,
        cwd=cwd,
        timeout=timeout,
        stream_limit=stream_limit,
        artifact_dir=run_dir / "streams",
    )
    static = _run_stage(
        "static",
        static_command,
        cwd=cwd,
        timeout=timeout,
        stream_limit=stream_limit,
        artifact_dir=run_dir / "streams",
    )
    for name, stage, output in (
        ("original", original, original_output),
        ("static", static, static_output),
    ):
        if stage["returncode"]:
            raise RuntimeError(
                f"{name} pass failed with exit {stage['returncode']}: "
                f"{str(stage['stderr']).strip() or 'no diagnostic'}"
            )
        if not output.is_file():
            raise RuntimeError(f"{name} pass did not create {output}")
    downstream = None
    if downstream_template:
        original_final = run_dir / "original.downstream"
        static_final = run_dir / "static.downstream"
        original_downstream_command = render_pass_command(
            downstream_template,
            input_path=original_output,
            output_path=original_final,
            work_path=run_dir,
        )
        static_downstream_command = render_pass_command(
            downstream_template,
            input_path=static_output,
            output_path=static_final,
            work_path=run_dir,
        )
        original_downstream = _run_stage(
            "original-downstream",
            original_downstream_command,
            cwd=cwd,
            timeout=timeout,
            stream_limit=stream_limit,
            artifact_dir=run_dir / "streams",
        )
        static_downstream = _run_stage(
            "static-downstream",
            static_downstream_command,
            cwd=cwd,
            timeout=timeout,
            stream_limit=stream_limit,
            artifact_dir=run_dir / "streams",
        )
        for name, stage, output in (
            ("original downstream", original_downstream, original_final),
            ("static downstream", static_downstream, static_final),
        ):
            if stage["returncode"] or not output.is_file():
                raise RuntimeError(
                    f"{name} failed or did not produce its output "
                    f"(exit {stage['returncode']})"
                )
        downstream = {
            "original": original_downstream,
            "static": static_downstream,
            "original_sha256": file_sha256(original_final),
            "static_sha256": file_sha256(static_final),
            "identical": original_final.read_bytes() == static_final.read_bytes(),
        }
    return {
        "schema": PASS_DIFF_SCHEMA,
        "boundary": boundary,
        "work_directory": str(run_dir),
        "input": str(source),
        "input_sha256": file_sha256(source),
        "original": {
            **original,
            "output": str(original_output),
            "output_sha256": file_sha256(original_output),
            "normalized_sha256": _normalized_hash(original_output, work=run_dir),
        },
        "static": {
            **static,
            "output": str(static_output),
            "output_sha256": file_sha256(static_output),
            "normalized_sha256": _normalized_hash(static_output, work=run_dir),
        },
        "byte_identical": original_output.read_bytes() == static_output.read_bytes(),
        "normalized_identical": (
            _normalized_hash(original_output, work=run_dir)
            == _normalized_hash(static_output, work=run_dir)
        ),
        "downstream": downstream,
        "proof": (
            "One user-supplied pass boundary differential. Instrumentation and "
            "source conclusions require disabled-instrumentation and unedited-"
            "replay calibration plus downstream/collateral gates."
        ),
    }
