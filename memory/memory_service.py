"""Semantic memory service — HardWorkres platform.

Extended with memory profile support:
- SHARED  → uses the global shared vector store (original behaviour)
- NONE    → no memory context injected
- DEDICATED → per-profile isolated fact namespace (stored with profile prefix)
"""

from __future__ import annotations

import threading

from database.repositories import DatabaseManager
from models.domain import MemoryProfile, SearchResult, UserFact
from models.enums import MemoryMode
from utils.logging_setup import get_logger
from vectorstore.faiss_store import VectorStore

log = get_logger("memory.memory_service")

_PROFILE_PREFIX = "__profile_"


class MemoryService:
    def __init__(self, db: DatabaseManager, vs: VectorStore) -> None:
        self._db = db
        self._vs = vs
        self._lock = threading.RLock()

        # Active memory mode and profile (changed when workspace switches)
        self._mode: MemoryMode = MemoryMode.SHARED
        self._profile: MemoryProfile | None = None

    # ── Profile management ────────────────────────────────────────────────────

    def set_mode(self, mode: MemoryMode, profile: MemoryProfile | None = None) -> None:
        with self._lock:
            self._mode = mode
            self._profile = profile
        log.info("Memory mode set to %s (profile=%s)", mode, profile.name if profile else "-")

    def get_mode(self) -> MemoryMode:
        with self._lock:
            return self._mode

    def is_active(self) -> bool:
        """Return False when memory is completely disabled (NONE mode)."""
        with self._lock:
            return self._mode != MemoryMode.NONE

    # ── Fact CRUD ─────────────────────────────────────────────────────────────

    def add_fact(self, key: str, value: str, importance: int = 5) -> int:
        if not key or not value:
            raise ValueError("Key and value must not be empty")
        if not (1 <= importance <= 10):
            raise ValueError("Importance must be between 1 and 10")

        with self._lock:
            stored_key = self._storage_key(key)
            fact_id = self._db.profile.upsert(stored_key, value, importance)
            fact = UserFact(id=fact_id, key=key, value=value, importance=importance)
            self._vs.add_fact(fact)

        log.info("Fact stored: %r (id=%d, importance=%d)", key, fact_id, importance)
        return fact_id

    def delete_fact(self, fact_id: int) -> bool:
        with self._lock:
            deleted = self._db.profile.delete(fact_id)
            if deleted:
                facts = self._visible_facts_locked()
                self._vs.rebuild(facts)
        if deleted:
            log.info("Fact %d deleted — index rebuilt", fact_id)
        return deleted

    def get_all_facts(self) -> list[UserFact]:
        with self._lock:
            return self._visible_facts_locked()

    # ── Semantic search ───────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        limit: int | None = None,
        threshold: float | None = None,
    ) -> list[SearchResult]:
        """Search for relevant facts.

        Returns empty list if mode is NONE (memory isolation).
        """
        with self._lock:
            if self._mode == MemoryMode.NONE:
                return []

        if not query or not query.strip():
            return []

        with self._lock:
            results = self._vs.search(query, limit=limit, threshold=threshold)
        log.debug("Semantic search %r → %d results (mode=%s)", query[:40], len(results), self._mode)
        return results

    # ── Index lifecycle ───────────────────────────────────────────────────────

    def rebuild_index(self) -> int:
        """Reload all facts from DB and rebuild the vector index."""
        with self._lock:
            facts = self._visible_facts_locked()
            self._vs.rebuild(facts)
        log.info("Index rebuilt from %d facts", len(facts))
        return len(facts)

    def save_index(self) -> None:
        with self._lock:
            self._vs.save()

    def close(self) -> None:
        self.save_index()
        self._vs.close()
        log.info("Memory service closed")

    # ── Profile listing (for UI) ──────────────────────────────────────────────

    def get_all_profiles(self) -> list[MemoryProfile]:
        return self._db.mem_profiles.get_all()

    def create_profile(self, name: str, description: str = "") -> tuple[bool, str]:
        with self._lock:
            try:
                existing = self._db.mem_profiles.get_by_name(name)
                if existing:
                    return False, f"Profile '{name}' already exists"
                profile = MemoryProfile(name=name, description=description)
                self._db.mem_profiles.save(profile)
                return True, f"Memory profile '{name}' created"
            except Exception as exc:
                log.error("Profile creation failed: %s", exc)
                return False, str(exc)

    def _storage_key(self, key: str) -> str:
        if self._mode == MemoryMode.DEDICATED and self._profile and self._profile.id is not None:
            return f"{_PROFILE_PREFIX}{self._profile.id}__::{key}"
        return key

    def _visible_facts_locked(self) -> list[UserFact]:
        if self._mode == MemoryMode.NONE:
            return []

        facts = self._db.profile.get_all()
        if self._mode == MemoryMode.DEDICATED and self._profile and self._profile.id is not None:
            prefix = f"{_PROFILE_PREFIX}{self._profile.id}__::"
            return [
                UserFact(id=f.id, key=f.key[len(prefix) :], value=f.value, importance=f.importance)
                for f in facts
                if f.key.startswith(prefix)
            ]

        return [f for f in facts if not f.key.startswith(_PROFILE_PREFIX)]
