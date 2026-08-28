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
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from phase_streams import binasm_record, binasm_stream, ucode_stream

from decomp_workbench.cli import main
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
        self.assertIn("ucode window", message)
        self.assertIn("docs/compiler-instrumentation.md", message)

    def test_refuses_binasm_by_name(self) -> None:
        with self.assertRaises(BinaryTraceStreamError) as caught:
            read_trace_source(binasm_stream(), name="after-9-ctmc2PdRlS")
        message = str(caught.exception)
        self.assertEqual(caught.exception.stream_format, "binasm")
        self.assertIn("after-9-ctmc2PdRlS", message)
        self.assertIn("16-byte", message)
        self.assertIn("binasm window", message)
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
        self.assertIn("stream window", message)
        self.assertIn("docs/compiler-instrumentation.md", message)


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
