from __future__ import annotations

# ruff: noqa: E501 -- COPYDEC fixtures intentionally preserve producer lines.
from decomp_workbench.copytrace import copy_decision_report, parse_copy_decisions

BASELINE = """\
CDXW 000001 p0   d2  COPYDEC      tag=pre-reemit stmt=64    lhs=62    rhs=-1    rhsop=00 rhstable=0     rhschain=0   occ=0/0 rhsformed=-1 bbwit=-1 lhscolor=12 rhscolor=-99 lhsframe=ffffffe4 -> COALESCE
CDXW 000002 p0   d2  COPYDEC      tag=pre-reemit stmt=87    lhs=39    rhs=62    rhsop=00 rhstable=0     rhschain=0   occ=0/0 rhsformed=1 bbwit=0 lhscolor=8 rhscolor=12 lhsframe=fffffffa -> TEMPCOPY
"""

CANDIDATE = """\
CDXW 000101 p0   d2  COPYDEC      tag=pre-reemit stmt=46    lhs=44    rhs=11    rhsop=00 rhstable=0     rhschain=0   occ=0/0 rhsformed=1 bbwit=0 lhscolor=-99 rhscolor=5 lhsframe=ffffffe4 -> TEMPCOPY
"""

TIMELINE = """\
CDXW 000201 p0   d2  COPYDEC      tag=pre-makelivranges stmt=26    lhs=23    rhs=25    rhsop=01 rhstable=1465  rhschain=0   occ=0/2 rhsformed=0 bbwit=1 lhscolor=-99 rhscolor=-99 lhsframe=fffffff0 -> COALESCE
CDXW 000202 p0   d2  COPYDEC      tag=post-makelivranges stmt=26    lhs=23    rhs=25    rhsop=01 rhstable=1465  rhschain=0   occ=1/2 rhsformed=1 bbwit=1 lhscolor=-99 rhscolor=0 lhsframe=fffffff0 -> TEMPCOPY
CDXW 000203 p0   d2  COPYDEC      tag=pre-localcolor stmt=26    lhs=23    rhs=25    rhsop=01 rhstable=1465  rhschain=0   occ=1/2 rhsformed=1 bbwit=1 lhscolor=-99 rhscolor=0 lhsframe=fffffff0 -> TEMPCOPY
"""


def test_parse_copy_decisions_signs_stack_home_and_ignores_other_stages() -> None:
    items, malformed = parse_copy_decisions(BASELINE)

    assert malformed == []
    assert len(items) == 2
    assert items[0].lhs_frame == -0x1C
    assert items[0].decision == "COALESCE"
    assert items[1].lhs_frame == -6


def test_copy_decision_diff_aligns_by_stack_home_not_trace_bits() -> None:
    report = copy_decision_report(BASELINE, against=CANDIDATE, proc=0)

    assert report["summary"]["decision_count"] == 2
    assert report["candidate_summary"]["decision_count"] == 1
    assert report["difference_count"] == 2
    changed = report["differences"][0]
    assert changed["alignment_key"] == "proc0:home-0x1c:#0"
    assert "decision" in changed["changed"]
    assert changed["baseline"]["decision"] == "COALESCE"
    assert changed["candidate"]["decision"] == "TEMPCOPY"
    assert "hash-table" in report["warnings"][0]


def test_copy_diff_reports_candidate_stage_evidence_separately() -> None:
    report = copy_decision_report("", against=CANDIDATE, tag="missing", proc=0)

    assert report["summary"]["decision_count"] == 0
    assert report["candidate_summary"]["decision_count"] == 0
    assert report["timeline"]["observed_stages"] == []
    assert report["candidate_timeline"]["observed_stages"] == ["pre-reemit"]


def test_copy_decision_timeline_identifies_directly_bracketed_owner_pass() -> None:
    report = copy_decision_report(TIMELINE, tag="pre-localcolor", proc=0)

    timeline = report["timeline"]
    assert timeline["observed_stages"] == [
        "pre-makelivranges",
        "post-makelivranges",
        "pre-localcolor",
    ]
    assert timeline["decision_transition_count"] == 1
    transition = timeline["transitions"][0]
    assert transition["alignment_key"] == "proc0:home-0x10:#0"
    assert transition["before_decision"] == "COALESCE"
    assert transition["after_decision"] == "TEMPCOPY"
    assert transition["owner_pass"] == "makelivranges"
    assert transition["owner_claim"] == "directly bracketed pass"
