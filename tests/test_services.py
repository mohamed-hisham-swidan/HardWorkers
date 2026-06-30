"""Tests for service layer components."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.events import ChatCreatedEvent, EventBus, SettingsChangedEvent
from services.chat_service import ChatService


class TestEventBus:
    def test_emit_and_receive(self) -> None:
        bus = EventBus()
        received = []

        def handler(event: ChatCreatedEvent) -> None:
            received.append(event)

        bus.on("ChatCreatedEvent", handler)
        bus.emit(ChatCreatedEvent(chat_id=42))

        assert len(received) == 1
        assert received[0].chat_id == 42

    def test_off(self) -> None:
        bus = EventBus()
        received = []

        def handler(event: object) -> None:
            received.append(event)

        bus.on("TestEvent", handler)
        bus.off("TestEvent", handler)
        bus.emit(SettingsChangedEvent(section="test"))

        assert len(received) == 0

    def test_multiple_handlers(self) -> None:
        bus = EventBus()
        results = []

        def h1(e: object) -> None:
            results.append("h1")

        def h2(e: object) -> None:
            results.append("h2")

        bus.on("SettingsChangedEvent", h1)
        bus.on("SettingsChangedEvent", h2)
        bus.emit(SettingsChangedEvent(section="test"))

        assert results == ["h1", "h2"]

    def test_handler_exception_does_not_block(self) -> None:
        bus = EventBus()
        results = []

        def failing(e: object) -> None:
            raise ValueError("oops")

        def working(e: object) -> None:
            results.append("ok")

        bus.on("SettingsChangedEvent", failing)
        bus.on("SettingsChangedEvent", working)
        bus.emit(SettingsChangedEvent(section="test"))

        assert results == ["ok"]

    def test_clear(self) -> None:
        bus = EventBus()
        bus.on("SettingsChangedEvent", lambda e: None)
        bus.clear()
        assert bus._handlers == {}  # type: ignore


class TestChatService:
    @pytest.fixture
    def db(self, tmp_path: Path):
        from config.settings import DatabaseConfig
        from database.repositories import DatabaseManager

        config = DatabaseConfig(path=tmp_path / "test.db")
        manager = DatabaseManager(config)
        yield manager
        manager.close()

    def test_get_default_chat_creates_when_empty(self, db) -> None:
        ws = db.workspaces.get_by_name("Default")
        assert ws is not None
        svc = ChatService(db)
        chat_id = svc.get_default_chat(ws.id)
        assert chat_id > 0

    def test_create_chat_increments_count(self, db) -> None:
        ws = db.workspaces.get_by_name("Default")
        assert ws is not None
        svc = ChatService(db)
        initial = len(svc.get_chats(ws.id))
        svc.create_chat(ws.id)
        after = len(svc.get_chats(ws.id))
        assert after == initial + 1

    def test_rename_chat(self, db) -> None:
        ws = db.workspaces.get_by_name("Default")
        assert ws is not None
        svc = ChatService(db)
        chat_id = svc.create_chat(ws.id, "Original")
        svc.rename_chat(chat_id, "Renamed")
        chat = svc.get_chat(chat_id)
        assert chat is not None
        assert chat.name == "Renamed"

    def test_pin_chat(self, db) -> None:
        ws = db.workspaces.get_by_name("Default")
        assert ws is not None
        svc = ChatService(db)
        chat_id = svc.create_chat(ws.id)
        svc.pin_chat(chat_id, True)
        chat = svc.get_chat(chat_id)
        assert chat is not None
        assert chat.pinned is True

    def test_delete_chat_ensures_replacement(self, db) -> None:
        ws = db.workspaces.get_by_name("Default")
        assert ws is not None
        svc = ChatService(db)
        chat_id = svc.create_chat(ws.id)
        replacement = svc.delete_chat(chat_id, ws.id)
        assert replacement > 0
        assert replacement != chat_id
