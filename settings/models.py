"""Mutable settings models for user-facing configuration.

All dataclasses are mutable (unlike the frozen env-var ``AppConfig``) so
they can be edited at runtime and persisted to ``settings.json``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GeneralSettings:
    language: str = "en"
    startup_behavior: str = "last_chat"  # "last_chat" | "new_chat" | "default_chat"
    minimize_to_tray: bool = False


@dataclass
class AppearanceSettings:
    theme: str = "dark"  # "dark" | "light" | "system"
    window_width: int = 1400
    window_height: int = 900
    compact_threshold: int = 1000


@dataclass
class ModelSettings:
    default_provider: str = "ollama"
    default_model: str = "llama3"
    temperature: float = 0.7
    max_tokens: int = 2048


@dataclass
class ProviderEntry:
    base_url: str = ""
    api_key: str = ""  # stored encrypted on disk; plaintext in memory


@dataclass
class ProviderSettings:
    ollama: ProviderEntry = field(default_factory=lambda: ProviderEntry(base_url="http://localhost:11434"))
    openai: ProviderEntry = field(default_factory=ProviderEntry)
    anthropic: ProviderEntry = field(default_factory=ProviderEntry)
    gemini: ProviderEntry = field(default_factory=ProviderEntry)
    groq: ProviderEntry = field(default_factory=ProviderEntry)
    openrouter: ProviderEntry = field(default_factory=ProviderEntry)
    together: ProviderEntry = field(default_factory=ProviderEntry)
    deepseek: ProviderEntry = field(default_factory=ProviderEntry)
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    max_retries: int = 3
    retry_delay: float = 1.5


@dataclass
class MemorySettings:
    default_profile: str = "Shared"
    fact_max_importance: int = 10
    fact_default_importance: int = 5
    embedding_model: str = "all-MiniLM-L6-v2"
    search_limit: int = 3
    similarity_threshold: float = 0.45
    orchestrator_frequency: int = 3


@dataclass
class WorkspaceSettings:
    default_name: str = "Default"
    router_mode: str = "auto"  # "disabled" | "auto" | "category"


@dataclass
class PerformanceSettings:
    embedding_cache_size: int = 1000
    thread_pool_size: int = 4
    background_save_enabled: bool = True


@dataclass
class SecuritySettings:
    encrypt_api_keys: bool = True
    master_key_file: str = ".master_key"


@dataclass
class DiagnosticsSettings:
    log_level: str = "INFO"
    debug_mode: bool = False
    profiling_enabled: bool = False


@dataclass
class AdvancedSettings:
    max_context_tokens: int = 3072
    max_active_tokens: int = 2500
    history_window_tokens: int = 1500
    archive_keep_last_n: int = 6
    chunk_buffer_flush_threshold: int = 10


@dataclass
class DeveloperSettings:
    dev_mode: bool = False
    experimental_features: bool = False
    show_internal_logs: bool = False


@dataclass
class VoiceSettings:
    stt_enabled: bool = True
    tts_enabled: bool = True
    tts_speed: int = 180
    tts_voice: str = ""
    tts_voice_name: str = ""
    tts_language: str = ""
    tts_volume: float = 1.0
    stt_language: str = "auto"
    push_to_talk: bool = False
    mic_device_index: int | None = None


@dataclass
class UserSettings:
    """Top-level aggregate of all user-configurable settings."""

    general: GeneralSettings = field(default_factory=GeneralSettings)
    appearance: AppearanceSettings = field(default_factory=AppearanceSettings)
    models: ModelSettings = field(default_factory=ModelSettings)
    providers: ProviderSettings = field(default_factory=ProviderSettings)
    memory: MemorySettings = field(default_factory=MemorySettings)
    workspaces: WorkspaceSettings = field(default_factory=WorkspaceSettings)
    performance: PerformanceSettings = field(default_factory=PerformanceSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)
    voice: VoiceSettings = field(default_factory=VoiceSettings)
    diagnostics: DiagnosticsSettings = field(default_factory=DiagnosticsSettings)
    advanced: AdvancedSettings = field(default_factory=AdvancedSettings)
    developer: DeveloperSettings = field(default_factory=DeveloperSettings)

    @classmethod
    def defaults(cls) -> UserSettings:
        return cls()
