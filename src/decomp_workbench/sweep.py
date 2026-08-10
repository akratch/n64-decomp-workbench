"""A sweep is a named family of sources, a manifest, and an honest ingest.

The workbench does not own a project's build. It emits sources and a manifest;
the project's own compile-one wrapper turns them into objects; and then the
objects come back here to be gated, scored and reported. That is the same
boundary `campaign` already draws, and this module is the search half of it:
what to generate, how to name it, and what a result set is entitled to claim.

Three things one campaign paid for, built in rather than remembered:

* **A variant is keyed by (site, class, carrier), never by site alone.** At one
  source line, the *carrier's declaration index* selected between two entirely
  different cost deltas -- the compiler lays the frame out in declaration
  order, so which dead local a hoist recycles is part of the experiment, not an
  implementation detail. A catalogue thinned on the site would have kept the
  wrong one. Two variants that collide on the full triple are a generator
  defect and raise here rather than overwriting each other.

* **A class is a registry entry, not a regex.** One campaign's atom catalogue
  matched labels with ``^[NHGME](\\d+)_``, so when two new generator classes
  were added their atoms silently vanished from every downstream read -- no
  error, just a shorter table. Here a class letter that is not in
  :data:`GENERATOR_CLASSES` is an error naming the registry.

* **Nothing is dropped silently.** A limit, a refused edit, a missing object:
  each is counted, named, and printed. The coverage line
  (:class:`decomp_workbench.coverage.SweepCoverage`) then says whether a
  negative result from this sweep is a proof about the space or evidence about
  a sample.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .coverage import SweepCoverage

__all__ = [
    "GENERATOR_CLASSES",
    "INGEST_SCHEMA",
    "SWEEP_SCHEMA",
    "GeneratorClass",
    "SweepError",
    "SweepManifest",
    "Variant",
    "VariantKey",
    "known_class",
    "read_manifest",
    "write_family",
]

SWEEP_SCHEMA = "decomp-workbench-sweep-v1"
INGEST_SCHEMA = "decomp-workbench-sweep-ingest-v1"


class SweepError(ValueError):
    """A sweep could not be generated, written, or read back."""


@dataclass(frozen=True)
class GeneratorClass:
    """One generator class: its letter, its name, and what it mints."""

    letter: str
    name: str
    description: str

    def as_dict(self) -> dict[str, str]:
        return {
            "letter": self.letter,
            "name": self.name,
            "description": self.description,
        }


#: Every class a sweep can mint. This is the registry the catalogue reads;
#: adding a class here is what makes its variants visible downstream, and a
#: label carrying a letter that is not here is an error rather than a row that
#: quietly disappears.
GENERATOR_CLASSES: dict[str, GeneratorClass] = {
    "N": GeneratorClass(
        "N",
        "null-hypothesis removal",
        "one accumulated construct deleted, singly or jointly, to price it",
    ),
    "O": GeneratorClass(
        "O",
        "deep operand hoist",
        "a leaf of a nested subexpression hoisted into a carrier",
    ),
    "H": GeneratorClass(
        "H",
        "top-level operand hoist",
        "one side of the top-level binary expression hoisted into a carrier",
    ),
    "P": GeneratorClass(
        "P",
        "compound-assignment hoist",
        "x op= y becomes C = y; x op= C",
    ),
    "A": GeneratorClass(
        "A",
        "call-argument hoist",
        "f(expr) becomes C = expr; f(C)",
    ),
    "C": GeneratorClass(
        "C",
        "commutative flip",
        "the two operands of a commutative operator exchanged",
    ),
    "K": GeneratorClass(
        "K",
        "copy elimination",
        "a copy Y = X removed and Y's later reads rehosted onto X",
    ),
    "F": GeneratorClass(
        "F",
        "live-range fusion",
        "a donor local's occurrences renamed to the target, fusing two webs",
    ),
}


def known_class(letter: str) -> GeneratorClass:
    """Return the registered class, or raise naming the registry.

    The whole point: a label whose class letter nobody registered must stop
    the read. The alternative -- the campaign's own regex -- returned a
    shorter table and was believed.
    """

    entry = GENERATOR_CLASSES.get(letter)
    if entry is None:
        known = ", ".join(
            f"{item.letter} ({item.name})" for item in GENERATOR_CLASSES.values()
        )
        raise SweepError(
            f"{letter!r} is not a generator class. Registered classes: {known}. "
            "A class that is not registered is dropped from every catalogue "
            "read, so this is an error rather than a shorter table."
        )
    return entry


_TOKEN_RE = re.compile(r"[^A-Za-z0-9]+")


def _token(text: str) -> str:
    return _TOKEN_RE.sub("-", text.strip()).strip("-") or "x"


@dataclass(frozen=True)
class VariantKey:
    """Where the edit is, what class it is, and which carrier selects it.

    The carrier is not decoration. `L65`: at one line, two carriers drawn from
    different declaration indices produced two entirely different cost deltas,
    and a catalogue keyed by the site alone kept whichever was generated last.
    """

    site: str
    generator_class: str
    carrier: str = "-"

    def __post_init__(self) -> None:
        known_class(self.generator_class)

    @property
    def label(self) -> str:
        if self.carrier in {"", "-"}:
            return f"{self.generator_class}.{_token(self.site)}"
        return f"{self.generator_class}.{_token(self.site)}.{_token(self.carrier)}"

    def as_dict(self) -> dict[str, str]:
        return {
            "site": self.site,
            "class": self.generator_class,
            "carrier": self.carrier,
            "label": self.label,
        }


@dataclass(frozen=True)
class Variant:
    """One generated source, with the key that identifies its experiment."""

    key: VariantKey
    filename: str
    text: str
    description: str
    #: Free-form provenance the generator wants the manifest to carry.
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def stem(self) -> str:
        return Path(self.filename).stem

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.key.as_dict(),
            "filename": self.filename,
            "stem": self.stem,
            "description": self.description,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class SweepManifest:
    """The sources a sweep emitted, and what space they are a sample of."""

    generator: str
    base: str
    base_sha256: str
    variants: tuple[Variant, ...]
    coverage: SweepCoverage
    #: Points the generator refused, each with the reason. Printed, never
    #: summarized away: a sweep that quietly drops rows reports a smaller,
    #: cleaner, wrong space.
    dropped: tuple[dict[str, str], ...] = ()
    directory: str = ""
    context: str = ""
    limits: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": SWEEP_SCHEMA,
            "generator": self.generator,
            "base": self.base,
            "base_sha256": self.base_sha256,
            "context": self.context,
            "directory": self.directory,
            "variant_count": len(self.variants),
            "variants": [item.as_dict() for item in self.variants],
            "coverage": self.coverage.as_dict(),
            "dropped": [dict(item) for item in self.dropped],
            "dropped_count": len(self.dropped),
            "classes": [
                GENERATOR_CLASSES[letter].as_dict()
                for letter in sorted(
                    {item.key.generator_class for item in self.variants}
                )
            ],
            "limits": list(self.limits),
        }


def check_keys(variants: tuple[Variant, ...]) -> None:
    """Raise when two variants share one (site, class, carrier) triple.

    A collision means the generator under-resolved its own experiment: two
    different edits are about to be recorded, scored and remembered under one
    name.
    """

    seen: dict[tuple[str, str, str], Variant] = {}
    for item in variants:
        key = (item.key.site, item.key.generator_class, item.key.carrier)
        other = seen.get(key)
        if other is not None:
            raise SweepError(
                f"two variants share the key site={item.key.site} "
                f"class={item.key.generator_class} carrier={item.key.carrier}: "
                f"{other.description!r} and {item.description!r}. A sweep is "
                "keyed by all three; a collision means two different edits "
                "would be scored under one name."
            )
        seen[key] = item


def dedupe_variants(
    variants: tuple[Variant, ...],
) -> tuple[tuple[Variant, ...], tuple[dict[str, str], ...]]:
    """Drop variants whose emitted bytes another variant already has.

    Two classes can spell the same edit -- a top-level hoist and a deep hoist
    of the same leaf are one file -- and building both pays twice for one
    object. This is exact identity, not a partial key: the dropped row names
    the variant it duplicates, so the catalogue can still see both classes
    reached the same source.
    """

    seen: dict[str, Variant] = {}
    kept: list[Variant] = []
    duplicates: list[dict[str, str]] = []
    for item in variants:
        first = seen.get(item.text)
        if first is None:
            seen[item.text] = item
            kept.append(item)
            continue
        duplicates.append(
            {
                "site": item.key.label,
                "reason": (
                    f"byte-identical to {first.key.label}; one source, one build"
                ),
            }
        )
    return tuple(kept), tuple(duplicates)


def write_family(
    manifest: SweepManifest,
    *,
    directory: str | Path,
    overwrite: bool = False,
) -> SweepManifest:
    """Write every variant plus `sweep.json`, and return the placed manifest."""

    variants, duplicates = dedupe_variants(manifest.variants)
    if duplicates:
        manifest = SweepManifest(
            generator=manifest.generator,
            base=manifest.base,
            base_sha256=manifest.base_sha256,
            variants=variants,
            coverage=SweepCoverage(
                basis=manifest.coverage.basis,
                space=manifest.coverage.space,
                covered=len(variants),
                step=manifest.coverage.step,
                excluded=manifest.coverage.excluded + len(duplicates),
            ),
            dropped=manifest.dropped + duplicates,
            directory=manifest.directory,
            context=manifest.context,
            limits=manifest.limits,
        )
    check_keys(manifest.variants)
    target = Path(directory)
    if target.exists() and any(target.iterdir()) and not overwrite:
        raise SweepError(
            f"{target} is not empty. A sweep directory is the record of one "
            "experiment; pass --overwrite to replace it, or name a new one."
        )
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise SweepError(f"cannot create {target}: {error}") from None
    for item in manifest.variants:
        (target / item.filename).write_text(item.text, encoding="utf-8")
    placed = SweepManifest(
        generator=manifest.generator,
        base=manifest.base,
        base_sha256=manifest.base_sha256,
        variants=manifest.variants,
        coverage=manifest.coverage,
        dropped=manifest.dropped,
        directory=str(target),
        context=manifest.context,
        limits=manifest.limits,
    )
    (target / "sweep.json").write_text(
        json.dumps(placed.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return placed


def read_manifest(path: str | Path) -> SweepManifest:
    """Read a `sweep.json` back, checking every class against the registry."""

    location = Path(path)
    if location.is_dir():
        location = location / "sweep.json"
    try:
        payload = json.loads(location.read_text(encoding="utf-8"))
    except OSError as error:
        raise SweepError(
            f"cannot read the sweep manifest {location}: {error}"
        ) from None
    except ValueError as error:
        raise SweepError(f"{location} is not valid JSON: {error}") from None
    if payload.get("schema") != SWEEP_SCHEMA:
        raise SweepError(
            f"{location} is not a {SWEEP_SCHEMA} document (schema="
            f"{payload.get('schema')!r})"
        )
    variants = tuple(
        Variant(
            key=VariantKey(
                site=str(item["site"]),
                generator_class=str(item["class"]),
                carrier=str(item.get("carrier", "-")),
            ),
            filename=str(item["filename"]),
            text="",
            description=str(item.get("description", "")),
            detail=dict(item.get("detail") or {}),
        )
        for item in payload.get("variants", [])
    )
    check_keys(variants)
    coverage = payload.get("coverage") or {}
    return SweepManifest(
        generator=str(payload.get("generator", "")),
        base=str(payload.get("base", "")),
        base_sha256=str(payload.get("base_sha256", "")),
        variants=variants,
        coverage=SweepCoverage(
            basis=str(coverage.get("basis", "unknown")),
            space=coverage.get("space"),
            covered=int(coverage.get("covered", len(variants))),
            step=coverage.get("step"),
            excluded=int(coverage.get("excluded", 0)),
        ),
        dropped=tuple(dict(item) for item in payload.get("dropped", [])),
        directory=str(payload.get("directory", str(location.parent))),
        context=str(payload.get("context", "")),
        limits=tuple(payload.get("limits", [])),
    )
