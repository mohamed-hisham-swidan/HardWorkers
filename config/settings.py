"""Application configuration loaded from environment variables or defaults."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("config.settings")


def _load_env_file(path: Path) -> None:
    """Load a ``.env`` file into ``os.environ`` (no external dependency).

    Supports ``KEY=VALUE`` lines, ``#`` comments, and quoted values.
    Never overwrites an already-set environment variable.
    """
    if not path.is_file():
        return
    for line in path.read_text("utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        key = key.strip()
        val = val.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = val


# Load .env files in priority order (local overrides committed template)
_env_files = [Path(".env"), Path(".env.example")]
for _p in _env_files:
    _load_env_file(_p)


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _env_float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


@dataclass(frozen=True)
class DatabaseConfig:
    path: Path = field(default_factory=lambda: Path(_env("DB_PATH", "./data/hardworkers.db")))
    busy_timeout_ms: int = field(default_factory=lambda: _env_int("DB_BUSY_TIMEOUT_MS", 10_000))

    def ensure_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class VectorConfig:
    index_dir: Path = field(default_factory=lambda: Path(_env("VECTOR_INDEX_DIR", "./data/faiss_index")))
    model_name: str = field(default_factory=lambda: _env("EMBEDDING_MODEL", "all-MiniLM-L6-v2"))
    dimension: int = field(default_factory=lambda: _env_int("VECTOR_DIMENSION", 384))
    cache_size: int = field(default_factory=lambda: _env_int("EMBEDDING_CACHE_SIZE", 1_000))
    search_limit: int = field(default_factory=lambda: _env_int("VECTOR_SEARCH_LIMIT", 3))
    similarity_threshold: float = field(default_factory=lambda: _env_float("SIMILARITY_THRESHOLD", 0.45))

    def ensure_dir(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str = field(default_factory=lambda: _env("OLLAMA_BASE_URL", "http://localhost:11434"))
    default_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "llama3"))
    connect_timeout: float = field(default_factory=lambda: _env_float("OLLAMA_CONNECT_TIMEOUT", 15.0))
    read_timeout: float = field(default_factory=lambda: _env_float("OLLAMA_READ_TIMEOUT", 180.0))
    temperature: float = field(default_factory=lambda: _env_float("OLLAMA_TEMPERATURE", 0.7))
    max_retries: int = field(default_factory=lambda: _env_int("OLLAMA_MAX_RETRIES", 3))
    retry_delay: float = field(default_factory=lambda: _env_float("OLLAMA_RETRY_DELAY", 1.5))
    bin_path: str = field(default_factory=lambda: _env("OLLAMA_BIN_PATH", "ollama"))


@dataclass(frozen=True)
class TokenConfig:
    encoding: str = field(default_factory=lambda: _env("TOKEN_ENCODING", "cl100k_base"))
    max_context: int = field(default_factory=lambda: _env_int("MAX_CONTEXT_TOKENS", 3_072))
    max_active: int = field(default_factory=lambda: _env_int("MAX_ACTIVE_TOKENS", 2_500))
    history_window: int = field(default_factory=lambda: _env_int("HISTORY_WINDOW_TOKENS", 1_500))


@dataclass(frozen=True)
class UIConfig:
    width: int = field(default_factory=lambda: _env_int("UI_WIDTH", 1_400))
    height: int = field(default_factory=lambda: _env_int("UI_HEIGHT", 900))


@dataclass(frozen=True)
class APIConfig:
    host: str = field(default_factory=lambda: _env("API_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("API_PORT", 8_000))
    reload: bool = field(default_factory=lambda: os.getenv("API_RELOAD", "true").lower() == "true")
    jwt_secret: str = field(default_factory=lambda: _env("JWT_SECRET", "dev-secret-change-in-production"))
    jwt_algorithm: str = field(default_factory=lambda: _env("JWT_ALGORITHM", "HS256"))
    jwt_expire_hours: int = field(default_factory=lambda: _env_int("JWT_EXPIRE_HOURS", 24))
    cors_origins: list[str] = field(default_factory=lambda: _env("CORS_ORIGINS", "http://localhost:5173").split(","))
    admin_username: str = field(default_factory=lambda: _env("ADMIN_USERNAME", "admin"))
    admin_password: str = field(default_factory=lambda: _env("ADMIN_PASSWORD", "admin"))


def _check_dev_defaults(config: AppConfig) -> None:
    """Warn loudly if production env is running with obvious dev defaults."""
    if config.api.jwt_secret == "dev-secret-change-in-production":
        log.warning("JWT_SECRET is set to the dev default — change it in production!")
    if config.api.admin_username == "admin" and config.api.admin_password == "admin":
        log.warning("ADMIN_USERNAME/ADMIN_PASSWORD are set to dev defaults — change them in production!")
    if os.getenv("ENV", "development") == "production":
        if config.api.jwt_secret == "dev-secret-change-in-production":
            log.error("PRODUCTION ENVIRONMENT WITH DEFAULT JWT_SECRET — THIS IS A SECURITY RISK!")
        if config.api.admin_password == "admin":
            log.error("PRODUCTION ENVIRONMENT WITH DEFAULT ADMIN PASSWORD — THIS IS A SECURITY RISK!")


@dataclass(frozen=True)
class AppConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    vector: VectorConfig = field(default_factory=VectorConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    tokens: TokenConfig = field(default_factory=TokenConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    api: APIConfig = field(default_factory=APIConfig)
    log_dir: Path = field(default_factory=lambda: Path(_env("LOG_DIR", "./logs")))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", "./data")))

    @classmethod
    def load(cls) -> AppConfig:
        """Create config from environment variables."""
        cfg = cls()
        _check_dev_defaults(cfg)
        return cfg

    def prepare_dirs(self) -> None:
        """Ensure all required directories exist."""
        self.database.ensure_parent()
        self.vector.ensure_dir()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
