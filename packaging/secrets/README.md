# GitHub token for in-app updates

This folder is used at **build time** only. Do not commit `github_token`.

For a **private** repository, release CI should set the repository secret `MEDIA_TOOL_UPDATE_TOKEN` to a fine-grained or classic PAT with **read-only** access to this repo’s contents. The release workflow writes that value here before PyInstaller runs so installed apps can check and download updates.

For **local** development or manual installs, use one of:

- Environment variable `MEDIA_TOOL_GITHUB_TOKEN`
- File `%LOCALAPPDATA%\MediaTool\github_token` (Windows) or `~/.local/share/MediaTool/github_token` (Linux), containing the token on a single line

The token is embedded in distributed installers (extractable from the binary). Use a dedicated read-only token limited to this repository.
