"""What a trace command says when it is handed a pass-boundary stream.

``capture make`` leaves binary Ucode and Binasm boundaries on disk beside the
textual traces, and the two are easy to confuse: the run directory names them
by the compiler's temporary-file names, so neither the extension nor the name
says which is which. Handing one to ``trace-summary`` used to surface a raw
``UnicodeDecodeError`` -- or, for a Binasm stream whose record words happen to
be small integers, to decode "successfully" and report zero events, which is
worse. Every stream here is synthesized by ``tests/phase_streams.py`` from the
published record formats; none comes from any compilation.
"""

from __future__ import annotations

import contextlib
import io
import re
import shlex
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from phase_streams import binasm_record, binasm_stream, ucode_stream

from decomp_workbench.cli import build_parser, main
from decomp_workbench.discovery import rewrite_group_alias
from decomp_workbench.trace import (
    BinaryTraceStreamError,
    classify_trace_bytes,
    parse_trace,
    read_trace_source,
    read_trace_text,
)

TEXT_TRACE = """\
CODEX-UGEN-APPEND line=182 list=10019da4 reg=14
CODEX-UGEN-ALLOC serial=1 line=700 reg=14
"""


class ClassificationTests(unittest.TestCase):
    def test_names_each_pass_boundary_stream(self) -> None:
        self.assertEqual(classify_trace_bytes(ucode_stream()), "ucode")
        self.assertEqual(classify_trace_bytes(binasm_stream()), "binasm")

    def test_text_is_not_a_stream(self) -> None:
        self.assertIsNone(classify_trace_bytes(TEXT_TRACE.encode("utf-8")))


class ReadTraceSourceTests(unittest.TestCase):
    def test_text_passes_through_unchanged(self) -> None:
        source = read_trace_source(TEXT_TRACE.encode("utf-8"))
        self.assertEqual(source.text, TEXT_TRACE)
        self.assertEqual(source.encoding, "utf-8")
        self.assertFalse(source.recovered)
        self.assertEqual(source.notes, ())

    def test_untagged_text_still_passes_through(self) -> None:
        # globalcolor, a71, and scheduler traces share this reader and carry no
        # CODEX/DKWB tag; the tag must never be the gate for accepting text.
        source = read_trace_source(b"p1dec proc=1 web=3 color=c17\n")
        self.assertEqual(source.encoding, "utf-8")
        self.assertEqual(source.notes, ())

    def test_refuses_ucode_by_name(self) -> None:
        with self.assertRaises(BinaryTraceStreamError) as caught:
            read_trace_source(ucode_stream(), name="before-7-ctmoA0r9Qp")
        message = str(caught.exception)
        self.assertEqual(caught.exception.stream_format, "ucode")
        self.assertIn("before-7-ctmoA0r9Qp", message)
        self.assertIn("Ucode", message)
        self.assertIn("record(s)", message)
        self.assertIn("ucode window before-7-ctmoA0r9Qp --at 0", message)
        self.assertIn("docs/compiler-instrumentation.md", message)

    def test_refuses_binasm_by_name(self) -> None:
        with self.assertRaises(BinaryTraceStreamError) as caught:
            read_trace_source(binasm_stream(), name="after-9-ctmc2PdRlS")
        message = str(caught.exception)
        self.assertEqual(caught.exception.stream_format, "binasm")
        self.assertIn("after-9-ctmc2PdRlS", message)
        self.assertIn("16-byte", message)
        self.assertIn("binasm window after-9-ctmc2PdRlS --at 0", message)
        self.assertIn("docs/compiler-instrumentation.md", message)

    def test_refuses_a_stream_that_decodes_as_utf8(self) -> None:
        # A Binasm record's words are small integers, so a stream can decode
        # cleanly and still be a stream. Decoding is not the test; framing is
        # -- this is the case that used to report zero events instead of an
        # error, which is the more expensive of the two failures.
        data = b"".join(
            (
                binasm_record(0, 0x002A0000, 7, 0xA),
                binasm_record(0, 0x00150000, 0, 0),
                binasm_record(0, 0x001C0000, 28, 85),
                binasm_record(0, 0x00170062, 0x040D4000, 0),
            )
        )
        self.assertIsInstance(data.decode("utf-8"), str)
        with self.assertRaises(BinaryTraceStreamError) as caught:
            read_trace_source(data, name="after-13-ctmgtUjPyVL")
        self.assertEqual(caught.exception.stream_format, "binasm")

    def test_recovers_diagnostic_lines_from_a_mixed_file(self) -> None:
        data = TEXT_TRACE.encode("utf-8") + b"\xff\xfe\n" + TEXT_TRACE.encode("utf-8")
        notes: list[str] = []
        text = read_trace_text(data, name="mixed.log", warn=notes.append)
        self.assertEqual(len(parse_trace(text)), 4)
        self.assertEqual(len(notes), 1)
        self.assertIn("mixed.log", notes[0])
        self.assertIn("2 byte(s) were replaced", notes[0])
        self.assertIn("4 diagnostic line(s)", notes[0])

    def test_unframed_binary_names_the_stream_reader_and_tier_two(self) -> None:
        with self.assertRaises(BinaryTraceStreamError) as caught:
            read_trace_source(bytes(range(0xC0, 0xFF)) * 3, name="mystery.bin")
        message = str(caught.exception)
        self.assertIsNone(caught.exception.stream_format)
        self.assertIn("mystery.bin", message)
        self.assertIn("neither Ucode nor Binasm", message)
        # Every command a refusal names has to be one that runs: `--at` is a
        # required argument of the window readers, and there is no
        # `stream window` command to send anyone to.
        self.assertIn("binasm window mystery.bin --at 0 --format binasm", message)
        self.assertIn("docs/compiler-instrumentation.md", message)


class RefusalCommandsRunTests(unittest.TestCase):
    """Every `decomp-workbench ...` a refusal prints has to parse.

    A refusal exists to give a reader their next command, and the two ways
    that fails silently are naming a command that does not exist and omitting
    a required argument. `stream window` was the first and the window
    readers' `--at` was the second, so the message is checked against the
    real parser rather than against a reviewer's memory of the CLI.
    """

    def _quoted_commands(self, message: str) -> list[list[str]]:
        found = [
            shlex.split(text)
            for text in re.findall(r"`decomp-workbench ([^`]+)`", message)
        ]
        self.assertTrue(found, message)
        return found

    def _assert_parses(self, message: str) -> None:
        parser = build_parser()
        for argv in self._quoted_commands(message):
            with self.subTest(argv=argv):
                with contextlib.redirect_stderr(io.StringIO()):
                    parser.parse_args(rewrite_group_alias(argv))

    def test_a_stream_refusal_names_a_command_that_runs(self) -> None:
        for stream, name in (
            (ucode_stream(), "before-7-ctmoA0r9Qp"),
            (binasm_stream(), "after-9-ctmc2PdRlS"),
        ):
            with self.subTest(name=name):
                with self.assertRaises(BinaryTraceStreamError) as caught:
                    read_trace_source(stream, name=name)
                self._assert_parses(str(caught.exception))

    def test_an_unframed_refusal_names_a_command_that_runs(self) -> None:
        with self.assertRaises(BinaryTraceStreamError) as caught:
            read_trace_source(bytes(range(0xC0, 0xFF)) * 3, name="mystery.bin")
        self._assert_parses(str(caught.exception))


class TraceCommandTests(unittest.TestCase):
    def _run(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            status = main(list(argv))
        return status, out.getvalue(), err.getvalue()

    def test_every_trace_command_refuses_a_stream_the_same_way(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "after-9-ctmc2PdRlS"
            path.write_bytes(binasm_stream())
            for command in ("trace-summary", "trace-fifo", "trace-alias"):
                with self.subTest(command=command):
                    status, _, err = self._run(command, str(path))
                    self.assertEqual(status, 2)
                    self.assertIn("Binasm", err)
                    self.assertIn("binasm window", err)
                    self.assertIn("docs/compiler-instrumentation.md", err)

    def test_mixed_file_warns_on_stderr_and_still_reports(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ugen.log"
            path.write_bytes(TEXT_TRACE.encode("utf-8") + b"\xff\n")
            status, out, err = self._run("trace-summary", str(path))
            self.assertEqual(status, 0)
            self.assertIn("events: 2", out)
            self.assertIn("warning:", err)
            self.assertIn("ugen.log", err)


if __name__ == "__main__":
    unittest.main()
