"""Pre-publication checks for redistributable proof and handoff repositories."""

from __future__ import annotations

import re
import subprocess
from fnmatch import fnmatch
from pathlib import Path
from typing import Any
from urllib.parse import unquote

HANDOFF_SCHEMA = "decomp-workbench-handoff-audit-v1"

MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\((?P<target>[^)]+)\)")
INLINE_CODE = re.compile(r"(?<!`)`(?P<value>[^`\n]+)`(?!`)")
ABSOLUTE_USER_PATH = re.compile(
    r"(?<![\w.])(?P<path>/(?:Users|home)/[^\s`'\"<>]+|[A-Za-z]:\\Users\\[^\s`'\"<>]+)"
)
SKIPPED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "dist",
    }
)


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _finding(
    severity: str,
    code: str,
    *,
    source: Path,
    root: Path,
    line: int | None,
    reference: str | None,
    message: str,
    action: str,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "source": source.relative_to(root).as_posix(),
        "line": line,
        "reference": reference,
        "message": message,
        "action": action,
    }


def _git_root(path: Path) -> Path | None:
    process = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode:
        return None
    return Path(process.stdout.strip()).resolve()


def _git_tracked(path: Path, cache: dict[Path, tuple[Path | None, bool]]) -> bool:
    resolved = path.resolve()
    if resolved in cache:
        return cache[resolved][1]
    git_root = _git_root(resolved if resolved.is_dir() else resolved.parent)
    if git_root is None or not resolved.is_relative_to(git_root):
        cache[resolved] = (git_root, False)
        return False
    relative = resolved.relative_to(git_root)
    process = subprocess.run(
        [
            "git",
            "-C",
            str(git_root),
            "ls-files",
            "--error-unmatch",
            "--",
            str(relative),
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    tracked = process.returncode == 0
    cache[resolved] = (git_root, tracked)
    return tracked


def _git_files(root: Path, git_root: Path, *modes: str) -> list[Path]:
    relative = root.relative_to(git_root)
    process = subprocess.run(
        ["git", "-C", str(git_root), "ls-files", "-z", *modes, "--", str(relative)],
        check=False,
        capture_output=True,
    )
    if process.returncode:
        return []
    return [
        (git_root / raw.decode("utf-8")).resolve()
        for raw in process.stdout.split(b"\0")
        if raw
    ]


def _excluded(path: Path, *, root: Path, patterns: list[str]) -> bool:
    relative = path.relative_to(root).as_posix()
    return any(fnmatch(relative, pattern) for pattern in patterns)


def _text_files(
    root: Path,
    *,
    git_root: Path | None,
    exclude: list[str],
) -> list[Path]:
    if git_root is not None and root.is_relative_to(git_root):
        candidates = _git_files(
            root,
            git_root,
            "--cached",
            "--others",
            "--exclude-standard",
        )
        return sorted(
            item
            for item in set(candidates)
            if item.is_file()
            and not item.is_symlink()
            and not _excluded(item, root=root, patterns=exclude)
        )
    files: list[Path] = []
    for item in root.rglob("*"):
        relative_parts = item.relative_to(root).parts
        if any(
            part in SKIPPED_DIRECTORY_NAMES or part.startswith(".venv")
            for part in relative_parts
        ):
            continue
        if (
            item.is_file()
            and not item.is_symlink()
            and not _excluded(item, root=root, patterns=exclude)
        ):
            files.append(item)
    return sorted(files)


def _decode_text(path: Path) -> str | None:
    if path.stat().st_size > 4 * 1024 * 1024:
        return None
    content = path.read_bytes()
    if b"\0" in content:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _link_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        return target[1 : target.index(">")]
    if " " in target:
        target = target.split(" ", 1)[0]
    return target


def _inline_path(raw: str, *, root: Path, document: Path) -> str | None:
    value = raw.strip().strip(".,;:()[]")
    if (
        not value
        or any(character.isspace() for character in value)
        or value.startswith(("http://", "https://", "mailto:", "#"))
        or any(marker in value for marker in ("$", "{", "}", "*"))
        or "/" not in value
    ):
        return None
    path_text = value.partition("#")[0]
    if not path_text or path_text.startswith("/"):
        return None
    path = Path(path_text)
    if path.suffix.casefold() == ".md":
        return path_text
    if (root / path_text).exists() or (document.parent / path_text).exists():
        return path_text
    return None


def _resolve_reference(
    reference: str,
    *,
    document: Path,
    root: Path,
    dependency_roots: list[Path],
) -> tuple[Path | None, str | None]:
    decoded = unquote(reference.partition("#")[0])
    if not decoded:
        return document, "handoff"
    path = Path(decoded).expanduser()
    if path.is_absolute():
        return (path.resolve(), "absolute") if path.exists() else (None, None)
    candidates = [
        (document.parent / path, "handoff"),
        (root / path, "handoff"),
        *((dependency / path, "dependency") for dependency in dependency_roots),
    ]
    seen: set[Path] = set()
    for candidate, origin in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved, origin
    matches = [
        (candidate, origin)
        for search_root, origin in [(root, "handoff")]
        + [(dependency, "dependency") for dependency in dependency_roots]
        for candidate in search_root.rglob(path.as_posix())
        if candidate.exists()
    ]
    if len(matches) == 1:
        candidate, origin = matches[0]
        return candidate.resolve(), origin
    return None, None


def audit_handoff(
    path: str | Path,
    *,
    dependency_roots: list[str | Path] | None = None,
    exclude: list[str] | None = None,
) -> dict[str, Any]:
    """Audit one public handoff tree for references that will not travel."""

    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"handoff root is not a directory: {root}")
    dependencies = [
        Path(item).expanduser().resolve() for item in dependency_roots or []
    ]
    exclusions = list(exclude or [])
    for dependency in dependencies:
        if not dependency.is_dir():
            raise NotADirectoryError(
                f"dependency root is not a directory: {dependency}"
            )

    findings: list[dict[str, Any]] = []
    git_cache: dict[Path, tuple[Path | None, bool]] = {}
    git_root = _git_root(root)
    files = _text_files(root, git_root=git_root, exclude=exclusions)

    if git_root is None:
        findings.append(
            _finding(
                "warning",
                "not-git-backed",
                source=root,
                root=root,
                line=None,
                reference=None,
                message="the handoff root is not inside a Git worktree",
                action=(
                    "audit the exact tracked tree or review the publication "
                    "archive manually"
                ),
            )
        )
    else:
        untracked_files = set(
            _git_files(root, git_root, "--others", "--exclude-standard")
        )
        for file_path in sorted(
            item
            for item in untracked_files
            if not _excluded(item, root=root, patterns=exclusions)
        ):
            findings.append(
                _finding(
                    "error",
                    "untracked-file",
                    source=file_path,
                    root=root,
                    line=None,
                    reference=file_path.relative_to(root).as_posix(),
                    message="this local file is not tracked and will not be published",
                    action=(
                        "track it, remove it from the handoff, or replace it "
                        "with a reproducible recipe"
                    ),
                )
            )

    examined_references: set[tuple[Path, int, str]] = set()
    for document in (item for item in files if item.suffix.casefold() == ".md"):
        text = _decode_text(document)
        if text is None:
            continue
        for match in ABSOLUTE_USER_PATH.finditer(text):
            reference = match.group("path").rstrip(".,;:")
            findings.append(
                _finding(
                    "error",
                    "absolute-user-path",
                    source=document,
                    root=root,
                    line=_line_number(text, match.start()),
                    reference=reference,
                    message="an absolute user path is not portable",
                    action=(
                        "replace it with a repository-relative path or a "
                        "documented placeholder"
                    ),
                )
            )

        references: list[tuple[int, str, str]] = []
        for match in MARKDOWN_LINK.finditer(text):
            target = _link_target(match.group("target"))
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            references.append((match.start(), target, "markdown-link"))
        for match in INLINE_CODE.finditer(text):
            inline_target = _inline_path(
                match.group("value"), root=root, document=document
            )
            if inline_target is not None:
                references.append((match.start(), inline_target, "inline-path"))

        for offset, reference, reference_kind in references:
            line = _line_number(text, offset)
            key = (document, line, reference)
            if key in examined_references:
                continue
            examined_references.add(key)
            resolved, origin = _resolve_reference(
                reference,
                document=document,
                root=root,
                dependency_roots=dependencies,
            )
            if resolved is None:
                findings.append(
                    _finding(
                        "error",
                        "missing-path-reference",
                        source=document,
                        root=root,
                        line=line,
                        reference=reference,
                        message=(
                            f"{reference_kind} does not resolve in the handoff "
                            "or declared dependency roots"
                        ),
                        action=(
                            "include the dependency, link its public location, "
                            "or pass --dependency-root to audit it explicitly"
                        ),
                    )
                )
                continue
            if origin == "absolute":
                continue
            if origin == "handoff" and resolved.is_relative_to(root):
                continue
            if origin == "dependency" and resolved.is_file():
                dependency_git = _git_root(resolved.parent)
                if dependency_git is None or not _git_tracked(resolved, git_cache):
                    findings.append(
                        _finding(
                            "error",
                            "untracked-dependency",
                            source=document,
                            root=root,
                            line=line,
                            reference=reference,
                            message=(
                                "the dependency exists locally but is not "
                                "tracked in its project"
                            ),
                            action=(
                                "publish/provision the dependency or replace "
                                "the claim with a self-contained explanation"
                            ),
                        )
                    )

    findings.sort(
        key=lambda item: (
            item["source"],
            item["line"] if item["line"] is not None else 0,
            item["code"],
        )
    )
    errors = sum(item["severity"] == "error" for item in findings)
    warnings = sum(item["severity"] == "warning" for item in findings)
    return {
        "schema": HANDOFF_SCHEMA,
        "root": str(root),
        "git_root": str(git_root) if git_root else None,
        "dependency_roots": [str(item) for item in dependencies],
        "excluded": exclusions,
        "files_examined": len(files),
        "errors": errors,
        "warnings": warnings,
        "ready": errors == 0,
        "findings": findings,
        "proof": (
            "Publication readiness only: this audit does not establish compiler "
            "provenance, function exactness, or project/ROM identity."
        ),
    }
