"""Data models for validation results and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class ValidationResult:
    name: str
    success: bool
    severity: Severity = Severity.INFO
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "success": self.success,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "recommendation": self.recommendation,
        }


@dataclass
class ValidationReport:
    results: list[ValidationResult] = field(default_factory=list)
    execution_time: float = 0.0

    @property
    def passed(self) -> list[ValidationResult]:
        return [r for r in self.results if r.success]

    @property
    def warnings(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.success and r.severity == Severity.WARNING]

    @property
    def errors(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.success and r.severity == Severity.ERROR]

    @property
    def critical(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.success and r.severity == Severity.CRITICAL]

    @property
    def is_healthy(self) -> bool:
        return all(r.success for r in self.results if r.severity in (Severity.ERROR, Severity.CRITICAL))

    @property
    def is_warning(self) -> bool:
        return bool(self.warnings) and not self.errors and not self.critical

    def has_failures(self) -> bool:
        return bool(self.errors) or bool(self.critical)
