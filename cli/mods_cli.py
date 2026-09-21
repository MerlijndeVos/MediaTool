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
    mods = subparsers.add_parser("mods", help="List, enable or disable mods.", description="Manage mods.")
    actions = mods.add_subparsers(dest="mods_action", required=True)
    actions.add_parser("list", help="List built-in features and user mods.")
    actions.add_parser("folder", help="Print the folder where user mods live.")
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


def _handle_mods(args: argparse.Namespace) -> None:
    action = args.mods_action
    if action == "list":
        _print_mods()
    elif action == "folder":
        print(user_mods_dir(create=True))
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
