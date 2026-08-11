"""The ledger must never be reconstructable back into the target's code.

This is a regression test for a real incident. Two campaign ledgers from a
Mickey's Speedway USA run were committed and pushed with their diff sites
quoting the target ROM's disassembly -- ``"target": "addiu\\tsp,sp,-64"``,
``"target_word": "27bdffc0"`` -- 126 sites each, between them enough to
reconstruct 129 of one function's 146 instructions. It took a history rewrite
to undo.

The fixtures below are shaped exactly like those records. The tests assert the
property that was missing: whatever else a ledger contains, the target's
instruction text and instruction words are not in it, and nothing retained in
it is a lossless index of them.
"""

from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from decomp_workbench.campaign import append_ledger
from decomp_workbench.ledger_redaction import (
    DIGEST_HEX,
    MASKED_OPCODE_SITE_LIMIT,
    REDACTION_SCHEMA,
    SITE_KEEP,
    RedactionError,
    digest_target,
    load_or_create_salt,
    mask_opcode,
    redact_record,
    salt_path,
    warn_if_unredacted,
)
from decomp_workbench.model import Comparison, CompileResult

# A real prologue's shape, in the incident's own format: assembly text beside
# the 32-bit word it decodes from.
TARGET_SITES = [
    ("addiu\tsp,sp,-64", "27bdffc0"),
    ("sw\tra,28(sp)", "afbf001c"),
    ("sw\ts0,24(sp)", "afb00018"),
    ("lui\tv0,0x8005", "3c028005"),
    ("addiu\tv0,v0,-4032", "2442f040"),
    ("jal\t0x80051f30", "0c0147cc"),
    ("sltu\tv1,v0,a1", "0045182b"),
    ("beq\tv1,zero,.L80051abc", "10600004"),
]

#: One target instruction, for the sweep-bypass tests below.
TARGET_TEXT = TARGET_SITES[0][0]

CANDIDATE_SITES = [
    ("addiu\tsp,sp,-72", "27bdffb8"),
    ("sw\tra,36(sp)", "afbf0024"),
    ("sw\ts0,32(sp)", "afb00020"),
    ("lui\tv0,0x8006", "3c028006"),
    ("addiu\tv0,v0,-2048", "2442f800"),
    ("jal\t0x80052000", "0c014800"),
    ("sltu\tv1,v0,a2", "0046182b"),
    ("beq\tv1,zero,.L80051ac0", "10600005"),
]


def make_diff_sites() -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "class": "operand",
            "target": target_text,
            "target_word": target_word,
            "candidate": candidate_text,
            "candidate_word": candidate_word,
        }
        for index, ((target_text, target_word), (candidate_text, candidate_word)) in (
            enumerate(zip(TARGET_SITES, CANDIDATE_SITES, strict=True))
        )
    ]


def make_aligned_sites() -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "aligned_row": index,
            "class": "schedule",
            "target": target_text,
            "target_index": index,
            "candidate": candidate_text,
            "candidate_index": index,
        }
        for index, ((target_text, _), (candidate_text, _)) in enumerate(
            zip(TARGET_SITES, CANDIDATE_SITES, strict=True)
        )
    ]


def make_register_sites() -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "target": target_text,
            "target_registers": ["sp", "ra", "s0"][: (index % 3) + 1],
            "candidate": candidate_text,
            "candidate_registers": ["sp", "ra", "s1"][: (index % 3) + 1],
        }
        for index, ((target_text, _), (candidate_text, _)) in enumerate(
            zip(TARGET_SITES, CANDIDATE_SITES, strict=True)
        )
    ]


def make_record() -> dict[str, Any]:
    return {
        "schema": "decomp-workbench-campaign-v1",
        "provenance": {
            # A *path*, not instruction text. A redactor that walked key names
            # would wreck this; the one under test is structural for exactly
            # this reason.
            "target": "/home/dev/build/target/func.o",
            "command": ["./compile.sh", "cand.c"],
        },
        "comparison": {
            "target": "build/target/func.o",
            "candidate": "build/cand/func.o",
            "exact": False,
            "insns": 146,
            "diff_site_classes": {"operand": 8},
            "diff_sites": make_diff_sites(),
            "aligned_diff_sites": make_aligned_sites(),
            "register_diff": make_register_sites(),
            "relocation_target_differences": [
                {
                    "instruction_index": 4,
                    "relocation_index": 0,
                    "target_instruction_offset": 16,
                    "candidate_instruction_offset": 16,
                    "target": {
                        "offset": 16,
                        "kind": "R_MIPS_HI16",
                        "symbol": "secret_target_symbol",
                        "addend": 4,
                    },
                    "candidate": {
                        "offset": 16,
                        "kind": "R_MIPS_HI16",
                        "symbol": "candidate_symbol",
                        "addend": 4,
                    },
                }
            ],
            "guidance": ["audit the earliest immediate against the target"],
        },
    }


def make_comparison(**overrides: Any) -> Comparison:
    """A Comparison with every required field filled.

    Built from the dataclass definition rather than a hand-written literal so
    the test keeps exercising the real serialised schema as that schema grows.
    """

    values: dict[str, Any] = {}
    for spec in dataclasses.fields(Comparison):
        if spec.default is not dataclasses.MISSING:
            values[spec.name] = spec.default
        elif spec.default_factory is not dataclasses.MISSING:
            values[spec.name] = spec.default_factory()
        elif spec.type in ("str", "str | None"):
            values[spec.name] = ""
        elif spec.type == "bool":
            values[spec.name] = False
        else:
            values[spec.name] = 0
    values.update(overrides)
    return Comparison(**values)


def make_result(**overrides: Any) -> CompileResult:
    fields: dict[str, Any] = {
        "source": "cand.c",
        "command": ["./compile.sh", "cand.c"],
        "returncode": 0,
        "stdout": "",
        "stderr": "",
        "object_path": "build/cand/func.o",
        "comparison": make_comparison(
            candidate="build/cand/func.o",
            target="build/target/func.o",
            diff_sites=make_diff_sites(),
            aligned_diff_sites=make_aligned_sites(),
            register_diff=make_register_sites(),
            aligned_row_receipts=[
                {
                    "aligned_row": 0,
                    "target_index": 0,
                    "candidate_index": 0,
                    "class": "register",
                    "raw_exact": False,
                    "relocation_aware_exact": False,
                }
            ],
        ),
        "cache_key": "abc123",
        "signals": [
            {
                "id": "tail",
                "kind": "target-rows-exact",
                "required": True,
                "status": "FAIL",
                "requested_rows": [0],
                "failed_rows": [0],
            }
        ],
    }
    fields.update(overrides)
    return CompileResult(**fields)


def write_ledger(directory: Path) -> dict[str, Any]:
    """Append one record through the real writer and read it back."""

    ledger = directory / "ledger.jsonl"
    append_ledger(
        ledger,
        make_result(),
        duplicate_sources=[],
        provenance={"target": "/home/dev/build/target/func.o"},
        timeout=None,
    )
    text = ledger.read_text(encoding="utf-8")
    record: dict[str, Any] = json.loads(text.splitlines()[0])
    record["_raw"] = text
    return record


class LedgerCarriesNoTargetCodeTest(unittest.TestCase):
    """The property whose absence caused the incident."""

    def test_redacted_record_contains_no_target_instruction_text(self) -> None:
        blob = json.dumps(redact_record(make_record(), b"salt"), sort_keys=True)
        for text, word in TARGET_SITES:
            self.assertNotIn(json.dumps(text)[1:-1], blob, f"{text!r} survived")
            self.assertNotIn(word, blob, f"{word!r} survived")
        self.assertNotIn("secret_target_symbol", blob)
        self.assertIn("candidate_symbol", blob)

    def test_written_ledger_contains_no_target_instruction_text(self) -> None:
        """End to end, through the one function that puts a ledger on disk."""

        with tempfile.TemporaryDirectory() as tmp:
            record = write_ledger(Path(tmp))
        for text, word in TARGET_SITES:
            self.assertNotIn(json.dumps(text)[1:-1], record["_raw"])
            self.assertNotIn(word, record["_raw"])
        self.assertEqual(record["redaction"]["schema"], REDACTION_SCHEMA)

    def test_written_ledger_is_still_a_usable_ledger(self) -> None:
        """Redaction that broke the bookkeeping would just move the problem."""

        with tempfile.TemporaryDirectory() as tmp:
            record = write_ledger(Path(tmp))
        self.assertEqual(record["cache_key"], "abc123")
        self.assertNotIn("aligned_row_receipts", record["comparison"])
        self.assertEqual(record["signals"][0]["status"], "FAIL")
        sites = record["comparison"]["diff_sites"]
        self.assertEqual(len(sites), len(TARGET_SITES))
        self.assertEqual([site["index"] for site in sites], list(range(len(sites))))
        self.assertEqual({site["class"] for site in sites}, {"operand"})
        # The candidate side is the operator's own compiler output, not the
        # ROM's, and it is what makes attempts comparable.
        for site, (text, word) in zip(sites, CANDIDATE_SITES, strict=True):
            self.assertEqual(site["candidate"], text)
            self.assertEqual(site["candidate_word"], word)

    def test_no_retained_target_field_is_invertible(self) -> None:
        """Enumerates every surviving target-side key and shows it is lossy.

        This checks the fields the *fixtures* produce. On its own it could
        never catch a new field added upstream in ``compare`` -- the fixtures
        are hand-written and would not contain it. That gap is closed
        structurally instead, by :data:`SITE_KEEP` being an allow-list; see
        ``test_unknown_site_fields_are_dropped_by_default``.
        """

        with tempfile.TemporaryDirectory() as tmp:
            record = write_ledger(Path(tmp))
        allowed = {
            "target_digest",  # 16 bits over a 32-bit space
            "target_opcode_masked",  # instruction kind, capped, operands zeroed
            "target_index",  # a position in the alignment, not content
            "target_register_count",  # how many, never which
        }
        # `dropped_fields` holds names of removed keys, never their values.
        for site in record["comparison"]["diff_sites"]:
            for name in site.get("dropped_fields", []):
                self.assertNotIn(name, set(site) - {"dropped_fields"})
        for name in ("diff_sites", "aligned_diff_sites", "register_diff"):
            for site in record["comparison"][name]:
                for key in site:
                    if key.startswith("target"):
                        self.assertIn(key, allowed, f"new target-side field {key!r}")

        sites = record["comparison"]["diff_sites"]
        for site in sites:
            self.assertEqual(len(site["target_digest"]), DIGEST_HEX)

        masked = [site for site in sites if "target_opcode_masked" in site]
        self.assertEqual(len(masked), MASKED_OPCODE_SITE_LIMIT)
        for site in masked:
            self.assertNotEqual(
                site["target_opcode_masked"], TARGET_SITES[site["index"]][1]
            )

    def test_unknown_site_fields_are_dropped_by_default(self) -> None:
        """The real regression guard: a field nobody anticipated.

        The incident's leak lived in per-site records emitted by ``compare``.
        If that emitter grows a new target-side field tomorrow, no fixture here
        will contain it and no whitelist assertion will see it -- so the
        redactor must drop it without being told. This simulates exactly that.
        """

        record = make_record()
        for site in record["comparison"]["diff_sites"]:
            site["target_pseudocode"] = "sp -= 64  /* invented upstream */"
            site["target_bytes"] = "27 bd ff c0"

        redacted = redact_record(record, b"salt")
        blob = json.dumps(redacted, sort_keys=True)

        # The values are gone...
        self.assertNotIn("sp -= 64", blob)
        self.assertNotIn("27 bd ff c0", blob)
        self.assertNotIn("invented upstream", blob)

        # ...and the names survive only as a record of what was dropped, which
        # is how an operator finds out the upstream field exists at all.
        first = redacted["comparison"]["diff_sites"][0]
        self.assertIn("target_pseudocode", first["dropped_fields"])
        self.assertIn("target_bytes", first["dropped_fields"])
        self.assertNotIn("target_pseudocode", set(first) - {"dropped_fields"})

    def test_site_keep_holds_nothing_target_valued(self) -> None:
        """The allow-list is the whole guarantee, so guard its contents."""

        for key in SITE_KEEP:
            if key.startswith("target"):
                # target_index is a position in the alignment, not content.
                self.assertEqual(key, "target_index", f"{key!r} is target content")

    def test_target_content_is_removed_at_every_depth(self) -> None:
        """The sweep used to filter only three named lists.

        Everything below reached the output verbatim until it was made
        recursive -- nested hunks, a sibling key on `comparison`, a top-level
        key, and a dict buried under an allow-listed one.
        """

        record = make_record()
        record["target_dump"] = "addiu\tsp,sp,-64"
        record["comparison"]["target_disassembly"] = ["sw\tra,28(sp)"]
        record["comparison"]["hunks"] = [
            {"start": 0, "target": "lui\tv0,0x8005", "candidate": "lui\tv0,0x8006"}
        ]
        record["comparison"]["nested"] = {"deep": {"target_bytes": "27 bd ff c0"}}

        blob = json.dumps(redact_record(record, b"salt"), sort_keys=True)
        for probe in (
            "addiu\\tsp,sp,-64",
            "sw\\tra,28(sp)",
            "lui\\tv0,0x8005",
            "27 bd ff c0",
        ):
            self.assertNotIn(probe, blob, f"{probe!r} survived the sweep")
        # ...while the candidate side of the same hunk is kept.
        self.assertIn("lui\\tv0,0x8006", blob)

    def test_paths_named_target_are_not_redacted(self) -> None:
        """``provenance.target`` and ``comparison.target`` are filesystem
        paths; redacting by key name would break resume and cache keys."""

        record = redact_record(make_record(), b"salt")
        self.assertEqual(
            record["provenance"]["target"], "/home/dev/build/target/func.o"
        )
        self.assertEqual(record["comparison"]["target"], "build/target/func.o")


class RedactionMechanismTest(unittest.TestCase):
    def test_digest_is_stable_within_a_salt(self) -> None:
        self.assertEqual(
            digest_target("27bdffc0", b"a"), digest_target("27bdffc0", b"a")
        )

    def test_digest_is_unlinkable_across_salts(self) -> None:
        """Per-ledger salts stop one rainbow table serving every campaign."""

        self.assertNotEqual(
            digest_target("27bdffc0", b"a"), digest_target("27bdffc0", b"b")
        )

    def test_digest_is_lossy_by_construction(self) -> None:
        """16 bits cannot index a 32-bit instruction space, so collisions are
        the mechanism, not a defect."""

        digests = {digest_target(f"{word:08x}", b"salt") for word in range(200_000)}
        self.assertLessEqual(len(digests), 1 << (DIGEST_HEX * 4))

    def test_masked_opcode_discards_immediates(self) -> None:
        # Same instruction, different stack frame size.
        self.assertEqual(mask_opcode("27bdffc0"), mask_opcode("27bdffb8"))

    def test_masked_opcode_discards_registers_and_offsets(self) -> None:
        self.assertEqual(mask_opcode("afbf001c"), mask_opcode("afb00018"))
        self.assertEqual(mask_opcode("0045182b"), mask_opcode("0046182b"))

    def test_masked_opcode_keeps_the_instruction_kind(self) -> None:
        # SPECIAL keeps funct, so sltu stays distinguishable from addu.
        self.assertNotEqual(mask_opcode("0045182b"), mask_opcode("00451821"))
        # ...and a load is distinguishable from a store.
        self.assertNotEqual(mask_opcode("afbf001c"), mask_opcode("8fbf001c"))

    def test_masked_opcode_rejects_nonsense(self) -> None:
        self.assertIsNone(mask_opcode("not-hex"))
        self.assertIsNone(mask_opcode(None))

    def test_register_names_are_reduced_to_a_count(self) -> None:
        record = redact_record(make_record(), b"salt")
        for original, redacted in zip(
            make_register_sites(),
            record["comparison"]["register_diff"],
            strict=True,
        ):
            self.assertNotIn("target_registers", redacted)
            self.assertEqual(
                redacted["target_register_count"], len(original["target_registers"])
            )
            self.assertEqual(
                redacted["candidate_registers"], original["candidate_registers"]
            )


class LedgerSaltTest(unittest.TestCase):
    def test_salt_is_created_once_and_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            first = load_or_create_salt(ledger)
            self.assertEqual(load_or_create_salt(ledger), first)

    def test_salt_lives_beside_the_ledger_not_inside_it(self) -> None:
        """A salt shipped inside the ledger would travel with any leak."""

        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            salt = load_or_create_salt(ledger)
            self.assertEqual(salt_path(ledger), Path(tmp) / "ledger.jsonl.salt")
            self.assertTrue(salt_path(ledger).exists())
            self.assertFalse(ledger.exists())
            append_ledger(
                ledger, make_result(), duplicate_sources=[], provenance={}, timeout=None
            )
            self.assertNotIn(salt.hex(), ledger.read_text(encoding="utf-8"))


class UnredactedLedgerWarningTest(unittest.TestCase):
    """A resumed campaign appends redacted records to an unredacted file."""

    def test_pre_redaction_ledger_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            ledger.write_text(
                json.dumps({"schema": "decomp-workbench-campaign-v1", "comparison": {}})
                + "\n",
                encoding="utf-8",
            )
            warning = warn_if_unredacted(ledger)
            self.assertIsNotNone(warning)
            assert warning is not None
            self.assertIn("written before ledger redaction", warning)

    def test_redacted_ledger_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            append_ledger(
                ledger, make_result(), duplicate_sources=[], provenance={}, timeout=None
            )
            self.assertIsNone(warn_if_unredacted(ledger))

    def test_absent_ledger_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(warn_if_unredacted(Path(tmp) / "nope.jsonl"))

    def test_mixed_ledger_is_flagged_even_when_the_first_record_is_clean(self) -> None:
        """A resumed campaign appends redacted records to an unredacted file,
        so the first line proves nothing about the rest."""

        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            append_ledger(
                ledger, make_result(), duplicate_sources=[], provenance={}, timeout=None
            )
            with ledger.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"schema": "v1", "comparison": {}}) + "\n")
            warning = warn_if_unredacted(ledger)
            self.assertIsNotNone(warning)
            assert warning is not None
            self.assertIn("1 of 2", warning)

    def test_blank_and_torn_lines_do_not_hide_an_unredacted_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            ledger.write_text("\n" + '{"schema": "v1", "comp' + "\n", encoding="utf-8")
            self.assertIsNotNone(warn_if_unredacted(ledger))

    def test_null_redaction_key_is_not_treated_as_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            ledger.write_text(
                json.dumps({"schema": "v1", "redaction": None}) + "\n", encoding="utf-8"
            )
            self.assertIsNotNone(warn_if_unredacted(ledger))


class SweepIsRecursiveAndTypeCompleteTest(unittest.TestCase):
    """The bypasses a review found in the "recursive default-deny" sweep.

    Each of these put the target's instruction text into a written record while
    the sweep reported success. They are grouped here because they are one
    defect, not six: the sweep was recursive over the two container types it
    happened to test for, and default-deny over key names spelled exactly one
    way.
    """

    SALT = b"\x00" * 16

    def emit(self, record: dict[str, Any]) -> str:
        return json.dumps(redact_record(record, self.SALT), default=str)

    def test_nested_dict_under_an_allow_listed_site_key_is_swept(self) -> None:
        """``redact_site`` copied allow-listed values with a shallow dict
        comprehension, so anything nested under ``candidate`` was verbatim."""

        text = self.emit(
            {"diff_sites": [{"index": 0, "candidate": {"target": TARGET_TEXT}}]}
        )
        self.assertNotIn(TARGET_TEXT, text)

    def test_tuples_are_traversed(self) -> None:
        """``model`` keeps tuples through ``dataclasses.asdict``; the sweep
        entered lists only, so a tuple was copied whole."""

        text = self.emit({"comparison": {"hunks": ({"target": TARGET_TEXT},)}})
        self.assertNotIn(TARGET_TEXT, text)

    def test_sets_are_traversed(self) -> None:
        text = self.emit({"comparison": {"hunks": [{"target": TARGET_TEXT}]}})
        self.assertNotIn(TARGET_TEXT, text)

    def test_a_payload_used_as_a_mapping_key_is_dropped(self) -> None:
        """Only key *names* were ever checked, never key content."""

        text = self.emit({"comparison": {TARGET_TEXT: 1}})
        self.assertNotIn(TARGET_TEXT, text)

    def test_target_key_matching_is_case_and_prefix_insensitive(self) -> None:
        for key in ("Target_dump", "TARGET", "_target_dump", "-target-listing"):
            with self.subTest(key=key):
                text = self.emit({"comparison": {key: TARGET_TEXT}})
                self.assertNotIn(TARGET_TEXT, text)

    def test_instruction_text_containing_a_slash_is_not_mistaken_for_a_path(
        self,
    ) -> None:
        """``_is_path_like`` kept any ``target*`` string containing one ``/``.
        Real objdump source-interleaved output qualifies."""

        payload = f"{TARGET_TEXT}  ; see src/main/runlink.c"
        text = self.emit({"comparison": {"target_disassembly": payload}})
        self.assertNotIn(TARGET_TEXT, text)

    def test_genuine_object_paths_still_survive(self) -> None:
        path = "/tmp/build/wb/Foo.target.o"
        record = redact_record({"provenance": {"target": path}}, self.SALT)
        self.assertEqual(record["provenance"]["target"], path)

    def test_excessive_nesting_raises_instead_of_crashing_the_campaign(self) -> None:
        """3000 levels used to unwind as an uncaught RecursionError."""

        deep: dict[str, Any] = {}
        cursor = deep
        for _ in range(3000):
            cursor["a"] = {}
            cursor = cursor["a"]
        cursor["target"] = TARGET_TEXT
        with self.assertRaises(RedactionError):
            redact_record(deep, self.SALT)

    def test_a_record_at_a_sane_depth_still_redacts(self) -> None:
        node: dict[str, Any] = {"target": TARGET_TEXT}
        for _ in range(8):
            node = {"a": node}
        text = self.emit(node)
        self.assertNotIn(TARGET_TEXT, text)


class ResumeWarningScansTheWholeFileTest(unittest.TestCase):
    def test_an_unredacted_record_past_the_old_4096_line_cap_is_found(self) -> None:
        """The docstring said "scans the file"; the default capped at 4096."""

        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            clean = json.dumps({"schema": "v1", "redaction": {"schema": "x"}})
            lines = [clean] * 5000 + [json.dumps({"schema": "v1"})]
            ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
            warning = warn_if_unredacted(ledger)
            self.assertIsNotNone(warning)
            assert warning is not None
            self.assertIn("1 of 5001", warning)

    def test_an_explicit_cap_says_it_only_looked_that_far(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.jsonl"
            ledger.write_text(
                "\n".join([json.dumps({"schema": "v1"})] * 10) + "\n",
                encoding="utf-8",
            )
            warning = warn_if_unredacted(ledger, scan_lines=4)
            assert warning is not None
            self.assertIn("the first 4 record(s)", warning)


if __name__ == "__main__":
    unittest.main()
