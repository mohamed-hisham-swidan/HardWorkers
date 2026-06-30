"""FastAPI application factory."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.middleware import setup_middleware
from api.routers import auth, chats, health, memory, models, settings, stream, workspaces
from config.settings import AppConfig
from core.container import Container

log = logging.getLogger("hard_workers.api")

_TASKS: dict[str, dict] = {}


def get_task_store() -> dict[str, dict]:
    return _TASKS


def create_app(config: AppConfig | None = None) -> FastAPI:
    """Create and return a fully configured FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log.info("Starting HardWorkers API server...")
        container = Container()
        container.init(config)
        app.state.container = container
        app.state.config = config or container.config
        app.state.task_store = _TASKS
        yield
        log.info("Shutting down HardWorkers API server...")
        try:
            container.close()
        except Exception:
            log.debug("Container close ignored (already closed)")

    app = FastAPI(
        title="HardWorkers API",
        version="1.0.0",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        lifespan=lifespan,
    )

    # Middleware
    api_config = config.api if config else None
    origins = api_config.cors_origins if api_config else ["http://localhost:5173"]
    setup_middleware(app, cors_origins=origins)

    # Exception handlers — consistent error envelope, never leak internals
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=404,
            content={"error": "Not found", "code": "NOT_FOUND"},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error": "Validation error",
                "code": "VALIDATION_ERROR",
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        log.exception("Unhandled exception processing %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "code": "INTERNAL_ERROR",
            },
        )

    # Routers
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(chats.router)
    app.include_router(models.router)
    app.include_router(memory.router)
    app.include_router(workspaces.router)
    app.include_router(settings.router)
    app.include_router(stream.router)

    # Root info
    @app.get("/")
    async def root():
        return {"name": "HardWorkers API", "version": "1.0.0", "docs": "/api/v1/docs"}

    # Static files mount for future React frontend
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

    # Task status endpoint
    @app.get("/api/v1/tasks/{task_id}")
    async def get_task_status(task_id: str):
        store = _TASKS
        if task_id not in store:
            return JSONResponse(
                status_code=404,
                content={"error": "Task not found", "code": "TASK_NOT_FOUND", "details": {"task_id": task_id}},
            )
        return store[task_id]

    return app


def create_background_task(status: str = "pending", total: int = 100) -> str:
    """Register a background task and return its ID."""
    task_id = uuid.uuid4().hex[:12]
    _TASKS[task_id] = {"status": status, "progress": 0, "total": total}
    return task_id


def update_background_task(task_id: str, **kwargs) -> None:
    if task_id in _TASKS:
        _TASKS[task_id].update(kwargs)
