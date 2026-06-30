"""Workspace service — HardWorkres platform.

A workspace bundles: active model + memory profile + router settings.
Switching a workspace atomically reconfigures all three.
"""

from __future__ import annotations

import threading

from database.repositories import DatabaseManager
from memory.memory_service import MemoryService
from models.domain import Workspace
from models.enums import MemoryMode, RouterMode
from services.ai.model_manager import ModelManager
from services.ai.model_router import ModelRouterService
from utils.logging_setup import get_logger

log = get_logger("services.workspace_service")


class WorkspaceService:
    def __init__(
        self,
        db: DatabaseManager,
        model_manager: ModelManager,
        router: ModelRouterService,
        memory: MemoryService | None = None,
    ) -> None:
        self._db = db
        self._mm = model_manager
        self._router = router
        self._memory = memory
        self._lock = threading.Lock()
        self._active: Workspace | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def get_all(self) -> list[Workspace]:
        return self._db.workspaces.get_all()

    def get_active(self) -> Workspace | None:
        with self._lock:
            return self._active

    def switch(self, workspace_name: str) -> tuple[bool, str]:
        """Switch to the named workspace.

        Applies model, router, and category settings atomically.
        Returns (success, message).
        """
        ws = self._db.workspaces.get_by_name(workspace_name)
        if ws is None:
            return False, f"Workspace '{workspace_name}' not found"

        with self._lock:
            self._active = ws

        # Apply model if it's set and available
        if ws.active_model:
            available = self._mm.get_available()
            if ws.active_model in available:
                self._mm.set_active(ws.active_model)
                log.info("Workspace '%s' → model %r", workspace_name, ws.active_model)
            else:
                log.warning("Workspace model %r not available", ws.active_model)

        # Apply router settings
        self._router.set_mode(ws.router_mode)
        self._router.set_workspace_category(str(ws.category))
        self._apply_memory(ws)

        log.info("Switched to workspace '%s' (router=%s, category=%s)", workspace_name, ws.router_mode, ws.category)
        return True, f"Switched to workspace '{workspace_name}'"

    def save_workspace(self, ws: Workspace) -> tuple[bool, str]:
        """Persist a new or updated workspace."""
        try:
            existing = self._db.workspaces.get_by_name(ws.name)
            if existing:
                ws.id = existing.id
                self._db.workspaces.update(ws)
                return True, f"Workspace '{ws.name}' updated"
            self._db.workspaces.save(ws)
            return True, f"Workspace '{ws.name}' created"
        except Exception as exc:
            log.error("Workspace save failed: %s", exc)
            return False, str(exc)

    def delete_workspace(self, ws_id: int, name: str) -> tuple[bool, str]:
        """Delete a workspace (protected names cannot be deleted)."""
        protected = {"Default"}
        if name in protected:
            return False, f"Workspace '{name}' is protected and cannot be deleted"
        try:
            deleted = self._db.workspaces.delete(ws_id)
            return (True, f"Workspace '{name}' deleted") if deleted else (False, "Not found")
        except Exception as exc:
            return False, str(exc)

    def update_active_model(self, model_name: str) -> None:
        """Persist the current model name to the active workspace."""
        with self._lock:
            ws = self._active
        if ws and ws.id is not None:
            ws.active_model = model_name
            self._db.workspaces.update(ws)

    def update_active_router(self, mode: RouterMode) -> None:
        with self._lock:
            ws = self._active
        self._router.set_mode(mode)
        if ws and ws.id is not None:
            ws.router_mode = mode
            self._db.workspaces.update(ws)

    def update_active_memory_profile(self, profile_id: int | None) -> None:
        refreshed = None
        with self._lock:
            ws = self._active
            if ws and ws.id is not None:
                ws.memory_profile_id = profile_id
                self._db.workspaces.update(ws)
                refreshed = self._db.workspaces.get_by_name(ws.name)
                if refreshed:
                    self._active = refreshed
        if refreshed:
            self._apply_memory(refreshed)

    def _apply_memory(self, ws: Workspace) -> None:
        if not self._memory:
            return

        profile = self._db.mem_profiles.get_by_id(ws.memory_profile_id) if ws.memory_profile_id is not None else None
        if profile and profile.name == "No Memory":
            mode = MemoryMode.NONE
        elif profile and profile.name != "Shared":
            mode = MemoryMode.DEDICATED
        else:
            mode = MemoryMode.SHARED

        self._memory.set_mode(mode, profile)
        # Index rebuild deferred — loads sentence-transformers (~5s) and is not
        # required during startup. Facts are indexed individually on add_fact().
