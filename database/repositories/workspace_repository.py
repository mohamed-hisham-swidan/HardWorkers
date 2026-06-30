from __future__ import annotations

import time

from database.connection import ConnectionManager
from models.domain import Workspace
from models.enums import ModelCategory, RouterMode
from utils.helpers import parse_enum
from utils.logging_setup import get_logger

log = get_logger("database.repositories.workspace_repository")


# ── Workspaces ────────────────────────────────────────────────────────────────


class WorkspaceRepository:
    """CRUD for workspace configurations."""

    def __init__(self, cm: ConnectionManager) -> None:
        self._cm = cm

    def get_all(self) -> list[Workspace]:
        with self._cm.transaction() as conn:
            rows = conn.execute(
                "SELECT w.id, w.name, w.active_model, w.memory_profile_id, "
                "COALESCE(mp.name, 'Shared') AS memory_profile_name, "
                "w.router_mode, w.category, w.description, w.created_at, w.updated_at "
                "FROM workspaces w "
                "LEFT JOIN memory_profiles mp ON w.memory_profile_id = mp.id "
                "ORDER BY w.id"
            ).fetchall()
        return [self._row_to_workspace(r) for r in rows]

    def get_by_name(self, name: str) -> Workspace | None:
        with self._cm.transaction() as conn:
            row = conn.execute(
                "SELECT w.id, w.name, w.active_model, w.memory_profile_id, "
                "COALESCE(mp.name, 'Shared') AS memory_profile_name, "
                "w.router_mode, w.category, w.description, w.created_at, w.updated_at "
                "FROM workspaces w "
                "LEFT JOIN memory_profiles mp ON w.memory_profile_id = mp.id "
                "WHERE w.name = ?",
                (name,),
            ).fetchone()
        return self._row_to_workspace(row) if row else None

    def save(self, ws: Workspace) -> int:
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._cm.transaction() as conn:
            cur = conn.execute(
                "INSERT INTO workspaces "
                "(name, active_model, memory_profile_id, router_mode, "
                "category, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ws.name,
                    ws.active_model,
                    ws.memory_profile_id,
                    str(ws.router_mode),
                    str(ws.category),
                    ws.description,
                    ts,
                    ts,
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def update(self, ws: Workspace) -> bool:
        if ws.id is None:
            return False
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with self._cm.transaction() as conn:
            cur = conn.execute(
                "UPDATE workspaces SET active_model=?, memory_profile_id=?, "
                "router_mode=?, category=?, description=?, updated_at=? "
                "WHERE id=?",
                (
                    ws.active_model,
                    ws.memory_profile_id,
                    str(ws.router_mode),
                    str(ws.category),
                    ws.description,
                    ts,
                    ws.id,
                ),
            )
        return cur.rowcount > 0

    def delete(self, ws_id: int) -> bool:
        with self._cm.transaction() as conn:
            cur = conn.execute("DELETE FROM workspaces WHERE id=?", (ws_id,))
        return cur.rowcount > 0

    @staticmethod
    def _row_to_workspace(row) -> Workspace:
        cat_val = row["category"]
        cat = parse_enum(ModelCategory, cat_val, ModelCategory.GENERAL)
        rm_val = row["router_mode"]
        rm = parse_enum(RouterMode, rm_val, RouterMode.DISABLED)
        return Workspace(
            id=row["id"],
            name=row["name"],
            active_model=row["active_model"] or "",
            memory_profile_id=row["memory_profile_id"],
            memory_profile_name=row["memory_profile_name"] or "Shared",
            router_mode=rm,
            category=cat,
            description=row["description"] or "",
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )
