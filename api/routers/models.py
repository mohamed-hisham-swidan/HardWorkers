"""Model registry and management endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_db, get_model_manager, get_router_service
from api.schemas.model import (
    CreateModelRequest,
    ModelConfigResponse,
    ModelListItem,
    TestConnectionResponse,
)
from database.repositories.database_manager import DatabaseManager
from services.ai.model_manager import ModelManager
from services.ai.model_router import ModelRouterService

log = logging.getLogger("hard_workers.api.routers.models")

router = APIRouter(prefix="/api/v1/models", tags=["Models"])


def _model_to_response(m) -> ModelConfigResponse:
    return ModelConfigResponse(
        id=m.id,
        name=m.name,
        provider=m.provider,
        category=m.category,
        description=m.description,
        system_prompt=m.system_prompt,
        base_model=m.base_model,
        api_url=m.api_url,
        supports_vision=m.supports_vision,
        memory_mode=m.memory_mode,
        created_at=str(m.created_at) if hasattr(m, "created_at") else "",
        updated_at=str(m.updated_at) if hasattr(m, "updated_at") else "",
    )


@router.get("")
async def list_models(db: DatabaseManager = Depends(get_db)):
    models = db.models.get_all()
    items = [_model_to_response(m) for m in models]
    return {"items": items, "total": len(items)}


@router.get("/available")
async def list_available(mm: ModelManager = Depends(get_model_manager)):
    names = mm.get_available()
    items = [ModelListItem(name=n, provider="ollama", category="general", is_available=True) for n in names]
    return {"items": items}


@router.post("", response_model=ModelConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_model(body: CreateModelRequest, db: DatabaseManager = Depends(get_db)):
    model = db.models.create(
        name=body.name,
        provider=body.provider,
        category=body.category,
        description=body.description,
        system_prompt=body.system_prompt,
        base_model=body.base_model,
        api_url=body.api_url,
        api_key=body.api_key or "",
        api_password=body.api_password or "",
        supports_vision=body.supports_vision,
        memory_mode=body.memory_mode,
    )
    return _model_to_response(model)


@router.get("/{model_id}", response_model=ModelConfigResponse)
async def get_model(model_id: int, db: DatabaseManager = Depends(get_db)):
    model = db.models.get(model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return _model_to_response(model)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(model_id: int, db: DatabaseManager = Depends(get_db)):
    ok = db.models.delete(model_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")


@router.post("/pull")
async def pull_model(
    model_name: str,
    mm: ModelManager = Depends(get_model_manager),
):
    ok, msg = mm.pull_model(model_name)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return {"status": "ok", "message": msg}


@router.get("/{model_id}/test", response_model=TestConnectionResponse)
async def test_connection(model_id: int, rs: ModelRouterService = Depends(get_router_service)):
    ok, msg = rs.test_model_connection(model_id)
    return TestConnectionResponse(ok=ok, message=msg)


@router.post("/default")
async def set_default_model(
    model_name: str,
    mm: ModelManager = Depends(get_model_manager),
):
    mm.set_default(model_name)
    return {"status": "ok", "default_model": model_name}
