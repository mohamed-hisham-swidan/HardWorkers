"""Domain data models (pure data, no I/O) — HardWorkres platform."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .enums import MemoryMode, MessageRole, ModelCategory, ModelProvider, RouterMode

# ── Chat Session ──────────────────────────────────────────────────────────────


@dataclass
class ChatSession:
    """A named conversation within a workspace."""

    workspace_id: int
    name: str
    pinned: bool = False
    created_at: str = ""
    updated_at: str = ""
    id: int | None = None
    message_count: int = 0

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Chat name must not be empty.")

    @property
    def display_name(self) -> str:
        return self.name


@dataclass
class ChatMemoryFact:
    """A single key-value fact extracted into per-chat structured memory."""

    chat_id: int
    key: str
    value: str
    importance: int = 5
    created_at: str = ""
    updated_at: str = ""
    id: int | None = None

    def __post_init__(self) -> None:
        if not self.key or not self.key.strip():
            raise ValueError("Fact key must not be empty.")
        if not (1 <= self.importance <= 10):
            raise ValueError(f"Importance must be 1–10, got {self.importance}.")


@dataclass
class ChatSummary:
    """A semantic insight extracted for a specific chat session."""

    chat_id: int
    summary: str
    source: str = "orchestrator"
    created_at: str = ""
    id: int | None = None

    def __post_init__(self) -> None:
        if not self.summary or not self.summary.strip():
            raise ValueError("Summary must not be empty.")


# ── Core chat models ──────────────────────────────────────────────────────────


@dataclass
class Message:
    role: MessageRole
    content: str
    tokens: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    id: int | None = None
    attachment_path: str | None = None
    file_type: str | None = None

    def __post_init__(self) -> None:
        if not self.content or not self.content.strip():
            raise ValueError("Message content must not be empty.")

    def to_api_dict(self) -> dict[str, str]:
        return {"role": str(self.role), "content": self.content}


@dataclass
class UserFact:
    key: str
    value: str
    importance: int = 5
    id: int | None = None

    def __post_init__(self) -> None:
        if not self.key or not self.value:
            raise ValueError("Fact key and value must not be empty.")
        if not (1 <= self.importance <= 10):
            raise ValueError(f"Importance must be 1–10, got {self.importance}.")

    def to_embedding_text(self) -> str:
        return f"Key: {self.key} | Value: {self.value}"


@dataclass(frozen=True)
class SearchResult:
    score: float
    key: str
    value: str

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"Score must be 0–1, got {self.score}.")


@dataclass
class ConversationSummary:
    text: str
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class OllamaModel:
    name: str
    size_bytes: int = 0
    modified_at: str = ""

    @property
    def size_human(self) -> str:
        size = self.size_bytes
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


@dataclass
class DiagnosticsSnapshot:
    cpu_percent: float = 0.0
    ram_used_mb: float = 0.0
    ram_total_mb: float = 0.0
    active_threads: int = 0
    db_active_messages: int = 0
    db_active_tokens: int = 0
    db_facts: int = 0
    vector_entries: int = 0
    embedding_cache_size: int = 0
    ollama_status: str = "unknown"
    ollama_latency_ms: float = 0.0
    current_model: str = ""


# ── Model Registry ────────────────────────────────────────────────────────────


@dataclass
class ModelRegistryEntry:
    """Represents a model stored in the local registry (Ollama or API)."""

    name: str
    provider: ModelProvider = ModelProvider.OLLAMA
    category: ModelCategory = ModelCategory.GENERAL
    description: str = ""
    system_prompt: str = ""
    base_model: str = ""  # Ollama base model used in Modelfile
    api_url: str = ""  # For API models: endpoint URL
    api_key: str = ""  # For API models: API key
    api_password: str = ""  # For API models: optional password/org
    supports_vision: bool = False
    memory_mode: MemoryMode = MemoryMode.SHARED
    memory_profile_id: int | None = None
    created_at: str = ""
    updated_at: str = ""
    id: int | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Model name must not be empty.")

    @property
    def is_ollama(self) -> bool:
        return self.provider == ModelProvider.OLLAMA

    @property
    def is_api(self) -> bool:
        return self.provider != ModelProvider.OLLAMA

    def display_label(self) -> str:
        icon = "🦙" if self.is_ollama else "🌐"
        return f"{icon} {self.name}"


# ── Memory Profiles ───────────────────────────────────────────────────────────


@dataclass
class MemoryProfile:
    """Isolated memory namespace for a model or workspace."""

    name: str
    description: str = ""
    created_at: str = ""
    id: int | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Profile name must not be empty.")


# ── Workspaces ────────────────────────────────────────────────────────────────


@dataclass
class Workspace:
    """Bundles an active model, memory profile, and router settings."""

    name: str
    active_model: str = ""
    memory_profile_id: int | None = None
    memory_profile_name: str = "Shared"
    router_mode: RouterMode = RouterMode.DISABLED
    description: str = ""
    category: ModelCategory = ModelCategory.GENERAL
    created_at: str = ""
    updated_at: str = ""
    id: int | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Workspace name must not be empty.")


# ── Router ────────────────────────────────────────────────────────────────────


@dataclass
class RouterDecision:
    """Result of the model router analysis."""

    chosen_model: str
    confidence: float  # 0.0 – 1.0
    detected_category: str
    reason: str
