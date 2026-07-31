"""Keep the target ROM's instruction text out of ledger files.

A campaign compares candidate objects against a *target* object built from a
game's ROM. The comparison that goes on screen quotes both sides -- that is the
point of the tool, and it happens on the operator's own machine against their
own legally dumped ROM. The ledger is different: it is a file, files get
committed, and committed files get pushed.

That is not hypothetical. Two ``ledger.jsonl`` files from a Mickey's Speedway
USA campaign reached a public remote with 126 diff-site records apiece, each
carrying ``"target": "addiu\\tsp,sp,-64"`` and ``"target_word": "27bdffc0"``.
Between them they were enough to reconstruct 129 of one function's 146
instructions verbatim. Removing them took a history rewrite.

The gap was architectural, not clerical: the ledger's schema *asked* for the
target's disassembly, so writing a correct ledger and leaking the ROM were the
same act. This module closes that by redacting at the serialisation boundary --
the one place every ledger record passes through -- so:

* the in-memory :class:`~decomp_workbench.model.Comparison` is untouched, and
  every renderer, report and diagnosis keeps showing the full diff;
* nothing that reaches disk can be turned back into instruction text.

What survives redaction is what the ledger is actually *for*: per-site
bookkeeping. Which sites differ, how many, of what class, and whether the
target at a given index is still the same one it was on an earlier run. What
does not survive is any way to read the ROM out of it.

Three mechanisms, in order of how much they give up:

``target_digest``
    A **16-bit** salted digest of the target word (or, where there is no word,
    of its assembly text). Sixteen bits is deliberate: it is ample to notice
    that the target at some index changed between records -- a 1-in-65536 miss
    -- and it is hopeless as a reconstruction primitive, because every digest
    has on the order of 2^16 preimages in the 32-bit instruction space. The
    security property therefore does not depend on the salt staying secret,
    which is the only kind of security property worth relying on here. The
    salt still earns its place: it is per-ledger, so identical instructions in
    two different campaigns do not produce identical digests, and no rainbow
    table spans ledgers.

``target_opcode_masked``
    The instruction word with every operand field zeroed -- primary opcode
    only, plus the ``funct`` selector for SPECIAL and the ``rt`` selector for
    REGIMM. It names the *kind* of instruction and says nothing about which
    registers or which immediates. Emitted for at most
    :data:`MASKED_OPCODE_SITE_LIMIT` sites per list, because a cap is what
    keeps "a few opcodes, for orientation" from becoming "an opcode sequence",
    which is most of a disassembly.

``target_register_count``
    Register-class sites recorded the target's register *names*. A sequence of
    register sets is operand data; its length is bookkeeping. Only the length
    survives.

The candidate side is never redacted. It is the operator's own compiler output
from their own C, it is what makes the ledger useful for ranking attempts, and
it is not the ROM's.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path
from typing import Any

#: Marks a record written by a redacting writer. A reader that finds this key
#: knows the target side is masked by construction; a reader that does not find
#: it is looking at a pre-redaction ledger and should treat it as ROM-derived.
REDACTION_SCHEMA = "decomp-workbench-ledger-redaction-v1"

#: Site lists under ``comparison`` whose records describe the target. Named
#: explicitly rather than discovered by key name, because ``comparison.target``
#: and ``provenance.target`` are *paths*, and a key-name walk would corrupt
#: them.
SITE_LISTS: tuple[str, ...] = ("diff_sites", "aligned_diff_sites", "register_diff")

#: Target-side keys removed from every site record.
REDACTED_KEYS: tuple[str, ...] = ("target", "target_word", "target_registers")

#: Digest width. 4 hex characters = 16 bits: enough to detect change, far too
#: little to reconstruct. Do not widen this without re-reading the module
#: docstring -- at 32 bits the digest becomes a lossless index of the word.
DIGEST_HEX = 4

#: How many sites per list may carry a masked opcode. Small on purpose.
MASKED_OPCODE_SITE_LIMIT = 3

SALT_BYTES = 16


def salt_path(ledger_path: str | Path) -> Path:
    """Return the sidecar file holding this ledger's digest salt."""

    path = Path(ledger_path)
    return path.with_name(path.name + ".salt")


def load_or_create_salt(ledger_path: str | Path) -> bytes:
    """Return this ledger's salt, generating it on first use.

    Kept beside the ledger rather than inside it so that a ledger which does
    leak carries no rainbow-table shortcut with it. Written 0600 and, being a
    per-machine random value, is not something to commit -- the consuming
    project's clean-room gate should refuse it, and this project's .gitignore
    already does.
    """

    path = salt_path(ledger_path)
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if raw:
            return bytes.fromhex(raw)
    except (OSError, ValueError):
        pass
    salt = secrets.token_bytes(SALT_BYTES)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create loses a race harmlessly: whoever lost re-reads the
    # winner's salt, so a ledger never mixes two salts.
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raw = path.read_text(encoding="utf-8").strip()
        return bytes.fromhex(raw)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(salt.hex())
    return salt


def digest_target(value: Any, salt: bytes) -> str:
    """Return the lossy salted digest of one target word or assembly string."""

    text = value if isinstance(value, str) else repr(value)
    keyed = hashlib.blake2s(text.encode("utf-8"), key=salt, digest_size=8)
    return keyed.hexdigest()[:DIGEST_HEX]


def mask_opcode(word: Any) -> str | None:
    """Return ``word`` with all operand fields zeroed, or None if it will not parse.

    Keeps the primary opcode (bits 31..26). For SPECIAL (opcode 0) the ``funct``
    field (bits 5..0) is what names the instruction, and for REGIMM (opcode 1)
    it is ``rt`` (bits 20..16); those selectors are kept so the result says
    "this is an ``addu``" rather than "this is a SPECIAL". Registers,
    immediates, shift amounts and branch/jump targets are all discarded.
    """

    if not isinstance(word, str):
        return None
    try:
        value = int(word, 16)
    except ValueError:
        return None
    if value < 0 or value > 0xFFFFFFFF:
        return None
    opcode = (value >> 26) & 0x3F
    masked = opcode << 26
    if opcode == 0x00:  # SPECIAL: funct names the instruction
        masked |= value & 0x3F
    elif opcode == 0x01:  # REGIMM: rt names the instruction
        masked |= value & 0x001F0000
    return f"{masked:08x}"


def redact_site(
    site: dict[str, Any], salt: bytes, *, mask_opcodes: bool
) -> dict[str, Any]:
    """Return a copy of one diff-site record with the target side masked."""

    out = {key: value for key, value in site.items() if key not in REDACTED_KEYS}

    word = site.get("target_word")
    text = site.get("target")
    source = word if isinstance(word, str) and word else text
    if isinstance(source, str) and source:
        out["target_digest"] = digest_target(source, salt)

    if mask_opcodes:
        masked = mask_opcode(word)
        if masked is not None:
            out["target_opcode_masked"] = masked

    registers = site.get("target_registers")
    if isinstance(registers, (list, tuple)):
        out["target_register_count"] = len(registers)

    return out


def redact_comparison(comparison: Any, salt: bytes) -> Any:
    """Return ``comparison`` with every target-side site field masked."""

    if not isinstance(comparison, dict):
        return comparison
    out = dict(comparison)
    for name in SITE_LISTS:
        sites = out.get(name)
        if not isinstance(sites, list):
            continue
        out[name] = [
            redact_site(site, salt, mask_opcodes=position < MASKED_OPCODE_SITE_LIMIT)
            if isinstance(site, dict)
            else site
            for position, site in enumerate(sites)
        ]
    return out


def redact_record(record: dict[str, Any], salt: bytes) -> dict[str, Any]:
    """Return one ledger record with the target ROM's instruction text removed.

    Everything outside ``comparison``'s site lists is passed through untouched,
    including ``provenance`` -- whose ``target`` is a filesystem path and whose
    contents feed the cache key.
    """

    out = dict(record)
    if "comparison" in out:
        out["comparison"] = redact_comparison(out["comparison"], salt)
    out["redaction"] = {
        "schema": REDACTION_SCHEMA,
        "digest_bits": DIGEST_HEX * 4,
        "masked_opcode_sites": MASKED_OPCODE_SITE_LIMIT,
    }
    return out
