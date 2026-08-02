"""Safe, upload-neutral inspection of decomp.me exports and workbench bundles."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shlex
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .context_lint import analyze_expression, file_scope_definitions, lint_sources

MAX_FILES = 64
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024

DECOMP_ME_METADATA = "metadata.json"
WORKBENCH_MANIFEST = "scratch.json"
SITE_SOURCE_MARKER = '#line 1 "src.c"\n'
SITE_CXX_SOURCE_MARKER = '#line 1 "src.cxx"\n'

#: How much of ctx.c's tail to show when it will glue onto code.c's first
#: line. Long enough to recognize the statement; short enough for one line.
CONTEXT_GLUE_TAIL = 40


@dataclass(frozen=True)
class ScratchPackage:
    """One validated scratch export held in memory.

    ZIP members are never extracted. Keeping the small, bounded export in
    memory makes path traversal impossible and gives directories and ZIPs the
    same validation path.
    """

    path: Path
    kind: str
    files: dict[str, bytes]
    metadata: dict[str, Any]
    checksums_valid: bool | None

    def text(self, name: str) -> str:
        """Decode one required text member as UTF-8."""

        try:
            content = self.files[name]
        except KeyError as error:
            raise ValueError(f"scratch is missing {name}") from error
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"scratch member is not UTF-8 text: {name}") from error

    def materialize(self, name: str, directory: Path) -> Path:
        """Write one validated member to a caller-owned temporary directory."""

        try:
            content = self.files[name]
        except KeyError as error:
            raise ValueError(f"scratch is missing {name}") from error
        destination = directory / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return destination

    def public_metadata(self) -> dict[str, Any]:
        """Return useful, bounded metadata without reproducing owner records."""

        if self.kind == "decomp.me-export":
            keys = (
                "slug",
                "parent",
                "name",
                "language",
                "platform",
                "compiler",
                "compiler_flags",
                "preset",
                "diff_label",
                "score",
                "max_score",
                "match_override",
                "creation_time",
                "last_updated",
            )
            return {key: self.metadata[key] for key in keys if key in self.metadata}
        decomp_me = self.metadata.get("decomp_me")
        result: dict[str, Any] = {"schema": self.metadata.get("schema")}
        if isinstance(decomp_me, dict):
            result["decomp_me"] = decomp_me
        if "project" in self.metadata:
            result["project"] = self.metadata["project"]
        return result


def _safe_member_path(raw_name: str) -> PurePosixPath | None:
    """Return a normalized member path, rejecting traversal and odd archives."""

    normalized = raw_name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if not raw_name or raw_name.endswith("/"):
        return None
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe scratch member path: {raw_name!r}")
    if not path.name:
        raise ValueError(f"invalid scratch member path: {raw_name!r}")
    return path


def _validate_member_set(files: dict[str, bytes]) -> None:
    if not files:
        raise ValueError("scratch contains no files")
    if len(files) > MAX_FILES:
        raise ValueError(f"scratch contains more than {MAX_FILES} files")
    total = sum(len(content) for content in files.values())
    if total > MAX_TOTAL_BYTES:
        raise ValueError(
            f"scratch exceeds the {MAX_TOTAL_BYTES // (1024 * 1024)} MiB size limit"
        )


def _read_zip(path: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    folded_names: set[str] = set()
    parents: set[PurePosixPath] = set()
    try:
        with zipfile.ZipFile(path) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            if len(members) > MAX_FILES:
                raise ValueError(f"scratch contains more than {MAX_FILES} files")
            total = 0
            for member in members:
                member_path = _safe_member_path(member.filename)
                if member_path is None:
                    continue
                name = member_path.name
                parents.add(member_path.parent)
                if member.flag_bits & 0x1:
                    raise ValueError(
                        f"encrypted scratch member is not supported: {name}"
                    )
                if member.file_size > MAX_FILE_BYTES:
                    raise ValueError(
                        f"scratch member exceeds the {MAX_FILE_BYTES // (1024 * 1024)} "
                        f"MiB limit: {name}"
                    )
                total += member.file_size
                if total > MAX_TOTAL_BYTES:
                    raise ValueError(
                        "scratch exceeds the "
                        f"{MAX_TOTAL_BYTES // (1024 * 1024)} MiB size limit"
                    )
                folded = name.casefold()
                if folded in folded_names:
                    raise ValueError(f"duplicate scratch member basename: {name}")
                folded_names.add(folded)
                files[name] = archive.read(member)
            if len(parents) > 1:
                rendered = ", ".join(sorted(str(parent) for parent in parents))
                raise ValueError(
                    "scratch ZIP members must share one flat directory; "
                    f"found: {rendered}"
                )
    except zipfile.BadZipFile as error:
        raise ValueError(f"not a valid ZIP archive: {path}") from error
    _validate_member_set(files)
    return files


def _read_directory(path: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    folded_names: set[str] = set()
    all_entries = list(path.iterdir())
    links = [item for item in all_entries if item.is_symlink()]
    if links:
        raise ValueError(
            f"scratch directory cannot contain symbolic links: {links[0].name}"
        )
    nested = [item for item in all_entries if item.is_dir()]
    if nested:
        raise ValueError(
            f"scratch directory must be flat; found nested directory: {nested[0].name}"
        )
    entries = [item for item in all_entries if item.is_file()]
    if len(entries) > MAX_FILES:
        raise ValueError(f"scratch contains more than {MAX_FILES} files")
    for item in entries:
        size = item.stat().st_size
        if size > MAX_FILE_BYTES:
            raise ValueError(
                f"scratch member exceeds the {MAX_FILE_BYTES // (1024 * 1024)} "
                f"MiB limit: {item.name}"
            )
        folded = item.name.casefold()
        if folded in folded_names:
            raise ValueError(f"duplicate scratch member basename: {item.name}")
        folded_names.add(folded)
        files[item.name] = item.read_bytes()
    _validate_member_set(files)
    return files


def _parse_json(files: dict[str, bytes], name: str) -> dict[str, Any]:
    try:
        raw = files[name].decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{name} is not UTF-8 JSON") from error
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} is not valid JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value


def _validate_decomp_me(files: dict[str, bytes], metadata: dict[str, Any]) -> None:
    missing = [name for name in ("code.c", "ctx.c") if name not in files]
    if missing:
        raise ValueError("decomp.me export is missing " + ", ".join(missing))
    for key in ("platform", "compiler", "diff_label"):
        value = metadata.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"metadata field {key!r} must be a string")
    for key in ("score", "max_score"):
        value = metadata.get(key)
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"metadata field {key!r} must be a finite number")
    score = metadata.get("score")
    maximum = metadata.get("max_score")
    if isinstance(maximum, (int, float)) and maximum <= 0:
        raise ValueError("metadata field 'max_score' must be positive")
    if isinstance(score, (int, float)) and score < 0:
        raise ValueError("metadata field 'score' cannot be negative")
    if (
        isinstance(score, (int, float))
        and isinstance(maximum, (int, float))
        and score > maximum
    ):
        raise ValueError("metadata field 'score' cannot exceed 'max_score'")


def _validate_bundle(files: dict[str, bytes], manifest: dict[str, Any]) -> bool:
    if manifest.get("schema") != "decomp-workbench-scratch-bundle-v1":
        raise ValueError("unsupported workbench scratch bundle schema")
    recorded = manifest.get("files")
    if not isinstance(recorded, dict) or not recorded:
        raise ValueError("scratch.json has no file checksums")
    for name, details in recorded.items():
        if not isinstance(name, str) or not isinstance(details, dict):
            raise ValueError("scratch.json contains an invalid file record")
        if PurePosixPath(name).name != name:
            raise ValueError(f"scratch.json has an invalid file name: {name!r}")
        expected = details.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", expected
        ):
            raise ValueError(f"scratch.json has an invalid SHA-256 for {name}")
        if name not in files:
            raise ValueError(f"workbench bundle is missing {name}")
        actual = hashlib.sha256(files[name]).hexdigest()
        if actual != expected.lower():
            raise ValueError(f"workbench bundle checksum mismatch: {name}")
    return True


def load_scratch(path: str | Path) -> ScratchPackage:
    """Load and validate a decomp.me export ZIP/directory or workbench bundle."""

    resolved = Path(path).expanduser().resolve()
    if resolved.is_dir():
        files = _read_directory(resolved)
    elif resolved.is_file():
        files = _read_zip(resolved)
    else:
        raise ValueError(f"scratch path does not exist: {resolved}")

    if DECOMP_ME_METADATA in files:
        metadata = _parse_json(files, DECOMP_ME_METADATA)
        _validate_decomp_me(files, metadata)
        return ScratchPackage(
            path=resolved,
            kind="decomp.me-export",
            files=files,
            metadata=metadata,
            checksums_valid=None,
        )
    if WORKBENCH_MANIFEST in files:
        manifest = _parse_json(files, WORKBENCH_MANIFEST)
        checksums_valid = _validate_bundle(files, manifest)
        return ScratchPackage(
            path=resolved,
            kind="workbench-bundle",
            files=files,
            metadata=manifest,
            checksums_valid=checksums_valid,
        )
    raise ValueError("unrecognized scratch: expected metadata.json or scratch.json")


def scratch_frontend(package: ScratchPackage) -> dict[str, str | None]:
    """Describe the selected language/frontend without conflating a preset.

    decomp.me exports record canonical compiler IDs (for example
    ``ido7.1_c++``), while workbench bundles may also carry a human-facing
    compiler label and an explicit ``compiler_id``. The distinction matters:
    the similarly named IDO 7.1 preset selects the C frontend, not NCC/EDG.
    """

    if package.kind == "workbench-bundle":
        settings = package.metadata.get("decomp_me")
        metadata = settings if isinstance(settings, dict) else {}
    else:
        metadata = package.metadata
    compiler_value = metadata.get("compiler")
    compiler = compiler_value if isinstance(compiler_value, str) else None
    compiler_id_value = metadata.get("compiler_id")
    compiler_id = (
        compiler_id_value
        if isinstance(compiler_id_value, str)
        else compiler
        if package.kind == "decomp.me-export"
        else None
    )
    language_value = metadata.get("language")
    language = language_value if isinstance(language_value, str) else None
    normalized_language = language.casefold() if language else ""
    normalized_compiler = (compiler_id or compiler or "").casefold()
    cxx = (
        "++" in normalized_language
        or normalized_language in {"cxx", "cpp", "old_cxx"}
        or normalized_compiler.endswith("_c++")
    )
    source_name = "src.cxx" if cxx else "src.c"
    driver: str | None = None
    frontend: str | None = None
    if normalized_compiler.startswith("ido") and (
        normalized_compiler.endswith("_c++") or cxx
    ):
        driver = "NCC"
        frontend = "EDG C++"
    elif normalized_compiler.startswith("ido"):
        driver = "cc"
        frontend = "cfe C"
    return {
        "compiler": compiler,
        "compiler_id": compiler_id,
        "language": language or ("C++" if cxx else None),
        "frontend": frontend,
        "expected_driver": driver,
        "source_name": source_name,
        "line_reset": f'#line 1 "{source_name}"',
    }


def site_source_marker(package: ScratchPackage) -> str:
    """Return decomp.me's editable-source marker for the selected language."""

    source_name = scratch_frontend(package)["source_name"]
    return f'#line 1 "{source_name}"\n'


def compose_site_source(package: ScratchPackage, source: str | Path | None) -> str:
    """Compose context and source with decomp.me's source line reset.

    decomp.me feeds the context and editable source to the compiler as one
    translation unit, inserting a language-aware marker before the editable
    source: ``#line 1 "src.c"`` for C and ``#line 1 "src.cxx"`` for old C++.
    With ``-g3`` that line identity can affect IDO/as1 scheduling, so compiling
    ``code.c`` alone is not a faithful verification.
    """

    if package.kind != "decomp.me-export":
        raise ValueError("site-faithful compilation requires a decomp.me export")
    context = package.text("ctx.c")
    if source is None:
        candidate = package.text("code.c")
    else:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise ValueError(f"candidate source is not a file: {source_path}")
        try:
            candidate = source_path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(
                f"candidate source is not UTF-8 text: {source_path}"
            ) from error
    separator = "" if context.endswith("\n") else "\n"
    return context + separator + site_source_marker(package) + candidate


def scratch_score(metadata: dict[str, Any]) -> dict[str, float] | None:
    """Return decomp.me's distance and percentage as context, never as truth."""

    score = metadata.get("score")
    maximum = metadata.get("max_score")
    if (
        isinstance(score, bool)
        or isinstance(maximum, bool)
        or not isinstance(score, (int, float))
        or not isinstance(maximum, (int, float))
        or maximum <= 0
    ):
        return None
    return {
        "score": float(score),
        "max_score": float(maximum),
        "percentage": 100.0 * (1.0 - float(score) / float(maximum)),
    }


# ---------------------------------------------------------------------------
# Pre-paste hardening: the two traps this repository was built to catch.
#
# decomp.me concatenates a scratch's context and code sections verbatim. A
# ctx.c that does not end in a newline glues its last statement onto code.c's
# first line, and a name declared in both sections fails to compile with no
# hint that the culprit is duplication rather than the candidate's logic.
# Both cost real human round-trips on the drawbitmap scratch before anyone
# saw a diff; both are checked here before the reader pastes anything.
# ---------------------------------------------------------------------------


def context_newline_warning(context: str) -> str | None:
    """Report exactly what happens when ctx.c does not end in a newline.

    decomp.me pastes `ctx.c` and `code.c` back to back with no separator of
    its own, so a missing trailing newline glues the first line of code onto
    the context's last statement. Returns `None` when the context is empty or
    already ends in a newline -- both are safe.
    """

    if not context or context.endswith("\n"):
        return None
    tail = context[-CONTEXT_GLUE_TAIL:]
    return (
        "context does not end in a newline; decomp.me concatenates ctx.c and "
        f"code.c verbatim, so your code's first line will glue onto ...{tail!r}"
        " -- start code.c with a blank line, or add a trailing newline to ctx.c"
    )


#: A backslash that only *looks* like a line splice: whitespace follows it, so
#: translation phase 2 never joins the lines. The layout reads as tied; the
#: compiler numbers the statements as untied; the only symptom is the score.
_BROKEN_SPLICE = re.compile(r"\\[ \t]+$")


def code_splice_report(code: str) -> dict[str, list[int]]:
    """Report line-splice hazards in code.c before a paste silently loses them.

    Statement-level trailing-backslash splices are how a candidate ties a
    statement to an earlier logical line (field-guide lever 25), and cfe
    numbers statements by logical line — so they are load-bearing, and they
    are exactly what whitespace-trimming editors, formatters, and some paste
    paths destroy. Two hazards, both silent:

    * ``broken``: a backslash followed by trailing whitespace is not a splice
      at all — the layout looks tied but compiles untied;
    * ``load_bearing``: an intact splice outside a preprocessor directive,
      which the reader must re-verify after every paste or reformat (splices
      inside directives are ordinary macro continuations and are not listed).

    Line-scanning is honestly approximate in the same way `context_lint` is:
    a backslash ending a ``//`` comment line is reported as load-bearing even
    though its effect is to continue the comment — that too is a hazard worth
    a look, not a false alarm.
    """

    broken: list[int] = []
    load_bearing: list[int] = []
    in_directive = False
    continuing = False
    for number, line in enumerate(code.split("\n"), start=1):
        if not continuing:
            in_directive = line.lstrip().startswith("#")
        splices = line.endswith("\\")
        if _BROKEN_SPLICE.search(line):
            broken.append(number)
        elif splices and not in_directive:
            load_bearing.append(number)
        continuing = splices
    return {"broken": broken, "load_bearing": load_bearing}


def duplicate_file_scope_symbols(context: str, code: str) -> list[dict[str, object]]:
    """Report names that `file_scope_definitions` sees defined in both files.

    This is the regex-level, honestly-approximate pass `context_lint`
    documents: it recognizes single-line static/global definitions and
    one-line function signatures, and it will miss more elaborate shapes
    (multi-line declarations, brace-initialized declarators, K&R signatures
    split across lines). A context that already declares a file-scope static
    the pasted code redeclares is exactly the second decomp.me trap -- the
    paste compiles-fails with a redefinition error that gives no hint the
    context is the other half of the conflict.
    """

    ctx_names = file_scope_definitions(context)
    code_names = file_scope_definitions(code)
    return [
        {
            "symbol": name,
            "ctx_line": ctx_names[name],
            "code_line": code_names[name],
        }
        for name in sorted(set(ctx_names) & set(code_names))
    ]


def _defines_from_compiler_flags(flags: object) -> dict[str, int | None]:
    """Seed the context lint's macro table from `metadata.json`'s -D flags.

    Best effort only: unparsable flag strings or non-string metadata yield an
    empty table rather than an error, since this is a bonus signal on top of
    the lint, not something the check should fail over.
    """

    if not isinstance(flags, str):
        return {}
    try:
        tokens = shlex.split(flags)
    except ValueError:
        return {}
    result: dict[str, int | None] = {}
    for token in tokens:
        if not token.startswith("-D") or len(token) <= 2:
            continue
        name, separator, value = token[2:].partition("=")
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            continue
        if not separator:
            result[name] = None
            continue
        analysis = analyze_expression(value, result)
        result[name] = analysis.value if analysis.ok else None
    return result


def scratch_context_hardening(package: ScratchPackage) -> dict[str, Any]:
    """Run the ctx.c/code.c checks that would have caught both known traps.

    Applies only to a decomp.me export, where the ctx.c + code.c concatenation
    and file-scope duplication risks actually exist; a workbench bundle uses
    differently named, differently composed files and gets
    `{"applicable": False}`.
    """

    if package.kind != "decomp.me-export":
        return {"applicable": False}
    context = package.text("ctx.c")
    code = package.text("code.c")
    defines = _defines_from_compiler_flags(package.metadata.get("compiler_flags"))
    report = lint_sources((("ctx.c", context), ("code.c", code)), defines)
    newline_warning = context_newline_warning(context)
    return {
        "applicable": True,
        "context_newline_warning": newline_warning,
        "duplicate_symbols": duplicate_file_scope_symbols(context, code),
        "code_splices": code_splice_report(code),
        "context_lint": report.as_dict(),
    }
