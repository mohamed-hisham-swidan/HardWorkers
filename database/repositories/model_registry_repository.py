from __future__ import annotations

import time

from database.connection import ConnectionManager
from models.domain import ModelRegistryEntry
from models.enums import MemoryMode, ModelCategory, ModelProvider
from utils.helpers import parse_enum
from utils.logging_setup import get_logger

log = get_logger("database.repositories.model_registry_repository")


# ── Model Registry ────────────────────────────────────────────────────────────


class ModelRegistryRepository:
    """CRUD for custom Ollama and API model definitions."""

    def __init__(self, cm: ConnectionManager) -> None:
        self._cm = cm

    def get_all(self) -> list[ModelRegistryEntry]:
        with self._cm.transaction() as conn:
            rows = conn.execute(
                "SELECT id, name, provider, category, description, system_prompt, "
                "base_model, api_url, api_key, api_password, memory_mode, "
                "memory_profile_id, supports_vision, created_at, updated_at "
                "FROM model_registry ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def get_by_name(self, name: str) -> ModelRegistryEntry | None:
        with self._cm.transaction() as conn:
            row = conn.execute(
                "SELECT id, name, provider, category, description, system_prompt, "
                "base_model, api_url, api_key, api_password, memory_mode, "
                "memory_profile_id, supports_vision, created_at, updated_at "
                "FROM model_registry WHERE name = ?",
                (name,),
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def save(self, entry: ModelRegistryEntry) -> int:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._cm.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO model_registry "
                "(name, provider, category, description, system_prompt, base_model, "
                "api_url, api_key, api_password, memory_mode, memory_profile_id, "
                "supports_vision, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.name,
                    str(entry.provider),
                    str(entry.category),
                    entry.description,
                    entry.system_prompt,
                    entry.base_model,
                    entry.api_url,
                    entry.api_key,
                    entry.api_password,
                    str(entry.memory_mode),
                    entry.memory_profile_id,
                    1 if entry.supports_vision else 0,
                    ts,
                    ts,
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def update(self, entry: ModelRegistryEntry) -> bool:
        if entry.id is None:
            return False
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._cm.transaction() as conn:
            cur = conn.execute(
                "UPDATE model_registry SET "
                "name=?, provider=?, category=?, description=?, system_prompt=?, "
                "base_model=?, api_url=?, api_key=?, api_password=?, "
                "memory_mode=?, memory_profile_id=?, supports_vision=?, updated_at=? "
                "WHERE id=?",
                (
                    entry.name,
                    str(entry.provider),
                    str(entry.category),
                    entry.description,
                    entry.system_prompt,
                    entry.base_model,
                    entry.api_url,
                    entry.api_key,
                    entry.api_password,
                    str(entry.memory_mode),
                    entry.memory_profile_id,
                    1 if entry.supports_vision else 0,
                    ts,
                    entry.id,
                ),
            )
        return cur.rowcount > 0

    def get_by_id(self, entry_id: int) -> ModelRegistryEntry | None:
        with self._cm.transaction() as conn:
            row = conn.execute(
                "SELECT id, name, provider, category, description, system_prompt, "
                "base_model, api_url, api_key, api_password, memory_mode, "
                "memory_profile_id, supports_vision, created_at, updated_at "
                "FROM model_registry WHERE id = ?",
                (entry_id,),
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def delete(self, entry_id: int) -> bool:
        with self._cm.transaction() as conn:
            cur = conn.execute("DELETE FROM model_registry WHERE id=?", (entry_id,))
        return cur.rowcount > 0

    def count(self) -> int:
        with self._cm.transaction() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM model_registry").fetchone()[0])

    @staticmethod
    def _row_to_entry(row) -> ModelRegistryEntry:
        return ModelRegistryEntry(
            id=row["id"],
            name=row["name"],
            provider=parse_enum(ModelProvider, row["provider"], ModelProvider.OLLAMA),
            category=parse_enum(ModelCategory, row["category"], ModelCategory.GENERAL),
            description=row["description"] or "",
            system_prompt=row["system_prompt"] or "",
            base_model=row["base_model"] or "",
            api_url=row["api_url"] or "",
            api_key=row["api_key"] or "",
            api_password=row["api_password"] or "",
            memory_mode=parse_enum(MemoryMode, row["memory_mode"], MemoryMode.SHARED),
            memory_profile_id=row["memory_profile_id"],
            supports_vision=bool(row["supports_vision"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )
