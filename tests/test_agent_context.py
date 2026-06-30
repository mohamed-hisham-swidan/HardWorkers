"""Tests for AgentContext and its sub-context types."""

from __future__ import annotations

import uuid

import pytest

from core.agent_context import (
    AgentContext,
    ConversationContext,
    MemoryContext,
    TokenBudget,
    WorkspaceContext,
)

# ── ConversationContext ────────────────────────────────────────────────────────


class TestConversationContext:
    def test_defaults(self) -> None:
        ctx = ConversationContext()
        assert ctx.system_prompt == ""
        assert ctx.messages == []
        assert ctx.user_message == ""
        assert ctx.image_base64 is None

    def test_full_construction(self) -> None:
        ctx = ConversationContext(
            system_prompt="You are a helpful assistant.",
            messages=[{"role": "user", "content": "hi"}],
            user_message="hello",
            image_base64="abc123",
        )
        assert ctx.system_prompt == "You are a helpful assistant."
        assert ctx.messages == [{"role": "user", "content": "hi"}]
        assert ctx.user_message == "hello"
        assert ctx.image_base64 == "abc123"

    def test_messages_shared_reference(self) -> None:
        original = [{"role": "user", "content": "test"}]
        ctx = ConversationContext(messages=original)
        original.append({"role": "assistant", "content": "response"})
        assert len(ctx.messages) == 2  # dataclass does not copy the list


# ── WorkspaceContext ───────────────────────────────────────────────────────────


class TestWorkspaceContext:
    def test_default_model(self) -> None:
        ws = WorkspaceContext()
        assert ws.model == ""

    def test_custom_model(self) -> None:
        ws = WorkspaceContext(model="qwen2.5:latest")
        assert ws.model == "qwen2.5:latest"

    def test_is_frozen(self) -> None:
        ws = WorkspaceContext(model="llama3")
        with pytest.raises(AttributeError):
            ws.model = "other"  # type: ignore[misc]


# ── MemoryContext ──────────────────────────────────────────────────────────────


class TestMemoryContext:
    def test_default_facts(self) -> None:
        mem = MemoryContext()
        assert mem.facts == []

    def test_custom_facts(self) -> None:
        facts = [{"key": "language", "value": "python", "score": 0.95}]
        mem = MemoryContext(facts=facts)
        assert len(mem.facts) == 1
        assert mem.facts[0]["key"] == "language"

    def test_facts_shared_reference(self) -> None:
        original = [{"key": "a", "value": "1"}]
        mem = MemoryContext(facts=original)
        original.append({"key": "b", "value": "2"})
        assert len(mem.facts) == 2  # dataclass does not copy the list


# ── TokenBudget ────────────────────────────────────────────────────────────────


class TestTokenBudget:
    def test_defaults(self) -> None:
        b = TokenBudget()
        assert b.max_input_tokens == 32_000
        assert b.max_output_tokens == 4_096
        assert b.max_total_tokens == 36_096

    def test_custom_values(self) -> None:
        b = TokenBudget(max_input_tokens=16_000, max_output_tokens=2_000, max_total_tokens=18_000)
        assert b.max_input_tokens == 16_000
        assert b.max_output_tokens == 2_000
        assert b.max_total_tokens == 18_000


# ── AgentContext ───────────────────────────────────────────────────────────────


class TestAgentContext:
    def test_default_invocation_id(self) -> None:
        ctx = AgentContext()
        assert isinstance(ctx.invocation_id, str)
        assert uuid.UUID(ctx.invocation_id).version == 4

    def test_unique_invocation_ids(self) -> None:
        ids = {AgentContext().invocation_id for _ in range(100)}
        assert len(ids) == 100

    def test_default_sub_contexts(self) -> None:
        ctx = AgentContext()
        assert isinstance(ctx.conversation, ConversationContext)
        assert isinstance(ctx.workspace, WorkspaceContext)
        assert isinstance(ctx.memory, MemoryContext)
        assert isinstance(ctx.token_budget, TokenBudget)
        assert ctx.metadata == {}

    def test_full_construction(self) -> None:
        ctx = AgentContext(
            conversation=ConversationContext(
                system_prompt="test prompt",
                messages=[{"role": "user", "content": "hi"}],
                user_message="hello",
            ),
            workspace=WorkspaceContext(model="gpt-4"),
            memory=MemoryContext(facts=[{"key": "lang", "value": "py"}]),
            token_budget=TokenBudget(max_input_tokens=8_000),
            metadata={"trace_id": "abc"},
            invocation_id="custom-id",
        )
        assert ctx.invocation_id == "custom-id"
        assert ctx.conversation.system_prompt == "test prompt"
        assert ctx.workspace.model == "gpt-4"
        assert ctx.memory.facts[0]["key"] == "lang"
        assert ctx.token_budget.max_input_tokens == 8_000
        assert ctx.metadata["trace_id"] == "abc"

    def test_metadata_default_is_empty(self) -> None:
        ctx = AgentContext()
        assert ctx.metadata == {}

    def test_can_attach_arbitrary_metadata(self) -> None:
        ctx = AgentContext(metadata={"user_id": "u1", "session_id": "s1"})
        assert ctx.metadata["user_id"] == "u1"
        assert ctx.metadata["session_id"] == "s1"
