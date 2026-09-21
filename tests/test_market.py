"""Tests for the mod market index, the AI prompts, and the mod install/remove API.

Run with::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mods import API_VERSION, market, registry  # noqa: E402
from core.mods.install import InstallError  # noqa: E402
from core.mods.prompts import BUILD_PROMPT, REVIEW_PROMPT  # noqa: E402

SHA = "c" * 40


def entry(**overrides):
    base = {
        "id": "my-mod",
        "name": "My Mod",
        "description": "Does a thing.",
        "author": "Someone",
        "version": "1.0.0",
        "repo": "https://github.com/someone/my-mod",
        "commit": SHA,
    }
    base.update(overrides)
    return base


class ParseEntryTests(unittest.TestCase):
    def test_minimal_entry_gets_defaults(self):
        parsed = market.parse_entry(entry())
        self.assertEqual((parsed["path"], parsed["tags"], parsed["permissions"]), ("", [], None))
        self.assertEqual(parsed["api_version"], API_VERSION)

    def test_normalises_repo_permissions_and_tags(self):
        parsed = market.parse_entry(
            entry(
                repo="https://github.com/someone/my-mod.git",
                path="mods\\x",
                commit=SHA.upper(),
                tags=[" Files ", "", "Subtitles"],
                permissions={"network": True},
            )
        )
        self.assertEqual(parsed["repo"], "https://github.com/someone/my-mod")
        self.assertEqual(parsed["path"], "mods/x")
        self.assertEqual(parsed["commit"], SHA)
        self.assertEqual(parsed["tags"], ["files", "subtitles"])
        self.assertEqual(parsed["permissions"], {"network": True, "writes_files": False, "runs_programs": False})

    def test_bad_entries_are_rejected(self):
        bad = [
            entry(id="Bad Id"),
            entry(commit="main"),
            entry(commit="abc123"),
            entry(repo="http://github.com/o/r"),
            entry(repo="https://github.com/o/r/tree/main"),  # the commit belongs in 'commit'
            entry(repo="git@github.com:o/r.git"),
            entry(name=""),
            entry(homepage="javascript:alert(1)"),
            entry(tags="files"),
            entry(permissions={"network": "yes"}),
            entry(path="../x"),
            "not an object",
        ]
        for raw in bad:
            with self.assertRaises(ValueError, msg=repr(raw)):
                market.parse_entry(raw)

    def test_one_bad_entry_does_not_hide_the_rest(self):
        entries, problems = market.parse_index(
            {"format": 1, "mods": [entry(), entry(id="Bad"), entry(id="my-mod"), entry(id="other")]}
        )
        self.assertEqual([e["id"] for e in entries], ["my-mod", "other"])
        self.assertEqual(len(problems), 2)

    def test_index_shape_and_format_are_checked(self):
        for data in ([], {"mods": "x"}, {"format": 2, "mods": []}):
            with self.assertRaises(Exception):
                market.parse_index(data)

    def test_search_matches_every_word_in_any_field(self):
        e = market.parse_entry(entry(tags=["subtitles"], description="Fix timing"))
        self.assertTrue(market.matches(e, ""))
        self.assertTrue(market.matches(e, "timing subtitles"))
        self.assertTrue(market.matches(e, "SOMEONE"))
        self.assertFalse(market.matches(e, "timing video"))


class ShippedIndexTests(unittest.TestCase):
    def test_the_index_in_the_repo_is_valid(self):
        data = json.loads((ROOT / "market" / "index.json").read_text(encoding="utf-8"))
        entries, problems = market.parse_index(data)
        self.assertEqual(problems, [])
        self.assertTrue(entries)
        builtin_ids = {m.id for m in registry.all() if m.builtin}
        self.assertFalse(builtin_ids & {e["id"] for e in entries}, "a listing cannot use a built-in id")


class FetchMarketTests(unittest.TestCase):
    def setUp(self):
        market._cache.clear()
        self.addCleanup(market._cache.clear)

    def test_reads_a_local_index_and_caches_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "index.json"
            index.write_text(json.dumps({"format": 1, "mods": [entry()]}), encoding="utf-8")
            with mock.patch.dict("os.environ", {market.MARKET_URL_ENV: index.as_uri()}):
                first = market.fetch_market()
                self.assertEqual((first["error"], [e["id"] for e in first["mods"]]), (None, ["my-mod"]))
                index.write_text(json.dumps({"format": 1, "mods": []}), encoding="utf-8")
                self.assertEqual(len(market.fetch_market()["mods"]), 1, "served from the cache")
                self.assertEqual(len(market.fetch_market(force=True)["mods"]), 0, "refresh reloads")

    def test_errors_come_back_in_the_result_and_are_not_cached(self):
        with mock.patch.object(market, "_http_get", side_effect=InstallError("offline")):
            result = market.fetch_market(force=True)
        self.assertIn("offline", result["error"])
        self.assertEqual(result["mods"], [])
        with mock.patch.object(market, "_http_get", return_value=b"not json"):
            self.assertIsNotNone(market.fetch_market(force=True)["error"])
        with mock.patch.object(market, "_http_get", return_value=b'{"format": 9, "mods": []}'):
            self.assertIn("newer version", market.fetch_market(force=True)["error"])


class PromptTests(unittest.TestCase):
    def test_build_prompt_carries_the_current_api_version(self):
        self.assertIn(f"api_version = {API_VERSION}", BUILD_PROMPT)
        self.assertNotIn("@API_VERSION@", BUILD_PROMPT)

    def test_modding_md_shows_the_same_prompts_the_app_copies(self):
        doc = (ROOT / "MODDING.md").read_text(encoding="utf-8").replace("\r\n", "\n")
        for prompt in (BUILD_PROMPT, REVIEW_PROMPT):
            self.assertIn("````text\n" + prompt + "\n````", doc)

    def test_review_prompt_asks_for_the_important_things(self):
        for phrase in ("[permissions]", "Verdict", "cannot run the code", "<PASTE"):
            self.assertIn(phrase, REVIEW_PROMPT)


def make_mod_zip(mod_id: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mod.toml", f'id = "{mod_id}"\nname = "{mod_id}"\nauthor = "T"\n[ui]\nrun_mode = "run"\n')
        zf.writestr("main.py", "def run(params, ctx):\n    ctx.log('hi')\n")
    return buf.getvalue()


class ModApiTests(unittest.TestCase):
    """The install / remove / safe-mode endpoints, in an isolated app-data folder."""

    def setUp(self):
        from fastapi.testclient import TestClient

        from web.server import app

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        data_dir = self.root / "Toolbox"
        data_dir.mkdir()
        self.mods_dir = data_dir / "mods"
        patches = [
            mock.patch("core.mods.registry.app_data_dir", lambda: data_dir),
            mock.patch("core.mods.install.app_data_dir", lambda: data_dir),
            mock.patch("core.settings_store.app_data_dir", lambda: data_dir),
            mock.patch.dict("os.environ", {"TOOLBOX_NO_MODS": "", "MEDIA_TOOL_NO_MODS": ""}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(registry.reload)
        registry.reload()
        self.client = TestClient(app)

    def make_zip(self, mod_id="api-mod") -> str:
        path = self.root / f"{mod_id}.zip"
        path.write_bytes(make_mod_zip(mod_id))
        return str(path)

    def test_prepare_confirm_and_remove(self):
        res = self.client.post("/api/mods/install/prepare", json={"location": self.make_zip()})
        self.assertEqual(res.status_code, 200, res.text)
        preview = res.json()
        self.assertEqual(preview["manifest"]["id"], "api-mod")
        self.assertFalse((self.mods_dir / "api-mod").exists())

        res = self.client.post("/api/mods/install/confirm", json={"token": preview["token"], "enable": True})
        self.assertEqual(res.status_code, 200, res.text)
        mods = {m["id"]: m for m in res.json()["mods"]}
        self.assertTrue(mods["api-mod"]["enabled"])
        self.assertEqual(mods["api-mod"]["install"]["type"], "zip")

        source = self.client.get("/api/mods/api-mod/source").json()
        self.assertEqual({f["path"] for f in source["files"]}, {"mod.toml", "main.py"})

        res = self.client.delete("/api/mods/api-mod")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("api-mod", {m["id"] for m in res.json()["mods"]})
        self.assertEqual(self.client.delete("/api/mods/convert").status_code, 409)

    def test_errors_are_readable_and_cancel_cleans_up(self):
        res = self.client.post("/api/mods/install/prepare", json={"location": str(self.root / "nothing")})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Nothing found", res.json()["detail"])

        preview = self.client.post("/api/mods/install/prepare", json={"location": self.make_zip("cancel-me")}).json()
        self.assertEqual(self.client.delete(f"/api/mods/install/{preview['token']}").status_code, 200)
        res = self.client.post("/api/mods/install/confirm", json={"token": preview["token"]})
        self.assertEqual(res.status_code, 400)

    def test_safe_mode_button_hides_and_restores_user_mods(self):
        preview = self.client.post("/api/mods/install/prepare", json={"location": self.make_zip("safe-one")}).json()
        self.client.post("/api/mods/install/confirm", json={"token": preview["token"], "enable": True})

        res = self.client.post("/api/mods/safe-mode", json={"enabled": True}).json()
        self.assertTrue(res["safe_mode"])
        self.assertNotIn("safe-one", {m["id"] for m in res["mods"]})
        self.assertIn("convert", {m["id"] for m in res["mods"]}, "built-in features stay on")

        res = self.client.post("/api/mods/safe-mode", json={"enabled": False}).json()
        self.assertFalse(res["safe_mode"])
        self.assertIn("safe-one", {m["id"] for m in res["mods"]})

    def test_prompts_and_market_endpoints(self):
        prompts = self.client.get("/api/mods/prompts").json()
        self.assertEqual((prompts["build"], prompts["review"]), (BUILD_PROMPT, REVIEW_PROMPT))
        with mock.patch.object(market, "_http_get", side_effect=InstallError("offline")):
            res = self.client.get("/api/mods/market?refresh=true")
        self.assertEqual(res.status_code, 200)
        self.assertIn("offline", res.json()["error"])


if __name__ == "__main__":
    unittest.main()
