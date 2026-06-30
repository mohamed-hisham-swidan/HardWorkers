"""Technical Architect expert — reviews architecture and design decisions."""

from __future__ import annotations

from typing import Any

from experts.base import ExpertBase


class TechnicalArchitect(ExpertBase):
    """Reviews architecture, refactoring plans, and design decisions."""

    def __init__(self) -> None:
        super().__init__(
            name="Technical Architect",
            role="Architecture & Design",
            description="Reviews system architecture, refactoring plans, component design, "
            "and ensures adherence to clean architecture principles.",
        )

    def _analyze(self, plan: dict[str, Any], context: dict[str, Any]) -> list[str]:
        findings: list[str] = []
        task = plan.get("task", "")
        steps = plan.get("steps", [])

        if not steps:
            findings.append("Plan has no defined steps")
        if len(steps) > 15:
            findings.append(f"Plan has {len(steps)} steps — consider splitting into sub-tasks")

        task_lower = task.lower()
        if "refactor" in task_lower:
            findings.append("Refactoring plan detected — verify backward compatibility")
        if "migrate" in task_lower:
            findings.append("Migration plan detected — ensure rollback strategy")
        if "database" in task_lower or "schema" in task_lower:
            findings.append("Database changes detected — verify migration path")
        if "api" in task_lower:
            findings.append("API changes detected — verify versioning strategy")

        return findings

    def _assess_risks(self, plan: dict[str, Any], context: dict[str, Any]) -> list[str]:
        risks: list[str] = []
        steps = plan.get("steps", [])

        if len(steps) > 10:
            risks.append("High step count increases risk of cascading failures")

        tools_used = {s.get("tool") for s in steps}
        if "delete" in tools_used:
            risks.append("File deletion risks breaking references")
        if "rename" in tools_used:
            risks.append("Renaming requires updating all imports and references")
        if "edit" in tools_used and len(tools_used) > 3:
            risks.append("Multiple simultaneous edits risk inconsistency")

        return risks

    def _recommend(
        self,
        plan: dict[str, Any],
        findings: list[str],
        risks: list[str],
    ) -> list[str]:
        recs = [
            "Maintain single responsibility per module",
            "Ensure backward compatibility for public APIs",
            "Add or update type hints for all modified functions",
        ]
        if risks:
            recs.append("Add rollback steps to the plan")
        if len(plan.get("steps", [])) > 8:
            recs.append("Consider splitting into smaller incremental changes")
        return recs
