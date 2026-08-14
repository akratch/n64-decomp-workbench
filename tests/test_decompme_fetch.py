"""Fetching an export is validated, cached, and honest about what it got.

The transport is the scripted double from `fake_http`; nothing here opens a
socket. The archive each test serves is built in memory, so the ZIP that
reaches the validator is exactly the one the assertions describe.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from fake_http import Answer, FakeOpener, RecordedSleep, html_answer

from decomp_workbench import decompme_cli
from decomp_workbench.cli import main
from decomp_workbench.decompme_fetch import (
    fetch_scratch,
    scratch_slug,
)
from decomp_workbench.http_client import (
    NetworkError,
    PoliteClient,
    RequestRefused,
)

METADATA = {
    "slug": "aBcDe",
    "name": "func_800C1A90",
    "platform": "n64",
    "compiler": "ido5.3",
    "compiler_flags": "-O2 -mips2 -g3",
    "diff_label": "func_800C1A90",
    "score": 20,
    "max_score": 12700,
}

MEMBERS = {
    "metadata.json": json.dumps(METADATA).encode("utf-8"),
    "ctx.c": b"typedef int s32;\n",
    "code.c": b"s32 func_800C1A90(void) { return 0; }\n",
    "target.o": b"\x7fELF-not-really\n",
    "target.s": b"glabel func_800C1A90\njr $ra\n",
}


def export_zip(members: dict[str, bytes] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in (MEMBERS if members is None else members).items():
            archive.writestr(name, content)
    return buffer.getvalue()


def zip_answer(members: dict[str, bytes] | None = None) -> Answer:
    return Answer(
        body=export_zip(members),
        headers={"Content-Type": "application/zip"},
    )


def client(*answers: Answer) -> tuple[PoliteClient, FakeOpener]:
    opener = FakeOpener(*answers)
    return PoliteClient(opener=opener, sleep=RecordedSleep()), opener


class SlugTests(unittest.TestCase):
    def test_a_pasted_scratch_url_is_accepted_as_its_slug(self) -> None:
        self.assertEqual(scratch_slug("https://decomp.me/scratch/aBcDe"), "aBcDe")
        self.assertEqual(scratch_slug("https://decomp.me/scratch/aBcDe/"), "aBcDe")
        self.assertEqual(scratch_slug(" aBcDe "), "aBcDe")

    def test_a_path_segment_cannot_be_smuggled_into_the_request(self) -> None:
        for value in ("../../etc/passwd", "abc/def", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                scratch_slug(value)


class FetchTests(unittest.TestCase):
    def test_an_export_is_validated_then_written_to_the_standard_layout(self) -> None:
        polite, opener = client(zip_answer())
        with tempfile.TemporaryDirectory() as temporary:
            report = fetch_scratch("aBcDe", client=polite, outdir=temporary)
            output = Path(report["output"])
            self.assertEqual(output, Path(temporary).resolve() / "aBcDe")
            for name, content in MEMBERS.items():
                self.assertEqual((output / name).read_bytes(), content)
            # The ZIP is kept: re-reading a local copy costs the server
            # nothing, which is the whole reason to keep it.
            self.assertTrue((Path(temporary).resolve() / "aBcDe.zip").is_file())
        self.assertFalse(report["reused"])
        self.assertEqual(report["schema"], "decomp-workbench-scratch-fetch-v1")
        self.assertEqual(report["missing_members"], [])
        self.assertEqual(report["metadata"]["max_score"], 12700)
        self.assertEqual(opener.urls, ["https://decomp.me/api/scratch/aBcDe/export"])

    def test_an_export_already_on_disk_is_reported_without_a_request(self) -> None:
        polite, opener = client(zip_answer())
        with tempfile.TemporaryDirectory() as temporary:
            fetch_scratch("aBcDe", client=polite, outdir=temporary)
            self.assertEqual(len(opener.requests), 1)
            # The opener has no answers left: a second request would fail the
            # test outright, which is the assertion.
            again = fetch_scratch("aBcDe", client=polite, outdir=temporary)
        self.assertTrue(again["reused"])
        self.assertEqual(len(opener.requests), 1)

    def test_force_replaces_the_cached_export(self) -> None:
        changed = dict(MEMBERS)
        changed["code.c"] = b"s32 func_800C1A90(void) { return 1; }\n"
        polite, opener = client(zip_answer(), zip_answer(changed))
        with tempfile.TemporaryDirectory() as temporary:
            fetch_scratch("aBcDe", client=polite, outdir=temporary)
            report = fetch_scratch("aBcDe", client=polite, outdir=temporary, force=True)
            self.assertEqual(
                (Path(report["output"]) / "code.c").read_bytes(), changed["code.c"]
            )
        self.assertFalse(report["reused"])
        self.assertEqual(len(opener.requests), 2)

    def test_an_optional_member_the_export_omits_is_reported_not_fatal(self) -> None:
        partial = {name: MEMBERS[name] for name in MEMBERS if name != "target.s"}
        polite, _opener = client(zip_answer(partial))
        with tempfile.TemporaryDirectory() as temporary:
            report = fetch_scratch("aBcDe", client=polite, outdir=temporary)
        self.assertEqual(report["missing_members"], ["target.s"])

    def test_an_archive_that_is_not_an_export_leaves_nothing_behind(self) -> None:
        polite, _opener = client(zip_answer({"notes.txt": b"hello\n"}))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                fetch_scratch("aBcDe", client=polite, outdir=temporary)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_a_body_that_is_not_a_zip_fails_before_touching_the_output(self) -> None:
        polite, _opener = client(Answer(body=b"<html>not a zip</html>"))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError) as error:
                fetch_scratch("aBcDe", client=polite, outdir=temporary)
            self.assertIn("not a valid ZIP archive", str(error.exception))
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_an_unrelated_directory_is_never_overwritten(self) -> None:
        polite, opener = client(zip_answer())
        with tempfile.TemporaryDirectory() as temporary:
            occupied = Path(temporary) / "aBcDe"
            occupied.mkdir()
            (occupied / "my-work.c").write_text("mine\n", encoding="utf-8")
            with self.assertRaises(ValueError) as error:
                fetch_scratch("aBcDe", client=polite, outdir=temporary)
            self.assertIn("already exists", str(error.exception))
            self.assertTrue((occupied / "my-work.c").is_file())
        self.assertEqual(opener.requests, [])

    def test_a_refusal_is_raised_with_its_guidance_intact(self) -> None:
        polite, _opener = client(html_answer(403))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(RequestRefused) as refused:
                fetch_scratch("aBcDe", client=polite, outdir=temporary)
        self.assertIn("HTTP 403", str(refused.exception))
        self.assertIn("browser", str(refused.exception))

    def test_a_deleted_scratch_says_so(self) -> None:
        polite, _opener = client(
            Answer(status=404, body=b'{"detail": "Not found."}'),
        )
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(NetworkError) as missing:
                fetch_scratch("aBcDe", client=polite, outdir=temporary)
        self.assertIn("does not exist", str(missing.exception))


class CommandTests(unittest.TestCase):
    def run_cli(self, arguments: list[str], *answers: Answer) -> tuple[int, str, str]:
        polite, _opener = client(*answers)
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(decompme_cli, "build_client", return_value=polite),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            status = main(arguments)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_the_terminal_report_names_the_layout_and_the_next_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status, stdout, stderr = self.run_cli(
                ["fetch-scratch", "aBcDe", "--outdir", temporary],
                zip_answer(),
            )
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("scratch aBcDe: downloaded", stdout)
        self.assertIn("members: code.c ctx.c metadata.json target.o target.s", stdout)
        self.assertIn("decomp.me display: score=20/12700", stdout)
        self.assertIn("next: decomp-workbench check-scratch", stdout)

    def test_the_grouped_spelling_emits_the_versioned_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status, stdout, _stderr = self.run_cli(
                ["scratch", "fetch", "aBcDe", "--outdir", temporary, "--json"],
                zip_answer(),
            )
        payload = json.loads(stdout)
        self.assertEqual(status, 0)
        self.assertEqual(payload["schema"], "decomp-workbench-scratch-fetch-v1")
        self.assertFalse(payload["reused"])

    def test_a_refusal_becomes_a_structured_json_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            status, stdout, _stderr = self.run_cli(
                ["fetch-scratch", "aBcDe", "--outdir", temporary, "--json"],
                html_answer(403),
            )
        payload = json.loads(stdout)
        self.assertEqual(status, 2)
        self.assertEqual(payload["schema"], "decomp-workbench-error-v1")
        self.assertIn("will not imitate", payload["error"]["message"])


if __name__ == "__main__":
    unittest.main()
