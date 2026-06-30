"""Python runtime version validation."""

from __future__ import annotations

import sys
from typing import Any

from packaging.version import Version

from core.environment.models import Severity, ValidationResult

SUPPORTED_VERSIONS = {
    "minimum": Version("3.11"),
    "maximum": Version("3.14"),
    "recommended": Version("3.12"),
}


class PythonCheck:
    def __init__(self, config: Any = None) -> None:
        self._config = config

    def run(self) -> ValidationResult:
        current = Version(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        details = {
            "current_version": str(current),
            "python_executable": sys.executable,
            "python_implementation": sys.implementation.name,
            "minimum_required": str(SUPPORTED_VERSIONS["minimum"]),
            "maximum_supported": str(SUPPORTED_VERSIONS["maximum"]),
            "recommended": str(SUPPORTED_VERSIONS["recommended"]),
            "build_info": sys.version,
        }

        if current < SUPPORTED_VERSIONS["minimum"]:
            return ValidationResult(
                name="Python Version",
                success=False,
                severity=Severity.CRITICAL,
                message=f"Python {current} is below minimum required {SUPPORTED_VERSIONS['minimum']}.",
                details=details,
                recommendation=f"Upgrade Python to {SUPPORTED_VERSIONS['recommended']} or later.",
            )

        if SUPPORTED_VERSIONS["maximum"] and current > SUPPORTED_VERSIONS["maximum"]:
            return ValidationResult(
                name="Python Version",
                success=False,
                severity=Severity.WARNING,
                message=f"Python {current} exceeds tested maximum {SUPPORTED_VERSIONS['maximum']}.",
                details=details,
                recommendation=f"Downgrade to Python {SUPPORTED_VERSIONS['recommended']} for best compatibility.",
            )

        if current < SUPPORTED_VERSIONS["recommended"]:
            return ValidationResult(
                name="Python Version",
                success=True,
                severity=Severity.WARNING,
                message=f"Python {current} is supported, but {SUPPORTED_VERSIONS['recommended']} is recommended.",
                details=details,
                recommendation=f"Consider upgrading to Python {SUPPORTED_VERSIONS['recommended']}.",
            )

        return ValidationResult(
            name="Python Version",
            success=True,
            severity=Severity.INFO,
            message=f"Python {current} is fully supported.",
            details=details,
            recommendation="",
        )
