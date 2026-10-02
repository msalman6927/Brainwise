"""POST /chat — the SSE conversational endpoint (AGENTS.md §9)."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.core.deps import CurrentUser, DbSession
from backend.schemas.chat import ChatRequest
from backend.services import chat as chat_service

router = APIRouter()

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.post("")
async def chat(body: ChatRequest, db: DbSession, user: CurrentUser) -> StreamingResponse:
    dispatch = await chat_service.prepare(db, user.id, body)
    return StreamingResponse(
        chat_service.chat_events(dispatch, user.id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
