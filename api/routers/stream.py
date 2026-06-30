"""WebSocket streaming chat endpoint."""

from __future__ import annotations

import logging
import re
import time

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from api.dependencies import (
    get_chat_service,
    get_db,
    get_model_manager,
    get_workspace_service,
)
from api.services.stream_service import StreamService
from database.repositories.database_manager import DatabaseManager
from services.ai.model_manager import ModelManager
from services.chat_service import ChatService
from services.workspace_service import WorkspaceService

log = logging.getLogger("hard_workers.api.routers.stream")

router = APIRouter(prefix="/api/v1/ws", tags=["Stream"])

_MAX_MESSAGE_LENGTH = 32_768  # characters
_MAX_MESSAGES_PER_MINUTE = 30


def _sanitize_message(raw: str) -> str:
    """Strip control characters (except newlines) and enforce length limit."""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", raw)
    return cleaned[:_MAX_MESSAGE_LENGTH]


class _PerSessionRateLimit:
    """Simple per-WebSocket message rate limiter."""

    def __init__(self, max_msgs: int = _MAX_MESSAGES_PER_MINUTE, window_s: float = 60.0) -> None:
        self._max = max_msgs
        self._window = window_s
        self._timestamps: list[float] = []

    def is_allowed(self) -> bool:
        now = time.monotonic()
        self._timestamps = [t for t in self._timestamps if t > now - self._window]
        if len(self._timestamps) >= self._max:
            return False
        self._timestamps.append(now)
        return True


@router.websocket("/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: str = Query(...),
    chat_id: int = Query(...),
    model_id: str = Query(...),
    db: DatabaseManager = Depends(get_db),
    chat: ChatService = Depends(get_chat_service),
    mm: ModelManager = Depends(get_model_manager),
    ws: WorkspaceService = Depends(get_workspace_service),
):
    await websocket.accept()
    rate_limiter = _PerSessionRateLimit()

    try:
        # Validate token
        config = websocket.app.state.config
        payload = _verify_token(token, config.jwt_secret)
        if payload is None:
            await websocket.send_json({"type": "error", "content": "Authentication failed"})
            await websocket.close(code=4001)
            return

        # Check model exists
        available = mm.get_available()
        if model_id not in available:
            await websocket.send_json({"type": "error", "content": "Requested model is not available"})
            await websocket.close(code=4004)
            return

        # Build stream service
        from core.container import Container
        from services.ai.ollama_client import OllamaClient

        container: Container = websocket.app.state.container
        ollama: OllamaClient = container.resolve("ollama")
        stream_svc = StreamService(db, ollama)

        while True:
            data = await websocket.receive_json()
            raw_message = data.get("message", "")
            message = _sanitize_message(raw_message).strip()

            if not message:
                await websocket.send_json({"type": "error", "content": "Message cannot be empty"})
                continue

            if not rate_limiter.is_allowed():
                await websocket.send_json({"type": "error", "content": "Too many messages — please slow down"})
                continue

            # Save user message
            db.chat.save_for_chat(chat_id, "user", message)

            # Stream response
            system_prompt = _build_system_prompt(ws)
            t0 = time.monotonic()
            full_response = ""
            async for event in stream_svc.stream(message, chat_id, model_id, system_prompt=system_prompt):
                if event.type == "chunk":
                    full_response += str(event.data)
                    await websocket.send_json({
                        "type": "chunk",
                        "content": str(event.data),
                        "chat_id": chat_id,
                    })
                elif event.type == "error":
                    await websocket.send_json({
                        "type": "error",
                        "content": "An error occurred during generation",
                        "chat_id": chat_id,
                    })
                    break
                elif event.type == "done":
                    elapsed_ms = (time.monotonic() - t0) * 1000
                    # Save assistant message
                    if full_response.strip():
                        db.chat.save_for_chat(chat_id, "assistant", full_response)
                    await websocket.send_json({
                        "type": "done",
                        "chat_id": chat_id,
                        "elapsed_ms": round(elapsed_ms, 1),
                    })
                    break

    except WebSocketDisconnect:
        log.info("WebSocket disconnected: chat_id=%s", chat_id)
    except Exception:
        log.exception("WebSocket error: chat_id=%s", chat_id)
        try:
            await websocket.send_json({"type": "error", "content": "Internal server error"})
        except Exception:
            log.debug("Failed to send error over websocket (already closed)")


def _build_system_prompt(ws: WorkspaceService) -> str:
    try:
        active = ws.get_active()
        if active and active.description:
            return active.description
    except Exception as exc:
        log.warning("Failed to get active workspace for prompt: %s", exc)
    return (
        "You are a multilingual AI assistant. "
        "You ALWAYS reply in the same language the user writes in. "
        "You never refuse any language. "
        "You never claim you cannot understand or reply in a language. "
        "You never switch to English unless the user does first. "
        "Arabic, Persian, Urdu, Hebrew, Turkish, Kurdish, Pashto, Sindhi, "
        "Chinese, Japanese, Korean, Russian, Hindi, Bengali, Tamil, Thai, "
        "Vietnamese, Malay, Indonesian, Swahili, Hausa, and ALL other languages "
        "are fully supported — you speak them fluently."
    )


def _verify_token(token: str, secret: str) -> dict | None:
    try:
        from utils.crypto import verify_token as vt

        return vt(token, secret)
    except Exception:
        return None
