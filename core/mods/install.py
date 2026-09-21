"""Install, update and remove user mods: from a git URL, a folder, a ``.zip`` or a single ``.py`` file
(a theme can also be a single ``.toml`` file).

Installing is two steps so nothing reaches the mods folder before the user has seen what they
are getting:

1. :func:`prepare` downloads or copies the mod into a staging folder and validates its
   manifest. **Nothing is imported or run.** The result describes the mod (author, declared
   access, exact commit, every file) for the trust prompt.
2. :func:`commit` moves the staged mod into ``<app data>/mods/<id>/`` and records where it came
   from. :func:`discard` throws a staged mod away.

Git installs are pinned: the ref the user gives (or the default branch) is resolved to a full
commit hash first and that exact commit is what gets downloaded and recorded. GitHub repos are
fetched as an archive, so no ``git`` program is needed; other https hosts use ``git`` if present.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..runtime import app_data_dir
from .groups import group_key, near_miss_message
from .manifest import MANIFEST_NAME, ManifestError, ModManifest, load_manifest
from .registry import INSTALL_META, ModError, read_install_meta, registry, unload_modules, user_mods_dir

STAGING_DIRNAME = "mods-staging"
USER_AGENT = "Toolbox-mod-installer"

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")

MAX_TOTAL_BYTES = 20 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 25 * 1024 * 1024
MAX_FILES = 500
STALE_STAGING_SECONDS = 3600

# What the trust prompt can show inline: text files up to this size, up to this much in all.
VIEW_FILE_BYTES = 60_000
VIEW_TOTAL_BYTES = 400_000

SKIPPED_DIRS = frozenset({".git", "__pycache__"})
# Files that are programs rather than mod code: worth a warning in the trust prompt.
RISKY_SUFFIXES = frozenset(
    {".exe", ".dll", ".so", ".dylib", ".pyd", ".bat", ".cmd", ".ps1", ".sh", ".jar", ".msi", ".scr", ".vbs", ".com"}
)

# The protocols ``git`` may use while cloning. Tests widen this to reach a local repository.
_GIT_PROTOCOLS = "https"

INLINE_MANIFEST_RE = re.compile(r"(?m)^# /// (?P<kind>[a-zA-Z0-9-]+)$\s(?P<body>(?:^#(?: .*)?$\s)+)^# ///$")


class InstallError(ModError):
    """A mod could not be installed; the message says why in plain words."""


# --------------------------------------------------------------------------------------------
# Where a mod comes from
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GitSource:
    url: str  # https clone URL without ".git" or a "/tree/..." tail
    ref: str = ""  # branch, tag or commit; empty = the default branch
    subdir: str = ""  # folder inside the repo that holds mod.toml; empty = the repo root

    @property
    def github(self) -> tuple[str, str] | None:
        parts = urllib.parse.urlsplit(self.url)
        if (parts.hostname or "").lower() != "github.com":
            return None
        bits = [b for b in parts.path.split("/") if b]
        return (bits[0], bits[1]) if len(bits) == 2 else None


def looks_like_git(location: str) -> bool:
    text = location.strip().lower()
    return text.startswith(("https://", "http://", "git@", "ssh://", "git://")) or text.endswith(".git")


def _clean_subdir(subdir: str) -> str:
    parts = [p for p in re.split(r"[\\/]+", subdir.strip()) if p and p != "."]
    if any(p == ".." or ":" in p for p in parts):
        raise InstallError("The folder inside the repository cannot contain '..'.")
    return "/".join(parts)


def parse_git_url(location: str, ref: str = "", subdir: str = "") -> GitSource:
    """Turn what the user pasted into a :class:`GitSource`. Only https URLs are accepted."""
    text = location.strip()
    if text.lower().startswith("http://"):
        raise InstallError("Use an https:// address; plain http is not accepted.")
    if not text.lower().startswith("https://"):
        raise InstallError("Paste an https:// git address, for example https://github.com/name/my-mod.")
    parts = urllib.parse.urlsplit(text)
    if not parts.hostname or parts.username or parts.password:
        raise InstallError("The address must be a plain https URL without a user name or password.")
    segments = [s for s in parts.path.split("/") if s]
    url_ref, url_subdir = "", ""
    if (parts.hostname or "").lower() == "github.com" and len(segments) >= 4 and segments[2] in ("tree", "blob"):
        # https://github.com/owner/repo/tree/<ref>[/<folder>]: a branch name with a slash is ambiguous,
        # so the ref is one segment; use the separate ref field for anything fancier.
        url_ref, url_subdir = segments[3], "/".join(segments[4:])
        segments = segments[:2]
    if segments and segments[-1].endswith(".git"):
        segments[-1] = segments[-1][: -len(".git")]
    if not segments:
        raise InstallError("That address does not point at a repository.")
    port = f":{parts.port}" if parts.port else ""
    url = f"https://{parts.hostname}{port}/{'/'.join(segments)}"
    return GitSource(url=url, ref=(ref or url_ref).strip(), subdir=_clean_subdir(subdir or url_subdir))


# --------------------------------------------------------------------------------------------
# Network and git (kept small and separate so tests can replace them)
# --------------------------------------------------------------------------------------------


def _http_get(url: str, *, accept: str | None = None, limit: int = MAX_DOWNLOAD_BYTES) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise InstallError("That download is too large for a mod.")
                chunks.append(chunk)
            return b"".join(chunks)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise InstallError("Not found. Check the address and the ref (private repositories are not supported).") from exc
        if exc.code in (403, 429):
            raise InstallError("The server refused the request (rate limit?). Try again in a while.") from exc
        raise InstallError(f"The server answered {exc.code}.") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise InstallError(f"Could not reach the server: {getattr(exc, 'reason', exc)}") from exc


def _github_resolve(owner: str, repo: str, ref: str) -> str:
    quoted = urllib.parse.quote(ref or "HEAD", safe="")
    body = _http_get(
        f"https://api.github.com/repos/{owner}/{repo}/commits/{quoted}",
        accept="application/vnd.github.sha",
        limit=4096,
    )
    sha = body.decode("ascii", errors="replace").strip().lower()
    if not SHA_RE.match(sha):
        raise InstallError("GitHub did not return a commit for that ref.")
    return sha


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ALLOW_PROTOCOL"] = _GIT_PROTOCOLS
    return env


def _run_git(args: list[str], *, cwd: Path | None = None) -> str:
    git = shutil.which("git")
    if not git:
        raise InstallError(
            "This address is not on GitHub, and installing from it needs the 'git' program, which "
            "was not found. Install git, or download the repository as a zip and add that instead."
        )
    try:
        done = subprocess.run(
            [git, *args], cwd=cwd, env=_git_env(), capture_output=True, text=True, timeout=300, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallError(f"git failed: {exc}") from exc
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()
        raise InstallError("git failed: " + (detail[-1] if detail else f"exit code {done.returncode}"))
    return done.stdout.strip()


def _git_resolve(url: str, ref: str) -> str:
    if SHA_RE.match(ref.lower()):
        return ref.lower()
    name = ref or "HEAD"
    out = _run_git(["ls-remote", url, name, name + "^{}"])
    found = ""
    for line in out.splitlines():
        sha, _, refname = line.partition("\t")
        sha = sha.strip().lower()
        if not SHA_RE.match(sha):
            continue
        if refname.endswith("^{}"):  # an annotated tag: the commit behind it, not the tag object
            return sha
        found = found or sha
    if found:
        return found
    raise InstallError(f"Could not find ref '{name}' in that repository.")


def _git_fetch(url: str, sha: str, dest: Path) -> None:
    """Clone *url* at *sha* into *dest* without its ``.git`` folder."""
    _run_git(["clone", "--quiet", "--no-checkout", "-c", "core.symlinks=false", url, str(dest)])
    _run_git(["-c", "advice.detachedHead=false", "checkout", "--quiet", "--detach", sha], cwd=dest)
    _rmtree(dest / ".git")


def resolve_commit(source: GitSource) -> str:
    """The full commit hash *source* points at right now."""
    gh = source.github
    if gh:
        return _github_resolve(gh[0], gh[1], source.ref)
    return _git_resolve(source.url, source.ref)


def _fetch_git(source: GitSource, sha: str, dest: Path) -> None:
    gh = source.github
    if gh:
        data = _http_get(f"https://codeload.github.com/{gh[0]}/{gh[1]}/zip/{sha}")
        archive = dest.parent / "download.zip"
        archive.write_bytes(data)
        try:
            _extract_zip(archive, dest)
        finally:
            archive.unlink(missing_ok=True)
        # A GitHub archive wraps everything in one "<repo>-<sha>" folder; step into it.
        entries = list(dest.iterdir())
        if len(entries) == 1 and entries[0].is_dir():
            wrapper = entries[0]
            for child in list(wrapper.iterdir()):
                shutil.move(str(child), str(dest / child.name))
            wrapper.rmdir()
    else:
        _git_fetch(source.url, sha, dest)


def compare_url(source: GitSource, old: str, new: str) -> str | None:
    gh = source.github
    return f"https://github.com/{gh[0]}/{gh[1]}/compare/{old}...{new}" if gh else None


# --------------------------------------------------------------------------------------------
# Files: safe copying and extracting
# --------------------------------------------------------------------------------------------


def _on_rm_error(func, path, _exc) -> None:  # pragma: no cover - Windows read-only files
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _rmtree(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, onerror=_on_rm_error)
    elif path.exists() or path.is_symlink():
        path.unlink()


class _Budget:
    def __init__(self) -> None:
        self.files = 0
        self.bytes = 0

    def add(self, size: int) -> None:
        self.files += 1
        self.bytes += size
        if self.files > MAX_FILES:
            raise InstallError(f"A mod can have at most {MAX_FILES} files.")
        if self.bytes > MAX_TOTAL_BYTES:
            raise InstallError(f"A mod can be at most {MAX_TOTAL_BYTES // (1024 * 1024)} MB.")


def _extract_zip(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    budget = _Budget()
    try:
        zf = zipfile.ZipFile(archive)
    except (zipfile.BadZipFile, OSError) as exc:
        raise InstallError("That is not a valid zip file.") from exc
    with zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            parts = [p for p in name.split("/") if p]
            if not parts:
                continue
            if name.startswith("/") or any(p == ".." or ":" in p for p in parts):
                raise InstallError(f"The zip contains an unsafe path: {info.filename}")
            if info.is_dir() or any(p in SKIPPED_DIRS for p in parts[:-1]):
                continue
            if stat.S_ISLNK(info.external_attr >> 16):
                raise InstallError(f"The zip contains a symbolic link: {info.filename}")
            target = dest.joinpath(*parts).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise InstallError(f"The zip contains an unsafe path: {info.filename}") from exc
            budget.add(info.file_size)
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with zf.open(info) as src, target.open("wb") as out:
                # Count what is really written: the size in the header can lie.
                while chunk := src.read(64 * 1024):
                    written += len(chunk)
                    if written > MAX_TOTAL_BYTES:
                        raise InstallError("A file in the zip is too large.")
                    out.write(chunk)


def _copy_folder(source: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    budget = _Budget()
    for current, dirs, files in os.walk(source, followlinks=False):
        here = Path(current)
        rel = here.relative_to(source)
        for d in list(dirs):
            if d in SKIPPED_DIRS:
                dirs.remove(d)
            elif (here / d).is_symlink():
                raise InstallError(f"The folder contains a symbolic link: {rel / d}")
        for f in files:
            src = here / f
            if src.is_symlink():
                raise InstallError(f"The folder contains a symbolic link: {rel / f}")
            budget.add(src.stat().st_size)
            target = dest / rel / f
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)


def _find_root(staged: Path, subdir: str) -> Path:
    """The folder holding ``mod.toml``: the top, *subdir*, or the one wrapper folder a zip usually has."""
    if subdir:
        root = staged.joinpath(*subdir.split("/"))
        if not (root / MANIFEST_NAME).is_file():
            raise InstallError(f"There is no {MANIFEST_NAME} in '{subdir}'.")
        return root
    if (staged / MANIFEST_NAME).is_file():
        return staged
    children = [c for c in staged.iterdir() if c.is_dir()]
    if len(children) == 1 and (children[0] / MANIFEST_NAME).is_file():
        return children[0]
    raise InstallError(f"No {MANIFEST_NAME} found. A mod is a folder with a {MANIFEST_NAME} and a main.py.")


def _inline_manifest(text: str) -> str | None:
    """The TOML in a ``# /// toolbox-mod`` comment block at the top of a single-file mod."""
    for match in INLINE_MANIFEST_RE.finditer(text.replace("\r\n", "\n")):
        if match.group("kind") == "toolbox-mod":
            lines = match.group("body").splitlines(keepends=True)
            return "".join(line[2:] if line.startswith("# ") else line[1:] for line in lines)
    return None


# --------------------------------------------------------------------------------------------
# Describing a mod for the trust prompt
# --------------------------------------------------------------------------------------------


def _read_text(path: Path, limit: int) -> tuple[str | None, bool]:
    """(text, truncated), or (None, False) for a binary file."""
    try:
        with path.open("rb") as fh:
            data = fh.read(limit + 1)
    except OSError:
        return None, False
    if b"\x00" in data[:8192]:
        return None, False
    truncated = len(data) > limit
    return data[:limit].decode("utf-8", errors="replace"), truncated


def describe_dir(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Every file in *root* with its size and (for text files) contents, plus warnings."""
    files: list[dict[str, Any]] = []
    risky: list[str] = []
    budget = VIEW_TOTAL_BYTES
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix().lower()):
        if not path.is_file() or path.name == INSTALL_META:
            continue
        rel = path.relative_to(root).as_posix()
        size = path.stat().st_size
        text, truncated = (None, False)
        if budget > 0:
            text, truncated = _read_text(path, min(VIEW_FILE_BYTES, budget))
            if text is not None:
                budget -= len(text.encode("utf-8", errors="replace"))
        files.append({"path": rel, "size": size, "text": text, "truncated": truncated})
        if path.suffix.lower() in RISKY_SUFFIXES:
            risky.append(rel)
    warnings = []
    if risky:
        warnings.append("Contains program files: " + ", ".join(risky[:6]) + (" ..." if len(risky) > 6 else ""))
    return files, warnings


def diff_dirs(old: Path, new: Path, limit: int = 200) -> list[dict[str, str]]:
    def listing(root: Path) -> dict[str, Path]:
        return {
            p.relative_to(root).as_posix(): p
            for p in root.rglob("*")
            if p.is_file() and p.name != INSTALL_META
        }

    before, after = listing(old), listing(new)
    changes: list[dict[str, str]] = []
    for rel in sorted(set(before) | set(after)):
        if rel not in before:
            changes.append({"path": rel, "status": "added"})
        elif rel not in after:
            changes.append({"path": rel, "status": "removed"})
        elif before[rel].read_bytes() != after[rel].read_bytes():
            changes.append({"path": rel, "status": "changed"})
    return changes[:limit]


# --------------------------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------------------------


def staging_dir() -> Path:
    return app_data_dir() / STAGING_DIRNAME


def _token_dir(token: str) -> Path:
    if not TOKEN_RE.match(token or ""):
        raise InstallError("Unknown install session.")
    return staging_dir() / token


def cleanup_stale(max_age: float = STALE_STAGING_SECONDS) -> None:
    root = staging_dir()
    if not root.is_dir():
        return
    cutoff = time.time() - max_age
    for child in root.iterdir():
        try:
            if child.stat().st_mtime < cutoff:
                _rmtree(child)
        except OSError:
            pass


def discard(token: str) -> None:
    _rmtree(_token_dir(token))


def _permissions_text(perms: dict[str, bool]) -> list[str]:
    labels = {"network": "uses the network", "writes_files": "writes files", "runs_programs": "runs programs"}
    return [labels[k] for k in labels if perms.get(k)]


def _check_expectations(manifest: ModManifest, expect: dict[str, Any]) -> list[str]:
    """Compare a market listing with the code that was actually downloaded."""
    if expect.get("id") and expect["id"] != manifest.id:
        raise InstallError(
            f"The listing says this is '{expect['id']}' but the code declares '{manifest.id}'. Nothing was installed."
        )
    # A listing that says "theme" promises there is no code; a tool behind it must never pass as one.
    if expect.get("type") and expect["type"] != manifest.type:
        raise InstallError(
            f"The listing says this is a {expect['type']} but the code is a {manifest.type}. Nothing was installed."
        )
    warnings: list[str] = []
    if expect.get("group") and not manifest.is_theme and group_key(expect["group"]) != group_key(manifest.group):
        warnings.append(
            f"The listing says this mod appears under '{expect['group']}', the code puts it under '{manifest.group}'."
        )
    if expect.get("version") and str(expect["version"]) != manifest.version:
        warnings.append(f"The listing says version {expect['version']}, the code says {manifest.version}.")
    listed = expect.get("permissions")
    if isinstance(listed, dict):
        actual = manifest.permissions.to_dict()
        extra = [k for k, v in actual.items() if v and not listed.get(k)]
        if extra:
            warnings.append(
                "The mod declares more access than its listing says: "
                + ", ".join(_permissions_text({k: True for k in extra}))
                + "."
            )
    return warnings


def _validate(root: Path) -> ModManifest:
    try:
        manifest = load_manifest(root / MANIFEST_NAME)
    except ManifestError as exc:
        raise InstallError(f"{MANIFEST_NAME}: {exc}") from exc
    if manifest.ui_kind == "builtin":
        raise InstallError('Only built-in features can use ui kind "builtin"; use kind = "form".')
    if manifest.is_theme:
        return manifest  # data only: nothing to import, so no entry file
    entry = (root / manifest.entry).resolve()
    try:
        entry.relative_to(root.resolve())
    except ValueError as exc:
        raise InstallError("The entry file is outside the mod folder.") from exc
    if not entry.is_file():
        raise InstallError(f"The entry file {manifest.entry} is missing.")
    return manifest


def _check_id_free(manifest: ModManifest, update_of: str | None) -> None:
    existing = registry.get(manifest.id)
    if existing is None:
        return
    if existing.builtin:
        raise InstallError(f"'{manifest.id}' is a built-in feature; a mod cannot take its name.")
    if update_of != manifest.id:
        raise InstallError(f"A mod with the id '{manifest.id}' is already installed. Update or remove it first.")


def prepare(
    location: str,
    *,
    ref: str = "",
    subdir: str = "",
    update_of: str | None = None,
    expect: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch and check a mod without running it. Returns what the trust prompt shows."""
    location = (location or "").strip()
    if not location:
        raise InstallError("Enter a git address, or choose a folder, zip or .py file.")
    cleanup_stale()

    token = uuid.uuid4().hex
    work = _token_dir(token)
    staged = work / "mod"
    work.mkdir(parents=True)
    try:
        git: GitSource | None = None
        if looks_like_git(location):
            git = parse_git_url(location, ref, subdir)
            sha = resolve_commit(git)
            _fetch_git(git, sha, staged)
            root = _find_root(staged, git.subdir)
            source: dict[str, Any] = {
                "type": "git",
                "url": git.url,
                "ref": git.ref,
                "commit": sha,
                "subdir": git.subdir,
            }
        else:
            source = _stage_local(Path(location).expanduser(), staged)
            root = staged if source["type"] == "file" else _find_root(staged, "")

        manifest = _validate(root)
        _check_id_free(manifest, update_of)
        if update_of and manifest.id != update_of:
            raise InstallError(f"This is '{manifest.id}', not '{update_of}'. Nothing was changed.")
        warnings = _check_expectations(manifest, expect or {})

        # From here on the thing to install is just the mod folder.
        final = work / "final"
        shutil.move(str(root), str(final))
        _rmtree(staged)
        files, file_warnings = describe_dir(final)
        warnings += file_warnings
        placement = None
        if manifest.is_theme:
            warnings += list(manifest.theme.warnings) if manifest.theme else []
            code = [f["path"] for f in files if f["path"].lower().endswith((".py", ".pyw"))]
            if code:
                warnings.append(
                    "This is a theme, so none of its files is ever run, but the folder also contains "
                    + ", ".join(code[:6])
                    + ". A theme does not need code: ask the author why it is there."
                )
        else:
            placement = registry.place(manifest.group)
            if placement["near_miss"]:
                warnings.append(near_miss_message(manifest.group, placement["near_miss"]))

        replaces = None
        changes = None
        if update_of:
            old = registry.get(update_of)
            if old is not None:
                old_meta = read_install_meta(old.path) or {}
                replaces = {"version": old.manifest.version, "commit": old_meta.get("commit", "")}
                changes = diff_dirs(old.path, final)
        (work / "source.json").write_text(json.dumps(source), encoding="utf-8")
        (work / "meta.json").write_text(json.dumps({"id": manifest.id, "update_of": update_of}), encoding="utf-8")
        return {
            "token": token,
            "manifest": manifest.to_dict(),
            "placement": placement,
            "source": source,
            "files": files,
            "warnings": warnings,
            "replaces": replaces,
            "changes": changes,
            "compare_url": (
                compare_url(git, replaces["commit"], source["commit"])
                if git and replaces and replaces["commit"]
                else None
            ),
        }
    except BaseException:
        _rmtree(work)
        raise


def _stage_local(path: Path, staged: Path) -> dict[str, Any]:
    if path.is_dir():
        _copy_folder(path, staged)
        return {"type": "folder", "path": str(path)}
    if not path.is_file():
        raise InstallError(f"Nothing found at {path}.")
    suffix = path.suffix.lower()
    if suffix == ".zip":
        _extract_zip(path, staged)
        return {"type": "zip", "path": str(path)}
    if suffix == ".py":
        text = path.read_text(encoding="utf-8", errors="replace")
        manifest_toml = _inline_manifest(text)
        if manifest_toml is None:
            raise InstallError(
                "A single .py file needs its manifest in a comment block at the top "
                "(# /// toolbox-mod ... # ///). See MODDING.md."
            )
        staged.mkdir(parents=True)
        (staged / MANIFEST_NAME).write_text(manifest_toml, encoding="utf-8")
        shutil.copyfile(path, staged / "main.py")
        return {"type": "file", "path": str(path)}
    if suffix == ".toml":
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise InstallError(f"That file is not valid TOML: {exc}") from exc
        if data.get("type") != "theme":
            raise InstallError(
                'A single .toml file can only be a theme (type = "theme"). A tool needs a folder, a .zip or a .py file.'
            )
        staged.mkdir(parents=True)
        (staged / MANIFEST_NAME).write_text(text, encoding="utf-8")
        return {"type": "file", "path": str(path)}
    raise InstallError("Choose a folder, a .zip file, a .py file or (for a theme) a .toml file.")


# --------------------------------------------------------------------------------------------
# Commit, remove, update checks
# --------------------------------------------------------------------------------------------


def commit(token: str, *, enable: bool = False) -> ModManifest:
    """Install a staged mod. It is off afterwards unless *enable* is true."""
    work = _token_dir(token)
    final = work / "final"
    try:
        meta = json.loads((work / "meta.json").read_text(encoding="utf-8"))
        source = json.loads((work / "source.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InstallError("That install session has expired. Start again.") from exc
    manifest = _validate(final)
    if manifest.id != meta.get("id"):
        raise InstallError("The staged files changed. Start again.")
    update_of = meta.get("update_of")
    _check_id_free(manifest, update_of)

    target = user_mods_dir(create=True) / manifest.id
    backup = work / "previous"
    (final / INSTALL_META).write_text(
        json.dumps(
            {
                **source,
                "id": manifest.id,
                "version": manifest.version,
                "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if target.exists():
        if not update_of:
            raise InstallError(f"A folder named '{manifest.id}' already exists in the mods folder.")
        shutil.move(str(target), str(backup))
    try:
        shutil.move(str(final), str(target))
    except OSError as exc:
        if backup.exists():
            shutil.move(str(backup), str(target))
        raise InstallError(f"Could not install: {exc}") from exc
    unload_modules(manifest.id)
    _rmtree(work)
    registry.reload()
    if enable:
        registry.set_enabled(manifest.id, True)
    return manifest


def remove(mod_id: str) -> None:
    """Delete an installed (or hand-copied) user mod and forget that it was enabled."""
    mod = registry.get(mod_id)
    if mod is None:
        raise ModError(f"Unknown mod: {mod_id}")
    if mod.builtin:
        raise ModError("Built-in features cannot be removed.")
    mods_root = user_mods_dir().resolve()
    path = mod.path.resolve()
    if path.parent != mods_root or mod.path.is_symlink():
        raise ModError("This mod is not in the mods folder, so Toolbox will not delete it.")
    _rmtree(path)
    unload_modules(mod_id)
    registry.forget_enabled(mod_id)
    registry.reload()


def _git_meta(mod_id: str) -> tuple[Any, dict[str, Any]]:
    mod = registry.get(mod_id)
    if mod is None or mod.builtin:
        raise ModError(f"Unknown mod: {mod_id}")
    return mod, read_install_meta(mod.path) or {}


def check_update(mod_id: str) -> dict[str, Any]:
    """Is there a newer commit for a git-installed mod? Only looks; never changes anything."""
    _, meta = _git_meta(mod_id)
    if meta.get("type") != "git" or not meta.get("url"):
        return {"supported": False, "reason": "Only mods installed from a git address can check for updates."}
    source = GitSource(url=meta["url"], ref=meta.get("ref", ""), subdir=meta.get("subdir", ""))
    latest = resolve_commit(source)
    current = meta.get("commit", "")
    return {
        "supported": True,
        "available": bool(current) and latest != current,
        "current": current,
        "latest": latest,
        "ref": source.ref,
        "compare_url": compare_url(source, current, latest) if current else None,
    }


def prepare_update(mod_id: str) -> dict[str, Any]:
    """Stage the newest commit of a git-installed mod for review (same trust prompt as an install)."""
    _, meta = _git_meta(mod_id)
    if meta.get("type") != "git" or not meta.get("url"):
        raise InstallError("Only mods installed from a git address can be updated this way.")
    return prepare(meta["url"], ref=meta.get("ref", ""), subdir=meta.get("subdir", ""), update_of=mod_id)


def describe_installed(mod_id: str) -> dict[str, Any]:
    """Files and contents of an installed mod, for 'view code'."""
    mod = registry.get(mod_id)
    if mod is None:
        raise ModError(f"Unknown mod: {mod_id}")
    files, warnings = describe_dir(mod.path)
    return {"id": mod.id, "files": files, "warnings": warnings}
