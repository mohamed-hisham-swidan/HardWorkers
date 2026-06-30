"""Review board — orchestrates multi-expert reviews of plans and implementations."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from experts.ai_expert import AIExpert
from experts.base import ExpertBase, ExpertOpinion, ReviewVerdict
from experts.cybersecurity_expert import CybersecurityExpert
from experts.obsidian_expert import ObsidianExpert
from experts.python_expert import PythonExpert
from experts.technical_architect import TechnicalArchitect

log = logging.getLogger("hard_workers.experts.review_board")


@dataclass
class ReviewResult:
    """Aggregated result from multiple expert reviews."""

    overall_verdict: ReviewVerdict
    opinions: list[ExpertOpinion] = field(default_factory=list)
    summary: str = ""
    blocking_issues: list[str] = field(default_factory=list)

    def is_approved(self) -> bool:
        return self.overall_verdict in (
            ReviewVerdict.APPROVED,
            ReviewVerdict.APPROVED_WITH_CHANGES,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_verdict": self.overall_verdict.value,
            "summary": self.summary,
            "blocking_issues": self.blocking_issues,
            "opinions": [o.to_dict() for o in self.opinions],
        }


class ReviewBoard:
    """Orchestrates review across all expert personas."""

    def __init__(self) -> None:
        self._experts: list[ExpertBase] = [
            TechnicalArchitect(),
            CybersecurityExpert(),
            PythonExpert(),
            AIExpert(),
            ObsidianExpert(),
        ]

    # ── Public API ──────────────────────────────────────────────────────────────

    def review_plan(
        self,
        plan: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ReviewResult:
        """Review a plan using all expert personas."""
        opinions: list[ExpertOpinion] = []
        ctx = context or {}

        for expert in self._experts:
            try:
                opinion = expert.review(plan, ctx)
                opinions.append(opinion)
                log.info(
                    "Expert '%s' verdict: %s (confidence: %.2f)",
                    expert.name,
                    opinion.verdict.value,
                    opinion.confidence,
                )
            except Exception as exc:
                log.error("Expert '%s' review failed: %s", expert.name, exc)
                opinions.append(
                    ExpertOpinion(
                        expert_name=expert.name,
                        expert_role=expert.role,
                        verdict=ReviewVerdict.NEEDS_REVIEW,
                        summary=f"Review failed: {exc}",
                        confidence=0.0,
                    )
                )

        return self._aggregate(opinions)

    def get_expert(self, name: str) -> ExpertBase | None:
        for expert in self._experts:
            if expert.name == name:
                return expert
        return None

    def get_all_experts(self) -> list[ExpertBase]:
        return list(self._experts)

    def add_expert(self, expert: ExpertBase) -> None:
        self._experts.append(expert)

    # ── Internal ────────────────────────────────────────────────────────────────

    def _aggregate(self, opinions: list[ExpertOpinion]) -> ReviewResult:
        rejected = [o for o in opinions if o.verdict == ReviewVerdict.REJECTED]
        needs_review = [o for o in opinions if o.verdict == ReviewVerdict.NEEDS_REVIEW]
        approved_changes = [o for o in opinions if o.verdict == ReviewVerdict.APPROVED_WITH_CHANGES]
        approved = [o for o in opinions if o.verdict == ReviewVerdict.APPROVED]

        blocking_issues: list[str] = []
        for o in rejected:
            blocking_issues.extend(o.risks or [])

        if rejected:
            overall = ReviewVerdict.REJECTED
            summary = f"Review rejected by {len(rejected)} expert(s): {', '.join(o.expert_name for o in rejected)}"
        elif needs_review:
            overall = ReviewVerdict.NEEDS_REVIEW
            summary = f"Review flagged by {len(needs_review)} expert(s) — issues must be addressed"
        elif approved_changes:
            overall = ReviewVerdict.APPROVED_WITH_CHANGES
            summary = f"Approved with {sum(len(o.recommendations) for o in approved_changes)} recommendations"
        else:
            overall = ReviewVerdict.APPROVED
            summary = f"Approved by all {len(approved)} expert(s)"

        return ReviewResult(
            overall_verdict=overall,
            opinions=opinions,
            summary=summary,
            blocking_issues=blocking_issues,
        )
