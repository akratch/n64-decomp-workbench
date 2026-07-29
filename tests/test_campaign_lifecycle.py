"""The campaign runner owns the processes it starts.

A leftover parallel compiler job outlived its campaign in the field and
degraded two later runs. Compilers therefore run in their own process group
so the campaign can end the wrapper and everything the wrapper spawned.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from decomp_workbench import campaign
from decomp_workbench.campaign import (
    CompilerTimeoutError,
    process_group_arguments,
    run_compiler,
    terminate_running_compilers,
)

# A wrapper that starts another tool and then keeps working, like a compiler
# driver that spawns an assembler or a parallel search job.
SLOW_COMPILER = """\
import pathlib
import subprocess
import sys
import time

child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
pathlib.Path(sys.argv[1]).write_text(f"{child.pid}\\n", encoding="utf-8")
time.sleep(30)
"""

# A wrapper that traps the polite signal, as build drivers with their own
# cleanup handlers do.
STUBBORN_COMPILER = """\
import pathlib
import signal
import sys
import time

signal.signal(signal.SIGTERM, signal.SIG_IGN)
pathlib.Path(sys.argv[1]).write_text("ready\\n", encoding="utf-8")
time.sleep(30)
"""


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_until(predicate: Callable[[], bool], timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


class ProcessLifecycleTests(unittest.TestCase):
    def test_process_group_arguments_are_platform_appropriate(self) -> None:
        arguments = process_group_arguments()
        if os.name != "posix":
            self.assertNotIn("start_new_session", arguments)
            return
        if sys.version_info >= (3, 11):
            # Own process group, same session: the compiler keeps the
            # controlling terminal instead of being detached from it.
            self.assertEqual(arguments, {"process_group": 0})
        else:
            self.assertEqual(arguments, {"start_new_session": True})

    def test_a_compiler_that_ignores_sigterm_is_still_ended(self) -> None:
        if os.name != "posix":
            self.skipTest("signal escalation is POSIX-specific")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            compiler = root / "stubborn.py"
            compiler.write_text(STUBBORN_COMPILER, encoding="utf-8")
            ready = root / "ready"
            completed: list[subprocess.CompletedProcess[str]] = []

            def run() -> None:
                completed.append(
                    run_compiler(
                        [sys.executable, str(compiler), str(ready)],
                        environment={},
                        compile_cwd=root,
                    )
                )

            worker = threading.Thread(target=run)
            worker.start()
            try:
                self.assertTrue(wait_until(ready.is_file))
                start = time.monotonic()
                terminate_running_compilers()
                worker.join(timeout=20)
                elapsed = time.monotonic() - start
            finally:
                terminate_running_compilers()
                worker.join(timeout=20)
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(completed), 1)
            # Terminated by the escalation, not by the ignored polite signal.
            self.assertEqual(completed[0].returncode, -signal.SIGKILL)
            self.assertLess(elapsed, 15)

    def test_compilers_run_in_their_own_group(self) -> None:
        if os.name != "posix":
            self.skipTest("process groups are POSIX-specific")
        completed = run_compiler(
            [sys.executable, "-c", "import os; print(os.getpgrp())"],
            environment={},
            compile_cwd=Path.cwd(),
        )
        self.assertEqual(completed.returncode, 0)
        self.assertNotEqual(int(completed.stdout.strip()), os.getpgrp())

    def test_terminating_the_campaign_ends_spawned_tools(self) -> None:
        if os.name != "posix":
            self.skipTest("process-group termination is POSIX-specific")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            compiler = root / "slow_compiler.py"
            compiler.write_text(SLOW_COMPILER, encoding="utf-8")
            child_pid_file = root / "child.pid"
            completed: list[subprocess.CompletedProcess[str]] = []

            def run() -> None:
                completed.append(
                    run_compiler(
                        [sys.executable, str(compiler), str(child_pid_file)],
                        environment={},
                        compile_cwd=root,
                    )
                )

            worker = threading.Thread(target=run)
            worker.start()
            try:
                self.assertTrue(
                    wait_until(lambda: child_pid_file.is_file()),
                    "the fake compiler never started its child",
                )
                child_pid = int(child_pid_file.read_text(encoding="utf-8").strip())
                self.assertTrue(is_running(child_pid))
                terminate_running_compilers()
                worker.join(timeout=15)
            finally:
                terminate_running_compilers()
                worker.join(timeout=15)
            self.assertFalse(worker.is_alive())
            self.assertEqual(len(completed), 1)
            self.assertNotEqual(completed[0].returncode, 0)
            self.assertTrue(
                wait_until(lambda: not is_running(child_pid)),
                "a tool spawned by the compiler outlived the campaign",
            )

    def test_timeout_ends_the_compiler_and_every_spawned_tool(self) -> None:
        if os.name != "posix":
            self.skipTest("process-group termination is POSIX-specific")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            compiler = root / "slow_compiler.py"
            compiler.write_text(SLOW_COMPILER, encoding="utf-8")
            child_pid_file = root / "child.pid"

            with self.assertRaisesRegex(
                CompilerTimeoutError, r"--timeout=0\.5 seconds"
            ):
                run_compiler(
                    [sys.executable, str(compiler), str(child_pid_file)],
                    environment={},
                    compile_cwd=root,
                    timeout=0.5,
                )

            self.assertTrue(child_pid_file.is_file())
            child_pid = int(child_pid_file.read_text(encoding="utf-8").strip())
            self.assertTrue(
                wait_until(lambda: not is_running(child_pid)),
                "a tool spawned by a timed-out compiler outlived the command",
            )


class CampaignOwnershipTests(unittest.TestCase):
    def test_a_failing_campaign_terminates_running_compilers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target.o"
            target.write_bytes(b"target")
            source = root / "candidate.c"
            source.write_text("int candidate;\n", encoding="utf-8")
            objdump = root / "objdump"
            objdump.write_text(
                "#!/usr/bin/env python3\n"
                "print('00000000 <demo>:')\n"
                "print('   0: 03e00008  jr $ra')\n"
                "print('   4: 00000000  nop')\n",
                encoding="utf-8",
            )
            objdump.chmod(0o755)
            calls: list[str] = []
            with (
                mock.patch.object(
                    campaign,
                    "_compile_candidate",
                    side_effect=KeyboardInterrupt,
                ),
                mock.patch.object(
                    campaign,
                    "terminate_running_compilers",
                    side_effect=lambda: calls.append("terminated"),
                ),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    campaign.run_campaign(
                        [source],
                        target=target,
                        template=f"{sys.executable} {{source}} {{output}}",
                        cache_dir=root / "cache",
                        objdump=str(objdump),
                        symbol="demo",
                    )
            self.assertEqual(calls, ["terminated"])


if __name__ == "__main__":
    unittest.main()
