# Toolbox mod market

A public list of mods people can browse, search and install from **Settings → Mods → Browse** in
the app, or on the website. There is no server: the whole market is [`index.json`](index.json) in
this folder, and each entry points at a git repository and an **exact commit**.

> **Listed is not reviewed.** A mod is code that runs with the same access as Toolbox. The
> project does not check the mods in this list, and being listed says nothing about whether one
> is safe. The app shows the real code, the commit hash and the access the mod declares before
> anything is installed, and warns when the code disagrees with its listing.

## List your mod

1. Put your mod in a public git repository (see [MODDING.md](../MODDING.md)). It can live in the
   repo root or in a folder of a bigger repo.
2. Tag or note the commit you want people to get. Use the **full 40-character hash**.
3. Open a pull request that adds an entry to `index.json`:

   ```json
   {
     "id": "my-mod",
     "name": "My Mod",
     "description": "One sentence on what it does.",
     "author": "Your name",
     "version": "1.0.0",
     "api_version": 1,
     "repo": "https://github.com/you/my-mod",
     "path": "",
     "commit": "0123456789abcdef0123456789abcdef01234567",
     "tags": ["subtitles"],
     "license": "MIT",
     "homepage": "https://github.com/you/my-mod",
     "permissions": { "network": false, "writes_files": true, "runs_programs": false }
   }
   ```

   | Field | |
   | --- | --- |
   | `id`, `name` | required. `id` must match the `id` in your `mod.toml`, and cannot be a built-in id |
   | `repo`, `commit` | required. A plain `https://` repository address and the full commit hash |
   | `path` | folder inside the repo that holds `mod.toml`; leave out or `""` for the repo root |
   | `description`, `author`, `version`, `tags`, `license`, `homepage` | shown in the list; `homepage` must be https |
   | `permissions` | what you declare in `mod.toml`. Be honest: the app compares it with the real manifest |

4. `python -m unittest tests.test_market` checks the file. A PR that breaks the format fails it.

To release a new version, open a PR that changes `version` and `commit`. Nobody gets an update
until they review it: the app shows what changed and asks first.

## How the app uses it

- **Browse** loads the index (cached for 10 minutes) and filters it as you type.
- **Install** downloads exactly the listed commit, checks that the `id` in the code matches the
  listing, and shows the trust prompt. Nothing runs until you turn the mod on.
- To use another list, set `TOOLBOX_MARKET_URL` to its address (or a `file:///` path).

## The website page

[`index.html`](index.html) is a self-contained, searchable page that reads `index.json` from the
same place. Publish the two files together (for example on GitHub Pages or toolbox.murly.nl), or
edit `INDEX_URL` at the top of its script to read the raw file from GitHub.
