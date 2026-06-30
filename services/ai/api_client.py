"""Generic API client for OpenAI-compatible external model providers.

Supports: OpenAI, Anthropic, OpenRouter, LM Studio, vLLM, and any
provider offering an OpenAI-compatible /chat/completions endpoint.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from typing import Any

import requests

from config.constants import API_CONNECT_TIMEOUT_S, API_READ_TIMEOUT_S, STREAM_ACTIVITY_TIMEOUT_S
from utils.http_session import build_session
from utils.language import wrap_for_multilingual
from utils.logging_setup import get_logger

log = get_logger("services.api_client")


class ApiModelClient:
    """Thin HTTP wrapper around any OpenAI-compatible API endpoint.

    Features
    --------
    * URL normalisation (protocol, slashes, trailing slash)
    * Smart /chat/completions endpoint resolution (never double-appends)
    * Multi-path health probing  (GET /models → /v1/models → /)
    * Model discovery (list_models)
    * Retry with exponential backoff for transient failures
    * Specific error diagnostics (SSL, DNS, timeout, HTTP codes)
    * Thread-safe session reuse
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        model_name: str,
        api_password: str = "",
        connect_timeout: float = API_CONNECT_TIMEOUT_S,
        read_timeout: float = API_READ_TIMEOUT_S,
        temperature: float = 0.7,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self._url = self._normalize_url(api_url)
        self._api_key = api_key
        self._password = api_password
        self._model = model_name
        self._conn_t = connect_timeout
        self._read_t = read_timeout
        self._temperature = temperature
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._session = self._build_session()
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def health_check(self) -> tuple[bool, str]:
        """Probe the server with multiple endpoints to verify connectivity.

        Tries GET /models, /v1/models, then / (root).
        Returns (ok, message) where *message* contains a specific diagnostic.
        """
        with self._lock:
            candidates = self._health_check_endpoints()
            errors: list[str] = []
            for endpoint in candidates:
                try:
                    r = self._session.get(
                        endpoint,
                        headers=self._headers(),
                        timeout=self._conn_t,
                    )
                    return True, f"Connection OK (HTTP {r.status_code})"
                except requests.exceptions.ConnectionError:
                    errors.append(f"Cannot reach {endpoint}")
                    continue
                except requests.exceptions.Timeout:
                    errors.append(f"Timed out: {endpoint}")
                    continue
                except Exception as exc:
                    errors.append(self._classify_error(exc))
                    continue

            detail = "; ".join(errors) if errors else "No Connection"
            return False, detail

    def list_models(self) -> list[str]:
        """Fetch available model IDs via the provider's /models endpoint."""
        with self._lock:
            base = self._strip_chat_suffix()
            candidates = [f"{base}/models", f"{base}/v1/models"]
            for endpoint in candidates:
                try:
                    r = self._session.get(
                        endpoint,
                        headers=self._headers(),
                        timeout=self._conn_t,
                    )
                    r.raise_for_status()
                    data = r.json()
                    raw = data.get("data", [])
                    if isinstance(raw, list):
                        models: list[str] = []
                        for m in raw:
                            if isinstance(m, dict):
                                mid = m.get("id")
                                if mid:
                                    models.append(str(mid))
                            elif isinstance(m, str):
                                models.append(m)
                        if models:
                            return models
                except Exception:
                    continue
            return []

    def stream_chat(
        self,
        *,
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
        """Stream a chat completion.  Callbacks mirror OllamaClient."""
        log.info(
            "API stream start model=%s image=%s",
            self._model,
            image_base64 is not None,
        )

        with self._lock:
            validation = self._validate_model_name()
            if validation:
                on_error(validation)
                return

            messages = self._build_messages(system_prompt, history, user_message, image_base64)
            payload = {
                "model": self._model,
                "messages": messages,
                "stream": True,
                "temperature": temperature if temperature is not None else self._temperature,
            }

            for attempt in range(self._max_retries):
                if stop_event.is_set():
                    return

                if attempt > 0:
                    delay = self._retry_delay * (2 ** (attempt - 1))
                    log.info("API stream retry %d/%d after %.1fs", attempt + 1, self._max_retries, delay)
                    if stop_event.wait(delay):
                        return

                try:
                    self._do_stream_request(payload, on_chunk, on_done, on_error, stop_event)
                    return
                except requests.exceptions.Timeout:
                    log.warning(
                        "API stream timeout attempt %d/%d model=%s", attempt + 1, self._max_retries, self._model
                    )
                    if attempt == self._max_retries - 1:
                        on_error("Connection timed out — server unreachable")
                        return
                except requests.exceptions.ConnectionError:
                    if attempt == self._max_retries - 1:
                        on_error(f"Cannot reach API endpoint: {self._url}")
                        return
                except requests.exceptions.HTTPError as exc:
                    status = exc.response.status_code if exc.response else "?"
                    body = exc.response.text[:300] if exc.response else str(exc)
                    if status == 429:
                        log.warning("Rate-limited (429) on %s — model: %s", self._url, self._model)
                        on_error("Rate-limited (HTTP 429). Wait a moment before trying again.")
                        return
                    if attempt == self._max_retries - 1:
                        on_error(f"API HTTP {status}: {body}")
                        return
                except Exception as exc:
                    log.error("API stream error attempt %d/%d: %s", attempt + 1, self._max_retries, exc, exc_info=True)
                    if attempt == self._max_retries - 1:
                        on_error(str(exc))
                        return

    def _build_messages(
        self,
        system_prompt: str,
        history: list[dict],
        user_message: str,
        image_base64: str | None,
    ) -> list[dict]:
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.extend(history)
        # Wrap non-English user messages with language instructions so
        # models fine-tuned to refuse non-English scripts (e.g. Nemotron)
        # see the directive right before the user's text at decode time.
        wrapped = wrap_for_multilingual(user_message)
        if image_base64:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": wrapped},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                ],
            })
        else:
            messages.append({"role": "user", "content": wrapped})
        return messages

    def _do_stream_request(
        self,
        payload: dict[str, Any],
        on_chunk: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None],
        stop_event: threading.Event,
    ) -> None:
        """Execute one streaming POST and process the SSE response."""
        last_activity = time.monotonic()

        with self._session.post(
            self._chat_endpoint,
            headers=self._headers(),
            json=payload,
            stream=True,
            timeout=(self._conn_t, self._read_t),
        ) as resp:
            resp.raise_for_status()

            for line in resp.iter_lines():
                if stop_event.is_set():
                    return

                if not line:
                    continue

                # ── activity heartbeat ──
                now = time.monotonic()
                if now - last_activity > STREAM_ACTIVITY_TIMEOUT_S:
                    log.warning(
                        "Stream inactive for %.1fs model=%s — aborting",
                        now - last_activity,
                        self._model,
                    )
                    on_error(
                        f"No data received for {STREAM_ACTIVITY_TIMEOUT_S:.0f}s — "
                        "the provider may be queued or overloaded."
                    )
                    return
                last_activity = now

                # ── decode & strip SSE framing ──
                raw = line.decode("utf-8", errors="replace").strip()
                if raw.startswith("data:"):
                    raw = raw[5:].strip()
                if not raw:
                    continue

                # ── [DONE] sentinel ──
                if raw == "[DONE]":
                    on_done()
                    return

                # ── parse JSON ──
                try:
                    chunk = json.loads(raw)
                except json.JSONDecodeError:
                    log.debug("API stream non-JSON line: %s", raw[:120])
                    continue

                # ── route by shape ──
                if self._handle_stream_chunk(chunk, on_chunk):
                    continue

                # ── unexpected — log for debugging ──
                log.debug(
                    "API stream unexpected chunk shape model=%s keys=%s snippet=%s",
                    self._model,
                    list(chunk.keys()),
                    json.dumps(chunk)[:200],
                )

            on_done()

    def _handle_stream_chunk(
        self,
        chunk: dict[str, Any],
        on_chunk: Callable[[str], None],
    ) -> bool:
        """Process one decoded SSE chunk.  Return True if it was handled."""
        # ── error payload (OpenRouter sends these mid-stream) ──
        error = chunk.get("error")
        if error is not None:
            code = error.get("code", "?")
            msg = error.get("message", str(error))
            log.warning("API stream error chunk code=%s message=%s", code, msg)
            return True

        # ── empty choices (usage-only, finish, or no-op delta) ──
        choices = chunk.get("choices")
        if not choices or not isinstance(choices, list):
            log.debug("API stream no choices — keys=%s", list(chunk.keys()))
            return True

        if len(choices) == 0:
            log.debug("API stream empty choices array — keys=%s", list(chunk.keys()))
            return True

        # ── safe access to first choice ──
        first = choices[0]
        if not isinstance(first, dict):
            log.debug("API stream non-dict choice — type=%s", type(first).__name__)
            return True

        finish_reason = first.get("finish_reason")
        if finish_reason is not None:
            log.debug("API stream finish_reason=%s", finish_reason)

        delta = first.get("delta")
        if not isinstance(delta, dict):
            return True

        text = delta.get("content", "")
        if not isinstance(text, str) or not text:
            return True

        on_chunk(text)
        return True

    def generate(self, prompt: str) -> str | None:
        """Non-streaming generation (for summarisation)."""
        with self._lock:
            validation = self._validate_model_name()
            if validation:
                log.warning("API generate skipped — %s", validation)
                return None

            try:
                payload = {
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "temperature": self._temperature,
                }
                r = self._session.post(
                    self._chat_endpoint,
                    headers=self._headers(),
                    json=payload,
                    timeout=(self._conn_t, self._read_t),
                )
                r.raise_for_status()
                data = r.json()
                choices = data.get("choices", [])
                if not choices:
                    return None
                return choices[0].get("message", {}).get("content", "").strip() or None
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response else "?"
                log.warning("API generate HTTP %s: %s", status, exc)
                return None
            except Exception as exc:
                log.warning("API generate failed: %s", exc)
                return None

    def _validate_model_name(self) -> str | None:
        """Return an error string if ``self._model`` is unusable, else ``None``."""
        if not self._model or not self._model.strip():
            return "Model name is empty — check the model field in the registry."
        return None

    def close(self) -> None:
        self._session.close()
        log.info("API client session closed (%s)", self._url)

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> ApiModelClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        if self._password:
            h["OpenAI-Organization"] = self._password
        return h

    def _build_session(self) -> requests.Session:
        return build_session(
            max_retries=self._max_retries,
            backoff_factor=self._retry_delay,
        )

    # ── URL resolution helpers ─────────────────────────────────────────────────

    @property
    def _chat_endpoint(self) -> str:
        """Full chat-completions URL — never double-appends the path."""
        url = self._url
        if url.endswith("/chat/completions"):
            return url
        return f"{url}/chat/completions"

    def _strip_chat_suffix(self) -> str:
        """Return the base URL without a trailing /chat/completions segment."""
        url = self._url
        if url.endswith("/chat/completions"):
            return url[: -len("/chat/completions")]
        return url

    def _health_check_endpoints(self) -> list[str]:
        """Return candidate endpoints for connectivity probing.

        Tries, in order:
          1. Base stripped of trailing version segment + /models  (e.g. /v1 → /models)
          2. Base + /models
          3. Base stripped of trailing version segment + /
          4. Base + /
        """
        from urllib.parse import urlparse

        base = self._strip_chat_suffix().rstrip("/")
        parsed = urlparse(base)
        path = parsed.path.rstrip("/")

        # Build a parent base by removing the last path segment
        parent_base = base
        if path:
            parent_path = path.rsplit("/", 1)[0] if "/" in path else ""
            if parent_path:
                parent_base = parsed._replace(path=parent_path).geturl()

        seen: set[str] = set()
        candidates: list[str] = []

        for suffix in ["/models", "/"]:
            for b in (base, parent_base):
                ep = f"{b}{suffix}"
                if ep not in seen:
                    seen.add(ep)
                    candidates.append(ep)

        return candidates

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Sanitise a user-provided URL.

        * Strips whitespace
        * Prepends ``https://`` if no protocol is present
        * Deduplicates internal slashes (leaves protocol ``//`` intact)
        * Removes trailing slash
        """
        url = url.strip()
        if not url:
            return ""
        if not re.match(r"^https?://", url, re.IGNORECASE):
            url = "https://" + url
        # Collapse multiple consecutive slashes while preserving protocol
        url = re.sub(r"(?<!:)//+", "/", url)
        url = url.rstrip("/")
        return url

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        """Return a human-readable error description."""
        if isinstance(exc, requests.exceptions.SSLError):
            return "SSL error — verify certificate or use http://"
        if isinstance(exc, requests.exceptions.ConnectionError):
            return "Cannot reach server — check URL or network"
        if isinstance(exc, requests.exceptions.Timeout):
            return "Connection timed out — server unreachable"
        if isinstance(exc, requests.exceptions.HTTPError):
            status = exc.response.status_code if exc.response else "?"
            body = exc.response.text[:200] if exc.response else str(exc)
            if status == 429:
                return "Rate-limited (HTTP 429) — wait before retrying"
            return f"HTTP {status}: {body}"
        if isinstance(exc, requests.exceptions.TooManyRedirects):
            return "Too many redirects — check URL"
        if isinstance(exc, requests.exceptions.InvalidURL):
            return f"Invalid URL: {exc}"
        if isinstance(exc, requests.exceptions.InvalidHeader):
            return f"Invalid header: {exc}"
        return str(exc)
