"""MarkdownText — streaming-aware markdown renderer using ft.Markdown."""

from __future__ import annotations

import flet as ft


class MarkdownText(ft.Column):
    """Renders markdown content with syntax highlighting and code copy buttons.

    Supports streaming via ``append_chunk()`` — content is re-rendered
    on each flush (throttled externally).
    """

    def __init__(self, initial: str = "", selectable: bool = True) -> None:
        super().__init__(spacing=0)
        self._raw = initial
        self._md = ft.Markdown(
            value=initial or " ",
            selectable=selectable,
            extension_set="gitHubFlavored",
            code_theme="atom-one-dark",
            auto_follow_links=True,
            on_tap_link=lambda e: self.page.launch_url(e.data) if self.page else None,
        )
        self.controls = [self._md]

    @property
    def value(self) -> str:
        return self._raw

    @value.setter
    def value(self, text: str) -> None:
        self._raw = text
        self._md.value = text or " "
        try:
            self._md.update()
        except Exception:
            pass

    def append_chunk(self, chunk: str) -> None:
        self._raw += chunk
        self._md.value = self._raw
