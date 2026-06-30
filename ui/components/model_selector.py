"""Styled dropdown for selecting the active model with hover effects."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from ui.helpers import Colors
from utils.logging_setup import get_logger

log = get_logger("ui.components.model_selector")


class ModelSelector(ft.Dropdown):
    """Model selection dropdown with custom styling."""

    def __init__(
        self,
        models: list[str],
        on_change: Callable[[str], None],
    ) -> None:
        super().__init__(
            options=[ft.dropdown.Option(m) for m in models],
            value=models[0] if models else None,
            width=180,
            height=36,
            border_radius=Colors.RADIUS_MD,
            filled=True,
            bgcolor=Colors.BG_SURFACE,
            hint_text="Select model\u2026",
            text_size=12,
            content_padding=ft.Padding(left=8, right=8, top=4, bottom=4),
            leading_icon=ft.Icons.MEMORY,
        )
        self._callback = on_change
        self.on_change = self._handle_change

    def _handle_change(self, _e: ft.ControlEvent) -> None:
        if self.value:
            self._callback(self.value)

    def update_models(self, models: list[str], active: str | None = None) -> None:
        self.options = [ft.dropdown.Option(m) for m in models]
        old_on_change = self.on_change
        self.on_change = None
        if active and active in models:
            self.value = active
        elif models:
            self.value = models[0]
        self.on_change = old_on_change
        try:
            self.update()
        except Exception as exc:
            log.warning("Failed to update model selector: %s", exc)
