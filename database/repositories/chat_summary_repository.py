from __future__ import annotations

import time

from database.connection import ConnectionManager
from models.domain import ChatSummary
from utils.logging_setup import get_logger

log = get_logger("database.repositories.chat_summary_repository")


# ── Chat Summaries (per-chat semantic summaries) ──────────────────────────────


class ChatSummaryRepository:
    """Per-chat semantic summaries for long-term memory compression."""

    def __init__(self, cm: ConnectionManager) -> None:
        self._cm = cm

    def save(self, chat_id: int, summary: str) -> int:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._cm.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO chat_summaries (chat_id, summary, created_at) VALUES (?, ?, ?)",
                (chat_id, summary, ts),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_recent(self, chat_id: int, limit: int = 5) -> list[ChatSummary]:
        with self._cm.transaction() as conn:
            rows = conn.execute(
                "SELECT id, chat_id, summary, created_at FROM chat_summaries WHERE chat_id=? ORDER BY id DESC LIMIT ?",
                (chat_id, limit),
            ).fetchall()
        return [
            ChatSummary(
                id=r["id"],
                chat_id=r["chat_id"],
                summary=r["summary"],
                created_at=r["created_at"] or "",
            )
            for r in rows
        ]

    def delete_all_for_chat(self, chat_id: int) -> int:
        with self._cm.transaction() as conn:
            cur = conn.execute("DELETE FROM chat_summaries WHERE chat_id=?", (chat_id,))
        return cur.rowcount
