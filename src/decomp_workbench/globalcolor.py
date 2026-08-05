"""Parsers for the uopt globalcolor traces used by the workbench."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field

# Color to machine register for the pinned IDO 5.3 profile. Phase one and
# phase two share this space, so one number means one register in both.
# Provenance, with its limits, is recorded in docs/compiler-instrumentation.md:
# c1-c5 were confirmed empirically by forcing each color and diffing the
# object; the rest follow the coloroffset table decode and pool-order probing.
# Colors outside the table stay numeric: naming them would be a guess.
COLOR_REGISTERS: dict[int, str] = {
    1: "v0",
    2: "v1",
    3: "a0",
    4: "a1",
    5: "a2",
    6: "a3",
    **{7 + index: f"t{index}" for index in range(6)},
    **{14 + index: f"s{index}" for index in range(9)},
    23: "ra",
}


def register_for_color(color: int | None) -> str | None:
    """Name a color's machine register where the pinned profile confirms it."""

    return None if color is None else COLOR_REGISTERS.get(color)


def color_for_register(register: str) -> int | None:
    """Return the pinned allocator color for one physical register name."""

    normalized = register.removeprefix("$").lower()
    return next(
        (color for color, name in COLOR_REGISTERS.items() if name == normalized),
        None,
    )


#: Highest color the two forbidden/available mask words can describe.
MAX_MASK_COLOR = 63


def color_is_forbidden(forbidden0: int, forbidden1: int, color: int) -> bool:
    """Return whether a web's interference mask rules one color out.

    The decode ring is ``1 << (31 - color)`` in the first word, confirmed
    against a recorded trace where ``forbidden0=0x7f800000`` meant exactly
    c1-c8. The second word continues the same convention for colors 32-63; no
    color the profile can name reaches it, so that half is a documented
    extrapolation rather than an observation.

    This is the same rule the instrumented pass applies before honoring a
    ``CDX_FORCE``, so a probe can be checked against a trace without running it.
    """

    if color < 0 or color > MAX_MASK_COLOR:
        return False
    if color < 32:
        return bool((forbidden0 >> (31 - color)) & 1)
    return bool((forbidden1 >> (63 - color)) & 1)


def decode_forbidden_colors(forbidden0: int, forbidden1: int) -> list[int]:
    """Return every color the two mask words rule out, in ascending order."""

    return [
        color
        for color in range(MAX_MASK_COLOR + 1)
        if color_is_forbidden(forbidden0, forbidden1, color)
    ]


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

# IDO initializes an unavailable color cost to a finite float near 1e20. It
# is not an ordinary expensive choice: treating it as one produces absurd
# affinity gaps and can send a source search toward an impossible endpoint.
IDO_INELIGIBLE_COST_FLOOR = 1.0e19


def optional_integer(value: str | None) -> int | None:
    """Parse one optional trace integer without trusting diagnostic text."""

    if value is None:
        return None
    try:
        return int(value, 0)
    except ValueError:
        return None


def is_ineligible_allocator_cost(value: float) -> bool:
    """Return whether an IDO color cost is the unavailable-color sentinel."""

    return math.isfinite(value) and value >= IDO_INELIGIBLE_COST_FLOOR


@dataclass(frozen=True)
class ColorCost:
    """The measured cost of assigning one color/register."""

    register: int
    color_class: int
    cost: float

    @property
    def eligible(self) -> bool:
        return math.isfinite(self.cost) and not is_ineligible_allocator_cost(self.cost)

    def as_dict(self) -> dict[str, object]:
        return {
            "register": self.register,
            "color_class": self.color_class,
            "cost": serialize_float(self.cost),
            "eligible": self.eligible,
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

    @property
    def eligible_costs(self) -> list[ColorCost]:
        """Return real cost endpoints, excluding IDO's finite sentinel."""

        return [item for item in self.color_costs if item.eligible]

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
            "eligible_color_costs": [item.as_dict() for item in self.eligible_costs],
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
    interference: list[dict[str, object]]
    decision_trace_ordinal: int

    @property
    def dtype(self) -> int | None:
        return optional_integer(self.detail.get("dtype"))

    @property
    def total_save(self) -> float:
        value = self.fields.get("totalsave", "nan")
        try:
            return float(value)
        except ValueError:
            return math.nan

    @property
    def assigned_color(self) -> int | None:
        """Return the color the pass actually assigned.

        ``bestcolor`` is the allocator's natural choice at the decision site.
        A diagnostic force can override it at the later ``p1color``/``p2color``
        site, whose joined value is recorded as ``actualcolor``.  Falling back
        keeps older traces useful without misreporting forced controls.
        """

        value = self.fields.get("actualcolor", self.fields.get("bestcolor"))
        if value is None:
            return None
        color = optional_integer(value)
        return color if color is not None and color >= 0 else None

    @property
    def natural_color(self) -> int | None:
        """Return the allocator's pre-force best color, when recorded."""

        color = optional_integer(self.fields.get("bestcolor"))
        return color if color is not None and color >= 0 else None

    @property
    def phase_tag(self) -> str:
        """Return the allocator phase namespace: ``p1`` or ``p2``.

        Phase one and phase two emit disjoint web spaces, so a web number is
        only meaningful with its phase. Records carry an explicit ``phase``
        field; older traces are read from the record name.
        """

        return self.fields.get("phase") or self.phase[:2]

    @property
    def force_key(self) -> str:
        """Return the phase-qualified CDX_FORCE key for this web."""

        return f"{self.phase_tag}:w{self.web}"

    @property
    def assigned_register(self) -> str | None:
        """Return a physical register name only when the mapping is stable."""

        return register_for_color(self.assigned_color)

    @property
    def forbidden_colors(self) -> list[int]:
        """Return the colors this web's interference mask rules out.

        A ``CDX_FORCE`` naming one of these is declined by the instrumented
        pass, so this is the list to read before spending a probe on an
        endpoint that cannot exist.
        """

        first = optional_integer(self.fields.get("forbidden0"))
        if first is None:
            return []
        second = optional_integer(self.fields.get("forbidden1")) or 0
        return decode_forbidden_colors(first, second)

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

    def color_barrier(self, desired_color: int) -> dict[str, object]:
        """Measure the source-level barrier between natural and desired colors.

        This does not prescribe a source edit. It states the allocator fact a
        legal edit must change: interference eligibility or relative measured
        cost. Missing cost records stay explicit rather than becoming zero.
        """

        costs: dict[int, float] = {}
        for record in self.color_costs:
            color = optional_integer(record.get("color"))
            if color is None:
                continue
            try:
                costs[color] = float(record["cost"])
            except (KeyError, ValueError):
                continue
        natural_color = self.natural_color
        natural_cost = costs.get(natural_color) if natural_color is not None else None
        desired_cost = costs.get(desired_color)
        desired_forbidden = desired_color in self.forbidden_colors
        desired_ineligible = desired_cost is not None and is_ineligible_allocator_cost(
            desired_cost
        )
        gap = (
            desired_cost - natural_cost
            if (
                desired_cost is not None
                and natural_cost is not None
                and not desired_ineligible
                and not is_ineligible_allocator_cost(natural_cost)
            )
            else None
        )
        desired_register = register_for_color(desired_color)
        natural_register = register_for_color(natural_color)
        blocking_neighbors: list[dict[str, object]] = []
        for edge in self.interference:
            assigned = optional_integer(str(edge.get("assigned", "")))
            if assigned != desired_color:
                continue
            neighbor_web = optional_integer(str(edge.get("other", "")))
            neighbor_detail = edge.get("neighbor_detail")
            blocking_neighbors.append(
                {
                    "phase": self.phase_tag,
                    "web": neighbor_web,
                    "force_key": (
                        f"{self.phase_tag}:w{neighbor_web}"
                        if neighbor_web is not None
                        else None
                    ),
                    "assigned_color": assigned,
                    "assigned_register": register_for_color(assigned),
                    "detail": (
                        neighbor_detail if isinstance(neighbor_detail, dict) else {}
                    ),
                }
            )
        if desired_color == natural_color:
            status = "already-natural"
            advice = (
                "the desired color is already the allocator's natural choice; "
                "inspect any later force override or downstream recoloring "
                "instead of searching for a cost or tie-break source edit"
            )
        elif desired_forbidden:
            status = "desired-forbidden"
            if blocking_neighbors:
                blockers = ", ".join(
                    str(item["force_key"] or "unknown web")
                    for item in blocking_neighbors
                )
                advice = (
                    "the desired color is occupied by an interfering web "
                    f"({blockers}); reshape that overlap or create a legal "
                    "coalescing/reuse edge before testing relative cost"
                )
            else:
                advice = (
                    "the desired color is ruled out by interference; recapture "
                    f"with CDX_DETAIL_WEB={self.web} to name the blocking web"
                )
        elif desired_ineligible:
            status = "desired-ineligible"
            advice = (
                "the desired color has IDO's unavailable-cost sentinel, not a "
                "large affinity penalty; inspect the register-class/availability "
                "constraints before attempting a cost or tie-break source edit"
            )
        elif gap is None:
            status = "cost-unmeasured"
            advice = (
                "the trace does not contain both costs; capture p1cost/p2cost "
                "records before choosing a source lever"
            )
        elif gap > 0:
            status = "natural-cheaper"
            advice = (
                "make the natural color unavailable or improve the desired "
                f"color's relative cost/affinity by more than {gap:g}"
            )
        elif gap == 0:
            status = "tie-break"
            advice = (
                "both colors have equal measured cost; investigate traversal, "
                "coalescing, and tie-break order"
            )
        else:
            status = "desired-cheaper-but-unselected"
            advice = (
                "the desired color is cheaper in the captured costs; inspect "
                "eligibility and whether this cost record precedes selection"
            )
        return {
            "status": status,
            "natural_color": natural_color,
            "natural_register": natural_register,
            "natural_cost": (
                serialize_float(natural_cost) if natural_cost is not None else None
            ),
            "desired_color": desired_color,
            "desired_register": desired_register,
            "desired_cost": (
                serialize_float(desired_cost) if desired_cost is not None else None
            ),
            "desired_forbidden": desired_forbidden,
            "desired_ineligible": desired_ineligible,
            "blocking_neighbors": blocking_neighbors,
            "interference_recorded": bool(self.interference),
            "cost_gap": serialize_float(gap) if gap is not None else None,
            "advice": advice,
            "claim_boundary": (
                "a force tests the endpoint only; stock-compiler acceptance "
                "still requires a source-caused allocator decision"
            ),
        }

    def as_dict(self) -> dict[str, object]:
        return {
            "proc": self.proc,
            "web": self.web,
            "phase": self.phase,
            "phase_tag": self.phase_tag,
            "force_key": self.force_key,
            "fields": self.fields,
            "detail": self.detail,
            "color_costs": self.color_costs,
            "interference": self.interference,
            "decision_trace_ordinal": self.decision_trace_ordinal,
            "assigned_color": self.assigned_color,
            "assigned_register": self.assigned_register,
            "natural_color": self.natural_color,
            "natural_register": register_for_color(self.natural_color),
            "forbidden_colors": self.forbidden_colors,
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

    def decisions_for(
        self, proc: int | None = None, *, web: int | None = None
    ) -> list[ColorDecision]:
        """Return decisions filtered to one invocation and allocator web."""

        selected: list[ColorDecision] = []
        for item in self.decisions:
            proc_value = optional_integer(item.fields.get("proc"))
            web_value = optional_integer(item.fields.get("web"))
            if proc is not None and proc_value != proc:
                continue
            if web is not None and web_value != web:
                continue
            selected.append(item)
        return selected

    def lineage_for(
        self,
        proc: int | None = None,
        *,
        tables: set[int] | None = None,
    ) -> list[ColorDecision]:
        """Return opt-in live-range formation records.

        These records are keyed by the ICHAIN table/chain identity that exists
        before globalcolor assigns a run-local web number.  They deliberately
        remain structural evidence rather than source-semantic attribution.
        """

        selected: list[ColorDecision] = []
        for item in self.decisions:
            if item.phase not in {"lineage_range", "lineage_member"}:
                continue
            item_proc = optional_integer(item.fields.get("proc"))
            item_table = optional_integer(item.fields.get("table"))
            if proc is not None and item_proc != proc:
                continue
            if tables is not None and item_table not in tables:
                continue
            selected.append(item)
        return selected

    def allocator_webs(
        self,
        *,
        proc: int | None = None,
        web: int | None = None,
        dtype: int | None = None,
        limit: int | None = None,
    ) -> list[AllocatorWebDecision]:
        """Join p1/p2 decisions to target webdetail and provenance snapshots."""

        decision_phases: dict[tuple[int, int], set[str]] = {}
        for item in self.decisions:
            if item.phase not in {"p1dec", "p2dec"}:
                continue
            item_proc = optional_integer(item.fields.get("proc"))
            item_web = optional_integer(item.fields.get("web"))
            if item_proc is None or item_web is None:
                continue
            decision_phases.setdefault((item_proc, item_web), set()).add(
                item.fields.get("phase") or item.phase[:2]
            )

        details: dict[tuple[int, int, str], dict[str, str]] = {}
        legacy_details: dict[tuple[int, int], dict[str, str]] = {}
        costs: dict[tuple[int, int, str], list[dict[str, str]]] = {}
        interference: dict[tuple[int, int, str], list[dict[str, str]]] = {}
        neighbor_details: dict[tuple[int, int, str], list[dict[str, str]]] = {}
        provenance: dict[tuple[int, int, str], dict[str, list[dict[str, str]]]] = {}
        allocations: dict[tuple[int, int, str], list[dict[str, str]]] = {}
        for item in self.decisions:
            if "proc" not in item.fields or "web" not in item.fields:
                continue
            item_proc = optional_integer(item.fields["proc"])
            item_web = optional_integer(item.fields["web"])
            if item_proc is None or item_web is None:
                continue
            key = (item_proc, item_web)
            if item.phase == "webdetail" and item.fields.get("role") == "target":
                detail_phase = item.fields.get("phase")
                if detail_phase in {"p1", "p2"}:
                    details[(*key, detail_phase)] = item.fields
                else:
                    legacy_details[key] = item.fields
            elif item.phase == "webdetail" and item.fields.get("role") == "neighbor":
                detail_phase = item.fields.get("phase")
                if detail_phase in {"p1", "p2"}:
                    neighbor_details.setdefault((*key, detail_phase), []).append(
                        item.fields
                    )
            elif item.phase == "intf":
                detail_phase = item.fields.get("phase")
                if detail_phase in {"p1", "p2"}:
                    interference.setdefault((*key, detail_phase), []).append(
                        item.fields
                    )
            elif item.phase in {"p1cost", "p2cost"}:
                costs.setdefault((*key, item.phase[:2]), []).append(item.fields)
            elif item.phase == "provenance_web":
                detail_phase = item.fields.get("phase")
                snapshot = item.fields.get("snapshot")
                if detail_phase in {"p1", "p2"} and snapshot in {
                    "preselect",
                    "postselect",
                }:
                    provenance.setdefault((*key, detail_phase), {}).setdefault(
                        snapshot, []
                    ).append(item.fields)
            elif item.phase in {"p1color", "p2color"}:
                allocations.setdefault((*key, item.phase[:2]), []).append(item.fields)

        def unique_provenance(
            entries: dict[str, list[dict[str, str]]] | None,
        ) -> dict[str, str]:
            """Join one pre/post pair while retaining stable provenance.

            Selection fields are expected to differ when a force overrides the
            natural choice.  Withholding the entire record in that case loses
            the very owner identity needed to interpret the control, so changed
            fields are preserved under explicit snapshot-qualified names.
            """

            if entries is None or set(entries) != {"preselect", "postselect"}:
                return {}
            if any(len(entries[snapshot]) != 1 for snapshot in entries):
                return {}
            before = entries["preselect"][0]
            after = entries["postselect"][0]
            merged: dict[str, str] = {}
            for field_name in sorted(set(before) | set(after)):
                if field_name == "snapshot":
                    continue
                pre_value = before.get(field_name)
                post_value = after.get(field_name)
                if pre_value == post_value and pre_value is not None:
                    merged[field_name] = pre_value
                else:
                    if pre_value is not None:
                        merged[f"preselect_{field_name}"] = pre_value
                    if post_value is not None:
                        merged[f"postselect_{field_name}"] = post_value
            return merged

        joined: list[AllocatorWebDecision] = []
        decision_trace_counts: dict[tuple[int, str], int] = {}
        for item in self.decisions:
            if item.phase not in {"p1dec", "p2dec"}:
                continue
            if "proc" not in item.fields or "web" not in item.fields:
                continue
            item_proc = optional_integer(item.fields["proc"])
            item_web = optional_integer(item.fields["web"])
            if item_proc is None or item_web is None:
                continue
            key = (item_proc, item_web)
            phase = item.fields.get("phase") or item.phase[:2]
            ordinal_key = (item_proc, phase)
            decision_trace_counts[ordinal_key] = (
                decision_trace_counts.get(ordinal_key, 0) + 1
            )
            detail = details.get((*key, phase))
            if detail is None and decision_phases.get(key) == {phase}:
                detail = legacy_details.get(key)
            provenance_detail = unique_provenance(provenance.get((*key, phase)))
            if provenance_detail:
                detail = {**provenance_detail, **(detail or {})}
            decision_fields = dict(item.fields)
            allocation_rows = allocations.get((*key, phase), [])
            if len(allocation_rows) == 1:
                actual_color = allocation_rows[0].get("color")
                actual_register = allocation_rows[0].get("reg")
                if actual_color is not None:
                    decision_fields["actualcolor"] = actual_color
                if actual_register is not None:
                    decision_fields["actualreg"] = actual_register
            joined_interference: list[dict[str, object]] = []
            for edge in interference.get((*key, phase), []):
                joined_edge: dict[str, object] = dict(edge)
                other = optional_integer(edge.get("other"))
                candidates = (
                    neighbor_details.get((item_proc, other, phase), [])
                    if other is not None
                    else []
                )
                unique_candidates = {
                    tuple(sorted(candidate.items())) for candidate in candidates
                }
                if len(unique_candidates) == 1:
                    joined_edge["neighbor_detail"] = dict(unique_candidates.pop())
                joined_interference.append(joined_edge)
            joined_item = AllocatorWebDecision(
                proc=item_proc,
                web=item_web,
                phase=item.phase,
                fields=decision_fields,
                detail=detail or {},
                color_costs=costs.get((item_proc, item_web, item.phase[:2]), []),
                interference=joined_interference,
                decision_trace_ordinal=decision_trace_counts[ordinal_key],
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
