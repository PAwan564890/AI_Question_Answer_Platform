"""Qdrant client factory and collection names.

Qdrant is the only database in this project. It plays two roles:

* a vector store for the knowledge base (``documents``: text chunks plus
  embeddings, searched by cosine similarity for RAG), and
* a document store for application data (``users``, ``chat_records``,
  ``audit_events``): these collections hold no vectors, only JSON payloads
  that are looked up by id or by an indexed payload field.
"""

from qdrant_client import AsyncQdrantClient

from app.core.config import Settings

USERS = "users"
CHAT_RECORDS = "chat_records"
AUDIT_EVENTS = "audit_events"
DOCUMENTS = "documents"
ALL_COLLECTIONS = (USERS, CHAT_RECORDS, AUDIT_EVENTS, DOCUMENTS)


def create_qdrant_client(settings: Settings) -> AsyncQdrantClient:
    """The client keeps a pooled HTTP connection; one instance is shared per process."""
    return AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=int(settings.qdrant_timeout_seconds),
    )
