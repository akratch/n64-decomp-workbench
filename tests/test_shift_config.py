"""Tests for the faithful-cascade gate.

Three tiers, the shape the rest of the shift family uses. The synthetic
fixtures are handcrafted map excerpts -- not derived from any project -- each
isolating one way a candidate link can fail to reproduce the shipped one: a
symbol that moved, a section placed differently, a name that appeared or
vanished, and an image that differs. The CLI tests drive the real parser and
the real exit statuses. The two live-conformance classes replay the campaign's
own pair of cases and self-skip when the sibling `decomp_playground` checkout
is absent:

* **pilotwings64 (S6, Gate 2).** The pinned link and the symbolic link that
  one yaml line produced. It passed *first try, zero iterations*, and the
  experiment's own note is why all three checks exist: "a byte-identical
  *image* can coexist with a symbol that moved into a hole; `nm -n` diff is
  what closes that."
* **DKR (S0, shift-0x10).** A correct, healthy 0x10 relink -- and therefore
  not a faithful pair at all. This command must refuse it loudly rather than
  find something to like about it, because the difference between "my config
  edit is safe" and "my shift worked" is the difference between two commands.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import ClassVar

from decomp_workbench.cli import main
from decomp_workbench.ldmap import parse_ld_map, read_ld_map
from decomp_workbench.schema import SHIFT_METRICS_BY_KEY
from decomp_workbench.shift_config import (
    CONFIG_VERIFY_SCHEMA,
    FAITHFUL_CHECKS,
    ConfigVerification,
    verify_faithful,
    verify_lines,
)

# --------------------------------------------------------------------------
# Synthetic fixtures
# --------------------------------------------------------------------------

PINNED_MAP = """
Linker script and memory map

.header         0x00000000       0x40
 .data          0x00000000       0x40 build/header.o

.main           0x80000400       0x80 load address 0x00000040
 .text          0x80000400       0x80 build/code.o
                0x80000400                entrypoint
                0x80000440                func_a

.main_bss       0x80000480       0x40
 .bss           0x80000480       0x40 build/code.o
                0x80000480                main_BSS_START
"""

IMAGE = bytes(range(0x40)) * 2


def candidate(
    *,
    moved: str | None = None,
    size: int = 0x80,
    load: int = 0x40,
    renamed: str | None = None,
    dropped: str | None = None,
) -> str:
    """Render one candidate map, optionally broken in exactly one way."""

    text = PINNED_MAP
    if moved is not None:
        text = text.replace(
            f"0x80000440                {moved}",
            f"0x80000450                {moved}",
        )
    if size != 0x80:
        text = text.replace(
            "0x80000400       0x80 load", f"0x80000400       0x{size:x} load"
        )
    if load != 0x40:
        text = text.replace("load address 0x00000040", f"load address 0x{load:08x}")
    if renamed is not None:
        text = text.replace("func_a", renamed)
    if dropped is not None:
        text = "\n".join(
            line for line in text.splitlines() if dropped not in line
        )
    return text


def verify(candidate_text: str, **extra: object) -> ConfigVerification:
    return verify_faithful(
        pinned=parse_ld_map(PINNED_MAP, path="pinned.map"),
        candidate=parse_ld_map(candidate_text, path="candidate.map"),
        **extra,  # type: ignore[arg-type]
    )


class FaithfulPairTests(unittest.TestCase):
    """The healthy case, which has to be reachable or the gate is useless."""

    def setUp(self) -> None:
        self.found = verify(
            PINNED_MAP,
            pinned_image=IMAGE,
            candidate_image=IMAGE,
            pinned_image_path="pinned.z64",
            candidate_image_path="candidate.z64",
        )

    def test_a_pair_that_matches_is_faithful(self) -> None:
        self.assertTrue(self.found.faithful)
        self.assertEqual(self.found.differences, 0)

    def test_every_check_reports_what_it_saw(self) -> None:
        self.assertEqual(self.found.shared_symbols, 3)
        self.assertEqual(self.found.shared_sections, 3)
        self.assertEqual(self.found.symbols_moved, 0)
        self.assertEqual(self.found.sections_diverged, 0)
        self.assertIs(self.found.image_identical, True)

    def test_there_is_no_first_divergence_to_name(self) -> None:
        self.assertIsNone(self.found.first_moved_symbol)
        self.assertIsNone(self.found.first_section_divergence)
        self.assertIsNone(self.found.image_first_difference)

    def test_the_check_table_travels_with_the_report(self) -> None:
        payload = self.found.as_dict(limit=5)
        self.assertEqual(payload["schema"], CONFIG_VERIFY_SCHEMA)
        self.assertEqual(
            [item["name"] for item in payload["faithful_checks"]],
            [item.name for item in FAITHFUL_CHECKS],
        )
        self.assertEqual(payload["allowed_deltas"], [0])

    def test_every_emitted_key_is_registered(self) -> None:
        payload = self.found.as_dict(limit=5)
        emitted = set(payload)
        for key in ("moved_symbols", "section_divergences", "faithful_checks"):
            for row in payload[key]:
                emitted |= set(row)
        self.assertLessEqual(emitted, set(SHIFT_METRICS_BY_KEY))


class DivergenceTests(unittest.TestCase):
    """One broken pair per check, so no check can pass by accident."""

    def test_a_symbol_that_moved_is_caught_and_named_first(self) -> None:
        found = verify(candidate(moved="func_a"))
        self.assertFalse(found.faithful)
        self.assertEqual(found.symbols_moved, 1)
        self.assertEqual(
            found.first_moved_symbol, ("func_a", 0x80000440, 0x80000450)
        )

    def test_a_section_placed_at_a_different_size_is_caught(self) -> None:
        found = verify(candidate(size=0x90))
        self.assertFalse(found.faithful)
        divergence = found.first_section_divergence
        assert divergence is not None
        self.assertEqual(divergence.name, ".main")
        self.assertEqual(divergence.field, "size")
        self.assertEqual((divergence.pinned, divergence.candidate), (0x80, 0x90))

    def test_a_section_with_a_different_at_load_address_is_caught(self) -> None:
        """The check a symbol comparison cannot make: every symbol can be at
        its old VMA while the section is loaded from somewhere else."""

        found = verify(candidate(load=0x60))
        divergence = found.first_section_divergence
        assert divergence is not None
        self.assertEqual(divergence.field, "load_address")
        self.assertEqual((divergence.pinned, divergence.candidate), (0x40, 0x60))

    def test_a_renamed_symbol_shows_on_both_sides(self) -> None:
        found = verify(candidate(renamed="func_b"))
        self.assertFalse(found.faithful)
        self.assertEqual(found.symbols_only_in_pinned, ("func_a",))
        self.assertEqual(found.symbols_only_in_candidate, ("func_b",))
        self.assertEqual(found.symbols_moved, 0)

    def test_a_dropped_section_is_counted_not_silently_skipped(self) -> None:
        found = verify(candidate(dropped=".main_bss"))
        self.assertIn(".main_bss", found.sections_only_in_pinned)
        self.assertFalse(found.faithful)

    def test_an_image_that_differs_names_the_first_byte(self) -> None:
        other = bytearray(IMAGE)
        other[0x33] ^= 0xFF
        found = verify(
            PINNED_MAP, pinned_image=IMAGE, candidate_image=bytes(other)
        )
        self.assertFalse(found.faithful)
        self.assertIs(found.image_identical, False)
        self.assertEqual(found.image_first_difference, 0x33)

    def test_an_image_of_a_different_length_is_not_identical(self) -> None:
        found = verify(
            PINNED_MAP, pinned_image=IMAGE, candidate_image=IMAGE + b"\x00" * 16
        )
        self.assertIs(found.image_identical, False)
        self.assertEqual(found.candidate_image_bytes, len(IMAGE) + 16)

    def test_uniform_trailing_padding_is_still_a_difference(self) -> None:
        """This gate is not the audit's consistency check: there, padding is
        benign because the question is "does this image match this map". Here
        the question is "is this the same build", and it is not."""

        found = verify(
            PINNED_MAP, pinned_image=IMAGE, candidate_image=IMAGE + b"\x00" * 16
        )
        self.assertFalse(found.faithful)


class ImagePairingTests(unittest.TestCase):
    """Naming one image is refused, not half-checked."""

    def test_one_image_alone_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            verify(PINNED_MAP, pinned_image=IMAGE)
        self.assertIn("go together", str(caught.exception))

    def test_no_images_leaves_the_check_off_rather_than_passed(self) -> None:
        found = verify(PINNED_MAP)
        self.assertFalse(found.image_checked)
        self.assertIsNone(found.image_identical)
        self.assertTrue(found.faithful)

    def test_the_report_says_not_checked(self) -> None:
        text = "\n".join(verify_lines(verify(PINNED_MAP), limit=5))
        self.assertIn("image=not-checked", text)


class RenderingTests(unittest.TestCase):
    """What a reader sees, and the one line they act on."""

    def test_the_headline_leads_with_the_verdict(self) -> None:
        text = "\n".join(
            verify_lines(verify(candidate(moved="func_a")), limit=5)
        )
        self.assertIn("faithful=NO", text)
        self.assertIn("first divergent symbol: func_a", text)

    def test_a_faithful_pair_says_so(self) -> None:
        text = "\n".join(verify_lines(verify(PINNED_MAP), limit=5))
        self.assertIn("faithful=yes", text)
        self.assertIn("differences=0", text)

    def test_the_report_names_the_command_this_is_not(self) -> None:
        """A shifted pair fails every check by construction, and a reader who
        pointed this at one needs to be told which command they wanted."""

        text = "\n".join(verify_lines(verify(PINNED_MAP), limit=5))
        self.assertIn("shift rehearse", text)

    def test_every_check_prints_its_evidence(self) -> None:
        text = "\n".join(verify_lines(verify(PINNED_MAP), limit=5))
        for check in FAITHFUL_CHECKS:
            with self.subTest(check=check.name):
                self.assertIn(f"  {check.name}:", text)

    def test_the_detail_lists_print_their_cap(self) -> None:
        broken = "\n".join(
            line.replace("0x80000440", "0x80000450") for line in PINNED_MAP.splitlines()
        )
        text = "\n".join(verify_lines(verify(broken), limit=0))
        self.assertIn("moved symbols (0 of 1, --limit)", text)


class CommandTests(unittest.TestCase):
    """The exit contract: 0 faithful, 3 not, 2 could not ask."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "pinned.map").write_text(PINNED_MAP, encoding="utf-8")
        (self.root / "candidate.map").write_text(PINNED_MAP, encoding="utf-8")
        (self.root / "moved.map").write_text(
            candidate(moved="func_a"), encoding="utf-8"
        )
        (self.root / "pinned.z64").write_bytes(IMAGE)
        (self.root / "candidate.z64").write_bytes(IMAGE)

    def run_verify(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(
                [
                    "shift",
                    "config",
                    "verify",
                    "--pager",
                    "never",
                    "--width",
                    "unlimited",
                    *arguments,
                ]
            )
        return status, stdout.getvalue(), stderr.getvalue()

    def test_a_faithful_pair_exits_zero(self) -> None:
        status, output, _ = self.run_verify(
            "--pinned-map",
            str(self.root / "pinned.map"),
            "--candidate-map",
            str(self.root / "candidate.map"),
            "--pinned-image",
            str(self.root / "pinned.z64"),
            "--candidate-image",
            str(self.root / "candidate.z64"),
        )
        self.assertEqual(status, 0)
        self.assertIn("faithful=yes", output)

    def test_an_unfaithful_pair_exits_three(self) -> None:
        """Three, not one: the census contract already spells "the report was
        produced and a predicate did not hold", and this is that shape."""

        status, output, _ = self.run_verify(
            "--pinned-map",
            str(self.root / "pinned.map"),
            "--candidate-map",
            str(self.root / "moved.map"),
        )
        self.assertEqual(status, 3)
        self.assertIn("faithful=NO", output)

    def test_json_carries_the_schema_and_the_status_still_holds(self) -> None:
        status, output, _ = self.run_verify(
            "--pinned-map",
            str(self.root / "pinned.map"),
            "--candidate-map",
            str(self.root / "moved.map"),
            "--json",
        )
        payload = json.loads(output)
        self.assertEqual(payload["schema"], CONFIG_VERIFY_SCHEMA)
        self.assertFalse(payload["faithful"])
        self.assertEqual(status, 3)

    def test_a_census_predicate_composes_with_the_gate(self) -> None:
        status, output, _ = self.run_verify(
            "--pinned-map",
            str(self.root / "pinned.map"),
            "--candidate-map",
            str(self.root / "candidate.map"),
            "--census",
            "symbols_moved=0,faithful=true",
        )
        self.assertEqual(status, 0)
        self.assertIn("census: PASS faithful=true", output)

    def test_a_failed_census_on_a_faithful_pair_still_exits_three(self) -> None:
        status, _, _ = self.run_verify(
            "--pinned-map",
            str(self.root / "pinned.map"),
            "--candidate-map",
            str(self.root / "candidate.map"),
            "--census",
            "shared_symbols=99",
        )
        self.assertEqual(status, 3)

    def test_one_image_alone_is_refused_by_the_command(self) -> None:
        status, _, stderr = self.run_verify(
            "--pinned-map",
            str(self.root / "pinned.map"),
            "--candidate-map",
            str(self.root / "candidate.map"),
            "--pinned-image",
            str(self.root / "pinned.z64"),
        )
        self.assertEqual(status, 2)
        self.assertIn("go together", stderr)

    def test_a_missing_map_is_a_usage_failure(self) -> None:
        status, _, stderr = self.run_verify(
            "--pinned-map",
            str(self.root / "absent.map"),
            "--candidate-map",
            str(self.root / "candidate.map"),
        )
        self.assertEqual(status, 2)
        self.assertTrue(stderr.startswith("error: "))


# --------------------------------------------------------------------------
# Live conformance -- skips when the sibling playground checkout is absent
# --------------------------------------------------------------------------

PLAYGROUND = Path(__file__).resolve().parents[2] / "decomp_playground"
CAMPAIGN = PLAYGROUND / ".workbench" / "shift-instrumentation"
S6_ARTIFACTS = CAMPAIGN / "s6" / "artifacts"
S0_DIR = CAMPAIGN / "s0"

PW64_PINNED_MAP = S6_ARTIFACTS / "ctl-pinned.map"
PW64_PINNED_IMAGE = S6_ARTIFACTS / "ctl-pinned.z64"
PW64_SYMBOLIC_MAP = S6_ARTIFACTS / "base-symbolic.map"
PW64_SYMBOLIC_IMAGE = S6_ARTIFACTS / "base-symbolic.z64"

_HAVE_PW64 = all(
    item.is_file()
    for item in (
        PW64_PINNED_MAP,
        PW64_PINNED_IMAGE,
        PW64_SYMBOLIC_MAP,
        PW64_SYMBOLIC_IMAGE,
    )
)


@unittest.skipUnless(
    _HAVE_PW64, f"S6 pilotwings64 artifacts not found under {S6_ARTIFACTS}"
)
class Pw64GateTwoConformanceTests(unittest.TestCase):
    """S6's Gate 2, as a command instead of three shell pipelines.

    The experiment ran `cmp` on the images, `diff <(nm -n ...) <(nm -n ...)`
    on the symbols and `diff <(readelf -S ...)` on the sections, and recorded
    the result as "three independent identity checks, all first-try, zero
    iterations required". This is the same three, and the numbers below are
    the ones it wrote down.
    """

    found: ClassVar[ConfigVerification]

    @classmethod
    def setUpClass(cls) -> None:
        cls.found = verify_faithful(
            pinned=read_ld_map(PW64_PINNED_MAP),
            candidate=read_ld_map(PW64_SYMBOLIC_MAP),
            pinned_image=PW64_PINNED_IMAGE.read_bytes(),
            candidate_image=PW64_SYMBOLIC_IMAGE.read_bytes(),
            pinned_image_path=str(PW64_PINNED_IMAGE),
            candidate_image_path=str(PW64_SYMBOLIC_IMAGE),
        )

    def test_the_symbolic_link_is_faithful_to_the_pinned_one(self) -> None:
        self.assertTrue(self.found.faithful)
        self.assertEqual(self.found.differences, 0)

    def test_no_symbol_moved(self) -> None:
        """S6: "all 2754 `nm` lines identical in address, type and name"."""

        self.assertEqual(self.found.symbols_moved, 0)
        self.assertEqual(self.found.symbols_only_in_pinned, ())
        self.assertEqual(self.found.symbols_only_in_candidate, ())
        self.assertGreater(self.found.shared_symbols, 2_000)

    def test_no_section_moved(self) -> None:
        self.assertEqual(self.found.sections_diverged, 0)
        self.assertEqual(self.found.sections_only_in_pinned, ())
        self.assertEqual(self.found.sections_only_in_candidate, ())

    def test_the_images_are_byte_identical(self) -> None:
        """`sha1 ec771aedf54ee1b214c25404fb4ec51cfd43191a`, both sides."""

        self.assertIs(self.found.image_identical, True)
        self.assertEqual(self.found.image_bytes, 8_388_608)
        self.assertEqual(self.found.candidate_image_bytes, 8_388_608)

    def test_the_command_exits_zero_on_it(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            status = main(
                [
                    "shift",
                    "config",
                    "verify",
                    "--pinned-map",
                    str(PW64_PINNED_MAP),
                    "--candidate-map",
                    str(PW64_SYMBOLIC_MAP),
                    "--pinned-image",
                    str(PW64_PINNED_IMAGE),
                    "--candidate-image",
                    str(PW64_SYMBOLIC_IMAGE),
                    "--json",
                    "--census",
                    "faithful=true,symbols_moved=0",
                ]
            )
        self.assertEqual(status, 0)
        self.assertTrue(json.loads(stdout.getvalue())["faithful"])


DKR_BASE_MAP = S0_DIR / "nm-base" / "dkr.us.v77.map"
DKR_BASE_IMAGE = S0_DIR / "nm-base" / "dkr.us.v77.z64"
DKR_SHIFT_MAP = S0_DIR / "shift-0x10" / "dkr.us.v77.map"
DKR_SHIFT_IMAGE = S0_DIR / "shift-0x10" / "dkr.us.v77.z64"

_HAVE_DKR = all(
    item.is_file()
    for item in (DKR_BASE_MAP, DKR_BASE_IMAGE, DKR_SHIFT_MAP, DKR_SHIFT_IMAGE)
)


@unittest.skipUnless(
    _HAVE_DKR, f"S0 shift-instrumentation artifacts not found under {S0_DIR}"
)
class DkrShiftedPairRefusalTests(unittest.TestCase):
    """A correct shift is not a faithful pair, and must be refused as one.

    S0's `shift-0x10` build is the campaign's own positive control: it relinks
    the same objects against a padded script and every one of its ~3,900
    shared symbols moves by exactly 0 or exactly 0x10. That makes it the most
    dangerous input this command can be handed, because it is *healthy* -- a
    gate that found something to like about it would pass the one pair a
    caller most needs told apart from a config edit.
    """

    found: ClassVar[ConfigVerification]

    @classmethod
    def setUpClass(cls) -> None:
        cls.found = verify_faithful(
            pinned=read_ld_map(DKR_BASE_MAP),
            candidate=read_ld_map(DKR_SHIFT_MAP),
            pinned_image=DKR_BASE_IMAGE.read_bytes(),
            candidate_image=DKR_SHIFT_IMAGE.read_bytes(),
        )

    def test_the_pair_is_refused(self) -> None:
        self.assertFalse(self.found.faithful)

    def test_thousands_of_symbols_moved_and_the_first_is_named(self) -> None:
        self.assertEqual(self.found.shared_symbols, 3_889)
        self.assertEqual(self.found.symbols_moved, 3_804)
        first = self.found.first_moved_symbol
        assert first is not None
        self.assertEqual(first, ("main_TEXT_SIZE", 0x000D08E0, 0x000D08F0))

    def test_the_sections_moved_too(self) -> None:
        self.assertEqual(self.found.sections_diverged, 4)
        divergence = self.found.first_section_divergence
        assert divergence is not None
        self.assertEqual(divergence.name, ".main")
        self.assertEqual(divergence.field, "size")

    def test_the_images_differ_from_the_first_generated_word(self) -> None:
        """ROM 0x10 is the CRC word a post-link step patches -- the first byte
        of the image a 0x10 relink changes."""

        self.assertIs(self.found.image_identical, False)
        self.assertEqual(self.found.image_first_difference, 0x10)
        self.assertEqual(
            self.found.candidate_image_bytes, (self.found.image_bytes or 0) + 0x10
        )

    def test_the_command_exits_three_and_says_which_command_to_use(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            status = main(
                [
                    "shift",
                    "config",
                    "verify",
                    "--pinned-map",
                    str(DKR_BASE_MAP),
                    "--candidate-map",
                    str(DKR_SHIFT_MAP),
                    "--limit",
                    "3",
                    "--pager",
                    "never",
                    "--width",
                    "unlimited",
                ]
            )
        output = stdout.getvalue()
        self.assertEqual(status, 3)
        self.assertIn("faithful=NO", output)
        self.assertIn("shift rehearse", output)


if __name__ == "__main__":
    unittest.main()
