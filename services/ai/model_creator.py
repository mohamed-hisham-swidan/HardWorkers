"""Model creator service — HardWorkres platform.

Handles:
- Generating Modelfiles for Ollama custom models
- Calling the Ollama /api/create endpoint
- Deleting and cloning Ollama models
- Registering and validating API models
"""

from __future__ import annotations

import json
import textwrap
from collections.abc import Callable

import requests

from config.settings import OllamaConfig
from database.repositories import DatabaseManager
from models.domain import ModelRegistryEntry
from services.ai.api_client import ApiModelClient
from utils.logging_setup import get_logger

log = get_logger("services.model_creator")


class ModelCreatorService:
    """Orchestrates creation, deletion, and registration of all model types."""

    def __init__(self, ollama_config: OllamaConfig, db: DatabaseManager) -> None:
        self._cfg = ollama_config
        self._db = db
        self._session = requests.Session()

    # ── Modelfile generation ──────────────────────────────────────────────────

    @staticmethod
    def build_modelfile(
        base_model: str,
        system_prompt: str = "",
        temperature: float = 0.7,
        extra_params: dict | None = None,
    ) -> str:
        """Produce a valid Ollama Modelfile string."""
        lines: list[str] = [f"FROM {base_model}"]

        if system_prompt.strip():
            escaped = system_prompt.replace('"""', '\\"\\"\\"')
            lines.append(f'\nSYSTEM """\n{textwrap.dedent(escaped).strip()}\n"""')

        lines.append(f"\nPARAMETER temperature {temperature:.2f}")

        if extra_params:
            for key, val in extra_params.items():
                lines.append(f"PARAMETER {key} {val}")

        return "\n".join(lines) + "\n"

    # ── Ollama model CRUD ─────────────────────────────────────────────────────

    def create_ollama_model(
        self,
        name: str,
        modelfile: str,
        on_progress: Callable[[str], None] | None = None,
    ) -> tuple[bool, str]:
        """Call POST /api/create to create an Ollama model.

        Returns (success, message).
        """
        url = f"{self._cfg.base_url}/api/create"

        # Validate model name (Ollama requires lowercase, no spaces)
        safe = name.strip().lower().replace(" ", "-").replace("_", "-")
        if safe != name:
            log.warning("Sanitised model name %r -> %r", name, safe)
            name = safe

        try:
            with self._session.post(
                url,
                json={"model": name, "modelfile": modelfile, "stream": True},
                stream=True,
                timeout=(self._cfg.connect_timeout, 300.0),
            ) as resp:
                if not resp.ok:
                    body = resp.text[:500]
                    log.error("Ollama create returned %d: %s", resp.status_code, body)
                resp.raise_for_status()

                last_status = ""
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        obj = json.loads(line.decode("utf-8"))
                        status = obj.get("status", "")
                        if status and status != last_status:
                            last_status = status
                            if on_progress:
                                on_progress(status)
                        if "error" in obj:
                            return False, obj["error"]
                    except json.JSONDecodeError:
                        continue

            log.info("Ollama model %r created", name)
            return True, "Model created successfully"

        except requests.exceptions.ConnectionError:
            return False, f"Cannot reach Ollama at {self._cfg.base_url}"
        except requests.exceptions.Timeout:
            return False, "Request timed out during model creation"
        except Exception as exc:
            log.error("Model creation error: %s", exc, exc_info=True)
            return False, str(exc)

    def delete_ollama_model(self, name: str) -> tuple[bool, str]:
        """Call DELETE /api/delete to remove an Ollama model."""
        url = f"{self._cfg.base_url}/api/delete"
        try:
            resp = self._session.delete(
                url,
                json={"name": name},
                timeout=self._cfg.connect_timeout,
            )
            if resp.status_code in (200, 404):
                log.info("Ollama model %r deleted", name)
                return True, f"Model '{name}' deleted"
            return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as exc:
            return False, str(exc)

    def clone_ollama_model(
        self,
        source_name: str,
        new_name: str,
    ) -> tuple[bool, str]:
        """Clone an Ollama model by copying its Modelfile."""
        # Fetch the existing model's Modelfile via /api/show
        url = f"{self._cfg.base_url}/api/show"
        try:
            resp = self._session.post(
                url,
                json={"name": source_name},
                timeout=self._cfg.connect_timeout,
            )
            resp.raise_for_status()
            modelfile = resp.json().get("modelfile", f"FROM {source_name}\n")
        except Exception as exc:
            modelfile = f"FROM {source_name}\n"
            log.warning("Could not fetch Modelfile for clone — using FROM only: %s", exc)

        return self.create_ollama_model(new_name, modelfile)

    def list_base_models(self) -> list[str]:
        """Return available Ollama models suitable for use as a base."""
        url = f"{self._cfg.base_url}/api/tags"
        try:
            resp = self._session.get(url, timeout=self._cfg.connect_timeout)
            resp.raise_for_status()
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception as exc:
            log.warning("Cannot list base models: %s", exc)
            return []

    # ── Registry operations ───────────────────────────────────────────────────

    def register_model(self, entry: ModelRegistryEntry) -> tuple[bool, str]:
        """Persist a model entry to the registry."""
        try:
            existing = self._db.models.get_by_name(entry.name)
            if existing:
                entry.id = existing.id
                self._db.models.update(entry)
                return True, f"Model '{entry.name}' updated in registry"
            self._db.models.save(entry)
            return True, f"Model '{entry.name}' registered"
        except Exception as exc:
            log.error("Registry save failed: %s", exc)
            return False, str(exc)

    def unregister_model(self, model_id: int) -> tuple[bool, str]:
        """Remove a model from the registry."""
        try:
            deleted = self._db.models.delete(model_id)
            return (True, "Model removed from registry") if deleted else (False, "Model not found")
        except Exception as exc:
            return False, str(exc)

    def get_registered_models(self) -> list[ModelRegistryEntry]:
        return self._db.models.get_all()

    def get_registered_model_by_id(self, model_id: int) -> ModelRegistryEntry | None:
        """Fetch a single registry entry by its primary key."""
        return self._db.models.get_by_id(model_id)

    def update_registered_model(self, entry: ModelRegistryEntry) -> tuple[bool, str]:
        """Persist changes to an existing registry entry using its *id*.

        Unlike *register_model*, this uses id-based lookup so the
        entry's name can change without creating a duplicate.
        """
        try:
            if entry.id is None:
                return False, "Cannot update model without an ID"
            self._db.models.update(entry)
            return True, f"Model '{entry.name}' updated in registry"
        except Exception as exc:
            log.error("Registry update failed: %s", exc)
            return False, str(exc)

    # ── API model validation ──────────────────────────────────────────────────

    @staticmethod
    def test_api_connection(
        api_url: str,
        api_key: str,
        model_name: str,
        api_password: str = "",
    ) -> tuple[bool, str, list[str]]:
        """Validate an API endpoint and discover available models.

        Returns (success, message, discovered_model_ids).
        """
        client = ApiModelClient(
            api_url=api_url,
            api_key=api_key,
            model_name=model_name,
            api_password=api_password,
        )
        try:
            ok, msg = client.health_check()
            models = client.list_models() if ok else []
            return ok, msg, models
        finally:
            client.close()

    def close(self) -> None:
        self._session.close()
