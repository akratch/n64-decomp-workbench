"""Tests for the permuter sweep driver.

Nothing here needs decomp-permuter, a compiler, or a project build: the
parsers are pure, and the orchestration takes its process runner as an
argument, so a fake stands in for `make -n`, `import.py` and `permuter.py`.
"""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import Any

from decomp_workbench.cli import main
from decomp_workbench.permute import (
    QueueItem,
    SweepResult,
    best_output,
    completed_functions,
    earlier_results,
    join_continuations,
    load_queue,
    load_ranking,
    object_target,
    order_queue,
    parse_base_score,
    parse_dry_run,
    permuter_argv,
    recipe_report,
    recover_recipe,
    render_settings,
    render_table,
    retarget_labels,
    retarget_objcopy,
    should_extend,
    sweep_payload,
    wait_for_headroom,
)
from decomp_workbench.permute_sweep import (
    PermuterError,
    doctor,
    prepare_scratch,
    render_doctor,
    resolve_plan,
    run_sweep,
    search_function,
)
from decomp_workbench.project_config import PermuterOptions, load_project_config
from decomp_workbench.ranking import stamp_ranking

#: A dry run whose compile line is split by a backslash continuation, with
#: the codegen flags on the second line -- the line that does not name the
#: compiler. This is the shape that silently defeated a naive parser.
CONTINUED_DRY_RUN = """\
echo "CC      src/game/track.c"
tools/ido/cc -c -non_shared -G 0 -I include -DVERSION_us \\
        -O2 -mips2 -Wab,-r4300_mul -32 -o build/src/game/track.c.o \\
        src/game/track.c
tools/binutils/objcopy --redefine-sym A=B build/src/game/track.c.o && \\
        tools/trim_elf_section.py build/src/game/track.c.o && \\
        tools/binutils/objcopy --weaken-symbol C build/src/game/track.c.o
"""

OBJECT = "build/src/game/track.c.o"


class RecipeParsingTests(unittest.TestCase):
    def test_continuation_lines_are_joined_before_parsing(self) -> None:
        joined = join_continuations("a \\\nb")
        self.assertEqual(joined, "a  b")

    def test_flags_come_off_the_continued_compile_line(self) -> None:
        recipe = parse_dry_run(CONTINUED_DRY_RUN, obj=OBJECT, compiler="tools/ido/cc")
        self.assertEqual(recipe.flags, ("-O2", "-mips2", "-Wab,-r4300_mul", "-32"))
        self.assertTrue(recipe.from_dry_run)
        self.assertEqual(recipe.warnings, ())

    def test_flags_are_recovered_without_a_compiler_marker(self) -> None:
        recipe = parse_dry_run(CONTINUED_DRY_RUN, obj=OBJECT)
        self.assertEqual(recipe.flags, ("-O2", "-mips2", "-Wab,-r4300_mul", "-32"))

    def test_the_objcopy_chain_is_split_and_python_passes_are_skipped(self) -> None:
        recipe = parse_dry_run(CONTINUED_DRY_RUN, obj=OBJECT, compiler="tools/ido/cc")
        self.assertEqual(
            recipe.objcopy_steps,
            (
                f"tools/binutils/objcopy --redefine-sym A=B {OBJECT}",
                f"tools/binutils/objcopy --weaken-symbol C {OBJECT}",
            ),
        )
        self.assertEqual(
            recipe.skipped_postprocess,
            (f"tools/trim_elf_section.py {OBJECT}",),
        )

    def test_an_up_to_date_object_prints_nothing_and_warns_loudly(self) -> None:
        """`make -n` says nothing for an object that is already built.

        Parsed naively that reads as "no flags", and the scratch then keeps
        decomp-permuter's `-mips1` default: the search explores an ISA the
        real build never emits and finds nothing, which reads as a hard
        function rather than as a misconfiguration.
        """

        recipe = parse_dry_run("", obj=OBJECT, compiler="tools/ido/cc")
        self.assertEqual(recipe.flags, ())
        self.assertFalse(recipe.from_dry_run)
        self.assertEqual(len(recipe.warnings), 1)
        self.assertIn("wrong ISA", recipe.warnings[0])

    def test_a_line_without_an_isa_flag_is_not_a_compile_line(self) -> None:
        recipe = parse_dry_run(f"rm -f {OBJECT}", obj=OBJECT)
        self.assertEqual(recipe.flags, ())

    def test_lines_about_other_objects_are_ignored(self) -> None:
        text = "tools/ido/cc -O2 -mips2 -32 -o build/other.c.o other.c\n"
        recipe = parse_dry_run(text, obj=OBJECT)
        self.assertEqual(recipe.flags, ())

    def test_object_targets_render_from_the_source_path(self) -> None:
        self.assertEqual(
            object_target("build/{source}.o", "src/game/track.c"),
            "build/src/game/track.c.o",
        )
        self.assertEqual(
            object_target("obj/{stem}.o", "src/game/track.c"), "obj/track.o"
        )

    def test_the_chain_is_retargeted_at_the_scratch_object(self) -> None:
        steps = retarget_objcopy((f"objcopy --redefine-sym A=B {OBJECT}",), OBJECT)
        self.assertEqual(steps, ('objcopy --redefine-sym A=B "$OUTPUT"',))

    def test_the_recipe_report_names_the_fallback_as_a_fallback(self) -> None:
        recipe = parse_dry_run("", obj=OBJECT)
        report = recipe_report(recipe, ())
        self.assertIn("NOT the real build", report)
        self.assertIn("warning:", report)


class RecipeRecoveryTests(unittest.TestCase):
    def test_the_source_is_touched_before_the_dry_run(self) -> None:
        calls: list[list[str]] = []

        def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, CONTINUED_DRY_RUN, "")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "src" / "game" / "track.c"
            source.parent.mkdir(parents=True)
            source.write_text("int f(void) { return 0; }\n", encoding="utf-8")
            before = source.stat().st_mtime_ns
            recipe = recover_recipe(
                root,
                QueueItem(function="f", source="src/game/track.c"),
                make="gmake",
                compiler="tools/ido/cc",
                runner=runner,
            )
            after = source.stat().st_mtime_ns
        self.assertEqual(calls, [["gmake", "-n", OBJECT]])
        self.assertGreaterEqual(after, before)
        self.assertEqual(recipe.flags[:2], ("-O2", "-mips2"))

    def test_a_failed_dry_run_falls_back_and_says_so(self) -> None:
        def runner(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            raise OSError("gmake: not found")

        with tempfile.TemporaryDirectory() as temporary:
            recipe = recover_recipe(
                Path(temporary),
                QueueItem(function="f", source="src/game/track.c"),
                fallback_flags=("-O2", "-mips2", "-32"),
                runner=runner,
            )
        self.assertEqual(recipe.flags, ("-O2", "-mips2", "-32"))
        self.assertFalse(recipe.from_dry_run)
        self.assertIn("could not run", recipe.warnings[0])


class QueueTests(unittest.TestCase):
    def test_json_and_line_queues_read_the_same_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            as_json = root / "queue.json"
            as_json.write_text(
                json.dumps(
                    {
                        "functions": [
                            {
                                "function": "f",
                                "source": "src/a.c",
                                "asm": "asm/f.s",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            as_text = root / "queue.txt"
            as_text.write_text("# comment\nf src/a.c asm/f.s\n\n", encoding="utf-8")
            self.assertEqual(load_queue(as_json), load_queue(as_text))

    def test_an_unknown_queue_key_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "queue.json"
            path.write_text(
                json.dumps([{"function": "f", "source": "a.c", "oops": 1}]),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_queue(path)

    def test_closest_first_ordering_puts_unranked_functions_last(self) -> None:
        """An unranked function is unmeasured, not close.

        A sweep that runs the unmeasured ones first reports "queue
        exhausted" having never reached the near-matches a ranking already
        identified -- the exact false verdict this ordering exists to stop.
        """

        items = [
            QueueItem(function="far", source="a.c"),
            QueueItem(function="unranked_b", source="b.c"),
            QueueItem(function="near", source="c.c"),
            QueueItem(function="unranked_a", source="d.c"),
        ]
        ranking = {"far": (40, 200), "near": (2, 120)}
        self.assertEqual(
            [item.function for item in order_queue(items, ranking)],
            ["near", "far", "unranked_a", "unranked_b"],
        )

    def test_a_ranking_reads_differing_words_and_ignores_junk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ranking.json"
            path.write_text(
                json.dumps(
                    {
                        "functions": [
                            {"name": "a", "differing_words": 3, "size_bytes": 10},
                            {"name": "b", "differing_words": "many"},
                            {"nope": True},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(load_ranking(path), {"a": (3, 10)})
        self.assertEqual(load_ranking(None), {})


class RunPolicyTests(unittest.TestCase):
    def test_stack_diffs_and_nice_are_forced_on(self) -> None:
        argv = permuter_argv(
            python="python3",
            permuter=Path("/p/permuter.py"),
            scratch=Path("/s"),
            threads=3,
        )
        self.assertEqual(argv[:3], ["nice", "-n", "15"])
        self.assertIn("--stack-diffs", argv)
        self.assertIn("--stop-on-zero", argv)
        self.assertEqual(argv[-1], "/s")

    def test_stack_diffs_is_not_repeated_when_forwarded(self) -> None:
        argv = permuter_argv(
            python="python3",
            permuter=Path("/p/permuter.py"),
            scratch=Path("/s"),
            threads=1,
            extra=["--stack-diffs"],
            nice=None,
        )
        self.assertEqual(argv.count("--stack-diffs"), 1)
        self.assertEqual(argv[0], "python3")

    def test_a_still_descending_run_is_extended_and_a_plateau_is_not(self) -> None:
        window = 20
        common = {"minutes": window, "best_score": 5, "extend_minutes": 10}
        # Hit the cap with the best result inside the final third: descending.
        self.assertTrue(should_extend(elapsed=window * 60, best_age=100.0, **common))
        # Hit the cap, but the best result landed early and then sat.
        self.assertFalse(should_extend(elapsed=window * 60, best_age=900.0, **common))
        # Stopped early (score 0, or the search ended): nothing to extend.
        self.assertFalse(should_extend(elapsed=60.0, best_age=10.0, **common))
        self.assertFalse(
            should_extend(
                elapsed=window * 60,
                minutes=window,
                best_score=0,
                best_age=10.0,
                extend_minutes=10,
            )
        )
        self.assertFalse(
            should_extend(
                elapsed=window * 60,
                minutes=window,
                best_score=5,
                best_age=10.0,
                extend_minutes=0,
            )
        )

    def test_the_load_gate_waits_and_then_proceeds(self) -> None:
        loads = iter([12.0, 11.0, 3.0])
        slept: list[float] = []
        messages: list[str] = []
        waits = wait_for_headroom(
            9.0,
            label="before permuting f",
            load=lambda: next(loads),
            sleep=slept.append,
            interval=1.0,
            report=messages.append,
        )
        self.assertEqual(waits, 2)
        self.assertEqual(slept, [1.0, 1.0])
        self.assertEqual(len(messages), 1)
        self.assertIn("before permuting f", messages[0])

    def test_a_disabled_load_gate_never_reads_the_load(self) -> None:
        def explode() -> float:
            raise AssertionError("the load must not be read when the gate is off")

        self.assertEqual(wait_for_headroom(0.0, load=explode), 0)

    def test_the_lowest_scoring_output_wins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scratch = Path(temporary)
            for name in ("output-12-aaa", "output-3-bbb", "output-nope"):
                (scratch / name).mkdir()
            directory, score = best_output(scratch)
            self.assertEqual(score, 3)
            assert directory is not None
            self.assertEqual(directory.name, "output-3-bbb")
            self.assertEqual(best_output(scratch / "missing"), (None, None))

    def test_the_base_score_is_read_out_of_the_log(self) -> None:
        self.assertEqual(parse_base_score("...\nbase score = 214\n"), 214)
        self.assertIsNone(parse_base_score("permuter failed"))


class SettingsTests(unittest.TestCase):
    def test_settings_carry_the_real_flags_and_preserved_macros(self) -> None:
        text = render_settings(
            compiler_command="cc -c -I include -DVERSION_us",
            assembler_command="as -march=vr4300",
            flags=("-O2", "-mips2"),
            preserve_macros=("g[DS]P.*=void",),
            decompme_compiler="ido5.3",
        )
        self.assertIn("cc -c -I include -DVERSION_us -O2 -mips2", text)
        self.assertIn('assembler_command = "as -march=vr4300"', text)
        self.assertIn("[preserve_macros]", text)
        self.assertIn('"g[DS]P.*" = "void"', text)
        self.assertIn('"cc" = "ido5.3"', text)

    def test_a_target_label_rename_touches_only_that_label(self) -> None:
        text = "glabel func_overlay_1_80001234\n/* code */\n.word func_other\n"
        renamed = retarget_labels(
            text, old="func_overlay_1_80001234", new="overlay1GetEntry"
        )
        self.assertIn("glabel overlay1GetEntry", renamed)
        self.assertIn(".word func_other", renamed)
        self.assertEqual(retarget_labels(text, old="x", new="x"), text)


class SummaryTests(unittest.TestCase):
    def test_resume_reads_the_functions_a_previous_sweep_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = Path(temporary) / "summary.json"
            summary.write_text(
                json.dumps(
                    sweep_payload(
                        [
                            SweepResult(
                                function="done", source="a.c", ok=True, best_score=4
                            )
                        ],
                        final=True,
                    )
                ),
                encoding="utf-8",
            )
            self.assertEqual(completed_functions(summary), {"done"})
            carried = earlier_results(summary)
            self.assertEqual([result.function for result in carried], ["done"])
            self.assertEqual(carried[0].best_score, 4)
            self.assertEqual(completed_functions(summary.parent / "nope.json"), set())

    def test_the_table_reports_a_fallback_search_as_a_fallback(self) -> None:
        rows = render_table(
            [
                SweepResult(function="a", source="a.c", ok=True, flags_recovered=True),
                SweepResult(function="b", source="b.c", ok=True, flags_recovered=False),
            ]
        )
        self.assertIn("real", rows[1])
        self.assertIn("FALLBACK", rows[2])
        self.assertIn("1 searched with fallback flags", rows[-1])


class FakeProject:
    """A project tree plus a runner that impersonates the three tools."""

    def __init__(self, root: Path, *, dry_run: str = CONTINUED_DRY_RUN) -> None:
        self.root = root
        self.dry_run = dry_run
        self.base_score = 214
        self.outputs: tuple[str, ...] = ("output-9-aaa",)
        self.import_fails = False
        self.commands: list[list[str]] = []
        (root / "src" / "game").mkdir(parents=True)
        (root / "src" / "game" / "track.c").write_text("int f(void);\n", "utf-8")
        (root / "asm").mkdir()
        (root / "asm" / "f.s").write_text("glabel f_asm\njr $ra\n", "utf-8")
        permuter = root / "permuter"
        permuter.mkdir()
        for name in ("import.py", "permuter.py"):
            (permuter / name).write_text("", encoding="utf-8")

    @property
    def options(self) -> PermuterOptions:
        return PermuterOptions(
            make="gmake",
            python="python3",
            permuter_dir=self.root / "permuter",
            compiler_marker="tools/ido/cc",
            compiler_command="tools/ido/cc -c -I include",
            assembler_command="as -march=vr4300",
            output_dir=self.root / "out",
        )

    @property
    def item(self) -> QueueItem:
        return QueueItem(
            function="f",
            source="src/game/track.c",
            asm="asm/f.s",
            asm_symbol="f_asm",
        )

    def run(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(argv))
        if argv[0].endswith("make") and "-n" in argv:
            return subprocess.CompletedProcess(argv, 0, self.dry_run, "")
        if any(part.endswith("import.py") for part in argv):
            if self.import_fails:
                return subprocess.CompletedProcess(argv, 1, "not found in base.c", "")
            scratch = self.root / "nonmatchings" / "f"
            scratch.mkdir(parents=True, exist_ok=True)
            (scratch / "compile.sh").write_text('#!/bin/sh\ncc "$1"\n', "utf-8")
            (scratch / "base.c").write_text("int f(void) { return 0; }\n", "utf-8")
            return subprocess.CompletedProcess(argv, 0, "imported", "")
        if any(part.endswith("permuter.py") for part in argv):
            scratch = Path(argv[-1])
            for name in self.outputs:
                directory = scratch / name
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "source.c").write_text("int f(void) { }\n", "utf-8")
            stream = kwargs.get("stdout")
            if isinstance(stream, io.IOBase):
                stream.write(f"base score = {self.base_score}\n")
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise AssertionError(f"unexpected command: {argv}")


class ScratchPreparationTests(unittest.TestCase):
    def test_the_scratch_replicates_the_real_recipe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            plan = resolve_plan(project.root, project.options)
            out_dir, scratch, recipe, steps = prepare_scratch(
                plan, project.item, runner=project.run
            )
            settings = (out_dir / "permuter_settings.toml").read_text("utf-8")
            compile_sh = (scratch / "compile.sh").read_text("utf-8")
            report = (out_dir / "recipe.txt").read_text("utf-8")
            target = (out_dir / "target.s").read_text("utf-8")
        self.assertTrue(recipe.from_dry_run)
        self.assertIn("-mips2", settings)
        self.assertEqual(len(steps), 2)
        self.assertIn('objcopy --redefine-sym A=B "$OUTPUT"', compile_sh)
        self.assertIn("trim_elf_section.py", report)
        self.assertIn("skipped (not replicable)", report)
        self.assertIn("glabel f", target)
        self.assertNotIn("f_asm", target)

    def test_a_failed_import_is_reported_with_its_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            project.import_fails = True
            plan = resolve_plan(project.root, project.options)
            with self.assertRaises(PermuterError) as raised:
                prepare_scratch(plan, project.item, runner=project.run)
        self.assertIn("import.py failed", str(raised.exception))

    def test_a_missing_compiler_command_refuses_before_running_anything(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            options = PermuterOptions(permuter_dir=project.root / "permuter")
            plan = resolve_plan(project.root, options)
            with self.assertRaises(PermuterError) as raised:
                prepare_scratch(plan, project.item, runner=project.run)
        self.assertIn("compiler_command", str(raised.exception))

    def test_a_missing_permuter_checkout_is_named(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            plan = resolve_plan(project.root, PermuterOptions(compiler_command="cc -c"))
            with self.assertRaises(PermuterError) as raised:
                prepare_scratch(plan, project.item, runner=project.run)
        self.assertIn("permuter_dir", str(raised.exception))


class SearchTests(unittest.TestCase):
    def test_one_function_is_searched_and_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            plan = resolve_plan(project.root, project.options, minutes=1)
            result = search_function(plan, project.item, runner=project.run)
        self.assertTrue(result.ok)
        self.assertIsNone(result.error)
        self.assertEqual(result.base_score, 214)
        self.assertEqual(result.best_score, 9)
        self.assertFalse(result.zero_found)
        self.assertTrue(result.flags_recovered)
        self.assertEqual(result.replicated_objcopy, 2)

    def test_a_zero_score_is_reported_but_never_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            project.outputs = ("output-0-win",)
            plan = resolve_plan(project.root, project.options, minutes=1)
            results = run_sweep(plan, [project.item], runner=project.run)
        self.assertTrue(results[0].zero_found)
        self.assertNotIn("promoted", results[0].as_dict())
        payload = sweep_payload(results, final=True)
        self.assertEqual(payload["totals"]["zero_found"], 1)

    def test_a_preparation_failure_records_the_error_and_keeps_going(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            project.import_fails = True
            plan = resolve_plan(project.root, project.options, minutes=1)
            results = run_sweep(plan, [project.item, project.item], runner=project.run)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.error for result in results))


class DoctorTests(unittest.TestCase):
    def test_a_healthy_function_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            plan = resolve_plan(project.root, project.options)
            report = doctor(plan, project.item, seconds=60, runner=project.run)
        self.assertTrue(report.ok)
        self.assertEqual(report.flags[:2], ("-O2", "-mips2"))
        self.assertEqual(len(report.replicated), 2)
        self.assertEqual(report.base_score, 214)
        self.assertTrue(report.base_compiles)
        self.assertIn("ready", render_doctor(report)[-1])

    def test_a_base_that_already_scores_zero_is_not_scoring_this_function(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            project.base_score = 0
            plan = resolve_plan(project.root, project.options)
            report = doctor(plan, project.item, seconds=60, runner=project.run)
        self.assertFalse(report.ok)
        self.assertIn("not scoring the function under test", report.problems[0])

    def test_unrecovered_flags_are_a_problem_not_a_footnote(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary), dry_run="")
            plan = resolve_plan(project.root, project.options)
            report = doctor(plan, project.item, check_base=False, runner=project.run)
        self.assertFalse(report.ok)
        self.assertIn("codegen flags were not recovered", report.problems[0])
        self.assertIn("NOT READY", render_doctor(report)[-1])


class PermuteCliTests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def write_project(self, root: Path) -> tuple[Path, Path]:
        (root / ".decomp-workbench.toml").write_text(
            "[project]\nname = 'example'\n\n"
            "[permuter]\n"
            "make = 'gmake'\n"
            "permuter_dir = 'permuter'\n"
            "compiler_command = 'tools/ido/cc -c -I include'\n"
            "assembler_command = 'as -march=vr4300'\n"
            "compiler_marker = 'tools/ido/cc'\n"
            "minutes = 7\n"
            "preserve_macros = ['g[DS]P.*=void']\n",
            encoding="utf-8",
        )
        queue = root / "queue.json"
        queue.write_text(
            json.dumps(
                [
                    {"function": "far", "source": "src/game/track.c"},
                    {"function": "near", "source": "src/game/track.c"},
                ]
            ),
            encoding="utf-8",
        )
        ranking = root / "ranking.json"
        ranking.write_text(
            json.dumps(
                {
                    "functions": [
                        {"name": "far", "differing_words": 30},
                        {"name": "near", "differing_words": 1},
                    ]
                }
            ),
            encoding="utf-8",
        )
        return queue, ranking

    def test_dry_run_orders_the_queue_and_starts_no_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, ranking = self.write_project(root)
            status, stdout, stderr = self.run_cli(
                [
                    "permute-sweep",
                    str(queue),
                    "--project",
                    str(root),
                    "--ranking",
                    str(ranking),
                    "--dry-run",
                ]
            )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertLess(stdout.index("near"), stdout.index("far"))
        self.assertIn("7 min cap", stdout)

    def test_the_configured_permuter_section_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_project(root)
            config = load_project_config(root / ".decomp-workbench.toml")
        self.assertEqual(config.permuter.make, "gmake")
        self.assertEqual(config.permuter.minutes, 7)
        self.assertEqual(config.permuter.preserve_macros, ("g[DS]P.*=void",))
        self.assertEqual(config.permuter.permuter_dir, root.resolve() / "permuter")

    def test_a_malformed_preserve_macro_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".decomp-workbench.toml").write_text(
                "[permuter]\npreserve_macros = ['gDPNoOp']\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError) as raised:
                load_project_config(root / ".decomp-workbench.toml")
        self.assertIn("PATTERN=TYPE", str(raised.exception))

    def test_a_missing_function_row_is_a_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, _ranking = self.write_project(root)
            status, _stdout, stderr = self.run_cli(
                [
                    "permute-doctor",
                    "absent",
                    "--project",
                    str(root),
                    "--queue",
                    str(queue),
                ]
            )
        self.assertEqual(status, 2)
        self.assertIn("is not in", stderr)

    def test_a_stale_ranking_is_loud_but_does_not_stop_a_sweep(self) -> None:
        """The ordering is a measurement of a tree that has since moved."""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, ranking = self.write_project(root)
            stamp_ranking(ranking, "a" * 40)
            with unittest.mock.patch(
                "decomp_workbench.permute_cli.git_head", return_value="b" * 40
            ):
                status, stdout, stderr = self.run_cli(
                    [
                        "permute-sweep",
                        str(queue),
                        "--project",
                        str(root),
                        "--ranking",
                        str(ranking),
                        "--dry-run",
                    ]
                )
        self.assertEqual(status, 0)
        self.assertIn("WARNING:", stderr)
        self.assertIn("measurement of a different tree", stderr)
        self.assertIn("near", stdout)

    def test_require_fresh_refuses_a_stale_ranking_before_any_process(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, ranking = self.write_project(root)
            stamp_ranking(ranking, "a" * 40)
            with unittest.mock.patch(
                "decomp_workbench.permute_cli.git_head", return_value="b" * 40
            ):
                status, stdout, stderr = self.run_cli(
                    [
                        "permute-sweep",
                        str(queue),
                        "--project",
                        str(root),
                        "--ranking",
                        str(ranking),
                        "--require-fresh",
                    ]
                )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertIn("error:", stderr)

    def test_a_fresh_ranking_is_silent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, ranking = self.write_project(root)
            stamp_ranking(ranking, "a" * 40)
            with unittest.mock.patch(
                "decomp_workbench.permute_cli.git_head", return_value="a" * 40
            ):
                status, _stdout, stderr = self.run_cli(
                    [
                        "permute-sweep",
                        str(queue),
                        "--project",
                        str(root),
                        "--ranking",
                        str(ranking),
                        "--require-fresh",
                        "--dry-run",
                    ]
                )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")

    def test_require_fresh_without_a_ranking_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, _ranking = self.write_project(root)
            status, _stdout, stderr = self.run_cli(
                [
                    "permute-sweep",
                    str(queue),
                    "--project",
                    str(root),
                    "--require-fresh",
                    "--dry-run",
                ]
            )
        self.assertEqual(status, 2)
        self.assertIn("--require-fresh needs a ranking", stderr)

    def test_the_doctor_checks_the_configured_ranking_too(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, ranking = self.write_project(root)
            config = root / ".decomp-workbench.toml"
            config.write_text(
                config.read_text(encoding="utf-8") + "ranking = 'ranking.json'\n",
                encoding="utf-8",
            )
            stamp_ranking(ranking, "a" * 40)
            with unittest.mock.patch(
                "decomp_workbench.permute_cli.git_head", return_value="b" * 40
            ):
                status, _stdout, stderr = self.run_cli(
                    [
                        "permute-doctor",
                        "far",
                        "--project",
                        str(root),
                        "--queue",
                        str(queue),
                        "--require-fresh",
                    ]
                )
        self.assertEqual(status, 2)
        self.assertIn("error:", stderr)

    def test_doctor_without_a_queue_needs_a_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_project(root)
            status, _stdout, stderr = self.run_cli(
                ["permute-doctor", "f", "--project", str(root)]
            )
        self.assertEqual(status, 2)
        self.assertIn("--source is required", stderr)


if __name__ == "__main__":
    unittest.main()
