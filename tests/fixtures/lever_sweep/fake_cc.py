"""A stand-in compiler for the lever-sweep tests. Not a model of IDO.

    python fake_cc.py SOURCE -o OUTPUT

Writes objdump-style text for `demo`: one instruction per emitting statement,
every one naming the register `acc` was coloured. An empty `if (n) {}`, a
`|= 0` / `^= 0` keep-alive and a `x = (T) x;` no-op emit nothing. `acc` takes
s1 (colour 15) when the body holds `if (n) {}` or when CDX_FORCE forces its
web to c15, and s0 (colour 14) otherwise.

With CDX_LOG=1 and CDX_OUT set it also writes CDX records in the grammar
`trace web-report` reads. Webs are numbered from 10 in order of each name's
first mention in the body, so an inserted statement can renumber them -- which
is what the oracle's re-identification by expression has to survive.
FAKE_BREAK_GATE=1 makes the traced compile emit a different object.
"""

from __future__ import annotations

import os
import re
import sys

NAMES = {"acc": -28, "tmp": -32, "n": 0, "p": 4}
ZERO_EMISSION = (
    re.compile(r"^if\s*\(\s*\w+\s*\)\s*\{\s*\}$"),
    re.compile(r"^\w+\s*[|^]=\s*0$"),
    re.compile(r"^(\w+)\s*=\s*\([^)]*\)\s*\1$"),
)


def main(argv: list[str]) -> int:
    source, output = argv[1], argv[argv.index("-o") + 1]
    text = open(source, encoding="utf-8").read()
    if "#error" in text:
        sys.stderr.write("fake_cc: error directive\n")
        return 1
    start = text.index("int demo(")
    body_start = text.index("{", start)
    body_end = text.rindex("}")
    statements: list[tuple[int, str]] = []
    offset = body_start + 1
    for piece in re.split(r"(;|\{\s*\})", text[body_start + 1 : body_end]):
        if piece is None:
            continue
        if piece.startswith("{"):
            if statements:
                line, previous = statements[-1]
                statements[-1] = (line, previous + piece)
            offset += len(piece)
            continue
        if piece == ";":
            offset += 1
            continue
        stripped = " ".join(piece.split())
        line = text.count("\n", 0, offset + len(piece) - len(piece.lstrip())) + 1
        offset += len(piece)
        if stripped and not stripped.startswith("int "):
            statements.append((line, stripped))
    boundary = any(ZERO_EMISSION[0].match(s) and "(n)" in s for _, s in statements)
    order: list[str] = []
    for _, statement in statements:
        for name in re.findall(r"[A-Za-z_]\w*", statement):
            if name in NAMES and name not in order:
                order.append(name)
    webs = {name: 10 + index for index, name in enumerate(order)}
    forces = dict(re.findall(r"p1:w(\d+)=c(\d+)", os.environ.get("CDX_FORCE", "")))
    forced_acc = forces.get(str(webs.get("acc", -1))) == "15"
    colour = 15 if boundary or forced_acc else 14
    if os.environ.get("CDX_LOG") == "1" and os.environ.get("FAKE_BREAK_GATE") == "1":
        colour = 16
    emitting = [
        (line, s)
        for line, s in statements
        if not any(p.match(s) for p in ZERO_EMISSION)
    ]
    rd = colour + 2
    word = (4 << 21) | (5 << 16) | (rd << 11) | 0x21
    register = {16: "s0", 17: "s1", 18: "s2"}[rd]
    rows = [
        f"{4 * index:4x}:\t{word:08x} \taddu\t${register},$a0,$a1"
        for index in range(len(emitting))
    ]
    with open(output, "w", encoding="utf-8") as handle:
        handle.write("00000000 <demo>:\n" + "\n".join(rows) + "\n")
    trace = os.environ.get("CDX_OUT")
    if os.environ.get("CDX_LOG") == "1" and trace:
        proc = os.environ.get("CDX_PROC", "0")
        records = [f"[CDX] globalcolor proc={proc}"]
        for number, (line, _) in enumerate(statements, 1):
            records.append(
                f"[CDX] bbline proc={proc} bb={number} weight=1 entry={line} "
                f"lines={line} mask1=0x0 mask2=0x0"
            )
        for name in order:
            web = webs[name]
            blocks = [
                str(number)
                for number, (_, statement) in enumerate(statements, 1)
                if re.search(rf"\b{name}\b", statement)
            ]
            want = forces.get(str(web))
            chosen = colour if name == "acc" else 16 + order.index(name)
            forced = "-2"
            if want is not None:
                chosen, forced = int(want), "-1"
            storage = 2 if NAMES[name] >= 0 else 1
            records += [
                f"[CDX] p1dec phase=p1 proc={proc} web={web} save=1.0 nocs=1 "
                f"totalsave=1 bestcost=0 forbidden0=0x0 regsleft=9 numintf=1 "
                f"decision=color forced={forced}",
                f"[CDX] webexpr proc={proc} phase=p1 web={web} lr=L{web} kind=3 "
                f"expr=var:{NAMES[name]}:{storage}:4",
                f"[CDX] webblocks phase=p1 proc={proc} role=target web={web} "
                f"lr=L{web} bbs={','.join(blocks)} aux=-",
                f"[CDX] p1color phase=p1 proc={proc} web={web} color={chosen} "
                f"reg=s{chosen - 14} forced={forced}",
            ]
        with open(trace, "w", encoding="utf-8") as handle:
            handle.write("\n".join(records) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
