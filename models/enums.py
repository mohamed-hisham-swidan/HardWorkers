"""Domain enumerations — HardWorkres platform."""

from enum import StrEnum


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AppStatus(StrEnum):
    READY = "Ready"
    GENERATING = "Generating…"
    LOADING = "Loading…"
    INDEXING = "Indexing…"
    ERROR = "Error"
    CREATING = "Creating…"
    ROUTING = "Routing…"


class ModelProvider(StrEnum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"
    GROQ = "groq"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    TOGETHER = "together"
    CUSTOM = "custom"


class ModelCategory(StrEnum):
    GENERAL = "General"
    CODING = "Coding"
    RESEARCH = "Research"
    WRITING = "Writing"
    TRANSLATION = "Translation"
    MEMORY = "Memory"
    OBSIDIAN = "Obsidian"
    SUMMARIZATION = "Summarization"


class MemoryMode(StrEnum):
    NONE = "none"  # API model gets no memory context
    DEDICATED = "dedicated"  # API model uses its own isolated memory profile
    SHARED = "shared"  # API model uses the global shared memory


class RouterMode(StrEnum):
    DISABLED = "disabled"  # always use the selected model
    AUTO = "auto"  # router picks based on message content
    CATEGORY = "category"  # router picks based on workspace category


class FileType(StrEnum):
    IMAGE = "image"
    PDF = "pdf"
    AUDIO = "audio"
    VIDEO = "video"
