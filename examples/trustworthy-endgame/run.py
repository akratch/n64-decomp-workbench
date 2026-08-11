#!/usr/bin/env python3
"""Asset-free scratch → controlled campaign → finish → package walkthrough."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def run(*arguments: str) -> dict[str, Any]:
    process = subprocess.run(
        [sys.executable, "-m", "decomp_workbench", *arguments, "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            f"command failed ({process.returncode}): {' '.join(arguments)}\n"
            f"{process.stdout}{process.stderr}"
        )
    value = json.loads(process.stdout)
    if not isinstance(value, dict):
        raise RuntimeError("command returned a non-object JSON document")
    return value


def main() -> int:
    scratch = run(
        "check-scratch",
        str(ROOT / "examples/fixtures/decompme-export"),
        "--view",
    )
    if [layer["id"] for layer in scratch["truth_layers"]] != [
        "site-metadata",
        "scratch-object",
        "project-object",
    ]:
        raise RuntimeError("scratch truth stack is incomplete")

    with tempfile.TemporaryDirectory(prefix="decomp-workbench-endgame-") as temp:
        root = Path(temp)
        baseline = root / "baseline.c"
        candidate = root / "candidate.c"
        target = root / "target.s"
        context = root / "ctx.c"
        compiler = root / "compile.py"
        objdump = root / "objdump"
        experiment = root / "experiment.json"
        baseline.write_text("int demo(void) { return 0; }\n", encoding="utf-8")
        candidate.write_text("int demo(void) { return 1; }\n", encoding="utf-8")
        target.write_text("jr $ra\n nop\n", encoding="utf-8")
        context.write_text("typedef int s32;\n", encoding="utf-8")
        compiler.write_text(
            "import pathlib, sys\n"
            "pathlib.Path(sys.argv[2]).write_bytes("
            "pathlib.Path(sys.argv[1]).read_bytes())\n",
            encoding="utf-8",
        )
        objdump.write_text(
            "#!/usr/bin/env python3\n"
            "print('00000000 <demo>:')\n"
            "print('   0: 03e00008  jr $ra')\n"
            "print('   4: 00000000  nop')\n",
            encoding="utf-8",
        )
        objdump.chmod(0o755)
        experiment.write_text(
            json.dumps(
                {
                    "schema": "decomp-workbench-experiment-v2",
                    "family": "synthetic-endgame",
                    "baseline": "baseline.c",
                    "parameters": {"return": [1]},
                    "candidates": [
                        {
                            "source": "candidate.c",
                            "parameters": {"return": 1},
                        }
                    ],
                    "signals": [
                        {
                            "id": "return-row",
                            "kind": "target-rows-exact",
                            "rows": [1],
                            "required": True,
                        }
                    ],
                    "controls": [
                        {
                            "id": "known-baseline",
                            "candidate": "baseline.c",
                            "expect": {
                                "words": 0,
                                "signals": {"return-row": "PASS"},
                            },
                        }
                    ],
                    "coverage": {"method": "exhaustive", "excluded": 0},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        run("experiment", "validate", str(experiment))
        campaign = run(
            "campaign",
            str(target),
            str(candidate),
            "--compile-command",
            f"{sys.executable} {compiler} {{source}} {{output}}",
            "--objdump",
            str(objdump),
            "--symbol",
            "demo",
            "--experiment-manifest",
            str(experiment),
            "--compiler-id",
            "synthetic-c89",
            "--frontend",
            "synthetic-c89",
            "--language",
            "c89",
            "--driver",
            "python-fixture",
            "--backend",
            "synthetic-final-object",
            "--cache-dir",
            str(root / "cache"),
            "--state-dir",
            str(root / "state"),
        )
        manifest = Path(str(campaign["manifest"]))
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
        if manifest_payload["identity_inputs"]["compile"].get("envelope") != {
            "backend": "synthetic-final-object",
            "compiler_id": "synthetic-c89",
            "driver": "python-fixture",
            "frontend": "synthetic-c89",
            "language": "c89",
        }:
            raise RuntimeError("compiler envelope is incomplete")
        status = run("campaign", "status", str(manifest))
        if status["controls"]["status"] != "PASS":
            raise RuntimeError("control preflight did not pass")
        if status["conclusion_label"] != "exhaustive-over-declared-space":
            raise RuntimeError("coverage conclusion is not exhaustive")

        finish_path = root / "finish.json"
        finish = run(
            "campaign",
            "finish",
            str(manifest),
            "--output",
            str(finish_path),
        )
        if not finish["ready"]:
            raise RuntimeError("fresh finish receipt did not pass")

        bundle = root / "scratch-bundle"
        run(
            "campaign",
            "package",
            str(manifest),
            "--finish-receipt",
            str(finish_path),
            "--output",
            str(bundle),
            "--target-assembly",
            str(target),
            "--context",
            str(context),
            "--platform",
            "n64",
            "--compiler",
            "synthetic-c89",
            "--compiler-id",
            "synthetic-c89",
            "--language",
            "c89",
            "--diff-label",
            "demo",
        )
        if not (bundle / "SHA256SUMS").is_file():
            raise RuntimeError("scratch bundle was not created")

        summary = {
            "schema": "decomp-workbench-trustworthy-endgame-walkthrough-v1",
            "scratch_truth": scratch["truth"]["classification"],
            "controls": status["controls"]["status"],
            "coverage": status["conclusion_label"],
            "finish": finish["status"],
            "package": "PASS",
            "compiler_envelope": "PASS",
            "network_used": False,
            "proprietary_assets_used": False,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
