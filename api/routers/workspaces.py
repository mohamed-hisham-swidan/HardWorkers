"""Workspace CRUD endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_db, get_workspace_service
from api.schemas.workspace import (
    CreateWorkspaceRequest,
    SwitchWorkspaceRequest,
    UpdateWorkspaceRequest,
    WorkspaceResponse,
)
from database.repositories.database_manager import DatabaseManager
from services.workspace_service import WorkspaceService

log = logging.getLogger("hard_workers.api.routers.workspaces")

router = APIRouter(prefix="/api/v1/workspaces", tags=["Workspaces"])


def _workspace_to_response(w) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=w.id,
        name=w.name,
        active_model=w.active_model or "",
        description=w.description or "",
        category=w.category or "general",
        router_mode=w.router_mode or "disabled",
        memory_profile_id=w.memory_profile_id,
        memory_profile_name=getattr(w, "memory_profile_name", "Shared"),
        created_at=str(w.created_at) if hasattr(w, "created_at") else "",
        updated_at=str(w.updated_at) if hasattr(w, "updated_at") else "",
    )


@router.get("")
async def list_workspaces(db: DatabaseManager = Depends(get_db)):
    workspaces = db.workspaces.get_all()
    items = [_workspace_to_response(w) for w in workspaces]
    return {"items": items, "total": len(items)}


@router.get("/active", response_model=WorkspaceResponse)
async def get_active_workspace(
    ws: WorkspaceService = Depends(get_workspace_service),
):
    active = ws.get_active()
    if active is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active workspace")
    return _workspace_to_response(active)


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    body: CreateWorkspaceRequest,
    db: DatabaseManager = Depends(get_db),
):
    ws = db.workspaces.create(body.name, body.active_model, body.description, body.category)
    return _workspace_to_response(ws)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(workspace_id: int, db: DatabaseManager = Depends(get_db)):
    ws = db.workspaces.get(workspace_id)
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return _workspace_to_response(ws)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: int,
    body: UpdateWorkspaceRequest,
    db: DatabaseManager = Depends(get_db),
):
    updates = body.model_dump(exclude_none=True)
    ws = db.workspaces.update(workspace_id, **updates)
    if ws is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return _workspace_to_response(ws)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(workspace_id: int, db: DatabaseManager = Depends(get_db)):
    ok = db.workspaces.delete(workspace_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")


@router.post("/switch")
async def switch_workspace(
    body: SwitchWorkspaceRequest,
    ws: WorkspaceService = Depends(get_workspace_service),
):
    ok, msg = ws.switch(body.name)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"status": "ok", "active_workspace": body.name}
