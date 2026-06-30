"""Health check and system diagnostics."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends

from api.dependencies import get_db, get_model_manager
from database.repositories.database_manager import DatabaseManager
from services.ai.model_manager import ModelManager

log = logging.getLogger("hard_workers.api.routers.health")

router = APIRouter(prefix="/api/v1", tags=["Health"])


@router.get("/health")
async def health_check(
    db: DatabaseManager = Depends(get_db),
    mm: ModelManager = Depends(get_model_manager),
):
    t0 = time.monotonic()
    db_ok = db.integrity_ok()
    models = mm.get_available()
    return {
        "status": "ok",
        "timestamp": time.time(),
        "uptime_ms": 0,
        "checks": {
            "database": "ok" if db_ok else "degraded",
            "models": len(models),
        },
        "version": "3.3.0",
        "response_time_ms": round((time.monotonic() - t0) * 1000, 1),
    }
