"""Tests for the {date} rename token, the "remove dates" rule and the built-in date profile.

The built-in "Date + name (Dutch)" profile replaces the old Rename Folders tool, so its
output is compared against a verbatim copy of that tool (``legacy_rename_folders.py``).

Run with::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for path in (ROOT, Path(__file__).resolve().parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import legacy_rename_folders as legacy  # noqa: E402

from core import dates  # noqa: E402
from core.rename_generic import (  # noqa: E402
    SKIP_NO_DATE,
    generic_new_name,
    plan_generic_rename,
    preview_generic,
    run_generic_rename,
)
from core.rename_profiles import (  # noqa: E402
    DATE_NAME_ID,
    ProfileError,
    get_profile,
    profile_from_dict,
    render_pattern,
    reverse_pattern,
    validate_pattern,
)

LOGGER = logging.getLogger("test_rename_dates")


def dutch_profile():
    profile = get_profile(DATE_NAME_ID)
    assert profile is not None
    return profile


class DateHelperTests(unittest.TestCase):
    def test_dates_are_read_from_dv_and_mp4_names(self):
        self.assertEqual(dates.parse_date_from_filename("clip-2006-07-13 17;48;08"), (2006, 7, 13))
        self.assertEqual(dates.parse_date_from_filename("13 juli 2006 17-48-08"), (2006, 7, 13))
        self.assertEqual(dates.parse_date_from_filename("3 MEI 1999 10-00-00"), (1999, 5, 3))
        self.assertIsNone(dates.parse_date_from_filename("holiday movie"))
        self.assertIsNone(dates.parse_date_from_filename("clip-2006-13-45"))

    def test_format_specs(self):
        d = (2006, 7, 3)
        self.assertEqual(dates.format_date(d, "YYYY MMMM D", "nl"), "2006 juli 3")
        self.assertEqual(dates.format_date(d, "D MMMM YYYY", "en"), "3 July 2006")
        self.assertEqual(dates.format_date(d, "YYYY-MM-DD"), "2006-07-03")
        self.assertEqual(dates.format_date(d, "YY.M.DD MMM", "nl"), "06.7.03 jul")

    def test_invalid_specs_are_rejected(self):
        for bad in ("", "YYY", "HH:mm", "hello", "YYYY{MM}", "YYYY/MM", "x" * 50):
            with self.assertRaises(ValueError, msg=bad):
                dates.validate_date_spec(bad)
        for good in ("YYYY", "D MMMM YYYY", "YYYY-MM-DD", "[YY] MMM"):
            dates.validate_date_spec(good)

    def test_dates_can_be_read_back(self):
        rx = dates.date_spec_regex("YYYY MMMM D", "nl")
        for text in ("2006 juli 13", "2006 JULI 13"):
            m = re.fullmatch(rx.pattern, text, re.IGNORECASE)
            self.assertEqual(rx.to_date(m), (2006, 7, 13), text)
        self.assertIsNone(dates.date_spec_regex("YY-MM-DD"))  # century unknown
        self.assertIsNone(dates.date_spec_regex("YYYY-MM"))  # no day

    def test_earliest_date_looks_in_subfolders(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Trip"
            (folder / "sub").mkdir(parents=True)
            (folder / "clip-2006-07-13 17;48;08.dv").write_text("x")
            (folder / "sub" / "clip-2005-08-03 10;00;00.dv").write_text("x")
            (folder / "sub" / "notes 2001.txt").write_text("x")  # not a video
            self.assertEqual(dates.earliest_date_in_folder(folder), (2005, 8, 3))
            self.assertIsNone(dates.earliest_date_in_folder(Path(tmp) / "missing"))


class ProfileTests(unittest.TestCase):
    def test_builtin_profile_exists_and_is_dutch(self):
        profile = dutch_profile()
        self.assertTrue(profile.builtin)
        self.assertEqual(profile.date_locale, "nl")
        self.assertEqual(profile.pattern("generic"), "{date:YYYY MMMM D} - {name}")
        self.assertEqual(profile_from_dict(profile.to_dict()).date_locale, "nl")

    def test_date_pattern_validation(self):
        validate_pattern("{date:D MMMM YYYY} {name}", "generic")
        validate_pattern("{date} {name}", "generic")
        for bad in ("{date:YYY} {name}", "{date:} {name}", "{date:HH} {name}"):
            with self.assertRaises(ProfileError, msg=bad):
                validate_pattern(bad, "generic")
        with self.assertRaises(ProfileError):  # {date} only exists in folders mode
            validate_pattern("{date} {title}", "movie")

    def test_profile_fields_are_validated(self):
        with self.assertRaises(ProfileError):
            profile_from_dict({"name": "x", "date_locale": "fr"})
        self.assertEqual(profile_from_dict({"name": "x"}).date_locale, "en")
        rule = profile_from_dict({"name": "x", "rules": [{"type": "prune_date", "junk": 1}]}).rules[0]
        self.assertEqual(rule, {"type": "prune_date"})

    def test_render_and_reverse_are_inverse(self):
        pattern = "{date:YYYY MMMM D} - {name}"
        text = render_pattern(pattern, {"name": "Holiday", "date": (2006, 7, 3)}, date_locale="nl")
        self.assertEqual(text, "2006 juli 3 - Holiday")
        self.assertEqual(reverse_pattern(pattern, text, "nl"), ((2006, 7, 3), "Holiday"))
        self.assertIsNone(reverse_pattern(pattern, "Holiday", "nl"))
        self.assertIsNone(reverse_pattern("{date} {name} {n}", "2006-07-03 x 1", "nl"))  # other tokens

    def test_english_month_names(self):
        profile = profile_from_dict(
            {"name": "En", "rules": [{"type": "prune_date"}], "patterns": {"generic": "{date:D MMMM YYYY} - {name}"}}
        )
        self.assertEqual(generic_new_name(profile, "Trip 13 July 2006", "P", 1, (2006, 7, 13)), "13 July 2006 - Trip")
        self.assertEqual(generic_new_name(profile, "13 July 2006 - Trip", "P", 1, (1999, 1, 1)), "13 July 2006 - Trip")


class ParityWithOldToolTests(unittest.TestCase):
    """The built-in profile must give the same names as the old Rename Folders tool."""

    NAMES = [
        "Holiday", "Holiday 2006", "2006 Holiday", "Kerst - 1999", "Vakantie Spanje 2004",
        "Trip 13 juli 2006", "Trip juli 2006", "Trip 13 juli", "Bruiloft 13-07-06",
        "Bruiloft 2006-07-13", "Feest 2006.07.13", "Opa's verjaardag", "Zomer – 2005",
        "Zomer — 2005 —", "   Spaces   ", "2006", "13 juli 2006", "Verjaardag 8 mei",
        "Ski 3-2-99", "Kamp (zomer 2003)", "Übermorgen", "A & B", "Name with 'quotes'",
        "Trailing dot.", "Mixed CASE name", "Mei 2006 feest", "2006 - Holiday",
        "Holiday - 2006 - Extra", "JULI 2004 Reis", "Dubbele  spatie", "tab\tname",
        "Ends with dash -", "- Starts with dash", "a.b.c", "Kerst 12-25-99 kerst",
        "1999-12-31 Oud en nieuw",
        # already renamed: the old tool re-tidies these using the date in the name
        "2006 juli 13 - Holiday", "2006 juli 13 - Holiday 2006", "2006 JULI 13 - Holiday",
        "1999 december 31 - 13 juli 2006", "2006 juli 13 - 2006", "2006 juli 3 - Zomer",
        "2006 juli 13  -  Extra spaces", "2006 mei 5 - Trip 5 mei", "2006 juli 13 - Kerst – 1999",
    ]
    DATES = [(2006, 7, 13), (1999, 12, 31), (2004, 1, 3), (2010, 5, 9)]

    @staticmethod
    def old_name(name: str, date):
        parsed = legacy.parse_already_renamed(name)
        if parsed:
            year, month, day, description = parsed
            return legacy.sanitize_for_windows(legacy.format_folder_name(year, month, day, description))
        return legacy.sanitize_for_windows(legacy.format_folder_name(*date, name))

    def test_names_match_the_old_tool(self):
        profile = dutch_profile()
        for name in self.NAMES:
            for date in self.DATES:
                with self.subTest(name=name, date=date):
                    self.assertEqual(generic_new_name(profile, name, "P", 1, date), self.old_name(name, date))

    def test_known_difference_edge_underscores(self):
        # The shared name tidy-up also trims leading/trailing "_" (the old tool kept them).
        self.assertEqual(self.old_name("Under_score_", (2006, 7, 13)), "2006 juli 13 - Under_score_")
        self.assertEqual(generic_new_name(dutch_profile(), "Under_score_", "P", 1, (2006, 7, 13)), "2006 juli 13 - Under_score")

    @staticmethod
    def build_tree(root: Path) -> None:
        (root / "Holiday 2006").mkdir(parents=True)
        (root / "Holiday 2006" / "clip-2006-07-13 17;48;08.dv").write_text("x")
        (root / "Zomer" / "deel 2").mkdir(parents=True)
        (root / "Zomer" / "deel 2" / "3 augustus 2005 10-00-00.mp4").write_text("x")
        (root / "Zomer" / "clip-2005-08-09 10;00;00.dv").write_text("x")
        (root / "2006 juli 13 - Oud 2006").mkdir()  # already dated, gets re-tidied
        (root / "2005 augustus 3 - Zomer2").mkdir()  # already exactly right
        (root / "Geen video's").mkdir()
        (root / "Geen video's" / "notes.txt").write_text("x")
        (root / "Kerst 1999").mkdir()
        (root / "Kerst 1999" / "clip-1999-12-25 20;00;00.dv").write_text("x")
        (root / "Kerst 1999" / "clip-1999-12-24 20;00;00.dv").write_text("x")

    def test_whole_folder_runs_match_the_old_tool(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("core.log_storage.app_data_dir", lambda: Path(tmp) / "data"):
            old_root, new_root = Path(tmp) / "old", Path(tmp) / "new"
            self.build_tree(old_root)
            self.build_tree(new_root)
            legacy.process_root(old_root, dry_run=False, log=lambda _line: None)
            run_generic_rename(
                argparse.Namespace(input=new_root, apply=True, targets="folders", max_depth=1),
                LOGGER,
                dutch_profile(),
            )
            old_names = sorted(p.name for p in old_root.iterdir())
            self.assertEqual(sorted(p.name for p in new_root.iterdir()), old_names)
            self.assertIn("2005 augustus 3 - Zomer", old_names)
            self.assertIn("1999 december 24 - Kerst", old_names)


class GenericRenameTests(unittest.TestCase):
    def test_second_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("core.log_storage.app_data_dir", lambda: Path(tmp) / "data"):
            root = Path(tmp) / "lib"
            ParityWithOldToolTests.build_tree(root)
            args = argparse.Namespace(input=root, apply=True, targets="folders", max_depth=1)
            run_generic_rename(args, LOGGER, dutch_profile())
            before = sorted(p.name for p in root.iterdir())
            ops, skipped = plan_generic_rename(root, "folders", 1, dutch_profile())
            self.assertEqual(ops, [])
            self.assertEqual(sorted(p.name for p in root.iterdir()), before)
            reasons = {reason for _path, reason in skipped}
            self.assertEqual(reasons, {"already correctly named", SKIP_NO_DATE})

    def test_folders_without_dates_are_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "No videos").mkdir()
            ops, skipped = plan_generic_rename(root, "folders", 1, dutch_profile())
            self.assertEqual(ops, [])
            self.assertEqual([(p.name, r) for p, r in skipped], [("No videos", SKIP_NO_DATE)])

    def test_files_use_the_date_in_their_own_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "clip-2006-07-13 17;48;08.dv").write_text("x")
            (root / "notes.txt").write_text("x")
            profile = profile_from_dict(
                {"name": "F", "patterns": {"generic": "{date:YYYY-MM-DD} {name}"}}
            )
            ops, skipped = plan_generic_rename(root, "files", 1, profile)
            self.assertEqual([(o.src.name, o.dst.name) for o in ops],
                             [("clip-2006-07-13 17;48;08.dv", "2006-07-13 clip-2006-07-13 17;48;08.dv")])
            self.assertEqual([r for _p, r in skipped], [SKIP_NO_DATE])

    def test_profile_tester_uses_a_sample_date(self):
        result, note = preview_generic(dutch_profile(), "Kerst 1999")
        self.assertEqual(result, "2006 juli 13 - Kerst")
        self.assertIn("Sample date", note)
        result, note = preview_generic(dutch_profile(), "2006 juli 13 - Kerst")
        self.assertEqual((result, note), ("2006 juli 13 - Kerst", None))
        result, note = preview_generic(profile_from_dict({"name": "Plain"}), "a_b")
        self.assertIsNone(note)

    def test_ai_prompt_describes_dates(self):
        from core.rename_ai import _system_prompt

        prompt = _system_prompt("generic")
        for word in ("{date:YYYY MMMM D}", "date_locale", "prune_date"):
            self.assertIn(word, prompt)


class DeprecatedCommandTests(unittest.TestCase):
    def test_rename_folders_command_still_works(self):
        from core.rename_folders import run_rename_folders

        from core import close_log_handlers

        self.addCleanup(close_log_handlers, "video_rename")  # release the log file before cleanup
        with tempfile.TemporaryDirectory() as tmp, mock.patch("core.log_storage.app_data_dir", lambda: Path(tmp) / "data"),                 mock.patch("core.config.FILE_LOGGING_ENABLED", False):
            root = Path(tmp) / "lib"
            (root / "Kerst 1999").mkdir(parents=True)
            (root / "Kerst 1999" / "clip-1999-12-25 20;00;00.dv").write_text("x")
            with mock.patch("sys.stderr"):
                run_rename_folders(argparse.Namespace(root=root, dry_run=True))
                self.assertEqual([p.name for p in root.iterdir()], ["Kerst 1999"])
                run_rename_folders(argparse.Namespace(root=root, dry_run=False))
            self.assertEqual([p.name for p in root.iterdir()], ["1999 december 25 - Kerst"])


if __name__ == "__main__":
    unittest.main()
