"""Memory facts and summaries endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from api.dependencies import get_db, get_memory
from api.schemas.memory import (
    AddFactRequest,
    FactResponse,
    SearchMemoryRequest,
    SearchMemoryResult,
    SummaryResponse,
)
from database.repositories.database_manager import DatabaseManager
from memory.memory_service import MemoryService

log = logging.getLogger("hard_workers.api.routers.memory")

router = APIRouter(prefix="/api/v1/memory", tags=["Memory"])


def _fact_to_response(f) -> FactResponse:
    return FactResponse(
        id=f.id,
        key=f.key,
        value=f.value,
        importance=f.importance,
        created_at=str(f.created_at) if hasattr(f, "created_at") else "",
    )


@router.get("/facts")
async def list_facts(
    offset: int = 0,
    limit: int = 50,
    db: DatabaseManager = Depends(get_db),
):
    facts = db.memory.get_facts(limit=limit, offset=offset)
    total = db.memory.get_fact_count()
    items = [_fact_to_response(f) for f in facts]
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.post("/facts")
async def add_fact(
    body: AddFactRequest, mem: MemoryService = Depends(get_memory), db: DatabaseManager = Depends(get_db)
):
    fact = db.memory.add_fact(body.key, body.value, importance=body.importance)
    mem.on_fact_added(fact)
    return _fact_to_response(fact)


@router.delete("/facts/{fact_id}", status_code=204)
async def delete_fact(fact_id: int, db: DatabaseManager = Depends(get_db)):
    db.memory.delete_fact(fact_id)


@router.post("/facts/search")
async def search_facts(
    body: SearchMemoryRequest,
    mem: MemoryService = Depends(get_memory),
):
    results = mem.search(body.query, top_k=body.limit, threshold=body.threshold)
    items = [SearchMemoryResult(key=r.key, value=r.value, score=r.score) for r in results]
    return {"items": items}


@router.get("/summaries")
async def list_summaries(
    chat_id: int | None = None,
    limit: int = 20,
    db: DatabaseManager = Depends(get_db),
):
    summaries = db.memory.get_summaries(chat_id=chat_id, limit=limit)
    items = [
        SummaryResponse(
            id=s.id,
            chat_id=s.chat_id,
            summary=s.summary,
            source=s.source,
            created_at=str(s.created_at) if hasattr(s, "created_at") else "",
        )
        for s in summaries
    ]
    return {"items": items}


@router.get("/chat/{chat_id}/facts")
async def get_chat_facts(
    chat_id: int,
    mem: MemoryService = Depends(get_memory),
):
    facts = mem.get_facts_for_chat(chat_id)
    return {"chat_id": chat_id, "facts": [_fact_to_response(f) for f in facts]}
