"""Chat session CRUD endpoints."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import (
    get_active_workspace_id,
    get_chat_service,
    get_db,
    get_model_manager,
    get_ollama,
    get_workspace_service,
)
from api.schemas.chat import (
    ChatHistoryParams,
    ChatSessionCreate,
    ChatSessionPin,
    ChatSessionRename,
    ChatSessionResponse,
    MessageResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from database.repositories.database_manager import DatabaseManager
from services.ai.model_manager import ModelManager
from services.ai.ollama_client import OllamaClient
from services.chat_service import ChatService
from services.workspace_service import WorkspaceService

log = logging.getLogger("hard_workers.api.routers.chats")

router = APIRouter(prefix="/api/v1/chats", tags=["Chats"])


def _session_to_response(session) -> ChatSessionResponse:
    return ChatSessionResponse(
        id=session.id,
        workspace_id=session.workspace_id,
        name=session.name,
        pinned=session.pinned,
        message_count=getattr(session, "message_count", 0),
        created_at=str(session.created_at) if hasattr(session, "created_at") else "",
        updated_at=str(session.updated_at) if hasattr(session, "updated_at") else "",
    )


@router.get("")
async def list_sessions(
    workspace_id: int = Depends(get_active_workspace_id),
    chat: ChatService = Depends(get_chat_service),
):
    sessions = chat.get_chats(workspace_id)
    items = [_session_to_response(s) for s in sessions]
    return {"items": items, "total": len(items), "offset": 0, "limit": len(items) or 1}


@router.post("", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: ChatSessionCreate,
    chat: ChatService = Depends(get_chat_service),
):
    session_id = chat.create_chat(body.workspace_id, name=body.name)
    session = chat.get_chat(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create session")
    return _session_to_response(session)


@router.get("/{session_id}", response_model=ChatSessionResponse)
async def get_session(
    session_id: int,
    chat: ChatService = Depends(get_chat_service),
):
    session = chat.get_chat(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return _session_to_response(session)


@router.patch("/{session_id}/rename", response_model=ChatSessionResponse)
async def rename_session(
    session_id: int,
    body: ChatSessionRename,
    chat: ChatService = Depends(get_chat_service),
):
    ok = chat.rename_chat(session_id, body.name)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session = chat.get_chat(session_id)
    return _session_to_response(session)


@router.patch("/{session_id}/pin", response_model=ChatSessionResponse)
async def pin_session(
    session_id: int,
    body: ChatSessionPin,
    chat: ChatService = Depends(get_chat_service),
):
    ok = chat.pin_chat(session_id, body.pinned)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session = chat.get_chat(session_id)
    return _session_to_response(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    ws=Depends(get_workspace_service),
    chat: ChatService = Depends(get_chat_service),
):
    workspace_id = ws.get_active().id
    new_id = chat.delete_chat(session_id, workspace_id)
    if new_id is None and session_id != new_id:
        pass  # Success: either deleted or reassigned
    return None


@router.get("/{session_id}/messages")
async def list_messages(
    session_id: int,
    params: ChatHistoryParams = Depends(),
    db: DatabaseManager = Depends(get_db),
):
    messages = db.chat.get_messages(session_id, limit=params.limit, offset=params.offset)
    total = db.chat.get_message_count(session_id)
    items = [
        MessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            tokens=getattr(m, "tokens", 0),
            timestamp=str(m.created_at) if hasattr(m, "created_at") else "",
        )
        for m in messages
    ]
    return {"items": items, "total": total, "offset": params.offset, "limit": params.limit}


@router.delete("/{session_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
async def clear_messages(session_id: int, db: DatabaseManager = Depends(get_db)):
    db.chat.clear_for_chat(session_id)


@router.post("/{session_id}/send", response_model=SendMessageResponse)
async def send_message(
    session_id: int,
    body: SendMessageRequest,
    db: DatabaseManager = Depends(get_db),
    ollama: OllamaClient = Depends(get_ollama),
    mm: ModelManager = Depends(get_model_manager),
    ws: WorkspaceService = Depends(get_workspace_service),
):
    model_id = body.model_id or mm.get_active() or ""
    if not model_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No model specified")

    # Save user message
    db.chat.save_for_chat(session_id, "user", body.message)

    # Build prompt from chat history + system prompt
    system_prompt = (
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
    try:
        active_ws = ws.get_active()
        if active_ws and active_ws.description:
            system_prompt = active_ws.description
    except Exception as exc:
        log.warning("Failed to get active workspace: %s", exc)

    history = db.chat.get_by_token_budget(session_id, 3072)
    history_text = "\n".join(f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}" for m in history)
    prompt = f"{system_prompt}\n\nConversation so far:\n{history_text}\n\nUser: {body.message}\nAssistant:"

    # Generate response
    t0 = time.monotonic()
    response_text = ollama.generate(model_id, prompt)
    elapsed_ms = (time.monotonic() - t0) * 1000

    if not response_text:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Model returned empty response")

    # Save assistant message
    asst_msg_id = db.chat.save_for_chat(session_id, "assistant", response_text)

    return SendMessageResponse(
        message_id=asst_msg_id,
        content=response_text,
        role="assistant",
        tokens=0,
        elapsed_ms=round(elapsed_ms, 1),
    )
