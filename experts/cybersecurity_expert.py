"""Cybersecurity Expert — reviews security, vulnerabilities, and safe coding practices."""

from __future__ import annotations

from typing import Any

from experts.base import ExpertBase


class CybersecurityExpert(ExpertBase):
    """Reviews code for security vulnerabilities, secret exposure, and safe practices."""

    def __init__(self) -> None:
        super().__init__(
            name="Cybersecurity Expert",
            role="Security & Vulnerability Analysis",
            description="Audits code for security issues: secret exposure, injection vulnerabilities, "
            "path traversal, unsafe deserialization, and authentication weaknesses.",
        )

    def _analyze(self, plan: dict[str, Any], context: dict[str, Any]) -> list[str]:
        findings: list[str] = []
        task = plan.get("task", "")
        task_lower = task.lower()

        security_keywords = ["api_key", "password", "secret", "token", "credential", "auth"]
        for kw in security_keywords:
            if kw in task_lower:
                findings.append(f"Sensitive data handling detected: '{kw}' — verify secure storage")
                break

        dangerous_patterns = ["eval(", "exec(", "pickle.loads", "subprocess.call", "os.system"]
        for pat in dangerous_patterns:
            if pat in task:
                findings.append(f"Dangerous function detected: {pat} — verify input sanitization")

        if "file" in task_lower or "path" in task_lower:
            findings.append("File/path operations detected — verify path traversal protections")

        return findings

    def _assess_risks(self, plan: dict[str, Any], context: dict[str, Any]) -> list[str]:
        risks: list[str] = [
            "Ensure API keys are never hardcoded — use env vars or encrypted storage",
            "Validate all file paths to prevent directory traversal",
            "Sanitize all user inputs to prevent injection attacks",
        ]

        # Check for specific risk indicators
        task = plan.get("task", "").lower()
        if "network" in task or "http" in task or "api" in task:
            risks.append("Network operations must use HTTPS with certificate validation")
        if "database" in task or "sql" in task:
            risks.append("SQL operations must use parameterized queries (not string formatting)")

        return risks

    def _recommend(
        self,
        plan: dict[str, Any],
        findings: list[str],
        risks: list[str],
    ) -> list[str]:
        return [
            "Use environment variables or .env files for secrets — never hardcode",
            "Implement input validation for all user-supplied data",
            "Use safe APIs for serialization (JSON over pickle)",
            "Add rate limiting for any network-exposed endpoints",
            "Enable WAL mode and timeout for SQLite to prevent corruption",
        ]
