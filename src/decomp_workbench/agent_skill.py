"""Install the portable decompilation campaign skill for supported agents."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

SKILL_NAME = "n64-decomp-campaign"
SUPPORTED_CLIENTS = ("codex", "claude")


def bundled_skill_path() -> Path:
    """Return the skill directory shipped with this installation."""

    path = Path(__file__).parent / "skills" / SKILL_NAME
    if not (path / "SKILL.md").is_file():
        raise FileNotFoundError(f"bundled skill is missing: {path}")
    return path


def default_skills_directory(client: str) -> Path:
    """Return the personal skill directory for one supported client."""

    if client == "codex":
        configured = os.environ.get("CODEX_HOME")
        root = Path(configured).expanduser() if configured else Path.home() / ".codex"
    elif client == "claude":
        root = Path.home() / ".claude"
    else:
        choices = ", ".join(SUPPORTED_CLIENTS)
        raise ValueError(f"unsupported client {client!r}; choose {choices}")
    return root / "skills"


def skill_tree_digest(path: Path) -> str:
    """Hash relative paths and contents for a deterministic tree identity."""

    digest = hashlib.sha256()
    for item in sorted(entry for entry in path.rglob("*") if entry.is_file()):
        relative = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with item.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def install_agent_skill(
    client: str, *, destination: str | Path | None = None
) -> tuple[Path, str]:
    """Install the bundled skill safely, returning its path and status."""

    if client not in SUPPORTED_CLIENTS:
        choices = ", ".join(SUPPORTED_CLIENTS)
        raise ValueError(f"unsupported client {client!r}; choose {choices}")
    source = bundled_skill_path()
    skills_directory = (
        Path(destination).expanduser()
        if destination is not None
        else default_skills_directory(client)
    ).resolve()
    if skills_directory.exists() and not skills_directory.is_dir():
        raise NotADirectoryError(
            f"skills destination is not a directory: {skills_directory}"
        )
    target = skills_directory / SKILL_NAME

    if target.exists() or target.is_symlink():
        if target.is_dir() and skill_tree_digest(target) == skill_tree_digest(source):
            return target, "current"
        raise FileExistsError(
            f"skill already exists and differs: {target}; "
            "move it aside or choose --destination"
        )

    skills_directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{SKILL_NAME}-", dir=skills_directory
    ) as temporary:
        staged = Path(temporary) / SKILL_NAME
        shutil.copytree(source, staged)
        staged.rename(target)
    return target, "installed"
