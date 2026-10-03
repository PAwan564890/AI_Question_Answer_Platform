"""Chat routes: ask a question, read history."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import ContainerDep, CurrentUser, require_role
from app.core.errors import PermissionDeniedError
from app.models import ChatRecord, Role, User
from app.schemas.chat import ChatRequest, ChatResponse, HistoryItem, Usage

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse, summary="Ask a question (ADMIN, USER)")
async def chat(
    payload: ChatRequest,
    container: ContainerDep,
    user: Annotated[User, Depends(require_role(Role.ADMIN, Role.USER))],
) -> ChatResponse:
    return await container.chat_service.ask(user, payload)


def _to_item(record: ChatRecord) -> HistoryItem:
    return HistoryItem(
        id=record.id,
        user_id=record.user_id,
        question=record.question,
        answer=record.answer,
        provider=record.provider,
        model=record.model,
        cached=record.cached,
        status=record.status,
        error_code=record.error_code,
        usage=Usage(
            prompt_tokens=record.prompt_tokens,
            completion_tokens=record.completion_tokens,
            total_tokens=record.total_tokens,
        ),
        latency_ms=record.latency_ms,
        retries=record.retries,
        fallback_used=record.fallback_used,
        created_at=record.created_at,
    )


@router.get("/history", response_model=list[HistoryItem], summary="Chat history, newest first")
async def history(
    container: ContainerDep,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
    user_id: Annotated[
        str | None, Query(max_length=64, description="ADMIN only: another user's id, or 'all'.")
    ] = None,
) -> list[HistoryItem]:
    # Policy: every role may read its own history; only ADMIN may read others'.
    target: str | None = user.id
    if user_id is not None and user_id != user.id:
        if user.role is not Role.ADMIN:
            raise PermissionDeniedError()
        target = None if user_id == "all" else user_id
    records = await container.chats.list(target, limit, offset)
    return [_to_item(r) for r in records]
