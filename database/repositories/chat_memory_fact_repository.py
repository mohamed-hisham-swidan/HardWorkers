from __future__ import annotations

from database.connection import ConnectionManager
from models.domain import ChatMemoryFact
from utils.logging_setup import get_logger

log = get_logger("database.repositories.chat_memory_fact_repository")


# ── Chat Memory Facts (per-chat structured KV store) ─────────────────────────


class ChatMemoryFactRepository:
    """Per-chat structured key-value facts (extracted entities, preferences, etc.)."""

    def __init__(self, cm: ConnectionManager) -> None:
        self._cm = cm

    def upsert(self, chat_id: int, key: str, value: str, importance: int = 5) -> int:
        with self._cm.transaction() as conn:
            conn.execute(
                "INSERT INTO chat_memory_facts (chat_id, fact_key, fact_value, importance, updated_at) "
                "VALUES (?, ?, ?, ?, datetime('now')) "
                "ON CONFLICT(chat_id, fact_key) DO UPDATE SET "
                "fact_value = excluded.fact_value, "
                "importance = excluded.importance, "
                "updated_at = datetime('now')",
                (chat_id, key, value, importance),
            )
            row = conn.execute(
                "SELECT id FROM chat_memory_facts WHERE chat_id=? AND fact_key=?",
                (chat_id, key),
            ).fetchone()
        return int(row["id"]) if row else 0

    def get_all(self, chat_id: int) -> list[ChatMemoryFact]:
        with self._cm.transaction() as conn:
            rows = conn.execute(
                "SELECT id, chat_id, fact_key, fact_value, importance, created_at, updated_at "
                "FROM chat_memory_facts WHERE chat_id=? ORDER BY importance DESC",
                (chat_id,),
            ).fetchall()
        return [
            ChatMemoryFact(
                id=r["id"],
                chat_id=r["chat_id"],
                key=r["fact_key"],
                value=r["fact_value"],
                importance=r["importance"],
                created_at=r["created_at"] or "",
                updated_at=r["updated_at"] or "",
            )
            for r in rows
        ]

    def delete(self, fact_id: int) -> bool:
        with self._cm.transaction() as conn:
            cur = conn.execute("DELETE FROM chat_memory_facts WHERE id=?", (fact_id,))
        return cur.rowcount > 0

    def count_for_chat(self, chat_id: int) -> int:
        with self._cm.transaction() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM chat_memory_facts WHERE chat_id=?", (chat_id,)).fetchone()[0])
