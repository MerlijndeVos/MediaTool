# Writing mods

A **mod** adds one tool to Toolbox: it shows up in the sidebar and home screen, gets an
automatically generated form, runs as a normal background job (live log, progress, cancel),
and is also a `toolbox <id>` command. Toolbox's own features are mods too. Their
folders in [`builtin_mods/`](builtin_mods) are working examples.

A mod is a folder with two files:

```
my-mod/
  mod.toml    # what the mod is and what it asks for (plain data, never runs code)
  main.py     # def run(params, ctx): ...
```

## Try the example

1. **Settings → Mods → Add a mod**, choose the folder
   [`examples/mods/count-files`](examples/mods/count-files) (or run
   `toolbox mods install examples/mods/count-files`). Toolbox shows what it is and asks first.
2. Turn **Count Files** on (the install prompt has a checkbox for it, or
   `toolbox mods enable count-files`).
3. Open **Count Files** in the sidebar (group *Other*), or run
   `toolbox count-files --folder D:\Videos`.

Mods you add yourself start **off** unless you tick *Turn on after installing*. Nothing from a
mod runs until it is on, and `main.py` is only imported when you actually run the mod. Start
Toolbox with `--no-mods` (or set `TOOLBOX_NO_MODS=1`), or press **Safe mode** in Settings → Mods,
to load none of them, for example if one misbehaves.

## Installing, updating and removing

Everything below shows a **trust prompt** first (what the mod is, who wrote it, where it comes
from, the exact commit, what it declares it needs, and every file) and installs nothing until
you say yes. The mod is downloaded and checked, but not run.

| From | In the app (Settings → Mods → Add a mod) | Command line |
| --- | --- | --- |
| A git address | paste `https://github.com/name/my-mod`, optionally a tag, branch or commit | `toolbox mods install https://github.com/name/my-mod --ref v1.2` |
| A folder | *Choose folder* | `toolbox mods install D:\mods\my-mod` |
| A `.zip` | *Choose file* | `toolbox mods install my-mod.zip` |
| A single `.py` file | *Choose file* | `toolbox mods install my-mod.py` |
| The market | Settings → Mods → **Browse** | `toolbox mods search subtitles` |

- **Git installs are pinned.** The ref you give (or the default branch) is turned into a full
  commit hash first, and exactly that commit is downloaded and recorded. GitHub repositories are
  fetched as an archive, so you do not need `git`; other `https://` hosts need `git` installed.
  A repository can hold several mods: point at one with a folder (`--subdir mods/my-mod`, or a
  `https://github.com/name/repo/tree/<ref>/<folder>` address).
- **Updates are never automatic.** *Check for updates* (or `toolbox mods update`) compares the
  recorded commit with the current one. To apply an update you review the changed files, and
  approve, the same way as an install. Whether the mod is on or off stays as it was.
- **Remove** deletes the mod's folder and forgets that it was enabled (`toolbox mods remove <id>`).
- **View code** in the mods list shows every file of an installed mod.
- A **single `.py` file** has no `mod.toml`, so the manifest goes in a comment block at the top:

  ```python
  # /// toolbox-mod
  # id = "hello"
  # name = "Hello"
  # [ui]
  # run_mode = "run"
  # ///
  def run(params, ctx):
      ctx.log("hello")
  ```

  The block holds the same TOML as `mod.toml`; the file is installed as `main.py`.
- A mod folder, zip or repository can have at most 500 files and 20 MB, and cannot contain
  symbolic links.

## Share your mod

Put it in a public git repository, then **list it in the [market](market/README.md)** by opening a
pull request that adds an entry to `market/index.json`. Anyone can then find it under
**Settings → Mods → Browse** or on the website, and install it pinned to the commit you listed.

## `mod.toml`

```toml
id = "count-files"            # required: lowercase letters, digits, - and _
name = "Count Files"          # required: what the sidebar shows
description = "Count the files in a folder, grouped by extension."
version = "1.0.0"
author = "You"
api_version = 1               # the mod API this mod was written for
group = "Other"               # sidebar/home section; new names create a new section
order = 1000                  # position within the group (lower = earlier)
icon = "puzzle"               # one of: archive audio-lines combine copy disc-3 download eraser
                              #   file-text file-video film folder folder-pen image languages
                              #   music pen-line puzzle scissors search sparkles tag wrench
entry = "main.py"             # optional

[ui]
run_mode = "run"              # "run" = one Run button, "preview_apply" = Preview + Apply buttons
# For preview_apply: the bool param the two buttons set. Preview -> dry_run = true.
mode_param = "dry_run"        # default; use "apply" together with mode_inverted = true
mode_inverted = false         #   when the param means "really do it" (Preview -> apply = false)
apply_hint = ""               # extra sentence in the "Apply changes?" confirmation

[run]
undo = false                  # true if the mod records an undo manifest (see below)
max_concurrent = 0            # limit parallel runs of this mod (0 = no limit)
cancel = "immediate"          # or "cooperative": the mod stops itself, the job ends when it does
loggers = []                  # extra logger names whose file handlers are closed after a run

[permissions]                 # advisory: shown in Settings → Mods, NOT enforced
network = false
writes_files = false
runs_programs = false
```

If you leave `[ui]` out, `run_mode` defaults to `preview_apply`, which needs a bool param named
`dry_run`. Mods that only read data should set `run_mode = "run"`.

### Parameters

Each `[[params]]` table becomes a form field, a `--flag` on the command line, and a validated
field in the API. There is no frontend code to write.

```toml
[[params]]
name = "top"                  # required: lowercase, digits, underscores. Key in `params`.
type = "integer"              # see the table below (default "text")
label = "Show the top N extensions"
help = "How many extensions to list."   # tooltip in the form, --help text on the CLI
default = 10                  # no default = the field is required
min = 1
max = 100
```

| `type` | Form field | Arrives in `run()` as |
|--------|------------|-----------------------|
| `text` | text box | `str` |
| `integer`, `number` | number box (`min`, `max`) | `int`, `float` |
| `bool` | switch | `bool` |
| `choice` | dropdown from `choices` | `str` |
| `folder`, `file` | path box with a Browse button in the desktop app | `str` (path) |
| `files`, `list` | one entry per line | `list[str]` |
| `json` | JSON text box | `dict` |

More fields: `placeholder`, `required` (defaults to "no default given"), `nullable = true`
(empty field becomes `None`), `ui = false` (accepted by the API and CLI but not shown in the
form), `width = "half"` (put two short fields side by side), and for `choice`:

```toml
choices = ["low", "high"]                                  # or
choices = [{ value = "low", label = "Low quality" }, { value = "high", label = "High" }]
strict = false               # dropdown only suggests values; any string is accepted
```

`initial` sets what the form starts with when that differs from the API `default`.

## `main.py`

```python
def run(params, ctx):
    ctx.log(f"Looking in {params['folder']}")
    ...
```

`params` is a plain `dict` of the validated values. Raise an exception to fail the job; its
message is shown to the user. Return normally to finish.

### `ctx`

| | |
|---|---|
| `ctx.log(message, level=logging.INFO)` | Write a line to the job log. |
| `ctx.progress(0.5, "Halfway")` | Report progress: a fraction from 0.0 to 1.0, plus optional text. |
| `ctx.cancelled()` | `True` once the user pressed cancel. Check it in loops. |
| `ctx.raise_if_cancelled()` | Stop and mark the job cancelled if the user cancelled. |
| `ctx.ffmpeg`, `ctx.ffprobe` | Paths to the tools (downloads them first if needed). |
| `ctx.run([...])` | Run a program from an argument **list** (never a shell string). Output goes to the log; cancelling stops it. Raises on a non-zero exit unless `check=False`. |
| `ctx.set_undo_manifest(data)` | See below. |
| `ctx.job_id`, `ctx.mod_id`, `ctx.cancel_event` | Identifiers and the raw cancel event. |

### Undo (optional)

Set `undo = true` under `[run]`, call `ctx.set_undo_manifest({...})` with whatever you need
to reverse the run (only when something changed), and export:

```python
def undo(manifest, ctx):
    ...
    return {"restored": 3, "failed": 0, "skipped": 0}
```

The log drawer then offers an Undo button for that job. The built-in Rename mod works this way.

### Advanced: your own validation

A mod without `[[params]]` may export a pydantic model named `Params`; it is used to validate
requests instead. Built-in mods with a custom panel do this (see `builtin_mods/rename`).

## What a mod can import

Mods run inside Toolbox's own Python, so they can use the **standard library** and the
packages Toolbox ships with (`yt_dlp`, `openai`, `httpx`, `pydantic`, `certifi`). To call an AI model, use `core.ai.get_provider()` so the user's chosen provider is used. There is no way to
install extra packages for a mod. If your mod has helper modules, put them next to `main.py`
and import them relatively: `from .helpers import tidy`.

In the installed (packaged) app only the parts of the standard library that Toolbox or the
list in `packaging/toolbox.spec` use are bundled. If a mod needs an unusual stdlib module and
fails with `ModuleNotFoundError`, that module needs adding to the list.

## Security

**A mod is code that runs with the same access as Toolbox.** It can read, change and delete
any file you can, use the network and start programs. Python cannot sandbox that, so:

- Only turn on mods from people you trust, and read the code first (or use the
  [review prompt](#ask-an-ai-assistant-to-review-a-mod) below).
- The `[permissions]` table is what the author says the mod does. It is shown to you, but it is
  not enforced.
- Installing shows the source, the exact commit, the author and the declared access before
  anything is copied, and installs nothing until you approve. Git installs are pinned to a commit.
- Mods start off (unless you tick the box when installing), are opt-in one at a time, and are
  never updated automatically: an update shows you what changed and waits for your approval.
- Safe mode (`--no-mods`, or the **Safe mode** button in Settings → Mods) runs the app without
  any user mods. A mod that crashes fails its own job with the error in the log; it does not
  take the app down.
- **Mods are third-party code. The project does not vet them**, and neither the market nor any
  other list says a mod is safe. AI-written mods can be wrong too.

Built-in features cannot be turned off, and a user mod cannot take over a built-in id.

## Ask an AI assistant to write one

Paste this into any AI assistant and replace the last paragraph with what you want. Then check
the result (see Security above) before you install it. In the app, **Settings → Mods → Copy AI
prompt** copies exactly this text (and `toolbox mods prompt` prints it).

````text
You are helping me build a mod for Toolbox, a desktop app that converts, renames and
organizes media files with ffmpeg and yt-dlp. A mod adds one new tool to the app. Write the
complete mod for the feature I describe at the bottom.

## What to produce
A folder with exactly these files, each in its own code block labelled with its path:
1. `mod.toml`: the manifest
2. `main.py`: the code
3. `README.md`: 3-5 lines on what it does and how to use it

## mod.toml
- Top level: `id` (lowercase letters, digits, `-`, `_`; e.g. "strip-metadata"), `name`,
  `description`, `version = "1.0.0"`, `author`, `api_version = 1`, optional `group` (default
  "Other") and `icon` (one of: archive audio-lines combine copy disc-3 download eraser
  file-text file-video film folder folder-pen image languages music pen-line puzzle scissors
  search sparkles tag wrench; default "puzzle").
- `[ui]`: `run_mode = "run"` (one Run button) for tools that only read or create new files.
  For tools that change existing files use `run_mode = "preview_apply"` and declare a bool
  param `dry_run` with `default = true` (Preview sets it to true, Apply to false).
- `[permissions]` (advisory, shown to the user, be honest): `network`, `writes_files`,
  `runs_programs`, each true or false.
- One `[[params]]` table per input. Fields: `name` (lowercase, underscores), `type`, `label`,
  `help` (a short tooltip), `default` (omit it to make the field required), `placeholder`,
  `min`/`max` (numbers), `nullable = true` (empty means None), `width = "half"`.
  Types: `text`, `integer`, `number`, `bool`, `choice` (add `choices = ["a", "b"]`),
  `folder`, `file`, `files` (list of paths, one per line), `list`, `json`.

## main.py
It must define `run(params, ctx)`. `params` is a dict with the values declared above.
`ctx` provides:
- `ctx.log(message)`: write a line to the job log
- `ctx.progress(fraction, text=None)`: 0.0 to 1.0
- `ctx.cancelled()` and `ctx.raise_if_cancelled()`: check these in loops so cancel works
- `ctx.ffmpeg` and `ctx.ffprobe`: paths to the tools
- `ctx.run([args...])`: run a program from an argument list (never a shell string); its
  output goes to the log and a non-zero exit raises an error

## Rules
- Python standard library only, plus `yt_dlp`, `openai`, `pydantic` if truly needed. No other
  packages, no pip installs.
- Never delete or overwrite the user's files. Write results to a new file or folder, or, if
  the feature has to change files, support `dry_run` (default true) that only logs what it
  would do.
- Use `pathlib`. Paths may contain spaces and non-ASCII characters, and the user may be on
  Windows, macOS or Linux.
- No network access unless the feature needs it (then declare `network = true`).
- Log what you do so the user can follow along. Report problems with
  `raise RuntimeError("clear message")`, not a bare traceback.
- Keep it simple and readable. No unrelated extras.

## How to answer
First, in 2-4 sentences, restate what you understood and list any assumptions. If something
important is unclear, ask me at most 3 short questions BEFORE writing code. Then give the
files. Finally, list 2-3 things I should test before trusting it.

## The feature I want
<DESCRIBE YOUR FEATURE HERE: what goes in, what should come out, and any examples. For
example: "For every video in a folder, cut the first 10 seconds and save the result next to
the original with '_trimmed' added to the name.">
````

## Ask an AI assistant to review a mod

Before you install a mod someone else wrote, paste this into an AI assistant together with the
mod's files. It explains in plain language what the code does, which files and programs it
touches, and whether that matches what the mod declares. It cannot run the code, so treat the
answer as a second opinion, not a guarantee. In the app, the install prompt has a
**Copy review prompt with the code** button (and `toolbox mods prompt --review` prints this text).

````text
You are a careful, plain-spoken code reviewer. I am thinking about installing a mod for
Toolbox, a desktop app that converts, renames and organizes media files. A mod is code that
runs on my computer with the same access as the app: it can read, change and delete my files,
use the network and start programs. Below are the mod's manifest and code. I am not a
programmer, so explain in plain language.

## What I want from you
1. **What it does**: 2-4 sentences, based on the code and not only on its description.
2. **Files**: every file or folder it reads, creates, changes, moves or deletes, and when.
3. **Programs and network**: every program it starts and every web address it contacts.
4. **Anything suspicious**: code unrelated to what it claims to do; code that downloads and
   runs other code (exec, eval, pip, curl, PowerShell, base64 blobs); anything that reads
   passwords, API keys, browser data, SSH keys or environment variables; obfuscated or
   deliberately hard-to-read code; deleting or overwriting my files without a preview.
5. **Does it match its manifest?** Compare what it really does with the `[permissions]`
   it declares (network, writes_files, runs_programs) and say where they disagree.
6. **Verdict**: "looks consistent with what it says" or "has concerns", with the 2-3 most
   important reasons.

Be honest about what you cannot tell. You cannot run the code and you may have missed
something, so say so rather than guessing, and do not call anything "safe".

## The mod
<PASTE mod.toml AND main.py HERE, plus any other .py files in the mod folder.>
````
