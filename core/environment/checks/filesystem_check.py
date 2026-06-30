"""Filesystem and directory permissions validation."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from core.environment.models import Severity, ValidationResult

REQUIRED_DIRECTORIES: list[dict[str, Any]] = [
    {"path": "./workspace", "purpose": "Agent workspace", "create": True},
    {"path": "./data", "purpose": "Application data (DB, FAISS index)", "create": True},
    {"path": "./logs", "purpose": "Application logs", "create": True},
    {"path": "./config", "purpose": "Configuration files", "create": False},
    {"path": "./vault", "purpose": "Obsidian vault", "create": False},
    {"path": "./assets", "purpose": "Static assets", "create": False},
]

REQUIRED_FILES: list[dict[str, Any]] = [
    {"path": "./.env.example", "purpose": "Environment template", "optional": True},
    {"path": "./requirements.txt", "purpose": "Python dependencies", "optional": False},
]


class FilesystemCheck:
    def __init__(self, config: Any = None) -> None:
        self._config = config

    def run(self) -> ValidationResult:
        directory_status: list[dict[str, Any]] = []
        file_status: list[dict[str, Any]] = []
        failures: list[str] = []
        warnings: list[str] = []

        for entry in REQUIRED_DIRECTORIES:
            status = self._check_directory(entry)
            directory_status.append(status)
            if not status["exists"] and entry.get("create", False):
                warnings.append(f"{entry['path']}: missing but will be auto-created")
            elif not status["exists"] and not entry.get("create", False):
                warnings.append(f"{entry['path']}: does not exist (optional)")
            if not status.get("writable", True) and status["exists"]:
                failures.append(f"{entry['path']}: not writable")

        for entry in REQUIRED_FILES:
            status = self._check_file(entry)
            file_status.append(status)
            if not status["exists"] and not entry.get("optional", False):
                failures.append(f"{entry['path']}: required file not found")
            elif not status["exists"] and entry.get("optional", False):
                warnings.append(f"{entry['path']}: optional file not found")

        writability_check = self._check_temp_writability()
        if not writability_check["writable"]:
            failures.append(f"Temp directory ({writability_check['path']}) is not writable")

        overall = len(failures) == 0
        severity = Severity.CRITICAL if failures else Severity.WARNING if warnings else Severity.INFO

        return ValidationResult(
            name="Filesystem",
            success=overall,
            severity=severity,
            message="Filesystem check complete."
            if overall
            else f"Filesystem issues found: {len(failures)} failures, {len(warnings)} warnings.",
            details={
                "directories": directory_status,
                "files": file_status,
                "temp_writable": writability_check,
                "cwd": str(Path.cwd()),
                "failures": failures,
                "warnings": warnings,
            },
            recommendation="Ensure all required directories exist and are writable." if failures else "",
        )

    @staticmethod
    def _check_directory(entry: dict[str, Any]) -> dict[str, Any]:
        path = Path(entry["path"])
        result: dict[str, Any] = {
            "path": str(path.resolve()),
            "relative_path": entry["path"],
            "purpose": entry["purpose"],
            "exists": path.exists(),
            "is_dir": path.is_dir() if path.exists() else False,
            "writable": False,
        }

        if path.exists() and path.is_dir():
            try:
                test_file = path / ".write_test"
                test_file.write_text("")
                test_file.unlink()
                result["writable"] = True
            except (OSError, PermissionError):
                result["writable"] = False

        return result

    @staticmethod
    def _check_file(entry: dict[str, Any]) -> dict[str, Any]:
        path = Path(entry["path"])
        result: dict[str, Any] = {
            "path": str(path.resolve()),
            "relative_path": entry["path"],
            "purpose": entry["purpose"],
            "exists": path.exists(),
            "is_file": path.is_file() if path.exists() else False,
            "readable": False,
            "optional": entry.get("optional", False),
        }

        if path.exists() and path.is_file():
            try:
                with path.open("rb") as f:
                    f.read(1)
                result["readable"] = True
            except (OSError, PermissionError):
                result["readable"] = False

        return result

    @staticmethod
    def _check_temp_writability() -> dict[str, Any]:
        try:
            with tempfile.NamedTemporaryFile(delete=True) as tmp:
                return {"path": tempfile.gettempdir(), "writable": True, "test_file": tmp.name}
        except (OSError, PermissionError):
            return {"path": tempfile.gettempdir(), "writable": False, "test_file": None}
