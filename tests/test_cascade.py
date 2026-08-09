"""The decision cascade, and the four ways campaign scripts got it wrong.

Every fixture here is the shape of one real incident:

* a four-round `f_split` cascade whose parent declined on cost, printed by
  tools that grepped only the final `p1dec` (WB-70);
* the same site across a rebase that renumbered `sym=1042` to `sym=1039`,
  which made a hard-coded lookup report a kill that never happened (WB-71);
* a forced run whose `bestcolor` is not the colour the web received (WB-88);
* float colours named from a map that was wrong for four stages (WB-80).
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from mips_asm import assemble

from decomp_workbench.cascade import (
    CascadeError,
    CdxLog,
    block_report,
    color_order_report,
    parse_frame_offset,
)
from decomp_workbench.cli import main
from decomp_workbench.model import Instruction
from decomp_workbench.objdump import parse_disassembly

SYMBOL = "demo"

# The real grammar, with the campaign's own field order and spelling. Numbers
# are small so the arithmetic is checkable by eye; the shape -- four splits
# then a colour, the memory-resident piece after each split, the occurrence
# list before each `savedetail` -- is the shape of the GE007 sp4A0 cascade.
_DETAIL = (
    "[CDX] webdetail phase=p1 proc=0 role=target web={web} sym={sym} type=3 "
    "dtype=13 table=847 chain=1 exprtable=1865 exprchain=1 bb=371 line=23 "
    "raw10={raw10} raw14=0x00030102 raw18=0x04010000 raw20=0x00000000"
)
_OCC = (
    "[CDX] saveocc proc=0 web={web} occ={occ} usesdefs=1.0 weight={weight} "
    "term=1.000000 bb={bb} uses={uses} defs={defs} occp=1 nl={nl} bb5=0 "
    "o22={o22} o23={o23} w34={w34}"
)
_SAVE = (
    "[CDX] savedetail proc=0 web={web} sym={sym} occ={occ} gross={gross} "
    "chargeA={charge_a} chargeB={charge_b} net={net} divisor={nocs} "
    "nocs={nocs} dtype=13 save={save} class={piece_class} forced=0"
)
_DEC = (
    "[CDX] p1dec phase=p1 proc=0 web={web} sym={sym} class=2 save={save} "
    "nocs={nocs} totalsave={net} bestcost={cost} bestcolor={color} bestreg=? "
    "forbidden0={forbidden} forbidden1=0x00000000 regsleft=5 numintf={intf} "
    "available0={available} available1=0x00000000 allcallersave=0 taken1=-1 "
    "taken2=-1 decision={decision} forced={forced}"
)
_COLOR = (
    "[CDX] p1color phase=p1 proc=0 web={web} sym={sym} color={color} reg=? "
    "forced={forced}"
)

#: `0x000000fb` leaves exactly c29 free; `0x000000e3` leaves c27/c28/c29.
ONE_FREE = "0x000000fb"
ONE_FREE_TIE = "0x00000004"
THREE_FREE = "0x000000e3"
THREE_FREE_TIE = "0x0000001c"

TARGET_OFFSET = "0xfffffdf8"


def cascade_log(*, symbol: int, killed: bool) -> str:
    """A four-round split cascade, ending in a colour or in a kill."""

    lines = ["[CDX] globalcolor proc=0"]
    parent, child = symbol, symbol + 2020
    for web in (parent, child):
        lines.append(_DETAIL.format(web=web, sym=symbol, raw10=TARGET_OFFSET))
    # A competing float web, decided first, so the site is never the only
    # record in the log and the colour order has something to rank.
    lines.append(_DETAIL.format(web=255, sym=255, raw10="0xfffffcec"))
    lines.append(
        _OCC.format(
            web=255,
            occ=1,
            weight="1.0",
            bb=900,
            uses=2,
            defs=0,
            nl=0,
            o22=0,
            o23=0,
            w34=0,
        )
    )
    lines.append(
        _SAVE.format(
            web=255,
            sym=255,
            occ=1,
            gross="24.000000",
            charge_a="0.000000",
            charge_b="0.000000",
            net="24.000000",
            nocs=3,
            save="8.000000",
            piece_class=1,
        )
    )
    lines.append(
        _DEC.format(
            web=255,
            sym=255,
            save="8.000000",
            nocs=3,
            net="24.000000",
            cost="0.000000",
            color=25,
            forbidden=THREE_FREE,
            intf=16,
            available=THREE_FREE_TIE,
            decision="color",
            forced=-2,
        )
    )
    lines.append(_COLOR.format(web=255, sym=255, color=25, forced=-2))

    # Rounds 1-3: the parent declines on cost three times, each leaving one
    # memory-resident piece behind.
    for index, (net, charge_b) in enumerate(
        ((8.0, 0.0), (3.0, 2.0), (2.0, 0.0)), start=1
    ):
        lines.append(
            _OCC.format(
                web=parent,
                occ=1,
                weight="1.0",
                bb=100 + index,
                uses=1,
                defs=0,
                nl=0,
                o22=0,
                o23=0,
                w34=1,
            )
        )
        if charge_b:
            lines.append(
                _OCC.format(
                    web=parent,
                    occ=2,
                    weight="2.0",
                    bb=200 + index,
                    uses=0,
                    defs=1,
                    nl=0,
                    o22=1,
                    o23=0,
                    w34=1,
                )
            )
        lines.append(
            _SAVE.format(
                web=parent,
                sym=symbol,
                occ=2 if charge_b else 1,
                gross=f"{net + charge_b:.6f}",
                charge_a="0.000000",
                charge_b=f"{charge_b:.6f}",
                net=f"{net:.6f}",
                nocs=19,
                save=f"{net / 19:.6f}",
                piece_class=1,
            )
        )
        lines.append(
            _DEC.format(
                web=parent,
                sym=symbol,
                save=f"{net / 19:.6f}",
                nocs=19,
                net=f"{net:.6f}",
                cost="8.000000",
                color=29,
                forbidden=ONE_FREE,
                intf=28,
                available=ONE_FREE_TIE,
                decision="split",
                forced=-2,
            )
        )
        lines.append(
            _SAVE.format(
                web=parent,
                sym=symbol,
                occ=1,
                gross="1.000000",
                charge_a="2.000000",
                charge_b="0.000000",
                net="-1.000000",
                nocs=2,
                save="-0.500000",
                piece_class=2,
            )
        )

    # Round 4: the surviving child. Coloured, unless this is the killed build.
    lines.append(
        _OCC.format(
            web=child,
            occ=1,
            weight="1.0",
            bb=300,
            uses=2,
            defs=1,
            nl=0,
            o22=0,
            o23=1,
            w34=1,
        )
    )
    lines.append(
        _SAVE.format(
            web=child,
            sym=symbol,
            occ=1,
            gross="5.000000",
            charge_a="1.000000",
            charge_b="0.000000",
            net="0.000000" if killed else "4.000000",
            nocs=2,
            save="0.000000" if killed else "2.000000",
            piece_class=2 if killed else 1,
        )
    )
    lines.append(
        _DEC.format(
            web=child,
            sym=symbol,
            save="0.000000" if killed else "2.000000",
            nocs=2,
            net="0.000000" if killed else "4.000000",
            cost="0.000000",
            color=27,
            forbidden=THREE_FREE,
            intf=10,
            available=THREE_FREE_TIE,
            decision="split" if killed else "color",
            forced=-2,
        )
    )
    if not killed:
        lines.append(_COLOR.format(web=child, sym=symbol, color=27, forced=-2))
    return "\n".join(lines) + "\n"


def forced_log() -> str:
    """A CDX_FORCE run: `bestcolor` is 24, the web is forced onto c25."""

    return (
        "\n".join(
            (
                "[CDX] globalcolor proc=0",
                _DETAIL.format(web=40, sym=40, raw10=TARGET_OFFSET),
                _DEC.format(
                    web=40,
                    sym=40,
                    save="2.000000",
                    nocs=2,
                    net="4.000000",
                    cost="0.000000",
                    color=24,
                    forbidden=THREE_FREE,
                    intf=10,
                    available=THREE_FREE_TIE,
                    decision="color",
                    forced=25,
                ),
                _COLOR.format(web=40, sym=40, color=25, forced=25),
            )
        )
        + "\n"
    )


def shipped_only_log() -> str:
    """What a log looks like without the campaign-local save records."""

    text = cascade_log(symbol=1039, killed=False)
    return (
        "\n".join(
            line
            for line in text.splitlines()
            if not line.startswith(("[CDX] savedetail", "[CDX] saveocc"))
        )
        + "\n"
    )


def tie_log() -> str:
    """The cascade log plus a second web tying with w255 on `save`."""

    return cascade_log(symbol=1039, killed=False) + (
        "[CDX] p1dec phase=p1 proc=0 web=260 sym=260 class=2 save=8.000000 "
        "nocs=3 totalsave=24.000000 bestcost=0.000000 bestcolor=24 "
        "bestreg=? forbidden0=0x000000e3 forbidden1=0x00000000 regsleft=5 "
        "numintf=15 available0=0x0000001c available1=0x00000000 "
        "allcallersave=0 taken1=-1 taken2=-1 decision=color forced=-2\n"
    )


@contextlib.contextmanager
def written(text: str, *, name: str = "build.ilog", objects: tuple[str, ...] = ()):
    """Write one log, plus any object files a command will hash by path."""

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / name
        path.write_text(text, encoding="utf-8")
        for item in objects:
            (Path(directory) / item).write_bytes(b"\x7fELF placeholder")
        yield str(path)


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = main(arguments)
    return status, stdout.getvalue(), stderr.getvalue()


def fake_dump(text: str) -> Callable[..., tuple[str, list[Instruction]]]:
    def _dump(
        path: str | Path,
        *,
        objdump: str | None = None,
        symbol: str | None = None,
        section: str = ".text",
    ) -> tuple[str, list[Instruction]]:
        return text, parse_disassembly(text, symbol=symbol)

    return _dump


class CascadeReadingTests(unittest.TestCase):
    def log(self, **kwargs: object) -> CdxLog:
        return CdxLog(cascade_log(symbol=1039, killed=False), name="build.ilog")

    def test_every_round_is_reported_not_only_the_last(self) -> None:
        """WB-70: one site's residue was the tail of a four-round cascade."""

        log = self.log()
        cascade = log.cascade(
            log.resolve(frame_offset=parse_frame_offset(TARGET_OFFSET))
        )

        self.assertEqual(len(cascade.rounds), 4)
        self.assertEqual(
            [item.decision for item in cascade.rounds],
            ["split", "split", "split", "color"],
        )
        # The parent declined on cost three times before the child was
        # coloured; a printer that read only the final record would report
        # that colour with no cascade behind it.
        self.assertEqual([item.index for item in cascade.rounds], [1, 2, 3, 4])
        self.assertTrue(all(item.web == 1039 for item in cascade.rounds[:3]))
        self.assertEqual(cascade.rounds[3].web, 3059)

    def test_the_site_is_found_across_a_symbol_renumbering(self) -> None:
        """WB-71: sym=1042 became sym=1039 and a hard-coded lookup lied."""

        offset = parse_frame_offset(TARGET_OFFSET)
        before = CdxLog(cascade_log(symbol=1042, killed=False), name="before.ilog")
        after = CdxLog(cascade_log(symbol=1039, killed=True), name="after.ilog")

        first = before.cascade(before.resolve(frame_offset=offset))
        second = after.cascade(after.resolve(frame_offset=offset))

        self.assertEqual(first.site.symbol, 1042)
        self.assertEqual(second.site.symbol, 1039)
        self.assertFalse(first.killed)
        self.assertTrue(second.killed)

    def test_a_missing_offset_says_it_is_not_a_kill(self) -> None:
        log = self.log()

        with self.assertRaises(CascadeError) as caught:
            log.resolve(frame_offset=parse_frame_offset("0xfffffd00"))

        message = str(caught.exception)
        self.assertIn("NOT a kill", message)
        self.assertIn("Nearest offsets present", message)
        self.assertIn(TARGET_OFFSET, message)

    def test_a_symbol_lookup_carries_its_own_caution(self) -> None:
        log = self.log()

        site = log.resolve(symbol=1039)

        assert site.caution is not None
        self.assertIn("trace-local", site.caution)
        self.assertIn("--frame-offset", site.caution)

    def test_the_colour_reported_is_the_post_resolution_one(self) -> None:
        """WB-88: `bestcolor` is the pre-force, pre-split field."""

        log = CdxLog(forced_log(), name="forced.ilog")
        cascade = log.cascade(
            log.resolve(frame_offset=parse_frame_offset(TARGET_OFFSET))
        )
        item = cascade.rounds[0]

        self.assertEqual(item.natural_color, 24)
        self.assertEqual(item.resolved_color, 25)
        self.assertTrue(item.resolution_differs)
        self.assertEqual(item.resolved_register, "$f2")

    def test_float_registers_are_named_from_the_corrected_map(self) -> None:
        """WB-80: `c24=$f8 c25=$f10` was wrong for four stages."""

        log = self.log()
        cascade = log.cascade(
            log.resolve(frame_offset=parse_frame_offset(TARGET_OFFSET))
        )

        self.assertEqual(cascade.rounds[0].natural_register, "$f18")
        self.assertEqual(cascade.rounds[3].resolved_register, "$f14")
        self.assertEqual(
            [
                cascade.rounds[3].color_name(color)
                for color in cascade.rounds[3].forbidden
            ],
            ["c24/$f0", "c25/$f2", "c26/$f12", "c30", "c31"],
        )

    def test_the_decision_prints_as_one_inequality(self) -> None:
        """WB-110: `totalsave` and `net` are one number under two names."""

        log = self.log()
        cascade = log.cascade(
            log.resolve(frame_offset=parse_frame_offset(TARGET_OFFSET))
        )

        self.assertEqual(
            cascade.rounds[0].inequality,
            "net 8.000 <= bestcost 8.000 ?  YES -> split (memory-resident, no colour)",
        )
        self.assertEqual(
            cascade.rounds[3].inequality,
            "net 4.000 <= bestcost 0.000 ?  NO -> colour it",
        )
        self.assertAlmostEqual(cascade.rounds[3].deficit, 4.0)

    def test_the_chargeb_gate_reproduces_the_recorded_charge(self) -> None:
        """WB-110/L92: chargeB is a store-placement term, not a loop term."""

        log = self.log()
        cascade = log.cascade(
            log.resolve(frame_offset=parse_frame_offset(TARGET_OFFSET))
        )
        detail = cascade.rounds[1].entering
        assert detail is not None

        self.assertEqual(detail.charge_b, 2.0)
        self.assertTrue(detail.charge_b_accounted)
        payers = detail.charge_b_contributors
        self.assertEqual([item.index for item in payers], [2])
        # The payer's weight is 2.0 and nothing about it is a loop: `o22` and a
        # def are the whole gate.
        self.assertEqual((payers[0].o22, payers[0].defs, payers[0].o23), (1, 1, 0))

    def test_each_round_keeps_its_own_occurrence_list(self) -> None:
        log = self.log()
        cascade = log.cascade(
            log.resolve(frame_offset=parse_frame_offset(TARGET_OFFSET))
        )

        counts = [
            len(item.entering.occurrences) if item.entering else 0
            for item in cascade.rounds
        ]
        self.assertEqual(counts, [1, 2, 1, 1])

    def test_a_shipped_only_log_still_gives_rounds_and_the_kill_signal(self) -> None:
        """The save records are campaign-local; the decision records are not."""

        log = CdxLog(shipped_only_log(), name="shipped.ilog")
        cascade = log.cascade(
            log.resolve(frame_offset=parse_frame_offset(TARGET_OFFSET))
        )

        self.assertEqual(len(cascade.rounds), 4)
        self.assertFalse(cascade.killed)
        self.assertIsNone(cascade.rounds[0].entering)

    def test_a_block_report_needs_the_campaign_local_records(self) -> None:
        log = CdxLog(shipped_only_log(), name="shipped.ilog")

        with self.assertRaises(CascadeError) as caught:
            block_report(log, webs=[1039], blocks=[])

        message = str(caught.exception)
        self.assertIn("saveocc", message)
        self.assertIn("campaign-local uopt patch", message)

    def test_a_log_without_cdx_records_says_how_to_make_one(self) -> None:
        with written("nothing here\n") as path:
            with self.assertRaises(CascadeError) as caught:
                CdxLog.read(path)

        self.assertIn("CDX_LOG=1", str(caught.exception))


class KillSignalTests(unittest.TestCase):
    def test_the_kill_line_names_the_colour_that_was_taken(self) -> None:
        """WB-120: a 946-variant sweep reduced to one column."""

        log = CdxLog(cascade_log(symbol=1039, killed=False), name="A1.ilog")
        cascade = log.cascade(
            log.resolve(frame_offset=parse_frame_offset(TARGET_OFFSET))
        )

        self.assertEqual(
            cascade.kill_line(),
            "kill: NO A1.ilog sym=1039 rounds=4 colors=1 final=w3059:c27/$f14",
        )

    def test_the_kill_line_says_yes_when_no_web_was_coloured(self) -> None:
        log = CdxLog(cascade_log(symbol=1039, killed=True), name="FINAL.ilog")
        cascade = log.cascade(
            log.resolve(frame_offset=parse_frame_offset(TARGET_OFFSET))
        )

        self.assertTrue(cascade.killed)
        self.assertEqual(
            cascade.kill_line(),
            "kill: YES FINAL.ilog sym=1039 rounds=4 colors=0",
        )


class ColorOrderTests(unittest.TestCase):
    def test_the_order_names_the_same_save_tie_groups(self) -> None:
        """WB-116: p1 breaks ties by ascending web number (L31)."""

        report = color_order_report(CdxLog(tie_log(), name="build.ilog"), limit=None)

        self.assertEqual(len(report["tie_groups"]), 1)
        group = report["tie_groups"][0]
        self.assertEqual(group["save"], 8.0)
        self.assertEqual([item["web"] for item in group["members"]], [255, 260])

    def test_the_float_class_filter_is_the_float_web_census(self) -> None:
        """WB-85: every float web in the object, in decision order, one pass."""

        log = CdxLog(cascade_log(symbol=1039, killed=False), name="build.ilog")

        floats = color_order_report(log, limit=None, register_class=2)
        integers = color_order_report(log, limit=None, register_class=1)

        self.assertEqual(floats["shown"], floats["decision_count"])
        self.assertTrue(all(item["register_class"] == 2 for item in floats["order"]))
        self.assertEqual(integers["shown"], 0)
        # Positions are the true colouring positions, not positions within the
        # filtered view: a filtered rank that renumbers is a different fact.
        self.assertEqual(floats["order"][0]["position"], 1)


class BlockIntersectionTests(unittest.TestCase):
    def test_two_webs_sharing_no_block_are_named_as_disjoint(self) -> None:
        """WB-114: five stages argued this from `numintf` deltas."""

        log = CdxLog(cascade_log(symbol=1039, killed=False), name="build.ilog")

        report = block_report(log, webs=[255, 3059], blocks=[])

        self.assertTrue(report["disjoint"])
        self.assertEqual(report["intersection"], [])
        self.assertEqual(report["webs"][0]["blocks"], [900])
        self.assertEqual(report["webs"][1]["blocks"], [300])

    def test_a_block_query_finds_every_web_occurring_in_it(self) -> None:
        log = CdxLog(cascade_log(symbol=1039, killed=False), name="build.ilog")

        report = block_report(log, webs=[], blocks=[900])

        self.assertEqual([item["web"] for item in report["webs"]], [255])

    def test_a_web_with_no_occurrences_is_an_error_not_an_empty_set(self) -> None:
        log = CdxLog(cascade_log(symbol=1039, killed=False), name="build.ilog")

        with self.assertRaises(CascadeError) as caught:
            block_report(log, webs=[999], blocks=[])

        self.assertIn("999", str(caught.exception))


PROLOGUE = ["addiu sp,sp,-1704", "sw ra,28(sp)"]
EPILOGUE = ["lw ra,28(sp)", "jr ra", "addiu sp,sp,1704"]
ROM_BODY = [*PROLOGUE, "lwc1 f0,1184(sp)", "swc1 f12,1184(sp)", *EPILOGUE]
CANDIDATE_BODY = [
    *PROLOGUE,
    "lwc1 f14,1184(sp)",
    "lwc1 f14,1184(sp)",
    "swc1 f14,1184(sp)",
    *EPILOGUE,
]


class CascadeCommandTests(unittest.TestCase):
    def test_the_command_prints_every_round_and_the_kill_signal(self) -> None:
        with written(cascade_log(symbol=1039, killed=False)) as path:
            status, out, _ = run_cli(
                ["trace-cascade", path, "--frame-offset", TARGET_OFFSET]
            )

        self.assertEqual(status, 0)
        self.assertIn("round 4", out)
        self.assertIn("kill: NO", out)
        self.assertIn("net 8.000 <= bestcost 8.000 ?  YES", out)
        self.assertIn("piece left memory-resident", out)

    def test_the_kill_flag_prints_one_line(self) -> None:
        with written(cascade_log(symbol=1039, killed=True)) as path:
            status, out, _ = run_cli(
                ["trace-cascade", path, "--frame-offset", TARGET_OFFSET, "--kill"]
            )

        self.assertEqual(status, 0)
        self.assertEqual(out.strip(), "kill: YES build.ilog sym=1039 rounds=4 colors=0")

    def test_a_slot_needs_a_frame_and_the_error_says_the_arithmetic(self) -> None:
        with written(cascade_log(symbol=1039, killed=False)) as path:
            status, _, err = run_cli(["trace-cascade", path, "--slot", "1184"])

        self.assertEqual(status, 2)
        self.assertIn("--frame -1704", err)

    def test_a_slot_and_a_frame_name_the_same_site_as_the_offset(self) -> None:
        with written(cascade_log(symbol=1039, killed=False)) as path:
            status, out, _ = run_cli(
                ["trace-cascade", path, "--slot", "1184", "--frame", "-1704"]
            )

        self.assertEqual(status, 0)
        self.assertIn("frame offset 0xfffffdf8 (-520)", out)

    def test_the_diff_reports_a_renumbered_symbol_and_a_changed_kill(self) -> None:
        with written(cascade_log(symbol=1042, killed=False), name="a.ilog") as base:
            with written(cascade_log(symbol=1039, killed=True), name="b.ilog") as other:
                status, out, _ = run_cli(
                    [
                        "trace-cascade",
                        base,
                        "--against",
                        other,
                        "--frame-offset",
                        TARGET_OFFSET,
                    ]
                )

        self.assertEqual(status, 0)
        self.assertIn("symbol 1042 -> 1039", out)
        self.assertIn("renumbered", out)
        self.assertIn("VERDICT: the kill signal changed", out)

    def test_the_occurrence_table_marks_the_chargeb_payers(self) -> None:
        with written(cascade_log(symbol=1039, killed=False)) as path:
            status, out, _ = run_cli(
                [
                    "trace-cascade",
                    path,
                    "--frame-offset",
                    TARGET_OFFSET,
                    "--occurrences",
                ]
            )

        self.assertEqual(status, 0)
        self.assertIn("o22 o23 w34", out)
        self.assertIn("PAYS", out)
        self.assertIn("store-placement term (L92)", out)

    def test_the_reference_object_names_the_colours_it_never_uses(self) -> None:
        """WB-69: four stages fought a barrier the ROM's own rows deny."""

        dump = fake_dump(assemble(ROM_BODY, symbol=SYMBOL))
        with written(
            cascade_log(symbol=1039, killed=False), objects=("target.o",)
        ) as path:
            reference = str(Path(path).with_name("target.o"))
            with mock.patch("decomp_workbench.row_source.dump_object", dump):
                status, out, _ = run_cli(
                    [
                        "trace-cascade",
                        path,
                        "--frame-offset",
                        TARGET_OFFSET,
                        "--rom",
                        reference,
                    ]
                )

        self.assertEqual(status, 0)
        self.assertIn("float colours the reference uses:", out)
        # The reference touches $f0 and $f12 only, so $f14/$f16/$f18 -- the
        # cheapest-tie set at the final round -- are free at its own decision.
        self.assertIn("never uses: c25/$f2 c27/$f14 c28/$f16 c29/$f18", out)
        self.assertIn("cheapest-tie colours the reference never uses", out)
        self.assertIn("cannot have been blocked by those colours", out)
        self.assertIn("occupancy over the named rows", out)

    def test_the_screen_line_carries_stores_apart_from_loads(self) -> None:
        """WB-78: the store count separated the kill from the relocation."""

        dump = fake_dump(assemble(CANDIDATE_BODY, symbol=SYMBOL))
        with written(
            cascade_log(symbol=1039, killed=False), objects=("candidate.o",)
        ) as path:
            candidate = str(Path(path).with_name("candidate.o"))
            with mock.patch("decomp_workbench.row_source.dump_object", dump):
                status, out, _ = run_cli(
                    [
                        "trace-cascade",
                        path,
                        "--frame-offset",
                        TARGET_OFFSET,
                        "--object",
                        candidate,
                        "--slot",
                        "1184",
                    ]
                )

        self.assertEqual(status, 0)
        self.assertIn("ld1184=2 st1184=1", out)

    def test_json_carries_the_schema_and_the_rounds(self) -> None:
        with written(cascade_log(symbol=1039, killed=False)) as path:
            status, out, _ = run_cli(
                ["trace-cascade", path, "--frame-offset", TARGET_OFFSET, "--json"]
            )

        self.assertEqual(status, 0)
        payload = json.loads(out)
        self.assertEqual(payload["schema"], "decomp-workbench-cascade-v1")
        self.assertEqual(len(payload["rounds"]), 4)
        self.assertEqual(payload["rounds"][3]["resolved_register"], "$f14")
        self.assertFalse(payload["killed"])

    def test_a_missing_site_reports_json_rather_than_bare_text(self) -> None:
        with written(cascade_log(symbol=1039, killed=False)) as path:
            status, out, _ = run_cli(
                ["trace-cascade", path, "--frame-offset", "0xfffffd00", "--json"]
            )

        self.assertEqual(status, 2)
        payload = json.loads(out)
        self.assertEqual(payload["schema"], "decomp-workbench-error-v1")
        self.assertIn("NOT a kill", payload["error"]["message"])

    def test_the_grammar_is_printable_without_a_log(self) -> None:
        """The dependency is documented at the point of use, not only in docs."""

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                main(["trace-cascade", "--grammar"])

        self.assertEqual(raised.exception.code, 0)
        out = stdout.getvalue()
        self.assertIn("savedetail", out)
        self.assertIn("CAMPAIGN-LOCAL", out)
        self.assertIn("p1-decision-arithmetic", out)

    def test_the_order_command_prints_the_ties(self) -> None:
        with written(tie_log()) as path:
            status, out, _ = run_cli(["trace-order", path, "--class", "2"])

        self.assertEqual(status, 0)
        self.assertIn("colour order:", out)
        self.assertIn("ASCENDING web number", out)
        self.assertIn("pos1/w255, pos6/w260", out)

    def test_the_blocks_command_names_an_empty_intersection(self) -> None:
        with written(cascade_log(symbol=1039, killed=False)) as path:
            status, out, _ = run_cli(
                ["trace-blocks", path, "--web", "255", "--web", "3059"]
            )

        self.assertEqual(status, 0)
        self.assertIn("intersection: EMPTY", out)

    def test_the_shipped_example_logs_are_the_fixture(self) -> None:
        """The documented transcript and the tested fixture are one log.

        `docs/cdx-cascade.md` quotes real output of these files. If the
        generator here drifts from the checked-in copy, the page still passes
        its own transcript check while documenting a log nobody tests.
        """

        traces = Path(__file__).resolve().parents[1] / "examples" / "traces"
        self.assertEqual(
            (traces / "cascade.log").read_text(encoding="utf-8"), tie_log()
        )
        self.assertEqual(
            (traces / "cascade-killed.log").read_text(encoding="utf-8"),
            cascade_log(symbol=1035, killed=True),
        )

    def test_the_grouped_spelling_reaches_the_same_command(self) -> None:
        with written(cascade_log(symbol=1039, killed=False)) as path:
            status, out, _ = run_cli(
                ["trace", "cascade", path, "--frame-offset", TARGET_OFFSET, "--kill"]
            )

        self.assertEqual(status, 0)
        self.assertIn("kill: NO", out)


if __name__ == "__main__":
    unittest.main()
