"""Diagnostics modal dialog."""

from __future__ import annotations

import flet as ft

from models.domain import DiagnosticsSnapshot
from ui.helpers import Colors, dialog_title


class DiagnosticsDialog:
    """Builds and manages the diagnostics AlertDialog."""

    def __init__(self, page: ft.Page) -> None:
        self._page = page
        self._dlg: ft.AlertDialog | None = None

    def show(self, snap: DiagnosticsSnapshot, formatted_text: str) -> None:
        status_color = Colors.status_color(snap.ollama_status)

        rows = []
        for line in formatted_text.splitlines():
            if line.strip():
                key, _, value = line.partition(":")
                rows.append(
                    ft.Row([
                        ft.Text(key.strip(), size=12, color=Colors.TEXT_LOW, width=140),
                        ft.Text(value.strip(), size=12, color=Colors.TEXT_HIGH2),
                    ])
                )
            else:
                rows.append(ft.Divider(color=Colors.BORDER_DIVIDER, height=8))

        self._dlg = ft.AlertDialog(
            modal=True,
            title=dialog_title(
                ft.Icons.HEALTH_AND_SAFETY,
                "System Diagnostics",
                icon_color=status_color,
                extra=ft.IconButton(icon=ft.Icons.CLOSE, on_click=self._close),
            ),
            content=ft.Container(
                content=ft.Column(rows, scroll=ft.ScrollMode.AUTO, spacing=2),
                width=400,
                height=320,
                padding=10,
            ),
            actions=[
                ft.TextButton(
                    "Close",
                    on_click=self._close,
                    style=ft.ButtonStyle(color=Colors.PRIMARY),
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.show_dialog(self._dlg)

    def _close(self, _e: ft.ControlEvent) -> None:
        if self._dlg:
            self._dlg.open = False
            self._dlg.update()
