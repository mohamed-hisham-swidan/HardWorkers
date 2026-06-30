"""Chat session and message schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MessageBase(BaseModel):
    role: str
    content: str
    tokens: int = 0


class MessageCreate(MessageBase):
    pass


class MessageResponse(MessageBase):
    id: int
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatSessionBase(BaseModel):
    name: str
    pinned: bool = False


class ChatSessionCreate(ChatSessionBase):
    workspace_id: int


class ChatSessionResponse(ChatSessionBase):
    id: int
    workspace_id: int
    message_count: int = 0
    created_at: str = ""
    updated_at: str = ""

    model_config = ConfigDict(from_attributes=True)


class ChatSessionRename(BaseModel):
    name: str


class ChatSessionPin(BaseModel):
    pinned: bool


class SendMessageRequest(BaseModel):
    message: str
    model_id: str | None = None


class SendMessageResponse(BaseModel):
    message_id: int
    content: str
    role: str
    tokens: int = 0
    elapsed_ms: float = 0.0


class ChatHistoryParams(BaseModel):
    offset: int = 0
    limit: int = 20
