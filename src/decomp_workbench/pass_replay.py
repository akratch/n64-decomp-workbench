"""Safe retained-listing edits and IDO as0/as1 pass replay."""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


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
            raise ValueError(
                f"listing pattern did not match: {edit.pattern!r}"
            )
        if len(matches) != 1 and not allow_multiple:
            raise ValueError(
                f"listing pattern matched {len(matches)} times: "
                f"{edit.pattern!r}; narrow it or pass --allow-multiple"
            )

        def insert(match: re.Match[str]) -> str:
            line = edit.text
            if line and not line.endswith("\n"):
                line += "\n"
            if edit.position == "before":
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

    values = {
        "{listing}": str(listing),
        "{binasm}": str(binasm),
        "{symtab}": str(symtab),
        "{object}": str(output),
    }
    parts = shlex.split(template)
    required = (
        ("{listing}", "{binasm}")
        if stage == "as0"
        else ("{binasm}", "{object}")
    )
    for placeholder in required:
        if not any(placeholder in part for part in parts):
            raise ValueError(
                f"{stage} command must contain {placeholder}"
            )
    return [
        _replace_placeholders(part, values)
        for part in parts
    ]


def _replace_placeholders(
    value: str, replacements: dict[str, str]
) -> str:
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
) -> ReplayResult:
    """Edit a retained ugen listing and rerun as0 followed by as1."""

    listing_path = Path(listing).expanduser().resolve()
    output_path = Path(output).expanduser().resolve()
    if output_path == listing_path:
        raise ValueError(
            "listing and object output must be different paths"
        )
    source = listing_path.read_text(encoding="utf-8")
    edited = apply_listing_edits(
        source, edits or [], allow_multiple=allow_multiple
    )
    retained_path = (
        Path(keep_work).expanduser().resolve() if keep_work else None
    )
    if retained_path:
        retained_path.mkdir(parents=True, exist_ok=True)
        retained_listing = (retained_path / "replay.s").resolve()
        if retained_listing == listing_path:
            raise ValueError(
                "--keep-work would overwrite the input listing; "
                "choose another directory"
            )

    with tempfile.TemporaryDirectory(
        prefix="decomp-workbench-pass-replay-"
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
        as0 = subprocess.run(
            as0_command, check=False, capture_output=True, text=True
        )
        if as0.returncode:
            detail = as0.stderr.strip() or as0.stdout.strip()
            raise RuntimeError(f"as0 failed ({as0.returncode}): {detail}")
        if not binasm.is_file():
            raise RuntimeError(
                "as0 succeeded but did not create the {binasm} output"
            )
        as1_command = render_stage_command(
            as1_template,
            listing=replay_listing,
            binasm=binasm,
            symtab=symtab,
            output=temporary_object,
            stage="as1",
        )
        as1 = subprocess.run(
            as1_command, check=False, capture_output=True, text=True
        )
        if as1.returncode:
            detail = as1.stderr.strip() or as1.stdout.strip()
            raise RuntimeError(f"as1 failed ({as1.returncode}): {detail}")
        if not temporary_object.is_file():
            raise RuntimeError(
                "as1 succeeded but did not create the {object} output"
            )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(temporary_object, output_path)
        if retained_path:
            for path in (replay_listing, binasm, symtab, temporary_object):
                if path.exists():
                    shutil.copy2(path, retained_path / path.name)

    return ReplayResult(
        as0_command=as0_command,
        as1_command=as1_command,
        as0_stdout=as0.stdout,
        as0_stderr=as0.stderr,
        as1_stdout=as1.stdout,
        as1_stderr=as1.stderr,
        output=str(output_path),
        retained_directory=str(retained_path) if retained_path else None,
    )
