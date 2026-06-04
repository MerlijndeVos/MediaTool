"""JavaScript-callable API exposed to the React UI inside pywebview."""

from __future__ import annotations

from typing import Any


class DesktopApi:
    """Native file/folder dialogs for the desktop shell."""

    def pick_folder(self) -> str | None:
        import webview

        window = webview.active_window()
        if window is None:
            return None
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        return str(result[0])

    def pick_files(self, multiple: bool = False) -> list[str]:
        import webview

        window = webview.active_window()
        if window is None:
            return []
        result = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=bool(multiple),
        )
        if not result:
            return []
        return [str(path) for path in result]

    def pick_save_file(self, suggested_filename: str = "") -> str | None:
        import webview

        window = webview.active_window()
        if window is None:
            return None
        kwargs: dict[str, Any] = {}
        if suggested_filename:
            kwargs["save_filename"] = suggested_filename
        result = window.create_file_dialog(webview.SAVE_DIALOG, **kwargs)
        if not result:
            return None
        return str(result[0])
