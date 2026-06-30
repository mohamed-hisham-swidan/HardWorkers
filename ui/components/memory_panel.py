"""Sidebar memory panel component."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from models.domain import ChatMemoryFact, ChatSummary, UserFact
from ui.helpers import Colors, badge, btn_style, divider, section_header
from utils.logging_setup import get_logger

log = get_logger("ui.components.memory_panel")


class MemoryPanel(ft.Container):
    def __init__(self, on_add_fact: Callable[[str, str], None]) -> None:
        super().__init__()
        self._on_add = on_add_fact

        self._list = ft.ListView(expand=True, spacing=8)
        self._inp_key = ft.TextField(
            label="Fact key",
            height=44,
            border_radius=Colors.RADIUS_MD,
            filled=True,
            bgcolor=Colors.BG_SURFACE,
        )
        self._inp_val = ft.TextField(
            label="Fact value",
            height=44,
            border_radius=Colors.RADIUS_MD,
            filled=True,
            bgcolor=Colors.BG_SURFACE,
        )

        self.bgcolor = Colors.BG_PANEL
        self.border_radius = 0
        self.padding = 10
        self.width = 240
        self.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.MEMORY, color=Colors.PRIMARY, size=14),
                        ft.Text("MEMORY", weight=ft.FontWeight.BOLD, color=Colors.PRIMARY, size=12),
                    ],
                    spacing=4,
                ),
                divider(),
                ft.Container(content=self._list, expand=True),
                divider(),
                self._inp_key,
                ft.Container(height=2),
                self._inp_val,
                ft.Container(height=4),
                ft.ElevatedButton(
                    "Add Fact",
                    icon=ft.Icons.ADD,
                    on_click=self._handle_add,
                    expand=True,
                    style=btn_style(),
                ),
            ],
            expand=True,
            spacing=0,
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def retheme(self) -> None:
        """Re-apply current Colors palette to panel and input fields."""
        self.bgcolor = Colors.BG_PANEL
        self._inp_key.bgcolor = Colors.BG_SURFACE
        self._inp_val.bgcolor = Colors.BG_SURFACE
        try:
            self.update()
        except Exception:
            pass

    def safe_refresh(self, facts, summaries, chat_facts=None):
        """Thread-safe refresh — schedules on UI thread if needed."""
        import threading

        if threading.current_thread() is threading.main_thread():
            self.refresh(facts, summaries, chat_facts)
        else:
            if self.page:
                self.page.run_thread(lambda: self.refresh(facts, summaries, chat_facts))

    def refresh(
        self,
        facts: list[UserFact],
        summaries: list[ChatSummary],
        chat_facts: list[ChatMemoryFact] | None = None,
    ) -> None:
        try:
            self._list.controls.clear()

            if facts:
                self._list.controls.append(section_header("Global Memory", Colors.SUCCESS))
                for fact in facts:
                    self._list.controls.append(self._fact_card(fact))

            chat_facts = chat_facts or []
            if chat_facts:
                self._list.controls.append(divider())
                self._list.controls.append(section_header("Chat Memory", Colors.PRIMARY))
                for cf in chat_facts:
                    self._list.controls.append(self._chat_fact_card(cf))

            if summaries:
                self._list.controls.append(divider())
                self._list.controls.append(section_header("SUMMARIES", Colors.SECONDARY))
                for s in summaries:
                    self._list.controls.append(self._summary_card(s))

            if not any([facts, chat_facts, summaries]):
                self._list.controls.append(
                    ft.Text(
                        "No facts or summaries yet.\nAdd facts below to build memory.",
                        color=Colors.TEXT_MUTED2,
                        size=10,
                        italic=True,
                        text_align=ft.TextAlign.CENTER,
                    )
                )

            if self._list.page is not None and self.page is not None:
                try:
                    self._list.update()
                except Exception:
                    log.log(5, "Memory list update deferred")
        except Exception as exc:
            msg = str(exc)
            if "must be added to the page" in msg:
                log.debug("Memory panel not mounted yet: %s", exc)
            else:
                log.warning("Failed to update memory panel list: %s", exc)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handle_add(self, _e: ft.ControlEvent) -> None:
        key = (self._inp_key.value or "").strip()
        val = (self._inp_val.value or "").strip()
        if not key or not val:
            return
        self._on_add(key, val)
        self._inp_key.value = ""
        self._inp_val.value = ""
        if not self._inp_key.page:
            return
        try:
            self._inp_key.update()
            self._inp_val.update()
        except Exception as exc:
            log.warning("Failed to update memory panel inputs: %s", exc)

    @staticmethod
    def _fact_card(fact: UserFact) -> ft.Container:
        return ft.Container(
            bgcolor=Colors.BADGE_GLOBAL_FACT,
            padding=ft.Padding(left=10, right=10, top=7, bottom=7),
            border_radius=7,
            border=ft.BorderSide(1, Colors.BORDER_GLOBAL_FACT),
            content=ft.Column(
                [
                    ft.Row([
                        ft.Text(
                            f"\U0001f511 {fact.key}",
                            color=Colors.TEXT_CODE,
                            size=10,
                            weight=ft.FontWeight.BOLD,
                            expand=True,
                        ),
                        badge(str(fact.importance), bg_color=Colors.BADGE_MEMORY),
                    ]),
                    ft.Text(fact.value, color=Colors.TEXT_MEDIUM, size=10),
                ],
                spacing=3,
            ),
        )

    @staticmethod
    def _chat_fact_card(fact: ChatMemoryFact) -> ft.Container:
        return ft.Container(
            bgcolor=Colors.BADGE_CHAT_FACT,
            padding=ft.Padding(left=10, right=10, top=7, bottom=7),
            border_radius=7,
            border=ft.BorderSide(1, Colors.BORDER_CHAT_FACT),
            content=ft.Column(
                [
                    ft.Row([
                        ft.Text(
                            f"\U0001f511 {fact.key}",
                            color=Colors.TEXT_CODE,
                            size=10,
                            weight=ft.FontWeight.BOLD,
                            expand=True,
                        ),
                        badge(str(fact.importance), bg_color=Colors.BADGE_CATEGORY),
                    ]),
                    ft.Text(fact.value, color=Colors.TEXT_MEDIUM, size=10),
                ],
                spacing=3,
            ),
        )

    @staticmethod
    def _summary_card(summary: ChatSummary) -> ft.Container:
        return ft.Container(
            bgcolor=Colors.BADGE_SUMMARY,
            padding=ft.Padding(left=10, right=10, top=7, bottom=7),
            border_radius=7,
            content=ft.Text(
                f"\U0001f4cc {summary.summary}",
                color=Colors.TEXT_HIGH2,
                size=9,
                max_lines=4,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        )
