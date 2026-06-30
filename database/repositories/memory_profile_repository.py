from __future__ import annotations

import time

from database.connection import ConnectionManager
from models.domain import MemoryProfile
from utils.logging_setup import get_logger

log = get_logger("database.repositories.memory_profile_repository")


# ── Memory Profiles ───────────────────────────────────────────────────────────


class MemoryProfileRepository:
    """CRUD for memory isolation profiles."""

    def __init__(self, cm: ConnectionManager) -> None:
        self._cm = cm

    def get_all(self) -> list[MemoryProfile]:
        with self._cm.transaction() as conn:
            rows = conn.execute("SELECT id, name, description, created_at FROM memory_profiles ORDER BY id").fetchall()
        return [
            MemoryProfile(
                id=r["id"], name=r["name"], description=r["description"] or "", created_at=r["created_at"] or ""
            )
            for r in rows
        ]

    def get_by_name(self, name: str) -> MemoryProfile | None:
        with self._cm.transaction() as conn:
            row = conn.execute(
                "SELECT id, name, description, created_at FROM memory_profiles WHERE name=?",
                (name,),
            ).fetchone()
        if not row:
            return None
        return MemoryProfile(
            id=row["id"], name=row["name"], description=row["description"] or "", created_at=row["created_at"] or ""
        )

    def get_by_id(self, profile_id: int) -> MemoryProfile | None:
        with self._cm.transaction() as conn:
            row = conn.execute(
                "SELECT id, name, description, created_at FROM memory_profiles WHERE id=?",
                (profile_id,),
            ).fetchone()
        if not row:
            return None
        return MemoryProfile(
            id=row["id"], name=row["name"], description=row["description"] or "", created_at=row["created_at"] or ""
        )

    def save(self, profile: MemoryProfile) -> int:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._cm.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO memory_profiles (name, description, created_at) VALUES (?, ?, ?)",
                (profile.name, profile.description, ts),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def delete(self, profile_id: int) -> bool:
        with self._cm.transaction() as conn:
            cur = conn.execute("DELETE FROM memory_profiles WHERE id=?", (profile_id,))
        return cur.rowcount > 0
