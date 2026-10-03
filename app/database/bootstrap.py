"""Idempotent schema bootstrap: the Qdrant equivalent of a database migration.

Qdrant has no SQL schema, so "migrating" means making sure each collection and
each payload index exists. The function can be run any number of times; it only
creates what is missing. It runs once from the one-shot ``init`` Compose service
before any API replica starts, so replicas never race to create collections.
"""

import logging
import warnings

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qm

from app.database.client import AUDIT_EVENTS, CHAT_RECORDS, DOCUMENTS, USERS

logger = logging.getLogger(__name__)

# collection -> payload fields that are filtered or sorted on
_PAYLOAD_INDEXES: dict[str, dict[str, qm.PayloadSchemaType]] = {
    USERS: {"created_ts": qm.PayloadSchemaType.FLOAT},
    CHAT_RECORDS: {
        "user_id": qm.PayloadSchemaType.KEYWORD,
        "created_ts": qm.PayloadSchemaType.FLOAT,
    },
    AUDIT_EVENTS: {"created_ts": qm.PayloadSchemaType.FLOAT},
    DOCUMENTS: {
        "doc_id": qm.PayloadSchemaType.KEYWORD,
        "chunk_index": qm.PayloadSchemaType.INTEGER,
        "created_ts": qm.PayloadSchemaType.FLOAT,
    },
}


class SchemaMismatchError(RuntimeError):
    """The existing ``documents`` collection was built for another embedding size."""


async def ensure_collections(client: AsyncQdrantClient, embedding_dim: int) -> None:
    for name in (USERS, CHAT_RECORDS, AUDIT_EVENTS):
        if not await client.collection_exists(name):
            # No vectors: these collections are used as a payload (JSON) store.
            await client.create_collection(name, vectors_config={})
            logger.info("collection_created", extra={"collection": name})

    if not await client.collection_exists(DOCUMENTS):
        await client.create_collection(
            DOCUMENTS,
            vectors_config=qm.VectorParams(size=embedding_dim, distance=qm.Distance.COSINE),
        )
        logger.info("collection_created", extra={"collection": DOCUMENTS, "dim": embedding_dim})
    else:
        info = await client.get_collection(DOCUMENTS)
        existing = info.config.params.vectors
        if isinstance(existing, qm.VectorParams) and existing.size != embedding_dim:
            raise SchemaMismatchError(
                f"Collection '{DOCUMENTS}' stores {existing.size}-dimensional vectors but "
                f"EMBEDDING_DIM={embedding_dim}. Vectors from different embedding models are "
                "not comparable: re-ingest the documents into a fresh collection."
            )

    with warnings.catch_warnings():
        # The in-memory client used by the tests has no payload indexes and warns.
        warnings.simplefilter("ignore", UserWarning)
        for collection, fields in _PAYLOAD_INDEXES.items():
            for field_name, schema in fields.items():
                await client.create_payload_index(collection, field_name, field_schema=schema)
