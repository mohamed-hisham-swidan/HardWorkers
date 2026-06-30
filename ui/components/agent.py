"""Agent UX components — status badge, info panel, activity feed."""

from __future__ import annotations

import time
from enum import StrEnum

import flet as ft

from ui.helpers import Colors

# ── Agent Status Enum ─────────────────────────────────────────────────────────


class AgentStatus(StrEnum):
    IDLE = "Idle"
    THINKING = "Thinking…"
    STREAMING = "Generating…"
    COMPLETED = "Completed"
    ERROR = "Error"
    CANCELLED = "Cancelled"


_STATUS_STYLES: dict[AgentStatus, tuple[str, str]] = {
    AgentStatus.IDLE: (Colors.TEXT_MUTED, Colors.BG_SURFACE2),
    AgentStatus.THINKING: (Colors.WARNING, Colors.STATUS_THINKING),
    AgentStatus.STREAMING: (Colors.PRIMARY, Colors.STATUS_STREAMING),
    AgentStatus.COMPLETED: (Colors.SUCCESS, Colors.STATUS_COMPLETED),
    AgentStatus.ERROR: (Colors.ERROR, Colors.STATUS_ERROR),
    AgentStatus.CANCELLED: (Colors.WARNING, Colors.STATUS_CANCELLED),
}


# ── Agent Status Badge ───────────────────────────────────────────────────────


class AgentStatusBadge(ft.Container):
    """Color-coded agent state badge shown in the toolbar."""

    def __init__(self) -> None:
        self._current_status = AgentStatus.IDLE
        self._label = ft.Text(
            AgentStatus.IDLE,
            size=11,
            weight=ft.FontWeight.BOLD,
            color=_STATUS_STYLES[AgentStatus.IDLE][0],
        )
        super().__init__(
            content=self._label,
            padding=ft.Padding(left=8, right=8, top=3, bottom=3),
            border_radius=Colors.RADIUS_SM,
            bgcolor=_STATUS_STYLES[AgentStatus.IDLE][1],
        )

    def set_status(self, status: AgentStatus) -> None:
        self._current_status = status
        style = _STATUS_STYLES.get(status, _STATUS_STYLES[AgentStatus.IDLE])
        self._label.value = status.value
        self._label.color = style[0]
        self.bgcolor = style[1]
        try:
            self.update()
        except Exception:
            pass

    def retheme(self) -> None:
        """Re-apply badge colors from current palette."""
        style = _STATUS_STYLES.get(self._current_status, _STATUS_STYLES[AgentStatus.IDLE])
        self._label.color = style[0]
        self.bgcolor = style[1]
        try:
            self.update()
        except Exception:
            pass


# ── Agent Info Panel ─────────────────────────────────────────────────────────


class AgentInfoPanel(ft.Container):
    """Collapsible info panel showing model, tokens, elapsed, memory."""

    def __init__(self) -> None:
        self._model_text = ft.Text("—", size=11, color=Colors.TEXT_MUTED)
        self._tokens_text = ft.Text("—", size=11, color=Colors.TEXT_MUTED)
        self._elapsed_text = ft.Text("—", size=11, color=Colors.TEXT_MUTED)
        self._memory_text = ft.Text("—", size=11, color=Colors.TEXT_MUTED)
        self._start_time: float | None = None
        self._timer_active = False

        self._body = ft.Column(
            spacing=2,
            controls=[
                ft.Row(
                    [ft.Text("Model", size=10, color=Colors.TEXT_LOW, weight=ft.FontWeight.BOLD), self._model_text],
                    spacing=8,
                ),
                ft.Row(
                    [ft.Text("Tokens", size=10, color=Colors.TEXT_LOW, weight=ft.FontWeight.BOLD), self._tokens_text],
                    spacing=8,
                ),
                ft.Row(
                    [ft.Text("Elapsed", size=10, color=Colors.TEXT_LOW, weight=ft.FontWeight.BOLD), self._elapsed_text],
                    spacing=8,
                ),
                ft.Row(
                    [ft.Text("Memory", size=10, color=Colors.TEXT_LOW, weight=ft.FontWeight.BOLD), self._memory_text],
                    spacing=8,
                ),
            ],
        )

        super().__init__(
            content=self._body,
            padding=ft.Padding(left=10, right=10, top=8, bottom=8),
            border_radius=Colors.RADIUS_MD,
            bgcolor=Colors.BG_SURFACE2,
            border=ft.border.BorderSide(1, Colors.BORDER_DIVIDER),
            visible=False,
        )

    def show(self, model: str, memory_facts: int = 0) -> None:
        self._model_text.value = model
        self._memory_text.value = f"{memory_facts} facts"
        self._start_time = time.time()
        self._timer_active = True
        self.visible = True
        try:
            self.update()
        except Exception:
            pass

    def retheme(self) -> None:
        """Re-apply current Colors palette to info panel."""
        self.bgcolor = Colors.BG_SURFACE2
        self.border = ft.border.BorderSide(1, Colors.BORDER_DIVIDER)
        self._model_text.color = Colors.TEXT_MUTED
        self._tokens_text.color = Colors.TEXT_MUTED
        self._elapsed_text.color = Colors.TEXT_MUTED
        self._memory_text.color = Colors.TEXT_MUTED
        try:
            self.update()
        except Exception:
            pass

    def hide(self) -> None:
        self._timer_active = False
        self.visible = False
        try:
            self.update()
        except Exception:
            pass

    def update_tokens(self, prompt: int = 0, output: int = 0) -> None:
        self._tokens_text.value = f"{prompt} in / {output} out"
        try:
            self._tokens_text.update()
        except Exception:
            pass

    def update_elapsed(self) -> None:
        if self._start_time is None or not self._timer_active:
            return
        elapsed = time.time() - self._start_time
        self._elapsed_text.value = f"{elapsed:.1f}s"
        try:
            self._elapsed_text.update()
        except Exception:
            pass

    def set_memory(self, count: int) -> None:
        self._memory_text.value = f"{count} facts"
        try:
            self._memory_text.update()
        except Exception:
            pass


# ── Agent Activity Feed ──────────────────────────────────────────────────────


class AgentActivityFeed(ft.Column):
    """Scrollable event log of agent lifecycle events."""

    def __init__(self, max_events: int = 50) -> None:
        super().__init__(spacing=2, scroll=ft.ScrollMode.AUTO, height=120)
        self._max_events = max_events
        self._header = ft.Container(
            content=ft.Text("Activity", size=10, color=Colors.TEXT_LOW, weight=ft.FontWeight.BOLD),
            padding=ft.Padding(left=8, right=8, top=4, bottom=2),
        )
        self.controls = [self._header]

    def add_event(self, message: str, color: str = Colors.TEXT_MUTED) -> None:
        entry = ft.Text(f"▸ {message}", size=11, color=color, no_wrap=False)
        self.controls.append(entry)
        if len(self.controls) > self._max_events + 1:
            self.controls = [self.controls[0]] + self.controls[-(self._max_events) :]
        try:
            self.update()
        except Exception:
            pass

    def clear(self) -> None:
        self.controls = [self._header]
        try:
            self.update()
        except Exception:
            pass
