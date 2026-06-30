from __future__ import annotations

from database.connection import ConnectionManager
from models.domain import UserFact
from utils.logging_setup import get_logger

log = get_logger("database.repositories.profile_repository")


# ── User profile (facts) ──────────────────────────────────────────────────────


class ProfileRepository:
    def __init__(self, cm: ConnectionManager) -> None:
        self._cm = cm

    def get_all(self) -> list[UserFact]:
        with self._cm.transaction() as conn:
            rows = conn.execute(
                "SELECT id, fact_key, fact_value, importance FROM user_profile ORDER BY importance DESC"
            ).fetchall()
        return [
            UserFact(id=r["id"], key=r["fact_key"], value=r["fact_value"], importance=r["importance"]) for r in rows
        ]

    def upsert(self, key: str, value: str, importance: int = 5) -> int:
        with self._cm.transaction() as conn:
            conn.execute(
                "INSERT INTO user_profile (fact_key, fact_value, importance, updated_at) "
                "VALUES (?, ?, ?, datetime('now')) "
                "ON CONFLICT(fact_key) DO UPDATE SET "
                "fact_value = excluded.fact_value, "
                "importance = excluded.importance, "
                "updated_at = datetime('now')",
                (key, value, importance),
            )
            row = conn.execute("SELECT id FROM user_profile WHERE fact_key = ?", (key,)).fetchone()
        return int(row["id"])

    def delete(self, fact_id: int) -> bool:
        with self._cm.transaction() as conn:
            cur = conn.execute("DELETE FROM user_profile WHERE id = ?", (fact_id,))
        return cur.rowcount > 0

    def count(self) -> int:
        with self._cm.transaction() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM user_profile").fetchone()[0])
