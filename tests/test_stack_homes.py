"""Synthetic ownership records only; no compiler or game bytes are embedded."""

from __future__ import annotations

import struct
import unittest

from decomp_workbench.instrument_ugen_owners import UGEN_SHA256
from decomp_workbench.stack_homes import parse_home_trace, stack_home_report
from decomp_workbench.ucode import OPCODE_NAMES


def fixture(*, reuse: bool = False) -> tuple[str, bytes, bytes]:
    ent = (OPCODE_NAMES.index("ent") << 24, 0, 0, 0)
    store_a = (
        (OPCODE_NAMES.index("str") << 24) | (1 << 21),
        4,
        4,
        (-236) & 0xFFFFFFFF,
    )
    records = [ent, store_a]
    if reuse:
        records.append(
            (
                (OPCODE_NAMES.index("str") << 24) | (1 << 21),
                4,
                4,
                (-232) & 0xFFFFFFFF,
            )
        )
    ucode = struct.pack(
        ">" + "I" * sum(map(len, records)), *(w for r in records for w in r)
    )
    rows = []
    for index, record in enumerate(records):
        if index == 1:
            rows.append(
                "DKWB-HOME-SPILL write=1 proc=0 slot=4096 index=1 "
                "offset=-236 size=4 enabled=1"
            )
        padded = list(record) + [0] * (8 - len(record))
        rows.append(
            "DKWB-HOME-WRITE write={} proc=0 {}".format(
                index, " ".join(f"w{i}={word}" for i, word in enumerate(padded))
            )
        )
    node = 8192
    owner_rows = []
    serial = 0

    def owner(kind: str, fields: dict[str, int]) -> None:
        nonlocal serial
        serial += 1
        owner_rows.append(
            f"DKWB-OWNER-{kind} serial={serial} "
            + " ".join(f"{key}={value}" for key, value in fields.items())
        )

    owner_rows.append(f"DKWB-OWNER-PROFILE version=1 source_sha256={UGEN_SHA256}")
    owner(
        "READ",
        {
            "ptr": 128,
            "node": 0,
            "id": 0,
            **dict(zip((f"w{i}" for i in range(8)), (*ent, 0, 0, 0, 0), strict=True)),
        },
    )
    owner(
        "READ",
        {
            "ptr": 128,
            "node": 0,
            "id": 0,
            **dict(
                zip(
                    (f"w{i}" for i in range(8)),
                    (*store_a, 0xDEADBEEF, 0, 0, 0),
                    strict=True,
                )
            ),
        },
    )
    owner("NEW", {"node": node, "id": 1})
    owner(
        "INPUT",
        {
            "ptr": 128,
            "node": node,
            "id": 1,
            **dict(
                zip((f"w{i}" for i in range(8)), (*store_a, 0, 0, 0, 0), strict=True)
            ),
        },
    )
    owner(
        "BUILD",
        {
            "ptr": node + 32,
            "node": node,
            "id": 1,
            **dict(
                zip((f"w{i}" for i in range(8)), (*store_a, 0, 0, 0, 0), strict=True)
            ),
        },
    )
    first_build_serial = serial
    home_rows = [
        f"DKWB-HOME-FRAME owner_serial={first_build_serial} node={node} "
        "virtual=-236 frame=320 mode=0 result=84",
        f"DKWB-HOME-MEM owner_serial={first_build_serial} node={node} "
        "epoch=1 emit=1 op=42 reg=3 base=29 displacement=84 extra=0",
    ]
    # The producer observes the frame after BUILD and before OUTPUT.
    owner_rows.extend(home_rows)
    if reuse:
        second = records[2]
        owner(
            "READ",
            {
                "ptr": 128,
                "node": 0,
                "id": 0,
                **dict(
                    zip((f"w{i}" for i in range(8)), (*second, 0, 0, 0, 0), strict=True)
                ),
            },
        )
        owner("NEW", {"node": node, "id": 2})
        owner(
            "INPUT",
            {
                "ptr": 128,
                "node": node,
                "id": 2,
                **dict(
                    zip((f"w{i}" for i in range(8)), (*second, 0, 0, 0, 0), strict=True)
                ),
            },
        )
        owner(
            "BUILD",
            {
                "ptr": node + 32,
                "node": node,
                "id": 2,
                **dict(
                    zip((f"w{i}" for i in range(8)), (*second, 0, 0, 0, 0), strict=True)
                ),
            },
        )
    owner("OUTPUT", {"epoch": 1, "forward": 1, "backward": 0})
    owner("CONCAT", {})
    # The output bytes are synthetic and encode exactly the event above.
    binasm = struct.pack(">4I", 0, 0x170000 | (42 << 1), (3 << 25) | (29 << 18), 84)
    return "\n".join([*rows, *owner_rows]) + "\n", ucode, binasm


class StackHomeTests(unittest.TestCase):
    def test_exact_store_chain_survives_pointer_reuse(self) -> None:
        text, ucode, binasm = fixture(reuse=True)
        report = stack_home_report(text, ucode=ucode, binasm=binasm)
        self.assertEqual(len(report["chains"]), 1)
        self.assertEqual(report["chains"][0]["read_index"], 1)
        self.assertEqual(report["chains"][0]["node_generation"], 3)
        self.assertEqual(report["chains"][0]["slot"]["offset"], -236)
        self.assertTrue(
            any("No source-expression identity" in item for item in report["limits"])
        )

    def test_missing_writer_rejects(self) -> None:
        text, ucode, binasm = fixture()
        text = "\n".join(
            line for line in text.splitlines() if "HOME-WRITE write=1 " not in line
        )
        with self.assertRaisesRegex(ValueError, "writer/retained record count"):
            stack_home_report(text, ucode=ucode, binasm=binasm)

    def test_wrong_procedure_rejects(self) -> None:
        text, ucode, binasm = fixture()
        text = text.replace("HOME-SPILL write=1 proc=0", "HOME-SPILL write=1 proc=1")
        with self.assertRaisesRegex(ValueError, "procedure identity"):
            stack_home_report(text, ucode=ucode, binasm=binasm)

    def test_reader_before_matching_writer_rejects(self) -> None:
        text, ucode, binasm = fixture()
        lines = text.splitlines()
        writer = next(
            i for i, line in enumerate(lines) if "HOME-WRITE write=1 " in line
        )
        read = next(i for i, line in enumerate(lines) if "OWNER-READ serial=2 " in line)
        line = lines.pop(writer)
        lines.insert(read + 1, line)
        with self.assertRaisesRegex(ValueError, "reader precedes matching writer"):
            stack_home_report("\n".join(lines) + "\n", ucode=ucode, binasm=binasm)

    def test_node_used_before_build_rejects(self) -> None:
        text, ucode, binasm = fixture()
        lines = text.splitlines()
        home = [line for line in lines if "HOME-FRAME " in line or "HOME-MEM " in line]
        lines = [
            line
            for line in lines
            if "HOME-FRAME " not in line and "HOME-MEM " not in line
        ]
        home = [line.replace("owner_serial=5", "owner_serial=4") for line in home]
        build = next(i for i, line in enumerate(lines) if "OWNER-BUILD " in line)
        lines[build:build] = home
        with self.assertRaisesRegex(ValueError, "used before tree copy"):
            stack_home_report("\n".join(lines) + "\n", ucode=ucode, binasm=binasm)

    def test_altered_addend_rejects_against_emitted_bytes(self) -> None:
        text, ucode, binasm = fixture()
        text = text.replace("displacement=84", "displacement=85")
        with self.assertRaisesRegex(ValueError, "emitter differs from retained binASM"):
            stack_home_report(text, ucode=ucode, binasm=binasm)

    def test_duplicate_emitter_rejects(self) -> None:
        text, ucode, binasm = fixture()
        lines = text.splitlines()
        mem = next(line for line in lines if "HOME-MEM " in line)
        position = next(i for i, line in enumerate(lines) if "HOME-MEM " in line)
        lines.insert(position + 1, mem)
        with self.assertRaisesRegex(ValueError, "duplicate memory emitter"):
            stack_home_report("\n".join(lines) + "\n", ucode=ucode, binasm=binasm)

    def test_truncated_record_rejects(self) -> None:
        text, ucode, binasm = fixture()
        with self.assertRaisesRegex(ValueError, "complete 32-bit words"):
            stack_home_report(text, ucode=ucode[:-1], binasm=binasm)

    def test_record_count_mismatch_rejects(self) -> None:
        text, ucode, binasm = fixture()
        fields = " ".join(f"w{i}=0" for i in range(8))
        text += f"DKWB-HOME-WRITE write=2 proc=0 {fields}\n"
        with self.assertRaisesRegex(ValueError, "writer/retained record count"):
            stack_home_report(text, ucode=ucode, binasm=binasm)

    def test_duplicate_frame_identity_rejects(self) -> None:
        text, ucode, binasm = fixture()
        frame = next(line for line in text.splitlines() if "HOME-FRAME " in line)
        text = text.replace(frame, frame + "\n" + frame)
        with self.assertRaisesRegex(ValueError, "duplicate frame identity"):
            stack_home_report(text, ucode=ucode, binasm=binasm)

    def test_enabled_preamble_spill_rejects_but_writer_is_allowed(self) -> None:
        parse_home_trace(
            "DKWB-HOME-WRITE write=0 proc=-1 " + " ".join(f"w{i}=0" for i in range(8))
        )
        spill = (
            "DKWB-HOME-SPILL write=0 proc=-1 slot=1 index=0 offset=0 size=4 enabled=1"
        )
        with self.assertRaisesRegex(ValueError, "no procedure identity"):
            parse_home_trace(spill)

    def test_spill_after_writer_rejects(self) -> None:
        text, ucode, binasm = fixture()
        lines = text.splitlines()
        spill = next(i for i, line in enumerate(lines) if "HOME-SPILL " in line)
        line = lines.pop(spill)
        writer = next(
            i for i, item in enumerate(lines) if "HOME-WRITE write=1 " in item
        )
        lines.insert(writer + 1, line)
        with self.assertRaisesRegex(ValueError, "spill follows matching writer"):
            stack_home_report("\n".join(lines) + "\n", ucode=ucode, binasm=binasm)

    def test_mem_before_frame_rejects(self) -> None:
        text, ucode, binasm = fixture()
        lines = text.splitlines()
        frame = next(i for i, line in enumerate(lines) if "HOME-FRAME " in line)
        mem = next(i for i, line in enumerate(lines) if "HOME-MEM " in line)
        lines[frame], lines[mem] = lines[mem], lines[frame]
        with self.assertRaisesRegex(ValueError, "precedes matching frame"):
            stack_home_report("\n".join(lines) + "\n", ucode=ucode, binasm=binasm)

    def test_stale_owner_serial_rejects(self) -> None:
        text, ucode, binasm = fixture()
        text = text.replace("owner_serial=5 node=8192", "owner_serial=4 node=8192")
        with self.assertRaisesRegex(ValueError, "latest preceding owner"):
            stack_home_report(text, ucode=ucode, binasm=binasm)

    def test_mem_after_output_rejects(self) -> None:
        text, ucode, binasm = fixture()
        text = text.replace("owner_serial=5 node=8192", "owner_serial=6 node=8192")
        lines = text.splitlines()
        home = [line for line in lines if "HOME-FRAME " in line or "HOME-MEM " in line]
        lines = [
            line
            for line in lines
            if "HOME-FRAME " not in line and "HOME-MEM " not in line
        ]
        output = next(i for i, item in enumerate(lines) if "OWNER-OUTPUT " in item)
        lines[output + 1 : output + 1] = home
        with self.assertRaisesRegex(ValueError, "follows matching output"):
            stack_home_report("\n".join(lines) + "\n", ucode=ucode, binasm=binasm)

    def test_mem_after_concat_rejects(self) -> None:
        text, ucode, binasm = fixture()
        text = text.replace("owner_serial=5 node=8192", "owner_serial=7 node=8192")
        lines = text.splitlines()
        home = [line for line in lines if "HOME-FRAME " in line or "HOME-MEM " in line]
        lines = [
            line
            for line in lines
            if "HOME-FRAME " not in line and "HOME-MEM " not in line
        ]
        concat = next(i for i, item in enumerate(lines) if "OWNER-CONCAT " in item)
        lines[concat + 1 : concat + 1] = home
        with self.assertRaisesRegex(ValueError, "follows final CONCAT"):
            stack_home_report("\n".join(lines) + "\n", ucode=ucode, binasm=binasm)

    def test_byte_field_bounds(self) -> None:
        text, ucode, binasm = fixture()
        with self.assertRaisesRegex(ValueError, "byte field"):
            stack_home_report(
                text.replace("enabled=1", "enabled=256"), ucode=ucode, binasm=binasm
            )
        with self.assertRaisesRegex(ValueError, "byte field"):
            stack_home_report(
                text.replace("mode=0", "mode=256"), ucode=ucode, binasm=binasm
            )
        parse_home_trace(text.replace("mode=0", "mode=7"))


if __name__ == "__main__":
    unittest.main()
