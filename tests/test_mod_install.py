"""Tests for installing, updating and removing mods (folder, zip, single file, git).

Network access is replaced with canned data; the git path uses a throwaway local repository.

Run with::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.mods import install, read_install_meta, registry  # noqa: E402
from core.mods.install import InstallError, parse_git_url  # noqa: E402

MOD_TOML = 'id = "{id}"\nname = "{id}"\nversion = "{version}"\nauthor = "Tester"\n[ui]\nrun_mode = "run"\n{extra}'
MAIN_PY = "def run(params, ctx):\n    ctx.log('{tag}')\n"
SHA_A = "a" * 40
SHA_B = "b" * 40


def toml(mod_id="hello", version="1.0.0", extra=""):
    return MOD_TOML.format(id=mod_id, version=version, extra=extra)


def make_zip(files: dict[str, str | bytes], wrapper: str = "") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(f"{wrapper}/{name}" if wrapper else name, content)
    return buf.getvalue()


class InstallTestCase(unittest.TestCase):
    def setUp(self):
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

    def write_mod(self, folder: Path, mod_id="hello", version="1.0.0", tag="v1", extra="") -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "mod.toml").write_text(toml(mod_id, version, extra), encoding="utf-8")
        (folder / "main.py").write_text(MAIN_PY.format(tag=tag), encoding="utf-8")
        return folder


class ParseGitUrlTests(unittest.TestCase):
    def test_plain_and_dot_git_urls(self):
        for text in ("https://github.com/o/r", "https://github.com/o/r.git", "https://github.com/o/r/"):
            source = parse_git_url(text)
            self.assertEqual((source.url, source.ref, source.subdir), ("https://github.com/o/r", "", ""))
            self.assertEqual(source.github, ("o", "r"))

    def test_tree_url_gives_ref_and_folder(self):
        source = parse_git_url("https://github.com/o/r/tree/v1.2/mods/x")
        self.assertEqual((source.ref, source.subdir), ("v1.2", "mods/x"))

    def test_explicit_ref_and_subdir_win(self):
        source = parse_git_url("https://github.com/o/r/tree/main/a", ref="abc", subdir="b")
        self.assertEqual((source.ref, source.subdir), ("abc", "b"))

    def test_other_hosts_are_not_github(self):
        self.assertIsNone(parse_git_url("https://gitlab.com/o/r").github)

    def test_rejects_unsafe_addresses(self):
        for text in (
            "http://github.com/o/r",
            "git@github.com:o/r.git",
            "ssh://github.com/o/r",
            "file:///tmp/r",
            "https://user:pw@github.com/o/r",
            "https://github.com/",
        ):
            with self.assertRaises(InstallError, msg=text):
                parse_git_url(text)
        with self.assertRaises(InstallError):
            parse_git_url("https://github.com/o/r", subdir="../etc")


class LocalInstallTests(InstallTestCase):
    def test_folder_install_is_staged_then_committed_and_starts_off(self):
        src = self.write_mod(self.root / "src" / "hello")
        preview = install.prepare(str(src))
        self.assertEqual(preview["manifest"]["id"], "hello")
        self.assertEqual(preview["source"]["type"], "folder")
        self.assertEqual({f["path"] for f in preview["files"]}, {"mod.toml", "main.py"})
        self.assertFalse((self.mods_dir / "hello").exists(), "nothing is installed before commit")

        install.commit(preview["token"])
        self.assertTrue((self.mods_dir / "hello" / "main.py").is_file())
        mod = registry.get("hello")
        self.assertFalse(mod.enabled)
        meta = read_install_meta(mod.path)
        self.assertEqual((meta["type"], meta["id"], meta["version"]), ("folder", "hello", "1.0.0"))
        self.assertFalse((install.staging_dir() / preview["token"]).exists())

    def test_commit_can_turn_the_mod_on(self):
        src = self.write_mod(self.root / "hello")
        install.commit(install.prepare(str(src))["token"], enable=True)
        self.assertTrue(registry.get("hello").enabled)

    def test_zip_with_a_wrapper_folder(self):
        archive = self.root / "hello.zip"
        archive.write_bytes(make_zip({"mod.toml": toml(), "main.py": MAIN_PY.format(tag="z")}, wrapper="hello-main"))
        preview = install.prepare(str(archive))
        self.assertEqual(preview["source"]["type"], "zip")
        install.commit(preview["token"])
        self.assertIn("'z'", (self.mods_dir / "hello" / "main.py").read_text(encoding="utf-8"))

    def test_zip_slip_and_symlinks_are_refused(self):
        evil = self.root / "evil.zip"
        evil.write_bytes(make_zip({"mod.toml": toml(), "main.py": "x", "../../escape.txt": "boom"}))
        with self.assertRaises(InstallError):
            install.prepare(str(evil))
        self.assertFalse((self.root / "escape.txt").exists())

        link = self.root / "link.zip"
        with zipfile.ZipFile(link, "w") as zf:
            zf.writestr("mod.toml", toml())
            zf.writestr("main.py", "x")
            info = zipfile.ZipInfo("shortcut")
            info.external_attr = (0o120777) << 16
            zf.writestr(info, "/etc/passwd")
        with self.assertRaises(InstallError):
            install.prepare(str(link))
        self.assertEqual(list(install.staging_dir().iterdir()), [], "failed installs leave no staging behind")

    def test_size_limits(self):
        archive = self.root / "big.zip"
        archive.write_bytes(make_zip({"mod.toml": toml(), "main.py": "x", "blob.bin": b"0" * 4096}))
        with mock.patch.object(install, "MAX_TOTAL_BYTES", 1000), self.assertRaises(InstallError):
            install.prepare(str(archive))

    def test_single_py_file_with_inline_manifest(self):
        script = self.root / "solo.py"
        script.write_text(
            "# /// toolbox-mod\n# id = \"solo\"\n# name = \"Solo\"\n# [ui]\n# run_mode = \"run\"\n# ///\n\n"
            "def run(params, ctx):\n    pass\n",
            encoding="utf-8",
        )
        preview = install.prepare(str(script))
        self.assertEqual((preview["manifest"]["id"], preview["source"]["type"]), ("solo", "file"))
        install.commit(preview["token"])
        self.assertTrue((self.mods_dir / "solo" / "main.py").is_file())

    def test_single_py_file_without_manifest_is_explained(self):
        script = self.root / "plain.py"
        script.write_text("def run(params, ctx):\n    pass\n", encoding="utf-8")
        with self.assertRaisesRegex(InstallError, "toolbox-mod"):
            install.prepare(str(script))

    def test_bad_manifest_and_missing_entry(self):
        broken = self.root / "broken"
        broken.mkdir()
        (broken / "mod.toml").write_text('id = "Not Valid"\nname = "x"\n', encoding="utf-8")
        with self.assertRaises(InstallError):
            install.prepare(str(broken))
        no_entry = self.write_mod(self.root / "noentry", "noentry")
        (no_entry / "main.py").unlink()
        with self.assertRaisesRegex(InstallError, "main.py"):
            install.prepare(str(no_entry))

    def test_ids_cannot_clash_with_builtins_or_installed_mods(self):
        with self.assertRaisesRegex(InstallError, "built-in"):
            install.prepare(str(self.write_mod(self.root / "a", "convert")))
        src = self.write_mod(self.root / "b", "dup")
        install.commit(install.prepare(str(src))["token"])
        with self.assertRaisesRegex(InstallError, "already installed"):
            install.prepare(str(src))

    def test_builtin_ui_kind_is_refused(self):
        src = self.write_mod(self.root / "c", "sneaky", extra='[ui]\nkind = "builtin"\npanel = "x"\n')
        # Duplicate [ui] tables are invalid TOML; use a fresh manifest instead.
        (src / "mod.toml").write_text('id = "sneaky"\nname = "s"\n[ui]\nkind = "builtin"\npanel = "x"\n', encoding="utf-8")
        with self.assertRaises(InstallError):
            install.prepare(str(src))

    def test_program_files_are_flagged(self):
        src = self.write_mod(self.root / "d", "withexe")
        (src / "helper.exe").write_bytes(b"MZ\x00\x00")
        preview = install.prepare(str(src))
        self.assertTrue(any("helper.exe" in w for w in preview["warnings"]))
        binary = next(f for f in preview["files"] if f["path"] == "helper.exe")
        self.assertIsNone(binary["text"])

    def test_discard_and_bad_tokens(self):
        preview = install.prepare(str(self.write_mod(self.root / "e", "gone")))
        install.discard(preview["token"])
        with self.assertRaises(InstallError):
            install.commit(preview["token"])
        with self.assertRaises(InstallError):
            install.commit("../../etc")

    def test_remove_deletes_the_folder_and_forgets_it_was_enabled(self):
        src = self.write_mod(self.root / "f", "temp")
        install.commit(install.prepare(str(src))["token"], enable=True)
        install.remove("temp")
        self.assertFalse((self.mods_dir / "temp").exists())
        self.assertIsNone(registry.get("temp"))
        from core.settings_store import load_settings

        self.assertNotIn("temp", load_settings()["enabled_mods"])
        with self.assertRaises(Exception):
            install.remove("convert")
        with self.assertRaises(Exception):
            install.remove("nope")

    def test_listing_expectations_are_checked_against_the_real_manifest(self):
        src = self.write_mod(self.root / "g", "real", extra="[permissions]\nnetwork = true\n")
        with self.assertRaisesRegex(InstallError, "Nothing was installed"):
            install.prepare(str(src), expect={"id": "other"})
        preview = install.prepare(
            str(src), expect={"id": "real", "version": "9.9.9", "permissions": {"network": False}}
        )
        text = " ".join(preview["warnings"])
        self.assertIn("9.9.9", text)
        self.assertIn("uses the network", text)


class GitHubInstallTests(InstallTestCase):
    """GitHub installs resolve a commit first, then download exactly that commit."""

    def fake_github(self, versions: dict[str, tuple[str, bytes]]):
        """versions: sha -> (label, zip bytes). The ref 'HEAD' resolves to the last one."""
        calls: list[str] = []
        order = list(versions)

        def fake_get(url, *, accept=None, limit=0):
            calls.append(url)
            if "/commits/" in url:
                ref = url.rsplit("/", 1)[1]
                if ref in versions:
                    return ref.encode()
                if ref == "HEAD":
                    return order[-1].encode()
                raise InstallError("Not found.")
            sha = url.rsplit("/", 1)[1]
            return versions[sha][1]

        return fake_get, calls

    def repo_zip(self, version, tag, subdir=""):
        base = f"{subdir}/" if subdir else ""
        return make_zip(
            {f"{base}mod.toml": toml("gh-mod", version), f"{base}main.py": MAIN_PY.format(tag=tag), "README.md": "hi"},
            wrapper="repo-abcdef",
        )

    def test_install_pins_the_resolved_commit(self):
        fake, calls = self.fake_github({SHA_A: ("v1", self.repo_zip("1.0.0", "v1"))})
        with mock.patch.object(install, "_http_get", fake):
            preview = install.prepare("https://github.com/o/r")
        self.assertEqual(preview["source"]["commit"], SHA_A)
        self.assertTrue(calls[-1].endswith(f"/zip/{SHA_A}"), "downloads the commit, not the branch")
        with mock.patch.object(install, "_http_get", fake):
            install.commit(preview["token"])
        meta = read_install_meta(self.mods_dir / "gh-mod")
        self.assertEqual((meta["type"], meta["url"], meta["commit"]), ("git", "https://github.com/o/r", SHA_A))

    def test_subfolder_of_a_repo(self):
        fake, _ = self.fake_github({SHA_A: ("v1", self.repo_zip("1.0.0", "v1", subdir="mods/gh"))})
        with mock.patch.object(install, "_http_get", fake):
            preview = install.prepare("https://github.com/o/r", ref=SHA_A, subdir="mods/gh")
        self.assertEqual({f["path"] for f in preview["files"]}, {"mod.toml", "main.py"})

    def test_missing_manifest_in_subfolder(self):
        fake, _ = self.fake_github({SHA_A: ("v1", self.repo_zip("1.0.0", "v1"))})
        with mock.patch.object(install, "_http_get", fake), self.assertRaisesRegex(InstallError, "no mod.toml"):
            install.prepare("https://github.com/o/r", subdir="nope")

    def test_update_check_and_reviewed_update(self):
        versions = {SHA_A: ("v1", self.repo_zip("1.0.0", "v1"))}
        fake, _ = self.fake_github(versions)
        with mock.patch.object(install, "_http_get", fake):
            install.commit(install.prepare("https://github.com/o/r")["token"])
            self.assertFalse(install.check_update("gh-mod")["available"])

        versions[SHA_B] = ("v2", self.repo_zip("1.1.0", "v2"))
        fake, _ = self.fake_github(versions)
        with mock.patch.object(install, "_http_get", fake):
            status = install.check_update("gh-mod")
            self.assertTrue(status["available"])
            self.assertEqual((status["current"], status["latest"]), (SHA_A, SHA_B))
            self.assertEqual(status["compare_url"], f"https://github.com/o/r/compare/{SHA_A}...{SHA_B}")

            preview = install.prepare_update("gh-mod")
            self.assertEqual(preview["replaces"], {"version": "1.0.0", "commit": SHA_A})
            self.assertIn({"path": "main.py", "status": "changed"}, preview["changes"])
            # Nothing changes until the update is approved.
            self.assertIn("'v1'", (self.mods_dir / "gh-mod" / "main.py").read_text(encoding="utf-8"))
            install.commit(preview["token"])
        self.assertIn("'v2'", (self.mods_dir / "gh-mod" / "main.py").read_text(encoding="utf-8"))
        self.assertEqual(read_install_meta(self.mods_dir / "gh-mod")["commit"], SHA_B)

    def test_update_keeps_the_mod_enabled_and_other_mods_cannot_replace_it(self):
        fake, _ = self.fake_github({SHA_A: ("v1", self.repo_zip("1.0.0", "v1"))})
        with mock.patch.object(install, "_http_get", fake):
            install.commit(install.prepare("https://github.com/o/r")["token"], enable=True)
            install.commit(install.prepare_update("gh-mod")["token"])
        self.assertTrue(registry.get("gh-mod").enabled)
        other = self.write_mod(self.root / "elsewhere", "gh-mod")
        with self.assertRaisesRegex(InstallError, "already installed"):
            install.prepare(str(other))

    def test_update_check_is_only_for_git_installs(self):
        install.commit(install.prepare(str(self.write_mod(self.root / "loc", "local")))["token"])
        self.assertFalse(install.check_update("local")["supported"])
        with self.assertRaises(InstallError):
            install.prepare_update("local")


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class GitBinaryTests(InstallTestCase):
    def git(self, *args, cwd):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
            cwd=cwd, check=True, capture_output=True,
        )

    def test_clone_pins_a_commit_and_drops_git_metadata(self):
        repo = self.root / "repo"
        self.write_mod(repo / "sub", "from-git", tag="one")
        self.git("init", "-q", cwd=self.root / "repo")
        self.git("add", "-A", cwd=repo)
        self.git("commit", "-q", "-m", "one", cwd=repo)
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()
        self.write_mod(repo / "sub", "from-git", tag="two")
        self.git("commit", "-qam", "two", cwd=repo)

        url = repo.as_uri()
        with mock.patch.object(install, "_GIT_PROTOCOLS", "file:https"):
            source = install.GitSource(url=url, ref="", subdir="sub")
            latest = install.resolve_commit(source)
            self.assertNotEqual(latest, sha)
            self.assertEqual(install.resolve_commit(install.GitSource(url=url, ref=sha)), sha)

            dest = self.root / "checkout"
            install._git_fetch(url, sha, dest)
        self.assertFalse((dest / ".git").exists())
        self.assertIn("'one'", (dest / "sub" / "main.py").read_text(encoding="utf-8"))

    def test_git_only_speaks_https_by_default(self):
        repo = self.root / "repo2"
        self.write_mod(repo, "x")
        self.git("init", "-q", cwd=repo)
        self.git("add", "-A", cwd=repo)
        self.git("commit", "-q", "-m", "x", cwd=repo)
        with self.assertRaises(InstallError):
            install._git_fetch(repo.as_uri(), "HEAD", self.root / "nope")


if __name__ == "__main__":
    unittest.main()
