"""Tests for AgentRunner, InvokeOptions, and InvocationStatus."""

from __future__ import annotations

import threading
import time

import pytest

from core.agent_context import (
    AgentContext,
    ConversationContext,
    TokenBudget,
    WorkspaceContext,
)
from core.agent_runner import AgentRunner, InvocationStatus, InvokeOptions
from core.agent_types import CancelToken, Error, FinalAnswer, ThinkingUpdate

# ── Mock clients ────────────────────────────────────────────────────────────


class MockOllamaClient:
    def __init__(
        self,
        chunks: list[str] | None = None,
        fail: str | None = None,
        chunk_delay: float = 0.005,
    ) -> None:
        self._chunks = chunks or ["Hello", " ", "world"]
        self._fail = fail
        self._chunk_delay = chunk_delay
        self.call_kwargs: dict = {}

    def stream_chat(
        self,
        *,
        model: str,
        system_prompt: str,
        history: list,
        user_message: str,
        image_base64: str | None,
        on_chunk,
        on_done,
        on_error,
        stop_event: threading.Event,
    ) -> None:
        self.call_kwargs.update(
            model=model,
            system_prompt=system_prompt,
            history=history,
            user_message=user_message,
            image_base64=image_base64,
        )
        if self._fail is not None:
            on_error(self._fail)
            return
        for chunk in self._chunks:
            if stop_event.is_set():
                return
            on_chunk(chunk)
            time.sleep(self._chunk_delay)
        on_done()


class MockApiClient:
    def __init__(
        self,
        chunks: list[str] | None = None,
        fail: str | None = None,
        chunk_delay: float = 0.005,
    ) -> None:
        self._chunks = chunks or ["API", " ", "response"]
        self._fail = fail
        self._chunk_delay = chunk_delay
        self.call_kwargs: dict = {}

    def stream_chat(
        self,
        *,
        system_prompt: str,
        history: list,
        user_message: str,
        image_base64: str | None,
        on_chunk,
        on_done,
        on_error,
        stop_event: threading.Event,
    ) -> None:
        self.call_kwargs.update(
            system_prompt=system_prompt,
            history=history,
            user_message=user_message,
            image_base64=image_base64,
        )
        if self._fail is not None:
            on_error(self._fail)
            return
        for chunk in self._chunks:
            if stop_event.is_set():
                return
            on_chunk(chunk)
            time.sleep(self._chunk_delay)
        on_done()


class MockModelManager:
    def __init__(self, api_models: set[str] | None = None) -> None:
        self._api = api_models or set()

    def is_api_model(self, name: str) -> bool:
        return name in self._api


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def context() -> AgentContext:
    return AgentContext(
        conversation=ConversationContext(
            system_prompt="Test system prompt",
            messages=[{"role": "user", "content": "hi"}],
            user_message="what is your name?",
        ),
        workspace=WorkspaceContext(model="test-model"),
        token_budget=TokenBudget(max_output_tokens=100),
    )


# ── InvokeOptions ───────────────────────────────────────────────────────────


class TestInvokeOptions:
    def test_defaults(self) -> None:
        opts = InvokeOptions()
        assert opts.model is None
        assert opts.streaming is True
        assert opts.cancel_token is None

    def test_custom_values(self) -> None:
        token = CancelToken()
        opts = InvokeOptions(model="gpt-4", streaming=False, cancel_token=token)
        assert opts.model == "gpt-4"
        assert opts.streaming is False
        assert opts.cancel_token is token


# ── InvocationStatus ────────────────────────────────────────────────────────


class TestInvocationStatus:
    def test_default_fields(self) -> None:
        s = InvocationStatus(invocation_id="abc", agent_type="core.chat", state="running", started_at=100.0)
        assert s.invocation_id == "abc"
        assert s.agent_type == "core.chat"
        assert s.state == "running"
        assert s.started_at == 100.0
        assert s.finished_at is None


# ── AgentRunner — Ollama streaming ──────────────────────────────────────────


class TestAgentRunnerOllama:
    def test_streaming_yields_thinking_and_final_answer(self, context: AgentContext) -> None:
        ollama = MockOllamaClient()
        runner = AgentRunner(ollama_client=ollama)
        events = list(runner.invoke("core.chat", context))

        thinking = [e for e in events if isinstance(e, ThinkingUpdate)]
        final = [e for e in events if isinstance(e, FinalAnswer)]

        assert len(thinking) == 3
        assert thinking[0].text == "Hello"
        assert thinking[1].text == " "
        assert thinking[2].text == "world"

        assert len(final) == 1
        assert final[0].content == "Hello world"

    def test_non_streaming_omits_thinking_updates(self, context: AgentContext) -> None:
        ollama = MockOllamaClient()
        runner = AgentRunner(ollama_client=ollama)
        events = list(runner.invoke("core.chat", context, InvokeOptions(streaming=False)))

        thinking = [e for e in events if isinstance(e, ThinkingUpdate)]
        final = [e for e in events if isinstance(e, FinalAnswer)]

        assert len(thinking) == 0
        assert len(final) == 1
        assert final[0].content == "Hello world"

    def test_completed_status(self, context: AgentContext) -> None:
        ollama = MockOllamaClient()
        runner = AgentRunner(ollama_client=ollama)
        list(runner.invoke("core.chat", context))

        status = runner.get_status(context.invocation_id)
        assert status is not None
        assert status.state == "completed"
        assert status.finished_at is not None

    def test_passes_through_call_parameters(self, context: AgentContext) -> None:
        ollama = MockOllamaClient()
        runner = AgentRunner(ollama_client=ollama)
        list(runner.invoke("core.chat", context))

        kwargs = ollama.call_kwargs
        assert kwargs["model"] == "test-model"
        assert kwargs["system_prompt"] == "Test system prompt"
        assert kwargs["history"] == [{"role": "user", "content": "hi"}]
        assert kwargs["user_message"] == "what is your name?"
        assert kwargs["image_base64"] is None

    def test_passes_image_base64(self, context: AgentContext) -> None:
        ollama = MockOllamaClient()
        context.conversation.image_base64 = "abc123"
        runner = AgentRunner(ollama_client=ollama)
        list(runner.invoke("core.chat", context))

        assert ollama.call_kwargs["image_base64"] == "abc123"

    def test_ollama_client_none_yields_error(self, context: AgentContext) -> None:
        runner = AgentRunner(ollama_client=None)
        events = list(runner.invoke("core.chat", context))

        assert len(events) == 1
        err = events[0]
        assert isinstance(err, Error)
        assert err.code == "runtime.config"
        assert "ollama" in err.message.lower()

    def test_ollama_failure_yields_error(self, context: AgentContext) -> None:
        ollama = MockOllamaClient(fail="Connection refused")
        runner = AgentRunner(ollama_client=ollama)
        events = list(runner.invoke("core.chat", context))

        assert len(events) == 1
        err = events[0]
        assert isinstance(err, Error)
        assert err.code == "llm.error"
        assert "Connection refused" in err.message
        assert err.recoverable is False


# ── AgentRunner — API model routing ─────────────────────────────────────────


class TestAgentRunnerApi:
    def test_api_routing_yields_events(self, context: AgentContext) -> None:
        api_client = MockApiClient()
        mm = MockModelManager(api_models={"test-model"})

        def factory(_model: str) -> MockApiClient:
            return api_client

        runner = AgentRunner(model_manager=mm, api_client_factory=factory)
        events = list(runner.invoke("core.chat", context))

        thinking = [e for e in events if isinstance(e, ThinkingUpdate)]
        final = [e for e in events if isinstance(e, FinalAnswer)]

        assert len(thinking) == 3
        assert len(final) == 1
        assert final[0].content == "API response"

    def test_api_passes_call_parameters(self, context: AgentContext) -> None:
        api_client = MockApiClient()
        mm = MockModelManager(api_models={"test-model"})

        def factory(_model: str) -> MockApiClient:
            return api_client

        runner = AgentRunner(model_manager=mm, api_client_factory=factory)
        context.conversation.image_base64 = "imgdata"
        list(runner.invoke("core.chat", context))

        kwargs = api_client.call_kwargs
        assert kwargs["system_prompt"] == "Test system prompt"
        assert kwargs["image_base64"] == "imgdata"

    def test_api_factory_none_yields_error(self, context: AgentContext) -> None:
        mm = MockModelManager(api_models={"test-model"})
        runner = AgentRunner(model_manager=mm, api_client_factory=None)
        events = list(runner.invoke("core.chat", context))

        assert len(events) == 1
        assert isinstance(events[0], Error)
        assert "api client factory" in events[0].message.lower()

    def test_api_failure_yields_error(self, context: AgentContext) -> None:
        api_client = MockApiClient(fail="Rate limited")
        mm = MockModelManager(api_models={"test-model"})

        def factory(_model: str) -> MockApiClient:
            return api_client

        runner = AgentRunner(model_manager=mm, api_client_factory=factory)
        events = list(runner.invoke("core.chat", context))

        assert len(events) == 1
        assert isinstance(events[0], Error)
        assert "Rate limited" in events[0].message


# ── AgentRunner — no model ──────────────────────────────────────────────────


class TestAgentRunnerNoModel:
    def test_no_model_yields_config_error(self) -> None:
        ctx = AgentContext(workspace=WorkspaceContext(model=""))
        runner = AgentRunner()
        events = list(runner.invoke("core.chat", ctx))

        assert len(events) == 1
        err = events[0]
        assert isinstance(err, Error)
        assert err.code == "runtime.config"
        assert "no model" in err.message.lower()

    def test_options_model_overrides_empty_workspace(self) -> None:
        ollama = MockOllamaClient()
        ctx = AgentContext(workspace=WorkspaceContext(model=""))
        runner = AgentRunner(ollama_client=ollama)
        list(runner.invoke("core.chat", ctx, InvokeOptions(model="override-model")))

        assert ollama.call_kwargs["model"] == "override-model"


# ── AgentRunner — cancellation ──────────────────────────────────────────────


class TestAgentRunnerCancellation:
    def test_cancel_stops_mid_stream(self, context: AgentContext) -> None:
        ollama = MockOllamaClient(chunks=["a", "b", "c", "d", "e"], chunk_delay=0.05)
        runner = AgentRunner(ollama_client=ollama)
        collected: list = []

        def _consume() -> None:
            for ev in runner.invoke("core.chat", context):
                collected.append(ev)

        t = threading.Thread(target=_consume, daemon=True)
        t.start()
        time.sleep(0.07)
        runner.cancel(context.invocation_id)
        t.join(timeout=3)

        assert len(collected) > 0
        assert not any(isinstance(e, FinalAnswer) for e in collected)

    def test_cancel_sets_status_cancelled(self, context: AgentContext) -> None:
        ollama = MockOllamaClient(chunks=["a", "b", "c", "d", "e"], chunk_delay=0.05)
        runner = AgentRunner(ollama_client=ollama)

        def _consume() -> None:
            for _ in runner.invoke("core.chat", context):
                pass

        t = threading.Thread(target=_consume, daemon=True)
        t.start()
        time.sleep(0.07)
        runner.cancel(context.invocation_id)
        t.join(timeout=3)

        status = runner.get_status(context.invocation_id)
        assert status is not None
        assert status.state == "cancelled"
        assert status.finished_at is not None

    def test_pre_cancelled_token_yields_no_events(self, context: AgentContext) -> None:
        token = CancelToken()
        token.cancel("explicit")
        runner = AgentRunner(ollama_client=MockOllamaClient())
        events = list(runner.invoke("core.chat", context, InvokeOptions(cancel_token=token)))

        assert len(events) == 0

    def test_cancel_unknown_id_is_noop(self) -> None:
        runner = AgentRunner()
        runner.cancel("nonexistent")  # should not raise

    def test_cancel_reason_stored(self, context: AgentContext) -> None:
        ollama = MockOllamaClient(chunks=["a", "b"], chunk_delay=0.05)
        runner = AgentRunner(ollama_client=ollama)

        def _consume() -> None:
            for _ in runner.invoke("core.chat", context):
                pass

        t = threading.Thread(target=_consume, daemon=True)
        t.start()
        time.sleep(0.07)
        runner.cancel(context.invocation_id, reason="user_stopped")
        t.join(timeout=3)

        status = runner.get_status(context.invocation_id)
        assert status is not None
        assert status.state == "cancelled"


# ── AgentRunner — status ────────────────────────────────────────────────────


class TestAgentRunnerStatus:
    def test_get_status_unknown(self) -> None:
        runner = AgentRunner()
        assert runner.get_status("nonexistent") is None

    def test_get_status_while_running(self, context: AgentContext) -> None:
        ollama = MockOllamaClient(chunks=["a", "b", "c"])
        runner = AgentRunner(ollama_client=ollama)
        statuses: list[InvocationStatus | None] = []

        def _consume() -> None:
            for _ in runner.invoke("core.chat", context):
                statuses.append(runner.get_status(context.invocation_id))

        t = threading.Thread(target=_consume, daemon=True)
        t.start()
        t.join(timeout=3)

        for s in statuses:
            assert s is not None
            assert s.state in ("running", "completed")

    def test_list_active_excludes_completed(self, context: AgentContext) -> None:
        ollama = MockOllamaClient()
        runner = AgentRunner(ollama_client=ollama)
        list(runner.invoke("core.chat", context))
        assert runner.list_active() == []

    def test_list_active_includes_running(self, context: AgentContext) -> None:
        ollama = MockOllamaClient(chunks=["a", "b", "c"], chunk_delay=0.05)
        runner = AgentRunner(ollama_client=ollama)

        def _consume() -> None:
            for _ in runner.invoke("core.chat", context):
                pass

        t = threading.Thread(target=_consume, daemon=True)
        t.start()
        time.sleep(0.03)

        active = runner.list_active()
        assert len(active) == 1
        assert active[0].invocation_id == context.invocation_id
        assert active[0].state == "running"

        t.join(timeout=3)


# ── AgentRunner — model override ────────────────────────────────────────────


class TestAgentRunnerModelOverride:
    def test_options_model_overrides_workspace(self, context: AgentContext) -> None:
        ollama = MockOllamaClient()
        runner = AgentRunner(ollama_client=ollama)
        list(runner.invoke("core.chat", context, InvokeOptions(model="override-model")))
        assert ollama.call_kwargs["model"] == "override-model"


# ── AgentRunner — edge cases ────────────────────────────────────────────────


class TestAgentRunnerEdgeCases:
    def test_empty_history(self) -> None:
        ctx = AgentContext(
            conversation=ConversationContext(user_message="hello"),
            workspace=WorkspaceContext(model="test-model"),
        )
        ollama = MockOllamaClient()
        runner = AgentRunner(ollama_client=ollama)
        events = list(runner.invoke("core.chat", ctx))

        assert any(isinstance(e, FinalAnswer) for e in events)
        assert ollama.call_kwargs["history"] == []
        assert ollama.call_kwargs["user_message"] == "hello"

    def test_invoke_with_default_options(self, context: AgentContext) -> None:
        ollama = MockOllamaClient()
        runner = AgentRunner(ollama_client=ollama)
        events = list(runner.invoke("core.chat", context, None))
        assert any(isinstance(e, FinalAnswer) for e in events)
