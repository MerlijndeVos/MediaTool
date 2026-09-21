"""Tests for renaming the selected folder itself, and for the AI assist that reads folder names.

Run with::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import rename_ai  # noqa: E402
from core.ai import InvalidJsonError  # noqa: E402
from core.ai.base import JsonResult  # noqa: E402
from core.rename import load_undo_journal, run_undo_from_journal  # noqa: E402
from core.rename_ai import (  # noqa: E402
    SAMPLE_MAX_NAMES,
    FolderContext,
    balanced_pick,
    build_sample,
    generate_profile,
    name_shape,
    propose_examples,
    verify_profile,
)
from core.rename_generic import (  # noqa: E402
    check_root_renamable,
    plan_generic_rename,
    run_generic_rename,
    scan_items,
)
from core.rename_profiles import ProfileError, profile_from_dict  # noqa: E402

LOGGER = logging.getLogger("test_rename_root_and_ai")

DRIVE_ROOT = Path(Path.cwd().anchor)


def tidy_profile(pattern: str | None = None):
    """Removes [tags], turns underscores into spaces."""
    data = {
        "name": "tidy",
        "rules": [
            {"type": "remove_brackets", "brackets": ["[]"]},
            {"type": "replace", "find": "_", "with": " "},
        ],
        "patterns": {"generic": pattern} if pattern else {},
        "strip_release_junk": False,
    }
    return profile_from_dict(data)


class TempTreeCase(unittest.TestCase):
    """A temp folder, with the app data (undo journals) redirected into it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        for patcher in (
            mock.patch("core.log_storage.app_data_dir", lambda: self.base / "appdata"),
            mock.patch("core.config.FILE_LOGGING_ENABLED", False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def make(self, *parts: str) -> Path:
        path = self.base.joinpath(*parts)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def tree(self) -> list[str]:
        return sorted(str(p.relative_to(self.base)).replace("\\", "/") for p in self.base.rglob("*") if "appdata" not in p.parts)


class IncludeRootPlanningTests(TempTreeCase):
    def setUp(self):
        super().setUp()
        self.root = self.make("Library", "My_Pack_[FREE]")
        self.make("Library", "My_Pack_[FREE]", "Kick_[WAV]")
        self.make("Library", "My_Pack_[FREE]", "Snare_[WAV]")

    def test_default_leaves_the_selected_folder_alone(self):
        ops, _ = plan_generic_rename(self.root, "folders", 1, tidy_profile())
        self.assertEqual({op.src.name for op in ops}, {"Kick_[WAV]", "Snare_[WAV]"})

    def test_root_is_planned_and_goes_last(self):
        ops, _ = plan_generic_rename(self.root, "folders", 1, tidy_profile(), include_root=True)
        self.assertEqual([op.dst.name for op in ops], ["Kick", "Snare", "My Pack"])
        self.assertEqual(ops[-1].src, self.root)
        self.assertEqual(ops[-1].dst, self.root.parent / "My Pack")

    def test_root_goes_after_deeper_children_too(self):
        self.make("Library", "My_Pack_[FREE]", "Kick_[WAV]", "Deep_[X]")
        ops, _ = plan_generic_rename(self.root, "folders", 3, tidy_profile(), include_root=True)
        depths = [len(op.src.parts) for op in ops]
        self.assertEqual(depths, sorted(depths, reverse=True))
        self.assertEqual(ops[-1].src, self.root)

    def test_works_with_folders_and_files(self):
        (self.root / "a_[x].txt").write_text("x")
        ops, _ = plan_generic_rename(self.root, "both", 1, tidy_profile(), include_root=True)
        self.assertEqual({op.kind for op in ops}, {"folder", "file"})
        self.assertEqual(ops[-1].src, self.root)

    def test_files_only_cannot_include_the_root(self):
        with self.assertRaises(ValueError):
            plan_generic_rename(self.root, "files", 1, tidy_profile(), include_root=True)

    def test_a_drive_root_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            plan_generic_rename(DRIVE_ROOT, "folders", 1, tidy_profile(), include_root=True)
        self.assertIn("drive or share root", str(caught.exception))
        with self.assertRaises(ValueError):
            check_root_renamable(DRIVE_ROOT)
        with self.assertRaises(ValueError):
            scan_items(DRIVE_ROOT, "folders", 1, include_root=True)

    def test_a_normal_folder_is_accepted(self):
        check_root_renamable(self.root)

    def test_a_name_that_already_exists_next_to_the_root_gets_a_counter(self):
        self.make("Library", "My Pack")
        ops, _ = plan_generic_rename(self.root, "folders", 1, tidy_profile(), include_root=True)
        self.assertEqual(ops[-1].dst.name, "My Pack (2)")

    def test_already_correct_root_is_left_alone(self):
        clean = self.make("Library", "Tidy Pack")
        ops, skipped = plan_generic_rename(clean, "folders", 1, tidy_profile(), include_root=True)
        self.assertEqual(ops, [])
        self.assertIn((clean, "already correctly named"), skipped)

    def test_parent_is_the_containing_folder_and_n_is_one(self):
        ops, _ = plan_generic_rename(
            self.root, "folders", 1, tidy_profile("{parent} - {name}"), include_root=True
        )
        self.assertEqual(ops[-1].dst.name, "Library - My Pack")
        ops, _ = plan_generic_rename(self.root, "folders", 1, tidy_profile("{n:02} {name}"), include_root=True)
        self.assertEqual(ops[-1].dst.name, "01 My Pack")

    def test_root_date_comes_from_the_videos_inside(self):
        (self.root / "Kick_[WAV]" / "clip-2006-07-13 17;48;08.dv").write_text("x")
        profile = tidy_profile("{date:YYYY MMMM D} - {name}")
        ops, skipped = plan_generic_rename(self.root, "folders", 1, profile, include_root=True)
        self.assertEqual(ops[-1].dst.name, "2006 July 13 - My Pack")
        # Snare has no video: skipped like any other folder without a date.
        self.assertTrue(any(path.name == "Snare_[WAV]" for path, _ in skipped))

    def test_a_relative_or_dotted_path_is_normalised(self):
        dotted = self.root / "Kick_[WAV]" / ".."
        ops, _ = plan_generic_rename(dotted, "folders", 1, tidy_profile(), include_root=True)
        self.assertEqual(ops[-1].src, self.root)


class IncludeRootRunTests(TempTreeCase):
    def setUp(self):
        super().setUp()
        self.root = self.make("Library", "My_Pack_[FREE]")
        self.make("Library", "My_Pack_[FREE]", "Kick_[WAV]")
        self.args = argparse.Namespace(
            input=self.root, apply=False, targets="folders", max_depth=1, include_root=True
        )

    def test_dry_run_changes_nothing_and_reports_the_root(self):
        before = self.tree()
        with self.assertLogs(LOGGER, level="INFO") as logs:
            self.assertIsNone(run_generic_rename(self.args, LOGGER, tidy_profile()))
        self.assertEqual(self.tree(), before)
        text = "\n".join(logs.output)
        self.assertIn("[DRY-RUN] folder 'Kick_[WAV]' -> 'Kick'", text)
        self.assertIn("(the selected folder) My_Pack_[FREE]' -> 'My Pack'", text)

    def test_apply_renames_the_root_and_reports_its_new_path(self):
        self.args.apply = True
        manifest = run_generic_rename(self.args, LOGGER, tidy_profile())
        new_root = self.root.parent / "My Pack"
        self.assertEqual(manifest["renamed_root"], {"from": str(self.root), "to": str(new_root)})
        self.assertEqual(self.tree(), ["Library", "Library/My Pack", "Library/My Pack/Kick"])
        self.assertEqual([Path(o["dst"]).name for o in manifest["operations"]], ["Kick", "My Pack"])

    def test_undo_restores_the_root_and_the_children(self):
        self.args.apply = True
        before = self.tree()
        manifest = run_generic_rename(self.args, LOGGER, tidy_profile())
        restored, failed, skipped = run_undo_from_journal(manifest, True, LOGGER)
        self.assertEqual((restored, failed, skipped), (2, 0, 0))
        self.assertEqual(self.tree(), before)

    def test_journal_is_filed_under_the_new_path_so_the_cli_can_undo(self):
        self.args.apply = True
        manifest = run_generic_rename(self.args, LOGGER, tidy_profile())
        new_root = Path(manifest["renamed_root"]["to"])
        journal = load_undo_journal(new_root, LOGGER)
        self.assertIsNotNone(journal)
        self.assertEqual(journal["renamed_root"]["from"], str(self.root))
        self.assertIsNone(load_undo_journal(self.root, LOGGER))

    def test_without_the_option_there_is_no_renamed_root(self):
        self.args.apply = True
        self.args.include_root = False
        manifest = run_generic_rename(self.args, LOGGER, tidy_profile())
        self.assertNotIn("renamed_root", manifest)
        self.assertTrue(self.root.exists())
        self.assertIsNotNone(load_undo_journal(self.root, LOGGER))

    def test_if_the_root_cannot_be_renamed_the_children_still_are_and_the_journal_keeps_the_old_path(self):
        import core.rename as rename_module

        real_move = rename_module.move_path

        def move(src, dst):
            if Path(src) == self.root:
                raise OSError("in use")
            return real_move(src, dst)

        self.args.apply = True
        with mock.patch("core.rename.move_path", move), self.assertLogs(LOGGER, level="INFO"):
            manifest = run_generic_rename(self.args, LOGGER, tidy_profile())
        self.assertNotIn("renamed_root", manifest)
        self.assertTrue((self.root / "Kick").is_dir())
        self.assertIsNotNone(load_undo_journal(self.root, LOGGER))

    def test_a_drive_root_stops_the_run_before_anything_happens(self):
        self.args.input = DRIVE_ROOT
        with self.assertRaises(ValueError):
            run_generic_rename(self.args, LOGGER, tidy_profile())


class CommandLineAndParamsTests(unittest.TestCase):
    def test_the_cli_has_an_include_root_flag(self):
        from cli.args import parse_args

        args = parse_args(["rename", "--input", "X", "--mode", "generic", "--include-root"])
        self.assertTrue(args.include_root)
        self.assertFalse(parse_args(["rename", "--input", "X", "--mode", "generic"]).include_root)

    def test_include_root_needs_the_other_mode(self):
        from core.rename import run_rename

        with tempfile.TemporaryDirectory() as tmp, mock.patch("core.config.FILE_LOGGING_ENABLED", False):
            args = argparse.Namespace(
                input=Path(tmp), output=None, type="auto", apply=False, copy=False, undo=False,
                prune_empty_dirs=False, no_titlecase=False, strip_words=[], bare_episode_numbers=False,
                default_sub_lang="en", profile=None, mode="media", layout=True, include_root=True,
            )
            with self.assertRaises(SystemExit):
                run_rename(args)

    def test_params_validation(self):
        from builtin_mods.rename.main import Params

        self.assertTrue(Params(input="D:/x", mode="generic", include_root=True).include_root)
        self.assertFalse(Params(input="D:/x").include_root)
        for bad in (
            dict(mode="media", include_root=True),
            dict(mode="generic", targets="files", include_root=True),
            dict(mode="generic", include_root=True, input=str(DRIVE_ROOT)),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Params(**{"input": "D:/x", **bad})

    def test_a_job_reports_the_renamed_folder(self):
        from web.jobs import Job

        job = Job(id="j", command="rename", undo_manifest={"operations": [], "renamed_root": {"from": "a", "to": "b"}})
        self.assertEqual(job.to_dict()["renamed_root"], {"from": "a", "to": "b"})
        self.assertIsNone(Job(id="k", command="rename").to_dict()["renamed_root"])


# ---------------------------------------------------------------------------
# AI: what the model sees, and the examples shown back
# ---------------------------------------------------------------------------


class FakeProvider:
    """Stands in for an AI provider and records what it was sent."""

    model = "test-model"
    label = "Fake AI"

    def __init__(self, *replies: dict | str):
        self.replies = [r if isinstance(r, str) else json.dumps(r) for r in replies]
        self.calls: list[list[dict]] = []

    def complete_json(self, messages, *, temperature: float = 0.0):
        self.calls.append([dict(m) for m in messages])
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        try:
            return JsonResult(text=text, data=json.loads(text))
        except json.JSONDecodeError as exc:
            raise InvalidJsonError(str(exc), raw=text) from exc

    def everything_sent(self) -> str:
        return "\n".join(m["content"] for call in self.calls for m in call)


TIDY_REPLY = {
    "name": "Tidy",
    "rules": [
        {"type": "remove_brackets", "brackets": ["[]"]},
        {"type": "replace", "find": "_", "with": " "},
    ],
    "patterns": {},
    "strip_release_junk": False,
}


class NameShapeTests(unittest.TestCase):
    def test_names_built_the_same_way_share_a_shape(self):
        self.assertEqual(name_shape("Kick_Drums [WAV]"), name_shape("Snare_Hits [FLAC]"))
        self.assertEqual(name_shape("2006-07-13 Holiday"), name_shape("1999-01-02 Trip"))

    def test_shape_tells_case_and_punctuation_apart(self):
        self.assertNotEqual(name_shape("kick drums"), name_shape("KICK DRUMS"))
        self.assertNotEqual(name_shape("kick_drums"), name_shape("kick drums"))
        self.assertNotEqual(name_shape("Holiday 2006"), name_shape("Holiday (2006)"))

    def test_digits_and_letters_are_blanked(self):
        self.assertEqual(name_shape("2006-07-13 Holiday [720p]"), "9-9-9 Aa [9a]")


class SamplerTests(TempTreeCase):
    def setUp(self):
        super().setUp()
        self.root = self.make("Library")

    def folders(self, names):
        for name in names:
            self.make("Library", name)

    def context(self, targets="folders", depth=1, include_root=False):
        return FolderContext.scan(self.root, targets, depth, include_root)

    def test_balanced_pick_shows_every_shape_before_repeating_one(self):
        self.folders([f"Pack_{i}_[WAV]" for i in range(100)])  # one very common shape
        self.folders(["2006-07-13 Holiday", "KICK DRUMS", "snare hits", "Odd (2019)"])  # four outliers
        items = self.context().items
        picked = {item.path.name for item, _ in balanced_pick(items, 6)}
        self.assertTrue({"2006-07-13 Holiday", "KICK DRUMS", "snare hits", "Odd (2019)"} <= picked)

    def test_balanced_pick_respects_the_limit_and_is_deterministic(self):
        self.folders([f"Name {i:03d}" for i in range(50)])
        items = self.context().items
        first = [i.path.name for i, _ in balanced_pick(items, 7)]
        self.assertEqual(len(first), 7)
        self.assertEqual(first, [i.path.name for i, _ in balanced_pick(items, 7)])

    def test_balanced_pick_spreads_over_a_big_group_instead_of_taking_the_front(self):
        self.folders([f"Name {i:03d}" for i in range(50)])
        picked = sorted(i.path.name for i, _ in balanced_pick(self.context().items, 5))
        self.assertNotEqual(picked, [f"Name {i:03d}" for i in range(5)])
        self.assertGreater(int(picked[-1].split()[-1]) - int(picked[0].split()[-1]), 25)

    def test_similar_counts_the_size_of_the_shape_group(self):
        self.folders([f"Pack {i}" for i in range(9)] + ["ODD ONE"])
        counts = {item.path.name: similar for item, similar in balanced_pick(self.context().items, 10)}
        self.assertEqual(counts["ODD ONE"], 1)
        self.assertEqual(counts["Pack 3"], 9)

    def test_the_sample_is_capped(self):
        self.folders([f"Pack {i} [WAV]" for i in range(300)])
        sample = build_sample(self.context())
        self.assertEqual(len(sample["entries"]), SAMPLE_MAX_NAMES)
        self.assertEqual(sample["info"]["sent"], SAMPLE_MAX_NAMES)
        self.assertEqual(sample["info"]["total"], 300)

    def test_long_names_are_cut(self):
        self.folders(["x" * 250])
        name = build_sample(self.context())["entries"][0]["name"]
        self.assertLessEqual(len(name), rename_ai.SAMPLE_NAME_LEN)
        self.assertTrue(name.endswith("…"))

    def test_only_a_few_folders_show_file_names_and_dates(self):
        for i in range(30):
            folder = self.make("Library", f"Trip {i:02d}")
            for j in range(6):
                (folder / f"clip-2006-07-{j + 1:02d} 10;00;00.dv").write_text("x")
        sample = build_sample(self.context())
        with_files = [e for e in sample["entries"] if "files_inside" in e]
        self.assertEqual(len(with_files), rename_ai.SAMPLE_FOLDERS_WITH_FILES)
        self.assertTrue(all(len(e["files_inside"]) <= rename_ai.SAMPLE_FILES_PER_FOLDER for e in with_files))
        self.assertTrue(all(e["date_in_videos"] == "2006-07-01" for e in with_files))

    def test_files_targets_sample_file_names(self):
        for i in range(5):
            (self.root / f"track_{i}.wav").write_text("secret audio")
        entries = build_sample(self.context("files"))["entries"]
        self.assertEqual({e["kind"] for e in entries}, {"file"})
        self.assertIn("track_2.wav", {e["name"] for e in entries})

    def test_nothing_but_names_is_sent(self):
        secret = self.make("Library", "Holiday")
        (secret / "clip-2006-07-13 10;00;00.dv").write_text("SECRET FILE CONTENT")
        blob = json.dumps(build_sample(self.context()))
        self.assertNotIn("SECRET FILE CONTENT", blob)
        self.assertNotIn(str(self.base), blob)  # no absolute paths, not even the temp folder
        self.assertNotIn("appdata", blob)

    def test_the_scan_stops_at_its_limit_and_says_so(self):
        self.folders([f"Pack {i}" for i in range(50)])
        items, truncated = scan_items(self.root, "folders", 1, limit=10)
        self.assertEqual(len(items), 10)
        self.assertTrue(truncated)
        self.assertFalse(scan_items(self.root, "folders", 1)[1])

    def test_the_selected_folder_is_marked_when_it_is_included(self):
        self.folders(["Pack A"])
        entries = build_sample(self.context(include_root=True))["entries"]
        self.assertEqual([e["name"] for e in entries if e.get("selected_folder")], ["Library"])


class ProposalTests(TempTreeCase):
    def setUp(self):
        super().setUp()
        self.root = self.make("Library")
        for name in ["Kick_[WAV]", "Snare_[WAV]", "Hats_[WAV]", "Already Clean", "2006-07-13 Trip", "SHOUTING_[X]"]:
            self.make("Library", name)

    def context(self):
        return FolderContext.scan(self.root, "folders", 1)

    def test_picks_the_names_the_profile_changes_and_shows_the_real_result(self):
        proposals = propose_examples(tidy_profile(), self.context(), count=10)
        by_before = {p["before"]: p for p in proposals}
        self.assertEqual(by_before["Kick_[WAV]"]["after"], "Kick") if "Kick_[WAV]" in by_before else None
        changed = [p for p in proposals if p["changed"]]
        self.assertTrue(changed)
        for p in proposals:
            self.assertEqual(p["parent"], "Library")
            self.assertEqual(p["kind"], "folder")

    def test_different_shapes_come_first_and_the_most_changed_of_each(self):
        self.make("Library", "A_[WAV]")
        proposals = propose_examples(tidy_profile(), self.context(), count=3)
        shapes = [rename_ai.name_shape(p["before"]) for p in proposals]
        self.assertEqual(len(set(shapes)), len(shapes))

    def test_a_zero_change_name_is_only_shown_when_there_is_room(self):
        proposals = propose_examples(tidy_profile(), self.context(), count=2)
        self.assertTrue(all(p["changed"] for p in proposals))
        everything = propose_examples(tidy_profile(), self.context(), count=20)
        self.assertIn(False, {p["changed"] for p in everything})

    def test_already_reviewed_names_are_left_out(self):
        first = propose_examples(tidy_profile(), self.context(), count=20)
        skip = {p["before"] for p in first[:3]}
        again = propose_examples(tidy_profile(), self.context(), exclude=skip, count=20)
        self.assertFalse(skip & {p["before"] for p in again})

    def test_date_patterns_use_the_real_date_and_skip_folders_without_one(self):
        (self.root / "Kick_[WAV]" / "clip-2006-07-13 17;48;08.dv").write_text("x")
        (self.root / "Snare_[WAV]" / "clip-1999-12-31 09;00;00.dv").write_text("x")
        profile = tidy_profile("{date:YYYY MMMM D} - {name}")
        proposals = {p["before"]: p for p in propose_examples(profile, self.context(), count=10)}
        self.assertEqual(proposals["Kick_[WAV]"]["after"], "2006 July 13 - Kick")
        self.assertEqual(proposals["Kick_[WAV]"]["date"], "2006-07-13")
        self.assertEqual(proposals["Snare_[WAV]"]["after"], "1999 December 31 - Snare")
        self.assertNotIn("Hats_[WAV]", proposals)  # no videos inside: a run would skip it too

    def test_a_proposal_verifies_when_sent_back_as_an_example(self):
        (self.root / "Kick_[WAV]" / "clip-2006-07-13 17;48;08.dv").write_text("x")
        for pattern in (None, "{parent} - {name}", "{n:02} {name}", "{date:YYYY MMMM D} - {name}"):
            with self.subTest(pattern=pattern):
                profile = tidy_profile(pattern)
                proposals = propose_examples(profile, self.context(), count=10)
                self.assertTrue(proposals)
                self.assertTrue(all(v["ok"] for v in verify_profile(profile, "generic", proposals)))

    def test_file_proposals_keep_their_extension(self):
        for name in ("a_[x].wav", "b_[y].wav"):
            (self.root / name).write_text("x")
        context = FolderContext.scan(self.root, "files", 1)
        proposals = propose_examples(tidy_profile(), context, count=5)
        self.assertTrue(all(p["after"].endswith(".wav") for p in proposals))
        self.assertTrue(all(v["ok"] for v in verify_profile(tidy_profile(), "generic", proposals)))


class GenerateProfileTests(TempTreeCase):
    def setUp(self):
        super().setUp()
        self.root = self.make("Library")
        for name in ["Kick_Drums_[WAV]", "Snare_Hits_[WAV]", "Hats_[WAV]"]:
            self.make("Library", name)

    def context(self, **kw):
        return FolderContext.scan(self.root, kw.get("targets", "folders"), 1, kw.get("include_root", False))

    def test_typed_examples_alone_never_send_folder_names(self):
        client = FakeProvider(TIDY_REPLY)
        result = generate_profile([{"before": "Cool_Pack_[WAV]", "after": "Cool Pack"}], "generic", provider=client)
        self.assertTrue(result["all_ok"])
        self.assertIsNone(result["sample"])
        self.assertEqual(result["proposed_examples"], [])
        sent = client.everything_sent()
        self.assertNotIn("Kick_[WAV]", sent)
        self.assertNotIn("folder_sample", sent)

    def test_a_folder_needs_no_examples_and_is_shown_to_the_model(self):
        client = FakeProvider(TIDY_REPLY)
        result = generate_profile([], "generic", folder=self.context(), provider=client)
        system, user = client.calls[0][0]["content"], client.calls[0][1]["content"]
        self.assertIn("folder_sample", system)
        for name in ("Kick_Drums_[WAV]", "Snare_Hits_[WAV]", "Hats_[WAV]"):
            self.assertIn(name, user)
        self.assertIn("not given examples", user)
        self.assertEqual(result["sample"]["sent"], 3)
        self.assertEqual(result["verification"], [])
        self.assertTrue(result["all_ok"])
        self.assertEqual(len(result["proposed_examples"]), 3)

    def test_a_big_folder_sends_a_capped_sample(self):
        for i in range(200):
            self.make("Library", f"Pack {i:03d} [WAV]")
        client = FakeProvider(TIDY_REPLY)
        result = generate_profile([], "generic", folder=self.context(), provider=client)
        user = client.calls[0][1]["content"]
        sent_names = [line for line in user.splitlines() if line.strip().startswith('"name"')]
        self.assertLessEqual(len(sent_names), SAMPLE_MAX_NAMES)
        self.assertEqual(result["sample"]["total"], 203)
        self.assertEqual(result["sample"]["sent"], SAMPLE_MAX_NAMES)

    def test_a_correction_is_sent_back_as_an_example_and_steers_the_next_profile(self):
        # Round 1: no examples. The AI keeps the underscores.
        lazy = {**TIDY_REPLY, "rules": [{"type": "remove_brackets", "brackets": ["[]"]}]}
        first = generate_profile([], "generic", folder=self.context(), provider=FakeProvider(lazy))
        wrong = next(p for p in first["proposed_examples"] if p["before"] == "Kick_Drums_[WAV]")
        self.assertEqual(wrong["after"], "Kick_Drums")  # the underscore is still there: not what the user wants

        # The user corrects it: "Kick Drums" (underscore gone). It comes back as an ordinary example.
        corrected = {**wrong, "after": "Kick Drums"}
        client = FakeProvider(lazy, TIDY_REPLY)  # the AI's first try misses the correction, then fixes it
        second = generate_profile([corrected], "generic", folder=self.context(), provider=client)
        first_user = client.calls[0][1]["content"]
        self.assertIn("Examples the user confirmed or wrote", first_user)
        self.assertIn('"after": "Kick Drums"', first_user)
        self.assertIn("folder_sample", first_user)
        # The miss is fed back, in the same conversation, and the second attempt reproduces it.
        self.assertEqual(second["attempts"], 2)
        self.assertIn("does not reproduce every example", client.calls[1][-1]["content"])
        self.assertIn("'Kick_Drums_[WAV]' gave 'Kick_Drums' but should give 'Kick Drums'", client.calls[1][-1]["content"])
        self.assertTrue(second["all_ok"])
        self.assertTrue(second["verification"][0]["ok"])
        # Names the user already reviewed are not proposed again.
        self.assertNotIn("Kick_Drums_[WAV]", {p["before"] for p in second["proposed_examples"]})

    def test_examples_from_a_real_folder_verify_with_their_own_context(self):
        (self.root / "Kick_Drums_[WAV]" / "clip-2006-07-13 17;48;08.dv").write_text("x")
        example = {"before": "Kick_Drums_[WAV]", "after": "Library - 2006 July 13 - Kick Drums", "parent": "Library", "n": 1, "date": "2006-07-13"}
        reply = {**TIDY_REPLY, "patterns": {"generic": "{parent} - {date:YYYY MMMM D} - {name}"}}
        result = generate_profile([example], "generic", folder=self.context(), provider=FakeProvider(reply))
        self.assertTrue(result["all_ok"], result["verification"])
        self.assertTrue(result["profile"]["patterns"]["generic"].startswith("{parent}"))

    def test_the_model_is_told_where_an_example_sat(self):
        client = FakeProvider(TIDY_REPLY)
        example = {"before": "Kick_Drums_[WAV]", "after": "Kick Drums", "parent": "Drums", "n": 3, "date": "2006-07-13"}
        generate_profile([example], "generic", provider=client)
        user = client.calls[0][1]["content"]
        self.assertIn('"inside_folder": "Drums"', user)
        self.assertIn('"position_in_folder": 3', user)
        self.assertIn('"date_in_videos": "2006-07-13"', user)

    def test_only_the_other_mode_can_look_at_a_folder(self):
        with self.assertRaises(ProfileError):
            generate_profile([{"before": "a", "after": "b"}], "media", folder=self.context(), provider=FakeProvider(TIDY_REPLY))

    def test_examples_are_still_required_without_a_folder(self):
        with self.assertRaises(ProfileError):
            generate_profile([], "generic", provider=FakeProvider(TIDY_REPLY))

    def test_bad_example_context_is_rejected(self):
        for bad in ({"date": "13/07/2006"}, {"n": "abc"}):
            with self.subTest(bad=bad), self.assertRaises(ProfileError):
                generate_profile([{"before": "a", "after": "b", **bad}], "generic", provider=FakeProvider(TIDY_REPLY))

    def test_the_profile_is_still_validated(self):
        broken = {**TIDY_REPLY, "patterns": {"generic": "{nonsense}"}}
        with self.assertRaises(ProfileError):
            generate_profile([], "generic", folder=self.context(), provider=FakeProvider(broken))

    def test_more_examples_are_allowed_for_corrections(self):
        examples = [{"before": f"Pack_{i}_[WAV]", "after": f"Pack {i}"} for i in range(rename_ai.MAX_EXAMPLES)]
        result = generate_profile(examples, "generic", folder=self.context(), provider=FakeProvider(TIDY_REPLY))
        self.assertTrue(result["all_ok"])
        with self.assertRaises(ProfileError):
            generate_profile(examples + [{"before": "x", "after": "y"}], "generic", provider=FakeProvider(TIDY_REPLY))


class GenerateEndpointTests(TempTreeCase):
    @classmethod
    def setUpClass(cls):
        try:
            from fastapi.testclient import TestClient

            from web.server import app
        except ImportError as exc:
            raise unittest.SkipTest(f"web dependencies missing: {exc}")
        cls.client = TestClient(app)

    def setUp(self):
        super().setUp()
        self.root = self.make("Library")
        for name in ["Kick_[WAV]", "Snare_[WAV]"]:
            self.make("Library", name)
        patcher = mock.patch("core.rename_ai.get_provider", lambda model=None: FakeProvider(TIDY_REPLY))
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, **body):
        return self.client.post("/api/rename/profiles/generate", json={"mode": "generic", **body})

    def test_a_folder_gives_a_profile_a_sample_summary_and_examples_to_review(self):
        res = self.post(folder=str(self.root))
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["sample"]["sent"], 2)
        self.assertEqual(body["sample"]["total"], 2)
        self.assertEqual({p["before"] for p in body["proposed_examples"]}, {"Kick_[WAV]", "Snare_[WAV]"})
        first = body["proposed_examples"][0]
        self.assertEqual(set(first), {"before", "after", "kind", "parent", "n", "date", "changed"})

    def test_reviewed_examples_go_back_in_and_come_out_verified(self):
        res = self.post(
            folder=str(self.root),
            examples=[{"before": "Kick_[WAV]", "after": "Kick", "parent": "Library", "n": 1}],
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["all_ok"])
        self.assertEqual([v["ok"] for v in res.json()["verification"]], [True])

    def test_options_reach_the_scan(self):
        res = self.post(folder=str(self.root), include_root=True)
        self.assertIn("Library", {p["before"] for p in res.json()["proposed_examples"]})
        res = self.post(folder=str(self.root), targets="files")
        self.assertEqual(res.status_code, 422)  # no files in there, so nothing to look at

    def test_bad_requests_are_refused(self):
        cases = [
            dict(folder=str(self.base / "missing")),
            dict(folder=str(self.root), mode="media"),
            dict(folder=str(DRIVE_ROOT), include_root=True),
            dict(folder=str(self.root), targets="files", include_root=True),
            dict(),
            dict(examples=[{"before": f"a{i}", "after": "b"} for i in range(13)]),
        ]
        for body in cases:
            with self.subTest(body=body):
                self.assertEqual(self.post(**body).status_code, 422)

    def test_examples_only_still_works_and_sends_no_names(self):
        client = FakeProvider(TIDY_REPLY)
        with mock.patch("core.rename_ai.get_provider", lambda model=None: client):
            res = self.post(examples=[{"before": "Cool_Pack_[WAV]", "after": "Cool Pack"}])
        self.assertEqual(res.status_code, 200, res.text)
        self.assertIsNone(res.json()["sample"])
        self.assertNotIn("Kick_[WAV]", client.everything_sent())


if __name__ == "__main__":
    unittest.main()
