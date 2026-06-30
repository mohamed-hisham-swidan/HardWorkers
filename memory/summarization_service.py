"""Conversation summarisation pipeline.

Triggered when the active-token budget is exhausted:
1. Summarise recent history via Ollama (always uses the default Ollama model,
   never an API model, to avoid dependency on external API availability).
2. Persist the summary.
3. Archive old messages, keeping only the tail.
4. Rebuild the vector index so new facts stay searchable.
"""

from __future__ import annotations

from database.repositories import DatabaseManager
from memory.memory_service import MemoryService
from models.domain import Message
from services.ai.ollama_client import OllamaClient
from utils.logging_setup import get_logger

log = get_logger("memory.summarization_service")

_SUMMARY_PROMPT = (
    "Summarise the following conversation in three sentences or fewer, "
    "preserving the most important facts and decisions:\n\n{text}"
)

_FALLBACK_MODELS = ["llama3", "llama3.1", "mistral", "qwen2.5", "gemma2"]


class SummarizationService:
    def __init__(
        self,
        ollama: OllamaClient,
        default_summary_model: str,
        db: DatabaseManager,
        memory: MemoryService,
    ) -> None:
        self._ollama = ollama
        self._summary_model = default_summary_model
        self._db = db
        self._memory = memory

    def run_pipeline(self, messages: list[Message], keep_last_n: int = 6, chat_id: int | None = None) -> bool:
        """Summarise *messages*, archive old rows, rebuild the index.

        Always uses the default Ollama model summarization to avoid
        depending on API model availability.

        If *chat_id* is provided, archiving and summary storage are scoped to
        that chat; otherwise they fall back to the global tables.
        Returns True if the pipeline completed successfully.
        """
        if not messages:
            return False

        conversation_text = "\n".join(f"{m.role.upper()}: {m.content}" for m in messages)
        log.info(
            "Running summarisation pipeline using model %r with %d messages (chat=%s)",
            self._summary_model,
            len(messages),
            chat_id,
        )

        summary = self._summarize(conversation_text)

        if summary:
            if chat_id is not None:
                self._db.chat_summaries.save(chat_id, summary)
            else:
                self._db.summaries.save(summary)
            log.info("Summary saved (%d chars)", len(summary))
        else:
            log.warning("Summarisation returned no text — skipping summary storage")

        if chat_id is not None:
            archived = self._db.chat.archive_old_for_chat(chat_id, keep_last_n)
        else:
            archived = self._db.chat.archive_old(keep_last_n)
        log.info("Archived %d messages", archived)

        self._memory.rebuild_index()
        return True

    def _summarize(self, text: str) -> str | None:
        """Attempt summarisation with the configured model, falling back
        through a list of common models if the primary one is unavailable."""
        models_to_try = [self._summary_model]
        if self._summary_model not in _FALLBACK_MODELS:
            models_to_try.extend(_FALLBACK_MODELS)

        for model in models_to_try:
            result = self._ollama.generate(model, _SUMMARY_PROMPT.format(text=text))
            if result:
                return result
            log.info("Summarisation with %r returned no result, trying next", model)

        log.error("All summarisation models failed")
        return None
