"""Vision model integration for image understanding.

Supports both local (Ollama with LLaVA/vision models) and API-based
vision models (OpenAI GPT-4V, Anthropic Claude 3 Vision).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import requests

log = logging.getLogger("hard_workers.vision.vision_model")


class VisionModel:
    """Vision model client for image understanding."""

    def __init__(
        self,
        provider: str = "ollama",
        model_name: str = "llava",
        api_url: str = "http://localhost:11434",
        api_key: str = "",
    ) -> None:
        self._provider = provider
        self._model = model_name
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._session = requests.Session()

    # ── Public API ──────────────────────────────────────────────────────────────

    def describe(
        self,
        base64_image: str,
        prompt: str = "Describe this image in detail.",
        max_tokens: int = 512,
        on_chunk: Callable[[str], None] | None = None,
    ) -> str:
        """Generate a description of an image using the vision model."""
        if self._provider == "ollama":
            return self._describe_ollama(base64_image, prompt, on_chunk)
        elif self._provider in ("openai", "custom"):
            return self._describe_openai(base64_image, prompt, max_tokens, on_chunk)
        elif self._provider == "anthropic":
            return self._describe_anthropic(base64_image, prompt, max_tokens)
        else:
            raise ValueError(f"Unsupported vision provider: {self._provider}")

    def describe_detailed(
        self,
        base64_image: str,
    ) -> dict[str, Any]:
        """Generate a structured, detailed description of an image."""
        prompt = (
            "Analyze this image in detail. Provide a structured description including:\n"
            "1. Overall scene and content\n"
            "2. Key objects, people, or elements\n"
            "3. Text visible in the image\n"
            "4. Layout and composition\n"
            "5. Colors and visual style\n"
            "6. Any notable details or context\n"
        )
        description = self.describe(base64_image, prompt)
        return {
            "description": description,
            "type": self._classify_image(description),
            "has_text": self._detect_text_mention(description),
            "key_elements": self._extract_key_elements(description),
        }

    def health_check(self) -> bool:
        """Check if the vision model is available."""
        try:
            if self._provider == "ollama":
                r = self._session.get(f"{self._api_url}/api/tags", timeout=5)
                return r.status_code == 200
            else:
                r = self._session.get(
                    f"{self._api_url}/models",
                    headers=self._headers(),
                    timeout=5,
                )
                return r.status_code == 200
        except Exception:
            return False

    def close(self) -> None:
        self._session.close()

    # ── Provider implementations ────────────────────────────────────────────────

    def _describe_ollama(
        self,
        base64_image: str,
        prompt: str,
        on_chunk: Callable[[str], None] | None = None,
    ) -> str:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": on_chunk is not None,
            "images": [base64_image],
        }
        try:
            r = self._session.post(
                f"{self._api_url}/api/generate",
                json=payload,
                stream=on_chunk is not None,
                timeout=120,
            )
            r.raise_for_status()

            if on_chunk:
                full = ""
                for line in r.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line.decode("utf-8"))
                        text = data.get("response", "")
                        if text:
                            on_chunk(text)
                            full += text
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
                return full
            else:
                data = r.json()
                return data.get("response", "").strip()

        except Exception as exc:
            log.error("Ollama vision error: %s", exc)
            return f"[Vision model error: {exc}]"

    def _describe_openai(
        self,
        base64_image: str,
        prompt: str,
        max_tokens: int,
        on_chunk: Callable[[str], None] | None = None,
    ) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": max_tokens,
            "stream": on_chunk is not None,
        }
        try:
            r = self._session.post(
                f"{self._api_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                stream=on_chunk is not None,
                timeout=120,
            )
            r.raise_for_status()

            if on_chunk:
                full = ""
                for line in r.iter_lines():
                    if not line:
                        continue
                    raw = line.decode("utf-8").strip()
                    if raw.startswith("data:"):
                        raw = raw[5:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        chunk = json.loads(raw)
                        choices = chunk.get("choices")
                        if not choices or not isinstance(choices, list) or len(choices) == 0:
                            continue
                        delta = choices[0].get("delta")
                        if not isinstance(delta, dict):
                            continue
                        text = delta.get("content", "")
                        if text:
                            on_chunk(text)
                            full += text
                    except json.JSONDecodeError:
                        continue
                return full
            else:
                data = r.json()
                choices = data.get("choices")
                if choices and isinstance(choices, list) and len(choices) > 0:
                    msg = choices[0].get("message")
                    if isinstance(msg, dict):
                        content = msg.get("content", "")
                        if content:
                            return content.strip()
                return ""

        except Exception as exc:
            log.error("OpenAI vision error: %s", exc)
            return f"[Vision API error: {exc}]"

    def _describe_anthropic(
        self,
        base64_image: str,
        prompt: str,
        max_tokens: int,
    ) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64_image,
                            },
                        },
                    ],
                }
            ],
            "max_tokens": max_tokens,
        }
        try:
            r = self._session.post(
                f"{self._api_url}/messages",
                headers=self._headers(),
                json=payload,
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            return data["content"][0]["text"].strip()
        except Exception as exc:
            log.error("Anthropic vision error: %s", exc)
            return f"[Anthropic vision error: {exc}]"

    # ── Analysis helpers ────────────────────────────────────────────────────────

    def _classify_image(self, description: str) -> str:
        desc_lower = description.lower()
        if any(kw in desc_lower for kw in ["screenshot", "interface", "ui", "window", "browser"]):
            return "screenshot"
        if any(kw in desc_lower for kw in ["diagram", "chart", "graph", "flowchart"]):
            return "diagram"
        if any(kw in desc_lower for kw in ["document", "page", "text", "letter"]):
            return "document"
        if any(kw in desc_lower for kw in ["person", "face", "people", "crowd"]):
            return "photograph"
        return "general"

    def _detect_text_mention(self, description: str) -> bool:
        text_indicators = ["text", "says", "written", "display", "shows", "label"]
        return any(kw in description.lower() for kw in text_indicators)

    def _extract_key_elements(self, description: str) -> list[str]:
        elements: list[str] = []
        lines = description.split("\n")
        for line in lines:
            if line.strip().startswith(("- ", "* ", "1. ", "2. ", "3.")):
                elements.append(line.strip().lstrip("-*0123456789. "))
        return elements[:10]

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h
