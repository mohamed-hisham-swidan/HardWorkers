"""Manages which model is currently active — Ollama or API.

Extends the original ModelManager to support the hybrid model registry:
- Ollama models fetched from the live Ollama service
- API models loaded from the local database registry
"""

from __future__ import annotations

import threading

from database.repositories import DatabaseManager
from models.domain import ModelRegistryEntry
from services.ai.ollama_client import OllamaClient
from utils.logging_setup import get_logger

log = get_logger("services.model_manager")


class ModelManager:
    def __init__(
        self,
        client: OllamaClient,
        default_model: str,
        db: DatabaseManager,
    ) -> None:
        self._client = client
        self._model = default_model
        self._db = db
        self._lock = threading.Lock()

        # All available models (Ollama live + registered API)
        self._available: list[str] = []
        # Quick lookup: name → registry entry (for API models)
        self._registry_map: dict[str, ModelRegistryEntry] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh_available(self) -> list[str]:
        """Fetch live Ollama models AND registered API models, merge list."""
        ollama_models = self._client.list_models()

        api_models: list[str] = []
        registry_map: dict[str, ModelRegistryEntry] = {}

        try:
            for entry in self._db.models.get_all():
                if entry.is_api:
                    api_models.append(entry.name)
                    registry_map[entry.name] = entry
        except Exception as exc:
            log.warning("Could not load API models from registry: %s", exc)

        merged = list(ollama_models) + api_models

        with self._lock:
            self._available = merged
            self._registry_map = registry_map
            if self._model not in merged and merged:
                self._model = merged[0]
                log.info("Active model not available — switching to %s", self._model)

        log.info(
            "Model list refreshed — %d Ollama + %d API = %d total", len(ollama_models), len(api_models), len(merged)
        )

        return list(merged)

    def set_active(self, name: str) -> None:
        with self._lock:
            self._model = name
        log.info("Active model set to %r", name)

    def get_active(self) -> str:
        with self._lock:
            return self._model

    def get_available(self) -> list[str]:
        with self._lock:
            return list(self._available)

    def is_api_model(self, name: str) -> bool:
        """Return True if *name* is a registered API model (not Ollama)."""
        with self._lock:
            return name in self._registry_map

    def get_registry_entry(self, name: str) -> ModelRegistryEntry | None:
        """Return the registry entry for an API model, or None for Ollama models."""
        with self._lock:
            return self._registry_map.get(name)

    def get_ollama_models(self) -> list[str]:
        """Return only Ollama-native model names."""
        with self._lock:
            return [m for m in self._available if m not in self._registry_map]

    def get_api_models(self) -> list[str]:
        """Return only registered API model names."""
        with self._lock:
            return list(self._registry_map.keys())

    def is_vision_capable(self, name: str) -> bool:
        lower = name.lower()

        # Models with "-vl-" or "_vl_" in their name are inherently vision-capable
        if "-vl-" in lower or "_vl_" in lower:
            return True

        with self._lock:
            entry = self._registry_map.get(name)
            if entry is not None:
                return entry.supports_vision
        vision_kw = [
            "llava",
            "bakllava",
            "gemma3",
            "minicpm",
            "moondream",
            "deepseek-vl",
            "gpt-4o",
            "gpt-4-vision",
            "claude-3",
            "claude-3.5",
            "gemini-pro-vision",
            "gemini-2.0-flash",
            "qwen",
            "cogvlm",
            "internvl",
            "phi-3-vision",
        ]
        return any(kw in lower for kw in vision_kw)

    def get_vision_recommendations(self) -> list[str]:
        """Return recommended vision-capable model names when current model lacks vision."""
        return [
            "llava (Ollama)",
            "gemma3:vision (Ollama)",
            "gpt-4o (OpenAI)",
            "claude-3-haiku (Anthropic)",
            "gemini-2.0-flash (Gemini)",
        ]

    def invalidate_cache(self, name: str) -> None:
        """Remove a single entry from the in-memory cache without a full refresh.

        Call this after a model is deleted or updated so that stale credentials
        are not reused on the next API call.
        """
        with self._lock:
            self._registry_map.pop(name, None)
            try:
                self._available.remove(name)
            except ValueError:
                pass  # already gone
