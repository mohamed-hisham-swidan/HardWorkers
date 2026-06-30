"""AI Expert — reviews LLM systems, agents, RAG, and fine-tuning plans."""

from __future__ import annotations

from typing import Any

from experts.base import ExpertBase


class AIExpert(ExpertBase):
    """Reviews AI/LLM-related code: model integration, RAG pipelines, agent systems, fine-tuning."""

    def __init__(self) -> None:
        super().__init__(
            name="AI Expert",
            role="AI/LLM Systems",
            description="Reviews LLM integration, RAG pipelines, agent frameworks, "
            "fine-tuning configurations, and model management.",
        )

    def _analyze(self, plan: dict[str, Any], context: dict[str, Any]) -> list[str]:
        findings: list[str] = []
        task = plan.get("task", "").lower()

        if "model" in task:
            findings.append("Model changes detected — verify provider compatibility and fallback behavior")
        if "agent" in task:
            findings.append("Agent system changes — verify Observe→Analyze→Plan→Execute→Verify→Retry→Report cycle")
        if "rag" in task or "retrieval" in task or "vector" in task:
            findings.append("RAG pipeline changes — verify embedding model consistency")
        if "fine" in task and "tune" in task:
            findings.append("Fine-tuning configuration — verify dataset format and LoRA parameters")
        if "token" in task:
            findings.append("Token handling changes — verify tiktoken encoding consistency")
        if "memory" in task:
            findings.append("Memory system changes — verify profile isolation and search semantics")

        return findings

    def _assess_risks(self, plan: dict[str, Any], context: dict[str, Any]) -> list[str]:
        risks: list[str] = []

        task = plan.get("task", "").lower()
        if "model" in task and "fallback" not in task:
            risks.append("Model changes without fallback strategy could break chat")
        if "embedding" in task:
            risks.append("Embedding model changes invalidate existing vector index")
        if "prompt" in task:
            risks.append("Prompt changes affect all downstream model responses")
        if "context" in task or "history" in task:
            risks.append("Context window changes affect summarization pipeline thresholds")

        return risks

    def _recommend(
        self,
        plan: dict[str, Any],
        findings: list[str],
        risks: list[str],
    ) -> list[str]:
        return [
            "Always provide a fallback model in case the primary model is unavailable",
            "Maintain backward compatibility for all model provider interfaces",
            "Cache embedding results where possible to reduce latency",
            "Validate token counts before sending to API to prevent truncation",
            "Test with both Ollama and API model providers when changing chat flow",
            "Ensure memory profile isolation works correctly after changes",
        ]
