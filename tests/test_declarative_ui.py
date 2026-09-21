"""Tests for the declarative mod UI: sections, show_if, new widgets, result views and actions.

Run with::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import base64
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from modenv import ROOT, ModEnvTestCase  # noqa: E402

from core.mods import ManifestError, ModContext, install, parse_manifest, registry  # noqa: E402
from core.mods import results as R  # noqa: E402
from core.mods.manifest import ICON_NAMES, load_manifest  # noqa: E402


def manifest(params=(), **extra):
    """A tool manifest that asks for API 2 and needs no dry_run switch."""
    return parse_manifest(
        {"id": "demo", "name": "Demo", "api_version": 2, "ui": {"run_mode": "run", **extra.pop("ui", {})}, "params": list(params), **extra}
    )


class ApiGateTests(unittest.TestCase):
    """Anything new has to ask for API 2, so an older Toolbox refuses the mod with a clear message."""

    def test_new_features_need_api_2_declared(self):
        needs_2 = [
            {"sections": [{"id": "a"}]},
            {"actions": [{"name": "go"}]},
            {"accent": "success"},
            {"ui": {"run_mode": "run", "layout": "tabs"}, "sections": [{"id": "a"}]},
            {"params": [{"name": "c", "type": "color", "default": "#ffffff"}]},
            {"params": [{"name": "d", "type": "date", "nullable": True}]},
            {"params": [{"name": "m", "type": "multichoice", "choices": ["a"], "default": []}]},
            {"params": [{"name": "n", "type": "integer", "min": 0, "max": 5, "widget": "slider", "default": 1}]},
            {"params": [{"name": "a", "type": "bool", "default": False}, {"name": "b", "default": "x", "show_if": {"param": "a"}}]},
        ]
        for extra in needs_2:
            data = {"id": "demo", "name": "Demo", "ui": {"run_mode": "run"}, **extra}
            for declared in ({}, {"api_version": 1}):
                with self.assertRaisesRegex(ManifestError, "API version 2", msg=f"{extra} {declared}"):
                    parse_manifest({**data, **declared})
            parse_manifest({**data, "api_version": 2})

    def test_old_manifests_still_load_unchanged(self):
        m = parse_manifest({"id": "old", "name": "Old", "api_version": 1, "ui": {"run_mode": "run"}, "params": [{"name": "n", "type": "integer", "default": 3}]})
        self.assertEqual((m.sections, m.actions, m.layout, m.accent), ((), (), "sections", ""))

    def test_a_newer_api_is_refused_with_advice(self):
        with self.assertRaisesRegex(ManifestError, "Update Toolbox"):
            parse_manifest({"id": "x", "name": "X", "api_version": 3})


class SectionAndShowIfTests(unittest.TestCase):
    def test_sections_params_and_conditions_parse(self):
        m = manifest(
            params=[
                {"name": "mode", "type": "choice", "choices": ["simple", "advanced"], "default": "simple"},
                {"name": "depth", "type": "integer", "default": 2, "section": "adv", "show_if": {"param": "mode", "equals": "advanced"}},
                {"name": "kind", "type": "choice", "choices": ["a", "b"], "default": "a", "show_if": {"param": "mode", "in": ["advanced", "expert"]}},
                {"name": "off", "type": "bool", "default": False, "show_if": {"param": "mode", "not_equals": "simple"}},
                {"name": "flag", "type": "bool", "default": False, "show_if": {"param": "mode", "truthy": False}},
                {"name": "plain", "type": "text", "default": "", "show_if": {"param": "mode"}},
            ],
            sections=[{"id": "adv", "title": "Advanced", "text": "Careful **now**.", "show_if": {"param": "mode", "equals": "advanced"}}],
        )
        self.assertEqual(m.sections[0].title, "Advanced")
        self.assertEqual(m.sections[0].show_if.op, "equals")
        by_name = {p.name: p for p in m.params}
        self.assertEqual(by_name["depth"].section, "adv")
        self.assertEqual([(p.show_if.op) for p in m.params if p.show_if], ["equals", "in", "not_equals", "falsy", "truthy"])
        data = m.to_dict()
        self.assertEqual(data["sections"][0]["id"], "adv")
        self.assertEqual(data["params"][1]["show_if"], {"param": "mode", "op": "equals", "value": "advanced"})

    def test_a_section_title_defaults_to_its_id(self):
        m = manifest(sections=[{"id": "more-options"}])
        self.assertEqual(m.sections[0].title, "More options")

    def test_mistakes_are_reported_plainly(self):
        base = [{"name": "a", "type": "bool", "default": False}]
        bad = {
            "unknown section": dict(params=[{"name": "b", "section": "nope", "default": "x"}]),
            "unknown show_if param": dict(params=[{"name": "b", "default": "x", "show_if": {"param": "ghost"}}]),
            "self reference": dict(params=[{"name": "b", "default": "x", "show_if": {"param": "b"}}]),
            "two operators": dict(params=base + [{"name": "b", "default": "x", "show_if": {"param": "a", "equals": 1, "in": [1]}}]),
            "bad operator": dict(params=base + [{"name": "b", "default": "x", "show_if": {"param": "a", "matches": "x"}}]),
            "show_if not a table": dict(params=base + [{"name": "b", "default": "x", "show_if": "a"}]),
            "empty in": dict(params=base + [{"name": "b", "default": "x", "show_if": {"param": "a", "in": []}}]),
            "duplicate section": dict(params=[], sections=[{"id": "s"}, {"id": "s"}]),
            "bad section id": dict(params=[], sections=[{"id": "Not Valid"}]),
            "section show_if unknown": dict(params=[], sections=[{"id": "s", "show_if": {"param": "ghost"}}]),
            "tabs without sections": dict(params=[], ui={"layout": "tabs"}),
            "bad layout": dict(params=[], ui={"layout": "grid"}),
            "bad accent": dict(params=[], accent="pink"),
        }
        for label, kwargs in bad.items():
            with self.assertRaises(ManifestError, msg=label):
                manifest(**kwargs)

    def test_a_field_that_can_be_hidden_needs_a_default(self):
        with self.assertRaisesRegex(ManifestError, "needs a default"):
            manifest(params=[{"name": "a", "type": "bool", "default": True}, {"name": "b", "show_if": {"param": "a"}}])
        # ... also through its section
        with self.assertRaisesRegex(ManifestError, "needs a default"):
            manifest(
                params=[{"name": "a", "type": "bool", "default": True}, {"name": "b", "section": "s"}],
                sections=[{"id": "s", "show_if": {"param": "a"}}],
            )
        # nullable is fine: a hidden field sends nothing and the mod gets None
        manifest(params=[{"name": "a", "type": "bool", "default": True}, {"name": "b", "nullable": True, "show_if": {"param": "a"}}])

    def test_tabs_layout(self):
        m = manifest(ui={"layout": "tabs"}, sections=[{"id": "one"}, {"id": "two"}])
        self.assertEqual(m.layout, "tabs")
        self.assertEqual(m.to_dict()["ui"]["layout"], "tabs")


class NewParamTypeTests(unittest.TestCase):
    def test_slider(self):
        p = manifest(params=[{"name": "n", "type": "integer", "widget": "slider", "min": 0, "max": 10, "step": 2, "default": 4}]).params[0]
        self.assertEqual((p.widget, p.step, p.minimum, p.maximum), ("slider", 2, 0, 10))
        for bad in (
            {"type": "integer", "widget": "slider", "default": 1},  # needs min and max
            {"type": "text", "widget": "slider", "default": ""},
            {"type": "integer", "widget": "dial", "default": 1},
            {"type": "integer", "min": 0, "max": 5, "step": 1, "default": 1},  # step only for sliders
            {"type": "integer", "widget": "slider", "min": 0, "max": 5, "step": 0, "default": 1},
        ):
            with self.assertRaises(ManifestError, msg=str(bad)):
                manifest(params=[{"name": "n", **bad}])

    def test_multichoice_color_and_date_defaults_are_checked(self):
        manifest(params=[{"name": "m", "type": "multichoice", "choices": ["a", "b"], "default": ["a"]}])
        manifest(params=[{"name": "c", "type": "color", "default": "#A0b1C2"}])
        manifest(params=[{"name": "d", "type": "date", "default": "2026-02-28"}])
        for bad in (
            {"type": "multichoice", "choices": ["a"], "default": ["z"]},
            {"type": "multichoice", "default": []},  # no choices
            {"type": "color", "default": "red"},
            {"type": "color", "default": "#fff"},
            {"type": "date", "default": "2026-13-01"},
            {"type": "date", "default": "28/02/2026"},
            {"type": "text", "choices": ["a"]},
        ):
            with self.assertRaises(ManifestError, msg=str(bad)):
                manifest(params=[{"name": "x", **bad}])

    def test_the_generated_validation_model_enforces_them(self):
        from web.mod_params import _generate

        from core.mods.registry import Mod

        m = manifest(
            params=[
                {"name": "kinds", "type": "multichoice", "choices": ["a", "b"], "default": ["a"]},
                {"name": "tint", "type": "color", "default": "#00ff00"},
                {"name": "day", "type": "date", "nullable": True},
                {"name": "n", "type": "integer", "widget": "slider", "min": 0, "max": 10, "default": 5},
            ]
        )
        model = _generate(Mod(m, "user", Path("."), True))
        ok = model.model_validate({"kinds": ["a", "b"], "tint": "#AABBCC", "day": "2026-02-28", "n": 3})
        self.assertEqual((ok.kinds, ok.tint, ok.day), (["a", "b"], "#AABBCC", "2026-02-28"))
        self.assertIsNone(model.model_validate({}).day)
        for bad in ({"kinds": ["c"]}, {"tint": "green"}, {"tint": "#12345"}, {"day": "2026-02-30"}, {"day": "tomorrow"}, {"n": 11}):
            with self.assertRaises(Exception, msg=str(bad)):
                model.model_validate(bad)


class ResultTests(unittest.TestCase):
    def test_each_view_becomes_plain_capped_data(self):
        table = R.build_result("table", {"title": "T", "columns": ["a", "b"], "rows": [[1, "x"], [2], [True, None]]})
        self.assertEqual(table["rows"], [[1, "x"], [2, ""], ["yes", ""]])
        self.assertEqual(R.build_result("counters", {"items": {"Files": 12, "Size": "3 MB"}})["items"], [{"label": "Files", "value": "12"}, {"label": "Size", "value": "3 MB"}])
        self.assertEqual(R.build_result("counters", {"items": [("a", 1), {"label": "b", "value": 2}]})["items"][1], {"label": "b", "value": "2"})
        files = R.build_result("files", {"files": ["a.txt", {"path": "b.txt", "label": "big"}]})
        self.assertEqual(files["files"], [{"path": "a.txt"}, {"path": "b.txt", "label": "big"}])
        self.assertEqual(R.build_result("markdown", {"text": "**hi**"})["text"], "**hi**")
        self.assertEqual(R.build_result("message", {"text": "ok", "level": "success"})["level"], "success")

    def test_size_limits(self):
        many = R.build_result("table", {"columns": ["a"], "rows": [[i] for i in range(R.MAX_ROWS + 50)]})
        self.assertEqual((len(many["rows"]), many["truncated"]), (R.MAX_ROWS, True))
        wide = R.build_result("table", {"columns": [str(i) for i in range(50)], "rows": [["x" * 1000] * 50]})
        self.assertEqual(len(wide["columns"]), R.MAX_COLUMNS)
        self.assertEqual(len(wide["rows"][0]), R.MAX_COLUMNS)
        self.assertLessEqual(len(wide["rows"][0][0]), R.MAX_CELL)
        self.assertEqual(len(R.build_result("files", {"files": [f"f{i}" for i in range(R.MAX_FILES + 5)]})["files"]), R.MAX_FILES)
        self.assertEqual(len(R.build_result("markdown", {"text": "x" * 99_999})["text"]), R.MAX_MARKDOWN)
        self.assertEqual(len(R.build_result("counters", {"items": {str(i): i for i in range(99)}})["items"]), R.MAX_COUNTERS)

    def test_mistakes_tell_the_mod_author_what_to_fix(self):
        bad = [
            ("chart", {}),
            ("table", {"rows": []}),
            ("table", {"columns": ["a"], "rows": ["not a row"]}),
            ("counters", {"items": "many"}),
            ("files", {"files": [{"label": "no path"}]}),
            ("markdown", {}),
            ("image", {"path": "x.svg"}),
            ("message", {"text": "hi", "level": "loud"}),
        ]
        for view, fields in bad:
            with self.assertRaises(R.ResultError, msg=view):
                R.build_result(view, fields)

    def test_images_become_data_uris_and_only_real_pictures_are_accepted(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "a.png"
            png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
            result = R.build_result("image", {"path": png, "alt": "chart"})
            self.assertTrue(result["src"].startswith("data:image/png;base64,"))
            self.assertEqual(base64.b64decode(result["src"].split(",")[1]), png.read_bytes())
            self.assertEqual(result["alt"], "chart")
            big = Path(tmp) / "big.png"
            big.write_bytes(b"0" * (R.MAX_IMAGE_BYTES + 1))
            with self.assertRaisesRegex(R.ResultError, "too large"):
                R.build_result("image", {"path": big})
            with self.assertRaisesRegex(R.ResultError, "cannot read"):
                R.build_result("image", {"path": Path(tmp) / "missing.png"})
            with self.assertRaises(R.ResultError):
                R.build_result("image", {"path": Path(tmp) / "x.svg"})  # svg can carry script

    def test_what_an_action_may_return(self):
        self.assertEqual(R.from_return(None), [])
        self.assertEqual(R.from_return("hello")[0]["view"], "message")
        self.assertEqual(R.from_return({"view": "markdown", "text": "x"})[0]["text"], "x")
        self.assertEqual(len(R.from_return(["a", {"view": "counters", "items": {"a": 1}}])), 2)
        for bad in ({"text": "no view"}, 42, [3]):
            with self.assertRaises(R.ResultError):
                R.from_return(bad)

    def test_ctx_result_hands_data_to_the_page_or_logs_it(self):
        seen: list[dict] = []
        ModContext("m", on_result=seen.append).result("counters", title="T", items={"a": 1})
        self.assertEqual(seen[0]["view"], "counters")
        ModContext("m").result("counters", items={"a": 1})  # no page: nothing to send, must not fail
        with self.assertRaises(R.ResultError):
            ModContext("m").result("table")

    def test_the_cli_prints_results_as_text(self):
        import contextlib
        import io

        from cli.console import console_result

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            console_result(R.build_result("table", {"title": "By kind", "columns": ["Kind", "Files"], "rows": [["Video", 3], ["Audio", 12]]}))
            console_result(R.build_result("counters", {"items": {"Files": 15}}))
        text = out.getvalue()
        self.assertIn("By kind", text)
        self.assertRegex(text, r"Kind\s+Files")
        self.assertRegex(text, r"Audio\s+12")
        self.assertIn("Files: 15", text)


class RunResultsTests(ModEnvTestCase):
    CODE = """
        def run(params, ctx):
            ctx.result("counters", title="Overview", items={"Files": 3})
            ctx.result("files", files=["C:/keep/a.txt", "C:/keep/tool.exe"])
            ctx.result("markdown", text="done")
    """

    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        from web.jobs import job_manager
        from web.server import app

        self.jobs = job_manager
        self.client = TestClient(app)
        self.make_mod("reporter", code=self.CODE)
        registry.set_enabled("reporter", True)

    def events(self, job):
        out = []
        while True:
            item = job.events.get(timeout=5)
            if item is None:
                return out
            out.append(item)

    def test_results_are_streamed_to_the_page_and_kept_on_the_job(self):
        job = self.wait(self.jobs.create("reporter", {}))
        self.assertEqual(job.status, "completed")
        self.assertEqual([r["view"] for r in job.results], ["counters", "files", "markdown"])
        sent = [e for e in self.events(job) if e["type"] == "result"]
        self.assertEqual([e["data"]["view"] for e in sent], ["counters", "files", "markdown"])
        self.assertEqual(sent[0]["data"]["job_id"], job.id)

    def test_a_mod_that_reports_in_a_loop_is_cut_off(self):
        self.make_mod("spammer", code="def run(params, ctx):\n    for i in range(100):\n        ctx.result('message', text=str(i))\n")
        registry.set_enabled("spammer", True)
        job = self.wait(self.jobs.create("spammer", {}))
        self.assertEqual(job.status, "completed")
        self.assertEqual(len(job.results), R.MAX_RESULTS_PER_JOB)

    def test_a_result_the_page_cannot_show_fails_the_job_with_a_clear_message(self):
        self.make_mod("sloppy", code="def run(params, ctx):\n    ctx.result('table')\n")
        registry.set_enabled("sloppy", True)
        job = self.wait(self.jobs.create("sloppy", {}))
        self.assertEqual(job.status, "failed")
        self.assertIn("columns", job.error)

    def open_result(self, job, path, reveal=False):
        return self.client.post(f"/api/jobs/{job.id}/results/open", json={"path": path, "reveal": reveal})

    def test_only_files_the_job_listed_can_be_opened(self):
        job = self.wait(self.jobs.create("reporter", {}))
        with mock.patch("web.server.open_path") as opener, mock.patch("web.server.reveal_path") as revealer:
            self.assertEqual(self.open_result(job, "C:/somewhere/else.txt").status_code, 403)
            self.assertEqual(self.client.post("/api/jobs/nope/results/open", json={"path": "x"}).status_code, 404)
            opener.assert_not_called()
            revealer.assert_not_called()

            self.assertEqual(self.open_result(job, "C:/keep/a.txt").status_code, 200)
            opener.assert_called_once_with(Path("C:/keep/a.txt"))
            self.assertEqual(self.open_result(job, "C:/keep/a.txt", reveal=True).status_code, 200)
            revealer.assert_called_once_with(Path("C:/keep/a.txt"))

    def test_a_program_is_never_launched_only_shown_in_its_folder(self):
        job = self.wait(self.jobs.create("reporter", {}))
        with mock.patch("web.server.open_path") as opener, mock.patch("web.server.reveal_path") as revealer:
            self.assertEqual(self.open_result(job, "C:/keep/tool.exe").status_code, 200)
            opener.assert_not_called()
            revealer.assert_called_once_with(Path("C:/keep/tool.exe"))

    def test_a_file_that_is_gone_says_so(self):
        job = self.wait(self.jobs.create("reporter", {}))
        with mock.patch("web.server.open_path", side_effect=FileNotFoundError("gone")):
            res = self.open_result(job, "C:/keep/a.txt")
        self.assertEqual(res.status_code, 404)
        self.assertIn("no longer exists", res.json()["detail"])


class ActionTests(ModEnvTestCase):
    HEADER = 'api_version = 2\n'
    TOML = """
        [[params]]
        name = "host"
        default = "example"
        [[params]]
        name = "port"
        type = "integer"
        default = 80
        min = 1
        max = 65535
        [[params]]
        name = "secret"
        default = "s"
        [[actions]]
        name = "check"
        label = "Test connection"
        params = ["host", "port"]
        [[actions]]
        name = "everything"
        [[actions]]
        name = "ghost"
    """
    CODE = """
        def run(params, ctx):
            pass

        def action_check(params, ctx):
            assert set(params) == {"host", "port"}, params   # only what it declared
            return f"{params['host']}:{params['port']} answers"

        def action_everything(params, ctx):
            ctx.result("counters", items={"params": len(params)})
            return {"view": "message", "level": "success", "text": "fine"}
    """

    def setUp(self):
        super().setUp()
        import textwrap

        from fastapi.testclient import TestClient
        from web.server import app

        self.client = TestClient(app)
        self.make_mod("pinger", textwrap.dedent(self.TOML), self.CODE, header=self.HEADER)
        registry.set_enabled("pinger", True)

    def call(self, action, params=None, mod="pinger"):
        return self.client.post(f"/api/mods/{mod}/actions/{action}", json={"params": params or {}})

    def test_an_action_runs_the_named_function_with_only_its_params(self):
        res = self.call("check", {"host": "toolbox.test", "port": 8080, "secret": "never sent on"})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["results"], [{"view": "message", "title": "", "text": "toolbox.test:8080 answers", "level": "info"}])

    def test_results_come_from_ctx_result_and_the_return_value(self):
        body = self.call("everything", {}).json()
        self.assertTrue(body["ok"])
        self.assertEqual([r["view"] for r in body["results"]], ["counters", "message"])
        self.assertEqual(body["results"][0]["items"], [{"label": "params", "value": "3"}])

    def test_the_params_are_validated_like_a_run(self):
        self.assertEqual(self.call("check", {"port": 0}).status_code, 422)
        self.assertEqual(self.call("check", {"port": "eighty"}).status_code, 422)

    def test_only_declared_actions_of_enabled_mods_can_be_called(self):
        self.assertEqual(self.call("run").status_code, 404, "run is not an action")
        self.assertEqual(self.call("nope").status_code, 404)
        self.assertEqual(self.call("check", mod="convert").status_code, 404)
        registry.set_enabled("pinger", False)
        self.assertEqual(self.call("check").status_code, 404)

    def test_a_declared_action_without_a_function_is_reported(self):
        res = self.call("ghost")
        self.assertEqual(res.status_code, 500)
        self.assertIn("action_ghost", res.json()["detail"])

    def test_a_crashing_action_is_a_message_not_a_server_error(self):
        self.make_mod(
            "crasher",
            '[[actions]]\nname = "boom"\n',
            "def run(params, ctx):\n    pass\n\ndef action_boom(params, ctx):\n    raise RuntimeError('it broke')\n",
            header=self.HEADER,
        )
        registry.set_enabled("crasher", True)
        with self.assertLogs("web.server", "ERROR"):  # the failure is logged for the developer, shown to the user
            body = self.call("boom", mod="crasher").json()
        self.assertFalse(body["ok"])
        self.assertEqual((body["results"][0]["level"], body["results"][0]["text"]), ("error", "it broke"))

    def test_an_unshowable_return_value_is_reported_too(self):
        self.make_mod(
            "muddled",
            '[[actions]]\nname = "odd"\n',
            "def run(params, ctx):\n    pass\n\ndef action_odd(params, ctx):\n    return {'no': 'view'}\n",
            header=self.HEADER,
        )
        registry.set_enabled("muddled", True)
        body = self.call("odd", mod="muddled").json()
        self.assertFalse(body["ok"])
        self.assertIn("cannot be shown", body["results"][0]["text"])

    def test_a_slow_action_is_given_up_on(self):
        self.make_mod(
            "slowpoke",
            '[[actions]]\nname = "nap"\n',
            "import time\n\ndef run(params, ctx):\n    pass\n\ndef action_nap(params, ctx):\n    time.sleep(2)\n",
            header=self.HEADER,
        )
        registry.set_enabled("slowpoke", True)
        with mock.patch("web.server.ACTION_TIMEOUT_SECONDS", 0.2):
            body = self.call("nap", mod="slowpoke").json()
        self.assertFalse(body["ok"])
        self.assertIn("took longer", body["results"][0]["text"])

    def test_actions_only_exist_for_declared_names_in_the_manifest(self):
        with self.assertRaisesRegex(ManifestError, "unknown param"):
            manifest(actions=[{"name": "go", "params": ["ghost"]}])
        with self.assertRaisesRegex(ManifestError, "unique"):
            manifest(actions=[{"name": "go"}, {"name": "go"}])


class IconTests(unittest.TestCase):
    def test_the_python_and_frontend_icon_lists_agree(self):
        source = (ROOT / "web/frontend/src/lib/modIcons.ts").read_text(encoding="utf-8")
        block = source[source.index("const MOD_ICONS"):]
        block = block[: block.index("};")]
        keys = re.findall(r'^\s+(?:"([a-z0-9-]+)"|([a-z0-9]+)):', block, flags=re.M)
        frontend = sorted(a or b for a, b in keys)
        self.assertEqual(frontend, sorted(ICON_NAMES))
        self.assertEqual(len(set(ICON_NAMES)), len(ICON_NAMES))

    def test_the_build_prompt_lists_the_icons_and_categories(self):
        from core.mods.groups import BUILTIN_GROUP_NAMES
        from core.mods.prompts import BUILD_PROMPT

        for icon in ICON_NAMES:
            self.assertIn(icon, BUILD_PROMPT)
        for name in BUILTIN_GROUP_NAMES:
            self.assertIn(f"- {name}:", BUILD_PROMPT)
        self.assertNotIn("@", BUILD_PROMPT.replace("@API", ""))


class ExampleModTests(ModEnvTestCase):
    """The shipped examples install through the real flow and do what their comments say."""

    def install_example(self, name: str):
        preview = install.prepare(str(ROOT / "examples/mods" / name))
        install.commit(preview["token"], enable=True)
        return preview

    def test_every_example_has_a_valid_manifest(self):
        for folder in sorted((ROOT / "examples/mods").iterdir()):
            m = load_manifest(folder / "mod.toml")
            self.assertIn(m.id, folder.name)

    def test_count_files_lives_in_the_files_section_and_still_works_on_api_1(self):
        preview = self.install_example("count-files")
        self.assertEqual(preview["placement"]["name"], "Files")
        self.assertEqual(registry.get("count-files").manifest.api_version, 1)

    def test_folder_report_end_to_end(self):
        from fastapi.testclient import TestClient
        from web.jobs import job_manager
        from web.server import app

        preview = self.install_example("folder-report")
        self.assertEqual(preview["placement"], {"name": "Files", "new_section": False, "near_miss": None})
        self.assertEqual(preview["warnings"], [])

        data = self.root / "library"
        (data / "sub").mkdir(parents=True)
        (data / ".hidden").mkdir()
        (data / "a.mkv").write_bytes(b"0" * 3000)
        (data / "b.mp3").write_bytes(b"0" * 1000)
        (data / "sub" / "c.srt").write_bytes(b"0" * 10)
        (data / "sub" / "notes.txt").write_bytes(b"0" * 20)
        (data / ".hidden" / "d.mkv").write_bytes(b"0" * 5000)

        job = self.wait(job_manager.create("folder-report", {"folder": str(data), "include_hidden": True}))
        self.assertEqual((job.status, job.error), ("completed", None))
        by_view = {r["view"]: r for r in job.results}
        self.assertEqual([r["view"] for r in job.results], ["counters", "table", "files", "markdown"])
        counters = {i["label"]: i["value"] for i in by_view["counters"]["items"]}
        self.assertEqual(counters["Files"], "5")
        self.assertEqual([row[0] for row in by_view["table"]["rows"]][0], "Video")
        self.assertEqual(by_view["files"]["files"][0]["path"], str(data / ".hidden" / "d.mkv"))
        self.assertIn(str(data / "a.mkv"), job.result_paths())

        # hidden files are left out unless asked for (the default), and the params are all plain values
        plain = self.wait(job_manager.create("folder-report", {"folder": str(data)}))
        self.assertEqual({i["label"]: i["value"] for i in plain.results[0]["items"]}["Files"], "4")
        job = self.wait(
            job_manager.create(
                "folder-report",
                {"folder": str(data), "kinds": ["video"], "include_hidden": False, "recursive": False, "show_files": False},
            )
        )
        self.assertEqual([r["view"] for r in job.results], ["counters", "table", "markdown"])
        counters = {i["label"]: i["value"] for i in job.results[0]["items"]}
        self.assertEqual(counters["Files"], "1")

        empty = self.wait(job_manager.create("folder-report", {"folder": str(data), "kinds": ["image"]}))
        self.assertEqual([(r["view"], r["level"]) for r in empty.results], [("message", "warning")])

        # the "Check folder" button
        client = TestClient(app)
        res = client.post("/api/mods/folder-report/actions/check_folder", json={"params": {"folder": str(data), "recursive": True}})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIn("5 file(s)", res.json()["results"][0]["text"])
        res = client.post("/api/mods/folder-report/actions/check_folder", json={"params": {"folder": str(data / "nope")}})
        self.assertEqual(res.json()["results"][0]["level"], "error")

    def test_folder_report_rejects_values_the_form_would_never_send(self):
        from web.jobs import job_manager

        self.install_example("folder-report")
        for bad in ({"kinds": ["podcasts"]}, {"min_size_mb": 9999}, {"since": "last week"}, {"top": 0}, {"sort_by": "colour"}):
            with self.assertRaises(ValueError, msg=str(bad)):
                job_manager.create("folder-report", {"folder": str(self.root), **bad})

    def test_the_example_form_declares_what_the_page_needs(self):
        m = registry.get("folder-report") or self.install_example("folder-report") and registry.get("folder-report")
        by_name = {p.name: p for p in m.manifest.params}
        self.assertEqual(by_name["min_size_mb"].widget, "slider")
        self.assertEqual(by_name["kinds"].type, "multichoice")
        self.assertEqual(by_name["since"].type, "date")
        self.assertEqual(by_name["top"].show_if.param, "show_files")
        self.assertEqual([s.id for s in m.manifest.sections], ["include", "report", "advanced"])
        self.assertEqual(m.manifest.sections[2].show_if.param, "advanced")
        self.assertEqual([a.name for a in m.manifest.actions], ["check_folder"])
        self.assertEqual(m.manifest.accent, "files")


if __name__ == "__main__":
    unittest.main()
