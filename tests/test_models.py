"""Unit tests for domain models and enums."""

from __future__ import annotations

import pytest

from models.domain import (
    ChatMemoryFact,
    ChatSession,
    ChatSummary,
    MemoryProfile,
    Message,
    ModelRegistryEntry,
    RouterDecision,
    SearchResult,
    UserFact,
    Workspace,
)
from models.enums import (
    AppStatus,
    MemoryMode,
    MessageRole,
    ModelCategory,
    ModelProvider,
    RouterMode,
)


class TestEnums:
    def test_message_role_values(self) -> None:
        assert MessageRole.USER == "user"
        assert MessageRole.ASSISTANT == "assistant"
        assert MessageRole.SYSTEM == "system"

    def test_app_status_values(self) -> None:
        assert AppStatus.READY == "Ready"
        assert AppStatus.GENERATING == "Generating\u2026"

    def test_model_provider_includes_all(self) -> None:
        providers = {p.value for p in ModelProvider}
        assert "openai" in providers
        assert "anthropic" in providers
        assert "openrouter" in providers
        assert "groq" in providers
        assert "gemini" in providers
        assert "deepseek" in providers
        assert "together" in providers
        assert "custom" in providers

    def test_model_category_values(self) -> None:
        assert ModelCategory.GENERAL == "General"
        assert ModelCategory.CODING == "Coding"

    def test_memory_mode_values(self) -> None:
        assert MemoryMode.NONE == "none"
        assert MemoryMode.SHARED == "shared"
        assert MemoryMode.DEDICATED == "dedicated"

    def test_router_mode_values(self) -> None:
        assert RouterMode.DISABLED == "disabled"
        assert RouterMode.AUTO == "auto"
        assert RouterMode.CATEGORY == "category"


class TestMessage:
    def test_create_valid(self) -> None:
        msg = Message(role=MessageRole.USER, content="Hello")
        assert msg.content == "Hello"
        assert msg.role == MessageRole.USER

    def test_empty_content_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            Message(role=MessageRole.USER, content="")

    def test_to_api_dict(self) -> None:
        msg = Message(role=MessageRole.USER, content="Hello")
        assert msg.to_api_dict() == {"role": "user", "content": "Hello"}


class TestChatSession:
    def test_create_valid(self) -> None:
        s = ChatSession(workspace_id=1, name="Test Chat")
        assert s.name == "Test Chat"
        assert s.pinned is False

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            ChatSession(workspace_id=1, name="")

    def test_display_name(self) -> None:
        s = ChatSession(workspace_id=1, name="My Chat")
        assert s.display_name == "My Chat"


class TestChatMemoryFact:
    def test_create_valid(self) -> None:
        f = ChatMemoryFact(chat_id=1, key="name", value="Alice")
        assert f.key == "name"
        assert f.importance == 5

    def test_invalid_importance_raises(self) -> None:
        with pytest.raises(ValueError, match="Importance"):
            ChatMemoryFact(chat_id=1, key="name", value="Alice", importance=99)


class TestChatSummary:
    def test_create_valid(self) -> None:
        s = ChatSummary(chat_id=1, summary="Key insight")
        assert s.summary == "Key insight"

    def test_empty_summary_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            ChatSummary(chat_id=1, summary="")


class TestUserFact:
    def test_create_valid(self) -> None:
        f = UserFact(key="name", value="Bob")
        assert f.key == "name"
        assert f.importance == 5

    def test_to_embedding_text(self) -> None:
        f = UserFact(key="name", value="Bob")
        assert "Key: name" in f.to_embedding_text()
        assert "Value: Bob" in f.to_embedding_text()

    def test_invalid_importance_raises(self) -> None:
        with pytest.raises(ValueError, match="Importance"):
            UserFact(key="name", value="Bob", importance=0)


class TestSearchResult:
    def test_create_valid(self) -> None:
        r = SearchResult(score=0.95, key="test", value="result")
        assert r.score == 0.95

    def test_invalid_score_raises(self) -> None:
        with pytest.raises(ValueError, match="Score"):
            SearchResult(score=1.5, key="test", value="result")


class TestModelRegistryEntry:
    def test_is_ollama(self) -> None:
        e = ModelRegistryEntry(name="test", provider=ModelProvider.OLLAMA)
        assert e.is_ollama is True
        assert e.is_api is False

    def test_is_api(self) -> None:
        e = ModelRegistryEntry(name="test", provider=ModelProvider.OPENAI)
        assert e.is_ollama is False
        assert e.is_api is True

    def test_display_label_ollama(self) -> None:
        e = ModelRegistryEntry(name="llama3", provider=ModelProvider.OLLAMA)
        assert "\U0001f999" in e.display_label()

    def test_display_label_api(self) -> None:
        e = ModelRegistryEntry(name="gpt-4", provider=ModelProvider.OPENAI)
        assert "\U0001f310" in e.display_label()

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            ModelRegistryEntry(name="")


class TestMemoryProfile:
    def test_create_valid(self) -> None:
        p = MemoryProfile(name="Research")
        assert p.name == "Research"

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            MemoryProfile(name="")


class TestWorkspace:
    def test_create_valid(self) -> None:
        w = Workspace(name="Default")
        assert w.name == "Default"
        assert w.router_mode == RouterMode.DISABLED

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            Workspace(name="")


class TestRouterDecision:
    def test_create(self) -> None:
        d = RouterDecision(
            chosen_model="gpt-4",
            confidence=0.9,
            detected_category="Coding",
            reason="keyword match",
        )
        assert d.chosen_model == "gpt-4"
        assert d.confidence == 0.9
