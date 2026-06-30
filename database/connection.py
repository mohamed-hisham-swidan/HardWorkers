"""Thread-local SQLite connection manager with multi-process safety.

Each OS thread gets exactly one connection, eliminating the shared-pool
concurrency hazards.  A cross-process lock serialises write transactions
so that multiple FastAPI workers (or a combined API + desktop setup) can
safely share the same database file.

Usage::

    cm = ConnectionManager(Path("data/db.sqlite"))
    with cm.transaction() as conn:
        conn.execute("INSERT INTO ...", (val,))
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from utils.logging_setup import get_logger

log = get_logger("database.connection")

try:
    import msvcrt

    _HAS_LOCK = True
except ImportError:
    _HAS_LOCK = False


class _InterProcessLock:
    """Cross-process file lock using platform-native locking.

    On Windows this uses ``msvcrt.locking``; on other platforms it degrades
    gracefully to a no-op (logs a warning).
    """

    def __init__(self, lock_path: Path, timeout_ms: int = 15_000) -> None:
        self._path = lock_path
        self._timeout = timeout_ms / 1000.0
        self._fd: int | None = None

    def acquire(self) -> bool:
        if not _HAS_LOCK:
            log.warning("Inter-process locking not available on this platform")
            return True
        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            try:
                fd = os.open(str(self._path), os.O_CREAT | os.O_RDWR, 0o644)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                self._fd = fd
                return True
            except (OSError, BlockingIOError):
                if self._fd is not None:
                    os.close(self._fd)
                    self._fd = None
                time.sleep(0.05)
        return False

    def release(self) -> None:
        if self._fd is not None:
            try:
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            os.close(self._fd)
            self._fd = None


class ConnectionManager:
    """Provides a per-thread SQLite connection with cross-process write locking.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.
    busy_timeout_ms:
        SQLite ``busy_timeout`` value in milliseconds.
    enable_lock:
        Whether to use the cross-process file lock (default ``True``).
    """

    _local: threading.local

    def __init__(
        self,
        db_path: Path,
        busy_timeout_ms: int = 10_000,
        enable_lock: bool = True,
    ) -> None:
        self._db_path = db_path
        self._busy_timeout_ms = busy_timeout_ms
        self._enable_lock = enable_lock
        self._local = threading.local()
        self._lock_path = db_path.parent / f".{db_path.name}.lock"
        self._lock = _InterProcessLock(self._lock_path)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager that yields a connection and auto-commits or rolls back.

        Acquires the cross-process write lock before returning the connection.
        On timeout a ``sqlite3.OperationalError`` is raised.
        """
        acquired = False
        if self._enable_lock:
            acquired = self._lock.acquire()
            if not acquired:
                raise sqlite3.OperationalError(
                    "Could not acquire database lock within timeout — "
                    "another process may be holding it."
                )
        conn = self._connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if acquired:
                self._lock.release()

    def close_thread_connection(self) -> None:
        """Close the connection belonging to the calling thread."""
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception as exc:
                log.warning("Error closing thread connection: %s", exc)
            finally:
                self._local.conn = None

    def integrity_check(self) -> bool:
        """Run SQLite integrity_check and return True if database is healthy."""
        try:
            conn = self._connection()
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            return result == "ok"
        except Exception as exc:
            log.error("Integrity check failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connection(self) -> sqlite3.Connection:
        conn: sqlite3.Connection | None = getattr(self._local, "conn", None)
        if conn is None or not self._is_alive(conn):
            conn = self._create()
            self._local.conn = conn
        return conn

    def _create(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), timeout=self._busy_timeout_ms / 1000)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
        conn.execute("PRAGMA cache_size=-8000")  # 8 MB page cache
        log.debug("Created SQLite connection — thread=%s path=%s", threading.current_thread().name, self._db_path)
        return conn

    @staticmethod
    def _is_alive(conn: sqlite3.Connection) -> bool:
        try:
            conn.execute("SELECT 1")
            return True
        except (sqlite3.ProgrammingError, sqlite3.OperationalError):
            return False
