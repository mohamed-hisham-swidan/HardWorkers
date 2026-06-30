"""Workspace schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WorkspaceBase(BaseModel):
    name: str
    active_model: str = ""
    description: str = ""
    category: str = "general"
    router_mode: str = "disabled"
    memory_profile_id: int | None = None


class CreateWorkspaceRequest(WorkspaceBase):
    pass


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    active_model: str | None = None
    description: str | None = None
    category: str | None = None
    router_mode: str | None = None


class WorkspaceResponse(WorkspaceBase):
    id: int
    memory_profile_name: str = "Shared"
    created_at: str = ""
    updated_at: str = ""

    model_config = ConfigDict(from_attributes=True)


class SwitchWorkspaceRequest(BaseModel):
    name: str
