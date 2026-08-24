"""`sweep build`: the compile fan-out, its cache, and its scored table.

The compiler here is a Python script the test writes: it copies a prebuilt
object into place. That keeps the wave's own behaviour -- pool, nice, cache,
ordering, table -- under test without a MIPS toolchain, which is the same
policy `elf_fixtures` states for the ELF readers. The objects it copies are
hand-built ELFs holding synthetic instruction words.
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from elf_fixtures import STB_GLOBAL, STT_FUNC, build_object, words

from decomp_workbench.sweep_build import (
    DEFAULT_JOBS,
    DEFAULT_NICE,
    SweepBuild,
    SweepBuildError,
    build_lines,
    collect_sources,
    run_sweep_build,
)
from decomp_workbench.sweep_cli import sweep_build_command
from decomp_workbench.watch_rows import parse_watch_rows

TARGET_WORDS = words(
    0x27BDFFE8,  # addiu sp,sp,-24
    0x00851021,  # addu v0,a0,a1
    0x24420004,  # addiu v0,v0,4
    0x03E00008,  # jr ra
    0x27BD0018,  # addiu sp,sp,24
)
#: One register different at row 1: a candidate that is close but not exact.
NEAR_WORDS = words(
    0x27BDFFE8,
    0x00851821,  # addu v1,a0,a1
    0x24420004,
    0x03E00008,
    0x27BD0018,
)
#: A different constant at row 2 as well: strictly further away.
FAR_WORDS = words(
    0x27BDFFE8,
    0x00851821,
    0x24420008,  # addiu v0,v0,8
    0x03E00008,
    0x27BD0018,
)


def _object(text: bytes) -> bytes:
    return build_object(
        text=text,
        symbols=[("wb_demo", 0, len(text), STT_FUNC, STB_GLOBAL)],
    )


HAVE_OBJDUMP = bool(
    shutil.which("mips-linux-gnu-objdump") or shutil.which("mips64-elf-objdump")
)


class CollectSourcesTests(unittest.TestCase):
    def test_a_directory_contributes_its_sources_in_order(self) -> None:
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            for name in ("b.c", "a.c", "notes.txt"):
                (directory / name).write_text("x", encoding="utf-8")
            found = collect_sources([directory])
        self.assertEqual([item.name for item in found], ["a.c", "b.c"])

    def test_a_sweep_directory_follows_its_manifest_order(self) -> None:
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            for name in ("v-second.c", "v-first.c"):
                (directory / name).write_text("x", encoding="utf-8")
            (directory / "sweep.json").write_text(
                json.dumps(
                    {
                        "schema": "decomp-workbench-sweep-v1",
                        "generator": "demo",
                        "base": "base.c",
                        "base_sha256": "0" * 64,
                        "variants": [
                            {
                                "site": "L2",
                                "class": "H",
                                "carrier": "-",
                                "filename": "v-second.c",
                            },
                            {
                                "site": "L1",
                                "class": "H",
                                "carrier": "-",
                                "filename": "v-first.c",
                            },
                        ],
                        "coverage": {"basis": "sampled", "covered": 2},
                    }
                ),
                encoding="utf-8",
            )
            found = collect_sources([directory])
        self.assertEqual([item.name for item in found], ["v-second.c", "v-first.c"])

    def test_a_missing_input_names_what_the_command_accepts(self) -> None:
        with self.assertRaises(SweepBuildError) as caught:
            collect_sources(["/nonexistent/variants"])
        self.assertIn("sweep.json", str(caught.exception))

    def test_a_source_named_twice_is_built_once(self) -> None:
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            source = directory / "a.c"
            source.write_text("x", encoding="utf-8")
            found = collect_sources([source, directory, source])
        self.assertEqual(len(found), 1)


@unittest.skipUnless(HAVE_OBJDUMP, "needs a MIPS objdump")
class WaveTests(unittest.TestCase):
    """A whole wave, driven by a fake compiler that copies prebuilt objects."""

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = self.root / "variants"
        self.sources.mkdir()
        self.objects = self.root / "objects"
        self.prebuilt = self.root / "prebuilt"
        self.prebuilt.mkdir()
        self.target = self.root / "target.o"
        self.target.write_bytes(_object(TARGET_WORDS))
        for name, text in (
            ("exact", TARGET_WORDS),
            ("near", NEAR_WORDS),
            ("far", FAR_WORDS),
        ):
            (self.prebuilt / f"{name}.o").write_bytes(_object(text))
            (self.sources / f"{name}.c").write_text(f"/* {name} */\n", encoding="utf-8")
        # A source with no prebuilt object: the compiler refuses it, and the
        # wave must report it rather than lose it.
        (self.sources / "broken.c").write_text("/* broken */\n", encoding="utf-8")
        self.compiler = self.root / "fake-cc.py"
        self.compiler.write_text(
            "import shutil, sys, pathlib\n"
            "source, output = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])\n"
            f"prebuilt = pathlib.Path({str(self.prebuilt)!r}) / (source.stem + '.o')\n"
            "if not prebuilt.is_file():\n"
            "    sys.stderr.write('no rule to make ' + source.stem + '\\n')\n"
            "    raise SystemExit(2)\n"
            "shutil.copyfile(prebuilt, output)\n"
            "counter = output.parent / 'compile-count.txt'\n"
            "counter.write_text(str(int(counter.read_text() or 0) + 1)"
            " if counter.exists() else '1')\n",
            encoding="utf-8",
        )
        self.template = f"{sys.executable} {self.compiler} {{source}} {{output}}"

    def _run(self, **overrides: object) -> SweepBuild:
        settings: dict[str, object] = {
            "target": self.target,
            "template": self.template,
            "objects": self.objects,
            "jobs": 2,
            "niceness": DEFAULT_NICE,
            "timeout": 60.0,
        }
        settings.update(overrides)
        return run_sweep_build(collect_sources([self.sources]), **settings)  # type: ignore[arg-type]

    def test_the_table_is_ranked_and_nothing_is_lost(self) -> None:
        wave = self._run()
        self.assertEqual([item.label for item in wave.ranked], ["exact", "near", "far"])
        self.assertEqual([item.label for item in wave.unscored], ["broken"])
        self.assertEqual(wave.unscored[0].status, "failed")
        self.assertIn("no rule to make broken", wave.unscored[0].detail)
        self.assertEqual(wave.count("compiled"), 3)

    def test_an_up_to_date_object_is_not_rebuilt(self) -> None:
        first = self._run()
        self.assertEqual(first.count("compiled"), 3)
        second = self._run()
        self.assertEqual(second.count("cached"), 3)
        self.assertEqual(second.count("compiled"), 0)
        # The table is identical either way: a cache that changes the answer
        # is worse than no cache.
        self.assertEqual(
            [item.label for item in second.ranked],
            [item.label for item in first.ranked],
        )

    def test_a_changed_compile_command_invalidates_the_cache(self) -> None:
        self._run()
        # A flag the fake compiler ignores: the *object* is identical, and the
        # cache must still rebuild, because a wave is usually re-run precisely
        # because the compile command changed. An mtime check would keep every
        # stale object here.
        again = self._run(template=self.template + " --ignored-flag")
        self.assertEqual(again.count("compiled"), 3)

    def test_refresh_rebuilds_everything(self) -> None:
        self._run()
        again = self._run(refresh=True)
        self.assertEqual(again.count("compiled"), 3)

    def test_the_watch_signature_is_a_column(self) -> None:
        wave = self._run(watch=parse_watch_rows("a=1,b=2"))
        signatures = {item.label: item.signature for item in wave.ranked}
        self.assertEqual(signatures["exact"], "..")
        self.assertEqual(signatures["near"], "X.")
        self.assertEqual(signatures["far"], "XX")

    def test_the_watch_order_ranks_by_healed_columns(self) -> None:
        wave = self._run(watch=parse_watch_rows("a=1,b=2"), order="watch")
        self.assertEqual([item.label for item in wave.ranked], ["exact", "near", "far"])

    def test_the_name_order_ignores_the_metrics(self) -> None:
        wave = self._run(order="name")
        self.assertEqual([item.label for item in wave.ranked], ["exact", "far", "near"])

    def test_an_unknown_order_is_refused(self) -> None:
        with self.assertRaises(SweepBuildError):
            self._run(order="vibes")

    def test_the_terminal_table_carries_the_signature_and_the_verdict(self) -> None:
        rendered = "\n".join(
            build_lines(self._run(watch=parse_watch_rows("r1=1,r2=2")))
        )
        self.assertIn("watch rows", rendered)
        self.assertIn("r1 r2", rendered)
        self.assertIn("instruction-words-identical", rendered)
        self.assertIn("EXACT: exact", rendered)
        self.assertIn("failed", rendered)

    def test_the_json_reports_every_status_and_the_ranked_rows(self) -> None:
        payload = self._run(watch=parse_watch_rows("r1=1")).as_dict()
        self.assertEqual(payload["schema"], "decomp-workbench-sweep-build-v1")
        self.assertEqual(payload["compiled"], 3)
        self.assertEqual(payload["failed"], 1)
        self.assertEqual(
            [row["label"] for row in payload["results"]], ["exact", "near", "far"]
        )
        self.assertEqual(payload["results"][0]["watch_signature"], ".")
        self.assertEqual(payload["results"][0]["words"], 0)
        self.assertEqual([row["label"] for row in payload["unscored"]], ["broken"])

    def test_the_default_pool_and_niceness_are_the_documented_ones(self) -> None:
        self.assertEqual((DEFAULT_JOBS, DEFAULT_NICE), (4, 10))

    def test_the_command_surface_exits_zero_and_prints_json(self) -> None:
        args = argparse.Namespace(
            sources=[str(self.sources)],
            target=str(self.target),
            compile_command=self.template,
            objects=str(self.objects),
            jobs=2,
            nice=DEFAULT_NICE,
            refresh=False,
            sort="words",
            source_suffix=".c",
            object_suffix=".o",
            compile_cwd=None,
            timeout=60.0,
            section=".text",
            objdump=None,
            symbol=None,
            watch_rows="r1=1",
            limit=40,
            json=True,
            width=None,
            pager=False,
        )
        stream = io.StringIO()
        with redirect_stdout(stream):
            status = sweep_build_command(args)
        self.assertEqual(status, 0)
        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["nice"], DEFAULT_NICE)
        self.assertEqual(payload["jobs"], 2)
        self.assertEqual([entry["label"] for entry in payload["watch_row_set"]], ["r1"])

    def test_a_wave_that_scores_nothing_exits_one(self) -> None:
        empty = self.root / "none"
        empty.mkdir()
        (empty / "broken.c").write_text("/* broken */\n", encoding="utf-8")
        args = argparse.Namespace(
            sources=[str(empty)],
            target=str(self.target),
            compile_command=self.template,
            objects=str(self.root / "none-objects"),
            jobs=1,
            nice=0,
            refresh=False,
            sort="words",
            source_suffix=".c",
            object_suffix=".o",
            compile_cwd=None,
            timeout=60.0,
            section=".text",
            objdump=None,
            symbol=None,
            watch_rows=None,
            limit=40,
            json=True,
            width=None,
            pager=False,
        )
        stream = io.StringIO()
        with redirect_stdout(stream):
            status = sweep_build_command(args)
        # Not a negative result about the search space: nothing was measured.
        self.assertEqual(status, 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
