"""Tests for the permuter sweep driver.

Nothing here needs decomp-permuter, a compiler, or a project build: the
parsers are pure, and the orchestration takes its process runner as an
argument, so a fake stands in for `make -n`, `import.py` and `permuter.py`.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from base64 import b64encode
from dataclasses import replace
from pathlib import Path
from typing import Any

from decomp_workbench.cli import main
from decomp_workbench.permute import (
    FIDELITY_DIFFERS,
    FIDELITY_IDENTICAL,
    FIDELITY_UNCHECKED,
    FIDELITY_UNKNOWN,
    FidelityAttempt,
    QueueItem,
    ScratchFidelity,
    SweepResult,
    best_output,
    completed_functions,
    earlier_results,
    fidelity_warning,
    join_continuations,
    load_gate_note,
    load_queue,
    load_ranking,
    macro_attributable,
    object_target,
    order_queue,
    parse_base_score,
    parse_dry_run,
    parse_preserved_macros,
    permuter_argv,
    recipe_report,
    recover_recipe,
    render_settings,
    render_table,
    resolve_preserve_macro_modes,
    retarget_labels,
    retarget_objcopy,
    should_extend,
    sweep_payload,
    wait_for_headroom,
)
from decomp_workbench.permute_classify import (
    MATCHED,
    P_STUCK_DESCENDING,
    classify_row,
)
from decomp_workbench.permute_sweep import (
    PermuterError,
    check_scratch_fidelity,
    doctor,
    expand_permuter_pragmas,
    prepare_scratch,
    render_doctor,
    resolve_plan,
    run_owned,
    run_permuter,
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

    def test_every_mention_of_the_object_is_retargeted(self) -> None:
        """`objcopy in.o out.o` names the object twice, and means both."""

        steps = retarget_objcopy((f"objcopy --weaken {OBJECT} {OBJECT}",), OBJECT)
        self.assertEqual(steps, ('objcopy --weaken "$OUTPUT" "$OUTPUT"',))

    def test_a_path_that_merely_starts_with_the_object_is_left_alone(self) -> None:
        """A sibling file is not the object, however alike the paths look.

        `--redefine-syms=<object>.syms` is the ordinary spelling of a
        redefine list, and a substring rewrite turns it into
        `"$OUTPUT".syms`: a path that does not exist, so every candidate
        fails to compile and the function reads as hard rather than as a
        broken scratch.
        """

        steps = retarget_objcopy(
            (f"objcopy --redefine-syms={OBJECT}.syms {OBJECT}",), OBJECT
        )
        self.assertEqual(steps, (f'objcopy --redefine-syms={OBJECT}.syms "$OUTPUT"',))

    def test_the_dot_slash_spelling_is_the_same_object(self) -> None:
        """`make` echoes whatever the rule wrote, including a `./` prefix."""

        steps = retarget_objcopy((f"objcopy --weaken-symbol C ./{OBJECT}",), OBJECT)
        self.assertEqual(steps, ('objcopy --weaken-symbol C "$OUTPUT"',))

    def test_another_object_under_a_similar_path_is_not_retargeted(self) -> None:
        steps = retarget_objcopy((f"objcopy --weaken vendor/{OBJECT}",), OBJECT)
        self.assertEqual(steps, (f"objcopy --weaken vendor/{OBJECT}",))

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

    def test_a_host_with_no_load_average_is_not_reported_as_idle(self) -> None:
        """None is not zero.

        `os.getloadavg` does not exist on Windows. Reading that as an idle
        machine lets every launch through a gate the operator set and
        believes in, so the gate does not stall -- there is nothing to wait
        for -- and the sweep says once that it is not gating.
        """

        self.assertEqual(wait_for_headroom(9.0, load=lambda: None), 0)
        note = load_gate_note(9.0, load=lambda: None)
        assert note is not None
        self.assertIn("not gated", note)
        self.assertIsNone(load_gate_note(9.0, load=lambda: 0.5))
        self.assertIsNone(load_gate_note(0.0, load=lambda: None))

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

    def test_a_function_whose_scratch_failed_is_not_counted_as_done(self) -> None:
        """`--resume` must not skip a function nothing was learned about.

        An IMPORT_FAULT row routes to fixing the scratch. Fixing it and
        resuming, only for the sweep to skip the very function that was
        repaired, is the trap: the run reports "queue exhausted" without
        ever searching it.
        """

        with tempfile.TemporaryDirectory() as temporary:
            summary = Path(temporary) / "summary.json"
            summary.write_text(
                json.dumps(
                    sweep_payload(
                        [
                            SweepResult(
                                function="done", source="a.c", ok=True, best_score=4
                            ),
                            SweepResult(
                                function="broken",
                                source="b.c",
                                ok=False,
                                error="import.py failed",
                            ),
                        ],
                        final=True,
                    )
                ),
                encoding="utf-8",
            )
            self.assertEqual(completed_functions(summary), {"done"})
            self.assertEqual(
                [result.function for result in earlier_results(summary)],
                ["done", "broken"],
            )

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

    def __init__(
        self,
        root: Path,
        *,
        dry_run: str = CONTINUED_DRY_RUN,
        preserve_macros: tuple[str, ...] = (),
    ) -> None:
        self.root = root
        self.dry_run = dry_run
        self.base_score = 214
        self.outputs: tuple[str, ...] = ("output-9-aaa",)
        self.import_fails = False
        self.commands: list[list[str]] = []
        self.preserve_macros = preserve_macros
        #: What `import.py` reports having preserved, per call.
        self.preserved_report = "macros: gDPPipeSync, gSPEndDisplayList"
        self.imports: list[str | None] = []
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
            preserve_macros=self.preserve_macros,
        )

    def build_the_object(self) -> Path:
        """Create the project object the fidelity check compares against."""

        obj = self.root / OBJECT
        obj.parent.mkdir(parents=True, exist_ok=True)
        obj.write_bytes(b"\x7fELF")
        return obj

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
            regex = (
                argv[argv.index("--preserve-macros") + 1]
                if "--preserve-macros" in argv
                else None
            )
            self.imports.append(regex)
            scratch = self.root / "nonmatchings" / "f"
            scratch.mkdir(parents=True, exist_ok=True)
            (scratch / "compile.sh").write_text('#!/bin/sh\ncc "$1"\n', "utf-8")
            (scratch / "base.c").write_text("int f(void) { return 0; }\n", "utf-8")
            preserved = "no macros" if regex == "" else self.preserved_report
            return subprocess.CompletedProcess(
                argv, 0, f"Preserving {preserved}. Use --preserve-macros\n", ""
            )
        if argv[0].endswith("compile.sh"):
            Path(argv[argv.index("-o") + 1]).write_bytes(b"\x7fELF")
            return subprocess.CompletedProcess(argv, 0, "", "")
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
            out_dir, scratch, recipe, steps, _fidelity = prepare_scratch(
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


class FakeComparison:
    """Just enough of a `Comparison` for the fidelity classifier to read."""

    def __init__(self, words: int, *, delta: int = 0, error: str | None = None) -> None:
        self.word_mismatches = words
        self.raw_word_mismatches = words
        self.instruction_delta = delta
        self.exact = words == 0 and delta == 0
        self.error = error


class ScriptedFidelity:
    """A fidelity checker that answers from a script instead of a compiler."""

    def __init__(self, *answers: ScratchFidelity) -> None:
        self.answers = list(answers)
        self.modes: list[str] = []

    def __call__(
        self,
        plan: Any,
        item: QueueItem,
        scratch: Path,
        out_dir: Path,
        *,
        mode: str,
        preserved_macros: tuple[str, ...] | None = None,
        runner: Any = None,
    ) -> ScratchFidelity:
        self.modes.append(mode)
        answer = self.answers[min(len(self.modes) - 1, len(self.answers) - 1)]
        return replace(
            answer, mode=mode, preserved_macros=tuple(preserved_macros or ())
        )


class PreserveMacroModeTests(unittest.TestCase):
    def test_the_default_modes_are_the_configured_set_then_none(self) -> None:
        modes = resolve_preserve_macro_modes(("g[DS]P.*=void",))
        self.assertEqual([mode.name for mode in modes], ["configured", "none"])
        self.assertEqual(modes[0].macros, ("g[DS]P.*=void",))
        self.assertIsNone(modes[0].regex)
        self.assertEqual(modes[1].macros, ())
        self.assertEqual(modes[1].regex, "")

    def test_a_project_with_no_macros_does_not_import_the_same_thing_twice(
        self,
    ) -> None:
        # `configured` with nothing configured *is* `none`: importing both
        # would spend a second import comparing a scratch with itself.
        modes = resolve_preserve_macro_modes(())
        self.assertEqual([mode.name for mode in modes], ["configured"])
        self.assertEqual(modes[0].regex, "")

    def test_a_mode_that_is_neither_name_is_a_narrowing_regex(self) -> None:
        modes = resolve_preserve_macro_modes(
            ("g[DS]P.*=void", "OS_PHYSICAL_TO_K0=void *"),
            ("configured", "OS_PHYSICAL_TO_K0", "none"),
        )
        self.assertEqual(
            [mode.name for mode in modes],
            ["configured", "OS_PHYSICAL_TO_K0", "none"],
        )
        # The narrowed mode keeps the type table and narrows the regex.
        self.assertEqual(modes[1].regex, "OS_PHYSICAL_TO_K0")
        self.assertEqual(modes[1].macros, modes[0].macros)


class PreservedMacroLogTests(unittest.TestCase):
    def test_the_import_log_says_which_macros_were_preserved(self) -> None:
        log = "Compiler type: ido\nPreserving macros: gDPPipeSync, gSPMatrix. Use\n"
        self.assertEqual(parse_preserved_macros(log), ("gDPPipeSync", "gSPMatrix"))

    def test_preserving_nothing_and_saying_nothing_are_different_answers(
        self,
    ) -> None:
        # An empty tuple rules preserved macros out as the cause of a
        # differing scratch; None rules nothing out.
        self.assertEqual(parse_preserved_macros("Preserving no macros. Use\n"), ())
        self.assertIsNone(parse_preserved_macros("Function name: f\n"))

    def test_only_a_scratch_that_preserved_something_is_worth_reimporting(
        self,
    ) -> None:
        differs = ScratchFidelity(
            status=FIDELITY_DIFFERS,
            differing_words=4,
            attempts=(FidelityAttempt(mode="configured", status=FIDELITY_DIFFERS),),
        )
        self.assertFalse(macro_attributable(differs))
        self.assertTrue(
            macro_attributable(replace(differs, preserved_macros=("gDPPipeSync",)))
        )
        self.assertFalse(macro_attributable(replace(differs, status=FIDELITY_UNKNOWN)))


class PragmaExpansionTests(unittest.TestCase):
    def test_the_latedefine_block_becomes_the_real_defines(self) -> None:
        source = "\n".join(
            (
                "#pragma _permuter latedefine start",
                "#pragma _permuter define gDPPipeSync(pkt) _g(pkt)",
                "void gDPPipeSync();",
                "#pragma _permuter latedefine end",
                "void f(void) { gDPPipeSync(x); }",
            )
        )
        expanded = expand_permuter_pragmas(source)
        self.assertIn("#define gDPPipeSync(pkt) _g(pkt)", expanded)
        # The fake declaration is what makes a macro call compile as a
        # function call; it must not reach the compiler.
        self.assertNotIn("void gDPPipeSync();", expanded)
        self.assertIn("void f(void) { gDPPipeSync(x); }", expanded)

    def test_a_b64_literal_is_restored(self) -> None:
        encoded = b64encode(b'__asm__("nop");').decode("ascii")
        expanded = expand_permuter_pragmas(f"#pragma _permuter b64literal {encoded}\n")
        self.assertIn('__asm__("nop");', expanded)

    def test_source_without_pragmas_is_returned_unchanged(self) -> None:
        self.assertEqual(expand_permuter_pragmas("int f(void);\n"), "int f(void);\n")


class ScratchFidelityTests(unittest.TestCase):
    def test_an_unbuilt_project_object_is_unknown_not_a_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            plan = resolve_plan(project.root, project.options)
            out_dir = plan.output_dir / "f"
            out_dir.mkdir(parents=True)
            fidelity = check_scratch_fidelity(
                plan,
                project.item,
                out_dir / "scratch",
                out_dir,
                mode="configured",
                runner=project.run,
            )
        self.assertEqual(fidelity.status, FIDELITY_UNKNOWN)
        self.assertEqual(fidelity.summary, "unknown")
        self.assertIn("is not built", fidelity.reason or "")
        self.assertEqual(fidelity.object, OBJECT)

    def test_an_identical_scratch_object_is_the_transferable_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            project.build_the_object()
            plan = resolve_plan(project.root, project.options)
            with unittest.mock.patch(
                "decomp_workbench.permute_sweep.compare_objects",
                return_value=FakeComparison(0),
            ):
                preparation = prepare_scratch(plan, project.item, runner=project.run)
        self.assertEqual(preparation.fidelity.status, FIDELITY_IDENTICAL)
        self.assertEqual(preparation.fidelity.summary, "identical")
        self.assertIsNone(fidelity_warning(preparation.fidelity, "f"))

    def test_a_differing_scratch_counts_its_words_and_is_loud(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            project.build_the_object()
            plan = resolve_plan(project.root, project.options)
            with unittest.mock.patch(
                "decomp_workbench.permute_sweep.compare_objects",
                return_value=FakeComparison(4),
            ):
                preparation = prepare_scratch(plan, project.item, runner=project.run)
        self.assertEqual(preparation.fidelity.status, FIDELITY_DIFFERS)
        self.assertEqual(preparation.fidelity.summary, "differs(4 words)")
        warning = fidelity_warning(preparation.fidelity, "f")
        self.assertIsNotNone(warning)
        self.assertIn("does not have to transfer", warning or "")

    def test_the_base_is_compiled_through_the_scratchs_own_compile_script(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            project.build_the_object()
            plan = resolve_plan(project.root, project.options)
            with unittest.mock.patch(
                "decomp_workbench.permute_sweep.compare_objects",
                return_value=FakeComparison(0),
            ):
                prepare_scratch(plan, project.item, runner=project.run)
            compiles = [
                argv for argv in project.commands if argv[0].endswith("compile.sh")
            ]
        self.assertEqual(len(compiles), 1)
        # Through compile.sh, because that is the script carrying the
        # recovered flags and the replicated objcopy chain.
        self.assertTrue(compiles[0][0].endswith("scratch/compile.sh"))
        self.assertTrue(compiles[0][1].endswith("fidelity-base.c"))

    def test_the_check_can_be_switched_off_entirely(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            project.build_the_object()
            plan = resolve_plan(project.root, project.options, check_fidelity=False)
            preparation = prepare_scratch(plan, project.item, runner=project.run)
            compiles = [
                argv for argv in project.commands if argv[0].endswith("compile.sh")
            ]
        self.assertEqual(preparation.fidelity.status, FIDELITY_UNCHECKED)
        self.assertEqual(compiles, [])


class PreserveMacroFallbackTests(unittest.TestCase):
    MACROS = ("g[DS]P.*=void",)

    def test_the_first_identical_mode_wins_and_stops_the_search(self) -> None:
        checker = ScriptedFidelity(
            ScratchFidelity(status=FIDELITY_DIFFERS, differing_words=8),
            ScratchFidelity(status=FIDELITY_IDENTICAL, differing_words=0),
        )
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary), preserve_macros=self.MACROS)
            plan = resolve_plan(project.root, project.options)
            preparation = prepare_scratch(
                plan, project.item, runner=project.run, fidelity_checker=checker
            )
        self.assertEqual(checker.modes, ["configured", "none"])
        # `none` is spelled to import.py as an empty --preserve-macros, which
        # is what makes the translation unit's real headers expand.
        self.assertEqual(project.imports, [None, ""])
        self.assertEqual(preparation.fidelity.status, FIDELITY_IDENTICAL)
        self.assertEqual(preparation.fidelity.mode, "none")
        self.assertEqual(
            [attempt.mode for attempt in preparation.fidelity.attempts],
            ["configured", "none"],
        )

    def test_a_difference_no_macro_can_explain_is_not_reimported(self) -> None:
        checker = ScriptedFidelity(
            ScratchFidelity(status=FIDELITY_DIFFERS, differing_words=8)
        )
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary), preserve_macros=self.MACROS)
            project.preserved_report = "no macros"
            plan = resolve_plan(project.root, project.options)
            preparation = prepare_scratch(
                plan, project.item, runner=project.run, fidelity_checker=checker
            )
        self.assertEqual(checker.modes, ["configured"])
        self.assertEqual(project.imports, [None])
        self.assertEqual(preparation.fidelity.status, FIDELITY_DIFFERS)

    def test_with_no_identical_mode_the_smallest_difference_is_kept(self) -> None:
        checker = ScriptedFidelity(
            ScratchFidelity(status=FIDELITY_DIFFERS, differing_words=2),
            ScratchFidelity(status=FIDELITY_DIFFERS, differing_words=7),
        )
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary), preserve_macros=self.MACROS)
            plan = resolve_plan(project.root, project.options)
            preparation = prepare_scratch(
                plan, project.item, runner=project.run, fidelity_checker=checker
            )
        self.assertEqual(checker.modes, ["configured", "none"])
        # The kept mode was not the one left on disk, so it is re-imported.
        self.assertEqual(project.imports, [None, "", None])
        self.assertEqual(preparation.fidelity.mode, "configured")
        self.assertEqual(preparation.fidelity.differing_words, 2)
        self.assertEqual(len(preparation.fidelity.attempts), 2)


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

    def test_the_record_says_where_in_the_window_the_best_result_landed(
        self,
    ) -> None:
        """The one thing no other record keeps.

        decomp-permuter overwrites its output directories, so once a run is
        over its mtime is the only evidence of when the search last
        improved -- and that is exactly what separates a plateau from a
        search the clock cut off.
        """

        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            plan = resolve_plan(project.root, project.options, minutes=1)
            ticks = iter([0.0, 0.0, 60.0, 60.0])
            result = search_function(
                plan,
                project.item,
                runner=project.run,
                clock=lambda: next(ticks),
            )
        self.assertEqual(result.window_seconds, 60.0)
        self.assertTrue(result.hit_cap)
        # The fake permuter wrote its output just now, so the best result
        # landed at the very end of the window.
        assert result.best_output_mtime_fraction is not None
        self.assertGreater(result.best_output_mtime_fraction, 0.9)
        self.assertEqual(classify_row(result.as_dict()).wall_class, P_STUCK_DESCENDING)

    def test_a_search_that_stopped_early_did_not_hit_its_cap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            project.outputs = ("output-0-win",)
            plan = resolve_plan(project.root, project.options, minutes=20)
            ticks = iter([0.0, 0.0, 75.0, 75.0])
            result = search_function(
                plan,
                project.item,
                runner=project.run,
                clock=lambda: next(ticks),
            )
        self.assertFalse(result.hit_cap)
        self.assertEqual(result.window_seconds, 1200.0)
        self.assertEqual(classify_row(result.as_dict()).wall_class, MATCHED)

    def test_a_preparation_failure_records_the_error_and_keeps_going(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            project.import_fails = True
            plan = resolve_plan(project.root, project.options, minutes=1)
            results = run_sweep(plan, [project.item, project.item], runner=project.run)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.error for result in results))


class FidelityReportingTests(unittest.TestCase):
    def test_a_search_records_the_fidelity_and_warns_about_a_difference(
        self,
    ) -> None:
        checker = ScriptedFidelity(
            ScratchFidelity(status=FIDELITY_DIFFERS, differing_words=6)
        )
        messages: list[str] = []
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            project.preserved_report = "no macros"
            plan = resolve_plan(project.root, project.options)
            result = search_function(
                plan,
                project.item,
                runner=project.run,
                report=messages.append,
                fidelity_checker=checker,
            )
        self.assertTrue(result.ok)
        self.assertEqual(result.scratch_fidelity, FIDELITY_DIFFERS)
        self.assertEqual(result.scratch_fidelity_words, 6)
        self.assertEqual(result.scratch_fidelity_mode, "configured")
        self.assertTrue(any("does not have to transfer" in line for line in messages))
        # The search still ran: a difference is loud, not fatal.
        self.assertEqual(result.base_score, 214)

    def test_require_fidelity_refuses_before_the_window_is_spent(self) -> None:
        checker = ScriptedFidelity(
            ScratchFidelity(status=FIDELITY_DIFFERS, differing_words=6)
        )
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            project.preserved_report = "no macros"
            plan = resolve_plan(project.root, project.options, require_fidelity=True)
            result = search_function(
                plan, project.item, runner=project.run, fidelity_checker=checker
            )
            launched = [
                argv
                for argv in project.commands
                if any(part.endswith("permuter.py") for part in argv)
            ]
        self.assertFalse(result.ok)
        self.assertIn("--require-fidelity", result.error or "")
        self.assertIn("differs(6 words)", result.error or "")
        self.assertEqual(launched, [])

    def test_the_summary_row_and_the_table_carry_the_verdict(self) -> None:
        results = [
            SweepResult(
                function="clean",
                source="a.c",
                ok=True,
                scratch_fidelity=FIDELITY_IDENTICAL,
                scratch_fidelity_words=0,
            ),
            SweepResult(
                function="dirty",
                source="b.c",
                ok=True,
                scratch_fidelity=FIDELITY_DIFFERS,
                scratch_fidelity_words=8,
            ),
        ]
        payload = sweep_payload(results, final=True)
        table = "\n".join(render_table(results))
        self.assertEqual(payload["totals"]["scratch_differs"], 1)
        self.assertEqual(payload["results"][0]["scratch_fidelity"], FIDELITY_IDENTICAL)
        self.assertIn("scratch", table)
        self.assertIn("identical", table)
        self.assertIn("DIFFERS/8", table)
        self.assertIn("1 on a scratch that is not the real object", table)


class ProcessOwnershipTests(unittest.TestCase):
    """A search that runs out of time must not leave workers behind.

    decomp-permuter is invoked with `-j`, so the process the sweep starts
    is the parent of a pool of compiling children. Killing only the direct
    child leaves that pool running: the reference host's runner accumulated
    permuter workers across a sweep until the machine was unusable, and
    every later timing in that campaign was measured under them.
    """

    def spawn(self, timeout: float) -> Path:
        temporary = tempfile.mkdtemp()
        marker = Path(temporary) / "child.pid"
        script = (
            "import pathlib, subprocess, sys, time\n"
            "child = subprocess.Popen([sys.executable, '-c',"
            " 'import time; time.sleep(60)'])\n"
            f"pathlib.Path({str(marker)!r}).write_text(str(child.pid))\n"
            "time.sleep(60)\n"
        )
        with self.assertRaises(subprocess.TimeoutExpired):
            run_owned(
                [sys.executable, "-c", script],
                cwd=Path.cwd(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
            )
        return marker

    @unittest.skipUnless(os.name == "posix", "process groups are POSIX here")
    def test_a_timeout_ends_the_whole_process_group(self) -> None:
        marker = self.spawn(timeout=3.0)
        pid = int(marker.read_text())
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                return
            time.sleep(0.05)
        os.kill(pid, 9)
        self.fail(f"grandchild {pid} outlived the timeout")

    def test_the_permuter_run_is_bounded_and_logged(self) -> None:
        """The timeout is the sweep's, and the log survives it."""

        with tempfile.TemporaryDirectory() as temporary:
            out_dir = Path(temporary)
            project = FakeProject(out_dir / "project")
            plan = resolve_plan(project.root, project.options)
            calls: list[float | None] = []

            def runner(
                argv: list[str], **kwargs: Any
            ) -> subprocess.CompletedProcess[str]:
                calls.append(kwargs.get("timeout"))
                return project.run(argv, **kwargs)

            score, elapsed = run_permuter(
                plan,
                out_dir / "scratch",
                out_dir,
                seconds=90.0,
                runner=runner,
                clock=iter([0.0, 12.0]).__next__,
            )
        self.assertEqual(calls, [90.0])
        self.assertEqual(score, 214)
        self.assertEqual(elapsed, 12.0)


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

    def test_the_doctor_reports_the_scratch_object_verdict(self) -> None:
        checker = ScriptedFidelity(
            ScratchFidelity(status=FIDELITY_DIFFERS, differing_words=3)
        )
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            project.preserved_report = "no macros"
            plan = resolve_plan(project.root, project.options)
            report = doctor(
                plan,
                project.item,
                seconds=60,
                runner=project.run,
                fidelity_checker=checker,
            )
            rendered = "\n".join(render_doctor(report))
        self.assertEqual(report.fidelity.status, FIDELITY_DIFFERS)
        self.assertIn("scratch object  differs(3 words) [configured]", rendered)
        self.assertIn("mode          configured: differs", rendered)
        # Loud, but not a refusal: the operator may know why it differs.
        self.assertTrue(report.ok)
        self.assertIn("ready", rendered.splitlines()[-1])

    def test_require_fidelity_makes_a_differing_scratch_a_problem(self) -> None:
        checker = ScriptedFidelity(
            ScratchFidelity(status=FIDELITY_DIFFERS, differing_words=3)
        )
        with tempfile.TemporaryDirectory() as temporary:
            project = FakeProject(Path(temporary))
            project.preserved_report = "no macros"
            plan = resolve_plan(project.root, project.options, require_fidelity=True)
            report = doctor(
                plan,
                project.item,
                seconds=60,
                runner=project.run,
                fidelity_checker=checker,
            )
        self.assertFalse(report.ok)
        self.assertIn("not the object the build produces", report.problems[0])

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

    def test_the_import_modes_and_their_objdump_are_read_from_the_config(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".decomp-workbench.toml").write_text(
                "[object]\nobjdump = 'mips-objdump'\n"
                "[permuter]\n"
                "preserve_macro_modes = ['configured', 'OS_PHYSICAL_TO_K0', 'none']\n",
                encoding="utf-8",
            )
            config = load_project_config(root / ".decomp-workbench.toml")
        self.assertEqual(
            config.permuter.preserve_macro_modes,
            ("configured", "OS_PHYSICAL_TO_K0", "none"),
        )
        # The fidelity comparison disassembles the same target with the same
        # tool as every other comparison, so it inherits object.objdump.
        self.assertEqual(config.permuter.objdump, "mips-objdump")

    def test_the_default_modes_are_the_configured_set_then_none(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".decomp-workbench.toml").write_text(
                "[permuter]\nmake = 'gmake'\n", encoding="utf-8"
            )
            config = load_project_config(root / ".decomp-workbench.toml")
        self.assertEqual(config.permuter.preserve_macro_modes, ("configured", "none"))

    def test_an_unusable_import_mode_is_refused_at_config_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".decomp-workbench.toml").write_text(
                "[permuter]\npreserve_macro_modes = ['gDP(']\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError) as raised:
                load_project_config(root / ".decomp-workbench.toml")
        self.assertIn("preserve_macro_modes", str(raised.exception))

    def test_an_unusable_skip_pattern_is_refused_at_config_time(self) -> None:
        """A bad regex would otherwise crash mid-sweep, not at load.

        `skip_postprocess` is compiled inside the dry-run parser, and
        `re.error` is not one of the exceptions the batch loop catches, so
        one malformed entry ends the whole run with a traceback after the
        first function's `make -n`.
        """

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".decomp-workbench.toml").write_text(
                "[permuter]\nskip_postprocess = ['*.py']\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError) as raised:
                load_project_config(root / ".decomp-workbench.toml")
        self.assertIn("skip_postprocess", str(raised.exception))
        self.assertIn("regular expression", str(raised.exception))

    def test_a_cap_of_zero_minutes_is_a_usage_error_not_a_default(self) -> None:
        """Zero is falsy, so it used to read as "no --minutes at all".

        A negative one was worse: a negative timeout expires immediately,
        and the row recorded a completed search of no seconds.
        """

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, _ranking = self.write_project(root)
            for value in ("0", "-5"):
                with self.assertRaises(SystemExit) as raised:
                    self.run_cli(
                        [
                            "permute-sweep",
                            str(queue),
                            "--project",
                            str(root),
                            "--minutes",
                            value,
                            "--dry-run",
                        ]
                    )
                self.assertEqual(raised.exception.code, 2)

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

    def test_resume_carries_the_done_rows_and_retries_the_broken_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue, _ranking = self.write_project(root)
            out = root / "out"
            out.mkdir()
            (out / "summary.json").write_text(
                json.dumps(
                    sweep_payload(
                        [
                            SweepResult(function="near", source="a.c", ok=True),
                            SweepResult(
                                function="far", source="b.c", error="import.py failed"
                            ),
                        ],
                        final=True,
                    )
                ),
                encoding="utf-8",
            )
            status, stdout, _stderr = self.run_cli(
                [
                    "permute-sweep",
                    str(queue),
                    "--project",
                    str(root),
                    "--output-dir",
                    str(out),
                    "--resume",
                    "--dry-run",
                ]
            )
        self.assertEqual(status, 0)
        self.assertIn("skipping 1", stdout)
        self.assertIn("far", stdout)
        self.assertNotIn("near", stdout.split("queued function(s):")[1])

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
