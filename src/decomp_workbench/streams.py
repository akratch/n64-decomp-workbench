"""Record-level surgery, windows, and diffs for IDO's two phase streams.

The two streams a late campaign actually holds in its hands are the binary
Ucode uopt hands ugen and the fixed 16-byte Binasm ugen hands as1.  They are
decoded by :mod:`decomp_workbench.ucode` and :mod:`decomp_workbench.binasm`;
this module is the small amount of shared machinery that makes them *editable*
evidence rather than only readable evidence:

* one unified record view, so a window or a diff reads the same for both;
* fresh-label allocation, so an inserted control-flow record cannot collide
  with a label the stream already owns;
* record-framed insertion, replacement, and deletion that refuses to write a
  stream the decoder cannot read back.

Every edit here is a *sufficiency* experiment. Proving that an inserted record
produces the target object establishes what the downstream pass does with that
record. It never establishes that a C spelling survives the earlier passes and
emits it -- that claim needs the source-level work the record only points at.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .binasm import BINASM_RECORD_SIZE, parse_binasm, read_stream_bytes
from .ucode import parse_ucode

STREAM_WINDOW_SCHEMA = "decomp-workbench-stream-window-v1"
STREAM_DIFF_SCHEMA = "decomp-workbench-stream-diff-v1"
STREAM_PATCH_SCHEMA = "decomp-workbench-stream-patch-v1"

FORMATS: tuple[str, ...] = ("ucode", "binasm")

#: Which operand words of a Ucode record name a label. Only the records whose
#: label operands the decoder already establishes are listed: a wrong entry
#: here would inflate the maximum label and silently waste numbers, and a
#: missing one would let a "fresh" label collide with a real one.
UCODE_LABEL_OPERANDS: dict[str, tuple[int, ...]] = {
    "lab": (1,),
    "ldef": (1,),
    "ujp": (1,),
    "fjp": (1,),
    "tjp": (1,),
    "clab": (1,),
    "xjp": (1, 2),
}

_FRESH_RE = re.compile(r"\{fresh(?:\+(\d+))?\}")
_COMMENT_RE = re.compile(r"#.*$", re.MULTILINE)


def _names_a_file(value: str) -> bool:
    """Say whether a spec argument is a readable path rather than inline text.

    An inline spec is arbitrary text, so the filesystem question itself can
    fail (a name longer than the host allows, an embedded NUL). Treat every
    such failure as "this is not a path".
    """

    try:
        return Path(value).expanduser().is_file()
    except (OSError, ValueError):
        return False


@dataclass(frozen=True)
class StreamRecord:
    """One decoded record of either phase stream, in one shape."""

    index: int
    byte_offset: int
    byte_length: int
    name: str
    detail: str
    words: tuple[int, ...]

    @property
    def raw_hex(self) -> str:
        return " ".join(f"{word:08x}" for word in self.words)

    @property
    def end_offset(self) -> int:
        return self.byte_offset + self.byte_length

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "byte_offset": self.byte_offset,
            "offset_hex": f"0x{self.byte_offset:x}",
            "byte_length": self.byte_length,
            "name": self.name,
            "detail": self.detail,
            "words": [f"0x{word:08x}" for word in self.words],
            "raw_hex": self.raw_hex,
        }


def detect_format(data: bytes) -> str:
    """Name the stream format from record framing alone.

    Binasm is a fixed 16-byte record; Ucode is variable-width and framed by an
    opcode byte. A stream that frames cleanly as Binasm *and* names most of its
    records is Binasm -- that is the wrong-file mistake this catches, since
    ugen's confusingly named ``-temp`` output is Binasm-shaped.
    """

    if not data:
        raise ValueError("stream is empty; nothing to decode")
    if len(data) % 4:
        raise ValueError(
            f"stream is {len(data)} bytes; both IDO phase streams are whole "
            "32-bit words"
        )
    binasm_framed = len(data) % BINASM_RECORD_SIZE == 0
    if binasm_framed:
        records = parse_binasm(data)
        recognized = sum(record.kind != "unknown" for record in records)
        if recognized * 4 >= len(records) * 3:
            return "binasm"
    try:
        parse_ucode(data)
    except ValueError:
        if binasm_framed:
            return "binasm"
        raise
    return "ucode"


def decode_stream(
    source: bytes | str | Path, *, stream_format: str | None = None
) -> tuple[str, bytes, tuple[StreamRecord, ...]]:
    """Read one stream and decode it into the unified record view."""

    data = read_stream_bytes(source)
    resolved = stream_format or detect_format(data)
    if resolved not in FORMATS:
        raise ValueError(f"unsupported stream format: {resolved!r}")
    if resolved == "binasm":
        records = tuple(
            StreamRecord(
                index=record.index,
                byte_offset=record.offset,
                byte_length=BINASM_RECORD_SIZE,
                name=record.name,
                detail=record.detail,
                words=tuple(record.words),
            )
            for record in parse_binasm(data)
        )
    else:
        records = tuple(
            StreamRecord(
                index=record.index,
                byte_offset=record.byte_offset,
                byte_length=len(record.words) * 4,
                name=f"U{record.name}",
                detail=record.detail,
                words=record.words,
            )
            for record in parse_ucode(data)
        )
    return resolved, data, records


def max_label(records: tuple[StreamRecord, ...], *, stream_format: str) -> int:
    """Return the highest label number any record in the stream names."""

    if stream_format != "ucode":
        raise ValueError("label allocation is defined for Ucode streams only")
    highest = 0
    for record in records:
        positions = UCODE_LABEL_OPERANDS.get(record.name.removeprefix("U"))
        if not positions:
            continue
        for position in positions:
            if position < len(record.words):
                highest = max(highest, record.words[position])
    return highest


def allocate_fresh_labels(
    records: tuple[StreamRecord, ...], count: int, *, stream_format: str = "ucode"
) -> tuple[int, ...]:
    """Allocate `count` label numbers above every label the stream uses."""

    if count < 0:
        raise ValueError("fresh label count must not be negative")
    base = max_label(records, stream_format=stream_format)
    return tuple(base + 1 + offset for offset in range(count))


def parse_record_spec(
    spec: str | bytes | Path,
    *,
    fresh_labels: tuple[int, ...] = (),
) -> tuple[bytes, tuple[int, ...] | None, int]:
    """Assemble insertion bytes from a hex spec, and say how it was framed.

    The spec is whitespace- or comma-separated 32-bit words, ``#`` comments to
    end of line, and ``|`` or a blank line between records. ``{fresh}`` and
    ``{fresh+N}`` are replaced by allocated label numbers, which is what makes
    an inserted branch/label pair safe to write into a stream whose labels the
    author has not read.

    Returns the bytes, the caller-declared record byte lengths (or ``None``
    when the spec did not group them), and the number of ``{fresh}`` slots.
    """

    if isinstance(spec, (bytes, bytearray, memoryview)):
        return bytes(spec), None, 0
    text: str
    if isinstance(spec, Path) or _names_a_file(spec):
        raw = Path(spec).expanduser().read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            # A raw record dump is a legitimate spec file; it just is not text.
            return raw, None, 0
    else:
        text = str(spec)

    highest_slot = -1

    def substitute(match: re.Match[str]) -> str:
        nonlocal highest_slot
        slot = int(match.group(1) or 0)
        highest_slot = max(highest_slot, slot)
        if slot >= len(fresh_labels):
            raise ValueError(
                f"record spec uses {{fresh+{slot}}} but only "
                f"{len(fresh_labels)} fresh label(s) were allocated; "
                "pass --fresh-label (repeat it for more)"
            )
        return str(fresh_labels[slot])

    text = _COMMENT_RE.sub("", text)
    text = _FRESH_RE.sub(substitute, text)
    groups = [group for group in re.split(r"\||\n\s*\n", text) if group.strip()]
    blob = bytearray()
    lengths: list[int] = []
    for group in groups:
        start = len(blob)
        for token in re.split(r"[\s,]+", group.strip()):
            if not token:
                continue
            try:
                value = int(token, 0)
            except ValueError as error:
                raise ValueError(
                    f"record spec token is not an integer: {token!r}"
                ) from error
            if not 0 <= value <= 0xFFFFFFFF:
                raise ValueError(f"record spec word out of range: {token!r}")
            blob.extend(value.to_bytes(4, "big"))
        lengths.append(len(blob) - start)
    if not blob:
        raise ValueError("record spec assembled to zero words")
    framing = tuple(lengths) if len(lengths) > 1 else None
    return bytes(blob), framing, highest_slot + 1


def count_fresh_slots(spec: str | bytes | Path) -> int:
    """Return how many distinct ``{fresh...}`` slots a spec names."""

    if isinstance(spec, (bytes, bytearray, memoryview)):
        return 0
    if isinstance(spec, Path) or _names_a_file(spec):
        try:
            text = Path(spec).expanduser().read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return 0
    else:
        text = str(spec)
    slots = [int(match or 0) for match in _FRESH_RE.findall(_COMMENT_RE.sub("", text))]
    return max(slots) + 1 if slots else 0


def resolve_position(
    records: tuple[StreamRecord, ...], position: str | int, *, data_length: int
) -> tuple[int, int]:
    """Resolve ``#index`` or a byte offset to a (record index, byte offset).

    A byte offset that is not a record boundary is refused rather than rounded:
    an insertion in the middle of a record produces a stream the next pass
    reads as garbage, and the resulting evidence would be about the damage.
    """

    if isinstance(position, str) and position.startswith("#"):
        try:
            index = int(position[1:], 0)
        except ValueError as error:
            raise ValueError(f"malformed record index: {position!r}") from error
        if index < 0:
            index += len(records)
        if not 0 <= index <= len(records):
            raise ValueError(f"record index {index} is outside 0..{len(records)}")
        offset = records[index].byte_offset if index < len(records) else data_length
        return index, offset
    try:
        offset = int(position, 0) if isinstance(position, str) else int(position)
    except ValueError as error:
        raise ValueError(
            f"expected a byte offset or #record-index, got {position!r}"
        ) from error
    if offset < 0 or offset > data_length:
        raise ValueError(
            f"offset 0x{offset:x} is outside stream range 0x0..0x{data_length:x}"
        )
    if offset == data_length:
        return len(records), offset
    for record in records:
        if record.byte_offset == offset:
            return record.index, offset
    raise ValueError(
        f"offset 0x{offset:x} is not a record boundary; the nearest boundaries "
        f"are {_nearest_boundaries(records, offset)}"
    )


def _nearest_boundaries(records: tuple[StreamRecord, ...], offset: int) -> str:
    before = [record for record in records if record.byte_offset < offset]
    after = [record for record in records if record.byte_offset > offset]
    parts = []
    if before:
        parts.append(f"0x{before[-1].byte_offset:x} (#{before[-1].index})")
    if after:
        parts.append(f"0x{after[0].byte_offset:x} (#{after[0].index})")
    return " and ".join(parts) or "none"


def stream_window(
    source: bytes | str | Path,
    *,
    at: str | int,
    radius: int = 6,
    stream_format: str | None = None,
) -> dict[str, Any]:
    """Decode the records around one position in either phase stream."""

    if radius < 0:
        raise ValueError("window radius must be non-negative")
    resolved, data, records = decode_stream(source, stream_format=stream_format)
    index, offset = resolve_position(records, at, data_length=len(data))
    first = max(0, index - radius)
    last = min(len(records), index + radius + 1)
    rows = []
    for record in records[first:last]:
        item = record.as_dict()
        item["at_position"] = record.index == index
        rows.append(item)
    return {
        "schema": STREAM_WINDOW_SCHEMA,
        "format": resolved,
        "stream": _stream_identity(source, data, records),
        "position": {
            "record_index": index,
            "byte_offset": offset,
            "offset_hex": f"0x{offset:x}",
        },
        "radius": radius,
        "records": rows,
        "proof": (
            "This reads a retained file and decodes record framing only. It "
            "runs no compiler and mutates nothing."
        ),
    }


def _stream_identity(
    source: bytes | str | Path, data: bytes, records: tuple[StreamRecord, ...]
) -> dict[str, Any]:
    identity: dict[str, Any] = {
        "bytes": len(data),
        "record_count": len(records),
        "sha256": hashlib.sha256(data).hexdigest(),
        "byteorder": "big",
    }
    if not isinstance(source, (bytes, bytearray, memoryview)):
        identity["path"] = str(Path(source))
    return identity


def patch_stream(
    source: bytes | str | Path,
    *,
    stream_format: str | None = None,
    insert_at: str | int | None = None,
    replace: str | None = None,
    delete: str | None = None,
    records_spec: str | bytes | Path | None = None,
    fresh_label_count: int = 0,
    allow_undecodable: bool = False,
) -> tuple[bytes, dict[str, Any]]:
    """Insert, replace, or delete whole records and verify the result decodes.

    Returns the patched bytes and a JSON-safe report; the caller decides where
    the bytes land, so nothing here can overwrite a retained capture.
    """

    operations = [
        name
        for name, value in (
            ("insert", insert_at),
            ("replace", replace),
            ("delete", delete),
        )
        if value is not None
    ]
    if len(operations) != 1:
        raise ValueError(
            "give exactly one of --insert-at, --replace, or --delete "
            f"(got {', '.join(operations) or 'none'})"
        )
    resolved, data, records = decode_stream(source, stream_format=stream_format)
    fresh: tuple[int, ...] = ()
    if fresh_label_count:
        fresh = allocate_fresh_labels(
            records, fresh_label_count, stream_format=resolved
        )

    payload = b""
    framing: tuple[int, ...] | None = None
    if records_spec is not None:
        payload, framing, _slots = parse_record_spec(records_spec, fresh_labels=fresh)

    if insert_at is not None:
        if not payload:
            raise ValueError("--insert-at requires --records")
        index, offset = resolve_position(records, insert_at, data_length=len(data))
        end_index, end_offset = index, offset
        patched = data[:offset] + payload + data[offset:]
        operation = "insert"
    else:
        span = replace if replace is not None else str(delete)
        index, end_index = _parse_span(span, len(records))
        if delete is not None and payload:
            raise ValueError("--delete does not take --records")
        if replace is not None and not payload:
            raise ValueError("--replace requires --records")
        offset = records[index].byte_offset
        end_offset = (
            records[end_index].byte_offset if end_index < len(records) else len(data)
        )
        patched = data[:offset] + payload + data[end_offset:]
        operation = "replace" if replace is not None else "delete"

    decoded_error: str | None = None
    patched_records: tuple[StreamRecord, ...] = ()
    try:
        _, _, patched_records = decode_stream(patched, stream_format=resolved)
    except ValueError as error:
        decoded_error = str(error)
        if not allow_undecodable:
            raise ValueError(
                f"patched stream does not decode as {resolved}: {error}; "
                "fix the record spec or pass --allow-undecodable to keep it"
            ) from error

    inserted_records: list[dict[str, Any]] = []
    if payload:
        try:
            _, _, inserted_records_view = decode_stream(payload, stream_format=resolved)
            inserted_records = [item.as_dict() for item in inserted_records_view]
            if framing is not None:
                declared = tuple(framing)
                actual = tuple(item.byte_length for item in inserted_records_view)
                if declared != actual:
                    raise ValueError(
                        "record spec groups do not match decoded record framing: "
                        f"spec says {declared}, the decoder frames {actual}"
                    )
        except ValueError as error:
            if not allow_undecodable:
                raise ValueError(
                    f"inserted records do not decode as {resolved}: {error}"
                ) from error

    report = {
        "schema": STREAM_PATCH_SCHEMA,
        "format": resolved,
        "operation": operation,
        "source": _stream_identity(source, data, records),
        "position": {
            "record_index": index,
            "end_record_index": end_index,
            "byte_offset": offset,
            "offset_hex": f"0x{offset:x}",
            "end_byte_offset": end_offset,
            "removed_bytes": end_offset - offset,
            "removed_records": end_index - index,
        },
        "fresh_labels": list(fresh),
        "max_existing_label": (
            max_label(records, stream_format=resolved) if resolved == "ucode" else None
        ),
        "inserted": {
            "bytes": len(payload),
            "hex": payload.hex(),
            "records": inserted_records,
        },
        "result": {
            "bytes": len(patched),
            "sha256": hashlib.sha256(patched).hexdigest(),
            "record_count": len(patched_records) if patched_records else None,
            "record_delta": (
                len(patched_records) - len(records) if patched_records else None
            ),
            "decodes": decoded_error is None,
            "decode_error": decoded_error,
        },
        "proof": (
            "A patched stream that produces the target object proves the "
            "inserted record is sufficient downstream of the patched boundary. "
            "It does not prove any C spelling emits that record."
        ),
    }
    return patched, report


def _parse_span(span: str, record_count: int) -> tuple[int, int]:
    """Parse ``N`` or ``N:M`` (half-open) into record indices."""

    text = span.removeprefix("#")
    start_text, separator, end_text = text.partition(":")
    try:
        start = int(start_text, 0)
        end = (
            int(end_text.removeprefix("#"), 0) if separator and end_text else start + 1
        )
    except ValueError as error:
        raise ValueError(f"malformed record span: {span!r}") from error
    if start < 0:
        start += record_count
    if end < 0:
        end += record_count
    if not 0 <= start < record_count:
        raise ValueError(f"record index {start} is outside 0..{record_count - 1}")
    if not start < end <= record_count:
        raise ValueError(
            f"record span {span!r} must select at least one record inside "
            f"0..{record_count}"
        )
    return start, end


def diff_streams(
    left: bytes | str | Path,
    right: bytes | str | Path,
    *,
    stream_format: str | None = None,
    limit: int = 40,
    context: int = 2,
) -> dict[str, Any]:
    """Align two phase streams by record and report the first divergence."""

    if limit <= 0:
        raise ValueError("diff limit must be positive")
    if context < 0:
        raise ValueError("diff context must be non-negative")
    left_format, left_data, left_records = decode_stream(
        left, stream_format=stream_format
    )
    # Each side is detected on its own evidence. Forcing the left format onto
    # the right would report a mixed pair as a damaged stream rather than as
    # the mistake it is: two different pass boundaries handed to one diff.
    right_format, right_data, right_records = decode_stream(
        right, stream_format=stream_format
    )
    if left_format != right_format:
        raise ValueError(
            f"streams have different formats ({left_format} and {right_format}); "
            "pass --format to decode both the same way"
        )
    left_keys = [record.words for record in left_records]
    right_keys = [record.words for record in right_records]
    matcher = SequenceMatcher(a=left_keys, b=right_keys, autojunk=False)
    counts = {"equal": 0, "replace": 0, "insert": 0, "delete": 0}
    rows: list[dict[str, Any]] = []
    pending_context: list[dict[str, Any]] = []
    first_divergence: dict[str, Any] | None = None
    truncated = False
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        counts[tag] += max(i2 - i1, j2 - j1)
        if tag == "equal":
            size = i2 - i1
            # Trailing context closes the previous change; the rows at the end
            # of the same equal run become leading context for the next one,
            # and a short run is never printed twice.
            trailing = min(context, size) if rows else 0
            for offset in range(trailing):
                if len(rows) >= limit:
                    truncated = True
                    break
                rows.append(
                    _diff_row(
                        "equal",
                        left_records,
                        right_records,
                        i1 + offset,
                        j1 + offset,
                    )
                )
            leading = min(context, size - trailing)
            pending_context = [
                _diff_row(
                    "equal",
                    left_records,
                    right_records,
                    i2 - taken,
                    j2 - taken,
                )
                for taken in range(leading, 0, -1)
            ]
            continue
        for row in pending_context:
            if len(rows) < limit:
                rows.append(row)
        pending_context = []
        if first_divergence is None:
            first_divergence = {
                "tag": tag,
                "left_index": i1 if i1 < len(left_records) else None,
                "right_index": j1 if j1 < len(right_records) else None,
                "left_offset_hex": (
                    f"0x{left_records[i1].byte_offset:x}"
                    if i1 < len(left_records)
                    else None
                ),
                "right_offset_hex": (
                    f"0x{right_records[j1].byte_offset:x}"
                    if j1 < len(right_records)
                    else None
                ),
                "left": (
                    left_records[i1].as_dict() if i1 < len(left_records) else None
                ),
                "right": (
                    right_records[j1].as_dict() if j1 < len(right_records) else None
                ),
            }
        for offset in range(max(i2 - i1, j2 - j1)):
            if len(rows) >= limit:
                truncated = True
                break
            rows.append(
                _diff_row(
                    tag,
                    left_records,
                    right_records,
                    i1 + offset if i1 + offset < i2 else None,
                    j1 + offset if j1 + offset < j2 else None,
                )
            )
    identical = left_data == right_data
    return {
        "schema": STREAM_DIFF_SCHEMA,
        "format": left_format,
        "identical": identical,
        "left": _stream_identity(left, left_data, left_records),
        "right": _stream_identity(right, right_data, right_records),
        "record_counts": {
            "left": len(left_records),
            "right": len(right_records),
        },
        "opcode_counts": counts,
        "similarity": round(matcher.ratio(), 6),
        "first_divergence": first_divergence,
        "rows": rows,
        "rows_truncated": truncated,
        "proof": (
            "This compares two retained files by decoded record framing. A "
            "record-level difference names what changed at the boundary, not "
            "why the earlier pass emitted it."
        ),
    }


def _diff_row(
    tag: str,
    left_records: tuple[StreamRecord, ...],
    right_records: tuple[StreamRecord, ...],
    left_index: int | None,
    right_index: int | None,
) -> dict[str, Any]:
    return {
        "tag": tag,
        "left": (
            left_records[left_index].as_dict() if left_index is not None else None
        ),
        "right": (
            right_records[right_index].as_dict() if right_index is not None else None
        ),
    }
