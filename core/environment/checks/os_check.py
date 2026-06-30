"""Operating system and platform validation."""

from __future__ import annotations

import platform
import sys
from typing import Any

from core.environment.models import Severity, ValidationResult

SUPPORTED_SYSTEMS = ["Windows", "Linux", "Darwin"]  # Darwin = macOS

SUPPORTED_ARCHITECTURES = ["AMD64", "x86_64", "arm64", "aarch64"]

MINIMUM_WINDOWS_VERSION = (10, 0)  # Windows 10+


class OSCheck:
    def __init__(self, config: Any = None) -> None:
        self._config = config

    def run(self) -> ValidationResult:
        system = platform.system()
        release = platform.release()
        version = platform.version()
        architecture = platform.machine()
        processor = platform.processor()
        node = platform.node()

        details: dict[str, Any] = {
            "system": system,
            "release": release,
            "version": version,
            "architecture": architecture,
            "processor": processor,
            "hostname": node,
            "platform": sys.platform,
            "is_64bit": sys.maxsize > 2**32,
        }

        failures: list[str] = []
        warnings: list[str] = []

        if system not in SUPPORTED_SYSTEMS:
            failures.append(f"Operating system '{system}' is not officially supported")
        elif system == "Windows":
            try:
                parts = release.split(".")
                win_major = int(parts[0])
                win_minor = int(parts[1]) if len(parts) > 1 else 0
                if (win_major, win_minor) < MINIMUM_WINDOWS_VERSION:
                    warnings.append(
                        f"Windows {release} is below minimum {MINIMUM_WINDOWS_VERSION[0]}.{MINIMUM_WINDOWS_VERSION[1]}"
                    )
            except (ValueError, IndexError):
                warnings.append(f"Could not parse Windows version from: {release}")

        if architecture not in SUPPORTED_ARCHITECTURES:
            warnings.append(f"Architecture '{architecture}' is not widely tested with this application")

        if not details["is_64bit"]:
            failures.append("32-bit Python is not supported — use 64-bit")

        overall = len(failures) == 0
        severity = Severity.CRITICAL if failures else Severity.WARNING if warnings else Severity.INFO

        return ValidationResult(
            name="Operating System",
            success=overall,
            severity=severity,
            message=f"OS check complete: {system} {release} on {architecture}."
            if overall
            else f"OS issues: {len(failures)} failures, {len(warnings)} warnings.",
            details=details,
            recommendation="Use a supported 64-bit operating system (Windows 10+, Linux, macOS)." if failures else "",
        )
