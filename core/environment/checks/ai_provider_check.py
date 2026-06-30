"""AI provider configuration validation."""

from __future__ import annotations

import os
from typing import Any

from core.environment.models import Severity, ValidationResult

KNOWN_PROVIDERS: list[dict[str, str]] = [
    {"name": "Ollama", "env_key": "OLLAMA_BASE_URL", "default_url": "http://localhost:11434", "needs_key": False},
    {"name": "OpenAI", "env_key": "OPENAI_API_KEY", "default_url": "", "needs_key": True},
    {"name": "Anthropic", "env_key": "ANTHROPIC_API_KEY", "default_url": "", "needs_key": True},
    {"name": "Google Gemini", "env_key": "GEMINI_API_KEY", "default_url": "", "needs_key": True},
    {"name": "Groq", "env_key": "GROQ_API_KEY", "default_url": "", "needs_key": True},
    {"name": "OpenRouter", "env_key": "OPENROUTER_API_KEY", "default_url": "", "needs_key": True},
    {"name": "Together AI", "env_key": "TOGETHER_API_KEY", "default_url": "", "needs_key": True},
    {"name": "DeepSeek", "env_key": "DEEPSEEK_API_KEY", "default_url": "", "needs_key": True},
]


class AIProviderCheck:
    def __init__(self, config: Any = None) -> None:
        self._config = config

    def run(self) -> ValidationResult:
        provider_statuses: list[dict[str, Any]] = []
        warnings: list[str] = []

        for provider in KNOWN_PROVIDERS:
            status = self._check_provider(provider)
            provider_statuses.append(status)
            if provider["name"] == "Ollama" and not status.get("reachable", True):
                warnings.append(f"Ollama is not reachable at {status.get('url')}")
            if not status.get("has_key") and provider.get("needs_key"):
                warnings.append(f"{provider['name']}: API key not found")

        configured_count = sum(1 for p in provider_statuses if p.get("has_key") or p.get("reachable"))

        return ValidationResult(
            name="AI Providers",
            success=True,
            severity=Severity.WARNING if warnings else Severity.INFO,
            message=f"AI provider check complete. {configured_count}/{len(KNOWN_PROVIDERS)} providers configured."
            if not warnings
            else f"Provider check: {len(warnings)} issues found.",
            details={
                "providers": provider_statuses,
                "total_providers": len(KNOWN_PROVIDERS),
                "configured": configured_count,
                "warnings": warnings,
            },
            recommendation="Configure AI providers via Settings dialog or .env file." if warnings else "",
        )

    @staticmethod
    def _check_provider(provider: dict[str, str]) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": provider["name"],
            "needs_api_key": provider["needs_key"],
            "has_key": False,
            "key_source": None,
            "url": provider["default_url"] if provider["default_url"] else None,
            "configured": False,
        }

        env_key = provider["env_key"]
        key_value = os.getenv(env_key, "")

        if key_value and key_value.strip():
            result["has_key"] = True
            result["key_source"] = "environment"
            result["configured"] = True

        if provider["name"] == "Ollama":
            result["url"] = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            result["configured"] = True

        return result
