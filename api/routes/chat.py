import base64
import io
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from PIL import Image as PILImage
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api.dependencies import get_ollama
from api.middleware.auth import get_current_user
from models.chat import ChatMessage, ChatSession
from models.user import User
from services.chat.agent import FitAIAgent
from services.groq.client import GroqClient as OllamaClient
from utils.database import AsyncSessionLocal, get_session
from utils.logger import get_logger

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = get_logger("fitai.routes.chat")

_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_ALLOWED_MIME = {"image/jpeg", "image/png"}
_CONTEXT_MESSAGES = 20


# ── Request schemas ───────────────────────────────────────────────────────────

class MessageRequest(BaseModel):
    content: str


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _get_chat_session(
    session_id: int,
    user_id: int,
    db: AsyncSession,
) -> ChatSession:
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .where(ChatSession.user_id == user_id)
    )
    cs = result.scalars().first()
    if cs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )
    return cs


async def _fetch_context_messages(session_id: int, db: AsyncSession) -> list:
    """Return the last N messages in chronological order (oldest first)."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.timestamp.desc())
        .limit(_CONTEXT_MESSAGES)
    )
    msgs = list(reversed(result.scalars().all()))
    return [{"role": m.role, "content": m.content} for m in msgs]


async def _validate_image(file: UploadFile) -> bytes:
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only JPEG and PNG images are accepted (got {file.content_type})",
        )
    data = await file.read()
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image must be smaller than 10 MB",
        )
    try:
        PILImage.open(io.BytesIO(data)).verify()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is not a valid image",
        ) from exc
    return data


async def _save_assistant_message(session_id: int, content: str) -> None:
    """Persist the assistant's full response in a fresh DB session after streaming."""
    try:
        async with AsyncSessionLocal() as db:
            db.add(ChatMessage(session_id=session_id, role="assistant", content=content))
            result = await db.execute(select(ChatSession).where(ChatSession.id == session_id))
            cs = result.scalars().first()
            if cs:
                cs.last_message_at = datetime.utcnow()
                db.add(cs)
            await db.commit()
    except Exception as exc:
        logger.error(f"Failed to save assistant message for session {session_id}: {exc}")


def _make_event_generator(agent: FitAIAgent, final_messages: list, image_b64: Optional[str], session_id: int):
    """Return an async generator that streams SSE events and saves the assistant message."""

    async def generator():
        full_response = ""
        async for sse_chunk in agent.stream_response(final_messages, image_b64):
            # Intercept the done event to strip _r (internal) before forwarding
            try:
                if '"done": true' in sse_chunk or '"done":true' in sse_chunk:
                    data = json.loads(sse_chunk[6:].strip())   # strip "data: "
                    if data.get("done"):
                        full_response = data.pop("_r", "")
                        yield f"data: {json.dumps(data)}\n\n"
                        continue
            except Exception:
                pass
            yield sse_chunk

        # Save assistant message after stream is complete
        await _save_assistant_message(session_id, full_response)

    return generator()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/session", status_code=status.HTTP_201_CREATED)
async def create_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Create a new chat session."""
    cs = ChatSession(user_id=current_user.id)
    db.add(cs)
    await db.flush()
    await db.refresh(cs)
    return {"session_id": cs.id, "created_at": cs.created_at.isoformat()}


@router.get("/sessions")
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return all chat sessions for the current user with a last-message preview."""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.last_message_at.desc())
    )
    sessions = result.scalars().all()

    out = []
    for cs in sessions:
        # Grab the last message for preview
        r_last = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == cs.id)
            .order_by(ChatMessage.timestamp.desc())
            .limit(1)
        )
        last_msg = r_last.scalars().first()
        preview = (last_msg.content[:100] + "…") if last_msg and len(last_msg.content) > 100 else (last_msg.content if last_msg else "")

        out.append({
            "session_id": cs.id,
            "created_at": cs.created_at.isoformat(),
            "last_message_at": cs.last_message_at.isoformat(),
            "preview": preview,
        })

    return {"sessions": out, "count": len(out)}


@router.get("/session/{session_id}/history")
async def session_history(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return all messages in a session ordered by timestamp."""
    await _get_chat_session(session_id, current_user.id, db)

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.timestamp)
    )
    msgs = result.scalars().all()

    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "has_image": m.has_image,
            "timestamp": m.timestamp.isoformat(),
        }
        for m in msgs
    ]


@router.post("/session/{session_id}/message")
async def send_message(
    session_id: int,
    req: MessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    ollama: OllamaClient = Depends(get_ollama),
):
    """
    Send a text message and receive a streaming SSE response.

    Each event: data: {"token": "...", "done": false}
    Final event: data: {"token": "", "done": true, "action": null|{...}}
    """
    await _get_chat_session(session_id, current_user.id, db)

    # Save the user message now (while the session is active)
    user_msg = ChatMessage(session_id=session_id, role="user", content=req.content)
    db.add(user_msg)
    await db.flush()

    # Fetch context messages (include the one we just saved)
    messages = await _fetch_context_messages(session_id, db)

    # Build agent context and system prompt before returning StreamingResponse
    agent = FitAIAgent(current_user, ollama)
    context = await agent.build_context(db)
    system_prompt = agent.build_system_prompt(context)
    final_messages = [{"role": "system", "content": system_prompt}] + messages

    return StreamingResponse(
        _make_event_generator(agent, final_messages, None, session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/session/{session_id}/message/image")
async def send_image_message(
    session_id: int,
    file: UploadFile = File(...),
    content: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    ollama: OllamaClient = Depends(get_ollama),
):
    """
    Send an image (+ optional text) and receive a streaming SSE response.
    The AI analyses the food photo and can offer to log it.
    """
    await _get_chat_session(session_id, current_user.id, db)

    image_data = await _validate_image(file)
    image_b64 = base64.b64encode(image_data).decode("utf-8")

    user_text = content or "What food is this?"
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=user_text,
        has_image=True,
    )
    db.add(user_msg)
    await db.flush()

    messages = await _fetch_context_messages(session_id, db)

    agent = FitAIAgent(current_user, ollama)
    context = await agent.build_context(db)
    system_prompt = agent.build_system_prompt(context)
    final_messages = [{"role": "system", "content": system_prompt}] + messages

    return StreamingResponse(
        _make_event_generator(agent, final_messages, image_b64, session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/session/{session_id}", status_code=status.HTTP_200_OK)
async def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Delete a chat session and all its messages."""
    cs = await _get_chat_session(session_id, current_user.id, db)

    # Delete messages first (no cascade defined at model level)
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id)
    )
    for msg in result.scalars().all():
        await db.delete(msg)

    await db.delete(cs)
    await db.flush()

    return {"deleted": True, "session_id": session_id}
