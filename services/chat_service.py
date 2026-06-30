"""Chat session management — HardWorkres platform."""

from __future__ import annotations

import threading

from config.constants import DEFAULT_CHAT_NAME
from database.repositories import DatabaseManager
from models.domain import ChatSession
from utils.logging_setup import get_logger

log = get_logger("services.chat_service")


class ChatService:
    """Business logic for multi-chat session management.

    Thread-safe: uses a dedicated lock for all mutation operations.
    """

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db
        self._lock = threading.Lock()

    # ── Queries ────────────────────────────────────────────────────────────

    def get_chats(self, workspace_id: int) -> list[ChatSession]:
        return self._db.chat_sessions.get_all(workspace_id)

    def get_chat(self, chat_id: int) -> ChatSession | None:
        return self._db.chat_sessions.get_by_id(chat_id)

    def get_default_chat(self, workspace_id: int) -> int:
        """Return the default (first) chat_id for a workspace, creating it if needed."""
        chat = self._db.chat_sessions.get_default(workspace_id)
        if chat is not None:
            return chat.id
        return self._ensure_default(workspace_id)

    # ── Mutations ──────────────────────────────────────────────────────────

    def ensure_default_chat(self, workspace_id: int) -> int:
        with self._lock:
            return self._ensure_default(workspace_id)

    def _ensure_default(self, workspace_id: int) -> int:
        chat = self._db.chat_sessions.get_default(workspace_id)
        if chat is not None:
            return chat.id
        return self._db.chat_sessions.create(workspace_id, DEFAULT_CHAT_NAME)

    def create_chat(self, workspace_id: int, name: str | None = None) -> int:
        with self._lock:
            if not name or not name.strip():
                count = len(self._db.chat_sessions.get_all(workspace_id))
                name = f"Chat {count + 1}"
            return self._db.chat_sessions.create(workspace_id, name.strip())

    def rename_chat(self, chat_id: int, new_name: str) -> bool:
        with self._lock:
            return self._db.chat_sessions.rename(chat_id, new_name.strip())

    def pin_chat(self, chat_id: int, pinned: bool) -> bool:
        with self._lock:
            return self._db.chat_sessions.set_pinned(chat_id, pinned)

    def delete_chat(self, chat_id: int, workspace_id: int) -> int:
        """Delete a chat. If it was the last one, create a new default chat first.

        Returns the *replacement* chat_id (the new default, or the next sibling).
        """
        with self._lock:
            all_chats = self._db.chat_sessions.get_all(workspace_id)
            if len(all_chats) <= 1:
                replacement_id = self._db.chat_sessions.create(workspace_id, DEFAULT_CHAT_NAME)
            else:
                replacement_id = 0

            self._db.chat_sessions.delete(chat_id)

            if replacement_id:
                return replacement_id

            remaining = self._db.chat_sessions.get_all(workspace_id)
            return remaining[0].id if remaining else self._ensure_default(workspace_id)
