"""Low-level HTTP client for the Ollama REST API.

Responsibilities:
- Connection pooling via requests.Session + urllib3 retry adapter.
- Streaming chat completions with per-chunk callback.
- Non-streaming text generation (for summarisation).
- Health probe.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable

import requests

from config.settings import OllamaConfig
from utils.http_session import build_session
from utils.language import wrap_for_multilingual
from utils.logging_setup import get_logger

log = get_logger("services.ollama_client")


class OllamaClient:
    def __init__(self, config: OllamaConfig) -> None:
        self._cfg = config
        self._session = self._build_session()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def health_check(self, quick: bool = False) -> bool:
        try:
            timeout = 2.0 if quick else self._cfg.connect_timeout
            session = requests.Session() if quick else self._session
            r = session.get(
                f"{self._cfg.base_url}/api/tags",
                timeout=timeout,
            )
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            session = requests.Session()
            r = session.get(
                f"{self._cfg.base_url}/api/tags",
                timeout=5.0,
            )
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])] or [self._cfg.default_model]
        except Exception as exc:
            log.warning("Cannot fetch model list: %s", exc)
            return [self._cfg.default_model]

    def probe(self) -> dict:
        """Return a diagnostics snapshot from the Ollama API."""
        try:
            t0 = time.monotonic()
            r = self._session.get(
                f"{self._cfg.base_url}/api/tags",
                timeout=self._cfg.connect_timeout,
            )
            latency_ms = (time.monotonic() - t0) * 1000
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            return {
                "status": "OK",
                "latency_ms": latency_ms,
                "available_models": models,
            }
        except requests.exceptions.Timeout:
            return {"status": "TIMEOUT", "latency_ms": None, "available_models": []}
        except requests.exceptions.ConnectionError:
            return {"status": "UNREACHABLE", "latency_ms": None, "available_models": []}
        except Exception as exc:
            return {"status": "ERROR", "error": str(exc), "latency_ms": None, "available_models": []}

    def stream_chat(
        self,
        *,
        model: str,
        system_prompt: str,
        history: list[dict],
        user_message: str,
        image_base64: str | None = None,
        temperature: float | None = None,
        on_chunk: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None],
        stop_event: threading.Event,
    ) -> None:
        log.info(
            "OLLAMA_STREAM model=%s image_present=%s image_len=%s",
            model,
            image_base64 is not None,
            len(image_base64) if image_base64 else 0,
        )
        log.info(
            "OLLAMA_STREAM_START model=%s image_present=%s image_len=%d",
            model,
            image_base64 is not None,
            len(image_base64) if image_base64 else 0,
        )
        validation = self._validate_model_name(model)
        if validation:
            on_error(validation)
            return

        if not self.health_check(quick=True):
            on_error("Ollama is not running — start it with 'ollama serve'")
            return

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        wrapped = wrap_for_multilingual(user_message)
        user_msg: dict = {"role": "user", "content": wrapped}
        if image_base64:
            user_msg["images"] = [image_base64]
        messages.append(user_msg)

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature if temperature is not None else self._cfg.temperature},
        }

        for attempt in range(self._cfg.max_retries):
            if stop_event.is_set():
                return
            if attempt > 0:
                delay = self._cfg.retry_delay * (2 ** (attempt - 1))
                log.info("Stream retry %d/%d after %.1fs", attempt + 1, self._cfg.max_retries, delay)
                if stop_event.wait(delay):  # interruptible sleep
                    return
            try:
                log.info(
                    "OLLAMA_PAYLOAD images_count=%d",
                    len(payload.get("messages", [{}])[-1].get("images", [])) if payload.get("messages") else 0,
                )
                with self._session.post(
                    f"{self._cfg.base_url}/api/chat",
                    json=payload,
                    stream=True,
                    timeout=(self._cfg.connect_timeout, self._cfg.read_timeout),
                ) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if stop_event.is_set():
                            return
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line.decode("utf-8"))
                        except json.JSONDecodeError:
                            continue
                        text = chunk.get("message", {}).get("content", "")
                        if text:
                            on_chunk(text)
                        if chunk.get("done"):
                            on_done()
                            return
                on_done()
                return
            except requests.exceptions.Timeout:
                if attempt == self._cfg.max_retries - 1:
                    on_error("Request timed out — is Ollama responsive?")
                    return
            except requests.exceptions.ConnectionError:
                if attempt == self._cfg.max_retries - 1:
                    on_error(f"Cannot reach Ollama at {self._cfg.base_url}")
                    return
            except Exception:
                if attempt == self._cfg.max_retries - 1:
                    log.exception("Streaming error")
                    on_error("Model generation failed — check Ollama logs")
                    return

    def generate(self, model: str, prompt: str) -> str | None:
        """Non-streaming generation (used for summarisation)."""
        validation = self._validate_model_name(model)
        if validation:
            log.warning("Generate blocked: %s", validation)
            return None
        if not self.health_check(quick=True):
            log.warning("Generate skipped — Ollama is not running")
            return None
        try:
            r = self._session.post(
                f"{self._cfg.base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=(self._cfg.connect_timeout, self._cfg.read_timeout),
            )
            r.raise_for_status()
            return r.json().get("response", "").strip() or None
        except Exception as exc:
            log.warning("Generate failed: %s", exc)
            return None

    def close(self) -> None:
        self._session.close()
        log.info("Ollama HTTP session closed")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_model_name(model: str) -> str | None:
        if not model or not model.strip():
            return "Model name is empty — cannot proceed"
        return None

    def _build_session(self) -> requests.Session:
        return build_session(
            max_retries=self._cfg.max_retries,
            backoff_factor=self._cfg.retry_delay,
        )
