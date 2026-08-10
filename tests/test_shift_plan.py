"""Tests for the remediation queue.

Three tiers again. The synthetic reports below are handcrafted payloads --
hand-written dictionaries in the two schemas `shift plan` reads, not captured
from any project -- built so that every routing rule in `PLAN_RULES` fires
exactly once and every ordering property has a witness. The CLI tests drive
the real argument parser, the real schema check, and the real Markdown export.
The live-conformance classes build the reports from the campaign's own
artifacts through the same command a reader would run, and self-skip when the
sibling `decomp_playground` checkout is absent:

* **pilotwings64** -- the audit and both rehearsals from S6's experiment. The
  queue has to put ``D_803571F0``'s shadow at the top as a
  ``delete-redundant-pin``: the one pin four separate pieces of evidence agree
  about, and the one whose deletion S6 proved byte-identical.
* **Banjo-Kazooie** -- the audit alone, because that project has no
  shift-capable linker script yet and so has no rehearsal to merge. Its
  fourteen-section overlay window must be parked as ``structural`` rather than
  ranked, and its 37 ROM-offset pins must arrive as ``derive-pin`` candidates
  with the five that equal an ``AT()`` load address byte-for-byte leading the
  class.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, ClassVar

from decomp_workbench.cli import main
from decomp_workbench.schema import SHIFT_METRICS_BY_KEY
from decomp_workbench.shift_plan import (
    AUDIT_SCHEMA,
    DELETE_REDUNDANT_PIN,
    DERIVE_PIN,
    DUAL_SPELLING_RISK,
    INVESTIGATE,
    MIGRATE_SYMBOL,
    PLAN_RULES,
    REHEARSE_SCHEMA,
    REMEDIATION_CLASSES,
    SHIFT_PLAN_SCHEMA,
    STRUCTURAL,
    WHITELIST_CANDIDATE,
    ShiftPlan,
    build_plan,
    plan_lines,
    plan_markdown,
)

# --------------------------------------------------------------------------
# Synthetic reports
# --------------------------------------------------------------------------

#: A region table with everything the router keys off: two sections sharing
#: one VMA (the overlay shape), a blob, and a `.main`/`.main_bss` pair whose
#: boundaries a pin can land on.
REGIONS: list[dict[str, Any]] = [
    {
        "output_section": ".header",
        "kind": "header",
        "vram": 0x0,
        "size": 0x40,
        "rom": 0x0,
    },
    {
        "output_section": ".assets",
        "kind": "blob",
        "vram": 0x80200000,
        "size": 0x1000,
        "rom": 0x5E90,
    },
    {
        "output_section": ".main",
        "kind": "text",
        "vram": 0x80000400,
        "size": 0x100,
        "rom": 0x40,
    },
    {
        "output_section": ".main_bss",
        "kind": "bss",
        "vram": 0x80000500,
        "size": 0x100,
        "rom": None,
    },
    {
        "output_section": ".ovl_a",
        "kind": "text",
        "vram": 0x80010000,
        "size": 0x80,
        "rom": 0x2000,
    },
    {
        "output_section": ".ovl_b",
        "kind": "text",
        "vram": 0x80010000,
        "size": 0x80,
        "rom": 0x3000,
    },
    {
        "output_section": ".empty_bss",
        "kind": "bss",
        "vram": 0x80000500,
        "size": 0x0,
        "rom": None,
    },
]


def pin(name: str, value: int, classification: str, **extra: Any) -> dict[str, Any]:
    row = {
        "name": name,
        "value": value,
        "classification": classification,
        "window": "kseg0",
        "source": "syms.txt",
        "line": 1,
        "form": "absolute",
    }
    row.update(extra)
    return row


AUDIT: dict[str, Any] = {
    "schema": AUDIT_SCHEMA,
    "map": "build/game.map",
    "image": "build/game.z64",
    "elf": "build/game.elf",
    "regions": REGIONS,
    "blobs": [".assets"],
    "pin_sources": ["syms.txt"],
    "window_lo": 0x80000400,
    "text_words": 1_024,
    "text_regions": 2,
    "pins_total": 7,
    "pins_shown": 7,
    "scan_high": 1,
    "hits_shown": 1,
    "pins": [
        pin("D_80000540", 0x80000540, "shadowing-pin"),
        pin("D_5E90", 0x5E90, "rom-offset", window=None),
        pin("D_DEADBEEF", 0xDEAD_BEEF, "rom-offset", window=None),
        pin("D_80000560", 0x80000560, "artifact-suspect"),
        pin("D_80000600", 0x80000600, "artifact-suspect"),  # .main_bss VRAM end
        pin("D_A4040010", 0xA404_0010, "artifact-suspect", window="kseg1"),
        pin("osTvType", 0x80000300, "artifact-suspect"),  # below window_lo
        pin("SP_STATUS", 0xA404_0000, "authentic-fixed", window="kseg1"),
    ],
    "hits": [
        {
            "rom": 0x00A0,
            "value": 0x80000560,
            "tier": "high",
            "region": ".main",
            "resident_symbol": "gTable",
            "target_symbol": "gThing",
        },
        {"rom": 0x00B0, "value": 0x80000560, "tier": "low", "region": ".main"},
    ],
}


REHEARSE: dict[str, Any] = {
    "schema": REHEARSE_SCHEMA,
    "mode": "analyze",
    "base_map": "build/game.map",
    "base_image": "build/game.z64",
    "shifted_map": "shift/game.map",
    "shifted_image": "shift/game.z64",
    "base_elf": "build/game.elf",
    "shifted_elf": "shift/game.elf",
    "delta": 0x10,
    "regions": REGIONS,
    "symbol_census": True,
    "stale_shown": 2,
    "stale_confirmed": 2,
    "symbol_findings_shown": 4,
    "symbol_stale": 3,
    "shadowing_pins": 1,
    "stale_unattributed": 5,
    "stale": [
        {
            "rom": 0x00C0,
            "value": 0x80000540,
            "outcome": "stale-confirmed",
            "region": ".main",
            "target_symbol": "D_80000540",
        },
        {
            "rom": 0x00C4,
            "value": 0x80000570,
            "outcome": "stale-confirmed",
            "region": ".main",
            "target_symbol": "gOther",
        },
        {"rom": 0x00C8, "value": 0x80000578, "outcome": "noise", "region": ".main"},
    ],
    "symbol_findings": [
        {
            "name": "D_80000540",
            "value": 0x80000540,
            "classification": "shadowing-pin",
            "size": 4,
            "owning_section": ".main_bss",
        },
        {
            "name": "D_80000600",
            "value": 0x80000600,
            "classification": "symbol-stale",
            "size": 0,
            "owning_section": None,
        },
        {
            "name": "D_80000560",
            "value": 0x80000560,
            "classification": "symbol-stale",
            "size": 0,
            "owning_section": ".main_bss",
        },
        {
            "name": "D_C0FFEE00",
            "value": 0xC0FF_EE00,
            "classification": "symbol-stale",
            "size": 0,
            "owning_section": None,
        },
    ],
}


def plan(**extra: Any) -> ShiftPlan:
    return build_plan(
        audit=AUDIT,
        rehearsals=extra.pop("rehearsals", [REHEARSE]),
        audit_path="audit.json",
        rehearse_paths=["rehearse.json"],
        **extra,
    )


class RoutingTests(unittest.TestCase):
    """Every rule in the published table, one witness apiece."""

    def setUp(self) -> None:
        self.plan = plan()
        self.by_subject = {
            (item.remediation, item.subject): item for item in self.plan.items
        }

    def test_every_published_rule_fired(self) -> None:
        """A routing table with an unreachable entry is a table that lies."""

        fired = {rule for item in self.plan.items for rule in item.rules}
        self.assertEqual(fired, {item.name for item in PLAN_RULES})

    def test_a_shadowing_pin_is_a_free_win(self) -> None:
        item = self.by_subject[(DELETE_REDUNDANT_PIN, "D_80000540")]
        self.assertTrue(item.conviction)
        self.assertEqual(item.rank.kind, "match-preserving")

    def test_a_rom_offset_pin_on_an_at_extent_is_an_exemplar(self) -> None:
        """`D_5E90` equals `.assets`' own ROM placement, byte for byte."""

        item = self.by_subject[(DERIVE_PIN, "D_5E90")]
        self.assertTrue(item.exemplar)
        self.assertIn("ROM start of .assets", item.evidence[0])
        self.assertEqual(item.section, ".assets")

    def test_a_rom_offset_pin_on_no_extent_is_still_derive_pin(self) -> None:
        """The class is about the remediation, not about the strength of the
        match: a raw cartridge offset is symbolized whether or not this map
        happens to compute that exact number."""

        item = self.by_subject[(DERIVE_PIN, "D_DEADBEEF")]
        self.assertFalse(item.exemplar)
        self.assertIn("raw cartridge offset", item.evidence[0])

    def test_a_kseg0_pin_inside_a_section_needs_a_home(self) -> None:
        item = self.by_subject[(MIGRATE_SYMBOL, "D_80000560")]
        self.assertEqual(item.section, ".main_bss")

    def test_a_hardware_window_pin_is_a_declaration(self) -> None:
        item = self.by_subject[(WHITELIST_CANDIDATE, "D_A4040010")]
        self.assertEqual(item.rank.kind, "declaration")

    def test_a_pin_below_the_window_floor_is_a_declaration_too(self) -> None:
        self.assertIn((WHITELIST_CANDIDATE, "osTvType"), self.by_subject)

    def test_an_already_authentic_pin_is_not_work(self) -> None:
        """It has a reason written down already; re-queuing it would ask a
        reader to re-make a decision they made."""

        self.assertNotIn("SP_STATUS", [item.subject for item in self.plan.items])

    def test_a_high_tier_scan_hit_is_investigate_and_a_low_one_is_nothing(
        self,
    ) -> None:
        self.assertIn((INVESTIGATE, "rom:0x0000a0"), self.by_subject)
        self.assertNotIn((INVESTIGATE, "rom:0x0000b0"), self.by_subject)

    def test_a_convicted_word_with_no_shadowing_target_is_investigate(self) -> None:
        item = self.by_subject[(INVESTIGATE, "rom:0x0000c4")]
        self.assertTrue(item.conviction)

    def test_an_unmoved_symbol_on_a_boundary_is_derive_pin(self) -> None:
        item = self.by_subject[(DERIVE_PIN, "D_80000600")]
        self.assertTrue(item.exemplar)
        self.assertIn("VRAM end of .main_bss", item.evidence[0])

    def test_an_unmoved_symbol_in_no_section_at_all_is_investigate(self) -> None:
        self.assertIn((INVESTIGATE, "D_C0FFEE00"), self.by_subject)

    def test_the_text_side_is_named_as_a_risk_not_counted_as_findings(self) -> None:
        item = self.by_subject[(DUAL_SPELLING_RISK, "text-regions")]
        self.assertIn("lui/%lo", item.evidence[0])

    def test_stale_unattributed_is_the_same_risk_from_the_other_side(self) -> None:
        self.assertIn((DUAL_SPELLING_RISK, "stale-unattributed"), self.by_subject)

    def test_a_shared_vram_window_is_parked(self) -> None:
        item = self.by_subject[(STRUCTURAL, "vram:0x80010000")]
        self.assertEqual(item.rank.kind, "parked")
        self.assertIn(".ovl_a, .ovl_b", item.evidence[0])

    def test_a_zero_size_section_does_not_manufacture_a_window(self) -> None:
        """`.empty_bss` shares `.main_bss`' start by arithmetic, not design."""

        self.assertNotIn((STRUCTURAL, "vram:0x80000500"), self.by_subject)

    def test_the_blob_set_is_parked_as_one_item(self) -> None:
        item = self.by_subject[(STRUCTURAL, "blob-segments")]
        self.assertIn(".assets", item.evidence[0])


class MergeTests(unittest.TestCase):
    """One subject in one class is one job, however many reports named it."""

    def setUp(self) -> None:
        self.plan = plan()

    def test_the_pin_four_reports_agree_about_is_one_item(self) -> None:
        matches = [item for item in self.plan.items if item.subject == "D_80000540"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            sorted(matches[0].sources),
            ["audit-pin", "rehearse-stale", "shadowing"],
        )

    def test_a_static_item_a_relink_confirms_becomes_a_conviction(self) -> None:
        item = next(item for item in self.plan.items if item.subject == "D_80000560")
        self.assertIn("audit-pin", item.sources)
        self.assertIn("rehearse-symbol", item.sources)
        self.assertTrue(item.conviction)

    def test_two_deltas_collapse_into_one_line_rather_than_two(self) -> None:
        """A queue whose evidence grows with the number of deltas rehearsed
        is a queue that punishes running the experiment properly."""

        doubled = plan(rehearsals=[REHEARSE, {**REHEARSE, "delta": 0x40}])
        item = next(item for item in doubled.items if item.subject == "D_80000540")
        self.assertEqual(item.deltas, [0x10, 0x40])
        self.assertTrue(
            any("confirmed at deltas 0x10, 0x40" in line for line in item.evidence)
        )

    def test_gates_are_one_per_kind_not_one_per_report(self) -> None:
        doubled = plan(rehearsals=[REHEARSE, {**REHEARSE, "delta": 0x40}])
        item = next(item for item in doubled.items if item.subject == "D_80000540")
        self.assertEqual(len(item.gates), 3)
        self.assertTrue(any("shift config verify" in gate for gate in item.gates))
        self.assertTrue(any("shift rehearse analyze" in gate for gate in item.gates))
        self.assertTrue(any("shift audit" in gate for gate in item.gates))


class OrderingTests(unittest.TestCase):
    """The ranking the DOSSIER asked for, asserted rather than described."""

    def setUp(self) -> None:
        self.plan = plan()

    def test_convictions_lead(self) -> None:
        flags = [item.conviction for item in self.plan.items]
        self.assertEqual(flags, sorted(flags, reverse=True))

    def test_inside_a_band_the_class_order_holds(self) -> None:
        ranks = [item.rank.rank for item in self.plan.items if item.conviction]
        self.assertEqual(ranks, sorted(ranks))

    def test_structural_is_last(self) -> None:
        self.assertEqual(self.plan.items[-1].remediation, STRUCTURAL)

    def test_migrations_are_grouped_by_owning_section(self) -> None:
        sections = [
            item.section
            for item in self.plan.items
            if item.remediation == MIGRATE_SYMBOL
        ]
        self.assertEqual(sections, sorted(sections, key=lambda item: item or "~"))

    def test_exemplars_lead_their_class(self) -> None:
        derive = [item for item in self.plan.items if item.remediation == DERIVE_PIN]
        flags = [item.exemplar for item in derive]
        self.assertEqual(flags, sorted(flags, reverse=True))

    def test_the_order_is_stable_across_runs(self) -> None:
        self.assertEqual(
            [item.subject for item in self.plan.items],
            [item.subject for item in plan().items],
        )


class ReportShapeTests(unittest.TestCase):
    """What the JSON and the terminal carry, and what they refuse to hide."""

    def setUp(self) -> None:
        self.plan = plan()
        self.payload = self.plan.as_dict(limit=5)

    def test_the_census_keys_are_present_and_add_up(self) -> None:
        counts = self.payload["plan_by_class"]
        self.assertEqual(sum(counts.values()), self.payload["plan_total"])
        self.assertEqual(self.payload["plan_free_wins"], counts[DELETE_REDUNDANT_PIN])
        self.assertEqual(self.payload["plan_structural"], counts[STRUCTURAL])

    def test_every_class_is_present_even_at_zero(self) -> None:
        self.assertEqual(
            set(self.payload["plan_by_class"]),
            {item.name for item in REMEDIATION_CLASSES},
        )

    def test_the_tables_travel_with_the_report(self) -> None:
        self.assertEqual(
            [item["name"] for item in self.payload["remediation_classes"]],
            [item.name for item in REMEDIATION_CLASSES],
        )
        self.assertEqual(
            [item["name"] for item in self.payload["plan_rules"]],
            [item.name for item in PLAN_RULES],
        )

    def test_the_queue_prints_its_cap(self) -> None:
        text = "\n".join(plan_lines(self.plan, limit=3))
        self.assertIn(f"queue (3 of {self.plan.total:,}, --limit)", text)

    def test_the_loop_is_stated(self) -> None:
        text = "\n".join(plan_lines(self.plan, limit=3))
        self.assertIn("the loop:", text)
        self.assertIn("shift config verify", text)

    def test_a_capped_report_says_which_part_it_planned(self) -> None:
        capped = build_plan(
            audit={**AUDIT, "pins_shown": 3, "hits_shown": 0, "scan_high": 9},
            rehearsals=[{**REHEARSE, "stale_shown": 0}],
        )
        self.assertTrue(capped.capped)
        text = "\n".join(plan_lines(capped, limit=3))
        self.assertIn("plan_capped", text)
        self.assertIn("larger --limit", text)

    def test_a_rehearse_report_with_no_census_is_named_as_a_gap(self) -> None:
        without = build_plan(
            audit=AUDIT, rehearsals=[{**REHEARSE, "symbol_census": False}]
        )
        self.assertTrue(any("symbol census" in item for item in without.capped))

    def test_every_emitted_key_is_registered(self) -> None:
        emitted = set(self.payload)
        for key in ("plan_items", "remediation_classes", "plan_rules"):
            for row in self.payload[key]:
                emitted |= set(row)
        self.assertLessEqual(emitted, set(SHIFT_METRICS_BY_KEY))


class MarkdownTests(unittest.TestCase):
    """The work order: grouped, checkable, and gated."""

    def setUp(self) -> None:
        self.text = plan_markdown(plan())

    def test_the_loop_is_at_the_top(self) -> None:
        head = self.text.splitlines()[:5]
        self.assertTrue(any("**The loop.**" in line for line in head))

    def test_every_non_empty_class_gets_a_heading_with_its_gate(self) -> None:
        for item in REMEDIATION_CLASSES:
            with self.subTest(remediation=item.name):
                if not any(row.remediation == item.name for row in plan().items):
                    continue
                self.assertIn(f"## {item.name}", self.text)
        self.assertIn("**Gate:**", self.text)

    def test_items_are_checkboxes_carrying_their_queue_rank(self) -> None:
        self.assertIn("- [ ] **#1 ", self.text)

    def test_migrations_are_subheaded_by_section(self) -> None:
        self.assertIn("### .main_bss", self.text)

    def test_every_item_carries_a_gate_command(self) -> None:
        for line in self.text.splitlines():
            if line.startswith("- [ ] ") and "structural" not in line:
                continue
        self.assertIn("  - gate: `decomp-workbench shift config verify", self.text)

    def test_convictions_are_marked(self) -> None:
        self.assertIn("**(conviction)**", self.text)

    def test_the_placeholder_convention_is_stated_near_the_loop(self) -> None:
        head = self.text.splitlines()[:8]
        self.assertTrue(any("**Placeholders.**" in line for line in head))
        self.assertTrue(any("<rebuilt>" in line for line in head))

    def test_re_audit_and_re_rehearse_gates_point_at_the_rebuild(self) -> None:
        """WB QA: a work order's re-audit/re-rehearse gates named the
        pre-fix map/image/elf, so re-running them forever reads the same
        census -- the loop's own gate could never pass. They must name the
        rebuild instead, the way the `shift config verify` gate already
        names its candidate side."""

        pre_fix_paths = (
            "build/game.map",
            "build/game.z64",
            "build/game.elf",
            "shift/game.map",
            "shift/game.z64",
            "shift/game.elf",
        )
        saw_audit_gate = saw_rehearse_gate = False
        for line in self.text.splitlines():
            if "gate: `decomp-workbench shift audit" in line:
                saw_audit_gate = True
                self.assertIn("<rebuilt>.map", line)
                self.assertIn("<rebuilt>.z64", line)
                self.assertIn("<rebuilt>.elf", line)
                for path in pre_fix_paths:
                    self.assertNotIn(path, line)
            elif (
                "gate: `decomp-workbench shift rehearse analyze" in line
                and "--delta 0x" not in line
            ):
                # The audit-only rules (`investigate`, `dual-spelling-risk`)
                # never had a rehearse report to name in the first place;
                # their hand-written placeholder form is a different,
                # pre-existing gap and not this defect's gate.
                continue
            elif "gate: `decomp-workbench shift rehearse analyze" in line:
                saw_rehearse_gate = True
                self.assertIn("<rebuilt-base>.map", line)
                self.assertIn("<rebuilt-base>.z64", line)
                self.assertIn("<rebuilt-shifted>.map", line)
                self.assertIn("<rebuilt-shifted>.z64", line)
                for path in pre_fix_paths:
                    self.assertNotIn(path, line)
        self.assertTrue(saw_audit_gate)
        self.assertTrue(saw_rehearse_gate)

    def test_the_identity_gate_still_pins_its_baseline(self) -> None:
        """The one gate that legitimately keeps a pre-fix path concrete:
        `shift config verify` proves the rebuild against the artifact it is
        *not* allowed to have moved, so `--pinned-map`/`--pinned-image`
        stay literal while `--candidate-map`/`--candidate-image` are the
        placeholders."""

        lines = [
            line
            for line in self.text.splitlines()
            if "gate: `decomp-workbench shift config verify" in line
        ]
        self.assertTrue(lines)
        for line in lines:
            self.assertIn("--pinned-map build/game.map", line)
            self.assertIn("--pinned-image build/game.z64", line)
            self.assertIn("--candidate-map <rebuilt>.map", line)
            self.assertIn("--candidate-image <rebuilt>.z64", line)

    def test_the_closing_note_refuses_to_be_a_verdict(self) -> None:
        self.assertIn("evidence with coordinates attached", self.text)


class CommandTests(unittest.TestCase):
    """The parser, the schema check, and the export."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "audit.json").write_text(json.dumps(AUDIT), encoding="utf-8")
        (self.root / "rehearse.json").write_text(json.dumps(REHEARSE), encoding="utf-8")

    def run_plan(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(
                [
                    "shift",
                    "plan",
                    "--pager",
                    "never",
                    "--width",
                    "unlimited",
                    *arguments,
                ]
            )
        return status, stdout.getvalue(), stderr.getvalue()

    def test_the_audit_alone_is_a_plan(self) -> None:
        status, output, _ = self.run_plan("--audit", str(self.root / "audit.json"))
        self.assertEqual(status, 0)
        self.assertIn("plan_total=", output)

    def test_rehearsals_are_repeatable(self) -> None:
        status, output, _ = self.run_plan(
            "--audit",
            str(self.root / "audit.json"),
            "--rehearse",
            str(self.root / "rehearse.json"),
            "--rehearse",
            str(self.root / "rehearse.json"),
            "--json",
        )
        payload = json.loads(output)
        self.assertEqual(status, 0)
        self.assertEqual(payload["schema"], SHIFT_PLAN_SCHEMA)
        self.assertEqual(len(payload["rehearse_reports"]), 2)

    def test_the_wrong_schema_is_refused_by_name(self) -> None:
        status, _, stderr = self.run_plan("--audit", str(self.root / "rehearse.json"))
        self.assertEqual(status, 2)
        self.assertIn("carries schema", stderr)
        self.assertIn(AUDIT_SCHEMA, stderr)

    def test_a_file_that_is_not_json_is_refused(self) -> None:
        (self.root / "junk.json").write_text("not json", encoding="utf-8")
        status, _, stderr = self.run_plan("--audit", str(self.root / "junk.json"))
        self.assertEqual(status, 2)
        self.assertIn("is not JSON", stderr)

    def test_the_markdown_export_is_written_and_announced(self) -> None:
        destination = self.root / "WORK-ORDER.md"
        status, _, stderr = self.run_plan(
            "--audit",
            str(self.root / "audit.json"),
            "--rehearse",
            str(self.root / "rehearse.json"),
            "--markdown",
            str(destination),
        )
        self.assertEqual(status, 0)
        self.assertIn("wrote work order", stderr)
        self.assertIn("# Shift remediation work order", destination.read_text())

    def test_a_census_predicate_answers_with_exit_three(self) -> None:
        status, output, _ = self.run_plan(
            "--audit",
            str(self.root / "audit.json"),
            "--census",
            "plan_free_wins=99",
        )
        self.assertEqual(status, 3)
        self.assertIn("census: FAIL", output)

    def test_the_census_keys_are_registered(self) -> None:
        status, _, _ = self.run_plan(
            "--audit",
            str(self.root / "audit.json"),
            "--rehearse",
            str(self.root / "rehearse.json"),
            "--census",
            "plan_convictions=6,plan_free_wins=1,plan_structural=2",
        )
        self.assertEqual(status, 0)


# --------------------------------------------------------------------------
# Live conformance -- skips when the sibling playground checkout is absent
# --------------------------------------------------------------------------

PLAYGROUND = Path(__file__).resolve().parents[2] / "decomp_playground"
CAMPAIGN = PLAYGROUND / ".workbench" / "shift-instrumentation"
S6 = CAMPAIGN / "s6"

PW64_PROJECT = PLAYGROUND / "pilotwings64"
PW64_AUTO_SYMS = PW64_PROJECT / "build" / "splat_out" / "us" / "undefined_syms_auto.txt"
PW64_BLOBS = (".filetable", ".filesys", ".audio_seq", ".audio_ctl", ".audio_tbl")

BK_PROJECT = PLAYGROUND / "banjo-kazooie"
BK_ROOT = BK_PROJECT / "build" / "us.v10"
BK_MAP = BK_ROOT / "banjo.us.v10.map"
BK_IMAGE = BK_ROOT / "banjo.us.v10.uncompressed.z64"
BK_PIN_FILES = (
    BK_PROJECT / "symbol_addrs.us.v10.txt",
    BK_PROJECT / "manual_syms.us.v10.txt",
    BK_PROJECT / "rzip_dummy_addrs.us.v10.txt",
    BK_PROJECT / "level_symbols.us.v10.txt",
)


def run_json(arguments: list[str], destination: Path) -> dict[str, Any]:
    """Run one shift command with `--json` and keep its report on disk.

    The plan is built from what the *commands* write, not from an in-process
    object, because the reports are the interface: a key the command stops
    emitting has to break this, not be papered over by a shared builder.
    """

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        status = main([*arguments, "--json"])
    if status != 0:
        raise AssertionError(f"{' '.join(arguments)} exited {status}")
    destination.write_text(stdout.getvalue(), encoding="utf-8")
    return dict(json.loads(stdout.getvalue()))


def run_plan_cli(*arguments: str) -> tuple[int, str, str]:
    """Run `shift plan` through the real CLI, the way a maintainer would."""

    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        status = main(
            ["shift", "plan", "--pager", "never", "--width", "unlimited", *arguments]
        )
    return status, stdout.getvalue(), stderr.getvalue()


_HAVE_PW64 = (
    (S6 / "artifacts" / "base-symbolic.map").is_file()
    and (S6 / "scratch" / "base-symbolic.elf").is_file()
    and (S6 / "scratch" / "shifted-10.elf").is_file()
    and PW64_AUTO_SYMS.is_file()
)


@unittest.skipUnless(_HAVE_PW64, f"S6 pilotwings64 artifacts not found under {S6}")
class Pw64PlanConformanceTests(unittest.TestCase):
    """The queue S6's own evidence produces, top item first.

    S6's recommendation to the pilotwings64 maintainer was three commits, and
    the second was *"delete the 10 redundant pins ... they are overridden
    object definitions and the ROM is byte-identical without them"*. The queue
    has to reach the same conclusion from the reports alone, and rank it
    ahead of the twelve migrations and the sixty-two scan hits that a
    severity-ordered list would have buried it under.
    """

    plan: ClassVar[ShiftPlan]
    temp: ClassVar[tempfile.TemporaryDirectory[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        artifacts = S6 / "artifacts"
        blobs = [item for blob in PW64_BLOBS for item in ("--blob", blob)]
        audit = run_json(
            [
                "shift",
                "audit",
                "--map",
                str(artifacts / "base-symbolic.map"),
                "--image",
                str(artifacts / "base-symbolic.z64"),
                "--elf",
                str(S6 / "scratch" / "base-symbolic.elf"),
                "--pins",
                str(PW64_AUTO_SYMS),
                *blobs,
                "--limit",
                "200",
            ],
            root / "audit.json",
        )
        rehearsals = [
            run_json(
                [
                    "shift",
                    "rehearse",
                    "analyze",
                    "--base-map",
                    str(artifacts / "base-symbolic.map"),
                    "--base-image",
                    str(artifacts / "base-symbolic.z64"),
                    "--shifted-map",
                    str(artifacts / f"shifted-{delta:x}.map"),
                    "--shifted-image",
                    str(artifacts / f"shifted-{delta:x}.z64"),
                    "--base-elf",
                    str(S6 / "scratch" / "base-symbolic.elf"),
                    "--shifted-elf",
                    str(S6 / "scratch" / f"shifted-{delta:x}.elf"),
                    "--delta",
                    f"0x{delta:x}",
                    *blobs,
                    "--crc-words",
                    "0x10,0x14",
                    "--limit",
                    "100",
                ],
                root / f"rehearse-{delta:x}.json",
            )
            for delta in (0x10, 0x40)
        ]
        cls.plan = build_plan(
            audit=audit,
            rehearsals=rehearsals,
            audit_path=str(root / "audit.json"),
            rehearse_paths=[str(root / "rehearse-10.json")],
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_the_top_item_is_d_803571f0s_shadow(self) -> None:
        top = self.plan.items[0]
        self.assertEqual(top.subject, "D_803571F0")
        self.assertEqual(top.remediation, DELETE_REDUNDANT_PIN)
        self.assertTrue(top.conviction)
        self.assertEqual(top.section, ".app_bss")

    def test_it_carries_every_piece_of_evidence_that_named_it(self) -> None:
        """The audit's pin classification, the rehearsal's convicted word,
        and the symbol census's shadowing finding -- one item, three
        sources, and both deltas agreeing."""

        top = self.plan.items[0]
        self.assertEqual(
            sorted(top.sources), ["audit-pin", "rehearse-stale", "shadowing"]
        )
        self.assertEqual(top.deltas, [0x10, 0x40])

    def test_it_carries_the_gate_that_proves_the_fix_is_free(self) -> None:
        top = self.plan.items[0]
        self.assertTrue(
            any("shift config verify" in gate for gate in top.gates),
            top.gates,
        )

    def test_the_ten_free_wins_are_all_here(self) -> None:
        """S6 4.4(a) and ablation B: ten pins, deleted together, same sha1."""

        self.assertEqual(self.plan.free_wins, 10)

    def test_the_thirteen_stale_symbols_are_planned_not_dropped(self) -> None:
        """Twelve become migrations or investigations and one -- the heap
        base `D_803805E0`, which equals `.app_bss`' own end -- becomes a
        derive-pin, because the linker already computes that address."""

        from_symbols = [
            item for item in self.plan.items if "rehearse-symbol" in item.sources
        ]
        self.assertEqual(len(from_symbols), 13)
        heap = next(item for item in from_symbols if item.subject == "D_803805E0")
        self.assertEqual(heap.remediation, DERIVE_PIN)
        self.assertTrue(heap.exemplar)

    def test_the_boot_stack_pointer_is_a_migration_in_kernel_bss(self) -> None:
        stack = next(item for item in self.plan.items if item.subject == "D_802C3C90")
        self.assertEqual(stack.remediation, MIGRATE_SYMBOL)
        self.assertEqual(stack.section, ".kernel_bss")

    def test_the_blob_segments_are_parked(self) -> None:
        parked = [item for item in self.plan.items if item.remediation == STRUCTURAL]
        self.assertTrue(any(item.subject == "blob-segments" for item in parked), parked)

    def test_the_convictions_lead_and_are_the_relinks_own(self) -> None:
        self.assertGreater(self.plan.convictions, 0)
        for item in self.plan.items[: self.plan.convictions]:
            with self.subTest(subject=item.subject):
                self.assertTrue(item.conviction)

    def test_the_work_orders_gates_point_at_the_rebuild_not_S6s_artifacts(
        self,
    ) -> None:
        """QA repro: ``shift plan --audit pw64-audit.json --rehearse ...
        --markdown`` on the real pilotwings64/S6 reports, then read the gate
        commands on item #1. `--pinned-map`/`--pinned-image` legitimately
        keep naming S6's `base-symbolic` pair -- that pair is the proof
        anchor `shift config verify` is not allowed to have moved. The
        re-audit and re-rehearse gates must not: naming S6's own
        pre-existing `.map`/`.z64`/`.elf` there means re-running the gate
        reads the same unfixed artifacts and the same census, forever."""

        destination = Path(self.temp.name) / "PW64-WORK-ORDER.md"
        status, _, stderr = run_plan_cli(
            "--audit",
            str(Path(self.temp.name) / "audit.json"),
            "--rehearse",
            str(Path(self.temp.name) / "rehearse-10.json"),
            "--rehearse",
            str(Path(self.temp.name) / "rehearse-40.json"),
            "--markdown",
            str(destination),
        )
        self.assertEqual(status, 0, stderr)
        text = destination.read_text(encoding="utf-8")

        self.assertTrue(
            any("**Placeholders.**" in line for line in text.splitlines()[:8])
        )

        pre_fix_paths = (
            str(S6 / "artifacts" / "base-symbolic.map"),
            str(S6 / "artifacts" / "base-symbolic.z64"),
            str(S6 / "scratch" / "base-symbolic.elf"),
            str(S6 / "artifacts" / "shifted-10.map"),
            str(S6 / "artifacts" / "shifted-10.z64"),
            str(S6 / "scratch" / "shifted-10.elf"),
        )
        saw_audit_gate = saw_rehearse_gate = False
        for line in text.splitlines():
            if "gate: `decomp-workbench shift audit" in line:
                saw_audit_gate = True
                self.assertIn("<rebuilt>.map", line)
                self.assertIn("<rebuilt>.z64", line)
                self.assertIn("<rebuilt>.elf", line)
                for path in pre_fix_paths:
                    self.assertNotIn(path, line)
            elif (
                "gate: `decomp-workbench shift rehearse analyze" in line
                and "--delta 0x" in line
            ):
                saw_rehearse_gate = True
                self.assertIn("<rebuilt-base>.map", line)
                self.assertIn("<rebuilt-shifted>.map", line)
                for path in pre_fix_paths:
                    self.assertNotIn(path, line)
            elif "gate: `decomp-workbench shift config verify" in line:
                # The one gate allowed to keep naming S6's pre-fix pair --
                # it is the baseline the fix must not have moved.
                self.assertIn(str(S6 / "artifacts" / "base-symbolic.map"), line)
                self.assertIn(str(S6 / "artifacts" / "base-symbolic.z64"), line)
                self.assertIn("<rebuilt>.map", line)
                self.assertIn("<rebuilt>.z64", line)
        self.assertTrue(saw_audit_gate)
        self.assertTrue(saw_rehearse_gate)


_HAVE_BK = (
    BK_MAP.is_file()
    and BK_IMAGE.is_file()
    and all(item.is_file() for item in BK_PIN_FILES)
)


@unittest.skipUnless(_HAVE_BK, f"Banjo-Kazooie artifacts not found under {BK_ROOT}")
class BkPlanConformanceTests(unittest.TestCase):
    """The hard-tail patient, planned from a static audit alone.

    Banjo-Kazooie has no shift-capable linker script yet, so there is no
    rehearsal to merge and every item is a suspicion rather than a conviction
    -- which is exactly the shape the DOSSIER predicted for this patient
    ("Needs: classification"). Two properties matter: the fourteen-section
    overlay window is *named and parked* rather than ranked, and the 37
    ROM-offset pins arrive as a mechanical class with the five that equal an
    `AT()` load address byte-for-byte leading it.
    """

    plan: ClassVar[ShiftPlan]
    temp: ClassVar[tempfile.TemporaryDirectory[str]]

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        audit = run_json(
            [
                "shift",
                "audit",
                "--map",
                str(BK_MAP),
                "--image",
                str(BK_IMAGE),
                *[item for path in BK_PIN_FILES for item in ("--pins", str(path))],
                "--blobs",
                "auto",
                "--limit",
                "200",
            ],
            root / "audit.json",
        )
        cls.plan = build_plan(audit=audit, audit_path=str(root / "audit.json"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_nothing_is_a_conviction_without_a_relink(self) -> None:
        self.assertEqual(self.plan.convictions, 0)

    def test_the_overlay_window_is_parked_with_its_fourteen_sections(self) -> None:
        item = next(
            row
            for row in self.plan.items
            if row.remediation == STRUCTURAL and row.subject == "vram:0x803863f0"
        )
        self.assertIn("14 output sections share", item.title)
        for section in (".CC", ".GV", ".MMM", ".emptyLvl"):
            with self.subTest(section=section):
                self.assertIn(section, item.evidence[0])

    def test_the_parked_items_are_at_the_bottom_of_the_queue(self) -> None:
        remediations = [item.remediation for item in self.plan.items]
        self.assertEqual(
            remediations[-self.plan.structural :], [STRUCTURAL] * self.plan.structural
        )

    def test_the_37_rom_offset_pins_are_derive_pin_candidates(self) -> None:
        derive = [item for item in self.plan.items if item.remediation == DERIVE_PIN]
        from_rom_offsets = [
            item for item in derive if "audit-rom-offset-pin" in item.rules
        ]
        self.assertGreaterEqual(len(from_rom_offsets), 37)

    def test_the_five_at_extent_matches_are_the_queues_exemplars(self) -> None:
        """S7 measured the identity: `D_5E90`, `D_D846C0`, `D_D954B0`,
        `D_EA3EB0` and `D_EADE60` are, byte for byte, the `AT()` load
        addresses of `.assets`, `.soundfont1ctl`, `.soundfont1tbl`,
        `.soundfont2ctl` and `.soundfont2tbl`."""

        exemplars = {
            item.subject: item.section
            for item in self.plan.items
            if item.remediation == DERIVE_PIN and item.exemplar
        }
        self.assertEqual(
            {
                "D_5E90": ".assets",
                "D_D846C0": ".soundfont1ctl",
                "D_D954B0": ".soundfont1tbl",
                "D_EA3EB0": ".soundfont2ctl",
                "D_EADE60": ".soundfont2tbl",
            }.items()
            & exemplars.items(),
            {
                "D_5E90": ".assets",
                "D_D846C0": ".soundfont1ctl",
                "D_D954B0": ".soundfont1tbl",
                "D_EA3EB0": ".soundfont2ctl",
                "D_EADE60": ".soundfont2tbl",
            }.items(),
        )

    def test_the_exemplars_lead_the_class_in_the_queue(self) -> None:
        derive = [item for item in self.plan.items if item.remediation == DERIVE_PIN]
        flags = [item.exemplar for item in derive]
        self.assertEqual(flags, sorted(flags, reverse=True))

    def test_the_plan_says_which_part_of_the_scan_it_planned(self) -> None:
        """`scan_high` is 1,581 and no report carries 1,581 rows; a plan that
        did not say so would look like the whole job."""

        self.assertTrue(any("scan hits" in item for item in self.plan.capped))

    def test_the_work_order_exports(self) -> None:
        text = plan_markdown(self.plan)
        self.assertIn("## structural", text)
        self.assertIn("## derive-pin", text)


if __name__ == "__main__":
    unittest.main()
