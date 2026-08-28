"""Classify a build against the target image, by function image range.

The permuter scores a scratch object and `compare` scores an object pair.
Neither is available for code in a module that ships unrelocated: the target's
own calls are spelled with placeholders whose values the runtime supplies, so
identical instructions still score as mismatches and no object-level oracle
can reach zero (see :mod:`decomp_workbench.reloc_surface`). The linked image
is what remains, and it is sound: if the built image equals the target image
over the function's bytes, the function is right, whatever any score says.

This module is the measurement half of that loop, and only that half. It
takes the bytes of a build the host produced, the bytes of the target, and the
image ranges the host says its functions occupy, and it answers four
questions per range:

``exact``
    the whole image is byte-identical.
``text-exact``
    nothing differs inside the range; something differs outside it. The
    function is right and the residue is collateral -- data or layout, an
    ownership question, not code work.
``text-differs``
    N words differ inside the range. This is a real residual with a number.
``size-differs``
    the two images are not the same length, so the range does not name the
    same bytes on both sides and no verdict about it would mean anything --
    or the range itself ends past the shorter image, which is the same
    absence of a comparison for a different reason, and the summary says
    which.

**No build orchestration lives here.** Splicing a candidate into its source,
running the project's build, and restoring the tree afterwards are the host's
job: only the project knows how it builds, and a workbench that guessed would
be wrong in the way that costs a day. `docs/linked-oracle.md` writes the
host-side loop out.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

LINKED_COMPARE_SCHEMA = "decomp-workbench-linked-compare-v1"
RANGES_SCHEMA = "decomp-workbench-image-ranges-v1"

#: Ordered worst-last, so the whole-image class is `max` over the ranges'.
CLASS_ORDER = ("exact", "text-exact", "text-differs", "size-differs")

#: Block size for the differing-offset scan. A ROM is tens of megabytes and
#: almost all of it is identical; comparing whole blocks first and descending
#: only into the ones that differ keeps a full-image scan cheap without ever
#: sampling -- every differing byte is still visited.
_BLOCK = 4096


class RangeError(ValueError):
    """An image range is malformed, or names bytes outside the image."""


@dataclass(frozen=True)
class ImageRange:
    """One function's byte range in the image, half-open."""

    name: str
    start: int
    end: int

    @property
    def size(self) -> int:
        return self.end - self.start

    def contains(self, offset: int) -> bool:
        return self.start <= offset < self.end

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start": self.start,
            "end": self.end,
            "size": self.size,
        }


@dataclass(frozen=True)
class RangeVerdict:
    """What the built image says about one range."""

    name: str
    start: int
    end: int
    klass: str
    in_range_words: int = 0
    in_range_bytes: int = 0
    out_of_range_bytes: int = 0
    first_in_range: int | None = None
    first_out_of_range: int | None = None
    size_delta: int = 0
    #: Whether the range itself names bytes past the end of the shorter
    #: image. Two images of equal length and a range beyond both of them is a
    #: wrong range, not a wrong build, and `size-differs (+0)` says neither.
    past_image: bool = False

    @property
    def summary(self) -> str:
        if self.klass == "text-differs":
            return f"text-differs {self.in_range_words} words"
        if self.klass == "size-differs":
            if not self.size_delta:
                return "size-differs (range past the image)"
            note = ", range past the image" if self.past_image else ""
            return f"size-differs ({self.size_delta:+d}{note})"
        if self.klass == "text-exact":
            return f"text-exact (collateral {self.out_of_range_bytes} bytes)"
        return "exact"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start": self.start,
            "end": self.end,
            "class": self.klass,
            "summary": self.summary,
            "in_range_words": self.in_range_words,
            "in_range_bytes": self.in_range_bytes,
            "out_of_range_bytes": self.out_of_range_bytes,
            "first_in_range": self.first_in_range,
            "first_out_of_range": self.first_out_of_range,
            "size_delta": self.size_delta,
            "past_image": self.past_image,
        }


@dataclass(frozen=True)
class LinkedComparison:
    """One build, one target, and a verdict per range."""

    built: str
    target: str
    built_size: int
    target_size: int
    differing_bytes: int
    verdicts: tuple[RangeVerdict, ...] = ()
    first_difference: int | None = None

    @property
    def size_delta(self) -> int:
        return self.built_size - self.target_size

    @property
    def klass(self) -> str:
        if not self.verdicts:
            return (
                "size-differs"
                if self.size_delta
                else ("exact" if not self.differing_bytes else "text-exact")
            )
        return max((item.klass for item in self.verdicts), key=CLASS_ORDER.index)

    @property
    def ok(self) -> bool:
        """Every range's own bytes agree; collateral outside them may not."""

        return self.klass in ("exact", "text-exact")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": LINKED_COMPARE_SCHEMA,
            "built": self.built,
            "target": self.target,
            "built_size": self.built_size,
            "target_size": self.target_size,
            "size_delta": self.size_delta,
            "differing_bytes": self.differing_bytes,
            "first_difference": self.first_difference,
            "class": self.klass,
            "ok": self.ok,
            "ranges": [item.as_dict() for item in self.verdicts],
        }


def differing_offsets(built: bytes, target: bytes) -> Iterator[int]:
    """Yield every offset at which the two images differ, in order.

    Only the common prefix is walked: past it the images have different
    lengths, which :func:`compare_images` reports as a size difference rather
    than as several million differing bytes.
    """

    limit = min(len(built), len(target))
    for base in range(0, limit, _BLOCK):
        stop = min(base + _BLOCK, limit)
        left, right = built[base:stop], target[base:stop]
        if left == right:
            continue
        for offset, (a, b) in enumerate(zip(left, right, strict=True), start=base):
            if a != b:
                yield offset


def parse_ranges(payload: Any, *, origin: str = "ranges") -> tuple[ImageRange, ...]:
    """Read image ranges from the host's JSON document.

    Accepts ``{"ranges": [...]}`` or a bare list; each entry needs a ``name``
    and ``start``, plus either ``end`` or ``size``. Values may be integers or
    ``"0x..."`` strings, because the numbers a host has to hand are usually
    already hexadecimal text.
    """

    if isinstance(payload, Mapping):
        schema = payload.get("schema")
        if schema is not None and schema != RANGES_SCHEMA:
            raise RangeError(
                f"{origin}: unknown schema {schema!r}; expected {RANGES_SCHEMA!r}"
            )
        entries = payload.get("ranges", [])
    else:
        entries = payload
    if not isinstance(entries, Sequence) or isinstance(entries, str | bytes):
        raise RangeError(f"{origin}: expected a list of ranges")

    out: list[ImageRange] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise RangeError(f"{origin}: each range must be a JSON object")
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise RangeError(f"{origin}: each range needs a non-empty 'name'")
        start = _integer(entry.get("start"), where=f"{origin}: {name} start")
        if entry.get("end") is not None:
            end = _integer(entry["end"], where=f"{origin}: {name} end")
        elif entry.get("size") is not None:
            end = start + _integer(entry["size"], where=f"{origin}: {name} size")
        else:
            raise RangeError(f"{origin}: {name} needs an 'end' or a 'size'")
        out.append(_range(name, start, end))
    return tuple(out)


def parse_range_argument(text: str) -> ImageRange:
    """Read one ``NAME:START:END`` or ``NAME:START+SIZE`` command-line range."""

    name, separator, rest = text.partition(":")
    if not separator or not name.strip():
        raise RangeError(f"{text!r}: expected NAME:START:END or NAME:START+SIZE")
    if "+" in rest:
        start_text, _, size_text = rest.partition("+")
        start = _integer(start_text, where=f"{name} start")
        return _range(name, start, start + _integer(size_text, where=f"{name} size"))
    start_text, separator, end_text = rest.partition(":")
    if not separator:
        raise RangeError(f"{text!r}: expected NAME:START:END or NAME:START+SIZE")
    return _range(
        name,
        _integer(start_text, where=f"{name} start"),
        _integer(end_text, where=f"{name} end"),
    )


def _range(name: str, start: int, end: int) -> ImageRange:
    if start < 0:
        raise RangeError(f"{name}: a negative start (0x{start:x}) names no bytes")
    if end <= start:
        raise RangeError(
            f"{name}: end 0x{end:x} is not past start 0x{start:x}; an empty "
            "range would report `text-exact` for a function nobody compared"
        )
    return ImageRange(name=name, start=start, end=end)


def _integer(value: Any, *, where: str) -> int:
    if isinstance(value, bool) or value is None:
        raise RangeError(f"{where}: expected an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip(), 0)
        except ValueError as error:
            raise RangeError(f"{where}: {value!r} is not an integer") from error
    raise RangeError(f"{where}: expected an integer, got {type(value).__name__}")


def compare_images(
    built: bytes,
    target: bytes,
    ranges: Iterable[ImageRange] = (),
    *,
    built_name: str = "built",
    target_name: str = "target",
) -> LinkedComparison:
    """Compare two images and classify each range the host named."""

    wanted = tuple(ranges)
    offsets = list(differing_offsets(built, target))
    size_delta = len(built) - len(target)
    comparable = min(len(built), len(target))

    # `offsets` is ascending, so each range's own slice is two bisections
    # rather than a walk. A build that went wrong differs over megabytes and
    # a trial names hundreds of functions; scanning the whole list per range
    # multiplies those two into a report that never finishes.
    verdicts: list[RangeVerdict] = []
    for item in wanted:
        low = bisect_left(offsets, item.start)
        high = bisect_left(offsets, item.end)
        inside = offsets[low:high]
        outside_count = len(offsets) - len(inside)
        first_outside: int | None = None
        if low > 0:
            first_outside = offsets[0]
        elif high < len(offsets):
            first_outside = offsets[high]
        past_image = item.end > comparable
        if size_delta or past_image:
            klass = "size-differs"
        elif inside:
            klass = "text-differs"
        elif outside_count:
            klass = "text-exact"
        else:
            klass = "exact"
        verdicts.append(
            RangeVerdict(
                name=item.name,
                start=item.start,
                end=item.end,
                klass=klass,
                in_range_words=len({offset & ~3 for offset in inside}),
                in_range_bytes=len(inside),
                out_of_range_bytes=outside_count,
                first_in_range=inside[0] if inside else None,
                first_out_of_range=first_outside,
                size_delta=size_delta,
                past_image=past_image,
            )
        )
    return LinkedComparison(
        built=built_name,
        target=target_name,
        built_size=len(built),
        target_size=len(target),
        differing_bytes=len(offsets),
        verdicts=tuple(verdicts),
        first_difference=offsets[0] if offsets else None,
    )


def render(comparison: LinkedComparison) -> list[str]:
    """Render the comparison as the table a reader reads first."""

    lines = [
        f"linked-compare {comparison.built} against {comparison.target}",
        f"  image           {comparison.built_size} bytes vs "
        f"{comparison.target_size} bytes "
        f"({comparison.size_delta:+d}), {comparison.differing_bytes} "
        "differing byte(s)",
    ]
    if comparison.first_difference is not None:
        lines.append(f"  first difference 0x{comparison.first_difference:x}")
    if not comparison.verdicts:
        lines.append("  ranges          none supplied; image-level verdict only")
    else:
        lines.append(
            f"  {'range':34} {'class':16} {'words':>6} {'collateral':>11}  first"
        )
        for item in comparison.verdicts:
            first = (
                f"0x{item.first_in_range:x}"
                if item.first_in_range is not None
                else (
                    f"outside 0x{item.first_out_of_range:x}"
                    if item.first_out_of_range is not None
                    else "-"
                )
            )
            lines.append(
                f"  {item.name:34} {item.klass:16} {item.in_range_words:>6} "
                f"{item.out_of_range_bytes:>11}  {first}"
            )
    lines.append(f"  verdict         {comparison.klass}")
    return lines


__all__ = [
    "CLASS_ORDER",
    "LINKED_COMPARE_SCHEMA",
    "RANGES_SCHEMA",
    "ImageRange",
    "LinkedComparison",
    "RangeError",
    "RangeVerdict",
    "compare_images",
    "differing_offsets",
    "parse_range_argument",
    "parse_ranges",
    "render",
]
