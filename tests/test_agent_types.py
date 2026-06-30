"""Tests for CancelToken, AgentEvent types, and the AgentEvent union."""

from __future__ import annotations

import threading
import time

import pytest

from core.agent_types import (
    CancellationError,
    CancelToken,
    Error,
    FinalAnswer,
    ThinkingUpdate,
)

# ── CancelToken ────────────────────────────────────────────────────────────────


class TestCancelToken:
    def test_default_not_cancelled(self) -> None:
        token = CancelToken()
        assert token.cancelled is False
        assert token.reason is None

    def test_cancel_sets_flag(self) -> None:
        token = CancelToken()
        token.cancel("timeout")
        assert token.cancelled is True

    def test_cancel_stores_reason(self) -> None:
        token = CancelToken()
        token.cancel("user_stopped")
        assert token.reason == "user_stopped"

    def test_throw_if_cancelled_before_cancel(self) -> None:
        token = CancelToken()
        token.throw_if_cancelled()  # must not raise

    def test_throw_if_cancelled_after_cancel(self) -> None:
        token = CancelToken()
        token.cancel("test")
        with pytest.raises(CancellationError, match="test"):
            token.throw_if_cancelled()

    def test_throw_if_cancelled_reason_default(self) -> None:
        token = CancelToken()
        token.cancel()
        with pytest.raises(CancellationError, match="cancelled"):
            token.throw_if_cancelled()

    def test_multiple_cancel_ignores_later(self) -> None:
        token = CancelToken()
        token.cancel("first")
        token.cancel("second")
        assert token.reason == "first"

    def test_wait_blocks_and_returns_reason(self) -> None:
        token = CancelToken()

        def delayed_cancel() -> None:
            time.sleep(0.05)
            token.cancel("delayed")

        t = threading.Thread(target=delayed_cancel, daemon=True)
        t.start()
        reason = token.wait()
        assert reason == "delayed"
        t.join(timeout=1)

    def test_wait_default_reason(self) -> None:
        token = CancelToken()

        def cancel_no_reason() -> None:
            time.sleep(0.05)
            token.cancel()

        t = threading.Thread(target=cancel_no_reason, daemon=True)
        t.start()
        reason = token.wait()
        assert reason == "cancelled"
        t.join(timeout=1)

    def test_cancel_is_idempotent(self) -> None:
        token = CancelToken()
        token.cancel("once")
        token.cancel("twice")
        assert token.reason == "once"
        assert token.cancelled is True


# ── Agent Events ───────────────────────────────────────────────────────────────


class TestThinkingUpdate:
    def test_default_text(self) -> None:
        event = ThinkingUpdate()
        assert event.text == ""

    def test_custom_text(self) -> None:
        event = ThinkingUpdate(text="Hello")
        assert event.text == "Hello"


class TestFinalAnswer:
    def test_default_content(self) -> None:
        event = FinalAnswer()
        assert event.content == ""

    def test_custom_content(self) -> None:
        event = FinalAnswer(content="The answer is 42.")
        assert event.content == "The answer is 42."


class TestError:
    def test_defaults(self) -> None:
        err = Error()
        assert err.code == ""
        assert err.message == ""
        assert err.recoverable is False

    def test_custom_fields(self) -> None:
        err = Error(code="llm.timeout", message="Request timed out", recoverable=False)
        assert err.code == "llm.timeout"
        assert err.message == "Request timed out"
        assert err.recoverable is False

    def test_recoverable_true(self) -> None:
        err = Error(code="tool.timeout", message="Tool timed out", recoverable=True)
        assert err.recoverable is True


# ── AgentEvent Union ──────────────────────────────────────────────────────────


class TestAgentEventUnion:
    def test_isinstance_thinking_update(self) -> None:
        from core.agent_types import AgentEvent

        event: AgentEvent = ThinkingUpdate(text="thinking...")
        assert isinstance(event, ThinkingUpdate)
        assert not isinstance(event, FinalAnswer)
        assert not isinstance(event, Error)

    def test_isinstance_final_answer(self) -> None:
        from core.agent_types import AgentEvent

        event: AgentEvent = FinalAnswer(content="done")
        assert isinstance(event, FinalAnswer)
        assert not isinstance(event, ThinkingUpdate)
        assert not isinstance(event, Error)

    def test_isinstance_error(self) -> None:
        from core.agent_types import AgentEvent

        event: AgentEvent = Error(code="fail", message="fail", recoverable=False)
        assert isinstance(event, Error)
        assert not isinstance(event, ThinkingUpdate)
        assert not isinstance(event, FinalAnswer)

    def test_match_statement_thinking(self) -> None:
        from core.agent_types import AgentEvent

        event: AgentEvent = ThinkingUpdate(text="token")
        match event:
            case ThinkingUpdate(text=t):
                assert t == "token"
            case _:
                pytest.fail("Should have matched ThinkingUpdate")

    def test_match_statement_final_answer(self) -> None:
        from core.agent_types import AgentEvent

        event: AgentEvent = FinalAnswer(content="answer")
        match event:
            case FinalAnswer(content=c):
                assert c == "answer"
            case _:
                pytest.fail("Should have matched FinalAnswer")

    def test_match_statement_error(self) -> None:
        from core.agent_types import AgentEvent

        event: AgentEvent = Error(code="err", message="msg", recoverable=False)
        match event:
            case Error(code=c, message=m):
                assert c == "err"
                assert m == "msg"
            case _:
                pytest.fail("Should have matched Error")
