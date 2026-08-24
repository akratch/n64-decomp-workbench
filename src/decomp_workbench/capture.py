"""Arg-preserving compiler phase capture around an unmodified IDO root.

A near match that survives to the last word is usually owned by one pass, and
the cheapest way to find out which is to keep every byte that crossed the pass
boundary.  IDO's driver hands its phases temporary files it deletes on exit, so
the inputs and outputs of ``ugen``, ``as0`` and ``as1`` are gone by the time a
build finishes.

This module generates the same wrapper toolchain two campaigns wrote by hand:
a phase-named symlink to one POSIX shell wrapper that copies every *file*
argument before and after a single invocation into a labelled run directory,
alongside the exact ``argv`` and the exit status.  Nothing about the phase is
changed -- the wrapper execs the untouched binary, kept beside it as
``<phase>.real`` -- so a capture build is byte-identical to the normal one.

The run directory layout is deliberately identical to the ad hoc original so
run directories collected before this module existed still read correctly:

``<dest>/captures/<YYYYmmdd-HHMMSS>-<pid>-<phase>/``
    ``argv.txt``      one ``%03d <argument>`` line per argument
    ``status.txt``    the phase's exit status
    ``before-<n>-<basename>``  each file argument as it was on entry
    ``after-<n>-<basename>``   each file argument as it was on exit
    ``phase.txt``, ``cwd.txt``  written by this generator, optional on read
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CAPTURE_SCHEMA = "decomp-workbench-capture-toolchain-v1"
CAPTURE_RUNS_SCHEMA = "decomp-workbench-capture-runs-v1"
CAPTURE_MANIFEST_NAME = "workbench-capture.json"
WRAPPER_NAME = "phase-wrapper"
TOOLCHAIN_DIRECTORY = "toolchain"
CAPTURES_DIRECTORY = "captures"

#: The phases whose boundaries the cef4c endgame actually needed: the Ucode
#: that uopt handed ugen, the Binasm ugen handed as1, and the assembler input
#: as0 built.  Others can be added with ``--phase``.
DEFAULT_PHASES: tuple[str, ...] = ("ugen", "as0", "as1")

#: Options whose *next* argument is a value rather than another option. IDO's
#: phases glue short values (``-p0``) and separate these.
VALUE_OPTIONS: frozenset[str] = frozenset({"-o", "-t", "-temp", "-l", "-G"})

#: Which role each value option names, for the argv summary and for replay.
OPTION_ROLES: dict[str, str] = {
    "-o": "output",
    "-t": "symtab",
    "-temp": "temp",
    "-l": "listing",
}

WRAPPER_TEXT = """#!/bin/sh
# decomp-workbench phase capture wrapper.
#
# Preserve one compiler phase's file arguments around a single invocation.
# The wrapper is invoked through a symlink named for the phase; the untouched
# phase binary lives beside it as "<phase>.real" and is exec'd unchanged, so a
# capture build produces the same bytes as a normal one.
#
# WORKBENCH_CAPTURE_OFF=1   pass straight through, capturing nothing
# WORKBENCH_CAPTURE_ROOT    write run directories here instead of ../captures
set -u

tool_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
phase=$(basename "$0")
real_tool="$tool_dir/$phase.real"

if [ ! -x "$real_tool" ]
then
    echo "capture wrapper: no real phase binary at $real_tool" >&2
    exit 127
fi

if [ "${WORKBENCH_CAPTURE_OFF:-0}" = "1" ]
then
    exec "$real_tool" "$@"
fi

capture_root=${WORKBENCH_CAPTURE_ROOT:-}
if [ -z "$capture_root" ]
then
    capture_root=$(CDPATH= cd -- "$tool_dir/.." && pwd)/captures
fi
mkdir -p "$capture_root"

run_dir="$capture_root/$(date +%Y%m%d-%H%M%S)-$$-$phase"
mkdir -p "$run_dir"
printf '%s\\n' "$phase" > "$run_dir/phase.txt"
pwd > "$run_dir/cwd.txt"
: > "$run_dir/argv.txt"

arg_index=0
for arg in "$@"
do
    arg_index=$((arg_index + 1))
    printf '%03d %s\\n' "$arg_index" "$arg" >> "$run_dir/argv.txt"
    if [ -f "$arg" ]
    then
        cp -p "$arg" "$run_dir/before-$arg_index-$(basename "$arg")"
    fi
done

"$real_tool" "$@"
status=$?

arg_index=0
for arg in "$@"
do
    arg_index=$((arg_index + 1))
    if [ -f "$arg" ]
    then
        cp -p "$arg" "$run_dir/after-$arg_index-$(basename "$arg")"
    fi
done
printf '%d\\n' "$status" > "$run_dir/status.txt"
exit "$status"
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _make_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@dataclass(frozen=True)
class CapturedArgv:
    """One phase invocation's arguments, split into roles.

    ``inputs`` are the positional file arguments; ``roles`` maps ``output``,
    ``symtab``, ``temp`` and ``listing`` to the argument each option named.
    Every entry carries the argument's one-based index so it can be joined to
    the ``before-<index>-`` / ``after-<index>-`` files the wrapper retained.
    """

    argv: tuple[str, ...]
    inputs: tuple[tuple[int, str], ...]
    roles: dict[str, tuple[int, str]]
    flags: tuple[str, ...]

    def index_of(self, role: str) -> int | None:
        entry = self.roles.get(role)
        return None if entry is None else entry[0]

    def value_of(self, role: str) -> str | None:
        entry = self.roles.get(role)
        return None if entry is None else entry[1]

    def summary(self) -> str:
        parts = [f"{Path(value).name}" for _index, value in self.inputs]
        for role in ("output", "symtab", "temp", "listing"):
            entry = self.roles.get(role)
            if entry is not None:
                parts.append(f"{role}={Path(entry[1]).name}")
        return " ".join(parts) if parts else "(no file arguments)"

    def as_dict(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv),
            "inputs": [
                {"index": index, "value": value} for index, value in self.inputs
            ],
            "roles": {
                role: {"index": index, "value": value}
                for role, (index, value) in sorted(self.roles.items())
            },
            "flags": list(self.flags),
            "summary": self.summary(),
        }


def parse_phase_argv(argv: Sequence[str]) -> CapturedArgv:
    """Split one phase command line into inputs, named roles, and flags."""

    inputs: list[tuple[int, str]] = []
    roles: dict[str, tuple[int, str]] = {}
    flags: list[str] = []
    pending: str | None = None
    for index, argument in enumerate(argv, start=1):
        if pending is not None:
            role = OPTION_ROLES.get(pending)
            if role is not None:
                roles[role] = (index, argument)
            else:
                flags.append(f"{pending} {argument}")
            pending = None
            continue
        if argument in VALUE_OPTIONS:
            pending = argument
            continue
        if argument.startswith("-"):
            flags.append(argument)
            continue
        inputs.append((index, argument))
    if pending is not None:
        flags.append(pending)
    return CapturedArgv(
        argv=tuple(argv),
        inputs=tuple(inputs),
        roles=roles,
        flags=tuple(flags),
    )


def read_argv_file(path: str | Path) -> tuple[str, ...]:
    """Read the wrapper's ``%03d <argument>`` argv listing in order.

    An argument may contain spaces, so only the fixed-width index and its one
    separating space are removed. Lines are sorted by the recorded index rather
    than by file order so a hand-edited file cannot silently reorder argv.
    """

    source = Path(path)
    if not source.is_file():
        return ()
    entries: list[tuple[int, str]] = []
    for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line:
            continue
        index_text, separator, value = line.partition(" ")
        if not separator or not index_text.isdigit():
            raise ValueError(f"{source}: malformed argv line: {line!r}")
        entries.append((int(index_text), value))
    entries.sort(key=lambda item: item[0])
    return tuple(value for _index, value in entries)


def make_capture_toolchain(
    source: str | Path,
    destination: str | Path,
    *,
    phases: Iterable[str] = DEFAULT_PHASES,
    link: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Generate an arg-preserving wrapper toolchain around one IDO root."""

    root = Path(source).expanduser().resolve()
    dest = Path(destination).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"IDO root is not a directory: {root}")
    if dest == root or root in dest.parents:
        raise ValueError("destination must not be inside the IDO root")
    wanted = tuple(dict.fromkeys(phases))
    if not wanted:
        raise ValueError("at least one phase must be wrapped")
    missing = [phase for phase in wanted if not (root / phase).is_file()]
    if missing:
        available = ", ".join(sorted(item.name for item in root.iterdir())) or "nothing"
        raise FileNotFoundError(
            f"IDO root {root} has no {', '.join(missing)}; it contains {available}"
        )

    toolchain = dest / TOOLCHAIN_DIRECTORY
    captures = dest / CAPTURES_DIRECTORY
    if toolchain.exists():
        if not force:
            raise FileExistsError(
                f"refusing to overwrite an existing capture toolchain: {toolchain} "
                "(pass --force to replace it; collected captures are kept)"
            )
        shutil.rmtree(toolchain)
    toolchain.mkdir(parents=True)
    captures.mkdir(parents=True, exist_ok=True)

    carried: list[dict[str, Any]] = []
    aliases: list[str] = []
    for entry in sorted(root.iterdir()):
        target = toolchain / entry.name
        if entry.is_symlink() and not entry.is_file() and not entry.is_dir():
            # A dangling link carries no phase; record it and move on.
            carried.append({"name": entry.name, "carried": "skipped-dangling-symlink"})
            continue
        if entry.is_symlink() and entry.resolve() == root:
            # An IDO root commonly carries a version self-alias (`7.1 -> .`).
            # Carrying it verbatim would point the capture toolchain back at
            # the stock root, so a build addressing `$(TOOLROOT)/7.1/ugen`
            # would silently bypass every wrapper.
            target.symlink_to(".")
            aliases.append(entry.name)
            carried.append({"name": entry.name, "carried": "self-alias"})
            continue
        if entry.name in wanted:
            # The real phase binary moves aside; the wrapper takes its name.
            real = toolchain / f"{entry.name}.real"
            _carry(entry, real, link=link)
            if not real.is_symlink():
                # Never chmod through a link: the target is the user's own
                # read-only IDO root.
                _make_executable(real)
            carried.append(
                {
                    "name": entry.name,
                    "carried": "wrapped",
                    "real": real.name,
                    "bytes": entry.stat().st_size,
                    "sha256": _sha256(entry),
                }
            )
            continue
        _carry(entry, target, link=link)
        carried.append(
            {
                "name": entry.name,
                "carried": "symlink" if link else "copy",
                "bytes": entry.stat().st_size if entry.is_file() else None,
            }
        )

    wrapper = toolchain / WRAPPER_NAME
    wrapper.write_text(WRAPPER_TEXT, encoding="utf-8")
    _make_executable(wrapper)
    for phase in wanted:
        link_path = toolchain / phase
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()
        link_path.symlink_to(WRAPPER_NAME)

    # IDO builds routinely address the toolchain through a version directory
    # (``$(TOOLROOT)/7.1/ugen``). A self-alias keeps such a command line
    # working against the capture copy without editing the project's build.
    alias = root.name
    if alias and alias not in aliases and not (toolchain / alias).exists():
        (toolchain / alias).symlink_to(".")
        aliases.append(alias)

    manifest = {
        "schema": CAPTURE_SCHEMA,
        "created_at_unix": time.time(),
        "source": str(root),
        "destination": str(dest),
        "toolchain": str(toolchain),
        "captures": str(captures),
        "carry_mode": "symlink" if link else "copy",
        "wrapped_phases": list(wanted),
        "wrapper": {
            "name": WRAPPER_NAME,
            "sha256": _sha256(wrapper),
        },
        "self_aliases": aliases,
        "entries": carried,
        "usage": (
            f"point the project's compiler root at {toolchain} and build one "
            "translation unit; every wrapped phase leaves one run directory "
            f"under {captures}. Set WORKBENCH_CAPTURE_OFF=1 to pass through."
        ),
        "proof": (
            "The wrapper execs the untouched phase binary and only copies file "
            "arguments, so a capture build is byte-identical to a normal one. "
            "It does not prove anything by itself; it retains the evidence."
        ),
    }
    (dest / CAPTURE_MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def _carry(source: Path, target: Path, *, link: bool) -> None:
    """Place one IDO root entry into the capture toolchain."""

    if link:
        if target.exists() or target.is_symlink():
            target.unlink()
        target.symlink_to(source)
        return
    if source.is_dir():
        shutil.copytree(source, target, symlinks=False, dirs_exist_ok=True)
        return
    shutil.copy2(source, target, follow_symlinks=True)


def resolve_toolchain(root: str | Path) -> Path:
    """Accept either a capture destination or the toolchain directory itself."""

    path = Path(root).expanduser().resolve()
    nested = path / TOOLCHAIN_DIRECTORY
    if nested.is_dir():
        return nested
    return path


def resolve_captures(root: str | Path) -> Path:
    """Accept either a capture destination or the captures directory itself."""

    path = Path(root).expanduser().resolve()
    nested = path / CAPTURES_DIRECTORY
    if nested.is_dir():
        return nested
    if path.is_dir():
        return path
    raise NotADirectoryError(f"no capture directory at {path}")


def stock_phase_binary(toolchain: str | Path, phase: str) -> Path:
    """Return the untouched phase binary, preferring ``<phase>.real``.

    Replay must not run through the capture wrapper: doing so would add a run
    directory for every replayed variant and, worse, make the replay's own
    evidence depend on the wrapper it is supposed to be independent of.
    """

    root = resolve_toolchain(toolchain)
    real = root / f"{phase}.real"
    if real.is_file() or real.is_symlink():
        return real
    plain = root / phase
    if plain.is_file() or plain.is_symlink():
        if plain.is_symlink() and Path(os.readlink(plain)).name == WRAPPER_NAME:
            raise FileNotFoundError(
                f"{plain} is a capture wrapper but {real} is missing; "
                "regenerate the toolchain with `capture make`"
            )
        return plain
    raise FileNotFoundError(f"no {phase} binary in {root}")


@dataclass(frozen=True)
class CaptureFile:
    """One retained copy of a phase file argument."""

    role: str
    index: int
    name: str
    path: Path
    size: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "argument_index": self.index,
            "name": self.name,
            "path": str(self.path),
            "bytes": self.size,
        }


@dataclass(frozen=True)
class CaptureRun:
    """One wrapped phase invocation, as retained on disk."""

    run_id: str
    directory: Path
    phase: str
    status: int | None
    argv: CapturedArgv
    files: tuple[CaptureFile, ...]
    cwd: str | None

    @property
    def stream_bytes(self) -> int:
        return sum(item.size for item in self.files)

    def file_for(self, role: str, index: int | None) -> CaptureFile | None:
        """Return one retained copy, or None when the argument had no role."""

        if index is None:
            return None
        for item in self.files:
            if item.role == role and item.index == index:
                return item
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "directory": str(self.directory),
            "phase": self.phase,
            "status": self.status,
            "cwd": self.cwd,
            "argv": self.argv.as_dict(),
            "files": [item.as_dict() for item in self.files],
            "stream_bytes": self.stream_bytes,
            "file_count": len(self.files),
        }


def _run_phase(directory: Path, argv: CapturedArgv) -> str:
    marker = directory / "phase.txt"
    if marker.is_file():
        recorded = marker.read_text(encoding="utf-8").strip()
        if recorded:
            return recorded
    # The original ad hoc wrapper named only ugen runs `<stamp>-<pid>`; the
    # per-phase wrappers appended the phase. Read the suffix when it is there.
    parts = directory.name.split("-")
    if len(parts) >= 3 and not parts[2].isdigit():
        return parts[2]
    if len(parts) >= 4:
        return parts[3]
    # A ugen invocation is the one that names both a -temp and an -o file.
    if argv.value_of("temp") and argv.value_of("output"):
        return "ugen"
    return "unknown"


def read_capture_run(directory: str | Path) -> CaptureRun:
    """Read one retained run directory into a structured record."""

    path = Path(directory).expanduser().resolve()
    if not path.is_dir():
        raise NotADirectoryError(f"capture run is not a directory: {path}")
    argv = parse_phase_argv(read_argv_file(path / "argv.txt"))
    status_path = path / "status.txt"
    status: int | None = None
    if status_path.is_file():
        text = status_path.read_text(encoding="utf-8").strip()
        status = int(text) if text.lstrip("-").isdigit() else None
    cwd_path = path / "cwd.txt"
    cwd = cwd_path.read_text(encoding="utf-8").strip() if cwd_path.is_file() else None
    files: list[CaptureFile] = []
    for entry in sorted(path.iterdir()):
        if not entry.is_file():
            continue
        role, separator, remainder = entry.name.partition("-")
        if not separator or role not in {"before", "after"}:
            continue
        index_text, separator, name = remainder.partition("-")
        if not separator or not index_text.isdigit():
            continue
        files.append(
            CaptureFile(
                role=role,
                index=int(index_text),
                name=name,
                path=entry,
                size=entry.stat().st_size,
            )
        )
    files.sort(key=lambda item: (item.index, item.role))
    return CaptureRun(
        run_id=path.name,
        directory=path,
        phase=_run_phase(path, argv),
        status=status,
        argv=argv,
        files=tuple(files),
        cwd=cwd,
    )


def list_capture_runs(
    root: str | Path,
    *,
    phase: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """List collected runs newest last, with phase, argv, and stream sizes."""

    captures = resolve_captures(root)
    runs: list[CaptureRun] = []
    unreadable: list[dict[str, str]] = []
    for entry in sorted(captures.iterdir()):
        if not entry.is_dir():
            continue
        try:
            run = read_capture_run(entry)
        except (OSError, ValueError) as error:
            # One malformed run directory must not hide the rest of a session.
            unreadable.append({"directory": str(entry), "error": str(error)})
            continue
        if phase is not None and run.phase != phase:
            continue
        runs.append(run)
    total = len(runs)
    if limit is not None and limit >= 0:
        runs = runs[-limit:] if limit else []
    phases: dict[str, int] = {}
    for run in runs:
        phases[run.phase] = phases.get(run.phase, 0) + 1
    return {
        "schema": CAPTURE_RUNS_SCHEMA,
        "captures": str(captures),
        "run_count": total,
        "listed_count": len(runs),
        "phase_counts": dict(sorted(phases.items())),
        "runs": [run.as_dict() for run in runs],
        "unreadable": unreadable,
    }


def find_capture_run(
    root: str | Path,
    *,
    phase: str,
    input_name: str | None = None,
) -> CaptureRun | None:
    """Find the newest run of one phase, optionally by its input basename.

    The as1 run that consumed a given ugen output names that output as its
    positional input, which is the only honest link between the two run
    directories: the temporary names are unique per driver invocation.
    """

    captures = resolve_captures(root)
    best: CaptureRun | None = None
    for entry in sorted(captures.iterdir()):
        if not entry.is_dir():
            continue
        try:
            run = read_capture_run(entry)
        except (OSError, ValueError):
            continue
        if run.phase != phase:
            continue
        if input_name is not None and not any(
            Path(value).name == input_name for _index, value in run.argv.inputs
        ):
            continue
        best = run
    return best
