"""End-to-end CLI tests for `reloc-surface` and `linked-compare`.

Both commands are file-in, report-out, so the tests write real files into a
temporary directory and run the parser the shipped entry point runs.
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from test_reloc_surface import (
    TU_OFFSET,
    candidate_object,
    module_document,
    shipped_image,
)

from decomp_workbench.cli import main
from decomp_workbench.linked_compare import LINKED_COMPARE_SCHEMA
from decomp_workbench.reloc_surface import MODULE_MAP_SCHEMA, SURFACE_SCHEMA


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class RelocSurfaceCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.object = root / "tu.c.o"
        self.object.write_bytes(candidate_object())
        self.image = root / "target.bin"
        self.image.write_bytes(shipped_image())
        self.map = root / "module.json"
        self.map.write_text(json.dumps(module_document()), encoding="utf-8")
        self.root = root

    def arguments(self, *extra: str) -> list[str]:
        return [
            "reloc-surface",
            str(self.object),
            "--module-map",
            str(self.map),
            "--image",
            str(self.image),
            *extra,
        ]

    def test_the_block_is_printed_and_is_a_linker_script(self) -> None:
        status, output, _ = run_cli(self.arguments())
        self.assertEqual(status, 0)
        self.assertIn("callee = 0xF000048C;", output)
        self.assertIn("gBase = 0x00018010;", output)

    def test_the_map_is_the_documented_schema(self) -> None:
        self.assertEqual(
            json.loads(self.map.read_text(encoding="utf-8"))["schema"],
            MODULE_MAP_SCHEMA,
        )

    def test_json_carries_the_schema_values_and_conflicts(self) -> None:
        status, output, _ = run_cli(self.arguments("--json"))
        self.assertEqual(status, 0)
        payload = json.loads(output)
        self.assertEqual(payload["schema"], SURFACE_SCHEMA)
        self.assertEqual(
            {item["name"]: item["value"] for item in payload["values"]},
            {"callee": 0xF000048C, "gBase": 0x18010},
        )
        self.assertEqual(payload["conflicts"], [])
        self.assertNotIn("sites", payload)

    def test_sites_are_reported_only_when_asked_for(self) -> None:
        _status, output, _ = run_cli(self.arguments("--json", "--sites"))
        payload = json.loads(output)
        self.assertEqual(len(payload["sites"]), 3)

    def test_out_writes_the_block_a_link_can_include(self) -> None:
        destination = self.root / "generated.ld"
        status, _output, _ = run_cli(self.arguments("--out", str(destination)))
        self.assertEqual(status, 0)
        self.assertIn("callee = 0xF000048C;", destination.read_text(encoding="utf-8"))

    def test_an_audit_that_agrees_exits_zero_and_says_so(self) -> None:
        tracked = self.root / "tracked.ld"
        tracked.write_text("callee = 0xF000048C;\n", encoding="utf-8")
        status, output, _ = run_cli(self.arguments("--audit", str(tracked)))
        self.assertEqual(status, 0)
        self.assertIn("agree           1/1", output)
        self.assertIn("verdict         agrees", output)

    def test_an_audit_that_disagrees_names_both_values_and_exits_one(self) -> None:
        tracked = self.root / "tracked.ld"
        tracked.write_text("callee = 0x1;\n", encoding="utf-8")
        status, output, _ = run_cli(self.arguments("--audit", str(tracked)))
        self.assertEqual(status, 1)
        self.assertIn("MISMATCH        callee", output)
        self.assertIn("0xf000048c", output)

    def test_a_missing_image_is_a_usage_error_not_a_traceback(self) -> None:
        status, _output, error = run_cli(
            [
                "reloc-surface",
                str(self.object),
                "--module-map",
                str(self.map),
                "--image",
                str(self.root / "absent.bin"),
            ]
        )
        self.assertEqual(status, 2)
        self.assertTrue(error.startswith("error: "))

    def test_a_malformed_module_map_names_the_problem(self) -> None:
        bad = self.root / "bad.json"
        bad.write_text(json.dumps({"module": {"image_start": 0}}), encoding="utf-8")
        status, _output, error = run_cli(
            [
                "reloc-surface",
                str(self.object),
                "--module-map",
                str(bad),
                "--image",
                str(self.image),
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("image_end", error)

    def test_a_refused_symbol_makes_the_command_exit_one(self) -> None:
        self.map.write_text(
            json.dumps(
                module_document(
                    relocation_sites=[{"offset": TU_OFFSET + 8, "type": "R_MIPS_HI16"}]
                )
            ),
            encoding="utf-8",
        )
        status, output, _ = run_cli(self.arguments())
        self.assertEqual(status, 1)
        self.assertIn("UNRESOLVED gBase: no-corroborated-site", output)


class LinkedCompareCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.root = root
        self.target = root / "target.z64"
        self.target.write_bytes(bytes(range(256)) * 16)
        self.built = root / "built.z64"

    def test_an_identical_image_is_exact_and_exits_zero(self) -> None:
        self.built.write_bytes(self.target.read_bytes())
        status, output, _ = run_cli(
            [
                "linked-compare",
                str(self.built),
                str(self.target),
                "--range",
                "draw:0x100:0x140",
            ]
        )
        self.assertEqual(status, 0)
        self.assertIn("verdict         exact", output)

    def test_collateral_outside_the_range_still_exits_zero(self) -> None:
        image = bytearray(self.target.read_bytes())
        image[0x800] ^= 0xFF
        self.built.write_bytes(bytes(image))
        status, output, _ = run_cli(
            [
                "linked-compare",
                str(self.built),
                str(self.target),
                "--range",
                "draw:0x100:0x140",
                "--json",
            ]
        )
        self.assertEqual(status, 0)
        payload = json.loads(output)
        self.assertEqual(payload["schema"], LINKED_COMPARE_SCHEMA)
        self.assertEqual(payload["ranges"][0]["class"], "text-exact")
        self.assertEqual(payload["ranges"][0]["out_of_range_bytes"], 1)

    def test_a_residual_in_range_exits_one_with_a_word_count(self) -> None:
        image = bytearray(self.target.read_bytes())
        image[0x104] ^= 0xFF
        self.built.write_bytes(bytes(image))
        status, output, _ = run_cli(
            [
                "linked-compare",
                str(self.built),
                str(self.target),
                "--range",
                "draw:0x100:0x140",
            ]
        )
        self.assertEqual(status, 1)
        self.assertIn("text-differs", output)
        self.assertIn("0x104", output)

    def test_a_ranges_file_classifies_a_whole_trials_worth(self) -> None:
        image = bytearray(self.target.read_bytes())
        image[0x104] ^= 0xFF
        self.built.write_bytes(bytes(image))
        ranges = self.root / "ranges.json"
        ranges.write_text(
            json.dumps(
                {
                    "ranges": [
                        {"name": "draw", "start": "0x100", "size": "0x40"},
                        {"name": "step", "start": "0x200", "size": "0x40"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        status, output, _ = run_cli(
            [
                "linked-compare",
                str(self.built),
                str(self.target),
                "--ranges",
                str(ranges),
                "--json",
            ]
        )
        self.assertEqual(status, 1)
        payload = json.loads(output)
        self.assertEqual(
            [item["class"] for item in payload["ranges"]],
            ["text-differs", "text-exact"],
        )

    def test_a_bad_range_argument_is_a_usage_error(self) -> None:
        self.built.write_bytes(self.target.read_bytes())
        status, _output, error = run_cli(
            [
                "linked-compare",
                str(self.built),
                str(self.target),
                "--range",
                "draw:0x140:0x100",
            ]
        )
        self.assertEqual(status, 2)
        self.assertIn("not past start", error)


if __name__ == "__main__":
    unittest.main()
