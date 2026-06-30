from __future__ import annotations

import time

from database.connection import ConnectionManager
from models.domain import ChatSession
from utils.logging_setup import get_logger

log = get_logger("database.repositories.chat_session_repository")


# ── Chat Sessions ─────────────────────────────────────────────────────────────


class ChatSessionRepository:
    """CRUD for chat sessions within a workspace."""

    def __init__(self, cm: ConnectionManager) -> None:
        self._cm = cm

    def create(self, workspace_id: int, name: str) -> int:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._cm.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO chats (workspace_id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (workspace_id, name, ts, ts),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_all(self, workspace_id: int) -> list[ChatSession]:
        with self._cm.transaction() as conn:
            rows = conn.execute(
                "SELECT id, workspace_id, name, is_pinned, created_at, updated_at "
                "FROM chats WHERE workspace_id=? ORDER BY is_pinned DESC, updated_at DESC",
                (workspace_id,),
            ).fetchall()
        return [
            ChatSession(
                id=r["id"],
                workspace_id=r["workspace_id"],
                name=r["name"],
                pinned=bool(r["is_pinned"]),
                created_at=r["created_at"] or "",
                updated_at=r["updated_at"] or "",
            )
            for r in rows
        ]

    def get_by_id(self, chat_id: int) -> ChatSession | None:
        with self._cm.transaction() as conn:
            row = conn.execute(
                "SELECT id, workspace_id, name, is_pinned, created_at, updated_at FROM chats WHERE id=?",
                (chat_id,),
            ).fetchone()
        if not row:
            return None
        return ChatSession(
            id=row["id"],
            workspace_id=row["workspace_id"],
            name=row["name"],
            pinned=bool(row["is_pinned"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    def get_default(self, workspace_id: int) -> ChatSession | None:
        """Return the chronologically first chat for a workspace (the default)."""
        with self._cm.transaction() as conn:
            row = conn.execute(
                "SELECT id, workspace_id, name, is_pinned, created_at, updated_at "
                "FROM chats WHERE workspace_id=? ORDER BY id ASC LIMIT 1",
                (workspace_id,),
            ).fetchone()
        if not row:
            return None
        return ChatSession(
            id=row["id"],
            workspace_id=row["workspace_id"],
            name=row["name"],
            pinned=bool(row["is_pinned"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    def set_pinned(self, chat_id: int, pinned: bool) -> bool:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        val = 1 if pinned else 0
        with self._cm.transaction() as conn:
            cur = conn.execute(
                "UPDATE chats SET is_pinned=?, updated_at=? WHERE id=?",
                (val, ts, chat_id),
            )
        return cur.rowcount > 0

    def delete(self, chat_id: int, reassign_to: int | None = None) -> bool:
        """Delete a chat session.

        If *reassign_to* is provided, messages belonging to the deleted chat are
        reassigned to that chat instead of being deleted.
        """
        with self._cm.transaction() as conn:
            if reassign_to is not None:
                conn.execute(
                    "UPDATE chat_history SET chat_id=? WHERE chat_id=?",
                    (reassign_to, chat_id),
                )
            else:
                conn.execute("DELETE FROM chat_history WHERE chat_id=?", (chat_id,))
            conn.execute("DELETE FROM chat_memory_facts WHERE chat_id=?", (chat_id,))
            conn.execute("DELETE FROM chat_summaries WHERE chat_id=?", (chat_id,))
            cur = conn.execute("DELETE FROM chats WHERE id=?", (chat_id,))
        return cur.rowcount > 0

    def rename(self, chat_id: int, new_name: str) -> bool:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._cm.transaction() as conn:
            cur = conn.execute(
                "UPDATE chats SET name=?, updated_at=? WHERE id=?",
                (new_name, ts, chat_id),
            )
        return cur.rowcount > 0
