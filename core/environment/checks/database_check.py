"""Database availability and health validation."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from core.environment.models import Severity, ValidationResult


class DatabaseCheck:
    def __init__(self, config: Any = None) -> None:
        self._config = config

    def run(self) -> ValidationResult:
        db_details: dict[str, Any] = {}
        failures: list[str] = []
        warnings: list[str] = []

        # Check sqlite3 module availability
        sqlite_version: str = sqlite3.sqlite_version_info
        sqlite_version_str = f"{sqlite_version[0]}.{sqlite_version[1]}.{sqlite_version[2]}"
        db_details["sqlite_module_version"] = sqlite_version_str

        if sqlite_version < (3, 35):
            warnings.append(f"SQLite {sqlite_version_str} is old — consider upgrading for better WAL support")

        # Check database file
        db_path = self._resolve_db_path()
        db_details["database_path"] = str(db_path)
        db_details["database_exists"] = db_path.exists()

        # Try connecting
        wal_supported = False
        integrity_ok = None
        journal_mode = None

        if db_path.exists() or True:
            try:
                db_path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("PRAGMA busy_timeout=5000")

                cursor = conn.execute("PRAGMA journal_mode")
                journal_mode = cursor.fetchone()[0]
                wal_supported = journal_mode == "wal"

                cursor = conn.execute("PRAGMA integrity_check")
                integrity_result = cursor.fetchone()[0]
                integrity_ok = integrity_result == "ok"

                cursor = conn.execute("SELECT sqlite_version()")
                conn_version = cursor.fetchone()[0]
                db_details["connected_version"] = conn_version

                conn.close()

                if not integrity_ok:
                    failures.append("Database integrity check failed — possible corruption")

            except sqlite3.Error as exc:
                failures.append(f"Database connection failed: {exc}")
                db_details["connection_error"] = str(exc)

        db_details["journal_mode"] = journal_mode
        db_details["wal_supported"] = wal_supported
        db_details["integrity_ok"] = integrity_ok

        # Check migrations
        migration_status = self._check_migrations(db_path)
        db_details["migrations"] = migration_status
        if migration_status.get("error"):
            warnings.append(migration_status["error"])

        overall = len(failures) == 0
        severity = Severity.CRITICAL if failures else Severity.WARNING if warnings else Severity.INFO

        return ValidationResult(
            name="Database",
            success=overall,
            severity=severity,
            message="Database check complete."
            if overall and not warnings
            else f"Database issues: {len(failures)} failures, {len(warnings)} warnings.",
            details=db_details,
            recommendation="Run database migration or repair." if failures else "",
        )

    def _resolve_db_path(self) -> Path:
        if self._config and hasattr(self._config, "database") and hasattr(self._config.database, "path"):
            return Path(self._config.database.path)
        db_env = __import__("os").getenv("DB_PATH", "./data/hardworkers.db")
        return Path(db_env)

    @staticmethod
    def _check_migrations(db_path: Path) -> dict[str, Any]:
        result: dict[str, Any] = {
            "applied": [],
            "pending": [],
            "error": None,
        }
        if not db_path.exists():
            result["error"] = "Database file does not exist yet (will be created on first run)"
            return result

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = [row[0] for row in cursor.fetchall()]
            result["tables"] = tables
            result["table_count"] = len(tables)

            expected_tables = {
                "chat_sessions",
                "messages",
                "model_registry",
                "memory_profiles",
                "workspaces",
                "user_facts",
                "chat_memory_facts",
                "chat_summaries",
                "conversation_summaries",
                "settings",
                "profiles",
            }
            found = expected_tables & set(tables)
            missing = expected_tables - set(tables)
            result["expected_tables"] = len(expected_tables)
            result["found_tables"] = len(found)
            result["missing_tables"] = sorted(missing)

            conn.close()
        except sqlite3.Error as exc:
            result["error"] = str(exc)

        return result
