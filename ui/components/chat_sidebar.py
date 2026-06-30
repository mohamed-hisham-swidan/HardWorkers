"""Chat sidebar — list, create, rename, pin, delete chat sessions.

Modern ChatGPT-inspired design with date grouping, context menus,
hover effects, and smooth animations.
"""

from __future__ import annotations

import datetime

import flet as ft

from models.domain import ChatSession
from ui.helpers import Colors
from utils.logging_setup import get_logger

log = get_logger("ui.chat_sidebar")

_GROUP_LABELS: dict[str, str] = {}


def _parse_dt(raw: str | datetime.datetime) -> datetime.datetime | None:
    if isinstance(raw, datetime.datetime):
        return raw
    if not raw:
        return None
    try:
        return datetime.datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _get_group_label(chat: ChatSession) -> str:
    if not chat.updated_at:
        return "Chats"
    d = _parse_dt(chat.updated_at)
    if not isinstance(d, datetime.datetime):
        return "Older"
    now = datetime.datetime.now()
    if d.date() == now.date():
        return "Today"
    yesterday = now - datetime.timedelta(days=1)
    if d.date() == yesterday.date():
        return "Yesterday"
    week_ago = now - datetime.timedelta(days=7)
    if d.date() >= week_ago.date():
        return "This Week"
    return "Older"


class ChatSidebar(ft.Container):
    """Sidebar listing chats for the active workspace with modern UX."""

    def __init__(
        self,
        on_chat_select=None,
        on_chat_create=None,
        on_chat_delete=None,
        on_chat_pin=None,
        on_chat_rename=None,
    ) -> None:
        self._on_chat_select = on_chat_select
        self._on_chat_create = on_chat_create
        self._on_chat_delete = on_chat_delete
        self._on_chat_pin = on_chat_pin
        self._on_chat_rename = on_chat_rename

        self._active_id: int | None = None
        self._last_chats: list[ChatSession] = []
        self._editing_id: int | None = None

        self._search_field = ft.TextField(
            hint_text="Search chats\u2026",
            height=34,
            text_size=12,
            border_radius=8,
            filled=True,
            bgcolor=Colors.BG_USER_MSG,
            border_color=Colors.BORDER_INPUT,
            focused_border_color=Colors.PRIMARY,
            prefix_icon=ft.Icons.SEARCH,
            content_padding=ft.Padding(left=10, right=10, top=6, bottom=6),
            on_change=self._on_search,
        )

        self._list = ft.ListView(spacing=2, auto_scroll=False, expand=True)

        header = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row(
                    spacing=6,
                    controls=[
                        ft.Icon(ft.Icons.CHAT, size=16, color=Colors.PRIMARY),
                        ft.Text(
                            "Chats",
                            size=13,
                            weight=ft.FontWeight.BOLD,
                            color=Colors.TEXT_HIGH,
                        ),
                    ],
                ),
                ft.Container(
                    content=ft.IconButton(
                        icon=ft.Icons.ADD,
                        icon_size=18,
                        icon_color=Colors.TEXT_HIGH,
                        tooltip="New chat",
                        on_click=self._on_create_click,
                        style=ft.ButtonStyle(
                            padding=4,
                            bgcolor={ft.ControlState.HOVERED: Colors.BG_HOVER},
                        ),
                    ),
                    border_radius=6,
                ),
            ],
        )

        super().__init__(
            width=240,
            bgcolor=Colors.BG_PANEL,
            border_radius=0,
            padding=ft.Padding(left=0, right=0, top=8, bottom=0),
            content=ft.Column(
                spacing=0,
                controls=[
                    ft.Container(
                        content=header,
                        padding=ft.Padding(left=12, right=8, top=0, bottom=6),
                    ),
                    ft.Container(
                        content=self._search_field,
                        padding=ft.Padding(left=8, right=8, top=0, bottom=6),
                    ),
                    ft.Divider(height=1, color=Colors.BORDER_DIVIDER),
                    self._list,
                ],
            ),
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def retheme(self) -> None:
        """Re-apply current Colors palette to all widgets."""
        self.bgcolor = Colors.BG_PANEL
        self._search_field.bgcolor = Colors.BG_USER_MSG
        self._search_field.border_color = Colors.BORDER_INPUT
        self._search_field.focused_border_color = Colors.PRIMARY
        for item in self.content.controls:
            if isinstance(item, ft.Divider):
                item.color = Colors.BORDER_DIVIDER
        self._rebuild_list()
        try:
            self.update()
        except Exception:
            pass

    def refresh(self, chats: list[ChatSession], active_chat_id: int | None) -> None:
        self._active_id = active_chat_id
        self._last_chats = chats
        self._editing_id = None
        self._rebuild_list()

    # ── Internal ───────────────────────────────────────────────────────────

    def _on_search(self, _e: ft.ControlEvent) -> None:
        self._rebuild_list()

    def _rebuild_list(self) -> None:
        self._list.controls.clear()
        query = (self._search_field.value or "").strip().lower()

        if not self._last_chats:
            self._list.controls.append(
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Icon(ft.Icons.CHAT_OUTLINED, size=32, color=Colors.TEXT_MUTED2),
                            ft.Text(
                                "No chats yet",
                                color=Colors.TEXT_MUTED2,
                                size=12,
                            ),
                            ft.Text(
                                "Create one to begin.",
                                color=Colors.TEXT_MUTED2,
                                size=11,
                                italic=True,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=4,
                    ),
                    alignment=ft.Alignment.CENTER,
                    padding=ft.Padding(left=20, right=20, top=20, bottom=20),
                )
            )
        else:
            filtered = [c for c in self._last_chats if not query or query in c.name.lower()]
            if not filtered:
                self._list.controls.append(
                    ft.Container(
                        ft.Text("No matching chats", color=Colors.TEXT_MUTED2, size=12),
                        padding=ft.Padding(left=16, right=16, top=16, bottom=16),
                    )
                )
            else:
                pinned = [c for c in filtered if c.pinned]
                unpinned = [c for c in filtered if not c.pinned]

                if pinned:
                    self._list.controls.append(
                        ft.Container(
                            padding=ft.Padding(left=12, top=8, bottom=4, right=12),
                            content=ft.Row(
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Text(
                                        "PINNED",
                                        size=10,
                                        color=Colors.PRIMARY,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Container(
                                        expand=True,
                                        height=1,
                                        bgcolor=Colors.with_opacity(Colors.PRIMARY, 0.2),
                                    ),
                                ],
                            ),
                        )
                    )
                    for chat in pinned:
                        self._list.controls.append(self._build_chat_row(chat))

                groups: dict[str, list[ChatSession]] = {}
                for chat in unpinned:
                    label = _get_group_label(chat)
                    groups.setdefault(label, []).append(chat)

                group_order = ["Today", "Yesterday", "This Week", "Older", "Chats"]
                for label in group_order:
                    if label not in groups:
                        continue
                    self._list.controls.append(
                        ft.Container(
                            padding=ft.Padding(left=12, top=8, bottom=4, right=12),
                            content=ft.Row(
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Text(
                                        label.upper(),
                                        size=10,
                                        color=Colors.TEXT_MUTED2,
                                        weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Container(
                                        expand=True,
                                        height=1,
                                        bgcolor=Colors.BORDER_DIVIDER,
                                    ),
                                ],
                            ),
                        )
                    )
                    for chat in groups[label]:
                        self._list.controls.append(self._build_chat_row(chat))

        try:
            self._list.update()
        except Exception as exc:
            log.warning("Failed to update chat sidebar list: %s", exc)

    def _build_chat_row(self, chat: ChatSession) -> ft.Container:
        is_active = chat.id == self._active_id
        is_pinned = chat.pinned
        is_editing = chat.id == self._editing_id
        cid = chat.id

        if is_editing:
            edit_field = ft.TextField(
                value=chat.name,
                border_radius=6,
                height=34,
                text_size=13,
                filled=True,
                bgcolor=Colors.BG_USER_MSG,
                border_color=Colors.BORDER_FOCUS,
                focused_border_color=Colors.BORDER_FOCUS,
                content_padding=ft.Padding(left=8, right=8, top=4, bottom=4),
            )

            def commit_rename(_, _cid=cid, field=edit_field) -> None:
                self._editing_id = None
                new_name = (field.value or "").strip()
                if new_name and self._on_chat_rename:
                    self._on_chat_rename(_cid, new_name)

            edit_field.on_submit = commit_rename
            edit_field.on_blur = commit_rename

            return ft.Container(
                bgcolor=Colors.BG_USER_MSG if is_active else "transparent",
                border_radius=8,
                padding=ft.Padding(left=8, right=8, top=2, bottom=2),
                content=edit_field,
            )

        menu_btn = ft.PopupMenuButton(
            icon=ft.Icons.MORE_VERT,
            icon_size=16,
            icon_color=Colors.TEXT_MUTED2,
            tooltip="Chat options",
            style=ft.ButtonStyle(padding=2),
            items=[
                ft.PopupMenuItem(
                    icon=ft.Icons.PUSH_PIN if is_pinned else ft.Icons.PUSH_PIN_OUTLINED,
                    content="Unpin" if is_pinned else "Pin",
                    on_click=lambda _, _cid=cid: self._on_pin(_cid),
                ),
                ft.PopupMenuItem(
                    icon=ft.Icons.EDIT_OUTLINED,
                    content="Rename",
                    on_click=lambda _, _cid=cid: self._start_rename(_cid),
                ),
                ft.PopupMenuItem(),
                ft.PopupMenuItem(
                    icon=ft.Icons.DELETE_OUTLINE,
                    content="Delete",
                    on_click=lambda _, _cid=cid: self._confirm_delete(_cid),
                ),
            ],
        )

        row = ft.Container(
            bgcolor=Colors.BG_HOVER if is_active else "transparent",
            border_radius=8,
            padding=ft.Padding(left=0, right=4, top=1, bottom=1),
            ink=True,
            border=ft.BorderSide(
                1,
                Colors.with_opacity(Colors.PRIMARY, 0.15) if is_active else "transparent",
            ),
            animate=ft.Animation(100, "ease_out"),
            content=ft.Row(
                spacing=0,
                controls=[
                    ft.Container(
                        width=4,
                        height=28,
                        bgcolor=Colors.PRIMARY if is_active else "transparent",
                        border_radius=ft.BorderRadius.only(top_right=2, bottom_right=2),
                        animate=ft.Animation(150, "ease_in_out"),
                    ),
                    ft.Container(
                        expand=True,
                        content=ft.Row(
                            spacing=2,
                            controls=[
                                ft.Icon(
                                    ft.Icons.PUSH_PIN if is_pinned else ft.Icons.CHAT_OUTLINED,
                                    size=14,
                                    color=Colors.PRIMARY if is_pinned else Colors.TEXT_MUTED2,
                                ),
                                ft.Container(
                                    expand=True,
                                    content=ft.Text(
                                        chat.name,
                                        size=13,
                                        weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.NORMAL,
                                        color=Colors.TEXT_HIGH if is_active else Colors.TEXT_MUTED,
                                        no_wrap=True,
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                    on_click=lambda _, _cid=cid: self._on_select(_cid),
                                ),
                                menu_btn,
                            ],
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        ),
                        padding=ft.Padding(left=4, right=0, top=0, bottom=0),
                    ),
                ],
            ),
        )

        return row

    def _confirm_delete(self, chat_id: int) -> None:
        def _on_delete(e):
            nonlocal dlg
            if dlg:
                dlg.open = False
                try:
                    dlg.update()
                except Exception:
                    log.debug("Delete dialog close ignored")
            if self._on_chat_delete:
                self._on_chat_delete(chat_id)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Delete Chat", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Text("Are you sure you want to delete this chat? This action cannot be undone.", size=13),
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self._close_dialog(dlg)),
                ft.ElevatedButton("Delete", color=Colors.TEXT_HIGH, bgcolor=Colors.ERROR, on_click=_on_delete),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    @staticmethod
    def _close_dialog(dlg: ft.AlertDialog) -> None:
        dlg.open = False
        try:
            dlg.update()
        except Exception:
            log.debug("Dialog close ignored")

    def _start_rename(self, chat_id: int) -> None:
        self._editing_id = chat_id
        self._rebuild_list()

    def _on_select(self, chat_id: int) -> None:
        if self._on_chat_select:
            self._on_chat_select(chat_id)

    def _on_create_click(self, _e: ft.ControlEvent) -> None:
        if self._on_chat_create:
            self._on_chat_create()

    def _on_pin(self, chat_id: int) -> None:
        if self._on_chat_pin:
            self._on_chat_pin(chat_id)

    def _on_delete(self, chat_id: int) -> None:
        if self._on_chat_delete:
            self._on_chat_delete(chat_id)
