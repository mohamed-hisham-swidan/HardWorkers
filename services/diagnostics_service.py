"""System diagnostics aggregator.

Collects health data from Ollama, the database, and the vector store
into a single DiagnosticsSnapshot without coupling the UI to each
individual service.
"""

from __future__ import annotations

import threading

from database.repositories import DatabaseManager
from models.domain import DiagnosticsSnapshot
from services.ai.model_manager import ModelManager
from services.ai.ollama_client import OllamaClient
from utils.logging_setup import get_logger
from vectorstore.faiss_store import VectorStore

log = get_logger("services.diagnostics_service")


class DiagnosticsService:
    def __init__(
        self,
        ollama: OllamaClient,
        model_manager: ModelManager,
        db: DatabaseManager,
        vs: VectorStore,
    ) -> None:
        self._ollama = ollama
        self._mm = model_manager
        self._db = db
        self._vs = vs

    def snapshot(self) -> DiagnosticsSnapshot:
        """Collect and return a complete diagnostics snapshot (blocking)."""
        snap = DiagnosticsSnapshot()

        ollama_probe = self._ollama.probe()
        snap.ollama_status = ollama_probe.get("status", "unknown")
        snap.ollama_latency_ms = ollama_probe.get("latency_ms") or 0.0
        snap.current_model = self._mm.get_active()

        db_stats = self._db.stats()
        snap.db_active_messages = db_stats["active_messages"]
        snap.db_active_tokens = db_stats["active_tokens"]
        snap.db_facts = db_stats["facts"]

        snap.vector_entries = self._vs.size

        snap.active_threads = threading.active_count()

        try:
            import psutil  # type: ignore[import]

            psutil.Process()
            snap.cpu_percent = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            snap.ram_used_mb = mem.used / 1024 / 1024
            snap.ram_total_mb = mem.total / 1024 / 1024
        except ImportError:
            log.debug("psutil not installed — CPU/RAM metrics unavailable")
        except Exception as exc:
            log.debug("Failed to collect CPU/RAM metrics: %s", exc)

        return snap

    def format_text(self, snap: DiagnosticsSnapshot) -> str:
        lines = [
            f"Ollama status : {snap.ollama_status}",
            f"Latency       : {snap.ollama_latency_ms:.0f} ms" if snap.ollama_latency_ms else "Latency       : —",
            f"Active model  : {snap.current_model}",
            "",
            f"DB messages   : {snap.db_active_messages}",
            f"DB tokens     : {snap.db_active_tokens}",
            f"Facts stored  : {snap.db_facts}",
            f"Vector entries: {snap.vector_entries}",
            f"Active threads: {snap.active_threads}",
        ]
        if snap.ram_total_mb:
            lines += [
                "",
                f"CPU           : {snap.cpu_percent:.1f}%",
                f"RAM           : {snap.ram_used_mb:.0f} / {snap.ram_total_mb:.0f} MB",
            ]
        return "\n".join(lines)
