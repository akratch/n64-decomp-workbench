"""Opt-in instrumentation for statically recompiled IDO ugen sources."""

from __future__ import annotations

import re
from dataclasses import dataclass

MARKER = "DKWB_UGEN_INSTRUMENTATION_V1"
FUNCTION_RE = re.compile(
    r"^(?P<header>static\s+[^\n;{}]+?\s+(?P<name>f_[A-Za-z0-9_]+)"
    r"\s*\([^;\n]*\)\s*\{)\s*$",
    re.MULTILINE,
)
#: Known ugen free-list helpers, and the event each one emits.
#:
#: Not every entry is a *live* hook. A recorded campaign measured that
#: `f_add_to_free_list` runs only inside `f_init_regs` -- ten calls for a
#: 4644-instruction procedure -- so a trace hooked there sees the initial pool
#: being built and nothing about the allocations that follow. The two hooks
#: that fire per allocation are `f_get_free_fp_reg` (floating point) and
#: `f_free_reg`. `f_get_free_fp_reg` is listed here because it was the missing
#: half of that pair: a campaign asking "which register does the n-th fp temp
#: get" had to add it by hand.
FREE_LIST_FUNCTIONS = {
    "f_alloc_reg": "ALLOC",
    "f_get_free_reg": "ALLOC_GP",
    "f_get_free_fp_reg": "ALLOC_FP",
    "f_free_reg": "FREE",
    "f_force_free_reg": "FORCE_FREE",
    "f_add_to_free_list": "ADD",
    "f_remove_from_free_list": "REMOVE",
    "f_move_to_end_gp_list": "MOVE_END",
}

#: Free-list helpers whose *entry* hook records the wrong value for the question
#: "which machine register did the n-th temporary get".
#:
#: `f_get_free_fp_reg` takes a request descriptor in ``a0`` (a class/hint word,
#: not a register — a recorded trace showed values such as 96 and 208 that the
#: object never uses as fp registers) and *returns* the allocated register in
#: ``v0``. The entry `ALLOC_FP` hook therefore stamps the request, not the
#: result, and a study of the fp pop sequence reads it wrongly. These functions
#: get a second hook injected before every ``return`` so the allocated register
#: is visible as a distinct ``*_RESULT`` record carrying ``v0``. The entry hook
#: is kept: request-then-result on one ordinal shows a phantom pop (a request
#: that resolves to an already-live register) for what it is.
#:
#: ``f_get_free_reg`` is the integer analog and the register allocator that
#: actually fires per integer-temp allocation -- ``f_alloc_reg`` (``ALLOC``)
#: does not fire in the sampled procedures, and ``f_remove_from_free_list``
#: (``REMOVE``) is dominated by the `v0`/`v1` setup removals, so neither is the
#: integer temp-ring pop. ``f_get_free_reg`` returns the integer register
#: directly (0-31, no ``32 + n`` fp offset), so ``ALLOC_GP_RESULT`` is the
#: integer temp-ring dequeue sequence.
RESULT_HOOK_FUNCTIONS = {
    "f_get_free_reg": "ALLOC_GP_RESULT",
    "f_get_free_fp_reg": "ALLOC_FP_RESULT",
}

#: Emit helpers: the point where one ibuffer instruction record is written.
#:
#: ugen has **no instruction scheduler**. A full inventory of its 431 named
#: generated functions contains no ready list, no dependence DAG, no delay-slot
#: filler and no nop inserter; the list scheduler that owns those decisions is
#: `as1`'s (`f_reorganize_bb` / `f_schedule` / `f_fill_inst` / `f_emitnop`),
#: already readable without patching through `cc -Wa,-R` (see
#: `as1_reorganize`). What ugen decides is the *order instructions enter the
#: ibuffer* and the *source line each one carries into as1*, and `lineno` is
#: the one scheduler key with a source lever attached. That input order is what
#: these hooks record.
#:
#: Each of these helpers writes the 16-byte ibuffer record at index
#: ``MEM_U32(0x10018e70)`` and then increments that word, so the index read at
#: function entry is the emit ordinal of the record this call is about to
#: write. ``a0`` is the opcode/directive selector for every one of them.
EMIT_FUNCTION_RE = re.compile(r"^f_(?:d?emit_|d?define_label$|define_exception_label$)")

#: Emitters that write the *backward* (data/directive) buffer at 0x10018e78
#: rather than the forward instruction buffer.
BACKWARD_EMIT_PREFIX = "f_demit"

SCHED_HELPERS = r"""
/* DKWB_UGEN_SCHED_V1 -- emit-order provenance.
 * Disabled unless DKWB_UGEN_SCHED is set. Reads only; writes nothing but
 * stderr, so a traces-off build is byte-identical to stock.
 */
static int dkwb_sched_state = -1;
static int dkwb_sched_on(void) {
    if (dkwb_sched_state < 0) {
        const char *value = getenv("DKWB_UGEN_SCHED");
        dkwb_sched_state =
            value != NULL && *value != '\0' && *value != '0';
    }
    return dkwb_sched_state;
}
#define DKWB_IBUFFER_BACKWARD_CURSOR 0x10018e78u
static void dkwb_emit(const char *fn, unsigned op, uint8_t *mem, int backward,
                      int is_label) {
    long index;
    if (is_label) dkwb_sched_block++;
    if (!dkwb_sched_on() || mem == NULL) return;
    index = backward
        ? (long) MEM_U32(DKWB_IBUFFER_BACKWARD_CURSOR)
        : (long) MEM_U32(DKWB_IBUFFER_FORWARD_CURSOR);
    fprintf(stderr,
            "DKWB-EMIT-V1 proc=%d block=%d emit=%ld op=%u line=%ld "
            "buffer=%s fn=%s\n",
            dkwb_trace_proc, dkwb_sched_block, index, op,
            dkwb_source_line(mem), backward ? "back" : "fwd", fn);
}
"""

HELPERS = r"""
/* DKWB_UGEN_INSTRUMENTATION_V1
 * Generated by n64-decomp-workbench. Disabled unless DKWB_UGEN_TRACE is set.
 */
#include <stdio.h>
#include <stdlib.h>
static int dkwb_trace_state = -1;
static int dkwb_trace_depth;
static int dkwb_trace_proc = -1;
static int dkwb_sched_block;
static int dkwb_trace_on(void) {
    if (dkwb_trace_state < 0) {
        const char *value = getenv("DKWB_UGEN_TRACE");
        dkwb_trace_state =
            value != NULL && *value != '\0' && *value != '0';
    }
    return dkwb_trace_state;
}
static int dkwb_trace_enter(const char *name) {
    dkwb_trace_depth++;
    if (dkwb_trace_on()) {
        fprintf(stderr, "DKWB-CALL %d > %s\n", dkwb_trace_depth, name);
    }
    return 0;
}
static void dkwb_trace_exit(int *unused) {
    (void) unused;
    if (dkwb_trace_on()) {
        fprintf(stderr, "DKWB-CALL %d <\n", dkwb_trace_depth);
    }
    dkwb_trace_depth--;
}
static void dkwb_proc_begin(void) {
    dkwb_trace_proc++;
    dkwb_sched_block = 0;
    if (dkwb_trace_on()) {
        fprintf(stderr, "DKWB-PROC BEGIN proc=%d\n", dkwb_trace_proc);
    }
}
#define DKWB_IBUFFER_FORWARD_CURSOR 0x10018e70u
static long dkwb_emit_index(uint8_t *mem) {
    if (mem == NULL) return -1;
    return (long) MEM_U32(DKWB_IBUFFER_FORWARD_CURSOR) - 1;
}
/* ugen's current source line, the value f_warning prints as "line %d". It is
 * updated as codegen walks the statement list, so stamping it on a free-list
 * record ties a temp-ring pop to the source construct that consumed it -- a
 * phantom pop from a redundant mask shares the line of the masked assignment,
 * and a ring shift shows exactly which statement moved it. */
#define DKWB_CURRENT_SOURCE_LINE 0x10018e00u
static long dkwb_source_line(uint8_t *mem) {
    if (mem == NULL) return -1;
    return (long) MEM_U32(DKWB_CURRENT_SOURCE_LINE);
}
static void dkwb_freelist(const char *event, unsigned reg, uint8_t *mem) {
    if (dkwb_trace_on()) {
        fprintf(stderr, "DKWB-FREELIST %s proc=%d reg=%u emitted=%ld line=%ld\n",
                event, dkwb_trace_proc, reg & 0xffu, dkwb_emit_index(mem),
                dkwb_source_line(mem));
    }
}
#define DKWB_TRACE_FRAME(name) \
    __attribute__((cleanup(dkwb_trace_exit))) \
    int dkwb_trace_frame = dkwb_trace_enter(name)
"""


@dataclass(frozen=True)
class InstrumentationResult:
    source: str
    functions: int
    free_list_hooks: int
    result_hooks: int = 0
    procedure_hooks: int = 0
    emit_hooks: int = 0


def _function_body_span(source: str, name: str) -> tuple[int, int] | None:
    """Return the ``[start, end)`` character span of ``name``'s body braces.

    ``start`` indexes the ``{`` that opens the recompiled function body and
    ``end`` indexes the matching ``}``. Returns ``None`` when the function is
    not defined in this source, so a profile that names a function the pinned
    revision does not emit fails loudly rather than injecting nothing.
    """

    define = re.compile(
        r"^static\s+[^\n;{}]*?\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*\{",
        re.MULTILINE,
    )
    match = define.search(source)
    if match is None:
        return None
    open_brace = source.index("{", match.start())
    depth = 0
    for index in range(open_brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return open_brace, index
    return None


RETURN_VALUE_RE = re.compile(r"(?P<indent>[ \t]*)return\s+(?P<value>[A-Za-z_]\w*)\s*;")


def _inject_result_hook(source: str, name: str, event: str) -> tuple[str, int]:
    """Log the returned register before every ``return v;`` in ``name``.

    The recompiled allocator returns the register it chose; a hook at the
    function entry can only see the request. This injects one
    ``dkwb_freelist`` call per value-returning statement inside the function
    body, so the allocated register is recorded on whichever exit is taken.
    Bare ``return;`` statements are left alone: there is no value to log.
    """

    span = _function_body_span(source, name)
    if span is None:
        raise ValueError(
            f"result-hook function {name!r} is not defined in this source; "
            "the generated source does not match this instrumentation profile"
        )
    start, end = span
    body = source[start:end]
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        indent = match.group("indent")
        value = match.group("value")
        return (
            f'{indent}dkwb_freelist("{event}", {value}, mem);\n{indent}return {value};'
        )

    body = RETURN_VALUE_RE.sub(replace, body)
    return source[:start] + body + source[end:], count


def _helper_insertion_offset(source: str) -> int:
    """Insert after the leading include block when one exists."""

    matches = list(re.finditer(r"^\s*#include[^\n]*\n", source, re.MULTILINE))
    if not matches:
        return 0
    return matches[-1].end()


def instrument_ugen(
    source: str,
    *,
    function_pattern: str = r"^f_",
    procedure_function: str | None = "f_init_regs",
    emit_provenance: bool = False,
) -> InstrumentationResult:
    """Instrument selected recompiled functions and known free-list helpers.

    ``emit_provenance`` additionally hooks every ibuffer emit helper, so each
    instruction record ugen writes is reported in emission order with the
    source line it carries into the assembler's scheduler. See
    ``EMIT_FUNCTION_RE`` for why that is the ugen-side half of a schedule
    question and ``as1_reorganize`` for the other half.
    """

    if MARKER in source:
        raise ValueError("source is already instrumented")
    selected = re.compile(function_pattern)
    function_count = 0
    free_list_count = 0
    procedure_hook_count = 0
    emit_hook_count = 0

    def add_frame(match: re.Match[str]) -> str:
        nonlocal function_count, free_list_count, procedure_hook_count
        nonlocal emit_hook_count
        name = match.group("name")
        additions: list[str] = []
        if selected.search(name):
            additions.append(f'DKWB_TRACE_FRAME("{name}");')
            function_count += 1
        if procedure_function is not None and name == procedure_function:
            additions.append("dkwb_proc_begin();")
            procedure_hook_count += 1
        event = FREE_LIST_FUNCTIONS.get(name)
        if (
            event
            and re.search(r"\ba0\b", match.group("header"))
            and re.search(r"\bmem\b", match.group("header"))
        ):
            additions.append(f'dkwb_freelist("{event}", a0, mem);')
            free_list_count += 1
        if (
            emit_provenance
            and EMIT_FUNCTION_RE.search(name)
            and re.search(r"\ba0\b", match.group("header"))
            and re.search(r"\bmem\b", match.group("header"))
        ):
            backward = 1 if name.startswith(BACKWARD_EMIT_PREFIX) else 0
            is_label = 1 if "define_label" in name else 0
            additions.append(f'dkwb_emit("{name}", a0, mem, {backward}, {is_label});')
            emit_hook_count += 1
        if not additions:
            return match.group(0)
        return match.group("header") + "\n" + "\n".join(additions)

    instrumented = FUNCTION_RE.sub(add_frame, source)
    if function_count == 0:
        raise ValueError(
            "no recompiled functions matched; expected definitions such as "
            "'static ... f_alloc_reg(...) {'"
        )
    result_hook_count = 0
    for name, event in RESULT_HOOK_FUNCTIONS.items():
        if re.search(r"\b" + re.escape(name) + r"\b", instrumented) is None:
            continue
        instrumented, injected = _inject_result_hook(instrumented, name, event)
        result_hook_count += injected
    if emit_provenance and emit_hook_count == 0:
        raise ValueError(
            "no ibuffer emit helpers matched; expected definitions such as "
            "'static void f_emit_rrr(uint8_t *mem, ...)'"
        )
    helpers = HELPERS + (SCHED_HELPERS if emit_provenance else "")
    offset = _helper_insertion_offset(instrumented)
    instrumented = instrumented[:offset] + helpers + instrumented[offset:]
    return InstrumentationResult(
        source=instrumented,
        functions=function_count,
        free_list_hooks=free_list_count,
        result_hooks=result_hook_count,
        procedure_hooks=procedure_hook_count,
        emit_hooks=emit_hook_count,
    )
