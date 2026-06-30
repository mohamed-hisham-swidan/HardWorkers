"""Immutable application constants — HardWorkres platform."""

# ── Branding ──────────────────────────────────────────────────────────────────
PROJECT_NAME = "HardWorkres"
APP_NAME = "HardWorkres"
APP_VERSION = "3.3.0"
APP_AUTHOR = "HardWorkres Contributors"

# ── Memory pipeline thresholds ────────────────────────────────────────────────
ARCHIVE_KEEP_LAST_N = 6
SUMMARY_MAX_MESSAGES = 20
MIN_RESPONSE_LENGTH = 15

# ── Fact importance bounds ────────────────────────────────────────────────────
FACT_MIN_IMPORTANCE = 1
FACT_MAX_IMPORTANCE = 10
FACT_DEFAULT_IMPORTANCE = 5

# ── UI animation / timing ─────────────────────────────────────────────────────
SPINNER_INTERVAL_MS = 120
STATUS_RESET_DELAY_S = 3.0

# ── File I/O ──────────────────────────────────────────────────────────────────
MAX_IMPORT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMPORT_EXTENSIONS = {".json"}

# ── Streaming ─────────────────────────────────────────────────────────────────
CHUNK_BUFFER_FLUSH_THRESHOLD = 10  # chars

# ── Model categories ──────────────────────────────────────────────────────────
MODEL_CATEGORIES = [
    "General",
    "Coding",
    "Research",
    "Writing",
    "Translation",
    "Memory",
    "Obsidian",
    "Summarization",
]

# ── Router keyword map (category → trigger words) ─────────────────────────────
ROUTER_KEYWORDS: dict[str, list[str]] = {
    "Coding": [
        "code",
        "function",
        "bug",
        "python",
        "javascript",
        "typescript",
        "debug",
        "error",
        "syntax",
        "class",
        "algorithm",
        "compile",
        "program",
        "variable",
        "loop",
    ],
    "Research": [
        "research",
        "study",
        "paper",
        "reference",
        "explain",
        "information",
        "science",
        "literature",
        "journal",
        "hypothesis",
        "data",
        "evidence",
        "source",
        "cite",
    ],
    "Writing": [
        "write",
        "essay",
        "article",
        "story",
        "draft",
        "creative",
        "novel",
        "blog",
        "paragraph",
        "edit",
        "poem",
        "describe",
        "narrate",
        "content",
        "script",
    ],
    "Translation": [
        "translate",
        "language",
        "french",
        "spanish",
        "arabic",
        "german",
        "chinese",
        "japanese",
        "korean",
        "russian",
        "portuguese",
        "italian",
        "dutch",
        "hindi",
    ],
    "Summarization": [
        "summarize",
        "summary",
        "brief",
        "tldr",
        "short",
        "condense",
        "overview",
        "recap",
        "shorten",
        "main points",
    ],
    "Memory": [
        "remember",
        "recall",
        "forgot",
        "memory",
        "know me",
        "my name",
        "previous",
        "last time",
        "before",
        "history",
    ],
    "Obsidian": ["obsidian", "vault", "note", "markdown", "wiki", "knowledge base", "link", "backlink", "graph"],
}

# ── Memory profile names ──────────────────────────────────────────────────────
MEMORY_PROFILE_SHARED = "Shared"
MEMORY_PROFILE_NONE = "No Memory"
DEFAULT_MEMORY_PROFILES = ["Shared", "No Memory", "Research", "Coding", "Writing"]

# ── Default workspace names ───────────────────────────────────────────────────
DEFAULT_WORKSPACE = "Default"
WORKSPACE_NAMES = ["Default", "Coding", "Research", "Writing", "Obsidian"]

# ── Chat system ────────────────────────────────────────────────────────────────
DEFAULT_CHAT_NAME = "General"
ORCHESTRATOR_FREQUENCY = 3  # Run memory extraction every N messages

# ── API connection defaults ───────────────────────────────────────────────────
API_CONNECT_TIMEOUT_S = 10.0
API_READ_TIMEOUT_S = 60.0
STREAM_ACTIVITY_TIMEOUT_S = 30.0  # max seconds between streaming chunks
