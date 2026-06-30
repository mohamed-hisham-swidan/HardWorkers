from __future__ import annotations

"""Main application window — orchestrates all UI components and service layer.

Design principles:
  - Minimal, clean toolbar (ChatGPT-inspired)
  - Sidebar with date-grouped chats and context menus
  - Responsive layout for 1366x768 through 4K
  - All service calls via ThreadPoolExecutor
  - UI mutations through page.run_thread()
"""

from enum import Enum, auto


class LifecycleState(Enum):
    STARTING = auto()
    READY = auto()
    BUSY = auto()
    SHUTTING_DOWN = auto()
    CLOSED = auto()


import asyncio
import json
import threading
import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import flet as ft

from backend.voice.audio_manager import AudioManager
from config.constants import APP_NAME, MAX_IMPORT_SIZE_BYTES, MIN_RESPONSE_LENGTH
from config.settings import AppConfig
from core.container import Container
from core.events import EventBus, SettingsChangedEvent
from database.repositories import DatabaseManager
from memory.memory_service import MemoryService
from memory.summarization_service import SummarizationService
from models.enums import AppStatus, MessageRole
from services.ai import ApiModelClient, ModelCreatorService, ModelManager, ModelRouterService, OllamaClient
from services.chat_service import ChatService
from services.diagnostics_service import DiagnosticsService
from services.infrastructure.ollama_lifecycle import OllamaLifecycleService
from services.workspace_service import WorkspaceService
from settings.service import SettingsService
from ui.components.agent import AgentActivityFeed, AgentInfoPanel, AgentStatus, AgentStatusBadge
from ui.components.chat_message import ChatMessage
from ui.components.chat_sidebar import ChatSidebar
from ui.components.memory_panel import MemoryPanel
from ui.components.model_selector import ModelSelector
from ui.components.waveform import RecordingIndicator, WaveformAnimation
from ui.controllers.mic_controller import MicController
from ui.dialogs.diagnostics_dialog import DiagnosticsDialog
from ui.dialogs.model_creator_dialog import ModelCreatorDialog
from ui.dialogs.registry_dialog import RegistryDialog
from ui.dialogs.settings_dialog import SettingsDialog
from ui.helpers import Colors, apply_flet_theme, detect_os_theme
from utils.clipboard import copy_to_clipboard
from utils.logging_setup import get_logger
from utils.token_counter import count as count_tokens
from vectorstore.faiss_store import VectorStore

log = get_logger("ui.main_window")


class MainWindow:
    """Top-level Flet application controller."""

    def __init__(
        self,
        page: ft.Page,
        config: AppConfig,
        db: DatabaseManager,
        vs: VectorStore,
        ollama: OllamaClient,
        ollama_lifecycle: OllamaLifecycleService,
        model_manager: ModelManager,
        model_creator: ModelCreatorService,
        model_router: ModelRouterService,
        memory: MemoryService,
        workspaces: WorkspaceService,
        chats: ChatService,
        summarizer: SummarizationService,
        diagnostics: DiagnosticsService,
        bus: EventBus | None = None,
        settings: SettingsService | None = None,
        container: Container | None = None,
        stt=None,
    ) -> None:
        self._lifecycle = LifecycleState.READY
        self._page = page
        self._ollama_state = "unknown"
        self._cfg = config
        self._bus = bus
        self._settings = settings
        self._container = container
        self._db = db
        self._vs = vs
        self._ollama = ollama
        self._ollama_lifecycle = ollama_lifecycle
        self._mm = model_manager
        self._creator = model_creator
        self._router = model_router
        self._memory = memory
        self._workspaces = workspaces
        self._chats = chats
        self._summarizer = summarizer
        self._diag_svc = diagnostics
        self._stt = stt

        self._active_chat_id: int | None = None
        self._sidebar_visible = True
        self._pasted_image_path: str | None = None
        self._paste_dir = Path(Path.home() / ".hardworkers" / "paste")
        self._paste_dir.mkdir(parents=True, exist_ok=True)
        self._stop = threading.Event()
        self._generating = False
        self._gen_lock = threading.Lock()
        self._pipeline_running = False
        self._paste_version = 0
        self._sending = False
        self._user_explicitly_selected_model = False
        self._pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="hw-worker")
        self._llm_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="hw-llm")
        self._snack: ft.SnackBar | None = None
        self._diag_dlg = DiagnosticsDialog(page)
        self._settings_dlg: SettingsDialog | None = SettingsDialog(page, settings, bus) if settings else None
        self._creator_dlg = ModelCreatorDialog(
            page=page,
            creator=self._creator,
            model_manager=self._mm,
            pool=self._pool,
            on_models_changed=self._refresh_models_from_registry,
        )
        self._registry_dlg = RegistryDialog(
            page=page,
            creator=self._creator,
            model_manager=self._mm,
            creator_dlg=self._creator_dlg,
            pool=self._pool,
            on_models_changed=self._refresh_models_from_registry,
        )

        # ── Voice waveform controls ────────────────────────────────────
        self._waveform = WaveformAnimation()
        self._rec_indicator = RecordingIndicator()

        # ── Memory panel ───────────────────────────────────────────────
        self._memory_panel = MemoryPanel(on_add_fact=self._on_add_fact)
        self._memory_dialog = ft.AlertDialog(
            modal=False,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.MEMORY, color=Colors.PRIMARY, size=20),
                    ft.Text("Memory", size=18, weight=ft.FontWeight.BOLD),
                ],
                spacing=8,
            ),
            content=ft.Container(content=self._memory_panel, width=360, height=520),
            actions=[
                ft.TextButton(
                    "Close",
                    on_click=lambda _: setattr(self._memory_dialog, "open", False) or self._memory_dialog.update(),
                )
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        # ── Agent UX components ────────────────────────────────────────
        self._agent_badge = AgentStatusBadge()
        self._agent_info = AgentInfoPanel()
        self._agent_feed = AgentActivityFeed()

        self._configure_page()
        self._build_ui()

        # ── Mic controller (STT) ───────────────────────────────────────
        self._mic_ctl = MicController(
            page=page,
            stt=stt,
            btn_mic=self._btn_mic,
            waveform=self._waveform,
            rec_indicator=self._rec_indicator,
            entry=self._entry,
            on_update_input_bar_visibility=self._update_input_bar_visibility,
            on_show_toast=self.show_toast,
        )
        self._btn_mic.on_click = self._mic_ctl.toggle_mic

        # ── Audio manager (per-message TTS playback) ───────────────────
        AudioManager.init(page=page, num_channels=32)

        log.info("TIMING MainWindow init complete — submitting bootstrap")
        self._safe_submit(self._bootstrap)

    # ── Safe executor submission ──────────────────────────────────────

    def _safe_submit(self, fn, *args, **kwargs):
        """Submit to pool only if lifecycle permits. Never crashes."""
        if self._lifecycle in (LifecycleState.SHUTTING_DOWN, LifecycleState.CLOSED):
            log.warning("SUBMIT_BLOCKED lifecycle=%s", self._lifecycle)
            return None
        if self._pool is None:
            log.warning("SUBMIT_BLOCKED pool=None — recreating")
            self._pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="hw-worker")
        try:
            return self._pool.submit(fn, *args, **kwargs)
        except RuntimeError as e:
            log.warning("SUBMIT_FAILED %s — recreating pool", e)
            old = self._pool
            self._pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="hw-worker")
            try:
                old.shutdown(wait=False)
            except Exception:
                log.debug("Old thread pool shutdown ignored")
            return self._pool.submit(fn, *args, **kwargs)

    def _safe_submit_llm(self, fn, *args, **kwargs):
        """Submit LLM work to the dedicated LLM pool. Never crashes."""
        if self._lifecycle in (LifecycleState.SHUTTING_DOWN, LifecycleState.CLOSED):
            log.warning("LLM_SUBMIT_BLOCKED lifecycle=%s", self._lifecycle)
            return None
        if self._llm_pool is None:
            log.warning("LLM_SUBMIT_BLOCKED pool=None — recreating")
            self._llm_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="hw-llm")
        try:
            return self._llm_pool.submit(fn, *args, **kwargs)
        except RuntimeError as e:
            log.warning("LLM_SUBMIT_FAILED %s — recreating pool", e)
            old = self._llm_pool
            self._llm_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="hw-llm")
            try:
                old.shutdown(wait=False)
            except Exception:
                log.debug("Old LLM pool shutdown ignored")
            return self._llm_pool.submit(fn, *args, **kwargs)

    def _safe_run_thread(self, callback, *args, **kwargs) -> None:
        """Dispatch callback to the Flet UI thread iff the session is alive.

        Silently drops the callback when the window is shutting down or
        already closed, which prevents the ``RuntimeError: An attempt to
        fetch destroyed session`` crash that occurs when cleanup code
        touches ``page`` after ``window.destroy()``.
        """
        if self._lifecycle in (LifecycleState.SHUTTING_DOWN, LifecycleState.CLOSED):
            log.debug("run_thread dropped — lifecycle=%s", self._lifecycle.name)
            return
        try:
            self._page.run_thread(callback, *args, **kwargs)
        except RuntimeError as exc:
            log.debug("run_thread failed — page session may be gone: %s", exc)

    # ── Sidebar toggle ─────────────────────────────────────────────────

    def _toggle_sidebar(self, _e: ft.ControlEvent | None = None) -> None:
        self._sidebar_visible = not self._sidebar_visible
        self._chat_sidebar.visible = self._sidebar_visible
        self._on_page_resize()
        try:
            self._page.update()
        except Exception as exc:
            log.warning("Failed to toggle sidebar: %s", exc)

    def _on_settings(self, _e: ft.ControlEvent | None = None) -> None:
        if self._settings_dlg:
            self._settings_dlg.show()
        else:
            self.show_toast("Settings service unavailable", Colors.ERROR)

    def _on_memory(self, _e: ft.ControlEvent | None = None) -> None:
        self._refresh_memory_panel()
        self._page.show_dialog(self._memory_dialog)

    def _on_model_manager(self, _e: ft.ControlEvent | None = None) -> None:
        self._registry_dlg.show()

    # ------------------------------------------------------------------
    # Page setup
    # ------------------------------------------------------------------

    def _configure_page(self) -> None:
        t0 = time.monotonic()
        self._page.title = APP_NAME
        us = self._settings.current if self._settings else None
        saved_theme = us.appearance.theme if us else "dark"
        apply_flet_theme(self._page, saved_theme)
        Colors.set_theme(saved_theme)
        self._page.bgcolor = Colors.BG_PAGE
        self._page.padding = ft.Padding(left=0, right=0, top=0, bottom=0)

        us = self._settings.current if self._settings else None
        self._page.window.width = max(1000, us.appearance.window_width if us else self._cfg.ui.width)
        self._page.window.height = max(600, us.appearance.window_height if us else self._cfg.ui.height)
        self._page.window.min_width = 1000
        self._page.window.min_height = 600
        self._page.window.icon = str(Path(__file__).resolve().parent.parent / "assets" / "app_logo.ico")
        self._page.on_resize = self._on_page_resize
        self._page.on_close = self._on_close
        self._page.on_keyboard_event = self._on_keyboard
        self._page.on_error = self._on_page_error
        if self._bus:
            self._bus.on("SettingsChangedEvent", self._on_settings_changed)
        log.info("TIMING _configure_page: %.3fs", time.monotonic() - t0)

        # ── OS theme poller (for SYSTEM mode) ─────────────────────────
        if saved_theme == "system":
            self._start_os_theme_poller()

    # ── OS theme change detection ──────────────────────────────────────

    def _start_os_theme_poller(self) -> None:
        """Poll OS theme changes every 10 s when in system mode."""

        async def _poll() -> None:
            while self._lifecycle not in (LifecycleState.SHUTTING_DOWN, LifecycleState.CLOSED):
                await asyncio.sleep(10)
                try:
                    self._check_os_theme_switch()
                except Exception:
                    pass

        asyncio.create_task(_poll())

    def _check_os_theme_switch(self) -> None:
        """If saved preference is ``"system"`` and OS theme has changed,
        re-theme all widgets without user interaction."""
        us = self._settings.current if self._settings else None
        if us and us.appearance.theme == "system":
            actual = detect_os_theme()
            if actual != Colors._current:
                log.info("OS theme changed %s -> %s — re-theming", Colors._current, actual)
                Colors.set_theme("system")
                apply_flet_theme(self._page, "system")
                self._page.bgcolor = Colors.BG_PAGE
                self._retheme_existing_widgets()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        t0 = time.monotonic()

        # ── Status (badge replaces old text, kept for _set_status compat) ─
        self._status = ft.Text(
            f"STATUS: {AppStatus.LOADING}",
            color=Colors.WARNING,
            weight=ft.FontWeight.BOLD,
            size=12,
            visible=False,
        )

        # ── Model selector ─────────────────────────────────────────────
        models = self._mm.get_available() or [self._cfg.ollama.default_model]
        self._model_sel = ModelSelector(models, on_change=self._on_model_change)

        # ── File picker (Service — auto-registers via init(), no overlay) ─
        self._file_picker = ft.FilePicker()

        # ── Workspace selector (styled) ────────────────────────────────
        self._workspace_sel = ft.Dropdown(
            label="",
            hint_text="Workspace",
            options=[],
            width=130,
            height=36,
            border_radius=Colors.RADIUS_MD,
            filled=True,
            bgcolor=Colors.BG_SURFACE,
            text_size=12,
            content_padding=ft.Padding(left=8, right=8, top=4, bottom=4),
        )
        self._workspace_sel.on_change = self._on_workspace_change

        # ── Minimal toolbar ────────────────────────────────────────────
        self._btn_hamburger = ft.IconButton(
            icon=ft.Icons.MENU,
            icon_size=18,
            icon_color=Colors.TEXT_MEDIUM,
            tooltip="Toggle chat sidebar (Ctrl+B)",
            on_click=self._toggle_sidebar,
            style=ft.ButtonStyle(padding=6),
        )

        self._btn_settings = ft.IconButton(
            icon=ft.Icons.SETTINGS,
            icon_size=18,
            icon_color=Colors.TEXT_MEDIUM,
            tooltip="Settings (Ctrl+S)",
            on_click=self._on_settings,
            style=ft.ButtonStyle(padding=6),
        )

        self._btn_model_mgr = ft.IconButton(
            icon=ft.Icons.DATASET,
            icon_size=18,
            icon_color=Colors.TEXT_MEDIUM,
            tooltip="Model Manager",
            on_click=self._on_model_manager,
            style=ft.ButtonStyle(padding=6),
        )

        self._btn_clear_chat = ft.IconButton(
            icon=ft.Icons.DELETE_SWEEP_OUTLINED,
            icon_size=18,
            icon_color=Colors.TEXT_MUTED2,
            tooltip="Clear current chat (Ctrl+L)",
            on_click=lambda _: self._on_clear_chat(),
            style=ft.ButtonStyle(padding=6),
        )

        # ── Chat list ──────────────────────────────────────────────────
        self._chat_list = ft.ListView(expand=True, spacing=10, auto_scroll=True)

        # ── Input area ─────────────────────────────────────────────────
        self._entry = ft.TextField(
            expand=True,
            multiline=True,
            min_lines=1,
            max_lines=6,
            hint_text="Message\u2026",
            border_radius=Colors.RADIUS_MD,
            bgcolor=Colors.BG_USER_MSG,
            border_color=Colors.BORDER_INPUT,
            focused_border_color=Colors.BORDER_FOCUS,
            shift_enter=True,
            on_submit=lambda _: self._send_message(),
        )

        self._btn_send = ft.IconButton(
            icon=ft.Icons.SEND_ROUNDED,
            icon_size=20,
            icon_color=Colors.TEXT_HIGH,
            bgcolor=Colors.PRIMARY,
            tooltip="Send message",
            on_click=lambda _: self._send_message(),
            style=ft.ButtonStyle(shape=ft.CircleBorder(), padding=8),
        )

        self._btn_stop = ft.IconButton(
            icon=ft.Icons.STOP_ROUNDED,
            icon_size=20,
            icon_color=Colors.TEXT_HIGH,
            bgcolor=Colors.ERROR,
            visible=False,
            tooltip="Stop generation",
            on_click=lambda _: self._stop_generation(),
            style=ft.ButtonStyle(shape=ft.CircleBorder(), padding=8),
        )

        # ── Media action buttons ───────────────────────────────────────
        self._btn_paste_img = ft.IconButton(
            icon=ft.Icons.CONTENT_PASTE,
            icon_size=18,
            icon_color=Colors.TEXT_MUTED2,
            tooltip="Paste image (Ctrl+V)",
            on_click=lambda _: self._paste_clipboard_image(),
            style=ft.ButtonStyle(padding=6),
        )

        stt_ok = self._stt is not None and self._stt.is_available
        self._btn_mic = ft.IconButton(
            icon=ft.Icons.MIC,
            icon_size=20,
            icon_color=Colors.TEXT_MUTED2,
            tooltip="Voice input" if stt_ok else "Voice input requires PyAudio — run: pip install pyaudio",
            on_click=None,
            disabled=not stt_ok,
            style=ft.ButtonStyle(shape=ft.CircleBorder(), padding=8),
        )

        self._btn_attach = ft.IconButton(
            icon=ft.Icons.ATTACH_FILE,
            icon_size=18,
            icon_color=Colors.TEXT_MUTED2,
            tooltip="Attach file",
            on_click=lambda _: self._page.run_task(self._on_attach_click),
            style=ft.ButtonStyle(padding=6),
        )

        # ── Image preview (immediate, no toast) ────────────────────────
        self._img_preview_img = ft.Image(src="", fit=ft.BoxFit.CONTAIN, height=140, width=220)
        self._img_preview_zoom = ft.Container(
            content=ft.Icon(ft.Icons.ZOOM_IN, color=Colors.TEXT_HIGH, size=16),
            bgcolor=ft.Colors.with_opacity(0.5, "#000000"),
            border_radius=4,
            padding=ft.Padding(left=4, right=4, top=4, bottom=4),
            on_click=lambda _: self._zoom_image_preview(),
        )

        self._img_preview = ft.Container(
            visible=False,
            border_radius=Colors.RADIUS_MD,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            width=220,
            content=ft.Stack(
                width=220,
                height=140,
                controls=[
                    self._img_preview_img,
                    ft.Container(
                        content=ft.GestureDetector(
                            content=ft.Icon(ft.Icons.CLOSE, size=14, color=Colors.TEXT_HIGH),
                            on_tap=lambda _: self._clear_pasted_image(),
                        ),
                        top=2,
                        right=2,
                        width=24,
                        height=24,
                        bgcolor=ft.Colors.with_opacity(0.7, Colors.ERROR),
                        border_radius=12,
                    ),
                    ft.Container(
                        content=self._img_preview_zoom,
                        alignment=ft.Alignment.TOP_LEFT,
                        padding=2,
                        width=32,
                        height=32,
                    ),
                ],
            ),
        )

        # ── Chat sidebar ───────────────────────────────────────────────
        self._chat_sidebar = ChatSidebar(
            on_chat_select=self._on_chat_select,
            on_chat_create=self._on_chat_create,
            on_chat_delete=self._on_chat_delete,
            on_chat_pin=self._on_chat_pin,
            on_chat_rename=self._on_chat_rename,
        )

        # ── Centered chat column (ChatGPT-style) ──────────────────────
        self._chat_col_ref = ft.Ref[ft.Container]()
        self._chat_col_container = ft.Container(
            ref=self._chat_col_ref,
            width=min(800, int((self._page.width or 1280) * 0.7)),
            content=ft.Column(
                [ft.Container(height=12), self._chat_list, ft.Container(height=12)],
                spacing=0,
                expand=True,
            ),
        )

        self._chat_area = ft.Container(
            expand=True,
            padding=ft.Padding(left=0, right=0, top=0, bottom=0),
            bgcolor=Colors.BG_CHAT,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            content=ft.Row(
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    ft.Container(expand=True),
                    self._chat_col_container,
                    ft.Container(expand=True),
                ],
            ),
        )

        # ── Voice waveform + recording indicator ───────────────────────
        self._voice_status = ft.Container(
            content=ft.Row(
                [self._waveform, self._rec_indicator],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(left=4),
        )

        self._input_inner = ft.Container(
            content=ft.Row(
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    self._entry,
                    self._btn_mic,
                    self._btn_send,
                    self._btn_stop,
                ],
            ),
            border=ft.BorderSide(1, Colors.BORDER_DIVIDER),
            border_radius=Colors.RADIUS_LG,
            padding=ft.Padding(left=4, right=4, top=2, bottom=2),
            bgcolor=Colors.BG_SURFACE,
        )

        self._input_row = ft.Container(
            padding=ft.Padding(left=16, right=16, top=8, bottom=12),
            content=ft.Column(
                spacing=6,
                controls=[
                    self._voice_status,
                    self._input_inner,
                ],
            ),
        )

        self._chat_panel = ft.Column(
            expand=True,
            spacing=0,
            controls=[
                self._chat_area,
                self._img_preview,
                self._input_row,
            ],
        )

        # ── Overflow menu (settings, model manager, clear) ─────────
        self._overflow_menu = ft.PopupMenuButton(
            icon=ft.Icons.MORE_VERT,
            icon_size=18,
            icon_color=Colors.TEXT_MUTED,
            tooltip="More actions",
            style=ft.ButtonStyle(padding=4),
            items=[
                ft.PopupMenuItem(
                    icon=ft.Icons.DATASET,
                    content="Model Manager",
                    on_click=lambda _: self._on_model_manager(),
                ),
                ft.PopupMenuItem(
                    icon=ft.Icons.SETTINGS,
                    content="Settings",
                    on_click=lambda _: self._on_settings(),
                ),
                ft.PopupMenuItem(),
                ft.PopupMenuItem(
                    icon=ft.Icons.DATA_EXPLORATION,
                    content="Toggle Activity Feed",
                    on_click=lambda _: self._toggle_activity_feed(),
                ),
                ft.PopupMenuItem(),
                ft.PopupMenuItem(
                    icon=ft.Icons.DELETE_SWEEP_OUTLINED,
                    content="Clear Chat",
                    on_click=lambda _: self._on_clear_chat(),
                ),
            ],
        )

        # ── App logo (transparent PNG, floating in toolbar) ──────────
        logo_path = str(Path(__file__).resolve().parent.parent / "assets" / "app_logo.png")
        self._app_logo = ft.Container(
            content=ft.Image(src=logo_path, height=36, width=36, fit=ft.BoxFit.CONTAIN),
            padding=ft.Padding(left=6, right=6, top=4, bottom=4),
            bgcolor=ft.Colors.with_opacity(0.08, Colors.BG_SURFACE),
            border_radius=10,
            shadow=ft.BoxShadow(
                blur_radius=16,
                spread_radius=1,
                color=ft.Colors.with_opacity(0.25, "#000000"),
            ),
            tooltip="HardWorkres",
        )

        # ── Minimal toolbar ────────────────────────────────────────────
        self._toolbar = ft.Container(
            padding=ft.Padding(left=4, right=8, top=0, bottom=0),
            bgcolor=Colors.BG_SURFACE,
            border=ft.border.Border(bottom=ft.BorderSide(1, Colors.BORDER_DIVIDER)),
            height=48,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=2,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            self._btn_hamburger,
                            ft.VerticalDivider(width=8, color=Colors.BORDER_DIVIDER),
                            self._app_logo,
                            ft.VerticalDivider(width=4, color=Colors.BORDER_DIVIDER),
                            ft.Container(
                                content=self._workspace_sel,
                                padding=ft.Padding(right=4),
                            ),
                            ft.VerticalDivider(width=4, color=Colors.BORDER_DIVIDER),
                            self._model_sel,
                            ft.VerticalDivider(width=4, color=Colors.BORDER_DIVIDER),
                            self._overflow_menu,
                        ],
                    ),
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            self._agent_badge,
                            self._agent_info,
                            self._status,
                        ],
                    ),
                ],
            ),
        )

        # ── Content area ───────────────────────────────────────────────
        self._content_area = ft.Container(
            expand=True,
            content=ft.Row(
                expand=True,
                spacing=0,
                controls=[self._chat_sidebar, self._chat_panel],
            ),
        )

        self._agent_feed_container = ft.Container(
            content=self._agent_feed,
            visible=False,
            bgcolor=Colors.BG_SURFACE2,
            border=ft.border.Border(bottom=ft.BorderSide(1, Colors.BORDER_DIVIDER)),
        )

        self._page.add(
            ft.Column(
                expand=True,
                spacing=0,
                controls=[self._toolbar, self._agent_feed_container, self._content_area],
            )
        )
        self._on_page_resize()
        log.info("TIMING _build_ui: %.3fs", time.monotonic() - t0)

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def _bootstrap(self) -> None:
        t0 = time.monotonic()
        self._set_status(AppStatus.INDEXING, Colors.WARNING)
        self._page.run_thread(lambda: self._agent_feed.add_event("Starting app\u2026", Colors.PRIMARY))

        # ── Ensure Ollama is running (non-blocking — already on thread pool) ──
        def _ollama_progress(msg: str) -> None:
            log.info("OLLAMA_PROGRESS %s", msg)
            self._page.run_thread(lambda m=msg: self._set_status(AppStatus.INDEXING, Colors.WARNING))
            self._page.run_thread(lambda m=msg: self._agent_feed.add_event(f"Ollama: {m}", Colors.WARNING))

        self._ollama_state = self._ollama_lifecycle.ensure_running(on_progress=_ollama_progress)

        if self._ollama_state == "binary_not_found":
            self._page.run_thread(
                lambda: self.show_toast(
                    "Ollama binary not found — download from https://ollama.com",
                    Colors.WARNING,
                )
            )
        elif self._ollama_state == "launch_failed":
            self._page.run_thread(
                lambda: self.show_toast(
                    "Ollama failed to launch — check logs",
                    Colors.WARNING,
                )
            )

        try:
            t1 = time.monotonic()
            models = self._mm.refresh_available()
            log.info("TIMING model refresh: %.3fs (%d models)", time.monotonic() - t1, len(models))

            t1 = time.monotonic()
            self._workspaces.switch("Default")
            log.info("TIMING workspace switch: %.3fs", time.monotonic() - t1)

            t1 = time.monotonic()
            active_ws = self._workspaces.get_active()
            if active_ws is not None:
                self._active_chat_id = self._chats.get_default_chat(active_ws.id)
            log.info("TIMING get default chat: %.3fs", time.monotonic() - t1)

            active = self._mm.get_active()
            self._page.run_thread(lambda: self._model_sel.update_models(models, active))
            self._page.run_thread(self._load_history)
            self._page.run_thread(self._refresh_chat_sidebar)
            self._page.run_thread(self._refresh_workspace_selectors)
            self._page.run_thread(self._refresh_memory_panel)

            if not self._page.web:

                async def _center() -> None:
                    try:
                        await self._page.window.center()
                    except Exception as exc:
                        log.warning("Window center failed (non-critical): %s", exc)

                self._page.run_task(_center)

            self._page.run_thread(lambda: self._agent_feed.add_event("Bootstrap completed", Colors.SUCCESS))
        except Exception as exc:
            log.error("Bootstrap error: %s\n%s", exc, traceback.format_exc())
            err_msg = f"Failed to initialise the application:\n{exc}"
            self._page.run_thread(
                lambda m=err_msg: self.show_error_recovery(
                    "Bootstrap error",
                    m,
                )
            )
            self._page.run_thread(lambda e=exc: self._agent_feed.add_event(f"Bootstrap error: {e}", Colors.ERROR))
        finally:
            log.info("TIMING bootstrap total: %.3fs", time.monotonic() - t0)
            self._set_status(AppStatus.READY, Colors.SUCCESS)
            self._page.run_thread(lambda: self._agent_feed.add_event("Ready", Colors.SUCCESS))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_model_change(self, name: str) -> None:
        log.info("MODEL_CHANGE_REQUESTED model=%s", name)
        self._user_explicitly_selected_model = True
        self._safe_submit(self._on_model_change_bg, name)

    def _on_model_change_bg(self, name: str) -> None:
        log.info("MODEL_CHANGE_APPLIED model=%s", name)
        self._mm.set_active(name)
        self._workspaces.update_active_model(name)

    def _on_workspace_change(self, e: ft.ControlEvent) -> None:
        if not self._workspace_sel.value:
            return
        self._safe_submit(self._switch_workspace, self._workspace_sel.value)

    def _switch_workspace(self, ws_name: str) -> None:
        self._set_status(AppStatus.LOADING, Colors.WARNING)
        self._user_explicitly_selected_model = False
        log.info("EXPLICIT_MODEL_SELECTION_RESET reason=workspace_switch")
        try:
            success, msg = self._workspaces.switch(ws_name)
            if success:
                active_ws = self._workspaces.get_active()
                if active_ws:
                    self._active_chat_id = self._chats.get_default_chat(active_ws.id)
                    self._page.run_thread(self._load_history)
                    self._page.run_thread(self._refresh_chat_sidebar)
                    self._page.run_thread(
                        lambda: self._model_sel.update_models(self._mm.get_available(), self._mm.get_active())
                    )
            else:
                self._page.run_thread(lambda: self.show_toast(f"Workspace switch failed: {msg}", Colors.ERROR))
        except Exception as exc:
            log.error("Error switching workspace: %s\n%s", exc, traceback.format_exc())
            self._page.run_thread(lambda _e=exc: self.show_toast(f"Error: {_e}", Colors.ERROR))
        finally:
            self._set_status(AppStatus.READY, Colors.SUCCESS)

    def _refresh_workspace_selectors(self) -> None:
        workspaces = self._workspaces.get_all()
        active_ws = self._workspaces.get_active()
        self._workspace_sel.options = [ft.dropdown.Option(w.name) for w in workspaces]
        if active_ws:
            self._workspace_sel.value = active_ws.name
        try:
            self._workspace_sel.update()
        except Exception as exc:
            log.warning("Failed to update workspace selector: %s", exc)

    def _refresh_models_from_registry(self) -> None:
        self._safe_submit(self._refresh_models_bg)

    def _refresh_models_bg(self) -> None:
        try:
            models = self._mm.refresh_available()
            active = self._mm.get_active()

            def _apply() -> None:
                previous = self._model_sel.value if hasattr(self, "_model_sel") else None
                self._model_sel.update_models(models, active)
                current = self._model_sel.value
                if previous is not None and previous != current and self._user_explicitly_selected_model:
                    log.info("EXPLICIT_MODEL_SELECTION_RESET reason=model_removed")
                    self._user_explicitly_selected_model = False

            self._page.run_thread(_apply)
        except Exception as exc:
            log.error("Failed to refresh models: %s\n%s", exc, traceback.format_exc())
            msg = f"Failed to refresh models: {exc}"
            self._page.run_thread(lambda: self.show_toast(msg, Colors.ERROR))

    async def _on_attach_click(self) -> None:
        files = await self._file_picker.pick_files(
            allow_multiple=False,
            allowed_extensions=["json", "png", "jpg", "jpeg", "gif", "bmp", "webp", "md", "txt"],
        )
        if not files:
            return
        path = Path(files[0].path)
        ext = path.suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
            self._show_image_preview(str(path))
        else:
            self._safe_submit(self._import_file, path)

    def _import_file(self, path: Path) -> None:
        try:
            if path.stat().st_size > MAX_IMPORT_SIZE_BYTES:
                self._page.run_thread(lambda: self.show_toast("Import rejected: file too large", Colors.ERROR))
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                chat_id = self._active_chat_id
                if chat_id is None:
                    ws = self._workspaces.get_active()
                    if ws is not None:
                        chat_id = self._chats.get_default_chat(ws.id)
                        self._active_chat_id = chat_id
                for item in data:
                    if isinstance(item, dict) and item.get("content"):
                        if chat_id is not None:
                            self._db.chat.save_for_chat(chat_id, item.get("role", "user"), item["content"])
            self._page.run_thread(self._load_history)
            self._page.run_thread(self._refresh_chat_sidebar)
            self._page.run_thread(lambda: self.show_toast("Import completed successfully", Colors.SUCCESS))
        except Exception as exc:
            log.error("Import failed: %s\n%s", exc, traceback.format_exc())
            self._page.run_thread(lambda _e=exc: self.show_toast(f"Import failed: {_e}", Colors.ERROR))

    def _on_diagnostics(self, _e: ft.ControlEvent) -> None:
        self._safe_submit(self._run_diagnostics)

    def _run_diagnostics(self) -> None:
        self._set_status(AppStatus.LOADING, Colors.WARNING)
        try:
            snap = self._diag_svc.snapshot()
            text = self._diag_svc.format_text(snap)
            self._page.run_thread(lambda: self._diag_dlg.show(snap, text))
        finally:
            self._set_status(AppStatus.READY, Colors.SUCCESS)

    def _on_add_fact(self, key: str, value: str) -> None:
        self._safe_submit(self._add_fact_async, key, value)

    def _add_fact_async(self, key: str, value: str) -> None:
        try:
            self._memory.add_fact(key, value)
        except Exception as exc:
            log.error("Add fact failed: %s\n%s", exc, traceback.format_exc())
            self._page.run_thread(lambda _e=exc: self.show_toast(f"Add fact failed: {_e}", Colors.ERROR))

    # ------------------------------------------------------------------
    # Global error handler (crash recovery)
    # ------------------------------------------------------------------

    def _on_page_error(self, e: ft.ControlEvent) -> None:
        log.error("Unhandled page error: %s\n%s", e.data, traceback.format_exc())
        if getattr(self, "_error_shown", False):
            return
        self._error_shown = True
        self.show_error_recovery(
            "Something went wrong",
            f"The application encountered an unexpected error:\n{e.data}\n\n{traceback.format_exc()}",
        )

    # ------------------------------------------------------------------
    # Chat sidebar events
    # ------------------------------------------------------------------

    def _on_chat_select(self, chat_id: int) -> None:
        if chat_id == self._active_chat_id:
            return
        with self._gen_lock:
            if self._generating:
                return
            self._active_chat_id = chat_id
        self._page.run_thread(self._load_history)
        self._safe_submit(self._refresh_chat_sidebar_bg)
        self._page.run_thread(self._refresh_memory_panel)

    def _refresh_chat_sidebar_bg(self) -> None:
        ws = self._workspaces.get_active()
        if ws is None:
            return
        chats = self._chats.get_chats(ws.id)
        self._page.run_thread(lambda: self._chat_sidebar.refresh(chats, self._active_chat_id))

    def _on_chat_create(self) -> None:
        ws = self._workspaces.get_active()
        if ws is None:
            return
        with self._gen_lock:
            if self._generating:
                return
        chat_id = self._chats.create_chat(ws.id)
        self._active_chat_id = chat_id
        self._page.run_thread(self._load_history)
        self._safe_submit(self._refresh_chat_sidebar_bg)
        self._page.run_thread(self._refresh_memory_panel)
        self._page.run_thread(lambda: self.show_toast("New chat created", Colors.SUCCESS))

    def _on_chat_delete(self, chat_id: int) -> None:
        ws = self._workspaces.get_active()
        if ws is None:
            return
        with self._gen_lock:
            if self._generating:
                return
        new_id = self._chats.delete_chat(chat_id, ws.id)
        self._active_chat_id = new_id
        self._page.run_thread(self._load_history)
        self._safe_submit(self._refresh_chat_sidebar_bg)
        self._page.run_thread(self._refresh_memory_panel)

    def _on_chat_pin(self, chat_id: int) -> None:
        ws = self._workspaces.get_active()
        if ws is None:
            return
        chat = self._chats.get_chat(chat_id)
        if chat is None:
            return
        self._chats.pin_chat(chat_id, not chat.pinned)
        self._safe_submit(self._refresh_chat_sidebar_bg)

    def _on_chat_rename(self, chat_id: int, new_name: str) -> None:
        self._safe_submit(self._on_chat_rename_bg, chat_id, new_name)

    def _on_chat_rename_bg(self, chat_id: int, new_name: str) -> None:
        self._chats.rename_chat(chat_id, new_name)
        self._refresh_chat_sidebar_bg()

    def _on_clear_chat(self) -> None:
        chat_id = self._active_chat_id
        if chat_id is None:
            return
        with self._gen_lock:
            if self._generating:
                return
        self._db.chat.clear_for_chat(chat_id)
        self._db.chat_summaries.delete_all_for_chat(chat_id)
        self._page.run_thread(self._load_history)
        self._page.run_thread(lambda: self.show_toast("Chat cleared", Colors.SUCCESS))

    # ------------------------------------------------------------------
    # Sending messages
    # ------------------------------------------------------------------

    def _send_message(self) -> None:
        if self._lifecycle in (LifecycleState.SHUTTING_DOWN, LifecycleState.CLOSED):
            log.warning("SEND_BLOCKED lifecycle=%s", self._lifecycle)
            self.show_toast("Application is shutting down", Colors.WARNING)
            return
        import uuid

        _sid = uuid.uuid4().hex[:8]
        log.info("SEND_START pasted_path=%s", self._pasted_image_path)
        log.info("SEND_REQUEST_ID=%s", _sid)

        if self._sending:
            log.info("SEND_IGNORED_ALREADY_SENDING sid=%s", _sid)
            return
        self._sending = True
        self._update_input_bar_visibility("generating")
        log.info("SEND_STARTED sid=%s", _sid)

        text = (self._entry.value or "").strip()
        if not text and not self._pasted_image_path:
            self._sending = False
            log.info("SEND_FINISHED sid=%s reason=empty", _sid)
            return

        log.info("SEND_TEXT_LENGTH sid=%s len=%d", _sid, len(text))

        if not text and self._pasted_image_path:
            text = "Describe this image"
            log.info("SEND_DEFAULT_TEXT_FOR_IMAGE sid=%s", _sid)

        self._entry.value = ""
        self._entry.update()

        _image_b64: str | None = None
        log.info("SEND_IMAGE_PATH sid=%s path=%s", _sid, self._pasted_image_path)
        if self._pasted_image_path:
            img_path = Path(self._pasted_image_path)
            log.info("SEND_IMAGE_EXISTS sid=%s exists=%s", _sid, img_path.exists())
            log.info("SEND_IMAGE_FILE_SIZE sid=%s bytes=%d", _sid, img_path.stat().st_size if img_path.exists() else 0)
            log.info("SEND_IMAGE_ENCODING_START sid=%s", _sid)
            try:
                import base64

                with open(self._pasted_image_path, "rb") as fh:
                    raw = fh.read()
                _image_b64 = base64.b64encode(raw).decode()
                log.info("SEND_IMAGE_ENCODING_FINISHED sid=%s", _sid)
                log.info("SEND_IMAGE_BASE64_LENGTH sid=%s len=%d", _sid, len(_image_b64))
            except Exception as exc:
                log.warning("Failed to encode pasted image: %s\n%s", exc, traceback.format_exc())
                self.show_toast("Failed to process image.", Colors.ERROR)
                self._sending = False
                log.info("SEND_FAILED sid=%s reason=encoding_error", _sid)
                return

        log.info(
            "TOKEN_CHECK_START sid=%s text_len=%d base64_len=%d", _sid, len(text), len(_image_b64) if _image_b64 else 0
        )
        _tokens = count_tokens(text)
        log.info(
            "TOKEN_CHECK_RESULT sid=%s tokens=%d max=%d text_len=%d base64_len=%d",
            _sid,
            _tokens,
            self._cfg.tokens.max_context,
            len(text),
            len(_image_b64) if _image_b64 else 0,
        )
        if _tokens > self._cfg.tokens.max_context:
            log.info("TOKEN_LIMIT_EXCEEDED sid=%s tokens=%d max=%d", _sid, _tokens, self._cfg.tokens.max_context)
            self.show_toast("Message exceeds token limit", Colors.ERROR)
            self._sending = False
            log.info("SEND_FAILED sid=%s reason=token_limit", _sid)
            return
        log.info("TOKEN_LIMIT_OK sid=%s tokens=%d max=%d", _sid, _tokens, self._cfg.tokens.max_context)

        with self._gen_lock:
            if self._generating:
                self._sending = False
                log.info("SEND_FINISHED sid=%s reason=already_generating", _sid)
                return
            self._generating = True

        self._stop.clear()
        self._entry.disabled = True
        self._btn_send.disabled = True
        self._btn_stop.disabled = False
        self._btn_clear_chat.disabled = True
        self._set_status(AppStatus.GENERATING, Colors.WARNING)

        _attach_path: str | None = None
        _file_type: str | None = None
        if self._pasted_image_path:
            ext = Path(self._pasted_image_path).suffix.lower()
            _image_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
            if ext in _image_exts:
                _file_type = "image"
                src = Path(self._pasted_image_path)
                dst = self._paste_dir / f"attach_{int(time.time() * 1000)}_{src.name}"
                if src.resolve() != dst.resolve():
                    import shutil

                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))
                    _attach_path = str(dst)
                    log.info("SEND_ATTACHMENT_COPIED src=%s dst=%s", src, dst)
                else:
                    _attach_path = str(src)
                    log.info("SEND_ATTACHMENT_ALREADY_PERSISTED path=%s", _attach_path)
                log.info("CHAT_ATTACHMENT_CREATED path=%s type=%s", _attach_path, _file_type)

        user_msg = ChatMessage(
            "You", text, attachment_path=_attach_path, file_type=_file_type, on_edit=self._on_edit_message
        )
        self._chat_list.controls.append(user_msg)
        log.info("SEND_MESSAGE_CREATED sid=%s", _sid)
        self._update_msg_widths()
        try:
            self._page.update()
            log.info("SEND_MESSAGE_RENDERED sid=%s", _sid)
        except Exception as exc:
            log.warning("Failed to update page after send: %s", exc)

        chat_id = self._active_chat_id
        if chat_id is None:
            ws = self._workspaces.get_active()
            if ws is not None:
                chat_id = self._chats.get_default_chat(ws.id)
                self._active_chat_id = chat_id
        if chat_id is not None:
            self._db.chat.save_for_chat(
                chat_id, MessageRole.USER, text, attachment_path=_attach_path, file_type=_file_type
            )
            log.info("SEND_MESSAGE_ADDED sid=%s", _sid)

        if self._pasted_image_path:
            log.info("SEND_CLEARING_IMAGE path=%s", self._pasted_image_path)
            self._clear_pasted_image()

        selected_model = self._model_sel.value if hasattr(self, "_model_sel") else None
        log.info("SEND_REQUEST_STARTED")
        log.info("ACTIVE_MODEL_AT_SEND selected_model=%s", selected_model)
        log.info("SEND_SUBMIT text_len=%d has_image=%s", len(text), _image_b64 is not None)
        log.info("THREADPOOL_SUBMIT_START")
        _fut = self._safe_submit_llm(self._generate_response, text, selected_model, _image_b64)
        log.info("THREADPOOL_SUBMIT_SUCCESS")
        _fut.add_done_callback(
            lambda _f: (
                (
                    log.info("THREADPOOL_SUBMIT_SUCCESS")
                    if _f.exception() is None
                    else log.error("THREADPOOL_SUBMIT_FAILED: %s\n%s", _f.exception(), traceback.format_exc())
                )
                if _f is not None
                else None
            )
        )
        self._sending = False
        log.info("SEND_FINISHED sid=%s reason=submitted", _sid)

    def _generate_response(self, user_text: str, selected_model: str | None, image_b64: str | None = None) -> None:
        _gen_t0 = time.monotonic()
        log.info("GENERATE_RESPONSE_START")
        log.info("GENERATE_RESPONSE_THREAD thread=%s", threading.current_thread().name)
        log.info("GENERATE_RESPONSE_TEXT_LENGTH len=%d", len(user_text))
        log.info("GENERATE_RESPONSE_HAS_IMAGE param_has=%s", image_b64 is not None)
        log.info("GENERATE_RESPONSE_SELECTED_MODEL selected=%s", selected_model)
        _cid = self._active_chat_id
        log.info("GENERATE_RESPONSE_CHAT_ID chat_id=%s", _cid)
        try:
            # ── Phase 1: Base model from immutable request context ──
            base_model = selected_model if selected_model else self._mm.get_active()
            log.info("ROUTER_INPUT_MODEL model=%s", base_model)
            _user_chose = self._user_explicitly_selected_model

            # ── Phase 2: Decide which model to use (NO global state mutation) ──
            if image_b64 is not None:
                model_name = base_model
                log.info("ROUTER_OUTPUT_MODEL model=%s reason=image_request", model_name)
            elif _user_chose:
                model_name = base_model
                log.info("ROUTER_OUTPUT_MODEL model=%s reason=user_explicit_selection", model_name)
            else:
                decision = self._router.route(user_text, fallback_model=base_model)
                model_name = decision.chosen_model
                log.info("ROUTER_OUTPUT_MODEL model=%s reason=%s", model_name, decision.reason)

            # ── Phase 3: Vision safety net ──
            if image_b64 is not None and not self._mm.is_vision_capable(model_name):
                log.warning("VISION_FALLBACK_NEEDED model=%s image_present=True", model_name)
                fallback_candidates: list[str] = []
                if selected_model:
                    fallback_candidates.append(selected_model)
                fallback_candidates.extend(self._mm.get_available())
                for candidate in fallback_candidates:
                    if self._mm.is_vision_capable(candidate):
                        model_name = candidate
                        log.info("VISION_FALLBACK_APPLIED model=%s", model_name)
                        break
                else:
                    log.warning("VISION_FALLBACK_FAILED no_vision_capable_model_found")
                    self._page.run_thread(
                        lambda: self.show_toast(
                            "No vision-capable model available. Select a vision model and try again.",
                            Colors.ERROR,
                        )
                    )
                    self._page.run_thread(self._reset_input_state)
                    return

            log.info("FINAL_MODEL_USED model=%s", model_name)

            if model_name != base_model:
                self._set_status(f"Routed: {model_name}", Colors.PRIMARY)

            ai_msg = ChatMessage(
                f"{APP_NAME} ({model_name})", on_copy=self._on_copy_message, on_change_model=self._on_change_model
            )

            self._page.run_thread(
                lambda: (
                    self._chat_list.controls.append(ai_msg),
                    log.info("ASSISTANT_WIDGET_ADDED"),
                    self._page.update(),
                    log.info("ASSISTANT_WIDGET_RENDERED"),
                )
            )
            self._page.run_thread(lambda: self._agent_feed.add_event(f"Model: {model_name}", Colors.PRIMARY))

            relevant = self._memory.search(user_text, limit=3)
            facts_ctx = (
                "\n".join(f"- {r.key}: {r.value} (score {r.score:.2f})" for r in relevant)
                if relevant
                else "No relevant facts found."
            )
            system_prompt = (
                "You are a multilingual AI assistant. "
                "You ALWAYS reply in the same language the user writes in. "
                "You never refuse any language. "
                "You never claim you cannot understand or reply in a language. "
                "You never switch to English unless the user does first. "
                "Arabic, Persian, Urdu, Hebrew, Turkish, Kurdish, Pashto, Sindhi, "
                "Chinese, Japanese, Korean, Russian, Hindi, Bengali, Tamil, Thai, "
                "Vietnamese, Malay, Indonesian, Swahili, Hausa, and ALL other languages "
                "are fully supported — you speak them fluently. "
                "If the user writes in multiple languages, follow their lead."
                f"\n\nRelevant facts about the user:\n{facts_ctx}"
            )

            chat_id = self._active_chat_id
            history = [
                m.to_api_dict()
                for m in (
                    self._db.chat.get_by_token_budget(chat_id, self._cfg.tokens.history_window)
                    if chat_id is not None
                    else self._db.chat.get_recent_by_token_budget(self._cfg.tokens.history_window)
                )
            ]

            _chunk_count = 0
            _vision_sent = image_b64 is not None

            def on_chunk(chunk: str) -> None:
                nonlocal _chunk_count
                _chunk_count += 1
                ai_msg.append_chunk(chunk)
                if _chunk_count == 1:
                    log.info("STREAM_CHUNK_RECEIVED first_chunk_len=%d", len(chunk))
                    self._page.run_thread(
                        lambda: (
                            self._agent_badge.set_status(AgentStatus.STREAMING),
                            self._agent_info.show(model_name),
                            self._agent_feed.add_event("Streaming started", Colors.SUCCESS),
                        )
                    )

            def on_done() -> None:
                if _vision_sent:
                    log.info("VISION_RESPONSE_RECEIVED")
                elapsed = time.monotonic() - _gen_t0

                def finalize_and_reset() -> None:
                    response = ai_msg.finalize(elapsed_s=elapsed)
                    log.info("MODEL_RESPONSE_RECEIVED len=%d", len(response) if response else 0)
                    log.info("MODEL_RESPONSE_LENGTH len=%d", len(response) if response else 0)
                    if response and len(response.strip()) >= MIN_RESPONSE_LENGTH:
                        cid = self._active_chat_id
                        if cid is not None:
                            self._db.chat.save_for_chat(cid, MessageRole.ASSISTANT, response)
                            log.info("DB_SAVE_ASSISTANT_MESSAGE chat_id=%s", cid)
                    self._agent_badge.set_status(AgentStatus.COMPLETED)
                    self._agent_info.hide()
                    self._agent_feed.add_event(f"Completed in {elapsed:.1f}s", Colors.TEXT_HIGH)
                    self._check_memory_pipeline()
                    self._reset_input_state()

                self._page.run_thread(finalize_and_reset)

            def on_error(msg: str) -> None:
                if _vision_sent:
                    log.info("VISION_REQUEST_FAILED reason=%s", msg)

                def error_and_reset(m: str) -> None:
                    ai_msg.append_chunk(f"\n\n❌ **Error:** {m}")
                    self._agent_badge.set_status(AgentStatus.ERROR)
                    self._agent_info.hide()
                    self._agent_feed.add_event(f"Error: {m}", Colors.ERROR)
                    self._reset_input_state()

                self._page.run_thread(lambda m=msg: error_and_reset(m))

            log.info(
                "VISION_REQUEST_CREATED image_b64_present=%s image_b64_len=%d",
                image_b64 is not None,
                len(image_b64) if image_b64 else 0,
            )

            provider = "api" if self._mm.is_api_model(model_name) else "ollama"
            log.info("MODEL_REQUEST_START")
            log.info("MODEL_PROVIDER provider=%s", provider)
            log.info("MODEL_NAME model=%s", model_name)
            log.info("MODEL_REQUEST_TEXT_LENGTH len=%d", len(user_text))
            log.info("MODEL_REQUEST_HAS_IMAGE has=%s", image_b64 is not None)
            log.info("MODEL_REQUEST_IMAGE_COUNT count=%d", 1 if image_b64 else 0)
            log.info("VISION_REQUEST_SENT model=%s image_len=%d", model_name, len(image_b64) if image_b64 else 0)

            try:
                log.info("ABOUT_TO_CALL_STREAM_CHAT")
                if self._mm.is_api_model(model_name):
                    entry = self._mm.get_registry_entry(model_name)
                    if entry:
                        client = ApiModelClient(
                            api_url=entry.api_url,
                            api_key=entry.api_key,
                            model_name=entry.base_model,
                            api_password=entry.api_password,
                            temperature=self._cfg.ollama.temperature,
                        )
                        _payload_size = len(user_text) + (len(image_b64) if image_b64 else 0)
                        log.info("MODEL_REQUEST_PAYLOAD_SIZE bytes=%d", _payload_size)
                        try:
                            client.stream_chat(
                                system_prompt=system_prompt,
                                history=history,
                                user_message=user_text,
                                image_base64=image_b64,
                                on_chunk=on_chunk,
                                on_done=on_done,
                                on_error=on_error,
                                stop_event=self._stop,
                            )
                        finally:
                            client.close()
                    else:
                        on_error(f"Registry entry for API model '{model_name}' not found.")
                else:
                    _payload_size = len(user_text) + (len(image_b64) if image_b64 else 0)
                    log.info("MODEL_REQUEST_PAYLOAD_SIZE bytes=%d", _payload_size)
                    self._ollama.stream_chat(
                        model=model_name,
                        system_prompt=system_prompt,
                        history=history,
                        user_message=user_text,
                        image_base64=image_b64,
                        on_chunk=on_chunk,
                        on_done=on_done,
                        on_error=on_error,
                        stop_event=self._stop,
                    )
                log.info("STREAM_CHAT_RETURNED")
            except Exception as exc:
                log.exception("STREAM_CHAT_EXCEPTION")
                log.info("MODEL_REQUEST_EXCEPTION")
                self._page.run_thread(lambda m=str(exc): on_error(m))
        except Exception:
            log.exception("GENERATE_RESPONSE_EXCEPTION")
            self._page.run_thread(lambda: self._reset_input_state())

    # ------------------------------------------------------------------
    # Stop generation
    # ------------------------------------------------------------------

    def _stop_generation(self) -> None:
        self._stop.set()
        with self._gen_lock:
            self._generating = False
        self._agent_badge.set_status(AgentStatus.CANCELLED)
        self._agent_info.hide()
        self._agent_feed.add_event("Generation cancelled by user", Colors.WARNING)
        self._reset_input_state()

    def _reset_input_state(self) -> None:
        with self._gen_lock:
            self._generating = False
        self._update_input_bar_visibility("idle")
        self._entry.value = ""
        self._entry.disabled = False
        self._btn_send.disabled = False
        self._btn_stop.disabled = True
        self._btn_clear_chat.disabled = False
        self._set_status(AppStatus.READY, Colors.SUCCESS)
        try:
            self._page.update()
        except Exception as exc:
            log.warning("Failed to reset input state: %s", exc)

    # ------------------------------------------------------------------
    # Memory pipeline
    # ------------------------------------------------------------------

    def _check_memory_pipeline(self) -> None:
        if self._pipeline_running:
            return
        chat_id = self._active_chat_id
        if chat_id is None:
            return
        total = self._db.chat.total_tokens_for_chat(chat_id)
        if total <= self._cfg.tokens.max_active:
            return
        self._pipeline_running = True
        log.info("Token budget exceeded — running memory pipeline (chat=%s)", chat_id)
        self._safe_submit(self._run_memory_pipeline, chat_id)

    def _run_memory_pipeline(self, chat_id: int | None = None) -> None:
        try:
            if chat_id is not None:
                messages = self._db.chat.get_by_token_budget(chat_id, self._cfg.tokens.max_active)
            else:
                messages = self._db.chat.get_recent_by_token_budget(self._cfg.tokens.max_active)
            self._summarizer.run_pipeline(messages, chat_id=chat_id)
            self._page.run_thread(self._refresh_memory_panel)
        except Exception as exc:
            log.error("Memory pipeline error: %s\n%s", exc, traceback.format_exc())
            msg = f"Memory pipeline error: {exc}"
            self._page.run_thread(lambda: self.show_toast(msg, Colors.ERROR))
        finally:
            self._pipeline_running = False

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def show_error_recovery(self, title: str, details: str) -> None:
        """Show a modal error dialog with 'Reload' and 'Close' buttons."""

        def _reload(_e: ft.ControlEvent | None = None) -> None:
            try:
                dlg.open = False
                dlg.update()
            except Exception:
                log.debug("Error recovery dialog close ignored")
            try:
                self._chat_list.controls.clear()
                self._chat_list.update()
            except Exception:
                log.debug("Chat list clear during recovery ignored")
            self._set_status(AppStatus.READY, Colors.SUCCESS)
            self._safe_submit(self._bootstrap)

        async def _close_app_async() -> None:
            try:
                dlg.open = False
                await dlg.update_async()
            except Exception:
                log.debug("Async error recovery dialog close ignored")
            try:
                await self._page.window.close()
            except Exception:
                log.debug("Async window close during recovery ignored")

        def _close_app(_e: ft.ControlEvent | None = None) -> None:
            asyncio.create_task(_close_app_async())

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.ERROR_OUTLINE, color=Colors.ERROR, size=22),
                    ft.Text(title, color=Colors.ERROR, weight=ft.FontWeight.BOLD),
                ],
                spacing=8,
            ),
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(details, color=Colors.TEXT_HIGH2, size=13, selectable=True),
                        ft.Text(
                            "You can reload the app to recover from this error.",
                            color=Colors.TEXT_MUTED,
                            size=11,
                            italic=True,
                        ),
                    ],
                    spacing=8,
                ),
                width=400,
                padding=ft.Padding(top=4, bottom=4),
            ),
            actions=[
                ft.TextButton("Close App", on_click=_close_app, style=ft.ButtonStyle(color=Colors.ERROR)),
                ft.ElevatedButton(
                    "Reload",
                    icon=ft.Icons.REFRESH,
                    on_click=_reload,
                    style=ft.ButtonStyle(bgcolor=Colors.PRIMARY, color=Colors.TEXT_HIGH),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.show_dialog(dlg)

    def show_toast(self, message: str, color: str = Colors.SUCCESS) -> None:
        """Show a transient SnackBar notification (thread-safe)."""

        def _show() -> None:
            try:
                if self._page is None or self._page.overlay is None:
                    log.info("TOAST_FAILED reason=no_page_or_overlay")
                    return
                log.info("TOAST_REQUEST msg_len=%d", len(message))
                if self._snack is None:
                    self._snack = ft.SnackBar(
                        ft.Text(""),
                        duration=4000,
                        open=True,
                        behavior=ft.SnackBarBehavior.FLOATING,
                    )
                    self._page.overlay.append(self._snack)
                    log.info("TOAST_CREATED")
                self._snack.content = ft.Text(message, color=Colors.TEXT_HIGH, size=13)
                self._snack.bgcolor = color
                self._snack.open = True
                self._page.update()
                log.info("TOAST_DISPLAYED")
            except Exception as exc:
                log.warning("TOAST_FAILED exc=%s\n%s", exc, traceback.format_exc())

        try:
            self._page.run_thread(_show)
            log.info("TOAST_THREAD ok")
        except RuntimeError:
            log.warning("TOAST_THREAD failed")

    def _load_history(self) -> None:
        t0 = time.monotonic()
        self._chat_list.controls.clear()
        chat_id = self._active_chat_id
        if chat_id is None:
            ws = self._workspaces.get_active()
            if ws is not None:
                chat_id = self._chats.get_default_chat(ws.id)
                self._active_chat_id = chat_id
        if chat_id is None:
            try:
                self._chat_list.update()
            except Exception:
                log.debug("Chat list update on empty load ignored")
            return
        messages = self._db.chat.get_by_token_budget(chat_id, self._cfg.tokens.history_window)
        for msg in messages:
            sender = "You" if msg.role == MessageRole.USER else APP_NAME
            cm = ChatMessage(
                sender,
                msg.content,
                attachment_path=msg.attachment_path,
                file_type=msg.file_type,
                on_copy=self._on_copy_message,
                on_edit=self._on_edit_message,
                on_change_model=self._on_change_model,
            )
            self._chat_list.controls.append(cm)
        self._update_msg_widths()
        try:
            self._chat_list.update()
        except Exception as exc:
            log.warning("Failed to update chat list: %s", exc)
        log.info("TIMING _load_history: %.3fs (%d msgs)", time.monotonic() - t0, len(self._chat_list.controls))

    def _refresh_chat_sidebar(self) -> None:
        ws = self._workspaces.get_active()
        if ws is None:
            return
        chats = self._chats.get_chats(ws.id)
        self._chat_sidebar.refresh(chats, self._active_chat_id)

    def _refresh_memory_panel(self) -> None:
        try:
            facts = self._memory.get_all_facts()
            chat_id = self._active_chat_id
            chat_facts = []
            summaries = []
            if chat_id is not None:
                chat_facts = self._db.chat_facts.get_all(chat_id)
                summaries = self._db.chat_summaries.get_recent(chat_id)
            self._memory_panel.refresh(facts, summaries, chat_facts)
        except Exception as exc:
            log.warning("Failed to refresh memory panel: %s", exc)

    _STATUS_TO_AGENT = {
        AppStatus.READY: AgentStatus.IDLE,
        AppStatus.GENERATING: AgentStatus.STREAMING,
        AppStatus.ERROR: AgentStatus.ERROR,
        AppStatus.LOADING: AgentStatus.THINKING,
        AppStatus.INDEXING: AgentStatus.THINKING,
        AppStatus.CREATING: AgentStatus.THINKING,
        AppStatus.ROUTING: AgentStatus.THINKING,
    }

    def _set_status(self, status: AppStatus | str, color: str) -> None:
        def update() -> None:
            self._status.value = f"STATUS: {status}"
            self._status.color = color
            agent_s = self._STATUS_TO_AGENT.get(status)
            if agent_s is not None:
                self._agent_badge.set_status(agent_s)
            try:
                self._status.update()
            except Exception as exc:
                log.warning("Failed to update status: %s", exc)

        import threading as _th

        if _th.current_thread() is _th.main_thread():
            update()
        else:
            self._page.run_thread(update)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _retheme_existing_widgets(self) -> None:
        """Re-apply theme colors to ALL existing UI widgets after theme switch."""
        # ── Page ──
        self._page.bgcolor = Colors.BG_PAGE

        # ── Toolbar ──
        self._toolbar.bgcolor = Colors.BG_SURFACE
        self._toolbar.border = ft.border.Border(bottom=ft.BorderSide(1, Colors.BORDER_DIVIDER))
        self._btn_hamburger.icon_color = Colors.TEXT_MEDIUM
        self._btn_settings.icon_color = Colors.TEXT_MEDIUM
        self._btn_model_mgr.icon_color = Colors.TEXT_MEDIUM
        self._btn_clear_chat.icon_color = Colors.TEXT_MUTED2
        self._overflow_menu.icon_color = Colors.TEXT_MUTED
        self._workspace_sel.bgcolor = Colors.BG_SURFACE
        self._workspace_sel.border_color = Colors.BORDER_INPUT
        self._app_logo.bgcolor = ft.Colors.with_opacity(0.08, Colors.BG_SURFACE)

        # ── Model selector ──
        self._model_sel.bgcolor = Colors.BG_SURFACE

        # ── Chat area ──
        self._chat_area.bgcolor = Colors.BG_CHAT

        # ── Agent feed ──
        self._agent_feed_container.bgcolor = Colors.BG_SURFACE2
        self._agent_feed_container.border = ft.border.Border(bottom=ft.BorderSide(1, Colors.BORDER_DIVIDER))

        # ── Input area ──
        self._input_inner.bgcolor = Colors.BG_SURFACE
        self._input_inner.border = ft.BorderSide(1, Colors.BORDER_DIVIDER)
        self._entry.bgcolor = Colors.BG_USER_MSG
        self._entry.border_color = Colors.BORDER_INPUT
        self._entry.focused_border_color = Colors.BORDER_FOCUS
        self._btn_send.bgcolor = Colors.PRIMARY
        self._btn_send.icon_color = Colors.TEXT_HIGH
        self._btn_stop.bgcolor = Colors.ERROR
        self._btn_stop.icon_color = Colors.TEXT_HIGH
        self._btn_mic.icon_color = Colors.TEXT_MUTED2
        self._btn_paste_img.icon_color = Colors.TEXT_MUTED2
        self._btn_attach.icon_color = Colors.TEXT_MUTED2

        # ── Components ──
        self._chat_sidebar.retheme()
        self._waveform.retheme()
        self._rec_indicator.retheme()
        self._agent_badge.retheme()
        self._agent_info.retheme()
        self._memory_panel.retheme()

        # ── Chat messages ──
        for control in self._chat_list.controls:
            if isinstance(control, ChatMessage):
                control.retheme()

        try:
            self._page.update()
        except Exception:
            pass
        try:
            self._page.update()
        except Exception:
            pass

    def _on_settings_changed(self, event: SettingsChangedEvent) -> None:
        if event.section in ("appearance", "*"):
            us = self._settings.current if self._settings else None
            if us:
                mode = us.appearance.theme
                apply_flet_theme(self._page, mode)
                self._page.bgcolor = Colors.BG_PAGE
                self._page.window.width = max(1000, us.appearance.window_width)
                self._page.window.height = max(600, us.appearance.window_height)
                self._retheme_existing_widgets()
                if mode == "system":
                    self._start_os_theme_poller()
        try:
            self._page.update()
        except Exception:
            log.debug("Page update on settings apply ignored")

    # ------------------------------------------------------------------
    # Responsive layout
    # ------------------------------------------------------------------

    def _calc_col_width(self) -> int:
        w = self._page.width or 1280
        sidebar_w = 240 if self._sidebar_visible else 0
        available = max(400, w - sidebar_w - 24)
        if w <= 1366:
            return min(680, available)
        return min(800, available)

    def _calc_msg_width(self) -> int:
        col_w = self._calc_col_width()
        return max(360, min(700, int(col_w * 0.90)))

    def _update_msg_widths(self) -> None:
        width = self._calc_msg_width()
        for ctrl in self._chat_list.controls:
            if isinstance(ctrl, ChatMessage):
                ctrl.set_message_width(width)

    def _on_page_resize(self, _e: ft.ControlEvent | None = None) -> None:
        try:
            self._chat_sidebar.visible = self._sidebar_visible
            col_w = self._calc_col_width()
            if self._chat_col_ref.current:
                self._chat_col_ref.current.width = col_w
            self._page.update()
        except Exception as exc:
            log.warning("Failed to resize: %s", exc)

    # ------------------------------------------------------------------
    # Image paste with immediate preview
    # ------------------------------------------------------------------

    def _show_image_preview(self, path: str) -> None:
        log.info("IMAGE_PREVIEW_START path=%s thread=%s", path, threading.current_thread().name)
        if not path or not Path(path).is_file():
            log.warning("Image preview: file not found: %s", path)
            self.show_toast("Selected image could not be found.", Colors.ERROR)
            return
        self._pasted_image_path = path
        log.info("IMAGE_PREVIEW_PATH_SET path=%s", self._pasted_image_path)
        try:
            import base64  # noqa: I001 — lazy import
            from PIL import Image  # noqa: I001 — lazy import

            with Image.open(path) as img:
                img.verify()
            with open(path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode()
            self._img_preview_img.src = f"data:image/png;base64,{b64}"
            self._img_preview.visible = True
            log.info("IMAGE_PREVIEW_VISIBLE visible=%s", self._img_preview.visible)
            log.info("IMAGE_PREVIEW_SRC_LENGTH src_len=%d", len(self._img_preview_img.src or ""))
        except Exception as exc:
            log.warning("Failed to load pasted image: %s\n%s", exc, traceback.format_exc())
            self._pasted_image_path = None
            self.show_toast("Failed to process image.", Colors.ERROR)
            return
        log.info(
            "IMAGE_PREVIEW_UPDATE visible=%s src_len=%s",
            self._img_preview.visible,
            len(self._img_preview_img.src or ""),
        )
        try:
            self._page.update()
            log.info("IMAGE_PREVIEW_PAGE_UPDATE_OK")
        except Exception:
            log.exception("IMAGE_PREVIEW_PAGE_UPDATE_FAILED")

    def _clear_pasted_image(self) -> None:
        self._paste_version += 1
        log.info("ATTACHMENT_REMOVE_CLICKED paste_version=%d", self._paste_version)
        log.info("ATTACHMENT_STATE_BEFORE_CLEAR path=%s", self._pasted_image_path)
        self._set_status("Image removed", Colors.WARNING)
        self._pasted_image_path = None
        self._img_preview.visible = False
        self._img_preview_img.src = ""
        log.info(
            "ATTACHMENT_STATE_AFTER_CLEAR path=%s img_src_len=%d",
            self._pasted_image_path,
            len(self._img_preview_img.src or ""),
        )
        try:
            self._page.update()
            log.info("ATTACHMENT_PREVIEW_REMOVED")
            log.info("ATTACHMENT_UI_REFRESHED")
        except Exception as exc:
            log.warning("Failed to update page after hide preview: %s\n%s", exc, traceback.format_exc())

    def _zoom_image_preview(self) -> None:
        if not self._pasted_image_path:
            return
        p = Path(self._pasted_image_path)
        if not p.is_file():
            self.show_toast("Image file no longer available", Colors.ERROR)
            return
        try:
            import subprocess

            subprocess.Popen(["explorer", str(p.resolve())])
        except Exception as exc:
            log.warning("Failed to open image: %s\n%s", exc, traceback.format_exc())
            self.show_toast("Open image manually: " + str(p), Colors.PRIMARY)

    def _paste_clipboard_image(self) -> None:
        log.info("PASTE_REQUESTED thread=%s", threading.current_thread().name)
        self._paste_version += 1
        self._safe_submit(self._paste_clipboard_bg)
        log.info("PASTE_BG_SUBMITTED")

    def _paste_clipboard_bg(self) -> None:
        t0 = time.monotonic()
        _paste_ver = self._paste_version
        log.info("PASTE_BG_START thread=%s version=%d", threading.current_thread().name, _paste_ver)
        path: str | None = None
        _pil_err: str | None = None
        try:
            from PIL import Image, ImageGrab

            img = ImageGrab.grabclipboard()
            if img is not None:
                log.info("PASTE_BG_IMAGE_FOUND size=%s", getattr(img, "size", None))
                if isinstance(img, Image.Image):
                    ts = int(time.time() * 1000)
                    path = str(self._paste_dir / f"paste_{ts}.png")
                    try:
                        img.save(path)
                    except Exception as exc:
                        log.warning("Paste PIL save failed: %s\n%s", exc, traceback.format_exc())
                        _pil_err = "Failed to save pasted image."
                    if _pil_err is None:
                        fp = Path(path)
                        log.info("PASTE_BG_FILE_SAVED path=%s", path)
                        log.info("PASTE_BG_FILE_SIZE bytes=%d", fp.stat().st_size)
                        log.info("PASTE_BG_FILE_EXISTS exists=%s", fp.exists())
                elif isinstance(img, list):
                    for f in img:
                        if isinstance(f, str) and f.lower().endswith((
                            ".png",
                            ".jpg",
                            ".jpeg",
                            ".gif",
                            ".bmp",
                            ".webp",
                        )):
                            p = Path(f)
                            if p.is_file():
                                path = f
                                log.info("PASTE_BG_FILE_SAVED path=%s", path)
                                log.info("PASTE_BG_FILE_SIZE bytes=%d", p.stat().st_size)
                                log.info("PASTE_BG_FILE_EXISTS exists=%s", True)
                                break
        except ImportError:
            log.warning("PIL not available for clipboard paste")
            _pil_err = "Failed to paste image."
        except Exception as exc:
            log.warning("Paste PIL failed: %s\n%s", exc, traceback.format_exc())
            _pil_err = "Failed to paste image."

        if _pil_err is None and path is None:
            try:
                import io
                import struct

                import win32clipboard
                import win32con

                win32clipboard.OpenClipboard()
                try:
                    if win32clipboard.IsClipboardFormatAvailable(win32con.CF_DIB):
                        data = win32clipboard.GetClipboardData(win32con.CF_DIB)
                        if data and len(data) > 40:
                            hdr = struct.pack("<HIHHI", 0x4D42, len(data) + 14, 0, 0, 14)
                            img = Image.open(io.BytesIO(hdr + data))
                            log.info("PASTE_BG_IMAGE_FOUND size=%s", getattr(img, "size", None))
                            ts = int(time.time() * 1000)
                            path = str(self._paste_dir / f"paste_{ts}.png")
                            try:
                                img.save(path)
                            except Exception as exc:
                                log.warning("Paste DIB save failed: %s\n%s", exc, traceback.format_exc())
                                _pil_err = "Failed to save pasted image."
                            if _pil_err is None:
                                fp = Path(path)
                                log.info("PASTE_BG_FILE_SAVED path=%s", path)
                                log.info("PASTE_BG_FILE_SIZE bytes=%d", fp.stat().st_size)
                                log.info("PASTE_BG_FILE_EXISTS exists=%s", fp.exists())
                finally:
                    win32clipboard.CloseClipboard()
            except ImportError:
                log.debug("Paste: win32clipboard not available")
            except Exception as exc:
                log.warning("Paste win32 failed: %s\n%s", exc, traceback.format_exc())
                _pil_err = "Failed to paste image."

        if _pil_err is not None:
            self.show_toast(_pil_err, Colors.ERROR)
            log.info("PASTE_BG_COMPLETED elapsed=%.3fs result=error", time.monotonic() - t0)
            return

        if path is None:
            log.info("PASTE_BG_NO_IMAGE")
            log.info("PASTE_BG_COMPLETED elapsed=%.3fs result=no_image", time.monotonic() - t0)
            return

        log.info("PASTE_BG_PREVIEW_CALLED path=%s version=%d", path, _paste_ver)
        if self._paste_version != _paste_ver:
            log.info("PASTE_BG_STALE_VERSION expected=%d actual=%d — skipping preview", _paste_ver, self._paste_version)
            log.info("PASTE_BG_COMPLETED elapsed=%.3fs result=stale", time.monotonic() - t0)
            return
        self._page.run_thread(lambda p=path: self._show_image_preview(p))
        log.info("PASTE_BG_COMPLETED elapsed=%.3fs result=success", time.monotonic() - t0)

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def _on_keyboard(self, e: ft.KeyboardEvent) -> None:
        if e.key == "Escape":
            self._page.run_task(self._entry.focus)
        elif e.ctrl and e.key == "N":
            self._on_chat_create()
        elif e.ctrl and e.key == "E":
            self._page.run_task(self._entry.focus)
        elif e.ctrl and e.key == "B":
            self._toggle_sidebar(None)
        elif e.ctrl and e.key == "V":
            self._paste_clipboard_image()
        elif e.ctrl and e.key == "L":
            self._on_clear_chat()
        elif e.ctrl and e.key == "S":
            self._on_settings(None)

    def _on_edit_message(self, text: str) -> None:
        self._entry.value = text
        self._entry.update()
        self._page.run_task(self._entry.focus)

    def _on_copy_message(self, text: str, result_cb: Callable[[bool], None] | None = None) -> None:
        ok = copy_to_clipboard(text)
        if result_cb:
            result_cb(ok)
        if not ok:
            self.show_toast("Copy failed", Colors.ERROR)

    def _on_change_model(self) -> None:
        self.show_toast("Change model dialog not implemented yet", Colors.WARNING)

    def _toggle_activity_feed(self) -> None:
        self._agent_feed_container.visible = not self._agent_feed_container.visible
        try:
            self._agent_feed_container.update()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _on_close(self, _e: ft.ControlEvent | None = None) -> None:
        log.info("Application closing...")
        self._lifecycle = LifecycleState.SHUTTING_DOWN
        self._stop.set()

        # ── Phase 1: Stop accepting new work ──
        self._pool.shutdown(wait=False)
        self._llm_pool.shutdown(wait=False)

        # ── Phase 2: Cleanup non-page resources off the UI thread ──
        def _cleanup() -> None:
            errors: list[str] = []
            for label, fn in (
                ("Memory save", lambda: self._memory.save_index()),
                ("Memory close", lambda: self._memory.close()),
                ("Model creator", lambda: self._creator.close()),
                ("Mic controller", lambda: self._mic_ctl.close()),
                ("AudioManager", lambda: AudioManager.get_instance().release_all()),
                ("Registry dialog", lambda: self._registry_dlg.close()),
                ("Creator dialog", lambda: self._creator_dlg.close()),
                ("Database", lambda: self._db.close()),
                ("Ollama client", lambda: self._ollama.close()),
            ):
                try:
                    fn()
                except Exception as exc:
                    errors.append(f"{label}: {exc}")
            for err in errors:
                log.warning("Shutdown cleanup error: %s", err)
            log.info("Non-page cleanup complete (errors=%d)", len(errors))
            # Signal the UI thread that cleanup is done
            if not errors:
                self._page.run_thread(self._on_cleanup_complete)

        threading.Thread(target=_cleanup, daemon=True).start()

    def _on_cleanup_complete(self) -> None:
        """Called on the UI thread after non-page cleanup finishes.

        Sets CLOSED state and destroys the session.  This two-phase
        approach avoids ``RuntimeError: An attempt to fetch destroyed
        session`` because ``window.destroy()`` is the very last call
        and nothing touches ``page`` afterward.
        """
        self._lifecycle = LifecycleState.CLOSED
        log.info("Cleanup complete — destroying window")
        try:
            self._page.run_task(self._page.window.destroy)
        except RuntimeError as exc:
            log.warning("Window destroy skipped (already closed?): %s", exc)

    def _update_input_bar_visibility(self, mode: str) -> None:
        if mode == "idle":
            self._btn_send.visible = True
            self._btn_mic.visible = True
            self._btn_stop.visible = False
        elif mode == "recording":
            self._btn_send.visible = False
            self._btn_mic.visible = True
            self._btn_stop.visible = False
        elif mode == "generating":
            self._btn_send.visible = False
            self._btn_mic.visible = False
            self._btn_stop.visible = True

        elif mode == "stopped":
            self._btn_send.visible = True
            self._btn_mic.visible = False
            self._btn_stop.visible = False

        self._btn_send.update()
        self._btn_mic.update()
        self._btn_stop.update()
