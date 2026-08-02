"""Reproducible, upload-neutral decomp.me scratch bundles."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScratchBundleResult:
    """Paths and manifest produced for one local scratch bundle."""

    output: str
    manifest: dict[str, Any]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_input(source: str | Path, destination: Path) -> None:
    input_path = Path(source).expanduser().resolve()
    if not input_path.is_file():
        raise ValueError(f"scratch input is not a file: {input_path}")
    shutil.copyfile(input_path, destination)


def bundle_scratch(
    output: str | Path,
    *,
    target_assembly: str | Path,
    context: str | Path,
    source: str | Path,
    platform: str,
    compiler: str,
    compiler_flags: str,
    diff_label: str,
    project: str | None = None,
    preset: str | None = None,
    compiler_id: str | None = None,
    language: str | None = None,
) -> ScratchBundleResult:
    """Copy scratch inputs and write a deterministic manifest and instructions."""

    required = {
        "platform": platform,
        "compiler": compiler,
        "diff_label": diff_label,
    }
    missing = [name for name, value in required.items() if not value.strip()]
    if missing:
        raise ValueError("scratch metadata cannot be empty: " + ", ".join(missing))

    output_path = Path(output).expanduser().resolve()
    if output_path.exists():
        if not output_path.is_dir():
            raise ValueError(
                f"scratch output exists and is not a directory: {output_path}"
            )
        if any(output_path.iterdir()):
            raise ValueError(f"scratch output directory is not empty: {output_path}")
    else:
        output_path.mkdir(parents=True)

    inputs = {
        "target.s": target_assembly,
        "context.c": context,
        "source.c": source,
    }
    for name, input_path in inputs.items():
        _copy_input(input_path, output_path / name)

    files = {name: {"sha256": _sha256(output_path / name)} for name in sorted(inputs)}
    decomp_me: dict[str, str] = {
        "platform": platform,
        "compiler": compiler,
        "compiler_flags": compiler_flags,
        "diff_label": diff_label,
    }
    if preset:
        decomp_me["preset"] = preset
    if compiler_id:
        decomp_me["compiler_id"] = compiler_id
    if language:
        decomp_me["language"] = language
    manifest: dict[str, Any] = {
        "schema": "decomp-workbench-scratch-bundle-v1",
        "decomp_me": decomp_me,
        "files": files,
    }
    if project:
        manifest["project"] = project

    (output_path / "scratch.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    checksums = "".join(
        f"{metadata['sha256']}  {name}\n" for name, metadata in files.items()
    )
    (output_path / "SHA256SUMS").write_text(checksums, encoding="utf-8")
    (output_path / "README.md").write_text(
        _bundle_readme(manifest),
        encoding="utf-8",
    )
    return ScratchBundleResult(output=str(output_path), manifest=manifest)


def _bundle_readme(manifest: dict[str, Any]) -> str:
    settings = manifest["decomp_me"]
    preset = settings.get("preset")
    compiler_id = settings.get("compiler_id")
    language = settings.get("language")
    identity = f" (canonical compiler id `{compiler_id}`)" if compiler_id else ""
    language_step = f"\n5. Verify the language is `{language}`." if language else ""
    if preset:
        selection = f"""3. Select preset `{preset}`.
4. Under **Compiler options**, verify compiler `{settings["compiler"]}`{identity};
   presets can silently select a different frontend even when their names look
   similar.{language_step}"""
    else:
        compiler_line = (
            "4. Under **Compiler options**, select compiler "
            f"`{settings['compiler']}`{identity}."
        )
        selection = f"""3. Set **Preset** to **Custom**.
{compiler_line}{language_step}"""
    project = manifest.get("project")
    project_line = f"\nProject: `{project}`.\n" if project else ""
    return f"""# decomp.me scratch bundle
{project_line}
This directory is upload-neutral: creating it does not contact decomp.me.

1. Open <https://www.decomp.me/new>.
2. Select platform `{settings["platform"]}`.
{selection}

Then use diff label `{settings["diff_label"]}`, paste `target.s` into **Target
assembly**, paste `context.c` into **Context**, create the scratch, and paste
`source.c` into the source editor.

If a preset was not selected, use these compiler flags:

   ```text
   {settings["compiler_flags"]}
   ```

Run `shasum -a 256 -c SHA256SUMS` before sharing to verify the three copied
inputs. `scratch.json` contains the same settings and content identities in a
machine-readable form.
"""
