"""The identity gate, recorded: an instrumented build that proves it is stock.

An instrumented compiler is only worth reading if, with its tracing off, it
emits the *same object* the stock compiler does. Otherwise its traces describe
a compiler nobody is trying to match, and every conclusion drawn from them is
about the instrument.

`docs/compiler-instrumentation.md` has stated that requirement for a long time,
and one campaign honoured it -- by hand, every single time, with no record that
it had been done. Twelve instruments across four passes, and the only evidence
that any of them was gated was a stage's own sentence saying so. A reader
arriving at a trace three stages later has nothing to check.

So this is the gate plus the one thing it was missing: a **stamp**. The
comparison itself is :mod:`decomp_workbench.fidelity`'s, unchanged and
section-scoped, because stock IDO under `-g3` is not file-level reproducible
and a whole-file hash reports `.mdebug` noise as a failure. What is added is a
durable record naming the profile, both objects and their hashes, the sections
gated, the objdump that read them, and exactly what the stamp does and does not
claim -- and a `--verify` that re-runs the comparison rather than trusting the
record, and reports STALE when either object has moved or changed underneath
it.

**What the workbench will not do here, deliberately.** Building a compiler
means invoking the user's build system, and the package does not run
user-supplied build commands. Every alternative -- a required build-command
template, a container, a declarative build description -- either reintroduces
the shell or constrains the recompilation trees this can serve to the one it
was written against. The build half stays with the project, as it must; the
gate is the half campaigns were actually skipping, and it needs no build system
at all.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .campaign import file_sha256
from .fidelity import DEFAULT_SECTIONS, compare_object_fidelity

__all__ = [
    "GATE_SCHEMA",
    "InstrumentGateError",
    "build_stamp",
    "gate_lines",
    "verify_stamp",
]

GATE_SCHEMA = "decomp-workbench-instrument-gate-v1"

#: Printed with every stamp. A gate that overstated its scope would be worse
#: than no gate, because it would be believed.
GATE_CLAIM = (
    "With tracing off, the instrumented pass emitted the same .text, .rodata, "
    ".data, relocations and symbol table as the stock pass, for these two "
    "objects only. It says nothing about any other translation unit, about the "
    "instrumented pass with tracing on, or about the record grammar its traces "
    "use."
)


class InstrumentGateError(ValueError):
    """The gate could not be run, stamped, or verified."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_stamp(
    *,
    stock: str | Path,
    instrumented: str | Path,
    profile: str,
    objdump: str | None = None,
    sections: tuple[str, ...] = DEFAULT_SECTIONS,
    timeout: float = 10.0,
    note: str = "",
) -> dict[str, Any]:
    """Run the section-scoped comparison and return the stamp it earns."""

    stock_path = Path(stock).expanduser()
    instrumented_path = Path(instrumented).expanduser()
    for label, path in (("--stock", stock_path), ("--instrumented", instrumented_path)):
        if not path.is_file():
            raise InstrumentGateError(
                f"{label} does not exist: {path}. The gate compares two objects "
                "somebody else already built -- the workbench does not build "
                "compilers."
            )
    if not profile.strip():
        raise InstrumentGateError(
            "--profile names which instrumented pass this stamp is about, e.g. "
            "--profile uopt-cdx. A stamp with no profile cannot be looked up."
        )
    report = compare_object_fidelity(
        stock_path,
        instrumented_path,
        objdump=objdump,
        sections=sections,
        timeout=timeout,
    )
    return {
        "schema": GATE_SCHEMA,
        "profile": profile.strip(),
        "recorded": _now(),
        "pass": bool(report["pass"]),
        "gates": dict(report["gates"]),
        "sections": list(sections),
        "objdump": report["stock"]["objdump"],
        "stock": {
            "path": str(stock_path.resolve()),
            "sha256": file_sha256(stock_path),
        },
        "instrumented": {
            "path": str(instrumented_path.resolve()),
            "sha256": file_sha256(instrumented_path),
        },
        "file_identical": bool(report["file_identical"]),
        "note": note,
        "claim": GATE_CLAIM,
    }


def write_stamp(stamp: dict[str, Any], *, path: str | Path) -> Path:
    """Write one stamp, refusing to create a directory nobody named."""

    target = Path(path)
    if target.parent and not target.parent.exists():
        raise InstrumentGateError(
            f"{target.parent} does not exist. Name a directory that does: the "
            "workbench does not invent a place to keep gate records."
        )
    target.write_text(
        json.dumps(stamp, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return target


def read_stamp(path: str | Path) -> dict[str, Any]:
    location = Path(path)
    try:
        payload = json.loads(location.read_text(encoding="utf-8"))
    except OSError as error:
        raise InstrumentGateError(
            f"cannot read the stamp {location}: {error}"
        ) from None
    except ValueError as error:
        raise InstrumentGateError(f"{location} is not valid JSON: {error}") from None
    schema = payload.get("schema") if isinstance(payload, dict) else None
    if not isinstance(payload, dict) or schema != GATE_SCHEMA:
        raise InstrumentGateError(
            f"{location} is not a {GATE_SCHEMA} document (schema={schema!r})"
        )
    return payload


def verify_stamp(
    path: str | Path,
    *,
    objdump: str | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Re-run the gate the stamp records, and report what changed.

    Re-run, not re-read. A record that could only be checked against itself is
    a record of an intention.
    """

    stamp = read_stamp(path)
    findings: list[str] = []
    moved: list[str] = []
    for side in ("stock", "instrumented"):
        recorded = stamp.get(side) or {}
        object_path = Path(str(recorded.get("path", "")))
        if not object_path.is_file():
            moved.append(f"{side} object {object_path} is gone")
            continue
        current = file_sha256(object_path)
        if current != recorded.get("sha256"):
            moved.append(
                f"{side} object {object_path} has changed since the stamp "
                f"({recorded.get('sha256', '?')[:16]} -> {current[:16]})"
            )
    if moved:
        return {
            "schema": GATE_SCHEMA,
            "verification": "STALE",
            "pass": False,
            "stamp": stamp,
            "findings": moved,
            "claim": GATE_CLAIM,
        }
    fresh = build_stamp(
        stock=stamp["stock"]["path"],
        instrumented=stamp["instrumented"]["path"],
        profile=stamp["profile"],
        objdump=objdump,
        sections=tuple(stamp.get("sections") or DEFAULT_SECTIONS),
        timeout=timeout,
    )
    for gate, passed in fresh["gates"].items():
        if passed != stamp["gates"].get(gate):
            findings.append(
                f"{gate}: the stamp recorded "
                f"{'PASS' if stamp['gates'].get(gate) else 'FAIL'}, the rerun "
                f"reports {'PASS' if passed else 'FAIL'}"
            )
    return {
        "schema": GATE_SCHEMA,
        "verification": "AGREES" if not findings else "DISAGREES",
        "pass": bool(fresh["pass"]) and not findings,
        "stamp": stamp,
        "rerun": fresh,
        "findings": findings,
        "claim": GATE_CLAIM,
    }


def gate_lines(stamp: dict[str, Any], *, stamp_path: Path | None = None) -> list[str]:
    """Render one gate result for a terminal."""

    verdict = "PASS" if stamp["pass"] else "FAIL"
    lines = [
        f"instrument gate: {verdict}  profile={stamp['profile']}",
        f"stock:        {stamp['stock']['path']}  "
        f"sha256 {stamp['stock']['sha256'][:16]}",
        f"instrumented: {stamp['instrumented']['path']}  "
        f"sha256 {stamp['instrumented']['sha256'][:16]}",
        "",
    ]
    for gate, passed in stamp["gates"].items():
        lines.append(f"  {gate:<14} {'PASS' if passed else 'FAIL'}")
    if stamp["pass"] and not stamp["file_identical"]:
        lines.extend(
            (
                "",
                "note: the gated sections agree and the whole files do not. "
                "That is expected -- stock IDO under -g3 is not file-level "
                "reproducible, and .mdebug varies between runs of the "
                "unmodified compiler.",
            )
        )
    if not stamp["pass"]:
        lines.extend(
            (
                "",
                "This instrument's traces are not evidence about the stock "
                "compiler. Fix the instrumentation until the disabled build is "
                "byte-identical, then gate again.",
            )
        )
    if stamp_path is not None:
        lines.extend(("", f"stamped: {stamp_path}"))
    lines.extend(("", f"claim: {stamp['claim']}"))
    return lines


def verification_lines(result: dict[str, Any]) -> list[str]:
    """Render a `--verify` result."""

    stamp = result["stamp"]
    lines = [
        f"instrument gate: {result['verification']}  "
        f"profile={stamp['profile']}  recorded {stamp['recorded']}",
    ]
    if result["findings"]:
        lines.append("")
        lines.extend(f"  {item}" for item in result["findings"])
        lines.extend(
            (
                "",
                "The stamp no longer describes what is on disk. Re-run the "
                "gate against the objects you actually have.",
            )
        )
    else:
        lines.extend(
            (
                "",
                "  the rerun agrees with the stamp on every gated section",
            )
        )
    lines.extend(("", f"claim: {stamp['claim']}"))
    return lines
