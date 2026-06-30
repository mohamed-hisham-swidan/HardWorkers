"""ChatMessage Flet component with streaming, error-safe rendering, and per-message audio."""

from __future__ import annotations

import base64
import threading
import time
from collections.abc import Callable
from pathlib import Path

import flet as ft

from backend.voice.audio_manager import AudioManager, AudioState
from ui.components.markdown_text import MarkdownText
from ui.helpers import Colors
from utils.helpers import elapsed_label
from utils.logging_setup import get_logger

log = get_logger("ui.components.chat_message")

_FLUSH_INTERVAL_S = 0.05

_FALLBACK_ICON = ft.Icons.ERROR_OUTLINE


def safe_icon_button(*, icon, **kwargs):
    """Create an IconButton with a guaranteed valid icon.

    Falls back to ERROR_OUTLINE if icon is falsy (None, empty string, etc.)
    and logs a warning.  Never raises the Flet backend error:
    'IconButton must have either icon or a visible content specified'.
    """
    if not icon:
        log.warning("IconButton missing icon=%r — using fallback", icon)
        icon = _FALLBACK_ICON
    kwargs.setdefault("icon_size", 24)
    return ft.IconButton(icon=icon, **kwargs)


_THUMB_WIDTH = 220
_THUMB_HEIGHT = 140


class ChatMessage(ft.Column):
    """Single chat bubble. Supports text streaming, attachment thumbnails, and per-message audio."""

    _next_msg_id = 0

    def __init__(
        self,
        sender: str,
        initial_text: str = "",
        attachment_path: str | None = None,
        file_type: str | None = None,
        on_copy: Callable[[str, Callable[[bool], None]], None] | None = None,
        on_edit: Callable[[str], None] | None = None,
        on_change_model: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        ChatMessage._next_msg_id += 1
        self._msg_id = f"msg_{ChatMessage._next_msg_id}"
        self.sender = sender
        self.is_user = sender == "You"
        self._raw = initial_text
        self._ready = bool(initial_text)

        self._buf_lock = threading.Lock()
        self._last_flush = time.monotonic()

        self.on_copy = on_copy
        self.on_edit = on_edit
        self.on_change_model = on_change_model
        self._copy_btn: ft.IconButton | None = None
        self._listen_btn: ft.IconButton | None = None

        # Per-message audio controller
        self._audio_ctrl = None
        self._init_audio()

        has_content = bool(initial_text)
        display_text = initial_text if has_content else ""

        self._content_display = MarkdownText(
            initial=display_text,
            selectable=True,
        )
        self._content_display.visible = has_content

        self._spinner = ft.ProgressRing(
            width=16,
            height=16,
            visible=not has_content and not self.is_user,
        )

        self._timer = ft.Text("", size=11, color=Colors.TEXT_MUTED2, visible=False)

        self._attachment_img = ft.Image(
            src="",
            fit=ft.BoxFit.CONTAIN,
            height=_THUMB_HEIGHT,
            width=_THUMB_WIDTH,
            border_radius=8,
            visible=False,
        )
        self._attachment_unavailable = ft.Container(
            content=ft.Text("[Image unavailable]", size=12, color=Colors.TEXT_MUTED, italic=True),
            height=_THUMB_HEIGHT,
            width=_THUMB_WIDTH,
            bgcolor=Colors.BG_HOVER,
            border_radius=8,
            alignment=ft.Alignment.CENTER,
            visible=False,
        )

        has_attachment = bool(attachment_path)
        if has_attachment:
            log.info("CHAT_ATTACHMENT_CREATED path=%s type=%s", attachment_path, file_type)
            p = Path(attachment_path)
            if file_type == "image" and p.is_file():
                try:
                    with open(attachment_path, "rb") as fh:
                        b64 = base64.b64encode(fh.read()).decode()
                    self._attachment_img.src = f"data:image/png;base64,{b64}"
                    self._attachment_img.visible = True
                    log.info("CHAT_ATTACHMENT_RENDERED path=%s src_len=%d", attachment_path, len(b64))
                except Exception as exc:
                    log.warning("CHAT_ATTACHMENT_FAILED path=%s exc=%s", attachment_path, exc)
                    self._attachment_unavailable.visible = True
            else:
                log.info("CHAT_ATTACHMENT_MISSING path=%s type=%s", attachment_path, file_type)
                self._attachment_unavailable.visible = True

        bg_color = Colors.BG_USER_MSG if self.is_user else Colors.BG_AI_MSG
        name_color = Colors.SUCCESS if self.is_user else Colors.PRIMARY

        # Actions row
        action_row = ft.Row(spacing=2, visible=self._ready)
        if self.is_user:
            self._copy_btn = safe_icon_button(
                icon=ft.Icons.COPY_ALL,
                icon_size=16,
                tooltip="Copy",
                on_click=lambda _: self.on_copy(self._raw, self._on_copy_result) if self.on_copy else None,
                style=ft.ButtonStyle(padding=2),
            )
            action_row.controls.append(self._copy_btn)
            action_row.controls.append(
                safe_icon_button(
                    icon=ft.Icons.EDIT,
                    icon_size=16,
                    tooltip="Edit",
                    on_click=lambda _: self.on_edit(self._raw) if self.on_edit else None,
                    style=ft.ButtonStyle(padding=2),
                )
            )
        else:
            self._copy_btn = safe_icon_button(
                icon=ft.Icons.COPY_ALL,
                icon_size=16,
                tooltip="Copy",
                on_click=lambda _: self.on_copy(self._raw, self._on_copy_result) if self.on_copy else None,
                style=ft.ButtonStyle(padding=2),
            )
            self._listen_btn = safe_icon_button(
                icon=ft.Icons.PLAY_ARROW,
                icon_size=16,
                tooltip="Listen",
                on_click=lambda _: self._on_listen_click(),
                style=ft.ButtonStyle(padding=2),
            )
            action_row.controls.extend([
                self._copy_btn,
                safe_icon_button(
                    icon=ft.Icons.REPLAY,
                    icon_size=16,
                    tooltip="Change Model",
                    on_click=lambda _: self.on_change_model() if self.on_change_model else None,
                    style=ft.ButtonStyle(padding=2),
                ),
                self._listen_btn,
            ])

        self._msg_container = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(sender, weight=ft.FontWeight.BOLD, color=name_color, size=14),
                            self._timer,
                            self._spinner,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self._attachment_img,
                    self._attachment_unavailable,
                    self._content_display,
                    action_row,
                ],
                spacing=6,
            ),
            bgcolor=bg_color,
            padding=15,
            border_radius=12,
            width=630,
        )
        self.controls = [
            ft.Row(
                alignment=(ft.MainAxisAlignment.END if self.is_user else ft.MainAxisAlignment.START),
                controls=[self._msg_container],
            )
        ]
        self.action_row = action_row

    # ── Audio integration ──────────────────────────────────────────

    def _init_audio(self) -> None:
        if self.is_user:
            return
        try:
            mgr = AudioManager.get_instance()
            self._audio_ctrl = mgr.get_or_create(self._msg_id, on_state_change=self._on_audio_state)
        except RuntimeError:
            pass  # AudioManager not initialised yet — no audio for this message

    def _on_audio_state(self, state: AudioState) -> None:
        if not self._listen_btn:
            return
        try:
            if state == AudioState.IDLE:
                self._listen_btn.icon = ft.Icons.PLAY_ARROW
                self._listen_btn.icon_color = None
                self._listen_btn.disabled = False
            elif state == AudioState.LOADING:
                self._listen_btn.icon = ft.Icons.HOURGLASS_TOP
                self._listen_btn.icon_color = Colors.TEXT_MUTED2
                self._listen_btn.disabled = True
            elif state == AudioState.PLAYING:
                self._listen_btn.icon = ft.Icons.PAUSE
                self._listen_btn.icon_color = Colors.ERROR
                self._listen_btn.disabled = False
            elif state == AudioState.PAUSED:
                self._listen_btn.icon = ft.Icons.PLAY_ARROW
                self._listen_btn.icon_color = Colors.PRIMARY
                self._listen_btn.disabled = False
            elif state == AudioState.ERROR:
                self._listen_btn.icon = ft.Icons.PLAY_ARROW
                self._listen_btn.icon_color = Colors.ERROR
                self._listen_btn.disabled = False
            self._listen_btn.update()
        except Exception as exc:
            log.debug("Audio state icon update failed: %s", exc)

    def _on_listen_click(self) -> None:
        if not self._audio_ctrl or not self._raw:
            return
        state = self._audio_ctrl.state
        if state == AudioState.IDLE or state == AudioState.ERROR:
            self._audio_ctrl.play(self._raw)
        elif state == AudioState.PLAYING:
            self._audio_ctrl.pause()
        elif state == AudioState.PAUSED:
            self._audio_ctrl.resume()

    # ── Text streaming ────────────────────────────────────────────

    def append_chunk(self, chunk: str) -> None:
        with self._buf_lock:
            self._raw += chunk
            text = self._raw
        now = time.monotonic()
        if now - self._last_flush < _FLUSH_INTERVAL_S:
            return
        self._last_flush = now
        self._flush(text)

    def finalize(self, elapsed_s: float | None = None) -> str:
        with self._buf_lock:
            text = self._raw
        self._flush(text)

        if elapsed_s is not None and not self.is_user:
            self._timer.value = f"\u23f1 {elapsed_label(elapsed_s)}"
            self._timer.visible = True
            try:
                if self._timer.page is not None:
                    self._timer.update()
            except Exception as exc:
                log.debug("Timer update skipped: %s", exc)

        return text

    def raw_text(self) -> str:
        with self._buf_lock:
            return self._raw

    # ── Copy result ───────────────────────────────────────────────

    def _on_copy_result(self, success: bool) -> None:
        if not self._copy_btn:
            return
        try:
            self._copy_btn.icon = ft.Icons.CHECK if success else ft.Icons.CLOSE
            if success:
                self._copy_btn.icon_color = Colors.SUCCESS
            else:
                self._copy_btn.icon_color = Colors.ERROR
            self._copy_btn.update()
        except Exception as exc:
            log.debug("Copy icon update failed: %s", exc)
        threading.Timer(2.0, self._reset_copy_icon).start()

    def _reset_copy_icon(self) -> None:
        if not self._copy_btn:
            return
        try:
            self._copy_btn.icon = ft.Icons.COPY_ALL
            self._copy_btn.icon_color = None
            page = self.page
            if page is not None:
                page.run_thread(self._copy_btn.update)
            else:
                self._copy_btn.update()
        except Exception as exc:
            log.debug("Reset copy icon failed: %s", exc)

    # ── Flush ─────────────────────────────────────────────────────

    def _flush(self, text: str) -> None:
        try:
            if not self._ready and text:
                self._content_display.visible = True
                self._spinner.visible = False
                self.action_row.visible = True
                self._ready = True
            if self._ready or text:
                self._content_display.value = text
            try:
                page = self.page
                if page is not None:
                    page.run_thread(self.update)
                else:
                    self.update()
            except Exception as exc:
                log.debug("Update skipped: %s", exc)
        except Exception as exc:
            log.debug("Render skipped: %s", exc)

    def retheme(self) -> None:
        """Re-apply current Colors palette to message bubble."""
        self._msg_container.bgcolor = Colors.BG_USER_MSG if self.is_user else Colors.BG_AI_MSG
        sender_text = self._msg_container.content.controls[0].controls[0]
        if isinstance(sender_text, ft.Text):
            sender_text.color = Colors.SUCCESS if self.is_user else Colors.PRIMARY
        self._timer.color = Colors.TEXT_MUTED2
        self._attachment_unavailable.bgcolor = Colors.BG_HOVER
        try:
            self.update()
        except Exception:
            pass

    def set_message_width(self, width: int) -> None:
        self._msg_container.width = width
