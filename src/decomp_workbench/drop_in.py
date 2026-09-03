"""One instrumented `cc` carrying both passes' traces, planned and audited.

Every instrumented-compiler question this workbench answers belongs to one of
two passes, and the two are instrumented from different generated sources:
uopt's CDX allocator profiles (`instrument-uopt`) and ugen's free-list and
emit-order hooks (`instrument-ugen`). A drop-in that carries only one of them
answers only half the questions -- and it does so silently, because a missing
profile is not an error, it is an empty log.

That is not hypothetical. A campaign rebuilt its drop-in for a ugen spike, the
rebuild reproduced only ugen, and the uopt CDX profile was gone from the
binary. `CDX_LOG=1` produced no file. The gap survived four separate lever
agents over two days, each of whom re-derived it from an empty log, and it
blocked four functions whose residual was an allocator tie -- exactly the class
CDX decides directly.

So this module does two things, and the second matters more than the first:

* :func:`plan` writes the reproducible two-profile recipe -- which generated
  source each profile is applied to, in which order, with which hash gate, and
  which fidelity check closes it -- as a manifest and a runnable script.
* :func:`audit` reads the *built* binaries back and reports, per profile,
  whether its gate strings are present. A profile that did not survive the
  rebuild is then a failed check rather than a week of empty logs.

The audit is a byte scan and needs no compiler, no build, and no ROM. It
cannot prove a profile *works* -- only the fidelity gate and a positive
microcase do that ([Principle 5](principles.md)) -- but a profile whose marker
is absent from the binary is definitely not there, and that one-sided claim is
what was missing.
"""

from __future__ import annotations

import hashlib
import shlex
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PLAN_SCHEMA = "decomp-workbench-drop-in-plan-v1"
AUDIT_SCHEMA = "decomp-workbench-drop-in-audit-v1"


@dataclass(frozen=True)
class Profile:
    """One instrumentation profile: its source, its command, its markers."""

    name: str
    #: The generated compiler source it is applied to, by basename.
    source: str
    #: The `decomp-workbench` argv that applies it, with `{input}`/`{output}`.
    command: tuple[str, ...]
    #: The environment variables that switch its records on at run time.
    environment: tuple[str, ...]
    #: Literal strings the instrumented source injects, which therefore
    #: survive into the built binary and can be scanned for.
    markers: tuple[str, ...]
    #: What this profile is the only way to answer.
    answers: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.name,
            "source": self.source,
            "command": list(self.command),
            "environment": list(self.environment),
            "markers": list(self.markers),
            "answers": self.answers,
        }


#: The four profiles a complete drop-in carries, in the order they are applied.
#:
#: Two sources, four profiles. `instrument-uopt` composes its two into one
#: uopt.c in a fixed order; `instrument-ugen` writes ugen.c once and
#: `--emit-provenance` adds the emit hooks to that same output. Applying a
#: uopt profile to ugen.c, or the reverse, fails the pinned-source hash rather
#: than producing a half-instrumented compiler.
PROFILES: tuple[Profile, ...] = (
    Profile(
        name="uopt-globalcolor",
        source="uopt.c",
        command=(
            "instrument-uopt",
            "--profile",
            "globalcolor",
            "--profile",
            "alias",
            "{input}",
            "{output}",
        ),
        environment=("CDX_LOG", "CDX_OUT", "CDX_DETAIL_WEB", "CDX_FORCE"),
        markers=("CDX_LOG", "CDX_OUT", "CDX_FORCE"),
        answers=(
            "which web took which colour, what each occurrence was charged, "
            "and whether a forced colour is accepted or declined -- the only "
            "direct evidence for an allocation tie"
        ),
    ),
    Profile(
        name="uopt-alias",
        source="uopt.c",
        command=(),
        environment=("DKWB_UOPT_ALIAS_TRACE",),
        markers=("DKWB-BASE", "DKWB-ALIAS-QUERY"),
        answers=(
            "which base a memory reference was resolved against, and how an "
            "alias query was answered"
        ),
    ),
    Profile(
        name="ugen-freelist",
        source="ugen.c",
        command=(
            "instrument-ugen",
            "--emit-provenance",
            "{input}",
            "{output}",
        ),
        environment=("DKWB_UGEN_TRACE",),
        markers=("DKWB-FREELIST", "DKWB-CALL"),
        answers=(
            "the temp-ring pop sequence with the source line each pop was "
            "consumed on -- the construct that bought or sold a pop"
        ),
    ),
    Profile(
        name="ugen-emit-provenance",
        source="ugen.c",
        command=(),
        environment=("DKWB_UGEN_SCHED",),
        markers=("DKWB-EMIT-V1",),
        answers=(
            "the order ugen wrote instruction records and the source line "
            "each carries into as1 -- the line-order conflicts a join removes"
        ),
    ),
)

#: The scheduler evidence that needs no drop-in at all.
#:
#: Named in the plan because a reader assembling an instrumented compiler is
#: exactly the reader about to patch as1 for this, and there is nothing to
#: patch: the assembler ships the trace, and the object is byte-identical with
#: the option on.
STOCK_EVIDENCE: tuple[tuple[str, str], ...] = (
    (
        "cc -Wa,-R",
        "as1's own list-scheduler trace: per-block dependence graph, node "
        "readiness, and the key that decided each selection. Print-only; the "
        "object is cmp-identical with -R on. Read it with "
        "`trace-scheduler --from-as1-r`",
    ),
)


def _digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def plan(
    *,
    generated: Path,
    output: Path,
    workbench: str = "decomp-workbench",
) -> dict[str, Any]:
    """Describe the two-profile rebuild over one generated-compiler tree.

    `generated` is the directory holding the recompiled compiler's C -- for
    `ido-static-recomp`, `build/5.3/out` -- and `output` is where the
    instrumented copies go. Neither is read for content beyond a hash, and
    neither has to exist: the plan is a recipe, and a recipe for a tree that
    is not there yet is still the recipe.
    """

    steps: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for profile in PROFILES:
        if profile.source not in seen:
            seen.add(profile.source)
            source_path = generated / profile.source
            sources.append(
                {
                    "source": profile.source,
                    "path": str(source_path),
                    "sha256": _digest(source_path),
                    "present": source_path.is_file(),
                }
            )
        if not profile.command:
            continue
        argv = [
            workbench,
            *(
                token.format(
                    input=generated / profile.source,
                    output=output / profile.source,
                )
                for token in profile.command
            ),
        ]
        steps.append(
            {
                "profile": profile.name,
                "argv": argv,
                "produces": str(output / profile.source),
            }
        )
    return {
        "schema": PLAN_SCHEMA,
        "generated": str(generated),
        "output": str(output),
        "sources": sources,
        "steps": steps,
        "profiles": [item.as_dict() for item in PROFILES],
        "stock_evidence": [
            {"command": command, "answers": answers}
            for command, answers in STOCK_EVIDENCE
        ],
        "gates": list(GATES),
        "proof": (
            "a recipe, not a build. Nothing here compiles anything, and a "
            "plan over a tree that does not exist yet is still the plan; the "
            "gates below are what make a built drop-in trustworthy, and "
            "`check-drop-in` is what says the profiles survived the rebuild."
        ),
    }


#: What must pass before an instrumented drop-in is used for evidence.
#:
#: These are the existing fidelity gates, restated here in the order they are
#: run rather than duplicated: a plan that names the profiles and not the
#: gates is a plan for a compiler nobody has checked.
GATES: tuple[str, ...] = (
    "traces off: build one translation unit through the instrumented cc with "
    "every trace variable unset, and cmp the object against the stock build. "
    "Byte-identical, whole file, in every configuration the project ships",
    "positive control: with each variable set in turn, confirm the profile's "
    "own records appear. An empty log is the failure this command exists for",
    "collateral: rebuild the whole translation unit set and confirm the "
    "project's own link and image comparison are unchanged",
    "stamp: record the instrumented binaries' hashes with "
    "`decomp-workbench instrument-gate`, so a later log can be tied to the "
    "compiler that produced it",
)


def render_script(document: dict[str, Any]) -> str:
    """Render the plan as a script an operator can read before running."""

    lines = [
        "#!/bin/sh",
        "# Generated by `decomp-workbench instrument-drop-in`.",
        "# Read it before running it: it rewrites generated compiler source.",
        "set -eu",
        "",
    ]
    for source in document["sources"]:
        lines.append(f"test -f {shlex.quote(source['path'])}")
    lines.append("")
    for step in document["steps"]:
        lines.append(f"# {step['profile']}")
        lines.append(" ".join(shlex.quote(token) for token in step["argv"]))
        lines.append("")
    lines.append("# Rebuild both passes from the instrumented sources, then:")
    for gate in document["gates"]:
        lines.append(f"#   - {gate}")
    lines.append("")
    return "\n".join(lines)


@dataclass(frozen=True)
class ProfileAudit:
    """Whether one profile's markers survived into one built binary."""

    profile: str
    binary: str
    present: tuple[str, ...]
    absent: tuple[str, ...]

    @property
    def carried(self) -> bool:
        return not self.absent

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "binary": self.binary,
            "present": list(self.present),
            "absent": list(self.absent),
            "carried": self.carried,
        }


def _markers_in(data: bytes, markers: Iterable[str]) -> tuple[list[str], list[str]]:
    present: list[str] = []
    absent: list[str] = []
    for marker in markers:
        (present if marker.encode("ascii") in data else absent).append(marker)
    return present, absent


def audit(
    binaries: Sequence[Path], *, profiles: Sequence[Profile] = PROFILES
) -> dict[str, Any]:
    """Report which profiles' markers are present in the built binaries.

    One-sided by construction, and the report says so: a marker found proves
    the instrumented source was compiled in, a marker missing proves it was
    not, and neither proves the profile *fires* -- that is the positive
    control's job, and it needs the compiler.
    """

    if not binaries:
        raise ValueError("name at least one built compiler binary to audit")
    contents: list[tuple[str, bytes]] = []
    for path in binaries:
        contents.append((str(path), path.read_bytes()))

    audits: list[ProfileAudit] = []
    for profile in profiles:
        best: ProfileAudit | None = None
        for name, data in contents:
            present, absent = _markers_in(data, profile.markers)
            candidate = ProfileAudit(
                profile=profile.name,
                binary=name,
                present=tuple(present),
                absent=tuple(absent),
            )
            if best is None or len(candidate.present) > len(best.present):
                best = candidate
        assert best is not None
        audits.append(best)

    missing = [item.profile for item in audits if not item.carried]
    return {
        "schema": AUDIT_SCHEMA,
        "binaries": [name for name, _data in contents],
        "profiles": [item.as_dict() for item in audits],
        "complete": not missing,
        "missing": missing,
        "proof": (
            "a byte scan of the built binaries for each profile's injected "
            "marker strings. A marker present proves the profile was compiled "
            "in; a marker absent proves it was not. Neither proves it fires -- "
            "run the positive control for that."
        ),
    }


def format_audit(document: dict[str, Any]) -> str:
    """Render the audit as the lines an operator reads before a campaign."""

    lines = [f"binaries: {', '.join(document['binaries'])}"]
    for entry in document["profiles"]:
        state = "carried" if entry["carried"] else "ABSENT"
        detail = (
            ", ".join(entry["present"])
            if entry["carried"]
            else "missing " + ", ".join(entry["absent"])
        )
        lines.append(f"  {entry['profile']:24s} {state:8s} {detail}")
    if document["missing"]:
        lines.append("")
        lines.append(
            "incomplete drop-in: "
            + ", ".join(document["missing"])
            + ". Its logs will be empty rather than wrong, which is why this "
            "is checked and not discovered."
        )
    return "\n".join(lines)
