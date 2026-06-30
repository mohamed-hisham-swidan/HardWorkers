"""Settings Center — comprehensive UI for all user-configurable settings categories."""

from __future__ import annotations

import logging
import threading

import flet as ft

from backend.voice.language_service import (
    get_stt_language_options,
    get_voice_languages,
    get_voices_by_language,
)
from backend.voice.tts_engine import TTSEngine
from core.events import EventBus, SettingsChangedEvent
from services.ai.api_client import ApiModelClient
from settings.models import UserSettings
from settings.service import SettingsService
from ui.helpers import Colors, dialog_title

log = logging.getLogger("hard_workers.ui.settings_dialog")


class SettingsDialog:
    """Tabbed settings panel that reads/writes UserSettings via SettingsService."""

    def __init__(
        self,
        page: ft.Page,
        settings_service: SettingsService,
        bus: EventBus | None = None,
    ) -> None:
        self._page = page
        self._svc = settings_service
        self._bus = bus
        self._dlg: ft.AlertDialog | None = None
        self._tabs: ft.Tabs | None = None

        self._txt_fields: dict[str, ft.TextField] = {}
        self._dd_fields: dict[str, ft.Dropdown] = {}
        self._sw_fields: dict[str, ft.Switch] = {}
        self._sl_fields: dict[str, ft.Slider] = {}
        self._provider_test_status: dict[str, ft.Text] = {}
        self._provider_test_btn: dict[str, ft.ElevatedButton] = {}

    # ── Public API ──────────────────────────────────────────────────────────────

    def show(self) -> None:
        self._build_dialog()
        if self._dlg:
            self._page.show_dialog(self._dlg)

    def close(self, _e: ft.ControlEvent | None = None) -> None:
        if self._dlg:
            try:
                self._dlg.open = False
                self._page.update()
            except Exception:
                log.debug("Settings dialog close ignored")

    # ── Dialog construction ─────────────────────────────────────────────────────

    def _build_dialog(self) -> None:
        us = self._svc.current

        tab_labels = [
            ("General", ft.Icons.SETTINGS),
            ("Appearance", ft.Icons.PALETTE),
            ("Models", ft.Icons.MODEL_TRAINING),
            ("Providers", ft.Icons.CLOUD),
            ("Routing", ft.Icons.ALT_ROUTE),
            ("Personalization", ft.Icons.PSYCHOLOGY),
            ("Diagnostics", ft.Icons.HEALTH_AND_SAFETY),
            ("Workspaces", ft.Icons.WORKSPACES),
            ("Performance", ft.Icons.SPEED),
            ("Voice", ft.Icons.MIC),
            ("Security", ft.Icons.SECURITY),
            ("Advanced", ft.Icons.TUNE),
            ("Developer", ft.Icons.CODE),
        ]

        tab_contents = [
            self._build_general_tab(us),
            self._build_appearance_tab(us),
            self._build_models_tab(us),
            self._build_providers_tab(us),
            self._build_routing_tab(us),
            self._build_memory_tab(us),
            self._build_diagnostics_tab(us),
            self._build_workspaces_tab(us),
            self._build_performance_tab(us),
            self._build_voice_tab(us),
            self._build_security_tab(us),
            self._build_advanced_tab(us),
            self._build_developer_tab(us),
        ]

        self._tabs = ft.Tabs(
            content=ft.Column(
                expand=True,
                controls=[
                    ft.TabBar(tabs=[ft.Tab(label=label, icon=icon) for label, icon in tab_labels]),
                    ft.TabBarView(expand=True, controls=tab_contents),
                ],
            ),
            length=len(tab_labels),
            selected_index=0,
            animation_duration=300,
            expand=True,
        )

        self._dlg = ft.AlertDialog(
            modal=True,
            title=dialog_title(
                ft.Icons.SETTINGS, "Settings Center", extra=ft.IconButton(icon=ft.Icons.CLOSE, on_click=self.close)
            ),
            content=ft.Container(
                content=self._tabs,
                width=720,
                height=520,
                padding=10,
            ),
            actions=[
                ft.TextButton(
                    "Reset Defaults",
                    on_click=self._on_reset,
                    style=ft.ButtonStyle(color=Colors.ERROR),
                ),
                ft.TextButton(
                    "Cancel",
                    on_click=lambda _: self.close(),
                    style=ft.ButtonStyle(color=Colors.TEXT_LOW),
                ),
                ft.ElevatedButton(
                    "Save",
                    on_click=self._on_save,
                    style=ft.ButtonStyle(
                        bgcolor=Colors.PRIMARY,
                        color=Colors.TEXT_HIGH,
                    ),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

    # ── Tab builders ────────────────────────────────────────────────────────────

    def _build_general_tab(self, us: UserSettings) -> ft.Control:
        g = us.general
        self._dd_fields["general.language"] = ft.Dropdown(
            label="Language",
            value=g.language,
            options=[
                ft.dropdown.Option("en", "English"),
                ft.dropdown.Option("es", "Spanish"),
                ft.dropdown.Option("fr", "French"),
                ft.dropdown.Option("de", "German"),
                ft.dropdown.Option("zh", "Chinese"),
                ft.dropdown.Option("ja", "Japanese"),
                ft.dropdown.Option("ru", "Russian"),
            ],
            width=200,
        )
        self._dd_fields["general.startup_behavior"] = ft.Dropdown(
            label="Startup Behavior",
            value=g.startup_behavior,
            options=[
                ft.dropdown.Option("last_chat", "Open Last Chat"),
                ft.dropdown.Option("new_chat", "New Chat"),
                ft.dropdown.Option("default_chat", "Default Chat"),
            ],
            width=240,
        )
        self._sw_fields["general.minimize_to_tray"] = ft.Switch(
            label="Minimize to Tray",
            value=g.minimize_to_tray,
        )
        return self._scrollable_column([
            self._section("General Settings"),
            self._row(self._dd_fields["general.language"], self._dd_fields["general.startup_behavior"]),
            self._row(self._sw_fields["general.minimize_to_tray"]),
        ])

    def _build_appearance_tab(self, us: UserSettings) -> ft.Control:
        a = us.appearance
        self._dd_fields["appearance.theme"] = ft.Dropdown(
            label="Theme",
            value=a.theme,
            options=[
                ft.dropdown.Option("dark", "Dark"),
                ft.dropdown.Option("light", "Light"),
                ft.dropdown.Option("system", "System"),
            ],
            width=200,
        )
        self._txt_fields["appearance.window_width"] = ft.TextField(
            label="Window Width",
            value=str(a.window_width),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._txt_fields["appearance.window_height"] = ft.TextField(
            label="Window Height",
            value=str(a.window_height),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._txt_fields["appearance.compact_threshold"] = ft.TextField(
            label="Compact Threshold (px)",
            value=str(a.compact_threshold),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        return self._scrollable_column([
            self._section("Appearance Settings"),
            self._row(self._dd_fields["appearance.theme"]),
            self._section("Window Size"),
            self._row(
                self._txt_fields["appearance.window_width"],
                self._txt_fields["appearance.window_height"],
                self._txt_fields["appearance.compact_threshold"],
            ),
        ])

    def _build_models_tab(self, us: UserSettings) -> ft.Control:
        m = us.models
        self._txt_fields["models.default_provider"] = ft.TextField(
            label="Default Provider",
            value=m.default_provider,
            width=200,
        )
        self._txt_fields["models.default_model"] = ft.TextField(
            label="Default Model",
            value=m.default_model,
            width=240,
        )
        self._sl_fields["models.temperature"] = ft.Slider(
            label="Temperature",
            value=m.temperature,
            min=0.0,
            max=2.0,
            divisions=40,
            width=300,
        )
        self._txt_fields["models.max_tokens"] = ft.TextField(
            label="Max Tokens",
            value=str(m.max_tokens),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        return self._scrollable_column([
            self._section("Model Settings"),
            self._row(self._txt_fields["models.default_provider"], self._txt_fields["models.default_model"]),
            self._row(self._sl_fields["models.temperature"], self._txt_fields["models.max_tokens"]),
        ])

    def _build_providers_tab(self, us: UserSettings) -> ft.Control:
        p = us.providers

        providers_config = [
            ("ollama", "Ollama", p.ollama.base_url, "", False),
            ("openai", "OpenAI", p.openai.base_url, p.openai.api_key, True),
            ("anthropic", "Anthropic", p.anthropic.base_url, p.anthropic.api_key, True),
            ("gemini", "Google Gemini", p.gemini.base_url, p.gemini.api_key, True),
            ("groq", "Groq", p.groq.base_url, p.groq.api_key, True),
            ("openrouter", "OpenRouter", p.openrouter.base_url, p.openrouter.api_key, True),
            ("together", "Together AI", p.together.base_url, p.together.api_key, True),
            ("deepseek", "DeepSeek", p.deepseek.base_url, p.deepseek.api_key, True),
        ]

        items: list[ft.Control] = []

        for key, label, base_url, api_key, has_key in providers_config:
            self._txt_fields[f"providers.{key}.base_url"] = ft.TextField(
                label=f"{label} Base URL",
                value=base_url,
                width=280,
            )
            if has_key:
                self._txt_fields[f"providers.{key}.api_key"] = ft.TextField(
                    label=f"{label} API Key",
                    value=api_key,
                    width=280,
                    password=True,
                    can_reveal_password=True,
                )

            status = ft.Text("", size=11, color=Colors.TEXT_MUTED)
            self._provider_test_status[key] = status
            test_btn = ft.ElevatedButton(
                "Test",
                icon=ft.Icons.WIFI_TETHERING,
                on_click=lambda _, k=key: self._test_provider(k),
                style=ft.ButtonStyle(
                    bgcolor=ft.Colors.with_opacity(0.1, Colors.PRIMARY),
                    color=Colors.PRIMARY,
                    padding=ft.Padding(left=10, right=10, top=4, bottom=4),
                ),
                height=34,
            )
            self._provider_test_btn[key] = test_btn

            items.append(self._section(label))
            row_fields = [self._txt_fields[f"providers.{key}.base_url"]]
            if has_key:
                row_fields.append(self._txt_fields[f"providers.{key}.api_key"])
            row_fields.extend([test_btn, status])
            items.append(self._row(*row_fields))

        # Timeouts & Retries
        self._txt_fields["providers.connect_timeout"] = ft.TextField(
            label="Connect Timeout (s)",
            value=str(p.connect_timeout),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._txt_fields["providers.read_timeout"] = ft.TextField(
            label="Read Timeout (s)",
            value=str(p.read_timeout),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._txt_fields["providers.max_retries"] = ft.TextField(
            label="Max Retries",
            value=str(p.max_retries),
            width=100,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._txt_fields["providers.retry_delay"] = ft.TextField(
            label="Retry Delay (s)",
            value=str(p.retry_delay),
            width=100,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        items.append(self._section("Timeouts & Retries"))
        items.append(
            self._row(
                self._txt_fields["providers.connect_timeout"],
                self._txt_fields["providers.read_timeout"],
                self._txt_fields["providers.max_retries"],
                self._txt_fields["providers.retry_delay"],
            )
        )

        return self._scrollable_column(items)

    def _build_routing_tab(self, us: UserSettings) -> ft.Control:
        w = us.workspaces
        self._dd_fields["routing.router_mode"] = ft.Dropdown(
            label="Router Mode",
            value=w.router_mode,
            options=[
                ft.dropdown.Option("disabled", "Disabled (Active Model)"),
                ft.dropdown.Option("auto", "Auto (Keyword Routing)"),
                ft.dropdown.Option("category", "Category Match"),
            ],
            width=240,
        )
        return self._scrollable_column([
            self._section("Routing Settings"),
            self._row(self._dd_fields["routing.router_mode"]),
            self._info("Routes messages to the best model based on content. Changes apply globally to all workspaces."),
        ])

    def _build_diagnostics_tab(self, us: UserSettings) -> ft.Control:
        d = us.diagnostics
        self._dd_fields["diagnostics.log_level"] = ft.Dropdown(
            label="Log Level",
            value=d.log_level,
            options=[
                ft.dropdown.Option("DEBUG"),
                ft.dropdown.Option("INFO"),
                ft.dropdown.Option("WARNING"),
                ft.dropdown.Option("ERROR"),
            ],
            width=160,
        )
        self._sw_fields["diagnostics.debug_mode"] = ft.Switch(
            label="Debug Mode",
            value=d.debug_mode,
        )
        self._sw_fields["diagnostics.profiling_enabled"] = ft.Switch(
            label="Profiling Enabled",
            value=d.profiling_enabled,
        )
        return self._scrollable_column([
            self._section("Diagnostics Settings"),
            self._row(self._dd_fields["diagnostics.log_level"]),
            self._row(self._sw_fields["diagnostics.debug_mode"]),
            self._row(self._sw_fields["diagnostics.profiling_enabled"]),
            self._info("Debug mode enables verbose logging. Profiling tracks operation timing."),
        ])

    def _build_memory_tab(self, us: UserSettings) -> ft.Control:
        m = us.memory
        self._txt_fields["memory.default_profile"] = ft.TextField(
            label="Default Profile",
            value=m.default_profile,
            width=200,
        )
        self._txt_fields["memory.fact_max_importance"] = ft.TextField(
            label="Max Importance",
            value=str(m.fact_max_importance),
            width=100,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._txt_fields["memory.fact_default_importance"] = ft.TextField(
            label="Default Importance",
            value=str(m.fact_default_importance),
            width=100,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._txt_fields["memory.embedding_model"] = ft.TextField(
            label="Embedding Model",
            value=m.embedding_model,
            width=280,
        )
        self._txt_fields["memory.search_limit"] = ft.TextField(
            label="Search Limit",
            value=str(m.search_limit),
            width=100,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._sl_fields["memory.similarity_threshold"] = ft.Slider(
            label="Similarity Threshold",
            value=m.similarity_threshold,
            min=0.0,
            max=1.0,
            divisions=20,
            width=300,
        )
        self._txt_fields["memory.orchestrator_frequency"] = ft.TextField(
            label="Orchestrator Frequency",
            value=str(m.orchestrator_frequency),
            width=100,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        return self._scrollable_column([
            self._section("Memory Settings"),
            self._row(self._txt_fields["memory.default_profile"], self._txt_fields["memory.embedding_model"]),
            self._row(
                self._txt_fields["memory.fact_max_importance"],
                self._txt_fields["memory.fact_default_importance"],
                self._txt_fields["memory.search_limit"],
                self._txt_fields["memory.orchestrator_frequency"],
            ),
            self._row(self._sl_fields["memory.similarity_threshold"]),
        ])

    def _build_workspaces_tab(self, us: UserSettings) -> ft.Control:
        w = us.workspaces
        self._txt_fields["workspaces.default_name"] = ft.TextField(
            label="Default Workspace Name",
            value=w.default_name,
            width=240,
        )
        return self._scrollable_column([
            self._section("Workspace Settings"),
            self._row(self._txt_fields["workspaces.default_name"]),
            self._info("Changes apply to new workspaces. Existing workspaces retain their current settings."),
        ])

    def _build_performance_tab(self, us: UserSettings) -> ft.Control:
        p = us.performance
        self._txt_fields["performance.embedding_cache_size"] = ft.TextField(
            label="Embedding Cache Size",
            value=str(p.embedding_cache_size),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._txt_fields["performance.thread_pool_size"] = ft.TextField(
            label="Thread Pool Size",
            value=str(p.thread_pool_size),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._sw_fields["performance.background_save_enabled"] = ft.Switch(
            label="Background Save Enabled",
            value=p.background_save_enabled,
        )
        return self._scrollable_column([
            self._section("Performance Settings"),
            self._row(
                self._txt_fields["performance.embedding_cache_size"],
                self._txt_fields["performance.thread_pool_size"],
            ),
            self._row(self._sw_fields["performance.background_save_enabled"]),
        ])

    def _build_voice_tab(self, us: UserSettings) -> ft.Control:
        v = us.voice

        # ── TTS section ──────────────────────────────────────────────
        self._sw_fields["voice.tts_enabled"] = ft.Switch(
            label="Text-to-Speech Enabled",
            value=v.tts_enabled,
        )

        # Enumerate available voices via modern TTS engine
        self._cached_tts_voices: list[dict] = []
        try:
            self._cached_tts_voices = TTSEngine.list_voices()
        except Exception:
            self._cached_tts_voices = []

        available_langs = get_voice_languages(self._cached_tts_voices)
        lang_options = [ft.dropdown.Option("", "System default")]
        for lang in available_langs:
            lang_options.append(ft.dropdown.Option(lang, lang))

        self._dd_fields["voice.tts_language"] = ft.Dropdown(
            label="Voice Language",
            options=lang_options,
            value=v.tts_language,
            width=200,
            on_select=lambda e: self._on_voice_language_changed(e),
        )

        # Voice name — populated dynamically when language changes
        voice_options = [ft.dropdown.Option("", "System default")]
        if v.tts_language:
            filtered = get_voices_by_language(self._cached_tts_voices, v.tts_language)
            for vv in filtered:
                voice_options.append(ft.dropdown.Option(vv["name"], vv["name"]))
        self._dd_fields["voice.tts_voice_name"] = ft.Dropdown(
            label="Voice Name",
            options=voice_options,
            value=v.tts_voice_name if v.tts_voice_name else "",
            width=280,
            on_select=lambda e: self._on_voice_name_changed(e),
        )

        self._txt_fields["voice.tts_speed"] = ft.TextField(
            label="Speed (words/min)",
            value=str(v.tts_speed),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
        )

        self._sl_fields["voice.tts_volume"] = ft.Slider(
            label="Volume",
            min=0.0,
            max=1.0,
            value=v.tts_volume,
            divisions=20,
            round=2,
            width=200,
        )

        # ── STT section ──────────────────────────────────────────────
        self._sw_fields["voice.stt_enabled"] = ft.Switch(
            label="Speech-to-Text Enabled",
            value=v.stt_enabled,
        )

        stt_lang_opts = get_stt_language_options()
        self._dd_fields["voice.stt_language"] = ft.Dropdown(
            label="Recognition Language",
            options=[ft.dropdown.Option(k, lbl) for k, lbl in stt_lang_opts.items()],
            value=v.stt_language if v.stt_language else "auto",
            width=200,
        )

        self._sw_fields["voice.push_to_talk"] = ft.Switch(
            label="Push-to-Talk Mode",
            value=v.push_to_talk,
        )

        # ── Microphone device selector ──────────────────────────────
        mic_options = [ft.dropdown.Option("", "System default")]
        selected_mic = ""
        if v.mic_device_index is not None:
            selected_mic = str(v.mic_device_index)
        try:
            import pyaudio

            pa = pyaudio.PyAudio()
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    label = info.get("name", f"Device {i}")
                    mic_options.append(ft.dropdown.Option(str(i), f"{label}"))
            pa.terminate()
        except Exception as exc:
            log.warning("Failed to enumerate microphone devices: %s", exc)
        self._dd_fields["voice.mic_device_index"] = ft.Dropdown(
            label="Microphone Device",
            options=mic_options,
            value=selected_mic,
            width=320,
        )

        return self._scrollable_column([
            self._section("Text-to-Speech"),
            self._row(self._sw_fields["voice.tts_enabled"]),
            self._row(self._dd_fields["voice.tts_language"], self._dd_fields["voice.tts_voice_name"]),
            self._row(self._txt_fields["voice.tts_speed"], self._sl_fields["voice.tts_volume"]),
            self._section("Speech-to-Text"),
            self._row(self._sw_fields["voice.stt_enabled"]),
            self._row(self._dd_fields["voice.stt_language"], self._sw_fields["voice.push_to_talk"]),
            self._row(self._dd_fields["voice.mic_device_index"]),
            self._info("STT: speech_recognition (Google API). TTS: pyttsx3 (system voices)."),
        ])

    def _build_security_tab(self, us: UserSettings) -> ft.Control:
        s = us.security
        self._txt_fields["security.master_key_file"] = ft.TextField(
            label="Master Key File",
            value=s.master_key_file,
            width=280,
        )
        self._sw_fields["security.encrypt_api_keys"] = ft.Switch(
            label="Encrypt API Keys",
            value=s.encrypt_api_keys,
        )
        return self._scrollable_column([
            self._section("Security Settings"),
            self._row(self._sw_fields["security.encrypt_api_keys"]),
            self._row(self._txt_fields["security.master_key_file"]),
            self._info("API keys are stored encrypted on disk when enabled. Requires a master key file to be present."),
        ])

    def _build_advanced_tab(self, us: UserSettings) -> ft.Control:
        a = us.advanced
        self._txt_fields["advanced.max_context_tokens"] = ft.TextField(
            label="Max Context Tokens",
            value=str(a.max_context_tokens),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._txt_fields["advanced.max_active_tokens"] = ft.TextField(
            label="Max Active Tokens",
            value=str(a.max_active_tokens),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._txt_fields["advanced.history_window_tokens"] = ft.TextField(
            label="History Window Tokens",
            value=str(a.history_window_tokens),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._txt_fields["advanced.archive_keep_last_n"] = ft.TextField(
            label="Archive Keep Last N",
            value=str(a.archive_keep_last_n),
            width=100,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self._txt_fields["advanced.chunk_buffer_flush_threshold"] = ft.TextField(
            label="Chunk Buffer Flush Threshold",
            value=str(a.chunk_buffer_flush_threshold),
            width=100,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        return self._scrollable_column([
            self._section("Advanced Settings"),
            self._row(
                self._txt_fields["advanced.max_context_tokens"],
                self._txt_fields["advanced.max_active_tokens"],
                self._txt_fields["advanced.history_window_tokens"],
            ),
            self._row(
                self._txt_fields["advanced.archive_keep_last_n"],
                self._txt_fields["advanced.chunk_buffer_flush_threshold"],
            ),
        ])

    def _build_developer_tab(self, us: UserSettings) -> ft.Control:
        d = us.developer
        self._sw_fields["developer.dev_mode"] = ft.Switch(
            label="Developer Mode",
            value=d.dev_mode,
        )
        self._sw_fields["developer.experimental_features"] = ft.Switch(
            label="Experimental Features",
            value=d.experimental_features,
        )
        self._sw_fields["developer.show_internal_logs"] = ft.Switch(
            label="Show Internal Logs",
            value=d.show_internal_logs,
        )
        return self._scrollable_column([
            self._section("Developer Settings"),
            self._row(self._sw_fields["developer.dev_mode"]),
            self._row(self._sw_fields["developer.experimental_features"]),
            self._row(self._sw_fields["developer.show_internal_logs"]),
            self._info("Developer mode enables debugging tools and exposes internal model information."),
        ])

    # ── Save / Reset handlers ───────────────────────────────────────────────────

    def _on_save(self, _e: ft.ControlEvent) -> None:
        self._save_general()
        self._save_appearance()
        self._save_models()
        self._save_providers()
        self._save_routing()
        self._save_memory()
        self._save_diagnostics()
        self._save_workspaces()
        self._save_performance()
        self._save_voice()
        self._save_security()
        self._save_advanced()
        self._save_developer()

        if self._bus:
            self._bus.emit(SettingsChangedEvent(sender="settings_dialog", section="*"))

        self.close()
        self._page.run_thread(lambda: self._show_toast("Settings saved", Colors.SUCCESS))

    def _save_general(self) -> None:
        self._svc.set_general(
            language=self._get_value("general.language"),
            startup_behavior=self._get_value("general.startup_behavior"),
            minimize_to_tray=self._get_switch("general.minimize_to_tray"),
        )

    def _save_appearance(self) -> None:
        self._svc.set_appearance(
            theme=self._get_value("appearance.theme"),
            window_width=max(1000, self._get_int("appearance.window_width", default=1400)),
            window_height=max(600, self._get_int("appearance.window_height", default=900)),
            compact_threshold=self._get_int("appearance.compact_threshold", default=1000),
        )

    def _save_models(self) -> None:
        self._svc.set_models(
            default_provider=self._get_value("models.default_provider"),
            default_model=self._get_value("models.default_model"),
            temperature=self._get_slider("models.temperature"),
            max_tokens=self._get_int("models.max_tokens"),
        )

    def _save_providers(self) -> None:
        self._svc.set_providers(
            connect_timeout=self._get_float("providers.connect_timeout"),
            read_timeout=self._get_float("providers.read_timeout"),
            max_retries=self._get_int("providers.max_retries"),
            retry_delay=self._get_float("providers.retry_delay"),
        )
        for provider in ("ollama", "openai", "anthropic", "gemini", "groq", "openrouter", "together", "deepseek"):
            self._svc.set_provider_entry(
                provider,
                base_url=self._get_value(f"providers.{provider}.base_url"),
                api_key=self._get_value(f"providers.{provider}.api_key"),
            )

    def _save_routing(self) -> None:
        router_mode = self._get_value("routing.router_mode")
        self._svc.set_workspaces(router_mode=router_mode)

    def _save_diagnostics(self) -> None:
        self._svc.set_diagnostics(
            log_level=self._get_value("diagnostics.log_level"),
            debug_mode=self._get_switch("diagnostics.debug_mode"),
            profiling_enabled=self._get_switch("diagnostics.profiling_enabled"),
        )

    def _save_memory(self) -> None:
        self._svc.set_memory(
            default_profile=self._get_value("memory.default_profile"),
            fact_max_importance=self._get_int("memory.fact_max_importance"),
            fact_default_importance=self._get_int("memory.fact_default_importance"),
            embedding_model=self._get_value("memory.embedding_model"),
            search_limit=self._get_int("memory.search_limit"),
            similarity_threshold=self._get_slider("memory.similarity_threshold"),
            orchestrator_frequency=self._get_int("memory.orchestrator_frequency"),
        )

    def _save_workspaces(self) -> None:
        self._svc.set_workspaces(
            default_name=self._get_value("workspaces.default_name"),
        )

    def _save_performance(self) -> None:
        self._svc.set_performance(
            embedding_cache_size=self._get_int("performance.embedding_cache_size"),
            thread_pool_size=self._get_int("performance.thread_pool_size"),
            background_save_enabled=self._get_switch("performance.background_save_enabled"),
        )

    def _save_voice(self) -> None:
        voice_name = self._get_value("voice.tts_voice_name")
        voice_id = ""
        if voice_name and hasattr(self, "_cached_tts_voices"):
            for vv in self._cached_tts_voices:
                if vv.get("name") == voice_name:
                    voice_id = vv.get("id", "")
                    break
        # Apply voice to all AudioManager controllers
        from backend.voice.audio_manager import AudioManager

        try:
            mgr = AudioManager.get_instance()
            if voice_id:
                for ctrl in list(mgr._controllers.values()):
                    ctrl.set_voice(voice_id)
        except RuntimeError:
            log.debug("AudioManager not yet initialised, voice change deferred")

        mic_val = self._get_value("voice.mic_device_index")
        try:
            mic_device_index = int(mic_val) if mic_val else None
        except (ValueError, TypeError):
            mic_device_index = None

        self._svc.set_voice(
            stt_enabled=self._get_switch("voice.stt_enabled"),
            tts_enabled=self._get_switch("voice.tts_enabled"),
            tts_speed=self._get_int("voice.tts_speed"),
            tts_voice=voice_id,
            tts_voice_name=voice_name,
            tts_language=self._get_value("voice.tts_language"),
            tts_volume=self._get_slider("voice.tts_volume"),
            stt_language=self._get_value("voice.stt_language"),
            push_to_talk=self._get_switch("voice.push_to_talk"),
            mic_device_index=mic_device_index,
        )

    def _save_security(self) -> None:
        self._svc.set_security(
            encrypt_api_keys=self._get_switch("security.encrypt_api_keys"),
            master_key_file=self._get_value("security.master_key_file"),
        )

    def _save_advanced(self) -> None:
        self._svc.set_advanced(
            max_context_tokens=self._get_int("advanced.max_context_tokens"),
            max_active_tokens=self._get_int("advanced.max_active_tokens"),
            history_window_tokens=self._get_int("advanced.history_window_tokens"),
            archive_keep_last_n=self._get_int("advanced.archive_keep_last_n"),
            chunk_buffer_flush_threshold=self._get_int("advanced.chunk_buffer_flush_threshold"),
        )

    def _save_developer(self) -> None:
        self._svc.set_developer(
            dev_mode=self._get_switch("developer.dev_mode"),
            experimental_features=self._get_switch("developer.experimental_features"),
            show_internal_logs=self._get_switch("developer.show_internal_logs"),
        )

    def _on_reset(self, _e: ft.ControlEvent) -> None:
        self._svc.reset()
        if self._bus:
            self._bus.emit(SettingsChangedEvent(sender="settings_dialog", section="*"))
        self.close()
        self._page.run_thread(lambda: self._show_toast("Settings reset to defaults", Colors.WARNING))

    def _on_voice_language_changed(self, e: ft.ControlEvent) -> None:
        """Populate voice name dropdown when language selection changes."""
        lang = e.control.value if e.control else ""
        name_dd = self._dd_fields.get("voice.tts_voice_name")
        if not name_dd:
            return
        options = [ft.dropdown.Option("", "System default")]
        if lang and hasattr(self, "_cached_tts_voices"):
            filtered = get_voices_by_language(self._cached_tts_voices, lang)
            for vv in filtered:
                options.append(ft.dropdown.Option(vv["name"], vv["name"]))
        name_dd.options = options
        name_dd.value = ""
        try:
            name_dd.update()
        except Exception:
            log.debug("Voice name dropdown update ignored")

    def _on_voice_name_changed(self, e: ft.ControlEvent) -> None:
        """Map selected voice name to voice ID and store for save."""
        name = e.control.value if e.control else ""
        voice_id = ""
        if name and hasattr(self, "_cached_tts_voices"):
            for vv in self._cached_tts_voices:
                if vv.get("name") == name:
                    voice_id = vv.get("id", "")
                    break
        # Store as a transient field for _save_voice to read
        self._voice_name_to_id = {name: voice_id}

    # ── Value readers ───────────────────────────────────────────────────────────

    def _get_value(self, key: str) -> str:
        if key in self._txt_fields:
            return self._txt_fields[key].value or ""
        if key in self._dd_fields:
            return self._dd_fields[key].value or ""
        return ""

    def _get_int(self, key: str, default: int = 1) -> int:
        try:
            return int(self._get_value(key))
        except (ValueError, TypeError):
            return default

    def _get_float(self, key: str, default: float = 1.0) -> float:
        try:
            return float(self._get_value(key))
        except (ValueError, TypeError):
            return default

    def _get_switch(self, key: str) -> bool:
        return self._sw_fields.get(key, ft.Switch()).value or False

    def _get_slider(self, key: str) -> float:
        return self._sl_fields.get(key, ft.Slider()).value or 0.0

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _section(self, title: str) -> ft.Control:
        return ft.Text(
            title,
            size=11,
            weight=ft.FontWeight.BOLD,
            color=Colors.PRIMARY,
        )

    def _info(self, text: str) -> ft.Control:
        return ft.Text(
            text,
            size=10,
            color=Colors.TEXT_LOW,
            italic=True,
        )

    def _row(self, *controls: ft.Control) -> ft.Control:
        return ft.Container(
            content=ft.Row(
                list(controls),
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=ft.Padding(left=0, right=0, top=4, bottom=4),
        )

    def _scrollable_column(self, items: list[ft.Control]) -> ft.Control:
        return ft.Container(
            content=ft.Column(
                items,
                spacing=6,
                scroll=ft.ScrollMode.AUTO,
            ),
            padding=ft.Padding(left=8, right=8, top=8, bottom=8),
            expand=True,
        )

    def _test_provider(self, provider_key: str) -> None:
        """Test connectivity to a provider using stored credentials."""
        url = self._get_value(f"providers.{provider_key}.base_url")
        key = self._get_value(f"providers.{provider_key}.api_key")
        status_text = self._provider_test_status.get(provider_key)
        btn = self._provider_test_btn.get(provider_key)
        if not status_text or not btn:
            return

        def set_status(msg: str, color: str) -> None:
            status_text.value = msg
            status_text.color = color
            try:
                status_text.update()
            except Exception:
                log.debug("API test status update ignored")

        def set_btn(enabled: bool) -> None:
            btn.disabled = not enabled
            try:
                btn.update()
            except Exception:
                log.debug("API test button update ignored")

        def run_test() -> None:
            try:
                client = ApiModelClient(
                    api_url=url or "http://localhost:11434",
                    api_key=key or "",
                    model_name="test",
                    connect_timeout=5.0,
                    read_timeout=10.0,
                )
                ok, msg = client.health_check()
                client.close()
                self._page.run_thread(
                    lambda: set_status(
                        "OK" if ok else f"FAIL: {msg}",
                        Colors.SUCCESS if ok else Colors.ERROR,
                    )
                )
            except Exception as exc:
                err_msg = f"Error: {exc}"
                self._page.run_thread(lambda: set_status(err_msg, Colors.ERROR))
            finally:
                self._page.run_thread(lambda: set_btn(True))

        set_status("Testing...", Colors.WARNING)
        set_btn(False)
        threading.Thread(target=run_test, daemon=True).start()

    def _show_toast(self, message: str, color: str) -> None:
        try:
            snack = ft.SnackBar(
                ft.Text(message, color=Colors.TEXT_HIGH, size=13),
                bgcolor=color,
                duration=3000,
                open=True,
                behavior=ft.SnackBarBehavior.FLOATING,
            )
            self._page.overlay.append(snack)
            self._page.update()
        except Exception as exc:
            log.warning("Toast failed: %s", exc)
