"""Tests for theme mods: validation, contrast rules, install, settings and the built-in themes.

Run with::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import re
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from modenv import ROOT, ModEnvTestCase  # noqa: E402

from core.mods import ManifestError, ModError, install, parse_manifest, prompts, registry  # noqa: E402
from core.mods import theme as t  # noqa: E402
from core.mods.install import InstallError  # noqa: E402
from core.mods.manifest import load_manifest  # noqa: E402

THEME_IDS = {"theme-default", "theme-high-contrast"}


def theme_manifest(theme, **extra):
    return {"id": "look", "name": "Look", "type": "theme", "api_version": 2, "theme": theme, **extra}


class ParseThemeTests(unittest.TestCase):
    def test_a_partial_theme_sets_only_what_it_names(self):
        m = parse_manifest(theme_manifest({"light": {"primary": "#268bd2"}}))
        self.assertTrue(m.is_theme)
        self.assertEqual(set(m.theme.light), {"primary"})
        self.assertEqual(m.theme.dark, {})
        # everything else falls back to the default palette
        palette = m.theme.palette("light")
        self.assertEqual(palette["primary"], "204.8 69.4% 48.6%")
        self.assertEqual(palette["background"], t.DEFAULT_LIGHT["background"])
        self.assertEqual(set(palette), set(t.COLOR_TOKENS))
        self.assertEqual(m.theme.palette("dark"), t.DEFAULT_DARK)

    def test_colours_can_be_hex_hsl_or_rgb_and_are_normalised(self):
        expected = "0 100% 50%"
        for written in ("#ff0000", "#f00", "hsl(0, 100%, 50%)", "hsl(0 100% 50%)", "hsl(0deg 100% 50%)", "rgb(255, 0, 0)", "rgb(255 0 0)"):
            self.assertEqual(t.parse_color(written, "x"), expected, written)

    def test_groups_set_the_category_accent_for_both_modes_and_a_mode_wins(self):
        m = parse_manifest(theme_manifest({"groups": {"files": "#dc322f"}, "dark": {"category-files": "#ff8080"}}))
        self.assertEqual(m.theme.light["category-files"], "1 71.2% 52.4%")
        self.assertEqual(m.theme.dark["category-files"], "0 100% 75.1%")

    def test_radius_and_font(self):
        m = parse_manifest(theme_manifest({"radius": "0.5rem", "font": "serif"}))
        self.assertEqual((m.theme.radius, m.theme.font), ("0.5rem", "serif"))
        resolved = m.theme.to_dict()["resolved"]
        self.assertEqual(resolved["radius"], "0.5rem")
        self.assertIn("Georgia", resolved["font_stack"])
        self.assertEqual(parse_manifest(theme_manifest({})).theme.to_dict()["resolved"]["radius"], t.DEFAULT_RADIUS)

    def test_no_css_can_be_smuggled_in(self):
        hostile = [
            "url(https://evil.example/x.png)",
            "#fff; background: url(x)",
            "@import 'x'",
            "var(--foreground)",
            "calc(1px + 2px)",
            "red",  # named colours are not accepted
            "#ff0000ff",  # no transparency
            "hsl(0, 100%, 50%, 0.5)",
            "rgb(300, 0, 0)",
            "expression(alert(1))",
            "",
            42,
        ]
        for value in hostile:
            with self.assertRaises(ManifestError, msg=repr(value)):
                parse_manifest(theme_manifest({"light": {"background": value}}))

    def test_only_known_tokens_and_keys_exist(self):
        with self.assertRaisesRegex(ManifestError, "unknown token 'sparkle'"):
            parse_manifest(theme_manifest({"light": {"sparkle": "#ffffff"}}))
        with self.assertRaisesRegex(ManifestError, "unknown key 'css'"):
            parse_manifest(theme_manifest({"css": "body { display: none }"}))
        with self.assertRaisesRegex(ManifestError, "unknown token 'nothing'"):
            parse_manifest(theme_manifest({"groups": {"nothing": "#ffffff"}}))

    def test_bad_radius_and_font_are_refused(self):
        for radius in ("10", "1em", "calc(1rem)", "99rem", "-1rem", 5):
            with self.assertRaises(ManifestError, msg=repr(radius)):
                parse_manifest(theme_manifest({"radius": radius}))
        with self.assertRaisesRegex(ManifestError, "font"):
            parse_manifest(theme_manifest({"font": "Comic Sans MS"}))
        with self.assertRaisesRegex(ManifestError, "font"):
            parse_manifest(theme_manifest({"font": "url(x)"}))

    def test_a_theme_is_data_only(self):
        for extra in ({"entry": "main.py"}, {"params": [{"name": "x"}]}, {"ui": {}}, {"run": {}}, {"permissions": {}}, {"group": "Media"}, {"icon": "film"}):
            with self.assertRaisesRegex(ManifestError, "cannot have"):
                parse_manifest(theme_manifest({}, **extra))
        with self.assertRaisesRegex(ManifestError, "needs a \\[theme\\]"):
            parse_manifest({"id": "look", "name": "Look", "type": "theme", "api_version": 2})

    def test_a_tool_cannot_carry_a_theme_table(self):
        with self.assertRaisesRegex(ManifestError, "only belongs in a theme"):
            parse_manifest({"id": "x", "name": "X", "theme": {}, "ui": {"run_mode": "run"}})

    def test_themes_need_api_2_and_old_apps_get_a_clear_message(self):
        with self.assertRaisesRegex(ManifestError, "API version 2"):
            parse_manifest({"id": "look", "name": "Look", "type": "theme", "theme": {}})
        with self.assertRaisesRegex(ManifestError, "API version 2"):
            parse_manifest({"id": "look", "name": "Look", "type": "theme", "api_version": 1, "theme": {}})
        with self.assertRaisesRegex(ManifestError, "supports"):
            parse_manifest({"id": "look", "name": "Look", "type": "theme", "api_version": 99, "theme": {}})

    def test_unknown_type(self):
        with self.assertRaisesRegex(ManifestError, "'type' must be"):
            parse_manifest({"id": "x", "name": "X", "type": "plugin"})


class ContrastTests(unittest.TestCase):
    def test_the_default_palette_passes_every_rule_without_warnings(self):
        problems, warnings = t.check_contrast(t.DEFAULT_LIGHT, t.DEFAULT_DARK)
        self.assertEqual((problems, warnings), ([], []))

    def test_contrast_ratio_matches_wcag(self):
        self.assertAlmostEqual(t.contrast_ratio("0 0% 0%", "0 0% 100%"), 21.0, places=1)
        self.assertAlmostEqual(t.contrast_ratio("0 0% 50%", "0 0% 50%"), 1.0, places=2)

    def test_unreadable_text_on_the_page_is_refused(self):
        with self.assertRaisesRegex(ManifestError, "'foreground' on 'background'"):
            parse_manifest(theme_manifest({"light": {"foreground": "#f7f7f9"}}))

    def test_a_theme_cannot_hide_error_text_or_the_remove_button(self):
        cases = [
            {"light": {"danger-text": "#f7f7f9"}},  # invisible error text
            {"dark": {"danger-text": "#0f121a"}},
            {"light": {"warning-text": "#ffffff"}},  # invisible caution text
            {"light": {"destructive-foreground": "#c62f2f"}},  # "Remove" written in its own colour
            {"dark": {"destructive": "#ffffff"}},
        ]
        for theme in cases:
            with self.assertRaisesRegex(ManifestError, "unsafe to read", msg=str(theme)):
                parse_manifest(theme_manifest(theme))

    def test_danger_colours_must_stay_red_or_orange(self):
        for token in ("destructive", "danger", "danger-text"):
            with self.assertRaisesRegex(ManifestError, "red or orange", msg=token):
                parse_manifest(theme_manifest({"light": {token: "#1a4fd6"}}))  # readable, but blue: looks harmless
        parse_manifest(theme_manifest({"light": {"destructive": "#c2410c"}}))  # orange is fine

    def test_other_low_contrast_pairs_are_warnings_not_refusals(self):
        m = parse_manifest(theme_manifest({"light": {"muted-foreground": "#b5b8c4"}}))
        self.assertTrue(any("muted-foreground" in w for w in m.theme.warnings))
        self.assertEqual(parse_manifest(theme_manifest({})).theme.warnings, ())

    def test_syntax_colours_can_be_set_and_are_contrast_checked(self):
        m = parse_manifest(theme_manifest({"dark": {"syntax-keyword": "#ff79c6"}}))
        self.assertEqual(m.theme.dark["syntax-keyword"], t.parse_color("#ff79c6", "x"))
        m = parse_manifest(theme_manifest({"light": {"syntax-comment": "#d0d0d0"}}))
        self.assertTrue(any("syntax-comment" in w for w in m.theme.warnings))


class DefaultPaletteSyncTests(unittest.TestCase):
    """The stylesheet is what shows before any theme loads; it must match the palette the server knows."""

    css = (ROOT / "web/frontend/src/index.css").read_text(encoding="utf-8")

    def variables(self, selector: str) -> dict[str, str]:
        block = re.search(rf"{re.escape(selector)}\s*\{{([^}}]*)\}}", self.css).group(1)
        return dict(re.findall(r"--([a-z-]+):\s*([^;]+);", block))

    def test_light_and_dark_defaults_match_the_stylesheet(self):
        light, dark = self.variables(":root"), self.variables(".dark")
        for name in t.COLOR_TOKENS:
            self.assertEqual(light.get(name), t.DEFAULT_LIGHT[name], f"light --{name}")
            self.assertEqual(dark.get(name), t.DEFAULT_DARK[name], f"dark --{name}")
        self.assertEqual(light["radius"], t.DEFAULT_RADIUS)
        self.assertEqual(light["font-sans"], t.FONTS[t.DEFAULT_FONT])

    def test_tailwind_maps_every_token(self):
        config = (ROOT / "web/frontend/tailwind.config.js").read_text(encoding="utf-8")
        for name in t.COLOR_TOKENS:
            self.assertIn(f"var(--{name})", config, name)

    def test_the_theme_prompt_lists_every_token(self):
        for name in t.COLOR_TOKENS:
            self.assertIn(f"- {name}:", prompts.THEME_PROMPT, name)
        self.assertNotIn("@TOKENS@", prompts.THEME_PROMPT)
        self.assertIn("type = \"theme\"", prompts.THEME_PROMPT)


class BuiltinThemeTests(ModEnvTestCase):
    def test_the_default_and_high_contrast_themes_ship_as_theme_mods(self):
        themes = {m.id: m for m in registry.all() if m.is_theme}
        self.assertEqual(set(themes), THEME_IDS)
        for mod in themes.values():
            self.assertTrue(mod.builtin and mod.enabled)
            self.assertEqual(mod.manifest.theme.warnings, ())
        self.assertEqual(themes["theme-default"].manifest.theme.light, {}, "the default sets nothing")
        self.assertEqual([m.id for m in registry.all() if m.is_theme], ["theme-default", "theme-high-contrast"])

    def test_high_contrast_really_is_high_contrast(self):
        theme = registry.get("theme-high-contrast").manifest.theme
        for mode in ("light", "dark"):
            palette = theme.palette(mode)
            self.assertGreaterEqual(t.contrast_ratio(palette["foreground"], palette["background"]), 15)
            self.assertGreaterEqual(t.contrast_ratio(palette["muted-foreground"], palette["background"]), 7)

    def test_themes_have_no_code_to_load_or_run(self):
        with self.assertRaisesRegex(ModError, "theme"):
            registry.get("theme-default").load_module()
        from web.jobs import job_manager

        with self.assertRaisesRegex(ValueError, "theme"):
            job_manager.create("theme-default", {})

    def test_themes_are_not_commands(self):
        from fastapi.testclient import TestClient
        from web.server import app

        client = TestClient(app)
        names = {c["name"] for c in client.get("/api/commands").json()["commands"]}
        self.assertTrue(names and not (names & THEME_IDS))
        self.assertEqual(client.get("/api/commands/theme-default/schema").status_code, 404)

    def test_the_cli_builds_no_subcommand_for_a_theme(self):
        import argparse

        from cli import mods_cli

        self.make_theme("solar")
        registry.set_enabled("solar", True)
        parser = argparse.ArgumentParser()
        mods_cli.register(parser.add_subparsers(dest="command"))
        choices = parser._subparsers._group_actions[0].choices
        self.assertIn("mods", choices)
        self.assertFalse(set(choices) & (THEME_IDS | {"solar"}))


class InstallThemeTests(ModEnvTestCase):
    THEME = 'id = "sol"\nname = "Sol"\ntype = "theme"\napi_version = 2\nversion = "1.2.0"\n[theme]\nradius = "0.5rem"\n[theme.light]\nprimary = "#1d5fa6"\n'

    def stage(self, location, **kw):
        preview = install.prepare(str(location), **kw)
        self.addCleanup(install.discard, preview["token"])
        return preview

    def test_a_theme_installs_from_a_single_toml_file(self):
        f = self.root / "sol.toml"
        f.write_text(self.THEME, encoding="utf-8")
        preview = self.stage(f)
        self.assertEqual(preview["manifest"]["type"], "theme")
        self.assertIsNone(preview["placement"], "a theme is not placed in a menu section")
        self.assertEqual(preview["warnings"], [])
        self.assertEqual([x["path"] for x in preview["files"]], ["mod.toml"])
        install.commit(preview["token"], enable=True)
        self.assertTrue(registry.get("sol").enabled)
        self.assertEqual(registry.get("sol").manifest.theme.radius, "0.5rem")

    def test_a_theme_installs_from_a_folder_without_a_main_py(self):
        folder = self.root / "sol"
        folder.mkdir()
        (folder / "mod.toml").write_text(self.THEME, encoding="utf-8")
        install.commit(self.stage(folder)["token"])
        self.assertIsNotNone(registry.get("sol"))
        self.assertFalse(registry.get("sol").enabled, "installed themes start off until turned on, like any mod")

    def test_a_theme_installs_from_a_zip(self):
        archive = self.root / "sol.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("sol/mod.toml", self.THEME)
        preview = self.stage(archive)
        install.commit(preview["token"], enable=True)
        self.assertEqual(registry.get("sol").manifest.version, "1.2.0")

    def test_a_single_toml_that_is_not_a_theme_is_refused(self):
        f = self.root / "tool.toml"
        f.write_text('id = "tool"\nname = "Tool"\n', encoding="utf-8")
        with self.assertRaisesRegex(InstallError, "can only be a theme"):
            install.prepare(str(f))
        (self.root / "broken.toml").write_text("this is [not toml", encoding="utf-8")
        with self.assertRaisesRegex(InstallError, "not valid TOML"):
            install.prepare(str(self.root / "broken.toml"))

    def test_a_dangerous_theme_is_refused_with_a_clear_message(self):
        f = self.root / "evil.toml"
        f.write_text(self.THEME + 'background = "url(https://evil.example/a.png)"\n', encoding="utf-8")
        with self.assertRaisesRegex(InstallError, "not a colour I accept"):
            install.prepare(str(f))
        g = self.root / "invisible.toml"
        g.write_text(self.THEME + 'danger-text = "#f6f7f9"\n', encoding="utf-8")
        with self.assertRaisesRegex(InstallError, "unsafe to read"):
            install.prepare(str(g))
        self.assertEqual(list((self.data_dir / "mods-staging").glob("*")) if (self.data_dir / "mods-staging").exists() else [], [])

    def test_contrast_warnings_appear_in_the_trust_prompt(self):
        f = self.root / "dim.toml"
        f.write_text(self.THEME + 'muted-foreground = "#b5b8c4"\n', encoding="utf-8")
        preview = self.stage(f)
        self.assertTrue(any("muted-foreground" in w for w in preview["warnings"]))

    def test_code_next_to_a_theme_is_flagged(self):
        folder = self.root / "sneaky"
        folder.mkdir()
        (folder / "mod.toml").write_text(self.THEME.replace('"sol"', '"sneaky"', 1), encoding="utf-8")
        (folder / "payload.py").write_text("print('hi')\n", encoding="utf-8")
        preview = self.stage(folder)
        self.assertTrue(any("payload.py" in w and "ever run" in w for w in preview["warnings"]))

    def test_a_listing_that_promises_a_theme_cannot_deliver_a_tool(self):
        folder = self.root / "tooly"
        folder.mkdir()
        (folder / "mod.toml").write_text('id = "tooly"\nname = "T"\n[ui]\nrun_mode = "run"\n', encoding="utf-8")
        (folder / "main.py").write_text("def run(params, ctx):\n    pass\n", encoding="utf-8")
        with self.assertRaisesRegex(InstallError, "listing says this is a theme but the code is a tool"):
            install.prepare(str(folder), expect={"id": "tooly", "type": "theme"})


class ActiveThemeTests(ModEnvTestCase):
    def setUp(self):
        super().setUp()
        from fastapi.testclient import TestClient
        from web.server import app

        self.client = TestClient(app)
        self.make_theme("sol")
        registry.set_enabled("sol", True)

    def test_the_theme_and_mode_are_saved_in_settings(self):
        s = self.client.get("/api/settings").json()
        self.assertEqual((s["theme"], s["color_mode"]), ("theme-default", "system"))
        res = self.client.patch("/api/settings", json={"theme": "sol", "color_mode": "dark"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual((res.json()["theme"], res.json()["color_mode"]), ("sol", "dark"))
        self.assertEqual(self.client.get("/api/settings").json()["theme"], "sol")

    def test_bad_values_are_rejected(self):
        self.assertEqual(self.client.patch("/api/settings", json={"theme": "../x"}).status_code, 422)
        self.assertEqual(self.client.patch("/api/settings", json={"color_mode": "purple"}).status_code, 422)

    def test_syntax_highlighting_settings_are_saved(self):
        s = self.client.get("/api/settings").json()
        self.assertEqual((s["syntax_code"], s["syntax_logs"], s["syntax_scheme"]), (True, True, "theme"))
        res = self.client.patch("/api/settings", json={"syntax_logs": False, "syntax_scheme": "github"})
        self.assertEqual(res.status_code, 200, res.text)
        s = self.client.get("/api/settings").json()
        self.assertEqual((s["syntax_code"], s["syntax_logs"], s["syntax_scheme"]), (True, False, "github"))
        self.assertEqual(self.client.patch("/api/settings", json={"syntax_scheme": "neon"}).status_code, 422)

    def test_an_unknown_stored_scheme_falls_back_to_the_theme(self):
        from core.settings_store import save_settings

        save_settings(syntax_scheme="removed-scheme")
        self.assertEqual(self.client.get("/api/settings").json()["syntax_scheme"], "theme")

    def test_turning_off_the_active_theme_returns_to_the_default(self):
        self.client.patch("/api/settings", json={"theme": "sol"})
        registry.set_enabled("sol", False)
        self.assertEqual(self.client.get("/api/settings").json()["theme"], "theme-default")

    def test_removing_the_active_theme_returns_to_the_default(self):
        self.client.patch("/api/settings", json={"theme": "sol"})
        install.remove("sol")
        self.assertEqual(self.client.get("/api/settings").json()["theme"], "theme-default")

    def test_turning_off_another_theme_keeps_the_choice(self):
        self.make_theme("other")
        registry.set_enabled("other", True)
        self.client.patch("/api/settings", json={"theme": "sol"})
        registry.set_enabled("other", False)
        self.assertEqual(self.client.get("/api/settings").json()["theme"], "sol")

    def test_safe_mode_leaves_only_the_built_in_themes(self):
        from unittest import mock

        with mock.patch.dict("os.environ", {"TOOLBOX_NO_MODS": "1"}):
            registry.reload()
            self.assertEqual({m.id for m in registry.all() if m.is_theme}, THEME_IDS)
        registry.reload()
        self.assertIn("sol", {m.id for m in registry.all() if m.is_theme})

    def test_the_mods_api_carries_the_resolved_theme_for_the_page(self):
        mods = {m["id"]: m for m in self.client.get("/api/mods").json()["mods"]}
        theme = mods["sol"]["theme"]
        self.assertEqual(mods["sol"]["type"], "theme")
        self.assertEqual(set(theme["resolved"]["light"]), set(t.COLOR_TOKENS))
        self.assertEqual(len(theme["swatches"]["light"]), len(t.SWATCH_TOKENS))
        self.assertTrue(all(re.fullmatch(r"#[0-9a-f]{6}", c) for c in theme["swatches"]["dark"]))
        self.assertIsNone(mods["convert"]["theme"])


class ThemeMarketTests(unittest.TestCase):
    def entry(self, **extra):
        return {"id": "sol", "name": "Sol", "repo": "https://github.com/someone/sol", "commit": "d" * 40, **extra}

    def test_type_and_swatches(self):
        from core.mods import market

        parsed = market.parse_entry(self.entry(type="theme", swatches=["#FDF6E3", "#268bd2"]))
        self.assertEqual((parsed["type"], parsed["swatches"], parsed["group"]), ("theme", ["#fdf6e3", "#268bd2"], ""))
        self.assertEqual(market.parse_entry(self.entry())["type"], "tool")
        self.assertTrue(market.matches(parsed, "theme"))

    def test_bad_swatches_and_types_are_skipped_not_fatal(self):
        from core.mods import market

        for bad in ({"swatches": ["red"]}, {"swatches": "#ffffff"}, {"swatches": ["#ffffff"] * 9}, {"type": "plugin"}):
            with self.assertRaises(ValueError, msg=str(bad)):
                market.parse_entry(self.entry(**bad))
        entries, problems = market.parse_index({"format": 1, "mods": [self.entry(type="nope"), self.entry(id="ok")]})
        self.assertEqual(([e["id"] for e in entries], len(problems)), (["ok"], 1))


class ExampleThemeTests(unittest.TestCase):
    def test_the_solarized_example_is_valid_and_has_no_warnings(self):
        m = load_manifest(ROOT / "examples/mods/solarized-theme/mod.toml")
        self.assertEqual((m.id, m.type, m.api_version), ("solarized", "theme", 2))
        self.assertEqual(m.theme.warnings, ())
        self.assertEqual(m.theme.radius, "0.5rem")
        self.assertEqual(len(m.theme.light["category-files"].split()), 3)


if __name__ == "__main__":
    unittest.main()
