"""Project/scratch truth and the evidence-gated call-contract probe."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from decomp_workbench.compare import compare_instructions
from decomp_workbench.context_truth import (
    build_truth_stack,
    call_contract_hypotheses,
)
from decomp_workbench.objdump import parse_disassembly
from decomp_workbench.scratch_check import ScratchPackage
from decomp_workbench.view import build_view

TARGET = """\
0: 27bdffe0 addiu $sp,$sp,-32
4: 00000000 nop
8: 00000000 nop
c: 00000000 nop
10: 00000000 nop
14: 0c000000 jal 0 <helper>
18: 00000000 nop
1c: 8c430000 lw $v1,0($v0)
20: 00631821 addu $v1,$v1,$v1
24: ac430004 sw $v1,4($v0)
"""

CANDIDATE = """\
0: 27bdffe0 addiu $sp,$sp,-32
4: 00000000 nop
8: 00000000 nop
c: 00000000 nop
10: 00000000 nop
14: 0c000000 jal 0 <helper>
18: 00000000 nop
1c: 8c420000 lw $v0,0($v0)
20: 00421021 addu $v0,$v0,$v0
24: ac420004 sw $v0,4($v0)
"""


class ContextTruthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = parse_disassembly(TARGET)
        self.candidate = parse_disassembly(CANDIDATE)
        self.scratch = compare_instructions(
            self.target,
            self.candidate,
            target_name="target",
            candidate_name="scratch",
            symbol="demo",
        )
        self.project = compare_instructions(
            self.target,
            self.target,
            target_name="target",
            candidate_name="project",
            symbol="demo",
        )
        self.view = build_view(
            self.target,
            self.candidate,
            target_name="target",
            candidate_name="scratch",
            symbol="demo",
        )
        self.package = ScratchPackage(
            path=Path("scratch.zip"),
            kind="decomp.me-export",
            files={
                "ctx.c": b"void helper();\n",
                "code.c": b"int demo(void) { helper(); return 0; }\n",
            },
            metadata={},
            checksums_valid=None,
        )

    def test_project_exact_and_scratch_mismatch_are_context_only(self) -> None:
        report = build_truth_stack(
            external_score={"score": 3, "max_score": 1000},
            scratch=self.scratch,
            project=self.project,
            hypotheses=[],
        )
        self.assertEqual(report["classification"], "context-only")
        self.assertEqual(report["layers"][1]["status"], "FAIL")
        self.assertEqual(report["layers"][2]["status"], "PASS")

    def test_measured_v0_v1_tail_web_routes_to_one_int_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_source = Path(temporary) / "module.c"
            project_source.write_text(
                "int demo(void) { helper(); return 0; }\n", encoding="utf-8"
            )
            hypotheses = call_contract_hypotheses(
                package=self.package,
                scratch=self.scratch,
                view=self.view,
                project=self.project,
                project_source=project_source,
                frontend={"language": "C", "frontend": "cfe C"},
            )
        self.assertEqual(len(hypotheses), 1)
        self.assertEqual(hypotheses[0]["callee"], "helper")
        self.assertIn("int helper();", hypotheses[0]["action"])
        self.assertEqual(hypotheses[0]["project_return_category"], "not-visible")

    def test_cpp_suppresses_implicit_int_advice(self) -> None:
        hypotheses = call_contract_hypotheses(
            package=self.package,
            scratch=self.scratch,
            view=self.view,
            project=self.project,
            project_source=None,
            frontend={"language": "C++", "frontend": "EDG C++"},
        )
        self.assertEqual(hypotheses, [])

    def test_non_c89_dialect_suppresses_implicit_int_advice(self) -> None:
        hypotheses = call_contract_hypotheses(
            package=self.package,
            scratch=self.scratch,
            view=self.view,
            project=self.project,
            project_source=None,
            frontend={"language": "C99", "frontend": "modern C"},
        )
        self.assertEqual(hypotheses, [])

    def test_generic_post_call_register_swap_without_void_decl_is_suppressed(
        self,
    ) -> None:
        package = ScratchPackage(
            path=Path("scratch.zip"),
            kind="decomp.me-export",
            files={"ctx.c": b"int helper();\n", "code.c": b"int demo(void);\n"},
            metadata={},
            checksums_valid=None,
        )
        hypotheses = call_contract_hypotheses(
            package=package,
            scratch=self.scratch,
            view=self.view,
            project=self.project,
            project_source=None,
            frontend={"language": "C", "frontend": "cfe C"},
        )
        self.assertEqual(hypotheses, [])


if __name__ == "__main__":
    unittest.main()
