"""Tests for the per-user data folder, including the move from the pre-3.0 "MediaTool" name.

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

from core import runtime  # noqa: E402


class AppDataDirTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        # Point every platform's base folder at the temp dir.
        env = {"LOCALAPPDATA": str(self.root), "XDG_DATA_HOME": str(self.root)}
        patches = [
            mock.patch.dict("os.environ", env),
            mock.patch("pathlib.Path.home", lambda: self.root),
        ]
        if sys.platform == "darwin":
            (self.root / "Library" / "Application Support").mkdir(parents=True)
            self.root = self.root / "Library" / "Application Support"
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_fresh_install_gets_a_new_folder(self):
        path = runtime.app_data_dir()
        self.assertEqual(path, self.root / "Toolbox")
        self.assertTrue(path.is_dir())
        self.assertFalse((self.root / "MediaTool").exists())

    def test_old_folder_is_moved_with_its_contents(self):
        old = self.root / "MediaTool"
        (old / "mods" / "mine").mkdir(parents=True)
        (old / "settings.json").write_text('{"file_logging": false}', encoding="utf-8")
        (old / "mods" / "mine" / "mod.toml").write_text('id = "mine"', encoding="utf-8")

        path = runtime.app_data_dir()

        self.assertEqual(path, self.root / "Toolbox")
        self.assertFalse(old.exists())
        self.assertEqual((path / "settings.json").read_text(encoding="utf-8"), '{"file_logging": false}')
        self.assertTrue((path / "mods" / "mine" / "mod.toml").is_file())

    def test_migration_happens_only_once_and_never_overwrites(self):
        (self.root / "MediaTool").mkdir()
        (self.root / "MediaTool" / "settings.json").write_text("old", encoding="utf-8")
        (self.root / "Toolbox").mkdir()
        (self.root / "Toolbox" / "settings.json").write_text("new", encoding="utf-8")

        path = runtime.app_data_dir()

        self.assertEqual((path / "settings.json").read_text(encoding="utf-8"), "new")
        # The old folder is left alone rather than merged or deleted.
        self.assertEqual((self.root / "MediaTool" / "settings.json").read_text(encoding="utf-8"), "old")

    def test_a_failed_move_falls_back_to_a_fresh_folder(self):
        (self.root / "MediaTool").mkdir()
        with mock.patch("pathlib.Path.rename", side_effect=PermissionError("in use")):
            with self.assertLogs("core.runtime", level="WARNING"):
                path = runtime.app_data_dir()
        self.assertEqual(path, self.root / "Toolbox")
        self.assertTrue(path.is_dir())
        self.assertTrue((self.root / "MediaTool").is_dir())


if __name__ == "__main__":
    unittest.main()
