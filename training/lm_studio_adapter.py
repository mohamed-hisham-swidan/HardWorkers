"""LM Studio compatibility adapter.

Provides integration between the training pipeline and LM Studio
for loading, testing, and managing local models.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

log = logging.getLogger("hard_workers.training.lm_studio_adapter")

_DEFAULT_LM_STUDIO_URL = "http://localhost:1234"


class LMStudioAdapter:
    """Adapter for LM Studio API compatibility."""

    def __init__(self, base_url: str = _DEFAULT_LM_STUDIO_URL) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()

    # ── Public API ──────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        try:
            r = self._session.get(f"{self._base_url}/v1/models", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[dict[str, Any]]:
        try:
            r = self._session.get(f"{self._base_url}/v1/models", timeout=10)
            r.raise_for_status()
            return r.json().get("data", [])
        except Exception as exc:
            log.warning("Cannot list LM Studio models: %s", exc)
            return []

    def get_active_model(self) -> str | None:
        models = self.list_models()
        if models:
            return models[0].get("id") if isinstance(models[0], dict) else str(models[0])
        return None

    def load_model(self, model_path: str) -> tuple[bool, str]:
        """Ask LM Studio to load a specific model."""
        try:
            r = self._session.post(
                f"{self._base_url}/v1/models/load",
                json={"model": model_path},
                timeout=60,
            )
            if r.status_code == 200:
                return True, f"Model '{model_path}' loaded"
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as exc:
            return False, str(exc)

    def generate(
        self,
        prompt: str,
        model: str = "",
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> str | None:
        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if model:
            payload["model"] = model

        try:
            r = self._session.post(
                f"{self._base_url}/v1/chat/completions",
                json=payload,
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            log.error("LM Studio generation error: %s", exc)
            return None

    def close(self) -> None:
        self._session.close()
