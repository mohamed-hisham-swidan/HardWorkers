"""Base classes for the multi-expert system."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger("hard_workers.experts.base")


class ReviewVerdict(Enum):
    APPROVED = "approved"
    APPROVED_WITH_CHANGES = "approved_with_changes"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


@dataclass
class ExpertOpinion:
    """Opinion from a single expert."""

    expert_name: str
    expert_role: str
    verdict: ReviewVerdict
    summary: str
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "expert_name": self.expert_name,
            "expert_role": self.expert_role,
            "verdict": self.verdict.value,
            "summary": self.summary,
            "findings": self.findings,
            "recommendations": self.recommendations,
            "risks": self.risks,
            "confidence": self.confidence,
        }


class ExpertBase:
    """Base class for all expert personas."""

    def __init__(self, name: str, role: str, description: str) -> None:
        self.name = name
        self.role = role
        self.description = description

    def review(
        self,
        plan: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ExpertOpinion:
        """Review a plan and return an expert opinion."""
        findings = self._analyze(plan, context or {})
        risks = self._assess_risks(plan, context or {})
        recommendations = self._recommend(plan, findings, risks)
        verdict = self._determine_verdict(risks, findings)
        summary = self._summarize(verdict, findings, recommendations)

        return ExpertOpinion(
            expert_name=self.name,
            expert_role=self.role,
            verdict=verdict,
            summary=summary,
            findings=findings,
            recommendations=recommendations,
            risks=risks,
            confidence=self._calculate_confidence(risks),
        )

    def _analyze(self, plan: dict[str, Any], context: dict[str, Any]) -> list[str]:
        """Analyze the plan and return findings."""
        raise NotImplementedError

    def _assess_risks(self, plan: dict[str, Any], context: dict[str, Any]) -> list[str]:
        """Assess risks in the plan."""
        raise NotImplementedError

    def _recommend(
        self,
        plan: dict[str, Any],
        findings: list[str],
        risks: list[str],
    ) -> list[str]:
        """Generate recommendations based on findings and risks."""
        raise NotImplementedError

    def _determine_verdict(
        self,
        risks: list[str],
        findings: list[str],
    ) -> ReviewVerdict:
        if len(risks) > 3:
            return ReviewVerdict.REJECTED
        if len(risks) > 1:
            return ReviewVerdict.NEEDS_REVIEW
        if len(findings) > 5:
            return ReviewVerdict.APPROVED_WITH_CHANGES
        return ReviewVerdict.APPROVED

    def _summarize(
        self,
        verdict: ReviewVerdict,
        findings: list[str],
        recommendations: list[str],
    ) -> str:
        lines = [f"Review by {self.name} ({self.role}): Verdict: {verdict.value}"]
        if findings:
            lines.append(f"Findings ({len(findings)}): " + "; ".join(findings[:3]))
        if recommendations:
            lines.append("Recommendations: " + "; ".join(recommendations[:3]))
        return "\n".join(lines)

    def _calculate_confidence(self, risks: list[str]) -> float:
        return max(0.3, 1.0 - (len(risks) * 0.2))
