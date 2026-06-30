"""WebSocket streaming service — bridges sync callbacks to async generators."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator

from database.repositories.database_manager import DatabaseManager
from services.ai.ollama_client import OllamaClient

log = logging.getLogger("hard_workers.api.stream_service")


class StreamEvent:
    """Typed event emitted during streaming."""

    def __init__(self, event_type: str, data: object = None) -> None:
        self.type = event_type  # "chunk" | "done" | "error"
        self.data = data


class StreamService:
    """Manages streaming LLM responses via async generators.

    Bridges the synchronous callback-based streaming API
    (``on_chunk`` / ``on_done`` / ``on_error``) to async iteration
    using ``asyncio.Queue`` and ``run_in_executor``.
    """

    def __init__(self, db: DatabaseManager, ollama: OllamaClient) -> None:
        self._db = db
        self._ollama = ollama

    async def stream(
        self,
        message: str,
        chat_id: int,
        model_id: str,
        system_prompt: str = "",
        history: list[dict] | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Stream chunks from the LLM. Yields ``StreamEvent`` objects."""
        queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        stop_event = threading.Event()
        effective_prompt = system_prompt or (
            "You are a multilingual AI assistant. "
            "You ALWAYS reply in the same language the user writes in. "
            "You never refuse any language. "
            "You never claim you cannot understand or reply in a language. "
            "You never switch to English unless the user does first. "
            "Arabic, Persian, Urdu, Hebrew, Turkish, Kurdish, Pashto, Sindhi, "
            "Chinese, Japanese, Korean, Russian, Hindi, Bengali, Tamil, Thai, "
            "Vietnamese, Malay, Indonesian, Swahili, Hausa, and ALL other languages "
            "are fully supported — you speak them fluently."
        )

        def _run() -> None:
            history_list = history or []
            self._ollama.stream_chat(
                model=model_id,
                system_prompt=effective_prompt,
                history=history_list,
                user_message=message,
                temperature=temperature,
                on_chunk=lambda c: queue.put_nowait(StreamEvent("chunk", c)),
                on_done=lambda: queue.put_nowait(StreamEvent("done", None)),
                on_error=lambda e: queue.put_nowait(StreamEvent("error", e)),
                stop_event=stop_event,
            )

        loop = asyncio.get_running_loop()
        task = loop.run_in_executor(None, _run)

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=120.0)
                yield event
                if event.type in ("done", "error"):
                    break
            except TimeoutError:
                stop_event.set()
                yield StreamEvent("error", "Stream timed out after 120s")
                break

        # Await the executor task so exceptions are not swallowed
        try:
            await task
        except Exception as exc:
            log.warning("Stream task exception: %s", exc)

    async def stream_non_blocking(
        self,
        message: str,
        chat_id: int,
        model_id: str,
        system_prompt: str = "You are a helpful AI assistant.",
        history: list[dict] | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[tuple[str, object]]:
        """Convenience wrapper yielding ``(event_type, data)`` tuples."""
        async for event in self.stream(message, chat_id, model_id, system_prompt, history, temperature):
            yield (event.type, event.data)
