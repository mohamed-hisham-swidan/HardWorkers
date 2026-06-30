"""Ollama compatibility adapter.

Handles importing/exporting models between Ollama and the training pipeline.
Supports creating Modelfiles, importing GGUF models, and managing
Ollama model configurations.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("hard_workers.training.ollama_adapter")

_DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OllamaAdapter:
    """Adapter for managing training-related Ollama operations."""

    def __init__(self, base_url: str = _DEFAULT_OLLAMA_URL) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = self._build_session()
        self._lock = threading.Lock()

    # ── Public API ──────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        try:
            r = self._session.get(f"{self._base_url}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[dict[str, Any]]:
        try:
            r = self._session.get(f"{self._base_url}/api/tags", timeout=10)
            r.raise_for_status()
            return r.json().get("models", [])
        except Exception as exc:
            log.warning("Cannot list Ollama models: %s", exc)
            return []

    def import_gguf_model(
        self,
        gguf_path: Path | str,
        model_name: str,
        modelfile_overrides: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """Import a GGUF model into Ollama by creating a Modelfile that points to it."""
        gguf_path = Path(gguf_path)
        if not gguf_path.exists():
            return False, f"GGUF file not found: {gguf_path}"

        modelfile = self._build_modelfile_for_gguf(gguf_path, modelfile_overrides)
        return self._create_ollama_model(model_name, modelfile)

    def import_hf_model(
        self,
        hf_model_id: str,
        model_name: str,
        quantize: str | None = "q4_k_m",
    ) -> tuple[bool, str]:
        """Import a HuggingFace model into Ollama."""
        modelfile = self._build_modelfile_for_hf(hf_model_id)
        return self._create_ollama_model(model_name, modelfile)

    def delete_model(self, model_name: str) -> tuple[bool, str]:
        try:
            r = self._session.delete(
                f"{self._base_url}/api/delete",
                json={"name": model_name},
                timeout=30,
            )
            if r.status_code in (200, 404):
                return True, f"Model '{model_name}' deleted"
            return False, f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as exc:
            return False, str(exc)

    def pull_model(self, model_name: str) -> bool:
        """Pull a model from Ollama's registry."""
        try:
            r = self._session.post(
                f"{self._base_url}/api/pull",
                json={"name": model_name},
                stream=True,
                timeout=600,
            )
            r.raise_for_status()
            for line in r.iter_lines():
                if line:
                    try:
                        data = json.loads(line.decode("utf-8"))
                        if "error" in data:
                            log.error("Pull error: %s", data["error"])
                            return False
                    except json.JSONDecodeError:
                        continue
            return True
        except Exception as exc:
            log.error("Pull failed: %s", exc)
            return False

    def get_modelfile(self, model_name: str) -> str | None:
        try:
            r = self._session.post(
                f"{self._base_url}/api/show",
                json={"name": model_name},
                timeout=30,
            )
            r.raise_for_status()
            return r.json().get("modelfile")
        except Exception as exc:
            log.warning("Cannot get Modelfile: %s", exc)
            return None

    def close(self) -> None:
        self._session.close()

    # ── Internal ────────────────────────────────────────────────────────────────

    def _create_ollama_model(
        self,
        name: str,
        modelfile: str,
    ) -> tuple[bool, str]:
        safe = name.strip().lower().replace(" ", "-").replace("_", "-")
        if safe != name:
            log.warning("Sanitised model name %r → %r", name, safe)
            name = safe

        try:
            with self._session.post(
                f"{self._base_url}/api/create",
                json={"model": name, "modelfile": modelfile},
                stream=True,
                timeout=300,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        obj = json.loads(line.decode("utf-8"))
                        if "error" in obj:
                            return False, obj["error"]
                    except json.JSONDecodeError:
                        continue
            return True, f"Model '{name}' created in Ollama"
        except Exception as exc:
            return False, str(exc)

    def _build_modelfile_for_gguf(
        self,
        gguf_path: Path,
        overrides: dict[str, Any] | None = None,
    ) -> str:
        lines = [f"FROM {gguf_path.resolve()}"]
        if overrides:
            for key, val in overrides.items():
                lines.append(f"PARAMETER {key} {val}")
        return "\n".join(lines) + "\n"

    def _build_modelfile_for_hf(self, hf_model_id: str) -> str:
        return f"FROM {hf_model_id}\n"

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "DELETE"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=4)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
