"""CLI support for mods: ``toolbox mods ...`` and one subcommand per enabled mod without one.

A user mod ``count-files`` with a ``folder`` param becomes::

    toolbox count-files --folder D:\\Videos

Built-in features keep their hand-written subcommands in :mod:`cli.args`; a new built-in
mod without one gets a generated subcommand the same way a user mod does.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from core.mods import (
    Mod,
    ModCancelled,
    ModContext,
    ModError,
    ParamSpec,
    install,
    market,
    prompts,
    registry,
    safe_mode,
    user_mods_dir,
)

from .console import console_log, console_progress


def _bounded(base: type, spec: ParamSpec):
    def convert(text: str):
        try:
            value = base(text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{text!r} is not a valid {base.__name__}") from exc
        if spec.minimum is not None and value < spec.minimum:
            raise argparse.ArgumentTypeError(f"must be at least {spec.minimum:g}")
        if spec.maximum is not None and value > spec.maximum:
            raise argparse.ArgumentTypeError(f"must be at most {spec.maximum:g}")
        return value

    convert.__name__ = base.__name__
    return convert


def _json_object(text: str) -> dict:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise argparse.ArgumentTypeError("expected a JSON object")
    return value


def _add_param(parser: argparse.ArgumentParser, spec: ParamSpec) -> None:
    flag = "--" + spec.name.replace("_", "-")
    help_text = spec.help or spec.label
    kwargs: dict[str, Any] = {"dest": spec.name, "help": help_text}
    default = spec.default if spec.has_default else None

    if spec.type == "bool":
        parser.add_argument(flag, action=argparse.BooleanOptionalAction, default=bool(default), **kwargs)
        return

    if spec.type == "integer":
        kwargs["type"] = _bounded(int, spec)
    elif spec.type == "number":
        kwargs["type"] = _bounded(float, spec)
    elif spec.type in ("files", "list"):
        kwargs["nargs"] = "+"
    elif spec.type == "json":
        kwargs["type"] = _json_object
    if spec.type == "choice" and spec.strict:
        kwargs["choices"] = [c.value for c in spec.choices]

    required = spec.required
    if required:
        parser.add_argument(flag, required=True, **kwargs)
    else:
        parser.add_argument(flag, default=default, **kwargs)


def register(subparsers: Any) -> None:
    """Add ``mods`` and a generated subcommand for every enabled mod that has none yet."""
    mods = subparsers.add_parser(
        "mods",
        help="List, install, update, enable, disable or remove mods.",
        description="Manage mods. A mod is code that runs with the same access as Toolbox: read it before you install it.",
    )
    actions = mods.add_subparsers(dest="mods_action", required=True)
    actions.add_parser("list", help="List built-in features and user mods.")
    actions.add_parser("folder", help="Print the folder where user mods live.")

    inst = actions.add_parser(
        "install",
        help="Install a mod from a git address, folder, .zip or .py file.",
        description="Shows what the mod is and where it comes from, then asks before installing. Nothing runs.",
    )
    inst.add_argument("location", help="https:// git address (GitHub, or any host if git is installed), or a local path.")
    inst.add_argument("--ref", default="", help="Branch, tag or commit to install (git addresses). Default: the default branch.")
    inst.add_argument("--subdir", default="", help="Folder inside the repository that holds mod.toml.")
    inst.add_argument("--yes", "-y", action="store_true", help="Do not ask; the details are still printed.")
    inst.add_argument("--enable", action="store_true", help="Turn the mod on after installing.")

    remove = actions.add_parser("remove", help="Delete an installed mod.")
    remove.add_argument("id", help="Mod id (see 'mods list').")
    remove.add_argument("--yes", "-y", action="store_true", help="Do not ask.")

    update = actions.add_parser(
        "update",
        help="Check git-installed mods for newer commits; with an id, review and apply the update.",
    )
    update.add_argument("id", nargs="?", help="Mod id. Without it, only check every git-installed mod.")
    update.add_argument("--yes", "-y", action="store_true", help="Do not ask before applying.")

    search = actions.add_parser("search", help="Search the mod market.")
    search.add_argument("query", nargs="*", help="Words to look for in names, descriptions, authors and tags.")
    search.add_argument("--refresh", action="store_true", help="Reload the list instead of using the cached one.")

    prompt = actions.add_parser("prompt", help="Print the copy-paste prompt for an AI assistant.")
    prompt.add_argument(
        "--review", action="store_true", help="Print the prompt for reviewing a mod instead of writing one."
    )
    for name, text in (("enable", "Turn a user mod on."), ("disable", "Turn a user mod off.")):
        sub = actions.add_parser(name, help=text)
        sub.add_argument("id", help="Mod id (see 'mods list').")

    for mod in registry.enabled():
        # Built-in features that already have a hand-written subcommand (cli/args.py) keep it.
        if mod.id in subparsers.choices:
            continue
        sub = subparsers.add_parser(
            mod.id,
            help=mod.manifest.description or f"User mod {mod.manifest.name}.",
            description=mod.manifest.description or None,
        )
        for spec in mod.manifest.params:
            _add_param(sub, spec)
        sub.set_defaults(_mod_id=mod.id)


def _print_mods() -> None:
    if safe_mode():
        print("Safe mode: user mods are off (--no-mods / TOOLBOX_NO_MODS).")
    for mod in registry.all():
        if mod.builtin:
            state = "built-in"
        else:
            state = "on" if mod.enabled else "off"
        print(f"{mod.id:<22} {state:<9} {mod.manifest.version:<8} {mod.manifest.description}")
    for err in registry.errors():
        print(f"! {err.path}: {err.message}", file=sys.stderr)


def _fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def _confirm(question: str, assume_yes: bool) -> None:
    if assume_yes:
        return
    if not sys.stdin.isatty():
        _fail("Refusing to continue without a terminal to ask you. Use --yes to confirm in scripts.")
    try:
        answer = input(f"{question} [y/N] ")
    except EOFError:  # e.g. stdin is /dev/null, which some platforms still call a terminal
        _fail("No answer available. Use --yes to confirm in scripts.")
    if answer.strip().lower() not in ("y", "yes"):
        print("Cancelled.")
        sys.exit(0)


_ACCESS_LABELS = (
    ("network", "uses the network"),
    ("writes_files", "writes files"),
    ("runs_programs", "runs programs"),
)


def _print_preview(preview: dict) -> None:
    """The trust prompt, as text."""
    manifest, source = preview["manifest"], preview["source"]
    declared = [label for key, label in _ACCESS_LABELS if manifest["permissions"].get(key)]
    print(f"\n{manifest['name']}  v{manifest['version']}  (id: {manifest['id']})")
    if manifest["author"]:
        print(f"  Author:      {manifest['author']}")
    if manifest["description"]:
        print(f"  Description: {manifest['description']}")
    if source["type"] == "git":
        print(f"  From:        {source['url']}" + (f"  [{source['subdir']}]" if source["subdir"] else ""))
        print(f"  Commit:      {source['commit']}  (pinned)")
    else:
        print(f"  From:        {source['type']} {source.get('path', '')}")
    print(f"  Declares:    {', '.join(declared) if declared else 'no special access'}  (not enforced)")
    print(f"  Files:       {', '.join(f['path'] for f in preview['files'])}")
    if preview.get("replaces"):
        old = preview["replaces"]
        print(f"  Replaces:    version {old['version']}" + (f" at {old['commit'][:10]}" if old["commit"] else ""))
        for change in preview.get("changes") or []:
            print(f"    {change['status']:<8} {change['path']}")
        if preview.get("compare_url"):
            print(f"  Changes:     {preview['compare_url']}")
    for warning in preview["warnings"]:
        print(f"  ! {warning}")
    print(
        "\nA mod is code that runs with the same access as Toolbox. It can read, change and delete your\n"
        "files. Toolbox does not vet mods, and the access above is only what the author says.\n"
        "Read the code first (the files are staged; nothing has run)."
    )


def _review_and_commit(preview: dict, question: str, assume_yes: bool, *, enable: bool = False) -> None:
    """Show the trust prompt, ask, then install; the staged copy is dropped on any other outcome."""
    token = preview["token"]
    try:
        _print_preview(preview)
        _confirm(question, assume_yes)
        install.commit(token, enable=enable)
    except ModError as exc:
        install.discard(token)
        _fail(str(exc))
    except BaseException:
        install.discard(token)
        raise


def _install(args: argparse.Namespace) -> None:
    try:
        preview = install.prepare(args.location, ref=args.ref, subdir=args.subdir)
    except ModError as exc:
        _fail(str(exc))
    _review_and_commit(preview, f"\nInstall {preview['manifest']['name']}?", args.yes, enable=args.enable)
    mod_id = preview["manifest"]["id"]
    print(f"Installed {mod_id}." + ("" if args.enable else f" It is off; turn it on with: toolbox mods enable {mod_id}"))


def _remove(args: argparse.Namespace) -> None:
    _confirm(f"Delete the mod '{args.id}' and its files?", args.yes)
    try:
        install.remove(args.id)
    except ModError as exc:
        _fail(str(exc))
    print(f"Removed {args.id}.")


def _update(args: argparse.Namespace) -> None:
    ids = [args.id] if args.id else [m.id for m in registry.all() if not m.builtin]
    for mod_id in ids:
        try:
            status = install.check_update(mod_id)
        except ModError as exc:
            _fail(str(exc))
        if not status["supported"]:
            if args.id:
                _fail(status["reason"])
            continue
        if not status["available"]:
            print(f"{mod_id}: up to date ({status['current'][:10]})")
            continue
        print(f"{mod_id}: update available {status['current'][:10]} -> {status['latest'][:10]}")
        if not args.id:
            print(f"  Review and apply it with: toolbox mods update {mod_id}")
            continue
        try:
            preview = install.prepare_update(mod_id)
        except ModError as exc:
            _fail(str(exc))
        _review_and_commit(preview, f"\nUpdate {mod_id}?", args.yes)
        print(f"Updated {mod_id}.")


def _search(args: argparse.Namespace) -> None:
    result = market.fetch_market(force=args.refresh)
    if result["error"]:
        _fail(result["error"])
    found = [e for e in result["mods"] if market.matches(e, " ".join(args.query))]
    for entry in found:
        print(f"{entry['id']:<22} {entry['version']:<8} {entry['name']}: {entry['description']}")
        where = entry["repo"] + (f" --subdir {entry['path']}" if entry["path"] else "")
        print(f"{'':<22} toolbox mods install {where} --ref {entry['commit']}")
    print(f"{len(found)} of {len(result['mods'])} mods. Listed is not reviewed: read the code before you install.")


def _handle_mods(args: argparse.Namespace) -> None:
    action = args.mods_action
    if action == "list":
        _print_mods()
    elif action == "folder":
        print(user_mods_dir(create=True))
    elif action == "install":
        _install(args)
    elif action == "remove":
        _remove(args)
    elif action == "update":
        _update(args)
    elif action == "search":
        _search(args)
    elif action == "prompt":
        print(prompts.REVIEW_PROMPT if args.review else prompts.BUILD_PROMPT)
    else:
        try:
            mod = registry.set_enabled(args.id, action == "enable")
        except ModError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"{mod.id}: {'on' if mod.enabled else 'off'}")


def _run_mod(mod: Mod, args: argparse.Namespace) -> None:
    params = {spec.name: getattr(args, spec.name, None) for spec in mod.manifest.params}
    ctx = ModContext(mod.id, on_progress=console_progress)
    try:
        mod.run_fn()(params, ctx)
    except ModCancelled:
        print("Cancelled.", file=sys.stderr)
        sys.exit(130)
    except ModError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # a broken mod must not look like a crash of Toolbox
        console_log(f"Error in mod '{mod.id}': {exc}", 40)
        sys.exit(1)


def run_command(args: argparse.Namespace) -> bool:
    """Handle ``mods`` and user-mod subcommands; False if *args* is neither."""
    if args.command == "mods":
        _handle_mods(args)
        return True
    mod_id = getattr(args, "_mod_id", None)
    if mod_id:
        mod = registry.get(mod_id)
        if mod is not None:
            _run_mod(mod, args)
            return True
    return False
