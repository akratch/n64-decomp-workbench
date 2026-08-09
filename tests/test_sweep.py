"""The sweep framework, tested against the incidents that shaped it.

Every case is a thing one campaign paid for: a catalogue keyed by the site
alone that kept the wrong carrier; a class letter a regex silently dropped; a
scorer that read a wrong instruction count as a rejection; a removal experiment
nobody ran, so ten rows of pure cost rode along for several stages.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import main
from decomp_workbench.coverage import SweepCoverage
from decomp_workbench.csource import declarations, strip_noncode
from decomp_workbench.sweep import (
    GENERATOR_CLASSES,
    SweepError,
    SweepManifest,
    Variant,
    VariantKey,
    check_keys,
    known_class,
    read_manifest,
    write_family,
)
from decomp_workbench.sweep_generators import (
    carrier_pool,
    commutative_family,
    copy_family,
    fusion_donors,
    fusion_family,
    hoist_family,
    parse_construct,
    removal_family,
)
from decomp_workbench.sweep_ingest import ingest_lines, ingest_sweep

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "fixtures" / "sweep-base.c"

SOURCE = """void demo(Object *obj) {
    f32 lead;
    f32 span;
    f32 reach;
    f32 carry;

    lead = obj->x * obj->y;
    span = lead + obj->z;
    reach = obj->speed * (obj->scale + obj->trim);
    if (span != 0.0f);
    carry = reach;
    limit(carry * obj->radius);
    tail(span);
}
"""

TARGET_DUMP = """
00000000 <demo>:
   0: 27bdffe8  addiu $sp,$sp,-24
   4: afbf0014  sw $ra,20($sp)
   8: 8c8e0000  lw $t6,0($a0)
   c: 03e00008  jr $ra
  10: 27bd0018  addiu $sp,$sp,24
"""

EXACT_DUMP = TARGET_DUMP

SHIFTED_DUMP = """
00000000 <demo>:
   0: 27bdffe8  addiu $sp,$sp,-24
   4: afbf0014  sw $ra,20($sp)
   8: 8c8e0000  lw $t6,0($a0)
   c: 000e7080  sll $t6,$t6,2
  10: 03e00008  jr $ra
  14: 27bd0018  addiu $sp,$sp,24
"""


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with (
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class SourceCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "work.c"
        self.path.write_text(SOURCE, encoding="utf-8")

    @property
    def code(self) -> list[str]:
        return strip_noncode(self.path.read_text(encoding="utf-8"))


class RegistryTests(unittest.TestCase):
    def test_an_unregistered_class_is_an_error_not_a_shorter_table(self) -> None:
        """One campaign's `^[NHGME](\\d+)_` dropped two new classes in silence."""

        with self.assertRaises(SweepError) as raised:
            known_class("Z")
        message = str(raised.exception)
        self.assertIn("not a generator class", message)
        for letter in ("N", "O", "P", "A"):
            self.assertIn(f"{letter} (", message)

    def test_every_registered_class_describes_itself(self) -> None:
        for letter, entry in GENERATOR_CLASSES.items():
            with self.subTest(letter=letter):
                self.assertEqual(entry.letter, letter)
                self.assertTrue(entry.name and entry.description)

    def test_a_variant_key_checks_its_class_on_construction(self) -> None:
        with self.assertRaises(SweepError):
            VariantKey(site="L1", generator_class="Z")


class KeyTests(unittest.TestCase):
    def variant(self, site: str, carrier: str, text: str = "x") -> Variant:
        return Variant(
            key=VariantKey(site=site, generator_class="O", carrier=carrier),
            filename=f"{site}.{carrier}.c",
            text=text,
            description=f"{site} into {carrier}",
        )

    def test_one_site_and_two_carriers_are_two_experiments(self) -> None:
        """L65: the carrier's declaration index selected the whole delta."""

        variants = (self.variant("L920", "lead"), self.variant("L920", "reach"))
        check_keys(variants)
        self.assertEqual(
            {item.key.label for item in variants},
            {"O.L920.lead", "O.L920.reach"},
        )

    def test_a_repeated_triple_is_a_generator_defect(self) -> None:
        with self.assertRaises(SweepError) as raised:
            check_keys((self.variant("L920", "lead"), self.variant("L920", "lead")))
        self.assertIn("share the key", str(raised.exception))

    def test_a_key_with_no_carrier_reads_without_a_placeholder(self) -> None:
        key = VariantKey(site="L14", generator_class="N")
        self.assertEqual(key.label, "N.L14")


class CarrierPoolTests(SourceCase):
    def test_a_dead_local_is_free_and_a_live_one_says_why(self) -> None:
        pool = carrier_pool(self.path, at=12)
        verdicts = {item.name: item.verdict for item in pool.carriers}
        self.assertEqual(verdicts["lead"], "dead")
        self.assertEqual(verdicts["span"], "live")
        refusal = next(item for item in pool.carriers if item.name == "span")
        self.assertIn("reads it before anything writes it", refusal.reason)

    def test_the_pool_is_ordered_by_declaration_index(self) -> None:
        pool = carrier_pool(self.path, at=12)
        usable = [item.declaration_index for item in pool.usable]
        self.assertEqual(usable, sorted(usable))

    def test_a_fresh_declaration_is_never_proposed(self) -> None:
        """L68: a fresh f32 costs 8 frame bytes and the frame gate rejects it."""

        pool = carrier_pool(self.path, at=12)
        declared = {item.name for item in declarations(self.code)}
        self.assertTrue({item.name for item in pool.carriers} <= declared)
        self.assertIn("frame gate rejects it", json.dumps(pool.as_dict()))

    def test_a_local_whose_address_escapes_is_refused(self) -> None:
        self.path.write_text(
            SOURCE.replace("tail(span);", "tail(&lead);"), encoding="utf-8"
        )
        pool = carrier_pool(self.path, at=12)
        lead = next(item for item in pool.carriers if item.name == "lead")
        self.assertEqual(lead.verdict, "escapes")
        self.assertFalse(lead.usable)

    def test_a_type_filter_narrows_the_pool(self) -> None:
        pool = carrier_pool(self.path, at=12, wanted_type="s32")
        self.assertEqual(pool.carriers, ())

    def test_a_line_past_the_end_names_the_file_length(self) -> None:
        with self.assertRaises(Exception) as raised:
            carrier_pool(self.path, at=999)
        self.assertIn("--at names line 999", str(raised.exception))


class RemovalTests(SourceCase):
    def test_the_lattice_carries_its_own_control(self) -> None:
        """A price is a difference; both terms are built in the same run."""

        manifest = removal_family(
            self.path,
            constructs=(parse_construct("10=deadread"), parse_construct("11=copy")),
        )
        sites = [item.key.site for item in manifest.variants]
        self.assertEqual(sites[0], "control")
        self.assertEqual(
            manifest.variants[0].text, self.path.read_text(encoding="utf-8")
        )
        self.assertIn("L10", sites)
        self.assertIn("L11", sites)
        self.assertIn("L10+L11", sites)

    def test_the_joint_point_is_always_included(self) -> None:
        constructs = tuple(parse_construct(item) for item in ("10=a", "11=b", "12=c"))
        manifest = removal_family(self.path, constructs=constructs, order=1)
        self.assertIn("L10+L11+L12", [item.key.site for item in manifest.variants])

    def test_a_removal_that_orphans_a_read_is_flagged_not_hidden(self) -> None:
        manifest = removal_family(self.path, constructs=(parse_construct("11=copy"),))
        removal = next(item for item in manifest.variants if item.key.site == "L11")
        self.assertIn("read-before-definition", removal.detail["semantics"])
        self.assertIn("carry", removal.detail["semantics"])

    def test_removing_a_line_inside_a_frozen_zone_is_refused_by_name(self) -> None:
        manifest = removal_family(
            self.path,
            constructs=(parse_construct("10=deadread"),),
            frozen=((9, 11),),
        )
        self.assertEqual([item["site"] for item in manifest.dropped], ["L10"])
        self.assertIn("frozen zone 9..11", manifest.dropped[0]["reason"])

    def test_naming_no_construct_says_what_a_construct_is(self) -> None:
        with self.assertRaises(SweepError) as raised:
            removal_family(self.path, constructs=())
        self.assertIn("--construct LO..HI=label", str(raised.exception))

    def test_a_construct_past_the_end_of_the_file_is_refused(self) -> None:
        with self.assertRaises(SweepError) as raised:
            removal_family(self.path, constructs=(parse_construct("900"),))
        self.assertIn("names line 900", str(raised.exception))


class HoistTests(SourceCase):
    def test_the_deep_hoist_reaches_a_leaf_no_top_level_split_can(self) -> None:
        """WB-104: a nested leaf is a different class with a different price."""

        deep = hoist_family(self.path, line=9, classes=("O",), carriers=("lead",))
        leaves = {item.detail["leaf"] for item in deep.variants}
        self.assertIn("obj->trim", leaves)

        shallow = hoist_family(self.path, line=9, classes=("H",), carriers=("lead",))
        self.assertNotIn(
            "obj->trim", {item.detail["leaf"] for item in shallow.variants}
        )

    def test_one_line_and_two_carriers_are_two_variants(self) -> None:
        manifest = hoist_family(
            self.path, line=9, classes=("H",), carriers=("lead", "carry")
        )
        carriers = {item.key.carrier for item in manifest.variants}
        self.assertEqual(carriers, {"lead", "carry"})
        self.assertEqual(
            len({item.text for item in manifest.variants}), len(manifest.variants)
        )

    def test_the_compound_assignment_class_exists(self) -> None:
        self.path.write_text(
            SOURCE.replace("    span = lead + obj->z;", "    span *= lead + obj->z;"),
            encoding="utf-8",
        )
        manifest = hoist_family(self.path, line=8, classes=("P",), carriers=("lead",))
        self.assertEqual(
            [item.key.generator_class for item in manifest.variants], ["P"]
        )
        self.assertIn("lead = lead + obj->z;", manifest.variants[0].text)

    def test_the_call_argument_class_exists(self) -> None:
        manifest = hoist_family(self.path, line=12, classes=("A",), carriers=("lead",))
        self.assertEqual(
            [item.key.generator_class for item in manifest.variants], ["A"]
        )
        self.assertIn("lead = carry * obj->radius;", manifest.variants[0].text)

    def test_no_carrier_names_the_command_that_says_why(self) -> None:
        self.path.write_text(
            "void demo(Object *obj) {\n    f32 span;\n    span = obj->x;\n"
            "    tail(span + obj->y * obj->z);\n}\n",
            encoding="utf-8",
        )
        with self.assertRaises(SweepError) as raised:
            hoist_family(self.path, line=4, classes=("A",))
        message = str(raised.exception)
        self.assertIn("sweep carriers", message)
        self.assertIn("mints a frame slot", message)

    def test_an_unknown_hoist_class_lists_the_four(self) -> None:
        with self.assertRaises(SweepError) as raised:
            hoist_family(self.path, line=9, classes=("Q",), carriers=("lead",))
        self.assertIn("not a hoist class", str(raised.exception))

    def test_a_carrier_this_file_does_not_declare_is_refused(self) -> None:
        with self.assertRaises(SweepError) as raised:
            hoist_family(self.path, line=9, classes=("H",), carriers=("nowhere",))
        self.assertIn("does not declare nowhere", str(raised.exception))


class CommutativeTests(SourceCase):
    def sites(self, manifest: SweepManifest) -> set[str]:
        return {item.description for item in manifest.variants}

    def test_a_pointer_declarator_is_not_a_multiplication(self) -> None:
        manifest = commutative_family(self.path)
        for item in manifest.variants:
            self.assertNotIn("Object", item.description)

    def test_a_swap_that_would_reassociate_is_never_offered(self) -> None:
        """`a + b * c` holds no exchangeable `a + b`: that is a reassociation."""

        self.path.write_text(
            "void demo(Object *obj) {\n    f32 span;\n"
            "    span = obj->a + obj->b * obj->c;\n    tail(span);\n}\n",
            encoding="utf-8",
        )
        manifest = commutative_family(self.path)
        described = self.sites(manifest)
        self.assertEqual(len(described), 1)
        self.assertIn("obj->b * obj->c exchanged", described.pop())

    def test_a_parenthesized_subexpression_is_its_own_pair(self) -> None:
        manifest = commutative_family(self.path, lines=(9,))
        self.assertEqual(len(manifest.variants), 2)
        self.assertIn(
            "obj->scale + obj->trim exchanged", " ".join(self.sites(manifest))
        )

    def test_a_comparison_offers_nothing(self) -> None:
        with self.assertRaises(SweepError) as raised:
            commutative_family(self.path, lines=(10,))
        self.assertIn("no exchangeable commutative operand pair", str(raised.exception))

    def test_the_exchange_is_textually_pure(self) -> None:
        manifest = commutative_family(self.path, lines=(7,))
        self.assertIn("lead = obj->y * obj->x;", manifest.variants[0].text)


class CopyTests(SourceCase):
    def test_a_copy_is_dropped_and_its_reads_rehosted(self) -> None:
        manifest = copy_family(self.path)
        self.assertEqual(len(manifest.variants), 1)
        text = manifest.variants[0].text
        self.assertNotIn("carry = reach;", text)
        self.assertIn("limit(reach * obj->radius);", text)

    def test_a_copy_whose_source_is_rewritten_is_refused_with_the_line(self) -> None:
        self.path.write_text(
            SOURCE.replace(
                "    limit(carry * obj->radius);",
                "    reach = 0.0f;\n    limit(carry * obj->radius);",
            ),
            encoding="utf-8",
        )
        manifest = copy_family(self.path)
        self.assertEqual(manifest.variants, ())
        self.assertIn("reach is written at line 12", manifest.dropped[0]["reason"])

    def test_a_file_with_no_copy_says_so(self) -> None:
        self.path.write_text(
            "void demo(void) {\n    f32 span;\n    span = 1.0f;\n    tail(span);\n}\n",
            encoding="utf-8",
        )
        with self.assertRaises(SweepError) as raised:
            copy_family(self.path)
        self.assertIn("no copy of the form", str(raised.exception))


class FusionTests(SourceCase):
    def test_a_declaration_block_does_not_make_every_range_overlap(self) -> None:
        donors = fusion_donors(self.path, target="carry")
        lead = next(item for item in donors if item.name == "lead")
        self.assertTrue(lead.disjoint)
        self.assertIn("dies at line", lead.reason)

    def test_an_overlapping_range_is_refused_with_both_ranges(self) -> None:
        donors = fusion_donors(self.path, target="carry")
        span = next(item for item in donors if item.name == "span")
        self.assertFalse(span.disjoint)
        self.assertIn("overlaps the target's", span.reason)

    def test_a_fused_variant_drops_the_donor_and_renames_its_uses(self) -> None:
        manifest = fusion_family(self.path, target="carry")
        self.assertEqual([item.key.site for item in manifest.variants], ["lead->carry"])
        text = manifest.variants[0].text
        self.assertNotIn("f32 lead;", text)
        self.assertIn("carry = obj->x * obj->y;", text)

    def test_naming_an_overlapping_donor_refuses_it_rather_than_fusing(self) -> None:
        manifest = fusion_family(self.path, target="carry", donors=("span",))
        self.assertEqual(manifest.variants, ())
        self.assertIn("overlaps", manifest.dropped[0]["reason"])

    def test_a_target_this_file_does_not_declare_is_refused(self) -> None:
        with self.assertRaises(Exception) as raised:
            fusion_donors(self.path, target="nowhere")
        self.assertIn("does not declare", str(raised.exception))


class ManifestTests(SourceCase):
    def manifest(self) -> SweepManifest:
        return removal_family(
            self.path,
            constructs=(parse_construct("10=deadread"), parse_construct("11=copy")),
        )

    def test_a_written_family_reads_back_with_every_key(self) -> None:
        directory = self.root / "regress"
        placed = write_family(self.manifest(), directory=directory)
        again = read_manifest(directory)
        self.assertEqual(
            [item.key.as_dict() for item in again.variants],
            [item.key.as_dict() for item in placed.variants],
        )
        self.assertEqual(again.generator, "regress")

    def test_a_non_empty_directory_is_refused_without_overwrite(self) -> None:
        directory = self.root / "regress"
        write_family(self.manifest(), directory=directory)
        with self.assertRaises(SweepError) as raised:
            write_family(self.manifest(), directory=directory)
        self.assertIn("--overwrite", str(raised.exception))
        write_family(self.manifest(), directory=directory, overwrite=True)

    def test_a_manifest_naming_an_unregistered_class_fails_to_read(self) -> None:
        directory = self.root / "regress"
        write_family(self.manifest(), directory=directory)
        payload = json.loads((directory / "sweep.json").read_text(encoding="utf-8"))
        payload["variants"][1]["class"] = "Z"
        (directory / "sweep.json").write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(SweepError) as raised:
            read_manifest(directory)
        self.assertIn("not a generator class", str(raised.exception))

    def test_two_classes_that_spell_one_file_pay_for_one_build(self) -> None:
        manifest = hoist_family(
            self.path, line=8, classes=("H", "O"), carriers=("lead",)
        )
        placed = write_family(manifest, directory=self.root / "hoist")
        texts = [item.text for item in placed.variants]
        self.assertEqual(len(texts), len(set(texts)))
        self.assertTrue(
            any("byte-identical" in item["reason"] for item in placed.dropped)
        )


class IngestTests(SourceCase):
    def build(self) -> tuple[Path, Path, Path]:
        directory = self.root / "regress"
        write_family(
            removal_family(
                self.path,
                constructs=(parse_construct("10=deadread"), parse_construct("11=copy")),
            ),
            directory=directory,
        )
        objects = self.root / "o"
        objects.mkdir()
        (objects / "work.N.control.objdump").write_text(SHIFTED_DUMP, encoding="utf-8")
        (objects / "work.N.L10.objdump").write_text(EXACT_DUMP, encoding="utf-8")
        (objects / "work.N.L11.objdump").write_text(SHIFTED_DUMP, encoding="utf-8")
        target = self.root / "target.objdump"
        target.write_text(TARGET_DUMP, encoding="utf-8")
        return directory, objects, target

    def ingest(self):
        directory, objects, target = self.build()
        return ingest_sweep(
            read_manifest(directory),
            objects=objects,
            target=target,
            suffix=".objdump",
            dumps=True,
            target_dumps=True,
        )

    def test_a_wrong_instruction_count_is_a_column_not_a_rejection(self) -> None:
        """Eleven stages abandoned candidates that were one row away."""

        result = self.ingest()
        control = result.control
        assert control is not None
        self.assertEqual(control.rows_away, 1)
        self.assertEqual(control.inserted, 1)
        assert control.screen is not None
        self.assertEqual(control.screen.instructions, 6)

    def test_the_price_table_names_what_each_construct_costs(self) -> None:
        result = self.ingest()
        prices = {
            item.key.site: result.price(item)
            for item in result.scored
            if item.key.site != "control"
        }
        self.assertEqual(prices["L10"], 1)
        self.assertEqual(prices["L11"], 0)
        report = "\n".join(ingest_lines(result))
        self.assertIn("COSTS 1 row(s): removing it improves the base", report)
        self.assertIn("free: removing it changes nothing measurable", report)

    def test_an_unbuilt_variant_is_a_row_naming_the_path(self) -> None:
        result = self.ingest()
        missing = result.missing
        self.assertEqual([item.key.site for item in missing], ["L10+L11"])
        self.assertIn("work.N.L10-L11.objdump", missing[0].missing or "")
        self.assertIn("unbuilt (1)", "\n".join(ingest_lines(result)))

    def test_coverage_falls_by_whatever_failed_to_build(self) -> None:
        result = self.ingest()
        payload = result.as_dict()
        self.assertEqual(payload["coverage"]["covered"], 3)
        self.assertIn("coverage:", "\n".join(ingest_lines(result)))

    def test_an_unbuilt_point_is_unvisited_and_never_an_exclusion(self) -> None:
        """An unbuilt variant must not buy back the exhaustiveness claim.

        `excluded` means "declined for a stated reason" -- a conflict rule, a
        failed edit -- and it counts toward `exhaustive`. Crediting variants
        that simply did not build restored exhaustiveness arithmetically, so
        an ingest that scored nothing still printed `swept-exhaustively` and
        `a negative result here is a proof about this space`.
        """

        result = self.ingest()
        payload = result.as_dict()
        self.assertEqual(len(result.missing), 1)
        self.assertEqual(payload["coverage"]["excluded"], 0)
        self.assertEqual(payload["coverage"]["unvisited"], 1)
        sentence = "\n".join(ingest_lines(result))
        self.assertIn("sampled", sentence)
        self.assertIn("never visited", sentence)
        self.assertNotIn("is a proof about this space", sentence)

    def test_the_best_variant_ranks_first(self) -> None:
        result = self.ingest()
        self.assertEqual(result.ranked[0].key.site, "L10")
        self.assertEqual(result.ranked[0].rows_away, 0)

    def test_an_objects_path_that_is_not_a_directory_says_what_it_is_for(self) -> None:
        directory, _objects, target = self.build()
        with self.assertRaises(SweepError) as raised:
            ingest_sweep(
                read_manifest(directory),
                objects=self.root / "nowhere",
                target=target,
                dumps=True,
                target_dumps=True,
            )
        self.assertIn("compile-one wrapper", str(raised.exception))


class SweepCliTests(unittest.TestCase):
    def test_the_group_lists_its_operations_rather_than_erroring(self) -> None:
        status, stdout, stderr = run_cli(["sweep"])
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("sweep regress", stdout)
        self.assertIn("sweep ingest", stdout)

    def test_the_probe_group_also_lists_rather_than_erroring(self) -> None:
        status, stdout, _ = run_cli(["probe"])
        self.assertEqual(status, 0)
        self.assertIn("probe deadread", stdout)

    def test_carriers_reports_the_pool_as_json(self) -> None:
        status, stdout, stderr = run_cli(
            ["sweep", "carriers", str(FIXTURE), "--at", "16", "--json"]
        )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        payload = json.loads(stdout)
        self.assertEqual(payload["schema"], "decomp-workbench-carrier-pool-v1")
        self.assertEqual(payload["pool_size"], 2)

    def test_a_generator_writes_a_manifest_and_names_the_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "commute"
            status, stdout, stderr = run_cli(
                ["sweep", "commute", str(FIXTURE), "--write", str(out)]
            )
            self.assertEqual(status, 0, stderr)
            self.assertTrue((out / "sweep.json").is_file())
        self.assertIn("sweep ingest", stdout)
        self.assertIn("coverage:", stdout)

    def test_a_bad_construct_spec_explains_the_spelling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status, _stdout, stderr = run_cli(
                [
                    "sweep",
                    "regress",
                    str(FIXTURE),
                    "--construct",
                    "the deadread",
                    "--write",
                    str(Path(temporary) / "out"),
                ]
            )
        self.assertEqual(status, 2)
        self.assertIn("LO..HI[=label]", stderr)

    def test_the_grouped_spelling_is_an_exact_alias(self) -> None:
        grouped = run_cli(["sweep", "carriers", str(FIXTURE), "--at", "16", "--json"])
        flat = run_cli(["sweep-carriers", str(FIXTURE), "--at", "16", "--json"])
        self.assertEqual(grouped, flat)


class CoverageContractTests(unittest.TestCase):
    def test_a_sampled_family_never_claims_a_proof(self) -> None:
        coverage = SweepCoverage(basis="carriers", space=10, covered=3)
        self.assertEqual(coverage.vocabulary, "sampled")
        self.assertIn("not a proof", coverage.sentence())


if __name__ == "__main__":
    unittest.main()
