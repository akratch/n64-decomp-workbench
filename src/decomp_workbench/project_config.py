"""Conservative, portable project configuration and discovery.

The workbench deliberately does not guess which of many build objects is a
function's target.  Discovery records useful surrounding evidence (objdiff,
Splat and a project build file), while object paths and symbols must be
unambiguous before they become executable defaults.
"""

from __future__ import annotations

import importlib
import json
import re
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

tomllib: Any = importlib.import_module(
    "tomllib" if sys.version_info >= (3, 11) else "tomli"
)

CONFIG_NAME = ".decomp-workbench.toml"
PROJECT_CONFIG_SCHEMA = "decomp-workbench-project-v1"
_SECTIONS = frozenset(
    {"project", "object", "build", "compiler", "campaign", "permuter"}
)
_KEYS = {
    "project": frozenset({"name"}),
    "object": frozenset(
        {"target", "candidate", "symbol", "section", "objdump", "input_mode"}
    ),
    "build": frozenset({"command", "cwd", "env", "inherit_env"}),
    "compiler": frozenset({"id", "frontend", "language", "driver", "backend"}),
    "campaign": frozenset({"state_dir", "cache_dir", "retain_sources"}),
    "permuter": frozenset(
        {
            "make",
            "python",
            "permuter_dir",
            "object_template",
            "compiler_marker",
            "compiler_command",
            "assembler_command",
            "compiler_type",
            "preserve_macros",
            "decompme_compiler",
            "output_dir",
            "ranking",
            "fallback_flags",
            "skip_postprocess",
            "minutes",
            "jobs",
            "threads",
            "load_threshold",
            "nice",
        }
    ),
}


@dataclass(frozen=True)
class PermuterOptions:
    """How this project drives decomp-permuter.

    Every field here exists because a permuter scratch that does not
    reproduce the project's real per-object recipe searches a target the
    real build never emits. `compiler_command` is the invariant half of the
    compile line (base arguments, includes, defines); the codegen flags are
    recovered per object from the build itself and appended to it.
    """

    make: str = "make"
    python: str | None = None
    permuter_dir: Path | None = None
    object_template: str = "build/{source}.o"
    compiler_marker: str | None = None
    compiler_command: str | None = None
    assembler_command: str | None = None
    compiler_type: str = "ido"
    preserve_macros: tuple[str, ...] = ()
    decompme_compiler: str | None = None
    output_dir: Path | None = None
    ranking: Path | None = None
    fallback_flags: tuple[str, ...] = ()
    skip_postprocess: tuple[str, ...] = (r"\.py\b",)
    minutes: int = 20
    jobs: int = 1
    threads: int | None = None
    load_threshold: float = 0.0
    nice: int = 15

    def as_dict(self) -> dict[str, object]:
        return {
            "make": self.make,
            "python": self.python,
            "permuter_dir": str(self.permuter_dir) if self.permuter_dir else None,
            "object_template": self.object_template,
            "compiler_marker": self.compiler_marker,
            "compiler_command": self.compiler_command,
            "assembler_command": self.assembler_command,
            "compiler_type": self.compiler_type,
            "preserve_macros": list(self.preserve_macros),
            "decompme_compiler": self.decompme_compiler,
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "ranking": str(self.ranking) if self.ranking else None,
            "fallback_flags": list(self.fallback_flags),
            "skip_postprocess": list(self.skip_postprocess),
            "minutes": self.minutes,
            "jobs": self.jobs,
            "threads": self.threads,
            "load_threshold": self.load_threshold,
            "nice": self.nice,
        }


@dataclass(frozen=True)
class ProjectConfig:
    """Validated project defaults with paths resolved from the config file."""

    path: Path
    name: str | None = None
    target: Path | None = None
    candidate: Path | None = None
    symbol: str | None = None
    section: str = ".text"
    objdump: str | None = None
    input_mode: str = "objects"
    build_command: tuple[str, ...] = ()
    build_cwd: Path | None = None
    inherit_env: tuple[str, ...] = ()
    environment: tuple[str, ...] = ()
    compiler_id: str | None = None
    frontend: str | None = None
    language: str | None = None
    driver: str | None = None
    backend: str | None = None
    state_dir: Path | None = None
    cache_dir: Path | None = None
    retain_sources: str = "leaders"
    permuter: PermuterOptions = field(default_factory=PermuterOptions)

    @property
    def root(self) -> Path:
        return self.path.parent

    def object_argv(self, command: str) -> list[str]:
        """Return an auditable object-command argv, or explain what is absent."""

        missing = [
            name
            for name, value in (
                ("object.target", self.target),
                ("object.candidate", self.candidate),
            )
            if value is None
        ]
        if missing:
            raise ValueError(
                f"{self.path} cannot run {command}: missing {', '.join(missing)}"
            )
        selected_command = f"{command}-dumps" if self.input_mode == "dumps" else command
        argv = [selected_command, str(self.target), str(self.candidate)]
        if self.symbol:
            argv.extend(("--function", self.symbol))
        if self.section != ".text":
            argv.extend(("--section", self.section))
        if self.objdump:
            argv.extend(("--objdump", self.objdump))
        return argv

    def campaign_argv(self, sources: list[str]) -> list[str]:
        """Return a campaign argv using every configured build identity field."""

        if self.target is None:
            raise ValueError(f"{self.path} cannot run campaign: missing object.target")
        if self.input_mode != "objects":
            raise ValueError("project campaign requires object.input_mode = 'objects'")
        if not sources:
            raise ValueError("project campaign requires at least one source")
        if not self.build_command:
            raise ValueError(f"{self.path} cannot run campaign: missing build.command")
        template = " ".join(self.build_command)
        for placeholder in ("{source}", "{output}"):
            if placeholder not in template:
                raise ValueError(f"build.command must contain {placeholder}")
        argv = [
            "campaign",
            str(self.target),
            *sources,
            "--compile-command",
            shlex.join(self.build_command),
            "--compile-cwd",
            str(self.build_cwd or self.root),
            "--state-dir",
            str(self.state_dir or self.root / ".decomp-workbench"),
            "--cache-dir",
            str(self.cache_dir or self.root / ".decomp-workbench/cache"),
            "--retain-sources",
            self.retain_sources,
        ]
        for env_value in self.environment:
            argv.extend(("--env", env_value))
        for inherited_name in self.inherit_env:
            argv.extend(("--inherit-env", inherited_name))
        for option, config_value in (
            ("--compiler-id", self.compiler_id),
            ("--frontend", self.frontend),
            ("--language", self.language),
            ("--driver", self.driver),
            ("--backend", self.backend),
            ("--symbol", self.symbol),
            ("--objdump", self.objdump),
        ):
            if config_value:
                argv.extend((option, config_value))
        if self.section != ".text":
            argv.extend(("--section", self.section))
        return argv

    def as_dict(self) -> dict[str, object]:
        def shown(value: Path | None) -> str | None:
            return str(value) if value is not None else None

        return {
            "schema": PROJECT_CONFIG_SCHEMA,
            "path": str(self.path),
            "root": str(self.root),
            "project": {"name": self.name},
            "object": {
                "target": shown(self.target),
                "candidate": shown(self.candidate),
                "symbol": self.symbol,
                "section": self.section,
                "objdump": self.objdump,
                "input_mode": self.input_mode,
            },
            "build": {
                "command_argv": list(self.build_command),
                "cwd": shown(self.build_cwd),
                "inherit_env": list(self.inherit_env),
                "env": list(self.environment),
            },
            "compiler": {
                "id": self.compiler_id,
                "frontend": self.frontend,
                "language": self.language,
                "driver": self.driver,
                "backend": self.backend,
            },
            "campaign": {
                "state_dir": shown(self.state_dir),
                "cache_dir": shown(self.cache_dir),
                "retain_sources": self.retain_sources,
            },
            "permuter": self.permuter.as_dict(),
        }


@dataclass(frozen=True)
class ProjectDiscovery:
    root: Path
    config_path: Path
    detected: tuple[dict[str, str], ...] = ()
    warnings: tuple[str, ...] = ()
    proposed: dict[str, dict[str, object]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": PROJECT_CONFIG_SCHEMA,
            "root": str(self.root),
            "config_path": str(self.config_path),
            "detected": list(self.detected),
            "warnings": list(self.warnings),
            "proposed": self.proposed,
        }


def _path(root: Path, value: object, field_name: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty path string")
    path = Path(value).expanduser()
    return (root / path).resolve() if not path.is_absolute() else path.resolve()


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _executable(root: Path, value: object) -> str | None:
    executable = _optional_string(value, "object.objdump")
    if executable is None:
        return None
    if "/" not in executable and "\\" not in executable:
        return executable
    path = Path(executable).expanduser()
    return str((root / path).resolve() if not path.is_absolute() else path.resolve())


def _table(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"[{name}] must be a TOML table")
    unknown = set(value) - _KEYS[name]
    if unknown:
        raise ValueError(f"unknown [{name}] keys: {', '.join(sorted(unknown))}")
    return value


def _string_list(value: object, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{field_name} must be an array of non-empty strings")
    return tuple(value)


def _positive_integer(value: object, field_name: str, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _permuter_options(root: Path, data: dict[str, Any]) -> PermuterOptions:
    """Validate the [permuter] table, refusing an unusable sweep early."""

    macros = _string_list(data.get("preserve_macros"), "permuter.preserve_macros")
    if any("=" not in entry for entry in macros):
        raise ValueError("permuter.preserve_macros entries must use PATTERN=TYPE")
    threads = data.get("threads")
    if threads is not None:
        threads = _positive_integer(threads, "permuter.threads", 1)
    load_threshold = data.get("load_threshold", 0.0)
    if isinstance(load_threshold, bool) or not isinstance(load_threshold, (int, float)):
        raise ValueError("permuter.load_threshold must be a number")
    if load_threshold < 0:
        raise ValueError("permuter.load_threshold must not be negative")
    nice = data.get("nice", 15)
    if isinstance(nice, bool) or not isinstance(nice, int):
        raise ValueError("permuter.nice must be an integer")
    skips = _string_list(data.get("skip_postprocess"), "permuter.skip_postprocess")
    for pattern in skips:
        try:
            re.compile(pattern)
        except re.error as error:
            raise ValueError(
                f"permuter.skip_postprocess entry {pattern!r} is not a valid "
                f"regular expression: {error}"
            ) from None
    template = data.get("object_template", "build/{source}.o")
    if not isinstance(template, str) or "{" not in template:
        raise ValueError(
            "permuter.object_template must name at least one of "
            "{source}, {stem}, {name}, {parent}"
        )
    defaults = PermuterOptions()
    return PermuterOptions(
        make=_optional_string(data.get("make"), "permuter.make") or defaults.make,
        python=_optional_string(data.get("python"), "permuter.python"),
        permuter_dir=_path(root, data.get("permuter_dir"), "permuter.permuter_dir"),
        object_template=template,
        compiler_marker=_optional_string(
            data.get("compiler_marker"), "permuter.compiler_marker"
        ),
        compiler_command=_optional_string(
            data.get("compiler_command"), "permuter.compiler_command"
        ),
        assembler_command=_optional_string(
            data.get("assembler_command"), "permuter.assembler_command"
        ),
        compiler_type=_optional_string(
            data.get("compiler_type"), "permuter.compiler_type"
        )
        or defaults.compiler_type,
        preserve_macros=macros,
        decompme_compiler=_optional_string(
            data.get("decompme_compiler"), "permuter.decompme_compiler"
        ),
        output_dir=_path(root, data.get("output_dir"), "permuter.output_dir"),
        ranking=_path(root, data.get("ranking"), "permuter.ranking"),
        fallback_flags=_string_list(
            data.get("fallback_flags"), "permuter.fallback_flags"
        ),
        skip_postprocess=skips or defaults.skip_postprocess,
        minutes=_positive_integer(data.get("minutes"), "permuter.minutes", 20),
        jobs=_positive_integer(data.get("jobs"), "permuter.jobs", 1),
        threads=threads,
        load_threshold=float(load_threshold),
        nice=nice,
    )


def load_project_config(path: str | Path) -> ProjectConfig:
    source = Path(path).expanduser().resolve()
    try:
        with source.open("rb") as stream:
            data = tomllib.load(stream)
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"invalid TOML in {source}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"project config is not a TOML table: {source}")
    unknown_sections = set(data) - _SECTIONS
    if unknown_sections:
        raise ValueError(
            f"unknown config sections: {', '.join(sorted(unknown_sections))}"
        )
    project = _table(data, "project")
    object_config = _table(data, "object")
    build = _table(data, "build")
    compiler = _table(data, "compiler")
    campaign = _table(data, "campaign")
    permuter = _permuter_options(source.parent, _table(data, "permuter"))
    command = build.get("command", [])
    inherit = build.get("inherit_env", [])
    environment = build.get("env", [])
    if not isinstance(command, list) or not all(
        isinstance(item, str) for item in command
    ):
        raise ValueError("build.command must be an array of strings")
    if not isinstance(inherit, list) or not all(
        isinstance(item, str) for item in inherit
    ):
        raise ValueError("build.inherit_env must be an array of environment names")
    if not isinstance(environment, list) or not all(
        isinstance(item, str) for item in environment
    ):
        raise ValueError("build.env must be an array of NAME=VALUE strings")
    env_name = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    if any(
        not separator or not env_name.fullmatch(name)
        for item in environment
        for name, separator, _value in (item.partition("="),)
    ):
        raise ValueError("build.env entries must use NAME=VALUE")
    if any(not env_name.fullmatch(item) for item in inherit):
        raise ValueError("build.inherit_env entries must be environment names")
    retain = campaign.get("retain_sources", "leaders")
    if retain not in {"leaders", "exact", "all", "none"}:
        raise ValueError("campaign.retain_sources must be leaders, exact, all, or none")
    section = object_config.get("section", ".text")
    if not isinstance(section, str) or not section:
        raise ValueError("object.section must be a non-empty string")
    input_mode = object_config.get("input_mode", "objects")
    if input_mode not in {"objects", "dumps"}:
        raise ValueError("object.input_mode must be objects or dumps")
    if input_mode == "dumps" and object_config.get("objdump") is not None:
        raise ValueError(
            "object.objdump does not apply when object.input_mode is dumps"
        )
    root = source.parent
    return ProjectConfig(
        path=source,
        name=_optional_string(project.get("name"), "project.name"),
        target=_path(root, object_config.get("target"), "object.target"),
        candidate=_path(root, object_config.get("candidate"), "object.candidate"),
        symbol=_optional_string(object_config.get("symbol"), "object.symbol"),
        section=section,
        objdump=_executable(root, object_config.get("objdump")),
        input_mode=str(input_mode),
        build_command=tuple(command),
        build_cwd=_path(root, build.get("cwd", "."), "build.cwd"),
        inherit_env=tuple(inherit),
        environment=tuple(environment),
        compiler_id=_optional_string(compiler.get("id"), "compiler.id"),
        frontend=_optional_string(compiler.get("frontend"), "compiler.frontend"),
        language=_optional_string(compiler.get("language"), "compiler.language"),
        driver=_optional_string(compiler.get("driver"), "compiler.driver"),
        backend=_optional_string(compiler.get("backend"), "compiler.backend"),
        state_dir=_path(
            root,
            campaign.get("state_dir", ".decomp-workbench"),
            "campaign.state_dir",
        ),
        cache_dir=_path(
            root,
            campaign.get("cache_dir", ".decomp-workbench/cache"),
            "campaign.cache_dir",
        ),
        retain_sources=str(retain),
        permuter=permuter,
    )


def find_project_config(start: str | Path = ".") -> Path:
    current = Path(start).expanduser().resolve()
    if current.is_file():
        current = current.parent
    for directory in (current, *current.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"no {CONFIG_NAME} found from {current} or its parents")


def discover_project(root: str | Path) -> ProjectDiscovery:
    directory = Path(root).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError(f"project root is not a directory: {directory}")
    detected: list[dict[str, str]] = []
    warnings: list[str] = []
    proposed: dict[str, dict[str, object]] = {
        "project": {"name": directory.name},
        "object": {"section": ".text"},
        "campaign": {
            "state_dir": ".decomp-workbench",
            "cache_dir": ".decomp-workbench/cache",
            "retain_sources": "leaders",
        },
    }
    objdiff = directory / "objdiff.json"
    if objdiff.is_file():
        detected.append({"kind": "objdiff", "path": str(objdiff)})
        try:
            payload = json.loads(objdiff.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("root is not an object")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            warnings.append(f"could not parse {objdiff.name}: {error}")
        else:
            warnings.append(
                "objdiff.json detected; object selection is intentionally not "
                "guessed because its units can name many targets"
            )
    splat_configs: list[Path] = []
    for candidate in sorted((*directory.glob("*.yaml"), *directory.glob("*.yml"))):
        try:
            head = candidate.read_text(encoding="utf-8", errors="replace")[:65536]
        except OSError:
            continue
        if "segments:" in head and "options:" in head:
            splat_configs.append(candidate)
    for candidate in splat_configs:
        detected.append({"kind": "splat", "path": str(candidate)})
    if splat_configs:
        warnings.append(
            "Splat config detected; ROM and segment metadata do not identify one "
            "unambiguous target/candidate object pair"
        )
    for filename in ("Makefile", "justfile"):
        build_file = directory / filename
        if build_file.is_file():
            detected.append({"kind": "build", "path": str(build_file)})
            break
    return ProjectDiscovery(
        root=directory,
        config_path=directory / CONFIG_NAME,
        detected=tuple(detected),
        warnings=tuple(warnings),
        proposed=proposed,
    )


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def render_project_config(discovery: ProjectDiscovery) -> str:
    """Render the small supported TOML surface without a writer dependency."""

    lines: list[str] = ["# n64-decomp-workbench project defaults", ""]
    for section in ("project", "object", "build", "compiler", "campaign"):
        values = discovery.proposed.get(section)
        if not values:
            continue
        lines.append(f"[{section}]")
        for key, value in values.items():
            if isinstance(value, str):
                rendered = _toml_string(value)
            elif isinstance(value, list):
                rendered = (
                    "[" + ", ".join(_toml_string(str(item)) for item in value) + "]"
                )
            else:
                raise ValueError(f"cannot render {section}.{key}: unsupported value")
            lines.append(f"{key} = {rendered}")
        lines.append("")
    return "\n".join(lines)


def with_object_overrides(
    discovery: ProjectDiscovery,
    *,
    target: str | None,
    candidate: str | None,
    symbol: str | None,
    objdump: str | None,
    input_mode: str = "objects",
) -> ProjectDiscovery:
    proposed = {name: dict(values) for name, values in discovery.proposed.items()}
    object_config = proposed.setdefault("object", {"section": ".text"})
    object_config["input_mode"] = input_mode
    for name, value in (
        ("target", target),
        ("candidate", candidate),
        ("symbol", symbol),
        ("objdump", objdump),
    ):
        if value is not None:
            object_config[name] = value
    return ProjectDiscovery(
        root=discovery.root,
        config_path=discovery.config_path,
        detected=discovery.detected,
        warnings=discovery.warnings,
        proposed=proposed,
    )


def with_build_overrides(
    discovery: ProjectDiscovery,
    *,
    command: list[str] | None,
    cwd: str | None,
    environment: list[str],
    inherit_env: list[str],
    compiler_id: str | None,
    frontend: str | None,
    language: str | None,
    driver: str | None,
    backend: str | None,
) -> ProjectDiscovery:
    """Attach only explicitly supplied compiler execution and lineage data."""

    if command is None and (cwd is not None or environment or inherit_env):
        raise ValueError(
            "--compile-cwd, --env, and --inherit-env require --compile-command"
        )
    if command is not None and not command:
        raise ValueError("--compile-command must contain an executable")
    proposed = {name: dict(values) for name, values in discovery.proposed.items()}
    if command is not None:
        proposed["build"] = {
            "command": command,
            "cwd": cwd or ".",
            "env": environment,
            "inherit_env": inherit_env,
        }
    lineage: dict[str, object] = {
        key: value
        for key, value in (
            ("id", compiler_id),
            ("frontend", frontend),
            ("language", language),
            ("driver", driver),
            ("backend", backend),
        )
        if value is not None
    }
    if lineage:
        proposed["compiler"] = lineage
    return ProjectDiscovery(
        root=discovery.root,
        config_path=discovery.config_path,
        detected=discovery.detected,
        warnings=discovery.warnings,
        proposed=proposed,
    )


def write_project_config(discovery: ProjectDiscovery) -> Path:
    discovery.config_path.parent.mkdir(parents=True, exist_ok=True)
    with discovery.config_path.open("x", encoding="utf-8") as stream:
        stream.write(render_project_config(discovery))
    return discovery.config_path


__all__ = [
    "CONFIG_NAME",
    "PROJECT_CONFIG_SCHEMA",
    "PermuterOptions",
    "ProjectConfig",
    "ProjectDiscovery",
    "discover_project",
    "find_project_config",
    "load_project_config",
    "render_project_config",
    "with_build_overrides",
    "with_object_overrides",
    "write_project_config",
]
