"""Unit tests for the database layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import DatabaseConfig
from database.repositories import DatabaseManager


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    config = DatabaseConfig(path=tmp_path / "test.db")
    manager = DatabaseManager(config)
    yield manager
    manager.close()


class TestChatRepository:
    def test_save_and_retrieve(self, db: DatabaseManager) -> None:
        db.chat.save("user", "Hello, world!")
        messages = db.chat.get_recent_by_token_budget(max_tokens=1000)
        assert len(messages) == 1
        assert messages[0].content == "Hello, world!"

    def test_token_budget_filters_old_messages(self, db: DatabaseManager) -> None:
        # Save a long message that will consume tokens
        long_content = "word " * 200
        db.chat.save("user", long_content)
        db.chat.save("user", "short message")

        # Budget only allows the most recent short message
        messages = db.chat.get_recent_by_token_budget(max_tokens=10)
        assert len(messages) == 1
        assert messages[0].content == "short message"

    def test_total_tokens_increases(self, db: DatabaseManager) -> None:
        assert db.chat.total_tokens() == 0
        db.chat.save("user", "hello")
        assert db.chat.total_tokens() > 0

    def test_archive_old(self, db: DatabaseManager) -> None:
        for i in range(10):
            db.chat.save("user", f"message {i}")
        archived = db.chat.archive_old(keep_last_n=4)
        assert archived == 6
        assert db.chat.active_count() == 4

    def test_empty_content_raises(self, db: DatabaseManager) -> None:
        # Empty content should raise ValueError from the Message model
        with pytest.raises(Exception):
            db.chat.save("user", "")


class TestProfileRepository:
    def test_upsert_and_retrieve(self, db: DatabaseManager) -> None:
        db.profile.upsert("name", "Alice", importance=8)
        facts = db.profile.get_all()
        assert len(facts) == 1
        assert facts[0].key == "name"
        assert facts[0].value == "Alice"
        assert facts[0].importance == 8

    def test_upsert_updates_existing(self, db: DatabaseManager) -> None:
        db.profile.upsert("name", "Alice")
        db.profile.upsert("name", "Bob", importance=9)
        facts = db.profile.get_all()
        assert len(facts) == 1
        assert facts[0].value == "Bob"

    def test_delete_fact(self, db: DatabaseManager) -> None:
        fact_id = db.profile.upsert("key", "value")
        assert db.profile.delete(fact_id)
        assert db.profile.get_all() == []

    def test_delete_nonexistent_returns_false(self, db: DatabaseManager) -> None:
        assert not db.profile.delete(9999)

    def test_ordering_by_importance(self, db: DatabaseManager) -> None:
        db.profile.upsert("low", "value", importance=2)
        db.profile.upsert("high", "value", importance=9)
        facts = db.profile.get_all()
        assert facts[0].importance >= facts[1].importance


class TestSummaryRepository:
    def test_save_and_get_recent(self, db: DatabaseManager) -> None:
        db.summaries.save("Summary one")
        db.summaries.save("Summary two")
        results = db.summaries.get_recent(limit=5)
        assert len(results) == 2
        # Most recent first
        assert results[0].text == "Summary two"

    def test_limit_respected(self, db: DatabaseManager) -> None:
        for i in range(10):
            db.summaries.save(f"summary {i}")
        assert len(db.summaries.get_recent(limit=3)) == 3


class TestDatabaseManager:
    def test_stats(self, db: DatabaseManager) -> None:
        db.chat.save("user", "test")
        db.profile.upsert("k", "v")
        stats = db.stats()
        assert stats["active_messages"] == 1
        assert stats["active_tokens"] > 0
        assert stats["facts"] == 1

    def test_integrity_check(self, db: DatabaseManager) -> None:
        assert db.integrity_ok()


# ── New chat session tests ────────────────────────────────────────────────────


class TestChatSessionRepository:
    def _create_ws(self, db: DatabaseManager) -> int:
        from models.domain import Workspace
        from models.enums import ModelCategory, RouterMode

        ws = Workspace(name="TestWS", category=ModelCategory.GENERAL, router_mode=RouterMode.DISABLED)
        return db.workspaces.save(ws)

    def test_create_and_get_all(self, db: DatabaseManager) -> None:
        ws_id = self._create_ws(db)
        cid1 = db.chat_sessions.create(ws_id, "Chat A")
        cid2 = db.chat_sessions.create(ws_id, "Chat B")
        assert cid1 is not None and cid2 is not None
        chats = db.chat_sessions.get_all(ws_id)
        assert len(chats) == 2
        names = {c.name for c in chats}
        assert names == {"Chat A", "Chat B"}

    def test_get_by_id(self, db: DatabaseManager) -> None:
        ws_id = self._create_ws(db)
        cid = db.chat_sessions.create(ws_id, "My Chat")
        chat = db.chat_sessions.get_by_id(cid)
        assert chat is not None
        assert chat.name == "My Chat"
        assert chat.workspace_id == ws_id

    def test_get_default_returns_first(self, db: DatabaseManager) -> None:
        ws_id = self._create_ws(db)
        cid1 = db.chat_sessions.create(ws_id, "First")
        db.chat_sessions.create(ws_id, "Second")
        default = db.chat_sessions.get_default(ws_id)
        assert default is not None
        assert default.id == cid1

    def test_rename(self, db: DatabaseManager) -> None:
        ws_id = self._create_ws(db)
        cid = db.chat_sessions.create(ws_id, "Old Name")
        assert db.chat_sessions.rename(cid, "New Name")
        chat = db.chat_sessions.get_by_id(cid)
        assert chat is not None
        assert chat.name == "New Name"

    def test_set_pinned(self, db: DatabaseManager) -> None:
        ws_id = self._create_ws(db)
        cid = db.chat_sessions.create(ws_id, "Pin Test")
        assert db.chat_sessions.set_pinned(cid, True)
        chat = db.chat_sessions.get_by_id(cid)
        assert chat is not None
        assert chat.pinned is True

    def test_delete(self, db: DatabaseManager) -> None:
        ws_id = self._create_ws(db)
        cid = db.chat_sessions.create(ws_id, "To Delete")
        db.chat_sessions.delete(cid)
        assert db.chat_sessions.get_by_id(cid) is None

    def test_get_nonexistent(self, db: DatabaseManager) -> None:
        assert db.chat_sessions.get_by_id(9999) is None


# ── Chat memory facts tests ───────────────────────────────────────────────────


class TestChatMemoryFactRepository:
    def _create_ws_and_chat(self, db: DatabaseManager) -> int:
        from models.domain import Workspace
        from models.enums import ModelCategory, RouterMode

        ws = Workspace(name="FactTestWS", category=ModelCategory.GENERAL, router_mode=RouterMode.DISABLED)
        ws_id = db.workspaces.save(ws)
        return db.chat_sessions.create(ws_id, "Fact Chat")

    def test_upsert_and_get_all(self, db: DatabaseManager) -> None:
        chat_id = self._create_ws_and_chat(db)
        db.chat_facts.upsert(chat_id, "color", "blue", importance=7)
        db.chat_facts.upsert(chat_id, "language", "Python")
        facts = db.chat_facts.get_all(chat_id)
        assert len(facts) == 2

    def test_upsert_updates(self, db: DatabaseManager) -> None:
        chat_id = self._create_ws_and_chat(db)
        db.chat_facts.upsert(chat_id, "key", "v1")
        db.chat_facts.upsert(chat_id, "key", "v2", importance=9)
        facts = db.chat_facts.get_all(chat_id)
        assert len(facts) == 1
        assert facts[0].value == "v2"
        assert facts[0].importance == 9

    def test_delete(self, db: DatabaseManager) -> None:
        chat_id = self._create_ws_and_chat(db)
        fid = db.chat_facts.upsert(chat_id, "temp", "x")
        assert db.chat_facts.delete(fid)
        assert db.chat_facts.count_for_chat(chat_id) == 0

    def test_count(self, db: DatabaseManager) -> None:
        chat_id = self._create_ws_and_chat(db)
        assert db.chat_facts.count_for_chat(chat_id) == 0
        db.chat_facts.upsert(chat_id, "a", "1")
        db.chat_facts.upsert(chat_id, "b", "2")
        assert db.chat_facts.count_for_chat(chat_id) == 2

    def test_isolation_between_chats(self, db: DatabaseManager) -> None:
        ws_id = self._create_ws_and_chat(db)
        chat_a = ws_id
        from models.domain import Workspace
        from models.enums import ModelCategory, RouterMode

        ws2 = Workspace(name="FactWS2", category=ModelCategory.GENERAL, router_mode=RouterMode.DISABLED)
        ws2_id = db.workspaces.save(ws2)
        chat_b = db.chat_sessions.create(ws2_id, "Other")
        db.chat_facts.upsert(chat_a, "secret", "value")
        assert db.chat_facts.count_for_chat(chat_b) == 0


# ── Chat summaries tests ──────────────────────────────────────────────────────


class TestChatSummaryRepository:
    def _create_ws_and_chat(self, db: DatabaseManager) -> int:
        from models.domain import Workspace
        from models.enums import ModelCategory, RouterMode

        ws = Workspace(name="SumTestWS", category=ModelCategory.GENERAL, router_mode=RouterMode.DISABLED)
        ws_id = db.workspaces.save(ws)
        return db.chat_sessions.create(ws_id, "Sum Chat")

    def test_save_and_get_recent(self, db: DatabaseManager) -> None:
        chat_id = self._create_ws_and_chat(db)
        db.chat_summaries.save(chat_id, "First summary")
        db.chat_summaries.save(chat_id, "Second summary")
        results = db.chat_summaries.get_recent(chat_id, limit=5)
        assert len(results) == 2
        assert results[0].summary == "Second summary"  # Most recent first

    def test_limit_respected(self, db: DatabaseManager) -> None:
        chat_id = self._create_ws_and_chat(db)
        for i in range(10):
            db.chat_summaries.save(chat_id, f"summary {i}")
        assert len(db.chat_summaries.get_recent(chat_id, limit=3)) == 3

    def test_delete_all_for_chat(self, db: DatabaseManager) -> None:
        chat_id = self._create_ws_and_chat(db)
        db.chat_summaries.save(chat_id, "s1")
        db.chat_summaries.save(chat_id, "s2")
        assert db.chat_summaries.delete_all_for_chat(chat_id) == 2
        assert db.chat_summaries.get_recent(chat_id) == []

    def test_isolation(self, db: DatabaseManager) -> None:
        chat_a = self._create_ws_and_chat(db)
        from models.domain import Workspace
        from models.enums import ModelCategory, RouterMode

        ws2 = Workspace(name="SumWS2", category=ModelCategory.GENERAL, router_mode=RouterMode.DISABLED)
        ws2_id = db.workspaces.save(ws2)
        chat_b = db.chat_sessions.create(ws2_id, "Other")
        db.chat_summaries.save(chat_a, "only on A")
        assert len(db.chat_summaries.get_recent(chat_b)) == 0


# ── Chat-aware message tests ──────────────────────────────────────────────────


class TestChatAwareMessages:
    def _create_ws_and_chat(self, db: DatabaseManager) -> int:
        from models.domain import Workspace
        from models.enums import ModelCategory, RouterMode

        ws = Workspace(name="MsgTestWS", category=ModelCategory.GENERAL, router_mode=RouterMode.DISABLED)
        ws_id = db.workspaces.save(ws)
        return db.chat_sessions.create(ws_id, "Msg Chat")

    def test_save_for_chat(self, db: DatabaseManager) -> None:
        chat_id = self._create_ws_and_chat(db)
        mid = db.chat.save_for_chat(chat_id, "user", "Hello chat!")
        assert mid is not None and mid > 0

    def test_get_by_token_budget(self, db: DatabaseManager) -> None:
        chat_id = self._create_ws_and_chat(db)
        db.chat.save_for_chat(chat_id, "user", "msg1")
        db.chat.save_for_chat(chat_id, "user", "msg2")
        messages = db.chat.get_by_token_budget(chat_id, max_tokens=1000)
        assert len(messages) == 2
        assert messages[-1].content == "msg2"

    def test_total_tokens_for_chat(self, db: DatabaseManager) -> None:
        chat_id = self._create_ws_and_chat(db)
        assert db.chat.total_tokens_for_chat(chat_id) == 0
        db.chat.save_for_chat(chat_id, "user", "test")
        assert db.chat.total_tokens_for_chat(chat_id) > 0

    def test_clear_for_chat(self, db: DatabaseManager) -> None:
        chat_id = self._create_ws_and_chat(db)
        db.chat.save_for_chat(chat_id, "user", "to delete")
        assert db.chat.clear_for_chat(chat_id) >= 1
        assert db.chat.total_tokens_for_chat(chat_id) == 0

    def test_message_isolation(self, db: DatabaseManager) -> None:
        chat_a = self._create_ws_and_chat(db)
        from models.domain import Workspace
        from models.enums import ModelCategory, RouterMode

        ws2 = Workspace(name="MsgIsolWS", category=ModelCategory.GENERAL, router_mode=RouterMode.DISABLED)
        ws2_id = db.workspaces.save(ws2)
        chat_b = db.chat_sessions.create(ws2_id, "Isolated")
        db.chat.save_for_chat(chat_a, "user", "only on A")
        assert len(db.chat.get_by_token_budget(chat_b, max_tokens=1000)) == 0


# ── ChatService tests ─────────────────────────────────────────────────────────


class TestChatService:
    def _create_ws(self, db: DatabaseManager) -> int:
        from models.domain import Workspace
        from models.enums import ModelCategory, RouterMode

        ws = Workspace(name="SvcTestWS", category=ModelCategory.GENERAL, router_mode=RouterMode.DISABLED)
        return db.workspaces.save(ws)

    def test_get_default_chat_creates_when_empty(self, db: DatabaseManager) -> None:
        from services.chat_service import ChatService

        svc = ChatService(db)
        ws_id = self._create_ws(db)
        chat_id = svc.get_default_chat(ws_id)
        chats = svc.get_chats(ws_id)
        assert len(chats) == 1
        assert chats[0].id == chat_id

    def test_create_chat_increments_count(self, db: DatabaseManager) -> None:
        from services.chat_service import ChatService

        svc = ChatService(db)
        ws_id = self._create_ws(db)
        svc.get_default_chat(ws_id)
        assert len(svc.get_chats(ws_id)) == 1
        svc.create_chat(ws_id)
        assert len(svc.get_chats(ws_id)) == 2

    def test_delete_chat_ensures_replacement(self, db: DatabaseManager) -> None:
        from services.chat_service import ChatService

        svc = ChatService(db)
        ws_id = self._create_ws(db)
        cid1 = svc.get_default_chat(ws_id)
        svc.create_chat(ws_id)
        replacement = svc.delete_chat(cid1, ws_id)
        chats = svc.get_chats(ws_id)
        assert len(chats) >= 1
        assert replacement in (c.id for c in chats)

    def test_rename_chat(self, db: DatabaseManager) -> None:
        from services.chat_service import ChatService

        svc = ChatService(db)
        ws_id = self._create_ws(db)
        cid = svc.get_default_chat(ws_id)
        assert svc.rename_chat(cid, "Renamed")
        chat = svc.get_chat(cid)
        assert chat is not None
        assert chat.name == "Renamed"
