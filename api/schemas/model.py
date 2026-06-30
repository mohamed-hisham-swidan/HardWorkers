"""Model registry schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ModelConfigBase(BaseModel):
    name: str
    provider: str = "ollama"
    category: str = "general"
    description: str = ""
    system_prompt: str = ""
    base_model: str = ""
    api_url: str = ""
    supports_vision: bool = False
    memory_mode: str = "shared"


class CreateModelRequest(ModelConfigBase):
    api_key: str = ""
    api_password: str = ""


class ModelConfigResponse(ModelConfigBase):
    id: int
    created_at: str = ""
    updated_at: str = ""

    model_config = ConfigDict(from_attributes=True)


class ModelListItem(BaseModel):
    name: str
    provider: str
    category: str
    is_available: bool = True


class PullModelRequest(BaseModel):
    name: str


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str
    latency_ms: float = 0.0
