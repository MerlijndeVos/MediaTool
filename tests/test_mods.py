"""Tests for the mod system: manifests, the registry, and running mods through the job runner.

Run with::

    python -m unittest discover -s tests -v
"""

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

from core.mods import ManifestError, ModRegistry, parse_manifest, registry  # noqa: E402
from core.mods.manifest import MISSING  # noqa: E402

BUILTIN_IDS = {
    "convert", "trim", "stitch", "download", "rename", "subtitle_translate",
    "subtitle_cleanup", "vts", "audio", "dedup",
}

# Every route the API had before features became mods; none may disappear.
ORIGINAL_ROUTES = {
    ("DELETE", "/api/rename/profiles/{profile_id}"), ("DELETE", "/api/settings/logs"),
    ("GET", "/api/commands"), ("GET", "/api/commands/{command}/schema"), ("GET", "/api/health"),
    ("GET", "/api/jobs"), ("GET", "/api/jobs/{job_id}"), ("GET", "/api/jobs/{job_id}/events"),
    ("GET", "/api/rename/profiles"), ("GET", "/api/settings"), ("GET", "/api/subtitles/languages"),
    ("GET", "/api/tools"), ("GET", "/api/updates/check"), ("GET", "/api/updates/status"),
    ("PATCH", "/api/settings"), ("POST", "/api/download/probe"), ("POST", "/api/jobs"),
    ("POST", "/api/jobs/{job_id}/cancel"), ("POST", "/api/jobs/{job_id}/undo"),
    ("POST", "/api/rename/profiles"), ("POST", "/api/rename/profiles/generate"),
    ("POST", "/api/rename/profiles/test"), ("POST", "/api/settings/logs/open-file"),
    ("POST", "/api/settings/logs/open-folder"), ("POST", "/api/subtitles/scan-junk"),
    ("POST", "/api/tools/bootstrap"), ("POST", "/api/updates/apply"),
}


def minimal(**extra) -> dict:
    return {"id": "demo", "name": "Demo", **extra}


class ManifestTests(unittest.TestCase):
    def test_minimal_manifest_gets_defaults(self):
        m = parse_manifest(minimal(ui={"run_mode": "run"}))
        self.assertEqual((m.id, m.group, m.icon, m.entry, m.ui_kind), ("demo", "Other", "puzzle", "main.py", "form"))
        self.assertEqual(m.params, ())

    def test_rejects_bad_ids(self):
        for bad in ("Bad Id", "1abc", "", "../x", "mods"):
            with self.assertRaises(ManifestError, msg=bad):
                parse_manifest({"id": bad, "name": "x"})

    def test_rejects_newer_api_version(self):
        with self.assertRaisesRegex(ManifestError, "API version"):
            parse_manifest(minimal(api_version=99))

    def test_rejects_entry_outside_folder(self):
        for entry in ("../evil.py", "/abs/evil.py", "main.txt"):
            with self.assertRaises(ManifestError, msg=entry):
                parse_manifest(minimal(entry=entry))

    def test_param_validation(self):
        bad_params = [
            {"name": "Upper"},
            {"name": "x", "type": "nope"},
            {"name": "x", "type": "choice"},
            {"name": "x", "type": "text", "choices": ["a"]},
            {"name": "x", "type": "text", "min": 1},
            {"name": "x", "type": "integer", "min": 5, "max": 1},
            {"name": "x", "type": "integer", "default": "one"},
            {"name": "x", "type": "choice", "choices": ["a"], "default": "b"},
        ]
        for p in bad_params:
            with self.assertRaises(ManifestError, msg=str(p)):
                parse_manifest(minimal(ui={"run_mode": "run"}, params=[p]))
        with self.assertRaisesRegex(ManifestError, "unique"):
            parse_manifest(minimal(ui={"run_mode": "run"}, params=[{"name": "a"}, {"name": "a"}]))

    def test_required_and_nullable_semantics(self):
        m = parse_manifest(minimal(ui={"run_mode": "run"}, params=[
            {"name": "needed", "type": "text"},
            {"name": "optional", "type": "text", "default": "x"},
            {"name": "maybe", "type": "text", "nullable": True},
        ]))
        needed, optional, maybe = m.params
        self.assertTrue(needed.required)
        self.assertIs(needed.default, MISSING)
        self.assertFalse(optional.required)
        self.assertFalse(maybe.required)
        self.assertIsNone(maybe.default)

    def test_preview_apply_needs_a_bool_mode_param(self):
        with self.assertRaisesRegex(ManifestError, "dry_run"):
            parse_manifest(minimal(ui={"run_mode": "preview_apply"}, params=[]))
        parse_manifest(minimal(params=[{"name": "dry_run", "type": "bool", "default": True}]))


class BuiltinModTests(unittest.TestCase):
    def test_all_builtin_features_are_mods_and_load(self):
        reg = ModRegistry()
        reg.reload()
        self.assertEqual(reg.errors(), [])
        builtin = {m.id for m in reg.all() if m.builtin}
        self.assertEqual(builtin, BUILTIN_IDS)
        for mod in reg.all():
            if mod.builtin:
                self.assertTrue(mod.enabled, mod.id)
                self.assertTrue(callable(mod.run_fn()), mod.id)

    def test_generated_models_match_the_previous_api(self):
        from web.mod_params import params_model

        convert = params_model(registry.get("convert"))
        self.assertEqual(convert.model_fields["crf"].default, 19)
        self.assertEqual(convert.model_fields["dry_run"].default, True)
        with self.assertRaises(Exception):
            convert.model_validate({"input": "a", "output": "b", "crf": 99})
        with self.assertRaises(Exception):
            convert.model_validate({"input": "a", "output": "b", "output_format": "avi"})
        trim = params_model(registry.get("trim")).model_validate({"input": "a"})
        self.assertIsNone(trim.output)
        # custom Params models (rename keeps its `copy` alias and profile validation)
        rename = params_model(registry.get("rename")).model_validate({"input": "a", "copy": True})
        self.assertTrue(rename.copy_files)

    def test_api_keeps_every_original_route(self):
        from web.server import app

        have = {(m, r.path) for r in app.routes if hasattr(r, "methods") for m in r.methods}
        self.assertEqual(ORIGINAL_ROUTES - have, set())


class UserModTests(unittest.TestCase):
    """User mods in an isolated app-data folder, run through the real job manager."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        data_dir = Path(self._tmp.name) / "Toolbox"
        data_dir.mkdir()
        self.mods_dir = data_dir / "mods"
        self.mods_dir.mkdir()
        patches = [
            mock.patch("core.mods.registry.app_data_dir", lambda: data_dir),
            mock.patch("core.settings_store.app_data_dir", lambda: data_dir),
            mock.patch.dict("os.environ", {"TOOLBOX_NO_MODS": "", "MEDIA_TOOL_NO_MODS": ""}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(registry.reload)  # runs after the patches are undone
        registry.reload()

    def make_mod(self, mod_id: str, toml_extra: str = "", code: str = "def run(params, ctx):\n    pass\n"):
        folder = self.mods_dir / mod_id
        folder.mkdir()
        (folder / "mod.toml").write_text(
            f'id = "{mod_id}"\nname = "{mod_id}"\n[ui]\nrun_mode = "run"\n{toml_extra}', encoding="utf-8"
        )
        (folder / "main.py").write_text(textwrap.dedent(code), encoding="utf-8")
        registry.reload()

    def wait(self, job, timeout=10.0):
        end = time.time() + timeout
        while time.time() < end and job.status in ("queued", "running"):
            time.sleep(0.02)
        return job

    def test_user_mods_start_disabled_and_can_be_enabled(self):
        from web.jobs import job_manager

        self.make_mod("hello")
        self.assertFalse(registry.get("hello").enabled)
        with self.assertRaisesRegex(ValueError, "turned off"):
            job_manager.create("hello", {})
        registry.set_enabled("hello", True)
        self.assertEqual(self.wait(job_manager.create("hello", {})).status, "completed")
        registry.set_enabled("hello", False)
        with self.assertRaises(ValueError):
            job_manager.create("hello", {})

    def test_builtin_mods_cannot_be_disabled(self):
        from core.mods import ModError

        with self.assertRaises(ModError):
            registry.set_enabled("convert", False)

    def test_params_are_validated_from_the_manifest(self):
        from web.jobs import job_manager

        self.make_mod("counter", '[[params]]\nname = "n"\ntype = "integer"\nmin = 1\nmax = 5\ndefault = 2\n',
                      "def run(params, ctx):\n    ctx.log(f'n={params[\"n\"]}')\n")
        registry.set_enabled("counter", True)
        job = self.wait(job_manager.create("counter", {}))
        self.assertEqual(job.params, {"n": 2})
        with self.assertRaises(ValueError):
            job_manager.create("counter", {"n": 9})

    def test_failing_and_unloadable_mods_fail_the_job_not_the_app(self):
        from web.jobs import job_manager

        self.make_mod("crash", code="def run(params, ctx):\n    raise ValueError('nope')\n")
        registry.set_enabled("crash", True)
        job = self.wait(job_manager.create("crash", {}))
        self.assertEqual((job.status, job.error), ("failed", "nope"))

        self.make_mod("boom", code="raise RuntimeError('on import')\n")
        registry.set_enabled("boom", True)
        with self.assertRaises(Exception):
            job_manager.create("boom", {})

    def test_cancelled_mod_ends_as_cancelled(self):
        from web.jobs import job_manager

        self.make_mod("selfcancel", code="def run(params, ctx):\n    ctx.cancel_event.set()\n    ctx.raise_if_cancelled()\n")
        registry.set_enabled("selfcancel", True)
        self.assertEqual(self.wait(job_manager.create("selfcancel", {})).status, "cancelled")

    def test_bad_manifests_are_reported_not_fatal(self):
        bad = self.mods_dir / "bad"
        bad.mkdir()
        (bad / "mod.toml").write_text('id = "Not Valid"\nname = "x"\n', encoding="utf-8")
        registry.reload()
        self.assertEqual(len(registry.errors()), 1)
        self.assertIn("bad", registry.errors()[0].path)
        self.assertEqual({m.id for m in registry.all() if m.builtin}, BUILTIN_IDS)

    def test_user_mods_cannot_claim_builtin_ids_or_panels(self):
        self.make_mod("convert")  # same id as a built-in feature
        panel = self.mods_dir / "sneaky"
        panel.mkdir()
        (panel / "mod.toml").write_text('id = "sneaky"\nname = "x"\n[ui]\nkind = "builtin"\npanel = "rename"\n', encoding="utf-8")
        registry.reload()
        self.assertEqual(len(registry.errors()), 2)
        self.assertTrue(registry.get("convert").builtin)
        self.assertIsNone(registry.get("sneaky"))

    def test_safe_mode_hides_user_mods(self):
        self.make_mod("hello")
        with mock.patch.dict("os.environ", {"TOOLBOX_NO_MODS": "1"}):
            registry.reload()
            self.assertIsNone(registry.get("hello"))
        registry.reload()
        self.assertIsNotNone(registry.get("hello"))

    def test_safe_mode_still_honours_the_pre_rename_variable(self):
        # Set before the app was renamed from Media Tool; it must keep user mods off.
        self.make_mod("hello")
        from core.mods.registry import safe_mode

        with mock.patch.dict("os.environ", {"MEDIA_TOOL_NO_MODS": "1"}):
            registry.reload()
            self.assertTrue(safe_mode())
            self.assertIsNone(registry.get("hello"))
        registry.reload()
        self.assertFalse(safe_mode())
        self.assertIsNotNone(registry.get("hello"))

    def test_undo_manifest_is_kept_only_when_the_mod_declares_undo(self):
        from web.jobs import job_manager

        code = (
            "def run(params, ctx):\n    ctx.set_undo_manifest({'operations': [1, 2]})\n"
            "def undo(manifest, ctx):\n    return {'restored': len(manifest['operations']), 'failed': 0, 'skipped': 0}\n"
        )
        self.make_mod("noundo", code=code)
        registry.set_enabled("noundo", True)
        self.assertFalse(self.wait(job_manager.create("noundo", {})).undo_available())

        self.make_mod("undoable", "[run]\nundo = true\n", code)
        registry.set_enabled("undoable", True)
        job = self.wait(job_manager.create("undoable", {}))
        self.assertTrue(job.undo_available())
        self.assertEqual(job.undo_op_count(), 2)
        undo_job = self.wait(job_manager.undo_job(job.id))
        self.assertEqual(undo_job.status, "completed")
        self.assertFalse(job.undo_available())


if __name__ == "__main__":
    unittest.main()
