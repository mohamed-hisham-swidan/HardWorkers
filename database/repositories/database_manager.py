from __future__ import annotations

from config.settings import DatabaseConfig
from database.connection import ConnectionManager
from database.migrations import apply_migrations
from database.repositories.chat_memory_fact_repository import ChatMemoryFactRepository
from database.repositories.chat_repository import ChatRepository
from database.repositories.chat_session_repository import ChatSessionRepository
from database.repositories.chat_summary_repository import ChatSummaryRepository
from database.repositories.memory_profile_repository import MemoryProfileRepository
from database.repositories.model_registry_repository import ModelRegistryRepository
from database.repositories.profile_repository import ProfileRepository
from database.repositories.summary_repository import SummaryRepository
from database.repositories.workspace_repository import WorkspaceRepository
from utils.logging_setup import get_logger

log = get_logger("database.repositories.database_manager")


# ── Unified facade ────────────────────────────────────────────────────────────


class DatabaseManager:
    """Facade providing access to all repositories through a single object."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._cm = ConnectionManager(config.path, config.busy_timeout_ms)
        self._bootstrap()

        self.chat = ChatRepository(self._cm)
        self.profile = ProfileRepository(self._cm)
        self.summaries = SummaryRepository(self._cm)
        self.models = ModelRegistryRepository(self._cm)
        self.mem_profiles = MemoryProfileRepository(self._cm)
        self.workspaces = WorkspaceRepository(self._cm)
        self.chat_sessions = ChatSessionRepository(self._cm)
        self.chat_facts = ChatMemoryFactRepository(self._cm)
        self.chat_summaries = ChatSummaryRepository(self._cm)

    def _bootstrap(self) -> None:
        with self._cm.transaction() as conn:
            apply_migrations(conn)
        log.info("Database ready — all migrations applied")

    def stats(self) -> dict[str, int]:
        return {
            "active_messages": self.chat.active_count(),
            "active_tokens": self.chat.total_tokens(),
            "facts": self.profile.count(),
            "registered_models": self.models.count(),
        }

    def integrity_ok(self) -> bool:
        return self._cm.integrity_check()

    def close(self) -> None:
        self._cm.close_thread_connection()
        log.info("Database connection closed")
