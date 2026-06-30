"""Main environment validator orchestrator."""

from __future__ import annotations

import logging
import time
from typing import Any

from core.environment.checks import ALL_CHECKS
from core.environment.models import Severity, ValidationReport, ValidationResult
from core.environment.report import generate_report_markdown

log = logging.getLogger("hard_workers.environment.validator")


class EnvironmentValidator:
    """Orchestrates all environment checks before application startup."""

    def __init__(self, config: Any | None = None) -> None:
        self._config = config
        self._report: ValidationReport | None = None

    @property
    def report(self) -> ValidationReport | None:
        return self._report

    def validate(self) -> ValidationReport:
        """Run all registered checks and generate a report."""
        t0 = time.monotonic()
        results: list[ValidationResult] = []

        for check_cls in ALL_CHECKS:
            try:
                check_instance = check_cls(self._config)
                result = check_instance.run()
                results.append(result)
            except Exception as exc:
                results.append(
                    ValidationResult(
                        name=check_cls.__name__,
                        success=False,
                        severity=Severity.CRITICAL,
                        message=f"Check crashed during execution",
                        details={"error": str(exc)},
                        recommendation="Fix the check implementation or dependency.",
                    )
                )

        elapsed = time.monotonic() - t0
        self._report = ValidationReport(results=results, execution_time=elapsed)
        return self._report

    def generate_report_markdown(self) -> str:
        """Generate a human-readable markdown report."""
        if self._report is None:
            return "# Environment Validation\n\nNo validation has been run yet."
        return generate_report_markdown(self._report)

    @staticmethod
    def validate_and_exit(config: Any = None) -> ValidationReport:
        """Convenience: validate, log report, exit on critical failure."""
        validator = EnvironmentValidator(config)
        report = validator.validate()
        markdown = validator.generate_report_markdown()
        log.info("Environment validation report:\n%s", markdown)

        if report.critical:
            log.critical("Critical failures detected — cannot continue safely.")
            import sys

            sys.exit(1)
        if report.errors:
            log.error("Errors detected — startup may be degraded.")
            log.info("Review the report above before proceeding.")

        return report
