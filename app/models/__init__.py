"""Plain domain objects. They know nothing about HTTP or about Qdrant."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    USER = "USER"
    READ_ONLY = "READ_ONLY"


@dataclass(slots=True)
class User:
    id: str
    username: str
    password_hash: str
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None
    password_changed_ts: float | None = None  # tokens issued before this are rejected


@dataclass(slots=True)
class RetrievedChunk:
    doc_id: str
    title: str
    chunk_index: int
    text: str
    score: float


@dataclass(slots=True)
class DocumentInfo:
    doc_id: str
    title: str
    source: str | None
    chunk_count: int
    created_by: str
    created_at: datetime


@dataclass(slots=True)
class ChatRecord:
    id: str
    user_id: str
    question: str | None
    answer: str | None
    provider: str | None
    model: str | None
    cached: bool
    status: str  # "ok" | "error"
    error_code: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_ms: int
    retries: int
    fallback_used: bool
    created_at: datetime
    sources: list[dict] = field(default_factory=list)
