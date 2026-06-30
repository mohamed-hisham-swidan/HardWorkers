"""Model Creator Dialog — Ollama and API model creation/editing."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import flet as ft

from config.constants import MODEL_CATEGORIES, STATUS_RESET_DELAY_S
from models.domain import ModelRegistryEntry
from models.enums import MemoryMode, ModelCategory, ModelProvider
from services.ai.model_creator import ModelCreatorService
from services.ai.model_manager import ModelManager
from ui.helpers import Colors, btn_style, dialog_title, divider, status_text
from utils.clipboard import copy_to_clipboard
from utils.helpers import parse_enum
from utils.logging_setup import get_logger

log = get_logger("ui.dialogs.model_creator_dialog")


_PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openai": {"label": "OpenAI", "url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "anthropic": {"label": "Anthropic", "url": "https://api.anthropic.com/v1", "model": "claude-3-5-haiku-latest"},
    "openrouter": {"label": "OpenRouter", "url": "https://openrouter.ai/api/v1", "model": "openrouter/auto"},
    "gemini": {
        "label": "Google Gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
    },
    "groq": {"label": "Groq", "url": "https://api.groq.com/openai/v1", "model": "mixtral-8x7b-32768"},
    "together": {
        "label": "Together AI",
        "url": "https://api.together.xyz/v1",
        "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
    },
    "deepseek": {"label": "DeepSeek", "url": "https://api.deepseek.com", "model": "deepseek-chat"},
    "mistral": {"label": "Mistral AI", "url": "https://api.mistral.ai/v1", "model": "mistral-small-latest"},
    "cohere": {"label": "Cohere", "url": "https://api.cohere.ai/v1", "model": "command-r-plus"},
    "perplexity": {
        "label": "Perplexity",
        "url": "https://api.perplexity.ai",
        "model": "llama-3.1-sonar-small-128k-chat",
    },
    "fireworks": {
        "label": "Fireworks AI",
        "url": "https://api.fireworks.ai/inference/v1",
        "model": "accounts/fireworks/models/llama-v3p2-3b-instruct",
    },
    "azure": {"label": "Azure OpenAI", "url": "https://YOUR_RESOURCE.openai.azure.com/v1", "model": "gpt-4o"},
    "lmstudio": {"label": "LM Studio", "url": "http://localhost:1234/v1", "model": "local-model"},
    "ollama": {"label": "Ollama (API)", "url": "http://localhost:11434/v1", "model": "llama3.2"},
    "vllm": {"label": "vLLM", "url": "http://localhost:8000/v1", "model": "mistralai/Mistral-7B-Instruct-v0.3"},
    "localai": {"label": "LocalAI", "url": "http://localhost:8080/v1", "model": "gpt-3.5-turbo"},
    "textsynth": {"label": "TextSynth", "url": "https://api.textsynth.com/v1", "model": "mistral_7b"},
    "novita": {
        "label": "Novita AI",
        "url": "https://api.novita.ai/v3/openai",
        "model": "mistralai/mixtral-8x22b-instruct",
    },
    "custom": {"label": "Custom", "url": "", "model": ""},
}

_MEM_MODES = ["shared", "dedicated", "none"]


class ModelCreatorDialog:
    """Full model management dialog (Ollama + API)."""

    def __init__(
        self,
        page: ft.Page,
        creator: ModelCreatorService,
        model_manager: ModelManager,
        pool: ThreadPoolExecutor,
        on_models_changed: Callable[[], None],
    ) -> None:
        self._page = page
        self._creator = creator
        self._mm = model_manager
        self._pool = pool
        self._notify = on_models_changed
        self._dlg: ft.AlertDialog | None = None
        self._editing_entry: ModelRegistryEntry | None = None
        self._original_snapshot: dict[str, str] | None = None

        # ── Ollama form fields ────────────────────────────────────────────────
        self._ol_name = ft.TextField(label="Model Name *", hint_text="my-assistant", expand=True)
        self._ol_desc = ft.TextField(label="Description", expand=True)
        self._ol_category = ft.Dropdown(
            label="Category",
            options=[ft.dropdown.Option(c) for c in MODEL_CATEGORIES],
            value="General",
            width=200,
        )
        self._ol_base = ft.Dropdown(label="Base Model *", options=[], expand=True)
        self._ol_sys_prompt = ft.TextField(
            label="System Prompt",
            multiline=True,
            min_lines=4,
            max_lines=8,
            expand=True,
        )
        self._ol_mem_mode = ft.Dropdown(
            label="Memory Mode",
            options=[ft.dropdown.Option(m) for m in _MEM_MODES],
            value="shared",
            width=160,
        )
        self._ol_status = status_text()
        self._ol_progress = ft.ProgressRing(width=20, height=20, visible=False)
        self._ol_btn_create = ft.ElevatedButton(
            "Create Model",
            icon=ft.Icons.ROCKET_LAUNCH,
            on_click=self._on_create_ollama,
            style=btn_style(Colors.PRIMARY),
        )

        # ── API form fields ───────────────────────────────────────────────────
        self._api_provider = ft.Dropdown(
            label="Provider",
            options=[ft.DropdownOption(key=k, text=p["label"]) for k, p in _PROVIDER_PRESETS.items()],
            value="custom",
            width=210,
            on_select=self._on_provider_change,
        )
        self._api_url = ft.TextField(
            label="API URL *",
            hint_text="Paste URL — /chat/completions appended automatically",
            expand=True,
            on_blur=self._on_url_blur,
        )
        self._api_url_copy_btn = ft.IconButton(
            icon=ft.Icons.COPY,
            icon_size=18,
            icon_color=Colors.TEXT_LOW,
            tooltip="Copy URL",
            on_click=self._on_copy_url,
        )
        self._api_url_reset_btn = ft.IconButton(
            icon=ft.Icons.REFRESH,
            icon_size=18,
            icon_color=Colors.TEXT_LOW,
            tooltip="Reset to provider default",
            on_click=self._on_reset_url,
        )
        self._api_key = ft.TextField(
            label="API Key *",
            password=True,
            can_reveal_password=True,
            expand=True,
        )
        self._api_password = ft.TextField(label="Password / Org ID (optional)", expand=True)
        self._api_model = ft.TextField(label="Model Name *", hint_text="gpt-4o-mini", expand=True)
        self._api_name = ft.TextField(label="Display Name *", hint_text="My GPT-4o", expand=True)
        self._api_desc = ft.TextField(label="Description", expand=True)
        self._api_category = ft.Dropdown(
            label="Category",
            options=[ft.dropdown.Option(c) for c in MODEL_CATEGORIES],
            value="General",
            width=200,
        )
        self._api_mem_mode = ft.Dropdown(
            label="Memory Mode",
            options=[ft.dropdown.Option(m) for m in _MEM_MODES],
            value="none",
            width=160,
        )
        self._api_discovered = ft.Dropdown(
            label="Discovered Models (select to auto-fill)",
            options=[],
            visible=False,
            expand=True,
            on_select=self._on_discovered_model_selected,
        )
        self._api_status = status_text()
        self._api_progress = ft.ProgressRing(width=20, height=20, visible=False)
        self._api_btn_test = ft.OutlinedButton(
            "Test Connection",
            icon=ft.Icons.WIFI_TETHERING,
            on_click=self._on_test_api,
            style=btn_style(Colors.SUCCESS),
        )
        self._api_btn_save = ft.ElevatedButton(
            "Save API Model",
            icon=ft.Icons.SAVE,
            on_click=self._on_save_api,
            style=btn_style(Colors.PRIMARY),
        )

    # ── Show / hide ───────────────────────────────────────────────────────────

    def show(self) -> None:
        self._load_base_models()

        is_edit = self._editing_entry is not None
        title_text = "Edit Model" if is_edit else "Create Model"

        # Adapt button text to edit/create mode
        self._ol_btn_create.text = "Update Model" if is_edit else "Create Model"
        self._api_btn_save.text = "Update API Model" if is_edit else "Save API Model"

        # Disable Ollama model-name / base-model when editing an existing Ollama model
        if is_edit and self._editing_entry and self._editing_entry.is_ollama:
            self._ol_name.disabled = True
            self._ol_base.disabled = True
        else:
            self._ol_name.disabled = False
            self._ol_base.disabled = False

        tabs = ft.Tabs(
            content=ft.Column(
                expand=True,
                controls=[
                    ft.TabBar(
                        tabs=[
                            ft.Tab(label="🦙 Ollama Model"),
                            ft.Tab(label="🌐 API Model"),
                        ]
                    ),
                    ft.TabBarView(
                        expand=True,
                        controls=[
                            self._build_ollama_tab(),
                            self._build_api_tab(),
                        ],
                    ),
                ],
            ),
            length=2,
            selected_index=0,
            animation_duration=200,
            expand=True,
        )

        self._dlg = ft.AlertDialog(
            modal=True,
            title=dialog_title(
                ft.Icons.SETTINGS_SUGGEST, title_text, extra=ft.IconButton(icon=ft.Icons.CLOSE, on_click=self._close)
            ),
            content=ft.Container(content=tabs, width=680, height=580, padding=10),
            actions=[
                ft.TextButton("Close", on_click=self._close, style=ft.ButtonStyle(color=Colors.TEXT_LOW)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.show_dialog(self._dlg)

    def _close(self, _e: ft.ControlEvent | None = None) -> None:
        # Disconnect on_change/on_select handlers to prevent event handler leaks
        for field in (self._ol_name, self._ol_desc, self._ol_sys_prompt):
            field.on_change = None
        for field in (self._ol_category, self._ol_mem_mode):
            field.on_select = None
        for field in (
            self._api_name,
            self._api_url,
            self._api_key,
            self._api_password,
            self._api_model,
            self._api_desc,
        ):
            field.on_change = None
        for field in (self._api_category, self._api_mem_mode):
            field.on_select = None
        self._editing_entry = None
        self._original_snapshot = None
        self._ol_btn_create.text = "Create Model"
        self._api_btn_save.text = "Save API Model"
        if self._dlg:
            self._dlg.open = False
            self._dlg.update()

    # ── Tab builders ──────────────────────────────────────────────────────────

    def _build_ollama_tab(self) -> ft.Container:
        return ft.Container(
            padding=16,
            content=ft.Column(
                [
                    ft.Row([self._ol_name, self._ol_category], spacing=8),
                    self._ol_desc,
                    self._ol_base,
                    ft.Text("System Prompt", size=12, color=Colors.TEXT_LOW),
                    self._ol_sys_prompt,
                    ft.Row([self._ol_mem_mode], alignment=ft.MainAxisAlignment.START),
                    divider(),
                    ft.Row(
                        [self._ol_progress, self._ol_status, self._ol_btn_create],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=10,
                    ),
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    def _build_api_tab(self) -> ft.Container:
        return ft.Container(
            padding=16,
            content=ft.Column(
                [
                    ft.Row([self._api_provider, self._api_category, self._api_mem_mode], spacing=8),
                    ft.Row(
                        [self._api_url, self._api_url_copy_btn, self._api_url_reset_btn],
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row([self._api_key], spacing=8),
                    self._api_password,
                    ft.Row([self._api_model, self._api_name], spacing=8),
                    self._api_discovered,
                    self._api_desc,
                    divider(),
                    ft.Row(
                        [self._api_progress, self._api_status, self._api_btn_test, self._api_btn_save],
                        alignment=ft.MainAxisAlignment.END,
                        spacing=8,
                    ),
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

    # ── Ollama creation flow ──────────────────────────────────────────────────

    def _on_create_ollama(self, _e: ft.ControlEvent) -> None:
        name = (self._ol_name.value or "").strip()
        base_model = self._ol_base.value or ""
        if not name:
            self._set_ol_status("Model name is required", Colors.ERROR)
            return
        if not base_model and not self._editing_entry:
            self._set_ol_status("Base model is required", Colors.ERROR)
            return

        self._ol_btn_create.disabled = True
        self._ol_progress.visible = True
        self._set_ol_status("Updating\u2026" if self._editing_entry else "Creating model\u2026", Colors.WARNING)
        self._pool.submit(self._create_ollama_bg, name, base_model)

    def _create_ollama_bg(self, name: str, base_model: str) -> None:
        sys_prompt = (self._ol_sys_prompt.value or "").strip()
        desc = (self._ol_desc.value or "").strip()
        category = self._ol_category.value or "General"
        mem_mode = MemoryMode(self._ol_mem_mode.value or "shared")

        if self._editing_entry:
            # Edit mode — only update registry metadata, skip Ollama API
            try:
                entry = ModelRegistryEntry(
                    id=self._editing_entry.id,
                    name=name,
                    provider=ModelProvider.OLLAMA,
                    category=parse_enum(ModelCategory, category, ModelCategory.GENERAL),
                    description=desc,
                    system_prompt=sys_prompt,
                    base_model=self._editing_entry.base_model,
                    memory_mode=mem_mode,
                )
                ok, msg = self._creator.update_registered_model(entry)
            except Exception as exc:
                log.exception("Ollama model edit crashed")
                ok, msg = False, f"Edit error: {exc}"
            self._page.run_thread(lambda: self._ollama_done(ok, msg))
            return

        # Create mode — call Ollama API then register
        modelfile = self._creator.build_modelfile(base_model, sys_prompt)

        def on_progress(status: str) -> None:
            self._set_ol_status(f"\u23f3 {status}", Colors.WARNING)

        try:
            ok, msg = self._creator.create_ollama_model(name, modelfile, on_progress=on_progress)
        except Exception as exc:
            log.exception("Ollama model creation crashed")
            ok, msg = False, f"Creation error: {exc}"

        if ok:
            try:
                entry = ModelRegistryEntry(
                    name=name,
                    provider=ModelProvider.OLLAMA,
                    category=parse_enum(ModelCategory, category, ModelCategory.GENERAL),
                    description=desc,
                    system_prompt=sys_prompt,
                    base_model=base_model,
                    memory_mode=mem_mode,
                )
                self._creator.register_model(entry)
            except Exception as exc:
                log.exception("Ollama model registration crashed")
                ok, msg = False, f"Registration error: {exc}"

        self._page.run_thread(lambda: self._ollama_done(ok, msg))

    def _ollama_done(self, ok: bool, msg: str) -> None:
        self._ol_progress.visible = False
        self._ol_btn_create.disabled = False
        color = Colors.SUCCESS if ok else Colors.ERROR
        self._set_ol_status(msg, color)
        try:
            self._ol_progress.update()
            self._ol_btn_create.update()
        except Exception as exc:
            log.warning("Failed to update Ollama done UI: %s", exc)
        if ok:
            self._editing_entry = None
            self._original_snapshot = None
            self._ol_btn_create.text = "Create Model"
            self._notify()
        else:
            self._schedule_ol_status_reset()

    # ── API save flow ─────────────────────────────────────────────────────────

    def _on_test_api(self, _e: ft.ControlEvent) -> None:
        url, key, model = self._api_url.value, self._api_key.value, self._api_model.value
        provider = (self._api_provider.value or "custom").lower()
        if not url or not model:
            self._set_api_status("API URL and Model Name are required", Colors.ERROR)
            self._schedule_status_reset()
            return
        self._api_btn_test.disabled = True
        self._api_btn_save.disabled = True
        self._api_progress.visible = True
        self._set_api_status("Testing connection\u2026", Colors.WARNING)
        try:
            self._api_btn_test.update()
            self._api_btn_save.update()
            self._api_progress.update()
        except Exception as exc:
            log.warning("Failed to update API test UI: %s", exc)
        self._pool.submit(self._test_api_bg, url, key or "", model, self._api_password.value or "", provider)

    def _test_api_bg(self, url: str, key: str, model: str, pwd: str, provider: str) -> None:
        try:
            ok, msg, discovered = self._creator.test_api_connection(url, key, model, pwd)
        except Exception as exc:
            log.exception("API connection test crashed")
            ok, msg, discovered = False, f"Connection test error: {exc}", []
        self._page.run_thread(lambda: self._api_test_done(ok, msg, discovered, provider))

    def _api_test_done(self, ok: bool, msg: str, discovered: list[str], provider: str = "") -> None:
        self._api_progress.visible = False
        self._api_btn_test.disabled = False
        self._api_btn_save.disabled = False
        color = Colors.SUCCESS if ok else Colors.ERROR
        self._set_api_status(msg, color)

        if ok and discovered:
            self._api_discovered.options = [ft.DropdownOption(key=m, text=m) for m in discovered]
            self._api_discovered.visible = True
            self._api_discovered.value = discovered[0]
            try:
                self._api_discovered.update()
            except Exception as exc:
                log.warning("Failed to update discovered models (visible): %s", exc)
            if provider == "openrouter":
                self._api_model.value = ""
                try:
                    self._api_model.update()
                except Exception:
                    log.debug("API model update on provider change ignored")
        else:
            self._api_discovered.visible = False
            self._api_discovered.options = []
            try:
                self._api_discovered.update()
            except Exception as exc:
                log.warning("Failed to update discovered models (hidden): %s", exc)

        try:
            self._api_progress.update()
            self._api_btn_test.update()
            self._api_btn_save.update()
        except Exception as exc:
            log.warning("Failed to update API test done UI: %s", exc)
        if not ok:
            self._schedule_status_reset()

    def _on_discovered_model_selected(self, _e: ft.ControlEvent) -> None:
        if self._api_discovered.value:
            self._api_model.value = self._api_discovered.value
        try:
            self._api_model.update()
        except Exception as exc:
            log.warning("Failed to update API model field: %s", exc)

    def _on_save_api(self, _e: ft.ControlEvent) -> None:
        name = (self._api_name.value or "").strip()
        url = (self._api_url.value or "").strip()
        key = (self._api_key.value or "").strip()
        model = (self._api_model.value or "").strip()
        provider_key = (self._api_provider.value or "custom").lower()

        if not name or not url or not model:
            self._set_api_status("Display name, URL, and model name are required", Colors.ERROR)
            return

        # Quick URL validation
        if not url.startswith(("http://", "https://")):
            self._set_api_status("URL must start with http:// or https://", Colors.ERROR)
            return
        if not url.endswith("/chat/completions"):
            url = url.rstrip("/") + "/chat/completions"
            self._api_url.value = url
            try:
                self._api_url.update()
            except Exception as exc:
                log.warning("Failed to update API URL field: %s", exc)

        # Map provider key to enum — only the original four have dedicated values
        if provider_key in ("openai", "anthropic", "openrouter"):
            provider = parse_enum(ModelProvider, provider_key, ModelProvider.CUSTOM)
        else:
            provider = ModelProvider.CUSTOM

        category_str = self._api_category.value or "General"
        category = parse_enum(ModelCategory, category_str, ModelCategory.GENERAL)
        mem_mode = MemoryMode(self._api_mem_mode.value or "none")

        entry = ModelRegistryEntry(
            name=name,
            provider=provider,
            category=category,
            description=(self._api_desc.value or "").strip(),
            api_url=url,
            api_key=key,
            api_password=(self._api_password.value or "").strip(),
            base_model=model,
            memory_mode=mem_mode,
        )

        # Preserve the primary key when editing so the update targets the right row
        if self._editing_entry:
            entry.id = self._editing_entry.id

        self._api_btn_test.disabled = True
        self._api_btn_save.disabled = True
        self._api_progress.visible = True
        self._set_api_status("Saving\u2026", Colors.WARNING)
        try:
            self._api_btn_test.update()
            self._api_btn_save.update()
            self._api_progress.update()
        except Exception as exc:
            log.warning("Failed to update API save UI: %s", exc)

        self._pool.submit(self._save_api_bg, entry)

    def _save_api_bg(self, entry: ModelRegistryEntry) -> None:
        try:
            if self._editing_entry:
                ok, msg = self._creator.update_registered_model(entry)
            else:
                ok, msg = self._creator.register_model(entry)
        except Exception as exc:
            log.exception("API model save crashed")
            ok, msg = False, f"Save error: {exc}"
        self._page.run_thread(lambda: self._api_save_done(ok, msg))

    def _api_save_done(self, ok: bool, msg: str) -> None:
        self._api_progress.visible = False
        self._api_btn_test.disabled = False
        self._api_btn_save.disabled = False
        color = Colors.SUCCESS if ok else Colors.ERROR
        self._set_api_status(msg, color)
        try:
            self._api_progress.update()
            self._api_btn_test.update()
            self._api_btn_save.update()
        except Exception:
            log.debug("API button UI update after test ignored")
        if ok:
            self._editing_entry = None
            self._original_snapshot = None
            self._api_btn_save.text = "Save API Model"
            self._notify()
        else:
            self._schedule_status_reset()

    # ── Edit flow ────────────────────────────────────────────────────────────

    def edit_model(self, entry: ModelRegistryEntry) -> None:
        """Open the dialog in edit mode with *entry* data pre-populated."""
        self._close()
        self._editing_entry = entry
        self._populate_form_for_edit(entry)
        self.show()

    def _on_field_changed(self, _e: ft.ControlEvent | None = None) -> None:
        """React to form field changes in edit mode — update save-button state."""
        self._check_for_changes()

    def _check_for_changes(self) -> None:
        """Disable the save button when no values have changed in edit mode."""
        if not self._editing_entry or self._original_snapshot is None:
            return

        current = self._gather_form_values()
        has_changes = current != self._original_snapshot

        if self._editing_entry.is_ollama:
            self._ol_btn_create.disabled = not has_changes
            try:
                self._ol_btn_create.update()
            except Exception as exc:
                log.warning("Failed to update Ollama button: %s", exc)
        else:
            self._api_btn_save.disabled = not has_changes
            try:
                self._api_btn_save.update()
            except Exception as exc:
                log.warning("Failed to update API save button: %s", exc)

    def _gather_form_values(self) -> dict[str, str]:
        """Return a dict of current form values for comparison."""
        if self._editing_entry and self._editing_entry.is_ollama:
            return {
                "name": (self._ol_name.value or "").strip(),
                "description": (self._ol_desc.value or "").strip(),
                "category": str(self._ol_category.value or "General"),
                "memory_mode": str(self._ol_mem_mode.value or "shared"),
                "system_prompt": (self._ol_sys_prompt.value or "").strip(),
            }
        return {
            "name": (self._api_name.value or "").strip(),
            "description": (self._api_desc.value or "").strip(),
            "category": str(self._api_category.value or "General"),
            "memory_mode": str(self._api_mem_mode.value or "none"),
            "api_url": (self._api_url.value or "").strip(),
            "api_key": (self._api_key.value or "").strip(),
            "api_password": (self._api_password.value or "").strip(),
            "base_model": (self._api_model.value or "").strip(),
        }

    def _populate_form_for_edit(self, entry: ModelRegistryEntry) -> None:
        """Pre-fill the correct tab with values from *entry*."""
        if entry.is_ollama:
            self._ol_name.value = entry.name
            self._ol_desc.value = entry.description
            self._ol_category.value = str(entry.category)
            self._ol_mem_mode.value = str(entry.memory_mode)
            self._ol_sys_prompt.value = entry.system_prompt
        else:
            self._api_name.value = entry.name
            self._api_url.value = entry.api_url
            self._api_key.value = entry.api_key
            self._api_password.value = entry.api_password or ""
            self._api_model.value = entry.base_model
            self._api_desc.value = entry.description
            self._api_category.value = str(entry.category)
            self._api_mem_mode.value = str(entry.memory_mode)

        # Snapshot current values for no-op detection
        self._original_snapshot = self._gather_form_values()

        # Wire on_change/on_select handlers to update save-button state
        if entry.is_ollama:
            for field in (self._ol_name, self._ol_desc, self._ol_sys_prompt):
                field.on_change = self._on_field_changed
            for field in (self._ol_category, self._ol_mem_mode):
                field.on_select = self._on_field_changed
        else:
            for field in (
                self._api_name,
                self._api_url,
                self._api_key,
                self._api_password,
                self._api_model,
                self._api_desc,
            ):
                field.on_change = self._on_field_changed
            for field in (self._api_category, self._api_mem_mode):
                field.on_select = self._on_field_changed

        # Initial check: nothing changed yet, so button should be disabled
        self._check_for_changes()

    # ── Bootstrap helpers ─────────────────────────────────────────────────────

    def _load_base_models(self) -> None:
        self._pool.submit(self._load_base_models_bg)

    def _load_base_models_bg(self) -> None:
        models = self._creator.list_base_models()
        if not models:
            models = ["llama3", "mistral", "gemma2", "phi3"]

        def update() -> None:
            self._ol_base.options = [ft.dropdown.Option(m) for m in models]
            if models:
                self._ol_base.value = models[0]
            try:
                self._ol_base.update()
            except Exception as exc:
                log.warning("Failed to update base models: %s", exc)

        self._page.run_thread(update)

    # ── Provider presets ──────────────────────────────────────────────────────

    def _on_provider_change(self, _e: ft.ControlEvent) -> None:
        key = self._api_provider.value or "custom"
        preset = _PROVIDER_PRESETS.get(key)
        if not preset:
            return

        def apply_preset(_e=None) -> None:
            self._api_url.value = preset.get("url", "")
            self._api_model.value = preset.get("model", "")
            try:
                self._api_url.update()
                self._api_model.update()
            except Exception as exc:
                log.warning("Failed to apply provider preset: %s", exc)

        # Confirm before overriding existing custom values
        url = (self._api_url.value or "").strip()
        if url and url != preset.get("url", ""):
            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text("Switch provider?"),
                content=ft.Text("Changing the provider will override the current URL and model name."),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda e: setattr(dlg, "open", False) or dlg.update()),
                    ft.TextButton(
                        "Apply", on_click=lambda e: setattr(dlg, "open", False) or dlg.update() or apply_preset()
                    ),
                ],
            )
            self._page.show_dialog(dlg)
        else:
            apply_preset()

    # ── URL helpers ────────────────────────────────────────────────────────────

    def _on_url_blur(self, _e: ft.ControlEvent) -> None:
        raw = (self._api_url.value or "").strip()
        if not raw:
            return
        if not re.match(r"^https?://", raw, re.IGNORECASE):
            raw = "https://" + raw
        raw = re.sub(r"(?<!:)//+", "/", raw)
        raw = raw.rstrip("/")
        if not raw.endswith("/chat/completions"):
            raw = raw + "/chat/completions"
        self._api_url.value = raw
        try:
            self._api_url.update()
        except Exception as exc:
            log.warning("Failed to update URL after blur: %s", exc)

    def _on_copy_url(self, _e: ft.ControlEvent) -> None:
        url = self._api_url.value or ""
        if url:
            copy_to_clipboard(url)

    def _on_reset_url(self, _e: ft.ControlEvent) -> None:
        key = self._api_provider.value or "custom"
        preset = _PROVIDER_PRESETS.get(key)
        if preset:
            self._api_url.value = preset.get("url", "")
            try:
                self._api_url.update()
            except Exception as exc:
                log.warning("Failed to reset API URL: %s", exc)

    # ── Status helpers ────────────────────────────────────────────────────────

    def _set_ol_status(self, msg: str, color: str) -> None:
        def update() -> None:
            self._ol_status.value = msg
            self._ol_status.color = color
            try:
                self._ol_status.update()
            except Exception as exc:
                log.warning("Failed to update Ollama status: %s", exc)

        try:
            self._page.run_thread(update)
        except RuntimeError:
            update()

    def _set_api_status(self, msg: str, color: str) -> None:
        def update() -> None:
            self._api_status.value = msg
            self._api_status.color = color
            try:
                self._api_status.update()
            except Exception as exc:
                log.warning("Failed to update API status: %s", exc)

        try:
            self._page.run_thread(update)
        except RuntimeError:
            update()

    # ── State recovery ─────────────────────────────────────────────────────────

    def _schedule_status_reset(self) -> None:
        """Reset API status to empty after a delay so UI isn't stuck in error state."""

        def reset() -> None:
            try:
                self._api_status.value = ""
                self._api_status.color = Colors.WARNING
                self._api_status.update()
            except Exception as exc:
                log.warning("Failed to reset API status: %s", exc)

        threading.Timer(STATUS_RESET_DELAY_S, lambda: self._page.run_thread(reset)).start()

    def _schedule_ol_status_reset(self) -> None:
        """Reset Ollama status to empty after a delay so UI isn't stuck in error state."""

        def reset() -> None:
            try:
                self._ol_status.value = ""
                self._ol_status.color = Colors.WARNING
                self._ol_status.update()
            except Exception as exc:
                log.warning("Failed to reset Ollama status: %s", exc)

        threading.Timer(STATUS_RESET_DELAY_S, lambda: self._page.run_thread(reset)).start()

    def close(self) -> None:
        """No-op: shared pool is shut down by MainWindow."""
