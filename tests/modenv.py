"""Shared setup for tests that need an isolated app-data folder with a mods folder in it."""

from __future__ import annotations

import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mods import registry  # noqa: E402


class ModEnvTestCase(unittest.TestCase):
    """A throwaway app-data folder, so user mods and settings never touch the real ones."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.data_dir = self.root / "Toolbox"
        self.data_dir.mkdir()
        self.mods_dir = self.data_dir / "mods"
        self.mods_dir.mkdir()
        patches = [
            mock.patch("core.mods.registry.app_data_dir", lambda: self.data_dir),
            mock.patch("core.mods.install.app_data_dir", lambda: self.data_dir),
            mock.patch("core.settings_store.app_data_dir", lambda: self.data_dir),
            mock.patch.dict("os.environ", {"TOOLBOX_NO_MODS": "", "MEDIA_TOOL_NO_MODS": ""}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(registry.reload)  # runs after the patches are undone
        registry.reload()

    def make_mod(self, mod_id: str, toml_extra: str = "", code: str = "def run(params, ctx):\n    pass\n", header: str = ""):
        """A tool in the mods folder. *toml_extra* goes after ``[ui] run_mode = "run"``; *header* before ``[ui]``."""
        folder = self.mods_dir / mod_id
        folder.mkdir()
        (folder / "mod.toml").write_text(
            f'id = "{mod_id}"\nname = "{mod_id}"\n{header}[ui]\nrun_mode = "run"\n{toml_extra}', encoding="utf-8"
        )
        (folder / "main.py").write_text(textwrap.dedent(code), encoding="utf-8")
        registry.reload()
        return folder

    def make_theme(self, mod_id: str, theme_toml: str = "[theme]\n", header: str = 'api_version = 2\n'):
        folder = self.mods_dir / mod_id
        folder.mkdir()
        (folder / "mod.toml").write_text(
            f'id = "{mod_id}"\nname = "{mod_id}"\ntype = "theme"\n{header}{theme_toml}', encoding="utf-8"
        )
        registry.reload()
        return folder

    @staticmethod
    def wait(job, timeout: float = 10.0):
        end = time.time() + timeout
        while time.time() < end and job.status in ("queued", "running"):
            time.sleep(0.02)
        return job
