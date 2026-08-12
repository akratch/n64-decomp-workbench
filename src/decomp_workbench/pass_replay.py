"""Safe retained-listing edits and IDO as0/as1 pass replay."""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import DEFAULT_STREAM_LIMIT, capture_streams
from .campaign import CompilerTimeoutError, run_compiler
from .command_line import split_command
from .fidelity import compare_object_fidelity


@dataclass(frozen=True)
class ListingEdit:
    """One regex-addressed listing insertion."""

    position: str
    pattern: str
    text: str


@dataclass(frozen=True)
class ReplayResult:
    """Commands and output from an as0/as1 replay."""

    as0_command: list[str]
    as1_command: list[str]
    as0_stdout: str
    as0_stderr: str
    as1_stdout: str
    as1_stderr: str
    output: str
    retained_directory: str | None
    calibration: dict[str, Any] | None = None
    streams: dict[str, Any] | None = None


def apply_listing_edits(
    source: str,
    edits: list[ListingEdit],
    *,
    allow_multiple: bool = False,
) -> str:
    """Apply validated before/after insertions to a retained listing."""

    result = source
    for edit in edits:
        if edit.position not in {"before", "after"}:
            raise ValueError(f"unsupported listing edit: {edit.position}")
        expression = re.compile(edit.pattern, re.MULTILINE)
        matches = list(expression.finditer(result))
        if not matches:
            raise ValueError(f"listing pattern did not match: {edit.pattern!r}")
        if len(matches) != 1 and not allow_multiple:
            raise ValueError(
                f"listing pattern matched {len(matches)} times: "
                f"{edit.pattern!r}; narrow it or pass --allow-multiple"
            )

        def insert(
            match: re.Match[str],
            text: str = edit.text,
            position: str = edit.position,
        ) -> str:
            line = text
            if line and not line.endswith("\n"):
                line += "\n"
            if position == "before":
                return line + match.group(0)
            matched = match.group(0)
            separator = "" if matched.endswith("\n") else "\n"
            return matched + separator + line

        result = expression.sub(insert, result)
    return result


def render_stage_command(
    template: str,
    *,
    listing: Path,
    binasm: Path,
    symtab: Path,
    output: Path,
    stage: str,
) -> list[str]:
    """Render one pass command without a shell."""

    if stage not in {"as0", "as1"}:
        raise ValueError(f"unsupported pass stage: {stage!r}")
    values = {
        "{listing}": str(listing),
        "{binasm}": str(binasm),
        "{symtab}": str(symtab),
        "{object}": str(output),
    }
    parts = split_command(template)
    required = ("{listing}", "{binasm}") if stage == "as0" else ("{binasm}", "{object}")
    for placeholder in required:
        if not any(placeholder in part for part in parts):
            raise ValueError(f"{stage} command must contain {placeholder}")
    return [_replace_placeholders(part, values) for part in parts]


def _replace_placeholders(value: str, replacements: dict[str, str]) -> str:
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


def replay_as1(
    listing: str | Path,
    output: str | Path,
    *,
    as0_template: str,
    as1_template: str,
    edits: list[ListingEdit] | None = None,
    allow_multiple: bool = False,
    keep_work: str | Path | None = None,
    calibration_object: str | Path | None = None,
    objdump: str | None = None,
    work_root: str | Path | None = None,
    compile_cwd: str | Path | None = None,
    environment: dict[str, str] | None = None,
    timeout: float = 120.0,
    stream_limit: int = DEFAULT_STREAM_LIMIT,
    artifact_dir: str | Path | None = None,
) -> ReplayResult:
    """Edit a retained ugen listing and rerun as0 followed by as1."""

    listing_path = Path(listing).expanduser().resolve()
    output_path = Path(output).expanduser().resolve()
    if output_path == listing_path:
        raise ValueError("listing and object output must be different paths")
    if timeout <= 0:
        raise ValueError("--timeout must be positive")
    if edits and calibration_object is None:
        raise ValueError(
            "edited replay requires --calibration-object from the normal "
            "unedited pipeline"
        )
    source = listing_path.read_text(encoding="utf-8")
    edited = apply_listing_edits(source, edits or [], allow_multiple=allow_multiple)
    retained_path = Path(keep_work).expanduser().resolve() if keep_work else None
    if retained_path:
        retained_path.mkdir(parents=True, exist_ok=True)
        retained_listing = (retained_path / "replay.s").resolve()
        if retained_listing == listing_path:
            raise ValueError(
                "--keep-work would overwrite the input listing; "
                "choose another directory"
            )

    cwd = (
        Path(compile_cwd).expanduser().resolve()
        if compile_cwd
        else Path.cwd().resolve()
    )
    if not cwd.is_dir():
        raise NotADirectoryError(f"pass working directory does not exist: {cwd}")
    work_parent = Path(work_root).expanduser().resolve() if work_root else None
    if work_parent:
        work_parent.mkdir(parents=True, exist_ok=True)
    calibration: dict[str, Any] | None = None
    if calibration_object is not None and edits:
        with tempfile.TemporaryDirectory(
            prefix="decomp-workbench-pass-control-",
            dir=work_parent,
        ) as control_temporary:
            control_output = Path(control_temporary) / "control.o"
            replay_as1(
                listing_path,
                control_output,
                as0_template=as0_template,
                as1_template=as1_template,
                work_root=work_parent,
                compile_cwd=cwd,
                environment=environment,
                timeout=timeout,
                stream_limit=stream_limit,
            )
            calibration = compare_object_fidelity(
                calibration_object,
                control_output,
                objdump=objdump,
            )
            if not calibration["pass"]:
                raise ValueError(
                    "unedited replay failed section-scoped calibration; "
                    "edited evidence would be ambiguous"
                )

    with tempfile.TemporaryDirectory(
        prefix="decomp-workbench-pass-replay-",
        dir=work_parent,
    ) as temporary:
        work = Path(temporary)
        replay_listing = work / "replay.s"
        binasm = work / "replay.G"
        symtab = work / "replay.T"
        temporary_object = work / "replay.o"
        replay_listing.write_text(edited, encoding="utf-8")
        as0_command = render_stage_command(
            as0_template,
            listing=replay_listing,
            binasm=binasm,
            symtab=symtab,
            output=temporary_object,
            stage="as0",
        )
        try:
            as0 = run_compiler(
                as0_command,
                environment=environment or {},
                compile_cwd=cwd,
                timeout=timeout,
            )
        except CompilerTimeoutError as error:
            raise RuntimeError(f"as0 {error}") from error
        if as0.returncode:
            detail = as0.stderr.strip() or as0.stdout.strip()
            raise RuntimeError(f"as0 failed ({as0.returncode}): {detail}")
        if not binasm.is_file():
            raise RuntimeError(f"as0 succeeded but did not create {binasm}")
        as1_command = render_stage_command(
            as1_template,
            listing=replay_listing,
            binasm=binasm,
            symtab=symtab,
            output=temporary_object,
            stage="as1",
        )
        try:
            as1 = run_compiler(
                as1_command,
                environment=environment or {},
                compile_cwd=cwd,
                timeout=timeout,
            )
        except CompilerTimeoutError as error:
            raise RuntimeError(f"as1 {error}") from error
        if as1.returncode:
            detail = as1.stderr.strip() or as1.stdout.strip()
            raise RuntimeError(f"as1 failed ({as1.returncode}): {detail}")
        if not temporary_object.is_file():
            raise RuntimeError(f"as1 succeeded but did not create {temporary_object}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(temporary_object, output_path)
        if retained_path:
            for path in (replay_listing, binasm, symtab, temporary_object):
                if path.exists():
                    shutil.copy2(path, retained_path / path.name)

    as0_streams = capture_streams(
        as0.stdout,
        as0.stderr,
        limit=stream_limit,
        artifact_dir=artifact_dir,
        stem="replay-as0",
    )
    as1_streams = capture_streams(
        as1.stdout,
        as1.stderr,
        limit=stream_limit,
        artifact_dir=artifact_dir,
        stem="replay-as1",
    )
    return ReplayResult(
        as0_command=as0_command,
        as1_command=as1_command,
        as0_stdout=as0_streams.stdout,
        as0_stderr=as0_streams.stderr,
        as1_stdout=as1_streams.stdout,
        as1_stderr=as1_streams.stderr,
        output=str(output_path),
        retained_directory=str(retained_path) if retained_path else None,
        calibration=calibration,
        streams={
            "as0": {
                "stdout_bytes": as0_streams.stdout_bytes,
                "stderr_bytes": as0_streams.stderr_bytes,
                "stdout_truncated": as0_streams.stdout_truncated,
                "stderr_truncated": as0_streams.stderr_truncated,
                "artifacts": as0_streams.artifacts,
            },
            "as1": {
                "stdout_bytes": as1_streams.stdout_bytes,
                "stderr_bytes": as1_streams.stderr_bytes,
                "stdout_truncated": as1_streams.stdout_truncated,
                "stderr_truncated": as1_streams.stderr_truncated,
                "artifacts": as1_streams.artifacts,
            },
        },
    )
