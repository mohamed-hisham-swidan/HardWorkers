"""Memory fact and summary schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FactBase(BaseModel):
    key: str
    value: str
    importance: int = 5


class AddFactRequest(FactBase):
    pass


class FactResponse(FactBase):
    id: int
    created_at: str = ""

    model_config = ConfigDict(from_attributes=True)


class SummaryBase(BaseModel):
    summary: str
    source: str = "api"


class SummaryResponse(SummaryBase):
    id: int
    chat_id: int
    created_at: str = ""

    model_config = ConfigDict(from_attributes=True)


class SearchMemoryRequest(BaseModel):
    query: str
    limit: int = 5
    threshold: float = 0.0


class SearchMemoryResult(BaseModel):
    key: str
    value: str
    score: float


class ChatFactsResponse(BaseModel):
    chat_id: int
    facts: list[FactResponse]
