"""Editing a source the way a composer must: the base named, the zones frozen.

Every stage of one campaign wrote its own source composer, and the difference
between the good ones and the bad ones was not cleverness. It was whether the
composer stated *which file it was written against* and refused to run when the
answer changed.

The strong ones (`don/mk.py`, `zed/mk.py`) opened with a whole-file SHA and a
list of named anchor lines, and died loudly when the base moved. The weak ones
(`redb/mk3.py`, `b4u/mk.py`) asserted the content of eight particular lines and
nothing else, so a rebase that shifted the file silently mis-edited it and
produced a plausible, wrong candidate that then had to be un-believed later.
One campaign lost a stage to exactly that.

So this module is the promotion of the strong shape, with the one weakness the
audit found in it removed. `don/mk.py` re-verified its anchors by searching the
*whole* emitted file for the anchor text, which a coincidental duplicate string
elsewhere would satisfy; here every anchor is re-read **at its own line**,
through the line map the edits themselves produced.

Three refusals, in the order they fire:

* **the base moved** -- the file's SHA-256 is not the one the plan was written
  against, so no line number in the plan means what it meant;
* **an anchor moved** -- the line is there but does not say what the plan
  expected, so the edit would land on someone else's statement;
* **the edit is in a frozen zone** -- another stage declared those lines
  protected, and a composer that quietly edits them is how two stages'
  constructions get silently merged.

What it does not do is judge whether the edit is *meaningful*. That is
:mod:`decomp_workbench.csource`'s and the reviewer's job. This module makes the
edit land where it was aimed, or not at all.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "COMPOSE_SCHEMA",
    "Anchor",
    "ComposeError",
    "Edit",
    "EditPlan",
    "apply_plan",
    "parse_zone",
    "source_sha256",
]

COMPOSE_SCHEMA = "decomp-workbench-compose-v1"


class ComposeError(ValueError):
    """A composed edit could not be proved to land where it was aimed.

    Every message names the file, the line, what was expected there and what
    is actually there, because the failure this class exists to prevent is a
    composer that edits the wrong line and reports success.
    """


def source_sha256(path: str | Path) -> str:
    """Return the SHA-256 of a source file's bytes.

    Whole-file, not per-line: the point of the check is to catch the rebase
    that moved everything, and a per-line assertion cannot see one.
    """

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_zone(text: str) -> tuple[int, int]:
    """Parse ``LO..HI`` (or a bare ``N``) into an inclusive line range."""

    raw = text.strip()
    if not raw:
        raise ComposeError("a frozen zone cannot be empty; write LO..HI or N")
    if ".." in raw:
        low_text, _, high_text = raw.partition("..")
    else:
        low_text = high_text = raw
    try:
        low, high = int(low_text), int(high_text)
    except ValueError:
        raise ComposeError(
            f"{text!r} is not a line range; write LO..HI (for example 900..940)"
        ) from None
    if low < 1 or high < low:
        raise ComposeError(
            f"{text!r} is not a line range: lines start at 1 and LO must not "
            "exceed HI"
        )
    return low, high


@dataclass(frozen=True)
class Anchor:
    """A line whose text the plan expects to still be there afterwards."""

    line: int
    text: str
    #: Who declared it. Printed in the refusal, so a reader knows whose
    #: construction they are about to disturb.
    owner: str = ""


@dataclass(frozen=True)
class Edit:
    """One line-level change, with the text it requires to already be there.

    `expect` is the whole point. A line number alone is a guess about a file;
    a line number plus the text that must be on it is a claim the composer can
    check before it writes anything.
    """

    line: int
    expect: str
    #: Replacement text for the line. ``None`` deletes the line entirely.
    replace: str | None = None
    #: Lines inserted immediately before this line, in order.
    insert: tuple[str, ...] = ()
    label: str = ""

    @property
    def deletes(self) -> bool:
        return self.replace is None and not self.insert

    def as_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "expect": self.expect,
            "replace": self.replace,
            "insert": list(self.insert),
            "label": self.label,
        }


@dataclass(frozen=True)
class EditPlan:
    """A base, the SHA it was written against, and the edits to make on it."""

    base: Path
    base_sha256: str
    edits: tuple[Edit, ...] = ()
    #: Inclusive line ranges no edit may touch, and who owns each.
    frozen: tuple[tuple[int, int], ...] = ()
    frozen_owner: str = ""
    #: Lines whose text must survive the edit unchanged, checked afterwards.
    anchors: tuple[Anchor, ...] = ()
    label: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "base": str(self.base),
            "base_sha256": self.base_sha256,
            "label": self.label,
            "edits": [item.as_dict() for item in self.edits],
            "frozen": [list(item) for item in self.frozen],
            "frozen_owner": self.frozen_owner,
            "anchors": [
                {"line": item.line, "text": item.text, "owner": item.owner}
                for item in self.anchors
            ],
        }


@dataclass(frozen=True)
class ComposedSource:
    """One emitted source, with the evidence that it landed where it was aimed."""

    text: str
    plan: EditPlan
    #: Base line number -> emitted line number, for every line that survived.
    line_map: dict[int, int] = field(default_factory=dict)
    verified_anchors: tuple[int, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": COMPOSE_SCHEMA,
            "base": str(self.plan.base),
            "base_sha256": self.plan.base_sha256,
            "label": self.plan.label,
            "edits": len(self.plan.edits),
            "frozen": [list(item) for item in self.plan.frozen],
            "verified_anchors": list(self.verified_anchors),
        }


def _normalize(text: str) -> str:
    """Compare source lines the way a reader does: by their words."""

    return " ".join(text.split())


def _in_frozen(line: int, frozen: tuple[tuple[int, int], ...]) -> tuple[int, int] | None:
    for low, high in frozen:
        if low <= line <= high:
            return low, high
    return None


def apply_plan(plan: EditPlan, *, text: str | None = None) -> ComposedSource:
    """Apply `plan` to its base and return the emitted source.

    Refuses -- loudly, with the line and both texts -- rather than emitting a
    source whose edits may have landed on the wrong statements.
    """

    if text is None:
        try:
            text = Path(plan.base).read_text(encoding="utf-8")
        except OSError as error:
            raise ComposeError(f"cannot read the base {plan.base}: {error}") from None
        actual_sha = source_sha256(plan.base)
    else:
        actual_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if plan.base_sha256 and actual_sha != plan.base_sha256:
        raise ComposeError(
            f"{plan.base} is not the base this plan was written against.\n"
            f"  expected sha256 {plan.base_sha256}\n"
            f"  found    sha256 {actual_sha}\n"
            "Every line number in the plan refers to the expected file. "
            "Re-derive the plan against the current base rather than "
            "re-pointing it."
        )

    lines = text.splitlines()
    total = len(lines)

    seen: dict[int, Edit] = {}
    for edit in plan.edits:
        if not 1 <= edit.line <= total:
            raise ComposeError(
                f"{plan.base} has {total} line(s); the edit "
                f"{edit.label or edit.expect!r} names line {edit.line}"
            )
        zone = _in_frozen(edit.line, plan.frozen)
        if zone is not None:
            owner = f" ({plan.frozen_owner})" if plan.frozen_owner else ""
            raise ComposeError(
                f"line {edit.line} is inside the frozen zone "
                f"{zone[0]}..{zone[1]}{owner} and this plan edits it. "
                "A frozen zone is another construction's protected lines; "
                "composing over it merges two stages' work silently."
            )
        if edit.line in seen:
            other = seen[edit.line]
            raise ComposeError(
                f"two edits target line {edit.line} "
                f"({other.label or other.expect!r} and "
                f"{edit.label or edit.expect!r}). One line, one edit: the "
                "second would be written against text the first replaced."
            )
        seen[edit.line] = edit
        found = lines[edit.line - 1]
        if _normalize(found) != _normalize(edit.expect):
            raise ComposeError(
                f"{plan.base}:{edit.line} does not say what the plan expects.\n"
                f"  expected: {_normalize(edit.expect)}\n"
                f"  found:    {_normalize(found)}\n"
                "The edit would land on a different statement."
            )

    for anchor in plan.anchors:
        if not 1 <= anchor.line <= total:
            raise ComposeError(
                f"{plan.base} has {total} line(s); the anchor names line "
                f"{anchor.line}"
            )
        found = lines[anchor.line - 1]
        if _normalize(found) != _normalize(anchor.text):
            owner = f" ({anchor.owner})" if anchor.owner else ""
            raise ComposeError(
                f"{plan.base}:{anchor.line} is not the anchor line{owner}.\n"
                f"  expected: {_normalize(anchor.text)}\n"
                f"  found:    {_normalize(found)}"
            )

    emitted: list[str] = []
    line_map: dict[int, int] = {}
    for number, line in enumerate(lines, start=1):
        edit = seen.get(number)
        if edit is None:
            emitted.append(line)
            line_map[number] = len(emitted)
            continue
        emitted.extend(edit.insert)
        if edit.replace is not None:
            emitted.append(edit.replace)
            line_map[number] = len(emitted)
        elif edit.insert:
            # An insert-only edit keeps the anchor line it was aimed before.
            emitted.append(line)
            line_map[number] = len(emitted)

    # The check `don/mk.py` got almost right: re-read every anchor *at its own
    # line* in the emitted file, not anywhere in it. A duplicate string
    # elsewhere satisfies a whole-file search and hides a corrupted anchor.
    verified: list[int] = []
    for anchor in plan.anchors:
        moved = line_map.get(anchor.line)
        if moved is None:
            raise ComposeError(
                f"the plan deleted line {anchor.line}, which is also one of "
                "its anchors"
            )
        if _normalize(emitted[moved - 1]) != _normalize(anchor.text):
            raise ComposeError(
                f"after composing, line {moved} (base line {anchor.line}) no "
                f"longer reads {_normalize(anchor.text)!r}. The emitted "
                "source is not trustworthy; nothing was written."
            )
        verified.append(anchor.line)

    for low, high in plan.frozen:
        for number in range(low, min(high, total) + 1):
            moved = line_map.get(number)
            if moved is None:
                raise ComposeError(
                    f"base line {number} is inside the frozen zone "
                    f"{low}..{high} and did not survive the edit"
                )
            if _normalize(emitted[moved - 1]) != _normalize(lines[number - 1]):
                raise ComposeError(
                    f"after composing, frozen line {number} changed. The "
                    "emitted source is not trustworthy; nothing was written."
                )

    trailing = "\n" if text.endswith("\n") or not text else ""
    return ComposedSource(
        text="\n".join(emitted) + trailing,
        plan=plan,
        line_map=line_map,
        verified_anchors=tuple(verified),
    )
