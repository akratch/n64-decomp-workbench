"""Safe retained-listing edits and IDO as0/as1/ugen pass replay."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import DEFAULT_STREAM_LIMIT, capture_streams
from .campaign import (
    CompilerTimeoutError,
    file_sha256,
    nice_prefix,
    run_compiler,
)
from .capture import (
    CaptureRun,
    find_capture_run,
    read_capture_run,
    stock_phase_binary,
)
from .command_line import split_command
from .fidelity import compare_object_fidelity

UGEN_REPLAY_SCHEMA = "decomp-workbench-replay-ugen-v1"


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


def _rebuild_argv(
    run: CaptureRun,
    *,
    input_path: Path,
    replacements: dict[str, Path],
) -> list[str]:
    """Rewrite one captured argv, keeping every flag in its original place.

    Only the *file* arguments move: the positional input becomes the stream
    being replayed and each named role becomes a path inside the work
    directory. Every optimization flag, target flag and driver quirk survives
    verbatim, which is the whole point of replaying against a capture instead
    of a reconstructed command line.
    """

    by_index: dict[int, str] = {}
    for index, _value in run.argv.inputs:
        by_index[index] = str(input_path)
        break
    for role, path in replacements.items():
        role_index = run.argv.index_of(role)
        if role_index is not None:
            by_index[role_index] = str(path)
    argv = [
        by_index.get(index, value) for index, value in enumerate(run.argv.argv, start=1)
    ]
    if not run.argv.inputs:
        argv.append(str(input_path))
    for role, option in (("output", "-o"), ("symtab", "-t"), ("temp", "-temp")):
        if role in replacements and run.argv.index_of(role) is None:
            argv.extend([option, str(replacements[role])])
    return argv


def _replay_environment(overrides: dict[str, str] | None) -> dict[str, str]:
    """Build the phase environment: the host's, plus capture suppressed.

    A replay must never write a capture run directory of its own: it runs the
    stock ``<phase>.real`` binary, and the variable is belt-and-braces for a
    toolchain whose wrapper someone pointed at directly.
    """

    environment = dict(os.environ)
    environment["WORKBENCH_CAPTURE_OFF"] = "1"
    environment.update(overrides or {})
    return environment


def replay_ugen(
    ucode: str | Path,
    *,
    toolchain: str | Path,
    argv_from: str | Path,
    output: str | Path | None = None,
    as1_argv_from: str | Path | None = None,
    expect: str | Path | None = None,
    run_as1: bool = True,
    keep_work: str | Path | None = None,
    work_root: str | Path | None = None,
    compile_cwd: str | Path | None = None,
    environment: dict[str, str] | None = None,
    timeout: float = 300.0,
    nice: int | None = 10,
    objdump: str | None = None,
    stream_limit: int = DEFAULT_STREAM_LIMIT,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Replay one Ucode stream through stock ugen and as1 using captured argv.

    The fidelity gate this exists for: replaying a capture's own unmodified
    Ucode must reproduce that capture's object byte for byte. Until that holds,
    a patched variant's object difference could belong to the replay harness
    rather than to the patch.
    """

    stream = Path(ucode).expanduser().resolve()
    if not stream.is_file():
        raise FileNotFoundError(f"Ucode stream does not exist: {stream}")
    if timeout <= 0:
        raise ValueError("--timeout must be positive")
    ugen_run = read_capture_run(argv_from)
    if ugen_run.phase not in {"ugen", "unknown"}:
        raise ValueError(
            f"{ugen_run.directory} is a {ugen_run.phase} run; "
            "--argv-from wants the ugen run whose argv shape to reuse"
        )
    ugen_binary = stock_phase_binary(toolchain, "ugen")

    as1_run: CaptureRun | None = None
    as1_discovery = "not requested"
    if run_as1:
        if as1_argv_from is not None:
            as1_run = read_capture_run(as1_argv_from)
            as1_discovery = "explicit --as1-argv-from"
        else:
            binasm_name = ugen_run.argv.value_of("output")
            as1_run = find_capture_run(
                ugen_run.directory.parent,
                phase="as1",
                input_name=Path(binasm_name).name if binasm_name else None,
            )
            as1_discovery = (
                "matched the as1 run whose positional input is this ugen run's -o file"
                if as1_run is not None
                else "no as1 run consumed this ugen run's output"
            )
        if as1_run is None:
            raise ValueError(
                "no as1 capture run consumes this ugen run's output; pass "
                "--as1-argv-from <run-dir>, or --skip-as1 to stop at Binasm"
            )
    as1_binary = stock_phase_binary(toolchain, "as1") if run_as1 else None

    work_parent = Path(work_root).expanduser().resolve() if work_root else None
    if work_parent:
        work_parent.mkdir(parents=True, exist_ok=True)
    cwd = (
        Path(compile_cwd).expanduser().resolve()
        if compile_cwd
        else Path.cwd().resolve()
    )
    if not cwd.is_dir():
        raise NotADirectoryError(f"pass working directory does not exist: {cwd}")
    retained = Path(keep_work).expanduser().resolve() if keep_work else None
    if retained:
        retained.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "schema": UGEN_REPLAY_SCHEMA,
        "ucode": {
            "path": str(stream),
            "bytes": stream.stat().st_size,
            "sha256": file_sha256(stream),
        },
        "toolchain": str(Path(toolchain).expanduser().resolve()),
        "ugen_binary": str(ugen_binary),
        "as1_binary": str(as1_binary) if as1_binary else None,
        "argv_source": {
            "ugen_run": str(ugen_run.directory),
            "as1_run": str(as1_run.directory) if as1_run else None,
            "as1_discovery": as1_discovery,
        },
    }

    with tempfile.TemporaryDirectory(
        prefix="decomp-workbench-replay-ugen-", dir=work_parent
    ) as temporary:
        work = Path(temporary)
        binasm = work / "replay.G"
        symtab = work / "replay.T"
        ugen_temp = work / "replay.temp"
        listing = work / "replay.s"

        # ugen mutates the symbol table in place and as1 reads what ugen left,
        # so the replay starts from the *entry* copy the wrapper retained and
        # hands the same file to both phases -- exactly as the driver did.
        symtab_index = ugen_run.argv.index_of("symtab")
        seed = (
            ugen_run.file_for("before", symtab_index)
            if symtab_index is not None
            else None
        )
        if seed is not None:
            shutil.copy2(seed.path, symtab)
            report["symtab_seed"] = str(seed.path)
        else:
            symtab.write_bytes(b"")
            report["symtab_seed"] = None
            report.setdefault("warnings", []).append(
                "the ugen run retained no entry symbol table; replaying with an "
                "empty one, which is only right for a self-contained stream"
            )

        replacements = {"output": binasm, "symtab": symtab, "temp": ugen_temp}
        if ugen_run.argv.index_of("listing") is not None:
            replacements["listing"] = listing
        ugen_command = [
            *nice_prefix(nice),
            str(ugen_binary),
            *_rebuild_argv(ugen_run, input_path=stream, replacements=replacements),
        ]
        report["ugen_command"] = ugen_command
        try:
            ugen = run_compiler(
                ugen_command,
                environment=_replay_environment(environment),
                compile_cwd=cwd,
                timeout=timeout,
            )
        except CompilerTimeoutError as error:
            raise RuntimeError(f"ugen {error}") from error
        ugen_streams = capture_streams(
            ugen.stdout,
            ugen.stderr,
            limit=stream_limit,
            artifact_dir=artifact_dir,
            stem="replay-ugen",
        )
        report["ugen"] = {
            "returncode": ugen.returncode,
            "stdout": ugen_streams.stdout,
            "stderr": ugen_streams.stderr,
        }
        if ugen.returncode:
            detail = ugen.stderr.strip() or ugen.stdout.strip()
            raise RuntimeError(f"ugen failed ({ugen.returncode}): {detail}")
        if not binasm.is_file():
            raise RuntimeError(f"ugen succeeded but did not create {binasm}")
        report["binasm"] = {
            "bytes": binasm.stat().st_size,
            "sha256": file_sha256(binasm),
        }

        object_path = (
            Path(output).expanduser().resolve() if output is not None else None
        )
        if run_as1 and as1_run is not None and as1_binary is not None:
            replay_object = work / "replay.o"
            as1_replacements: dict[str, Path] = {
                "output": replay_object,
                "symtab": symtab,
            }
            as1_command = [
                *nice_prefix(nice),
                str(as1_binary),
                *_rebuild_argv(
                    as1_run, input_path=binasm, replacements=as1_replacements
                ),
            ]
            report["as1_command"] = as1_command
            try:
                as1 = run_compiler(
                    as1_command,
                    environment=_replay_environment(environment),
                    compile_cwd=cwd,
                    timeout=timeout,
                )
            except CompilerTimeoutError as error:
                raise RuntimeError(f"as1 {error}") from error
            as1_streams = capture_streams(
                as1.stdout,
                as1.stderr,
                limit=stream_limit,
                artifact_dir=artifact_dir,
                stem="replay-as1",
            )
            report["as1"] = {
                "returncode": as1.returncode,
                "stdout": as1_streams.stdout,
                "stderr": as1_streams.stderr,
            }
            if as1.returncode:
                detail = as1.stderr.strip() or as1.stdout.strip()
                raise RuntimeError(f"as1 failed ({as1.returncode}): {detail}")
            if not replay_object.is_file():
                raise RuntimeError(f"as1 succeeded but did not create {replay_object}")
            report["object"] = {
                "bytes": replay_object.stat().st_size,
                "sha256": file_sha256(replay_object),
            }
            report["verification"] = _verify_replay_object(
                replay_object,
                as1_run=as1_run,
                expect=expect,
                objdump=objdump,
            )
            if object_path is not None:
                object_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(replay_object, object_path)
                report["object"]["path"] = str(object_path)
        elif object_path is not None:
            # Without as1 the only product is the Binasm stream; write it where
            # the caller asked for a product rather than silently dropping it.
            object_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(binasm, object_path)
            report["binasm"]["path"] = str(object_path)

        if retained:
            for path in (stream, binasm, symtab, ugen_temp, listing):
                if path.exists() and path.parent != retained:
                    shutil.copy2(path, retained / path.name)
            report["retained_directory"] = str(retained)

    report["proof"] = (
        "Stock ugen and as1 ran on a retained stream with the captured argv "
        "shape. Reproducing the capture's object byte for byte establishes the "
        "replay itself is faithful; a patched variant's object difference is "
        "then attributable to the patch, and to no C spelling."
    )
    return report


def _verify_replay_object(
    replayed: Path,
    *,
    as1_run: CaptureRun,
    expect: str | Path | None,
    objdump: str | None,
) -> dict[str, Any]:
    """Compare the replayed object with the capture's own object, if retained."""

    reference: Path | None = None
    source = "none"
    if expect is not None:
        reference = Path(expect).expanduser().resolve()
        source = "--expect"
    else:
        output_index = as1_run.argv.index_of("output")
        retained = (
            as1_run.file_for("after", output_index)
            if output_index is not None
            else None
        )
        if retained is not None:
            reference = retained.path
            source = "as1 capture run's retained output object"
    if reference is None or not reference.is_file():
        return {
            "reference": None,
            "reference_source": source,
            "byte_identical": None,
            "verdict": (
                "not verified: no reference object. Re-run the capture so the "
                "as1 run retains its -o file, or pass --expect."
            ),
        }
    replayed_hash = file_sha256(replayed)
    reference_hash = file_sha256(reference)
    identical = replayed_hash == reference_hash
    result: dict[str, Any] = {
        "reference": str(reference),
        "reference_source": source,
        "reference_sha256": reference_hash,
        "replayed_sha256": replayed_hash,
        "byte_identical": identical,
        "verdict": (
            "replay reproduces the reference object byte for byte"
            if identical
            else "replay differs from the reference object"
        ),
    }
    if not identical:
        # A hash difference alone cannot say whether the code changed or only
        # a timestamp/comment section did; the fidelity report can.
        try:
            result["fidelity"] = compare_object_fidelity(
                reference, replayed, objdump=objdump
            )
        except (OSError, RuntimeError, ValueError) as error:
            result["fidelity_error"] = str(error)
    return result
