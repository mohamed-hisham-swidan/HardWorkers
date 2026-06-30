"""Validator orchestrator — runs multiple checkers and aggregates results."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qa.checkers import (
    CodeQualityChecker,
    ImportChecker,
    SecurityChecker,
    SyntaxChecker,
    TestRunner,
)
from qa.models import CheckStatus, ValidationResult

log = logging.getLogger("hard_workers.qa.validator")


@dataclass
class ValidationReport:
    """Complete validation report with summary."""

    timestamp: str = ""
    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration_s: float = 0.0
    results: list[ValidationResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.errors == 0

    @property
    def summary(self) -> str:
        return (
            f"QA Validation: {self.passed}/{self.total_checks} passed, "
            f"{self.failed} failed, {self.errors} errors, "
            f"{self.skipped} skipped ({self.duration_s:.1f}s)"
        )


class QAValidator:
    """Orchestrates all QA checks and produces a unified report."""

    def __init__(self, project_root: str | Path | None = None) -> None:
        self._root = Path(project_root or ".")
        self._checkers: list[tuple[str, Any]] = []

    # ── Checker registration ────────────────────────────────────────────────────

    def register_defaults(self) -> QAValidator:
        """Register all built-in checkers with default settings."""
        self._checkers = [
            ("Syntax Check", SyntaxChecker(self._root)),
            ("Import Resolution", ImportChecker(self._root)),
            ("Pytest Tests", TestRunner(self._root)),
            ("Code Quality", CodeQualityChecker(self._root)),
            ("Security Scan", SecurityChecker(self._root)),
        ]
        return self

    def register(self, name: str, checker: Any) -> QAValidator:
        self._checkers.append((name, checker))
        return self

    # ── Execution ───────────────────────────────────────────────────────────────

    def run_all(self, include: list[str] | None = None) -> ValidationReport:
        """Run all registered checkers and return a report."""
        from datetime import datetime

        t0 = time.monotonic()
        results: list[ValidationResult] = []

        for name, checker in self._checkers:
            if include and name not in include:
                results.append(
                    ValidationResult(
                        name=name,
                        status=CheckStatus.SKIPPED,
                        details="Excluded by filter",
                    )
                )
                continue

            log.info("Running check: %s", name)
            try:
                chk_t0 = time.monotonic()
                result = checker.run()
                result.duration_s = time.monotonic() - chk_t0
                results.append(result)
            except Exception as exc:
                log.error("Checker '%s' raised an exception: %s", name, exc)
                results.append(
                    ValidationResult(
                        name=name,
                        status=CheckStatus.ERROR,
                        details=str(exc),
                        errors=[str(exc)],
                    )
                )

        elapsed = time.monotonic() - t0
        report = ValidationReport(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total_checks=len(results),
            passed=sum(1 for r in results if r.status == CheckStatus.PASSED),
            failed=sum(1 for r in results if r.status == CheckStatus.FAILED),
            skipped=sum(1 for r in results if r.status == CheckStatus.SKIPPED),
            errors=sum(1 for r in results if r.status == CheckStatus.ERROR),
            duration_s=elapsed,
            results=results,
        )
        log.info(report.summary)
        return report

    def run_selected(self, names: list[str]) -> ValidationReport:
        return self.run_all(include=names)

    # ── Report output ───────────────────────────────────────────────────────────

    def print_report(self, report: ValidationReport) -> None:
        """Print a human-readable validation report."""
        print(f"\n{'=' * 60}")
        print("  QA Validation Report")
        print(f"  {report.timestamp}")
        print(f"{'=' * 60}")
        print(f"  Duration: {report.duration_s:.1f}s")
        print(f"  Total:    {report.total_checks}")
        print(f"  Passed:   {report.passed}")
        print(f"  Failed:   {report.failed}")
        print(f"  Errors:   {report.errors}")
        print(f"  Skipped:  {report.skipped}")
        print(f"{'=' * 60}")

        for result in report.results:
            icon = {
                CheckStatus.PASSED: "  OK",
                CheckStatus.FAILED: "FAIL",
                CheckStatus.ERROR: " ERR",
                CheckStatus.SKIPPED: "SKIP",
            }.get(result.status, " ??")
            print(f"  [{icon}] {result.name} ({result.duration_s:.2f}s)")
            if result.details:
                print(f"         {result.details[:120]}")
            if result.warnings:
                for w in result.warnings[:3]:
                    print(f"         Warning: {w[:100]}")
            if result.errors:
                for e in result.errors[:3]:
                    print(f"         Error: {e[:100]}")

        print(f"{'=' * 60}")
        if report.success:
            print("  ALL CHECKS PASSED")
        else:
            print(f"  {report.failed} check(s) FAILED, {report.errors} error(s)")

    def to_dict(self, report: ValidationReport) -> dict[str, Any]:
        return {
            "timestamp": report.timestamp,
            "success": report.success,
            "duration_s": report.duration_s,
            "total_checks": report.total_checks,
            "passed": report.passed,
            "failed": report.failed,
            "skipped": report.skipped,
            "errors": report.errors,
            "results": [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "details": r.details,
                    "duration_s": r.duration_s,
                    "errors": r.errors,
                    "warnings": r.warnings,
                }
                for r in report.results
            ],
        }
