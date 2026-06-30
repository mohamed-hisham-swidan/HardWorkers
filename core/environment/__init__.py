"""Environment validation framework.

Validates the runtime environment before application startup,
providing early, human-readable diagnostics for misconfiguration.
"""

from core.environment.models import Severity, ValidationReport, ValidationResult
from core.environment.validator import EnvironmentValidator

__all__ = [
    "EnvironmentValidator",
    "Severity",
    "ValidationReport",
    "ValidationResult",
]
