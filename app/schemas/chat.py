"""Request/response models for /chat and /chat/history."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class ChatRequest(BaseModel):
    # extra="forbid": a client cannot smuggle in fields such as "role" or "user_id".
    model_config = ConfigDict(extra="forbid")

    question: Question
    model: str | None = Field(default=None, min_length=1, max_length=100)
    temperature: float | None = Field(default=None, ge=0, le=1)
    use_rag: bool = True


class Usage(BaseModel):
    """Token counts exactly as reported by the provider; null when not reported."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class Source(BaseModel):
    doc_id: str
    title: str
    chunk_index: int
    score: float


class ChatResponse(BaseModel):
    id: str
    answer: str
    provider: str
    model: str
    cached: bool
    usage: Usage
    latency_ms: int
    retries: int = 0
    fallback_used: bool = False
    sources: list[Source] = []


class HistoryItem(BaseModel):
    id: str
    user_id: str
    question: str | None
    answer: str | None
    provider: str | None
    model: str | None
    cached: bool
    status: str
    error_code: str | None
    usage: Usage
    latency_ms: int
    retries: int
    fallback_used: bool
    sources: list[Source] = []
    created_at: datetime
