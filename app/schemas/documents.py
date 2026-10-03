"""Request/response models for the knowledge base (RAG) endpoints."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Query = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    text: Body  # upper bound enforced in the service from RAG_MAX_DOCUMENT_CHARS
    source: str | None = Field(default=None, max_length=500)


class DocumentOut(BaseModel):
    doc_id: str
    title: str
    source: str | None
    chunk_count: int
    created_by: str
    created_at: datetime


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Query
    top_k: int = Field(default=4, ge=1, le=10)


class SearchHit(BaseModel):
    doc_id: str
    title: str
    chunk_index: int
    text: str
    score: float


class SearchResponse(BaseModel):
    results: list[SearchHit]
