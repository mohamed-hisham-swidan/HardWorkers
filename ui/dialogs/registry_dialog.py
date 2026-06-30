"""Model Manager — dedicated UI for browsing, managing, and downloading models.

Provides:
  - Full list of registered models (Ollama + API) with type badges
  - Model version / tag display
  - Clone (Ollama), Edit (API), Delete, Test Connection
  - Download progress indicator for Ollama models
  - Modern card-based layout with hover effects
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import flet as ft

from models.domain import ModelRegistryEntry
from services.ai.model_creator import ModelCreatorService
from services.ai.model_manager import ModelManager
from ui.helpers import Colors, badge, btn_style
from utils.logging_setup import get_logger

if TYPE_CHECKING:
    from ui.dialogs.model_creator_dialog import ModelCreatorDialog

log = get_logger("ui.dialogs.registry_dialog")


class RegistryDialog:
    """Model Manager — browse, manage, clone, test, and delete models."""

    def __init__(
        self,
        page: ft.Page,
        creator: ModelCreatorService,
        model_manager: ModelManager,
        creator_dlg: ModelCreatorDialog,
        pool: ThreadPoolExecutor,
        on_models_changed: Callable[[], None],
    ) -> None:
        self._page = page
        self._creator = creator
        self._mm = model_manager
        self._creator_dlg = creator_dlg
        self._pool = pool
        self._notify = on_models_changed
        self._dlg: ft.AlertDialog | None = None
        self._card_cache: dict[int, ft.Container] = {}
        self._reg_list = ft.ListView(expand=True, spacing=6)

    # ------------------------------------------------------------------
    # Show / hide
    # ------------------------------------------------------------------

    def show(self) -> None:
        self._refresh_registry_list()

        header = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.DATASET, color=Colors.PRIMARY, size=22),
                    ft.Text("Model Manager", size=20, weight=ft.FontWeight.BOLD),
                    ft.Container(expand=True),
                    ft.IconButton(icon=ft.Icons.CLOSE, on_click=self._close),
                    ft.ElevatedButton(
                        "Add Model",
                        icon=ft.Icons.ADD,
                        on_click=self._on_add_model,
                        style=btn_style(Colors.PRIMARY),
                        height=36,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(bottom=8),
        )

        self._dlg = ft.AlertDialog(
            modal=True,
            title=header,
            content=ft.Container(
                content=self._reg_list,
                width=720,
                height=560,
                padding=ft.Padding(left=8, right=8, top=8, bottom=8),
            ),
            actions=[
                ft.TextButton("Close", on_click=self._close, style=ft.ButtonStyle(color=Colors.TEXT_LOW)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.show_dialog(self._dlg)

    def _on_add_model(self, _e: ft.ControlEvent) -> None:
        self._creator_dlg.show()

    def _close(self, _e: ft.ControlEvent | None = None) -> None:
        if self._dlg:
            self._dlg.open = False
            self._dlg.update()

    def close(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Registry list
    # ------------------------------------------------------------------

    def _invalidate_card(self, entry_id: int) -> None:
        self._card_cache.pop(entry_id, None)

    def _refresh_registry_list(self) -> None:
        entries = self._creator.get_registered_models()
        current_ids = {e.id for e in entries if e.id is not None}

        for eid in list(self._card_cache.keys()):
            if eid not in current_ids:
                card_item = self._card_cache.pop(eid)
                if card_item in self._reg_list.controls:
                    self._reg_list.controls.remove(card_item)

        if not entries:
            self._reg_list.controls.clear()
            self._reg_list.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.DATASET_OUTLINED, size=48, color=Colors.TEXT_MUTED2),
                            ft.Text("No models registered", color=Colors.TEXT_MUTED2, size=14),
                            ft.Text(
                                "Click 'Add Model' above to register one.",
                                color=Colors.TEXT_MUTED2,
                                size=12,
                                italic=True,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=8,
                    ),
                    alignment=ft.Alignment.CENTER,
                    expand=True,
                )
            )
            self._card_cache.clear()
        else:
            for entry in entries:
                eid = entry.id
                if eid is not None and eid in self._card_cache:
                    continue
                card_item = self._registry_card(entry)
                if eid is not None:
                    self._card_cache[eid] = card_item
                self._reg_list.controls.append(card_item)

            ordered = []
            for entry in entries:
                eid = entry.id
                if eid is not None and eid in self._card_cache:
                    ordered.append(self._card_cache[eid])
            if ordered:
                self._reg_list.controls.clear()
                self._reg_list.controls.extend(ordered)

        try:
            if self._reg_list.page is not None:
                self._reg_list.update()
        except Exception as exc:
            log.warning("Failed to update registry list: %s", exc)

    def _registry_card(self, entry: ModelRegistryEntry) -> ft.Container:
        is_ollama = entry.is_ollama
        type_label = "Ollama" if is_ollama else "API"

        version_str = ""
        if is_ollama and entry.base_model:
            parts = entry.base_model.split(":")
            version_str = f"v{parts[1]}" if len(parts) > 1 else "latest"

        def on_delete(_e, eid=entry.id, ename=entry.name) -> None:
            if eid is None:
                return
            self._confirm_delete(eid, ename)

        def on_clone(_e, ename=entry.name) -> None:
            if is_ollama:
                self._pool.submit(self._clone_model_bg, ename)

        def on_test(_e) -> None:
            self._pool.submit(self._test_connection_bg, entry)

        def on_edit(_e, eid=entry.id) -> None:
            self._invalidate_card(eid)
            self._creator_dlg.edit_model(entry)

        actions: list[ft.Control] = []

        if is_ollama:
            actions.append(
                ft.IconButton(
                    icon=ft.Icons.COPY,
                    icon_color=Colors.TEXT_LOW,
                    icon_size=16,
                    tooltip="Clone model",
                    on_click=on_clone,
                    style=ft.ButtonStyle(padding=4),
                )
            )
        else:
            actions.extend([
                ft.IconButton(
                    icon=ft.Icons.PLAY_ARROW,
                    icon_color=Colors.SUCCESS,
                    icon_size=16,
                    tooltip="Test connection",
                    on_click=on_test,
                    style=ft.ButtonStyle(padding=4),
                ),
                ft.IconButton(
                    icon=ft.Icons.MODE_EDIT_OUTLINE,
                    icon_color=Colors.PRIMARY,
                    icon_size=16,
                    tooltip="Edit",
                    on_click=on_edit,
                    style=ft.ButtonStyle(padding=4),
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color=Colors.ERROR,
                    icon_size=16,
                    tooltip="Delete",
                    on_click=on_delete,
                    style=ft.ButtonStyle(padding=4),
                ),
            ])

        badges = [badge(type_label, bg_color=Colors.SUCCESS if is_ollama else Colors.SECONDARY)]
        badges.append(badge(str(entry.category), bg_color=Colors.BADGE_CATEGORY))
        badges.append(badge(str(entry.memory_mode), bg_color=Colors.BADGE_MEMORY))
        if version_str:
            badges.append(badge(version_str, bg_color=Colors.BG_SURFACE))

        second_row = [
            ft.Container(
                content=ft.Text(
                    entry.description or entry.api_url or entry.base_model or "\u2014",
                    color=Colors.TEXT_MUTED,
                    size=11,
                    no_wrap=True,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                width=400,
            )
        ]
        if not is_ollama:
            second_row.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.CLOUD, size=12, color=Colors.TEXT_MUTED2),
                            ft.Text("API", size=10, color=Colors.TEXT_MUTED2),
                        ],
                        spacing=2,
                    ),
                    padding=ft.Padding(left=4, right=4, top=0, bottom=0),
                )
            )

        return ft.Container(
            bgcolor=Colors.BG_SURFACE2,
            padding=ft.Padding(left=12, right=12, top=10, bottom=10),
            border_radius=Colors.RADIUS_MD,
            border=ft.BorderSide(1, Colors.BORDER_CARD),
            ink=True,
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Row(badges, spacing=6, wrap=True),
                            ft.Row(second_row, spacing=8),
                        ],
                        expand=True,
                        spacing=3,
                    ),
                    ft.Container(
                        content=ft.Row(actions, spacing=2),
                        padding=ft.Padding(left=4),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    # ------------------------------------------------------------------
    # Delete flow
    # ------------------------------------------------------------------

    def _confirm_delete(self, entry_id: int, entry_name: str) -> None:
        def _do_delete(_e: ft.ControlEvent) -> None:
            dlg.open = False
            dlg.update()
            self._pool.submit(self._delete_model_bg, entry_id, entry_name)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.WARNING_AMBER, color=Colors.WARNING, size=22),
                            ft.Text("Delete Model", color=Colors.ERROR),
                        ],
                        spacing=8,
                    ),
                    ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda e: setattr(dlg, "open", False) or dlg.update()),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            content=ft.Text(f"Are you sure you want to delete '{entry_name}'?\nThis action cannot be undone."),
            actions=[
                ft.TextButton("Cancel", on_click=lambda e: setattr(dlg, "open", False) or dlg.update()),
                ft.TextButton("Delete", on_click=_do_delete, style=ft.ButtonStyle(color=Colors.ERROR)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.show_dialog(dlg)

    def _delete_model_bg(self, model_id: int, name: str) -> None:
        ok, msg = self._creator.unregister_model(model_id)
        if ok:
            self._mm.invalidate_cache(name)
            self._page.run_thread(lambda: (self._refresh_registry_list(), self._notify()))

    # ------------------------------------------------------------------
    # Clone flow
    # ------------------------------------------------------------------

    def _clone_model_bg(self, source: str) -> None:
        new_name = f"{source}-clone"
        ok, msg = self._creator.clone_ollama_model(source, new_name)
        if ok:
            self._page.run_thread(lambda: (self._refresh_registry_list(), self._notify()))
        else:
            self._page.run_thread(lambda: self._show_toast(f"Clone failed: {msg}", Colors.ERROR))

    def _test_connection_bg(self, entry: ModelRegistryEntry) -> None:
        ok, msg, _discovered = self._creator.test_api_connection(
            entry.api_url,
            entry.api_key or "",
            entry.base_model,
            entry.api_password or "",
        )
        self._page.run_thread(lambda: self._show_toast(msg, Colors.SUCCESS if ok else Colors.ERROR))

    def _show_toast(self, message: str, color: str) -> None:
        try:
            snack = ft.SnackBar(
                ft.Text(message, color=Colors.TEXT_HIGH, size=13),
                bgcolor=color,
                duration=4000,
                open=True,
                behavior=ft.SnackBarBehavior.FLOATING,
            )
            self._page.overlay.append(snack)
            snack.update()
        except Exception as exc:
            log.warning("Failed to show toast: %s", exc)
