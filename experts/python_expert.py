"""Python Expert — reviews code quality, performance, and Python best practices."""

from __future__ import annotations

from typing import Any

from experts.base import ExpertBase


class PythonExpert(ExpertBase):
    """Reviews Python code quality, performance optimization, and best practices."""

    def __init__(self) -> None:
        super().__init__(
            name="Python Expert",
            role="Python Code Quality & Performance",
            description="Ensures Python code follows PEP 8, uses type hints, avoids anti-patterns, "
            "and is optimized for performance.",
        )

    def _analyze(self, plan: dict[str, Any], context: dict[str, Any]) -> list[str]:
        findings: list[str] = []
        task = plan.get("task", "")

        py_issues = [
            ("from __future__ import annotations", "Missing future annotations import"),
            ("type hint", "Verify type hints are present"),
            ("Any", "Check for proper type annotations vs Any"),
        ]
        for pattern, issue in py_issues:
            if pattern not in task:
                findings.append(f"Check: {issue}")

        steps = plan.get("steps", [])
        py_files = [s for s in steps if s.get("params", {}).get("path", "").endswith(".py")]
        if py_files:
            findings.append(f"Python files to modify: {len(py_files)}")

        return findings

    def _assess_risks(self, plan: dict[str, Any], context: dict[str, Any]) -> list[str]:
        risks: list[str] = []
        task = plan.get("task", "").lower()

        if "import" in task or "dependency" in task:
            risks.append("New dependencies must be added to requirements.txt")
        if "class" in task:
            risks.append("Class modifications may affect inheritance hierarchies")
        if "async" in task or "await" in task:
            risks.append("Async code requires proper event loop management")
        if "thread" in task:
            risks.append("Threading code requires proper lock management")

        return risks

    def _recommend(
        self,
        plan: dict[str, Any],
        findings: list[str],
        risks: list[str],
    ) -> list[str]:
        return [
            "Add type hints to all function signatures and class attributes",
            "Use dataclasses for data containers instead of dicts",
            "Prefer pathlib over os.path for path operations",
            "Use f-strings over .format() or % formatting",
            "Add or update unit tests for modified code paths",
            "Use context managers (with statements) for resource management",
        ]
