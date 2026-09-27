"""Trace-only, source-pinned IDO 5.3 AS1 admission and rollback probes.

Predicate IDs describe generated-C branches, not inferred source semantics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AS1_SHA256 = "905927751a79aba82d332bdce254b2b30a4312ae14a4108897e11b48487d17a1"
UPSTREAM_COMMIT = "9c242adc890beef098020149d9554f48208f699d"
MARKER = "DKWB_AS1_MOTION_PREDICATES_V1"
HEADER = r"""
/* DKWB_AS1_MOTION_PREDICATES_V1: trace only; no behavior controls. */
static unsigned long dkwb_as1_invocation;
static unsigned long dkwb_as1_query;
static unsigned dkwb_as1_slot;
static int dkwb_as1_on(void) {
    const char *v = getenv("DKWB_AS1_MOTION_TRACE");
    return v && *v && *v != '0';
}
static int dkwb_as1_selected(unsigned src, unsigned dst) {
    const char *s = getenv("DKWB_AS1_MOTION_SRC");
    const char *d = getenv("DKWB_AS1_MOTION_DST");
    return dkwb_as1_on() && (!s || strtoul(s, 0, 10) == src)
        && (!d || strtoul(d, 0, 10) == dst);
}
"""


@dataclass(frozen=True)
class MotionInstrumentation:
    source: str
    input_sha256: str
    predicates: tuple[dict[str, Any], ...]


def _replace(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("AS1 motion anchor missing or duplicated")
    return source.replace(old, new, 1)


def _function(source: str, name: str) -> tuple[int, int]:
    pattern = r"^static [^\n]+ " + re.escape(name) + r"\([^\n]+\) \{\n"
    matches = list(re.finditer(pattern, source, re.M))
    if len(matches) != 1:
        raise ValueError("AS1 function definition missing or duplicated: " + name)
    start = matches[0].start()
    end = source.index("\n}\n", matches[0].end()) + 3
    return start, end


def _instrument_admission(
    body: str,
    *,
    prefix: str = "admit",
    expected: int = 29,
    slot: str = "s2",
    main: bool = True,
) -> tuple[str, list[dict[str, Any]]]:
    branches = list(re.finditer(r"^if \((.*)\) \{", body, re.M))
    if len(branches) != expected:
        raise ValueError("AS1 admission branch count changed")
    records = []
    for index, branch in reversed(list(enumerate(branches))):
        expression = branch[1]
        # The pinned branches contain only register reads, casts and operators.
        names = sorted(set(re.findall(r"\b(?:at|v[01]|[ast][0-9]|fp)\b", expression)))
        remainder = re.sub(
            r"\b(?:int|uint32_t|at|v[01]|[ast][0-9]|fp)\b|0x[0-9a-f]+|\d+|[\s()!<>=&|+-]",
            "",
            expression,
        )
        if (
            remainder
            or "++" in expression
            or "--" in expression
            or re.search(r"(?<![!<>=])=(?!=)", expression)
        ):
            raise ValueError("unreviewed side effect or operand in predicate")
        site = f"{prefix}-{index:02d}"
        fields = "".join(f" {name}=%u" for name in names)
        args = "".join(", (unsigned)" + name for name in names)
        injection = (
            "if (dkwb_as1_selected(dkwb_src, dkwb_dst)) {\n"
            '    fprintf(stderr, "DKWB-AS1-PRED invocation=%lu query=%lu '
            "src=%u dst=%u slot=%u site=" + site + " value=%u" + fields + '\\n",\n'
            "        dkwb_as1_invocation, dkwb_as1_query, dkwb_src, dkwb_dst, "
            "(unsigned)"
            + slot
            + ", (unsigned)(("
            + expression
            + ") != 0)"
            + args
            + ");\n}\n"
        )
        body = body[: branch.start()] + injection + body[branch.start() :]
        records.append({"site": site, "condition": expression, "operands": names})
    first = body.index("\n") + 1
    body = (
        body[:first]
        + (
            "const unsigned dkwb_src = MEM_U32(a0 + 64);\n"
            "const unsigned dkwb_dst = MEM_U32(a1 + 64);\n"
            + ("++dkwb_as1_query;\n" if main else "")
        )
        + body[first:]
    )
    if not main:
        for label, kind, values in [
            (
                "L429c14",
                "contributor",
                [
                    "MEM_U32(sp + 140)",
                    "s0 / 40",
                    "MEM_U32(s3)",
                    "MEM_U32(s3 + 4)",
                    "MEM_U32(s3 + 8)",
                    "MEM_U32(sp + 120)",
                    "MEM_U32(sp + 124)",
                    "MEM_U32(sp + 128)",
                ],
            ),
            (
                "L429cac",
                "aggregate",
                [
                    "0",
                    "0",
                    "MEM_U32(s3)",
                    "MEM_U32(s3 + 4)",
                    "MEM_U32(s3 + 8)",
                    "MEM_U32(sp + 96)",
                    "MEM_U32(sp + 100)",
                    "MEM_U32(sp + 104)",
                ],
            ),
        ]:
            mask_fields = [
                "block",
                "instruction",
                "candidate_def0",
                "candidate_def1",
                "candidate_def2",
                "path_def0",
                "path_def1",
                "path_def2",
            ]
            hook = (
                "if (dkwb_as1_selected(dkwb_src, dkwb_dst)) {\n"
                'fprintf(stderr, "DKWB-AS1-MASK invocation=%lu query=%lu '
                "src=%u dst=%u slot=%u kind="
                + kind
                + "".join(" " + field + "=%u" for field in mask_fields)
                + '\\n", dkwb_as1_invocation, dkwb_as1_query, dkwb_src, '
                "dkwb_dst, dkwb_as1_slot, "
                + ", ".join("(unsigned)(" + value + ")" for value in values)
                + ");\n}\n"
            )
            body = _replace(body, label + ":\n", label + ":\n" + hook)
        return body, list(reversed(records))
    body = _replace(
        body,
        "v0 = func_429928(mem, sp, a0, a1, a2, a3);",
        "dkwb_as1_slot = s2;\nv0 = func_429928(mem, sp, a0, a1, a2, a3);",
    )
    body = _replace(
        body,
        "L42a44c:\n",
        "L42a44c:\n"
        "if (dkwb_as1_selected(dkwb_src, dkwb_dst)) {\n"
        '    fprintf(stderr, "DKWB-AS1-RESULT invocation=%lu query=%lu '
        'src=%u dst=%u slot=%u\\n",\n'
        "        dkwb_as1_invocation, dkwb_as1_query, dkwb_src, dkwb_dst, "
        "(unsigned)v0);\n}\n",
    )
    return body, list(reversed(records))


def instrument_as1_motion(source: str) -> MotionInstrumentation:
    if MARKER in source:
        raise ValueError("AS1 source already instrumented")
    digest = hashlib.sha256(source.encode()).hexdigest()
    if digest != AS1_SHA256:
        raise ValueError("AS1 source SHA-256 is not the pinned revision: " + digest)
    result = _replace(source, '#include "header.h"\n', '#include "header.h"\n' + HEADER)
    start, end = _function(result, "func_42a028")
    body, predicates = _instrument_admission(result[start:end])
    result = result[:start] + body + result[end:]
    start, end = _function(result, "func_429928")
    body, helper_predicates = _instrument_admission(
        result[start:end], prefix="path", expected=30, slot="dkwb_as1_slot", main=False
    )
    predicates.extend(helper_predicates)
    result = result[:start] + body + result[end:]
    start, end = _function(result, "f_do_xbb_opt")
    body = result[start:end]
    first = body.index("\n") + 1
    body = (
        body[:first]
        + (
            "++dkwb_as1_invocation;\n"
            'if (dkwb_as1_on()) fprintf(stderr, "DKWB-AS1-PROFILE '
            "version=1 source_sha256="
            + AS1_SHA256
            + ' invocation=%lu\\n", dkwb_as1_invocation);\n'
        )
        + body[first:]
    )
    result = result[:start] + body + result[end:]
    start, end = _function(result, "func_42aa0c")
    body = result[start:end]
    for label, outcome, source_new in [
        ("L42ae90", "trial", "v0"),
        ("L42aedc", "rollback", "s7"),
        ("L42afe8", "accepted", "s7"),
    ]:
        hook = (
            "if (dkwb_as1_selected(MEM_U32(s3 + 64), MEM_U32(s4 + 64))) {\n"
            '    fprintf(stderr, "DKWB-AS1-COST invocation=%lu query=%lu outcome='
            + outcome
            + " "
            "src=%u dst=%u src_slot=%u dst_slot=%u src_old=%u dst_old=%u "
            'src_new=%u dst_new=%u context=%u\\n",\n'
            "        dkwb_as1_invocation, dkwb_as1_query, MEM_U32(s3 + "
            "64), MEM_U32(s4 + 64),\n"
            "        (unsigned)fp, (unsigned)s5, (unsigned)s6, (unsigned)s2, "
            "(unsigned)" + source_new + ", (unsigned)s0, MEM_U32(sp + 108));\n}\n"
        )
        body = _replace(body, label + ":\n", label + ":\n" + hook)
    result = result[:start] + body + result[end:]
    return MotionInstrumentation(result, digest, tuple(predicates))


def main(argv: list[str] | None = None) -> int:
    """Write an instrumented private source and its authenticated site manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args(argv)
    if len({p.resolve() for p in (args.source, args.output, args.manifest)}) != 3:
        parser.error("source, output and manifest must be distinct")
    try:
        result = instrument_as1_motion(args.source.read_text())
        args.output.write_text(result.source)
        args.manifest.write_text(
            json.dumps(
                {
                    "profile": MARKER,
                    "source_sha256": result.input_sha256,
                    "upstream_commit": UPSTREAM_COMMIT,
                    "predicates": result.predicates,
                },
                indent=2,
            )
            + "\n"
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
