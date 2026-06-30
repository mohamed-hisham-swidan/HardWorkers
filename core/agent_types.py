"""Agent runtime types — events, cancellation, and result types.

This module defines the discriminated union of events an agent can emit
during execution, plus the cancellation mechanism.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class CancellationError(Exception):
    """Raised when an operation is cancelled via a CancelToken."""


class CancelToken:
    """Thread-safe cancellation signal.

    Usage::

        token = CancelToken()
        # ... in another thread ...
        token.cancel("user stopped")
        # ... in the worker ...
        token.throw_if_cancelled()      # raises CancellationError
        reason = token.wait()           # blocks until cancelled, returns reason
    """

    def __init__(self) -> None:
        self._event = threading.Event()
        self._reason: str | None = None

    def cancel(self, reason: str = "cancelled") -> None:
        """Signal cancellation.  The first call determines *reason*."""
        if self._event.is_set():
            return
        self._reason = reason
        self._event.set()

    @property
    def cancelled(self) -> bool:
        """True if ``cancel()`` has been called."""
        return self._event.is_set()

    @property
    def reason(self) -> str | None:
        """The reason passed to ``cancel()``, or ``None`` if not cancelled."""
        return self._reason

    def throw_if_cancelled(self) -> None:
        """Raise :class:`CancellationError` if ``cancel()`` was called."""
        if self._event.is_set():
            raise CancellationError(self._reason or "cancelled")

    def wait(self) -> str | None:
        """Block until cancelled, then return the cancellation reason.

        This is a **synchronous** block.  Use ``throw_if_cancelled()``
        for non-blocking checks inside tight loops.
        """
        self._event.wait()
        return self._reason


# ── Agent Event Types ──────────────────────────────────────────────────────────


@dataclass
class ThinkingUpdate:
    """A streaming text delta produced by the LLM."""

    text: str = ""


@dataclass
class FinalAnswer:
    """The agent's final answer (terminal event)."""

    content: str = ""


@dataclass
class Error:
    """An error that occurred during agent execution.

    Fields:
        code: Machine-readable error code (e.g. ``"llm.timeout"``).
        message: Human-readable error description.
        recoverable: If ``True`` the agent *may* continue after handling.
    """

    code: str = ""
    message: str = ""
    recoverable: bool = False


# Discriminated union of all events an agent can emit during invocation.
AgentEvent = ThinkingUpdate | FinalAnswer | Error
