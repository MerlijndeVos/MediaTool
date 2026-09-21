"""The two copy-paste prompts for building and reviewing mods with an AI assistant.

Both are plain text with nothing app-specific, so they work with any assistant. They are the single
source of truth: the Mods panel serves them to its "Copy" buttons and ``MODDING.md`` shows the same
text (a test keeps the two in sync). The prompt follows ``API_VERSION`` in :mod:`core.mods.manifest`;
re-test it with a few assistants before a release that changes the mod API.
"""

from __future__ import annotations

from .manifest import API_VERSION

_BUILD = r'''You are helping me build a mod for Toolbox, a desktop app that converts, renames and
organizes media files with ffmpeg and yt-dlp. A mod adds one new tool to the app. Write the
complete mod for the feature I describe at the bottom.

## What to produce
A folder with exactly these files, each in its own code block labelled with its path:
1. `mod.toml`: the manifest
2. `main.py`: the code
3. `README.md`: 3-5 lines on what it does and how to use it

## mod.toml
- Top level: `id` (lowercase letters, digits, `-`, `_`; e.g. "strip-metadata"), `name`,
  `description`, `version = "1.0.0"`, `author`, `api_version = @API_VERSION@`, optional `group` (default
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
the original with '_trimmed' added to the name.">'''

_REVIEW = r'''You are a careful, plain-spoken code reviewer. I am thinking about installing a mod for
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
<PASTE mod.toml AND main.py HERE, plus any other .py files in the mod folder.>'''

BUILD_PROMPT = _BUILD.replace("@API_VERSION@", str(API_VERSION))
REVIEW_PROMPT = _REVIEW
