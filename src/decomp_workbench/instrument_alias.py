"""Profiled alias-state tracing for statically recompiled IDO 5.3 uopt."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .instrument_uopt import IDO_53_V12_SHA256

MARKER = "DKWB_UOPT_ALIAS_TRACE_V1"

HEADER = r"""
/* DKWB_UOPT_ALIAS_TRACE_V1
 * Trace-only hooks for the pinned IDO 5.3 static-recomp uopt profile.
 * Disabled unless DKWB_UOPT_ALIAS_TRACE is present in the environment.
 */
#include <stdio.h>
#include <stdlib.h>
static int dkwb_alias_trace_state = -1;
static unsigned long dkwb_alias_base_ordinal;
static unsigned long dkwb_alias_query_ordinal;
static uint32_t dkwb_alias_current_register;
static int dkwb_alias_trace_on(void) {
    if (dkwb_alias_trace_state < 0) {
        const char *value = getenv("DKWB_UOPT_ALIAS_TRACE");
        dkwb_alias_trace_state =
            value != NULL && *value != '\0' && *value != '0';
    }
    return dkwb_alias_trace_state;
}
static const char *dkwb_alias_kind(uint32_t kind) {
    switch (kind) {
    case 1: return "islda";
    case 2: return "isop";
    case 3: return "isvar";
    case 4: return "issvar";
    case 5: return "isilda";
    case 6: return "dumped";
    default: return "unknown";
    }
}
"""


@dataclass(frozen=True)
class AliasInstrumentationResult:
    """Instrumented source plus the profile identity."""

    source: str
    input_sha256: str
    profile: str = "ido-5.3-static-recomp-v12"
    trace_points: int = 2


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(
            f"uopt alias profile anchor {label!r} occurred {count} times; "
            "the generated source does not match this profile"
        )
    return source.replace(old, new, 1)


def instrument_uopt_alias(
    source: str, *, allow_unverified_source: bool = False
) -> AliasInstrumentationResult:
    """Trace base provenance and base-noalias decisions."""

    if MARKER in source:
        raise ValueError("source is already instrumented")
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if not allow_unverified_source and digest != IDO_53_V12_SHA256:
        raise ValueError(
            "source SHA-256 is not the pinned IDO 5.3 static-recomp profile "
            f"({digest}); pass --allow-unverified-source only after reviewing "
            "the anchors and running a disabled-instrumentation fidelity test"
        )

    result = _replace_once(
        source,
        '#include "header.h"\n',
        '#include "header.h"\n' + HEADER,
        "instrumentation header",
    )
    result = _replace_once(
        result,
        "L420e28:\n"
        "// bdead 21 ra = MEM_U32(sp + 36);\n"
        "// bdead 21 sp = sp + 0x28;\n"
        "v0 = a0 < 0x1;",
        "L420e28:\n"
        "// bdead 21 ra = MEM_U32(sp + 36);\n"
        "// bdead 21 sp = sp + 0x28;\n"
        "if (dkwb_alias_trace_on()) {\n"
        "    uint32_t dkwb_left = MEM_U32(sp + 40);\n"
        "    uint32_t dkwb_right = MEM_U32(sp + 44);\n"
        "    fprintf(stderr, "
        '"DKWB-ALIAS-QUERY ordinal=%lu reg=%u result=%s '
        "left_kind=%u left_type=%s left_sym=%u left_addr=%u "
        'right_kind=%u right_type=%s right_sym=%u right_addr=%u\\n",\n'
        "        dkwb_alias_query_ordinal++, "
        "dkwb_alias_current_register,\n"
        '        a0 != 0 ? "may-alias" : "no-alias",\n'
        "        MEM_U8(dkwb_left + 0), "
        "dkwb_alias_kind(MEM_U8(dkwb_left + 0)),\n"
        "        MEM_U16(dkwb_left + 4), MEM_U32(dkwb_left + 40),\n"
        "        MEM_U8(dkwb_right + 0), "
        "dkwb_alias_kind(MEM_U8(dkwb_right + 0)),\n"
        "        MEM_U16(dkwb_right + 4), MEM_U32(dkwb_right + 40));\n"
        "}\n"
        "v0 = a0 < 0x1;",
        "base-noalias decision",
    )
    result = _replace_once(
        result,
        "t0 = a3 + t6;\n"
        "v0 = MEM_U32(t0 + 0);\n"
        "// fdead 400083eb MEM_U32(sp + 44) = s6;",
        "t0 = a3 + t6;\n"
        "v0 = MEM_U32(t0 + 0);\n"
        "if (dkwb_alias_trace_on()) {\n"
        "    uint32_t dkwb_kind = MEM_U8(a2 + 0);\n"
        "    dkwb_alias_current_register = a0;\n"
        "    fprintf(stderr, "
        '"DKWB-BASE ordinal=%lu reg=%u kind=%u type=%s sym=%u '
        'addr=%u hadbase=%u path=%s\\n",\n'
        "        dkwb_alias_base_ordinal++, a0, dkwb_kind,\n"
        "        dkwb_alias_kind(dkwb_kind), MEM_U16(a2 + 4),\n"
        "        MEM_U32(a2 + 40), v0 != 0,\n"
        "        (v0 != 0 && dkwb_kind != 1 && dkwb_kind != 5)\n"
        '            ? "retain" : '
        '(dkwb_kind == 1 || dkwb_kind == 5 ? "direct" : "fresh"));\n'
        "}\n"
        "// fdead 400083eb MEM_U32(sp + 44) = s6;",
        "base-in-register state",
    )
    return AliasInstrumentationResult(
        source=result,
        input_sha256=digest,
    )
