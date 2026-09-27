"""Read source-pinned AS1 predicates without inventing source-level causes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .instrument_as1_motion import AS1_SHA256

COMMON = {"invocation", "query", "src", "dst"}
MASK_FIELDS = {
    "slot",
    "kind",
    "block",
    "instruction",
    "candidate_def0",
    "candidate_def1",
    "candidate_def2",
    "path_def0",
    "path_def1",
    "path_def2",
}
COST_FIELDS = {
    "outcome",
    "src_slot",
    "dst_slot",
    "src_old",
    "dst_old",
    "src_new",
    "dst_new",
    "context",
}


def _fields(line: str) -> tuple[str, dict[str, Any]]:
    parts = line.split()
    fields: dict[str, Any] = {}
    for part in parts[1:]:
        key, separator, value = part.partition("=")
        if not separator or not value or key in fields:
            raise ValueError("malformed or duplicate AS1 field")
        if key not in {"site", "kind", "outcome", "source_sha256"}:
            if not value.isascii() or not value.isdecimal():
                raise ValueError("AS1 numeric fields must be unsigned decimal")
            fields[key] = int(value)
        else:
            fields[key] = value
    return parts[0].removeprefix("DKWB-AS1-"), fields


def decode_register_mask(words: list[int]) -> list[int]:
    """f_addset's MSB-first IDs; not source variable identities."""
    if len(words) != 3 or any(word < 0 or word > 0xFFFFFFFF for word in words):
        raise ValueError("register masks require three unsigned 32-bit words")
    return [
        index
        for index in range(72)
        if words[index // 32] & (0x80000000 >> (index % 32))
    ]


def predicate_report(text: str) -> dict[str, Any]:
    profiles: set[int] = set()
    queries: dict[tuple[int, int], dict[str, Any]] = {}
    ignored = 0
    for line in text.splitlines():
        if not line.startswith("DKWB-AS1-"):
            if "DKWB-AS1-" in line:
                raise ValueError("interleaved AS1 record; capture stderr separately")
            ignored += bool(line.strip())
            continue
        kind, fields = _fields(line)
        if kind == "PROFILE":
            if (
                set(fields) != {"version", "source_sha256", "invocation"}
                or fields["version"] != 1
                or fields["source_sha256"] != AS1_SHA256
            ):
                raise ValueError("unsupported AS1 producer profile")
            invocation = fields["invocation"]
            if invocation < 1 or invocation in profiles:
                raise ValueError("duplicate or invalid AS1 invocation")
            profiles.add(invocation)
            continue
        required = {
            "PRED": COMMON | {"slot", "site", "value"},
            "RESULT": COMMON | {"slot"},
            "MASK": COMMON | MASK_FIELDS,
            "COST": COMMON | COST_FIELDS,
        }.get(kind)
        if required is None or not required <= fields.keys():
            raise ValueError("unknown or incomplete AS1 record")
        extra = fields.keys() - required
        if kind != "PRED" and extra:
            raise ValueError("unknown AS1 fields")
        if kind == "PRED" and any(
            name
            not in {
                "at",
                "fp",
                "v0",
                "v1",
                *[f"{p}{i}" for p in "ast" for i in range(10)],
            }
            for name in extra
        ):
            raise ValueError("unknown raw predicate operand")
        if fields["invocation"] not in profiles or fields["query"] < 1:
            raise ValueError("AS1 record lacks authenticated invocation")
        key = fields["invocation"], fields["query"]
        query = queries.setdefault(
            key,
            {
                "invocation": key[0],
                "query": key[1],
                "src": fields["src"],
                "dst": fields["dst"],
                "predicates": [],
                "masks": [],
                "result": None,
                "cost": [],
            },
        )
        if (query["src"], query["dst"]) != (fields["src"], fields["dst"]):
            raise ValueError("AS1 query changed endpoint identity")
        if kind == "PRED":
            site = fields["site"]
            valid_sites = {f"admit-{i:02d}" for i in range(29)} | {
                f"path-{i:02d}" for i in range(30)
            }
            if (
                site not in valid_sites
                or fields["value"] not in (0, 1)
                or query["result"] is not None
            ):
                raise ValueError("invalid or out-of-order AS1 predicate")
            query["predicates"].append(fields)
        elif kind == "MASK":
            if (
                fields["kind"] not in {"contributor", "aggregate"}
                or query["result"] is not None
            ):
                raise ValueError("invalid or out-of-order AS1 mask")
            candidate = [fields[f"candidate_def{i}"] for i in range(3)]
            path = [fields[f"path_def{i}"] for i in range(3)]
            fields["candidate_register_ids"] = decode_register_mask(candidate)
            fields["path_register_ids"] = decode_register_mask(path)
            fields["intersection_register_ids"] = decode_register_mask(
                [a & b for a, b in zip(candidate, path, strict=True)]
            )
            query["masks"].append(fields)
        elif kind == "RESULT":
            if query["result"] is not None:
                raise ValueError("duplicate AS1 admission result")
            query["result"] = fields["slot"]
        else:
            outcome = fields["outcome"]
            previous = query["cost"]
            if (
                query["result"] is None
                or query["result"] == 0
                or query["result"] != fields["src_slot"]
            ):
                raise ValueError("AS1 trial lacks matching admitted slot")
            if (not previous and outcome != "trial") or (
                previous
                and (len(previous) != 1 or outcome not in {"accepted", "rollback"})
            ):
                raise ValueError("AS1 cost outcome is not a paired trial")
            if previous and any(
                fields[name] != previous[0][name] for name in COST_FIELDS - {"outcome"}
            ):
                raise ValueError("AS1 trial and outcome costs conflict")
            previous.append(fields)
    for query in queries.values():
        if query["result"] is None or (query["result"] and len(query["cost"]) != 2):
            raise ValueError("truncated AS1 query or trial")
        query["status"] = (
            "no-candidate-admitted"
            if query["result"] == 0
            else query["cost"][-1]["outcome"]
        )
    return {
        "profile": "as1-motion-predicates-v1",
        "source_sha256": AS1_SHA256,
        "invocations": sorted(profiles),
        "queries": list(queries.values()),
        "ignored_lines": ignored,
        "limits": [
            "Block, slot, query and invocation IDs are run-local, not "
            "semantic identities.",
            "Raw branch predicates require the source-pinned manifest; "
            "truth is not always rejection.",
            "Only DEF/DEF path masks are decoded; other predicates retain "
            "raw operands.",
            "No records or omitted queries do not prove absence; producer "
            "filters may be active.",
            "No source variable, C lever, target compiler IR or match "
            "verdict is inferred.",
        ],
    }


def compare_queries(
    left: dict[str, Any], right: dict[str, Any], left_slot: int, right_slot: int
) -> dict[str, Any]:
    """Compare explicitly selected candidates, preserving repeated predicate visits."""

    def candidate(query: dict[str, Any], slot: int) -> dict[str, Any]:
        if slot < 1:
            raise ValueError("candidate slots must be positive")
        predicates = [row for row in query["predicates"] if row["slot"] == slot]
        if not predicates:
            raise ValueError("selected candidate has no predicate records")
        return {
            "slot": slot,
            "predicates": predicates,
            "masks": [row for row in query["masks"] if row["slot"] == slot],
        }

    return {
        "comparison_basis": "explicit candidate selection; semantic identity unproved",
        "left": candidate(left, left_slot),
        "right": candidate(right, right_slot),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args(argv)
    try:
        report = predicate_report(args.trace.read_text())
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
