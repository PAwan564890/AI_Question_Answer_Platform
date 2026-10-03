"""Knowledge-base (RAG) routes.

ADMIN manages documents. Every authenticated role, including READ_ONLY, may
list documents and run a retrieval-only search: that reads permitted data and
costs no LLM tokens.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import ContainerDep, CurrentUser, require_role
from app.core.errors import ServiceUnavailableError
from app.models import Role, User
from app.schemas.documents import (
    DocumentCreate,
    DocumentOut,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from app.services.rag.embeddings import EmbeddingError

router = APIRouter(prefix="/documents", tags=["knowledge base"])
AdminUser = Annotated[User, Depends(require_role(Role.ADMIN))]


@router.post("", response_model=DocumentOut, status_code=201, summary="Ingest a document (ADMIN)")
async def ingest(payload: DocumentCreate, container: ContainerDep, admin: AdminUser) -> DocumentOut:
    info = await container.knowledge_base.ingest(
        title=payload.title, text=payload.text, source=payload.source, actor=admin
    )
    return DocumentOut.model_validate(info, from_attributes=True)


@router.get("", response_model=list[DocumentOut], summary="List documents (any role)")
async def list_documents(
    container: ContainerDep,
    _: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
) -> list[DocumentOut]:
    documents = await container.knowledge_base.list(limit, offset)
    return [DocumentOut.model_validate(d, from_attributes=True) for d in documents]


@router.post("/search", response_model=SearchResponse, summary="Vector search only (any role)")
async def search(payload: SearchRequest, container: ContainerDep, _: CurrentUser) -> SearchResponse:
    try:
        chunks = await container.knowledge_base.search(payload.query, payload.top_k)
    except EmbeddingError as exc:
        raise ServiceUnavailableError(
            "The embedding service is unavailable.", code="EMBEDDING_UNAVAILABLE"
        ) from exc
    return SearchResponse(
        results=[SearchHit.model_validate(c, from_attributes=True) for c in chunks]
    )


@router.delete("/{doc_id}", status_code=204, summary="Delete a document (ADMIN)")
async def delete(doc_id: str, container: ContainerDep, _: AdminUser) -> Response:
    await container.knowledge_base.delete(doc_id)
    return Response(status_code=204)
