"""Tests for mod categories (the `group` of a mod): normalising names, section order, near-misses.

Run with::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from modenv import ModEnvTestCase  # noqa: E402

from core.mods import ManifestError, install, parse_manifest, registry  # noqa: E402
from core.mods.groups import (  # noqa: E402
    BUILTIN_GROUP_NAMES,
    canonical_group,
    clean_group,
    group_rank,
    near_miss,
)

BUILTIN_SECTIONS = ["Files", "Media", "Subtitles", "Experimental"]


def sections(mods) -> list[str]:
    """The sections in on-screen order (each once), for the tools among *mods*."""
    out: list[str] = []
    for mod in mods:
        if not mod.is_theme and mod.manifest.group not in out:
            out.append(mod.manifest.group)
    return out


class GroupNameTests(unittest.TestCase):
    def test_case_and_spacing_do_not_matter(self):
        for spelling in ("media", "Media", " Media ", "MEDIA", "  me   dia"[:0] or "\tmedia\n"):
            self.assertEqual(canonical_group(spelling), "Media", repr(spelling))
        self.assertEqual(clean_group("  My   Tools "), "My Tools")

    def test_an_empty_name_is_the_default_category(self):
        self.assertEqual(canonical_group(""), "Other")
        self.assertEqual(canonical_group("   "), "Other")

    def test_a_new_name_keeps_the_authors_spelling_unless_one_exists(self):
        self.assertEqual(canonical_group("My Tools"), "My Tools")
        self.assertEqual(canonical_group("my tools", known=["My Tools"]), "My Tools")

    def test_near_misses(self):
        self.assertEqual(near_miss("Subtitle"), "Subtitles")
        self.assertEqual(near_miss("Sub-titles"), "Subtitles")
        self.assertEqual(near_miss("File"), "Files")
        self.assertEqual(near_miss("Others"), "Other")
        self.assertEqual(near_miss("Medias"), "Media")
        self.assertEqual(near_miss("Experimentl"), "Experimental")

    def test_names_that_merge_or_differ_are_not_near_misses(self):
        self.assertIsNone(near_miss("media"), "a case difference merges, it is not a lookalike")
        self.assertIsNone(near_miss("Downloads"))
        self.assertIsNone(near_miss("My Tools"))
        self.assertIsNone(near_miss("Film"), "different word, not a typo of Files")

    def test_built_in_sections_have_a_fixed_order_then_new_ones_alphabetically(self):
        names = ["Zebra", "Other", "alpha", "Experimental", "Files", "Media", "Subtitles"]
        ordered = sorted(names, key=group_rank)
        self.assertEqual(ordered, [*BUILTIN_GROUP_NAMES, "alpha", "Zebra"])


class ManifestGroupTests(unittest.TestCase):
    def test_the_manifest_normalises_the_group(self):
        for spelling in ("media", "Media", " Media "):
            m = parse_manifest({"id": "demo", "name": "Demo", "group": spelling, "ui": {"run_mode": "run"}})
            self.assertEqual(m.group, "Media", repr(spelling))

    def test_the_default_group_is_other(self):
        self.assertEqual(parse_manifest({"id": "demo", "name": "Demo", "ui": {"run_mode": "run"}}).group, "Other")

    def test_group_must_be_text(self):
        with self.assertRaises(ManifestError):
            parse_manifest({"id": "demo", "name": "Demo", "group": 3, "ui": {"run_mode": "run"}})


class SectionOrderTests(ModEnvTestCase):
    def test_the_built_in_sections_come_in_their_fixed_order(self):
        self.assertEqual(sections(registry.all()), BUILTIN_SECTIONS)

    def test_case_variants_all_land_in_the_same_section(self):
        for i, spelling in enumerate(("media", "Media", " Media ")):
            self.make_mod(f"m{i}", header=f'group = "{spelling}"\n')
        self.assertEqual(sections(registry.all()), BUILTIN_SECTIONS, "no second, lookalike section")
        self.assertEqual({registry.get(f"m{i}").manifest.group for i in range(3)}, {"Media"})

    def test_a_mod_order_never_moves_a_built_in_section(self):
        self.make_mod("greedy", header='group = "Media"\norder = 1\n')
        self.make_mod("greedier", header='group = "Subtitles"\norder = -50\n')
        self.assertEqual(sections(registry.all()), BUILTIN_SECTIONS)

    def test_a_low_order_does_not_lift_a_new_section_above_the_built_in_ones(self):
        self.make_mod("mine", header='group = "My Tools"\norder = 1\n')
        self.assertEqual(sections(registry.all()), [*BUILTIN_SECTIONS, "My Tools"])

    def test_new_sections_are_alphabetical_and_mods_inside_sort_by_order_then_name(self):
        self.make_mod("z1", header='group = "Zeta"\norder = 5\n')
        self.make_mod("a1", header='group = "Alpha"\norder = 50\n')
        self.make_mod("a2", header='group = "Alpha"\norder = 5\n')
        self.make_mod("a3", header='group = "Alpha"\norder = 5\n')
        mods = registry.all()
        self.assertEqual(sections(mods), [*BUILTIN_SECTIONS, "Alpha", "Zeta"])
        self.assertEqual([m.id for m in mods if m.manifest.group == "Alpha"], ["a2", "a3", "a1"])

    def test_other_is_a_built_in_section_and_comes_before_new_ones(self):
        self.make_mod("plain")
        self.make_mod("mine", header='group = "Aardvark"\n')
        self.assertEqual(sections(registry.all()), [*BUILTIN_SECTIONS, "Other", "Aardvark"])

    def test_two_spellings_of_a_new_category_share_one_section(self):
        self.make_mod("first", header='group = "My Tools"\n')
        self.make_mod("second", header='group = "my tools"\n')
        self.assertEqual(sections(registry.all()), [*BUILTIN_SECTIONS, "My Tools"])
        self.assertEqual(registry.get("second").manifest.group, "My Tools")
        self.assertEqual(registry.notices(), [], "case differences are merged silently")

    def test_themes_are_not_part_of_the_tool_sections(self):
        self.make_theme("looks")
        self.assertEqual(sections(registry.all()), BUILTIN_SECTIONS)
        self.assertEqual([m.id for m in registry.all() if m.is_theme][-1], "looks", "themes are listed after tools")


class NearMissNoticeTests(ModEnvTestCase):
    def test_a_lookalike_category_is_reported_instead_of_silently_added(self):
        self.make_mod("subs", header='group = "Subtitle"\n')
        self.assertIn("Subtitle", sections(registry.all()), "still its own section: nothing is guessed")
        [notice] = registry.notices()
        self.assertEqual(notice.mod_id, "subs")
        self.assertIn("Subtitles", notice.message)
        self.assertIn('group = "Subtitles"', notice.message)

    def test_lookalikes_between_two_new_categories_are_reported_too(self):
        self.make_mod("one", header='group = "My Tool"\n')
        self.make_mod("two", header='group = "My Tools"\n')
        self.assertEqual({n.mod_id for n in registry.notices()}, {"one", "two"})

    def test_no_notice_for_ordinary_names(self):
        self.make_mod("fine", header='group = "Backups"\n')
        self.assertEqual(registry.notices(), [])

    def test_notices_reach_the_api(self):
        from fastapi.testclient import TestClient
        from web.server import app

        self.make_mod("subs", header='group = "Subtitle"\n')
        body = TestClient(app).get("/api/mods").json()
        self.assertEqual([n["id"] for n in body["notices"]], ["subs"])
        self.assertEqual([g["name"] for g in body["groups"]], list(BUILTIN_GROUP_NAMES))
        self.assertTrue(all(g["description"] for g in body["groups"]))


class PlacementTests(ModEnvTestCase):
    def prepare(self, header: str):
        folder = self.root / "cand"
        folder.mkdir()
        (folder / "mod.toml").write_text(f'id = "cand"\nname = "Cand"\n{header}[ui]\nrun_mode = "run"\n', encoding="utf-8")
        (folder / "main.py").write_text("def run(params, ctx):\n    pass\n", encoding="utf-8")
        preview = install.prepare(str(folder))
        self.addCleanup(install.discard, preview["token"])
        return preview

    def test_the_trust_prompt_says_where_the_tool_will_appear(self):
        preview = self.prepare('group = "media"\n')
        self.assertEqual(preview["placement"], {"name": "Media", "new_section": False, "near_miss": None})
        self.assertEqual(preview["manifest"]["group"], "Media")

    def test_a_new_section_is_flagged(self):
        preview = self.prepare('group = "My Tools"\n')
        self.assertTrue(preview["placement"]["new_section"])

    def test_a_near_miss_is_a_warning_in_the_trust_prompt(self):
        preview = self.prepare('group = "Subtitle"\n')
        self.assertEqual(preview["placement"]["near_miss"], "Subtitles")
        self.assertTrue(any("Subtitles" in w and "separate section" in w for w in preview["warnings"]))

    def test_a_listing_that_names_another_category_is_a_warning(self):
        folder = self.root / "listed"
        folder.mkdir()
        (folder / "mod.toml").write_text('id = "listed"\nname = "L"\ngroup = "Files"\n[ui]\nrun_mode = "run"\n', encoding="utf-8")
        (folder / "main.py").write_text("def run(params, ctx):\n    pass\n", encoding="utf-8")
        preview = install.prepare(str(folder), expect={"id": "listed", "group": "Media"})
        self.addCleanup(install.discard, preview["token"])
        self.assertTrue(any("'Media'" in w and "'Files'" in w for w in preview["warnings"]))


class MarketCategoryTests(unittest.TestCase):
    def entry(self, **extra):
        return {
            "id": "my-mod",
            "name": "My Mod",
            "repo": "https://github.com/someone/my-mod",
            "commit": "c" * 40,
            **extra,
        }

    def test_the_listed_category_is_normalised(self):
        from core.mods import market

        self.assertEqual(market.parse_entry(self.entry(group=" media "))["group"], "Media")
        self.assertEqual(market.parse_entry(self.entry())["group"], "", "unstated stays unstated")

    def test_the_category_is_searchable(self):
        from core.mods import market

        parsed = market.parse_entry(self.entry(group="Subtitles"))
        self.assertTrue(market.matches(parsed, "subtitles"))


if __name__ == "__main__":
    unittest.main()
