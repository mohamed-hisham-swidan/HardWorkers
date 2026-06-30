"""Phase B: AgentRunner — thin orchestration layer for LLM invocation.

The AgentRunner owns the LLM transport loop.  It accepts an :class:`AgentContext`
and yields :class:`AgentEvent` objects (:class:`ThinkingUpdate`, :class:`FinalAnswer`,
:class:`Error`).

No tool loop, no permission checker, no approval gates — those are deferred
to post-v4.0.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

from core.agent_context import AgentContext
from core.agent_types import (
    AgentEvent,
    CancellationError,
    CancelToken,
    Error,
    FinalAnswer,
    ThinkingUpdate,
)

_SENTINEL: Any = object()


@dataclass
class InvokeOptions:
    """Per-invocation options passed to :meth:`AgentRunner.invoke`.

    Fields:
        model: Override the workspace-default model name.
        streaming: When True yield ``ThinkingUpdate`` events mid-stream.
        cancel_token: Token used to signal cancellation.
    """

    model: str | None = None
    streaming: bool = True
    cancel_token: CancelToken | None = None


@dataclass
class InvocationStatus:
    """Snapshot of a single invocation at a point in time."""

    invocation_id: str
    agent_type: str
    state: str  # "running" | "completed" | "cancelled" | "failed"
    started_at: float
    finished_at: float | None = None


class AgentRunner:
    """Thin LLM-invocation orchestrator.

    Construct with the services it needs; call :meth:`invoke` to run an LLM
    request and iterate over the yielded events.
    """

    def __init__(
        self,
        ollama_client: Any | None = None,
        model_manager: Any | None = None,
        api_client_factory: Any | None = None,
    ) -> None:
        self._ollama = ollama_client
        self._model_manager = model_manager
        self._api_client_factory = api_client_factory
        self._invocations: dict[str, InvocationStatus] = {}
        self._cancel_tokens: dict[str, CancelToken] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def invoke(
        self,
        agent_type: str,
        context: AgentContext,
        options: InvokeOptions | None = None,
    ) -> Generator[AgentEvent, None, None]:
        """Run an LLM invocation and yield events.

        Yields:
            ``ThinkingUpdate`` (one per chunk when *streaming* is True),
            ``FinalAnswer`` (once), or ``Error`` (on failure).
        """
        opts = options or InvokeOptions()
        cancel_token = opts.cancel_token or CancelToken()
        invocation_id = context.invocation_id
        model = _resolve_model(context, opts)

        self._register(invocation_id, agent_type, cancel_token)

        try:
            if model is None:
                yield Error(
                    code="runtime.config",
                    message="No model specified in context or options",
                    recoverable=False,
                )
                return

            if self._is_api_model(model):
                yield from self._run_api(context, model, opts, cancel_token)
            else:
                yield from self._run_ollama(context, model, opts, cancel_token)

            if cancel_token.cancelled:
                self._set_state(invocation_id, "cancelled")
            else:
                self._set_state(invocation_id, "completed")

        except CancellationError:
            self._set_state(invocation_id, "cancelled")
        except Exception as exc:
            self._set_state(invocation_id, "failed")
            yield Error(code="runtime.internal", message=str(exc), recoverable=False)
        finally:
            self._cleanup(invocation_id)

    def cancel(self, invocation_id: str, reason: str = "cancelled") -> None:
        """Request cancellation of a running invocation."""
        with self._lock:
            token = self._cancel_tokens.get(invocation_id)
        if token is not None:
            token.cancel(reason)

    def get_status(self, invocation_id: str) -> InvocationStatus | None:
        """Return status snapshot, or None if unknown."""
        with self._lock:
            s = self._invocations.get(invocation_id)
            if s is None:
                return None
            return InvocationStatus(
                invocation_id=s.invocation_id,
                agent_type=s.agent_type,
                state=s.state,
                started_at=s.started_at,
                finished_at=s.finished_at,
            )

    def list_active(self) -> list[InvocationStatus]:
        """Return status snapshots for all currently-running invocations."""
        with self._lock:
            return [
                InvocationStatus(
                    invocation_id=s.invocation_id,
                    agent_type=s.agent_type,
                    state=s.state,
                    started_at=s.started_at,
                    finished_at=s.finished_at,
                )
                for s in self._invocations.values()
                if s.state == "running"
            ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_api_model(self, model: str) -> bool:
        if self._model_manager is None:
            return False
        return self._model_manager.is_api_model(model)

    def _register(self, invocation_id: str, agent_type: str, cancel_token: CancelToken) -> None:
        status = InvocationStatus(
            invocation_id=invocation_id,
            agent_type=agent_type,
            state="running",
            started_at=time.time(),
        )
        with self._lock:
            self._invocations[invocation_id] = status
            self._cancel_tokens[invocation_id] = cancel_token

    def _set_state(self, invocation_id: str, state: str) -> None:
        with self._lock:
            s = self._invocations.get(invocation_id)
            if s is not None:
                s.state = state
                s.finished_at = time.time()

    def _cleanup(self, invocation_id: str) -> None:
        with self._lock:
            self._cancel_tokens.pop(invocation_id, None)

    # ------------------------------------------------------------------
    # LLM transport — Ollama
    # ------------------------------------------------------------------

    def _run_ollama(
        self,
        context: AgentContext,
        model: str,
        opts: InvokeOptions,
        cancel_token: CancelToken,
    ) -> Generator[AgentEvent, None, None]:
        if self._ollama is None:
            yield Error(
                code="runtime.config",
                message="Ollama client not configured",
                recoverable=False,
            )
            return

        conv = context.conversation
        ev_queue: queue.Queue[AgentEvent | object] = queue.Queue()
        collected: list[str] = []

        def on_chunk(text: str) -> None:
            collected.append(text)
            if opts.streaming:
                ev_queue.put(ThinkingUpdate(text=text))

        def on_done() -> None:
            full = "".join(collected)
            ev_queue.put(FinalAnswer(content=full))
            ev_queue.put(_SENTINEL)

        def on_error(msg: str) -> None:
            ev_queue.put(Error(code="llm.error", message=msg, recoverable=False))
            ev_queue.put(_SENTINEL)

        stop_event = cancel_token._event  # type: ignore[attr-defined]

        def _run() -> None:
            self._ollama.stream_chat(
                model=model,
                system_prompt=conv.system_prompt,
                history=conv.messages,
                user_message=conv.user_message or "",
                image_base64=conv.image_base64,
                on_chunk=on_chunk,
                on_done=on_done,
                on_error=on_error,
                stop_event=stop_event,
            )

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        yield from self._drain_queue(ev_queue, thread, cancel_token)

    # ------------------------------------------------------------------
    # LLM transport — API (OpenAI-compatible)
    # ------------------------------------------------------------------

    def _run_api(
        self,
        context: AgentContext,
        model: str,
        opts: InvokeOptions,
        cancel_token: CancelToken,
    ) -> Generator[AgentEvent, None, None]:
        if self._api_client_factory is None:
            yield Error(
                code="runtime.config",
                message="API client factory not configured",
                recoverable=False,
            )
            return

        conv = context.conversation
        ev_queue: queue.Queue[AgentEvent | object] = queue.Queue()
        collected: list[str] = []

        def on_chunk(text: str) -> None:
            collected.append(text)
            if opts.streaming:
                ev_queue.put(ThinkingUpdate(text=text))

        def on_done() -> None:
            full = "".join(collected)
            ev_queue.put(FinalAnswer(content=full))
            ev_queue.put(_SENTINEL)

        def on_error(msg: str) -> None:
            ev_queue.put(Error(code="llm.error", message=msg, recoverable=False))
            ev_queue.put(_SENTINEL)

        stop_event = cancel_token._event  # type: ignore[attr-defined]

        client = self._api_client_factory(model)

        def _run() -> None:
            client.stream_chat(
                system_prompt=conv.system_prompt,
                history=conv.messages,
                user_message=conv.user_message or "",
                image_base64=conv.image_base64,
                on_chunk=on_chunk,
                on_done=on_done,
                on_error=on_error,
                stop_event=stop_event,
            )

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        yield from self._drain_queue(ev_queue, thread, cancel_token)

    # ------------------------------------------------------------------
    # Queue drain (shared logic)
    # ------------------------------------------------------------------

    @staticmethod
    def _drain_queue(
        ev_queue: queue.Queue[AgentEvent | object],
        thread: threading.Thread,
        cancel_token: CancelToken,
    ) -> Generator[AgentEvent, None, None]:
        while True:
            try:
                event = ev_queue.get(timeout=0.1)
            except queue.Empty:
                if not thread.is_alive() and ev_queue.empty():
                    return
                if cancel_token.cancelled:
                    return
                continue

            if event is _SENTINEL:
                return
            if isinstance(event, Error):
                yield event
                return
            yield event


def _resolve_model(context: AgentContext, opts: InvokeOptions) -> str | None:
    """Return the effective model name for this invocation."""
    if opts.model:
        return opts.model
    if context.workspace.model:
        return context.workspace.model
    return None
