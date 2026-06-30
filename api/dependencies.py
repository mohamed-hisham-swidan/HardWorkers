"""FastAPI dependency injection — reuses existing service layer."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.container import Container
from database.repositories.database_manager import DatabaseManager
from memory.memory_service import MemoryService
from services.ai.model_manager import ModelManager
from services.ai.model_router import ModelRouterService
from services.ai.ollama_client import OllamaClient
from services.chat_service import ChatService
from services.workspace_service import WorkspaceService
from settings.service import SettingsService
from utils.crypto import verify_token

_security = HTTPBearer(auto_error=False)


def _resolve(request: Request, name: str) -> Any:
    container: Container | None = getattr(request.app.state, "container", None)
    if container is None:
        raise RuntimeError("Container not initialised — did the lifespan hook run?")
    return container.resolve(name)


def get_db(request: Request) -> DatabaseManager:
    return _resolve(request, "db")


def get_memory(request: Request) -> MemoryService:
    return _resolve(request, "memory")


def get_model_manager(request: Request) -> ModelManager:
    return _resolve(request, "model_manager")


def get_router_service(request: Request) -> ModelRouterService:
    return _resolve(request, "model_router")


def get_ollama(request: Request) -> OllamaClient:
    return _resolve(request, "ollama")


def get_chat_service(request: Request) -> ChatService:
    return _resolve(request, "chats")


def get_workspace_service(request: Request) -> WorkspaceService:
    return _resolve(request, "workspaces")


def get_settings_service(request: Request) -> SettingsService:
    return _resolve(request, "settings")


def get_active_workspace_id(
    ws: WorkspaceService = Depends(get_workspace_service),
) -> int:
    active = ws.get_active()
    if active is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active workspace")
    return active.id


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
    request: Request | None = None,
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    token = credentials.credentials
    config = _resolve(request, "config") if request else None
    secret = getattr(config, "api", type("obj", (object,), {"jwt_secret": ""})).jwt_secret if config else ""
    payload = verify_token(token, secret)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return {"username": payload.get("sub", "unknown"), "role": "admin"}
