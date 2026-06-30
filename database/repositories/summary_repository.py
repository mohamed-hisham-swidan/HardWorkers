from __future__ import annotations

from database.connection import ConnectionManager
from models.domain import ConversationSummary
from utils.logging_setup import get_logger

log = get_logger("database.repositories.summary_repository")


# ── Conversation summaries ────────────────────────────────────────────────────


class SummaryRepository:
    def __init__(self, cm: ConnectionManager) -> None:
        self._cm = cm

    def save(self, text: str) -> int:
        with self._cm.transaction() as conn:
            cur = conn.execute("INSERT INTO conversation_summaries (summary) VALUES (?)", (text,))
            return cur.lastrowid  # type: ignore[return-value]

    def get_recent(self, limit: int = 5) -> list[ConversationSummary]:
        with self._cm.transaction() as conn:
            rows = conn.execute(
                "SELECT id, summary FROM conversation_summaries ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [ConversationSummary(id=r["id"], text=r["summary"]) for r in rows]
