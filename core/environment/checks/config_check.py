"""Configuration files validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.environment.models import Severity, ValidationResult

REQUIRED_CONFIG_FILES: list[dict[str, Any]] = [
    {"path": "./.env", "purpose": "Environment variables", "required": False, "template": "./.env.example"},
    {"path": "./data/settings.json", "purpose": "User settings", "required": False},
    {"path": "./ruff.toml", "purpose": "Ruff linter configuration", "required": False},
]

REQUIRED_ENV_VARS: list[dict[str, Any]] = [
    {"key": "OLLAMA_BASE_URL", "default": "http://localhost:11434", "required": False},
    {"key": "DB_PATH", "default": "./data/hardworkers.db", "required": False},
    {"key": "LOG_DIR", "default": "./logs", "required": False},
    {"key": "UI_WIDTH", "default": "1280", "required": False},
    {"key": "UI_HEIGHT", "default": "900", "required": False},
]

SENSITIVE_ENV_VARS: list[dict[str, Any]] = [
    {"key": "JWT_SECRET", "dev_default": "dev-secret-change-in-production"},
    {"key": "ADMIN_USERNAME", "dev_default": "admin"},
    {"key": "ADMIN_PASSWORD", "dev_default": "admin"},
]


class ConfigCheck:
    def __init__(self, config: Any = None) -> None:
        self._config = config

    def run(self) -> ValidationResult:
        config_file_status: list[dict[str, Any]] = []
        env_var_status: list[dict[str, Any]] = []
        security_issues: list[str] = []
        warnings: list[str] = []

        for entry in REQUIRED_CONFIG_FILES:
            status = self._check_config_file(entry)
            config_file_status.append(status)
            if not status["exists"] and entry.get("required", False):
                warnings.append(f"{entry['path']}: required config missing")

        for entry in REQUIRED_ENV_VARS:
            status = self._check_env_var(entry)
            env_var_status.append(status)
            if not status["set"] and entry.get("required", False):
                warnings.append(f"{entry['key']}: required env var not set")

        for entry in SENSITIVE_ENV_VARS:
            current = os.getenv(entry["key"], "")
            if current == entry["dev_default"]:
                security_issues.append(f"{entry['key']} is still set to dev default '{entry['dev_default']}'")

        env_file_present = any(s["exists"] for s in config_file_status if ".env" in s["path"])
        if not env_file_present and not security_issues:
            template_path = Path("./.env.example")
            if template_path.exists():
                warnings.append(".env file not found — copy .env.example to .env")

        overall = len(security_issues) == 0
        severity = Severity.WARNING if security_issues else Severity.WARNING if warnings else Severity.INFO

        return ValidationResult(
            name="Configuration",
            success=overall,
            severity=severity,
            message="Configuration check complete."
            if overall and not warnings
            else f"Configuration issues: {len(security_issues)} security, {len(warnings)} warnings.",
            details={
                "config_files": config_file_status,
                "env_vars": env_var_status,
                "security_issues": security_issues,
                "warnings": warnings,
                "env": os.getenv("ENV", "development"),
            },
            recommendation="Review security issues above. Set proper secrets in production." if security_issues else "",
        )

    @staticmethod
    def _check_config_file(entry: dict[str, Any]) -> dict[str, Any]:
        path = Path(entry["path"])
        result: dict[str, Any] = {
            "path": str(path.resolve()),
            "relative_path": entry["path"],
            "purpose": entry["purpose"],
            "exists": path.exists(),
            "required": entry.get("required", False),
            "readable": False,
        }

        template_path = entry.get("template")
        if template_path:
            result["template_exists"] = Path(template_path).exists()
        else:
            result["template_exists"] = False

        if path.exists() and path.is_file():
            try:
                size = path.stat().st_size
                result["readable"] = True
                result["size_bytes"] = size
            except (OSError, PermissionError):
                result["readable"] = False

        return result

    @staticmethod
    def _check_env_var(entry: dict[str, Any]) -> dict[str, Any]:
        value = os.getenv(entry["key"])
        result: dict[str, Any] = {
            "key": entry["key"],
            "set": value is not None and value != "",
            "value": "***SET***" if value else None,
            "default": entry.get("default"),
            "required": entry.get("required", False),
        }
        if value is None or value == "":
            result["value"] = entry.get("default")
            result["using_default"] = True
        else:
            result["using_default"] = False
        return result
