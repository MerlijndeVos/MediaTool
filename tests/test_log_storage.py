"""Tests for reading stored logs in pieces (the Settings → Logs viewer).

Run with::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import log_storage  # noqa: E402
from core.log_storage import read_log_chunk  # noqa: E402


class LogDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        patcher = mock.patch.object(log_storage, "logs_dir", lambda: self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name: str, data: str | bytes) -> Path:
        path = self.dir / name
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        return path


class ReadLogChunkTests(LogDirTestCase):
    def numbered(self, count: int) -> str:
        return "".join(f"2026-01-01 00:00:00,000 [INFO] line {i}\n" for i in range(count))

    def test_small_file_is_returned_whole(self):
        self.write("a.log", "one\ntwo\nthree\n")
        chunk = read_log_chunk("a.log")
        self.assertEqual(chunk["lines"], ["one", "two", "three"])
        self.assertEqual(chunk["start"], 0)
        self.assertFalse(chunk["has_earlier"])
        self.assertEqual(chunk["end"], chunk["size_bytes"])

    def test_default_is_the_tail(self):
        self.write("a.log", self.numbered(1200))
        chunk = read_log_chunk("a.log", max_lines=100)
        self.assertEqual(len(chunk["lines"]), 100)
        self.assertTrue(chunk["lines"][0].endswith("line 1100"))
        self.assertTrue(chunk["lines"][-1].endswith("line 1199"))
        self.assertTrue(chunk["has_earlier"])

    def test_paging_back_covers_every_line_once(self):
        # Big enough to need several 64 KB blocks, so block boundaries fall inside lines.
        self.write("a.log", self.numbered(6000))
        lines: list[str] = []
        chunk = read_log_chunk("a.log", max_lines=700)
        lines = chunk["lines"] + lines
        pages = 1
        while chunk["has_earlier"]:
            chunk = read_log_chunk("a.log", end=chunk["start"], max_lines=700)
            lines = chunk["lines"] + lines
            pages += 1
        self.assertGreater(pages, 5)
        self.assertEqual(lines, [s.rstrip("\n") for s in self.numbered(6000).splitlines(keepends=True)])

    def test_chunk_starting_exactly_on_a_block_boundary_loses_nothing(self):
        # Every line is 63 bytes + newline, so 1024 lines fill exactly one 64 KB block.
        line = "x" * 63 + "\n"
        self.write("a.log", line * 3000)
        seen = 0
        chunk = read_log_chunk("a.log", max_lines=1024)
        seen += len(chunk["lines"])
        while chunk["has_earlier"]:
            chunk = read_log_chunk("a.log", end=chunk["start"], max_lines=1024)
            seen += len(chunk["lines"])
        self.assertEqual(seen, 3000)

    def test_last_line_without_a_trailing_newline(self):
        self.write("a.log", "one\ntwo\nthree")
        self.assertEqual(read_log_chunk("a.log")["lines"], ["one", "two", "three"])

    def test_windows_line_endings(self):
        self.write("a.log", b"one\r\ntwo\r\n")
        self.assertEqual(read_log_chunk("a.log")["lines"], ["one", "two"])

    def test_empty_file(self):
        self.write("a.log", b"")
        chunk = read_log_chunk("a.log")
        self.assertEqual(chunk["lines"], [])
        self.assertFalse(chunk["has_earlier"])

    def test_invalid_utf8_is_replaced_not_fatal(self):
        self.write("a.log", b"ok\nbad \xff\xfe byte\nfine\n")
        lines = read_log_chunk("a.log")["lines"]
        self.assertEqual(len(lines), 3)
        self.assertIn("�", lines[1])

    def test_multibyte_characters_survive_paging(self):
        text = "".join(f"regel {i} éè€ ✓\n" for i in range(9000))
        self.write("a.log", text)
        lines: list[str] = []
        chunk = read_log_chunk("a.log", max_lines=800)
        lines = chunk["lines"] + lines
        while chunk["has_earlier"]:
            chunk = read_log_chunk("a.log", end=chunk["start"], max_lines=800)
            lines = chunk["lines"] + lines
        self.assertEqual(lines, text.splitlines())

    def test_one_huge_line_is_read_in_pieces_and_terminates(self):
        self.write("a.log", "x" * (3 * 1024 * 1024) + "\ntail\n")
        chunk = read_log_chunk("a.log")
        self.assertEqual(chunk["lines"][-1], "tail")
        pages = 0
        while chunk["has_earlier"]:
            chunk = read_log_chunk("a.log", end=chunk["start"])
            pages += 1
            self.assertLess(pages, 20, "paging back must make progress")

    def test_end_is_clamped_to_the_file(self):
        self.write("a.log", "one\ntwo\n")
        self.assertEqual(read_log_chunk("a.log", end=10_000)["lines"], ["one", "two"])
        self.assertEqual(read_log_chunk("a.log", end=0)["lines"], [])

    def test_appended_lines_do_not_move_earlier_pages(self):
        path = self.write("a.log", self.numbered(50))
        tail = read_log_chunk("a.log", max_lines=10)
        with path.open("ab") as fh:
            fh.write(b"appended later\n")
        earlier = read_log_chunk("a.log", end=tail["start"], max_lines=10)
        self.assertTrue(earlier["lines"][-1].endswith("line 39"))

    def test_rejects_anything_but_a_log_file_in_the_logs_folder(self):
        self.write("a.log", "one\n")
        (self.dir.parent / "outside.log").write_text("secret\n")
        self.addCleanup(lambda: (self.dir.parent / "outside.log").unlink(missing_ok=True))
        for bad in ["", "../outside.log", "..\\outside.log", "sub/a.log", "a.txt", "a.log.bak", str(self.dir / "a.log")]:
            with self.subTest(name=bad), self.assertRaises(ValueError):
                read_log_chunk(bad)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            read_log_chunk("nope.log")


class LogEndpointTests(LogDirTestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from fastapi.testclient import TestClient

            from web.server import app
        except ImportError as exc:  # web extras not installed
            raise unittest.SkipTest(f"web dependencies missing: {exc}")
        cls.client = TestClient(app)

    def test_tail_then_earlier(self):
        self.write("a.log", "".join(f"line {i}\n" for i in range(30)))
        res = self.client.get("/api/settings/logs/a.log", params={"lines": 10})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["lines"][0], "line 20")
        self.assertTrue(body["has_earlier"])
        res = self.client.get("/api/settings/logs/a.log", params={"lines": 10, "end": body["start"]})
        self.assertEqual(res.json()["lines"][-1], "line 19")

    def test_rejects_bad_names_and_missing_files(self):
        self.write("a.log", "one\n")
        self.assertEqual(self.client.get("/api/settings/logs/a.txt").status_code, 422)
        self.assertEqual(self.client.get("/api/settings/logs/..%2Fa.log").status_code, 404)
        self.assertEqual(self.client.get("/api/settings/logs/open-folder").status_code, 422)
        self.assertEqual(self.client.get("/api/settings/logs/nope.log").status_code, 404)

    def test_rejects_out_of_range_parameters(self):
        self.write("a.log", "one\n")
        self.assertEqual(self.client.get("/api/settings/logs/a.log", params={"lines": 0}).status_code, 422)
        self.assertEqual(self.client.get("/api/settings/logs/a.log", params={"lines": 99999}).status_code, 422)
        self.assertEqual(self.client.get("/api/settings/logs/a.log", params={"end": -1}).status_code, 422)

    def test_existing_actions_still_work(self):
        self.write("a.log", "one\n")
        self.assertEqual(self.client.get("/api/settings").status_code, 200)
        with mock.patch("web.server.open_path") as open_path:
            res = self.client.post("/api/settings/logs/open-file", json={"name": "a.log"})
            self.assertEqual(res.status_code, 200)
            open_path.assert_called_once()
        res = self.client.delete("/api/settings/logs")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["deleted_count"], 1)


if __name__ == "__main__":
    unittest.main()
