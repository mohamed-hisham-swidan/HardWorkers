"""Ollama process lifecycle management.

Responsibilities:
  - Detect whether Ollama is running (health check).
  - Start Ollama as a subprocess if not running.
  - Stop Ollama gracefully.
  - Poll until Ollama is ready to serve requests.
  - Provide a single entry point: ensure_running().

This service has zero UI dependencies and zero Flet imports.
It is safe to use from any layer (CLI, API, UI controllers).
"""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable

from config.settings import OllamaConfig
from services.ai.ollama_client import OllamaClient
from utils.logging_setup import get_logger

log = get_logger("services.infrastructure.ollama_lifecycle")


class OllamaLifecycleService:
    """Manages the Ollama server process lifecycle.

    Public API:
        is_running()      — health check via HTTP.
        start()           — launch Ollama subprocess.
        stop()            — terminate Ollama subprocess.
        wait_until_ready()— poll health endpoint until Ollama responds.
        ensure_running()  — high-level: start + wait, return status string.

    Architecture note: this is an Infrastructure-layer service.
    It may be consumed by Application-layer orchestration services
    (e.g. a StartupOrchestrator) but never by UI code directly.
    """

    def __init__(
        self,
        client: OllamaClient,
        config: OllamaConfig,
        *,
        bin_path: str = "ollama",
        serve_args: list[str] | None = None,
        health_poll_interval: float = 0.5,
        max_startup_attempts: int = 6,
        startup_timeout: float = 30.0,
    ) -> None:
        self._client = client
        self._cfg = config
        self._bin_path = bin_path
        self._serve_args = serve_args or ["serve"]
        self._poll_interval = health_poll_interval
        self._max_attempts = max_startup_attempts
        self._startup_timeout = startup_timeout
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_running(self, *, quick: bool = True) -> bool:
        """Check whether Ollama is reachable via HTTP health check."""
        return self._client.health_check(quick=quick)

    def start(self) -> bool:
        """Launch the Ollama server process.

        This method does NOT check is_running() — the caller
        (e.g. ensure_running) is responsible for that. This avoids
        a redundant health-check delay when called from the startup
        path.

        Returns True if the binary was found and launched (does not
        guarantee readiness — call wait_until_ready for that).
        Returns False if the binary cannot be found or launch fails.
        """
        try:
            self._process = subprocess.Popen(
                [self._bin_path, *self._serve_args],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log.info("Ollama process started (PID %s)", self._process.pid)
            return True
        except FileNotFoundError:
            log.warning(
                "Ollama binary '%s' not found — download from https://ollama.com",
                self._bin_path,
            )
            return False
        except Exception as exc:
            log.warning("Failed to launch Ollama: %s", exc)
            return False

    def stop(self, *, timeout: float | None = None) -> bool:
        """Stop the Ollama server process.

        If this service started the process, it terminates it.
        If Ollama was already running externally, this is a no-op
        (we do not kill processes we did not start).

        Returns True if the process was stopped or was not ours to stop.
        """
        if self._process is None:
            log.info("No Ollama process to stop (was externally managed)")
            return True
        try:
            self._process.terminate()
            self._process.wait(timeout=timeout or 5.0)
            log.info("Ollama process terminated")
            self._process = None
            return True
        except Exception as exc:
            log.warning("Failed to stop Ollama gracefully: %s", exc)
            try:
                self._process.kill()
                self._process = None
            except Exception:
                log.debug("Process kill failed (already terminated)")
            return False

    def wait_until_ready(
        self,
        *,
        max_attempts: int | None = None,
        poll_interval: float | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> bool:
        """Poll the health endpoint until Ollama responds.

        Args:
            max_attempts: How many polls before giving up (default 6).
            poll_interval: Seconds between polls (default 0.5).
            on_progress: Optional callback (attempt, max_attempts)
                         for progress reporting (e.g. to show spinner).

        Returns True when Ollama becomes reachable, False on timeout.
        """
        attempts = max_attempts if max_attempts is not None else self._max_attempts
        interval = poll_interval if poll_interval is not None else self._poll_interval

        for i in range(attempts):
            if self.is_running():
                log.info("Ollama is ready after %d/%d polls", i + 1, attempts)
                return True
            if on_progress:
                on_progress(i + 1, attempts)
            time.sleep(interval)

        log.warning(
            "Ollama did not become ready after %d polls (%.1fs total)",
            attempts,
            attempts * interval,
        )
        return False

    def ensure_running(
        self,
        *,
        on_progress: Callable[[str], None] | None = None,
    ) -> str:
        """High-level entry point: ensure Ollama is running and ready.

        Thread-safe — uses an internal lock to serialise concurrent calls.

        Returns one of:
          "already_running"  — was reachable without any action.
          "auto_started"     — was started and became ready.
          "started_unconfirmed" — binary launched but did not respond
                                  in time (non-fatal — continue anyway).
          "binary_not_found" — ollama binary is not installed.
          "launch_failed"    — binary found but failed to launch.

        This method never raises. Callers should inspect the return
        value and decide how to proceed. The application can remain
        usable in all states except "binary_not_found".
        """
        with self._lock:
            if self.is_running():
                if on_progress:
                    on_progress("Ollama is already running")
                return "already_running"

            if on_progress:
                on_progress("Ollama not reachable — attempting auto-start")

            started = self.start()
            if not started:
                return "binary_not_found"

            def _on_progress(i: int, n: int) -> None:
                if on_progress:
                    on_progress(f"Waiting for Ollama ({i}/{n})…")

            ready = self.wait_until_ready(on_progress=_on_progress)

            if ready:
                if on_progress:
                    on_progress("Ollama is ready")
                return "auto_started"

            log.warning("Ollama process launched but not responding — continuing")
            return "started_unconfirmed"
