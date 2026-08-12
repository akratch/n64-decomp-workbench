"""Conservative project discovery and configured command dispatch."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from decomp_workbench.cli import main
from decomp_workbench.project_config import (
    CONFIG_NAME,
    discover_project,
    find_project_config,
    load_project_config,
    render_project_config,
    with_build_overrides,
    with_object_overrides,
    write_project_config,
)

DUMP = """
00000000 <demo>:
   0: 03e00008  jr $ra
   4: 00000000  nop
"""


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


class ProjectConfigTests(unittest.TestCase):
    def test_init_previews_before_explicit_write_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
            status, stdout, stderr = run_cli(
                [
                    "project",
                    "init",
                    str(root),
                    "--target",
                    "build/target.o",
                    "--candidate",
                    "build/candidate.o",
                    "--symbol",
                    "demo",
                ]
            )
            self.assertEqual((status, stderr), (0, ""))
            self.assertIn("Preview only", stdout)
            self.assertFalse((root / CONFIG_NAME).exists())

            status, _stdout, stderr = run_cli(
                [
                    "project",
                    "init",
                    str(root),
                    "--target",
                    "build/target.o",
                    "--candidate",
                    "build/candidate.o",
                    "--symbol",
                    "demo",
                    "--compile-command",
                    "./compile-one {source} {output}",
                    "--env",
                    "FIXED=1",
                    "--frontend",
                    "IRIX 4.1 accom",
                    "--write",
                ]
            )
            self.assertEqual((status, stderr), (0, ""))
            config = load_project_config(root / CONFIG_NAME)
            self.assertEqual(config.symbol, "demo")
            self.assertEqual(
                config.build_command, ("./compile-one", "{source}", "{output}")
            )
            self.assertEqual(config.environment, ("FIXED=1",))
            self.assertEqual(config.frontend, "IRIX 4.1 accom")
            self.assertEqual(config.target, (root / "build/target.o").resolve())

            status, _stdout, stderr = run_cli(["project", "init", str(root), "--write"])
            self.assertEqual(status, 2)
            self.assertIn("File exists", stderr)

    def test_objdiff_and_splat_are_detected_without_guessing_an_object_pair(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "objdiff.json").write_text('{"units": []}\n', encoding="utf-8")
            (root / "game.us.yaml").write_text(
                "options:\n  basename: game\nsegments:\n  - name: header\n",
                encoding="utf-8",
            )
            discovery = discover_project(root)
        self.assertEqual(
            {item["kind"] for item in discovery.detected}, {"objdiff", "splat"}
        )
        self.assertNotIn("target", discovery.proposed["object"])
        self.assertTrue(any("not guessed" in warning for warning in discovery.warnings))

    def test_config_searches_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nested = root / "src" / "overlay"
            nested.mkdir(parents=True)
            discovery = with_object_overrides(
                discover_project(root),
                target="target.o",
                candidate="candidate.o",
                symbol=None,
                objdump=None,
            )
            write_project_config(discovery)
            self.assertEqual(
                find_project_config(nested), (root / CONFIG_NAME).resolve()
            )

    def test_unknown_keys_fail_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / CONFIG_NAME
            config.write_text("[object]\ntypo = 'candidate.o'\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown .* keys"):
                load_project_config(config)

    def test_relative_objdump_path_resolves_from_config_not_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            discovery = with_object_overrides(
                discover_project(root),
                target="target.o",
                candidate="candidate.o",
                symbol="demo",
                objdump="tools/mips-objdump",
            )
            write_project_config(discovery)
            loaded = load_project_config(root / CONFIG_NAME)
        self.assertEqual(loaded.objdump, str((root / "tools/mips-objdump").resolve()))

    def test_project_compare_dispatches_auditable_configured_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.objdump"
            candidate = root / "candidate.objdump"
            target.write_text(DUMP, encoding="utf-8")
            candidate.write_text(DUMP, encoding="utf-8")
            discovery = with_object_overrides(
                discover_project(root),
                target=target.name,
                candidate=candidate.name,
                symbol="demo",
                objdump=None,
            )
            # Use the dump command in this fixture by exercising argv rendering;
            # configured object execution itself is covered with print-command.
            write_project_config(discovery)
            status, stdout, stderr = run_cli(
                [
                    "project",
                    "compare",
                    "--config",
                    str(root / CONFIG_NAME),
                    "--print-command",
                    "--",
                    "--show-diff",
                ]
            )
        self.assertEqual((status, stderr), (0, ""))
        self.assertIn("decomp-workbench compare", stdout)
        self.assertIn(str(target), stdout)
        self.assertIn("--function demo", stdout)
        self.assertIn("--show-diff", stdout)
        self.assertNotIn(" -- --show-diff", stdout)

    def test_configured_dump_mode_runs_without_objdump(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.objdump"
            candidate = root / "candidate.objdump"
            target.write_text(DUMP, encoding="utf-8")
            candidate.write_text(DUMP, encoding="utf-8")
            discovery = with_object_overrides(
                discover_project(root),
                target=target.name,
                candidate=candidate.name,
                symbol="demo",
                objdump=None,
                input_mode="dumps",
            )
            write_project_config(discovery)
            status, stdout, stderr = run_cli(
                [
                    "project",
                    "compare",
                    "--config",
                    str(root / CONFIG_NAME),
                    "--",
                    "--json",
                ]
            )
        payload = json.loads(stdout)
        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(payload["schema"], "decomp-workbench-comparison-v1")
        self.assertTrue(payload["exact"])

    def test_dump_mode_rejects_an_inapplicable_objdump(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            discovery = with_object_overrides(
                discover_project(root),
                target="target.objdump",
                candidate="candidate.objdump",
                symbol="demo",
                objdump="mips-objdump",
                input_mode="dumps",
            )
            write_project_config(discovery)
            with self.assertRaisesRegex(ValueError, "does not apply"):
                load_project_config(root / CONFIG_NAME)

    def test_rendered_config_round_trips_non_ascii_and_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            discovery = with_object_overrides(
                discover_project(temporary),
                target='build/a "target".o',
                candidate="build/candidaté.o",
                symbol="demo",
                objdump=None,
            )
            rendered = render_project_config(discovery)
            (Path(temporary) / CONFIG_NAME).write_text(rendered, encoding="utf-8")
            loaded = load_project_config(Path(temporary) / CONFIG_NAME)
        target = loaded.target
        candidate = loaded.candidate
        self.assertIsNotNone(target)
        self.assertIsNotNone(candidate)
        assert target is not None and candidate is not None
        self.assertIn('a "target".o', os.fspath(target))
        self.assertIn("candidaté.o", os.fspath(candidate))

    def test_project_init_json_has_schema_and_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status, stdout, stderr = run_cli(["project", "init", temporary, "--json"])
        payload = json.loads(stdout)
        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(payload["schema"], "decomp-workbench-project-v1")
        self.assertIsNone(payload["written"])

    def test_configured_campaign_expands_sealed_environment_and_irix_lineage(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "candidate.c"
            source.write_text("int demo;\n", encoding="utf-8")
            discovery = with_object_overrides(
                discover_project(root),
                target="target.o",
                candidate=None,
                symbol="demo",
                objdump="mips-objdump",
            )
            discovery = with_build_overrides(
                discovery,
                command=["./compile-one", "{source}", "{output}"],
                cwd=".",
                environment=["FIXED=1"],
                inherit_env=["PATH"],
                compiler_id="ido-5.3",
                frontend="IRIX 4.1 accom",
                language="c89",
                driver="cc-irix4",
                backend="IDO 5.3 uopt/ugen/as1",
            )
            write_project_config(discovery)
            status, stdout, stderr = run_cli(
                [
                    "project",
                    "campaign",
                    str(source),
                    "--config",
                    str(root / CONFIG_NAME),
                    "--print-command",
                ]
            )
        self.assertEqual((status, stderr), (0, ""))
        self.assertIn("--env FIXED=1", stdout)
        self.assertIn("--inherit-env PATH", stdout)
        self.assertIn("--frontend 'IRIX 4.1 accom'", stdout)
        self.assertIn("--backend 'IDO 5.3 uopt/ugen/as1'", stdout)
        self.assertIn("--retain-sources leaders", stdout)
        self.assertIn(f"--state-dir {(root / '.decomp-workbench').resolve()}", stdout)
        self.assertNotIn("campaigns/campaigns", stdout)

    def test_build_options_without_a_compile_command_fail_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status, _stdout, stderr = run_cli(
                ["project", "init", temporary, "--env", "FIXED=1"]
            )

        self.assertEqual(status, 2)
        self.assertIn("require --compile-command", stderr)

    def test_campaign_requires_a_real_compile_template(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            discovery = with_object_overrides(
                discover_project(root),
                target="target.o",
                candidate=None,
                symbol="demo",
                objdump=None,
            )
            discovery = with_build_overrides(
                discovery,
                command=["make"],
                cwd=None,
                environment=[],
                inherit_env=[],
                compiler_id=None,
                frontend=None,
                language=None,
                driver=None,
                backend=None,
            )
            write_project_config(discovery)
            config = load_project_config(root / CONFIG_NAME)
            with self.assertRaisesRegex(ValueError, r"\{source\}"):
                config.campaign_argv(["candidate.c"])


if __name__ == "__main__":
    unittest.main()
