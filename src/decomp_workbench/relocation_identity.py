"""Declarative, project-supplied identities for relocation sites.

The workbench deliberately does not parse a game's overlay atlas. A project
provider translates its own ownership model into this code-free interchange
schema; this module validates the result and joins it to the generic relocation
surface without guessing from a synthetic VMA or a target row position.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .reloc_surface import Site

IDENTITY_PROVIDER_SCHEMA = "decomp-workbench-relocation-identities-v1"
IDENTITY_REPORT_SCHEMA = "decomp-workbench-relocation-identity-report-v1"
STATUSES = frozenset({"resolved", "unknown", "contradicted"})


@dataclass(frozen=True)
class SiteKey:
    object: str
    section: str
    offset: int
    type: int
    symbol: str

    @classmethod
    def from_site(cls, site: Site) -> SiteKey:
        return cls(
            object=site.object,
            section=site.section,
            offset=site.object_offset,
            type=site.type,
            symbol=site.symbol,
        )


@dataclass(frozen=True)
class RelocationIdentity:
    key: SiteKey
    status: str
    namespace: str | None = None
    module: str | None = None
    section: str | None = None
    offset: int | None = None
    addend: int = 0
    evidence: str = ""

    def as_dict(self) -> dict[str, Any]:
        identity = None
        if self.status == "resolved":
            identity = {
                "namespace": self.namespace,
                "module": self.module,
                "section": self.section,
                "offset": self.offset,
                "addend": self.addend,
            }
        return {
            "object": self.key.object,
            "section": self.key.section,
            "object_offset": self.key.offset,
            "type": self.key.type,
            "symbol": self.key.symbol,
            "status": self.status,
            "identity": identity,
            "evidence": self.evidence,
        }


def _integer(value: object, *, where: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{where} must be an integer, not a boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            pass
    raise ValueError(f"{where} must be an integer or 0x-prefixed integer string")


def _text(value: object, *, where: str, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where} must be a non-empty string")
    return value.strip()


def parse_identity_provider(value: object) -> dict[SiteKey, RelocationIdentity]:
    """Validate one provider result and index it by exact object relocation site."""

    if (
        not isinstance(value, Mapping)
        or value.get("schema") != IDENTITY_PROVIDER_SCHEMA
    ):
        raise ValueError(f"identity provider schema must be {IDENTITY_PROVIDER_SCHEMA}")
    entries = value.get("entries")
    if not isinstance(entries, Sequence) or isinstance(entries, str | bytes):
        raise ValueError("identity provider entries must be a list")
    result: dict[SiteKey, RelocationIdentity] = {}
    for index, raw in enumerate(entries):
        where = f"identity provider entry {index}"
        if not isinstance(raw, Mapping):
            raise ValueError(f"{where} must be an object")
        key = SiteKey(
            object=_text(raw.get("object"), where=f"{where}.object") or "",
            section=_text(raw.get("section"), where=f"{where}.section") or "",
            offset=_integer(raw.get("object_offset"), where=f"{where}.object_offset"),
            type=_integer(raw.get("type"), where=f"{where}.type"),
            symbol=_text(raw.get("symbol"), where=f"{where}.symbol") or "",
        )
        if key.offset < 0 or key.type < 0:
            raise ValueError(f"{where} contains a negative offset or type")
        if key in result:
            raise ValueError(f"{where} duplicates an exact relocation site")
        status = _text(raw.get("status"), where=f"{where}.status") or ""
        if status not in STATUSES:
            raise ValueError(
                f"{where}.status must be resolved, unknown, or contradicted"
            )
        identity_raw = raw.get("identity")
        namespace = module = identity_section = None
        identity_offset = None
        addend = 0
        if status == "resolved":
            if not isinstance(identity_raw, Mapping):
                raise ValueError(f"{where}.identity is required when status=resolved")
            namespace = _text(
                identity_raw.get("namespace"), where=f"{where}.identity.namespace"
            )
            module = _text(identity_raw.get("module"), where=f"{where}.identity.module")
            identity_section = _text(
                identity_raw.get("section"), where=f"{where}.identity.section"
            )
            identity_offset = _integer(
                identity_raw.get("offset"), where=f"{where}.identity.offset"
            )
            addend = _integer(
                identity_raw.get("addend", 0), where=f"{where}.identity.addend"
            )
            if identity_offset < 0:
                raise ValueError(f"{where}.identity.offset must be non-negative")
        elif identity_raw is not None:
            raise ValueError(f"{where}.identity is allowed only when status=resolved")
        result[key] = RelocationIdentity(
            key=key,
            status=status,
            namespace=namespace,
            module=module,
            section=identity_section,
            offset=identity_offset,
            addend=addend,
            evidence=_text(
                raw.get("evidence", ""), where=f"{where}.evidence", required=False
            )
            or "",
        )
    return result


def identity_report(
    sites: Sequence[Site], provider: Mapping[SiteKey, RelocationIdentity]
) -> dict[str, Any]:
    """Join exact sites, distinguishing absent knowledge from contradiction."""

    rows: list[dict[str, Any]] = []
    consumed: set[SiteKey] = set()
    counts = {status: 0 for status in STATUSES}
    for site in sites:
        key = SiteKey.from_site(site)
        supplied = provider.get(key)
        if supplied is None:
            row = RelocationIdentity(key=key, status="unknown")
        else:
            row = supplied
            consumed.add(key)
        counts[row.status] += 1
        rows.append(row.as_dict())
    unused = [
        provider[key].as_dict() for key in sorted(set(provider) - consumed, key=repr)
    ]
    return {
        "schema": IDENTITY_REPORT_SCHEMA,
        "sites": len(sites),
        "resolved": counts["resolved"],
        "unknown": counts["unknown"],
        "contradicted": counts["contradicted"],
        "complete": bool(sites)
        and counts["resolved"] == len(sites)
        and counts["contradicted"] == 0,
        "entries": rows,
        "unused_provider_entries": unused,
    }


__all__ = [
    "IDENTITY_PROVIDER_SCHEMA",
    "IDENTITY_REPORT_SCHEMA",
    "RelocationIdentity",
    "SiteKey",
    "identity_report",
    "parse_identity_provider",
]
