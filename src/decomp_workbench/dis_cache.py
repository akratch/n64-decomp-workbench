"""A disassembly cache that cannot answer "perfect" because it was truncated.

Scoring a few thousand objects means disassembling a few thousand objects, so
every campaign eventually writes a disassembly cache. The one every campaign
writes looks like this::

    if not os.path.exists(dis):
        open(dis, 'w').write(objdump(obj))
    rows = load(dis)

and it has a failure mode that is worse than being wrong: it is wrong
*silently, in the safe-looking direction*. Kill a scoring run mid-write and the
next run finds a **zero-byte** cache file, which exists, so it is not rebuilt.
``load`` returns no rows. Every downstream loop is of the shape "for each row
present in both sides", so no rows means no mismatches, and the object reports
a perfect score. One campaign shipped that number into a stage summary; four
later stages reported the same defect independently, and one of them
strengthened the guard to also reject an empty file -- which still accepts a
cache that was truncated at 60% and still scores it as better than it is.

The rule this module enforces is that a cache entry is trusted only when it can
prove it is a complete disassembly of *this* object:

* the entry carries a header naming the object's SHA-256, the section, the
  symbol filter, and its own row count;
* the SHA-256 must match the object on disk, so a rebuilt object invalidates
  its entry rather than being scored against a stale one;
* the row count in the header must equal the rows the body actually parses to,
  so a truncated write is caught even when it is not empty;
* for a whole-section disassembly, that count must also equal the number of
  32-bit words the object's own ELF section holds -- the row-count assertion
  the campaign asked for, parameterized by the object rather than hard-coded
  to one campaign's 4641.

Anything that fails is discarded and rebuilt, and the rejection is *reported*
rather than swallowed. If a freshly built disassembly fails the same check,
that is not a cache problem and this module raises instead of scoring.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .campaign import file_sha256
from .elf_instructions import ElfFormatError, read_section
from .model import Instruction, display_path
from .objdump import dump_object, parse_disassembly

__all__ = [
    "CACHE_HEADER_PREFIX",
    "CacheEvent",
    "DisassemblyCache",
    "DisassemblyCacheError",
]

#: First line of every entry. Version it, because a future field addition must
#: invalidate old entries rather than be silently ignored by an old reader.
CACHE_HEADER_PREFIX = "#decomp-workbench-disassembly-cache-v1"

_HEADER_RE = re.compile(
    re.escape(CACHE_HEADER_PREFIX) + r"\s+(?P<fields>.*)$",
)


class DisassemblyCacheError(ValueError):
    """A disassembly could not be trusted, and no fallback would be honest."""


@dataclass(frozen=True)
class CacheEvent:
    """What happened to one cache entry, and why."""

    object_path: str
    status: str
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "object": self.object_path,
            "status": self.status,
            "reason": self.reason,
        }

    def __str__(self) -> str:
        if self.reason is None:
            return f"{self.status}: {self.object_path}"
        return f"{self.status}: {self.object_path} ({self.reason})"


def _section_words(path: Path, section: str) -> int | None:
    """Return how many 32-bit words the object's own section holds.

    ``None`` when that cannot be read -- a section this ELF reader does not
    support, or a file that is not an ELF object at all. A cache entry is
    still checked against its own declared row count in that case; this is the
    stronger cross-check, not the only one.
    """

    try:
        raw = read_section(path, section)
    except (OSError, ElfFormatError):
        return None
    if raw is None:
        return None
    return len(raw) // 4


@dataclass
class DisassemblyCache:
    """A validated, content-addressed store of objdump text.

    There is no default directory on purpose. A scorer that defaults to some
    directory scores whatever happens to be in it: one campaign's batch scorer
    defaulted to a *later* stage's object directory and every stage that copied
    it kept scoring the wrong objects while printing a plausible number.
    """

    directory: Path
    objdump: str | None = None
    events: list[CacheEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.directory = Path(self.directory)

    @property
    def rejections(self) -> list[CacheEvent]:
        """Entries that existed and were not trusted."""

        return [event for event in self.events if event.status == "rejected"]

    def entry_path(
        self, object_path: str | Path, *, symbol: str | None, section: str
    ) -> Path:
        """Return the entry file for one (object, symbol, section) request.

        Keyed by the object's absolute path *and* the dump's shape, so a
        whole-section dump and a ``--symbol``-narrowed dump of the same object
        never overwrite one another.
        """

        key = "\0".join(
            (
                str(Path(object_path).resolve()),
                symbol or "",
                section,
            )
        ).encode("utf-8")
        return self.directory / f"{hashlib.sha256(key).hexdigest()}.objdump"

    def load(
        self,
        object_path: str | Path,
        *,
        symbol: str | None = None,
        section: str = ".text",
    ) -> tuple[str, list[Instruction]]:
        """Return one object's disassembly text and parsed instructions."""

        path = Path(object_path)
        display = display_path(path)
        digest = file_sha256(path)
        expected_words = _section_words(path, section) if symbol is None else None
        entry = self.entry_path(path, symbol=symbol, section=section)

        cached = self._read_entry(
            entry,
            display=display,
            digest=digest,
            expected_words=expected_words,
        )
        if cached is not None:
            self.events.append(CacheEvent(object_path=display, status="hit"))
            return cached

        text, instructions = dump_object(
            path, objdump=self.objdump, symbol=symbol, section=section
        )
        reason = _row_count_problem(
            len(instructions), expected_words=expected_words, symbol=symbol
        )
        if reason is not None:
            raise DisassemblyCacheError(
                f"the disassembly of {display} does not describe the whole "
                f"object: {reason}. This is not a cache problem -- the object "
                "and its disassembly disagree. Check that --section names the "
                "section the code is in, and that objdump is a MIPS-capable "
                "build."
            )
        self._write_entry(
            entry,
            text=text,
            digest=digest,
            rows=len(instructions),
            symbol=symbol,
            section=section,
        )
        return text, instructions

    def _read_entry(
        self,
        entry: Path,
        *,
        display: str,
        digest: str,
        expected_words: int | None,
    ) -> tuple[str, list[Instruction]] | None:
        """Return a trusted entry's contents, or ``None`` after rejecting it."""

        try:
            raw = entry.read_text(encoding="utf-8")
        except FileNotFoundError:
            self.events.append(CacheEvent(object_path=display, status="miss"))
            return None
        except OSError as error:
            self._reject(display, f"unreadable ({error})")
            return None

        if not raw.strip():
            # The zero-byte entry an interrupted run leaves behind. Existence
            # is not evidence: this is the exact file that scored as a perfect
            # match five times in one campaign.
            self._reject(display, "empty cache entry (an interrupted write)")
            return None
        header, _, body = raw.partition("\n")
        match = _HEADER_RE.match(header.strip())
        if match is None:
            self._reject(display, "missing or unrecognized cache header")
            return None
        fields = dict(
            item.split("=", 1) for item in match.group("fields").split() if "=" in item
        )
        if fields.get("sha256") != digest:
            self._reject(display, "the object changed since the entry was written")
            return None
        try:
            declared_rows = int(fields.get("rows", ""))
        except ValueError:
            self._reject(display, "cache header does not declare a row count")
            return None
        instructions = parse_disassembly(body)
        if len(instructions) != declared_rows:
            self._reject(
                display,
                f"truncated: header declares {declared_rows} row(s), the body "
                f"parses to {len(instructions)}",
            )
            return None
        if expected_words is not None and declared_rows != expected_words:
            self._reject(
                display,
                f"short: {declared_rows} row(s) cached for a section holding "
                f"{expected_words} instruction word(s)",
            )
            return None
        return body, instructions

    def _reject(self, display: str, reason: str) -> None:
        self.events.append(
            CacheEvent(object_path=display, status="rejected", reason=reason)
        )

    def _write_entry(
        self,
        entry: Path,
        *,
        text: str,
        digest: str,
        rows: int,
        symbol: str | None,
        section: str,
    ) -> None:
        """Write one entry, atomically, so an interrupted run leaves no stub."""

        self.directory.mkdir(parents=True, exist_ok=True)
        header = (
            f"{CACHE_HEADER_PREFIX} sha256={digest} rows={rows} "
            f"section={section} symbol={symbol or '-'}"
        )
        temporary = entry.with_suffix(entry.suffix + ".partial")
        temporary.write_text(f"{header}\n{text}", encoding="utf-8")
        temporary.replace(entry)


def _row_count_problem(
    rows: int, *, expected_words: int | None, symbol: str | None
) -> str | None:
    """Return why a freshly built disassembly is not usable, or ``None``."""

    if rows == 0:
        return "it parsed to no instructions at all"
    if expected_words is not None and rows != expected_words:
        return (
            f"it parsed to {rows} row(s) for a section holding "
            f"{expected_words} instruction word(s)"
        )
    if symbol is not None and rows == 0:  # pragma: no cover - covered above
        return "it parsed to no instructions at all"
    return None
