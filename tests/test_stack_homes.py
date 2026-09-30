"""Synthetic ownership records only; no compiler or game bytes are embedded."""

from __future__ import annotations

import struct
import unittest

from decomp_workbench.instrument_ugen_owners import UGEN_SHA256
from decomp_workbench.stack_homes import stack_home_report
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
        padded = list(record) + [0] * (8 - len(record))
        rows.append(
            "DKWB-HOME-WRITE write={} proc=0 {}".format(
                index, " ".join(f"w{i}={word}" for i, word in enumerate(padded))
            )
        )
    rows.append(
        "DKWB-HOME-SPILL write=1 proc=0 slot=4096 index=1 offset=-236 size=4 enabled=1"
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
    home_rows = [
        f"DKWB-HOME-FRAME owner_serial={first_build_serial} node={node} "
        "virtual=-236 frame=320 mode=0 result=84",
        f"DKWB-HOME-MEM owner_serial={first_build_serial} node={node} "
        "epoch=1 emit=1 op=42 reg=3 base=29 displacement=84 extra=0",
    ]
    # The output bytes are synthetic and encode exactly the event above.
    binasm = struct.pack(">4I", 0, 0x170000 | (42 << 1), (3 << 25) | (29 << 18), 84)
    return "\n".join([*rows, *owner_rows, *home_rows]) + "\n", ucode, binasm


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
        text = text.replace("owner_serial=5 node=8192", "owner_serial=4 node=8192")
        with self.assertRaisesRegex(ValueError, "used before tree copy"):
            stack_home_report(text, ucode=ucode, binasm=binasm)

    def test_altered_addend_rejects_against_emitted_bytes(self) -> None:
        text, ucode, binasm = fixture()
        text = text.replace("displacement=84", "displacement=85")
        with self.assertRaisesRegex(ValueError, "emitter differs from retained binASM"):
            stack_home_report(text, ucode=ucode, binasm=binasm)

    def test_duplicate_emitter_rejects(self) -> None:
        text, ucode, binasm = fixture()
        mem = next(line for line in text.splitlines() if "HOME-MEM " in line)
        text += mem + "\n"
        with self.assertRaisesRegex(ValueError, "duplicate memory emitter"):
            stack_home_report(text, ucode=ucode, binasm=binasm)

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


if __name__ == "__main__":
    unittest.main()
