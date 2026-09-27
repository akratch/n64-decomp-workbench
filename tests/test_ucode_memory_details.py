"""Synthetic unequal width/displacement controls for memory-op formatting."""

import struct
import unittest

from decomp_workbench.ucode import OPCODE_NAMES, parse_ucode


class MemoryDetailsTests(unittest.TestCase):
    def test_length_and_signed_displacement_are_not_swapped(self) -> None:
        for name in ("lod", "str"):
            for mtype in (1, 3, 4):
                for displacement in (16, -16):
                    with self.subTest(name=name, mtype=mtype, offset=displacement):
                        header = OPCODE_NAMES.index(name) << 24 | mtype << 21 | 6 << 16
                        stream = struct.pack(
                            ">IIII", header, 7, 4, displacement & 0xFFFFFFFF
                        )
                        record = parse_ucode(stream)[0]
                        self.assertIn(f"offset={displacement} length=4", record.detail)
                        self.assertIn("block=7", record.detail)


if __name__ == "__main__":
    unittest.main()
