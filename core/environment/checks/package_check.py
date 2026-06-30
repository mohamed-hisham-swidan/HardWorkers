"""Installed packages version validation against requirements.

Package tiers:
  CORE    - Missing = CRITICAL, blocks startup
  FEATURE - Missing = WARNING, degraded but functional
  OPTIONAL - Missing = INFO, not needed for core operation
"""

from __future__ import annotations

import logging
import time
from typing import Any

from packaging.version import Version

from core.environment.models import Severity, ValidationResult

log = logging.getLogger("hard_workers.environment.checks.package_check")

# ── instrumentation: measure importlib.metadata import time ────────────────
_t0_import = time.monotonic()
import importlib.metadata
_t1_import = time.monotonic()
log.info("TIMING import importlib.metadata: %.3fs", _t1_import - _t0_import)

CORE_PACKAGES: list[dict[str, str]] = [
    {"name": "flet", "required": ">=0.85.0"},
    {"name": "requests", "required": ">=2.32.0"},
    {"name": "urllib3", "required": ">=2.2.0"},
    {"name": "numpy", "required": ">=1.26.0"},
    {"name": "tiktoken", "required": ">=0.7.0"},
    {"name": "pillow", "required": ">=10.4.0"},
    {"name": "pydantic", "required": ">=2.9.0"},
    {"name": "cryptography", "required": ">=42.0.0"},
]

FEATURE_PACKAGES: list[dict[str, str]] = [
    {"name": "faiss-cpu", "required": ">=1.8.0", "feature": "Vector memory search"},
    {"name": "psutil", "required": ">=6.0.0", "feature": "System diagnostics"},
    {"name": "pywin32", "required": ">=306", "feature": "Windows clipboard (image paste)"},
    {"name": "pyperclip", "required": ">=1.11.0", "feature": "Clipboard access"},
    {"name": "pyttsx3", "required": ">=2.90", "feature": "Text-to-speech"},
    {"name": "SpeechRecognition", "required": ">=3.10.0", "feature": "Speech-to-text"},
    {"name": "fastapi", "required": ">=0.115.0", "feature": "REST API server"},
    {"name": "uvicorn", "required": ">=0.30.0", "feature": "ASGI server"},
    {"name": "websockets", "required": ">=13.0", "feature": "WebSocket streaming"},
]

OPTIONAL_PACKAGES: list[dict[str, str]] = [
    {"name": "pypdf", "required": ">=4.0.0", "feature": "PDF document import"},
    {"name": "python-docx", "required": ">=1.1.0", "feature": "DOCX document import"},
    {"name": "beautifulsoup4", "required": ">=4.12.0", "feature": "HTML document import"},
    {"name": "pyyaml", "required": ">=6.0", "feature": "YAML parsing"},
    {"name": "pytesseract", "required": ">=0.3.10", "feature": "OCR / vision"},
    {"name": "python-jose", "required": ">=3.3.0", "feature": "JWT auth"},
    {"name": "python-multipart", "required": ">=0.0.12", "feature": "File uploads"},
    {"name": "pydantic-settings", "required": ">=2.5.0", "feature": "Settings management"},
    {"name": "pytest", "required": ">=8.0.0", "feature": "Test runner"},
    {"name": "sentence-transformers", "required": ">=2.2.0", "feature": "Embedding models"},
    {"name": "edge-tts", "required": ">=7.2.0", "feature": "Edge TTS"},
    {"name": "opencv-python", "required": ">=4.8.0", "feature": "Advanced image ops"},
    {"name": "transformers", "required": ">=4.36.0", "feature": "Model training"},
    {"name": "torch", "required": ">=2.1.0", "feature": "Deep learning"},
    {"name": "datasets", "required": ">=2.16.0", "feature": "Training datasets"},
]


def _parse_spec(spec: str) -> tuple[str, str]:
    spec = spec.strip()
    for op in [">=", "<=", "!=", "==", ">", "<", "~="]:
        if op in spec:
            parts = spec.split(op, 1)
            return op, parts[1].strip()
    return "==", spec


class PackageCheck:
    def __init__(self, config: Any = None) -> None:
        _t0 = time.monotonic()
        self._config = config
        _t1 = time.monotonic()
        log.info("TIMING PackageCheck.__init__: %.6fs", _t1 - _t0)

    def run(self) -> ValidationResult:
        _t0_run = time.monotonic()
        all_statuses: list[dict[str, Any]] = []
        criticals: list[str] = []
        warnings: list[str] = []
        infos: list[str] = []

        for pkg in CORE_PACKAGES:
            status = self._check_package(pkg)
            status["tier"] = "CORE"
            all_statuses.append(status)
            if not status["installed"] or not status["compatible"]:
                criticals.append(f"{pkg['name']}: {status.get('error', 'missing')}")

        for pkg in FEATURE_PACKAGES:
            status = self._check_package(pkg)
            status["tier"] = "FEATURE"
            all_statuses.append(status)
            if not status["installed"] or not status["compatible"]:
                warnings.append(f"{pkg['name']} ({pkg.get('feature', '')}): {status.get('error', 'missing')}")

        for pkg in OPTIONAL_PACKAGES:
            status = self._check_package(pkg)
            status["tier"] = "OPTIONAL"
            all_statuses.append(status)
            if status["installed"] and not status["compatible"]:
                infos.append(f"{pkg['name']}: version mismatch ({status.get('error', '')})")
        _t1_run = time.monotonic()
        log.info("TIMING PackageCheck.run (total): %.3fs (%d packages)", _t1_run - _t0_run,
                 len(CORE_PACKAGES) + len(FEATURE_PACKAGES) + len(OPTIONAL_PACKAGES))

        has_critical = len(criticals) > 0
        has_warnings = len(warnings) > 0
        len(infos) > 0

        if has_critical:
            severity = Severity.CRITICAL
            message = f"Missing {len(criticals)} core package(s) — application cannot start."
            success = False
            recommendation = "Run: pip install -r requirements.txt"
        elif has_warnings:
            severity = Severity.WARNING
            message = f"All core packages present. {len(warnings)} feature package(s) missing."
            success = True
            recommendation = "Install feature packages as needed: pip install <package>"
        else:
            severity = Severity.INFO
            message = "All required packages are installed and compatible."
            success = True
            recommendation = ""

        return ValidationResult(
            name="Installed Packages",
            success=success,
            severity=severity,
            message=message,
            details={
                "core_count": len(CORE_PACKAGES),
                "feature_count": len(FEATURE_PACKAGES),
                "optional_count": len(OPTIONAL_PACKAGES),
                "total": len(CORE_PACKAGES) + len(FEATURE_PACKAGES) + len(OPTIONAL_PACKAGES),
                "critical_failures": len(criticals),
                "warning_failures": len(warnings),
                "info_notes": len(infos),
                "critical_packages": criticals,
                "warning_packages": warnings,
                "packages": all_statuses,
            },
            recommendation=recommendation,
        )

    @staticmethod
    def _check_package(pkg: dict[str, str]) -> dict[str, Any]:
        name = pkg["name"]
        required_spec = pkg["required"]
        result: dict[str, Any] = {
            "name": name,
            "required": required_spec,
            "feature": pkg.get("feature", ""),
            "installed": False,
            "installed_version": None,
            "compatible": False,
            "error": None,
        }

        _t0_v = time.monotonic()
        try:
            installed = importlib.metadata.version(name)
            _t1_v = time.monotonic()
            log.info("TIMING importlib.metadata.version('%s'): %.6fs", name, _t1_v - _t0_v)
            result["installed"] = True
            result["installed_version"] = installed
        except importlib.metadata.PackageNotFoundError:
            _t1_v = time.monotonic()
            log.info("TIMING importlib.metadata.version('%s') — NOT FOUND: %.6fs", name, _t1_v - _t0_v)
            result["error"] = "not installed"
            return result

        try:
            op, ver_str = _parse_spec(required_spec)
            required_ver = Version(ver_str)
            installed_ver = Version(result["installed_version"])

            if op == ">=":
                result["compatible"] = installed_ver >= required_ver
            elif op == "==":
                result["compatible"] = installed_ver == required_ver
            elif op == ">":
                result["compatible"] = installed_ver > required_ver
            elif op == "<":
                result["compatible"] = installed_ver < required_ver
            elif op == "<=":
                result["compatible"] = installed_ver <= required_ver
            elif op == "!=":
                result["compatible"] = installed_ver != required_ver
            elif op == "~=":
                result["compatible"] = (
                    installed_ver.major == required_ver.major and installed_ver.minor >= required_ver.minor
                )
            else:
                result["compatible"] = True

            if not result["compatible"]:
                result["error"] = f"version {installed} does not satisfy {required_spec}"

        except Exception as exc:
            result["compatible"] = False
            result["error"] = f"version comparison error: {exc}"

        return result
