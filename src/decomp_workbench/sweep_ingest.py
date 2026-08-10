"""Reading a sweep's objects back: the gate, the score, and the price table.

The workbench emitted the sources and the project built them. This is what
happens next, and it is the half campaigns kept rebuilding by hand: find each
variant's object, gate it, score it, and report the family with the coverage
its own manifest declared.

Two rules the campaign's own scorers broke, enforced here:

* **A wrong instruction count is reported, not silently absorbed.** Position-
  indexed scoring turns one inserted instruction into a four-figure mismatch,
  and eleven stages abandoned candidates that were one row away. The score is
  the shift-tolerant edit distance
  (:func:`decomp_workbench.shift_align.build_shift_diff`), and the ``ni`` delta
  is a column, not a rejection.

* **Nothing is dropped quietly.** A variant whose object is missing is a row in
  the report with the path that was looked for. A variant the generator refused
  is a row too. The coverage line then says what the family's negative result
  is entitled to claim.

The price table is the point of the null-hypothesis sweep. Every variant's
score is a difference against the control -- the base itself, built in the same
run by the same wrapper -- so "this construct costs ten rows" is a measurement
on the base as it stands now, not a memory from the stage that introduced it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .coverage import SweepCoverage
from .dis_cache import DisassemblyCache
from .model import Instruction
from .row_source import load_dump_rows, load_object_rows
from .screen import ScreenLine, build_screen_line
from .shift_align import build_shift_diff
from .sweep import INGEST_SCHEMA, SweepError, SweepManifest, VariantKey

__all__ = ["IngestResult", "VariantResult", "ingest_lines", "ingest_sweep"]

#: The manifest site that names the control: the base, unedited, built in the
#: same run. A price is a difference and needs both terms measured together.
CONTROL_SITE = "control"


@dataclass(frozen=True)
class VariantResult:
    """One variant's object, gate line and score -- or why there is none."""

    key: VariantKey
    description: str
    object_path: str | None
    screen: ScreenLine | None = None
    rows_away: int | None = None
    inserted: int = 0
    deleted: int = 0
    replaced: int = 0
    paired_mismatches: int = 0
    missing: str | None = None

    @property
    def scored(self) -> bool:
        return self.rows_away is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.key.as_dict(),
            "description": self.description,
            "object": self.object_path,
            "missing": self.missing,
            "rows_away": self.rows_away,
            "inserted": self.inserted,
            "deleted": self.deleted,
            "replaced": self.replaced,
            "paired_mismatches": self.paired_mismatches,
            "screen": self.screen.as_dict() if self.screen else None,
        }


@dataclass(frozen=True)
class IngestResult:
    """A whole sweep, read back and ranked."""

    manifest: SweepManifest
    target: str
    results: tuple[VariantResult, ...]
    control: VariantResult | None
    target_rows: int

    @property
    def scored(self) -> tuple[VariantResult, ...]:
        return tuple(item for item in self.results if item.scored)

    @property
    def missing(self) -> tuple[VariantResult, ...]:
        return tuple(item for item in self.results if not item.scored)

    @property
    def ranked(self) -> tuple[VariantResult, ...]:
        return tuple(
            sorted(
                self.scored,
                key=lambda item: (
                    item.rows_away if item.rows_away is not None else 1 << 30,
                    item.key.label,
                ),
            )
        )

    def price(self, item: VariantResult) -> int | None:
        """What this variant is worth against the control, in rows.

        Positive means the variant is that many rows *better* than the base --
        so for a removal sweep, the construct it removed was costing that much.
        """

        if self.control is None or self.control.rows_away is None:
            return None
        if item.rows_away is None:
            return None
        return self.control.rows_away - item.rows_away

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": INGEST_SCHEMA,
            "generator": self.manifest.generator,
            "base": self.manifest.base,
            "base_sha256": self.manifest.base_sha256,
            "target": self.target,
            "target_rows": self.target_rows,
            "control": self.control.as_dict() if self.control else None,
            "scored_count": len(self.scored),
            "missing_count": len(self.missing),
            "results": [
                {**item.as_dict(), "price": self.price(item)} for item in self.ranked
            ],
            "missing": [item.as_dict() for item in self.missing],
            "dropped": [dict(item) for item in self.manifest.dropped],
            "coverage": _ingest_coverage(self).as_dict(),
            "limits": list(self.manifest.limits),
        }


def _ingest_coverage(result: IngestResult) -> SweepCoverage:
    """The manifest's coverage, reduced by whatever failed to build.

    A variant with no object, or one objdump could not read, is a point the
    sweep **never visited** -- not one it declined for a stated reason. Only
    the generator's own refusals are exclusions, and those are already in the
    manifest's declared count. Crediting the unbuilt ones as excluded restored
    exhaustiveness arithmetically, so an ingest where nothing built at all
    printed `swept-exhaustively -- 0 of 4 point(s), 4 excluded; a negative
    result here is a proof about this space`. That is the false proof the
    coverage model exists to prevent.
    """

    declared = result.manifest.coverage
    return SweepCoverage(
        basis=declared.basis,
        space=declared.space,
        covered=len(result.scored),
        step=declared.step,
        excluded=declared.excluded,
    )


def _load(
    path: Path,
    *,
    dumps: bool,
    objdump: str | None,
    symbol: str | None,
    section: str,
    cache: DisassemblyCache | None,
) -> list[Instruction]:
    if dumps:
        return load_dump_rows(path, symbol=symbol)
    return load_object_rows(
        path, objdump=objdump, symbol=symbol, section=section, cache=cache
    )


def ingest_sweep(
    manifest: SweepManifest,
    *,
    objects: str | Path,
    target: str | Path,
    suffix: str = ".o",
    dumps: bool = False,
    target_dumps: bool = False,
    objdump: str | None = None,
    symbol: str | None = None,
    section: str = ".text",
    slot: int | None = None,
    cache_directory: str | Path | None = None,
) -> IngestResult:
    """Gate and score every built variant of one sweep."""

    directory = Path(objects)
    if not directory.is_dir():
        raise SweepError(
            f"{directory} is not a directory. --objects names the directory "
            "the project's compile-one wrapper wrote the built variants into."
        )
    cache = DisassemblyCache(Path(cache_directory)) if cache_directory else None
    target_rows = _load(
        Path(target),
        dumps=target_dumps,
        objdump=objdump,
        symbol=symbol,
        section=section,
        cache=cache,
    )

    results: list[VariantResult] = []
    for variant in manifest.variants:
        candidate = directory / f"{variant.stem}{suffix}"
        if not candidate.is_file():
            results.append(
                VariantResult(
                    key=variant.key,
                    description=variant.description,
                    object_path=None,
                    missing=f"no object at {candidate}",
                )
            )
            continue
        try:
            rows = _load(
                candidate,
                dumps=dumps,
                objdump=objdump,
                symbol=symbol,
                section=section,
                cache=cache,
            )
        except (OSError, RuntimeError, ValueError) as error:
            # A failed objdump raises RuntimeError. One truncated variant is
            # an `unreadable:` row like any other, not the end of the ingest:
            # a sweep is read for the variants that did build.
            results.append(
                VariantResult(
                    key=variant.key,
                    description=variant.description,
                    object_path=str(candidate),
                    missing=f"unreadable: {error}",
                )
            )
            continue
        diff = build_shift_diff(target_rows, rows)
        screen = build_screen_line(
            rows,
            label=variant.key.label,
            path=None if dumps else candidate,
            target=target_rows,
            slot=slot,
        )
        results.append(
            VariantResult(
                key=variant.key,
                description=variant.description,
                object_path=str(candidate),
                screen=screen,
                rows_away=diff.rows_away,
                inserted=diff.inserted,
                deleted=diff.deleted,
                replaced=diff.replaced,
                paired_mismatches=diff.paired_mismatches,
            )
        )

    control = next(
        (item for item in results if item.key.site == CONTROL_SITE and item.scored),
        None,
    )
    return IngestResult(
        manifest=manifest,
        target=str(target),
        results=tuple(results),
        control=control,
        target_rows=len(target_rows),
    )


def ingest_lines(result: IngestResult, *, limit: int = 20) -> list[str]:
    """Render the ingest report: the ranked family, then everything it lost."""

    manifest = result.manifest
    lines = [
        f"sweep {manifest.generator}: {manifest.base} -> {result.target}",
        f"base sha256 {manifest.base_sha256[:16]}  "
        f"{len(result.scored)} scored, {len(result.missing)} unbuilt, "
        f"{len(manifest.dropped)} refused by the generator",
        "",
    ]
    if result.control is not None:
        screen = result.control.screen
        lines.append(
            f"control (the base, unedited): rows_away="
            f"{result.control.rows_away}  {screen.render() if screen else ''}"
        )
        lines.append("")
    lines.append(" rows  price  ni    frame  coset  class site                 carrier")
    for item in result.ranked[:limit]:
        lines.append(_result_row(item, price=result.price(item)))
    if len(result.ranked) > limit:
        lines.append(
            f" ... {len(result.ranked) - limit} more scored variant(s); "
            "--limit 0 prints every row"
        )
    if result.control is not None and manifest.generator == "regress":
        lines.extend(("", *_price_lines(result)))
    if result.missing:
        lines.extend(("", f"unbuilt ({len(result.missing)}):"))
        for item in result.missing[:limit]:
            # An objdump refusal quotes the tool over several lines. One
            # variant is one row here, so keep the sentence and say the rest
            # is there -- a table that reflows on a bad object is unreadable
            # exactly when the reader most needs to scan it.
            reason = (item.missing or "").splitlines() or [""]
            more = "" if len(reason) == 1 else f" (+{len(reason) - 1} more line(s))"
            lines.append(f"  {item.key.label}  {reason[0]}{more}")
        if len(result.missing) > limit:
            lines.append(f"  ... {len(result.missing) - limit} more")
    if manifest.dropped:
        lines.extend(("", f"refused by the generator ({len(manifest.dropped)}):"))
        for entry in manifest.dropped[:limit]:
            lines.append(f"  {entry.get('site', '?')}  {entry.get('reason', '')}")
        if len(manifest.dropped) > limit:
            lines.append(f"  ... {len(manifest.dropped) - limit} more")
    coset = [item for item in result.scored if item.screen and item.screen.rotated]
    if coset:
        lines.extend(
            (
                "",
                f"COSET: {len(coset)} scored variant(s) sit at a rotated "
                "scratch ring. A ring-quotienting scorer reads them as better "
                "than they are; do not record one as a win on that number.",
            )
        )
    lines.extend(("", _ingest_coverage(result).sentence()))
    return lines


def _price_row(price: int | None) -> str:
    """The price column: `+3`, `0`, `-2`, or `-` when there is no control."""

    if price is None:
        return "-"
    return f"+{price}" if price > 0 else str(price)


def _result_row(item: VariantResult, *, price: int | None) -> str:
    """One ranked row: the distance, the price, and the gate line's four facts."""

    screen = item.screen
    instructions = str(screen.instructions) if screen else "-"
    frame = str(screen.frame) if screen and screen.frame is not None else "-"
    coset = (screen.coset or "-") if screen else "-"
    return (
        f" {str(item.rows_away).rjust(4)}  {_price_row(price).rjust(5)}  "
        f"{instructions:<5} {frame:<6} {coset:<6} "
        f"{item.key.generator_class:<5} {item.key.site[:20]:<20} "
        f"{item.key.carrier}"
    )


def _price_lines(result: IngestResult) -> list[str]:
    """The null-hypothesis answer: what each construct costs on this base."""

    lines = [
        "what each construct costs on the base as it stands now:",
    ]
    singles = [
        item
        for item in result.ranked
        if item.key.site != CONTROL_SITE and "+" not in item.key.site
    ]
    if not singles:
        return [*lines, "  (no single-construct removal scored)"]
    for item in sorted(singles, key=lambda entry: entry.key.site):
        price = result.price(item)
        if price is None:
            continue
        if price > 0:
            verdict = f"COSTS {price} row(s): removing it improves the base"
        elif price == 0:
            verdict = "free: removing it changes nothing measurable"
        else:
            verdict = f"EARNS {-price} row(s): it is load-bearing"
        lines.append(f"  {item.key.site:<20} {item.description[:44]:<44} {verdict}")
    return lines


def summarize(rows: Sequence[VariantResult]) -> dict[str, int]:
    """Count the family by generator class, for a one-line census."""

    counts: dict[str, int] = {}
    for item in rows:
        counts[item.key.generator_class] = counts.get(item.key.generator_class, 0) + 1
    return counts
