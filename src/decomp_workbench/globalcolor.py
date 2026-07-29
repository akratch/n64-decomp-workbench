"""Parsers for the uopt globalcolor traces used by the workbench."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field


def callee_saved_color_name(color: int | None) -> str | None:
    """Name stable callee-saved colors from the pinned IDO profile.

    Other color values remain compiler colors. Guessing names for them would
    make a trace friendlier but less reliable across profiles.
    """

    if color is None or not 14 <= color <= 22:
        return None
    return f"s{color - 14}"


FLOAT_PATTERN = (
    r"(?:[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
    r"|[-+]?(?:inf|nan))"
)
CSAVE_RE = re.compile(
    r"^CSAVE\s+bitpos=(?P<bitpos>\d+)\s+"
    r"kind=(?P<kind>\d+)\s+dtype=(?P<dtype>\d+)\s+"
    r"unk1C=(?P<weight>-?\d+)\s+"
    rf"adjsave=(?P<adjusted_save>{FLOAT_PATTERN})\s+"
    r"unk23=(?P<flag>\d+)",
    re.IGNORECASE,
)
CUP_RE = re.compile(
    r"^CUP\s+bitpos=(?P<bitpos>\d+)\s+"
    r"reg=(?P<register>-?\d+)\s+cs=(?P<color_class>-?\d+)\s+"
    rf"cost=(?P<cost>{FLOAT_PATTERN})",
    re.IGNORECASE,
)
CDX_RE = re.compile(r"^\[CDX\]\s+(?P<phase>\S+)\s+(?P<fields>.*)$")
FIELD_RE = re.compile(r"([A-Za-z0-9_]+)=([^\s]+)")


@dataclass(frozen=True)
class ColorCost:
    """The measured cost of assigning one color/register."""

    register: int
    color_class: int
    cost: float

    def as_dict(self) -> dict[str, object]:
        return {
            "register": self.register,
            "color_class": self.color_class,
            "cost": serialize_float(self.cost),
        }


@dataclass
class LiveRange:
    """One live range or web observed by CSAVE/CUP instrumentation."""

    bitpos: int
    kind: int
    dtype: int
    weight: int
    adjusted_save: float
    flag: int
    color_costs: list[ColorCost] = field(default_factory=list)

    @property
    def total_save(self) -> float:
        """Historical campaign metric: adjusted save multiplied by weight."""

        return self.adjusted_save * self.weight

    @property
    def finite_costs(self) -> list[ColorCost]:
        return [item for item in self.color_costs if math.isfinite(item.cost)]

    def as_dict(self) -> dict[str, object]:
        return {
            "bitpos": self.bitpos,
            "kind": self.kind,
            "dtype": self.dtype,
            "weight": self.weight,
            "adjusted_save": serialize_float(self.adjusted_save),
            "flag": self.flag,
            "color_costs": [item.as_dict() for item in self.color_costs],
            "total_save": serialize_float(self.total_save),
            "finite_color_costs": [item.as_dict() for item in self.finite_costs],
        }


@dataclass(frozen=True)
class ColorDecision:
    """A higher-level CDX globalcolor decision record."""

    phase: str
    fields: dict[str, str]
    raw: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AllocatorWebDecision:
    """One allocator decision joined with optional webdetail metadata."""

    proc: int
    web: int
    phase: str
    fields: dict[str, str]
    detail: dict[str, str]
    color_costs: list[dict[str, str]]

    @property
    def dtype(self) -> int | None:
        value = self.detail.get("dtype")
        return int(value, 0) if value is not None else None

    @property
    def total_save(self) -> float:
        value = self.fields.get("totalsave", "nan")
        return float(value)

    @property
    def assigned_color(self) -> int | None:
        """Return the selected color when this decision allocated one."""

        value = self.fields.get("bestcolor")
        if value is None:
            return None
        try:
            return int(value, 0)
        except ValueError:
            return None

    @property
    def assigned_register(self) -> str | None:
        """Return a physical register name only when the mapping is stable."""

        return callee_saved_color_name(self.assigned_color)

    @property
    def explanation(self) -> str:
        """Human-scale explanation suitable for a focused web inspection."""

        decision = self.fields.get("decision", "unknown")
        if decision == "split":
            return (
                "split: this web was divided instead of receiving one "
                "allocation; inspect its live range and interference edges"
            )
        color = self.assigned_color
        if color is None:
            return f"{decision}: no selected color was recorded"
        register = self.assigned_register
        target = f"c{color}" + (f" ({register})" if register else "")
        return f"{decision}: selected {target}"

    def as_dict(self) -> dict[str, object]:
        return {
            "proc": self.proc,
            "web": self.web,
            "phase": self.phase,
            "fields": self.fields,
            "detail": self.detail,
            "color_costs": self.color_costs,
            "assigned_color": self.assigned_color,
            "assigned_register": self.assigned_register,
            "explanation": self.explanation,
        }


@dataclass
class GlobalColorTrace:
    """Parsed globalcolor live ranges and decisions."""

    live_ranges: dict[int, LiveRange]
    decisions: list[ColorDecision]
    unparsed_diagnostic_lines: list[str]

    def ranked(
        self, *, dtype: int | None = None, limit: int | None = None
    ) -> list[LiveRange]:
        selected = [
            item
            for item in self.live_ranges.values()
            if dtype is None or item.dtype == dtype
        ]
        selected.sort(
            key=lambda item: (
                math.isnan(item.total_save),
                -item.total_save if not math.isnan(item.total_save) else 0.0,
                item.bitpos,
            )
        )
        return selected[:limit] if limit else selected

    def decisions_for(self, proc: int | None = None) -> list[ColorDecision]:
        """Return decisions for one globalcolor invocation, or all decisions."""

        if proc is None:
            return self.decisions
        return [item for item in self.decisions if item.fields.get("proc") == str(proc)]

    def allocator_webs(
        self,
        *,
        proc: int | None = None,
        web: int | None = None,
        dtype: int | None = None,
        limit: int | None = None,
    ) -> list[AllocatorWebDecision]:
        """Join p1/p2 decisions to target webdetail records."""

        details: dict[tuple[int, int], dict[str, str]] = {}
        costs: dict[tuple[int, int, str], list[dict[str, str]]] = {}
        for item in self.decisions:
            if "proc" not in item.fields or "web" not in item.fields:
                continue
            key = (int(item.fields["proc"], 0), int(item.fields["web"], 0))
            if item.phase == "webdetail" and item.fields.get("role") == "target":
                details[key] = item.fields
            elif item.phase in {"p1cost", "p2cost"}:
                costs.setdefault((*key, item.phase[:2]), []).append(item.fields)

        joined: list[AllocatorWebDecision] = []
        for item in self.decisions:
            if item.phase not in {"p1dec", "p2dec"}:
                continue
            if "proc" not in item.fields or "web" not in item.fields:
                continue
            item_proc = int(item.fields["proc"], 0)
            item_web = int(item.fields["web"], 0)
            detail = details.get((item_proc, item_web), {})
            joined_item = AllocatorWebDecision(
                proc=item_proc,
                web=item_web,
                phase=item.phase,
                fields=item.fields,
                detail=detail,
                color_costs=costs.get((item_proc, item_web, item.phase[:2]), []),
            )
            if proc is not None and item_proc != proc:
                continue
            if web is not None and item_web != web:
                continue
            if dtype is not None and joined_item.dtype != dtype:
                continue
            joined.append(joined_item)
        joined.sort(
            key=lambda item: (
                math.isnan(item.total_save),
                -item.total_save if not math.isnan(item.total_save) else 0.0,
                item.proc,
                item.web,
                item.phase,
            )
        )
        return joined[:limit] if limit else joined

    def as_dict(self) -> dict[str, object]:
        return {
            "live_ranges": [item.as_dict() for item in self.ranked()],
            "allocator_webs": [item.as_dict() for item in self.allocator_webs()],
            "decisions": [item.as_dict() for item in self.decisions],
            "unparsed_diagnostic_lines": self.unparsed_diagnostic_lines,
        }


def serialize_float(value: float) -> float | str:
    """Return finite values as numbers and non-finite values as JSON strings."""

    if math.isfinite(value):
        return value
    if math.isnan(value):
        return "nan"
    return "inf" if value > 0 else "-inf"


def parse_globalcolor_trace(text: str) -> GlobalColorTrace:
    """Parse the stable CSAVE/CUP format and the later CDX format."""

    live_ranges: dict[int, LiveRange] = {}
    pending_costs: dict[int, list[ColorCost]] = {}
    decisions: list[ColorDecision] = []
    unparsed: list[str] = []

    for raw in text.splitlines():
        line = raw.strip()
        save = CSAVE_RE.match(line)
        if save:
            values = save.groupdict()
            bitpos = int(values["bitpos"])
            live_ranges[bitpos] = LiveRange(
                bitpos=bitpos,
                kind=int(values["kind"]),
                dtype=int(values["dtype"]),
                weight=int(values["weight"]),
                adjusted_save=float(values["adjusted_save"]),
                flag=int(values["flag"]),
                color_costs=pending_costs.pop(bitpos, []),
            )
            continue
        cost = CUP_RE.match(line)
        if cost:
            values = cost.groupdict()
            bitpos = int(values["bitpos"])
            item = ColorCost(
                register=int(values["register"]),
                color_class=int(values["color_class"]),
                cost=float(values["cost"]),
            )
            if bitpos in live_ranges:
                live_ranges[bitpos].color_costs.append(item)
            else:
                pending_costs.setdefault(bitpos, []).append(item)
            continue
        decision = CDX_RE.match(line)
        if decision:
            decisions.append(
                ColorDecision(
                    phase=decision.group("phase"),
                    fields={
                        key: value
                        for key, value in FIELD_RE.findall(decision.group("fields"))
                    },
                    raw=raw,
                )
            )
            continue
        if line.startswith(("CSAVE", "CUP", "[CDX]")):
            unparsed.append(raw)

    for bitpos in pending_costs:
        unparsed.append(f"CUP records for bitpos={bitpos} appeared without CSAVE")
    return GlobalColorTrace(
        live_ranges=live_ranges,
        decisions=decisions,
        unparsed_diagnostic_lines=unparsed,
    )
